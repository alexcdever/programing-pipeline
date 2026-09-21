# 编程流水线工具 v1：机械闸门与项目级反馈

<!-- Task ID: pipeline-tools-v1 -->
<!-- Contract section is frozen after commit. Lifecycle sections are maintained by the main agent. -->

## 任务身份

- 项目：programing-pipeline（内置 `pipeline_tools`）
- 领域或阶段：工作流机械化 / v1
- 用户结果或系统能力：使用不依赖大模型判断的 Python 命令程序，校验任务契约、Git 身份、改动范围、任务证据和有界命令执行，并在项目 `.workflow/metrics/` 生成脱敏反馈统计。
- 状态：已合并；自动指标采集由 `pipeline-tools-v1-continuation-1` 补充

## 依赖与范围

### 前置条件

- `programing-pipeline` 当前基线提交 `88c75d3`；本任务会在工具 worktree 内同步接线改动，父技能接线证据以本任务最终提交为准。
- Python 3.11 标准库；不依赖网络、第三方 Python 包或特定项目语言。
- 工具源码已并入 `programing-pipeline/pipeline_tools`；不再维护独立 `programing-pipeline-tools` worktree。

### 允许修改

- 新建 `D:/Projects/Skills/programing-pipeline-tools/**`：命令程序、测试、文档、启动包装器和任务级证据。
- `programing-pipeline/SKILL.md`：增加最小工具调用契约和机械检查边界。
- `programing-pipeline/README.md`：增加工具安装、调用和项目数据目录说明。
- `programing-pipeline/references/metrics-contract.md`：定义项目级统计事件、脱敏、可信度和禁止反馈回写规则。
- `programing-pipeline/templates/task-sheet.md`：增加机器可读 `pipeline-contract` 区块以及工具调用所需的最小字段。
- `programing-pipeline/scripts/validate_task_sheet.py`：保留兼容入口，并与新模板的字段约束一致。

### 明确不改

- 不修改任何产品项目源码、任务单、既有 workflow 证据或用户数据。
- 不实现远程遥测、云端服务、自动上传、自动修改技能或自动合并。
- 不让命令程序从自由文本猜测产品结论；不把代理自述当作观察事实。
- 不把原始 prompt、源代码、完整日志、绝对路径、用户名、邮箱、凭据、令牌或业务数据写入 metrics。
- 不新增第三方运行依赖；不要求用户安装 Node.js、数据库服务或网络服务。

## 事实、假设与待决

### 已确认事实

- 当前技能已有 `scripts/validate_task_sheet.py`，但只做 Markdown 结构检查。
- 当前技能要求任务证据位于 `.workflow/<task-id>/`，项目级反馈数据应位于 `.workflow/metrics/`。
- 机械校验应 fail closed；统计数据是派生反馈，不是验收证据。

### 未验证事实

- Windows 子进程树在不同项目命令下的终止行为，需要用本工具测试的短命令验证；未覆盖的特殊进程模型不声称已验证。
- 不同项目的报告自然语言格式不完全一致，因此 v1 只验证稳定身份字段和必要证据标记，不解析产品语义。

### 禁止猜测

- 不得把命令退出码之外的自然语言描述推断为测试通过。
- 不得把缺失 token 用量、缺失原始输出或未执行的命令记为零或 PASS。
- 不得根据统计趋势自动改变验收等级、审查阶段、技能规则或产品契约。

## 设计与行为契约

主代理提供已冻结任务单、项目根目录和明确命令参数；工具程序只执行可验证的机械检查或记录已声明事实：

触发命令 → 解析任务契约/Git/报告/命令输出 → 生成结构化 PASS、FAIL、BLOCKED 或契约漂移结果 → 原始输出落盘、终端只返回短摘要；metrics 写入项目 `.workflow/metrics/`，作为可审查工作流历史进入 Git。

