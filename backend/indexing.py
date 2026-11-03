"""Project video analysis, run once when a project is created with its video.

The project's source job folder gets index/{transcript.json, moments.json, vectors.npz}: everything
a prompt needs to pick clips with one model call (backend/agent/moment_selection.py). Prompts sent
before it finishes wait for it (wait_ready). Runs on its own thread, never on job_service.worker,
because queued prompt jobs on that worker wait for it.
"""
import json
import logging
import tempfile
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from backend.core import jobs as job_service
from backend.core import storage as storage_service
from backend.pipeline_timing import StageTimer

logger = logging.getLogger("cascade_indexing")
pool = ThreadPoolExecutor(max_workers=1)
convert_pool = ThreadPoolExecutor(max_workers=1)  # video conversion runs beside the analysis, not before it
ready_events = {}  # source job -> Event, set when its index finished (ready or error)
loaded = OrderedDict()  # source job -> VideoIndex with moments, the last few projects only
loaded_lock = threading.Lock()
warming = set()  # source jobs being loaded in the background right now
LOADED_LIMIT = 2
INDEX_FILES = ('transcript.json', 'moments.json', 'vectors.npz')


def index_dir(source_job):
    return job_service.JOBS_DIR / source_job / 'index'


def start(source_job):
    with job_service.jobs_lock:
        job_service.jobs[source_job] = {'state': 'queued', 'message': 'Waiting to analyse the video...', 'clips': []}
        ready_events[source_job] = threading.Event()
    job_service.save_json(job_service.JOBS_DIR / source_job / 'progress.json', dict(job_service.jobs[source_job]))
    pool.submit(build, source_job)


def status(source_job):
    """{state, message, steps_log, timings, ...} for the Studio progress widget."""
    with job_service.jobs_lock:
        if source_job in job_service.jobs:
            return dict(job_service.jobs[source_job])
    path = job_service.JOBS_DIR / source_job / 'progress.json'
    saved = job_service.load_json(path) if job_service.metadata_exists(path) else {}
    if saved.get('state') in ('queued', 'processing'):  # the server restarted mid-analysis
        return {**saved, 'state': 'error', 'message': 'Video analysis was interrupted. Retry it.'}
    return saved or {'state': 'error', 'message': 'Video analysis has not run. Retry it.'}


def wait_ready(source_job, on_wait):
    """Block until the source is analysed. on_wait() runs about once a second (it raises on
    cancel). Raises SelectionError (shown to the user) when the analysis failed."""
    from backend.agent.website import SelectionError
    event = ready_events.get(source_job)
    while event is not None and not event.wait(1):
        on_wait()
    if status(source_job).get('state') != 'done':
        raise SelectionError('Video analysis failed. Retry it from the Studio, then send the prompt again.')


def build(source_job):
    job_service.update_job(source_job, state='processing', message='Loading the analysis models...')
    from backend.agent.index import build_index  # the first import after a restart loads ML libraries (~10s)
    from backend.agent.moments import describe_moments, moment_vectors
    from backend.media import (convert_media, gpu_encoder, needs_conversion, needs_reencode, normalize_media,
                               probe_media, replace_with_converted)
    from backend.video_search import router as vs

    folder = job_service.JOBS_DIR / source_job
    video = folder / 'source.video'
    timer = StageTimer(lambda timings, active: job_service.update_job(
        source_job, timings=timings, timing_stage=active))
    steps, elapsed, started = [], [], time.monotonic()

    def progress(message):
        steps.append(message)
        elapsed.append(round(time.monotonic() - started, 1))
        job_service.update_job(source_job, message=message, steps_log=steps[-200:], steps_elapsed=elapsed[-200:])

    converted = folder / 'normalized.mp4'
    try:
        timer.start('Preparing video')
        progress('Reading the video...')
        owner = job_service.load_json(folder / 'owner.json')
        info = probe_media(video)
        conversion = None
        if needs_conversion(info) and needs_reencode(info):
            # Slow (HEVC, VP9, ...): convert alongside the analysis, which reads the original as it is.
            # The converted file replaces the original before the project is marked ready.
            encoder = gpu_encoder()
            progress(f'Converting the {str(info["video_codec"]).upper()} video to H.264 on the '
                     f'{encoder[0] if encoder else "CPU"}, alongside the analysis')
            conversion = convert_pool.submit(convert_media, video, info, converted, progress)
        else:
            owner.update(normalize_media(video, info))  # nothing to do, or a few seconds to move it into an MP4
        job_service.save_json(folder / 'owner.json', owner)

        timer.start('Transcript and search index')
        with tempfile.TemporaryDirectory(prefix='project_index_') as scratch:
            index = build_index(video, Path(scratch), progress=progress, visual=True)
        # Transcript and frames run side by side; their own times show which one held this stage up.
        job_service.update_job(source_job, index_timings=index.timings)

        timer.start('Moment cards')
        # Video stretches without speech are described from their frames; audio-only has none.
        cards, usage = describe_moments(index.transcript, progress, video_path=video if index.has_video else None,
                                        duration=index.duration, video_key=index.video_key)
        vectors = moment_vectors(cards, index, lambda texts: vs.search_model.encode(texts, normalize_embeddings=True)) if cards else {}
        progress('Saving the analysis')
        save_bundle(source_job, index, cards, vectors)
        if conversion:
            if not conversion.done():
                timer.start('Finishing video conversion')
                progress('Waiting for the video conversion to finish')
            normalized = conversion.result()
            replace_with_converted(video, converted)
            owner = job_service.load_json(folder / 'owner.json')
            owner.update(normalized)
            job_service.save_json(folder / 'owner.json', owner)
            progress(f'Video converted to H.264 on the {"CPU" if normalized["encoder"] == "cpu" else normalized["encoder"]}')
        if index.has_video:
            from backend.routers.projects import frame_time, prepare_frames
            # The source box's thumbnail; the same duration the frame endpoint reads, so it is a cache hit.
            prepare_frames(video, [frame_time(owner.get('duration') or index.duration, None)])
        progress(f'Ready: {len(cards)} moments ({sum(not c["speech"] for c in cards)} without speech, described from frames)')
        timings = timer.finish()
        job_service.update_job(source_job, state='done', message='Video analysed. Ready for prompts.',
                               timings=timings, moment_count=len(cards), moment_usage=usage)
    except Exception as error:
        logger.exception('Video analysis failed for %s', source_job)
        job_service.update_job(source_job, state='error',
                               message=job_service.processing_error(error, 'analysing the video'))
        return
    finally:
        try:
            converted.unlink(missing_ok=True)  # left over only when something failed
        except OSError:
            pass  # a conversion still running after a failure keeps it open; the next run overwrites it
        event = ready_events.get(source_job)
        if event:
            event.set()

    # The S3 backup is not needed to prompt on this laptop, so it runs after "ready".
    if not storage_service.uses_local_storage():
        try:
            owner = job_service.load_json(folder / 'owner.json')
            owner.update(storage_service.upload_source_media(folder, source_job, owner))
            owner.update(storage_service.upload_index_files(folder, source_job, owner, INDEX_FILES))
            job_service.save_json(folder / 'owner.json', owner)
        except Exception:
            logger.exception('Could not back up %s to S3', source_job)


