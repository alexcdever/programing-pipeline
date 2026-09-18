import subprocess, tempfile, unittest
from pathlib import Path
from pipeline_tools.core import freeze_check, scope_check

class GitChecks(unittest.TestCase):
    def test_untracked_forbidden_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); subprocess.run(['git','init'],cwd=p,capture_output=True)
            (p/'ok.txt').write_text('x'); (p/'bad.secret').write_text('x')
            self.assertEqual(scope_check(p,['ok.txt'],['*.secret']),['bad.secret'])

    def test_freeze_requires_ancestor_contract(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); subprocess.run(['git','init'],cwd=p,capture_output=True)
            subprocess.run(['git','config','user.email','test@example.invalid'],cwd=p)
            subprocess.run(['git','config','user.name','Test'],cwd=p)
            (p/'x').write_text('x'); subprocess.run(['git','add','.'],cwd=p); subprocess.run(['git','commit','-m','base'],cwd=p,capture_output=True)
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip()
            self.assertEqual(freeze_check(p,head),[])
            self.assertTrue(freeze_check(p,'deadbeef'))

if __name__=='__main__': unittest.main()
