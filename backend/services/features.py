"""Background search, caption-style and research workers."""
import hashlib
import logging
import shutil
import time
from pathlib import Path

from backend.core import jobs as job_service, storage as storage_service
from backend.pipeline_timing import StageTimer
from backend.services import projects_store


def publish_clip(folder, job_id, number, path, start, end, title, explanation='', captions=None):
    filename = f'clip_{number}.mp4'
    captions_filename = f'clip_{number}.vtt'
    shutil.copyfile(path, folder / filename)
    if captions and captions.is_file():
        shutil.copyfile(captions, folder / captions_filename)
    else:
        (folder / captions_filename).write_text('WEBVTT\n\n')
    storage = storage_service.upload_clip_files(folder, job_id, filename, captions_filename)
    return {**storage, 'clip_id': f'{job_id}:{number-1}', 'start': start, 'end': end, 'title': title, 'explanation': explanation,
            'clip_url': f'/clips/{job_id}/{filename}',
            'captions_url': f'/clips/{job_id}/{captions_filename}'}


def process_search(job_id, video_path, search, mode, target):
    """Reuse origin/main speech/visual search under the existing job and S3 contract."""
    from starlette.datastructures import UploadFile
    stage = 'loading search dependencies'
    def timing(timings, active):
        job_service.update_job(job_id, timings=timings, timing_stage=active, timing_stage_started_at=time.time())
    timer = StageTimer(timing)
    def progress(message):
        nonlocal stage
        stage = message
        job_service.update_job(job_id, message=message)
    try:
        if job_service.load_json(job_service.JOBS_DIR/job_id/'owner.json').get('media_kind') == 'audio':
            from backend.routers import clips as clip_routes
            clip_routes.process_upload(job_id, video_path, search, 'speech', target)
            return
        timer.start('Dependency imports')
        from backend.video_search.router import search_video, OUTPUTS
        from backend.generation import options, contextual_prompt
        requested_count, parent = options(video_path.parent)
        initial = timer.finish()
        def search_timing(timings, active):
            timing({**initial, **timings}, active)
        job_service.update_job(job_id, state='processing', message='Searching video and rendering captions...')
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
            projects_store.finish_feature(job_id, {'clips': clips, 'timings': timings, 'requested_clip_count': requested_count,
                                    'selection_note': (f'Found {len(clips)} of {requested_count} requested suitable clips. ' if len(clips) < requested_count else '') + result.get('selection_note', '')})
        finally:
            for output in outputs:
                output.unlink(missing_ok=True)
    except ImportError:
        projects_store.fail_feature(job_id, 'A processing dependency is missing. Install requirements.txt and restart the service.')
    except Exception as error:
        logging.getLogger(__name__).exception('Search job %s failed during %s', job_id, stage)
        projects_store.fail_feature(job_id, job_service.processing_error(error, stage))


def render_styles(job_id, source, source_clip):
    try:
        from backend.clips.render_subtitles import generate_four_styled_clips
        folder = job_service.JOBS_DIR / job_id
        job_service.update_job(job_id, state='processing', message='Transcribing and rendering four caption styles...')
        names = generate_four_styled_clips(str(source), ['hormozi', 'minimalist', 'bold_viral', 'cinematic'],
                                           output_dir=folder, whole_clip=True)
        clips = []
        for index, name in enumerate(names, 1):
            clips.append(publish_clip(folder, job_id, index, folder / name, 0,
                         source_clip['end'] - source_clip['start'], name.removeprefix('output_').removesuffix('.mp4'),
                         captions=(folder / name).with_suffix('.vtt')))
        projects_store.finish_feature(job_id, {'clips': clips})
    except ImportError:
        projects_store.fail_feature(job_id, 'A processing dependency is missing. Install requirements.txt and restart the service.')
    except Exception:
        projects_store.fail_feature(job_id)


def research(job_id, source, topic):
    work = None
    internal_id = None
    job_registry = None
    try:
        from backend.trends.router import _run_analysis, _new_job, JOBS, RESULTS_CACHE_DIR, _result_cache_key
        # Existing remote pipeline owns its progress/cache; adapt to persistent authenticated jobs.
        folder = job_service.JOBS_DIR / job_id
        work = folder / 'research'
        work.mkdir()
        internal_id = _new_job()
        job_registry = JOBS
        job_service.update_job(job_id, state='processing', message='Analyzing your video and current YouTube trends...')
        hasher = hashlib.sha256()
        with source.open('rb') as video:
            while chunk := video.read(1024 * 1024):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        cache = RESULTS_CACHE_DIR / (_result_cache_key(topic, digest) + '.json')
        if cache.is_file() and __import__('time').time()-cache.stat().st_mtime < 21600:
            result = job_service.load_json(cache)
        else:
            _run_analysis(internal_id, topic, source, work, cache,
                          progress=lambda message: job_service.update_job(job_id, message=message))
            outcome = JOBS[internal_id]
            if outcome['status'] != 'done':
                raise RuntimeError('Research failed')
            result = outcome['result']
        projects_store.finish_feature(job_id, {'clips': [], 'research': result})
    except ImportError:
        projects_store.fail_feature(job_id, 'A processing dependency is missing. Install requirements.txt and restart the service.')
    except Exception:
        projects_store.fail_feature(job_id)

    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
        if job_registry is not None and internal_id is not None:
            job_registry.pop(internal_id, None)
