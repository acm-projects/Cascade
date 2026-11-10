"""The look: colour by meaning, the type system, the grade, and the sprites every word is drawn from.

Type system (from TEXT INSPO): a heavy condensed grotesk (Anton) for giant words, a light italic
serif (Instrument Serif) for the one word that carries the feeling, and a clean sans (Inter)
for everything else. Colour follows meaning and never fills the frame: water and rivers are
blue, forest and life are green, danger and loss are red, money and greed are gold.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).parent/'fonts'
W, H, FPS = 1080, 1920, 30

TONES = {
    'water': (72, 198, 255),
    'life': (88, 227, 140),
    'hope': (126, 240, 196),
    'danger': (255, 64, 52),
    'money': (245, 197, 66),
    'earth': (255, 168, 76),
    'calm': (244, 241, 234),
}
WHITE = (247, 245, 240)
INK = (6, 9, 12)

# Words that pick their own colour when the plan does not say (lower case, stems).
TONE_WORDS = {
    'water': ('water', 'river', 'rain', 'ocean', 'sea', 'flood', 'stream', 'wave', 'ice', 'glacier', 'blue', 'lake', 'swim'),
    'life': ('forest', 'tree', 'jungle', 'rainforest', 'amazon', 'green', 'life', 'alive', 'grow', 'leaf', 'leaves', 'plant',
             'animal', 'jaguar', 'species', 'wild', 'nature', 'breathe', 'oxygen', 'baby', 'mother', 'peace', 'peaceful'),
    'danger': ('fire', 'burn', 'kill', 'die', 'dead', 'death', 'destroy', 'cut', 'chainsaw', 'gone', 'lost', 'loss', 'extinct',
               'crush', 'bite', 'skull', 'danger', 'dangerous', 'blood', 'heat', 'smoke', 'collapse', 'never', 'teeth', 'hungry', 'prey'),
    'money': ('money', 'dollar', 'profit', 'cattle', 'beef', 'gold', 'pay', 'cost', 'rich', 'greed', 'billion', 'million', 'price'),
    'earth': ('earth', 'planet', 'world', 'sun', 'home', 'everyone', 'everything'),
}


def tone_of(word, default='calm'):
    w = word.lower().strip(".,!?'\"")
    for tone, stems in TONE_WORDS.items():
        if any(w.startswith(s) for s in stems): return tone
    return default


@lru_cache(64)
def font(name, size, weight=None):
    f = ImageFont.truetype(str(FONTS/name), size)
    if weight:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


SANS = lambda size, weight=650: font('Inter.ttf', size, weight)
SERIF = lambda size: font('InstrumentSerif-Regular.ttf', size)
ITALIC = lambda size: font('InstrumentSerif-Italic.ttf', size)
HEAVY = lambda size: font('Anton-Regular.ttf', size)
SCRIPT = lambda size: font('MrsSaintDelafield-Regular.ttf', size)


class Sprite:
    """An RGBA image (uint8) and where its anchor sits; `pad`/`ascent` locate the text's left edge and baseline."""
    def __init__(self, rgba, ax=.5, ay=.5, pad=0, ascent=0, width=None):
        self.rgba = rgba
        self.h, self.w = rgba.shape[:2]
        self.ax, self.ay = ax, ay
        self.pad, self.ascent = pad, ascent
        self.width = width if width is not None else self.w  # the text's own width, without padding

    def blurred(self, radius):
        if radius < .5: return self
        img = Image.fromarray(self.rgba).filter(ImageFilter.GaussianBlur(radius))
        return Sprite(np.asarray(img), self.ax, self.ay, self.pad, self.ascent, self.width)

    def baseline(self):
        """The same sprite anchored at the left end of its baseline."""
        return Sprite(self.rgba, self.pad/self.w, (self.pad+self.ascent)/self.h, self.pad, self.ascent, self.width)


