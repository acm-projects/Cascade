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


def add(box, start, end, score=0.5, reason="r"):
    return box.call("add_candidate", {"start_time": start, "end_time": end, "reason": reason, "score": score})


def test_add_candidate_validation():
    box = make_toolbox()
    assert add(box, 0, 2)[1]      # too short
    assert add(box, 0, 95)[1]     # too long (limit is 90s)
    assert add(box, 95, 105)[1]   # past the end
    assert not add(box, 10, 20, 0.9)[1]
    assert add(box, 12, 22)[1]    # heavy overlap with candidate #0 is rejected
    blocks, err = add(box, 40, 50)
    assert not err and "Added candidate #1" in blocks[0]["text"]
    assert len(box.candidates) == 2 and [c["id"] for c in box.candidates] == [0, 1]


def test_coverage_text_shows_which_regions_have_candidates():
    box = make_toolbox()  # 100s video -> four 25s regions
    add(box, 5, 15)
    blocks, _ = add(box, 30, 40)
    text = blocks[0]["text"]
    assert "0:00-0:25: 1" in text and "0:25-0:50: 1" in text and "0:50-1:15: 0" in text
    assert "no candidates yet" in text


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


def cand_call(id_, start, end, score, reason="r"):
    return tool_use(id_, "add_candidate", start_time=start, end_time=end, reason=reason, score=score)


def test_agent_gathers_candidates_ranks_and_the_loop_ends_on_rank():
    adds = [
        cand_call("a", 10, 20, 0.5),   # mid 15
        cand_call("b", 20, 30, 0.9),   # mid 25  (too close to a better pick if ranked 1st)
        cand_call("c", 50, 60, 0.6),   # mid 55
        cand_call("d", 80, 90, 0.7),   # mid 85
        cand_call("e", 65, 75, 0.4),   # mid 70
    ]
    ranking = [
        {"id": 1, "note": "b beats everything"},
        {"id": 3, "note": "d over c"},
        {"id": 2, "note": "c over e"},
        {"id": 4, "note": "e over a"},
        {"id": 0, "note": "a last"},
    ]
    client = FakeClient(
        [
            OVERVIEW_TURN,
            ([tool_use("1", "search_video", query="10", mode="visual"),
              tool_use("2", "inspect_clip", start_time=18, end_time=28, num_frames=2)], "tool_use"),
            (adds, "tool_use"),
            ([tool_use("r", "rank_candidates", ranking=ranking)], "tool_use"),
        ]
    )
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    assert len(client.calls) == 4          # overview + 3 working turns; nothing after rank
    assert result["iterations"] == 3
    assert result["ranked_by_agent"] is True and result["candidates_considered"] == 5
    picked = [(s["rank"], s["candidate_id"]) for s in result["suggestions"]]
    # ranked b(25), d(85), c(55), e(70), a(15); gap 12.5: b ok, d ok, c ok, e (70 vs 55/85: 15) ok -> 4
    assert picked == [(1, 1), (2, 3), (3, 2), (4, 4)]
    assert result["suggestions"][0]["comparison"] == "b beats everything"
    assert result["spacing_relaxed"] is False
    assert "get_overview" not in [t["name"] for t in client.calls[1]["tools"]]
    names = [t["name"] for t in client.calls[1]["tools"]]
    assert {"add_candidate", "rank_candidates", "search_video", "read_transcript"} <= set(names)


