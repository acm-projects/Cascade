"""Guided research contracts and selected-edit execution; providers stay mocked."""
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
from fastapi import HTTPException
from backend.editor import trends
from tests import test_clip_trends as fixtures

class GuidedTrendsTests(fixtures.ClipTrendsTests):
    def test_editing_instruction_is_not_the_search_query(self):
        goal='Tell me how to improve this clip based on trends.'
        with patch.object(trends.POOL,'submit'):
            r=self.client.post(self.base,headers=self.headers,json={'state':self.state,'goal':goal,'topic':goal})
        self.assertEqual(r.status_code,202,r.text);data=r.json()
        self.assertEqual(data['goal'],goal);self.assertNotIn('Tell me',data['topic']);self.assertEqual(data['topic'],'comedy reaction editing')
        trends.RUNNING.discard(data['id'])
    def test_selected_batch_receipts_and_sequential_apply(self):
        r=self.analyze()
        a=self.client.post(self.base+'/apply',headers=self.headers,json={'state':self.state,'research_id':r['id'],'suggestions':[2,1]})
        self.assertEqual(a.status_code,200,a.text);data=a.json()
        self.assertEqual([o['status'] for o in data['outcomes']],['applied','applied'])
        self.assertEqual(data['application']['applied_indices'],[1,2]);self.assertEqual(len(data['state']['motion']),1)
        self.assertEqual(self.client.put(self.url,headers=self.headers,json={'state':data['state']}).status_code,200)
        persisted=self.client.get(self.base,headers=self.headers).json();self.assertTrue(persisted['applications'])
        again=self.client.post(self.base+'/apply',headers=self.headers,json={'state':data['state'],'research_id':r['id'],'suggestions':[1,3]})
        self.assertEqual(again.status_code,200,again.text);self.assertEqual(len(again.json()['state']['motion']),1)
        self.assertTrue(again.json()['state']['audio'])
        # Unrelated manual changes still invalidate the research, even after a batch.
        altered={**data['state'],'dialogue_volume':.7}
        self.assertEqual(self.client.post(self.base+'/apply',headers=self.headers,json={'state':altered,'research_id':r['id'],'suggestions':[3]}).status_code,409)
    def test_failed_action_keeps_successful_selected_action(self):
        r=self.analyze();original=trends.supported_plan
        def partial(*args,**kwargs):
            if args[5]==1:raise HTTPException(422,'Timed effect could not be applied.')
            return original(*args,**kwargs)
        with patch.object(trends,'supported_plan',side_effect=partial):
            a=self.client.post(self.base+'/apply',headers=self.headers,json={'state':self.state,'research_id':r['id'],'suggestions':[2,1]})
        self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json()['state']['captions']['animation'],'pop')
        self.assertEqual([o['status'] for o in a.json()['outcomes']],['applied','failed']);self.assertEqual(a.json()['state']['motion'],[])
    def test_missing_moment_is_unsupported_not_zero(self):
        result=fixtures.fixture_result();result['suggestions'][1]['at']=None
        r=self.analyze(result)
        loaded=self.client.get(self.base,headers=self.headers).json()
        self.assertFalse(loaded['result']['suggestions'][1]['executable'])
        a=self.client.post(self.base+'/apply',headers=self.headers,json={'state':self.state,'research_id':r['id'],'suggestions':[1,2]})
        self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json()['outcomes'][0]['status'],'unsupported')
        self.assertEqual(a.json()['state']['motion'],[]);self.assertEqual(a.json()['outcomes'][1]['status'],'applied')
    def test_missing_transcript_is_never_proof_of_no_dialogue(self):
        info={'cues':[],'has_audio':True}
        self.assertEqual(trends.speech_evidence(info)['status'],'unknown')
        self.assertIn('does not establish',trends.speech_evidence(info)['message'])
        self.assertIsNotNone(trends.support({'technique':'captions','at':None},trends.Edit(**self.state),info))
    def test_pause_removal_preserves_the_selected_opening(self):
        data=fixtures.fixture_result()
        data['suggestions'].append({'category':'pacing','text':'Tighten the pauses.','reason':'Keep the scene moving.','source_ids':['abcdefghijk'],'at':None,'technique':'pause_removal'})
        r=self.analyze(data)
        a=self.client.post(self.base+'/apply',headers=self.headers,json={'state':self.state,'research_id':r['id'],'suggestions':[0,4]})
        self.assertEqual(a.status_code,200,a.text)
        self.assertEqual(a.json()['outcomes'][0]['status'],'applied')
        self.assertGreaterEqual(a.json()['state']['timeline'][0]['start'],.3)
    def test_audio_research_recovers_missing_transcript_or_reports_uncertainty(self):
        from backend.trends import pipeline,youtube_trends
        from backend import cascade_llm
        from backend.editor.runtime import jobs_dir,load_json
        parts=self.url.split('/');pid,jid,index=parts[3],parts[5],int(parts[6])
        (jobs_dir()/jid/'clip_1.vtt').write_text('WEBVTT\n\n')
        user=load_json(jobs_dir()/jid/'owner.json')['user_id']
        video={'video_id':'abcdefghijk','title':'Editing example','url':'https://www.youtube.com/watch?v=abcdefghijk','channel':'Test','published_at':'2026-10-29T00:00:00Z'}
        for failed in [False,True]:
            with self.subTest(failed=failed),patch.object(youtube_trends,'get_trending_videos',side_effect=lambda query,limit:[video] if 'tutorial' not in query else []), \
                 patch.object(pipeline,'extract_tags',return_value={'pacing':'fast'}),patch.object(pipeline,'analyze_youtube_video',return_value={'tags':{'pacing':'fast'}}), \
                 patch.object(pipeline,'transcribe',side_effect=RuntimeError('Transcription service unavailable') if failed else None,return_value='A spoken reaction was recognized.') as transcribe, \
                 patch.object(cascade_llm,'structured_json',return_value=SimpleNamespace(data=fixtures.findings())) as synthesis:
                result=trends.collect(pid,jid,index,user,trends.Edit(**self.state),{'topic':'reaction editing','goal':'Improve the pacing'},lambda m:None)
            self.assertEqual(result['speech_evidence']['status'],'transcription_failed' if failed else 'research_transcript')
            transcribe.assert_called_once()
            self.assertIn('speech_evidence',synthesis.call_args.args[0])
            if failed:self.assertTrue(any(f['stage']=='transcription' for f in result['failures']))
