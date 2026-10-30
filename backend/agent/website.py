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
from .intent import classify_request
from .fast_selection import MAX_TRANSCRIPT_CHARS, MAX_BATCH_CLIPS, run_transcript_selection
from .chunks import format_transcript
from .index import build_index
from .summaries import ensure_summaries
from .tools import MAX_CLIP_SECONDS, TARGET_CLIPS, ToolBox

logger = logging.getLogger("cascade_agent")

# The website lets users pick a clip length of 15, 30 or 60 seconds. As with the engine this
# replaces, a clip may run from 8 seconds up to 1.5x that target, so a joke keeps its setup.
WEBSITE_MIN_CLIP_SECONDS = 8.0
WEBSITE_MAX_CLIP_FACTOR = 1.5
MAX_EXPLANATION_CHARS = 700


def transcript_first_request(prompt: str) -> bool:
    """Spoken/topic searches can avoid the full CLIP index; inspection still uses real frames."""
    if re.search(r'\b(visual|visually|fight|fighting|fall|falls|chase|explosion|dance|action|scene|footage)\b|on screen', prompt, re.I):
        return False
    return bool(re.search(r'\b(said|says|speech|transcript|talk|talks|discuss|discusses|explain|explains|explanation|interview|documentary|history|historical|healthcare|news|topic)\b', prompt, re.I))


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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Run the agent on a video. Returns (clips, transcript, metadata).

    `progress` receives every step (indexing, summarizing, each agent turn and tool call), and
    `stage` marks coarse stages for the website's timing panel. Exceptions from `progress`
    (cancellation, timeout) propagate untouched.
    """
    video_path = Path(video_path)
    duration, target = float(duration), float(target)
    min_len = min(WEBSITE_MIN_CLIP_SECONDS, duration)
    max_len = min(MAX_CLIP_SECONDS, max(min_len, target * WEBSITE_MAX_CLIP_FACTOR))

    stage("Transcript and search index")
    # Frames and the temporary MP3 live in a scratch folder, never in the job's folder; the index
    # itself (embeddings, transcript) is cached by file hash for follow-up prompts.
    with tempfile.TemporaryDirectory(prefix="agent_index_") as scratch:
        speech_first = transcript_first_request(request_prompt if request_prompt is not None else search)
        index = build_index(video_path, Path(scratch), progress=progress, **({'visual': False} if speech_first else {}))

    fast_batch = (speech_first and bool(index.transcript) and requested_count <= MAX_BATCH_CLIPS
                  and len(format_transcript(index.transcript)) <= MAX_TRANSCRIPT_CHARS)
    if not fast_batch:
        stage("Transcript summaries")
        ensure_summaries(index, progress=progress)

    stage("AI agent selection")
    intent = classify_request(request_prompt if request_prompt is not None else search)
    toolbox = ToolBox(index, video_path, min_clip_seconds=min_len, max_clip_seconds=max_len,
                      target_clips=requested_count, intent=intent, exclude_windows=exclude_windows,
                      references=references, require_count=True)
    result = (run_transcript_selection(toolbox, search, progress) if fast_batch else
              run_agent(toolbox, search, progress=progress, target_seconds=target))

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
