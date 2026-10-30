"""Run with python -m unittest discover -s tests -v.
External identity, S3, and AI workers are mocked; persistence/HTTP/ownership are real.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import app1
from backend.routers import clips as clip_routes
from backend.core import jobs as core_jobs
from backend.core import media as core_media
from backend.core import storage as core_storage
from backend.core import config as service_config
from backend.core import auth
import backend.core.storage
from backend.services import projects_store
from backend.services import features as feature_workers


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.storage = patch.dict(os.environ, {'CASCADE_STORAGE': 'local', 'LLM_PROVIDER': 'anthropic', 'ANTHROPIC_API_KEY': 'test-key', 'DEEPGRAM_API_KEY': 'test-key', 'CASCADE_METADATA_STORE': 'local'})
        self.storage.start()
        self.temp = tempfile.TemporaryDirectory()
        self.directory = patch.object(core_jobs, 'JOBS_DIR', Path(self.temp.name))
        self.directory.start()
        self.auth = patch.object(auth, 'verify_clerk_token', side_effect=lambda token: token)
        self.auth.start()
        self.client = TestClient(app1.app)
        self.headers = {'Authorization': 'Bearer user-a'}
        self.other = {'Authorization': 'Bearer user-b'}
        self.project = self.client.post('/api/projects', json={'name': 'My project'}, headers=self.headers).json()

    def tearDown(self):
        self.storage.stop()
        self.auth.stop()
        self.directory.stop()
        self.temp.cleanup()
        core_jobs.jobs.clear()

    def test_authentication_and_static_allowlist(self):
        for url in ['/api/projects', '/api/features/' + 'a'*32, '/api/my-clips']:
            self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/.env').status_code, 404)
        self.assertEqual(self.client.get('/integration.py').status_code, 404)
        self.assertEqual(self.client.get('/api/projects', headers={**self.headers, 'Origin': 'https://evil.invalid'}).status_code, 403)

    def test_session_registers_only_the_verified_user(self):
        self.assertEqual(self.client.get('/api/session').status_code, 401)
        response = self.client.get('/api/session', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'user_id': 'user-a'})
        paths = list((core_jobs.JOBS_DIR / 'users').glob('*.json'))
        self.assertEqual(len(paths), 1)
        self.assertEqual(json.loads(paths[0].read_text())['clerk_user_id'], 'user-a')

    def test_project_page_fields_search_and_owned_rename(self):
        pid = self.project['id']
        self.assertIsNone(self.project['thumbnail_key'])
        self.assertEqual(self.project['created_at'], self.project['updated_at'])
        url = '/api/projects/' + pid
        self.assertEqual(self.client.patch(url, headers=self.other, json={'name': 'No'}).status_code, 404)
        self.assertEqual(self.client.patch(url, headers=self.headers, json={'name': '   '}).status_code, 400)
        renamed = self.client.patch(url, headers=self.headers, json={'name': '  Holiday  '})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()['name'], 'Holiday')
        self.assertEqual(renamed.json()['created_at'], self.project['created_at'])
        self.assertGreaterEqual(renamed.json()['updated_at'], self.project['updated_at'])
        self.assertEqual(renamed.json()['saved_clips'], [])
        self.assertEqual(len(self.client.get('/api/projects?q=HOLI', headers=self.headers).json()['projects']), 1)
        self.assertEqual(self.client.get('/api/projects?q=absent', headers=self.headers).json()['projects'], [])
        self.assertEqual(self.client.get('/api/projects?q=Holiday', headers=self.other).json()['projects'], [])

    def test_upload_and_clip_save_update_project_activity(self):
        before = self.project['updated_at']
        jid = self.upload()
        item = self.client.get('/api/projects/' + self.project['id'], headers=self.headers).json()
        self.assertGreater(item['updated_at'], before)

    def test_projects_are_persistent_and_private(self):
        pid = self.project['id']
        self.assertEqual(self.client.get('/api/projects', headers=self.headers).json()['projects'][0]['name'], 'My project')
        self.assertEqual(self.client.get('/api/projects', headers=self.other).json()['projects'], [])
        self.assertEqual(self.client.get('/api/projects/' + pid, headers=self.other).status_code, 404)
        self.assertEqual(self.client.post('/api/projects', headers=self.headers, json={'name': ' '}).status_code, 400)
        core_jobs.jobs.clear()
        self.assertEqual(self.client.get('/api/projects/' + pid, headers=self.headers).json()['name'], 'My project')

    def upload(self):
        with patch.object(core_storage, 'resolve_storage_folder', return_value={'folder': 'users', 'source': 'test'}), patch.object(core_jobs.worker, 'submit') as submit:
            result = self.client.post('/upload', headers=self.headers, data={'project_id': self.project['id'], 'search': 'waterfalls'}, files={'video': ('source.mp4', b'example-source', 'video/mp4')})
        self.assertEqual(result.status_code, 202)
        self.assertIs(submit.call_args.args[0], clip_routes.process_upload)
        return result.json()['job_id']

    def test_agent_upload_checks_keys_and_dispatches(self):
        data = {'project_id': self.project['id'], 'search': 'four funny moments'}
        files = lambda: {'video': ('a.mp4', b'video')}
        with patch.object(core_jobs.worker, 'submit') as submit:
            # a missing key fails at upload with a clear message, not minutes into a job
            for missing in ('DEEPGRAM_API_KEY', 'ANTHROPIC_API_KEY'):
                with patch.dict(os.environ, {missing: ''}):
                    response = self.client.post('/upload', headers=self.headers, data=data, files=files())
                self.assertEqual(response.status_code, 503, missing)
                self.assertIn(missing, response.json()['detail'])
            with patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': ''}):
                response = self.client.post('/upload', headers=self.headers, data=data, files=files())
            self.assertEqual(response.status_code, 503)
            self.assertIn('OPENAI_API_KEY', response.json()['detail'])
            submit.assert_not_called()

            response = self.client.post('/upload', headers=self.headers, data=data, files=files())
            self.assertEqual(response.status_code, 202)
            self.assertIs(submit.call_args.args[0], clip_routes.process_upload)


    def test_upload_project_association_history_and_source(self):
        job_id = self.upload()
        pid = self.project['id']
        owner = json.loads((core_jobs.JOBS_DIR / job_id / 'owner.json').read_text())
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
        folder = core_jobs.JOBS_DIR / job_id
        (folder / 'clip_1.mp4').write_bytes(b'real-file-fixture')
        (folder / 'clip_1.vtt').write_bytes(b'WEBVTT\n\n')
        clip = {'clip_url': f'/clips/{job_id}/clip_1.mp4', 'captions_url': f'/clips/{job_id}/clip_1.vtt', 'title': 'Clip', 'start': 0, 'end': 2}
        core_jobs.save_json(folder / 'results.json', {'clips': [clip], 'research': {'comparison': 'fixture'}})
        core_jobs.jobs.clear()
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
        core_jobs.jobs.clear()
        result = self.client.get('/api/features/' + job_id, headers=self.headers).json()
        self.assertEqual(result['state'], 'error')
        with core_jobs.jobs_lock:
            core_jobs.jobs[job_id] = {'state': 'processing'}
        projects_store.fail_feature(job_id)
        core_jobs.jobs.clear()
        self.assertEqual(self.client.get('/api/features/' + job_id, headers=self.headers).json()['state'], 'error')

    def test_cancel_is_owned_and_worker_stops_on_next_progress(self):
        job_id = self.upload()
        url = '/api/features/' + job_id + '/cancel'
        self.assertEqual(self.client.post(url, headers=self.other).status_code, 404)
        self.assertEqual(self.client.post(url, headers=self.headers).status_code, 200)
        with self.assertRaises(core_jobs.JobCancelled):
            core_jobs.update_job(job_id, message='Next stage')
        projects_store.fail_feature(job_id, core_jobs.processing_error(core_jobs.JobCancelled(), 'search'))
        self.assertEqual(self.client.post(url, headers=self.headers).status_code, 409)

    def test_analysis_cache_is_reused_only_within_owned_project(self):
        original = self.upload()
        (core_jobs.JOBS_DIR / original / 'transcript.json').write_text('[{"text":"cached"}]')
        retry = self.upload()
        self.assertEqual((core_jobs.JOBS_DIR / retry / 'transcript.json').read_text(), '[{"text":"cached"}]')
        other = self.client.post('/api/projects', headers=self.headers, json={'name': 'Other'}).json()
        with patch.object(core_storage, 'resolve_storage_folder', return_value={'folder': 'users', 'source': 'test'}), patch.object(core_jobs.worker, 'submit'):
            result = self.client.post('/upload', headers=self.headers, data={'project_id': other['id'], 'search': 'blue'},
                                      files={'video': ('source.mp4', b'example-source', 'video/mp4')})
        self.assertFalse((core_jobs.JOBS_DIR / result.json()['job_id'] / 'transcript.json').exists())

    def test_search_stage_timings_are_saved_with_results(self):
        import sys
        import types
        job_id = self.upload()
        folder = core_jobs.JOBS_DIR / job_id
        fake = types.ModuleType('backend.video_search.router')
        fake.OUTPUTS = Path(self.temp.name)
        output = fake.OUTPUTS / 'generated.mp4'
        output.write_bytes(b'fixture')
        def search(*args, progress, timing, **options):
            timing({}, 'Image embeddings')
            values = {'Image embeddings': 2.5, 'Whisper transcription': 1.0}
            timing(values, None)
            return {'clip_url': '/search/generated.mp4', 'captions_vtt': 'WEBVTT\n',
                    'start': 0, 'end': 15, 'match': 'fixture', 'timings': values}
        fake.search_video = search
        with patch.dict(sys.modules, {'backend.video_search.router': fake}), \
             patch.object(core_storage, 'upload_clip_files', return_value={'storage': 'local'}):
            feature_workers.process_search(job_id, folder / 'source.video', 'blue', 'visual', 15)
        core_jobs.jobs.clear()
        result = self.client.get('/api/features/' + job_id, headers=self.headers).json()
        self.assertEqual(result['state'], 'done')
        self.assertEqual(result['timings']['Image embeddings'], 2.5)
        self.assertIn('Clip storage', result['timings'])

    def test_search_adapter_publishes_all_four_clips_and_captions(self):
        import sys
        import types
        job_id = self.upload()
        folder = core_jobs.JOBS_DIR / job_id
        fake = types.ModuleType('backend.video_search.router')
        fake.OUTPUTS = Path(self.temp.name)
        matches = []
        for index in range(4):
            name = f'generated_{index}.mp4'
            (fake.OUTPUTS / name).write_bytes(f'video-{index}'.encode())
            matches.append({'clip_url': '/search/' + name, 'start': index * 30, 'end': (index + 1) * 30,
                            'match': f'Match {index}', 'captions_vtt': f'WEBVTT\n\nCaption {index}'})
        fake.search_video = lambda *args, **kwargs: {'clips': matches, 'timings': {'Image embeddings': 1.5}, 'selection_note': ''}
        with patch.dict(sys.modules, {'backend.video_search.router': fake}), \
             patch.object(core_storage, 'upload_clip_files', return_value={'storage': 'local'}) as storage:
            feature_workers.process_search(job_id, folder / 'source.video', 'blue', 'visual', 30)
        self.assertEqual(storage.call_count, 4)
        core_jobs.jobs.clear()
        result = self.client.get('/api/features/' + job_id, headers=self.headers).json()
        self.assertEqual(len(result['clips']), 4)
        for number in range(1, 5):
            self.assertEqual((folder / f'clip_{number}.mp4').read_bytes(), f'video-{number - 1}'.encode())
            self.assertIn(f'Caption {number - 1}', (folder / f'clip_{number}.vtt').read_text())
        self.assertTrue(all(not (fake.OUTPUTS / Path(m['clip_url']).name).exists() for m in matches))
        self.assertEqual(self.client.get('/api/features/' + job_id, headers=self.other).status_code, 404)


    def test_generation_without_cloud_restores_editor_and_history(self):
        job_id = self.upload()
        folder = core_jobs.JOBS_DIR / job_id
        selection = {'start': 0, 'end': 2, 'title': 'Local clip'}
        transcript = [{'start': 0, 'end': 2, 'text': 'Local caption'}]
        def render(command):
            Path(command[-1]).write_bytes(b'local-video')
        with patch.dict(os.environ, {'CASCADE_STORAGE': 'auto', 'S3_BUCKET_NAME': '', 'DATABASE_URL': '', 'NEON_DATABASE_URL': ''}), \
                patch.object(backend.core.storage, 's3_client', side_effect=AssertionError('Local generation must not use S3')), \
                patch('backend.media.probe_media', return_value={'duration':2,'has_audio':True,'has_video':True,
                    'media_kind':'video','video_codec':'h264','audio_codec':'aac','container':'mp4','pixel_format':'yuv420p'}), \
                patch.object(clip_routes, 'select_with_agent', return_value=([selection], transcript, {})), \
                patch.object(core_media, 'run_command', side_effect=render):
            clip_routes.process_upload(job_id, folder / 'source.video', 'caption', 'speech', 2)
            core_jobs.jobs.clear()
            job = self.client.get('/api/features/' + job_id, headers=self.headers).json()
            self.assertEqual(job['state'], 'done')
            clip = job['clips'][0]
            self.assertNotIn('clip_s3_key', clip)
            self.assertEqual(self.client.get(clip['clip_url'], headers=self.headers).content, b'local-video')
            self.assertIn('Local caption', self.client.get(clip['captions_url'], headers=self.headers).text)
            self.assertEqual(self.client.get(clip['captions_url'], headers=self.other).status_code, 404)
            project_url = '/api/projects/' + self.project['id']
            self.assertEqual(self.client.get(project_url, headers=self.headers).json()['jobs'][0]['job_id'], job_id)
            self.assertEqual(self.client.post(project_url + '/saved-clips', headers=self.headers,
                                            json={'job_id': job_id, 'clip_index': 0}).status_code, 200)
            self.assertEqual(len(self.client.get('/api/my-clips', headers=self.headers).json()['clips']), 1)
            with patch.object(core_jobs.worker, 'submit') as submit:
                response = self.client.post(project_url + '/caption-styles', headers=self.headers,
                                            json={'job_id': job_id, 'clip_index': 0})
                self.assertEqual(response.status_code, 202)
                self.assertEqual(submit.call_args.args[2], folder / 'clip_1.mp4')

    def test_local_playback_with_existing_cloud_metadata(self):
        job_id = self.upload()
        folder = core_jobs.JOBS_DIR / job_id
        clip = {'clip_url': f'/clips/{job_id}/clip_1.mp4', 'captions_url': f'/clips/{job_id}/clip_1.vtt',
                's3_bucket': 'old-bucket', 'clip_s3_key': 'old-video', 'captions_s3_key': 'old-captions'}
        core_jobs.save_json(folder / 'results.json', {'clips': [clip]})
        (folder / 'clip_1.mp4').write_bytes(b'local-copy')
        (folder / 'clip_1.vtt').write_bytes(b'WEBVTT\n\n')
        with patch.object(core_storage, 's3_client', side_effect=AssertionError('Use existing local copies')):
            response = self.client.get(clip['clip_url'], headers=self.headers)
            self.assertEqual(response.content, b'local-copy')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(self.client.get(clip['clip_url'], headers=self.other).status_code, 404)
            self.assertEqual(self.client.get(clip['captions_url'], headers=self.headers).text, 'WEBVTT\n\n')

    def test_cloud_upload_uses_authoritative_owner_metadata_without_local_owner_file(self):
        folder = Path(self.temp.name) / ('e' * 32)
        owner = {'user_id': 'verified-user', 'user_folder': 'jungle'}
        with patch.dict(os.environ, {'CASCADE_STORAGE': 's3', 'S3_BUCKET_NAME': 'test-bucket'}), \
             patch.object(core_jobs, 'load_json', return_value=owner) as load, \
             patch.object(backend.core.storage, 's3_client') as client:
            result = core_storage.upload_clip_files(folder, folder.name, 'clip_1.mp4', 'clip_1.vtt')
        load.assert_called_once_with(folder / 'owner.json')
        self.assertEqual(client.return_value.upload_file.call_count, 2)
        self.assertTrue(result['clip_s3_key'].startswith('jungle/verified-user/jobs/'))

    def test_configured_cloud_upload_is_preserved(self):
        job_id = self.upload()
        folder = core_jobs.JOBS_DIR / job_id
        with patch.dict(os.environ, {'CASCADE_STORAGE': 's3', 'S3_BUCKET_NAME': 'test-bucket'}), patch.object(backend.core.storage, 's3_client') as client:
            storage = core_storage.upload_clip_files(folder, job_id, 'clip_1.mp4', 'clip_1.vtt')
            self.assertEqual(storage['s3_bucket'], 'test-bucket')
            self.assertEqual(client.return_value.upload_file.call_count, 2)
            self.assertTrue(storage['clip_s3_key'].endswith('/clip_1.mp4'))

    def test_feature_adapters_validate_ownership_before_workers(self):
        job_id = self.upload()
        prefix = '/api/projects/' + self.project['id']
        body = {'job_id': job_id, 'topic': 'waterfalls'}
        with patch.object(core_jobs.worker, 'submit') as submit:
            response = self.client.post(prefix + '/research', headers=self.headers, json=body)
            self.assertEqual(response.status_code, 202)
            self.assertIs(submit.call_args.args[0], feature_workers.research)
            self.assertEqual(self.client.post(prefix + '/research', headers=self.other, json=body).status_code, 404)
        self.assertEqual(self.client.post('/upload', headers=self.other, data={'project_id': self.project['id'], 'search': 'waterfalls'}, files={'video': ('a.mp4', b'video')}).status_code, 404)

    def test_settings_save_reload_isolation_and_legacy_preservation(self):
        legacy = Path(self.temp.name) / 'preferences.json'
        legacy.write_text(json.dumps({'tone': 'professional', 'audience': 'legacy audience'}))
        original = legacy.read_bytes()
        body = {'video_type': 'interview', 'audience': 'creators', 'tone': 'funny',
                'goal': 'grow followers', 'platforms': ['youtube', 'tiktok']}
        with patch.object(service_config, 'PROJECT_DIR', Path(self.temp.name)):
            self.assertEqual(self.client.get('/api/settings').status_code, 401)
            self.assertEqual(self.client.post('/api/settings', json=body).status_code, 401)
            self.assertEqual(self.client.get('/api/settings', headers=self.headers).json()['tone'], 'professional')
            self.assertEqual(self.client.post('/api/settings', headers=self.headers, json=body).status_code, 200)
            self.assertEqual(self.client.get('/api/settings', headers=self.headers).json(), body)
            self.assertEqual(self.client.get('/api/settings', headers=self.other).json()['tone'], 'professional')
            self.assertEqual(self.client.post('/api/settings', headers=self.other, json={**body, 'tone': 'casual'}).status_code, 200)
            self.assertEqual(self.client.get('/api/settings', headers=self.headers).json(), body)
            self.assertEqual(legacy.read_bytes(), original)
            self.assertEqual(self.client.post('/api/settings', headers=self.headers, json={**body, 'platforms': ['unknown']}).status_code, 422)
            self.assertEqual(len(self.client.get('/api/projects', headers=self.headers).json()['projects']), 1)

    def test_research_upload_without_clip_generation(self):
        url = '/api/projects/' + self.project['id'] + '/research-upload'
        data = {'topic': 'waterfalls'}
        with patch.object(core_storage, 'resolve_storage_folder', return_value={'folder': 'users', 'source': 'test'}), patch.object(core_jobs.worker, 'submit') as submit:
            response = self.client.post(url, headers=self.headers, data=data, files={'video': ('research.mp4', b'research-source', 'video/mp4')})
            self.assertEqual(response.status_code, 202)
            job_id = response.json()['job_id']
            self.assertIs(submit.call_args.args[0], feature_workers.research)
            self.assertEqual(submit.call_args.args[2].read_bytes(), b'research-source')
            submit.reset_mock()
            self.assertEqual(self.client.post(url, headers=self.other, data=data, files={'video': ('research.mp4', b'video')}).status_code, 404)
            self.assertEqual(self.client.post(url, headers=self.headers, data=data, files={'video': ('research.txt', b'video')}).status_code, 400)
            self.assertEqual(self.client.post(url, headers=self.headers, data=data, files={'video': ('research.mp4', b'')}).status_code, 400)
            submit.assert_not_called()
        owner = json.loads((core_jobs.JOBS_DIR / job_id / 'owner.json').read_text())
        self.assertEqual(owner['user_id'], 'user-a')
        self.assertEqual(owner['project_id'], self.project['id'])
        self.assertEqual(owner['kind'], 'research')
        project = self.client.get('/api/projects/' + self.project['id'], headers=self.headers).json()
        self.assertTrue(any(item['job_id'] == job_id and item['has_source'] for item in project['jobs']))

    def test_research_from_caption_job_follows_owned_source(self):
        original = self.upload()
        owner = json.loads((core_jobs.JOBS_DIR / original / 'owner.json').read_text())
        caption_job, folder = projects_store.new_feature_job(owner, 'caption-styles', original)
        url = '/api/projects/' + self.project['id'] + '/research'
        with patch.object(core_jobs.worker, 'submit') as submit:
            response = self.client.post(url, headers=self.headers, json={'job_id': caption_job, 'topic': 'waterfalls'})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(submit.call_args.args[2], core_jobs.JOBS_DIR / original / 'source.video')
            self.assertEqual(self.client.post(url, headers=self.other, json={'job_id': caption_job, 'topic': 'waterfalls'}).status_code, 404)
        owner['parent_job'] = caption_job
        core_jobs.save_json(folder / 'owner.json', owner)
        self.assertEqual(self.client.post(url, headers=self.headers, json={'job_id': caption_job, 'topic': 'waterfalls'}).status_code, 409)

    def test_caption_worker_publishes_four_results_with_storage_metadata_private(self):
        import sys
        import types
        original = self.upload()
        owner = json.loads((core_jobs.JOBS_DIR / original / 'owner.json').read_text())
        job_id, folder = projects_store.new_feature_job(owner, 'caption-styles', original)
        source = core_jobs.JOBS_DIR / original / 'clip_1.mp4'
        source.write_bytes(b'fixture')
        fake_renderer = types.ModuleType('backend.clips.render_subtitles')
        def render(video_path, styles, output_dir, whole_clip):
            self.assertTrue(whole_clip)
            self.assertEqual(Path(video_path), source)
            names = []
            for style in styles:
                name = style + '.mp4'; names.append(name)
                (output_dir / name).write_bytes(b'rendered-' + style.encode())
                (output_dir / name).with_suffix('.vtt').write_text('WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nCaption\n')
            return names
        fake_renderer.generate_four_styled_clips = render
        with patch.dict(sys.modules, {'backend.clips.render_subtitles': fake_renderer}), patch.object(core_storage, 'upload_clip_files', return_value={'s3_bucket': 'test-bucket', 'clip_s3_key': 'private-key', 'captions_s3_key': 'private-caption-key'}) as storage:
            feature_workers.render_styles(job_id, source, {'start': 10, 'end': 12})
        self.assertEqual(storage.call_count, 4)
        core_jobs.jobs.clear()
        response = self.client.get('/api/features/' + job_id, headers=self.headers).json()
        self.assertEqual(response['state'], 'done')
        self.assertEqual(len(response['clips']), 4)
        for number, clip in enumerate(response['clips'], 1):
            self.assertEqual(clip['clip_url'], f'/clips/{job_id}/clip_{number}.mp4')
            self.assertNotIn('s3_bucket', clip)
            self.assertNotIn('clip_s3_key', clip)
            self.assertNotIn('captions_s3_key', clip)
            self.assertIn('Caption', (folder / f'clip_{number}.vtt').read_text())

    def test_research_pipeline_progress_persistence_and_cache_with_mocked_providers(self):
        import importlib
        import sys
        import types
        tags = {'visual_style': ['close-ups'], 'audio_style': ['voiceover'], 'topics': ['waterfalls'],
                'pacing': 'medium', 'tone': 'informative', 'hook_style': 'question'}
        fake_pipeline = types.ModuleType('backend.trends.pipeline')
        def analyze(*args, progress=None):
            if progress: progress('Tagging fixture')
            return {'tags': tags, 'transcript': 'fixture'}
        fake_pipeline.analyze_youtube_video = analyze
        fake_pipeline.analyze_video_file = analyze
        fake_youtube = types.ModuleType('backend.trends.youtube_trends')
        fake_youtube.get_trending_videos = lambda *args, **kwargs: [{'video_id': 'fixture', 'title': 'Fixture title', 'channel': 'Fixture channel', 'url': 'https://www.youtube.com/watch?v=fixture'}]
        with patch.dict(sys.modules, {'backend.trends.pipeline': fake_pipeline, 'backend.trends.youtube_trends': fake_youtube}):
            router = importlib.import_module('backend.trends.router')
        original = self.upload()
        owner = json.loads((core_jobs.JOBS_DIR / original / 'owner.json').read_text())
        job_id, folder = projects_store.new_feature_job(owner, 'research', original)
        cache = Path(self.temp.name) / 'research-cache'; cache.mkdir()
        with patch.dict(sys.modules, {'backend.trends.router': router}), patch.object(router, 'pipeline', fake_pipeline), patch.object(router, 'youtube_trends', fake_youtube), patch.object(router, 'RESULTS_CACHE_DIR', cache), patch.object(core_jobs, 'update_job', wraps=core_jobs.update_job) as updates:
            feature_workers.research(job_id, core_jobs.JOBS_DIR / original / 'source.video', 'waterfalls')
            self.assertTrue(any('Tagging fixture' in call.kwargs.get('message', '') for call in updates.call_args_list))
            self.assertFalse((folder / 'research').exists())
            core_jobs.jobs.clear()
            result = self.client.get('/api/features/' + job_id, headers=self.headers).json()
            self.assertEqual(result['state'], 'done')
            self.assertEqual(result['research']['trending_summary'][0]['title'], 'Fixture title')
            self.assertTrue(result['research']['comparison']['matching_traits'])
            cached_job, cached_folder = projects_store.new_feature_job(owner, 'research', original)
            with patch.object(router, '_run_analysis', side_effect=AssertionError('Cache should avoid providers')):
                feature_workers.research(cached_job, core_jobs.JOBS_DIR / original / 'source.video', 'waterfalls')
            self.assertEqual(core_jobs.jobs[cached_job]['state'], 'done')
        self.assertEqual(self.client.get('/api/features/' + job_id, headers=self.other).status_code, 404)


if __name__ == '__main__':
    unittest.main()
