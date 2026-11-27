"""Run an edit in the background, tied to its clip, and attach the result to that clip's draft.

Starting a job only records it; the chat answers at once and the Editor polls. A failed job leaves
the last working edit in place and says why in the chat. Versions are kept so a revision can go back.
"""
import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import HTTPException

from . import prep as preparation, tools

LOG = logging.getLogger(__name__)
RUNNING = {}
GUARD = threading.Lock()
RENDER_SLOT = threading.BoundedSemaphore(1)  # one heavy edit at a time; others show as queued
GO_BACK = re.compile(r'^\s*(undo( (your|the) last (ai )?(edit|change))?|go back|previous version|revert( that)?)\b[\s.!]*$', re.I)


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


def _reply(state, message, job=None):
    return {'state': state.model_dump(), 'message': message[:4000], 'report': [], 'unsupported': [], 'actions': [], 'ai_job': job,
            'analysis': {'provider': 'openai', 'model': None, 'planning_method': 'finished edit', 'sampled_frames': [], 'observations': [], 'transcript_cues': 0,
                         'limitation': 'OpenAI reads contact sheets and reads the transcript. It cannot hear the audio.'}}


def turn(pid, jid, index, user, clip, body, info, stock, audio_store):
    folder = root(pid, jid, index, user)
    job = job_status(folder)
    if job and job['status'] in ('queued', 'running'):
        return _reply(body.state, 'Still working on your last request for this clip. I will take the next change as soon as it finishes.', job)
    current = body.state.ai_edit
    if current and GO_BACK.search(body.message):
        history = [v for v in versions(folder) if v.get('engine') != 'beats']   # old beat plans have no film to go back to
        names = [v['version'] for v in history]
        if current.version not in names or names.index(current.version) == 0:
            return _reply(body.state, 'This is the first version of the edit, so there is nothing earlier to go back to.')
        earlier = history[names.index(current.version)-1]
        state = body.state.model_copy(update={'ai_edit': type(current)(version=earlier['version'], duration=earlier['duration'])})
        return _reply(state, f"Back to {earlier['version']} ({earlier['request'][:80]}). Your later version is still saved.")
    job = {'id': uuid.uuid4().hex, 'status': 'queued', 'progress': 0, 'stage': 'Waiting for another edit to finish…', 'kind': 'revision' if current else 'edit',
           'request': body.message[:500], 'version': None, 'message': '', 'started': time.time(), 'finished': None}
    _write(folder/'job.json', job)
    args = (folder, pid, jid, index, user, clip, info, body.state.model_copy(deep=True), [m.model_dump() for m in body.chat], body.message, stock, job)
    thread = threading.Thread(target=_run_cinema, args=args, daemon=True, name='cascade-ai-edit')
    with GUARD: RUNNING[str(folder)] = thread
    thread.start()
    verb = 'Changing the edit' if current else 'Editing this clip'
    return _reply(body.state, f'{verb} now. You can keep working or switch clips. It will show up in the Edited preview when it is ready.', job)


