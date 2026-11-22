"""Editor media routes; extracted without changing media behavior."""
import json
import subprocess
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
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


def style_progress(pid: str, jid: str, index: int, request: Request):
    """Subject-cutout progress for a stylized preview: {'done', 'total'} or {} when idle."""
    from .segmentation import PROGRESS
    clip = selected(pid, jid, index, request.state.user_id)
    done, total = PROGRESS.get(str(jobs_dir()/jid/Path(clip.get('clip_url', '')).name), (None, None))
    return {} if total is None else {'done': done, 'total': total}


def get_media(pid: str, jid: str, index: int, request: Request):
    """The clip, streamed: the browser asks for byte ranges as it plays or seeks, so a long video is never
    loaded (or copied) whole."""
    clip = selected(pid, jid, index, request.state.user_id)
    name = Path(clip.get('clip_url', '')).name
    kind = 'audio/mpeg' if clip.get('media_kind') == 'audio' or name.endswith('.mp3') else 'video/mp4'
    local = jobs_dir() / jid / name
    if name and local.is_file():
        return FileResponse(local, media_type=kind)
    if clip.get('clip_s3_key') and clip.get('s3_bucket'):
        from backend.core.storage import stream_s3
        return stream_s3(clip['s3_bucket'], clip['clip_s3_key'], kind, request.headers.get('range'))
    raise HTTPException(404, 'Clip media is missing.')
