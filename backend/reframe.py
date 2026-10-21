"""Local, audio-visual Auto Reframe. No face-only speaker inference or paid calls."""
import math
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from functools import lru_cache
from time import perf_counter
from threading import RLock
from backend.reframe_metrics import Timings

_failed_devices=set()
FPS=25
VERSION=3


def model_folder():
    return Path(os.getenv('CASCADE_REFRAME_MODELS',Path.home()/'.cache/cascade/reframe'))


def models():
    path=model_folder()/'light_asd.model'
    if not path.is_file():raise ValueError('Active speaker model is missing. Run python3 scripts/setup_reframe.py.')
    requested=os.getenv('CASCADE_REFRAME_DEVICE','cpu')
    if requested in _failed_devices:requested='cpu'
    return _speaker_models(str(path.resolve()),path.stat().st_mtime_ns,path.stat().st_size,requested)


@lru_cache(maxsize=2)
def _speaker_models(path,mtime,size,requested_device):
    try:
        import cv2
        import numpy as np
        import torch
        import python_speech_features
    except ImportError as exc:
        raise ValueError('Auto Reframe needs local dependencies. Run: python3 -m pip install -r requirements-reframe.txt; then python3 scripts/setup_reframe.py') from exc
    folder=model_folder()
    if not all((folder/name).is_file() for name in ['yunet.onnx','light_asd.model']):
        raise ValueError('Auto Reframe models are missing. Run: python3 scripts/setup_reframe.py, then retry.')
    from backend.vendor.light_asd.Model import ASD_Model
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    state=torch.load(path,map_location='cpu',weights_only=True)
    network=ASD_Model().eval()
    network.load_state_dict({k.removeprefix('model.'):v for k,v in state.items() if k.startswith('model.')},strict=True)
    classifier=torch.nn.Linear(128,2).eval()
    classifier.load_state_dict({k.removeprefix('lossAV.FC.'):v for k,v in state.items() if k.startswith('lossAV.FC.')},strict=True)
    device='cpu'
    if requested_device in ('cuda','auto') and torch.cuda.is_available():device='cuda'
    elif requested_device in ('mps','auto') and torch.backends.mps.is_available():device='mps'
    if device in _failed_devices:device='cpu'
    try:network=network.to(device);classifier=classifier.to(device)
    except (RuntimeError,NotImplementedError):
        _failed_devices.add(device);network=network.cpu();classifier=classifier.cpu()
    return cv2,np,torch,python_speech_features,network,classifier


def iou(a,b):
    x=max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]))
    y=max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))
    area=x*y
    return area/max(1e-9,a[2]*a[3]+b[2]*b[3]-area)


def analysis_profile(info,focus='auto',selection=None):
    from backend.subject_tracking import context_classes
    if selection:return 'manual'
    if focus=='auto' and context_classes(info.get('context',''))-{'person'}:return 'subjects'
    if focus in ('left','right','both'):return 'visual'
    return 'full'

def analysis_key(info,focus='auto',selection=None):
    profile=analysis_profile(info,focus,selection)
    names=[] if profile=='manual' else ['yolox.onnx']+(['yunet.onnx'] if profile in ('visual','full') else [])+(['light_asd.model'] if profile=='full' else [])
    weights=[]
    for name in names:
        path=model_folder()/name
        weights.append([str(path.resolve()),path.stat().st_mtime_ns,path.stat().st_size] if path.is_file() else [name,'missing'])
    import cv2
    data={'version':VERSION,'runtime':cv2.__version__,'profile':profile,'device':os.getenv('CASCADE_REFRAME_DEVICE','cpu') if profile=='full' else 'not used','selection':selection,'context':info.get('context','') if profile!='manual' else '','source_revision':info.get('source_revision'),
          'width':info['width'],'height':info['height'],'duration':info['duration'],'weights':weights}
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()



@lru_cache(maxsize=8)
def _face_detector(path,mtime,size,width,height):
    import cv2
    return cv2.FaceDetectorYN.create(path,'',(width,height),.75,.3,100),RLock()


