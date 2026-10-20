import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from metadata_store import MetadataStore, get_store
from migrate_metadata import migrate


class MetadataTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = MetadataStore(self.root)
        self.project = self.root / 'projects' / ('a' * 64) / ('b' * 32 + '.json')

    def test_app_user_only_stores_clerk_id_and_first_seen_date(self):
        self.store.ensure_user('user_verified')
        path = next((self.root / 'users').glob('*.json'))
        original = self.store.read(path)
        self.store.ensure_user('user_verified')
        self.assertEqual(self.store.read(path), original)
        self.assertEqual(set(original), {'clerk_user_id', 'created_at'})
        with self.assertRaises(ValueError):
            self.store.ensure_user('')

    def test_local_storage_is_explicit_and_roundtrips(self):
        with patch.dict(os.environ, {'CASCADE_METADATA_STORE': 'local', 'DATABASE_URL': 'must-not-connect'}):
            self.assertIsNone(get_store(self.root).database_url)
        self.store.write(self.project, {'name': 'Project', 'saved_clips': []})
        self.store.append_saved_clip(self.project, 'u', {'job_id': 'c' * 32, 'clip_index': 0})
        self.store.append_saved_clip(self.project, 'u', {'job_id': 'c' * 32, 'clip_index': 0})
        self.assertEqual(len(self.store.read(self.project)['saved_clips']), 1)
        self.assertIsNone(self.store.key(self.root / '../outside.json'))
        self.assertIsNone(self.store.key(self.root / ('c' * 32) / 'transcript.json'))

    def test_neon_missing_record_does_not_use_stale_local_copy(self):
        self.store.write(self.project, {'name': 'stale'})
        store = MetadataStore(self.root, 'not-used')
        pool = MagicMock()
        store.pool = pool
        pool.getconn.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        self.assertFalse(store.exists(self.project))

    def test_project_rename_preserves_saved_clips_and_checks_owner(self):
        clip = {'job_id': 'c' * 32, 'clip_index': 0}
        self.store.write(self.project, {'name': 'Before', 'user_id': 'u', 'saved_clips': [clip], 'created_at': 10})
        renamed = self.store.update_project(self.project, 'u', {'name': 'After'})
        self.assertEqual(renamed['saved_clips'], [clip])
        self.assertEqual(renamed['created_at'], 10)
        with self.assertRaises(HTTPException):
            self.store.update_project(self.project, 'someone-else', {'name': 'Wrong'})
        self.assertEqual(self.store.read(self.project)['name'], 'After')

    def test_neon_mode_requires_configuration(self):
        with patch.dict(os.environ, {'CASCADE_METADATA_STORE': 'neon', 'DATABASE_URL': ''}):
            with self.assertRaises(HTTPException) as raised:
                get_store(self.root)
        self.assertEqual(raised.exception.status_code, 503)

    def test_database_error_is_safe_and_does_not_save_locally(self):
        store = MetadataStore(self.root, 'not-used')
        with patch.object(store, 'initialize', side_effect=RuntimeError('sensitive connection string')):
            with self.assertRaises(HTTPException) as raised:
                store.write(self.project, {'name': 'Must not report saved'})
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn('sensitive', raised.exception.detail)
        self.assertFalse(self.project.exists())

    def test_migration_only_imports_durable_metadata_and_preserves_database_records(self):
        self.store.write(self.project, {'name': 'Local'})
        job = self.root / ('c' * 32)
        self.store.write(job / 'owner.json', {'user_id': 'u'})
        self.store.write(job / 'transcript.json', [{'text': 'cache stays local'}])
        imported = {}
        def write(path, data, *, import_only=False):
            self.assertTrue(import_only)
            key = self.store.key(path)
            if key in imported:
                return 0
            imported[key] = data
            return 1
        with patch.object(self.store, 'write', side_effect=write):
            self.assertEqual(migrate(self.store)['imported'], 2)
            self.project.write_text(json.dumps({'name': 'stale changed file'}))
            self.assertEqual(migrate(self.store), {'imported': 0, 'already_present': 2})
        self.assertEqual(imported[self.store.key(self.project)]['name'], 'Local')
