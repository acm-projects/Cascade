"""The composition HyperFrames renders: captions, graphics and the plate. Words appear on their spoken frame."""
import html
import re

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


def build(plan, layout, has_closing, has_mix, credits):
    """Returns (html, dot landing times)."""
    elements, tweens, dots, count = [], [], [], [0]

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
        i = nid(); show(i, t)
        return f'<span id="{i}" class="wd">{html.escape(CLEAN.sub("", text))}</span>'

    def hero(text, t, color, with_dot=False, marker=False):
        i = nid()
        tweens.append(f'tl.fromTo("#{i}",{{opacity:0}},{{opacity:1,duration:{3/30:.4f},ease:"none"}},{t:.4f});')
        tweens.append(f'tl.fromTo("#{i}",{{scale:1.1}},{{scale:1,duration:{8/30:.4f},ease:"power3.out"}},{t:.4f});')
        mark = ''
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
        big = hero(words[h][0], words[h][1], color, marker=plan.mode == 'talk') if h is not None else ''
        under = ''.join(word(words[i][0], words[i][1]) for i in range(h+1, z+1)) if h is not None else ''
        inner = (f'<div class="lead">{lead}</div>' if lead else '')+big+(f'<div class="lead under">{under}</div>' if under else '')
        start = words[a][1]-.02
        clip('lay'+('' if on_ink(words[a][1]) else ' dim'), start, until, f'<div class="cap">{inner}</div>')

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
                clip('lay verdict'+(' paper' if plan.mode == 'talk' else ''), chunk[0][1]-.02, until-.02, '<div class="vlead">'+''.join(word(w, t) for w, t, _ in chunk)+'</div>')
            big = ''
            for position, (w, t, _) in enumerate(words[caps:], caps):
                i = nid(); show(i, t)
                final = position == len(words)-1 and ENDS.search(w) is not None
                big += f'<div id="{i}" class="vw">{html.escape(CLEAN.sub("", w).upper())}{dot(t, "flare") if final else ""}</div>'
            clip('lay verdict'+(' paper' if plan.mode == 'talk' else ''), words[caps][1]-.02, stop, big)
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
    if layout.end_card > fade:
        dark = clip('fadeout', layout.end_card-fade, layout.end_card+.05)
        tweens.append(f'tl.fromTo("#{dark}",{{opacity:0}},{{opacity:1,duration:{fade:.4f},ease:"power1.inOut"}},{layout.end_card-fade:.4f});')
    # credit and end card
    if plan.credit:
        a = 0
        for start, stop in ([layout.reset] if layout.reset else []):
            clip('label', a, start, html.escape(plan.credit)); a = stop
        clip('label', a, layout.end_card, html.escape(plan.credit))
    start = layout.end_card
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
    audio = f'<audio id="mix" src="assets/mix.wav" data-start="0" data-duration="{layout.total:.4f}" data-has-audio="true"></audio>' if has_mix else ''
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=1080, height=1920"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>{CSS}</style></head><body>
<div id="root" data-composition-id="main" data-width="1080" data-height="1920" data-fps="30" data-start="0" data-duration="{layout.total:.4f}">
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
