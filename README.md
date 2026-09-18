# programing-pipeline

与具体产品和工具无关的多代理编程工作流，以及配套的 Python 机械闸门工具。

## 工作流边界

- 主代理负责任务拆分、冻结契约、真实设计判断、独立审查调度和最终裁决。
- 执行子代理在隔离 worktree 实现冻结任务。
- 审查子代理从独立上下文复验。
- `pipeline_tools` 只校验机械事实：契约结构、Git 身份、范围、命令退出码、证据身份和本地统计；它不判断产品语义，也不自动合并。

默认项目约定：

- 任务单：`docs/tasks/<task-id>.md`
- 任务证据：`.workflow/<task-id>/`
- 项目级本地统计：`.workflow/metrics/`（必须未跟踪）
- 任务契约提交后冻结
- 合并前需要执行、独立审查和主代理终检；合并后在主工作树复验

## 机械工具

Python 3.11 标准库即可运行；不联网、不遥测、不上传数据：

```bash
python -m pipeline_tools --help
python -m pipeline_tools task validate docs/tasks/<task-id>.md
python -m pipeline_tools task preflight . --contract <frozen-commit> --task-sheet docs/tasks/<task-id>.md
python -m pipeline_tools scope check . --allowed 'src/**' --forbidden '**/.env'
python -m pipeline_tools command run --cwd . --log .workflow/<task-id>/test.log --timeout 180 -- python -m unittest
python -m pipeline_tools evidence verify .workflow/<task-id> --task-id <task-id> --branch <branch>
python -m pipeline_tools gate pre-merge .workflow/<task-id> --task-id <task-id> --branch <branch>
python -m pipeline_tools gate post-merge .workflow/<task-id> --task-id <task-id> --branch <branch>
```

退出码：`0` 通过、`1` 被执行命令失败、`2` 参数/配置错误、`3` 证据不足或环境阻塞、`4` 身份/契约/范围漂移。

新任务单使用 `templates/task-sheet.md`，填完后复制其 `pipeline-contract` 区块；用 `templates/pipeline-evidence.json` 为 executor、reviewer 和 main-final 报告生成机器证据。空模板本身故意不能通过校验，填入真实字段后才应通过。

## 项目级反馈

```bash
python -m pipeline_tools metrics record . retry --confidence observed --task-id <task-id> --result unknown --attempt 1
python -m pipeline_tools metrics report .
python -m pipeline_tools metrics export . .workflow/metrics-summary.json
python -m pipeline_tools metrics purge .
```

事件逐文件原子写入 `.workflow/metrics/`。只有 `observed` 和 `derived` 进入核心聚合；`reported` 只留作追溯。详见 `references/metrics-contract.md`。

## 测试

```bash
python -m unittest discover -s tests -v
```

Windows 入口：`bin\pipeline-tools.cmd`；POSIX 入口：`bin/pipeline-tools`。两者会把工具根目录加入 Python 模块搜索路径，因此可以从其他工作目录调用。

## 许可证

MIT，见 `LICENSE`。