def _run_cinema(folder, pid, jid, index, user, clip, info, state, chat, message, stock, job):
    """The Cinema engine (cinema/), the only edit engine. OpenAI (cinema/planner.py) or the rule-based director
    decides the plan; the engine renders it. Simple follow-ups change the saved project with no AI at all."""
    from ..storage import media
    from .cinema import broll, engine, planner, project, revise, visual

    def progress(amount, stage):
        job.update(status='running', progress=round(amount, 3), stage=stage)
        _write(folder/'job.json', job)

    def finish(status, text, **more):
        job.update(status=status, message=text, finished=time.time(), **more)
        _write(folder/'job.json', job)
    try:
        from backend import demo
        from backend.core import jobs as job_service
        try: demo_clip = demo.enabled() and job_service.load_json(job_service.JOBS_DIR/jid/'owner.json').get('demo')
        except Exception: demo_clip = False
        if demo_clip and not state.ai_edit:   # demo mode: the finished hike edit
            name = _next_version(folder)
            out = folder/name; out.mkdir(parents=True, exist_ok=True)
            plan, report = demo.edit(out, progress)
            duration = preparation.probe(out/'edited.mp4')['duration']
            project.save(out, plan, dict(report), 'openai', message, {'job': jid, 'clip': index, 'duration': duration, 'credits': []})
            report.pop('timeline', None)
            _write(out/'report.json', report)
            _write(folder/'versions.json', [*versions(folder), {'version': name, 'title': plan.title, 'request': message[:500], 'duration': duration, 'created': time.time()}])
            text = '\n'.join([plan.reply or f'{plan.title} is ready.', '',
                               f"{name} · {report['seconds']} s · {report['size']} · visual edit, {report['pieces']} shots · {report['lufs']} LUFS · planned by openai.",
                               'Ask for any change here.'])[:4000]
            _publish(pid, jid, index, user, state, name, duration, text)
            return finish('done', text, progress=1, stage='Done', version=name, duration=duration)
        with RENDER_SLOT, media(jid, clip) as source:
            progress(.02, 'Getting the clip ready…')
            prep_dir = folder/'prep'
            prep = preparation.prepare(source, info.get('cues', []), prep_dir, progress, speech_optional=True)
            windows = _windows(state)
            speechless = not prep['words']   # nobody speaks: a visual edit planned from the frames and the motion
            # a music-led montage (friends, a trip, an Insta or trend edit): the same visual edit, with talking shots
            montage = not speechless and planner.wants_montage(message)
            try:   # a clip joined from several Studio picks: tell the planner which part is which
                from backend.core import jobs as job_service
                owner = job_service.load_json(job_service.JOBS_DIR/jid/'owner.json')
                if owner.get('parts'): prep = {**prep, 'parts': owner['parts']}
            except Exception:
                pass
            if montage and not prep.get('motion'):
                prep = {**prep, 'motion': preparation.motion(source)}
            current = project.load(folder/state.ai_edit.version) if state.ai_edit else None
            notes = []
            from .cinema import reference
            if current is None and len(reference.rows(message)) >= 8:   # a reference edit's shot list: followed exactly
                progress(.3, 'Gathering the moments your shot list names…')
                plan = reference.plan_request(message, folder/'reference.mp4', tools.ffmpeg())
                source, who, prep = folder/'reference.mp4', 'reference', {**prep, 'words': []}
            elif current is None:
                progress(.3, 'Watching the clip and planning the edit…')
                plan, who = (planner.plan_visual if speechless or montage else planner.plan_edit)(message, prep_dir, prep, windows, chat)
                if who == 'rules' and planner.choice() != 'rules':
                    notes.append("No AI planner was available, so Cascade's built-in director made this cut. Configure OpenAI for a story-led edit.")
            else:
                plan, done, left = revise.apply(message, current)   # switches and simple timeline changes need no AI
                who = 'no AI needed'
                if left or not done:
                    progress(.3, 'Planning the change…')
                    try:
                        plan, who = planner.revise(message, plan, prep_dir, prep, windows, chat)
                    except planner.Unavailable as exc:
                        if not done:   # nothing we can do without a planner: keep the draft exactly as it is
                            text = (f'NOT CHANGED: this change needs the AI planner, which is not available right now ({exc}) '
                                    'Your edit is saved and still plays and exports. Without the planner you can still ask for: reel or original shape, '
                                    'music up, down or off, captions on or off, less or no b-roll, a new title or closing message in quotes, shorter, or no sign-off.')
                            _publish(pid, jid, index, user, state, None, None, text)
                            return finish('failed', text)
                        notes.append('Not done, because the AI planner is not available right now: '+'; '.join(left)+'.')
                if done: notes.insert(0, 'Changed: '+', '.join(done)+'.')
            name = _next_version(folder)
            out = folder/name; out.mkdir(parents=True, exist_ok=True)
            composition = getattr(state, 'composition', None)
            ratio = getattr(composition, 'ratio', 'original') or 'original'   # the clip's own shape unless the user picked one (Reel = 9:16)
            local = [tools.folder()/'B-roll', tools.folder()/'Raw Footage']
            find = broll.resolver(stock, local)
            if isinstance(plan, visual.VisualPlan):
                report = visual.make(source, plan, out/'edited.part.mp4', lambda a, s: progress(.36+a*.6, s), tools.ffmpeg(), ratio=ratio,
                                     words=prep['words'])
            else:
                report = engine.make(source, prep['words'], plan, out/'edited.part.mp4', prep['cuts'], find,
                                     lambda a, s: progress(.36+a*.6, s), tools.ffmpeg(), ratio=ratio)
            (out/'edited.part.mp4').replace(out/'edited.mp4')
            duration = preparation.probe(out/'edited.mp4')['duration']
            report.update(directed=who)
            if report.get('song'): notes.append(report['song']+' Put this credit in your post caption.')
            project.save(out, plan, dict(report), who, message, {'job': jid, 'clip': index, 'duration': prep['duration'], 'credits': find.credits})
            report.pop('timeline', None)
            _write(out/'report.json', report)
            history = [*versions(folder), {'version': name, 'title': plan.title, 'request': message[:500], 'duration': duration, 'created': time.time()}]
            _write(folder/'versions.json', history)
            text = '\n'.join([(plan.reply if current is None or who not in ('no AI needed',) else '') or f'{plan.title} is ready.', *notes, '',
                               (f"{name} · {report['seconds']} s · {report['size']} · visual edit, {report['pieces']} shots · {report['lufs']} LUFS · planned by {who}."
                                if report.get('visual') else
                                f"{name} · {report['seconds']} s · {report['size']} · cut {report['removed_fillers']} ums and stumbles"
                                f"{', '+str(report['removed_interjections'])+' interjections' if report['removed_interjections'] else ''} · "
                                f"{report['broll']} b-roll shots · {report['lufs']} LUFS · planned by {who}."),
                               'Ask for any change here.'])[:4000]
            _publish(pid, jid, index, user, state, name, duration, text)
            finish('done', text, progress=1, stage='Done', version=name, duration=duration)
    except Exception as exc:
        why = getattr(exc, 'detail', None) or str(exc) or exc.__class__.__name__
        LOG.warning('Cinema edit failed', exc_info=True)
        if not isinstance(exc, (HTTPException, ValueError)): why = 'Something went wrong while making this edit. Try the request again.'
        text = f'NOT CHANGED: {str(why)[:600]}'+(' The last working edit is still in place.' if state.ai_edit else '')
        _publish(pid, jid, index, user, state, None, None, text)
        finish('failed', text)
    finally:
        with GUARD: RUNNING.pop(str(folder), None)


