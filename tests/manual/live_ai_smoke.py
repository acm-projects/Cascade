"""Opt-in live local Ollama test; synthetic silent video, no paid APIs or S3.
Run: python tests/manual/live_ai_smoke.py
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import app1
original = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    job_id = 'a' * 32
    folder = root / job_id
    folder.mkdir()
    source = folder / 'source.video'
    if original:
        shutil.copyfile(original, source)
        transcript = original.parent / 'transcript.json'
        if transcript.is_file():
            shutil.copyfile(transcript, folder / 'transcript.json')
    else:
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=320x240:r=10:d=4',
                        '-c:v', 'libx264', '-f', 'mp4', str(source)], check=True, timeout=30)
    (folder / 'owner.json').write_text(json.dumps({'user_id': 'local-smoke', 'user_folder': 'users'}))
    app1.jobs[job_id] = {'state': 'queued', 'message': 'Waiting', 'clips': []}
    start = time.monotonic()
    with patch.object(app1, 'JOBS_DIR', root), patch.dict(os.environ, {'CASCADE_STORAGE': 'local'}):
        search = json.loads((original.parent / 'owner.json').read_text()).get('prompt', 'Find an interesting scene') if original else 'Find the blue screen'
        app1.process_upload(job_id, source, search, 'both' if original else 'visual', 30 if original else 15)
    result = app1.jobs.pop(job_id)
    print(json.dumps({'elapsed_seconds': round(time.monotonic() - start, 1),
                      'state': result['state'], 'message': result['message'], 'clips': len(result['clips'])}))
    assert result['state'] == 'done', result['message']
    assert result['clips'], 'Model did not select the synthetic blue screen'
    output = folder / 'clip_1.mp4'
    assert output.is_file()
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(output)], timeout=30))
    assert float(probe['format']['duration']) > 0
    print('PASS: live Ollama selection and FFprobe-verified clip render; local storage.')
