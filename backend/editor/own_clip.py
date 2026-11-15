"""Edit your own clip: upload a video straight into the Editor, no AI Studio selection needed.

The upload becomes a one-clip job (kind "upload") shaped exactly like a generated clip, so every
Editor feature (drafts, captions, B-roll, AI Editor, export) works on it unchanged. It is added to
the project's Editor clips; AI Studio's canvas ignores it because it isn't a generation.
"""
import hashlib
import logging
import shutil
import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi import File, HTTPException, Request, UploadFile

from backend.core import config, jobs as job_service, media as media_service, storage as storage_service
from backend.services import projects_store


def upload_clip(pid: str, request: Request, video: UploadFile = File(...)):
    user = request.state.user_id
    projects_store.require_project(pid, user)
    from backend.media import validate_filename, normalize_media, probe_media, AUDIO_EXTENSIONS
    validate_filename(video.filename)
    source_name = Path(video.filename or 'video').name
    if Path(source_name).suffix.lower() in AUDIO_EXTENSIONS:
        raise HTTPException(400, 'Choose a video file (MP4, MOV, WebM, MKV or AVI).')
    if shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None:
        raise HTTPException(503, 'FFmpeg and ffprobe must be installed.')
    storage = {'folder': config.DEFAULT_FOLDER, 'source': 'local'}
    if not storage_service.uses_local_storage():
        try:  # only names the cloud-backup folder; never worth failing the upload over
            storage = storage_service.resolve_storage_folder(user)
        except Exception:
            logging.getLogger(__name__).warning('Could not resolve the storage folder for an uploaded clip; using the default.')

    job_id = uuid4().hex
    folder = job_service.JOBS_DIR / job_id
    folder.mkdir(parents=True)
    source = folder / 'source.video'
    try:
        fingerprint = hashlib.sha256()
        with source.open('wb') as destination:
            while chunk := video.file.read(1024 * 1024):
                fingerprint.update(chunk)
                destination.write(chunk)
        if source.stat().st_size == 0:
            raise HTTPException(400, 'The uploaded file is empty.')
        info = normalize_media(source, probe_media(source))
        if not info['has_video']:
            raise HTTPException(400, 'This file has no video. Choose a video file.')

        owner = {'user_id': user, 'project_id': pid, 'kind': 'upload', 'prompt': '', 'source_name': source_name,
                 'media_kind': 'video', 'video_sha256': fingerprint.hexdigest(), 'requested_clip_count': 1,
                 'history_id': job_id, 'source_job': job_id, 'created_at': time.time(),
                 'user_folder': storage['folder'], 'folder_source': storage['source'], **info}
        job_service.save_json(folder / 'owner.json', owner)

        # Captions: transcribe if speech-to-text is set up; otherwise the clip starts without captions.
        captions = folder / 'own-captions.vtt'
        warning = ''
        try:
            from backend.cascade_stt import transcribe_media
            segments = transcribe_media(source)  # its scratch audio goes in a temp folder
            media_service.write_captions(captions, segments, 0, info['duration'])
        except Exception as error:  # a missing key or a provider hiccup must not block editing
            warning = f'Captions were skipped: {error}'[:300]

        # The clip is saved on this machine first, so it opens in the Editor right away.
        shutil.copyfile(source, folder / 'clip_1.mp4')
        if captions.is_file(): captions.replace(folder / 'clip_1.vtt')
        else: (folder / 'clip_1.vtt').write_text('WEBVTT\n\n')
        clip = {'clip_id': f'{job_id}:0', 'start': 0.0, 'end': info['duration'], 'title': Path(source_name).stem[:120] or 'My clip',
                'explanation': 'Your own upload', 'media_kind': 'video', 'has_video': True,
                'clip_url': f'/clips/{job_id}/clip_1.mp4', 'captions_url': f'/clips/{job_id}/clip_1.vtt'}
        job_service.save_json(folder / 'results.json', {'clips': [clip], 'requested_clip_count': 1})
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    # Put it in the Editor's clip list (the same list AI Studio's "Pick clip" fills)
    from backend import studio
    with projects_store.lock:
        project = studio.ensure(pid, user)
        ref = {'job_id': job_id, 'clip_index': 0}
        studio.set_selection(project['studio'], [*project['studio'].get('editor_clips', []), ref])
        studio.save(project, user)
    # Cloud backup (S3) runs after the response: slow or failing uploads must never block editing.
    if not storage_service.uses_local_storage():
        threading.Thread(target=_back_up, args=(folder, job_id), daemon=True).start()
    return {**ref, 'title': clip['title'], 'duration': info['duration'], 'captions': not warning, 'warning': warning}


def _back_up(folder, job_id):
    try:
        keys = storage_service.upload_clip_files(folder, job_id, 'clip_1.mp4', 'clip_1.vtt')
        results = job_service.load_json(folder / 'results.json')
        results['clips'][0].update(keys)
        job_service.save_json(folder / 'results.json', results)
        owner = job_service.load_json(folder / 'owner.json')
        original = folder / 'original-upload.media'
        original.unlink(missing_ok=True)  # the converted copy is what gets edited; skip backing up the large original
        owner.update(storage_service.upload_source_media(folder, job_id, owner))
        job_service.save_json(folder / 'owner.json', owner)
    except Exception:  # the local copy keeps working; only the backup is missing
        logging.getLogger(__name__).exception('Cloud backup of uploaded clip %s failed', job_id)
