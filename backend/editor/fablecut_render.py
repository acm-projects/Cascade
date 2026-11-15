"""Isolated MIT FableCut compositor over Cascade's existing manual-edit render.

Each export gets a private data directory and loopback server; no user credentials,
remote media URLs, inference, or executable project payloads enter this process.
"""
import json
import logging
import math
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import unquote

import httpx
from fastapi import HTTPException
from .retiming import Clock

LOG = logging.getLogger(__name__)
RENDER_LOCK = threading.Lock()


def engine_path():
    path = Path(os.getenv('CASCADE_FABLECUT_DIR', str(Path(__file__).parent/'.cache/fablecut'))).resolve()
    try:
        if json.loads((path/'package.json').read_text())['version'] != '1.18.0':
            raise ValueError('version')
        if not (path/'LICENSE').read_text().startswith('MIT License'):
            raise ValueError('license')
        if not (path/'server.js').is_file(): raise ValueError('runtime')
        if (path/'CASCADE_PIN').read_text().strip()!='579b08ec1a789baec5cbf06d7430373460508d09':raise ValueError('pin')
    except (OSError, ValueError, KeyError):
        raise HTTPException(503, 'FableCut 1.18.0 is not installed. Run python3 scripts/install_fablecut.py. Your original edit is preserved.') from None
    return path


def sequence_pieces(state):
    """Native source clock → base-render clock → final sequence clock."""
    base = state.model_copy(update={'fablecut': None})
    clock = Clock(base)
    pieces = []; cursor = 0
    for shot in state.fablecut.shots:
        a, b = max(state.start, shot.start), min(state.end, shot.end)
        if b <= a: continue
        begin, end = clock.output(a), clock.output(b)
        if end-begin < .05: continue
        duration = 2*(end-begin)/(shot.rate_from+shot.rate_to)
        pieces.append({'shot':shot, 'source_start':a, 'source_end':b, 'input':begin,
                       'consumed':end-begin, 'start':cursor, 'duration':duration})
        cursor += duration
    if not pieces: raise HTTPException(422, 'The current trim excludes every AI sequence shot. Undo the trim or generate a new sequence.')
    return pieces


