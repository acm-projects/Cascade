"""Stage 4: render a beat plan with Remotion (the remotion/ project at the repository root).

The renderer reads ONLY the plan and assets: no model is called here.

    render(plan, source, out, work) -> report

1. prepare(): a 60 fps H.264 proxy of the plan's window (frame 0 = source_window.start), the fonts, film grain
   tiles and the beat assets go into work/public; the props go into work/props.json.
2. One `npx remotion bundle` per render, then `npx remotion render <bundle> Edit --frames=a-b` for every beat
   whose segment is not cached. A segment's cache key covers the beat, the beat before it (its transition draws
   that beat's tail), both beats' assets, the size and the renderer's own source, so a revision re-renders only
   the beats it changed (and the beat right after each).
3. The segments are joined without re-encoding, the speech (+ sound effects, Stage 5) is mixed and muxed, and the
   result is checked: every segment has exactly its beat's frame count, so every beat starts within half a
   frame of the plan, and the audio is cut from the same window start as the picture.

Environment: CASCADE_REMOTION_BROWSER (a Chrome to use instead of Remotion's own download),
CASCADE_REMOTION_CONCURRENCY (default: CPU count, at most 4).
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

LOG = logging.getLogger(__name__)
FPS = 60
REPO = Path(__file__).resolve().parents[4]
REMOTION = Path(os.getenv('CASCADE_REMOTION_DIR', REPO/'remotion'))
FONTS = Path(__file__).resolve().parents[1]/'cinema'/'fonts'
FONT_FILES = ('Anton-Regular.ttf', 'InstrumentSerif-Italic.ttf', 'InstrumentSerif-Regular.ttf', 'Inter.ttf')
RUN = dict(capture_output=True, text=True)


class RenderError(RuntimeError):
    """The render could not finish; the message is safe to show."""


def to_frame(seconds, fps=FPS):
    """Mirrors toFrame() in remotion/src/lib/timing.js."""
    return int(round(seconds*fps+1e-6))


def frames_for(plan, fps=FPS):
    """[(beat id, first frame, end frame)] mirroring beatFrames() in remotion/src/lib/timing.js."""
    origin = plan['source_window']['start']
    return [(b['id'], to_frame(b['start']-origin, fps), to_frame(b['end']-origin, fps)) for b in plan['beats']]


def total_frames(plan, fps=FPS):
    return to_frame(plan['source_window']['end']-plan['source_window']['start'], fps)


def available():
    """None if renders can run here, else why not (plain words)."""
    if not shutil.which('node') or not shutil.which('npx'): return 'Node.js is not installed on the server.'
    if not (REMOTION/'node_modules'/'remotion').is_dir(): return f'The renderer is not installed (run: npm --prefix {REMOTION} ci).'
    if not shutil.which('ffmpeg'): return 'FFmpeg is not installed on the server.'
    return None


def renderer_version():
    """A hash of the renderer's own source, so template changes invalidate cached segments."""
    digest = hashlib.sha1()
    for path in sorted((REMOTION/'src').rglob('*')):
        if path.is_file(): digest.update(path.relative_to(REMOTION).as_posix().encode()); digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def probe_frames(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries', 'stream=nb_read_packets',
                          '-of', 'csv=p=0', str(path)], **RUN, timeout=300)
    digits = ''.join(ch for ch in out.stdout.split('\n')[0] if ch.isdigit())
    return int(digits or 0)


def probe_duration(path, stream='a:0'):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', stream, '-show_entries', 'stream=duration', '-of', 'csv=p=0', str(path)],
                         **RUN, timeout=120)
    try: return float(out.stdout.strip())
    except ValueError: return 0.


def output_size(source, ratio='original'):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height:stream_side_data=rotation',
                          '-of', 'json', str(source)], **RUN, timeout=60, check=True)
    stream = json.loads(out.stdout)['streams'][0]
    w, h = stream['width'], stream['height']
    if ratio == '9:16': return 1080, 1920
    scale = min(1., 1920/max(w, h))
    return int(round(w*scale/2))*2, int(round(h*scale/2))*2


def _run(cmd, cwd=None, timeout=3600):
    run = subprocess.run(cmd, cwd=cwd, timeout=timeout, **RUN)
    if run.returncode:
        LOG.warning('command failed: %s\n%s', ' '.join(map(str, cmd))[:300], (run.stderr or run.stdout)[-2000:])
        raise RenderError('The video render failed. Your plan is saved; try the request again.')
    return run


