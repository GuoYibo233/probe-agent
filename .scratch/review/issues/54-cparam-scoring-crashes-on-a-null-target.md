# 54 cparam scoring concatenates a null target and dies with a TypeError

Status: needs-triage
Severity: minor
File: eval/utils/probe_eval.py:459
Contract: 1.3 (the prediction row's `target` is written by the method's `predict` hook; `data/probe_output.py` declares it nullable), 1.4 (cparam's `params_all_ok` "is what `match` returns for the two whole calls its caller rebuilt")
Errata: not recorded

## Finding

The cparam branch rebuilds both whole calls by string concatenation:

```python
        for row in joined.iter_rows(named=True):
            tool = row["tool"]
            tool_ok = row["fired_label"] == tool
            params_all_ok = match_cparam(
                tool + "(" + row["text_pred"], tool + "(" + row["target"], env)["params_all_ok"]
```
(`eval/utils/probe_eval.py:455-459`)

`row["target"]` is null on a prediction row whose `call` does not start with
`tool + "("`. That row is written on purpose, and its own hook says so:

```
    """One row per example row, no drop: ... Unlike batches/reference_loss, a row whose call does
    not start with tool + "(" still gets a prediction row -- its `target` is None (1.2's derivation
    rule only says such rows are dropped from training) -- so predictions.parquet keeps one row per
    input row ..."""
```
(`train/methods/cparam.py:366`, with `_derive_target` returning None at
`train/methods/cparam.py:40-44`)

`data/probe_output.py` declares the column nullable (`DEFAULTS` maps every
column to None, `data/probe_output.py:41`), and a per-row null passes
`read_frame` (errata "Part 1 (`read_frame` and a null column)"). Run through
this function, such a row raises `TypeError: can only concatenate str (not
"NoneType") to str` — measured here on a two-row frame with one null target.

The cgen branch of the same function hands the target to `match_cgen` whole and
gets a named refusal for a target it cannot use:

```python
    if t is None:
        raise ValueError(f"match_{method}: target {target!r} does not parse via env.split_args")
```
(`eval/utils/probe_eval.py:211-212`)

so the two generator paths disagree about what a broken target does.

## Failure scenario

An eval of a cparam run over a build whose example rows carry a `call` that
does not open with `tool + "("`. Today's builder cannot produce one —
`data/build_training_dataset.py:183` writes `call = env.build_call(tool,
call_args)` and AppWorld's `build_call` returns `f"{tool}({...})"`
(`data/environments/appworld.py:318`) — so the row is one environment file
away: a second benchmark whose `build_call` normalises the tool spelling
(strips a prefix, lowercases, rewrites an alias) writes exactly the row
`cparam.predict` documents. The eval then dies at the join with a TypeError
that names no row, no column and no file, at the end of a sample, build and
train chain that ran on cards.

## Proposed fix

State the requirement where the two whole calls are rebuilt: before the
concatenation, refuse a row whose `target` is null, naming the method and the
row's `example_id`, the way `_match_call` refuses a target it cannot parse at
`eval/utils/probe_eval.py:211-212`. A ground truth that cannot be rebuilt is a
defect in the prediction frame, and both generator paths then fail the same way
and name the row.
