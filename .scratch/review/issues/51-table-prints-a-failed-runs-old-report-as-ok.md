# 51 The table prints a failed run's leftover report and calls it OK

Status: needs-triage
Severity: important
File: eval/method_table.py:99
Contract: 8.6 (`run.py table`), errata "Part 8.6 (`run.py table`): ... one table row per `(backbone, method, risk target)` ... the cell is `mean ± sample standard deviation` over the group's runs"
Errata: not recorded

## Finding

`table` decides whether a group's numbers are current from the presence of a
file and from nothing else:

```python
        reports = []
        for row in members:
            report_path = Path(row["dir"]) / "probe_report.json"
            reports.append(probe_eval.read_report(Path(row["dir"]))[0] if report_path.exists() else None)

        n_ready = sum(1 for r in reports if r is not None)
        m = len(members)
        status = "OK" if n_ready == m else f"PENDING {n_ready}/{m}"
```
(`eval/method_table.py:96-103`)

`members` are folded registry rows, and each one carries its own verdict:
`registry._ls_row` puts the newest finish row's `status` — `ok`, `failed`,
`launch_failed`, `killed`, or the start row's `launching` while no finish row
follows it — on the row it returns (`jobs/registry.py:934-959`). `table` never
reads that field.

`eval` always recomputes inside its key (2.4, `run.py`'s `ALWAYS_RECOMPUTE`),
and `write_report` is the last-but-one thing `probe_eval.run` does
(`eval/utils/probe_eval.py:686`), so a recomputation that dies leaves the
previous computation's `probe_report.json` in the directory untouched.

## Failure scenario

1. `run.py train_probe ctool_qwen3_0pt6b` walks to `eval`; the stage finishes,
   writes `probe_report.json` and gets a finish row with `status: "ok"`.
2. The train run is retried and re-predicts, so `predictions.parquet` changes.
   `run.py retry train_probe ctool_qwen3_0pt6b eval` starts the eval again and
   the process exits non-zero — a target value outside `labels`
   (`eval/utils/probe_eval.py:332-334`), a missing `val` split
   (`:337-339`), any raise at all. `run.py` appends a finish row with
   `status: "failed"` (`run.py:2105-2110`) and the directory keeps step 1's
   report.
3. `run.py table train_probe` finds one member, finds `probe_report.json`,
   counts `n_ready == m` and prints the group's cells from step 1's numbers
   with `status` = `OK`.

The printed numbers belong to a prediction file that no longer exists, and the
column a reader consults to find that out says the opposite. The same holds
while a recomputation is in flight: the newest registry row reads `launching`
and the table still reads `OK`.

## Proposed fix

Decide readiness on both facts the row already carries: a member is ready when
its registry row's `status` is `ok` **and** its directory holds a
`probe_report.json`. Count those for `n_ready`, and read a report only for
them, so a member whose newest launch failed or is still running is counted
into `PENDING n/m` and its leftover numbers stay out of the mean. Apply this
together with the fix of ticket 56, which is what keeps a group whose only
member is not ready visible as a row at all.
