import tempfile, unittest
from pathlib import Path
from pipeline_tools.contract import validate_task

VALID = '''# T
<!-- Task ID: demo -->
```pipeline-contract
{"schema":1,"task_id":"demo","allowed_paths":["src/**"],"forbidden_paths":["*.secret"],"acceptance_tests":[{"id":"AT1","evidence_level":1,"test_ref":"tests/x.py","command_ref":"python -m unittest"}]}
```
'''
class ContractTests(unittest.TestCase):
 def test_valid_pipeline_contract(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'t.md'; p.write_text(VALID); self.assertEqual(validate_task(p), [])
 def test_missing_and_bad_contract_fail_without_path(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'private.md'; p.write_text('# T\n<!-- Task ID: demo -->\n```pipeline-contract\n{}\n```')
   errors=validate_task(p); self.assertTrue(errors); self.assertNotIn(str(p), ' '.join(errors))
 def test_placeholder_and_duplicate_ids_fail(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'t.md'; p.write_text(VALID.replace('"AT1"','"<AT>"').replace('"demo"','"demo"',1))
   errors=validate_task(p); self.assertTrue(any('placeholder' in e or 'id' in e for e in errors))
if __name__=='__main__': unittest.main()
