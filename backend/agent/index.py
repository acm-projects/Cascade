"""Per-video search index: CLIP frame embeddings + Whisper transcript embeddings.

Built once per uploaded video and cached on disk by file hash, so re-running the
agent on the same video skips the expensive embedding work. The heavy models are
imported lazily from video_search.router (which already loads them once per
process) so importing this module stays cheap.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

MIN_FRAME_INTERVAL = 2.0
MAX_FRAMES = 300


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass
class VideoIndex:
    duration: float
    frame_interval: float
    frame_times: list[float]
    frame_embeddings: np.ndarray  # (n_frames, d), L2-normalized
    transcript: list[dict[str, Any]]  # [{start, end, text}]
    segment_embeddings: np.ndarray  # (n_segments, d), L2-normalized
    encode_visual_query: Callable[[str], np.ndarray] = field(repr=False, default=None)
    encode_text_query: Callable[[str], np.ndarray] = field(repr=False, default=None)

    def search(self, query: str, mode: str = "visual", top_k: int = 5) -> list[dict[str, Any]]:
        """Return up to top_k well-separated hits as {start, end, score, text?}."""
        if mode == "speech":
            if len(self.transcript) == 0:
                return []
            scores = self.segment_embeddings @ self.encode_text_query(query)
            order = np.argsort(-scores)[:top_k]
            return [
                {
                    "start": round(self.transcript[i]["start"], 1),
                    "end": round(self.transcript[i]["end"], 1),
                    "score": round(float(scores[i]), 3),
                    "text": self.transcript[i]["text"],
                }
                for i in order
            ]

        scores = self.frame_embeddings @ self.encode_visual_query(query)
        hits: list[dict[str, Any]] = []
        picked_times: list[float] = []
        for i in np.argsort(-scores):
            t = self.frame_times[i]
            # Non-max suppression: skip frames right next to an already-picked hit.
            if any(abs(t - p) < 2 * self.frame_interval for p in picked_times):
                continue
            picked_times.append(t)
            hits.append(
                {
                    "start": round(max(0.0, t - self.frame_interval), 1),
                    "end": round(min(self.duration, t + self.frame_interval), 1),
                    "score": round(float(scores[i]), 3),
                }
            )
            if len(hits) >= top_k:
                break
        return hits

    def transcript_between(self, start: float, end: float) -> str:
        parts = [
            seg["text"]
            for seg in self.transcript
            if seg["end"] > start and seg["start"] < end
        ]
        return " ".join(parts)


def _probe_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path),
        ],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _extract_sampled_frames(video_path: Path, frames_dir: Path, interval: float) -> list[Path]:
    frames_dir.mkdir(exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", f"fps=1/{interval}",
            "-frames:v", str(MAX_FRAMES),
            str(frames_dir / "frame_%05d.jpg"),
        ],
        check=True, capture_output=True, text=True,
    )
    return sorted(frames_dir.glob("frame_*.jpg"))


def build_index(
    video_path: Path,
    work_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> VideoIndex:
    """Build (or load from cache) the search index for a video file."""
    emit = progress or (lambda msg: None)

    # Lazy: these load multi-hundred-MB models at import time.
    from video_search.router import search_model, visual_model, whisper_model
    from PIL import Image

    def encode_visual_query(q: str) -> np.ndarray:
        return visual_model.encode(q, normalize_embeddings=True)

    def encode_text_query(q: str) -> np.ndarray:
        return search_model.encode(q, normalize_embeddings=True)

    key = file_sha256(video_path)
    meta_path = CACHE_DIR / f"{key}.json"
    arrays_path = CACHE_DIR / f"{key}.npz"

    if meta_path.exists() and arrays_path.exists():
        emit("Loaded video index from cache")
        meta = json.loads(meta_path.read_text())
        arrays = np.load(arrays_path)
        return VideoIndex(
            duration=meta["duration"],
            frame_interval=meta["frame_interval"],
            frame_times=meta["frame_times"],
            frame_embeddings=arrays["frame_embeddings"],
            transcript=meta["transcript"],
            segment_embeddings=arrays["segment_embeddings"],
            encode_visual_query=encode_visual_query,
            encode_text_query=encode_text_query,
        )

    duration = _probe_duration(video_path)
    interval = max(MIN_FRAME_INTERVAL, duration / MAX_FRAMES)

    emit("Sampling frames")
    frame_paths = _extract_sampled_frames(video_path, work_dir / "index_frames", interval)
    if not frame_paths:
        raise RuntimeError("No frames could be extracted from this video.")

    emit("Embedding frames with CLIP")
    images = []
    for p in frame_paths:
        with Image.open(p) as img:
            images.append(img.convert("RGB"))
    frame_embeddings = visual_model.encode(images, normalize_embeddings=True, batch_size=32)
    frame_times = [round(i * interval, 2) for i in range(len(frame_paths))]

    emit("Transcribing speech")
    segments, _ = whisper_model.transcribe(str(video_path))
    transcript = [
        {"start": s.start, "end": s.end, "text": s.text.strip()}
        for s in segments
        if s.text.strip()
    ]
    if transcript:
        segment_embeddings = search_model.encode(
            [seg["text"] for seg in transcript], normalize_embeddings=True
        )
    else:
        segment_embeddings = np.zeros((0, 1), dtype=np.float32)

    meta_path.write_text(
        json.dumps(
            {
                "duration": duration,
                "frame_interval": interval,
                "frame_times": frame_times,
                "transcript": transcript,
            }
        )
    )
    np.savez(arrays_path, frame_embeddings=frame_embeddings, segment_embeddings=segment_embeddings)

    return VideoIndex(
        duration=duration,
        frame_interval=interval,
        frame_times=frame_times,
        frame_embeddings=frame_embeddings,
        transcript=transcript,
        segment_embeddings=segment_embeddings,
        encode_visual_query=encode_visual_query,
        encode_text_query=encode_text_query,
    )
