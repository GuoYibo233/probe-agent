# 46 counts.dropped_overlong counts the train split, not the rows that lost a prediction

Status: needs-triage
Severity: minor
File: train/utils/trainer.py:431
Contract: 1.5 (`done.json`'s `counts`), 1.3 (one prediction row per example row of every split in `train.predict.splits`)
Errata: touched by "5.2 (`train.max_len`): 'tokens per event; a longer event is dropped whole' -> applied in each method's `batches` over the longest text of the event; **those rows get no prediction row** and the count is `done.json`'s `counts.dropped_overlong`" — the entry ties the count to the rows that lose a prediction row

## Finding

The trainer computes the count over the training split alone:

```python
    dropped_overlong = _dropped_overlong_events(train_df, probe.tokenizer, cfg.train.max_len)

    registry.write_done(
        run_dir, stage="train", key=cfg._key, commit=cfg._commit,
        counts={"train_rows": train_df.height, "val_rows": val_df.height,
                "predictions": pred_df.height, "dropped_overlong": dropped_overlong},
```
(`train/utils/trainer.py:431-436`, with `train_df = df.filter(pl.col("split") == "train")`
at `train/utils/trainer.py:227`)

The prediction step runs over `cfg.train.predict.splits`, `["val", "test"]` by
default (`train/utils/trainer.py:410-419`, `experimental_settings/schema.py:96`),
and `ctool.predict` reaches those rows through the same packed path, which
applies the same whole-event drop:

```python
def _score_frame(probe, df, tok, cfg, block_mult: int) -> list[dict]:
    events, _dropped = _build_events(df, tok, cfg.train.max_len)
```
(`train/methods/ctool.py:254-256`, called by `predict` at
`train/methods/ctool.py:293`; `_build_events` drops at
`train/methods/ctool.py:61-63`)

So the events the errata's sentence is about — the val and test events that get
no prediction row — are counted nowhere, and the number that carries their name
counts training events instead. `_build_events`'s own `dropped` return value is
discarded at every call site (`train/methods/ctool.py:189`, `:256`;
`train/methods/cgen.py:203`, `:298`; `train/methods/cparam.py:226`, `:324`).

## Failure scenario

A `ctool` setting on gpt-oss trajectories: `generation.max_step_tokens` is 8192
(`experimental_settings/schema.py:53`) and `train.max_len` is 8192
(`experimental_settings/schema.py:107`), so a step whose reasoning runs long
gives its terminal cut a probe text of the whole thinking plus the task and the
history, and the event's longest row tokenizes past `max_len`. Every such event
is dropped whole, in the training split and in the val and test splits alike.

`done.json` then records, say, `"predictions": 41,000` against a val plus test
example count of 44,000, and `"dropped_overlong": <a training-split number>`
that explains none of the 3,000 missing rows. `eval/utils/probe_eval.py`
computes coverage and `n_events` over the prediction frame it is handed, so the
dropped events leave both the numerator and the denominator and the reported
coverage is over the events that fit, with no line anywhere saying how many did
not. A `train.max_len: 2048` sweep child widens the same silence.

## Proposed fix

Count the drop over the frames the run actually consumed. In
`train/utils/trainer.py:431`, call `_dropped_overlong_events` once per split the
run touched — the train split and each split of `cfg.train.predict.splits` — and
write the counts under their own names (`dropped_overlong_train`,
`dropped_overlong_<split>`), so `counts.predictions` plus the prediction splits'
drops reconstructs the example-row count `1.3` promises. The rule is already one
function in one place and stays method-independent.
