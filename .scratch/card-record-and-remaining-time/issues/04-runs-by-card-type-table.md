# 04 the "Runs by card type" table in jobs/RESULTS.md

Status: ready-for-agent
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
