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
    purge_metrics,
    run_command,
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
    for name in ("aggregate", "report"):
        item = metrics_sub.add_parser(name)
        item.add_argument("root", type=Path)
    export = metrics_sub.add_parser("export")
    export.add_argument("root", type=Path)
    export.add_argument("output", type=Path)
    purge = metrics_sub.add_parser("purge")
    purge.add_argument("root", type=Path)

    return parser


def _print_errors(errors: list[str]) -> None:
    print("PASS" if not errors else "FAIL: " + "; ".join(errors))


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
    return int(result["status_code"])


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        if args.group == "task" and args.action == "validate":
            errors = validate_task(args.path)
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
                    },
                )
                print(json.dumps({"event_file": str(path)}, ensure_ascii=True))
                return PASS
            if args.action == "purge":
                print(json.dumps({"deleted": purge_metrics(args.root)}))
                return PASS
            data = aggregate(args.root)
            if args.action == "export":
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(data, ensure_ascii=True, sort_keys=True), encoding="utf-8")
            print(json.dumps(data, ensure_ascii=True, sort_keys=True))
            return PASS
    except (OSError, ValueError) as exc:
        print(f"FAIL: {type(exc).__name__}", file=sys.stderr)
        return CONFIG
    return CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
