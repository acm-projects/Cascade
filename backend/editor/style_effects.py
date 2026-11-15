"""Fan-edit frame effects and procedural backgrounds (NumPy/OpenCV/Pillow, all local and free).

Frames are RGB float32 arrays; mattes are float32 0..1 subject masks from segmentation.Mattes.
"""
import math
import os
from functools import lru_cache

MATTE_KINDS = {'bg_swap', 'color_pop', 'shape_reveal', 'outline'}
PALETTES = {  # primary, secondary, dark, light, accent (RGB)
    'spider': ((226, 54, 54), (31, 63, 191), (12, 12, 20), (245, 240, 230), (255, 214, 0)),
    'neon': ((155, 48, 255), (255, 40, 170), (16, 6, 36), (240, 230, 255), (0, 240, 255)),
    'gold': ((255, 140, 0), (120, 40, 0), (10, 8, 6), (255, 236, 200), (255, 200, 60)),
    'mono': ((230, 230, 230), (70, 70, 70), (8, 8, 8), (250, 250, 250), (210, 20, 20)),
}
WORDS = ('POW!', 'BAM!', 'WHAM!', 'ZAP!', 'THWIP!', 'BOOM!', 'KRAK!')
FONT_BOLD = ('/System/Library/Fonts/Supplemental/Impact.ttf', '/Library/Fonts/Impact.ttf',
             '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
FONT_SERIF = ('/System/Library/Fonts/Supplemental/Didot.ttc', '/System/Library/Fonts/Supplemental/Bodoni 72.ttc',
              '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf')


def _font(candidates, size):
    from PIL import ImageFont
    path = next((c for c in candidates if os.path.isfile(c)), None)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


def _ease(x):
    return 1-(1-min(1.0, max(0.0, x)))**3


@lru_cache(maxsize=24)
def _halftone_screen(w, h, spacing):
    import cv2
    import numpy as np
    screen = np.zeros((h, w), np.float32)
    for y in range(0, h+spacing, spacing):
        for x in range((y//spacing % 2)*spacing//2, w+spacing, spacing):
            radius = spacing*(.25+.3*((x/w+y/h)/2))
            cv2.circle(screen, (x, y), max(1, int(radius)), 1, -1, cv2.LINE_AA)
    return screen


@lru_cache(maxsize=24)
def _comic(w, h, seed, palette):
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(seed)
    primary, secondary, dark, light, accent = PALETTES[palette]
    base, dots = (primary, secondary) if seed % 2 == 0 else (secondary, primary)
    image = np.empty((h, w, 3), np.float32); image[:] = base
    cx, cy = rng.uniform(.25, .75)*w, rng.uniform(.25, .75)*h
    rays = np.zeros((h, w), np.uint8)
    count = 18
    for i in range(count):
        a0 = 2*math.pi*i/count; a1 = a0+math.pi/count
        r = 2*max(w, h)
        cv2.fillPoly(rays, [np.array([[cx, cy], [cx+r*math.cos(a0), cy+r*math.sin(a0)], [cx+r*math.cos(a1), cy+r*math.sin(a1)]], np.int32)], 1)
    image[rays == 1] = image[rays == 1]*.8+np.array(light, np.float32)*.2
    screen = _halftone_screen(w, h, max(8, h//28))[..., None]
    image = image*(1-screen*.55)+np.array(dots, np.float32)*screen*.55
    picture = Image.fromarray(image.clip(0, 255).astype(np.uint8))
    word = WORDS[seed % len(WORDS)]
    font = _font(FONT_BOLD, max(24, h//4))
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    box = draw.textbbox((0, 0), word, font=font, stroke_width=max(2, h//60))
    tx = rng.uniform(.05, .95)*w-(box[2]-box[0])/2; ty = rng.uniform(.08, .5)*h
    draw.text((tx, ty), word, font=font, fill=accent+(255,), stroke_width=max(2, h//60), stroke_fill=dark+(255,))
    layer = layer.rotate(rng.uniform(-14, 14), center=(tx+(box[2]-box[0])/2, ty+(box[3]-box[1])/2), resample=Image.BICUBIC)
    picture.paste(layer, (0, 0), layer)
    return np.asarray(picture, np.float32)


@lru_cache(maxsize=24)
def _paper(w, h, seed, palette):
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    primary, secondary, dark, light, accent = PALETTES[palette]
    image = np.empty((h, w, 3), np.float32); image[:] = light
    image += rng.normal(0, 6, (h, w, 1)).astype(np.float32)
    step = max(12, h//24)
    for y in range(0, h, step): cv2.line(image, (0, y), (w, y), (190, 205, 225), 1, cv2.LINE_AA)
    for _ in range(14):  # newsprint text blocks
        x, y = int(rng.uniform(0, w*.85)), int(rng.uniform(0, h*.9))
        bw = int(rng.uniform(.1, .3)*w)
        for line in range(int(rng.integers(3, 8))):
            cv2.line(image, (x, y+line*step//2), (x+int(bw*rng.uniform(.6, 1)), y+line*step//2), (110, 110, 110), max(1, h//300), cv2.LINE_AA)
    for _ in range(9):  # ink scribbles
        points = np.cumsum(rng.normal(0, h/14, (12, 2)), 0)+[rng.uniform(0, w), rng.uniform(0, h)]
        cv2.polylines(image, [points.astype(np.int32)], False, primary, max(2, h//160), cv2.LINE_AA)
    return image.clip(0, 255)


def _speedlines(w, h, seed, palette, t):
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed*1000+int(t*15))
    primary, secondary, dark, light, accent = PALETTES[palette]
    image = np.empty((h, w, 3), np.float32); image[:] = dark
    cx, cy = w/2, h/2; r = max(w, h)
    for _ in range(110):
        a = rng.uniform(0, 2*math.pi); spread = rng.uniform(.004, .018); inner = rng.uniform(.12, .45)*r*.5
        color = light if rng.random() < .7 else primary
        tri = np.array([[cx+inner*math.cos(a), cy+inner*math.sin(a)], [cx+r*math.cos(a-spread), cy+r*math.sin(a-spread)],
                        [cx+r*math.cos(a+spread), cy+r*math.sin(a+spread)]], np.int32)
        cv2.fillPoly(image, [tri], color, cv2.LINE_AA)
    return image


def _neon(w, h, seed, palette, t):
    import numpy as np
    rng = np.random.default_rng(seed*1000+int(t*12))
    primary, secondary, dark, light, accent = PALETTES[palette]
    ramp = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    image = np.broadcast_to(np.array(primary, np.float32)*(1-ramp)+np.array(secondary, np.float32)*ramp, (h, w, 3)).copy()*.85
    for _ in range(int(rng.integers(5, 10))):
        x = int(rng.uniform(0, w)); bw = int(rng.uniform(.01, .08)*w)
        image[:, x:x+bw] = image[:, x:x+bw]*.4+np.array(accent if rng.random() < .4 else dark, np.float32)*.6
    image[::4] *= .78
    return image


def _halftone_frame(frame, palette):
    import cv2
    import numpy as np
    primary, secondary, dark, light, accent = PALETTES[palette]
    h, w = frame.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(frame.astype(np.uint8), cv2.COLOR_RGB2GRAY), (0, 0), 3).astype(np.float32)/255
    duo = np.array(dark, np.float32)*(1-gray[..., None])+np.array(primary, np.float32)*gray[..., None]
    screen = _halftone_screen(w, h, max(6, h//60))[..., None]
    return duo*(1-screen*.35)+np.array(light, np.float32)*screen*.35*gray[..., None]


def _blurred(frame, palette):
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (max(2, w//10), max(2, h//10)), interpolation=cv2.INTER_AREA)
    tint = np.array(PALETTES[palette][2], np.float32)
    return cv2.resize(cv2.GaussianBlur(small, (0, 0), 3), (w, h))*.55+tint*.45


def background(kind, frame, t, seed, palette):
    h, w = frame.shape[:2]
    if kind == 'comic': return _comic(w, h, seed, palette)
    if kind == 'paper': return _paper(w, h, seed, palette)
    if kind == 'speedlines': return _speedlines(w, h, seed, palette, t)
    if kind == 'neon': return _neon(w, h, seed, palette, t)
    if kind == 'halftone': return _halftone_frame(frame, palette)
    return _blurred(frame, palette)


def _outline(image, matte, palette, strength=1.0, glow=True):
    import cv2
    import numpy as np
    h = image.shape[0]
    solid = (matte > .5).astype(np.uint8)
    radius = max(2, int(h/110*strength))
    ring = cv2.dilate(solid, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1)))-solid
    ring = cv2.GaussianBlur(ring.astype(np.float32), (0, 0), 1)[..., None]
    primary, secondary, dark, light, accent = PALETTES[palette]
    if glow:
        halo = cv2.GaussianBlur(ring[..., 0], (0, 0), max(3, h/50))[..., None]*(1-matte[..., None])
        image = image+np.array(primary, np.float32)*halo*1.4
    return image*(1-ring)+np.array(light, np.float32)*ring


def _shape(kind, w, h, progress, seed):
    import cv2
    import numpy as np
    canvas = np.zeros((h, w), np.uint8)
    grow = _ease(progress*2.5)
    cx, cy = w/2, h/2; r = math.hypot(w, h)*.6*grow
    if r < 2: return canvas.astype(np.float32)
    if kind == 'star':
        points = [(cx+(r if i % 2 == 0 else r*.45)*math.cos(math.pi/2+i*math.pi/5+seed), cy-(r if i % 2 == 0 else r*.45)*math.sin(math.pi/2+i*math.pi/5+seed)) for i in range(10)]
        cv2.fillPoly(canvas, [np.array(points, np.int32)], 1, cv2.LINE_AA)
    elif kind == 'slash':
        band = .35*w*grow
        cv2.fillPoly(canvas, [np.array([[cx-band-w*.3, h], [cx-band+w*.3, 0], [cx+band+w*.3, 0], [cx+band-w*.3, h]], np.int32)], 1, cv2.LINE_AA)
    else:
        thick = max(2, int(.22*min(w, h)*grow+.06*min(w, h)))
        cv2.line(canvas, (int(cx-r), int(cy-r)), (int(cx+r), int(cy+r)), 1, thick, cv2.LINE_AA)
        cv2.line(canvas, (int(cx-r), int(cy+r)), (int(cx+r), int(cy-r)), 1, thick, cv2.LINE_AA)
    return canvas.astype(np.float32)


def _glitch(image, rng, strength):
    import numpy as np
    h, w = image.shape[:2]
    shift = max(2, int(w*.012*strength*(.5+rng.random())))
    out = image.copy()
    out[..., 0] = np.roll(image[..., 0], shift, axis=1)
    out[..., 2] = np.roll(image[..., 2], -shift, axis=1)
    for _ in range(int(rng.integers(3, 8))):
        y = int(rng.uniform(0, h)); bh = int(rng.uniform(.01, .07)*h)
        out[y:y+bh] = np.roll(out[y:y+bh], int(rng.uniform(-.06, .06)*w*strength), axis=1)
    out[::3] *= .85
    return out


def _ink(image, palette):
    import cv2
    import numpy as np
    gray = cv2.cvtColor(image.clip(0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 0, 1, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    primary, secondary, dark, light, accent = PALETTES[palette]
    b = binary.astype(np.float32)[..., None]
    return np.array(light, np.float32)*b+np.array(dark, np.float32)*(1-b)


def _zoom_blur(image, amount):
    import cv2
    import numpy as np
    h, w = image.shape[:2]
    if amount < .005: return image
    total = image.copy(); samples = 6
    for k in range(1, samples):
        scale = 1+amount*k/(samples-1)
        cw, ch = int(w/scale), int(h/scale); x, y = (w-cw)//2, (h-ch)//2
        total += cv2.resize(image[y:y+ch, x:x+cw], (w, h), interpolation=cv2.INTER_LINEAR)
    return total/samples


def _title_card(w, h, text, palette, progress, rng, frame):
    import numpy as np
    card = _card(w, h, text, palette)
    if progress < .35:  # glitch-in reveal
        card = _glitch(card, rng, 2.5*(1-progress/.35))
    fade = _ease(progress/.15)
    return frame*(1-fade)+card*fade


@lru_cache(maxsize=8)
def _card(w, h, text, palette):
    import numpy as np
    from PIL import Image, ImageDraw
    primary, secondary, dark, light, accent = PALETTES[palette]
    color = PALETTES['gold'][0] if palette == 'spider' else primary
    picture = Image.new('RGB', (w, h), dark)
    draw = ImageDraw.Draw(picture)
    small = _font(FONT_SERIF, max(14, h//22)); big = _font(FONT_BOLD, max(24, h//7))
    name = (text or 'Cascade').upper()
    while big.size > 20 and draw.textbbox((0, 0), name, font=big)[2] > w*.86:
        big = _font(FONT_BOLD, int(big.size*.9))
    top = draw.textbbox((0, 0), 'Edited by', font=small); main = draw.textbbox((0, 0), name, font=big)
    y = h/2-(main[3]-main[1])/2
    draw.text(((w-top[2])/2, y-(top[3]-top[1])*1.6), 'Edited by', font=small, fill=light)
    draw.text(((w-main[2])/2, y), name, font=big, fill=color)
    return np.asarray(picture, np.float32)


def apply_events(frame, t, events, palette, matte_at, frame_number):
    """Composite every event active at time t (seconds) onto an RGB float frame."""
    import numpy as np
    h, w = frame.shape[:2]
    out = frame
    matte = None
    for index, event in events:
        progress = (t-event.start)/event.duration
        if not 0 <= progress < 1: continue
        seed = index*7919+int(event.start*1000)
        rng = np.random.default_rng(seed+frame_number)
        if event.kind in MATTE_KINDS and matte is None:
            matte = matte_at(t, w, h)
        if event.kind == 'bg_swap':
            m = matte[..., None]
            out = out*m+background(event.background, frame, t, seed, palette)*(1-m)
            if event.background in ('comic', 'neon', 'speedlines', 'paper'):
                out = _outline(out, matte, palette, event.strength, glow=event.background != 'paper')
        elif event.kind == 'color_pop':
            gray = (frame @ np.array([.299, .587, .114], np.float32))[..., None]
            gray = (gray-128)*1.15+128
            m = matte[..., None]
            out = out*m+np.repeat(gray, 3, axis=2)*(1-m)
        elif event.kind == 'shape_reveal':
            region = (_shape(event.shape, w, h, progress, seed % 7)*(1-matte))[..., None]
            out = out*(1-region)+background(event.background, frame, t, seed, palette)*region
        elif event.kind == 'outline':
            out = _outline(out, matte, palette, event.strength)
        elif event.kind == 'ink':
            out = _ink(out, palette)
        elif event.kind == 'glitch':
            out = _glitch(out, rng, event.strength)
        elif event.kind == 'zoom_blur':
            out = _zoom_blur(out, .2*event.strength*math.sin(math.pi*progress))
        elif event.kind == 'whip':
            import cv2
            length = int(w*.12*event.strength*math.sin(math.pi*progress))+1
            if length > 2: out = cv2.blur(out, (length, 1))
        elif event.kind == 'flash':
            a = min(1, (1-progress)**2*.85*event.strength)
            out = out*(1-a)+255*a
        elif event.kind == 'title_card':
            out = _title_card(w, h, event.text, palette, progress, rng, out)
    return out
