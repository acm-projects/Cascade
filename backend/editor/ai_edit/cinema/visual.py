"""Visual edits: Cinema music edits. For clips where nobody speaks (sport, travel, b-roll, pets, music-only footage),
and for montages that mix music with a few talking moments (a group of friends on a trip): a shot marked "voice"
plays at normal speed with its own sound up front, the song dips under it and its words appear as captions.

The planner watches the contact sheets and the per-second motion and returns a VisualPlan: which moments of
the source to play, in what order, at what speed, with which zooms, effects and words. Everything is
addressed by source second, not by transcript word. Rendering reuses the Cinema picture and sound code
(render.py, score.py) and, like the rest of the engine, calls no AI model."""
import logging
import re
import time
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import look, render, score, settings, stamp
from .plan import Settings, Tone
from .render import Overlay, Shot

LOG = logging.getLogger(__name__)
MESSAGE = settings.get('pacing.message_seconds', 3.4)
ZOOMS = {'none': (1., 1.03), 'push': (1., 1.12), 'punch': (1.14, 1.17), 'pull': (1.14, 1.), 'close': (1.85, 1.95), 'rise': (1., 1.35),
         'dive': (1., 2.6)}
SHORTEST = .5   # seconds on screen
QUICKEST = .4   # a quick music shot is not shortened below this to make an edit fit
OUTRO = 1.7     # the ending word: pop, hold, zoom into it
LOOP = .75      # the closing return to the opening shot, for a seamless loop
TYPE_SECONDS = .9   # how long the typed title takes to spell out
TITLE_SECONDS = 3.6   # how long a "corners" title stays up
EFFECT_SECONDS = {'shake': .45, 'slices': .5, 'window': .6, 'cutin': .9, 'glowpop': .6, 'fade': .6, 'iris': .7}   # transitions longer than the default 0.32 s
TITLE_TONES = {'red': 'danger', 'blue': 'water', 'dark blue': 'water', 'water': 'water', 'yellow': 'money', 'green': 'life', 'white': 'calm'}
TITLE_PAINT = {'water': {'fill': (24, 86, 196), 'texture': 'water'}, 'blue': {'fill': (38, 98, 214)}, 'dark blue': {'fill': (30, 78, 178), 'edge': (6, 20, 66)}}   # colours that are not one of the tones


class VisualShot(BaseModel):
    model_config = ConfigDict(extra='ignore')
    clip: int = Field(default=0, ge=0, le=60)       # which clip of the "Clips" list it comes from (1-based; 0 = not said)
    start: float = Field(ge=0)                     # source seconds
    end: float = Field(gt=0)
    speed: float = Field(default=1., ge=.25, le=2.)   # .5 = half-speed slow motion, 2 = double speed
    # 'close': a strong close-up on people filmed from far away; 'rise': the camera rises toward the sky (hands up, an ending)
    # 'dive': the camera plunges into the subject (an ending: "zoom into the rock and end")
    zoom: Literal['none', 'push', 'punch', 'pull', 'close', 'rise', 'dive'] = 'none'
    focus_x: float = Field(default=.5, ge=0, le=1)   # where the subject is, left (0) to right (1), for vertical crops
    focus_y: float = Field(default=.45, ge=0, le=1)  # where the subject is, top (0) to bottom (1), for a 'close' zoom
    # 'cutin': the people of this shot appear cut out on top of the previous shot, then its picture fades in behind them
    # 'glowpop': the people pop up big as a glowing white cut-out, turn to their colours, then the scene fades in around them
    # 'fade': a smooth dissolve from the previous shot
    # 'iris': an Earth-zoom push: the previous shot rushes in while a circle opens around this shot's focus point,
    # this shot zooming in inside it, until it fills the frame
    effect: Literal['whip', 'rgb', 'ink', 'ripple', 'flash', 'invert', 'glitch', 'leak', 'zoom', 'shake', 'slices', 'window', 'cutin', 'glowpop', 'fade', 'iris'] | None = None   # a transition as this shot lands
    text: str = Field(default='', max_length=16)       # one big word over the start of this shot
    text_style: Literal['slam', 'perspective'] = 'perspective'
    tone: Tone | None = None
    voice: bool = False   # a talking moment: its own sound up front, the music dipped under it, its words captioned
    flash: bool = False   # a 0.1-0.3 s glimpse in a burst of very fast cuts (not snapped to the beat)
    mono: bool = False    # this shot in high-contrast black and white (one standout moment)
    big_captions: bool = False   # a talking shot's words big, bold and centred (a chant, a punchline)
    # a collage: the frame split into vertical strips, all playing at once; left to right: this shot, then these other
    # moments (source seconds) in order
    panels: list[float] = Field(default_factory=list, max_length=5)
    panel_ends: list[float] = Field(default_factory=list, max_length=6)   # (set by Cascade: where each strip's clip ends)
    hard_end: bool = False     # (set by Cascade: the request says where this talking shot stops; it is not stretched to a beat)
    said_until: float = 0      # (set by Cascade: no word starting after this is captioned, in source seconds)
    said_word: str = ''        # (set by Cascade: a misheard shout, captioned as the word the request names...)
    said_from: float = 0       # (...for the transcript words between these source seconds)
    said_to: float = 0
    # a collage's strips, left to right (this shot, then its panels): where to look across each (0-1) and how far to zoom in
    panel_focus: list[float] = Field(default_factory=list, max_length=6)
    panel_zoom: list[float] = Field(default_factory=list, max_length=6)
    panel_who: list[str] = Field(default_factory=list, max_length=6)   # (set by Cascade from the request: who each strip frames)
    carry_sound: bool = False  # this shot plays the previous shot's sound carrying on (the chant heard over the last picture)
    carry_until: float = 0     # (set by Cascade: the carried sound stops here, where the previous moment's clip ends)
    silhouette: bool = False   # a bright splash: the background flashes to cream and the people become cut-out silhouettes
    # the people of this shot cut out and standing in front of another moment (source second of that background; -1 = none):
    # the same person over changing places, like a travel edit's ending
    backdrop: float = -1.
    voice_through: float = Field(default=0, ge=0, le=4)   # its own sound keeps playing this long over the next shots


class VisualPlan(BaseModel):
    model_config = ConfigDict(extra='ignore')
    kind: Literal['visual'] = 'visual'
    reply: str = Field(default='', max_length=1500)
    title: str = Field(default='', max_length=60)
    # 'typed': a big place name typed out letter by letter over the opening shot; 'corners': the title's words pop in
    # white in the top corners one after another and its last word lands huge and red behind the people (a lyric-video opener)
    title_style: Literal['small', 'typed', 'corners'] = 'small'
    # the big word of a "corners" title; 'dark blue': a deep blue word with a thick, darker navy outline
    title_color: Literal['red', 'blue', 'dark blue', 'water', 'yellow', 'green', 'white'] = 'red'
    shots: list[VisualShot] = Field(min_length=1, max_length=64)
    mood: Literal['awakening', 'wonder', 'tension', 'warm'] = 'awakening'
    grade: Literal['cinema', 'forest', 'night', 'vintage', 'bw', 'cold', 'red', 'warm', 'natural', 'film'] = 'cinema'
    bars: bool = False   # cinematic letterbox bars (a 2.39:1 picture inside the frame)
    sound: Literal['both', 'score', 'original'] = 'both'   # music over the clip's own sound, music only, or only the clip's sound
    song: str = Field(default='', max_length=40)          # a Music Library song id; '' = Cascade's composed score
    song_section: int = Field(default=0, ge=0, le=5)       # which of that song's candidate sections plays
    lyrics: Literal['off', 'bold', 'serif', 'glitch', 'typewriter'] = 'off'   # the song's sung words on screen, as they are sung
    intro: Literal['none', 'black'] = 'none'               # 'black': open on black while the music builds, first shot on the beat
    settings: Settings = Field(default_factory=Settings)
    end_line: str = Field(default='', max_length=90)
    clip_order: list[int] = Field(default_factory=list, max_length=20)   # the request's order of the joined clips (1-based)
    outro: str = Field(default='', max_length=20)   # an ending word ("CASCADE"): pops in with a bing, then the camera zooms into it
    transition_sounds: bool = True   # whooshes under the designed transitions (off: the song and voices only)
    fade_out: bool = False  # the film fades to black at its end
    loop: bool = False      # end on a short return to the opening shot and title, so the reel plays as a seamless loop
    seconds: float = Field(default=0, ge=0, le=60)   # the edit's length when the user asked for one; 0 = the house length
    hard_length: bool = False   # (set by Cascade: the request gives that length as a maximum: it is never stretched)
    # a reference edit's line, building word by word in small white italics (a word in capitals lands bigger, on a new line)
    line: str = Field(default='', max_length=80)
    line_from: float = 0       # edit seconds: the first word appears...
    line_to: float = 0         # ...the last word appears...
    line_until: float = 0      # ...and the line clears
    exact: bool = False        # (a reference edit: every shot keeps the reference's exact length; nothing is refitted)
    # the inspo's paper: the opening shots laid out small on crumpled paper with a line above and below, the paper
    # tearing open into the next shot, and the last shot wrapping back onto the paper
    paper_until: float = 0     # edit seconds the paper layout lasts from the start (0 = no paper)
    paper_top: str = Field(default='', max_length=30)
    paper_bottom: str = Field(default='', max_length=40)
    paper_word_at: float = 0   # when the bottom line lands (with a white flash)
    tear: float = Field(default=0, ge=0, le=2)        # how long the paper takes to tear open after the layout
    paper_end: float = Field(default=0, ge=0, le=3)   # the last this-many seconds wrap back onto the paper
    music_from: float = Field(default=0, ge=0, le=10)  # the song starts this many seconds in (a spoken opening first)

    @model_validator(mode='after')
    def _tidy(self):
        self.end_line = self.end_line.strip().rstrip('.')
        for s in self.shots:
            if s.voice: s.speed = 1.   # speech plays at its own speed
            if s.effect == 'glowpop': s.mono = False   # it ends in its colourful background
        # captions are drawn for the talking shots only (speech_captions); the dialogue caption track stays off
        self.settings.captions = False
        if any(s.voice for s in self.shots) and self.sound == 'score': self.sound = 'both'
        # a coloured title word only exists in the corners style (the typed title is always cream)
        if self.title_color != 'red' and self.title_style == 'typed': self.title_style = 'corners'
        return self


