# Routine and on-demand inspection

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

## The reading exemption

Every other layer reads jsonl ledgers only through `ledger.py query`'s
default (active-rows) view. Oversight is the one exemption: it may read
any ledger sliced arbitrarily wide, in full, into context --
`query`'s `--batch` / `--run` / `--spec-item` / `--since` / `--metric`
dimensions plus `--all-rows` / `--include-archive` exist for exactly this.
An R3 report's full-scan claim rests on actually having read the full
scope, not a sample -- that's what this exemption is for.

`query` takes a required positional `LEDGER` naming which jsonl ledger to
read -- one of the `query-only`-read-class names in `tables/ledgers.json`
(`story`, `blocked`, `decisions`, `feedback`, `runs`), not a file path. A
full-scope read for one batch, everything included:

```
python3 <plugin-root>/scripts/ledger.py query runs --batch <batch_id> --all-rows --include-archive
python3 <plugin-root>/scripts/ledger.py query blocked --all-rows --include-archive
```

`--spec-item` filters `runs` by joining through the launch orders
directory (every order whose own `spec_ref` matches names a `run_id`) --
there's no `spec_item` column on a runs row itself.

Two ledgers this exemption's own dimensions don't reach, because `query`
refuses them outright and names the alternative: **`jobs`** (`read: sliced`
-- too large for a direct read; dispatch a reader subagent, model
`roles.reader_model`, one ledger at a time, and take back only its summary
plus the file's own path -- spec §2.1 "读手 subagent（辅）") and
**`launch_orders`** (`read: direct` -- a directory of small json files,
each one read straight off disk, no query layer needed:
`ls ops/launch_orders/*.json`, then read the ones this inspection's scope
actually names).

## Running an inspection

1. Run the three mechanical-check scripts against the material named in
   the dispatch (or the material the user pointed at, for an on-demand
   "查 X" / "深查这批" inspection):
   ```
   python3 <plugin-root>/scripts/trace_check.py --project-root <root>
   python3 <plugin-root>/scripts/evidence_lint.py <material>
   python3 <plugin-root>/scripts/verify_report.py <material>
   ```
2. **Read through the batch's ledgers and report in full** -- every batch,
   every time (config `inspection_policy=always`; the plugin ships no
   other value). Not a sample, not "spot-checked and it looked fine."
3. Write the report to `reports/<batch_id>.md` -- the routine close-out
   inspection's own naming convention, parallel to `plans/<batch_id>.md`
   for the batch report itself. Genre and mechanics: see
   `references/report-genre.md`.

## Who reads this report

Nobody downstream of this file reads it directly out of `reports/` --
consumption is mechanical: the deploy layer's own close-out step
(`references/closeout.md` in that skill) reads this report's `verdict`,
transcribes any blocker into a blocked entry, and on a clean verdict
back-fills this report's own path into the batch report's
`inspection_report` header field, which is what actually clears
`batches_pending_inspection` off `status`'s working face. Writing this file
alone doesn't close anything -- it's deploy's read-back that does.

## Verdict header

The report's header carries a `verdict` field --
`tables/rows.json` → `inspection_report_header` (field set and the
`verdict` enum are there, not restated here). A blocker only ever names a
**process or evidence defect**: a broken traceability chain, a missing
repro command, a mismatched basis between a claim and its evidence.
**Never a scientific conclusion** -- "this effect looks real" or "this
number seems off" doesn't belong in a blocker; that judgment is the user's
and the deploy/idea layers', not this report's.

## Two people, two jobs (§1)

The **`inspector` agent** (`agents/inspector.md`) does the read-only,
mechanical half: run the suite, read through, write the report, verdict
included. It writes only `reports/` and nothing else.

The **oversight session** dispatching it does the two things the agent
cannot: opening a blocked entry to ask a question as a participant, and
appending a suggestion to the feedback ledger. These two write slots
belong to the session, never to the agent -- don't fold them into the
agent's dispatch contract expecting it to use them.

## Cross-session memory

`reports/inspector-notes.md` is oversight's own scratch memory across
inspections -- clues worth carrying to next time. No other layer reads it
or depends on it; it exists purely so oversight doesn't start from zero
each time.
