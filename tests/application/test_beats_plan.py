"""Stage 2 of the beats pipeline, offline: the validator (a port of critic.py), make_plan and revise_plan
with the model replaced by scripted replies. Fixture: examples/transcript_full.json, window 27.12-71.78."""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.editor.ai_edit.beats import llm, service, validator

HERE = Path(service.__file__).parent
TRANSCRIPT = json.loads((HERE/'examples'/'transcript_full.json').read_text())
EXAMPLE = json.loads((HERE/'examples'/'edit_plan_example.json').read_text())
WINDOW = {'start': 27.12, 'end': 71.78}


def reference_critic(plan):
    """Issues reported by the original reference/scripts/critic.py, as (rule, severity, beat_id) tuples."""
    with tempfile.TemporaryDirectory() as folder:
        p, t = Path(folder)/'plan.json', Path(folder)/'t.json'
        p.write_text(json.dumps(plan)); t.write_text(json.dumps(TRANSCRIPT))
        out = subprocess.run([sys.executable, '-I', str(HERE/'reference'/'scripts'/'critic.py'), str(p), str(t)],
                             capture_output=True, text=True, check=True).stdout
    found = re.findall(r'rule (\d+) (\w+) beat (\w+) -', out)
    return {(int(r), s, None if b == 'None' else int(b)) for r, s, b in found}


def ours(plan):
    return {(i.rule, i.severity, i.beat_id) for i in validator.validate(plan, TRANSCRIPT)}


def mutated(**changes):
    plan = copy.deepcopy(EXAMPLE)
    for beat_id, fields in changes.items():
        plan['beats'][int(beat_id[1:])-1].update(fields)
    return plan


class Validator(unittest.TestCase):
    def test_the_example_plan_passes_both_validators(self):
        self.assertEqual(reference_critic(EXAMPLE), set())
        self.assertEqual(validator.validate(EXAMPLE, TRANSCRIPT), [])

    def test_matches_the_reference_critic_on_broken_plans(self):
        cases = [
            mutated(b3={'template': 'KINETIC_KEYWORD'}, b4={'template': 'KINETIC_KEYWORD'}),
            mutated(b5={'emphasis_text': 'JAGUAR', 'accent_word': 'a b c d e'}),
            mutated(b4={'broll_query': None}, b11={'broll_fallback_query': 'tree frog on leaf | blue morpho butterfly | jaguar walking in jungle | orchid macro'}),
            mutated(b2={'background_mode': 'light'}, b3={'background_mode': 'light'}),
            mutated(b6={'transition_in': 'fade'}, b7={'transition_in': 'fade'}, b8={'transition_in': 'fade'}),
            mutated(b10={'emphasis_text': None}),
        ]
        merged = copy.deepcopy(EXAMPLE)   # a 4.2 s beat in the middle and a gap
        merged['beats'][8]['end'] = merged['beats'][9]['end']; del merged['beats'][9]
        cases.append(merged)
        gap = copy.deepcopy(EXAMPLE); gap['beats'][5]['end'] -= .2
        cases.append(gap)
        for plan in cases:
            with self.subTest(plan=[b['id'] for b in plan['beats']][:3]):
                reference, found = reference_critic(plan), ours(plan)
                self.assertLessEqual(reference, found)
                # the only extra: a per-beat check that spoken_text matches the transcript (rule 1)
                self.assertTrue(all(rule == 1 and beat for rule, _, beat in found-reference), found-reference)

    def test_the_hook_beat_may_run_to_four_seconds(self):
        plan = copy.deepcopy(EXAMPLE)
        plan['beats'][0]['end'] = plan['beats'][1]['end']; del plan['beats'][1]   # a 4.16 s hook
        self.assertIn((3, 'high', 1), ours(plan))
        plan = copy.deepcopy(EXAMPLE)
        plan['beats'][0]['end'] = 30.0; plan['beats'][1]['start'] = 30.0          # a 2.88 s hook, fine
        self.assertNotIn(3, {i.rule for i in validator.validate(*validator.normalize(plan, TRANSCRIPT)[:1], TRANSCRIPT)})

    def test_schema_problems_are_high_severity(self):
        plan = mutated(b1={'template': 'SPINNING_CUBE', 'semantic_color': 'purple', 'data': None})
        found = validator.validate(plan, TRANSCRIPT)
        for expected in ('unknown template', 'semantic_color', 'data must'):
            self.assertTrue(any(expected in i.problem for i in found), expected)
        self.assertTrue(all(i.severity == 'high' for i in found if i.rule == 0))
        self.assertTrue(validator.validate({'beats': []}, TRANSCRIPT))

    def test_number_counter_needs_its_number(self):
        plan = mutated(b8={'template': 'NUMBER_COUNTER'})
        self.assertIn((12, 'high', 8), ours(plan))

    def test_normalize_rebuilds_text_ids_and_tiny_gaps_from_the_transcript(self):
        plan = copy.deepcopy(EXAMPLE)
        for beat in plan['beats']: beat['spoken_text'] = 'wrong'; beat['id'] += 100
        plan['beats'][2]['end'] -= .03
        plan['beats'][0]['start'] = 27.15
        fixed, notes = validator.normalize(plan, TRANSCRIPT)
        self.assertEqual(fixed, EXAMPLE)
        self.assertTrue(notes)
        self.assertEqual(plan['beats'][0]['spoken_text'], 'wrong')   # the input is not changed

    def test_resemblance(self):
        self.assertEqual(validator.resemblance(EXAMPLE, EXAMPLE)['shared_boundaries'], 1.0)