def _windows(state):
    if state.timeline:
        spans = [[max(state.start, s.start), min(state.end, s.end)] for s in state.timeline]
        return [[round(a, 2), round(b, 2)] for a, b in spans if b > a]
    return [[round(state.start, 2), round(state.end, 2)]]


def _next_version(folder):
    used = [int(p.name[1:]) for p in Path(folder).glob('v[0-9][0-9][0-9]') if (p/'edited.mp4').is_file() or (p/'beats.json').is_file()]
    return f'v{max(used, default=0)+1:03d}'


def _publish(pid, jid, index, user, state, version, duration, text):
    """Save the result, retrying through a brief database outage so a finished edit is not lost."""
    for attempt in range(6):
        try:
            return _save_result(pid, jid, index, user, state, version, duration, text)
        except HTTPException as exc:
            if attempt == 5 or exc.status_code == 409: raise
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
        if draft is None and state is None: raise HTTPException(409, 'Open this clip in the Editor first.')
        draft = draft or Draft(state=state)
        if version:
            song = None
            try:   # "Music: Alive Again (your audio)." -> "Alive Again"
                said = json.loads((root(pid, jid, index, user)/version/'report.json').read_text()).get('song') or ''
                song = re.sub(r'^Music:\s*|\s*\(.*$|\.$', '', said).strip()[:160] or None
            except (OSError, ValueError):
                pass
            draft.state.ai_edit = AIEditRef(version=version, duration=duration, song=song)
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


