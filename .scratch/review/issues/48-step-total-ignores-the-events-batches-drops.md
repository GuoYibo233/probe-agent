# 48 The step total, and with it the LR schedule, counts events the method drops

Status: needs-triage
Severity: minor
File: train/utils/trainer.py:238
Contract: 2.6 (`batches` is the method's own packing and drop rule), 5.2 (`train.max_len`: a longer event is dropped whole)
Errata: touched by "5.2 (`train.max_len`) ... applied in each method's `batches` over the longest text of the event" and by "0.2 (`train/utils/trainer.py` third-party imports) ... the LR schedule is a `torch.optim.lr_scheduler.LambdaLR`"; neither rules on where the schedule's total comes from

## Finding

The trainer derives the step total from the raw event count of the training
split:

```python
        n_train_events = train_df["event_id"].n_unique()
        m_per_epoch = max(math.ceil(n_train_events / cfg.train.events_per_mb), 1)
        steps_per_epoch = max(math.ceil(m_per_epoch / cfg.train.accum), 1)
        full_steps = steps_per_epoch * cfg.train.epochs
        steps = min(full_steps, cfg.train.max_steps) if cfg.train.max_steps is not None else full_steps
```
(`train/utils/trainer.py:238-242`)

`steps` is the schedule's horizon:

```python
        warmup_steps = int(steps * cfg.train.warmup_ratio)
        sch = torch.optim.lr_scheduler.LambdaLR(
            opt, lr_lambda=lambda s: _lr_lambda(s, warmup_steps, steps))
```
(`train/utils/trainer.py:267-269`, `_lr_lambda` decaying to 0.0 at `total_steps`
at `train/utils/trainer.py:63-69`)

`batches()` yields fewer minibatches than that count implies, because every
method drops whole events: an event whose longest text tokenizes past
`cfg.train.max_len` (`train/methods/ctool.py:61-63`,
`train/methods/cgen.py:61-63`, `train/methods/cparam.py:76-78`), and for the two
generators an event all of whose rows were dropped for an over-long target or a
target that does not assemble (`train/methods/cgen.py:74-81`,
`train/methods/cparam.py:81-100`). The trainer knows this — the docstring of
`_batches_with_flags` says the minibatch count computed ahead of time "is wrong
by however many events a method's `batches()` drops"
(`train/utils/trainer.py:145-150`) — and reads the epoch's end off the
lookahead instead, but `steps` is still the raw count.

## Failure scenario

A `train_probe` setting at the schema defaults: `generation.max_step_tokens` is
8192 (`experimental_settings/schema.py:53`) and `train.max_len` is 8192
(`experimental_settings/schema.py:107`), so an event whose reasoning ran long
gives its terminal cut a probe text of the whole thinking plus the task and the
history and the event is dropped whole. Say the split loses one event in ten.
`steps` is then about 11% above the steps the loop takes, the loop ends by
running out of batches rather than at `gstep >= steps`, and
`_lr_lambda(last_step, warmup_steps, steps)` returns about 0.11 instead of 0.0:
the run's last optimizer steps are taken at a tenth of the peak learning rate
where a completed linear decay would take them at zero, which moves the final
weights, `best/` and every number below it. Nothing reports the difference —
`train_log.jsonl`'s `lr` field records the schedule that ran, not the one the
setting asked for — and a `train.max_len: 2048` sweep child widens the gap
without changing anything else in the setting. The same count is the heartbeat's
`total` (`train/utils/trainer.py:264`, `:297`), so `done` never reaches it and
the `ls` line's progress and ETA are short by the same share for the whole run.

## Proposed fix

Count the events the run will actually train on. `_dropped_overlong_events`
(`train/utils/trainer.py:110-118`) already applies the whole-event `max_len`
rule the three methods share, and the trainer already calls it at
`train/utils/trainer.py:431`; call it once before
`train/utils/trainer.py:238` and set `n_train_events` to the distinct event
count of the training split minus that drop, so the schedule's horizon and the
beat total describe the events that reach `loss`. The generators' further
per-row drops stay outside this count, and the same `_batches_with_flags`
lookahead keeps ending the epoch correctly, so a residual gap changes no
behaviour beyond the schedule's last steps.
