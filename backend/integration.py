"""Persistent, owner-checked adapters for the existing website and origin/main features.
No database configuration is replaced; records live beside existing video_jobs.
"""
import hashlib
import json
import logging
import time
import traceback
import re
import shutil
from pathlib import Path
from threading import RLock
from uuid import uuid4
from typing import Literal
from backend.pipeline_timing import StageTimer

from backend.settings.preferences import load_preferences, save_preferences

from fastapi import HTTPException, Request, File, Form, UploadFile
from pydantic import BaseModel, Field

host = None
lock = RLock()


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SettingsInput(BaseModel):
    video_type: Literal["", "tutorial", "vlog", "interview", "podcast"] = ""
    audience: str = Field(default="", max_length=200)
    tone: Literal["", "casual", "professional", "funny", "educational"] = ""
    goal: str = Field(default="", max_length=500)
    platforms: list[Literal["tiktok", "instagram", "linkedin", "youtube"]] = Field(default_factory=list, max_length=4)


class ClipInput(BaseModel):
    job_id: str
    clip_index: int = Field(default=0, ge=0)


class ResearchInput(BaseModel):
    job_id: str
    topic: str = Field(min_length=1, max_length=200)


def project_dir(user_id):
    return host.JOBS_DIR / 'projects' / hashlib.sha256(user_id.encode()).hexdigest()


def require_project(project_id, user_id):
    if not re.fullmatch(r'[0-9a-f]{32}', project_id):
        raise HTTPException(404, 'Project not found.')
    path = project_dir(user_id) / (project_id + '.json')
    if not path.is_file():
        raise HTTPException(404, 'Project not found.')
    data = json.loads(path.read_text())
    if data['user_id'] != user_id:
        raise HTTPException(404, 'Project not found.')
    return data


def project_jobs(project_id, user_id):
    result = []
    for path in host.JOBS_DIR.glob('*/owner.json'):
        owner = json.loads(path.read_text())
        if owner.get('user_id') == user_id and owner.get('project_id') == project_id and not owner.get('project_deleted'):
            result.append({'job_id': path.parent.name, 'prompt': owner.get('prompt', ''),
                           'source_name': owner.get('source_name', ''),
                           'kind': owner.get('kind', 'generation'), 'has_source': (path.parent / 'source.video').is_file(),
                           'created_at': owner.get('created_at', path.stat().st_mtime),
                           'history_id': owner.get('history_id', path.parent.name), 'creation_order': owner.get('creation_order'),
                           'retry_attempts': owner.get('retry_attempts', []),
                           'requested_clip_count': owner.get('requested_clip_count', 4),
                           'source_job': owner.get('source_job', path.parent.name), 'parent_clip': owner.get('parent_clip')})
    return sorted(result, key=lambda item: item['created_at'], reverse=True)


def owner_for_job(project_id, job_id, user_id):
    require_project(project_id, user_id)
    host.require_job_owner(job_id, user_id)
    owner = json.loads((host.JOBS_DIR / job_id / 'owner.json').read_text())
    if owner.get('project_id') != project_id:
        raise HTTPException(404, 'Job not found in this project.')
    return owner


def selected_clip(project_id, body, user_id):
    owner = owner_for_job(project_id, body.job_id, user_id)
    path = host.JOBS_DIR / body.job_id / 'results.json'
    if not path.is_file():
        raise HTTPException(409, 'Clip is not ready.')
    clips = json.loads(path.read_text()).get('clips', [])
    if body.clip_index >= len(clips):
        raise HTTPException(404, 'Clip not found.')
    return owner, clips[body.clip_index]


def original_source(project_id, job_id, user_id):
    visited = set()
    while job_id and job_id not in visited:
        visited.add(job_id)
        owner = owner_for_job(project_id, job_id, user_id)
        if owner.get('parent_job'):
            job_id = owner.get('parent_job')
            continue
        root = owner.get('source_job')
        if root and root != job_id:
            job_id = root
            continue
        source = host.JOBS_DIR / job_id / 'source.video'
        if source.is_file():
            return source
        job_id = owner.get('parent_job')
    raise HTTPException(409, 'Original source is unavailable. Choose an original upload from history.')


def new_feature_job(owner, kind, parent_job=None):
    job_id = uuid4().hex
    folder = host.JOBS_DIR / job_id
    folder.mkdir()
    host.save_json(folder / 'owner.json', {**owner, 'kind': kind, 'parent_job': parent_job, 'created_at': time.time()})
    with host.jobs_lock:
        host.jobs[job_id] = {'state': 'queued', 'message': 'Waiting to process...', 'clips': []}
    return job_id, folder


