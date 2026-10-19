"""Stock providers are mocked; export uses real local colored videos and audio."""
import base64
import io
import json
import math
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image
from backend import broll, editor_backend as editor, integration
from tests import test_editor as editor_fixture


def provider_video(ident=12):
    return {'id':ident,'duration':3,'image':'https://images.pexels.com/videos/12/free-photo.jpeg',
            'url':f'https://www.pexels.com/video/{ident}/','user':{'name':'Fixture Creator','url':'https://www.pexels.com/@fixture/'},
            'video_files':[{'id':99,'width':3840,'height':2160,'file_type':'video/mp4','link':'https://videos.pexels.com/large.mp4'},
                           {'id':25,'width':320,'height':180,'file_type':'video/mp4','link':'https://videos.pexels.com/fixture.mp4'}]}


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=broll.Store(self.temp.name)
        self.key=patch.dict(os.environ,{'PEXELS_API_KEY':'fixture-secret'});self.key.start();self.addCleanup(self.key.stop)

    def test_mapping_caching_and_safe_fields(self):
        response=SimpleNamespace(status_code=200,json=lambda:{'videos':[provider_video()],'next_page':'provider-controlled-url-not-followed'})
        with patch.object(broll.httpx,'get',return_value=response) as get:
            result=self.store.search('mountains')
            self.assertEqual(result['results'][0]['id'],'px-12-25');self.assertTrue(result['has_more'])
            self.assertNotIn('link',json.dumps(result));self.assertNotIn('fixture-secret',json.dumps(result))
            self.assertEqual(self.store.search('mountains'),result);self.assertEqual(get.call_count,1)
            self.assertEqual(get.call_args.args[0],'https://api.pexels.com/v1/videos/search')
            self.assertFalse(get.call_args.kwargs['follow_redirects'])
        self.assertEqual(self.store.entry('px-12-25')['asset']['creator'],'Fixture Creator')

    def test_missing_key_errors_and_url_validation(self):
        for status,expected in [(429,429),(401,503),(403,503),(500,502)]:
            with patch.object(broll.httpx,'get',return_value=SimpleNamespace(status_code=status,text='fixture-secret')):
                with self.assertRaises(HTTPException) as e:self.store.search('mountains')
                self.assertEqual(e.exception.status_code,expected);self.assertNotIn('fixture-secret',e.exception.detail)
        with patch.dict(os.environ,{'PEXELS_API_KEY':''}),self.assertRaises(HTTPException) as e:self.store.search('mountains')
        self.assertEqual(e.exception.status_code,503)
        for url in ['http://videos.pexels.com/a.mp4','https://videos.pexels.com.evil.test/a.mp4','https://user:pass@videos.pexels.com/a.mp4','https://127.0.0.1/a.mp4','file:///etc/passwd','https://videos.pexels.com/a.mp4?key=secret']:
            with self.assertRaises(HTTPException):broll.provider_url(url,'video')
        for query,page in [('',1),('a',0),('a',101),('x'*161,1)]:
            with self.assertRaises(HTTPException):self.store.search(query,page)
        with self.assertRaises(HTTPException):self.store.entry('../../etc/passwd')

    def test_download_limits_validation_and_cleanup(self):
        self.seed()
        class Response:
            status_code=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def iter_bytes(self):yield b'not a video'
        with patch.object(broll.httpx,'stream',return_value=Response()):
            with self.assertRaises(HTTPException):self.store.media('px-12-25')
        self.assertEqual([p.name for p in Path(self.temp.name).iterdir()],['assets.json'])
        with patch.object(broll.httpx,'stream',return_value=Response()),patch.object(broll,'MAX_BYTES',2):
            with self.assertRaises(HTTPException) as e:self.store.media('px-12-25')
            self.assertEqual(e.exception.status_code,422)

    def seed(self):
        asset=broll.Asset(id='px-12-25',provider_id=12,creator='Fixture Creator',creator_url='https://www.pexels.com/@fixture/',source_url='https://www.pexels.com/video/12/',duration=3,width=320,height=180)
        broll.write_json(self.store.folder/'assets.json',{asset.id:{'asset':asset.model_dump(),'video':'https://videos.pexels.com/fixture.mp4','image':'https://images.pexels.com/image.jpg'}})


