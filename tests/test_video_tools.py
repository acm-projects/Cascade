import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from backend import video_tools


class SubtitleBinaryTests(unittest.TestCase):
    def setUp(self): video_tools._subtitle_binary.cache_clear()
    def tearDown(self): video_tools._subtitle_binary.cache_clear()

    def test_selects_installed_full_build_if_default_has_no_subtitles(self):
        def filters(command,**kwargs):
            return SimpleNamespace(stdout=' .. subtitles V->V Render subtitles' if 'ffmpeg-full' in command[0] else ' .. scale V->V Scale frames')
        with patch.dict(os.environ,{'CASCADE_FFMPEG':''}), patch.object(video_tools.shutil,'which',return_value='/opt/homebrew/bin/ffmpeg'), patch.object(video_tools.subprocess,'run',side_effect=filters):
            self.assertEqual(os.path.normpath(video_tools.subtitle_ffmpeg()),os.path.normpath('/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg'))

    def test_compatible_default_is_used_without_fallback(self):
        with patch.dict(os.environ,{'CASCADE_FFMPEG':''}), patch.object(video_tools.shutil,'which',return_value='/usr/bin/ffmpeg'), patch.object(video_tools.subprocess,'run',return_value=SimpleNamespace(stdout=' .. subtitles V->V Render subtitles')) as run:
            self.assertEqual(video_tools.subtitle_ffmpeg(),'/usr/bin/ffmpeg')
            self.assertEqual(run.call_count,1)

    def test_incompatible_explicit_binary_has_actionable_error(self):
        with patch.dict(os.environ,{'CASCADE_FFMPEG':'/configured/ffmpeg'}), patch.object(video_tools.subprocess,'run',return_value=SimpleNamespace(stdout='')):
            with self.assertRaises(HTTPException) as caught: video_tools.subtitle_ffmpeg()
            self.assertEqual(caught.exception.status_code,503)
            self.assertIn('CASCADE_FFMPEG',caught.exception.detail)

if __name__=='__main__': unittest.main()
