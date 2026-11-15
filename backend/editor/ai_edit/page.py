"""The composition HyperFrames renders: captions, graphics and the plate. Words appear on their spoken frame."""
import html
import re

from . import scrapbook

CLEAN = re.compile(r'[.,;:!"“”]+$')
FILLER = {'a', 'an', 'the', 'of', 'or', 'and', 'but', 'is', 'are', 'was', 'were', 'be', 'it', "it's", 'its', 'that', 'this', 'so', 'to',
          'in', 'on', 'at', 'for', 'with', 'they', "they're", 'he', 'she', "he's", "she's", 'we', 'you', 'i', 'my', 'your', 'their',
          'his', 'her', 'them', 'just', 'like', 'um', 'uh', 'very', 'really', 'do', 'does', 'did', 'have', 'has', 'if', 'as'}


def _plain(word):
    return re.sub(r"[^\w']", '', word.lower().replace('’', "'"))
ENDS = re.compile(r'[.!]["”]?$')

CSS = '''@font-face{font-family:"Bricolage Grotesque";src:url("assets/fonts/BricolageGrotesque.ttf");font-weight:200 800;font-stretch:75% 100%}
@font-face{font-family:"Instrument Sans";src:url("assets/fonts/InstrumentSans.ttf");font-weight:400 700;font-stretch:75% 100%}
@font-face{font-family:"Instrument Serif";src:url("assets/fonts/InstrumentSerif-Italic.ttf");font-style:italic}
:root{--blue:#3D4EFF;--ink:#0C0D13;--bone:#EDEEE8;--flare:#FF6A3D;--mark:#D3203A;--paper:#F4EFE2}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden;background:var(--ink)}
#root{position:relative;width:1080px;height:1920px;overflow:hidden;background:var(--ink);font-family:"Instrument Sans",sans-serif;color:var(--bone)}
#plate{position:absolute;left:0;top:0;width:1080px;height:1920px}
.lay{position:absolute;inset:0}.dim{background:linear-gradient(180deg,rgba(12,13,19,0) 35%,rgba(12,13,19,.42) 55%,rgba(12,13,19,.42) 75%,rgba(12,13,19,0) 90%)}
.disc{position:absolute;z-index:5;left:160px;top:250px;width:760px;height:760px;border-radius:50%;object-fit:cover}
.disc.blue{background:var(--blue)}.disc.flare{background:var(--flare)}
.closing{position:absolute;left:40px;top:460px;width:1000px;height:1000px;border-radius:50%;object-fit:cover}
.stopdot{position:absolute;left:505px;top:925px;width:70px;height:70px;border-radius:50%;background:var(--flare)}
.reset{position:absolute;inset:0;background:var(--bone)}
.cap{position:absolute;left:108px;width:820px;top:1090px;text-align:center}
.lead{font:700 50px/1.05 "Instrument Sans",sans-serif;color:#fff;margin-bottom:-6px;text-shadow:0 2px 0 rgba(0,0,0,.55),0 3px 16px rgba(0,0,0,.75)}
.lead.under{margin:-6px 0 0}
.wd{display:inline-block;margin:0 7px}
.big{position:relative;isolation:isolate;display:inline-block;font:800 150px/.95 "Bricolage Grotesque",sans-serif;font-stretch:88%;letter-spacing:-.012em;color:#fff;white-space:nowrap;text-shadow:0 4px 0 rgba(0,0,0,.45),0 6px 28px rgba(0,0,0,.7)}
.big .mk{position:absolute;z-index:-1;left:-.06em;right:-.06em;bottom:.04em;height:.3em;background:var(--mark);transform-origin:left center}
.pt{display:inline-block;width:.2em;height:.2em;border-radius:50%;margin-left:.06em;vertical-align:baseline;background:var(--blue)}
.pt.flare{background:var(--flare)}
.src{position:absolute;left:108px;width:820px;top:1050px;text-align:center;font:500 30px/1.25 "Instrument Sans",sans-serif;color:var(--bone);text-shadow:0 2px 12px rgba(0,0,0,.9)}
.ntop{position:absolute;left:108px;width:820px;top:640px;text-align:center;font:600 50px/1.2 "Instrument Sans",sans-serif;text-shadow:0 2px 18px rgba(0,0,0,.7)}
.num{position:absolute;left:108px;width:820px;top:710px;text-align:center;font:800 270px/1 "Bricolage Grotesque",sans-serif;font-stretch:75%;letter-spacing:-.03em;color:var(--bone);white-space:nowrap;text-shadow:0 6px 40px rgba(0,0,0,.55)}
.verdict{display:grid;align-content:center;justify-items:center;padding:0 151px 120px 108px;text-align:center}
.vlead{font:800 120px/.95 "Bricolage Grotesque",sans-serif;font-stretch:75%;letter-spacing:-.02em;text-transform:uppercase}
.vlead .wd{margin:0 14px}
.vw{font:800 215px/.95 "Bricolage Grotesque",sans-serif;font-stretch:75%;letter-spacing:-.02em;color:var(--bone)}
.verdict.paper{background:var(--paper);color:var(--ink)}.verdict.paper .vw{color:var(--mark);font-stretch:85%;font-size:170px}.verdict.paper .vlead{color:var(--ink)}
.verdict.paper .pt.flare{background:var(--ink)}
.label{position:absolute;left:60px;top:190px;font:500 28px/1.2 "Instrument Sans",sans-serif;color:var(--bone);text-shadow:0 2px 10px rgba(0,0,0,.9)}
.endc{display:grid;align-content:center;justify-items:center;padding:0 151px 160px 108px;text-align:center;gap:26px}
.eline{font:italic 400 64px/1.15 "Instrument Serif",serif;max-width:820px;text-wrap:balance}
.ecred{position:absolute;left:0;right:0;bottom:120px;text-align:center;font:500 24px/1.35 "Instrument Sans",sans-serif;color:#7E8193}
.otitle{position:absolute;left:0;right:0;top:820px;text-align:center;font:600 34px/1 "Instrument Sans",sans-serif;letter-spacing:.42em;text-transform:uppercase;color:var(--bone);text-shadow:0 2px 16px rgba(0,0,0,.7)}
.fadeout{position:absolute;inset:0;background:var(--ink)}
.ebrand{position:absolute;left:0;right:0;bottom:330px;display:flex;justify-content:center}
.ebrand .stk{display:flex;align-items:baseline;gap:18px;padding:22px 40px 26px;background:var(--mark);border-radius:10px;transform:rotate(-4deg);box-shadow:0 10px 30px rgba(0,0,0,.45);font:italic 400 58px/1 "Instrument Serif",serif;color:#fff;white-space:nowrap}
.ebrand b{font:800 84px/1 "Bricolage Grotesque",sans-serif;font-style:normal;font-stretch:85%;letter-spacing:.02em;color:#fff}
'''


