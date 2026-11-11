"""Measured (not AI-judged) facts about a video file for the Trend Analysis page.

Everything here comes straight from FFmpeg, so the page can chart it as data:
  duration, frame size, shot changes (scene detection) and a loudness envelope.
Every function fails soft: a measurement that can't be taken is simply missing,
and the page shows it as "not measured" instead of guessing.
"""
import re
import subprocess
from pathlib import Path

SCENE_THRESHOLD = 0.32   # FFmpeg scene score that counts as a shot change
WINDOW = 0.5             # seconds per loudness sample
LIMIT = 120              # only the first two minutes are measured (keeps research fast)


def _run(args, timeout=150):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def probe(path: Path) -> dict:
    result = _run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height:format=duration',
                   '-of', 'default=noprint_wrappers=1', str(path)], timeout=30)
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    out = {}
    try: out['duration'] = round(float(values['duration']), 3)
    except (KeyError, ValueError): pass
    for key in ('width', 'height'):
        try: out[key] = int(values[key])
        except (KeyError, ValueError): pass
    return out


def shot_changes(path: Path, limit: float = LIMIT) -> list[float]:
    """Seconds where the picture changes enough to count as a new shot."""
    result = _run(['ffmpeg', '-hide_banner', '-nostats', '-t', str(limit), '-i', str(path), '-an',
                   '-vf', f"scale=160:-2,select='gt(scene,{SCENE_THRESHOLD})',showinfo", '-f', 'null', '-'])
    if result.returncode != 0:
        raise RuntimeError('scene detection failed')
    times = [round(float(t), 2) for t in re.findall(r'pts_time:([0-9.]+)', result.stderr)]
    cuts = []
    for t in sorted(times):   # two detections closer than 0.25s are one cut (flashes, fades)
        if t > 0.1 and (not cuts or t - cuts[-1] >= 0.25):
            cuts.append(t)
    return cuts


def loudness(path: Path, limit: float = LIMIT) -> list[float]:
    """RMS loudness in dBFS for each WINDOW seconds (silence is clamped to -60)."""
    rate = 8000
    result = _run(['ffmpeg', '-hide_banner', '-nostats', '-t', str(limit), '-i', str(path), '-vn',
                   '-af', f'aresample={rate},asetnsamples={int(rate * WINDOW)},astats=metadata=1:reset=1,'
                          'ametadata=print:key=lavfi.astats.Overall.RMS_level', '-f', 'null', '-'])
    if result.returncode != 0:
        raise RuntimeError('loudness failed')
    levels = []
    for value in re.findall(r'RMS_level=(-?[0-9.]+|-inf)', result.stderr):
        level = -60.0 if value == '-inf' else max(-60.0, float(value))
        levels.append(round(level, 1))
    return levels


def measure_video(path: Path, limit: float = LIMIT) -> dict:
    """All measurements for one file. Missing keys mean "couldn't be measured"."""
    path = Path(path)
    out = {'source': 'ffmpeg', 'scene_threshold': SCENE_THRESHOLD, 'window': WINDOW}
    try: out.update(probe(path))
    except Exception: pass
    measured = min(limit, out.get('duration') or limit)
    out['measured_seconds'] = round(measured, 2)
    try: out['cuts'] = shot_changes(path, limit)
    except Exception: pass
    try:
        levels = loudness(path, limit)
        if levels: out['loudness'] = levels
    except Exception: pass
    return out
