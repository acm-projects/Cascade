"""Music edits that keep a few talking moments: plan rules, captions and the music dip (no AI, no rendering)."""
import unittest

import numpy as np

from backend.editor.ai_edit.cinema import visual
from backend.editor.ai_edit.cinema.planner import speech, wants_montage


def plan(shots, **more):
    return visual.VisualPlan(shots=[visual.VisualShot(**s) for s in shots], **more)


class MontageTests(unittest.TestCase):
    def test_talking_shots_play_at_normal_speed_and_keep_the_clip_sound(self):
        p = plan([{'start': 0, 'end': 2, 'speed': .5, 'voice': True}, {'start': 5, 'end': 6}], sound='score')
        self.assertEqual(p.shots[0].speed, 1.)
        self.assertEqual(p.sound, 'both')

    def test_a_talking_shot_ends_on_the_beat_after_its_words_never_before(self):
        p = plan([{'start': 10, 'end': 12.3, 'voice': True}, {'start': 20, 'end': 21}, {'start': 30, 'end': 31}])
        visual.fit(p, 15, grid=[k * .5 for k in range(40)])
        talking = [s for s in p.shots if 10 <= s.start < 12.3]   # a long hold becomes jump cuts on the beat
        self.assertTrue(all(s.voice for s in talking))
        self.assertGreaterEqual(talking[-1].end, 12.3)
        self.assertLess(talking[-1].end, 12.85)

    def test_captions_follow_the_words_said_in_talking_shots_only(self):
        words = [{'w': 'wait', 's': 10.1, 'e': 10.4}, {'w': 'he', 's': 10.5, 'e': 10.6}, {'w': 'fell', 's': 10.7, 'e': 11.0},
                 {'w': 'unrelated', 's': 30.0, 'e': 30.5}]
        out = visual.speech_captions(words, [(2.0, 3.2, 10.0)])
        self.assertEqual(len(out), 1)
        self.assertEqual([w for w, _ in out[0].data['words']], ['wait', 'he', 'fell'])
        self.assertAlmostEqual(out[0].data['words'][0][1], 2.1, places=3)   # edit time = shot start + (word - source start)
        self.assertEqual(out[0].data['style'], 'caption')

    def test_the_clip_sound_splits_into_talking_and_a_quiet_bed(self):
        sr = 1000
        natural = np.ones((5 * sr, 2), np.float32)
        voice, bed = visual._split(natural, [(1., 2., 0.)], sr)
        self.assertAlmostEqual(float(voice[1500, 0]), 1.)
        self.assertAlmostEqual(float(voice[3500, 0]), 0.)
        self.assertTrue(np.allclose(voice + bed, natural))

    def test_pieces_of_one_moment_never_play_back_to_back(self):
        # the plan OpenAI returned for the real hiking montage: three pieces of the opening clip in a row
        spans = [(0, 1.67), (2, 3.67), (4, 5.67), (7, 8.67), (8.5, 9.75), (10.1, 11.35), (12.1, 13.77), (14, 15.67), (18.1, 19.77), (20, 20.83)]
        p = visual.interleave(plan([{'start': a, 'end': b} for a, b in spans]))
        order = [(s.start, s.end) for s in p.shots]
        self.assertEqual(sorted(order), sorted(spans))                  # every shot still plays once
        self.assertEqual((order[0], order[-1]), (spans[0], spans[-1]))   # same opening and closing shot
        together = sum(visual._near(a, b) for a, b in zip(p.shots, p.shots[1:]))
        self.assertLessEqual(together, 1)

    def test_a_clip_with_only_one_moment_keeps_its_order(self):
        p = visual.interleave(plan([{'start': 0, 'end': 1}, {'start': 1, 'end': 2}, {'start': 2, 'end': 3}]))
        self.assertEqual([s.start for s in p.shots], [0, 1, 2])

    def test_trip_reel_burst_keeps_its_glimpses_short_and_off_the_beat_grid(self):
        shots = [{'start': 0, 'end': 2}] + [{'start': 4 + k, 'end': 4.6 + k, 'flash': True} for k in range(5)] + \
                [{'start': 12, 'end': 13}, {'start': 16, 'end': 17}, {'start': 20, 'end': 23}]
        p = plan(shots, loop=True, title='YOSEMITE', title_style='typed', grade='natural')
        visual.interleave(p)
        self.assertTrue(all(s.flash for s in p.shots[1:6]))           # the burst stays right after the opening
        visual.fit(p, 15, grid=[k * .64 for k in range(40)])
        burst = [s for s in p.shots if s.flash]
        self.assertTrue(all(.1 <= s.end - s.start <= .3 + 1e-6 for s in burst))
        self.assertEqual((p.shots[0].start, p.shots[1].flash), (0, True))   # the titled opening holds as one shot
        self.assertLessEqual(visual.length(p) + visual.LOOP, 15.01)    # room is kept for the loop ending

    def test_requested_length_is_read_from_the_editor_request(self):
        from backend.editor.ai_edit.cinema.planner import requested_seconds
        self.assertEqual(requested_seconds('make a 15 second insta edit'), 15)
        self.assertEqual(requested_seconds('around 10 to 15 seconds'), 15)
        self.assertEqual(requested_seconds('exactly like my reference'), 0)
        self.assertEqual(requested_seconds('a 3 second edit'), 6)

    def test_montage_requests_and_the_speech_list(self):
        self.assertTrue(wants_montage('make an insta edit of our hike like my references'))
        self.assertFalse(wants_montage('Edit this video'))
        words = [{'w': 'wait', 's': 1.0, 'e': 1.3}, {'w': 'what', 's': 1.4, 'e': 1.6}, {'w': 'later', 's': 4.0, 'e': 4.4}]
        text = speech(words, [[0, 10]])
        self.assertIn('1.00-1.60: wait what', text)
        self.assertIn('4.00-4.40: later', text)
        self.assertIn('none', speech([], [[0, 10]]))


if __name__ == '__main__':
    unittest.main()
