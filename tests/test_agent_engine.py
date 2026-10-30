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
from backend import main as app_main
from backend.routers import clips as clip_routes
from backend.core import jobs as core_jobs
from backend.core import media as core_media
from backend.core import auth
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
        self.directory = patch.object(core_jobs, 'JOBS_DIR', self.root)
        self.directory.start()
        self.auth = patch.object(auth, 'verify_clerk_token', side_effect=lambda token: token)
        self.auth.start()
        self.client = TestClient(app1.app)
        self.headers = {'Authorization': 'Bearer ' + USER}
        self.folder = self.root / JOB
        self.folder.mkdir()
        self.source = self.folder / 'source.video'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=10:d=40',
                        '-c:v', 'libx264', '-f', 'mp4', str(self.source)], check=True, timeout=30)
        core_jobs.save_json(self.folder / 'owner.json', {'user_id': USER, 'user_folder': 'users'})
        core_jobs.jobs[JOB] = {'state': 'queued', 'message': 'Waiting', 'clips': []}

    def tearDown(self):
        core_jobs.jobs.pop(JOB, None)
        self.env.stop()
        self.auth.stop()
        self.directory.stop()
        self.temp.cleanup()

    def run_job(self, select, search='four funny clips', target=15):
        with patch.object(clip_routes, 'select_with_agent', side_effect=select):
            clip_routes.process_upload(JOB, self.source, search, 'both', target)
        return core_jobs.jobs[JOB]

    # ------------------------------------------------------------------ the happy path
    def test_playable_prefix_is_published_before_the_batch_finishes(self):
        original = core_jobs.update_job
        published = []
        def capture(job_id, **fields):
            result = original(job_id, **fields)
            if fields.get('ready_clip_count'):
                self.assertFalse((self.folder / 'results.json').exists())
                published.append([clip['clip_id'] for clip in fields['clips']])
            return result
        with patch.object(core_jobs, 'update_job', side_effect=capture):
            self.assertEqual(self.run_job(fake_agent({}))['state'], 'done')
        self.assertTrue(published)
        for clips in published:
            self.assertEqual(clips, [f'{JOB}:{i}' for i in range(len(clips))])
        self.assertIn('first_clip_ready_seconds', core_jobs.load_json(self.folder / 'results.json'))
    def test_session_exclusions_survive_post_selection_transforms_and_persist(self):
        owner = core_jobs.load_json(self.folder / 'owner.json')
        owner['exclude_windows'] = [[2., 11.]]
        core_jobs.save_json(self.folder / 'owner.json', owner)
        select = fake_agent({})
        received = {}
        def stub(*args, **kwargs):
            received.update(kwargs)
            clips, transcript, metadata = select(*args)
            return clips, transcript, {**metadata, 'intent': 'general'}
        job = self.run_job(stub)
        self.assertEqual(received['exclude_windows'], [[2., 11.]])
        self.assertEqual(job['state'], 'done')
        self.assertEqual(len(job['clips']), 3)
        self.assertIn('3 new clips; others were already in this session', job['selection_note'])
        saved = core_jobs.load_json(self.folder / 'results.json')
        self.assertEqual(saved['intent'], 'general')
        self.assertTrue(all(clip['start'] >= 11 for clip in saved['clips']))

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
        core_jobs.jobs.clear()
        restored = self.client.get('/api/features/' + JOB, headers=self.headers).json()
        self.assertEqual((restored['state'], restored['steps_log']), ('done', job['steps_log']))
        self.assertEqual(self.client.get('/jobs/' + JOB, headers=self.headers).json()['steps_log'], job['steps_log'])
        # another user cannot read someone else's steps
        self.assertEqual(self.client.get('/api/features/' + JOB, headers={'Authorization': 'Bearer user-b'}).status_code, 404)

    def test_the_step_log_is_capped(self):
        many = tuple(f'step {i}' for i in range(clip_routes.MAX_STEPS + 50))
        job = self.run_job(fake_agent({}, steps=many))
        self.assertEqual(job['state'], 'done')
        self.assertLessEqual(len(job['steps_log']), clip_routes.MAX_STEPS)
        self.assertIn('Saving clip 4/4...', job['steps_log'])  # the newest steps are the ones kept
        self.assertNotIn('step 0', job['steps_log'])         # the oldest were dropped

    # ------------------------------------------------------------------ time limit
    def test_there_is_no_default_time_limit_but_an_optional_safety_net(self):
        ticks = iter([0.0] + [5000.0] * 10000)  # the job "takes" over an hour
        with patch.object(clip_routes.time, 'monotonic', side_effect=lambda: next(ticks)):
            job = self.run_job(fake_agent({}))
        self.assertEqual(job['state'], 'done')  # the old 900s default would have stopped this

        core_jobs.jobs[JOB] = {'state': 'queued', 'message': 'Waiting', 'clips': []}
        ticks = iter([0.0] + [5000.0] * 10000)
        with patch.object(clip_routes.time, 'monotonic', side_effect=lambda: next(ticks)), \
             patch.dict(os.environ, {'CASCADE_JOB_TIMEOUT': '900'}):
            job = self.run_job(fake_agent({}))
        self.assertEqual(job['state'], 'error')
        self.assertIn('Timed out', job['message'])

    # ------------------------------------------------------------------ stop button
    def test_cancel_stops_the_agent_at_its_next_step(self):
        reached = []

        def select(video_path, duration, search, target, progress, stage):
            progress('Agent turn 1/8')
            core_jobs.jobs[JOB]['cancel_requested'] = True  # the user clicks "Stop processing"
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
            self.assertEqual(core_jobs.processing_error(error, 'selecting'), str(error))

    def test_provider_http_errors_become_actionable_without_leaking_details(self):
        class ApiError(Exception):
            def __init__(self, status):
                super().__init__('request failed with key sk-secret-123')
                self.status_code = status

        for status, needle in ((401, 'rejected the API key'), (403, 'rejected the API key'), (429, 'rate limiting')):
            message = core_jobs.processing_error(ApiError(status), 'selecting')
            self.assertIn(needle, message)
            self.assertNotIn('sk-secret', message)
        # a validation error from our own code keeps its own status and text
        self.assertEqual(core_jobs.processing_error(core_jobs.HTTPException(401, 'Please sign in again.'), 'x'), 'Please sign in again.')

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

    # ------------------------------------------------------------------ parallel rendering and step timings
    def test_render_worker_counts_follow_the_machine(self):
        for cores, clips, workers, threads in ((2, 4, 1, 2), (4, 4, 2, 2), (8, 4, 4, 2), (16, 4, 4, 4), (32, 2, 2, 16), (None, 4, 1, 1)):
            with patch.object(core_media.os, 'cpu_count', return_value=cores):
                self.assertEqual(core_media.render_workers(clips), workers, (cores, clips))
                self.assertEqual(core_media.encoder_threads(workers), threads, (cores, clips))

    def test_clips_render_in_parallel_but_come_back_in_rank_order(self):
        import threading
        import time as clock
        lock, running, peak = threading.Lock(), [0], [0]
        real = core_media.render_clip

        def slow_render(video_path, selection, output_path, threads):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            clock.sleep(0.4 if selection['title'] == 'Moment 0' else 0.05)  # the first clip finishes last
            try:
                real(video_path, selection, output_path, threads)
            finally:
                with lock:
                    running[0] -= 1

        with patch.object(core_media.os, 'cpu_count', return_value=8), patch.object(core_media, 'render_clip', side_effect=slow_render):
            job = self.run_job(fake_agent({}))
        self.assertEqual(job['state'], 'done')
        self.assertGreater(peak[0], 1)  # more than one encode ran at once
        self.assertEqual([c['title'] for c in job['clips']], [f'Moment {i}' for i in range(4)])
        self.assertIn('Video rendering and storage', job['timings'])

    def test_a_failed_render_fails_the_job_with_a_safe_message(self):
        def broken(video_path, selection, output_path, threads):
            raise RuntimeError('ffmpeg exploded at /secret/path with key sk-secret-123')

        with patch.object(core_media, 'render_clip', side_effect=broken):
            job = self.run_job(fake_agent({}))
        self.assertEqual(job['state'], 'error')
        self.assertNotIn('sk-secret', job['message'])
        self.assertNotIn('/secret/path', job['message'])

    def test_every_step_carries_its_elapsed_time(self):
        job = self.run_job(fake_agent({}))
        self.assertEqual(len(job['steps_elapsed']), len(job['steps_log']))
        self.assertEqual(job['steps_elapsed'], sorted(job['steps_elapsed']))  # never goes backwards
        saved = json.loads((self.folder / 'results.json').read_text())
        self.assertEqual(saved['steps_elapsed'], job['steps_elapsed'])
        restored = (core_jobs.jobs.clear(), self.client.get('/api/features/' + JOB, headers=self.headers).json())[1]
        self.assertEqual(restored['steps_elapsed'], job['steps_elapsed'])

    def test_model_warmup_can_be_switched_off_and_never_breaks_startup(self):
        with patch.object(app_main.threading, 'Thread') as thread:
            with patch.dict(os.environ, {'CASCADE_WARM_MODELS': '0'}):
                app_main.start_model_warmup()
            thread.assert_not_called()
            with patch.dict(os.environ, {'CASCADE_WARM_MODELS': '1'}):
                app_main.start_model_warmup()
            thread.assert_called_once()
        with patch('backend.video_search.router.load_models', side_effect=RuntimeError('no model files')):
            app_main.warm_models()  # a failed warm-up is logged, not raised


if __name__ == '__main__':
    unittest.main()
