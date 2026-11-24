"""Tests that post to the Editor chat pick its path here instead of asking OpenAI (backend/editor/chat_router.py)."""
from unittest.mock import patch


def route(name):
    """A context manager: every chat message inside takes the `name` path."""
    return patch('backend.editor.chat_router.choose', return_value=name)


def use_route(test, name):
    """For a setUp: the whole test takes the `name` path."""
    patcher = route(name)
    patcher.start()
    test.addCleanup(patcher.stop)
