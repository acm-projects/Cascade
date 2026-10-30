"""Real owned media, persistence, automatic asset execution and actual AV renders.
AI and stock transport are fixture-only; no user jobs or paid providers touched.
"""
import array
import io
import json
import math
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from tests.test_editor import EditorTests
from backend.editor.models import Action, Proposal
from backend.editor import ai
from backend.editor.audio_assets import store
from backend.editor.storage import stock_store
from backend import broll

class AdvancedEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): EditorTests.setUpClass()
    @classmethod
    def tearDownClass(cls): EditorTests.tearDownClass()
    def setUp(self):
        self.fx=EditorTests();self.fx.setUp()
        self.client=self.fx.client;self.url=self.fx.url;self.headers=self.fx.headers
        self.audio=store(self.fx.pid,self.fx.jid,0,'editor-user')
        self.assets=self.audio.library()
        self.stock=stock_store(self.fx.pid,self.fx.jid,0,'editor-user')
        self.stock.folder.mkdir(parents=True,exist_ok=True)
        self.asset=broll.Asset(id='px-12-25',provider_id=12,creator='Fixture',creator_url='https://www.pexels.com/@fixture/',source_url='https://www.pexels.com/video/12/',duration=3,width=320,height=180)
        broll.write_json(self.stock.folder/'assets.json',{self.asset.id:{'asset':self.asset.model_dump(),'video':'https://videos.pexels.com/test.mp4','image':'https://images.pexels.com/test.jpg'}})
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=red:s=320x180:d=3','-c:v','libx264',str(self.stock.folder/(self.asset.id+'.mp4'))],check=True)
    def tearDown(self): self.fx.tearDown()
    def state(self): return self.fx.get()['draft']['state']
    def chat(self, actions, message, state=None, unsupported=()):
        with patch.object(ai,'request_edit',return_value=Proposal(message='Planned only',actions=[Action(**a) for a in actions],unsupported=list(unsupported))),patch.object(broll.Store,'search',return_value={'results':[self.asset.model_dump()],'query':'red','page':1,'has_more':False}):
            return self.client.post(self.url+'/chat',headers=self.headers,json={'message':message,'state':state or self.state()})
    def test_multi_action_auto_insert_preserves_duration_and_partial_success(self):
        response=self.chat([
            {'type':'keep_first','seconds':1},
            {'type':'broll_auto','query':'red background','anchor':'Hello world','duration':.6},
            {'type':'audio_add','track':'music','query':'dramatic tension','volume':.2},
            {'type':'audio_add','track':'sfx','query':'impact hit','start':1.2},
            {'type':'motion','motion':{'start':1.2,'duration':.8,'scale_from':1,'scale_to':1.4,'shake':.01}},
            {'type':'caption_animation','animation':'karaoke'},
            {'type':'text_overlay','overlay':{'start':1.2,'duration':.7,'text':'TEDDY!'}},
            {'type':'broll_auto','query':'impossible','start':2.8,'duration':2},
        ],'Add short B-roll shots, dramatic music, a punch hit, zoom and highlighted captions. Keep the full clip.')
        self.assertEqual(response.status_code,200,response.text);data=response.json();state=data['state']
        self.assertEqual((state['start'],state['end']),(0,3))
        self.assertEqual(len(state['broll']),1);self.assertEqual(state['broll'][0]['start'],.5)
        self.assertEqual(len(state['audio']),2);self.assertEqual(len(state['motion']),1)
        self.assertEqual([r['status'] for r in data['report']].count('failed'),2)
        self.assertIn('Duration preserved',data['message']);self.assertNotIn('Planned only',data['message'])
        save=self.client.put(self.url,headers=self.headers,json={'state':state,'chat':[{'role':'assistant','text':data['message']}]})
        self.assertEqual(save.status_code,200,save.text);self.assertEqual(self.state(),state)
        self.assertEqual(self.client.put(self.url,headers={'Authorization':'Bearer intruder'},json={'state':state}).status_code,404)
    def test_negated_trim_and_legacy_search_only_response(self):
        response=self.chat([{'type':'keep_first','seconds':1},{'type':'broll_search','query':'red'}],"Do not trim. Add B-roll automatically; preserve the full clip.")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['state']['end'],3)
        self.assertEqual(len(response.json()['state']['broll']),1)
        self.assertEqual(response.json()['report'][0]['status'],'failed')

    def test_missing_audio_asset_does_not_erase_successful_captions(self):
        result=self.chat([{'type':'caption_color','color':'#ffff00'},{'type':'audio_add','query':'licensed orchestral recording by artist unavailable','track':'music'}],'Add captions and suitable orchestral music')
        self.assertEqual(result.status_code,200);self.assertEqual(result.json()['state']['audio'],[])
        self.assertEqual(result.json()['state']['captions']['color'],'#ffff00');self.assertIn('Upload',result.json()['message'])
    def test_tracking_failure_keeps_other_edits_renderable(self):
        with patch('backend.editor.chat.begin_analysis',side_effect=HTTPException(503,'Tracking unavailable')):
            r=self.chat([{'type':'reframe_focus','focus':'speaker'},{'type':'caption_color','color':'#ffff00'}],'Follow the speaker and add yellow captions')
        self.assertEqual(r.status_code,200,r.text)
        state=r.json()['state']
        self.assertEqual(state['composition']['mode'],'fit')
        self.assertFalse(state['reframe']['enabled'])
        self.assertEqual(state['captions']['color'],'#ffff00')
        self.assertTrue(any(x['status']=='failed' for x in r.json()['report']))
        self.render(state)

    def test_audio_upload_scope_and_validation(self):
        path=self.audio.media(self.assets[0]['id'])
        result=self.client.post(self.url+'/audio',headers=self.headers,files={'audio':('my.wav',path.read_bytes(),'audio/wav')},data={'name':'My permitted music','kind':'music'})
        self.assertEqual(result.status_code,200,result.text);ident=result.json()['id']
        self.assertEqual(self.client.get(self.url+'/audio/'+ident+'/media',headers=self.headers).status_code,200)
        self.assertEqual(self.client.get(self.url+'/audio/'+ident+'/media',headers={'Authorization':'Bearer intruder'}).status_code,404)
        self.assertEqual(self.client.post(self.url+'/audio',headers=self.headers,files={'audio':('bad.wav',b'not audio','audio/wav')}).status_code,422)
    def render(self,state):
        r=self.client.post(self.url+'/export',headers=self.headers,json=state)
        self.assertEqual(r.status_code,200,r.text[:500] if r.status_code!=200 else '')
        path=Path(self.fx.temp.name)/('render-'+str(len(list(Path(self.fx.temp.name).glob('render-*'))))+'.mp4');path.write_bytes(r.content);return path
    def pcm(self,path):
        data=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a','-ar','24000','-ac','1','-f','f32le','-'])
        out=array.array('f');out.frombytes(data);return out
    def frame(self,path,t):return subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
    def test_real_teddy_style_fixture_export_has_broll_zoom_captions_and_audible_mix(self):
        import app1
        from backend.core import jobs as core_jobs
        source=core_jobs.JOBS_DIR/self.fx.jid/'clip_1.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=24:d=3','-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True)
        base=self.state();base['captions']['enabled']=False
        original=self.render(base)
        result=self.chat([
            {'type':'broll_auto','query':'red','start':.5,'duration':.6},
            {'type':'audio_add','track':'music','query':'dramatic tension','volume':.6},
            {'type':'audio_add','track':'sfx','query':'bell accent','start':1.2,'volume':.7},
            {'type':'motion','motion':{'start':1.5,'duration':1,'scale_from':1.3,'scale_to':1.5,'shake':.01}},
            {'type':'caption_animation','animation':'karaoke'},
            {'type':'text_overlay','overlay':{'start':1.2,'duration':.7,'text':'TEDDY!'}},
            {'type':'transition','transition':{'fade_in':.15,'fade_out':.2}}
        ],'Add automatic B-roll, dramatic music, bell SFX, zoom shake and captions without trimming.',base)
        self.assertEqual(result.status_code,200,result.text)
        state=result.json()['state'];edited=self.render(state)
        duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(edited)]))
        self.assertAlmostEqual(duration,3,delta=.12)
        # B-roll visibly replaces the source at the requested timestamp.
        frame=self.frame(edited,.7);self.assertGreater(sum(frame[::3])/len(frame[::3]),150)
        self.assertNotEqual(self.frame(original,2),self.frame(edited,2))
        a=self.pcm(original);b=self.pcm(edited);n=min(len(a),len(b))
        self.assertGreater(math.sqrt(sum((a[i]-b[i])**2 for i in range(n))/n),.015)
        artifact=Path('/tmp/cascade-teddy-edit-fixture.mp4');shutil.copyfile(edited,artifact)
        # Tone energy changes at music (55Hz) and bell (1100Hz); dialogue (440Hz) remains.
        def energy(data,f,start,end):
            values=data[round(start*24000):round(end*24000)]
            return abs(sum(v*complex(math.cos(2*math.pi*f*i/24000),-math.sin(2*math.pi*f*i/24000)) for i,v in enumerate(values)))/len(values)
        self.assertGreater(energy(b,55,.1,.4),energy(a,55,.1,.4)+.005)
        self.assertGreater(energy(b,1100,1.22,1.5),energy(a,1100,1.22,1.5)+.005)
        self.assertGreater(energy(b,440,.6,1),.02)
    def test_music_ducking_and_fades_change_actual_audio_energy(self):
        state=self.state();state['captions']['enabled']=False
        music=next(a for a in self.assets if a['name']=='Tension pulse')
        state['audio']=[{'id':'b'*32,'asset_id':music['id'],'track':'music','start':0,'duration':3,'offset':0,'volume':1,'fade_in':.2,'fade_out':.2,'duck':True,'duck_gain':.1,'loop':True}]
        values=self.pcm(self.render(state))
        def band(start,end):
            window=values[round(start*24000):round(end*24000)]
            return abs(sum(v*complex(math.cos(2*math.pi*55*i/24000),-math.sin(2*math.pi*55*i/24000)) for i,v in enumerate(window)))/len(window)
        open_level=band(.2,.4);speech_level=band(1,1.2)
        self.assertGreater(open_level,.05)
        self.assertLess(speech_level,open_level*.3)
        self.assertLess(band(.01,.11),open_level*.7)
        self.assertLess(band(2.9,2.99),open_level*.7)

    def test_unsupported_speed_and_freeze_are_explicit_and_duration_is_not_changed(self):
        r=self.chat([{'type':'caption_color','color':'#ffff00'}],'Add yellow captions, freeze-frame and slow motion')
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['state']['end'],3)
        self.assertTrue(any('Freeze' in x for x in r.json()['unsupported']));self.assertTrue(any('Speed' in x for x in r.json()['unsupported']))
