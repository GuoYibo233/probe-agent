# 43 The build's beats reach done == total before the build does any of its work

Status: needs-triage
Severity: minor
File: data/build_training_dataset.py:98
Contract: 8.4 (a piece emits a beat per unit of its main loop), 8.5 (the verdicts)
Errata: touched by "Part 8.4 (`build`'s heartbeat unit): `unit` for `build` is `row`, while the countable unit before the example frame exists is the record file -> `build` emits one beat per record read, with `done` and `total` counted in records" — the entry requires one beat per record read; it does not license emitting all of them at once

## Finding

The builder opens its heartbeat, emits a zero beat, reads every record in one
call, and then runs an empty loop whose only body is a beat:

```python
    # 2.5: build reads only the records of the pairs in its own key.
    df = trajectory_record.read_dir(sample_dir, pairs)
    for i in range(len(pairs)):
        hb.emit(i + 1, len(pairs), "row")
```
(`data/build_training_dataset.py:96-99`, after `hb.emit(0, len(pairs), "row")`
at `data/build_training_dataset.py:55`)

`i` indexes nothing: `read_dir` has already returned. After this loop the last
beat reads `done == total == len(pairs)`, and the next beat of the stage is
`hb.finish()` at `data/build_training_dataset.py:370`. Everything between —
the abort gate, the per-record walk that parses every action, calls
`env.build_call`, runs the round-trip gate, enumerates the cuts and assembles
every example text (`data/build_training_dataset.py:101-250`), the cap, the
parquet write, `consumed.json` and `report.md` — emits no beat.

`jobs/registry.judge` reads the last beat first:

```python
    done, total = piece.get("done"), piece.get("total")
    if piece.get("status") == "done" or (done is not None and total and done >= total):
        return "done", False
```
(`jobs/registry.py:698-700`)

## Failure scenario

A build over a real sample run: `read_dir` returns in seconds and the example
walk is the minutes. From the moment the loop at
`data/build_training_dataset.py:98` finishes, `run.py ls` prints the build
piece as `done` while the process is still assembling example rows, and
`registry.judge` can no longer return `suspected stall` for it, because the
`done` test short-circuits every stall rule below it. A build that hangs — an
`env.split_args` walk over a pathological action, an NFS read that never
returns — reads as finished for as long as it hangs, and the operator watching
`run.py ls` has no signal at all. The progress display is wrong the other way
too: the whole stage shows `len(pairs)/len(pairs) row` from its first minute,
so the rate and the ETA `registry.rates` computes off these beats describe the
record read and not the work.

## Proposed fix

Beat where the work is. Move the per-record beat into the loop that consumes
the records, `for task_id, seed in pairs:` at
`data/build_training_dataset.py:124`, emitting `hb.emit(i + 1, len(pairs),
"row")` after each record's events have become example rows, and delete the
empty loop at `data/build_training_dataset.py:97-99`. `done` then advances with
the records actually built and reaches `total` on the last one, which is the
errata's "one beat per record" read over the stage's own main loop.
