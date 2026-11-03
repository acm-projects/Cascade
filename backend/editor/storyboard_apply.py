"""Render an approved storyboard onto the clip's timeline with the existing Director recipes.

Global choices (look, captions, music, hook card, B-roll, big words) go through apply_plan; per-beat
choices the recipes do not place on their own (cuts, caption rewrites, zooms, flashes, glitches and
sound effects) are added on exactly the beats the storyboard names.
"""
from .advanced_models import Motion, StyleEvent, TimelineSpan
from .director_models import BrollIdea, DirectorPlan, Emphasis
from .style_profile_models import ProfileChoices


def _cuts(state, beats, cues):
    kept = [cues[b.n] for b in beats if b.keep]
    if len(kept) == len(beats) or not kept: return []
    spans = []
    for c in kept:
        a, b = max(state.start, c['start']-.1), min(state.end, c['end']+.1)
        if spans and a-spans[-1][1] < .35: spans[-1][1] = max(spans[-1][1], b)
        else: spans.append([a, b])
    return [TimelineSpan(start=round(a, 3), end=round(b, 3)) for a, b in spans[:20]]


def apply(state, board, info, stock, audio_store, profile=None):
    """Mutates and returns (state, notes)."""
    from .director_recipes import apply_plan
    from .my_style import _sfx
    cues = info['cues']
    beats = [b for b in board.beats if b.n < len(cues)]
    rel = lambda b: round(max(0, cues[b.n]['start']-state.start), 3)
    choices = (profile.choices if profile else ProfileChoices()).model_copy(update={
        'look': board.look, 'captions': board.captions, 'accent': board.accent, 'music': board.music, 'motion_cards': bool(board.hook),
        'glitch_accents': False, 'sound_fx': False, 'transitions': 'cut', 'punch_ins': False, 'tighten_pauses': False})
    plan = DirectorPlan(style='memorial' if board.look in ('bw', 'sepia') and board.music == 'Quiet reflection' else 'podcast', look=board.look,
                        pacing='fast', captions=board.captions, music=board.music,
                        emphasis=[Emphasis(text=b.emphasis, at=rel(b)) for b in beats if b.emphasis and b.keep][:6],
                        broll=[BrollIdea(query=b.broll, at=rel(b), duration=1.8) for b in beats if b.broll and b.keep][:6],
                        rationale=board.title, hook=board.hook, my_style=choices)
    state, notes = apply_plan(state, plan, info, stock, audio_store)
    state.captions.size = board.caption_size
    rewrites = {str(b.n): b.caption for b in beats if b.caption and b.caption.strip() != cues[b.n]['text'].strip()}
    state.texts = {**state.texts, **rewrites}
    timeline = _cuts(state, beats, cues)
    if timeline: state.timeline = timeline
    events, taken, zooms, effects, sounds = list(state.stylize.events), [(m.start, m.start+m.duration) for m in state.motion], 0, 0, 0
    for b in beats:
        if not b.keep: continue
        at = max(state.start, cues[b.n]['start'])
        if b.zoom != 'none':
            length = min(3.5 if b.zoom == 'push' else 1.4, max(.3, state.end-at-.05))
            if all(at+length <= s or at >= e for s, e in taken):
                frm, to = (1, 1.08) if b.zoom == 'push' else (1.14, 1.16)
                state.motion.append(Motion(start=round(at, 3), duration=round(length, 3), scale_from=frm, scale_to=to)); taken.append((at, at+length)); zooms += 1
        if b.effect != 'none' and at < state.end-.3:
            events.append(StyleEvent(start=round(at, 3), duration=.1 if b.effect == 'flash' else .18, kind=b.effect)); effects += 1
        if b.sfx != 'none' and audio_store is not None:
            sounds += _sfx(state, audio_store, 'Impact hit' if b.sfx == 'hit' else 'Air whoosh', at, .45)
    state.stylize.events = sorted(events, key=lambda e: e.start)[:80]
    cut = sum(not b.keep for b in beats)
    notes += [n for n in (f'{len(rewrites)} caption rewrite(s)' if rewrites else '', f'caption size {board.caption_size}',
                          f'cut {cut} line(s)' if timeline else '', f'{zooms} zoom(s)' if zooms else '', f'{effects} flash/glitch' if effects else '',
                          f'{sounds} sound effect(s)' if sounds else '') if n]
    return state, notes
