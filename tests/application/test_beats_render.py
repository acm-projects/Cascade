"""Stage 4 of the beats pipeline, offline: frame math (mirrors remotion/src/lib/timing.js), the beat cache and
the render checks. Real renders: see PROGRESS.md / REPORT.md."""
import copy
import json
import unittest
from pathlib import Path
from unittest import mock

from backend.editor.ai_edit.beats import render

HERE = Path(render.__file__).parent
EXAMPLE = json.loads((HERE/'examples'/'edit_plan_example.json').read_text())


class Frames(unittest.TestCase):
    def test_beats_are_contiguous_and_within_half_a_frame_of_the_plan(self):
        frames = render.frames_for(EXAMPLE)
        self.assertEqual(frames[0][1], 0)
        self.assertEqual(frames[-1][2], render.total_frames(EXAMPLE))
        self.assertEqual(render.total_frames(EXAMPLE), 2680)   # same number the JS test checks
        for (_, a, b), (_, c, _) in zip(frames, frames[1:]): self.assertEqual(b, c)
        for (_, a, _), beat in zip(frames, EXAMPLE['beats']): self.assertLessEqual(abs(a/60-(beat['start']-27.12)), .5/60+1e-9)

    def test_changing_a_beat_re_renders_it_and_the_beat_after_only(self):
        props = {'width': 1284, 'height': 704, 'assets': {}, 'options': {}, 'source_key': {}}
        with mock.patch.object(render, 'renderer_version', return_value='x'):
            before = render.segment_keys(EXAMPLE, props)
            changed = copy.deepcopy(EXAMPLE); changed['beats'][6]['semantic_color'] = 'red'   # beat 7
            after = render.segment_keys(changed, props)
            props2 = {**props, 'assets': {'9': {'cutout': {'dir': 'c', 'fps': 30, 'count': 3, 'from': 0}}}}
            with_asset = render.segment_keys(EXAMPLE, props2)
        self.assertEqual([i for i in before if before[i] != after[i]], [7, 8])
        self.assertEqual([i for i in before if before[i] != with_asset[i]], [9, 10])

    def test_verify_rejects_a_render_that_drifts_from_the_plan(self):
        with mock.patch.object(render, 'probe_frames', return_value=2680), mock.patch.object(render, 'probe_duration', return_value=44.6667):
            self.assertTrue(render.verify(EXAMPLE, 'x.mp4')['ok'])
        with mock.patch.object(render, 'probe_frames', return_value=2679), mock.patch.object(render, 'probe_duration', return_value=44.65):
            with self.assertRaises(render.RenderError): render.verify(EXAMPLE, 'x.mp4')
        with mock.patch.object(render, 'probe_frames', return_value=2680), mock.patch.object(render, 'probe_duration', return_value=44.4):
            with self.assertRaises(render.RenderError): render.verify(EXAMPLE, 'x.mp4')


if __name__ == '__main__':
    unittest.main()
