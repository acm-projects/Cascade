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

# app.py and index.html are both inside test1.
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


@app.post("/upload") #this creates the address inside fastAPI app
async def upload_video(
    video: UploadFile = File(...),
    search: str = Form(...),
    mode: str = Form("speech"),
):
    if not search.strip():
        raise HTTPException(status_code=400, detail="Type what you want to find.")

    if mode not in ("speech", "visual"):
        raise HTTPException(
            status_code=400,
            detail="Mode must be speech or visual.",
        )

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

            # CLIP compares the meaning of your search with each picture.
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

        filename = f"{uuid4().hex}.mp4"
        output_path = OUTPUTS / filename

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss", str(clip_start),
                    "-i", str(video_path),
                    "-t", str(clip_end - clip_start),
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-movflags", "+faststart",
                    str(output_path),
                ],
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