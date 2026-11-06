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


def whisper():
    binary = shutil.which('whisper-cli') or ('/opt/homebrew/bin/whisper-cli' if Path('/opt/homebrew/bin/whisper-cli').exists() else '')
    models = folder()/'Tools'/'whisper-models'
    model = next((m for m in (models/'ggml-large-v3-turbo-q5_0.bin', models/'ggml-base.en.bin') if m.is_file()), None)
    return (binary, str(model)) if binary and model else None


def demucs():
    python = folder()/'Tools'/'demucs-venv'/'bin'/'python'
    return str(python) if python.is_file() else None


def style_sheet():
    """The owner's live rules when the editing folder is on this machine, else the copy kept with Cascade."""
    live = folder()/'CLAUDE.md'
    return (live if live.is_file() else HERE/'style_sheet.md').read_text()
