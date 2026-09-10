# 编程工作流（programing-pipeline）

一个与具体模型、产品和宿主 agent 无关的多代理编程工作流技能。

## 核心角色

- **主代理**：读取项目状态，设计目标与任务拆分，编写并冻结任务单，调度子代理，最终验收、合并和更新项目状态。
- **执行子代理**：在隔离 worktree 中实现冻结任务单，运行测试并写执行证据。
- **审查子代理**：使用独立上下文复验实现、验收测试、边界和证据，不修改产品代码。

宿主 agent 可以为长任务提供后台运行和恢复支持，但这不是工作流角色，也不参与验收判断。后台支持只属于宿主配置，不改变主代理、执行子代理和审查子代理之间的工作流契约。

## 目录

```text
SKILL.md
README.md
templates/task-sheet.md
references/
  acceptance-evidence.md
  execution-and-review.md
  live-and-browser.md
  merge-and-recovery.md
  multi-medium.md
  task-design.md
scripts/
  validate_task_sheet.py
```

## 使用方式

把本目录作为一个可加载的 agent skill，或将 `SKILL.md` 与其引用的 `templates/`、`references/`、`scripts/` 一起复制到目标 agent 的技能目录。具体的子代理调用命令、模型选择和通知方式由宿主 agent 提供，不写入本技能。

默认项目约定：

- 任务单：`docs/tasks/<task-id>.md`
- 任务证据：`.workflow/<task-id>/`
- 任务契约提交后冻结
- 合并前必须经过执行子代理、独立审查子代理和主代理最终检查
- 合并后必须在主工作树复验

## 校验任务单

```bash
python scripts/validate_task_sheet.py docs/tasks/<task-id>.md
```

## 许可证

MIT，见 `LICENSE`。
