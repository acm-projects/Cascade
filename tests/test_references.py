"""Numbered examples, session persistence and backward-compatible generation APIs."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import app1
from backend import integration
from backend.generation import contextual_prompt, followup_windows, exclude_reference_overlaps, finalize_selections
from backend.services.references import parse_reference_numbers, resolve_references, build_clip_context


class ParserTests(unittest.TestCase):
    def test_explicit_references(self):
        cases = {
            'clip 2': [2], 'clips 2 and 4': [2, 4], '#3': [3],
            'selected 1, 2 & 5': [1, 2, 5], 'more like clip 2 and 4': [2, 4],
            'CLIPS 4, 2, and 4': [2, 4], 'clip #2 and #4': [2, 4],
            'Selected 12,13 & 15 but clip 12': [12, 13, 15],
            'clips 2,4,6': [2, 4, 6], 'like #3 and #1': [1, 3],
            '2 and 4': [], 'give me 2 funny clips': [], 'make 4 clips': [],
            'give me 2 funny clips and 4 sad ones': [], 'clip -2': [],
            'selected moments from 2 videos': [], 'eclipse 2': [], 'abc#3': [],
            'clips': [], '': [], 'selected 1 with 2 more clips': [1],
        }
        for prompt, expected in cases.items():
            with self.subTest(prompt=prompt):
                self.assertEqual(parse_reference_numbers(prompt), expected)

    def test_prompt_and_overlap_boundaries(self):
        refs = [{'start': 10, 'end': 20}, {'start': 40, 'end': 50}]
        prompt = contextual_prompt('more like these', refs)
        for value in ('10', '20', '40', '50', 'Find NEW moments', 'Do not return'):
            self.assertIn(value, prompt)
        selected = [{'start': 10, 'end': 20}, {'start': 5, 'end': 15},
                    {'start': 45, 'end': 55}, {'start': 12, 'end': 18}, {'start': 60, 'end': 70}]
        self.assertEqual(exclude_reference_overlaps(selected, refs), [selected[1], selected[2], selected[4]])
        self.assertEqual(finalize_selections(selected, refs, 'expand these', 100, 30, 4),
                         [selected[1], selected[2], selected[4]])
        expanded = followup_windows([], refs[:1], 'expand this clip', 100, 30, 4)
        self.assertLess(expanded[0]['start'], 10)
        self.assertGreater(expanded[0]['end'], 20)


class ReferenceApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for context in (
            patch.object(app1, 'JOBS_DIR', self.root),
            patch.object(app1, 'verify_clerk_token', side_effect=lambda t: t),
            patch.dict(os.environ, {'CASCADE_STORAGE': 'local', 'DEEPGRAM_API_KEY': 'fixture',
                                   'ANTHROPIC_API_KEY': 'fixture', 'LLM_PROVIDER': 'anthropic', 'CASCADE_WARM_MODELS': '0'}),
            patch.object(app1.worker, 'submit'),
        ):
            context.start()
            self.addCleanup(context.stop)
        self.addCleanup(app1.jobs.clear)
        self.client = TestClient(app1.app)
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer reference-user'}
        self.pid = self.client.post('/api/projects', headers=self.headers, json={'name': 'Examples'}).json()['id']
        self.base = f'/api/projects/{self.pid}'
        self.sid = self.client.get(self.base + '/sessions', headers=self.headers).json()['sessions'][0]['id']
        response = self.client.post('/upload', headers=self.headers,
            data={'project_id': self.pid, 'search': 'moments', 'engine': 'agent'},
            files={'video': ('source.mp4', b'original video', 'video/mp4')})
        self.assertEqual(response.status_code, 202, response.text)
        self.jid = response.json()['job_id']
        self.clips = [{'start': 10 + i * 20, 'end': 18 + i * 20, 'title': f'Moment {i}',
                       'clip_url': f'/clips/{self.jid}/clip_{i+1}.mp4'} for i in range(5)]
        app1.save_json(self.root / self.jid / 'results.json', {'clips': self.clips})
        app1.jobs.pop(self.jid, None)
        for i in range(5):
            (self.root / self.jid / f'clip_{i+1}.vtt').write_text('WEBVTT\n' + 'context' * 1000, encoding='utf-8')

    def call(self, method, path, **kwargs):
        return getattr(self.client, method)(self.base + path, headers=self.headers, **kwargs)

    def select(self, index, sid=None, jid=None):
        return self.call('post', f'/sessions/{sid or self.sid}/selections',
                         json={'job_id': jid or self.jid, 'clip_index': index})

    def generate(self, **kwargs):
        return self.call('post', '/generations', json={
            'prompt': 'more like clip 2 and 4', 'request_id': 'examples', 'session_id': self.sid, **kwargs})

    def owner(self, jid):
        return json.loads((self.root / jid / 'owner.json').read_text(encoding='utf-8'))

    def test_numbered_and_explicit_examples_persist_before_enqueue_and_reload(self):
        for i in range(4):
            self.assertEqual(self.select(i).status_code, 201)
        snapshots = []
        def submitted(worker, jid, *args):
            snapshots.append(self.owner(jid))
        with patch.object(app1.worker, 'submit', side_effect=submitted):
            response = self.generate()
        self.assertEqual(response.status_code, 202, response.text)
        jid = response.json()['job_id']
        refs = self.owner(jid)['reference_clips']
        self.assertEqual([r['number'] for r in refs], [2, 4])
        self.assertEqual(snapshots[0]['reference_clips'], refs)
        self.assertEqual(self.owner(jid)['parent_clip'], refs[0])
        self.assertEqual(len(refs[0]['captions']), 4000)
        app1.jobs.clear()
        groups = self.call('get', '/generations', params={'session_id': self.sid}).json()['groups']
        self.assertEqual(next(g for g in groups if g['job_id'] == jid)['reference_clips'], refs)
        explicit = self.generate(prompt='like these but sadder', reference_numbers=[4, 2], request_id='explicit')
        self.assertEqual([r['number'] for r in self.owner(explicit.json()['job_id'])['reference_clips']], [2, 4])

    def test_agent_receives_both_examples_and_duplicate_results_are_removed(self):
        for i in range(4): self.select(i)
        jid = self.generate().json()['job_id']
        candidate = {'start': 100, 'end': 110, 'title': 'New moment'}
        with patch.object(app1, 'inspect_video', return_value=(150, {})), patch.object(
            app1, 'select_with_agent', return_value=([self.clips[1], self.clips[3], candidate], [], {})
        ) as agent, patch.object(app1, 'render_clip'), patch.object(app1, 'write_captions'), patch.object(
            app1, 'upload_clip_files', return_value={}
        ):
            app1.process_upload(jid, self.root / jid / 'source.video', 'more like clip 2 and 4', 'both', 30)
        prompt = agent.call_args.args[2]
        self.assertIn('"start": 30', prompt)
        self.assertIn('"start": 70', prompt)
        result = json.loads((self.root / jid / 'results.json').read_text())
        self.assertEqual([c['start'] for c in result['clips']], [100])

    def test_unknown_excessive_and_malformed_references(self):
        response = self.generate()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'There is no Selected 2 in this session')
        for numbers in ([1] * 7, [True], [1.5], ['2'], [0], [-1]):
            with self.subTest(numbers=numbers):
                self.assertEqual(self.generate(reference_numbers=numbers).status_code, 422)
        self.assertEqual(self.generate(prompt='selected 1,2,3,4,5,6,7').status_code, 400)

    def test_selection_numbers_never_reused_and_idempotent(self):
        for i in range(3): self.assertEqual(self.select(i).json()['number'], i + 1)
        self.assertEqual(self.select(0).status_code, 200)
        self.assertEqual(self.call('delete', f'/sessions/{self.sid}/selections/2').status_code, 204)
        self.assertEqual(self.select(3).json()['number'], 4)
        self.assertEqual(self.generate(reference_numbers=[2]).status_code, 400)
        rows = self.call('get', '/selections').json()['selections']
        self.assertEqual([r['number'] for r in rows], [1, 3, 4])
        self.assertEqual(rows[0]['session_name'], 'Session 1')
        self.assertEqual(self.call('get', '').json()['selection_count'], 3)
        self.assertEqual(self.select(99).status_code, 404)
        self.assertEqual(self.select(-1).status_code, 422)

    def test_session_crud_validation_and_isolation(self):
        self.assertEqual(self.call('delete', '/sessions/' + self.sid).status_code, 409)
        second = self.call('post', '/sessions', json={'name': '  Sad moments  '}).json()
        sid = second['id']
        self.assertEqual(second['name'], 'Sad moments')
        self.assertEqual(self.select(0, sid=sid).status_code, 400)
        for name in ('', '   ', 'x' * 61):
            self.assertEqual(self.call('post', '/sessions', json={'name': name}).status_code, 422)
        self.assertEqual(self.call('patch', '/sessions/' + sid, json={'name': 'Renamed'}).json()['name'], 'Renamed')
        self.assertEqual(self.generate(session_id='s_missing').status_code, 400)
        response = self.generate(prompt='sad', session_id=sid, source_job=self.jid)
        self.assertEqual(response.status_code, 202, response.text)
        jid = response.json()['job_id']
        self.assertEqual(self.owner(jid)['session_id'], sid)
        groups = self.call('get', '/generations', params={'session_id': sid}).json()['groups']
        self.assertEqual([g['job_id'] for g in groups], [jid])
        self.assertEqual(groups[0]['session_number'], 2)
        self.assertEqual(self.call('delete', '/sessions/' + sid).status_code, 409)
        app1.jobs.pop(jid)
        self.assertEqual(self.call('delete', '/sessions/' + sid).status_code, 204)
        self.assertTrue(self.owner(jid)['session_deleted'])
        self.assertTrue((self.root / jid / 'source.video').exists())
        self.assertFalse(any(g['job_id'] == jid for g in self.call('get', '/generations').json()['groups']))
        self.assertEqual(self.client.get(self.base + '/sessions', headers={'Authorization': 'Bearer other'}).status_code, 404)

    def test_legacy_project_and_jobs_migrate_without_rewriting_job(self):
        project = integration.require_project(self.pid, 'reference-user')
        project.pop('sessions')
        project.pop('legacy_session_id', None)
        app1.save_json(integration.project_dir('reference-user') / (self.pid + '.json'), project)
        owner = self.owner(self.jid)
        owner.pop('session_id')
        app1.save_json(self.root / self.jid / 'owner.json', owner)
        before = (self.root / self.jid / 'owner.json').read_bytes()
        sessions = self.call('get', '/sessions').json()['sessions']
        self.assertEqual(sessions[0]['name'], 'Session 1')
        self.assertEqual(self.call('get', '/generations').json()['groups'][0]['session_id'], sessions[0]['id'])
        self.assertEqual((self.root / self.jid / 'owner.json').read_bytes(), before)

    def test_foreign_project_and_cross_source_references_rejected(self):
        self.select(0)
        other = self.client.post('/api/projects', headers=self.headers, json={'name': 'Other'}).json()['id']
        response = self.client.post('/upload', headers=self.headers,
            data={'project_id': other, 'search': 'other'}, files={'video': ('other.mp4', b'other', 'video/mp4')})
        jid = response.json()['job_id']
        self.assertEqual(self.select(0, jid=jid).status_code, 404)
        response = self.client.post('/upload', headers=self.headers,
            data={'project_id': self.pid, 'search': 'different source'}, files={'video': ('other.mp4', b'other', 'video/mp4')})
        source = response.json()['job_id']
        self.assertEqual(self.generate(reference_numbers=[1], source_job=source).status_code, 400)

    def test_deleted_jobs_skipped_and_reference_rejected(self):
        self.select(0)
        owner = self.owner(self.jid)
        owner['project_deleted'] = True
        app1.save_json(self.root / self.jid / 'owner.json', owner)
        self.assertEqual(self.call('get', '/selections').json()['selections'], [])
        self.assertEqual(self.generate(reference_numbers=[1]).status_code, 404)

    def test_selection_counter_is_atomic_for_concurrent_requests(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(self.select, range(4)))
        self.assertEqual(sorted(r.json()['number'] for r in responses), [1, 2, 3, 4])
        self.assertTrue(all(r.status_code == 201 for r in responses))

    def test_retry_preserves_session_and_all_reference_contexts(self):
        for i in range(4): self.select(i)
        jid = self.generate().json()['job_id']
        before = self.owner(jid)
        app1.jobs.pop(jid, None)
        app1.save_json(self.root / jid / 'failure.json', {'message': 'Fixture interruption'})
        response = self.call('post', f'/generations/{jid}/retry', json={'request_id': 'retry-examples'})
        self.assertEqual(response.status_code, 202, response.text)
        after = self.owner(jid)
        self.assertEqual(after['reference_clips'], before['reference_clips'])
        self.assertEqual(after['session_id'], self.sid)

    def test_default_session_ordinary_counts_and_api_schema(self):
        response = self.call('post', '/generations', json={
            'prompt': 'give me 2 funny clips', 'clip_count': 2, 'request_id': 'ordinary-count'})
        self.assertEqual(response.status_code, 202, response.text)
        owner = self.owner(response.json()['job_id'])
        self.assertEqual(owner['session_id'], self.sid)
        self.assertEqual(owner['reference_clips'], [])
        schema = self.client.get('/openapi.json').json()
        self.assertIn('/api/projects/{pid}/sessions', schema['paths'])
        self.assertIn('/api/projects/{pid}/sessions/{sid}/selections', schema['paths'])
        self.assertIn('reference_numbers', schema['components']['schemas']['GenerationInput']['properties'])

    def test_deleting_source_session_preserves_surviving_session_source(self):
        sid = self.call('post', '/sessions', json={'name': 'Surviving'}).json()['id']
        response = self.generate(prompt='new moments', source_job=self.jid, session_id=sid)
        jid = response.json()['job_id']
        app1.jobs.pop(jid, None)
        app1.save_json(self.root / jid / 'results.json', {'clips': self.clips})
        self.assertEqual(self.call('delete', '/sessions/' + self.sid).status_code, 204)
        self.assertEqual(self.client.get(f'/clips/{self.jid}/clip_1.vtt', headers=self.headers).status_code, 404)
        response = self.generate(prompt='more moments', source_job=jid, session_id=sid, request_id='after-delete')
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual((self.root / response.json()['job_id'] / 'source.video').read_bytes(), b'original video')
