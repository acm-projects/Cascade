"""Generation history, submissions, retry and project deletion routes."""
import json
import os
import shutil
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from backend.core import jobs as job_service, storage as storage_service
from backend.routers import clips as clip_routes
from backend.services import projects_store, features as feature_workers

router = APIRouter(prefix="/api")


class GenerationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt: str = Field(min_length=1, max_length=2000)
    clip_count: int = Field(default=4, strict=True, ge=1, le=12)
    source_job: str
    parent_job: str | None = None
    parent_clip_index: int | None = Field(default=None, strict=True, ge=0)
    engine: str = 'agent'
    request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')


class RetryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')


@router.get('/projects/{project_id}/generations')
def groups(project_id: str, request: Request):
    with projects_store.lock:
        projects_store.require_project(project_id, request.state.user_id)
        rows = []
        generation_jobs = [j for j in reversed(projects_store.project_jobs(project_id, request.state.user_id)) if j['kind']=='generation']
        documents = job_service.metadata_store().read_many([
            job_service.JOBS_DIR / job['job_id'] / name for job in generation_jobs for name in ('results.json', 'failure.json')])
        for number, job in enumerate(generation_jobs, 1):
            folder = job_service.JOBS_DIR / job['job_id']
            if folder/'results.json' in documents:
                result = documents[folder/'results.json']
                status = {'state': 'done', **result}
            elif folder/'failure.json' in documents:
                status = {'state': 'error', **documents[folder/'failure.json']}
            else:
                with job_service.jobs_lock:
                    status = dict(job_service.jobs.get(job['job_id'], {'state':'error', 'message':'Processing was interrupted. Retry this request.'}))
            clips = [{**storage_service.public_clip(clip), 'clip_id': f"{job['job_id']}:{index}", 'clip_index': index}
                     for index, clip in enumerate(status.get('clips', []))]
            rows.append({**job, **{k:v for k,v in status.items() if k!='clips'}, 'clips': clips, 'order': job.get('creation_order') or number, 'search_type': 'follow-up' if job.get('parent_clip') else 'full-video'})
        from backend.editor_navigation import label_waves
        return {'groups': label_waves(rows)}


@router.post('/projects/{project_id}/generations', status_code=202)
def generate(project_id: str, body: GenerationInput, request: Request):
    user = request.state.user_id
    with projects_store.lock:
        projects_store.require_project(project_id, user)
        # Retrying the same submission does not enqueue another paid request.
        for job in projects_store.project_jobs(project_id, user):
            if job['kind'] != 'generation':
                continue
            owner = job_service.load_json(job_service.JOBS_DIR/job['job_id']/'owner.json')
            if owner.get('request_id') == body.request_id:
                return {'job_id': job['job_id']}
        source = projects_store.original_source(project_id, body.source_job, user)
        if body.parent_job:
            parent_source = projects_store.original_source(project_id, body.parent_job, user)
            if source.resolve() != parent_source.resolve():
                raise HTTPException(400, 'Parent clip and source must belong to the same original upload.')
        with source.open('rb') as file:
            result = clip_routes.upload_video(request=request, video=UploadFile(file=file, filename='saved-source.video'),
                search=body.prompt, mode='both', clip_length=30, project_id=project_id, engine=body.engine,
                clip_count=body.clip_count, source_job=source.parent.name,
                parent_job=body.parent_job, parent_clip_index=body.parent_clip_index)
        owner_path = job_service.JOBS_DIR/result['job_id']/'owner.json'
        owner = job_service.load_json(owner_path)
        owner['request_id'] = body.request_id
        job_service.save_json(owner_path, owner)
        return result


