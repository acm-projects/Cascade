"""Media inspection, FFmpeg execution, caption writing, and clip encoding."""
from pathlib import Path
import html
import os
import subprocess


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


def render_clip(video_path, selection, output_path, threads):
    if Path(output_path).suffix == '.mp3':
        run_command(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(selection['start']),
            '-i', str(video_path), '-t', str(selection['end']-selection['start']),
            '-map', '0:a:0', '-vn', '-c:a', 'libmp3lame', '-b:a', '192k', str(output_path)])
        return
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
