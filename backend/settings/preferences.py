"""Teammate preference fields with optional isolated storage for the integrated app."""
import json
from pathlib import Path
from uuid import uuid4

PREFS_FILE = str(Path(__file__).resolve().parent / "preferences.json")
DEFAULTS = {"video_type": "", "audience": "", "tone": "", "goal": "", "platforms": []}


def load_preferences(file_path=None):
    path = Path(file_path or PREFS_FILE)
    if not path.is_file():
        return {**DEFAULTS, "platforms": []}
    return {**DEFAULTS, **json.loads(path.read_text(encoding="utf-8"))}
