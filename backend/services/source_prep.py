"""Prepare a project's source once using the agent's existing disk caches."""
import logging
import tempfile
from pathlib import Path
from backend import integration as store
from backend.agent.index import build_index
from backend.agent.summaries import ensure_summaries
from backend.core.media import inspect_video, make_thumbnail
from backend.services.projects_store import update_source

logger = logging.getLogger(__name__)


def prepare_source(job_id, project_id, user_id):
    host = store.host
    folder = host.JOBS_DIR / job_id
    stage = 'inspecting the source video'
    try:
        host.update_job(job_id, state='processing', message='Inspecting source video...')
        duration, _ = inspect_video(folder / 'source.video')
        stage = 'creating the thumbnail'
        make_thumbnail(folder / 'source.video', folder / 'thumbnail.jpg', duration * .1)
        if not update_source(project_id, user_id, job_id, source_duration=duration,
                             thumbnail_url=f'/api/projects/{project_id}/thumbnail'):
            return
        stage = 'preparing the transcript and search index'
        def progress(message):
            host.update_job(job_id, message=message)
        # Same content hash + transcription/model cache keys used by select_with_agent.
        with tempfile.TemporaryDirectory(prefix='cascade_source_') as scratch:
            index = build_index(folder / 'source.video', Path(scratch), progress=progress)
        ensure_summaries(index, progress=progress)
        update_source(project_id, user_id, job_id, source_status='ready', source_error=None)
        host.update_job(job_id, state='done', message='Source video is ready.', clips=[])
    except Exception as error:
        logger.exception('Source preparation failed for job %s', job_id)
        message = host.processing_error(error, stage)
        update_source(project_id, user_id, job_id, source_status='error', source_error=message)
        store.fail_feature(job_id, message)
