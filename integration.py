"""Persistent, owner-checked adapters for the existing website and origin/main features.
No database configuration is replaced; records live beside existing video_jobs.
"""
import asyncio
import hashlib
import json
import re
import shutil
from pathlib import Path
from threading import RLock
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

host = None
lock = RLock()


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ClipInput(BaseModel):
    job_id: str
    clip_index: int = Field(default=0, ge=0, le=3)


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
        if owner.get('user_id') == user_id and owner.get('project_id') == project_id:
            result.append({'job_id': path.parent.name, 'prompt': owner.get('prompt', ''),
                           'source_name': owner.get('source_name', ''),
                           'kind': owner.get('kind', 'generation'), 'created_at': path.stat().st_mtime})
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


def new_feature_job(owner, kind):
    job_id = uuid4().hex
    folder = host.JOBS_DIR / job_id
    folder.mkdir()
    host.save_json(folder / 'owner.json', {**owner, 'kind': kind})
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
    host.save_json(host.JOBS_DIR / job_id / 'failure.json', {'message': message})
    host.update_job(job_id, state='error', message=message)


def publish_clip(folder, job_id, number, path, start, end, title, explanation='', captions=None):
    filename = f'clip_{number}.mp4'
    captions_filename = f'clip_{number}.vtt'
    shutil.copyfile(path, folder / filename)
    if captions and captions.is_file():
        shutil.copyfile(captions, folder / captions_filename)
    else:
        (folder / captions_filename).write_text('WEBVTT\n\n')
    storage = host.upload_clip_files(folder, job_id, filename, captions_filename)
    return {**storage, 'start': start, 'end': end, 'title': title, 'explanation': explanation,
            'clip_url': f'/clips/{job_id}/{filename}',
            'captions_url': f'/clips/{job_id}/{captions_filename}'}


def process_search(job_id, video_path, search, mode, target):
    """Reuse origin/main speech/visual search under the existing job and S3 contract."""
    from starlette.datastructures import UploadFile
    try:
        from backend.video_search.router import upload_video, OUTPUTS
        host.update_job(job_id, state='processing', message='Searching video and rendering captions...')
        with video_path.open('rb') as file:
            upload = UploadFile(file, filename='source.mp4')
            result = asyncio.run(upload_video(video=upload, search=search, mode=mode, clip_length=target))
        output = OUTPUTS / Path(result['clip_url']).name
        captions = video_path.parent / "search.vtt"
        captions.write_text(result["captions_vtt"], encoding="utf-8")
        try:
            clip = publish_clip(video_path.parent, job_id, 1, output, result['start'], result['end'],
                                search, result['match'] + ' · Captions are burned into the video.', captions=captions)
            finish_feature(job_id, {'clips': [clip]})
        finally:
            output.unlink(missing_ok=True)
    except ImportError:
        fail_feature(job_id, 'A processing dependency is missing. Install requirements.txt and restart the service.')
    except Exception:
        fail_feature(job_id)


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
    try:
        from backend.trends.router import _run_analysis, _new_job, JOBS, RESULTS_CACHE_DIR, _result_cache_key
        # Existing remote pipeline owns its progress/cache; adapt to persistent authenticated jobs.
        folder = host.JOBS_DIR / job_id
        work = folder / 'research'
        work.mkdir()
        internal_id = _new_job()
        host.update_job(job_id, state='processing', message='Analyzing your video and current YouTube trends...')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        cache = RESULTS_CACHE_DIR / (_result_cache_key(topic, digest) + '.json')
        if cache.is_file():
            result = json.loads(cache.read_text())
        else:
            _run_analysis(internal_id, topic, source, work, cache)
            outcome = JOBS[internal_id]
            if outcome['status'] != 'done':
                raise RuntimeError('Research failed')
            result = outcome['result']
        JOBS.pop(internal_id, None)
        finish_feature(job_id, {'clips': [], 'research': result})
    except ImportError:
        fail_feature(job_id, 'A processing dependency is missing. Install requirements.txt and restart the service.')
    except Exception:
        fail_feature(job_id)


def register(app, backend):
    global host
    host = backend

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
        job_id, folder = new_feature_job(owner, 'caption-styles')
        host.worker.submit(render_styles, job_id, source, clip)
        return {'job_id': job_id}

    @app.post('/api/projects/{project_id}/research', status_code=202)
    def start_research(project_id: str, body: ResearchInput, request: Request):
        owner = owner_for_job(project_id, body.job_id, request.state.user_id)
        source = host.JOBS_DIR / body.job_id / 'source.video'
        if not source.is_file():
            raise HTTPException(409, 'Open an original upload to run research.')
        if not body.topic.strip():
            raise HTTPException(400, 'Enter a topic.')
        job_id, folder = new_feature_job(owner, 'research')
        host.worker.submit(research, job_id, source, body.topic.strip())
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
