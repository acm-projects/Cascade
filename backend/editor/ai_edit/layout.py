"""Turn a plan into exact times: lines on the beat grid, shots on beats, graphics between them."""
import math
from dataclasses import dataclass, field

DIM_FREE = ('dot', 'ink')
MAX_HOLD = 3.4


@dataclass
class Event:
    start: float
    kind: str  # source | sync | stock | dot | band | ink
    src: float = 0
    cx: float = .5
    zoom: float = 1
    query: str = ''
    note: str = ''
    part: str = 'main'
    line: int = -1
    shot: int = -1
    end: float = 0
    sync_line: int = -1


@dataclass
class Layout:
    beat: float
    total: float
    lines: list  # {index, t, end, beat, words: [(text, time, source index)], plan line}
    events: list = field(default_factory=list)
    closing: tuple | None = None
    silence: tuple | None = None
    reset: tuple | None = None
    end_card: float = 0
    part_flips: list = field(default_factory=list)

    def b(self, n):
        return round(n*self.beat*30)/30


def build(plan, words):
    beat = 60/plan.bpm
    b = lambda n: round(n*beat*30)/30
    placed, cur, reset, closing, silence, verdict_seen = [], .4, None, None, None, False
    for n, line in enumerate(plan.lines):
        chosen = words[line.from_word:line.to_word+1]
        a, z = chosen[0]['s'], chosen[-1]['e']
        key = words[line.key_word]['s']
        gap = line.gap_before if n else 0
        first_verdict = line.verdict and not verdict_seen
        if first_verdict: gap = max(gap, (3 if plan.closing_src is not None else 2)*beat+.2)
        if reset and reset[1] > cur: cur = reset[1]
        at_beat = math.ceil((cur+gap+key-a)/beat-1e-6)
        t = b(at_beat)-(key-a)
        if first_verdict:
            starts = math.floor(t/beat+1e-6)  # the graphics land on whole beats; the silence runs until the first word
            if plan.closing_src is not None: closing = (b(starts-2), b(starts-1))
            silence = (b(starts-1), t)
            verdict_seen = True
        end = t+z-a
        placed.append({'index': n, 'plan': line, 't': t, 'end': end, 'beat': at_beat, 'a': a,
                       'words': [(w['w'], round(t+w['s']-a, 3), w['i']) for w in chosen]})
        cur = end
        if line.verdict:
            k = math.ceil(end/beat+.25)
            reset = (b(k), b(k+.25))
    if reset and placed[-1]['plan'].verdict: reset = None  # nothing to open onto
    end_beat = math.ceil(max(cur, reset[1] if reset else 0)/beat+.5)
    card = max(4, math.ceil(3.2/beat)) if plan.end_hero or plan.end_line else max(2, math.ceil(1.6/beat))  # the end card always shows "Edited by Cascade"
    layout = Layout(beat=beat, total=b(end_beat+card), lines=placed, closing=closing, silence=silence, reset=reset, end_card=b(end_beat))
    layout.events = _events(plan, layout)
    previous = None
    for line in placed:
        part = line['plan'].part
        if previous is not None and part != previous: layout.part_flips.append(b(round(line['t']/beat)))
        previous = part
    return layout


def _events(plan, layout):
    half = layout.beat/2
    snap = lambda t: round(round(t/half)*half*30)/30
    raw = []
    for line in layout.lines:
        word_time = {i: t for _, t, i in line['words']}
        for number, shot in enumerate(line['plan'].shots):
            at = snap(word_time[shot.at_word])
            raw.append(Event(at, shot.kind, shot.src, shot.cx, shot.zoom, shot.query, shot.note, line['plan'].part, line['index'], number))
    if not raw:  # a line with no shots at all: stay on the speaker
        for line in layout.lines:
            raw.append(Event(snap(line['t']), 'sync', 0, .5, 1, '', 'speaker', line['plan'].part, line['index'], -1))
    raw.sort(key=lambda e: e.start)
    raw[0].start = 0
    # Ink regions the engine owns; they replace whatever would be on screen.
    blocks = []
    if layout.silence:
        verdicts = [l for l in layout.lines if l['plan'].verdict]
        stop = (layout.reset or (layout.end_card, 0))[1] if layout.reset else layout.end_card
        last = next((r for r in verdicts[::-1]), None)
        begin = layout.closing[0] if layout.closing else layout.silence[0]
        blocks.append((begin, max(stop, last['end'] if last else stop)))
    blocks.append((layout.end_card, layout.total))
    events = []
    for event in raw:
        if not any(a-.001 <= event.start < b for a, b in blocks): events.append(event)
        else:
            # a shot asked for inside a block starts right after it instead of vanishing
            after = next((b for a, b in blocks if a-.001 <= event.start < b), None)
            if after and after < layout.end_card and event.line > -1 and not layout.lines[event.line]['plan'].verdict:
                event.start = after; events.append(event)
    for a, b in blocks: events.append(Event(a, 'ink', note='graphic'))
    events.sort(key=lambda e: e.start)
    # no empty Ink after a graphic: the next shot opens the moment the block ends
    for a, b in blocks[:-1]:
        following = next((e for e in events if e.start >= b-.001 and e.kind != 'ink'), None)
        if following and following.start-b < 3: following.start = b
    events.sort(key=lambda e: e.start)
    # later shot wins on a tie; too-short shots yield to the next
    kept = []
    for event in events:
        if kept and event.start-kept[-1].start < .7 and kept[-1].kind != 'ink': kept.pop()
        kept.append(event)
    if kept[0].start > 0: kept[0].start = 0
    for one, two in zip(kept, [*kept[1:], None]):
        one.end = two.start if two else layout.total
    return _resolve_sync(_hold_limit(kept, layout), layout)


def _hold_limit(events, layout):
    """A visual change every 1.5-3 s: long holds get an instant zoom jump, on the half beat, in the same shot."""
    out, half = [], layout.beat/2
    for e in events:
        if e.kind not in ('source', 'sync', 'stock', 'band') or e.end-e.start <= MAX_HOLD:
            out.append(e); continue
        steps = max(2, math.ceil((e.end-e.start)/3))
        length = (e.end-e.start)/steps
        at, sequence = e.start, [1, 1.15, 1.3, 1.15]
        for n in range(steps):
            cut = e.end if n == steps-1 else round(round((e.start+length*(n+1))/half)*half*30)/30
            zoom = e.zoom if e.kind == 'band' else sequence[(sequence.index(e.zoom)+n) % 4] if e.zoom in sequence else e.zoom
            out.append(Event(at, e.kind, e.src+(at-e.start), e.cx, zoom, e.query, e.note, e.part, e.line, e.shot, cut))
            at = cut
    return out


def _resolve_sync(events, layout):
    for e in events:
        if e.kind not in ('sync', 'stock') or not 0 <= e.line < len(layout.lines): continue  # stock falls back to the speaker
        line = layout.lines[e.line]
        e.src = max(0, line['a']+(e.start-line['t']))
    return events
