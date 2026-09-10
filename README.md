# 编程工作流（programing-pipeline）

一个与具体模型、产品和工具无关的多代理编程工作流技能。

## 核心角色

- **主代理**：读取项目状态，设计目标与任务拆分，编写并冻结任务单，调度子代理，最终验收、合并和更新项目状态。
- **执行子代理**：在隔离 worktree 中实现冻结任务单，运行测试并写执行证据。
- **审查子代理**：使用独立上下文复验实现、验收测试、边界和证据，不修改产品代码。

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
