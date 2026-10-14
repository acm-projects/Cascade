"""Agent tools: get_overview, search_video, inspect_clip, read_transcript, add_candidate,
rank_candidates.

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

from .chunks import OVERVIEW_TRANSCRIPT_CHARS, fmt_time, format_segment, format_transcript
from .index import VideoIndex

MIN_CLIP_SECONDS = 5.0
MAX_CLIP_SECONDS = 60.0
MAX_INSPECT_FRAMES = 6
MAX_OVERLAP_RATIO = 0.5

# The final result is the best TARGET_CLIPS moments of the WHOLE video, spread out: a pick must
# be at least duration / (2 * TARGET_CLIPS) seconds (midpoint to midpoint) from every better
# pick. The gap is relaxed in steps only if the candidates can't otherwise fill the set.
TARGET_CLIPS = 4
SPACING_RELAX_STEPS = (1.0, 0.5, 0.25, 0.0)
MAX_READ_SECONDS = 600.0      # read_transcript window cap, so the agent can't pull hours back in
MAX_READ_CHARS = 20000        # ~5k tokens; a normal 10-minute podcast window fits whole
MAX_NOTABLE_CHARS = 200

OVERVIEW_FRAMES = 6

GET_OVERVIEW_SCHEMA: dict[str, Any] = {
    "name": "get_overview",
    "description": (
        "Get an overview of the whole video: its duration, the transcript (in full for short "
        "videos; for long ones an outline of per-chunk summaries with notable lines), and a few "
        "evenly spaced frames. Must be called first, exactly once; the other tools are "
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
        "name": "read_transcript",
        "description": (
            f"Read the exact timestamped transcript (with speaker labels when known) for a time "
            f"range. At most {int(MAX_READ_SECONDS)} seconds per call - use it to read the words "
            f"around a candidate moment from the outline or a search hit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_time": {"type": "number", "description": "seconds"},
                "end_time": {"type": "number", "description": "seconds"},
            },
            "required": ["start_time", "end_time"],
        },
    },
    {
        "name": "add_candidate",
        "description": (
            f"Add a candidate clip ({MIN_CLIP_SECONDS:g}-{MAX_CLIP_SECONDS:g} seconds long) to the "
            "pool you will rank at the end. Add MANY candidates, from DIFFERENT parts of the video - "
            "not just the first few you find. Start and end at natural sentence boundaries with a "
            "little setup before the payoff. score is your 0-1 estimate of how well it fits the "
            "category. The result shows how your candidates are spread across the video so you can "
            "see which regions still lack any."
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
    {
        "name": "rank_candidates",
        "description": (
            "Finish: rank the candidates you added from best to worst for the category. Compare them "
            "head-to-head - which is funnier or stronger than which, and why. The final "
            f"{TARGET_CLIPS} clips are taken from the top of your ranking, skipping any clip too close "
            "in time to a better-ranked pick so the final set is spread across the video. Call this "
            "once, after you have compared your candidates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ranking": {
                    "type": "array",
                    "description": "Candidate ids, best first.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer", "description": "candidate id from add_candidate"},
                            "note": {"type": "string", "description": "why it ranks here vs its neighbours"},
                        },
                        "required": ["id"],
                    },
                },
            },
            "required": ["ranking"],
        },
    },
]

# Last turn: only the ranking tool, so the agent must commit instead of running out of turns.
FINAL_SCHEMAS = [s for s in TOOL_SCHEMAS if s["name"] == "rank_candidates"]


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
        self.candidates: list[dict[str, Any]] = []
        self.ranking: list[dict[str, Any]] | None = None
        self.finalized = False
        self.spacing_relaxed = False
        self.overview_given = False

    def call(self, name: str, args: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        try:
            if name == "get_overview":
                return self._get_overview()
            if name == "search_video":
                return self._search_video(**args)
            if name == "inspect_clip":
                return self._inspect_clip(**args)
            if name == "read_transcript":
                return self._read_transcript(**args)
            if name == "add_candidate":
                return self._add_candidate(**args)
            if name == "rank_candidates":
                return self._rank_candidates(**args)
            return _text(f"Unknown tool '{name}'"), True
        except TypeError as exc:
            return _text(f"Bad arguments for {name}: {exc}"), True
        except Exception as exc:
            return _text(f"{name} failed: {exc}"), True

    def _get_overview(self):
        if self.overview_given:
            return _text("You already have the overview. Do not call get_overview again."), True
        self.overview_given = True

        idx = self.index
        header = f"Video duration: {idx.duration:.1f}s ({fmt_time(idx.duration)})"
        full = format_transcript(idx.transcript)

        if len(full) <= OVERVIEW_TRANSCRIPT_CHARS:
            # Short video: the whole transcript fits, exactly as before.
            body = f"{header}\n\nTranscript:\n{full or '(no speech detected)'}"
        elif idx.chunk_summaries:
            body = self._outline_text(header)
        else:
            body = (
                f"{header}\n\nTranscript (truncated - it is long and no summaries are available; "
                "use read_transcript or search_video mode='speech' for the rest):\n"
                + full[:OVERVIEW_TRANSCRIPT_CHARS]
            )

        blocks: list[dict[str, Any]] = [{"type": "text", "text": body}]
        n = OVERVIEW_FRAMES
        for i in range(n):
            t = idx.duration * (i + 0.5) / n
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

    def _outline_text(self, header: str) -> str:
        parts = [
            header,
            "",
            f"The transcript is long, so here is an outline of {len(self.index.chunk_summaries)} "
            "chunks instead of the full text. Each chunk gives its time range, speakers, topic, "
            "summary and a few notable lines with exact timestamps. Use read_transcript(start_time, "
            f"end_time) to read the exact words of any stretch (max {int(MAX_READ_SECONDS)}s per "
            "call), search_video to find moments by meaning, and inspect_clip to look at frames.",
            "",
        ]
        for c in self.index.chunk_summaries:
            speakers = ", ".join(f"S{s}" for s in c.get("speakers", [])) or "speakers unknown"
            parts.append(
                f"#{c['index']} [{c['start']:.0f}-{c['end']:.0f}s | "
                f"{fmt_time(c['start'])}-{fmt_time(c['end'])}] ({speakers}) {c['topic']}"
            )
            parts.append(f"  {c['summary']}")
            for n in c.get("notable", []):
                text = n["text"]
                if len(text) > MAX_NOTABLE_CHARS:
                    text = text[:MAX_NOTABLE_CHARS] + "..."
                parts.append(f"  notable [{n['start']:.1f}-{n['end']:.1f}s]: {text}")
        return "\n".join(parts)

    def _read_transcript(self, start_time: float, end_time: float):
        start, end = float(start_time), float(end_time)
        duration = self.index.duration
        if start < 0 or end > duration + 0.01 or end <= start:
            return _text(f"Invalid range. Need 0 <= start < end <= {duration:.1f}s."), True
        if end - start > MAX_READ_SECONDS:
            return _text(
                f"Range too long ({end - start:.0f}s). Read at most {int(MAX_READ_SECONDS)}s at a "
                "time - narrow it to the stretch you care about."
            ), True
        segments = self.index.segments_between(start, end)
        if not segments:
            return _text(f"(no speech between {start:.1f}s and {end:.1f}s)"), False
        # Never error on a dense window (that would cost the agent one of its few turns):
        # return as many whole segments as fit and say where to continue.
        lines: list[str] = []
        used = 0
        for pos, seg in enumerate(segments):
            line = format_segment(seg)
            if lines and used + len(line) + 1 > MAX_READ_CHARS:
                next_start = segments[pos]["start"]
                lines.append(
                    f"(continues - dense speech; call read_transcript with start_time="
                    f"{next_start:.1f} for the rest of this range)"
                )
                break
            lines.append(line)
            used += len(line) + 1
        return _text("\n".join(lines)), False

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

    def _add_candidate(self, start_time: float, end_time: float, reason: str, score: float):
        start, end = float(start_time), float(end_time)
        length = end - start
        if start < 0 or end > self.index.duration + 0.01:
            return _text(f"Clip must lie within 0-{self.index.duration:.1f}s."), True
        if not (MIN_CLIP_SECONDS <= length <= MAX_CLIP_SECONDS):
            return _text(
                f"Clip length must be {MIN_CLIP_SECONDS:g}-{MAX_CLIP_SECONDS:g}s (got {length:.1f}s)."
            ), True
        for existing in self.candidates:
            overlap = min(end, existing["end"]) - max(start, existing["start"])
            if overlap > MAX_OVERLAP_RATIO * min(length, existing["end"] - existing["start"]):
                return _text(
                    f"Overlaps candidate #{existing['id']} ({existing['start']}s-{existing['end']}s). "
                    "Pick a distinct moment."
                ), True
        candidate = {
            "id": len(self.candidates),
            "start": round(start, 1),
            "end": round(end, 1),
            "reason": str(reason),
            "score": round(max(0.0, min(1.0, float(score))), 2),
        }
        self.candidates.append(candidate)
        return _text(
            f"Added candidate #{candidate['id']} ({candidate['start']}s-{candidate['end']}s). "
            f"{len(self.candidates)} candidates so far. {self._coverage_text()}"
        ), False

    def _coverage_text(self) -> str:
        """Candidates per equal slice of the video, so gaps are visible to the agent."""
        regions = TARGET_CLIPS
        counts = [0] * regions
        for c in self.candidates:
            mid = (c["start"] + c["end"]) / 2
            counts[min(regions - 1, int(mid / self.index.duration * regions))] += 1
        size = self.index.duration / regions
        parts = [
            f"{fmt_time(i * size)}-{fmt_time((i + 1) * size)}: {n}" for i, n in enumerate(counts)
        ]
        empty = [i for i, n in enumerate(counts) if n == 0]
        hint = " Some regions have no candidates yet - look there." if empty and len(self.candidates) >= 2 else ""
        return "Candidates by region of the video - " + "; ".join(parts) + "." + hint

    def _rank_candidates(self, ranking: list):
        if not isinstance(ranking, list):
            return _text("ranking must be a list of {id, note} objects, best first."), True
        self.ranking = [e for e in ranking if isinstance(e, dict)]
        self.finalized = True
        if not self.candidates:
            return _text("No candidates were added, so there is nothing to rank."), False
        chosen = self.final_selection()
        lines = [
            f"#{c['rank']}: candidate {c['candidate_id']} ({c['start']}s-{c['end']}s)" for c in chosen
        ]
        note = " Spacing was relaxed to fill the set." if self.spacing_relaxed else ""
        return _text("Final selection: " + "; ".join(lines) + "." + note), False

    def final_selection(self) -> list[dict[str, Any]]:
        """The best TARGET_CLIPS candidates, in ranked order, spread across the video.

        Order = the agent's ranking, then any unranked candidates by their own score. A pick is
        skipped if its midpoint is closer than the minimum gap to a better-ranked pick; the gap
        is relaxed in steps only if that leaves fewer than TARGET_CLIPS.
        """
        by_id = {c["id"]: c for c in self.candidates}
        order: list[int] = []
        notes: dict[int, str] = {}
        for entry in self.ranking or []:
            cid = entry.get("id")
            if isinstance(cid, int) and cid in by_id and cid not in notes:
                order.append(cid)
                notes[cid] = str(entry.get("note", "")).strip()
        order += sorted(
            (cid for cid in by_id if cid not in notes), key=lambda cid: -by_id[cid]["score"]
        )

        def mid(cid: int) -> float:
            return (by_id[cid]["start"] + by_id[cid]["end"]) / 2

        base_gap = self.index.duration / (2 * TARGET_CLIPS)
        chosen: list[int] = []
        strict_count = 0
        for step, factor in enumerate(SPACING_RELAX_STEPS):
            gap = base_gap * factor
            chosen = []
            for cid in order:
                if all(abs(mid(cid) - mid(other)) >= gap for other in chosen):
                    chosen.append(cid)
                if len(chosen) == TARGET_CLIPS:
                    break
            if step == 0:
                strict_count = len(chosen)
            if len(chosen) == TARGET_CLIPS:
                break
        # "Relaxed" only if loosening the gap actually let more picks in.
        self.spacing_relaxed = len(chosen) > strict_count

        return [
            {
                "rank": n + 1,
                "candidate_id": cid,
                "start": by_id[cid]["start"],
                "end": by_id[cid]["end"],
                "reason": by_id[cid]["reason"],
                "score": by_id[cid]["score"],
                "comparison": notes.get(cid, ""),
            }
            for n, cid in enumerate(chosen)
        ]


def _text(message: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": message}]
