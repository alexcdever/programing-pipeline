"""Mechanical workflow checks, bounded command execution, and local metrics."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

PASS, FAIL, CONFIG, BLOCKED, DRIFT = 0, 1, 2, 3, 4
REPORT_NAMES = ("executor-report.md", "review-report.md", "final-check.md")
CONFIDENCES = {"observed", "derived", "reported"}
METRIC_RESULTS = {"pass", "passed", "fail", "failed", "blocked", "flaky", "unknown"}

_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|token|secret|authorization|api[_-]?key|cvc)\b"
    r"(\s*[=:]\s*)[^\s,;]+"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/]|/Users/|/home/)[^\r\n\t\s,;]+")


def redact(value: Any) -> str:
    """Redact secrets and common local identity paths before output is persisted."""
    text = str(value or "")
    text = _SECRET_RE.sub(r"\1\2<redacted>", text)
    text = _BEARER_RE.sub("Bearer <redacted>", text)
    return _PATH_RE.sub("<path>", text)


def git(root: Path, *args: str, timeout: float = 20) -> tuple[int, str]:
    """Run a read-only Git command with a bounded wait."""
    if not root.is_dir():
        return CONFIG, "working directory does not exist"
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return CONFIG, "git executable not found"
    except subprocess.TimeoutExpired:
        return CONFIG, "git command timed out"
    # Do NOT strip: porcelain output is column-sensitive (a leading space is
    # part of the XY status code for the first line).
    return result.returncode, redact((result.stdout or "") + (result.stderr or ""))


def _write_log(path: Path, content: str) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"unable to write log: {type(exc).__name__}"
    return None


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    try:
        process.kill()
    except (OSError, ProcessLookupError):
        pass


def run_command(command: list[str], cwd: Path, log: Path, timeout: float = 30) -> dict[str, Any]:
    """Run a command without a shell and return a bounded, redacted result."""
    command = list(command)
    if command and command[0] == "--":
        command = command[1:]
    if not command or timeout <= 0:
        raise ValueError("command and positive timeout required")
    if not cwd.is_dir():
        raise ValueError("working directory does not exist")

    log_path = log if log.is_absolute() else cwd / log
    started = time.monotonic()
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **kwargs)
    except (OSError, ValueError) as exc:
        content = redact(f"{type(exc).__name__}: {exc}")
        log_error = _write_log(log_path, content)
        return {
            "status_code": CONFIG,
            "exit_code": None,
            "timed_out": False,
            "duration_s": round(time.monotonic() - started, 3),
            "log": str(log_path),
            "output": content,
            "error": log_error or "command could not start",
        }

    timed_out = False
    try:
        output, _ = process.communicate(timeout=timeout)
        exit_code = process.returncode
        status_code = PASS if exit_code == 0 else FAIL
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            output = "process did not terminate during cleanup"
            _terminate_process_tree(process)
        # The public exit_code is the workflow result for a timeout.
        exit_code = BLOCKED
        status_code = BLOCKED

    content = redact(output or "")
    log_error = _write_log(log_path, content)
    if log_error:
        status_code = CONFIG
    return {
        "status_code": status_code,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_s": round(time.monotonic() - started, 3),
        "log": str(log_path),
        "output": content,
        "error": log_error,
    }


def _normalize_path(value: str) -> str:
    value = value.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.rstrip("/") if value != "/" else value


def _matches(path: str, pattern: str, root: Path | None = None) -> bool:
    path = _normalize_path(path)
    pattern = _normalize_path(pattern)
    if fnmatch.fnmatchcase(path, pattern):
        return True
    if root is not None and (
        Path(pattern).is_absolute() or bool(re.match(r"^[A-Za-z]:/", pattern))
    ):
        absolute_path = _normalize_path(str((root / path).resolve()))
        if fnmatch.fnmatchcase(absolute_path, pattern):
            return True
    if pattern.endswith("/**"):
        base = pattern[:-3].rstrip("/")
        return path == base or path.startswith(base + "/")
    return False


def _status_paths(output: str) -> list[str]:
    paths: set[str] = set()
    for line in output.splitlines():
        if len(line) < 4:
            continue
        # Porcelain codes are exactly two columns. git() must preserve the
        # output's leading space so the path always begins at column three.
        value = line[3:]
        if " -> " in value:
            value = value.rsplit(" -> ", 1)[1]
        value = value.strip().strip('"').replace("\\", "/")
        if value:
            paths.add(value)
    return sorted(paths)


def scope_check(root: Path, allowed: list[str], forbidden: list[str]) -> list[str]:
    """Return changed paths outside the allow-list or inside the deny-list."""
    rc, output = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if rc:
        return [output or "not a git repository"]
    allowed = allowed or []
    forbidden = forbidden or []
    bad = []
    for path in _status_paths(output):
        if any(_matches(path, pattern, root) for pattern in forbidden) or not any(
            _matches(path, pattern, root) for pattern in allowed
        ):
            bad.append(path)
    return bad


def _validate_evidence_ref(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.replace(chr(92), "/")
    return not (
        Path(normalized).is_absolute()
        or bool(re.match(r"^[A-Za-z]:/", normalized))
        or normalized.startswith("/")
        or ".." in normalized.split("/")
    )


def _evidence_root(directory: Path) -> Path:
    # Standard layout: <project>/.workflow/<task-id>/.
    if directory.parent.name == ".workflow":
        return directory.parent.parent
    return directory


def _evidence_file_exists(directory: Path, reference: Any) -> bool:
    if not _validate_evidence_ref(reference):
        return False
    root = _evidence_root(directory)
    candidate = root / str(reference).replace(chr(92), "/")
    return candidate.is_file()


def _read_machine_evidence(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, ["unreadable"]

    lines = text.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.strip() == "```pipeline-evidence"
    ]
    if len(starts) != 1:
        return None, ["missing or duplicate pipeline-evidence block"]
    start = starts[0]
    ends = [
        index
        for index in range(start + 1, len(lines))
        if lines[index].strip() == "```"
    ]
    if len(ends) != 1:
        return None, ["pipeline-evidence block is not closed exactly once"]
    body = "\n".join(lines[start + 1 : ends[0]])
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        return None, ["pipeline-evidence JSON is invalid"]
    if not isinstance(value, dict):
        return None, ["pipeline-evidence must be an object"]
    return value, []


def evidence_verify(directory: Path, task_id: str, branch: str | None = None) -> list[str]:
    """Verify machine-readable report identity and minimum evidence fields."""
    errors: list[str] = []
    reports: dict[str, dict[str, Any]] = {}
    valid_statuses = {
        "PASS",
        "FAIL",
        "BLOCKED",
        "FLAKY",
        "EXPLORATORY_ONLY",
        "READY-TO-MERGE",
        "MERGED",
    }
    expected_roles = {
        "executor-report.md": "executor",
        "review-report.md": "reviewer",
        "final-check.md": "main-final",
    }
    required = (
        "schema",
        "task_id",
        "worktree",
        "branch",
        "role",
        "round",
        "status",
        "commands",
        "assertions",
        "evidence_refs",
        "unverified",
    )

    for name in REPORT_NAMES:
        path = directory / name
        if not path.is_file():
            errors.append(f"missing {name}")
            continue
        if not path.read_text(encoding="utf-8", errors="replace").strip():
            errors.append(f"{name} is empty")
            continue
        value, parse_errors = _read_machine_evidence(path)
        if parse_errors:
            errors.extend(f"{name}: {item}" for item in parse_errors)
            continue
        assert value is not None
        reports[name] = value

        for field in required:
            if field not in value:
                errors.append(f"{name} missing field: {field}")
        if value.get("schema") != 1:
            errors.append(f"{name} schema must be 1")
        if value.get("task_id") != task_id:
            errors.append(f"{name} task identity mismatch")
        if branch and value.get("branch") != branch:
            errors.append(f"{name} branch mismatch")
        if value.get("role") != expected_roles[name]:
            errors.append(f"{name} role mismatch")
        if not isinstance(value.get("worktree"), str) or not value.get("worktree"):
            errors.append(f"{name} worktree must be non-empty")
        if isinstance(value.get("round"), bool) or not isinstance(value.get("round"), int) or value.get("round", 0) < 1:
            errors.append(f"{name} round must be a positive integer")
        if value.get("status") not in valid_statuses:
            errors.append(f"{name} status is invalid")

        commands = value.get("commands")
        if not isinstance(commands, list) or not commands:
            errors.append(f"{name} commands must be non-empty")
        else:
            for index, command in enumerate(commands, start=1):
                if not isinstance(command, dict):
                    errors.append(f"{name} command {index} must be an object")
                    continue
                if not isinstance(command.get("command"), str) or not command.get("command"):
                    errors.append(f"{name} command {index} has no command")
                if isinstance(command.get("exit_code"), bool) or not isinstance(command.get("exit_code"), int):
                    errors.append(f"{name} command {index} has no numeric exit_code")
                elif not _evidence_file_exists(directory, command.get("evidence_ref")):
                    errors.append(f"{name} command {index} evidence_ref is missing or not relative")

        assertions = value.get("assertions")
        if not isinstance(assertions, list) or not assertions or any(
            not isinstance(item, str) or not item.strip() for item in assertions
        ):
            errors.append(f"{name} assertions must be non-empty strings")
        refs = value.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{name} evidence_refs must be non-empty")
        else:
            for reference in refs:
                if not _evidence_file_exists(directory, reference):
                    errors.append(f"{name} evidence_ref is missing or not relative")
        if not isinstance(value.get("unverified"), list):
            errors.append(f"{name} unverified must be an array")

    return errors


def _metrics_dir(root: Path) -> Path:
    return root / ".workflow" / "metrics"


def _safe_identifier(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", str(value or "unknown"))
    return cleaned or "unknown"


def _relative_reference(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace(chr(92), "/")
    if not text or Path(text).is_absolute() or text.startswith(("/", "../")):
        return None
    if ".." in text.split("/"):
        return None
    return text


def metric_event(root: Path, event: dict[str, Any]) -> Path:
    """Write one allow-listed, local, atomic metric event."""
    confidence = event.get("confidence")
    if confidence not in CONFIDENCES:
        raise ValueError("invalid confidence")
    name = event.get("event")
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError("event must be a non-empty short string")
    result = event.get("result")
    if result is not None and result not in METRIC_RESULTS and result not in (0, 1):
        raise ValueError("invalid result")
    token_count = event.get("token_count")
    if token_count is not None and (
        isinstance(token_count, bool) or not isinstance(token_count, int) or token_count < 0
    ):
        raise ValueError("token_count must be a non-negative integer or null")
    evidence_ref = event.get("evidence_ref")
    if evidence_ref is not None and not _validate_evidence_ref(evidence_ref):
        raise ValueError("evidence_ref must be a project-relative path or null")

    clean: dict[str, Any] = {
        "schema": 1,
        "event_id": uuid.uuid4().hex,
        "recorded_at": time.time_ns(),
        "event": _safe_identifier(name),
        "confidence": confidence,
        "task_id": _safe_identifier(event.get("task_id", "unknown")),
        "result": result if result is not None else "unknown",
        "duration_s": event.get("duration_s"),
        "timed_out": event.get("timed_out"),
        "token_count": token_count,
        "reason": _safe_identifier(event["reason"]) if event.get("reason") else None,
        "attempt": event.get("attempt", 0),
        "evidence_ref": _relative_reference(evidence_ref),
    }
    if clean["duration_s"] is not None and (
        isinstance(clean["duration_s"], bool)
        or not isinstance(clean["duration_s"], (int, float))
        or clean["duration_s"] < 0
    ):
        raise ValueError("duration_s must be non-negative or null")
    if not isinstance(clean["timed_out"], (bool, type(None))):
        raise ValueError("timed_out must be boolean or null")
    if isinstance(clean["attempt"], bool) or not isinstance(clean["attempt"], int) or clean["attempt"] < 0:
        raise ValueError("attempt must be a non-negative integer")

    directory = _metrics_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{clean['recorded_at']}-{clean['event_id']}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(clean, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)
    return target


def _load_metric_events(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    invalid: list[str] = []
    directory = _metrics_dir(root)
    if not directory.is_dir():
        return rows, invalid
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("schema") != 1:
                raise ValueError("invalid schema")
            if value.get("confidence") not in CONFIDENCES:
                raise ValueError("invalid confidence")
            rows.append(value)
        except (OSError, json.JSONDecodeError, ValueError):
            invalid.append(path.name)
    return rows, invalid


def aggregate(root: Path) -> dict[str, Any]:
    rows, invalid = _load_metric_events(root)
    if invalid:
        raise ValueError(f"invalid metric event files: {len(invalid)}")
    core = [row for row in rows if row.get("confidence") in {"observed", "derived"}]
    reported = [row for row in rows if row.get("confidence") == "reported"]
    passed = sum(row.get("result") in {"pass", "passed", 0} for row in core)
    failed = sum(row.get("result") in {"fail", "failed", 1} for row in core)
    known = passed + failed
    token_values = [row["token_count"] for row in core if isinstance(row.get("token_count"), int)]
    event_counts = {
        name: sum(row.get("event") == name for row in core)
        for name in (
            "review_overturn",
            "retry",
            "timeout",
            "evidence_gap",
            "post_merge_regression",
        )
    }
    return {
        "schema": 1,
        "events": len(rows),
        "core_events": len(core),
        "reported_events": len(reported),
        "passed": passed,
        "failed": failed,
        "blocked": sum(row.get("result") == "blocked" for row in core),
        "flaky": sum(row.get("result") == "flaky" for row in core),
        "unknown_results": sum(row.get("result") == "unknown" for row in core),
        "success_rate": passed / known if known else None,
        "token_count_total": sum(token_values) if token_values else None,
        "token_count_unknown": sum(row.get("token_count") is None for row in core),
        "review_overturns": event_counts["review_overturn"],
        "retries": event_counts["retry"] + sum(row.get("attempt", 0) > 0 for row in core),
        "timeouts": event_counts["timeout"] + sum(row.get("timed_out") is True for row in core),
        "evidence_gaps": event_counts["evidence_gap"],
        "post_merge_regressions": event_counts["post_merge_regression"],
    }


def purge_metrics(root: Path) -> int:
    directory = _metrics_dir(root)
    if not directory.is_dir():
        return 0
    count = 0
    for pattern in ("*.json", "*.tmp"):
        for path in directory.glob(pattern):
            path.unlink()
            count += 1
    return count


def gate_check(directory: Path, task_id: str, branch: str | None, phase: str) -> list[str]:
    """Run evidence checks and the minimum phase-specific merge gates."""
    errors = evidence_verify(directory, task_id, branch)
    root = _evidence_root(directory)
    reports: dict[str, dict[str, Any]] = {}
    for name in REPORT_NAMES:
        value, parse_errors = _read_machine_evidence(directory / name)
        if not parse_errors and value is not None:
            reports[name] = value

    # Structural verification and a merge gate are intentionally separate:
    # a report may accurately say BLOCKED, but that must block merging.
    for name, value in reports.items():
        status = value.get("status")
        if phase == "pre-merge" and name in {"executor-report.md", "review-report.md", "final-check.md"}:
            if status not in {"PASS", "READY-TO-MERGE"}:
                errors.append(f"{name} status is not mergeable")
        if phase == "post-merge" and name != "executor-report.md" and status not in {"PASS", "READY-TO-MERGE", "MERGED"}:
            errors.append(f"{name} status is not post-merge passing")
        for command in value.get("commands", []):
            if isinstance(command, dict) and command.get("exit_code") != 0:
                errors.append(f"{name} contains a non-zero command exit_code")

    if (root / ".git").exists() or (root / ".git").is_file():
        rc, _ = git(root, "diff", "--check")
        if rc:
            errors.append("git diff --check failed")
        rc, output = git(root, "ls-files", "-u")
        if rc:
            errors.append("unable to inspect conflict index")
        elif output.strip():
            errors.append("unmerged entries present")
        if phase == "post-merge":
            rc, _ = git(root, "rev-parse", "--verify", "HEAD")
            if rc:
                errors.append("merged HEAD unavailable")
    return errors


# Backwards-compatible name used by the first CLI draft.
def freeze_check(
    root: Path,
    contract: str,
    expected_head: str | None = None,
    expected_branch: str | None = None,
    expected_worktree: Path | None = None,
) -> list[str]:
    """Verify contract ancestry and optional HEAD/branch/worktree identity."""
    errors: list[str] = []
    rc, _ = git(root, "rev-parse", "--verify", "HEAD")
    if rc:
        return ["not a git repository"]
    rc, _ = git(root, "cat-file", "-e", f"{contract}^{{commit}}")
    if rc:
        return ["contract commit unavailable"]
    rc, _ = git(root, "merge-base", "--is-ancestor", contract, "HEAD")
    if rc:
        errors.append("contract commit is not an ancestor")
    if expected_head:
        rc, actual = git(root, "rev-parse", "HEAD")
        if rc or actual.strip() != expected_head:
            errors.append("HEAD does not match expected head")
    if expected_branch:
        rc, actual = git(root, "branch", "--show-current")
        if rc or actual.strip() != expected_branch:
            errors.append("branch does not match expected branch")
    if expected_worktree:
        rc, actual = git(root, "rev-parse", "--show-toplevel")
        try:
            expected = expected_worktree.resolve()
            actual_path = Path(actual.strip()).resolve()
        except (OSError, ValueError):
            errors.append("worktree identity cannot be resolved")
        else:
            if rc or actual_path != expected:
                errors.append("worktree does not match expected worktree")
    return errors
