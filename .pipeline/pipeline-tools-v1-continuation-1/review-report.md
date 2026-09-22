# Independent review — BLOCKED

Task ID: `pipeline-tools-v1-continuation-1`  
Worktree: `D:/Projects/Skills/programing-pipeline`  
Branch: `main`  
Role: `reviewer`  
Round: 1

## Capability and environment gate

The required reviewer runtime handshake was run before acceptance work with
`reviewer.product_write=false`. It returned `status=blocked`, exit code `3`:

- `node --version`: `v22.23.2` (valid)
- `pnpm --version`: `10.27.0` from the required PATH (required `9.15.4`, invalid)
- handshake subprocess result: `pnpm unavailable`, `pnpm version mismatch`

The authoritative handshake is
`.pipeline/pipeline-tools-v1-continuation-1/capability-handshake.json`.
Because the handshake failed, this review cannot produce an acceptance PASS or
ready-to-merge recommendation. Any later test invocation is non-admissible
under the workflow gate.

## Findings

### P1 — Automatic collection is skipped for argparse failures

`pipeline_tools/__main__.py:529-533` lets `argparse.parse_args()` raise
`SystemExit` for missing/invalid arguments. `main()` only calls
`_record_automatic_metrics()` when `_main()` returns normally
(`__main__.py:672-681`), so malformed non-`metrics` stage invocations produce
no observed event. This violates the “every non-metrics command” contract and
has no test coverage. The implementation should preserve argparse's existing
exit code while recording a minimal mechanically-derived event for the parsed
command family when that can be done safely.

### P1 — Metrics write/attribution exceptions can replace the original exit code

`__main__.py:486-487` and `394-452` perform path resolution and JSON/contract
reads before the protected write block at `475-525`. For example, a malformed
non-UTF-8 structured result can raise `UnicodeDecodeError` in `_auto_task_id()`;
symlink-loop resolution can also raise outside the handled exceptions. The
exception escapes `main()`'s `finally`, changing the command's exit behavior,
contrary to `references/metrics-contract.md:13-16`. Add a regression test that
forces attribution/metric failure for success, fail, and config/error paths and
asserts the original code is returned.

### P1 — Automatic evidence attribution is missing for several stages

`__main__.py:362-391` returns `(root, None)` for all `runtime` and `lifecycle`
commands. Consequently a successful handshake does not reference the
machine-readable `capability-handshake.json`, and lifecycle/evidence state is
not linked to its supplied evidence directory. `scope` also has no task-id or
evidence input and currently records `task_id=unknown` (visible in the
untracked generated events). This weakens the required task/evidence audit
trail; tests cover only command-log and task-sheet attribution
(`tests/test_cli.py:120-165`).

### P1 — Retry feedback has an off-by-one condition

`__main__.py:462-463` emits `retry` only when `--attempt > 1`, while the public
example uses `--attempt 1` for a retry (`README.md:50-51`) and aggregation counts
any positive attempt (`pipeline_tools/core.py:537`). A first retry therefore
does not get the required derived event. Add an automatic `--attempt 1` test and
align the threshold with the documented attempt semantics.

### P1 — The automatic-collection test matrix covers only two stage families

`tests/test_cli.py:120-165` exercises `task validate` and `command run`, plus
the recursion guard. There are no automatic-event assertions for `scope`,
`task preflight`/`freeze-check`, `evidence`, `gate`, `runtime`, `lifecycle`,
`dispatch`, `result`, or `freshness`, and no matrix for their success, failure,
configuration-error, and blocked paths. Therefore the “all non-metrics
commands” promise is not regression-protected, especially for the argparse and
attribution paths above.

### P2 — Relative command log references are resolved against the wrong cwd

For `command run`, `__main__.py:374-376` passes `Path(args.log)` directly to
`_safe_project_reference()`, which resolves it against the pipeline process's
current directory. `run_command()` resolves a relative log against
`args.cwd` (`pipeline_tools/core.py:110`). Invoking the documented
`--cwd <project> --log .pipeline/...` form from outside the project can thus
write the log in the project but record a null/wrong evidence reference. Add a
non-project-cwd test.

