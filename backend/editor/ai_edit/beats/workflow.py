"""Stage 3: the beats pipeline inside the AI Editor chat (CASCADE_EDIT_ENGINE=beats).

A beat plan is saved as ai-edits/<job>-<clip>/vNNN/beats.json next to the Cinema engine's versions and
listed in the same versions.json, so the version numbers never collide. Each version records its plan id,
its parent's plan id, the user message that made it, the critic score and which beats changed. The
draft points at the current plan with `state.ai_plan`; `state.ai_edit` (a rendered film) is untouched,
so the Edited preview and Export keep using the user's own timeline until plans render.

    first(...)   transcribe -> window -> make_plan -> v001
    revise(...)  revise_plan on the current version -> a child version (only if something changed)
    go_back(...) the parent version
    patch_route  a direct edit of one beat's text, color or template, through the same validator
"""
import copy
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from . import llm, service, validator
from .llm import PlanError
from .transcribe import transcribe

PLAN_FILE = 'beats.json'
MAX_WINDOW = 60.0
EXAMPLE_NAME = 'source'


def _jobs():
    from .. import jobs   # jobs imports this module; import lazily to avoid a cycle
    return jobs


def transcript_folder(folder):
    return Path(folder)/'beats'


def cached_transcript(folder):
    try:
        return json.loads((transcript_folder(folder)/'transcript.json').read_text())['words']
    except (OSError, ValueError, KeyError):
        raise PlanError('The transcript for this clip is missing. Ask for a new edit ("edit this video").') from None


def load(folder, version):
    path = Path(folder)/version/PLAN_FILE
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        raise HTTPException(404, 'That plan version is not on this machine.') from None


def ref(data):
    from ...models import AIPlanRef
    return AIPlanRef(version=data['version'], plan_id=data['plan_id'])


def save_version(folder, plan, *, message, kind, parent=None, changed=None, critic_score=None, issues=(), notes=(), model=''):
    """Write vNNN/beats.json and list it in versions.json. Returns the saved record."""
    jobs = _jobs()
    name = jobs._next_version(folder)
    record = {'engine': 'beats', 'version': name, 'plan_id': uuid.uuid4().hex, 'kind': kind,
              'parent_id': parent and parent['plan_id'], 'parent_version': parent and parent['version'],
              'message': message[:2000], 'critic_score': critic_score, 'validator_score': validator.score([validator.Issue(**i) for i in issues]),
              'changed_beat_ids': list(changed if changed is not None else [b['id'] for b in plan['beats']]),
              'issues': list(issues), 'notes': list(notes), 'model': model, 'created': time.time(), 'plan': plan}
    jobs._write(Path(folder)/name/PLAN_FILE, record)
    entry = {'version': name, 'title': f"Beat plan · {len(plan['beats'])} beats", 'request': message[:500], 'duration': plan.get('total_duration'),
             'created': record['created'], 'engine': 'beats', 'plan_id': record['plan_id'], 'parent_id': record['parent_id'], 'score': critic_score}
    jobs._write(Path(folder)/'versions.json', [*jobs.versions(folder), entry])
    return record


def choose_window(words, start, end):
    """The words inside the user's trim and the window to plan: all of it if it is 60 s or less, else the director picks."""
    inside = [w for w in words if start-1e-6 <= w['start'] < end]
    if not inside: raise PlanError('I could not find any speech in this part of the clip to edit around.')
    span = {'start': inside[0]['start'], 'end': inside[-1]['end']}
    return inside, (span if span['end']-span['start'] <= MAX_WINDOW else None)


