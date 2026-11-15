"""Source durability off the generation critical path; no analysis/provider calls."""
from concurrent.futures import ThreadPoolExecutor
import logging

from backend.core import jobs, storage
from backend.services import projects_store

_workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix='source-backup')


def schedule(folder, job_id, owner):
    """The local source remains authoritative until the cloud backup succeeds.

    Capture the store and folder so a subsequent job cannot redirect writes.
    Persist pending/failed state; never report an uncompleted backup as durable.
    """
    if storage.uses_local_storage() or owner.get('source_s3_key'):
        return
    store = jobs.metadata_store()
    path = folder / 'owner.json'
    with projects_store.lock:
        current = store.read(path)
        current['source_backup_state'] = 'pending'
        store.write(path, current)

    def backup():
        fields = {'source_backup_state': 'failed'}
        try:
            uploaded = storage.upload_source_media(folder, job_id, dict(owner))
            if not uploaded.get('source_s3_key'):
                raise RuntimeError('Source backup did not return a durable source key')
            fields.update(uploaded)
            fields['source_backup_state'] = 'complete'
        except Exception:
            logging.getLogger(__name__).warning('Source backup failed for job %s; local source retained.', job_id)
        with projects_store.lock:
            # Deletion uses the same lock. A late backup must not recreate a deleted job.
            if folder.is_dir() and store.exists(path):
                current = store.read(path)
                current.update(fields)
                store.write(path, current)
        return fields

    try:
        return _workers.submit(backup)
    except RuntimeError:
        # Executor shutdown is not a successful backup.
        with projects_store.lock:
            current = store.read(path)
            current['source_backup_state'] = 'failed'
            store.write(path, current)
        return None
