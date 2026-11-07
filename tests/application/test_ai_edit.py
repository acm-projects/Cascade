"""The finished-edit workflow, offline: no Claude, no render. Real renders are checked by hand in the app."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from backend.editor.ai_edit import jobs, layout, page
from backend.editor.ai_edit.models import Plan, check
from backend.editor.models import AIEditRef, Edit


def words(text, step=.4):
    return [{'i': i, 'w': w, 's': round(i*step, 3), 'e': round(i*step+step*.9, 3)} for i, w in enumerate(text.split())]


WORDS = words('We can not wait. The planet is burning now. It will cook. People are fighting for it today.')


def plan(**changes):
    base = {'bpm': 72, 'mood': 'dark', 'lines': [
        {'from_word': 0, 'to_word': 3, 'key_word': 3, 'gap_before': .3, 'phrases': [{'from_word': 0, 'to_word': 3, 'hero': 3}], 'shots': [{'at_word': 0, 'kind': 'source', 'src': 4}]},
        {'from_word': 4, 'to_word': 8, 'key_word': 7, 'phrases': [{'from_word': 4, 'to_word': 6, 'hero': 6}, {'from_word': 7, 'to_word': 8, 'hero': 8}], 'shots': [{'at_word': 4, 'kind': 'sync'}]},
    ]}
    return Plan.model_validate({**base, **changes})


class Layout(unittest.TestCase):
    def test_key_words_land_on_beats_and_nothing_overlaps(self):
        chosen = plan()
        built = layout.build(chosen, WORDS)
        previous = 0
        for line in built.lines:
            key = next(t for _, t, i in line['words'] if i == line['plan'].key_word)
            self.assertLess(abs(key/built.beat-round(key/built.beat)), .05)
            self.assertGreaterEqual(line['t'], previous)
            previous = line['end']
        for one, two in zip(built.events, built.events[1:]):
            self.assertAlmostEqual(one.end, two.start)
        self.assertEqual(built.events[0].start, 0)
        self.assertEqual(built.events[-1].end, built.total)

    def test_verdict_gets_graphics_on_whole_beats_then_footage_without_empty_frames(self):
        lines = [*plan().model_dump()['lines'], {'from_word': 9, 'to_word': 11, 'key_word': 11, 'verdict': True, 'shots': []},
                 {'from_word': 12, 'to_word': 17, 'key_word': 13, 'shots': [{'at_word': 12, 'kind': 'source', 'src': 8}]}]
        built = layout.build(Plan.model_validate({'bpm': 72, 'mode': 'earth', 'closing_src': 5, 'lines': lines}), WORDS)
        for t in (built.closing[0], built.closing[1], built.silence[0]):
            self.assertLess(abs(t/built.beat-round(t/built.beat))*built.beat, 2/30)
        after = next(e for e in built.events if e.start >= built.reset[1]-.001)
        self.assertNotEqual(after.kind, 'ink')
        self.assertAlmostEqual(after.start, built.reset[1])

    def test_long_holds_get_a_visual_change(self):
        long_words = words(' '.join(['word']*40))
        chosen = Plan.model_validate({'bpm': 72, 'lines': [{'from_word': 0, 'to_word': 39, 'key_word': 5, 'shots': [{'at_word': 0, 'kind': 'sync'}]}]})
        footage = [e for e in layout.build(chosen, long_words).events if e.kind != 'ink']
        self.assertGreater(len(footage), 3)
        self.assertTrue(all(e.end-e.start <= 3.6 for e in footage))


class Captions(unittest.TestCase):
    def test_no_dots_or_typed_full_stops_on_ordinary_captions(self):
        chosen = plan()
        document, dots = page.build(chosen, layout.build(chosen, WORDS), False, False, [])
        self.assertEqual(dots, [])  # a dot after every sentence looked like periods everywhere
        self.assertRegex(document, r'class="big">planet</div>')  # the hero "is" is filler, so the real word takes the big slot
        self.assertNotIn('wait.<', document)
        self.assertIn('>wait</div>', document)

    def test_only_a_verdict_ends_on_the_dot(self):
        lines = [*plan().model_dump()['lines'], {'from_word': 9, 'to_word': 11, 'key_word': 11, 'verdict': True, 'shots': []}]
        chosen = Plan.model_validate({'bpm': 72, 'lines': lines})
        _, dots = page.build(chosen, layout.build(chosen, WORDS), False, False, [])
        self.assertEqual(len(dots), 1)  # "cook." closes the verdict

    def test_end_card_sums_it_up_and_says_edited_by_cascade(self):
        chosen = plan(end_hero='Never again.', end_line='Some walks you never forget.')
        document, _ = page.build(chosen, layout.build(chosen, WORDS), False, False, [])
        self.assertIn('>Never again</div>', document)  # no full stop on the end card
        self.assertIn('Some walks you never forget</div>', document)
        self.assertIn('Edited by</span><b>Cascade</b>', document)
        bare = plan()  # even with nothing to say, the film ends on the Cascade credit
        self.assertIn('Edited by</span><b>Cascade</b>', page.build(bare, layout.build(bare, WORDS), False, False, [])[0])

    def test_closing_circle_and_silence_dot_only_in_earth_mode(self):
        lines = [*plan().model_dump()['lines'], {'from_word': 9, 'to_word': 11, 'key_word': 11, 'verdict': True, 'shots': []}]
        core = Plan.model_validate({'bpm': 72, 'closing_src': 5, 'lines': lines})
        self.assertIsNone(core.closing_src)
        built = layout.build(core, WORDS)
        self.assertIsNone(built.closing)
        self.assertNotIn('class="clip stopdot"', page.build(core, built, False, False, [])[0])


class Checks(unittest.TestCase):
    def test_scrapbook_look(self):
        lines = [*plan().model_dump()['lines'], {'from_word': 9, 'to_word': 11, 'key_word': 11, 'verdict': True, 'shots': []}]
        lines[0]['shots'] = [{'at_word': 0, 'kind': 'source', 'src': 4}]
        chosen = Plan.model_validate({'bpm': 72, 'mode': 'talk', 'end_line': 'half pit bull, all sweetheart', 'lines': lines})
        document, dots = page.build(chosen, layout.build(chosen, WORDS), False, False, [], look='scrapbook')
        self.assertIn('class="scrap"', document)
        self.assertIn('class="lab', document)  # cut-out labels
        self.assertIn('clip photo', document)  # cutaways pinned up as photos
        self.assertIn('half pit bull, all sweetheart</p>', document)  # the handwritten closing line
        self.assertIn('class="fill">Cascade</span>', document)  # the leopard wordmark ending
        self.assertNotIn('ebrand', document.split('</style>')[1])
        self.assertEqual(dots, [])

    def test_point_look_unchanged_by_default(self):
        chosen = plan()
        self.assertNotIn('class="scrap"', page.build(chosen, layout.build(chosen, WORDS), False, False, [])[0])

    def test_talk_mode_keeps_the_speakers_on_screen(self):
        lines = [{'from_word': 0, 'to_word': 3, 'key_word': 3, 'verdict': True, 'shots': [{'at_word': i, 'kind': 'stock', 'query': 'x'} for i in range(4)]},
                 {'from_word': 4, 'to_word': 8, 'key_word': 7, 'verdict': True, 'shots': [{'at_word': 4, 'kind': 'sync'}]}]
        talk = Plan.model_validate({'bpm': 72, 'mode': 'talk', 'lines': lines})
        self.assertEqual(sum(s.kind == 'stock' for l in talk.lines for s in l.shots), 4)
        self.assertEqual(sum(l.verdict for l in talk.lines), 1)

    def test_a_hero_written_as_a_word_becomes_its_number(self):
        chosen = plan()
        chosen.lines[1].phrases[0].hero = 'Planet'
        chosen.lines[1].phrases[1].hero = 'gone'  # not in the phrase: shown without a big word
        check(chosen, WORDS, [(0, 99)])
        self.assertEqual(chosen.lines[1].phrases[0].hero, 5)
        self.assertIsNone(chosen.lines[1].phrases[1].hero)
        page.build(chosen, layout.build(chosen, WORDS), False, False, [])

    def test_rejects_long_phrases_and_times_outside_the_trim(self):
        bad = plan(lines=[{'from_word': 0, 'to_word': 8, 'key_word': 3, 'phrases': [{'from_word': 0, 'to_word': 8}]}])
        with self.assertRaisesRegex(ValueError, 'more than 5'):
            check(bad, WORDS, [[0, 100]])
        with self.assertRaisesRegex(ValueError, 'outside'):
            check(plan(), WORDS, [[0, .5]])


def body(state, message):
    return SimpleNamespace(state=state, chat=[], message=message, research_id=None)


class Routing(unittest.TestCase):
    state = Edit(start=0, end=10)

    def test_edit_requests_and_followups_route_here(self):
        with patch('backend.editor.ai.claude_plan', return_value='pro'):
            self.assertTrue(jobs.wants(body(self.state, 'edit this clip'), {'has_video': True}))
            self.assertFalse(jobs.wants(body(self.state, 'make the captions yellow'), {'has_video': True}))
            self.assertFalse(jobs.wants(body(self.state, 'edit this with a storyboard'), {'has_video': True}))
            self.assertFalse(jobs.wants(body(self.state, 'edit this clip'), {'has_video': False}))
            edited = self.state.model_copy(update={'ai_edit': AIEditRef(version='v001', duration=9)})
            self.assertTrue(jobs.wants(body(edited, 'make the captions yellow'), {'has_video': True}))

    def test_never_without_the_claude_plan(self):
        with patch('backend.editor.ai.claude_plan', return_value=''):
            self.assertFalse(jobs.wants(body(self.state, 'edit this clip'), {'has_video': True}))


class Failure(unittest.TestCase):
    def test_a_failed_revision_keeps_the_last_edit_and_says_why(self):
        edited = Edit(start=0, end=10, ai_edit=AIEditRef(version='v001', duration=9))
        with TemporaryDirectory() as folder, patch.object(jobs, '_publish') as publish, patch('backend.editor.storage.media', side_effect=HTTPException(429, 'usage limit reached')):
            folder = Path(folder)
            job = {'id': 'x', 'status': 'queued', 'progress': 0, 'stage': '', 'version': None, 'message': '', 'finished': None}
            with jobs.GUARD: jobs.RUNNING[str(folder)] = object()
            jobs._run(folder, 'p', 'j', 0, 'u', {}, {}, edited, [], 'lower the music', None, None, job)
        args = publish.call_args.args
        self.assertIsNone(args[5])  # no new version attached
        self.assertIn('usage limit reached', args[7])
        self.assertIn('last working edit', args[7])
        self.assertEqual(job['status'], 'failed')
        self.assertNotIn(str(folder), jobs.RUNNING)

    def test_a_job_left_running_by_a_restart_is_reported(self):
        with TemporaryDirectory() as folder:
            (Path(folder)/'job.json').write_text(json.dumps({'status': 'running', 'message': ''}))
            self.assertEqual(jobs.job_status(folder)['status'], 'failed')
