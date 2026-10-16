import unittest
from unittest.mock import Mock, patch
from pipeline_timing import StageTimer


class TimingTests(unittest.TestCase):
    def test_repeated_stage_times_accumulate_and_final_report_has_no_active_stage(self):
        report = Mock()
        timer = StageTimer(report)
        with patch('pipeline_timing.time.perf_counter', side_effect=[10, 12, 12, 15, 15, 20]):
            timer.start('Rendering')
            timer.start('Storage')
            timer.start('Rendering')
            result = timer.finish()
        self.assertEqual(result, {'Rendering': 7, 'Storage': 3})
        self.assertEqual(report.call_args.args, (result, None))
