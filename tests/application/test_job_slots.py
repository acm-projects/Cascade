"""Several generation jobs at once, one per person (backend/core/job_slots.py)."""
import threading
import time
import unittest
from unittest.mock import patch

from backend.core import job_slots, media


def wait_for(condition, seconds=3):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(.01)
    return condition()


class FairWorkerTest(unittest.TestCase):
    def setUp(self):
        self.worker = job_slots.FairWorker(2)
        self.started, self.gates = [], {}

    def tearDown(self):
        for gate in self.gates.values():
            gate.set()

    def submit(self, job_id, user):
        gate = self.gates.setdefault(job_id, threading.Event())
        def run(record):
            self.started.append(record['job_id'])
            assert gate.wait(5)
            return record['job_id']
        return self.worker.submit(run, {'job_id': job_id, 'user_id': user})

    def test_two_people_run_at_once_and_one_person_waits_for_their_own(self):
        first = self.submit('a1', 'alice')
        self.submit('a2', 'alice')
        self.submit('b1', 'bob')
        self.assertTrue(wait_for(lambda: sorted(self.started) == ['a1', 'b1']))   # bob does not wait behind alice
        time.sleep(.05)
        self.assertEqual(sorted(self.started), ['a1', 'b1'])                       # alice's second waits for her first
        self.assertEqual(self.worker.running_count(), 2)
        self.assertEqual(self.worker.waiting_message('a2'), 'Waiting for your other video to finish…')
        self.gates['a1'].set()
        self.assertEqual(first.result(3), 'a1')
        self.assertTrue(wait_for(lambda: 'a2' in self.started))

    def test_the_line_says_how_many_are_ahead(self):
        for job_id, user in (('a1', 'alice'), ('b1', 'bob'), ('c1', 'carol'), ('d1', 'dan')):
            self.submit(job_id, user)
        self.assertTrue(wait_for(lambda: len(self.started) == 2))
        self.assertEqual(self.worker.waiting_message('c1'), 'Waiting to process...')
        self.assertEqual(self.worker.waiting_message('d1'), 'Waiting to process: 1 video ahead of yours…')
        self.assertIsNone(self.worker.waiting_message('a1'))   # running, not waiting

    def test_a_failed_job_frees_its_slot(self):
        def broken(record):
            raise RuntimeError('boom')
        with self.assertLogs(job_slots.LOG, 'ERROR'):
            failed = self.worker.submit(broken, {'job_id': 'x', 'user_id': 'alice'})
            with self.assertRaises(RuntimeError):
                failed.result(3)
        self.submit('a2', 'alice')
        self.gates['a2'].set()
        self.assertTrue(wait_for(lambda: self.started == ['a2']))

    def test_the_number_of_slots_comes_from_the_environment(self):
        for value, slots in (('3', 3), ('0', 1), ('99', 8), ('lots', 2)):
            with patch.dict('os.environ', {'CASCADE_GENERATION_WORKERS': value}):
                self.assertEqual(job_slots.configured_slots(), slots)

    def test_parallel_jobs_share_the_cores_for_encoding(self):
        with patch('os.cpu_count', return_value=16), patch.object(media, 'os', wraps=media.os) as fake_os:
            fake_os.cpu_count.return_value = 16
            from backend.core import jobs
            with patch.object(jobs.worker, 'running_count', return_value=1):
                self.assertEqual((media.render_workers(4), media.encoder_threads(4)), (4, 4))
            with patch.object(jobs.worker, 'running_count', return_value=2):
                self.assertEqual((media.render_workers(4), media.encoder_threads(4)), (4, 2))


if __name__ == '__main__':
    unittest.main()
