"""Fan-edit style effects: subject cutout backgrounds, color pop, shape reveals, glitch,
ink, zoom/whip blur, flashes and an "Edited by" end card.

All rendering is local (NumPy/OpenCV/Pillow + FFmpeg) and free. Subject mattes come from
segmentation.Mattes. Events use generated-clip seconds like every other timeline field; the
stylized file has the source's size, duration and audio, so the existing export pipeline
(trim, captions, B-roll, OpenChatCut sequences) runs on it unchanged.
"""
import hashlib
import json
import logging
import math
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException

from .advanced_models import StyleEvent, StyleInfo, StyleOptions
from .style_effects import MATTE_KINDS, PALETTES, apply_events  # noqa: F401 (re-exported)
from .style_text import apply_text, plan_text
from .style_looks import apply_looks

LOG = logging.getLogger(__name__)
FPS = 30
BASE_KINDS = ('bg_swap', 'shape_reveal', 'color_pop', 'outline', 'ink')
ACCENT_KINDS = ('glitch', 'zoom_blur', 'whip', 'flash')
# ---------------------------------------------------------------- rendering

def _probe(path):
    probe = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration',
                                       '-of', 'json', str(path)], capture_output=True, text=True, check=True, timeout=30).stdout)
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    return int(video['width']), int(video['height']), float(probe['format']['duration']), any(s['codec_type'] == 'audio' for s in probe['streams'])


def render(source, output, style, matte_cache):
    """Write `output` (same size, duration and audio as `source`) with the style events applied."""
    import numpy as np
    from .segmentation import Mattes
    width, height, duration, has_audio = _probe(source)
    events = [(i, e) for i, e in enumerate(style.events) if e.start < duration]
    mattes = Mattes(source, matte_cache)
    texts = [(i, e) for i, e in events if e.kind == 'text']
    looks = [(i, e) for i, e in events if e.kind == 'film']
    cards = None
    spans = [(e.start, min(duration, e.start+e.duration)) for _, e in events if e.kind in MATTE_KINDS or (e.kind == 'text' and e.behind)]
    if spans:
        mattes.ensure(spans)
    w, h = width-width % 2, height-height % 2
    if any(e.kind == 'motion_card' for _, e in events):
        from .motion_cards import Cards
        cards = Cards([e for _, e in events if e.kind == 'motion_card'], w, h, '#%02x%02x%02x' % PALETTES[style.palette][0], Path(matte_cache).parent)
    ffmpeg = shutil.which('ffmpeg') or 'ffmpeg'
    decoder = subprocess.Popen([ffmpeg, '-nostdin', '-v', 'error', '-i', str(source), '-vf', f'fps={FPS},crop={w}:{h}:0:0',
                                '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    encoder = subprocess.Popen([ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}',
                                '-r', str(FPS), '-i', '-', '-i', str(source), '-map', '0:v', *(['-map', '1:a', '-c:a', 'copy'] if has_audio else []),
                                '-t', f'{duration:.3f}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-pix_fmt', 'yuv420p',
                                '-movflags', '+faststart', str(output)], stdin=subprocess.PIPE)
    size = w*h*3; number = 0
    try:
        while True:
            raw = decoder.stdout.read(size)
            if len(raw) < size: break
            t = number/FPS
            if any(0 <= t-e.start < e.duration for _, e in events):
                frame = np.frombuffer(raw, np.uint8).reshape(h, w, 3).astype(np.float32)
                if looks:
                    frame = apply_looks(frame, t, looks, number)
                frame = apply_events(frame, t, events, style.palette, mattes.at, number)
                if texts:
                    frame = apply_text(frame, t, texts, style.palette, mattes.at, number)
                if cards:
                    frame = cards.overlay(frame, t)
                raw = frame.clip(0, 255).astype(np.uint8).tobytes()
            encoder.stdin.write(raw)
            number += 1
    finally:
        encoder.stdin.close()
        decoder.stdout.close()
        decoder.wait(timeout=60); encoder.wait(timeout=300)
    if encoder.returncode != 0 or not Path(output).is_file():
        raise HTTPException(503, 'Stylized effects render failed; your saved edit is unchanged.')
    return output


def _code_version():
    folder = Path(__file__).parent
    return hashlib.sha256(b''.join(p.read_bytes() for p in sorted(folder.glob('style*.py'))+[folder/'segmentation.py'])).hexdigest()[:16]


@contextmanager
def stylized(source, state, cache_root):
    """Yield the source, or a cached stylized copy when the edit has style events."""
    if not state.stylize or not state.stylize.events:
        yield source
        return
    source = Path(source)
    st = source.stat()
    cache_root = Path(cache_root); cache_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(json.dumps({'style': state.stylize.model_dump(), 'source': [source.name, st.st_size, st.st_mtime_ns],
                                        'code': _code_version()}, sort_keys=True).encode()).hexdigest()[:32]
    target = cache_root/f'{digest}.mp4'
    if not target.is_file():
        staged = cache_root/f'{digest}.partial.mp4'
        try:
            render(source, staged, state.stylize, cache_root/'mattes')
            staged.replace(target)
        except (OSError, subprocess.SubprocessError, ValueError, StopIteration) as exc:
            LOG.warning('stylize render failed: %s', exc)
            staged.unlink(missing_ok=True)
            raise HTTPException(503, 'Stylized effects render failed; your saved edit is unchanged.') from None
        for old in sorted(cache_root.glob('*.mp4'), key=lambda p: p.stat().st_mtime)[:-6]:
            old.unlink(missing_ok=True)  # keep the most recent renders only
    yield target


