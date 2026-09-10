#!/usr/bin/env python3
"""Validate the static structure of a generic programming task sheet.

This checks structure and identity only. It does not decide whether the
acceptance criteria are substantively correct; that remains the main agent's
responsibility.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_HEADINGS = (
    "## 任务身份",
    "## 依赖与范围",
    "## 设计与行为契约",
    "## 环境前置",
    "## 验收标准",
    "## 决策点",
    "## 任务级进度",
    "### 验收台账",
    "### 执行记录",
    "### 最终结果",
)


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")

    if not text.startswith("# "):
        errors.append("first line must be a Markdown title")
    if not re.search(r"<!--\s*Task ID:\s*[A-Za-z0-9][A-Za-z0-9._-]*\s*-->", text):
        errors.append("missing valid Task ID comment")
    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing heading: {heading}")
    if not re.search(r"### AC\d+[：:]", text):
        errors.append("at least one acceptance criterion (AC1, AC2, ...) is required")
    if "| AC | 状态 | 当前测试/命令 | 最新证据 | 备注 |" not in text:
        errors.append("acceptance ledger header is missing")
    if "- 合并提交：-" not in text:
        errors.append("final result must contain the merge-commit field")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <task-sheet.md>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2
    errors = validate(path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: valid task sheet: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
