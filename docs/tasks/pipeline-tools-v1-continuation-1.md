# pipeline-tools v1 continuation-1：自动采集可追踪流程指标

<!-- Task ID: pipeline-tools-v1-continuation-1 -->
<!-- Contract section is frozen after commit. Lifecycle sections are maintained by the main agent. -->

```pipeline-contract
{
  "schema": 1,
  "task_id": "pipeline-tools-v1-continuation-1",
  "allowed_paths": [
    "docs/tasks/pipeline-tools-v1-continuation-1.md",
    "pipeline_tools/__main__.py",
    "pipeline_tools/core.py",
    "tests/test_cli.py",
    "tests/test_git_checks.py",
    "README.md",
    "SKILL.md",
    "references/metrics-contract.md",
    ".gitignore",
    "docs/tasks/pipeline-tools-v1.md",
    ".workflow/metrics/**",
    ".workflow/pipeline-tools-v1-continuation-1/**"
  ],
  "forbidden_paths": [
    "**/.env",
    "**/*secret*",
    "package.json",
    "pnpm-lock.yaml"
  ],
  "acceptance_tests": [
    {
      "id": "AT1",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_workflow_command_automatically_records_tracked_metric",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_workflow_command_automatically_records_tracked_metric"
    },
    {
      "id": "AT2",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_automatic_timeout_records_feedback_event",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_automatic_timeout_records_feedback_event"
    },
    {
      "id": "AT2B",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_automatic_command_uses_task_id_from_workflow_log_path",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_automatic_command_uses_task_id_from_workflow_log_path"
    },
    {
      "id": "AT2C",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_automatic_retry_records_first_retry_attempt",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_automatic_retry_records_first_retry_attempt"
    },
    {
      "id": "AT2D",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_malformed_non_metrics_command_records_a_failure_metric",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_malformed_non_metrics_command_records_a_failure_metric"
    },
    {
      "id": "AT2E",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_automatic_metrics_redact_sensitive_path_components",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_automatic_metrics_redact_sensitive_path_components"
    },
    {
      "id": "AT2F",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_top_level_parse_error_records_a_failure_metric",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_top_level_parse_error_records_a_failure_metric"
    },
    {
      "id": "AT2G",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_subcommand_help_records_a_help_metric",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_subcommand_help_records_a_help_metric"
    },
    {
      "id": "AT3",
      "evidence_level": 2,
      "test_ref": "tests/test_cli.py and tests/test_git_checks.py: metrics recursion and scope behavior",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_metrics_commands_do_not_recursively_record_stage_metrics tests.test_git_checks.GitChecks.test_generated_metrics_are_not_scope_drift"
    },
    {
      "id": "AT3B",
      "evidence_level": 2,
      "test_ref": "tests/test_git_checks.py: test_forbidden_metrics_pattern_still_wins",
      "command_ref": "python -m unittest tests.test_git_checks.GitChecks.test_forbidden_metrics_pattern_still_wins"
    },
    {
      "id": "AT3C",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: malformed/attributed command and sensitive component protections",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_malformed_non_metrics_command_records_a_failure_metric tests.test_cli.CLITests.test_automatic_metrics_redact_sensitive_path_components"
    },
    {
      "id": "AT3D",
      "evidence_level": 2,
      "test_ref": "tests/test_git_checks.py: test_tracked_metrics_are_workflow_metadata",
      "command_ref": "python -m unittest tests.test_git_checks.GitChecks.test_tracked_metrics_are_workflow_metadata"
    },
    {
      "id": "AT3E",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_automatic_runtime_and_lifecycle_events_keep_identity",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_automatic_runtime_and_lifecycle_events_keep_identity"
    },
    {
      "id": "AT4",
      "evidence_level": 1,
      "test_ref": "tests/: complete regression suite",
      "command_ref": "python -m unittest discover -s tests -v"
    },
    {
      "id": "AT4B",
      "evidence_level": 1,
      "test_ref": "tests/test_metrics.py: test_automatic_event_counts_are_available_for_new_stage_names",
      "command_ref": "python -m unittest tests.test_metrics.MetricsTests.test_automatic_event_counts_are_available_for_new_stage_names"
    },
    {
      "id": "AT4C",
      "evidence_level": 1,
      "test_ref": "tests/test_metrics.py: test_sensitive_identifiers_are_redacted_at_metric_boundary",
      "command_ref": "python -m unittest tests.test_metrics.MetricsTests.test_sensitive_identifiers_are_redacted_at_metric_boundary"
    },
    {
      "id": "AT4D",
      "evidence_level": 1,
      "test_ref": "tests/test_metrics.py: test_extended_sensitive_vocabulary_is_redacted_at_metric_boundary",
      "command_ref": "python -m unittest tests.test_metrics.MetricsTests.test_extended_sensitive_vocabulary_is_redacted_at_metric_boundary"
    },
    {
      "id": "AT5",
      "evidence_level": 1,
      "test_ref": "docs and code: automatic collection contract and tracked metrics policy",
      "command_ref": "python -m pipeline_tools task validate docs/tasks/pipeline-tools-v1-continuation-1.md"
    },
    {
      "id": "AT6",
      "evidence_level": 1,
      "test_ref": "tests/test_metrics.py: aggregate rate, task/run and recovery dimensions",
      "command_ref": "python -m unittest tests.test_metrics.MetricsTests.test_aggregate_distinguishes_all_event_rates_from_known_result_rate tests.test_metrics.MetricsTests.test_aggregate_groups_events_by_task_and_reports_terminal_gate"
    },
    {
      "id": "AT7",
      "evidence_level": 2,
      "test_ref": "tests/test_cli.py: task-filtered terminal report and evidence readiness",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_metrics_report_filters_by_task_and_terminal tests.test_cli.CLITests.test_evidence_readiness_reports_missing_final_check_without_gate_claim"
    },
    {
      "id": "AT8",
      "evidence_level": 1,
      "test_ref": "tests/test_metrics.py and tests/test_cli.py: metric run/terminal identity dimensions",
      "command_ref": "python -m unittest tests.test_metrics.MetricsTests.test_metric_event_preserves_run_and_terminal_dimensions tests.test_cli.CLITests.test_automatic_events_carry_task_and_evidence_identity"
    },
    {
      "id": "AT9",
      "evidence_level": 1,
      "test_ref": "tests/test_cli.py: test_evidence_readiness_records_not_ready_feedback",
      "command_ref": "python -m unittest tests.test_cli.CLITests.test_evidence_readiness_records_not_ready_feedback"
    }
  ]
}
```

