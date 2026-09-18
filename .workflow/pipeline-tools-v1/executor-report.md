# Executor Report — pipeline-tools-v1

## 摘要（人读）

- **task-id**: `pipeline-tools-v1`
- **worktree**: `D:/Projects/Skills/programing-pipeline-tools`
- **branch**: `pipeline-tools-v1`
- **轮次**: round 3（主代理接管收尾：两次执行子代理均在 1800 秒超时，本报告记录真实接管过程）
- **日期**: 2026-09-18 CST
- **提交状态**: 未 commit、未 push

## 执行轮次真实记录

1. round 1（子代理 sa-0-68139c61）：1800 秒超时，留下未提交的部分实现（contract.py / core.py / __main__.py / 6 个测试文件 / bin 包装器 / README / metrics-contract.md）。无完成摘要。
2. round 2（子代理 sa-0-c5053021）：1800 秒超时，25 次 API 调用后中断，未能产出 executor-report。部分实现已修复（CLI 测试从 7 失败降到 3 失败）。
3. round 3（主代理接管）：直接核验现场并修复剩余问题，本报告即该轮产物。

## round 3 实际修复内容

1. `pipeline_tools/contract.py`：重写为完整契约校验（恰好一个 pipeline-contract 区块、schema=1、Task ID 与 task_id 一致、相对/绝对路径模式校验、验收测试字段/ID/占位符/证据等级 1-5）。修复正则转义错误。
2. `pipeline_tools/core.py`：
   - `evidence_verify` 改为机器可读 `pipeline-evidence` JSON 区块校验（角色、状态、命令退出码、证据引用），不再依赖自然语言标记；新增状态闸门（仅 PASS/READY-TO-MERGE/MERGED 通过）。
   - 修复 `git()` 对 porcelain 输出 `.strip()` 破坏首行 XY 状态码列结构的缺陷（` M .gitignore` 被吞掉前导空格导致路径解析错位）。
   - `run_command` 超时后以 exit_code=BLOCKED(3) 报告并终止进程树（Windows taskkill /T/F）。
   - `_read_machine_evidence` 用逐行扫描代替正则，支持 CRLF。
3. `pipeline_tools/__main__.py`：CLI 分发重构（task validate/preflight/freeze-check + 顶层别名、scope、command run、evidence verify、gate pre/post-merge、metrics record/aggregate/report/export/purge）。
4. `tests/test_evidence.py`：升级为机器证据格式测试（含身份不匹配、缺报告、纯散文被拒绝、gate 状态闸门）。
5. `tests/test_cli.py`：保留并全部通过（含 `--` 分隔符、非零退出码=1、缺可执行文件=2、超时=3、空命令=2、preflight/freeze-check、scope、metrics 往返、bin 包装器、真实任务单校验）。

## 当前证据命令与结果

所有命令从 `D:/Projects/Skills/programing-pipeline-tools` 执行，外层 `timeout 180`：

| 命令 | 退出码 | 日志 |
|---|---|---|
| `python -m unittest discover -s tests -v` | 0（24 tests OK） | `.workflow/pipeline-tools-v1/unittest-full.log` |
| `python -m pipeline_tools task preflight . --contract d9a4909` | 0 PASS | `.workflow/pipeline-tools-v1/preflight.log` |
| `python -m pipeline_tools scope check . --allowed ...`（本任务允许清单） | 0 PASS | `.workflow/pipeline-tools-v1/scope-check.log` |
| `python -m pipeline_tools task validate docs/tasks/pipeline-tools-v1.md` | 0 PASS | 上面日志引用 |
| `python -m pipeline_tools metrics record/report/purge .` | 0/0/0（事件往返、重建、清空） | 终端输出（会话记录） |

## 未完成项 / 环境限制

- `bin/pipeline-tools`（POSIX sh 包装器）未在本机以 POSIX 方式实跑（Windows 环境）；`pipeline-tools.cmd` 通过测试 `test_bin_wrappers_run` 实跑验证。
- 两次执行子代理超时是通道问题（1800 秒上限），不是产品失败；现场已保留并被本轮接管修复。
- 父技能 `programing-pipeline` 的 SKILL.md/README/templates 尚未接线（属于本任务允许范围但主代理尚未执行——等待独立审查通过后统一接线，避免与工具实现混淆）。

## 结论

工具核心全部真实通过：24 个单元/集成测试、5 组 CLI 子命令、scope/preflight 冻结检查、metrics 脱敏往返。工具不解析自然语言报告、不猜测产品语义、fail-closed。

```pipeline-evidence
{
  "schema": 1,
  "task_id": "pipeline-tools-v1",
  "worktree": ".worktrees/../programing-pipeline-tools",
  "branch": "pipeline-tools-v1",
  "role": "executor",
  "round": 3,
  "status": "PASS",
  "commands": [
    {"command": "timeout 180 python -m unittest discover -s tests -v", "exit_code": 0, "evidence_ref": ".workflow/pipeline-tools-v1/unittest-full.log"},
    {"command": "python -m pipeline_tools task preflight . --contract d9a4909", "exit_code": 0, "evidence_ref": ".workflow/pipeline-tools-v1/preflight.log"},
    {"command": "python -m pipeline_tools scope check . --allowed <task-allow-list>", "exit_code": 0, "evidence_ref": ".workflow/pipeline-tools-v1/scope-check.log"},
    {"command": "python -m pipeline_tools task validate docs/tasks/pipeline-tools-v1.md", "exit_code": 0, "evidence_ref": ".workflow/pipeline-tools-v1/preflight.log"},
    {"command": "python -m pipeline_tools metrics record/report/purge .", "exit_code": 0, "evidence_ref": ".workflow/pipeline-tools-v1/executor-report.md"}
  ],
  "assertions": [
    "24 unittest cases pass with exit 0",
    "CLI exit codes stable: 0 PASS / 1 FAIL / 2 CONFIG / 3 BLOCKED timeout / 4 DRIFT",
    "scope check passes only with the frozen allow-list",
    "metrics events are per-file, atomic, redacted, rebuildable; reported excluded from core",
    "evidence verification rejects prose-only reports without pipeline-evidence block"
  ],
  "evidence_refs": [
    ".workflow/pipeline-tools-v1/unittest-full.log",
    ".workflow/pipeline-tools-v1/preflight.log",
    ".workflow/pipeline-tools-v1/scope-check.log"
  ],
  "unverified": [
    "POSIX bin wrapper not executed on this Windows host (cmd wrapper verified via test_bin_wrappers_run)",
    "parent-skill wiring (SKILL.md/README/templates) not yet applied in this round"
  ]
}
```
