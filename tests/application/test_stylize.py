import unittest

import numpy as np

from backend.editor.advanced_models import StyleEvent, StyleOptions
from backend.editor.models import Edit
from backend.editor.style_requests import parse_request, proposal_for
from backend.editor.stylize import apply_events, plan_preset


class StyleRequestTests(unittest.TestCase):
    def test_routes_style_requests_without_a_model(self):
        request = parse_request('make this a spiderman fan edit, edited by Manila')
        self.assertEqual(request['type'], 'preset')
        self.assertEqual(request['options'].end_card, 'Cascade')  # always Cascade
        self.assertEqual(parse_request('make the background gray and keep him in color')['options'].effects, ['color_pop'])
        self.assertEqual(parse_request('remove the fan edit')['type'], 'clear')
        timed = parse_request('add a glitch from 2 to 3 seconds')
        self.assertEqual((timed['events'][0].kind, timed['events'][0].start, timed['events'][0].duration), ('glitch', 2, 1))

    def test_text_fonts_and_extra_footage(self):
        ww2 = parse_request('make a ww2 fan edit with crazy text and other clips of soldiers and tanks, edited by Manila')['options']
        self.assertEqual((ww2.palette, ww2.texts, ww2.broll_query, ww2.end_card), ('mono', True, 'soldiers and tanks', 'Cascade'))
        timed = parse_request('add text "D-DAY" from 2 to 4 seconds in a stencil font')['events'][0]
        self.assertEqual((timed.kind, timed.text, timed.font, timed.start), ('text', 'D-DAY', 'war', 2))
        self.assertIsNone(parse_request('add b-roll of explosions'))  # regular B-roll planner
        from backend.editor.style_text import apply_text, plan_text
        words = plan_text(Edit(start=0, end=10), [{'start': 0, 'end': 9, 'text': 'I was shot three times'}], [0, 1, 2, 3, 4, 5, 6, 7], 'mono')
        self.assertEqual([e.text for e in words], ['THREE', 'TIMES'])
        frame = np.zeros((90, 160, 3), np.float32)
        out = apply_text(frame, 1.2, [(0, words[0].model_copy(update={'behind': False}))], 'mono', lambda t, w, h: np.zeros((h, w), np.float32), 0)
        self.assertGreater(float(out.max()), 200)

    def test_leaves_other_requests_to_the_planner(self):
        for message in ('make captions yellow', 'trim the first 3 seconds', 'add music', 'set the caption background to black'):
            self.assertIsNone(parse_request(message), message)

    def test_preset_is_beat_synced_inside_the_trim(self):
        state = Edit(start=4, end=12)
        style = plan_preset(state, {'scene_boundaries': [6.0], 'style_beats': []}, StyleOptions(end_card='Manila'))
        self.assertTrue(all(4 <= e.start and e.start+e.duration <= 12.001 for e in style.events))
        self.assertEqual(style.events[-1].kind, 'title_card')
        self.assertTrue({'bg_swap', 'color_pop', 'zoom_blur'} <= {e.kind for e in style.events})
        self.assertEqual(proposal_for({'type': 'preset', 'options': StyleOptions()}).actions[0].type, 'style_preset')

    def test_color_pop_keeps_subject_color(self):
        frame = np.zeros((40, 60, 3), np.float32); frame[..., 0] = 200
        matte = np.zeros((40, 60), np.float32); matte[:, :30] = 1
        out = apply_events(frame, .1, [(0, StyleEvent(start=0, duration=1, kind='color_pop'))], 'spider', lambda t, w, h: matte, 0)
        self.assertAlmostEqual(float(out[0, 0, 0]), 200, places=3)
        self.assertAlmostEqual(float(out[0, 50, 0]), float(out[0, 50, 1]), places=3)


class StyleChatRenderTests(unittest.TestCase):
    """Real chat route and MP4 export; the SAM matte model is replaced by a fixed half-frame matte."""
    @classmethod
    def setUpClass(cls):
        from tests.application import test_editor
        cls.fixture = test_editor.EditorTests
        cls.fixture.setUpClass()

    @classmethod
    def tearDownClass(cls): cls.fixture.tearDownClass()

    def setUp(self):
        self.fx = self.fixture(); self.fx.setUp()

    def tearDown(self): self.fx.tearDown()

    def test_chat_applies_style_and_export_renders_it(self):
        import subprocess
        from unittest.mock import patch
        from backend.editor import segmentation
        def half(self, seconds, width, height):
            matte = np.zeros((height, width), np.float32); matte[:, :width//2] = 1
            return matte
        state = self.fx.get()['draft']['state']
        with patch.object(segmentation.Mattes, 'ensure', lambda self, spans, progress=None: None), \
                patch.object(segmentation.Mattes, 'at', half):
            response = self.fx.client.post(self.fx.url+'/chat', headers=self.fx.headers,
                                           json={'message': 'make it a fan edit, edited by Tester', 'state': state})
            self.assertEqual(response.status_code, 200, response.text)
            styled = response.json()['state']
            self.assertEqual(styled['stylize']['events'][-1]['kind'], 'title_card')
            self.assertIn('fan-edit style', response.json()['message'])
            export = self.fx.client.post(self.fx.url+'/export', headers=self.fx.headers, json=styled)
        self.assertEqual(export.status_code, 200, export.text[:300])
        card = styled['stylize']['events'][-1]
        frame = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(card['start']+card['duration']*.8-styled['start']), '-i', '-',
                                '-frames:v', '1', '-vf', 'scale=64:-2', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                               input=export.content, capture_output=True, check=True).stdout
        pixels = np.frombuffer(frame, np.uint8).reshape(-1, 3)
        self.assertLess(np.median(pixels), 40)  # dark end card
        self.assertTrue(((pixels[:, 0] > 180) & (pixels[:, 2] < 90)).any())  # orange name text


if __name__ == '__main__':
    unittest.main()