- 工具程序使用稳定退出码：`0` 通过，`1` 观察到产品/测试失败，`2` 参数或配置错误，`3` 证据不足或环境阻塞，`4` 身份、契约或范围漂移。
- 任务单中的 `pipeline-contract` JSON 区块是机械检查投影；任务单正文供人阅读，工具不得通过自由文本补全缺失字段。
- 统计事件的可信度只有 `observed`、`derived`、`reported`；只有前两者进入核心聚合，缺失值保持 `unknown`/`null`。
- metrics 事件逐文件原子写入，禁止多个代理共同追加一个共享文件；汇总可删除并由事件重建。
- 任何命令都必须有明确工作目录、超时和日志路径；超时后记录现场并停止，不无限重试。

```pipeline-contract
{
  "schema": 1,
  "task_id": "pipeline-tools-v1",
  "allowed_paths": [
    "D:/Projects/Skills/programing-pipeline-tools/**",
    "SKILL.md",
    "README.md",
    "references/metrics-contract.md",
    "templates/task-sheet.md",
    "scripts/validate_task_sheet.py",
    "docs/tasks/pipeline-tools-v1.md",
    ".workflow/metrics/**",
    ".workflow/pipeline-tools-v1/**"
  ],
  "forbidden_paths": [
    "package.json",
    "pnpm-lock.yaml",
    "**/.env",
    "**/*secret*",
    "**/*token*"
  ],
  "acceptance_tests": [
    {"id": "AT1", "evidence_level": 3, "test_ref": "tests/test_contract.py", "command_ref": "python -m unittest discover -s tests"},
    {"id": "AT2", "evidence_level": 2, "test_ref": "tests/test_git_checks.py", "command_ref": "python -m unittest discover -s tests"},
    {"id": "AT3", "evidence_level": 1, "test_ref": "tests/test_runner.py", "command_ref": "python -m unittest discover -s tests"},
    {"id": "AT4", "evidence_level": 2, "test_ref": "tests/test_evidence.py", "command_ref": "python -m unittest discover -s tests"},
    {"id": "AT5", "evidence_level": 1, "test_ref": "tests/test_metrics.py", "command_ref": "python -m unittest discover -s tests"},
    {"id": "AT6", "evidence_level": 1, "test_ref": "tests/test_cli.py", "command_ref": "python -m unittest discover -s tests"}
  ]
}
```

## 环境前置

1. 在 `programing-pipeline` 主工作树确认 `git status --short --branch` 干净后提交本任务单，再创建实现 worktree。
2. 新工具使用 Python 3.11 标准库；测试不访问网络、不读取用户项目数据。
3. 每条测试命令使用外层 180 秒硬上限；工具内部命令也必须有明确超时。
4. 测试临时 Git 仓库和临时项目目录必须由测试自行创建并清理。

## 验收测试

### 验收测试1：任务契约和模板硬校验

- 触发：对完整、缺字段、证据等级缺失、占位符未替换和契约 JSON 非法的任务单执行 `task validate`。
- 断言：完整任务单 exit 0；缺字段、非法 JSON、占位符和每条验收测试字段缺失分别返回可定位错误，不生成 PASS。
- 测试：`tests/test_contract.py`：契约解析和校验相关用例。
- 命令：`python -m unittest discover -s tests -p 'test_contract.py' -v`
- 验收模式：命令程序单元测试
- 证据等级：1
- 结果要求：所有用例通过；错误摘要不包含绝对路径或敏感值。

### 验收测试2：Git 身份、冻结和改动范围

- 触发：在临时 Git 仓库中创建契约提交、修改冻结区、制造允许和禁止路径改动，执行 `preflight`、`freeze-check`、`scope check`。
- 断言：正确的 HEAD、branch、worktree 和契约提交通过；冻结区变化、契约提交不在祖先链、禁止路径或未匹配允许路径改动返回 exit 4；未跟踪文件也被检查。
- 测试：`tests/test_git_checks.py`：Git 检查相关用例。
- 命令：`python -m unittest discover -s tests -p 'test_git_checks.py' -v`
- 验收模式：临时真实 Git 仓库集成测试
- 证据等级：2
- 结果要求：所有用例通过；不修改被测仓库之外的文件。

### 验收测试3：有界命令执行和失败现场

