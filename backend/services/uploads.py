"""Shared streaming upload persistence for source uploads and legacy generation."""
import hashlib
import shutil
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from backend import integration as store


def save_uploaded_source(file, owner, job_id=None):
    """Persist the existing upload contract: nonempty bytes, SHA-256, private owner.

    Media contents are validated by inspect_video in the worker. The legacy route
    has no extension or upload-size restriction; keep that behavior here.
    """
    job_id = job_id or uuid4().hex
    folder = store.host.JOBS_DIR / job_id
    folder.mkdir()
    try:
        fingerprint = hashlib.sha256()
        with (folder / 'source.video').open('wb') as destination:
            while chunk := file.file.read(1024 * 1024):
                fingerprint.update(chunk)
                destination.write(chunk)
        if (folder / 'source.video').stat().st_size == 0:
            raise HTTPException(400, 'The uploaded file is empty.')
        store.host.save_json(folder / 'owner.json', {
            **owner, 'source_name': owner.get('source_name', Path(file.filename or 'video').name),
            'video_sha256': fingerprint.hexdigest(),
        })
    except Exception:
        shutil.rmtree(folder)
        raise
    finally:
        file.file.close()
    return job_id
