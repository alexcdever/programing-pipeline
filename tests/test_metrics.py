import json
import tempfile
import unittest
from pathlib import Path

from pipeline_tools.core import aggregate, import_opencode_session, metric_event
from pipeline_tools.layout import metrics_dirs


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
            raw = ' '.join(p.read_text() for p in metrics_dirs(root)[0].glob('*.json'))
            self.assertNotIn(str(root), raw)
            self.assertIn('null', raw)

    def test_sensitive_identifiers_are_redacted_at_metric_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = metric_event(root, {
                'event': 'test', 'confidence': 'observed', 'task_id': 'customer-token',
                'result': 'pass', 'evidence_ref': 'reports/password.log',
            })
            value = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(value['task_id'], 'unknown')
            self.assertIsNone(value['evidence_ref'])

    def test_metric_event_preserves_run_and_terminal_dimensions(self):
        with tempfile.TemporaryDirectory() as d:
            path = metric_event(Path(d), {
                'event': 'gate_pre_merge', 'confidence': 'observed', 'task_id': 'task-a',
                'result': 'pass', 'run_id': 'run-a', 'phase': 'main-final', 'role': 'main-final',
                'head': 'abc123', 'branch': 'main', 'evidence_root': '.pipeline/task-a',
                'terminal': True, 'source': 'pipeline_tools',
            })
            value = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(value['run_id'], 'run-a')
            self.assertEqual(value['phase'], 'main-final')
            self.assertTrue(value['terminal'])
            self.assertEqual(value['evidence_root'], '.pipeline/task-a')

    def test_extended_sensitive_vocabulary_is_redacted_at_metric_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = metric_event(root, {
                'event': 'test', 'confidence': 'observed', 'task_id': 'authorization',
                'reason': 'Bearer abc', 'source': 'passwd', 'result': 'pass',
                'evidence_ref': 'reports/authorization.log',
            })
            value = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(value['task_id'], 'unknown')
            self.assertEqual(value['reason'], 'unknown')
            self.assertEqual(value['source'], 'unknown')
            self.assertIsNone(value['evidence_ref'])

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

    def test_blocker_classes_and_process_metrics_are_aggregated(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            metric_event(root, {
                'event': 'environment_block', 'confidence': 'observed', 'task_id': 'task-a',
                'result': 'blocked', 'blocker_class': 'environment',
            })
            metric_event(root, {
                'event': 'main_agent_product_edit', 'confidence': 'observed', 'task_id': 'task-a',
                'result': 'fail', 'blocker_class': 'workflow',
            })
            summary = aggregate(root)
            self.assertEqual(summary['blockers_by_class']['environment'], 1)
            self.assertEqual(summary['main_agent_product_edits'], 1)

    def test_automatic_event_counts_are_available_for_new_stage_names(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            metric_event(root, {
                'event': 'task_validate', 'confidence': 'observed', 'task_id': 'task-a',
                'result': 'pass', 'source': 'pipeline_tools',
            })
            summary = aggregate(root)
            self.assertEqual(summary['automatic_events'], 1)
            self.assertEqual(summary['event_counts']['task_validate'], 1)

    def test_aggregate_distinguishes_all_event_rates_from_known_result_rate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for event, result in (('task_validate', 'pass'), ('evidence_verify', 'blocked'), ('evidence_gap', 'blocked')):
                metric_event(root, {
                    'event': event, 'confidence': 'observed' if event != 'evidence_gap' else 'derived',
                    'task_id': 'task-a', 'result': result, 'source': 'pipeline_tools',
                })
            summary = aggregate(root)
            self.assertEqual(summary['passed'], 1)
            self.assertEqual(summary['blocked'], 2)
            self.assertEqual(summary['known_result_success_rate'], 1.0)
            self.assertAlmostEqual(summary['all_event_pass_rate'], 1 / 3)
            self.assertAlmostEqual(summary['blocked_rate'], 2 / 3)
            self.assertEqual(summary['unresolved_blocked_count'], 1)
            self.assertEqual(summary['terminal_state_unknown_count'], 3)

    def test_aggregate_groups_events_by_task_and_reports_terminal_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            metric_event(root, {
                'event': 'evidence_verify', 'confidence': 'observed', 'task_id': 'task-a',
                'result': 'blocked', 'source': 'pipeline_tools', 'run_id': 'run-a',
                'phase': 'reviewer', 'terminal': False,
            })
            metric_event(root, {
                'event': 'gate_pre_merge', 'confidence': 'observed', 'task_id': 'task-a',
                'result': 'pass', 'source': 'pipeline_tools', 'run_id': 'run-a',
                'phase': 'main-final', 'terminal': True,
            })
            metric_event(root, {
                'event': 'task_validate', 'confidence': 'observed', 'task_id': 'task-b',
                'result': 'pass', 'source': 'pipeline_tools', 'run_id': 'run-b',
                'phase': 'executor', 'terminal': True,
            })
            summary = aggregate(root)
            self.assertEqual(summary['task_counts']['task-a'], 2)
            self.assertEqual(summary['terminal_task_count'], 2)
            self.assertEqual(summary['terminal_gate_pass_count'], 1)
            self.assertEqual(summary['terminal_unresolved_blocked_count'], 0)

    def test_import_opencode_session_records_structured_observations(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            session = root / 'session.json'
            session.write_text(json.dumps({
                'info': {'id': 'ses_demo'},
                'messages': [
                    {'info': {'role': 'user'}, 'parts': [{'type': 'text', 'text': '继续'}]},
                    {'info': {'role': 'user'}, 'parts': [{'type': 'text', 'text': '为什么停下来？'}]},
                    {'info': {'role': 'assistant'}, 'parts': [
                        {'type': 'tool', 'tool': 'task', 'state': {'status': 'error'}},
                        {'type': 'text', 'text': '我直接修改产品代码，违反了工作流。'},
                    ]},
                ],
            }), encoding='utf-8')
            imported = import_opencode_session(root, session, 'demo')
            self.assertGreaterEqual(len(imported), 4)
            summary = aggregate(root)
            self.assertGreaterEqual(summary['user_continue_nudges'], 1)
            self.assertGreaterEqual(summary['user_process_corrections'], 1)
            self.assertEqual(summary['main_agent_product_edits'], 1)


if __name__ == '__main__':
    unittest.main()
