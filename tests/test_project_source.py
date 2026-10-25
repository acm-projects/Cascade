"""Project source lifecycle; provider work is mocked, media smoke uses FFmpeg."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import app1
from backend import integration
from backend.services import source_prep


class ProjectSourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for context in (
            patch.object(app1, 'JOBS_DIR', self.root),
            patch.object(app1, 'verify_clerk_token', side_effect=lambda token: token),
            patch.dict(os.environ, {'CASCADE_STORAGE': 'local', 'CASCADE_WARM_MODELS': '0',
                'DEEPGRAM_API_KEY': 'fixture', 'ANTHROPIC_API_KEY': 'fixture', 'LLM_PROVIDER': 'anthropic'}),
        ):
            context.start()
            self.addCleanup(context.stop)
        self.submit_patch = patch.object(app1.worker, 'submit')
        self.submit = self.submit_patch.start()
        self.addCleanup(self.submit_patch.stop)
        self.addCleanup(app1.jobs.clear)
        self.client = TestClient(app1.app)
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer source-user'}
        self.pid = self.client.post('/api/projects', headers=self.headers, json={'name': 'Video project'}).json()['id']
        self.base = f'/api/projects/{self.pid}'

    def upload(self, content=b'video bytes', headers=None):
        return self.client.post(self.base + '/source', headers=headers or self.headers,
            files={'video': ('example.mp4', content, 'video/mp4')})

    def project(self):
        return self.client.get(self.base, headers=self.headers).json()

    def generate(self, **kwargs):
        return self.client.post(self.base + '/generations', headers=self.headers,
            json={'prompt': 'funny moments', 'clip_count': 2, 'request_id': 'first', **kwargs})

    def prepared(self, jid, build=None):
        def thumbnail(video, output, at):
            Path(output).write_bytes(b'fake jpeg')
        with patch.object(source_prep, 'inspect_video', return_value=(300., True)), patch.object(
            source_prep, 'make_thumbnail', side_effect=thumbnail
        ) as make, patch.object(source_prep, 'build_index', side_effect=build) as index, patch.object(
            source_prep, 'ensure_summaries'
        ) as summaries:
            source_prep.prepare_source(jid, self.pid, 'source-user')
        return make, index, summaries

    def test_upload_once_prepares_thumbnail_and_uses_project_source(self):
        response = self.upload()
        self.assertEqual(response.status_code, 202, response.text)
        jid = response.json()['source_job']
        self.assertEqual(response.json()['status'], 'processing')
        data = self.project()
        self.assertEqual((data['source_job'], data['source_status']), (jid, 'processing'))
        owner = json.loads((self.root / jid / 'owner.json').read_text())
        self.assertEqual(owner['kind'], 'source')
        self.assertEqual(owner['project_id'], self.pid)
        self.assertEqual((self.root / jid / 'source.video').read_bytes(), b'video bytes')
        self.submit.assert_called_once_with(source_prep.prepare_source, jid, self.pid, 'source-user')
        self.assertEqual(self.upload().status_code, 409)
        self.assertEqual(self.generate().status_code, 409)
        self.assertEqual(self.client.get(self.base + '/thumbnail', headers=self.headers).status_code, 404)
        make, index, summaries = self.prepared(jid)
        self.assertEqual(make.call_args.args[2], 30.)
        index.assert_called_once()
        summaries.assert_called_once_with(index.return_value, progress=unittest.mock.ANY)
        data = self.project()
        self.assertEqual((data['source_status'], data['source_duration'], data['source_error']), ('ready', 300., None))
        thumbnail = self.client.get(data['thumbnail_url'], headers=self.headers)
        self.assertEqual(thumbnail.content, b'fake jpeg')
        self.assertEqual(thumbnail.headers['content-type'], 'image/jpeg')
        self.assertEqual(thumbnail.headers['cache-control'], 'no-store')
        response = self.generate()
        self.assertEqual(response.status_code, 202, response.text)
        generated = response.json()['job_id']
        child = json.loads((self.root / generated / 'owner.json').read_text())
        self.assertEqual(child['source_job'], jid)
        self.assertEqual((self.root / generated / 'source.video').read_bytes(), b'video bytes')
        self.assertEqual([g['job_id'] for g in self.client.get(self.base + '/generations', headers=self.headers).json()['groups']], [generated])

    def test_thumbnail_available_during_preparation_and_new_sessions_preserved(self):
        jid = self.upload().json()['source_job']
        def indexing(*args, **kwargs):
            self.assertEqual(self.project()['source_status'], 'processing')
            self.assertEqual(self.client.get(self.base + '/thumbnail', headers=self.headers).status_code, 200)
            self.client.post(self.base + '/sessions', headers=self.headers, json={'name': 'During preparation'})
            return object()
        self.prepared(jid, build=indexing)
        self.assertEqual(len(self.project()['sessions']), 2)
        self.assertEqual(self.project()['source_status'], 'ready')

    def test_ownership_empty_upload_and_missing_source(self):
        other = {'Authorization': 'Bearer other-user'}
        self.assertEqual(self.upload(headers=other).status_code, 404)
        self.assertEqual(self.client.get(self.base + '/thumbnail', headers=other).status_code, 404)
        self.assertEqual(self.upload(b'').status_code, 400)
        self.assertNotIn('source_job', self.project())
        self.assertEqual(list(self.root.glob('*/owner.json')), [])
        self.assertEqual(self.generate().status_code, 409)
        self.assertEqual(self.upload().status_code, 202)

    def test_preparation_error_is_persisted_without_provider_secrets(self):
        jid = self.upload().json()['source_job']
        with patch.object(source_prep, 'inspect_video', side_effect=RuntimeError('secret https://provider/key')):
            with self.assertLogs('backend.services.source_prep', level='ERROR'):
                source_prep.prepare_source(jid, self.pid, 'source-user')
        data = self.project()
        self.assertEqual(data['source_status'], 'error')
        self.assertNotIn('secret', data['source_error'])
        self.assertEqual(self.generate().status_code, 409)
        self.assertEqual(app1.jobs[jid]['state'], 'error')

    def test_queue_failure_persists_error(self):
        self.submit.side_effect = RuntimeError('queue down')
        response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.project()['source_status'], 'error')
        self.assertEqual(self.upload().status_code, 409)

    def test_project_source_survives_session_deletion(self):
        jid = self.upload().json()['source_job']
        self.prepared(jid)
        first = self.project()['sessions'][0]['id']
        self.client.post(self.base + '/sessions', headers=self.headers, json={'name': 'Keep'})
        self.assertEqual(self.client.delete(self.base + '/sessions/' + first, headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get(self.base + '/thumbnail', headers=self.headers).status_code, 200)
        self.assertEqual(self.generate().status_code, 202)
        self.assertNotIn('session_deleted', json.loads((self.root / jid / 'owner.json').read_text()))

    def test_preparing_source_prevents_project_deletion(self):
        self.upload()
        self.assertEqual(self.client.delete(self.base, headers=self.headers).status_code, 409)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_five_minute_source_duration_and_thumbnail(self):
        video = self.root / 'five-minutes.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'color=c=blue:s=160x90:r=1:d=300', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)],
            check=True, capture_output=True, timeout=30)
        jid = self.upload(video.read_bytes()).json()['source_job']
        with patch.object(source_prep, 'build_index'), patch.object(source_prep, 'ensure_summaries'):
            source_prep.prepare_source(jid, self.pid, 'source-user')
        self.assertEqual(self.project()['source_status'], 'ready')
        self.assertAlmostEqual(self.project()['source_duration'], 300, delta=1)
        thumbnail = self.client.get(self.base + '/thumbnail', headers=self.headers)
        self.assertEqual(thumbnail.status_code, 200)
        self.assertTrue(thumbnail.content.startswith(b'\xff\xd8'))
        info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json',
                          str(self.root / jid / 'thumbnail.jpg')], timeout=10))
        self.assertEqual(info['streams'][0]['width'], 640)

    def test_index_failure_keeps_thumbnail_and_records_error(self):
        jid = self.upload().json()['source_job']
        with self.assertLogs('backend.services.source_prep', level='ERROR'):
            self.prepared(jid, build=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('provider secret')))
        self.assertEqual(self.project()['source_status'], 'error')
        self.assertNotIn('provider secret', self.project()['source_error'])
        self.assertEqual(self.client.get(self.base + '/thumbnail', headers=self.headers).status_code, 200)
        self.assertEqual(self.generate().status_code, 409)

    def test_source_routes_documented_and_foreign_source_rejected(self):
        jid = self.upload().json()['source_job']
        self.prepared(jid)
        other_pid = self.client.post('/api/projects', headers=self.headers, json={'name': 'Other'}).json()['id']
        other = self.client.post(f'/api/projects/{other_pid}/source', headers=self.headers,
            files={'video': ('other.mp4', b'other video', 'video/mp4')}).json()['source_job']
        self.assertEqual(self.generate(source_job=other).status_code, 404)
        schema = self.client.get('/openapi.json').json()['paths']
        self.assertIn('post', schema['/api/projects/{project_id}/source'])
        self.assertIn('get', schema['/api/projects/{project_id}/thumbnail'])
