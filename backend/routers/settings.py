"""Owner-scoped settings endpoints."""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.core import config, jobs as job_service
from backend.services import projects_store
from backend.settings.preferences import load_preferences

router = APIRouter(prefix="/api")


class SettingsInput(BaseModel):
    video_type: Literal["", "tutorial", "vlog", "interview", "podcast"] = ""
    audience: str = Field(default="", max_length=200)
    tone: Literal["", "casual", "professional", "funny", "educational"] = ""
    goal: str = Field(default="", max_length=500)
    platforms: list[Literal["tiktok", "instagram", "linkedin", "youtube"]] = Field(default_factory=list, max_length=4)


@router.get('/settings')
def get_settings(request: Request):
    path = projects_store.project_dir(request.state.user_id) / 'settings' / 'preferences.json'
    with projects_store.lock:
        if job_service.metadata_exists(path):
            return job_service.load_json(path)
        # Retain original global preferences as defaults; never overwrite them.
        legacy = Path(config.PROJECT_DIR) / 'preferences.json'
        return load_preferences(legacy if legacy.is_file() else None)


@router.post('/settings')
def set_settings(body: SettingsInput, request: Request):
    path = projects_store.project_dir(request.state.user_id) / 'settings' / 'preferences.json'
    with projects_store.lock:
        job_service.save_json(path, body.model_dump())
    return {'saved': True, 'preferences': body.model_dump()}