class BrollEditorTests(unittest.TestCase):
    setUpClass=classmethod(editor_fixture.EditorTests.setUpClass.__func__)
    tearDownClass=classmethod(editor_fixture.EditorTests.tearDownClass.__func__)
    setUp=editor_fixture.EditorTests.setUp
    tearDown=editor_fixture.EditorTests.tearDown
    job=editor_fixture.EditorTests.job
    get=editor_fixture.EditorTests.get

    def stock(self):
        store=broll.Store(integration.project_dir('editor-user')/'editor'/self.pid/'stock'/(self.jid+'-0'))
        asset=broll.Asset(id='px-12-25',provider_id=12,creator='Fixture Creator',creator_url='https://www.pexels.com/@fixture/',source_url='https://www.pexels.com/video/12/',duration=3,width=320,height=180)
        broll.write_json(store.folder/'assets.json',{asset.id:{'asset':asset.model_dump(),'video':'https://videos.pexels.com/fixture.mp4','image':'https://images.pexels.com/image.jpg'}})
        # Red then green, and 880Hz stock audio that must never enter the output.
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=red:s=320x180:r=25:d=1',
                        '-f','lavfi','-i','color=green:s=320x180:r=25:d=2','-f','lavfi','-i','sine=frequency=880:duration=3',
                        '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-map','2:a',
                        '-c:v','libx264','-c:a','aac',str(store.folder/(asset.id+'.mp4'))],check=True)
        return store,asset

    def segment(self,asset,**kw):
        return broll.Segment(id='e'*32,asset=asset,start=.5,duration=1,offset=1,**kw)

    def chat(self,state,actions,**extra):
        with patch.object(editor,'request_edit',return_value=editor.Proposal(message='model text',actions=actions)) as ai:
            response=self.client.post(self.url+'/chat',headers=self.headers,json={'state':state,'message':'explicit fixture edit',**extra})
            return response,ai

    def test_ownership_registry_persistence_and_old_drafts(self):
        state=self.get()['draft']['state'];self.assertEqual(state['broll'],[])
        store,asset=self.stock();state['broll']=[self.segment(asset).model_dump()]
        draft={'state':state,'chat':[{'role':'user','text':'Add result 1'}],'updated_at':100}
        self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,200)
        self.assertEqual(self.get()['draft'],draft)
        self.assertEqual(self.client.get(self.url+'/broll/'+asset.id+'/media',headers=self.headers).status_code,200)
        self.assertEqual(self.client.get(self.url+'/broll/'+asset.id+'/media',headers={'Authorization':'Bearer other'}).status_code,404)
        self.assertEqual(self.client.get(self.url+'/broll/px-999-25/media',headers=self.headers).status_code,422)
        draft['state']['broll'][0]['asset']['source_url']='https://evil.test/'
        self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,422)
        self.job(1,'b'*32)
        other=self.base+'/'+'b'*32+'/0'
        self.assertEqual(self.client.post(other+'/export',headers=self.headers,json=state).status_code,422)

    def test_download_valid_mp4_without_provider_credentials(self):
        store,asset=self.stock()
        path=store.folder/(asset.id+'.mp4');raw=path.read_bytes();path.unlink()
        class Response:
            status_code=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_bytes(self):yield raw
        with patch.object(broll.httpx,'stream',return_value=Response()) as stream:
            self.assertEqual(store.media(asset.id).read_bytes(),raw)
            self.assertNotIn('headers',stream.call_args.kwargs)
            self.assertFalse(stream.call_args.kwargs['follow_redirects'])

    def test_search_route_validation_and_scope(self):
        with patch.object(broll.Store,'search',return_value={'results':[],'page':1,'query':'mountains','has_more':False}) as search:
            response=self.client.get(self.url+'/broll/search?query=mountains',headers=self.headers)
            self.assertEqual(response.status_code,200);search.assert_called_once_with('mountains',1)
            self.assertEqual(self.client.get(self.url+'/broll/search?query=mountains',headers={'Authorization':'Bearer other'}).status_code,404)
            self.assertEqual(search.call_count,1)
        self.assertEqual(self.client.get(self.url+'/broll/search?query=x&page=101',headers=self.headers).status_code,422)

    def test_stock_fit_fill_output_dimensions(self):
        _,asset=self.stock()
        state=editor.Edit(start=0,end=3,captions=editor.Captions(enabled=False),composition=editor.Composition(ratio='9:16',background='#ff0000'),broll=[self.segment(asset,mode='fit')])
        path=Path(self.temp.name)/'framed-stock.mp4'
        def pixel():
            raw=subprocess.check_output(['ffmpeg','-v','error','-ss','0.8','-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
            return tuple(raw[:3])
        response=self.client.post(self.url+'/export',headers=self.headers,json=state.model_dump())
        self.assertEqual(response.status_code,200);path.write_bytes(response.content)
        self.assertGreater(pixel()[0],200) # portrait Fit leaves red output background above landscape stock
        state.broll[0].mode='fill'
        response=self.client.post(self.url+'/export',headers=self.headers,json=state.model_dump())
        self.assertEqual(response.status_code,200);path.write_bytes(response.content)
        self.assertGreater(pixel()[1],90);self.assertLess(pixel()[0],30) # Fill covers the entire frame

    def test_timing_overlap_and_trim_preserve_segments(self):
        _,asset=self.stock();segment=self.segment(asset)
        state=editor.Edit(start=0,end=3,broll=[segment])
        trimmed=editor.apply_actions(state,[editor.Action(type='trim_first',seconds=2)],3)
        self.assertEqual(trimmed.broll,state.broll) # hidden but recoverable
        for update in [{'duration':4},{'offset':2.5},{'start':2.8}]:
            with self.assertRaises(HTTPException):editor.validate_edit(state.model_copy(update={'broll':[segment.model_copy(update=update)]}),3)
        with self.assertRaises(HTTPException):editor.validate_edit(state.model_copy(update={'broll':[segment,segment.model_copy(update={'id':'f'*32,'start':1})]}),3)

    def test_chat_search_insert_move_shorten_remove_and_ambiguity(self):
        store,asset=self.stock();state=self.get()['draft']['state']
        with patch.object(broll.Store,'search',return_value={'query':'mountains','page':1,'has_more':False,'results':[asset.model_dump()]}):
            response,_=self.chat(state,[editor.Action(type='broll_search',query='mountains')])
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['state']['broll'],[])
        self.assertEqual(response.json()['broll_search']['results'][0]['id'],asset.id)
        state['start']=.5
        response,ai=self.chat(state,[editor.Action(type='broll_insert',asset_id=asset.id,start=.5,duration=1,offset=.5,time_basis='preview'),editor.Action(type='caption_color',color='#ffff00')],result_ids=[asset.id])
        self.assertEqual(response.status_code,200,response.text);state=response.json()['state'];segment=state['broll'][0]
        self.assertEqual(segment['start'],1);self.assertEqual(state['captions']['color'],'#ffff00')
        self.assertEqual(ai.call_args.args[0]['broll_results'][0]['id'],asset.id)
        response,_=self.chat(state,[editor.Action(type='broll_update',start=1.5)],selected_segment=segment['id'])
        self.assertEqual(response.status_code,200,response.text);state=response.json()['state']
        response,_=self.chat(state,[editor.Action(type='broll_update',duration=.5)],selected_segment=segment['id'])
        self.assertEqual(response.status_code,200);state=response.json()['state']
        response,_=self.chat(state,[editor.Action(type='broll_remove')])
        self.assertEqual(response.status_code,422)
        response,_=self.chat(state,[editor.Action(type='broll_remove')],selected_segment=segment['id'])
        self.assertEqual(response.json()['state']['broll'],[])
        response,_=self.chat(state,[editor.Action(type='broll_insert',asset_id='px-999-9',start=0,duration=1)],result_ids=[asset.id])
        self.assertEqual(response.status_code,422)
        with patch.object(broll.Store,'media',side_effect=HTTPException(502,'Stock download failed')):
            response,_=self.chat(state,[editor.Action(type='broll_insert',asset_id=asset.id,start=0,duration=1)],result_ids=[asset.id])
        self.assertEqual(response.status_code,502);self.assertNotIn('state',response.json())

    def test_real_export_intervals_offsets_captions_and_original_audio(self):
        import numpy as np
        store,asset=self.stock()
        state=editor.Edit(start=0,end=3,captions=editor.Captions(enabled=False),broll=[self.segment(asset),broll.Segment(id='f'*32,asset=asset,start=2,duration=.5,offset=0)])
        original=(Path(self.temp.name)/self.jid/'clip_1.mp4').read_bytes()
        response=self.client.post(self.url+'/export',headers=self.headers,json=state.model_dump())
        self.assertEqual(response.status_code,200,response.text[:200] if response.status_code!=200 else '')
        path=Path(self.temp.name)/'broll-output.mp4';path.write_bytes(response.content)
        def pixel(t,x=160,y=90):
            raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
            return tuple(raw[(y*320+x)*3:(y*320+x)*3+3])
        self.assertGreater(pixel(.2)[2],200) # blue main
        self.assertGreater(pixel(.8)[1],90) # green stock proves source offset
        self.assertGreater(pixel(1.7)[2],200) # main returns
        self.assertGreater(pixel(2.2)[0],200) # second stock segment red
        self.assertGreater(pixel(2.8)[2],200)
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-vn','-ar','8000','-ac','1','-f','f32le','-'])
        wave=np.frombuffer(raw,dtype='<f4');freq=np.fft.rfftfreq(len(wave),1/8000);peak=freq[np.abs(np.fft.rfft(wave)).argmax()]
        self.assertAlmostEqual(peak,440,delta=2) # stock 880Hz never mixed
        self.assertEqual((Path(self.temp.name)/self.jid/'clip_1.mp4').read_bytes(),original)
        # Partial trim shifts the stock source offset, preserving the hidden portion in state.
        state.start=1;state.end=2.8
        response=self.client.post(self.url+'/export',headers=self.headers,json=state.model_dump())
        self.assertEqual(response.status_code,200);path.write_bytes(response.content)
        self.assertGreater(pixel(.2)[1],90);self.assertGreater(pixel(.7)[2],200);self.assertGreater(pixel(1.2)[0],200)
        # Caption PNG must be on top of the green stock frame.
        state.start=0;state.end=3;state.captions.enabled=True
        image=Image.new('RGBA',(320,180));image.paste((255,255,0,255),(140,80,180,100));buffer=io.BytesIO();image.save(buffer,format='PNG')
        overlays=[{'start':.5,'end':2.5,'png':base64.b64encode(buffer.getvalue()).decode()}]
        response=self.client.post(self.url+'/export',headers=self.headers,json={**state.model_dump(),'overlays':overlays})
        self.assertEqual(response.status_code,200);path.write_bytes(response.content)
        self.assertGreater(pixel(.8)[0],200);self.assertGreater(pixel(.8)[1],200);self.assertLess(pixel(.8)[2],40)


if __name__=='__main__':unittest.main()
