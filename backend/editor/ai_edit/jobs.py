"""Run an edit in the background, tied to its clip, and attach the result to that clip's draft.

Starting a job only records it; the chat answers at once and the Editor polls. A failed job leaves
the last working edit in place and says why in the chat. Versions are kept so a revision can go back.
"""
import json
import logging
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from fastapi import HTTPException

from . import director, layout as layouts, page, picture, prep as preparation, sound, tools
from .models import Plan, check

LOG = logging.getLogger(__name__)
RUNNING = {}
GUARD = threading.Lock()
RENDER_SLOT = threading.BoundedSemaphore(1)  # one heavy edit at a time; others show as queued
EDIT_REQUEST = re.compile(r'\b(edit|recut|re-cut)\s+(this|it|the|my)\b|\bmake\s+(this|it)\s+(into\s+)?(a|an)\b|\b(reels?|tiktok|shorts)\b|\bcut\s+(this|it)\s+(down|into)\b|\b(trailer|montage)\b', re.I)
GO_BACK = re.compile(r'^\s*(undo( (your|the) last (ai )?(edit|change))?|go back|previous version|revert( that)?)\b[\s.!]*$', re.I)
ASSETS = Path(__file__).parent/'assets'


def root(pid, jid, index, user):
    from ..storage import draft_path
    return draft_path(pid, jid, index, user).parent/'ai-edits'/f'{jid}-{index}'


def _read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _write(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(data)); temp.replace(path)


def job_status(folder):
    job = _read(Path(folder)/'job.json')
    if job and job['status'] in ('queued', 'running') and str(folder) not in RUNNING:
        job.update(status='failed', message='The server restarted while this edit was running. Send the request again.', finished=time.time())
        _write(Path(folder)/'job.json', job)
    return job


def versions(folder):
    return _read(Path(folder)/'versions.json', [])


def rendered_path(pid, jid, index, user, version):
    if not re.fullmatch(r'v[0-9]{3}', version): raise HTTPException(422, 'Unknown edit version.')
    path = root(pid, jid, index, user)/version/'edited.mp4'
    if not path.is_file(): raise HTTPException(409, 'This edited version is no longer on this machine. Ask the AI Editor to edit the clip again.')
    return path


def wants(body, info):
    """Whether this chat turn belongs to the finished-edit workflow."""
    if body.research_id or not info.get('has_video', True) or re.search(r'storyboard', body.message, re.I): return False
    from ..ai import claude_plan
    if not claude_plan(): return False
    return bool(body.state.ai_edit) or bool(EDIT_REQUEST.search(body.message))


def _reply(state, message, job=None):
    return {'state': state.model_dump(), 'message': message[:4000], 'report': [], 'unsupported': [], 'actions': [], 'ai_job': job,
            'analysis': {'provider': 'Claude (your Claude plan)', 'model': None, 'planning_method': 'finished edit', 'sampled_frames': [], 'observations': [], 'transcript_cues': 0,
                         'limitation': 'Claude watches contact sheets and reads the transcript. It cannot hear the audio.'}}


