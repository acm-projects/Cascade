"""Editor previews that stream instead of downloading whole.

POST .../{jid}/{index}/preview renders the edit exactly as POST .../export does, but keeps the file on the server
and answers with its address. The browser then plays that address through a signed media link
(GET /api/media-link), asking for byte ranges as it plays, so playback starts once the first part arrives
instead of after the whole file has downloaded. Only the newest KEEP renders per clip are kept.
"""
import re
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from .models import ExportInput
from .render import export
from .runtime import jobs_dir
from .storage import selected

KEEP = 6   # recent renders per clip: enough for a few quick edits (and undo) while one is still playing
NAME = re.compile(r'^[0-9a-f]{32}\.(mp4|mp3)$')


def _folder(jid, index):
    return jobs_dir()/jid/'previews'/str(index)


def _prune(folder):
    renders = sorted(folder.glob('*.mp[34]'), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in renders[KEEP:]:
        old.unlink(missing_ok=True)


def render_preview(pid: str, jid: str, index: int, body: ExportInput, request: Request):
    """Render the edit and keep it: {"path": where to stream it from, "media_type"}."""
    response = export(pid, jid, index, body, request)
    try:
        source = Path(response.path)
        folder = _folder(jid, index)
        folder.mkdir(parents=True, exist_ok=True)
        name = f'{uuid.uuid4().hex}{source.suffix if source.suffix in (".mp4", ".mp3") else ".mp4"}'
        staged = folder/(name+'.tmp')
        shutil.copyfile(source, staged)
        staged.replace(folder/name)
    finally:
        if response.background:
            response.background.func(*response.background.args, **response.background.kwargs)
    _prune(folder)
    return {'path': f'/api/projects/{pid}/editor/{jid}/{index}/preview/{name}', 'media_type': response.media_type}


def get_preview(pid: str, jid: str, index: int, name: str, request: Request):
    """A kept preview render, streamed in byte ranges."""
    selected(pid, jid, index, request.state.user_id)   # the clip must be this user's
    if not NAME.match(name):
        raise HTTPException(404, 'Preview not found.')
    path = _folder(jid, index)/name
    if not path.is_file():
        raise HTTPException(404, 'This preview has expired. Make any edit to render it again.')
    return FileResponse(path, media_type='audio/mpeg' if name.endswith('.mp3') else 'video/mp4')
