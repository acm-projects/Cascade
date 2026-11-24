"""Trend references are videos of the same kind, chosen by the AI, and compared by measurements (editor/trends_pick.py)."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.editor import trends_pick

CLIP = {'title': 'A Jaguar Walks Right By'}
TAGS = {'hook_style': 'first-person story', 'topics': ['jaguars', 'amazon'], 'pacing': 'medium'}


def answer(data):
    return patch('backend.cascade_llm.structured_json', return_value=SimpleNamespace(data=data))


class SearchPlan(unittest.TestCase):
    def test_the_ai_writes_searches_from_what_the_clip_is(self):
        data = {'video_kind': 'podcast clip of a guest telling a story', 'subject': 'a close call with a jaguar',
                'queries': ['#jaguar encounter story', 'jaguar encounter story', '"wildlife podcast"', 'ok', 'amazon jungle story', 'extra', 'one too many']}
        with answer(data) as call:
            plan = trends_pick.search_plan(CLIP, 'one time I was checking a camera trap', TAGS, '', 'make it better')
        self.assertEqual(plan['queries'], ['jaguar encounter story', 'wildlife podcast', 'amazon jungle story', 'extra'])   # cleaned, deduped, short ones dropped, at most 4
        prompt = call.call_args.args[0]
        self.assertIn('A Jaguar Walks Right By', prompt); self.assertIn('camera trap', prompt); self.assertIn('first-person story', prompt)

    def test_no_usable_searches_is_an_error_so_the_keyword_fallback_runs(self):
        with answer({'video_kind': '', 'subject': '', 'queries': ['#', 'a']}), self.assertRaises(ValueError):
            trends_pick.search_plan(CLIP, '', TAGS)


class Screen(unittest.TestCase):
    plan = {'video_kind': 'podcast clip of a guest telling a story', 'subject': 'a close call with a jaguar', 'queries': []}
    found = [{'video_id': 'a'*11, 'title': 'Kigali to Kampala by Bus! Jaguar Bus Ride', 'view_count': 37},
             {'video_id': 'b'*11, 'title': 'Paul Rosolie: The Amazon\'s Jaguar tracks', 'view_count': 1542},
             {'video_id': 'c'*11, 'title': 'SMU Will BEAT Wake Forest', 'view_count': 1080}]

    def test_only_videos_the_ai_judged_the_same_kind_are_kept_with_its_reason(self):
        picks = {'picks': [{'video_id': 'b'*11, 'why': 'A wildlife expert telling a jaguar story on a podcast.'},
                           {'video_id': 'zzzzzzzzzzz', 'why': 'made up'}, {'video_id': 'b'*11, 'why': 'twice'}]}
        with answer(picks) as call:
            kept = trends_pick.screen(self.plan, self.found)
        self.assertEqual([v['video_id'] for v in kept], ['b'*11])   # an id it invented, and a repeat, are ignored
        self.assertEqual(kept[0]['selected_reason'], 'A wildlife expert telling a jaguar story on a podcast.')
        self.assertIn('Wake Forest', call.call_args.args[0])

    def test_none_fitting_is_an_honest_empty_answer(self):
        with answer({'picks': []}):
            self.assertEqual(trends_pick.screen(self.plan, self.found), [])
        self.assertEqual(trends_pick.screen(self.plan, []), [])


class Measurements(unittest.TestCase):
    def test_the_edit_and_each_reference_are_compared_by_the_same_numbers(self):
        edit = {'duration': 60, 'measured_seconds': 60, 'cuts': [5, 20, 40, 55], 'width': 1920, 'height': 1080, 'loudness': [-20, -22, -60, -60]}
        ref = {'duration': 30, 'measured_seconds': 30, 'cuts': [1, 2, 4, 6, 9, 12, 15, 18, 21], 'width': 1080, 'height': 1920, 'loudness': [-14, -16]}
        rows = trends_pick.comparison_table(edit, [{'title': 'Jaguar tracks', 'measured': ref}, {'title': 'Not measured', 'measured': {}}])
        mine, theirs, missing, average = rows
        self.assertEqual((mine['cuts_per_minute'], mine['first_cut_at'], mine['vertical'], mine['quiet_share']), (4.0, 5, False, .5))
        self.assertEqual((theirs['cuts_per_minute'], theirs['first_cut_at'], theirs['vertical'], theirs['average_loudness_db']), (18.0, 1, True, -15.0))
        self.assertEqual(missing, {'video': 'Not measured'})   # nothing guessed
        self.assertEqual((average['video'], average['cuts_per_minute']), ('reference average', 18.0))


if __name__ == '__main__':
    unittest.main()
