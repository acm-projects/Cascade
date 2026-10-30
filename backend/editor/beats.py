"""Local measured onset/tempo analysis. Quiet/arrhythmic tracks do not get fake grids."""
from functools import lru_cache
from pathlib import Path
import subprocess
import numpy as np

@lru_cache(maxsize=64)
def _analyze(path, size, modified):
    raw=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',path,'-t','120','-ac','1','-ar','22050','-f','f32le','-'],capture_output=True,check=True,timeout=30).stdout
    samples=np.frombuffer(raw,dtype='<f4')
    if len(samples)<22050 or float(np.sqrt(np.mean(samples**2)))<.001:
        return {'beats':[],'bpm':None,'confidence':0,'method':'spectral-flux/onset autocorrelation'}
    hop=256;window=1024
    frames=np.lib.stride_tricks.sliding_window_view(samples,window)[::hop]
    spectrum=np.abs(np.fft.rfft(frames*np.hanning(window),axis=1))
    # Percussive bass flux plus broadband attacks; musical content remains untouched.
    flux=np.maximum(0,np.diff(spectrum,axis=0,prepend=spectrum[:1])).sum(axis=1)
    low=spectrum[:,1:10].sum(axis=1)
    energy=np.sqrt(np.mean(frames**2,axis=1))
    novelty=flux/(np.max(flux)+1e-9)+np.maximum(0,np.diff(low,prepend=low[:1]))/(np.max(low)+1e-9)
    novelty+=.4*np.maximum(0,np.diff(energy,prepend=energy[:1]))/(np.max(energy)+1e-9)
    novelty=np.maximum(0,novelty-np.median(novelty));rate=22050/hop
    lo=round(rate*60/180);hi=min(round(rate*60/75),len(novelty)//2)
    if hi<=lo:return {'beats':[],'bpm':None,'confidence':0,'method':'spectral-flux/onset autocorrelation'}
    centered=novelty-novelty.mean();den=float(np.dot(centered,centered))+1e-12
    correlations=[float(np.dot(centered[:-lag],centered[lag:]))/den for lag in range(lo,hi+1)]
    lag=lo+int(np.argmax(correlations));confidence=max(0,min(1,max(correlations)))
    if confidence<.18 or np.max(novelty)<.05:
        return {'beats':[],'bpm':None,'confidence':round(confidence,3),'method':'spectral-flux/onset autocorrelation'}
    # Best measured phase over the inferred period, using real onset strengths.
    scores=[float(novelty[phase::lag].sum()) for phase in range(lag)]
    phase=int(np.argmax(scores));period=lag/rate
    peaks=[]
    for position in range(phase,len(novelty),lag):
        left=max(0,position-round(.06*rate));right=min(len(novelty),position+round(.06*rate)+1)
        peak=left+int(np.argmax(novelty[left:right]))
        if novelty[peak]>.08:peaks.append(round(peak/rate+window/(2*22050),4))
    return {'beats':sorted(set(peaks)),'bpm':round(60/period,2),'confidence':round(confidence,3),'method':'spectral-flux/onset autocorrelation'}

def analyze(path):
    p=Path(path);stat=p.stat()
    return _analyze(str(p),stat.st_size,stat.st_mtime_ns)

def loop_beats(analysis, asset_duration, output_duration, offset=0):
    if not analysis['beats']:return []
    result=[];cycle=-1
    while cycle*asset_duration<output_duration+offset:
        result.extend(round(t+cycle*asset_duration-offset,4) for t in analysis['beats'] if 0<=t+cycle*asset_duration-offset<=output_duration)
        cycle+=1
    return sorted(set(result))[:3000]
