"""Editor media routes; extracted without changing media behavior."""
import json
import subprocess
import shutil
from functools import lru_cache
import tempfile
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask
from .storage import media, selected
from .render import export_binary
from .runtime import jobs_dir

@lru_cache(maxsize=128)
def thumbnail(jid, serialized, revision):
    clip = json.loads(serialized)
    with media(jid, clip) as source:
        try:
            result = subprocess.run(
                [export_binary(False), '-v', 'error', '-i', str(source),
                 '-frames:v', '1', '-vf', 'scale=640:-2',
                 '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'],
                capture_output=True, check=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise HTTPException(503, 'Could not generate clip thumbnail. Retry.')
    if not result.stdout:
        raise HTTPException(503, 'Clip thumbnail is unavailable. Retry.')
    return result.stdout


def get_thumbnail(pid: str, jid: str, index: int, request: Request):
    clip = selected(pid, jid, index, request.state.user_id)
    if clip.get('media_kind') == 'audio' or clip.get('clip_url', '').endswith('.mp3'):
        raise HTTPException(422, 'Audio-only clips do not have video thumbnails.')
    source = jobs_dir() / jid / Path(clip.get('clip_url', '')).name
    revision = (source.stat().st_mtime_ns, source.stat().st_size) if source.is_file() else None
    return Response(thumbnail(jid, json.dumps(clip, sort_keys=True), revision),
                    media_type='image/jpeg', headers={'Cache-Control': 'private, no-cache'})


def get_media(pid: str, jid: str, index: int, request: Request):
    clip = selected(pid, jid, index, request.state.user_id)
    # Copy cloud-backed temporary media before returning a streaming response.
    with media(jid, clip) as source:
        temp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        import shutil
        with temp:
            with source.open('rb') as stream:
                shutil.copyfileobj(stream, temp)
    return FileResponse(temp.name, media_type='audio/mpeg' if clip.get('media_kind') == 'audio' or clip.get('clip_url', '').endswith('.mp3') else 'video/mp4', background=BackgroundTask(Path(temp.name).unlink))
