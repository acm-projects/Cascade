"""Motion cards: HyperFrames installed ahead of time (item 15) and a skipped card is told to the user (item 16)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.editor import motion_cards, notices, stylize
from backend.editor.advanced_models import StyleEvent

CARD = StyleEvent(start=0, duration=1.5, kind='motion_card', text='Wait for it')


class MotionCardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)

    def test_the_setup_install_is_used_before_npx(self):
        with patch.dict('os.environ', {}, clear=False) as env:
            env.pop('CASCADE_HYPERFRAMES', None)
            with patch.object(motion_cards, 'TOOLS', self.cache):
                (self.cache/'.bin').mkdir(); (self.cache/'.bin'/'hyperframes').write_text('')
                self.assertEqual(motion_cards.command(), [str(self.cache/'.bin'/'hyperframes')])

    def test_gsap_comes_from_the_setup_install_not_a_cdn(self):
        gsap = self.cache/'gsap.min.js'; gsap.write_text('/* gsap */')
        with patch.object(motion_cards, 'GSAP', gsap):
            self.assertIn('<script src="gsap.min.js">', motion_cards.page('Big news', 720, 1280, 1.5, '#ff0000', 'impact'))
        with patch.object(motion_cards, 'GSAP', self.cache/'missing.js'):
            self.assertIn(motion_cards.GSAP_CDN, motion_cards.page('Big news', 720, 1280, 1.5, '#ff0000', 'impact'))

    def test_a_card_left_out_because_hyperframes_is_missing_is_told_to_the_user(self):
        with patch.object(motion_cards, 'command', return_value=None), notices.collect() as notes:
            self.assertEqual(motion_cards.frames(CARD, 64, 64, '#ff0000', self.cache), [])
        self.assertEqual(len(notes), 1)
        self.assertIn('"Wait for it" was left out', notes[0]); self.assertIn("isn't installed", notes[0])

    def test_a_card_that_fails_to_render_is_told_to_the_user(self):
        with patch.object(motion_cards, 'command', return_value=['false']), notices.collect() as notes:
            self.assertEqual(motion_cards.frames(CARD, 64, 64, '#ff0000', self.cache), [])
        self.assertIn("couldn't be drawn", notes[0])

    def test_notes_only_reach_someone_collecting_them(self):
        notices.add('nobody is listening')   # no error, nothing kept
        with notices.collect() as outer:
            with notices.collect() as inner:
                notices.add('left out'); notices.add('left out')
        self.assertEqual(inner, ['left out']); self.assertEqual(outer, ['left out'])

    def test_a_render_that_left_something_out_is_not_cached(self):
        source = self.cache/'clip.mp4'; source.write_bytes(b'video')
        state = type('State', (), {'stylize': type('S', (), {'events': [CARD], 'model_dump': lambda self: {'card': 1}})()})()

        def render(source, output, style, mattes):
            Path(output).write_bytes(b'rendered'); notices.add('card left out')
        with patch.object(stylize, 'render', side_effect=render) as rendered, notices.collect() as notes:
            for _ in range(2):
                with stylize.stylized(source, state, self.cache/'stylize') as path:
                    self.assertEqual(Path(path).read_bytes(), b'rendered')
        self.assertEqual(rendered.call_count, 2)   # the second render tries the card again
        self.assertEqual(notes, ['card left out'])
        self.assertEqual(list((self.cache/'stylize').glob('*.mp4')), [])


if __name__ == '__main__':
    unittest.main()
