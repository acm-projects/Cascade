from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4
from functools import lru_cache

import base64
import html
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import traceback
import httpx

from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote

import jwt
import boto3

from botocore.exceptions import ClientError, BotoCoreError
from botocore.config import Config
from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)

from fastapi.responses import (
    FileResponse,
    JSONResponse,
    StreamingResponse,
)

from starlette.concurrency import run_in_threadpool
from pipeline_timing import StageTimer

from backend.agent.website import SelectionError, requirements_error, select_with_agent
from backend.cascade_llm import LLMConfigError
from backend.cascade_stt import TranscriptionError


# --------------------------------------------------
# Configuration
# --------------------------------------------------

app = FastAPI()

PROJECT_DIR = Path(__file__).resolve().parent

load_dotenv(PROJECT_DIR / ".env", override=True)
# Accept existing local names without rewriting the user's secrets file.
if not os.getenv('CLERK_SECRET_KEY') and os.getenv('CLERK_KEY', '').startswith('sk_'):
    os.environ['CLERK_SECRET_KEY'] = os.environ['CLERK_KEY']
if not os.getenv('CLERK_PUBLISHABLE_KEY') and os.getenv('CLERK_KEY', '').startswith('pk_'):
    os.environ['CLERK_PUBLISHABLE_KEY'] = os.environ['CLERK_KEY']
if not os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_ACCESS_KEY'):
    os.environ['AWS_ACCESS_KEY_ID'] = os.environ['AWS_ACCESS_KEY']

JOBS_DIR = PROJECT_DIR / "video_jobs"
JOBS_DIR.mkdir(exist_ok=True)

PROFILE_CACHE_SECONDS = 300
FAILURE_CACHE_SECONDS = 30

DEFAULT_FOLDER = "users"

PROTECTED_EXACT_PATHS = (
    "/upload",
    "/api/my-clips",
    "/api/session",
    "/api/settings",
)

FRONTEND_FILES = {
    "index_C.html",
    "login_C.html",
    "projects_C.html",
    "canvas_C.html",
    "editor_C.html",
    "exports_C.html",
    "settings_C.html",
    "styles_C.css",
    "flow_C.js",
}

PRIVATE_CLIP_FIELDS = {
    "s3_bucket",
    "clip_s3_key",
    "captions_s3_key",
}

CLERK_HINTS = {
    401: "The secret key was rejected.",
    403: "Clerk refused the request.",
    404: (
        "User not found. The key may belong "
        "to a different Clerk application."
    ),
    429: "Clerk is rate limiting requests.",
}

worker = ThreadPoolExecutor(max_workers=1)

jobs = {}
jobs_lock = Lock()

profile_cache = {}
profile_cache_lock = Lock()

# --------------------------------------------------
# S3 storage
# --------------------------------------------------

def uses_local_storage():
    mode = os.getenv('CASCADE_STORAGE', 'auto').lower()
    if mode not in ('auto', 'local', 's3'):
        raise HTTPException(503, 'CASCADE_STORAGE must be auto, local, or s3.')
    return mode == 'local' or (mode == 'auto' and not os.getenv('S3_BUCKET_NAME', '').strip())


def validate_clip_storage():
    if uses_local_storage():
        return
    if not os.getenv('S3_BUCKET_NAME', '').strip():
        raise HTTPException(503, 'S3_BUCKET_NAME is missing. Configure S3 or set CASCADE_STORAGE=local.')
    try:
        credentials = boto3.Session().get_credentials()
        if credentials is None:
            raise HTTPException(503, 'AWS credentials are missing. Configure AWS or set CASCADE_STORAGE=local.')
        credentials.get_frozen_credentials()
    except BotoCoreError as error:
        raise HTTPException(503, 'AWS credentials are incomplete or unavailable. Check AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or set CASCADE_STORAGE=local.') from error

@lru_cache(maxsize=1)
def s3_client():
    return boto3.client(
        "s3",
        region_name=os.environ.get(
            "AWS_DEFAULT_REGION",
            "us-east-2",
        ),
        config=Config(
            signature_version="s3v4",
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 3},
        ),
    )


def s3_bucket():
    bucket = os.environ.get(
        "S3_BUCKET_NAME",
        "",
    ).strip()

    if not bucket:
        raise RuntimeError(
            "Set S3_BUCKET_NAME in your .env file."
        )

    return bucket


