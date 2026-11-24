"""Short notes for the person editing, collected while a render runs.

Some parts of an edit can be left out without failing the whole render (a motion card when HyperFrames is
missing or fails). Instead of only writing a server log line, the code that leaves something out calls `add`,
and whoever started the render wraps it in `collect()` and shows the notes (the Editor preview's status line).
Outside `collect()`, `add` does nothing.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_notes = ContextVar('cascade_editor_notes', default=None)


def add(text):
    notes = _notes.get()
    if notes is not None and text not in notes:
        notes.append(text)


@contextmanager
def collect():
    """Yield the list of notes added inside; they are also passed on to an outer collect()."""
    outer, notes = _notes.get(), []
    token = _notes.set(notes)
    try:
        yield notes
    finally:
        _notes.reset(token)
        for text in notes:
            if outer is not None and text not in outer:
                outer.append(text)
