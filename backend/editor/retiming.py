"""One source↔output clock for plans, captions, audio, preview and MP4 export.
Ramps use eight pitch-preserving tempo steps, and are prohibited over speech.
"""
from contextlib import contextmanager
from pathlib import Path
import copy
import re
import subprocess
import tempfile
from fastapi import HTTPException
from .advanced_models import TimelineSpan

def phrases(cues):
    result=[];current=None
    for cue in sorted(cues,key=lambda c:c['start']):
        if current and cue['start']-current['end']>.3:
            result.append(current);current=None
        if current is None: current={'start':cue['start'],'end':cue['end'],'text':cue['text']}
        else: current['end']=cue['end'];current['text']+=' '+cue['text']
        if re.search(r'[.!?]["\u201d\u2019\']?$',cue['text'].strip()):result.append(current);current=None
    if current:result.append(current)
    return result

class Clock:
    def __init__(self,state):
        spans=state.timeline or [TimelineSpan(start=state.start,end=state.end)]
        self.pieces=[];out=0
        for span in spans:
            left=max(state.start,span.start);right=min(state.end,span.end)
            boundaries={left,right}
            for ramp in state.speed:
                for i in range(9):
                    t=ramp.start+(ramp.end-ramp.start)*i/8
                    if left<t<right:boundaries.add(t)
            points=sorted(boundaries)
            for a,b in zip(points,points[1:]):
                if b<=a:continue
                mid=(a+b)/2;rate=1
                for ramp in state.speed:
                    if ramp.start<=mid<ramp.end:
                        ratio=(mid-ramp.start)/(ramp.end-ramp.start);rate=ramp.rate_from+(ramp.rate_to-ramp.rate_from)*ratio
                self.pieces.append((a,b,rate,out));out+=(b-a)/rate
        self.duration=out
    def output(self,t):return sum(max(0,min(b-a,t-a))/rate for a,b,rate,_ in self.pieces)
    def source(self,t):
        for a,b,rate,start in self.pieces:
            if t<start+(b-a)/rate-1e-8:return a+max(0,t-start)*rate
        return self.pieces[-1][1] if self.pieces else 0
    def kept(self,start,end):return self.output(end)-self.output(start)>.001
    def expression(self):
        return '+'.join(f'max(0,min({b-a:.9f},PTS*TB-({a:.9f})))/{rate:.9f}' for a,b,rate,_ in self.pieces) or '0'

def validate_timing(state,cues,duration):
    previous=state.start
    windows=phrases(cues)
    for span in state.timeline:
        if not state.start<=span.start<span.end<=state.end or span.start<previous-.001:
            raise HTTPException(422,'Kept ranges must be ordered, non-overlapping and inside the trim.')
        for point in (span.start,span.end):
            if any(c['start']+.015<point<c['end']-.015 for c in windows):
                raise HTTPException(422,'A cut would split a spoken phrase. Choose a transcript phrase boundary.')
        previous=span.end
    last=-1
    for ramp in sorted(state.speed,key=lambda r:r.start):
        if not state.start<=ramp.start<ramp.end<=state.end or ramp.start<last:
            raise HTTPException(422,'Speed ramps must be non-overlapping and inside the trim.')
        if not cues:raise HTTPException(422,'Speech timestamps are required before safe speed changes can be applied.')
        if any(ramp.start<c['end']+.08 and ramp.end>c['start']-.08 for c in cues):
            raise HTTPException(422,'Speed changes cannot overlap speech. Use a confirmed pause to preserve natural dialogue.')
        last=ramp.end
    if len(Clock(state).pieces)>96:raise HTTPException(422,'Use fewer cuts or speed ramps.')

def mapped_state(state,info):
    clock=Clock(state);mapped=state.model_copy(deep=True)
    mapped.start=0;mapped.end=clock.duration;mapped.timeline=[];mapped.speed=[]
    for field in ('motion','accents','text_overlays','broll','audio'):
        rows=[]
        for item in getattr(state,field):
            end=item.start+item.duration
            if not clock.kept(item.start,end):continue
            update={'start':clock.output(item.start),'duration':clock.output(end)-clock.output(item.start)}
            if field=='broll' and item.offset+update['duration']>item.asset.duration:
                raise HTTPException(422,'Retimed B-roll exceeds the available stock media.')
            rows.append(item.model_copy(update=update))
        setattr(mapped,field,rows)
    cues=[]
    for i,c in enumerate(info['cues']):
        if clock.kept(c['start'],c['end']):
            cues.append({**c,'start':clock.output(c['start']),'end':clock.output(c['end']),'text':state.texts.get(str(i),c['text'])})
    mapped.texts={}
    return mapped,{**info,'duration':clock.duration,'cues':cues},clock

@contextmanager
def prepare(source,state,info,binary):
    mapped,new_info,clock=mapped_state(state,info)
    with tempfile.TemporaryDirectory(prefix='cascade-retime-') as directory:
        path=Path(directory)/'retimed.mp4'
        keep='+'.join(f'between(t,{a:.9f},{b-1e-7:.9f})' for a,b,_,_ in clock.pieces)
        graph=f"[0:v]select='{keep}',setpts='({clock.expression()})/TB',fps=30[v]"
        audio_map=[]
        if info['has_audio']:
            labels=[]
            for i,(a,b,rate,start) in enumerate(clock.pieces):
                length=(b-a)/rate
                tempo=f',atempo={rate:.9f}' if abs(rate-1)>1e-8 else ''
                graph+=f';[0:a]atrim=start={a:.9f}:end={b:.9f},asetpts=PTS-STARTPTS{tempo},aresample=48000,apad,atrim=duration={length:.9f},afade=t=in:st=0:d=0.002,afade=t=out:st={max(0,length-.002):.9f}:d=0.002[a{i}]'
                labels.append(f'[a{i}]')
            graph+=';'+''.join(labels)+f'concat=n={len(labels)}:v=0:a=1[a]';audio_map=['-map','[a]']
        try:
            (Path(directory)/'graph.txt').write_text(graph)
            args=['-filter_complex',graph]
            if len(graph)>60000:
                help_text=subprocess.run([binary,'-hide_banner','-h','full'],capture_output=True,text=True,timeout=15,check=True).stdout
                args=['-filter_complex_script' if '-filter_complex_script' in help_text else '-/filter_complex',str(Path(directory)/'graph.txt')]
            subprocess.run([binary,'-nostdin','-v','error','-y','-i',str(source),*args,'-map','[v]',*audio_map,'-t',str(clock.duration),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac',str(path)],capture_output=True,check=True,timeout=300)
        except (OSError,subprocess.SubprocessError):
            raise HTTPException(503,'Timeline retiming failed. No speed or cut success is confirmed for this render.') from None
        yield path,mapped,new_info
