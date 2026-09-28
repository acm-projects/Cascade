"""FastAPI app for the video trend-analysis demo.

Endpoints:
  POST /api/analyze                    - upload a video + topic, starts a background job
  GET  /api/analyze/{job_id}/status    - poll job progress / result
  GET  /api/health                     - liveness check
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import pipeline
import youtube_trends

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("video_trend_demo")

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:8000")

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
ALLOWED_VIDEO_MIME_PREFIXES = ("video/",)

RESULTS_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "results"
RESULTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

TRENDING_LIMIT = 5
# Rough step counts used to drive the progress bar (see pipeline.py's `emit` calls):
# each trending video reports "downloading" + the 5 steps analyze_video_file emits;
# the uploaded video only reports the 5 analyze_video_file steps.
STEPS_PER_TRENDING_VIDEO = 6
STEPS_PER_UPLOAD = 5
TOTAL_STEPS = 1 + TRENDING_LIMIT * STEPS_PER_TRENDING_VIDEO + STEPS_PER_UPLOAD + 1

app = FastAPI(title="Video Trend Analysis Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _new_job() -> str:
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "step": "Starting...",
            "step_index": 0,
            "total_steps": TOTAL_STEPS,
            "result": None,
            "error": None,
        }
    return job_id


def _update_job(job_id: str, message: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["step"] = message
        job["step_index"] = min(job["step_index"] + 1, job["total_steps"])


def _finish_job(job_id: str, result: dict, from_cache: bool = False) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "done"
        job["step"] = "Loaded from cache" if from_cache else "Done"
        job["step_index"] = job["total_steps"]
        job["result"] = result


def _fail_job(job_id: str, message: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "error"
        job["error"] = message


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    background_tasks: BackgroundTasks, topic: str = Form(...), video: UploadFile = File(...)
):
    _validate_video_upload(video)

    work_dir = Path(tempfile.mkdtemp(prefix="video_trend_"))
    upload_path = work_dir / f"upload{Path(video.filename).suffix}"

    hasher = hashlib.sha256()
    with upload_path.open("wb") as f:
        while chunk := video.file.read(1024 * 1024):
            hasher.update(chunk)
            f.write(chunk)

    cache_key = _result_cache_key(topic, hasher.hexdigest())
    cache_path = RESULTS_CACHE_DIR / f"{cache_key}.json"

    job_id = _new_job()

    if cache_path.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
        _finish_job(job_id, json.loads(cache_path.read_text()), from_cache=True)
        return {"job_id": job_id}

    background_tasks.add_task(_run_analysis, job_id, topic, upload_path, work_dir, cache_path)
    return {"job_id": job_id}


def _result_cache_key(topic: str, video_hash: str) -> str:
    normalized_topic = topic.strip().lower()
    return hashlib.sha256(f"{normalized_topic}|{video_hash}".encode("utf-8")).hexdigest()


@app.get("/api/analyze/{job_id}/status")
def analyze_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _run_analysis(
    job_id: str, topic: str, upload_path: Path, work_dir: Path, cache_path: Path
) -> None:
    try:
        _update_job(job_id, f"Fetching trending videos for '{topic}'...")
        try:
            trending_videos = youtube_trends.get_trending_videos(topic, limit=TRENDING_LIMIT)
        except Exception as exc:
            logger.exception("Failed to fetch trending videos")
            _fail_job(job_id, f"Could not fetch trending videos: {exc}")
            return

        trending_results = []
        for i, tv in enumerate(trending_videos, start=1):
            def report(msg: str, i=i, title=tv["title"]) -> None:
                _update_job(job_id, f"Trending video {i}/{len(trending_videos)} ({title}): {msg}")

            try:
                analysis = pipeline.analyze_youtube_video(tv["video_id"], work_dir, progress=report)
                trending_results.append({**tv, "tags": analysis["tags"]})
            except Exception:
                logger.exception("Failed to analyze trending video %s", tv["video_id"])
                # Skip this one video rather than failing the whole request.
                continue

        if not trending_results:
            _fail_job(job_id, "Could not analyze any trending videos")
            return

        def report_upload(msg: str) -> None:
            _update_job(job_id, f"Your video: {msg}")

        try:
            your_analysis = pipeline.analyze_video_file(upload_path, work_dir, progress=report_upload)
        except Exception as exc:
            logger.exception("Failed to analyze uploaded video")
            _fail_job(job_id, f"Could not analyze your video: {exc}")
            return

        _update_job(job_id, "Comparing your video against trending videos...")
        comparison = _compare_tags(your_analysis["tags"], [r["tags"] for r in trending_results])

        result = {
            "trending_summary": [
                {
                    "title": r["title"],
                    "channel": r["channel"],
                    "url": r["url"],
                    "tags": r["tags"],
                }
                for r in trending_results
            ],
            "your_video_tags": your_analysis["tags"],
            "comparison": comparison,
        }
        cache_path.write_text(json.dumps(result))
        _finish_job(job_id, result)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _validate_video_upload(video: UploadFile) -> None:
    suffix = Path(video.filename or "").suffix.lower()
    content_type = video.content_type or ""

    if suffix not in ALLOWED_VIDEO_EXTENSIONS and not content_type.startswith(
        ALLOWED_VIDEO_MIME_PREFIXES
    ):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file does not look like a video (check extension/mimetype).",
        )


def _compare_tags(your_tags: dict, trending_tags_list: list[dict]) -> dict:
    """Diff the uploaded video's tags against the trending videos' tags."""

    def collect_values(field: str) -> set[str]:
        values: set[str] = set()
        for tags in trending_tags_list:
            v = tags.get(field)
            if isinstance(v, list):
                values.update(x.lower() for x in v)
            elif isinstance(v, str) and v:
                values.add(v.lower())
        return values

    matching_traits: list[str] = []
    missing_traits: list[str] = []

    for field in ["visual_style", "audio_style", "topics"]:
        your_values = your_tags.get(field, [])
        your_values = {v.lower() for v in your_values} if isinstance(your_values, list) else set()
        trending_values = collect_values(field)

        for v in your_values:
            if v in trending_values:
                matching_traits.append(f"{field}: {v}")

        for v in trending_values:
            if v not in your_values:
                missing_traits.append(f"{field}: {v}")

    for field in ["pacing", "tone", "hook_style"]:
        trending_values = collect_values(field)
        your_value = str(your_tags.get(field, "")).lower()
        if your_value and your_value in trending_values:
            matching_traits.append(f"{field}: {your_value}")
        elif trending_values:
            common = max(trending_values, key=lambda v: v)
            missing_traits.append(f"{field}: trending videos favor '{common}'")

    narrative = _build_narrative(matching_traits, missing_traits)

    return {
        "matching_traits": matching_traits,
        "missing_traits": missing_traits,
        "narrative": narrative,
    }


def _build_narrative(matching_traits: list[str], missing_traits: list[str]) -> str:
    if not matching_traits and not missing_traits:
        return "Not enough data to compare your video against current trends."

    parts = []
    if matching_traits:
        parts.append(
            f"Your video shares {len(matching_traits)} trait(s) with what's trending right now, "
            f"including {matching_traits[0]}."
        )
    if missing_traits:
        parts.append(
            f"It's missing {len(missing_traits)} trait(s) common in trending videos, "
            f"such as {missing_traits[0]}."
        )
    parts.append("Consider adjusting pacing, hook, or visual style to align more closely with current trends.")
    return " ".join(parts)


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
