"""Running several generation jobs at once, fairly between people.

Before, every generation, search, caption-style and research job ran one at a time on a single thread, so one
person's long video made everyone else wait for all of it. Now SLOTS jobs run at once (CASCADE_GENERATION_WORKERS,
default 2), and each person has at most one running: while theirs runs, someone else's waiting job goes first, and
their own next job waits its turn. Jobs still start in the order they were submitted otherwise.

`FairWorker.submit(fn, record)` has the same shape as ThreadPoolExecutor.submit and returns a Future, so callers and
tests that patch `jobs.worker.submit` are unchanged. `record['user_id']` names the person (job_queue adds it); a
record without one is treated as its own person.
"""
import logging
import os
import threading
from collections import Counter
from concurrent.futures import Future

LOG = logging.getLogger(__name__)


def configured_slots():
    """CASCADE_GENERATION_WORKERS, 1–8 (bad values fall back to 2). Each job also encodes with several cores."""
    try:
        return max(1, min(8, int(os.environ.get('CASCADE_GENERATION_WORKERS', '2'))))
    except ValueError:
        return 2


class FairWorker:
    def __init__(self, slots):
        self.slots = slots
        self._pending = []          # [(person, job_id, fn, args, future)], oldest first
        self._running = Counter()   # person -> running jobs
        self._running_jobs = set()
        self._changed = threading.Condition()
        self._threads = []

    @staticmethod
    def _person(args):
        record = args[0] if args and isinstance(args[0], dict) else {}
        return str(record.get('user_id') or record.get('job_id') or id(args)), record.get('job_id')

    def submit(self, fn, *args):
        future = Future()
        person, job_id = self._person(args)
        with self._changed:
            self._pending.append((person, job_id, fn, args, future))
            while len(self._threads) < self.slots:
                thread = threading.Thread(target=self._loop, name=f'generation-{len(self._threads) + 1}', daemon=True)
                self._threads.append(thread)
                thread.start()
            self._changed.notify()
        return future

    def _take(self):
        """The oldest waiting job whose person has nothing running (call with the lock held)."""
        for position, item in enumerate(self._pending):
            if not self._running[item[0]]:
                return self._pending.pop(position)
        return None

    def _loop(self):
        while True:
            with self._changed:
                item = self._take()
                while item is None:
                    self._changed.wait()
                    item = self._take()
                person, job_id, fn, args, future = item
                self._running[person] += 1
                self._running_jobs.add(job_id)
            try:
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(fn(*args))
                    except BaseException as error:
                        # the type only: job errors can carry keys or signed links, and jobs report their own errors
                        LOG.error('Background job %s ended with %s', job_id, type(error).__name__)
                        future.set_exception(error)
            finally:
                with self._changed:
                    self._running[person] -= 1
                    if not self._running[person]:
                        del self._running[person]
                    self._running_jobs.discard(job_id)
                    self._changed.notify_all()

    def running_count(self):
        with self._changed:
            return sum(self._running.values())

    def waiting_message(self, job_id):
        """What a waiting job is waiting for, in words, or None if it isn't waiting here."""
        with self._changed:
            ids = [item[1] for item in self._pending]
            if job_id not in ids:
                return None
            mine = ids.index(job_id)
            if self._running[self._pending[mine][0]]:
                return 'Waiting for your other video to finish…'
            ahead = mine
        return 'Waiting to process...' if not ahead else (
            f'Waiting to process: {ahead} video{"s" if ahead != 1 else ""} ahead of yours…')
