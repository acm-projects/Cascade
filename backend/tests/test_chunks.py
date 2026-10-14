"""Tests for transcript chunking and formatting helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import chunks as c  # noqa: E402


def segs(n, length=10.0, speaker_fn=lambda i: 0):
    return [
        {"start": i * length, "end": (i + 1) * length, "text": f"s{i}", "speaker": speaker_fn(i)}
        for i in range(n)
    ]


def test_empty_and_short_are_handled():
    assert c.build_chunks([]) == []
    one = c.build_chunks(segs(5))  # 50s
    assert len(one) == 1 and one[0]["first"] == 0 and one[0]["last"] == 4


def test_chunks_cover_everything_contiguously_on_segment_edges():
    t = segs(120)  # 20 minutes, one speaker
    chunks = c.build_chunks(t)
    assert chunks[0]["first"] == 0 and chunks[-1]["last"] == len(t) - 1
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt["first"] == prev["last"] + 1
    for ch in chunks:
        assert ch["start"] == t[ch["first"]]["start"] and ch["end"] == t[ch["last"]]["end"]
        assert ch["end"] - ch["start"] <= c.MAX_CHUNK_SECONDS + 10  # at most one segment over
    assert [ch["index"] for ch in chunks] == list(range(len(chunks)))


def test_prefers_speaker_turns_after_minimum():
    # speaker flips every 20 segments (200s): first chunk should close at a flip, not at 300s
    t = segs(60, speaker_fn=lambda i: (i // 20) % 2)
    chunks = c.build_chunks(t)
    assert chunks[0]["last"] == 19


def test_forced_split_without_speaker_turns():
    chunks = c.build_chunks(segs(60))  # 600s, never changes speaker
    assert len(chunks) == 2
    assert chunks[0]["end"] - chunks[0]["start"] >= c.MAX_CHUNK_SECONDS


def test_tiny_tail_is_merged():
    # 30 segments*10s = 300s forces a split at the 30th; 3 more segments = 30s tail < 60s
    t = segs(33)
    chunks = c.build_chunks(t)
    assert len(chunks) == 1
    assert chunks[0]["last"] == 32


def test_fmt_time():
    assert c.fmt_time(0) == "0:00"
    assert c.fmt_time(91) == "1:31"
    assert c.fmt_time(3725) == "1:02:05"


def test_format_segment_speaker_prefix_only_when_known():
    assert c.format_segment({"start": 1.0, "end": 2.5, "text": "hi", "speaker": 1}) == "[1.0-2.5s] S1: hi"
    assert c.format_segment({"start": 1.0, "end": 2.5, "text": "hi", "speaker": None}) == "[1.0-2.5s] hi"
    assert c.format_segment({"start": 1.0, "end": 2.5, "text": "hi"}) == "[1.0-2.5s] hi"


def test_is_long_transcript_threshold():
    short = [{"start": 0.0, "end": 1.0, "text": "x" * 100, "speaker": None}]
    long_ = [{"start": 0.0, "end": 1.0, "text": "x" * (c.OVERVIEW_TRANSCRIPT_CHARS + 1), "speaker": None}]
    assert not c.is_long_transcript(short)
    assert c.is_long_transcript(long_)
