"""The finished-edit workflow, offline: no AI, no render. Real renders are checked by hand in the app."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from backend.editor.ai_edit import jobs
from backend.editor.models import AIEditRef, Edit


def body(state, message):
    return SimpleNamespace(state=state, chat=[], message=message, research_id=None)


class OldDrafts(unittest.TestCase):
    def test_a_draft_saved_with_an_old_beat_plan_still_opens(self):
        state = Edit.model_validate({'start': 0, 'end': 10, 'ai_plan': {'version': 'v001', 'plan_id': '0'*32}})
        self.assertNotIn('ai_plan', state.model_dump())


class Failure(unittest.TestCase):
    def test_a_failed_revision_keeps_the_last_edit_and_says_why(self):
        edited = Edit(start=0, end=10, ai_edit=AIEditRef(version='v001', duration=9))
        with TemporaryDirectory() as folder, patch.object(jobs, '_publish') as publish, patch('backend.editor.storage.media', side_effect=HTTPException(429, 'usage limit reached')):
            folder = Path(folder)
            job = {'id': 'x', 'status': 'queued', 'progress': 0, 'stage': '', 'version': None, 'message': '', 'finished': None}
            with jobs.GUARD: jobs.RUNNING[str(folder)] = object()
            jobs._run_cinema(folder, 'p', 'j', 0, 'u', {}, {}, edited, [], 'lower the music', None, job)
        args = publish.call_args.args
        self.assertIsNone(args[5])  # no new version attached
        self.assertIn('usage limit reached', args[7])
        self.assertIn('last working edit', args[7])
        self.assertEqual(job['status'], 'failed')
        self.assertNotIn(str(folder), jobs.RUNNING)

    def test_cinema_chat_flow_without_any_ai_model(self):
        """The exact chat path with every planner off: a first edit is still made and saved as a project; a simple
        follow-up changes that project and renders again; a creative follow-up is refused clearly and the draft is kept."""
        from contextlib import contextmanager
        from backend.editor.ai_edit.cinema import engine, project
        words = [{'i': i, 'w': w, 's': i*.4, 'e': i*.4+.3} for i, w in enumerate('Why save the forest? Because the jaguars live there. He walked right by me.'.split())]
        prep = {'words': words, 'duration': 6, 'cuts': [], 'sheets': []}
        rendered = []
        def fake_make(source, words, plan, out, *a, **k):
            Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b'video'); rendered.append(plan)
            return {'seconds': 6.0, 'size': '1920x1080', 'removed_fillers': 0, 'removed_interjections': 0, 'broll': 0, 'moments': 0, 'lufs': -14.0, 'timeline': {'shots': []}}
        @contextmanager
        def media(*a):
            yield Path('clip.mp4')
        env = {'CASCADE_EDIT_PLANNER': 'rules'}
        with TemporaryDirectory() as folder, patch.object(jobs, '_publish') as publish, patch('backend.editor.storage.media', media), \
                patch.object(jobs.preparation, 'prepare', return_value=prep), patch.object(jobs.preparation, 'probe', return_value={'duration': 6.0}), \
                patch.object(engine, 'make', fake_make), patch.dict('os.environ', env):
            folder = Path(folder)
            def run(state, message):
                job = {'id': 'x', 'status': 'queued', 'progress': 0, 'stage': '', 'version': None, 'message': '', 'finished': None}
                with jobs.GUARD: jobs.RUNNING[str(folder)] = object()
                jobs._run_cinema(folder, 'p', 'j', 0, 'u', {}, {}, state, [], message, None, job)
                return job
            first = run(Edit(start=0, end=6), 'Edit this video')
            self.assertEqual((first['status'], first['version']), ('done', 'v001'))
            self.assertIn('planned by rules', first['message'])
            self.assertEqual(project.read(folder/'v001')['planner'], 'rules')

            edited = Edit(start=0, end=6, ai_edit=AIEditRef(version='v001', duration=6))
            second = run(edited, 'make it a reel and turn the music down')
            self.assertEqual((second['status'], second['version']), ('done', 'v002'))
            self.assertEqual((rendered[-1].settings.ratio, rendered[-1].settings.music_db), ('9:16', -5))
            self.assertEqual(rendered[-1].story, rendered[0].story)          # the same cut, modified, not regenerated

            third = run(edited, 'open on a more emotional line')
            self.assertEqual(third['status'], 'failed')
            self.assertIn('needs the AI planner', third['message'])
            self.assertIsNone(publish.call_args.args[5])                      # no new version; the draft is untouched
            self.assertFalse((folder/'v003').exists())
            self.assertEqual(len(rendered), 2)

    def test_a_job_left_running_by_a_restart_is_reported(self):
        with TemporaryDirectory() as folder:
            (Path(folder)/'job.json').write_text(json.dumps({'status': 'running', 'message': ''}))
            self.assertEqual(jobs.job_status(folder)['status'], 'failed')
