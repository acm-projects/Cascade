"""Stage 1 of the beats pipeline: transcribe(video) -> [{word,start,end}], offline (the speech model is mocked)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.editor.ai_edit import prep
from backend.editor.ai_edit.beats import transcribe as asr

REFERENCE = json.loads((asr.EXAMPLES/'transcript_full.json').read_text())


def shifted(words, by):
    return [{**w, 'start': round(w['start']+by, 2), 'end': round(w['end']+by, 2)} for w in words]


class Compare(unittest.TestCase):
    def test_reference_matches_itself(self):
        result = asr.compare(REFERENCE, REFERENCE)
        self.assertTrue(result['passed'])
        self.assertEqual(result['coverage'], 1.0)
        self.assertEqual(result['start_max'], 0.0)

    def test_tolerance_is_about_three_tenths_of_a_second(self):
        self.assertTrue(asr.compare(shifted(REFERENCE, .25), REFERENCE)['passed'])
        self.assertFalse(asr.compare(shifted(REFERENCE, .45), REFERENCE)['passed'])

    def test_case_punctuation_and_a_few_misheard_words_do_not_break_matching(self):
        ours = [{**w, 'word': w['word'].upper().strip('.,?')} for w in REFERENCE]
        ours[10]['word'] = 'missed'
        del ours[50]
        ours.insert(80, {'word': 'uh', 'start': ours[80]['start'], 'end': ours[80]['start']})
        result = asr.compare(ours, REFERENCE)
        self.assertTrue(result['passed'])
        self.assertGreater(result['coverage'], .98)

    def test_too_few_words_fails(self):
        self.assertFalse(asr.compare(REFERENCE[:100], REFERENCE)['passed'])
        self.assertFalse(asr.compare([], REFERENCE)['passed'])


class Normalize(unittest.TestCase):
    def test_internal_words_become_sorted_non_overlapping_word_start_end(self):
        raw = [{'w': ' world', 's': 1.004, 'e': 1.6}, {'w': 'hello', 's': .2, 'e': 1.2}, {'w': '', 's': 2, 'e': 3}]
        self.assertEqual(asr.normalize(raw), [{'word': 'hello', 'start': .2, 'end': 1.0}, {'word': 'world', 'start': 1.0, 'end': 1.6}])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs FFmpeg')
class Transcribe(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.video = self.folder/'clip.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=gray:s=160x90:d=2', '-f', 'lavfi',
                        '-i', 'sine=frequency=220:duration=2', '-shortest', '-c:v', 'libx264', '-c:a', 'aac', str(self.video)], check=True)
        self.patch = mock.patch.object(prep.tools, 'ffmpeg', return_value='ffmpeg')
        self.patch.start(); self.addCleanup(self.patch.stop)

    def test_audio_is_extracted_from_the_video_and_words_come_back_in_the_standard_shape(self):
        seen = {}
        def fake(mono, samples, db, folder):
            seen['seconds'] = len(samples)/16000
            return [{'w': 'Hello', 's': .1, 'e': .5}, {'w': 'there.', 's': .5, 'e': 1.0}]
        with mock.patch.object(prep, '_transcribe', side_effect=fake):
            words = asr.transcribe(self.video, self.folder/'work')
        self.assertAlmostEqual(seen['seconds'], 2, delta=.1)   # 16 kHz mono from the video's own audio
        self.assertEqual(words, [{'word': 'Hello', 'start': .1, 'end': .5}, {'word': 'there.', 'start': .5, 'end': 1.0}])

    def test_caches_until_the_video_changes(self):
        with mock.patch.object(prep, '_transcribe', return_value=[{'w': 'hi', 's': 0, 'e': .4}]) as dg:
            first = asr.transcribe(self.video, self.folder/'work')
            again = asr.transcribe(self.video, self.folder/'work')
        self.assertEqual(first, again)
        self.assertEqual(dg.call_count, 1)

    def test_no_transcriber_is_a_clear_error(self):
        with mock.patch.object(prep, '_transcribe', return_value=None):
            with self.assertRaises(asr.TranscriptionUnavailable):
                asr.transcribe(self.video, self.folder/'work')


class DeepgramWords(unittest.TestCase):
    def test_without_a_deepgram_key_prep_falls_back(self):
        from backend.cascade_stt import TranscriptionError
        with mock.patch('backend.cascade_stt.transcribe_words', side_effect=TranscriptionError('no key')):
            self.assertIsNone(prep._transcribe('voice.wav', None, [], None))

    def test_word_times_are_snapped_and_never_overlap(self):
        import numpy as np
        db = np.full(300, -60.); db[50:250] = -20.   # voice from 0.5 s to 2.5 s
        words = [{'w': 'Hello', 's': .52, 'e': 1.2}, {'w': 'there.', 's': 1.1, 'e': 2.4}]
        with mock.patch('backend.cascade_stt.transcribe_words', return_value=words):
            out = prep._transcribe('voice.wav', None, db, None)
        self.assertEqual([w['w'] for w in out], ['Hello', 'there.'])
        self.assertLessEqual(out[0]['e'], out[1]['s'] + .04)
        self.assertLess(out[0]['s'], out[1]['s'])


if __name__ == '__main__':
    unittest.main()
