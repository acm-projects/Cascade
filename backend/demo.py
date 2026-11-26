"""Demo mode (the demo_final branch): the presentation-night hike demo, precomputed so it runs smoothly on stage.

When the Studio gets the hike recordings (recognised by their file names), Cascade skips the multi-gigabyte join and
the AI search and returns, in about 4 seconds, the 11 clips the finished edit uses. "Go to Editor" joins them from a
prebuilt file, and the first AI edit asked for on that joined clip returns, in about 8 seconds, the finished edit that
Cascade's planner and renderer made. Everything after that (preview, export, YouTube) is the app's normal code.
Set CASCADE_DEMO=0 to turn it off. Assets: demo/hike/.
"""
import json
import os
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent/'demo'/'hike'
STUDIO_SECONDS = 0.8   # (+ the upload request and the page's next check: about 4 s on screen)
EDIT_SECONDS = 6.5
TRENDS_SECONDS = 3.0   # Trends on the demo edit


def enabled():
    return os.getenv('CASCADE_DEMO', '1') != '0' and (ROOT/'clips.json').is_file()


def _load(name):
    return json.loads((ROOT/name).read_text())


def source_parts():
    return _load('source_parts.json')


def names():
    return {p['name'] for p in source_parts()}


def matches(filenames):
    """The files picked are the hike recordings (two or more of them, nothing else)."""
    picked = [Path(f or '').name for f in filenames]
    return enabled() and len(picked) >= 2 and all(name in names() for name in picked)


def is_demo_upload(owner):
    """A Studio job made from the hike recordings."""
    parts = (owner or {}).get('source_parts') or []
    return enabled() and len(parts) >= 2 and all(p.get('name') in names() for p in parts)


def stand_in():
    """The small file kept as the joined source (the real join of the recordings is ~19 GB of footage)."""
    return ROOT/'source_preview.mp4'


def _pace(steps, seconds, report):
    for i, message in enumerate(steps):
        report(message)
        time.sleep(seconds/len(steps))


def find_clips(job_id, folder, progress):
    """Studio: the clips the edit uses, as if found by the agent. Returns (clips, metadata)."""
    picked = _load('clips.json')['clips']
    _pace(['Reading uploaded video...', 'Transcribing the footage with Deepgram...', 'Searching the hike for the moments you asked for...',
           'Agent: checking the best moments...', 'Ranking the clips...', f'Cutting {len(picked)} clips...'], STUDIO_SECONDS*.85, progress)
    clips = []
    for n, clip in enumerate(picked, start=1):
        shutil.copyfile(ROOT/f'clip_{n}.mp4', folder/f'clip_{n}.mp4')
        shutil.copyfile(ROOT/f'clip_{n}.vtt', folder/f'clip_{n}.vtt')
        clips.append({**clip, 'clip_id': f'{job_id}:{n-1}', 'media_kind': 'video', 'has_video': True, 'storage': 'local',
                      'backup_state': 'local', 'encode_seconds': 0.1,
                      'clip_url': f'/clips/{job_id}/clip_{n}.mp4', 'captions_url': f'/clips/{job_id}/clip_{n}.vtt'})
    time.sleep(STUDIO_SECONDS*.15)
    return clips, {'model': 'cascade-agent', 'provider': 'openai', 'requested_clip_count': len(clips), 'backup_state': 'local'}


def is_demo_combine(refs, owners):
    """Go to Editor with clips picked from a demo Studio job."""
    return enabled() and bool(refs) and all(is_demo_upload(o) for o in owners)


def combined_file():
    return ROOT/'combined.mp4'


def combined_parts():
    return _load('combined_parts.json')


def edit(out, progress):
    """AI edit: the finished edit, paced like a render. Writes out/edited.mp4 and the project; returns (plan, report)."""
    from backend.editor.ai_edit.cinema import visual
    _pace(['Getting the clip ready…', 'Transcribing what is said…', 'Watching the clip and planning the edit…',
           'Picking the shots on the beat…', 'Building the collage and transitions…', 'Adding titles and captions…',
           'Mixing the music under your voices…', 'Rendering the finished edit…'],
          EDIT_SECONDS, lambda s, k=iter(range(100)): progress(min(.95, .05+next(k)*.12), s))
    shutil.copyfile(ROOT/'edited.mp4', out/'edited.mp4')
    plan = visual.VisualPlan.model_validate_json((ROOT/'plan.json').read_text())
    return plan, _load('report.json')


def trends_result(jid):
    """Trends on the demo edit: the research Cascade made on it (demo/hike/trends.json), or None."""
    from backend.core import jobs as job_service
    if not enabled() or not (ROOT/'trends.json').is_file(): return None
    try:
        if not job_service.load_json(job_service.JOBS_DIR/jid/'owner.json').get('demo'): return None
        saved = _load('trends.json')
    except Exception:
        return None
    return saved if saved.get('result') else None


def start_trends(pid, jid, index, state, edit_version, root, put, running, ttl):
    """Trends on the demo edit: a research record that finishes with the saved result after TRENDS_SECONDS."""
    import threading
    import uuid
    saved = trends_result(jid)
    record = {**{k: v for k, v in saved.items() if k not in ('result', 'fresh')}, 'id': uuid.uuid4().hex, 'status': 'running',
              'message': 'Searching YouTube for hiking and camping friendship edits…', 'project_id': pid, 'job_id': jid,
              'clip_index': index, 'edit_version': edit_version, 'edit_state': state.model_dump(mode='json'), 'started_at': time.time()}
    running.add(record['id']); put(root, record)

    def finish():
        time.sleep(TRENDS_SECONDS/2)
        record['message'] = f"Comparing your edit with {len(saved['result'].get('references', []))} memorable friendship and trip edits…"
        put(root, record)
        time.sleep(TRENDS_SECONDS/2)
        record.update(status='done', result={**saved['result'], 'state': state.model_dump(mode='json')},
                      message='YouTube research ready; no edits applied.', researched_at=time.time(), expires_at=time.time()+ttl)
        put(root, record); running.discard(record['id'])
    threading.Thread(target=finish, daemon=True).start()
    return record
