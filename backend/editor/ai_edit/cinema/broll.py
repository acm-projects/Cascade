"""Finding b-roll for a query: the project's stock library (Pexels, licence-free) first, with the
a relevance check on each result's page description, then any local folder of footage."""
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LOG = logging.getLogger(__name__)
VIDEO = ('.mp4', '.mov', '.m4v', '.webm')
LOOK_WORDS = {'close', 'up', 'closeup', 'shot', 'aerial', 'view', 'slow', 'motion', 'footage', 'video', 'cinematic', 'b', 'roll',
              'stock', 'wide', 'macro', 'drone', 'the', 'a', 'an', 'of', 'in', 'on', 'at', 'and', 'with', 'from', 'into', 'its',
              'walking', 'running', 'moving', 'looking', 'face', 'powerful', 'beautiful', 'dark', 'night', 'day'}


def _stem(word):
    if word.endswith('ies'): return word[:-3]
    if word.endswith('ing') and len(word) > 5: word = word[:-3]  # "roaring" matches a "lion-roars" clip
    return word[:-1] if word.endswith('s') and len(word) > 3 else word


def ranked(query, results):
    """Stock results whose own page description names what the query is about, best first, or None.

    Pexels returns loose matches (a search for "jaguar" can return a woman's face), and the first result is
    often off. Each result's page address describes it ("/video/a-jaguar-resting-on-a-branch-123/"), so a
    clip is used only when that description contains the query's subject words."""
    subject = {_stem(w) for w in re.findall(r'[a-z]+', query.lower()) if w not in LOOK_WORDS and len(w) > 2}
    if not subject: return None
    def score(asset):
        slug = re.sub(r'[^a-z]+', ' ', (asset.get('source_url') or '').lower().rsplit('/video/', 1)[-1])
        words = {_stem(w) for w in slug.split()}
        return len(subject & words)
    needed = 1 if len(subject) <= 2 else 2  # "jaguar" needs jaguar; "caiman river amazon" needs two of them
    scored = sorted(((score(a), i, a) for i, a in enumerate(results)), key=lambda x: (-x[0], x[1]))
    return [a for n, _, a in scored if n >= needed]


def _words(text):
    return {w for w in re.findall(r'[a-z]+', text.lower()) if len(w) > 2}


def from_folder(query, folder, used):
    """Best file in `folder` whose name shares the most words with the query; an unused one wins a tie,
    and a used one is taken again only when nothing else matches."""
    folder = Path(folder)
    if not folder.is_dir(): return None
    want = _words(query)-{'cinematic', 'footage', 'shot', 'close', 'aerial', 'view', 'slow', 'motion'}
    best, score = None, 0
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in VIDEO: continue
        s = len(want & _words(f.stem))-(.5 if str(f) in used else 0)
        if s > score and s >= .9: best, score = f, s
    if best: used.add(str(best))
    return str(best) if best else None


def from_stock(query, store, used, credits=None, lock=None):
    lock = lock or threading.Lock()
    if store is None: return None
    try:
        for orientation in ('portrait', 'landscape'):
            with lock: taken = set(used)
            results = [a for a in store.search(query, orientation=orientation, hd=True).get('results', []) if a['id'] not in taken]
            for pick in (ranked(query, results) or [])[:3]:
                with lock:
                    if pick['id'] in used: continue    # another shot just took it
                    used.add(pick['id'])
                try:
                    path = store.media(pick['id'])
                    if credits is not None:
                        with lock: credits.append({'query': query, 'id': pick['id'], 'source': pick.get('source_url') or pick.get('url') or '', 'license': 'Pexels License'})
                    return str(path)
                except Exception:
                    with lock: used.discard(pick['id'])
                    continue
    except Exception:
        LOG.info('stock search failed for %r', query, exc_info=True)
    return None


def resolver(store=None, folders=()):
    """find(query) -> path or None. `find.credits` lists where every shot came from; it is saved with the project.
    `find.prefetch(queries)` starts every search and download at once, so the edit finds each clip already waiting."""
    used, credits, lock, pending = set(), [], threading.Lock(), {}
    pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix='broll')

    def lookup(query):
        found = from_stock(query, store, used, credits, lock)
        if found: return found
        for folder in folders:
            with lock: found = from_folder(query, folder, used)
            if found:
                with lock: credits.append({'query': query, 'file': Path(found).name, 'source': 'local folder'})
                return found
        return None

    def prefetch(queries):
        for query in dict.fromkeys(q for q in queries if q):
            if query not in pending: pending[query] = pool.submit(lookup, query)

    def find(query):
        job = pending.pop(query, None)
        if job is not None:
            try: return job.result()
            except Exception:
                LOG.info('b-roll prefetch failed for %r', query, exc_info=True)
                return None
        return lookup(query)
    find.credits = credits
    find.prefetch = prefetch
    return find