def check(plan, duration, windows=None, cuts=(), parts=None):
    """Raises ValueError naming what is wrong, in words a planner can fix. A shot edge a few frames from a
    camera cut moves onto the cut, so no shot opens or closes on a flash of the neighbouring camera shot. With
    `parts` (the joined clips) and a clip_order, the shots must play those clips in that order, none left out."""
    for s in plan.shots:
        for c in cuts:
            if s.start < c < s.start+.35 and s.end-c >= .3: s.start = c
            if s.end-.35 < c < s.end and c-s.start >= .3: s.end = c
    for k, s in enumerate(plan.shots):
        if not s.flash and s.end-s.start < .3:   # too short to see: grow it to 0.3 s inside its own clip
            clip = next((p for p in parts or [] if p['from']-.05 <= s.start < p['to']), None)
            top = clip['to'] if clip else duration
            s.end = min(top, s.start+.31)
            if s.end-s.start < .3: s.start = max(clip['from'] if clip else 0., s.end-.31)
        if s.end > duration+.05: raise ValueError(f'shots[{k}]: ends at {s.end:.1f} s but the clip is {duration:.1f} s long')
        if s.end-s.start < (.08 if s.flash else .3)-1e-6:
            raise ValueError(f'shots[{k}]: needs end at least {.08 if s.flash else .3} s after start')
        if any(not 0 <= p <= duration-.3 for p in s.panels):
            raise ValueError(f'shots[{k}]: panels must be source seconds inside the clip (0-{duration-.3:.1f})')
        if windows and not any(s.start >= a-.05 and s.end <= b+.05 for a, b in windows):
            raise ValueError(f'shots[{k}]: {s.start:.1f}-{s.end:.1f} s is outside the usable ranges {windows}')
    for s in plan.shots: s.end = min(s.end, duration)
    if parts and plan.clip_order:
        n = len(parts)
        if any(not 1 <= c <= n for c in plan.clip_order): raise ValueError(f'clip_order: use clip numbers 1-{n}')
        which = lambda s: next((k+1 for k, p in enumerate(parts) if p['from']-.05 <= s.start < p['to']), 0)
        exact = re.compile(r'\d{1,2}:\d{2}(?:[.:]\d{1,3})?\s*(?:-|–|to)\s*\d{1,2}:\d{2}')   # a clip the user timed to the frame
        for s in plan.shots:   # it plays from the start the user gave ("as she finishes the E" is the range's start)
            c = which(s)
            if c and not s.voice and not s.flash and exact.search(parts[c-1]['title']) and s.start > parts[c-1]['from']+.15:
                length = s.end-s.start
                s.start = round(parts[c-1]['from']+.02, 3); s.end = round(min(parts[c-1]['to']-.02, s.start+length), 3)
            at = lambda x: next((k for k, p in enumerate(parts) if p['from']-.05 <= x < p['to']), None)
            s.panels = [round(parts[k]['from']+.02, 3) if k is not None and exact.search(parts[k]['title']) else x
                        for x, k in ((x, at(x)) for x in s.panels)]   # (collage strips from a timed clip too)
        for s in plan.shots:   # a shot whose seconds fall outside the clip it names moves into that clip (same length)
            if 1 <= s.clip <= n and which(s) != s.clip and not s.voice:
                p = parts[s.clip-1]
                length = min(s.end-s.start, p['to']-p['from']-.04)
                s.start = round(p['from']+.02, 3); s.end = round(s.start+length, 3)
        played, strips = [], set()
        for k, s in enumerate(plan.shots):
            c = which(s)
            if c and s.end > parts[c-1]['to']+.1:   # a shot that runs into the next clip stops at its own clip's end
                s.end = parts[c-1]['to']-.02
                if s.end-s.start < .3: s.start = max(parts[c-1]['from'], s.end-max(.3, min(1., s.end-parts[c-1]['from'])))
                if s.end-s.start < .08: raise ValueError(f"shots[{k}]: starts at the very end of clip {c}; start it earlier in that clip")
            if c and not s.flash and (not played or played[-1] != c): played.append(c)
            strips.update(which(type('P', (), {'start': x})) for x in s.panels)   # a collage plays its strips' clips too
        want = list(dict.fromkeys(plan.clip_order))
        # Cascade repairs what the planner missed rather than refusing the plan: every clip the request names gets a
        # shot (a short one from its middle), and the shots are put in the requested order
        missing = [c for c in want if c not in played and c not in strips]
        groups = {}
        for x in plan.shots:
            groups.setdefault(which(x) or 0, []).append(x)
        for c in missing:
            p = parts[c-1]
            mid, room = (p['from']+p['to'])/2, min(.8, p['to']-p['from'])
            groups[c] = [VisualShot(start=round(max(p['from'], mid-room/2), 3), end=round(min(p['to'], mid+room/2), 3))]
        for c in list(groups):   # a plain shot of a clip already shown as a collage strip is a repeat
            if c in strips and groups[c] and all(not (x.voice or x.effect or x.panels or x.silhouette) for x in groups[c]):
                groups[c] = []
        for c, xs in groups.items():   # each named clip once: the planner's repeats of a picture go (talking moments stay whole)
            if c and c in want and len(xs) > 1 and not any(x.voice for x in xs):
                keep = next((x for x in xs if x.effect or x.panels or x.silhouette), xs[0])
                groups[c] = [keep]
        ordered = [x for c in want for x in groups.pop(c, [])]
        plan.shots = ordered+[x for c, xs in groups.items() for x in xs if c not in want] if ordered else plan.shots
        played = [which(x) for x in plan.shots]


def story_edges(plan, words, parts=None, most=4.):
    """A montage opens and ends on people: the first and last shots are talking shots when they are mostly speech
    (an intro, a chant), and with a requested clip order the ending plays to the end of its clip (its payoff),
    at most `most` s longer."""
    shots = [s for s in plan.shots if not s.flash]
    if not shots: return plan
    for s in {id(x): x for x in (shots[0], shots[-1])}.values():
        spoken = sum(max(0., min(w['e'], s.end)-max(w['s'], s.start)) for w in words or [])
        if spoken >= .5*(s.end-s.start): s.voice, s.speed = True, 1.
    first = shots[0]
    if first.voice and words:   # an opening intro starts at its first word ("Hey guys, this is ..."), inside its own clip
        clip = next((p for p in parts or [] if p['from']-.05 <= first.start < p['to']), None)
        before = [w for w in words if w['s'] < first.start and (clip is None or w['s'] >= clip['from'])]
        ends = lambda w: w['w'].rstrip('"\'”’').endswith(('.', '?', '!'))
        k = len(before)
        if k and first.start-before[-1]['e'] < .6:
            if not ends(before[-1]):   # the shot starts mid-sentence: back to that sentence's start
                while k > 1 and not ends(before[k-2]) and before[k-1]['s']-before[k-2]['e'] < .6: k -= 1
                k -= 1
            else:   # it starts a sentence: take in one short greeting just before it ("Hey, guys."), no more
                j = k-1
                while j > 0 and not ends(before[j-1]) and before[j]['s']-before[j-1]['e'] < .6: j -= 1
                if k-j <= 3: k = j
            if k < len(before): first.start = max(clip['from'] if clip else 0., before[k]['s']-.1)
    if parts and plan.clip_order:
        last = shots[-1]
        clip = next((p for p in parts if p['from']-.05 <= last.start < p['to']), None)
        if clip and 0 < clip['to']-last.end <= most: last.end = clip['to']-.05
    return plan


DIGITS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']


def spoken_tokens(word):
    """A transcript word as spoken words: transcription writes a counted "one two three" as "123." or "3."."""
    import re
    w = re.sub(r"[^a-z0-9']", '', word.lower())
    return [DIGITS[int(c)] for c in w] if w.isdigit() and len(w) <= 3 else [w]


def ending_transition(plan):
    """A push into the ending belongs on the ending: when the edit ends on a dive and the planner put the circle push
    (iris) on an earlier shot, it moves to the dive (aimed at the dive's focus)."""
    if len(plan.shots) < 2 or plan.shots[-1].zoom != 'dive' or plan.shots[-1].effect == 'iris': return plan
    early = [x for x in plan.shots[:-1] if x.effect == 'iris']
    if early:
        for x in early: x.effect = None
        plan.shots[-1].effect = 'iris'
    return plan


