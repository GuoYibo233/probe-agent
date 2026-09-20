# 15 `run.py ls` hashes and re-loads every row in the ledger, including the rows its own workflow and debug filters drop

Status: needs-triage
Severity: minor
File: run.py:650-662
Contract: 8.6 (`ls [workflow]`: one line per run, the five flags `run.py` computes and passes in)
Errata: the entry "8.6 (`ls` and the host probe)" already narrows `ls`'s other cost — `live_sessions()` is called only when the ledger is non-empty — and stops there.

## Finding

`cmd_ls` reads every folded row, computes the five flags and the progress pair for all of
them, and only then hands them to `registry.ls`, which applies the display filters:

```python
    rows = registry.find({})
    row_flags = _compute_row_flags(rows)
    progress = _compute_progress(rows)
    result = registry.ls(
        workflow_name, debug=debug, progress=progress, ...)
```

`registry.ls` drops the rows of other workflows and, unless `--debug` is given, every
debug row (`jobs/registry.py:1023-1026`). The work `run.py` did for those rows is thrown
away. Two of the three readings are expensive per row: `_inputs_changed` sha1s every
path in the run's `consumed.json` and every split file in its `meta.json`
(`run.py:432-442`, `run.py:510-511`), and `_compute_progress` opens the environment and
stats one record file per requested (task, seed) pair (`run.py:518-565`).

## Failure scenario

A finished `build` run's `consumed.json` names one entry per record file it read — 315
task records for the p1-scale collection, each a flush-per-row jsonl of megabytes (2.5:
"`build` writes `consumed.json`: every record file it read, with its sha1"). After that
build, `run.py ls inject` — a command about a different workflow that prints no build
line at all — still reads and sha1s all of them, plus every `sample` directory's records
for the progress pair. The gpu-run skill's monitoring loop calls `ls` every half hour, so
the cost is paid over and over for lines nobody asked for, and a debug walk's rows are
folded in too while `ls` without `--debug` hides them.

## Proposed fix

Filter before computing. In `cmd_ls`, keep the rows `registry.ls` will return — those
whose `workflow` equals `workflow_name` when one is given, and, when `--debug` is absent,
those whose `debug` is false — and pass only those to `_compute_row_flags` and
`_compute_progress`. The two filters are one line each and are already spelled in
`registry.ls`; the orphan-session rows `registry.ls` adds carry no `run_id` and take no
flag from these maps, so they are unaffected.