def turn(pid, jid, index, user, clip, body, info, stock, audio_store):
    folder = root(pid, jid, index, user)
    job = job_status(folder)
    if job and job['status'] in ('queued', 'running'):
        return _reply(body.state, 'Still working on your last request for this clip. I will take the next change as soon as it finishes.', job)
    current = body.state.ai_edit
    if current and GO_BACK.search(body.message):
        history = versions(folder)
        names = [v['version'] for v in history]
        if current.version not in names or names.index(current.version) == 0:
            return _reply(body.state, 'This is the first version of the edit, so there is nothing earlier to go back to.')
        earlier = history[names.index(current.version)-1]
        state = body.state.model_copy(update={'ai_edit': type(current)(version=earlier['version'], duration=earlier['duration'])})
        return _reply(state, f"Back to {earlier['version']} ({earlier['request'][:80]}). Your later version is still saved.")
    job = {'id': uuid.uuid4().hex, 'status': 'queued', 'progress': 0, 'stage': 'Waiting for another edit to finish…', 'kind': 'revision' if current else 'edit',
           'request': body.message[:500], 'version': None, 'message': '', 'started': time.time(), 'finished': None}
    _write(folder/'job.json', job)
    args = (folder, pid, jid, index, user, clip, info, body.state.model_copy(deep=True), [m.model_dump() for m in body.chat], body.message, stock, audio_store, job)
    thread = threading.Thread(target=_run, args=args, daemon=True, name='cascade-ai-edit')
    with GUARD: RUNNING[str(folder)] = thread
    thread.start()
    verb = 'Changing the edit' if current else 'Editing this clip'
    return _reply(body.state, f'{verb} now. Claude is directing it on your Claude plan, at no extra cost. You can keep working or switch clips; it stays tied to this clip and will appear in the Edited preview when it is ready.', job)


def _run(folder, pid, jid, index, user, clip, info, state, chat, message, stock, audio_store, job):
    from ..storage import media

    def progress(amount, stage):
        job.update(status='running', progress=round(amount, 3), stage=stage)
        _write(folder/'job.json', job)

    try:
        with RENDER_SLOT, media(jid, clip) as source:
            progress(.02, 'Getting the clip ready…')
            prep_dir = folder/'prep'
            prep = preparation.prepare(source, info.get('cues', []), prep_dir, progress)
            windows = _windows(state)
            summary = json.dumps({k: v for k, v in state.model_dump().items() if k in ('start', 'end', 'timeline', 'texts', 'dialogue_volume')})[:4000]
            assets = _assets(state, audio_store)
            current = None
            if state.ai_edit:
                saved = _read(folder/state.ai_edit.version/'plan.json')
                current = Plan.model_validate(saved) if saved else None
            progress(.34, 'Claude is watching the clip and planning the edit…' if not current else 'Claude is revising the edit…')
            if current:
                plan = director.revise(message, current, prep_dir, prep, summary, windows, assets, chat)
            else:
                plan = director.plan_edit(message, prep_dir, prep, summary, windows, assets, chat)
            name = _next_version(folder)
            out = folder/name; out.mkdir(parents=True, exist_ok=True)
            _write(out/'plan.json', plan.model_dump())  # kept even if a later step fails, for diagnosis
            track = _track(state, audio_store, plan)
            result = _render(plan, source, prep, prep_dir, folder, out, stock, track, progress)
            problems, fixed = [], False
            try:
                progress(.92, 'Claude is checking the finished picture…')
                problems, fixes = director.review(_review_sheet(result, out), result['table'], plan, prep_dir, prep, windows)
                revised = _apply_fixes(plan, fixes, prep, windows)
                if revised:
                    progress(.93, 'Fixing what the check found…')
                    plan = revised
                    result = _render(plan, source, prep, prep_dir, folder, out, stock, track, lambda a, s: progress(.93+(a-.5)*.1, s))
                    fixed = True
            except HTTPException as exc:  # the edit is already good; the check is a bonus
                LOG.info('review skipped: %s', exc.detail)
            shutil.rmtree(out/'project', ignore_errors=True)
            _write(out/'plan.json', plan.model_dump())
            report = {**result['metrics'], 'problems': problems, 'fixed': fixed, 'notes': result['notes']}
            _write(out/'report.json', report)
            history = [*versions(folder), {'version': name, 'title': plan.title, 'request': message[:500], 'duration': result['duration'], 'created': time.time()}]
            _write(folder/'versions.json', history)
            text = _message(plan, name, report)
            _publish(pid, jid, index, user, state, name, result['duration'], text)
            job.update(status='done', progress=1, stage='Done', version=name, duration=result['duration'], message=text, finished=time.time())
            _write(folder/'job.json', job)
    except Exception as exc:  # any failure is told in the chat, and the last edit keeps playing
        why = getattr(exc, 'detail', None) or str(exc) or exc.__class__.__name__
        LOG.warning('AI edit failed', exc_info=True)
        if not isinstance(exc, (HTTPException, ValueError)): why = 'Something went wrong while making this edit. Try the request again.'
        text = f'NOT CHANGED: {str(why)[:600]}'+(' The last working edit is still in place.' if state.ai_edit else '')
        _publish(pid, jid, index, user, state, None, None, text)
        job.update(status='failed', message=text, finished=time.time())
        _write(folder/'job.json', job)
    finally:
        with GUARD: RUNNING.pop(str(folder), None)


