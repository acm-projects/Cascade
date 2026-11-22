"""Stage 3 of the beats pipeline: the AI Editor chat with CASCADE_EDIT_ENGINE=beats, offline.

The model is scripted (no network), transcription returns the fixture transcript, and the background
thread runs inline. Covers: first message, "make it faster", a direct PATCH edit, an invalid PATCH,
undo, and that Cinema stays the default."""
import copy
import json
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from backend.editor.ai_edit import jobs
from backend.editor.ai_edit.beats import llm, workflow
from backend.editor.models import AIEditRef, Edit

HERE = Path(workflow.__file__).parent
TRANSCRIPT = json.loads((HERE/'examples'/'transcript_full.json').read_text())
EXAMPLE = json.loads((HERE/'examples'/'edit_plan_example.json').read_text())
TRIM = dict(start=27.12, end=71.78)


class Script:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, messages, max_tokens=None):
        self.calls.append(system)
        reply = self.replies.pop(0)
        return reply if isinstance(reply, str) else json.dumps(reply)


class InlineThread:
    def __init__(self, target, args=(), **kwargs): self.target, self.args = target, args
    def start(self): self.target(*self.args)


def faster(plan):
    """What a sensible "make it faster" answer looks like: split the two longest beats, leave the rest alone."""
    plan = copy.deepcopy(plan)
    beats = plan['beats']
    i = next(n for n, b in enumerate(beats) if b['id'] == 9)          # 42.88-45.60 "And we're on this glowing example of"
    a = beats[i]; b = copy.deepcopy(a)
    a.update(end=44.4, emphasis_text='GLOWING', accent_word='on this')
    b.update(start=44.4, template='TEXT_BEHIND_SUBJECT', emphasis_text='EXAMPLE', accent_word=None, broll_query=None, broll_fallback_query=None, transition_in='zoom_blur')
    beats.insert(i+1, b)
    return plan