class Script:
    """Stands in for llm.complete: returns scripted replies in order and records every call."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, messages, max_tokens=None):
        self.calls.append({'system': system, 'messages': copy.deepcopy(messages)})
        reply = self.replies.pop(0)
        return reply if isinstance(reply, str) else json.dumps(reply)


def fenced(data):
    return '```json\n' + json.dumps(data, indent=1) + '\n```'


def critic_ok(plan, score=91):
    return {'issues': [], 'score': score, 'fixed_plan': plan}


class Service(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(os.environ, {'AI_EDITOR_MODEL': 'test-model', 'AI_EDITOR_PROVIDER': 'anthropic'})
        patch.start(); self.addCleanup(patch.stop)

    def run_with(self, script, fn, *args, **kwargs):
        with mock.patch.object(llm, 'complete', script):
            return fn(*args, **kwargs)

    def test_make_plan_uses_the_prompt_files_and_the_example_as_one_few_shot_turn(self):
        script = Script(fenced(EXAMPLE), critic_ok(EXAMPLE))
        result = self.run_with(script, service.make_plan, TRANSCRIPT, WINDOW)
        self.assertEqual(result.plan, EXAMPLE)
        self.assertEqual(result.issues, [])
        self.assertEqual((result.rounds, result.critic_score, result.validator_score, result.model), (1, 91, 100, 'test-model'))
        director, critic = script.calls
        self.assertEqual(director['system'], (HERE/'prompts'/'director_prompt.txt').read_text())
        self.assertEqual(critic['system'], (HERE/'prompts'/'critic_prompt.txt').read_text())
        roles = [m['role'] for m in director['messages']]
        self.assertEqual(roles, ['user', 'assistant', 'user'])
        self.assertEqual(json.loads(director['messages'][1]['content']), EXAMPLE)
        real = json.loads(director['messages'][2]['content'])
        self.assertEqual(real['window'], WINDOW)
        self.assertEqual(len(real['transcript']), sum(len(b['spoken_text'].split()) for b in EXAMPLE['beats']))   # only the window's words

    def test_director_mistakes_needing_no_judgement_are_repaired_without_a_retry(self):
        sloppy = copy.deepcopy(EXAMPLE)
        for beat in sloppy['beats']: beat['spoken_text'] = beat['spoken_text'].lower()+' extra'
        sloppy['source_window'] = {'start': 0, 'end': 999}   # the window is the caller's, not the model's
        script = Script('Here is the plan:\n' + json.dumps(sloppy) + '\nEnjoy!', critic_ok(EXAMPLE))
        result = self.run_with(script, service.make_plan, TRANSCRIPT, WINDOW)
        self.assertEqual(result.plan, EXAMPLE)
        self.assertEqual(len(script.calls), 2)
        self.assertTrue(result.notes)

    def test_an_invalid_plan_is_retried_once_with_the_validation_errors(self):
        broken = mutated(b5={'template': 'KINETIC_KEYWORD', 'emphasis_text': 'JAGUAR'})
        script = Script(json.dumps(broken), json.dumps(EXAMPLE), critic_ok(EXAMPLE))
        result = self.run_with(script, service.make_plan, TRANSCRIPT, WINDOW)
        self.assertEqual(result.plan, EXAMPLE)
        retry = script.calls[1]['messages']
        self.assertEqual(retry[-2]['role'], 'assistant')
        self.assertIn('same template back to back', retry[-1]['content'])
        self.assertIn("'jaguar' in emphasis_text not spoken", retry[-1]['content'])

    def test_unparseable_twice_is_a_friendly_error(self):
        script = Script('nope', 'still nope')
        with self.assertRaises(llm.PlanError) as caught:
            self.run_with(script, service.make_plan, TRANSCRIPT, WINDOW)
        self.assertNotIn('JSON', caught.exception.user_message)
        self.assertEqual(len(script.calls), 2)

    def test_the_critic_fixes_what_the_director_left_and_stops_after_two_rounds(self):
        broken = mutated(b5={'template': 'KINETIC_KEYWORD'})
        still_broken = mutated(b5={'template': 'KINETIC_KEYWORD'})
        issue = [{'beat_id': 4, 'rule': 4, 'severity': 'high', 'problem': 'repeat', 'fix': 'use BROLL_OVERLAY'}]
        script = Script(json.dumps(broken), json.dumps(still_broken),        # director + its one retry
                        {'issues': issue, 'score': 70, 'fixed_plan': EXAMPLE},  # critic round 1 fixes it
                        critic_ok(EXAMPLE, 94))                               # round 2: nothing left
        result = self.run_with(script, service.make_plan, TRANSCRIPT, WINDOW)
        self.assertEqual((result.plan, result.rounds, result.critic_score), (EXAMPLE, 2, 94))

    def test_a_critic_plan_that_is_worse_is_not_taken_and_remaining_high_issues_fail(self):
        worse = mutated(b5={'template': 'KINETIC_KEYWORD'}, b8={'template': 'KINETIC_KEYWORD'}, b9={'template': 'KINETIC_KEYWORD'})
        script = Script(json.dumps(EXAMPLE), {'issues': [{'rule': 7}], 'score': 80, 'fixed_plan': worse}, critic_ok(EXAMPLE))
        self.assertEqual(self.run_with(script, service.make_plan, TRANSCRIPT, WINDOW).plan, EXAMPLE)
        broken = mutated(b5={'template': 'KINETIC_KEYWORD'})
        script = Script(json.dumps(broken), json.dumps(broken), {'issues': [], 'score': 50, 'fixed_plan': broken},
                        {'issues': [], 'score': 50, 'fixed_plan': broken})
        with self.assertRaises(llm.PlanError):
            self.run_with(script, service.make_plan, TRANSCRIPT, WINDOW)

    def test_the_model_name_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {'AI_EDITOR_MODEL': ''}):
            with self.assertRaises(llm.PlanError) as caught:
                llm.model()
        self.assertIn('AI_EDITOR_MODEL', caught.exception.detail)

    def test_revise_reports_the_beats_that_actually_changed(self):
        revised = mutated(b7={'semantic_color': 'red'}, b20={'emphasis_text': 'APEX OF LIFE'})
        claimed = {'reply': 'Made the void red and the apex bigger.', 'changed_beat_ids': [1, 2, 3], 'plan': revised}
        script = Script(fenced(claimed))
        result = self.run_with(script, service.revise_plan, EXAMPLE, TRANSCRIPT, 'red for the void part')
        self.assertEqual(result.changed_beat_ids, [7, 20])
        self.assertEqual(result.reply, 'Made the void red and the apex bigger.')
        self.assertEqual(script.calls[0]['system'], (HERE/'prompts'/'revise_prompt.txt').read_text())
        sent = json.loads(script.calls[0]['messages'][0]['content'])
        self.assertEqual((sent['current_plan'], sent['user_message']), (EXAMPLE, 'red for the void part'))

    def test_revise_may_split_beats_and_never_moves_the_window(self):
        split = copy.deepcopy(EXAMPLE)
        a = split['beats'][6]; b = {**copy.deepcopy(a), 'start': 39.68, 'template': 'KINETIC_KEYWORD', 'emphasis_text': 'MAJORITY', 'accent_word': None,
                                    'broll_query': None, 'broll_fallback_query': None}
        a['end'] = 39.68; a['emphasis_text'] = 'ALL'; a['accent_word'] = None
        split['beats'].insert(7, b)
        split['source_window'] = {'start': 20, 'end': 80}
        script = Script({'reply': 'Split beat 7.', 'changed_beat_ids': [7, 8], 'plan': split})
        result = self.run_with(script, service.revise_plan, EXAMPLE, TRANSCRIPT, 'split beat 7')
        self.assertEqual(result.plan['source_window'], EXAMPLE['source_window'])
        self.assertEqual(len(result.plan['beats']), 24)
        self.assertEqual([b['id'] for b in result.plan['beats']], list(range(1, 25)))
        self.assertEqual(result.changed_beat_ids[:2], [7, 8])
        self.assertEqual(validator.high([validator.Issue(**i) for i in result.issues]), [])

    def test_a_clarifying_question_leaves_the_plan_unchanged(self):
        script = Script({'reply': 'Which part should be red?', 'changed_beat_ids': [], 'plan': EXAMPLE})
        result = self.run_with(script, service.revise_plan, EXAMPLE, TRANSCRIPT, 'make it red')
        self.assertEqual((result.plan, result.changed_beat_ids, result.reply), (EXAMPLE, [], 'Which part should be red?'))

    def test_a_revision_that_breaks_the_rules_twice_keeps_the_plan(self):
        bad = mutated(b5={'template': 'KINETIC_KEYWORD'})
        original = copy.deepcopy(EXAMPLE)
        script = Script({'reply': 'x', 'plan': bad}, {'reply': 'x', 'plan': bad})
        with self.assertRaises(llm.PlanError) as caught:
            self.run_with(script, service.revise_plan, EXAMPLE, TRANSCRIPT, 'kinetic everywhere')
        self.assertIn('unchanged', caught.exception.user_message)
        self.assertEqual(EXAMPLE, original)


class OpenAI(unittest.TestCase):
    def test_openai_gets_the_same_conversation_in_json_mode(self):
        calls = []
        class Responses:
            def create(self, **kw):
                calls.append(kw)
                part = mock.Mock(type='output_text', text='{"ok": 1}')
                return mock.Mock(status='completed', output=[mock.Mock(type='message', content=[part])])
        client = mock.Mock(responses=Responses())
        with mock.patch.dict(os.environ, {'AI_EDITOR_PROVIDER': 'openai', 'AI_EDITOR_OPENAI_MODEL': 'gpt-test'}), \
                mock.patch('backend.cascade_llm.clients.make_client', return_value=client):
            text = llm.complete('SYSTEM', [{'role': 'user', 'content': 'example'}, {'role': 'assistant', 'content': '{}'}, {'role': 'user', 'content': 'real'}])
        self.assertEqual(text, '{"ok": 1}')
        call = calls[0]
        self.assertEqual((call['model'], call['instructions'], call['text']), ('gpt-test', 'SYSTEM', {'format': {'type': 'json_object'}}))
        self.assertEqual([t['role'] for t in call['input']], ['user', 'assistant', 'user'])
        self.assertIn('JSON', call['input'][-1]['content'])

    def test_provider_choice(self):
        with mock.patch.dict(os.environ, {'AI_EDITOR_PROVIDER': '', 'ANTHROPIC_API_KEY': ''}):
            self.assertEqual(llm.provider(), 'openai')
        with mock.patch.dict(os.environ, {'AI_EDITOR_PROVIDER': '', 'ANTHROPIC_API_KEY': 'k'}):
            self.assertEqual(llm.provider(), 'anthropic')
        with mock.patch.dict(os.environ, {'AI_EDITOR_PROVIDER': 'openai', 'ANTHROPIC_API_KEY': 'k'}):
            self.assertEqual(llm.provider(), 'openai')


class ReadyMade(unittest.TestCase):
    def test_the_example_plan_lands_on_a_clip_cut_elsewhere_with_slightly_different_word_times(self):
        from backend.editor.ai_edit.beats import demo
        import random
        rand = random.Random(3)
        clip = [{'word': w['word'].lower().strip('.,?'), 'start': round(w['start']-20+rand.uniform(-.06, .06), 2),
                 'end': round(w['end']-20+rand.uniform(-.06, .06), 2)} for w in TRANSCRIPT if 15 <= w['start'] < 80]
        plan = demo.matching_plan(clip)
        self.assertIsNotNone(plan)
        self.assertAlmostEqual(plan['source_window']['start'], 7.12, delta=.1)
        self.assertEqual([b['template'] for b in plan['beats']], [b['template'] for b in EXAMPLE['beats']])
        self.assertEqual([i for i in validator.validate(plan, clip) if i.rule == 0 or 'gap' in i.problem], [])

    def test_other_speech_or_a_clip_too_short_gets_nothing(self):
        from backend.editor.ai_edit.beats import demo
        self.assertIsNone(demo.matching_plan([w for w in TRANSCRIPT if w['start'] > 100]))
        self.assertIsNone(demo.matching_plan(TRANSCRIPT, 30, 60))           # the trim cuts into the demo section


class ParseJson(unittest.TestCase):
    def test_fences_and_chatter(self):
        self.assertEqual(llm.parse_json('```json\n{"a": 1}\n```'), {'a': 1})
        self.assertEqual(llm.parse_json('```\n{"a": 1}\n```'), {'a': 1})
        self.assertEqual(llm.parse_json('Sure! {"a": {"b": 2}} hope that helps'), {'a': {'b': 2}})
        for bad in ('', 'no json', '[1, 2]'):
            with self.assertRaises(ValueError): llm.parse_json(bad)


if __name__ == '__main__':
    unittest.main()
