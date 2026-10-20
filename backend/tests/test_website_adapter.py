"""The adapter between the website's job pipeline and the agent, plus the per-job clip limits and titles.

No network, models or ffmpeg: the index, summaries and agent are stubbed.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent import agent as agent_module  # noqa: E402
from backend.agent import website  # noqa: E402
from backend.agent.index import VideoIndex  # noqa: E402
from backend.agent.tools import MAX_CLIP_SECONDS, ToolBox  # noqa: E402
from backend.cascade_llm import LLMConfigError, make_client  # noqa: E402


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-test")


# ---------------------------------------------------------------- requirements_error
def test_ready_when_both_keys_are_present():
    assert website.requirements_error() is None


def test_missing_deepgram_key_is_reported_first(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "  ")
    assert "DEEPGRAM_API_KEY" in website.requirements_error()


def test_missing_key_of_the_selected_provider_only(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert "ANTHROPIC_API_KEY" in website.requirements_error()
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert website.requirements_error() is None  # the Anthropic key is irrelevant now
    monkeypatch.delenv("OPENAI_API_KEY")
    assert "OPENAI_API_KEY" in website.requirements_error()


def test_a_bad_provider_setting_is_a_clear_message(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    assert "LLM_PROVIDER must be" in website.requirements_error()


def test_config_errors_are_a_safe_runtime_error_subclass(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(LLMConfigError) as caught:
        make_client()
    assert isinstance(caught.value, RuntimeError) and "ANTHROPIC_API_KEY" in str(caught.value)


# ---------------------------------------------------------------- select_with_agent
class Recorder:
    def __init__(self, suggestions=None, **result_overrides):
        self.suggestions = suggestions if suggestions is not None else [
            {"rank": 1, "candidate_id": 0, "start": 5.0, "end": 20.0, "title": "The joke", "reason": "a clear punchline",
             "score": 0.9, "comparison": "beats the pun"},
            {"rank": 2, "candidate_id": 1, "start": 50.0, "end": 70.0, "title": "The fall", "reason": "slapstick",
             "score": 0.7, "comparison": ""},
        ]
        self.result_overrides = result_overrides
        self.stages, self.steps, self.work_dirs = [], [], []
        self.toolbox = None
        self.run_kwargs = None


@pytest.fixture
def stubbed(monkeypatch):
    def install(rec, duration=120.0):
        index = SimpleNamespace(
            duration=duration, transcript=[{"start": 1.0, "end": 2.0, "text": "hi", "speaker": 0}],
            chunk_summaries=[], summary_usage={}, transcription_cost_usd=0.0, video_key="k",
        )

        def fake_build(video_path, work_dir, progress=None):
            rec.work_dirs.append(Path(work_dir))
            assert Path(work_dir).is_dir()
            progress("Indexing video")
            return index

        monkeypatch.setattr(website, "build_index", fake_build)
        monkeypatch.setattr(website, "ensure_summaries", lambda idx, progress=None: progress("Summaries ready"))

        def fake_run(toolbox, category, progress=None, target_seconds=None, **kw):
            rec.toolbox, rec.run_kwargs = toolbox, {"category": category, "target_seconds": target_seconds}
            progress("Agent turn 1/8")
            result = {
                "suggestions": rec.suggestions, "candidates_considered": 6, "ranked_by_agent": True,
                "spacing_relaxed": False, "iterations": 3, "summary": "",
                "usage": {"input_tokens": 100, "output_tokens": 10, "model": "claude-haiku-5-5", "estimated_cost_usd": 0.01},
            }
            result.update(rec.result_overrides)
            return result

        monkeypatch.setattr(website, "run_agent", fake_run)
        return index

    return install


def run(rec, target=30, duration=120.0):
    return website.select_with_agent(
        Path("video.mp4"), duration, "funny", target, rec.steps.append, rec.stages.append
    )


def test_stages_and_steps_flow_through_in_order(stubbed):
    rec = Recorder()
    stubbed(rec)
    run(rec)
    assert rec.stages == ["Transcript and search index", "Transcript summaries", "AI agent selection"]
    assert rec.steps == ["Indexing video", "Summaries ready", "Agent turn 1/8"]


def test_index_work_uses_a_scratch_folder_that_is_removed(stubbed):
    rec = Recorder()
    stubbed(rec)
    run(rec)
    assert len(rec.work_dirs) == 1 and "agent_index_" in rec.work_dirs[0].name
    assert not rec.work_dirs[0].exists()  # frames and the temporary MP3 never outlive the build


@pytest.mark.parametrize("target,low,high", [(15, 8.0, 22.5), (30, 8.0, 45.0), (60, 8.0, 90.0)])
def test_clip_limits_follow_the_users_chosen_length(stubbed, target, low, high):
    rec = Recorder()
    stubbed(rec)
    run(rec, target=target)
    assert (rec.toolbox.min_clip_seconds, rec.toolbox.max_clip_seconds) == (low, high)
    assert rec.run_kwargs == {"category": "funny", "target_seconds": float(target)}


def test_limits_never_exceed_the_global_cap_or_the_video(stubbed):
    rec = Recorder()
    stubbed(rec)
    run(rec, target=600)
    assert rec.toolbox.max_clip_seconds == MAX_CLIP_SECONDS
    rec2 = Recorder()
    stubbed(rec2, duration=5.0)
    run(rec2, target=15, duration=5.0)
    assert rec2.toolbox.min_clip_seconds == 5.0  # a 5-second source: the global floor, not 8s


def test_clips_have_the_shape_the_website_expects(stubbed):
    rec = Recorder()
    stubbed(rec)
    clips, transcript, meta = run(rec)
    assert clips[0] == {
        "start": 5.0, "end": 20.0, "title": "The joke",
        "explanation": "a clear punchline (Ranked #1: beats the pun)",
    }
    assert clips[1]["explanation"] == "slapstick"  # no comparison note: no empty parenthesis
    assert transcript == [{"start": 1.0, "end": 2.0, "text": "hi", "speaker": 0}]
    assert meta["provider"] == "anthropic" and meta["model"] == "claude-haiku-5-5"
    assert meta["usage"]["estimated_cost_usd"] == 0.01 and meta["candidates_considered"] == 6


def test_end_times_are_clamped_and_explanations_capped(stubbed):
    long_pick = {"rank": 1, "candidate_id": 0, "start": 100.0, "end": 130.0, "title": "t", "reason": "x" * 2000,
                 "score": 0.5, "comparison": ""}
    rec = Recorder(suggestions=[long_pick])
    stubbed(rec)
    clips, _, _ = run(rec, duration=120.0)
    assert clips[0]["end"] == 120.0 and len(clips[0]["explanation"]) == website.MAX_EXPLANATION_CHARS


def test_selection_notes_explain_short_results_honestly(stubbed):
    def note(**kw):
        rec = Recorder(**kw)
        stubbed(rec)
        return run(rec)[2]["selection_note"]

    assert note() == "Found 2 distinct strong moments; no weaker clips were added just to fill four slots."
    rec = Recorder(suggestions=[])
    stubbed(rec)
    assert "did not find any moments" in run(rec)[2]["selection_note"]
    assert "ran out of steps before ranking" in note(ranked_by_agent=False)
    assert "closer together" in note(spacing_relaxed=True)
    four = [{"rank": i, "candidate_id": i, "start": 10.0 * i, "end": 10.0 * i + 9, "title": "t", "reason": "r", "score": 0.5,
             "comparison": ""} for i in range(1, 5)]
    rec = Recorder(suggestions=four)
    stubbed(rec)
    assert run(rec)[2]["selection_note"] == ""  # a full, clean result needs no note


def test_cancellation_and_timeouts_from_progress_pass_through_untouched(stubbed, monkeypatch):
    class Cancelled(Exception):
        pass

    rec = Recorder()
    stubbed(rec)

    def stop(message):
        raise Cancelled()

    with pytest.raises(Cancelled):
        website.select_with_agent(Path("v.mp4"), 120.0, "funny", 30, stop, rec.stages.append)


# ---------------------------------------------------------------- titles and limits in the tools / agent
def make_box(**kw):
    times = [float(t) for t in range(0, 100, 2)]
    index = VideoIndex(
        duration=100.0, frame_interval=2.0, frame_times=times,
        frame_embeddings=np.eye(len(times), dtype=np.float32),
        transcript=[{"start": 10.0, "end": 14.0, "text": "so the joke is", "speaker": 0}],
        segment_embeddings=np.eye(1, dtype=np.float32),
        encode_visual_query=lambda q: np.zeros(len(times), dtype=np.float32),
        encode_text_query=lambda q: np.zeros(1, dtype=np.float32),
    )
    return ToolBox(index, Path("fake.mp4"), frame_grabber=lambda p, t: b"j", **kw)


def test_candidates_carry_a_short_title_that_falls_back_to_the_reason():
    box = make_box()
    box.call("add_candidate", {"start_time": 10, "end_time": 20, "reason": "a joke lands", "score": 0.9, "title": "x" * 200})
    box.call("add_candidate", {"start_time": 40, "end_time": 50, "reason": "a fall happens", "score": 0.5})
    assert box.candidates[0]["title"] == "x" * 80
    assert box.candidates[1]["title"] == "a fall happens"
    box.call("rank_candidates", {"ranking": [{"id": 0}, {"id": 1}]})
    assert [c["title"] for c in box.final_selection()] == ["x" * 80, "a fall happens"]


def test_per_job_limits_are_enforced_and_named_in_the_error():
    box = make_box(min_clip_seconds=8.0, max_clip_seconds=22.5)
    blocks, err = box.call("add_candidate", {"start_time": 0, "end_time": 30, "reason": "r", "score": 0.5})
    assert err and "8-22.5s" in blocks[0]["text"]
    assert box.call("add_candidate", {"start_time": 0, "end_time": 6, "reason": "r", "score": 0.5})[1]  # under 8s
    assert not box.call("add_candidate", {"start_time": 0, "end_time": 22, "reason": "r", "score": 0.5})[1]


def test_limits_cannot_be_widened_beyond_the_global_ones():
    box = make_box(min_clip_seconds=1.0, max_clip_seconds=5000.0)
    assert (box.min_clip_seconds, box.max_clip_seconds) == (5.0, MAX_CLIP_SECONDS)


def test_the_agent_is_told_this_runs_limits_only_when_they_differ():
    class Client:
        def __init__(self):
            self.messages = self
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs["messages"][0]["content"])
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="done")], stop_reason="end_turn", usage=None)

    custom = Client()
    agent_module.run_agent(make_box(min_clip_seconds=8.0, max_clip_seconds=22.5), "funny", client=custom, target_seconds=15)
    assert "between 8 and 22.5 seconds" in custom.calls[0] and "aim for about 15s" in custom.calls[0]

    default = Client()
    agent_module.run_agent(make_box(), "funny", client=default)
    assert "must be between" not in default.calls[0]
