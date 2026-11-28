"""Reference edits: "make it exactly like this reference video, with our footage".

A request that lays out a shot list (an edit time, then a source recording and second, per row, as a table or one per
line) becomes a VisualPlan that keeps the reference's exact cut times. Cascade:
  1. reads the rows (rows())
  2. finds each recording ("DJI 0024", "IMG_6229", "the 15 minute 40 second video") among the footage (Footage)
  3. gathers just those moments into one clip, in order, framed to the edit's shape (gather())
  4. plans one shot per row, its length the gap to the next row; the row's words pick its effect (plan())
visual.make renders it like any other edit. No AI model is needed once the shot list exists.
"""
import re
import subprocess
from pathlib import Path

from .visual import VisualPlan, VisualShot

TIME = r'(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?'
# "| 0:02.57 | IMG_6228 · 0:07.4 | Sun through the branches |"   or   "0:02.57 DJI 0024 0:23.5 shoes on the rock"
ROW = re.compile(r'^\s*\|?\s*\**' + TIME + r'(?:\s*[-–]\s*' + TIME + r')?\**\s*\|?\s*\**\s*'
                 r'(DJI\s*\d{4}|IMG[_ ]?\d{4}|first|second|[\w.-]+\.(?:mp4|mov))\s*[·:|-]?\s*' + TIME + r'(?:\s*[-–]\s*' + TIME + r')?\**\s*\|?\s*(.*)$',
                 re.I | re.M)
EFFECTS = [(r'cut[- ]?out|cutin|pops? up', 'cutin'), (r'whip', 'whip'), (r'zoom blur|zoom in fast|punch', 'zoom'), (r'dissolve|fade', 'fade'), (r'glitch', 'glitch'),
           (r'flash of light|white flash', 'flash'), (r'shake', 'shake')]


def _seconds(m, s, f):
    return int(m)*60+int(s)+(int(f)/10**len(f) if f else 0.)


def rows(request):
    """[{'at': edit seconds, 'file': 'DJI 0024', 'src': source seconds, 'note': words}] in edit order."""
    out = []
    for m in ROW.finditer(request or ''):
        g = m.groups()
        out.append({'at': _seconds(*g[0:3]), 'file': re.sub(r'\s+', ' ', g[6]).strip(), 'src': _seconds(*g[7:10]),
                    'note': g[13].strip(' |*') if g[13] else ''})
    return sorted(out, key=lambda r: r['at'])


class Footage:
    """The recordings a shot list can name: by their camera number ("DJI 0024" -> ..._0024_D_...), their file name
    ("IMG_6229"), each with its length."""
    def __init__(self, paths):
        self.paths = [Path(p) for p in paths]

    def find(self, name):
        key = name.upper().replace(' ', '')
        number = re.search(r'(\d{4})', key)
        for p in self.paths:
            stem = p.stem.upper()
            if key.startswith('DJI') and number and f'_{number.group(1)}_' in stem: return p
            if key.startswith('IMG') and number and stem.replace('_', '').endswith('IMG'+number.group(1)): return p
            if stem == Path(name).stem.upper(): return p
        if key in ('FIRST', 'SECOND') and stem == key: return p
        raise ValueError(f'No recording called {name} in the footage.')


def _probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height:stream_side_data=rotation',
                          '-of', 'default=nw=1', str(path)], capture_output=True, text=True).stdout
    w = int(re.search(r'width=(\d+)', out).group(1)); h = int(re.search(r'height=(\d+)', out).group(1))
    rot = re.search(r'rotation=(-?\d+)', out)
    if rot and abs(int(rot.group(1))) % 180 == 90: w, h = h, w
    return w, h


