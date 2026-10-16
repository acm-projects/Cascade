"""Opt-in offline visual search using cached models and a local input video.
Run: python tests/live_search_smoke.py path/to/video.mp4 [visual|speech]
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
mode = sys.argv[2] if len(sys.argv) > 2 else 'visual'
def progress(message):
    print(f'{time.monotonic() - start:.1f}s: {message}', flush=True)

with tempfile.TemporaryDirectory() as directory, patch.object(router, 'OUTPUTS', Path(directory)):
    with source.open('rb') as file:
        result = router.search_video(UploadFile(file, filename='source.mp4'), 'a person speaking', mode, 30, progress)
    lengths = []
    for clip in result['clips']:
        output = Path(directory) / Path(clip['clip_url']).name
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                                  '-of', 'json', str(output)], timeout=30))
        length = float(probe['format']['duration'])
        assert 0 < length <= 30.2
        assert any(stream['codec_type'] == 'audio' for stream in probe['streams'])
        assert clip['captions_vtt'].startswith('WEBVTT')
        lengths.append(length)
    print(json.dumps({'state': 'done', 'mode': mode, 'elapsed_seconds': round(time.monotonic() - start, 1),
                      'clips': len(result['clips']), 'clip_seconds': lengths, 'timings': result['timings']}), flush=True)
