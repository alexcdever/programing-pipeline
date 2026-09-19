# 项目级反馈事件契约

项目级反馈是从任务证据派生的本地统计，不是验收证据，不回写任务契约、技能规则或产品数据。目录固定为项目根目录的 `.workflow/metrics/`，必须由项目 `.gitignore` 忽略。

## 可信度与来源

| `confidence` | 含义 | 是否进入核心聚合 |
|---|---|---|
| `observed` | 工具或主代理本轮直接读取 Git、命令输出、产物后记录 | 是 |
| `derived` | 由已观察事件按固定规则计算 | 是 |
| `reported` | 代理自述但没有当前原始证据 | 否，仅保留追溯 |

缺失字段必须保留为 `null` 或 `unknown`；不得把未记录 token、未执行命令或未知结果写成零或 PASS。

## 事件文件

每次 `metrics record` 写一个独立 JSON 文件，先写同目录临时文件再原子替换。每个事件只允许以下字段：

```json
{
  "schema": 1,
  "event_id": "opaque-id",
  "recorded_at": 0,
  "event": "retry",
  "confidence": "observed",
  "task_id": "safe-task-id",
  "result": "unknown",
  "duration_s": null,
  "timed_out": null,
  "token_count": null,
  "reason": null,
  "attempt": 0,
  "evidence_ref": ".workflow/task-id/raw-command.log",
  "blocker_class": null,
  "source": null
}
```

- `task_id`、`event`、`reason` 只保存安全字符 `[A-Za-z0-9._-]`；其他字符替换为 `_`。
- `evidence_ref` 只能是项目内相对路径；绝对路径、`..` 和空值以外的非法值拒绝写入。
- 不记录原始 prompt、源代码、完整命令输出、完整日志、绝对路径、用户名、邮箱、凭据、令牌或业务数据。
- `token_count` 只有运行时提供实际值才填写；字符数或估算值不能冒充实际 token。
- `blocker_class` 可为 `product`、`environment`、`permission`、`evidence`、`dependency` 或 `workflow`；用于区分产品失败与执行环境/流程阻塞。
- `source` 只保存短的结构化来源标识，例如 `opencode_session`，不得保存原始会话内容。

## 固定事件名

优先使用以下事件名，避免自由文本拆散统计口径：

| 事件 | 触发条件 |
|---|---|
| `review_overturn` | 执行阶段报告 PASS，独立审查或终检改判 FAIL/BLOCKED |
| `retry` | 同一冻结契约下再次执行 |
| `timeout` | 有界命令或任务超时 |
| `evidence_gap` | 缺命令、退出码、产物、身份或新鲜证据 |
| `post_merge_regression` | 合并后复验推翻 worktree 结论 |
| `environment_block` | runtime、Node/pnpm、native ABI 或测试能力不可用 |
| `permission_block` | OpenCode 工具/代理权限阻止了所需操作 |
| `main_agent_product_edit` | 主代理未获授权修改产品代码 |
| `user_continue_nudge` | 用户要求继续推进已开始的任务 |
| `user_process_correction` | 用户纠正停滞、角色或流程行为 |
| `recovery_path_miss` | 恢复阶段读取了不存在或错误路径 |

`aggregate`、`report` 和 `export` 只从事件文件重建摘要，至少输出成功率、reported 排除数量、token 已知/未知数量、阻塞类型计数、用户流程纠正、主代理产品修改，以及上表的事件计数。聚合文件可以删除后重建。

## 反馈边界

统计只能生成后续优化问题，不得自动：

- 降低验收证据等级；
- 删除独立审查或合并后复验；
- 改写任务契约、产品设计或技能规则；
- 上传数据或访问网络；
- 把单次样本当成趋势。

评估节省 token 的流程优化时，至少同时观察证据缺口、审查推翻、合并后回归和高等级验收数量；任一恶化时，不能把 token 下降判为成功。