def keep_in_clips(plan, parts):
    """Shots stay inside their own clip (a sentence run on to its end may otherwise spill into the next clip)."""
    for x in plan.shots:
        clip = next((p for p in parts or [] if p['from']-.05 <= x.start < p['to']), None)
        if clip and x.end > clip['to']: x.end = clip['to']-.02
    return plan


def text_requests(plan, request):
    """Text the request asks for in so many words: "big text" / "make the text bigger" on the last talking moment
    (a chant, a punchline) shows its words big and centred."""
    import re
    if re.search(r'fade\s*(out\s*)?(in)?to\s+black|\bfades?\s+(out|black)\b|ends?\s+(it\s+)?in\s+black', request or '', re.I):
        plan.fade_out = True
    if plan.shots and not plan.shots[-1].voice and re.search(
            r'(audio|sound|background|voices?|them\s+speaking|chant)[^.]{0,60}\b(still|keep|keeps|continue|continues|carr(y|ies)|run|runs|go(es|ing)?\s+on|till\s+the\s+end)', request or '', re.I):
        plan.shots[-1].carry_sound = True   # the last moment's sound carries on over the ending picture
    if re.search(r'colou?rful|\b(no|not|without|don\'?t|do\s+not)\b[^.]{0,20}black\s+(and|&)\s+white|\bin\s+colou?r\b', request or '', re.I):
        for s in plan.shots: s.mono = False   # the request wants colour
    if re.search(r'\b(big|bigger|large|huge)\s+text\b|\btext\s+(much\s+)?bigger\b', request or '', re.I):
        talking = [s for s in plan.shots if s.voice]
        if talking:
            last = talking[-1]
            for s in plan.shots:   # (the whole last talking moment, every beat piece of it)
                if s.voice and s.start >= last.start-6 and s is not talking[0] or s is last: s.big_captions = True
    return plan


def stop_at(plan, words, request):
    """Where the request says talking starts and stops: "stop the intro at presentation prep" ends the talking shot
    that says those words right after them, before the next word ("I" never sneaks in); "start (the last part) from
    one two three" starts the last talking shot right before those words; "end right after the one two three" ends
    the last talking shot after them (with a beat more, so the moment lands: hands going up). A stopped shot keeps
    its exact end (hard_end) instead of being stretched to the next beat."""
    import re
    if not words: return plan
    said, owner = [], []   # spoken tokens and the transcript word each came from
    for k, w in enumerate(words):
        for tok in spoken_tokens(w['w']): said.append(tok); owner.append(k)
    ending = r"(?=\s*(?:[,.;]|\band\b|\bthen\b|\bwhen\b|\bwith\b|$))"
    phrase = r"[\"'“]?([a-z0-9' ]{3,60}?)[\"'”]?"+ending
    rules = [('stop', r"\bstop(?:s|ping)?\b[^.;]*?\b(?:at|after)\s+(?:the\s+)?"+phrase, .2, False),
             ('end', r"\bend(?:s|ing)?\s+(?:it\s+)?(?:right\s+|just\s+)?after\s+(?:the\s+|we\s+say\s+|they\s+say\s+)?"+phrase, .9, True),
             ('say', r"\bwhen\s+(?:we|they|you)\s+(?:all\s+)?(?:say|shout|yell)\s+"+phrase, .35, True),
             ('start', r"\bstart(?:s|ing)?\b(?:\s+(?:it|the\s+\w+(?:\s+\w+)?))?\s+(?:right\s+|just\s+)?(?:from|at|with)\s+(?:the\s+|when\s+we\s+say\s+)?"+phrase, .12, True)]
    rules = [r for r in rules if r[0] == 'start']+[r for r in rules if r[0] != 'start']   # where it starts, before where it ends
    for kind, pattern, pad, last in rules:
        m = re.search(pattern, request or '', re.I)
        if not m: continue
        target = re.findall(r"[a-z0-9']+", m.group(1).lower())
        talking = [s for s in plan.shots if s.voice]
        if kind == 'say' and len(target) == 1 and talking:   # one shouted word may be misheard ("Cascade!" -> "Custade."): closest match
            import difflib
            s = talking[-1]
            near = [w for w in words if s.start-.05 <= w['s'] < s.end+3 and len(re.sub(r"[^a-z]", '', w['w'].lower())) >= 4]
            good = [w for w in near if w['s'] >= s.start-.05
                    and difflib.SequenceMatcher(None, target[0], re.sub(r"[^a-z]", '', w['w'].lower())).ratio() >= .55]
            best = good[-1] if good else None   # the last time it is said in the moment (the shout, not "Cascade on three")
            if best:
                s.end = min(best['e'], best['s']+.15)+pad   # the moment turns as the shout starts (hands going up)
                s.said_word, s.said_from, s.said_to = m.group(1).strip(), best['s'], best['e']   # caption it as the word named
            else:   # misheard beyond recognition ("Cut thee."): the word shouted right after a count ("... three, Cascade!")
                span = [w for w in words if s.start-.05 <= w['s'] < s.end+3]
                k = next((i for i, w in enumerate(span) if spoken_tokens(w['w'])[-1] == 'three'), None)
                if k is not None and k+1 < len(span):
                    j = k+1
                    while j+1 < len(span) and span[j+1]['s']-span[j]['e'] < .3 and span[j+1]['s']-span[k+1]['s'] < 1.5: j += 1
                    s.end = min(span[j]['e'], span[k+1]['s']+.15)+pad   # the moment turns as the shout starts (hands going up)
                    s.said_word, s.said_from, s.said_to = m.group(1).strip(), span[k+1]['s'], span[j]['e']   # caption it as said
            continue
        for s in (talking[-1:] if last else talking):
            reach = 6 if kind == 'start' else 3
            for i in range(len(said)-len(target)+1):
                first, last_word = owner[i], owner[i+len(target)-1]
                if said[i:i+len(target)] == target and s.start-reach <= words[first]['s'] < s.end+reach:
                    if kind == 'start':
                        s.start = max(0., words[first]['s']-pad)
                    elif kind == 'say':   # "when we say Cascade, fade into ...": the moment ends just after the word
                        if words[first]['s'] >= s.start: s.end = words[last_word]['e']+pad
                    else:
                        j = last_word
                        stop = words[j]['e']+pad
                        if kind == 'stop':   # the word is said in full (a breath of the next one at most), and nothing after it is captioned
                            stop = words[j]['e']+.12
                            if j+1 < len(words) and words[j+1]['s'] > words[j]['e']-.05:   # never into the next word said
                                stop = min(stop, max(words[j]['e'], words[j+1]['s']-.02))
                            s.said_until = words[j]['s']+.03   # (by start: the next word may overlap its end)
                        s.end = min(s.end, stop) if kind == 'stop' else stop
                        if kind == 'stop': s.hard_end = True
                    break
            else:
                continue
            break
    return plan


NEAR = 2.5   # seconds: two shots whose source moments are this close read as one long shot when played back to back


def _near(a, b):
    """True when shot b picks up where shot a left off (or overlaps it) in the source."""
    return b.start < a.end+NEAR and a.start < b.end+NEAR


def interleave(plan, budget=20000):
    """Reorder so no two shots in a row come from the same moment of the source (that plays as one slow, long
    hold, not a cut). The opening shot stays first and the closing shot last; between them, the order closest to
    the plan with no neighbours from the same moment wins (a short search). When no such order exists, the one
    with the fewest same-moment neighbours is used."""
    shots = list(plan.shots)
    if len(shots) < 3: return plan
    head = max([0]+[k for k, x in enumerate(shots[:-1]) if x.flash])   # the opening and its burst of glimpses stay put
    fixed, last, middle = shots[:head+1], shots[-1], shots[head+1:-1]
    if not middle: return plan
    first = fixed[-1]
    best = {'order': None, 'bad': len(shots)}
    steps = [0]

    def search(order, left, bad):
        steps[0] += 1
        if bad >= best['bad'] or steps[0] > budget: return
        if not left:
            bad += _near(order[-1], last)
            if bad < best['bad']: best.update(order=list(order), bad=bad)
            return
        for s in sorted(left, key=lambda s: _near(order[-1], s)):   # planned order, clean neighbours first
            left.remove(s); order.append(s)
            search(order, left, bad+_near(order[-2], s))
            order.pop(); left.append(s); left.sort(key=middle.index)
            if best['bad'] == 0: return

    search([first], list(middle), 0)
    if best['order'] is not None: plan.shots = fixed[:-1]+best['order']+[last]
    return plan