@router.post('/projects/{project_id}/generations/{job_id}/retry', status_code=202)
def retry(project_id: str, job_id: str, body: RetryInput, request: Request):
    with projects_store.lock:
        owner = projects_store.owner_for_job(project_id, job_id, request.state.user_id)
        if owner.get('kind', 'generation') != 'generation':
            raise HTTPException(400, 'Only generation requests can be retried here.')
        attempts = owner.get('retry_attempts', [])
        if any(a['id'] == body.request_id for a in attempts):
            return {'job_id': job_id}
        with job_service.jobs_lock:
            if job_service.jobs.get(job_id, {}).get('state') in ('queued', 'processing'):
                return {'job_id': job_id}
        folder = job_service.JOBS_DIR/job_id
        if job_service.metadata_exists(folder/'results.json'):
            raise HTTPException(409, 'This generation is complete. Reuse its prompt to create a new request.')
        source = projects_store.original_source(project_id, job_id, request.state.user_id)
        parent = owner.get('parent_clip')
        if parent:
            projects_store.selected_clip(project_id, projects_store.ClipInput(job_id=parent['job_id'], clip_index=parent['clip_index']), request.state.user_id)
        engine = owner.get('engine', 'agent')
        if engine in ('openai','qwen'): engine='agent'
        if engine not in ('agent','visual','speech'):
            raise HTTPException(409, 'Saved search method is unavailable. Reuse the prompt with a supported method.')
        problem=clip_routes.requirements_error() if engine=='agent' else (
            None if os.getenv('DEEPGRAM_API_KEY','').strip() else 'DEEPGRAM_API_KEY is not set. Add it to .env and restart the server.')
        if problem:
            raise HTTPException(503,problem)
        work_source = folder/'source.video'
        if not work_source.is_file():
            shutil.copyfile(source, work_source)
        previous_error = job_service.load_json(folder/'failure.json').get('message') if job_service.metadata_exists(folder/'failure.json') else 'Processing was interrupted.'
        owner.setdefault('history_id',job_id)
        owner.setdefault('created_at',(folder/'owner.json').stat().st_mtime)
        if not owner.get('creation_order'):
            chronological=[j for j in reversed(projects_store.project_jobs(project_id,request.state.user_id)) if j['kind']=='generation']
            owner['creation_order']=next(i for i,j in enumerate(chronological,1) if j['job_id']==job_id)
        owner['retry_attempts'] = attempts + [{'id':body.request_id, 'created_at':time.time(), 'previous_error':previous_error}]
        job_service.save_json(folder/'owner.json', owner)
        job_service.metadata_store().delete(folder/'failure.json')
        with job_service.jobs_lock:
            job_service.jobs[job_id] = {'state':'queued', 'message':'Retry queued...', 'clips':[]}
        job_service.save_json(folder/'progress.json', dict(job_service.jobs[job_id]))
        worker = clip_routes.process_upload if engine=='agent' else feature_workers.process_search
        try:
            job_service.worker.submit(worker, job_id, work_source, owner['prompt'], owner.get('mode','both') if engine=='agent' else engine, owner.get('clip_length',30))
        except Exception:
            projects_store.fail_feature(job_id, 'Could not queue the retry. Try again.')
            raise HTTPException(503, 'Could not queue the retry. Try again.')
        return {'job_id':job_id}


@router.delete('/projects/{project_id}')
def delete(project_id: str, request: Request):
    user = request.state.user_id
    with projects_store.lock:
        project = projects_store.require_project(project_id, user)
        owned = projects_store.project_jobs(project_id, user)
        ids = {row['job_id'] for row in owned}
        with job_service.jobs_lock:
            if any(job_service.jobs.get(j, {}).get('state') in ('queued','processing') for j in ids):
                raise HTTPException(409, 'Stop active generation/research and wait for it to finish before deleting this project.')
        # Be conservative with historical/shared references, including saved clips.
        referenced = set()
        candidates = job_service.metadata_documents('*/owner.json') + job_service.metadata_documents('*/results.json') + job_service.metadata_documents('projects/*/*.json')
        project_path = projects_store.project_dir(user)/(project_id+'.json')
        drafts = projects_store.project_dir(user)/'editor'/project_id
        for path, record in candidates:
            if path == project_path or path.parent.name in ids or drafts in path.parents:
                continue
            try:
                text = json.dumps(record)
                referenced.update(j for j in ids if j in text)
            except OSError:
                continue
        # Stage a recoverable logical deletion before removing any bytes.
        # If staging fails, put every record back so a failed request keeps
        # the project available. Shared source files are never staged.
        trash = job_service.JOBS_DIR / ('.deleted-' + uuid4().hex)
        trash.mkdir()
        moved, changed = [], []
        try:
            for job in owned:
                folder = job_service.JOBS_DIR/job['job_id']
                if job['job_id'] in referenced:
                    owner_path = folder/'owner.json'
                    owner = job_service.load_json(owner_path)
                    changed.append((owner_path, owner))
                    job_service.save_json(owner_path, {**owner, 'project_deleted': True})
                elif folder.is_dir():
                    destination = trash/job['job_id']
                    folder.rename(destination)
                    moved.append((destination, folder))
            if drafts.is_dir():
                destination = trash/'editor-drafts'
                drafts.rename(destination)
                moved.append((destination, drafts))
            if not project_path.is_file():
                job_service.metadata_store().local_write(project_path, project)
            destination = trash/'project.json'
            project_path.rename(destination)
            moved.append((destination, project_path))
            job_service.metadata_store().delete_project_metadata(project_path, user, ids, referenced)
        except (OSError, HTTPException) as error:
            for origin, destination in reversed(moved):
                origin.rename(destination)
            for path, owner in changed:
                job_service.save_json(path, owner)
            shutil.rmtree(trash, ignore_errors=True)
            raise HTTPException(500, 'Could not delete project files. Please retry.') from error
        for job_id in ids:
            with job_service.jobs_lock:
                job_service.jobs.pop(job_id, None)
        shutil.rmtree(trash, ignore_errors=True)
    return {'deleted': True, 'project_id': project_id, 'job_ids': sorted(ids)}
