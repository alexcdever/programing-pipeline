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
            subprocess.run(['git','branch','-M','main'],cwd=p,check=True,capture_output=True)
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip()
            self.assertEqual(freeze_check(p,head),[])
            self.assertEqual(
                freeze_check(p,head,expected_head=head,expected_branch='main',expected_worktree=p),
                [],
            )
            self.assertTrue(freeze_check(p,'deadbeef'))
            self.assertTrue(freeze_check(p,head,expected_branch='wrong'))
            self.assertTrue(freeze_check(p,head,expected_worktree=Path(d)/'other'))

    def test_absolute_scope_pattern_matches_repository_path(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); subprocess.run(['git','init'],cwd=p,capture_output=True)
            (p/'ok.txt').write_text('x')
            absolute_pattern = str((p/'ok.txt')).replace('\\\\','/')
            self.assertEqual(scope_check(p,[absolute_pattern],[]),[])

if __name__=='__main__': unittest.main()
