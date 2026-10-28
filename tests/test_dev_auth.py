"""Local dev identity must never override credentials or remote peer checks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import app1


class DevAuthTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict('os.environ', {'CASCADE_WARM_MODELS': '0', 'CASCADE_METADATA_STORE': 'local'})
        environment.start()
        self.addCleanup(environment.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        jobs = patch.object(app1, 'JOBS_DIR', Path(temp.name))
        jobs.start()
        self.addCleanup(jobs.stop)
        self.client = TestClient(app1.app)
        self.addCleanup(self.client.close)

    def test_flag_off_requires_login(self):
        with patch.object(app1, 'DEV_AUTH', False):
            self.assertEqual(self.client.get('/api/projects').status_code, 401)

    def test_local_dev_projects_and_session_without_clerk(self):
        with patch.object(app1, 'DEV_AUTH', True), patch.object(
            app1, 'clerk_configuration', side_effect=AssertionError('Clerk called')
        ), patch.object(app1, 'verify_clerk_token') as verify:
            response = self.client.get('/api/projects')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'projects': []})
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(self.client.get('/api/session').json(),
                             {'user_id': 'dev-user', 'dev': True})
            self.assertEqual(self.client.get('/api/auth-config').json(),
                             {'dev_auth': True, 'publishable_key': '', 'domain': ''})
            verify.assert_not_called()

    def test_bad_credentials_are_still_rejected(self):
        with patch.object(app1, 'DEV_AUTH', True), patch.object(
            app1, 'verify_clerk_token', side_effect=HTTPException(401, 'Invalid token')
        ) as verify:
            for headers in ({'Authorization': 'Bearer invalid'},
                            {'Cookie': '__session=invalid'}):
                with self.subTest(headers=headers):
                    self.assertEqual(self.client.get('/api/projects', headers=headers).status_code, 401)
            self.assertEqual(verify.call_count, 2)
            for headers in ({'Authorization': ''}, {'Authorization': 'Basic bad'},
                            {'Cookie': '__session='}):
                with self.subTest(headers=headers):
                    self.assertEqual(self.client.get('/api/projects', headers=headers).status_code, 401)

    def test_real_identity_is_preserved(self):
        with patch.object(app1, 'DEV_AUTH', True), patch.object(
            app1, 'verify_clerk_token', return_value='real-user'
        ):
            response = self.client.get('/api/session', headers={'Authorization': 'Bearer valid'})
            self.assertEqual(response.json(), {'user_id': 'real-user'})

    def test_remote_peer_cannot_spoof_local_headers(self):
        with patch.object(app1, 'DEV_AUTH', True), TestClient(
            app1.app, client=('203.0.113.5', 1234)
        ) as client, patch.dict('os.environ', {'CASCADE_WARM_MODELS': '0', 'CASCADE_METADATA_STORE': 'local'}):
            response = client.get('/api/projects', headers={
                'Host': 'localhost', 'X-Forwarded-For': '127.0.0.1'
            })
            self.assertEqual(response.status_code, 401)

    def test_local_peer_allowlist(self):
        with patch.object(app1, 'DEV_AUTH', True):
            for host in app1.LOCAL_HOSTS:
                with self.subTest(host=host), TestClient(app1.app, client=(host, 1234)) as client:
                    self.assertEqual(client.get('/api/session').json()['user_id'], 'dev-user')

    def test_dev_mode_keeps_origin_check(self):
        with patch.object(app1, 'DEV_AUTH', True):
            self.assertEqual(self.client.get('/api/projects', headers={
                'Origin': 'https://untrusted.example'
            }).status_code, 403)

    def test_auth_config_preserves_clerk_when_disabled_or_remote(self):
        with patch.object(app1, 'clerk_configuration', return_value=('pk_test', 'clerk.example')):
            with patch.object(app1, 'DEV_AUTH', False):
                self.assertEqual(self.client.get('/api/auth-config').json(), {
                    'dev_auth': False, 'publishable_key': 'pk_test', 'domain': 'clerk.example'
                })
            with patch.object(app1, 'DEV_AUTH', True), TestClient(
                app1.app, client=('203.0.113.5', 1234)
            ) as client:
                self.assertFalse(client.get('/api/auth-config').json()['dev_auth'])

    def test_startup_warns_only_when_enabled(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), patch.object(app1, 'DEV_AUTH', enabled), patch.dict(
                'os.environ', {'CASCADE_WARM_MODELS': '0', 'CASCADE_METADATA_STORE': 'local'}
            ), patch('builtins.print') as output:
                app1.start_model_warmup()
                self.assertEqual(output.call_count, int(enabled))
                if enabled:
                    self.assertIn('never use this in production', output.call_args.args[0])
