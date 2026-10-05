"""Clip-generation feature: burn in 4 differently-styled caption treatments.

Mounted by backend/app.py under the /api/v1 prefix. Endpoints:
  POST /api/v1/process-video     - upload a video, start a background job generating 4 styled clips
  GET  /api/v1/job/{job_id}      - poll job progress / result
"""

import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from .render_subtitles import generate_four_styled_clips

router = APIRouter()

# In-memory database for job status
jobs_db = {}

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
ALLOWED_VIDEO_MIME_PREFIXES = ("video/",)


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


def process_video_background(
    job_id: str,
    video_path: Path,
    work_dir: Path,
    styles: List[str],
    tone: str,
    audience: str,
):
    """Background task worker that generates the 4 styled clips."""
    try:
        print(f"--- Starting background generation for {job_id} ---")

        # Call the 4-clip renderer from render_subtitles.py
        clip_files = generate_four_styled_clips(
            video_path=str(video_path),
            styles=styles,
            tone=tone,
            audience=audience,
        )

        # Update status to COMPLETED and attach file names
        jobs_db[job_id]["status"] = "COMPLETED"
        jobs_db[job_id]["clips"] = clip_files
        print(f"--- Finished job {job_id} successfully! ---")

    except Exception as e:
        jobs_db[job_id]["status"] = "FAILED"
        jobs_db[job_id]["error"] = str(e)
        print(f"--- Error on job {job_id}: {e} ---")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@router.post("/process-video")
async def create_processing_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    tone: str = Form("engaging"),
    audience: str = Form("gen-z"),
    preferred_styles: Optional[List[str]] = Form(
        ["hormozi", "minimalist", "bold_viral", "cinematic"]
    ),
):
    _validate_video_upload(video)

    work_dir = Path(tempfile.mkdtemp(prefix="clips_upload_"))
    video_path = work_dir / f"upload{Path(video.filename).suffix}"
    with video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    job_id = f"job_{len(jobs_db) + 1}"
    jobs_db[job_id] = {"status": "PROCESSING", "clips": [], "error": None}

    # Hand off execution to FastAPI background worker
    background_tasks.add_task(
        process_video_background, job_id, video_path, work_dir, preferred_styles, tone, audience
    )

    return {
        "status": "success",
        "job_id": job_id,
        "message": "Video queued for 4-clip generation."
    }


@router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs_db[job_id]
