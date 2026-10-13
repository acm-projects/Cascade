"""Settings/preferences feature: a simple form for video-generation preferences.

Ported from a standalone Flask app to a FastAPI APIRouter so it can share one
process with the rest of Cascade's features. Same behavior, same template.

Mounted by backend/app.py with no extra prefix (keeps the original /settings path).
"""

from pathlib import Path
from typing import List

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .preferences import save_preferences, load_preferences

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    current = load_preferences()
    return templates.TemplateResponse("settings.html", {"request": request, "prefs": current})


@router.post("/settings", response_class=HTMLResponse)
async def post_settings(
    request: Request,
    video_type: str = Form(""),
    audience: str = Form(""),
    tone: str = Form(""),
    goal: str = Form(""),
    platforms: List[str] = Form([]),
):
    # Pull the values entered/selected by the user in the HTML form
    data = {
        "video_type": video_type,
        "audience": audience,
        "tone": tone,
        "goal": goal,
        # Form(...) with a list type already collects all checked "platforms" values
        "platforms": platforms,
    }
    # Save the dictionary to preferences.json
    save_preferences(data)

    # Load whatever is currently saved in preferences.json and send it to the page
    current = load_preferences()
    return templates.TemplateResponse("settings.html", {"request": request, "prefs": current})