- 触发：执行一个成功命令、失败命令和超过超时的命令。
- 断言：输出写入指定日志；终端返回脱敏后的命令摘要、退出码、耗时和日志路径；超时返回 exit 3，记录 `timed_out=true` 并停止子进程，不无限等待。
- 测试：`tests/test_runner.py`：命令执行和超时用例。
- 命令：`python -m unittest discover -s tests -p 'test_runner.py' -v`
- 验收模式：真实 Python 子进程
- 证据等级：1
- 结果要求：所有用例在 180 秒内完成；测试不留下受控子进程。

### 验收测试4：任务证据和合并闸门

- 触发：对完整报告、缺报告、身份不匹配、缺命令/退出码/断言的报告目录执行 `evidence verify` 和 `gate pre-merge`。
- 断言：三份报告存在且身份、命令、退出码、关键断言和证据路径齐全时通过；任一缺失返回 exit 3 或 4；统计目录不被当作验收证据。
- 测试：`tests/test_evidence.py`：报告、范围和闸门用例。
- 命令：`python -m unittest discover -s tests -p 'test_evidence.py' -v`
- 验收模式：命令程序集成测试
- 证据等级：2
- 结果要求：错误能指出缺失项；不根据代理自述或旧报告补全 PASS。

### 验收测试5：项目级脱敏反馈统计

- 触发：初始化 `.workflow/metrics/`，记录 observed/derived/reported 事件，聚合并输出报告。
- 断言：每事件独立原子文件；任务和项目标识不保存绝对路径；reported 不进入核心成功率；缺失 token 为 null/unknown；审查推翻、重试、超时、证据缺口和合并后回归可从 observed/derived 事件计算；汇总可由事件重建。
- 测试：`tests/test_metrics.py`：脱敏、聚合、重建和未知值用例。
- 命令：`python -m unittest discover -s tests -p 'test_metrics.py' -v`
- 验收模式：命令程序单元/文件测试
- 证据等级：1
- 结果要求：统计输出不包含源代码、完整 prompt、完整日志、绝对路径、用户名、邮箱、凭据或令牌；所有用例通过。

### 验收测试6：安装/启动入口和短摘要输出

- 触发：从工具项目根目录执行模块入口及 Windows/POSIX 启动包装器。
- 断言：`python -m pipeline_tools --help`、`task validate`、`metrics report` 可运行；正常只输出短摘要，完整数据留在指定文件；错误退出码稳定。
- 测试：`tests/test_cli.py`：模块入口和子命令用例。
- 命令：`python -m unittest discover -s tests -p 'test_cli.py' -v`
- 验收模式：命令程序真实启动
- 证据等级：1
- 结果要求：所有用例通过；不要求网络或额外依赖。

## 决策点

出现以下情况必须保留现场并报告，不得自行扩展范围：

1. 需要第三方运行依赖、远程服务、遥测或云端数据库才能实现核心能力。
2. Windows 进程树无法在当前安全方式下有界停止，或会误杀不属于本命令的进程。
3. 任务单正文与 `pipeline-contract` 机器区块发生语义冲突，无法通过机械校验确定权威来源。
4. 需要修改现有产品项目的代码、任务契约或历史证据才能让工具测试通过。
5. 需要把自然语言报告解析成产品 PASS，或把 reported 数据纳入成功率。

---

## 任务级进度（主代理维护）

> 以下内容不是新的设计权威。契约区在提交后冻结；此处记录进度、裁决和最终结果。

### 任务锚点

- 基线 HEAD：88c75d3cd8a7d315ef52cf98686c555db0f1252e
- 契约提交：d9a4909
- 执行分支：pipeline-tools-v1
- 执行 worktree：D:/Projects/Skills/programing-pipeline-tools

### 验收台账

