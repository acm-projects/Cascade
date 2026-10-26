"""Native scheduling: real persistence, mocked Google transport, no real channel mutations."""
import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient
from starlette.background import BackgroundTask
from pydantic import BaseModel
from backend import youtube_schedule as schedule
from backend import social_youtube as social

class TimezoneTests(unittest.TestCase):
    def resolve(self, wall, zone='America/Chicago', offset=None):
        return schedule.resolve(schedule.Schedule(local_datetime=wall,timezone=zone,utc_offset_minutes=offset),now=datetime(2026,1,1,tzinfo=timezone.utc))
    def test_standard_daylight_and_fractional_offsets(self):
        self.assertEqual(self.resolve('2026-10-30T15:30')['publish_at'],'2026-10-30T20:30:00Z')
        self.assertEqual(self.resolve('2026-12-30T15:30')['publish_at'],'2026-12-30T21:30:00Z')
        self.assertEqual(self.resolve('2026-12-30T15:30','Asia/Kathmandu')['publish_at'],'2026-12-30T09:45:00Z')
    def test_dst_gap_and_ambiguous_hour(self):
        with self.assertRaises(HTTPException): self.resolve('2027-03-14T02:30')
        with self.assertRaises(HTTPException): self.resolve('2026-11-01T01:30')
        self.assertEqual(self.resolve('2026-11-01T01:30',offset=-300)['publish_at'],'2026-11-01T06:30:00Z')
        self.assertEqual(self.resolve('2026-11-01T01:30',offset=-360)['publish_at'],'2026-11-01T07:30:00Z')
    def test_bad_offset_zone_past_and_short_lead(self):
        for wall,zone,offset in [('2026-12-30T15:30','America/Chicago',0),('2026-12-30T15:30','fake/zone',None),('2025-01-01T00:00','UTC',None),('2026-01-01T00:29','UTC',0)]:
            with self.assertRaises(HTTPException):self.resolve(wall,zone,offset)
    def test_status_payload_preserves_settings_and_cancel_removes_timestamp(self):
        remote={'privacyStatus':'private','publishAt':'2027-01-01T00:00:00Z','embeddable':False,'license':'youtube','selfDeclaredMadeForKids':True,'uploadStatus':'processed'}
        payload=schedule.status_payload(remote,'2027-02-01T00:00:00Z')
        self.assertEqual(payload['privacyStatus'],'private');self.assertFalse(payload['embeddable']);self.assertTrue(payload['selfDeclaredMadeForKids'])
        self.assertNotIn('uploadStatus',payload)
        self.assertNotIn('publishAt',schedule.status_payload(remote))

class Edit(BaseModel):
    marker: str = 'saved-edits'

class NativeScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'SOCIAL_DATABASE_PATH':self.temp.name+'/social.db','GOOGLE_YOUTUBE_CLIENT_ID':'client','GOOGLE_YOUTUBE_CLIENT_SECRET':'secret','GOOGLE_YOUTUBE_REDIRECT_URI':'http://localhost/callback','SOCIAL_TOKEN_ENCRYPTION_KEY':Fernet.generate_key().decode()});self.env.start()
        app=FastAPI()
        @app.middleware('http')
        async def auth(request,next):
            request.state.user_id=request.headers.get('x-user','owner');return await next(request)
        def selected(pid,jid,index,user):
            if user!='owner':raise HTTPException(404,'Not found')
        media=Path(self.temp.name)/'final.mp4';media.write_bytes(b'edited-MP4')
        self.cleanup=MagicMock();self.renderer=MagicMock(return_value=FileResponse(media,background=BackgroundTask(self.cleanup)))
        social.register(app,SimpleNamespace(require_project=lambda *a:None),selected,self.renderer,Edit)
        self.client=TestClient(app);self.base='/api/projects/p/editor/j/0/publish/youtube';self.key='owner:p:j:0'
        self.connect()
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def connect(self,channel='channel1',scope=social.SCOPES):
        token={'access_token':'access','refresh_token':'refresh','expires_at':datetime.now().timestamp()+3600,'scope':scope}
        social.write('connection','owner',{'token':social.protect(token),'channel':'Channel','channel_id':channel})
    def future(self,hours=3):
        dt=datetime.now(timezone.utc)+timedelta(hours=hours)
        return {'local_datetime':dt.strftime('%Y-%m-%dT%H:%M'),'timezone':'UTC','utc_offset_minutes':0}
    def body(self):return {'title':'Snapshot title','description':'Caption\n\n#tag','hashtags':['#tag'],'privacy':'private','submission_id':str(uuid.uuid4()),'edit':{'marker':'saved-edits'},'schedule':self.future()}
    def record(self,status='Processing',**changes):
        rec={'user':'owner','pid':'p','jid':'j','index':0,'submission_id':str(uuid.uuid4()),'status':status,'video_id':'v1','url':'https://www.youtube.com/watch?v=v1','schedule':schedule.resolve(schedule.Schedule(**self.future())),'channel_id':'channel1','privacy':'private','revision':0}
        rec.update(changes);social.write('publish',self.key,rec);return rec
    def video(self,publish_at=None,processing='succeeded',privacy='private'):
        status={'privacyStatus':privacy,'uploadStatus':'processed','embeddable':False,'selfDeclaredMadeForKids':True}
        if publish_at:status['publishAt']=publish_at
        return {'id':'v1','snippet':{'channelId':'channel1'},'processingDetails':{'processingStatus':processing},'status':status}
    def response(self,item):return httpx.Response(200,json={'items':[item]})
    def test_submission_snapshots_and_duplicate_survives_expired_request(self):
        body=self.body()
        with patch.object(social,'start_worker') as worker:
            first=self.client.post(self.base,json=body);second=self.client.post(self.base,json=body)
        self.assertEqual(first.status_code,200);self.assertEqual(worker.call_count,1);self.assertEqual(first.json(),second.json())
        stored=social.read('publish',self.key)
        self.assertEqual(stored['snapshot']['edit']['marker'],'saved-edits');self.assertEqual(stored['snapshot']['hashtags'],['#tag']);self.assertEqual(stored['channel_id'],'channel1')
        self.assertNotIn('snapshot',first.json())
        body['schedule']['local_datetime']='2000-01-01T00:00'
        self.assertEqual(self.client.post(self.base,json=body).status_code,200)
    def test_initial_upload_private_then_native_schedule_after_processing(self):
        remote=MagicMock();remote.post.return_value=httpx.Response(200,headers={'location':'https://www.googleapis.com/upload/session'},json={});remote.put.return_value=httpx.Response(200,json={'id':'v1'})
        def run_upload_only(target,args):
            if target.__name__=='run':target(*args)
        with patch.object(social.httpx,'Client') as client,patch.object(social,'start_worker',side_effect=run_upload_only):
            client.return_value.__enter__.return_value=remote
            self.client.post(self.base,json=self.body())
        self.renderer.assert_called_once();self.cleanup.assert_called_once()
        self.assertEqual(remote.post.call_args.kwargs['json']['status'],{'privacyStatus':'private'})
        rec=social.read('publish',self.key)
        with patch.object(social.httpx,'get',side_effect=[self.response(self.video()),self.response(self.video(rec['schedule']['publish_at']))]),patch.object(social.httpx,'put',return_value=httpx.Response(200,json={'id':'v1'})) as update:
            result=self.client.get(self.base).json()
        self.assertEqual(result['status'],'Scheduled');self.assertEqual(update.call_args.kwargs['json']['status']['publishAt'],rec['schedule']['publish_at']);self.assertFalse(update.call_args.kwargs['json']['status']['embeddable'])
        # Refresh can never render/reupload an existing video.
        with patch.object(social,'start_worker') as worker:self.client.post(self.base,json=self.body());worker.assert_not_called()
    def test_change_and_cancel_do_not_upload(self):
        rec=self.record('Scheduled');new=self.future(5);new_utc=schedule.resolve(schedule.Schedule(**new))['publish_at']
        with patch.object(social.httpx,'get',side_effect=[self.response(self.video(rec['schedule']['publish_at'])),self.response(self.video(new_utc))]),patch.object(social.httpx,'put',return_value=httpx.Response(200,json={'id':'v1'})) as update:
            result=self.client.put(self.base+'/schedule',json={'schedule':new,'revision':0}).json()
        self.assertEqual(result['status'],'Scheduled');self.assertEqual(result['revision'],1);self.assertEqual(result['video_id'],'v1')
        with patch.object(social.httpx,'get',side_effect=[self.response(self.video(new_utc)),self.response(self.video())]),patch.object(social.httpx,'put',return_value=httpx.Response(200,json={'id':'v1'})) as update:
            result=self.client.put(self.base+'/schedule',json={'schedule':None,'revision':1}).json()
        self.assertEqual(result['status'],'Private');self.assertIsNone(result['schedule']);self.assertIn('Private',result['message']);self.assertNotIn('publishAt',update.call_args.kwargs['json']['status']);self.renderer.assert_not_called()
    def test_ownership_revision_and_channel_binding(self):
        self.record('Scheduled')
        self.assertEqual(self.client.put(self.base+'/schedule',headers={'x-user':'other'},json={'schedule':None,'revision':0}).status_code,404)
        self.assertEqual(self.client.put(self.base+'/schedule',json={'schedule':None,'revision':2}).status_code,409)
        self.connect(channel='different-channel')
        with patch.object(social.httpx,'put') as update:
            self.assertEqual(self.client.put(self.base+'/schedule',json={'schedule':None,'revision':0}).status_code,409);update.assert_not_called()
    def test_processing_overrun_never_arms_schedule(self):
        rec=self.record();rec['schedule']['publish_at']='2000-01-01T00:00:00Z';social.write('publish',self.key,rec)
        with patch.object(social.httpx,'put') as update:
            result=self.client.get(self.base).json();update.assert_not_called()
        self.assertEqual(result['status'],'Failed');self.assertIn('new time',result['error'])
    def test_schedule_rejection_and_missing_permissions(self):
        self.record()
        rejected=httpx.Response(400,json={'error':{'errors':[{'reason':'invalidPublishAt'}]}})
        with patch.object(social.httpx,'get',return_value=self.response(self.video())),patch.object(social.httpx,'put',return_value=rejected):result=self.client.get(self.base).json()
        self.assertEqual(result['status'],'Failed');self.assertIn('invalidPublishAt',result['error'])
        self.connect(scope='https://www.googleapis.com/auth/youtube.upload')
        self.assertEqual(self.client.put(self.base+'/schedule',json={'schedule':self.future(),'revision':0}).status_code,409)
    def test_ambiguous_mutation_recovers_from_readback_without_reupload(self):
        rec=self.record('Scheduled');target=self.future(5);utc=schedule.resolve(schedule.Schedule(**target))['publish_at']
        with patch.object(social.httpx,'get',return_value=self.response(self.video(rec['schedule']['publish_at']))),patch.object(social.httpx,'put',side_effect=httpx.ReadTimeout('secret request data')):
            result=self.client.put(self.base+'/schedule',json={'schedule':target,'revision':0}).json()
        self.assertEqual(result['status'],'Verifying');self.assertNotIn('secret',result['error'])
        with patch.object(social.httpx,'get',return_value=self.response(self.video(utc))),patch.object(social.httpx,'put') as update:
            result=self.client.get(self.base).json();update.assert_not_called()
        self.assertEqual(result['status'],'Scheduled');self.assertEqual(result['video_id'],'v1');self.assertEqual(result['revision'],1)
    def test_token_refresh_inside_job_transaction(self):
        rec=social.read('connection','owner');token=json.loads(Fernet(social.config()[3].encode()).decrypt(rec['token'].encode()));token['expires_at']=0;rec['token']=social.protect(token);social.write('connection','owner',rec)
        refreshed=httpx.Response(200,json={'access_token':'renewed-access','expires_in':3600})
        with patch.object(social.httpx,'post',return_value=refreshed),patch.object(social,'start_worker'):
            result=self.client.post(self.base,json=self.body())
        self.assertEqual(result.status_code,200)
        saved=social.read('connection','owner')
        self.assertEqual(saved['channel_id'],'channel1')
        self.assertEqual(json.loads(Fernet(social.config()[3].encode()).decrypt(saved['token'].encode()))['access_token'],'renewed-access')
    def test_expired_authorization_is_actionable_without_upload(self):
        rec=social.read('connection','owner');token=json.loads(Fernet(social.config()[3].encode()).decrypt(rec['token'].encode()));token['expires_at']=0;rec['token']=social.protect(token);social.write('connection','owner',rec)
        with patch.object(social.httpx,'post',return_value=httpx.Response(400,json={'error':'invalid_grant'})),patch.object(social,'start_worker') as worker:
            result=self.client.post(self.base,json=self.body());worker.assert_not_called()
        self.assertEqual(result.status_code,409);self.assertIn('Reconnect',result.json()['detail'])

    def test_ambiguous_upload_blocks_new_submission(self):
        self.record('Failed',video_id=None,upload_attempted=True)
        with patch.object(social,'start_worker') as worker:
            result=self.client.post(self.base,json=self.body());worker.assert_not_called()
        self.assertEqual(result.json()['status'],'Failed')

if __name__=='__main__':unittest.main()
