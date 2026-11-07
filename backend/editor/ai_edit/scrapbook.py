"""The scrapbook look (style sheet "Look: scrapbook"), from the owner's references of 2026-11-06:
paper and tape, footage pinned up as photos, handwritten words next to cut-out labels, marker doodles,
and the Cascade wordmark ending (ENDWITHCASCADE.mov) with a leopard-print fill.

Everything here is HTML/CSS/GSAP for HyperFrames; nothing is drawn by hand per edit."""
import math
import random
from urllib.parse import quote


def _leopard():
    """A seamless leopard-print tile as an SVG data URI (fixed seed, so every edit looks the same)."""
    rng = random.Random(7)
    size = 240
    shapes = ['<rect width="240" height="240" fill="#D9A441"/>',
              '<rect width="240" height="240" fill="url(#g)"/>']
    for _ in range(14):  # rosettes: broken dark rings around a warmer centre
        cx, cy, r = rng.uniform(0, size), rng.uniform(0, size), rng.uniform(13, 22)
        for dx in (-size, 0, size):
            for dy in (-size, 0, size):
                x, y = cx+dx, cy+dy
                if not (-40 < x < size+40 and -40 < y < size+40): continue
                shapes.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{r*.72:.1f}" ry="{r*.58:.1f}" fill="#B9772A"/>')
                parts = rng.randint(3, 5)
                start = rng.uniform(0, math.tau)
                for k in range(parts):
                    a = start+k*math.tau/parts+rng.uniform(-.25, .25)
                    px, py = x+math.cos(a)*r, y+math.sin(a)*r*.85
                    shapes.append(f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{r*.46:.1f}" ry="{r*.27:.1f}" '
                                  f'transform="rotate({math.degrees(a)+90:.0f} {px:.1f} {py:.1f})" fill="#24160B"/>')
    for _ in range(26):  # small solid spots between the rosettes
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        shapes.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rng.uniform(4, 8):.1f}" ry="{rng.uniform(3.5, 7):.1f}" fill="#24160B"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"><defs><radialGradient id="g">'
           '<stop offset="0" stop-color="#E8B85A" stop-opacity=".6"/><stop offset="1" stop-color="#C98F37" stop-opacity=".0"/>'
           f'</radialGradient></defs>{"".join(shapes)}</svg>')
    return 'url("data:image/svg+xml,' + quote(svg) + '")'


GRAIN = ('url("data:image/svg+xml,' + quote(
    '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><filter id="n"><feTurbulence type="fractalNoise" '
    'baseFrequency=".9" numOctaves="3" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 .5  0 0 0 0 .45  0 0 0 0 .38  0 0 0 .55 0"/>'
    '</filter><rect width="300" height="300" filter="url(#n)"/></svg>') + '")')


def _torn(flip=False):
    """A torn paper strip (1080 wide) as an SVG data URI."""
    rng = random.Random(3 if flip else 5)
    points, x = [], 0
    while x < 1080:
        points.append(f'{x},{rng.uniform(14, 34):.0f}'); x += rng.uniform(14, 36)
    points.append('1080,22')
    path = f'M0,0 L{" L".join(points)} L1080,0 Z' if not flip else f'M0,60 L{" L".join(p.split(",")[0]+","+str(60-float(p.split(",")[1])) for p in points)} L1080,60 Z'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="60" preserveAspectRatio="none">'
           f'<path d="{path}" fill="#EFE8D6"/></svg>')
    return 'url("data:image/svg+xml,' + quote(svg) + '")'


LEOPARD = _leopard()
PAPER = '#EFE8D6'
RED = '#C81E32'

