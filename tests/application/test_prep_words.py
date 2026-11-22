"""Word timings for the Cinema engine's prep step (Deepgram), offline."""
import unittest
from unittest import mock

from backend.editor.ai_edit import prep


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
