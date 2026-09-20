# 31 `hb.finish()` sits in a `finally`, so a loop piece that dies mid-walk writes `status: "done"` and `ls` calls it done

Status: needs-triage
Severity: important
File: agent/run_tasks.py:204
Contract: 8.4 ("one beat per unit of work, then `finish()`, which writes the final beat with `status: \"done\"`"; "a claiming piece's `done` verdict comes from its final beat's `status`"), 8.5 (`judge`: `done` when `status == done`, else `dead` when the piece is gone)
Errata: not recorded

## Finding

The whole walk is wrapped in a `try` whose `finally` closes the heartbeat:

```python
    hb = registry.beat(run_dir, i)
    hb.emit(0, len(triples), "task")
    done = 0
    try:
        for split, task_id, seed in triples:
            writer = open_record(run_dir, task_id, seed)
            ...
            done += 1
            hb.emit(done, len(triples), "task", tok_in=tokens_in, tok_out=tokens_out)
    finally:
        hb.finish()
```

`Heartbeat.finish` writes `status: "done"` unconditionally
(`jobs/registry.py:317-319`), and `registry.judge` tests that status first, ahead
of the liveness test:

```python
    if piece.get("status") == "done" or (done is not None and total and done >= total):
        return "done", False
    if piece.get("alive") is False:
        return "dead", True
```

For a claiming piece this status is the *only* done signal there is: 8.4 makes
`done >= total` deliberately unreachable for one loop piece, because `total` is
the whole requested count. So the `finally` hands the failure path the one word
that means success.

The four other stages call `hb.finish()` on the success path only, after
`registry.write_done` (`data/build_training_dataset.py:370`,
`train/utils/trainer.py:439`, `eval/utils/probe_eval.py:718`,
`eval/score_run.py:261`). `agent/run_tasks.py` is the one file that puts it in a
`finally`.

## Failure scenario

A `sample` run, six loop pieces, piece 3 on a records directory whose NFS
write-back fails at close:

1. Task 40's `writer.row("final", ...)` (line 173) lands.
2. `writer.close()` (line 179) raises `OSError` — NFS reports a deferred write
   error at close.
3. The per-task guard at line 180 catches it, `meta_written` is true, so it goes
   straight to `writer.row("final", ...)` at line 184, which writes into the
   file object `close()` already closed and raises
   `ValueError: I/O operation on closed file`.
4. That `ValueError` escapes the guard and the `for` loop.
5. `finally: hb.finish()` appends
   `{"done": 40, "total": 450, "unit": "task", "status": "done"}`.
6. The piece dies with a traceback; its tmux session ends.

`run.py ls` then prints `3:done` for a piece that collected 40 of the tasks it
was walking and died, and `job-monitor` reports the piece finished. The same
holds for any exception raised outside the per-task guard — `open_record`'s
`mkdir`/`os.open` (line 125) and `hb.emit` (line 203) are the two other
statements in the `for` body that are not inside it.

`registry.launch_failed` needs every verdict to be `dead`, so a run whose loop
pieces all died this way never gets its `launch_failed` finish row either.

## Proposed fix

Root cause: the final beat says "this piece finished its walk" and is written
where "this piece stopped, for any reason" is true. In `agent/run_tasks.py`,
call `hb.finish()` once, after the `for` loop completes, on the path that
reached the end of the rotation — the shape the other four stage programs
already have — and leave the failure path with its last progress beat, which is
what lets `judge` reach `dead`.

If the heartbeat file must still be closed on the failure path, close it without
a status beat; the status word and the file handle are two different
obligations, and only the first one is a claim about the work.
