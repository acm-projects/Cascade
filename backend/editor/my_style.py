"""Apply the user's learned style (from their reference reels) with the Director's existing recipe machinery.

The Director still watches the clip for key moments, important words and B-roll ideas; the style
sheet replaces the YouTube inspiration search and decides how each of those is presented.
"""
import uuid

from .advanced_models import AudioSegment, StyleEvent
from .director_models import DirectorPlan

FONTS = {'impact': 'impact', 'poster': 'poster', 'typewriter': 'typewriter', 'script': 'script', 'grunge': 'grunge'}
BROLL = {'low': 1, 'medium': 3, 'high': 5}


def plan_from_profile(analysis, profile):
    """DirectorPlan for this clip: the analysis supplies the moments, the profile the treatment."""
    c = profile.choices
    # 'podcast' carries punch-ins, words and B-roll; pacing 'fast' raises how many of each are placed.
    style = 'memorial' if c.look in ('bw', 'sepia') and c.pacing == 'slow' else 'podcast'
    return DirectorPlan(style=style, look=c.look, pacing=c.pacing, captions=c.captions, music=c.music, tighten_pauses=c.tighten_pauses,
                        emphasis=analysis.emphasis[:6], broll=analysis.broll[:BROLL[c.broll]], key_moments=analysis.key_moments,
                        rationale=f'Edited this {analysis.genre.replace("_", " ")} clip in your "{c.name}" style.',
                        inspiration='; '.join(c.summary[:3])[:600], genre=analysis.genre, my_style=c)


def recipe(base, c):
    """The Director recipe for this style, adjusted by the style sheet."""
    out = dict(base)
    font, animate, size, place = base['font']
    out['font'] = (FONTS[c.emphasis_font], 'slam' if c.pacing != 'slow' else 'type', size, place)
    out['broll'] = ('dissolve' if c.transitions == 'dissolve' else 'cut', base['broll'][1])
    out['palette'] = 'mono' if c.look == 'bw' else base['palette']
    return out


def captions(state, c, plan):
    cap = state.captions
    cap.color, cap.highlight = c.caption_color, c.accent
    if c.captions in ('pop', 'karaoke'):
        cap.max_words = c.caption_words
    cap.emphasis = [e.text.lower() for e in plan.emphasis][:12]


def _sfx(state, audio_store, name, at, volume=.5):
    asset = next((a for a in audio_store.library() if a['kind'] == 'sfx' and a['name'] == name), None)
    if not asset or not state.start <= at < state.end-.1: return 0
    state.audio.append(AudioSegment(id=uuid.uuid4().hex, asset_id=asset['id'], track='sfx', start=round(at, 3),
                                    duration=round(min(asset['duration'], state.end-at), 3), volume=volume, fade_in=0, fade_out=.1, duck=False, loop=False))
    return 1


def extras(state, plan, events, audio_store, hook_text):
    """Flashes, glitches, sound effects and the HyperFrames hook card. Returns note strings."""
    c = plan.my_style
    notes = []
    cuts = sorted(s.start for s in state.broll)
    if c.transitions == 'flash':
        for at in cuts[:4]:
            events.append(StyleEvent(start=round(at, 3), duration=.1, kind='flash'))
        if cuts: notes.append(f'{min(4, len(cuts))} flash transitions')
    if c.glitch_accents:
        moments = sorted(plan.key_moments, key=lambda m: -m.importance)[:2]
        for m in moments:
            at = max(state.start, min(state.end-.3, state.start+m.at))
            events.append(StyleEvent(start=round(at, 3), duration=.18, kind='glitch'))
        if moments: notes.append(f'{len(moments)} glitch accents')
    card = 0
    if c.motion_cards and hook_text and state.end-state.start > 6:
        card = 1.6
        kept = [e for e in events if not (e.kind == 'text' and e.start < state.start+card)]  # the card is the hook's text
        if len(kept) < len(events): notes.append(f'hook card replaces {len(events)-len(kept)} key word(s) in its first {card}s')
        events[:] = kept
        events.append(StyleEvent(start=round(state.start, 3), duration=card, kind='motion_card', text=hook_text[:40],
                                  color=c.accent, font=c.emphasis_font))
        notes.append(f'HyperFrames hook card: "{hook_text[:40]}"')
    words = [e for e in events if e.kind == 'text' and e.start >= state.start]
    if c.sound_fx and audio_store is not None:
        placed = sum(_sfx(state, audio_store, 'Impact hit', w.start, .45) for w in words[:4])
        placed += sum(_sfx(state, audio_store, 'Air whoosh', max(state.start, at-.2), .4) for at in cuts[:4])
        if card: placed += _sfx(state, audio_store, 'Impact hit', state.start+.1, .5)
        if placed: notes.append(f'{placed} sound effects on key words and cuts')
    return notes


def hook_text(plan, info, state):
    """A short hook line: the strongest spoken phrase near the start, else the top emphasis word."""
    cues = [q for q in info.get('cues', []) if state.start <= q['start'] < min(state.end, state.start+12)]
    for q in cues:
        text = q['text'].strip().rstrip('.,')
        if 2 <= len(text.split()) <= 7:
            return text
    return plan.emphasis[0].text if plan.emphasis else ''