def build(plan, layout, has_closing, has_mix, credits, look='point', behind=()):
    """Returns (html, dot landing times). look: "point" (the original sheet) or "scrapbook".
    behind: [(start, end, word, cut-out file)] for words behind the speaker (scrapbook only)."""
    elements, tweens, dots, count = [], [], [], [0]
    scrap = look == 'scrapbook'
    heroes = [0]  # scrapbook labels take turns: cream, red, ink; every 4th gets a marker circle
    behind = list(behind) if scrap else []
    hero_times = []  # when key words land: the picture punches in on them
    in_behind = lambda t: any(a-.06 <= t < b for a, b, _, _ in behind)

    def nid():
        count[0] += 1
        return f'e{count[0]}'

    def clip(cls, start, end, inner='', style=''):
        i = nid()
        elements.append(f'<div id="{i}" class="clip {cls}" data-start="{start:.4f}" data-duration="{end-start:.4f}" style="{style}">{inner}</div>')
        return i

    def show(i, t):
        tweens.append(f'tl.fromTo("#{i}",{{opacity:0}},{{opacity:1,duration:{2/30:.4f},ease:"none"}},{t:.4f});')

    def dot(t, color):
        lands = min((t+6/30+i/30 for i in range(5)), key=lambda c: abs(c/layout.beat-round(c/layout.beat)))
        dots.append(lands)
        i = nid()
        tweens.append(f'tl.fromTo("#{i}",{{scale:0}},{{scale:1,duration:{6/30:.4f},ease:"power3.out"}},{lands:.4f});')
        return f'<i id="{i}" class="pt {color}"></i>'

    def word(text, t):
        i = nid()
        if scrap: tweens.append(f'tl.fromTo("#{i}",{{opacity:0,y:16,scale:.85}},{{opacity:1,y:0,scale:1,duration:{5/30:.4f},ease:"back.out(2.4)"}},{t:.4f});')
        else: show(i, t)
        return f'<span id="{i}" class="wd">{html.escape(CLEAN.sub("", text))}</span>'

    def hero(text, t, color, with_dot=False, marker=False):
        i = nid()
        tweens.append(f'tl.fromTo("#{i}",{{opacity:0}},{{opacity:1,duration:{3/30:.4f},ease:"none"}},{t:.4f});')
        tweens.append(f'tl.fromTo("#{i}",{{scale:1.1}},{{scale:1,duration:{8/30:.4f},ease:"power3.out"}},{t:.4f});')
        mark = ''
        if scrap:
            n = heroes[0]; heroes[0] += 1
            plain = CLEAN.sub('', text)
            size = f' style="font-size:{min(118, int(1000/max(len(plain), 1)))}px"' if len(plain) > 8 else ''
            doodle = ''
            if n % 4 == 3:
                d = nid(); doodle = scrapbook.DOODLE.replace('<path ', f'<path id="{d}" ', 1)
                tweens.append(f'tl.fromTo("#{d}",{{strokeDasharray:1,strokeDashoffset:1}},{{strokeDashoffset:0,duration:.35,ease:"power2.out"}},{t+.12:.4f});')
            variant = ('', 'red', 'ink')[n % 3]
            tweens.append(f'tl.fromTo("#{i} .lab",{{rotation:{-9 if n % 2 else 9}}},{{rotation:{-2.2 if n % 2 == 0 else 1.8},duration:{9/30:.4f},ease:"back.out(3)"}},{t:.4f});')
            return f'<div id="{i}" class="big"{size}><span class="lab {variant}">{html.escape(plain)}</span>{doodle}</div>'
        if marker:
            m = nid(); mark = f'<i id="{m}" class="mk"></i>'
            tweens.append(f'tl.fromTo("#{m}",{{scaleX:0}},{{scaleX:1,duration:{6/30:.4f},ease:"power2.out"}},{t+2/30:.4f});')
        closes = with_dot and bool(ENDS.search(text))  # ordinary captions get no dot; a full stop on every line looked like periods everywhere
        plain = CLEAN.sub('', text)
        size = f' style="font-size:{min(150, int(1300/max(len(plain), 1)))}px"' if len(plain) > 8 else ''
        return f'<div id="{i}" class="big"{size}>{mark}{html.escape(plain)}{dot(t, color) if closes else ""}</div>'

    def colour(part):
        return 'flare' if part in ('loss', 'cost') else 'blue'

    def on_ink(t):
        return next((e.kind in ('ink', 'dot') for e in layout.events if e.start <= t < e.end), False)

    def phrases(line):
        spec = line['plan'].phrases
        first = line['plan'].from_word
        if spec:
            out = []
            for p in spec:
                a, z, h = p.from_word-first, p.to_word-first, None if p.hero is None else p.hero-first
                if h is not None and _plain(line['words'][h][0]) in FILLER:
                    real = [i for i in range(a, z+1) if _plain(line['words'][i][0]) not in FILLER]
                    h = max(real, key=lambda i: len(line['words'][i][0])) if real else None
                out.append((a, z, h))
            return out
        size, out, n = 4, [], len(line['words'])
        for a in range(0, n, size):
            z = min(a+size, n)-1
            out.append((a, z, max(range(a, z+1), key=lambda i: len(line['words'][i][0]))))
        return out

    def caption(line, a, z, h, until):
        words = line['words']
        color = colour(line['plan'].part)
        lead = ''.join(word(words[i][0], words[i][1]) for i in range(a, h if h is not None else z+1))
        if h is not None: hero_times.append(words[h][1])
        if h is not None and in_behind(words[h][1]): h_shown = None
        else: h_shown = h
        big = hero(words[h][0], words[h][1], color, marker=plan.mode == 'talk' and not scrap) if h_shown is not None else ''
        under = ''.join(word(words[i][0], words[i][1]) for i in range(h+1, z+1)) if h is not None else ''
        inner = (f'<div class="lead">{lead}</div>' if lead else '')+big+(f'<div class="lead under">{under}</div>' if under else '')
        start = words[a][1]-.02
        clip('lay'+('' if on_ink(words[a][1]) else ' dim'), start, until, f'<div class="cap">{inner}</div>')

    # scrapbook: cutaways are pinned up as taped photos on paper; the speaker stays full frame
    if scrap:
        tweens.append('tl.set("#plate",{scale:1,rotation:0,transformOrigin:"50% 45%"},0);')
        tilt = 1
        for e in layout.events:
            if e.kind not in ('stock', 'source', 'band') or e.end-e.start < .7 or e.start >= layout.end_card: continue
            tilt = -tilt; r = 2.4*tilt
            tweens.append(f'tl.set("#plate",{{rotation:{r}}},{e.start:.4f});')
            tweens.append(f'tl.fromTo("#plate",{{scale:.87}},{{scale:.8,duration:.22,ease:"power3.out"}},{e.start:.4f});')
            tweens.append(f'tl.set("#plate",{{scale:1,rotation:0}},{min(e.end, layout.end_card):.4f});')
            # the white border and tape move exactly with the footage: same origin, scale and tilt
            frame = clip('photo', e.start, min(e.end, layout.end_card), '<i class="tape l"></i><i class="tape r"></i>')
            tweens.append(f'tl.fromTo("#{frame}",{{scale:.87,rotation:{r}}},{{scale:.8,rotation:{r},duration:.22,ease:"power3.out"}},{e.start:.4f});')
    # the dot as the planet
    earth_offset = 0
    for e in layout.events:
        if e.kind != 'dot': continue
        if plan.mode == 'earth' and colour(e.part) == 'blue':
            elements.append(f'<video id="{nid()}" class="clip disc" src="assets/earth.mp4" muted data-start="{e.start:.4f}" data-duration="{e.end-e.start:.4f}" data-media-start="{earth_offset:.2f}"></video>')
            earth_offset = (earth_offset+1.7) % 5
        else:
            clip(f'disc {colour(e.part)}', e.start, e.end)
    if layout.closing and has_closing:
        i = nid()
        elements.append(f'<video id="{i}" class="clip closing" src="assets/closing.mp4" muted data-start="{layout.closing[0]:.4f}" data-duration="{layout.closing[1]-layout.closing[0]:.4f}" data-media-start="0"></video>')
        shrink = min(.8, layout.closing[1]-layout.closing[0])
        tweens.append(f'tl.fromTo("#{i}",{{scale:1,opacity:1}},{{scale:.07,opacity:.9,duration:{shrink:.4f},ease:"power2.inOut"}},{layout.closing[1]-shrink:.4f});')
    if layout.silence and plan.mode == 'earth': clip('stopdot', layout.silence[0], max(layout.silence[1], layout.silence[0]+.1))
    if layout.reset: clip('reset', *layout.reset)
    # lines
    for n, line in enumerate(layout.lines):
        spec = line['plan']; words = line['words']
        next_start = layout.lines[n+1]['t'] if n+1 < len(layout.lines) else layout.end_card
        hold = min(line['end']+.45, next_start-.02)
        if spec.verdict:
            stop = layout.reset[0] if layout.reset and layout.reset[0] > line['t'] else next_start
            caps = len(words)-(min(3, len(words)) if not spec.phrases else spec.phrases[-1].to_word-spec.phrases[-1].from_word+1)
            caps = max(caps, len(words)-3)
            chunks = [words[i:i+5] for i in range(0, caps, 5)]
            for j, chunk in enumerate(chunks):
                until = chunks[j+1][0][1] if j+1 < len(chunks) else words[caps][1]
                clip('lay verdict'+(' paper' if plan.mode == 'talk' or scrap else ''), chunk[0][1]-.02, until-.02, '<div class="vlead">'+''.join(word(w, t) for w, t, _ in chunk)+'</div>')
            big = ''
            for position, (w, t, _) in enumerate(words[caps:], caps):
                i = nid(); show(i, t)
                final = position == len(words)-1 and ENDS.search(w) is not None
                big += f'<div id="{i}" class="vw">{html.escape(CLEAN.sub("", w).upper())}{dot(t, "flare") if final and not scrap else ""}</div>'
            clip('lay verdict'+(' paper' if plan.mode == 'talk' or scrap else ''), words[caps][1]-.02, stop, big)
            continue
        numbered = len(words)
        if spec.number:
            numbered = max(0, spec.number.from_word-spec.from_word)
        parts = [(a, min(z, numbered-1), h if h is None or h < numbered else None) for a, z, h in phrases(line) if a < numbered]
        for j, (a, z, h) in enumerate(parts):
            following = parts[j+1][0] if j+1 < len(parts) else None
            until = words[following][1]-.02 if following is not None else (words[numbered][1]-.02 if numbered < len(words) else hold)
            if until > words[a][1]: caption(line, a, z, h, until)
        if spec.number and numbered < len(words):
            at = words[numbered][1]
            i = nid(); show(i, at)
            s = nid(); show(s, at)
            closes = ''
            clip('lay'+('' if on_ink(at) else ' dim'), at-.02, hold,
                 f'<div id="{i}" class="num">{html.escape(spec.number.text)}{closes}</div><div id="{s}" class="src">{html.escape(spec.number.source)}</div>')
    # a small spaced-out title over the opening shot, then it fades (ref "Rhythm of the wild")
    first = layout.lines[0]['t'] if layout.lines else 0
    if plan.title and plan.title != 'Edit' and first >= .8:
        title = nid()
        tweens.append(f'tl.fromTo("#{title}",{{opacity:0,letterSpacing:".6em"}},{{opacity:1,letterSpacing:".42em",duration:.7,ease:"power2.out"}},.1);')
        tweens.append(f'tl.to("#{title}",{{opacity:0,duration:.35,ease:"power1.in"}},{max(.6, first-.4):.4f});')
        elements.append(f'<div id="{title}" class="clip otitle" data-start="0" data-duration="{first:.4f}">{html.escape(plan.title)}</div>')
    # the footage fades to black into the end card instead of cutting
    fade = min(.6, max(.2, layout.end_card-(layout.lines[-1]['end'] if layout.lines else 0)))
    if layout.end_card > fade and not scrap:
        dark = clip('fadeout', layout.end_card-fade, layout.end_card+.05)
        tweens.append(f'tl.fromTo("#{dark}",{{opacity:0}},{{opacity:1,duration:{fade:.4f},ease:"power1.inOut"}},{layout.end_card-fade:.4f});')
    # credit and end card
    if plan.credit:
        a = 0
        for start, stop in ([layout.reset] if layout.reset else []):
            clip('label', a, start, html.escape(plan.credit)); a = stop
        clip('label', a, layout.end_card, html.escape(plan.credit))
    start = layout.end_card
    if scrap:
        _scrap_ending(plan, layout, start, clip, nid, tweens, credits)
        start = layout.total  # the scrapbook ending replaces the end card below
    if not scrap:
        inner = hero(plan.end_hero, start+.05, 'blue') if plan.end_hero else ''
        if plan.end_line:
            line = nid()
            tweens.append(f'tl.fromTo("#{line}",{{opacity:0,y:18}},{{opacity:1,y:0,duration:.8,ease:"power2.out"}},{start+.35:.4f});')
            inner += f'<div id="{line}" class="eline">{html.escape(CLEAN.sub("", plan.end_line))}</div>'
        if credits: inner += '<div class="ecred">'+'<br>'.join(html.escape(c) for c in credits)+'</div>'
        brand = nid()
        tweens.append(f'tl.fromTo("#{brand}",{{opacity:0,scale:1.25}},{{opacity:1,scale:1,duration:.45,ease:"back.out(2)"}},{start+.7:.4f});')
        inner += f'<div id="{brand}" class="ebrand"><div class="stk"><span>Edited by</span><b>Cascade</b></div></div>'
        clip('lay endc', start, layout.total, inner)
    if scrap:
        _scrap_motion(layout, hero_times, behind, clip, nid, tweens, elements)
    if scrap:  # paper grain and torn edges over everything except the black wordmark ending
        clip('grain', 0, layout.end_card); clip('torn top', 0, layout.end_card); clip('torn bottom', 0, layout.end_card)
    audio = f'<audio id="mix" src="assets/mix.wav" data-start="0" data-duration="{layout.total:.4f}" data-has-audio="true"></audio>' if has_mix else ''
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=1080, height=1920"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>{CSS}{scrapbook.CSS if scrap else ''}</style></head><body>
<div id="root"{' class="scrap"' if scrap else ''} data-composition-id="main" data-width="1080" data-height="1920" data-fps="30" data-start="0" data-duration="{layout.total:.4f}">
<video id="plate" class="clip" src="assets/plate.mp4" muted data-start="0" data-duration="{layout.total:.4f}"></video>
{chr(10).join(elements)}
{audio}
</div>
<script>
window.__timelines=window.__timelines||{{}};
const tl=gsap.timeline({{paused:true}});
{chr(10).join(tweens)}
tl.set({{}},{{}},{layout.total-.01:.4f});
window.__timelines["main"]=tl;
</script></body></html>'''
    return document, dots


def _scrap_ending(plan, layout, start, clip, nid, tweens, credits):
    """The closing line handwritten on paper, then the ENDWITHCASCADE ending: black, the wordmark blurs in,
    holds, and leaves on a colour-split glitch. The wordmark is filled with leopard print."""
    total = layout.total
    mark_at = start
    if plan.end_line:
        mark_at = start+min(1.8, (total-start)*.5)
        note = clip('lay note', start, mark_at, f'<p>{html.escape(CLEAN.sub("", plan.end_line))}</p>')
        tweens.append(f'tl.fromTo("#{note} p",{{opacity:0,y:30,rotation:-6}},{{opacity:1,y:0,rotation:-2,duration:.35,ease:"back.out(1.6)"}},{start:.4f});')
    w = nid()
    inner = (f'<div id="{w}" class="wm"><span class="ghost r">Cascade</span><span class="ghost c">Cascade</span>'
             f'<span class="fill">Cascade</span></div>')
    clip('lay wmk', mark_at, total, inner)
    tweens.append(f'tl.fromTo("#{w}",{{opacity:0,filter:"blur(18px)",scale:1.04}},{{opacity:1,filter:"blur(0px)",scale:1,duration:.35,ease:"power2.out"}},{mark_at+.08:.4f});')
    g = max(mark_at+.6, total-.32)  # the glitch out, ~5 frames, like the reference
    tweens.append(f'tl.to("#{w} .ghost.r",{{opacity:.9,x:-9,duration:.03}},{g:.4f});')
    tweens.append(f'tl.to("#{w} .ghost.c",{{opacity:.9,x:9,duration:.03}},{g:.4f});')
    tweens.append(f'tl.to("#{w}",{{x:6,duration:.03}},{g+.04:.4f});')
    tweens.append(f'tl.to("#{w}",{{x:-4,skewX:8,duration:.03}},{g+.08:.4f});')
    tweens.append(f'tl.to("#{w}",{{opacity:0,x:0,skewX:0,duration:.12}},{g+.14:.4f});')


def _is_card(e, layout):
    return e.kind in ('stock', 'source', 'band') and e.end-e.start >= .7 and e.start < layout.end_card


def _scrap_motion(layout, hero_times, behind, clip, nid, tweens, elements):
    """Nothing sits still: every shot drifts, punches in on its key words, cuts are covered by a paper swipe,
    and a few key words sit behind the speaker (FireEdit)."""
    target = '#plate,.photo,.cutv' if behind else '#plate,.photo'  # the photo's white border and tape zoom with the footage
    for e in layout.events:
        if e.kind in ('ink', 'dot') or e.start >= layout.end_card: continue
        end = min(e.end, layout.end_card)
        card = _is_card(e, layout)
        base = .8 if card else 1.0
        t0, level = (e.start+.22 if card else e.start), base
        if not card: tweens.append(f'tl.set("{target}",{{scale:1}},{e.start:.4f});')
        for h in sorted(h for h in hero_times if t0+.15 < h < end-.15):
            if h-t0 > .05: tweens.append(f'tl.to("{target}",{{scale:{level*1.018:.4f},duration:{h-t0:.4f},ease:"none"}},{t0:.4f});')
            level = base*1.1 if abs(level-base) < .01 else base  # punch in, then back out on the next key word
            tweens.append(f'tl.to("{target}",{{scale:{level:.4f},duration:.16,ease:"power3.out"}},{h:.4f});')
            t0 = h+.16
        if end-t0 > .05: tweens.append(f'tl.to("{target}",{{scale:{level*1.025:.4f},duration:{end-t0:.4f},ease:"none"}},{t0:.4f});')
    # a sheet of paper swipes across every cut between the speaker and a pinned-up photo
    shots = [e for e in layout.events if e.kind not in ('ink', 'dot') and e.start < layout.end_card]
    for a, b in zip(shots, shots[1:]):
        if _is_card(a, layout) == _is_card(b, layout): continue
        cut = b.start
        sweep = clip('swipe', cut-.16, cut+.16)
        tweens.append(f'tl.fromTo("#{sweep}",{{x:1250}},{{x:-1450,duration:.32,ease:"power2.inOut"}},{cut-.16:.4f});')
    # words behind the speaker: the giant word, then the cut-out of the person on top of it
    layers = []
    for n, (a, b, word, name) in enumerate(behind):
        size = min(330, int(2050/max(len(word), 1)))
        w = nid()
        layers.append(f'<div id="{w}" class="clip bword{" red" if n % 2 else ""}" data-start="{a:.4f}" data-duration="{b-a:.4f}" style="font-size:{size}px">{html.escape(word)}</div>')
        tweens.append(f'tl.fromTo("#{w}",{{opacity:0,scale:1.35,y:40}},{{opacity:1,scale:1,y:0,duration:.22,ease:"power3.out"}},{a:.4f});')
        tweens.append(f'tl.to("#{w}",{{opacity:0,duration:.12}},{b-.12:.4f});')
        layers.append(f'<video id="{nid()}" class="clip cutv" src="assets/{name}" muted data-start="{a:.4f}" data-duration="{b-a:.4f}" data-media-start="0"></video>')
    elements[:0] = layers  # straight above the plate, under every caption and graphic
