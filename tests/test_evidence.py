import json
import tempfile
import unittest
from pathlib import Path

from pipeline_tools.core import evidence_verify, gate_check


def report(role, task_id='demo', branch='feature/demo', status='PASS'):
    evidence = {
        'schema': 1,
        'task_id': task_id,
        'worktree': '.worktrees/demo',
        'branch': branch,
        'role': role,
        'round': 1,
        'status': status,
        'commands': [
            {
                'command': 'python -m unittest',
                'exit_code': 0,
                'evidence_ref': '.workflow/demo/test.log',
            }
        ],
        'assertions': ['the observed result matches the contract'],
        'evidence_refs': ['.workflow/demo/test.log'],
        'unverified': [],
    }
    return '```pipeline-evidence\n' + json.dumps(evidence) + '\n```\n'


class EvidenceTests(unittest.TestCase):
    def _make_evidence_dir(self, root, statuses=None):
        directory = root / '.workflow' / 'demo'
        directory.mkdir(parents=True)
        artifact = directory / 'test.log'
        artifact.write_text('observed test output', encoding='utf-8')
        statuses = statuses or {}
        for name, role in {
            'executor-report.md': 'executor',
            'review-report.md': 'reviewer',
            'final-check.md': 'main-final',
        }.items():
            status = statuses.get(role, 'PASS')
            (directory / name).write_text(report(role, status=status), encoding='utf-8')
        return directory

    def test_all_reports_require_machine_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            directory = self._make_evidence_dir(root)
            self.assertEqual(evidence_verify(directory, 'demo', 'feature/demo'), [])

    def test_nonpassing_report_is_structurally_valid_but_gate_rejects_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            directory = self._make_evidence_dir(root, {'reviewer': 'BLOCKED'})
            self.assertEqual(evidence_verify(directory, 'demo', 'feature/demo'), [])
            errors = gate_check(directory, 'demo', 'feature/demo', 'pre-merge')
            self.assertTrue(any('review-report.md' in error for error in errors))

    def test_missing_evidence_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            directory = root / '.workflow' / 'demo'
            directory.mkdir(parents=True)
            for name, role in {
                'executor-report.md': 'executor',
                'review-report.md': 'reviewer',
                'final-check.md': 'main-final',
            }.items():
                (directory / name).write_text(report(role), encoding='utf-8')
            errors = evidence_verify(directory, 'demo', 'feature/demo')
            self.assertTrue(any('evidence_ref' in error for error in errors))

    def test_absolute_evidence_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            directory = self._make_evidence_dir(root)
            absolute = str(root / '.workflow' / 'demo' / 'test.log').replace('\\', '/')
            for name, role in {
                'executor-report.md': 'executor',
                'review-report.md': 'reviewer',
                'final-check.md': 'main-final',
            }.items():
                text = report(role).replace('.workflow/demo/test.log', absolute)
                (directory / name).write_text(text, encoding='utf-8')
            errors = evidence_verify(directory, 'demo', 'feature/demo')
            self.assertTrue(any('relative' in error for error in errors))

    def test_passing_report_with_nonzero_command_is_rejected_by_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            directory = self._make_evidence_dir(root)
            text = report('executor').replace('"exit_code": 0', '"exit_code": 7')
            (directory / 'executor-report.md').write_text(text, encoding='utf-8')
            errors = gate_check(directory, 'demo', 'feature/demo', 'pre-merge')
            self.assertTrue(errors)
            self.assertTrue(any('non-zero' in error for error in errors))

    def test_missing_report_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(evidence_verify(Path(d) / 'demo', 'demo'))

    def test_identity_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'demo'
            p.mkdir()
            for name, role in (
                ('executor-report.md', 'executor'),
                ('review-report.md', 'reviewer'),
                ('final-check.md', 'main-final'),
            ):
                (p / name).write_text(report(role, task_id='other'), encoding='utf-8')
            self.assertTrue(evidence_verify(p, 'demo', 'feature/demo'))

    def test_prose_markers_without_machine_block_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'demo'
            p.mkdir()
            text = 'task-id demo worktree x branch feature/demo round 1 command c exit code 0 assertion a evidence e'
            for name in ('executor-report.md', 'review-report.md', 'final-check.md'):
                (p / name).write_text(text, encoding='utf-8')
            errors = evidence_verify(p, 'demo', 'feature/demo')
            self.assertTrue(any('pipeline-evidence' in error for error in errors))

    def test_gate_requires_pass_statuses(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'demo'
            p.mkdir()
            (p / 'executor-report.md').write_text(report('executor'), encoding='utf-8')
            (p / 'review-report.md').write_text(report('reviewer', status='BLOCKED'), encoding='utf-8')
            (p / 'final-check.md').write_text(report('main-final', status='READY-TO-MERGE'), encoding='utf-8')
            errors = gate_check(p, 'demo', 'feature/demo', 'pre-merge')
            self.assertTrue(any('review-report.md' in error for error in errors))


if __name__ == '__main__':
    unittest.main()

