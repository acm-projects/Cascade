"""Bridge between the website's job pipeline (backend.routers.clips.process_upload) and the clip agent.

`select_with_agent()` returns what the website already expects from a selection engine - clips shaped
{start, end, title, explanation} - plus the transcript (the website writes caption files from it) and
metadata for the job record. Everything after selection (cutting, captions, S3, ownership, projects)
stays the website's own code.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

from backend.cascade_llm import LLMConfigError, make_client, selected_model, selected_provider

from .agent import run_agent
from .intent import classify_request, heuristic_intent
from .fast_selection import MAX_BATCH_CLIPS, run_transcript_selection
from .index import build_index
from .summaries import ensure_summaries
from .tools import MAX_CLIP_SECONDS, TARGET_CLIPS, ToolBox

logger = logging.getLogger("cascade_agent")

# The website lets users pick a clip length of 15, 30 or 60 seconds. As with the engine this
# replaces, a clip may run from 8 seconds up to 1.5x that target, so a joke keeps its setup.
WEBSITE_MIN_CLIP_SECONDS = 8.0
WEBSITE_MAX_CLIP_FACTOR = 1.5
# "Short moments" (a 5 s target): 2-7.5 s clips, the single best beat each, for fast music montages
SHORT_TARGET_SECONDS = 6
SHORT_MIN_CLIP_SECONDS = 2.0
SHORT_MAX_CLIP_SECONDS = 10.0   # a talking moment (an introduction) keeps its whole sentence
MAX_EXPLANATION_CHARS = 700


def transcript_first_request(prompt: str) -> bool:
    """Spoken/topic searches can avoid the full CLIP index; inspection still uses real frames."""
    if re.search(r'\b(visual|visually|fight|fighting|fall|falls|chase|explosion|dance|action|scene|footage)\b|on screen', prompt, re.I):
        return False
    # moods and moments people see more than say: friends together, trips, views, memories
    if re.search(r'\b(nostalgi\w*|memor(y|ies|able)|friends?(hip)?|vibes?|aesthetic|hik(e|es|ing)|trips?|travel\w*|adventures?|'
                 r'scenery|views?|sunsets?|cinematic|montage|b-?roll|candid|wholesome|together)\b', prompt, re.I):
        return False
    # Ordinary highlights/mood prompts should not pay for visual indexing unless
    # they explicitly ask for on-screen evidence.
    return not bool(re.search(r'\b(silent|gesture|gestures|camera|slap|punch|kick|running|jumping)\b', prompt, re.I))


T = r'(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?'   # 5:30, 5:30.01, or 2:16:24 (minutes:seconds:hundredths)
CLIP = r'\s*(?:in|of|from|into)\s+(?:the\s+|a\s+)?(\d{1,2}):(\d{2})\s*(?:min(?:ute)?s?\s*)?(?:length\s+|long\s+)?(?:clip|video|recording)'
RANGE = re.compile(T+r'\s*(?:-|–|to|until)\s*'+T+CLIP, re.I)
SINGLE = re.compile(r'(?:\bat\s+|\bfrom\s+|^|[\s,(])'+T+CLIP, re.I)
SINGLE_SECONDS = 3.0   # a single time ("2:16.24 in the 6:17 clip") becomes a clip this long, starting just before it


def _seconds(m, s, f):
    return int(m)*60+int(s)+(int(f)/10**len(f) if f else 0.)


def add_given_ranges(toolbox, prompt, parts):
    """Times the request writes out become clips before the agent starts: a range ("5:30.01 to 5:31 in the 15:40
    clip") exactly, a single time ("2:16.24 in the 6:17 clip") as a short clip around it. A recording is named by its
    length as a phone shows it. Returns a note for the agent about what was added."""
    if not parts or not prompt: return ''
    find = lambda length: next((p for p in parts if abs(int(p['end']-p['start'])-length) <= 1), None)
    wanted, used = [], []
    for m in RANGE.finditer(prompt):
        part = find(int(m.group(7))*60+int(m.group(8)))
        a, b = _seconds(*m.group(1, 2, 3)), _seconds(*m.group(4, 5, 6))
        if part and b > a: wanted.append((part, a, b, m.group(0))); used.append(m.span())
    for m in SINGLE.finditer(prompt):
        if any(x <= m.start(1) < y for x, y in used): continue
        part = find(int(m.group(4))*60+int(m.group(5)))
        if part: t = _seconds(*m.group(1, 2, 3)); wanted.append((part, max(0., t-.3), t-.3+SINGLE_SECONDS, m.group(0).strip(' ,(')))
    added = []
    floor = toolbox.min_clip_seconds
    for part, a, b, said in wanted:
        start, end = part['start']+a, min(part['end'], part['start']+b)
        toolbox.min_clip_seconds = min(floor, max(.5, end-start))   # an exact range may be shorter than usual clips
        try:
            blocks, err = toolbox.call('add_candidate', {'start_time': round(start, 2), 'end_time': round(end, 2), 'score': .9,
                                                         'asked_for': True, 'title': said[:70], 'reason': 'The exact time the request asks for.'})
        finally:
            toolbox.min_clip_seconds = floor
        if not err:
            toolbox.candidates[-1]['exact'] = True   # the user's own times are kept before any other pick
            added.append(f'{start:.2f}-{end:.2f}s ({said})')
    return (f"\n\n(Already added from the request's exact times: {'; '.join(added)}. Do not add those again; find the other moments.)"
            if added else '')


def footage_note(parts, short):
    """Context for the agent about how the footage was made and what a short-moment request wants."""
    note = ''
    if parts:
        mmss = lambda x: f"{int(x // 60)}:{int(x % 60):02d}"   # as a phone shows it (15:40.5 -> 15:40)
        listed = '; '.join(f"recording {n + 1} ({mmss(p['end'] - p['start'])} long) = {p['start']:.1f}-{p['end']:.1f}s"
                           for n, p in enumerate(parts))
        note += (f"\n\n(Footage: {len(parts)} separate recordings joined end to end, in time order: {listed}. "
                 'Look through all of them and spread the picks across different recordings. A clip must stay inside one recording. '
                 'People name a recording by its length or its order: "5:28 in the 15:40 clip" or "8-9 seconds into the 0:12 clip" '
                 'means that recording\'s start plus that time (e.g. a recording at 148.2-1088.7s, 5:28 in = 148.2 + 328 = 476.2s). '
                 'For every time the request gives, read the transcript and inspect frames around that exact second (people misremember '
                 'by a minute or so: if the described moment is not there, look nearby and in the other recordings for it) and add it '
                 'with asked_for: true. A time RANGE given with no description ("5:28 to 5:31 in the 15:40 clip") is the clip itself: '
                 'add exactly that range with asked_for: true, even if it looks ordinary to you.)')
    if short:
        note += ('\n\n(These are short moments for a fast music edit, like an Instagram reel of friends: each clip is the single best beat - '
                 'a laugh, a reaction, a funny line said in full, friends together, a striking view. Start right before it and cut right after; '
                 'no setup. Visual moments are 2-6 s; a talking moment (an introduction, a chant) keeps its whole sentence, up to 10 s. '
                 'Mix moments where someone says something with purely visual ones.)')
    return note


class SelectionError(Exception):
    """Only safe, locally authored messages belong in this exception (it is shown to users)."""


def requirements_error() -> str | None:
    """Why the agent cannot run right now (for an early, clear error at upload), or None.

    Needs a Deepgram key (transcripts) and the key of the provider chosen by LLM_PROVIDER.
    """
    if not os.environ.get("DEEPGRAM_API_KEY", "").strip():
        return "DEEPGRAM_API_KEY is not set. Add it to .env and restart the server."
    try:
        make_client()  # builds the SDK client only (no network); raises if the key is missing
    except LLMConfigError as error:
        return str(error)
    return None


def _selection_note(result: dict[str, Any], count: int, requested_count: int = TARGET_CLIPS) -> str:
    notes = []
    if count == 0:
        notes.append("The agent did not find any moments that match your request.")
    elif count < requested_count:
        notes.append(
            f"Found {count} distinct strong moment{'s' if count != 1 else ''}; no weaker clips were "
            f"added just to fill {'four' if requested_count==4 else requested_count} slots."
        )
    if count and not result.get("ranked_by_agent"):
        notes.append("The agent ran out of steps before ranking, so clips are ordered by its own confidence scores.")
    if result.get("spacing_relaxed"):
        notes.append("Some clips are closer together than usual because there were not enough well-spaced candidates.")
    return " ".join(notes)


def select_with_agent(
    video_path: Path,
    duration: float,
    search: str,
    target: float,
    progress: Callable[[str], None],
    stage: Callable[[str], Any],
    requested_count: int = TARGET_CLIPS,
    exclude_windows: list | None = None,
    request_prompt: str | None = None,
    references: list | None = None,
    parts: list | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Run the agent on a video. Returns (clips, transcript, metadata).

    `progress` receives every step (indexing, summarizing, each agent turn and tool call), and
    `stage` marks coarse stages for the website's timing panel. Exceptions from `progress`
    (cancellation, timeout) propagate untouched.
    """
    video_path = Path(video_path)
    duration, target = float(duration), float(target)
    short = target <= SHORT_TARGET_SECONDS
    min_len = min(SHORT_MIN_CLIP_SECONDS if short else WEBSITE_MIN_CLIP_SECONDS, duration)
    max_len = min(MAX_CLIP_SECONDS, max(min_len, SHORT_MAX_CLIP_SECONDS if short else target * WEBSITE_MAX_CLIP_FACTOR))

    stage("Transcript and search index")
    # Frames and the temporary MP3 live in a scratch folder, never in the job's folder; the index
    # itself (embeddings, transcript) is cached by file hash for follow-up prompts.
    with tempfile.TemporaryDirectory(prefix="agent_index_") as scratch:
        # Short moments and footage joined from several recordings are found by what is seen as well as said
        speech_first = (transcript_first_request(request_prompt if request_prompt is not None else search)
                        and not short and not parts)
        batch_request = speech_first and requested_count <= MAX_BATCH_CLIPS
        index = build_index(video_path, Path(scratch), progress=progress,
                            **({'visual': False, 'embed_transcript': not batch_request} if speech_first else {}))
        if speech_first and not index.transcript and getattr(index, 'has_video', True):
            # A silent/completely non-speech video still needs visual evidence.
            # Reuse the empty transcript cache rather than transcribing again.
            speech_first = False
            index = build_index(video_path, Path(scratch), progress=progress)

    fast_batch = speech_first and bool(index.transcript) and requested_count <= MAX_BATCH_CLIPS
    if not fast_batch:
        stage("Transcript summaries")
        ensure_summaries(index, progress=progress)

    stage("AI agent selection")
    intent = (heuristic_intent if fast_batch else classify_request)(
        request_prompt if request_prompt is not None else search)
    toolbox = ToolBox(index, video_path, min_clip_seconds=min_len, max_clip_seconds=max_len,
                      target_clips=requested_count, intent=intent, exclude_windows=exclude_windows,
                      references=references, require_count=True, parts=parts)
    given = add_given_ranges(toolbox, request_prompt if request_prompt is not None else search, parts)
    result = (run_transcript_selection(toolbox, search, progress) if fast_batch else
              run_agent(toolbox, search + footage_note(parts, short) + given, progress=progress, target_seconds=target))

    clips = []
    for pick in result["suggestions"]:
        explanation = pick["reason"].strip()
        if pick.get("comparison"):
            explanation += f" (Ranked #{pick['rank']}: {pick['comparison'].strip()})"
        clips.append(
            {
                "start": pick["start"],
                "end": min(pick["end"], duration),
                "title": pick["title"],
                "explanation": explanation[:MAX_EXPLANATION_CHARS],
                **({'reference_matches': pick['reference_matches']} if pick.get('reference_matches') else {}),
            }
        )

    metadata = {
        "intent": intent,
        "index_mode": getattr(index, 'index_mode', 'multimodal'),
        "index_timings": getattr(index, 'timings', {}),
        "selection_mode": result.get('selection_mode', 'tool-agent'),
        "provider": selected_provider(),
        "model": selected_model(),
        "selection_note": _selection_note(result, len(clips), requested_count),
        "usage": result["usage"],
        "candidates_considered": result["candidates_considered"],
        "agent_iterations": result["iterations"],
    }
    if exclude_windows and len(clips) < requested_count:
        metadata['selection_note'] = (f"Found {len(clips)} new clips; others were already in this session. "
                                      + metadata['selection_note'])
    if len(references or []) > 1 and len(clips) < requested_count:
        metadata['selection_note'] = (f'Found {len(clips)} of {requested_count} requested combined matches. '
            'The remaining candidates did not form distinct new moments matching all selected references.')
    return clips, index.transcript, metadata
