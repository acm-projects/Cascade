"""Render an approved storyboard onto the clip's timeline with the existing Director recipes.

Global choices (framing, look, captions, music, hook card, B-roll, big words) go through apply_plan;
per-beat choices the recipes do not place on their own (cuts, caption rewrites, zooms, flashes,
glitches and sound effects) are added on exactly the beats the storyboard names. What a storyboard
adds is recorded in `state.board`, so rendering a new one replaces it instead of stacking on top
while anything the user added by hand stays.
"""
from .advanced_models import Motion, StoryboardInfo, StyleEvent, TimelineSpan
from .director_models import BrollIdea, DirectorPlan, Emphasis
from .style_profile_models import ProfileChoices

CARD = 1.6


def _forget_previous(state, audio_store):
    """Remove what the last rendered storyboard added. Style events are only ever AI-made."""
    previous = state.board
    legacy = previous is None and state.stylize and any(e.kind == 'motion_card' for e in state.stylize.events)
    if legacy:  # rendered before ownership was recorded: its audio is the synthesized library, its motion all generated
        synthesized = {a['id'] for a in audio_store.library() if a.get('source') == 'synthesized'}
        state.audio = [a for a in state.audio if a.asset_id not in synthesized]
        state.motion, state.timeline = [], []
    elif previous:
        remaining = list(previous.motion)
        kept = []
        for motion in state.motion:
            if motion in remaining: remaining.remove(motion)
            else: kept.append(motion)
        state.motion = kept
        state.audio = [a for a in state.audio if a.id not in previous.audio_ids]
        state.broll = [b for b in state.broll if b.id not in previous.broll_ids]
        state.texts = {k: v for k, v in state.texts.items() if k not in previous.text_keys}
        state.timeline = []
    state.stylize, state.board = None, None


def _cuts(state, beats, cues):
    """Kept lines only, with the pauses between them removed. [] when that would change almost nothing."""
    spans = []
    for c in (cues[b.n] for b in beats if b.keep):
        a, b = max(state.start, c['start']-.1), min(state.end, c['end']+.1)
        if spans and a-spans[-1][1] < .35: spans[-1][1] = max(spans[-1][1], b)
        else: spans.append([a, b])
    while len(spans) > 20:
        gap = min(range(len(spans)-1), key=lambda i: spans[i+1][0]-spans[i][1])
        spans[gap][1] = spans.pop(gap+1)[1]
    if not spans or (state.end-state.start)-sum(b-a for a, b in spans) < .5: return []
    return [TimelineSpan(start=round(a, 3), end=round(b, 3)) for a, b in spans]


def _fit_cards_to_cuts(state, events, timeline):
    """The hook card opens the first kept moment and the end card closes the last one, or the cuts would remove them."""
    first, last = timeline[0], timeline[-1]
    for event in events:
        if event.kind == 'motion_card':
            event.start = first.start
            event.duration = min(CARD, first.end-first.start)
        elif event.kind == 'title_card':
            event.duration = min(event.duration, last.end-last.start)
            event.start = round(last.end-event.duration, 3)
    if any(e.kind == 'motion_card' for e in events):
        events[:] = [e for e in events if not (e.kind == 'text' and first.start <= e.start < first.start+CARD)]


def apply(state, board, info, stock, audio_store, profile=None):
    """Mutates and returns (state, notes)."""
    from .director_recipes import apply_plan
    from .my_style import _sfx
    _forget_previous(state, audio_store)
    manual_audio, manual_broll, manual_motion = {a.id for a in state.audio}, {b.id for b in state.broll}, list(state.motion)
    cues = info['cues']
    beats = [b for b in board.beats if b.n < len(cues)]
    rel = lambda b: round(max(0, cues[b.n]['start']-state.start), 3)
    # Big words stay in front of the subject: a word half hidden behind someone can't be read.
    choices = (profile.choices if profile else ProfileChoices()).model_copy(update={
        'look': board.look, 'captions': board.captions, 'accent': board.accent, 'music': board.music, 'motion_cards': bool(board.hook),
        'glitch_accents': False, 'sound_fx': False, 'transitions': 'cut', 'punch_ins': False, 'tighten_pauses': False, 'words_behind': False})
    plan = DirectorPlan(style='memorial' if board.look in ('bw', 'sepia') and board.music == 'Quiet reflection' else 'podcast', look=board.look,
                        pacing='fast', captions=board.captions, music=board.music,
                        emphasis=[Emphasis(text=b.emphasis, at=rel(b)) for b in beats if b.emphasis and b.keep][:6],
                        broll=[BrollIdea(query=b.broll, at=rel(b), duration=1.8) for b in beats if b.broll and b.keep][:6],
                        rationale=board.title, hook=board.hook, my_style=choices)
    state, notes = apply_plan(state, plan, info, stock, audio_store)
    if board.ratio != 'original':
        # Fit keeps the whole picture and every word burned into it; framing a crop is the Aspect Ratio tab's job.
        state.composition.ratio = board.ratio
        state.composition.mode = 'fill' if state.reframe.enabled else 'fit'
        if state.composition.mode == 'fit': state.composition.background = '#000000'
        notes.insert(0, f'{board.ratio} frame')
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
    if timeline: _fit_cards_to_cuts(state, events, timeline)
    state.stylize.events = sorted(events, key=lambda e: e.start)[:80]
    remaining = list(manual_motion)
    state.board = StoryboardInfo(audio_ids=[a.id for a in state.audio if a.id not in manual_audio], broll_ids=[b.id for b in state.broll if b.id not in manual_broll],
                                 motion=[m for m in state.motion if not (m in remaining and not remaining.remove(m))], text_keys=list(rewrites))
    cut = sum(not b.keep for b in beats)
    removed = (state.end-state.start)-sum(s.end-s.start for s in timeline) if timeline else 0
    notes += [n for n in (f'{len(rewrites)} caption rewrite(s)' if rewrites else '', f'caption size {board.caption_size}',
                          f'cut {cut} line(s) and pauses (−{removed:.1f}s)' if timeline else '', f'{zooms} zoom(s)' if zooms else '', f'{effects} flash/glitch' if effects else '',
                          f'{sounds} sound effect(s)' if sounds else '') if n]
    return state, notes
