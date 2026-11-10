"""Clean dialogue: the cut every other layer is built on.

Fixes what made earlier AI edits feel cheap:
- words were cut at the transcript's own word times, which often end before the voice does,
  so endings and soft first consonants were clipped. Every boundary here is moved to where the
  voice's own energy actually starts and stops, with a little breathing room either side;
- pauses were kept whole and then grown to land on a beat. Here every pause is squeezed to a
  natural breath and nothing waits for the music;
- ums, ahs, stutters and the other person's "yeah"/"mhm" stayed in. They are taken out here
  (see `fillers` and speakers.py), and every join gets a short equal-power crossfade so nothing clicks.
"""
import re
from dataclasses import dataclass, field

import numpy as np

FILLER_WORDS = {'um', 'umm', 'uh', 'uhh', 'uhm', 'erm', 'er', 'ah', 'ahh', 'hmm', 'hm', 'mm', 'mhm', 'mmm', 'eh', 'uh-huh'}
MAX_PAUSE = .24       # a pause longer than this inside a kept line is squeezed
BREATH = .07          # what is left either side of a squeezed pause
PART_BREATH = .06     # extra room between two parts of the story
LEAD_IN = .09         # room kept before the first sound of a word
TAIL = .20            # how far an ending may run past the transcript's end time
FADE = .012           # crossfade at every join


def plain(word):
    return re.sub(r"[^a-z0-9'’-]", '', word.lower()).replace('’', "'")


def fillers(words):
    """Word indices that are hesitation, not content: um/uh, stutters, and "you know"/"I mean" asides."""
    out = set()
    for n, word in enumerate(words):
        p = plain(word['w'])
        if p in FILLER_WORDS:
            out.add(n); continue
        nxt = plain(words[n+1]['w']) if n+1 < len(words) else ''
        # a stutter: the same word twice in a row ("this, this", "the the"); keep the second
        if p and p == nxt and p not in ('very', 'really', 'so', 'no', 'bye', 'ha') and words[n+1]['s']-word['e'] < .6:
            out.add(n); continue
        # "you know," and "I mean," set off by commas are asides
        if p == 'you' and nxt == 'know' and (words[n+1]['w'].endswith(',') or (n and words[n-1]['w'].endswith(','))):
            out.update((n, n+1)); continue
        if p == 'i' and nxt == 'mean' and words[n+1]['w'].endswith(','):
            out.update((n, n+1)); continue
    return out


@dataclass
class Piece:
    a: float        # source seconds
    b: float
    out: float      # where it starts in the edit
    words: list     # word indices it carries
    part: int       # which kept range (story part) it belongs to

    @property
    def length(self):
        return self.b-self.a


@dataclass
class Edit:
    pieces: list
    total: float
    word_out: dict = field(default_factory=dict)   # word index -> (start, end) in the edit
    order: list = field(default_factory=list)       # kept word indices in play order

    def to_out(self, src):
        """Edit time of a source second (None when that moment was cut)."""
        for p in self.pieces:
            if p.a-.001 <= src <= p.b+.001: return p.out+src-p.a
        return None


def _floor(db):
    return float(np.percentile(db, 8)) if len(db) else -60.


def _start(word, previous_end, db, threshold, fps=100):
    """Move a start back to where the sound begins, never into the previous word."""
    t = word['s']
    limit = max(previous_end+.015, t-.16, 0)
    i = int(t*fps)
    while i > 0 and (i-1)/fps > limit and db[min(i-1, len(db)-1)] > threshold: i -= 1
    return max(limit, min(t, i/fps)-LEAD_IN*.6)


def _end(word, next_start, db, threshold, fps=100):
    """Move an end on to where the sound stops (soft endings, trailing consonants), never into the next word."""
    t = word['e']
    limit = min(next_start-.015, t+TAIL)
    i = int(t*fps)
    while i < len(db)-1 and (i+1)/fps < limit and db[i+1] > threshold: i += 1
    return min(limit, max(t, i/fps)+.05)


def cut(words, ranges, drop, db, fps=100, duration=None):
    """The clean dialogue edit. `ranges` are (from_word, to_word) in play order; `drop` word indices to leave out."""
    threshold = _floor(db)+10
    drop = set(drop)
    pieces, cursor, order = [], 0., []
    for part, (first, last) in enumerate(ranges):
        kept = [i for i in range(first, last+1) if i not in drop and 0 <= i < len(words)]
        if not kept: continue
        if pieces: cursor += PART_BREATH
        runs, run = [], [kept[0]]
        for i in kept[1:]:
            gap = words[i]['s']-words[run[-1]]['e']
            if i == run[-1]+1 and gap <= MAX_PAUSE: run.append(i)
            else: runs.append(run); run = [i]
        runs.append(run)
        for run in runs:
            first_w, last_w = words[run[0]], words[run[-1]]
            prev_end = words[run[0]-1]['e'] if run[0] > 0 else -1.
            next_start = words[run[-1]+1]['s'] if run[-1]+1 < len(words) else (duration or last_w['e']+1)
            a = _start(first_w, prev_end, db, threshold, fps)
            b = _end(last_w, next_start, db, threshold, fps)
            if b-a < .08: continue
            pieces.append(Piece(round(a, 3), round(b, 3), round(cursor, 3), run, part))
            cursor += b-a-FADE
            order += run
    edit = Edit(pieces, round(cursor+FADE, 3), order=order)
    for p in pieces:
        for i in p.words:
            w = words[i]
            edit.word_out[i] = (round(p.out+max(0, w['s']-p.a), 3), round(p.out+min(p.b, w['e'])-p.a, 3))
    return edit


def render_voice(samples, sr, edit):
    """The dialogue for the edit, joined with short equal-power crossfades. `samples` is (n, channels) float."""
    n = int(edit.total*sr)+sr
    out = np.zeros((n, samples.shape[1]), np.float32)
    f = max(1, int(FADE*sr))
    up = np.sin(np.linspace(0, np.pi/2, f))[:, None]
    down = np.cos(np.linspace(0, np.pi/2, f))[:, None]
    for p in edit.pieces:
        x = samples[int(p.a*sr):int(p.b*sr)].copy()
        if len(x) < 2*f: continue
        x[:f] *= up; x[-f:] *= down
        i = int(p.out*sr)
        m = min(len(x), n-i)
        out[i:i+m] += x[:m]
    return out[:int(edit.total*sr)]


def energy(samples, sr, fps=100):
    """dB envelope of a mono or stereo signal, `fps` values per second."""
    mono = samples.mean(1) if samples.ndim == 2 else samples
    hop = int(sr/fps)
    win = hop*2
    power = np.convolve(mono**2, np.ones(win)/win, 'same')[::hop]
    return 10*np.log10(power+1e-10)
