"""Grounded grading, draft-aware caching, wave batching and owner checks."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
import app1
from backend import integration
from backend.editor_backend import Draft, Edit
from backend.research import grader, jobs
from backend.research.models import Short, Rubric


def comparable():
    return Short(video_id='example', title='Comparable short', channel='Creator',
        url='https://www.youtube.com/shorts/example', views=1000, likes=20, comments=3,
        published_at='2026-10-20T00:00:00Z', duration_s=30, views_per_day=200)


def judge_data(value=8):
    return {'rubric': {name: value for name in grader.WEIGHTS}, 'summary': 'A clear hook with room to improve pacing.',
        'suggestions': [{'text': 'Remove two seconds of setup.', 'action_hint': 'trim_first 2'},
                        {'text': 'Enable captions for accessibility.', 'action_hint': 'captions_enabled'},
                        {'text': 'Add relevant B-roll.', 'action_hint': 'broll_search'}]}


class ScoreTests(unittest.TestCase):
    def test_weighted_score_and_letter_boundaries(self):
        rubric = {name: 0 for name in grader.WEIGHTS}
        rubric['hook'] = 10
        self.assertEqual(grader.score_rubric(rubric), 30)
        self.assertEqual(grader.score_rubric({name: 8 for name in grader.WEIGHTS}), 80)
        for minimum, letter in grader.BANDS:
            self.assertEqual(grader.letter_for(minimum), letter)
        self.assertEqual(grader.letter_for(89), 'A-')
        self.assertEqual(grader.letter_for(49), 'F')
        with self.assertRaises(ValueError): grader.score_rubric({name: 11 for name in grader.WEIGHTS})
        with self.assertRaises(ValueError): grader.score_rubric({name: float('nan') for name in grader.WEIGHTS})


class GraderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for context in (patch.object(app1, 'JOBS_DIR', self.root),
            patch.object(app1, 'verify_clerk_token', side_effect=lambda token: token),
            patch.dict(os.environ, {'CASCADE_WARM_MODELS': '0', 'AUTO_GRADE_WAVES': '0'})):
            context.start(); self.addCleanup(context.stop)
        self.client = TestClient(app1.app)
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer grade-user'}
        self.pid = self.client.post('/api/projects', headers=self.headers, json={'name': 'Research'}).json()['id']
        project = integration.require_project(self.pid, 'grade-user')
        self.jid = 'a' * 32
        self.folder = self.root / self.jid
        self.folder.mkdir()
        app1.save_json(self.folder / 'owner.json', {'user_id': 'grade-user', 'project_id': self.pid,
            'kind': 'generation', 'session_id': project['sessions'][0]['id'], 'prompt': 'funny stories'})
        self.clips = []
        for index in range(4):
            (self.folder / f'clip_{index+1}.mp4').write_bytes(b'video')
            (self.folder / f'clip_{index+1}.vtt').write_text(
                'WEBVTT\n\n00:00.000 --> 00:05.000\nIntro\n\n00:05.000 --> 00:10.000\nCore story\n\n00:10.000 --> 00:20.000\nClosing\n', encoding='utf-8')
            self.clips.append({'start': 100 + index*20, 'end': 120 + index*20, 'title': f'Clip {index}',
                'clip_url': f'/clips/{self.jid}/clip_{index+1}.mp4', 'captions_url': f'/clips/{self.jid}/clip_{index+1}.vtt'})
        app1.save_json(self.folder / 'results.json', {'clips': self.clips})
        self.addCleanup(app1.jobs.clear)
        self.patches = [patch.object(app1, 'inspect_video', return_value=(20., True)),
            patch.object(grader, 'grab_frame_jpeg', return_value=b'jpeg'),
            patch.object(grader, 'find_similar_shorts', return_value=[comparable()]),
            patch.object(grader, 'structured_json', return_value=SimpleNamespace(data=judge_data())),
            patch.object(app1.worker, 'submit')]
        self.probe, self.frames, self.similar, self.llm, self.submit = [p.start() for p in self.patches]
        for p in self.patches: self.addCleanup(p.stop)
        self.base = f'/api/projects/{self.pid}'
        self.url = self.base + f'/clips/{self.jid}/0/grade'

    def grade(self, index=0, **kwargs):
        return grader.grade_clip(self.pid, self.jid, index, user_id='grade-user', **kwargs)

    def execute_queued(self):
        fn, *args = self.submit.call_args.args
        fn(*args)

    def save_draft(self, start=5, end=12):
        path = grader.draft_path(self.pid, self.jid, 0, 'grade-user')
        path.parent.mkdir(parents=True, exist_ok=True)
        state = Edit(start=start, end=end)
        state.captions.bold = True
        state.composition.ratio = '9:16'
        state.texts = {'1': 'Edited core story'}
        app1.save_json(path, Draft(state=state).model_dump())

    def test_context_uses_trimmed_transcript_images_settings_and_prompt(self):
        self.save_draft()
        context = grader.build_clip_context(self.pid, self.jid, 0, True, user_id='grade-user')
        self.assertEqual(context['duration'], 7)
        self.assertNotIn('Intro', context['transcript'])
        self.assertIn('Edited core story', context['transcript'])
        self.assertTrue(context['captions']['bold'])
        self.assertEqual(context['aspect_ratio'], '9:16')
        self.assertEqual(context['session_prompt'], 'funny stories')
        self.assertEqual(len(context['images']), 3)
        self.assertEqual([call.args[1] for call in self.frames.call_args_list], [5, 8.5, 11.95])

    def test_raw_cache_skips_models_lookup_and_media(self):
        first = self.grade()
        self.assertEqual((first.score, first.letter), (80, 'B+'))
        self.assertEqual(first, self.grade())
        self.similar.assert_called_once()
        self.llm.assert_called_once()
        self.probe.assert_called_once()
        self.assertEqual(len(self.llm.call_args.kwargs['images']), 3)
        self.assertIn('only their metadata is provided', self.llm.call_args.args[0])

    def test_edit_state_invalidates_grade_without_overwriting_raw(self):
        raw = self.grade()
        self.save_draft()
        first = self.grade(use_edits=True)
        self.save_draft(start=6)
        second = self.grade(use_edits=True)
        self.assertNotEqual(first.cache_key, second.cache_key)
        self.assertEqual(self.grade(), raw)
        self.assertEqual(self.llm.call_count, 3)
        self.assertIsNotNone(grader.cached_grade(self.pid, self.jid, 0, False, 'grade-user'))

    def test_unknown_action_hint_dropped_and_invalid_rubric_not_cached(self):
        data = judge_data()
        data['suggestions'].append({'text': 'Buy followers', 'action_hint': 'buy_followers'})
        self.llm.return_value = SimpleNamespace(data=data)
        result = self.grade()
        self.assertEqual(len(result.suggestions), 3)
        self.llm.return_value = SimpleNamespace(data=judge_data(99))
        with self.assertRaises(ValueError): self.grade(index=1)
        self.assertFalse(grader.grade_path(self.jid, 1).exists())

    def test_clip_background_api_cache_and_owner_checks(self):
        response = self.client.post(self.url, headers=self.headers, json={'use_edits': False})
        self.assertEqual(response.status_code, 202)
        feature = response.json()['job_id']
        self.execute_queued()
        status = self.client.get('/api/features/' + feature, headers=self.headers)
        self.assertEqual(status.json()['state'], 'done')
        self.assertEqual(status.json()['grade']['score'], 80)
        response = self.client.post(self.url, headers=self.headers, json={'use_edits': False})
        self.assertEqual(response.status_code, 200)
        self.submit.assert_called_once()
        self.assertEqual(self.client.get(self.url, headers=self.headers).json()['grade']['score'], 80)
        other = {'Authorization': 'Bearer other-user'}
        for method in ('get', 'post'):
            result = getattr(self.client, method)(self.url, headers=other, **({'json': {'use_edits': False}} if method == 'post' else {}))
            self.assertEqual(result.status_code, 404)
        self.assertEqual(self.client.get('/api/features/' + feature, headers=other).status_code, 404)

    def test_queued_edit_grade_uses_request_snapshot(self):
        self.save_draft(start=5)
        self.client.post(self.url, headers=self.headers, json={'use_edits': True})
        old_key = self.submit.call_args.args[-1]['cache_key']
        self.save_draft(start=7)
        self.execute_queued()
        self.assertIsNone(grader.cached_grade(self.pid, self.jid, 0, True, 'grade-user'))
        saved = json.loads(grader.grade_path(self.jid, 0).read_text())
        self.assertIn(old_key, saved['grades'])

    def test_one_comparable_lookup_per_wave_and_best_clip_badges(self):
        responses = [SimpleNamespace(data=judge_data(score)) for score in (7, 9, 8, 6)]
        self.llm.side_effect = responses
        response = self.client.post(self.base + f'/generations/{self.jid}/grade', headers=self.headers)
        self.assertEqual(response.status_code, 202)
        feature = response.json()['job_id']
        self.execute_queued()
        self.similar.assert_called_once()
        self.assertEqual(self.llm.call_count, 4)
        result = self.client.get('/api/features/' + feature, headers=self.headers).json()
        self.assertEqual((result['state'], result['best_clip_index']), ('done', 1))
        self.assertEqual(len(result['grades']), 4)
        group = self.client.get(self.base + '/generations', headers=self.headers).json()['groups'][0]
        self.assertEqual(group['best_clip_index'], 1)
        self.assertEqual([clip['grade']['score'] for clip in group['clips']], [70, 90, 80, 60])
        self.similar.reset_mock(); self.llm.reset_mock()
        grader.grade_wave(self.pid, self.jid, user_id='grade-user')
        self.similar.assert_not_called(); self.llm.assert_not_called()

    def test_partial_grading_has_no_best_clip_and_unfinished_wave_409(self):
        self.grade()
        group = self.client.get(self.base + '/generations', headers=self.headers).json()['groups'][0]
        self.assertIsNone(group['best_clip_index'])
        self.assertIsNotNone(group['clips'][0]['grade'])
        self.assertIsNone(group['clips'][1]['grade'])
        (self.folder / 'results.json').unlink()
        self.assertEqual(self.client.post(self.base + f'/generations/{self.jid}/grade', headers=self.headers).status_code, 409)

    def test_auto_grade_opt_in_and_no_recursive_research_grading(self):
        jobs.maybe_auto_grade(self.jid)
        self.submit.assert_not_called()
        with patch.dict(os.environ, {'AUTO_GRADE_WAVES': '1'}):
            jobs.maybe_auto_grade(self.jid)
        self.submit.assert_called_once()
        with patch.object(jobs, 'enqueue_wave', side_effect=RuntimeError('queue down')), patch.dict(os.environ, {'AUTO_GRADE_WAVES': '1'}):
            with self.assertLogs('backend.research.jobs', level='ERROR'):
                jobs.maybe_auto_grade(self.jid)  # Does not break successful generation.

    def test_duplicate_pending_grade_reuses_job_and_failure_persists(self):
        first = self.client.post(self.url, headers=self.headers, json={'use_edits': False}).json()['job_id']
        second = self.client.post(self.url, headers=self.headers, json={'use_edits': False}).json()['job_id']
        self.assertEqual(first, second)
        self.submit.assert_called_once()
        self.similar.side_effect = RuntimeError('private provider URL')
        with self.assertLogs('backend.research.jobs', level='ERROR'): self.execute_queued()
        data = self.client.get('/api/features/' + first, headers=self.headers).json()
        self.assertEqual(data['state'], 'error')
        self.assertNotIn('private provider', data['message'])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_trimmed_media_context_and_frame_sampling(self):
        from backend.agent.tools import grab_frame_jpeg as real_frame
        self.probe.side_effect = None
        self.frames.side_effect = real_frame
        def probe(video):
            result = subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', str(video)], timeout=15)
            return float(json.loads(result)['format']['duration']), False
        self.probe.side_effect = probe
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'color=c=blue:s=160x90:r=10:d=20', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            str(self.folder / 'clip_1.mp4')], check=True, capture_output=True, timeout=30)
        self.save_draft(start=5, end=12)
        context = grader.build_clip_context(self.pid, self.jid, 0, True, user_id='grade-user')
        self.assertEqual(context['duration'], 7)
        import base64
        self.assertTrue(all(base64.b64decode(frame['data']).startswith(b'\xff\xd8') for frame in context['images']))
        self.assertIn('Edited core story', context['transcript'])

    def test_cloud_only_media_reuses_editor_download_path(self):
        (self.folder / 'clip_1.mp4').unlink()
        self.clips[0].update(s3_bucket='fixture-bucket', clip_s3_key='private/source.mp4')
        app1.save_json(self.folder / 'results.json', {'clips': self.clips})
        def download(bucket, key, path):
            Path(path).write_bytes(b'cloud media')
        with patch.object(app1, 's3_client') as s3:
            s3.return_value.download_file.side_effect = download
            context = grader.build_clip_context(self.pid, self.jid, 0, False, user_id='grade-user')
            self.assertEqual(len(context['images']), 3)
            s3.return_value.download_file.assert_called_once()

    def test_wave_owner_and_pending_checks_and_empty_batch(self):
        url = self.base + f'/generations/{self.jid}/grade'
        self.assertEqual(self.client.post(url, headers={'Authorization': 'Bearer other'}).status_code, 404)
        app1.jobs[self.jid] = {'state': 'processing'}
        self.assertEqual(self.client.post(url, headers=self.headers).status_code, 409)
        app1.jobs.pop(self.jid)
        app1.save_json(self.folder / 'results.json', {'clips': []})
        self.assertEqual(grader.grade_wave(self.pid, self.jid, user_id='grade-user'), [])
        self.similar.assert_not_called()