## 任务身份

- 项目：programing-pipeline
- 领域或阶段：工作流反馈自动化 / v1 continuation-1
- 用户结果或系统能力：每次非 `metrics` 的 `pipeline-tools` 阶段命令自动保存可审查的 observed/derived 指标，且指标文件可由 Git 追踪。
- 状态：已实现并完成当前环境实测

## 依赖与范围

### 前置条件

- 父任务 `pipeline-tools-v1` 已实现基础指标事件、聚合和 CLI；工具现已并入本技能仓库。
- 当前任务只改技能仓库，不修改 StoryLine 或其他消费项目。
- Python 3.11 标准库；不联网、不上传数据、不新增第三方依赖。

### 允许修改

- `pipeline_tools` 的 CLI 自动采集和范围检查。
- 自动采集、递归保护、超时反馈和跟踪策略测试。
- 技能、README、指标契约和 `.gitignore` 文档/配置。
- 本任务自己的证据与 `.workflow/metrics/` 事件文件。

### 明确不改

- 不解析自然语言报告来推断产品 PASS。
- 不记录 prompt、完整日志、源代码、凭据、token 或业务数据。
- 不修改任何外部产品项目，不自动合并，不上传遥测。
- 不改变已有稳定退出码和验收 gate 语义。

## 设计与行为契约

`pipeline-tools` 阶段命令启动
→ CLI 根据机械退出码和结构化参数执行自动采集
→ 项目 `.workflow/metrics/` 原子写入一个阶段事件，必要时追加 derived 反馈事件
→ `metrics report/export` 从事件重建统计
→ 指标文件作为工作流历史进入 Git，scope check 不将工具自动生成的指标视为产品越界

- `metrics` 子命令不递归生成阶段指标。
- 自动采集失败不得改变原命令退出码；命令结果仍是验收权威。
- 退出码、超时、任务 ID 和项目内 evidence reference 必须来自机械输入或结构化结果。
- 自动事件的 token 值保持 `null`，没有实际 token 计量时不得估算。
- 可用环境变量 `PIPELINE_TOOLS_DISABLE_AUTO_METRICS=1` 关闭自动采集，仅供测试或明确诊断使用。

## 环境前置

1. 在当前技能仓库执行测试；不要执行 StoryLine 产品测试。
2. 每条测试命令有明确超时，默认 180 秒。
3. 指标事件使用临时 Git/项目目录测试；不会把测试样本写入生产项目。

## 决策点

1. 若自动采集需要从自然语言报告推断产品结论，停止并报告 BLOCKED。
2. 若指标文件中发现敏感信息，停止并修正脱敏边界后再继续。
3. 若 tracked metrics 与现有 scope/gate 发生语义冲突，只扩展机械元数据边界，不放宽产品路径检查。

---

## 任务级进度（主代理维护）

### 任务锚点

- 基线 HEAD：`1a097f9`
- 契约提交：未提交（当前会话不执行 commit）
- 执行分支：`main`
- 执行 worktree：`D:/Projects/Skills/programing-pipeline`

### 验收台账

| 验收测试 | 状态 | 当前测试/命令 | 最新证据 | 备注 |
|---|---|---|---|---|
| AT1 | 已通过 | targeted automatic collection test | `.workflow/pipeline-tools-v1-continuation-1/full-test.raw.log` | task validate writes tracked event |
| AT2 | 已通过 | timeout feedback test | `.workflow/pipeline-tools-v1-continuation-1/full-test.raw.log` | stage + derived timeout |
| AT2B–AT2F | 已通过 | attribution/retry/argparse/redaction tests | `.workflow/pipeline-tools-v1-continuation-1/full-test.raw.log` | path and failure boundaries |
| AT3–AT3E | 已通过 | recursion/scope/identity tests | `.workflow/pipeline-tools-v1-continuation-1/full-test.raw.log` | forbidden override retained |
| AT4 / AT4B / AT4C / AT4D | 已通过 | full unittest suite | `.workflow/pipeline-tools-v1-continuation-1/full-test.raw.log` | 62 tests OK |
| AT5 | 已通过 | task validate / scope / compile / diff check / pnpm10 preflight | `.workflow/pipeline-tools-v1-continuation-1/runtime-preflight-pnpm10.json` | continuation contract and current runtime valid |

### 最终结果

- 状态：实现完成；Node 22.23.2 + pnpm 10.27.0 实测通过
- 执行子代理：未派发（主代理直接实现）
- 独立审查子代理：runtime preflight / reviewer handshake PASS（pnpm 10.27.0）
- 主代理最终检查：未开始
- 合并提交：不执行
- 合并后复验：未开始
- 遗留项：本任务产生的回溯/自动指标文件须在提交前逐项审查后再纳入 Git；指标模型已增加 task/run/terminal、真实通过率、恢复率与 evidence readiness，但旧 StoryLine 事件没有这些新维度时会保持 `null`/空过滤结果，不得回填猜测。
