"""Execute a saved AI sequence with OpenChatCut and render it to MP4.

Cascade compiles the validated sequence into a compact spec; the Cascade-owned
driver (openchatcut_driver.mts) applies it to a fresh OpenChatCut project in one
offline edit session and renders it with OpenChatCut's export pipeline. No
OpenChatCut agent, LLM, browser tab, or network service is involved, and the
subprocess receives an allowlisted environment without Cascade secrets.
"""
import json
import re
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from fastapi import HTTPException

from .fablecut_render import sequence_pieces
from .retiming import Clock
from .sequence_models import OCC_GRAIN, OCC_LOOKS, OCC_SHAKE, OCC_TRANSITIONS, OCC_ZOOMS

LOG = logging.getLogger(__name__)
VERSION = '0.2.17'
DRIVER = Path(__file__).with_name('openchatcut_driver.mts')
FPS = 30
_render_lock = threading.Lock()
CHROME_CANDIDATES = ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                     '/Applications/Chromium.app/Contents/MacOS/Chromium', '/usr/bin/google-chrome', '/usr/bin/chromium')


def engine_path():
    path = Path(os.getenv('CASCADE_OPENCHATCUT_DIR', str(Path(__file__).parent/'.cache/openchatcut'))).resolve()
    try:
        if json.loads((path/'package.json').read_text())['version'] != VERSION: raise ValueError('version')
        if 'GNU AFFERO GENERAL PUBLIC LICENSE' not in (path/'LICENSE').read_text()[:200]: raise ValueError('license')
        if not (path/'node_modules/.bin/tsx').exists() or not (path/'cli/main.ts').is_file(): raise ValueError('runtime')
    except (OSError, ValueError, KeyError):
        raise HTTPException(503, f'OpenChatCut {VERSION} is not installed. See docs/openchatcut-ai-editor.md. Your edit is preserved.') from None
    return path


def available():
    try:
        engine_path(); _tool('ffmpeg'); _chrome()
        return True
    except HTTPException:
        return False


def _tool(name):
    found = os.getenv(f'OPENCHATCUT_{name.upper()}') or shutil.which(name) or (f'/opt/homebrew/bin/{name}' if Path(f'/opt/homebrew/bin/{name}').exists() else None)
    if not found: raise HTTPException(503, f'{name} is required for OpenChatCut rendering.')
    return found


def _chrome():
    found = os.getenv('CASCADE_OPENCHATCUT_CHROME') or next((c for c in CHROME_CANDIDATES if Path(c).exists()), None)
    if not found: raise HTTPException(503, 'Google Chrome or Chromium is required for OpenChatCut rendering. Set CASCADE_OPENCHATCUT_CHROME.')
    return found


def canvas(state, info):
    if state.fablecut.ratio == '9:16': return 1080, 1920
    w, h = info['width'], info['height']
    scale = 1080/min(w, h)
    return round(w*scale/2)*2, round(h*scale/2)*2


