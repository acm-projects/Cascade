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
import time
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
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
    has_video: bool = True
    index_mode: str = "multimodal"
    timings: dict[str, float] = field(default_factory=dict)
    video_key: str = ""  # sha256 of the video file; ties per-video caches (and saved research) together

    def search(self, query: str, mode: str = "visual", top_k: int = 5) -> list[dict[str, Any]]:
        """Return up to top_k well-separated hits as {start, end, score, text?, speaker?}."""
        if mode == "speech" or not self.has_video or not self.frame_times:
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
    *,
    visual: bool = True,
) -> VideoIndex:
    """Build independent transcript/visual indexes concurrently; callbacks stay on the caller thread."""
    from PIL import Image
    from backend.video_search import router as vs
    from backend.media import probe_media

    emit = progress or (lambda msg: None)
    media_info = probe_media(video_path)
    key = file_sha256(video_path)
    timings = {}

    def transcript_index(report):
        started = time.perf_counter()
        transcript_path, segemb_path = transcript_cache_paths(key, TRANSCRIPT_TAG)
        cost = 0.0
        vs.load_models("speech", report)
        if transcript_path.exists() and segemb_path.exists():
            report("Loaded transcript from cache")
            transcript = json.loads(transcript_path.read_text())
            embeddings = np.load(segemb_path)
        else:
            info = {}
            transcript = transcribe_media(video_path, work_dir, progress=report, info=info)
            cost = info.get("cost_usd", 0.0)
            if transcript:
                report("Embedding transcript")
                embeddings = vs.search_model.encode([s["text"] for s in transcript], normalize_embeddings=True)
            else:
                embeddings = np.zeros((0, 1), dtype=np.float32)
            transcript_path.write_text(json.dumps(transcript))
            np.save(segemb_path, embeddings)
        timings['transcript_index_seconds'] = round(time.perf_counter() - started, 3)
        return transcript, embeddings, cost

    def visual_index(report):
        started = time.perf_counter()
        vs.load_models("visual", report)
        cache = CACHE_DIR / f"frames_{key}.npz"
        if cache.exists():
            report("Loaded frame embeddings from cache")
            with np.load(cache) as data:
                result = (float(data["duration"]), float(data["interval"]),
                          [float(t) for t in data["frame_times"]], data["frame_embeddings"])
        else:
            duration = media_info['duration']
            interval = max(MIN_FRAME_INTERVAL, duration / MAX_FRAMES)
            report("Sampling frames")
            times, paths = _sample_frames(video_path, work_dir / "index_frames", duration, interval)
            report("Embedding frames with CLIP")
            images = []
            for path in paths:
                with Image.open(path) as image:
                    images.append(image.convert("RGB"))
            embeddings = vs.visual_model.encode(images, normalize_embeddings=True, batch_size=32)
            np.savez(cache, frame_embeddings=embeddings, frame_times=np.array(times),
                     interval=np.array(interval), duration=np.array(duration))
            result = duration, interval, times, embeddings
        timings['visual_index_seconds'] = round(time.perf_counter() - started, 3)
        return result

    started = time.perf_counter()
    if visual and media_info['has_video']:
        emit("Building transcript and visual indexes in parallel")
        messages = Queue()
        # Only the caller invokes progress: cancellation and job state updates stay serialized.
        with ThreadPoolExecutor(max_workers=2) as pool:
            speech = pool.submit(transcript_index, messages.put)
            frames = pool.submit(visual_index, messages.put)
            pending = {speech, frames}
            while pending:
                _, pending = wait(pending, timeout=.1, return_when=FIRST_COMPLETED)
                while True:
                    try:
                        message = messages.get_nowait()
                    except Empty:
                        break
                    emit(message)
            transcript, segment_embeddings, transcription_cost = speech.result()
            duration, interval, frame_times, frame_embeddings = frames.result()
    else:
        emit("Building transcript-first search index")
        transcript, segment_embeddings, transcription_cost = transcript_index(emit)
        duration, interval, frame_times = media_info['duration'], MIN_FRAME_INTERVAL, []
        frame_embeddings = np.zeros((0, 1), dtype=np.float32)
    timings['index_wall_seconds'] = round(time.perf_counter() - started, 3)

    return VideoIndex(
        duration=duration, has_video=media_info['has_video'], frame_interval=interval,
        frame_times=frame_times, frame_embeddings=frame_embeddings,
        transcript=transcript, segment_embeddings=segment_embeddings,
        encode_visual_query=(lambda q: vs.visual_model.encode(q, normalize_embeddings=True)),
        encode_text_query=(lambda q: vs.search_model.encode(q, normalize_embeddings=True)),
        chunks=build_chunks(transcript), transcription_cost_usd=transcription_cost, video_key=key,
        index_mode='multimodal' if frame_times else 'transcript-first', timings=timings,
    )
