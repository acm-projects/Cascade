"""Local subject mattes for stylized edits: YOLOX boxes prompt SAM 2.1 (tiny), cached on disk.

Everything runs on this machine (Apple GPU when available). The only network use is the
one-time download of the public SAM 2.1 weights from Hugging Face; no paid service is used.
Masks are sampled at MASK_FPS and interpolated in time by the renderer.
"""
import hashlib
import logging
import threading
from pathlib import Path

LOG = logging.getLogger(__name__)
MODEL_ID = 'facebook/sam2.1-hiera-tiny'
MASK_FPS = 6
MASK_HEIGHT = 360
_model_lock = threading.Lock()
_cache_locks = {}
_cache_locks_guard = threading.Lock()
_loaded = {}
_gpu_lock = threading.Lock()  # one matte job at a time finishes sooner than several sharing the GPU
PROGRESS = {}  # source path -> (done, total) while mattes are being computed


def _device():
    import torch
    return 'mps' if torch.backends.mps.is_available() else 'cpu'


def _sam():
    with _model_lock:
        if 'sam' not in _loaded:
            from transformers import Sam2Model, Sam2Processor
            device = _device()
            _loaded['sam'] = (Sam2Model.from_pretrained(MODEL_ID).to(device).eval(),
                              Sam2Processor.from_pretrained(MODEL_ID), device)
        return _loaded['sam']


def _detector():
    from backend.reframe import model_folder
    from backend.subject_tracking import Subjects
    path = model_folder()/'yolox.onnx'
    return Subjects(path) if path.is_file() else None


def _iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    w = max(0, min(ax+aw, bx+bw)-max(ax, bx)); h = max(0, min(ay+ah, by+bh)-max(ay, by))
    union = aw*ah+bw*bh-w*h
    return w*h/union if union else 0


def choose_subjects(detections, previous):
    """Main subject(s): people first, the largest plus any person at least 30% its size."""
    people = [d for d in detections if d['label'] == 'person' and d['confidence'] > .35]
    pool = people or [d for d in detections if d['confidence'] > .5 and d['box'][2]*d['box'][3] > .03]
    if not pool:
        return previous
    def score(d):
        bonus = max((_iou(d['box'], p) for p in previous), default=0)
        return d['box'][2]*d['box'][3]*d['confidence']*(1+bonus)
    pool = sorted(pool, key=score, reverse=True)
    top = pool[0]['box'][2]*pool[0]['box'][3]
    return [d['box'] for d in pool[:4] if d['box'][2]*d['box'][3] >= top*.3]


def _cache_lock(key):
    with _cache_locks_guard:
        return _cache_locks.setdefault(key, threading.Lock())


class Mattes:
    """Subject mattes for one source file, keyed by sample index (index / MASK_FPS seconds)."""

    def __init__(self, source, cache_dir):
        source = Path(source)
        st = source.stat()
        self.source = source
        self.key = hashlib.sha256(f'{source.name}:{st.st_size}:{st.st_mtime_ns}:{MODEL_ID}:{MASK_FPS}'.encode()).hexdigest()[:24]
        self.folder = Path(cache_dir)/self.key
        self.folder.mkdir(parents=True, exist_ok=True)

    def path(self, index):
        return self.folder/f'{index:05d}.png'

    def missing(self, start, end):
        return [i for i in range(int(start*MASK_FPS), int(end*MASK_FPS)+2) if not self.path(i).is_file()]

    def ensure(self, spans, progress=None):
        """Compute every missing sample covering the (start, end) spans."""
        import cv2
        import numpy as np
        import torch
        from PIL import Image
        wanted = sorted({i for a, b in spans for i in self.missing(max(0, a-.1), b+.1)})
        if not wanted:
            return
        PROGRESS[str(self.source)] = (0, len(wanted))
        with _cache_lock(self.key), _gpu_lock:
            wanted = [i for i in wanted if not self.path(i).is_file()]
            model, processor, device = _sam()
            detector = _detector()
            capture = cv2.VideoCapture(str(self.source))
            previous = []
            try:
                for done, index in enumerate(wanted):
                    capture.set(cv2.CAP_PROP_POS_MSEC, index*1000/MASK_FPS)
                    ok, frame = capture.read()
                    if not ok:
                        cv2.imwrite(str(self.path(index)), np.full((MASK_HEIGHT, MASK_HEIGHT), 255, np.uint8))
                        continue
                    h, w = frame.shape[:2]
                    small = cv2.resize(frame, (max(2, round(w*540/h)), 540)) if h > 540 else frame
                    sh, sw = small.shape[:2]
                    boxes = choose_subjects(detector.detect(small) if detector else [], previous)
                    previous = boxes
                    out_size = (max(2, round(w*MASK_HEIGHT/h)), MASK_HEIGHT)
                    if not boxes:
                        # No subject found: a full matte leaves the shot untouched rather than blank.
                        matte = np.full((out_size[1], out_size[0]), 255, np.uint8)
                    else:
                        pixels = [[x*sw, y*sh, (x+bw)*sw, (y+bh)*sh] for x, y, bw, bh in boxes]
                        with torch.no_grad():
                            inputs = processor(images=Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)),
                                               input_boxes=[pixels], return_tensors='pt').to(device)
                            result = model(**inputs, multimask_output=False)
                            masks = processor.post_process_masks(result.pred_masks.cpu(), inputs['original_sizes'].cpu(), binarize=False)[0]
                        probability = masks.float()
                        if probability.min() < 0 or probability.max() > 1:
                            probability = probability.sigmoid()
                        union = probability.amax(dim=(0, 1)).numpy() if probability.ndim == 4 else probability.amax(dim=0).numpy()
                        matte = cv2.resize((union*255).astype(np.uint8), out_size, interpolation=cv2.INTER_AREA)
                    cv2.imwrite(str(self.path(index)), matte)
                    PROGRESS[str(self.source)] = (done+1, len(wanted))
                    if progress:
                        progress(done+1, len(wanted))
            finally:
                capture.release()
                PROGRESS.pop(str(self.source), None)

    def at(self, seconds, width, height):
        """Matte (float32 0..1, height x width) at a time, linearly interpolated between samples."""
        import cv2
        import numpy as np
        position = max(0.0, seconds*MASK_FPS)
        low = int(position); weight = position-low
        def load(i):
            image = cv2.imread(str(self.path(i)), cv2.IMREAD_GRAYSCALE)
            return None if image is None else image.astype(np.float32)/255
        a = load(low); b = load(low+1)
        if a is None and b is None:
            return np.ones((height, width), np.float32)
        if a is None: a = b
        if b is None or a.shape != b.shape: b = a
        matte = a*(1-weight)+b*weight
        matte = cv2.resize(matte, (width, height), interpolation=cv2.INTER_LINEAR)
        # Soft, slightly tightened edge hides the low-resolution matte boundary.
        matte = cv2.GaussianBlur(matte, (0, 0), max(1.0, height/540))
        return np.clip((matte-.15)/.7, 0, 1)
