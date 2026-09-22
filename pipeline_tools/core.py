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
import hashlib
from pathlib import Path
from typing import Any

from .layout import active_pipeline_dir, evidence_root, is_metrics_path, metrics_dirs

PASS, FAIL, CONFIG, BLOCKED, DRIFT = 0, 1, 2, 3, 4
REPORT_NAMES = ("executor-report.md", "review-report.md", "final-check.md")
CONFIDENCES = {"observed", "derived", "reported"}
METRIC_RESULTS = {"pass", "passed", "fail", "failed", "blocked", "flaky", "unknown"}
BLOCKER_CLASSES = {"product", "environment", "permission", "evidence", "dependency", "workflow", None}

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


def git(
    root: Path,
    *args: str,
    timeout: float = 20,
    redact_output: bool = True,
) -> tuple[int, str]:
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
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, redact(output) if redact_output else output


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
        # Automatically generated metrics are workflow metadata and may be
        # tracked by the host project. They must not turn every frozen task
        # scope check into a product-scope failure.
        normalized = _normalize_path(path)
        forbidden_match = any(_matches(path, pattern, root) for pattern in forbidden)
        allowed_match = any(_matches(path, pattern, root) for pattern in allowed)
        if is_metrics_path(normalized) and not forbidden_match:
            continue
        if forbidden_match or not allowed_match:
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
    return evidence_root(directory)


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
    return active_pipeline_dir(root) / "metrics"


def _metric_bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def evidence_readiness(directory: Path, task_id: str) -> dict[str, Any]:
    """Check whether the evidence set is ready for formal verification."""
    required = ["executor-report.md", "review-report.md", "final-check.md"]
    missing = [name for name in required if not (directory / name).is_file()]
    result = "ready" if not missing else "not_ready"
    return {
        "schema": 1,
        "command": "evidence.readiness",
        "task_id": task_id,
        "status": result,
        "missing": missing,
        "errors": [],
        "blockers": [] if not missing else [{"class": "evidence", "reason": "missing evidence artifacts"}],
        "observed": [{"fact": "required_evidence", "value": required}],
        "next_actions": [] if not missing else ["complete_evidence_set"],
        "unverified": [] if not missing else ["formal evidence verification"],
    }


def _safe_identifier(value: Any) -> str:
    text = str(value or "")
    if (
        re.search(r"(?i)(secret|token|password|api[_-]?key|passwd|authorization|cvc)", text)
        or _BEARER_RE.search(text)
    ):
        return "unknown"
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
    if (
        any(re.search(r"(?i)(secret|token|password|api[_-]?key|passwd|authorization|cvc)", part) for part in text.split("/"))
        or _BEARER_RE.search(text)
    ):
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
    evidence_root = event.get("evidence_root")
    if evidence_root is not None and not _validate_evidence_ref(evidence_root):
        raise ValueError("evidence_root must be a project-relative path or null")
    blocker_class = event.get("blocker_class")
    if blocker_class not in BLOCKER_CLASSES:
        raise ValueError("invalid blocker_class")

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
        "evidence_root": _relative_reference(evidence_root),
        "blocker_class": blocker_class,
        "source": _safe_identifier(event["source"]) if event.get("source") else None,
        "run_id": _safe_identifier(event["run_id"]) if event.get("run_id") else None,
        "phase": _safe_identifier(event["phase"]) if event.get("phase") else None,
        "role": _safe_identifier(event["role"]) if event.get("role") else None,
        "head": _safe_identifier(event["head"]) if event.get("head") else None,
        "branch": _safe_identifier(event["branch"]) if event.get("branch") else None,
        "terminal": event.get("terminal"),
        "supersedes": _safe_identifier(event["supersedes"]) if event.get("supersedes") else None,
    }
    if clean["duration_s"] is not None and (
        isinstance(clean["duration_s"], bool)
        or not isinstance(clean["duration_s"], (int, float))
        or clean["duration_s"] < 0
    ):
        raise ValueError("duration_s must be non-negative or null")
    if not isinstance(clean["timed_out"], (bool, type(None))):
        raise ValueError("timed_out must be boolean or null")
    if not isinstance(clean["terminal"], (bool, type(None))):
        raise ValueError("terminal must be boolean or null")
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
    seen_event_ids: set[str] = set()
    for directory in metrics_dirs(root):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, dict) or value.get("schema") != 1:
                    raise ValueError("invalid schema")
                if value.get("confidence") not in CONFIDENCES:
                    raise ValueError("invalid confidence")
                event_id = value.get("event_id")
                if isinstance(event_id, str) and event_id in seen_event_ids:
                    continue
                if isinstance(event_id, str):
                    seen_event_ids.add(event_id)
                value.setdefault("terminal", None)
                value.setdefault("run_id", None)
                value.setdefault("phase", None)
                value.setdefault("role", None)
                value.setdefault("head", None)
                value.setdefault("branch", None)
                value.setdefault("evidence_root", None)
                rows.append(value)
            except (OSError, json.JSONDecodeError, ValueError):
                invalid.append(path.name)
    return rows, invalid


