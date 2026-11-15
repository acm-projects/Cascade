"""Research worker failure paths: the failing step is reported, secrets stay out of the job, tracebacks are logged.
Run with python -m unittest tests.application.test_research_failures -v.
"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.core import jobs as core_jobs
from backend.services import features as feature_workers
from backend.services import projects_store

SECRET = 'sk-test-research-secret-123456'
LOGGER = 'backend.services.features'


class ResearchFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        patches = [patch.dict(os.environ, {'ANTHROPIC_API_KEY': SECRET}),
                   patch.object(core_jobs, 'JOBS_DIR', Path(self.temp.name)),
                   patch.object(core_jobs, 'update_job')]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.temp.cleanup)
        self.fail_feature = self.start(patch.object(projects_store, 'fail_feature'))
        self.finish_feature = self.start(patch.object(projects_store, 'finish_feature'))
        self.job_id = 'a' * 32
        (Path(self.temp.name) / self.job_id).mkdir()
        self.source = Path(self.temp.name) / 'source.video'
        self.source.write_bytes(b'video')
        self.cache = Path(self.temp.name) / 'cache'
        self.cache.mkdir()

    def start(self, item):
        mock = item.start()
        self.addCleanup(item.stop)
        return mock

    def fake_router(self, run_analysis):
        router = types.ModuleType('backend.trends.router')
        router.JOBS = {}
        router.RESULTS_CACHE_DIR = self.cache
        router._result_cache_key = lambda topic, digest: f'{topic}-{digest}'
        def new_job():
            router.JOBS['internal'] = {'status': 'running'}
            return 'internal'
        router._new_job = new_job
        router._run_analysis = lambda job_id, topic, source, work, cache, progress=None: run_analysis(router.JOBS[job_id], progress)
        return router

    def run_research(self, router):
        with patch.dict(sys.modules, {'backend.trends.router': router}):
            feature_workers.research(self.job_id, self.source, 'waterfalls')
        return router

    def message(self):
        self.fail_feature.assert_called_once()
        self.finish_feature.assert_not_called()
        return self.fail_feature.call_args.args[1]

    def test_pipeline_error_names_the_step_and_keeps_provider_details_in_the_log(self):
        def run(job, progress):
            progress('Fetching trending videos...')
            progress('Your video: transcribing...')
            job.update(status='error', error=f'Could not analyze your video: invalid key {SECRET}')
        with self.assertLogs(LOGGER, 'ERROR') as logs:
            router = self.run_research(self.fake_router(run))
        message = self.message()
        self.assertIn('Research failed while Your video: transcribing.', message)
        self.assertNotIn(SECRET, message)
        self.assertNotIn('invalid key', message)
        output = '\n'.join(logs.output)
        self.assertIn('Could not analyze your video', output)
        self.assertNotIn(SECRET, output)
        self.assertIn('[redacted]', output)
        self.assertTrue(any(record.exc_info for record in logs.records))
        # cleanup still runs on failure
        self.assertFalse((Path(self.temp.name) / self.job_id / 'research').exists())
        self.assertEqual(router.JOBS, {})

    def test_unexpected_exception_reports_last_step_and_logs_traceback(self):
        def run(job, progress):
            progress('Trending video 2/5 (Falls): extracting frames...')
            raise ValueError(f'frame decoder exploded {SECRET}')
        with self.assertLogs(LOGGER, 'ERROR') as logs:
            self.run_research(self.fake_router(run))
        message = self.message()
        self.assertEqual(message, 'Research failed while Trending video 2/5 (Falls): extracting frames. Check the API terminal for the error details.')
        self.assertNotIn(SECRET, message)
        record = next(record for record in logs.records if record.exc_info)
        self.assertIs(record.exc_info[0], ValueError)
        self.assertIn('Traceback', logs.output[-1])

    def test_provider_status_errors_keep_their_existing_safe_message(self):
        class Rejected(Exception):
            status_code = 401
        def run(job, progress):
            raise Rejected(SECRET)
        with self.assertLogs(LOGGER, 'ERROR'):
            self.run_research(self.fake_router(run))
        self.assertEqual(self.message(), 'The AI provider rejected the API key. Check it in .env and restart the server.')

    def test_unreadable_source_names_the_read_step(self):
        self.source.unlink()
        with self.assertLogs(LOGGER, 'ERROR'):
            self.run_research(self.fake_router(lambda job, progress: self.fail('analysis should not start')))
        self.assertTrue(self.message().startswith('Research failed while reading your source video.'))

    def test_missing_dependency_names_the_step_and_logs_traceback(self):
        with self.assertLogs(LOGGER, 'ERROR') as logs:
            self.run_research(None)  # a None module entry makes the import raise ImportError
        self.assertEqual(self.message(), 'A processing dependency is missing (while loading the trends module). Install requirements.txt and restart the service.')
        self.assertTrue(any(record.exc_info and issubclass(record.exc_info[0], ImportError) for record in logs.records))

    def test_success_still_finishes_with_the_research_result(self):
        def run(job, progress):
            progress('Comparing your video against trending videos...')
            job.update(status='done', result={'comparison': 'fixture'})
        router = self.run_research(self.fake_router(run))
        self.fail_feature.assert_not_called()
        self.finish_feature.assert_called_once_with(self.job_id, {'clips': [], 'research': {'comparison': 'fixture'}})
        self.assertEqual(router.JOBS, {})


if __name__ == '__main__':
    unittest.main()
