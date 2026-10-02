# 04 the "Runs by card type" table in jobs/RESULTS.md

Status: resolved
Blocked by: 01
Spec: .scratch/card-record-and-remaining-time/spec.md (section "The lookup view")

## What to do

`registry.render()` (`jobs/registry.py:493-519`) writes a second table after the existing
one, headed `## Runs by card type`, from the finish rows that carry a `card_record`:

- one row per (task identity, card model); debug and full-size runs are separate rows,
  because `debug` is part of the identity;
- columns: stage, task (the identity fields as `k=v`), card model and memory, runs `ok`,
  runs failed for memory, the largest peak memory (train and probe service) or weights +
  KV cache and the maximum concurrency (agent service), the median speed with its unit, the
  newest run key;
- a row with a memory failure adds the run key and the quoted `failure_line` of its newest
  memory failure;
- newest row first.

The README section 2 line of `jobs/RESULTS.md` names the second table.

## Acceptance

- A CPU-only unit test renders from fixture rows (two card models, one memory failure, one
  debug run) and checks the grouping and the failure quote.
- `run.py selfcheck` green; all CPU test modules pass.

## Comments

- 2026-10-02, wave 2 (ticket-run): DONE after one fix round. Branch ticket/2026-10-02-wave2/T04 (f37f098..781f2ae), merged at c8feb71 (README `jobs/registry.py` entry and tests/ line, and the test docstring, merged as the union with tickets 01 to 03). Selfcheck green, all eight test modules pass. Rendered from the real `jobs/runs.jsonl` after the merge: one row, train ctool 0.6B full debug on an RTX A6000 47 GiB, peak 43.64 GiB, `train-3e562de5abb9`.
  - Minors for the final review: F2, the probe-service and cross-card-model paths have no test; N1, `_card_type_lines` looks up `starts[run_id]` for every record, so a finish row with a card record and no start row above it (only possible from a row not written by `append_finish`) makes `render()` raise inside every later append.
  - Implementer's choices, kept: a record with a null task is grouped under its stage with task `-`; the agent-service memory cell shows the load with the largest weights + KV cache and that load's concurrency; a run counts under every card model its pieces held, a memory failure only under the failing piece's card model; the column headers are the implementer's words.
