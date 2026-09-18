import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

def run_cli(args, cwd=ROOT, env=None):
    e = dict(os.environ)
    if env: e.update(env)
    return subprocess.run([PY, '-m', 'pipeline_tools', *args], capture_output=True, text=True, cwd=str(cwd), env=e, timeout=60)

def make_repo(tmp):
    """Temporary git repo with one commit; returns (path, head_sha)."""
    p = Path(tmp)
    def g(*args):
        r = subprocess.run(['git', '-C', str(p), *args], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout
    subprocess.run(['git', 'init', '-q'], cwd=p, capture_output=True)
    g('config', 'user.email', 'test@example.invalid')
    g('config', 'user.name', 'Test')
    (p / 'ok.txt').write_text('x', encoding='utf-8')
    g('add', '.'); g('commit', '-q', '-m', 'base')
    return p, g('rev-parse', 'HEAD').strip()


class CLITests(unittest.TestCase):
    def test_help(self):
        p = run_cli(['--help'])
        self.assertEqual(p.returncode, 0)
        for word in ('task', 'scope', 'command', 'evidence', 'gate', 'metrics'):
            self.assertIn(word, p.stdout)

    def test_command_run_with_dashdash_separator(self):
        # README documents: command run --cwd . --log L --timeout 30 -- python -c "print('hi')"
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'ok.log'
            p = run_cli(['command', 'run', '--cwd', str(ROOT), '--log', str(log), '--timeout', '30',
                         '--', PY, '-c', "print('hi')"])
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('hi', log.read_text(encoding='utf-8'))
            self.assertIn('"exit_code": 0', p.stdout.replace("'", '"'))

    def test_command_run_nonzero_exit_is_fail_1(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'fail.log'
            p = run_cli(['command', 'run', '--cwd', str(ROOT), '--log', str(log), '--timeout', '30',
                         '--', PY, '-c', 'raise SystemExit(7)'])
            self.assertEqual(p.returncode, 1, (p.stdout, p.stderr))
            self.assertIn('"exit_code": 7', p.stdout.replace("'", '"'))

    def test_command_run_missing_executable_is_config_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = run_cli(['command', 'run', '--cwd', str(ROOT), '--log', str(Path(d) / 'x.log'),
                         '--timeout', '5', '--', 'definitely-not-a-real-exe-xyz', 'arg'])
            self.assertEqual(p.returncode, 2, (p.stdout, p.stderr))
            self.assertNotIn('Traceback', p.stderr)

    def test_command_run_timeout_is_3_with_timed_out_flag(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'slow.log'
            p = run_cli(['command', 'run', '--cwd', str(ROOT), '--log', str(log), '--timeout', '1',
                         '--', PY, '-c', 'import time; time.sleep(5)'])
            self.assertEqual(p.returncode, 3, (p.stdout, p.stderr))
            self.assertIn('"timed_out": true', p.stdout.replace("'", '"'))

    def test_command_run_empty_command_is_config_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = run_cli(['command', 'run', '--cwd', str(ROOT), '--log', str(Path(d) / 'x.log'),
                         '--timeout', '5', '--'])
            self.assertEqual(p.returncode, 2, (p.stdout, p.stderr))

    def test_task_preflight_and_freeze_check_subcommands(self):
        # SKILL.md stable interface: `pipeline-tools task preflight` / `task freeze-check`
        with tempfile.TemporaryDirectory() as d:
            repo, head = make_repo(d)
            for name in ('preflight', 'freeze-check'):
                p = run_cli(['task', name, str(repo), '--contract', head])
                self.assertEqual(p.returncode, 0, (name, p.stdout, p.stderr))
            # non-ancestor contract commit -> exit 4
            p = run_cli(['task', 'freeze-check', str(repo), '--contract', 'deadbeef'])
            self.assertEqual(p.returncode, 4, (p.stdout, p.stderr))

    def test_scope_check_multiple_allowed_flags(self):
        with tempfile.TemporaryDirectory() as d:
            repo, _ = make_repo(d)
            (repo / 'src').mkdir()
            (repo / 'src' / 'a.py').write_text('x', encoding='utf-8')
            (repo / 'docs').mkdir()
            (repo / 'docs' / 'b.md').write_text('x', encoding='utf-8')
            p = run_cli(['scope', 'check', str(repo), '--allowed', 'src/**', '--allowed', 'docs/**'])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))

    def test_metrics_roundtrip_and_purge(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = run_cli(['metrics', 'record', str(root), 'test', '--confidence', 'observed',
                         '--task-id', 'demo', '--result', 'pass'])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            p = run_cli(['metrics', 'report', str(root)])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            self.assertIn('"core_events": 1', p.stdout.replace("'", '"'))
            p = run_cli(['metrics', 'purge', str(root)])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            self.assertEqual(list((root / '.workflow' / 'metrics').glob('*.json')), [])

    def test_bin_wrappers_run(self):
        # AT6: wrappers must run; on Windows use .cmd via shell, on POSIX use the sh wrapper.
        import platform
        with tempfile.TemporaryDirectory() as d:
            if platform.system() == 'Windows':
                r = subprocess.run(['cmd', '/c', str(ROOT / 'bin' / 'pipeline-tools.cmd'), '--help'],
                                   capture_output=True, text=True, cwd=str(ROOT), timeout=60)
            else:
                r = subprocess.run([str(ROOT / 'bin' / 'pipeline-tools'), '--help'],
                                   capture_output=True, text=True, cwd=str(ROOT), timeout=60)
            self.assertEqual(r.returncode, 0, (r.stdout, r.stderr))
            self.assertIn('task', r.stdout)

    def test_task_validate_real_sheet(self):
        p = run_cli(['task', 'validate', str(ROOT / 'docs' / 'tasks' / 'pipeline-tools-v1.md')])
        self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
        p = run_cli(['task', 'validate', str(ROOT / 'nope.md')])
        self.assertEqual(p.returncode, 2, (p.stdout, p.stderr))


if __name__ == '__main__':
    unittest.main()
