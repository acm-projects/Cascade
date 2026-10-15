"""Clip cutting, serving and persistence. Uses real ffmpeg on a tiny generated video (skipped if
ffmpeg is missing); the models, Deepgram and Claude are stubbed out."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import clipper  # noqa: E402
from agent import router as router_module  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="needs ffmpeg"
)


def duration_of(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


@pytest.fixture(scope="module")
def tiny_video(tmp_path_factory):
    path = tmp_path_factory.mktemp("vid") / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440",
            "-t", "8", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )
    return path


# ---------- clipper ----------

def test_cut_clip_makes_a_real_short_file_of_the_right_length(tiny_video, tmp_path):
    out = clipper.cut_clip(tiny_video, 2.0, 5.5, tmp_path / "c.mp4")
    assert out.is_file() and out.stat().st_size > 0
    assert duration_of(out) == pytest.approx(3.5, abs=0.15)
    assert duration_of(out) < duration_of(tiny_video) / 2  # it is the clip, not the whole video
    assert not list(tmp_path.glob("*.part*"))


def test_cut_clip_rejects_bad_ranges_and_leaves_nothing_behind(tiny_video, tmp_path):
    with pytest.raises(clipper.ClipError):
        clipper.cut_clip(tiny_video, 5.0, 5.0, tmp_path / "x.mp4")
    with pytest.raises(clipper.ClipError):
        clipper.cut_clip(tmp_path / "missing.mp4", 0.0, 2.0, tmp_path / "y.mp4")
    assert not list(tmp_path.glob("*.mp4*"))


# ---------- router: upload -> job -> clips on disk -> served ----------

FAKE_RESULT = {
    "suggestions": [
        {"rank": 1, "candidate_id": 0, "start": 1.0, "end": 3.5, "reason": "r1", "score": 0.9, "comparison": "best"},
        {"rank": 2, "candidate_id": 1, "start": 4.0, "end": 7.0, "reason": "r2", "score": 0.6, "comparison": ""},
    ],
    "candidates_considered": 5,
    "ranked_by_agent": True,
    "spacing_relaxed": False,
    "summary": "",
    "iterations": 3,
    "usage": {"input_tokens": 1, "output_tokens": 1, "model": "m", "estimated_cost_usd": 0.0,
              "transcription_cost_usd": 0.0},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(router_module, "OUTPUTS_DIR", tmp_path / "outputs")
    router_module.JOBS.clear()
    monkeypatch.setattr(router_module, "build_index", lambda v, w, progress=None: SimpleNamespace(duration=8.0))
    monkeypatch.setattr(router_module, "ensure_summaries", lambda index, progress=None: None)
    monkeypatch.setattr(
        router_module, "run_agent",
        lambda toolbox, category, progress=None: json.loads(json.dumps(FAKE_RESULT)),
    )
    app = FastAPI()
    app.include_router(router_module.router, prefix="/api/agent")
    return TestClient(app)


def upload(client, video, category="funny"):
    with video.open("rb") as f:
        return client.post(
            "/api/agent/analyze", files={"video": ("tiny.mp4", f, "video/mp4")}, data={"category": category}
        )


def test_full_flow_cuts_real_clips_and_serves_them(client, tiny_video):
    job_id = upload(client, tiny_video, "funny").json()["job_id"]
    job = client.get(f"/api/agent/analyze/{job_id}/status").json()
    assert job["status"] == "done", job
    assert job["category"] == "funny" and job["source_name"] == "tiny.mp4"
    steps = " | ".join(job["steps_log"])
    assert "Cutting clip 1/2" in steps and "Cutting clip 2/2" in steps

    first, second = job["result"]["suggestions"]
    assert first["clip_url"] == f"/api/agent/clips/{job_id}/1"
    assert first["download_url"].endswith("?download=1")

    resp = client.get(first["clip_url"])
    assert resp.status_code == 200 and resp.headers["content-type"] == "video/mp4"
    assert "attachment" not in resp.headers.get("content-disposition", "")
    saved = router_module.OUTPUTS_DIR / job_id
    assert duration_of(saved / "clip_1.mp4") == pytest.approx(2.5, abs=0.15)
    assert duration_of(saved / "clip_2.mp4") == pytest.approx(3.0, abs=0.15)

    ranged = client.get(first["clip_url"], headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206 and len(ranged.content) == 100  # the player can seek

    dl = client.get(first["download_url"])
    assert dl.status_code == 200 and "attachment" in dl.headers["content-disposition"]


def test_finished_run_survives_a_restart(client, tiny_video):
    job_id = upload(client, tiny_video).json()["job_id"]
    router_module.JOBS.clear()  # what a server restart does to memory
    job = client.get(f"/api/agent/analyze/{job_id}/status").json()
    assert job["status"] == "done" and len(job["result"]["suggestions"]) == 2
    assert client.get(job["result"]["suggestions"][0]["clip_url"]).status_code == 200


def test_jobs_list_shows_saved_runs_newest_first(client, tiny_video):
    first = upload(client, tiny_video, "funny").json()["job_id"]
    second = upload(client, tiny_video, "interesting").json()["job_id"]
    jobs = client.get("/api/agent/jobs").json()["jobs"]
    assert [j["job_id"] for j in jobs] == [second, first]
    assert jobs[0]["category"] == "interesting" and jobs[0]["clips"] == 2


def test_a_failed_cut_does_not_fail_the_job(client, tiny_video, monkeypatch):
    def broken(video, start, end, out):
        raise clipper.ClipError("ffmpeg exploded")

    monkeypatch.setattr(router_module, "cut_clip", broken)
    job_id = upload(client, tiny_video).json()["job_id"]
    job = client.get(f"/api/agent/analyze/{job_id}/status").json()
    assert job["status"] == "done"
    s = job["result"]["suggestions"][0]
    assert s["clip_url"] is None and "exploded" in s["clip_error"]
    assert s["start"] == 1.0  # timestamps are still there


def test_agent_failure_is_reported_and_not_saved(client, tiny_video, monkeypatch):
    def boom(toolbox, category, progress=None):
        raise RuntimeError("model down")

    monkeypatch.setattr(router_module, "run_agent", boom)
    job_id = upload(client, tiny_video).json()["job_id"]
    job = client.get(f"/api/agent/analyze/{job_id}/status").json()
    assert job["status"] == "error" and "model down" in job["error"]
    assert client.get("/api/agent/jobs").json()["jobs"] == []


def test_clip_endpoint_rejects_bad_ids_and_missing_clips(client, tiny_video):
    job_id = upload(client, tiny_video).json()["job_id"]
    for url in (
        "/api/agent/clips/not-a-job/1",
        f"/api/agent/clips/{job_id}/0",
        f"/api/agent/clips/{job_id}/100",
        f"/api/agent/clips/{job_id}/9",
        f"/api/agent/clips/{'0' * 32}/1",
        "/api/agent/clips/..%2f..%2fapp/1",
        "/api/agent/analyze/..%2f..%2fapp/status",
        f"/api/agent/analyze/{'1' * 32}/status",
    ):
        assert client.get(url).status_code == 404, url


def test_non_video_upload_is_rejected(client, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with bad.open("rb") as f:
        resp = client.post("/api/agent/analyze", files={"video": ("notes.txt", f, "text/plain")})
    assert resp.status_code == 400
