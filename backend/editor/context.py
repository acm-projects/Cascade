"""Local scene-boundary hints, not visual-semantic or beat-detection claims."""
from functools import lru_cache
import re
import subprocess
from .storage import media

@lru_cache(maxsize=32)
def _cuts(path, size, modified):
    try:
        response=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-i',path,'-an','-vf',"scale=160:-2,select='gt(scene,0.3)',showinfo",'-f','null','-'],capture_output=True,text=True,timeout=15)
        return [float(t) for t in re.findall(r'pts_time:([\d.]+)',response.stderr)][:40]
    except (OSError,subprocess.SubprocessError):return []

def scene_hints(jid, clip):
    with media(jid,clip) as source:
        st=source.stat()
        return {'scene_boundaries':_cuts(str(source),st.st_size,st.st_mtime_ns),
                'limitation':'Local scene-cut detection only; no visual-semantic recognition or exact musical beat analysis.'}