def _grain(folder, width, height, tiles=6):
    import numpy as np
    from PIL import Image
    folder.mkdir(parents=True, exist_ok=True)
    rand = np.random.default_rng(7)
    for n in range(tiles):
        path = folder/f'{n}.png'
        if path.is_file(): continue
        noise = rand.normal(128, 42, (height//2, width//2)).clip(0, 255).astype('uint8')
        Image.fromarray(noise, 'L').resize((width, height), Image.BILINEAR).save(path)


def proxy(source, plan, path, size):
    """The plan's window as a constant 60 fps H.264 file: frame n is source time start + n/60."""
    start, end = plan['source_window']['start'], plan['source_window']['end']
    frames = total_frames(plan)
    stamp = path.with_suffix('.json')
    key = {'source': str(source), 'size': os.path.getsize(source), 'mtime': os.path.getmtime(source), 'start': start, 'end': end, 'wh': list(size)}
    if path.is_file() and stamp.is_file() and json.loads(stamp.read_text()) == key: return path
    w, h = size
    _run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', f'{start:.4f}', '-i', str(source), '-frames:v', str(frames),
          '-vf', f'fps={FPS},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1', '-an',
          '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-g', '30', '-pix_fmt', 'yuv420p', str(path)], timeout=1800)
    stamp.write_text(json.dumps(key))
    return path


def prepare(plan, source, work, assets=None, ratio='original', labels=False):
    """Fill work/public and write work/props.json. Returns the props."""
    work = Path(work); public = work/'public'
    (public/'fonts').mkdir(parents=True, exist_ok=True)
    size = output_size(source, ratio)
    for name in FONT_FILES:
        if not (public/'fonts'/name).is_file(): shutil.copy2(FONTS/name, public/'fonts'/name)
    _grain(public/'grain', *size)
    proxy(source, plan, public/'source.mp4', size)
    props = {'plan': plan, 'fps': FPS, 'width': size[0], 'height': size[1], 'source': 'source.mp4',
             'assets': {str(k): v for k, v in (assets or {}).items()}, 'options': {'grain': True, 'labels': labels}}
    (work/'props.json').write_text(json.dumps(props))
    return props


def _npx(*args):
    command = ['npx', '--no-install', 'remotion', *args]
    browser = os.getenv('CASCADE_REMOTION_BROWSER', '').strip()
    if browser and args[0] == 'render': command.append(f'--browser-executable={browser}')
    return command


def bundle(work):
    out = Path(work)/'bundle'
    shutil.rmtree(out, ignore_errors=True)
    _run(_npx('bundle', 'src/index.ts', f'--public-dir={Path(work).resolve()/"public"}', f'--out-dir={out.resolve()}'), cwd=REMOTION, timeout=900)
    return out


def segment_keys(plan, props):
    """Cache key per beat id: the beat, the beat before it, their assets, the frame size and the renderer."""
    version = renderer_version()
    beats = plan['beats']
    keys = {}
    for n, (beat_id, a, b) in enumerate(frames_for(plan)):
        prev = beats[n-1] if n else None
        payload = {'beat': beats[n], 'prev': prev, 'frames': [a, b], 'size': [props['width'], props['height']], 'fps': FPS,
                   'assets': [props['assets'].get(str(beat_id)), prev and props['assets'].get(str(prev['id']))],
                   'window': plan['source_window'], 'options': props['options'], 'renderer': version,
                   'source': props.get('source_key')}
        keys[beat_id] = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]
    return keys


