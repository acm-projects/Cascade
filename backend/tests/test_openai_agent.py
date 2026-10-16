"""The agent loop, summarizer and Trends tagging on OpenAI (Responses API), with a fake client.

These prove our adapter against the documented API shape; whether the live API accepts the same
requests is checked separately with a real key (see scripts/check_openai.py).
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
from agent.chunks import build_chunks  # noqa: E402
from agent.index import VideoIndex  # noqa: E402
from agent.tools import ToolBox  # noqa: E402
from cascade_llm import MODELS, OpenAIConversation, call_cost  # noqa: E402
from trends import pipeline  # noqa: E402

LUNA = MODELS["openai"]


# ---------- fake Responses API ----------

def fc(call_id, name, args=None, raw=None):
    return SimpleNamespace(
        type="function_call", id=f"fc_{call_id}", call_id=call_id, name=name,
        arguments=raw if raw is not None else json.dumps(args or {}),
    )


def reasoning(n):
    return SimpleNamespace(type="reasoning", id=f"rs_{n}", summary=[])


def message(text):
    return SimpleNamespace(type="message", role="assistant", content=[SimpleNamespace(type="output_text", text=text)])


def response(*items, i=1000, o=100, cached=0, status="completed"):
    return SimpleNamespace(
        status=status,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        output=list(items),
        usage=SimpleNamespace(input_tokens=i, output_tokens=o, input_tokens_details=SimpleNamespace(cached_tokens=cached)),
    )


class FakeOpenAI:
    """`responses.create` returns scripted responses; each call's input list is snapshotted."""

    def __init__(self, *scripted):
        self.scripted = list(scripted)
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append({**kwargs, "input": list(kwargs["input"])})
        return self.scripted.pop(0)


def make_index(duration=100.0):
    times = [float(t) for t in range(0, 100, 2)]
    return VideoIndex(
        duration=duration, frame_interval=2.0, frame_times=times,
        frame_embeddings=np.eye(len(times), dtype=np.float32),
        transcript=[{"start": 10.0, "end": 14.0, "text": "so the joke is", "speaker": 0}],
        segment_embeddings=np.eye(1, dtype=np.float32),
        encode_visual_query=lambda q: np.zeros(len(times), dtype=np.float32),
        encode_text_query=lambda q: np.zeros(1, dtype=np.float32),
    )


def toolbox():
    return ToolBox(make_index(), Path("fake.mp4"), frame_grabber=lambda p, t: b"jpeg")


def add(call_id, start, end, score=0.9):
    return fc(call_id, "add_candidate", {"start_time": start, "end_time": end, "reason": "r", "score": score})


@pytest.fixture(autouse=True)
def openai_selected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")  # the one switch


def outputs_by_call_id(items):
    return {i["call_id"]: i["output"] for i in items if isinstance(i, dict) and i.get("type") == "function_call_output"}


# ---------- the agent loop ----------

def test_full_loop_request_shapes_history_and_guards():
    r0, r1, r2 = reasoning(0), reasoning(1), reasoning(2)
    call_overview = fc("c0", "get_overview")
    client = FakeOpenAI(
        response(r0, call_overview, i=1500, o=50),
        response(
            r1,
            fc("c1", "search_video", {"query": "10", "mode": "visual"}),
            add("c2", 10, 20),
            fc("c3", "add_candidate", raw="{not json"),   # unparseable arguments
            fc("c4", "get_overview"),                     # not offered on this turn
            i=3000, o=200, cached=1000,
        ),
        response(r2, fc("c5", "rank_candidates", {"ranking": [{"id": 0, "note": "only one"}]}), i=3500, o=80),
    )
    tb = toolbox()
    result = agent_module.run_agent(tb, "funny", client=client)
    assert len(client.calls) == 3

    # turn 0: forced get_overview, OpenAI-shaped tool, explicit reasoning effort and generous output cap
    first = client.calls[0]
    assert first["model"] == LUNA
    assert first["tool_choice"] == {"type": "function", "name": "get_overview"}
    assert [t["name"] for t in first["tools"]] == ["get_overview"]
    assert first["tools"][0]["type"] == "function" and first["tools"][0]["strict"] is False
    assert first["tools"][0]["parameters"] == {"type": "object", "properties": {}}
    assert first["reasoning"] == {"effort": "low"}
    assert first["max_output_tokens"] >= 8000
    assert "best clips of a whole video" in first["instructions"]
    assert first["input"][0]["role"] == "user" and "'funny'" in first["input"][0]["content"]

    # turn 1 sees: user, the reasoning item we were sent, the call, its output, then the frames
    second = client.calls[1]
    assert second["tool_choice"] == "auto"
    assert second["input"][1] is r0 and second["input"][2] is call_overview
    assert outputs_by_call_id(second["input"])["c0"].startswith("Video duration")
    frames_msg = second["input"][-1]
    assert frames_msg["role"] == "user"
    assert sum(c["type"] == "input_image" for c in frames_msg["content"]) == 6

    # turn 2: every call_id got exactly one output, including the rejected ones
    third = client.calls[2]
    positions = {id(item): n for n, item in enumerate(third["input"])}
    assert id(r1) in positions, "the reasoning item from turn 1 must be sent back"
    first_output = min(n for n, i in enumerate(third["input"]) if isinstance(i, dict) and i.get("type") == "function_call_output" and i["call_id"] == "c1")
    assert positions[id(r1)] < first_output  # reasoning goes back before the tool outputs
    outs = outputs_by_call_id(third["input"])
    assert set(outs) == {"c0", "c1", "c2", "c3", "c4"}
    assert sum(1 for i in third["input"] if isinstance(i, dict) and i.get("type") == "function_call_output") == 5
    assert outs["c2"].startswith("Added candidate #0")
    assert outs["c3"].startswith("ERROR:") and "Invalid JSON" in outs["c3"]
    assert outs["c4"].startswith("ERROR:") and "not available this turn" in outs["c4"]

    assert result["ranked_by_agent"] is True and result["iterations"] == 2
    assert [s["candidate_id"] for s in result["suggestions"]] == [0]
    # only the one valid add_candidate ran; the unparseable and the not-offered calls never touched the toolbox
    assert [c["id"] for c in tb.candidates] == [0] and tb.overview_given is True


