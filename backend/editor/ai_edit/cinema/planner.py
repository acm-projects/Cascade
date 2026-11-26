"""OpenAI plans Cinema edits through Cascade's shared structured client. Rules are explicit/offline only."""
import json
import logging
import re
import os
from pathlib import Path
from fastapi import HTTPException
from ... import openai_edit
from . import director, plan as plans, visual

class Unavailable(Exception):
    """No plan could be produced; preserve the existing edit."""

def choice():
    return 'rules' if os.getenv('CASCADE_EDIT_PLANNER', '').strip().lower() == 'rules' else 'openai'

def model():
    from backend.cascade_llm.clients import MODELS, OPENAI
    return MODELS[OPENAI]

def ai():
    return [] if choice() == 'rules' else ['openai']

def label(name):
    return openai_edit.label() if name == 'openai' else name

def _direct(prompt, prep_dir, prep, windows):
    system, images = director.instructions(), director.images(prep_dir, prep)
    # Local word alignment can overshoot the physical file by a few milliseconds.
    # Clamp only to the media boundary; manual trim windows remain strict.
    words = [{**w, 'e': min(w['e'], prep['duration'])} for w in prep['words']]
    try:
        return director.direct(lambda p: openai_edit.ask(system, p, openai_edit.strict_schema(plans.CinemaPlan), images,
                                                       name='cinema_edit', tokens=16000), prompt, words, windows=windows), label('openai')
    except HTTPException as exc:
        raise Unavailable(str(exc.detail)) from None
    except ValueError:
        raise Unavailable('OpenAI did not return a usable edit plan. Try the request again.') from None

def output(plan, words, new=True):
    """The house output rules (style.json "output"): about 15 s, 9:16, no Cascade sign-off."""
    from . import settings
    plan.settings.stamp = bool(settings.get('output.stamp', False))
    ratio = settings.get('output.ratio', '9:16')
    if ratio and (new or plan.settings.ratio is None): plan.settings.ratio = ratio
    target = settings.get('output.target_seconds', 15)
    if isinstance(plan, visual.VisualPlan) and plan.seconds: target = plan.seconds   # the length the user asked for
    if isinstance(plan, visual.VisualPlan) and new and target and not plan.seconds and not plan.hard_length:   # (an asked-for length is kept)
        talking = sum(s.end-s.start for s in plan.shots if s.voice)
        if talking: target = min(40, max(target, talking+8))   # room for the quick cuts around the talking
    if target and isinstance(plan, visual.VisualPlan):
        from . import score
        message = settings.get('pacing.message_seconds', 3.4) if plan.end_line else 0
        if plan.clip_order and new and not plan.hard_length:   # every clip the request names stays: run a little long rather than drop one
            ending = (visual.OUTRO*.4 if plan.shots and plan.shots[-1].voice else visual.OUTRO) if plan.outro.strip() else 0
            target = min(target+3.5, max(target, visual.shortest(plan)+ending+message+.7))   # (+ room for beat snapping)
        timing = visual.song_timing(plan, target)
        if new and not plan.clip_order: visual.interleave(plan)   # never two pieces of one moment back to back (a requested order wins)
        if plan.song and not timing:   # an unknown song: Cascade's own score instead
            plan.song, plan.lyrics, plan.intro = '', 'off', 'none'
        if timing: visual.fit(plan, max(2., target-message), grid=timing[2], lead=timing[3])
        else: visual.fit(plan, max(2., target-message), beat=60/score.MOODS.get(plan.mood, score.MOODS['awakening'])['bpm'])
    elif target:
        tail = settings.get('pacing.tail_seconds', .5)
        message = settings.get('pacing.message_seconds', 3.4) if plan.end_line else 0
        plans.fit(plan, words, max(3., target-tail-message), pause=settings.get('dialogue.max_pause', .16))
    return plan

def plan_edit(request, prep_dir, prep, windows, history):
    if choice() == 'rules': return output(plans.auto(prep['words']), prep['words']), 'rules'
    plan, who = _direct(director.new_edit(request, prep, windows, history)+'\n\n'+songs(), prep_dir, prep, windows)
    return output(plan, prep['words']), who

