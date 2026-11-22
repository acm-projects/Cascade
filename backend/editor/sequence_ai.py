"""Shot candidates and direct (no-AI) revisions for a FableCut sequence."""
import re

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class PlannedShot(BaseModel):
    model_config=ConfigDict(extra='forbid')
    candidate: int=Field(ge=0,le=49)
    beats: int=Field(ge=1,le=8)
    ramp: bool
    zoom: float=Field(ge=1,le=1.25)
    shake: float=Field(ge=0,le=5)
    transition: Literal['none','fade','whip','blur','zoom']
    reason: str=Field(max_length=200)


class SequencePlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    rationale: str=Field(max_length=1000)
    shots: list[PlannedShot]=Field(min_length=3,max_length=8)
    music_asset_id: str | None=None
    grade: float=Field(ge=0,le=.15)
    caption_animation: Literal['none','pop','karaoke']
    sound_design: bool
    unsupported: list[str]=Field(default_factory=list,max_length=12)


def candidates(state,info,hints):
    # Whole cues are indivisible. Remaining footage is split at detected scene cuts.
    from .retiming import phrases
    speech_windows=phrases(info['cues'])
    boundaries={state.start,state.end}
    boundaries.update(t for t in hints.get('scene_boundaries',[]) if state.start<t<state.end)
    boundaries.update(t for c in speech_windows for t in (c['start'],c['end']) if state.start<t<state.end)
    boundaries={t for t in boundaries if not any(c['start']+.025<t<c['end']-.025 for c in speech_windows)}
    points=sorted(boundaries);rows=[]
    for a,b in zip(points,points[1:]):
        if b-a<.25:continue
        if state.timeline and not any(s.start<=a+.025 and s.end>=b-.025 for s in state.timeline):continue
        rows.append({'id':len(rows),'start':round(a,3),'end':round(b,3),
                     'speech':' '.join(c['text'] for c in info['cues'] if c['start']<b and c['end']>a)})
    # Put the available spoken hook beside the visual candidates, rather than
    # making a small model confuse frame indices with a late transcript row.
    spoken=[r for r in rows if r['speech']]
    visual=[r for r in rows if not r['speech']]
    ordered=spoken[:1]+visual+spoken[1:]
    return [{**row,'id':index} for index,row in enumerate(ordered[:50])]


def direct_revision(state,message):
    if not state.fablecut:return None
    text=message.lower().strip().rstrip('.!');result=state.model_copy(deep=True);seq=result.fablecut
    if re.fullmatch(r'(please )?(less shake|reduce (the )?shake|no shake|remove shake)',text):
        factor=0 if 'no shake' in text or 'remove' in text else .5
        for shot in seq.shots:shot.shake*=factor
        return result,'Updated existing sequence shakes; no extra effects added.'
    if re.fullmatch(r'(please )?(less zoom|reduce (the )?zooms?)',text):
        for shot in seq.shots:shot.zoom=1+(shot.zoom-1)*.5
        return result,'Reduced existing punch-ins.'
    match=re.fullmatch(r'move (?:that|the last|last) zoom earlier(?: by (\d+(?:\.\d+)?) seconds?)?',text)
    if match:
        shot=next((s for s in reversed(seq.shots) if s.zoom>1),None)
        if not shot:raise HTTPException(422,'There is no sequence punch-in to move.')
        before=shot.zoom_at;shot.zoom_at=max(0,shot.zoom_at-float(match[1] or .1))
        return result,f'Moved the last punch-in peak from {before:.2f}s to {shot.zoom_at:.2f}s within its existing shot; no duplicate zoom added.'
    if re.fullmatch(r'(please )?(remove|no|disable) (the )?music',text):
        seq.music_asset_id=None
        return result,'Removed the AI sequence music bed. Existing manual audio remains.'
    if re.fullmatch(r'(please )?(remove|disable|clear) (the )?(ai )?sequence',text):
        result.fablecut=None
        return result,'Removed the AI sequence; your underlying manual edit is preserved.'
    match=re.fullmatch(r'(?:remove|delete) (?:shot|cut) (\d+)',text)
    if match:
        index=int(match[1])-1
        if not 0<=index<len(seq.shots) or len(seq.shots)<2:
            raise HTTPException(422,'Choose an existing shot number and retain at least one shot.')
        seq.shots.pop(index)
        return result,f'Removed sequence shot {index+1}; remaining shots close the gap.'
    return None
