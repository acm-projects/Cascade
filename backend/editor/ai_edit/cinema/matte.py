"""Person cut-outs for the words that sit behind the speaker, the outline reveal and the glow.

Uses U²-Net human segmentation (Apache-2.0, from the open-source rembg project) through ONNX Runtime
on the CPU. The model (176 MB) is downloaded once into ~/.cache/cascade on first use; without it,
or without onnxruntime, these moments simply render as front captions."""
import logging
import os
import urllib.request
from pathlib import Path

import numpy as np

LOG = logging.getLogger(__name__)
URL = 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx'
SIZE = 320


def model_path():
    for candidate in (os.getenv('CASCADE_MATTE_MODEL', ''), Path(__file__).parent/'models'/'u2net_human_seg.onnx',
                      Path.home()/'.cache'/'cascade'/'u2net_human_seg.onnx'):
        if candidate and Path(candidate).is_file(): return Path(candidate)
    return None


def ensure():
    found = model_path()
    if found: return found
    target = Path.home()/'.cache'/'cascade'/'u2net_human_seg.onnx'
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix('.part')
        urllib.request.urlretrieve(URL, temp)
        if temp.stat().st_size < 50_000_000: raise ValueError('incomplete download')
        temp.replace(target)
        return target
    except Exception:
        LOG.warning('person matte model unavailable', exc_info=True)
        return None


class Matter:
    """matte(frame) -> float32 (H, W) in 0..1, smoothed over time so edges do not flicker."""
    def __init__(self):
        import onnxruntime as ort
        path = ensure()
        if not path: raise RuntimeError('no matte model')
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, (os.cpu_count() or 2)-1)
        self.session = ort.InferenceSession(str(path), options, providers=['CPUExecutionProvider'])
        self.name = self.session.get_inputs()[0].name
        self.previous = None

    def reset(self):
        self.previous = None

    def __call__(self, frame):
        import cv2
        h, w = frame.shape[:2]
        x = cv2.resize(frame, (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(np.float32)/255.
        x = (x-np.array([.485, .456, .406], np.float32))/np.array([.229, .224, .225], np.float32)
        out = self.session.run(None, {self.name: x.transpose(2, 0, 1)[None]})[0][0, 0]
        out = (out-out.min())/(out.max()-out.min()+1e-6)
        out = cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR)
        out = np.clip((out-.25)/.55, 0, 1)  # firm up the edge
        if self.previous is not None and self.previous.shape == out.shape:
            out = .55*out+.45*self.previous
        self.previous = out
        return out.astype(np.float32)


def available():
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False
    return ensure() is not None
