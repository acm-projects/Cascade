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

NO_AI = {'CASCADE_EDITOR_CLAUDE': 'off', 'CASCADE_EDIT_PLANNER': 'rules', 'CASCADE_EDIT_PLANNER_CMD': ''}
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

    def test_openai_plan_receives_images_and_ignores_old_claude_configuration(self):
        from backend.editor import openai_edit
        w = words(STORY)
        answer = plans.auto(w).model_dump(); answer['title'] = 'OpenAI directed'
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'sheet.jpg').write_bytes(b'fixture-jpeg')
            with patch.dict(os.environ, {'CASCADE_EDIT_PLANNER':'claude'}), patch.object(openai_edit, 'ask', return_value=answer) as ask:
                plan, who = planner.plan_edit('edit this video', tmp, {'words':w,'duration':20,'cuts':[],'sheets':['sheet.jpg']}, [[0,20]], [])
            self.assertEqual(plan.title, 'OpenAI directed')
            self.assertIn('OpenAI',who)
            self.assertEqual(ask.call_args.args[3],[('sheet.jpg',b'fixture-jpeg')])



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
            self.assertEqual(first['size'], '180x320')                       # 9:16 (iPhone) by default
            self.assertFalse(plan.settings.stamp)                            # no Cascade sign-off by default
            self.assertTrue(first['timeline']['dialogue'] and first['timeline']['shots'])
            self.assertEqual(set(first['timings']), {'dialogue', 'framing', 'broll', 'sound', 'picture'})

            reopened = project.load(tmp/'v001')                               # a later session, any model or none
            changed, done, left = revise.apply('back to original shape and remove the music', reopened)
            self.assertEqual(left, [])
            second = engine.make(tmp/'clip.mp4', w, changed, tmp/'v002'/'edited.mp4', use_matte=False, lines=180)
            self.assertEqual(second['size'], '320x180')                      # back to the source shape
            self.assertEqual(second['timeline']['dialogue'], first['timeline']['dialogue'])   # same cut, only the switches moved
            probe = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration', '-of', 'json',
                                               str(tmp/'v002'/'edited.mp4')], capture_output=True, text=True).stdout)
            self.assertEqual({s['codec_type'] for s in probe['streams']}, {'video', 'audio'})
            self.assertAlmostEqual(float(probe['format']['duration']), second['seconds'], delta=.5)


class OutputRules(unittest.TestCase):
    def test_new_edits_are_about_15_seconds_vertical_and_unsigned(self):
        from backend.editor.ai_edit.cinema import planner
        from backend.editor.ai_edit.cinema.plan import CinemaPlan
        words, t = [], 0.
        for n in range(120):   # 40 s of speech, a sentence every 6 words
            words.append({'w': f'word{n}' + ('.' if n % 6 == 5 else ''), 's': t, 'e': t+.3}); t += .33
        plan = CinemaPlan.model_validate({'story': [{'from_word': 0, 'to_word': 59}, {'from_word': 60, 'to_word': 119, 'role': 'payoff'}],
                                          'broll': [{'from_word': 100, 'to_word': 102, 'query': 'forest aerial'}]})
        plan = planner.output(plan, words)
        spoken = sum(words[i]['e']-words[i]['s'] for s in plan.story for i in range(s.from_word, s.to_word+1))
        self.assertLessEqual(spoken, 14.5)
        self.assertGreater(spoken, 11)
        self.assertTrue(words[plan.story[-1].to_word]['w'].endswith('.'))   # ends on a complete sentence
        self.assertEqual((plan.settings.ratio, plan.settings.stamp), ('9:16', False))
        self.assertEqual(plan.broll, [])                                    # b-roll on cut lines is gone


