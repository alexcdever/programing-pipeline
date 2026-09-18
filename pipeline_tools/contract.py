"""Machine-readable task contract validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CONTRACT_RE = re.compile(
    r"```pipeline-contract[ \t]*\r?\n(.*?)\r?\n```", re.DOTALL
)
TASK_ID_RE = re.compile(
    r"<!--\s*Task ID:\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*-->",
    re.IGNORECASE,
)
REQUIRED_FIELDS = (
    "schema",
    "task_id",
    "allowed_paths",
    "forbidden_paths",
    "acceptance_tests",
)
ACCEPTANCE_FIELDS = ("id", "evidence_level", "test_ref", "command_ref")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_path_pattern(value: Any) -> bool:
    """Accept repo-relative patterns and explicit absolute allow-list patterns."""
    if not _nonempty_string(value) or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    if "<" in normalized or ">" in normalized:
        return False
    # Absolute patterns are useful when one task spans sibling repositories.
    # Traversal segments are never allowed.
    segments = normalized.split("/")
    return ".." not in segments


def load_contract(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load and validate the JSON contract block without inferring missing data."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, ["task sheet unreadable"]

    blocks = CONTRACT_RE.findall(text)
    if len(blocks) != 1:
        return None, ["task sheet must contain exactly one pipeline-contract block"]

    try:
        data = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        return None, [f"pipeline-contract JSON is invalid at line {exc.lineno}"]
    if not isinstance(data, dict):
        return None, ["pipeline-contract must be a JSON object"]

    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing contract field: {field}")

    task_match = TASK_ID_RE.search(text)
    if not task_match:
        errors.append("missing valid Task ID")
    elif data.get("task_id") != task_match.group(1):
        errors.append("task_id does not match Task ID")

    schema = data.get("schema")
    if isinstance(schema, bool) or schema != 1:
        errors.append("schema must be integer 1")

    for field in ("allowed_paths", "forbidden_paths"):
        values = data.get(field)
        if not isinstance(values, list):
            errors.append(f"{field} must be an array")
            continue
        for index, value in enumerate(values, start=1):
            if not _valid_path_pattern(value):
                errors.append(
                    f"{field}[{index}] must be a non-empty safe path pattern"
                )

    tests = data.get("acceptance_tests")
    if not isinstance(tests, list) or not tests:
        errors.append("acceptance_tests must be a non-empty array")
        tests = []

    seen_ids: set[str] = set()
    for index, item in enumerate(tests, start=1):
        if not isinstance(item, dict):
            errors.append(f"acceptance test {index} must be an object")
            continue
        for field in ACCEPTANCE_FIELDS:
            if field not in item:
                errors.append(f"acceptance test {index} missing field: {field}")

        test_id = item.get("id")
        if not isinstance(test_id, str) or not IDENTIFIER_RE.fullmatch(test_id):
            errors.append(f"acceptance test {index} has invalid id")
        elif test_id in seen_ids:
            errors.append(f"duplicate acceptance test id: {test_id}")
        else:
            seen_ids.add(test_id)

        for field in ("test_ref", "command_ref"):
            value = item.get(field)
            if not _nonempty_string(value) or "<" in value or ">" in value:
                errors.append(
                    f"acceptance test {index} has empty or placeholder {field}"
                )

        level = item.get("evidence_level")
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 5:
            errors.append(f"acceptance test {index} evidence_level must be integer 1-5")

    return (data if not errors else None), errors


def validate_task(path: Path) -> list[str]:
    """Return structural contract errors; never decide product semantics."""
    _data, errors = load_contract(path)
    return errors
