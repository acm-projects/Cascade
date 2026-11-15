"""Turn a DirectorPlan into a real, clean edit with existing timeline features.

Each style is a recipe: look, captions, music, motion on key moments, a few important words,
B-roll (source video first, free Pexels stock second), pause tightening, fades and the
"Edited by Cascade" end card. Everything renders locally; nothing here costs money.
"""
import logging
import uuid

from fastapi import HTTPException

from .advanced_models import AudioSegment, Motion, StyleEvent, StyleInfo, TimelineSpan, Transition

LOG = logging.getLogger(__name__)
RECIPES = {  # fades, zoom kind/strength, word font/animation/size/place, B-roll transition/length, palette
    'memorial': dict(fade=(.8, 1.2), zoom=('push', 1.07), font=('typewriter', 'type', .6, 'upper'), broll=('dissolve', 3.0), palette='mono'),
    'podcast': dict(fade=(0, .4), zoom=('punch', 1.14), font=('impact', 'slam', .5, 'upper'), broll=('cut', 1.8), palette='spider'),
    'cinematic': dict(fade=(.5, .8), zoom=('push', 1.06), font=('poster', 'type', .45, 'center'), broll=('dissolve', 2.5), palette='gold'),
    'clean': dict(fade=(.2, .4), zoom=('push', 1.05), font=('impact', 'type', .4, 'upper'), broll=('cut', 2.0), palette='spider'),
    'hype': dict(fade=(0, .3), zoom=('punch', 1.2), font=('poster', 'slam', .8, 'center'), broll=('cut', 1.2), palette='neon'),
    'fan_edit': dict(fade=(0, .3), zoom=('punch', 1.15), font=('impact', 'slam', 1.0, 'center'), broll=('cut', 1.0), palette='spider'),
}
LIMITS = {'slow': 3, 'medium': 4, 'fast': 6}


def _clamp(state, at, length=0):
    return max(state.start, min(state.end-length-.05, state.start+at))


def _free(spans, a, b):
    return all(b <= s or a >= e for s, e in spans)


def _look(state, plan, events):
    if plan.look in ('bw', 'sepia') or (plan.look == 'warm' and plan.style == 'memorial'):
        events.append(StyleEvent(start=state.start, duration=min(30, state.end-state.start), kind='film', tone=plan.look if plan.look != 'warm' else 'warm',
                                 strength=.8))
        extra = state.end-state.start-30
        if extra > 0:
            events.append(StyleEvent(start=state.start+30, duration=min(30, extra), kind='film', tone=plan.look if plan.look != 'warm' else 'warm', strength=.8))
        return 'film look: '+plan.look
    grades = {'teal_orange': (1, 1.08, 1.12), 'vivid': (1.02, 1.1, 1.25), 'warm': (1.03, 1.04, 1.08)}
    if plan.look in grades:
        state.effects.brightness, state.effects.contrast, state.effects.saturation = grades[plan.look]
        return 'color grade: '+plan.look
    return ''


def _captions(state, plan):
    c = state.captions
    if plan.captions == 'none':
        c.enabled = False; return 'captions off'
    c.enabled = True
    if plan.captions == 'clean':
        c.animation, c.bold, c.size, c.max_words = 'none', False, 30, 0
    elif plan.captions == 'pop':
        c.animation, c.bold, c.size, c.max_words = 'pop', True, 40, 3
    else:
        c.animation, c.bold, c.size, c.max_words, c.highlight = 'karaoke', True, 38, 4, '#ffdc39'
    return f'{plan.captions} captions'


def _music(state, plan, audio_store):
    if plan.music == 'none' or any(s.track == 'music' for s in state.audio): return ''
    asset = next((a for a in audio_store.library() if a['kind'] == 'music' and a['name'] == plan.music), None)
    if not asset: return ''
    volume = .1 if plan.style in ('memorial', 'podcast', 'clean') else .16
    state.audio.append(AudioSegment(id=uuid.uuid4().hex, asset_id=asset['id'], track='music', start=state.start,
                                    duration=round(state.end-state.start, 3), volume=volume, fade_in=1, fade_out=1.5, duck=True, loop=True))
    return f'music: {plan.music} (ducked under speech)'


def _motion(state, plan, recipe):
    if plan.my_style and not plan.my_style.punch_ins: return ''
    kind, strength = recipe['zoom']
    moments = sorted(plan.key_moments, key=lambda m: -m.importance)[:LIMITS[plan.pacing]]
    taken = [(m.start, m.start+m.duration) for m in state.motion]
    for m in sorted(moments, key=lambda m: m.at):
        length = 3.5 if kind == 'push' else 1.4
        at = _clamp(state, m.at, length)
        if at < state.start or not _free(taken, at, at+length): continue
        frm, to = (1, strength) if kind == 'push' else (strength, strength+.02)
        state.motion.append(Motion(start=round(at, 3), duration=length, scale_from=frm, scale_to=to,
                                   shake=.004 if plan.style in ('hype', 'fan_edit') else 0))
        taken.append((at, at+length))
    return f'{len(taken)} {"slow push-ins" if kind == "push" else "punch-ins"} on key moments' if taken else ''


