"""Cut every shot to the vertical plate, frame-exact so cuts stay on the grid. Parts are cached, so a
revision that keeps a shot does not cut it again."""
import re
import bisect
import hashlib
import json
import logging
import subprocess
from pathlib import Path

from . import tools
from .prep import probe

LOG = logging.getLogger(__name__)
GRADE = 'eq=contrast=1.10:saturation=1.05:brightness=-0.02,unsharp=5:5:0.8'
RUN = dict(capture_output=True, text=True, timeout=600)


def _crop(width, height, cx, zoom):
    ch = int(height/zoom)//2*2
    cw = int(ch*9/16)//2*2
    if cw > width:
        cw = width//2*2; ch = int(cw*16/9)//2*2
    x = int(min(max(0, width*cx-cw/2), width-cw))
    y = int((height-ch)*.35)
    return f'crop={cw}:{ch}:{x}:{y},scale=1080:1920:flags=lanczos,{GRADE}'


def _within_shot(src, seconds, cuts, duration):
    """(start, slow factor) so the part never runs across a cut into the wrong shot."""
    src = min(src, max(0, duration-.1))
    i = bisect.bisect_right(cuts, src)
    previous = cuts[i-1] if i else 0
    following = cuts[i] if i < len(cuts) else duration
    room = following-src-.03
    if room >= seconds: return src, 1
    earlier = max(previous+.05, following-seconds-.03)
    room = following-earlier-.03
    if room >= seconds: return earlier, 1
    return earlier, min(2.5, seconds/max(room, .2))


