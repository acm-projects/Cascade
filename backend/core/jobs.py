"""Background job state, ownership checks, metadata persistence, and public errors."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import re
import subprocess
import time

import httpx
from botocore.exceptions import ClientError, BotoCoreError
from fastapi import HTTPException

from backend.agent.website import SelectionError
from backend.cascade_llm import LLMConfigError
from backend.cascade_stt import TranscriptionError
from backend.core.config import JOBS_DIR

worker = ThreadPoolExecutor(max_workers=1)
jobs = {}
jobs_lock = Lock()


def require_job_owner(job_id, user_id):
    if not re.fullmatch(
        r"[0-9a-f]{32}",
        job_id,
    ):
        raise HTTPException(
            404,
            "Job not found.",
        )

    owner_path = (
        JOBS_DIR / job_id / "owner.json"
    )

    if not metadata_exists(owner_path):
        raise HTTPException(
            404,
            "Job not found. Upload the video again.",
        )

    owner = load_json(owner_path)

    if owner.get("user_id") != user_id or owner.get("project_deleted"):
        raise HTTPException(
            404,
            "Job not found.",
        )


def metadata_store():
    from metadata_store import get_store
    return get_store(JOBS_DIR)


def load_json(path):
    return metadata_store().read(path)


def metadata_exists(path):
    return metadata_store().exists(path)


def metadata_paths(pattern):
    return metadata_store().paths(pattern)


def metadata_documents(pattern, user_id=None):
    return metadata_store().documents(pattern, user_id)


def save_json(path, data):
    metadata_store().write(path, data)


def initialize_metadata():
    store = metadata_store()
    if store.database_url:
        with store.connection() as conn, conn.cursor() as cur:
            cur.execute('SELECT 1')


def update_job(job_id, **changes):
    with jobs_lock:
        job = jobs[job_id]
        if job.get('cancel_requested') and changes.get('state') not in ('error', 'done'):
            raise JobCancelled()
        now = time.time()
        job.setdefault("started_at", now)
        if "message" in changes and changes["message"] != job.get("message"):
            job["stage_started_at"] = now
            print(f"[{job_id}] {changes['message']}", flush=True)
        job.update(changes)
        job["updated_at"] = now
        snapshot = dict(job)
    folder = JOBS_DIR / job_id
    if folder.is_dir():
        save_json(folder / "progress.json", snapshot)


class JobCancelled(Exception):
    pass


def processing_error(error, stage):
    """Safe public errors: never expose provider credentials or signed URLs."""
    if isinstance(error, JobCancelled):
        return 'Processing cancelled. You can start another search.'
    if isinstance(error, (SelectionError, TranscriptionError, LLMConfigError)):
        return str(error)  # locally authored messages only
    status = getattr(error, 'status_code', None)  # the Anthropic / OpenAI SDK API errors
    if isinstance(status, int) and not isinstance(error, HTTPException):
        if status in (401, 403):
            return 'The AI provider rejected the API key. Check it in .env and restart the server.'
        if status == 429:
            return 'The AI provider is rate limiting this project or has no credit left. Wait briefly and retry; check API billing and limits.'
    if isinstance(error, (httpx.TimeoutException, subprocess.TimeoutExpired, TimeoutError)):
        return f'Timed out while {stage}. Processing exceeded its time limit. Try a shorter video; check the API terminal.'
    if isinstance(error, (ConnectionError, httpx.ConnectError)):
        return 'Cannot reach the AI provider or Deepgram. Check your internet connection and retry.'
    if isinstance(error, ClientError) or isinstance(error, BotoCoreError):
        return f'Storage failed while {stage}. Check AWS credentials, bucket permissions, and connectivity, or use CASCADE_STORAGE=local.'
    if isinstance(error, HTTPException) and isinstance(error.detail, str):
        # Only locally raised processing validation errors reach this adapter.
        return error.detail
    return f'Processing failed while {stage}. Check the API terminal for the error details.'
