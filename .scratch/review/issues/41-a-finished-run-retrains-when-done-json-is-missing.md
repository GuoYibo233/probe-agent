# 41 A run whose predictions are already written retrains instead of closing

Status: needs-triage
Severity: important
File: train/utils/trainer.py:180
Contract: 2.4 (the continue rule for train), 2.3 (train's done marker)
Errata: not recorded

## Finding

The continue rule reads the three markers in this order:

```python
    predict_only = False
    resume_step = None
    ckpt_dir = None
    if train_done_path.exists() and not predictions_path.exists():
        predict_only = True
        ckpt_dir = best_dir
    elif last_dir.exists():
        last_meta = json.loads((last_dir / "meta.json").read_text())
        if last_meta.get("commit") == cfg._commit:
            resume_step = last_meta.get("step")
            ckpt_dir = last_dir
        else:
            raise SystemExit(...)
    elif train_log_path.exists():
        raise SystemExit(
            f"{train_log_path}: already exists, this run directory has already been trained "
            "once and its train_log.jsonl would mix two runs; run.py retry to start fresh")
```
(`train/utils/trainer.py:177-195`)

The first branch requires `predictions.parquet` to be **absent**. The state in
which `train_done.json` and `predictions.parquet` both exist and `done.json`
does not therefore falls through to `elif last_dir.exists()` and is read as a
mid-training crash. That state is reachable: `probe_output.write` renames
`predictions.parquet` into place at `train/utils/trainer.py:429`, and
`registry.write_done` — the only writer of a train run's `done.json`
(contracts 2.3) — is called at `train/utils/trainer.py:433`, with
`_dropped_overlong_events` in between (`train/utils/trainer.py:431`), which
re-tokenizes the longest text of every event of the training split
(`train/utils/trainer.py:110-118`).

## Failure scenario

A `train_probe` setting finishes its step loop, writes `train_done.json`, runs
the prediction step, and `predictions.parquet` lands. The piece is then killed
inside `_dropped_overlong_events` — one tokenizer pass over every training
event, minutes on a real split — or between that call and the `done.json`
rename: a node reboot, a `run.py kill`, an NFS error inside `write_done`.

`run.py train_probe <setting>` next sees no `done.json`, so it relaunches the
train stage. The trainer takes the `elif last_dir.exists()` branch, resumes from
`last/`'s step — the last periodic checkpoint, `train.checkpoint_hours` before
the end — and retrains the tail of the run, up to two hours of card time that is
already on disk. It then overwrites `best/` (ticket 40), rewrites
`train_done.json` with a new `best_objective` and recomputes
`predictions.parquet`, so the finished run's numbers are replaced by a second
training's.

When `last/` does not exist — a run shorter than `train.checkpoint_hours`, which
is every `--debug` smoke — the same state falls to `elif train_log_path.exists()`
and the trainer exits with "already trained once ... run.py retry to start
fresh", which throws away a completed training and its predictions and asks for
the whole run again.

## Proposed fix

Make the marker test say what is true: `train_done.json` means the step loop
finished, and `predictions.parquet` beside it means the prediction step finished
too, so only `done.json` is owed. In `train/utils/trainer.py:177-195`, split the
first test in two — when `train_done.json` exists and `predictions.parquet`
exists, skip both the step loop and the prediction loop, read
`best_objective` back out of `train_done.json` for the metrics, and go straight
to `registry.write_done` and `hb.finish()`; when `train_done.json` exists and
`predictions.parquet` does not, keep today's predict-only path. `last/` and
`train_log.jsonl` are then consulted only when `train_done.json` is absent,
which is the state they describe.
