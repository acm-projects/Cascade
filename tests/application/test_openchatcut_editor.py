"""OpenChatCut + Gemini free-tier AI Editor: planning, quota safety, compilation (no network)."""
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from backend.editor import gemini_planner, sequence_ai
from backend.editor.audio_assets import AudioStore
from backend.editor.models import Edit
from backend.editor.openchatcut_render import build_spec
from backend.editor.sequence_models import OPENCHATCUT_ENGINE, FablecutSequence, SequenceShot

FAKE_KEY = 'AIza-test-key-should-never-appear-0123456789'


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status; self._body = body
    def json(self):
        return self._body


class FakeClient:
    calls = []
    def __init__(self, responses):
        self.responses = list(responses)
    def __call__(self, *a, **k):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def post(self, url, headers=None, json=None):
        FakeClient.calls.append({'url': url, 'headers': headers, 'body': json})
        return self.responses.pop(0)


def plan_response(payload):
    return FakeResponse(200, {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(payload)}]}}]})


class GeminiPlannerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {'GEMINI_API_KEY': FAKE_KEY, 'CASCADE_EDITOR_AI_USAGE': str(Path(self.dir.name)/'usage.json')})
        self.env.start(); FakeClient.calls = []

    def tearDown(self):
        self.env.stop(); self.dir.cleanup()

    def test_paid_or_unknown_models_are_refused(self):
        with mock.patch.dict(os.environ, {'CASCADE_EDITOR_GEMINI_MODEL': 'gemini-3.1-pro-preview'}):
            with self.assertRaises(HTTPException) as raised:
                gemini_planner.model()
        self.assertEqual(raised.exception.status_code, 503)

    def test_one_request_returns_json_and_counts_usage(self):
        client = FakeClient([plan_response({'ok': True})])
        with mock.patch.object(gemini_planner.httpx, 'Client', client):
            self.assertEqual(gemini_planner.generate_json('sys', [gemini_planner.text_part('x')], {'type': 'object'}), {'ok': True})
        self.assertEqual(len(FakeClient.calls), 1)
        self.assertEqual(FakeClient.calls[0]['headers'], {'x-goog-api-key': FAKE_KEY})  # header only, never URL
        self.assertNotIn(FAKE_KEY, FakeClient.calls[0]['url'])
        self.assertEqual(gemini_planner.usage()['used'], 1)

    def test_daily_quota_stops_immediately_and_never_leaks_the_key(self):
        daily = FakeResponse(429, {'error': {'status': 'RESOURCE_EXHAUSTED', 'message': f'quota for key {FAKE_KEY}', 'details': [
            {'violations': [{'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaValue': '20'}]},
            {'retryDelay': '12705s'}]}})
        client = FakeClient([daily, plan_response({'never': 'used'})])
        with self.assertLogs('backend.editor.gemini_planner', level=logging.INFO) as logs, \
                mock.patch.object(gemini_planner.httpx, 'Client', client):
            with self.assertRaises(gemini_planner.QuotaError) as raised:
                gemini_planner.generate_json('sys', [], {'type': 'object'})
        self.assertEqual(len(FakeClient.calls), 1)  # no retry, no fallback
        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn('Nothing was changed', raised.exception.detail)
        self.assertNotIn(FAKE_KEY, raised.exception.detail + ' '.join(logs.output))
        self.assertTrue(gemini_planner.usage()['exhausted'])
        with mock.patch.object(gemini_planner.httpx, 'Client', FakeClient([])):
            with self.assertRaises(gemini_planner.QuotaError):  # later requests stop before any network call
                gemini_planner.generate_json('sys', [], {'type': 'object'})

    def test_overload_fails_over_to_next_free_model_only(self):
        busy = FakeResponse(503, {'error': {'status': 'UNAVAILABLE'}})
        client = FakeClient([busy, plan_response({'ok': 1})])
        with mock.patch.object(gemini_planner.httpx, 'Client', client):
            self.assertEqual(gemini_planner.generate_json('sys', [], {'type': 'object'}), {'ok': 1})
        used = [c['url'].split('/models/')[1].split(':')[0] for c in FakeClient.calls]
        self.assertEqual(used, list(gemini_planner.FREE_MODELS[:2]))
        self.assertTrue(all(m in gemini_planner.FREE_MODELS for m in used))
        self.assertEqual(gemini_planner.last_model(), gemini_planner.FREE_MODELS[1])

    def test_all_free_models_overloaded_changes_nothing(self):
        busy = FakeResponse(503, {'error': {'status': 'UNAVAILABLE'}})
        with mock.patch.object(gemini_planner.httpx, 'Client', FakeClient([busy] * len(gemini_planner.FREE_MODELS))):
            with self.assertRaises(HTTPException) as raised:
                gemini_planner.generate_json('sys', [], {'type': 'object'})
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn('Nothing was changed', raised.exception.detail)

    def test_missing_key_is_actionable(self):
        with mock.patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            with self.assertRaises(HTTPException) as raised:
                gemini_planner.generate_json('sys', [], {'type': 'object'})
        self.assertIn('GEMINI_API_KEY', raised.exception.detail)


