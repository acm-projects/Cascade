"""The Cascade stamp, the signature at the end of every edit: a wet blue paint stroke sweeps across
the dark, flicks drops of water off its end, and "Cascade" is brushed over it in white. No music,
only the splash. 2.5 seconds."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import look

DURATION = 2.5
DEEP, AQUA = np.array((18, 74, 160), np.float32), np.array((96, 206, 255), np.float32)


def _ease(x, p=3):
    x = min(1, max(0, x))
    return 1-(1-x)**p


def _stroke(w, h, seed=5):
    """A loaded paint brush dragged once: a heavy wet start, a body whose width breathes, and dry
    bristle streaks breaking up at the end. Blues from deep to aqua, with a darker wet edge."""
    rng = np.random.default_rng(seed)
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    xs = np.linspace(0, w, 220)
    breathe = 1+.12*np.sin(xs/w*7.1+1.3)+.07*np.sin(xs/w*17.3)        # the stroke's width varies along it
    bend = np.sin(xs/w*math.pi*1.1-.2)*h*.07                           # a gentle arc
    for _ in range(170):
        band = rng.uniform(-.48, .48)
        thick = rng.uniform(3, 11)*h/240
        mix = rng.uniform(0, 1)**.8
        color = DEEP*(1-mix)+AQUA*mix
        alpha = rng.uniform(.45, 1.)
        start = rng.uniform(0, .05)*w+abs(band)*w*.07                     # a rounded, loaded start
        stop = w*(1-rng.uniform(0, .3)*(abs(band)*1.4+.3))                 # outer bristles run dry first
        pts = []
        for x, br, bn in zip(xs, breathe, bend):
            if x < start or x > stop: continue
            if x > w*.7 and rng.random() < .035:                          # dry-brush breaks toward the end
                if len(pts) > 1: d.line(pts, fill=tuple(int(c) for c in color)+(int(255*alpha),), width=max(1, int(thick)))
                pts = []
                continue
            pts.append((x, h/2+band*h*.8*br+bn+rng.normal(0, .5)))
        if len(pts) > 1: d.line(pts, fill=tuple(int(c) for c in color)+(int(255*alpha),), width=max(1, int(thick)))
    # a few lighter highlights where the paint is thick
    for _ in range(18):
        y = h/2+rng.uniform(-.3, .3)*h
        x0 = rng.uniform(.05, .5)*w
        d.line([(x0, y), (x0+rng.uniform(.1, .35)*w, y+rng.normal(0, 2))], fill=(190, 236, 255, int(rng.uniform(60, 140))), width=max(1, int(2*h/240)))
    soft = img.filter(ImageFilter.GaussianBlur(1.1))
    a = np.asarray(soft).astype(np.float32)
    edge = np.asarray(soft.split()[3].filter(ImageFilter.GaussianBlur(6))).astype(np.float32)/255.
    rim = np.clip(edge-a[..., 3]/255., 0, 1)[..., None]
    rgb = a[..., :3]*(1-rim*.5)+DEEP*.4*rim*.5
    return np.dstack([rgb, np.maximum(a[..., 3], rim[..., 0]*70)]).astype(np.float32)


def _splatter(w, h, cx, cy, seed=9):
    rng = np.random.default_rng(seed)
    drops = []
    for _ in range(34):
        ang = rng.uniform(-1.1, 1.1)
        dist = rng.uniform(.02, .3)*w
        drops.append((cx+math.cos(ang)*dist, cy+math.sin(ang)*dist*.6, rng.uniform(2, 11)*h/1080, rng.uniform(.06, .3), rng.uniform(0, 1)))
    return drops


def frames(background):
    """Yield frames at the current output size. `background` is the edit's last frame."""
    W, H, FPS = look.W, look.H, look.FPS
    u = look.unit()
    ink = np.zeros((H, W, 3), np.float32)+np.array(look.INK, np.float32)
    bg = background.astype(np.float32)
    sw, sh = int(W*(.78 if W > H else .92)), int(260*u)
    stroke = _stroke(sw, sh)
    sx, sy = (W-sw)//2, int(H*.5-sh/2)
    f = look.BRUSH(200*u)
    word = Image.new('L', (int(f.getlength('Cascade'))+80, int(260*u)), 0)
    ImageDraw.Draw(word).text((40, 10), 'Cascade', font=f, fill=255)
    box = word.getbbox()
    word = np.asarray(word.crop(box)).astype(np.float32)/255.
    wh, ww = word.shape
    wx, wy = W//2-ww//2, int(H*.5-wh/2-8*u)
    shadow = np.asarray(Image.fromarray((word*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10*u))).astype(np.float32)/255.
    drops = _splatter(W, H, sx+sw*.93, sy+sh*.5)
    caption = look.text_sprite('EDITED BY', look.TIGHT(28*u, 700), fill=(196, 230, 248), tracking=int(12*u), shadow=0)
    for n in range(int(DURATION*FPS)):
        t = n/FPS
        k = _ease(t/.35)
        out = bg*(1-k)+ink*k
        # the brush sweeps left to right; its leading edge is soft and wet
        if t > .2:
            head = _ease((t-.2)/.62, 2.4)*(sw+60)-30
            cols = np.clip((head-np.arange(sw))/26+.5, 0, 1)[None, :, None]
            a = stroke[..., 3:4]/255.*cols
            region = out[sy:sy+sh, sx:sx+sw]
            region[:] = region*(1-a)+stroke[..., :3]*a
        # drops flicked off the end of the stroke
        if t > .78:
            q = t-.78
            canvas = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
            d = ImageDraw.Draw(canvas)
            for x, y, r, delay, mix in drops:
                p = _ease((q-delay)/.25)
                if p <= 0: continue
                ox, oy = sx+sw*.93, sy+sh*.5
                px, py = ox+(x-ox)*p, oy+(y-oy)*p+260*u*max(0, q-delay-.25)**2
                color = tuple(int(c) for c in DEEP*(1-mix)+AQUA*mix)
                d.ellipse((px-r, py-r, px+r, py+r), fill=color)
            out = np.asarray(canvas).astype(np.float32)
        # "Cascade", brushed on in white
        if t > .7:
            reveal = _ease((t-.7)/.75, 2)
            edge = reveal*(ww+60)-30
            cols = np.clip((edge-np.arange(ww))/30+.5, 0, 1)[None, :]
            region = out[wy:wy+wh, wx:wx+ww]
            sa = (shadow*cols*.55)[..., None]
            region[:] = region*(1-sa)
            a = (word*cols)[..., None]
            region[:] = region*(1-a)+np.array(look.WHITE, np.float32)*a
        frame = np.clip(out, 0, 255).astype(np.uint8)
        if t > 1.1:
            look.paste(frame, caption, W/2, sy-26*u, alpha=_ease((t-1.1)/.4)*.85)
        if t > DURATION-.3:
            frame = (frame*(1-(t-(DURATION-.3))/.3)).astype(np.uint8)
        yield frame
