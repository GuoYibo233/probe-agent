# 11 The loader accepts an `inject.probe_score` (and an `eval.theta_from`) that names a generator, and the walk dies on `KeyError: 'temperature'`

Status: needs-triage
Severity: important
File: experimental_settings/schema.py:994-1008
Contract: 5.2 (`probe_score` = "the setting whose ctool probe decides when to fire"; `theta_from` = "the classifier setting whose frozen theta selects the fired rows"), 5.4 (the resolved temperature), 1.4 (one report shape per `PROBE_KIND`), 5.7 (the refusals)
Errata: not recorded. The errata entry "5.4 / 2.1 (`{probe_score_method}` ...)" gives the pinned form a `method:` sibling and has `run.py` compare it with the referenced train run, but neither side checks the method's kind.

## Finding

`_finalize` resolves the two inject references in turn and checks the kind of one of
them:

```python
    _resolve_if_set("inject.probe_score")

    _resolve_if_set("inject.probe_gen")
    if "inject.probe_gen" in refs:
        gen_method = refs["inject.probe_gen"][2]
        ...
        whole_call_generator = gen_kind == "generator" and checkpoint_meta.get("param_only") is False
        if whole_call_generator is False:
            raise SchemaError(...)
```

`inject.probe_score` gets no matching check, although `_resolve_ref` has already put its
method in `refs["inject.probe_score"][2]` and `_method_kind` is one call away.
`eval.theta_from` (resolved at line 971) is in the same position: its name form resolves
to a Setting whose `probe.method` is readable, and nothing tests it.

## Failure scenario

Copy `inject.yaml`'s `probe_p1_e1_theta_0pt80` with one word changed —
`probe_score: train_probe/cgen_qwen3_0pt6b` instead of `ctool_qwen3_0pt6b`, the obvious
typo since `probe_gen` names `cgen` on the next line. Measured: the setting loads, the
inject key is `fcadd019ca8f`, `_upstream["probe_score.eval"]` is `a89e9dd67003` (the cgen
eval) and the key folds `eval/utils/probe_eval.py#MATCH_VERSION.cgen`. The walk then
passes `_refuse_missing_upstream`, `_check_inject_probe_methods` (which compares the
stated method against the train run, not against the kind) and
`_check_inject_shared_build_key`, and reaches `run.py:1951`:

```python
    fields, _fires = probe_eval.read_report(upstream_dirs["probe_score.eval"])
    return {"probe_temperature": fields["temperature"]}
```

`temperature` is a field of the classifier report only (`eval/utils/probe_eval.py:410-416`
against the generator block at `:521-526`), so the walk ends in
`KeyError: 'temperature'` with no field named, after every gate has passed. The same
hole on `eval.theta_from` sends a generator eval into
`eval/utils/probe_eval.py:637` with `ref[1]` (`fires`) `None`, because a generator eval
writes no `fires.parquet`.

## Proposed fix

Check the kind of both references at load, beside the `probe_gen` check they already sit
next to. After `_resolve_if_set("inject.probe_score")`, when the reference carries a
method (every name form, and the pinned form through its required `method:` sibling),
require `_method_kind(method) == "classifier"` and raise `SchemaError` naming the field,
the method and its kind otherwise. Do the same for `eval.theta_from`'s name form, whose
method the loader reads off the named setting. `schema.py` already holds `_method_kind`
and uses it for the generator branch three lines above.
