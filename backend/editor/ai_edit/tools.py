"""Where the free local editing tools live. All optional except FFmpeg."""
import os
from pathlib import Path


def folder():
    return Path(os.getenv('CASCADE_EDITING_FOLDER') or Path.home()/'Desktop'/'AI video editor')


def ffmpeg():
    from ..render import export_binary
    return export_binary(True)  # the build with drawtext/libass

