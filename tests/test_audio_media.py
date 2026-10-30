"""Real audio/video encode, playback, trim and storage contracts; AI/STT mocked."""
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import numpy as np
from fastapi.testclient import TestClient
from fastapi import HTTPException
import app1
from backend.routers import clips as clip_routes
from backend.core import jobs as core_jobs
from backend.core import storage as core_storage
from backend.core import auth
from backend.media import probe_media, normalize_media, validate_filename
from backend.agent import index as indexing
from backend.agent.tools import ToolBox
from backend.core import storage


class AudioMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory()
        cls.audio = Path(cls.fixtures.name)/'podcast.mp3'
        cls.video = Path(cls.fixtures.name)/'video.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=4',
                        '-c:a','libmp3lame',str(cls.audio)],check=True)
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:size=160x120:rate=10:duration=4',
                        '-f','lavfi','-i','sine=frequency=440:duration=4','-c:v','libx264','-c:a','aac',
                        '-shortest',str(cls.video)],check=True)

    @classmethod
    def tearDownClass(cls): cls.fixtures.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for context in [patch.object(core_jobs,'JOBS_DIR',self.root),
                        patch.dict(os.environ,{'CASCADE_METADATA_STORE':'local','CASCADE_STORAGE':'local'}),
                        patch.object(auth,'verify_clerk_token',side_effect=lambda token:token),
                        patch.object(clip_routes,'requirements_error',return_value=None),
                        patch.object(core_jobs.worker,'submit')]:
            context.start();self.addCleanup(context.stop)
        self.addCleanup(core_jobs.jobs.clear)
        self.client=TestClient(app1.app);self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer audio-user'}
        self.pid=self.client.post('/api/projects',headers=self.headers,json={'name':'Audio test'}).json()['id']

    def generate(self, path):
        response=self.client.post('/upload',headers=self.headers,
            data={'project_id':self.pid,'search':'Find an insightful moment','clip_count':1},
            files={'video':(path.name,path.read_bytes(),'application/octet-stream')})
        self.assertEqual(response.status_code,202,response.text)
        jid=response.json()['job_id']
        transcript=[{'start':0,'end':3,'text':'An insightful podcast moment','speaker':0}]
        picks=[{'start':.5,'end':2.5,'title':'Insight','explanation':'A useful takeaway'}]
        with patch.object(clip_routes,'select_with_agent',return_value=(picks,transcript,{})):
            clip_routes.process_upload(jid,self.root/jid/'source.video','Find an insightful moment','both',15)
        self.assertEqual(core_jobs.jobs[jid]['state'],'done',core_jobs.jobs[jid])
        return jid,core_jobs.jobs[jid]['clips'][0]

    def test_mp3_podcast_through_generation_editor_and_native_exports(self):
        jid,clip=self.generate(self.audio)
        self.assertEqual(clip['media_kind'],'audio');self.assertTrue(clip['clip_url'].endswith('.mp3'))
        result=self.client.get(clip['clip_url'],headers=self.headers)
        self.assertEqual(result.headers['content-type'],'audio/mpeg')
        self.assertEqual(self.client.get(clip['clip_url'],headers={'Authorization':'Bearer other'}).status_code,404)
        url=f'/api/projects/{self.pid}/editor/{jid}/0'
        info=self.client.get(url,headers=self.headers).json()
        self.assertFalse(info['has_video']);self.assertTrue(info['has_audio']);self.assertTrue(info['cues'])
        draft=info['draft'];draft['state'].update(start=.25,end=1.25)
        draft['state']['texts']={'0':'Edited podcast transcript'}
        self.assertEqual(self.client.put(url,headers=self.headers,json=draft).status_code,200)
        response=self.client.post(url+'/export',headers=self.headers,json=draft['state'])
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['content-type'],'audio/mpeg')
        downloaded=self.root/'edited.mp3';downloaded.write_bytes(response.content)
        details=probe_media(downloaded)
        self.assertFalse(details['has_video']);self.assertAlmostEqual(details['duration'],1,delta=.15)
        self.assertEqual(self.client.post(url+'/reframe',headers=self.headers,json={}).status_code,422)
        self.assertEqual(self.client.get(url+'/broll/search?query=trees',headers=self.headers).status_code,422)
        invalid={**draft['state'],'composition':{'ratio':'9:16','mode':'fill'}}
        self.assertEqual(self.client.post(url+'/export',headers=self.headers,json=invalid).status_code,422)
        batch=self.client.post(f'/api/projects/{self.pid}/editor/export-selected',headers=self.headers,
            json={'clips':[{'job_id':jid,'clip_index':0,'edit':draft['state']}]})
        self.assertEqual(batch.status_code,200)
        with zipfile.ZipFile(io.BytesIO(batch.content)) as archive:
            self.assertEqual(sorted(Path(n).suffix for n in archive.namelist()),['.mp3','.vtt'])
            self.assertIn('Edited podcast transcript',archive.read(next(n for n in archive.namelist() if n.endswith('.vtt'))).decode())

    def test_mp4_video_remains_video_with_captions_and_export(self):
        jid,clip=self.generate(self.video)
        self.assertEqual(clip['media_kind'],'video')
        self.assertTrue(probe_media(self.root/jid/'clip_1.mp4')['has_video'])
        url=f'/api/projects/{self.pid}/editor/{jid}/0'
        info=self.client.get(url,headers=self.headers).json();self.assertTrue(info['has_video'])
        export=self.client.post(url+'/export',headers=self.headers,json=info['draft']['state'])
        self.assertEqual(export.status_code,200);self.assertEqual(export.headers['content-type'],'video/mp4')

    def test_mixed_audio_video_batch_keeps_each_format(self):
        entries=[]
        for source in [self.audio,self.video]:
            jid,_=self.generate(source)
            url=f'/api/projects/{self.pid}/editor/{jid}/0'
            state=self.client.get(url,headers=self.headers).json()['draft']['state']
            state['captions']['enabled']=False
            entries.append({'job_id':jid,'clip_index':0,'edit':state})
        result=self.client.post(f'/api/projects/{self.pid}/editor/export-selected',headers=self.headers,json={'clips':entries})
        self.assertEqual(result.status_code,200)
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            self.assertEqual(sorted(Path(name).suffix for name in archive.namelist()),['.mp3','.mp4'])

    def test_supported_containers_normalize_and_bad_media_fails_before_ai(self):
        for suffix,codec in [('.wav','pcm_s16le'),('.m4a','aac'),('.flac','flac')]:
            path=self.root/('input'+suffix)
            subprocess.run(['ffmpeg','-v','error','-i',str(self.audio),'-c:a',codec,str(path)],check=True)
            validate_filename(path.name)
            work=self.root/suffix[1:];work.mkdir();source=work/'source.video';shutil.copyfile(path,source)
            info=normalize_media(source)
            self.assertEqual(info['audio_codec'],'mp3');self.assertFalse(info['has_video'])
            self.assertTrue((work/'original-upload.media').is_file())
        for suffix,codec in [('.mov','libx264'),('.webm','libvpx-vp9'),('.mkv','libx264')]:
            path=self.root/('input'+suffix)
            subprocess.run(['ffmpeg','-v','error','-i',str(self.video),'-an','-c:v',codec,str(path)],check=True)
            validate_filename(path.name)
            work=self.root/suffix[1:];work.mkdir();source=work/'source.video';shutil.copyfile(path,source)
            self.assertTrue(normalize_media(source)['has_video'])
        response=self.client.post('/upload',headers=self.headers,data={'project_id':self.pid,'search':'test'},
            files={'video':('bad.exe',b'bad','audio/mpeg')})
        self.assertEqual(response.status_code,400)
        response=self.client.post('/upload',headers=self.headers,data={'project_id':self.pid,'search':'test'},
            files={'video':('broken.mp3',b'not actual audio','audio/mpeg')})
        jid=response.json()['job_id']
        with patch.object(clip_routes,'select_with_agent') as ai:
            clip_routes.process_upload(jid,self.root/jid/'source.video','test','both',15)
            ai.assert_not_called()
        self.assertEqual(core_jobs.jobs[jid]['state'],'error')
        self.assertIn('corrupted',core_jobs.jobs[jid]['message'])

    def test_audio_index_and_agent_tools_never_extract_frames(self):
        cache=self.root/'cache';cache.mkdir()
        speech=SimpleNamespace(encode=lambda text,**kwargs: np.ones((len(text),2),dtype=np.float32) if isinstance(text,list) else np.ones(2,dtype=np.float32))
        fake=SimpleNamespace(load_models=MagicMock(),search_model=speech)
        import sys
        import backend.video_search as video_search
        transcript=[{'start':0,'end':3,'text':'A surprising insight','speaker':0}]
        with patch.dict(sys.modules,{'backend.video_search.router':fake}), patch.object(video_search,'router',fake,create=True), patch.object(indexing,'CACHE_DIR',cache), \
             patch.object(indexing,'transcribe_media',return_value=transcript),patch.object(indexing,'_sample_frames',side_effect=AssertionError('No frames')):
            index=indexing.build_index(self.audio,self.root)
        fake.load_models.assert_called_once_with('speech',unittest.mock.ANY)
        self.assertFalse(index.has_video)
        toolbox=ToolBox(index,self.audio,frame_grabber=MagicMock(side_effect=AssertionError('No video')))
        overview,error=toolbox._get_overview();self.assertFalse(error)
        self.assertFalse(any(block['type']=='image' for block in overview))
        blocks,error=toolbox._inspect_clip(0,3,2);self.assertFalse(error)
        self.assertIn('insight',blocks[-1]['text'])
        self.assertTrue(index.search('insight',mode='visual'))

    def test_s3_audio_content_types_and_owner_scoped_source_backup(self):
        jid,clip=self.generate(self.audio)
        owner=core_jobs.load_json(self.root/jid/'owner.json');owner['user_folder']='users'
        client=MagicMock()
        with patch.object(storage,'uses_local_storage',return_value=False),patch.object(storage,'s3_bucket',return_value='bucket'),patch.object(storage,'s3_client',return_value=client):
            source=storage.upload_source_media(self.root/jid,jid,owner)
            self.assertIn('/audio-user/jobs/'+jid+'/',source['source_s3_key'])
            self.assertEqual(client.upload_file.call_args.kwargs['ExtraArgs']['ContentType'],'audio/mpeg')
            storage.upload_clip_files(self.root/jid,jid,'clip_1.mp3','clip_1.vtt')
            self.assertEqual(client.upload_file.call_args_list[-2].kwargs['ExtraArgs']['ContentType'],'audio/mpeg')
        # Same metadata adapter backs local fixtures and Neon JSON records; no new table.
        self.assertEqual(core_jobs.load_json(self.root/jid/'owner.json')['media_kind'],'audio')
        owner.update(source)
        core_jobs.save_json(self.root/jid/'owner.json',owner)
        (self.root/jid/'source.video').unlink()
        client.download_file.side_effect=lambda bucket,key,target: Path(target).write_bytes(self.audio.read_bytes())
        with patch.object(core_storage,'s3_client',return_value=client):
            url=f'/api/projects/{self.pid}/source/{jid}'
            self.assertEqual(self.client.get(url,headers={'Authorization':'Bearer other'}).status_code,404)
            client.download_file.assert_not_called()
            result=self.client.get(url,headers=self.headers)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.headers['content-type'],'audio/mpeg')
            self.assertEqual(result.content,self.audio.read_bytes())
