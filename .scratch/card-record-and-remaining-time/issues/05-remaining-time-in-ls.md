# 05 remaining time in run.py ls

Status: resolved
Blocked by: 02
Spec: .scratch/card-record-and-remaining-time/spec.md (section "Remaining time")

## What to do

`_format_ls_row` (`run.py:805`, the progress and rate at `:823-825`) adds
`left=<h>h<mm>` after the rate for a run without a finish row: `(total - done) /
recent_rate`. A `train` run whose newest beats carry the unit `prediction split` (ticket 02)
prints `left=<h>h<mm> (prediction)`; during training, `left=<h>h<mm> (training)`, which
does not include the prediction phase. No rate, or a finished run: `left=-`.

`run.py --help`'s `ls` line and the README section 2 line of `run.py` mention the field.

## Acceptance

- A CPU-only unit test of the formatting: a sample run at 300/1575 tasks and 0.03 tasks/s
  prints `left=11h48`; no rate prints `left=-`.
- `run.py selfcheck` green; all CPU test modules pass.

## Comments

- 2026-10-02, wave 3 (ticket-run): DONE after one fix round. Branch ticket/2026-10-02-wave3/T05 (ae70b18..ab0f602), merged at 79e2052 (README `jobs/registry.py` entry and tests/ line, and the test docstring, merged as the union with tickets 01 to 04). Selfcheck green, all eight test modules pass. The live `run.py ls` after the merge prints the `left` column (header and rows).
  - The fix round reads a piece's rates over its counting beats in the newest beat's unit, so a train piece's prediction phase has a rate of its own (and the `slowed` verdict compares within that phase).
  - For gyb: `notes/plans/2026-09-17-contracts.md` (the `rates(first_beat, recent_beats)` row) still says the average is over the whole run; it is now over the current phase.
  - Implementer's notes: an open run is recognised by `status == "launching"`; a zero recent rate prints `left=-`; for the first few prediction beats the recent rate is usually `None`.