| 验收测试 | 状态 | 当前测试/命令 | 最新证据 | 备注 |
|---|---|---|---|---|
| 验收测试1 | 已通过 | `python -m unittest discover -s tests -p 'test_contract.py'` | `.workflow/pipeline-tools-v1/unittest-full.log`（28 tests OK，含契约用例） | 契约 fail-closed 11 种失败模式由审查探针复核 |
| 验收测试2 | 已通过 | `python -m unittest discover -s tests -p 'test_git_checks.py'` | 同上 | freeze/scope 身份检查含临时真实 Git 仓库 |
| 验收测试3 | 已通过 | `python -m unittest discover -s tests -p 'test_runner.py'` | 同上 | 超时=3、进程树终止、脱敏均覆盖 |
| 验收测试4 | 已通过 | `python -m unittest discover -s tests -p 'test_evidence.py'` | 同上 | 机器证据、身份不匹配、散文拒绝、gate 状态闸门 |
| 验收测试5 | 已通过 | `python -m unittest discover -s tests -p 'test_metrics.py'` | 同上 | reported 不入核心、token null、往返重建 |
| 验收测试6 | 已通过 | `python -m unittest discover -s tests -p 'test_cli.py'` | 同上 | 模块入口、退出码、bin 包装器、真实任务单 |

### 执行记录

| 时间/轮次 | 事件 | 结果 | 证据 | 后续 |
|---|---|---|---|---|
| 2026-09-18 / 创建 | 主代理读取技能现状与既有 validate_task_sheet.py，设计工具任务契约 | 设计完成 | `docs/tasks/pipeline-tools-v1.md`（契约提交 d9a4909） | 创建工具 worktree 并派发执行 |
| 2026-09-18 / 执行 round 1 | 执行子代理 sa-0-68139c61 实现 v1 | 1800 秒超时，未提交部分实现保留 | 会话记录 | 重派 |
| 2026-09-18 / 执行 round 2 | 执行子代理 sa-0-c5053021 修复收尾 | 1800 秒超时，CLI 测试从 7 失败降到 3 失败 | 会话记录 | 主代理接管 |
| 2026-09-18 / 执行 round 3 | 主代理接管：修复契约正则、porcelain strip 缺陷、机器证据格式，24→28 tests 全绿 | 全绿 | `executor-report.md` round 3 | 派发独立审查 |
| 2026-09-18 / 审查 round 1-2 | 审查子代理两次派发 | 均 1800 秒超时，留下部分 review-*.log | review-*.log | 缩小范围重派 |
| 2026-09-18 / 审查 round 3 | 审查子代理 sa-0-e4393c91 极短复核 | PASS（28 tests、validate/preflight/scope 全 exit 0） | `review-report.md` round 3 | 主代理终检 |
| 2026-09-18 / 终检 round 4 | 主代理终检：发现并修复 `_read_machine_evidence` 的 `\\n` 字面量缺陷与重复函数定义；串行重跑 4 项关键验收全部 exit 0 | READY-TO-MERGE | `final-check.md` round 4；evidence verify + gate pre-merge 均 PASS | 等待用户批准 |
| 2026-09-18 / 合并后复验 | fast-forward 合并到 main；主工作树复验 | PASS（31 tests、身份/范围/证据/合并后闸门全通过） | 主工作树终端输出 | 任务完成，等待推送 |

### 设计变更与 continuation 索引

- [`pipeline-tools-v1-continuation-1`](pipeline-tools-v1-continuation-1.md)：将指标从显式可选记录改为非 `metrics` 阶段命令的自动采集，并允许 `.workflow/metrics/**` 作为可审查 Git 历史；不改变验收结论语义。

### 最终结果

- 状态：已合并并完成主工作树复验
- 执行子代理：完成（round 1-2 子代理超时，round 3 主代理接管完成）
- 独立审查子代理：完成（round 1-2 子代理超时，round 3 缩小范围复核 PASS）
- 主代理最终检查：通过（`final-check.md`，4/4 exit 0 + evidence verify + gate pre-merge PASS）
- 合并提交：932a351
- 合并后复验：通过（31 tests；task validate/preflight；scope；evidence verify；gate post-merge）
- 遗留项：POSIX bin 包装器未在 Windows 实跑（Windows cmd 包装器已由测试覆盖）；自动指标 continuation 已在 Node 22.23.2 + pnpm 10.27.0 环境完成 preflight、reviewer handshake 和完整测试复验。
