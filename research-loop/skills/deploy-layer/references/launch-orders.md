# Launch orders

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

One launch order = one logical experiment, named by `run_id`. Its full
field contract -- what's required, what's optional, what each field means
-- is `tables/rows.json` → `launch_order`; read it there rather than from a
second copy here. `argv` is the authoritative execution body (what the
rails and fallback launcher actually run); `registry_task` is only its
declared identity, and the two are checked against each other at write
time.

## Writing one

`<draft_file>` is a plain JSON file whose top-level object has exactly the
`launch_order` field shape (`tables/rows.json` → `launch_order`) -- there is
no other accepted format, and no separate "draft" schema looser than the
real one.

```
python3 <plugin-root>/scripts/ledger.py launch-order --layer deploy --file <draft_file>
```

Re-running this on the same `run_id` idempotently rewrites the same file --
it never produces a second launch order for one run. The same action also
back-fills this run's `run_id` into the `affects` array of every decision
named in its `decision_refs`; `decision_refs` stays authoritative and
`affects` is only its materialized index -- `trace_check` verifies the two
agree.

**Delete the draft file once the write succeeds.** The canonical copy is
`ops/launch_orders/<run_id>.json` -- a leftover draft anywhere else in the
working tree is untracked-but-not-ignored, which makes the tree dirty, which
refuses the *next* launch and escalates it as a fault that never had
anything to do with that launch (the run-layer skill's
`references/execute.md` "dirty" definition). Don't work around this by
adding the draft's own path to `dirty_exempt_globs` -- delete it instead.

**`run_id`** is given by this layer, never invented by the run layer
(`tables/rows.json` → `launch_order.run_id`). Absent a project-specific
naming rule, the plugin's own default applies: `<name>-<YYYYMMDD>-<序>`,
`name` restricted to `[A-Za-z0-9_.]+` (the hyphens are reserved as segment
separators). This shape isn't arbitrary -- it's exactly what
`evidence_lint.py`'s own id-shape exemption already recognizes on sight
(the oversight skill's `references/report-genre.md`), so a report quoting
this `run_id` in prose never needs a `$ ` line just to name it.

**`decision_refs`** is required (non-null) whenever `quick=false`, but it is
legally an empty array. Cite a decision here only when an R5 fork was
actually raised and answered while producing *this* launch order
(`references/r5-choices.md`) -- a launch order that mechanically executes a
fully-specified ticket with no fork of its own cites nothing, and
`decision_refs: []` is the correct, non-suspicious value for it. Don't
invent a citation just to make the list look populated.

**`created_by`** is always `"deploy"` -- `launch-order` rejects any
`--layer` other than `deploy`, so this field records that origin, not a
session id or a user name.

**`expected_commit`** is the git HEAD this launch is pinned to. The fallback
rail compares it against `_lib.git_head(project_root)` with any `-dirty`
suffix stripped first; a mismatch refuses the launch exactly like a dirty
tree does (the run-layer skill's `references/execute.md`). On a project with
no git repo at all, `git_head()` reports the literal sentinel `"no-git"` --
that's the value to use here too, not a guess at a commit hash.

**`created_at`** is ISO-seconds, **naive local time** -- the same clock
`_lib.now_iso()` stamps every other ledger entry with, not UTC. A
`created_at` recorded in UTC on a project east of Greenwich reads as hours
in the future/past against that same clock, and `status`'s own
`launch-overdue` cross-check (created_at + `expected_runtime_s` ×
`runtime_factor`) will fire on launches that are not actually overdue.

**`batch_id` / `env_name` / `workdir` / `artifact_dir` / `smoke_cmd`** are
project-shaped, not plugin-shaped -- `batch_id` follows the pattern above
(`batch_report_header.batch_id_pattern`); `env_name` and `workdir` are
whatever this project calls its own environment and execution directory;
`artifact_dir` is where this run's outputs, logs, and `RUNMETA.json` land
(`expected_outputs`' globs and `output_check.py` resolve against it);
`smoke_cmd` is the optional pre-launch smoke command in §8 step 5's batch
sequence, null when there isn't one.

## Sourcing `expected_outputs`

`expected_outputs` must be non-empty (`tables/rows.json` →
`launch_order.expected_outputs`, `minItems: 1`, #157) -- a launch order
with none is rejected outright at write time, and `output_check.py` treats
an empty list the same as a hand-authored one written before that gate
existed. Each entry is `{path_glob, min_bytes, min_lines, required_keys[]}`.
Source them from what the registry task this order names actually writes --
read the task's own code or its own documented outputs, don't guess a
generic glob and move on; a glob that never matches anything real defeats
the whole point of the gate as surely as an empty list does. The run-layer
skill's `references/execute.md`, "After it lands" section, covers what
happens once these are checked; this section only covers where the values
themselves come from.

## Approval gate

If `spec_ref` is set, the write checks that spec's `approved_by` is
non-empty and its `approved_digest` still matches -- a stale approval
refuses the write and escalates rather than launching against a spec the
user hasn't actually signed off on in its current form. A `quick=true`
order with `spec_ref` empty is exempt from this gate entirely (§2.6, see
`references/quick-lane.md`).

## Handing off to run

The launch order itself is the handoff -- the run layer never gets
free-text instructions, only this file. Where it goes:

- `rails.gpu`'s value in config decides how: a skill name means route there
  for the launch; a command/script path means the run layer executes it
  directly, passing the launch order's path.
- After landing, check the artifact before trusting any number from it:
  ```
  python3 <plugin-root>/scripts/output_check.py --launch-order <path>
  ```
  A clean exit code with an empty artifact is not `ok` -- see the run-layer
  skill's `references/execute.md` for what actually runs this.

## The batch sequence (§8 step 5)

Launch order → smoke (`smoke_cmd`, if set) → criterion run
(`ledger.py runs-append`, see `references/criteria.md`) → R3 evidence
report → `evidence_lint` + `verify_report` clean → the user looks at it
themselves → only then does the batch launch for real, through `rails.gpu`.
Numbers only ever enter runs.jsonl through `metrics_cmd` (normal rows) or
`criterion_cmd` (criterion rows) -- never by reading a log and typing a
number in.
