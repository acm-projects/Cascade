"""Words behind the speaker (the owner's FireEdit reference): a giant word sits between the background and
the person. The person is cut out of the finished plate with the local subject mattes (YOLOX + SAM 2.1, the
same ones the fan-edit effects use) and laid back on top as a short transparent video.

Runs on this machine; if the matte model or a VP9-alpha encoder is missing, nothing is made and the edit
renders without these moments."""
import logging
import re
import subprocess
import tempfile
from pathlib import Path

LOG = logging.getLogger(__name__)
FPS = 30
MOST = 4         # at most this many moments per film
SPACING = 4.0    # seconds between moments
LENGTH = 1.6     # seconds a moment lasts
FILLER = {'a', 'an', 'the', 'of', 'or', 'and', 'but', 'is', 'are', 'it', 'that', 'this', 'so', 'to', 'in', 'on', 'they',
          "they're", 'he', 'she', 'we', 'you', 'i', 'my', 'just', 'like', 'very', 'really', 'have', 'has', 'do', 'was'}


def moments(layout):
    """Up to MOST (start, end, word) on the speaker, on each line's stressed word, spaced apart."""
    out = []
    for line in layout.lines:
        spec = line['plan']
        if spec.verdict: continue
        key = next(((w, t) for w, t, i in line['words'] if i == spec.key_word), None)
        if not key: continue
        text = re.sub(r"[^\w'’-]", '', key[0])
        if not text or text.lower() in FILLER or len(text) > 12: continue
        start = key[1]-.05
        end = min(start+LENGTH, layout.end_card-.1)
        if start < .8 or end-start < .9: continue
        during = [e for e in layout.events if e.start < end and e.end > start]
        if not during or any(e.kind != 'sync' for e in during): continue  # only while the speaker is on screen
        if out and start-out[-1][0] < SPACING: continue
        out.append((round(start, 3), round(end, 3), text.upper()))
        if len(out) == MOST: break
    return out


def make(plate, spans, out_dir, cache_dir, ffmpeg='ffmpeg'):
    """[(start, end, word, file name)] for the moments whose cut-out could be made."""
    if not spans: return []
    try:
        import cv2
        import numpy as np
        from ..segmentation import Mattes, _detector
        if _detector() is None:  # without the person detector every matte is the whole frame, which would hide the word
            LOG.warning('words-behind-the-speaker skipped: the person detector model is not installed')
            return []
        mattes = Mattes(plate, cache_dir)
        mattes.ensure([(a, b) for a, b, _ in spans])
    except Exception:
        LOG.warning('words-behind-the-speaker skipped: subject mattes are unavailable', exc_info=True)
        return []
    made = []
    capture = cv2.VideoCapture(str(plate))
    try:
        for n, (start, end, word) in enumerate(spans):
            name = f'behind{n}.webm'
            with tempfile.TemporaryDirectory(prefix='cascade-behind-') as scratch:
                first, last = round(start*FPS), round(end*FPS)
                probe = mattes.at(start+.4, 108, 192)
                if probe.mean() > .8 or probe.mean() < .03: continue  # no person found here: keep the normal caption
                capture.set(cv2.CAP_PROP_POS_FRAMES, first)
                count = 0
                for index in range(first, last):
                    ok, frame = capture.read()
                    if not ok: break
                    h, w = frame.shape[:2]
                    alpha = (mattes.at(index/FPS, w, h)*255).astype(np.uint8)
                    cv2.imwrite(str(Path(scratch)/f'{count:04d}.png'), np.dstack([frame, alpha]))
                    count += 1
                if count < FPS*.8: continue
                run = subprocess.run([ffmpeg, '-nostdin', '-y', '-v', 'error', '-framerate', str(FPS), '-i', str(Path(scratch)/'%04d.png'),
                                      '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '32', '-deadline', 'good',
                                      '-cpu-used', '4', '-auto-alt-ref', '0', str(Path(out_dir)/name)],
                                     capture_output=True, text=True, timeout=300)
                if run.returncode:
                    LOG.warning('words-behind-the-speaker skipped: VP9 alpha encode failed: %s', run.stderr[-300:])
                    return made
                made.append((start, start+count/FPS, word, name))
    finally:
        capture.release()
    return made
