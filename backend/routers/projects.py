"""Project CRUD, source media, saved clips and health endpoints."""
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from backend.core import jobs as job_service
from backend.services import projects_store

router = APIRouter(prefix="/api")


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, min_length=1, max_length=100)
    favorite: StrictBool | None = None
    archived: StrictBool | None = None
    trashed: StrictBool | None = None

    @model_validator(mode='after')
    def require_changes(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Provide at least one non-null project change.')
        return self


@router.get('/health')
def health():
    store = job_service.metadata_store()
    if store.database_url:
        with store.connection() as conn, conn.cursor() as cur:
            cur.execute('SELECT 1')
    return {'status': 'ok', 'metadata_storage': 'neon' if store.database_url else 'local'}


@router.get('/projects')
def list_projects(request: Request, q: str = ''):
    directory = projects_store.project_dir(request.state.user_id)
    items = [data for path, data in job_service.metadata_documents(
        directory.relative_to(job_service.JOBS_DIR).as_posix() + '/*.json', request.state.user_id)]
    items = [projects_store.project_defaults(p) for p in items if q.strip().casefold() in p['name'].casefold()]
    return {'projects': sorted(items, key=lambda p: p['updated_at'], reverse=True)}


@router.post('/projects', status_code=201)
def create_project(body: ProjectInput, request: Request):
    import time
    name = body.name.strip()
    if not name:
        raise HTTPException(400, 'Enter a project name.')
    now = time.time()
    project = {'id': uuid4().hex, 'name': name, 'user_id': request.state.user_id,
               'created_at': now, 'updated_at': now, 'thumbnail_key': None, 'saved_clips': [],
               'favorite': False, 'archived': False, 'trashed_at': None}
    directory = projects_store.project_dir(request.state.user_id)
    directory.mkdir(parents=True, exist_ok=True)
    with projects_store.lock:
        job_service.save_json(directory / (project['id'] + '.json'), project)
    return project


@router.patch('/projects/{project_id}')
def rename_project(project_id: str, body: ProjectUpdate, request: Request):
    changes = body.model_dump(exclude_unset=True)
    if 'name' in changes:
        changes['name'] = changes['name'].strip()
        if not changes['name']:
            raise HTTPException(400, 'Enter a project name.')
    with projects_store.lock:
        projects_store.require_project(project_id, request.state.user_id)
        if 'trashed' in changes:
            changes['trashed_at'] = time.time() if changes.pop('trashed') else None
        updated = job_service.metadata_store().update_project(
            projects_store.project_dir(request.state.user_id) / (project_id + '.json'),
            request.state.user_id, changes)
        return projects_store.project_defaults(updated)


@router.get('/projects/{project_id}')
def get_project(project_id: str, request: Request):
    with projects_store.lock:
        project = projects_store.require_project(project_id, request.state.user_id)
        return {**project, 'jobs': projects_store.project_jobs(project_id, request.state.user_id)}


@router.get('/projects/{project_id}/source/{job_id}')
def source_video(project_id: str, job_id: str, request: Request):
    from fastapi.responses import FileResponse
    projects_store.owner_for_job(project_id, job_id, request.state.user_id)
    source = projects_store.original_source(project_id, job_id, request.state.user_id)
    owner = projects_store.owner_for_job(project_id, job_id, request.state.user_id)
    return FileResponse(source, media_type='audio/mpeg' if owner.get('media_kind') == 'audio' else 'video/mp4', headers={'Cache-Control': 'no-store'})


@router.post('/projects/{project_id}/saved-clips')
def save_clip(project_id: str, body: projects_store.ClipInput, request: Request):
    projects_store.selected_clip(project_id, body, request.state.user_id)
    with projects_store.lock:
        projects_store.require_project(project_id, request.state.user_id)
        job_service.metadata_store().append_saved_clip(
            projects_store.project_dir(request.state.user_id) / (project_id + '.json'),
            request.state.user_id, body.model_dump())
    return {'saved': True}
