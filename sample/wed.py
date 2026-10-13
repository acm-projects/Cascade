from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from cascade_clips import generate_four_styled_clips

app = FastAPI()


class ClipRequest(BaseModel):
    video_path: str = "sample.mp4"
    query: str = Field(min_length=1)
    target_length: float = Field(default=20.0, gt=0, le=120)


@app.post("/generate-clips")
def handle_clip_request(request: ClipRequest):
    if not Path(request.video_path).is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    try:
        clips = generate_four_styled_clips(
            video_path=request.video_path,
            query=request.query,
            clip_duration=request.target_length,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", "clips": clips}