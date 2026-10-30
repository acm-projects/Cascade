"""Editor validation; extracted without changing media behavior."""
import json
import html
import math
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException
from backend import broll as stocklib
from .storage import media
from .runtime import jobs_dir, load_json, metadata_exists
from .models import Composition, Effects


def validate_media_edit(state, info):
    validate_edit(state, info['duration'])
    from .retiming import validate_timing
    validate_timing(state,info['cues'],info['duration'])
    if (state.timeline or state.speed) and (state.reframe.enabled or state.composition.mode=='fill'):
        raise HTTPException(422,'Use Fit framing for a retimed Reel; source-time tracking cannot be reused after cuts or speed changes.')
    if info.get('has_video') is False and (
        state.reframe.enabled or state.reframe.selection is not None or state.broll
        or state.composition != Composition() or state.effects != Effects() or state.motion or state.text_overlays or state.timeline or state.speed or state.accents
    ):
        raise HTTPException(422, 'Audio-only clips support trimming and transcript edits; video effects, B-roll, framing, and subject tracking are unavailable.')
    return state

def validate_edit(state, duration):
    if not math.isfinite(duration) or not 0 <= state.start < state.end <= duration or state.end - state.start < .05 - 1e-8:
        raise HTTPException(422, 'Trim must stay inside the generated clip and retain at least 0.05 seconds.')
    if any(not re.fullmatch(r'[0-9]+', key) or len(value)>2000 for key,value in state.texts.items()):
        raise HTTPException(422, 'Caption text must identify a timed segment and stay within 2000 characters.')
    if state.reframe.selection and state.reframe.selection.t>=duration:raise HTTPException(422,'Subject selection is outside this clip.')
    for segment in [*state.audio, *state.motion, *state.text_overlays, *state.accents]:
        if segment.start+segment.duration > duration+.001:
            raise HTTPException(422, 'Timeline items must fit inside the generated clip.')
    if len({s.id for s in state.audio}) != len(state.audio):
        raise HTTPException(422, 'Audio segment IDs must be unique.')
    if state.transition.fade_in+state.transition.fade_out > state.end-state.start:
        raise HTTPException(422, 'Transitions must fit within the trimmed clip.')
    stocklib.validate_segments(state.broll, duration)
    return state


def parse_vtt(text):
    def seconds(value):
        parts = value.replace(',', '.').split(':')
        return sum(float(v) * 60 ** i for i, v in enumerate(reversed(parts)))
    cues = []
    for block in re.split(r'\n\s*\n', text.replace('\r', '')):
        lines = block.splitlines()
        for i, line in enumerate(lines):
            if '-->' not in line:
                continue
            try:
                a, b = line.split('-->')
                start, end = seconds(a.strip()), seconds(b.strip().split()[0])
                # VTT cue markup is removed before entity decoding, so escaped
                # literal angle brackets remain text rather than becoming tags.
                caption = html.unescape(re.sub(r'<[^>]*>', '', '\n'.join(lines[i+1:]))).strip()
                if 0 <= start < end and math.isfinite(end) and caption:
                    cues.append({'start': start, 'end': end, 'text': caption})
            except (ValueError, IndexError):
                pass
    return cues


def trimmed_cues(cues, state):
    return [{**c, 'start': max(c['start'], state.start) - state.start,
             'end': min(c['end'], state.end) - state.start, 'text': state.texts.get(str(index), c['text'])}
            for index, c in enumerate(cues) if c['end'] > state.start and c['start'] < state.end]


def details(jid, clip):
    folder = jobs_dir() / jid
    # Generated media is immutable. Invalidate cached metadata when results/local media change.
    revisions = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in
                      [folder / 'results.json', folder / Path(clip.get('clip_url', '')).name,
                       folder / Path(clip.get('captions_url', '')).name] if p.is_file())
    return json.loads(cached_details(str(folder), jid, json.dumps(clip, sort_keys=True), revisions))


@lru_cache(maxsize=128)
def cached_details(folder_key, jid, serialized, revisions):
    clip = json.loads(serialized)
    try:
        with media(jid, clip) as path:
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height', '-of', 'json', str(path)], capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(probe.stdout)
            duration = float(data['format']['duration'])
            dimensions = next((s for s in data['streams'] if 'width' in s), {})
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise HTTPException(409, 'Clip duration could not be read. Check media and ffprobe availability.')
    if not math.isfinite(duration) or duration <= .05:
        raise HTTPException(409, 'Clip has no playable duration.')
    cues, warning = [], ''
    try:
        with media(jid, clip, True) as path:
            cues = parse_vtt(path.read_text(encoding='utf-8-sig'))
    except (HTTPException, OSError, UnicodeError):
        warning = 'Caption data is unavailable.'
    owner_path = jobs_dir() / jid / 'owner.json'
    kind = load_json(owner_path).get('kind') if metadata_exists(owner_path) else None
    burned = kind == 'caption-styles' or 'burned' in clip.get('explanation', '').lower() or bool(clip.get('captions_burned_in'))
    if burned:
        warning = 'This generated clip has burned-in captions. They cannot be removed or restyled; controls affect additional captions only.'
    has_video = any(s.get('codec_type') == 'video' for s in data['streams'])
    return json.dumps({'duration': duration, 'cues': cues, 'warning': warning, 'burned_in': burned,
                       'has_video': has_video, 'media_kind': 'video' if has_video else 'audio',
                       'has_audio':any(s.get('codec_type')=='audio' for s in data['streams']),'width': dimensions.get('width', 1280), 'height': dimensions.get('height', 720)})