def finish_feature(job_id, result):
    host.save_json(host.JOBS_DIR / job_id / 'results.json', result)
    host.update_job(job_id, state='done', message='Processing complete.',
                    **{**result, 'clips': [host.public_clip(c) for c in result.get('clips', [])]})


def fail_feature(job_id, message=None):
    # Never return provider exceptions, credentials, or signed storage URLs.
    message = message or 'Processing failed. Check the required models, services, and credentials, then retry.'
    host.update_job(job_id, state='error', message=message)
    with host.jobs_lock:
        job = host.jobs[job_id]
        details = {key: job[key] for key in ('timings', 'timing_stage', 'timing_stage_started_at', 'updated_at', 'steps_log', 'steps_elapsed') if key in job}
    host.save_json(host.JOBS_DIR / job_id / 'failure.json', {'message': message, **details})


def publish_clip(folder, job_id, number, path, start, end, title, explanation='', captions=None):
    filename = f'clip_{number}.mp4'
    captions_filename = f'clip_{number}.vtt'
    shutil.copyfile(path, folder / filename)
    if captions and captions.is_file():
        shutil.copyfile(captions, folder / captions_filename)
    else:
        (folder / captions_filename).write_text('WEBVTT\n\n')
    storage = host.upload_clip_files(folder, job_id, filename, captions_filename)
    return {**storage, 'clip_id': f'{job_id}:{number-1}', 'start': start, 'end': end, 'title': title, 'explanation': explanation,
            'clip_url': f'/clips/{job_id}/{filename}',
            'captions_url': f'/clips/{job_id}/{captions_filename}'}


def process_search(job_id, video_path, search, mode, target):
    """Reuse origin/main speech/visual search under the existing job and S3 contract."""
    from starlette.datastructures import UploadFile
    stage = 'loading search dependencies'
    def timing(timings, active):
        host.update_job(job_id, timings=timings, timing_stage=active, timing_stage_started_at=time.time())
    timer = StageTimer(timing)
    def progress(message):
        nonlocal stage
        stage = message
        host.update_job(job_id, message=message)
    try:
        timer.start('Dependency imports')
        from backend.video_search.router import search_video, OUTPUTS
        from backend.generation import options, contextual_prompt
        requested_count, parent = options(video_path.parent)
        initial = timer.finish()
        def search_timing(timings, active):
            timing({**initial, **timings}, active)
        host.update_job(job_id, state='processing', message='Searching video and rendering captions...')
        with video_path.open('rb') as file:
            upload = UploadFile(file, filename='source.mp4')
            result = search_video(upload, contextual_prompt(search, parent), mode, target, progress=progress, timing=search_timing, requested_count=requested_count, parent_context=parent, followup_prompt=search)
        matches = result.get('clips', [result] if result.get('clip_url') else [])
        outputs = [OUTPUTS / Path(match['clip_url']).name for match in matches]
        try:
            timer.timings = {**initial, **result['timings']}
            clips = []
            for number, (match, output) in enumerate(zip(matches, outputs), 1):
                progress(f'Saving clip {number}/{len(matches)}...')
                captions = video_path.parent / f'search_{number}.vtt'
                captions.write_text(match['captions_vtt'], encoding='utf-8')
                timer.start('Clip storage')
                clips.append(publish_clip(video_path.parent, job_id, number, output, match['start'], match['end'],
                                          search, match['match'] + ' · Captions are burned into the video.', captions=captions))
            timings = timer.finish()
            finish_feature(job_id, {'clips': clips, 'timings': timings, 'requested_clip_count': requested_count,
                                    'selection_note': (f'Found {len(clips)} of {requested_count} requested suitable clips. ' if len(clips) < requested_count else '') + result.get('selection_note', '')})
        finally:
            for output in outputs:
                output.unlink(missing_ok=True)
    except ImportError:
        fail_feature(job_id, 'A processing dependency is missing. Install requirements.txt and restart the service.')
    except Exception as error:
        logging.getLogger(__name__).exception('Search job %s failed during %s', job_id, stage)
        fail_feature(job_id, host.processing_error(error, stage))


def render_styles(job_id, source, source_clip):
    try:
        from backend.clips.render_subtitles import generate_four_styled_clips
        folder = host.JOBS_DIR / job_id
        host.update_job(job_id, state='processing', message='Transcribing and rendering four caption styles...')
        names = generate_four_styled_clips(str(source), ['hormozi', 'minimalist', 'bold_viral', 'cinematic'],
                                           output_dir=folder, whole_clip=True)
        clips = []
        for index, name in enumerate(names, 1):
            clips.append(publish_clip(folder, job_id, index, folder / name, 0,
                         source_clip['end'] - source_clip['start'], name.removeprefix('output_').removesuffix('.mp4'),
                         captions=(folder / name).with_suffix('.vtt')))
        finish_feature(job_id, {'clips': clips})
    except ImportError:
        fail_feature(job_id, 'A processing dependency is missing. Install requirements.txt and restart the service.')
    except Exception:
        fail_feature(job_id)


