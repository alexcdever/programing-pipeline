# Final read-only review — BLOCKED

Task ID: `pipeline-tools-v1-continuation-1`  
Worktree: `D:/Projects/Skills/programing-pipeline`  
Branch: `main`  
Role: `reviewer`  
Product write: `false`

## Capability gate

The required reviewer runtime handshake was run for this review and wrote
`.pipeline/pipeline-tools-v1-continuation-1/capability-handshake.json`. It is
`status=blocked` with `product_write=false`. The required PATH reports
`node --version=v22.23.2` but `pnpm --version=10.27.0`, not the required
`9.15.4`. Raw output is in
`.pipeline/pipeline-tools-v1-continuation-1/environment-validation-final-review.raw.log`;
the handshake output is in
`.pipeline/pipeline-tools-v1-continuation-1/runtime-handshake-final-review.raw.log`.

Acceptance is **BLOCKED by environment**. No test output is used as acceptance
evidence after the failed handshake. The pnpm mismatch is an environment
finding, not a product failure.

## Remaining concrete findings

### P1 — `metric_event` still permits credential-looking identifiers and paths

`pipeline_tools/core.py:399-416, 442-457` uses a narrower keyword list than
the existing `redact()` boundary (`core.py:23-36`) and does not call `redact()`.
For example, `task_id`/`reason` containing `authorization=...` or `passwd=...`,
an absolute-path-shaped task ID such as `C:\\Users\\alice`, and an
`evidence_ref` component named `authorization` or `passwd`, can survive
`metric_event()` after punctuation replacement. This violates the metrics
contract's no-credentials/no-token/absolute-path boundary. The sensitive
vocabulary and redaction policy must be unified at `metric_event`, with
boundary tests for `authorization`, `passwd`, `bearer`, `cvc`, and absolute
path-shaped identifiers.

### P2 — Help exits bypass the documented “every non-metrics command” event

`pipeline_tools/__main__.py:579-581` returns without recording whenever any
`-h`/`--help` token is present, including non-metrics stage help such as
`task validate --help`. The current README, skill, reference, and continuation
contract do not document help as an exemption from automatic collection. Either
record a mechanically attributed help event or explicitly narrow the contract
and tests to exclude help invocations.

### P2 — Automatic metric write failures are silently swallowed

`pipeline_tools/__main__.py:616-633` returns the events recorded so far on a
write/validation exception, and `main()` swallows any finalizer exception at
`__main__.py:791-798`. This correctly protects the original command exit code,
but it leaves no diagnostic when an automatic event or derived event was not
collected, contrary to `references/metrics-contract.md:13-16`. Preserve the
original exit code while emitting a bounded diagnostic or structured
“not-collected” record that cannot itself recurse.

### P2 — Parent frozen contract and continuation tracking policy still diverge

The working parent prose says metrics enter Git at
`docs/tasks/pipeline-tools-v1.md:57-67`, while its frozen
`pipeline-contract.allowed_paths` at `docs/tasks/pipeline-tools-v1.md:69-81`
still omits `.pipeline/metrics/**`. The continuation contract explicitly adds
that path at `docs/tasks/pipeline-tools-v1-continuation-1.md:10-22`, and the
implementation exempts it in `pipeline_tools/core.py:222-234` unless an
explicit forbidden pattern matches. This is a remaining machine-contract vs
continuation-policy mismatch: retain the parent contract as immutable history
and document the continuation override, or make the intended authority
unambiguous before acceptance.

### P2 — Task ledgers claim acceptance that the current evidence cannot support

`docs/tasks/pipeline-tools-v1-continuation-1.md:197-216` records AT1–AT5 as
`已通过` and says the implementation is complete, while the same section says
the reviewer is still blocked. The parent task also has the contradictory
`状态：未开始` at `docs/tasks/pipeline-tools-v1.md:11` and
`已合并并完成主工作树复验` at `docs/tasks/pipeline-tools-v1.md:221-229`.
These lifecycle claims must be reconciled; a failed current handshake cannot
be represented as an acceptance pass by carrying forward prior test/log claims.

## Areas checked with no remaining code finding

- The malformed non-metrics parse fallback now returns an `unknown` namespace
  and records `cli_parse_error`; recognized malformed groups retain their stage
  attribution (`__main__.py:380-435, 573-590`).
- The current finalizer guard preserves the original exit code when automatic
  attribution or metric writing fails (`__main__.py:791-798`).
- Relative command logs resolve against `--cwd`, and runtime handshake,
  runtime preflight, and lifecycle evidence references are now attributed from
  their supplied paths (`__main__.py:438-481, 502-509`).
- The metrics scope exemption is overridden by an explicit forbidden match;
  the current `scope_check` ordering at `core.py:225-234` is correct.

## Local generated files

The current `.pipeline/metrics/` directory contains untracked local generated
JSON samples. They are not blanket-add candidates; review task ownership and
sensitive content file by file before selecting any for Git. This review did
not stage or add them.

```pipeline-evidence
{
  "schema": 1,
  "task_id": "pipeline-tools-v1-continuation-1",
  "worktree": "D:/Projects/Skills/programing-pipeline",
  "branch": "main",
  "role": "reviewer",
  "round": 3,
  "status": "BLOCKED",
  "commands": [
    {
      "command": "powershell.exe -NoProfile -Command '<required PATH>; node --version; pnpm --version'",
      "exit_code": 0,
      "evidence_ref": ".pipeline/pipeline-tools-v1-continuation-1/environment-validation-final-review.raw.log"
    },
    {
      "command": "runtime handshake --role reviewer --node 22.23.2 --pnpm 9.15.4",
      "exit_code": 3,
      "evidence_ref": ".pipeline/pipeline-tools-v1-continuation-1/runtime-handshake-final-review.raw.log"
    }
  ],
  "assertions": [
    "reviewer product_write is false",
    "node is v22.23.2",
    "pnpm is 10.27.0 rather than the required 9.15.4",
    "acceptance is blocked by environment",
    "remaining findings are static review findings, not acceptance claims"
  ],
  "evidence_refs": [
    ".pipeline/pipeline-tools-v1-continuation-1/capability-handshake.json",
    ".pipeline/pipeline-tools-v1-continuation-1/environment-validation-final-review.raw.log",
    ".pipeline/pipeline-tools-v1-continuation-1/runtime-handshake-final-review.raw.log"
  ],
  "unverified": [
    "all acceptance tests under a passing runtime handshake"
  ]
}
```
