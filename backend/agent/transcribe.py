"""Speech-to-text: Deepgram (default) or local Whisper (opt-in).

Whatever the provider, the result is a list of sentence-level segments
{start, end, text, speaker} - the shape VideoIndex.transcript already uses - so
speech search, inspect_clip and read_transcript don't care where it came from.

There is deliberately NO automatic fallback from Deepgram to Whisper: silently
switching would turn a seconds-long step into hours of CPU work on a long video.
Set TRANSCRIPTION_PROVIDER=whisper in .env to use Whisper on purpose.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import httpx

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_MODEL = "nova-3"
DEEPGRAM_USD_PER_MINUTE = 0.0043  # Nova-3 monolingual pay-as-you-go (deepgram.com/pricing)

# Segmenting rules for turning Deepgram's word list into sentence-level segments.
MAX_GAP_SECONDS = 1.0
MAX_SEGMENT_SECONDS = 25.0
MIN_WORDS_FOR_SENTENCE_BREAK = 3  # keeps "Yeah." / "Right." from becoming 1-word segments
SENTENCE_END = (".", "?", "!")

# Generous: a long audio upload plus server-side processing can take minutes.
REQUEST_TIMEOUT = httpx.Timeout(900.0, connect=30.0)


class TranscriptionError(RuntimeError):
    """A transcription failure with a message that is safe to show the user."""


def provider() -> str:
    value = os.environ.get("TRANSCRIPTION_PROVIDER", "deepgram").strip().lower()
    if value not in ("deepgram", "whisper"):
        raise TranscriptionError(
            f"TRANSCRIPTION_PROVIDER must be 'deepgram' or 'whisper' (got '{value}')."
        )
    return value


def provider_tag() -> str:
    """Identifies provider + model; part of the transcript cache key."""
    p = provider()
    return f"{p}-{DEEPGRAM_MODEL}" if p == "deepgram" else "whisper-base"


def has_audio_stream(video_path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(video_path),
        ],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def extract_audio(video_path: Path, dest_dir: Path) -> Path:
    """Mono 16 kHz MP3 (~20 MB/hour) - small enough to upload quickly."""
    audio_path = dest_dir / "audio.mp3"
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "libmp3lame", "-b:a", "48k",
            str(audio_path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not audio_path.exists():
        raise TranscriptionError(f"Could not extract audio: {result.stderr.strip()[-300:]}")
    return audio_path


def deepgram_request(
    audio_path: Path,
    api_key: str,
    client: httpx.Client | None = None,
    info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST the audio to Deepgram and return the parsed JSON response.

    If `info` is given it records whether diarization had to be dropped
    (info["diarization_dropped"]), so a wrong parameter is visible, not silent.
    """
    base_params = {
        "model": DEEPGRAM_MODEL,
        "smart_format": "true",
        "punctuate": "true",
    }
    headers = {"Authorization": f"Token {api_key}", "Content-Type": "audio/mpeg"}
    audio_bytes = audio_path.read_bytes()  # ~20 MB/hour; plain bytes keep a Content-Length
    own_client = client is None
    http = client or httpx.Client(timeout=REQUEST_TIMEOUT)

    def post(params: dict[str, str]) -> httpx.Response:
        try:
            return http.post(
                DEEPGRAM_URL, params=params, headers=headers, content=audio_bytes
            )
        except httpx.TimeoutException as exc:
            raise TranscriptionError("Deepgram timed out. Try again, or use a shorter file.") from exc
        except httpx.HTTPError as exc:
            raise TranscriptionError(f"Could not reach Deepgram: {type(exc).__name__}") from exc

    try:
        # diarize_model is the documented way to turn on speaker labels.
        response = post({**base_params, "diarize_model": "latest"})
        if response.status_code == 400:
            # If the diarization parameter was the problem, transcribe without speakers
            # rather than failing the whole job.
            response = post(base_params)
            if info is not None and response.status_code < 400:
                info["diarization_dropped"] = True
    finally:
        if own_client:
            http.close()

    if response.status_code == 401 or response.status_code == 403:
        raise TranscriptionError("Deepgram rejected the API key (check DEEPGRAM_API_KEY in .env).")
    if response.status_code == 402:
        raise TranscriptionError("Deepgram reports insufficient credit for this request.")
    if response.status_code == 429:
        raise TranscriptionError("Deepgram is rate limiting requests. Try again shortly.")
    if response.status_code == 504:
        raise TranscriptionError("Deepgram timed out processing this file.")
    if response.status_code >= 400:
        raise TranscriptionError(f"Deepgram returned HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError as exc:
        raise TranscriptionError("Deepgram returned an unreadable response.") from exc


def words_to_segments(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group Deepgram words into sentence-level segments (pure function).

    Breaks on: a speaker change, sentence-ending punctuation (once the segment has a
    few words), a gap over MAX_GAP_SECONDS, or MAX_SEGMENT_SECONDS of speech.
    """
    segments: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        if not current:
            return
        text = " ".join(
            (w.get("punctuated_word") or w.get("word") or "").strip() for w in current
        ).strip()
        if text:
            segments.append(
                {
                    "start": float(current[0]["start"]),
                    "end": float(current[-1]["end"]),
                    "text": text,
                    "speaker": current[0].get("speaker"),
                }
            )
        current.clear()

    for word in words:
        if "start" not in word or "end" not in word:
            continue
        if current:
            prev = current[-1]
            if (
                word.get("speaker") != current[0].get("speaker")
                or float(word["start"]) - float(prev["end"]) > MAX_GAP_SECONDS
                or float(word["end"]) - float(current[0]["start"]) > MAX_SEGMENT_SECONDS
            ):
                flush()
        current.append(word)
        shown = (word.get("punctuated_word") or word.get("word") or "").strip()
        if shown.endswith(SENTENCE_END) and len(current) >= MIN_WORDS_FOR_SENTENCE_BREAK:
            flush()
    flush()
    return segments


def segments_from_deepgram(response: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        words = response["results"]["channels"][0]["alternatives"][0].get("words", [])
    except (KeyError, IndexError, TypeError) as exc:
        raise TranscriptionError("Deepgram's response had no transcript data.") from exc
    return words_to_segments(words)


def _transcribe_whisper(video_path: Path) -> list[dict[str, Any]]:
    # Lazy: importing video_search.router loads the heavy models.
    from video_search.router import whisper_model

    segments, _ = whisper_model.transcribe(str(video_path))
    return [
        {"start": s.start, "end": s.end, "text": s.text.strip(), "speaker": None}
        for s in segments
        if s.text.strip()
    ]


def transcribe_video(
    video_path: Path,
    work_dir: Path,
    progress: Callable[[str], None] | None = None,
    info: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Returns segments. If `info` is given it receives `cost_usd` (Deepgram only)."""
    emit = progress or (lambda msg: None)

    if not has_audio_stream(video_path):
        emit("No audio track found; skipping transcription")
        return []

    if provider() == "whisper":
        emit("Transcribing speech with local Whisper (slow on CPU)")
        return _transcribe_whisper(video_path)

    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise TranscriptionError(
            "DEEPGRAM_API_KEY is not set. Add it to .env and restart, or set "
            "TRANSCRIPTION_PROVIDER=whisper to use local Whisper instead."
        )

    emit("Extracting audio")
    audio_path = extract_audio(video_path, work_dir)
    emit(f"Transcribing with Deepgram ({audio_path.stat().st_size / 1e6:.1f} MB of audio)")
    dg_info: dict[str, Any] = {}
    response = deepgram_request(audio_path, api_key, info=dg_info)
    if dg_info.get("diarization_dropped"):
        emit("Deepgram rejected diarization; continuing without speaker labels")
    if info is not None:
        minutes = float((response.get("metadata") or {}).get("duration") or 0.0) / 60.0
        info["cost_usd"] = minutes * DEEPGRAM_USD_PER_MINUTE
    emit("Building transcript segments")
    return segments_from_deepgram(response)