def _words(state, plan, recipe, events):
    font, animate, size, place = recipe['font']
    taken = []
    for e in sorted(plan.emphasis, key=lambda e: e.at)[:LIMITS[plan.pacing]]:
        at = _clamp(state, e.at, 1.4)
        if at < state.start or not _free(taken, at-.4, at+1.8): continue
        events.append(StyleEvent(start=round(at, 3), duration=1.4, kind='text', text=e.text.upper()[:40], font=font, animate=animate,
                                 size=size, place=place, behind=plan.my_style.words_behind if plan.my_style else plan.style in ('fan_edit', 'hype')))
        taken.append((at, at+1.4))
    return f'{len(taken)} key words on screen' if taken else ''


def _broll(state, plan, recipe, info, stock):
    from . import source_broll
    transition, length = recipe['broll']
    source = info.get('source_path')
    avoid = [tuple(info['clip_source_range'])] if info.get('clip_source_range') else []
    taken = [(s.start, s.start+s.duration) for s in state.broll]
    placed, used = [], []
    for idea in plan.broll[:4 if plan.pacing != 'slow' else 3]:
        span = min(length, idea.duration if plan.style != 'memorial' else max(idea.duration, length))
        at = _clamp(state, idea.at, span)
        if at < state.start+.5 or not _free(taken, at-.3, at+span+.3): continue
        try:
            hits = source_broll.find(source, idea.query, avoid, used=used) if source and idea.source == 'source_video' else []
            if hits:
                source_broll.insert(state, stock, source, hits[0], at, span, idea.query, transition)
                used.append(hits[0]); placed.append(f'"{idea.query}" from your source video')
            else:
                from backend.broll import Asset, Segment
                result = next((r for r in stock.search(idea.query)['results'] if r['duration'] >= span+.5), None)
                if not result: continue
                stock.media(result['id'])
                state.broll.append(Segment(id=uuid.uuid4().hex, asset=Asset(**result), start=round(at, 3), duration=round(span, 3),
                                           offset=.3, mode='fill', transition=transition))
                placed.append(f'"{idea.query}" from free stock')
            taken.append((at, at+span))
        except (HTTPException, OSError, ValueError, KeyError, IndexError) as exc:
            LOG.info('director broll skipped %s: %s', idea.query, exc)
    return 'B-roll: '+', '.join(placed) if placed else ''


def _tighten(state, info):
    """Line edit: drop silent gaps longer than 0.6 s between spoken cues."""
    cues = sorted((c for c in info.get('cues', []) if c['end'] > state.start and c['start'] < state.end), key=lambda c: c['start'])
    if len(cues) < 2 or state.timeline: return ''
    spans = []
    for c in cues:
        a, b = max(state.start, c['start']-.15), min(state.end, c['end']+.15)
        if spans and a-spans[-1][1] < .6: spans[-1][1] = max(spans[-1][1], b)
        else: spans.append([a, b])
    while len(spans) > 20:
        gap = min(range(len(spans)-1), key=lambda i: spans[i+1][0]-spans[i][1])
        spans[gap][1] = spans.pop(gap+1)[1]
    removed = (state.end-state.start)-sum(b-a for a, b in spans)
    if removed < 1: return ''
    state.timeline = [TimelineSpan(start=round(a, 3), end=round(b, 3)) for a, b in spans]
    return f'tightened pauses (−{removed:.1f}s)'


def apply_plan(state, plan, info, stock, audio_store):
    """Mutates and returns state plus human-readable notes of what was actually applied."""
    recipe = RECIPES[plan.style]
    if plan.my_style:
        from . import my_style
        recipe = my_style.recipe(recipe, plan.my_style)
    style = state.stylize or StyleInfo(palette=recipe['palette'])
    events = list(style.events)
    notes = []
    if plan.style == 'fan_edit':
        notes += [_look(state, plan, events), _music(state, plan, audio_store)]
    elif plan.style != 'hype':  # the high-energy reel brings its own music and motion
        notes += [_look(state, plan, events), _music(state, plan, audio_store), _motion(state, plan, recipe)]
        a, b = recipe['fade']
        state.transition = Transition(fade_in=a, fade_out=b)
    notes += [_captions(state, plan), _words(state, plan, recipe, events) if plan.style != 'fan_edit' else '', _broll(state, plan, recipe, info, stock)]
    if plan.tighten_pauses and (plan.style in ('podcast', 'clean') or plan.my_style):
        notes.append(_tighten(state, info))
    if plan.my_style:
        my_style.captions(state, plan.my_style, plan)
        notes += my_style.extras(state, plan, events, audio_store, my_style.hook_text(plan, info, state))
    if not any(e.kind == 'title_card' for e in events):
        card = min(1.6, (state.end-state.start)/5)
        events = [e for e in events if e.start < state.end-card or e.kind == 'film']
        events.append(StyleEvent(start=round(state.end-card, 3), duration=round(card, 3), kind='title_card', text='Cascade'))
    style.events = sorted(events, key=lambda e: e.start)[:80]
    state.stylize = style
    notes.append('ends with "Edited by Cascade"')
    return state, [n for n in notes if n]