def safe_folder_name(value):
    cleaned = re.sub(
        r"[^a-z0-9_-]+",
        "-",
        str(value or "").lower(),
    )

    return cleaned.strip("-_")[:60]


def public_clip(clip):
    return {
        key: value
        for key, value in clip.items()
        if key not in PRIVATE_CLIP_FIELDS
    }


def clerk_profile(user_id):
    secret = (
        os.environ.get("CLERK_SECRET_KEY", "")
        .strip()
        .strip("\"'")
        .strip()
    )

    if not re.fullmatch(
        r"sk_(?:test|live)_[A-Za-z0-9_-]+",
        secret,
    ):
        return (
            None,
            "CLERK_SECRET_KEY is missing or invalid.",
        )

    try:
        public_key, _ = clerk_configuration()
    except HTTPException:
        return (
            None,
            "The Clerk publishable key could not be read.",
        )

    if (
        public_key.startswith("pk_test_")
        != secret.startswith("sk_test_")
    ):
        return (
            None,
            "The publishable and secret keys use different environments.",
        )

    request = URLRequest(
        (
            "https://api.clerk.com/v1/users/"
            + quote(user_id, safe="")
        ),
        headers={
            "Authorization": f"Bearer {secret}",
            "Accept": "application/json",
            "User-Agent": "Cascade/1.0",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            profile = json.load(response)

    except HTTPError as error:
        body = (
            error.read()
            .decode("utf-8", errors="replace")
            .replace(secret, "[redacted]")
        )

        error.close()

        print(
            "CLERK HTTP STATUS:",
            error.code,
            flush=True,
        )

        print(
            "CLERK RESPONSE:",
            body[:800],
            flush=True,
        )

        hint = CLERK_HINTS.get(error.code, "")

        return (
            None,
            (
                f"Clerk profile request failed "
                f"(HTTP {error.code}). {hint}"
            ).strip(),
        )

    except (URLError, TimeoutError, ValueError) as error:
        print(
            "Clerk profile error:",
            type(error).__name__,
            str(error).replace(secret, "[redacted]"),
            flush=True,
        )

        return (
            None,
            "Could not get a valid response from Clerk.",
        )

    if (
        not isinstance(profile, dict)
        or profile.get("id") != user_id
    ):
        return (
            None,
            "Clerk returned an unexpected user profile.",
        )

    return profile, None


def resolve_storage_folder(user_id):
    with profile_cache_lock:
        entry = profile_cache.get(user_id)

        if (
            entry
            and entry["expires"] > time.monotonic()
        ):
            return dict(entry["value"])

    value = {
        "folder": DEFAULT_FOLDER,
        "source": "fallback",
        "detail": (
            "This account has no username or name, "
            "so the users folder is used."
        ),
    }

    try:
        profile, problem = clerk_profile(user_id)
    except Exception:
        traceback.print_exc()

        profile = None
        problem = "Username lookup failed unexpectedly."

    if problem:
        value["detail"] = problem

    elif profile:
        full_name = " ".join(
            str(part)
            for part in (
                profile.get("first_name"),
                profile.get("last_name"),
            )
            if part
        )

        for source, text in (
            ("username", profile.get("username")),
            ("name", full_name),
        ):
            name = safe_folder_name(text)

            if name:
                value = {
                    "folder": name,
                    "source": source,
                    "detail": "",
                }

                break

    lifetime = (
        FAILURE_CACHE_SECONDS
        if value["source"] == "fallback"
        else PROFILE_CACHE_SECONDS
    )

    with profile_cache_lock:
        profile_cache[user_id] = {
            "expires": time.monotonic() + lifetime,
            "value": dict(value),
        }

    return value


def upload_clip_files(
    folder,
    job_id,
    filename,
    captions_filename,
):
    # Local media already uses the same ownership-checked /clips route.
    if uses_local_storage():
        return {"storage": "local"}
    owner = json.loads(
        (folder / "owner.json").read_text(
            encoding="utf-8"
        )
    )

    user_folder = (
        safe_folder_name(owner.get("user_folder"))
        or DEFAULT_FOLDER
    )

    prefix = (
        f"{user_folder}/{owner['user_id']}"
        f"/jobs/{job_id}"
    )

    bucket = s3_bucket()
    client = s3_client()
    keys = {}

    for name, content_type, field in (
        (
            filename,
            "video/mp4",
            "clip_s3_key",
        ),
        (
            captions_filename,
            "text/vtt; charset=utf-8",
            "captions_s3_key",
        ),
    ):
        key = f"{prefix}/{name}"

        client.upload_file(
            str(folder / name),
            bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
            },
        )

        keys[field] = key

    return {
        "s3_bucket": bucket,
        **keys,
    }


# --------------------------------------------------
# Clerk configuration and token verification
# --------------------------------------------------

def clerk_configuration():
    key = os.environ.get(
        "CLERK_PUBLISHABLE_KEY",
        "",
    ).strip()

    # Preserve the original working login.html fallback.
    if not key:
        login_path = PROJECT_DIR / "login.html"

        if login_path.is_file():
            match = re.search(
                (
                    r"const\s+CLERK_PUBLISHABLE_KEY"
                    r"\s*=\s*[\"']"
                    r"(pk_(?:test|live)_[^\"']+)"
                    r"[\"']"
                ),
                login_path.read_text(
                    encoding="utf-8"
                ),
            )

            if match:
                key = match.group(1)

    try:
        if not key.startswith(
            ("pk_test_", "pk_live_")
        ):
            raise ValueError(
                "Invalid publishable key."
            )

        encoded = key.split("_", 2)[2]
        encoded += "=" * (-len(encoded) % 4)

        decoded = base64.b64decode(
            encoded
        ).decode()

        if not decoded.endswith("$"):
            raise ValueError(
                "Invalid Clerk domain."
            )

        domain = decoded[:-1]

        if not re.fullmatch(
            r"[a-zA-Z0-9.-]+",
            domain,
        ):
            raise ValueError(
                "Invalid Clerk domain."
            )

    except (
        ValueError,
        IndexError,
        UnicodeError,
    ):
        raise HTTPException(
            503,
            (
                "Set CLERK_PUBLISHABLE_KEY in .env "
                "or keep your original login.html "
                "with its publishable key."
            ),
        )

    return key, domain


def authorized_parties():
    return {
        value.strip()
        for value in os.environ.get(
            "CLERK_AUTHORIZED_PARTIES",
            (
                "http://127.0.0.1:8000,"
                "http://localhost:8000"
            ),
        ).split(",")
        if value.strip()
    }


@lru_cache(maxsize=4)
def clerk_jwks(domain):
    return jwt.PyJWKClient(
        (
            f"https://{domain}"
            "/.well-known/jwks.json"
        ),
        timeout=10,
    )


def verify_clerk_token(token):
    _, domain = clerk_configuration()

    try:
        signing_key = (
            clerk_jwks(domain)
            .get_signing_key_from_jwt(token)
            .key
        )

        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=f"https://{domain}",
            options={
                "require": [
                    "exp",
                    "iat",
                    "nbf",
                    "sub",
                    "sid",
                ],
                "verify_aud": False,
            },
        )

        if (
            claims.get("azp")
            not in authorized_parties()
            or not claims.get("sub")
            or not claims.get("sid")
        ):
            raise jwt.InvalidTokenError(
                "Invalid session or authorized party."
            )

        return claims["sub"]

    except jwt.PyJWKClientConnectionError as error:
        print(
            "Clerk signing-key connection failed:",
            str(error),
            flush=True,
        )

        traceback.print_exc()

        raise HTTPException(
            503,
            (
                "Could not reach Clerk to verify "
                "your session. Try again."
            ),
        ) from error

    except jwt.PyJWTError:
        raise HTTPException(
            401,
            "Please sign in again.",
        )


