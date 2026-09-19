"""Command-line entry point for programing-pipeline-tools."""

from __future__ import annotations

import argparse
import json
import sys
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


def _add_scope_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allowed", action="append", nargs="+", required=True)
    parser.add_argument("--forbidden", action="append", nargs="*", default=[])


def _flatten(values: list[list[str]]) -> list[str]:
    return [item for group in values for item in group]


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
    _add_scope_args(scope_check_parser)

    command = groups.add_parser("command", help="run a bounded command")
    command_sub = command.add_subparsers(dest="action", required=True)
    runner = command_sub.add_parser("run")
    runner.add_argument("--cwd", type=Path, required=True)
    runner.add_argument("--log", type=Path, required=True)
    runner.add_argument("--timeout", type=float, default=30)
    runner.add_argument("command", nargs=argparse.REMAINDER)

    evidence = groups.add_parser("evidence", help="verify task evidence")
    evidence_sub = evidence.add_subparsers(dest="action", required=True)
    evidence_verify_parser = evidence_sub.add_parser("verify")
    evidence_verify_parser.add_argument("directory", type=Path)
    evidence_verify_parser.add_argument("--task-id", required=True)
    evidence_verify_parser.add_argument("--branch")

    gate = groups.add_parser("gate", help="run merge gates")
    gate_sub = gate.add_subparsers(dest="action", required=True)
    for name in ("pre-merge", "post-merge"):
        item = gate_sub.add_parser(name)
        item.add_argument("directory", type=Path)
        item.add_argument("--task-id", required=True)
        item.add_argument("--branch")
        item.add_argument("--result", type=Path)
        item.add_argument("--role", choices=("executor", "reviewer"))

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
    for name in ("aggregate", "report"):
        item = metrics_sub.add_parser(name)
        item.add_argument("root", type=Path)
    export = metrics_sub.add_parser("export")
    export.add_argument("root", type=Path)
    export.add_argument("output", type=Path)
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
    handshake = runtime_sub.add_parser("handshake")
    handshake.add_argument("root", type=Path)
    handshake.add_argument("workflow", type=Path)
    handshake.add_argument("--role", required=True)
    handshake.add_argument("--node")
    handshake.add_argument("--pnpm")
    handshake.add_argument("--require", action="append", default=[])
    handshake.add_argument("--allow-product-write", action="store_true")
    role = runtime_sub.add_parser("role-scope")
    role.add_argument("root", type=Path)
    role.add_argument("--role", required=True)
    role.add_argument("--product-pattern", action="append", default=[])
    role.add_argument("--authorized", action="store_true")

    lifecycle = groups.add_parser("lifecycle", help="derive structured workflow state")
    lifecycle_sub = lifecycle.add_subparsers(dest="action", required=True)
    status = lifecycle_sub.add_parser("status")
    status.add_argument("root", type=Path)
    status.add_argument("--task-id", required=True)
    status.add_argument("--evidence", type=Path, required=True)

    dispatch = groups.add_parser("dispatch", help="structured agent dispatch checks")
    dispatch_sub = dispatch.add_subparsers(dest="action", required=True)
    dispatch_write = dispatch_sub.add_parser("write")
    dispatch_write.add_argument("input", type=Path)
    dispatch_write.add_argument("output", type=Path)
    result = groups.add_parser("result", help="structured agent result checks")
    result_sub = result.add_subparsers(dest="action", required=True)
    result_verify = result_sub.add_parser("verify")
    result_verify.add_argument("path", type=Path)
    result_verify.add_argument("--task-id", required=True)
    result_verify.add_argument("--role", required=True, choices=("executor", "reviewer"))
    freshness = groups.add_parser("freshness", help="evidence freshness checks")
    freshness.add_argument("root", type=Path)
    freshness.add_argument("evidence", type=Path)
    freshness.add_argument("--result", type=Path, required=True)

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


def main(argv: list[str] | None = None) -> int:
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
            data = aggregate(args.root)
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


if __name__ == "__main__":
    raise SystemExit(main())
