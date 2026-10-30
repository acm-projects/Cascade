"""Execute a bounded AI plan step-by-step; retain successful steps on failure."""
import re
import uuid
from fastapi import HTTPException
from .actions import apply_actions
from .models import Edit
from .advanced_models import AudioSegment
from .validation import validate_media_edit


def trim_authorized(message):
    if re.search(r"\b(?:do not|don't|never|no|without)\s+(?:any\s+)?(?:trim(?:ming)?|shorten(?:ing)?|cut(?:ting)?)\b|\b(?:keep|preserve).{0,20}\b(?:full|entire|duration|length)\b",message,re.I):
        return False
    return bool(re.search(r'\b(trim|shorten|remove (?:the )?(first|last)|keep (?:only )?(?:the )?first|cut (off|out|the first|the last))\b|\bmake (?:this |the )?clip \d+\s*seconds', message, re.I))


def at(action, state, cues):
    if action.anchor:
        anchor=re.sub(r'\W+', ' ', action.anchor).lower().strip()
        cue=next((c for c in cues if anchor and anchor in re.sub(r'\W+',' ',c['text']).lower()),None)
        if cue is None: raise HTTPException(422, 'Dialogue anchor was not found: '+action.anchor)
        return max(state.start,cue['start'])
    return (action.start if action.start is not None else state.start)+(state.start if action.time_basis=='preview' and action.start is not None else 0)


