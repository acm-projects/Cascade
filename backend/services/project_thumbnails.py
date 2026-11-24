"""The picture on each Projects page card, made once instead of on every visit.

When a job finishes making clips (AI Studio, an uploaded clip, combined clips), `save` grabs the first frame of its
first video clip, shrinks it to WIDTH pixels and saves it as a small WebP next to the clips (a few KB). The project's
`thumbnail_key` then points at it, so the project list can hand the page a link for each card and the browser can
cache the picture (GET /api/projects/{id}/thumbnail/{name}). Before this, every visit had FFmpeg rebuild each
thumbnail, sometimes after downloading a whole clip from S3, two requests per card, with nothing cached.

With S3 storage the picture is also uploaded there, so it survives the server's disk being cleared.
Projects made before this get theirs in the background the first time the list is opened (`backfill`).
"""
import io
import logging
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import FileResponse

from backend.core import jobs as job_service, storage as storage_service
from backend.services import projects_store

LOG = logging.getLogger(__name__)
WIDTH = 320          # twice the card's thumbnail width on most screens: sharp, and still only a few KB
QUALITY = 72
CACHE = 'private, max-age=172800, immutable'   # the address changes whenever the picture does
_tried = set()       # projects whose missing picture we already tried to make since the server started
_tried_lock = threading.Lock()


def _is_video(clip):
    return clip.get('media_kind') != 'audio' and not clip.get('clip_url', '').endswith('.mp3') and clip.get('has_video', True)


def _frame(source):
    """The clip's first frame as a WebP (FFmpeg reads the frame; Pillow writes WebP, which every FFmpeg build can't)."""
    from PIL import Image
    from backend.video_tools import ffmpeg
    result = subprocess.run([ffmpeg(), '-nostdin', '-v', 'error', '-i', str(source), '-frames:v', '1',
                             '-vf', f"scale='min({WIDTH},iw)':-2", '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'],
                            capture_output=True, check=True, timeout=30)
    if not result.stdout:
        raise ValueError('no frame')
    out = io.BytesIO()
    Image.open(io.BytesIO(result.stdout)).convert('RGB').save(out, 'WEBP', quality=QUALITY, method=4)
    return out.getvalue()


def save(job_id, clips=None):
    """Make the project's card picture from this finished job. Never raises: a missing picture only shows the leaf."""
    try:
        folder = job_service.JOBS_DIR/job_id
        owner = job_service.load_json(folder/'owner.json')
        if clips is None:
            clips = job_service.load_json(folder/'results.json').get('clips', [])
        clip = next((c for c in clips if isinstance(c, dict) and _is_video(c)), None)
        source = folder/Path(clip.get('clip_url', '')).name if clip else None
        if not source or not source.is_file() or not owner.get('project_id'):
            return None
        name = f'thumbnail-{uuid4().hex[:16]}.webp'
        (folder/name).write_bytes(_frame(source))
        changes = {'thumbnail_key': f'{job_id}/{name}', 'thumbnail_s3': None}
        if not storage_service.uses_local_storage():
            try:
                folder_name = storage_service.safe_folder_name(owner.get('user_folder')) or storage_service.DEFAULT_FOLDER
                key = f"{folder_name}/{owner['user_id']}/jobs/{job_id}/{name}"
                bucket = storage_service.s3_bucket()
                storage_service.s3_client().upload_file(str(folder/name), bucket, key, ExtraArgs={'ContentType': 'image/webp'})
                changes['thumbnail_s3'] = {'bucket': bucket, 'key': key}
            except Exception:
                LOG.warning('Could not back up the thumbnail for job %s to S3', job_id, exc_info=True)
        with projects_store.lock:
            path = projects_store.project_dir(owner['user_id'])/(owner['project_id']+'.json')
            if not job_service.metadata_exists(path):
                return None
            old = job_service.load_json(path).get('thumbnail_key')
            job_service.metadata_store().update_project(path, owner['user_id'], changes)
        if old and old != changes['thumbnail_key']:
            (job_service.JOBS_DIR/old).unlink(missing_ok=True)
        return changes['thumbnail_key']
    except Exception:
        LOG.warning('Could not make the project thumbnail for job %s', job_id, exc_info=True)
        return None


def link(project, user_id):
    """The picture's address for the page, or None. It stays the same for a day, so the browser keeps the picture."""
    key = project.get('thumbnail_key')
    if not key:
        return None
    from backend.core.media_links import cacheable_link
    return cacheable_link(f"/api/projects/{project['id']}/thumbnail/{Path(key).name}", user_id)


def with_link(project, user_id):
    return {**project, 'thumbnail_url': link(project, user_id)}


def serve(project_id, name, user_id):
    """GET /api/projects/{id}/thumbnail/{name}: the card picture, from this disk or else S3."""
    project = projects_store.require_project(project_id, user_id)
    key = project.get('thumbnail_key') or ''
    if not key or Path(key).name != name:
        raise HTTPException(404, 'Thumbnail not found.')
    local = job_service.JOBS_DIR/key
    if local.is_file():
        return FileResponse(local, media_type='image/webp', headers={'Cache-Control': CACHE})
    s3 = project.get('thumbnail_s3') or {}
    if s3.get('bucket') and s3.get('key'):
        response = storage_service.stream_s3(s3['bucket'], s3['key'], 'image/webp', None)
        response.headers['Cache-Control'] = CACHE
        return response
    raise HTTPException(404, 'Thumbnail not found.')


def _newest_clips(project_id, user_id):
    """Make the picture from the project's newest finished job that has a video clip."""
    for job in projects_store.project_jobs(project_id, user_id):
        results = job_service.JOBS_DIR/job['job_id']/'results.json'
        if job_service.metadata_exists(results):
            clips = job_service.load_json(results).get('clips', [])
            if any(isinstance(c, dict) and _is_video(c) for c in clips) and save(job['job_id'], clips):
                return


def backfill(projects, user_id):
    """Projects from before thumbnails were saved: make theirs in the background (once per server start)."""
    with _tried_lock:
        missing = [p['id'] for p in projects if not p.get('thumbnail_key') and p['id'] not in _tried]
        _tried.update(missing)
    if missing:
        threading.Thread(target=lambda: [_newest_clips(pid, user_id) for pid in missing],
                         name='thumbnail-backfill', daemon=True).start()
