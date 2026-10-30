"""Private owner/clip-scoped audio, including real procedurally synthesized assets.
No remote URLs or arbitrary filesystem paths are accepted from clients or models.
"""
import array
import hashlib
import json
import math
import re
import subprocess
import tempfile
import threading
import uuid
import wave
from pathlib import Path
from fastapi import HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from backend.broll import write_json
from .storage import draft_path, selected

LOCK = threading.RLock()
CATALOG = [
    ('Reel pulse', 'music', ['high', 'energy', 'reel', 'upbeat', 'beat', 'pulse'], 32, 'reel'),
    ('Tension pulse', 'music', ['dramatic', 'tension', 'dark', 'fight', 'suspense'], 30, 'pulse'),
    ('Quiet reflection', 'music', ['calm', 'emotional', 'soft', 'background'], 30, 'pad'),
    ('Playful plucks', 'music', ['comic', 'funny', 'playful', 'teddy'], 30, 'pluck'),
    ('Impact hit', 'sfx', ['impact', 'punch', 'hit', 'dramatic'], .55, 'hit'),
    ('Air whoosh', 'sfx', ['whoosh', 'transition', 'zoom'], .65, 'whoosh'),
    ('Bell accent', 'sfx', ['bell', 'ding', 'reaction', 'punchline', 'funny'], .6, 'bell'),
]

def store(pid, jid, index, user):
    selected(pid, jid, index, user)
    return AudioStore(draft_path(pid,jid,index,user).parent/'audio'/(jid+'-'+str(index)))

class AudioStore:
    def __init__(self, folder): self.folder = Path(folder)
    def registry(self):
        path = self.folder/'assets.json'
        return json.loads(path.read_text()) if path.is_file() else {}
    def entry(self, ident):
        if not re.fullmatch(r'aud-[a-f0-9]{32}', ident or ''):
            raise HTTPException(422, 'Invalid audio asset ID.')
        item = self.registry().get(ident)
        if not item: raise HTTPException(422, 'Audio asset is unavailable for this clip. Select or upload a track again.')
        return item
    def media(self, ident):
        self.entry(ident)
        path = self.folder/(ident+'.wav')
        if not path.is_file(): raise HTTPException(409, 'Audio file is missing. Restore the uploaded asset or choose another track.')
        return path
    def verify(self, state):
        for segment in state.audio:
            item = self.entry(segment.asset_id); self.media(segment.asset_id)
            if segment.offset >= item['duration'] or (not segment.loop and segment.offset+segment.duration > item['duration']+.02):
                raise HTTPException(422, 'Audio trim exceeds the selected asset. Shorten it or enable looping.')
    def library(self):
        with LOCK:
            items = self.registry()
            for name, kind, tags, duration, sound in CATALOG:
                ident='aud-'+hashlib.sha256(('cascade-synth-v1:'+name).encode()).hexdigest()[:32]
                if ident not in items or not (self.folder/(ident+'.wav')).is_file():
                    self.folder.mkdir(parents=True, exist_ok=True)
                    synth(self.folder/(ident+'.wav'), duration, sound)
                    items[ident]={'id':ident,'name':name,'kind':kind,'tags':tags,'duration':duration,'license':'Cascade procedural synthesis; no third-party recording','source':'synthesized'}
            write_json(self.folder/'assets.json', items)
            return list(items.values())
    def upload(self, file, name, kind):
        self.folder.mkdir(parents=True, exist_ok=True)
        ident='aud-'+uuid.uuid4().hex
        try:
            with tempfile.TemporaryDirectory(prefix='cascade-audio-upload-') as directory:
                source=Path(directory)/'input'
                size=0
                with source.open('wb') as target:
                    while chunk:=file.file.read(1024*1024):
                        size+=len(chunk)
                        if size>50*1024*1024: raise HTTPException(413, 'Audio uploads must be at most 50 MB.')
                        target.write(chunk)
                try:
                    probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(source)],capture_output=True,check=True,timeout=20)
                    duration=float(json.loads(probe.stdout)['format']['duration'])
                    if not math.isfinite(duration) or not .05<=duration<=1200: raise ValueError()
                    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(source),'-vn','-map','0:a:0','-ac','2','-ar','48000','-c:a','pcm_s16le',str(self.folder/(ident+'.wav'))],capture_output=True,check=True,timeout=90)
                except (ValueError,KeyError,OSError,subprocess.SubprocessError):
                    (self.folder/(ident+'.wav')).unlink(missing_ok=True)
                    raise HTTPException(422, 'Upload a valid audio file, at most 20 minutes long. FFmpeg must be installed.') from None
                item={'id':ident,'name':name[:100], 'kind':kind, 'tags':['uploaded'], 'duration':duration,'license':'User-provided; use only audio you have permission to use','source':'uploaded'}
                with LOCK:
                    items=self.registry();items[ident]=item;write_json(self.folder/'assets.json',items)
                return item
        finally: file.file.close()

def synth(path, duration, sound):
    rate=24000;data=array.array('h')
    notes=[220,261.63,329.63,293.66,196,246.94,293.66,261.63]
    for i in range(round(duration*rate)):
        t=i/rate
        if sound=='reel':
            beat=t%.5;hat=t%.25
            kick=.36*math.exp(-beat*24)*math.sin(2*math.pi*(48*t+2*math.exp(-beat*18)))
            percussion=.1*math.exp(-hat*90)*math.sin(2*math.pi*5700*t)
            chord=sum(.035*math.sin(2*math.pi*f*t) for f in [130.81,164.81,196])* (.45+.55*min(1,beat*6))
            value=kick+percussion+chord
        elif sound=='pulse':
            pulse=math.exp(-((t%(.5)))*16)
            value=.19*math.sin(2*math.pi*55*t)+.12*pulse*math.sin(2*math.pi*110*t)
        elif sound=='pad': value=sum(.075*math.sin(2*math.pi*f*t) for f in [130.81,164.81,196])*min(1,t/1.5)
        elif sound=='pluck': value=.35*math.exp(-(t%.25)*18)*math.sin(2*math.pi*notes[int(t/.25)%8]*t)
        elif sound=='hit': value=.65*math.exp(-t*12)*math.sin(2*math.pi*(110*t-50*t*t))
        elif sound=='whoosh': value=.35*math.sin(2*math.pi*(330*t+1800*t*t))*math.sin(math.pi*t/duration)**2
        else: value=.4*math.exp(-t*8)*(math.sin(2*math.pi*1100*t)+.25*math.sin(2*math.pi*2200*t))
        value*=min(1,t/.01,(duration-t)/.02)
        data.append(round(max(-1,min(1,value))*32700))
    import sys
    if sys.byteorder!='little': data.byteswap()
    with wave.open(str(path),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(rate);output.writeframes(data.tobytes())

def list_assets(pid: str, jid: str, index: int, request: Request):
    return {'assets':store(pid,jid,index,request.state.user_id).library()}

def upload_asset(pid: str, jid: str, index: int, request: Request, audio: UploadFile=File(...), name: str=Form('My music',max_length=100), kind: str=Form('music')):
    if kind not in ('music','sfx'): raise HTTPException(422, 'Choose music or sfx.')
    return store(pid,jid,index,request.state.user_id).upload(audio,name.strip() or 'My music',kind)

def asset_media(pid: str, jid: str, index: int, asset_id: str, request: Request):
    return FileResponse(store(pid,jid,index,request.state.user_id).media(asset_id),media_type='audio/wav',headers={'Cache-Control':'no-store'})
