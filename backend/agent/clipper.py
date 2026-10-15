"""Cut a selected moment out of the source video into its own short MP4.

Input seeking + re-encode, so the cut is frame-accurate (a stream copy can only start on a
keyframe, which on a long podcast can be several seconds off). Output is capped at 720p so
cutting stays fast and the files stay small; it never upscales.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

MAX_OUTPUT_HEIGHT = 720
CUT_TIMEOUT_SECONDS = 600


class ClipError(RuntimeError):
    pass


def cut_clip(video_path: Path, start: float, end: float, out_path: Path) -> Path:
    if end <= start:
        raise ClipError(f"Invalid clip range {start}-{end}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".part.mp4")  # never leave a half-written file at the real name
    command = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-i", str(video_path),
        "-t", f"{end - start:.3f}",
        "-map", "0:v:0", "-map", "0:a:0?",
        # even dimensions for H.264, capped at MAX_OUTPUT_HEIGHT, never upscaled
        "-vf", f"scale=-2:'min({MAX_OUTPUT_HEIGHT},ih)'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(tmp_path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=CUT_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        tmp_path.unlink(missing_ok=True)
        raise ClipError("Cutting the clip timed out.") from exc
    if result.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        raise ClipError(f"ffmpeg failed: {result.stderr.strip()[-300:]}")
    tmp_path.replace(out_path)
    return out_path
