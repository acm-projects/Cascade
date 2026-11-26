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
    monkeypatch.setattr(website, 'classify_request', lambda prompt: 'general')
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

        def fake_build(video_path, work_dir, progress=None, **kwargs):
            rec.index_kwargs = kwargs
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
        Path("video.mp4"), duration, "funny footage", target, rec.steps.append, rec.stages.append
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


def test_classifies_raw_request_once_and_records_intent(stubbed, monkeypatch):
    rec = Recorder()
    stubbed(rec)
    calls = []
    monkeypatch.setattr(website, 'classify_request', lambda prompt: calls.append(prompt) or 'specific')
    _, _, meta = website.select_with_agent(Path('video.mp4'), 120, 'expanded reference context', 30,
        rec.steps.append, rec.stages.append, request_prompt='the teddy bear fight', exclude_windows=[[80, 100]])
    assert calls == ['the teddy bear fight']
    assert rec.toolbox.intent == meta['intent'] == 'specific'
    assert rec.toolbox.exclude_windows == [(80, 100)]
    assert '2 new clips' in meta['selection_note']


def test_spoken_documentary_uses_batch_selection_without_summaries(stubbed, monkeypatch):
    rec = Recorder()
    stubbed(rec)
    monkeypatch.setattr(website, 'ensure_summaries', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Unexpected summaries')))
    monkeypatch.setattr(website, 'run_transcript_selection', lambda *a: {
        'suggestions': rec.suggestions, 'candidates_considered': 2, 'ranked_by_agent': True,
        'spacing_relaxed': False, 'iterations': 1, 'usage': {}, 'selection_mode': 'transcript-batch'})
    clips, _, meta = website.select_with_agent(Path('documentary.mp4'), 120, 'Find historical explanations in this documentary',
        30, rec.steps.append, rec.stages.append)
    assert len(clips) == 2
    assert rec.index_kwargs == {'visual': False, 'embed_transcript': False}
    assert meta['selection_mode'] == 'transcript-batch'
    assert 'Transcript summaries' not in rec.stages


@pytest.mark.parametrize("target,low,high", [(15, 8.0, 22.5), (30, 8.0, 45.0), (60, 8.0, 90.0)])
def test_clip_limits_follow_the_users_chosen_length(stubbed, target, low, high):
    rec = Recorder()
    stubbed(rec)
    run(rec, target=target)
    assert (rec.toolbox.min_clip_seconds, rec.toolbox.max_clip_seconds) == (low, high)
    assert rec.run_kwargs == {"category": "funny footage", "target_seconds": float(target)}


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
    from backend.agent.tools import SHORTEST_CLIP_SECONDS
    assert (box.min_clip_seconds, box.max_clip_seconds) == (SHORTEST_CLIP_SECONDS, MAX_CLIP_SECONDS)


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


def test_clips_from_a_joined_source_stay_inside_one_recording():
    box = make_box(parts=[{"name": "a.mp4", "start": 0, "end": 40}, {"name": "b.mp4", "start": 40, "end": 100}])
    blocks, err = box.call("add_candidate", {"start_time": 36, "end_time": 44, "reason": "spans two", "score": .8})
    assert err and "40.0" in str(blocks)
    _, err = box.call("add_candidate", {"start_time": 41, "end_time": 46, "reason": "inside b", "score": .8})
    assert not err and len(box.candidates) == 1


def test_short_moment_requests_allow_clips_down_to_two_seconds():
    box = make_box(min_clip_seconds=2.0, max_clip_seconds=7.5)
    _, err = box.call("add_candidate", {"start_time": 10, "end_time": 12.5, "reason": "a laugh", "score": .9})
    assert not err
    _, err = box.call("add_candidate", {"start_time": 30, "end_time": 39, "reason": "too long", "score": .9})
    assert err


def test_mood_and_trip_prompts_use_the_footage_not_only_the_transcript():
    assert not website.transcript_first_request("find the funniest nostalgic friendship hiking clips")
    assert website.transcript_first_request("find where he talks about taxes")
    assert "recordings joined" in website.footage_note([{"name": "a", "start": 0, "end": 5}, {"name": "b", "start": 5, "end": 9}], False)
    assert "short moments" in website.footage_note(None, True)


def test_moments_the_request_names_are_kept_whatever_their_spacing():
    box = make_box(target_clips=2)
    box.call("add_candidate", {"start_time": 10, "end_time": 15, "reason": "generic great view", "score": .95})
    box.call("add_candidate", {"start_time": 16, "end_time": 21, "reason": "we introduce ourselves", "score": .6, "asked_for": True})
    box.call("add_candidate", {"start_time": 22, "end_time": 27, "reason": "team chant with hands", "score": .5, "asked_for": True})
    box.call("rank_candidates", {"ranking": [{"id": 0}, {"id": 1}, {"id": 2}]})
    assert [c["reason"] for c in box.final_selection()] == ["we introduce ourselves", "team chant with hands"]


def test_a_clip_running_into_the_next_recording_is_trimmed_not_rejected():
    box = make_box(parts=[{"name": "a.mp4", "start": 0, "end": 40}, {"name": "b.mp4", "start": 40, "end": 100}])
    blocks, err = box.call("add_candidate", {"start_time": 39, "end_time": 47, "reason": "names round", "score": .8})
    assert not err and "trimmed" in str(blocks)
    assert 40 <= box.candidates[0]["start"] and box.candidates[0]["end"] == 47


def test_speech_search_prefers_lines_that_say_the_query_words():
    from backend.agent.index import _word_overlap
    assert _word_overlap("cascade on three", "Set. Cascade on three.") > _word_overlap("cascade on three", "We're team Cascade, and we're on our daily walk.")


def test_an_exact_range_in_a_named_recording_becomes_a_clip():
    from backend.agent.website import add_given_ranges
    box = make_box(min_clip_seconds=2.0, max_clip_seconds=10.0, parts=[{"name": "a", "start": 0, "end": 30}, {"name": "b", "start": 30, "end": 100}])
    note = add_given_ranges(box, "the moment 0:08 to 0:13 in the 1:10 clip please", [{"name": "a", "start": 0, "end": 30}, {"name": "b", "start": 30, "end": 100}])
    assert box.candidates[0]["start"] == 38 and box.candidates[0]["end"] == 43 and box.candidates[0]["asked_for"]
    assert "Already added" in note


def test_rough_recording_names_and_short_video_times():
    from backend.agent.website import add_given_ranges
    parts = [{"name": "a", "start": 0, "end": 4.8}, {"name": "b", "start": 4.8, "end": 945}]
    box = make_box(min_clip_seconds=2.0, max_clip_seconds=10.0, parts=parts)
    box.index.duration = 945
    add_given_ranges(box, "01:14-1:40 from the 5 second length video and 05:30:02-05:30:98 from the 15 minute video", parts)
    got = sorted((round(c["start"], 2), round(c["end"], 2)) for c in box.candidates)
    assert got == [(1.1, 1.4), (334.8, 335.8)]   # (candidates are kept to 0.1 s)
