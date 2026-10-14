"""Tests for the long-video path: chunk summaries, the condensed overview, read_transcript.

No network: the Anthropic client is a scripted fake.
"""

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import agent as agent_module  # noqa: E402
from agent import summaries  # noqa: E402
from agent import tools  # noqa: E402
from agent.chunks import build_chunks  # noqa: E402
from agent.index import VideoIndex  # noqa: E402
from agent.tools import ToolBox  # noqa: E402


def long_transcript(n=60, length=10.0):
    return [
        {"start": i * length, "end": (i + 1) * length, "text": f"line {i} " + "blah " * 40, "speaker": i % 2}
        for i in range(n)
    ]


def make_index(transcript):
    duration = transcript[-1]["end"] if transcript else 60.0
    return VideoIndex(
        duration=duration,
        frame_interval=2.0,
        frame_times=[0.0],
        frame_embeddings=np.zeros((1, 1), dtype=np.float32),
        transcript=transcript,
        segment_embeddings=np.zeros((len(transcript), 1), dtype=np.float32),
        chunks=build_chunks(transcript),
    )


def toolbox(index):
    return ToolBox(index, Path("fake.mp4"), frame_grabber=lambda p, t: b"jpeg")


class SummaryClient:
    """Fake client: answers every chunk with a valid JSON summary, thinking block first."""

    def __init__(self, fail_on=(), notable_extra=None):
        self.calls = []
        self.fail_on = set(fail_on)
        self.notable_extra = notable_extra or []
        self.messages = self

    def create(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        self.calls.append(kwargs)
        ids = [int(m) for m in re.findall(r"^\[(\d+)\]", prompt, flags=re.M)]
        if ids[0] in self.fail_on:
            raise RuntimeError("model exploded")
        payload = {
            "topic": f"topic {ids[0]}",
            "summary": f"summary of {ids[0]}-{ids[-1]}",
            "notable_segment_ids": [ids[1]] + self.notable_extra,
        }
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking="hmm", signature="sig"),
                SimpleNamespace(type="text", text=json.dumps(payload)),
            ],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
        )


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(summaries, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("ANTHROPIC_CALLS_DISABLED", raising=False)


# ---------- summaries ----------

def test_short_transcript_is_a_noop():
    index = make_index(
        [{"start": 0.0, "end": 5.0, "text": "short", "speaker": None}]
    )

    class Boom:
        messages = None

        def create(self, **kw):
            pytest.fail("no API call expected for a short transcript")

    boom = Boom()
    boom.messages = boom
    summaries.ensure_summaries(index, client=boom)
    assert index.chunk_summaries == []


def test_summaries_map_ids_to_transcript_timestamps_and_skip_thinking():
    index = make_index(long_transcript())
    client = SummaryClient(notable_extra=[9999, "x", -1])  # out-of-chunk / non-int ids
    summaries.ensure_summaries(index, client=client)

    assert len(index.chunk_summaries) == len(index.chunks) >= 2
    first = index.chunk_summaries[0]
    assert first["topic"].startswith("topic")
    assert first["speakers"] == [0, 1]
    # exactly the one valid id survives, with timestamps/text from the transcript itself
    assert len(first["notable"]) == 1
    n = first["notable"][0]
    seg = index.transcript[n["segment_id"]]
    assert (n["start"], n["end"], n["text"]) == (seg["start"], seg["end"], seg["text"])
    # structured output requested with low effort
    cfg = client.calls[0]["output_config"]
    assert cfg["effort"] == "low" and cfg["format"]["type"] == "json_schema"


def test_prompt_is_category_agnostic_and_numbers_segments():
    index = make_index(long_transcript())
    client = SummaryClient()
    summaries.ensure_summaries(index, client=client)
    prompt = client.calls[0]["messages"][0]["content"]
    assert re.search(r"^\[0\] 0:00 S0:", prompt, flags=re.M)
    assert "funny" not in prompt.lower()


def test_usage_is_aggregated_and_priced():
    index = make_index(long_transcript())
    client = SummaryClient()
    summaries.ensure_summaries(index, client=client)
    n = len(index.chunks)
    u = index.summary_usage
    assert u["input_tokens"] == 1000 * n and u["output_tokens"] == 100 * n
    assert u["cost_usd"] == pytest.approx(n * (1000 * 0.10 + 100 * 0.50) / 1_000_000)
    assert u["cached"] is False


def test_cache_hit_needs_no_client_even_when_calls_disabled(monkeypatch):
    transcript = long_transcript()
    summaries.ensure_summaries(make_index(transcript), client=SummaryClient())

    monkeypatch.setenv("ANTHROPIC_CALLS_DISABLED", "true")
    again = make_index(transcript)
    summaries.ensure_summaries(again)  # would raise if it tried to build a client
    assert again.chunk_summaries and again.summary_usage["cached"] is True
    assert again.summary_usage["input_tokens"] == 0


def test_kill_switch_without_cache(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_CALLS_DISABLED", "true")
    with pytest.raises(RuntimeError, match="disabled"):
        summaries.ensure_summaries(make_index(long_transcript()))


def test_partial_failure_uses_placeholder_and_is_not_cached(tmp_path):
    index = make_index(long_transcript())
    second_first_id = index.chunks[1]["first"]
    client = SummaryClient(fail_on=[second_first_id])
    summaries.ensure_summaries(index, client=client)
    assert index.chunk_summaries[0]["topic"].startswith("topic")
    assert index.chunk_summaries[1]["topic"] == "(summary unavailable)"
    assert not list(tmp_path.glob("summaries_*.json"))  # partial results never cached


def test_total_failure_raises():
    index = make_index(long_transcript())
    client = SummaryClient(fail_on=[ch["first"] for ch in index.chunks])
    with pytest.raises(RuntimeError, match="Could not summarize"):
        summaries.ensure_summaries(index, client=client)


# ---------- get_overview: short vs long ----------

def test_short_overview_is_unchanged_full_transcript():
    index = make_index([{"start": 0.0, "end": 3.0, "text": "hello there", "speaker": None}])
    blocks, err = toolbox(index).call("get_overview", {})
    assert not err
    assert blocks[0]["text"].endswith("Transcript:\n[0.0-3.0s] hello there")
    assert "outline" not in blocks[0]["text"]


def test_long_overview_is_an_outline_with_notable_lines():
    index = make_index(long_transcript())
    summaries.ensure_summaries(index, client=SummaryClient())
    blocks, err = toolbox(index).call("get_overview", {})
    assert not err
    text = blocks[0]["text"]
    assert "outline" in text and "read_transcript" in text
    assert "#0 [0-" in text and "(S0, S1)" in text
    assert "notable [" in text
    assert "line 5 blah" not in text.split("notable")[0]  # raw transcript is not dumped
    assert len(text) < tools.OVERVIEW_TRANSCRIPT_CHARS * 2
    assert sum(b["type"] == "image" for b in blocks) == 6


def test_long_overview_without_summaries_falls_back_to_truncation():
    blocks, _ = toolbox(make_index(long_transcript())).call("get_overview", {})
    assert "truncated" in blocks[0]["text"] and "read_transcript" in blocks[0]["text"]


# ---------- read_transcript ----------

def test_read_transcript_returns_timestamped_lines_with_speakers():
    index = make_index(long_transcript())
    blocks, err = toolbox(index).call("read_transcript", {"start_time": 0, "end_time": 25})
    assert not err
    text = blocks[0]["text"]
    assert text.startswith("[0.0-10.0s] S0: line 0")
    assert "[20.0-30.0s] S0: line 2" in text  # overlapping segment is included
    assert "line 3" not in text


def test_read_transcript_bounds_and_window_cap():
    index = make_index(long_transcript())
    box = toolbox(index)
    assert box.call("read_transcript", {"start_time": -1, "end_time": 5})[1]
    assert box.call("read_transcript", {"start_time": 10, "end_time": 10})[1]
    assert box.call("read_transcript", {"start_time": 0, "end_time": 9999})[1]

    index.duration = 3000.0  # window cap needs a video longer than the window
    wide, err = box.call("read_transcript", {"start_time": 0, "end_time": 601})
    assert err and "too long" in wide[0]["text"]


def test_normal_ten_minute_podcast_window_fits_whole():
    # ~150 wpm for 10 minutes is ~10k characters of speech plus labels: must NOT be an error
    seg_text = "word " * 28  # ~140 chars per 10s segment... ~60 segments
    index = make_index(
        [{"start": i * 10.0, "end": (i + 1) * 10.0, "text": seg_text, "speaker": i % 2} for i in range(60)]
    )
    index.duration = 3000.0
    blocks, err = toolbox(index).call("read_transcript", {"start_time": 0, "end_time": 600})
    assert not err
    assert "continues" not in blocks[0]["text"]
    assert len(blocks[0]["text"].splitlines()) == 60


def test_dense_window_is_cut_at_a_segment_with_a_continuation_note_not_an_error():
    dense = make_index(
        [{"start": float(i), "end": i + 1.0, "text": "x" * 400, "speaker": 0} for i in range(100)]
    )
    blocks, err = toolbox(dense).call("read_transcript", {"start_time": 0, "end_time": 100})
    assert not err  # an error would burn one of the agent's few turns
    text = blocks[0]["text"]
    assert len(text) <= tools.MAX_READ_CHARS + 300
    lines = text.splitlines()
    assert lines[-1].startswith("(continues")
    last_seg_line = lines[-2]
    # continuation points at the first segment that was NOT returned
    returned = len(lines) - 1
    assert f"start_time={float(returned):.1f}" in lines[-1]
    assert last_seg_line.startswith(f"[{returned - 1}.0-{returned}.0s]")
    # following the note returns the rest
    follow, err = toolbox(dense).call(
        "read_transcript", {"start_time": float(returned), "end_time": 100}
    )
    assert not err and follow[0]["text"].startswith(f"[{returned}.0-")


def test_read_transcript_empty_range_is_not_an_error():
    index = make_index([{"start": 0.0, "end": 1.0, "text": "a", "speaker": None}])
    index.duration = 100.0
    blocks, err = toolbox(index).call("read_transcript", {"start_time": 50, "end_time": 60})
    assert not err and "no speech" in blocks[0]["text"]


def test_read_transcript_is_offered_in_loop_but_not_on_final_turn_or_overview():
    assert "read_transcript" in [t["name"] for t in tools.TOOL_SCHEMAS]
    assert [t["name"] for t in tools.FINAL_SCHEMAS] == ["rank_candidates"]
    assert "add_candidate" in [t["name"] for t in tools.TOOL_SCHEMAS]
    assert [t["name"] for t in tools.OVERVIEW_ONLY_SCHEMAS] == ["get_overview"]


# ---------- agent usage includes summarization ----------

def test_agent_total_usage_includes_summary_spend():
    index = make_index(long_transcript())
    summaries.ensure_summaries(index, client=SummaryClient())
    spent_in = index.summary_usage["input_tokens"]

    class OneShot:
        messages = None

        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="done")],
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=500, output_tokens=20),
            )

    client = OneShot()
    client.messages = client
    result = agent_module.run_agent(toolbox(index), "funny", client=client)
    assert result["usage"]["input_tokens"] == spent_in + 500
    assert result["usage"]["estimated_cost_usd"] > 0


def test_agent_cost_includes_deepgram_transcription():
    index = make_index(long_transcript())
    index.transcription_cost_usd = 0.52

    class OneShot:
        messages = None

        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="done")],
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
            )

    client = OneShot()
    client.messages = client
    usage = agent_module.run_agent(toolbox(index), "funny", client=client)["usage"]
    llm = (1000 * 0.10 + 100 * 0.50) / 1_000_000
    assert usage["transcription_cost_usd"] == 0.52
    assert usage["estimated_cost_usd"] == pytest.approx(0.52 + llm, abs=1e-5)
