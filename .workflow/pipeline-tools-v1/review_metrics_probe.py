# Review rerun phase D: metrics record/report/export/purge + redaction (reviewer-run)
# All output goes to stdout; the reviewer tee's it into review-metrics.log
import json, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(r"D:/Projects/Skills/programing-pipeline-tools")

def cli(*a):
    r = subprocess.run([sys.executable, "-m", "pipeline_tools", *a],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=60)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def p(*a):
    print(*a)

p("# phase D metrics — date:", time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cwd:", ROOT)

with tempfile.TemporaryDirectory() as d:
    root = Path(d)

    p("\n== D1 record observed pass, task-id 'a/b' (unsafe chars), abs evidence-ref, no token ==")
    rc, out, err = cli("metrics", "record", str(root), "test", "--confidence", "observed",
                       "--task-id", "a/b", "--result", "pass",
                       "--evidence-ref", str(root / "x.log"))
    p("exit", rc, "| out:", out, "| err:", err)

    p("\n== D2 record reported pass (must NOT enter core) + derived fail token-count 12 ==")
    rc2, out2, e2 = cli("metrics", "record", str(root), "test", "--confidence", "reported",
                        "--task-id", "x", "--result", "pass")
    p("exit", rc2, out2, e2)
    rc3, out3, e3 = cli("metrics", "record", str(root), "test", "--confidence", "derived",
                        "--task-id", "x", "--result", "fail", "--token-count", "12")
    p("exit", rc3, out3, e3)

    p("\n== D3 metrics report ==")
    rc, out, err = cli("metrics", "report", str(root))
    p("exit", rc, "| out:", out)
    agg = json.loads(out)
    p("core_events:", agg["core_events"], "| reported_events:", agg["reported_events"],
      "| passed:", agg["passed"], "| failed:", agg["failed"],
      "| success_rate:", agg["success_rate"], "| token_count_total:", agg["token_count_total"])
    assert agg["core_events"] == 2 and agg["reported_events"] == 1, "core/reported split wrong"
    # if 'reported' leaked into the rate it would be 2/3 instead of 1/2
    assert agg["success_rate"] == 0.5, "reported leaked into success_rate"
    assert agg["token_count_total"] == 12, "token count wrong"
    p("ASSERT OK: reported excluded from success_rate; token total from core events only")

    p("\n== D4 raw event files: sanitization scan ==")
    files = sorted((root / ".workflow" / "metrics").glob("*.json"))
    raw = "\n".join(fp.read_text(encoding="utf-8") for fp in files)
    p("files:", [fp.name for fp in files])
    p("contains absolute temp path:", str(root) in raw,
      "| contains 'a/b':", "a/b" in raw,
      "| contains 'a_b' (sanitized):", "a_b" in raw,
      "| contains null token:", '"token_count": null' in raw)
    first = json.loads(files[0].read_text(encoding="utf-8"))
    p("event keys:", sorted(first.keys()))
    p("task_id:", first.get("task_id"), "| evidence_ref:", first.get("evidence_ref"),
      "| token_count:", first.get("token_count"))
    assert "a/b" not in raw and str(root) not in raw, "sanitization failed"
    assert first.get("task_id") == "a_b", "task id not sanitized to safe charset"

    p("\n== D5 export + purge + rebuild (evidence dirs survive purge) ==")
    rc, out, err = cli("metrics", "export", str(root), str(root / "export.json"))
    p("export exit", rc)
    p("export file exists:", (root / "export.json").exists(),
      "| same aggregate:", json.loads((root / "export.json").read_text(encoding="utf-8")) == agg)
    (root / ".workflow" / "demo-task").mkdir(parents=True, exist_ok=True)
    (root / ".workflow" / "demo-task" / "executor-report.md").write_text("keep", encoding="utf-8")
    rc, out, err = cli("metrics", "purge", str(root))
    p("purge exit", rc, "| out:", out)
    p("events after purge:", list((root / ".workflow" / "metrics").glob("*.json")))
    p("evidence dir survived purge:",
      (root / ".workflow" / "demo-task" / "executor-report.md").exists())
    rc, out, err = cli("metrics", "report", str(root))
    p("report after purge exit", rc, "| out:", out)
    p("aggregate rebuildable from zero events:", json.loads(out)["events"] == 0)

    p("\n== D6 invalid confidence must be CONFIG(2), fail-closed ==")
    rc, out, err = cli("metrics", "record", str(root), "test", "--confidence",
                       "guessed", "--task-id", "x")
    p("exit", rc, "| err:", (err or "").splitlines()[0] if err else "")

    p("\n== D7 malformed event file makes aggregate fail-closed ==")
    (root / ".workflow" / "metrics").mkdir(parents=True, exist_ok=True)
    (root / ".workflow" / "metrics" / "bad.json").write_text("{not json", encoding="utf-8")
    rc, out, err = cli("metrics", "report", str(root))
    p("exit", rc, "| err:", err)

p("\nPHASE D DONE")
