# 通用任务单

<!-- Task ID: <task-id> -->
<!-- Contract section is frozen after commit. Lifecycle sections are maintained by the main agent in this task sheet; no separate progress tracker is required. -->

```pipeline-contract
{
  "schema": 1,
  "task_id": "<task-id>",
  "allowed_paths": ["<repo-relative-or-explicit-sibling-path-pattern>"],
  "forbidden_paths": ["<path-pattern>"],
  "acceptance_tests": [
    {
      "id": "AT1",
      "evidence_level": 1,
      "test_ref": "<file>: <exact test name>",
      "command_ref": "<complete command>"
    }
  ]
}
```

`pipeline-contract` is the machine-checkable projection of this task sheet. Keep it synchronized with the human-readable contract; after the contract commit it is frozen.

## 任务身份

- 项目：<project name>
- 领域或阶段：<area / phase>
- 用户结果或系统能力：<one verifiable outcome>
- 执行 worktree 约定：`<仓库根目录>/.worktrees/<task-id>`，由主代理用 `git worktree add` 创建；不预先 `mkdir`，不创建仓库同级或第二个 worktree
- 状态：未开始

## 依赖与范围

### 前置条件

- <已合并任务、架构决策、文档、工具或环境>

### 允许修改

- <生产代码、测试、文档和任务级证据>

### 明确不改

- <禁止修改的文件、接口、行为、迁移或清理>

## 事实、假设与待决

### 已确认事实

- <文件/符号/命令输出/架构决策及其来源>

### 未验证事实

- <尚未读取、运行或确认的内容；不得写成已实现或已通过>

### 禁止猜测

- <会改变产品行为、协议、数据格式、权限或验收边界的待决事项>

## 设计与行为契约

[触发] <用户动作或系统事件>
→ [处理] <前端、核心服务、领域或协议>
→ [状态] <领域事实、文档或持久化变化>
→ [可见结果] <界面、接口、文件、通知或重启后的结果>

- <必须保持的不变量>
- <失败、重试、幂等、隔离和恢复规则>

## 环境前置

1. `<命令或设置步骤>`
2. `<依赖、服务、设备或测试数据要求>`

## 验收测试

### 验收测试1：<名称>

- 触发：<真实用户动作或系统事件>
- 断言：<可观察结果、状态/持久化结果和恢复结果>
- 测试：`<文件路径>: <精确用例名>`
- 命令：`<从正确工作目录执行的完整命令>`
- 验收模式：<单元 / 组件 / 协议 / 集成 / 真实浏览器 / 真实设备 / 其他>
- 证据等级：<1 / 2 / 3 / 4 / 5>
- 结果要求：<退出码、输出、隔离、产物和超时>

### 验收测试2：<名称>

- 触发：<真实用户动作或系统事件>
- 断言：<可观察结果>
- 测试：`<文件路径>: <精确用例名>`
- 命令：`<完整命令>`
- 验收模式：<单元 / 组件 / 协议 / 集成 / 真实浏览器 / 真实设备 / 其他>
- 证据等级：<1 / 2 / 3 / 4 / 5>
- 结果要求：<当前命令的明确通过边界>

## 决策点

出现以下情况时，保留 worktree 并报告给主代理，不得静默改变契约：

1. <产品或架构设计冲突>
2. <缺失环境、权限或外部依赖>
3. <验收要求超出当前范围>

---

## 任务级进度（主代理维护）

> 以下内容不是新的设计权威。契约区在提交后冻结；此处记录进度、裁决和最终结果。

### 任务锚点

- 基线 HEAD：-
- 契约提交：-
- 执行分支：-
- 执行 worktree：<仓库根目录>/.worktrees/<task-id>（核对后的绝对路径）

### 验收台账

| 验收测试 | 状态 | 当前测试/命令 | 最新证据 | 备注 |
|---|---|---|---|---|
| 验收测试1 | 未开始 | - | - | - |

### 执行记录

| 时间/轮次 | 事件 | 结果 | 证据 | 后续 |
|---|---|---|---|---|
| - | 任务单创建 | 未开始 | - | 派发执行子代理 |

### 设计变更与延续任务索引

- 无。如需设计裁决，建立延续任务并链接 `docs/tasks/<task-id>-continuation-N.md`；机器路径保留 `continuation`，不得覆盖本任务历史。

### 最终结果

- 状态：未开始
- 执行子代理：未开始
- 独立审查子代理：未开始
- 主代理最终检查：未开始
- 合并提交：-
- 合并后复验：未开始
- 遗留项：-
