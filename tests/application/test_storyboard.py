"""Storyboard-first AI Editor chat, offline: Claude Code, Ollama and the renderer are never called."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.editor import claude_code, storyboard
from backend.editor.models import Edit
from backend.editor.storyboard_models import SavedStoryboard, Storyboard

CUES = [{'start': 0, 'end': 2, 'text': 'Oh'}, {'start': 2, 'end': 5, 'text': 'Talking to a cat'}, {'start': 5, 'end': 9, 'text': 'She feels lucky'}]
SFX = [{'id': 'aud-'+c*32, 'kind': k, 'name': n, 'tags': [], 'duration': d} for c, k, n, d in
       (('a', 'music', 'Quiet reflection', 30), ('b', 'sfx', 'Impact hit', .55), ('c', 'sfx', 'Air whoosh', .65))]


class FakeAudio:
    def library(self): return SFX


class FakeStock:
    def search(self, query): return {'results': []}


def board(**extra):
    return SavedStoryboard(id='a'*32, request='make it moody', title='Moody', look='bw', music='Quiet reflection', caption_size=72, hook='Talking to a cat',
                           beats=[{'n': 0, 'keep': False}, {'n': 1, 'zoom': 'push', 'sfx': 'whoosh'},
                                  {'n': 2, 'caption': 'she has no idea', 'emphasis': 'lucky', 'effect': 'flash', 'sfx': 'hit'}], **extra)


class StoryboardTests(unittest.TestCase):
    def test_render_applies_exactly_the_storyboard(self):
        from backend.editor.storyboard_apply import apply
        state, notes = apply(Edit(start=0, end=9), board(), {'cues': CUES}, FakeStock(), FakeAudio())
        self.assertEqual(state.texts, {'2': 'she has no idea'})
        self.assertEqual((state.captions.size, [(s.start, s.end) for s in state.timeline]), (72, [(1.9, 9)]))
        self.assertEqual([(m.start, m.scale_from) for m in state.motion], [(2, 1)])
        self.assertEqual(sorted(a.track for a in state.audio), ['music', 'sfx', 'sfx'])
        kinds = [e.kind for e in state.stylize.events]
        self.assertIn('flash', kinds); self.assertIn('motion_card', kinds)
        self.assertEqual(next(e.text for e in state.stylize.events if e.kind == 'motion_card'), 'Talking to a cat')
        self.assertIn('cut 1 line(s)', notes)

    def test_plan_falls_back_to_local_then_transcript_and_says_why(self):
        lines = storyboard._lines({'cues': CUES}, Edit(start=0, end=9))
        with patch.object(claude_code, 'ask', side_effect=claude_code.UsageLimit('limit reached')), \
                patch('backend.editor.director._local', side_effect=OSError()):
            planned, planner = storyboard._plan('make it moody', [], lines, 'make it moody')
        self.assertIn('usage limit', planner)
        self.assertEqual((planned.look, len(planned.beats)), ('bw', 3))
        complete = storyboard._complete(Storyboard(beats=[{'n': 2}, {'n': 99}]), lines)
        self.assertEqual([b.n for b in complete.beats], [0, 1, 2])

    def test_chat_routing_render_cancel_and_notes(self):
        self.assertTrue(storyboard.RENDER.search('render') and storyboard.RENDER.search('Looks good!'))
        self.assertFalse(storyboard.RENDER.search('render beat 3 bigger'))
        self.assertTrue(storyboard.CANCEL.search('discard'))
        text = storyboard.describe(board(planner='Claude (your Claude subscription)'))
        self.assertIn('Beat 0: CUT', text); self.assertIn('Beat 2: "she has no idea", BIG LUCKY', text)

    def test_claude_code_never_sees_an_api_key(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-ant-secret', 'ANTHROPIC_AUTH_TOKEN': 't', 'PATH': '/bin'}):
            env = claude_code.subscription_env()
        self.assertNotIn('ANTHROPIC_API_KEY', env); self.assertNotIn('ANTHROPIC_AUTH_TOKEN', env)
        self.assertEqual(env['PATH'], '/bin')

    def test_claude_code_requires_a_subscription_sign_in(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder)/'claude'; fake.write_text('#!/bin/sh\necho \'{"loggedIn": true, "authMethod": "api_key"}\'\n'); fake.chmod(0o755)
            with patch.dict(os.environ, {'CASCADE_CLAUDE_BIN': str(fake)}):
                self.assertEqual(claude_code.signed_in(), '')
                with self.assertRaises(HTTPException) as raised:
                    claude_code.ask('system', 'prompt')
        self.assertIn('not signed in with a Claude subscription', raised.exception.detail)


if __name__ == '__main__':
    unittest.main()