def _windows(state):
    if state.timeline:
        spans = [[max(state.start, s.start), min(state.end, s.end)] for s in state.timeline]
        return [[round(a, 2), round(b, 2)] for a, b in spans if b > a]
    return [[round(state.start, 2), round(state.end, 2)]]


def _assets(state, audio_store):
    try:
        library = [{'id': a['id'], 'name': a.get('name'), 'kind': a.get('kind')} for a in audio_store.library() if a.get('source') != 'synthesized']
    except Exception:
        library = []
    return {'audio_library': library[:20], 'music_already_on_the_clip': [a.asset_id for a in state.audio][:6], 'stock_shots_already_on_the_clip': [b.asset.source_url for b in state.broll][:10]}


def _track(state, audio_store, plan):
    """A music track the user put on this clip is used instead of composing, and the edit follows its tempo."""
    if plan.mood == 'none': return None
    try:
        music = {a['id'] for a in audio_store.library() if a.get('kind') == 'music' and a.get('source') != 'synthesized'}
        chosen = next((a.asset_id for a in state.audio if a.asset_id in music), None)
        if not chosen: return None
        from ..beats import analyze
        path = audio_store.media(chosen)
        measured = analyze(path)
        if measured.get('bpm'): plan.bpm = int(min(120, max(56, round(measured['bpm']))))
        return str(path), float((measured.get('beats') or [0])[0])
    except Exception:
        LOG.info('could not use the clip music', exc_info=True)
        return None


def _next_version(folder):
    used = [int(p.name[1:]) for p in Path(folder).glob('v[0-9][0-9][0-9]') if (p/'edited.mp4').is_file()]
    return f'v{max(used, default=0)+1:03d}'


def _hyperframes(project, *args, timeout=1500):
    import os
    env = {**os.environ, 'PATH': os.environ.get('PATH', '')+':/usr/local/bin:/opt/homebrew/bin'}
    return subprocess.run(['npx', '--yes', tools.HYPERFRAMES, *args], cwd=project, capture_output=True, text=True, timeout=timeout, env=env)


