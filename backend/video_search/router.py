from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import json
import math
import os
import re
import shutil
import subprocess
import textwrap

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from faster_whisper import WhisperModel
from moviepy import VideoFileClip, TextClip, CompositeVideoClip
from PIL import Image
from sentence_transformers import SentenceTransformer


router = APIRouter()

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUTS = PROJECT_DIR / "outputs"
OUTPUTS.mkdir(exist_ok=True)

whisper_model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8",
)

search_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

visual_model = SentenceTransformer(
    "sentence-transformers/clip-ViT-B-32"
)

# Existing labels are retained for frontend compatibility.
# All four use the same simple subtitle appearance.
STYLE_NAMES = [
    "hormozi",
    "minimalist",
    "bold_viral",
    "cinematic",
]

FRAME_INTERVAL = 3.0
DIALOGUE_PAUSE = 1.5
SCENE_THRESHOLD = 0.35


# Note: the standalone "/" page is served via StaticFiles at /search-ui
# (see backend/app.py) instead of a dedicated route here, since this router
# is mounted under /api/search alongside the other features' APIs.


@router.get("/clips/{filename}")
def get_clip(filename: str):
    clip = OUTPUTS / filename

    if (
        Path(filename).name != filename
        or clip.suffix != ".mp4"
        or not clip.is_file()
    ):
        raise HTTPException(404, "Clip not found.")

    return FileResponse(clip, media_type="video/mp4")


def get_duration(video_path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    duration = float(
        json.loads(result.stdout)["format"]["duration"]
    )

    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid video duration.")

    return duration


def transcribe_video(video_path):
    segments, _ = whisper_model.transcribe(
        str(video_path),
        word_timestamps=True,
        vad_filter=True,
    )

    transcript = []

    for segment in segments:
        if not segment.text.strip():
            continue

        words = [
            {
                "start": float(word.start),
                "end": float(word.end),
                "text": word.word.strip(),
            }
            for word in (segment.words or [])
            if (
                word.word.strip()
                and word.end > word.start
            )
        ]

        transcript.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
                "words": words,
            }
        )

    return transcript


def speech_units(transcript):
    """Group words into sentences or phrases separated by pauses."""
    units = []
    current = []

    def finish():
        if current:
            units.append(
                {
                    "start": current[0]["start"],
                    "end": current[-1]["end"],
                    "text": " ".join(
                        word["text"] for word in current
                    ),
                }
            )

    for part in transcript:
        if not part["words"]:
            finish()
            current = []
            units.append(
                {
                    "start": part["start"],
                    "end": part["end"],
                    "text": part["text"],
                }
            )
            continue

        for word in part["words"]:
            if (
                current
                and word["start"] - current[-1]["end"] >= 0.65
            ):
                finish()
                current = []

            current.append(word)

            if re.search(r"""[.!?]["'”]*$""", word["text"]):
                finish()
                current = []

    finish()

    return sorted(units, key=lambda unit: unit["start"])


def detect_visual_cuts(video_path, duration):
    """
    Detect significant picture changes.

    These are shot-change clues, not guaranteed story boundaries.
    """
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "info",
            "-i", str(video_path),
            "-an",
            "-vf",
            (
                "scale=320:-2,"
                f"select='gt(scene,{SCENE_THRESHOLD})',"
                "showinfo"
            ),
            "-f", "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise HTTPException(
            500,
            "Could not analyze visual cuts: "
            + result.stderr[-500:],
        )

    cuts = []

    for line in result.stderr.splitlines():
        if "showinfo" not in line:
            continue

        match = re.search(
            r"\bpts_time:([0-9.eE+-]+)",
            line,
        )

        if match:
            second = float(match.group(1))

            if 0 < second < duration:
                cuts.append(second)

    return sorted(set(cuts))


