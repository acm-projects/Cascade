from functools import lru_cache
from threading import Lock
import json
import os
import re
import time
import traceback
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError
from fastapi import HTTPException

from backend.core.config import (
    DEFAULT_FOLDER,
    FAILURE_CACHE_SECONDS,
    PRIVATE_CLIP_FIELDS,
    PROFILE_CACHE_SECONDS,
)

profile_cache = {}
profile_cache_lock = Lock()


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


def resolve_storage_folder(user_id):
    # Auth stays in app1 until the next refactor; defer this import to avoid a cycle.
    from app1 import clerk_profile

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
    from backend.media import content_type as media_content_type
    # Local media already uses the same ownership-checked /clips route.
    if uses_local_storage():
        return {"storage": "local"}
    from app1 import load_json
    owner = load_json(folder / 'owner.json')

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
            media_content_type(filename),
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


def upload_source_media(folder, job_id, owner):
    """Back up normalized sources alongside clips; retain local sources for editing."""
    if uses_local_storage():
        return {}
    from backend.media import content_type
    suffix = '.mp3' if owner.get('media_kind') == 'audio' else '.mp4'
    prefix = f"{safe_folder_name(owner.get('user_folder')) or DEFAULT_FOLDER}/{owner['user_id']}/jobs/{job_id}"
    bucket, client = s3_bucket(), s3_client()
    key = prefix+'/source'+suffix
    client.upload_file(str(folder/'source.video'), bucket, key, ExtraArgs={'ContentType':content_type(key)})
    result = {'source_s3_bucket':bucket, 'source_s3_key':key}
    original = folder/'original-upload.media'
    if original.is_file():
        original_key = prefix+'/original-upload'+Path(owner.get('source_name','')).suffix.lower()
        client.upload_file(str(original), bucket, original_key, ExtraArgs={'ContentType':'application/octet-stream'})
        result['original_source_s3_key'] = original_key
    return result
