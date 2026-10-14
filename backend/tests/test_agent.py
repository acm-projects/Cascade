"""Unit tests for the clip-finding agent. No network, models, or ffmpeg needed.

Run from backend/:  python -m pytest tests -q
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import agent as agent_module  # noqa: E402
from agent.index import VideoIndex  # noqa: E402
from agent.tools import ToolBox  # noqa: E402


def make_index(duration=100.0):
    times = [float(t) for t in range(0, 100, 2)]
    emb = np.eye(len(times), dtype=np.float32)  # frame i is orthogonal basis vector i

    def encode_visual(q):
        v = np.zeros(len(times), dtype=np.float32)
        v[int(q)] = 1.0  # query "10" matches frame 10 (t=20s)
        return v

    transcript = [
        {"start": 10.0, "end": 14.0, "text": "so the joke is"},
        {"start": 30.0, "end": 33.0, "text": "and that's the punchline"},
    ]
    seg_emb = np.eye(2, dtype=np.float32)
    return VideoIndex(
        duration=duration,
        frame_interval=2.0,
        frame_times=times,
        frame_embeddings=emb,
        transcript=transcript,
        segment_embeddings=seg_emb,
        encode_visual_query=encode_visual,
        encode_text_query=lambda q: seg_emb[int(q)],
    )


def make_toolbox():
    return ToolBox(make_index(), Path("fake.mp4"), frame_grabber=lambda p, t: b"jpeg")


def test_search_visual_returns_best_frame_window():
    hits = make_index().search("10", mode="visual", top_k=3)
    assert hits[0]["start"] == 18.0 and hits[0]["end"] == 22.0
    assert hits[0]["score"] == 1.0


def test_search_nms_spreads_hits():
    index = make_index()
    index.encode_visual_query = lambda q: np.ones(len(index.frame_times), dtype=np.float32)
    hits = index.search("x", top_k=5)
    ends = [h["end"] for h in hits]  # end = t + interval is never clamped here
    assert len(ends) == 5
    assert all(abs(a - b) >= 4 for i, a in enumerate(ends) for b in ends[i + 1:])


def test_search_speech():
    hits = make_index().search("1", mode="speech", top_k=1)
    assert hits[0]["text"] == "and that's the punchline"


def test_inspect_clip_returns_frames_and_transcript():
    blocks, is_error = make_toolbox().call(
        "inspect_clip", {"start_time": 10, "end_time": 20, "num_frames": 3}
    )
    assert not is_error
    assert sum(b["type"] == "image" for b in blocks) == 3
    assert "so the joke is" in blocks[-1]["text"]


def test_inspect_clip_rejects_out_of_bounds_and_caps_frames():
    box = make_toolbox()
    _, err = box.call("inspect_clip", {"start_time": 90, "end_time": 120, "num_frames": 2})
    assert err
    blocks, err = box.call("inspect_clip", {"start_time": 0, "end_time": 50, "num_frames": 50})
    assert not err and sum(b["type"] == "image" for b in blocks) == 6


def test_suggest_clip_validation():
    box = make_toolbox()
    assert box.call("suggest_clip", {"start_time": 0, "end_time": 2, "reason": "r", "score": 0.5})[1]
    assert box.call("suggest_clip", {"start_time": 0, "end_time": 90, "reason": "r", "score": 0.5})[1]
    assert box.call("suggest_clip", {"start_time": 95, "end_time": 105, "reason": "r", "score": 0.5})[1]
    assert not box.call("suggest_clip", {"start_time": 10, "end_time": 20, "reason": "r", "score": 0.9})[1]
    # heavy overlap rejected, distinct clip accepted
    assert box.call("suggest_clip", {"start_time": 12, "end_time": 22, "reason": "r", "score": 0.5})[1]
    assert not box.call("suggest_clip", {"start_time": 40, "end_time": 50, "reason": "r", "score": 0.5})[1]
    assert len(box.suggestions) == 2


def test_unknown_tool_and_bad_args_are_errors_not_exceptions():
    box = make_toolbox()
    assert box.call("nope", {})[1]
    assert box.call("search_video", {"wrong": 1})[1]


def test_overview_has_transcript_and_frames_and_only_works_once():
    box = make_toolbox()
    blocks, err = box.call("get_overview", {})
    assert not err
    assert "Video duration: 100.0s" in blocks[0]["text"]
    assert "[30.0-33.0s] and that's the punchline" in blocks[0]["text"]
    assert sum(b["type"] == "image" for b in blocks) == 6
    blocks, err = box.call("get_overview", {})
    assert err and "already" in blocks[0]["text"]


def test_overview_truncates_long_transcripts():
    index = make_index()
    index.transcript = [{"start": float(i), "end": i + 1.0, "text": "word " * 20} for i in range(200)]
    blocks, _ = ToolBox(index, Path("fake.mp4"), frame_grabber=lambda p, t: b"j").call("get_overview", {})
    assert "truncated" in blocks[0]["text"]


# --- agent loop with a scripted fake client ---

def tool_use(id_, name, **input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def text(t):
    return SimpleNamespace(type="text", text=t)


OVERVIEW_TURN = ([tool_use("ov", "get_overview")], "tool_use")


class FakeClient:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content, stop = self.scripted.pop(0)
        return SimpleNamespace(content=content, stop_reason=stop)


def test_agent_search_inspect_suggest_end_turn():
    client = FakeClient(
        [
            OVERVIEW_TURN,
            ([tool_use("1", "search_video", query="10", mode="visual")], "tool_use"),
            ([tool_use("2", "inspect_clip", start_time=18, end_time=28, num_frames=2)], "tool_use"),
            ([tool_use("3", "suggest_clip", start_time=18, end_time=28, reason="funny", score=0.8)], "tool_use"),
            ([text("Done.")], "end_turn"),
        ]
    )
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    assert result["suggestions"][0]["start"] == 18.0
    assert result["iterations"] == 4  # overview turn is not counted
    assert client.calls[0]["tool_choice"] == {"type": "tool", "name": "get_overview"}
    assert [t["name"] for t in client.calls[0]["tools"]] == ["get_overview"]
    assert "get_overview" not in [t["name"] for t in client.calls[1]["tools"]]
    assert result["summary"] == "Done."
    # tool results are fed back as a user message
    # (the recorded list is the live one, so the final assistant reply is at [-1])
    last_messages = client.calls[-1]["messages"]
    assert last_messages[-2]["content"][0]["type"] == "tool_result"


def test_agent_stops_at_target_suggestions():
    turn = [
        tool_use("a", "suggest_clip", start_time=0, end_time=10, reason="r", score=0.5),
        tool_use("b", "suggest_clip", start_time=20, end_time=30, reason="r", score=0.7),
        tool_use("c", "suggest_clip", start_time=40, end_time=50, reason="r", score=0.9),
    ]
    client = FakeClient([OVERVIEW_TURN, (turn, "tool_use")])
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    assert [s["score"] for s in result["suggestions"]] == [0.9, 0.7, 0.5]  # sorted by score
    assert len(client.calls) == 2  # overview + one working turn


def test_agent_iteration_cap_and_last_turn_only_suggest():
    # Keeps searching forever; the cap must stop it at MAX_ITERATIONS.
    scripted = [OVERVIEW_TURN] + [
        ([tool_use(str(i), "search_video", query="10")], "tool_use")
        for i in range(agent_module.MAX_ITERATIONS)
    ]
    client = FakeClient(scripted)
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    assert len(client.calls) == agent_module.MAX_ITERATIONS + 1
    last = client.calls[-1]
    assert [t["name"] for t in last["tools"]] == ["suggest_clip"]
    assert last["tool_choice"] == {"type": "any"}
    assert "tool_choice" not in client.calls[1]
    assert result["suggestions"] == []


def test_agent_respects_disabled_flag(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_CALLS_DISABLED", "true")
    try:
        agent_module.run_agent(make_toolbox(), "funny")
    except RuntimeError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_usage_is_accumulated_and_priced():
    def with_usage(turn, in_tok, out_tok):
        return (turn[0], turn[1], SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok))

    class UsageClient(FakeClient):
        def create(self, **kwargs):
            self.calls.append(kwargs)
            content, stop, usage = self.scripted.pop(0)
            return SimpleNamespace(content=content, stop_reason=stop, usage=usage)

    client = UsageClient(
        [
            with_usage(OVERVIEW_TURN, 1000, 50),
            with_usage(([text("Done.")], "end_turn"), 3000, 100),
        ]
    )
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    u = result["usage"]
    assert (u["input_tokens"], u["output_tokens"]) == (4000, 150)
    expected = (4000 * 0.10 + 150 * 0.50) / 1_000_000
    assert u["estimated_cost_usd"] == round(expected, 5)


def test_usage_cost_unknown_for_unpriced_model(monkeypatch):
    monkeypatch.setattr(agent_module, "AGENT_MODEL", "some-other-model")
    class OneShot:
        messages = None

        def create(self, **kwargs):
            return SimpleNamespace(
                content=[text("hi")],
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            )

    client = OneShot()
    client.messages = client
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["estimated_cost_usd"] is None


def test_thinking_blocks_are_preserved_in_history():
    thinking = SimpleNamespace(type="thinking", thinking="hmm", signature="sig123")
    redacted = SimpleNamespace(type="redacted_thinking", data="opaque")
    client = FakeClient(
        [
            ([thinking, tool_use("ov", "get_overview")], "tool_use"),
            ([redacted, text("Done.")], "end_turn"),
        ]
    )
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    assert result["summary"] == "Done."
    history = client.calls[1]["messages"]
    assistant_first = history[1]["content"]
    assert assistant_first[0] == {"type": "thinking", "thinking": "hmm", "signature": "sig123"}
    assert assistant_first[1]["type"] == "tool_use"