def build_spec(state, info, audio_store, base, folder, output, base_size=None):
    seq = state.fablecut
    pieces = sequence_pieces(state)
    width, height = canvas(state, info)
    total = sum(p['duration'] for p in pieces)
    media = {'base': str(base)}
    def add_media(ident):
        if ident not in media:
            target = folder/f'{ident}.wav'
            shutil.copy2(audio_store.media(ident), target)
            media[ident] = str(target)
        return ident

    shots = []
    for i, part in enumerate(pieces):
        shot = part['shot']
        effects = [{'assetId': OCC_SHAKE, 'overrides': {'strength': round(min(5, max(.3, shot.shake*.35)), 2)}}] if shot.shake > 0 else []
        shots.append({'media': 'base', 'sourceStart': part['input'], 'sourceEnd': part['input']+part['consumed'],
                      'speed': shot.rate_from, 'mute': shot.rate_from != 1,
                      'zoom': {'assetId': OCC_ZOOMS[shot.zoom_style], 'overrides': {'magnification': round(1+(shot.zoom-1)*2, 3)}}
                      if shot.zoom > 1.02 else None, 'fx': effects,
                      'transition': {'assetId': OCC_TRANSITIONS[shot.transition], 'frames': 8}
                      if i and shot.transition != 'none' else None})
    grade = {'brightness': 1 + seq.grade*.6, 'contrast': 1 + seq.grade, 'saturate': 1 + seq.grade*.8,
             'look': OCC_LOOKS.get(seq.look), 'lookIntensity': .45,
             'fx': [{'assetId': OCC_GRAIN, 'overrides': {'amount': .05, 'size': 1.0}}] if seq.film_grain else []}  # subtle texture, not noise

    audio = []
    # Manual music/SFX segments, rebuilt on the sequence clock (never pitch-warped).
    for segment in state.audio:
        add_media(segment.asset_id)
        asset = audio_store.entry(segment.asset_id)
        lane = 'music' if segment.track == 'music' else 'sfx'
        for part in pieces:
            a = max(part['source_start'], segment.start); b = min(part['source_end'], segment.start+segment.duration)
            if b <= a: continue
            at = part['start'] + (Clock(state.model_copy(update={'fablecut': None})).output(a) - part['input']) / part['shot'].rate_from
            offset = (segment.offset + a - segment.start) % asset['duration'] if segment.loop else segment.offset + a - segment.start
            if offset >= asset['duration']: continue
            audio.append({'media': segment.asset_id, 'at': round(at, 3), 'sourceStart': round(offset, 3),
                          'duration': round(min(b-a, asset['duration']-offset), 3), 'volume': segment.volume, 'lane': lane})
    if seq.music_asset_id and not any(a.track == 'music' for a in state.audio):
        asset = audio_store.entry(seq.music_asset_id)
        if asset['kind'] != 'music': raise HTTPException(422, 'Select a music asset for the sequence bed.')
        add_media(seq.music_asset_id)
        t = 0.0
        while t < total - .01:
            d = min(asset['duration'], total - t)
            audio.append({'media': seq.music_asset_id, 'at': round(t, 3), 'sourceStart': 0, 'duration': round(d, 3),
                          'volume': min(1, seq.music_volume*2.5), 'fadeIn': .08 if t == 0 else 0,
                          'fadeOut': .35 if t+d >= total-.01 else 0, 'lane': 'music'})
            t += d
    if seq.sound_design:
        library = audio_store.library()
        whoosh = next(a for a in library if a['name'] == 'Air whoosh')
        impact = next(a for a in library if a['name'] == 'Impact hit')
        for i, part in enumerate(pieces[1:], 1):
            shot = part['shot']
            if shot.transition == 'none' and shot.zoom <= 1.05: continue
            asset = whoosh if shot.transition != 'none' else impact
            add_media(asset['id'])
            at = max(0, part['start'] - (.08 if asset is whoosh else 0))
            audio.append({'media': asset['id'], 'at': round(at, 3), 'sourceStart': 0,
                          'duration': round(min(asset['duration'], total-at), 3), 'volume': .5, 'fadeOut': .1, 'lane': 'sfx'})

    texts = []
    if seq.title:
        texts.append({'text': seq.title.upper(), 'at': 0.05, 'duration': min(1.4, total), 'fontSize': 104, 'color': '#ffffff', 'y': -30, 'pop': True, 'lane': 'title'})
    if state.captions.enabled:
        clock = Clock(state.model_copy(update={'fablecut': None}))
        y = {'top': -30, 'middle': 0, 'bottom': 30}[state.captions.position]
        for part in pieces:
            for index, cue in enumerate(info['cues']):
                a = max(part['source_start'], cue['start']); b = min(part['source_end'], cue['end'])
                if b <= a: continue
                words = state.texts.get(str(index), cue['text']).split()
                if not words: continue
                # Existing VTT cue timing only; word groups are estimated, not forced-aligned.
                begin = part['start'] + (clock.output(a) - part['input']) / part['shot'].rate_from
                span = (b - a) / part['shot'].rate_from
                for w in range(0, len(words), 3):
                    group = words[w:w+3]
                    texts.append({'text': ' '.join(group), 'at': round(begin + span*w/len(words), 3),
                                  'duration': round(max(.1, span*len(group)/len(words)), 3),
                                  'fontSize': int(max(72, min(110, state.captions.size*2.6))), 'color': state.captions.color,
                                  'fontWeight': 900 if state.captions.bold else 600, 'y': y,
                                  'pop': state.captions.animation != 'none'})
    # One clip per track at a time: trim caption groups so they never overlap.
    captions = sorted((t for t in texts if t.get('lane') != 'title'), key=lambda t: t['at'])
    for current, following in zip(captions, captions[1:]):
        current['duration'] = round(max(.07, min(current['duration'], following['at'] - current['at'] - 1/FPS)), 3)
    captions = [t for t in captions if t['duration'] > .067]
    texts = [t for t in texts if t.get('lane') == 'title'] + captions
    return {'name': 'Cascade AI Editor', 'width': width, 'height': height, 'fps': FPS, 'media': media,
            'shots': shots, 'grade': grade, 'audio': audio, 'texts': texts, 'output': str(output),
            'resolution': '1080p', 'framing': seq.framing if seq.ratio == '9:16' else 'fit',
            'frameScale': frame_scale(seq.framing, (width, height), base_size or (info['width'], info['height']))}, total


def frame_scale(framing, canvas_size, base_size):
    """Scale over the contain fit: true cover for 'cover' (capped to protect resolution,
    any remainder shows the blurred fill), a gentle enlargement for 'blur'."""
    (cw, ch), (bw, bh) = canvas_size, base_size
    contain = min(cw/bw, ch/bh)
    cover = max(cw/bw, ch/bh) / contain
    if framing == 'cover': return round(min(cover, 2.4), 3)
    if framing == 'blur': return round(min(cover, 1.25), 3)
    return 1


