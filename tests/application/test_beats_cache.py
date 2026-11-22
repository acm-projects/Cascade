"""Beat analysis is cached by file contents, so a clip or song downloaded again to a new path is not re-measured."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.editor import beats


class BeatCache(unittest.TestCase):
    def test_the_same_audio_at_a_new_path_is_measured_once(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder)/'a'/'clip_1.mp3'; first.parent.mkdir()
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', str(first)], check=True)
            second = Path(folder)/'b'/'clip_1.mp3'; second.parent.mkdir()
            shutil.copy(first, second)   # what a second S3 download looks like: same bytes, new temporary path
            beats._RESULTS.clear()
            with patch.object(beats, '_measure', wraps=beats._measure) as measure:
                self.assertEqual(beats.analyze(first), beats.analyze(second))
            self.assertEqual(measure.call_count, 1)


if __name__ == '__main__':
    unittest.main()
