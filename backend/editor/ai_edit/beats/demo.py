"""The kit's validated plan (examples/edit_plan_example.json) placed on another recording of the same speech.

The example plan was made for the 27.12-71.78 s window of the demo podcast. When a clip contains that speech
(found by matching its words, so a clip cut from the podcast at any offset works), the plan is moved onto the
clip's own word times: every beat boundary that sits on a word moves to that word in the clip, and boundaries in
a silence move by the clip's offset. The result goes through the same validator as any plan.

Used for the demo clip when the planner cannot answer, and always with CASCADE_BEATS_DEMO_PLAN=on.
"""
import copy
import difflib
import json
import logging
import os
import re
import statistics
from pathlib import Path

from . import validator

LOG = logging.getLogger(__name__)
EXAMPLES = Path(__file__).parent/'examples'


def forced():
    return os.getenv('CASCADE_BEATS_DEMO_PLAN', '').strip().lower() in ('1', 'on', 'true', 'yes')


def _token(text):
    return re.sub(r"[^a-z0-9']", '', text.lower())


def matching_plan(words, start=None, end=None):
    """The example plan on these words ([{word,start,end}]), or None if the clip does not contain that speech."""
    example = json.loads((EXAMPLES/'edit_plan_example.json').read_text())
    w0, w1 = example['source_window']['start'], example['source_window']['end']
    ref = [w for w in json.loads((EXAMPLES/'transcript_full.json').read_text()) if w0-1e-6 <= w['start'] < w1]
    ours = [_token(w['word']) for w in words]
    theirs = [_token(w['word']) for w in ref]
    matcher = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
    pairs = {b.b+k: words[b.a+k] for b in matcher.get_matching_blocks() for k in range(b.size) if theirs[b.b+k]}
    if len(pairs) < .85*len(ref):
        return None
    offsets = [pairs[i]['start']-ref[i]['start'] for i in pairs]
    offset = statistics.median(offsets)
    if statistics.median(abs(o-offset) for o in offsets) > .25:   # not one straight cut of the same speech
        return None

    def place(t):
        for i, w in enumerate(ref):
            if abs(w['start']-t) <= .02 and i in pairs: return pairs[i]['start']
        for i, w in enumerate(ref):
            if abs(w['end']-t) <= .02 and i in pairs: return pairs[i]['end']
        return t+offset

    plan = copy.deepcopy(example)
    edges = [place(b['start']) for b in plan['beats']]+[place(plan['beats'][-1]['end'])]
    for a, b in zip(edges, edges[1:]):
        if b <= a: return None
    for beat, a, b in zip(plan['beats'], edges, edges[1:]):
        beat['start'], beat['end'] = round(a, 2), round(b, 2)
    plan['source_window'] = {'start': plan['beats'][0]['start'], 'end': plan['beats'][-1]['end']}
    plan['hook'] = {**plan['hook'], 'start': round(place(plan['hook']['start']), 2), 'end': round(place(plan['hook']['end']), 2)}
    plan['source_video'] = 'source'
    if start is not None and plan['source_window']['start'] < start-.05: return None
    if end is not None and plan['source_window']['end'] > end+.05: return None
    plan, _ = validator.normalize(plan, words)
    plan['total_duration'] = round(plan['source_window']['end']-plan['source_window']['start'], 2)
    issues = validator.validate(plan, words)
    broken = [i for i in issues if i.rule == 0 or (i.rule == 1 and 'gap' in i.problem) or 'window not fully covered' in i.problem]
    if broken:
        LOG.info('example plan does not fit this clip: %s', [i.problem for i in broken])
        return None
    return plan