def whole_phrases(plan, words, gap=.6, most=6., cuts=()):
    """Talking shots start and end on sentence edges: a shot that would cut into speech grows to the edges of the
    sentence it touches (words closer than `gap` s run on, up to the full stop), at most `most` s each way, never across a camera cut
    (a clip made of several clips: the next clip is another moment)."""
    if not words: return plan
    for s in plan.shots:
        if not s.voice: continue
        inside = [w for w in words if w['e'] > s.start and w['s'] < s.end]
        if not inside: continue
        first, last = words.index(inside[0]), words.index(inside[-1])
        ends = lambda w: w['w'].rstrip('"\'”’').endswith(('.', '?', '!'))   # a sentence ends here: the shot may stop
        while first > 0 and not ends(words[first-1]) and words[first]['s']-words[first-1]['e'] < gap and s.start-words[first-1]['s'] < most: first -= 1
        while last+1 < len(words) and not ends(words[last]) and words[last+1]['s']-words[last]['e'] < gap and words[last+1]['e']-s.end < most: last += 1
        start, end = min(s.start, max(0., words[first]['s']-.12)), max(s.end, words[last]['e']+.25)
        before = [c for c in cuts if start < c <= s.start+.05]
        after = [c for c in cuts if s.end-.05 <= c < end]
        s.start = max(before) if before else start
        s.end = min(after) if after else end
        inner = [c for c in cuts if s.start+.5 < c < s.end-.05]   # the planned shot itself ran over a cut
        if inner and s.end-inner[0] < (inner[0]-s.start): s.end = inner[0]
    return plan


def shortest(plan):
    """The least time the planned shots can take once quick shots are at their shortest: talking shots, designed
    shots (with room for their transition) and every other shot at QUICKEST."""
    total = 0.
    for x in plan.shots:
        on = (x.end-x.start)/x.speed
        if x.panels: total += max(on, 1.1)
        elif x.voice or x.silhouette: total += on
        elif x.effect in EFFECT_SECONDS: total += max(on, EFFECT_SECONDS[x.effect]+.3)
        elif x.flash: total += min(on, .3)
        else: total += min(on, QUICKEST)
    return total


def length(plan):
    return sum((s.end-s.start)/s.speed for s in plan.shots)


def fit(plan, seconds, beat=None, grid=None, lead=0.):
    """Make the edit play in at most `seconds` (a black intro of `lead` seconds included): later shots go, the last
    one is trimmed. Every cut lands on `grid` (edit times, e.g. a song's beats and half-beats) or on the half-beat
    grid of `beat`."""
    # an ending word said in the last talking shot lands inside it (only its zoom runs past the shot)
    ends_talking = bool(plan.shots) and plan.shots[-1].voice
    real = seconds-lead-(LOOP if plan.loop else 0)-((OUTRO*.4 if ends_talking else OUTRO) if plan.outro.strip() else 0)
    budget = real-(.5 if plan.hard_length else 0)   # (a hard limit keeps room for the cuts snapping to the beat)
    for s in plan.shots:   # a burst glimpse lasts 0.1-0.3 s whatever was planned
        if s.flash: s.end = s.start+min(.3, max(.1, s.end-s.start))*s.speed
    # too long: music shots from the middle go first (latest first); talking shots, the opening and the ending stay
    on = lambda x: (x.end-x.start)/x.speed
    over = sum(map(on, plan.shots))-budget
    designed = lambda x: x.silhouette or x.panels or x.effect in ('cutin', 'glowpop', 'window', 'slices', 'iris')   # these need their time
    middle = [k for k, x in enumerate(plan.shots) if 0 < k < len(plan.shots)-1 and not x.voice and not x.flash and not designed(x)]
    for k, x in enumerate(plan.shots):   # a designed transition gets at least its own length plus a beat; a collage plays a second
        need = EFFECT_SECONDS.get(x.effect, 0)+.3 if x.effect in EFFECT_SECONDS else 0
        if x.panels: need = max(need, 1.1)
        if need and on(x) < need: plan.shots[k] = x.model_copy(update={'end': x.start+need*x.speed})
    last = plan.shots[-1] if plan.shots else None   # an ending that is not talking gives up time before any named clip
    over = sum(map(on, plan.shots))-budget
    if over > 0 and last is not None and not last.voice and on(last) > 1.:
        plan.shots[-1] = last.model_copy(update={'end': last.start+max(1., on(last)-over)*last.speed})
    over = sum(map(on, plan.shots))-budget
    room = sum(max(0., on(plan.shots[k])-QUICKEST) for k in middle)
    if over > 0 and room > 0:   # first shorten every quick shot in proportion (down to QUICKEST)
        share = min(1., over/room)
        for k in middle:
            x = plan.shots[k]
            cut = max(0., on(x)-QUICKEST)*share
            plan.shots[k] = x.model_copy(update={'end': x.end-cut*x.speed})
    while sum(map(on, plan.shots)) > budget+1e-6:
        # (a silhouette or a collage is a designed moment the request asked for: it is never the one dropped)
        middle = [k for k, x in enumerate(plan.shots) if 0 < k < len(plan.shots)-1 and not x.voice and not designed(x)]
        if not middle or sum(on(plan.shots[k]) for k in middle) <= SHORTEST: break
        k = middle[-1]
        over = sum(map(on, plan.shots))-budget
        if on(plan.shots[k])-over >= SHORTEST:   # trimming this shot is enough
            x = plan.shots[k]; plan.shots[k] = x.model_copy(update={'end': x.end-over*x.speed}); break
        plan.shots.pop(k)
    shots, used = [], 0.
    for s in plan.shots:
        on_screen = (s.end-s.start)/s.speed
        if used+on_screen > budget:
            room = budget-used
            if room >= SHORTEST: shots.append(s.model_copy(update={'end': s.start+room*s.speed})); used += room
            break
        shots.append(s); used += on_screen
    if grid is None and beat:
        grid = [k*beat/2 for k in range(int(seconds/(beat/2))+2)]
    if grid:
        points = sorted(g for g in grid if lead+.3 <= g <= seconds+1e-6)
        t, snapped = lead, []
        for s in shots:
            if s.flash:   # burst glimpses keep their own length; the beat grid picks up again after them
                snapped.append(s); t += (s.end-s.start)/s.speed; continue
            target = t+(s.end-s.start)/s.speed
            options = [g for g in points if g-t >= .33]
            if not options: break
            # a talking shot ends on the first beat after its words, never before (a word cut off sounds broken)
            later = [g for g in options if g >= target-.04] if (s.voice and not s.hard_end) or designed(s) else []
            end = min(later) if later else min(options, key=lambda g: abs(g-target))
            if s.hard_end: end = min([g for g in options if g <= target+.02] or [target], key=lambda g: abs(g-target))
            snapped.append(s.model_copy(update={'end': s.start+(end-t)*s.speed})); t = end
        shots = _on_the_beat(snapped, points, lead, hold_first=plan.title_style in ('typed', 'corners'), fade=plan.fade_out) if snapped else shots
    plan.shots = shots
    return length(plan)+lead


LONGEST = 1.8   # seconds a music edit holds one shot before cutting again on the beat


def _on_the_beat(shots, points, lead, hold_first=False, fade=False):
    """Long holds become jump cuts on the beat: the same moment carries on, the framing punches in and out,
    so the picture moves with the music (effects and words stay on the first piece)."""
    out, t = [], lead
    for n, s in enumerate(shots):
        end = t+(s.end-s.start)/s.speed
        if end-t <= LONGEST+.05 or (n == 0 and hold_first) or s.zoom in ('dive', 'rise') or s.carry_sound or (n == len(shots)-1 and fade):   # a typed title holds its opening; a dive or rise is one move
            out.append(s); t = end; continue
        cuts, last = [], t
        for g in points:
            if last+.85 <= g <= end-.6: cuts.append(g); last = g
        bounds = [t]+cuts+[end]
        for k, (a, b) in enumerate(zip(bounds, bounds[1:])):
            piece = {'start': s.start+(a-t)*s.speed, 'end': s.start+(b-t)*s.speed}
            if k:
                piece.update(effect=None, text='', zoom='punch' if k % 2 else ('push' if s.zoom == 'none' else s.zoom))
            out.append(s.model_copy(update=piece))
        t = end
    return out


def song_timing(plan, seconds):
    """(song, where it starts, the cut grid in edit seconds, the black intro length) for a plan with a song, else None."""
    if not plan.song: return None
    from . import music
    song = music.find(plan.song)
    if not song: return None
    options = music.sections(song, seconds)
    start = options[min(plan.song_section, len(options)-1)]
    beats = [b-start for b in song.get('beats', []) if start <= b <= start+seconds+2]
    if len(beats) > 2 and beats[-1] < seconds+2:   # the song is shorter than the edit (it loops): keep the beat going
        period = float(np.median(np.diff(beats)))
        while beats[-1] < seconds+2: beats.append(beats[-1]+period)
    grid = sorted(set(beats+[(a+b)/2 for a, b in zip(beats, beats[1:])]))
    lead = 0.
    if plan.intro == 'black':
        drop = song.get('drop')
        if drop is not None and 1. <= drop-start <= 5.: lead = drop-start          # black until the drop
        else: lead = next((b for b in beats if b >= 1.2), 1.5)                     # or the first beat after a moment
    return song, start, grid, lead


