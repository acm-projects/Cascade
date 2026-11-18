"""Demo mode: any Studio prompt returns the saved clips at once, and the Editor opens the picked clips joined."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app1
from backend import demo
from backend.core import auth, jobs as core_jobs


def make_clip(path, seconds, tone):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=30', '-f', 'lavfi',
                    '-i', f'sine=f={tone}:sample_rate=44100', '-t', str(seconds), '-pix_fmt', 'yuv420p', '-c:v', 'libx264',
                    '-c:a', 'aac', '-shortest', str(path)], check=True)


def length(path, stream='v:0'):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', stream, '-show_entries', 'stream=duration', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True).stdout
    return float(out.strip().strip(','))


class DemoMode(unittest.TestCase):
    SECONDS = [2, 1.5, 1, 2.5, 1]

    @classmethod
    def setUpClass(cls):
        cls.assets = tempfile.TemporaryDirectory()
        root = Path(cls.assets.name)/'jaguar'; root.mkdir()
        for i, seconds in enumerate(cls.SECONDS, 1):
            make_clip(root/f'clip_{i}.mp4', seconds, 300+50*i)
            (root/f'clip_{i}.vtt').write_text(f'WEBVTT\n\n00:00:00.100 --> 00:00:00.900\nline {i}\n')
        (root/'results.json').write_text(json.dumps({'clips': [{'start': 10.*i, 'end': 10.*i+s, 'title': f'Jaguar {i}', 'explanation': 'x'}
                                                               for i, s in enumerate(cls.SECONDS, 1)]}))
        make_clip(Path(cls.assets.name)/'upload.mp4', 3, 200)

    @classmethod
    def tearDownClass(cls):
        cls.assets.cleanup()

    def setUp(self):
        self.env = patch.dict(os.environ, {'CASCADE_DEMO': 'on', 'CASCADE_STORAGE': 'local', 'CASCADE_METADATA_STORE': 'local',
                                           'OPENAI_API_KEY': 'test', 'DEEPGRAM_API_KEY': 'test', 'ANTHROPIC_API_KEY': 'test'})
        self.env.start()
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(core_jobs, 'JOBS_DIR', Path(self.temp.name)), patch.object(demo, 'ROOT', Path(self.assets.name)),
                        patch.object(auth, 'verify_clerk_token', side_effect=lambda token: token)]
        for p in self.patches: p.start()
        self.client = TestClient(app1.app)
        self.h = {'Authorization': 'Bearer demo-user'}
        self.pid = self.client.post('/api/projects', json={'name': 'Demo'}, headers=self.h).json()['id']
        self.sid = self.client.get(f'/api/projects/{self.pid}/studio', headers=self.h).json()['sessions'][0]['id']

    def tearDown(self):
        for p in self.patches: p.stop()
        self.env.stop(); self.temp.cleanup(); core_jobs.jobs.clear()

    def prompt(self, text):
        with (Path(self.assets.name)/'upload.mp4').open('rb') as f:
            r = self.client.post(f'/api/projects/{self.pid}/studio/sessions/{self.sid}/upload', headers=self.h,
                                 files={'video': ('talk.mp4', f, 'video/mp4')}, data={'prompt': text, 'clip_count': '3', 'request_id': 'r1'})
        self.assertEqual(r.status_code, 202, r.text)
        job = r.json()['job_id']
        started = time.monotonic()
        while time.monotonic()-started < 10:
            state = self.client.get(f'/jobs/{job}', headers=self.h).json()
            if state['state'] in ('done', 'error'): break
            time.sleep(.05)
        return job, state, time.monotonic()-started

    def test_any_prompt_gives_the_saved_clips_at_once(self):
        job, state, seconds = self.prompt('something completely different')
        self.assertEqual(state['state'], 'done', state)
        self.assertLess(seconds, 3)
        self.assertEqual([c['title'] for c in state['clips']], [f'Jaguar {i}' for i in range(1, 6)])
        for i in range(1, 6):
            self.assertEqual(self.client.get(f'/clips/{job}/clip_{i}.mp4', headers=self.h).status_code, 200)

    def test_editor_can_open_selected_clips_without_waiting_for_a_join(self):
        job, _, _ = self.prompt('find jaguars')
        picks = [{'job_id': job, 'clip_index': i} for i in (0, 2)]
        with patch.object(demo, 'join_early'):
            response = self.client.put(f'/api/projects/{self.pid}/studio/editor-selection',
                                       headers=self.h, json={'clips': picks})
        self.assertEqual(response.status_code, 200, response.text)
        with patch.object(demo, 'editor_clips', side_effect=AssertionError('Editor must not wait for joining')):
            response = self.client.get(f'/api/projects/{self.pid}/editor?selected_only=true&wait_for_join=false',
                                       headers=self.h)
        self.assertEqual(response.status_code, 200, response.text)
        clips = [clip for session in response.json()['sessions'] for clip in session['clips']]
        self.assertEqual([(clip['job_id'], clip['clip_index']) for clip in clips], [(job, 0), (job, 2)])

    def test_the_editor_opens_the_picked_clips_joined_in_order(self):
        job, _, _ = self.prompt('find jaguars')
        picks = [{'job_id': job, 'clip_index': i} for i in (4, 0, 3, 1)]     # picked out of order; clip 3 skipped
        self.assertEqual(self.client.put(f'/api/projects/{self.pid}/studio/editor-selection', headers=self.h, json={'clips': picks}).status_code, 200)
        started = time.monotonic()
        index = self.client.get(f'/api/projects/{self.pid}/editor?selected_only=true', headers=self.h).json()
        self.assertLess(time.monotonic()-started, 5)
        clips = [c for s in index['sessions'] for c in s['clips']]
        self.assertEqual(len(clips), 1)
        joined = clips[0]
        self.assertEqual(index['selection'], {'job_id': joined['job_id'], 'clip_index': 0})
        folder = core_jobs.JOBS_DIR/joined['job_id']
        owner = json.loads((folder/'owner.json').read_text())
        self.assertEqual([p['clip_index'] for p in owner['combined_from']], [0, 1, 3, 4])                       # clips 1, 2, 4, 5
        self.assertAlmostEqual(length(folder/'clip_1.mp4'), 2+1.5+2.5+1, delta=.15)
        self.assertAlmostEqual(length(folder/'clip_1.mp4', 'a:0'), 2+1.5+2.5+1, delta=.15)
        self.assertEqual([line for line in (folder/'clip_1.vtt').read_text().split('\n') if line.startswith('line')], ['line 1', 'line 2', 'line 4', 'line 5'])
        again = self.client.get(f'/api/projects/{self.pid}/editor?selected_only=true', headers=self.h).json()
        self.assertEqual(again['selection'], index['selection'])                                              # reused, not made twice
        draft = self.client.get(f"/api/projects/{self.pid}/editor/{joined['job_id']}/0", headers=self.h)
        self.assertEqual(draft.status_code, 200, draft.text)

    def test_any_broll_search_gives_the_saved_footage(self):
        from backend.broll import Store
        root = Path(self.assets.name)/'broll'; root.mkdir(exist_ok=True)
        make_clip(root/'jaguar-walking-past.mp4', 1, 300); make_clip(root/'jaguar-teeth-roar.mp4', 1, 400)
        store = Store(Path(self.temp.name)/'stock')
        with patch.object(demo, 'BROLL', root):
            found = demo.broll_results(store, 'roar')
        self.assertEqual(len(found['results']), 2)
        first = found['results'][0]
        self.assertIn('teeth-roar', first['source_url'])                                   # best name match first
        self.assertTrue(store.media(first['id']).is_file())                                  # ready to add, no download
        self.assertTrue(store.media(first['id'], image=True).is_file())

    def test_built_in_music_comes_first(self):
        from backend.editor.audio_assets import AudioStore
        root = Path(self.assets.name)/'music_library'; root.mkdir(exist_ok=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=f=330:duration=2', str(root/'Jungle Run (upbeat).mp3')], check=True)
        with patch.object(demo, 'MUSIC', root):
            items = AudioStore(Path(self.temp.name)/'audio').library()
        self.assertEqual(items[0]['name'], 'Jungle Run (upbeat)')
        self.assertAlmostEqual(items[0]['duration'], 2, delta=.1)

    def test_any_ai_chat_message_shows_the_saved_edit(self):
        from types import SimpleNamespace
        from backend.editor.ai_edit import jobs
        from backend.editor.models import Edit
        final = Path(self.assets.name)/'jaguar'
        make_clip(final/'final_edit.mp4', 2, 500)
        (final/'final_plan.json').write_text(json.dumps({'beats': [], 'source_window': {'start': 0, 'end': 2}, 'total_duration': 2}))
        published = []
        folder = Path(self.temp.name)/'edit'
        try:
            import time
            from backend import demo as demo_module
            with patch.object(jobs, 'root', lambda *a: folder), patch.object(jobs, '_publish', lambda *a, **k: published.append((a, k))), \
                    patch.object(demo_module, 'EDIT_SECONDS', .2):
                body = SimpleNamespace(state=Edit(start=0, end=5), chat=[], message='whatever you like', research_id=None)
                reply = jobs.turn('p', 'j', 0, 'u', {}, body, {'has_video': True}, None, None)
                self.assertEqual(reply['ai_job']['status'], 'running')                   # editing steps first (about 6 s in the demo)
                self.assertEqual(json.loads((folder/'job.json').read_text())['status'], 'running')
                for _ in range(100):
                    if json.loads((folder/'job.json').read_text())['status'] == 'done': break
                    time.sleep(.05)
            self.assertEqual(json.loads((folder/'job.json').read_text())['status'], 'done')
            self.assertTrue((folder/'v001'/'edited.mp4').is_file())
            self.assertEqual(published[0][0][5], 'v001')
            self.assertIn("jaguar fan edit", published[0][0][7])
        finally:
            (final/'final_edit.mp4').unlink(); (final/'final_plan.json').unlink()

    def test_picking_clips_joins_them_before_the_editor_opens(self):
        job, _, _ = self.prompt('find jaguars')
        picks = [{'job_id': job, 'clip_index': i} for i in (0, 1, 3)]
        self.client.put(f'/api/projects/{self.pid}/studio/editor-selection', headers=self.h, json={'clips': picks})
        started = time.monotonic()
        while time.monotonic()-started < 10 and not any((p/'owner.json').is_file() and 'combined' in (p/'owner.json').read_text()
                                                         for p in core_jobs.JOBS_DIR.iterdir() if p.is_dir()):
            time.sleep(.05)
        made = [p for p in core_jobs.JOBS_DIR.iterdir() if (p/'owner.json').is_file() and '"combined"' in (p/'owner.json').read_text()]
        self.assertEqual(len(made), 1)                                     # made in the background, before any Editor call
        index = self.client.get(f'/api/projects/{self.pid}/editor?selected_only=true', headers=self.h).json()
        self.assertEqual(index['selection']['job_id'], made[0].name)      # the Editor reuses it, no second join

    def test_youtube_publishes_the_moment_you_click(self):
        job, _, _ = self.prompt('find jaguars')
        conn = self.client.get(f'/api/projects/{self.pid}/social/youtube', headers=self.h).json()
        self.assertTrue(conn['connected'])
        url = f'/api/projects/{self.pid}/editor/{job}/0/publish/youtube'
        self.assertEqual(self.client.get(url, headers=self.h).json()['status'], 'Ready')
        body = {'title': 'Jaguar', 'description': '', 'hashtags': [], 'privacy': 'public',
                'submission_id': '00000000-0000-4000-8000-000000000001', 'edit': {'start': 0, 'end': 2}}
        with patch.dict(os.environ, {'CASCADE_DEMO_YOUTUBE_URL': 'https://www.youtube.com/watch?v=abcDEF12345'}):
            started = time.monotonic()
            done = self.client.post(url, headers=self.h, json=body)
        self.assertLess(time.monotonic()-started, 1)
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual((done.json()['status'], done.json()['url'], done.json()['video_id']),
                         ('Published', 'https://www.youtube.com/watch?v=abcDEF12345', 'abcDEF12345'))
        self.assertEqual(self.client.get(url, headers=self.h).json()['status'], 'Published')

    def test_trend_analysis_is_the_saved_research_at_once(self):
        from backend.editor.models import Edit
        saved = Path(self.assets.name)/'jaguar'/'trends.json'
        saved.write_text(json.dumps({'topic': 'podcast / interview', 'goal': 'g', 'source': 'YouTube',
                                     'result': {'summary': 's', 'suggestions': [{'title': 'Captions'}], 'references': [{'video_id': 'x'}]}}))
        try:
            record = demo.instant_trends('p', 'j', 0, Edit(start=0, end=5), 'v1')
            self.assertEqual((record['status'], record['topic'], record['edit_version']), ('done', 'podcast / interview', 'v1'))
            self.assertEqual(record['result']['suggestions'], [{'title': 'Captions'}])
            self.assertGreater(record['expires_at'], time.time()+3600)
        finally:
            saved.unlink()

    def test_off_means_off(self):
        with patch.dict(os.environ, {'CASCADE_DEMO': 'off'}):
            self.assertFalse(demo.enabled())


if __name__ == '__main__':
    unittest.main()
