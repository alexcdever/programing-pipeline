# Review rerun phase F: task validate failure modes (fail-closed, no abs paths, no PASS)
import subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(r"D:/Projects/Skills/programing-pipeline-tools")

def cli(*a):
    r = subprocess.run([sys.executable, "-m", "pipeline_tools", "task", "validate", *a],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=60)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def p(*a):
    print(*a)

p("# phase F contract fail-modes — date:", time.strftime("%Y-%m-%dT%H:%M:%S%z"))

HEAD = "<!-- Task ID: demo -->"
OK = ('{"schema":1,"task_id":"demo","allowed_paths":["src/**"],"forbidden_paths":["*.env"],'
      '"acceptance_tests":[{"id":"AT1","evidence_level":2,"test_ref":"tests/x.py",'
      '"command_ref":"python -m unittest"}]}')

def sheet(body):
    return "# T\n" + HEAD + "\n```pipeline-contract\n" + body + "\n```\n"

cases = {
    "F1 missing forbidden_paths":
        '{"schema":1,"task_id":"demo","allowed_paths":["src/**"],"acceptance_tests":[{"id":"AT1","evidence_level":2,"test_ref":"t","command_ref":"c"}]}',
    "F2 invalid JSON":
        '{"schema":1, ',
    "F3 placeholder command_ref":
        '{"schema":1,"task_id":"demo","allowed_paths":["a"],"forbidden_paths":["b"],"acceptance_tests":[{"id":"AT1","evidence_level":2,"test_ref":"t","command_ref":"<cmd>"}]}',
    "F4 missing evidence_level":
        '{"schema":1,"task_id":"demo","allowed_paths":["a"],"forbidden_paths":["b"],"acceptance_tests":[{"id":"AT1","test_ref":"t","command_ref":"c"}]}',
    "F5 evidence_level out of range":
        '{"schema":1,"task_id":"demo","allowed_paths":["a"],"forbidden_paths":["b"],"acceptance_tests":[{"id":"AT1","evidence_level":9,"test_ref":"t","command_ref":"c"}]}',
    "F6 duplicate ids":
        '{"schema":1,"task_id":"demo","allowed_paths":["a"],"forbidden_paths":["b"],"acceptance_tests":[{"id":"AT1","evidence_level":1,"test_ref":"t","command_ref":"c"},{"id":"AT1","evidence_level":1,"test_ref":"t","command_ref":"c"}]}',
    "F7 task_id mismatch":
        '{"schema":1,"task_id":"other","allowed_paths":["a"],"forbidden_paths":["b"],"acceptance_tests":[{"id":"AT1","evidence_level":1,"test_ref":"t","command_ref":"c"}]}',
    "F8 schema not 1":
        '{"schema":2,"task_id":"demo","allowed_paths":["a"],"forbidden_paths":["b"],"acceptance_tests":[{"id":"AT1","evidence_level":1,"test_ref":"t","command_ref":"c"}]}',
    "F9 traversal in allowed_paths":
        '{"schema":1,"task_id":"demo","allowed_paths":["../evil/**"],"forbidden_paths":["b"],"acceptance_tests":[{"id":"AT1","evidence_level":1,"test_ref":"t","command_ref":"c"}]}',
    "F10 no contract block": None,
    "F11 two contract blocks": "DOUBLE",
}

with tempfile.TemporaryDirectory() as d:
    for name, body in cases.items():
        if body == "DOUBLE":
            text = sheet(OK) + sheet(OK)
        elif body is None:
            text = "# T\n" + HEAD + "\nplain text only\n"
        else:
            text = sheet(body)
        f = Path(d) / "sheet.md"
        f.write_text(text, encoding="utf-8")
        rc, out, err = cli(str(f))
        leak = str(d) in (out or "") or str(d) in (err or "")
        print(f"{name}: exit={rc} out={out[:130]!r} abs_path_leak={leak}")
        assert rc == 2, f"{name}: expected CONFIG(2), got {rc}"
        assert not (out or "").startswith("PASS"), f"{name}: printed PASS"
        assert not leak, f"{name}: leaked absolute path"

p("")
p("ALL F CASES: exit 2, no PASS, no absolute-path leak — fail-closed CONFIRMED")