def auto(prep, windows=None, seconds=15.):
    """The rule-based visual edit: the moments with the most movement, in story (source) order."""
    motion = prep.get('motion') or [1]*max(1, int(prep['duration']))
    duration = prep['duration']
    inside = lambda t: not windows or any(a <= t and t+1.5 <= b for a, b in windows)
    starts = [float(t) for t in range(0, max(1, int(duration-1.5))+1) if inside(t)] or [0.]
    ranked = sorted(starts, key=lambda t: -sum(motion[int(t):int(t)+2]))
    picked = []
    for t in ranked:
        if all(abs(t-p) >= 2 for p in picked): picked.append(t)
        if len(picked)*1.6 >= seconds: break
    shots = [VisualShot(start=t, end=min(duration, t+1.6), zoom='push' if n % 2 else 'none') for n, t in enumerate(sorted(picked))]
    return VisualPlan(title='', shots=shots, reply='Nobody speaks in this clip, so I cut together its liveliest moments.')


def lyric_lines(song, start, end, style):
    """The song's sung words from `start` as on-screen lines (edit times), each building word by word."""
    from . import music
    words = [w for w in music.words_between(song, start, start+end) if w['s']-start < end-.2]
    most = 2 if style in ('bold', 'glitch') else 5   # big styles show two words at a time, so they stay big
    lines, run = [], []
    for w in words:
        if run and (w['s']-run[-1]['e'] > .55 or len(run) >= most or run[-1]['w'].rstrip().endswith(('.', ',', '?', '!'))):
            lines.append(run); run = []
        run.append(w)
    if run: lines.append(run)
    out = []
    for n, line in enumerate(lines):
        t0 = line[0]['s']-start-.04
        t1 = min(end, line[-1]['e']-start+.45, (lines[n+1][0]['s']-start-.06) if n+1 < len(lines) else end)
        if t1-t0 > .2:
            out.append(Overlay(t0, t1, 'lyric', {'style': style, 'words': [(w['w'].strip(',.'), w['s']-start) for w in line]}))
    return out