def research(job_id, source, topic):
    work = None
    internal_id = None
    job_registry = None
    stage = 'loading the trends module'

    def progress(message):
        # Remember the last step so a failure can say where it happened.
        nonlocal stage
        stage = message
        print(f'[research {job_id[:8]}] {message}', flush=True)
        host.update_job(job_id, message=message)

    try:
        from backend.trends.router import _run_analysis, _new_job, JOBS, RESULTS_CACHE_DIR, _result_cache_key
        # Existing remote pipeline owns its progress/cache; adapt to persistent authenticated jobs.
        folder = host.JOBS_DIR / job_id
        work = folder / 'research'
        work.mkdir()
        internal_id = _new_job()
        job_registry = JOBS
        host.update_job(job_id, state='processing', message='Analyzing your video and current YouTube trends...')
        stage = 'reading your source video'
        print(f'[research {job_id[:8]}] topic={topic!r} source={source}', flush=True)
        hasher = hashlib.sha256()
        with source.open('rb') as video:
            while chunk := video.read(1024 * 1024):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        stage = 'checking for a cached result'
        cache = RESULTS_CACHE_DIR / (_result_cache_key(topic, digest) + '.json')
        if cache.is_file():
            print(f'[research {job_id[:8]}] using cached result', flush=True)
            result = json.loads(cache.read_text())
        else:
            _run_analysis(internal_id, topic, source, work, cache, progress=progress)
            outcome = JOBS[internal_id]
            if outcome['status'] != 'done':
                # The pipeline's own message can include provider details, so it stays in the API terminal.
                print(f"[research {job_id[:8]}] pipeline error while {stage}: {outcome.get('error')}", flush=True)
                raise RuntimeError('Research pipeline reported an error')
            result = outcome['result']
        finish_feature(job_id, {'clips': [], 'research': result})
    except ImportError:
        print(f'[research {job_id[:8]}] missing dependency while {stage}:', flush=True)
        traceback.print_exc()
        fail_feature(job_id, f'A processing dependency is missing (while {stage}). Install requirements.txt and restart the service.')
    except Exception as error:
        print(f'[research {job_id[:8]}] failed while {stage}:', flush=True)
        traceback.print_exc()
        fail_feature(job_id, f'Research failed while {stage} ({type(error).__name__}). Check the API terminal for the error details.')

    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
        if job_registry is not None and internal_id is not None:
            job_registry.pop(internal_id, None)

