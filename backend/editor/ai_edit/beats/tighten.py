"""Take the pauses out of a beat edit before it is rendered.

    keep_ranges(words, start, end) -> [(a, b)]   the parts of the window that are speech (source seconds)
    tighten(plan, ranges) -> plan                 the plan on the tight timeline (window 0..kept seconds)
    tight_source(source, ranges, folder) -> path  the kept parts of the source joined into one file (cached)

A gap between two words longer than MAX_GAP is cut down to a short breath (LEAD before the next word, TAIL after
the last one). Beats keep their words; a beat with no words left (a "pause" beat) is dropped and its neighbour takes
its place. The saved plan is unchanged; only the render uses the tight one. CASCADE_BEATS_TIGHTEN=off keeps pauses.
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

MAX_GAP = .3      # seconds of silence kept between words; longer gaps are cut
LEAD = .09        # kept before a word that follows a cut
TAIL = .14        # kept after a word before a cut
MIN_BEAT = .2     # a beat shorter than this on the tight timeline merges into its neighbour


def enabled():
    return os.getenv('CASCADE_BEATS_TIGHTEN', 'on').strip().lower() != 'off'


def _fps(source):
    run = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=avg_frame_rate',
                          '-of', 'csv=p=0', str(source)], capture_output=True, text=True, timeout=60)
    try:
        a, _, b = run.stdout.strip().strip(',').partition('/')
        rate = float(a)/float(b or 1)
        return rate if 1 < rate < 241 else 30.
    except (ValueError, ZeroDivisionError):
        return 30.


def keep_ranges(words, start, end, fps=None):
    """Speech ranges inside [start, end]. Cut points snap to the source's frame grid (when fps is given) so the
    joined picture and sound stay in step."""
    inside = sorted((w for w in words if start <= w['start'] < end), key=lambda w: w['start'])
    if not inside: return [(start, end)]
    snap = (lambda t: round(t*fps)/fps) if fps else (lambda t: t)
    ranges = []
    a = max(start, inside[0]['start']-LEAD)
    last = inside[0]['end']
    for w in inside[1:]:
        if w['start']-last > MAX_GAP:
            ranges.append((a, last+TAIL))
            a = w['start']-LEAD
        last = max(last, w['end'])
    ranges.append((a, min(end, last+TAIL*2)))
    out = []
    for a, b in ranges:
        a, b = snap(max(start, a)), snap(min(end, b))
        if b-a <= 1/60: continue
        if out and a <= out[-1][1]: out[-1] = (out[-1][0], max(out[-1][1], b))
        else: out.append((a, b))
    return out or [(start, end)]


def mapper(ranges):
    """source seconds -> tight seconds (a time inside a cut lands on the start of the next kept part)."""
    def to_tight(t):
        done = 0.
        for a, b in ranges:
            if t < a: return done
            if t <= b: return done+t-a
            done += b-a
        return done
    return to_tight


def tighten(plan, ranges):
    to_tight = mapper(ranges)
    total = round(sum(b-a for a, b in ranges), 4)
    beats = []
    for beat in plan['beats']:
        b = dict(beat, start=round(to_tight(beat['start']), 4), end=round(to_tight(beat['end']), 4))
        empty = not (b.get('spoken_text') or '').strip()
        if beats and (b['end']-b['start'] < MIN_BEAT or empty):
            beats[-1]['end'] = b['end']           # the previous beat runs on through this one
            continue
        if not beats and empty and len(plan['beats']) > 1:
            continue                              # a pause at the very start: the next beat starts at 0
        beats.append(b)
    if not beats: return dict(plan, source_window={'start': 0., 'end': total}, total_duration=total)
    beats[0]['start'] = 0.
    for x, y in zip(beats, beats[1:]): y['start'] = x['end']
    beats[-1]['end'] = total
    beats = [b for b in beats if b['end']-b['start'] > 1/60] or beats[:1]
    hook = plan.get('hook') or {}
    out = dict(plan, beats=beats, source_window={'start': 0., 'end': total}, total_duration=total)
    if hook: out['hook'] = dict(hook, start=round(to_tight(hook.get('start', 0)), 4), end=round(to_tight(hook.get('end', 0)), 4))
    return out


def tight_source(source, ranges, folder):
    """The kept ranges of `source` (picture + sound) joined into one .mov, short fades on the sound at each cut."""
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(json.dumps([str(source), os.path.getsize(source), os.path.getmtime(source), ranges]).encode()).hexdigest()[:16]
    out = folder/f'tight-{key}.mov'
    if out.is_file(): return out
    for old in folder.glob('tight-*.mov'): old.unlink(missing_ok=True)
    parts, labels = [], ''
    for n, (a, b) in enumerate(ranges):
        d = b-a; f = min(.008, d/4)
        parts.append(f'[0:v]trim=start={a:.5f}:end={b:.5f},setpts=PTS-STARTPTS[v{n}]')
        parts.append(f'[0:a]atrim=start={a:.5f}:end={b:.5f},asetpts=PTS-STARTPTS,aresample=48000,'
                     f'afade=t=in:d={f:.4f},afade=t=out:st={d-f:.5f}:d={f:.4f}[a{n}]')
        labels += f'[v{n}][a{n}]'
    parts.append(f'{labels}concat=n={len(ranges)}:v=1:a=1[v][a]')
    part = out.with_suffix('.part.mov')
    run = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source), '-filter_complex', ';'.join(parts),
                          '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '14', '-pix_fmt', 'yuv420p',
                          '-c:a', 'pcm_s16le', '-ac', '2', str(part)], capture_output=True, text=True, timeout=3600)
    if run.returncode: raise RuntimeError(f'could not join the speech parts: {run.stderr[-800:]}')
    part.replace(out)
    return out


def prepare(plan, words, source, folder):
    """(plan, source, removed seconds) for the render: the tight plan over the tight source, or the originals when
    there is nothing worth cutting (< 0.25 s) or tightening is off."""
    if not enabled() or not words or not Path(source).is_file(): return plan, source, 0.
    w0, w1 = plan['source_window']['start'], plan['source_window']['end']
    ranges = keep_ranges(words, w0, w1, _fps(source))
    removed = (w1-w0)-sum(b-a for a, b in ranges)
    if removed < .25: return plan, source, 0.
    return tighten(plan, ranges), tight_source(source, ranges, folder), round(removed, 2)
