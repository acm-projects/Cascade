"""Unified Cascade backend: mounts every feature's router on one FastAPI app.

Run from inside backend/:
    uvicorn app:app --reload --port 8000

Feature routers (each owns its own job-dict / processing logic unchanged):
  /api/trends/...   - trend-analysis: compare an uploaded video against trending YouTube videos
  /api/v1/...       - clip-generation: burn in 4 styled caption treatments
  /api/search/...   - video-search: find the best-matching moment via speech/visual search
  /settings         - preferences form (video type, audience, tone, goal, platforms)

Quick-look static pages for manually exercising a feature without the final
frontend (not the production UI):
  /trends-ui  -> trends feature's standalone page
  /search-ui  -> video-search feature's standalone page
  /app-ui     -> combined page with tabs for trends + video-search together
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from trends.router import router as trends_router
from clips.router import router as clips_router
from video_search.router import router as video_search_router
from settings.router import router as settings_router

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:8000")

app = FastAPI(title="Cascade")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(trends_router, prefix="/api/trends", tags=["trends"])
app.include_router(clips_router, prefix="/api/v1", tags=["clips"])
app.include_router(video_search_router, prefix="/api/search", tags=["video-search"])
app.include_router(settings_router, tags=["settings"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Quick-look static pages for each feature (not the final React frontend).
app.mount(
    "/trends-ui",
    StaticFiles(directory=str(BACKEND_DIR / "trends" / "static"), html=True),
    name="trends-ui",
)
app.mount(
    "/search-ui",
    StaticFiles(directory=str(BACKEND_DIR / "video_search" / "static"), html=True),
    name="search-ui",
)
app.mount(
    "/app-ui",
    StaticFiles(directory=str(BACKEND_DIR / "static"), html=True),
    name="app-ui",
)
