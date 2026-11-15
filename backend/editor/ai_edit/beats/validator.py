"""The code validator for beat plans: a port of reference/scripts/critic.py, plus schema checks.

    validate(plan, transcript) -> [Issue]      every problem, each with a rule number and severity
    normalize(plan, transcript) -> (plan, [str]) deterministic repairs applied before validating

Rule numbers follow prompts/critic_prompt.txt. Rule 0 is the schema (not in critic.py): a plan that
breaks it cannot be rendered, so those issues are all high severity.

One deliberate difference from critic.py: the hook beat (the first beat) may run up to 4.0 s, as
the director and critic prompts allow. critic.py flags any beat over 3.0 s.
"""
import re
from collections import Counter
from dataclasses import asdict, dataclass

TEMPLATES = {'KINETIC_KEYWORD', 'TEXT_BEHIND_SUBJECT', 'NUMBER_COUNTER', 'MAP_CALLOUT', 'BROLL_OVERLAY', 'SCREENSHOT_CALLOUT',
             'SCRIBBLE_HIGHLIGHT', 'COLLAGE', 'SPEAKER_CUTOUT_ICONS', 'PLAIN_SPEAKER'}
TRANSITIONS = {'whip_pan', 'zoom_blur', 'glitch', 'flash_cut', 'slide', 'fade'}
COLORS = {'green', 'red', 'yellow', 'orange', 'white'}
BACKGROUNDS = {'light', 'dark'}
GRADES = {'bw', 'color'}
SEVERITY = {'high': 15, 'medium': 5, 'low': 1}   # points off a validator score of 100
EPS = 1e-6


@dataclass
class Issue:
    rule: int
    severity: str
    beat_id: int | None
    problem: str

    def as_dict(self):
        return asdict(self)


def _norm(text):
    return re.sub(r"[^a-z0-9' ]", '', text.lower())


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _words_in(transcript, start, end, window_end):
    return [w for w in transcript if start-EPS <= w['start'] < end-EPS and w['start'] < window_end]


def normalize(plan, transcript):
    """Repairs that need no judgement: ids 1..n, tiny gaps closed, the window edges exact,
    total_duration, and spoken_text rebuilt from the transcript words that start inside each beat.
    Returns (plan, notes). The input is not modified."""
    plan = {**plan, 'beats': [dict(b) for b in plan.get('beats') or [] if isinstance(b, dict)]}
    notes = []
    beats = plan['beats']
    window = plan.get('source_window') or {}
    if not beats or not _num(window.get('start')) or not _num(window.get('end')): return plan, notes
    if not all(_num(b.get('start')) and _num(b.get('end')) for b in beats): return plan, notes
    w0, w1 = window['start'], window['end']
    beats.sort(key=lambda b: b['start'])
    for n, beat in enumerate(beats, 1):
        if beat.get('id') != n: beat['id'] = n; notes.append('renumbered beats')
    if 0 < abs(beats[0]['start']-w0) <= .05: beats[0]['start'] = w0; notes.append('first beat snapped to the window start')
    if 0 < abs(beats[-1]['end']-w1) <= .05: beats[-1]['end'] = w1; notes.append('last beat snapped to the window end')
    for a, b in zip(beats, beats[1:]):
        if 0 < abs(a['end']-b['start']) <= .05: a['end'] = b['start']; notes.append(f'closed a tiny gap before beat {b["id"]}')
    for beat in beats:
        text = ' '.join(w['word'] for w in _words_in(transcript, beat['start'], beat['end'], w1))
        if beat.get('spoken_text') != text: beat['spoken_text'] = text; notes.append(f'beat {beat["id"]} spoken_text set from the transcript')
    total = round(w1-w0, 2)
    if plan.get('total_duration') != total: plan['total_duration'] = total
    return plan, sorted(set(notes), key=notes.index)