def project_document(state, info, audio_store, folder):
    pieces = sequence_pieces(state)
    ratio = 9/16 if state.fablecut.ratio=='9:16' else {'9:16':9/16, '1:1':1, '4:5':.8, '16:9':16/9, '4:3':4/3}.get(state.composition.ratio, info['width']/info['height'])
    height = 960 if ratio < 1 else 540
    width = round(height*ratio/2)*2
    project = {'name':'Cascade sequence', 'revision':1, 'width':width, 'height':height,
               'fps':30, 'panSchema':1, 'media':[{'id':'base','name':'Manual edit render','kind':'video','src':'/media/base.mp4'}],
               'clips':[], 'markers':[], 'master':{'fx':[{'type':'limiter','ceiling':-1}]}}
    total = sum(p['duration'] for p in pieces)
    base_clock=Clock(state.model_copy(update={'fablecut':None}))
    def mapped(part,source):
        x=max(0,min(part['consumed'],base_clock.output(source)-part['input']))
        shot=part['shot'];k=(shot.rate_to-shot.rate_from)/part['duration']
        dt=x/shot.rate_from if abs(k)<1e-9 else (-shot.rate_from+math.sqrt(max(0,shot.rate_from**2+2*k*x)))/k
        return part['start']+dt
    def add_audio(ident, name):
        if any(m['id']==ident for m in project['media']):return ident
        filename=f'{ident}.wav'; shutil.copy2(audio_store.media(ident), folder/'media'/filename)
        project['media'].append({'id':ident,'name':name,'kind':'audio','src':'/media/'+filename})
        return ident
    for i, part in enumerate(pieces):
        shot = part['shot']; d = part['duration']; at = part['start']
        rate = [{'t':0,'v':shot.rate_from},{'t':d,'v':shot.rate_to,'ease':'linear'}]
        props = {'fit':'cover','volume':0,'contrast':100*(1+state.fablecut.grade), 'saturation':100*(1+state.fablecut.grade/2)}
        keys = {'speed':rate}
        if shot.zoom > 1:
            peak=min(shot.zoom_at,d/4)
            keys['scale']=([{'t':0,'v':1},{'t':peak,'v':shot.zoom,'ease':'ease-out'}] if peak>.001 else [{'t':0,'v':shot.zoom}])+[{'t':d,'v':1.02,'ease':'linear'}]
        if shot.shake:
            keys['shake']=[{'t':0,'v':shot.shake},{'t':min(.22,d),'v':0,'ease':'ease-out'}]
        item={'id':f'shot-{i}','kind':'video','mediaId':'base','track':'V1','start':at,'in':part['input'],'duration':d,'props':props,'keyframes':keys}
        if i and shot.transition!='none': item['transitionIn']={'type':shot.transition,'duration':min(.16,d/4)}
        if i==len(pieces)-1: item['transitionOut']={'type':'fade','duration':min(.25,d/4)}
        project['clips'].append(item)
        # Never pitch-warp speech or production sound. Ramped action shots are silent;
        # music and authored SFX continue on their own output-time tracks.
        if shot.rate_from==shot.rate_to==1:
            project['clips'].append({'id':f'dialogue-{i}','kind':'audio','mediaId':'base','track':'A1','start':at,'in':part['input'],'duration':d,'props':{'volume':1},'transitionIn':{'type':'fade','duration':.006},'transitionOut':{'type':'fade','duration':.006}})
        if state.captions.enabled:
            clock=Clock(state.model_copy(update={'fablecut':None}))
            for cue_index,cue in enumerate(info['cues']):
                a=max(part['source_start'],cue['start']);b=min(part['source_end'],cue['end'])
                if b<=a:continue
                text=state.texts.get(str(cue_index),cue['text']);words=text.split()
                if not words:continue
                # Existing VTT has cue timing only. Grouping does not invent forced alignment.
                for word in range(0,len(words),3):
                    group=words[word:word+3]
                    ca=at+clock.output(a)-part['input']+(b-a)*word/len(words)
                    cd=(b-a)*len(group)/len(words)
                    size=min(width*.075,state.captions.size*height/540)
                    project['clips'].append({'id':f'caption-{i}-{cue_index}-{word}','kind':'text','mediaId':None,'track':'V2','start':ca,'in':0,'duration':cd,'props':{'text':' '.join(group),'font':state.captions.font,'fontSize':size,'bold':state.captions.bold,'color':state.captions.color,'strokeColor':state.captions.stroke,'strokeWidth':state.captions.thickness,'bgColor':state.captions.background,'bgOpacity':state.captions.opacity,'highlightColor':state.captions.highlight,'y':height*({'top':-.32,'middle':0,'bottom':.32}[state.captions.position]),'textAnim':{'pop':'word-pop','karaoke':'karaoke','none':'none'}[state.captions.animation],'wordRate':cd/len(group),'wordTimes':[[cd*n/len(group),cd*(n+1)/len(group)] for n in range(len(group))]}})
    library = audio_store.library()
    # Manual music/SFX are rebuilt on the final output clock, not baked into
    # footage and jumped/pitch-warped when its shots are reordered.
    for number,segment in enumerate(state.audio):
        asset=audio_store.entry(segment.asset_id);add_audio(segment.asset_id,asset['name'])
        intervals=[]
        for part in pieces:
            a=max(part['source_start'],segment.start);b=min(part['source_end'],segment.start+segment.duration)
            if b>a:intervals.append([mapped(part,a),mapped(part,b),segment.offset+a-segment.start])
        if segment.track=='music':
            joined=[]
            for a,b,offset in intervals:
                if joined and abs(joined[-1][1]-a)<.002:joined[-1][1]=b
                else:joined.append([a,b,offset])
            intervals=joined
        for interval,(a,b,offset) in enumerate(intervals):
            t=a;chunk=0
            while t<b-.001:
                if segment.loop:offset%=asset['duration']
                if offset>=asset['duration']:break
                d=min(b-t,asset['duration']-offset)
                duck=[]
                if segment.track=='music' and segment.duck:
                    for part in pieces:
                        if any(c['start']<part['source_end'] and c['end']>part['source_start'] for c in info['cues']):
                            left=max(0,part['start']-t);right=min(d,part['start']+part['duration']-t)
                            if right>left:duck.extend([{'t':max(0,left-.1),'v':20*math.log10(max(.001,segment.duck_gain))},{'t':right,'v':20*math.log10(max(.001,segment.duck_gain))},{'t':min(d,right+.2),'v':0}])
                project['clips'].append({'id':f'manual-audio-{number}-{interval}-{chunk}','kind':'audio','mediaId':segment.asset_id,'track':'A2' if segment.track=='music' else 'A3','start':t,'in':offset,'duration':d,'props':{'volume':segment.volume},'keyframes':{'duck':sorted(duck,key=lambda k:k['t'])},'transitionIn':{'type':'fade','duration':min(segment.fade_in,d/3) if chunk==0 else 0},'transitionOut':{'type':'fade','duration':min(segment.fade_out,d/3) if t+d>=b-.001 else 0}})
                offset+=d;t+=d;chunk+=1
                if not segment.loop:break
    ident = state.fablecut.music_asset_id
    if ident and not any(a.track=='music' for a in state.audio):
        asset = audio_store.entry(ident)
        if asset['kind']!='music': raise HTTPException(422,'Select a music asset for the sequence bed.')
        add_audio(ident,asset['name'])
        # Repeat as separate clips: never pretend a short asset contains more audio.
        t=0; n=0
        while t<total:
            d=min(asset['duration'],total-t)
            duck=[]
            for p in pieces:
                voiced=any(c['start']<p['source_end'] and c['end']>p['source_start'] for c in info['cues'])
                if voiced and p['start']<t+d and p['start']+p['duration']>t:
                    a=max(0,p['start']-t); b=min(d,p['start']+p['duration']-t)
                    duck += [{'t':max(0,a-.12),'v':-12},{'t':b,'v':-12},{'t':min(d,b+.25),'v':0}]
            project['clips'].append({'id':f'bed-{n}','kind':'audio','mediaId':ident,'track':'A2','start':t,'in':0,'duration':d,'props':{'volume':state.fablecut.music_volume},'keyframes':{'duck':sorted(duck,key=lambda k:k['t'])},'transitionIn':{'type':'fade','duration':.1},'transitionOut':{'type':'fade','duration':.25}})
            t+=d;n+=1
    if state.fablecut.sound_design:
        impact=next(a for a in library if a['name']=='Impact hit'); whoosh=next(a for a in library if a['name']=='Air whoosh')
        riser=next(a for a in library if a['name']=='Build riser')
        for asset in (impact,whoosh,riser):add_audio(asset['id'],asset['name'])
        emphasis=next((p for p in pieces[1:] if p['shot'].transition!='none' or p['shot'].rate_from!=p['shot'].rate_to),None)
        if emphasis and emphasis['start']>.5:
            d=min(riser['duration'],emphasis['start'])
            project['clips'].append({'id':'build-riser','kind':'audio','mediaId':riser['id'],'track':'A4','start':emphasis['start']-d,'in':riser['duration']-d,'duration':d,'props':{'volume':.1},'transitionIn':{'type':'fade','duration':.2},'transitionOut':{'type':'fade','duration':.05}})
        for i,p in enumerate(pieces[1:],1):
            shot=p['shot']
            if shot.transition=='none' and shot.zoom<=1.05:continue
            asset=whoosh if shot.transition!='none' else impact
            at=max(0,p['start']-(.08 if asset==whoosh else 0))
            project['clips'].append({'id':f'fx-{i}','kind':'audio','mediaId':asset['id'],'track':'A3','start':at,'in':0,'duration':min(asset['duration'],total-at),'props':{'volume':.15},'transitionOut':{'type':'fade','duration':.15}})
    return project


