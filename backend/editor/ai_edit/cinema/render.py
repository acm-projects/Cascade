"""The picture: every shot decoded and graded by FFmpeg, then composed frame by frame in NumPy:
captions that build as they are spoken and never vanish mid-thought, giant words behind the speaker,
full-screen b-roll that arrives on the word, the quiet payoff, the closing message and the stamp.

Frames keep the clip's own shape ("original", the default) unless the edit asks for a reel (9:16)."""
import logging
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import look, settings, accents

LOG = logging.getLogger(__name__)
FPS = look.FPS
OPENER = 1.25          # seconds of opener before the first word plays
VOICE_AT = 1.05        # where the first word lands when there is an opener
PUNCH = (1.0, 1.12)    # zoom steps that hide a jump cut


def size_for(source_w, source_h, ratio='original', lines=1080):
    """Output frame size: the clip's own shape, or a reel. `lines` is the short side (1080; tests use less)."""
    w, h = _size_for(source_w, source_h, ratio)
    return int(round(w*lines/1080/2))*2, int(round(h*lines/1080/2))*2


def _size_for(source_w, source_h, ratio):
    if ratio in ('9:16', 'reel'): return 1080, 1920
    if ratio == '1:1': return 1080, 1080
    if ratio == '4:5': return 1080, 1350
    if ratio == '16:9': return 1920, 1080
    if ratio == '4:3': return 1440, 1080
    aspect = source_w/source_h
    if abs(aspect-16/9) < .09: return 1920, 1080
    if aspect >= 1: return int(round(1080*aspect/2))*2, 1080
    return 1080, int(round(1080/aspect/2))*2


@dataclass
class Shot:
    t0: float
    t1: float
    kind: str                 # aroll | broll | still
    path: str
    src: float                # source second at t0
    rate: float = 1.0         # source seconds per edit second
    cx: float = .5
    zoom0: float = 1.
    zoom1: float = 1.03
    grade: str = 'cinema'
    look: str = 'full'        # full | mono
    face: tuple | None = None  # (x, y) of the face in output pixels
    tone: str = 'calm'
    center: bool = False       # zoom brings `face` to the middle of the frame (a close-up of people filmed far away)
    ease_in: bool = False      # the zoom holds, then accelerates (a dive: see the whole subject, then plunge in)
    carry: bool = False        # plays the previous shot's sound carrying on (see audio_src)
    audio_src: float | None = None   # source second its sound starts at, when it is not its own
    audio_until: float | None = None  # and where that carried sound stops
    backdrop: tuple | None = None     # (path, source second): the people of this shot are cut out over that moment
    voice_through: float = 0.         # its own sound keeps playing this long after it ends


@dataclass
class Overlay:
    t0: float
    t1: float
    kind: str                 # behind | outline | glow | slam | quote | message | flash | title
    data: dict = field(default_factory=dict)


def probe(path):
    import json
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration', '-of', 'json', str(path)],
                         capture_output=True, text=True, timeout=60).stdout
    data = json.loads(out)
    v = next((s for s in data['streams'] if s['codec_type'] == 'video'), {})
    return {'duration': float(data['format']['duration']), 'width': v.get('width'), 'height': v.get('height')}


# ---------------------------------------------------------------- faces and framing

_FACE = None


def _detector(w, h):
    global _FACE
    import cv2
    model = Path(__file__).parent/'face_yunet.onnx'
    if _FACE is None:
        _FACE = cv2.FaceDetectorYN.create(str(model), '', (w, h), .6, .3, 20)
    _FACE.setInputSize((w, h))
    return _FACE


def grab(path, at, width=640, ffmpeg='ffmpeg'):
    info = probe(path)
    h = int(round(info['height']*width/info['width']/2))*2
    raw = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-ss', f'{max(0, at):.3f}', '-i', str(path), '-frames:v', '1', '-vf', f'scale={width}:{h}',
                          '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], capture_output=True, timeout=60).stdout
    if len(raw) < width*h*3: return None
    return np.frombuffer(raw[:width*h*3], np.uint8).reshape(h, width, 3)


def find_faces(path, at, ffmpeg='ffmpeg'):
    """[(cx, cy, width)] of every face, as fractions of the source frame (biggest first)."""
    try:
        frame = grab(path, at, 640, ffmpeg)
        if frame is None: return []
        h, w = frame.shape[:2]
        found = _detector(w, h).detect(frame)[1]
        if found is None: return []
        return [(float((f[0]+f[2]/2)/w), float((f[1]+f[3]/2)/h), float(f[2]/w)) for f in sorted(found, key=lambda f: -f[2]*f[3])]
    except Exception:
        LOG.info('face search failed', exc_info=True)
        return []


def find_face(path, at, ffmpeg='ffmpeg'):
    """(cx, cy, width) of the biggest face as fractions of the source frame, or None."""
    try:
        frame = grab(path, at, 640, ffmpeg)
        if frame is None: return None
        h, w = frame.shape[:2]
        found = _detector(w, h).detect(frame)[1]
        if found is None or not len(found): return None
        best = max(found, key=lambda f: f[2]*f[3])
        x, y, fw, fh = best[:4]
        return (float((x+fw/2)/w), float((y+fh/2)/h), float(fw/w))
    except Exception:
        LOG.info('face search failed', exc_info=True)
        return None


def crop_box(sw, sh, cx, target):
    """The window (x, y, w, h) of aspect `target` inside a source frame, centred on cx."""
    if sw/sh > target:
        ch = sh//2*2; cw = int(ch*target)//2*2
    else:
        cw = sw//2*2; ch = int(cw/target)//2*2
    x = int(min(max(0, sw*cx-cw/2), sw-cw))
    y = int(max(0, (sh-ch)*.4))
    return x, y, cw, ch


def face_in_output(face, sw, sh):
    """Where a source face lands in the output frame, after the crop."""
    if not face: return None
    x, y, cw, ch = crop_box(sw, sh, face[0], look.W/look.H)
    return ((face[0]*sw-x)/cw*look.W, (face[1]*sh-y)/ch*look.H)