def aggregate(
    root: Path,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    terminal_only: bool = False,
    include_derived: bool = True,
) -> dict[str, Any]:
    rows, invalid = _load_metric_events(root)
    if invalid:
        raise ValueError(f"invalid metric event files: {len(invalid)}")
    filtered = [row for row in rows if task_id is None or row.get("task_id") == task_id]
    filtered = [row for row in filtered if run_id is None or row.get("run_id") == run_id]
    filtered = [row for row in filtered if not terminal_only or _metric_bool(row.get("terminal"))]
    core = [row for row in filtered if row.get("confidence") == "observed" or (include_derived and row.get("confidence") == "derived")]
    reported = [row for row in filtered if row.get("confidence") == "reported"]
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
    blocker_counts = {
        name: sum(row.get("blocker_class") == name for row in core)
        for name in ("product", "environment", "permission", "evidence", "dependency", "workflow")
    }
    all_event_counts: dict[str, int] = {}
    for row in core:
        event = row.get("event")
        if isinstance(event, str):
            all_event_counts[event] = all_event_counts.get(event, 0) + 1
    task_ids = {row.get("task_id") for row in core if isinstance(row.get("task_id"), str)}
    run_ids = {row.get("run_id") for row in core if isinstance(row.get("run_id"), str)}
    blocked_tasks = {
        row.get("task_id") for row in core
        if row.get("result") == "blocked" and isinstance(row.get("task_id"), str)
    }
    recovered_tasks = {
        task for task in blocked_tasks
        if any(
            later.get("task_id") == task
            and later.get("result") == "pass"
            and later.get("recorded_at", 0) > row.get("recorded_at", 0)
            for row in core if row.get("task_id") == task
            for later in core
        )
    }
    return {
        "schema": 1,
        "events": len(filtered),
        "core_events": len(core),
        "reported_events": len(reported),
        "passed": passed,
        "failed": failed,
        "blocked": sum(row.get("result") == "blocked" for row in core),
        "flaky": sum(row.get("result") == "flaky" for row in core),
        "unknown_results": sum(row.get("result") == "unknown" for row in core),
        "success_rate": passed / known if known else None,
        "known_result_success_rate": passed / known if known else None,
        "all_event_pass_rate": passed / len(core) if core else None,
        "blocked_rate": sum(row.get("result") == "blocked" for row in core) / len(core) if core else None,
        "token_count_total": sum(token_values) if token_values else None,
        "token_count_unknown": sum(row.get("token_count") is None for row in core),
        "review_overturns": event_counts["review_overturn"],
        "retries": event_counts["retry"] + sum(row.get("attempt", 0) > 0 for row in core),
        "timeouts": event_counts["timeout"] + sum(row.get("timed_out") is True for row in core),
        "evidence_gaps": event_counts["evidence_gap"],
        "post_merge_regressions": event_counts["post_merge_regression"],
        "blockers_by_class": blocker_counts,
        "main_agent_product_edits": sum(row.get("event") == "main_agent_product_edit" for row in core),
        "user_continue_nudges": sum(row.get("event") == "user_continue_nudge" for row in core),
        "user_process_corrections": sum(row.get("event") == "user_process_correction" for row in core),
        "recovery_path_misses": sum(row.get("event") == "recovery_path_miss" for row in core),
        "automatic_events": sum(row.get("source") == "pipeline_tools" for row in core),
        "event_counts": dict(sorted(all_event_counts.items())),
        "task_counts": dict(sorted({
            str(key): sum(row.get("task_id") == key for row in core)
            for key in task_ids
        }.items())),
        "run_counts": dict(sorted({
            str(key): sum(row.get("run_id") == key for row in core)
            for key in run_ids
        }.items())),
        "terminal_task_count": len({row.get("task_id") for row in core if _metric_bool(row.get("terminal")) and row.get("task_id")} ),
        "terminal_gate_pass_count": sum(row.get("event") == "gate_pre_merge" and row.get("result") == "pass" for row in core if _metric_bool(row.get("terminal"))),
        "terminal_unresolved_blocked_count": sum(row.get("result") == "blocked" for row in core if _metric_bool(row.get("terminal"))),
        "blocked_attempts": sum(row.get("result") == "blocked" for row in core),
        "blocked_task_count": len(blocked_tasks),
        "recovered_blocked_task_count": len(recovered_tasks),
        "recovery_rate": len(recovered_tasks) / len(blocked_tasks) if blocked_tasks else None,
        "unresolved_blocked_count": len(blocked_tasks - recovered_tasks),
        "terminal_state_unknown_count": sum(row.get("terminal") is None for row in core),
        "filters": {"task_id": task_id, "run_id": run_id, "terminal_only": terminal_only, "include_derived": include_derived},
    }


