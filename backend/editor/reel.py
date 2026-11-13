"""One restrained, reproducible High-Energy Reel grammar, not an effect lottery."""
import math
import re
import uuid
from fastapi import HTTPException
from backend.broll import Segment,Asset
from .advanced_models import TimelineSpan,SpeedRamp,Motion,AudioSegment,Transition,CutAccent,ReelInfo
from .retiming import Clock,phrases
from .beats import analyze,loop_beats

def is_reel_request(text):return bool(re.search(r'high[ -]energy.{0,35}reel|reel.{0,35}high[ -]energy',text,re.I))

def hook_candidates(cues,start,end):
    options=[]
    for i,p in enumerate(phrases(cues)):
        if p['start']<start or p['end']>end or end-p['start']<min(10,(end-start)*.55):continue
        words=re.findall(r"[\w']+",p['text'].lower())
        score=2*('?' in p['text'])+sum(w in {'why','never','best','wrong','listen','mind','friend','teddy','wait','secret','stop','imagine'} for w in words)
        score+=min(1,len(words)/8)-max(0,len(words)-20)*.2
        options.append({'phrase_index':i,**p,'score':round(score,3)})
    return sorted(options,key=lambda p:(-p['score'],p['start']))[:8]

def build_reel(state,info,stock,audio_store,action,message):
    candidate=state.model_copy(deep=True);reports=[]
    previous=state.reel
    def retain_manual(items, owned):
        remaining=list(items)
        for item in owned:
            match=next((i for i,row in enumerate(remaining) if row==item),None)
            if match is not None:remaining.pop(match)
        return remaining
    manual_motion=retain_manual(state.motion,previous.generated_motion if previous else [])
    manual_accents=retain_manual(state.accents,previous.generated_accents if previous else [])
    manual_audio=[a for a in state.audio if not previous or a.id not in previous.generated_audio_ids]
    manual_broll=[b for b in state.broll if not previous or b.id not in previous.generated_broll_ids]
    manual_speed=retain_manual(state.speed,previous.generated_speed if previous else [])
    generated_audio=[];generated_motion=[];generated_accents=[];generated_broll=[];generated_speed=[]

    flashy=bool(re.search(r'flashy|crazy|punchy',message,re.I))
    budget=min(action.max_punch_ins or (6 if flashy else 3),max(0,30-len(manual_motion)))
    separation=1.25 if flashy else 2.5
    zoom_from,zoom_to=(1.06,1.38) if flashy else (1.04,1.24)
    if action.zoom_strength is not None:zoom_to=action.zoom_strength
    def report(action,status,message,**extra):reports.append({'action':action,'status':status,'message':message,**extra})
    if not info.get('has_video',True):raise HTTPException(422,'High-Energy Reel needs video footage.')
    if not info['cues']:raise HTTPException(409,'Transcript timestamps are required for a phrase-safe Reel. Transcribe the clip first.')
    windows=phrases(info['cues']);options=hook_candidates(info['cues'],state.start,state.end)
    explicit_keep=bool(re.search(r"do not trim|don't trim|no trimming|keep.{0,10}(full|entire)|preserve.{0,10}(duration|length)",message,re.I))
    choose_hook=bool(re.search(r'strong opening|hook|tighten|trim',message,re.I)) and not explicit_keep
    start=state.start;reason='Original opening preserved.'
    if choose_hook and options:
        hook=next((s['at'] for s in info.get('trend_suggestions',[]) if s['technique']=='hook'),None)
        preferred=min(options,key=lambda p:abs(p['start']-hook)) if hook is not None else options[0]
        chosen=next((p for p in options if p['phrase_index']==action.cue_index),preferred)
        start=max(state.start,chosen['start']-.06)
        if any(p['start']+.015<start<p['end']-.015 for p in windows):start=chosen['start']
        reason='Complete opening phrase: '+chosen['text'][:220]
    end=state.end
    # Tail trim only removes trailing silence, never a spoken ending.
    last=max((p['end'] for p in windows if p['end']<=state.end+.01),default=state.end)
    if choose_hook and state.end-last>.5:end=min(state.end,last+.18)
    existing_timing=bool(state.timeline)
    if existing_timing:
        start=state.start;end=state.end;reason='Existing kept-footage ranges preserved.'
    else:
        candidate.timeline=[TimelineSpan(start=start,end=end)] if start>state.start+.01 or end<state.end-.01 else []
    candidate.speed=list(manual_speed);pause_cut_bounds=None
    relevant=[c for c in info['cues'] if c['end']>start and c['start']<end]
    # No global fast-forward: only confirmed pauses, with 100ms guards to speech.
    if not explicit_keep and not existing_timing:
        gaps=[]
        for left,right in zip(relevant,relevant[1:]):
            a=max(start,left['end']+.1);b=min(end,right['start']-.1)
            if b-a>=.65:gaps.append((a,b))
        if len(gaps)>1:
            a,b=max(gaps,key=lambda g:g[1]-g[0])
            # Remove the middle of a confirmed pause, leaving breath room at both ends.
            # The other pause can carry a speed ramp: never accelerate spoken words.
            cut_a=a+.12;cut_b=b-.12
            pause_cut_bounds=(a+.02,cut_b-.15)
            candidate.timeline=[TimelineSpan(start=start,end=cut_a),TimelineSpan(start=cut_b,end=end)]
            gaps.remove((a,b))
            report('pause_removal','applied',f'Removed silent pause {cut_a:.2f}–{cut_b:.2f}s; complete spoken phrases retained.',start=cut_a,duration=cut_b-cut_a)
        for a,b in sorted(gaps,key=lambda g:g[1]-g[0],reverse=True)[:2]:
            if len(candidate.speed)>=8 or any(a<r.end and b>r.start for r in candidate.speed):continue
            ramp=SpeedRamp(start=a,end=b,rate_from=1,rate_to=1.8)
            candidate.speed.append(ramp);generated_speed.append(ramp)
    candidate.speed.sort(key=lambda r:r.start)
    if candidate.timeline or candidate.speed:
        candidate.composition.mode='fit';candidate.reframe.enabled=False
    clock=Clock(candidate)
    if clock.duration<1:raise HTTPException(422,'Not enough complete footage remains for this style.')
    report('opening','applied',f'{reason} Kept {start:.2f}–{end:.2f}s; output {clock.duration:.2f}s.',start=start,duration=end-start)
    for ramp in generated_speed:report('speed_ramp','applied',f'Pause-only ramp {ramp.start:.2f}–{ramp.end:.2f}s: 1.00×→1.80×; spoken phrases stay at 1×.',start=ramp.start,duration=ramp.end-ramp.start)
    if not candidate.speed:report('speed_ramp','skipped','No safe long pause for a speed ramp; dialogue was not accelerated.')
    library=audio_store.library()
    music=next((a for a in library if a['id']==action.asset_id and a['kind']=='music'),None) if action.asset_id else None
    manual_music=next((s for s in manual_audio if s.track=='music'),None)
    current=manual_music or next((s for s in state.audio if s.track=='music'),None)
    if manual_music:music=audio_store.entry(manual_music.asset_id)
    if music is None and current:music=audio_store.entry(current.asset_id)
    if music is None:music=next((a for a in library if a['name']=='Reel pulse'),None)
    if not music:raise HTTPException(409,'No permitted music is available. Upload or choose a track in Music.')
    offset=current.offset if current and current.asset_id==music['id'] else 0
    measured=analyze(audio_store.media(music['id']))
    def aligned_beats():
        begin=max(start,manual_music.start) if manual_music else start
        finish=min(end,manual_music.start+manual_music.duration) if manual_music else end
        if finish<=begin:return []
        output_begin=clock.output(begin);output_end=clock.output(finish)
        source_offset=offset+(begin-manual_music.start if manual_music else 0)
        found=loop_beats(measured,music['duration'],output_end-output_begin,source_offset)
        if manual_music and not manual_music.loop:
            found=[t for t in found if t+source_offset<music['duration']]
        return [round(t+output_begin,4) for t in found]
    beats=aligned_beats()
    if beats and pause_cut_bounds:
        cut_a=candidate.timeline[0].end;cut_b=candidate.timeline[1].start
        before=clock.output(cut_a);lo,hi=pause_cut_bounds
        available=[t for t in beats if before+lo-cut_a<=t<=before+hi-cut_a]
        if available:
            beat=min(available,key=lambda t:abs(t-before));new_a=cut_a+beat-before
            previous_duration=clock.duration
            candidate.timeline[0].end=new_a
            clock=Clock(candidate);beats=aligned_beats()
            for row in reports:
                if row['action']=='pause_removal':
                    row.update(start=new_a,duration=cut_b-new_a,message=f'Removed silent pause {new_a:.2f}–{cut_b:.2f}s; cut lands on music beat at output {beat:.2f}s. Complete spoken phrases retained.')
                if row['action']=='opening':row['message']=row['message'].replace(f'output {previous_duration:.2f}s',f'output {clock.duration:.2f}s')
    candidate.audio=list(manual_audio)
    if not manual_music:
        if len(candidate.audio)>=24:raise HTTPException(409,'Audio track budget is full. Remove an unused segment before adding a music bed.')
        bed=AudioSegment(id=uuid.uuid4().hex,asset_id=music['id'],track='music',start=start,duration=end-start,offset=offset,volume=.24,fade_in=.12,fade_out=.35,duck=True,duck_gain=.18,loop=True)
        candidate.audio.append(bed);generated_audio.append(bed.id)
        report('music','applied',f'Added {music["name"]} with dialogue ducking, fades and continuous output-time playback.')
    else:
        report('music','preserved',f'Kept existing {music["name"]} timing, offset, volume and fades; beats measured against that music bed.')
    if beats:report('beat_analysis','applied',f'Detected {len(beats)} onset-aligned beats; {measured["bpm"]:.1f} BPM estimate, confidence {measured["confidence"]:.2f}. Effect times use this output clock.')
    else:report('beat_analysis','failed','No reliable beat grid in the selected music. Phrase-timed effects applied; beat sync is unverified.')
    def snap(t):
        if not beats:return t
        near=min(beats,key=lambda b:abs(b-t))
        return near if abs(near-t)<=.25 else t
    candidate.motion=list(manual_motion);candidate.accents=list(manual_accents);candidate.broll=list(manual_broll)
    # Pick a few dialogue/scene events, separated by >=2 seconds. Protect the opening.
    observations=info.get('editor_moments',[])
    cues=[{**c,'reason':'Dialogue: '+c['text'][:180],'activity':'medium','score':.5+min(.4,len(c['text'].split())/40)} for c in relevant if start+.6<=c['start']<end-1]
    cues += [{'start':o['at'],'text':o['description'],'reason':'Visible moment: '+o['description'], 'activity':o['activity'],'score':o['importance']+(.3 if o['activity']=='high' else 0)}
             for o in observations if o['importance']>=.5 and start+.6<=o['at']<end-1]
    def available(t):
        source=clock.source(t)
        return all(not (source<m.start+m.duration+.2 and source+.7>m.start-.2) for m in manual_motion) and all(not (source<b.start+b.duration and source+.7>b.start) for b in manual_broll)

    suggested=[s['at'] for s in info.get('trend_suggestions',[]) if s['technique']=='punch_in' and s.get('at') is not None]
    ranked=sorted(cues,key=lambda c:(min((abs(c['start']-t) for t in suggested),default=0),-c['score']))
    ranked=[c for c in ranked if clock.kept(c['start'],min(end,c['start']+.05))]
    moments=[]
    if flashy and cues:
        early=next((c for c in sorted(cues,key=lambda c:c['start']) if .65<clock.output(c['start'])<3.5),None)
        if early and available(snap(clock.output(early['start']))):moments.append(snap(clock.output(early['start'])))
        # Cover the clip instead of clustering every reaction around one AI suggestion.
        for section in range(3):
            event=next((c for c in ranked if section*clock.duration/3<=clock.output(c['start'])<(section+1)*clock.duration/3
                        and .65<snap(clock.output(c['start']))<clock.duration-.9
                        and available(snap(clock.output(c['start']))) and all(abs(snap(clock.output(c['start']))-v)>=separation for v in moments)),None)
            if event:moments.append(snap(clock.output(event['start'])))
    for cue in ranked:
        t=snap(clock.output(cue['start']))
        if .65<t<clock.duration-.9 and available(t) and all(abs(t-v)>=separation for v in moments):moments.append(t)
        if len(moments)>=budget:break
    moments=moments[:budget]
    if not moments:report('motion','skipped','No sufficiently grounded, non-overlapping moment was available for an extra zoom.')
    for i,t in enumerate(sorted(moments)):
        source=clock.source(t);finish=clock.source(min(clock.duration,t+(.45 if flashy else .7)))
        evidence=min(ranked,key=lambda c:abs(clock.output(c['start'])-t))
        busy=evidence['activity']=='high'
        requested_shake=action.shake_strength if action.shake_strength is not None else (.009 if flashy else .004)
        shake=min(requested_shake,.003) if busy else requested_shake
        if i >= (2 if flashy else 1):shake=0
        end_scale=min(zoom_to,1.16) if busy else zoom_to
        motion=Motion(start=source,duration=finish-source,scale_from=zoom_from,scale_to=end_scale,shake=shake)
        candidate.motion.append(motion);generated_motion.append(motion)
        alignment='beat-aligned' if beats and min(abs(t-b) for b in beats)<.002 else 'content-timed'
        report('motion','applied',f'{"Flashy" if flashy else "High-energy"} {alignment} punch-in at output {t:.2f}s (source {source:.2f}s), zoom {zoom_from:.2f}×→{end_scale:.2f}×; '+('brief controlled shake. ' if shake else 'no shake. ')+evidence['reason'],start=source,duration=finish-source,output_start=t)
    # One short blur accent at a real scene cut; never flashes or stacked transitions.
    cuts=[t for t in info.get('scene_boundaries',[]) if start+2<t<end-2 and all(abs(clock.output(t)-m)>1 for m in moments)]
    if cuts and len(candidate.accents)<8:
        t=clock.output(cuts[0]);a=clock.source(max(0,t-.05));b=clock.source(min(clock.duration,t+.05))
        accent=CutAccent(start=a,duration=max(.05,b-a),strength=1.8)
        candidate.accents.append(accent);generated_accents.append(accent)
        report('cut_accent','applied',f'One restrained 0.10s blur accent near scene cut at output {t:.2f}s.')
    # Only two short cutaways; leave the hook and final spoken payoff visible.
    query=action.query
    context=' '.join([info.get('clip_title',''),*[c['text'] for c in relevant],*[o['description'] for o in observations]]).casefold()
    if query:
        vocabulary=set(re.findall(r'\w+',context))
        generic={'reel','pulse','high','energy','beat','upbeat','cinematic','music','dynamic','stock','footage','video','the','and','with','a'}
        terms=set(re.findall(r'\w+',query.casefold()))-generic
        if not terms or not (terms & vocabulary):
            report('broll_query','skipped','Search terms were not grounded in footage/transcript context; no generic style footage inserted.')
            query=None
    if query:
        try:
            results=stock.search(query)['results'];asset=None
            for item in results[:4]:
                if item['duration']<1.2:continue
                try:stock.media(item['id']);asset=Asset(**item);break
                except (HTTPException,OSError):continue
            if not asset:raise HTTPException(409,'No suitable downloadable cutaway was found.')
            inserted=0
            anchors=[c['start'] for c in relevant if terms & set(re.findall(r'\w+',c['text'].casefold()))]
            anchors += [o['at'] for o in observations if terms & set(re.findall(r'\w+',o['description'].casefold()))]
            for source_anchor in sorted(set(anchors)):
                if inserted>=2:break
                t=snap(clock.output(source_anchor))
                if t<3 or t>clock.duration-2 or len(candidate.broll)>=30:continue
                if any(abs(t-m)<(.55 if flashy else 1) for m in moments):continue
                a=clock.source(t);b=clock.source(min(clock.duration,t+1))
                if any(a<s.start+s.duration and b>s.start for s in candidate.broll):continue
                candidate.broll.append(Segment(id=uuid.uuid4().hex,asset=asset,start=a,duration=b-a,offset=0,mode='fill',transition='dissolve',transition_duration=.1))
                generated_broll.append(candidate.broll[-1].id)
                inserted+=1
                report('broll_auto','applied',f'Relevant cutaway at output {t:.2f}–{t+1:.2f}s, 0.10s dissolve; dialogue preserved.',start=a,duration=b-a)
            if not inserted:report('broll_auto','skipped','No cutaway slot met the hook/payoff and effect-spacing budget; source footage retained.')
        except (HTTPException,OSError) as exc:report('broll_auto','failed',str(exc.detail if isinstance(exc,HTTPException) else 'Stock media unavailable; other edits retained.'))
    else:report('broll_auto','skipped','No grounded visual search query was supplied; no irrelevant stock was inserted.')
    # Only one whoosh accent; never a sound on every beat.
    if moments:
        sound=next((a for a in library if a['name']=='Air whoosh'),None)
        if sound and len(candidate.audio)<24:
            t=sorted(moments)[0];a=clock.source(t);b=clock.source(min(clock.duration,t+min(.4,sound['duration'])))
            candidate.audio.append(AudioSegment(id=uuid.uuid4().hex,asset_id=sound['id'],track='sfx',start=a,duration=b-a,volume=.17,fade_in=.01,fade_out=.08,duck=True,duck_gain=.55,loop=False))
            generated_audio.append(candidate.audio[-1].id)
            report('sfx','applied',f'One quiet whoosh at output {t:.2f}s, ducked under speech.')
        if flashy:
            impact=next((a for a in library if a['name']=='Impact hit'),None)
            if impact and len(moments)>2 and len(candidate.audio)<24:
                t=sorted(moments)[-1];a=clock.source(t);b=clock.source(min(clock.duration,t+.25))
                candidate.audio.append(AudioSegment(id=uuid.uuid4().hex,asset_id=impact['id'],track='sfx',start=a,duration=b-a,volume=.22,fade_in=.005,fade_out=.1,duck=True,duck_gain=.4,loop=False))
                generated_audio.append(candidate.audio[-1].id)
                report('sfx','applied',f'Quiet impact on the final punch-in at output {t:.2f}s; dialogue ducking enabled.')
    words=re.findall(r"[\w']+",' '.join(c['text'] for c in relevant).lower())
    stop={'the','and','that','this','with','have','your','you','are','for','but','was','not','just','what','when','from','they','them','then','would','could'}
    keywords=list(dict.fromkeys(w for w in sorted(words,key=lambda w:-(min(8,len(w))+12*(w in {'teddy','friend','mind','best','never','why','secret'}))) if len(w)>3 and w not in stop))[:6]
    candidate.captions=candidate.captions.model_copy(update={'enabled':True,'font':'Arial','size':50,'bold':True,'color':'#ffffff','highlight':'#ffe05b','stroke':'#101010','thickness':2.5,'position':'bottom','opacity':.45,'background':'#101010','animation':'pop','max_words':4,'emphasis':keywords})
    if flashy:candidate.captions=candidate.captions.model_copy(update={'size':60,'max_words':3,'thickness':3,'animation':'karaoke'})
    if action.animation:candidate.captions.animation=action.animation
    if not previous:candidate.effects=candidate.effects.model_copy(update={'brightness':min(2,candidate.effects.brightness*1.02),'contrast':min(2,candidate.effects.contrast*1.07),'saturation':min(2,candidate.effects.saturation*1.06)})
    candidate.transition=Transition(fade_in=.08,fade_out=.18)
    candidate.reel=ReelInfo(music_asset_id=music['id'],beats=beats,bpm=measured['bpm'],beat_confidence=measured['confidence'],beat_sync_current=bool(beats),hook_reason=reason,intensity='flashy' if flashy else 'high-energy',generated_motion=generated_motion,generated_accents=generated_accents,generated_audio_ids=generated_audio,generated_broll_ids=generated_broll,generated_speed=generated_speed,last_motion_index=len(candidate.motion)-1 if generated_motion else None)
    report('captions','applied',f'Bold {candidate.captions.max_words}-word {candidate.captions.animation} captions'+' with emphasized transcript keywords; word timing estimated within cues.')
    if not pause_cut_bounds and not existing_timing:report('cuts','skipped','No safe beat-aligned pause cut was available; no spoken phrase or arbitrary action shot was removed.')
    report('style','applied',f'{"Flashy" if flashy else "High-energy"} profile: up to {budget} content/beat-timed zooms, minimum {separation:.2f}s spacing. No strobing; dialogue stays at 1×.')
    report('color','applied','Consistent restrained contrast/saturation grade; no flashes.')
    return candidate,reports
