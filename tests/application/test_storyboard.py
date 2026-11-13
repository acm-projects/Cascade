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
        self.assertEqual((state.composition.ratio, state.composition.mode), ('9:16', 'fit'))
        self.assertEqual(next(e.start for e in state.stylize.events if e.kind == 'motion_card'), 1.9)  # opens the first kept moment
        self.assertTrue(all(not e.behind for e in state.stylize.events if e.kind == 'text'))
        self.assertEqual(sorted(a.track for a in state.audio), ['music', 'sfx', 'sfx'])
        kinds = [e.kind for e in state.stylize.events]
        self.assertIn('flash', kinds); self.assertIn('motion_card', kinds)
        self.assertEqual(next(e.text for e in state.stylize.events if e.kind == 'motion_card'), 'Talking to a cat')
        self.assertIn('cut 1 line(s) and pauses (−1.9s)', notes)

    def test_rendering_again_replaces_the_last_storyboard_and_keeps_manual_edits(self):
        from backend.editor.advanced_models import AudioSegment, Motion
        from backend.editor.storyboard_apply import apply
        manual_audio = AudioSegment(id='d'*32, asset_id='aud-'+'a'*32, track='music', start=0, duration=2)
        manual_motion = Motion(start=8, duration=.5)
        first, _ = apply(Edit(start=0, end=9, motion=[manual_motion], texts={'0': 'mine'}), board(), {'cues': CUES}, FakeStock(), FakeAudio())
        second, _ = apply(first, board().model_copy(update={'look': 'natural', 'hook': 'New hook', 'beats': [b.model_copy(update={'keep': True}) for b in board().beats]}),
                          {'cues': CUES}, FakeStock(), FakeAudio())
        self.assertEqual([e.text for e in second.stylize.events if e.kind == 'motion_card'], ['New hook'])
        self.assertEqual(sum(e.kind == 'flash' for e in second.stylize.events), 1)
        self.assertEqual(sum(a.track == 'sfx' for a in second.audio), 2)
        self.assertEqual(second.motion.count(manual_motion), 1)
        self.assertEqual(second.texts, {'0': 'mine', '2': 'she has no idea'})
        self.assertEqual(len(apply(Edit(start=0, end=9, audio=[manual_audio]), Storyboard(beats=[{'n': 1}]), {'cues': CUES}, FakeStock(), FakeAudio())[0].audio), 1)

    def test_pauses_are_cut_even_when_every_line_stays(self):
        from backend.editor.storyboard_apply import _cuts
        from backend.editor.storyboard_models import Beat
        cues = [{'start': 0, 'end': 2, 'text': 'a'}, {'start': 2.1, 'end': 3, 'text': 'b'}, {'start': 6, 'end': 8, 'text': 'c'}]
        spans = _cuts(Edit(start=0, end=8), [Beat(n=0), Beat(n=1), Beat(n=2)], cues)
        self.assertEqual([(s.start, s.end) for s in spans], [(0, 3.1), (5.9, 8)])

    def test_plan_falls_back_to_local_then_transcript_and_says_why(self):
        lines = storyboard._lines({'cues': CUES}, Edit(start=0, end=9))
        with patch.object(claude_code, 'ask', side_effect=claude_code.UsageLimit('limit reached')), \
                patch('backend.editor.director._local', side_effect=OSError()):
            planned, planner = storyboard._plan('make it moody', [], lines, 'make it moody')
        self.assertIn('usage limit', planner)
        self.assertEqual((planned.look, len(planned.beats)), ('bw', 3))
        complete = storyboard._complete(Storyboard(beats=[{'n': 2}, {'n': 99}]), lines)
        self.assertEqual([b.n for b in complete.beats], [0, 1, 2])

    def test_a_long_fallback_reason_still_saves_the_storyboard(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(storyboard, 'path', return_value=Path(folder)/'board.json'), \
                patch.object(storyboard, '_frames', return_value=[]), patch.object(claude_code, 'ask', side_effect=HTTPException(503, 'x'*400)), \
                patch('backend.editor.director._local', side_effect=OSError()):
            saved = storyboard.create('p', 'j', 0, 'u', 'clip.mp4', Edit(start=0, end=9), {'cues': CUES}, 'edit this')
            self.assertEqual(saved.planner[:14], 'transcript onl')
            self.assertEqual(storyboard.pending('p', 'j', 0, 'u').id, saved.id)

    def test_only_reel_requests_become_storyboards(self):
        from backend.editor.storyboard_chat import REEL
        self.assertTrue(REEL.search('Make this a high-energy Reel') and REEL.search('cut this for YouTube Shorts'))
        for message in ('Add short B-roll shots', 'make the captions yellow', 'shorten the intro'):
            self.assertIsNone(REEL.search(message), message)

    def test_chat_routing_render_cancel_and_notes(self):
        self.assertTrue(storyboard.RENDER.search('render') and storyboard.RENDER.search('Looks good!'))
        self.assertFalse(storyboard.RENDER.search('render beat 3 bigger'))
        self.assertTrue(storyboard.CANCEL.search('discard'))
        text = storyboard.describe(board(planner='Claude (your Claude subscription)'))
        self.assertIn('3 beats below, 1 cut. Planned by Claude', text)

    def test_claude_code_never_sees_an_api_key(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-ant-secret', 'ANTHROPIC_AUTH_TOKEN': 't', 'PATH': '/bin'}):
            env = claude_code.subscription_env()
        self.assertNotIn('ANTHROPIC_API_KEY', env); self.assertNotIn('ANTHROPIC_AUTH_TOKEN', env)
        self.assertEqual(env['PATH'], '/bin')

    def test_claude_code_requires_a_subscription_sign_in(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder)/'claude'; fake.write_text('#!/bin/sh\necho \'{"loggedIn": true, "authMethod": "api_key"}\'\n'); fake.chmod(0o755)
            with patch.dict(os.environ, {'CASCADE_CLAUDE_BIN': str(fake), 'CASCADE_EDITOR_CLAUDE': ''}):
                self.assertEqual(claude_code.signed_in(), '')
                with self.assertRaises(HTTPException) as raised:
                    claude_code.ask('system', 'prompt')
        self.assertIn('not signed in with a Claude subscription', raised.exception.detail)


if __name__ == '__main__':
    unittest.main()
