"""LinkedIn uses real owner-scoped persistence and mocked provider I/O. Never posts live."""
import json
import logging
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse, parse_qs
import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.background import BackgroundTask
from backend import social_linkedin as li

class Edit(BaseModel):
    marker: str = 'final-caption-reframe-broll'

class LinkedInTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'SOCIAL_DATABASE_PATH':self.temp.name+'/social.sqlite3','SOCIAL_TOKEN_ENCRYPTION_KEY':Fernet.generate_key().decode(),'LINKEDIN_CLIENT_ID':'client','LINKEDIN_CLIENT_SECRET':'SECRET_CLIENT','LINKEDIN_REDIRECT_URI':'https://localhost:8443/api/social/linkedin/callback','LINKEDIN_API_VERSION':'202607','GOOGLE_YOUTUBE_CLIENT_ID':'','GOOGLE_YOUTUBE_CLIENT_SECRET':''});self.env.start()
        app=FastAPI()
        @app.middleware('http')
        async def auth(request,next):
            request.state.user_id=request.headers.get('x-user','owner');return await next(request)
        def owner(pid,user):
            if user!='owner':raise HTTPException(404,'Not found')
        def selected(pid,jid,index,user):owner(pid,user)
        self.media=Path(self.temp.name)/'final.mp4';self.media.write_bytes(b'M'*82000)
        self.cleanup=MagicMock();self.render=MagicMock(return_value=FileResponse(self.media,background=BackgroundTask(self.cleanup)))
        li.register(app,SimpleNamespace(require_project=owner),selected,self.render,Edit)
        self.client=TestClient(app);self.base='/api/projects/p/editor/j/0/publish/linkedin';self.key='owner:p:j:0'
        self.token={'access_token':'SECRET_ACCESS','expires_at':time.time()+3600,'person':'urn:li:person:member1','name':'Personal profile'}
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def connect(self,**changes):li.storage.write('linkedin_connection','owner',{'encrypted':li.encrypt({**self.token,**changes})})
    def body(self):return {'title':'Edited video','caption':'Post copy (literal)','hashtags':['#Cascade'],'edit':{'marker':'saved-edits'},'submission_id':str(uuid.uuid4())}
    def state(self):
        result=self.client.post('/api/projects/p/social/linkedin/connect').json()
        self.assertIn('w_member_social',parse_qs(urlparse(result['url']).query)['scope'][0])
        return parse_qs(urlparse(result['url']).query)['state'][0]
    def response(self,status=200,data=None,headers=None):return httpx.Response(status,json=data or {},headers=headers)
    def test_missing_configuration_and_ownership(self):
        with patch.dict(os.environ,{'LINKEDIN_CLIENT_SECRET':''}):
            result=self.client.get('/api/projects/p/social/linkedin').json();self.assertFalse(result['configured']);self.assertIn('LINKEDIN_CLIENT_SECRET',result['error'])
        self.assertEqual(self.client.post(self.base,headers={'x-user':'intruder'},json=self.body()).status_code,404)
        self.assertEqual(self.client.get(self.base,headers={'x-user':'intruder'}).status_code,404)
        self.assertEqual(self.client.post('/api/projects/p/social/linkedin/connect',headers={'x-user':'intruder'}).status_code,404)
    def test_oauth_state_replay_expiry_and_cancellation(self):
        state=self.state()
        self.assertEqual(self.client.get('/api/social/linkedin/callback',params={'state':state,'error':'access_denied'}).status_code,400)
        with patch.object(li.httpx,'post') as exchange:
            self.assertEqual(self.client.get('/api/social/linkedin/callback',params={'state':state,'code':'SECRET_CODE'}).status_code,400);exchange.assert_not_called()
        state=self.state();li.storage.write('linkedin_oauth',state,{'user':'owner','expires':0})
        self.assertEqual(self.client.get('/api/social/linkedin/callback',params={'state':state,'code':'SECRET_CODE'}).status_code,400)
    def test_oauth_encrypted_user_connection_without_google_credentials(self):
        state=self.state();token={'access_token':'SECRET_ACCESS','expires_in':3600,'scope':'openid profile w_member_social'}
        with patch.object(li.httpx,'post',return_value=self.response(data=token)),patch.object(li.httpx,'get',return_value=self.response(data={'sub':'member1','name':'Personal profile'})):
            result=self.client.get('/api/social/linkedin/callback',params={'state':state,'code':'SECRET_CODE'})
        self.assertEqual(result.status_code,200);self.assertEqual(li.connection('owner')['person'],'urn:li:person:member1')
        self.assertNotIn('SECRET_ACCESS',Path(os.environ['SOCIAL_DATABASE_PATH']).read_bytes().decode(errors='ignore'))
        self.assertIsNone(li.storage.read('linkedin_connection','intruder'))
        self.assertTrue(self.client.get('/api/projects/p/social/linkedin').json()['connected'])
        self.render.assert_not_called()
    def test_missing_scopes_does_not_fake_connection(self):
        state=self.state()
        with patch.object(li.httpx,'post',return_value=self.response(data={'access_token':'SECRET_ACCESS','expires_in':3600,'scope':'openid profile'})),patch.object(li.httpx,'get') as profile:
            result=self.client.get('/api/social/linkedin/callback',params={'state':state,'code':'SECRET_CODE'});profile.assert_not_called()
        self.assertEqual(result.status_code,409);self.assertIn('w_member_social',result.json()['detail']);self.assertIsNone(li.storage.read('linkedin_connection','owner'))
    def test_expiry_and_profile_mismatch_block_publication(self):
        self.connect(expires_at=0)
        with patch.object(li.storage,'start_worker') as worker:
            result=self.client.post(self.base,json=self.body());worker.assert_not_called()
        self.assertEqual(result.status_code,409);self.assertIn('expired',result.json()['detail'])
        self.connect()
        with self.assertRaises(HTTPException):li.connection('owner','urn:li:person:different')
    def test_duplicate_submission_and_refresh_do_not_start_jobs(self):
        self.connect();body=self.body()
        with patch.object(li.storage,'start_worker') as worker:
            a=self.client.post(self.base,json=body);b=self.client.post(self.base,json=self.body());self.client.get(self.base)
        self.assertEqual(a.status_code,200);self.assertEqual(a.json(),b.json());self.assertEqual(worker.call_count,1)
        self.assertNotIn('snapshot',a.json());self.assertNotIn('person',a.json())
    def upload(self,processing='AVAILABLE',post_response=None,post_error=None,owner='urn:li:person:member1'):
        self.connect();transport=MagicMock()
        initialized={'value':{'video':'urn:li:video:video1','uploadToken':'SECRET_UPLOAD','uploadInstructions':[{'firstByte':0,'lastByte':39999,'uploadUrl':'https://www.linkedin.com/upload/part1?signature=SECRET'},{'firstByte':40000,'lastByte':81999,'uploadUrl':'https://www.linkedin.com/upload/part2?signature=SECRET'}]}}
        transport.post.side_effect=[self.response(data=initialized),self.response()]
        transport.put.side_effect=[self.response(headers={'etag':'"part-1"'}),self.response(headers={'etag':'"part-2"'})]
        def immediate(target,args):target(*args)
        # A single Processing iteration is exercised without sleeping or background threads.
        with patch.object(li.httpx,'Client') as client,patch.object(li.storage,'start_worker',side_effect=immediate),patch.object(li.httpx,'get',return_value=self.response(data={'owner':owner,'status':processing})),patch.object(li.httpx,'post',return_value=post_response or self.response(201,headers={'x-restli-id':'urn:li:share:12345'})) as create:
            if post_error:create.side_effect=post_error
            client.return_value.__enter__.return_value=transport
            result=self.client.post(self.base,json=self.body())
        return result,transport,create
    def test_final_renderer_multipart_finalize_and_confirmed_personal_post(self):
        result,transport,created=self.upload()
        self.assertEqual(result.status_code,200);data=self.client.get(self.base).json();self.assertEqual(data['status'],'Published');self.assertEqual(data['url'],'https://www.linkedin.com/feed/update/urn:li:share:12345/')
        self.render.assert_called_once();self.assertEqual(self.render.call_args.args[3].marker,'saved-edits');self.cleanup.assert_called_once()
        self.assertEqual([len(call.kwargs['content']) for call in transport.put.call_args_list],[40000,42000])
        finalize=transport.post.call_args_list[1].kwargs['json']['finalizeUploadRequest'];self.assertEqual(finalize['uploadedPartIds'],['part-1','part-2'])
        post=created.call_args.kwargs['json'];self.assertEqual(post['author'],'urn:li:person:member1');self.assertEqual(post['content']['media']['id'],'urn:li:video:video1');self.assertEqual(post['lifecycleState'],'PUBLISHED');self.assertIn('Cascade',post['commentary'])
        self.assertEqual(created.call_args.kwargs['headers']['LinkedIn-Version'],'202607')
        with patch.object(li.storage,'start_worker') as worker:self.client.post(self.base,json=self.body());worker.assert_not_called()
    def test_processing_failure_never_creates_post(self):
        _,_,created=self.upload(processing='PROCESSING_FAILED');created.assert_not_called();data=self.client.get(self.base).json();self.assertEqual(data['status'],'Failed');self.assertIn('process',data['error'])
    def test_access_rejection_has_real_status_no_tokens_and_no_fake_success(self):
        response=self.response(403,{'message':'SECRET_ACCESS rejected','serviceErrorCode':100})
        _,_,created=self.upload(post_response=response)
        data=self.client.get(self.base).json();self.assertEqual(data['status'],'Failed');self.assertIn('HTTP 403',data['error']);self.assertIn('w_member_social',data['error']);self.assertNotIn('SECRET',str(data));self.assertNotIn('url',data)
        with patch.object(li.storage,'start_worker') as worker:self.client.post(self.base,json=self.body());worker.assert_not_called()
    def test_transport_failure_after_post_attempt_blocks_duplicate_retry(self):
        self.upload(post_error=httpx.ReadTimeout('SECRET request headers'))
        result=self.client.get(self.base).json();self.assertEqual(result['status'],'Failed');self.assertTrue(result['post_attempted']);self.assertNotIn('SECRET',result['error'])
        with patch.object(li.storage,'start_worker') as worker:self.client.post(self.base,json=self.body());worker.assert_not_called()
    def test_wrong_video_owner_never_creates_post(self):
        _,_,created=self.upload(owner='urn:li:person:other');created.assert_not_called()
        result=self.client.get(self.base).json();self.assertEqual(result['status'],'Failed');self.assertIn('ownership',result['error'])

    def test_ambiguous_post_response_is_not_retried(self):
        self.connect();record={'user':'owner','pid':'p','jid':'j','index':0,'status':'Failed','submission_id':str(uuid.uuid4()),'post_attempted':True,'video':'urn:li:video:video1'};li.storage.write('linkedin_publish',self.key,record)
        with patch.object(li.storage,'start_worker') as worker:
            self.client.post(self.base,json=self.body());self.client.get(self.base);worker.assert_not_called()
    def test_caption_validation_literal_escape_and_upload_url_safety(self):
        body=li.Publish(**self.body());text=li.commentary(body);self.assertIn(r'\(literal\)',text);self.assertIn(r'{hashtag|\#|Cascade}',text)
        body.caption='x'*2999
        with self.assertRaises(HTTPException):li.commentary(body)
        for url in ['http://www.linkedin.com/u','https://evil.example/u','https://linkedin.com.evil.example/u','https://www.linkedin.com:9000/u']:
            with self.assertRaises(HTTPException):li.upload_url(url)
    def test_callback_access_logs_hide_codes_and_state(self):
        record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',('client','GET','/api/social/linkedin/callback?code=SECRET_CODE&state=SECRET_STATE','1.1',200),None)
        li.CallbackLogFilter().filter(record);self.assertNotIn('SECRET',record.getMessage())

if __name__=='__main__':unittest.main()