@app.middleware("http")
async def authenticate_backend(
    request: Request,
    call_next,
):
    protected = (
        request.url.path
        in PROTECTED_EXACT_PATHS
        or request.url.path.startswith(
            ("/jobs/", "/clips/", "/api/projects", "/api/features/")
        )
    )

    if protected:
        origin = request.headers.get("origin")

        if (
            origin
            and origin not in authorized_parties()
        ):
            return JSONResponse(
                {"detail": "Origin not allowed."},
                status_code=403,
            )

        authorization = request.headers.get(
            "authorization",
            "",
        )

        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = request.cookies.get(
                "__session"
            )

        if not token:
            return JSONResponse(
                {
                    "detail": "Please sign in first."
                },
                status_code=401,
            )

        try:
            request.state.user_id = (
                await run_in_threadpool(
                    verify_clerk_token,
                    token,
                )
            )

        except HTTPException as error:
            return JSONResponse(
                {"detail": error.detail},
                status_code=error.status_code,
            )

    response = await call_next(request)

    if protected:
        response.headers[
            "Cache-Control"
        ] = "no-store"

    return response


# --------------------------------------------------
# New frontend pages
# --------------------------------------------------

def serve_new_page(filename):
    if filename not in FRONTEND_FILES:
        raise HTTPException(
            404,
            "Page not found.",
        )

    path = PROJECT_DIR / filename

    if not path.is_file():
        raise HTTPException(
            404,
            f"Put {filename} beside app1.py.",
        )

    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store",
        },
    )


