"""Demo mode (CASCADE_DEMO=on, demo branches only): the ACM presentation without waiting on any processing.

Everything shown is a real Cascade result, saved beforehand in demo_assets/<set>/ (CASCADE_DEMO_SET, default
"jaguar"):

    results.json, clip_1.mp4 … clip_N.mp4, clip_1.vtt … clip_N.vtt   the clips one real Studio run found
    source.mp4 (optional, not in git: too big)                         that run's normalized source video

- Any Studio prompt returns those clips at once (instant_clips replaces the agent worker). Uploading still works
  as normal; when source.mp4 is present it stands in for the upload, so "Original media" plays the real video.
- Opening the Editor with two or more picked clips joins them (in clip order) into one clip and shows only that
  clip (editor_clips). The join is a stream copy, so it takes about a second, and the same picks reuse it.
With CASCADE_DEMO off nothing here runs.
"""
import json
import os
import time
from pathlib import Path

from backend.core import config, jobs as job_service

ROOT = Path(config.PROJECT_DIR)/'demo_assets'
CLIP_FIELDS = ('start', 'end', 'title', 'explanation', 'match', 'score', 'reason')


def enabled():
    return os.getenv('CASCADE_DEMO', '').strip().lower() in ('1', 'on', 'true', 'yes')


def folder():
    return ROOT/(os.getenv('CASCADE_DEMO_SET', '').strip() or 'jaguar')


