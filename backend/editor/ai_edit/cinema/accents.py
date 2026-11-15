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
