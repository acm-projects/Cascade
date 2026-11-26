"""Visual edits: Cinema music edits. For clips where nobody speaks (sport, travel, b-roll, pets, music-only footage),
and for montages that mix music with a few talking moments (a group of friends on a trip): a shot marked "voice"
plays at normal speed with its own sound up front, the song dips under it and its words appear as captions.

The planner watches the contact sheets and the per-second motion and returns a VisualPlan: which moments of
the source to play, in what order, at what speed, with which zooms, effects and words. Everything is
addressed by source second, not by transcript word. Rendering reuses the Cinema picture and sound code
(render.py, score.py) and, like the rest of the engine, calls no AI model."""
import logging
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
ZOOMS = {'none': (1., 1.03), 'push': (1., 1.12), 'punch': (1.14, 1.17), 'pull': (1.14, 1.), 'close': (1.85, 1.95)}
SHORTEST = .5   # seconds on screen
QUICKEST = .6   # a quick music shot is not shortened below this to make an edit fit
LOOP = .75      # the closing return to the opening shot, for a seamless loop
TYPE_SECONDS = .9   # how long the typed title takes to spell out
TITLE_SECONDS = 3.6   # how long a "corners" title stays up
EFFECT_SECONDS = {'shake': .45, 'slices': .5, 'window': .6}   # transitions longer than the default 0.32 s
TITLE_TONES = {'red': 'danger', 'blue': 'water', 'dark blue': 'water', 'yellow': 'money', 'green': 'life', 'white': 'calm'}
TITLE_PAINT = {'blue': {'fill': (38, 98, 214)}, 'dark blue': {'fill': (30, 78, 178), 'edge': (6, 20, 66)}}   # colours that are not one of the tones


class VisualShot(BaseModel):
    model_config = ConfigDict(extra='ignore')
    start: float = Field(ge=0)                     # source seconds
    end: float = Field(gt=0)
    speed: float = Field(default=1., ge=.25, le=2.)   # .5 = half-speed slow motion, 2 = double speed
    zoom: Literal['none', 'push', 'punch', 'pull', 'close'] = 'none'   # 'close': a strong close-up on people filmed from far away
    focus_x: float = Field(default=.5, ge=0, le=1)   # where the subject is, left (0) to right (1), for vertical crops
    focus_y: float = Field(default=.45, ge=0, le=1)  # where the subject is, top (0) to bottom (1), for a 'close' zoom
    effect: Literal['whip', 'rgb', 'ink', 'ripple', 'flash', 'invert', 'glitch', 'leak', 'zoom', 'shake', 'slices', 'window'] | None = None   # a transition as this shot lands
    text: str = Field(default='', max_length=16)       # one big word over the start of this shot
    text_style: Literal['slam', 'perspective'] = 'perspective'
    tone: Tone | None = None
    voice: bool = False   # a talking moment: its own sound up front, the music dipped under it, its words captioned
    flash: bool = False   # a 0.1-0.3 s glimpse in a burst of very fast cuts (not snapped to the beat)
    mono: bool = False    # this shot in high-contrast black and white (one standout moment)
    big_captions: bool = False   # a talking shot's words big, bold and centred (a chant, a punchline)