# ---------------------------------------------------------------- planning

def _beat_grid(state, info, audio_store):
    """Musical beats in clip seconds: music track, else the clip's own audio, else 120 BPM."""
    from .beats import analyze
    beats = []
    music = next((s for s in state.audio if s.track == 'music'), None)
    if music is not None and audio_store is not None:
        try:
            measured = analyze(audio_store.media(music.asset_id))
            beats = [music.start+b-music.offset for b in measured['beats'] if 0 <= b-music.offset < music.duration]
        except (OSError, subprocess.SubprocessError, HTTPException, KeyError):
            beats = []
    if not beats:
        beats = list(info.get('style_beats') or [])
    beats = sorted(b for b in beats if state.start <= b < state.end)
    if len(beats) < 4:
        beats = [state.start+i*.5 for i in range(int((state.end-state.start)/.5)+1)]
    merged = []
    for b in beats:  # an event per ~0.35s at most keeps the effect readable
        if not merged or b-merged[-1] >= .35: merged.append(b)
    if not merged or merged[0] > state.start+.05: merged.insert(0, state.start)
    return merged


def beats_for(state, info, audio_store=None):
    return _beat_grid(state, info, audio_store)


def add_broll(state, stock, query, beats, count=3):
    """Insert short free stock (Pexels) shots on spread-out beats; returns how many were placed."""
    import uuid
    from backend.broll import Asset, Segment
    results = [r for r in stock.search(query)['results'] if r['duration'] >= 1.5]
    picks = [b for b in beats[3::max(1, len(beats)//(count+1))] if b+1 < state.end][:count]
    placed = 0
    for at, entry in zip(picks, results):
        try:
            stock.media(entry['id'])
        except (HTTPException, OSError):
            continue
        state.broll.append(Segment(id=uuid.uuid4().hex, asset=Asset(**entry), start=round(at, 3), duration=.9, offset=.3, mode='fill'))
        placed += 1
    return placed


def plan_preset(state, info, options, audio_store=None):
    span_end = state.end
    card = min(1.8, (state.end-state.start)/4) if options.end_card else 0
    beats = [b for b in _beat_grid(state, info, audio_store) if b < span_end-card-.1]
    step = max(1, math.ceil(len(beats)/56))
    beats = beats[::step]
    bounds = beats+[span_end-card]
    wanted = list(dict.fromkeys(options.effects))
    base = [k for k in wanted if k in BASE_KINDS]
    accents = [k for k in wanted if k in ACCENT_KINDS]
    if not wanted:
        base = ['bg_swap', 'shape_reveal', 'bg_swap', 'color_pop', 'bg_swap', 'outline', 'bg_swap', 'ink'] if options.intensity == 'high' \
            else ['color_pop', 'color_pop', 'color_pop', 'bg_swap']
        accents = ['glitch', 'zoom_blur', 'flash', 'whip']
    backgrounds = list(dict.fromkeys(options.backgrounds)) or ['comic', 'speedlines', 'neon', 'paper', 'halftone']
    shapes = ['x', 'star', 'slash']
    events = []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        if b-a < .1 or not base: continue
        kind = base[i % len(base)]
        events.append(StyleEvent(start=round(a, 3), duration=round(b-a, 3), kind=kind,
                                 background=backgrounds[i % len(backgrounds)], shape=shapes[i % 3]))
    merged = []
    for e in events:  # one long event instead of many identical ones (e.g. color pop only)
        last = merged[-1] if merged else None
        if last and last.kind == e.kind and last.background == e.background and e.kind in ('color_pop', 'outline', 'ink') \
                and abs(last.start+last.duration-e.start) < .01:
            last.duration = round(last.duration+e.duration, 3)
        else:
            merged.append(e)
    events = merged
    if accents:
        cuts = [c for c in info.get('scene_boundaries', []) if state.start+.2 < c < span_end-card-.2]
        marks = [(c, 'cut') for c in cuts]+[(b, 'beat') for b in beats[2::4]]
        for n, (at, why) in enumerate(sorted(marks)):
            kind = ('zoom_blur' if 'zoom_blur' in accents else accents[0]) if why == 'cut' else accents[n % len(accents)]
            length = {'glitch': .18, 'zoom_blur': .26, 'whip': .22, 'flash': .14}[kind]
            start = max(state.start, at-(length/2 if kind in ('zoom_blur', 'whip') else 0))
            events.append(StyleEvent(start=round(start, 3), duration=length, kind=kind))
    if options.texts:
        events += plan_text(state, [] if options.words else info.get('cues', []), beats, options.palette,
                            info.get('clip_title', ''), words=options.words)
    if card:
        events.append(StyleEvent(start=round(span_end-card, 3), duration=round(card, 3), kind='title_card', text=options.end_card))
    if not events:
        raise HTTPException(422, 'No room for style effects in the current trim.')
    events = sorted(events, key=lambda e: (e.start, e.kind in ACCENT_KINDS or e.kind == 'title_card'))[:80]
    return StyleInfo(palette=options.palette, events=events,
                     note=f'{len(events)} effects on {len(beats)} beats; subject cutouts are computed locally.')