def text_sprite(text, f, fill=WHITE, stroke=0, stroke_fill=None, shadow=.55, glow=None, tracking=0, outline_only=False):
    """One run of text as a sprite with a soft shadow (and an optional coloured glow)."""
    pad = max(24, stroke*3, int(f.size*.35))
    if tracking:
        widths = [f.getlength(ch) for ch in text]
        width = int(sum(widths)+tracking*(len(text)-1))
    else:
        width = int(f.getlength(text))
    ascent, descent = f.getmetrics()
    height = ascent+descent
    size = (width+pad*2, height+pad*2)
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    def draw(target, color, sw=stroke, sf=stroke_fill):
        dd = ImageDraw.Draw(target)
        if tracking:
            x = pad
            for ch, wch in zip(text, widths):
                dd.text((x, pad), ch, font=f, fill=color, stroke_width=sw, stroke_fill=sf)
                x += wch+tracking
        else:
            dd.text((pad, pad), text, font=f, fill=color, stroke_width=sw, stroke_fill=sf)
    if outline_only:
        draw(layer, (0, 0, 0, 0), max(2, stroke), fill+(255,) if len(fill) == 3 else fill)
    else:
        draw(layer, fill+(255,) if len(fill) == 3 else fill)
    out = Image.new('RGBA', size, (0, 0, 0, 0))
    if shadow:
        alpha = layer.split()[3].filter(ImageFilter.GaussianBlur(max(4, f.size*.09)))
        shade = Image.new('RGBA', size, (0, 0, 0, 0))
        shade.putalpha(alpha.point(lambda v: int(v*shadow)))
        out = Image.alpha_composite(out, shade.transform(size, Image.AFFINE, (1, 0, 0, 0, 1, -max(2, f.size//28))))
    if glow:
        g = layer.split()[3].filter(ImageFilter.GaussianBlur(f.size*.22))
        tint = Image.new('RGBA', size, glow+(0,))
        tint.putalpha(g.point(lambda v: int(min(255, v*1.3))))
        out = Image.alpha_composite(out, tint)
    out = Image.alpha_composite(out, layer)
    return Sprite(np.asarray(out), pad=pad, ascent=ascent, width=width)


def fit_heavy(text, max_w, max_size=520, min_size=120):
    """The largest heavy-font size that fits `max_w` pixels."""
    size = max_size
    while size > min_size and HEAVY(size).getlength(text) > max_w: size -= 12
    return HEAVY(size)


def paste(frame, sprite, x, y, alpha=1., scale=1.):
    """Alpha-composite `sprite` into `frame` (H, W, 3 uint8) with its anchor at (x, y)."""
    if alpha <= .003: return
    rgba = sprite.rgba
    if abs(scale-1) > .004:
        h, w = rgba.shape[:2]
        nw, nh = max(1, int(w*scale)), max(1, int(h*scale))
        rgba = np.asarray(Image.fromarray(rgba).resize((nw, nh), Image.BILINEAR))
    h, w = rgba.shape[:2]
    x0, y0 = int(round(x-w*sprite.ax)), int(round(y-h*sprite.ay))
    fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(frame.shape[1], x0+w), min(frame.shape[0], y0+h)
    if fx1 <= fx0 or fy1 <= fy0: return
    part = rgba[fy0-y0:fy1-y0, fx0-x0:fx1-x0]
    a = part[..., 3:4].astype(np.float32)*(alpha/255.)
    region = frame[fy0:fy1, fx0:fx1]
    region[:] = (region*(1-a)+part[..., :3]*a).astype(np.uint8)


# FFmpeg colour for every shot as it is decoded (fast, in C). Shadows lean teal, skin stays warm,
# blacks are rich but not crushed; greens are lifted for forest footage.
GRADES = {
    'cinema': "eq=contrast=1.07:saturation=1.06:gamma=0.98,"
              "colorbalance=rs=-0.035:gs=0.0:bs=0.045:rm=0.015:gm=0.0:bm=-0.015:rh=0.035:gh=0.015:bh=-0.03,"
              "curves=master='0/0.025 0.22/0.19 0.5/0.5 0.8/0.82 1/0.97'",
    'forest': "eq=contrast=1.06:saturation=1.18:gamma=0.97,"
              "colorbalance=rs=-0.03:gs=0.02:bs=0.03:rm=-0.01:gm=0.03:bm=-0.01:rh=0.03:gh=0.01:bh=-0.03,"
              "curves=master='0/0.03 0.22/0.19 0.5/0.5 0.8/0.81 1/0.96'",
    'mono': "hue=s=0.08,eq=contrast=1.16:brightness=-0.035:gamma=0.95,curves=master='0/0.02 0.3/0.24 0.7/0.72 1/0.93'",
    'night': "eq=contrast=1.1:saturation=0.85:brightness=-0.04,colorbalance=rs=-0.06:bs=0.08:rm=-0.03:bm=0.05",
}


def vignette(strength=.38):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((x-W/2)/(W*.62))**2+((y-H/2)/(H*.6))**2)
    return (1-strength*np.clip(r-.35, 0, 1)**1.6).astype(np.float32)[..., None]


@lru_cache(1)
def grain_bank(count=8, amount=7):
    rng = np.random.default_rng(3)
    small = rng.normal(0, amount, (count, H//2, W//2, 1)).astype(np.float32)
    return np.repeat(np.repeat(small, 2, 1), 2, 2).astype(np.int16)