def execute(body, proposal, info, stock, audio_store):
    state=body.state.model_copy(deep=True); reports=[]; search_result=None
    ids=list(body.result_ids)
    def commit(candidate):
        validate_media_edit(candidate,info);stock.verify(candidate);audio_store.verify(candidate)
        return candidate
    actions=list(proposal.actions)
    # A legacy search-only response must not defeat an explicit insert request.
    auto=bool(re.search(r'\b(add|insert|include|overlay)\b',body.message,re.I) and re.search(r'b[ -]?roll|stock footage|cutaway',body.message,re.I))
    if auto and not any(a.type in ('broll_auto','broll_insert') for a in actions):
        actions=[a.model_copy(update={'type':'broll_auto','duration':a.duration or min(2,state.end-state.start)}) if a.type=='broll_search' else a for a in actions]
    for number, action in enumerate(actions):
        candidate=state.model_copy(deep=True)
        begin=None;length=None
        try:
            if action.type in ('trim_first','keep_first','reset_trim') and not trim_authorized(body.message):
                raise HTTPException(422,'Duration preserved: trimming was not requested. Short B-roll shots do not authorize shortening the clip.')
            if action.type=='high_energy_reel':
                from .reel import build_reel
                candidate,steps=build_reel(state,info,stock,audio_store,action,body.message)
                state=commit(candidate)
                reports.extend(steps)
                continue
            if action.type=='speed_ramp':
                if not action.speed: raise HTTPException(422,'Speed-ramp timing and rates are required.')
                candidate.speed.append(action.speed.model_copy(deep=True))
                begin=action.speed.start;length=action.speed.end-action.speed.start
            elif action.type=='cut_accent':
                if not action.accent: raise HTTPException(422,'Cut-transition timing is required.')
                candidate.accents.append(action.accent.model_copy(deep=True))
                begin=action.accent.start;length=action.accent.duration
            elif action.type=='broll_search':
                search_result=stock.search(action.query or '')
                ids=list(dict.fromkeys([*ids,*[a['id'] for a in search_result['results']]]))
                reports.append({'step':number+1,'action':action.type,'status':'searched','message':f"Found {len(search_result['results'])} candidates; no insertion claimed."})
                continue
            if action.type in ('speed_ramp','cut_accent'):
                pass
            elif action.type=='broll_auto':
                if not re.search(r'\b(add|insert|use|select|choose|apply|include|overlay)\b',body.message,re.I):
                    raise HTTPException(422,'Automatic insertion requires a request to add/use/select footage.')
                begin=at(action,state,info['cues']);length=action.duration or min(2,state.end-begin)
                if begin+length>state.end+.001: raise HTTPException(422,'Requested B-roll extends beyond the current trim.')
                if not action.query: raise HTTPException(422,'A relevant B-roll search query is required.')
                search_result=stock.search(action.query)
                candidates=[a for a in search_result['results'] if a['duration']>=(action.offset or 0)+length]
                asset=None
                for entry in candidates[:5]:
                    try: stock.media(entry['id']);asset=entry;break
                    except (HTTPException,OSError): continue
                if not asset: raise HTTPException(409,'No usable stock result is available for this shot. Check Pexels configuration or try a different query.')
                from backend.broll import Asset, Segment
                candidate.broll.append(Segment(id=uuid.uuid4().hex,asset=Asset(**asset),start=begin,duration=length,offset=action.offset or 0,mode=action.mode or 'fill'))
            elif action.type in ('audio_add','audio_update','audio_remove'):
                if action.type=='audio_remove':
                    before=len(candidate.audio)
                    candidate.audio=[s for s in candidate.audio if s.id!=action.segment_id]
                    if before==len(candidate.audio): raise HTTPException(422,'Identify an existing audio segment to remove.')
                elif action.type=='audio_update':
                    if action.audio is None or not any(s.id==action.audio.id for s in candidate.audio): raise HTTPException(422,'Identify an existing audio segment to update.')
                    candidate.audio=[action.audio.model_copy(deep=True) if s.id==action.audio.id else s for s in candidate.audio]
                    begin=action.audio.start;length=action.audio.duration
                else:
                    if action.audio:
                        segment=action.audio.model_copy(deep=True)
                    else:
                        track=action.track or 'music';assets=[a for a in audio_store.library() if a['kind']==track]
                        if action.asset_id:
                            assets=[a for a in assets if a['id']==action.asset_id]
                        else:
                            words=set(re.findall(r'\w+',action.query or body.message.lower()))
                            def score(a): return len(words & set(' '.join([a['name'],*a['tags']]).lower().split()))
                            assets=sorted(assets,key=score,reverse=True)
                            if action.query and not any(score(a) for a in assets):
                                raise HTTPException(409,'No matching permitted audio track is available. Upload your own music/SFX in the Music tab, or select an available track by name.')
                        if not assets: raise HTTPException(409,'No matching audio asset is available. Upload one in the Music tab.')
                        chosen=assets[0];begin=at(action,state,info['cues'])
                        length=action.duration or (state.end-begin if track=='music' else min(chosen['duration'],state.end-begin))
                        segment=AudioSegment(id=uuid.uuid4().hex,asset_id=chosen['id'],track=track,start=begin,duration=length,offset=action.offset or 0,volume=action.volume if action.volume is not None else (.18 if track=='music' else .55),fade_in=.3 if track=='music' else .01,fade_out=.5 if track=='music' else .05,duck=track=='music',loop=track=='music')
                    candidate.audio.append(segment);begin=segment.start;length=segment.duration
            elif action.type=='motion':
                if not action.motion: raise HTTPException(422,'Zoom/shake settings are required.')
                motion=action.motion.model_copy(deep=True)
                if action.anchor: motion.start=at(action,state,info['cues'])
                candidate.motion.append(motion);begin=motion.start;length=motion.duration
            elif action.type=='text_overlay':
                if not action.overlay: raise HTTPException(422,'Text overlay settings are required.')
                overlay=action.overlay.model_copy(deep=True)
                if action.anchor: overlay.start=at(action,state,info['cues'])
                candidate.text_overlays.append(overlay);begin=overlay.start;length=overlay.duration
            elif action.type=='color_adjust':
                if not action.effects: raise HTTPException(422,'Color settings are required.')
                candidate.effects=action.effects.model_copy(deep=True)
            elif action.type=='transition':
                if not action.transition: raise HTTPException(422,'Fade settings are required.')
                candidate.transition=action.transition.model_copy(deep=True)
            elif action.type=='caption_animation':
                if not action.animation: raise HTTPException(422,'Specify pop, karaoke or none.')
                candidate.captions.animation=action.animation;candidate.captions.enabled=True
                if action.color: candidate.captions.highlight=action.color
            elif action.type=='dialogue_volume':
                if action.volume is None: raise HTTPException(422,'Dialogue volume is required.')
                candidate.dialogue_volume=action.volume
            else:
                candidate=apply_actions(state,[action],info['duration'],len(info['cues']),stock,ids,body.selected_segment)
            state=commit(candidate)
            message=action.type.replace('_',' ')
            if begin is not None: message+=f' at {begin:.2f}–{begin+(length or 0):.2f}s'
            if action.type in ('speed_ramp','cut_accent'):
                pass
            elif action.type=='broll_auto': message+='; selected and inserted '+asset['id']+'; original dialogue preserved'
            if action.type=='audio_add': message+='; '+audio_store.entry(segment.asset_id)['name']
            reports.append({'step':number+1,'action':action.type,'status':'applied','start':begin,'duration':length,'message':message})
        except (HTTPException,ValueError,OSError) as exc:
            reports.append({'step':number+1,'action':action.type,'status':'failed','http_status':exc.status_code if isinstance(exc,HTTPException) else 422,'message':str(exc.detail if isinstance(exc,HTTPException) else 'Invalid/unavailable asset or timeline settings; this step was not applied.')})
    unsupported=list(proposal.unsupported)
    for pattern,label in [(r'freeze[ -]?frame','Freeze-frames'),(r'\breverse\b','Reverse playback')]:
        if re.search(pattern,body.message,re.I): unsupported.append(label+' are not implemented; clip timing and dialogue are unchanged.')
    if re.search(r'speed[ -]?(ramp|change)|slow[ -]?motion|\b(?:2x|double speed)\b',body.message,re.I) and not state.speed:
        unsupported.append('Speed changes were not applied: only transcript-confirmed pauses can be retimed safely.')
    return state,reports,search_result,list(dict.fromkeys(unsupported))
