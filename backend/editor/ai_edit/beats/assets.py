"""Stage 5: the real assets a beat plan needs, made before rendering (the renderer only reads them).

    prepare(plan, work, store=None, folders=()) -> {beat id: {"broll": [...], "cutout": {...}}}
    mix(plan, source, work) -> wav path: the window's speech with each beat's sound effect under it

Speaker cut-outs: TEXT_BEHIND_SUBJECT and SPEAKER_CUTOUT_ICONS beats get RGBA PNG frames of the speaker, made with
Cinema's U^2-Net person matte (cinema/matte.py, runs locally) from the render proxy, so they line up with the
footage frame for frame. The mic and its arm in front of the speaker stay in the cut-out on purpose: they are in
front of the giant word too.

B-roll: BROLL_OVERLAY and COLLAGE subjects are searched on Pexels through the project's stock store
(backend/broll.py: results and downloads are cached), ranked by how well each clip's own page description matches
the query (ai_edit/picture.ranked), then the fallback query, then local footage folders. A subject with no clip
gets the renderer's generated background (no placeholder blocks). Every stock clip used is recorded with its URL.

Sound: each beat's `sfx` names a dark sound synthesized here, under a dramatic score (beats/music.py) that ducks
under the voice. No sample packs, nothing to license.
"""
import json
import re
import logging
import math
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

LOG = logging.getLogger(__name__)
CUTOUT_TEMPLATES = ('TEXT_BEHIND_SUBJECT', 'SPEAKER_CUTOUT_ICONS')
BROLL_TEMPLATES = ('BROLL_OVERLAY', 'COLLAGE')
STOCK_BEHIND = ('KINETIC_KEYWORD', 'NUMBER_COUNTER', 'MAP_CALLOUT')   # dark graphic beats that sit over their stock clip
CUTOUT_FPS = 30
TAIL = 14          # the next beat's transition draws this beat for up to 14 more frames
SR = 48000
RUN = dict(capture_output=True, text=True)


def _frames(plan):
    from .render import frames_for
    return {i: (a, b) for i, a, b in frames_for(plan)}


# ---------------------------------------------------------------- speaker cut-outs

def needs_cutout(beat):
    """Text behind the speaker and the icon scene need the speaker cut out; so do dark keyword beats, where the
    speaker stands out of a dimmed shot with a rim glow (the reference's look)."""
    if beat['template'] in CUTOUT_TEMPLATES: return True
    # a dark keyword beat with a b-roll search sits over its stock clip instead, so it needs no cutout
    return beat['template'] == 'KINETIC_KEYWORD' and beat.get('background_mode') == 'dark' and not beat.get('broll_query')


def cutouts(plan, work, progress=None):
    """{beat id: {"dir", "fps", "count", "from"}} for the beats that need the speaker cut out."""
    from ..cinema import matte
    from .render import FPS, total_frames
    report = progress or (lambda amount, stage: None)
    beats = [b for b in plan['beats'] if needs_cutout(b)]
    if not beats: return {}
    if not matte.available():
        LOG.warning('person matte unavailable; cut-out beats fall back to text in front')
        return {}
    work = Path(work); public = work/'public'
    proxy = public/'source.mp4'
    frames = _frames(plan)
    total = total_frames(plan)
    matter = matte.Matter()
    found = {}
    for n, beat in enumerate(beats):
        a, b = frames[beat['id']]
        b = min(total, b+TAIL)
        rel = f"cutouts/b{beat['id']}"
        folder = public/rel
        key = {'proxy': json.loads((public/'source.json').read_text()), 'from': a, 'to': b, 'fps': CUTOUT_FPS, 'version': 3}
        stamp = folder/'key.json'
        if stamp.is_file() and json.loads(stamp.read_text()) == key:
            found[beat['id']] = {'dir': rel, 'fps': CUTOUT_FPS, 'count': len(list(folder.glob('[0-9]*.png'))), 'from': a}
            continue
        report(n/len(beats), f"Cutting out the speaker for beat {beat['id']}…")
        shutil.rmtree(folder, ignore_errors=True); folder.mkdir(parents=True)
        count = _cut(proxy, a/FPS, (b-a)/FPS, folder, matter)
        stamp.write_text(json.dumps(key))
        found[beat['id']] = {'dir': rel, 'fps': CUTOUT_FPS, 'count': count, 'from': a}
    return found


