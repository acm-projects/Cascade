"""Device-named frame shapes: every shape renders, the quick preview never waits for speaker tracking, and a finished edit can be reshaped."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.application import test_editor as editor_fixture
from backend.editor import render
from backend.editor.models import Composition, ExportInput


def size_of(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0:s=x', str(path)], capture_output=True, text=True).stdout
    return tuple(map(int, out.strip().split('x')))


class AspectPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): editor_fixture.EditorTests.setUpClass()
    @classmethod
    def tearDownClass(cls): editor_fixture.EditorTests.tearDownClass()
    def setUp(self):
        self.fx = editor_fixture.EditorTests(); self.fx.setUp()
        self.client, self.url, self.headers = self.fx.client, self.fx.url, self.fx.headers
        self.state = self.fx.get()['draft']['state']
    def tearDown(self): self.fx.tearDown()

    def export(self, **changes):
        body = {**self.state, **changes}
        return self.client.post(self.url + '/export', headers=self.headers, json=body)

    def test_the_new_shapes_are_accepted_and_render_at_their_ratio(self):
        for ratio, expected in (('16:10', 1.6), ('21:9', 21 / 9)):
            response = self.export(composition={**self.state['composition'], 'ratio': ratio, 'mode': 'fit'})
            self.assertEqual(response.status_code, 200, response.text)
            with tempfile.NamedTemporaryFile(suffix='.mp4') as file:
                file.write(response.content); file.flush()
                w, h = size_of(file.name)
            self.assertAlmostEqual(w / h, expected, delta=.02)

    def test_the_quick_preview_never_waits_for_speaker_tracking(self):
        fill = {**self.state['composition'], 'ratio': '9:16', 'mode': 'fill'}
        with patch.object(render, 'begin_analysis', return_value={'analysis_id': 'a' * 32, 'status': 'processing'}):
            waiting = self.export(composition=fill)
            quick = self.export(composition=fill, preview=True, resolution='480p')
        self.assertEqual(waiting.status_code, 409)        # a real export still waits for the analysis
        self.assertEqual(quick.status_code, 200, quick.text)  # the preview shows a steady crop right away

    def test_a_finished_edit_can_be_reshaped(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'finished.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=25:duration=1', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-shortest', '-pix_fmt', 'yuv420p', str(source)], check=True)
            body = ExportInput(start=0, end=1, composition=Composition(ratio='9:16', mode='fill'), preview=True, resolution='480p')
            response = render.recompose_file(source, body)
            w, h = size_of(response.path)
            self.assertAlmostEqual(w / h, 9 / 16, delta=.02)
            self.assertLessEqual(min(w, h), 480)


if __name__ == '__main__':
    unittest.main()


class TopicSearchTests(unittest.TestCase):
    def test_menu_choices_search_real_kinds_of_video(self):
        from backend.editor import trends
        self.assertIn('podcast clip', trends.search_queries('Podcast / interview'))
        self.assertTrue(all('podcast' not in q for q in trends.search_queries('travel vlog')))
        self.assertEqual(trends.search_queries('street food tour'), ['street food tour', 'street food tour viral'])
        self.assertEqual(trends.search_queries(''), ['viral shorts'])

    def test_automatic_topic_follows_the_clip(self):
        from backend.editor import trends
        talk = {'cues': [{'text': 'welcome back to the show'}]}
        self.assertEqual(trends.derive_search({'title': 'Episode 4'}, talk), 'podcast / interview')
        self.assertEqual(trends.derive_search({'title': 'Bali trip vlog'}, {'cues': []}), 'travel vlog')
        self.assertEqual(trends.derive_search({'title': 'x'}, talk, override='gaming'), 'gaming')
