"""Whole-frame film looks for documentary/memorial edits: B&W, sepia or warm tone with grain,
vignette and a gentle projector flicker. Local NumPy/OpenCV only."""
from functools import lru_cache

TONES = {'bw': (1.0, 1.0, 1.0), 'sepia': (1.07, .93, .74), 'warm': (1.05, .98, .9)}


@lru_cache(maxsize=8)
def _vignette(w, h):
    import numpy as np
    y, x = np.ogrid[-1:1:h*1j, -1:1:w*1j]
    return np.clip(1.15-.55*(x*x+y*y), .45, 1).astype(np.float32)[..., None]


def apply_looks(frame, t, events, frame_number):
    import numpy as np
    h, w = frame.shape[:2]
    out = frame
    for _, event in events:
        if not 0 <= t-event.start < event.duration: continue
        rng = np.random.default_rng(frame_number)
        gray = (out @ np.array([.299, .587, .114], np.float32))[..., None]
        if event.tone == 'warm':
            out = out*.75+gray*.25
        else:
            out = np.repeat(gray, 3, axis=2)
        out = out*np.array(TONES[event.tone], np.float32)
        out = (out-128)*1.08+128  # a little archival contrast
        out = out*_vignette(w, h)*(1+.025*event.strength*rng.uniform(-1, 1))
        out = out+rng.normal(0, 5*event.strength, (h, w, 1)).astype(np.float32)
    return out
