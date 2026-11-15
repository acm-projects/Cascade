"""The user's editing style, learned in the background from reference reels for the AI Editor chat.

References come from reel links pasted into the chat message, else from the folder named by
`CASCADE_STYLE_REFERENCES` (e.g. ~/Desktop/AI Video Editor/Reference). A profile is built once per
set of references and cached per user under `video_jobs/projects/<user hash>/styles/<id>.json`;
adding, removing or replacing a reference builds a new one on the next edit.
"""
import hashlib
import json
import logging
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import HTTPException

from backend.broll import write_json
from backend.services.projects_store import project_dir
from .style_profile_models import StyleProfile

LOG = logging.getLogger(__name__)
MAX_REFERENCES = 8
VIDEO_TYPES = ('.mp4', '.mov', '.m4v', '.webm')


def folder(user):
    return project_dir(user)/'styles'


def save(user, profile):
    write_json(folder(user)/(profile.id+'.json'), profile.model_dump())
    return profile


def saved(user):
    profiles = []
    for path in folder(user).glob('*.json'):
        try:
            profiles.append(StyleProfile.model_validate(json.loads(path.read_text())))
        except (OSError, ValueError):
            continue
    return sorted(profiles, key=lambda p: -p.created)


def chat_links(message):
    from .style_reference import LINK
    return list(dict.fromkeys(u.rstrip('.,;)') for u in re.findall(r'https://\S+', message) if LINK.match(u.rstrip('.,;)'))))[:MAX_REFERENCES]


def folder_references():
    configured = os.environ.get('CASCADE_STYLE_REFERENCES', '').strip()
    if not configured: return []
    root = Path(configured).expanduser()
    files = [p for p in root.glob('*') if p.is_file() and p.suffix.lower() in VIDEO_TYPES] if root.is_dir() else []
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:MAX_REFERENCES]


def build(user, paths=(), links=(), source_key=''):
    """Measure every reference and choose the style; returns a saved StyleProfile."""
    from .style_reference import choose, download, measure
    refs, frames, skipped = [], [], []
    with tempfile.TemporaryDirectory(prefix='cascade-style-') as work:
        sources = [(Path(p), Path(p).name) for p in paths]
        for n, url in enumerate(links):
            place = Path(work)/f'link{n}'; place.mkdir()
            try:
                sources.append((download(url, place), url))
            except HTTPException as exc:
                skipped.append(exc.detail)
        for path, label in sources:
            try:
                info, sampled = measure(path, label)
            except HTTPException as exc:
                skipped.append(exc.detail); continue
            refs.append(info); frames += sampled[:max(2, 16//max(1, len(sources)))]
    if not refs:
        raise HTTPException(422, 'None of your reference reels could be read. '+' '.join(skipped)[:400])
    choices, chosen_by = choose(refs, frames)
    choices.summary = [line[:200] for line in choices.summary][:12]
    if skipped:
        choices.summary.append(('Skipped: '+'; '.join(skipped))[:200])
    return save(user, StyleProfile(id=uuid.uuid4().hex, status='approved', created=time.time(), chosen_by=chosen_by,
                                   source_key=source_key, references=refs, choices=choices))


def for_chat(user, message):
    """(StyleProfile or None, report line). Links in the message win over the references folder;
    without either, the most recent learned style is reused."""
    links = chat_links(message)
    paths = [] if links else folder_references()
    if links:
        key = 'links:'+hashlib.sha256('\n'.join(sorted(links)).encode()).hexdigest()[:24]
    elif paths:
        key = 'folder:'+hashlib.sha256(json.dumps([(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in paths]).encode()).hexdigest()[:24]
    else:
        latest = next(iter(saved(user)), None)
        return latest, (f'Style: your saved "{latest.choices.name}" style.' if latest else '')
    cached = next((p for p in saved(user) if p.source_key == key), None)
    if cached:
        return cached, f'Style: "{cached.choices.name}", learned from your {len(cached.references)} reference reel(s).'
    started = time.time()
    try:
        profile = build(user, paths, links, key)
    except HTTPException as exc:
        LOG.warning('style learning failed: %s', exc.detail)
        return None, f'Could not learn your style ({exc.detail}); edited without it.'
    return profile, (f'Style: learned "{profile.choices.name}" from {len(profile.references)} reference reel(s) in {time.time()-started:.0f}s '
                     f'via {profile.chosen_by}; reused on later edits.')
