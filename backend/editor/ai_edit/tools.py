"""Where the free local editing tools live. All optional except FFmpeg and HyperFrames."""
import os
import shutil
from pathlib import Path

HERE = Path(__file__).parent
HYPERFRAMES = 'hyperframes@0.9.13'


def folder():
    return Path(os.getenv('CASCADE_EDITING_FOLDER') or Path.home()/'Desktop'/'AI video editor')


def ffmpeg():
    from ..render import export_binary
    return export_binary(True)  # the build with drawtext/libass


def demucs():
    python = folder()/'Tools'/'demucs-venv'/'bin'/'python'
    return str(python) if python.is_file() else None


def style_sheet():
    """The owner's live rules when the editing folder is on this machine, else the copy kept with Cascade."""
    return (HERE/'style_sheet.md').read_text()


def look():
    """The visual look the active style sheet asks for: a "Look: scrapbook" line switches the renderer to it."""
    import re
    match = re.search(r'^\s*Look:\s*([a-z-]+)', style_sheet(), re.M | re.I)
    return match.group(1).lower() if match else 'point'


def cinema():
    """The Cinema engine (cinema/) makes AI edits unless CASCADE_EDIT_ENGINE=legacy asks for the older HyperFrames looks."""
    return os.getenv('CASCADE_EDIT_ENGINE', 'cinema').strip().lower() != 'legacy'
