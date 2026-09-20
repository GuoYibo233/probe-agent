# 10 A `sweep:` key is validated only to its first component, so a sweep can crash the loader or collapse its children onto one key

Status: needs-triage
Severity: important
File: experimental_settings/schema.py:678-693, experimental_settings/schema.py:654-656
Contract: 5.5 (the sweep keyword), 5.7 (the merge order and what the loader refuses), 3.2 rule 7 (sweep children each get their own path)
Errata: not recorded

## Finding

`_sweep_children` checks a swept field name in two ways and no more: the section is a
section of the schema, and the section's dataclass has a field with the name before the
second dot.

```python
    for dotted in sweep:
        _refuse_probe_under_inject(workflow, dotted)
        section, _, field_name = dotted.partition(".")
        if section not in SECTION_CLASSES:
            raise SchemaError(f"sweep.{dotted}: not a field of the schema")
        _field_type(SECTION_CLASSES[section], field_name.split(".")[0])
```

The child's values are then written straight into the merged dictionary:

```python
    for dotted, value in extra.items():
        _set_dotted(full, dotted, value)
        authored.add(dotted)
```

The command-line override path, ten lines below, validates the same kind of name
completely — the section must be one the workflow builds (`section not in full`) and the
whole dotted path must exist (`_get_dotted` inside `try: ... except KeyError`). The sweep
path has neither test, so two states pass it.

## Failure scenario

Both measured through `schema.load` with the shipped files copied to `/tmp`:

1. A section the workflow does not name. `baseline.yaml`'s workflow is `[sample, score]`;
   a setting there with `sweep: {train.lr: [1.0e-5, 3.0e-5]}` reaches
   `_set_dotted(full, "train.lr", ...)`, `full` holds no `train` key, and the loader
   raises a bare `KeyError: 'train'`. `run.py` catches `schema.SchemaError` only
   (`run.py:180`, `run.py:1730`), so the operator gets a traceback instead of the
   message 5.7 promises. The same typo as a command-line override is refused with
   `train.lr: not a field of the schema`.

2. A nested field that does not exist. `sweep: {train.predict.bogus: [1, 2, 3]}` on
   `train_probe/ctool_qwen3_0pt6b` loads cleanly and gives three children,
   `ctool_qwen3_0pt6b/train.predict.bogus=1` and its two siblings, whose train keys are
   all `d17a4e720c70` and whose run directory is the one
   `.../outputs/train/d17a4e720c70`. The value lands in a dictionary entry no dataclass
   field reads, so `_dict_to_dataclass` drops it and the three children differ in name
   only. `run.py train_probe 'ctool_qwen3_0pt6b'` then launches the first child, and each
   later child prints `has a live piece; launching nothing` — the sweep is silently one
   run. That is exactly the collapse 5.5's refusal of a sweep over a `debug.yaml` field
   exists to prevent, and it breaks 3.2 rule 7.

## Proposed fix

Validate a swept field where the merged dictionary exists, the way an override is
validated. In `_merge_one`, before `_set_dotted`, require that `section` is a key of
`full` and that `_get_dotted(full, dotted)` resolves, raising `SchemaError` naming the
field and the workflow when either fails — the same two refusals the override loop makes
four lines later, so one rule covers both paths. `_sweep_children` keeps the checks it
can make without the merged dictionary (the section exists, the field is a field,
`debug.yaml` does not set it).