@app.get("/")
def show_website():
    return serve_new_page("index_C.html")


@app.get("/login")
def login_page():
    return serve_new_page("login_C.html")


@app.get("/api/auth-config")
def frontend_auth_config():
    key, domain = clerk_configuration()

    # Only the publishable key is sent to the browser.
    return JSONResponse(
        {
            "publishable_key": key,
            "domain": domain,
        },
        headers={
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/session")
def frontend_session(request: Request):
    # The middleware has already verified this token.
    return JSONResponse(
        {
            "user_id": request.state.user_id,
        },
        headers={
            "Cache-Control": "no-store",
        },
    )


def make_frontend_endpoint(filename):
    def endpoint():
        return serve_new_page(filename)

    return endpoint


# Serve only these named files, not the entire folder.
for frontend_filename in sorted(FRONTEND_FILES):
    app.add_api_route(
        "/" + frontend_filename,
        make_frontend_endpoint(
            frontend_filename
        ),
        methods=["GET"],
        include_in_schema=False,
    )


# --------------------------------------------------
# Job ownership and helpers
# --------------------------------------------------

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

    if not owner_path.is_file():
        raise HTTPException(
            404,
            "Job not found. Upload the video again.",
        )

    owner = json.loads(
        owner_path.read_text(
            encoding="utf-8"
        )
    )

    if owner.get("user_id") != user_id:
        raise HTTPException(
            404,
            "Job not found.",
        )


def save_json(path, data):
    temporary = path.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)


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


def run_command(command):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=float(os.getenv("CASCADE_FFMPEG_TIMEOUT", "300")),
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr[-1500:]
            or "Video processing failed."
        )

    return result.stdout


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


def inspect_video(video_path):
    information = json.loads(
        run_command([
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(video_path),
        ])
    )

    streams = information.get(
        "streams",
        [],
    )

    if not any(
        stream.get("codec_type") == "video"
        for stream in streams
    ):
        raise ValueError(
            "This file has no video track."
        )

    duration = float(
        information["format"]["duration"]
    )

    if (
        not math.isfinite(duration)
        or duration <= 0
    ):
        raise ValueError(
            "Invalid video duration."
        )

    has_audio = any(
        stream.get("codec_type") == "audio"
        for stream in streams
    )

    return duration, has_audio


# --------------------------------------------------

def caption_time(seconds):
    milliseconds = max(
        0,
        round(seconds * 1000),
    )

    hours, remainder = divmod(
        milliseconds,
        3600000,
    )

    minutes, remainder = divmod(
        remainder,
        60000,
    )

    seconds, milliseconds = divmod(
        remainder,
        1000,
    )

    return (
        f"{hours:02}:"
        f"{minutes:02}:"
        f"{seconds:02}."
        f"{milliseconds:03}"
    )


def write_captions(
    path,
    transcript,
    start,
    end,
):
    lines = ["WEBVTT", ""]

    for segment in transcript:
        caption_start = max(
            start,
            segment["start"],
        )

        caption_end = min(
            end,
            segment["end"],
        )

        if caption_end <= caption_start:
            continue

        text = html.escape(
            " ".join(
                segment["text"].split()
            )
        )

        lines.extend([
            (
                f"{caption_time(caption_start - start)}"
                " --> "
                f"{caption_time(caption_end - start)}"
            ),
            text,
            "",
        ])

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------
# Background processing
# --------------------------------------------------

