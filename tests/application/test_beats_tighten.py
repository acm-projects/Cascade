"""Pause removal and the dramatic score for beat renders."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.editor.ai_edit.beats import assets, music, tighten

EXAMPLE = json.loads((Path(__file__).resolve().parents[2]/'backend/editor/ai_edit/beats/examples/edit_plan_example.json').read_text())


def W(word, a, b):
    return {'word': word, 'start': a, 'end': b}


class Ranges(unittest.TestCase):
    def test_long_gaps_are_cut_short_ones_kept(self):
        words = [W('one', 10., 10.4), W('two', 10.5, 10.9), W('three', 12.5, 13.), W('four', 13.1, 13.5)]
        ranges = tighten.keep_ranges(words, 10., 15.)
        self.assertEqual(len(ranges), 2)
        self.assertAlmostEqual(ranges[0][1], 10.9+tighten.TAIL)
        self.assertAlmostEqual(ranges[1][0], 12.5-tighten.LEAD)
        kept = sum(b-a for a, b in ranges)
        self.assertLess(kept, 5-1.5)              # the 1.6 s pause and the 1.5 s tail are gone

    def test_cut_points_snap_to_the_frame_grid(self):
        words = [W('a', 1.013, 1.4), W('b', 3.077, 3.3)]
        for a, b in tighten.keep_ranges(words, 1., 4., fps=30):
            self.assertAlmostEqual(a*30, round(a*30), 6); self.assertAlmostEqual(b*30, round(b*30), 6)

    def test_mapping(self):
        to = tighten.mapper([(1., 2.), (3., 4.)])
        self.assertEqual([to(0.5), to(1.5), to(2.5), to(3.5), to(9)], [0, .5, 1., 1.5, 2.])


class Plan(unittest.TestCase):
    def test_pause_beats_drop_and_the_rest_stay_contiguous(self):
        words = json.loads((Path(tighten.__file__).parent/'examples'/'transcript_full.json').read_text())
        w = EXAMPLE['source_window']
        ranges = tighten.keep_ranges(words, w['start'], w['end'], fps=60)
        plan = tighten.tighten(EXAMPLE, ranges)
        self.assertNotIn(14, [b['id'] for b in plan['beats']])                    # the empty "pause" beat
        self.assertEqual(plan['source_window']['start'], 0.)
        self.assertAlmostEqual(plan['source_window']['end'], sum(b-a for a, b in ranges), 3)
        self.assertEqual(plan['beats'][0]['start'], 0.)
        self.assertEqual(plan['beats'][-1]['end'], plan['source_window']['end'])
        for a, b in zip(plan['beats'], plan['beats'][1:]): self.assertEqual(a['end'], b['start'])
        self.assertTrue(all(b['end']-b['start'] >= tighten.MIN_BEAT-1e-6 for b in plan['beats'][:-1]))
        self.assertEqual(EXAMPLE['beats'][13]['spoken_text'], '')                  # the saved plan is untouched

    def test_tight_source_joins_the_kept_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/'src.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=160x90:rate=30', '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=48000',
                            '-t', '4', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(src)], check=True)
            out = tighten.tight_source(src, [(.5, 1.5), (2.5, 3.)], Path(tmp)/'tight')
            probe = lambda s: float(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', s, '-show_entries', 'stream=duration', '-of', 'csv=p=0', str(out)],
                                                   capture_output=True, text=True).stdout.strip().strip(','))
            self.assertAlmostEqual(probe('v:0'), 1.5, delta=.04)
            self.assertAlmostEqual(probe('a:0'), 1.5, delta=.04)
            self.assertEqual(tighten.tight_source(src, [(.5, 1.5), (2.5, 3.)], Path(tmp)/'tight'), out)   # cached


class Sound(unittest.TestCase):
    def test_the_score_is_the_right_length_and_not_silent(self):
        x = music.dramatic(6., hits=[2.])
        self.assertEqual(x.shape, (6*music.SR, 2))
        self.assertGreater(np.sqrt((x**2).mean()), 1e-3)
        self.assertTrue(np.isfinite(x).all())

    def test_every_effect_name_gets_a_dark_sound(self):
        for name in ('wind_whoosh', 'deep_rumble', 'low_hit', 'marker_swipe', 'counter_tick', 'map_ping', 'riser_build', 'impact_hit_big', 'whatever'):
            x, where = assets.sound(name, 1.2)
            self.assertIn(where, assets.LEVELS, name)
            self.assertGreater(len(x), 100, name)
        self.assertEqual(assets.sound('deep_rumble', 1.)[1], 'span')
        self.assertEqual(assets.sound('riser_build', 1.)[1], 'end')

    def test_hits_come_from_impact_beats(self):
        hits = assets.hit_times(EXAMPLE)
        self.assertIn(round(56.62-27.12, 2), [round(h, 2) for h in hits])        # beat 16, impact_hit_big


if __name__ == '__main__':
    unittest.main()
