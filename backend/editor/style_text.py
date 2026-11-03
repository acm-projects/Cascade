"""Kinetic fan-edit text: big words in loud fonts that slam, glitch, type or flicker in,
optionally placed behind the subject using its matte. Local Pillow/OpenCV rendering only."""
import math
import os
import re
from functools import lru_cache

from .style_effects import PALETTES, _ease, _glitch

SUPPLEMENTAL = '/System/Library/Fonts/Supplemental/'
FONTS = {  # (file, collection index) candidates per style; Linux falls back to DejaVu
    'impact': [('Impact.ttf', 0)],
    'typewriter': [('AmericanTypewriter.ttc', 1), ('Courier New Bold.ttf', 0)],
    'poster': [('Phosphate.ttc', 1), ('Impact.ttf', 0)],
    'grunge': [('Chalkduster.ttf', 0)],
    'script': [('Brush Script.ttf', 0)],
    'war': [('Copperplate.ttc', 2), ('Rockwell.ttc', 1)],
    'ancient': [('Herculanum.ttf', 0), ('Trattatello.ttf', 0)],
}
STOPWORDS = set('the and that this with from they them their there what when were will would have been just like about into your you our out for are was but not his her its who all can had has one get got'.split())


def font(style, size):
    from PIL import ImageFont
    for name, index in FONTS.get(style, FONTS['impact']) + FONTS['impact']:
        path = SUPPLEMENTAL+name
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size, index=index)
            except OSError:
                continue
    fallback = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    return ImageFont.truetype(fallback, size) if os.path.isfile(fallback) else ImageFont.load_default(size)


@lru_cache(maxsize=24)
def layer(w, h, text, style, palette, seed, scale=1.0, place='center'):
    """Full-frame (rgb float32, alpha float32) for one word or short phrase."""
    import numpy as np
    from PIL import Image, ImageDraw
    primary, secondary, dark, light, accent = PALETTES[palette]
    words = text.upper().split()
    lines = [' '.join(words[:math.ceil(len(words)/2)]), ' '.join(words[math.ceil(len(words)/2):])] if len(text) > 12 and len(words) > 1 else [text.upper()]
    size = int(h*.42*scale/len(lines))
    face = font(style, size)
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))
    while size > 16 and max(probe.textbbox((0, 0), line, font=face)[2] for line in lines) > w*.9:
        size = int(size*.9); face = font(style, size)
    clean = scale < .7  # documentary/podcast emphasis: white type, no tilt
    fill, stroke = ((250, 250, 250), (15, 15, 15)) if clean else [(light, primary), (accent, dark), (primary, light)][seed % 3]
    picture = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)
    heights = [probe.textbbox((0, 0), line, font=face) for line in lines]
    y = h*{'upper': .2, 'lower': .8, 'center': .5 if seed % 4 else .3}[place]-sum(b[3]-b[1] for b in heights)*.55
    for line, box in zip(lines, heights):
        draw.text(((w-box[2])/2, y-box[1]), line, font=face, fill=fill+(255,), stroke_width=max(2, size//18), stroke_fill=stroke+(255,))
        y += (box[3]-box[1])*1.1
    if not clean:
        picture = picture.rotate([-7, 0, 6, -3][seed % 4], resample=Image.BICUBIC, center=(w/2, h/2))
    data = np.asarray(picture, np.float32)
    return data[..., :3], data[..., 3]/255


def apply_text(frame, t, events, palette, matte_at, frame_number):
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    out = frame
    for index, event in events:
        progress = (t-event.start)/event.duration
        if not 0 <= progress < 1 or not event.text: continue
        seed = index*7919+int(event.start*1000)
        rgb, alpha = layer(w, h, event.text, event.font, palette, seed, event.size, event.place)
        rng = np.random.default_rng(seed+frame_number)
        if event.animate == 'slam' and progress < .25:  # oversized, then slams down with a shake
            scale = 1+.7*(1-_ease(progress/.25))
            dx, dy = rng.integers(-w//60-1, w//60+1, 2)
            matrix = np.float32([[scale, 0, (1-scale)*w/2+dx], [0, scale, (1-scale)*h/2+dy]])
            rgb = cv2.warpAffine(rgb, matrix, (w, h)); alpha = cv2.warpAffine(alpha, matrix, (w, h))
        elif event.animate == 'glitch' and progress < .4:
            rgb = _glitch(rgb, rng, 2.2); alpha = np.maximum(alpha, np.roll(alpha, int(w*.02), axis=1)*.6)
        elif event.animate == 'type':
            columns = np.where(alpha.max(axis=0) > .05)[0]
            if len(columns):
                edge = columns[0]+(columns[-1]-columns[0])*min(1, progress/.6)
                alpha = alpha*(np.arange(w) <= edge)[None, :]
        elif event.animate == 'flicker' and progress < .5 and rng.random() < .35:
            continue
        alpha = alpha*min(1, (1-progress)/.12)  # quick fade at the end
        if event.behind:
            alpha = alpha*(1-matte_at(t, w, h))
        a = alpha[..., None]
        out = out*(1-a)+rgb*a
    return out


def keyword(text, used=()):
    words = [re.sub(r"[^A-Za-z0-9'-]", '', word).upper() for word in text.split()]
    words = sorted(dict.fromkeys(w for w in words if len(w) > 3 and w.lower() not in STOPWORDS and w not in used), key=len, reverse=True)
    return words[0] if words else ''


def plan_text(state, cues, beats, palette, title='', limit=8, words=()):
    """Kinetic words on every fourth beat: the strongest word being spoken, else the title."""
    from .advanced_models import StyleEvent
    fonts = ['war', 'typewriter', 'poster', 'impact', 'grunge'] if palette in ('mono', 'gold') \
        else ['impact', 'poster', 'grunge', 'script', 'ancient']
    animations = ['slam', 'glitch', 'type', 'flicker']
    fallback = [w.upper() for w in words] or [w.upper() for w in re.findall(r'[A-Za-z0-9-]{3,}', title)] or ['EPIC']
    events = []; used = set()
    for n, at in enumerate(beats[1::4][:limit]):
        spoken = ' '.join(c['text'] for c in cues if c['start'] <= at+.6 and c['end'] >= at)
        word = keyword(spoken, used) or fallback[n % len(fallback)]
        used.add(word)
        length = min(1.2, max(.6, state.end-at-.05))
        if length < .3: continue
        events.append(StyleEvent(start=round(at, 3), duration=round(length, 3), kind='text', text=word[:40],
                                 font=fonts[n % len(fonts)], animate=animations[n % len(animations)], behind=n % 3 != 2))
    return events
