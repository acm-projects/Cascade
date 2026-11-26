"""Demo mode (demo_final): the hike recordings are recognised by name, and the database read cache stays correct."""
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

from backend import demo
from backend.database.metadata_store import MetadataStore


@unittest.skipUnless(demo.enabled(), 'the demo assets (demo/hike) are kept on the demo machine only')
class DemoTests(unittest.TestCase):
    def test_the_hike_recordings_are_recognised_and_nothing_else(self):
        names = sorted(demo.names())
        self.assertTrue(demo.matches(['/Users/x/' + n for n in names[:3]]))
        self.assertFalse(demo.matches(names[:1]))   # one file is an ordinary upload
        self.assertFalse(demo.matches([names[0], 'holiday.mp4']))
        self.assertTrue(demo.is_demo_upload({'source_parts': demo.source_parts()}))
        self.assertFalse(demo.is_demo_upload({'source_parts': [{'name': 'a.mp4'}, {'name': 'b.mp4'}]}))

    def test_the_demo_assets_are_complete(self):
        clips = demo._load('clips.json')['clips']
        self.assertEqual(len(clips), len(demo.combined_parts()))
        for n in range(1, len(clips)+1):
            self.assertTrue((demo.ROOT/f'clip_{n}.mp4').is_file() and (demo.ROOT/f'clip_{n}.vtt').is_file())
        for name in ('combined.mp4', 'edited.mp4', 'source_preview.mp4', 'plan.json', 'report.json'):
            self.assertTrue((demo.ROOT/name).is_file(), name)


class CacheTests(unittest.TestCase):
    def store(self, rows):
        store = MetadataStore(Path('/tmp/cascade-cache-test'), 'postgres://x')
        calls = []

        @contextmanager
        def connection():
            cur = MagicMock()
            cur.execute.side_effect = lambda sql, args=(): calls.append(sql.split()[0])
            cur.fetchone.side_effect = lambda: (rows[0],)
            conn = MagicMock()
            conn.cursor.return_value.__enter__.return_value = cur
            yield conn
        store.connection = connection
        return store, calls

    def test_a_record_read_twice_costs_one_round_trip_and_a_write_is_seen_at_once(self):
        rows = [{'v': 1}]
        store, calls = self.store(rows)
        path = Path('/tmp/cascade-cache-test')/('a'*32)/'owner.json'
        self.assertEqual(store.read(path), {'v': 1})
        self.assertTrue(store.exists(path))
        self.assertEqual(calls.count('SELECT'), 1)
        store.write(path, {'v': 2}); rows[0] = {'v': 2}
        self.assertEqual(store.read(path), {'v': 2})
        got = store.read(path); got['v'] = 99   # callers may change what they read
        self.assertEqual(store.read(path), {'v': 2})


if __name__ == '__main__':
    unittest.main()
