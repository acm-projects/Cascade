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
# the first prompt shows 5 of the edit's 11 clips; "find more like it" (a branch) shows the other 6
FIRST = [0, 1, 2, 9, 10]          # the intro, the waterfall, the waving, the hands-in, CASCADE on the rock
BRANCH = [3, 4, 5, 6, 7, 8]       # the bench, filming, the laugh, the red coat, the spin, the hug
STUDIO_SECONDS = 0.8   # (+ the upload request and the page's next check: about 4 s on screen)
EDIT_SECONDS = 6.5
TRENDS_SECONDS = 3.0   # Trends on the demo edit


def enabled():
    return os.getenv('CASCADE_DEMO', '1') != '0' and (ROOT/'clips.json').is_file()


def _load(name):
    return json.loads((ROOT/name).read_text())


def source_parts():
    return _load('source_parts.json')


# every other recording in the hike's source folders (the phone clips, first/second, ...): picking them too is the demo
EXTRA_NAMES = [
    "IMG_6227.MOV",
    "IMG_6228.MOV",
    "IMG_6229.MOV",
    "IMG_6230.MOV",
    "IMG_6231.MOV",
    "IMG_6232.MOV",
    "IMG_6233.MOV",
    "Video_1074791040_DJI_20261125102035_0010_D_MP4_62719618_7000_20261125102034_video_original.MP4",
    "Video_1074791104_DJI_20261125102240_0011_D_MP4_71868583_8000_20261125102240_video_original.MP4",
    "Video_1074791296_DJI_20261125102550_0014_D_MP4_1016579242_119000_20261125102550_video_original.mov",
    "Video_1074791360_DJI_20261125102815_0015_D_MP4_133962978_15000_20261125102814_video_original.MP4",
    "first.MP4",
    "second.MOV",
]


def names():
    return {p['name'] for p in source_parts()} | set(EXTRA_NAMES)


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
    return ROOT/'combined.mp4'   # the edit's clips joined, full quality (branches search it for real)


def stand_in_parts():
    """Where each clip sits in the stand-in source, as recordings the clip search keeps clips inside."""
    return [{'name': p['title'], 'start': p['from'], 'end': p['to']} for p in combined_parts()]


def _pace(steps, seconds, report):
    for i, message in enumerate(steps):
        report(message)
        time.sleep(seconds/len(steps))


def find_clips(job_id, folder, progress, branch=False):
    """Studio: the clips the edit uses, as if found by the agent (branch=True: the "more like these" moments a branch
    finds, from demo/hike/branch). Returns (clips, metadata)."""
    root = ROOT
    every = json.loads((root/'clips.json').read_text())['clips']
    chosen = BRANCH if branch else FIRST   # (which of the edit's clips each round shows: 5, then the other 6)
    picked = [every[i] for i in chosen]
    _pace(['Reading the clips you picked...', 'Searching the hike for more moments like them...', 'Agent: checking the best matches...',
           f'Cutting {len(picked)} clips...'] if branch else
          ['Reading uploaded video...', 'Transcribing the footage with Deepgram...', 'Searching the hike for the moments you asked for...',
           'Agent: checking the best moments...', 'Ranking the clips...', f'Cutting {len(picked)} clips...'], STUDIO_SECONDS*.85, progress)
    clips = []
    where = combined_parts()   # (times inside the stand-in source, so the Editor agrees with them)
    for n, (i, clip) in enumerate(zip(chosen, picked), start=1):
        clip = {**clip, 'start': where[i]['from'], 'end': where[i]['to'], 'edit_index': i}
        shutil.copyfile(root/f'clip_{i+1}.mp4', folder/f'clip_{n}.mp4')
        shutil.copyfile(root/f'clip_{i+1}.vtt', folder/f'clip_{n}.vtt')
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
