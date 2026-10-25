"""Background grading jobs and opt-in generation completion hook."""
import json
import logging
import os
from fastapi import HTTPException
from backend import integration as store
from backend.research import QuotaBudgetExceeded, ResearchConfigError
from backend.research import grader

logger = logging.getLogger(__name__)


def _run(feature_id, pid, jid, index, user_id, spec=None):
    host = store.host
    try:
        host.update_job(feature_id, state='processing', message='Preparing clip grading…')
        progress = lambda message: host.update_job(feature_id, message=message)
        if index is None:
            grades = grader.grade_wave(pid, jid, user_id=user_id, progress=progress)
            store.finish_feature(feature_id, {'grades': [g.model_dump() for g in grades],
                'best_clip_index': max(range(len(grades)), key=lambda i: grades[i].score) if grades else None})
        else:
            grade = grader.grade_clip(pid, jid, index, spec['use_edits'], user_id=user_id, spec=spec, progress=progress)
            store.finish_feature(feature_id, {'grade': grade.model_dump()})
    except Exception as error:
        logger.exception('Research grading job %s failed', feature_id)
        message = str(error) if isinstance(error, (QuotaBudgetExceeded, ResearchConfigError)) else host.processing_error(error, 'grading the clip')
        store.fail_feature(feature_id, message)


def _enqueue(owner, pid, jid, index, user_id, spec=None):
    kind = 'wave-grade' if index is None else 'clip-grade'
    identity = spec['cache_key'] if spec else jid
    for path in store.host.JOBS_DIR.glob('*/owner.json'):
        record = json.loads(path.read_text(encoding='utf-8'))
        if (record.get('user_id') == user_id and record.get('project_id') == pid and record.get('kind') == kind
                and record.get('grading_identity') == identity):
            with store.host.jobs_lock:
                if store.host.jobs.get(path.parent.name, {}).get('state') in ('queued', 'processing'):
                    return path.parent.name
    feature, _ = store.new_feature_job({**owner, 'grading_identity': identity,
                                       'clip_index': index}, kind, parent_job=jid)
    try:
        store.host.worker.submit(_run, feature, pid, jid, index, user_id, spec)
    except Exception:
        store.fail_feature(feature, 'Could not queue grading. Try again.')
        raise HTTPException(503, 'Could not queue grading. Try again.')
    return feature


def enqueue_clip(pid, jid, index, use_edits, user_id):
    with store.lock:
        spec = grader.snapshot(pid, jid, index, use_edits, user_id)
        grade = grader.cached_grade(pid, jid, index, use_edits, user_id, spec)
        if grade is not None:
            return {'state': 'done', 'grade': grade.model_dump()}, True
        return {'job_id': _enqueue(spec['owner'], pid, jid, index, user_id, spec)}, False


def enqueue_wave(pid, jid, user_id):
    with store.lock:
        owner = store.owner_for_job(pid, jid, user_id)
        if owner.get('kind', 'generation') != 'generation':
            raise HTTPException(400, 'Only generation waves can be graded here.')
        with store.host.jobs_lock:
            state = store.host.jobs.get(jid, {}).get('state')
        if state in ('queued', 'processing') or not (store.host.JOBS_DIR / jid / 'results.json').is_file():
            raise HTTPException(409, 'Wait for this wave to finish before grading.')
        return _enqueue(owner, pid, jid, None, user_id)


def maybe_auto_grade(jid):
    if os.getenv('AUTO_GRADE_WAVES', '0') != '1': return
    try:
        owner = json.loads((store.host.JOBS_DIR / jid / 'owner.json').read_text(encoding='utf-8'))
        if owner.get('kind', 'generation') == 'generation' and owner.get('project_id'):
            enqueue_wave(owner['project_id'], jid, owner['user_id'])
    except Exception:
        # A research failure must never turn a successful media generation into a failure.
        logger.exception('Could not automatically queue grading for %s', jid)