class Chat(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.published = []
        self.draft = {'state': None, 'chat': []}

        def publish(pid, jid, index, user, state, version, duration, text, plan=None):
            self.published.append({'version': version, 'duration': duration, 'text': text, 'plan': plan})
            if plan: self.draft['state'] = (state or self.draft['state']).model_copy(update={'ai_plan': plan})
            if version: self.draft['state'] = self.draft['state'].model_copy(update={'ai_edit': AIEditRef(version=version, duration=duration)})
            self.draft['chat'].append(text)

        @contextmanager
        def media(*a):
            yield self.folder/'clip.mp4'

        def transcribe(video, workdir, progress=None):
            Path(workdir).mkdir(parents=True, exist_ok=True)
            (Path(workdir)/'transcript.json').write_text(json.dumps({'stamp': [0, 0], 'words': TRANSCRIPT}))
            return TRANSCRIPT

        for patch in (mock.patch.object(jobs, 'root', lambda *a: self.folder), mock.patch.object(jobs, '_publish', publish),
                      mock.patch.object(jobs.threading, 'Thread', InlineThread), mock.patch('backend.editor.storage.media', media),
                      mock.patch('backend.editor.storage.selected', lambda *a: {}), mock.patch.object(workflow, 'transcribe', transcribe),
                      mock.patch.dict(os.environ, {'CASCADE_EDIT_ENGINE': 'beats', 'AI_EDITOR_MODEL': 'test-model', 'CASCADE_BEATS_RENDER': 'off'})):
            patch.start(); self.addCleanup(patch.stop)

    def say(self, state, message, *replies):
        script = Script(*replies)
        self.draft['state'] = self.draft['state'] or state
        body = SimpleNamespace(state=state, chat=[], message=message, research_id=None)
        self.assertTrue(jobs.wants(body, {'has_video': True}))
        with mock.patch.object(llm, 'complete', script):
            reply = jobs.turn('p', 'j', 0, 'u', {}, body, {'has_video': True}, None, None)
        self.assertEqual(script.replies, [], 'every scripted model reply was used')
        return reply, json.loads((self.folder/'job.json').read_text()) if reply.get('ai_job') else None

    def patch_beat(self, version, beat_id, **changes):
        request = SimpleNamespace(state=SimpleNamespace(user_id='u'))
        return workflow.patch_route('p', 'j', 0, version, beat_id, workflow.BeatEdit(**changes), request)

    def saved(self, version):
        return workflow.load(self.folder, version)

    def test_full_chat_flow(self):
        # 1. First message: transcribe, plan the trimmed window, save v001.
        state = Edit(**TRIM)
        _, job = self.say(state, 'Edit this video', EXAMPLE, {'issues': [], 'score': 92, 'fixed_plan': EXAMPLE})
        self.assertEqual((job['status'], job['version']), ('done', 'v001'))
        v1 = self.saved('v001')
        self.assertEqual(v1['plan'], {**EXAMPLE, 'source_video': 'source'})
        self.assertEqual((v1['parent_id'], v1['critic_score'], v1['kind'], v1['message']), (None, 92, 'edit', 'Edit this video'))
        self.assertEqual(self.published[-1]['plan'].version, 'v001')
        self.assertIn('23 beats', self.published[-1]['text'])
        self.assertEqual(jobs.versions(self.folder)[0]['engine'], 'beats')

        # 2. "make it faster": revise the current plan; only the affected beats change.
        state = self.draft['state']
        revised = faster(v1['plan'])
        _, job = self.say(state, 'make it faster', {'reply': 'Split beat 9 so it moves faster.', 'changed_beat_ids': [9, 10], 'plan': revised})
        self.assertEqual((job['status'], job['version'], job['changed_beat_ids']), ('done', 'v002', [9, 10]))
        v2 = self.saved('v002')
        self.assertEqual((v2['parent_id'], v2['parent_version'], v2['changed_beat_ids']), (v1['plan_id'], 'v001', [9, 10]))
        strip = lambda b: {k: v for k, v in b.items() if k != 'id'}
        untouched = [strip(b) for b in v2['plan']['beats'] if b['id'] not in (9, 10)]
        self.assertEqual(untouched, [strip(b) for b in v1['plan']['beats'] if b['id'] != 9])   # byte-identical apart from renumbering
        self.assertEqual(len(v2['plan']['beats']), 24)
        self.assertIn('changed beats 9, 10', self.published[-1]['text'])

        # 3. A direct edit of one beat: same validator, new version, only that beat changed.
        result = self.patch_beat('v002', 2, semantic_color='red', emphasis_text='GOD the most')
        v3 = self.saved('v003')
        self.assertEqual((result['ai_plan']['version'], v3['changed_beat_ids'], v3['parent_version'], v3['kind']), ('v003', [2], 'v002', 'manual'))
        self.assertEqual((v3['plan']['beats'][1]['semantic_color'], v3['plan']['beats'][1]['emphasis_text']), ('red', 'GOD the most'))
        self.assertEqual([b for n, b in enumerate(v3['plan']['beats']) if n != 1], [b for n, b in enumerate(v2['plan']['beats']) if n != 1])
        self.assertEqual(self.draft['state'].ai_plan.version, 'v003')

        # 4. Invalid direct edits are refused with a clear reason, and nothing is saved.
        for changes, reason in (({'template': 'BROLL_OVERLAY'}, 'same style as the beat before'),          # beat 4 is already b-roll... (beat 5 follows it)
                                ({'emphasis_text': 'JAGUAR'}, '“jaguar” is not said during beat 5'),
                                ({'template': 'NUMBER_COUNTER'}, 'would need a number')):
            with self.subTest(changes=changes), self.assertRaises(HTTPException) as caught:
                self.patch_beat('v003', 5, **changes)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertIn(reason, caught.exception.detail)
        self.assertFalse((self.folder/'v004').exists())

        # 5. Undo walks back through the parents, then says there is nothing earlier.
        state = self.draft['state']
        for expected in ('v002', 'v001'):
            reply, _ = self.say(state, 'undo your last edit')
            state = Edit.model_validate(reply['state'])
            self.assertEqual(state.ai_plan.version, expected)
            self.assertIn(f'Back to {expected}', reply['message'])
        reply, _ = self.say(state, 'go back')
        self.assertIn('first version', reply['message'])
        self.assertEqual(reply['state']['ai_plan']['version'], 'v001')

        # A follow-up from an older version branches from it: the parent is v001, numbering continues.
        _, job = self.say(state, 'red for the void part', {'reply': 'Made the void red.', 'changed_beat_ids': [8],
                                                           'plan': {**v1['plan'], 'beats': [{**b, 'semantic_color': 'red'} if b['id'] == 8 else b for b in v1['plan']['beats']]}})
        self.assertEqual((job['version'], self.saved('v004')['parent_version'], self.saved('v004')['changed_beat_ids']), ('v004', 'v001', [8]))

    def test_a_question_back_saves_no_version(self):
        self.say(Edit(**TRIM), 'Edit this video', EXAMPLE, {'issues': [], 'score': 90, 'fixed_plan': EXAMPLE})
        _, job = self.say(self.draft['state'], 'make it pop', {'reply': 'Which part should pop more?', 'changed_beat_ids': [], 'plan': self.saved('v001')['plan']})
        self.assertEqual((job['status'], job['version']), ('done', None))
        self.assertEqual(self.published[-1]['text'], 'Which part should pop more?')
        self.assertFalse((self.folder/'v002').exists())

    def test_a_long_clip_lets_the_director_pick_the_window(self):
        _, job = self.say(Edit(start=0, end=175), 'Edit this video', EXAMPLE, {'issues': [], 'score': 90, 'fixed_plan': EXAMPLE})
        self.assertEqual(job['status'], 'done')
        self.assertEqual(self.saved('v001')['plan']['source_window'], {'start': 27.12, 'end': 71.78})

    def test_failures_are_friendly_and_change_nothing(self):
        with mock.patch.dict(os.environ, {'AI_EDITOR_MODEL': ''}):
            _, job = self.say(Edit(**TRIM), 'Edit this video')
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(self.published[-1]['text'], 'NOT CHANGED: The AI editor is not set up on this server yet.')
        self.assertIsNone(self.published[-1]['plan'])
        self.say(Edit(**TRIM), 'Edit this video', EXAMPLE, {'issues': [], 'score': 90, 'fixed_plan': EXAMPLE})
        broken = {'reply': 'x', 'plan': {**EXAMPLE, 'beats': [{**b, 'template': 'KINETIC_KEYWORD'} for b in EXAMPLE['beats']]}}
        _, job = self.say(self.draft['state'], 'kinetic everywhere', broken, broken)
        self.assertEqual(job['status'], 'failed')
        self.assertIn('the edit is unchanged', self.published[-1]['text'])
        self.assertIn('current plan is still in place', self.published[-1]['text'])
        self.assertFalse((self.folder/'v002').exists())

    def test_patch_waits_for_a_running_job(self):
        self.say(Edit(**TRIM), 'Edit this video', EXAMPLE, {'issues': [], 'score': 90, 'fixed_plan': EXAMPLE})
        (self.folder/'job.json').write_text(json.dumps({'status': 'running'}))
        with mock.patch.dict(jobs.RUNNING, {str(self.folder): object()}), self.assertRaises(HTTPException) as caught:
            self.patch_beat('v001', 2, semantic_color='red')
        self.assertEqual(caught.exception.status_code, 409)


class Rendering(Chat):
    """With rendering on (the renderer itself is faked here; real renders are checked by hand and in REPORT.md)."""
    def setUp(self):
        super().setUp()
        self.renders = []
        def fake_render(plan, source, out, work, **kwargs):
            self.renders.append([b['id'] for b in plan['beats']])
            Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b'mp4')
            return {'frames': 2680, 'seconds': 44.667, 'size': [1284, 704], 'rendered_beats': [1], 'reused_beats': [], 'timings': {}, 'checks': {'ok': True}, 'credits': []}
        from backend.editor.ai_edit.beats import render as beats_render
        for patch in (mock.patch.dict(os.environ, {'CASCADE_BEATS_RENDER': 'on'}), mock.patch.object(beats_render, 'render', fake_render),
                      mock.patch.object(beats_render, 'available', lambda: None)):
            patch.start(); self.addCleanup(patch.stop)

    def test_full_chat_flow(self):   # the inherited flow is plan-only; here: rendering makes each version the Edited film
        _, job = self.say(Edit(**TRIM), 'Edit this video', EXAMPLE, {'issues': [], 'score': 92, 'fixed_plan': EXAMPLE})
        self.assertEqual((job['status'], self.published[-1]['version'], self.published[-1]['duration']), ('done', 'v001', 44.667))
        self.assertIn('Preview ready', self.published[-1]['text'])
        self.assertEqual(self.draft['state'].ai_edit.version, 'v001')
        self.assertTrue((self.folder/'v001'/'edited.mp4').is_file())
        self.assertEqual(self.saved('v001')['render']['frames'], 2680)
        state = self.draft['state']
        _, job = self.say(state, 'make it faster', {'reply': 'Faster.', 'changed_beat_ids': [9, 10], 'plan': faster(self.saved('v001')['plan'])})
        self.assertEqual((self.published[-1]['version'], self.draft['state'].ai_edit.version), ('v002', 'v002'))
        reply, _ = self.say(self.draft['state'], 'undo your last edit')
        self.assertEqual((reply['state']['ai_plan']['version'], reply['state']['ai_edit']['version']), ('v001', 'v001'))   # the earlier film comes back too

    def test_a_render_failure_keeps_the_plan(self):
        from backend.editor.ai_edit.beats import render as beats_render
        with mock.patch.object(beats_render, 'render', side_effect=beats_render.RenderError('Chrome went away.')):
            _, job = self.say(Edit(**TRIM), 'Edit this video', EXAMPLE, {'issues': [], 'score': 92, 'fixed_plan': EXAMPLE})
        self.assertEqual(job['status'], 'done')
        self.assertIsNone(self.published[-1]['version'])
        self.assertIn('could not be made (Chrome went away.)', self.published[-1]['text'])
        self.assertEqual(self.draft['state'].ai_plan.version, 'v001')

    test_a_question_back_saves_no_version = test_a_long_clip_lets_the_director_pick_the_window = None
    test_failures_are_friendly_and_change_nothing = test_patch_waits_for_a_running_job = None


