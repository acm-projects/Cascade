"""Free edit inspiration from public YouTube: key-less yt-dlp search, then for the two shortest
popular references a 240p download, measured cut pacing and a few sampled frames.

No API key, no paid service. Results are cached per query for a week. Failures return what was
found (possibly nothing); the Director then plans from the clip alone and says so.
"""
import base64
import hashlib
import json
import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path

LOG = logging.getLogger(__name__)
CACHE = Path.home()/'.cache'/'cascade'/'inspiration'
WEEK = 7*24*3600


def _search(query, limit=8):
    import yt_dlp
    options = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'extract_flat': True, 'socket_timeout': 15}
    with yt_dlp.YoutubeDL(options) as ydl:
        listing = ydl.extract_info(f'ytsearch{limit}:{query}', download=False) or {}
    results = []
    for entry in listing.get('entries') or []:
        if not entry or not re.fullmatch(r'[A-Za-z0-9_-]{11}', entry.get('id') or ''):
            continue
        results.append({'id': entry['id'], 'title': (entry.get('title') or '')[:140], 'channel': (entry.get('channel') or entry.get('uploader') or '')[:80],
                        'views': entry.get('view_count') or 0, 'duration': entry.get('duration') or 0,
                        'url': 'https://www.youtube.com/watch?v='+entry['id']})
    return results


def _measure(video_id, work):
    """Download one short reference at low resolution; return cuts/minute and 6 frames."""
    import yt_dlp
    from backend.trends.diagnostics import ydl_options
    target = work/f'{video_id}.mp4'
    options = {**ydl_options(), 'no_warnings': True, 'format': 'bestvideo[height<=360][ext=mp4]/best[height<=360]/best',
               'outtmpl': str(work/f'{video_id}.%(ext)s'), 'socket_timeout': 20, 'noplaylist': True, 'max_filesize': 60*1024*1024}
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download(['https://www.youtube.com/watch?v='+video_id])
    if not target.is_file():
        found = list(work.glob(video_id+'.*'))
        if not found: return None
        target = found[0]
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(target)],
                           capture_output=True, text=True, timeout=30).stdout.strip()
    duration = float(probe or 0)
    if duration <= 0: return None
    scan = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', str(target), '-an', '-vf', "scale=160:-2,select='gt(scene,0.3)',showinfo",
                           '-f', 'null', '-'], capture_output=True, text=True, timeout=120).stderr
    cuts = len(re.findall(r'pts_time:', scan))
    frames = []
    for i in range(6):
        jpg = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{duration*(i+.5)/6:.2f}', '-i', str(target), '-frames:v', '1',
                              '-vf', 'scale=256:-2', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'], capture_output=True, timeout=30).stdout
        if jpg: frames.append(base64.b64encode(jpg).decode())
    return {'cuts_per_minute': round(cuts/duration*60, 1), 'measured_seconds': round(duration, 1), 'frames': frames}


def inspire(query):
    """{'query', 'references': [...], 'pacing': cuts/min or None, 'frames': [b64 jpeg], 'note'}."""
    query = re.sub(r'\s+', ' ', query or '').strip()[:80]
    if not query:
        return {'query': '', 'references': [], 'pacing': None, 'frames': [], 'note': 'No search context.'}
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE/(hashlib.sha256(query.lower().encode()).hexdigest()[:20]+'.json')
    try:
        data = json.loads(cached.read_text())
        if time.time()-data['saved'] < WEEK: return data['result']
    except (OSError, ValueError, KeyError):
        pass
    try:
        references = _search(query)
    except Exception as exc:  # yt-dlp raises many types; inspiration is optional
        LOG.warning('director inspiration search failed: %s', str(exc)[:200])
        return {'query': query, 'references': [], 'pacing': None, 'frames': [], 'note': 'YouTube search was unavailable.'}
    popular = sorted(references, key=lambda r: r['views'], reverse=True)
    short = [r for r in popular if 0 < r['duration'] <= 240][:2]
    measured, frames = [], []
    with tempfile.TemporaryDirectory(prefix='cascade-inspo-') as work:
        for ref in short:
            try:
                result = _measure(ref['id'], Path(work))
            except Exception as exc:
                LOG.info('director inspiration measure skipped %s: %s', ref['id'], str(exc)[:120])
                continue
            if result:
                ref['cuts_per_minute'] = result['cuts_per_minute']
                measured.append(result['cuts_per_minute']); frames += result['frames'][:6]
    result = {'query': query, 'references': popular[:6], 'pacing': round(sum(measured)/len(measured), 1) if measured else None,
              'frames': frames[:12], 'note': f'{len(references)} public results; pacing measured on {len(measured)} reference(s).'}
    try:
        cached.write_text(json.dumps({'saved': time.time(), 'result': result}))
    except OSError:
        pass
    return result


def contact_sheet(frames_b64, columns=4):
    """One labeled grid image of reference frames (keeps the request to a single image)."""
    if not frames_b64: return None
    import io
    from PIL import Image
    images = [Image.open(io.BytesIO(base64.b64decode(f))).convert('RGB') for f in frames_b64]
    w, h = 256, max(i.height*256//max(1, i.width) for i in images)
    sheet = Image.new('RGB', (w*columns, h*((len(images)+columns-1)//columns)), (20, 20, 20))
    for n, image in enumerate(images):
        sheet.paste(image.resize((w, image.height*w//max(1, image.width))), ((n % columns)*w, (n//columns)*h))
    out = io.BytesIO(); sheet.save(out, format='JPEG', quality=75)
    return base64.b64encode(out.getvalue()).decode()
