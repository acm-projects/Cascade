"""Finding b-roll for a query: the project's stock library (Pexels, licence-free) first, with the
relevance check the old engine used, then any local folder of footage."""
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LOG = logging.getLogger(__name__)
VIDEO = ('.mp4', '.mov', '.m4v', '.webm')


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
        from ..picture import ranked
    except Exception:
        return None
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
