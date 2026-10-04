"""Shared pipeline: download/accept a video, extract frames + transcript,
then ask Claude to tag it with a structured JSON schema.

Used both for the 5 trending YouTube videos and the user's uploaded video.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import anthropic
import whisper
import yt_dlp

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TAGGING_MODEL = "claude-haiku-4-5-20251001"
# Hard kill-switch: when true, extract_tags() never calls the Anthropic API,
# even on a cache miss — it raises instead. Set ANTHROPIC_CALLS_DISABLED=true
# in .env to guarantee zero spend while testing other parts of the pipeline.
ANTHROPIC_CALLS_DISABLED = os.environ.get("ANTHROPIC_CALLS_DISABLED", "").lower() in ("1", "true", "yes")

# Loaded once per process — reused across requests.
_whisper_model = None

# Content-addressed cache for Claude tag extractions: same frames + transcript
# (i.e. the same video, re-analyzed) never re-calls the API. Persists across
# server restarts so you can iterate on other parts of the pipeline for free.
TAGS_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "tags"
TAGS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "hook_style": {
            "type": "string",
            "description": "How the video opens / grabs attention in the first few seconds",
        },
        "pacing": {
            "type": "string",
            "enum": ["fast", "medium", "slow"],
        },
        "visual_style": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Notable visual traits, e.g. text overlays, jump cuts, close-ups",
        },
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Subject matter / themes covered",
        },
        "tone": {
            "type": "string",
            "description": "Overall tone, e.g. humorous, informative, dramatic",
        },
        "audio_style": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Notable audio traits, e.g. trending sound, voiceover, music genre",
        },
        "call_to_action": {
            "type": "string",
            "description": "Any explicit CTA present, or empty string if none",
        },
    },
    "required": ["hook_style", "pacing", "visual_style", "topics", "tone", "audio_style", "call_to_action"],
}


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = whisper.load_model("base")
    return _whisper_model


def download_video(video_id: str, dest_dir: Path) -> Path:
    """Download a YouTube video by id into dest_dir, return the file path."""
    out_template = str(dest_dir / f"{video_id}.%(ext)s")
    ydl_opts = {
        "format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]/best",
        "merge_output_format": "mp4",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

    matches = list(dest_dir.glob(f"{video_id}.*"))
    if not matches:
        raise RuntimeError(f"yt-dlp did not produce an output file for {video_id}")
    return matches[0]


def extract_frames(video_path: Path, dest_dir: Path, count: int = 5) -> list[Path]:
    """Extract `count` evenly-spaced frames from the video using ffmpeg."""
    frames_dir = dest_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    duration = _probe_duration(video_path)
    frame_paths = []
    for i in range(count):
        timestamp = max(duration * (i + 1) / (count + 1), 0.1)
        out_path = frames_dir / f"frame_{i}.jpg"
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(out_path),
            ]
        )
        if out_path.exists():
            frame_paths.append(out_path)
    return frame_paths


def _probe_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 30.0


def _has_audio_stream(video_path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")


def extract_audio(video_path: Path, dest_dir: Path) -> Path | None:
    """Extract audio to a WAV file, or return None if the video has no audio track."""
    if not _has_audio_stream(video_path):
        return None

    audio_path = dest_dir / "audio.wav"
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(audio_path),
        ]
    )
    return audio_path


def transcribe(audio_path: Path | None) -> str:
    if audio_path is None:
        return ""
    model = _get_whisper_model()
    result = model.transcribe(str(audio_path))
    return result.get("text", "").strip()


def _tags_cache_key(frame_paths: list[Path], transcript: str) -> str:
    hasher = hashlib.sha256()
    hasher.update(TAGGING_MODEL.encode("utf-8"))
    hasher.update(transcript.encode("utf-8"))
    for frame_path in frame_paths:
        hasher.update(frame_path.read_bytes())
    return hasher.hexdigest()


def extract_tags(frame_paths: list[Path], transcript: str) -> dict[str, Any]:
    """Call the Anthropic API with frames + transcript to get structured tags.

    Results are cached on disk by a hash of the input frames + transcript, so
    re-analyzing the same video never re-calls the API.
    """
    cache_key = _tags_cache_key(frame_paths, transcript)
    cache_path = TAGS_CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    if ANTHROPIC_CALLS_DISABLED:
        raise RuntimeError(
            "Anthropic API calls are disabled (ANTHROPIC_CALLS_DISABLED=true in .env) "
            "and this video has no cached tags."
        )

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Analyze this short video's frames and transcript. "
                "Extract structured tags describing its style and content.\n\n"
                f"Transcript:\n{transcript or '(no speech detected)'}"
            ),
        }
    ]
    for frame_path in frame_paths:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(frame_path.read_bytes()).decode("utf-8"),
                },
            }
        )

    response = client.messages.create(
        model=TAGGING_MODEL,
        max_tokens=1024,
        tools=[
            {
                "name": "record_video_tags",
                "description": "Record structured tags describing a video's style and content.",
                "input_schema": TAG_SCHEMA,
            }
        ],
        tool_choice={"type": "tool", "name": "record_video_tags"},
        messages=[{"role": "user", "content": content}],
    )

    for block in response.content:
        if block.type == "tool_use":
            tags = block.input
            cache_path.write_text(json.dumps(tags))
            return tags

    raise RuntimeError("Claude did not return structured tags")


def analyze_video_file(
    video_path: Path, work_dir: Path, progress: Callable[[str], None] | None = None
) -> dict[str, Any]:
    """Run the full frame/transcribe/tag pipeline on an already-downloaded video file."""
    emit = progress or (lambda msg: None)

    emit("Extracting frames")
    frames = extract_frames(video_path, work_dir)

    emit("Extracting audio")
    audio_path = extract_audio(video_path, work_dir)

    emit("Transcribing audio" if audio_path else "No audio track found, skipping transcription")
    transcript = transcribe(audio_path)

    emit("Tagging with Claude")
    tags = extract_tags(frames, transcript)

    emit("Done")
    return {"tags": tags, "transcript": transcript}


def analyze_youtube_video(
    video_id: str, work_dir: Path, progress: Callable[[str], None] | None = None
) -> dict[str, Any]:
    """Download a YouTube video by id and run the full pipeline on it."""
    emit = progress or (lambda msg: None)

    emit("Downloading video")
    video_dir = work_dir / video_id
    video_dir.mkdir(exist_ok=True)
    video_path = download_video(video_id, video_dir)
    return analyze_video_file(video_path, video_dir, progress=progress)