def test_selection_skips_clustered_picks_to_spread_across_the_video():
    box = make_toolbox()  # 100s -> base gap 12.5s between midpoints
    for start, end in [(10, 20), (20, 30), (50, 60), (80, 90), (65, 75)]:
        add(box, start, end)
    # agent loves the two adjacent clips at the start: ids 0 and 1
    box.call("rank_candidates", {"ranking": [{"id": 0}, {"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]})
    picked = [c["candidate_id"] for c in box.final_selection()]
    assert picked == [0, 2, 3, 4]      # id 1 (mid 25) is within 12.5s of better-ranked id 0 (mid 15)
    assert box.spacing_relaxed is False


def test_selection_relaxes_spacing_only_when_it_has_to():
    box = make_toolbox()
    for start, end in [(10, 20), (20, 30), (50, 60), (80, 90)]:
        add(box, start, end)
    box.call("rank_candidates", {"ranking": [{"id": i} for i in range(4)]})
    picked = [c["candidate_id"] for c in box.final_selection()]
    assert sorted(picked) == [0, 1, 2, 3]   # only four exist, so the close pair is let back in
    assert box.spacing_relaxed is True


def test_fewer_candidates_than_target_is_not_reported_as_relaxed():
    box = make_toolbox()
    add(box, 10, 20)
    add(box, 60, 70)
    box.call("rank_candidates", {"ranking": [{"id": 0}, {"id": 1}]})
    assert len(box.final_selection()) == 2
    assert box.spacing_relaxed is False


def test_ranking_is_lenient_and_unranked_candidates_fall_back_to_score():
    box = make_toolbox()
    add(box, 10, 20, 0.2)
    add(box, 40, 50, 0.9)
    add(box, 70, 80, 0.5)
    blocks, err = box.call(
        "rank_candidates", {"ranking": [{"id": 2}, {"id": 2}, {"id": 99}, {"id": "x"}, "junk"]}
    )
    assert not err and "Final selection" in blocks[0]["text"]
    # ranked id 2 first (dups/unknown ignored), the rest by their own score: 1 (0.9), then 0 (0.2)
    assert [c["candidate_id"] for c in box.final_selection()] == [2, 1, 0]
    assert box.call("rank_candidates", {"ranking": "not a list"})[1]


def test_rank_with_no_candidates_is_harmless():
    box = make_toolbox()
    blocks, err = box.call("rank_candidates", {"ranking": []})
    assert not err and "nothing to rank" in blocks[0]["text"]
    assert box.finalized and box.final_selection() == []


def test_agent_that_never_ranks_falls_back_to_candidate_scores():
    client = FakeClient(
        [
            OVERVIEW_TURN,
            ([cand_call("a", 10, 20, 0.3), cand_call("b", 50, 60, 0.9), cand_call("c", 80, 90, 0.6)], "tool_use"),
            ([text("I think that's all.")], "end_turn"),
        ]
    )
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    assert result["ranked_by_agent"] is False
    assert [s["score"] for s in result["suggestions"]] == [0.9, 0.6, 0.3]
    assert [s["rank"] for s in result["suggestions"]] == [1, 2, 3]


def test_agent_iteration_cap_and_final_turn_only_offers_rank():
    # Keeps searching forever; the cap must stop it at MAX_ITERATIONS.
    scripted = [OVERVIEW_TURN] + [
        ([tool_use(str(i), "search_video", query="10")], "tool_use")
        for i in range(agent_module.MAX_ITERATIONS)
    ]
    client = FakeClient(scripted)
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    assert len(client.calls) == agent_module.MAX_ITERATIONS + 1
    last = client.calls[-1]
    assert [t["name"] for t in last["tools"]] == ["rank_candidates"]
    assert last["tool_choice"] == {"type": "any"}
    assert "tool_choice" not in client.calls[1]
    assert result["suggestions"] == [] and result["ranked_by_agent"] is False


def test_final_forced_turn_rank_is_executed():
    n = agent_module.MAX_ITERATIONS
    scripted = [OVERVIEW_TURN, ([cand_call("a", 10, 20, 0.5), cand_call("b", 60, 70, 0.8)], "tool_use")]
    scripted += [([tool_use(f"s{i}", "search_video", query="10")], "tool_use") for i in range(n - 2)]
    scripted += [([tool_use("r", "rank_candidates", ranking=[{"id": 0, "note": "a wins"}, {"id": 1}])], "tool_use")]
    client = FakeClient(scripted)
    result = agent_module.run_agent(make_toolbox(), "funny", client=client)
    assert result["ranked_by_agent"] is True
    assert [s["candidate_id"] for s in result["suggestions"]] == [0, 1]
    assert result["suggestions"][0]["comparison"] == "a wins"


def test_prompt_states_the_best_of_whole_video_spread_out_goal():
    prompt = agent_module.SYSTEM_PROMPT
    assert str(agent_module.TARGET_SUGGESTIONS) in prompt and agent_module.TARGET_SUGGESTIONS == 4
    for needle in ("ENTIRE video", "spread out", "COMPARE", "rank_candidates", "add_candidate"):
        assert needle in prompt


def test_missing_api_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        agent_module.run_agent(make_toolbox(), "funny")
    except RuntimeError as exc:
        assert "ANTHROPIC_API_KEY is not set" in str(exc)
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
    from cascade_llm import clients

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setitem(clients.MODELS, "anthropic", "some-other-model")
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


def test_clip_limits_and_turn_budget():
    assert agent_module.MAX_ITERATIONS == 8
    box = make_toolbox()
    blocks, err = add(box, 0, 90)   # exactly the limit is fine; a 90s podcast bit used to be rejected at 60
    assert not err
    blocks, err = add(box, 91, 100)  # 9s, in bounds, no overlap: fine
    assert not err
    other = make_toolbox()
    blocks, err = add(other, 0, 91)  # one second over the limit
    assert err and "5-90s" in blocks[0]["text"]


def test_tool_not_offered_this_turn_is_never_executed():
    n = agent_module.MAX_ITERATIONS
    scripted = [OVERVIEW_TURN] + [
        ([tool_use(f"s{i}", "search_video", query="10")], "tool_use") for i in range(n - 1)
    ]
    # final turn offers only rank_candidates, but the model asks for add_candidate anyway
    scripted.append(([cand_call("x", 10, 20, 0.9)], "tool_use"))
    client = FakeClient(scripted)
    box = make_toolbox()
    result = agent_module.run_agent(box, "funny", client=client)
    assert box.candidates == []           # it was NOT run
    last_results = client.calls[-1]["messages"][-1]["content"]
    assert last_results[0]["is_error"] is True
    assert "not available this turn" in last_results[0]["content"][0]["text"]
    assert result["ranked_by_agent"] is False


def test_pacing_notes_push_toward_ranking_before_the_last_turn():
    n = agent_module.MAX_ITERATIONS
    scripted = [OVERVIEW_TURN] + [
        ([tool_use(f"s{i}", "search_video", query="10")], "tool_use") for i in range(n)
    ]
    client = FakeClient(scripted)
    agent_module.run_agent(make_toolbox(), "funny", client=client)
    systems = [c["system"] for c in client.calls]          # [overview, turn 1, ..., turn n]
    assert "Stop researching" not in systems[1] and "Stop researching" not in systems[n - 3]
    assert "Stop researching" in systems[n - 2] and "Stop researching" in systems[n - 1]
    assert "FINAL turn" in systems[n] and "Stop researching" not in systems[n]