class Reader:
    """Frames of one shot, graded and framed to the output size."""
    def __init__(self, shot, ffmpeg='ffmpeg'):
        info = probe(shot.path)
        sw, sh = info['width'], info['height']
        length = (shot.t1-shot.t0)*shot.rate+.2
        grade = look.GRADES['mono' if shot.look == 'mono' else shot.grade]
        speed = f'setpts=PTS/{shot.rate:.4f},' if abs(shot.rate-1) > .01 else ''
        x, y, cw, ch = crop_box(sw, sh, shot.cx, look.W/look.H)
        self.size = (look.W, look.H)
        sharpen = 'unsharp=5:5:0.5,' if cw < look.W*.8 else ''
        vf = f"{speed}fps={FPS},crop={cw}:{ch}:{x}:{y},scale={look.W}:{look.H}:flags=lanczos,{sharpen}{grade}"
        cmd = [ffmpeg, '-nostdin', '-v', 'error', '-ss', f'{max(0, shot.src):.3f}', '-t', f'{length:.3f}', '-i', str(shot.path),
               '-vf', vf, '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.last = None

    def next(self):
        w, h = self.size
        raw = self.proc.stdout.read(w*h*3)
        if len(raw) == w*h*3:
            self.last = np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy()
        if self.last is None: self.last = np.zeros((h, w, 3), np.uint8)
        return self.last

    def close(self):
        try:
            self.proc.stdout.close(); self.proc.kill(); self.proc.wait(timeout=5)
        except Exception:
            pass


def _zoom(frame, z, cx=None, cy=None):
    if abs(z-1) < .002: return frame
    import cv2
    h, w = frame.shape[:2]
    cx = w/2 if cx is None else cx
    cy = h*.42 if cy is None else cy
    m = np.array([[z, 0, (1-z)*cx], [0, z, (1-z)*cy]], np.float32)
    return cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _ease(x):
    x = min(1, max(0, x))
    return 1-(1-x)**3


# ---------------------------------------------------------------- captions

class Captions:
    """The owner's reference (Entrepreneurs House): a block of heavy, tight words beside the speaker in
    the empty side of the frame, building word by word as it is spoken, one keyword set on a coloured
    chip. A block stays up until the next one replaces it, so the text never blinks on and off
    between words or pauses."""

    def __init__(self, words, edit, offset, keywords, placement):
        self.offset, self.placement = offset, placement
        u = look.unit()
        self.size = settings.get('captions.size_wide' if look.W > look.H else 'captions.size_tall', 80)*u
        line = edit.timeline     # (word, start, end) as played
        self.at = [a+offset for _, a, _ in line]
        self.items = []
        block = []
        def close():
            if block: self.items.append(list(block)); block.clear()
        for n, (i, a, b) in enumerate(line):
            block.append(n)
            text = words[i]['w']
            gap = (line[n+1][1]-b) if n+1 < len(line) else 9
            jump = n+1 < len(line) and not 0 < line[n+1][0]-i <= 12   # the story moves to another part of the clip: never share a block
            if text.rstrip().endswith(('.', '?', '!')) or len(block) >= settings.get('captions.max_words', 7) or (text.endswith(',') and len(block) >= 3) or gap > .7 or gap < -.01 or jump: close()
        close()
        self.sprites = {}
        f = look.TIGHT(self.size, 860)
        fk = look.TIGHT(self.size*1.12, 900)
        for n, (i, _, _) in enumerate(line):
            raw = words[i]['w'].strip()
            clean = raw.strip('.,!?;:"“”').replace('…', '') or raw
            sp = look.chip(clean, fk, look.TONES[keywords[i]]) if i in keywords else \
                look.text_sprite(clean, f, fill=look.WHITE, shadow=.75, tracking=-int(self.size*.025))
            self.sprites[n] = sp.baseline()
        self.spans = []
        for k, group in enumerate(self.items):
            t0 = self.at[group[0]]-.06
            nxt = self.items[k+1] if k+1 < len(self.items) else None
            end = line[group[-1]][2]+offset
            t1 = (self.at[nxt[0]]-.06) if nxt else end+.9
            if t1-end > 1.6: t1 = end+1.2   # a long silence after: let it go, rather than hang
            self.spans.append((t0, t1))
        self._layouts = {}

    def _layout(self, k, t):
        """Lines of (word, x, baseline y) for block k, laid out once in the side of the frame the speaker leaves free."""
        if k in self._layouts: return self._layouts[k]
        group = self.items[k]
        align, x0, y_mid, max_w = self.placement(self.spans[k][0])
        space = self.size*.24
        lines, line, width = [], [], 0
        for i in group:
            w = self.sprites[i].width
            if line and width+space+w > max_w:
                lines.append((line, width)); line, width = [], 0
            width = width+(space if line else 0)+w
            line.append(i)
        if line: lines.append((line, width))
        lead = self.size*1.02
        top = y_mid-(len(lines)-1)*lead/2
        out = []
        for n, (line, width) in enumerate(lines):
            x = x0 if align == 'left' else x0-width if align == 'right' else x0-width/2
            for i in line:
                out.append((i, x, top+n*lead))
                x += self.sprites[i].width+space
        self._layouts[k] = out
        return out

    def draw(self, frame, t, mute):
        if any(a <= t < b for a, b in mute): return
        for k, ((t0, t1), group) in enumerate(zip(self.spans, self.items)):
            if not t0 <= t < t1: continue
            leave = 1-_ease((t-(t1-.07))/.07) if t > t1-.07 else 1
            for i, x, y in self._layout(k, t):
                start = self.at[i]-.06
                if t < start: continue
                p = _ease((t-start)/.12)
                look.paste(frame, self.sprites[i], x, y+(1-p)*self.size*.22, alpha=p*leave)


# ---------------------------------------------------------------- the composer

_WATER = {}


_PAPER = {}


def paper(h, w, variant=0):
    """Crumpled paper (h x w x 3 uint8): faceted folds lit from the top left, creases, fine grain. A few variants, so the
    sheet can 'boil' (scramble) between them like stop-motion paper."""
    key = (h, w, variant)
    if key not in _PAPER:
        import cv2
        rng = np.random.default_rng(11+variant)
        sh, sw = max(8, h//4), max(8, w//4)
        pts = rng.random((90, 2))*(sh, sw)
        y, x = np.mgrid[0:sh, 0:sw].astype(np.float32)
        d = (y[..., None]-pts[:, 0])**2+(x[..., None]-pts[:, 1])**2
        order = np.argsort(d, axis=2)
        near, second = order[..., 0], order[..., 1]
        tilt = rng.normal(0, 1, (90, 2))
        shade = .95+.03*(tilt[near, 0]*-.7+tilt[near, 1]*-.7)                     # each facet tilted to the light
        gap = np.sqrt(np.take_along_axis(d, second[..., None], 2)[..., 0])-np.sqrt(np.take_along_axis(d, near[..., None], 2)[..., 0])
        crease = np.exp(-gap/1.2)                                                 # thin dark folds between facets
        shade = shade-.05*crease+.025*np.exp(-gap/3.5)*(tilt[near, 0] > 0)
        shade = cv2.GaussianBlur(shade.astype(np.float32), (0, 0), 1.1)
        shade = cv2.resize(shade, (w, h), interpolation=cv2.INTER_CUBIC)
        grain = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), .7)*.018
        yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]; xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
        vignette = 1-.06*(xx**2+yy**2)
        base = np.array((246, 242, 234), np.float32)
        _PAPER[key] = np.clip(base*((shade+grain)*vignette)[..., None], 0, 255).astype(np.uint8)
    return _PAPER[key]