def _link(source, destination):
    destination.unlink(missing_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        import shutil
        shutil.copyfile(source, destination)


def saved_clips():
    """The saved clips (results.json entries) or [] when the demo set is missing."""
    path = folder()/'results.json'
    if not path.is_file(): return []
    clips = json.loads(path.read_text(encoding='utf-8')).get('clips', [])
    return [c for i, c in enumerate(clips, 1) if (folder()/f'clip_{i}.mp4').is_file()]


# ---------- Studio: any prompt -> the saved clips ----------

def instant_clips(job_id, video_path, search, mode, target):
    """Worker used instead of the agent in demo mode: publish the saved clips under this job straight away."""
    from backend.media import probe_media
    from backend.services import projects_store
    job_folder = job_service.JOBS_DIR/job_id
    try:
        job_service.update_job(job_id, state='processing', message='Finding the best moments...')
        source = folder()/'source.mp4'
        if source.is_file():
            _link(source, Path(video_path))
        owner = job_service.load_json(job_folder/'owner.json')
        try:
            owner.update(probe_media(video_path))
        except Exception:
            pass
        owner['demo'] = True
        job_service.save_json(job_folder/'owner.json', owner)
        clips = []
        for number, saved in enumerate(saved_clips(), 1):
            _link(folder()/f'clip_{number}.mp4', job_folder/f'clip_{number}.mp4')
            captions = folder()/f'clip_{number}.vtt'
            if captions.is_file(): _link(captions, job_folder/f'clip_{number}.vtt')
            clips.append({**{k: saved[k] for k in CLIP_FIELDS if k in saved},
                          'clip_id': f'{job_id}:{number-1}', 'media_kind': 'video', 'has_video': True,
                          'storage': 'local', 'backup_state': 'local',
                          'clip_url': f'/clips/{job_id}/clip_{number}.mp4', 'captions_url': f'/clips/{job_id}/clip_{number}.vtt'})
        if not clips:
            raise RuntimeError(f'Demo clips are missing: put them in {folder()}.')
        from backend.core.storage import public_clip
        meta = {'requested_clip_count': len(clips), 'backup_state': 'local', 'demo': True}
        job_service.save_json(job_folder/'results.json', {'clips': clips, **meta})
        job_service.update_job(job_id, state='done', message=f'{len(clips)} clip(s) ready.',
                               clips=[public_clip(c) for c in clips], **meta)
    except Exception as error:
        import traceback
        traceback.print_exc()
        projects_store.fail_feature(job_id, str(error) or 'The demo clips could not be loaded.')


# ---------- Editor: picked clips -> one joined clip ----------

def ordered_picks(chosen):
    """Picked clips in story order: oldest generation first, then clip number."""
    paths = {ref['job_id']: job_service.JOBS_DIR/ref['job_id']/'owner.json' for ref in chosen}
    documents = job_service.metadata_store().read_many(paths.values())
    picks = {}
    for ref in chosen:
        job_id, index = ref['job_id'], ref['clip_index']
        owner = documents.get(paths[job_id])
        if owner is not None and owner.get('kind') != 'combined':
            picks[(job_id, index)] = owner.get('created_at', 0)
    return [{'job_id': job_id, 'clip_index': index}
            for job_id, index in sorted(picks, key=lambda key: (picks[key], key[1]))]


def _matches_join(job_id, owner, want):
    made = [(p['job_id'], p['clip_index']) for p in owner.get('combined_from', [])]
    return made == want and (job_service.JOBS_DIR/job_id/'clip_1.mp4').is_file()


def existing(pid, user, picks):
    """The joined clip already made from exactly these picks, if any."""
    from backend.services import projects_store
    want = [(p['job_id'], p['clip_index']) for p in picks]
    for job in projects_store.project_jobs(pid, user):
        if job['kind'] != 'combined': continue
        owner = job_service.load_json(job_service.JOBS_DIR/job['job_id']/'owner.json')
        if _matches_join(job['job_id'], owner, want):
            return {'job_id': job['job_id'], 'clip_index': 0}
    return None


JOINING = __import__('threading').Lock()   # one join at a time, so the early join and the Editor never make two


def join_early(pid, user):
    """Studio picks changed: make the joined clip now, in the background, so opening the Editor finds it ready."""
    import threading
    from types import SimpleNamespace
    def run():
        try:
            editor_clips(pid, SimpleNamespace(state=SimpleNamespace(user_id=user)))
        except Exception:
            import logging
            logging.getLogger(__name__).info('early join skipped', exc_info=True)
    threading.Thread(target=run, daemon=True, name='cascade-demo-join').start()


def editor_clips(pid, request):
    """The joined clip for the current picks (made now if needed), or None when fewer than two clips are picked."""
    from backend.services import projects_store
    user = request.state.user_id
    with projects_store.lock:
        project = projects_store.require_project(pid, user)
        studio = project.get('studio', {})
        if studio.get('selection_model') == 'shared-v1' and len(studio.get('editor_clips', [])) < 2:
            return None
        ready = ready_editor_clip(pid, user, project)
        if ready:
            return ready
    with JOINING:
        return _editor_clips(pid, request)


def ready_editor_clip(pid, user, project):
    """Reuse a finished join without waiting for FFmpeg or the join lock."""
    studio = project.get('studio', {})
    chosen = studio.get('editor_clips', [])
    current = project.get('editor_selection')
    if (studio.get('selection_model') == 'shared-v1' and len(chosen) >= 2
            and current in chosen and current['clip_index'] == 0
            and _current_join_matches(pid, user, current['job_id'], chosen)):
        return current
    return None


def _current_join_matches(pid, user, job_id, chosen):
    path = job_service.JOBS_DIR/job_id/'owner.json'
    try:
        owner = job_service.load_json(path)
    except FileNotFoundError:
        return False
    if (owner.get('kind') != 'combined' or owner.get('user_id') != user
            or owner.get('project_id') != pid or owner.get('project_deleted')):
        return False
    want = [(p['job_id'], p['clip_index']) for p in ordered_picks(chosen)]
    return len(want) >= 2 and _matches_join(job_id, owner, want)


def _editor_clips(pid, request):
    from backend import studio
    from backend.services import projects_store
    user = request.state.user_id
    with projects_store.lock:
        chosen = list(studio.ensure(pid, user)['studio'].get('editor_clips', []))
        picks = ordered_picks(chosen)
        if len(picks) < 2: return None
        found = existing(pid, user, picks)
    if found:
        with projects_store.lock:
            project = studio.ensure(pid, user)
            project['editor_selection'] = found
            studio.save(project, user)
        return found
    from backend.editor.combine import CombineInput, Part, combine_clips
    made = combine_clips(pid, CombineInput(clips=[Part(**p) for p in picks]), request)
    return {'job_id': made['job_id'], 'clip_index': 0}


def concat_copy(paths, out):
    """Join same-format clips without re-encoding (about a second for a few minutes of video). False if it fails."""
    import subprocess
    listing = Path(out).with_suffix('.txt')
    listing.write_text(''.join("file '{}'\n".format(str(Path(p).resolve()).replace("'", "'\\''")) for p in paths))
    try:
        run = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing),
                              '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy', '-movflags', '+faststart', str(out)],
                             capture_output=True, text=True, timeout=300)
        return run.returncode == 0 and Path(out).is_file() and Path(out).stat().st_size > 0
    finally:
        listing.unlink(missing_ok=True)


def same_format(infos):
    keys = ('video_codec', 'width', 'height', 'pixel_format', 'has_audio', 'audio_codec')
    return len({tuple(info.get(k) for k in keys) for info in infos}) == 1 and all(i.get('video_codec') == 'h264' for i in infos)



# ---------- saving a real run as the demo set ----------