def clean_matte(alpha):
    """Firm, single-person matte: half-transparent ghosts (fast hands, the matte's temporal smoothing) are pushed to
    fully in or out, and blobs not attached to the body (a stray hand fragment) are dropped unless they are large."""
    import cv2
    alpha = np.clip((alpha-.3)/.4, 0, 1)
    solid = (alpha > .5).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(solid, 8)
    if count > 2:
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = np.zeros(count, bool); keep[1:] = areas >= .15*areas.max()
        mask = cv2.dilate(keep[labels].astype(np.uint8), np.ones((9, 9), np.uint8))
        alpha = alpha*mask
    return cv2.GaussianBlur(alpha.astype(np.float32), (0, 0), 1.1)   # soft, not jagged, edges


def _cut(proxy, start, seconds, folder, matter):
    """RGBA PNGs of the speaker from `proxy` between start and start+seconds, CUTOUT_FPS a second."""
    import cv2
    from PIL import Image
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(proxy)], **RUN)
    w, h = (int(x) for x in probe.stdout.strip().split(',')[:2])
    raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{start:.4f}', '-i', str(proxy), '-t', f'{seconds:.4f}',
                          '-vf', f'fps={CUTOUT_FPS}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, timeout=1800, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)
    matter.reset()
    for n, frame in enumerate(frames):
        alpha = clean_matte(matter(frame))
        rgba = np.dstack([frame, (alpha*255).clip(0, 255).astype(np.uint8)])
        Image.fromarray(rgba, 'RGBA').save(folder/f'{n:04d}.png', compress_level=1)
    return len(frames)


# ---------------------------------------------------------------- b-roll

def subjects(beat):
    """The searches for a beat: one per COLLAGE subject (" | "), else the beat's query."""
    query = beat.get('broll_query') or ''
    return [s.strip() for s in query.split('|') if s.strip()] if beat['template'] == 'COLLAGE' else ([query] if query else [])


def plan_subject(plan):
    """The thing the whole edit is about, from its b-roll searches ("jaguar" when most searches name a jaguar), or None."""
    from collections import Counter
    from ..picture import LOOK_WORDS, _stem
    generic = LOOK_WORDS | {'jungle', 'rainforest', 'forest', 'wildlife', 'documentary', 'amazon', 'river', 'tree', 'trees', 'nature',
                            'old', 'young', 'big', 'small', 'camera', 'background', 'scene', 'people', 'man', 'woman', 'person'}
    counts = Counter()
    for beat in plan.get('beats', []):
        words = {_stem(w) for q in (beat.get('broll_query'), beat.get('broll_fallback_query')) if q
                 for w in re.findall(r'[a-z]+', q.lower()) if len(w) > 2 and w not in generic}
        counts.update(words)
    if not counts: return None
    word, n = counts.most_common(1)[0]
    return word if n >= 2 else None


def _shows(asset, subject):
    from ..picture import _stem
    slug = re.sub(r'[^a-z]+', ' ', (asset.get('source_url') or '').lower().rsplit('/video/', 1)[-1])
    return subject in {_stem(w) for w in slug.split()}


def find_broll(query, fallback, store, used, folders=(), subject=None, words=''):
    """(path, record) for the best clip: query, then the fallback, on the stock store; then local folders.
    With a subject (the edit's main thing, e.g. "jaguar") only clips whose page names it are used, and plain
    searches for the subject are tried last, so a jaguar edit never gets a sloth. Local footage (the user's own
    clips, named by what they show) is tried first, matched on the search plus the beat's own `words`."""
    from ..cinema import broll as cinema_broll
    from ..picture import ranked
    for folder in folders:
        path = cinema_broll.from_folder(f'{query or fallback or ""} {words}', folder, used)
        if path: return path, {'query': query, 'source': Path(path).name, 'license': 'local footage'}
    attempts = [query, fallback] + ([f'{subject} close up', subject] if subject else [])
    for attempt in attempts:
        if not attempt or store is None: continue
        try:
            results = [a for a in store.search(attempt, orientation='landscape', hd=True).get('results', []) if a['id'] not in used]
        except Exception as exc:   # no key, no network: say why once in the report, keep going
            LOG.info('stock search failed for %r: %s', attempt, getattr(exc, 'detail', exc))
            return None, {'query': query, 'error': str(getattr(exc, 'detail', exc))[:200]}
        picks = ranked(attempt, results) or []
        if subject: picks = [a for a in (picks or results) if _shows(a, subject)] or [a for a in results if _shows(a, subject)]
        for pick in picks[:3]:
            try:
                path = store.media(pick['id'])
            except Exception:
                continue
            used.add(pick['id'])
            return str(path), {'query': query, 'searched': attempt, 'id': pick['id'], 'source': pick.get('source_url', ''), 'license': 'Pexels License'}
    return None, {'query': query, 'note': 'no clip found; generated background'}


