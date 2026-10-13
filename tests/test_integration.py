"""Run with python -m unittest discover -s tests -v.
External identity, S3, and AI workers are mocked; persistence/HTTP/ownership are real.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import app1
import integration


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = patch.object(app1, 'JOBS_DIR', Path(self.temp.name))
        self.directory.start()
        self.auth = patch.object(app1, 'verify_clerk_token', side_effect=lambda token: token)
        self.auth.start()
        self.client = TestClient(app1.app)
        self.headers = {'Authorization': 'Bearer user-a'}
        self.other = {'Authorization': 'Bearer user-b'}
        self.project = self.client.post('/api/projects', json={'name': 'My project'}, headers=self.headers).json()

    def tearDown(self):
        self.auth.stop()
        self.directory.stop()
        self.temp.cleanup()
        app1.jobs.clear()

    def test_authentication_and_static_allowlist(self):
        for url in ['/api/projects', '/api/features/' + 'a'*32, '/api/my-clips']:
            self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/.env').status_code, 404)
        self.assertEqual(self.client.get('/integration.py').status_code, 404)
        self.assertEqual(self.client.get('/api/projects', headers={**self.headers, 'Origin': 'https://evil.invalid'}).status_code, 403)

    def test_projects_are_persistent_and_private(self):
        pid = self.project['id']
        self.assertEqual(self.client.get('/api/projects', headers=self.headers).json()['projects'][0]['name'], 'My project')
        self.assertEqual(self.client.get('/api/projects', headers=self.other).json()['projects'], [])
        self.assertEqual(self.client.get('/api/projects/' + pid, headers=self.other).status_code, 404)
        self.assertEqual(self.client.post('/api/projects', headers=self.headers, json={'name': ' '}).status_code, 400)
        app1.jobs.clear()
        self.assertEqual(self.client.get('/api/projects/' + pid, headers=self.headers).json()['name'], 'My project')

    def upload(self):
        with patch.object(app1, 'resolve_storage_folder', return_value={'folder': 'users', 'source': 'test'}), patch.object(app1.worker, 'submit') as submit:
            result = self.client.post('/upload', headers=self.headers, data={'project_id': self.project['id'], 'search': 'waterfalls', 'engine': 'speech'}, files={'video': ('source.mp4', b'example-source', 'video/mp4')})
        self.assertEqual(result.status_code, 202)
        self.assertIs(submit.call_args.args[0], integration.process_search)
        return result.json()['job_id']

    def test_upload_project_association_history_and_source(self):
        job_id = self.upload()
        pid = self.project['id']
        owner = json.loads((app1.JOBS_DIR / job_id / 'owner.json').read_text())
        self.assertEqual(owner['project_id'], pid)
        self.assertEqual(owner['user_id'], 'user-a')
        project = self.client.get('/api/projects/' + pid, headers=self.headers).json()
        self.assertEqual(project['jobs'][0]['job_id'], job_id)
        self.assertEqual(project['jobs'][0]['prompt'], 'waterfalls')
        url = '/api/projects/' + pid + '/source/' + job_id
        self.assertEqual(self.client.get(url, headers=self.headers).content, b'example-source')
        self.assertEqual(self.client.get(url, headers=self.other).status_code, 404)
        self.assertEqual(self.client.get('/api/features/' + job_id, headers=self.other).status_code, 404)
        other_project = self.client.post('/api/projects', headers=self.headers, json={'name': 'Other'}).json()
        self.assertEqual(self.client.get('/api/projects/' + other_project['id'] + '/source/' + job_id, headers=self.headers).status_code, 404)

    def test_save_clip_restore_results_and_download(self):
        job_id = self.upload()
        folder = app1.JOBS_DIR / job_id
        (folder / 'clip_1.mp4').write_bytes(b'real-file-fixture')
        (folder / 'clip_1.vtt').write_text('WEBVTT\n\n')
        clip = {'clip_url': f'/clips/{job_id}/clip_1.mp4', 'captions_url': f'/clips/{job_id}/clip_1.vtt', 'title': 'Clip', 'start': 0, 'end': 2}
        app1.save_json(folder / 'results.json', {'clips': [clip], 'research': {'comparison': 'fixture'}})
        app1.jobs.clear()
        result = self.client.get('/api/features/' + job_id, headers=self.headers).json()
        self.assertEqual(result['state'], 'done')
        self.assertEqual(result['research']['comparison'], 'fixture')
        self.assertEqual(self.client.get(clip['clip_url'], headers=self.headers).content, b'real-file-fixture')
        self.assertEqual(self.client.get(clip['clip_url'], headers=self.other).status_code, 404)
        url = '/api/projects/' + self.project['id'] + '/saved-clips'
        body = {'job_id': job_id, 'clip_index': 0}
        for _ in range(2):
            self.assertEqual(self.client.post(url, headers=self.headers, json=body).status_code, 200)
        self.assertEqual(len(self.client.get('/api/projects/' + self.project['id'], headers=self.headers).json()['saved_clips']), 1)
        self.assertEqual(self.client.post(url, headers=self.headers, json={**body, 'clip_index': 1}).status_code, 404)
        self.assertEqual(self.client.post(url, headers=self.other, json=body).status_code, 404)
        self.assertEqual(len(self.client.get('/api/my-clips', headers=self.headers).json()['clips']), 1)

    def test_interrupted_jobs_and_persistent_errors(self):
        job_id = self.upload()
        app1.jobs.clear()
        result = self.client.get('/api/features/' + job_id, headers=self.headers).json()
        self.assertEqual(result['state'], 'error')
        with app1.jobs_lock:
            app1.jobs[job_id] = {'state': 'processing'}
        integration.fail_feature(job_id)
        app1.jobs.clear()
        self.assertEqual(self.client.get('/api/features/' + job_id, headers=self.headers).json()['state'], 'error')

    def test_prompt_selection_returns_real_nonoverlapping_candidates(self):
        observations = [{'start': i*40, 'end': i*40+10, 'score': 8, 'title': str(i), 'reason': 'match'} for i in range(5)]
        with patch.object(app1, 'interpret_request', return_value=('criteria', True)), patch.object(app1, 'score_observations', return_value=observations):
            clips = app1.select_clips(observations, 'prompt', 220, 15, lambda _: None)
        self.assertEqual(len(clips), 4)
        self.assertEqual([clip['title'] for clip in clips], ['0', '1', '2', '3'])
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(clips, clips[1:])))

    def test_feature_adapters_validate_ownership_before_workers(self):
        job_id = self.upload()
        prefix = '/api/projects/' + self.project['id']
        body = {'job_id': job_id, 'topic': 'waterfalls'}
        with patch.object(app1.worker, 'submit') as submit:
            response = self.client.post(prefix + '/research', headers=self.headers, json=body)
            self.assertEqual(response.status_code, 202)
            self.assertIs(submit.call_args.args[0], integration.research)
            self.assertEqual(self.client.post(prefix + '/research', headers=self.other, json=body).status_code, 404)
        self.assertEqual(self.client.post('/upload', headers=self.other, data={'project_id': self.project['id'], 'search': 'waterfalls'}, files={'video': ('a.mp4', b'video')}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
