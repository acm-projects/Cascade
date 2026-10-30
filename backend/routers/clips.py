"""Authenticated upload, generation progress, and clip playback routes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from uuid import uuid4
import hashlib
import os
import re
import shutil
import time
import traceback

from botocore.exceptions import ClientError, BotoCoreError
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from backend.services import projects_store, features as feature_workers
from backend.agent.website import requirements_error, select_with_agent
from backend.core import config, jobs as job_service, media as media_service, storage as storage_service
from backend.pipeline_timing import StageTimer

router = APIRouter()
MAX_STEPS = 400  # the step log shown on the website is capped


def process_upload(
    job_id,
    video_path,
    search,
    mode,
    target,
):
    folder = job_service.JOBS_DIR / job_id
    from backend.generation import options, contextual_prompt, followup_windows
    requested_count, parent_context = options(folder)
    original_search = search
    search = contextual_prompt(search, parent_context)
    started = time.monotonic()
    stage = 'starting analysis'
    steps = []
    steps_elapsed = []  # seconds since the job started, one per step (shown beside each step)
    timer = StageTimer(lambda timings, active: job_service.update_job(
        job_id, timings=timings, timing_stage=active, timing_stage_started_at=time.time()))

    def progress(message):
        nonlocal stage
        # No time limit by default: a first run on a long video can legitimately take a while.
        # CASCADE_JOB_TIMEOUT (seconds) is an optional safety net, checked between steps.
        budget = os.getenv('CASCADE_JOB_TIMEOUT')
        if budget and time.monotonic() - started > float(budget):
            raise TimeoutError('Job processing budget exceeded')
        stage = message
        steps.append(message)
        steps_elapsed.append(round(time.monotonic() - started, 1))
        del steps[:-MAX_STEPS], steps_elapsed[:-MAX_STEPS]
        # update_job also raises JobCancelled if the user stopped the job, so cancel works mid-agent.
        job_service.update_job(job_id, message=message, steps_log=list(steps), steps_elapsed=list(steps_elapsed))

    try:
        job_service.update_job(
            job_id,
            state="processing",
        )

        progress("Reading uploaded audio..." if job_service.load_json(folder/"owner.json").get("media_kind") == "audio" else "Reading uploaded video...")
        timer.start('Video inspection')
        from backend.media import probe_media, normalize_media
        media_info = normalize_media(video_path, probe_media(video_path))
        duration = media_info['duration']
        owner = job_service.load_json(folder/'owner.json')
        owner.update(media_info)
        from backend.core.storage import upload_source_media
        if owner.get('source_job', job_id) == job_id and not owner.get('source_s3_key'):
            owner.update(upload_source_media(folder, job_id, owner))
        job_service.save_json(folder/'owner.json', owner)
        suffix = '.mp4' if media_info['has_video'] else '.mp3'
        job_service.update_job(job_id, media_kind=media_info['media_kind'])

        # The agent: Deepgram transcript, search index, and a multi-step selection of the best
        # moments across the whole video. Cutting, captions and storage below are unchanged.
        selected, transcript, metadata = select_with_agent(
            video_path, duration, search, target, progress, timer.start,
            **({'requested_count':requested_count} if requested_count!=4 else {}),
            **({'exclude_windows': owner['exclude_windows']} if owner.get('exclude_windows') else {}),
            **({'references': owner['parent_clips']} if len(owner.get('parent_clips', [])) > 1 else {}),
            **({'request_prompt': original_search} if parent_context else {}))
        selected = followup_windows(selected, parent_context, original_search, duration, target, requested_count)
        if owner.get('exclude_windows'):
            before_exclusion = len(selected)
            selected = [clip for clip in selected if not any(
                min(clip['end'], end) - max(clip['start'], start) > .5 * min(clip['end'] - clip['start'], end - start)
                for start, end in owner['exclude_windows'])]
            if len(selected) < before_exclusion:
                metadata['selection_note'] = f'Found {len(selected)} new clips; others were already in this session.'
        metadata['requested_clip_count']=requested_count
        if len(selected)<requested_count:
            metadata['selection_note']=f'Found {len(selected)} of {requested_count} requested suitable clips. '+metadata.get('selection_note','')

        job_service.save_json(
            folder / "selected_clips.json",
            {
                "query": search,
                "model": metadata.get('model'),
                "provider": metadata.get('provider'),
                "clips": selected,
            },
        )

        total = len(selected)
        workers = media_service.render_workers(total)
        threads = media_service.encoder_threads(workers)
        timer.start('Video rendering and storage')
        results = {}

        # Encoding runs in parallel (CPU only); captions and storage happen on this thread as each
        # clip finishes, so uploads overlap with the encodes still running. Progress, cancel and the
        # optional job timeout are only ever checked here, never from the encoder threads.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for number, selection in enumerate(selected, start=1):
                progress(f"Cutting clip {number}/{total}...")
                filename = f"clip_{number}{suffix}"
                futures[pool.submit(media_service.render_clip, video_path, selection, folder / filename, threads)] = number
            try:
                for future in as_completed(futures):
                    number = futures[future]
                    future.result()
                    selection = selected[number - 1]
                    filename = f"clip_{number}{suffix}"
                    captions_filename = f"clip_{number}.vtt"
                    media_service.write_captions(folder / captions_filename, transcript, selection["start"], selection["end"])
                    progress(f"Saving clip {number}/{total}...")
                    storage = storage_service.upload_clip_files(folder, job_id, filename, captions_filename)
                    results[number] = {
                        **selection,
                        "clip_id": f"{job_id}:{number-1}",
                        "media_kind": media_info["media_kind"],
                        "has_video": media_info["has_video"],
                        **storage,
                        "clip_url": f"/clips/{job_id}/{filename}",
                        "captions_url": f"/clips/{job_id}/{captions_filename}",
                    }
                    ready = []
                    for index in range(1, total + 1):
                        if index not in results: break
                        ready.append(storage_service.public_clip(results[index]))
                    if ready and 'first_clip_ready_seconds' not in metadata:
                        metadata['first_clip_ready_seconds'] = round(time.monotonic() - started, 3)
                    job_service.update_job(job_id, clips=ready, ready_clip_count=len(ready), requested_clip_count=requested_count)
            except BaseException:
                for future in futures:
                    future.cancel()  # clips not started yet are skipped; running encodes finish on their own
                raise

        clips = [results[number] for number in sorted(results)]

        timings = timer.finish()
        job_service.save_json(
            folder / "results.json",
            {"clips": clips, 'timings': timings, 'steps_log': list(steps), 'steps_elapsed': list(steps_elapsed), **metadata},
        )

        job_service.update_job(
            job_id,
            state="done",

            message=(
                f"{len(clips)} clip(s) ready."
                if clips
                else "No matching clip was found."
            ),

            clips=[
                storage_service.public_clip(clip)
                for clip in clips
            ],
            **metadata,
        )

    except Exception as error:
        traceback.print_exc()
        message = job_service.processing_error(error, stage)
        projects_store.fail_feature(job_id, message)


@router.post("/upload", status_code=202)
def upload_video(
    request: Request,
    video: UploadFile = File(...),
    search: str = Form(...),
    mode: str = Form("both"),
    clip_length: int = Form(30),
    project_id: str = Form(...),
    engine: str = Form("agent"),
    clip_count: int = Form(4, ge=1, le=50),
    source_job: str | None = Form(None),
    parent_job: str | None = Form(None),
    parent_clip_index: int | None = Form(None, ge=0),
    canvas_context: str | None = Form(None),
):
    with projects_store.lock:
        projects_store.require_project(project_id, request.state.user_id)
        from backend.generation import MAX_CLIPS
        if not 1 <= clip_count <= MAX_CLIPS:
            raise HTTPException(400, 'Choose 1–50 clips.')
        parent_context = None
        from backend import studio
        studio_context = studio.prepare_upload(project_id,
                                               request.state.user_id, canvas_context)
        if studio_context:
            if parent_job:
                raise HTTPException(400, 'Use studio reference clips for this request.')
            source_job = studio_context['source_job']
            references = studio_context['references']
            parent_context = ({'references': references} if len(references) > 1 else references[0]) if references else None
        if parent_job:
            if parent_clip_index is None:
                raise HTTPException(400, 'Choose a parent clip.')
            parent_owner, parent = projects_store.selected_clip(project_id, projects_store.ClipInput(job_id=parent_job, clip_index=parent_clip_index), request.state.user_id)
            original = projects_store.original_source(project_id, parent_job, request.state.user_id)
            source_job = original.parent.name
            parent_context = {'clip_id': f'{parent_job}:{parent_clip_index}', 'job_id': parent_job, 'clip_index': parent_clip_index,
                              'start': parent['start'], 'end': parent['end'], 'title': parent.get('title', ''),
                              'prompt': parent_owner.get('prompt', ''), 'description': parent.get('explanation', '')}
            captions_path = job_service.JOBS_DIR / parent_job / f'clip_{parent_clip_index+1}.vtt'
            if captions_path.is_file():
                parent_context['captions'] = captions_path.read_text(encoding='utf-8-sig')[:12000]
        elif parent_clip_index is not None:
            raise HTTPException(400, 'Choose a parent generation.')
        if source_job:
            original = projects_store.original_source(project_id, source_job, request.state.user_id)
            source_job = original.parent.name
        from backend.media import validate_filename, AUDIO_EXTENSIONS
        if not source_job:
            validate_filename(video.filename)
        source_name = Path(video.filename or 'video').name
        if Path(source_name).suffix.lower() in AUDIO_EXTENSIONS:
            engine = 'agent'
        if source_job:
            source_owner = job_service.load_json(job_service.JOBS_DIR / source_job / 'owner.json')
            source_name = source_owner.get('source_name', source_name)
        storage_service.validate_clip_storage()
        # Old saved editor requests may name the retired engines; keep their source context
        # but run selection through main's configured agent, never restore Ollama/Whisper.
        if engine in ('openai','qwen'):
            engine='agent'
        if engine not in ('agent','speech','visual'):
            raise HTTPException(400, 'Invalid search engine.')
        configuration_error = requirements_error() if engine=='agent' else (
            None if os.getenv('DEEPGRAM_API_KEY','').strip() else 'DEEPGRAM_API_KEY is not set. Add it to .env and restart the server.')
        if configuration_error:
            raise HTTPException(503, configuration_error)
        search = search.strip()

        if not search or len(search) > 2000:
            raise HTTPException(
                400,
                "Enter a prompt of 1–2000 characters.",
            )

        if mode not in (
            "speech",
            "visual",
            "both",
        ):
            raise HTTPException(
                400,
                "Invalid search mode.",
            )

        if clip_length not in (15, 30, 60):
            raise HTTPException(
                400,
                "Invalid clip length.",
            )

        if (
            shutil.which("ffmpeg") is None
            or shutil.which("ffprobe") is None
        ):
            raise HTTPException(
                503,
                "FFmpeg and ffprobe must be installed.",
            )

        storage_information = ({'folder': config.DEFAULT_FOLDER, 'source': 'local'} if storage_service.uses_local_storage()
                               else storage_service.resolve_storage_folder(request.state.user_id))

        job_id = uuid4().hex

        folder = job_service.JOBS_DIR / job_id
        folder.mkdir()

        video_path = folder / "source.video"

        try:
            fingerprint = hashlib.sha256()
            if source_job:
                from backend.generation import reuse_source
                fingerprint = reuse_source(original, video_path)
            else:
                with video_path.open('wb') as destination:
                    while chunk := video.file.read(1024 * 1024):
                        fingerprint.update(chunk)
                        destination.write(chunk)

            if video_path.stat().st_size == 0:
                raise HTTPException(
                    400,
                    "The uploaded file is empty.",
                )

            job_service.save_json(
                folder / "owner.json",
                {
                    "user_id": request.state.user_id,
                    "project_id": project_id,
                    "prompt": search,
                    "source_name": source_name,
                    "media_kind": "audio" if Path(source_name).suffix.lower() in AUDIO_EXTENSIONS else "video",
                    "video_sha256": fingerprint.hexdigest(),
                    "engine": engine,
                    "mode": mode if engine=="agent" else engine,
                    "clip_length": clip_length,
                    "requested_clip_count": clip_count,
                    "history_id": job_id,
                    "creation_order": 1 + max((j.get("creation_order") or i+1 for i,j in enumerate(reversed(projects_store.project_jobs(project_id, request.state.user_id))) if j["kind"] == "generation"), default=0),
                    "created_at": time.time(),
                    "source_job": source_job or job_id,
                    "parent_clip": (studio_context['references'][0] if studio_context and studio_context['references'] else parent_context),
                    "parent_clips": studio_context['references'] if studio_context else [],
                    "exclude_windows": studio_context.get('exclude_windows', []) if studio_context else [],
                    "studio_session_id": studio_context['session_id'] if studio_context else None,
                    "studio_revision_of": studio_context.get('revision_of') if studio_context else None,
                    "studio_revision_targets": studio_context.get('revision_targets', []) if studio_context else [],
                    "request_id": studio_context['request_id'] if studio_context else None,

                    "user_folder": (
                        storage_information["folder"]
                    ),

                    "folder_source": (
                        storage_information["source"]
                    ),
                },
            )
            # Reuse only analysis from the same verified account and project.
            for previous in job_service.metadata_paths('*/owner.json'):
                if previous.parent == folder:
                    continue
                try:
                    owner = job_service.load_json(previous)
                except (OSError, ValueError):
                    continue
                if (owner.get('user_id') == request.state.user_id and owner.get('project_id') == project_id
                        and owner.get('video_sha256') == fingerprint.hexdigest()):
                    for name in ('transcript.json', 'video_descriptions.json', 'visual_analysis_settings.json', 'openai_selection.json'):
                        cached = previous.parent / name
                        if cached.is_file() and not (folder / name).exists():
                            shutil.copyfile(cached, folder / name)

        except Exception:
            shutil.rmtree(folder)
            raise

        finally:
            video.file.close()

        with job_service.jobs_lock:
            job_service.jobs[job_id] = {
                "state": "queued",
                "message": "Waiting to process...",
                "clips": [],
            }

        job_service.save_json(folder / 'progress.json', dict(job_service.jobs[job_id]))
        if studio_context:
            try:
                studio.record_submission(project_id, request.state.user_id,
                                         job_id, studio_context, search)
            except Exception:
                projects_store.fail_feature(job_id, 'Could not save the studio request. No generation was started.')
                raise
        try:
            job_service.worker.submit(process_upload if engine=='agent' else feature_workers.process_search,
                          job_id, video_path, search, mode if engine=='agent' else engine, clip_length)
        except Exception:
            projects_store.fail_feature(job_id, 'Could not queue generation. Retry this request.')
        return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    request: Request,
):
    job_service.require_job_owner(
        job_id,
        request.state.user_id,
    )

    with job_service.jobs_lock:
        if job_id in job_service.jobs:
            return dict(job_service.jobs[job_id])

    results_path = (
        job_service.JOBS_DIR / job_id / "results.json"
    )

    if job_service.metadata_exists(results_path):
        results = job_service.load_json(results_path)

        clips = [
            storage_service.public_clip(clip)
            for clip in results.get("clips", [])
            if isinstance(clip, dict)
        ]

        return {
            "state": "done",

            "message": (
                "Clip 1 is ready."
                if clips
                else "No matching clip was found."
            ),

            "clips": clips,
            "steps_log": results.get("steps_log", []),
            "steps_elapsed": results.get("steps_elapsed", []),
            "timings": results.get("timings"),
            "selection_note": results.get("selection_note", ""),
        }

    raise HTTPException(
        404,
        (
            "Job unavailable. The server may have "
            "restarted before processing finished. "
            "Upload the video again."
        ),
    )


@router.get("/clips/{job_id}/{filename}")
def get_clip(
    job_id: str,
    filename: str,
    request: Request,
):
    job_service.require_job_owner(
        job_id,
        request.state.user_id,
    )

    # Keep compatibility with previously saved jobs.
    if not re.fullmatch(
        r"clip_[1-9][0-9]*\.(mp4|mp3|vtt)",
        filename,
    ):
        raise HTTPException(
            404,
            "Clip not found.",
        )

    folder = job_service.JOBS_DIR / job_id

    results_path = folder / "results.json"

    storage = None

    if job_service.metadata_exists(results_path):
        results = job_service.load_json(results_path)

        for clip in results.get("clips", []):
            field = (
                "clip_url"
                if not filename.endswith(".vtt")
                else "captions_url"
            )

            if clip.get(field) == (
                f"/clips/{job_id}/{filename}"
            ):
                storage = clip
                break

    key_field = (
        "clip_s3_key"
        if not filename.endswith(".vtt")
        else "captions_s3_key"
    )

    from backend.media import content_type
    media_type = content_type(filename)

    path = folder / filename
    if path.is_file():
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Cache-Control": "no-store"},
        )

    if storage and storage.get(key_field):
        parameters = {
            "Bucket": storage["s3_bucket"],
            "Key": storage[key_field],
        }

        byte_range = request.headers.get(
            "range"
        )

        if byte_range:
            if not re.fullmatch(
                r"bytes=(?:[0-9]+-[0-9]*|-[0-9]+)",
                byte_range,
            ):
                raise HTTPException(
                    416,
                    "Invalid byte range.",
                )

            parameters["Range"] = byte_range

        try:
            result = storage_service.s3_client().get_object(
                **parameters
            )

        except ClientError as error:
            code = error.response.get(
                "Error",
                {},
            ).get("Code")

            if code == "InvalidRange":
                raise HTTPException(
                    416,
                    "Requested range unavailable.",
                ) from error

            if code in ("NoSuchKey", "404"):
                raise HTTPException(
                    404,
                    "Clip not found.",
                ) from error

            raise HTTPException(
                503,
                "Could not retrieve clip.",
            ) from error

        except BotoCoreError as error:
            raise HTTPException(
                503,
                "Could not retrieve clip.",
            ) from error

        body = result["Body"]

        def chunks():
            try:
                yield from body.iter_chunks(
                    chunk_size=1024 * 1024
                )

            finally:
                body.close()

        headers = {
            "Content-Length": str(
                result["ContentLength"]
            ),

            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store",
        }

        if result.get("ContentRange"):
            headers["Content-Range"] = (
                result["ContentRange"]
            )

        return StreamingResponse(
            chunks(),
            media_type=media_type,
            headers=headers,
            status_code=(
                206 if byte_range else 200
            ),
        )

    path = folder / filename

    if not path.is_file():
        raise HTTPException(
            404,
            "Clip not found.",
        )

    return FileResponse(
        path,
        media_type=media_type,
    )


@router.get("/api/my-clips")
def get_my_clips(request: Request):
    saved_clips = []

    owners = job_service.metadata_documents('*/owner.json', request.state.user_id)
    owners.sort(key=lambda item: item[1].get('created_at', 0), reverse=True)

    for owner_path, owner in owners:
        folder = owner_path.parent
        results_path = folder / "results.json"

        try:
            if (
                owner.get("user_id")
                != request.state.user_id or owner.get("project_deleted")
            ):
                continue

            if not job_service.metadata_exists(results_path):
                continue

            results = job_service.load_json(results_path)

            clips = results.get("clips", [])

            if not isinstance(clips, list):
                continue

            for clip in clips:
                if not isinstance(clip, dict):
                    continue

                clip_url = clip.get("clip_url")

                if not isinstance(clip_url, str):
                    continue

                match = re.fullmatch(
                    (
                        rf"/clips/{folder.name}/"
                        r"(clip_[1-9][0-9]*\.mp4)"
                    ),
                    clip_url,
                )

                if not match:
                    continue

                if (
                    not clip.get("clip_s3_key")
                    and not (
                        folder / match.group(1)
                    ).is_file()
                ):
                    continue

                saved_clips.append({
                    **storage_service.public_clip(clip),
                    "job_id": folder.name,
                })

        except (
            OSError,
            ValueError,
            TypeError,
            AttributeError,
        ):
            continue

    return JSONResponse(
        {"clips": saved_clips},
        headers={
            "Cache-Control": "no-store",
        },
    )
