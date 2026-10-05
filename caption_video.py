from pathlib import Path
import json
import subprocess

from ollama import chat


PROJECT_DIR = Path(__file__).resolve().parent
VIDEO_PATH = PROJECT_DIR / "test_video.mp4"
FRAMES_DIR = PROJECT_DIR / "video_frames"
OUTPUT_PATH = PROJECT_DIR / "video_descriptions.json"

FRAME_INTERVAL = 2
GROUP_SIZE = 5


def main():
    if not VIDEO_PATH.is_file():
        raise SystemExit(f"Video not found: {VIDEO_PATH}")

    frames = sorted(FRAMES_DIR.glob("frame_*.jpg"))

    if not frames:
        raise SystemExit(
            "No frames found. Extract the frames with FFmpeg first."
        )

    # Read the actual duration instead of hardcoding 214 seconds.
    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(VIDEO_PATH),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(probe.stdout.strip())

    results = []
    total_groups = (len(frames) + GROUP_SIZE - 1) // GROUP_SIZE

    for group_number, offset in enumerate(
        range(0, len(frames), GROUP_SIZE),
        start=1,
    ):
        group = frames[offset:offset + GROUP_SIZE]

        # Approximate ranges for the existing FFmpeg frame extraction.
        start = offset * FRAME_INTERVAL
        end = min(
            (offset + len(group)) * FRAME_INTERVAL,
            duration,
        )

        if start >= duration:
            break

        print(
            f"\n[{group_number}/{total_groups}] "
            f"Analyzing {start:.1f}–{end:.1f} seconds...",
            flush=True,
        )

        description_parts = []

        for chunk in chat(
            model="qwen3-vl:4b",
            options={"num_ctx": 16384},
            messages=[{
                "role": "user",
                "content": (
                    "These images are consecutive samples from a video "
                    "in chronological order, approximately 2 seconds apart. "
                    f"They cover approximately {start:.1f} to {end:.1f} "
                    "seconds of the original video. "
                    "Describe the visible sequence of events in 3–5 "
                    "sentences. Include changes in actions, expressions, "
                    "objects, and readable text. Distinguish observations "
                    "from guesses. Do not invent dialogue or sounds: "
                    "you have no audio. Describe events without deciding "
                    "whether they are funny."
                ),
                "images": [str(frame) for frame in group],
            }],
            stream=True,
        ):
            text = chunk.message.content or ""
            description_parts.append(text)
            print(text, end="", flush=True)

        description = "".join(description_parts).strip()

        if not description:
            raise RuntimeError(
                f"The model returned no description for group {group_number}."
            )

        print(flush=True)

        results.append({
            "start": start,
            "end": end,
            "visual_description": description,
        })

        # Save progress after every completed group.
        OUTPUT_PATH.write_text(
            json.dumps(results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"\nDone! Saved descriptions to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()