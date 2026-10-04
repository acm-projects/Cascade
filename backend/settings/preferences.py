import json
import os
from pathlib import Path

PREFS_FILE = str(Path(__file__).resolve().parent / "preferences.json")

def save_preferences(data):
    with open(PREFS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_preferences():
    if not os.path.exists(PREFS_FILE):
        return {
            "video_type": "",
            "audience": "",
            "tone": "",
            "goal": "",
            "platforms": []
        }
    with open(PREFS_FILE) as f:
        return json.load(f)