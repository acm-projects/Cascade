"""The durable job queue (backend/core/job_queue.py) and sources kept in S3 (projects_store.local_source)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.core import job_queue, jobs
from backend.services import projects_store


class Queue(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(jobs, 'JOBS_DIR', self.root), patch.object(jobs.worker, 'submit')]
        for p in self.patches: p.start()
        self.ran = []
        job_queue.TASKS['test'] = 'tests.application.test_job_queue:record_run'
        RUNS.clear()

    def tearDown(self):
        job_queue.TASKS.pop('test', None)
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def job(self, job_id='a'*32, state=None):
        folder = self.root/job_id
        folder.mkdir()
        if state: (folder/'progress.json').write_text(json.dumps({'state': state}))
        return job_id, folder

    def test_a_job_is_saved_until_it_finishes(self):
        job_id, folder = self.job()
        job_queue.submit('test', job_id, folder/'source.video', 'funny clips', 4)
        saved = json.loads((self.root/'queue'/f'{job_id}.json').read_text())
        self.assertEqual(saved['args'], [{'$path': str(folder/'source.video')}, 'funny clips', 4])   # plain data, no code
        run, record = jobs.worker.submit.call_args.args
        run(record)
        self.assertEqual(RUNS, [(job_id, folder/'source.video', 'funny clips', 4)])
        self.assertFalse((self.root/'queue'/f'{job_id}.json').exists())

    def test_a_restart_runs_queued_and_cut_off_jobs_again(self):
        waiting, folder = self.job('b'*32, state='queued')
        cut_off, _ = self.job('c'*32, state='processing')
        finished, _ = self.job('d'*32, state='done')
        for job_id in (waiting, cut_off, finished):
            job_queue.submit('test', job_id, 'prompt')
        jobs.worker.submit.reset_mock()
        with patch.dict(jobs.jobs, {}, clear=True):
            self.assertEqual(sorted(job_queue.resume()), sorted([waiting, cut_off]))
            self.assertEqual(jobs.jobs[waiting]['message'], 'Resuming after a server restart…')
        self.assertEqual(jobs.worker.submit.call_count, 2)
        self.assertFalse((self.root/'queue'/f'{finished}.json').exists())   # a finished job is not run again

    def test_unknown_tasks_are_refused(self):
        with self.assertRaises(ValueError):
            job_queue.submit('os:system', 'e'*32)

    def test_a_source_only_in_s3_comes_back_before_the_job_runs(self):
        job_id, folder = self.job('f'*32)
        (folder/'owner.json').write_text(json.dumps({'source_s3_key': 'sources/x.mp4', 'source_s3_bucket': 'bucket'}))
        client = MagicMock()
        client.download_file.side_effect = lambda bucket, key, target: Path(target).write_bytes(b'video')
        with patch.object(projects_store.storage_service, 's3_client', return_value=client):
            job_queue.submit('test', job_id, folder/'source.video')
            run, record = jobs.worker.submit.call_args.args
            run(record)
        self.assertEqual((folder/'source.video').read_bytes(), b'video')
        client.download_file.assert_called_once()
        self.assertEqual(RUNS[0][1], folder/'source.video')


class SourceBackupRetry(unittest.TestCase):
    def test_a_failed_source_backup_is_retried_on_startup(self):
        from backend.services import source_backup
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)/('g'*32)
            folder.mkdir()
            (folder/'source.video').write_bytes(b'video')
            owner = {'source_backup_state': 'failed'}
            threads = []
            with patch.object(source_backup.storage, 'uses_local_storage', return_value=False), \
                    patch.object(source_backup.jobs, 'metadata_documents', return_value=[(folder/'owner.json', owner)]), \
                    patch.object(source_backup, 'schedule') as schedule, \
                    patch.object(source_backup.threading, 'Thread', side_effect=lambda target, **k: threads.append(target) or MagicMock()):
                source_backup.resume_pending()
                threads[0]()
            schedule.assert_called_once()
            self.assertEqual(schedule.call_args.args[:2], (folder, 'g'*32))


RUNS = []


def record_run(job_id, *args):
    RUNS.append((job_id, *args))


if __name__ == '__main__':
    unittest.main()
