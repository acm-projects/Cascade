"""Finding b-roll for a query: the project's stock library (Pexels, licence-free) first, with the
relevance check the old engine used, then any local folder of footage."""
import logging
import re
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


def from_stock(query, store, used):
    if store is None: return None
    try:
        from ..picture import ranked
    except Exception:
        return None
    try:
        for orientation in ('portrait', 'landscape'):
            results = [a for a in store.search(query, orientation=orientation, hd=True).get('results', []) if a['id'] not in used]
            for pick in (ranked(query, results) or [])[:3]:
                try:
                    path = store.media(pick['id'])
                    used.add(pick['id'])
                    return str(path)
                except Exception:
                    continue
    except Exception:
        LOG.info('stock search failed for %r', query, exc_info=True)
    return None


def resolver(store=None, folders=()):
    used = set()
    def find(query):
        found = from_stock(query, store, used)
        if found: return found
        for folder in folders:
            found = from_folder(query, folder, used)
            if found: return found
        return None
    return find