MAX_STEPS = 400  # the step log shown on the website is capped


def process_upload(
    job_id,
    video_path,
    search,
    mode,
    target,
):
    folder = JOBS_DIR / job_id
    started = time.monotonic()
    stage = 'starting analysis'
    steps = []
    timer = StageTimer(lambda timings, active: update_job(
        job_id, timings=timings, timing_stage=active, timing_stage_started_at=time.time()))

    def progress(message):
        nonlocal stage
        # No time limit by default: a first run on a long video can legitimately take a while.
        # CASCADE_JOB_TIMEOUT (seconds) is an optional safety net, checked between steps.
        budget = os.getenv('CASCADE_JOB_TIMEOUT')
        if budget and time.monotonic() - started > float(budget):
            raise TimeoutError('Job processing budget exceeded')
        stage = message
        steps.append(message)
        del steps[:-MAX_STEPS]
        # update_job also raises JobCancelled if the user stopped the job, so cancel works mid-agent.
        update_job(job_id, message=message, steps_log=list(steps))

    try:
        update_job(
            job_id,
            state="processing",
        )

        progress("Reading uploaded video...")
        timer.start('Video inspection')
        duration, _ = inspect_video(video_path)

        # The agent: Deepgram transcript, search index, and a multi-step selection of the best
        # moments across the whole video. Cutting, captions and storage below are unchanged.
        selected, transcript, metadata = select_with_agent(
            video_path, duration, search, target, progress, timer.start)

        save_json(
            folder / "selected_clips.json",
            {
                "query": search,
                "model": metadata.get('model'),
                "provider": metadata.get('provider'),
                "clips": selected,
            },
        )

        clips = []

        for number, selection in enumerate(
            selected,
            start=1,
        ):
            progress(
                f"Cutting clip {number}/{len(selected)}..."
            )
            timer.start('Video rendering')

            filename = f"clip_{number}.mp4"

            captions_filename = (
                f"clip_{number}.vtt"
            )

            run_command([
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(selection["start"]),
                "-i",
                str(video_path),
                "-t",
                str(
                    selection["end"]
                    - selection["start"]
                ),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(folder / filename),
            ])

            timer.start('Caption preparation')
            write_captions(
                folder / captions_filename,
                transcript,
                selection["start"],
                selection["end"],
            )

            progress(
                f"Saving clip {number}/{len(selected)}..."
            )
            timer.start('Clip storage')

            storage = upload_clip_files(
                folder,
                job_id,
                filename,
                captions_filename,
            )

            clips.append({
                **selection,
                **storage,

                "clip_url": (
                    f"/clips/{job_id}/{filename}"
                ),

                "captions_url": (
                    f"/clips/{job_id}/"
                    f"{captions_filename}"
                ),
            })

        timings = timer.finish()
        save_json(
            folder / "results.json",
            {"clips": clips, 'timings': timings, 'steps_log': list(steps), **metadata},
        )

        update_job(
            job_id,
            state="done",

            message=(
                f"{len(clips)} clip(s) ready."
                if clips
                else "No matching clip was found."
            ),

            clips=[
                public_clip(clip)
                for clip in clips
            ],
            **metadata,
        )

    except Exception as error:
        traceback.print_exc()
        message = processing_error(error, stage)
        integration.fail_feature(job_id, message)


# --------------------------------------------------
# Upload
# --------------------------------------------------

