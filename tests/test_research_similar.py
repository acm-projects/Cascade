"""Shorts discovery is deterministic and never calls network/model services."""
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from googleapiclient.errors import HttpError
from backend.research import cache, similar, QuotaBudgetExceeded, ResearchConfigError


class FixedDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 25, tzinfo=timezone.utc)


class SimilarShortsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        fixtures = Path(__file__).parent / 'fixtures'
        self.youtube = MagicMock()
        self.youtube.search.return_value.list.return_value.execute.return_value = json.loads((fixtures / 'youtube_search.json').read_text(encoding='utf-8-sig'))
        self.youtube.videos.return_value.list.return_value.execute.return_value = json.loads((fixtures / 'youtube_videos.json').read_text(encoding='utf-8-sig'))
        for context in (patch.object(cache, 'CACHE_DIR', self.directory),
            patch.object(similar, 'datetime', FixedDate),
            patch.dict(os.environ, {'YOUTUBE_API_KEY': 'fixture', 'RESEARCH_DAILY_UNIT_BUDGET': '8000'})):
            context.start(); self.addCleanup(context.stop)
        self.client_patch = patch.object(similar, 'youtube_client', return_value=self.youtube)
        self.client = self.client_patch.start(); self.addCleanup(self.client_patch.stop)
        self.llm_patch = patch.object(similar, 'structured_json', return_value=SimpleNamespace(data={
            'query': 'funny cooking podcast clips', 'topic': 'cooking', 'format': 'podcast clip'}))
        self.llm = self.llm_patch.start(); self.addCleanup(self.llm_patch.stop)
        self.context = {'title': 'Funny cooking story', 'transcript': 'words ' * 100, 'session_prompt': 'funny moments'}

    def test_duration_filter_velocity_sort_and_search_contract(self):
        shorts = similar.find_similar_shorts(self.context)
        self.assertEqual([s.video_id for s in shorts], ['edge', 'fast', 'slow'])
        self.assertEqual(shorts[0].duration_s, 180)
        self.assertEqual(shorts[0].views_per_day, 3000)
        query = self.youtube.search.return_value.list.call_args.kwargs
        self.assertEqual((query['type'], query['videoDuration'], query['order'], query['maxResults']),
                         ('video', 'short', 'viewCount', 25))
        self.assertEqual(query['publishedAfter'], '2026-04-28T00:00:00Z')
        self.assertEqual(self.youtube.videos.return_value.list.call_args.kwargs['part'], 'statistics,contentDetails,snippet')
        self.assertEqual(cache.read_json(self.directory / 'quota.json')['units'], 101)

    def test_second_call_skips_youtube_and_query_llm(self):
        first = similar.find_similar_shorts(self.context, limit=1)
        second = similar.find_similar_shorts(self.context, limit=3)
        self.assertEqual(first[0], second[0])
        self.assertEqual(len(second), 3)
        self.client.assert_called_once()
        self.llm.assert_called_once()
        self.assertEqual(cache.read_json(self.directory / 'quota.json')['units'], 101)

    def test_query_excerpt_is_bounded_and_fallback_without_llm(self):
        similar.build_query(self.context)
        payload = json.loads(self.llm.call_args.args[0].split('\n', 1)[1])
        self.assertEqual(len(payload['transcript'].split()), 60)
        self.llm.side_effect = RuntimeError('No LLM')
        result = similar.build_query({'title': 'The Beautiful Cooking Story'})
        self.assertEqual(result['query'], 'beautiful cooking story')

    def test_budget_guard_precedes_http_and_concurrent_reservations(self):
        with patch.dict(os.environ, {'RESEARCH_DAILY_UNIT_BUDGET': '100'}):
            with self.assertRaises(QuotaBudgetExceeded): similar.find_similar_shorts(self.context)
        self.client.assert_not_called()
        def reserve(_):
            try: cache.reserve_units(101); return True
            except QuotaBudgetExceeded: return False
        with patch.dict(os.environ, {'RESEARCH_DAILY_UNIT_BUDGET': '202'}), ThreadPoolExecutor(max_workers=3) as executor:
            self.assertEqual(sum(executor.map(reserve, range(3))), 2)
        self.assertEqual(cache.read_json(self.directory / 'quota.json')['units'], 202)

    def test_cache_ttl_expiry_and_daily_reset(self):
        with patch.object(cache.time, 'time', return_value=1000): cache.put('sample', ['cached'])
        with patch.object(cache.time, 'time', return_value=1001): self.assertEqual(cache.get('sample'), ['cached'])
        with patch.object(cache.time, 'time', return_value=1000 + cache.TTL): self.assertIsNone(cache.get('sample'))
        cache.write_json(self.directory / 'quota.json', {'date': '2000-01-01', 'units': 99999})
        cache.reserve_units(101)
        self.assertEqual(cache.read_json(self.directory / 'quota.json')['units'], 101)

    def test_missing_key_and_youtube_quota_are_friendly(self):
        with patch.dict(os.environ, {'YOUTUBE_API_KEY': ''}):
            with self.assertRaisesRegex(ResearchConfigError, 'Set YOUTUBE_API_KEY'): similar.find_similar_shorts(self.context)
        error = HttpError(SimpleNamespace(status=403, reason='Forbidden'),
                          b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')
        self.youtube.search.return_value.list.return_value.execute.side_effect = error
        with self.assertRaisesRegex(QuotaBudgetExceeded, 'quota is exhausted'):
            similar.find_similar_shorts(self.context)

    def test_empty_search_cached_and_malformed_duration_ignored(self):
        self.youtube.search.return_value.list.return_value.execute.return_value = {'items': []}
        self.assertEqual(similar.find_similar_shorts(self.context), [])
        self.assertEqual(similar.find_similar_shorts(self.context), [])
        self.youtube.videos.assert_not_called()
        self.client.assert_called_once()
        self.assertEqual(similar.duration_seconds('not a duration'), 0)
        self.assertEqual(similar.duration_seconds('PT1H2M3S'), 3723)

    def test_corrupt_quota_ledger_fails_closed(self):
        (self.directory / 'quota.json').write_text('broken json')
        with self.assertRaises(QuotaBudgetExceeded): cache.reserve_units(101)
        cache.write_json(self.directory / 'quota.json', {'date': '2026-10-25', 'units': -500})
        with self.assertRaises(QuotaBudgetExceeded): cache.reserve_units(101)
