"""Prompt caching: a stable prefix on both providers, correct token accounting, no edits to sent history.

No network. (Whether the live APIs actually report cache hits needs a real call, which costs money.)
"""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import agent as agent_module  # noqa: E402
from agent.index import VideoIndex  # noqa: E402
from agent.tools import ToolBox  # noqa: E402
from cascade_llm import call_cost  # noqa: E402

HAIKU, LUNA = "claude-haiku-5-5", "gpt-6-luna"


def make_toolbox():
    times = [float(t) for t in range(0, 100, 2)]
    index = VideoIndex(
        duration=100.0, frame_interval=2.0, frame_times=times,
        frame_embeddings=np.eye(len(times), dtype=np.float32),
        transcript=[{"start": 10.0, "end": 14.0, "text": "so the joke is", "speaker": 0}],
        segment_embeddings=np.eye(1, dtype=np.float32),
        encode_visual_query=lambda q: np.zeros(len(times), dtype=np.float32),
        encode_text_query=lambda q: np.zeros(1, dtype=np.float32),
    )
    return ToolBox(index, Path("fake.mp4"), frame_grabber=lambda p, t: b"jpeg")


@pytest.fixture(autouse=True)
def default_provider(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


# ---------------------------------------------------------------- Anthropic fakes
def a_tool(i, name, **args):
    return SimpleNamespace(type="tool_use", id=i, name=name, input=args)


class SnapshotAnthropic:
    """Records a deep copy of every request, so later appends cannot hide an edit of earlier messages."""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": copy.deepcopy(kwargs["messages"])})
        content, stop, usage = self.scripted.pop(0)
        return SimpleNamespace(content=content, stop_reason=stop, usage=usage)


def a_usage(fresh=100, read=0, written=0, out=10):
    return SimpleNamespace(
        input_tokens=fresh, cache_read_input_tokens=read, cache_creation_input_tokens=written, output_tokens=out
    )


def long_anthropic_run():
    n = agent_module.MAX_ITERATIONS
    script = [([a_tool("o", "get_overview")], "tool_use", a_usage())]
    script += [([a_tool(f"s{i}", "search_video", query="10")], "tool_use", a_usage()) for i in range(n)]
    client = SnapshotAnthropic(script)
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    return client, result


def test_anthropic_instructions_are_identical_on_every_turn():
    client, _ = long_anthropic_run()
    systems = {c["system"] for c in client.calls}
    assert len(systems) == 1 and "FINAL turn" not in next(iter(systems))


def test_anthropic_history_only_grows_by_appending():
    """The property prompt caching depends on: each request starts with the previous request, unchanged."""
    client, _ = long_anthropic_run()
    for before, after in zip(client.calls, client.calls[1:]):
        assert after["messages"][: len(before["messages"])] == before["messages"]
        assert len(after["messages"]) > len(before["messages"])


def test_anthropic_notes_are_added_only_to_the_pending_message():
    client, _ = long_anthropic_run()
    last = client.calls[-1]["messages"]
    pending = last[-1]  # the tool results sent with the final request
    assert pending["role"] == "user" and pending["content"][-1]["type"] == "text"
    assert "FINAL turn" in pending["content"][-1]["text"]
    # the very first user message was never touched
    assert client.calls[0]["messages"][0]["content"].startswith("Find the 4 best")
    assert last[0]["content"] == client.calls[0]["messages"][0]["content"]
    # no note before the reminders start
    assert not any(b.get("type") == "text" for b in client.calls[2]["messages"][-1]["content"])


def test_anthropic_requests_enable_automatic_caching():
    client, _ = long_anthropic_run()
    assert all(c["cache_control"] == {"type": "ephemeral"} for c in client.calls)


def test_anthropic_usage_adds_cached_tokens_back_into_the_total():
    # Anthropic reports input_tokens WITHOUT the cached parts
    client = SnapshotAnthropic([
        ([a_tool("o", "get_overview")], "tool_use", a_usage(fresh=100, read=0, written=1500, out=20)),
        ([SimpleNamespace(type="text", text="done")], "end_turn", a_usage(fresh=50, read=1500, written=400, out=30)),
    ])
    usage = agent_module.run_agent(make_toolbox(), "funny", client=client)["usage"]
    assert usage["input_tokens"] == (100 + 0 + 1500) + (50 + 1500 + 400)
    assert usage["cached_input_tokens"] == 1500
    expected = call_cost(HAIKU, 1600, 20, 0, 1500) + call_cost(HAIKU, 1950, 30, 1500, 400)
    assert usage["estimated_cost_usd"] == pytest.approx(expected, abs=1e-5)


# ---------------------------------------------------------------- OpenAI fakes
def o_call(i, name, args=None):
    return SimpleNamespace(type="function_call", id=f"fc_{i}", call_id=i, name=name, arguments=json.dumps(args or {}))


def o_response(*items, i=1000, o=50, cached=0, written=0):
    return SimpleNamespace(
        status="completed", output=list(items),
        usage=SimpleNamespace(
            input_tokens=i, output_tokens=o,
            input_tokens_details=SimpleNamespace(cached_tokens=cached, cache_write_tokens=written),
        ),
    )


class SnapshotOpenAI:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append({**kwargs, "input": list(kwargs["input"])})
        return self.scripted.pop(0)


def long_openai_run(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    n = agent_module.MAX_ITERATIONS
    script = [o_response(o_call("o", "get_overview"))]
    script += [o_response(o_call(f"s{i}", "search_video", {"query": "10"})) for i in range(n)]
    client = SnapshotOpenAI(script)
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    return client, result


def test_openai_instructions_identical_and_history_append_only(monkeypatch):
    client, _ = long_openai_run(monkeypatch)
    assert len({c["instructions"] for c in client.calls}) == 1
    for before, after in zip(client.calls, client.calls[1:]):
        assert after["input"][: len(before["input"])] == before["input"]


def test_openai_notes_are_trailing_user_messages_in_order(monkeypatch):
    client, _ = long_openai_run(monkeypatch)
    n = agent_module.MAX_ITERATIONS
    final_input = client.calls[-1]["input"]
    notes = [
        i["content"] for i in final_input
        if isinstance(i, dict) and i.get("role") == "user" and isinstance(i["content"], str)
        and i["content"].startswith(("Turn ", "This is your FINAL"))
    ]
    assert len(notes) == 3 and notes[0].startswith(f"Turn {n - 2} of {n}") and "FINAL turn" in notes[2]
    # the note rides at the very end of the request that carries it
    assert final_input[-1] == {"role": "user", "content": notes[2]}


def test_openai_usage_reads_cached_and_written_tokens(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    done = SimpleNamespace(type="message", role="assistant", content=[SimpleNamespace(type="output_text", text="done")])
    client = SnapshotOpenAI([
        o_response(o_call("o", "get_overview"), i=2000, o=100, cached=0, written=1800),
        o_response(done, i=2600, o=40, cached=1800, written=600),
    ])
    usage = agent_module.run_agent(make_toolbox(), "funny", client=client)["usage"]
    assert usage["input_tokens"] == 4600 and usage["cached_input_tokens"] == 1800
    expected = call_cost(LUNA, 2000, 100, 0, 1800) + call_cost(LUNA, 2600, 40, 1800, 600)
    assert usage["estimated_cost_usd"] == pytest.approx(expected, abs=1e-5)


# ---------------------------------------------------------------- pricing
def test_cache_reads_are_cheap_and_writes_cost_a_quarter_more():
    plain = call_cost(HAIKU, 10_000, 0)
    assert call_cost(HAIKU, 10_000, 0, cached_tokens=10_000) == pytest.approx(plain * 0.1)
    assert call_cost(HAIKU, 10_000, 0, cache_write_tokens=10_000) == pytest.approx(plain * 1.25)
    assert call_cost(LUNA, 10_000, 0, cached_tokens=10_000) == pytest.approx(call_cost(LUNA, 10_000, 0) * 0.1)
    assert call_cost(LUNA, 10_000, 0, cache_write_tokens=10_000) == pytest.approx(call_cost(LUNA, 10_000, 0) * 1.25)


def test_cost_mixes_ordinary_cached_and_written_tokens_and_picks_the_tier_from_the_total():
    cost = call_cost(LUNA, 1000, 200, cached_tokens=600, cache_write_tokens=300)
    assert cost == pytest.approx((100 * 0.10 + 600 * 0.01 + 300 * 0.125 + 200 * 0.50) / 1e6)
    # over Luna's 272K line every rate switches to the large tier, including the cache rates
    big = call_cost(LUNA, 300_000, 0, cached_tokens=200_000, cache_write_tokens=50_000)
    assert big == pytest.approx((50_000 * 0.20 + 200_000 * 0.02 + 50_000 * 0.25) / 1e6)


def test_old_cost_calls_still_work():
    assert call_cost(HAIKU, 1000, 1000) == pytest.approx((1000 * 0.10 + 1000 * 0.50) / 1e6)
    assert call_cost("some-other-model", 1, 1, 1, 1) is None
    # absurd inputs are clamped instead of producing a negative price
    assert call_cost(HAIKU, 100, 0, cached_tokens=500, cache_write_tokens=500) >= 0
