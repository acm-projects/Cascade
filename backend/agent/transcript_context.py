"""Bound transcript selection input without loading embedding models.

Small sources remain complete. Long sources use intact 3-minute windows,
balanced across the timeline and ranked against the prompt/reference text.
"""
from collections import Counter
import math
import re

from .chunks import format_transcript

MAX_CONTEXT_CHARS = 72_000
STOP = set('the a an and or to of in on for with this that these clips clip find from video more like seconds'.split())


def selection_context(transcript, query, references=(), limit=MAX_CONTEXT_CHARS):
    complete = format_transcript(transcript)
    if len(complete) <= limit:
        return complete, None
    query = query + ' ' + ' '.join(str(r.get('title', '')) + ' ' + str(r.get('description', '')) for r in references)
    terms = set(re.findall(r'\w{3,}', query.lower())) - STOP
    windows = []
    window_size = 0
    for segment in transcript:
        if (not windows or segment['start'] - windows[-1][0]['start'] >= 180
                or window_size + len(segment['text']) + 64 > limit // 8):
            windows.append([])
            window_size = 0
        windows[-1].append(segment)
        window_size += len(segment['text']) + 64
    counts = [Counter(re.findall(r'\w{3,}', ' '.join(s['text'] for s in window).lower())) for window in windows]
    weights = {term: math.log(1 + len(windows) / (1 + sum(term in row for row in counts))) for term in terms}
    scores = [sum(weights[t] * min(row[t], 5) for t in terms) for row in counts]
    # Interleave relevance-ranked windows from each quarter, so general requests
    # and repetitive topics don't silently exclude the end of a long recording.
    quarters = [sorted((i for i in range(len(windows)) if min(3, i * 4 // len(windows)) == q),
                       key=lambda i: (-scores[i], i)) for q in range(4)]
    selected, size = set(), 0
    snippets = [format_transcript(window) for window in windows]
    for i in dict.fromkeys((0, len(windows) - 1)):
        if size + len(snippets[i]) + 2 <= limit:
            selected.add(i)
            size += len(snippets[i]) + 2
    for depth in range(max(map(len, quarters))):
        for quarter in quarters:
            if depth >= len(quarter):
                continue
            i = quarter[depth]
            if i in selected:
                continue
            if size + len(snippets[i]) + 2 <= limit:
                selected.add(i)
                size += len(snippets[i]) + 2
    if not selected:
        raise ValueError('Transcript segment is too large for a bounded selection request.')
    intervals, previous = [], -2
    for i in sorted(selected):
        start, end = windows[i][0]['start'], windows[i][-1]['end']
        if i == previous + 1:
            intervals[-1] = (intervals[-1][0], end)
        else:
            intervals.append((start, end))
        previous = i
    return '\n\n'.join(snippets[i] for i in sorted(selected)), intervals
