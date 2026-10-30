"""Shared owner-checked project metadata and feature job persistence."""
import hashlib
import re
import time
from threading import RLock
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.core import jobs as job_service, storage as storage_service

lock = RLock()


class ClipInput(BaseModel):
    job_id: str
    clip_index: int = Field(default=0, ge=0)


def project_dir(user_id):
    return job_service.JOBS_DIR / 'projects' / hashlib.sha256(user_id.encode()).hexdigest()


def require_project(project_id, user_id):
    if not re.fullmatch(r'[0-9a-f]{32}', project_id):
        raise HTTPException(404, 'Project not found.')
    path = project_dir(user_id) / (project_id + '.json')
    if not job_service.metadata_exists(path):
        raise HTTPException(404, 'Project not found.')
    data = project_defaults(job_service.load_json(path))
    if data['user_id'] != user_id:
        raise HTTPException(404, 'Project not found.')
    return data


def project_defaults(data):
    return {'updated_at': data['created_at'], 'thumbnail_key': None,
            'favorite': False, 'archived': False, 'trashed_at': None, **data}


def project_jobs(project_id, user_id):
    result = []
    for path, owner in job_service.metadata_documents('*/owner.json', user_id):
        if owner.get('user_id') == user_id and owner.get('project_id') == project_id and not owner.get('project_deleted'):
            result.append({'job_id': path.parent.name, 'prompt': owner.get('prompt', ''),
                           'source_name': owner.get('source_name', ''),
                           'kind': owner.get('kind', 'generation'), 'media_kind': owner.get('media_kind', 'video'), 'has_source': (path.parent / 'source.video').is_file() or bool(owner.get('source_s3_key')),
                           'created_at': owner.get('created_at', path.stat().st_mtime if path.is_file() else 0),
                           'session_id': owner.get('session_id'), 'wave_id': owner.get('wave_id'),
                           'history_id': owner.get('history_id', path.parent.name), 'creation_order': owner.get('creation_order'),
                           'retry_attempts': owner.get('retry_attempts', []),
                           'requested_clip_count': owner.get('requested_clip_count', 4),
                           'source_job': owner.get('source_job', path.parent.name), 'parent_clip': owner.get('parent_clip'),
                           'parent_clips': owner.get('parent_clips', []), 'studio_session_id': owner.get('studio_session_id'),
                           'studio_revision_of': owner.get('studio_revision_of'), 'studio_revision_targets': owner.get('studio_revision_targets', [])})
    return sorted(result, key=lambda item: item['created_at'], reverse=True)


def owner_for_job(project_id, job_id, user_id):
    require_project(project_id, user_id)
    job_service.require_job_owner(job_id, user_id)
    owner = job_service.load_json(job_service.JOBS_DIR / job_id / 'owner.json')
    if owner.get('project_id') != project_id:
        raise HTTPException(404, 'Job not found in this project.')
    return owner


def selected_clip(project_id, body, user_id):
    owner = owner_for_job(project_id, body.job_id, user_id)
    path = job_service.JOBS_DIR / body.job_id / 'results.json'
    if not job_service.metadata_exists(path):
        with job_service.jobs_lock:
            running = job_service.jobs.get(body.job_id, {})
            clips = list(running.get('clips', [])) if running.get('state') == 'processing' else []
        if not clips:
            raise HTTPException(409, 'Clip is not ready.')
    else:
        clips = job_service.load_json(path).get('clips', [])
    if body.clip_index < 0 or body.clip_index >= len(clips):
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
        source = job_service.JOBS_DIR / job_id / 'source.video'
        if not source.is_file() and owner.get('source_s3_key'):
            temporary = source.with_name(uuid4().hex+'.download')
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                storage_service.s3_client().download_file(owner['source_s3_bucket'], owner['source_s3_key'], str(temporary))
                temporary.replace(source)
            except Exception:
                raise HTTPException(503, 'Could not retrieve the original media from storage. Retry shortly.') from None
            finally:
                temporary.unlink(missing_ok=True)
        if source.is_file():
            return source
        job_id = owner.get('parent_job')
    raise HTTPException(409, 'Original source is unavailable. Choose an original upload from history.')


def new_feature_job(owner, kind, parent_job=None):
    job_id = uuid4().hex
    folder = job_service.JOBS_DIR / job_id
    folder.mkdir()
    job_service.save_json(folder / 'owner.json', {**owner, 'kind': kind, 'parent_job': parent_job, 'created_at': time.time()})
    with job_service.jobs_lock:
        job_service.jobs[job_id] = {'state': 'queued', 'message': 'Waiting to process...', 'clips': []}
    return job_id, folder


def finish_feature(job_id, result):
    job_service.save_json(job_service.JOBS_DIR / job_id / 'results.json', result)
    job_service.update_job(job_id, state='done', message='Processing complete.',
                    **{**result, 'clips': [storage_service.public_clip(c) for c in result.get('clips', [])]})


def fail_feature(job_id, message=None):
    # Never return provider exceptions, credentials, or signed storage URLs.
    message = message or 'Processing failed. Check the required models, services, and credentials, then retry.'
    job_service.update_job(job_id, state='error', message=message)
    with job_service.jobs_lock:
        job = job_service.jobs[job_id]
        details = {key: job[key] for key in ('timings', 'timing_stage', 'timing_stage_started_at', 'updated_at', 'steps_log', 'steps_elapsed') if key in job}
    job_service.save_json(job_service.JOBS_DIR / job_id / 'failure.json', {'message': message, **details})
