# 16 `schema.upstream_of` is a second name for `schema.upstream` with no caller

Status: needs-triage
Severity: minor
File: experimental_settings/schema.py:1322-1324
Contract: 5.1 (what the file holds: the dataclasses, the axis literals, the stage table, and the loader — `load`, `load_frozen`, `freeze`, `diff`, `key`, `run_dir`, `run_dir_of`), README section 1 ("no near-duplicate files and no framework", "every file does one thing its name says")
Errata: the entry "5.1: none of the loader's named functions hands `run.py` the resolved upstream map" adds exactly one name for this, `upstream(stage, setting)`, and no second one.

## Finding

```python
def upstream_of(stage: str, setting: Setting) -> dict:
    """name -> key, per the stage table's upstream cell; the same map as upstream()."""
    return upstream(stage, setting)
```

Its own docstring says it is the same map. A search over the tree's code
(`constants/`, `experimental_settings/`, `data/`, `models/`, `agent/`, `train/`,
`eval/`, `jobs/`, `run.py`, `tests/`) finds the name in `schema.py` alone: every caller —
`run.py:2059`, `jobs/launch.py`, the four stage-side readers — uses `upstream` or reads
`_upstream` off the frozen setting. The errata entry that created the function named
`upstream`; `upstream_of` came from ticket 04's own name list, and that ticket's report
records the two as the same function.

## Failure scenario

Nothing computes a wrong number from it; the cost is the one the tree's first principle
names. The next builder who needs the upstream map finds two public names for it in the
file the whole repo imports, has to read both bodies to learn they are the same, and may
call the one that no test, no acceptance and no stage exercises. The same fork already
cost a review round once: the function exists because ticket 04 listed both spellings,
and no reader since has been able to tell which one the tree means.

## Proposed fix

Delete `upstream_of` and the `upstream_of` mention in the section comment at
`schema.py:1095`, leaving `upstream(stage, setting)`, the name the errata pins and every
caller uses. Nothing in the tree imports the deleted name, so no other file changes and
no key moves.