def _safe_version(value: str) -> str:
    match = re.search(r"v?(\d+(?:\.\d+){0,2})", value or "")
    return match.group(1) if match else "unknown"


def runtime_preflight(
    root: Path,
    expected_node: str | None = None,
    expected_pnpm: str | None = None,
    required_commands: list[str] | None = None,
    timeout: float = 20,
) -> dict[str, Any]:
    """Check the runtime before dispatching an executor or reviewer."""
    if not root.is_dir():
        return {"status": "blocked", "blocker_class": "environment", "errors": ["working directory does not exist"]}
    checks: dict[str, Any] = {}
    errors: list[str] = []
    commands = ("node", "pnpm.cmd", "git") + tuple(required_commands or []) if os.name == "nt" else ("node", "pnpm", "git") + tuple(required_commands or [])
    for name in commands:
        try:
            result = subprocess.run(
                [name, "--version"] if name not in {"git"} else [name, "--version"],
                cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            checks[name] = "missing"
            errors.append(f"{name} unavailable")
            continue
        version = _safe_version((result.stdout or result.stderr).strip())
        logical_name = "pnpm" if name == "pnpm.cmd" else name
        checks[logical_name] = version if result.returncode == 0 else "unavailable"
        if result.returncode != 0:
            errors.append(f"{name} returned {result.returncode}")
    if expected_node and checks.get("node") != _safe_version(expected_node):
        errors.append("node version mismatch")
    if expected_pnpm and checks.get("pnpm") != _safe_version(expected_pnpm):
        errors.append("pnpm version mismatch")
    return {
        "status": "pass" if not errors else "blocked",
        "blocker_class": None if not errors else "environment",
        "checks": checks,
        "errors": errors,
    }


def capability_handshake(
    root: Path,
    role: str,
    workflow_directory: Path,
    product_write_allowed: bool = False,
    expected_node: str | None = None,
    expected_pnpm: str | None = None,
    required_commands: list[str] | None = None,
) -> dict[str, Any]:
    """Create a bounded, machine-readable agent capability handshake."""
    runtime = runtime_preflight(root, expected_node, expected_pnpm, required_commands)
    checks = {
        "repository_read": root.is_dir(),
        "workflow_write": workflow_directory.is_dir() or workflow_directory.parent.is_dir(),
        "product_write": product_write_allowed,
        "runtime": runtime["status"] == "pass",
    }
    errors = list(runtime.get("errors", []))
    if not checks["repository_read"]:
        errors.append("repository unavailable")
    if not checks["workflow_write"]:
        errors.append("workflow directory is not writable")
    if role == "reviewer" and product_write_allowed:
        errors.append("reviewer product write must be denied")
    result = {
        "schema": 1,
        "role": role,
        "status": "pass" if not errors else "blocked",
        "checks": checks,
        "runtime": runtime,
        "errors": errors,
    }
    workflow_directory.mkdir(parents=True, exist_ok=True)
    (workflow_directory / "capability-handshake.json").write_text(
        json.dumps(result, ensure_ascii=True, sort_keys=True), encoding="utf-8"
    )
    return result


def lifecycle_status(root: Path, task_id: str, evidence_directory: Path) -> dict[str, Any]:
    """Derive the next safe workflow phase from current machine evidence."""
    errors: list[str] = []
    observed: list[dict[str, Any]] = []
    if not root.is_dir():
        return {
            "phase": "recovery",
            "status": "blocked",
            "errors": ["working directory does not exist"],
            "blockers": [{"class": "environment", "reason": "working directory does not exist"}],
            "next_actions": [],
            "unverified": ["repository identity", "task evidence"],
        }
    if not evidence_directory.exists():
        observed.append({"fact": "evidence_directory", "value": "not_created"})
    reports = {
        name: (evidence_directory / name).is_file()
        for name in REPORT_NAMES
    }
    machine_results = {
        name: (evidence_directory / name).is_file()
        for name in ("executor-result.json", "reviewer-result.json", "final-result.json")
    }
    observed.append({"fact": "machine_results", "value": machine_results})
    observed.append({"fact": "evidence_reports", "value": reports})
    if machine_results["final-result.json"] or reports["final-check.md"]:
        phase = "merge"
    elif machine_results["reviewer-result.json"] or reports["review-report.md"]:
        phase = "final-check"
    elif machine_results["executor-result.json"] or reports["executor-report.md"]:
        phase = "review"
    else:
        phase = "executor"
    blockers: list[dict[str, str]] = []
    if errors:
        blockers.append({"class": "evidence", "reason": errors[0]})
    next_actions_by_phase = {
        "executor": ["dispatch_executor"],
        "review": ["dispatch_reviewer"],
        "final-check": ["run_final_check"],
        "merge": ["run_gate_pre_merge", "merge_branch"],
    }
    if blockers:
        status = "blocked"
        next_actions: list[str] = ["reconcile_evidence"]
    else:
        status = "ready"
        next_actions = next_actions_by_phase[phase]
    return {
        "schema": 1,
        "command": "lifecycle.status",
        "task_id": task_id,
        "phase": phase,
        "status": status,
        "observed": observed,
        "errors": errors,
        "blockers": blockers,
        "next_actions": next_actions,
        "forbidden_actions": ["merge_branch"] if phase != "merge" else [],
        "unverified": [] if phase == "merge" else ["current phase acceptance evidence"],
    }


def _json_file(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def write_dispatch(root: Path, dispatch: dict[str, Any], output: Path) -> Path:
    """Validate and atomically write a structured executor/reviewer dispatch."""
    required = ("schema", "task_id", "role", "round", "root", "worktree", "branch", "evidence_dir", "permissions", "output")
    missing = [field for field in required if field not in dispatch]
    if missing:
        raise ValueError(f"dispatch missing fields: {', '.join(missing)}")
    if dispatch["schema"] != 1 or dispatch["role"] not in {"executor", "reviewer"}:
        raise ValueError("invalid dispatch schema or role")
    permissions = dispatch["permissions"]
    if not isinstance(permissions, dict) or permissions.get("write_workflow") is not True:
        raise ValueError("dispatch must allow workflow writes")
    if dispatch["role"] == "reviewer" and permissions.get("write_product") is not False:
        raise ValueError("reviewer product writes must be false")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(dispatch, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    os.replace(temporary, output)
    return output


def verify_structured_result(path: Path, expected_task_id: str, expected_role: str) -> list[str]:
    """Validate a machine result without interpreting semantic claims."""
    value = _json_file(path)
    if value is None:
        return ["result is missing or invalid JSON"]
    errors: list[str] = []
    for field in ("schema", "task_id", "role", "status", "acceptance", "unverified"):
        if field not in value:
            errors.append(f"missing field: {field}")
    if value.get("schema") != 1:
        errors.append("schema must be 1")
    if value.get("task_id") != expected_task_id:
        errors.append("task identity mismatch")
    if value.get("role") != expected_role:
        errors.append("role mismatch")
    if value.get("status") not in {"pass", "fail", "blocked", "flaky"}:
        errors.append("invalid status")
    if not isinstance(value.get("acceptance"), list) or not value.get("acceptance"):
        errors.append("acceptance must be a non-empty array")
    if not isinstance(value.get("unverified"), list):
        errors.append("unverified must be an array")
    for index, item in enumerate(value.get("acceptance", []), start=1):
        if not isinstance(item, dict):
            errors.append(f"acceptance {index} must be an object")
            continue
        for field in ("id", "status", "exit_code", "evidence_refs"):
            if field not in item:
                errors.append(f"acceptance {index} missing field: {field}")
        if item.get("status") not in {"pass", "fail", "blocked", "flaky", "unverified"}:
            errors.append(f"acceptance {index} has invalid status")
        if not isinstance(item.get("evidence_refs"), list):
            errors.append(f"acceptance {index} evidence_refs must be an array")
    return errors


def evidence_freshness(root: Path, evidence_directory: Path, result_path: Path | None = None) -> dict[str, Any]:
    """Compare structured result identity and evidence timestamps with current Git state."""
    result = _json_file(result_path) if result_path else None
    errors: list[str] = []
    observed: list[dict[str, Any]] = []
    rc, head = git(root, "rev-parse", "HEAD")
    current_head = head.strip() if rc == 0 else None
    if current_head:
        observed.append({"fact": "head", "value": current_head})
    if result is None:
        errors.append("structured result is missing")
    elif result.get("identity", {}).get("head") and result["identity"]["head"] != current_head:
        errors.append("result HEAD is stale")
    evidence_refs: list[str] = []
    if result:
        for item in result.get("acceptance", []):
            if isinstance(item, dict):
                evidence_refs.extend(ref for ref in item.get("evidence_refs", []) if isinstance(ref, str))
    missing = []
    for reference in evidence_refs:
        candidate = root / reference.replace("\\", "/")
        if not candidate.is_file():
            missing.append(reference)
    if missing:
        errors.append("evidence artifact missing")
    return {
        "schema": 1,
        "command": "evidence.freshness",
        "status": "pass" if not errors else "blocked",
        "observed": observed,
        "errors": errors,
        "blockers": [{"class": "evidence", "reason": error} for error in errors],
        "artifacts": [str(evidence_directory / "freshness.json")],
        "next_actions": [] if not errors else ["regenerate_structured_result"],
        "unverified": [],
        "result_sha256": _file_sha256(result_path) if result_path else None,
    }


def role_scope_check(
    root: Path,
    role: str,
    product_patterns: list[str] | None = None,
    authorized: bool = False,
) -> list[str]:
    """Prevent the main agent from changing product files without authorization."""
    if role != "main-agent" or authorized:
        return []
    patterns = product_patterns or ["src/**", "packages/**", "apps/**", "lib/**", "app/**"]
    rc, output = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if rc:
        return [output or "not a git repository"]
    return [path for path in _status_paths(output) if any(_matches(path, pattern, root) for pattern in patterns)]


def _session_text(session: dict[str, Any], role: str | None = None) -> list[str]:
    values: list[str] = []
    for message in session.get("messages", []):
        if role is not None and message.get("info", {}).get("role") != role:
            continue
        for part in message.get("parts", []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                values.append(part["text"])
    return values


def import_opencode_session(root: Path, session_file: Path, task_id: str = "opencode-session") -> list[Path]:
    """Convert structured OpenCode export observations into local metric events."""
    session = json.loads(session_file.read_text(encoding="utf-8"))
    if not isinstance(session, dict) or not isinstance(session.get("messages"), list):
        raise ValueError("invalid OpenCode session export")
    info = session.get("info", {}) if isinstance(session.get("info"), dict) else {}
    texts = _session_text(session, role="user")
    output: list[Path] = []
    tool_errors = 0
    task_errors = 0
    for message in session["messages"]:
        for part in message.get("parts", []):
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool" and isinstance(part.get("state"), dict) and part["state"].get("status") == "error":
                tool_errors += 1
            if part.get("type") == "tool" and part.get("tool") == "task" and isinstance(part.get("state"), dict) and part["state"].get("status") == "error":
                task_errors += 1
    def record(name: str, result: str, reason: str, blocker: str | None = None) -> None:
        output.append(metric_event(root, {
            "event": name, "confidence": "observed", "task_id": task_id, "result": result,
            "reason": reason, "blocker_class": blocker, "source": "opencode_session",
            "evidence_ref": None,
        }))
    if tool_errors:
        record("evidence_gap", "blocked", f"tool_errors_{tool_errors}", "evidence")
    if task_errors:
        record("retry", "blocked", f"subagent_errors_{task_errors}", "workflow")
    lower = "\n".join(texts).lower()
    assistant_lower = "\n".join(_session_text(session, role="assistant")).lower()
    for marker, name, reason in (
        ("继续", "user_continue_nudge", "user_requested_continue"),
        ("为什么停", "user_process_correction", "user_questioned_stop"),
        ("卡住", "user_process_correction", "user_reported_stuck"),
        ("改代码什么的不该", "user_process_correction", "user_corrected_role_boundary"),
    ):
        count = lower.count(marker.lower())
        for _ in range(count):
            record(name, "unknown", reason)
    if "直接修改产品代码" in assistant_lower or "违反了你提供的工作流" in assistant_lower:
        record("main_agent_product_edit", "fail", "role_boundary_violation", "workflow")
    return output


def purge_metrics(root: Path) -> int:
    count = 0
    for directory in metrics_dirs(root):
        if not directory.is_dir():
            continue
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
        rc, actual = git(
            root,
            "rev-parse",
            "--show-toplevel",
            redact_output=False,
        )
        try:
            expected = expected_worktree.resolve()
            actual_path = Path(actual.strip()).resolve()
        except (OSError, ValueError):
            errors.append("worktree identity cannot be resolved")
        else:
            if rc or actual_path != expected:
                errors.append("worktree does not match expected worktree")
    return errors
