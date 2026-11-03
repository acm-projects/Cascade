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
import subprocess

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
    from .context import scene_hints, footage_frames
    hints=scene_hints(jid,clip) if info.get('has_video') else {}
    from .reel import is_reel_request,hook_candidates
    info={**info,**hints,'clip_title':clip.get('title','')}
    if is_reel_request(body.message) and not info.get('has_video',True):
        raise HTTPException(422,'High-energy Reels require video footage. This audio-only clip supports transcript, audio and trim edits.')
    # Fan-edit style requests are routed deterministically: free, no model quota, no guessing.
    from .style_requests import parse_request, proposal_for
    style_request=parse_request(body.message) if info.get('has_video',True) and not body.research_id and not body.style_id else None
    from .style_requests import wants_director
    director_request=not style_request and info.get('has_video',True) and not body.research_id and (bool(body.style_id) or wants_director(body.message))
    wants_trends=not style_request and not director_request and ai.editor_provider() not in ai.LOCAL_ANALYSIS and bool(re.search(r'flashy|crazy|tiktok|trend[- ]informed',body.message,re.I) and re.search(r'make|edit|apply|create',body.message,re.I))
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
    if style_request:
        proposal=proposal_for(style_request)
        if style_request['type']=='preset':
            from .beats import analyze
            from .storage import media
            try:
                with media(jid,clip) as source: info['style_beats']=analyze(source)['beats']
            except (OSError,subprocess.SubprocessError,HTTPException,ValueError,KeyError):
                info['style_beats']=[]
    if director_request:
        # AI Director: watches the clip, studies real reference edits, picks the edit (free tiers/local only).
        from .director import chat_proposal
        proposal,research_report=chat_proposal(jid,clip,body,info,hints,request.state.user_id)
    assets=audio_store.library()
    if ai.editor_provider() in ai.LOCAL_ANALYSIS and proposal is None:
        from .beats import analyze
        measured_assets=[]
        for asset in assets:
            if asset['kind']=='music':
                try:
                    measured=analyze(audio_store.media(asset['id']))
                    asset={**asset,'measured_bpm':measured['bpm'],'beat_confidence':measured['confidence']}
                except (OSError, subprocess.SubprocessError):
                    asset={**asset,'measured_bpm':None,'beat_confidence':0}
            measured_assets.append(asset)
        assets=measured_assets
    frames = footage_frames(jid,clip,body.state,info,hints) if ai.editor_provider() in ai.LOCAL_ANALYSIS and proposal is None else []
    # Rich sequence editing uses the installed open-source compositor. Shared
    # non-editor providers and ordinary manual-edit chat tools remain unchanged.
    if ai.editor_provider() in ai.LOCAL_ANALYSIS and proposal is None:
        from .sequence_ai import direct_revision, edit as sequence_edit
        occ=ai.editor_provider()=='openchatcut'
        montage=r'sequence|montage|pacing|transition|ramp|shot|cut.*beat'+(r'|zoom|shake|slow.?mo|grade|look|cinematic|title|hook|faster|slower|energy|music' if occ else '')
        new_sequence=occ and info.get('has_video',True) and re.search(r'reel|tiktok|shorts?\b|montage|hype|high.?energy|beat|cinematic|trailer|edit (this|it)|make (this|it)',body.message,re.I)
        if is_reel_request(body.message) or new_sequence or (body.state.fablecut and (
            direct_revision(body.state,body.message) is not None or re.search(montage,body.message,re.I))):
            return sequence_edit(body.state,body.message,body.chat,info,hints,frames,audio_store)
    proposal = proposal or ai.request_edit({'visual_frames': frames,'broll_results': results, 'audio_assets': assets,
        'selected_broll_segment':body.selected_segment, 'media_kind': info.get('media_kind', 'video'),
        'style_request': 'high-energy-v1' if is_reel_request(body.message) else None,
        'hook_candidates':hook_candidates(info['cues'],body.state.start,body.state.end),
        'visual_timing_hints': hints, 'clip': public_clip(clip), 'duration': info['duration'], 'state': body.state.model_dump(),
        'transcript': info['cues'][:300], 'history': [m.model_dump() for m in body.chat[-20:]], 'request': body.message})
    if not style_request and not director_request and ai.editor_provider() not in ai.LOCAL_ANALYSIS and is_reel_request(body.message) and not any(a.type=='high_energy_reel' for a in proposal.actions):
        from .models import Action,Proposal
        query=next((a.query for a in proposal.actions if a.type in ('broll_auto','broll_search') and a.query),None)
        proposal=proposal.model_copy(update={'actions':[Action(type='high_energy_reel',query=query)]})
    info['editor_moments'] = [{**observation.model_dump(),'at':frames[observation.frame_index]['at']} for observation in proposal.observations if observation.frame_index<len(frames) and body.state.start <= frames[observation.frame_index]['at'] < body.state.end]
    state, reports, search_result, unsupported = execute(body, proposal, info, stock, audio_store)
    reports=research_report+reports
    analysis = {
        'provider': ai.editor_provider(),
        'model': None,
        'planning_method': proposal.planning_method,
        'sampled_frames': [{'frame_index':i, 'source_seconds':frame['at']} for i,frame in enumerate(frames)],
        'observations': info['editor_moments'],
        'scene_boundaries': hints.get('scene_boundaries', []),
        'transcript_cues': len(info['cues']),
        'limitation': 'Sparse sampled frames and transcript context; not continuous video comprehension or word-level forced alignment.',
    }
    if ai.editor_provider() == 'openchatcut':
        from . import gemini_planner
        analysis.update(provider='Gemini API free tier', model=gemini_planner.last_model(), quota={k: gemini_planner.usage()[k] for k in ('used','limit','resets')})
    elif ai.editor_provider() in ('ollama','local'):
        from .local_ai import runtime
        analysis['model'] = runtime()[1]

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
    if any(r['status']=='applied' for r in reports):
        message=('Timeline updated; rendered preview/export must still complete.\n' if state!=body.state else 'No net timeline changes were needed.\n')+message
    if state.stylize and state.stylize!=body.state.stylize:
        cutout=sum(e.duration for e in state.stylize.events if e.kind in ('bg_swap','color_pop','shape_reveal','outline'))
        message+=f'\nSubject cutouts are computed on this Mac for free; the first preview may take about {max(10,round(cutout*4))}s, later previews reuse them.'
    if state.captions.animation=='karaoke': message+='\nWord highlighting uses estimated timing within transcript cues.'
    if info['burned_in']: message+='\nExisting burned-in captions remain; new caption controls affect additional text only.'
    return {'state':state.model_dump(),'analysis':analysis,'message':message[:4000],'report':reports,'unsupported':unsupported,
            'plan':proposal.model_dump(mode='json'),'resolved_plan':state.model_dump(mode='json'),'broll_search':search_result,
            'actions':[a.model_dump(exclude_none=True) for a in proposal.actions]}
