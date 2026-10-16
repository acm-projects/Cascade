"""Measure sequential processing stages with a monotonic clock."""
import time


class StageTimer:
    def __init__(self, report=lambda timings, active: None):
        self.report = report
        self.timings = {}
        self.active = None
        self.started = None

    def start(self, name):
        self._finish()
        self.active = name
        self.started = time.perf_counter()
        self.report(dict(self.timings), name)

    def _finish(self):
        if self.active is not None:
            elapsed = time.perf_counter() - self.started
            self.timings[self.active] = round(self.timings.get(self.active, 0) + elapsed, 3)
        self.active = None

    def finish(self):
        self._finish()
        self.report(dict(self.timings), None)
        return dict(self.timings)
