"""Editor provider isolation, strict plans, real effect pixels, and trim safety; no network."""
import base64
import os
import unittest
from unittest.mock import patch
from fastapi import HTTPException
import numpy as np
from backend.editor import openai_edit, ai, storyboard
from backend.cascade_llm import StructuredResult
from backend.editor.ai_edit.cinema import accents, director, plan as plans, planner

class OpenAIEditing(unittest.TestCase):
    def test_actual_image_inputs_style_guide_and_provider_isolation(self):
        with patch.dict(os.environ, {'LLM_PROVIDER':'anthropic'}), patch.object(openai_edit,'structured_json',return_value=StructuredResult({},0,0)) as call:
            openai_edit.ask('system','context',{},[('frame.jpg',b'jpeg')])
            self.assertEqual(call.call_args.kwargs['provider'],'openai')
            self.assertEqual(call.call_args.kwargs['images'],[{'media_type':'image/jpeg','data':base64.b64encode(b'jpeg').decode()}])
            self.assertIn('Kinetic conversation',call.call_args.args[0])
            self.assertEqual(os.environ['LLM_PROVIDER'],'anthropic')

    def test_strict_schema_keeps_fields_named_title_and_forbids_extra_properties(self):
        schema=openai_edit.strict_schema(plans.CinemaPlan)
        self.assertIn('title',schema['properties'])
        def walk(node):
            if isinstance(node,dict):
                if node.get('type')=='object':
                    self.assertFalse(node['additionalProperties'])
                    self.assertEqual(set(node['required']),set(node['properties']))
                for v in node.values(): walk(v)
            elif isinstance(node,list):
                for v in node:walk(v)
        walk(schema)

    def test_unavailable_openai_is_not_a_silent_rules_edit(self):
        prep={'words':[{'i':0,'w':'Hello.','s':0,'e':1}], 'duration':2,'cuts':[],'sheets':[]}
        with patch.dict(os.environ, {'CASCADE_EDIT_PLANNER':'auto'}), patch.object(openai_edit,'ask',side_effect=HTTPException(502,'Try again')):
            with self.assertRaises(planner.Unavailable):planner.plan_edit('edit this', '.', prep, [[0,2]], [])

    def test_invalid_trim_is_rejected_before_render(self):
        words=[{'i':i,'w':'word','s':i,'e':i+.8} for i in range(8)]
        answer={'story':[{'from_word':0,'to_word':7}]}
        with self.assertRaisesRegex(ValueError,'usable source ranges'):
            director.direct(lambda p:answer,'request',words,windows=[[2,5]])

    def test_word_alignment_overshoot_is_clamped_only_at_physical_media_end(self):
        prep={'words':[{'i':0,'w':'Hello.','s':0,'e':1.04}], 'duration':1,'cuts':[],'sheets':[]}
        answer={'story':[{'from_word':0,'to_word':0}]}
        with patch.dict(os.environ, {'CASCADE_EDIT_PLANNER':'openai'}), patch.object(openai_edit,'ask',return_value=answer):
            plan,who=planner.plan_edit('edit this', '.', prep, [[0,1]], [])
            self.assertEqual(len(plan.story),1)
            with self.assertRaises(planner.Unavailable):planner.plan_edit('edit this', '.', prep, [[0,.9]], [])

    def test_accents_drop_cut_words_and_reject_too_dense_spacing(self):
        words=[{'i':i,'w':'word','s':i,'e':i+.8} for i in range(8)]
        plan=plans.CinemaPlan(story=[{'from_word':0,'to_word':7}],drop=[[2,2]],accents=[{'word':i,'kind':'ripple'} for i in (0,1,2,4,99)])
        plans.check(plan,words)
        self.assertEqual([a.word for a in plan.accents],[0,4])

class RenderAccents(unittest.TestCase):
    def test_all_accents_render_and_resolve_without_edge_wrap(self):
        y,x=np.mgrid[:180,:320]
        frame=np.stack((x%256,y%256,(x+y)%256),axis=-1).astype(np.uint8)
        previous=np.full_like(frame,90)
        for kind in ('whip','rgb','ink','ripple'):
            with self.subTest(kind=kind):
                result=accents.apply(frame,previous,kind,.4)
                self.assertEqual(result.dtype,np.uint8);self.assertEqual(result.shape,frame.shape)
                self.assertGreater(np.abs(result.astype(float)-frame).mean(),.1)
                np.testing.assert_array_equal(accents.apply(frame,previous,kind,1),frame)
                np.testing.assert_array_equal(result,accents.apply(frame,previous,kind,.4))
        np.testing.assert_array_equal(accents.apply(frame,previous,'ink',0),previous)

    def test_photo_card_and_drawn_circle_are_real_pixels(self):
        frame=np.full((180,320,3),80,np.uint8)
        card=accents.card(frame,.5,'water')
        self.assertGreater(np.abs(card.astype(float)-frame).mean(),1)
        accents.circle(frame,.4,(255,220,60))
        self.assertGreater(frame.max(),80)
