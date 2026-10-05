from pathlib import Path
from uuid import uuid4
import shutil
import traceback

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from render_subtitles import generate_four_styled_clips

app = FastAPI()

BASE = Path(__file__).parent
UPLOADS = BASE / "uploads"
OUTPUTS = BASE / "outputs"


@app.get("/")
def homepage():
    return FileResponse(BASE / "sample" / "front.html")


@app.post("/generate-clips")
def generate_clips(
    video: UploadFile = File(...),
    query: str = Form(...),
):
    if not video.filename or not video.filename.lower().endswith(".mp4"):
        raise HTTPException(400, "Please choose an MP4 video.")
    if not query.strip():
        raise HTTPException(400, "Enter a search phrase.")

    job_id = uuid4().hex
    UPLOADS.mkdir(exist_ok=True)
    job_output = OUTPUTS / job_id
    video_path = UPLOADS / f"{job_id}.mp4"

    with video_path.open("wb") as saved:
        shutil.copyfileobj(video.file, saved)

    try:
        clip_paths = generate_four_styled_clips(
            video_path=str(video_path),
            query=query,
            output_dir=str(job_output),
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(500, f"Could not generate clips: {exc}") from exc

    return {
        "clips": [
            f"/clips/{job_id}/{Path(path).name}"
            for path in clip_paths
        ]
    }


@app.get("/clips/{job_id}/{filename}")
def watch_clip(job_id: str, filename: str):
    clip = OUTPUTS / job_id / filename
    if not clip.is_file():
        raise HTTPException(404, "Clip not found")
    return FileResponse(clip, media_type="video/mp4")