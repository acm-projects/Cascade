"""Editor chat; extracted without changing media behavior."""
from fastapi import HTTPException, Request
from .models import ChatInput
from .validation import details, validate_edit
from .actions import apply_actions
from .storage import selected, stock_store
from .reframe import begin_analysis
from . import ai
from .runtime import public_clip

def chat(pid: str, jid: str, index: int, body: ChatInput, request: Request):
    clip = selected(pid, jid, index, request.state.user_id)
    info = details(jid, clip)
    validate_edit(body.state, info['duration'])
    stock=stock_store(pid,jid,index,request.state.user_id)
    stock.verify(body.state)
    results=[stock.entry(asset_id)['asset'] for asset_id in body.result_ids]
    if body.selected_segment and not any(s.id==body.selected_segment for s in body.state.broll):
        raise HTTPException(422, 'Selected B-roll segment does not exist.')
    proposal = ai.request_edit({'broll_results': results, 'selected_broll_segment':body.selected_segment, 'clip': public_clip(clip), 'duration': info['duration'], 'state': body.state.model_dump(),
                             'transcript': info['cues'][:300], 'history': [m.model_dump() for m in body.chat[-20:]], 'request': body.message})
    state = apply_actions(body.state, proposal.actions, info['duration'], len(info['cues']), stock, body.result_ids, body.selected_segment)
    if state.reframe.enabled and not state.reframe.analysis_id:
        state.reframe.analysis_id=begin_analysis(pid,jid,index,request.state.user_id,state.reframe.selection,state.reframe.focus)['analysis_id']
    searches=[a for a in proposal.actions if a.type=='broll_search']
    search_result=stock.search(searches[-1].query) if searches else None
    message = proposal.message
    if proposal.actions:
        changes = []
        if (state.start, state.end) != (body.state.start, body.state.end):
            changes.append(f'Trim set to {state.start:.2f}–{state.end:.2f} seconds of this generated clip.')
        for field, label in [('enabled', 'Captions'), ('color', 'Caption color'), ('bold', 'Bold captions'), ('position', 'Caption position')]:
            if getattr(state.captions, field) != getattr(body.state.captions, field):
                value = getattr(state.captions, field)
                changes.append(f"{label}: {('on' if value else 'off') if isinstance(value, bool) else value}.")
        if state.captions != body.state.captions and not changes:
            changes.append('Caption style updated.')
        if state.reframe!=body.state.reframe:
            changes.append('Requested '+state.reframe.focus+' reframing. The editor will wait for real tracking analysis before applying it.' if state.reframe.enabled else 'Follow Speaker disabled.')
        if state.texts!=body.state.texts:
            changes.append('Caption text updated on the selected timed segment.')
        if state.broll!=body.state.broll:
            changes.append(f'B-roll updated: {len(state.broll)} segment(s). Speaker audio preserved.')
        if search_result is not None:
            changes.append(f"Found {len(search_result['results'])} stock result(s). Select footage in the B-roll tab; nothing was inserted.")
        message = ' '.join(changes) or 'The clip already has those settings.'
        if info['burned_in'] and state.captions != body.state.captions:
            message += ' These controls affect additional captions only; burned-in text remains.'
    return {'state': state.model_dump(), 'message': message, 'broll_search':search_result, 'actions': [a.model_dump(exclude_none=True) for a in proposal.actions]}
