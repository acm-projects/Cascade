"""Studio state/branches use real persistence and mocked workers/providers."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import app1
from backend import studio, integration
from backend.generation import contextual_prompt, followup_windows, options


class StudioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for context in [patch.object(app1, 'JOBS_DIR', Path(temp.name)),
                        patch.object(app1, 'verify_clerk_token', side_effect=lambda token: token),
                        patch.dict(os.environ, {'CASCADE_METADATA_STORE': 'local', 'CASCADE_STORAGE': 'local'}),
                        patch.object(app1, 'requirements_error', return_value=None),
                        patch.object(app1.worker, 'submit')]:
            value = context.start()
            self.addCleanup(context.stop)
        self.client = TestClient(app1.app)
        self.headers = {'Authorization': 'Bearer studio-user'}
        self.other = {'Authorization': 'Bearer another-user'}
        self.pid = self.client.post('/api/projects', headers=self.headers, json={'name': 'Studio'}).json()['id']
        self.base = '/api/projects/' + self.pid + '/studio'
        self.jid = 'a' * 32
        folder = app1.JOBS_DIR / self.jid
        folder.mkdir()
        (folder / 'source.video').write_bytes(b'original-source')
        app1.save_json(folder / 'owner.json', {'user_id': 'studio-user', 'project_id': self.pid,
            'kind': 'generation', 'source_job': self.jid, 'prompt': 'Funny moments', 'created_at': 1,
            'requested_clip_count': 4, 'engine': 'agent'})
        app1.save_json(folder / 'results.json', {'clips': [{'start': i*10., 'end': (i+1)*10.,
            'title': 'Moment ' + str(i+1), 'explanation': 'A surprise and reaction',
            'clip_url': f'/clips/{self.jid}/clip_{i+1}.mp4'} for i in range(4)]})
        self.sid = self.client.get(self.base, headers=self.headers).json()['sessions'][0]['id']
        self.addCleanup(app1.jobs.clear)

    def ref(self, index=0):
        return {'job_id': self.jid, 'clip_index': index}

    def test_legacy_generations_and_session_state_survive_reload(self):
        url = self.base + '/sessions/' + self.sid + '/state'
        patch_data = {'references': [self.ref(3)], 'positions': {'clip:' + self.jid + ':3': {'x': 900, 'y': 90}},
                      'viewport': {'x': 10, 'y': 20, 'zoom': .8}}
        self.assertEqual(self.client.patch(url, headers=self.headers, json=patch_data).status_code, 200)
        app1.jobs.clear()
        result = self.client.get(self.base, headers=self.headers).json()['sessions'][0]
        self.assertEqual(result['references'], [self.ref(3)])
        self.assertEqual(result['viewport']['zoom'], .8)
        self.assertEqual(result['job_ids'], [self.jid])
        self.assertEqual(self.client.get(self.base, headers=self.other).status_code, 404)
        self.assertEqual(self.client.patch(url, headers=self.other, json={}).status_code, 404)
        self.assertEqual(self.client.patch(url, headers=self.headers, json={'positions': {'unknown': {'x': 1, 'y': 2}}}).status_code, 400)

    def test_multi_reference_request_is_recorded_before_worker_and_is_idempotent(self):
        payload = {'prompt': 'Find more clips with their shared humor', 'clip_count': 4,
                   'references': [self.ref(0), self.ref(3)], 'request_id': 'same-request'}
        url = self.base + '/sessions/' + self.sid + '/generate'
        first = self.client.post(url, headers=self.headers, json=payload)
        self.assertEqual(first.status_code, 202, first.text)
        jid = first.json()['job_id']
        owner = app1.load_json(app1.JOBS_DIR / jid / 'owner.json')
        self.assertEqual(len(owner['parent_clips']), 2)
        self.assertEqual(owner['studio_session_id'], self.sid)
        count, context = options(app1.JOBS_DIR / jid)
        self.assertEqual(count, 4)
        self.assertEqual(len(context['references']), 2)
        self.assertIn('ALL these references', contextual_prompt('Find more', context))
        again = self.client.post(url, headers=self.headers, json=payload)
        self.assertEqual(again.json()['job_id'], jid)
        self.assertEqual(app1.worker.submit.call_count, 1)
        state = self.client.get(self.base, headers=self.headers).json()
        self.assertEqual(len(state['sessions']), 1)
        self.assertIn(jid, state['sessions'][0]['job_ids'])
        self.assertEqual(state['sessions'][0]['messages'][-1]['text'], payload['prompt'])

    def test_session_reuses_source_and_rejects_references_from_other_sessions(self):
        created = self.client.post(self.base + '/sessions', headers=self.headers,
                                   json={'name': 'Emotional', 'source_job': self.jid})
        self.assertEqual(created.status_code, 201)
        new = created.json()
        self.assertEqual(new['source_job'], self.jid)
        self.assertEqual(new['job_ids'], [])
        response = self.client.post(self.base + '/sessions/' + new['id'] + '/generate', headers=self.headers,
            json={'prompt': 'More like that', 'references': [self.ref()], 'request_id': 'bad-ref'})
        self.assertEqual(response.status_code, 400)
        app1.worker.submit.assert_not_called()

    def test_first_upload_binds_the_session_without_creating_an_extra_session(self):
        pid = self.client.post('/api/projects', headers=self.headers, json={'name': 'Fresh'}).json()['id']
        url = '/api/projects/' + pid + '/studio'
        sid = self.client.get(url, headers=self.headers).json()['sessions'][0]['id']
        response = self.client.post(url + '/sessions/' + sid + '/upload', headers=self.headers,
            data={'prompt': 'Find funny moments', 'clip_count': '3', 'request_id': 'first-upload'},
            files={'video': ('source.mp4', b'synthetic-source', 'video/mp4')})
        self.assertEqual(response.status_code, 202, response.text)
        state = self.client.get(url, headers=self.headers).json()
        self.assertEqual(len(state['sessions']), 1)
        self.assertEqual(state['sessions'][0]['source_job'], response.json()['job_id'])
        self.assertEqual(state['sessions'][0]['job_ids'], [response.json()['job_id']])

    def test_editor_handoff_limits_listing_to_checked_clips(self):
        selected = [self.ref(0), self.ref(3)]
        response = self.client.put(self.base + '/editor-selection', headers=self.headers, json={'clips': selected})
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/api/projects/' + self.pid + '/editor?selected_only=true', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c['clip_index'] for c in response.json()['sessions'][0]['clips']], [0, 3])
        self.assertEqual(response.json()['selection'], self.ref(0))
        self.assertEqual(self.client.put(self.base + '/editor-selection', headers=self.other, json={'clips': selected}).status_code, 404)

    def test_chat_persists_and_does_not_queue_generation(self):
        url = self.base + '/sessions/' + self.sid + '/chat'
        payload = {'message': 'Why is this funny?', 'references': [self.ref()], 'request_id': 'discussion'}
        with patch.object(studio, 'discuss', return_value='The contrast creates surprise.') as discuss:
            first = self.client.post(url, headers=self.headers, json=payload)
            second = self.client.post(url, headers=self.headers, json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(discuss.call_count, 1)
        app1.worker.submit.assert_not_called()
        messages = self.client.get(self.base, headers=self.headers).json()['sessions'][0]['messages']
        self.assertEqual(messages[-1]['text'], 'The contrast creates surprise.')

    def test_combined_reference_windows_are_not_returned_as_new_clips(self):
        refs = [{'start': 0, 'end': 10}, {'start': 30, 'end': 40}]
        choices = [{'start': 0, 'end': 10}, {'start': 10, 'end': 20}, {'start': 30, 'end': 40}]
        self.assertEqual(followup_windows(choices, {'references': refs}, 'More like these', 60, 30, 4), [choices[1]])

    def test_nested_branches_and_editor_choices_remain_after_switching_sessions(self):
        generated = self.client.post(self.base + '/sessions/' + self.sid + '/generate', headers=self.headers,
            json={'prompt': 'More like clip four', 'references': [self.ref(3)], 'request_id': 'nested-first'})
        self.assertEqual(generated.status_code, 202)
        child = generated.json()['job_id']
        app1.save_json(app1.JOBS_DIR / child / 'results.json', {'clips': [
            {'start': 40., 'end': 50., 'title': 'New related moment', 'clip_url': f'/clips/{child}/clip_1.mp4'}]})
        combined = [self.ref(0), {'job_id': child, 'clip_index': 0}]
        response = self.client.post(self.base + '/sessions/' + self.sid + '/generate', headers=self.headers,
            json={'prompt': 'Blend their emotional effect', 'references': combined, 'request_id': 'nested-combined'})
        self.assertEqual(response.status_code, 202)
        owner = app1.load_json(app1.JOBS_DIR / response.json()['job_id'] / 'owner.json')
        self.assertEqual([r['job_id'] for r in owner['parent_clips']], [self.jid, child])
        self.assertEqual(owner['source_job'], self.jid)
        self.assertEqual(self.client.put(self.base + '/editor-selection', headers=self.headers,
                                        json={'clips': combined}).status_code, 200)
        another = self.client.post(self.base + '/sessions', headers=self.headers,
                                  json={'name': 'Sad moments', 'source_job': self.jid}).json()
        self.assertEqual(self.client.patch(self.base + '/sessions/' + self.sid + '/state',
                                          headers=self.headers, json={}).status_code, 200)
        restored = self.client.get(self.base, headers=self.headers).json()
        self.assertEqual(restored['active_session_id'], self.sid)
        self.assertEqual(restored['editor_clips'], combined)
        self.assertEqual(next(s for s in restored['sessions'] if s['id'] == another['id'])['job_ids'], [])

    def test_single_checked_reference_supplies_context_for_short_funny_prompt(self):
        captions = app1.JOBS_DIR / self.jid / 'clip_2.vtt'
        captions.write_text('WEBVTT\n\n00:00.000 --> 00:04.000\nBedroom wrestling surprise\n', encoding='utf-8')
        response = self.client.post(self.base + '/sessions/' + self.sid + '/generate', headers=self.headers,
            json={'prompt': 'funnier moments', 'references': [self.ref(1)], 'request_id': 'similar-bedroom'})
        self.assertEqual(response.status_code, 202, response.text)
        jid = response.json()['job_id']
        count, context = options(app1.JOBS_DIR / jid)
        self.assertEqual(context['job_id'], self.jid)
        self.assertEqual(context['clip_index'], 1)
        self.assertEqual(context['reference_mode'], 'similar')
        prompt = contextual_prompt('funnier moments', context)
        self.assertIn('Moment 2', prompt)
        self.assertIn('Bedroom wrestling surprise', prompt)
        self.assertIn('NEW moments', prompt)
        candidates = [{'start': 10., 'end': 20.}, {'start': 11., 'end': 19.}, {'start': 22., 'end': 30.}]
        self.assertEqual(followup_windows(candidates, context, 'funnier moments', 60, 30, count), [candidates[2]])
        expanded = followup_windows(candidates, context, 'Expand this clip', 60, 30, count)
        self.assertLess(expanded[0]['start'], 10.)
        self.assertGreater(expanded[0]['end'], 20.)

    def test_negated_expansion_still_excludes_checked_examples(self):
        ref = {'start': 10., 'end': 20., 'reference_mode': 'similar'}
        choices = [{'start': 10., 'end': 20.}, {'start': 30., 'end': 40.}]
        self.assertEqual(followup_windows(choices, ref, "Don't expand, find funny moments", 60, 30, 4), [choices[1]])

    def test_revision_reuses_clip_context_and_records_in_place_replacement(self):
        path = app1.JOBS_DIR / self.jid / 'results.json'
        original = path.read_bytes()
        body = {'prompt': 'More funny clips with this same feel, different footage is fine',
                'references': [self.ref(1)], 'operation': 'revise', 'request_id': 'revise-selected'}
        url = self.base + '/sessions/' + self.sid + '/generate'
        response = self.client.post(url, headers=self.headers, json=body)
        self.assertEqual(response.status_code, 202, response.text)
        jid = response.json()['job_id']
        owner = app1.load_json(app1.JOBS_DIR / jid / 'owner.json')
        self.assertEqual(owner['studio_revision_of'], self.ref(1))
        self.assertEqual(owner['parent_clips'][0]['clip_index'], 1)
        self.assertEqual(owner['source_job'], self.jid)
        session = self.client.get(self.base, headers=self.headers).json()['sessions'][0]
        self.assertEqual(session['clip_revisions'][self.jid + ':1'], jid)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.client.post(url, headers=self.headers, json=body).json()['job_id'], jid)
        self.assertEqual(app1.worker.submit.call_count, 1)
        listing = self.client.get('/api/projects/' + self.pid + '/generations', headers=self.headers).json()['groups']
        self.assertEqual(next(g for g in listing if g['job_id'] == jid)['studio_revision_of'], self.ref(1))

    def test_revision_requires_selected_clips(self):
        url = self.base + '/sessions/' + self.sid + '/generate'
        for refs in ([],):
            response = self.client.post(url, headers=self.headers, json={
                'prompt': 'Similar clips', 'references': refs, 'operation': 'revise', 'request_id': 'invalid-revision'})
            self.assertEqual(response.status_code, 400)
        app1.worker.submit.assert_not_called()

    def test_old_client_editor_check_focuses_clip_and_missing_operation_revises(self):
        self.client.put(self.base + '/editor-selection', headers=self.headers, json={'clips': [self.ref(2)]})
        session = self.client.get(self.base, headers=self.headers).json()['sessions'][0]
        self.assertEqual(session['references'], [self.ref(2)])
        response = self.client.post(self.base + '/sessions/' + self.sid + '/generate', headers=self.headers,
            json={'prompt': 'find similar clips to the selected one', 'references': [], 'request_id': 'old-client'})
        self.assertEqual(response.status_code, 202, response.text)
        owner = app1.load_json(app1.JOBS_DIR / response.json()['job_id'] / 'owner.json')
        self.assertEqual(owner['studio_revision_of'], self.ref(2))
        self.client.put(self.base + '/editor-selection', headers=self.headers, json={'clips': []})
        session = self.client.get(self.base, headers=self.headers).json()['sessions'][0]
        self.assertEqual(session['references'], [])

    def test_similar_request_without_reference_never_queues_fresh_generation(self):
        response = self.client.post(self.base + '/sessions/' + self.sid + '/generate', headers=self.headers,
            json={'prompt': 'find similar clips to the selected one', 'references': [], 'request_id': 'missing-selected'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('No new generation was started', response.json()['detail'])
        app1.worker.submit.assert_not_called()

    def test_legacy_single_explicit_reference_defaults_to_revision(self):
        response = self.client.post(self.base + '/sessions/' + self.sid + '/generate', headers=self.headers,
            json={'prompt': 'funnier', 'references': [self.ref(1)], 'request_id': 'legacy-single'})
        self.assertEqual(response.status_code, 202)
        owner = app1.load_json(app1.JOBS_DIR / response.json()['job_id'] / 'owner.json')
        self.assertEqual(owner['studio_revision_of'], self.ref(1))

    def test_editor_handoff_preserves_studio_names_wave_labels_and_clip_identity(self):
        chosen = [self.ref(3), self.ref(1)]
        self.client.put(self.base + '/editor-selection', headers=self.headers, json={'clips': chosen})
        result = self.client.get('/api/projects/' + self.pid + '/editor?selected_only=true', headers=self.headers)
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertEqual(data['selection'], chosen[0])
        wave = data['sessions'][0]
        self.assertEqual({clip['clip_index'] for clip in wave['clips']}, {1, 3})
        self.assertEqual(wave['session_id'], self.sid)
        self.assertTrue(wave['session_name'])
        self.assertEqual(wave['session_number'], 1)
        self.assertEqual(wave['wave_number'], 1)
        complete = self.client.get('/api/projects/' + self.pid + '/editor', headers=self.headers).json()
        self.assertEqual(len(complete['sessions'][0]['clips']), 4)

    def test_shared_selection_drives_ai_editor_and_survives_reload(self):
        selected = [self.ref(0), self.ref(2)]
        response = self.client.put(self.base + '/editor-selection', headers=self.headers, json={'clips': selected})
        self.assertEqual(response.status_code, 200)
        state = self.client.get(self.base, headers=self.headers).json()
        self.assertEqual(state['editor_clips'], selected)
        self.assertEqual(state['sessions'][0]['references'], selected)
        app1.jobs.clear()
        self.assertEqual(self.client.get(self.base, headers=self.headers).json()['editor_clips'], selected)
        response = self.client.post(self.base + '/sessions/' + self.sid + '/generate', headers=self.headers,
            json={'prompt': 'more like the selected clips', 'references': [], 'request_id': 'shared-pair'})
        self.assertEqual(response.status_code, 202, response.text)
        jid = response.json()['job_id']
        owner = app1.load_json(app1.JOBS_DIR / jid / 'owner.json')
        self.assertEqual(owner['studio_revision_targets'], selected)
        self.assertEqual(len(owner['parent_clips']), 2)
        clips = [{'start': 41.+i*3, 'end': 43.+i*3, 'title': f'New {i}',
                  'clip_url': f'/clips/{jid}/clip_{i+1}.mp4'} for i in range(4)]
        app1.save_json(app1.JOBS_DIR / jid / 'results.json', {'clips': clips})
        state = self.client.get(self.base, headers=self.headers).json()
        self.assertEqual(state['editor_clips'], [{'job_id': jid, 'clip_index': i} for i in (0,2,1,3)])
        self.assertEqual(state['sessions'][0]['references'], state['editor_clips'])
        editor = self.client.get('/api/projects/' + self.pid + '/editor?selected_only=true', headers=self.headers)
        self.assertEqual(len(editor.json()['sessions'][0]['clips']), 4)
        self.client.put(self.base + '/editor-selection', headers=self.headers, json={'clips': []})
        state = self.client.get(self.base, headers=self.headers).json()
        self.assertEqual(state['editor_clips'], [])
        self.assertEqual(state['sessions'][0]['references'], [])

    def test_shared_selection_keeps_other_sessions_out_of_ai_context(self):
        another = self.client.post(self.base + '/sessions', headers=self.headers,
                                  json={'name': 'Other', 'source_job': self.jid}).json()
        response = self.client.post(self.base + '/sessions/' + another['id'] + '/generate', headers=self.headers,
            json={'prompt': 'A different mood', 'request_id': 'other-wave'})
        jid = response.json()['job_id']
        app1.save_json(app1.JOBS_DIR / jid / 'results.json', {'clips': [
            {'start': 50., 'end': 55., 'title': 'Other session clip', 'clip_url': f'/clips/{jid}/clip_1.mp4'}]})
        selected = [self.ref(0), {'job_id': jid, 'clip_index': 0}]
        self.client.put(self.base + '/editor-selection', headers=self.headers, json={'clips': selected})
        state = self.client.get(self.base, headers=self.headers).json()
        by_id = {session['id']: session for session in state['sessions']}
        self.assertEqual(by_id[self.sid]['references'], [self.ref(0)])
        self.assertEqual(by_id[another['id']]['references'], [selected[1]])
        self.assertEqual(state['editor_clips'], selected)

    def test_unchecked_clip_is_not_reselected_when_its_update_finishes(self):
        self.client.put(self.base + '/editor-selection', headers=self.headers, json={'clips': [self.ref(0)]})
        response = self.client.post(self.base + '/sessions/' + self.sid + '/generate', headers=self.headers,
            json={'prompt': 'similar clips', 'references': [self.ref(0)], 'operation': 'revise', 'request_id': 'uncheck-pending'})
        jid = response.json()['job_id']
        self.client.put(self.base + '/editor-selection', headers=self.headers, json={'clips': []})
        app1.save_json(app1.JOBS_DIR / jid / 'results.json', {'clips': [
            {'start': 42., 'end': 48., 'title': 'Updated', 'clip_url': f'/clips/{jid}/clip_1.mp4'}]})
        self.assertEqual(self.client.get(self.base, headers=self.headers).json()['editor_clips'], [])
