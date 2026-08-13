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

```
python3 <plugin-root>/scripts/ledger.py launch-order --layer deploy --file <draft_file>
```

Re-running this on the same `run_id` idempotently rewrites the same file --
it never produces a second launch order for one run. The same action also
back-fills this run's `run_id` into the `affects` array of every decision
named in its `decision_refs`; `decision_refs` stays authoritative and
`affects` is only its materialized index -- `trace_check` verifies the two
agree.

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