def first(folder, source, state, message, progress):
    llm.model()   # fail before minutes of transcription if the planner is not set up
    words = transcribe(source, transcript_folder(folder), lambda amount, stage: progress(.05+amount*.4, stage))
    inside, window = choose_window(words, state.start, state.end)
    progress(.5, 'Planning the edit…' if window else 'Finding the strongest 30 to 60 seconds and planning the edit…')
    result = service.make_plan(inside, window, message, source_video=EXAMPLE_NAME)
    chosen = result.plan['source_window']
    if window is None and not (inside[0]['start']-1e-6 <= chosen['start'] < chosen['end'] <= inside[-1]['end']+1e-6
                               and 25 <= chosen['end']-chosen['start'] <= MAX_WINDOW+2):
        raise PlanError('The AI editor picked a part of the clip it should not have. Try again.', f'bad window {chosen}')
    progress(.95, 'Saving the plan…')
    data = save_version(folder, result.plan, message=message, kind='edit', critic_score=result.critic_score,
                        issues=result.issues, notes=result.notes, model=result.model)
    plan = data['plan']
    text = (f"Here's the plan: {len(plan['beats'])} beats covering {chosen['start']:.1f}s to {chosen['end']:.1f}s of the clip "
            f"({plan['total_duration']:.1f}s). It opens on “{plan['hook']['text']}”.\n"
            f"{data['version']}{' · quality score '+str(round(result.critic_score)) if result.critic_score is not None else ''}. "
            'Ask for any change here.')
    return data, text


def render_version(folder, data, source, stock=None, progress=None):
    """Render a saved plan version to vNNN/edited.mp4 (Remotion; see render.py). Returns (duration or None, a note for the
    chat). Beats already rendered for an earlier version are reused. Never raises: a plan stays usable without its video."""
    import os
    from . import render
    report = progress or (lambda amount, stage: None)
    if os.getenv('CASCADE_BEATS_RENDER', 'on').strip().lower() == 'off': return None, ''
    why = render.available()
    if why: return None, f'\nThe preview video was not made: {why}'
    folder = Path(folder)
    out = folder/data['version']/'edited.mp4'
    try:
        result = render.render(data['plan'], source, out, folder/'beats-render', progress=report)
    except Exception as exc:
        logging.getLogger(__name__).warning('beat plan render failed', exc_info=True)
        return None, f"\nThe preview video could not be made ({getattr(exc, 'detail', None) or exc}). The plan is saved."
    record = load(folder, data['version'])
    record['render'] = {k: result[k] for k in ('frames', 'seconds', 'size', 'rendered_beats', 'reused_beats', 'timings', 'checks', 'credits')}
    _jobs()._write(folder/data['version']/PLAN_FILE, record)
    reused = len(result['reused_beats'])
    return result['seconds'], (f"\nPreview ready: {result['seconds']:.1f}s at 60 fps"
                               f"{f', {reused} unchanged beats reused' if reused else ''}. The Edited view plays it.")


def film(folder, version):
    """The rendered film of a plan version as an AIEditRef, or None if it has none."""
    from ...models import AIEditRef
    record = load(folder, version)
    seconds = (record.get('render') or {}).get('seconds')
    return AIEditRef(version=version, duration=seconds) if seconds and (Path(folder)/version/'edited.mp4').is_file() else None


def revise(folder, current, message, progress):
    llm.model()
    base = load(folder, current.version)
    words = cached_transcript(folder)
    progress(.3, 'Planning the change…')
    result = service.revise_plan(base['plan'], words, message)
    if not result.changed_beat_ids:
        return None, result.reply
    data = save_version(folder, result.plan, message=message, kind='revise', parent=base, changed=result.changed_beat_ids,
                        critic_score=base.get('critic_score'), issues=result.issues, notes=result.notes, model=result.model)
    ids = ', '.join(str(i) for i in result.changed_beat_ids)
    return data, f"{result.reply}\n{data['version']} · changed beat{'s' if len(result.changed_beat_ids) > 1 else ''} {ids}."


def go_back(folder, current):
    """(plan ref, film ref or None, text) of the parent version; plan ref None when there is no parent."""
    base = load(folder, current.version)
    if not base.get('parent_version'):
        return None, None, 'This is the first version of the plan, so there is nothing earlier to go back to.'
    parent = load(folder, base['parent_version'])
    return ref(parent), film(folder, parent['version']), f"Back to {parent['version']} ({parent['message'][:80]}). Your later version is still saved."


class BeatEdit(BaseModel):
    """What a person may change on one beat by hand. Anything else goes through the chat."""
    model_config = ConfigDict(extra='forbid')
    emphasis_text: str | None = Field(default=None, max_length=60)
    accent_word: str | None = Field(default=None, max_length=60)
    semantic_color: Literal['green', 'red', 'yellow', 'orange', 'white'] | None = None
    template: str | None = Field(default=None, max_length=40)


