# programing-pipeline

与具体产品和工具无关的多代理编程工作流，以及配套的 Python 机械闸门工具。

## 工作流边界

- 主代理负责任务拆分、冻结契约、真实设计判断、独立审查调度和最终裁决。
- 执行子代理在隔离 worktree 实现冻结任务。
- 审查子代理从独立上下文复验。
- `pipeline_tools` 只校验机械事实：契约结构、Git 身份、范围、命令退出码、证据身份和本地统计；它不判断产品语义，也不自动合并。

默认项目约定：

- 任务单：`docs/tasks/<task-id>.md`
- 任务证据：`.pipeline/<task-id>/`
- 项目级统计：`.pipeline/metrics/`（由工具自动生成并纳入 Git 追踪）
- 执行 worktree：`.worktrees/<task-id>`（主代理从主工作树创建唯一目录）
- 任务契约提交后冻结
- 合并前需要执行、独立审查和主代理终检；合并后在主工作树复验

创建实现 worktree 时，从仓库根目录执行：

```bash
git worktree add -b "<branch>" ".worktrees/<task-id>" "<baseline-head>"
```

`git worktree add` 会创建目标目录及缺失的 `.worktrees` 父目录，不需要预先 `mkdir`。项目根目录的 `.gitignore` 应包含 `/.worktrees/`。执行和审查子代理只使用主代理传入的 worktree，不自行创建第二个目录。

## 机械工具

Python 3.11 标准库即可运行；不联网、不遥测、不上传数据：

```bash
python -m pipeline_tools --help
python -m pipeline_tools task validate docs/tasks/<task-id>.md
python -m pipeline_tools task preflight . --contract <frozen-commit> --task-sheet docs/tasks/<task-id>.md
python -m pipeline_tools scope check . --allowed 'src/**' --forbidden '**/.env'
python -m pipeline_tools command run --cwd . --log .pipeline/<task-id>/test.log --timeout 180 -- python -m unittest
python -m pipeline_tools evidence verify .pipeline/<task-id> --task-id <task-id> --branch <branch>
python -m pipeline_tools gate pre-merge .pipeline/<task-id> --task-id <task-id> --branch <branch>
python -m pipeline_tools gate post-merge .pipeline/<task-id> --task-id <task-id> --branch <branch>
```

退出码：`0` 通过、`1` 被执行命令失败、`2` 参数/配置错误、`3` 证据不足或环境阻塞、`4` 身份/契约/范围漂移。

新任务单使用 `templates/task-sheet.md`，填完后复制其 `pipeline-contract` 区块；用 `templates/pipeline-evidence.json` 为 executor、reviewer 和 main-final 报告生成机器证据。空模板本身故意不能通过校验，填入真实字段后才应通过。

## 项目级反馈

除 `metrics` 子命令外，所有 `pipeline-tools` 阶段命令默认自动记录一个结构化指标事件到
目标项目的 `.pipeline/metrics/`。指标文件是可审查的流水线历史，应纳入 Git；不要把该目录
加入项目的 `.gitignore`。自动采集只使用命令退出码、结构化结果和可定位的证据路径，不会从
自然语言报告推断产品结论，也不会记录 token、凭据、完整命令输出或业务数据。

自动采集可以通过环境变量 `PIPELINE_TOOLS_DISABLE_AUTO_METRICS=1` 暂时关闭（仅用于测试或
明确的诊断场景）；正常任务执行不要关闭。`metrics` 子命令本身不递归生成阶段事件，但
`metrics record` 仍可用于补充经过直接证据确认的事件。

```bash
python -m pipeline_tools metrics record . retry --confidence observed --task-id <task-id> --result unknown --attempt 1
python -m pipeline_tools metrics report .
python -m pipeline_tools metrics report . --task-id <task-id> --terminal-only
python -m pipeline_tools metrics export . .pipeline/metrics-summary.json
python -m pipeline_tools metrics purge .
python -m pipeline_tools metrics import-opencode-session . <session-export.json> --task-id <task-id>
python -m pipeline_tools runtime preflight . --node 22.23.2 --pnpm 10.27.0
python -m pipeline_tools runtime handshake . .pipeline/<task-id> --role reviewer --node 22.23.2 --pnpm 10.27.0
python -m pipeline_tools runtime role-scope . --role main-agent --product-pattern 'packages/**'
python -m pipeline_tools --format json --output .pipeline/<task-id>/task-validate.json task validate docs/tasks/<task-id>.md
python -m pipeline_tools --format json lifecycle status . --task-id <task-id> --evidence .pipeline/<task-id>
python -m pipeline_tools dispatch write dispatch.json .pipeline/<task-id>/dispatch.json
python -m pipeline_tools result verify .pipeline/<task-id>/reviewer-result.json --task-id <task-id> --role reviewer
python -m pipeline_tools --format json freshness . .pipeline/<task-id> --result .pipeline/<task-id>/reviewer-result.json
python -m pipeline_tools --format json evidence readiness .pipeline/<task-id> --task-id <task-id>
```

自动事件和 `metrics record` 事件都逐文件原子写入 `.pipeline/metrics/`。只有 `observed` 和 `derived` 进入核心聚合；`reported` 只留作追溯。已有 `.workflow/` 的项目必须先把整个目录原样迁移到 `.pipeline/`，核对文件哈希并更新路径引用；迁移完成后不再使用旧目录。详见 `references/metrics-contract.md`。

`metrics import-opencode-session` 只从 OpenCode Desktop 的结构化导出中提取可验证的工具错误、子代理错误和用户流程纠正信号；不会把自然语言 PASS 当作验收事实。`runtime preflight` 应在派发 executor/reviewer 前执行，`runtime role-scope` 用于阻止未授权的主代理产品代码修改。正式 `evidence verify` 前先执行 `evidence readiness`，避免把尚未生成 final-check 的正常阶段顺序误报为最终证据缺陷。

结构化命令使用统一响应外壳：`schema`、`command`、`status`、`exit_code`、`observed`、`errors`、`blockers`、`artifacts`、`next_actions` 和 `unverified`。JSON 文件是流程编排输入，终端摘要只用于人类查看。

结构化闭环顺序为：`dispatch write` → agent 写入 `executor-result.json`/`reviewer-result.json` → `final-check` → `evidence readiness` → `result verify` → `freshness` → `lifecycle status` → merge gate。Markdown 报告用于人类阅读，JSON 结果用于机械编排。

## 测试

```bash
python -m unittest discover -s tests -v
```

Windows 入口：`bin\pipeline-tools.cmd`；POSIX 入口：`bin/pipeline-tools`。两者会把工具根目录加入 Python 模块搜索路径，因此可以从其他工作目录调用。

## 许可证

MIT，见 `LICENSE`。