def _natural(samples, sr, shots, total, source=None):
    """The clip's own sound under each shot (muted under slow or fast motion), with short fades so cuts do not click.
    A shot made from another file (a collage) has no sound of its own here; a shot with `audio_src` plays that moment's
    sound instead of its own (a moment heard carrying on over the next picture)."""
    out = np.zeros((int(total*sr), 2), np.float32)
    fade = int(.012*sr)
    for s in shots:
        carry = getattr(s, 'audio_src', None)
        if s.kind != 'aroll' or (abs(s.rate-1) > .01 and carry is None): continue
        if carry is None and source is not None and str(s.path) != str(source): continue
        a, n = int((carry if carry is not None else s.src)*sr), int((s.t1-s.t0)*sr)
        until = getattr(s, 'audio_until', None)
        if carry is not None and until: n = max(0, min(n, int(until*sr)-a))   # the carried moment's clip ends here
        piece = samples[a:a+n].copy()
        if not len(piece): continue
        ramp = np.linspace(0, 1, min(fade, len(piece)//2), dtype=np.float32)[:, None]
        if len(ramp): piece[:len(ramp)] *= ramp; piece[-len(ramp):] *= ramp[::-1]
        i = int(s.t0*sr)
        out[i:i+len(piece)] += piece[:len(out)-i]
    return out


def _split(natural, voiced, sr):
    """The clip's own sound split into the talking shots (with short fades) and everything else."""
    mask = np.zeros(len(natural), np.float32)
    ramp = int(.06*sr)
    for a, b, *_ in voiced:
        i, j = int(a*sr), min(len(mask), int(b*sr))
        if j <= i: continue
        mask[i:j] = 1
        k = min(ramp, (j-i)//2)
        if k: mask[i:i+k] = np.linspace(0, 1, k); mask[j-k:j] = np.linspace(1, 0, k)
    return natural*mask[:, None], natural*(1-mask)[:, None]


def speech_captions(words, voiced, most=4):
    """The words said in the talking shots, as short caption lines that build word by word as they are said.
    A shot marked big_captions shows its words big, bold and centred, two at a time."""
    timed, seen = [], set()
    for a, b, src, *flags in voiced:
        big = bool(flags and flags[0])
        until = flags[1] if len(flags) > 1 and flags[1] else None   # nothing said after this is captioned
        fix = flags[2] if len(flags) > 2 and flags[2] and flags[2][0] else None   # a misheard shout, captioned as named
        run_end = b   # captions end with their talking moment (the run of pieces it was cut into)
        for a2, b2, src2, *_ in voiced:
            if abs(a2-run_end) < .05 and abs((src2-a2)-(src-a)) < .05: run_end = b2
        for w in words:   # a word belongs to the piece it starts in (beat cuts split a moment into pieces)
            if src-.02 <= w['s'] < src+(b-a)-.02 and id(w) not in seen and (until is None or w['s'] <= until):
                seen.add(id(w))
                if fix and fix[1]-.02 <= w['s'] <= fix[2]:   # the shout the edit cuts on is heard, not captioned
                    continue
                toks = spoken_tokens(w['w'])
                if toks[0] in DIGITS and len(toks) > 1:   # "123." said as one two three: each its own subtitle, in turn
                    after = next((x['s'] for x in words if x['s'] > w['s']+.01), w['e']+.6)   # (the count runs up to the next word)
                    step = max(w['e']-w['s'], min(after-w['s'], 1.2))/len(toks)
                    for k, tok in enumerate(toks):
                        timed.append((tok, a+w['s']+k*step-src, a+w['s']+(k+1)*step-src, big, run_end))
                    continue
                text = toks[0] if w['w'].strip('.,!?').isdigit() else w['w'].strip()
                timed.append((text, a+w['s']-src, a+w['e']-src, big, run_end))
    lines, run = [], []
    for item in sorted(timed, key=lambda x: x[1]):
        if run and (item[1]-run[-1][2] > .45 or len(run) >= (1 if item[3] else most) or item[3] != run[-1][3]
                    or run[-1][0].endswith(('.', ',', '?', '!'))):
            lines.append(run); run = []
        run.append(item)
    if run: lines.append(run)
    out = []
    for n, line in enumerate(lines):
        t0 = line[0][1]-.05
        t1 = min(line[-1][2]+.35, (lines[n+1][0][1]-.06) if n+1 < len(lines) else line[-1][2]+.35, line[-1][4])
        if t1-t0 > .15:
            out.append(Overlay(t0, t1, 'lyric', {'style': 'bold' if line[0][3] else 'caption',
                                                 'words': [(w.strip(',.'), at) for w, at, *_ in line]}))
    return out


def trim_to_outro(plan, words):
    """An edit that ends on a word said in its last talking shot needs that shot only until the word (plus the
    start of the zoom): the rest is cut before the edit's length is worked out."""
    last = plan.shots[-1] if plan.shots else None
    if not (plan.outro.strip() and last and last.voice and words): return plan
    # look a little past the planned end too: the word may come just after it
    at = outro_word_time(plan, words, [(last.start, last.end+3, last.start)])   # (edit time = source time here)
    if at is not None and at > last.start: last.end = at+OUTRO*.5
    return plan


def outro_word_time(plan, words, voiced):
    """When the ending word is said in the last talking shot ("... one two three, Cascade!"), the edit time it is
    said at, so the word lands on screen with the voice. None otherwise."""
    word = plan.outro.strip().lower()
    if not word or not words or not voiced: return None
    import difflib
    run = [voiced[-1]]   # the whole last talking moment (beat jump cuts split one moment into pieces)
    for v in reversed(voiced[:-1]):
        if abs(v[1]-run[0][0]) > .05: break
        run.insert(0, v)
    near, at = [], {}
    for a, b, src, *_ in run:
        for w in words:
            if src-.02 <= w['s'] < src+(b-a)+(.6 if (a, b) == run[-1][:2] else 0) and id(w) not in at:
                at[id(w)] = a+w['s']-src; near.append(w)
    clean = lambda w: w['w'].strip('.,!?"\'').lower()
    # transcription can mishear a shouted name ("Cascade!" -> "Custained."): take the closest-sounding word in the
    # shot, and after a count ("one two three") the word that follows it
    score = lambda i: difflib.SequenceMatcher(None, word, clean(near[i])).ratio()+(.3 if i and spoken_tokens(near[i-1]['w'])[-1] == 'three' else 0)
    best = max(range(len(near)), key=score, default=None)
    if best is None or len(clean(near[best])) < 4 or score(best) < .5: return None
    return at[id(near[best])]


def person_at(source, at, ffmpeg='ffmpeg', who=''):
    """Where the main person is in the frame at `at`: (centre x, centre y, height), each 0-1, or None. Uses the
    person cut-out model; the largest figure wins, or, given a description (`who`: "the girl in the red coat"), the
    figure the visual search model matches best to it."""
    try:
        import cv2
        from .matte import Matter
        frame = render.grab(source, at, 640, ffmpeg)
        if frame is None: return None
        mask = Matter()(np.ascontiguousarray(frame[..., ::-1]))   # (grab gives BGR; the model takes RGB)
        if mask is None: return None
        binary = (mask > .5).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
        if count < 2: return None
        k = 1+int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        if stats[k, cv2.CC_STAT_AREA] < binary.size*.003: return None
        people = [j for j in range(1, count) if stats[j, cv2.CC_STAT_AREA] >= binary.size*.003]
        if who and len(people) > 1: k = _likeliest(frame, labels, stats, people, who)
        x, y, w, h = stats[k, :4]
        H, W = binary.shape
        return ((x+w/2)/W, (y+h/2)/H, h/H)
    except Exception:
        LOG.warning('could not find the person to zoom on', exc_info=True)
        return None


def _likeliest(frame, labels, stats, people, who):
    """Of the people cut out of a frame, the one the visual search model matches best to a description."""
    from PIL import Image
    from backend.video_search import router
    router.load_models('visual')
    rgb = np.ascontiguousarray(frame[..., ::-1])
    crops = []
    for j in people:
        x, y, w, h = stats[j, :4]
        piece = rgb[y:y+h, x:x+w].copy()
        piece[labels[y:y+h, x:x+w] != j] = 128   # that person alone, on grey
        crops.append(Image.fromarray(piece))
    model = router.visual_model
    pics = model.encode(crops, normalize_embeddings=True)
    text = model.encode([f'a photo of {who}'], normalize_embeddings=True)[0]
    return people[int(np.argmax(pics @ text))]


def collage_clip(source, starts, seconds, W, H, out, ffmpeg='ffmpeg', ends=None, focus=None, zoom=None, who=None):
    """A collage: the frame split into vertical strips, each playing a different moment of the source at once, left to
    right in the order given. Written as a short silent clip at the output size."""
    import subprocess
    n = len(starts)
    ends = ends if ends and len(ends) == n else [None]*n
    order, stops = list(starts), list(ends)   # left to right: the shot itself, then its panels in order
    widths = [W//n]*(n-1)+[W-W//n*(n-1)]
    cmd = [ffmpeg, '-nostdin', '-v', 'error', '-y']
    for a, e in zip(order, stops):   # a strip whose clip is shorter than the collage holds its own last frame
        # (stopping two frames short of the clip's end, so the next clip's first frame never shows in this strip)
        cmd += ['-ss', f'{a:.3f}', '-t', f'{max(.1, min(seconds+.4, (e-a-2/look.FPS) if e else seconds+.4)):.3f}', '-i', str(source)]
    focus = focus if focus and len(focus) == n else [.5]*n
    zoom = zoom if zoom and len(zoom) == n else [1.]*n
    who = (list(who or [])+['']*n)[:n]
    graph = []
    for i, w in enumerate(widths):   # each strip: zoomed in on its subject, cropped around where it is
        z = min(4., max(1., zoom[i]))
        fx, fy = focus[i], .5
        faces = render.find_faces(source, order[i]+.1, ffmpeg)
        half = w/W/2   # each strip is about its person: when no face is in its centred view, it moves onto the biggest face
        if faces and not any(abs(f[0]-fx) < half for f in faces): fx = faces[0][0]
        close = [f for f in faces if f[2] > .07]   # a close-up (faces big in frame)
        if z > 1.05 and close:   # zooming in on a close-up: onto the face nearest the strip's focus, the whole head in view
            face = min(close, key=lambda f: abs(f[0]-fx))
            fx, fy = face[0], min(.6, face[1]+.08)
        found = None if z <= 1.05 or close else person_at(source, order[i]+.1, ffmpeg)
        if who[i]:   # the request names who this strip is about ("the girl in the red coat"): that person, zoomed on
            named = person_at(source, order[i]+.1, ffmpeg, who[i])
            if named: found, z = named, 1.3   # (room for them to move)
        moving = None
        if who[i] and found:   # ...and followed: where they are by the strip's end, the view pans between the two
            span = min(seconds+.3, (stops[i]-order[i]-.15) if stops[i] else seconds+.3)
            moving = (person_at(source, order[i]+span, ffmpeg, who[i]), span) if span > .4 else None
        if z <= 1.05 and not faces:   # no face at all: their figure
            found = person_at(source, order[i]+.1, ffmpeg)
            if found and abs(found[0]-fx) > half: fx = found[0]
            found = None
        if found:
            fx = found[0]
            if z > 1.05:   # zooming in on someone: their whole figure (head and what they hold) stays in view, above the letterbox
                top, height = found[1]-found[2]/2, found[2]
                z = min(z, max(1.2, .55/max(.05, height)))
                fy = top+height*.42
        zw, zh = int(W*z)//2*2, int(H*z)//2*2
        x = int(min(max(0, fx*zw-w/2), zw-w))
        y = int(min(max(0, fy*zh-H/2), zh-H))
        cx = str(x)
        if moving and moving[0]:
            x1 = int(min(max(0, moving[0][0]*zw-w/2), zw-w))
            cx = f"'{x}+({x1-x})*min(1,t/{moving[1]:.3f})'"
        graph.append(f'[{i}:v:0]fps={look.FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},'
                     f'scale={zw}:{zh},crop={w}:{H}:{cx}:{y},setsar=1,tpad=stop_mode=clone:stop_duration={seconds+.5:.3f},'
                     f'trim=duration={seconds+.4:.3f}[s{i}]')
    graph.append(''.join(f'[s{i}]' for i in range(n))+f'hstack=inputs={n}[v]')
    cmd += ['-filter_complex', ';'.join(graph), '-map', '[v]', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '14',
            '-pix_fmt', 'yuv420p', str(out)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    return out


def make(source, plan, out, progress=None, ffmpeg='ffmpeg', ratio='original', lines=1080, faces=True, words=None):
    """Render a VisualPlan over `source` to `out` (mp4). No AI model is called. `words` (the clip's transcript,
    source seconds) caption the talking shots."""
    from .engine import _audio
    clock, timings = time.time(), {}
    def lap(name):
        nonlocal clock
        timings[name] = round(time.time()-clock, 1); clock = time.time()
    options = plan.settings
    ratio = options.ratio or ratio or 'original'
    progress = progress or (lambda a, s: None)
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    info = render.probe(source)
    look.configure(*render.size_for(info['width'], info['height'], ratio, lines))
    W, H = look.W, look.H

    # --- 1. the shots, back to back
    progress(.05, 'Lining up the best moments…')
    timing = song_timing(plan, plan.seconds or settings.get('output.target_seconds', 15) or 15)
    lead = timing[3] if timing else 0.
    shots, overlays, events, t = [], [], [], lead
    made = []     # temporary clips (collages), removed after the render
    voiced = []   # (edit from, edit to, source from) of every talking shot
    if lead:   # the opening black: the music plays, the picture waits for the beat
        first = plan.shots[0]
        shots.append(Shot(0, lead, 'aroll', str(source), first.start, cx=first.focus_x, grade=plan.grade))
        overlays.append(Overlay(0, lead, 'black'))
    for n, v in enumerate(plan.shots):
        dur = (v.end-v.start)/v.speed
        z0, z1 = ZOOMS[v.zoom]
        cx = v.focus_x
        face = render.find_face(source, v.start+(v.end-v.start)/2, ffmpeg) if faces and W < H else None
        if face: cx = face[0]
        path, src = str(source), v.start
        if v.panels:   # the collage is built once as its own short clip, then graded and framed like any shot
            path, src = str(collage_clip(source, [v.start]+list(v.panels), dur*v.speed, W, H, out.with_name(f'collage-{n}.mp4'), ffmpeg,
                                         ends=list(v.panel_ends) or None, focus=list(v.panel_focus) or None, zoom=list(v.panel_zoom) or None, who=list(v.panel_who) or None)), 0.
            made.append(Path(path))
        shots.append(Shot(t, t+dur, 'aroll', path, src, rate=v.speed, cx=cx, zoom0=z0, zoom1=z1,
                          grade='bwhot' if v.mono else plan.grade,
                          # a close-up zooms in on the people where they are; a rise climbs toward the sky
                          face=(v.focus_x*W, v.focus_y*H) if v.zoom in ('close', 'dive') else (W/2, H*.04) if v.zoom == 'rise' else None))
        if v.zoom == 'close': shots[-1].center = True   # the people come to the middle of the frame, big
        if v.backdrop >= 0: shots[-1].backdrop = (str(source), v.backdrop)   # the people of this shot over another place
        if v.voice_through: shots[-1].voice_through = v.voice_through
        if v.zoom == 'dive': shots[-1].ease_in = True   # the whole subject first, then the plunge
        if v.silhouette:
            overlays.append(Overlay(t, min(t+dur, t+.55), 'silhouette'))
            events.append((t, 'flash', 'calm'))
        if v.voice: voiced.append((t, t+dur, v.start, v.big_captions, v.said_until, (v.said_word, v.said_from, v.said_to)))
        if v.carry_sound:   # it plays the previous moment's sound (set below), up to where that clip ends
            shots[-1].carry = True
            shots[-1].audio_until = v.carry_until or None
        tone = v.tone or look.tone_of(v.text, None) or 'calm'
        if v.effect and n:
            data = {'kind': v.effect}
            if v.effect == 'iris': data['center'] = (v.focus_x*W, v.focus_y*H)
            if v.effect in ('cutin', 'glowpop', 'fade', 'iris') and len(shots) > 1:   # the previous shot keeps playing underneath
                prev = shots[-2]
                data['under'] = Shot(t, t+EFFECT_SECONDS[v.effect], prev.kind, prev.path, prev.src+(prev.t1-prev.t0)*prev.rate,
                                     rate=prev.rate, cx=prev.cx, grade=prev.grade)
            overlays.append(Overlay(t, t+EFFECT_SECONDS.get(v.effect, .32), v.effect if v.effect in ('cutin', 'glowpop', 'fade', 'iris') else 'accent', data))
            events.append((t, 'broll', 'water' if v.effect == 'ripple' else 'calm'))
        if v.text.strip() and not v.voice:   # (a talking shot's text is its captions)
            word = v.text.strip().upper()
            if v.text_style == 'slam':
                overlays.append(Overlay(t, min(t+dur, t+.95), 'slam', {'text': word, 'tone': tone}))
                events.append((t, 'slam', tone))
            else:
                overlays.append(Overlay(t, min(t+dur, t+1.6), 'perspective', {'text': word, 'tone': tone}))
                events.append((t, 'moment', tone))
        t += dur
    if plan.paper_until:   # the inspo's paper layout, then the paper tearing open into the next shot
        data = {'top': plan.paper_top, 'bottom': plan.paper_bottom, 'top_at': 0., 'bottom_at': plan.paper_word_at,
                'flash_at': plan.paper_word_at if plan.paper_bottom else -1}
        overlays.append(Overlay(0, plan.paper_until, 'paper', data))
        if plan.tear: overlays.append(Overlay(plan.paper_until, plan.paper_until+plan.tear, 'tear'))
    if plan.paper_end:   # the ending wraps back onto the paper, its words returning
        overlays.append(Overlay(max(0., t-plan.paper_end), t+.01, 'paperout',
                                {'top': plan.paper_top, 'bottom': plan.paper_bottom, 'top_at': 0., 'bottom_at': 0., 'boil': True}))
    if plan.line.strip() and plan.line_until > plan.line_from:   # the reference's line, word by word
        parts = plan.line.split()
        step = (plan.line_to-plan.line_from)/max(1, len(parts)-1)
        overlays.append(Overlay(plan.line_from, plan.line_until, 'whisper', {'words': [(w, plan.line_from+k*step) for k, w in enumerate(parts)]}))
    if plan.title and plan.title_style == 'typed':   # the place name, typed out over the opening shot
        opening = shots[1 if lead else 0]
        overlays.append(Overlay(opening.t0, max(opening.t1, opening.t0+1.2), 'typed',
                                {'text': plan.title.upper(), 'from': opening.t0+.05, 'to': opening.t0+.05+TYPE_SECONDS}))
    if plan.title and plan.title_style == 'corners':   # white words in the corners, then the last word huge and red behind us
        opening = shots[1 if lead else 0]
        title_words = plan.title.upper().split()   # (not `words`: that is the clip's transcript, used for captions)
        step = .45
        title_end = min(opening.t1, opening.t0+TITLE_SECONDS)   # up for about 3.5 s, like the reference's lyric title
        for k, w in enumerate(title_words[:-1]):
            overlays.append(Overlay(opening.t0+k*step, title_end, 'corner', {'text': w, 'side': 'left' if k % 2 == 0 else 'right', 'row': k//2}))
        at = opening.t0+max(0, len(title_words)-1)*step
        tone = TITLE_TONES[plan.title_color]
        overlays.append(Overlay(at, max(title_end, at+1.4), 'behind', {'text': title_words[-1], 'tone': tone, 'y': look.H*.42,
                                                                       **TITLE_PAINT.get(plan.title_color, {})}))
        events.append((at, 'moment', tone))
    if plan.loop and plan.shots:   # back to the opening shot (and the start of the title) so the reel loops
        first = plan.shots[0]
        shots.append(Shot(t, t+LOOP, 'aroll', str(source), first.start, cx=shots[1 if lead else 0].cx,
                          zoom0=ZOOMS[first.zoom][0], zoom1=ZOOMS[first.zoom][0]+.01, grade=plan.grade))
        if plan.title and plan.title_style == 'typed':
            word = plan.title.upper()
            overlays.append(Overlay(t, t+LOOP, 'typed', {'text': word, 'from': t, 'to': t+TYPE_SECONDS*len(word), 'fixed': min(2, len(word))}))
        t += LOOP
    # the word lands as it is said only when the edit ends on that talking moment
    carried = []   # (edit from, edit to, source second): the previous moment's sound heard on over a later picture
    for k in range(1, len(shots)):
        if getattr(shots[k], 'carry', False):
            prev = shots[k-1]
            shots[k].audio_src = prev.src+(prev.t1-prev.t0)*prev.rate
            shots[k].audio_until = getattr(shots[k], 'audio_until', None)
            carried.append((shots[k].t0, shots[k].t1, shots[k].audio_src))
    spoken = outro_word_time(plan, words, voiced) if voiced and voiced[-1][1] >= t-.05 else None
    if plan.outro.strip() and shots and spoken is not None:   # the ending word lands as it is said, over the moment itself
        shots = [s for s in shots if s.t0 < spoken-.05]
        last = shots[-1]
        last.t1 = spoken+OUTRO
        paint = TITLE_PAINT.get(plan.title_color, {})
        overlays.append(Overlay(spoken, spoken+OUTRO, 'outro', {'text': plan.outro.strip().upper(), 'texture': paint.get('texture'),
                                                                'fill': paint.get('fill') or look.TONES[TITLE_TONES[plan.title_color]]}))
        overlays = [o for o in overlays if o.t0 < spoken or o.kind == 'outro']
        events.append((spoken+.02, 'bing', 'calm'))
        t = spoken+OUTRO
    elif plan.outro.strip() and shots:   # the ending word over the last moment, slowing to a near-hold
        last = shots[-1]
        shots.append(Shot(t, t+OUTRO, 'aroll', last.path, last.src+(last.t1-last.t0)*last.rate, rate=.3, cx=last.cx,
                          zoom0=last.zoom1, zoom1=last.zoom1+.04, grade=last.grade, face=last.face))
        paint = TITLE_PAINT.get(plan.title_color, {})
        overlays.append(Overlay(t, t+OUTRO, 'outro', {'text': plan.outro.strip().upper(), 'texture': paint.get('texture'),
                                                      'fill': paint.get('fill') or look.TONES[TITLE_TONES[plan.title_color]]}))
        events.append((t+.04, 'bing', 'calm'))
        t += OUTRO
    main_end = t
    if plan.shots and (plan.shots[-1].zoom == 'dive' or plan.fade_out) and not plan.outro.strip():   # it ends in black
        overlays.append(Overlay(max(0., t-.4), t+1, 'fadeout'))
    if plan.end_line:   # the closing message over a held, softened last moment
        last = shots[-1]
        shots.append(Shot(t, t+MESSAGE, 'aroll', str(source), last.src+(last.t1-last.t0)*last.rate, rate=min(1., last.rate), cx=last.cx,
                          zoom0=1.08, zoom1=1.14, grade='mono', look='mono'))
        parts = plan.end_line.split()
        step = min(.32, 1.6/max(1, len(parts)))
        overlays.append(Overlay(t+.15, t+MESSAGE, 'message', {'words': [(w, t+.35+k*step, None) for k, w in enumerate(parts)]}))
        events.append((t+.3, 'boom', 'calm'))
        main_end = t+MESSAGE
    if plan.title and plan.title_style == 'small':   # (typed and corners titles draw themselves)
        overlays.append(Overlay(.15, min(2.2, main_end), 'title', {'text': plan.title}))
    if timing and plan.lyrics != 'off':   # the song's words, but never over someone talking
        overlays += [o for o in lyric_lines(timing[0], timing[1], main_end, plan.lyrics)
                     if not any(o.t0 < b and a < o.t1 for a, b, *_ in voiced)]
    if voiced:   # what is said in the talking shots, captioned as it is said
        lines = speech_captions(words or [], voiced)
        if spoken is not None:   # the ending word takes over the screen: no caption under it
            lines = [o for o in lines if o.t0 < spoken-.1]
            for o in lines: o.t1 = min(o.t1, spoken)
        overlays += lines
    if plan.bars:   # cinematic letterbox
        overlays.append(Overlay(0, main_end+10, 'bars'))
    lap('shots')

    # --- 2. sound: the score, the clip's own sound, or both
    progress(.15, 'Composing the score…')
    total = main_end+(stamp.DURATION if options.stamp else 0)
    samples = _audio(source, score.SR, ffmpeg) if info.get('has_audio', True) else np.zeros((0, 2), np.float32)
    natural = _natural(samples, score.SR, shots, total, source) if plan.sound != 'score' and len(samples) else np.zeros((int(total*score.SR), 2), np.float32)
    for s in shots:   # a moment whose sound keeps going over the next pictures (the chant in the background)
        extra = getattr(s, 'voice_through', 0)
        if not extra or not len(samples) or plan.sound == 'score': continue
        a, n = int((s.src+(s.t1-s.t0)*s.rate)*score.SR), int(extra*score.SR)
        piece = samples[a:a+n].copy()
        if not len(piece): continue
        piece *= np.linspace(1, 0, len(piece), dtype=np.float32)[:, None]**.5
        i = int(s.t1*score.SR)
        natural[i:i+len(piece)] += piece[:max(0, len(natural)-i)]
        voiced.append((s.t1, s.t1+extra, 0.))
    if timing:   # the song's chosen section, with a short fade in and a longer fade out
        from . import music as library
        music = library.samples(timing[0]['file'], score.SR, timing[1], main_end+.1)
        want = int((main_end+.1)*score.SR)
        if 0 < len(music) < want:   # a short song loops to cover the edit
            whole = library.samples(timing[0]['file'], score.SR, 0.)
            music = np.concatenate([music]+[whole]*(1+(want-len(music))//max(1, len(whole))))[:want]
        if plan.music_from:   # a spoken opening first; the song comes in after it
            pad = int(plan.music_from*score.SR)
            music = np.concatenate([np.zeros((pad, 2), np.float32), music])[:want]
        n = len(music)
        if n:
            music[:int(.08*score.SR)] *= np.linspace(0, 1, min(n, int(.08*score.SR)), dtype=np.float32)[:, None]
            tail = min(n, int(.9*score.SR)); music[n-tail:] *= np.linspace(1, 0, tail, dtype=np.float32)[:, None]
        events = [e for e in events if e[1] in ('broll', 'bing', 'flash')]   # a real song needs only the whooshes, bings and splashes
    else:
        music = score.compose(main_end, {'silence': None, 'end': main_end, 'hook_end': min(3., main_end)}, plan.mood)
    if plan.sound == 'original' or not options.music: music = music*0
    if not plan.transition_sounds: events = [e for e in events if e[1] == 'bing']   # no whooshes or hits
    fx = score.sound_design(total, events)
    wav = out.with_suffix('.mix.wav')
    under = (10. if timing else 2.)+options.music_db if plan.sound == 'both' else settings.get('mix.music_under_voice_db', -17.)+options.music_db
    voice = natural
    if (voiced or carried) and plan.sound != 'score' and len(samples):
        # talking shots lead; the song dips under them (score.mix ducks music wherever the voice track speaks) and
        # comes back up between them; the rest of the clip's own sound stays as a quiet bed inside the music
        voice, bed = _split(natural, voiced+[(a, b, c) for a, b, c in carried], score.SR)
        n = min(len(music), len(bed))
        if n and bed[:n].any():
            music = music.copy()
            music[:n] += bed[:n]*.35*float(np.sqrt((music[:n]**2).mean())/(np.sqrt((bed[:n]**2).mean())+1e-9))
        under = settings.get('mix.montage_music_under_voice_db', -9.)+options.music_db
    lufs, peak = score.mix(voice, music, fx, 0, wav, ffmpeg, music_under=under,
                           stamp=score.stamp_audio(stamp.DURATION) if options.stamp else None, stamp_at=main_end)
    lap('sound')

    # --- 3. picture
    progress(.25, 'Composing the picture…')
    matter = None
    if any(o.kind in ('behind', 'silhouette', 'cutin', 'glowpop') for o in overlays) or any(getattr(s, 'backdrop', None) for s in shots):   # the big word sits behind the people; silhouettes
        try:
            from .matte import Matter
            matter = Matter()
        except Exception:
            LOG.warning('person cut-outs unavailable; the big word goes in front', exc_info=True)
            for o in overlays:
                if o.kind == 'behind': o.kind = 'soft'
    composer = render.Composer(shots, overlays, None, main_end, matter, ffmpeg, lambda a, s: progress(.25+.7*a, s))
    def all_frames():
        yield from composer.frames()
        last = composer.last if composer.last is not None else np.zeros((H, W, 3), np.uint8)
        if options.stamp: yield from stamp.frames(last)
    try:
        render.encode(all_frames(), wav, out, ffmpeg)
    finally:
        for clip in made: clip.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)
    lap('picture')
    progress(1, 'Done')
    timeline = {
        'size': [W, H], 'fps': look.FPS, 'ends': round(total, 3),
        'shots': [{'from': round(s.t0, 3), 'to': round(s.t1, 3), 'kind': s.kind, 'file': Path(s.path).name, 'source_from': round(s.src, 3),
                   'speed': s.rate, 'look': s.look} for s in shots],
        'overlays': [{'from': round(o.t0, 3), 'to': round(o.t1, 3), 'kind': o.kind, **({'text': o.data['text']} if 'text' in o.data else {})} for o in overlays],
    }
    return {'visual': True, 'song': timing[0]['credit'] if timing else None, 'seconds': round(total, 1), 'spoken_seconds': 0, 'pieces': len(plan.shots), 'removed_fillers': 0, 'removed_interjections': 0,
            'broll': 0, 'broll_share': 0, 'moments': sum(1 for s in plan.shots if s.text.strip()), 'accents': sum(1 for s in plan.shots if s.effect),
            'visual_family': 'visual', 'lufs': lufs, 'peak': peak, 'cut_out': False, 'size': f'{W}x{H}', 'timings': timings, 'timeline': timeline}


def swap_clips(plan, old_parts, new_parts, replaced=()):
    """A follow-up that only replaces some clips ("change the bench part to 5:17.70"): every shot and collage strip keeps
    its place in the edit and moves onto the same clip in the new joined timeline. A replaced clip (1-based numbers in
    `replaced`) plays from its new start; the others keep their offset inside their clip. Nothing else changes."""
    def where(x):
        return next((k for k, p in enumerate(old_parts) if p['from']-.05 <= x < p['to']), None)
    def move(x, k, offset=None):
        new = new_parts[k]
        at = new['from']+.02 if k+1 in replaced else new['from']+(x-old_parts[k]['from'])
        return round(min(max(new['from'], at), new['to']-.1), 3)
    for s in plan.shots:
        k = where(s.start)
        if k is None or k >= len(new_parts): continue
        length = s.end-s.start
        s.start = move(s.start, k)
        s.end = round(min(new_parts[k]['to']-.02, s.start+length), 3)
        if s.said_from or s.said_to:
            s.said_from, s.said_to = (round(new_parts[k]['from']+(v-old_parts[k]['from']), 3) if v else v for v in (s.said_from, s.said_to))
        if s.said_until: s.said_until = round(new_parts[k]['from']+(s.said_until-old_parts[k]['from']), 3)
        s.panels = [move(x, j) if j is not None and j < len(new_parts) else x for x, j in ((x, where(x)) for x in s.panels)]
        if s.panels:   # each strip stops where its own clip ends
            ends = [next((p['to'] for p in new_parts if p['from']-.05 <= x < p['to']), None) for x in [s.start]+list(s.panels)]
            s.panel_ends = ends if None not in ends else []
        if s.carry_until:
            j = where(s.carry_until-.01)
            if j is not None: s.carry_until = round(new_parts[j]['to']-.03, 3)
    return plan


ORDINALS = {'first': 1, '1st': 1, 'second': 2, '2nd': 2, 'third': 3, '3rd': 3, 'fourth': 4, '4th': 4, 'fifth': 5, '5th': 5, 'sixth': 6, '6th': 6}


def strip_subjects(plan, request):
    """ "the 3rd vertical box ... focus on the girl with the red coat": who each collage strip frames (left to right)."""
    collage = next((s for s in plan.shots if s.panels), None)
    if not collage or not request: return plan
    n = len(collage.panels)+1
    who = (list(collage.panel_who)+['']*n)[:n]
    pattern = (r'\b(' + '|'.join(ORDINALS) + r')\s+(?:vertical\s+)?(?:box|bit|strip|panel|slot)\b(.{0,160}?)'
               r'\bfocus(?:es|ed|ing)?\s+on\s+(?:the\s+|a\s+)?(.+?)(?=\s+only\b|\s+in\s+which\b|\s+and\s+then\b|\s+who\b|[.,;!]|\.\.\.|$)')
    for m in re.finditer(pattern, request, re.I):
        k = ORDINALS[m.group(1).lower()]-1
        if k < n and not re.search(r'\b(' + '|'.join(ORDINALS) + r')\s+(?:vertical\s+)?(?:box|bit|strip|panel|slot)\b', m.group(2), re.I):
            who[k] = re.sub(r'\s+', ' ', m.group(3)).strip().lower().replace('/', ' or ')
    if any(who): collage.panel_who = who
    return plan


THEME_TRANSITIONS = ('leak', 'window', 'cutin')   # fresh transitions (a warm light leak first: hikes, nostalgia), in order of preference, for a shot that gives its own away


def transition_requests(plan, request):
    """ "do the vertical transition before the vertical clips (when the bench scene ends), and a different transition
    for the bench to start": the slices move onto the collage, and the shot they leave gets a transition the edit has
    not used yet."""
    if not request or not re.search(r'\b(vertical|slices?|strips?|split)\s+transi?tion', request, re.I): return plan
    if not re.search(r'before\s+(?:all\s+)?(?:the\s+)?(?:vertical|collage|split)|(?:goes|go|leads?|into)\s+(?:in)?(?:to\s+)?the\s+(?:vertical|collage)'
                     r'|when\s+the\s+[\w ]{1,20}?\s+(?:scene|clip|part|shot)\s+ends', request, re.I): return plan
    k = next((i for i, s in enumerate(plan.shots) if s.panels), None)
    if not k: return plan
    before = plan.shots[k-1]
    plan.shots[k].effect = 'slices'
    if before.effect == 'slices' or re.search(r'differ\w*\s+transi?tion|another\s+transi?tion|new\s+transi?tion', request, re.I):
        used = {s.effect for s in plan.shots}
        before.effect = next((e for e in THEME_TRANSITIONS if e not in used), 'cutin')
    return plan
