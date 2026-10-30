"""Clip-specific research: mocked providers; real auth, storage, execution and FFmpeg."""
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from backend.editor import trends
from backend.editor.models import Edit
from backend.trends.router import _compare_tags
from tests import test_high_energy_reel as fixtures

def findings():
    return {'summary':'Keep the dialogue clear; emphasize the reaction with a restrained zoom and bold captions.',
            'strengths':['The complete opening question gives context.'],
            'suggestions':[{'category':'hook','text':'Start on the complete opening question.','reason':'The question establishes stakes.', 'source_ids':['abcdefghijk'],'at':.3,'technique':'hook'},
                {'category':'visuals','text':'Punch in on the second phrase.','reason':'Accent a change of thought.', 'source_ids':['abcdefghijk'],'at':4,'technique':'punch_in'},
                {'category':'captions','text':'Use short bold caption groups.','reason':'Keep the spoken message readable.', 'source_ids':['abcdefghijk'],'at':.3,'technique':'captions'},
                {'category':'audio','text':'Use quiet ducked music.','reason':'Dialogue remains primary.', 'source_ids':['abcdefghijk'],'at':.3,'technique':'music'}]}

def fixture_result():
    return {**findings(),'references':[{'id':'abcdefghijk','video_id':'abcdefghijk','title':'Mock reference, not live research','channel':'Fixture',
            'kind':'example','url':'https://www.youtube.com/watch?v=abcdefghijk','published_at':'2026-10-29T12:00:00Z','view_count':100,'observed_tags':{'pacing':'fast'}}],
            'comparison':{'matching_traits':['pacing: fast'],'missing_traits':[]},'failures':[],
            'coverage':'Mocked YouTube provider fixture; not live research.'}

class ClipTrendsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.ReelRenderTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixtures.ReelRenderTests.tearDownClass()
    def setUp(self):
        self.fx=fixtures.ReelRenderTests();self.fx.setUp()
        self.client=self.fx.client;self.url=self.fx.url;self.headers=self.fx.headers
        self.state=self.fx.get();self.base=self.url+'/trends'
    def tearDown(self):self.fx.tearDown()
    def analyze(self,result=None):
        def inline(fn,*args):fn(*args)
        with patch.object(trends.POOL,'submit',side_effect=inline),patch.object(trends,'collect',return_value=result or fixture_result()):
            response=self.client.post(self.base,headers=self.headers,json={'state':self.state})
        self.assertEqual(response.status_code,202,response.text);return response.json()
    def test_ownership_persistence_and_analysis_does_not_edit(self):
        before=self.fx.get();r=self.analyze()
        self.assertEqual(r['status'],'done');self.assertEqual(self.fx.get(),before)
        loaded=self.client.get(self.base,headers=self.headers).json()
        self.assertEqual(loaded['id'],r['id']);self.assertEqual(loaded['edit_version'],trends.version(Edit(**self.state)))
        for method in ('get','post'):
            kw={'json':{'state':self.state}} if method=='post' else {}
            self.assertEqual(getattr(self.client,method)(self.base,headers={'Authorization':'Bearer intruder'},**kw).status_code,404)
        self.assertEqual(self.client.post(self.base+'/apply',headers={'Authorization':'Bearer intruder'},json={'state':self.state,'research_id':r['id']}).status_code,404)
    def test_cache_expiry_and_changed_edits(self):
        r=self.analyze()
        with patch.object(trends.POOL,'submit') as submit:
            again=self.client.post(self.base,headers=self.headers,json={'state':self.state}).json()
            self.assertEqual(again['id'],r['id']);submit.assert_not_called()
        changed={**self.state,'dialogue_volume':.7}
        response=self.client.post(self.base+'/apply',headers=self.headers,json={'state':changed,'research_id':r['id']})
        self.assertEqual(response.status_code,409)
        # Use actual fixture owner rather than assuming its ID.
        from backend.editor.runtime import jobs_dir,load_json
        owner=load_json(jobs_dir()/r['job_id']/'owner.json')['user_id'];root=trends.folder(r['project_id'],r['job_id'],r['clip_index'],owner)
        expired={**r,'expires_at':time.time()-1};trends.put(root,expired)
        self.assertEqual(self.client.post(self.base+'/apply',headers=self.headers,json={'state':self.state,'research_id':r['id']}).status_code,409)
        with patch.object(trends.POOL,'submit') as submit:
            new=self.client.post(self.base,headers=self.headers,json={'state':self.state}).json()
            self.assertNotEqual(new['id'],r['id']);submit.assert_called_once();trends.RUNNING.discard(new['id'])
    def test_apply_real_state_save_and_export(self):
        r=self.analyze()
        # Avoid external stock; this fixture requests no B-roll. Missing stock is partial failure.
        with patch('backend.broll.Store.search',return_value={'results':[]}):
            a=self.client.post(self.base+'/apply',headers=self.headers,json={'state':self.state,'research_id':r['id']})
        self.assertEqual(a.status_code,200,a.text);state=a.json()['state']
        self.assertTrue(state['audio']);self.assertTrue(state['motion']);self.assertEqual(state['captions']['animation'],'pop')
        self.assertTrue(any(s['status']=='failed' for s in a.json()['report']))
        self.assertEqual(self.client.put(self.url,headers=self.headers,json={'state':state}).status_code,200)
        self.assertEqual(self.fx.get(),state)
        video=self.client.post(self.url+'/export',headers=self.headers,json=state)
        self.assertEqual(video.status_code,200);self.assertGreater(len(video.content),10000)
    def test_individual_suggestion_executes_without_searching_again(self):
        r=self.analyze()
        with patch('backend.broll.Store.search',side_effect=AssertionError('Caption suggestion must not download stock')):
            a=self.client.post(self.url+'/chat',headers=self.headers,json={'state':self.state,'message':'Apply this suggestion.','research_id':r['id'],'suggestion':2})
        self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json()['state']['captions']['animation'],'pop')
        self.assertEqual(a.json()['state']['audio'],self.state['audio'])
    def test_failure_is_persisted_and_flashy_chat_keeps_supported_edits(self):
        with patch.object(trends,'collect',side_effect=RuntimeError('private provider failure')),patch('backend.broll.Store.search',return_value={'results':[]}):
            a=self.client.post(self.url+'/chat',headers=self.headers,json={'state':self.state,'message':'Make this a crazy flashy TikTok-style edit.'})
        self.assertEqual(a.status_code,200,a.text);self.assertTrue(a.json()['state']['audio'])
        self.assertIn('RESEARCH',a.json()['message'].upper());self.assertNotIn('private provider',a.text)
        self.assertEqual(self.client.get(self.base,headers=self.headers).json()['status'],'error')
    def test_collection_uses_rendered_selected_edit_and_provenance(self):
        from backend.trends import pipeline,youtube_trends
        from backend import cascade_llm
        from backend.editor import render
        s=Edit(**self.state);s.start=.2;s.end=9.5
        video={'video_id':'abcdefghijk','title':'Mock recent example','url':'https://www.youtube.com/watch?v=abcdefghijk','channel':'Fixture','published_at':'2026-10-29T00:00:00Z','view_count':100}
        def search(query,limit):return [video] if 'tutorial' not in query else [{**video,'video_id':'lmnopqrstuv','title':'Editing tutorial'}]
        record={'topic':'talking head'}
        with patch.object(youtube_trends,'get_trending_videos',side_effect=search),patch.object(pipeline,'extract_tags',return_value={'pacing':'fast'}), \
             patch.object(pipeline,'analyze_youtube_video',return_value={'tags':{'pacing':'fast'}}), \
             patch.object(cascade_llm,'structured_json',return_value=SimpleNamespace(data=findings())),patch.object(trends,'tutorial',return_value={'techniques':['Use readable captions']}) as tutorial,patch.object(render,'export',wraps=render.export) as exporter:
            # Read identifiers from the actual route fixture.
            parts=self.url.split('/');pid,jid,index=parts[3],parts[5],int(parts[6])
            from backend.editor.runtime import load_json,jobs_dir
            user=load_json(jobs_dir()/jid/'owner.json')['user_id']
            result=trends.collect(pid,jid,index,user,s,record,lambda m:None)
        exported=exporter.call_args.args[3]
        self.assertEqual(exported.start,.2);self.assertEqual(exported.end,9.5)
        self.assertEqual(result['references'][0]['published_at'],video['published_at'])
        self.assertTrue(result['coverage'].startswith('YouTube only'))
        tutorial.assert_called_once()
        self.assertNotIn('observed_tags',result['references'][1])
        self.assertEqual(result['references'][1]['kind'],'tutorial')
    def test_comparison_counts_majority_not_lexical_max(self):
        r=_compare_tags({'tone':'other'},[{'tone':'funny'},{'tone':'funny'},{'tone':'serious'}])
        self.assertIn("'funny'",r['missing_traits'][0])

    def test_pause_cut_lands_on_measured_beat_without_splitting_speech(self):
        from backend.editor.runtime import jobs_dir
        from backend.editor.retiming import Clock
        jid=self.url.split('/')[5]
        (jobs_dir()/jid/'clip_1.vtt').write_text('WEBVTT\n\n00:00.300 --> 00:02.000\nWhy is Teddy your best friend?\n\n00:04.000 --> 00:05.800\nWait for the whole story.\n\n00:08.000 --> 00:09.300\nThis is the final complete phrase!\n')
        r=self.analyze()
        with patch('backend.broll.Store.search',return_value={'results':[]}):
            a=self.client.post(self.base+'/apply',headers=self.headers,json={'state':self.state,'research_id':r['id']})
        self.assertEqual(a.status_code,200,a.text)
        state=Edit(**a.json()['state']);self.assertEqual(len(state.timeline),2);self.assertTrue(state.speed)
        cut=Clock(state).output(state.timeline[0].end)
        self.assertLess(min(abs(cut-b) for b in state.reel.beats),.002)
        rendered=self.client.post(self.url+'/export',headers=self.headers,json=state.model_dump())
        self.assertEqual(rendered.status_code,200)

if __name__=='__main__':unittest.main()
