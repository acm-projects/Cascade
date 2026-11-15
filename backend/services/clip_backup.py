"""Bounded cloud uploads after clips are locally playable and results are saved."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import time
import threading
from uuid import uuid4

from backend.core import jobs, storage
from backend.services import projects_store

_batches = ThreadPoolExecutor(max_workers=2, thread_name_prefix='clip-backup-batch')
_uploads = ThreadPoolExecutor(max_workers=3, thread_name_prefix='clip-upload')
_active = {}


def schedule(folder, job_id):
    """Back up pending/failed clips without blocking local playback.

    The result record is the durable retry manifest. Local files are never
    removed. A failed upload leaves the generation successful and marks the
    backup failed. A new batch token protects retried/deleted generations.
    """
    if storage.uses_local_storage():
        return None
    store = jobs.metadata_store()
    path, owner_path = folder/'results.json', folder/'owner.json'
    key = str(path.resolve())
    with projects_store.lock:
        running = _active.get(key)
        if running is not None and not running.done():
            return running
        payload, owner = store.read(path), store.read(owner_path)
        if owner.get('project_deleted'):
            return None
        clips = [dict(clip) for clip in payload.get('clips', [])]
        pending = [i for i, clip in enumerate(clips) if not (clip.get('clip_s3_key') and clip.get('captions_s3_key'))]
        if not pending:
            return None
        token = uuid4().hex
        for i in pending:
            clips[i]['backup_state'] = 'pending'
        payload.update(clips=clips, backup_state='pending', backup_batch_id=token)
        store.write(path, payload)
        with jobs.jobs_lock:
            instance = jobs.jobs.get(job_id)
            if instance is not None:
                instance.update(backup_state='pending', backup_batch_id=token)

        def upload(i):
            started = time.perf_counter()
            suffix = '.mp3' if clips[i].get('media_kind') == 'audio' else '.mp4'
            try:
                fields = storage.upload_clip_files(folder, job_id, f'clip_{i+1}{suffix}', f'clip_{i+1}.vtt', owner=owner)
                if not fields.get('clip_s3_key') or not fields.get('captions_s3_key'):
                    raise RuntimeError('Upload did not return durable clip and caption keys')
                return i, {**fields, 'storage': 's3', 'backup_state': 'complete',
                           'upload_seconds': round(time.perf_counter() - started, 3)}
            except Exception:
                logging.getLogger(__name__).warning('Clip %s backup failed for job %s; local files retained.', i+1, job_id)
                return i, {'backup_state': 'failed', 'upload_seconds': round(time.perf_counter() - started, 3)}

        def run():
            started = time.perf_counter()
            completed = {}
            futures = {}
            for i in pending:
                try:
                    futures[_uploads.submit(upload, i)] = i
                except RuntimeError:
                    completed[i] = {'backup_state': 'failed'}
            for future in as_completed(futures):
                try:
                    i, fields = future.result()
                except Exception:
                    i, fields = futures[future], {'backup_state': 'failed'}
                completed[i] = fields
            elapsed = round(time.perf_counter() - started, 3)
            with projects_store.lock:
                # Do not resurrect a deleted job or write into a newer retry.
                if not folder.is_dir():
                    return
                try:
                    current, current_owner = store.read(path), store.read(owner_path)
                except FileNotFoundError:
                    return
                if current_owner.get('project_deleted') or current.get('backup_batch_id') != token:
                    return
                for i, fields in completed.items():
                    current['clips'][i].update(fields)
                state = 'failed' if any(c.get('backup_state') == 'failed' for c in current['clips']) else 'complete'
                current.update(backup_state=state, cloud_backup_seconds=elapsed)
                store.write(path, current)
                with jobs.jobs_lock:
                    live = jobs.jobs.get(job_id)
                    if live is instance and live is not None and live.get('backup_batch_id') == token:
                        live.update(backup_state=state, cloud_backup_seconds=elapsed,
                                    clips=[storage.public_clip(c) for c in current['clips']])
            return current

        try:
            future = _batches.submit(run)
        except RuntimeError:
            payload['backup_state'] = 'failed'
            for i in pending:
                payload['clips'][i]['backup_state'] = 'failed'
            store.write(path, payload)
            with jobs.jobs_lock:
                live = jobs.jobs.get(job_id)
                if live is instance and live is not None:
                    live.update(backup_state='failed', clips=[storage.public_clip(c) for c in payload['clips']])
            raise
        _active[key] = future
        # Entries are bounded to active work, not every historical generation.
        def forget(done):
            with projects_store.lock:
                if _active.get(key) is done:
                    _active.pop(key, None)
        future.add_done_callback(forget)
        return future


def resume_pending():
    """Restart interrupted backups from saved manifests, without rerunning AI."""
    if storage.uses_local_storage():
        return
    def recover():
        try:
            for path, payload in jobs.metadata_documents('*/results.json'):
                if payload.get('backup_state') == 'pending' and path.parent.is_dir():
                    try:
                        schedule(path.parent, path.parent.name)
                    except Exception:
                        logging.getLogger(__name__).warning('Could not resume clip backup for job %s.', path.parent.name)
        except Exception:
            logging.getLogger(__name__).warning('Could not scan pending clip backups; saved manifests retained.')
    threading.Thread(target=recover, name='backup-recovery', daemon=True).start()
