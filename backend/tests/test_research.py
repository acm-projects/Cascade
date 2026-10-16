"""Per-video research memory: stored after each run, never read back into prompts (yet). No network."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent import agent as agent_module  # noqa: E402
from backend.agent import research  # noqa: E402
from backend.agent.index import VideoIndex  # noqa: E402
from backend.agent.tools import ToolBox  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "RESEARCH_DIR", tmp_path)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


CANDS = [
    {"id": 0, "start": 10.0, "end": 20.0, "reason": "a joke", "score": 0.9, "extra": "ignored"},
    {"id": 1, "start": 60.0, "end": 70.0, "reason": "a fall", "score": 0.6},
]
PICKS = [{"rank": 1, "candidate_id": 0, "start": 10.0, "end": 20.0, "comparison": "best", "reason": "dup"}]


def test_round_trip_keeps_the_useful_fields_only():
    research.save_run("abc123", "funny", CANDS, PICKS, 100.0)
    runs = research.load_runs("abc123")
    assert len(runs) == 1
    run = runs[0]
    assert run["prompt"] == "funny" and run["duration"] == 100.0 and run["created_at"] > 0
    assert run["candidates"][0] == {"id": 0, "start": 10.0, "end": 20.0, "reason": "a joke", "score": 0.9}
    assert run["selected"] == [{"rank": 1, "candidate_id": 0, "start": 10.0, "end": 20.0, "comparison": "best"}]


def test_runs_accumulate_oldest_first_and_are_capped():
    for n in range(research.MAX_RUNS + 5):
        research.save_run("vid", f"prompt {n}", CANDS, PICKS, 100.0)
    runs = research.load_runs("vid")
    assert len(runs) == research.MAX_RUNS
    assert runs[0]["prompt"] == "prompt 5" and runs[-1]["prompt"] == f"prompt {research.MAX_RUNS + 4}"


def test_videos_are_kept_separate():
    research.save_run("video-a", "funny", CANDS, PICKS, 100.0)
    research.save_run("video-b", "sad", CANDS, PICKS, 50.0)
    assert [r["prompt"] for r in research.load_runs("video-a")] == ["funny"]
    assert [r["prompt"] for r in research.load_runs("video-b")] == ["sad"]
    assert research.load_runs("never-seen") == []


def test_missing_empty_or_corrupt_files_are_just_empty(tmp_path):
    assert research.load_runs("") == []
    research.save_run("vid", "p", CANDS, PICKS, 1.0)
    research._path("vid").write_text("{not json", encoding="utf-8")
    assert research.load_runs("vid") == []
    research._path("vid").write_text(json.dumps({"runs": "oops"}), encoding="utf-8")
    assert research.load_runs("vid") == []
    # and saving over a corrupt file recovers
    research.save_run("vid", "again", CANDS, PICKS, 1.0)
    assert [r["prompt"] for r in research.load_runs("vid")] == ["again"]


def test_write_is_atomic_and_the_key_cannot_escape_the_folder(tmp_path):
    research.save_run("vid", "p", CANDS, PICKS, 1.0)
    assert not list(tmp_path.glob("*.part"))
    research.save_run("../../evil", "p", CANDS, PICKS, 1.0)
    assert all(p.parent == tmp_path for p in tmp_path.rglob("research_*"))
    assert not any("evil" in p.name and ".." in p.name for p in tmp_path.iterdir())


def test_no_video_key_means_nothing_is_saved(tmp_path):
    research.save_run("", "p", CANDS, PICKS, 1.0)
    assert not list(tmp_path.glob("research_*"))


# ---------------------------------------------------------------- the agent saves after a run
def make_toolbox(video_key):
    times = [float(t) for t in range(0, 100, 2)]
    index = VideoIndex(
        duration=100.0, frame_interval=2.0, frame_times=times,
        frame_embeddings=np.eye(len(times), dtype=np.float32),
        transcript=[{"start": 10.0, "end": 14.0, "text": "so the joke is", "speaker": 0}],
        segment_embeddings=np.eye(1, dtype=np.float32),
        encode_visual_query=lambda q: np.zeros(len(times), dtype=np.float32),
        encode_text_query=lambda q: np.zeros(1, dtype=np.float32),
        video_key=video_key,
    )
    return ToolBox(index, Path("fake.mp4"), frame_grabber=lambda p, t: b"jpeg")


def tool(i, name, **args):
    return SimpleNamespace(type="tool_use", id=i, name=name, input=args)


class ScriptedClient:
    def __init__(self):
        self.calls = []
        self.messages = self
        self.scripted = [
            ([tool("o", "get_overview")], "tool_use"),
            ([tool("a", "add_candidate", start_time=10, end_time=20, reason="a joke", score=0.9),
              tool("b", "add_candidate", start_time=60, end_time=70, reason="a fall", score=0.6)], "tool_use"),
            ([tool("r", "rank_candidates", ranking=[{"id": 0, "note": "joke wins"}, {"id": 1}])], "tool_use"),
        ]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content, stop = self.scripted.pop(0)
        return SimpleNamespace(content=content, stop_reason=stop, usage=None)


def test_a_finished_run_is_saved_for_its_video():
    result = agent_module.run_agent(make_toolbox("hash-1"), "the funniest bits", client=ScriptedClient())
    runs = research.load_runs("hash-1")
    assert len(runs) == 1
    assert runs[0]["prompt"] == "the funniest bits"
    assert [c["reason"] for c in runs[0]["candidates"]] == ["a joke", "a fall"]
    assert [s["candidate_id"] for s in runs[0]["selected"]] == [s["candidate_id"] for s in result["suggestions"]]
    assert runs[0]["selected"][0]["comparison"] == "joke wins"


def test_a_second_run_on_the_same_video_adds_to_the_memory():
    agent_module.run_agent(make_toolbox("hash-1"), "funny", client=ScriptedClient())
    agent_module.run_agent(make_toolbox("hash-1"), "interesting", client=ScriptedClient())
    assert [r["prompt"] for r in research.load_runs("hash-1")] == ["funny", "interesting"]


def test_saved_research_is_not_fed_back_into_the_prompt_yet():
    agent_module.run_agent(make_toolbox("hash-1"), "funny", client=ScriptedClient())
    second = ScriptedClient()
    agent_module.run_agent(make_toolbox("hash-1"), "interesting", client=second)
    first_message = second.calls[0]["messages"][0]["content"]
    assert "a joke" not in first_message and "Earlier" not in first_message


def test_a_save_failure_never_breaks_a_finished_run(monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(research, "save_run", boom)
    result = agent_module.run_agent(make_toolbox("hash-1"), "funny", client=ScriptedClient())
    assert result["suggestions"] and result["ranked_by_agent"] is True


def test_runs_without_a_video_key_save_nothing(tmp_path):
    agent_module.run_agent(make_toolbox(""), "funny", client=ScriptedClient())
    assert not list(tmp_path.glob("research_*"))