def render(plan, source, out, work, assets=None, audio=None, progress=None, ratio='original', labels=False, make_assets=None):
    """Render `plan` over `source` to `out` (mp4). `audio(plan, source, work) -> wav path` mixes the sound;
    without it the window's own sound is used. `make_assets(work, size) -> (assets, credits)` runs once the proxy
    exists (cut-outs are made from it). Returns a report with timings and which beats were rendered."""
    report_progress = progress or (lambda amount, stage: None)
    why = available()
    if why: raise RenderError(why)
    started = time.time()
    timings = {}
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    segments = work/'segments'; segments.mkdir(exist_ok=True)
    report_progress(.02, 'Preparing the footage…')
    props = prepare(plan, source, work, assets, ratio, labels)
    credits = []
    if make_assets:
        report_progress(.04, 'Finding footage and cutting out the speaker…')
        t = time.time()
        assets, credits = make_assets(work, (props['width'], props['height']))
        props = prepare(plan, source, work, assets, ratio, labels)
        timings['assets'] = round(time.time()-t, 1)
    props['source_key'] = json.loads((work/'public'/'source.json').read_text())
    keys = segment_keys(plan, props)
    frames = frames_for(plan)
    dirty = [(i, a, b) for i, a, b in frames if not (segments/f'{keys[i]}.mp4').is_file()]
    timings['prepare'] = round(time.time()-started, 1)
    if dirty:
        report_progress(.08, 'Getting the renderer ready…')
        t = time.time(); served = bundle(work); timings['bundle'] = round(time.time()-t, 1)
        concurrency = os.getenv('CASCADE_REMOTION_CONCURRENCY', '') or str(max(1, min(4, os.cpu_count() or 1)))
        t = time.time()
        for n, (beat_id, a, b) in enumerate(dirty):
            report_progress(.1+.75*n/len(dirty), f'Rendering beat {beat_id} ({n+1} of {len(dirty)})…')
            part = segments/f'{keys[beat_id]}.part.mp4'
            _run(_npx('render', str(served.resolve()), 'Edit', str(part.resolve()), f'--props={(work/"props.json").resolve()}',
                      f'--frames={a}-{b-1}', '--codec=h264', '--crf=16', '--pixel-format=yuv420p', f'--concurrency={concurrency}',
                      '--muted', '--log=error'), cwd=REMOTION, timeout=3600)
            got = probe_frames(part)
            if got != b-a: raise RenderError(f'Beat {beat_id} rendered {got} frames instead of {b-a}.')
            part.replace(segments/f'{keys[beat_id]}.mp4')
        timings['beats'] = round(time.time()-t, 1)
    report_progress(.88, 'Joining the beats…')
    listing = work/'segments.txt'
    listing.write_text(''.join(f"file '{(segments/(keys[i]+'.mp4')).resolve()}'\n" for i, _, _ in frames))
    picture = work/'picture.mp4'
    _run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy', str(picture)])
    report_progress(.92, 'Mixing the sound…')
    total = total_frames(plan)
    sound = audio(plan, source, work) if audio else speech(plan, source, work/'speech.wav')
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.stem+'.part.mp4')
    _run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(picture), '-i', str(sound), '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
          '-c:a', 'aac', '-b:a', '256k', '-t', f'{total/FPS:.5f}', '-movflags', '+faststart', str(part)])
    part.replace(out)
    checks = verify(plan, out)
    timings['total'] = round(time.time()-started, 1)
    report_progress(1, 'Rendered.')
    return {'frames': total, 'seconds': round(total/FPS, 3), 'fps': FPS, 'size': [props['width'], props['height']],
            'rendered_beats': [i for i, _, _ in dirty], 'reused_beats': [i for i, _, _ in frames if i not in {d[0] for d in dirty}],
            'timings': timings, 'checks': checks, 'credits': credits}


def speech(plan, source, path):
    """The source's own sound over the plan's window, cut at the same start as the picture."""
    start, end = plan['source_window']['start'], plan['source_window']['end']
    _run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', f'{start:.4f}', '-i', str(source), '-t', f'{end-start:.4f}', '-vn',
          '-ac', '2', '-ar', '48000', str(path)])
    return path


def verify(plan, out):
    """Frame count, per-beat start times (from the frame grid) and the audio length, against the plan."""
    total = total_frames(plan)
    frames = probe_frames(out)
    origin = plan['source_window']['start']
    worst = max(abs(a/FPS-(b['start']-origin)) for (_, a, _), b in zip(frames_for(plan), plan['beats']))
    audio = probe_duration(out, 'a:0')
    result = {'video_frames': frames, 'expected_frames': total, 'worst_beat_start_error_frames': round(worst*FPS, 3),
              'audio_seconds': round(audio, 4), 'video_seconds': round(frames/FPS, 4)}
    result['ok'] = frames == total and worst*FPS <= 1 and abs(audio-frames/FPS) <= 1/FPS
    if not result['ok']: raise RenderError(f'The render does not match the plan: {result}')
    return result
