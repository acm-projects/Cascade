"""Opt-in offline visual search using cached models and a local input video.
Run: python tests/live_search_smoke.py path/to/video.mp4
No downloads, S3, paid APIs, or changes to the input video.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
start = time.monotonic()
from starlette.datastructures import UploadFile
from backend.video_search import router

source = Path(sys.argv[1]).resolve()
def progress(message):
    print(f'{time.monotonic() - start:.1f}s: {message}', flush=True)

with tempfile.TemporaryDirectory() as directory, patch.object(router, 'OUTPUTS', Path(directory)):
    with source.open('rb') as file:
        result = router.search_video(UploadFile(file, filename='source.mp4'), 'a person speaking', 'visual', 30, progress)
    output = Path(directory) / Path(result['clip_url']).name
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                              '-of', 'json', str(output)], timeout=30))
    assert 0 < float(probe['format']['duration']) <= 30.2
    assert result['captions_vtt'].startswith('WEBVTT')
    print(json.dumps({'state': 'done', 'elapsed_seconds': round(time.monotonic() - start, 1),
                      'clip_seconds': float(probe['format']['duration']), 'timings': result['timings']}), flush=True)
