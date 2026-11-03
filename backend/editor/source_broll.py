"""B-roll from the project's own source video (other moments and other clips), found with the
cached local search index built during generation (CLIP frames + transcript), then cut locally.

Free: no transcription or model API is called. If the source video or its cached index is not on
this machine, nothing is found and the Director uses free Pexels stock instead.
"""
import hashlib
import logging
import subprocess
from functools import lru_cache
from pathlib import Path

LOG = logging.getLogger(__name__)


@lru_cache(maxsize=8)
def _key(path, size, mtime):
    from backend.agent.index import file_sha256
    return file_sha256(Path(path))


@lru_cache(maxsize=4)
def _frames(key):
    import numpy as np
    from backend.agent.index import CACHE_DIR
    path = CACHE_DIR/f'frames_{key}.npz'
    if not path.is_file(): return None
    with np.load(path) as data:
        return np.array(data['frame_times']), np.array(data['frame_embeddings']), float(data['interval'])


def _clip_model():
    from backend.video_search import router as vs
    vs.load_models('visual')
    return vs.visual_model


def _refine(source, at, interval, query_vector):
    """The cached index samples every ~interval s; pick the best moment within it."""
    import io
    import numpy as np
    from PIL import Image
    times = [max(0, at+interval*f) for f in (-.4, -.2, 0, .2, .4)]
    images, kept = [], []
    for t in times:
        jpg = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{t:.2f}', '-i', str(source), '-frames:v', '1', '-vf', 'scale=224:-2',
                              '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'], capture_output=True, timeout=30).stdout
        if jpg: images.append(Image.open(io.BytesIO(jpg)).convert('RGB')); kept.append(t)
    if not images: return None
    vectors = _clip_model().encode(images, normalize_embeddings=True)
    # Skip near-black or blank frames (night shots, fades): they read as a glitch in the edit.
    usable = np.array([np.asarray(i.convert('L'), np.float32).mean() > 45 and np.asarray(i.convert('L'), np.float32).std() > 18 for i in images])
    if not usable.any(): return None
    scores = np.where(usable, vectors @ query_vector, -1)
    return kept[int(np.argmax(scores))]


def find(source, query, avoid, limit=1, used=()):
    """Best source-video moments for a visual query, outside `avoid` (start, end) ranges."""
    import numpy as np
    source = Path(source)
    if not source.is_file(): return []
    st = source.stat()
    index = _frames(_key(str(source), st.st_size, st.st_mtime_ns))
    if index is None: return []
    times, vectors, interval = index
    query_vector = _clip_model().encode([query], normalize_embeddings=True)[0]
    scores = vectors @ query_vector
    hits = []
    for i in np.argsort(-scores)[:12]:
        t = float(times[i])
        if any(a-interval <= t <= b+interval for a, b in avoid) or any(abs(t-u) < 2*interval for u in [*used, *hits]):
            continue
        best = _refine(source, t, interval, query_vector)
        if best is not None: hits.append(best)
        if len(hits) >= limit: break
    return hits


def insert(state, stock, source, at, place, length, query, transition='cut'):
    """Cut `length` seconds around source time `at` into this clip's B-roll store; show it at clip time `place`."""
    import uuid
    from backend import broll
    folder = Path(stock.folder); folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f'{Path(source).name}:{at:.2f}:{length:.2f}'.encode()).hexdigest()
    asset_id = f'px-{int(digest[:7], 16)+1}-{int(digest[7:13], 16)}'
    video = folder/(asset_id+'.mp4')
    if not video.is_file():
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', f'{max(0, at-length/2):.2f}', '-i', str(source), '-t', f'{length:.2f}',
                        '-an', '-vf', "scale='min(1280,iw)':-2", '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                        str(video)], check=True, capture_output=True, timeout=120)
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', f'{length/2:.2f}', '-i', str(video), '-frames:v', '1',
                        str(folder/(asset_id+'.jpg'))], capture_output=True, timeout=30)
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height:format=duration',
                            '-of', 'csv=p=0', str(video)], capture_output=True, text=True, timeout=30).stdout.split()
    width, height = (int(v) for v in probe[0].split(',')[:2])
    asset = broll.Asset(id=asset_id, provider_id=int(digest[:7], 16)+1, creator='Your source video', creator_url='',
                        source_url=f'source video at {at:.1f}s ({query})', duration=round(float(probe[-1]), 3), width=width, height=height)
    registry = stock.registry()
    registry[asset_id] = {'asset': asset.model_dump(), 'video': 'local', 'image': 'local'}
    broll.write_json(folder/'assets.json', registry)
    length = min(length, asset.duration-.05, state.end-place)
    state.broll.append(broll.Segment(id=uuid.uuid4().hex, asset=asset, start=round(place, 3), duration=round(length, 3),
                                     mode='fill', transition=transition))
    return state.broll[-1]
