# Re-review — BLOCKED

Task ID: `pipeline-tools-v1-continuation-1`  
Worktree: `D:/Projects/Skills/programing-pipeline`  
Branch: `main`  
Role: `reviewer`  
Round: 2  
Product write: `false`

## Remaining findings

### P1 — Some argparse failures still produce no metric

`pipeline_tools/__main__.py:369-421` only recovers a stage when the raw argv
contains one of the known group names. `_record_automatic_metrics` then returns
without writing anything when that scan returns `None` (`:546-551`). Thus a
non-`metrics` invocation such as a missing group or an unknown top-level
subcommand has no automatic event, despite the contract covering every
non-`metrics` pipeline-tools invocation. Recognized groups with missing or bad
arguments are covered, but the top-level argparse-failure cases are not.

### P1 — Exit-code preservation is not closed over all attribution/path errors

The attribution block catches errors from `_auto_root_and_reference` and
`_auto_task_id`, but its fallback calls `_git_root(Path.cwd())` outside another
guard (`pipeline_tools/__main__.py:555-558`). The finalizer itself is also called
without a last-resort guard (`:742-755`). A `Path.resolve`/cwd failure in that
fallback can escape the `finally` block and replace the original command result.
The current tests do not force attribution/path failures for success, fail, and
config returns.

### P1 — Relative command logs still lose task identity when invoked outside cwd

`_auto_root_and_reference` correctly resolves a relative command log against
`--cwd` (`pipeline_tools/__main__.py:437-442`), but `_auto_task_id` passes the
unresolved `--log` value to `_task_id_from_path` (`:474-477`). That helper
resolves relative to the pipeline process cwd (`:311-322`), not the command
cwd. For `--cwd <project> --log .pipeline/demo/test.log` invoked from outside
`<project>`, the evidence reference can be correct while `task_id` becomes
`unknown` (or an unrelated task if the caller cwd has a matching path).

### P1 — Runtime/lifecycle evidence identity is still dropped

`_auto_root_and_reference` returns `(root, None)` for every `runtime` and
`lifecycle` command (`pipeline_tools/__main__.py:424-427`). This discards the
explicit `runtime handshake --workflow` capability-handshake artifact, runtime
preflight `--output`, and lifecycle `--evidence` identity. The automatic event
can therefore have the task id (for a handshake) but no evidence reference,
and cannot link lifecycle/preflight events to their supplied machine result.

### P1 — Sensitive-looking path components and derived task IDs are not fully redacted

The automatic path filter only rejects components that equal a short keyword
(`pipeline_tools/__main__.py:284-292`). Names such as
`reports/customer-token.csv`, `evidence/alice/password.log`, and
`api_token/result.json` pass through. The lower-level manual evidence path
normalizer has no sensitive-component check at all
(`pipeline_tools/core.py:404-413`), and command-derived task ids bypass
`_safe_task_id` (`pipeline_tools/__main__.py:474-477`). A path such as
`.pipeline/secret/test.log` can therefore persist `task_id: "secret"`, while
the existing test only covers an explicit safe task id plus a directory named
`secret`.

### P2 — The derived retry event does not preserve attempt 1

The condition now emits a retry for any positive attempt
(`pipeline_tools/__main__.py:528-529`), but the derived event construction does
not pass `attempt` (`:580-591`). Consequently `--attempt 1` produces a
`command_run` event with `attempt: 1` and a `retry` event whose default is
`attempt: 0`; its reason also still says `attempt_greater_than_one`. The test
only checks event names, so it does not catch this metric identity loss.

### P1 — Metrics tracking policy and the current event set are unresolved

The continuation contract and current README/reference require event files in
`.pipeline/metrics/` to be trackable, but the parent task still says metrics do
not enter Git (`docs/tasks/pipeline-tools-v1.md:57-67`, especially `:61`). The
working tree currently has no tracked `.pipeline/metrics` files and has 33
untracked JSON events, including historical `storyline-opencode-2026-09-18`
events and prior runs. Do not blanket-add this directory: retain only
deliberately approved current-task history after the sensitive-content review.
Resolve the parent/continuation policy conflict before acceptance.

### P2 — The export ignore rule was removed along with the event-directory rule

The current `.gitignore:1-7` no longer ignores `.pipeline/metrics-export.json`.
The requested policy is to track the event directory, not necessarily generated
aggregate exports; the metrics contract says aggregates can be deleted and
rebuilt (`references/metrics-contract.md:81`). Keep the event-directory policy
separate from export-file tracking unless that broader change is intentional.

## Environment / acceptance status

The required runtime handshake was run before acceptance with reviewer
`product_write=false` and written to
`.pipeline/pipeline-tools-v1-continuation-1/capability-handshake.json`.
It returned exit code `3` / `status=blocked`. The required PATH produced
`node --version = v22.23.2`, but `pnpm --version = 10.27.0` rather than the
required `9.15.4`; the handshake's Python subprocess check reported pnpm
unavailable/version mismatch. Raw outputs are in
`environment-validation.raw.log` and `runtime-handshake.raw.log`.

Because the handshake failed, no project tests, build, or Playwright acceptance
was run in this re-review. Acceptance is **BLOCKED by environment**; the
findings above are static code/test/document review findings, not test-pass
claims.

```pipeline-evidence
{
  "schema": 1,
  "task_id": "pipeline-tools-v1-continuation-1",
  "worktree": "D:/Projects/Skills/programing-pipeline",
  "branch": "main",
  "role": "reviewer",
  "round": 2,
  "status": "BLOCKED",
  "commands": [
    {
      "command": "powershell.exe -NoProfile -Command '<required PATH>; node --version; pnpm --version'",
      "exit_code": 1,
      "evidence_ref": ".pipeline/pipeline-tools-v1-continuation-1/environment-validation.raw.log"
    },
    {
      "command": "powershell.exe -NoProfile -Command '<required PATH>; python -m pipeline_tools runtime handshake ... --role reviewer --node 22.23.2 --pnpm 9.15.4'",
      "exit_code": 3,
      "evidence_ref": ".pipeline/pipeline-tools-v1-continuation-1/runtime-handshake.raw.log"
    }
  ],
  "assertions": [
    "reviewer product_write is false",
    "node version is correct",
    "pnpm version is not the required 9.15.4",
    "acceptance tests were not run after the failed handshake"
  ],
  "evidence_refs": [
    ".pipeline/pipeline-tools-v1-continuation-1/capability-handshake.json",
    ".pipeline/pipeline-tools-v1-continuation-1/environment-validation.raw.log",
    ".pipeline/pipeline-tools-v1-continuation-1/runtime-handshake.raw.log"
  ],
  "unverified": [
    "all acceptance tests under a valid handshake",
    "runtime behavior of the remaining findings"
  ]
}
```
