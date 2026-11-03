"""Media inspection, FFmpeg execution, caption writing, and clip encoding."""
from pathlib import Path
import html
import logging
import os
import subprocess
import tempfile


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


def inspect_video(video_path):
    # Compatibility name: callers may now provide either an audio or video source.
    from backend.media import probe_media
    info = probe_media(video_path)
    return info['duration'], info['has_audio']


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
            ), quote=False
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


def render_workers(clip_count):
    """How many clips to encode at once: about half the cores (x264 already uses several per encode)."""
    cores = os.cpu_count() or 1
    return max(1, min(clip_count, cores // 2))


def encoder_threads(workers):
    """Split the cores between the parallel encodes so they do not oversubscribe the CPU."""
    return max(1, (os.cpu_count() or 1) // workers)


def keyframes_between(video_path, start, end):
    """Keyframe times (seconds) of the first video stream from the keyframe at or before `start` to `end`."""
    out = run_command(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                       "-read_intervals", f"{start}%{end}", "-show_entries", "frame=pts_time", "-of", "csv=p=0",
                       str(video_path)])
    return sorted(float(t) for t in out.replace(",", " ").split() if t.strip())


def smart_cut(video_path, start, end, output_path, threads, scratch, head_preset="superfast"):
    """Frame-exact clip without re-encoding it all: only start → the next keyframe is re-encoded, the
    rest of the video is copied as stored, then the two are joined. Audio is re-encoded whole (cheap,
    and it avoids a click at the join). Returns False when this source/clip can't be cut this way;
    raises on ffmpeg failure. The caller falls back to a full re-encode in both cases."""
    from backend.media import probe_media
    info = probe_media(video_path)
    # Copied video keeps the source's format, so it must already be what a full encode would produce.
    if (not info["has_video"] or info["video_codec"] != "h264" or info.get("pixel_format") != "yuv420p"
            or info["width"] % 2 or info["height"] % 2 or (info["has_audio"] and info["audio_codec"] != "aac")):
        return False
    following = [t for t in keyframes_between(video_path, start, end) if t >= start - 0.02]
    if not following or following[0] > end - 1.0:
        return False  # no keyframe inside the clip: nothing to copy, a full re-encode is just as fast
    keyframe = following[0]
    scratch = Path(scratch)
    parts = []
    if keyframe - start > 0.04:
        head = scratch / "head.ts"
        run_command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start), "-i", str(video_path),
                     "-t", f"{keyframe - start:.3f}", "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", head_preset,
                     "-threads", str(threads), "-pix_fmt", "yuv420p", "-f", "mpegts", str(head)])
        parts.append(head)
    tail = scratch / "tail.ts"
    # Seeking just past the keyframe lands exactly on it (input seeking goes to the keyframe at or before).
    run_command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{keyframe + 0.001:.3f}", "-i", str(video_path),
                 "-t", f"{end - keyframe:.3f}", "-map", "0:v:0", "-an", "-c:v", "copy", "-bsf:v", "h264_mp4toannexb",
                 "-f", "mpegts", str(tail)])
    parts.append(tail)
    listing = scratch / "parts.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    audio = ["-ss", str(start), "-t", f"{end - start:.3f}", "-i", str(video_path)] if info["has_audio"] else []
    # Audio is one continuous piece (only the video is joined), and AAC cuts cleanly without re-encoding.
    # The start is frame-exact; the copied end can run ~2 frames long (B-frames are stored out of order),
    # which is unnoticeable and much cheaper than also re-encoding the last keyframe interval.
    run_command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), *audio,
                 "-map", "0:v:0", *(["-map", "1:a:0"] if audio else []), "-c", "copy", "-t", f"{end - start:.3f}",
                 "-movflags", "+faststart", str(output_path)])
    # A join that doesn't decode cleanly (or a clip of the wrong length) is rejected, never shown.
    produced = probe_media(output_path)["duration"]
    if abs(produced - (end - start)) > 0.5:
        raise RuntimeError(f"Smart cut produced {produced:.2f}s instead of {end - start:.2f}s")
    check = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, keyframe - start - 1):.3f}",
                            "-i", str(output_path), "-t", "3", "-f", "null", "-"], capture_output=True, text=True)
    if check.returncode != 0 or check.stderr.strip():
        raise RuntimeError("Smart cut join does not decode cleanly: " + check.stderr[-300:])
    return True


def render_clip(video_path, selection, output_path, threads):
    if Path(output_path).suffix == '.mp3':
        run_command(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(selection['start']),
            '-i', str(video_path), '-t', str(selection['end']-selection['start']),
            '-map', '0:a:0', '-vn', '-c:a', 'libmp3lame', '-b:a', '192k', str(output_path)])
        return
    # Smart cut first (a few seconds instead of ~20); any doubt about its result means a full re-encode.
    try:
        with tempfile.TemporaryDirectory(prefix="smart_cut_") as scratch:
            if smart_cut(video_path, selection["start"], selection["end"], output_path, threads, scratch):
                return
    except Exception as error:
        logging.getLogger(__name__).warning("Smart cut failed, re-encoding the whole clip: %s", str(error)[:300])
    run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(selection["start"]),
        "-i", str(video_path),
        "-t", str(selection["end"] - selection["start"]),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-preset", "veryfast", "-threads", str(threads),
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
        str(output_path),
    ])