def _render(plan, source, prep, prep_dir, folder, out, stock, track, progress):
    layout = layouts.build(plan, prep['words'])
    project = out/'project'
    shutil.rmtree(project, ignore_errors=True)
    (project/'assets'/'fonts').mkdir(parents=True)
    for font in (ASSETS/'fonts').iterdir(): shutil.copy2(font, project/'assets'/'fonts'/font.name)
    shutil.copy2(ASSETS/'hyperframes.json', project/'hyperframes.json')
    (project/'meta.json').write_text(json.dumps({'id': 'cascade-ai-edit', 'name': plan.title}))
    (project/'package.json').write_text(json.dumps({'name': 'cascade-ai-edit', 'private': True, 'type': 'module'}))
    uses_planet = plan.mode == 'earth' and any(e.kind == 'dot' and e.part not in ('loss', 'cost') for e in layout.events)
    if uses_planet: shutil.copy2(ASSETS/'earth.mp4', project/'assets'/'earth.mp4')
    notes = []
    progress(.5, 'Cutting the picture…')
    picture.cut(layout.events, source, prep, folder/'parts', project/'assets'/'plate.mp4', stock, notes)
    has_closing = layout.closing is not None and plan.closing_src is not None
    if has_closing: picture.closing(source, plan.closing_src, plan.closing_cx, prep, project/'assets'/'closing.mp4')
    credits = [c for c in ([plan.credit] if plan.credit else [])]
    if uses_planet: credits.append('Earth: NASA DSCOVR EPIC.')
    if any(e.kind == 'stock' for e in layout.events) and not notes: credits.append('Stock footage: Pexels.')
    document, dots = page.build(plan, layout, has_closing, True, credits)
    progress(.62, 'Composing the music and mixing…')
    numbers = sound.mix(plan, layout, prep_dir, prep, dots, project/'assets'/'mix.wav', track)
    (project/'index.html').write_text(document)
    progress(.7, 'Checking the composition…')
    checked = _hyperframes(project, 'check', '--json', timeout=300)
    if '"errorCount": 0' not in checked.stdout and checked.returncode: 
        LOG.warning('render check: %s', checked.stdout[-600:])
        raise ValueError('The edit did not pass its render check.')
    progress(.74, 'Rendering the finished video…')
    final = project/'final.mp4'
    run = _hyperframes(project, 'render', '--quality', 'looks', '-o', 'final.mp4')
    if run.returncode or not final.is_file():
        LOG.warning('render: %s', (run.stderr or run.stdout)[-600:])
        raise ValueError('The render failed. Try the request again.')
    finished = out/'edited.mp4.part'
    muxed = subprocess.run([tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-i', str(final), '-i', str(project/'assets'/'mix.wav'), '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k',
                            '-movflags', '+faststart', '-shortest', '-f', 'mp4', str(finished)], capture_output=True, text=True, timeout=300)
    if muxed.returncode: raise ValueError('I could not finish the video file.')
    finished.replace(out/'edited.mp4')
    duration = preparation.probe(out/'edited.mp4')['duration']
    # numbers the sheet asks to report
    cuts = [e.start for e in layout.events[1:]]
    grid = lambda t, step=1: abs(t/(layout.beat*step)-round(t/(layout.beat*step)))*layout.beat*step <= 2/30
    graphic = sum(e.end-e.start for e in layout.events if e.kind in ('ink', 'dot'))
    words = sum(len(l['words']) for l in layout.lines)
    numbers.update(seconds=round(duration, 1), cuts=len(cuts), cuts_per_minute=round(len(cuts)/duration*60), cuts_on_beat=sum(grid(c) for c in cuts), cuts_on_half_beat=sum(grid(c, .5) for c in cuts),
                   bpm=plan.bpm, graphics_share=round(graphic/duration*100), words_per_minute=round(words/duration*60), voice_isolated=prep['isolated'])
    return {'layout': layout, 'metrics': numbers, 'notes': notes, 'duration': round(duration, 3), 'table': _table(layout)}


def _table(layout):
    rows = []
    for n, e in enumerate(e for e in layout.events if e.end-e.start > .3):
        rows.append(f'{n}: {(e.start+e.end)/2:.1f}s line {e.line} shot {e.shot} {e.kind} {e.note}')
    return '\n'.join(rows[:48])


