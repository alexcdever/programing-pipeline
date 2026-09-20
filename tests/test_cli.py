import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

def run_cli(args, cwd=ROOT, env=None):
    e = dict(os.environ)
    # These tests cover the legacy command surface. Automatic collection has
    # explicit tests and is disabled here to avoid mutating this checkout.
    e.setdefault('PIPELINE_TOOLS_DISABLE_AUTO_METRICS', '1')
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
        for word in ('task', 'scope', 'command', 'evidence', 'gate', 'metrics', 'lifecycle'):
            self.assertIn(word, p.stdout)

    def test_json_output_has_common_envelope_and_can_be_saved(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'result.json'
            p = run_cli(['--format', 'json', '--output', str(output), 'task', 'validate', str(ROOT / 'docs' / 'tasks' / 'pipeline-tools-v1.md')])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            value = json.loads(p.stdout)
            self.assertEqual(value['schema'], 1)
            self.assertEqual(value['status'], 'pass')
            self.assertEqual(json.loads(output.read_text(encoding='utf-8')), value)

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

    def test_workflow_command_automatically_records_tracked_metric(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            task = root / 'task.md'
            task.write_text('''# Demo\n<!-- Task ID: demo -->\n```pipeline-contract\n{"schema":1,"task_id":"demo","allowed_paths":["src/**"],"forbidden_paths":[],"acceptance_tests":[{"id":"AT1","evidence_level":1,"test_ref":"tests/x.py","command_ref":"python -m unittest"}]}\n```\n''', encoding='utf-8')
            p = run_cli(['task', 'validate', str(task)], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            files = list((root / '.workflow' / 'metrics').glob('*.json'))
            self.assertEqual(len(files), 1)
            value = json.loads(files[0].read_text(encoding='utf-8'))
            self.assertEqual(value['event'], 'task_validate')
            self.assertEqual(value['confidence'], 'observed')
            self.assertEqual(value['task_id'], 'demo')
            self.assertEqual(value['result'], 'pass')
            self.assertEqual(value['source'], 'pipeline_tools')
            self.assertEqual(value['evidence_ref'], 'task.md')
            self.assertIsInstance(value['duration_s'], float)
            ignored = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '--no-index', '.workflow/metrics/event.json'], capture_output=True, text=True, timeout=60)
            self.assertNotEqual(ignored.returncode, 0)

    def test_automatic_timeout_records_feedback_event(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            log = root / 'timeout.log'
            p = run_cli(['command', 'run', '--cwd', str(root), '--log', str(log), '--timeout', '1', '--task-id', 'demo', '--', PY, '-c', 'import time; time.sleep(5)'], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 3, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            self.assertEqual({value['event'] for value in values}, {'command_run', 'timeout'})
            command = next(value for value in values if value['event'] == 'command_run')
            self.assertTrue(command['timed_out'])
            self.assertEqual(command['result'], 'blocked')
            timeout = next(value for value in values if value['event'] == 'timeout')
            self.assertEqual(timeout['result'], 'blocked')
            self.assertEqual(timeout['task_id'], 'demo')

    def test_automatic_command_uses_task_id_from_workflow_log_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            log = root / '.workflow' / 'demo' / 'test.log'
            p = run_cli(['command', 'run', '--cwd', str(root), '--log', str(log), '--timeout', '5', '--', PY, '-c', 'print("ok")'], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0]['task_id'], 'demo')
            self.assertEqual(values[0]['evidence_ref'], '.workflow/demo/test.log')

    def test_automatic_retry_records_first_retry_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = run_cli(['command', 'run', '--cwd', str(root), '--log', 'retry.log', '--timeout', '5', '--attempt', '1', '--', PY, '-c', 'print("ok")'], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            self.assertEqual({value['event'] for value in values}, {'command_run', 'retry'})
            retry = next(value for value in values if value['event'] == 'retry')
            self.assertEqual(retry['attempt'], 1)
            self.assertEqual(retry['reason'], 'attempt_1')

    def test_malformed_non_metrics_command_records_a_failure_metric(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = run_cli(['command', 'run', '--cwd', str(root)], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 2, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0]['event'], 'command_run')
            self.assertEqual(values[0]['result'], 'fail')

    def test_top_level_parse_error_records_a_failure_metric(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = run_cli(['not-a-command'], cwd=root, env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0', 'PYTHONPATH': str(ROOT)})
            self.assertEqual(p.returncode, 2, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0]['event'], 'cli_parse_error')

    def test_subcommand_help_records_a_help_metric(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = run_cli(['task', 'validate', '--help'], cwd=root, env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0', 'PYTHONPATH': str(ROOT)})
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0]['event'], 'cli_help')

    def test_automatic_metrics_redact_sensitive_path_components(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            log = root / '.workflow' / 'demo' / 'secret' / 'test.log'
            p = run_cli(['command', 'run', '--cwd', str(root), '--log', str(log), '--timeout', '5', '--task-id', 'demo', '--', PY, '-c', 'print("ok")'], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            self.assertEqual(len(values), 1)
            self.assertIsNone(values[0]['evidence_ref'])
            self.assertNotIn('secret', values[0]['task_id'].lower())

    def test_automatic_runtime_and_lifecycle_events_keep_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root, _ = make_repo(d)
            workflow = root / '.workflow' / 'demo'
            p = run_cli(['runtime', 'handshake', str(root), str(workflow), '--role', 'reviewer', '--node', '0.0.0'], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 3, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            handshake = next(value for value in values if value['event'] == 'runtime_handshake')
            self.assertEqual(handshake['task_id'], 'demo')
            self.assertEqual(handshake['evidence_ref'], '.workflow/demo/capability-handshake.json')
            p = run_cli(['lifecycle', 'status', str(root), '--task-id', 'demo', '--evidence', str(workflow)], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            lifecycle = next(value for value in values if value['event'] == 'lifecycle_status')
            self.assertEqual(lifecycle['task_id'], 'demo')
            self.assertEqual(lifecycle['evidence_ref'], '.workflow/demo')

    def test_metrics_commands_do_not_recursively_record_stage_metrics(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = run_cli(['metrics', 'record', str(root), 'manual', '--confidence', 'observed', '--task-id', 'demo'], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            p = run_cli(['metrics', 'report', str(root)], env={'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '0'})
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (root / '.workflow' / 'metrics').glob('*.json')]
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0]['event'], 'manual')

    def test_runtime_preflight_and_role_scope(self):
        with tempfile.TemporaryDirectory() as d:
            root, _ = make_repo(d)
            p = run_cli(['runtime', 'preflight', str(root), '--node', '0.0.0'])
            self.assertEqual(p.returncode, 3, (p.stdout, p.stderr))
            (root / 'src').mkdir()
            (root / 'src' / 'app.py').write_text('x', encoding='utf-8')
            p = run_cli(['runtime', 'role-scope', str(root), '--role', 'main-agent', '--product-pattern', 'src/**'])
            self.assertEqual(p.returncode, 4, (p.stdout, p.stderr))
            p = run_cli(['runtime', 'role-scope', str(root), '--role', 'main-agent', '--product-pattern', 'src/**', '--authorized'])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))

    def test_runtime_preflight_uses_windows_pnpm_command_name(self):
        import platform

        if platform.system() != 'Windows':
            self.skipTest('Windows command resolution only')
        with tempfile.TemporaryDirectory() as d:
            root, _ = make_repo(d)
            fake_bin = Path(d) / 'bin'
            fake_bin.mkdir()
            (fake_bin / 'pnpm.cmd').write_text('@echo 10.27.0\n', encoding='utf-8')
            env = {
                'PATH': str(fake_bin) + ';' + os.environ.get('PATH', ''),
                'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '1',
            }
            p = run_cli(['runtime', 'preflight', str(root), '--pnpm', '10.27.0'], env=env)
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            self.assertEqual(json.loads(p.stdout)['checks']['pnpm'], '10.27.0')

    def test_runtime_handshake_writes_machine_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root, _ = make_repo(d)
            workflow = root / '.workflow' / 'demo'
            p = run_cli(['runtime', 'handshake', str(root), str(workflow), '--role', 'reviewer'])
            self.assertEqual(p.returncode, 3, (p.stdout, p.stderr))
            self.assertTrue((workflow / 'capability-handshake.json').is_file())

    def test_import_opencode_session_cli(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            session = root / 'session.json'
            session.write_text('{"info":{"id":"ses_demo"},"messages":[]}', encoding='utf-8')
            p = run_cli(['metrics', 'import-opencode-session', str(root), str(session), '--task-id', 'demo'])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            self.assertIn('"imported": 0', p.stdout)

    def test_bin_wrappers_run(self):
        # AT6: wrappers must run; on Windows use .cmd via shell, on POSIX use the sh wrapper.
        import platform
        with tempfile.TemporaryDirectory() as d:
            if platform.system() == 'Windows':
                r = subprocess.run(['cmd', '/c', str(ROOT / 'bin' / 'pipeline-tools.cmd'), '--help'],
                                   capture_output=True, text=True, cwd=str(ROOT), timeout=60,
                                   env={**os.environ, 'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '1', 'PATH': os.environ.get('PATH', '') + ';C:\\Users\\alexc\\AppData\\Local\\Programs\\Python\\Python312'})
            else:
                r = subprocess.run([str(ROOT / 'bin' / 'pipeline-tools'), '--help'],
                                   capture_output=True, text=True, cwd=str(ROOT), timeout=60,
                                   env={**os.environ, 'PIPELINE_TOOLS_DISABLE_AUTO_METRICS': '1'})
            self.assertEqual(r.returncode, 0, (r.stdout, r.stderr))
            self.assertIn('task', r.stdout)

    def test_task_validate_real_sheet(self):
        p = run_cli(['task', 'validate', str(ROOT / 'docs' / 'tasks' / 'pipeline-tools-v1.md')])
        self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
        p = run_cli(['task', 'validate', str(ROOT / 'nope.md')])
        self.assertEqual(p.returncode, 2, (p.stdout, p.stderr))

    def test_lifecycle_status_is_structured_and_starts_with_executor(self):
        with tempfile.TemporaryDirectory() as d:
            root, _ = make_repo(d)
            evidence = root / '.workflow' / 'demo'
            p = run_cli(['--format', 'json', 'lifecycle', 'status', str(root), '--task-id', 'demo', '--evidence', str(evidence)])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            value = json.loads(p.stdout)
            self.assertEqual(value['status'], 'ready')
            self.assertEqual(value['phase'], 'executor')
            self.assertIn('dispatch_executor', value['next_actions'])

    def test_dispatch_result_and_freshness_form_machine_closed_loop(self):
        with tempfile.TemporaryDirectory() as d:
            root, head = make_repo(d)
            dispatch = root / 'dispatch.json'
            dispatch.write_text(json.dumps({
                'schema': 1, 'task_id': 'demo', 'role': 'reviewer', 'round': 1,
                'root': '.', 'worktree': '.', 'branch': 'main',
                'evidence_dir': '.workflow/demo',
                'permissions': {'write_workflow': True, 'write_product': False},
                'output': {'result': '.workflow/demo/reviewer-result.json'},
            }), encoding='utf-8')
            out = root / '.workflow' / 'demo' / 'dispatch.json'
            p = run_cli(['dispatch', 'write', str(dispatch), str(out)])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            evidence = root / '.workflow' / 'demo' / 'evidence.log'
            evidence.write_text('observed', encoding='utf-8')
            result = root / '.workflow' / 'demo' / 'reviewer-result.json'
            result.write_text(json.dumps({
                'schema': 1, 'task_id': 'demo', 'role': 'reviewer', 'status': 'pass',
                'identity': {'head': head}, 'acceptance': [{'id': 'AT1', 'status': 'pass', 'exit_code': 0, 'evidence_refs': ['.workflow/demo/evidence.log']}],
                'unverified': [],
            }), encoding='utf-8')
            p = run_cli(['result', 'verify', str(result), '--task-id', 'demo', '--role', 'reviewer'])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            p = run_cli(['--format', 'json', 'freshness', str(root), str(root / '.workflow' / 'demo'), '--result', str(result)])
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
            self.assertEqual(json.loads(p.stdout)['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
