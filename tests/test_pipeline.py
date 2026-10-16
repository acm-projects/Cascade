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
import numpy as np
from PIL import Image
from starlette.datastructures import UploadFile


class PipelineTests(unittest.TestCase):
    def test_vision_context_overflow_splits_without_dropping_or_reordering_frames(self):
        completed = []
        sheets = {}
        def preview(images):
            name = 'sheet-' + ','.join(images)
            sheets[name] = images
            return name
        def respond(prompt, images):
            frames = sheets.get(images[0], images)
            if len(frames) > 2:
                raise app1.ResponseError('request exceeds the available context size', 400)
            completed.extend(frames)
            return ','.join(frames)
        messages = []
        with patch.object(app1, 'ask_qwen', side_effect=respond), patch.object(app1, 'scene_preview', side_effect=preview):
            answer = app1.describe_frame_group('describe', ['1', '2', '3', '4', '5'], messages.append)
        self.assertEqual(completed, ['1', '2', '3', '4', '5'])
        self.assertEqual(answer, '1,2\n3\n4,5')
        self.assertTrue(any('splitting' in message for message in messages))

    def test_unrelated_model_errors_are_not_retried(self):
        with patch.object(app1, 'ask_qwen', side_effect=app1.ResponseError('model not found', 404)) as ask, \
             patch.object(app1, 'scene_preview', return_value='sheet.jpg'):
            with self.assertRaises(app1.ResponseError):
                app1.describe_frame_group('describe', ['1', '2'], lambda _: None)
        self.assertEqual(ask.call_count, 1)

    def test_scene_preview_keeps_all_frames_in_one_bounded_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for index in range(5):
                path = Path(tmp) / f'frame_{index}.jpg'
                Image.new('RGB', (100, 300), 'blue').save(path)
                paths.append(path)
            preview = app1.scene_preview(paths)
            with Image.open(preview) as image:
                self.assertEqual(image.size, (672, 488))
            with patch.object(app1, 'ask_qwen', return_value='scene') as ask:
                app1.describe_frame_group('describe', paths, lambda _: None)
            self.assertEqual(len(ask.call_args.kwargs['images']), 1)

    def test_single_frame_context_failure_is_actionable(self):
        with patch.object(app1, 'ask_qwen', side_effect=app1.ResponseError('request exceeds context size', 400)):
            with self.assertRaises(app1.HTTPException) as caught:
                app1.describe_frame_group('describe', ['1'], lambda _: None)
        self.assertIn('CASCADE_MODEL_CONTEXT', caught.exception.detail)

    def test_local_storage_needs_no_aws_calls(self):
        with patch.dict(os.environ, {'CASCADE_STORAGE': 'local'}), patch.object(app1, 's3_client') as client:
            self.assertEqual(app1.upload_clip_files(Path('unused'), 'job', 'clip.mp4', 'clip.vtt'), {'storage': 'local'})
            client.assert_not_called()

    def test_timeout_and_cancellation_errors_are_actionable(self):
        self.assertIn('Timed out', app1.processing_error(TimeoutError(), 'analyzing visuals'))
        self.assertIn('cancelled', app1.processing_error(app1.JobCancelled(), 'analyzing visuals'))

    def test_s3_credentials_are_checked_before_processing(self):
        session = Mock()
        session.get_credentials.return_value = None
        with patch.dict(os.environ, {'CASCADE_STORAGE': 's3', 'S3_BUCKET_NAME': 'test'}), \
             patch.object(app1.boto3, 'Session', return_value=session):
            with self.assertRaises(app1.HTTPException) as caught:
                app1.validate_clip_storage()
        self.assertIn('AWS credentials are missing', caught.exception.detail)

    def test_failed_scoring_is_not_reported_as_no_match(self):
        observations = [{'start': 0, 'end': 3, 'text': 'blue screen'}]
        with patch.object(app1, 'ask_qwen', side_effect=RuntimeError('invalid JSON')):
            with self.assertRaises(RuntimeError):
                app1.score_observations(observations, 'blue', 'blue screen', lambda _: None)

    def test_visual_pipeline_renders_and_transcribes_only_selected_audio(self):
        fake_speech = types.ModuleType('faster_whisper')
        fake_speech.WhisperModel = Mock()
        fake_search = types.ModuleType('sentence_transformers')
        fake_search.SentenceTransformer = Mock()
        with patch.dict(sys.modules, {'faster_whisper': fake_speech, 'sentence_transformers': fake_search}):
            router = importlib.import_module('backend.video_search.router')
        class Encoder:
            def encode(self, values, **kwargs):
                return np.array([1., 0.]) if isinstance(values, str) else np.array([[1., 0.]] * len(values))
        seen_audio = []
        class Speech:
            def transcribe(self, path, **kwargs):
                seen_audio.append(Path(path).name)
                self_duration = router.get_duration(Path(path))
                self_test.assertLessEqual(self_duration, 15.1)
                return iter([types.SimpleNamespace(start=0., end=1., text='Test caption')]), None
        self_test = self
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=10:d=18',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=18', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', str(source)], check=True, timeout=30)
            messages = []
            with patch.object(router, 'OUTPUTS', root), patch.object(router, 'load_models'), \
                 patch.object(router, 'visual_model', Encoder()), patch.object(router, 'whisper_model', Speech()):
                with source.open('rb') as file:
                    result = router.search_video(UploadFile(file, filename='source.mp4'), 'blue screen', 'visual', 15, messages.append)
            self.assertEqual(seen_audio, ['selected_1.wav'])
            self.assertIn('Test caption', result['captions_vtt'])
            output = root / Path(result['clip_url']).name
            self.assertTrue(output.is_file())
            self.assertAlmostEqual(router.get_duration(output), 15, delta=.2)
            self.assertTrue(any('Rendering' in message for message in messages))
            for stage in ('Frame extraction', 'Prompt embedding', 'Image embeddings', 'Whisper transcription', 'Video rendering'):
                self.assertIn(stage, result['timings'])
                self.assertGreaterEqual(result['timings'][stage], 0)

            # A sub-second silent source still produces a frame and never needs speech inference.
            short = root / 'short.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=10:d=0.5',
                            '-c:v', 'libx264', str(short)], check=True, timeout=30)
            with patch.object(router, 'OUTPUTS', root), patch.object(router, 'load_models') as models, \
                 patch.object(router, 'visual_model', Encoder()), patch.object(router, 'whisper_model') as speech:
                with short.open('rb') as file:
                    result = router.search_video(UploadFile(file, filename='short.mp4'), 'blue', 'visual', 15)
                speech.transcribe.assert_not_called()
                self.assertEqual([c.args[0] for c in models.call_args_list], ['visual'])
                self.assertTrue((root / Path(result['clip_url']).name).is_file())
                self.assertNotIn('Whisper transcription', result['timings'])


if __name__ == '__main__':
    unittest.main()