class OpenChatCutSequenceTests(unittest.TestCase):
    def test_inlined_schemas_keep_property_names_gemini_requires(self):
        # Regression: dropping the annotation key "title" must not drop a FIELD named title.
        from backend.editor import ai
        for schema in (sequence_ai.inline_schema(sequence_ai.OccPlan), ai._inline(ai.proposal_schema())):
            def check(node):
                if isinstance(node, dict):
                    if 'required' in node and 'properties' in node:
                        self.assertFalse(set(node['required']) - set(node['properties']))
                    self.assertNotIn('$ref', node)
                    for value in node.values(): check(value)
                elif isinstance(node, list):
                    for value in node: check(value)
            check(schema)
        self.assertIn('title', sequence_ai.inline_schema(sequence_ai.OccPlan)['properties'])

    def test_engine_specific_settings_are_validated(self):
        with self.assertRaises(ValueError):  # OpenChatCut never claims an unexecuted ramp
            FablecutSequence(engine=OPENCHATCUT_ENGINE, shots=[SequenceShot(start=0, end=2, rate_from=1.5, rate_to=.5)])
        with self.assertRaises(ValueError):  # FableCut cannot execute OpenChatCut-only transitions
            FablecutSequence(shots=[SequenceShot(start=0, end=2), SequenceShot(start=3, end=5, transition='flash')])
        legacy = FablecutSequence.model_validate({'shots': [{'start': 0, 'end': 2}]})
        self.assertEqual((legacy.engine, legacy.look, legacy.framing), ('fablecut-1.18.0', 'none', 'blur'))

    def test_single_gemini_plan_compiles_to_bounded_openchatcut_sequence(self):
        plan = sequence_ai.OccPlan.model_validate({
            'rationale': 'hook then action', 'music_asset_id': None, 'grade': .1, 'look': 'teal-orange', 'film_grain': True,
            'framing': 'blur', 'title': 'No way out', 'caption_animation': 'pop', 'sound_design': True, 'unsupported': ['masks'],
            'shots': [{'candidate': c, 'beats': 2, 'slow_motion': c == 2, 'zoom': 1.2, 'zoom_style': 'snap', 'shake': True,
                       'transition': t, 'reason': 'action'} for c, t in ((0, 'none'), (1, 'whip'), (2, 'flash'), (3, 'glitch'), (4, 'shake'))]})
        state = Edit(start=0, end=20)
        info = {'duration': 20, 'has_video': True, 'width': 960, 'height': 540,
                'cues': [{'start': 0.2, 'end': 1.8, 'text': 'Spoken hook line'}]}
        hints = {'scene_boundaries': [4, 8, 12, 16]}
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.dict(os.environ, {'CASCADE_EDITOR_PROVIDER': 'openchatcut'}), \
                mock.patch('backend.editor.openchatcut_render.engine_path', return_value=Path(directory)), \
                mock.patch.object(sequence_ai, 'gemini_plan', return_value=plan) as planned, \
                mock.patch('backend.editor.beats.analyze', return_value={'bpm': 120, 'confidence': .9, 'beats': []}), \
                mock.patch('backend.editor.gemini_planner.usage', return_value={'used': 1, 'limit': 20, 'resets': '2:00 AM', 'exhausted': False, 'model': 'gemini-3.6-flash'}):
            result = sequence_ai.edit(state, 'Make this a high-energy reel', [], info, hints, [], AudioStore(Path(directory)/'audio'))
        planned.assert_called_once()  # exactly one planning request
        seq = FablecutSequence.model_validate(result['state']['fablecut'])
        self.assertEqual(seq.engine, OPENCHATCUT_ENGINE)
        self.assertEqual((seq.look, seq.film_grain, seq.framing, seq.title), ('teal-orange', True, 'blur', 'No way out'))
        self.assertLessEqual(sum(s.transition != 'none' for s in seq.shots), 3)
        self.assertLessEqual(sum(s.shake > 0 for s in seq.shots), 2)
        self.assertLessEqual(sum(s.rate_from != 1 for s in seq.shots), 1)
        self.assertTrue(all(s.rate_from == s.rate_to for s in seq.shots))
        self.assertEqual(result['analysis']['engine'], 'OpenChatCut 0.2.17')
        self.assertIn('masks', result['unsupported'])

    def test_spec_uses_only_verified_assets_and_maps_captions(self):
        state = Edit(start=0, end=20, fablecut=FablecutSequence(engine=OPENCHATCUT_ENGINE, look='teal-orange', title='Go', shots=[
            SequenceShot(start=0, end=2, zoom=1.2, zoom_style='punch', shake=2.5),
            SequenceShot(start=6, end=8, transition='whip', rate_from=.6, rate_to=.6)]))
        state.captions.enabled = True
        info = {'duration': 20, 'width': 960, 'height': 540, 'cues': [{'start': .5, 'end': 1.5, 'text': 'keep this spoken line'}]}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            spec, total = build_spec(state, info, AudioStore(folder/'audio'), folder/'base.mp4', folder, folder/'out.mp4')
        self.assertEqual((spec['width'], spec['height']), (1080, 1920))
        self.assertAlmostEqual(total, 2 + 2/.6, places=3)
        ids = json.dumps(spec)
        for asset in ('library:zoom:punch', 'builtin:fx-shake', 'builtin:tr-whip-pan', 'builtin:look-teal-orange'):
            self.assertIn(asset, ids)
        self.assertTrue(spec['shots'][1]['mute'])
        self.assertEqual(spec['texts'][0]['text'], 'GO')
        self.assertTrue(any(t['text'].startswith('keep this') for t in spec['texts']))
        self.assertNotIn('http', ids)


if __name__ == '__main__':
    unittest.main()