def analyze(source,info,progress=lambda value,message:None,selection=None,focus='auto'):
    import cv2 as cv
    import numpy as np
    # Bound OpenCV's worker pool for these small analysis frames; avoid 14-way overhead.
    cv.setNumThreads(int(os.getenv('CASCADE_REFRAME_THREADS','4')))
    metrics=Timings();started=perf_counter();profile=analysis_profile(info,focus,selection)
    need_faces=profile in ('full','visual');need_speaker=profile=='full'
    torch=features=network=head=None
    duration=info['duration']
    if duration>300:
        raise ValueError('Analyze clips up to five minutes. Trim or generate a shorter clip before Auto Reframe.')
    progress(.03,'Decoding video and original audio locally…')
    with tempfile.TemporaryDirectory(prefix='cascade-reframe-') as directory:
        normalized=Path(directory)/'analysis.mp4'
        offset=math.floor(selection['t']*FPS)/FPS if selection else 0.
        seek_args=['-ss',str(offset)] if offset else []
        # Analysis resampling never changes the original media or its exported timing.
        metrics.call('video_preparation',subprocess.run,['ffmpeg','-nostdin','-v','error','-y',*seek_args,'-i',str(source),'-an','-vf',"scale='min(640,iw)':-2,fps=25",'-c:v','libx264','-preset','ultrafast',str(normalized)],check=True,capture_output=True,timeout=180)
        pcm=np.zeros(0,dtype=np.float32);has_audio=False;mfcc=None
        if need_speaker and info.get('has_audio',True):
            audio=metrics.call('audio_preparation',subprocess.run,['ffmpeg','-nostdin','-v','error','-i',str(source),'-vn','-ac','1','-ar','16000','-f','s16le','-'],capture_output=True,timeout=120)
            pcm=np.frombuffer(audio.stdout,dtype=np.int16).astype(np.float32) if audio.returncode==0 else pcm
            has_audio=len(pcm)>0 and float(np.max(np.abs(pcm)))>20
        if len(pcm)<int(duration*16000)+1600:pcm=np.pad(pcm,(0,max(0,int(duration*16000)+1600-len(pcm))))
        energy_threshold=max(35.,float(np.percentile(np.abs(pcm),20))*1.5)
        capture=cv.VideoCapture(str(normalized))
        width=int(capture.get(cv.CAP_PROP_FRAME_WIDTH));height=int(capture.get(cv.CAP_PROP_FRAME_HEIGHT))
        detector=None;detector_lock=None
        if need_faces:
            path=model_folder()/'yunet.onnx'
            if not path.is_file():raise ValueError('Face model is missing. Run python3 scripts/setup_reframe.py.')
            detector,detector_lock=metrics.call('face_model_load',_face_detector,str(path.resolve()),path.stat().st_mtime_ns,path.stat().st_size,width,height)
        from backend.subject_tracking import Subjects,RegionTracker
        subjects=metrics.call('object_model_load',Subjects,model_folder()/'yolox.onnx',metrics) if profile!='manual' else None;region=RegionTracker(selection) if selection else None
        object_frames={}
        tracks={};next_id=0;frame_index=round(offset*FPS);observations=[{'t':round(i/FPS,4),'audio':False,'subjects':[],'region':None,'cut':False,'faces':[]} for i in range(frame_index)];batch=[];previous_gray=None
        def infer_batch(batch):
            nonlocal torch,features,network,head,mfcc
            if not batch:return
            start=batch[0][0];length=len(batch)
            audio_features=None
            usable=need_speaker and has_audio and max(len(faces) for _,faces in batch)>1 and any(sum(any(f['id']==ident for f in faces) for _,faces in batch)>=12 for ident in {f['id'] for _,faces in batch for f in faces})
            if usable:
                if network is None:
                    _,_,torch,features,network,head=metrics.call('speaker_model_load',models)
                    mfcc=metrics.call('audio_features',features.mfcc,pcm,16000,numcep=13,winlen=.025,winstep=.010).astype(np.float32)
                audio_features=mfcc[start*4:(start+length)*4]
            if usable and len(audio_features)<length*4:audio_features=np.pad(audio_features,((0,length*4-len(audio_features)),(0,0)),mode='edge')
            audio_embeddings={}
            for ident in ({face['id'] for _,faces in batch for face in faces} if usable else set()):
                present={index:next((f for f in faces if f['id']==ident),None) for index,faces in batch}
                valid=[f for f in present.values() if f]
                # Short fragments cannot establish audio-visual synchrony.
                if len(valid)<12:continue
                crops=np.stack([present[index]['crop'] if present[index] else valid[0]['crop'] for index,_ in batch])
                # Pad temporal inputs to a multiple of four video frames for encoder alignment.
                padded=4*math.ceil(length/4);crops=np.pad(crops,((0,padded-length),(0,0),(0,0)),mode='edge')
                af=np.pad(audio_features,((0,padded*4-len(audio_features)),(0,0)),mode='edge')
                inference_start=perf_counter()
                def run_inference(network,head):
                    device=next(network.parameters()).device
                    with torch.inference_mode():
                        key=(id(network),str(device))
                        if key not in audio_embeddings:audio_embeddings[key]=network.forward_audio_frontend(torch.from_numpy(af).unsqueeze(0).to(device))
                        a=audio_embeddings[key]
                        v=network.forward_visual_frontend(torch.from_numpy(crops.astype(np.float32)).unsqueeze(0).to(device))
                        out=head(network.forward_audio_visual_backend(a,v))
                        return torch.softmax(out,dim=-1)[:,1].cpu().numpy()[:length]
                try:probability=run_inference(network,head)
                except (RuntimeError,NotImplementedError):
                    device=next(network.parameters()).device.type
                    if device=='cpu':raise
                    _failed_devices.add(device)
                    path=model_folder()/'light_asd.model'
                    _,_,_,_,network,head=_speaker_models(str(path.resolve()),path.stat().st_mtime_ns,path.stat().st_size,'cpu')
                    probability=run_inference(network,head)
                metrics.seconds['active_speaker']+=perf_counter()-inference_start;metrics.calls['active_speaker']+=1
                for offset,(index,_) in enumerate(batch):
                    face=present[index]
                    if face:
                        face['score']=float(probability[offset]) if has_audio else 0.
            for index,faces in batch:
                segment=pcm[index*640:(index+1)*640]
                energy=float(np.sqrt(np.mean(segment**2))) if len(segment) else 0
                observations.append({'t':round(index/FPS,4),'audio':energy>energy_threshold,
                                     **object_frames.pop(index), 'faces':[{k:v for k,v in face.items() if k!='crop'} for face in faces]})
        try:
            while True:
                ok,image=metrics.call('decode',capture.read)
                if not ok:break
                if subjects:objects,cut=metrics.call('subject_tracking_including_detection',subjects.update,image,frame_index)
                else:
                    gray=cv.cvtColor(image,cv.COLOR_BGR2GRAY)
                    cut=previous_gray is not None and float(np.mean(cv.absdiff(cv.resize(gray,(64,36)),cv.resize(previous_gray,(64,36)))))>48
                    previous_gray=gray;objects=[]
                if cut:tracks.clear()
                manual=metrics.call('manual_tracking',region.update,image,frame_index/FPS,cut) if region else None
                object_frames[frame_index]={'subjects':objects,'region':manual,'cut':cut}
                detections=None
                if detector:
                    with detector_lock:_,detections=metrics.call('face_detection',detector.detect,image)
                face_start=perf_counter()
                faces=[];used=set()
                for row in sorted([] if detections is None else detections,key=lambda r:float(r[2]*r[3]),reverse=True)[:6]:
                    box=[float(value) for value in row[:4]]
                    candidates=[(iou(box,track['box']),ident) for ident,track in tracks.items() if frame_index-track['seen']<12 and ident not in used]
                    overlap,ident=max(candidates,default=(0,-1))
                    if overlap<.15:ident=next_id;next_id+=1
                    used.add(ident);previous=tracks.get(ident)
                    # Low-pass detector boxes before model crops, reducing artificial lip motion.
                    smooth=[.65*x+.35*y for x,y in zip(box,previous['box'])] if previous else box
                    tracks[ident]={'box':smooth,'seen':frame_index}
                    x,y,w,h=smooth;half=max(w,h)/2;cx=x+w/2;cy=y+h/2
                    pad=int(half*1.8)+2;padded=cv.copyMakeBorder(image,pad,pad,pad,pad,cv.BORDER_CONSTANT,value=(110,110,110))
                    crop=padded[int(cy-half+pad):int(cy+half*1.8+pad),int(cx-half*1.4+pad):int(cx+half*1.4+pad)]
                    if not crop.size:continue
                    crop=cv.cvtColor(cv.resize(crop,(224,224)),cv.COLOR_BGR2GRAY)[56:168,56:168]
                    faces.append({'id':ident,'box':[x/width,y/height,w/width,h/height],'score':0.,'crop':crop})
                metrics.seconds['face_tracking']+=perf_counter()-face_start;metrics.calls['face_tracking']+=1
                batch.append((frame_index,faces));frame_index+=1
                if frame_index%25==0:progress(min(.95,.1+.85*frame_index/FPS/duration),'Tracking '+('selected region' if region else 'subjects')+' locally…')
                if len(batch)==100:
                    infer_batch(batch);batch=[]
                    progress(min(.95,.1+.85*frame_index/FPS/duration),'Tracking faces and scoring audio-visual speaker activity…')
            infer_batch(batch)
        finally:capture.release()
        if not observations:raise ValueError('No video frames could be analyzed. Check the source clip and retry.')
        no_faces=not any(row['faces'] for row in observations)
        metrics.seconds['total']=perf_counter()-started;metrics.calls['total']=1
        return {'version':VERSION,'profile':profile,'speaker_device':str(next(network.parameters()).device) if network is not None else 'not needed','device_fallbacks':sorted(_failed_devices),'timings':metrics.export(),'duration':duration,'width':info['width'],'height':info['height'],'has_audio':has_audio,'frames':observations,
                'context':info.get('context',''),'selection':selection,
                'method':'YOLOX COCO + appearance/optical flow tracks; YuNet + Light-ASD; optional MIL region',
                'warning':('Subject-only analysis; speaker inference was not needed.' if not need_speaker else 'No usable faces detected. Holding a stable centered crop; no speaker tracking is claimed.' if no_faces and not any(r['subjects'] for r in observations) and not selection else '' if has_audio else 'No usable audio. Visual subject tracking only; speaker identity cannot be established.')}