def register(app, backend):
    global host
    host = backend

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    @app.get('/settings', include_in_schema=False)
    def settings_page():
        return host.serve_new_page('settings_C.html')

    @app.get('/api/settings')
    def get_settings(request: Request):
        path = project_dir(request.state.user_id) / 'settings' / 'preferences.json'
        with lock:
            if path.is_file():
                return load_preferences(path)
            # Retain original global preferences as defaults; never overwrite them.
            legacy = Path(host.PROJECT_DIR) / 'preferences.json'
            return load_preferences(legacy if legacy.is_file() else None)

    @app.post('/api/settings')
    def set_settings(body: SettingsInput, request: Request):
        path = project_dir(request.state.user_id) / 'settings' / 'preferences.json'
        with lock:
            save_preferences(body.model_dump(), path)
        return {'saved': True, 'preferences': body.model_dump()}

    @app.get('/api/projects')
    def list_projects(request: Request):
        directory = project_dir(request.state.user_id)
        items = [json.loads(p.read_text()) for p in directory.glob('*.json')]
        return {'projects': sorted(items, key=lambda p: p['created_at'], reverse=True)}

    @app.post('/api/projects', status_code=201)
    def create_project(body: ProjectInput, request: Request):
        import time
        name = body.name.strip()
        if not name:
            raise HTTPException(400, 'Enter a project name.')
        project = {'id': uuid4().hex, 'name': name, 'user_id': request.state.user_id,
                   'created_at': time.time(), 'saved_clips': []}
        directory = project_dir(request.state.user_id)
        directory.mkdir(parents=True, exist_ok=True)
        with lock:
            host.save_json(directory / (project['id'] + '.json'), project)
        return project

    @app.get('/api/projects/{project_id}')
    def get_project(project_id: str, request: Request):
        with lock:
            project = require_project(project_id, request.state.user_id)
            return {**project, 'jobs': project_jobs(project_id, request.state.user_id)}

    @app.get('/api/projects/{project_id}/source/{job_id}')
    def source_video(project_id: str, job_id: str, request: Request):
        from fastapi.responses import FileResponse
        owner_for_job(project_id, job_id, request.state.user_id)
        source = host.JOBS_DIR / job_id / 'source.video'
        if not source.is_file():
            raise HTTPException(404, 'Source video is unavailable.')
        return FileResponse(source, media_type='application/octet-stream', headers={'Cache-Control': 'no-store'})

    @app.post('/api/projects/{project_id}/saved-clips')
    def save_clip(project_id: str, body: ClipInput, request: Request):
        selected_clip(project_id, body, request.state.user_id)
        with lock:
            project = require_project(project_id, request.state.user_id)
            entry = body.model_dump()
            if entry not in project['saved_clips']:
                project['saved_clips'].append(entry)
                host.save_json(project_dir(request.state.user_id) / (project_id + '.json'), project)
        return {'saved': True}

    @app.post('/api/projects/{project_id}/caption-styles', status_code=202)
    def caption_styles(project_id: str, body: ClipInput, request: Request):
        owner, clip = selected_clip(project_id, body, request.state.user_id)
        source = host.JOBS_DIR / body.job_id / f'clip_{body.clip_index + 1}.mp4'
        if not source.is_file():
            raise HTTPException(409, 'Local clip is unavailable for rendering. Original download remains available.')
        job_id, folder = new_feature_job(owner, 'caption-styles', body.job_id)
        host.worker.submit(render_styles, job_id, source, clip)
        return {'job_id': job_id}

    @app.post('/api/projects/{project_id}/research', status_code=202)
    def start_research(project_id: str, body: ResearchInput, request: Request):
        owner = owner_for_job(project_id, body.job_id, request.state.user_id)
        source = original_source(project_id, body.job_id, request.state.user_id)
        if not body.topic.strip():
            raise HTTPException(400, 'Enter a topic.')
        job_id, folder = new_feature_job(owner, 'research', body.job_id)
        host.worker.submit(research, job_id, source, body.topic.strip())
        return {'job_id': job_id}

    @app.post('/api/projects/{project_id}/research-upload', status_code=202)
    def research_upload(project_id: str, request: Request, video: UploadFile = File(...), topic: str = Form(...)):
        require_project(project_id, request.state.user_id)
        topic = topic.strip()
        if not topic or len(topic) > 200:
            raise HTTPException(400, 'Enter a research topic of 1–200 characters.')
        suffix = Path(video.filename or '').suffix.lower()
        if suffix not in {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}:
            raise HTTPException(400, 'Choose a supported video file.')
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise HTTPException(503, 'FFmpeg and ffprobe must be installed.')
        storage = host.resolve_storage_folder(request.state.user_id)
        owner = {'user_id': request.state.user_id, 'project_id': project_id,
                 'user_folder': storage['folder'], 'folder_source': storage['source'],
                 'source_name': Path(video.filename).name, 'prompt': topic}
        job_id, folder = new_feature_job(owner, 'research')
        source = folder / 'source.video'
        try:
            with source.open('wb') as destination:
                shutil.copyfileobj(video.file, destination)
            if source.stat().st_size == 0:
                raise HTTPException(400, 'The uploaded file is empty.')
        except Exception:
            fail_feature(job_id, 'The video upload failed. Select a nonempty video and retry.')
            raise
        finally:
            video.file.close()
        host.worker.submit(research, job_id, source, topic)
        return {'job_id': job_id}

    @app.get('/api/features/{job_id}')
    def feature_status(job_id: str, request: Request):
        host.require_job_owner(job_id, request.state.user_id)
        with host.jobs_lock:
            if job_id in host.jobs:
                return dict(host.jobs[job_id])
        folder = host.JOBS_DIR / job_id
        if (folder / 'failure.json').is_file():
            return {'state': 'error', **json.loads((folder / 'failure.json').read_text())}
        if (folder / 'results.json').is_file():
            result = json.loads((folder / 'results.json').read_text())
            return {'state': 'done', **result, 'clips': [host.public_clip(c) for c in result.get('clips', [])]}
        return {'state': 'error', 'message': 'Processing was interrupted by a server restart. Retry the operation.'}

    @app.post('/api/features/{job_id}/cancel')
    def cancel_feature(job_id: str, request: Request):
        host.require_job_owner(job_id, request.state.user_id)
        with host.jobs_lock:
            job = host.jobs.get(job_id)
            if not job or job.get('state') in ('done', 'error'):
                raise HTTPException(409, 'This job is no longer processing.')
            job['cancel_requested'] = True
            job['message'] = 'Stopping after the current processing step...'
        return {'message': 'Stop requested. The active model call or render may take up to its timeout to return.'}
