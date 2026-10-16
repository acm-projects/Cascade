"""The clip agent as the website's selection engine.

Real FFmpeg cutting, real captions, real job records and ownership checks; the AI itself (the agent,
Deepgram, the model) is a deterministic stub, so nothing here touches the network or costs money.
Run with python -m unittest discover -s tests -v.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app1
from backend.agent.website import SelectionError
from backend.cascade_llm import LLMConfigError
from backend.cascade_stt import TranscriptionError

JOB = 'b' * 32
USER = 'user-a'
TRANSCRIPT = [
    {'start': 3.0, 'end': 6.0, 'text': 'first line of speech', 'speaker': 0},
    {'start': 13.0, 'end': 16.0, 'text': 'second line of speech', 'speaker': 1},
]


def fake_agent(record, steps=('Indexing video', 'Agent turn 1/8', "Tool call: search_video(query='a joke')", 'Agent turn 2/8')):
    def select(video_path, duration, search, target, progress, stage):
        record.update(video_path=video_path, duration=duration, search=search, target=target)
        stage('Transcript and search index')
        for step in steps:
            progress(step)
        stage('AI agent selection')
        clips = [{'start': 2.0 + 9 * i, 'end': 11.0 + 9 * i, 'title': f'Moment {i}', 'explanation': f'because {i}'} for i in range(4)]
        return clips, TRANSCRIPT, {'provider': 'anthropic', 'model': 'claude-haiku-5-5', 'selection_note': ''}
    return select


class AgentEngineTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'CASCADE_STORAGE': 'local', 'LLM_PROVIDER': 'anthropic',
                                           'ANTHROPIC_API_KEY': 'test-key', 'DEEPGRAM_API_KEY': 'test-key'})
        self.env.start()
        os.environ.pop('CASCADE_JOB_TIMEOUT', None)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.directory = patch.object(app1, 'JOBS_DIR', self.root)
        self.directory.start()
        self.auth = patch.object(app1, 'verify_clerk_token', side_effect=lambda token: token)
        self.auth.start()
        self.client = TestClient(app1.app)
        self.headers = {'Authorization': 'Bearer ' + USER}
        self.folder = self.root / JOB
        self.folder.mkdir()
        self.source = self.folder / 'source.video'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=10:d=40',
                        '-c:v', 'libx264', '-f', 'mp4', str(self.source)], check=True, timeout=30)
        app1.save_json(self.folder / 'owner.json', {'user_id': USER, 'user_folder': 'users'})
        app1.jobs[JOB] = {'state': 'queued', 'message': 'Waiting', 'clips': []}

    def tearDown(self):
        app1.jobs.pop(JOB, None)
        self.env.stop()
        self.auth.stop()
        self.directory.stop()
        self.temp.cleanup()

    def run_job(self, select, search='four funny clips', target=15):
        with patch.object(app1, 'select_with_agent', side_effect=select):
            app1.process_upload(JOB, self.source, search, 'both', target)
        return app1.jobs[JOB]

    # ------------------------------------------------------------------ the happy path
    def test_job_cuts_four_real_clips_with_titles_captions_and_a_step_log(self):
        record = {}
        job = self.run_job(fake_agent(record))
        self.assertEqual(job['state'], 'done')
        self.assertEqual(len(job['clips']), 4)
        self.assertEqual([c['title'] for c in job['clips']], [f'Moment {i}' for i in range(4)])
        self.assertEqual(job['provider'], 'anthropic')
        # the agent is handed the real request, the video length and the user's chosen clip length
        self.assertEqual((record['search'], record['target']), ('four funny clips', 15))
        self.assertAlmostEqual(record['duration'], 40, delta=.5)
        for number in range(1, 5):
            probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                                        '-of', 'json', str(self.folder / f'clip_{number}.mp4')], timeout=30))
            self.assertAlmostEqual(float(probe['format']['duration']), 9, delta=.2)
        # captions come from the agent's Deepgram transcript, with times relative to each clip
        first = (self.folder / 'clip_1.vtt').read_text()
        self.assertIn('first line of speech', first)
        self.assertIn('00:00:01.000 --> 00:00:04.000', first)
        self.assertNotIn('second line', first)
        second = (self.folder / 'clip_2.vtt').read_text()  # clip 2 runs 11s-20s
        self.assertIn('second line of speech', second)
        self.assertIn('00:00:02.000 --> 00:00:05.000', second)
        # nothing the agent needed for its index is stored with the job
        self.assertFalse([p for p in self.folder.rglob('*') if p.suffix in ('.jpg', '.mp3')])

    def test_steps_are_recorded_live_persisted_and_served(self):
        job = self.run_job(fake_agent({}))
        for step in ('Reading uploaded video...', 'Indexing video', 'Agent turn 1/8', 'Cutting clip 1/4...', 'Saving clip 4/4...'):
            self.assertIn(step, job['steps_log'])
        self.assertLess(job['steps_log'].index('Agent turn 1/8'), job['steps_log'].index('Cutting clip 1/4...'))
        saved = json.loads((self.folder / 'results.json').read_text())
        self.assertEqual(saved['steps_log'], job['steps_log'])
        self.assertIn('timings', saved)
        # the page polls /api/features/<job>; it must carry the steps while running AND after a restart
        live = self.client.get('/api/features/' + JOB, headers=self.headers).json()
        self.assertEqual(live['steps_log'], job['steps_log'])
        app1.jobs.clear()
        restored = self.client.get('/api/features/' + JOB, headers=self.headers).json()
        self.assertEqual((restored['state'], restored['steps_log']), ('done', job['steps_log']))
        self.assertEqual(self.client.get('/jobs/' + JOB, headers=self.headers).json()['steps_log'], job['steps_log'])
        # another user cannot read someone else's steps
        self.assertEqual(self.client.get('/api/features/' + JOB, headers={'Authorization': 'Bearer user-b'}).status_code, 404)

    def test_the_step_log_is_capped(self):
        many = tuple(f'step {i}' for i in range(app1.MAX_STEPS + 50))
        job = self.run_job(fake_agent({}, steps=many))
        self.assertEqual(job['state'], 'done')
        self.assertLessEqual(len(job['steps_log']), app1.MAX_STEPS)
        self.assertIn('Saving clip 4/4...', job['steps_log'])  # the newest steps are the ones kept
        self.assertNotIn('step 0', job['steps_log'])         # the oldest were dropped

    # ------------------------------------------------------------------ time limit
    def test_there_is_no_default_time_limit_but_an_optional_safety_net(self):
        ticks = iter([0.0] + [5000.0] * 10000)  # the job "takes" over an hour
        with patch.object(app1.time, 'monotonic', side_effect=lambda: next(ticks)):
            job = self.run_job(fake_agent({}))
        self.assertEqual(job['state'], 'done')  # the old 900s default would have stopped this

        app1.jobs[JOB] = {'state': 'queued', 'message': 'Waiting', 'clips': []}
        ticks = iter([0.0] + [5000.0] * 10000)
        with patch.object(app1.time, 'monotonic', side_effect=lambda: next(ticks)), \
             patch.dict(os.environ, {'CASCADE_JOB_TIMEOUT': '900'}):
            job = self.run_job(fake_agent({}))
        self.assertEqual(job['state'], 'error')
        self.assertIn('Timed out', job['message'])

    # ------------------------------------------------------------------ stop button
    def test_cancel_stops_the_agent_at_its_next_step(self):
        reached = []

        def select(video_path, duration, search, target, progress, stage):
            progress('Agent turn 1/8')
            app1.jobs[JOB]['cancel_requested'] = True  # the user clicks "Stop processing"
            progress('Tool call: search_video(...)')
            reached.append('past the stop')            # must never run
            return [], [], {}

        job = self.run_job(select)
        self.assertEqual(reached, [])
        self.assertEqual(job['state'], 'error')
        self.assertIn('cancelled', job['message'])
        self.assertFalse((self.folder / 'clip_1.mp4').exists())

    # ------------------------------------------------------------------ errors shown to users
    def test_known_errors_show_their_safe_message(self):
        for error in (TranscriptionError('Deepgram rejected the API key (check DEEPGRAM_API_KEY in .env).'),
                      LLMConfigError("ANTHROPIC_API_KEY is not set (LLM_PROVIDER is 'anthropic')."),
                      SelectionError('The agent could not pick any clips.')):
            self.assertEqual(app1.processing_error(error, 'selecting'), str(error))

    def test_provider_http_errors_become_actionable_without_leaking_details(self):
        class ApiError(Exception):
            def __init__(self, status):
                super().__init__('request failed with key sk-secret-123')
                self.status_code = status

        for status, needle in ((401, 'rejected the API key'), (403, 'rejected the API key'), (429, 'rate limiting')):
            message = app1.processing_error(ApiError(status), 'selecting')
            self.assertIn(needle, message)
            self.assertNotIn('sk-secret', message)
        # a validation error from our own code keeps its own status and text
        self.assertEqual(app1.processing_error(app1.HTTPException(401, 'Please sign in again.'), 'x'), 'Please sign in again.')

    def test_unexpected_errors_are_generic_and_never_show_internals(self):
        def select(*args):
            raise RuntimeError('boom with key sk-secret-123 at https://signed.example/?sig=abc')

        job = self.run_job(select)
        self.assertEqual(job['state'], 'error')
        self.assertNotIn('sk-secret', job['message'])
        self.assertNotIn('signed.example', job['message'])
        self.assertIn('Processing failed', job['message'])
        failure = json.loads((self.folder / 'failure.json').read_text())
        self.assertIn('steps_log', failure)  # a failed job still shows where it stopped, after a restart too


if __name__ == '__main__':
    unittest.main()
