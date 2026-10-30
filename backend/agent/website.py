"""Bridge between the website's job pipeline (backend.routers.clips.process_upload) and the clip agent.

`select_with_agent()` returns what the website already expects from a selection engine - clips shaped
{start, end, title, explanation} - plus the transcript (the website writes caption files from it) and
metadata for the job record. Everything after selection (cutting, captions, S3, ownership, projects)
stays the website's own code.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from backend.cascade_llm import LLMConfigError, make_client, selected_model, selected_provider

from .agent import run_agent
from .index import build_index
from .summaries import ensure_summaries
from .tools import MAX_CLIP_SECONDS, TARGET_CLIPS, ToolBox

logger = logging.getLogger("cascade_agent")

# The website lets users pick a clip length of 15, 30 or 60 seconds. As with the engine this
# replaces, a clip may run from 8 seconds up to 1.5x that target, so a joke keeps its setup.
WEBSITE_MIN_CLIP_SECONDS = 8.0
WEBSITE_MAX_CLIP_FACTOR = 1.5
MAX_EXPLANATION_CHARS = 700


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
        index = build_index(video_path, Path(scratch), progress=progress)

    stage("Transcript summaries")
    ensure_summaries(index, progress=progress)

    stage("AI agent selection")
    toolbox = ToolBox(index, video_path, min_clip_seconds=min_len, max_clip_seconds=max_len, target_clips=requested_count)
    result = run_agent(toolbox, search, progress=progress, target_seconds=target)

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
            }
        )

    metadata = {
        "provider": selected_provider(),
        "model": selected_model(),
        "selection_note": _selection_note(result, len(clips), requested_count),
        "usage": result["usage"],
        "candidates_considered": result["candidates_considered"],
        "agent_iterations": result["iterations"],
    }
    return clips, index.transcript, metadata