def cut(events, source, prep, parts_dir, plate, stock=None, fallback_notes=None):
    parts_dir = Path(parts_dir); parts_dir.mkdir(parents=True, exist_ok=True)
    listing, used = [], set()
    for event in events:
        frames = max(1, round((event.end-event.start)*30))
        base = ['-r', '30', '-frames:v', str(frames), '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '15', '-pix_fmt', 'yuv420p']
        inputs = None
        kind = event.kind
        if kind == 'stock':
            inputs = _stock(event, stock, frames, used)
            if inputs is None:
                if fallback_notes is not None: fallback_notes.append(f'no stock footage for "{event.query}", stayed on the clip')
                kind = 'sync'
        key = hashlib.sha256(json.dumps([kind, round(event.src, 3), event.cx, event.zoom, frames, event.query, inputs, prep['stamp'], 3]).encode()).hexdigest()[:24]
        out = parts_dir/f'{key}.mp4'
        if not out.is_file():
            temp = out.with_suffix('.tmp.mp4')
            if kind in ('ink', 'dot'):
                command = [tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0x0C0D13:s=1080x1920:r=30']
            elif kind == 'band':
                command = [tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-ss', f'{event.src:.3f}', '-i', str(source), '-filter_complex',
                           f'color=c=0x0C0D13:s=1080x1920:r=30[bg];[0:v]scale=1080:-2:flags=lanczos,{GRADE}[v];[bg][v]overlay=0:(H-h)/2-110:shortest=1']
            elif inputs:
                command = [tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-ss', '0.5', '-i', inputs[0], '-vf', f'setpts=PTS*{inputs[3]},'+_crop(inputs[1], inputs[2], event.cx, event.zoom)]
            else:
                start, slow = (event.src, 1) if kind == 'sync' else _within_shot(event.src, frames/30, prep['cuts'], prep['duration'])
                retime = f'setpts=PTS*{slow:.3f},' if slow > 1 else ''
                command = [tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-ss', f'{start:.3f}', '-i', str(source), '-vf', retime+_crop(prep['width'], prep['height'], event.cx, event.zoom)]
            run = subprocess.run(command+base+[str(temp)], **RUN)
            if run.returncode and inputs:  # a stock file ffmpeg cannot read must not sink the whole edit
                if fallback_notes is not None: fallback_notes.append(f'could not use stock footage for "{event.query}", stayed on the clip')
                command = [tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-ss', f'{event.src:.3f}', '-i', str(source), '-vf', _crop(prep['width'], prep['height'], event.cx, event.zoom)]
                run = subprocess.run(command+base+[str(temp)], **RUN)
            if run.returncode:
                LOG.warning('shot failed: %s', run.stderr[-400:])
                raise ValueError(f'I could not cut the shot at {event.start:.1f} s of the edit.')
            temp.replace(out)
        listing.append(out)
    concat = parts_dir/f'{Path(plate).stem}.txt'
    concat.write_text(''.join(f"file '{p.name}'\n" for p in listing))
    run = subprocess.run([tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', concat.name, '-c', 'copy', str(Path(plate).resolve())], cwd=parts_dir, **RUN)
    if run.returncode:
        LOG.warning('join failed: %s', run.stderr[-400:])
        raise ValueError('I could not join the shots together.')


# Words that say how a shot looks, not what is in it: they never make a stock clip relevant on their own
LOOK_WORDS = {'close', 'up', 'closeup', 'shot', 'aerial', 'view', 'slow', 'motion', 'footage', 'video', 'cinematic', 'b', 'roll',
              'stock', 'wide', 'macro', 'drone', 'the', 'a', 'an', 'of', 'in', 'on', 'at', 'and', 'with', 'from', 'into', 'its',
              'walking', 'running', 'moving', 'looking', 'face', 'powerful', 'beautiful', 'dark', 'night', 'day'}


def _stem(word):
    if word.endswith('ies'): return word[:-3]
    if word.endswith('ing') and len(word) > 5: word = word[:-3]  # "roaring" matches a "lion-roars" clip
    return word[:-1] if word.endswith('s') and len(word) > 3 else word


def ranked(query, results):
    """Stock results whose own page description names what the query is about, best first. whose own page description names what the query is about, or None.

    Pexels returns loose matches (a search for "jaguar" can return a woman's face), and the first result is
    often off. Each result's page address describes it ("/video/a-jaguar-resting-on-a-branch-123/"), so a
    clip is used only when that description contains the query's subject words."""
    subject = {_stem(w) for w in re.findall(r'[a-z]+', query.lower()) if w not in LOOK_WORDS and len(w) > 2}
    if not subject: return None
    def score(asset):
        slug = re.sub(r'[^a-z]+', ' ', (asset.get('source_url') or '').lower().rsplit('/video/', 1)[-1])
        words = {_stem(w) for w in slug.split()}
        return len(subject & words)
    needed = 1 if len(subject) <= 2 else 2  # "jaguar" needs jaguar; "caiman river amazon" needs two of them
    scored = sorted(((score(a), i, a) for i, a in enumerate(results)), key=lambda x: (-x[0], x[1]))
    return [a for n, _, a in scored if n >= needed]


def relevant(query, results):
    best = ranked(query, results)
    return best[0] if best else None


def _stock(event, store, frames, used):
    """(path, width, height, slow) of free stock footage for this shot, or None."""
    if store is None: return None
    try:
        path = info = None
        # Vertical clips first (they fill the frame natively), then 4K landscape ones (sharp after the vertical crop)
        for orientation in ('portrait', 'landscape'):
            results = [a for a in store.search(event.query, orientation=orientation, hd=True).get('results', []) if a['id'] not in used]
            for pick in ranked(event.query, results)[:3]:
                try:
                    path = store.media(pick['id']); info = probe(path); used.add(pick['id']); break
                except Exception:
                    continue  # too large or too slow to download: try the next good match
            if path: break
        if not path:
            # the exact action is not in stock ("jaguar jaws biting"): show the subject itself, close and sharp
            subject = next((w for w in re.findall(r'[a-z]+', event.query.lower()) if w not in LOOK_WORDS and len(w) > 2), None)
            simpler = f'{subject} close up' if subject else ''
            if simpler and simpler != event.query.lower().strip():
                for orientation in ('portrait', 'landscape'):
                    results = [a for a in store.search(simpler, orientation=orientation, hd=True).get('results', []) if a['id'] not in used]
                    for pick in ranked(simpler, results)[:3]:
                        try:
                            path = store.media(pick['id']); info = probe(path); used.add(pick['id']); break
                        except Exception:
                            continue
                    if path: break
        if not path: return None  # nothing that really shows it: stay on the speaker rather than show something random
    except Exception:  # no key, no network, quota: the edit carries on without this shot
        return None
    room = max(.2, info['duration']-.6)
    return [str(path), info['width'], info['height'], round(max(1, frames/30/room), 3)]


def closing(source, src, cx, prep, out):
    side = min(prep['width'], prep['height'])
    x = int(min(max(0, prep['width']*cx-side/2), prep['width']-side))
    y = (prep['height']-side)//2
    run = subprocess.run([tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-ss', f'{src:.3f}', '-t', '2', '-i', str(source), '-vf', f'crop={side}:{side}:{x}:{y},scale=1000:1000,{GRADE}',
                          '-r', '30', '-an', '-c:v', 'libx264', '-crf', '15', '-pix_fmt', 'yuv420p', str(out)], **RUN)
    if run.returncode: raise ValueError('Could not cut the closing shot.')
