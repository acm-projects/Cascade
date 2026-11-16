"""Stages 4-5 of the beats pipeline, offline: frame math (mirrors remotion/src/lib/timing.js), the beat cache,
the render checks, b-roll search and ranking, and the synthesized sound effects. Real renders: see REPORT.md."""
import copy
import json
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from backend.editor.ai_edit.beats import assets, render

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


class Broll(unittest.TestCase):
    class Store:
        def __init__(self, results, fail=False): self.results, self.fail, self.searches = results, fail, []
        def search(self, query, orientation=None, hd=False):
            self.searches.append(query)
            if self.fail: raise RuntimeError('Pexels is not configured.')
            return {'results': self.results.get(query, [])}
        def media(self, asset_id): return Path(f'/cache/{asset_id}.mp4')

    def test_best_described_clip_wins_and_the_fallback_query_is_used_when_needed(self):
        store = self.Store({'deep space stars slow push in': [
            {'id': 'a', 'source_url': 'https://www.pexels.com/video/woman-smiling-1/'},
            {'id': 'b', 'source_url': 'https://www.pexels.com/video/stars-in-deep-space-2/'}],
            'rainforest canopy time lapse': [{'id': 'c', 'source_url': 'https://www.pexels.com/video/rainforest-canopy-in-fog-3/'}]})
        path, record = assets.find_broll('deep space stars slow push in', 'starfield', store, set())
        self.assertEqual((path, record['id'], record['license']), ('/cache/b.mp4', 'b', 'Pexels License'))
        path, record = assets.find_broll('aerial drone flight over rainforest canopy morning mist', 'rainforest canopy time lapse', store, set())
        self.assertEqual((record['searched'], record['id']), ('rainforest canopy time lapse', 'c'))
        used = {'c'}
        path, record = assets.find_broll('jaguar', 'rainforest canopy time lapse', store, used)
        self.assertIsNone(path)                                       # nothing relevant left: the renderer draws a background
        self.assertIn('generated background', record['note'])

    def test_no_stock_service_is_reported_not_fatal(self):
        path, record = assets.find_broll('stars', 'space', self.Store({}, fail=True), set())
        self.assertIsNone(path)
        self.assertIn('not configured', record['error'])

    def test_collage_subjects(self):
        beat = next(b for b in EXAMPLE['beats'] if b['template'] == 'COLLAGE')
        self.assertEqual(assets.subjects(beat), ['tree frog on leaf', 'blue morpho butterfly', 'jaguar walking in jungle', 'orchid macro'])


class Matte(unittest.TestCase):
    def test_stray_fragments_and_half_transparent_ghosts_are_removed(self):
        alpha = np.zeros((100, 100), np.float32)
        alpha[20:90, 40:80] = 1          # the speaker
        alpha[5:9, 5:9] = 1              # a stray speck
        alpha[50:60, 10:20] = .45        # a ghost from the matte's smoothing
        clean = assets.clean_matte(alpha)
        self.assertGreater(clean[50, 60], .9)
        self.assertLess(clean[7, 7], .05)
        self.assertLess(clean[55, 15], .2)


class Sound(unittest.TestCase):
    def test_every_effect_in_the_plan_is_made_and_placed(self):
        names = {b['sfx'] for b in EXAMPLE['beats'] if b['sfx']}
        for name in names:
            x, where = assets.sound(name, 1.5)
            self.assertTrue(len(x) and np.isfinite(x).all(), name)
            self.assertIn(where, assets.LEVELS)
        track, placed = assets.effects_track(EXAMPLE, 44.66)
        self.assertEqual(track.shape, (int(44.66*assets.SR), 2))
        self.assertEqual(len(placed), sum(1 for b in EXAMPLE['beats'] if b['sfx']))
        self.assertLessEqual(np.abs(track).max(), 1.0)
        riser = next(p for p in placed if p['sfx'] == 'riser_build')          # beat 14: lands on the payoff's cut
        self.assertAlmostEqual(riser['at']+riser['seconds'], 55.26-27.12, places=2)


if __name__ == '__main__':
    unittest.main()