def paper_layout(frame, t, data, k=1., words=1.):
    """The inspo's layout on crumpled paper: the footage small in the middle (k: 0 = full frame, 1 = laid out on the
    sheet), "pov" above it and the line below it, painted with moving water."""
    import cv2
    H, W = frame.shape[:2]
    sheet = paper(H, W, int(t*8) % 3 if data.get('boil', True) else 0).astype(np.float32)
    scale = 1-(1-data.get('scale', .5))*k
    fw, fh = int(W*scale)//2*2, int(H*scale)//2*2
    small = cv2.resize(frame, (fw, fh), interpolation=cv2.INTER_AREA).astype(np.float32)
    x0, y0 = (W-fw)//2, int((H-fh)/2+H*.02*k)
    out = sheet.copy() if k > 0 else frame.astype(np.float32)
    if k > 0:   # a soft shadow under the print, and the paper's folds showing faintly through it
        shadow = np.zeros((H, W), np.float32); shadow[y0+6:y0+fh+10, x0+4:x0+fw+8] = .35*k
        shadow = cv2.GaussianBlur(shadow, (0, 0), 9)[..., None]
        out = out*(1-shadow)
        fold = (sheet[y0:y0+fh, x0:x0+fw]/236.)*.25+.75
        out[y0:y0+fh, x0:x0+fw] = small*(fold*k+(1-k))
    if words > 0:
        for text, at, y, size in ((data.get('top', ''), data.get('top_at', -1), y0-H*.1, .15), (data.get('bottom', ''), data.get('bottom_at', -1), y0+fh+H*.105, .115)):
            if not text or t < at: continue
            f = look.TIGHT(int(H*size), 900)
            sp = look.text_sprite(text, f, fill=(255, 255, 255), shadow=.25, tracking=-int(f.size*.02))
            rgba = sp.rgba.copy(); rgba[..., :3] = water(rgba.shape[0], rgba.shape[1], t).astype(np.uint8)
            pop = 1+.12*max(0., 1-(t-at)/.18)
            img = out.astype(np.uint8)
            look.paste(img, look.Sprite(rgba, .5, .5), W/2, y, alpha=words*min(1., (t-at)/.08+.2), scale=pop)
            out = img.astype(np.float32)
    flash = data.get('flash_at', -1)
    if 0 <= t-flash < .14:   # the white flash as the word lands (the inspo's flash frame)
        a = 1-(t-flash)/.14
        out = out*(1-a)+255*a
    return np.clip(out, 0, 255).astype(np.uint8)


def tear(under, sheet, p, seed=3):
    """The paper tearing open from the middle (the second inspo): a ragged hole in `sheet` grows (p: 0..1) and shows
    `under` through it; the torn edge is a rim of white paper fibre with a shadow inside."""
    import cv2
    H, W = sheet.shape[:2]
    rng = np.random.default_rng(seed)
    n = 18
    angles = np.sort(rng.random(n))*2*np.pi
    jag = .72+.5*rng.random(n)
    r = (p**1.7)*np.hypot(W, H)*.62
    cx, cy = W*.5+W*.04*np.sin(p*3), H*.5
    def poly(scale):
        return np.stack([cx+np.cos(angles)*r*jag*scale, cy+np.sin(angles)*r*jag*scale*.86], 1).astype(np.int32)
    hole = np.zeros((H, W), np.uint8); cv2.fillPoly(hole, [poly(1.)], 255)
    rim = np.zeros((H, W), np.uint8); cv2.fillPoly(rim, [poly(1.12)], 255)
    shade = cv2.GaussianBlur(hole.astype(np.float32)/255, (0, 0), 14)
    out = sheet.astype(np.float32)
    rimmed = (rim > 0) & (hole == 0)
    out[rimmed] = out[rimmed]*.55+np.array((250, 248, 242), np.float32)*.45              # the white torn fibre
    flap = cv2.GaussianBlur(((rim > 0) & (hole == 0)).astype(np.float32), (0, 0), 6)
    out = out*(1-.25*flap[..., None]*(1-hole[..., None]/255))                              # curled edge shadow
    m = (hole/255.).astype(np.float32)[..., None]
    inside = under.astype(np.float32)*(1-.35*(1-shade[..., None])*m)                      # the edge's shadow inside the hole
    return np.clip(out*(1-m)+inside*m, 0, 255).astype(np.uint8)