def test_usage_and_cost_use_lunas_pricing_including_cached_tokens():
    client = FakeOpenAI(
        response(reasoning(0), fc("c0", "get_overview"), i=2000, o=100, cached=0),
        response(reasoning(1), fc("c1", "rank_candidates", {"ranking": []}), i=2200, o=50, cached=2000),
    )
    usage = agent_module.run_agent(toolbox(), "funny", client=client)["usage"]
    assert usage["input_tokens"] == 4200 and usage["output_tokens"] == 150
    expected = call_cost(LUNA, 2000, 100) + call_cost(LUNA, 2200, 50, cached_tokens=2000)
    assert usage["estimated_cost_usd"] == pytest.approx(expected, abs=1e-5)
    assert usage["model"] == LUNA


def test_final_turn_offers_only_rank_and_requires_a_tool():
    n = agent_module.MAX_ITERATIONS
    script = [response(fc("o", "get_overview"))]
    script += [response(reasoning(i), fc(f"s{i}", "search_video", {"query": "10"})) for i in range(n - 1)]
    # on the final turn the model asks for add_candidate even though only rank_candidates is offered
    script += [response(fc("a", "add_candidate", {"start_time": 10, "end_time": 20, "reason": "r", "score": 0.5}))]
    client = FakeOpenAI(*script)
    conv = OpenAIConversation(client, LUNA)
    tb = toolbox()
    result = agent_module.run_agent(tb, "funny", conversation=conv)

    last = client.calls[-1]
    assert last["tool_choice"] == "required"
    assert [t["name"] for t in last["tools"]] == ["rank_candidates"]
    # the forbidden call was answered with an error and never executed
    answered = conv.input[-1]
    assert answered["type"] == "function_call_output" and answered["call_id"] == "a"
    assert answered["output"].startswith("ERROR:") and "not available this turn" in answered["output"]
    assert tb.candidates == []
    assert result["ranked_by_agent"] is False


def test_assistant_text_ends_the_loop_and_becomes_the_summary():
    client = FakeOpenAI(response(fc("o", "get_overview")), response(message("That is everything.")))
    result = agent_module.run_agent(toolbox(), "funny", client=client)
    assert result["summary"] == "That is everything." and result["iterations"] == 1
    assert len(client.calls) == 2


def test_incomplete_and_failed_responses_raise_clear_errors():
    with pytest.raises(RuntimeError, match="cut off"):
        agent_module.run_agent(toolbox(), "funny", client=FakeOpenAI(response(status="incomplete")))
    failed = response(status="failed")
    failed.error = SimpleNamespace(message="overloaded")
    with pytest.raises(RuntimeError, match="overloaded"):
        agent_module.run_agent(toolbox(), "funny", client=FakeOpenAI(failed))


def test_reasoning_effort_is_low_on_every_turn():
    client = FakeOpenAI(response(fc("o", "get_overview")), response(message("done")))
    agent_module.run_agent(toolbox(), "funny", client=client)
    assert [c["reasoning"] for c in client.calls] == [{"effort": "low"}, {"effort": "low"}]


# ---------- images inside tool results ----------

def test_image_array_mode_puts_frames_inside_the_function_call_output():
    client = FakeOpenAI(response(fc("o", "get_overview")), response(message("done")))
    conv = OpenAIConversation(client, LUNA, image_mode="array")
    agent_module.run_agent(toolbox(), "funny", conversation=conv)
    second = client.calls[1]["input"]
    output = outputs_by_call_id(second)["o"]
    assert isinstance(output, list)
    assert output[0]["type"] == "input_text" and output[0]["text"].startswith("Video duration")
    images = [c for c in output if c["type"] == "input_image"]
    assert len(images) == 6 and images[0]["image_url"].startswith("data:image/jpeg;base64,")
    assert second[-1]["type"] == "function_call_output"  # no separate frames message


