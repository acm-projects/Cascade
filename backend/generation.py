"""Generation request metadata and source-relative follow-up selection."""
import json
import math

from fastapi import HTTPException
import re

MAX_CLIPS = 12  # Bound encoder work and local selection while allowing varied counts.


def options(folder):
    path = folder / 'owner.json'
    owner = json.loads(path.read_text()) if path.is_file() else {}
    return owner.get('requested_clip_count', 4), owner.get('parent_clip')


def contextual_prompt(prompt, parent):
    if not parent:
        return prompt
    return (prompt + '\nFollow-up context (source-video seconds; search the original source):\n' +
            json.dumps(parent, ensure_ascii=False) +
            '\nPrioritize this moment and surrounding context for expansion requests; related-moment requests may search broadly.')


def followup_windows(selected, parent, prompt, duration, target, count):
    """An explicit expansion includes the complete parent plus available context.

    All branches use original-source time. No duplicate variants fill empty slots.
    Other requests retain semantic search over the full original source.
    """
    if re.search(r"(?:not|don't|never)\s+(?:expand|extend)", prompt, re.I):
        return selected[:count]
    if not parent or not re.search(r'\bexpand\b|before and after|surrounding|more of the explanation', prompt, re.I):
        return selected[:count]
    start, end = parent['start'], parent['end']
    if not all(math.isfinite(t) for t in (start,end,duration)) or not 0 <= start < end <= duration:
        raise HTTPException(409, 'Parent timestamps do not match the original source. Choose another clip.')
    pad = max(2., (target - (end - start)) / 2)
    left, right = max(0., start-pad), min(duration, end+pad)
    if left >= start and right <= end:
        return []  # The parent already spans the entire original source.
    expanded = {'start': left, 'end': right, 'title': 'Expanded: '+parent.get('title', 'selected moment'),
                'explanation': 'Includes the selected moment and available surrounding original footage.',
                'match': 'Expanded parent moment with surrounding source context'}
    return [expanded] + [c for c in selected if c['end'] <= left or c['start'] >= right][:count-1]
