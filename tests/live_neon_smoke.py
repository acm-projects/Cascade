"""Opt-in Neon integration test. Uses synthetic records and cleans them up.
Run from root: python tests/live_neon_smoke.py --allow-database-writes
No Clerk, OpenAI, Ollama, S3, or model calls are made.
"""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app1
import integration
from fastapi.testclient import TestClient


def run():
    if sys.argv[1:] != ['--allow-database-writes']:
        raise SystemExit('Pass --allow-database-writes to run this opt-in test.')
    user = 'cascade-smoke-' + uuid4().hex
    headers = {'Authorization': 'Bearer ' + user}
    other = {'Authorization': 'Bearer other-' + user}
    keys = []
    with tempfile.TemporaryDirectory() as tmp, patch.object(app1, 'JOBS_DIR', Path(tmp)), \
            patch.dict(os.environ, {'CASCADE_METADATA_STORE': 'neon'}), \
            patch.object(app1, 'verify_clerk_token', side_effect=lambda token: token):
        store = app1.metadata_store()
        try:
            with TestClient(app1.app) as client:
                assert client.get('/api/health').json()['metadata_storage'] == 'neon'
                response = client.post('/api/projects', headers=headers, json={'name': 'Synthetic Neon persistence test'})
                assert response.status_code == 201, response.status_code
                pid = response.json()['id']
                project_path = integration.project_dir(user) / (pid + '.json')
                keys.append(store.key(project_path))
                settings_path = integration.project_dir(user) / 'settings' / 'preferences.json'
                keys.append(store.key(settings_path))
                assert client.post('/api/settings', headers=headers, json={'tone': 'funny'}).status_code == 200
                jid, folder = integration.new_feature_job({'user_id': user, 'project_id': pid}, 'generation')
                keys.extend(store.key(folder / name) for name in ('owner.json', 'progress.json', 'results.json'))
                integration.finish_feature(jid, {'clips': [{'clip_url': f'/clips/{jid}/clip_1.mp4',
                    'captions_url': f'/clips/{jid}/clip_1.vtt', 'storage': 's3',
                    's3_bucket': 'synthetic-test', 'clip_s3_key': 'synthetic-only'}]})
                for _ in range(2):
                    assert client.post(f'/api/projects/{pid}/saved-clips', headers=headers,
                                       json={'job_id': jid, 'clip_index': 0}).status_code == 200
                # Remove local metadata and clear process memory: reads must come from Neon.
                for path in Path(tmp).rglob('*.json'):
                    path.unlink()
                app1.jobs.pop(jid, None)
                result = client.get(f'/api/projects/{pid}', headers=headers)
                assert result.status_code == 200
                assert len(result.json()['saved_clips']) == 1
                assert result.json()['jobs'][0]['job_id'] == jid
                assert len(client.get('/api/projects', headers=headers).json()['projects']) == 1
                assert client.get('/api/settings', headers=headers).json()['tone'] == 'funny'
                assert client.get(f'/api/features/{jid}', headers=headers).json()['state'] == 'done'
                assert len(client.get('/api/my-clips', headers=headers).json()['clips']) == 1
                assert client.get(f'/api/projects/{pid}', headers=other).status_code == 404
                assert client.get(f'/api/features/{jid}', headers=other).status_code == 404
                assert client.get('/api/projects', headers=other).json()['projects'] == []
                with store.connection() as conn, conn.cursor() as cur:
                    cur.execute('SELECT count(*) FROM cascade_app.clips WHERE job_id = %s', (jid,))
                    assert cur.fetchone()[0] == 1
                print('PASS: Neon project/settings/history/clips survive missing local metadata; ownership enforced.')
        finally:
            if keys:
                with store.connection() as conn, conn.cursor() as cur:
                    cur.execute('DELETE FROM cascade_app.records WHERE key = ANY(%s)', (keys,))
            print('Synthetic test records cleaned up.')


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        raise SystemExit('Neon smoke test failed: ' + type(error).__name__) from None