def revise(note, current, prep_dir, prep, windows, history):
    if choice() == 'rules': raise Unavailable('The planner is set to rules, which cannot take creative changes.')
    if isinstance(current, visual.VisualPlan):
        prompt = (f"Request (a change to the edit below): {note}\nChange only what this asks for and return the whole plan.\n\n"
                  f"Current plan:\n{current.model_dump_json()}\n\nEarlier chat:\n{json.dumps(history[-8:])}\n\n{_footage(prep, windows)}")
        return output(_watch(prompt, prep_dir, prep, windows), prep['words'], new=False), label('openai')
    plan, who = _direct(director.change(note, current, prep, windows, history)+'\n\n'+songs(), prep_dir, prep, windows)
    return output(plan, prep['words'], new=False), who


# --- visual edits: clips where nobody speaks -------------------------------------------------------

VISUAL_PROMPT = Path(__file__).parent/'prompts'/'visual.md'


def _footage(prep, windows):
    every = prep.get('sheet_every', 1)
    motion = prep.get('motion') or []
    return (f"Clip: {prep['duration']:.1f} s. Usable source ranges: {windows}. Contact sheets: one cell every {every} s, 8 across and 6 down, "
            f"labelled with the source second. Camera cuts at seconds: {[round(c, 1) for c in prep.get('cuts', [])][:200]}.\n"
            f"Motion per second (index = second): {motion[:600]}\n\n{clips(prep.get('parts'), prep.get('words'))}{speech(prep.get('words') or [], windows)}{songs()}")


def clips(parts, words=None):
    """The picked clips this video was joined from, so "the wave" or "the hands thing" in a request maps to seconds;
    each with the first words said in it, so a talking clip (an intro, a chant) is recognised by what is said."""
    if not parts: return ''
    said = lambda p: ' '.join(w['w'] for w in (words or []) if p['from'] <= w['s'] < p['to'])[:110]
    listed = '\n'.join(f"{n+1}. {p['from']:.1f}-{p['to']:.1f} s: {p['title']}" + (f' | says: "{said(p)}"' if said(p) else ' | (no speech)')
                       for n, p in enumerate(parts))
    return ('Clips (this video is these picked clips joined in this order; a request naming a moment means the clip with that '
            f'title; use every clip unless the request leaves one out, and never let a shot cross from one clip into the next):\n{listed}\n\n')


def speech(words, windows):
    """What is said, as timed phrases in source seconds, for edits that mix talking moments with music."""
    inside = lambda w: not windows or any(a <= w['s'] and w['e'] <= b for a, b in windows)
    lines, run = [], []
    for w in (w for w in words if inside(w)):
        if run and (w['s']-run[-1]['e'] > .6 or len(run) >= 18):
            lines.append(run); run = []
        run.append(w)
    if run: lines.append(run)
    if not lines: return 'Speech: none (nobody talks in this clip).\n\n'
    said = '\n'.join(f"{r[0]['s']:.2f}-{r[-1]['e']:.2f}: {' '.join(w['w'] for w in r)}" for r in lines[:200])
    return ('Speech (what is said, source seconds start-end; a talking shot must start at or before a phrase start and end at or '
            f'after its end, so no word is cut):\n{said}\n\n')


MONTAGE = re.compile(r'\b(montage|music (edit|video)|recap|vibes?|insta(gram)? edit|trend(ing|y)? edit|inspo|(my|the) references?|'
                     r'memor(y|ies)|nostalgi\w*|friendship|hik(e|es|ing)|trip recap|vlog|aesthetic)\b', re.I)


def wants_montage(request):
    """A request for a music-led edit (a montage, an Insta or trend edit, a recap of a trip) rather than a talk edit."""
    return bool(MONTAGE.search(request or ''))


def songs():
    """The Music Library as the planner reads it (empty library: the composed score)."""
    from . import music, settings
    try:
        catalogue = music.catalogue(settings.get('output.target_seconds', 15) or 15)
    except Exception:
        logging.getLogger(__name__).warning('Music Library unavailable', exc_info=True)
        catalogue = []
    if not catalogue: return 'Music Library: empty. Set "song" to "" (Cascade composes a score in your chosen mood).'
    return 'Music Library (pick "song" by id and "song_section" by number; sections start at their own drop or chorus):\n'+json.dumps(catalogue)


