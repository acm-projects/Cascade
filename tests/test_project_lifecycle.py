"""Persistent project flags, partial updates and owner boundaries (CAS-59)."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.main import app
from backend.core import auth, jobs
from backend.services import projects_store


class ProjectLifecycleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for context in (patch.object(jobs, 'JOBS_DIR', Path(temp.name)),
                        patch.dict('os.environ', {'CASCADE_METADATA_STORE': 'local', 'CASCADE_WARM_MODELS': '0'}),
                        patch.object(auth, 'verify_clerk_token', side_effect=lambda token: token)):
            context.start()
            self.addCleanup(context.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.owner = {'Authorization': 'Bearer lifecycle-owner'}
        self.other = {'Authorization': 'Bearer lifecycle-other'}
        self.project = self.client.post('/api/projects', headers=self.owner, json={'name': 'Lifecycle'}).json()
        self.url = '/api/projects/' + self.project['id']
        self.path = projects_store.project_dir('lifecycle-owner') / (self.project['id'] + '.json')

    def update(self, changes):
        response = self.client.patch(self.url, headers=self.owner, json=changes)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_old_projects_have_defaults_without_rewriting_on_read(self):
        original = {k: v for k, v in self.project.items() if k not in ('favorite', 'archived', 'trashed_at')}
        jobs.save_json(self.path, original)
        for result in (self.client.get(self.url, headers=self.owner).json(),
                       self.client.get('/api/projects', headers=self.owner).json()['projects'][0]):
            self.assertIs(result['favorite'], False)
            self.assertIs(result['archived'], False)
            self.assertIsNone(result['trashed_at'])
        self.assertEqual(jobs.load_json(self.path), original)
        self.assertIsNone(self.update({'favorite': True})['trashed_at'])

    def test_flags_survive_reload_and_preserve_unrelated_project_data(self):
        saved = [{'job_id': 'a' * 32, 'clip_index': 0}]
        jobs.save_json(self.path, {**self.project, 'saved_clips': saved, 'studio': {'sessions': []}})
        result = self.update({'favorite': True, 'archived': True, 'trashed': True})
        self.assertIs(result['favorite'], True)
        self.assertIs(result['archived'], True)
        self.assertAlmostEqual(result['trashed_at'], time.time(), delta=5)
        self.assertNotIn('trashed', result)
        with TestClient(app) as reloaded:
            result = reloaded.get(self.url, headers=self.owner).json()
        self.assertIs(result['favorite'], True)
        self.assertIs(result['archived'], True)
        self.assertIsNotNone(result['trashed_at'])
        self.assertEqual(result['created_at'], self.project['created_at'])
        self.assertEqual(result['saved_clips'], saved)
        self.assertEqual(result['studio'], {'sessions': []})
        self.assertGreaterEqual(result['updated_at'], self.project['updated_at'])

    def test_restore_keeps_favorite_and_archive_until_explicitly_changed(self):
        self.update({'favorite': True, 'archived': True, 'trashed': True})
        restored = self.update({'trashed': False})
        self.assertIsNone(restored['trashed_at'])
        self.assertTrue(restored['favorite'])
        self.assertTrue(restored['archived'])
        result = self.update({'favorite': False, 'archived': False, 'name': ' Renamed '})
        self.assertFalse(result['favorite'])
        self.assertFalse(result['archived'])
        self.assertEqual(result['name'], 'Renamed')

    def test_list_includes_trash_and_archive_but_never_another_owners_projects(self):
        self.update({'archived': True, 'trashed': True})
        self.assertEqual(len(self.client.get('/api/projects', headers=self.owner).json()['projects']), 1)
        self.assertEqual(self.client.get('/api/projects', headers=self.other).json()['projects'], [])
        before = jobs.load_json(self.path)
        for changes in ({'favorite': True}, {'archived': False}, {'trashed': False}, {'name': 'Stolen'}):
            self.assertEqual(self.client.patch(self.url, headers=self.other, json=changes).status_code, 404)
        self.assertEqual(jobs.load_json(self.path), before)

    def test_invalid_changes_cannot_overwrite_metadata(self):
        before = jobs.load_json(self.path)
        for change in ({}, {'favorite': None}, {'archived': 'false'}, {'trashed': 1},
                       {'name': None}, {'user_id': 'another-user'}, {'trashed_at': 42}):
            with self.subTest(change=change):
                self.assertEqual(self.client.patch(self.url, headers=self.owner, json=change).status_code, 422)
        self.assertEqual(jobs.load_json(self.path), before)

    def test_permanent_delete_reuses_existing_owner_checked_endpoint(self):
        self.update({'trashed': True})
        self.assertEqual(self.client.delete(self.url, headers=self.other).status_code, 404)
        self.assertEqual(self.client.delete(self.url, headers=self.owner).status_code, 200)
        self.assertEqual(self.client.get(self.url, headers=self.owner).status_code, 404)

    def test_active_job_prevents_permanent_delete_without_losing_trash_state(self):
        self.update({'trashed': True})
        jid, _ = projects_store.new_feature_job({'user_id': 'lifecycle-owner', 'project_id': self.project['id']}, 'research')
        self.addCleanup(jobs.jobs.pop, jid, None)
        self.assertEqual(self.client.delete(self.url, headers=self.owner).status_code, 409)
        self.assertIsNotNone(self.client.get(self.url, headers=self.owner).json()['trashed_at'])
