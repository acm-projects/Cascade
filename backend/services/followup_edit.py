"""Deterministic one-reference trims, using cached captions without AI calls."""
import json
import math
import re


def select(video_path, prompt, parent, count, duration):
    if count != 1 or not parent or parent.get('references'):
        return None
    # Only an explicit, unambiguous timestamp instruction is a local edit.
    # Similarity/theme changes and requests for multiple new clips stay with AI.
    match = re.fullmatch(
        r'\s*(?:please\s+)?(?:keep|use)\s+(?:only\s+)?(?:the\s+)?(first|last)\s+'
        r'(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)(?:\s+of\s+(?:this|the|that)(?:\s+clip)?)?[.!]?\s*',
        prompt, re.I)
    if not match:
        return None
    length = float(match[2])
    start, end = parent.get('start'), parent.get('end')
    if not all(isinstance(t, (float, int)) and math.isfinite(t) for t in (start, end, length)):
        return None
    if not 1 <= length < end - start or not 0 <= start < end <= duration:
        return None
    from backend.agent.index import file_sha256, transcript_cache_paths
    from backend.cascade_stt import TRANSCRIPT_TAG
    path, _ = transcript_cache_paths(file_sha256(video_path), TRANSCRIPT_TAG)
    try:
        transcript = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(transcript, list):
            return None
    except (OSError, ValueError):
        return None
    if match[1].lower() == 'first':
        end = start + length
    else:
        start = end - length
    return ([{'start': start, 'end': end, 'title': parent.get('title') or 'Trimmed clip',
              'explanation': f'Keeps the {match[1].lower()} {length:g} seconds of the selected clip.'}],
            transcript, {'selection_mode': 'timestamp-edit', 'provider': 'local', 'model': 'timestamp-edit',
                         'selection_note': '', 'usage': {'estimated_cost_usd': 0}, 'intent': 'specific'})
