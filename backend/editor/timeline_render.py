"""FFmpeg graph helpers; source timestamps remain stable through all edits."""
import math

def motion_filter(state, width, height):
    if not state.motion: return 'null'
    zoom=[];shake=[]
    for m in state.motion:
        start=m.start-state.start;end=start+m.duration
        gate=f'between(t,{start:.6f},{end:.6f})'
        progress=f'max(0,min(1,(t-({start:.6f}))/{m.duration:.6f}))'
        zoom.append(f'({m.scale_from-1:.6f}+({m.scale_to-m.scale_from:.6f})*{progress})*{gate}')
        if m.shake: shake.append(f'{m.shake:.6f}*{gate}')
    amount='+'.join(shake) or '0'
    z=f'max(1,min(3,1+{ "+".join(zoom) }+2*({amount})))'
    x=f'max(0,min(iw-ow,(iw-ow)/2+{width}*({amount})*sin(t*71)))'
    y=f'max(0,min(ih-oh,(ih-oh)/2+{height}*({amount})*sin(t*93)))'
    return f"scale=w='ceil({width}*({z})/2)*2':h='ceil({height}*({z})/2)*2':eval=frame,crop={width}:{height}:x='{x}':y='{y}',setsar=1"

def transition_filter(state):
    filters=[];duration=state.end-state.start
    if state.transition.fade_in: filters.append(f'fade=t=in:st=0:d={state.transition.fade_in}')
    if state.transition.fade_out: filters.append(f'fade=t=out:st={max(0,duration-state.transition.fade_out)}:d={state.transition.fade_out}')
    for accent in state.accents:
        start=accent.start-state.start
        filters.append(f"gblur=sigma={accent.strength}:enable='between(t,{start},{start+accent.duration})'")
    return ','.join(filters) or 'null'

def audio_graph(state, cues, store, has_audio, first_index):
    """Returns inputs, graph fragments and output mapping. Mix preserves dialogue.
    Duck envelopes use available speech cue windows, including attack/release ramps.
    """
    duration=state.end-state.start
    inputs=[];filters=[];labels=[];index=first_index
    if has_audio:
        filters.append(f'[0:a]atrim=duration={duration},asetpts=PTS-STARTPTS,volume={state.dialogue_volume}[dialogue]')
        labels.append('[dialogue]')
    for number,s in enumerate(state.audio):
        begin=max(state.start,s.start);end=min(state.end,s.start+s.duration)
        if end<=begin: continue
        length=end-begin;offset=s.offset+begin-s.start
        if s.loop: offset %= store.entry(s.asset_id)['duration']
        if s.loop: inputs.extend(['-stream_loop','-1'])
        inputs.extend(['-ss',str(offset),'-t',str(length),'-i',str(store.media(s.asset_id).resolve())])
        duck='1'
        if s.duck and cues:
            envelopes=[]
            for c in cues:
                a=c['start']-begin;b=c['end']-begin
                if b<-.2 or a>length+.2:continue
                envelopes.append(f'max(0,min(1,min((t-({a:.6f})+.12)/.12,(({b:.6f})+.25-t)/.25)))')
            if envelopes:
                speech='min(1,('+ '+'.join(envelopes)+'))'
                duck=f'(1-{1-s.duck_gain:.6f}*({speech}))'
        fade_in=max(0,min(length,s.fade_in-(begin-s.start)))
        fade_out=min(length,s.fade_out)
        parts=[f'atrim=duration={length}','asetpts=PTS-STARTPTS','aresample=48000',f"volume='{s.volume}*({duck})':eval=frame"]
        if fade_in:parts.append(f'afade=t=in:st=0:d={fade_in}')
        if fade_out:parts.append(f'afade=t=out:st={max(0,length-fade_out)}:d={fade_out}')
        delay=round((begin-state.start)*1000)
        parts.append(f'adelay={delay}:all=1')
        filters.append(f'[{index}:a]'+','.join(parts)+f'[added{number}]');labels.append(f'[added{number}]');index+=1
    if not labels:return inputs,filters,None
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=longest:normalize=0:dropout_transition=0,apad,atrim=duration={duration},alimiter=limit=.95:level=false:latency=true[audioout]')
    return inputs,filters,'[audioout]'
