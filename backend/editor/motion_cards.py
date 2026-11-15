"""Kinetic hook/quote cards rendered with HyperFrames (open-source HTML-to-video by HeyGen).

Each `motion_card` StyleEvent becomes a transparent PNG sequence at the clip's own size and 30 fps,
cached by content, and is alpha-composited over the footage by stylize.render. HyperFrames runs
through `CASCADE_HYPERFRAMES`, an installed `hyperframes` binary, or `npx hyperframes@0.9.9`.
If it is unavailable the card is skipped and the rest of the edit still renders.
"""
import hashlib
import html
import logging
import os
import shutil
import subprocess
from pathlib import Path

LOG = logging.getLogger(__name__)
VERSION = '0.9.9'
FONTS = {'impact': "Impact,'Arial Black',sans-serif", 'poster': "'Arial Black',Impact,sans-serif", 'grunge': "Impact,sans-serif",
         'typewriter': "'Courier New',monospace", 'script': "Georgia,'Times New Roman',serif"}
PAGE = '''<!doctype html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width={w}, height={h}" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:transparent}}
#root{{width:100%;height:100%;font-family:{font};text-transform:uppercase;{italic}}}
#card{{width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:0 6%}}
.w{{color:#fff;font-size:{size}px;line-height:.95;text-align:center;text-shadow:0 {shadow}px {blur}px rgba(0,0,0,.6)}}
.w.a{{color:{accent}}}
#bar{{width:0;height:{bar}px;background:{accent};margin-top:{gap}px}}
</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{d}" data-width="{w}" data-height="{h}">
<div id="card" class="clip" data-start="0" data-duration="{d}" data-track-index="0">
<div class="w">{lead}</div><div class="w a">{payoff}</div><div id="bar"></div></div></div>
<script>
const tl=gsap.timeline({{paused:true}});
tl.fromTo(".w",{{scale:1.6,opacity:0}},{{scale:1,opacity:1,duration:.22,ease:"power4.out",stagger:.12}},0);
tl.to("#bar",{{width:{barw},duration:.35,ease:"power3.out"}},.3);
tl.to("#root",{{opacity:0,duration:.2}},{fade});
window.__timelines["main"]=tl;tl.seek(0);
</script></body></html>'''


def command():
    custom = os.environ.get('CASCADE_HYPERFRAMES')
    if custom: return [custom]
    found = shutil.which('hyperframes')
    if found: return [found]
    npx = shutil.which('npx')
    return [npx, '--yes', f'hyperframes@{VERSION}'] if npx else None


def page(text, w, h, duration, accent, font):
    words = text.upper().split()
    split = max(1, (len(words)+1)//2)
    lead, payoff = ' '.join(words[:split]), ' '.join(words[split:])
    if not payoff: lead, payoff = '', lead
    longest = max(len(lead), len(payoff), 4)
    size = int(min(w*1.55/longest, h*(.11 if h > w else .17)))
    return PAGE.format(w=w, h=h, d=f'{duration:.3f}', font=FONTS.get(font, FONTS['impact']), italic='font-style:italic;' if font == 'script' else '',
                       size=size, shadow=max(2, size//14), blur=max(8, size//4), accent=accent, bar=max(4, h//96), gap=max(8, h//44),
                       barw=int(w*.6), fade=f'{max(.2, duration-.2):.3f}', lead=html.escape(lead), payoff=html.escape(payoff))


def frames(event, w, h, accent, cache):
    """Sorted RGBA PNG paths for one card, rendered once per (text, size, look); [] if unavailable."""
    markup = page(event.text, w, h, event.duration, accent, event.font)
    key = hashlib.sha256((VERSION+markup).encode()).hexdigest()[:24]  # any design change renders anew
    folder = Path(cache)/'cards'/key
    done = sorted(folder.glob('out/*.png'))
    if done: return done
    cmd = command()
    if not cmd:
        LOG.warning('HyperFrames is not installed (npm i -g hyperframes); motion card skipped')
        return []
    shutil.rmtree(folder, ignore_errors=True); folder.mkdir(parents=True)
    (folder/'index.html').write_text(markup)
    try:
        subprocess.run([*cmd, 'render', str(folder), '--format', 'png-sequence', '-o', str(folder/'out'), '--fps', '30', '--quiet'],
                       capture_output=True, text=True, timeout=300, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        LOG.warning('HyperFrames render failed; motion card skipped: %s', str(getattr(exc, 'stderr', '') or exc)[-300:])
        shutil.rmtree(folder, ignore_errors=True)
        return []
    return sorted(folder.glob('out/*.png'))


class Cards:
    """Per-render lookup: overlay(frame, t) alpha-composites whichever card is active at t."""

    def __init__(self, events, w, h, accent, cache):
        self.items = [(e, frames(e, w, h, e.color or accent, cache)) for e in events]
        self.items = [(e, f) for e, f in self.items if f]
        self._loaded = {}

    def overlay(self, frame, t):
        import numpy as np
        from PIL import Image
        for event, paths in self.items:
            n = int((t-event.start)*30)
            if not 0 <= n < len(paths): continue
            if paths[n] not in self._loaded:
                self._loaded = {paths[n]: np.asarray(Image.open(paths[n]).convert('RGBA'), np.float32)}
            rgba = self._loaded[paths[n]]
            if rgba.shape[:2] != frame.shape[:2]: continue
            alpha = rgba[..., 3:4]/255
            frame = frame*(1-alpha)+rgba[..., :3]*alpha
        return frame
