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

    def test_talking_shots_keep_whole_sentences(self):
        words = [{'w': w, 's': a, 'e': a + .3} for w, a in [('hey', 0.2), ('guys', .6), ('this', 1.0), ('is', 1.4), ('cascade', 1.8),
                                                            ('reconnect', 2.3), ('with', 2.7), ('nature', 3.1), ('later', 9.0)]]
        p = visual.whole_phrases(plan([{'start': 0.5, 'end': 1.5, 'voice': True}, {'start': 9.5, 'end': 10.5}]), words)
        self.assertLessEqual(p.shots[0].start, 0.2)
        self.assertGreaterEqual(p.shots[0].end, 3.4)
        self.assertEqual((p.shots[1].start, p.shots[1].end), (9.5, 10.5))   # music shots are left alone

    def test_talking_stops_at_the_sentence_end(self):
        words = [{'w': w, 's': a, 'e': a + .3} for w, a in [('taking', 0.2), ('a', .6), ('break', 1.0), ('prep.', 1.4), ('I', 1.8), ('have', 2.2), ('no', 2.6), ('clue.', 3.0)]]
        p = visual.whole_phrases(plan([{'start': 0.1, 'end': 1.7, 'voice': True}]), words)
        self.assertLess(p.shots[0].end, 2.0)   # stops after "prep." instead of running into the next sentence

    def test_blue_title_and_shake(self):
        p = plan([{'start': 0, 'end': 2, 'effect': 'shake'}], title='HIKE WITH CASCADE', title_style='corners', title_color='blue')
        self.assertEqual(visual.TITLE_TONES[p.title_color], 'water')
        import numpy as np
        from backend.editor.ai_edit.cinema import accents
        frame = np.zeros((90, 160, 3), np.uint8); frame[40:50, 70:90] = 255
        self.assertEqual(accents.apply(frame, None, 'shake', .3).shape, frame.shape)
        self.assertTrue((accents.apply(frame, None, 'shake', 1.) == frame).all())

    def test_shots_must_follow_the_requested_clip_order(self):
        parts = [{'title': 'hands', 'from': 0, 'to': 5}, {'title': 'intro', 'from': 5, 'to': 11}, {'title': 'wave', 'from': 11, 'to': 14}]
        good = plan([{'start': 5, 'end': 9, 'voice': True}, {'start': 11, 'end': 12}, {'start': 0, 'end': 4, 'voice': True}], clip_order=[2, 3, 1])
        visual.check(good, 14, parts=parts)
        with self.assertRaisesRegex(ValueError, 'not played'):
            visual.check(plan([{'start': 5, 'end': 9}, {'start': 0, 'end': 4}], clip_order=[2, 3, 1]), 14, parts=parts)
        with self.assertRaisesRegex(ValueError, 'order'):
            visual.check(plan([{'start': 0, 'end': 4}, {'start': 5, 'end': 9}, {'start': 11, 'end': 12}], clip_order=[2, 3, 1]), 14, parts=parts)

    def test_clips_in_a_collage_count_as_played(self):
        parts = [{'title': 'a', 'from': 0, 'to': 5}, {'title': 'b', 'from': 5, 'to': 10}, {'title': 'c', 'from': 10, 'to': 15}]
        visual.check(plan([{'start': 0, 'end': 2}, {'start': 5, 'end': 6.5, 'panels': [11]}], clip_order=[1, 2, 3]), 15, parts=parts)

    def test_stop_at_the_words_the_request_names(self):
        words = [{'w': w, 's': a, 'e': a + .3} for w, a in [('break', 0.2), ('from', .6), ('presentation', 1.0), ('prep.', 1.4), ('I', 1.8), ('have', 2.2)]]
        p = visual.stop_at(plan([{'start': 0, 'end': 3, 'voice': True}]), words, 'keep the intro, and stop the intro at presentation prep. Then the wave')
        self.assertAlmostEqual(p.shots[0].end, 1.78)   # right after "prep.", before "I" starts

    def test_the_intro_and_ending_are_heard_and_the_ending_plays_out(self):
        words = [{'w': w, 's': a, 'e': a + .4} for w, a in [('Set.', .2), ('Cascade', .7), ('on', 1.2), ('three.', 1.6), ('one', 2.4), ('two', 2.9), ('three.', 3.4), ('Cascade.', 4.2),
                                                          ('Hey', 5.1), ('guys.', 5.6), ('This', 6.1), ('is', 6.6), ('Cascade.', 7.1)]]
        parts = [{'title': 'hands', 'from': 0, 'to': 5}, {'title': 'intro', 'from': 5, 'to': 8}]
        p = visual.story_edges(plan([{'start': 5, 'end': 7.5}, {'start': 0, 'end': 2.3}], clip_order=[2, 1]), words, parts)
        self.assertTrue(p.shots[0].voice and p.shots[-1].voice)
        self.assertGreater(p.shots[-1].end, 4.9)

    def test_end_right_after_the_named_words(self):
        words = [{'w': w, 's': a, 'e': a + .3} for w, a in [('Set.', .2), ('Cascade', .7), ('on', 1.1), ('three.', 1.5), ('One', 2.4), ('two', 2.8), ('three.', 3.2), ('Cascade.', 4.2)]]
        p = plan([{'start': 10, 'end': 12, 'voice': True}, {'start': 0, 'end': 5, 'voice': True}])
        visual.stop_at(p, words, 'end right after the one two three and our hands are up')
        self.assertAlmostEqual(p.shots[-1].end, 4.4)
        self.assertEqual(p.shots[0].end, 12)

    def test_effects_and_big_captions(self):
        import numpy as np
        from backend.editor.ai_edit.cinema import accents
        a, b = np.zeros((90, 160, 3), np.uint8), np.full((90, 160, 3), 200, np.uint8)
        for kind in ('slices', 'window'):
            self.assertEqual(accents.apply(b, a, kind, .4).shape, a.shape)
            self.assertTrue((accents.apply(b, a, kind, 1.) == b).all())
        words = [{'w': 'cascade', 's': 1.0, 'e': 1.4}]
        self.assertEqual(visual.speech_captions(words, [(0., 2., 0., True)])[0].data['style'], 'bold')

    def test_stop_before_the_next_word_and_start_from_words(self):
        words = [{'w': w, 's': a, 'e': e} for w, a, e in [('presentation', 3.18, 3.74), ('prep.', 3.7, 4.15), ('I', 4.11, 4.36),
                                                         ("That's", 10.0, 10.2), ('it.', 10.2, 10.5), ('One', 12.0, 12.4), ('two', 12.5, 12.9), ('three.', 13.0, 13.4), ('Cascade.', 13.5, 14.0)]]
        p = plan([{'start': 1, 'end': 6, 'voice': True}, {'start': 9.8, 'end': 14.5, 'voice': True}])
        visual.stop_at(p, words, 'stop the intro at presentation prep, and the last part is too long just start from one two three')
        self.assertLess(p.shots[0].end, 4.11)          # "I" is not heard
        self.assertTrue(p.shots[0].hard_end)
        self.assertAlmostEqual(p.shots[1].start, 11.88)

    def test_an_opening_intro_starts_at_its_first_word(self):
        words = [{'w': w, 's': a, 'e': a + .3} for w, a in [('Hey,', 2.8), ('guys.', 3.1), ('This', 3.5), ('is', 3.8), ('Cascade.', 4.1)]]
        p = visual.story_edges(plan([{'start': 3.45, 'end': 4.5}, {'start': 10, 'end': 11}]), words,
                               [{'title': 'intro', 'from': 0, 'to': 9}, {'title': 'b', 'from': 9, 'to': 12}])
        self.assertAlmostEqual(p.shots[0].start, 2.7)
        chatter = [{'w': w, 's': a, 'e': a + .3} for w, a in [("It's", 1.0), ('a', 1.3), ('good', 1.6), ('hour.', 1.9), ("Let's.", 2.3)]] + words
        p = visual.story_edges(plan([{'start': 3.45, 'end': 4.5}, {'start': 10, 'end': 11}]), chatter,
                               [{'title': 'intro', 'from': 0, 'to': 9}, {'title': 'b', 'from': 9, 'to': 12}])
        self.assertAlmostEqual(p.shots[0].start, 2.7)   # only the "Hey, guys." greeting, not the chatter before it

    def test_counted_numbers_in_digits_still_match(self):
        words = [{'w': w, 's': a, 'e': a + .3} for w, a in [('Gascade', 4.0), ('on', 4.4), ('3.', 4.6), ('123.', 5.0), ('Custade.', 6.6)]]
        p = plan([{'start': 0, 'end': 2, 'voice': True}, {'start': 3, 'end': 7, 'voice': True}], outro='CASCADE')
        visual.stop_at(p, words, 'the last part: start from one two three, as big text')
        self.assertAlmostEqual(p.shots[1].start, 4.88)
        lines = visual.speech_captions(words, [(0., 4., 3., True)])
        self.assertIn('one two three', ' '.join(w for o in lines for w, _ in o.data['words']))
        self.assertAlmostEqual(visual.outro_word_time(p, words, [(10., 14., 3., True)]), 13.6)

    def test_quick_shots_shrink_before_any_is_dropped(self):
        p = plan([{'start': 0, 'end': 4, 'voice': True}] + [{'start': 10 + 3 * k, 'end': 11.5 + 3 * k} for k in range(4)] + [{'start': 30, 'end': 34, 'voice': True}])
        visual.fit(p, 11.6)
        self.assertEqual(len(p.shots), 6)

    def test_a_long_edit_loses_middle_music_shots_not_its_talking_or_ending(self):
        p = plan([{'start': 0, 'end': 6, 'voice': True}, {'start': 10, 'end': 12}, {'start': 14, 'end': 16},
                  {'start': 18, 'end': 20}, {'start': 30, 'end': 35, 'voice': True}])
        visual.fit(p, 14)
        self.assertEqual(p.shots[0].start, 0)
        self.assertEqual(p.shots[-1].start, 30)
        self.assertTrue(p.shots[-1].voice)
        self.assertLessEqual(visual.length(p), 14.01)

    def test_horizontal_requests(self):
        from backend.editor.ai_edit.cinema.planner import requested_ratio
        self.assertEqual(requested_ratio('make a horizontal edit'), '16:9')
        self.assertEqual(requested_ratio('vertical reel please'), '9:16')
        self.assertEqual(requested_ratio('make an edit'), '')

    @unittest.skipUnless(__import__('shutil').which('ffmpeg'), 'needs ffmpeg')
    def test_collage_silhouette_and_outro_render(self):
        import subprocess, tempfile
        from pathlib import Path
        folder = Path(tempfile.mkdtemp())
        src = folder / 'src.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=320x180:d=8:r=30', '-f', 'lavfi', '-i', 'sine=d=8',
                        '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(src)], check=True)
        p = plan([{'start': 0, 'end': 1.5}, {'start': 2, 'end': 3.5, 'panels': [4, 5.5, 6.5], 'silhouette': True},
                  {'start': 6, 'end': 7.2, 'zoom': 'rise'}], outro='CASCADE', title_color='blue', sound='original')
        p.settings.music = False
        p.settings.stamp = False
        out = folder / 'out.mp4'
        report = visual.make(src, p, out, ffmpeg='ffmpeg', ratio='16:9', lines=180, faces=False)
        self.assertTrue(out.is_file())
        self.assertAlmostEqual(report['seconds'], 1.5 + 1.5 + 1.2 + visual.OUTRO, delta=.2)
        self.assertFalse(list(folder.glob('collage-*.mp4')))   # temporary collage clips are removed

    def test_the_ending_word_lands_when_it_is_said(self):
        words = [{'w': w, 's': a, 'e': a + .3} for w, a in [('One', 10.0), ('two', 10.4), ('three.', 10.8), ('Cascade!', 11.4)]]
        p = plan([{'start': 0, 'end': 2}], outro='CASCADE')
        self.assertAlmostEqual(visual.outro_word_time(p, words, [(8.0, 10.0, 9.5, True)]), 9.9)   # 8.0 + (11.4 - 9.5)
        self.assertIsNone(visual.outro_word_time(plan([{'start': 0, 'end': 2}], outro='HIKE'), words, [(8.0, 10.0, 9.5)]))
        misheard = words[:3]+[{'w': 'Custained.', 's': 11.4, 'e': 11.8}]   # what transcription made of a shouted "Cascade!"
        self.assertAlmostEqual(visual.outro_word_time(p, misheard, [(8.0, 10.0, 9.5, True)]), 9.9)
        # the moment split into beat pieces: the word is in an earlier piece than the last one
        self.assertAlmostEqual(visual.outro_word_time(p, misheard, [(8.0, 9.8, 9.5, True), (9.8, 10.6, 11.3, True)]), 9.9)

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
