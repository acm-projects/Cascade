"""OpenAI protocol and real four-clip rendering, with every API call mocked."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import httpx
import app1
import openai_scene as scene


def candidate(start, end, score=8):
    return {'start': start, 'end': end, 'score': score, 'title': 'A funny moment', 'explanation': 'Setup, surprise, and reaction.'}


def completed(proposal):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps(proposal)}]}], 'usage': {'input_tokens': 100, 'output_tokens': 50}}


class OpenAISceneTests(unittest.TestCase):
    def setUp(self):
        mode = patch.dict(os.environ, {'CASCADE_METADATA_STORE': 'local'})
        mode.start()
        self.addCleanup(mode.stop)

    def test_four_distinct_candidates_survive_adjacent_boundaries(self):
        proposal = scene.Proposal.model_validate({'candidates': [candidate(i, i + 10) for i in (0, 10, 20, 30)],
                                                   'insufficient_material_reason': ''})
        self.assertEqual(len(scene.choose_clips(proposal, 40, 15)), 4)

    def test_selection_avoids_greedy_overlap_and_invalid_bounds(self):
        values = [candidate(0, 22, 10), candidate(0, 9), candidate(10, 19), candidate(20, 29),
                  candidate(30, 39), candidate(35, 50, 10), candidate(0, 9), candidate(40, 39)]
        proposal = scene.Proposal(candidates=values, insufficient_material_reason='')
        result = scene.choose_clips(proposal, 40, 15)
        self.assertEqual([(c['start'], c['end']) for c in result], [(0, 9), (10, 19), (20, 29), (30, 39)])

    def test_does_not_pad_weak_or_duplicate_matches(self):
        proposal = scene.Proposal(candidates=[candidate(0, 10), candidate(0, 10), candidate(10, 20, 2)],
                                   insufficient_material_reason='Only one genuine joke.')
        self.assertEqual(len(scene.choose_clips(proposal, 40, 15)), 1)

    def test_provider_auth_failure_is_safe_and_not_retried(self):
        calls = []
        real_client = httpx.Client
        def handle(request):
            calls.append(request)
            return httpx.Response(401, json={'error': {'message': 'raw provider error with sensitive data'}})
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-secret'}), \
             patch.object(scene.httpx, 'Client', side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs)):
            with self.assertRaises(scene.SceneAnalysisError) as caught:
                scene.request_proposal({'model': 'gpt-5.4-mini'}, lambda _: None)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('test-secret', str(caught.exception))
        self.assertIn('API key', str(caught.exception))

    def test_refusal_and_incomplete_output_fail_clearly(self):
        for payload in ({'status': 'incomplete'}, {'status': 'completed', 'output': [
            {'content': [{'type': 'refusal', 'refusal': 'No'}]}]}):
            real_client = httpx.Client
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
                 patch.object(scene.httpx, 'Client', side_effect=lambda **kwargs: real_client(
                     transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)), **kwargs)):
                with self.assertRaises(scene.SceneAnalysisError):
                    scene.request_proposal({'model': 'gpt-5.4-mini'}, lambda _: None)

    def test_temporary_service_failure_retries_only_once(self):
        calls = []
        real_client = httpx.Client
        def handle(request):
            calls.append(request)
            return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=completed(
                {'candidates': [], 'insufficient_material_reason': 'No supported moments.'}))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), patch.object(scene.time, 'sleep'), \
             patch.object(scene.httpx, 'Client', side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs)):
            proposal, _ = scene.request_proposal({'model': 'gpt-5.4-mini'}, lambda _: None)
        self.assertEqual(len(calls), 2)
        self.assertEqual(proposal.candidates, [])

    def test_exhausted_quota_is_not_retried(self):
        calls = []
        real_client = httpx.Client
        def handle(request):
            calls.append(request)
            return httpx.Response(429, json={'error': {'code': 'insufficient_quota'}})
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
             patch.object(scene.httpx, 'Client', side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs)):
            with self.assertRaises(scene.SceneAnalysisError) as caught:
                scene.request_proposal({'model': 'gpt-5.4-mini'}, lambda _: None)
        self.assertIn('billing', str(caught.exception))
        self.assertEqual(len(calls), 1)

    def test_api_pipeline_renders_four_real_clips_and_reuses_paid_selection(self):
        proposal = {'candidates': [candidate(i, i + 9) for i in (0, 10, 20, 30)], 'insufficient_material_reason': ''}
        requests = []
        real_client = httpx.Client
        def handle(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertFalse(body['store'])
            self.assertTrue(body['text']['format']['strict'])
            inputs = body['input'][1]['content']
            self.assertTrue(any(c['type'] == 'input_image' for c in inputs))
            return httpx.Response(200, json=completed(proposal), headers={'x-request-id': 'test-request'})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_id = 'b' * 32
            folder = root / job_id
            folder.mkdir()
            source = folder / 'source.video'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=10:d=40',
                            '-c:v', 'libx264', '-f', 'mp4', str(source)], check=True, timeout=30)
            app1.save_json(folder / 'owner.json', {'user_id': 'test', 'user_folder': 'users'})
            app1.jobs[job_id] = {'state': 'queued', 'message': 'Waiting', 'clips': []}
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'CASCADE_STORAGE': 'local'}), \
                 patch.object(app1, 'JOBS_DIR', root), patch.object(app1, 'transcribe_video', return_value=[]), \
                 patch.object(app1.httpx, 'get', side_effect=AssertionError('Ollama must not be called')), \
                 patch.object(scene.httpx, 'Client', side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs)):
                app1.process_openai_upload(job_id, source, 'four funny clips', 'both', 15)
                result = app1.jobs[job_id]
                self.assertEqual(result['state'], 'done')
                self.assertEqual(len(result['clips']), 4)
                for clip in result['clips']:
                    video = folder / Path(clip['clip_url']).name
                    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                      'format=duration', '-of', 'json', str(video)], timeout=30))
                    self.assertAlmostEqual(float(probe['format']['duration']), 9, delta=.2)
                _, metadata = scene.select_scenes(source, folder, 40, [], 'four funny clips', 15,
                    lambda _: None, lambda _: None, app1.run_command, app1.save_json)
                self.assertTrue(metadata['selection_cached'])
                self.assertEqual(len(requests), 1)
                _, metadata = scene.select_scenes(source, folder, 40, [], 'four surprising moments', 15,
                    lambda _: None, lambda _: None, app1.run_command, app1.save_json)
                self.assertFalse(metadata['selection_cached'])
                self.assertEqual(len(requests), 2)
                self.assertNotIn('test-key', (folder / 'openai_selection.json').read_text())
            app1.jobs.pop(job_id, None)