def _schema(plan, issues):
    def add(beat, problem): issues.append(Issue(0, 'high', beat, problem))
    if not isinstance(plan, dict): add(None, 'plan is not a JSON object'); return False
    for key in ('source_window', 'hook', 'beats'):
        if key not in plan: add(None, f'missing "{key}"')
    window = plan.get('source_window')
    if not isinstance(window, dict) or not _num(window.get('start')) or not _num(window.get('end')) or window.get('end', 0) <= window.get('start', 0):
        add(None, 'source_window needs numeric start < end')
    hook = plan.get('hook')
    if not isinstance(hook, dict) or not isinstance(hook.get('text'), str) or not _num(hook.get('start')) or not _num(hook.get('end')):
        add(None, 'hook needs text, start and end')
    beats = plan.get('beats')
    if not isinstance(beats, list) or not beats: add(None, 'beats must be a non-empty list'); return False
    usable = True
    for n, b in enumerate(beats, 1):
        if not isinstance(b, dict): add(n, 'beat is not an object'); usable = False; continue
        bid = b.get('id', n)
        if not _num(b.get('start')) or not _num(b.get('end')) or b['end'] <= b['start']:
            add(bid, 'start/end must be numbers with start < end'); usable = False
        if not isinstance(b.get('spoken_text'), str): add(bid, 'spoken_text must be a string'); usable = False
        if b.get('template') not in TEMPLATES: add(bid, f'unknown template {b.get("template")!r}')   # rule 12 in critic.py
        for field, allowed in (('semantic_color', COLORS), ('background_mode', BACKGROUNDS), ('grade', GRADES), ('transition_in', TRANSITIONS)):
            if b.get(field) not in allowed: add(bid, f'{field} must be one of {sorted(allowed)}'); usable = usable and field != 'background_mode'
        for field in ('emphasis_text', 'accent_word', 'broll_query', 'broll_fallback_query', 'sfx'):
            if b.get(field) is not None and not isinstance(b.get(field), str): add(bid, f'{field} must be a string or null'); usable = False
        data = b.get('data')
        if not isinstance(data, dict) or set(data) != {'number', 'place', 'screenshot_target'}:
            add(bid, 'data must have exactly number, place, screenshot_target')
    return usable


