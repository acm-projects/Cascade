"""The Cinema engine, offline: dialogue cleaning, the rule-based director, the score's silence and the stamp."""
import unittest

import numpy as np

from backend.editor.ai_edit.cinema import look, plan as plans, render, score, speech, stamp


def words(text, step=.4, start=0.):
    return [{'i': i, 'w': w, 's': round(start+i*step, 3), 'e': round(start+i*step+step*.8, 3)} for i, w in enumerate(text.split())]


class Dialogue(unittest.TestCase):
    def test_fillers_stutters_and_asides_are_found(self):
        w = words('So um the the river is, you know, dying. I mean, it is uh gone.')
        found = {w[i]['w'] for i in speech.fillers(w)}
        self.assertEqual(found, {'um', 'the', 'you', 'know,', 'I', 'mean,', 'uh'})

    def test_false_starts_go_but_repetition_on_purpose_stays(self):
        w = words('But whenever you see, whenever I have seen a jaguar it is peaceful. Tongue out, big teeth out. See that deer, you can eat that deer.')
        cut = {w[i]['w'] for i in speech.restarts(w)}
        self.assertEqual(cut, {'whenever', 'you', 'see,'})

    def test_cut_squeezes_pauses_and_never_overlaps(self):
        w = words('The forest is burning', .4)+words('right now today', .4, start=6.)
        for n, x in enumerate(w): x['i'] = n
        db = np.full(1000, -60.)
        for x in w: db[int(x['s']*100):int(x['e']*100)] = -20
        edit = speech.cut(w, [(0, len(w)-1)], set(), db, duration=10)
        self.assertLess(edit.total, 3.6)          # a 4 s silence is gone
        ends = [(p.out, p.out+p.length) for p in edit.pieces]
        for (a, b), (c, d) in zip(ends, ends[1:]): self.assertLessEqual(c, b)   # joined, crossfaded, no gap
        for x in w:   # every word is kept whole, with room either side
            piece = next(p for p in edit.pieces if x['i'] in p.words)
            self.assertLessEqual(piece.a, x['s']); self.assertGreaterEqual(piece.b, x['e'])

    def test_word_endings_follow_the_voice_not_the_transcript(self):
        w = [{'i': 0, 'w': 'gone', 's': 1.0, 'e': 1.2}, {'i': 1, 'w': 'now', 's': 2.0, 'e': 2.2}]
        db = np.full(400, -60.); db[100:138] = -20; db[200:222] = -20   # "gone" really rings on to 1.38 s
        edit = speech.cut(w, [(0, 0)], set(), db, duration=4)
        self.assertGreaterEqual(edit.pieces[0].b, 1.38)


class Director(unittest.TestCase):
    def test_rule_based_plan_is_question_first_and_cuts_the_echo_and_false_starts(self):
        text = ('What is the most dangerous animal in the Amazon? Dangerous animal in the Amazon. '
                'They are. Okay. The jaguars are the pit bulls of the big cats. They crush the skull of a caiman. '
                'But in the forest they are peaceful. He walked right by me.')
        w = words(text)
        p = plans.auto(w)
        plans.check(p, w)
        self.assertEqual(p.story[0].role, 'question')
        dropped = ' '.join(w[i]['w'] for i in sorted(p.dropped()))
        self.assertIn('Dangerous animal in the Amazon.', dropped)
        self.assertIn('They are.', dropped)
        self.assertTrue(p.moments)


class Sound(unittest.TestCase):
    def test_music_stops_dead_before_the_payoff(self):
        music = score.compose(20, {'silence': (12., 13.), 'end': 20, 'hook_end': 3}, 'awakening')
        quiet = np.abs(music[int(12.05*score.SR):int(12.95*score.SR)]).max()
        self.assertLess(quiet, 1e-6)
        self.assertGreater(np.abs(music[int(14*score.SR):int(15*score.SR)]).max(), 1e-3)

    def test_stamp_is_short_full_size_and_has_no_music(self):
        look.configure(1920, 1080)
        frames = list(stamp.frames(np.zeros((1080, 1920, 3), np.uint8)))
        self.assertEqual(len(frames), int(stamp.DURATION*30))
        self.assertEqual(frames[40].shape, (1080, 1920, 3))
        self.assertGreater(frames[50].mean(), frames[0].mean())   # the stroke and the word are painted by then
        sound = score.stamp_audio()
        tail = sound[int(1.9*score.SR):]
        self.assertLess(np.abs(tail).max(), np.abs(sound).max()*.2)   # only the splash and its drops, nothing sustained

    def test_original_shape_by_default_and_reel_on_request(self):
        self.assertEqual(render.size_for(1282, 694), (1920, 1080))
        self.assertEqual(render.size_for(1282, 694, '9:16'), (1080, 1920))
        self.assertEqual(render.size_for(1080, 1920), (1080, 1920))


if __name__ == '__main__':
    unittest.main()
