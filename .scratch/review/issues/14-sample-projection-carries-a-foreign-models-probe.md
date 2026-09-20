# 14 `freeze` writes the whole `models` section into a `sample` run, so a shared sample directory asserts the last walker's probe backbone

Status: needs-triage
Severity: minor
File: experimental_settings/schema.py:1438-1448, experimental_settings/schema.py:1454-1460
Contract: 3.4 ("`settings.yaml` is a stage projection, not the whole setting" — "only what *this* stage reads at run time: the sections the stage table names (2.1)"), 2.1 (the `sample` row's sections read are `data`, `models.agent`, `generation`, `sample.{...}`)
Errata: not recorded

## Finding

The projection is computed at section granularity: every entry of the stage table's
`sections` and `projection` tuples is cut at the first dot.

```python
def _projection_sections(stage: str, setting: Setting) -> set[str]:
    entry = STAGES[stage]
    sections = {t.split(".", 1)[0] for t in entry["sections"]}
```

`STAGES["sample"]["sections"]` names `models.agent`, so the set holds `models`, and
`freeze` writes the section whole:

```python
    for sec in sections:
        obj = getattr(setting, sec, None)
        if obj is not None:
            doc[sec] = _dataclass_to_dict(obj)
```

A `sample` run's `settings.yaml` therefore carries `models.probe` and `models.probe_row`
as well, neither of which is in the sample key (`fields_of("sample", ...)` walks the same
tuple field by field and keeps `models.agent` alone).

## Failure scenario

Measured: `train_probe/ctool_qwen3_0pt6b` and the same setting with
`models.probe=qwen3_1pt7b` give the same sample key, `a7d8b62ee953`, and the same build
key — correct, since neither stage reads the probe. Walking the second one re-freezes
that shared directory (3.4: freeze runs at every launch) and writes
`models: {probe: qwen3_1pt7b, probe_row: {family: qwen, weights: qwen3-1.7b-base, ...}}`
over the first's `qwen3_0pt6b`. `settings_diff.yaml` is identical both times, so the
collision check passes and nothing is reported. The directory's own record of what it is
then contradicts the run that produced it, which is the failure 3.4 names in so many
words ("a whole-setting file would make a shared `sample` directory assert one owner's
`probe.method` and `train.lr` while another owner contradicts them"). It is today's
record only — the one reader of `models.probe_row` is `train/utils/trainer.py`, on a
`train` run where the field is keyed — so nothing computes a wrong number from it.

## Proposed fix

Project the fields the stage table names, not their sections, whenever a `sections` or
`projection` entry carries a dot: write `models.agent` together with its expanded
`models.agent_row` for `sample` and `inject`, and `models.probe` with `models.probe_row`
for `train` — the role's alias and the row 5.2 says the key is computed over, which is
what `models/agent_models/service.py` and `train/utils/trainer.py` read back. A bare
section entry (`data`, `build`, `train`, `eval`, `inject`, `score`) keeps meaning the
whole section, which is what every other row spells. `models` is the only section any
row names field by field today, so the change is visible on `sample` and `inject` alone.