def validate(plan, transcript):
    """All issues in `plan` against the word-level `transcript` ([{word,start,end}])."""
    issues = []
    if not _schema(plan, issues): return issues
    add = lambda rule, sev, beat, msg: issues.append(Issue(rule, sev, beat, msg))
    beats = plan['beats']
    w0, w1 = plan['source_window']['start'], plan['source_window']['end']
    # 1 coverage
    if abs(beats[0]['start']-w0) > .01 or abs(beats[-1]['end']-w1) > .01: add(1, 'high', None, 'window not fully covered')
    for a, b in zip(beats, beats[1:]):
        if abs(a['end']-b['start']) > .001: add(1, 'high', b['id'], f'gap/overlap {a["end"]}->{b["start"]}')
    inwin = [w for w in transcript if w0-EPS <= w['start'] < w1]
    got = sum(len(b['spoken_text'].split()) for b in beats)
    if got != len(inwin): add(1, 'high', None, f'words in beats {got} != words in window {len(inwin)}')
    for b in beats:
        expected = ' '.join(w['word'] for w in _words_in(transcript, b['start'], b['end'], w1))
        if _norm(b['spoken_text']).split() != _norm(expected).split():
            add(1, 'high', b['id'], 'spoken_text does not match the transcript words inside this beat')
    # 2 hook
    if beats[0]['start']-w0 > 3: add(2, 'high', 1, 'hook not in first 3s')
    # 3 pacing
    lens = [b['end']-b['start'] for b in beats]
    for n, (b, length) in enumerate(zip(beats, lens)):
        limit = 4.0 if n == 0 else 3.0
        if length > limit+EPS: add(3, 'high', b['id'], f'{length:.2f}s > {limit:.1f}s')
        if length < .6: add(3, 'medium', b['id'], f'{length:.2f}s < 0.6s')
    avg = sum(lens)/len(lens)
    if not 1.0 <= avg <= 2.0: add(3, 'medium', None, f'avg beat {avg:.2f}s outside 1.0-2.0')
    # 4 variety
    for a, b in zip(beats, beats[1:]):
        if a['template'] == b['template']: add(4, 'high', b['id'], 'same template back to back')
    plains = [b for b in beats if b['template'] == 'PLAIN_SPEAKER']
    for a, b in zip(plains, plains[1:]):
        if b['start']-a['start'] < 10: add(4, 'medium', b['id'], 'PLAIN_SPEAKER twice within 10s')
    for b in beats:
        window = {x['template'] for x in beats if b['start'] <= x['start'] < b['start']+15}
        if b['start']+15 <= w1 and len(window) < 4: add(4, 'medium', b['id'], f'only {len(window)} templates in 15s window')
    for template, count in Counter(b['template'] for b in beats).items():
        if len(beats) >= 12 and count/len(beats) > .36: add(4, 'medium', None, f'{template} is {count}/{len(beats)} beats (>36%)')
    # 5 fit
    for b in beats:
        if re.search(r'\d', b['spoken_text']) and b['template'] != 'NUMBER_COUNTER': add(5, 'medium', b['id'], 'number spoken, no counter')
    # 6 text
    for b in beats:
        spoken = {_norm(w) for w in b['spoken_text'].split()}
        for field in ('emphasis_text', 'accent_word'):
            value = b.get(field)
            if value:
                tokens = _norm(value).split()
                if len(tokens) > 4: add(6, 'medium', b['id'], f'{field} > 4 words')
                for token in tokens:
                    if token not in spoken: add(6, 'high', b['id'], f"'{token}' in {field} not spoken in this beat")
        if b['template'] != 'PLAIN_SPEAKER' and not b.get('emphasis_text'): add(6, 'high', b['id'], 'missing emphasis_text')
    # 8 contrast
    run = 1
    for a, b in zip(beats, beats[1:]):
        run = run+1 if a['background_mode'] == b['background_mode'] else 1
        if run >= 3: add(8, 'medium', b['id'], '3+ same background_mode in a row')
    # 9 transitions
    for x, y, z in zip(beats, beats[1:], beats[2:]):
        if x['transition_in'] == y['transition_in'] == z['transition_in']: add(9, 'low', y['id'], 'same transition 3x')
    # 10 b-roll
    for b in beats:
        if b['template'] in ('BROLL_OVERLAY', 'COLLAGE'):
            if not b.get('broll_query') or not b.get('broll_fallback_query'): add(10, 'high', b['id'], 'missing b-roll query/fallback')
            elif b['broll_query'] == b['broll_fallback_query']: add(10, 'low', b['id'], 'fallback same as query')
    # 12 feasibility: the data each template needs
    for b in beats:
        data = b.get('data') or {}
        need = {'NUMBER_COUNTER': 'number', 'MAP_CALLOUT': 'place', 'SCREENSHOT_CALLOUT': 'screenshot_target'}.get(b['template'])
        if need and data.get(need) in (None, ''): add(12, 'high', b['id'], f'{b["template"]} needs data.{need}')
    return issues


def high(issues):
    return [i for i in issues if i.severity == 'high']


def score(issues):
    """A 0-100 score from the code validator alone (the critic model gives its own score)."""
    return max(0, 100-sum(SEVERITY.get(i.severity, 0) for i in issues))


def summary(plan, issues):
    beats = plan.get('beats') or []
    lens = [b['end']-b['start'] for b in beats if _num(b.get('start')) and _num(b.get('end'))]
    return {'beats': len(beats), 'avg_beat': round(sum(lens)/len(lens), 2) if lens else None,
            'max_beat': round(max(lens), 2) if lens else None, 'min_beat': round(min(lens), 2) if lens else None,
            'templates': dict(Counter(b.get('template') for b in beats)),
            'issues': len(issues), 'high': len(high(issues)), 'validator_score': score(issues)}


def resemblance(plan, reference, tolerance=.3):
    """How close a plan is to a reference plan: shared beat boundaries and template mix (0-1 each)."""
    edges = lambda p: [b['start'] for b in p['beats'][1:]]
    ours, theirs = edges(plan), edges(reference)
    shared = sum(any(abs(a-b) <= tolerance for a in ours) for b in theirs)/max(1, len(theirs))
    mix_a, mix_b = Counter(b['template'] for b in plan['beats']), Counter(b['template'] for b in reference['beats'])
    overlap = sum((mix_a & mix_b).values())/max(1, max(sum(mix_a.values()), sum(mix_b.values())))
    return {'beats': len(plan['beats']), 'reference_beats': len(reference['beats']),
            'shared_boundaries': round(shared, 2), 'template_mix_overlap': round(overlap, 2)}
