# 56 A group whose runs have written no report vanishes from the table

Status: needs-triage
Severity: minor
File: eval/method_table.py:106
Contract: 8.6 (`run.py table`), errata "Part 8.6 (`run.py table`): ... one table row per `(backbone, method, risk target)`, every risk in the report"
Errata: not recorded

## Finding

Every table row is emitted inside a loop over the risk targets the group's
reports name:

```python
        risks: list[float] = []
        for fields in reports:
            if fields is not None:
                for risk in fields["risk_targets"]:
                    if risk not in risks:
                        risks.append(risk)

        for risk in risks:
```
(`eval/method_table.py:105-112`)

When every member's report is missing, `reports` holds only None, `risks` stays
empty, the loop body never runs and the group appends nothing to `table_rows`.
The `status` value computed one block above it —

```python
        status = "OK" if n_ready == m else f"PENDING {n_ready}/{m}"
```
(`eval/method_table.py:103`)

— is then discarded with the group. `PENDING 0/m` is a string this function can
never print: it reaches the output only through a row that a report produced.

## Failure scenario

`run.py train_probe cgen_qwen3_0pt6b` walks `sample`, `build` and `train` and
launches `eval`. While that eval runs, `run.py table train_probe` prints a
table with no line for `cgen_qwen3_0pt6b` — byte for byte the table it prints
for a setting nobody ever launched. A reader cannot tell a run in flight, or a
run whose launch failed before the report existed, from a setting that was
never started, and the column added to answer that question is silent in
exactly the case it was added for.

The same silence covers a group all of whose members failed: with the fix of
ticket 51 in place (a member counts as ready only when its registry row reads
`ok`), a group whose newest launch failed would have no readable report and
would disappear from the table altogether, which is why the two tickets belong
together.

## Proposed fix

Emit one row per group whatever its reports hold. When the group's `risks` list
is empty, append a single row carrying `backbone`, `method`, `runs` and
`status`, with `-` in the `risk` cell and in every metric cell — `_fmt` and
`_fmt_n` already render `-` for an empty value list
(`eval/method_table.py:46-65`), so the row is built by the same code path with
empty lists. A group then always has a line, and `status` says whether its
numbers are there.
