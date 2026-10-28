"""Editor reframe; extracted without changing media behavior."""
import json
import os
import math
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException, Request
from backend import reframe as reframelib
from .models import ReframePlanInput
from .composition import composition_geometry
from .validation import details
from .storage import draft_path, media, selected
from .runtime import jobs_dir, save_json

_reframe_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cascade-reframe")
_reframe_lock = threading.Lock()
_reframe_running = set()

def acquire_analysis_lock(path):
    stream=path.with_suffix('.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0, os.SEEK_END)
            if not stream.tell():
                stream.write(b'0');stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        stream.close();return None
    return stream


@lru_cache(maxsize=16)
def cached_analysis_record(path,mtime,size):
    return json.loads(Path(path).read_text())


def analysis_record(path):
    stat=path.stat()
    return dict(cached_analysis_record(str(path),stat.st_mtime_ns,stat.st_size))


def analysis_folder(pid,jid,index,user):
    return draft_path(pid,jid,index,user).parent/'reframe'/f'{jid}-{index}'


def read_analysis(pid,jid,index,analysis_id,user):
    if not analysis_id or not re.fullmatch(r'[a-f0-9]{32}',analysis_id):
        raise HTTPException(422,'Analyze this clip before enabling Follow Speaker.')
    path=analysis_folder(pid,jid,index,user)/(analysis_id+'.json')
    if not path.is_file():raise HTTPException(409,'Tracking analysis is unavailable. Analyze the clip again.')
    record=analysis_record(path)
    if record['status']!='ready':raise HTTPException(409,record.get('message','Tracking analysis is not ready.'))
    if record['analysis'].get('version')!=reframelib.VERSION:raise HTTPException(409,'Tracking engine changed. Prepare tracking again.')
    if record.get('cache_key'):
        clip=selected(pid,jid,index,user)
        expected=reframelib.analysis_key(tracking_info(jid,clip),record.get('focus','auto'),record.get('selection'))
        if expected!=record['cache_key']:raise HTTPException(409,'Tracking source or models changed. Prepare tracking again.')
    return record['analysis']


def tracking_info(jid,clip):
    info=details(jid,clip)
    owner_path=jobs_dir()/jid/'owner.json'
    owner=json.loads(owner_path.read_text()) if owner_path.is_file() else {}
    paths=[jobs_dir()/jid/Path(clip.get('clip_url','')).name]
    revision=[(p.name,p.stat().st_mtime_ns,p.stat().st_size) for p in paths if p.is_file()]
    return {**info,'context':str(owner.get('prompt',''))+' '+str(clip.get('title','')),
            'source_revision':[revision,clip.get('s3_bucket'),clip.get('clip_s3_key'),clip.get('etag'),clip.get('version_id')]}


def begin_analysis(pid,jid,index,user,selection=None,focus='auto'):
    clip=selected(pid,jid,index,user);info=tracking_info(jid,clip)
    if selection and selection.t>=info['duration']:raise HTTPException(422,'Selection time is outside this clip.')
    selection_data=selection.model_dump() if selection else None
    key=reframelib.analysis_key(info,focus,selection_data)
    folder=analysis_folder(pid,jid,index,user);folder.mkdir(parents=True,exist_ok=True)
    ident=key[:32];path=folder/(ident+'.json')
    with _reframe_lock:
        if path.is_file():
            record=analysis_record(path)
            if record.get('cache_key')==key and record.get('status')=='ready':
                return {'analysis_id':ident,'status':'ready','cache_hit':True,'version':reframelib.VERSION}
        if str(path) in _reframe_running:return {'analysis_id':ident,'status':'processing','cache_hit':True}
        if len(_reframe_running)>=8:raise HTTPException(429,'Local tracking queue is full. Retry shortly.')
        job_lock=acquire_analysis_lock(path)
        if job_lock is None:return {'analysis_id':ident,'status':'processing','cache_hit':True}
        def write(status,progress,message,analysis=None):
            if not folder.is_dir():return
            save_json(path,{'status':status,'progress':progress,'message':message,'updated_at':time.time(),
                                'cache_key':key,'focus':focus,'selection':selection_data,'version':reframelib.VERSION,**({'analysis':analysis}if analysis else {})})
        write('queued',0,'Queued for local tracking…');_reframe_running.add(str(path))
        def work():
            try:
                with media(jid,clip) as source:
                    analysis=reframelib.analyze(source,info,lambda progress,message:write('processing',progress,message),selection=selection_data,focus=focus)
                write('ready',1,'Tracking ready.',analysis)
            except ValueError as error:write('error',0,str(error))
            except Exception:write('error',0,'Local tracking failed. Check dependencies, models and FFmpeg, then retry. No simulated tracking was applied.')
            finally:
                job_lock.close()
                with _reframe_lock:_reframe_running.discard(str(path))
        try:_reframe_worker.submit(work)
        except Exception:
            job_lock.close();_reframe_running.discard(str(path));raise
    return {'analysis_id':ident,'status':'queued','cache_hit':False}


def start_reframe(pid:str,jid:str,index:int,request:Request,body: ReframePlanInput | None = None):
    return begin_analysis(pid,jid,index,request.state.user_id,body.selection if body else None,body.focus if body else 'auto')


def reframe_status(pid:str,jid:str,index:int,analysis_id:str,request:Request):
    selected(pid,jid,index,request.state.user_id)
    if not re.fullmatch(r'[a-f0-9]{32}',analysis_id):raise HTTPException(404,'Tracking job not found.')
    path=analysis_folder(pid,jid,index,request.state.user_id)/(analysis_id+'.json')
    if not path.is_file():
        if path.with_suffix('.lock').is_file():
            probe=acquire_analysis_lock(path)
            if probe is None:return {'status':'queued','progress':0,'message':'Preparing shared tracking job…','version':reframelib.VERSION}
            probe.close()
        raise HTTPException(404,'Tracking job not found.')
    record=analysis_record(path);record['version']=record.get('analysis',{}).get('version',record.get('version'));analysis=record.pop('analysis',{})
    if analysis:record.update(timings=analysis.get('timings',{}),profile=analysis.get('profile'),speaker_device=analysis.get('speaker_device'))
    if record['status'] in ('queued','processing') and str(path) not in _reframe_running:
        probe=acquire_analysis_lock(path)
        if probe is not None:
            probe.close();record.update(status='error',message='Tracking was interrupted. Retry analysis.')
    return record


def subjects_at(pid:str,jid:str,index:int,analysis_id:str,request:Request,t:float=0):
    selected(pid,jid,index,request.state.user_id)
    analysis=read_analysis(pid,jid,index,analysis_id,request.state.user_id)
    if not math.isfinite(t) or t<0 or t>analysis['duration']:raise HTTPException(422,'Invalid source time.')
    row=min(analysis['frames'],key=lambda row:abs(row['t']-t))
    return {'subjects':row.get('subjects',[])}


def reframe_plan(pid:str,jid:str,index:int,analysis_id:str,body:ReframePlanInput,request:Request):
    clip=selected(pid,jid,index,request.state.user_id);info=details(jid,clip)
    analysis=read_analysis(pid,jid,index,analysis_id,request.state.user_id)
    if analysis.get('selection')!=(body.selection.model_dump() if body.selection else None):raise HTTPException(409,'Selected subject changed. Prepare tracking again.')
    return reframelib.plan(analysis,composition_geometry(info['width'],info['height'],body.composition),body.focus,(body.composition.x,body.composition.y))