def capture(job_id, with_source=True):
    """Copy a finished Studio run (video_jobs/<job_id>) into demo_assets/<set>/. Returns the clip titles."""
    import shutil
    job_folder = job_service.JOBS_DIR/job_id
    results = job_service.load_json(job_folder/'results.json')
    target = folder(); target.mkdir(parents=True, exist_ok=True)
    for old in target.glob('clip_*'): old.unlink()
    clips = []
    for number, clip in enumerate(results.get('clips', []), 1):
        shutil.copyfile(job_folder/f'clip_{number}.mp4', target/f'clip_{number}.mp4')
        if (job_folder/f'clip_{number}.vtt').is_file():
            shutil.copyfile(job_folder/f'clip_{number}.vtt', target/f'clip_{number}.vtt')
        clips.append({k: clip[k] for k in CLIP_FIELDS if k in clip})
    owner = job_service.load_json(job_folder/'owner.json')
    (target/'results.json').write_text(json.dumps({'clips': clips, 'prompt': owner.get('prompt', ''),
                                                   'source_name': owner.get('source_name', ''), 'from_job': job_id}, indent=1, ensure_ascii=False))
    if with_source and (job_folder/'source.video').is_file():
        _link(job_folder/'source.video', target/'source.mp4')
    return [c.get('title') for c in clips]


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != 'capture':
        sys.exit('usage: python -m backend.demo capture <job_id>')
    print('\n'.join(capture(sys.argv[2])))
    print('saved to', folder())


# ---------- Editor tabs: instant jaguar b-roll, built-in music, the finished AI edit ----------

BROLL = ROOT/'broll'
MUSIC = ROOT/'music_library'
VIDEO = ('.mp4', '.mov', '.m4v')


def broll_files():
    return sorted(p for p in BROLL.glob('*') if p.suffix.lower() in VIDEO) if BROLL.is_dir() else []


def broll_results(store, query, page=1):
    """Any B-roll search returns the saved footage at once (best name matches first), ready to add to the timeline."""
    import re
    import subprocess
    from backend.broll import write_json
    files = broll_files()
    want = set(re.findall(r'[a-z]{3,}', (query or '').lower()))
    files.sort(key=lambda p: -len(want & set(re.findall(r'[a-z]{3,}', p.stem.lower()))))
    store.folder.mkdir(parents=True, exist_ok=True)
    registry = store.registry()
    results = []
    for path in files:
        number = int.from_bytes(path.stem.encode()[:6].ljust(6, b'_'), 'big') % 900000 + 9000000
        ident = f'px-{number}-1'
        target = store.folder/f'{ident}.mp4'
        if not target.is_file(): _link(path, target)
        thumb = store.folder/f'{ident}.jpg'
        if not thumb.is_file():
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', '0.5', '-i', str(path), '-frames:v', '1', '-vf', 'scale=480:-2',
                            str(thumb)], capture_output=True, timeout=60)
        info = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=width,height', '-of', 'json', str(path)],
                              capture_output=True, text=True, timeout=30)
        data = json.loads(info.stdout or '{}')
        stream = (data.get('streams') or [{}])[0]
        asset = {'id': ident, 'provider_id': number, 'creator': 'Cascade', 'creator_url': 'https://www.pexels.com/',
                 'source_url': f'https://www.pexels.com/video/{path.stem}-{number}/', 'duration': round(float(data.get('format', {}).get('duration', 4)), 3),
                 'width': int(stream.get('width', 1280)), 'height': int(stream.get('height', 720))}
        registry[ident] = {'asset': asset, 'video': f'https://videos.pexels.com/video-files/{number}/{ident}.mp4',
                           'image': f'https://images.pexels.com/videos/{number}/{ident}.jpg'}
        results.append(asset)
    write_json(store.folder/'assets.json', registry)
    return {'results': results if page == 1 else [], 'page': page, 'query': query, 'has_more': False}


def music_tracks():
    return sorted(p for p in MUSIC.glob('*') if p.suffix.lower() in ('.mp3', '.wav', '.m4a')) if MUSIC.is_dir() else []


def add_music(store, items):
    """Put the built-in demo tracks into a clip's music list (converted to the store's wav once)."""
    import hashlib
    import subprocess
    for path in music_tracks():
        ident = 'aud-'+hashlib.sha256(('cascade-demo-v1:'+path.stem).encode()).hexdigest()[:32]
        wav = store.folder/(ident+'.wav')
        if not wav.is_file():
            store.folder.mkdir(parents=True, exist_ok=True)
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(path), '-ac', '2', '-ar', '48000', '-c:a', 'pcm_s16le', str(wav)],
                           capture_output=True, check=True, timeout=120)
        if ident not in items:
            seconds = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(wav)],
                                           capture_output=True, text=True, timeout=30).stdout.strip() or 30)
            items[ident] = {'id': ident, 'name': path.stem, 'kind': 'music', 'tags': ['demo'], 'duration': round(seconds, 3),
                            'license': 'Cascade original', 'source': 'synthesized', 'demo': True}
    return items


