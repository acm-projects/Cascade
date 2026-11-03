"""My Style: style sheets built from the user's own reference reels, offline (no Gemini, Ollama, yt-dlp or HyperFrames calls)."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.editor.director_models import Analysis
from backend.editor.models import ChatInput, Edit
from backend.editor.style_profile_models import ProfileChoices, ReferenceInfo, StyleProfile

SFX = [{'id': 'aud-'+c*32, 'kind': 'sfx', 'name': n, 'tags': [], 'duration': .6} for c, n in (('b', 'Impact hit'), ('c', 'Air whoosh'))]


class FakeAudio:
    def library(self):
        return [{'id': 'aud-'+'a'*32, 'kind': 'music', 'name': 'Reel pulse', 'tags': [], 'duration': 30}, *SFX]


class FakeStock:
    def search(self, query): return {'results': []}


def profile(**choices):
    return StyleProfile(id='f'*32, status='approved', references=[ReferenceInfo(label='a', duration=20, cuts_per_minute=30)],
                        choices=ProfileChoices(name='Red pop', **choices))


class MyStyleTests(unittest.TestCase):
    def test_style_sheet_drives_captions_words_sound_and_hook_card(self):
        from backend.editor.director_recipes import apply_plan
        from backend.editor.my_style import plan_from_profile
        analysis = Analysis(genre='podcast_interview', emphasis=[{'text': 'clapping', 'at': 5}, {'text': 'noticing', 'at': 12}],
                            key_moments=[{'at': 4, 'importance': .9}, {'at': 14, 'importance': .7}])
        cues = [{'start': 0, 'end': 2.5, 'text': 'Encourage yourself always.'}, {'start': 5, 'end': 9, 'text': 'when no one else is clapping'},
                {'start': 11, 'end': 20, 'text': 'validate yourself when no one else is noticing'}]
        plan = plan_from_profile(analysis, profile(accent='#e50914', caption_words=2, transitions='flash', glitch_accents=True, words_behind=True))
        state, notes = apply_plan(Edit(start=0, end=20), plan, {'cues': cues}, FakeStock(), FakeAudio())
        cap = state.captions
        self.assertEqual((cap.highlight, cap.max_words, cap.emphasis), ('#e50914', 2, ['clapping', 'noticing']))
        card = next(e for e in state.stylize.events if e.kind == 'motion_card')
        self.assertEqual((card.text, card.color, card.start), ('Encourage yourself always', '#e50914', 0))
        self.assertTrue(all(e.behind for e in state.stylize.events if e.kind == 'text'))
        self.assertEqual(sum(e.kind == 'glitch' for e in state.stylize.events), 2)
        self.assertTrue(any(a.track == 'sfx' for a in state.audio))
        self.assertTrue(any('HyperFrames hook card' in n for n in notes))

    def test_turning_things_off_in_the_sheet_is_respected(self):
        from backend.editor.director_recipes import apply_plan
        from backend.editor.my_style import plan_from_profile
        analysis = Analysis(emphasis=[{'text': 'growth', 'at': 3}], key_moments=[{'at': 3, 'importance': 1}])
        plan = plan_from_profile(analysis, profile(punch_ins=False, sound_fx=False, motion_cards=False, glitch_accents=False, music='none'))
        state, _ = apply_plan(Edit(start=0, end=15), plan, {'cues': []}, FakeStock(), FakeAudio())
        self.assertEqual((state.motion, state.audio), ([], []))
        self.assertFalse(any(e.kind in ('motion_card', 'glitch') for e in state.stylize.events))

    def test_measured_defaults_without_any_model(self):
        from backend.editor import style_reference
        fast = ReferenceInfo(label='a', duration=15, cuts_per_minute=60, flash_bursts=4, saturation=.5, accent='#ff2020')
        slow = ReferenceInfo(label='b', duration=30, cuts_per_minute=4, mono=.9)
        with patch('backend.editor.gemini_planner.configured', return_value=False), \
                patch('backend.editor.director._local', side_effect=OSError()):
            choices, how = style_reference.choose([fast, fast, slow], [])
        self.assertEqual((choices.pacing, choices.accent, choices.transitions, how[:12]), ('fast', '#ff2020', 'flash', 'measurements'))

    def test_measure_reads_a_real_video(self):
        from backend.editor.style_reference import measure
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'ref.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x568:rate=25:duration=4', '-pix_fmt', 'yuv420p', str(path)], check=True)
            info, frames = measure(path, 'test pattern')
        self.assertEqual((info.label, round(info.duration), len(frames)), ('test pattern', 4, 6))
        self.assertGreater(info.saturation, .2)

    def test_links_must_be_public_social_urls_and_drafts_cannot_be_used(self):
        from backend.editor import style_profile, style_reference
        with self.assertRaises(HTTPException):
            style_reference.download('file:///etc/passwd', '/tmp')
        with tempfile.TemporaryDirectory() as folder, patch.object(style_profile, 'folder', return_value=Path(folder)):
            draft = style_profile.save('user', profile().model_copy(update={'status': 'draft'}))
            with self.assertRaises(HTTPException) as raised:
                style_profile.approved('user', draft.id)
            self.assertEqual(raised.exception.status_code, 409)
            with self.assertRaises(HTTPException):
                style_profile.load('user', '../../etc')
        self.assertEqual(ChatInput(state=Edit(start=0, end=1), message='edit', style_id='f'*32).style_id, 'f'*32)

    def test_motion_card_page_escapes_text_and_overlay_composites_alpha(self):
        import numpy as np
        from PIL import Image
        from backend.editor import motion_cards
        from backend.editor.advanced_models import StyleEvent
        html = motion_cards.page('<b>stop</b> waiting', 540, 960, 1.6, '#e50914', 'impact')
        self.assertIn('&lt;B&gt;STOP&lt;/B&gt;', html)
        self.assertNotIn('<b>', html)
        event = StyleEvent(start=1, duration=.1, kind='motion_card', text='hi')
        with tempfile.TemporaryDirectory() as folder:
            png = Path(folder)/'frame_000001.png'
            rgba = np.zeros((4, 4, 4), np.uint8); rgba[0, 0] = (255, 0, 0, 255)
            Image.fromarray(rgba).save(png)
            with patch.object(motion_cards, 'frames', return_value=[png]):
                cards = motion_cards.Cards([event], 4, 4, '#ffffff', folder)
            out = cards.overlay(np.full((4, 4, 3), 10, np.float32), 1.01)
        self.assertEqual((out[0, 0].tolist(), out[1, 1].tolist()), ([255, 0, 0], [10, 10, 10]))


if __name__ == '__main__':
    unittest.main()