@app.post("/upload", status_code=202)
def upload_video(
    request: Request,
    video: UploadFile = File(...),
    search: str = Form(...),
    mode: str = Form("both"),
    clip_length: int = Form(30),
    project_id: str = Form(...),
):
    integration.require_project(project_id, request.state.user_id)
    validate_clip_storage()
    # a missing key fails now, with a clear message, not mid-job
    problem = requirements_error()
    if problem:
        raise HTTPException(503, problem)
    search = search.strip()

    if not search or len(search) > 2000:
        raise HTTPException(
            400,
            "Enter a prompt of 1–2000 characters.",
        )

    if mode not in (
        "speech",
        "visual",
        "both",
    ):
        raise HTTPException(
            400,
            "Invalid search mode.",
        )

    if clip_length not in (15, 30, 60):
        raise HTTPException(
            400,
            "Invalid clip length.",
        )

    if (
        shutil.which("ffmpeg") is None
        or shutil.which("ffprobe") is None
    ):
        raise HTTPException(
            503,
            "FFmpeg and ffprobe must be installed.",
        )

    storage_information = ({'folder': DEFAULT_FOLDER, 'source': 'local'} if uses_local_storage()
                           else resolve_storage_folder(request.state.user_id))

    job_id = uuid4().hex

    folder = JOBS_DIR / job_id
    folder.mkdir()

    video_path = folder / "source.video"

    try:
        fingerprint = hashlib.sha256()
        with video_path.open("wb") as destination:
            while chunk := video.file.read(1024 * 1024):
                fingerprint.update(chunk)
                destination.write(chunk)

        if video_path.stat().st_size == 0:
            raise HTTPException(
                400,
                "The uploaded file is empty.",
            )

        save_json(
            folder / "owner.json",
            {
                "user_id": request.state.user_id,
                "project_id": project_id,
                "prompt": search,
                "source_name": Path(video.filename or "video").name,
                "video_sha256": fingerprint.hexdigest(),

                "user_folder": (
                    storage_information["folder"]
                ),

                "folder_source": (
                    storage_information["source"]
                ),
            },
        )
        # Reuse only analysis from the same verified account and project.
        for previous in JOBS_DIR.glob('*/owner.json'):
            if previous.parent == folder:
                continue
            try:
                owner = json.loads(previous.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if (owner.get('user_id') == request.state.user_id and owner.get('project_id') == project_id
                    and owner.get('video_sha256') == fingerprint.hexdigest()):
                for name in ('transcript.json', 'video_descriptions.json', 'visual_analysis_settings.json', 'openai_selection.json'):
                    cached = previous.parent / name
                    if cached.is_file() and not (folder / name).exists():
                        shutil.copyfile(cached, folder / name)

    except Exception:
        shutil.rmtree(folder)
        raise

    finally:
        video.file.close()

    with jobs_lock:
        jobs[job_id] = {
            "state": "queued",
            "message": "Waiting to process...",
            "clips": [],
        }

    worker.submit(
        process_upload,
        job_id,
        video_path,
        search,
        mode,
        clip_length,
    )

    return {"job_id": job_id}


# --------------------------------------------------
# Job progress
# --------------------------------------------------

@app.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    request: Request,
):
    require_job_owner(
        job_id,
        request.state.user_id,
    )

    with jobs_lock:
        if job_id in jobs:
            return dict(jobs[job_id])

    results_path = (
        JOBS_DIR / job_id / "results.json"
    )

    if results_path.is_file():
        results = json.loads(
            results_path.read_text(
                encoding="utf-8"
            )
        )

        clips = [
            public_clip(clip)
            for clip in results.get("clips", [])
            if isinstance(clip, dict)
        ]

        return {
            "state": "done",

            "message": (
                "Clip 1 is ready."
                if clips
                else "No matching clip was found."
            ),

            "clips": clips,
            "steps_log": results.get("steps_log", []),
            "timings": results.get("timings"),
            "selection_note": results.get("selection_note", ""),
        }

    raise HTTPException(
        404,
        (
            "Job unavailable. The server may have "
            "restarted before processing finished. "
            "Upload the video again."
        ),
    )


# --------------------------------------------------
# Protected clip and caption playback
# --------------------------------------------------

