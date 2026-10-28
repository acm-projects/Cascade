"""Editor drafts; extracted without changing media behavior."""
from fastapi import HTTPException, Request
from .models import Captions, Draft, Edit
from .validation import details, validate_edit
from .storage import draft_path, selected, stock_store
from .reframe import read_analysis
from .runtime import jobs_dir, load_json, save_json, metadata_exists, public_clip
from backend.integration import project_dir, require_project, project_jobs, lock

def editor_index(pid: str, request: Request, selected_only: bool = False):
    project = require_project(pid, request.state.user_id)
    jobs = list(reversed(project_jobs(pid, request.state.user_id)))
    by_id = {j['job_id']: j for j in jobs}
    groups = {}
    for job in jobs:
        if job['kind'] == 'research':
            continue
        root = job
        visited = set()
        while root['kind'] == 'caption-styles' and root['job_id'] not in visited:
            visited.add(root['job_id'])
            owner = load_json(jobs_dir() / root['job_id'] / 'owner.json')
            parent = by_id.get(owner.get('parent_job'))
            if not parent:
                break
            root = parent
        group = groups.setdefault(root['job_id'], {**root, 'clips': []})
        path = jobs_dir() / job['job_id'] / 'results.json'
        if metadata_exists(path):
            clips = load_json(path).get('clips', [])
            group['clips'].extend({**public_clip(c), 'job_id': job['job_id'], 'clip_index': i} for i, c in enumerate(clips))
    from backend.editor_navigation import label_waves
    sessions = [group for group in groups.values() if group['clips']]
    studio = project.get('studio', {})
    chosen = studio.get('editor_clips', [])
    allowed = {(r['job_id'], r['clip_index']) for r in chosen}
    for group in sessions:
        match = next((s for s in studio.get('sessions', []) if group['job_id'] in s['job_ids']), None)
        if match:
            group['session_name'] = match['name']
            group['session_id'] = match['id']
        if selected_only:
            group['clips'] = [c for c in group['clips'] if (c['job_id'], c['clip_index']) in allowed]
    sessions = label_waves(sessions)
    sessions = [group for group in sessions if group['clips']]
    selection = chosen[0] if selected_only and chosen else project.get('editor_selection')
    return {'sessions': sessions, 'selection': selection}


def get_draft(pid: str, jid: str, index: int, request: Request):
    clip = selected(pid, jid, index, request.state.user_id)
    info = details(jid, clip)
    path = draft_path(pid, jid, index, request.state.user_id)
    draft = None
    if metadata_exists(path):
        try:
            draft = Draft.model_validate(load_json(path))
            validate_edit(draft.state, info['duration'])
        except (ValueError, HTTPException):
            info['warning'] += ' Outdated saved edits were reset.'
            draft = None
    if draft is None:
        draft = Draft(state=Edit(start=0, end=info['duration'], captions=Captions(enabled=not info['burned_in'])))
    return {**info, 'draft': draft.model_dump()}


def save_draft(pid: str, jid: str, index: int, body: Draft, request: Request):
    clip = selected(pid, jid, index, request.state.user_id)
    validate_edit(body.state, details(jid, clip)['duration'])
    stock_store(pid,jid,index,request.state.user_id).verify(body.state)
    if body.state.reframe.enabled:read_analysis(pid,jid,index,body.state.reframe.analysis_id,request.state.user_id)
    with lock:
        path = draft_path(pid, jid, index, request.state.user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        save_json(path, body.model_dump())
        project = require_project(pid, request.state.user_id)
        project['editor_selection'] = {'job_id': jid, 'clip_index': index}
        save_json(project_dir(request.state.user_id) / (pid + '.json'), project)
    return {'saved': True}


def save_clip(pid: str, jid: str, index: int, request: Request):
    selected(pid, jid, index, request.state.user_id)
    with lock:
        project = require_project(pid, request.state.user_id)
        entry = {'job_id': jid, 'clip_index': index}
        if entry not in project['saved_clips']:
            project['saved_clips'].append(entry)
            save_json(project_dir(request.state.user_id) / (pid + '.json'), project)
    return {'saved': True}
