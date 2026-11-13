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


# ---------------------------------------------------------------------------------------------
# The system without any AI model: planning falls back, projects reopen, follow-ups change the
# saved timeline, and the engine renders. These are the tests that keep the editor independent
# of whichever Claude model happens to be available.

import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

from backend.editor.ai_edit.cinema import engine, planner, project, revise

NO_AI = {'CASCADE_EDITOR_CLAUDE': 'off', 'CASCADE_EDIT_PLANNER': 'auto', 'CASCADE_EDIT_PLANNER_CMD': ''}
STORY = ('What is the most dangerous animal in the Amazon? The jaguars are the pit bulls of the big cats. '
         'They crush the skull of a caiman. But in the forest they are peaceful. He walked right by me.')


class Planner(unittest.TestCase):
    def test_no_model_still_plans_a_first_edit_with_rules(self):
        w = words(STORY)
        with patch.dict(os.environ, NO_AI):
            self.assertEqual(planner.ai(), [])
            plan, who = planner.plan_edit('edit this video', '.', {'words': w, 'duration': 20, 'cuts': [], 'sheets': []}, [[0, 20]], [])
        self.assertEqual(who, 'rules')
        plans.check(plan, w)

    def test_creative_change_without_a_model_is_reported_not_faked(self):
        w = words(STORY)
        with patch.dict(os.environ, NO_AI), self.assertRaises(planner.Unavailable):
            planner.revise('open on a different line', plans.auto(w), '.', {'words': w, 'duration': 20, 'cuts': [], 'sheets': []}, [[0, 20]], [])

    def test_any_program_can_be_the_planner_and_the_model_name_is_only_configuration(self):
        w = words(STORY)
        answer = plans.auto(w).model_dump(); answer['title'] = 'From another model'
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp)/'model.py'
            script.write_text(f'import sys, json\njson.load(sys.stdin)\nprint(json.dumps({answer!r}))\n')
            env = {**NO_AI, 'CASCADE_EDIT_PLANNER': 'command', 'CASCADE_EDIT_PLANNER_CMD': f'{sys.executable} {script}'}
            with patch.dict(os.environ, env):
                plan, who = planner.plan_edit('edit this video', tmp, {'words': w, 'duration': 20, 'cuts': [], 'sheets': []}, [[0, 20]], [])
        self.assertEqual((plan.title, who), ('From another model', 'command'))
        with patch.dict(os.environ, {'CASCADE_EDIT_MODEL': 'opus'}):
            self.assertEqual(planner.label('claude'), 'claude:opus')
        source = ''.join(p.read_text() for p in Path(planner.__file__).parent.rglob('*.py'))+(Path(planner.__file__).parent/'prompts'/'director.md').read_text()
        self.assertNotIn('fable', source.lower())   # no model is named anywhere in the engine or its prompt


class Revisions(unittest.TestCase):
    def test_simple_follow_ups_change_the_saved_plan_without_ai(self):
        plan = plans.auto(words(STORY))
        new, done, left = revise.apply('make it a reel, lower the music and change the message to "Keep it wild, for them"', plan)
        self.assertEqual((new.settings.ratio, new.settings.music_db, new.end_line), ('9:16', -5, 'Keep it wild, for them'))
        self.assertEqual((len(done), left), (3, []))
        self.assertEqual(plan.settings.ratio, None)            # the original draft is untouched
        self.assertEqual(new.story, plan.story)                # the timeline is modified, not regenerated

    def test_creative_parts_are_left_for_the_planner(self):
        new, done, left = revise.apply('no captions and open on the line about the skull', plans.auto(words(STORY)))
        self.assertFalse(new.settings.captions)
        self.assertEqual(left, ['open on the line about the skull'])

    def test_project_round_trip(self):
        plan = plans.auto(words(STORY))
        with tempfile.TemporaryDirectory() as tmp:
            project.save(tmp, plan, {'seconds': 9, 'timeline': {'shots': []}}, 'claude:opus', 'edit this video')
            self.assertEqual(project.load(tmp), plan)
            saved = project.read(tmp)
            self.assertEqual((saved['planner'], saved['timeline'], saved['schema']), ('claude:opus', {'shots': []}, project.SCHEMA))
            (Path(tmp)/'project.json').unlink()                # the first releases only wrote plan.json
            self.assertEqual(project.load(tmp), plan)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs FFmpeg')
class RenderWithoutAI(unittest.TestCase):
    """Plan with rules, render, save, reopen, change with a plain sentence, render again: no model anywhere."""

    def test_edit_reopen_revise_and_export(self):
        w = words(STORY, step=.22)
        length = w[-1]['e']+.6
        sr = 16000
        t = np.arange(int(length*sr))/sr
        voice = np.zeros_like(t)
        for x in w: voice[int(x['s']*sr):int(x['e']*sr)] = .4*np.sin(2*np.pi*180*t[int(x['s']*sr):int(x['e']*sr)])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, NO_AI):
            tmp = Path(tmp)
            with wave.open(str(tmp/'a.wav'), 'wb') as f:
                f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr); f.writeframes((voice*32767).astype('<i2').tobytes())
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=s=640x360:r=30:d={length:.2f}', '-i', str(tmp/'a.wav'),
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(tmp/'clip.mp4')], check=True)
            prep = {'words': w, 'duration': length, 'cuts': [], 'sheets': []}
            plan, who = planner.plan_edit('edit this video', tmp, prep, [[0, length]], [])
            plan.end_line = 'Keep it wild'
            first = engine.make(tmp/'clip.mp4', w, plan, tmp/'v001'/'edited.mp4', use_matte=False, lines=180)
            project.save(tmp/'v001', plan, dict(first), who, 'edit this video')
            self.assertEqual(first['size'], '320x180')                       # original shape by default
            self.assertTrue(first['timeline']['dialogue'] and first['timeline']['shots'])
            self.assertEqual(set(first['timings']), {'dialogue', 'framing', 'broll', 'sound', 'picture'})

            reopened = project.load(tmp/'v001')                               # a later session, any model or none
            changed, done, left = revise.apply('make it a reel and remove the music', reopened)
            self.assertEqual(left, [])
            second = engine.make(tmp/'clip.mp4', w, changed, tmp/'v002'/'edited.mp4', use_matte=False, lines=180)
            self.assertEqual(second['size'], '180x320')                      # reframed 9:16
            self.assertEqual(second['timeline']['dialogue'], first['timeline']['dialogue'])   # same cut, only the switches moved
            probe = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration', '-of', 'json',
                                               str(tmp/'v002'/'edited.mp4')], capture_output=True, text=True).stdout)
            self.assertEqual({s['codec_type'] for s in probe['streams']}, {'video', 'audio'})
            self.assertAlmostEqual(float(probe['format']['duration']), second['seconds'], delta=.5)
