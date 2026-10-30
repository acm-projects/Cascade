"""Planning + authenticated moving-crop FFmpeg exports; paid APIs never called."""
import json
import math
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import reframe, editor
from tests import test_editor as fixture

class ReframePlanTests(unittest.TestCase):
    def analysis(self,kind='switch'):
        rows=[]
        for i in range(250):
            t=i/25
            faces=[{'id':1,'box':[.1+.02*math.sin(t),.2,.12,.2],'score':.99 if t<4 else .01},
                   {'id':2,'box':[.72,.2,.12,.2],'score':.99 if t>=4 else .01}]
            if kind=='overlap':
                for f in faces:f['score']=.99
            rows.append({'t':t,'audio':True,'faces':faces})
        return {'version':1,'frames':rows,'duration':10,'has_audio':True,'width':640,'height':360}

    def test_speaker_switch_smooth_bounded_and_uncertainty(self):
        g=editor.composition_geometry(640,360,editor.Composition(mode='fill',ratio='9:16'))
        plan=reframe.plan(self.analysis(),g)
        self.assertLess(plan['points'][15]['x'],.3)
        self.assertGreater(plan['points'][-1]['x'],.8)
        self.assertTrue(all(0<=p['x']<=1 and 0<=p['y']<=1 for p in plan['points']))
        self.assertLess(max(abs(a['x']-b['x']) for a,b in zip(plan['points'],plan['points'][1:])),.15)
        overlap=reframe.plan(self.analysis('overlap'),g)
        self.assertEqual(len({p['x']for p in overlap['points']}),1)
        left=reframe.plan(self.analysis(),g,'left');self.assertLess(left['points'][-1]['x'],.3)
        both=reframe.plan(self.analysis(),g,'both');self.assertIn('otherwise framing holds',both['warning'])

class ReframeExportTests(unittest.TestCase):
    setUpClass=classmethod(fixture.EditorTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.EditorTests.tearDownClass.__func__)
    setUp=fixture.EditorTests.setUp
    tearDown=fixture.EditorTests.tearDown
    job=fixture.EditorTests.job
    get=fixture.EditorTests.get

    def test_saved_motion_real_ffmpeg_and_owner_scope(self):
        from backend.services import projects_store
        folder=projects_store.project_dir('editor-user')/'editor'/self.pid/'reframe'/(self.jid+'-0');folder.mkdir(parents=True)
        analysis={'version':reframe.VERSION,'width':320,'height':180,'duration':3,'has_audio':True,'frames':[{'t':i/25,'audio':True,'faces':[{'id':1,'box':[.1+i/75*.6,.2,.1,.2],'score':.99}]} for i in range(75)]}
        ident='f'*32;(folder/(ident+'.json')).write_text(json.dumps({'status':'ready','analysis':analysis}))
        draft=self.get()['draft'];draft['state']['reframe']={'enabled':True,'focus':'speaker','analysis_id':ident};draft['state']['composition'].update(mode='fill',ratio='9:16');draft['state']['captions']['enabled']=False
        self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,200)
        self.assertEqual(self.get()['draft']['state']['reframe']['analysis_id'],ident)
        plan=self.client.post(self.url+'/reframe/'+ident+'/plan',headers=self.headers,json={'composition':draft['state']['composition'],'focus':'speaker'})
        self.assertEqual(plan.status_code,200)
        self.assertGreater(plan.json()['points'][-1]['x'],plan.json()['points'][0]['x'])
        result=self.client.post(self.url+'/export',headers=self.headers,json=draft['state'])
        self.assertEqual(result.status_code,200,result.text[:200]if result.status_code!=200 else '')
        path=Path(self.temp.name)/'motion.mp4';path.write_bytes(result.content)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
        self.assertTrue(any(s['codec_type']=='audio' for s in probe['streams']))
        self.assertAlmostEqual(float(probe['format']['duration']),3,delta=.1)
        self.assertEqual(self.client.get(self.url+'/reframe/'+ident,headers={'Authorization':'Bearer other'}).status_code,404)
        self.job(1,'b'*32)
        other_url=self.base+'/'+'b'*32+'/0'
        self.assertEqual(self.client.post(other_url+'/reframe/'+ident+'/plan',headers=self.headers,json={'composition':draft['state']['composition'],'focus':'speaker'}).status_code,409)

    def test_chat_reframe_action_is_a_real_request_not_coordinates(self):
        state=editor.Edit(start=0,end=3)
        result=editor.apply_actions(state,[editor.Action(type='reframe_focus',focus='left')],3)
        self.assertTrue(result.reframe.enabled);self.assertEqual(result.reframe.focus,'left');self.assertEqual(result.composition.mode,'fill')
        result=editor.apply_actions(result,[editor.Action(type='reframe_focus',focus='off')],3)
        self.assertFalse(result.reframe.enabled)
