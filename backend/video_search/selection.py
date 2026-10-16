"""Rank fixed-length local-search windows without selecting overlapping clips."""
from bisect import bisect_right
import math


def select_matches(anchors, duration, clip_length, lead, limit=4):
    preferred = select_windows(anchors, duration, clip_length, lead, limit)
    if len(preferred) < limit:
        # The website's duration is a target. Only shorten it if that actually
        # enables four distinct results; never duplicate a match to fill slots.
        for shorter in dict.fromkeys((max(8., clip_length / 2), 8.)):
            if shorter >= clip_length:
                continue
            alternative = select_windows(anchors, duration, shorter, min(lead, shorter / 3), limit)
            if len(alternative) == limit:
                return alternative
    return preferred


def select_windows(anchors, duration, clip_length, lead, limit=4):
    if not math.isfinite(duration) or duration <= 0 or clip_length <= 0:
        return []
    length = min(float(clip_length), duration)
    windows = {}
    for anchor in anchors:
        moment, score = float(anchor['time']), float(anchor['score'])
        if not math.isfinite(moment) or not math.isfinite(score) or not 0 <= moment < duration:
            continue
        for proposed in (moment - lead, moment - length / 2, moment - length + lead,
                         math.floor(moment / length) * length):
            start = max(0., min(proposed, duration - length))
            end = min(duration, start + length)
            if not start <= moment < end:
                continue
            # Keep a matched speech segment complete whenever it fits in one clip.
            evidence_start = anchor.get('evidence_start', moment)
            evidence_end = anchor.get('evidence_end', moment)
            if evidence_end - evidence_start <= length and (start > evidence_start or end < evidence_end):
                continue
            key = (round(start, 3), round(end, 3))
            candidate = {**anchor, 'start': key[0], 'end': key[1]}
            if key not in windows or score > windows[key]['score']:
                windows[key] = candidate
    candidates = sorted(windows.values(), key=lambda c: c['end'])
    ends = [c['end'] for c in candidates]
    # Cardinality-constrained interval scheduling: unlike greedy suppression,
    # a high-scoring middle window cannot prevent four available distinct clips.
    previous = [bisect_right(ends, c['start'], hi=i) for i, c in enumerate(candidates)]
    empty = (0., [])
    table = [[empty] * (len(candidates) + 1)]
    best = []
    for count in range(1, limit + 1):
        row = [None] * (len(candidates) + 1)
        for index, candidate in enumerate(candidates, 1):
            skipped = row[index - 1]
            parent = table[count - 1][previous[index - 1]]
            taken = None if parent is None else (parent[0] + candidate['score'], parent[1] + [candidate])
            row[index] = taken if taken and (skipped is None or taken[0] > skipped[0]) else skipped
        table.append(row)
        if row[-1] is not None:
            best = row[-1][1]
    return sorted(best, key=lambda c: c['score'], reverse=True)
