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
3. Write the report to `reports/`. Genre and mechanics: see
   `references/report-genre.md`.

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