def render(base, output, state, info, audio_store):
    engine=engine_path()
    with RENDER_LOCK, tempfile.TemporaryDirectory(prefix='cascade-fablecut-') as temporary:
        folder=Path(temporary);(folder/'media').mkdir()
        shutil.copy2(base,folder/'media/base.mp4')
        (folder/'project.json').write_text(json.dumps(project_document(state,info,audio_store,folder)))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        # Explicit allowlist: even database URLs and unrelated service settings
        # stay out of the compositor's environment.
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','TMPDIR','LANG','LC_ALL','USER','SYSTEMROOT','FABLECUT_CHROME')}
        env.update(PORT=str(port),HOST='127.0.0.1',FABLECUT_DATA_DIR=str(folder))
        process=None
        try:
            process=subprocess.Popen(['node',str(engine/'server.js')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=15) as client:
                for _ in range(100):
                    try:
                        if client.get('/api/project').is_success:break
                    except httpx.RequestError:pass
                    if process.poll() is not None:raise RuntimeError('engine_start')
                    time.sleep(.1)
                response=client.post('/api/export/request',json={'where':'headless','range':'entire','profile':'hq'})
                response.raise_for_status();job=response.json()['id']
                deadline=time.monotonic()+300
                while time.monotonic()<deadline:
                    result=client.get('/api/export/job',params={'id':job}).json()
                    if result['status']=='done':
                        path=folder/'exports'/Path(unquote(result['src'])).name
                        if not path.is_file() or path.stat().st_size<1000:raise RuntimeError('missing_media')
                        shutil.copy2(path,output)
                        return
                    if result['status'] in ('failed','cancelled'):
                        # Categorize only known messages; never log captions, paths
                        # or arbitrary browser/provider exception bodies.
                        message=str(result.get('error','')).lower()
                        reason='video_seek_timeout' if 'seek' in message else 'ffmpeg_encode' if 'ffmpeg' in message else 'browser_exit' if 'browser' in message else 'engine_render'
                        raise RuntimeError(reason)
                    time.sleep(.25)
                client.post('/api/export/job/cancel',params={'id':job})
                raise RuntimeError('engine_timeout')
        except (OSError, RuntimeError, httpx.HTTPError, ValueError, KeyError) as exc:
            allowed={'engine_start','missing_media','engine_timeout','video_seek_timeout','ffmpeg_encode','browser_exit','engine_render'}
            reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allowed else 'local_transport'
            LOG.warning('FableCut export failed stage=local_composition reason=%s',reason)
            raise HTTPException(503,f'FableCut local render failed ({reason}). The edit is saved. Check Node, Chrome and FFmpeg, then retry; simplify the sequence if rendering timed out. No paid service was used.') from None
        finally:
            if process:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
