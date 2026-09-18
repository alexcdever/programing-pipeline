import tempfile, unittest, sys
from pathlib import Path
from pipeline_tools.core import run_command, BLOCKED
class RunnerTests(unittest.TestCase):
 def test_success_and_timeout(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); ok=run_command([sys.executable,'-c','print("ok")'],p,p/'ok.log'); self.assertEqual(ok['exit_code'],0); self.assertIn('ok', (p/'ok.log').read_text())
   slow=run_command([sys.executable,'-c','import time; time.sleep(2)'],p,p/'slow.log',.05); self.assertEqual(slow['exit_code'],BLOCKED); self.assertTrue(slow['timed_out'])
 def test_secret_is_redacted(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); result=run_command([sys.executable,'-c','print("token=abc123 C:/Users/alex/file")'],p,p/'secret.log'); self.assertNotIn('abc123',result['output']); self.assertNotIn('C:/Users/alex',result['output'])
if __name__=='__main__': unittest.main()