def _clip(path, out, seconds, size):
    """A stock clip trimmed and scaled for the renderer (H.264, 60 fps, cover-cropped to the output size)."""
    if out.is_file(): return out
    w, h = size
    part = out.with_suffix('.part.mp4')
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(path), '-t', f'{seconds:.3f}', '-an',
                    '-vf', f'fps=60,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', str(part)], **RUN, check=True, timeout=900)
    part.replace(out)
    return out


def broll(plan, work, store=None, folders=(), size=(1284, 704)):
    """({beat id: [media]}, credits). Subjects without a clip are left out; the renderer draws their background."""
    from .render import FPS
    public = Path(work)/'public'
    (public/'broll').mkdir(parents=True, exist_ok=True)
    frames = _frames(plan)
    used, media, credits = set(), {}, []
    subject = plan_subject(plan)
    for beat in plan['beats']:
        behind = beat['template'] in STOCK_BEHIND and beat.get('background_mode') != 'light' and beat.get('broll_query')
        if beat['template'] not in BROLL_TEMPLATES and not behind: continue
        a, b = frames[beat['id']]
        seconds = (b-a+TAIL)/FPS+.5
        found = []
        for thing in (subjects(beat) if not behind else [beat['broll_query']]):
            words = f"{beat.get('emphasis_text') or ''} {beat.get('spoken_text') or ''}"
            path, record = find_broll(thing, beat.get('broll_fallback_query'), store, used, folders, subject, words)
            credits.append({'beat': beat['id'], **record})
            if not path: found.append(None); continue
            name = f"broll/{Path(path).stem}-{int(seconds*1000)}.mp4"
            _clip(path, public/name, seconds, size)
            found.append({'src': name, 'kind': 'video'})
        if any(found): media[beat['id']] = [m or {} for m in found]
    return media, credits


def prepare(plan, work, store=None, folders=(), size=(1284, 704), progress=None):
    """All assets for `plan` (the render proxy must already be in work/public). Returns (assets, credits)."""
    assets = {}
    for beat_id, cut in cutouts(plan, work, progress).items():
        assets.setdefault(beat_id, {})['cutout'] = cut
    media, credits = broll(plan, work, store, folders, size)
    for beat_id, items in media.items():
        assets.setdefault(beat_id, {})['broll'] = [m if m else None for m in items]
    return assets, credits


# ---------------------------------------------------------------- sound effects

def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def _scribble(seconds=.55, seed=3):
    from scipy.signal import butter, sosfilt
    n = int(seconds*SR); t = np.arange(n)/SR
    scratch = sosfilt(butter(2, [2200, 7000], 'bandpass', fs=SR, output='sos'), _noise(n, seed))
    strokes = .5+.5*np.sin(2*math.pi*7.5*t+np.sin(2*math.pi*1.3*t))
    return scratch*strokes**3*np.minimum(1, (seconds-t)/.08)


def _glitch(seed=8):
    rng = np.random.default_rng(seed); n = int(.32*SR)
    x = np.zeros(n)
    for _ in range(6):
        a = int(rng.uniform(0, n-2400)); m = int(rng.uniform(600, 2400))
        burst = np.sign(rng.standard_normal(m))*.6 if rng.random() > .5 else np.sin(2*math.pi*rng.uniform(200, 1800)*np.arange(m)/SR)
        x[a:a+m] += burst[:max(0, min(m, n-a))]
    return np.round(x*6)/6   # bit-crushed


def _drone(seconds, f=55.):
    n = int(seconds*SR); t = np.arange(n)/SR
    x = sum(np.sin(2*math.pi*f*k*t+k)*a for k, a in ((1, .6), (2, .25), (3, .1)))
    return x*np.minimum(1, t/.4)*np.minimum(1, (seconds-t)/.3)


def _dark_riser(seconds, seed=1):
    """A serious build: filtered noise opening upward over a growing sub rumble, no musical tone."""
    from scipy.signal import butter, sosfilt
    n = int(seconds*SR); t = np.arange(n)/SR
    x = _noise(n, seed)
    lo = sosfilt(butter(2, [120, 700], 'bandpass', fs=SR, output='sos'), x)
    hi = sosfilt(butter(2, [900, 5000], 'bandpass', fs=SR, output='sos'), x)
    p = t/seconds
    rumble = np.sin(2*math.pi*np.cumsum(38+20*p)/SR)*.8
    env = p**2.4
    return (lo*(1-p)+hi*p*.8+rumble)*env


def _tick(seed=4):
    from ..cinema import score
    return score._thump(140, .18, .3)*.6+_noise(int(.18*SR), seed)*np.exp(-np.arange(int(.18*SR))/(.006*SR))*.25


