"""Deterministic, short INSPO accents. No external footage, randomness or model calls."""
import math
import cv2
import numpy as np


def apply(frame, previous, kind, phase):
    """phase 0..1: a held previous picture reveals the incoming picture; ends pixel-exact."""
    p = min(1., max(0., phase))
    if p >= 1: return frame
    h, w = frame.shape[:2]
    if kind == 'whip':
        dx = int(w*.15*(1-p)**3)
        moved = cv2.warpAffine(frame, np.float32([[1, 0, dx], [0, 1, 0]]), (w, h), borderMode=cv2.BORDER_REFLECT_101)
        size = max(1, int(w*.045*(1-p)) | 1)
        return cv2.blur(moved, (size, 1))
    if kind == 'rgb':
        shift = max(1, int(w*.025*(1-p)**2))
        out = frame.copy()
        out[:, :, 0] = cv2.warpAffine(frame[:, :, 0], np.float32([[1, 0, shift], [0, 1, 0]]), (w, h), borderMode=cv2.BORDER_REFLECT_101)
        out[:, :, 2] = cv2.warpAffine(frame[:, :, 2], np.float32([[1, 0, -shift], [0, 1, 0]]), (w, h), borderMode=cv2.BORDER_REFLECT_101)
        return out
    if kind == 'flash':   # a white blow-out that clears to the new shot
        k = (1-p)**2
        return np.clip(frame.astype(np.float32)*(1-k)+255*k, 0, 255).astype(np.uint8)
    if kind == 'invert':  # a negative frame that snaps back
        return (255-frame) if p < .45 else frame
    if kind == 'glitch':  # sliced, shifted bands with split colour
        out = frame.copy()
        rng = np.random.default_rng(int(p*30))
        strength = (1-p)**1.5
        for _ in range(9):
            y0 = int(rng.integers(0, h)); band = int(rng.integers(h//60+1, h//12+2))
            out[y0:y0+band] = np.roll(frame[y0:y0+band], int(rng.normal(0, w*.08*strength)), 1)
        shift = max(1, int(w*.03*strength))
        out[:, :, 0] = np.roll(out[:, :, 0], shift, 1); out[:, :, 2] = np.roll(out[:, :, 2], -shift, 1)
        return out
    if kind == 'leak':    # a warm light leak sweeping across
        xs = np.linspace(-1, 1, w, dtype=np.float32)[None, :, None]
        centre = -1.2+2.4*p
        glow = np.exp(-((xs-centre)/.45)**2)*(1-p)*.85
        warm = np.array([255, 150, 60], np.float32)
        return np.clip(frame*(1-glow*.35)+warm*glow, 0, 255).astype(np.uint8)
    if kind == 'slices' and previous is not None:   # the new shot arrives through vertical strips, staggered, over the old one
        out = previous.copy()
        strips = 5
        for i in range(strips):
            local = min(1., max(0., p*1.6-i*.15))          # each strip starts a little later
            if local <= 0: continue
            x0, x1 = int(w*i/strips), int(w*(i+1)/strips)
            grow = int(h*min(1., local*1.4))               # it slides in from the top or bottom, alternating
            if i % 2: out[:grow, x0:x1] = frame[:grow, x0:x1]
            else: out[h-grow:, x0:x1] = frame[h-grow:, x0:x1]
        return out
    if kind == 'window' and previous is not None:   # the new shot appears in a box over the old one, then fills the frame
        k = min(1., p*1.25)
        grow = .38+.62*(k**2.2)
        bw, bh = max(2, int(w*grow)), max(2, int(h*grow))
        cx, cy = w*(.62-.12*k), h*(.45+.05*k)
        x0, y0 = int(min(max(0, cx-bw/2), w-bw)), int(min(max(0, cy-bh/2), h-bh))
        out = (previous*(1-.35*(1-k))).astype(np.uint8)       # the old shot dims behind the box
        small = cv2.resize(frame, (bw, bh))
        out[y0:y0+bh, x0:x0+bw] = small
        if k < .98:   # a thin white edge, like a photo laid on top
            cv2.rectangle(out, (x0, y0), (x0+bw-1, y0+bh-1), (245, 245, 240), max(1, int(min(w, h)*.004)))
        return out
    if kind == 'shake':   # a camera shake that settles: a punch in, jolting left/right and up/down, easing out
        k = (1-p)**2
        dx, dy = w*.035*k*math.sin(p*math.pi*9), h*.03*k*math.cos(p*math.pi*7)
        z = 1+.08*k
        M = np.float32([[z, 0, (1-z)*w/2+dx], [0, z, (1-z)*h/2+dy]])
        moved = cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REFLECT_101)
        size = max(1, int(w*.012*k) | 1)
        return cv2.blur(moved, (size, size)) if size > 1 else moved
    if kind == 'zoom':    # a radial zoom blur into the new shot
        k = (1-p)**2
        out = frame.astype(np.float32)
        for s in (1.04, 1.08, 1.12):
            z = 1+(s-1)*k*2.5
            M = cv2.getRotationMatrix2D((w/2, h/2), 0, z)
            out += cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REFLECT_101)
        return (out/4).astype(np.uint8)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if kind == 'ink':
        # Multi-lobed irregular edge, smooth within a few pixels; no copied ink texture.
        x, y = (xx-w*.48)/w, (yy-h*.48)/h
        angle = np.arctan2(y, x)
        radius = np.sqrt(x*x+y*y)
        edge = p*.95*(1+.12*np.sin(angle*7)+.07*np.cos(angle*13))
        mask = np.clip((edge-radius)*min(w, h)*.3, 0, 1)[..., None]
        old = previous if previous is not None else np.full_like(frame, (239, 233, 217))
        return (frame*mask+old*(1-mask)).astype(np.uint8)
    if kind == 'ripple':
        x, y = xx-w*.5, yy-h*.5
        radius = np.sqrt(x*x+y*y)+1
        amp = min(w, h)*.016*(1-p)**2
        wave = np.sin(radius/min(w, h)*42-p*math.pi*4)*amp
        return cv2.remap(frame, xx+x/radius*wave, yy+y/radius*wave, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    return frame


def card(frame, phase, tone):
    """A moving bordered photo on cream graph paper; preserves the full incoming picture."""
    h, w = frame.shape[:2]
    paper = np.full_like(frame, (239, 233, 217))
    step = max(10, int(min(w, h)*.055))
    paper[::step] = (214, 211, 198); paper[:, ::step] = (214, 211, 198)
    scale = .76+.04*min(1., max(0., phase))
    sw, sh = max(2, int(w*scale)), max(2, int(h*scale))
    border = max(2, int(min(w, h)*.012))
    photo = cv2.resize(frame, (sw, sh))
    photo = cv2.copyMakeBorder(photo, border, border*3, border, border, cv2.BORDER_CONSTANT, value=(252, 250, 241))
    canvas = np.zeros((h, w, 4), np.uint8)
    y, x = (h-photo.shape[0])//2, (w-photo.shape[1])//2
    canvas[y:y+photo.shape[0], x:x+photo.shape[1], :3] = photo
    canvas[y:y+photo.shape[0], x:x+photo.shape[1], 3] = 255
    m = cv2.getRotationMatrix2D((w/2, h/2), -3+phase*2, 1)
    layer = cv2.warpAffine(canvas, m, (w, h))
    a = layer[..., 3:4]/255.
    return (layer[..., :3]*a+paper*(1-a)).astype(np.uint8)


def circle(frame, phase, color):
    """A progressively hand-drawn double ellipse, within the title-safe area."""
    h, w = frame.shape[:2]
    end = int(360*min(1., phase/.35))
    u = min(w, h)/1080
    for shift in (0, 5*u):
        cv2.ellipse(frame, (int(w*.5+shift), int(h*.64)), (int(w*.38), int(min(h*.12, w*.13))),
                    -6, 0, end, tuple(int(v) for v in color), max(1, int(4*u)), cv2.LINE_AA)
