from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Optional

# Import the NEW 4-clip generation function
from render_subtitles import generate_four_styled_clips

app = FastAPI(title="Cascade AI Clip Engine")

# In-memory database for job status
jobs_db = {}

class VideoJobRequest(BaseModel):
    video_url: str = "sample.mp4"
    tone: Optional[str] = "engaging"
    audience: Optional[str] = "gen-z"
    preferred_styles: Optional[List[str]] = ["hormozi", "minimalist", "bold_viral", "cinematic"]

def process_video_background(job_id: str, request: VideoJobRequest):
    """Background task worker that generates the 4 styled clips."""
    try:
        print(f"--- Starting background generation for {job_id} ---")
        
        # Call the 4-clip renderer from render_subtitles.py
        clip_files = generate_four_styled_clips(
            video_url=request.video_url,
            styles=request.preferred_styles,
            tone=request.tone,
            audience=request.audience
        )
        
        # Update status to COMPLETED and attach file names
        jobs_db[job_id]["status"] = "COMPLETED"
        jobs_db[job_id]["clips"] = clip_files
        print(f"--- Finished job {job_id} successfully! ---")
        
    except Exception as e:
        jobs_db[job_id]["status"] = "FAILED"
        jobs_db[job_id]["error"] = str(e)
        print(f"--- Error on job {job_id}: {e} ---")

@app.post("/api/v1/process-video")
async def create_processing_job(request: VideoJobRequest, background_tasks: BackgroundTasks):
    job_id = f"job_{len(jobs_db) + 1}"
    jobs_db[job_id] = {"status": "PROCESSING", "clips": [], "error": None}
    
    # Hand off execution to FastAPI background worker
    background_tasks.add_task(process_video_background, job_id, request)
    
    return {
        "status": "success",
        "job_id": job_id,
        "message": "Video queued for 4-clip generation."
    }

@app.get("/api/v1/job/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs_db[job_id]