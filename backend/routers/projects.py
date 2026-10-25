"""Project-owned source upload and private thumbnail delivery."""
import time
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from backend import integration as store
from backend.services.uploads import save_uploaded_source
from backend.services.sessions import save
from backend.services.source_prep import prepare_source

router = APIRouter()


@router.post('/api/projects/{project_id}/source', status_code=202)
def upload_source(project_id: str, request: Request, video: UploadFile = File(...)):
    host = store.host
    with store.lock:
        project = store.require_project(project_id, request.state.user_id)
        if project.get('source_job'):
            raise HTTPException(409, 'This project already has a source video')
        job_id = save_uploaded_source(video, {
            'user_id': request.state.user_id, 'project_id': project_id,
            'kind': 'source', 'created_at': time.time(),
        })
        project.update(source_job=job_id, source_status='processing', source_duration=None,
                       thumbnail_url=None, source_error=None)
        save(project)
        with host.jobs_lock:
            host.jobs[job_id] = {'state': 'queued', 'message': 'Preparing source video...', 'clips': []}
        host.save_json(host.JOBS_DIR / job_id / 'progress.json', dict(host.jobs[job_id]))
        try:
            host.worker.submit(prepare_source, job_id, project_id, request.state.user_id)
        except Exception:
            project.update(source_status='error', source_error='Could not queue source preparation.')
            save(project)
            store.fail_feature(job_id, project['source_error'])
            raise HTTPException(503, project['source_error'])
        return {'source_job': job_id, 'status': 'processing'}


@router.get('/api/projects/{project_id}/thumbnail')
def thumbnail(project_id: str, request: Request):
    with store.lock:
        project = store.require_project(project_id, request.state.user_id)
        if not project.get('source_job'):
            raise HTTPException(404, 'Project thumbnail is not available yet.')
        store.owner_for_job(project_id, project['source_job'], request.state.user_id)
        path = store.host.JOBS_DIR / project['source_job'] / 'thumbnail.jpg'
        if not path.is_file():
            raise HTTPException(404, 'Project thumbnail is not available yet.')
        return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})
