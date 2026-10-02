# 05 remaining time in run.py ls

Status: ready-for-agent
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
