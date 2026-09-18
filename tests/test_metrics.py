import json
import tempfile
import unittest
from pathlib import Path

from pipeline_tools.core import aggregate, metric_event


class MetricsTests(unittest.TestCase):
    def test_reported_excluded_and_token_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            metric_event(root, {
                'event': 'pass', 'confidence': 'observed', 'task_id': 'a/b', 'result': 'pass'
            })
            metric_event(root, {
                'event': 'pass', 'confidence': 'reported', 'task_id': 'x', 'result': 'pass'
            })
            self.assertEqual(aggregate(root)['events'], 2)
            self.assertEqual(aggregate(root)['core_events'], 1)
            raw = ' '.join(p.read_text() for p in (root / '.workflow/metrics').glob('*.json'))
            self.assertNotIn(str(root), raw)
            self.assertIn('null', raw)

    def test_feedback_events_are_aggregated_without_treating_unknown_as_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for event, result in (
                ('review_overturn', 'blocked'),
                ('retry', 'unknown'),
                ('timeout', 'blocked'),
                ('evidence_gap', 'blocked'),
                ('post_merge_regression', 'fail'),
            ):
                metric_event(root, {
                    'event': event,
                    'confidence': 'derived',
                    'task_id': 'task-a',
                    'result': result,
                })
            metric_event(root, {
                'event': 'retry',
                'confidence': 'observed',
                'task_id': 'task-a',
                'result': 'pass',
                'attempt': 2,
            })
            summary = aggregate(root)
            self.assertEqual(summary['review_overturns'], 1)
            self.assertEqual(summary['retries'], 3)
            self.assertEqual(summary['timeouts'], 1)
            self.assertEqual(summary['evidence_gaps'], 1)
            self.assertEqual(summary['post_merge_regressions'], 1)
            self.assertEqual(summary['success_rate'], 1 / 2)

    def test_absolute_evidence_ref_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(ValueError):
                metric_event(root, {
                    'event': 'test',
                    'confidence': 'observed',
                    'task_id': 'task-a',
                    'result': 'pass',
                    'evidence_ref': str(root / 'secret.log'),
                })


if __name__ == '__main__':
    unittest.main()

