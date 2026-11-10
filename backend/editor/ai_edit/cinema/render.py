"""The picture: every shot decoded and graded by FFmpeg, then composed frame by frame in NumPy:
words that appear as they are spoken, giant words behind the speaker, b-roll that arrives on the
word, the silence moment, and the Cascade stamp. Encoded once at the end."""
import logging
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import look, stamp
from .look import FPS, H, W

LOG = logging.getLogger(__name__)
OPENER = 1.25          # seconds of opener before the first word plays
VOICE_AT = 1.05        # where the first word lands when there is an opener
PUNCH = (1.0, 1.13)    # zoom steps that hide a jump cut


@dataclass
class Shot:
    t0: float
    t1: float
    kind: str                 # aroll | broll
    path: str
    src: float                # source second at t0
    rate: float = 1.0         # source seconds per edit second
    cx: float = .5
    cy: float = .42
    zoom0: float = 1.
    zoom1: float = 1.03
    grade: str = 'cinema'
    look: str = 'full'        # full | card | band | mono
    face: tuple | None = None  # (x, y) of the face in the vertical frame
    tone: str = 'calm'


@dataclass
class Overlay:
    t0: float
    t1: float
    kind: str                 # caption | behind | outline | glow | slam | serif | flash
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
    """(cx, cy) of the biggest face as fractions of the source frame, or None."""
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


def _crop_box(sw, sh, cx, cy=.5):
    """The 9:16 window (x, y, w, h) inside a source frame, centred on cx."""
    if sw/sh > 9/16:
        ch = sh//2*2; cw = int(ch*9/16)//2*2
    else:
        cw = sw//2*2; ch = int(cw*16/9)//2*2
    x = int(min(max(0, sw*cx-cw/2), sw-cw))
    y = int(min(max(0, sh*cy-ch/2), sh-ch))
    return x, y, cw, ch


