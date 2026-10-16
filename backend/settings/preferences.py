"""Teammate preference fields with optional isolated storage for the integrated app."""
import json
from pathlib import Path
from uuid import uuid4

PREFS_FILE = str(Path(__file__).resolve().parent / "preferences.json")
DEFAULTS = {"video_type": "", "audience": "", "tone": "", "goal": "", "platforms": []}


def save_preferences(data, file_path=None):
    path = Path(file_path or PREFS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_preferences(file_path=None):
    path = Path(file_path or PREFS_FILE)
    if not path.is_file():
        return {**DEFAULTS, "platforms": []}
    return {**DEFAULTS, **json.loads(path.read_text(encoding="utf-8"))}
