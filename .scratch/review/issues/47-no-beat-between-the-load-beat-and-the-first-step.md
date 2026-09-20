# 47 No beat between the model-loaded beat and the first optimizer step

Status: needs-triage
Severity: minor
File: train/utils/trainer.py:264
Contract: 8.4 (a long phase must not cross the stall line), 8.5 (the verdicts)
Errata: not recorded (the wave-7 entry "(e) 8.4 / ticket 13" covers the opposite end, the prediction step's beats; the walks' entry records that a piece whose beats stop reads as stalled)

## Finding

The trainer emits one beat when the model is loaded and then nothing until a
step is logged:

```python
        hb.emit(0, steps, "step")   # the model has finished loading (8.4)
```
(`train/utils/trainer.py:264`)

The next beat comes from `_log_step`, which runs after an optimizer step and
only on the cadence:

```python
                    if gstep == 1 or gstep % LOG_EVERY == 0 or gstep >= steps:
                        _log_step(ep)
```
(`train/utils/trainer.py:360-361`, `_log_step` at `train/utils/trainer.py:292-300`)

Two windows sit between them and neither emits anything.

1. `method.batches(train_df, probe.tokenizer, _epoch_cfg(cfg, ep))` at
   `train/utils/trainer.py:324` yields its first block only after
   `_build_events` has walked the whole training split, making one tokenizer
   call per example row plus one per event (`train/methods/ctool.py:57-73`,
   `train/methods/cgen.py:57-86`, `train/methods/cparam.py:72-105`).
2. On a resume, the fast-forward at `train/utils/trainer.py:329-337` runs that
   pass once per already-completed epoch and builds every physical block —
   `_make_batch`'s `[B, 1, L_pad, L_pad]` float32 mask and its `L x L` boolean
   intermediates — purely to recount `gstep`, with the `continue` at
   `train/utils/trainer.py:337` skipping every beat below it.

One block of that construction costs 0.24 s and 277 MB at the schema's
`train.max_len: 8192` (measured on this machine with
`external/probe-env/bin/python`, one 64-cut event of packed length 8315,
`_chunk_by_budget` giving one event per block at the training budget
`2 * max_len`).

`jobs/registry.judge` reads the gap from the last beat
(`jobs/registry.py:703-708`); with one beat in the launch's file
`stall_line_s` falls back to `DEFAULTS["warmup_s"]`, 1800 s
(`jobs/registry.py:671-675`, `:40`).

## Failure scenario

A `train_probe` run resumes after a kill in its third epoch. The fast-forward
re-tokenizes the training split twice and rebuilds every block of two epochs at
0.24 s a block, so the run is past 1800 s before its first real step. From
`run.py ls` the piece then reads `suspected stall`, and past three times the
line `suspected stall(escalated)`, while it is doing exactly what the resume
asks. `.claude/agents/job-monitor.md`'s autopsy branch tests that escalation
and reports a stalled train job; the operator's remedy for a stall is a kill,
which throws away the fast-forward and starts the same 30 minutes again on the
next resume. The first window has the same shape on a fresh run over a large
split: every beat before the first optimizer step is missing, so a slow
tokenization pass is indistinguishable from a hang.

## Proposed fix

Beat inside both windows, with the totals the phase already has. In the
fast-forward branch at `train/utils/trainer.py:329-337`, emit
`hb.emit(gstep, steps, "step")` every `LOG_EVERY` steps as `gstep` advances, so
a resume shows its progress towards `resume_step` instead of silence; and emit
one beat immediately after `method.batches(...)` yields its first block —
`_batches_with_flags` already holds that lookahead at
`train/utils/trainer.py:145-156` — so the tokenization pass is bounded by a
beat on both sides, the shape `train/utils/trainer.py:372-375` already uses
around validation.