def final_edit():
    """(video, plan) of the finished AI edit saved for the demo, or None."""
    video, plan = folder()/'final_edit.mp4', folder()/'final_plan.json'
    return (video, json.loads(plan.read_text())) if video.is_file() and plan.is_file() else None


DONE_TEXT = "Done! Here's your jaguar fan edit. Press play on the Edited view."


EDIT_SECONDS = float(os.getenv('CASCADE_DEMO_EDIT_SECONDS', '') or 5.8)   # how long the AI chat "works" before the edit shows
EDIT_STAGES = ((.1, 'Watching the clip…'), (.3, 'Planning the edit…'), (.55, 'Adding captions and B-roll…'), (.8, 'Rendering your edit…'))


def run_final_edit_later(folder_path, pid, jid, index, user, state, message, job, publish, write, done=None):
    """The AI chat in demo mode: show editing steps for EDIT_SECONDS (about 6 s), then the saved finished edit."""
    import threading
    def run():
        try:
            for amount, stage in EDIT_STAGES:
                job.update(status='running', progress=amount, stage=stage)
                write(Path(folder_path)/'job.json', job)
                time.sleep(EDIT_SECONDS/len(EDIT_STAGES))
            run_final_edit(folder_path, pid, jid, index, user, state, message, job, publish, write)
        finally:
            if done: done()
    thread = threading.Thread(target=run, daemon=True, name='cascade-demo-edit')
    thread.start()
    return thread


def run_final_edit(folder_path, pid, jid, index, user, state, message, job, publish, write):
    """The AI chat in demo mode: any request shows the saved finished edit straight away, as the clip's next version."""
    from backend.editor.ai_edit.beats import workflow
    from backend.media import probe_media
    try:
        video, plan = final_edit()
        data = workflow.save_version(folder_path, plan, message=message, kind='edit', critic_score=None, issues=(), notes=(), model='')
        out = Path(folder_path)/data['version']/'edited.mp4'
        _link(video, out)
        seconds = round(probe_media(out)['duration'], 3)
        publish(pid, jid, index, user, state, data['version'], seconds, DONE_TEXT, plan=workflow.ref(data))
        job.update(status='done', progress=1, stage='Done', version=data['version'], message=DONE_TEXT, finished=time.time())
    except Exception:
        import logging
        logging.getLogger(__name__).warning('demo edit failed', exc_info=True)
        job.update(status='failed', message='The edit could not be shown. Try again.', finished=time.time())
    write(Path(folder_path)/'job.json', job)


# ---------- Editor: Trend Analysis ----------

def saved_trends():
    """The trend analysis saved for the demo (demo_assets/<set>/trends.json), or None."""
    path = folder()/'trends.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def instant_trends(pid, jid, index, state, edit_version):
    """Any "Analyze" in demo mode: the saved YouTube research, finished at once, for the clip on screen."""
    import uuid
    saved = saved_trends()
    now = time.time()
    record = {key: saved[key] for key in ('source', 'topic', 'goal', 'topic_override', 'model', 'revision', 'added_references') if key in saved}
    record.update({'id': uuid.uuid4().hex, 'status': 'done', 'message': saved.get('message') or 'YouTube research ready; no edits applied.',
                   'project_id': pid, 'job_id': jid, 'clip_index': index, 'edit_version': edit_version,
                   'edit_state': state.model_dump(mode='json'), 'cache_key': 'demo', 'demo': True,
                   'started_at': now, 'researched_at': now, 'expires_at': now+30*24*3600,
                   'result': {**saved['result'], 'checked_at': now}})
    return record


# ---------- Export: publishing to YouTube ----------

YOUTUBE = {}   # clip key -> the published record, for this server run


def youtube_url():
    """The finished video on YouTube: CASCADE_DEMO_YOUTUBE_URL (upload the edit once yourself and put its link here)."""
    return os.getenv('CASCADE_DEMO_YOUTUBE_URL', '').strip() or 'https://www.youtube.com/'


def youtube_channel():
    return os.getenv('CASCADE_DEMO_YOUTUBE_CHANNEL', '').strip() or 'Cascade'


def youtube_published(privacy='public'):
    import re
    url = youtube_url()
    found = re.search(r'(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{6,})', url)
    return {'status': 'Published', 'url': url, 'video_id': found.group(1) if found else 'demo', 'upload_attempted': True,
            'privacy': privacy, 'channel': youtube_channel()}
