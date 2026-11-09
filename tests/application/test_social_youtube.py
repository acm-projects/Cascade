import os
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from backend import social_youtube as social

class Edit(BaseModel):
    pass

class SocialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'SOCIAL_DATABASE_PATH': self.temp.name+'/social.db', 'GOOGLE_YOUTUBE_CLIENT_ID':'client', 'GOOGLE_YOUTUBE_CLIENT_SECRET':'secret', 'GOOGLE_YOUTUBE_REDIRECT_URI':'http://localhost/api/social/youtube/callback', 'SOCIAL_TOKEN_ENCRYPTION_KEY':Fernet.generate_key().decode()})
        self.env.start()
        app = FastAPI()
        @app.middleware('http')
        async def auth(request, next):
            request.state.user_id = request.headers.get('x-user', 'owner')
            return await next(request)
        def owner(pid, user):
            if user != 'owner': raise HTTPException(404, 'Not found')
        def selected(pid, jid, index, user): owner(pid, user)
        social.register(app, SimpleNamespace(require_project=owner), selected, lambda *args: None, Edit)
        self.client = TestClient(app)
        self.base = '/api/projects/p/editor/j/0/publish/youtube'
    def tearDown(self):
        self.env.stop();self.temp.cleanup()
    def test_schedule_lock_releases_after_failure(self):
        with self.assertRaises(RuntimeError):
            with social.schedule_lock('same-publish-request'):
                raise RuntimeError('interrupted')
        with social.schedule_lock('same-publish-request'):
            pass

    def test_current_worker_liveness_never_sends_a_signal(self):
        with patch.object(social.os, 'kill', side_effect=AssertionError('Do not signal the server')):
            self.assertTrue(social.process_alive(os.getpid()))

    def test_owner_and_missing_account(self):
        self.assertEqual(self.client.get(self.base, headers={'x-user':'other'}).status_code,404)
        self.assertEqual(self.client.post(self.base,json={'title':'Title','edit':{},'submission_id':str(uuid.uuid4())}).status_code,409)
    def test_oauth_state_single_use_and_cancellation(self):
        result = self.client.post('/api/projects/p/social/youtube/connect').json()
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(result['url']).query)
        self.assertEqual(query['code_challenge_method'],['S256'])
        state = query['state'][0]
        self.assertEqual(self.client.get('/api/social/youtube/callback',params={'state':state,'error':'access_denied'}).status_code,400)
        self.assertIsNone(social.read('oauth', state))
        self.assertEqual(self.client.get('/api/social/youtube/callback',params={'state':state,'code':'bad'}).status_code,400)
    def oauth_state(self):
        from urllib.parse import urlparse, parse_qs
        result=self.client.post('/api/projects/p/social/youtube/connect').json()
        return parse_qs(urlparse(result['url']).query)['state'][0]

    def google_response(self, status, data):
        import httpx
        return httpx.Response(status,json=data)

    def token_response(self, **changes):
        data={'access_token':'PRIVATE_ACCESS','refresh_token':'PRIVATE_REFRESH','scope':social.SCOPES,'expires_in':3600}
        data.update(changes)
        return self.google_response(200,data)

    def test_callback_identifies_api_disabled_without_leaking_secrets(self):
        state=self.oauth_state()
        failed=self.google_response(403,{'error':{'status':'PERMISSION_DENIED','message':'PRIVATE_ACCESS secret body','errors':[{'reason':'accessNotConfigured'}],'details':[{'reason':'SERVICE_DISABLED'}]}})
        with patch.object(social.httpx,'post',return_value=self.token_response()), patch.object(social.httpx,'get',return_value=failed), self.assertLogs(social.logger,level='WARNING') as logs:
            response=self.client.get('/api/social/youtube/callback',params={'state':state,'code':'PRIVATE_CODE'})
        self.assertEqual(response.status_code,502)
        self.assertIn('channel_lookup',response.json()['detail'])
        self.assertIn('SERVICE_DISABLED',response.json()['detail'])
        combined=' '.join(logs.output)+response.text
        for secret in ('PRIVATE_ACCESS','PRIVATE_REFRESH','PRIVATE_CODE','secret body',state):
            self.assertNotIn(secret,combined)
        self.assertIsNone(social.read('connection','owner'))
        self.assertIsNone(social.read('oauth',state))

    def test_callback_token_exchange_failure_and_state_replay(self):
        state=self.oauth_state()
        with patch.object(social.httpx,'post',return_value=self.google_response(400,{'error':'invalid_grant','error_description':'PRIVATE_CODE'})), patch.object(social.httpx,'get') as lookup, self.assertLogs(social.logger,level='WARNING'):
            response=self.client.get('/api/social/youtube/callback',params={'state':state,'code':'PRIVATE_CODE'})
            self.assertIn('token_exchange (invalid_grant)',response.json()['detail'])
            self.assertEqual(self.client.get('/api/social/youtube/callback',params={'state':state,'code':'PRIVATE_CODE'}).status_code,400)
            lookup.assert_not_called()

    def test_callback_missing_scopes_and_refresh_are_distinct(self):
        for token,expected in [(self.token_response(scope=social.SCOPES.split()[0]),'scope_validation'),(self.token_response(refresh_token=None),'offline_access')]:
            state=self.oauth_state()
            with patch.object(social.httpx,'post',return_value=token),patch.object(social.httpx,'get') as lookup,self.assertLogs(social.logger,level='WARNING'):
                response=self.client.get('/api/social/youtube/callback',params={'state':state,'code':'PRIVATE_CODE'})
                self.assertIn(expected,response.json()['detail'])
                lookup.assert_not_called()

    def test_callback_channel_empty_and_success(self):
        for items,expected in [([],502),([{'id':'channel-id','snippet':{'title':'My channel'}}],200)]:
            state=self.oauth_state()
            with patch.object(social.httpx,'post',return_value=self.token_response()),patch.object(social.httpx,'get',return_value=self.google_response(200,{'items':items})) as lookup,self.assertLogs(social.logger,level='WARNING'):
                response=self.client.get('/api/social/youtube/callback',params={'state':state,'code':'PRIVATE_CODE'})
                self.assertEqual(response.status_code,expected)
                self.assertEqual(lookup.call_args.kwargs['params'],{'part':'snippet','mine':'true'})
        record=social.read('connection','owner')
        self.assertEqual(record['channel_id'],'channel-id')
        self.assertNotIn('PRIVATE_ACCESS',str(record))
        self.assertIsNone(social.read('connection','other'))

    def test_access_logs_remove_callback_query(self):
        import logging
        record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',('client','GET','/api/social/youtube/callback?code=PRIVATE_CODE&state=PRIVATE_STATE','1.1',200),None)
        social.OAuthAccessLogFilter().filter(record)
        self.assertNotIn('PRIVATE_',record.getMessage())
        self.assertIn('/api/social/youtube/callback',record.getMessage())

    def test_tokens_encrypted_and_connection_scoped(self):
        encrypted = social.protect({'refresh_token':'sensitive-token'})
        social.write('connection','owner',{'token':encrypted,'channel':'Test channel'})
        self.assertNotIn('sensitive-token',Path(os.environ['SOCIAL_DATABASE_PATH']).read_bytes().decode(errors='ignore'))
        self.assertTrue(self.client.get('/api/projects/p/social/youtube').json()['connected'])
    def test_idempotency_and_private_default(self):
        body={'title':'Title','edit':{},'submission_id':str(uuid.uuid4())}
        with patch.object(social,'credentials',return_value='access'), patch.object(social,'start_worker') as thread:
            first=self.client.post(self.base,json=body)
            second=self.client.post(self.base,json=body)
            self.assertEqual(first.status_code,200)
            self.assertEqual(first.json(),second.json())
            self.assertEqual(thread.call_count,1)
            self.assertEqual(thread.call_args.args[1][2].privacy,'private')
    def test_upload_uses_final_render_and_reports_processing(self):
        from unittest.mock import MagicMock
        from fastapi.responses import FileResponse
        from starlette.background import BackgroundTask
        media=Path(self.temp.name)/'final.mp4';media.write_bytes(b'final-edited-mp4')
        cleanup=MagicMock()
        exported=FileResponse(media,background=BackgroundTask(cleanup))
        app=FastAPI()
        @app.middleware('http')
        async def auth(request,next):
            request.state.user_id='owner'
            return await next(request)
        render=MagicMock(return_value=exported)
        social.register(app,SimpleNamespace(require_project=lambda *a:None),lambda *a:None,render,Edit)
        client=TestClient(app)
        remote=MagicMock()
        remote.post.return_value.headers={'location':'https://www.googleapis.com/upload/session'}
        remote.put.return_value.json.return_value={'id':'video123'}
        with patch.object(social,'credentials',return_value='access'), patch.object(social.httpx,'Client') as http, patch.object(social,'start_worker',side_effect=lambda target,args:target(*args)):
            http.return_value.__enter__.return_value=remote
            client.post(self.base,json={'title':'Title','edit':{},'submission_id':str(uuid.uuid4())})
        record=social.read('publish','owner:p:j:0')
        self.assertEqual(record['status'],'Processing')
        self.assertEqual(record['url'],'https://www.youtube.com/watch?v=video123')
        self.assertEqual(remote.post.call_args.kwargs['json']['status']['privacyStatus'],'private')
        render.assert_called_once();cleanup.assert_called_once()

    def test_upload_failure_is_persisted(self):
        with patch.object(social,'credentials',return_value='access'):
            response=self.client.post(self.base,json={'title':'Title','edit':{},'submission_id':str(uuid.uuid4())})
            import time
            for _ in range(100):
                result=self.client.get(self.base).json()
                if result['status']=='Failed': break
                time.sleep(.01)
            self.assertEqual(result['status'],'Failed')
            self.assertIn('error',result)

if __name__=='__main__': unittest.main()
