"""Editor chat; extracted without changing media behavior."""
from fastapi import HTTPException, Request
from .models import ChatInput
from .validation import details, validate_edit, validate_media_edit
from .actions import apply_actions
from .storage import selected, stock_store
from .reframe import begin_analysis
from . import ai
from .runtime import public_clip
import re

def chat(pid: str, jid: str, index: int, body: ChatInput, request: Request):
    clip = selected(pid, jid, index, request.state.user_id)
    info = details(jid, clip)
    validate_media_edit(body.state, info)
    stock=stock_store(pid,jid,index,request.state.user_id)
    stock.verify(body.state)
    results=[stock.entry(asset_id)['asset'] for asset_id in body.result_ids]
    if body.selected_segment and not any(s.id==body.selected_segment for s in body.state.broll):
        raise HTTPException(422, 'Selected B-roll segment does not exist.')
    from .audio_assets import store
    from .execution import execute
    audio_store = store(pid,jid,index,request.state.user_id)
    audio_store.verify(body.state)
    from .context import scene_hints
    hints=scene_hints(jid,clip) if info.get('has_video') else {}
    from .reel import is_reel_request,hook_candidates
    info={**info,**hints,'clip_title':clip.get('title','')}
    wants_trends=bool(re.search(r'flashy|crazy|tiktok|trend[- ]informed',body.message,re.I) and re.search(r'make|edit|apply|create',body.message,re.I))
    research_report=[]
    if body.research_id or wants_trends:
        from . import trends
        if body.research_id:
            return trends.apply_result(pid,jid,index,trends.ApplyInput(state=body.state,research_id=body.research_id,suggestion=body.suggestion,suggestions=body.suggestions,intensity='flashy' if re.search(r'flashy|crazy',body.message,re.I) else 'high-energy'),request)
        record=trends.research_for_chat(pid,jid,index,request.state.user_id,body.state,goal=body.message)
        if record['status']=='done':
            result=trends.apply_result(pid,jid,index,trends.ApplyInput(state=body.state,research_id=record['id'],intensity='flashy' if re.search(r'flashy|crazy',body.message,re.I) else 'high-energy'),request)
            result['message']='YouTube research informed this supported High-Energy style. This is not verified TikTok trend data.\n'+result['message']
            unsupported=[name for pattern,name in [(r'freeze','freeze-frames'),(r'reverse','reverse playback'),(r'mask|rotoscop','subject masks'),(r'glow|3d','glow/3D compositing'),(r'optical.flow','optical-flow ramps')] if re.search(pattern,body.message,re.I)]
            result['unsupported']=unsupported
            if unsupported:result['message']+='\nNot applied: '+', '.join(unsupported)+'.'
            return result
        research_report=[{'action':'research','status':'failed','message':record.get('message','YouTube research unavailable.')}]
        research_report.append({'action':'fallback','status':'info','message':'FALLBACK MODE — any applied edits below are not trend-grounded. No current YouTube reference findings were used.'})
        # Missing external research must not block the working local style.
        from .models import Action,Proposal
        proposal=Proposal(message='Supported local style; external research unavailable.',actions=[Action(type='high_energy_reel')])
    else:
        proposal=None
    proposal = proposal or ai.request_edit({'broll_results': results, 'audio_assets': audio_store.library(),
        'selected_broll_segment':body.selected_segment, 'media_kind': info.get('media_kind', 'video'),
        'style_request': 'high-energy-v1' if is_reel_request(body.message) else None,
        'hook_candidates':hook_candidates(info['cues'],body.state.start,body.state.end),
        'visual_timing_hints': hints, 'clip': public_clip(clip), 'duration': info['duration'], 'state': body.state.model_dump(),
        'transcript': info['cues'][:300], 'history': [m.model_dump() for m in body.chat[-20:]], 'request': body.message})
    if is_reel_request(body.message) and not any(a.type=='high_energy_reel' for a in proposal.actions):
        from .models import Action,Proposal
        query=next((a.query for a in proposal.actions if a.type in ('broll_auto','broll_search') and a.query),None)
        proposal=Proposal(message='Coordinated style plan',actions=[Action(type='high_energy_reel',query=query)])
    state, reports, search_result, unsupported = execute(body, proposal, info, stock, audio_store)
    reports=research_report+reports
    if state.reframe.enabled and not state.reframe.analysis_id:
        try:
            state.reframe.analysis_id=begin_analysis(pid,jid,index,request.state.user_id,state.reframe.selection,state.reframe.focus)['analysis_id']
            reports.append({'action':'reframe','status':'processing','message':'Tracking queued; preview/render waits for completed analysis.'})
        except HTTPException as exc:
            state.reframe=body.state.reframe.model_copy(deep=True)
            state.composition.mode=body.state.composition.mode
            reports.append({'action':'reframe','status':'failed','message':str(exc.detail)})
    if reports and all(r['status']=='failed' for r in reports):
        raise HTTPException(reports[0].get('http_status',422), '\n'.join(r['message'] for r in reports))
    message='\n'.join(f"{r['status'].upper()}: {r['message']}" for r in reports)
    if unsupported: message+='\nNot applied: '+'; '.join(unsupported)
    if not reports and not unsupported: message=proposal.message
    if state.captions.animation=='karaoke': message+='\nWord highlighting uses estimated timing within transcript cues.'
    if info['burned_in']: message+='\nExisting burned-in captions remain; new caption controls affect additional text only.'
    return {'state':state.model_dump(),'message':message[:4000],'report':reports,'unsupported':unsupported,
            'plan':proposal.model_dump(mode='json'),'resolved_plan':state.model_dump(mode='json'),'broll_search':search_result,
            'actions':[a.model_dump(exclude_none=True) for a in proposal.actions]}
