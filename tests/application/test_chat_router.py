"""The AI picks the Editor chat's path (backend/editor/chat_router.py); no keyword routing is left."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from backend.cascade_llm.clients import LLMConfigError
from backend.editor import chat_router
from backend.editor.models import AIEditRef, Edit, Message


def body(message, state=None, research_id=None, chat=()):
    return SimpleNamespace(message=message, state=state or Edit(start=0, end=10), research_id=research_id, chat=list(chat))


def answer(route, reason='fits'):
    return patch('backend.cascade_llm.structured_json', return_value=SimpleNamespace(data={'route': route, 'reason': reason}))


class Router(unittest.TestCase):
    video = {'has_video': True}

    def test_the_apps_own_state_decides_some_turns_without_asking(self):
        edited = Edit(start=0, end=10, ai_edit=AIEditRef(version='v001', duration=9))
        self.assertEqual(chat_router.fixed(body('x', research_id='a'*32), self.video, None), 'trends')
        self.assertEqual(chat_router.fixed(body('edit this clip'), {'has_video': False}, None), 'changes')
        self.assertEqual(chat_router.fixed(body('make the captions yellow', edited), self.video, None), 'finished_edit')
        self.assertEqual(chat_router.fixed(body('render'), self.video, object()), 'storyboard')
        self.assertIsNone(chat_router.fixed(body('make it flashy'), self.video, None))

    def test_the_ai_picks_the_path_whatever_the_wording(self):
        # The same idea in two wordings used to take two different keyword paths.
        for message in ('make it flashy', 'make it pop like the stuff that is popular right now'):
            with answer('trends') as call:
                self.assertEqual(chat_router.choose(body(message), self.video), 'trends')
            prompt, schema = call.call_args.args
            self.assertIn(message, prompt)
            self.assertEqual(schema['properties']['route']['enum'], list(chat_router.ROUTES))
            self.assertEqual(call.call_args.kwargs['effort'], 'low')

    def test_recent_chat_and_clip_details_go_with_the_message(self):
        history = [Message(role='user', text='make a reel'), Message(role='assistant', text='Done')]
        with answer('changes') as call:
            chat_router.choose(body('now shorter', chat=history), {**self.video, 'clip_title': 'Teddy'})
        prompt = call.call_args.args[0]
        self.assertIn('make a reel', prompt); self.assertIn('Teddy', prompt)

    def test_a_failed_or_odd_answer_falls_back_to_the_general_planner(self):
        with patch('backend.cascade_llm.structured_json', side_effect=RuntimeError('timeout')):
            self.assertEqual(chat_router.choose(body('make it flashy'), self.video), 'changes')
        with answer('delete_everything'):
            self.assertEqual(chat_router.choose(body('make it flashy'), self.video), 'changes')

    def test_no_openai_key_is_said_plainly(self):
        with patch('backend.cascade_llm.structured_json', side_effect=LLMConfigError('no key')), self.assertRaises(HTTPException) as error:
            chat_router.choose(body('make it flashy'), self.video)
        self.assertEqual(error.exception.status_code, 503)

    def test_a_fan_edit_with_nothing_specific_named_is_a_full_fan_edit(self):
        from backend.editor.style_requests import parse_request
        self.assertIsNone(parse_request('make it look sick'))
        self.assertEqual(parse_request('make it look sick', force=True)['type'], 'preset')


if __name__ == '__main__':
    unittest.main()
