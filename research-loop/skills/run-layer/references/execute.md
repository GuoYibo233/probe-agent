# Executing a launch order

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

## Take a job only when a launch order says exactly what to run

This layer never starts something from a verbal description or a half-written plan -- only from a launch order file already on disk, fully specified (`tables/rows.json` → `launch_order`). If what's being asked for isn't a launch order yet, that's a deploy-layer job, not this layer's.

## Execution

Whatever `rails.gpu` resolves to in config runs the order: a skill name means route the launch there, a command/script path means run it directly with the launch order's path as the argument. On a bare project (or during plugin self-test) that resolves to the fallback:

```
python3 <plugin-root>/scripts/fallback/launch.py <launch_order> [--project-root <root>]
```

**Three rejection categories, checked in this order, before anything runs:**

1. **An explicit `--project-root` with no `research-loop.json` under it
   refuses before either of the other two checks even runs.** The fallback
   launcher resolves `--project-root` through the same `_lib.resolve_project_root`
   the other scripts share (`scripts/trace_check.py`, `regression_check.py`,
   `verify_report.py`, `doctor.py`) -- a wrong path raises `RLError`, caught
   by `main()`'s own handler: stderr gets just the error text
   (`--project-root <root> has no research-loop.json (wrong path?)`), exit
   code **2**, not 3. There's no "escalate to deploy layer" line here --
   this is a mis-invocation of the launcher (the wrong path was passed on
   the command line), not a fact about the repository state that the
   deploy layer needs to act on. Omitting `--project-root` never hits this
   path; it falls back to walking up from cwd instead.
2. **A dirty working tree always refuses the launch** -- except paths
   matching config's `dirty_exempt_globs`. "Dirty" is `git status
   --porcelain` on the launch order's `workdir`, filtered through that
   exempt list -- it counts **untracked-but-not-ignored files**, not just
   modified tracked ones. A single leftover scratch file (a stray draft
   launch order, a debug output) is enough to trip this; the fallback
   launcher's own stderr is `refuse to launch: dirty tree; escalate to
   deploy layer`, exit code 3.
3. **An `expected_commit` mismatch also refuses the launch.** The fallback
   rail compares it against this project's git HEAD (`-dirty` suffix
   stripped from both sides first) -- same stderr shape, same exit code:
   `refuse to launch: expected_commit mismatch (expected ..., got ...);
   escalate to deploy layer`, exit code 3. The deploy-layer skill's
   `references/launch-orders.md` covers where this field's value comes
   from and what the `no-git` sentinel means.

Categories 2 and 3 both escalate back to deploy (`references/failures.md`)
exactly the same way -- neither ever launches "just this once" against
uncommitted or unexpected code, and (see "Job-ledger registration" below)
neither ever gets an entry in the job ledger at all. Category 1 gets no
job-ledger entry either, but it is not a deploy-layer escalation: fix the
`--project-root` value passed to the launcher and re-invoke it.

**A launch that does start writes nothing to this session's own stdout on
failure.** The child process's stdout+stderr are captured straight to
`<artifact_dir>/attempt<N>.log` -- the launcher itself prints nothing about
what went wrong, only its own exit code. **Re-invoking the launcher on the
same launch order is not idempotent**: `attempt_no` is computed fresh each
call (`len(existing attempts) + 1`), so a second invocation genuinely
re-executes `argv` and appends a new attempt record -- it never resumes,
skips, or dedupes. Don't re-run it to "see what happens" while diagnosing a
silent failure; read the log the first attempt already wrote instead. Every
earlier attempt's own `argv`/log path/resources stay untouched byte for
byte in `RUNMETA.json` -- a rerun accumulates, never overwrites.

## After it lands

Before anything downstream trusts a number from this run, check the artifact:

```
python3 <plugin-root>/scripts/output_check.py --launch-order <launch_order>
```

`expected_outputs` cannot legally be empty (`#157`, non-empty at write
time) -- what this call actually reports is one of three verdicts: `ok`,
`missing-output` (a glob matched nothing), or `empty-output` (a file
matched but failed a size/line/key check). An exit code of 0 from the
*experiment process itself* with an empty or missing artifact is still not
`ok` here -- that distinction is what feeds R8's escalation path, not a
judgment call made here. See "Recording" below for what each of these three
verdicts means for `--status`.