class VisualEdits(unittest.TestCase):
    """Clips where nobody speaks: planned from frames and motion, rendered with no AI (rules planner)."""

    def test_fit_keeps_15_seconds_on_the_beat(self):
        from backend.editor.ai_edit.cinema import visual
        plan = visual.VisualPlan.model_validate({'shots': [{'start': n*3, 'end': n*3+2.3} for n in range(10)]})
        beat = 60/70
        used = visual.fit(plan, 15, beat=beat)
        self.assertLessEqual(used, 15+1e-6)
        self.assertGreater(used, 12)
        edges, t = [], 0.
        for s in plan.shots:
            t += (s.end-s.start)/s.speed; edges.append(t)
        for e in edges: self.assertAlmostEqual(e/(beat/2), round(e/(beat/2)), places=4)   # every cut on the half-beat grid

    def test_shot_edges_move_onto_nearby_camera_cuts(self):
        from backend.editor.ai_edit.cinema import visual
        plan = visual.VisualPlan.model_validate({'shots': [{'start': 4.5, 'end': 6.9}, {'start': 1.0, 'end': 4.4}]})
        visual.check(plan, 10, cuts=[4.53])
        self.assertEqual((plan.shots[0].start, plan.shots[1].end), (4.53, 4.4))
        with self.assertRaises(ValueError):
            visual.check(visual.VisualPlan.model_validate({'shots': [{'start': 8, 'end': 12}]}), 10)

    def test_speechless_clip_edits_end_to_end_without_ai(self):
        from backend.editor.ai_edit import prep as preparation
        from backend.editor.ai_edit.cinema import planner, project, revise, visual
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, NO_AI):
            tmp = Path(tmp)
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=30:d=24',
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(tmp/'clip.mp4')], check=True)
            with self.assertRaises(ValueError):   # the older engines still need speech
                preparation.prepare(tmp/'clip.mp4', [], tmp/'strict', lambda a, s: None, separate=False)
            prep = preparation.prepare(tmp/'clip.mp4', [], tmp/'prep', lambda a, s: None, separate=False, speech_optional=True)
            self.assertEqual(prep['words'], [])
            self.assertEqual(len(prep['motion']), 24)
            plan, who = planner.plan_visual('edit this clip', tmp/'prep', prep, [[0, 24]], [])
            self.assertEqual((who, plan.settings.ratio, plan.settings.stamp, plan.settings.captions), ('rules', '9:16', False, False))
            report = visual.make(tmp/'clip.mp4', plan, tmp/'v001'/'edited.mp4', faces=False, lines=180)
            self.assertEqual(report['size'], '180x320')
            self.assertLessEqual(report['seconds'], 15.05)
            probe = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type:format=duration', '-of', 'json',
                                               str(tmp/'v001'/'edited.mp4')], capture_output=True, text=True).stdout)
            self.assertEqual({s['codec_type'] for s in probe['streams']}, {'video', 'audio'})   # a soundtrack even though the clip had none
            self.assertAlmostEqual(float(probe['format']['duration']), report['seconds'], delta=.5)
            project.save(tmp/'v001', plan, dict(report), who, 'edit this clip')
            reopened = project.load(tmp/'v001')
            self.assertIsInstance(reopened, visual.VisualPlan)
            changed, done, left = revise.apply('make it square and remove the music, shorter', reopened)
            self.assertEqual((changed.settings.ratio, changed.settings.music), ('1:1', False))
            self.assertEqual(left, ['shorter'])   # a spoken-edit rule on a visual edit goes to the planner instead of crashing


def _beat_song(path, bpm=128, seconds=30, drop_beat=16):
    """A test song: a quiet kick, then a loud one from the drop."""
    sr, beat = 44100, 60/bpm
    t = np.arange(int(seconds*sr))/sr
    out = .05*np.sin(2*np.pi*220*t)
    for k in range(int(seconds/beat)):
        i, n = int(k*beat*sr), int(.2*sr)
        tt = np.arange(n)/sr
        out[i:i+n] += (np.sin(2*np.pi*(55+90*np.exp(-tt*30))*tt)*np.exp(-tt*9)*(1. if k >= drop_beat else .2))[:len(out)-i]
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(sr), '-ac', '1', '-i', '-', str(path)],
                   input=(out/np.abs(out).max()*.9).astype(np.float32).tobytes(), check=True)
    return drop_beat*beat