def starts_as_continuation(text):
    """
    Protect likely replies and sentences referring to earlier context.
    """
    return bool(
        re.match(
            r"^\s*(?:"
            r"yes|no|yeah|okay|ok|well|but|and|so|because|"
            r"then|also|however|that|this|it|he|she|they|"
            r"his|her|their"
            r")\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def dialogue_blocks(units, cuts):
    """
    Keep nearby sentences and likely questions/replies together.

    A picture cut alone does not split connected dialogue.
    """
    if not units:
        return []

    embeddings = search_model.encode(
        [unit["text"] for unit in units],
        normalize_embeddings=True,
    )

    blocks = []
    first = 0

    for index in range(1, len(units)):
        previous = units[index - 1]
        current = units[index]

        pause = max(
            0.0,
            current["start"] - previous["end"],
        )

        similarity = float(
            embeddings[index - 1] @ embeddings[index]
        )

        nearby_cut = any(
            previous["end"] - 0.2
            <= cut
            <= current["start"] + 0.2
            for cut in cuts
        )

        follows_question = bool(
            re.search(
                r"""\?["'”]*$""",
                previous["text"].strip(),
            )
        )

        continuation = (
            follows_question
            or starts_as_continuation(current["text"])
        )

        # Preserve likely replies across short pauses.
        split_at_pause = (
            pause >= DIALOGUE_PAUSE
            and not (
                continuation
                and pause < 4.0
            )
        )

        # A cut, a pause, and a topic change together are
        # stronger evidence than a camera cut by itself.
        split_at_transition = (
            nearby_cut
            and pause >= 0.4
            and similarity < 0.25
            and not continuation
        )

        if split_at_pause or split_at_transition:
            blocks.append(
                {
                    "start": units[first]["start"],
                    "end": previous["end"],
                }
            )
            first = index

    blocks.append(
        {
            "start": units[first]["start"],
            "end": units[-1]["end"],
        }
    )

    return blocks


def natural_boundaries(duration, blocks, cuts):
    """
    Build boundaries that do not interrupt protected dialogue.
    """
    boundaries = {0.0, float(duration)}

    for index, block in enumerate(blocks):
        previous_end = (
            blocks[index - 1]["end"]
            if index > 0
            else 0.0
        )

        next_start = (
            blocks[index + 1]["start"]
            if index + 1 < len(blocks)
            else duration
        )

        boundaries.add(
            max(
                previous_end,
                block["start"] - 0.4,
                0.0,
            )
        )

        boundaries.add(
            min(
                next_start,
                block["end"] + 0.4,
                duration,
            )
        )

    for cut in cuts:
        interrupts_dialogue = any(
            block["start"] - 0.2
            < cut
            < block["end"] + 0.2
            for block in blocks
        )

        if not interrupts_dialogue:
            boundaries.add(float(cut))

    return sorted(boundaries)


def context_window(candidate, duration, target, boundaries):
    """
    Include setup before a match and room for its outcome afterward.

    Snap outward to natural boundaries rather than cutting
    strictly at the requested number of seconds.
    """
    anchor = float(candidate["second"])
    match_end = float(candidate.get("end", anchor))

    setup = min(
        10.0,
        max(5.0, target * 0.3),
    )

    desired_start = max(
        0.0,
        anchor - setup,
    )

    desired_end = min(
        duration,
        max(
            match_end + 4.0,
            desired_start + target,
        ),
    )

    start = max(
        (
            boundary
            for boundary in boundaries
            if boundary <= desired_start
        ),
        default=0.0,
    )

    end = min(
        (
            boundary
            for boundary in boundaries
            if boundary >= desired_end
        ),
        default=duration,
    )

    return start, end


def find_speech_candidates(search, units):
    if not units:
        return []

    embeddings = search_model.encode(
        [unit["text"] for unit in units],
        normalize_embeddings=True,
    )

    query = search_model.encode(
        search,
        normalize_embeddings=True,
    )

    scores = embeddings @ query

    return [
        {
            "second": unit["start"],
            "end": unit["end"],
            "match": unit["text"],
            "score": float(scores[index]),
            "kind": "speech",
        }
        for index, unit in enumerate(units)
    ]


def find_visual_candidates(video_path, work_dir, search):
    frames_dir = work_dir / "frames"
    frames_dir.mkdir()

    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", str(video_path),
            "-vf",
            f"fps=1/{FRAME_INTERVAL},scale=512:-2",
            str(frames_dir / "frame_%06d.jpg"),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise HTTPException(
            500,
            "Could not extract frames: "
            + result.stderr[-500:],
        )

    paths = sorted(
        frames_dir.glob("frame_*.jpg")
    )

    if not paths:
        return []

    query = visual_model.encode(
        search,
        normalize_embeddings=True,
    )

    scores = []

    for batch_start in range(0, len(paths), 32):
        images = []

        try:
            for path in paths[batch_start:batch_start + 32]:
                with Image.open(path) as image:
                    images.append(image.convert("RGB"))

            embeddings = visual_model.encode(
                images,
                normalize_embeddings=True,
            )

            scores.extend(
                float(score)
                for score in embeddings @ query
            )

        finally:
            for image in images:
                image.close()

    return [
        {
            "second": index * FRAME_INTERVAL,
            "match": (
                "Visual similarity match near "
                f"{index * FRAME_INTERVAL:.0f} seconds"
            ),
            "score": score,
            "kind": "visual",
        }
        for index, score in enumerate(scores)
    ]


def choose_clips(
    speech_candidates,
    visual_candidates,
    mode,
    duration,
    target,
    boundaries,
):
    speech_ranked = sorted(
        speech_candidates,
        key=lambda item: item["score"],
        reverse=True,
    )

    visual_ranked = sorted(
        visual_candidates,
        key=lambda item: item["score"],
        reverse=True,
    )

    chosen = []

    def add_candidates(candidates, limit):
        added = 0

        for candidate in candidates:
            if len(chosen) >= 4 or added >= limit:
                break

            start, end = context_window(
                candidate,
                duration,
                target,
                boundaries,
            )

            if end <= start:
                continue

            overlaps = any(
                start < previous["end"]
                and end > previous["start"]
                for previous in chosen
            )

            if overlaps:
                continue

            chosen.append(
                {
                    **candidate,
                    "start": start,
                    "end": end,
                }
            )

            added += 1

    if mode == "speech":
        add_candidates(speech_ranked, 4)

    elif mode == "visual":
        add_candidates(visual_ranked, 4)

    else:
        # Aim for two spoken and two visual clips.
        add_candidates(speech_ranked, 2)
        add_candidates(visual_ranked, 2)

        # Fill remaining slots if one type has too few
        # separate usable moments.
        add_candidates(speech_ranked, 4 - len(chosen))
        add_candidates(visual_ranked, 4 - len(chosen))

    return chosen


def caption_chunks(transcript):
    chunks = []

    for part in transcript:
        words = part["words"]

        if not words:
            chunks.append(
                {
                    "start": part["start"],
                    "end": part["end"],
                    "text": part["text"],
                }
            )
            continue

        current = []

        def finish():
            if current:
                chunks.append(
                    {
                        "start": current[0]["start"],
                        "end": current[-1]["end"],
                        "text": " ".join(
                            word["text"]
                            for word in current
                        ),
                    }
                )

        for word in words:
            if current:
                pause = (
                    word["start"]
                    - current[-1]["end"]
                )

                proposed = " ".join(
                    [item["text"] for item in current]
                    + [word["text"]]
                )

                if (
                    pause > 0.35
                    or len(current) >= 7
                    or len(proposed) > 48
                ):
                    finish()
                    current = []

            current.append(word)

            if re.search(
                r"""[.!?,;:]["'”]*$""",
                word["text"],
            ):
                finish()
                current = []

        finish()

    return chunks


def caption_font():
    override = os.environ.get("CASCADE_CAPTION_FONT")

    if override:
        return override

    for path in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(path).is_file():
            return path

    return None


def explain_clip(search, moment, units):
    contained = [
        unit
        for unit in units
        if (
            unit["start"] >= moment["start"]
            and unit["end"] <= moment["end"]
        )
    ]

    if moment["kind"] == "speech":
        reason = (
            "I chose this clip because the dialogue "
            f'"{moment["match"]}" ranked as a spoken match '
            f'to your request: "{search}".'
        )

    else:
        reason = (
            "I chose this clip because sampled frames "
            "within this section ranked as visual matches "
            f'to your request: "{search}".'
        )

        if contained:
            embeddings = search_model.encode(
                [unit["text"] for unit in contained],
                normalize_embeddings=True,
            )

            query = search_model.encode(
                search,
                normalize_embeddings=True,
            )

            index = int(
                (embeddings @ query).argmax()
            )

            reason += (
                " The most related dialogue within this "
                f'clip is: "{contained[index]["text"]}".'
            )

    return (
        reason
        + " The boundaries were expanded to include setup "
        "and follow nearby dialogue or visual boundary clues."
    )


def render_clip(full_video, moment, chunks, output_path):
    start = moment["start"]
    end = min(moment["end"], full_video.duration)

    sub_video = full_video.subclipped(start, end)

    captions = []
    finished = None

    try:
        font_size = max(
            14,
            round(
                min(
                    sub_video.w * 0.045,
                    sub_video.h * 0.06,
                )
            ),
        )

        for chunk in chunks:
            caption_start = max(start, chunk["start"])
            caption_end = min(end, chunk["end"])

            if caption_end <= caption_start:
                continue

            text = "\n".join(
                textwrap.wrap(
                    chunk["text"],
                    width=30,
                )
            )

            caption = TextClip(
                text=text,
                font=caption_font(),
                font_size=font_size,
                color="white",
                bg_color="black",
                margin=(12, 8),
                method="label",
                text_align="center",
            )

            maximum_width = max(
                1,
                int(sub_video.w * 0.88),
            )

            if caption.w > maximum_width:
                caption = caption.resized(
                    width=maximum_width
                )

            y = max(
                0,
                int(sub_video.h * 0.93) - caption.h,
            )

            caption = (
                caption
                .with_position(("center", y))
                .with_start(caption_start - start)
                .with_duration(caption_end - caption_start)
            )

            captions.append(caption)

        finished = CompositeVideoClip(
            [sub_video, *captions]
        ).with_audio(sub_video.audio)

        finished.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
        )

    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    finally:
        if finished is not None:
            finished.close()

        for caption in captions:
            caption.close()

        sub_video.close()


@router.post("/upload")
def upload_video(
    video: UploadFile = File(...),
    search: str = Form(...),
    mode: str = Form("speech"),
    clip_length: int = Form(30),
):
    search = search.strip()

    if not search:
        raise HTTPException(
            400,
            "Type what you want to find.",
        )

    if mode not in ("speech", "visual", "both"):
        raise HTTPException(
            400,
            "Choose speech, visual, or both.",
        )

    if clip_length not in (15, 30, 60):
        raise HTTPException(
            400,
            "Choose 15, 30, or 60 seconds.",
        )

    if (
        shutil.which("ffmpeg") is None
        or shutil.which("ffprobe") is None
    ):
        raise HTTPException(
            500,
            "FFmpeg and ffprobe must be installed.",
        )

    with TemporaryDirectory() as folder:
        work_dir = Path(folder)

        suffix = (
            Path(video.filename or "video.mp4").suffix
            or ".mp4"
        )

        video_path = work_dir / f"uploaded{suffix}"

        with video_path.open("wb") as destination:
            shutil.copyfileobj(video.file, destination)

        try:
            duration = get_duration(video_path)
        except (
            subprocess.CalledProcessError,
            ValueError,
            KeyError,
        ):
            raise HTTPException(
                400,
                "Could not read this video.",
            )

        transcript = transcribe_video(video_path)
        units = speech_units(transcript)
        chunks = caption_chunks(transcript)

        if mode == "speech" and not units:
            raise HTTPException(
                400,
                "No speech was found in the video.",
            )

        cuts = detect_visual_cuts(
            video_path,
            duration,
        )

        blocks = dialogue_blocks(units, cuts)

        boundaries = natural_boundaries(
            duration,
            blocks,
            cuts,
        )

        speech_candidates = []
        visual_candidates = []

        if mode in ("speech", "both"):
            speech_candidates = find_speech_candidates(
                search,
                units,
            )

        if mode in ("visual", "both"):
            visual_candidates = find_visual_candidates(
                video_path,
                work_dir,
                search,
            )

        chosen = choose_clips(
            speech_candidates,
            visual_candidates,
            mode,
            duration,
            clip_length,
            boundaries,
        )

        if not chosen:
            raise HTTPException(
                400,
                "No usable clips were found.",
            )

        clips = []
        created_paths = []

        try:
            with VideoFileClip(str(video_path)) as full_video:
                if full_video.audio is None:
                    raise HTTPException(
                        400,
                        "The video has no audio track.",
                    )

                for number, moment in enumerate(
                    chosen,
                    start=1,
                ):
                    moment["end"] = min(
                        moment["end"],
                        full_video.duration,
                    )

                    explanation = explain_clip(
                        search,
                        moment,
                        units,
                    )

                    style_name = STYLE_NAMES[number - 1]

                    filename = (
                        f"{uuid4().hex}_{style_name}.mp4"
                    )

                    output_path = OUTPUTS / filename

                    render_clip(
                        full_video,
                        moment,
                        chunks,
                        output_path,
                    )

                    created_paths.append(output_path)

                    clips.append(
                        {
                            "clip_url": f"/api/search/clips/{filename}",
                            "title": f"Clip {number}",
                            "start": round(moment["start"], 1),
                            "end": round(moment["end"], 1),
                            "match": moment["match"],
                            "match_kind": moment["kind"],
                            "style": style_name,
                            "subtitle_style": "black_and_white",
                            "explanation": explanation,
                        }
                    )

        except Exception:
            for path in created_paths:
                path.unlink(missing_ok=True)
            raise

    return {
        "clips": clips,
        "mode": mode,
        "note": (
            "Clip lengths may increase to preserve connected "
            "dialogue and nearby visual context. Fewer than four "
            "clips may be returned when complete sections overlap."
        ),
    }