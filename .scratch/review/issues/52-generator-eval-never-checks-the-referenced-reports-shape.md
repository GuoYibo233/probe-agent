# 52 A generator eval accepts a generator report as its theta source

Status: needs-triage
Severity: minor
File: eval/utils/probe_eval.py:487
Contract: 1.4 (`probe_kind`: "`classifier` or `generator`: which of the two shapes this file is"; the generator shape "carries exact-match numbers at a theta taken from a named **classifier** report"), 2.5 (the gates `probe_eval.run` holds on the referenced eval)
Errata: not recorded

## Finding

`run` holds three gates on the referenced eval run and none on its shape:

```python
        ref_key = cfg._upstream["theta_from.eval"]
        ref_eval_dir = schema.referenced_run_dir("eval", ref_key)
        if ref_eval_dir is not None and (ref_eval_dir / "done.json").exists():
            ref = read_report(ref_eval_dir)
```
(`eval/utils/probe_eval.py:635-638`, then the `risk_targets` gate at `:643-646`
and the build-key gate at `:660-665`)

`report_generator` then reads the classifier block of that report without
asking what shape it is:

```python
        theta = ref_fields["chosen"][risk_str]
```
(`eval/utils/probe_eval.py:487`)

```python
        fires_risk = ref_fires.filter((pl.col("risk") == risk) & (pl.col("split") == "test"))
```
(`eval/utils/probe_eval.py:498`)

A generator report carries neither: its fields are `risk_targets`,
`theta_used`, `exact` and `n_events` (`:521-526`), and it returns None for the
frame, so its directory holds no `fires.parquet` (1.4, "written only by the
classifier shape").

The loader does not close this either. It resolves `eval.theta_from` and checks
only that a generator method has one (`experimental_settings/schema.py:971-977`),
and `run.py`'s pre-launch test asks the referenced directory for a `done.json`
and nothing more (`run.py:1893-1894`).

## Failure scenario

`train_probe.yaml` holds `ctool_qwen3_0pt6b`, `cgen_qwen3_0pt6b` and
`cparam_qwen3_0pt6b` side by side, and the last two both write `eval.theta_from:
train_probe/ctool_qwen3_0pt6b` (errata "5.2 (`train_probe.yaml`'s named
settings)"). Write `cgen_qwen3_0pt6b` there instead of `ctool_qwen3_0pt6b` in
the cparam setting:

- the loader resolves the reference and never reads the referenced setting's
  kind;
- both referenced runs descend from the same build, so the build-key gate at
  `:660-665` passes;
- a generator report carries `risk_targets`, so the gate at `:643-646` passes;
- `report_generator` raises `KeyError: 'chosen'` with no file name, no key name
  and no mention of the reference — after the whole sample, build and train
  chain has run on cards.

With `eval.risk` empty the loop body never runs and the failure moves one step
later, to `run`'s `consumed.json` block, where `_sha1(ref_eval_dir /
"fires.parquet")` raises `FileNotFoundError` for a file a generator never
writes:

```python
        ref_fires_height = ref[1].height if ref[1] is not None else 0
        consumed.append({
            "path": str(ref_eval_dir / "fires.parquet"),
            "sha1": _sha1(ref_eval_dir / "fires.parquet"),
```
(`eval/utils/probe_eval.py:700-703` — the `ref[1] is not None` guard one line
above records that the frame is optional; the `_sha1` call below it assumes it
is not)

## Proposed fix

Put the shape gate beside the three gates that are already there. In `run`,
directly after `ref = read_report(ref_eval_dir)`, refuse when
`ref[0]["probe_kind"]` is anything but `"classifier"`, naming the referenced
directory, the key and the kind the report carries — the identity block records
the shape for exactly this question (1.4) — and in the same place require the
frame, refusing when `ref[1]` is None and naming the missing `fires.parquet`.
`report_generator` and the `consumed.json` block then both read a reference
whose shape is already established, and the `ref[1] is not None` guard at
`:700` becomes a plain `.height`.