CSS = f'''
@font-face{{font-family:"Caveat";src:url("assets/fonts/Caveat-Bold.woff2");font-weight:700}}
@font-face{{font-family:"Permanent Marker";src:url("assets/fonts/PermanentMarker.woff2")}}
#root.scrap{{background:{PAPER} {GRAIN}}}
.scrap .grain{{position:absolute;inset:0;z-index:40;pointer-events:none;background:{GRAIN};opacity:.32;mix-blend-mode:multiply}}
.scrap .torn{{position:absolute;left:0;width:1080px;height:60px;z-index:39;background-size:1080px 60px}}
.scrap .torn.top{{top:0;background-image:{_torn()}}}.scrap .torn.bottom{{bottom:0;background-image:{_torn(True)}}}
.scrap .photo{{position:absolute;left:0;top:0;width:1080px;height:1920px;outline:25px solid #FBF8F0;box-shadow:0 30px 60px rgba(0,0,0,.4);transform-origin:50% 45%}}
.scrap .tape{{position:absolute;width:260px;height:72px;background:rgba(236,224,190,.82);box-shadow:0 2px 6px rgba(0,0,0,.18)}}
.scrap .tape.l{{left:-90px;top:-28px;transform:rotate(-32deg)}}.scrap .tape.r{{right:-90px;top:-28px;transform:rotate(34deg)}}
.scrap .pnote{{position:absolute;left:0;right:0;bottom:-118px;text-align:center;font:700 66px/1 "Caveat",cursive;color:#1D1A16}}
.scrap .lead{{font:700 64px/1 "Caveat",cursive;color:#fff;margin-bottom:6px;text-shadow:0 2px 0 rgba(0,0,0,.6),0 3px 14px rgba(0,0,0,.7)}}
.scrap .lead.under{{margin:8px 0 0}}
.scrap .big{{font-size:118px;line-height:1;text-shadow:none;color:#151311}}
.scrap .big .lab{{display:inline-block;padding:.08em .24em .12em;background:#F6F1E3;transform:rotate(-2.2deg);box-shadow:0 10px 22px rgba(0,0,0,.4)}}
.scrap .big .lab.red{{background:{RED};color:#fff;transform:rotate(1.8deg)}}
.scrap .big .lab.ink{{background:#151311;color:#F6F1E3;transform:rotate(-1.2deg)}}
.scrap .doodle{{position:absolute;left:-60px;top:-40px;width:calc(100% + 120px);height:calc(100% + 80px);overflow:visible;pointer-events:none}}
.scrap .doodle path{{fill:none;stroke:{RED};stroke-width:9;stroke-linecap:round}}
.scrap .verdict.paper{{background:{PAPER} {GRAIN}}}
.scrap .verdict.paper .vw{{font-family:"Permanent Marker",cursive;font-stretch:100%;color:{RED};font-size:150px;letter-spacing:0}}
.scrap .verdict.paper .vlead{{font:700 96px/1 "Caveat",cursive;text-transform:none;color:#151311}}
.scrap .note{{display:grid;align-content:center;justify-items:center;background:{PAPER} {GRAIN}}}
.scrap .note p{{max-width:820px;text-align:center;font:700 92px/1.05 "Caveat",cursive;color:#151311;transform:rotate(-2deg)}}
.scrap .note p::after{{content:"";display:block;margin:22px auto 0;width:58%;height:12px;background:{RED};transform:rotate(1deg);border-radius:6px}}
.scrap .wmk{{display:grid;place-items:center;background:#000}}
.scrap .wm{{position:relative;font:800 190px/1 "Bricolage Grotesque",sans-serif;font-stretch:100%;letter-spacing:-.02em}}
.scrap .wm span{{display:block}}
.scrap .wm .fill{{background:{LEOPARD};background-size:190px 190px;-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 1px rgba(36,22,11,.6))}}
.scrap .wm .ghost{{position:absolute;inset:0;opacity:0;mix-blend-mode:screen}}
.scrap .wm .ghost.r{{color:#FF2A4D}}.scrap .wm .ghost.c{{color:#22E5FF}}
'''

CSS += f'''
.scrap .swipe{{position:absolute;top:-40px;left:0;width:1300px;height:2000px;z-index:30;background:{PAPER} {GRAIN};transform:skewX(-12deg);box-shadow:0 0 40px rgba(0,0,0,.35)}}
.scrap .bword{{position:absolute;left:0;right:0;top:260px;text-align:center;font-family:"Bricolage Grotesque",sans-serif;font-weight:800;font-stretch:75%;line-height:.88;letter-spacing:-.02em;color:#F6F1E3;text-shadow:0 8px 40px rgba(0,0,0,.35);white-space:nowrap}}
.scrap .bword.red{{color:{RED}}}
.scrap .cutv{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:50% 45%}}
'''

DOODLE = ('<svg class="doodle" viewBox="0 0 100 100" preserveAspectRatio="none">'
          '<path pathLength="1" d="M8,52 C6,22 40,8 62,12 C88,16 98,40 92,62 C85,86 50,94 26,86 C10,80 4,66 12,44"/></svg>')
