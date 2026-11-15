"""Exercise the production composition root without contacting LinkedIn."""
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from backend.routers import editor_setup
from backend import social_linkedin as linkedin, social_youtube as storage


class LinkedInRegistrationTests(unittest.TestCase):
    def test_connection_and_publish_routes_are_wired_and_owner_scoped(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            'SOCIAL_DATABASE_PATH': directory+'/social.db',
            'SOCIAL_TOKEN_ENCRYPTION_KEY': Fernet.generate_key().decode(),
            'LINKEDIN_CLIENT_ID': 'fixture', 'LINKEDIN_CLIENT_SECRET': 'fixture',
            'LINKEDIN_REDIRECT_URI': 'https://example.test/api/social/linkedin/callback',
        }):
            app = FastAPI()
            @app.middleware('http')
            async def auth(request, next):
                request.state.user_id = request.headers.get('x-user', 'owner')
                return await next(request)
            def owner(*args):
                if args[-1] != 'owner':
                    raise HTTPException(404, 'Not found')
            with patch.object(editor_setup.projects_store, 'require_project', side_effect=owner), patch.object(editor_setup, 'selected_video', side_effect=owner):
                editor_setup.include_editor(app)
                client = TestClient(app)
                social = '/api/projects/p/social/linkedin'
                publish = '/api/projects/p/editor/j/0/publish/linkedin'
                with patch.object(linkedin.httpx, 'post', side_effect=AssertionError('No live provider calls')):
                    result = client.get(social)
                    self.assertEqual(result.status_code, 200)
                    self.assertTrue(result.json()['configured'])
                    self.assertFalse(result.json()['connected'])
                    connected = client.post(social+'/connect')
                    self.assertEqual(connected.status_code, 200)
                    self.assertTrue(connected.json()['url'].startswith('https://www.linkedin.com/oauth/v2/authorization?'))
                    self.assertEqual(client.get(publish).json()['status'], 'Ready')
                    # Credentials and rendering are fixtures; no worker can create a post.
                    with patch.object(linkedin, 'connection', return_value={'person': 'urn:li:person:fixture', 'name': 'Fixture profile'}), patch.object(storage, 'start_worker') as worker:
                        self.assertTrue(client.get(social).json()['connected'])
                        body = {'title': 'Fixture', 'caption': 'Caption', 'hashtags': ['#Cascade'], 'edit': {'start': 0, 'end': 5}, 'submission_id': str(uuid.uuid4())}
                        response = client.post(publish, json=body)
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(response.json()['status'], 'Rendering')
                        worker.assert_called_once()
                        saved = storage.read('linkedin_publish', 'owner:p:j:0')
                        self.assertEqual(saved['snapshot']['caption'], 'Caption')
                        self.assertEqual(client.post(publish, json=body).json()['submission_id'], body['submission_id'])
                        self.assertEqual(worker.call_count, 1)
                    self.assertEqual(client.get(social, headers={'x-user': 'other'}).status_code, 404)
                    self.assertEqual(client.get(publish, headers={'x-user': 'other'}).status_code, 404)
                    self.assertEqual(client.post(publish, json=body, headers={'x-user': 'other'}).status_code, 404)
