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

from . import look, settings

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


def _blur(frame, k=61):
    import cv2
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (max(8, w//6), max(8, h//6)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), k/12)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


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

class Composer:
    def __init__(self, shots, overlays, captions, total, matter=None, ffmpeg='ffmpeg', progress=None, start=0.):
        self.shots, self.overlays, self.captions = shots, overlays, captions
        self.start = start
        self.total, self.matter, self.ffmpeg = total, matter, ffmpeg
        self.progress = progress or (lambda a, s: None)
        self.sprites = {}
        self.last = None

    def _sprite(self, key, make):
        if key not in self.sprites: self.sprites[key] = make()
        return self.sprites[key]

    def _base(self, shot, reader, t):
        frame = reader.next()
        k = (t-shot.t0)/max(.01, shot.t1-shot.t0)
        z = shot.zoom0+(shot.zoom1-shot.zoom0)*k
        if shot.face: return _zoom(frame, z, shot.face[0], shot.face[1])
        return _zoom(frame, z)

    def frames(self):
        n_total = int(round(self.total*FPS))
        try:
            first = int(round(self.start*FPS))
            shot_i = max(0, max((k for k, s in enumerate(self.shots) if s.t0 <= first/FPS+1e-6), default=0))
            reader = Reader(self.shots[shot_i], self.ffmpeg)
            for n in range(first, n_total):
                t = n/FPS
                while shot_i+1 < len(self.shots) and self.shots[shot_i+1].t0 <= t+1e-6:
                    shot_i += 1
                    reader.close()
                    reader = Reader(self.shots[shot_i], self.ffmpeg)
                    if self.matter: self.matter.reset()
                shot = self.shots[shot_i]
                frame = self._base(shot, reader, t)
                active = [o for o in self.overlays if o.t0 <= t < o.t1]
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
        need_matte = shot.kind == 'aroll' and kinds & {'behind', 'outline', 'glow'}
        person = self._matte(frame) if need_matte else None
        mute = []
        for o in active:
            if o.kind in ('quote', 'message'):   # the picture falls back so the words can land
                k = _ease((t-o.t0)/.4)
                frame[:] = (frame*(1-.62*k)).astype(np.uint8)
        for o in active:
            if o.kind in ('behind', 'outline', 'soft'):
                text, tone = o.data['text'], o.data['tone']
                f = look.fit_heavy(text, W*.92, int(min(H*.34, W*.42)))
                solid = self._sprite(('behind', text, tone, W), lambda: look.text_sprite(text, f, fill=look.TONES[tone], shadow=.35, tracking=-int(f.size*.03)))
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
            elif o.kind == 'title':
                text = o.data['text']
                sp = self._sprite(('title', text, W), lambda: look.text_sprite(text.upper(), look.TIGHT(34*u, 700), fill=(236, 240, 236), tracking=int(10*u), shadow=.7))
                k = min(1, (t-o.t0)/.4)*min(1, max(0, (o.t1-t)/.4))
                look.paste(frame, sp, W/2, H*.08, alpha=.92*k)
        if self.captions: self.captions.draw(frame, t, mute)
        return frame

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