def test_user_message_mode_is_the_safe_default_and_keeps_frame_labels_in_order():
    client = FakeOpenAI(response(fc("o", "get_overview")), response(message("done")))
    agent_module.run_agent(toolbox(), "funny", client=client)
    second = client.calls[1]["input"]
    assert isinstance(outputs_by_call_id(second)["o"], str)
    content = second[-1]["content"]
    kinds = [c["type"] for c in content]
    assert kinds[0] == "input_text" and kinds.count("input_image") == 6
    labels = [c["text"] for c in content if c["type"] == "input_text" and c["text"].startswith("Frame at")]
    assert len(labels) == 6  # each image keeps its "Frame at Ns:" label, in order


def test_bad_image_mode_is_rejected():
    with pytest.raises(ValueError):
        OpenAIConversation(FakeOpenAI(), LUNA, image_mode="carrier-pigeon")


# ---------- summaries on OpenAI ----------

def long_transcript(n=60, length=10.0):
    return [{"start": i * length, "end": (i + 1) * length, "text": f"line {i} " + "blah " * 40, "speaker": i % 2} for i in range(n)]


class SummaryOpenAI:
    def __init__(self):
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["input"][0]["content"][0]["text"]
        ids = [int(m) for m in re.findall(r"^\[(\d+)\]", prompt, flags=re.M)]
        payload = {"topic": f"topic {ids[0]}", "summary": f"summary {ids[0]}-{ids[-1]}", "notable_segment_ids": [ids[1]]}
        return response(reasoning(0), message(json.dumps(payload)), i=800, o=120, cached=300)


def test_summaries_run_on_openai_with_strict_schema_and_lunas_price(monkeypatch, tmp_path):
    monkeypatch.setattr(summaries, "CACHE_DIR", tmp_path)
    transcript = long_transcript()
    index = VideoIndex(
        duration=600.0, frame_interval=2.0, frame_times=[0.0], frame_embeddings=np.zeros((1, 1), dtype=np.float32),
        transcript=transcript, segment_embeddings=np.zeros((len(transcript), 1), dtype=np.float32),
        chunks=build_chunks(transcript),
    )
    client = SummaryOpenAI()
    summaries.ensure_summaries(index, client=client)
    assert len(index.chunk_summaries) == len(index.chunks) >= 2
    first = index.chunk_summaries[0]
    assert first["topic"].startswith("topic") and len(first["notable"]) == 1
    seg = transcript[first["notable"][0]["segment_id"]]
    assert first["notable"][0]["start"] == seg["start"]  # timestamps from the transcript, not the model
    call = client.calls[0]
    assert call["text"]["format"]["type"] == "json_schema" and call["text"]["format"]["strict"] is True
    assert call["reasoning"] == {"effort": "low"}
    u = index.summary_usage
    assert u["input_tokens"] == 800 * len(index.chunks)
    assert u["cost_known"] is True and u["cost_usd"] > 0


# ---------- Trends tagging on OpenAI ----------

TAGS = {
    "hook_style": "cold open", "pacing": "fast", "visual_style": ["jump cuts"], "topics": ["fitness"],
    "tone": "upbeat", "audio_style": ["music"], "call_to_action": "",
}


@pytest.fixture
def frames(tmp_path):
    out = []
    for i in range(2):
        p = tmp_path / f"f{i}.jpg"
        p.write_bytes(b"\xff\xd8fake-jpeg-%d" % i)
        out.append(p)
    return out


def test_trends_tagging_uses_openai_and_caches(monkeypatch, tmp_path, frames):
    monkeypatch.setattr(pipeline, "TAGS_CACHE_DIR", tmp_path / "tags")
    (tmp_path / "tags").mkdir()
    client = FakeOpenAI(response(reasoning(0), message(json.dumps(TAGS))))
    monkeypatch.setattr(pipeline, "make_client", lambda provider: client)

    assert pipeline.extract_tags(frames, "hello world") == TAGS
    call = client.calls[0]
    content = call["input"][0]["content"]
    assert content[0]["type"] == "input_text" and "hello world" in content[0]["text"]
    assert [c["type"] for c in content[1:]] == ["input_image", "input_image"]
    assert call["text"]["format"]["strict"] is True and call["text"]["format"]["name"] == "video_tags"

    # second run: served from the on-disk cache, no API call (the fake has nothing left to return)
    assert pipeline.extract_tags(frames, "hello world") == TAGS
    assert len(client.calls) == 1


def test_trends_missing_key_names_the_selected_providers_variable(monkeypatch, tmp_path, frames):
    monkeypatch.setattr(pipeline, "TAGS_CACHE_DIR", tmp_path / "tags")
    (tmp_path / "tags").mkdir()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        pipeline.extract_tags(frames, "t")

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        pipeline.extract_tags(frames, "t")
