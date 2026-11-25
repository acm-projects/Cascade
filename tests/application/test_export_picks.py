"""The "Edited" mark Export's clip picker shows (backend/editor/drafts.py `edited`)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.editor import drafts
from backend.editor.models import Captions, Draft, Edit


class EditedTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'draft.json'
        patcher = patch.object(drafts, 'draft_path', return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)
        self.clip = {'job_id': 'a'*32, 'clip_index': 0, 'start': 10.0, 'end': 40.0}

    def save(self, state, chat=()):
        self.path.write_text(json.dumps(Draft(state=state, chat=list(chat)).model_dump()))

    def edited(self):
        return drafts.edited('p', self.clip, 'user')

    def test_no_saved_draft_is_not_edited(self):
        self.assertFalse(self.edited())

    def test_the_untouched_starting_edit_is_not_edited(self):
        self.save(Edit(start=0, end=30, captions=Captions(enabled=False)))
        self.assertFalse(self.edited())

    def test_a_trim_captions_or_chat_counts_as_edited(self):
        self.save(Edit(start=0, end=20, captions=Captions(enabled=False)))
        self.assertTrue(self.edited())
        self.save(Edit(start=0, end=30, captions=Captions(enabled=True)))
        self.assertTrue(self.edited())
        self.save(Edit(start=0, end=30, captions=Captions(enabled=False)), chat=[{'role': 'user', 'text': 'make it pop'}])
        self.assertTrue(self.edited())

    def test_an_unreadable_draft_is_not_edited(self):
        self.path.write_text('{"state": "broken"}')
        self.assertFalse(self.edited())


if __name__ == '__main__':
    unittest.main()