def explain(issue):
    """A validator issue as one plain sentence for the person editing."""
    where = f'Beat {issue.beat_id}' if issue.beat_id else 'The plan'
    problem = issue.problem
    if 'same template back to back' in problem: return f'{where} would use the same style as the beat before it.'
    if 'not spoken in this beat' in problem:
        word = problem.split("'")[1]
        return f'“{word}” is not said during beat {issue.beat_id}; on-screen words must be spoken in that beat.'
    if 'missing b-roll' in problem: return f'{where} would need footage picked for it; ask for B-roll in the chat instead.'
    if 'needs data.' in problem: return f'{where} would need a {problem.rsplit(".", 1)[1]} from the speech; ask for that in the chat instead.'
    if 'missing emphasis_text' in problem: return f'{where} needs on-screen text for that style.'
    if 'unknown template' in problem: return f'{where}: that style does not exist.'
    if 'PLAIN_SPEAKER twice' in problem: return f'{where}: the plain speaker shot can only be used once every 10 seconds.'
    return f'{where}: {problem}.'


def _clip(pid, jid, index, request):
    from ...storage import selected
    selected(pid, jid, index, request.state.user_id)
    return _jobs().root(pid, jid, index, request.state.user_id)


def plan_route(pid: str, jid: str, index: int, version: str, request: Request):
    """GET …/{jid}/{index}/beats/{version}: one saved plan version."""
    if not version.startswith('v') or not version[1:].isdigit(): raise HTTPException(422, 'Unknown plan version.')
    return load(_clip(pid, jid, index, request), version)


def patch_route(pid: str, jid: str, index: int, version: str, beat_id: int, body: BeatEdit, request: Request):
    """PATCH …/{jid}/{index}/beats/{version}/{beat_id}: change one beat's text, color or template by hand."""
    if not version.startswith('v') or not version[1:].isdigit(): raise HTTPException(422, 'Unknown plan version.')
    folder = _clip(pid, jid, index, request)
    jobs = _jobs()
    job = jobs.job_status(folder)
    if job and job['status'] in ('queued', 'running'): raise HTTPException(409, 'The AI editor is still working on this clip. Try again when it finishes.')
    base = load(folder, version)
    changes = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in body.model_dump(exclude_unset=True).items()}
    if not changes: raise HTTPException(422, 'Nothing to change.')
    plan = copy.deepcopy(base['plan'])
    beat = next((b for b in plan['beats'] if b['id'] == beat_id), None)
    if beat is None: raise HTTPException(404, f'There is no beat {beat_id} in {version}.')
    if 'template' in changes and not changes['template']: raise HTTPException(422, 'Choose a style for the beat.')
    beat.update(changes)
    words = cached_transcript(folder)
    before = {(i.rule, i.beat_id, i.problem) for i in validator.validate(base['plan'], words)}
    issues = validator.validate(plan, words)
    new = [i for i in issues if (i.rule, i.beat_id, i.problem) not in before]
    blocking = validator.high(new)
    if blocking:
        raise HTTPException(422, "That change can't be made: " + ' '.join(dict.fromkeys(explain(i) for i in blocking)))
    what = ', '.join(f'{k.replace("_", " ")}: {v}' for k, v in changes.items())
    message = f'Edited beat {beat_id} by hand ({what}).'
    data = save_version(folder, plan, message=message, kind='manual', parent=base, changed=[beat_id],
                        critic_score=base.get('critic_score'), issues=[i.as_dict() for i in issues], model=base.get('model', ''))
    text = f"{message[:-1]}. Saved as {data['version']}."
    jobs._publish(pid, jid, index, request.state.user_id, None, None, None, text, plan=ref(data))
    job = jobs.start_beats_render(folder, pid, jid, index, request, data)
    return {'plan': data, 'ai_plan': ref(data).model_dump(), 'message': text, 'ai_job': job,
            'warnings': [explain(i) for i in new if i.severity != 'high']}
