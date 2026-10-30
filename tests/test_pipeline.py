"""Real FFmpeg coverage; AI outputs are deterministic stubs, with no downloads."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import app1
from backend.core import jobs as core_jobs
from backend.core import storage as core_storage
import backend.core.storage
import numpy as np
from starlette.datastructures import UploadFile


class PipelineTests(unittest.TestCase):
    def setUp(self):
        mode = patch.dict(os.environ, {'CASCADE_METADATA_STORE': 'local'})
        mode.start()
        self.addCleanup(mode.stop)



    def test_local_storage_needs_no_aws_calls(self):
        with patch.dict(os.environ, {'CASCADE_STORAGE': 'local'}), patch.object(backend.core.storage, 's3_client') as client:
            self.assertEqual(core_storage.upload_clip_files(Path('unused'), 'job', 'clip.mp4', 'clip.vtt'), {'storage': 'local'})
            client.assert_not_called()

    def test_timeout_and_cancellation_errors_are_actionable(self):
        self.assertIn('Timed out', core_jobs.processing_error(TimeoutError(), 'analyzing visuals'))
        self.assertIn('cancelled', core_jobs.processing_error(core_jobs.JobCancelled(), 'analyzing visuals'))

    def test_s3_credentials_are_checked_before_processing(self):
        session = Mock()
        session.get_credentials.return_value = None
        with patch.dict(os.environ, {'CASCADE_STORAGE': 's3', 'S3_BUCKET_NAME': 'test'}), \
             patch.object(backend.core.storage.boto3, 'Session', return_value=session):
            with self.assertRaises(core_jobs.HTTPException) as caught:
                core_storage.validate_clip_storage()
        self.assertIn('AWS credentials are missing', caught.exception.detail)


    def test_visual_pipeline_renders_and_transcribes_only_selected_audio(self):
        fake_search = types.ModuleType('sentence_transformers')
        fake_search.SentenceTransformer = Mock()
        with patch.dict(sys.modules, {'sentence_transformers': fake_search}):
            router = importlib.import_module('backend.video_search.router')
        class Encoder:
            def encode(self, values, **kwargs):
                return np.array([1., 0.]) if isinstance(values, str) else np.array([[1., 0.]] * len(values))
        seen_audio = []
        self_test = self
        def fake_transcribe(path, work=None, progress=None, info=None):
            # Deepgram stand-in: it must only ever be sent the short selected-clip audio
            seen_audio.append(Path(path).name)
            self_test.assertLessEqual(router.get_duration(Path(path)), 15.1)
            return [{'start': 0., 'end': 1., 'text': 'Test caption', 'speaker': None}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=10:d=18',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=18', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', str(source)], check=True, timeout=30)
            messages = []
            with patch.object(router, 'OUTPUTS', root), patch.object(router, 'load_models'), \
                 patch.object(router, 'visual_model', Encoder()), patch.object(router, 'transcribe_media', fake_transcribe):
                with source.open('rb') as file:
                    result = router.search_video(UploadFile(file, filename='source.mp4'), 'blue screen', 'visual', 15, messages.append)
            self.assertEqual(seen_audio, ['selected_1.wav'])
            self.assertIn('Test caption', result['captions_vtt'])
            output = root / Path(result['clip_url']).name
            self.assertTrue(output.is_file())
            self.assertAlmostEqual(router.get_duration(output), 15, delta=.2)
            self.assertTrue(any('Rendering' in message for message in messages))
            for stage in ('Frame extraction', 'Prompt embedding', 'Image embeddings', 'Deepgram transcription', 'Video rendering'):
                self.assertIn(stage, result['timings'])
                self.assertGreaterEqual(result['timings'][stage], 0)

            # A sub-second silent source still produces a frame and never needs speech inference.
            short = root / 'short.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=10:d=0.5',
                            '-c:v', 'libx264', str(short)], check=True, timeout=30)
            with patch.object(router, 'OUTPUTS', root), patch.object(router, 'load_models') as models, \
                 patch.object(router, 'visual_model', Encoder()), patch.object(router, 'transcribe_media') as speech:
                with short.open('rb') as file:
                    result = router.search_video(UploadFile(file, filename='short.mp4'), 'blue', 'visual', 15)
                speech.assert_not_called()
                self.assertEqual([c.args[0] for c in models.call_args_list], ['visual'])
                self.assertTrue((root / Path(result['clip_url']).name).is_file())
                self.assertNotIn('Deepgram transcription', result['timings'])


if __name__ == '__main__':
    unittest.main()