## Recording

runs.jsonl normal rows go through the project's bookkeeping script (config `record_cmd`), or on a bare project, the fallback:

```
python3 <plugin-root>/scripts/fallback/record.py --launch-order <launch_order> [--status <status>]
```

This is the only path that writes a normal row -- never hand-type a number
into runs.jsonl from a log (R7). **This step does not apply to a refused
launch**: `record.py` hard-requires `<artifact_dir>/RUNMETA.json`, which a
launch refused at any of the three rejection categories above never produces
(`record: RUNMETA not found: ...`, exit 2) -- there is nothing to record,
and nothing downstream expects a row for it.

Omitting `--status` makes `record.py` derive it from the *last attempt's
exit code alone* (`ok` if 0, else `failed`) -- correct only when
`output_check`'s verdict was `ok`. When it wasn't, pass `--status`
explicitly; the two vocabularies don't share every name, so map by hand:

| `output_check` verdict | `record.py --status` |
|---|---|
| `ok` | omit `--status` (or `ok`) |
| `missing-output` | `empty-output` |
| `empty-output` | `empty-output` |

Both of `output_check`'s non-`ok` verdicts land on the single
`empty-output` value in `runs.status` -- there's no separate
`missing-output` value on the runs side. Passing nothing here when the
process exited 0 but produced an empty or missing artifact would let
`record.py`'s own default silently write `status=ok` -- exactly the bug
this whole gate exists to prevent (v1-run-6).

## Job-ledger registration

The fallback launcher already writes a base entry into `ops/jobs.json`
itself, keyed by `run_id`, right after every check above passes and right
before it starts the child process -- **so a launch that actually started
always has one** (a precheck rejection never reaches this point, so a
rejected launch gets no job-ledger entry at all; `tables/rows.json` →
`jobs_min_additions._precheck_refusal`). For categories 2 and 3 (dirty
tree, `expected_commit` mismatch) the refusal stderr is archived into the
escalation entry's evidence instead of dropped. Category 1 (invalid
`--project-root`) never gets that treatment: `main()`'s own exception
handler prints the `RLError` text and returns straight away, no blocked
entry is opened for it at all -- it's a mis-invocation of the launcher
caught before config or the job ledger's path are even resolved, not a
fact about a run that run-layer failure handling (`references/failures.md`)
would escalate; the invoker fixes the `--project-root` value and re-runs
the launcher directly. The base entry's
keys: `launch_order_ref`, `state` (`running` → `done`/`failed`/`timeout`),
`started_at`, `finished_at`, `log_path`.

This layer's own job is adding the **two required backrefs on top of
that** -- there is no `ledger.py jobs` verb; this is a direct edit to
`ops/jobs.json` in this session (run-layer SKILL.md §3 grants this file
directly, the same way deploy-layer's own SKILL.md §3 grants its owned
json/md files):

- **`escalation_ref`**: the `blocked_id` of the entry raised for this run,
  if one was (`references/failures.md`); `null` for a run that never
  needed escalating.
- **`sampler_verdict`** / **`sampler_verdict_at`**: one of `stall` /
  `dead` / `ok`, with an ISO-seconds timestamp, **only for a job that
  actually started** (a precheck-refused launch has no entry to add this
  to in the first place -- there is no fourth enum value for that case,
  because there is no row). The fallback rail carries no real sampler at
  all (config `stall_thresholds` reads as "the rail supplies its own
  judgment" when null, and the fallback rail supplies none) -- its own
  terminal `state` maps deterministically instead
  (`tables/rows.json` → `jobs_min_additions._fallback_mapping`):
  `done`/`failed` → `ok` (liveness is not the same question as success --
  both ran to a terminal state), `timeout` → `stall`. A real `rails.gpu`
  adapter with its own sampler reports whatever that sampler actually
  observed instead of this mapping.

The rest of the job ledger's fields follow whatever the project already
has.

## Zero code write

If running the order surfaces a code problem, this layer does not patch it -- see `references/failures.md` for what happens instead. Fixing code here would be writing outside this layer's authority, no matter how small the fix looks.
