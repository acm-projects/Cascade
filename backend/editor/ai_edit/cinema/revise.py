"""Follow-up requests that need no AI: switches and simple timeline changes applied straight to the
saved plan ("make it a reel", "lower the music", "remove the b-roll", 'change the message to "…"').
Anything creative ("open on a different line", "more b-roll of rivers") goes to the planner.

`apply(note, plan)` returns (new plan, what changed, what is left for the planner)."""
import re

QUOTED = r'["“\'‘](.+?)["”\'’]'
B = r'b[\s-]?roll'


def _music_down(p): p.settings.music_db = max(-18, p.settings.music_db-5); return 'turned the music down'
def _music_up(p): p.settings.music_db = min(12, p.settings.music_db+4); return 'turned the music up'


def _shorter(p):
    middle = [n for n, s in enumerate(p.story) if s.role == 'answer']
    if len(middle) < 3: return None
    gone = p.story.pop(middle[len(middle)//2])
    inside = lambda w: gone.from_word <= w <= gone.to_word
    p.moments = [m for m in p.moments if not inside(m.word)]
    p.broll = [b for b in p.broll if not inside(b.from_word)]
    return f'cut one line from the middle (words {gone.from_word}-{gone.to_word})'


def _less_broll(p):
    if len(p.broll) < 2: return None
    p.broll = p.broll[::2]
    return 'kept every other b-roll shot'


def _set(attr, value, text):
    def run(p):
        setattr(p.settings, attr, value)
        return text
    return run


def _no_hook(p):
    if p.story and p.story[0].role == 'hook' and len(p.story) > 1:
        p.story.pop(0); return 'removed the cold open'
    return None


def _no_big_words(p):
    p.moments = [m for m in p.moments if m.style not in ('behind', 'outline', 'slam')]
    return 'removed the giant words'


def _no_opener(p): p.opener.style = 'none'; return 'removed the opening word'
def _no_message(p): p.end_line = ''; return 'removed the closing message'

RULES = [
    (rf'\b(reel|vertical|9\s?[:x]\s?16|portrait|tiktok|shorts)\b', _set('ratio', '9:16', 'reframed it as a 9:16 reel')),
    (rf'\b(original (shape|size|aspect|ratio|framing)|landscape|horizontal|16\s?[:x]\s?9|back to original)\b', _set('ratio', 'original', 'put it back in the original shape')),
    (rf'\b(square|1\s?[:x]\s?1)\b', _set('ratio', '1:1', 'made it square')),
    (rf'\b(no|remove|without|mute|kill|turn off)\b[^.;]*\bmusic\b|\bmusic off\b', _set('music', False, 'removed the music')),
    (rf'\b(music (back|on)|add (the )?music)\b', _set('music', True, 'put the music back')),
    (rf'\b(lower|quieter|softer|turn down|reduce)\b[^.;]*\bmusic\b|\bmusic\b[^.;]*\b(lower|quieter|softer|down|too loud)\b', _music_down),
    (rf'\b(louder|raise|turn up|more)\b[^.;]*\bmusic\b|\bmusic\b[^.;]*\b(louder|up|too quiet)\b', _music_up),
    (rf'\b(no|remove|without|hide|turn off)\b[^.;]*\b(captions?|subtitles?)\b|\bcaptions? off\b', _set('captions', False, 'turned the captions off')),
    (rf'\b(captions?|subtitles?) (back|on)\b|\b(add|show)\b[^.;]*\b(captions?|subtitles?)\b', _set('captions', True, 'turned the captions on')),
    (rf'\b(no|remove|without)\b[^.;]*\b{B}\b', _set('broll', False, 'removed the b-roll')),
    (rf'\b{B} (back|on)\b', _set('broll', True, 'put the b-roll back')),
    (rf'\b(less|fewer)\b[^.;]*\b{B}\b', _less_broll),
    (rf'\b(no|remove|without)\b[^.;]*\b(stamp|logo|sign[\s-]?off|cascade (ending|outro|end))\b', _set('stamp', False, 'removed the Cascade sign-off')),
    (rf'\b(stamp|logo|sign[\s-]?off) (back|on)\b', _set('stamp', True, 'put the Cascade sign-off back')),
    (rf'\b(no|remove|without)\b[^.;]*\b(closing |ending |end )?(message|end line)\b', _no_message),
    (rf'\b(no|remove|without)\b[^.;]*\b(hook|cold open)\b', _no_hook),
    (rf'\b(no|remove|without)\b[^.;]*\b(opener|intro|opening word)\b', _no_opener),
    (rf'\b(no|remove|without)\b[^.;]*\b(big|giant|huge) (words?|text)\b', _no_big_words),
    (rf'\b(shorter|trim it down|cut it down|too long)\b', _shorter),
]
TEXT_RULES = [
    (rf'\b(?:message|end(?:ing)? line|closing line)\b[^"“\'‘]*{QUOTED}', lambda p, t: (setattr(p, 'end_line', t[:90].rstrip('.')), f'changed the closing message to “{t[:90]}”')[1]),
    (rf'\btitle\b[^"“\'‘]*{QUOTED}', lambda p, t: (setattr(p, 'title', t[:60]), f'changed the title to “{t[:60]}”')[1]),
    (rf'\b(?:opener|opening word)\b[^"“\'‘]*{QUOTED}', lambda p, t: (setattr(p.opener, 'word', t[:14].upper()), setattr(p.opener, 'style', 'mask'), f'changed the opening word to {t[:14].upper()}')[2]),
]


def apply(note, plan):
    """(plan copy with the simple changes made, [what changed], [clauses nothing here understood])."""
    new = plan.model_copy(deep=True)
    done, left = [], []
    protected = re.sub(QUOTED, lambda m: m.group(0).replace(',', '\x00').replace(' and ', '\x01'), note)
    for clause in re.split(r'\s*(?:,|;|\.(?:\s|$)|\band\b|\bthen\b|\balso\b)\s*', protected):
        clause = clause.replace('\x00', ',').replace('\x01', ' and ').strip()
        if len(clause) < 3: continue
        low, hit = clause.lower(), None
        for pattern, change in TEXT_RULES:
            m = re.search(pattern, clause, re.I)
            if m: hit = change(new, m.group(1).strip()); break
        if hit is None:
            for pattern, change in RULES:
                if re.search(pattern, low):
                    hit = change(new); break
        (done if hit else left).append(hit or clause)
    return new, done, left
