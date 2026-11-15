"""AI Editor chat turns for storyboard-first editing (see storyboard.py)."""
import os
import re

from fastapi import HTTPException

from . import storyboard
from .models import Edit
from .validation import validate_media_edit

REEL = re.compile(r'\b(reels?|tiktok|shorts|montage|hype|high[- ]energy)\b', re.I)


def wants(body, info, user, pid, jid, index):
    """The pending storyboard (or True for a new one) when this turn belongs to the storyboard flow, else None."""
    if body.research_id or not info.get('has_video', True): return None
    board = storyboard.pending(pid, jid, index, user)
    if board: return board
    from .style_profile import chat_links
    from .style_requests import wants_director
    # With no provider chosen, Reel requests are storyboards too (their other path needs Gemini).
    reel = not os.getenv('CASCADE_EDITOR_PROVIDER', '').strip() and not body.state.fablecut and REEL.search(body.message)
    return True if wants_director(body.message) or chat_links(body.message) or reel else None


def _reply(state, message, report, board=None, planner=''):
    return {'state': state.model_dump(), 'message': message[:4000], 'report': report, 'unsupported': [], 'actions': [],
            'analysis': {'provider': planner or 'storyboard', 'model': None, 'planning_method': 'storyboard', 'sampled_frames': [],
                         'observations': [], 'transcript_cues': 0, 'limitation': 'Planned from sampled frames and the transcript.'},
            'storyboard': board.model_dump() if board else None}


def turn(pid, jid, index, user, clip, body, info, stock, audio_store, pending):
    from .storage import media
    from .style_profile import for_chat
    if pending is not True and storyboard.CANCEL.search(body.message):
        storyboard.clear(pid, jid, index, user)
        return _reply(body.state, 'Storyboard discarded. Nothing was changed.', [])
    if pending is not True and storyboard.RENDER.search(body.message):
        return _render(pid, jid, index, user, body, info, stock, audio_store, pending)
    with media(jid, clip) as source:
        if pending is True:
            profile, learned = for_chat(user, body.message)
            board = storyboard.create(pid, jid, index, user, source, body.state, info, body.message, profile)
        else:
            learned = ''
            board = storyboard.revise(pid, jid, index, user, source, body.state, info, pending, body.message)
    report = [{'action': 'storyboard', 'status': 'info', 'message': line} for line in (learned, f'Planned by {board.planner}.') if line]
    return _reply(body.state, storyboard.describe(board), report, board, board.planner)


def _render(pid, jid, index, user, body, info, stock, audio_store, board):
    from .storyboard_apply import apply
    from .style_profile import for_chat
    profile, _ = for_chat(user, board.request)
    candidate, notes = apply(body.state.model_copy(deep=True), board, info, stock, audio_store, profile)

    def commit(edit):
        edit = Edit.model_validate(edit.model_dump())
        validate_media_edit(edit, info); stock.verify(edit); audio_store.verify(edit)
        return edit
    try:
        state = commit(candidate)
    except (HTTPException, ValueError):
        candidate.broll, candidate.timeline = list(body.state.broll), list(body.state.timeline)
        state = commit(candidate)
        notes.append('some B-roll/cuts did not fit and were skipped')
    storyboard.clear(pid, jid, index, user)
    message = 'Timeline updated; rendered preview/export must still complete.\nAPPLIED: '+'; '.join(notes)
    if state.stylize and state.stylize.events:
        message += '\nThe preview renders on this Mac for free; the first one can take a minute.'
    return _reply(state, message, [{'action': 'storyboard', 'status': 'applied', 'message': '; '.join(notes)}])
