# 44 The logged step loss is divided by the number of physical blocks

Status: needs-triage
Severity: minor
File: train/utils/trainer.py:342
Contract: 8.4 (the beat carries `loss`), 2.6 (`loss` returns the unnormalised weighted sum)
Errata: touched by "6.2 (`Batch`): only four keys are read outside the method -> two more, `mb` (int) and `mb_weight` (float), are required and read by `train/utils/trainer.py`, so the trainer reproduces legacy's per-logical-minibatch normalisation" — the entry pins the normalisation of the gradient, not of the logged number

## Finding

Each method's `loss` hook returns the unnormalised weighted sum over the rows of
**one physical block** (errata "2.6 (`loss`, `reference_loss`)"), and
`mb_weight` is the weight of the **whole logical minibatch** the block belongs
to — `w_total` is summed over every row of every event in the minibatch before
the block split (`train/methods/ctool.py:198-203`, `train/methods/cgen.py:212-217`,
`train/methods/cparam.py:235-240`). The gradient path divides by both
`mb_weight` and `accum`, so the blocks of one minibatch add up to one weighted
mean:

```python
                (loss / batch["mb_weight"] / cfg.train.accum).backward()
                window_loss_sum += float(loss.detach()) / float(batch["mb_weight"])
                window_loss_n += 1
```
(`train/utils/trainer.py:341-343`)

The logged number does not. `window_loss_n` counts physical blocks, and the
window is averaged over that count:

```python
            loss_val = window_loss_sum / max(window_loss_n, 1)
            log(event="step", ep=ep, gstep=gstep, loss=loss_val, lr=sch.get_last_lr()[0])
            hb.emit(gstep, steps, "step", loss=loss_val)
```
(`train/utils/trainer.py:295-297`)

A minibatch that `_chunk_by_budget` splits into k blocks contributes k terms
that each carry a k-th of the minibatch's weighted mean, so `loss_val` is the
true per-minibatch weighted mean divided by k.

## Failure scenario

A `ctool` setting at the schema defaults: `train.events_per_mb: 4`,
`train.max_len: 8192`, so a physical block's budget is
`_TRAIN_BLOCK_MULT * max_len = 16384` tokens
(`train/methods/ctool.py:32,190`). Four events whose packed length is near
8192 tokens do not fit one block, so `_chunk_by_budget` yields two or three
blocks for that minibatch and one block for a minibatch of short events. The
`loss` field of `train_log.jsonl` and of the heartbeat then reads half or a
third of the real weighted-mean loss for some steps and the full value for
others, with the factor set by the token lengths of the events the shuffle
happened to group. A person reading the loss curve — or `run.py ls`, which
prints the beat's `loss` — sees steps and jumps that come from the packing, and
two runs of the same setting with a different `train.seed` report losses on
different scales.

## Proposed fix

Count the window in logical minibatches, which is the unit the sum is already
normalised to. In `train/utils/trainer.py:341-347`, increment `window_loss_n`
only when `is_mb_end` is true — the same flag the accumulation already uses —
so each minibatch contributes exactly one to the denominator while every block
keeps contributing its share to `window_loss_sum`.
