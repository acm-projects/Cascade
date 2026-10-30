"""Editor actions; extracted without changing media behavior."""
import uuid
from fastapi import HTTPException
from backend import broll as stocklib
from .validation import validate_edit

def apply_actions(state, actions, duration, cue_count=0, stock=None, result_ids=(), selected_segment=None):
    result = state.model_copy(deep=True)
    if any(a.type=='broll_search' for a in actions) and any(a.type.startswith('broll_') and a.type!='broll_search' for a in actions):
        raise HTTPException(422, 'Search first, then select an identifiable result to insert.')
    for action in actions:
        if action.type == 'reframe_focus':
            if action.focus is None: raise HTTPException(422, 'Specify a framing focus.')
            result.reframe.enabled=action.focus!='off'
            if action.focus=='off':result.composition.mode='fit'
            if action.focus!='off':
                result.reframe.focus=action.focus
                result.reframe.selection=None
                result.reframe.analysis_id=None
                result.composition.mode='fill'
            continue
        if action.type == 'broll_search':
            if not action.query:
                raise HTTPException(422, 'Specify what stock footage to search for.')
            continue
        if action.type.startswith('broll_'):
            if stock is None:
                raise HTTPException(422, 'B-roll context is unavailable.')
            if action.type=='broll_insert':
                if action.asset_id not in result_ids or action.start is None or action.duration is None:
                    raise HTTPException(422, 'Select a displayed stock result and specify its start and duration.')
                asset=stocklib.Asset(**stock.entry(action.asset_id)['asset'])
                stock.media(asset.id)  # Confirm footage is usable before committing the transaction.
                result.broll.append(stocklib.Segment(id=uuid.uuid4().hex, asset=asset,
                    start=action.start+(state.start if action.time_basis=='preview' else 0),
                    duration=action.duration, offset=action.offset or 0, mode=action.mode or 'fill'))
            else:
                segment_id=action.segment_id or selected_segment
                segment=next((s for s in result.broll if s.id==segment_id),None)
                if segment is None:
                    raise HTTPException(422, 'Select the B-roll segment to change, or identify it explicitly.')
                if action.type=='broll_remove':
                    result.broll.remove(segment)
                else:
                    if action.asset_id is not None:
                        if action.asset_id not in result_ids:
                            raise HTTPException(422, 'Choose a displayed stock result for replacement.')
                        segment.asset=stocklib.Asset(**stock.entry(action.asset_id)['asset'])
                        stock.media(segment.asset.id)
                    for field in ('start','duration','offset','mode'):
                        value=getattr(action,field)
                        if value is not None:
                            if field=='start' and action.time_basis=='preview': value+=state.start
                            setattr(segment,field,value)
            continue
        if action.type in ('trim_first', 'keep_first'):
            if action.seconds is None:
                raise HTTPException(422, 'The edit did not specify a duration.')
            if action.type == 'trim_first':
                result.start += action.seconds
            else:
                result.end = min(result.end, result.start + action.seconds)
        elif action.type == 'reset_trim':
            result.start, result.end = 0, duration
        elif action.type in ('captions_enabled', 'caption_bold'):
            if action.enabled is None:
                raise HTTPException(422, 'The edit did not specify on or off.')
            setattr(result.captions, 'enabled' if action.type == 'captions_enabled' else 'bold', action.enabled)
            if action.type=='caption_bold':
                result.captions.enabled=True
        elif action.type == 'caption_settings':
            if action.settings is None:
                raise HTTPException(422, 'Caption settings were not specified.')
            result.captions = action.settings.model_copy(deep=True)
        elif action.type == 'caption_color':
            if action.color is None:
                raise HTTPException(422, 'The edit did not specify a color.')
            result.captions.color = action.color
            result.captions.enabled = True
        elif action.type == 'caption_text':
            if action.cue_index is None or action.cue_index>=cue_count or action.text is None:
                raise HTTPException(422, 'The caption edit must identify an existing timed segment and text.')
            result.texts[str(action.cue_index)]=action.text
            result.captions.enabled=True
        elif action.type == 'caption_position':
            if action.position is None:
                raise HTTPException(422, 'The edit did not specify a position.')
            result.captions.position = action.position
            result.captions.enabled = True
    return validate_edit(result, duration)
