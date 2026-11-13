"""Local planner routing, follow-up tools, ownership and shared timing contracts."""
import base64
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from PIL import Image
from fastapi import HTTPException
from backend.editor import ai, local_ai
from backend.editor.models import Edit, Action
from backend.editor.advanced_models import Motion, AudioSegment, TimelineSpan, TextOverlay
from backend.editor.audio_assets import AudioStore
from backend.editor.reel import build_reel
from backend.editor.retiming import mapped_state


class LocalPlannerTests(unittest.TestCase):
    def payload(self):
        state=Edit(start=0,end=10,motion=[Motion(start=3,duration=.7,shake=.008)])
        image=Image.new('RGB',(96,54),'green');buffer=io.BytesIO();image.save(buffer,format='JPEG')
        return {'request':'Make this a high-energy Instagram Reel','state':state.model_dump(),
                'visual_frames':[{'at':3,'data':base64.b64encode(buffer.getvalue()).decode()}]}

    def test_default_is_local_with_bounded_images_and_no_paid_fallback(self):
        response=httpx.Response(200,json={'done':True,'message':{'content':'{"message":"Plan","observations":[{"frame_index":0,"description":"Visible reaction","importance":0.9,"activity":"high"}],"actions":[{"type":"high_energy_reel"},{"type":"composition","ratio":"9:16"}]}'}})
        with patch.dict(os.environ,{},clear=True), patch.object(local_ai.httpx,'Client') as factory, patch.object(ai,'structured_json') as cloud:
            factory.return_value.__enter__.return_value.post.return_value=response
            proposal=ai.request_edit(self.payload())
            cloud.assert_not_called()
            request=factory.return_value.__enter__.return_value.post.call_args
        self.assertEqual(request.args[0],'http://127.0.0.1:11434/api/chat')
        self.assertEqual(len(request.kwargs['json']['messages'][1]['images']),1)
        self.assertEqual(proposal.observations[0].at,3)
        self.assertEqual(proposal.actions[1].composition.ratio,'9:16')
        self.assertNotIn('visual_frames',request.kwargs['json']['messages'][1]['content'])

    def test_reel_contract_is_small_and_does_not_emit_unrequested_tools(self):
        payload=self.payload();payload['style_request']='high-energy-v1'
        result={'message':'Action-focused Reel','observations':[{'frame_index':0,'description':'A visible reaction','importance':.9,'activity':'high'}],
                'caption_animation':'pop','zoom_strength':1.3,'shake_strength':.006,'max_punch_ins':2}
        with patch.object(local_ai.httpx,'Client') as factory:
            factory.return_value.__enter__.return_value.post.return_value=httpx.Response(200,json={'done':True,'message':{'content':__import__('json').dumps(result)}})
            plan=local_ai.request_edit(payload)
            schema=factory.return_value.__enter__.return_value.post.call_args.kwargs['json']['format']
        self.assertNotIn('actions',schema['properties'])
        self.assertEqual([a.type for a in plan.actions],['high_energy_reel','composition'])
        self.assertEqual(plan.actions[0].max_punch_ins,2)
        self.assertEqual(plan.actions[0].zoom_strength,1.3)

    def test_failure_never_calls_paid_provider_or_logs_exception_values(self):
        with patch.dict(os.environ,{'CASCADE_EDITOR_PROVIDER':'ollama'}), patch.object(local_ai.httpx,'Client') as factory, patch.object(ai,'structured_json') as cloud, self.assertLogs(local_ai.logger,level='WARNING') as logs:
            factory.return_value.__enter__.return_value.post.side_effect=httpx.ConnectError('PRIVATE_TOKEN')
            with self.assertRaises(HTTPException) as caught: ai.request_edit(self.payload())
            cloud.assert_not_called()
        self.assertEqual(caught.exception.status_code,503)
        self.assertNotIn('PRIVATE_TOKEN',caught.exception.detail+' '.join(logs.output))

    def test_unknown_tools_and_nonlocal_endpoints_rejected(self):
        with self.assertRaises(ValueError):local_ai.LocalPlan.model_validate({'message':'bad','actions':[{'type':'shell'}]})
        with patch.dict(os.environ,{'CASCADE_EDITOR_OLLAMA_URL':'https://example.com'}), self.assertRaises(HTTPException):local_ai.runtime()

    def test_followups_change_existing_motion_instead_of_adding_duplicates(self):
        payload=self.payload();payload['request']='Less shake'
        with patch.object(local_ai.httpx,'Client',side_effect=AssertionError('No inference needed')):
            result=local_ai.request_edit(payload)
        self.assertEqual(result.actions[0].type,'motion_update')
        self.assertEqual(result.actions[0].motion.shake,.004)
        self.assertEqual(result.actions[0].motion.start,3)
        payload['request']='move that zoom earlier by 0.5 seconds'
        result=local_ai.request_edit(payload)
        self.assertEqual(result.actions[0].motion.start,2.5)
        payload['state']['motion'].append(Motion(start=6,duration=.5).model_dump())
        result=local_ai.request_edit(payload)
        self.assertEqual(result.actions,[])
        self.assertIn('Identify a zoom',result.unsupported[0])

    def test_incomplete_plan_is_not_an_applied_edit(self):
        with patch.object(local_ai.httpx,'Client') as factory, self.assertLogs(local_ai.logger,level='WARNING'):
            factory.return_value.__enter__.return_value.post.return_value=httpx.Response(200,json={'done':True,'done_reason':'length','message':{'content':'{}'}})
            with self.assertRaises(HTTPException) as caught:local_ai.request_edit(self.payload())
        self.assertEqual(caught.exception.status_code,502)


