"""Agent tools: search_video, inspect_clip, suggest_clip.

Each tool returns (content_blocks, is_error) where content_blocks is what goes
into the Anthropic tool_result. Errors are returned to the model (not raised) so
it can correct its arguments.
"""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from .index import VideoIndex

MIN_CLIP_SECONDS = 5.0
MAX_CLIP_SECONDS = 60.0
MAX_INSPECT_FRAMES = 6
MAX_OVERLAP_RATIO = 0.5

OVERVIEW_FRAMES = 6
OVERVIEW_TRANSCRIPT_CHARS = 6000

GET_OVERVIEW_SCHEMA: dict[str, Any] = {
    "name": "get_overview",
    "description": (
        "Get an overview of the whole video: its duration, the full timestamped transcript, and "
        "a few evenly spaced frames. Must be called first, exactly once; the search tools are "
        "available afterwards."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

OVERVIEW_ONLY_SCHEMAS: list[dict[str, Any]] = [GET_OVERVIEW_SCHEMA]

# Tools available after the overview (get_overview is deliberately not offered again).
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_video",
        "description": (
            "Search the video's embeddings with a text query. mode='visual' matches the query "
            "against what appears on screen (CLIP); mode='speech' matches against the spoken "
            "transcript. Returns the top matching time windows with similarity scores. Use "
            "concrete queries (e.g. 'person laughing', 'someone falling over'), not abstract ones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {"type": "string", "enum": ["visual", "speech"]},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "inspect_clip",
        "description": (
            "Look at a time range of the video: returns num_frames evenly spaced frames as images "
            "plus the transcript text spoken in that range. Use this to verify a candidate before "
            "suggesting it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_time": {"type": "number", "description": "seconds"},
                "end_time": {"type": "number", "description": "seconds"},
                "num_frames": {"type": "integer", "minimum": 1, "maximum": MAX_INSPECT_FRAMES},
            },
            "required": ["start_time", "end_time", "num_frames"],
        },
    },
    {
        "name": "suggest_clip",
        "description": (
            f"Record a final clip suggestion ({MIN_CLIP_SECONDS:g}-{MAX_CLIP_SECONDS:g} seconds long). "
            "Call once per distinct clip. Include a short reason and a 0-1 confidence score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_time": {"type": "number"},
                "end_time": {"type": "number"},
                "reason": {"type": "string"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["start_time", "end_time", "reason", "score"],
        },
    },
]

SUGGEST_ONLY_SCHEMAS = [s for s in TOOL_SCHEMAS if s["name"] == "suggest_clip"]


def grab_frame_jpeg(video_path: Path, timestamp: float, width: int = 512) -> bytes:
    """Extract one downscaled JPEG frame at `timestamp` seconds."""
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error",
            "-ss", str(timestamp), "-i", str(video_path),
            "-frames:v", "1",
            "-vf", f"scale={width}:-2",
            "-f", "image2", "-c:v", "mjpeg", "pipe:1",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(f"Could not extract frame at {timestamp}s")
    return result.stdout


class ToolBox:
    def __init__(
        self,
        index: VideoIndex,
        video_path: Path,
        frame_grabber: Callable[[Path, float], bytes] = grab_frame_jpeg,
    ):
        self.index = index
        self.video_path = video_path
        self.frame_grabber = frame_grabber
        self.suggestions: list[dict[str, Any]] = []
        self.overview_given = False

    def call(self, name: str, args: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        try:
            if name == "get_overview":
                return self._get_overview()
            if name == "search_video":
                return self._search_video(**args)
            if name == "inspect_clip":
                return self._inspect_clip(**args)
            if name == "suggest_clip":
                return self._suggest_clip(**args)
            return _text(f"Unknown tool '{name}'"), True
        except TypeError as exc:
            return _text(f"Bad arguments for {name}: {exc}"), True
        except Exception as exc:
            return _text(f"{name} failed: {exc}"), True

    def _get_overview(self):
        if self.overview_given:
            return _text("You already have the overview. Do not call get_overview again."), True
        self.overview_given = True

        lines = [
            f"[{seg['start']:.1f}-{seg['end']:.1f}s] {seg['text']}" for seg in self.index.transcript
        ]
        transcript = "\n".join(lines) or "(no speech detected)"
        if len(transcript) > OVERVIEW_TRANSCRIPT_CHARS:
            transcript = (
                transcript[:OVERVIEW_TRANSCRIPT_CHARS]
                + "\n... (transcript truncated; use search_video mode='speech' for the rest)"
            )

        blocks: list[dict[str, Any]] = [
            {"type": "text", "text": f"Video duration: {self.index.duration:.1f}s\n\nTranscript:\n{transcript}"}
        ]
        n = OVERVIEW_FRAMES
        for i in range(n):
            t = self.index.duration * (i + 0.5) / n
            jpeg = self.frame_grabber(self.video_path, t)
            blocks.append({"type": "text", "text": f"Frame at {t:.1f}s:"})
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(jpeg).decode("utf-8"),
                    },
                }
            )
        return blocks, False

    def _search_video(self, query: str, mode: str = "visual", top_k: int = 5):
        if not query.strip():
            return _text("query must not be empty"), True
        if mode not in ("visual", "speech"):
            return _text("mode must be 'visual' or 'speech'"), True
        top_k = max(1, min(int(top_k), 10))
        hits = self.index.search(query, mode=mode, top_k=top_k)
        if not hits:
            return _text("No results (the video may have no transcript)."), False
        return _text(json.dumps(hits)), False

    def _inspect_clip(self, start_time: float, end_time: float, num_frames: int):
        start, end = float(start_time), float(end_time)
        if start < 0 or end > self.index.duration + 0.01 or end <= start:
            return _text(
                f"Invalid range. Need 0 <= start < end <= {self.index.duration:.1f}s."
            ), True
        n = max(1, min(int(num_frames), MAX_INSPECT_FRAMES))
        blocks: list[dict[str, Any]] = []
        for i in range(n):
            t = start + (end - start) * (i + 0.5) / n
            jpeg = self.frame_grabber(self.video_path, t)
            blocks.append({"type": "text", "text": f"Frame at {t:.1f}s:"})
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(jpeg).decode("utf-8"),
                    },
                }
            )
        spoken = self.index.transcript_between(start, end) or "(no speech in this range)"
        blocks.append({"type": "text", "text": f"Transcript {start:.1f}s-{end:.1f}s: {spoken}"})
        return blocks, False

    def _suggest_clip(self, start_time: float, end_time: float, reason: str, score: float):
        start, end = float(start_time), float(end_time)
        length = end - start
        if start < 0 or end > self.index.duration + 0.01:
            return _text(f"Clip must lie within 0-{self.index.duration:.1f}s."), True
        if not (MIN_CLIP_SECONDS <= length <= MAX_CLIP_SECONDS):
            return _text(
                f"Clip length must be {MIN_CLIP_SECONDS:g}-{MAX_CLIP_SECONDS:g}s (got {length:.1f}s)."
            ), True
        for existing in self.suggestions:
            overlap = min(end, existing["end"]) - max(start, existing["start"])
            if overlap > MAX_OVERLAP_RATIO * min(length, existing["end"] - existing["start"]):
                return _text(
                    f"Overlaps an existing suggestion ({existing['start']}s-{existing['end']}s). "
                    "Pick a distinct moment."
                ), True
        self.suggestions.append(
            {
                "start": round(start, 1),
                "end": round(end, 1),
                "reason": str(reason),
                "score": round(max(0.0, min(1.0, float(score))), 2),
            }
        )
        return _text(f"Recorded suggestion {len(self.suggestions)}."), False


def _text(message: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": message}]
