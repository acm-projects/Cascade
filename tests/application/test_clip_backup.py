"""No external storage calls: failed backups, retry ownership, and deletion races."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.core import auth, jobs, storage
from backend.services import clip_backup, projects_store


class ClipBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict('os.environ', {'CASCADE_METADATA_STORE': 'local', 'CASCADE_STORAGE': 'local'})
        self.env.start()
        self.root_patch = patch.object(jobs, 'JOBS_DIR', self.root)
        self.root_patch.start()
        self.auth_patch = patch.object(auth, 'verify_clerk_token', side_effect=lambda token: token)
        self.auth_patch.start()
        self.jid, self.pid, self.user = 'c'*32, 'd'*32, 'backup-owner'
        self.folder = self.root/self.jid
        self.folder.mkdir()
        project = {'id': self.pid, 'user_id': self.user, 'name': 'Backup test', 'created_at': time.time()}
        jobs.save_json(projects_store.project_dir(self.user)/(self.pid+'.json'), project)
        jobs.save_json(self.folder/'owner.json', {'user_id': self.user, 'project_id': self.pid})
        clips = []
        for i in (1, 2):
            (self.folder/f'clip_{i}.mp4').write_bytes(b'local-media')
            (self.folder/f'clip_{i}.vtt').write_text('WEBVTT\n', encoding='utf-8')
            clips.append({'clip_url': f'/clips/{self.jid}/clip_{i}.mp4', 'captions_url': f'/clips/{self.jid}/clip_{i}.vtt',
                          'start': 0, 'end': 2, 'media_kind': 'video', 'backup_state': 'pending'})
        jobs.save_json(self.folder/'results.json', {'clips': clips, 'backup_state': 'pending'})
        jobs.jobs[self.jid] = {'state': 'done', 'clips': clips}
        self.client = TestClient(app)
        self.headers = {'Authorization': 'Bearer '+self.user}

    def tearDown(self):
        jobs.jobs.pop(self.jid, None)
        self.auth_patch.stop()
        self.root_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    def result(self):
        return jobs.load_json(self.folder/'results.json')

    def wait_complete(self):
        deadline = time.monotonic()+5
        while self.result()['backup_state'] == 'pending' and time.monotonic() < deadline:
            time.sleep(.01)
        return self.result()

    def test_failed_upload_is_playable_and_retry_only_uploads_missing_files(self):
        def first_upload(folder, jid, filename, captions, **kwargs):
            if filename == 'clip_1.mp4':
                raise OSError('Fake offline storage')
            return {'s3_bucket': 'test', 'clip_s3_key': filename, 'captions_s3_key': captions}
        with patch.object(storage, 'uses_local_storage', return_value=False), patch.object(storage, 'upload_clip_files', side_effect=first_upload):
            clip_backup.schedule(self.folder, self.jid).result(timeout=5)
        self.assertEqual(self.result()['backup_state'], 'failed')
        self.assertEqual(jobs.jobs[self.jid]['state'], 'done')
        self.assertEqual(self.client.get(f'/clips/{self.jid}/clip_1.mp4', headers=self.headers).status_code, 200)

        calls = []
        def succeed(folder, jid, filename, captions, **kwargs):
            calls.append(filename)
            return {'s3_bucket': 'test', 'clip_s3_key': filename, 'captions_s3_key': captions}
        url = f'/api/projects/{self.pid}/generations/{self.jid}/backup/retry'
        with (patch.object(storage, 'uses_local_storage', return_value=False),
              patch.object(storage, 'upload_clip_files', side_effect=succeed),
              patch.object(jobs.worker, 'submit', side_effect=AssertionError('Backup retry must not regenerate clips'))):
            self.assertEqual(self.client.post(url, headers={'Authorization': 'Bearer someone-else'}).status_code, 404)
            self.assertEqual(self.client.post(url, headers=self.headers).status_code, 202)
            result = self.wait_complete()
        self.assertEqual(result['backup_state'], 'complete')
        self.assertEqual(calls, ['clip_1.mp4'])
        self.assertTrue(all((self.folder/f'clip_{i}.mp4').is_file() for i in (1, 2)))

    def test_deleted_project_is_not_recreated_by_late_backup(self):
        entered, release = threading.Event(), threading.Event()
        def upload(*args, **kwargs):
            entered.set()
            release.wait(5)
            return {'s3_bucket': 'test', 'clip_s3_key': 'clip', 'captions_s3_key': 'caption'}
        with patch.object(storage, 'uses_local_storage', return_value=False), patch.object(storage, 'upload_clip_files', side_effect=upload):
            future = clip_backup.schedule(self.folder, self.jid)
            try:
                self.assertTrue(entered.wait(3))
                owner = jobs.load_json(self.folder/'owner.json')
                owner['project_deleted'] = True
                jobs.save_json(self.folder/'owner.json', owner)
            finally:
                release.set()
                future.result(timeout=5)
        self.assertEqual(self.result()['backup_state'], 'pending')
        self.assertTrue(jobs.load_json(self.folder/'owner.json')['project_deleted'])
