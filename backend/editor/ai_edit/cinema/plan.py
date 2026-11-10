"""What Claude decides for a Cinema edit, addressed by transcript word number, and the rule-based
director used when Claude is unavailable (so "edit this video" never fails)."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import look, speech

Tone = Literal['water', 'life', 'hope', 'danger', 'money', 'earth', 'calm']


class Span(BaseModel):
    model_config = ConfigDict(extra='ignore')
    from_word: int = Field(ge=0)
    to_word: int = Field(ge=0)
    role: Literal['hook', 'question', 'answer', 'payoff'] = 'answer'


class Moment(BaseModel):
    """A designed beat on one spoken word."""
    model_config = ConfigDict(extra='ignore')
    word: int = Field(ge=0)
    style: Literal['behind', 'outline', 'slam', 'serif', 'glow'] = 'behind'
    tone: Tone | None = None
    text: str = Field(default='', max_length=16)   # what to show; defaults to the spoken word


class Keyword(BaseModel):
    model_config = ConfigDict(extra='ignore')
    word: int = Field(ge=0)
    tone: Tone | None = None


class Broll(BaseModel):
    model_config = ConfigDict(extra='ignore')
    from_word: int = Field(ge=0)
    to_word: int = Field(ge=0)
    query: str = Field(min_length=2, max_length=90)
    look: Literal['full', 'card', 'mono', 'band'] = 'full'
    tone: Tone | None = None


class Opener(BaseModel):
    model_config = ConfigDict(extra='ignore')
    style: Literal['mask', 'none'] = 'mask'
    word: str = Field(default='', max_length=14)
    query: str = Field(default='', max_length=90)   # footage that fills the word


class CinemaPlan(BaseModel):
    model_config = ConfigDict(extra='ignore')
    reply: str = Field(default='', max_length=1500)
    title: str = Field(default='Edit', max_length=60)
    mood: Literal['awakening', 'wonder', 'tension', 'warm'] = 'awakening'
    grade: Literal['cinema', 'forest', 'night'] = 'cinema'
    story: list[Span] = Field(min_length=1, max_length=40)
    drop: list[list[int]] = Field(default_factory=list, max_length=200)
    keywords: list[Keyword] = Field(default_factory=list, max_length=60)
    moments: list[Moment] = Field(default_factory=list, max_length=12)
    broll: list[Broll] = Field(default_factory=list, max_length=24)
    silence_before: int | None = None
    opener: Opener = Field(default_factory=Opener)
    end_line: str = Field(default='', max_length=70)

    @model_validator(mode='after')
    def _tidy(self):
        self.drop = [d if len(d) == 2 else [d[0], d[0]] for d in self.drop if d]
        self.end_line = self.end_line.strip().rstrip('.')
        return self

    def dropped(self):
        out = set()
        for a, b in self.drop: out.update(range(min(a, b), max(a, b)+1))
        return out


def check(plan, words):
    """Raises ValueError naming what is wrong, in words Claude can fix."""
    n = len(words)
    seen = set()
    for k, s in enumerate(plan.story):
        if not s.from_word <= s.to_word < n: raise ValueError(f'story {k}: needs from_word <= to_word < {n}')
        span = set(range(s.from_word, s.to_word+1))
        if span & seen: raise ValueError(f'story {k}: overlaps an earlier story span; each word plays once')
        seen |= span
    for m in plan.moments:
        if m.word not in seen: raise ValueError(f'moment on word {m.word} is not in the story')
    for b in plan.broll:
        if not b.from_word <= b.to_word < n: raise ValueError('broll: from_word <= to_word required')
    if plan.silence_before is not None and plan.silence_before not in seen:
        plan.silence_before = None


# --- the rule-based director -------------------------------------------------------------------

FILLER = {'a', 'an', 'the', 'of', 'or', 'and', 'but', 'is', 'are', 'it', "it's", 'that', 'this', 'so', 'to', 'in', 'on', 'they',
          "they're", 'he', 'she', 'we', 'you', 'i', 'my', 'just', 'like', 'very', 'really', 'have', 'has', 'do', 'was', 'be',
          'been', 'what', 'with', 'for', 'at', 'as', 'about', 'there', 'then', 'them', 'their', 'can', 'could', 'would', 'me',
          'yeah', 'okay', 'ok', 'all', 'any', 'into', 'up', 'out', 'if', 'not', "don't", "didn't", 'one', 'get', 'go', 'look',
          'thing', 'things', 'kind', 'mean', 'know', 'see', 'way', 'time', 'always', 'never', 'even', 'most', 'some'}


def _plain(w):
    return speech.plain(w)


def sentences(words):
    out, run = [], []
    for i, w in enumerate(words):
        run.append(i)
        if w['w'].rstrip().endswith(('.', '?', '!')):
            out.append(run); run = []
    if run: out.append(run)
    return out


def auto(words, duration_goal=55.):
    """A complete plan from the transcript alone: question first, the answer tightened, false starts and
    echoes cut, the strongest nouns given designed moments, b-roll on concrete nouns."""
    sents = sentences(words)
    text = lambda s: ' '.join(words[i]['w'] for i in s)
    question = next((s for s in sents[:6] if words[s[-1]]['w'].rstrip().endswith('?') and len(s) >= 4), None)
    story, drop = [], []
    start = 0
    if question:
        story.append(Span(from_word=question[0], to_word=question[-1], role='question'))
        start = question[-1]+1
        qwords = {_plain(words[i]['w']) for i in question} - FILLER
        # an answer that opens by repeating the question ("Unpredictable or dangerous animal in the Amazon.") is cut
        for s in sents:
            if s[0] < start or s[0] > start+40: continue
            sw = [_plain(words[i]['w']) for i in s]
            if len(s) <= 10 and sum(w in qwords for w in sw) >= max(2, int(.6*len(sw))):
                drop.append([s[0], s[-1]])
            break
    # very short false starts ("They are." "The Jags, okay.") are cut
    for s in sents:
        if s[0] < start: continue
        if len(s) <= 3 and words[s[-1]]['e']-words[s[0]]['s'] < 1.2 and not words[s[-1]]['w'].endswith('?'):
            drop.append([s[0], s[-1]])
    # the answer: from the end of the question, up to about the goal length of spoken time
    dropped = {i for a, b in drop for i in range(a, b+1)}
    spoken, end = 0., start
    for s in sents:
        if s[0] < start: continue
        spoken += sum(words[i]['e']-words[i]['s'] for i in s if i not in dropped)+.08*len(s)
        end = s[-1]
        if spoken > duration_goal and words[s[-1]]['w'].endswith(('.', '!')): break
    if end >= start:
        story.append(Span(from_word=start, to_word=end, role='answer'))
    kept = [i for sp in story for i in range(sp.from_word, sp.to_word+1) if i not in dropped]
    # keywords: content words that carry a tone
    keywords, moments, broll = [], [], []
    last_moment, last_broll = -99., -99.
    for i in kept:
        p = _plain(words[i]['w'])
        if p in FILLER or len(p) < 4: continue
        tone = look.tone_of(p, None)
        if tone:
            keywords.append(Keyword(word=i, tone=tone))
            t = words[i]['s']
            if t-last_moment > 9 and len(moments) < 5 and len(p) <= 11 and i > (question[-1] if question else -1):
                moments.append(Moment(word=i, style='behind' if len(moments) % 2 == 0 else 'outline', tone=tone)); last_moment = t
            if t-last_broll > 6 and len(broll) < 6 and tone in ('water', 'life', 'danger', 'earth'):
                j = min(i+6, kept[-1])
                broll.append(Broll(from_word=i, to_word=j, query=f'{p} cinematic', look='full', tone=tone)); last_broll = t
    payoff = next((s for s in reversed(sents) if s[-1] <= end and s[0] >= start and len(s) >= 3), None)
    plan = CinemaPlan(title='Cascade cut', story=story, drop=drop, keywords=keywords, moments=moments, broll=broll,
                      silence_before=payoff[0] if payoff else None,
                      opener=Opener(style='mask', word=next((_plain(words[k.word]['w']).upper() for k in keywords if len(_plain(words[k.word]['w'])) <= 8), 'LISTEN')),
                      end_line='')
    return plan
