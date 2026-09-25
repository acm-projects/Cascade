from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import json
import shutil
import subprocess

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from faster_whisper import WhisperModel
from PIL import Image
from sentence_transformers import SentenceTransformer

app = FastAPI()

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUTS = PROJECT_DIR / "outputs"
OUTPUTS.mkdir(exist_ok=True)

whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
search_model = SentenceTransformer("all-MiniLM-L6-v2")
visual_model = SentenceTransformer("sentence-transformers/clip-ViT-B-32")


@app.get("/")
def show_website():
    return FileResponse(PROJECT_DIR / "index.html")


@app.get("/clips/{filename}")
def get_clip(filename: str):
    clip = OUTPUTS / filename

    if clip.suffix != ".mp4" or not clip.is_file():
        raise HTTPException(status_code=404, detail="Clip not found")

    return FileResponse(clip, media_type="video/mp4")


def get_duration(video_path: Path) -> float:
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
    return float(json.loads(result.stdout)["format"]["duration"])


def srt_time(seconds):
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


@app.post("/upload")
async def upload_video(
    video: UploadFile = File(...),
    search: str = Form(...),
    mode: str = Form("speech"),
):
    if not search.strip():
        raise HTTPException(status_code=400, detail="Type what you want to find.")

    if mode not in ("speech", "visual"):
        raise HTTPException(status_code=400, detail="Mode must be speech or visual.")

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise HTTPException(
            status_code=500,
            detail="FFmpeg and ffprobe must be installed.",
        )

    with TemporaryDirectory() as folder:
        work_dir = Path(folder)
        suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
        video_path = work_dir / f"uploaded{suffix}"

        with video_path.open("wb") as destination:
            shutil.copyfileobj(video.file, destination)

        try:
            duration = get_duration(video_path)
        except (subprocess.CalledProcessError, ValueError, KeyError):
            raise HTTPException(
                status_code=400,
                detail="Could not read this video's duration.",
            )

        if mode == "speech":
            segments, _ = whisper_model.transcribe(str(video_path))
            transcript = [
                {"start": s.start, "end": s.end, "text": s.text.strip()}
                for s in segments
                if s.text.strip()
            ]

            if not transcript:
                raise HTTPException(
                    status_code=400,
                    detail="Whisper could not find speech in this video.",
                )

            sentences = [part["text"] for part in transcript]
            embeddings = search_model.encode(sentences)
            query_embedding = search_model.encode(search)
            scores = search_model.similarity(query_embedding, embeddings)

            best_index = scores.argmax().item()
            match = transcript[best_index]

            clip_start = max(0, match["start"] - 3)
            clip_end = min(
                duration,
                max(match["end"] + 3, clip_start + 15),
                clip_start + 30,
            )
            match_text = match["text"]

        else:
            # Take one picture from the video every 3 seconds.
            frames_dir = work_dir / "frames"
            frames_dir.mkdir()

            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i", str(video_path),
                        "-vf", "fps=1/3",
                        "-frames:v", "100",
                        str(frames_dir / "frame_%04d.jpg"),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Could not extract frames: {error.stderr[-500:]}",
                )

            frame_paths = sorted(frames_dir.glob("frame_*.jpg"))
            if not frame_paths:
                raise HTTPException(
                    status_code=400,
                    detail="No pictures could be taken from this video.",
                )

            images = []
            for path in frame_paths:
                with Image.open(path) as image:
                    images.append(image.convert("RGB"))

            # CLIP compares the search with each picture.
            query_embedding = visual_model.encode(
                search, normalize_embeddings=True
            )
            frame_embeddings = visual_model.encode(
                images, normalize_embeddings=True
            )
            scores = frame_embeddings @ query_embedding
            best_index = int(scores.argmax())

            matched_second = best_index * 3
            clip_start = max(0, matched_second - 5)
            clip_end = min(duration, clip_start + 15)
            match_text = f"Best visual match near {matched_second} seconds"

            # Visual search did not need speech, but captions do.
            segments, _ = whisper_model.transcribe(str(video_path))
            transcript = [
                {"start": s.start, "end": s.end, "text": s.text.strip()}
                for s in segments
                if s.text.strip()
            ]

        # Keep only speech inside the selected clip. Adjust timestamps so
        # the captions start at 0 seconds in the new video.
        subtitle_lines = []
        for part in transcript:
            start = max(part["start"], clip_start)
            end = min(part["end"], clip_end)

            if end <= start:
                continue

            subtitle_lines.append(
                f"{len(subtitle_lines) + 1}\n"
                f"{srt_time(start - clip_start)} --> "
                f"{srt_time(end - clip_start)}\n"
                f"{part['text']}\n"
            )

        if subtitle_lines:
            (work_dir / "captions.srt").write_text(
                "\n".join(subtitle_lines),
                encoding="utf-8",
            )

        filename = f"{uuid4().hex}.mp4"
        output_path = OUTPUTS / filename

        command = [
            "ffmpeg",
            "-y",
            "-ss", str(clip_start),
            "-i", str(video_path),
            "-t", str(clip_end - clip_start),
        ]

        # Burn subtitles onto the video if Whisper found speech.
        if subtitle_lines:
            command += ["-vf", "subtitles=filename=captions.srt"]

        command += [
            "-c:v", "libx264",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(output_path),
        ]

        try:
            subprocess.run(
                command,
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise HTTPException(
                status_code=500,
                detail=f"Could not make clip: {error.stderr[-500:]}",
            )

    return {
        "clip_url": f"/clips/{filename}",
        "start": round(clip_start, 1),
        "end": round(clip_end, 1),
        "match": match_text,
        "mode": mode,
    }