class OwnershipAndTimingTests(unittest.TestCase):
    def test_style_preserves_manual_tracks_and_reapplication_replaces_owned_events(self):
        with tempfile.TemporaryDirectory() as directory:
            audio=AudioStore(Path(directory));library=audio.library();track=next(a for a in library if a['name']=='Reel pulse')
            manual=Motion(start=1,duration=.4,scale_to=1.15)
            state=Edit(start=0,end=10,motion=[manual],text_overlays=[TextOverlay(start=2,duration=1,text='Manual title')],
                audio=[AudioSegment(id='a'*32,asset_id=track['id'],start=0,duration=10,volume=.12)])
            info={'has_video':True,'duration':10,'clip_title':'A conversation','scene_boundaries':[],
                  'cues':[{'start':.2,'end':2,'text':'Why now?'},{'start':3,'end':5,'text':'This is the key reaction.'},{'start':6,'end':9.5,'text':'Keep this whole ending.'}],
                  'editor_moments':[{'at':6,'description':'Visible reaction','importance':.95,'activity':'high'}]}
            result,report=build_reel(state,info,MagicMock(),audio,Action(type='high_energy_reel'),'Make a high-energy Reel; keep the entire duration')
            self.assertIn(manual,result.motion)
            self.assertEqual(result.text_overlays,state.text_overlays)
            self.assertEqual(result.audio[0],state.audio[0])
            self.assertTrue(result.reel.generated_motion)
            self.assertTrue(any('Visible moment' in row['message'] for row in report))
            again,_=build_reel(result,info,MagicMock(),audio,Action(type='high_energy_reel'),'Make a high-energy Reel; keep the entire duration')
            self.assertEqual(len(again.motion),len(result.motion))
            self.assertEqual(again.motion.count(manual),1)
            self.assertEqual(len(again.audio),len(result.audio))
            self.assertEqual(again.audio[0],state.audio[0])

    def test_retimed_audio_leading_trim_preserves_source_offset(self):
        segment=AudioSegment(id='a'*32,asset_id='aud-'+'b'*32,start=0,duration=10,offset=2)
        state=Edit(start=5,end=10,timeline=[TimelineSpan(start=5,end=10)],audio=[segment])
        mapped,_,_=mapped_state(state,{'cues':[],'duration':10})
        self.assertEqual(mapped.audio[0].start,0)
        self.assertEqual(mapped.audio[0].offset,7)
        self.assertEqual(mapped.audio[0].duration,5)