def sound(name, seconds):
    """(samples, where) for one effect: where is "cut" (centred on the cut), "start", "span" or "end" (lands on the next cut).
    Every sound is dark and serious: air, drums, booms and rumbles, no bright tones. Names the director invents are matched
    by what they contain (\"deep_rumble\" is a rumble, \"low_hit\" is a hit)."""
    from ..cinema import score
    name = (name or '').lower()
    has = lambda *words: any(w in name for w in words)
    if has('outro', 'big', 'boom', 'slam'): return score._boom(46, 2.4 if 'outro' in name else 1.8), 'start'
    if has('riser', 'build', 'swell', 'suck'): return _dark_riser(min(max(.6, seconds), 2.5), 4), 'end'
    if has('rumble', 'drone'): return _drone(seconds, 41.), 'span'
    if has('hit', 'impact', 'thud', 'punch'): return score._thump(55, .9)*1.1, 'start'
    if has('glitch'): return _glitch(), 'start'
    if has('pen', 'scribble', 'marker', 'swipe'): return _scribble(), 'start'
    if has('tick', 'counter', 'clock', 'ping', 'pop', 'sparkle', 'click'): return _tick(), 'start'
    if has('whoosh_soft', 'soft'): return score._air(.55, True, 2)*.5, 'cut'
    if has('wind', 'air'): return score._air(min(max(.5, seconds), 1.5), True, 9)*.6, 'cut'
    return score._air(.55, True, 2), 'cut'


LEVELS = {'start': .34, 'cut': .28, 'end': .26, 'span': .16}   # peak level of each kind, under the voice


def effects_track(plan, seconds_total):
    """The sound effects alone, as a stereo float array at SR."""
    origin = plan['source_window']['start']
    track = np.zeros(int(seconds_total*SR)+SR)
    placed = []
    for beat in plan['beats']:
        if not beat.get('sfx'): continue
        start, length = beat['start']-origin, beat['end']-beat['start']
        x, where = sound(beat['sfx'], length)
        x = x/(np.abs(x).max()+1e-9)*LEVELS[where]
        at = {'start': start, 'cut': start-len(x)/SR*.45, 'end': start+length-len(x)/SR, 'span': start}[where]
        i = int(round(max(0, at)*SR)); x = x[int(round(max(0, -at)*SR)):]
        m = min(len(x), len(track)-i)
        track[i:i+m] += x[:m]
        placed.append({'beat': beat['id'], 'sfx': beat['sfx'], 'at': round(at, 3), 'seconds': round(len(x)/SR, 3)})
    return np.stack([track, track], 1)[:int(seconds_total*SR)], placed


def _read(path):
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32)/32768
        return x.reshape(-1, w.getnchannels())


MUSIC_UNDER_VOICE_DB = -9.    # the score sits this far under the voice while someone speaks (louder between lines);
                              # CASCADE_BEATS_MUSIC_DB overrides it (e.g. -15 for a quieter bed)


def hit_times(plan):
    """Where the score lands a big drum: the beats whose sound is an impact."""
    origin = plan['source_window']['start']
    return [b['start']-origin for b in plan['beats'] if any(w in (b.get('sfx') or '').lower() for w in ('impact', 'boom', 'slam', 'big'))]


def mix(plan, source, work):
    """speech.wav (the window's own sound) + a dramatic score ducked under the voice + effects, at -14 LUFS.
    Returns the wav path (same length as the speech). CASCADE_BEATS_MUSIC=off leaves the score out."""
    import os
    from ..cinema import score
    from . import music
    from .render import speech
    work = Path(work)
    voice = _read(speech(plan, source, work/'speech.wav')).astype(np.float64)
    seconds = len(voice)/SR
    fx, placed = effects_track(plan, seconds)
    on = os.getenv('CASCADE_BEATS_MUSIC', 'on').strip().lower() != 'off'
    own = music.track_file() if on else None
    if own:
        try:
            start = float(os.getenv('CASCADE_BEATS_MUSIC_START', '0') or 0)
        except ValueError:
            start = 0.
        bed = music.from_file(own, seconds, start)
    else:
        bed = music.dramatic(seconds, hit_times(plan)) if on else np.zeros((len(voice), 2))
    final = work/'mix.wav'
    try:
        under = float(os.getenv('CASCADE_BEATS_MUSIC_DB', MUSIC_UNDER_VOICE_DB))
    except ValueError:
        under = MUSIC_UNDER_VOICE_DB
    score.mix(voice, bed, fx*.6, -80., final, music_under=under)
    (work/'effects.json').write_text(json.dumps({'music': (own.name if own else 'dramatic') if on else None, 'effects': placed}, indent=1))
    return final
