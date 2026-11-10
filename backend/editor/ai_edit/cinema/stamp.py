"""The Cascade stamp: the little signature at the end of every edit, like an app's watermark but made
to be loved. Modelled on END INSPO (liquid wipe, a hand-written signature drawing itself) and made
ours: a single water drop falls into the dark, splashes into a crown and ripples, and "Cascade"
writes itself in light while drops run off the letters. 2.7 seconds."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import look

DURATION = 2.7
AQUA = (110, 222, 255)
CENTER = (540, 900)
IMPACT = .45


def _ease(x):
    x = min(1, max(0, x))
    return 1-(1-x)**3


def _word():
    f = look.SCRIPT(300)
    text = 'Cascade'
    w = int(f.getlength(text))+120
    ascent, descent = f.getmetrics()
    img = Image.new('L', (w, ascent+descent+120), 0)
    ImageDraw.Draw(img).text((60, 50), text, font=f, fill=255)
    box = img.getbbox()
    img = img.crop((box[0]-30, box[1]-30, box[2]+30, box[3]+30))
    mask = np.asarray(img).astype(np.float32)/255.
    h, w = mask.shape
    # white core fading to aqua at the bottom of the letters
    grad = np.linspace(0, 1, h)[:, None, None]
    color = np.array(look.WHITE, np.float32)*(1-grad*.55)+np.array(AQUA, np.float32)*grad*.55
    glow = np.asarray(img.filter(ImageFilter.GaussianBlur(14))).astype(np.float32)/255.
    return mask, glow, color, (w, h)


def _drops_from_letters(mask, count=6, seed=3):
    rng = np.random.default_rng(seed)
    h, w = mask.shape
    cols = np.where(mask[int(h*.55):].max(0) > .6)[0]
    picks = rng.choice(cols, size=min(count, len(cols)), replace=False) if len(cols) else []
    out = []
    for c in picks:
        rows = np.where(mask[:, c] > .6)[0]
        out.append((int(c), int(rows.max()), rng.uniform(1.25, 1.75), rng.uniform(4, 7)))
    return out


def frames(background):
    """Yield (H, W, 3) uint8 frames. `background` is the edit's last frame."""
    rng = np.random.default_rng(12)
    W, H, FPS = look.W, look.H, look.FPS
    ink = np.zeros((H, W, 3), np.float32)+np.array(look.INK, np.float32)
    bg = background.astype(np.float32)
    blur_bg = np.asarray(Image.fromarray(background).filter(ImageFilter.GaussianBlur(28))).astype(np.float32)
    mask, glow, color, (ww, wh) = _word()
    wx, wy = CENTER[0]-ww//2, CENTER[1]-wh//2-10
    letter_drops = _drops_from_letters(mask)
    crown = [(rng.uniform(-1, 1)*math.pi*.48-math.pi/2, rng.uniform(520, 980), rng.uniform(3, 9)) for _ in range(46)]
    small = look.SANS(30, 600)
    caption = look.text_sprite('EDITED BY', small, fill=(200, 236, 250), tracking=14, shadow=0)
    total = int(DURATION*FPS)
    for n in range(total):
        t = n/FPS
        # 1. the film darkens into ink
        k = _ease(t/.42)
        frame = bg*(1-k)*(1-k*.4)+blur_bg*k*.25+ink*k
        canvas = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).convert('RGBA')
        layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # 2. the drop falls
        if t < IMPACT:
            p = (t/IMPACT)**2
            y = -60+(CENTER[1]+40+60)*p
            stretch = 1+p*1.4
            d.ellipse((CENTER[0]-13, y-13*stretch*1.6, CENTER[0]+13, y+13), fill=AQUA+(235,))
            d.ellipse((CENTER[0]-5, y-8, CENTER[0]+1, y-1), fill=(255, 255, 255, 200))
        else:
            s = t-IMPACT
            # 3. bloom at impact
            if s < .35:
                r = 80+s*900
                a = int(140*(1-s/.35))
                d.ellipse((CENTER[0]-r, CENTER[1]+40-r*.35, CENTER[0]+r, CENTER[1]+40+r*.35), fill=AQUA+(a//3,))
            # 4. ripples
            for j in range(3):
                q = s-j*.16
                if q <= 0: continue
                rx = 40+q*620
                a = int(200*max(0, 1-q/1.4))
                if a <= 0: continue
                d.ellipse((CENTER[0]-rx, CENTER[1]+40-rx*.22, CENTER[0]+rx, CENTER[1]+40+rx*.22), outline=AQUA+(a,), width=3)
            # 5. the crown: drops thrown up and falling back
            for ang, speed, size in crown:
                if s > 1.25: break
                x = CENTER[0]+math.cos(ang)*speed*.55*s
                y = CENTER[1]+40+math.sin(ang)*speed*s+1300*s*s
                a = int(255*max(0, 1-s/1.25))
                r = size*(1-s*.4)
                if a > 0 and r > .5: d.ellipse((x-r, y-r*1.25, x+r, y+r*1.25), fill=(225, 246, 255, a))
        glowing = layer.filter(ImageFilter.GaussianBlur(6))
        canvas = Image.alpha_composite(canvas, glowing)
        canvas = Image.alpha_composite(canvas, layer)
        out = np.asarray(canvas.convert('RGB')).astype(np.float32)
        # 6. "Cascade" writes itself, left to right, with a soft leading edge
        if t > .58:
            reveal = _ease((t-.58)/1.0)
            edge = reveal*(ww+80)-40
            cols = np.clip((edge-np.arange(ww))/40+.5, 0, 1)[None, :]
            lift = (1-_ease((t-.58)/.8))*14
            y0 = int(wy+lift)
            a = mask*cols
            g = glow*cols*.75
            region = out[y0:y0+wh, wx:wx+ww]
            hh, wwr = region.shape[:2]
            a, g, col = a[:hh, :wwr, None], g[:hh, :wwr, None], color[:hh]
            region[:] = region*(1-g*.5)+np.array(AQUA, np.float32)*g*.5
            region[:] = region*(1-a)+col*a
            # drops running off the letters
            if t > 1.45:
                for cx, cy, start, size in letter_drops:
                    q = t-start
                    if q <= 0: continue
                    x, y = wx+cx, y0+cy+q*q*900
                    alpha = max(0, 1-q/1.1)
                    yy, xx = int(y), int(x)
                    r = int(size)
                    if alpha <= 0 or yy+2*r >= H: continue
                    patch = out[yy-2*r:yy+r, xx-r:xx+r]
                    if patch.size: patch[:] = patch*(1-.85*alpha)+np.array((225, 246, 255), np.float32)*.85*alpha
        frame8 = np.clip(out, 0, 255).astype(np.uint8)
        if t > .95:
            look.paste(frame8, caption, CENTER[0], wy-28, alpha=_ease((t-.95)/.5)*.85)
        if t > DURATION-.28:
            frame8 = (frame8*(1-(t-(DURATION-.28))/.28)).astype(np.uint8)
        yield frame8