class Reader:
    """Frames of one shot, graded and framed to 1080x1920 (or the card/band size)."""
    def __init__(self, shot, ffmpeg='ffmpeg'):
        info = probe(shot.path)
        sw, sh = info['width'], info['height']
        length = (shot.t1-shot.t0)*shot.rate+.2
        grade = look.GRADES['mono' if shot.look == 'mono' else shot.grade]
        speed = f'setpts=PTS/{shot.rate:.4f},' if abs(shot.rate-1) > .01 else ''
        if shot.look in ('card', 'band'):
            self.size = (940, 705) if shot.look == 'card' else (W, int(W*sh/sw)//2*2)
            vf = f"{speed}fps={FPS},scale={self.size[0]}:{self.size[1]}:force_original_aspect_ratio=increase:flags=lanczos,crop={self.size[0]}:{self.size[1]},{grade}"
        else:
            x, y, cw, ch = _crop_box(sw, sh, shot.cx)
            self.size = (W, H)
            vf = f"{speed}fps={FPS},crop={cw}:{ch}:{x}:{y},scale={W}:{H}:flags=lanczos,unsharp=5:5:0.55,{grade}"
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


def _zoom(frame, z, cx=W/2, cy=H*.42):
    if abs(z-1) < .002: return frame
    import cv2
    m = np.array([[z, 0, (1-z)*cx], [0, z, (1-z)*cy]], np.float32)
    return cv2.warpAffine(frame, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _blur(frame, k=61):
    import cv2
    small = cv2.resize(frame, (W//6, H//6), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), k/12)
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)


_CARD_MASK = {}


def _card_mask(w, h, r=38):
    key = (w, h, r)
    if key not in _CARD_MASK:
        from PIL import Image, ImageDraw, ImageFilter
        m = Image.new('L', (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w-1, h-1), r, fill=255)
        _CARD_MASK[key] = np.asarray(m.filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32)[..., None]/255.
    return _CARD_MASK[key]


# ---------------------------------------------------------------- captions

class Captions:
    """Phrases of up to three words, low-centre, each word arriving as it is spoken: a blur that settles
    upward. The keyword of a phrase is set in italic serif, larger, in the colour of what it means."""
    Y = 1400

    def __init__(self, words, edit, offset, keywords, hidden):
        self.items = []
        order = edit.order
        phrase = []
        def close():
            if phrase: self.items.append(list(phrase)); phrase.clear()
        for n, i in enumerate(order):
            if i in hidden: close(); continue
            w = words[i]
            phrase.append(i)
            text = w['w']
            nxt = order[n+1] if n+1 < len(order) else None
            gap = (edit.word_out[nxt][0]-edit.word_out[i][1]) if nxt is not None else 9
            if len(phrase) >= 3 or text.endswith(('.', '?', '!', ',')) or gap > .3 or sum(len(words[j]['w']) for j in phrase) > 16: close()
        close()
        self.sprites = {}
        for group in self.items:
            for i in group:
                raw = words[i]['w'].strip()
                clean = raw.strip('.,!?;:"“”').replace('…', '')
                if not clean: clean = raw
                if i in keywords:
                    sp = look.text_sprite(clean, look.ITALIC(124), fill=look.TONES[keywords[i]], shadow=.6, glow=look.TONES[keywords[i]])
                else:
                    sp = look.text_sprite(clean, look.SANS(76, 720), fill=look.WHITE, shadow=.7)
                sp = sp.baseline()
                self.sprites[i] = (sp, sp.blurred(5), sp.blurred(2.2))
        self.edit, self.offset = edit, offset
        self.spans = []
        for k, group in enumerate(self.items):
            t0 = edit.word_out[group[0]][0]+offset-.04
            nxt = self.items[k+1] if k+1 < len(self.items) else None
            t1 = min(edit.word_out[group[-1]][1]+offset+.45, (edit.word_out[nxt[0]][0]+offset-.04) if nxt else 9e9)
            self.spans.append((t0, t1))

    def draw(self, frame, t, mute):
        for (t0, t1), group in zip(self.spans, self.items):
            if not t0 <= t < t1: continue
            if any(a <= t < b for a, b in mute): return
            space = 24
            widths = [self.sprites[i][0].width for i in group]
            total = sum(widths)+space*(len(group)-1)
            x = W/2-total/2
            out = 1-min(1, max(0, (t-(t1-.08))/.08))
            for i, w in zip(group, widths):
                start = self.edit.word_out[i][0]+self.offset-.05
                if t >= start:
                    k = min(1, (t-start)/.14)
                    sharp, soft, mid = self.sprites[i]
                    sprite = soft if k < .35 else mid if k < .75 else sharp
                    look.paste(frame, sprite, x, self.Y+(1-k)**2*26, alpha=min(1, k*1.4)*out)
                x += w+space


# ---------------------------------------------------------------- the composer

class Composer:
    def __init__(self, shots, overlays, captions, total, matter=None, ffmpeg='ffmpeg', progress=None, start=0.):
        self.shots, self.overlays, self.captions = shots, overlays, captions
        self.start = start
        self.total, self.matter, self.ffmpeg = total, matter, ffmpeg
        self.progress = progress or (lambda a, s: None)
        self.sprites = {}

    def _sprite(self, key, make):
        if key not in self.sprites: self.sprites[key] = make()
        return self.sprites[key]

    def _base(self, shot, reader, t, under):
        frame = reader.next()
        k = (t-shot.t0)/max(.01, shot.t1-shot.t0)
        if shot.look == 'card':
            bg = _blur(under if under is not None else np.zeros((H, W, 3), np.uint8))
            bg = (bg*.45).astype(np.uint8)
            h, w = frame.shape[:2]
            z = 1+.04*k
            import cv2
            card = cv2.resize(frame, (int(w*z), int(h*z)))[int(h*(z-1)/2):int(h*(z-1)/2)+h, int(w*(z-1)/2):int(w*(z-1)/2)+w]
            y0, x0 = int(H*.36-h/2), (W-w)//2
            m = _card_mask(w, h)
            key = ('shadow', w, h, y0, x0)
            if key not in self.sprites:
                self.sprites[key] = _blur(np.pad(np.full((h, w, 1), 255, np.uint8), ((y0, H-y0-h), (x0, W-x0-w), (0, 0))).repeat(3, 2), 41).astype(np.float32)/255.*.6
            bg = (bg*(1-self.sprites[key])).astype(np.uint8)
            region = bg[y0:y0+h, x0:x0+w]
            region[:] = (region*(1-m)+card*m).astype(np.uint8)
            return bg
        if shot.look == 'band':
            h = frame.shape[0]
            import cv2
            bg = _blur(cv2.resize(frame, (W, H)))
            bg = (bg*.35).astype(np.uint8)
            y0 = int(H*.4-h/2)
            bg[y0:y0+h] = frame
            return bg
        z = shot.zoom0+(shot.zoom1-shot.zoom0)*k
        cy = shot.face[1] if shot.face else H*.42
        return _zoom(frame, z, W/2, cy)

    def frames(self):
        """Yield every frame of the edit (without the stamp)."""
        n_total = int(round(self.total*FPS))
        shot_i, reader, previous = -1, None, None
        last_under = None
        mattes = {}
        try:
            first = int(round(self.start*FPS))
            # open whatever shot covers the first frame (or the first shot, if a gap comes first)
            shot_i = max(0, max((k for k, s in enumerate(self.shots) if s.t0 <= first/FPS+1e-6), default=0))
            reader = Reader(self.shots[shot_i], self.ffmpeg)
            for n in range(first, n_total):
                t = n/FPS
                while shot_i+1 < len(self.shots) and self.shots[shot_i+1].t0 <= t+1e-6:
                    shot_i += 1
                    if reader: reader.close()
                    reader = Reader(self.shots[shot_i], self.ffmpeg)
                    if self.matter: self.matter.reset()
                shot = self.shots[max(0, shot_i)]
                frame = self._base(shot, reader, t, last_under)
                if shot.kind == 'aroll' and shot.look == 'full': last_under = frame
                active = [o for o in self.overlays if o.t0 <= t < o.t1]
                frame = self._compose(frame, t, active, shot)
                # entry punch for b-roll: a short zoom settle with motion blur
                since = t-shot.t0
                if shot.kind == 'broll' and since < .14 and shot.look == 'full':
                    k = 1-since/.14
                    frame = ((_zoom(frame, 1+.08*k).astype(np.uint16)+_zoom(frame, 1+.16*k)+frame)//3).astype(np.uint8)
                if n % 30 == 0: self.progress(n/max(1, n_total), 'Composing the picture…')
                previous = frame
                yield frame
        finally:
            if reader: reader.close()
        self.last = previous

    def _matte(self, frame):
        try:
            return self.matter(frame) if self.matter else None
        except Exception:
            LOG.warning('matte failed', exc_info=True)
            self.matter = None
            return None

    def _compose(self, frame, t, active, shot):
        frame = frame.copy() if not frame.flags.writeable else frame
        kinds = {o.kind for o in active}
        need_matte = shot.kind == 'aroll' and shot.look == 'full' and kinds & {'behind', 'outline', 'glow'}
        person = self._matte(frame) if need_matte else None
        mute = []
        # the silence / serif moment: picture falls back, small serif words take the screen
        for o in active:
            if o.kind == 'serif':
                k = min(1, (t-o.t0)/.35)
                gray = frame.mean(2, keepdims=True)
                frame[:] = np.clip((frame*(1-.85*k)+gray*.85*k)*(1-.55*k), 0, 255).astype(np.uint8)
        for o in active:
            if o.kind in ('behind', 'outline') and person is not None:
                text, tone = o.data['text'], o.data['tone']
                solid = self._sprite(('behind', text, tone), lambda: look.text_sprite(text, look.fit_heavy(text, 1000), fill=look.TONES[tone], shadow=.35))
                k = min(1, (t-o.t0)/.22)
                out = min(1, max(0, (o.t1-t)/.2))
                y = o.data.get('y', H*.33)
                bg = frame.copy()
                look.paste(bg, solid, W/2, y, alpha=k*out, scale=1.12-.12*(1-(1-k)**3))
                a = person[..., None]
                frame[:] = (bg*(1-a)+frame*a).astype(np.uint8)
                if o.kind == 'outline':
                    line = self._sprite(('outline', text, tone), lambda: look.text_sprite(text, look.fit_heavy(text, 1000), fill=look.TONES[tone], stroke=5, shadow=0, outline_only=True))
                    look.paste(frame, line, W/2, y, alpha=.9*k*out, scale=1.12-.12*(1-(1-k)**3))
            elif o.kind == 'glow' and person is not None:
                import cv2
                tone = look.TONES[o.data['tone']]
                k = min(1, (t-o.t0)/.3)*min(1, max(0, (o.t1-t)/.3))
                rim = np.clip((cv2.GaussianBlur(person, (0, 0), 26)-person)*2.6, 0, 1)[..., None]*k
                frame[:] = np.clip(frame+rim*np.array(tone, np.float32), 0, 255).astype(np.uint8)
        for o in active:
            if o.kind == 'slam':
                k = min(1, (t-o.t0)/.08)
                frame[:] = (frame*(1-.92*k)+np.array(look.INK)*.92*k).astype(np.uint8)
                text, tone = o.data['text'], o.data['tone']
                big = self._sprite(('slam', text, tone), lambda: look.text_sprite(text, look.fit_heavy(text, 960, 420), fill=look.TONES[tone], glow=look.TONES[tone], shadow=.4))
                s = (t-o.t0)
                scale = 1.08-.08*min(1, s/.3)
                if s < .14:
                    shift = int(18*(1-s/.14))
                    layer = np.zeros_like(frame)
                    look.paste(layer, big, W/2, H*.46, scale=scale)
                    frame[..., 0] = np.maximum(frame[..., 0], np.roll(layer[..., 0], shift, 1))
                    frame[..., 1] = np.maximum(frame[..., 1], layer[..., 1])
                    frame[..., 2] = np.maximum(frame[..., 2], np.roll(layer[..., 2], -shift, 1))
                else:
                    look.paste(frame, big, W/2, H*.46, scale=scale)
                mute.append((o.t0, o.t1))
            elif o.kind == 'serif':
                mute.append((o.t0, o.t1))
                self._serif(frame, t, o)
            elif o.kind == 'flash':
                k = 1-abs((t-(o.t0+o.t1)/2)/((o.t1-o.t0)/2))
                frame[:] = np.clip(frame.astype(np.int16)+int(120*max(0, k)), 0, 255).astype(np.uint8)
            elif o.kind == 'slam_soft':
                text, tone = o.data['text'], o.data['tone']
                solid = self._sprite(('behind', text, tone), lambda: look.text_sprite(text, look.fit_heavy(text, 1000), fill=look.TONES[tone], shadow=.5))
                k = min(1, (t-o.t0)/.22)*min(1, max(0, (o.t1-t)/.2))
                look.paste(frame, solid, W/2, H*.2, alpha=.95*k, scale=1.08-.08*k)
            elif o.kind == 'title':
                text = o.data['text']
                sp = self._sprite(('title', text), lambda: look.text_sprite(text.upper(), look.SANS(40, 650), fill=(232, 238, 234), tracking=14, shadow=.7))
                k = min(1, (t-o.t0)/.4)*min(1, max(0, (o.t1-t)/.4))
                look.paste(frame, sp, W/2, H*.12, alpha=.9*k)
        if self.captions: self.captions.draw(frame, t, mute)
        return frame

    def _serif(self, frame, t, o):
        """Words of the payoff line stacked one under another, centred, each appearing as it is spoken."""
        items = o.data['words']   # [(text, at, tone)]
        size = 92 if len(items) <= 6 else 78
        lines, line = [], []
        for text, at, tone in items:
            line.append((text, at, tone))
            if len(line) >= (2 if len(items) > 6 else 1) or text.endswith((',', '.')): lines.append(line); line = []
        if line: lines.append(line)
        lines = lines[-6:]
        y = H*.5-(len(lines)-1)*size*.62
        for row in lines:
            pieces = []
            for text, at, tone in row:
                clean = text.strip('.,!?')
                f = look.ITALIC(size) if tone else look.SERIF(size)
                pieces.append((self._sprite(('serif', clean, tone, size), lambda: look.text_sprite(clean, f, fill=look.TONES[tone] if tone else look.WHITE, shadow=.5, glow=look.TONES[tone] if tone else None).baseline()), at))
            total = sum(p.width for p, _ in pieces)+24*(len(pieces)-1)
            x = W/2-total/2
            for sprite, at in pieces:
                if t >= at-.06:
                    k = min(1, (t-at+.06)/.3)
                    look.paste(frame, sprite.blurred(4*(1-k)) if k < .6 else sprite, x, y+(1-k)*14, alpha=k)
                x += sprite.width+24
            y += size*1.24


def opener_frames(word, footage, duration=OPENER, ffmpeg='ffmpeg'):
    """TEXT INSPO's text-as-mask opener: the word filled with footage on black, then we fly through it."""
    from PIL import Image
    import cv2
    shot = Shot(0, duration, 'broll', footage, 0, look='full', grade='forest')
    info = probe(footage)
    shot.src = max(0, min(info['duration']-duration-.2, info['duration']*.3))
    reader = Reader(shot, ffmpeg)
    sprite = look.text_sprite(word, look.fit_heavy(word, 980, 460), fill=(255, 255, 255), shadow=0)
    alpha = sprite.rgba[..., 3]
    mask = np.zeros((H, W), np.uint8)
    y0, x0 = int(H*.46-sprite.h/2), int(W/2-sprite.w/2)
    ys, xs = max(0, y0), max(0, x0)
    mask[ys:ys+sprite.h-(ys-y0), xs:xs+sprite.w-(xs-x0)] = alpha[ys-y0:, xs-x0:][:H-ys, :W-xs]
    try:
        for n in range(int(duration*FPS)):
            t = n/FPS
            frame = reader.next()
            if t < .62: z = 1+.05*t
            else: z = 1.03*math.exp((t-.62)*4.6)
            m = cv2.warpAffine(mask, np.array([[z, 0, (1-z)*W/2], [0, z, (1-z)*H*.46]], np.float32), (W, H)).astype(np.float32)[..., None]/255.
            reveal = min(1, max(0, (z-6)/5))
            m = m*(1-reveal)+reveal
            fade_in = min(1, t/.25)
            yield (frame*m*fade_in).astype(np.uint8)
    finally:
        reader.close()


def encode(frames_iter, audio, out, ffmpeg='ffmpeg'):
    cmd = [ffmpeg, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-i', str(audio), '-map', '0:v', '-map', '1:a', '-vf', 'vignette=angle=0.5:mode=forward,noise=c0s=5:c0f=t+u',
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