def plan(analysis,geometry,focus='speaker',fallback=(.5,.5)):
    """Conservative hysteresis + bounded acceleration; no zoom, no invented speaker."""
    sw,sh=geometry['scaledWidth'],geometry['scaledHeight'];w,h=geometry['width']/sw,geometry['height']/sh
    current=None;candidate=None;candidate_since=0.;last_switch=-10.;anchor=None
    from backend.subject_tracking import context_classes
    preferred=context_classes(analysis.get('context',''));subject_id=None;body_id=None;body_seen=-10.;subject_scene=None
    position=list(fallback);velocity=[0.,0.];points=[];last_t=0.;uncertain=0;confirmed=0
    for row in analysis['frames']:
        t=row['t'];dt=min(.1,max(.001,t-last_t));last_t=t
        faces=row['faces'];selected=[];is_subject=False
        objects=row.get('subjects',[])
        if row.get('cut'):
            current=None;candidate=None;anchor=None;subject_id=None;body_id=None;velocity=[0.,0.]
        # Explicit region remains exclusive even when lost; never switch to an unrelated detection.
        if analysis.get('selection'):
            selected=[row['region']] if row.get('region') else [];is_subject=True
        elif focus=='auto' and (preferred-{'person'} or not faces):
            if subject_id is None:
                eligible=[o for o in objects if o['confidence']>=.5 and (not preferred or o['label'] in preferred)]
                if eligible:
                    chosen=max(eligible,key=lambda o:((o['label'] in preferred),o['confidence']*math.sqrt(o['box'][2]*o['box'][3])))
                    subject_id=chosen['id']
            selected=[o for o in objects if o['id']==subject_id and o['confidence']>=.25];is_subject=True
        elif focus in ('left','right'):
            if anchor is None and faces:anchor=sorted(faces,key=lambda f:f['box'][0],reverse=focus=='right')[0]['id']
            selected=[f for f in faces if f['id']==anchor]
        elif focus=='both':selected=faces
        elif len(faces)==1:
            # A disappearing speaker is not evidence that the remaining face is speaking.
            if current is not None and faces[0]['id']!=current and body_id is not None and t-body_seen<1.2:
                selected=[]
            else:selected=faces;current=faces[0]['id']
        elif faces:
            ranked=sorted(faces,key=lambda f:f['score'],reverse=True)
            reliable=row['audio'] and ranked[0]['score']>=.8 and ranked[1]['score']<.65
            wanted=ranked[0]['id'] if reliable else None
            if reliable:
                confirmed+=1
                if wanted!=candidate:candidate=wanted;candidate_since=t
                if wanted!=current and t-candidate_since>=.65 and t-last_switch>=1.4:current=wanted;last_switch=t
                selected=[f for f in faces if f['id']==current]
            else:
                candidate=None;uncertain+=1;selected=faces  # Include all only if feasible; otherwise hold.
        # Associate the selected speaker's face with its person body for a brief face occlusion.
        if not is_subject and len(selected)==1:
            face=selected[0];fx,fy,fw,fh=face['box']
            bodies=[o for o in objects if o['label']=='person' and o['box'][0]<=fx+fw/2<=o['box'][0]+o['box'][2] and o['box'][1]<=fy+fh/2<=o['box'][1]+o['box'][3]]
            if bodies:body_id=min(bodies,key=lambda o:o['box'][2]*o['box'][3])['id'];body_seen=t
        elif not is_subject and not selected and body_id is not None and t-body_seen<1.2:
            selected=[o for o in objects if o['id']==body_id and o['confidence']>=.25];is_subject=bool(selected)
        if selected:
            left=min(f['box'][0]-.25*f['box'][2] for f in selected);right=max(f['box'][0]+1.25*f['box'][2] for f in selected)
            top=min(f['box'][1]-(.12 if is_subject else .45)*f['box'][3] for f in selected);bottom=max(f['box'][1]+(1.12 if is_subject else 1.25)*f['box'][3] for f in selected)
            fits=len(selected)==1 or (right-left<=w and bottom-top<=h)
            if fits:
                center=[(left+right)/2,(top+bottom)/2]
                if len(selected)==1 and not is_subject:center[1]=top+h*.42  # Headroom; face sits above center.
                target=[max(0.,min(1.,(center[0]-w/2)/max(1e-9,1-w))),max(0.,min(1.,(center[1]-h/2)/max(1e-9,1-h)))]
                if not points:position=target[:]
                for axis in (0,1):
                    desired=max(-.65,min(.65,(target[axis]-position[axis])*2.6))
                    velocity[axis]+=max(-1.3*dt,min(1.3*dt,desired-velocity[axis]))
                    position[axis]=max(0.,min(1.,position[axis]+velocity[axis]*dt))
            else:velocity=[0.,0.]
        else:velocity=[0.,0.]
        if not points or t-points[-1]['t']>=.199:
            points.append({'t':t,'x':round(position[0],6),'y':round(position[1],6)})
    if not points:raise ValueError('No tracking data is available.')
    if points[-1]['t']<analysis['duration']:points.append({**points[-1],'t':analysis['duration']})
    warnings=[analysis.get('warning','')]
    if analysis.get('selection'):warnings.append('Following your selected region from its selection time; holding on loss or a scene cut. Reselect to recover.')
    elif focus=='auto':warnings.append('A fixed Fill crop may not fit a large subject; use Fit for the full scene. Auto uses prompt category matches and scene detections, with a locked subject per shot. Unsupported or uncertain subjects hold framing.')
    if focus=='speaker' and not confirmed:warnings.append('No confident multi-person speaker match. Following a sole visible person; otherwise keeping both in frame when possible or holding the last reliable crop.')
    if focus=='both':warnings.append('Both people are included only where the fixed Fill crop can fit them with headroom; otherwise framing holds. Use Fit for the entire scene.')
    return {'points':points,'warning':' '.join(filter(None,warnings)),'confirmed_frames':confirmed,'uncertain_frames':uncertain}


def expression(points,axis,extent,offset=0):
    """Same linear interpolation as editor_state.reframeAt; source clip time."""
    terms=[str(points[0][axis]*extent)]
    for a,b in zip(points,points[1:]):
        delta=(b[axis]-a[axis])*extent
        if abs(delta)<.01:continue
        terms.append(f"({delta:.6f})*clip((t+{offset:.6f}-{a['t']:.6f})/{b['t']-a['t']:.6f},0,1)")
    return '2*floor(('+ '+'.join(terms)+')/2+0.5)'
