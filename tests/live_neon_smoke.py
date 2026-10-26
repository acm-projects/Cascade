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
                assert client.get('/api/session').status_code == 401
                for _ in range(2):
                    assert client.get('/api/session', headers=headers).json() == {'user_id': user}
                with store.connection() as conn, conn.cursor() as cur:
                    cur.execute('SELECT count(*), min(created_at) FROM cascade_app.users WHERE clerk_user_id = %s', (user,))
                    count, created_at = cur.fetchone()
                    assert count == 1 and created_at is not None
                response = client.post('/api/projects', headers=headers, json={'name': 'Synthetic Neon persistence test'})
                assert response.status_code == 201, response.status_code
                pid = response.json()['id']
                project_path = integration.project_dir(user) / (pid + '.json')
                keys.append(store.key(project_path))
                original_created = response.json()['created_at']
                assert response.json()['thumbnail_key'] is None
                renamed = client.patch(f'/api/projects/{pid}', headers=headers, json={'name': 'Renamed Neon test'})
                assert renamed.status_code == 200
                assert renamed.json()['created_at'] == original_created
                assert client.patch(f'/api/projects/{pid}', headers=other, json={'name': 'Forbidden'}).status_code == 404
                assert len(client.get('/api/projects?q=RENAMED', headers=headers).json()['projects']) == 1
                settings_path = integration.project_dir(user) / 'settings' / 'preferences.json'
                keys.append(store.key(settings_path))
                assert client.post('/api/settings', headers=headers, json={'tone': 'funny'}).status_code == 200
                jid, folder = integration.new_feature_job({'user_id': user, 'project_id': pid}, 'generation')
                (folder / 'source.video').write_bytes(b'synthetic-source-not-for-processing')
                keys.extend(store.key(folder / name) for name in ('owner.json', 'progress.json', 'results.json'))
                integration.finish_feature(jid, {'clips': [{'clip_url': f'/clips/{jid}/clip_1.mp4',
                    'start': 0, 'end': 5, 'title': 'Synthetic clip',
                    'captions_url': f'/clips/{jid}/clip_1.vtt', 'storage': 's3',
                    's3_bucket': 'synthetic-test', 'clip_s3_key': 'synthetic-only'}]})
                for _ in range(2):
                    assert client.post(f'/api/projects/{pid}/saved-clips', headers=headers,
                                       json={'job_id': jid, 'clip_index': 0}).status_code == 200
                studio_url = f'/api/projects/{pid}/studio'
                initial = client.get(studio_url, headers=headers).json()
                sid = initial['sessions'][0]['id']
                assert client.patch(f'{studio_url}/sessions/{sid}/state', headers=headers, json={
                    'references': [{'job_id': jid, 'clip_index': 0}],
                    'viewport': {'x': 12, 'y': 34, 'zoom': .75}}).status_code == 200
                assert client.post(studio_url + '/sessions', headers=headers,
                    json={'name': 'Emotional', 'source_job': jid}).status_code == 201
                assert client.put(studio_url + '/editor-selection', headers=headers,
                    json={'clips': [{'job_id': jid, 'clip_index': 0}]}).status_code == 200
                # Remove local metadata and clear process memory: reads must come from Neon.
                for path in Path(tmp).rglob('*.json'):
                    path.unlink()
                app1.jobs.pop(jid, None)
                result = client.get(f'/api/projects/{pid}', headers=headers)
                assert result.status_code == 200
                assert len(result.json()['saved_clips']) == 1
                assert result.json()['name'] == 'Renamed Neon test'
                assert result.json()['updated_at'] >= original_created
                assert result.json()['jobs'][0]['job_id'] == jid
                assert len(client.get('/api/projects', headers=headers).json()['projects']) == 1
                assert client.get('/api/settings', headers=headers).json()['tone'] == 'funny'
                restored = client.get(studio_url, headers=headers).json()
                assert len(restored['sessions']) == 2
                assert restored['sessions'][0]['viewport']['zoom'] == .75
                assert restored['sessions'][0]['references'][0]['job_id'] == jid
                assert restored['sessions'][1]['source_job'] == jid
                assert restored['editor_clips'][0]['job_id'] == jid
                assert client.get(f'/api/features/{jid}', headers=headers).json()['state'] == 'done'
                assert len(client.get('/api/my-clips', headers=headers).json()['clips']) == 1
                assert client.get(f'/api/projects/{pid}', headers=other).status_code == 404
                assert client.get(f'/api/features/{jid}', headers=other).status_code == 404
                assert client.get('/api/projects', headers=other).json()['projects'] == []
                with store.connection() as conn, conn.cursor() as cur:
                    cur.execute('SELECT count(*) FROM cascade_app.clips WHERE job_id = %s', (jid,))
                    assert cur.fetchone()[0] == 1
                    cur.execute('SELECT created_at, updated_at, thumbnail_key FROM cascade_app.projects WHERE id = %s', (pid,))
                    created, updated, thumbnail = cur.fetchone()
                    assert created is not None and updated >= created and thumbnail is None
                print('PASS: Neon users/projects/studio sessions/references/viewport/editor choices persist without local JSON; ownership verified.')
        finally:
            if keys:
                with store.connection() as conn, conn.cursor() as cur:
                    cur.execute('DELETE FROM cascade_app.records WHERE key = ANY(%s)', (keys,))
            with store.connection() as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM cascade_app.users WHERE clerk_user_id = %s', (user,))
            print('Synthetic test records cleaned up.')


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        raise SystemExit('Neon smoke test failed: ' + type(error).__name__) from None