class VisualPlan(BaseModel):
    model_config = ConfigDict(extra='ignore')
    kind: Literal['visual'] = 'visual'
    reply: str = Field(default='', max_length=1500)
    title: str = Field(default='', max_length=60)
    # 'typed': a big place name typed out letter by letter over the opening shot; 'corners': the title's words pop in
    # white in the top corners one after another and its last word lands huge and red behind the people (a lyric-video opener)
    title_style: Literal['small', 'typed', 'corners'] = 'small'
    # the big word of a "corners" title; 'dark blue': a deep blue word with a thick, darker navy outline
    title_color: Literal['red', 'blue', 'dark blue', 'yellow', 'green', 'white'] = 'red'
    shots: list[VisualShot] = Field(min_length=1, max_length=40)
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
    loop: bool = False      # end on a short return to the opening shot and title, so the reel plays as a seamless loop
    seconds: float = Field(default=0, ge=0, le=60)   # the edit's length when the user asked for one; 0 = the house length

    @model_validator(mode='after')
    def _tidy(self):
        self.end_line = self.end_line.strip().rstrip('.')
        for s in self.shots:
            if s.voice: s.speed = 1.   # speech plays at its own speed
        # captions are drawn for the talking shots only (speech_captions); the dialogue caption track stays off
        self.settings.captions = False
        if any(s.voice for s in self.shots) and self.sound == 'score': self.sound = 'both'
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
        if s.end > duration+.05: raise ValueError(f'shots[{k}]: ends at {s.end:.1f} s but the clip is {duration:.1f} s long')
        if s.end-s.start < (.08 if s.flash else .3):
            raise ValueError(f'shots[{k}]: needs end at least {.08 if s.flash else .3} s after start')
        if windows and not any(s.start >= a-.05 and s.end <= b+.05 for a, b in windows):
            raise ValueError(f'shots[{k}]: {s.start:.1f}-{s.end:.1f} s is outside the usable ranges {windows}')
    for s in plan.shots: s.end = min(s.end, duration)
    if parts and plan.clip_order:
        n = len(parts)
        if any(not 1 <= c <= n for c in plan.clip_order): raise ValueError(f'clip_order: use clip numbers 1-{n}')
        which = lambda s: next((k+1 for k, p in enumerate(parts) if p['from']-.05 <= s.start < p['to']), 0)
        played = []
        for k, s in enumerate(plan.shots):
            c = which(s)
            if c and s.end > parts[c-1]['to']+.1:
                raise ValueError(f"shots[{k}]: runs from clip {c} into the next clip; end it by {parts[c-1]['to']:.1f} s")
            if c and not s.flash and (not played or played[-1] != c): played.append(c)
        want = list(dict.fromkeys(plan.clip_order))
        missing = [c for c in want if c not in played]
        if missing:
            raise ValueError(f"clip_order {want}: clip(s) {missing} ({'; '.join(parts[c-1]['title'] for c in missing)}) are not "
                             f"played; your shots play clips {played}. Give each one at least one shot, shortening others to fit.")
        order = [c for c in played if c in want]
        if [c for c in dict.fromkeys(order)] != want:
            raise ValueError(f'clip_order {want}: your shots play the clips in the order {played}; put the shots in clip_order.')


def story_edges(plan, words, parts=None, most=4.):
    """A montage opens and ends on people: the first and last shots are talking shots when they are mostly speech
    (an intro, a chant), and with a requested clip order the ending plays to the end of its clip (its payoff),
    at most `most` s longer."""
    shots = [s for s in plan.shots if not s.flash]
    if not shots: return plan
    for s in {id(x): x for x in (shots[0], shots[-1])}.values():
        spoken = sum(max(0., min(w['e'], s.end)-max(w['s'], s.start)) for w in words or [])
        if spoken >= .5*(s.end-s.start): s.voice, s.speed = True, 1.
    if parts and plan.clip_order:
        last = shots[-1]
        clip = next((p for p in parts if p['from']-.05 <= last.start < p['to']), None)
        if clip and 0 < clip['to']-last.end <= most: last.end = clip['to']-.05
    return plan


def stop_at(plan, words, request):
    """Where the request says talking stops: "stop the intro at presentation prep" ends the talking shot that says
    those words right after them; "end right after the one two three" ends the edit's last talking shot right after
    those words (with a beat more, so the moment lands: hands going up)."""
    import re
    if not words: return plan
    said = [re.sub(r"[^a-z0-9']", '', w['w'].lower()) for w in words]
    ending = r"(?=\s*(?:[,.;]|\band\b|\bthen\b|\bwhen\b|\bwith\b|$))"
    rules = [(r"\bstop(?:s|ping)?\b[^.;]*?\b(?:at|after)\s+(?:the\s+)?[\"'“]?([a-z0-9' ]{3,60}?)[\"'”]?"+ending, .2, False),
             (r"\bend(?:s|ing)?\s+(?:it\s+)?(?:right\s+|just\s+)?after\s+(?:the\s+|we\s+say\s+|they\s+say\s+)?[\"'“]?([a-z0-9' ]{3,60}?)[\"'”]?"+ending, .9, True)]
    for pattern, tail, last in rules:
        m = re.search(pattern, request or '', re.I)
        if not m: continue
        target = re.findall(r"[a-z0-9']+", m.group(1).lower())
        talking = [s for s in plan.shots if s.voice]
        for s in (talking[-1:] if last else talking):
            for i in range(len(words)-len(target)+1):
                if said[i:i+len(target)] == target and s.start-.05 <= words[i]['s'] < s.end+3:
                    s.end = min(s.end, words[i+len(target)-1]['e']+tail) if not last else words[i+len(target)-1]['e']+tail
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


