"""Intent and selection policy tests never contact a provider."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.agent.intent import classify_request
from backend.agent.tools import ToolBox
from backend.agent.agent import run_agent
from backend.cascade_llm import ToolCall, Turn


class IntentTests(unittest.TestCase):
    def test_structured_response(self):
        with patch('backend.agent.intent.structured_json', return_value=SimpleNamespace(data={'intent': 'specific', 'reason': 'an event'})) as call:
            self.assertEqual(classify_request('the teddy bear fight'), 'specific')
            self.assertEqual(call.call_count, 1)

    def test_failure_and_invalid_output_fallback(self):
        for value in (RuntimeError('offline'), SimpleNamespace(data={'intent': 'unknown'})):
            kwargs = {'side_effect': value} if isinstance(value, Exception) else {'return_value': value}
            with patch('backend.agent.intent.structured_json', **kwargs):
                for prompt, expected in [('sad moments', 'general'), ('best highlights', 'general'),
                                         ('where he fights the teddy bear', 'specific'),
                                         ('find "I quit"', 'specific'), ('the teddy bear fight', 'specific')]:
                    self.assertEqual(classify_request(prompt), expected)


class SelectionPolicyTests(unittest.TestCase):
    def box(self, **kwargs):
        return ToolBox(SimpleNamespace(duration=1000), Path('unused'), **kwargs)

    def add(self, box, start, score=.9, end=None):
        return box._add_candidate(start, start + 10 if end is None else end, 'match', score, 'Moment')

    def test_specific_close_matches_and_low_scores(self):
        box = self.box(intent='specific')
        for start, score in [(10, .9), (22, .8), (34, .49)]:
            self.add(box, start, score)
        box.ranking = [{'id': 2}, {'id': 0}, {'id': 1}]
        self.assertEqual([c['start'] for c in box.final_selection()], [10, 22])
        self.assertFalse(box.spacing_relaxed)

    def test_general_keeps_spread_policy(self):
        box = self.box()
        for start in (10, 22, 270, 520, 770):
            self.add(box, start)
        self.assertEqual([c['start'] for c in box.final_selection()], [10, 270, 520, 770])

    def test_excluded_overlap_is_actionable_and_boundary_allowed(self):
        box = self.box(exclude_windows=[[10, 30]])
        text, error = self.add(box, 12)
        self.assertTrue(error)
        self.assertIn('already shown in this session (10.0–30.0s)', text[0]['text'])
        self.assertFalse(self.add(box, 25)[1])  # exactly 50% is allowed
        self.assertFalse(self.add(box, 50)[1])
        self.assertEqual(box.excluded_candidates, 1)

    def test_specific_still_rejects_overlapping_candidates(self):
        box = self.box(intent='specific')
        self.add(box, 10)
        self.assertTrue(self.add(box, 11)[1])

    def test_large_requested_count_is_selected_without_a_four_clip_cap(self):
        box = self.box(target_clips=20)
        for start in range(0, 1000, 50):
            self.add(box, start)
        self.assertEqual(len(box.final_selection()), 20)

    def test_count_target_gets_a_second_search_without_combined_references(self):
        box = self.box(target_clips=2, require_count=True)
        box._get_overview = lambda: ([{'type': 'text', 'text': 'overview'}], False)
        def candidate(start):
            return {'start_time': start, 'end_time': start + 10, 'reason': 'Match', 'score': .9}
        turns = iter([
            Turn('', [ToolCall('overview', 'get_overview', {})], True),
            Turn('', [ToolCall('one', 'add_candidate', candidate(100)), ToolCall('rank1', 'rank_candidates', {'ranking': [{'id': 0}]})], True),
            Turn('', [ToolCall('two', 'add_candidate', candidate(600)), ToolCall('rank2', 'rank_candidates', {'ranking': [{'id': 0}, {'id': 1}]})], True),
        ])
        conv = SimpleNamespace(start=lambda _: None, take_turn=lambda **_: next(turns), add_tool_results=lambda _: None)
        with patch('backend.agent.agent.research.save_run'):
            self.assertEqual(len(run_agent(box, 'funny moments', conversation=conv)['suggestions']), 2)

    def test_combined_candidates_require_evidence_from_every_reference(self):
        refs = [{'start': 10, 'end': 20}, {'start': 40, 'end': 50}]
        box = self.box(references=refs)
        self.assertTrue(self.add(box, 100)[1])
        matches = [{'reference': 1, 'explanation': 'Comic reversal'}, {'reference': 2, 'explanation': 'Fast physical action'}]
        self.assertFalse(box._add_candidate(100, 115, 'Both qualities', .9, reference_matches=matches)[1])
        self.assertEqual(box.final_selection()[0]['reference_matches'], matches)
        self.assertTrue(box._add_candidate(11, 21, 'Old reference', .9, reference_matches=matches)[1])

    def test_combined_agent_searches_again_after_ranking_just_one_of_two(self):
        box = self.box(target_clips=2, references=[{'start': 10, 'end': 20}, {'start': 40, 'end': 50}])
        box._get_overview = lambda: ([{'type': 'text', 'text': 'overview'}], False)
        matches = [{'reference': 1, 'explanation': 'Humor'}, {'reference': 2, 'explanation': 'Action'}]
        def candidate(start):
            return {'start_time': start, 'end_time': start + 10, 'reason': 'Blend', 'score': .9, 'reference_matches': matches}
        turns = iter([
            Turn('', [ToolCall('overview', 'get_overview', {})], True),
            Turn('', [ToolCall('one', 'add_candidate', candidate(100)), ToolCall('rank1', 'rank_candidates', {'ranking': [{'id': 0}]})], True),
            Turn('', [ToolCall('two', 'add_candidate', candidate(600)), ToolCall('rank2', 'rank_candidates', {'ranking': [{'id': 0}, {'id': 1}]})], True),
        ])
        notes = []
        def turn(**kwargs):
            notes.append(kwargs.get('note') or '')
            return next(turns)
        conv = SimpleNamespace(start=lambda _: None, take_turn=turn, add_tool_results=lambda _: None)
        with patch('backend.agent.agent.research.save_run'):
            result = run_agent(box, 'mix both clips', conversation=conv)
        self.assertEqual(len(result['suggestions']), 2)
        self.assertTrue(any('Only 1 of 2' in note for note in notes))

    def test_agent_receives_specific_and_exclusion_instructions(self):
        box = self.box(intent='specific', exclude_windows=[[10, 30]])
        conversation = SimpleNamespace(start=lambda text: setattr(self, 'first', text),
            take_turn=lambda **kw: (setattr(self, 'system', kw['system']) or SimpleNamespace(
                input_tokens=0, output_tokens=0, text='', continue_loop=False)))
        run_agent(box, 'the teddy bear fight', conversation=conversation)
        self.assertIn('SPECIFIC request', self.system)
        self.assertIn('only clear matches', self.first)
        self.assertIn('already seen', self.first)


if __name__ == '__main__':
    unittest.main()