def save_bundle(source_job, index, cards, vectors):
    target = index_dir(source_job)
    target.mkdir(exist_ok=True)
    (target / 'transcript.json').write_text(json.dumps(index.transcript), encoding='utf-8')
    (target / 'moments.json').write_text(json.dumps({'moments': cards, 'duration': index.duration,
                                                     'has_video': index.has_video}), encoding='utf-8')
    np.savez(target / 'vectors.npz', segment=index.segment_embeddings, frames=index.frame_embeddings,
             frame_times=np.array(index.frame_times), interval=np.array(index.frame_interval),
             **{f'moment_{k}': v for k, v in vectors.items()})
    with loaded_lock:
        loaded.pop(source_job, None)


def load(source_job):
    """The project's analysed index (a VideoIndex with .moments and .moment_vectors), kept in
    memory for the last few projects; None when this source has no finished analysis."""
    with loaded_lock:
        if source_job in loaded:
            loaded.move_to_end(source_job)
            return loaded[source_job]
    if status(source_job).get('state') != 'done':
        return None
    target = index_dir(source_job)
    if not all((target / name).is_file() for name in INDEX_FILES):
        owner = job_service.load_json(job_service.JOBS_DIR / source_job / 'owner.json')
        if not owner.get('index_s3_keys'):
            return None
        storage_service.download_index_files(owner, target)
    index = read_bundle(target)
    with loaded_lock:
        loaded[source_job] = index
        while len(loaded) > LOADED_LIMIT:
            loaded.popitem(last=False)
    return index


def read_bundle(target):
    from backend.agent.chunks import build_chunks
    from backend.agent.index import VideoIndex
    from backend.video_search import router as vs

    transcript = json.loads((target / 'transcript.json').read_text(encoding='utf-8'))
    meta = json.loads((target / 'moments.json').read_text(encoding='utf-8'))
    with np.load(target / 'vectors.npz') as data:
        arrays = {key: data[key] for key in data.files}
    vs.load_models('speech')
    frame_times = [float(t) for t in arrays['frame_times']]
    if frame_times:
        vs.load_models('visual')
    index = VideoIndex(
        duration=float(meta['duration']), has_video=meta['has_video'], frame_interval=float(arrays['interval']),
        frame_times=frame_times, frame_embeddings=arrays['frames'], transcript=transcript,
        segment_embeddings=arrays['segment'], chunks=build_chunks(transcript),
        encode_visual_query=(lambda q: vs.visual_model.encode(q, normalize_embeddings=True)),
        encode_text_query=(lambda q: vs.search_model.encode(q, normalize_embeddings=True)),
        index_mode='multimodal' if frame_times else 'transcript-first')
    index.moments = meta['moments']
    index.moment_vectors = {k[len('moment_'):]: v for k, v in arrays.items() if k.startswith('moment_')}
    return index


def warm(source_job):
    """Load the index in the background when a project is opened, so the first prompt is fast."""
    with loaded_lock:
        if source_job in loaded or source_job in warming:
            return
        warming.add(source_job)
    threading.Thread(target=lambda: _quiet_load(source_job), daemon=True).start()


def _quiet_load(source_job):
    try:
        load(source_job)
    except Exception:
        logger.exception('Could not load the analysis for %s', source_job)
    finally:
        with loaded_lock:
            warming.discard(source_job)
