#!/usr/bin/env python3
"""Validate the static structure of a generic programming task sheet.

This checks structure and identity only. It does not decide whether the
acceptance tests are substantively correct; that remains the main agent's
responsibility.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_HEADINGS = (
    "## 任务身份",
    "## 依赖与范围",
    "## 事实、假设与待决",
    "## 设计与行为契约",
    "## 环境前置",
    "## 验收测试",
    "## 决策点",
    "## 任务级进度",
    "### 任务锚点",
    "### 验收台账",
    "### 执行记录",
    "### 最终结果",
)

REQUIRED_ANCHOR_FIELDS = (
    "基线 HEAD：",
    "契约提交：",
    "执行分支：",
    "执行 worktree：",
)

REQUIRED_ACCEPTANCE_FIELDS = (
    "- 触发：",
    "- 断言：",
    "- 测试：",
    "- 命令：",
    "- 验收模式：",
    "- 证据等级：",
    "- 结果要求：",
)

CONTRACT_RE = re.compile(r"```pipeline-contract\s*\n(.*?)\n```", flags=re.DOTALL)


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")

    if not text.startswith("# "):
        errors.append("first line must be a Markdown title")
    if not re.search(r"<!--\s*Task ID:\s*[A-Za-z0-9][A-Za-z0-9._-]*\s*-->", text):
        errors.append("missing valid Task ID comment")
    blocks = CONTRACT_RE.findall(text)
    if len(blocks) != 1:
        errors.append("task sheet must contain exactly one pipeline-contract block")
    elif any(token in blocks[0] for token in ("<task-id>", "<repo-relative", "<path-pattern>", "<file>", "<exact test name>", "<complete command>")):
        errors.append("pipeline-contract contains unfilled placeholders")
    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing heading: {heading}")

    acceptance_matches = list(
        re.finditer(r"^### 验收测试\d+[：:].*$", text, flags=re.MULTILINE)
    )
    if not acceptance_matches:
        errors.append("at least one acceptance test (验收测试1, 验收测试2, ...) is required")
    else:
        for index, match in enumerate(acceptance_matches, start=1):
            end = (
                acceptance_matches[index].start()
                if index < len(acceptance_matches)
                else len(text)
            )
            section = text[match.start():end]
            for field in REQUIRED_ACCEPTANCE_FIELDS:
                if field not in section:
                    errors.append(f"acceptance test {index} is missing field: {field}")
            if not re.search(
                r"^- 证据等级：(?:<\s*1\s*/|[1-5])", section, re.MULTILINE
            ):
                errors.append(
                    f"acceptance test {index} must declare an evidence level (1-5)"
                )

    for field in REQUIRED_ANCHOR_FIELDS:
        if field not in text:
            errors.append(f"missing task anchor field: {field}")
    if "| 验收测试 | 状态 | 当前测试/命令 | 最新证据 | 备注 |" not in text:
        errors.append("acceptance-test ledger header is missing")
    if not re.search(r"^- 合并提交：.*$", text, re.MULTILINE):
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
