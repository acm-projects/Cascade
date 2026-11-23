"""Cascade application composition root."""
import os
import threading

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend import studio
from backend.core import auth, jobs
from backend.core.config import FRONTEND_DIR
from backend.routers import clips, pages, projects, settings, features, generations
from backend.routers.editor_setup import include_editor
from backend.core.media_links import media_link
from backend.core import job_queue
from backend.services import source_backup
from backend.services.clip_backup import resume_pending

app = FastAPI()
app.middleware("http")(auth.authenticate_request)
app.include_router(pages.router)
app.include_router(clips.router)


def warm_models():
    """Load the CLIP and MiniLM search models in the background so the first upload does not pay for it."""
    try:
        from backend.video_search import router as video_search
        video_search.load_models("visual")
        video_search.load_models("speech")
        print("Search models loaded.", flush=True)
    except Exception as error:  # a failed warm-up only means the first upload loads them itself
        print(f"Search model warm-up failed: {error}", flush=True)


def start_model_warmup():
    auth.warn_dev_auth()
    # Off by default: the models (and PyTorch) hold about 400 MB of RAM, and they load on the first upload or
    # search anyway (about 5 s). CASCADE_WARM_MODELS=1 loads them at startup instead.
    if os.getenv("CASCADE_WARM_MODELS", "0") == "1":
        threading.Thread(target=warm_models, name="model-warmup", daemon=True).start()


app.on_event("startup")(start_model_warmup)
app.on_event("startup")(jobs.initialize_metadata)
app.on_event("startup")(job_queue.resume)   # generation jobs a restart cut off run again
app.on_event("startup")(resume_pending)
app.on_event("startup")(source_backup.resume_pending)   # retry source backups a restart cut off
app.include_router(projects.router)
app.include_router(settings.router)
app.include_router(features.router)
include_editor(app)
app.add_api_route('/api/media-link', media_link, methods=['GET'])
app.include_router(generations.router)
app.include_router(studio.router)
app.mount('/studio-assets', StaticFiles(directory=FRONTEND_DIR / 'studio', check_dir=False), name='studio-assets')
