"""Per-video search index: CLIP frame embeddings + transcript embeddings.

Built once per uploaded video and cached on disk. Two independent caches:
  * frames:     keyed by file hash only (CLIP embedding is the expensive local step)
  * transcript: keyed by file hash + transcription provider/model, so switching
                provider re-transcribes but never re-embeds frames
The heavy models come from the website's lazy loader in backend.video_search.router (which loads
them once per process) so importing this module stays cheap.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .chunks import build_chunks
from backend.cascade_stt import TRANSCRIPT_TAG, transcribe_media

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

MIN_FRAME_INTERVAL = 2.0
MAX_FRAMES = 300
FRAME_WIDTH = 448          # CLIP resizes to 224 anyway; smaller files seek/decode faster
FRAME_WORKERS = 4


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
    transcript: list[dict[str, Any]]  # [{start, end, text, speaker}]
    segment_embeddings: np.ndarray  # (n_segments, d), L2-normalized
    encode_visual_query: Callable[[str], np.ndarray] = field(repr=False, default=None)
    encode_text_query: Callable[[str], np.ndarray] = field(repr=False, default=None)
    # Long-transcript support (filled by build_index / summaries.ensure_summaries):
    chunks: list[dict[str, Any]] = field(default_factory=list)
    chunk_summaries: list[dict[str, Any]] = field(default_factory=list)
    summary_usage: dict[str, Any] = field(default_factory=dict)
    transcription_cost_usd: float = 0.0  # Deepgram spend for this build; 0 on a cache hit
    video_key: str = ""  # sha256 of the video file; ties per-video caches (and saved research) together

    def search(self, query: str, mode: str = "visual", top_k: int = 5) -> list[dict[str, Any]]:
        """Return up to top_k well-separated hits as {start, end, score, text?, speaker?}."""
        if mode == "speech":
            if len(self.transcript) == 0:
                return []
            scores = self.segment_embeddings @ self.encode_text_query(query)
            order = np.argsort(-scores)[:top_k]
            hits = []
            for i in order:
                hit = {
                    "start": round(self.transcript[i]["start"], 1),
                    "end": round(self.transcript[i]["end"], 1),
                    "score": round(float(scores[i]), 3),
                    "text": self.transcript[i]["text"],
                }
                if self.transcript[i].get("speaker") is not None:
                    hit["speaker"] = self.transcript[i]["speaker"]
                hits.append(hit)
            return hits

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

    def segments_between(self, start: float, end: float) -> list[dict[str, Any]]:
        return [seg for seg in self.transcript if seg["end"] > start and seg["start"] < end]


def transcript_cache_paths(key: str, tag: str) -> tuple[Path, Path]:
    """Transcript + segment-embedding cache files. `tag` is provider+model, so switching
    transcription provider can never serve a transcript made by another one."""
    return CACHE_DIR / f"transcript_{key}_{tag}.json", CACHE_DIR / f"segemb_{key}_{tag}.npy"


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


def _grab_frame(video_path: Path, t: float, out_path: Path) -> None:
    """One frame via input seeking - fast on long videos (no full-file decode)."""
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{t:.2f}", "-i", str(video_path),
            "-an", "-sn", "-frames:v", "1",
            "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "4",
            str(out_path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg could not extract a frame at {t:.1f}s: {result.stderr.strip()[-200:]}")


def _sample_frames(video_path: Path, frames_dir: Path, duration: float, interval: float):
    frames_dir.mkdir(exist_ok=True)
    count = max(1, min(MAX_FRAMES, int(duration // interval)))
    times = [round(min(i * interval, max(0.0, duration - 0.1)), 2) for i in range(count)]
    paths = [frames_dir / f"frame_{i:05d}.jpg" for i in range(count)]
    with ThreadPoolExecutor(max_workers=FRAME_WORKERS) as pool:
        list(pool.map(lambda tp: _grab_frame(video_path, tp[0], tp[1]), zip(times, paths)))
    return times, paths


def build_index(
    video_path: Path,
    work_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> VideoIndex:
    """Build (or load from cache) the search index for a video file."""
    emit = progress or (lambda msg: None)

    # Use the website's own lazy model loader, through its one module path (backend.video_search.router),
    # so CLIP / MiniLM are loaded once per process even when the visual/speech engines run too.
    from PIL import Image
    from backend.video_search import router as vs

    vs.load_models("visual", emit)
    vs.load_models("speech", emit)

    def encode_visual_query(q: str) -> np.ndarray:
        return vs.visual_model.encode(q, normalize_embeddings=True)

    def encode_text_query(q: str) -> np.ndarray:
        return vs.search_model.encode(q, normalize_embeddings=True)

    key = file_sha256(video_path)

    # ---- frames (provider-independent) ----
    frames_path = CACHE_DIR / f"frames_{key}.npz"
    if frames_path.exists():
        emit("Loaded frame embeddings from cache")
        data = np.load(frames_path)
        duration = float(data["duration"])
        interval = float(data["interval"])
        frame_times = [float(t) for t in data["frame_times"]]
        frame_embeddings = data["frame_embeddings"]
    else:
        duration = _probe_duration(video_path)
        interval = max(MIN_FRAME_INTERVAL, duration / MAX_FRAMES)
        emit("Sampling frames")
        frame_times, frame_paths = _sample_frames(video_path, work_dir / "index_frames", duration, interval)
        emit("Embedding frames with CLIP")
        images = []
        for p in frame_paths:
            with Image.open(p) as img:
                images.append(img.convert("RGB"))
        frame_embeddings = vs.visual_model.encode(images, normalize_embeddings=True, batch_size=32)
        np.savez(
            frames_path,
            frame_embeddings=frame_embeddings,
            frame_times=np.array(frame_times),
            interval=np.array(interval),
            duration=np.array(duration),
        )

    # ---- transcript (keyed by provider + model) ----
    tag = TRANSCRIPT_TAG
    transcript_path, segemb_path = transcript_cache_paths(key, tag)
    transcription_cost = 0.0
    if transcript_path.exists() and segemb_path.exists():
        emit("Loaded transcript from cache")
        transcript = json.loads(transcript_path.read_text())
        segment_embeddings = np.load(segemb_path)
    else:
        t_info: dict[str, Any] = {}
        transcript = transcribe_media(video_path, work_dir, progress=emit, info=t_info)
        transcription_cost = t_info.get("cost_usd", 0.0)
        if transcript:
            segment_embeddings = vs.search_model.encode(
                [seg["text"] for seg in transcript], normalize_embeddings=True
            )
        else:
            segment_embeddings = np.zeros((0, 1), dtype=np.float32)
        transcript_path.write_text(json.dumps(transcript))
        np.save(segemb_path, segment_embeddings)

    return VideoIndex(
        duration=duration,
        frame_interval=interval,
        frame_times=frame_times,
        frame_embeddings=frame_embeddings,
        transcript=transcript,
        segment_embeddings=segment_embeddings,
        encode_visual_query=encode_visual_query,
        encode_text_query=encode_text_query,
        chunks=build_chunks(transcript),
        transcription_cost_usd=transcription_cost,
        video_key=key,
    )