def gather(moments, footage, out, width=1920, height=1080, ffmpeg='ffmpeg'):
    """Cut each (file, from, seconds) moment out of its recording and join them, in order, into one clip of the edit's
    shape (a vertical phone shot is cropped to fill the frame). Returns where each moment starts in the joined clip.
    Each moment is cut on its own (a few at once: 4K phone and drone footage is heavy), then the pieces are joined."""
    import shutil
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    folder = Path(tempfile.mkdtemp(prefix='reference-'))
    def cut(k):
        name, a, seconds = moments[k]
        piece = folder/f'{k:03d}.mp4'
        vf = (f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30,format=yuv420p')
        run = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-ss', f'{max(0., a):.3f}', '-i', str(footage.find(name)),
                              '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', f'{seconds:.3f}', '-vf', vf,
                              '-filter_complex', '[0:a:0]aresample=48000,aformat=channel_layouts=stereo[a0];[a0][1:a]amix=inputs=2:duration=first:normalize=0[a]',
                              '-map', '0:v:0', '-map', '[a]', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-r', '30',
                              '-c:a', 'aac', '-ar', '48000', '-b:a', '192k', str(piece)], capture_output=True, text=True)
        if run.returncode: raise RuntimeError(f'Could not cut {name} at {a:.2f}s: {run.stderr[-400:]}')
        return piece
    try:
        with ThreadPoolExecutor(4) as pool:
            pieces = list(pool.map(cut, range(len(moments))))
        starts, at = [], 0.
        for piece in pieces:
            starts.append(round(at, 3))
            at += float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(piece)],
                                       capture_output=True, text=True).stdout.strip())
        (folder/'list.txt').write_text(''.join(f"file '{p}'\n" for p in pieces))
        run = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(folder/'list.txt'),
                              '-c', 'copy', '-movflags', '+faststart', str(out)], capture_output=True, text=True)
        if run.returncode: raise RuntimeError(f'Could not join the moments: {run.stderr[-400:]}')
        return starts
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _effect(note):
    for pattern, effect in EFFECTS:
        if re.search(pattern, note, re.I): return effect
    return None