def water(h, w, t):
    """A moving water texture (h x w x 3 float): deep to bright blue with drifting light caustics."""
    key = (h, w)
    if key not in _WATER:
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        _WATER[key] = (x/max(1, w), y/max(1, h))
    x, y = _WATER[key]
    s = max(w, h)/900
    c = (np.sin((x*w/s)*.045+t*2.1+np.sin((y*h/s)*.03+t*1.3)*2.2)
         + np.sin((y*h/s)*.052-t*1.7+np.sin((x*w/s)*.027-t)*2.6)
         + np.sin(((x*w+y*h)/s)*.031+t*2.6))
    caustic = np.clip((c-1.1)/1.9, 0, 1)**2                        # thin bright ridges where the waves meet
    deep, light = np.array((14, 62, 168), np.float32), np.array((70, 160, 240), np.float32)
    base = deep+(light-deep)*(1-y)[..., None]*.8
    return np.clip(base+caustic[..., None]*np.array((150, 170, 160), np.float32), 0, 255)


class Composer:
    def __init__(self, shots, overlays, captions, total, matter=None, ffmpeg='ffmpeg', progress=None, start=0.):
        self.shots, self.overlays, self.captions = shots, overlays, captions
        self.start = start
        self.total, self.matter, self.ffmpeg = total, matter, ffmpeg
        self.progress = progress or (lambda a, s: None)
        self.sprites = {}
        self.last = None
        self.accent_previous = {}

    def _sprite(self, key, make):
        if key not in self.sprites: self.sprites[key] = make()
        return self.sprites[key]

    def _base(self, shot, reader, t):
        frame = reader.next()
        k = (t-shot.t0)/max(.01, shot.t1-shot.t0)
        if shot.ease_in: k = min(1., max(0., k))**2.6
        z = shot.zoom0+(shot.zoom1-shot.zoom0)*k
        if shot.look == 'card': return accents.card(frame, k, shot.tone)
        if shot.look == 'band':
            import cv2
            h, w = frame.shape[:2]
            band = cv2.resize(frame, (w, max(2, int(h*.62))))
            frame = np.full_like(frame, look.INK)
            y = (h-band.shape[0])//2
            frame[y:y+band.shape[0]] = band
        if shot.face and shot.center:   # the subject moves to the middle as the frame zooms in on it
            import cv2
            h, w = frame.shape[:2]
            m = np.array([[z, 0, w/2-z*shot.face[0]], [0, z, h/2-z*shot.face[1]]], np.float32)
            return cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        if shot.face: return _zoom(frame, z, shot.face[0], shot.face[1])
        return _zoom(frame, z)

    def frames(self):
        n_total = int(round(self.total*FPS))
        try:
            first = int(round(self.start*FPS))
            shot_i = max(0, max((k for k, s in enumerate(self.shots) if s.t0 <= first/FPS+1e-6), default=0))
            reader = Reader(self.shots[shot_i], self.ffmpeg)
            behind = self._behind(self.shots[shot_i])
            for n in range(first, n_total):
                t = n/FPS
                while shot_i+1 < len(self.shots) and self.shots[shot_i+1].t0 <= t+1e-6:
                    shot_i += 1
                    reader.close()
                    if behind: behind.close()
                    reader = Reader(self.shots[shot_i], self.ffmpeg)
                    behind = self._behind(self.shots[shot_i])
                    if self.matter: self.matter.reset()
                shot = self.shots[shot_i]
                frame = self._base(shot, reader, t)
                if behind:   # the people of this shot, standing in front of another place
                    mask = self._matte(frame)
                    if mask is not None:
                        m = mask[..., None]
                        frame = (behind.next()*(1-m)+frame*m).astype(np.uint8)
                active = [o for o in self.overlays if o.t0 <= t < o.t1]
                for o in active:   # the paper: the opening layout, its tearing open, and the wrap-up back onto it
                    if o.kind == 'paper':
                        frame = paper_layout(frame, t, o.data)
                    elif o.kind == 'paperout':
                        k = _ease(min(1., (t-o.t0)/max(.01, (o.t1-o.t0)*.6)))
                        frame = paper_layout(frame, t, o.data, k=k, words=k)
                    elif o.kind == 'tear':
                        key = (o.t0, o.t1, 'tear')
                        if key not in self.accent_previous:
                            self.accent_previous[key] = self.last.copy() if self.last is not None else paper(*frame.shape[:2])
                        frame = tear(frame, self.accent_previous[key], (t-o.t0)/max(.01, o.t1-o.t0))
                frame = self._compose(frame, t, active, shot)
                since = t-shot.t0
                if shot.kind == 'broll' and since < .16:   # b-roll lands with a short zoom settle and motion blur
                    k = 1-since/.16
                    frame = ((_zoom(frame, 1+.06*k).astype(np.uint16)+_zoom(frame, 1+.12*k)+frame)//3).astype(np.uint8)
                if n % 30 == 0: self.progress(n/max(1, n_total), 'Composing the picture…')
                self.last = frame
                yield frame
        finally:
            reader.close()
            if behind: behind.close()

    def _behind(self, shot):
        """The background moment a cut-out shot stands in front of (a Reader), or None."""
        if not shot.backdrop or not self.matter: return None
        path, src = shot.backdrop
        return Reader(Shot(shot.t0, shot.t1, 'aroll', path, src, rate=shot.rate, cx=.5, grade=shot.grade), self.ffmpeg)

    def _matte(self, frame):
        try:
            return self.matter(frame) if self.matter else None
        except Exception:
            LOG.warning('matte failed', exc_info=True)
            self.matter = None
            return None

    def _compose(self, frame, t, active, shot):
        W, H, u = look.W, look.H, look.unit()
        kinds = {o.kind for o in active}
        need_matte = shot.kind == 'aroll' and kinds & {'behind', 'outline', 'glow', 'silhouette', 'cutin', 'glowpop'}
        person = self._matte(frame) if need_matte else None
        mute = []
        for o in active:
            if o.kind == 'glowpop' and person is not None:   # over the previous shot (still playing): a glowing white
                import cv2                                     # cut-out of the people fades in, turns to colour, then their scene
                p = (t-o.t0)/max(.01, o.t1-o.t0)
                under = self._under(o, frame).astype(np.float32)
                f32 = frame.astype(np.float32)
                a = cv2.GaussianBlur(person, (0, 0), 1.2)[..., None]
                appear = _ease(p/.18)                                 # a glimpse: the white glow pops in on top
                colour = _ease((p-.25)/.3)                            # white -> their real colours
                scene = _ease((p-.4)/.6)                              # the previous shot -> their own, colourful scene
                halo = np.clip(cv2.GaussianBlur(person, (0, 0), 24*u)*1.8-person, 0, 1)[..., None]*appear*(1-scene)
                people = 255*(1-colour)+f32*colour
                back = under*(1-scene)+f32*scene
                out = back*(1-a*appear)+people*a*appear+halo*255*.85
                frame[:] = np.clip(out, 0, 255).astype(np.uint8)
            if o.kind == 'iris':   # an Earth-zoom push: the old shot rushes in, a circle opens on the new one, zooming in
                import cv2
                p = (t-o.t0)/max(.01, o.t1-o.t0)
                cx, cy = o.data.get('center') or (W/2, H/2)
                under = self._under(o, frame)
                zo = 1+1.4*p**1.6                                      # the old shot pushes in hard
                old = cv2.warpAffine(under, np.float32([[zo, 0, (1-zo)*cx], [0, zo, (1-zo)*cy]]), (W, H), borderMode=cv2.BORDER_REFLECT_101)
                blur = max(1, int(W*.03*p) | 1)
                if blur > 1:   # with a radial-ish rush: a blend of a few scales
                    acc = old.astype(np.float32)
                    for sc in (1.03, 1.06):
                        acc += cv2.warpAffine(old, cv2.getRotationMatrix2D((cx, cy), 0, sc), (W, H), borderMode=cv2.BORDER_REFLECT_101)
                    old = (acc/3).astype(np.uint8)
                zn = 1.5-.5*_ease(p)                                   # the new shot settles from close in
                new = cv2.warpAffine(frame, np.float32([[zn, 0, (1-zn)*cx], [0, zn, (1-zn)*cy]]), (W, H), borderMode=cv2.BORDER_REFLECT_101)
                yy, xx = np.ogrid[:H, :W]
                r = (_ease(p)**1.3)*math.hypot(max(cx, W-cx), max(cy, H-cy))*1.05
                d = np.sqrt((xx-cx)**2+(yy-cy)**2)
                a = np.clip((r-d)/max(2., W*.01), 0, 1)[..., None]
                frame[:] = (old*(1-a)+new*a).astype(np.uint8)
            if o.kind == 'fadeout':   # the film fades to black
                k = min(1., max(0., (t-o.t0)/.4))
                frame[:] = (frame*(1-k)).astype(np.uint8)
            if o.kind == 'fade':   # a smooth dissolve from the previous shot (still playing) into this one
                k = _ease((t-o.t0)/max(.01, o.t1-o.t0))
                frame[:] = (self._under(o, frame).astype(np.float32)*(1-k)+frame*k).astype(np.uint8)
            if o.kind == 'cutin':   # the people arrive cut out over the previous shot, then their own picture fades in
                prev = self._under(o, frame).astype(np.float32)
                p = (t-o.t0)/max(.01, o.t1-o.t0)
                k = 0. if p < .45 else _ease((p-.45)/.55)
                bg = prev*(1-k)+frame*k
                a = person[..., None] if person is not None else np.full(frame.shape[:2]+(1,), min(1., p*2), np.float32)
                frame[:] = (bg*(1-a)+frame*a).astype(np.uint8)
        for o in active:
            if o.kind in ('quote', 'message'):   # the picture falls back so the words can land
                k = _ease((t-o.t0)/.4)
                frame[:] = (frame*(1-.62*k)).astype(np.uint8)
            elif o.kind == 'black':   # a black opening while the music builds
                frame[:] = 0
        for o in active:
            if o.kind in ('behind', 'outline', 'soft'):
                text, tone = o.data['text'], o.data['tone']
                f = look.fit_heavy(text, W*.92, int(min(H*.34, W*.42)))
                fill, edge = tuple(o.data.get('fill') or look.TONES[tone]), o.data.get('edge')   # edge: an outline colour
                if o.data.get('texture') == 'water': fill = (255, 255, 255)   # painted with moving water below
                solid = self._sprite(('behind', text, fill, tuple(edge or ()), W), lambda: look.text_sprite(
                    text, f, fill=fill, shadow=.35, tracking=-int(f.size*.03),
                    **({'stroke': max(4, int(f.size*.045)), 'stroke_fill': tuple(edge)} if edge else {})))
                if o.data.get('texture') == 'water':   # the letters filled with moving water
                    rgba = solid.rgba.copy()
                    rgba[..., :3] = water(rgba.shape[0], rgba.shape[1], t).astype(np.uint8)
                    solid = look.Sprite(rgba, solid.ax, solid.ay, solid.pad, solid.ascent, solid.width)
                k = _ease((t-o.t0)/.22)
                out = min(1, max(0, (o.t1-t)/.2))
                y = o.data.get('y', H*.3)
                scale = 1.08-.08*k
                if person is not None and o.kind != 'soft':
                    bg = frame.copy()
                    look.paste(bg, solid, W/2, y, alpha=k*out, scale=scale)
                    a = person[..., None]
                    frame[:] = (bg*(1-a)+frame*a).astype(np.uint8)
                    if o.kind == 'outline':
                        line = self._sprite(('outline', text, tone, W), lambda: look.text_sprite(text, f, fill=look.TONES[tone], stroke=max(3, int(5*u)), shadow=0, outline_only=True, tracking=-int(f.size*.03)))
                        look.paste(frame, line, W/2, y, alpha=.9*k*out, scale=scale)
                else:
                    look.paste(frame, solid, W/2, H*.2, alpha=.95*k*out, scale=scale)
            elif o.kind == 'glow' and person is not None:
                import cv2
                tone = look.TONES[o.data['tone']]
                k = min(1, (t-o.t0)/.3)*min(1, max(0, (o.t1-t)/.3))
                rim = np.clip((cv2.GaussianBlur(person, (0, 0), 26*u)-person)*2.6, 0, 1)[..., None]*k
                frame[:] = np.clip(frame+rim*np.array(tone, np.float32), 0, 255).astype(np.uint8)
        for o in active:
            if o.kind == 'slam':
                k = min(1, (t-o.t0)/.08)
                frame[:] = (frame*(1-.92*k)+np.array(look.INK)*.92*k).astype(np.uint8)
                text, tone = o.data['text'], o.data['tone']
                f = look.fit_heavy(text, W*.86, int(min(H*.3, W*.36)))
                big = self._sprite(('slam', text, tone, W), lambda: look.text_sprite(text, f, fill=look.TONES[tone], glow=look.TONES[tone], shadow=.4, tracking=-int(f.size*.03)))
                s = t-o.t0
                scale = 1.06-.06*_ease(s/.3)
                if s < .14:
                    shift = int(16*u*(1-s/.14))
                    layer = np.zeros_like(frame)
                    look.paste(layer, big, W/2, H*.48, scale=scale)
                    frame[..., 0] = np.maximum(frame[..., 0], np.roll(layer[..., 0], shift, 1))
                    frame[..., 1] = np.maximum(frame[..., 1], layer[..., 1])
                    frame[..., 2] = np.maximum(frame[..., 2], np.roll(layer[..., 2], -shift, 1))
                else:
                    look.paste(frame, big, W/2, H*.48, scale=scale)
                mute.append((o.t0, o.t1))
            elif o.kind in ('quote', 'message'):
                mute.append((o.t0, o.t1))
                self._words(frame, t, o)
            elif o.kind == 'flash':
                k = 1-abs((t-(o.t0+o.t1)/2)/((o.t1-o.t0)/2))
                frame[:] = np.clip(frame.astype(np.int16)+int(110*max(0, k)), 0, 255).astype(np.uint8)
            elif o.kind == 'silhouette':   # a bright splash: cream background, the people as cut-out silhouettes
                k = 1. if t-o.t0 < .3 else max(0., 1-(t-o.t0-.3)/max(.01, o.t1-o.t0-.3))
                splash = np.empty_like(frame); splash[:] = (246, 241, 226)
                if person is not None:
                    a = person[..., None]
                    splash = (splash*(1-a)+np.array((16, 22, 34))*a).astype(np.uint8)
                frame[:] = (frame*(1-k)+splash*k).astype(np.uint8)
            elif o.kind == 'outro':   # the ending word pops in, holds, then the camera flies into it
                frame[:] = self._outro(frame, t, o)
            elif o.kind == 'typed':   # a big place name typed out letter by letter (the trip-reel opener)
                self._typed(frame, t, o)
            elif o.kind == 'corner':   # a lyric-video word popping in, white, in a top corner
                text = o.data['text']
                size = int(min(H*.12, W*.11))
                sp = self._sprite(('corner', text, W), lambda: look.text_sprite(text, look.HEAVY(size), fill=(250, 250, 248), shadow=.5, tracking=int(size*.02)))
                k = _ease((t-o.t0)/.12)
                x = W*.06+sp.w/2 if o.data['side'] == 'left' else W*.94-sp.w/2
                bars = any(x.kind == 'bars' for x in active) and W > H   # below a letterbox bar, never under it
                top = max(H*.13, (H-W/2.39)/2+size*.75) if bars else H*.13
                look.paste(frame, sp, x, top+o.data.get('row', 0)*size*1.05, alpha=k, scale=1.12-.12*k)
            elif o.kind == 'title':
                text = o.data['text']
                sp = self._sprite(('title', text, W), lambda: look.text_sprite(text.upper(), look.TIGHT(34*u, 700), fill=(236, 240, 236), tracking=int(10*u), shadow=.7))
                k = min(1, (t-o.t0)/.4)*min(1, max(0, (o.t1-t)/.4))
                look.paste(frame, sp, W/2, H*.08, alpha=.92*k)
        for o in active:
            if o.kind in ('scribble', 'perspective'):
                f = look.fit_heavy(o.data['text'], W*.66, int(min(H*.18, W*.22)))
                sp = self._sprite((o.kind, o.data['text'], W), lambda: look.text_sprite(o.data['text'], f, fill=look.WHITE, shadow=.6))
                p = _ease((t-o.t0)/.2)
                if o.kind == 'perspective':
                    import cv2
                    layer = np.zeros((H, W, 3), np.uint8)
                    look.paste(layer, sp, W*.5, H*.3, alpha=p)
                    corners = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
                    target = np.float32([[W*.08, H*.13], [W*.96, 0], [W*.9, H*.92], [0, H]])
                    warped = cv2.warpPerspective(layer, cv2.getPerspectiveTransform(corners, target), (W, H))
                    frame[:] = np.maximum(frame, warped)
                else:
                    look.paste(frame, sp, W*.5, H*.64, alpha=p)
                    accents.circle(frame, t-o.t0, look.TONES[o.data['tone']])
        for o in active:
            if o.kind == 'bars' and W > H:   # cinematic letterbox: a 2.39:1 picture
                bar = max(0, int((H-W/2.39)/2))
                if bar: frame[:bar] = 0; frame[H-bar:] = 0
        for o in active:
            if o.kind == 'lyric': self._lyric(frame, t, o)
            if o.kind == 'whisper': self._whisper(frame, t, o)
        if self.captions: self.captions.draw(frame, t, mute)
        for o in active:
            if o.kind != 'accent': continue
            key = (o.t0, o.t1, o.data['kind'])
            if key not in self.accent_previous:
                self.accent_previous[key] = self.last.copy() if self.last is not None else None
            phase = (t-o.t0)/max(.001, o.t1-o.t0)
            frame = accents.apply(frame, self.accent_previous[key], o.data['kind'], phase)
            for b in active:   # a transition's glow never spills onto the letterbox
                if b.kind == 'bars' and W > H:
                    bar = max(0, int((H-W/2.39)/2))
                    if bar: frame[:bar] = 0; frame[H-bar:] = 0
        keep = {}
        for k, v in self.accent_previous.items():
            if (k[0] in ('cutin', 'under') and t-k[1] < 2) or (k[0] not in ('cutin', 'under') and t < k[1]): keep[k] = v
            elif isinstance(v, Reader): v.close()
        self.accent_previous = keep
        return frame

    TYPED_COLOUR = (244, 231, 198)   # warm cream

    def _under(self, o, frame):
        """The previous shot carrying on under a transition (or its last frame when it cannot be read on)."""
        key = ('under', o.t0)
        if key not in self.accent_previous:
            under = o.data.get('under')
            self.accent_previous[key] = Reader(under, self.ffmpeg) if under is not None else (self.last.copy() if self.last is not None else frame.copy())
        got = self.accent_previous[key]
        return got.next() if isinstance(got, Reader) else got

    def _outro(self, frame, t, o):
        """The ending word pops in, holds, then the camera flies into its first letter until that letter's colour
        (or water texture) fills the frame: the film ends in the word's colour."""
        import cv2
        W, H = look.W, look.H
        text, fill = o.data['text'], np.array(o.data['fill'], np.float32)
        key = ('outro', text, W)
        if key not in self.sprites:
            f = look.fit_heavy(text, W*.78, int(min(H*.3, W*.22)))
            sp = look.text_sprite(text, f, fill=(255, 255, 255), shadow=0, tracking=-int(f.size*.02))
            mask = np.zeros((H, W), np.float32)
            y0, x0 = int(H*.5-sp.h/2), int(W/2-sp.w/2)
            ys, xs = max(0, y0), max(0, x0)
            part = sp.rgba[ys-y0:, xs-x0:, 3][:H-ys, :W-xs]
            mask[ys:ys+part.shape[0], xs:xs+part.shape[1]] = part/255.
            # aim at the first letter's thick left stroke, so the flight ends inside its colour
            cols = np.nonzero(mask.max(0) > .5)[0]
            first = x0+sp.pad+f.getlength(text[0])*.16 if len(cols) else W/2
            rows = np.nonzero(mask[:, int(min(W-1, max(0, first)))] > .5)[0]
            aim = (float(first), float(rows.mean()) if len(rows) else H*.5)
            self.sprites[key] = (mask, aim)
        mask, (ax, ay) = self.sprites[key]
        p = (t-o.t0)/max(.01, o.t1-o.t0)
        if p < .1: z = 1.35-.35*_ease(p/.1)                       # pop in
        elif p < .5: z = 1.                                        # hold
        else: z = math.exp((p-.5)/.42*math.log(60))                # fly into the first letter
        cx, cy = (W/2, H*.5) if p < .5 else (ax, ay)
        m = cv2.warpAffine(mask, np.float32([[z, 0, (1-z)*cx], [0, z, (1-z)*cy]]), (W, H))[..., None] if abs(z-1) > 1e-3 else mask[..., None]
        # the water texture while the word stands; once the camera flies in, plain colour (no white streaks)
        if o.data.get('texture') == 'water' and p < .58:
            k = min(1., max(0., (p-.48)/.1))
            paint = water(H, W, t)*(1-k)+fill*k
        else:
            paint = fill
        base = frame*(1-.25*min(1., p/.1))   # the moment itself stays behind the word as the camera flies in
        out = base*(1-m)+paint*m
        if p > .86:   # and the film ends in the word's colour
            k = min(1., (p-.86)/.14)
            out = out*(1-k)+fill*k
        return np.clip(out, 0, 255).astype(np.uint8)

    def _typed(self, frame, t, o):
        W, H, u = look.W, look.H, look.unit()
        text = o.data['text']
        span = max(.01, o.data['to']-o.data['from'])
        shown = o.data.get('fixed') or max(min(2, len(text)), int(round(len(text)*min(1., max(0., (t-o.data['from'])/span)))))
        part = text[:shown]
        f = look.fit_heavy(text, W*.82, int(min(H*.16, W*.24)))
        whole = self._sprite(('typed-w', text, W), lambda: look.text_sprite(text, f, fill=self.TYPED_COLOUR, shadow=.45, tracking=int(f.size*.01)))
        sp = self._sprite(('typed', part, W), lambda: look.text_sprite(part, f, fill=self.TYPED_COLOUR, shadow=.45, tracking=int(f.size*.01)))
        # left-aligned with where the whole word will sit, so the letters grow to the right as they are typed
        x = W/2-whole.w/2+sp.w/2
        look.paste(frame, sp, x, H*(.36 if H > W else .42))

    LYRIC_COLOURS = {'bold': (246, 244, 238), 'serif': (246, 244, 238), 'glitch': (236, 40, 44), 'typewriter': (245, 205, 70),
                     'caption': (250, 248, 242)}

    def _lyric(self, frame, t, o):
        """One sung line, building word by word as it is sung (typewriter: letter by letter)."""
        W, H, u = look.W, look.H, look.unit()
        style, words = o.data.get('style', 'bold'), o.data['words']
        shown = [w for w, at in words if at <= t]
        if not shown: return
        text = ' '.join(shown)
        if style == 'typewriter':   # type the newest word out over its first 0.25 s
            last_at = max(at for _, at in words if at <= t)
            k = min(1., (t-last_at)/.25)
            text = ' '.join(shown[:-1]+[shown[-1][:max(1, int(round(len(shown[-1])*k)))]])
        full = ' '.join(w for w, _ in words)
        upper = style in ('bold', 'glitch')
        if upper: text, full = text.upper(), full.upper()
        colour = self.LYRIC_COLOURS.get(style, look.WHITE)
        if style in ('bold', 'glitch'):
            f = look.fit_heavy(full, W*.86, int(min(H*.11, W*.2)), int(40*u))
        elif style == 'caption':   # what someone says in a music edit: clean, mid-weight, lower third
            size = int(min(H*.042, W*.075))
            f = look.TIGHT(size, 760)
            while size > 24*u and f.getlength(full) > W*.84:
                size = int(size*.92); f = look.TIGHT(size, 760)
        else:
            size = int(min(H*.075, W*.13))
            f = (look.ITALIC if style == 'serif' else look.SERIF)(size)
            while size > 30*u and f.getlength(full) > W*.86:
                size = int(size*.9); f = (look.ITALIC if style == 'serif' else look.SERIF)(size)
        sp = self._sprite(('lyric', style, text, W), lambda: look.text_sprite(text, f, fill=colour, shadow=.75))
        fade = min(1., (t-o.t0)/.12)*min(1., max(0., (o.t1-t)/.18))
        newest = max(at for _, at in words if at <= t)
        pop = 1+.08*max(0., 1-(t-newest)/.14) if style != 'typewriter' else 1.
        y = H*(.5 if style in ('bold', 'glitch') else .74 if style == 'caption' else .62)
        if style == 'glitch' and t-newest < .16:
            layer = np.zeros_like(frame)
            look.paste(layer, sp, W/2, y, alpha=fade, scale=pop)
            shift = int(10*u)
            frame[..., 0] = np.maximum(frame[..., 0], np.roll(layer[..., 0], shift, 1))
            frame[..., 1] = np.maximum(frame[..., 1], layer[..., 1])
            frame[..., 2] = np.maximum(frame[..., 2], np.roll(layer[..., 2], -shift, 1))
        else:
            look.paste(frame, sp, W/2, y, alpha=fade, scale=pop)

    def _whisper(self, frame, t, o):
        """A reference edit's line ("I wish that I could STAY here..."): small white italic words appearing one by one in
        the open sky above the people; the word in capitals starts a second line, bigger and bolder."""
        W, H, u = look.W, look.H, look.unit()
        words = [(w, at) for w, at in o.data['words'] if at <= t]
        if not words: return
        lines, line = [], []
        for w, _ in words:
            loud = w.isupper() and len(w) > 1
            if loud and line: lines.append(line); line = []
            line.append(w)
        if line: lines.append(line)
        def sprite(text, loud):
            size = int((62 if loud else 38)*u)
            def make():
                sp = look.text_sprite(text, look.SANS(size, 800 if loud else 500), shadow=.7)
                from PIL import Image   # an italic slant
                img = Image.fromarray(sp.rgba)
                k = .2
                img = img.transform((img.width+int(img.height*k), img.height), Image.AFFINE, (1, k, -img.height*k, 0, 1, 0), Image.BICUBIC)
                return look.Sprite(np.asarray(img), .5, .5)
            return self._sprite(('whisper', text, loud, size), make)
        fade = min(1., max(0., (o.t1-t)/.12))
        x, y = W*.62, H*.3
        for k, line in enumerate(lines):
            loud = any(w.isupper() and len(w) > 1 for w in line)
            sp = sprite(' '.join(line), loud)
            look.paste(frame, sp, x+(W*.04 if k else 0), y, alpha=fade)
            y += (70 if loud else 52)*u

    def _words(self, frame, t, o):
        """The payoff (quote) or the closing message: centred, word by word, each word as it is spoken."""
        W, H, u = look.W, look.H, look.unit()
        items = o.data['words']   # [(text, at, tone)]
        size = (78 if o.kind == 'quote' else 72)*u
        f = look.TIGHT(size, 820)
        space = size*.26
        max_w = W*(.8 if W > H else .86)
        sprites = []
        for text, at, tone in items:
            clean = text.strip(',') if o.kind == 'message' else text.strip('.,!?')
            key = ('words', clean, tone, int(size))
            sprites.append((self._sprite(key, lambda: (look.chip(clean, look.TIGHT(size*1.04, 880), look.TONES[tone]) if tone
                                                       else look.text_sprite(clean, f, fill=look.WHITE, shadow=.6, tracking=-int(size*.02))).baseline()), at))
        lines, line, width = [], [], 0
        for (sp, at), (text, _, _) in zip(sprites, items):
            if line and width+space+sp.width > max_w: lines.append((line, width)); line, width = [], 0
            width = width+(space if line else 0)+sp.width; line.append((sp, at))
            if o.kind == 'message' and text.endswith(('.', '!', '?')): lines.append((line, width)); line, width = [], 0
        if line: lines.append((line, width))
        y = H*.5-(len(lines)-1)*size*.6
        fade = min(1, max(0, (o.t1-t)/.25))
        for line, width in lines:
            x = W/2-width/2
            for sp, at in line:
                if t >= at-.06:
                    k = _ease((t-at+.06)/.25)
                    look.paste(frame, sp, x, y+(1-k)*size*.25, alpha=k*fade)
                x += sp.width+space
            y += size*1.2


def opener_frames(word, footage, duration=OPENER, ffmpeg='ffmpeg'):
    """TEXT INSPO's text-as-mask opener: the word filled with footage on black, then we fly through it."""
    import cv2
    W, H = look.W, look.H
    shot = Shot(0, duration, 'broll', footage, 0, look='full', grade='forest')
    info = probe(footage)
    shot.src = max(0, min(info['duration']-duration-.2, info['duration']*.3))
    reader = Reader(shot, ffmpeg)
    f = look.fit_heavy(word, W*.9, int(min(H*.42, W*.4)))
    sprite = look.text_sprite(word, f, fill=(255, 255, 255), shadow=0, tracking=-int(f.size*.03))
    alpha = sprite.rgba[..., 3]
    mask = np.zeros((H, W), np.uint8)
    y0, x0 = int(H*.48-sprite.h/2), int(W/2-sprite.w/2)
    ys, xs = max(0, y0), max(0, x0)
    part = alpha[ys-y0:, xs-x0:][:H-ys, :W-xs]
    mask[ys:ys+part.shape[0], xs:xs+part.shape[1]] = part
    try:
        for n in range(int(duration*FPS)):
            t = n/FPS
            frame = reader.next()
            z = 1+.05*t if t < .62 else 1.03*math.exp((t-.62)*4.6)
            m = cv2.warpAffine(mask, np.array([[z, 0, (1-z)*W/2], [0, z, (1-z)*H*.48]], np.float32), (W, H)).astype(np.float32)[..., None]/255.
            reveal = min(1, max(0, (z-6)/5))
            m = m*(1-reveal)+reveal
            lit = np.clip(frame.astype(np.float32)*1.35+12, 0, 255)
            yield (lit*m*min(1, t/.25)).astype(np.uint8)
    finally:
        reader.close()


def encode(frames_iter, audio, out, ffmpeg='ffmpeg'):
    cmd = [ffmpeg, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{look.W}x{look.H}', '-r', str(FPS), '-i', '-',
           '-i', str(audio), '-map', '0:v', '-map', '1:a', '-vf', 'vignette=angle=0.45:mode=forward,noise=c0s=4:c0f=t+u',
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '256k',
           '-movflags', '+faststart', '-shortest', str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in frames_iter:
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors='ignore')
        proc.wait()
    if proc.returncode: raise ValueError('I could not write the finished video: '+err[-300:])