class Engines(unittest.TestCase):
    def test_cinema_stays_the_default_and_keeps_its_own_follow_ups(self):
        edit = Edit(**TRIM)
        with mock.patch.dict(os.environ, {'CASCADE_EDIT_ENGINE': ''}):
            self.assertFalse(jobs.uses_beats(edit))
        with mock.patch.dict(os.environ, {'CASCADE_EDIT_ENGINE': 'cinema'}):
            self.assertFalse(jobs.uses_beats(edit))
        with mock.patch.dict(os.environ, {'CASCADE_EDIT_ENGINE': 'beats'}):
            self.assertTrue(jobs.uses_beats(edit))
            self.assertFalse(jobs.uses_beats(edit.model_copy(update={'ai_edit': AIEditRef(version='v001', duration=9)})))  # a Cinema film keeps its engine

    def test_a_leftover_beat_plan_goes_to_openai_when_beats_is_off(self):
        from backend.editor.models import AIPlanRef
        leftover = Edit(**TRIM).model_copy(update={'ai_plan': AIPlanRef.model_construct(version='v001')})
        with mock.patch.dict(os.environ, {'CASCADE_EDIT_ENGINE': ''}):
            self.assertFalse(jobs.uses_beats(leftover))
        with mock.patch.dict(os.environ, {'CASCADE_EDIT_ENGINE': 'beats'}):
            self.assertTrue(jobs.uses_beats(leftover))

    def test_a_cinema_edit_never_goes_back_to_a_beat_plan(self):
        with TemporaryDirectory() as folder, mock.patch.object(jobs, 'root', lambda *a: Path(folder)):
            jobs._write(Path(folder)/'versions.json', [{'version': 'v001', 'request': 'a', 'duration': 9}, {'version': 'v002', 'engine': 'beats', 'request': 'b'},
                                                        {'version': 'v003', 'request': 'c', 'duration': 8}])
            state = Edit(**TRIM, ai_edit=AIEditRef(version='v003', duration=8))
            reply = jobs.turn('p', 'j', 0, 'u', {}, SimpleNamespace(state=state, chat=[], message='go back', research_id=None), {}, None, None)
        self.assertEqual(reply['state']['ai_edit']['version'], 'v001')


if __name__ == '__main__':
    unittest.main()
