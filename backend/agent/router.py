"""Agentic clip-search feature: an LLM agent finds the best clips for a category.

Mounted by backend/app.py under the /api/agent prefix. Endpoints:
  POST /api/agent/analyze                  - upload a video + category, starts a background job
  GET  /api/agent/analyze/{job_id}/status  - poll job progress / result
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from .agent import run_agent
from .index import build_index
from .tools import ToolBox

logger = logging.getLogger("cascade_agent")

router = APIRouter()

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
ALLOWED_VIDEO_MIME_PREFIXES = ("video/",)

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _new_job() -> str:
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
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


def _finish_job(job_id: str, result: dict) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "done"
        job["step"] = "Done"
        job["result"] = result


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

    job_id = _new_job()
    background_tasks.add_task(_run_job, job_id, video_path, work_dir, category)
    return {"job_id": job_id}


@router.get("/analyze/{job_id}/status")
def analyze_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return {**job, "steps_log": list(job["steps_log"])}


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
            result = run_agent(ToolBox(index, video_path), category, progress=progress)
        except Exception as exc:
            logger.exception("Agent run failed")
            _fail_job(job_id, f"Agent failed: {exc}")
            return

        _finish_job(job_id, result)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