### P2 — Sensitive path material is not sanitized

Automatic evidence refs are copied verbatim after only absolute/traversal
checks (`__main__.py:284-292`; `pipeline_tools/core.py:404-413`). A relative
path such as `reports/customer-token.csv` or `evidence/alice/password.log`
would be persisted in metrics, despite the task's no-sensitive-data boundary
and `references/metrics-contract.md:55-60`. Either constrain evidence refs to
safe generated locations or redact/reject sensitive path components, with
tests for filenames and task IDs containing sensitive-looking data.

### P2 — `.gitignore` change is broader than the request

The diff removes both `.pipeline/metrics/` and
`.pipeline/metrics-export.json` from `.gitignore`. The request requires the
event directory to be trackable; it does not require generated export files to
become trackable. Preserve the export ignore rule unless intentionally
changing that policy. The current tracking test is insufficient:
`tests/test_cli.py:137` runs `git check-ignore` in a fresh temp directory with
no project `.gitignore`, so it would pass even if the repository still ignored
metrics.

### P2 — Scope exemption lacks forbidden-path and tracked-change coverage

`pipeline_tools/core.py:221-234` intentionally exempts `.pipeline/metrics/**`
from scope drift, but the only test (`tests/test_git_checks.py:36-42`) checks an
untracked file and does not verify that an explicit forbidden pattern still
wins, or that modified/deleted tracked metric files behave as intended. Add
those cases before relying on this safety boundary.

## Generated files / scope

The working tree currently contains 26 untracked `.pipeline/metrics/*.json`
events, including historical `opencode_session` records and prior
`pipeline_tools` runtime events. The tests use temporary directories for their
metric fixtures; these repository-root files are not test fixtures and should
not be blanket-added. Keep only deliberately approved workflow-history events
after checking task ownership and sensitive path content. The reviewer
handshake/raw logs and this report are workflow evidence, not product source.

## Test observation (not acceptance evidence)

A bounded full-suite invocation was attempted after the blocked handshake and
printed `Ran 45 tests in 17.567s` / `OK`. Per the failed capability/environment
gate, that result is explicitly non-admissible and is not used to claim PASS.

```pipeline-evidence
{
  "schema": 1,
  "task_id": "pipeline-tools-v1-continuation-1",
  "worktree": "D:/Projects/Skills/programing-pipeline",
  "branch": "main",
  "role": "reviewer",
  "round": 1,
  "status": "BLOCKED",
  "commands": [
    {
      "command": "powershell.exe -NoProfile -Command '<required PATH>; python -m pipeline_tools runtime handshake ... --role reviewer --node 22.23.2 --pnpm 9.15.4'",
      "exit_code": 3,
      "evidence_ref": ".pipeline/pipeline-tools-v1-continuation-1/runtime-handshake.raw.log"
    },
    {
      "command": "powershell.exe -NoProfile -Command '<required PATH>; node --version; pnpm --version'",
      "exit_code": 3,
      "evidence_ref": ".pipeline/pipeline-tools-v1-continuation-1/environment-validation.raw.log"
    }
  ],
  "assertions": [
    "reviewer product_write is false",
    "runtime handshake is blocked because pnpm is not the required 9.15.4",
    "acceptance is blocked and no readiness claim is made"
  ],
  "evidence_refs": [
    ".pipeline/pipeline-tools-v1-continuation-1/capability-handshake.json",
    ".pipeline/pipeline-tools-v1-continuation-1/runtime-handshake.raw.log",
    ".pipeline/pipeline-tools-v1-continuation-1/environment-validation.raw.log"
  ],
  "unverified": [
    "full acceptance suite under a valid handshake",
    "all automatic argparse/error paths",
    "automatic metric write-failure exit-code preservation"
  ]
}
```

Final disposition: **BLOCKED; not ready for acceptance/merge.**
