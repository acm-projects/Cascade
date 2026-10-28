"""Editor storage; extracted without changing media behavior."""
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from fastapi import HTTPException
from backend import broll as stocklib
from .runtime import jobs_dir, metadata_exists, s3_client
from backend.integration import project_dir, selected_clip

def selected(pid, jid, index, user):
    if index < 0:
        raise HTTPException(404, 'Clip not found.')
    from types import SimpleNamespace
    return selected_clip(pid, SimpleNamespace(job_id=jid, clip_index=index), user)[1]


@contextmanager
def media(jid, clip, captions=False):
    field = 'captions_url' if captions else 'clip_url'
    name = Path(clip.get(field, '')).name
    if not re.fullmatch(r'clip_[1-9][0-9]*\.(mp4|vtt)', name):
        raise HTTPException(404, 'Clip media is unavailable.')
    path = jobs_dir() / jid / name
    if metadata_exists(path):
        yield path
        return
    key = clip.get('captions_s3_key' if captions else 'clip_s3_key')
    if not key:
        raise HTTPException(404, 'Clip media is missing.')
    with tempfile.TemporaryDirectory(prefix='cascade-editor-') as directory:
        path = Path(directory) / name
        try:
            s3_client().download_file(clip['s3_bucket'], key, str(path))
        except Exception:
            raise HTTPException(503, 'Could not retrieve clip media. Retry.')
        yield path


def draft_path(pid, jid, index, user):
    return project_dir(user) / 'editor' / pid / (jid + '-' + str(index) + '.json')


def stock_store(pid, jid, index, user):
    return stocklib.Store(draft_path(pid,jid,index,user).parent/'stock'/(jid+'-'+str(index)))
