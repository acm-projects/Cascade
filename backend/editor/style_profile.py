"""My Style: the user's saved editing styles, built from reference reels they upload or link.

Profiles live per user under `video_jobs/projects/<user hash>/styles/<id>.json` and are shared by
all of that user's projects. A new profile is a draft; the AI Director only uses approved ones.
"""
import json
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import File, Form, HTTPException, Request, UploadFile

from backend.broll import write_json
from backend.services.projects_store import project_dir, require_project
from .style_profile_models import ProfileUpdate, StyleProfile

MAX_REFERENCES = 8
MAX_UPLOAD = 200*1024*1024
VIDEO_TYPES = ('.mp4', '.mov', '.m4v', '.webm')


def folder(user):
    return project_dir(user)/'styles'


def load(user, sid):
    if not sid or len(sid) != 32 or any(c not in '0123456789abcdef' for c in sid):
        raise HTTPException(404, 'Style not found.')
    try:
        return StyleProfile.model_validate_json((folder(user)/(sid+'.json')).read_text())
    except (OSError, ValueError):
        raise HTTPException(404, 'Style not found.') from None


def approved(user, sid):
    profile = load(user, sid)
    if profile.status != 'approved':
        raise HTTPException(409, 'Approve this style sheet before editing with it.')
    return profile


def save(user, profile):
    write_json(folder(user)/(profile.id+'.json'), profile.model_dump())
    return profile


def _store_upload(upload, target):
    size = 0
    with target.open('wb') as out:
        while chunk := upload.file.read(1024*1024):
            size += len(chunk)
            if size > MAX_UPLOAD: raise HTTPException(413, 'Each reference video must be at most 200 MB.')
            out.write(chunk)


def build(user, uploads, links):
    """Measure every reference and choose the style; returns a draft StyleProfile."""
    from .style_reference import choose, download, measure
    if not uploads and not links:
        raise HTTPException(422, 'Add at least one reference video or link.')
    if len(uploads)+len(links) > MAX_REFERENCES:
        raise HTTPException(422, f'Use at most {MAX_REFERENCES} reference videos.')
    refs, frames, skipped = [], [], []
    with tempfile.TemporaryDirectory(prefix='cascade-style-') as work:
        sources = []
        for n, upload in enumerate(uploads):
            name = Path(upload.filename or f'reference {n+1}').name
            if Path(name).suffix.lower() not in VIDEO_TYPES:
                raise HTTPException(422, f'{name}: upload MP4, MOV, M4V or WebM videos.')
            target = Path(work)/f'upload{n}{Path(name).suffix.lower()}'
            _store_upload(upload, target)
            sources.append((target, name))
        for n, url in enumerate(links):
            place = Path(work)/f'link{n}'; place.mkdir()
            try:
                sources.append((download(url.strip(), place), url.strip()))
            except HTTPException as exc:
                skipped.append(exc.detail)
        for path, label in sources:
            try:
                info, sampled = measure(path, label)
            except HTTPException as exc:
                skipped.append(exc.detail); continue
            refs.append(info); frames += sampled[:max(2, 16//max(1, len(sources)))]
    if not refs:
        raise HTTPException(422, 'No reference could be read. '+' '.join(skipped)[:400])
    choices, chosen_by = choose(refs, frames)
    choices.summary = [line[:200] for line in choices.summary][:12]
    if skipped:
        choices.summary.append(('Skipped: '+'; '.join(skipped))[:200])
    return save(user, StyleProfile(id=uuid.uuid4().hex, created=time.time(), chosen_by=chosen_by, references=refs, choices=choices))


# ---------------------------------------------------------------- routes

def create_style(pid: str, request: Request, videos: list[UploadFile] = File(default=[]), links: str = Form('', max_length=4000)):
    user = request.state.user_id
    require_project(pid, user)
    urls = [u.strip() for u in links.replace(',', '\n').splitlines() if u.strip()]
    return build(user, videos, urls)


def list_styles(pid: str, request: Request):
    user = request.state.user_id
    require_project(pid, user)
    profiles = []
    for path in folder(user).glob('*.json'):
        try:
            profiles.append(StyleProfile.model_validate(json.loads(path.read_text())))
        except (OSError, ValueError):
            continue
    return {'styles': sorted(profiles, key=lambda p: -p.created)}


def update_style(pid: str, sid: str, body: ProfileUpdate, request: Request):
    user = request.state.user_id
    require_project(pid, user)
    profile = load(user, sid)
    profile.choices = body.choices
    if body.approve: profile.status = 'approved'
    return save(user, profile)


def delete_style(pid: str, sid: str, request: Request):
    user = request.state.user_id
    require_project(pid, user)
    load(user, sid)
    (folder(user)/(sid+'.json')).unlink(missing_ok=True)
    return {'deleted': sid}