def _watch(prompt, prep_dir, prep, windows, tries=4):
    system, images = VISUAL_PROMPT.read_text(), director.images(prep_dir, prep)
    schema, last = openai_edit.strict_schema(visual.VisualPlan), ''
    for _ in range(tries):
        try:
            answer = openai_edit.ask(system, prompt+last, schema, images, name='cinema_visual_edit', tokens=24000)
        except HTTPException as exc:
            raise Unavailable(str(exc.detail)) from None
        try:
            plan = visual.VisualPlan.model_validate(answer)
            for shot in plan.shots:   # Cascade's own markers: never taken from the planner
                shot.hard_end, shot.panel_ends, shot.panel_who, shot.said_until, shot.said_word = False, [], [], 0, ''
            plan.hard_length = False
            for shot in plan.shots: shot.carry_sound, shot.carry_until = False, 0   # (set from the request's words, not the planner)
            visual.check(plan, prep['duration'], windows, prep.get('cuts', []), prep.get('parts'))
            return plan
        except ValueError as exc:
            logging.getLogger(__name__).warning('Visual plan rejected: %s', exc)
            last = f'\n\nYour previous plan was rejected, fix this and return the whole plan: {str(exc)[:600]}'
    raise Unavailable('OpenAI did not return a usable edit plan. Try the request again.')


def requested_seconds(request):
    """The edit length the user asked for ("a 15 second edit", "10-15 seconds", "27s"), or 0. Clamped to 6-60 s."""
    found = re.findall(r'(\d+(?:\.\d+)?)\s*(?:-|–|to)?\s*(\d+(?:\.\d+)?)?\s*-?\s*(?:sec(?:ond)?s?|s)\b', request or '')
    if not found: return 0
    low, high = found[-1]
    return float(min(60, max(6, float(high or low))))


def plan_visual(request, prep_dir, prep, windows, history):
    """A new music edit: OpenAI watches the contact sheets and the motion (and reads any speech) and picks the moments."""
    if choice() == 'rules': return output(visual.auto(prep, windows), []), 'rules'
    seconds = requested_seconds(request)
    length = f"Length: {seconds:g} s, as asked." if seconds else ''
    prompt = f"Request: {request}\n{length}\n\nEarlier chat:\n{json.dumps(history[-8:])}\n\n{_footage(prep, windows)}"
    plan = _watch(prompt, prep_dir, prep, windows)
    said = [{**w, 'e': min(w['e'], prep['duration'])} for w in prep.get('words') or []]
    visual.story_edges(plan, said, prep.get('parts'))   # the intro and the ending are heard, the ending plays out
    visual.whole_phrases(plan, said, cuts=prep.get('cuts') or [])
    visual.stop_at(plan, said, request)   # "stop the intro at presentation prep"
    visual.trim_to_outro(plan, said)      # an ending word said in the last shot: the shot stops just after it
    visual.text_requests(plan, request)   # "big text in the middle"
    visual.keep_in_clips(plan, prep.get('parts'))
    if len(plan.shots) > 1 and plan.shots[-1].carry_sound and prep.get('parts'):   # the carried sound ends with its own clip
        prev = plan.shots[-2]
        clip = next((p for p in prep['parts'] if p['from']-.05 <= prev.start < p['to']), None)
        if clip: plan.shots[-1].carry_until = clip['to']-.03
    visual.ending_transition(plan)
    visual.transition_requests(plan, request)   # "the vertical transition before the vertical clips"
    visual.strip_subjects(plan, request)   # "the 3rd box ... focus on the girl in the red coat"
    for shot in plan.shots:   # each collage strip stops where its own clip ends (it then holds its last frame)
        if shot.panels and prep.get('parts'):
            end_of = lambda x: next((p['to'] for p in prep['parts'] if p['from']-.05 <= x < p['to']), None)
            shot.panel_ends = [e for e in [end_of(x) for x in [shot.start]+list(shot.panels)] if e is not None]
            if len(shot.panel_ends) != len(shot.panels)+1: shot.panel_ends = []
    if seconds: plan.seconds = seconds
    # "12 seconds max", "at most 12 seconds": a ceiling, never stretched to fit everything
    plan.hard_length = bool(seconds) and bool(re.search(r'\bmax(imum)?\b|\bat\s+most\b|no\s+longer\s+than|\bunder\s+\d', request or '', re.I))
    plan = output(plan, [])
    ratio = requested_ratio(request)
    if ratio: plan.settings.ratio = ratio
    return plan, label('openai')


def requested_ratio(request):
    """'16:9' for a horizontal / landscape / YouTube edit, '9:16' for a vertical one, '' when the request does not say."""
    if re.search(r'\b(horizontal(ly)?|landscape|16 ?: ?9|widescreen|youtube video)\b', request or '', re.I): return '16:9'
    if re.search(r'\b(vertical(ly)?|portrait|9 ?: ?16)\b', request or '', re.I): return '9:16'
    return ''
