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

def _created(job_id):
    try:
        return job_service.load_json(job_service.JOBS_DIR/job_id/'owner.json').get('created_at', 0)
    except Exception:
        return 0


def ordered_picks(chosen):
    """Picked clips (not already-joined ones) in story order: oldest generation first, then clip 1, 2, 3…"""
    picks = []
    for ref in chosen:
        try:
            kind = job_service.load_json(job_service.JOBS_DIR/ref['job_id']/'owner.json').get('kind')
        except Exception:
            continue
        if kind != 'combined' and (ref['job_id'], ref['clip_index']) not in [(p['job_id'], p['clip_index']) for p in picks]:
            picks.append({'job_id': ref['job_id'], 'clip_index': ref['clip_index']})
    return sorted(picks, key=lambda r: (_created(r['job_id']), r['clip_index']))


def existing(pid, user, picks):
    """The joined clip already made from exactly these picks, if any."""
    from backend.services import projects_store
    want = [(p['job_id'], p['clip_index']) for p in picks]
    for job in projects_store.project_jobs(pid, user):
        if job['kind'] != 'combined': continue
        owner = job_service.load_json(job_service.JOBS_DIR/job['job_id']/'owner.json')
        made = [(p['job_id'], p['clip_index']) for p in owner.get('combined_from', [])]
        if made == want and (job_service.JOBS_DIR/job['job_id']/'clip_1.mp4').is_file():
            return {'job_id': job['job_id'], 'clip_index': 0}
    return None


def editor_clips(pid, request):
    """The joined clip for the current picks (made now if needed), or None when fewer than two clips are picked."""
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
