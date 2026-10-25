"""Stored sessions and stable selection numbers, serialized by the project lock."""
import json
import logging
import time
from uuid import uuid4

from fastapi import HTTPException
from backend import integration as store


def save(project):
    store.host.save_json(store.project_dir(project['user_id']) / (project['id'] + '.json'), project)


def list_sessions(project):
    if 'sessions' not in project:
        project['sessions'] = [new_session('Session 1')]
        project['legacy_session_id'] = project['sessions'][0]['id']
        save(project)
    return project['sessions']


def new_session(name):
    return {'id': 's_' + uuid4().hex[:12], 'name': name, 'created_at': time.time(),
            'next_selection_number': 1, 'selections': []}


def require_session(project, sid=None):
    sessions = list_sessions(project)
    if sid is None:
        return sessions[0]
    for session in sessions:
        if session['id'] == sid:
            return session
    raise HTTPException(400, 'Session not found in this project.')


def create_session(project, name=None):
    sessions = list_sessions(project)
    session = new_session(name or f'Session {len(sessions) + 1}')
    sessions.append(session)
    save(project)
    return session


def rename_session(project, sid, name):
    session = require_session(project, sid)
    session['name'] = name
    save(project)
    return session


def job_session(project, owner):
    if owner.get('kind') == 'source':
        return None  # Sources belong to the project, independently of any session.
    # Legacy jobs retain the original first session even if newer sessions are added.
    return owner.get('session_id') or project.get('legacy_session_id') or list_sessions(project)[0]['id']


def delete_session(project, sid):
    session = require_session(project, sid)
    if len(list_sessions(project)) == 1:
        raise HTTPException(409, 'Cannot delete the last session.')
    jobs = [j for j in store.project_jobs(project['id'], project['user_id']) if j['session_id'] == sid]
    for job in jobs:
        folder = store.host.JOBS_DIR / job['job_id']
        with store.host.jobs_lock:
            state = store.host.jobs.get(job['job_id'], {}).get('state')
        if state in ('queued', 'processing'):
            raise HTTPException(409, 'A generation in this session is still running.')
    for job in jobs:
        path = store.host.JOBS_DIR / job['job_id'] / 'owner.json'
        owner = json.loads(path.read_text(encoding='utf-8'))
        owner['session_deleted'] = True
        store.host.save_json(path, owner)
    project.setdefault('legacy_session_id', list_sessions(project)[0]['id'])
    project['sessions'].remove(session)
    save(project)


def add_selection(project, sid, job_id, clip_index):
    session = require_session(project, sid)
    owner, clip = store.selected_clip(project['id'], store.ClipInput(job_id=job_id, clip_index=clip_index), project['user_id'])
    if owner.get('kind', 'generation') != 'generation' or job_session(project, owner) != sid:
        raise HTTPException(400, 'Clip must belong to this session.')
    for selection in session['selections']:
        if (selection['job_id'], selection['clip_index']) == (job_id, clip_index):
            return selection, False
    selection = {'number': session['next_selection_number'], 'job_id': job_id,
                 'clip_index': clip_index, 'selected_at': time.time()}
    session['selections'].append(selection)
    session['next_selection_number'] += 1
    save(project)
    return selection, True


def remove_selection(project, sid, number):
    session = require_session(project, sid)
    matches = [s for s in session['selections'] if s['number'] == number]
    if not matches:
        raise HTTPException(404, 'Selection not found.')
    session['selections'].remove(matches[0])
    save(project)


def list_selections(project, sid=None):
    sessions = [require_session(project, sid)] if sid is not None else list_sessions(project)
    result = []
    for session in sessions:
        for selection in session['selections']:
            try:
                owner, clip = store.selected_clip(project['id'], store.ClipInput(
                    job_id=selection['job_id'], clip_index=selection['clip_index']), project['user_id'])
                if job_session(project, owner) != session['id']:
                    continue
            except HTTPException:
                logging.getLogger(__name__).warning('Skipping unavailable selection %s in session %s', selection['number'], session['id'])
                continue
            result.append({**store.host.public_clip(clip), **selection,
                           'session_id': session['id'], 'session_name': session['name']})
    return result