def length(plan):
    return sum((s.end-s.start)/s.speed for s in plan.shots)


def fit(plan, seconds, beat=None, grid=None, lead=0.):
    """Make the edit play in at most `seconds` (a black intro of `lead` seconds included): later shots go, the last
    one is trimmed. Every cut lands on `grid` (edit times, e.g. a song's beats and half-beats) or on the half-beat
    grid of `beat`."""
    budget = seconds-lead-(LOOP if plan.loop else 0)
    for s in plan.shots:   # a burst glimpse lasts 0.1-0.3 s whatever was planned
        if s.flash: s.end = s.start+min(.3, max(.1, s.end-s.start))*s.speed
    # too long: music shots from the middle go first (latest first); talking shots, the opening and the ending stay
    on = lambda x: (x.end-x.start)/x.speed
    over = sum(map(on, plan.shots))-budget
    middle = [k for k, x in enumerate(plan.shots) if 0 < k < len(plan.shots)-1 and not x.voice and not x.flash]
    room = sum(max(0., on(plan.shots[k])-QUICKEST) for k in middle)
    if over > 0 and room > 0:   # first shorten every quick shot in proportion (down to QUICKEST)
        share = min(1., over/room)
        for k in middle:
            x = plan.shots[k]
            cut = max(0., on(x)-QUICKEST)*share
            plan.shots[k] = x.model_copy(update={'end': x.end-cut*x.speed})
    while sum(map(on, plan.shots)) > budget+1e-6:
        middle = [k for k, x in enumerate(plan.shots) if 0 < k < len(plan.shots)-1 and not x.voice]
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
            later = [g for g in options if g >= target-.04] if s.voice else []
            end = min(later) if later else min(options, key=lambda g: abs(g-target))
            snapped.append(s.model_copy(update={'end': s.start+(end-t)*s.speed})); t = end
        shots = _on_the_beat(snapped, points, lead, hold_first=plan.title_style in ('typed', 'corners')) if snapped else shots
    plan.shots = shots
    return length(plan)+lead


LONGEST = 1.8   # seconds a music edit holds one shot before cutting again on the beat


def _on_the_beat(shots, points, lead, hold_first=False):
    """Long holds become jump cuts on the beat: the same moment carries on, the framing punches in and out,
    so the picture moves with the music (effects and words stay on the first piece)."""
    out, t = [], lead
    for n, s in enumerate(shots):
        end = t+(s.end-s.start)/s.speed
        if end-t <= LONGEST+.05 or (n == 0 and hold_first):   # a typed title holds its opening shot
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


