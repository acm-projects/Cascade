"""Provider routing and proposal safety, with no paid/network AI calls."""
import os
import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
from fastapi import HTTPException
from backend.editor import ai
from backend.editor.actions import apply_actions
from backend.editor.models import Edit
from backend.cascade_llm import StructuredResult, LLMConfigError
from backend.cascade_llm import structured


class EditorAITests(unittest.TestCase):
    def result(self):
        return StructuredResult({'message':'Captions yellow.', 'actions':[
            {'type':'caption_color','color':'#ffff00'}]}, 1, 1)

    def test_each_provider_works_with_only_its_own_key(self):
        for provider in ('anthropic', 'openai'):
            env={'LLM_PROVIDER':provider,'CASCADE_EDITOR_PROVIDER':'',
                 'ANTHROPIC_API_KEY':'test' if provider=='anthropic' else '',
                 'OPENAI_API_KEY':'test' if provider=='openai' else ''}
            with self.subTest(provider=provider), patch.dict(os.environ,env), patch.object(
                structured,'make_client',return_value=object()) as client, patch.object(
                structured,'_'+provider,return_value=self.result()) as call:
                proposal=ai.request_edit({'request':'make captions yellow'})
                state=apply_actions(Edit(start=0,end=3),proposal.actions,3)
                self.assertEqual(state.captions.color,'#ffff00')
                client.assert_called_once_with(provider)
                self.assertIn('make captions yellow',call.call_args.args[2])

    def test_override_is_per_call_and_does_not_change_global_provider(self):
        with patch.dict(os.environ,{'LLM_PROVIDER':'openai','CASCADE_EDITOR_PROVIDER':'anthropic'}), patch.object(
            structured,'make_client',return_value=object()) as client, patch.object(
            structured,'_anthropic',return_value=self.result()), patch.object(
            structured,'_openai',return_value=self.result()):
            ai.request_edit({})
            client.assert_called_with('anthropic')
            self.assertEqual(os.environ['LLM_PROVIDER'],'openai')
            structured.structured_json('another concurrent feature',{},name='test')
            client.assert_called_with('openai')

    def test_missing_keys_and_invalid_provider_fail_without_leaking_details(self):
        for provider in ('anthropic','openai','invalid'):
            with self.subTest(provider=provider), patch.dict(os.environ,{
                'CASCADE_EDITOR_PROVIDER':provider,'ANTHROPIC_API_KEY':'','OPENAI_API_KEY':''}):
                with self.assertRaises(HTTPException) as error:
                    ai.request_edit({})
                self.assertEqual(error.exception.status_code,503)
        with patch.object(ai,'structured_json',side_effect=LLMConfigError('private')):
            with self.assertRaises(HTTPException) as error:ai.request_edit({})
            self.assertNotIn('private',error.exception.detail)

    def test_invalid_output_never_becomes_an_edit(self):
        for data in ({'message':'ok','actions':[{'type':'shell'}]}, {'message':'ok','actions':'broken'}, {}):
            with self.subTest(data=data), patch.object(ai,'structured_json',return_value=StructuredResult(data,0,0)):
                with self.assertRaises(HTTPException) as error:ai.request_edit({})
                self.assertEqual(error.exception.status_code,502)
                self.assertEqual(error.exception.detail,'The editing AI returned an invalid response. Try rephrasing.')

    def test_schema_requires_all_properties_and_disallows_unknown_actions(self):
        def check(node):
            if isinstance(node,dict):
                if node.get('type')=='object':
                    self.assertEqual(set(node['required']),set(node['properties']))
                    self.assertFalse(node['additionalProperties'])
                for value in node.values():check(value)
            elif isinstance(node,list):
                for value in node:check(value)
        schema=ai.proposal_schema();check(schema)
        action=schema['$defs']['Action']
        self.assertIn({'type':'null'},action['properties']['seconds']['anyOf'])

    def test_openai_adapter_keeps_request_storage_disabled(self):
        client=MagicMock()
        client.responses.create.return_value=SimpleNamespace(status='completed', output=[
            SimpleNamespace(type='message',content=[SimpleNamespace(type='output_text',text='{"message":"ok","actions":[]}')])])
        structured._openai(client,'fixture-model','context',ai.proposal_schema(),'editor_actions',[],'low',4096)
        self.assertFalse(client.responses.create.call_args.kwargs['store'])
