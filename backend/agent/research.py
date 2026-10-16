"""Per-video memory of what the agent found, saved after every run.

Keyed by the video's file hash, so any later prompt on the same video can see what earlier prompts
turned up (the candidate moments, why they mattered, and which four were picked).

This module only STORES and LOADS. Nothing feeds these findings back into a prompt yet: how a
follow-up should use them (reference text? preloaded pool? exclude repeats?) is a product decision
for the branching feature.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .index import CACHE_DIR

RESEARCH_DIR = CACHE_DIR  # next to the other per-video caches (git-ignored)
MAX_RUNS = 20  # newest runs kept per video


def _path(video_key: str):
    # video_key is a sha256 hex digest made by us, but never trust it as a path component
    safe = "".join(c for c in video_key if c.isalnum())[:64]
    return RESEARCH_DIR / f"research_{safe}.json"


def load_runs(video_key: str) -> list[dict[str, Any]]:
    """Earlier runs for this video, oldest first. Missing or unreadable file -> []."""
    if not video_key:
        return []
    try:
        data = json.loads(_path(video_key).read_text(encoding="utf-8"))
        runs = data.get("runs", [])
        return runs if isinstance(runs, list) else []
    except (OSError, ValueError, AttributeError):
        return []


def save_run(
    video_key: str,
    prompt: str,
    candidates: list[dict[str, Any]],
    selection: list[dict[str, Any]],
    duration: float,
) -> None:
    """Append one run (prompt, every candidate the agent added, and the final picks)."""
    if not video_key:
        return
    run = {
        "prompt": prompt,
        "created_at": time.time(),
        "duration": duration,
        "candidates": [
            {k: c[k] for k in ("id", "start", "end", "reason", "score") if k in c} for c in candidates
        ],
        "selected": [
            {k: s[k] for k in ("rank", "candidate_id", "start", "end", "comparison") if k in s}
            for s in selection
        ],
    }
    runs = (load_runs(video_key) + [run])[-MAX_RUNS:]
    path = _path(video_key)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps({"video_key": video_key, "runs": runs}), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash never leaves a half-written file
