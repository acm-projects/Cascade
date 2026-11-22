"""The one place Cascade finds FFmpeg (set CASCADE_FFMPEG to choose a build), including one that can burn captions."""
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
import subprocess
from fastapi import HTTPException


@lru_cache(maxsize=8)
def _subtitle_binary(configured, binary):
    # Homebrew's minimal build can coexist with an already-installed full build.
    candidates = [configured] if configured else [binary, str(Path(binary).parent.parent / 'opt/ffmpeg-full/bin/ffmpeg')]
    for candidate in dict.fromkeys(candidates):
        try:
            result = subprocess.run([candidate, '-hide_banner', '-filters'], capture_output=True, text=True, check=True, timeout=15)
            if re.search(r'\bsubtitles\s+V->V', result.stdout):
                return candidate
        except (OSError, subprocess.SubprocessError):
            continue
    raise HTTPException(503, 'Caption rendering needs FFmpeg with libass/subtitles support. Set CASCADE_FFMPEG to a compatible binary and restart; the default installed build may omit subtitles.')


def ffmpeg():
    """The FFmpeg to use: CASCADE_FFMPEG when set, else the one on PATH."""
    return os.getenv('CASCADE_FFMPEG', '').strip() or shutil.which('ffmpeg') or 'ffmpeg'


def subtitle_ffmpeg():
    """An FFmpeg with libass (captions): CASCADE_FFMPEG when set, else the one on PATH or Homebrew's full build."""
    return _subtitle_binary(os.getenv('CASCADE_FFMPEG', '').strip(), shutil.which('ffmpeg') or 'ffmpeg')