def build(request, footage, out, end, reference_start=0., pad=.25, ffmpeg='ffmpeg', **plan_fields):
    """The reference edit for a shot-list request: gathers the footage into `out` and returns the VisualPlan.
    `end`: the reference second where the edit ends (it loops back to its first shot there). `reference_start`: the
    reference second the edit's 0 stands for (a screen recording starts a few frames early).
    A row's note can say: 'whip' / 'zoom blur' (its transition), 'silhouette' (a cut-out splash), 'over DJI 0024 0:13.5'
    or 'in front of IMG_6230 0:44' (the people cut out over that moment), 'voice through 0.4' (its sound keeps going)."""
    timed = rows(request)
    if len(timed) < 2: raise ValueError('The request needs a shot list: an edit time, then a recording and its second, per row.')
    lengths = [b['at']-a['at'] for a, b in zip(timed, timed[1:])]+[end-timed[-1]['at']]
    moments, extra, panels = [], [], {}
    for r, length in zip(timed, lengths):
        through = re.search(r'voice through\s*([\d.]+)', r['note'], re.I)
        r['through'] = float(through.group(1)) if through else 0.
        moments.append((r['file'], r['src'], length+r['through']+pad))
        back = re.search(r'(?:over|in front of)\s+(DJI\s*\d{4}|IMG[_ ]?\d{4})\s*[·:]?\s*' + TIME, r['note'], re.I)
        if back: extra.append((len(moments)-1, (back.group(1), _seconds(*back.group(2, 3, 4)), length+pad)))
        if re.search(r'\bcollage\b', r['note'], re.I):   # "collage: DJI 0018 11:24.26, first 2:18.20, ...": strips beside this shot
            for name, *when in re.findall(r'(DJI\s*\d{4}|IMG[_ ]?\d{4}|first|second)\s*[·:]?\s*' + TIME, r['note'].split(':', 1)[-1], re.I):
                panels.setdefault(len(moments)-1, []).append(len(extra))   # (an index into `extra`)
                extra.append((None, (name, _seconds(*when), length+pad)))
    starts = gather(moments+[m for _, m in extra], footage, out, ffmpeg=ffmpeg)
    behind = {k: starts[len(moments)+i] for i, (k, _) in enumerate(extra) if k is not None}
    shots = []
    for k, (r, length) in enumerate(zip(timed, lengths)):
        a = starts[k]
        shot = VisualShot(start=a, end=round(a+length, 3), effect=_effect(r['note']) if k else None,
                          silhouette=bool(re.search(r'silhouette', r['note'], re.I)),
                          backdrop=behind.get(k, -1.), voice_through=r['through'],
                          voice=bool(r['through']) or bool(re.search(r'\bvoice\b|chant|saying', r['note'], re.I)))
        if re.search(r'push in|slow zoom', r['note'], re.I): shot.zoom = 'push'
        for word, fx in (('boomerang', 'boomerang'), ('forward and back', 'boomerang'), ('sticker', 'sticker'), ('red cut', 'redcut'), ('red paper', 'redcut'), ('scribble', 'scribble'), ('polaroid', 'polaroid')):
            if re.search(word, r['note'], re.I): shot.fx = fx
        if k and re.search(r'\brip\b|torn', r['note'], re.I): shot.rip_in = True
        if k in panels:
            at = [starts[len(moments)+i] for i in panels[k]]
            shot.panels = [round(x, 3) for x in at]
            shot.panel_ends = [round(x+length+pad-.02, 3) for x in [a]+at]
            z = re.search(r'zoom\s+([\d. ]+)', r['note'], re.I)
            if z: shot.panel_zoom = [float(v) for v in z.group(1).split()][:len(shot.panels)+1]
        spot = re.search(r'focus at ([\d.]+)\s+([\d.]+)', r['note'], re.I)
        who = None if spot else re.search(r'focus(?:es|ed)? on (?:the )?(.+?)(?: only)?(?:[,.;]|$)', r['note'], re.I)
        if spot:   # "focus at 0.40 0.18": a close-up that brings that point (across, down) to the middle
            shot.focus_x, shot.focus_y, shot.zoom = float(spot.group(1)), float(spot.group(2)), 'close'
        whos = re.search(r'who:\s*(.+?)(?:[,.;]\s*\w+\s*$|$)', r['note'], re.I)
        if k in panels and whos: shot.panel_who = [w.strip().lower() for w in whos.group(1).split('/')][:len(shot.panels)+1]
        if who:   # a close-up on the person named, found with the visual search model
            from .visual import person_at
            found = person_at(out, a+min(.15, length/2), ffmpeg, who.group(1).strip().lower())
            if found:
                shot.focus_x, shot.focus_y = round(float(found[0]), 3), round(float(min(.7, max(.2, found[1]-found[2]*.25))), 3)
                shot.zoom = 'close' if found[2] < .45 else 'punch'
        shots.append(shot)
    return VisualPlan(shots=shots, exact=True, **plan_fields)


def cuts(reference, threshold=.18, ffmpeg='ffmpeg'):
    """The reference video's cut times (seconds), found from its picture changes."""
    run = subprocess.run([ffmpeg, '-nostdin', '-i', str(reference), '-filter:v', f"select='gt(scene,{threshold})',showinfo", '-an', '-f', 'null', '-'],
                         capture_output=True, text=True)
    return [round(float(x), 2) for x in re.findall(r'pts_time:([\d.]+)', run.stderr)]


VIDEO_TYPES = {'.mp4', '.mov', '.m4v', '.mkv', '.webm'}


def footage_files():
    """Where the recordings a shot list names are looked for: CASCADE_FOOTAGE_DIR, the editing folder's Raw Footage,
    and the Desktop's Cascade Source Videos."""
    import os
    from ..tools import folder
    places = [os.getenv('CASCADE_FOOTAGE_DIR', ''), folder()/'Raw Footage', Path.home()/'Desktop'/'Cascade Source Videos']
    return [p for place in places if place and Path(place).is_dir() for p in sorted(Path(place).iterdir()) if p.suffix.lower() in VIDEO_TYPES]


def ending(request, timed):
    """Where the edit ends: "loops back ... at 0:15.12" / "ends at 0:15", else just after the last row."""
    m = re.search(r'(?:loops?|ends?)\b[^|\n]{0,40}?' + TIME, request or '', re.I)
    last = timed[-1]['at']
    return _seconds(*m.groups()) if m and _seconds(*m.groups()) > last else last+.5


