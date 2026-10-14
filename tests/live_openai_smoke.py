"""Opt-in PAID OpenAI smoke test on an existing local source.
python tests/live_openai_smoke.py video_jobs/<id>/source.video [--keep]
One scene-selection request normally; a transient service error may retry once.
--keep saves a new owned job in the source project; outputs use local storage.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app1

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--keep', action='store_true')
args = parser.parse_args()
source = args.source.resolve()
temporary = None if args.keep else tempfile.TemporaryDirectory()
root = app1.JOBS_DIR if args.keep else Path(temporary.name)
job_id = uuid4().hex
folder = root / job_id
folder.mkdir()
try:
    owner = json.loads((source.parent / 'owner.json').read_text())
except FileNotFoundError:
    if args.keep:
        raise SystemExit('--keep requires an existing owned source upload.')
    owner = {'user_id': 'local-smoke', 'user_folder': 'users'}
search = 'Find four distinct funny moments. Include each joke or mishap setup and its payoff or reaction.'
app1.save_json(folder / 'owner.json', {**owner, 'prompt': search, 'source_name': source.name})
shutil.copyfile(source, folder / 'source.video')
transcript = source.parent / 'transcript.json'
if transcript.is_file():
    shutil.copyfile(transcript, folder / 'transcript.json')
app1.jobs[job_id] = {'state': 'queued', 'message': 'Waiting', 'clips': []}
start = time.monotonic()
with patch.object(app1, 'JOBS_DIR', root), patch.dict(os.environ, {'CASCADE_STORAGE': 'local'}):
    app1.process_openai_upload(job_id, folder / 'source.video', search, 'both', 30)
result = app1.jobs.pop(job_id)
print(json.dumps({'job_id': job_id, 'state': result['state'], 'message': result['message'],
                  'elapsed_seconds': round(time.monotonic() - start, 1), 'clips': len(result['clips']),
                  'timings': result.get('timings'), 'usage': result.get('usage'),
                  'selection_note': result.get('selection_note')}), flush=True)
assert result['state'] == 'done', result['message']
assert result['clips'], 'No supported funny moments were selected; inspect selection metadata.'
for clip in result['clips']:
    output = folder / Path(clip['clip_url']).name
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                              '-of', 'json', str(output)], timeout=30))
    assert float(probe['format']['duration']) > 0
print('PASS: live OpenAI selection and FFprobe-verified local renders.', flush=True)
if args.keep:
    print('Saved outputs:', folder, flush=True)
if temporary:
    temporary.cleanup()
