"""Command-line entry point for programing-pipeline-tools."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .contract import validate_task
from .core import (
    BLOCKED,
    CONFIG,
    DRIFT,
    FAIL,
    PASS,
    aggregate,
    evidence_verify,
    freeze_check,
    gate_check,
    metric_event,
    import_opencode_session,
    capability_handshake,
    lifecycle_status,
    evidence_freshness,
    evidence_readiness,
    verify_structured_result,
    write_dispatch,
    purge_metrics,
    role_scope_check,
    run_command,
    runtime_preflight,
    scope_check,
)


def _add_contract_command(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("root", type=Path)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--task-sheet", type=Path)
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-branch")
    parser.add_argument("--expected-worktree", type=Path)
    parser.add_argument("--run-id")


def _add_scope_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allowed", action="append", nargs="+", required=True)
    parser.add_argument("--forbidden", action="append", nargs="*", default=[])


def _flatten(values: list[list[str]]) -> list[str]:
    return [item for group in values for item in group]


def _add_metrics_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id")
    parser.add_argument("--run-id")
    parser.add_argument("--terminal-only", action="store_true")
    parser.add_argument("--no-derived", action="store_true")


CONTRACT_PLACEHOLDER_TOKENS = (
    "<task-id>",
    "<repo-relative",
    "<path-pattern>",
    "<file>",
    "<exact test name>",
    "<complete command>",
)


def _task_contract_for_preflight(args: argparse.Namespace) -> list[str]:
    if not args.task_sheet:
        return []
    return [f"{args.task_sheet.name}: {error}" for error in validate_task(args.task_sheet)]


def _run_task_lifecycle(args: argparse.Namespace) -> int:
    errors = freeze_check(
        args.root,
        args.contract,
        expected_head=args.expected_head,
        expected_branch=args.expected_branch,
        expected_worktree=args.expected_worktree,
    )
    if getattr(args, "action", None) == "preflight":
        errors.extend(_task_contract_for_preflight(args))
    _print_errors(errors)
    return PASS if not errors else DRIFT


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline-tools")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path)
    groups = parser.add_subparsers(dest="group", required=True)

    task = groups.add_parser("task", help="task-sheet and lifecycle checks")
    task_sub = task.add_subparsers(dest="action", required=True)
    validate = task_sub.add_parser("validate", help="validate a pipeline-contract block")
    validate.add_argument("path", type=Path)
    for name in ("preflight", "freeze-check"):
        item = task_sub.add_parser(name, help=f"run {name} checks")
        _add_contract_command(item)

    # Keep top-level aliases for the first documented interface.
    for name in ("preflight", "freeze-check"):
        item = groups.add_parser(name, help=f"alias for task {name}")
        _add_contract_command(item)

    scope = groups.add_parser("scope", help="check changed paths")
    scope_sub = scope.add_subparsers(dest="action", required=True)
    scope_check_parser = scope_sub.add_parser("check")
    scope_check_parser.add_argument("root", type=Path)
    scope_check_parser.add_argument("--task-id")
    scope_check_parser.add_argument("--run-id")
    _add_scope_args(scope_check_parser)

    command = groups.add_parser("command", help="run a bounded command")
    command_sub = command.add_subparsers(dest="action", required=True)
    runner = command_sub.add_parser("run")
    runner.add_argument("--cwd", type=Path, required=True)
    runner.add_argument("--log", type=Path, required=True)
    runner.add_argument("--timeout", type=float, default=30)
    runner.add_argument("--task-id")
    runner.add_argument("--attempt", type=int, default=0)
    runner.add_argument("--run-id")
    runner.add_argument("command", nargs=argparse.REMAINDER)

    evidence = groups.add_parser("evidence", help="verify task evidence")
    evidence_sub = evidence.add_subparsers(dest="action", required=True)
    evidence_verify_parser = evidence_sub.add_parser("verify")
    evidence_verify_parser.add_argument("directory", type=Path)
    evidence_verify_parser.add_argument("--task-id", required=True)
    evidence_verify_parser.add_argument("--branch")
    evidence_verify_parser.add_argument("--run-id")
    evidence_ready_parser = evidence_sub.add_parser("readiness")
    evidence_ready_parser.add_argument("directory", type=Path)
    evidence_ready_parser.add_argument("--task-id", required=True)
    evidence_ready_parser.add_argument("--run-id")

    gate = groups.add_parser("gate", help="run merge gates")
    gate_sub = gate.add_subparsers(dest="action", required=True)
    for name in ("pre-merge", "post-merge"):
        item = gate_sub.add_parser(name)
        item.add_argument("directory", type=Path)
        item.add_argument("--task-id", required=True)
        item.add_argument("--branch")
        item.add_argument("--result", type=Path)
        item.add_argument("--role", choices=("executor", "reviewer"))
        item.add_argument("--run-id")

    metrics = groups.add_parser("metrics", help="record and aggregate local metrics")
    metrics_sub = metrics.add_subparsers(dest="action", required=True)
    record = metrics_sub.add_parser("record")
    record.add_argument("root", type=Path)
    record.add_argument("event")
    record.add_argument("--confidence", required=True, choices=("observed", "derived", "reported"))
    record.add_argument("--task-id", default="unknown")
    record.add_argument("--result", choices=("pass", "fail", "blocked", "flaky", "unknown"))
    record.add_argument("--reason")
    record.add_argument("--attempt", type=int, default=0)
    record.add_argument("--duration-s", type=float)
    record.add_argument("--timed-out", action="store_true")
    record.add_argument("--token-count", type=int)
    record.add_argument("--evidence-ref")
    record.add_argument("--blocker-class", choices=("product", "environment", "permission", "evidence", "dependency", "workflow"))
    record.add_argument("--source")
    record.add_argument("--run-id")
    record.add_argument("--phase")
    record.add_argument("--role")
    record.add_argument("--head")
    record.add_argument("--branch")
    record.add_argument("--evidence-root")
    record.add_argument("--terminal", action="store_true")
    record.add_argument("--supersedes")
    for name in ("aggregate", "report"):
        item = metrics_sub.add_parser(name)
        item.add_argument("root", type=Path)
        _add_metrics_filters(item)
    export = metrics_sub.add_parser("export")
    export.add_argument("root", type=Path)
    export.add_argument("output", type=Path)
    _add_metrics_filters(export)
    purge = metrics_sub.add_parser("purge")
    purge.add_argument("root", type=Path)
    session = metrics_sub.add_parser("import-opencode-session")
    session.add_argument("root", type=Path)
    session.add_argument("session", type=Path)
    session.add_argument("--task-id", default="opencode-session")

    runtime = groups.add_parser("runtime", help="runtime and agent capability checks")
    runtime_sub = runtime.add_subparsers(dest="action", required=True)
    preflight = runtime_sub.add_parser("preflight")
    preflight.add_argument("root", type=Path)
    preflight.add_argument("--node")
    preflight.add_argument("--pnpm")
    preflight.add_argument("--require", action="append", default=[])
    preflight.add_argument("--output", type=Path)
    preflight.add_argument("--task-id")
    preflight.add_argument("--run-id")
    handshake = runtime_sub.add_parser("handshake")
    handshake.add_argument("root", type=Path)
    handshake.add_argument("workflow", type=Path)
    handshake.add_argument("--role", required=True)
    handshake.add_argument("--node")
    handshake.add_argument("--pnpm")
    handshake.add_argument("--require", action="append", default=[])
    handshake.add_argument("--allow-product-write", action="store_true")
    handshake.add_argument("--run-id")
    role = runtime_sub.add_parser("role-scope")
    role.add_argument("root", type=Path)
    role.add_argument("--role", required=True)
    role.add_argument("--product-pattern", action="append", default=[])
    role.add_argument("--authorized", action="store_true")
    role.add_argument("--task-id")
    role.add_argument("--run-id")

    lifecycle = groups.add_parser("lifecycle", help="derive structured workflow state")
    lifecycle_sub = lifecycle.add_subparsers(dest="action", required=True)
    status = lifecycle_sub.add_parser("status")
    status.add_argument("root", type=Path)
    status.add_argument("--task-id", required=True)
    status.add_argument("--evidence", type=Path, required=True)
    status.add_argument("--run-id")

    dispatch = groups.add_parser("dispatch", help="structured agent dispatch checks")
    dispatch_sub = dispatch.add_subparsers(dest="action", required=True)
    dispatch_write = dispatch_sub.add_parser("write")
    dispatch_write.add_argument("input", type=Path)
    dispatch_write.add_argument("output", type=Path)
    dispatch_write.add_argument("--run-id")
    result = groups.add_parser("result", help="structured agent result checks")
    result_sub = result.add_subparsers(dest="action", required=True)
    result_verify = result_sub.add_parser("verify")
    result_verify.add_argument("path", type=Path)
    result_verify.add_argument("--task-id", required=True)
    result_verify.add_argument("--role", required=True, choices=("executor", "reviewer"))
    result_verify.add_argument("--run-id")
    freshness = groups.add_parser("freshness", help="evidence freshness checks")
    freshness.add_argument("root", type=Path)
    freshness.add_argument("evidence", type=Path)
    freshness.add_argument("--result", type=Path, required=True)
    freshness.add_argument("--run-id")

    return parser


def _print_errors(errors: list[str]) -> None:
    print("PASS" if not errors else "FAIL: " + "; ".join(errors))


def _envelope(command: str, status: str, *, task_id: str | None = None, phase: str | None = None, **data: object) -> dict[str, object]:
    return {
        "schema": 1,
        "command": command,
        "status": status,
        "exit_code": {"pass": 0, "fail": 1, "blocked": 3, "drift": 4}.get(status, 2),
        "task_id": task_id,
        "phase": phase,
        "observed": data.pop("observed", []),
        "errors": data.pop("errors", []),
        "blockers": data.pop("blockers", []),
        "artifacts": data.pop("artifacts", []),
        "next_actions": data.pop("next_actions", []),
        "unverified": data.pop("unverified", []),
        **data,
    }


def _emit(value: dict[str, object], args: argparse.Namespace) -> None:
    if args.format == "json":
        text = json.dumps(value, ensure_ascii=True, sort_keys=True)
        print(text)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")


def _json_file_for_cli(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON input must be an object")
    return value


def _command_result(result: dict[str, object]) -> int:
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("status_code", "exit_code", "timed_out", "duration_s", "log")
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return int(result["status_code"])  # type: ignore[arg-type]


def _auto_metrics_enabled() -> bool:
    """Return whether automatic workflow metrics are enabled."""
    value = os.environ.get("PIPELINE_TOOLS_DISABLE_AUTO_METRICS", "")
    return value.strip().lower() not in {"1", "true", "yes", "on"}


def _git_root(start: Path) -> Path:
    """Find the nearest Git project, falling back to the supplied directory."""
    value = start.resolve()
    if value.is_file():
        value = value.parent
    for candidate in (value, *value.parents):
        if (candidate / ".git").exists():
            return candidate
    if ".workflow" in value.parts:
        workflow_index = value.parts.index(".workflow")
        return Path(*value.parts[:workflow_index])
    return value


def _safe_project_reference(root: Path, value: Path | None) -> str | None:
    """Convert an in-project path to a relative metric evidence reference."""
    if value is None:
        return None
    try:
        reference = value.resolve().relative_to(root.resolve()).as_posix()
        if any(_SENSITIVE_COMPONENT_RE.search(part) for part in Path(reference).parts):
            return None
        return reference
    except (OSError, ValueError):
        return None


def _path_arg(args: argparse.Namespace, name: str) -> Path | None:
    value = getattr(args, name, None)
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    return None


def _int_arg(args: argparse.Namespace, name: str, default: int = 0) -> int:
    value = getattr(args, name, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _task_id_from_path(value: Path | None) -> str | None:
    """Extract a task id from the conventional .workflow/<task-id>/ path."""
    if value is None:
        return None
    parts = value.resolve().parts
    try:
        index = next(index for index, part in enumerate(parts) if part == ".workflow")
    except StopIteration:
        return None
    if index + 1 >= len(parts) or parts[index + 1] == "metrics":
        return None
    return _safe_task_id(parts[index + 1])


_SENSITIVE_COMPONENT_RE = re.compile(r"(?i)(?:secret|token|password|api[_-]?key)")


def _safe_task_id(value: str) -> str:
    return value if not any(_SENSITIVE_COMPONENT_RE.search(part) for part in Path(value).parts) else "unknown"


def _git_metadata(root: Path) -> tuple[str | None, str | None]:
    """Read short Git identity without putting an absolute path in metrics."""
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
        branch = subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
        return (
            head.stdout.strip() if head.returncode == 0 else None,
            branch.stdout.strip() if branch.returncode == 0 else None,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None


def _auto_run_id(args: argparse.Namespace, root: Path, task_id: str) -> str:
    explicit = _arg_value(args, "run_id") or os.environ.get("PIPELINE_TOOLS_RUN_ID")
    if isinstance(explicit, str) and explicit:
        return explicit
    head, _branch = _git_metadata(root)
    return f"{task_id}-{head or 'nogit'}"


def _auto_phase(args: argparse.Namespace) -> str | None:
    explicit = _arg_value(args, "phase")
    if isinstance(explicit, str) and explicit:
        return explicit
    group = getattr(args, "group", None)
    action = getattr(args, "action", None)
    if group in {"task", "preflight", "freeze-check"}:
        return "contract"
    if group == "command":
        return "execution"
    if group == "runtime":
        return "runtime"
    if group == "scope":
        return "scope"
    if group in {"evidence", "freshness"}:
        return "evidence"
    if group == "result":
        return "review"
    if group == "gate":
        return "post-merge" if action == "post-merge" else "main-final"
    if group == "lifecycle":
        return "lifecycle"
    if group == "dispatch":
        return "dispatch"
    return None


def _auto_role(args: argparse.Namespace) -> str | None:
    explicit = _arg_value(args, "role")
    if isinstance(explicit, str) and explicit:
        return explicit
    group = getattr(args, "group", None)
    if group == "gate":
        return "main-final"
    return None


def _evidence_root_from_reference(reference: str | None) -> str | None:
    if not reference:
        return None
    parts = Path(reference).parts
    try:
        index = parts.index(".workflow")
    except ValueError:
        return None
    if index + 1 >= len(parts) or parts[index + 1] == "metrics":
        return None
    return Path(*parts[: index + 2]).as_posix()


def _arg_value(args: argparse.Namespace, name: str, default: object = None) -> object:
    return getattr(args, name, default)


def _metric_result(exit_code: int) -> str:
    if exit_code == 0:
        return "pass"
    if exit_code == BLOCKED:
        return "blocked"
    return "fail"


def _auto_stage_name(args: argparse.Namespace) -> str | None:
    group = getattr(args, "group", None)
    action = getattr(args, "action", None)
    if not group or group == "metrics":
        return None
    if group == "help":
        return "cli_help"
    if group in {"preflight", "freeze-check"}:
        return f"task_{group.replace('-', '_')}"
    if group == "command":
        return "command_run"
    if group == "scope":
        return "scope_check"
    if group == "task":
        return f"task_{str(action).replace('-', '_')}"
    if group == "runtime":
        return f"runtime_{str(action).replace('-', '_')}"
    if group == "lifecycle":
        return "lifecycle_status"
    if group == "dispatch":
        return "dispatch_write"
    if group == "result":
        return "result_verify"
    if group == "freshness":
        return "freshness"
    if group in {"evidence", "gate"}:
        return f"{group}_{str(action).replace('-', '_')}"
    return None


def _arg_task_id(args: argparse.Namespace) -> str:
    return _safe_task_id(str(getattr(args, "task_id", "unknown") or "unknown"))


def _raw_stage_args(argv: list[str]) -> argparse.Namespace | None:
    """Best-effort stage identity for argparse failures.

    Full parsing intentionally remains authoritative for valid invocations.
    This small scan exists only so a malformed non-metrics invocation still
    leaves an automatic failure event instead of disappearing before the
    normal parser can produce a namespace.
    """
    groups = {
        "task", "preflight", "freeze-check", "scope", "command", "evidence",
        "gate", "runtime", "lifecycle", "dispatch", "result", "freshness", "metrics",
    }
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in {"--format", "--output"}:
            index += 2
            continue
        if token.startswith("--"):
            index += 1
            continue
        if token not in groups:
            index += 1
            continue
        group = token
        action = None
        if group in {"task", "scope", "command", "evidence", "gate", "runtime", "lifecycle", "dispatch", "result"}:
            next_index = index + 1
            while next_index < len(argv) and argv[next_index].startswith("--"):
                next_index += 2 if "=" not in argv[next_index] else 1
            if next_index < len(argv):
                action = argv[next_index]
        values: dict[str, object] = {"group": group, "action": action}
        option_names = ("cwd", "log", "task-id", "attempt", "root", "directory", "workflow", "path", "result")
        cursor = index + 1
        while cursor < len(argv):
            token = argv[cursor]
            matched = next((name for name in option_names if token == f"--{name}"), None)
            if matched is not None and cursor + 1 < len(argv):
                value: object = argv[cursor + 1]
                if matched in {"cwd", "log", "root", "directory", "workflow", "path", "result"}:
                    value = Path(str(value))
                elif matched in {"attempt"}:
                    try:
                        value = int(str(value))
                    except ValueError:
                        value = 0
                values[matched.replace("-", "_")] = value
                cursor += 2
                continue
            cursor += 1
        return argparse.Namespace(**values)
    # A completely malformed invocation still represents a non-metrics CLI
    # attempt. Keep the attribution intentionally unknown rather than dropping
    # the sample.
    return argparse.Namespace(group="unknown", action=None)


def _auto_root_and_reference(args: argparse.Namespace) -> tuple[Path, str | None]:
    group = getattr(args, "group", None)
    if group in {"preflight", "freeze-check", "scope", "runtime", "lifecycle"}:
        root = _git_root(Path(args.root))
        if group == "runtime" and args.action == "handshake":
            workflow = _path_arg(args, "workflow")
            artifact = workflow / "capability-handshake.json" if workflow else None
            return root, _safe_project_reference(root, artifact)
        if group == "runtime" and args.action == "preflight":
            return root, _safe_project_reference(root, _path_arg(args, "output"))
        if group == "lifecycle":
            return root, _safe_project_reference(root, _path_arg(args, "evidence"))
        if group in {"scope", "runtime"}:
            return root, None
        return root, None
    if group == "task" and args.action == "validate":
        path = Path(args.path)
        root = _git_root(path)
        return root, _safe_project_reference(root, path)
    if group == "task" and args.action in {"preflight", "freeze-check"}:
        root = _git_root(Path(args.root))
        return root, _safe_project_reference(root, _path_arg(args, "task_sheet"))
    if group == "command":
        cwd = _path_arg(args, "cwd") or Path.cwd()
        log = _path_arg(args, "log")
        if log is not None and not log.is_absolute():
            log = cwd / log
        root = _git_root(cwd)
        return root, _safe_project_reference(root, log)
    if group in {"evidence", "gate"}:
        directory = Path(args.directory)
        root = _git_root(directory)
        return root, _safe_project_reference(root, directory)
    if group == "dispatch":
        root = _git_root(Path(args.output))
        return root, _safe_project_reference(root, Path(args.output))
    if group == "result":
        path = Path(args.path)
        root = _git_root(path)
        return root, _safe_project_reference(root, path)
    if group == "freshness":
        root = _git_root(Path(args.root))
        return root, _safe_project_reference(root, _path_arg(args, "result"))
    return _git_root(Path.cwd()), None


def _auto_task_id(args: argparse.Namespace, root: Path) -> str:
    value = _arg_value(args, "task_id")
    if isinstance(value, str) and value:
        return _safe_task_id(value)
    group = getattr(args, "group", None)
    if group == "scope":
        return _arg_task_id(args)
    if group == "runtime" and args.action in {"preflight", "role-scope"}:
        return _arg_task_id(args)
    if group in {"evidence", "gate"}:
        return _safe_task_id(str(args.task_id))
    if group == "result":
        try:
            data = json.loads(Path(args.path).read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("task_id"), str):
                return _safe_task_id(data["task_id"])
        except (OSError, json.JSONDecodeError):
            pass
    if group == "command":
        log = _path_arg(args, "log")
        cwd = _path_arg(args, "cwd") or Path.cwd()
        if log is not None and not log.is_absolute():
            log = cwd / log
        task_id = _task_id_from_path(log)
        if task_id:
            return task_id
    if group == "task" and args.action in {"validate", "preflight", "freeze-check"}:
        try:
            from .contract import load_contract

            task_path = _path_arg(args, "path") if args.action == "validate" else _path_arg(args, "task_sheet")
            if task_path is not None:
                contract, _errors = load_contract(task_path)
                if contract and isinstance(contract.get("task_id"), str):
                    return _safe_task_id(contract["task_id"])
        except (OSError, UnicodeError):
            pass
    if group in {"preflight", "freeze-check"} and args.task_sheet:
        try:
            from .contract import load_contract

            contract, _errors = load_contract(Path(args.task_sheet))
            if contract and isinstance(contract.get("task_id"), str):
                return _safe_task_id(contract["task_id"])
        except (OSError, UnicodeError):
            pass
    if group == "runtime" and args.action == "handshake":
        workflow = _path_arg(args, "workflow")
        task_id = _task_id_from_path(workflow)
        return _safe_task_id(task_id or (workflow.name if workflow else "unknown"))
    if group == "dispatch":
        try:
            data = json.loads(Path(args.input).read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("task_id"), str):
                return _safe_task_id(data["task_id"])
        except (OSError, json.JSONDecodeError):
            pass
    if group == "freshness":
        result = _path_arg(args, "result")
        if result:
            try:
                data = json.loads(result.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("task_id"), str):
                    return _safe_task_id(data["task_id"])
            except (OSError, json.JSONDecodeError):
                pass
    return "unknown"


def _auto_feedback_events(args: argparse.Namespace, exit_code: int) -> list[tuple[str, str, str | None]]:
    """Derive feedback only from structured command outcomes."""
    group = getattr(args, "group", None)
    action = getattr(args, "action", None)
    feedback: list[tuple[str, str, str | None]] = []
    if group == "command" and exit_code == BLOCKED:
        feedback.append(("timeout", "blocked", "command_timeout"))
    if group == "command" and _int_arg(args, "attempt") > 0:
        feedback.append(("retry", "unknown", f"attempt_{_int_arg(args, 'attempt')}"))
    if group == "runtime" and action in {"preflight", "handshake"} and exit_code == BLOCKED:
        feedback.append(("environment_block", "blocked", "runtime_check_failed"))
    if group == "evidence" and action == "readiness" and exit_code != 0:
        feedback.append(("evidence_not_ready", "blocked", "readiness_check_failed"))
    elif group in {"evidence", "gate", "freshness"} and exit_code != 0:
        feedback.append(("evidence_gap", "blocked", f"{group}_{action}_failed"))
    if group == "scope" and exit_code != 0:
        feedback.append(("scope_drift", "fail", "scope_check_failed"))
    if group == "runtime" and action == "role-scope" and exit_code != 0:
        feedback.append(("main_agent_product_edit", "fail", "role_scope_drift"))
    return feedback


def _record_automatic_metrics(argv: list[str], exit_code: int, duration_s: float | None = None) -> list[Path]:
    """Record a stage result and machine-derived feedback for one CLI call."""
    if not _auto_metrics_enabled():
        return []
    try:
        parsed = _build_parser().parse_args(argv)
    except SystemExit:
        if exit_code == 0 and any(token in {"-h", "--help"} for token in argv):
            parsed = argparse.Namespace(group="help", action=None)
        else:
            parsed = _raw_stage_args(argv)
        if parsed is None:
            return []
    stage = _auto_stage_name(parsed)
    if stage is None and getattr(parsed, "group", None) in {"unknown", "help"}:
        stage = "cli_parse_error"
    if stage is None:
        return []
    try:
        root, evidence_ref = _auto_root_and_reference(parsed)
        task_id = _auto_task_id(parsed, root)
    except Exception:
        root, evidence_ref, task_id = _git_root(Path.cwd()), None, "unknown"
    result = _metric_result(exit_code)
    head, branch = _git_metadata(root)
    run_id = _auto_run_id(parsed, root, task_id)
    phase = _auto_phase(parsed)
    role = _auto_role(parsed)
    evidence_root = _evidence_root_from_reference(evidence_ref)
    blocker = "environment" if exit_code == BLOCKED else None
    if parsed.group in {"evidence", "gate", "freshness"} and exit_code != 0:
        blocker = "evidence"
    if parsed.group == "runtime" and parsed.action == "role-scope" and exit_code != 0:
        blocker = "workflow"
    recorded: list[Path] = []
    try:
        recorded.append(metric_event(root, {
            "event": stage,
            "confidence": "observed",
            "task_id": task_id,
            "result": result,
            "duration_s": duration_s,
            "timed_out": parsed.group == "command" and exit_code == BLOCKED,
            "attempt": _int_arg(parsed, "attempt"),
            "reason": None if exit_code == 0 else f"exit_code_{exit_code}",
            "evidence_ref": evidence_ref,
            "blocker_class": blocker,
            "source": "pipeline_tools",
            "run_id": run_id,
            "phase": phase,
            "role": role,
            "head": head,
            "branch": branch,
            "evidence_root": evidence_root,
            "terminal": parsed.group == "gate" and exit_code == 0,
            "supersedes": None,
        }))
        for event, event_result, reason in _auto_feedback_events(parsed, exit_code):
            recorded.append(metric_event(root, {
                "event": event,
                "confidence": "derived",
                "task_id": task_id,
                "result": event_result,
                "reason": reason,
                "timed_out": event == "timeout",
                "attempt": _int_arg(parsed, "attempt"),
                "evidence_ref": evidence_ref,
                "blocker_class": "workflow" if event in {"retry", "scope_drift", "main_agent_product_edit"} else "evidence" if event in {"evidence_gap", "evidence_not_ready"} else "environment" if event in {"timeout", "environment_block"} else None,
                "source": "pipeline_tools",
                "run_id": run_id,
                "phase": phase,
                "role": role,
                "head": head,
                "branch": branch,
                "evidence_root": evidence_root,
                "terminal": False,
                "supersedes": None,
            }))
    except Exception as error:
        # Metrics are feedback, not an acceptance gate.  A read-only project
        # must not change the original command's result.
        print(f"WARNING: automatic metrics unavailable ({type(error).__name__})", file=sys.stderr)
        return recorded
    return recorded


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        if args.group == "task" and args.action == "validate":
            errors = validate_task(args.path)
            if args.format == "json":
                _emit(_envelope("task.validate", "pass" if not errors else "fail", errors=errors), args)
            else:
                _print_errors(errors)
            return PASS if not errors else CONFIG
        if args.group in {"preflight", "freeze-check"}:
            return _run_task_lifecycle(args)
        if args.group == "task" and args.action in {"preflight", "freeze-check"}:
            return _run_task_lifecycle(args)
        if args.group == "scope":
            allowed = _flatten(args.allowed)
            forbidden = _flatten(args.forbidden)
            bad = scope_check(args.root, allowed, forbidden)
            if bad:
                print("FAIL: " + ", ".join(bad))
                return DRIFT
            print("PASS")
            return PASS
        if args.group == "command":
            try:
                result = run_command(args.command, args.cwd, args.log, args.timeout)
            except ValueError as exc:
                print(f"FAIL: {exc}", file=sys.stderr)
                return CONFIG
            return _command_result(result)
        if args.group == "evidence":
            if args.action == "readiness":
                value = evidence_readiness(args.directory, args.task_id)
                if args.format == "json":
                    _emit(value, args)
                else:
                    print(f"{value['status'].upper()} evidence.readiness")
                return PASS if value["status"] == "ready" else BLOCKED
            errors = evidence_verify(args.directory, args.task_id, args.branch)
            _print_errors(errors)
            return PASS if not errors else BLOCKED
        if args.group == "gate":
            errors = gate_check(args.directory, args.task_id, args.branch, args.action)
            if args.result:
                role = args.role or ("reviewer" if "reviewer" in args.result.name else "executor")
                errors.extend(verify_structured_result(args.result, args.task_id, role))
                freshness = evidence_freshness(args.directory.parent.parent, args.directory, args.result)
                if freshness["status"] != "pass":
                    errors.extend(freshness["errors"])
            _print_errors(errors)
            return PASS if not errors else BLOCKED
        if args.group == "metrics":
            if args.action == "record":
                path = metric_event(
                    args.root,
                    {
                        "event": args.event,
                        "confidence": args.confidence,
                        "task_id": args.task_id,
                        "result": args.result,
                        "reason": args.reason,
                        "attempt": args.attempt,
                        "duration_s": args.duration_s,
                        "timed_out": args.timed_out,
                        "token_count": args.token_count,
                        "evidence_ref": args.evidence_ref,
                        "blocker_class": args.blocker_class,
                        "source": args.source,
                        "run_id": args.run_id,
                        "phase": args.phase,
                        "role": args.role,
                        "head": args.head,
                        "branch": args.branch,
                        "evidence_root": args.evidence_root,
                        "terminal": args.terminal,
                        "supersedes": args.supersedes,
                    },
                )
                print(json.dumps({"event_file": str(path)}, ensure_ascii=True))
                return PASS
            if args.action == "purge":
                print(json.dumps({"deleted": purge_metrics(args.root)}))
                return PASS
            if args.action == "import-opencode-session":
                files = import_opencode_session(args.root, args.session, args.task_id)
                print(json.dumps({"imported": len(files)}, ensure_ascii=True))
                return PASS
            data = aggregate(
                args.root,
                task_id=getattr(args, "task_id", None),
                run_id=getattr(args, "run_id", None),
                terminal_only=getattr(args, "terminal_only", False),
                include_derived=not getattr(args, "no_derived", False),
            )
            if args.action == "export":
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(data, ensure_ascii=True, sort_keys=True), encoding="utf-8")
            print(json.dumps(data, ensure_ascii=True, sort_keys=True))
            return PASS
        if args.group == "runtime":
            if args.action == "preflight":
                result = runtime_preflight(args.root, args.node, args.pnpm, args.require)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(result, ensure_ascii=True, sort_keys=True), encoding="utf-8")
                print(json.dumps(result, ensure_ascii=True, sort_keys=True))
                return PASS if result["status"] == "pass" else BLOCKED
            if args.action == "handshake":
                result = capability_handshake(
                    args.root,
                    args.role,
                    args.workflow,
                    args.allow_product_write,
                    args.node,
                    args.pnpm,
                    args.require,
                )
                print(json.dumps(result, ensure_ascii=True, sort_keys=True))
                return PASS if result["status"] == "pass" else BLOCKED
            bad = role_scope_check(args.root, args.role, args.product_pattern, args.authorized)
            if bad:
                print("FAIL: " + ", ".join(bad))
                return DRIFT
            print("PASS")
            return PASS
        if args.group == "lifecycle" and args.action == "status":
            result = lifecycle_status(args.root, args.task_id, args.evidence)
            status_code = PASS if result["status"] == "ready" else BLOCKED
            if args.format == "json":
                _emit(result, args)
            else:
                print(f"{result['status'].upper()} lifecycle.status phase={result['phase']}")
            return status_code
        if args.group == "dispatch" and args.action == "write":
            dispatch_value = _json_file_for_cli(args.input)
            path = write_dispatch(args.input.parent, dispatch_value, args.output)
            value = _envelope("dispatch.write", "pass", artifacts=[str(path)], next_actions=["start_agent"])
            if args.format == "json":
                _emit(value, args)
            else:
                print("PASS dispatch.write")
            return PASS
        if args.group == "result" and args.action == "verify":
            errors = verify_structured_result(args.path, args.task_id, args.role)
            value = _envelope("result.verify", "pass" if not errors else "fail", task_id=args.task_id, errors=errors)
            if args.format == "json":
                _emit(value, args)
            else:
                _print_errors(errors)
            return PASS if not errors else CONFIG
        if args.group == "freshness":
            value = evidence_freshness(args.root, args.evidence, args.result)
            if args.format == "json":
                _emit(value, args)
            else:
                print(f"{value['status'].upper()} evidence.freshness")
            return PASS if value["status"] == "pass" else BLOCKED
    except (OSError, ValueError) as exc:
        print(f"FAIL: {type(exc).__name__}", file=sys.stderr)
        return CONFIG
    return CONFIG


def main(argv: list[str] | None = None) -> int:
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    exit_code: int | None = None
    started = time.monotonic()
    try:
        exit_code = _main(actual_argv)
        return exit_code
    except SystemExit as error:
        code = error.code
        exit_code = code if isinstance(code, int) else CONFIG
        return exit_code
    finally:
        if exit_code is not None:
            try:
                _record_automatic_metrics(actual_argv, exit_code, round(time.monotonic() - started, 3))
            except BaseException:
                # Automatic feedback must never replace the original command
                # result, including when attribution or filesystem probing
                # fails during finalization.
                pass


if __name__ == "__main__":
    raise SystemExit(main())