def line_of(request):
    """The on-screen line a request quotes: 'Opening line: "I wish that I could STAY here..."'."""
    m = re.search(r'(?:opening line|text|line)\s*[:=]\s*["\u201c]([^"\u201d]{2,80})["\u201d]', request or '', re.I)
    return m.group(1).strip() if m else ''


def song_for(request):
    """The Music Library song a request names ("our song Alive Again", "the reference's sound"), or ''."""
    from . import music
    songs = music.library()
    text = (request or '').lower()
    for song in songs:
        title = re.sub(r'\s*\(.*?\)', '', song['title']).lower().strip()
        if title and title in text: return song['id']
    if re.search(r"reference'?s? (?:sound|song|audio|music)", text):
        return next((s['id'] for s in songs if 'reference' in s['title'].lower()), '')
    return ''


def plan_request(request, out, ffmpeg='ffmpeg', footage=None):
    """A shot-list request, start to finish: the gathered footage written to `out` and the VisualPlan to render over it."""
    timed = rows(request)
    opener = timed[1]['at']-timed[0]['at']
    said = line_of(request)
    return build(request, footage or Footage(footage_files()), out, end=ending(request, timed), ffmpeg=ffmpeg,
                 song=song_for(request), sound='both', grade='cinema', transition_sounds=False,
                 settings={'ratio': '16:9', 'stamp': False, 'music': True},
                 line=said, line_from=round(opener*.37, 2) if said else 0, line_to=round(opener*.75, 2) if said else 0,
                 line_until=round(opener*.95, 2) if said else 0, reply='Your footage, cut exactly like the reference shot list.',
                 **{**sound_of(request), **paper_of(request, opener), **words_of(request)})


def sound_of(request):
    """The mix a request asks for, with or without the paper: 'music from 0, music under voice -2.5, clip sound 0'."""
    text = request or ''
    get = lambda pattern: re.search(pattern + r'\s*-?([\d.]+)', text, re.I)
    out = {}
    if get(r'music from'): out['music_from'] = float(get(r'music from').group(1))
    if get(r'music under voices?'): out['music_under_voice_db'] = -float(get(r'music under voices?').group(1))
    if get(r'clip sound'): out['bed'] = float(get(r'clip sound').group(1))
    if re.search(r'fade(?:s)? (?:out|to black) at the end', text, re.I): out['fade_out'] = True
    patches = re.findall(r'hide the word at ([\d.]+) with the song at ([\d.]+) for ([\d.]+)', text, re.I)
    if patches: out['music_patches'] = [tuple(float(v) for v in p) for p in patches]
    return out


def words_of(request):
    """Big white words a request times: 'Words: ONE at 0.04, TWO at 0.76, THREE at 1.24 until 1.64'."""
    m = re.search(r'words\s*:\s*(.+)', request or '', re.I)
    if not m: return {}
    pairs = re.findall(r'([A-Z][A-Z!]+)\s+at\s+([\d.]+)', m.group(1))
    until = re.search(r'until\s+([\d.]+)', m.group(1))
    return {'big_words': [(w, float(a)) for w, a in pairs], **({'big_words_until': float(until.group(1))} if until else {})}


def paper_of(request, opener):
    """The inspo's paper, when the request asks for it: 'Paper: "pov" / "hike with cascade" at 1.6, tear 0.6, wrap 0.9,
    music from 2.25'."""
    m = re.search(r'paper\s*:\s*["\u201c]([^"\u201d]*)["\u201d]\s*/\s*["\u201c]([^"\u201d]*)["\u201d](.*)', request or '', re.I)
    if not m: return {}
    rest = m.group(3)
    num = lambda word, default: float(re.search(word + r'\s*([\d.]+)', rest, re.I).group(1)) if re.search(word + r'\s*([\d.]+)', rest, re.I) else default
    return {'paper_until': opener, 'paper_top': m.group(1), 'paper_bottom': m.group(2), 'paper_word_at': num(r'\bat', opener*.7),
            'tear': num(r'tear', .6), 'paper_end': num(r'wrap', 0.),
            'paper_typed': bool(re.search(r'\btyped?\b|typing', rest, re.I)), 'vintage': bool(re.search(r'vintage', rest, re.I))}
