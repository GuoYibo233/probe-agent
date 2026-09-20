# 20 The probe service never checks that its score checkpoint is a classifier

Status: needs-triage
Severity: important
File: models/probe_models/service.py:104-109
Contract: 7.2 (the `/gen` row: the service "refuses to start" on a checkpoint that cannot serve its side, "naming the checkpoint"), 6.2 (`base.load`)
Errata: not recorded

## Finding

`serve()` refuses a wrong checkpoint on the generator side and takes the score
side on trust:

```python
 94         gen_meta = json.loads((gen_dir / "meta.json").read_text())
 95         if gen_meta.get("param_only"):
 96             raise SystemExit(
 97                 f"models.probe_models.service: {gen_dir} is an argument-only checkpoint "
 98                 "(param_only: true) and cannot serve /gen; refusing before any card is taken"
 99             )
...
104         score_dir = Path(args.score_ckpt) / "best"
105         score_meta = json.loads((score_dir / "meta.json").read_text())
106         max_len = score_meta["max_len"]
107         score_train_key = score_meta["train_key"]
108
109         score_probe = base.load(None, None, probe_kind="classifier", ckpt_dir=score_dir, device=device)
```

A generator checkpoint's `best/meta.json` carries `"labels": null`
(`train/methods/cgen.py:35-36` returns None, `train/utils/trainer.py:210-212`
passes it down, `models/probe_models/base.py:93` writes it), and both fields
read at lines 106-107 are present on a generator checkpoint, so the file looks
healthy right up to the load. `base.load` then reaches

```python
242         head_n_labels = n_labels if ckpt_dir is None else len(labels)
```

with `labels is None`.

Upstream, `experimental_settings/schema.py:1000-1008` runs the
whole-call-generator check on `inject.probe_gen` alone and `inject.probe_score`
is resolved at `:994` with no kind test (this is ticket 11's finding, seen from
the loader). `run.py:1897-1911` compares a pinned reference's stated `method:`
against the referenced **train** run's frozen `probe.method` — a consistency
test between two statements, not a test of the kind.

## Failure scenario

Ticket 11 covers the name form, which dies earlier at `run.py:1954`
(`KeyError: 'temperature'`). The pinned `key:` form of errata "5.4 / 2.1"
reaches the card. The operator pins both references by hand — the shape the
acceptance `--debug` walks use (errata entry 81), where the hex keys are pasted
out of `run.py where`:

```yaml
inject:
  probe_score: {key: {train: <the cgen train key, pasted by mistake>,
                      eval:  <the ctool eval key>}, method: ctool}
  probe_gen:   {key: {train: <the cgen train key>, eval: <the cgen eval key>}, method: cgen}
```

`run.py:1908-1911` refuses with "stated method 'ctool', the referenced train
run's frozen probe.method is 'cgen'", which invites the wrong repair: change the
statement to `method: cgen` rather than the key. With that word changed every
gate passes —

- `_check_inject_probe_methods`: stated `cgen` equals the train run's `cgen`;
- `_resolve_inject_temperature` (`run.py:1951-1954`) reads
  `probe_score.eval`, which is still the **ctool** eval run, so
  `fields["temperature"]` is there;
- `_check_inject_shared_build_key`: both train runs came from one build;
- `_check_inject_code_currency`: one build, one backbone, versions current;
- `{probe_score_method}` fills with `cgen` and folds
  `eval/utils/probe_eval.py#MATCH_VERSION.cgen`.

`jobs/launch.py:1037` then passes that generator train run as `--score-ckpt`,
claims one card for the probe service piece (`:1034`) and starts it. The piece
dies at `models/probe_models/base.py:242` with `TypeError: object of type
'NoneType' has no len()` — no checkpoint path, no mention of `probe_score`. The
launch ends `launch_failed` at the service alive check, and the operator reads a
bare `TypeError` in `log/<piece>.txt` after the cards were taken.

## Proposed fix

In `serve()`, beside the `param_only` refusal and before any `base.load`, state
the requirement the score side has: the score checkpoint carries a class order.
`Probe.save` writes `labels` as a list for a classifier and null for a
generator, so that field is the marker:

```python
score_labels = score_meta.get("labels")
if not (isinstance(score_labels, list) and score_labels):
    raise SystemExit(
        f"models.probe_models.service: {score_dir} carries no class order "
        "(meta.json labels is not a non-empty list) and is not a classifier "
        "checkpoint, so it cannot serve /score; refusing before the probe is loaded"
    )
```

placed between the `score_meta` read and the `base.load` at line 109, so the two
checkpoint flags get the same kind of refusal and both name the directory they
refuse. Ticket 11's loader check is the other half and does not replace this
one: it tests the setting's stated method, and this tests the checkpoint that is
actually on the card — the same division 7.2 already draws for `param_only`.