def _review_sheet(result, out):
    """The numbered frames, and the top of each one enlarged, where stray logos hide."""
    picks = [round((e.start+e.end)/2*30) for e in result['layout'].events if e.end-e.start > .3][:48]
    select = '+'.join(f'eq(n\\,{p})' for p in picks)
    label = "drawtext=text='%{eif\\:selected_n\\:d}':x=6:y=6:fontsize=26:fontcolor=white:box=1:boxcolor=black"
    sheets = []
    for name, shape in (('review.jpg', f'scale=240:-2,{label},tile=8x6'), ('tops.jpg', f'crop=iw:ih*.11:0:0,scale=480:-2,{label},tile=4x12')):
        sheet = out/name
        filters = f"select='{select}',{shape}"
        run = subprocess.run([tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-i', str(out/'edited.mp4'), '-vf', filters, '-fps_mode', 'vfr', '-frames:v', '1', '-q:v', '4', str(sheet)], capture_output=True, text=True, timeout=300)
        if run.returncode or not sheet.is_file(): raise HTTPException(503, 'Could not build the review frames.')
        sheets.append((name, sheet.read_bytes()))
    return sheets


def _apply_fixes(plan, fixes, prep, windows):
    """The plan with Claude's corrections, or None if nothing valid was asked for."""
    if not fixes: return None
    data = plan.model_dump()
    changed = False
    for fix in fixes:
        try:
            shot = data['lines'][int(fix['line'])]['shots'][int(fix['shot'])]
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        for key in ('src', 'cx', 'kind', 'query'):
            if fix.get(key) is not None and fix[key] != shot.get(key):
                shot[key] = fix[key]; changed = True
    if not changed: return None
    try:
        revised = Plan.model_validate(data)
        check(revised, prep['words'], windows)
        return revised
    except ValueError:
        return None


def _message(plan, name, report):
    lines = [plan.reply or f'{plan.title} is ready.', '',
             f"{name} · {report['seconds']} s · {report['cuts_per_minute']} cuts a minute · {report['cuts_on_beat']}/{report['cuts']} cuts on a beat ({report['cuts_on_half_beat']} counting half beats) · "
             f"{report['effects_on_beat']}/{report['effects']} effects on a beat · {report['lufs']} LUFS, peak {report['peak']} dB."]
    if report.get('fixed'): lines.append('My check of the finished frames found problems, and I re-cut them: '+'; '.join(report['problems'])[:400])
    elif report.get('problems'): lines.append('Worth a look: '+'; '.join(report['problems'])[:400])
    if report.get('notes'): lines.append('Note: '+'; '.join(sorted(set(report['notes'])))[:300])
    if not report.get('voice_isolated', True): lines.append('The voices could not be separated from the clip\'s own sound, so any music in the clip remains under them.')
    lines.append('I can see the frames but cannot hear it, so please judge the sound. Ask for any change here.')
    return '\n'.join(lines)[:4000]


def _publish(pid, jid, index, user, state, version, duration, text):
    """Save the result, retrying through a brief database outage so a finished edit is not lost."""
    for attempt in range(6):
        try:
            return _save_result(pid, jid, index, user, state, version, duration, text)
        except HTTPException:
            if attempt == 5: raise
            time.sleep(5*(attempt+1))


def _save_result(pid, jid, index, user, state, version, duration, text):
    """Attach the result to the saved draft, keeping anything the user changed while it ran."""
    from backend.services.projects_store import lock
    from ..models import AIEditRef, Draft
    from ..runtime import load_json, metadata_exists, save_json
    from ..storage import draft_path
    path = draft_path(pid, jid, index, user)
    with lock:
        draft = None
        if metadata_exists(path):
            try:
                draft = Draft.model_validate(load_json(path))
            except ValueError:
                draft = None
        draft = draft or Draft(state=state)
        if version: draft.state.ai_edit = AIEditRef(version=version, duration=duration)
        draft.chat = [*draft.chat, {'role': 'assistant', 'text': text[:4000]}][-200:]
        path.parent.mkdir(parents=True, exist_ok=True)
        save_json(path, draft.model_dump())


def status(pid: str, jid: str, index: int, request):
    from ..storage import draft_path, selected
    from ..models import Draft
    from ..runtime import load_json, metadata_exists
    user = request.state.user_id
    selected(pid, jid, index, user)
    folder = root(pid, jid, index, user)
    job = job_status(folder)
    draft = {}
    path = draft_path(pid, jid, index, user)
    if job and job['status'] in ('done', 'failed') and metadata_exists(path):
        try:
            saved = Draft.model_validate(load_json(path))
            draft = {'chat': [m.model_dump() for m in saved.chat], 'ai_edit': saved.state.ai_edit.model_dump() if saved.state.ai_edit else None}
        except ValueError:
            draft = {}
    return {'job': job, 'versions': versions(folder), 'saved': draft}