def _natural(samples, sr, shots, total):
    """The clip's own sound under each shot (muted under slow or fast motion), with short fades so cuts do not click."""
    out = np.zeros((int(total*sr), 2), np.float32)
    fade = int(.012*sr)
    for s in shots:
        if s.kind != 'aroll' or abs(s.rate-1) > .01: continue
        a, n = int(s.src*sr), int((s.t1-s.t0)*sr)
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
    timed = []
    for a, b, src, *flags in voiced:
        big = bool(flags and flags[0])
        for w in words:
            if src-.02 <= w['s'] and w['e'] <= src+(b-a)+.08:
                timed.append((w['w'].strip(), a+w['s']-src, a+min(w['e'], src+(b-a))-src, big))
    lines, run = [], []
    for item in sorted(timed, key=lambda x: x[1]):
        if run and (item[1]-run[-1][2] > .45 or len(run) >= (2 if item[3] else most) or item[3] != run[-1][3]
                    or run[-1][0].endswith(('.', ',', '?', '!'))):
            lines.append(run); run = []
        run.append(item)
    if run: lines.append(run)
    out = []
    for n, line in enumerate(lines):
        t0 = line[0][1]-.05
        t1 = min(line[-1][2]+.35, (lines[n+1][0][1]-.06) if n+1 < len(lines) else line[-1][2]+.35)
        if t1-t0 > .15:
            out.append(Overlay(t0, t1, 'lyric', {'style': 'bold' if line[0][3] else 'caption',
                                                 'words': [(w.strip(',.'), at) for w, at, *_ in line]}))
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
        shots.append(Shot(t, t+dur, 'aroll', str(source), v.start, rate=v.speed, cx=cx, zoom0=z0, zoom1=z1,
                          grade='bwhot' if v.mono else plan.grade,
                          # a close-up zooms in on the people where they are in the frame
                          face=(v.focus_x*W, v.focus_y*H) if v.zoom == 'close' else None))
        if v.voice: voiced.append((t, t+dur, v.start, v.big_captions))
        tone = v.tone or look.tone_of(v.text, None) or 'calm'
        if v.effect and n:
            overlays.append(Overlay(t, t+EFFECT_SECONDS.get(v.effect, .32), 'accent', {'kind': v.effect}))
            events.append((t, 'broll', 'water' if v.effect == 'ripple' else 'calm'))
        if v.text.strip():
            word = v.text.strip().upper()
            if v.text_style == 'slam':
                overlays.append(Overlay(t, min(t+dur, t+.95), 'slam', {'text': word, 'tone': tone}))
                events.append((t, 'slam', tone))
            else:
                overlays.append(Overlay(t, min(t+dur, t+1.6), 'perspective', {'text': word, 'tone': tone}))
                events.append((t, 'moment', tone))
        t += dur
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
    main_end = t
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
        overlays += speech_captions(words or [], voiced)
    if plan.bars:   # cinematic letterbox
        overlays.append(Overlay(0, main_end+10, 'bars'))
    lap('shots')

    # --- 2. sound: the score, the clip's own sound, or both
    progress(.15, 'Composing the score…')
    total = main_end+(stamp.DURATION if options.stamp else 0)
    samples = _audio(source, score.SR, ffmpeg) if info.get('has_audio', True) else np.zeros((0, 2), np.float32)
    natural = _natural(samples, score.SR, shots, total) if plan.sound != 'score' and len(samples) else np.zeros((int(total*score.SR), 2), np.float32)
    if timing:   # the song's chosen section, with a short fade in and a longer fade out
        from . import music as library
        music = library.samples(timing[0]['file'], score.SR, timing[1], main_end+.1)
        want = int((main_end+.1)*score.SR)
        if 0 < len(music) < want:   # a short song loops to cover the edit
            whole = library.samples(timing[0]['file'], score.SR, 0.)
            music = np.concatenate([music]+[whole]*(1+(want-len(music))//max(1, len(whole))))[:want]
        n = len(music)
        if n:
            music[:int(.08*score.SR)] *= np.linspace(0, 1, min(n, int(.08*score.SR)), dtype=np.float32)[:, None]
            tail = min(n, int(.9*score.SR)); music[n-tail:] *= np.linspace(1, 0, tail, dtype=np.float32)[:, None]
        events = [e for e in events if e[1] == 'broll']   # a real song needs only the whooshes, not the score's hits
    else:
        music = score.compose(main_end, {'silence': None, 'end': main_end, 'hook_end': min(3., main_end)}, plan.mood)
    if plan.sound == 'original' or not options.music: music = music*0
    fx = score.sound_design(total, events)
    wav = out.with_suffix('.mix.wav')
    under = (10. if timing else 2.)+options.music_db if plan.sound == 'both' else settings.get('mix.music_under_voice_db', -17.)+options.music_db
    voice = natural
    if voiced and plan.sound != 'score' and len(samples):
        # talking shots lead; the song dips under them (score.mix ducks music wherever the voice track speaks) and
        # comes back up between them; the rest of the clip's own sound stays as a quiet bed inside the music
        voice, bed = _split(natural, voiced, score.SR)
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
    if any(o.kind == 'behind' for o in overlays):   # the big word sits behind the people
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
    render.encode(all_frames(), wav, out, ffmpeg)
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
