"""Multi-clip editing: picked clips (e.g. clip 1 and clip 3) are joined into one Editor clip."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app1
from backend.core import auth, jobs as core_jobs
from backend.editor import combine


def make_video(path, seconds, size='320x180', tone=440):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc=size={size}:rate=30', '-f', 'lavfi',
                    '-i', f'sine=f={tone}:sample_rate=48000', '-t', str(seconds), '-pix_fmt', 'yuv420p', '-c:v', 'libx264',
                    '-c:a', 'aac', '-shortest', str(path)], check=True)


def duration(path, stream):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', stream, '-show_entries', 'stream=duration,width,height',
                          '-of', 'json', str(path)], capture_output=True, text=True).stdout
    return json.loads(out)['streams'][0]


class Captions(unittest.TestCase):
    def test_cues_shift_by_the_parts_before_them(self):
        a = 'WEBVTT\n\n00:00:00.500 --> 00:00:01.500\nhello there\n\n00:00:01.600 --> 00:00:09.000\ncut at the end\n'
        b = 'WEBVTT\n\n1\n00:00.000 --> 00:01.250\nsecond <b>clip</b>\n'
        merged = combine.merged_captions([(a, 2.), (b, 3.)])
        self.assertEqual(combine.cues(merged), [(.5, 1.5, 'hello there'), (1.6, 2., 'cut at the end'), (2., 3.25, 'second <b>clip</b>')])

    def test_empty_or_broken_captions_are_skipped(self):
        self.assertEqual(combine.cues(''), [])
        self.assertEqual(combine.cues('WEBVTT\n\nnot a cue\n\n00:00:01.000 --> bad\nx\n'), [])

    def test_titles(self):
        self.assertEqual(combine.default_title(['Hook', 'Payoff']), 'Hook + Payoff')
        self.assertEqual(combine.default_title(['x'*80, 'y'*80]), '2 clips combined')


class Route(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'CASCADE_STORAGE': 'local', 'CASCADE_METADATA_STORE': 'local', 'DEEPGRAM_API_KEY': '',
                                           'OPENAI_API_KEY': '', 'CASCADE_TRANSCRIBER': 'none'})
        self.env.start()
        self.temp = tempfile.TemporaryDirectory()
        self.jobs = patch.object(core_jobs, 'JOBS_DIR', Path(self.temp.name)); self.jobs.start()
        self.auth = patch.object(auth, 'verify_clerk_token', side_effect=lambda token: token); self.auth.start()
        self.client = TestClient(app1.app)
        self.headers = {'Authorization': 'Bearer user-a'}
        self.pid = self.client.post('/api/projects', json={'name': 'Combine'}, headers=self.headers).json()['id']

    def tearDown(self):
        self.env.stop(); self.auth.stop(); self.jobs.stop(); self.temp.cleanup(); core_jobs.jobs.clear()

    def upload(self, seconds, size='320x180'):
        path = Path(self.temp.name)/f'in-{seconds}-{size}.mp4'
        make_video(path, seconds, size)
        with path.open('rb') as f:
            r = self.client.post(f'/api/projects/{self.pid}/editor/upload', headers=self.headers, files={'video': ('talk.mp4', f, 'video/mp4')})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()['job_id']

    def four_clips(self, job):
        """Make an upload look like a generation with four clips cut from its source."""
        folder = core_jobs.JOBS_DIR/job
        clips = [{'clip_id': f'{job}:{i}', 'start': 2.*i, 'end': 2.*i+1.5, 'title': f'Moment {i+1}', 'media_kind': 'video', 'has_video': True,
                  'clip_url': f'/clips/{job}/clip_{i+1}.mp4', 'captions_url': f'/clips/{job}/clip_{i+1}.vtt'} for i in range(4)]
        core_jobs.save_json(folder/'results.json', {'clips': clips})
        for i in range(4):
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(2.*i), '-t', '1.5', '-i', str(folder/'source.video'),
                            '-c:v', 'libx264', '-c:a', 'aac', str(folder/f'clip_{i+1}.mp4')], check=True)
            (folder/f'clip_{i+1}.vtt').write_text(f'WEBVTT\n\n00:00:00.200 --> 00:00:01.000\nline {i+1}\n')

    def test_clip_1_and_clip_3_become_one_editor_clip(self):
        job = self.upload(8)
        self.four_clips(job)
        r = self.client.post(f'/api/projects/{self.pid}/editor/combine', headers=self.headers,
                             json={'clips': [{'job_id': job, 'clip_index': 0}, {'job_id': job, 'clip_index': 2}]})
        self.assertEqual(r.status_code, 201, r.text)
        made = r.json()
        self.assertEqual((made['parts'], made['title']), (2, 'Moment 1 + Moment 3'))
        self.assertAlmostEqual(made['duration'], 3., delta=.1)
        folder = core_jobs.JOBS_DIR/made['job_id']
        self.assertAlmostEqual(float(duration(folder/'clip_1.mp4', 'a:0')['duration']), 3., delta=.1)
        self.assertAlmostEqual(float(duration(folder/'clip_1.mp4', 'v:0')['duration']), 3., delta=.1)
        self.assertEqual([c[2] for c in combine.cues((folder/'clip_1.vtt').read_text())], ['line 1', 'line 3'])
        self.assertAlmostEqual(combine.cues((folder/'clip_1.vtt').read_text())[1][0], 1.7, places=2)
        owner = json.loads((folder/'owner.json').read_text())
        self.assertEqual((owner['kind'], [p['clip_index'] for p in owner['combined_from']]), ('combined', [0, 2]))
        index = self.client.get(f'/api/projects/{self.pid}/editor?selected_only=true', headers=self.headers).json()
        self.assertEqual(index['selection'], {'job_id': made['job_id'], 'clip_index': 0})        # the Editor opens it
        draft = self.client.get(f"/api/projects/{self.pid}/editor/{made['job_id']}/0", headers=self.headers)
        self.assertEqual(draft.status_code, 200, draft.text)

    def test_different_frame_sizes_join_at_the_first_size(self):
        a, b = self.upload(2), self.upload(2, '180x320')
        r = self.client.post(f'/api/projects/{self.pid}/editor/combine', headers=self.headers,
                             json={'clips': [{'job_id': a, 'clip_index': 0}, {'job_id': b, 'clip_index': 0}]})
        self.assertEqual(r.status_code, 201, r.text)
        v = duration(core_jobs.JOBS_DIR/r.json()['job_id']/'clip_1.mp4', 'v:0')
        self.assertEqual((v['width'], v['height']), (320, 180))

    def test_bad_requests(self):
        job = self.upload(8); self.four_clips(job)
        url = f'/api/projects/{self.pid}/editor/combine'
        one = {'job_id': job, 'clip_index': 0}
        self.assertEqual(self.client.post(url, headers=self.headers, json={'clips': [one]}).status_code, 422)
        self.assertEqual(self.client.post(url, headers=self.headers, json={'clips': [one, one]}).status_code, 400)
        self.assertEqual(self.client.post(url, headers=self.headers, json={'clips': [one, {**one, 'clip_index': 9}]}).status_code, 404)
        other = {'Authorization': 'Bearer user-b'}
        self.assertIn(self.client.post(url, headers=other, json={'clips': [one, {**one, 'clip_index': 1}]}).status_code, (403, 404))


if __name__ == '__main__':
    unittest.main()
