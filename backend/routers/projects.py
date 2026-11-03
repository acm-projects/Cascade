"""Project CRUD, source media, saved clips and health endpoints."""
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
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


@router.post('/projects/with-video', status_code=201)
def create_project_with_video(request: Request, name: str = Form(..., min_length=1, max_length=100),
                              video: UploadFile = File(...)):
    """One project = one video: save it as the project's source and start analysing it now."""
    import hashlib
    import shutil
    from pathlib import Path
    from backend import indexing
    from backend.agent.website import requirements_error
    from backend.core import storage as storage_service
    from backend.core.config import DEFAULT_FOLDER
    from backend.media import AUDIO_EXTENSIONS, validate_filename
    try:
        name = name.strip()
        if not name:
            raise HTTPException(400, 'Enter a project name.')
        validate_filename(video.filename)
        storage_service.validate_clip_storage()
        configuration_error = requirements_error()
        if configuration_error:
            raise HTTPException(503, configuration_error)
        if shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None:
            raise HTTPException(503, 'FFmpeg and ffprobe must be installed.')
        user_id = request.state.user_id
        storage = ({'folder': DEFAULT_FOLDER, 'source': 'local'} if storage_service.uses_local_storage()
                   else storage_service.resolve_storage_folder(user_id))
        source_name = Path(video.filename).name
        job_id = uuid4().hex
        folder = job_service.JOBS_DIR / job_id
        folder.mkdir()
        try:
            fingerprint = hashlib.sha256()
            with (folder / 'source.video').open('wb') as destination:
                while chunk := video.file.read(1024 * 1024):
                    fingerprint.update(chunk)
                    destination.write(chunk)
            if (folder / 'source.video').stat().st_size == 0:
                raise HTTPException(400, 'The uploaded file is empty.')
            now = time.time()
            project = {'id': uuid4().hex, 'name': name, 'user_id': user_id, 'created_at': now, 'updated_at': now,
                       'thumbnail_key': None, 'saved_clips': [], 'favorite': False, 'archived': False,
                       'trashed_at': None, 'source_job': job_id, 'source_name': source_name}
            job_service.save_json(folder / 'owner.json', {
                'kind': 'source', 'user_id': user_id, 'project_id': project['id'], 'source_job': job_id,
                'source_name': source_name, 'created_at': now, 'video_sha256': fingerprint.hexdigest(),
                'media_kind': 'audio' if Path(source_name).suffix.lower() in AUDIO_EXTENSIONS else 'video',
                'user_folder': storage['folder'], 'folder_source': storage['source']})
            directory = projects_store.project_dir(user_id)
            directory.mkdir(parents=True, exist_ok=True)
            with projects_store.lock:
                job_service.save_json(directory / (project['id'] + '.json'), project)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    finally:
        video.file.close()
    indexing.start(job_id)
    return project


@router.post('/projects/{project_id}/reindex', status_code=202)
def reindex_project(project_id: str, request: Request):
    from backend import indexing
    project = projects_store.require_project(project_id, request.state.user_id)
    if not project.get('source_job'):
        raise HTTPException(400, 'This project has no video to analyse.')
    if indexing.status(project['source_job']).get('state') in ('queued', 'processing'):
        return {'state': 'processing'}
    indexing.start(project['source_job'])
    return {'state': 'queued'}


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


@router.get('/projects/{project_id}/source/{job_id}/frame')
def source_frame(project_id: str, job_id: str, request: Request, t: float | None = Query(None, ge=0)):
    """One small JPEG frame of the source video at `t` seconds (default: 10% in): the thumbnail of the
    source box and of every clip box (a clip uses a moment inside its own range), even before it renders."""
    from fastapi.responses import Response
    media_kind, duration, source = owned_source(project_id, job_id, request.state.user_id)
    if media_kind == 'audio':
        raise HTTPException(404, 'Audio has no picture.')
    try:
        jpeg = source_frame_jpeg(str(source), source.stat().st_mtime_ns, frame_time(duration, t))
    except RuntimeError:
        raise HTTPException(404, 'No frame at that time.') from None
    # The same source and time always give the same picture, so the browser may keep it.
    return Response(jpeg, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=86400'})


OWNERSHIP_SECONDS = 60
owned_sources = {}  # (user, project, job) -> (expires, media kind, duration, source path)


def owned_source(project_id, job_id, user_id):
    """The ownership check behind thumbnails, remembered for a minute: a Studio page asks for many
    frames at once, and with Neon every check is two network round trips."""
    key, now = (user_id, project_id, job_id), time.monotonic()
    hit = owned_sources.get(key)
    if hit and hit[0] > now:
        return hit[1:]
    owner = projects_store.owner_for_job(project_id, job_id, user_id)
    source = projects_store.original_source(project_id, job_id, user_id)
    if len(owned_sources) > 1000:
        owned_sources.clear()
    owned_sources[key] = (now + OWNERSHIP_SECONDS, owner.get('media_kind'), owner.get('duration') or 0, source)
    return owned_sources[key][1:]


def frame_time(duration, t):
    """Where a thumbnail is taken: `t`, or 10% in when no time is given; always inside the video."""
    at = duration * 0.1 if t is None else t
    if duration:
        at = min(at, duration - 0.1)
    return round(max(0.0, at), 1)


@lru_cache(maxsize=512)
def source_frame_jpeg(path, revision, at):
    from backend.agent.tools import grab_frame_jpeg
    return grab_frame_jpeg(Path(path), at, width=384)


frame_pool = ThreadPoolExecutor(max_workers=4)


def prepare_frames(source, times):
    """Make thumbnails before the browser asks for them (in the background), so they appear together
    with their clip boxes. A failure here only means the frame is made when it is requested."""
    source = Path(source)
    try:
        revision = source.stat().st_mtime_ns
    except OSError:
        return
    for at in times:
        frame_pool.submit(_prepare_frame, str(source), revision, at)


def _prepare_frame(path, revision, at):
    try:
        source_frame_jpeg(path, revision, at)
    except Exception:
        pass


@router.post('/projects/{project_id}/saved-clips')
def save_clip(project_id: str, body: projects_store.ClipInput, request: Request):
    projects_store.selected_clip(project_id, body, request.state.user_id)
    with projects_store.lock:
        projects_store.require_project(project_id, request.state.user_id)
        job_service.metadata_store().append_saved_clip(
            projects_store.project_dir(request.state.user_id) / (project_id + '.json'),
            request.state.user_id, body.model_dump())
    return {'saved': True}