class MusicLibrary(unittest.TestCase):
    """Songs in the Music Library: measured offline (no Deepgram, no OpenAI), cut to and played."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)/'music'; self.dir.mkdir()
        self.drop = _beat_song(self.dir/'Some Artist - Fly High [NCS Release].mp3')
        lyrics = [{'w': w, 's': 4.5+n*.5, 'e': 4.9+n*.5} for n, w in enumerate('we will fly so high tonight'.split())]
        self.patches = [patch.dict(os.environ, {'CASCADE_MUSIC_DIR': str(self.dir), **NO_AI}),
                        patch('backend.editor.ai_edit.cinema.music._lyrics', return_value=lyrics),
                        patch('backend.editor.ai_edit.cinema.music._mood', return_value={'mood': 'uplifting', 'energy': 'high', 'fits': ['sports'], 'genre': 'edm'})]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()

    def test_measures_tempo_drop_and_credit(self):
        from backend.editor.ai_edit.cinema import music
        song = music.library()[0]
        self.assertAlmostEqual(song['bpm'], 128, delta=.3)
        self.assertAlmostEqual(song['beats'][40], 40*60/128, delta=.05)   # no drift across the song
        self.assertAlmostEqual(song['drop'], self.drop, delta=.5)
        self.assertEqual((song['artist'], song['title'], song['ncs']), ('Some Artist', 'Fly High', True))
        self.assertIn('NoCopyrightSounds', song['credit'])
        first = music.sections(song)[0]
        self.assertTrue(self.drop-3 <= first <= self.drop)                # the first section builds into the drop
        self.assertEqual(music.catalogue()[0]['sections'][0]['section'], 0)

    def test_song_edit_cuts_on_beats_with_lyrics_and_plays_the_song(self):
        from backend.editor.ai_edit.cinema import music, planner, visual
        song = music.library()[0]
        clip = Path(self.tmp.name)/'clip.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=30:d=20',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(clip)], check=True)
        plan = visual.VisualPlan.model_validate({'song': song['id'], 'lyrics': 'glitch', 'intro': 'black', 'grade': 'cold', 'sound': 'score',
                                                 'shots': [{'start': n*2, 'end': n*2+1.9, 'effect': e} for n, e in
                                                           enumerate(['flash', 'glitch', 'invert', 'leak', 'zoom', 'whip', None, 'rgb', None])]})
        plan = planner.output(plan, [])
        _, start, grid, lead = visual.song_timing(plan, 15)
        self.assertGreater(lead, 1)
        t = lead
        for s in plan.shots:
            t += (s.end-s.start)/s.speed
            self.assertLess(min(abs(t-g) for g in grid), 1e-6)            # every cut on a beat or half-beat
        lines = visual.lyric_lines(song, start, 15, 'glitch')
        self.assertTrue(lines and all(len(o.data['words']) <= 3 for o in lines))
        report = visual.make(clip, plan, Path(self.tmp.name)/'v001'/'edited.mp4', faces=False, lines=180)
        self.assertIn('Fly High', report['song'])
        self.assertTrue(any(o['kind'] == 'lyric' for o in report['timeline']['overlays']))
        self.assertTrue(any(o['kind'] == 'black' for o in report['timeline']['overlays']))
        self.assertGreater(report['lufs'], -20)                              # the song is audible, not silence

    def test_a_song_plays_under_speech(self):
        from backend.editor.ai_edit.cinema import engine, music
        from backend.editor.ai_edit.cinema.plan import CinemaPlan
        song = music.library()[0]
        plan = CinemaPlan.model_validate({'story': [{'from_word': 0, 'to_word': 0}], 'song': song['id']})
        bed = engine.song_bed(plan, 10)
        self.assertEqual(bed.shape[1], 2)
        self.assertAlmostEqual(len(bed)/48000, 10.1, delta=.05)
        self.assertIsNone(engine.song_bed(plan.model_copy(update={'song': 'nope'}), 10))   # an unknown song: the composed score
