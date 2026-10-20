"""Owner-scoped project deletion and reusable-source generation requests."""
import json
import os
import shutil
import time
from uuid import uuid4

from fastapi import HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, ConfigDict


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


def register(app, host, integration):
    @app.get('/api/projects/{project_id}/generations')
    def groups(project_id: str, request: Request):
        with integration.lock:
            integration.require_project(project_id, request.state.user_id)
            rows = []
            for number, job in enumerate((j for j in reversed(integration.project_jobs(project_id, request.state.user_id)) if j['kind']=='generation'), 1):
                folder = host.JOBS_DIR / job['job_id']
                if host.metadata_exists(folder/'results.json'):
                    result = host.load_json(folder/'results.json')
                    status = {'state': 'done', **result}
                elif host.metadata_exists(folder/'failure.json'):
                    status = {'state': 'error', **host.load_json(folder/'failure.json')}
                else:
                    with host.jobs_lock:
                        status = dict(host.jobs.get(job['job_id'], {'state':'error', 'message':'Processing was interrupted. Retry this request.'}))
                clips = [{**host.public_clip(clip), 'clip_id': f"{job['job_id']}:{index}", 'clip_index': index}
                         for index, clip in enumerate(status.get('clips', []))]
                rows.append({**job, **{k:v for k,v in status.items() if k!='clips'}, 'clips': clips, 'order': job.get('creation_order') or number, 'search_type': 'follow-up' if job.get('parent_clip') else 'full-video'})
            return {'groups': rows}

    @app.post('/api/projects/{project_id}/generations', status_code=202)
    def generate(project_id: str, body: GenerationInput, request: Request):
        user = request.state.user_id
        with integration.lock:
            integration.require_project(project_id, user)
            # Retrying the same submission does not enqueue another paid request.
            for job in integration.project_jobs(project_id, user):
                if job['kind'] != 'generation':
                    continue
                owner = host.load_json(host.JOBS_DIR/job['job_id']/'owner.json')
                if owner.get('request_id') == body.request_id:
                    return {'job_id': job['job_id']}
            source = integration.original_source(project_id, body.source_job, user)
            if body.parent_job:
                parent_source = integration.original_source(project_id, body.parent_job, user)
                if source.resolve() != parent_source.resolve():
                    raise HTTPException(400, 'Parent clip and source must belong to the same original upload.')
            with source.open('rb') as file:
                result = host.upload_video(request=request, video=UploadFile(file=file, filename='saved-source.video'),
                    search=body.prompt, mode='both', clip_length=30, project_id=project_id, engine=body.engine,
                    clip_count=body.clip_count, source_job=source.parent.name,
                    parent_job=body.parent_job, parent_clip_index=body.parent_clip_index)
            owner_path = host.JOBS_DIR/result['job_id']/'owner.json'
            owner = host.load_json(owner_path)
            owner['request_id'] = body.request_id
            host.save_json(owner_path, owner)
            return result

    @app.post('/api/projects/{project_id}/generations/{job_id}/retry', status_code=202)
    def retry(project_id: str, job_id: str, body: RetryInput, request: Request):
        with integration.lock:
            owner = integration.owner_for_job(project_id, job_id, request.state.user_id)
            if owner.get('kind', 'generation') != 'generation':
                raise HTTPException(400, 'Only generation requests can be retried here.')
            attempts = owner.get('retry_attempts', [])
            if any(a['id'] == body.request_id for a in attempts):
                return {'job_id': job_id}
            with host.jobs_lock:
                if host.jobs.get(job_id, {}).get('state') in ('queued', 'processing'):
                    return {'job_id': job_id}
            folder = host.JOBS_DIR/job_id
            if host.metadata_exists(folder/'results.json'):
                raise HTTPException(409, 'This generation is complete. Reuse its prompt to create a new request.')
            source = integration.original_source(project_id, job_id, request.state.user_id)
            parent = owner.get('parent_clip')
            if parent:
                integration.selected_clip(project_id, integration.ClipInput(job_id=parent['job_id'], clip_index=parent['clip_index']), request.state.user_id)
            engine = owner.get('engine', 'agent')
            if engine in ('openai','qwen'): engine='agent'
            if engine not in ('agent','visual','speech'):
                raise HTTPException(409, 'Saved search method is unavailable. Reuse the prompt with a supported method.')
            problem=host.requirements_error() if engine=='agent' else (
                None if os.getenv('DEEPGRAM_API_KEY','').strip() else 'DEEPGRAM_API_KEY is not set. Add it to .env and restart the server.')
            if problem:
                raise HTTPException(503,problem)
            work_source = folder/'source.video'
            if not work_source.is_file():
                shutil.copyfile(source, work_source)
            previous_error = host.load_json(folder/'failure.json').get('message') if host.metadata_exists(folder/'failure.json') else 'Processing was interrupted.'
            owner.setdefault('history_id',job_id)
            owner.setdefault('created_at',(folder/'owner.json').stat().st_mtime)
            if not owner.get('creation_order'):
                chronological=[j for j in reversed(integration.project_jobs(project_id,request.state.user_id)) if j['kind']=='generation']
                owner['creation_order']=next(i for i,j in enumerate(chronological,1) if j['job_id']==job_id)
            owner['retry_attempts'] = attempts + [{'id':body.request_id, 'created_at':time.time(), 'previous_error':previous_error}]
            host.save_json(folder/'owner.json', owner)
            host.metadata_store().delete(folder/'failure.json')
            with host.jobs_lock:
                host.jobs[job_id] = {'state':'queued', 'message':'Retry queued...', 'clips':[]}
            host.save_json(folder/'progress.json', dict(host.jobs[job_id]))
            worker = host.process_upload if engine=='agent' else integration.process_search
            try:
                host.worker.submit(worker, job_id, work_source, owner['prompt'], owner.get('mode','both') if engine=='agent' else engine, owner.get('clip_length',30))
            except Exception:
                integration.fail_feature(job_id, 'Could not queue the retry. Try again.')
                raise HTTPException(503, 'Could not queue the retry. Try again.')
            return {'job_id':job_id}

    @app.delete('/api/projects/{project_id}')
    def delete(project_id: str, request: Request):
        user = request.state.user_id
        with integration.lock:
            project = integration.require_project(project_id, user)
            owned = integration.project_jobs(project_id, user)
            ids = {row['job_id'] for row in owned}
            with host.jobs_lock:
                if any(host.jobs.get(j, {}).get('state') in ('queued','processing') for j in ids):
                    raise HTTPException(409, 'Stop active generation/research and wait for it to finish before deleting this project.')
            # Be conservative with historical/shared references, including saved clips.
            referenced = set()
            candidates = host.metadata_documents('*/owner.json') + host.metadata_documents('*/results.json') + host.metadata_documents('projects/*/*.json')
            project_path = integration.project_dir(user)/(project_id+'.json')
            drafts = integration.project_dir(user)/'editor'/project_id
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
            trash = host.JOBS_DIR / ('.deleted-' + uuid4().hex)
            trash.mkdir()
            moved, changed = [], []
            try:
                for job in owned:
                    folder = host.JOBS_DIR/job['job_id']
                    if job['job_id'] in referenced:
                        owner_path = folder/'owner.json'
                        owner = host.load_json(owner_path)
                        changed.append((owner_path, owner))
                        host.save_json(owner_path, {**owner, 'project_deleted': True})
                    elif folder.is_dir():
                        destination = trash/job['job_id']
                        folder.rename(destination)
                        moved.append((destination, folder))
                if drafts.is_dir():
                    destination = trash/'editor-drafts'
                    drafts.rename(destination)
                    moved.append((destination, drafts))
                if not project_path.is_file():
                    host.metadata_store().local_write(project_path, project)
                destination = trash/'project.json'
                project_path.rename(destination)
                moved.append((destination, project_path))
                host.metadata_store().delete_project_metadata(project_path, user, ids, referenced)
            except (OSError, HTTPException) as error:
                for origin, destination in reversed(moved):
                    origin.rename(destination)
                for path, owner in changed:
                    host.save_json(path, owner)
                shutil.rmtree(trash, ignore_errors=True)
                raise HTTPException(500, 'Could not delete project files. Please retry.') from error
            for job_id in ids:
                with host.jobs_lock:
                    host.jobs.pop(job_id, None)
            shutil.rmtree(trash, ignore_errors=True)
        return {'deleted': True, 'project_id': project_id, 'job_ids': sorted(ids)}
