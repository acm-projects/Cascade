"""Research, caption styles and feature status/cancellation endpoints."""
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from backend.core import jobs as job_service, storage as storage_service
from backend.services import projects_store, features as feature_workers

router = APIRouter(prefix="/api")


class ResearchInput(BaseModel):
    job_id: str
    topic: str = Field(min_length=1, max_length=200)


@router.post('/projects/{project_id}/caption-styles', status_code=202)
def caption_styles(project_id: str, body: projects_store.ClipInput, request: Request):
    owner, clip = projects_store.selected_clip(project_id, body, request.state.user_id)
    source = job_service.JOBS_DIR / body.job_id / f'clip_{body.clip_index + 1}.mp4'
    if not source.is_file():
        raise HTTPException(409, 'Local clip is unavailable for rendering. Original download remains available.')
    job_id, folder = projects_store.new_feature_job(owner, 'caption-styles', body.job_id)
    job_service.worker.submit(feature_workers.render_styles, job_id, source, clip)
    return {'job_id': job_id}


@router.post('/projects/{project_id}/research', status_code=202)
def start_research(project_id: str, body: ResearchInput, request: Request):
    owner = projects_store.owner_for_job(project_id, body.job_id, request.state.user_id)
    source = projects_store.original_source(project_id, body.job_id, request.state.user_id)
    if not body.topic.strip():
        raise HTTPException(400, 'Enter a topic.')
    job_id, folder = projects_store.new_feature_job(owner, 'research', body.job_id)
    job_service.worker.submit(feature_workers.research, job_id, source, body.topic.strip())
    return {'job_id': job_id}


@router.post('/projects/{project_id}/research-upload', status_code=202)
def research_upload(project_id: str, request: Request, video: UploadFile = File(...), topic: str = Form(...)):
    projects_store.require_project(project_id, request.state.user_id)
    topic = topic.strip()
    if not topic or len(topic) > 200:
        raise HTTPException(400, 'Enter a research topic of 1–200 characters.')
    suffix = Path(video.filename or '').suffix.lower()
    if suffix not in {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}:
        raise HTTPException(400, 'Choose a supported video file.')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise HTTPException(503, 'FFmpeg and ffprobe must be installed.')
    storage = storage_service.resolve_storage_folder(request.state.user_id)
    owner = {'user_id': request.state.user_id, 'project_id': project_id,
             'user_folder': storage['folder'], 'folder_source': storage['source'],
             'source_name': Path(video.filename).name, 'prompt': topic}
    job_id, folder = projects_store.new_feature_job(owner, 'research')
    source = folder / 'source.video'
    try:
        with source.open('wb') as destination:
            shutil.copyfileobj(video.file, destination)
        if source.stat().st_size == 0:
            raise HTTPException(400, 'The uploaded file is empty.')
    except Exception:
        projects_store.fail_feature(job_id, 'The video upload failed. Select a nonempty video and retry.')
        raise
    finally:
        video.file.close()
    job_service.worker.submit(feature_workers.research, job_id, source, topic)
    return {'job_id': job_id}


@router.get('/features/{job_id}')
def feature_status(job_id: str, request: Request):
    job_service.require_job_owner(job_id, request.state.user_id)
    with job_service.jobs_lock:
        if job_id in job_service.jobs:
            return dict(job_service.jobs[job_id])
    folder = job_service.JOBS_DIR / job_id
    if job_service.metadata_exists(folder / 'failure.json'):
        return {'state': 'error', **job_service.load_json(folder / 'failure.json')}
    if job_service.metadata_exists(folder / 'results.json'):
        result = job_service.load_json(folder / 'results.json')
        return {'state': 'done', **result, 'clips': [storage_service.public_clip(c) for c in result.get('clips', [])]}
    return {'state': 'error', 'message': 'Processing was interrupted by a server restart. Retry the operation.'}


@router.post('/features/{job_id}/cancel')
def cancel_feature(job_id: str, request: Request):
    job_service.require_job_owner(job_id, request.state.user_id)
    with job_service.jobs_lock:
        job = job_service.jobs.get(job_id)
        if not job or job.get('state') in ('done', 'error'):
            raise HTTPException(409, 'This job is no longer processing.')
        job['cancel_requested'] = True
        job['message'] = 'Stopping after the current processing step...'
    return {'message': 'Stop requested. The active model call or render may take up to its timeout to return.'}
