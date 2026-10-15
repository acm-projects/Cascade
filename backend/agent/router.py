"""Agentic clip-search feature: an LLM agent finds the best clips for a category.

Mounted by backend/app.py under the /api/agent prefix. Endpoints:
  POST /api/agent/analyze                  - upload a video + category, starts a background job
  GET  /api/agent/analyze/{job_id}/status  - poll job progress / result (survives restarts once done)
  GET  /api/agent/jobs                     - recent finished runs, newest first
  GET  /api/agent/clips/{job_id}/{rank}    - the cut clip as an MP4 (add ?download=1 to download)

Finished runs are saved under backend/agent/outputs/<job_id>/ (result.json + clip_N.mp4), so
results survive a page refresh and a server restart.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .agent import run_agent
from .clipper import cut_clip
from .index import build_index
from .summaries import ensure_summaries
from .tools import ToolBox

logger = logging.getLogger("cascade_agent")

router = APIRouter()

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
ALLOWED_VIDEO_MIME_PREFIXES = ("video/",)

OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"  # git-ignored (outputs/)
JOB_ID_RE = re.compile(r"[0-9a-f]{32}")
MAX_LISTED_JOBS = 20

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _new_job(category: str, source_name: str) -> str:
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "category": category,
            "source_name": source_name,
            "created_at": time.time(),
            "status": "running",
            "step": "Starting...",
            "steps_log": [],
            "result": None,
            "error": None,
        }
    return job_id


def _update_job(job_id: str, message: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["step"] = message
        job["steps_log"].append(message)


def _job_dir(job_id: str) -> Path:
    return OUTPUTS_DIR / job_id


def _save_job(job_id: str) -> None:
    """Persist a finished job so it survives a refresh / restart."""
    with JOBS_LOCK:
        snapshot = {**JOBS[job_id], "steps_log": list(JOBS[job_id]["steps_log"])}
    folder = _job_dir(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "result.json.part"
    tmp.write_text(json.dumps(snapshot), encoding="utf-8")
    tmp.replace(folder / "result.json")


def _load_saved(job_id: str) -> dict | None:
    path = _job_dir(job_id) / "result.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _finish_job(job_id: str, result: dict) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "done"
        job["step"] = "Done"
        job["result"] = result
    try:
        _save_job(job_id)
    except OSError:
        # The result is still served from memory; just say it wasn't persisted.
        logger.exception("Could not save job %s to disk", job_id)


def _fail_job(job_id: str, message: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "error"
        job["error"] = message


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


@router.post("/analyze")
async def analyze(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    category: str = Form("funny"),
):
    _validate_video_upload(video)
    category = category.strip()
    if not category:
        raise HTTPException(status_code=400, detail="category must not be empty")

    work_dir = Path(tempfile.mkdtemp(prefix="agent_upload_"))
    video_path = work_dir / f"upload{Path(video.filename).suffix}"
    with video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    job_id = _new_job(category, Path(video.filename or "video").name)
    background_tasks.add_task(_run_job, job_id, video_path, work_dir, category)
    return {"job_id": job_id}


@router.get("/analyze/{job_id}/status")
def analyze_status(job_id: str):
    if not JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            return {**job, "steps_log": list(job["steps_log"])}
    saved = _load_saved(job_id)  # not in memory (e.g. after a restart): fall back to disk
    if saved is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return saved


@router.get("/jobs")
def list_jobs():
    """Recent finished runs, newest first."""
    jobs = []
    if OUTPUTS_DIR.is_dir():
        for folder in OUTPUTS_DIR.iterdir():
            if not (folder.is_dir() and JOB_ID_RE.fullmatch(folder.name)):
                continue
            saved = _load_saved(folder.name)
            if saved is None or saved.get("status") != "done":
                continue
            suggestions = (saved.get("result") or {}).get("suggestions", [])
            jobs.append(
                {
                    "job_id": saved["job_id"],
                    "category": saved.get("category", ""),
                    "source_name": saved.get("source_name", ""),
                    "created_at": saved.get("created_at", 0),
                    "clips": len(suggestions),
                }
            )
    jobs.sort(key=lambda j: j["created_at"], reverse=True)
    return {"jobs": jobs[:MAX_LISTED_JOBS]}


@router.get("/clips/{job_id}/{rank}")
def get_clip(job_id: str, rank: int, download: int = 0):
    if not JOB_ID_RE.fullmatch(job_id) or not 1 <= rank <= 99:
        raise HTTPException(status_code=404, detail="Clip not found")
    path = _job_dir(job_id) / f"clip_{rank}.mp4"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Clip not found")
    if download:
        return FileResponse(path, media_type="video/mp4", filename=f"clip_{rank}.mp4")
    return FileResponse(path, media_type="video/mp4")  # supports Range, so the player can seek


def _cut_clips(job_id: str, video_path: Path, result: dict, progress) -> None:
    """Cut each selected moment into its own MP4 and record where it is.

    A failed cut never fails the job: the clip keeps its timestamps and gets a clip_error.
    """
    suggestions = result.get("suggestions", [])
    for n, s in enumerate(suggestions, start=1):
        progress(f"Cutting clip {n}/{len(suggestions)}")
        out_path = _job_dir(job_id) / f"clip_{s['rank']}.mp4"
        try:
            cut_clip(video_path, s["start"], s["end"], out_path)
            s["clip_url"] = f"/api/agent/clips/{job_id}/{s['rank']}"
            s["download_url"] = f"/api/agent/clips/{job_id}/{s['rank']}?download=1"
        except Exception as exc:
            logger.exception("Could not cut clip %s", s["rank"])
            s["clip_url"] = None
            s["download_url"] = None
            s["clip_error"] = str(exc)[:300]


def _run_job(job_id: str, video_path: Path, work_dir: Path, category: str) -> None:
    def progress(msg: str) -> None:
        _update_job(job_id, msg)

    try:
        _update_job(job_id, "Indexing video")
        try:
            index = build_index(video_path, work_dir, progress=progress)
        except Exception as exc:
            logger.exception("Failed to index video")
            _fail_job(job_id, f"Could not index your video: {exc}")
            return

        try:
            # Long transcripts (podcasts) get a per-chunk summary outline; no-op for short ones.
            ensure_summaries(index, progress=progress)
        except Exception as exc:
            logger.exception("Failed to summarize transcript")
            _fail_job(job_id, f"Could not summarize your video's transcript: {exc}")
            return

        try:
            result = run_agent(ToolBox(index, video_path), category, progress=progress)
        except Exception as exc:
            logger.exception("Agent run failed")
            _fail_job(job_id, f"Agent failed: {exc}")
            return

        # The upload still exists here (it is deleted below), so cut the real clips now.
        _cut_clips(job_id, video_path, result, progress)
        _finish_job(job_id, result)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
