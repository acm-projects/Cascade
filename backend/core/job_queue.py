"""A small durable job queue: generation and feature jobs survive a server restart.

Jobs run on `jobs.worker` (a few at once, one per person: job_slots.py), and each one is first written to video_jobs/queue/<job_id>.json
(what to run and with what), and that file is removed only when the job finishes. On startup, `resume()` puts every
file still there back in line: jobs that were waiting, and jobs a restart cut off (they start again from the
beginning; their transcripts, frame embeddings and clip backups are cached, so the repeat is quick). Before this,
a restart lost them and the status page said "Upload the video again".

Single server, local disk: no extra service (Redis, Celery) to run. The tasks are named here, not pickled, so a
queue file is plain JSON and can never run arbitrary code.
"""
import importlib
import json
import logging
import time
from pathlib import Path

from backend.core import jobs

LOG = logging.getLogger(__name__)
TASKS = {   # name -> "module:function"; the function takes (job_id, *args)
    'generate': 'backend.routers.clips:process_upload',
    'search': 'backend.services.features:process_search',
    'caption_styles': 'backend.services.features:render_styles',
    'research': 'backend.services.features:research',
}


def _encode(value):
    return {'$path': str(value)} if isinstance(value, Path) else value


def _decode(value):
    return Path(value['$path']) if isinstance(value, dict) and set(value) == {'$path'} else value


def _queue():
    return jobs.JOBS_DIR/'queue'   # read each time, so tests (and a moved jobs folder) are respected


def _file(job_id):
    return _queue()/f'{job_id}.json'


def _user(job_id):
    """Whose job this is, so the worker can share its slots fairly between people."""
    try:
        return jobs.load_json(jobs.JOBS_DIR/job_id/'owner.json').get('user_id')
    except Exception:
        return None


def submit(task, job_id, *args):
    """Run `task` for `job_id` in the background, and keep it queued across restarts until it finishes."""
    if task not in TASKS:
        raise ValueError(f'Unknown task {task}')
    _queue().mkdir(parents=True, exist_ok=True)
    record = {'task': task, 'job_id': job_id, 'user_id': _user(job_id), 'args': [_encode(a) for a in args],
              'queued_at': time.time()}
    temporary = _file(job_id).with_suffix('.tmp')
    temporary.write_text(json.dumps(record))
    temporary.replace(_file(job_id))
    return jobs.worker.submit(_run, record)


def _run(record):
    module, name = TASKS[record['task']].split(':')
    try:
        args = [_decode(a) for a in record['args']]
        for value in args:   # a source video that only survives in S3 (item 12) comes back before the job starts
            if isinstance(value, Path) and value.name == 'source.video' and not value.is_file():
                from backend.services.projects_store import local_source
                local_source(value.parent.name)
        getattr(importlib.import_module(module), name)(record['job_id'], *args)
    finally:
        _file(record['job_id']).unlink(missing_ok=True)   # done, failed or cancelled: either way it is no longer queued


def _finished(job_id):
    """Already done or failed (read through the metadata store, which may be the database rather than files)."""
    folder = jobs.JOBS_DIR/job_id
    try:
        if jobs.metadata_exists(folder/'progress.json'):
            return jobs.load_json(folder/'progress.json').get('state') in ('done', 'error')
        return jobs.metadata_exists(folder/'results.json')
    except Exception:
        return False


def resume():
    """Startup: put back in line every job a restart left queued or half done (oldest first)."""
    queue = _queue()
    if not queue.is_dir():
        return []
    resumed = []
    for path in sorted(queue.glob('*.json'), key=lambda p: p.stat().st_mtime):
        try:
            record = json.loads(path.read_text())
            job_id = record['job_id']
            if record.get('task') not in TASKS or not (jobs.JOBS_DIR/job_id).is_dir() or _finished(job_id):
                path.unlink(missing_ok=True)   # deleted, already finished, or not ours
                continue
            with jobs.jobs_lock:
                jobs.jobs[job_id] = {'state': 'queued', 'message': 'Resuming after a server restart…', 'clips': []}
            jobs.worker.submit(_run, {**record, 'user_id': record.get('user_id') or _user(job_id)})
            resumed.append(job_id)
        except Exception:
            LOG.warning('Could not resume queued job %s', path.name, exc_info=True)
    if resumed:
        LOG.warning('Resumed %d queued job(s) after a restart: %s', len(resumed), ', '.join(resumed))
    return resumed
