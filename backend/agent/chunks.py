"""Transcript chunking and formatting helpers (pure functions, no I/O).

Chunks are 3-5 minute windows whose boundaries fall only on segment edges,
preferring speaker turns, so a chunk never splits a sentence.
"""

from __future__ import annotations

from typing import Any

# Full transcripts up to this many characters go straight into get_overview; longer
# ones are condensed into per-chunk summaries (see summaries.py).
OVERVIEW_TRANSCRIPT_CHARS = 6000

MIN_CHUNK_SECONDS = 180.0   # don't close a chunk on a speaker turn before this
MAX_CHUNK_SECONDS = 300.0   # always close by the next segment edge after this
MIN_TAIL_SECONDS = 60.0     # a shorter leftover merges into the previous chunk


def fmt_time(seconds: float) -> str:
    """Seconds -> m:ss (or h:mm:ss over an hour)."""
    t = int(round(seconds))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_segment(seg: dict[str, Any], with_speaker: bool = True) -> str:
    """'[start-end s] S1: text' - speaker prefix only when we know the speaker."""
    prefix = ""
    if with_speaker and seg.get("speaker") is not None:
        prefix = f"S{seg['speaker']}: "
    return f"[{seg['start']:.1f}-{seg['end']:.1f}s] {prefix}{seg['text']}"


def format_transcript(transcript: list[dict[str, Any]]) -> str:
    return "\n".join(format_segment(seg) for seg in transcript)


def is_long_transcript(transcript: list[dict[str, Any]]) -> bool:
    return len(format_transcript(transcript)) > OVERVIEW_TRANSCRIPT_CHARS


def build_chunks(transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split segments into chunks: [{index, start, end, first, last}] (first/last are
    inclusive indexes into `transcript`). Empty transcript -> no chunks."""
    if not transcript:
        return []

    spans: list[list[int]] = []  # [first, last]
    first = 0
    for i in range(1, len(transcript)):
        chunk_start = transcript[first]["start"]
        elapsed = transcript[i - 1]["end"] - chunk_start
        speaker_turn = transcript[i].get("speaker") != transcript[i - 1].get("speaker")
        if elapsed >= MAX_CHUNK_SECONDS or (elapsed >= MIN_CHUNK_SECONDS and speaker_turn):
            spans.append([first, i - 1])
            first = i
    spans.append([first, len(transcript) - 1])

    # Fold a very short tail into the previous chunk.
    if len(spans) > 1:
        last_first, last_last = spans[-1]
        if transcript[last_last]["end"] - transcript[last_first]["start"] < MIN_TAIL_SECONDS:
            spans[-2][1] = last_last
            spans.pop()

    return [
        {
            "index": n,
            "start": transcript[a]["start"],
            "end": transcript[b]["end"],
            "first": a,
            "last": b,
        }
        for n, (a, b) in enumerate(spans)
    ]
