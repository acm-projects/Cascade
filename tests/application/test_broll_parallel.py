"""B-roll searches and downloads run at the same time instead of waiting in one line."""
import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend import broll
from backend.editor.ai_edit.cinema import broll as cinema_broll
from tests.application.test_broll import provider_video


class ParallelTests(unittest.TestCase):
    def test_different_searches_overlap(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        store = broll.Store(temp.name)
        key = patch.dict(os.environ, {'PEXELS_API_KEY': 'k'}); key.start(); self.addCleanup(key.stop)
        def slow(*a, **k):
            time.sleep(.4)
            return SimpleNamespace(status_code=200, json=lambda: {'videos': [provider_video()]})
        started = time.time()
        with patch.object(broll.httpx, 'get', side_effect=slow):
            threads = [threading.Thread(target=store.search, args=(q,)) for q in ('ocean', 'forest', 'city', 'desert')]
            [t.start() for t in threads]; [t.join() for t in threads]
        self.assertLess(time.time()-started, 1.0, 'four 0.4 s searches should take about 0.4 s, not 1.6 s')

    def test_resolver_prefetch_finds_every_clip_at_once(self):
        class Store:
            def search(self, query, orientation=None, hd=False):
                time.sleep(.3); return {'results': [{'id': 'px-' + query, 'source_url': 'u'}]}
            def media(self, ident): time.sleep(.3); return '/tmp/' + ident + '.mp4'
        find = cinema_broll.resolver(Store())
        queries = ['a', 'b', 'c', 'd']
        started = time.time()
        with patch('backend.editor.ai_edit.picture.ranked', side_effect=lambda q, r: r):
            find.prefetch(queries)
            paths = [find(q) for q in queries]
        self.assertEqual(paths, ['/tmp/px-' + q + '.mp4' for q in queries])
        self.assertLess(time.time()-started, 1.2, 'eight 0.3 s steps in parallel')
        self.assertEqual(len(find.credits), 4)