@app.get("/clips/{job_id}/{filename}")
def get_clip(
    job_id: str,
    filename: str,
    request: Request,
):
    require_job_owner(
        job_id,
        request.state.user_id,
    )

    # Keep compatibility with previously saved jobs.
    if not re.fullmatch(
        r"clip_[1-4]\.(mp4|vtt)",
        filename,
    ):
        raise HTTPException(
            404,
            "Clip not found.",
        )

    folder = JOBS_DIR / job_id

    results_path = folder / "results.json"

    storage = None

    if results_path.is_file():
        results = json.loads(
            results_path.read_text(
                encoding="utf-8"
            )
        )

        for clip in results.get("clips", []):
            field = (
                "clip_url"
                if filename.endswith(".mp4")
                else "captions_url"
            )

            if clip.get(field) == (
                f"/clips/{job_id}/{filename}"
            ):
                storage = clip
                break

    key_field = (
        "clip_s3_key"
        if filename.endswith(".mp4")
        else "captions_s3_key"
    )

    media_type = (
        "video/mp4"
        if filename.endswith(".mp4")
        else "text/vtt"
    )

    if storage and storage.get(key_field):
        parameters = {
            "Bucket": storage["s3_bucket"],
            "Key": storage[key_field],
        }

        byte_range = request.headers.get(
            "range"
        )

        if byte_range:
            if not re.fullmatch(
                r"bytes=(?:[0-9]+-[0-9]*|-[0-9]+)",
                byte_range,
            ):
                raise HTTPException(
                    416,
                    "Invalid byte range.",
                )

            parameters["Range"] = byte_range

        try:
            result = s3_client().get_object(
                **parameters
            )

        except ClientError as error:
            code = error.response.get(
                "Error",
                {},
            ).get("Code")

            if code == "InvalidRange":
                raise HTTPException(
                    416,
                    "Requested range unavailable.",
                ) from error

            if code in ("NoSuchKey", "404"):
                raise HTTPException(
                    404,
                    "Clip not found.",
                ) from error

            raise HTTPException(
                503,
                "Could not retrieve clip.",
            ) from error

        except BotoCoreError as error:
            raise HTTPException(
                503,
                "Could not retrieve clip.",
            ) from error

        body = result["Body"]

        def chunks():
            try:
                yield from body.iter_chunks(
                    chunk_size=1024 * 1024
                )

            finally:
                body.close()

        headers = {
            "Content-Length": str(
                result["ContentLength"]
            ),

            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store",
        }

        if result.get("ContentRange"):
            headers["Content-Range"] = (
                result["ContentRange"]
            )

        return StreamingResponse(
            chunks(),
            media_type=media_type,
            headers=headers,
            status_code=(
                206 if byte_range else 200
            ),
        )

    path = folder / filename

    if not path.is_file():
        raise HTTPException(
            404,
            "Clip not found.",
        )

    return FileResponse(
        path,
        media_type=media_type,
    )


# --------------------------------------------------
# Existing user clip history
# --------------------------------------------------

@app.get("/api/my-clips")
def get_my_clips(request: Request):
    saved_clips = []

    folders = [
        folder
        for folder in JOBS_DIR.iterdir()
        if (
            folder.is_dir()
            and re.fullmatch(
                r"[0-9a-f]{32}",
                folder.name,
            )
        )
    ]

    folders.sort(
        key=lambda folder: folder.stat().st_mtime,
        reverse=True,
    )

    for folder in folders:
        owner_path = folder / "owner.json"
        results_path = folder / "results.json"

        if not owner_path.is_file():
            continue

        try:
            owner = json.loads(
                owner_path.read_text(
                    encoding="utf-8"
                )
            )

            if (
                owner.get("user_id")
                != request.state.user_id
            ):
                continue

            if not results_path.is_file():
                continue

            results = json.loads(
                results_path.read_text(
                    encoding="utf-8"
                )
            )

            clips = results.get("clips", [])

            if not isinstance(clips, list):
                continue

            for clip in clips:
                if not isinstance(clip, dict):
                    continue

                clip_url = clip.get("clip_url")

                if not isinstance(clip_url, str):
                    continue

                match = re.fullmatch(
                    (
                        rf"/clips/{folder.name}/"
                        r"(clip_[1-4]\.mp4)"
                    ),
                    clip_url,
                )

                if not match:
                    continue

                if (
                    not clip.get("clip_s3_key")
                    and not (
                        folder / match.group(1)
                    ).is_file()
                ):
                    continue

                saved_clips.append({
                    **public_clip(clip),
                    "job_id": folder.name,
                })

        except (
            OSError,
            ValueError,
            TypeError,
            AttributeError,
        ):
            continue

    return JSONResponse(
        {"clips": saved_clips},
        headers={
            "Cache-Control": "no-store",
        },
    )

# Integrate remote backend features under the existing authenticated app.
import sys
import integration
integration.register(app, sys.modules[__name__])
