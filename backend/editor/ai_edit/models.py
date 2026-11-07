"""The edit Claude directs. Everything is addressed by transcript word number, never by invented
timecode: the engine owns the beat grid, so captions always sit on the spoken frame."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Part = Literal['home', 'loss', 'cost', 'left', 'main']


class Phrase(BaseModel):
    model_config = ConfigDict(extra='ignore')
    from_word: int = Field(ge=0)
    to_word: int = Field(ge=0)
    hero: int | str | None = None  # the word number shown big; at most one per phrase (a word written out is resolved in check())


class Number(BaseModel):
    model_config = ConfigDict(extra='ignore')
    text: str = Field(min_length=1, max_length=12)  # "60–80%"
    from_word: int = Field(ge=0)  # the phrase before it stops here and the number lands
    source: str = Field(min_length=3, max_length=120)  # a named source and year, shown on screen


class Shot(BaseModel):
    model_config = ConfigDict(extra='ignore')
    at_word: int = Field(ge=0)  # the picture changes on (or just before) this word
    kind: Literal['source', 'sync', 'stock', 'dot', 'band'] = 'source'
    src: float = Field(default=0, ge=0)  # source seconds, for source and band
    cx: float = Field(default=.5, ge=0, le=1)  # horizontal centre of the vertical crop
    zoom: Literal[1, 1.15, 1.3] = 1
    query: str = Field(default='', max_length=120)  # stock search words
    note: str = Field(default='', max_length=80)


class Line(BaseModel):
    model_config = ConfigDict(extra='ignore')
    from_word: int = Field(ge=0)
    to_word: int = Field(ge=0)
    key_word: int = Field(ge=0)  # lands exactly on a beat
    part: Part = 'main'
    gap_before: float = Field(default=.3, ge=0, le=3)
    phrases: list[Phrase] = Field(default_factory=list, max_length=20)
    shots: list[Shot] = Field(default_factory=list, max_length=12)
    number: Number | None = None
    verdict: bool = False  # caps on Ink, voice alone, with silence before it


class Plan(BaseModel):
    model_config = ConfigDict(extra='ignore')
    reply: str = Field(default='', max_length=1500)
    title: str = Field(default='Edit', max_length=60)
    mode: Literal['core', 'earth', 'talk'] = 'core'  # talk: podcasts, interviews, Q&A
    bpm: int = Field(default=72, ge=56, le=120)
    mood: Literal['dark', 'warm', 'driving', 'none'] = 'dark'
    music_db: float = Field(default=-15, ge=-40, le=-6)  # against the voice
    credit: str = Field(default='', max_length=80)  # on-screen source credit
    closing_src: float | None = Field(default=None, ge=0)  # footage for the circle that shrinks to a dot before the verdict
    closing_cx: float = Field(default=.5, ge=0, le=1)
    end_hero: str = Field(default='', max_length=24)
    end_line: str = Field(default='', max_length=70)  # one line that sums the video up and lands it
    lines: list[Line] = Field(min_length=1, max_length=60)

    @model_validator(mode='after')
    def one_verdict_kind(self):
        if sum(line.verdict for line in self.lines) > 2: raise ValueError('At most two verdict lines.')
        if self.mode != 'earth': self.closing_src = None  # the shrinking circle is an Earth-mode graphic; elsewhere it came out of nowhere
        if self.mode == 'talk':  # podcast references: the speakers carry it, stock only now and then, one punchline slam at most
            stock = [s for line in self.lines for s in line.shots if s.kind == 'stock']
            for s in stock[3:]: s.kind, s.query = 'sync', ''
            for line in [l for l in self.lines if l.verdict][1:]: line.verdict = False
        self.end_hero = self.end_hero.strip().rstrip('.')  # the end card shows no full stop
        return self


def check(plan, words, windows):
    """Raises ValueError naming what a plan got wrong, in terms Claude can fix."""
    total = len(words)
    inside = lambda t: any(a-.05 <= t <= b+.05 for a, b in windows)
    for n, line in enumerate(plan.lines):
        if not line.from_word <= line.key_word <= line.to_word < total:
            raise ValueError(f'line {n}: from_word <= key_word <= to_word < {total} is required')
        if not inside(words[line.from_word]['s']) or not inside(words[line.to_word]['s']):
            raise ValueError(f'line {n}: words outside the part of the clip the user kept')
        for p in line.phrases:
            if not line.from_word <= p.from_word <= p.to_word <= line.to_word: raise ValueError(f'line {n}: a phrase leaves its line')
            if isinstance(p.hero, str):  # Claude sometimes writes the word itself ("caiman") instead of its number
                text = p.hero.strip()
                if text.isdigit(): p.hero = int(text)
                else:
                    plain = lambda w: re.sub(r'[^\w]', '', w).lower()
                    p.hero = next((i for i in range(p.from_word, p.to_word+1) if plain(words[i]['w']) == plain(text)), None)
            if p.to_word-p.from_word+1 > 5: raise ValueError(f'line {n}: a phrase has more than 5 words')
            if p.hero is not None and not p.from_word <= p.hero <= p.to_word: raise ValueError(f'line {n}: a hero word leaves its phrase')
        for s in line.shots:
            if not line.from_word <= s.at_word <= line.to_word: raise ValueError(f'line {n}: a shot starts outside its line')
            if s.kind in ('source', 'band') and not inside(s.src): raise ValueError(f'line {n}: shot source time {s.src} is outside the kept clip')
            if s.kind == 'stock' and not s.query: raise ValueError(f'line {n}: a stock shot needs a query')