def verify_output(path, width, height, total):
    try:
        probe = json.loads(subprocess.run([_tool('ffprobe'), '-v', 'error', '-show_entries',
            'stream=codec_type,width,height:format=duration', '-of', 'json', str(path)],
            capture_output=True, text=True, check=True, timeout=30).stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise HTTPException(502, 'OpenChatCut produced an unreadable MP4; no result was saved.') from None
    kinds = {s['codec_type'] for s in probe.get('streams', [])}
    video = next((s for s in probe['streams'] if s['codec_type'] == 'video'), {})
    duration = float(probe.get('format', {}).get('duration', 0))
    if 'video' not in kinds or 'audio' not in kinds or (video.get('width'), video.get('height')) != (width, height) or abs(duration-total) > .35:
        LOG.warning('openchatcut render verification failed kinds=%s size=%sx%s duration=%.2f expected=%.2f',
                    sorted(kinds), video.get('width'), video.get('height'), duration, total)
        raise HTTPException(502, 'OpenChatCut render did not match the planned edit (streams/size/duration); no result was saved.')


def remove_letterbox(base, target):
    """Crop baked-in cinema bars so portrait framing uses picture, not black bars. Returns the path used."""
    try:
        probe = subprocess.run([_tool('ffmpeg'), '-nostdin', '-hide_banner', '-i', str(base), '-vf', 'fps=2,cropdetect=limit=24:round=2:reset=0',
                                '-an', '-f', 'null', '-'], capture_output=True, text=True, timeout=120).stderr
        crops = [tuple(map(int, m)) for m in re.findall(r'crop=(\d+):(\d+):(\d+):(\d+)', probe)]
        size = subprocess.run([_tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                               '-of', 'csv=p=0', str(base)], capture_output=True, text=True, timeout=30).stdout.strip().split(',')
        width, height = int(size[0]), int(size[1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return base
    if not crops: return base
    w, h, x, y = crops[-1]  # reset=0 accumulates the widest content box over the whole clip
    if h > height*.92 and w > width*.92: return base
    subprocess.run([_tool('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-i', str(base), '-vf', f'crop={w}:{h}:{x}:{y}',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-c:a', 'copy', str(target)], check=True, timeout=600)
    return target


def _size(path):
    try:
        out = subprocess.run([_tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                              '-of', 'csv=p=0', str(path)], capture_output=True, text=True, timeout=30).stdout.strip().split(',')
        return int(out[0]), int(out[1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def render(base, output, state, info, audio_store):
    engine = engine_path()
    with _render_lock, tempfile.TemporaryDirectory(prefix='cascade-occ-') as work:
        work = Path(work)
        (work/'media').mkdir(); (work/'library').mkdir()
        if state.fablecut.ratio == '9:16':
            base = remove_letterbox(base, work/'media'/'base-picture.mp4')
        if Path(base).parent != work/'media':  # imports are restricted to this folder
            shutil.copy2(base, work/'media'/'base.mp4'); base = work/'media'/'base.mp4'
        spec, total = build_spec(state, info, audio_store, base, work/'media', work/'out.mp4', _size(base))
        (work/'spec.json').write_text(json.dumps(spec))
        env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER')}
        env.update({'OCC_DIR': str(engine), 'OPENCHATCUT_DATA_DIR': str(work/'library'), 'CC_BROWSER_EXECUTABLE': _chrome(),
                    'OPENCHATCUT_FFMPEG': _tool('ffmpeg'), 'OPENCHATCUT_FFPROBE': _tool('ffprobe'),
                    'AGENT_IMPORT_ROOTS': str(work/'media'), 'NODE_NO_WARNINGS': '1'})
        try:
            subprocess.run([str(engine/'node_modules/.bin/tsx'), str(DRIVER), str(work/'spec.json'), str(work/'result.json')],
                           cwd=engine, env=env, capture_output=True, timeout=900)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, 'OpenChatCut rendering timed out; your edit is saved and you can retry the preview.') from None
        try:
            result = json.loads((work/'result.json').read_text())
        except (OSError, ValueError):
            result = {'committed': False, 'rendered': False, 'steps': []}
        if not (result.get('committed') and result.get('rendered')):
            failed = next((s for s in result.get('steps', []) if not s.get('ok')), {})
            LOG.warning('openchatcut execution failed step=%s detail=%s', failed.get('tool'), str(failed.get('note', ''))[:400])
            raise HTTPException(502, f"OpenChatCut could not apply the edit ({failed.get('tool', 'driver')}). Your saved edit is unchanged.")
        verify_output(work/'out.mp4', spec['width'], spec['height'], total)
        shutil.move(str(work/'out.mp4'), output)
        return {'steps': len(result['steps']), 'duration': total}
