# 40 A resume overwrites best/ with a worse checkpoint

Status: needs-triage
Severity: important
File: train/utils/trainer.py:282
Contract: 2.4 (the continue rule for train), 1.6 (the checkpoint layout)
Errata: not recorded (errata "2.6 (`validate`)" fixes the cadence and says "`best/` is chosen over those points"; nothing rules on what a resume does with the score it was chosen on)

## Finding

`run()` restores the optimizer and the scheduler on a resume and then starts the
best-objective tracking from scratch:

```python
        gstep = 0
        skip_target = 0
        if resume_step is not None:
            skip_target = resume_step
            opt_path = last_dir / "optimizer.pt"
            if opt_path.exists():
                saved = torch.load(opt_path, map_location="cpu")
                opt.load_state_dict(saved["opt"])
                sch.load_state_dict(saved["sch"])
            log(event="resume", gstep=skip_target, key=cfg._key)

        best = float("inf")
        best_metrics: dict = {"objective": best}
```
(`train/utils/trainer.py:271-283`)

`best` is the only guard on `best/`:

```python
            if metrics["objective"] < best:
                best = metrics["objective"]
                best_metrics = dict(metrics)
                probe.save(best_dir, labels=labels, extra=method.CHECKPOINT_META,
                           meta=_checkpoint_meta(cfg))
```
(`train/utils/trainer.py:309-313`)

Nothing on disk is consulted for the pre-crash best. `_save_last`'s meta carries
`step`, `epoch`, `commit` and `rng_state` only (`train/utils/trainer.py:366-369`),
`probe.save`'s meta for `best/` is `_checkpoint_meta(cfg)` — backbone, tuning,
max_len, train_key (`train/utils/trainer.py:128-130`) — and the resume branch
reads `ckpt_dir/meta.json` for `labels` alone (`train/utils/trainer.py:206-208`).

## Failure scenario

A `train_probe` setting with `train.epochs: 3` on a card. Epoch 0 validates at
objective 0.41, epoch 1 at 0.20, and `best/` holds epoch 1's checkpoint. The
piece is killed in epoch 2 (a node reboot, `run.py kill`, an OOM), after a
`last/` write at step 900. `run.py train_probe <setting>` relaunches: the
commit matches, so `resume_step = 900` and the run continues.

Epoch 2 overfits and validates at 0.35. Because `best` was reset to `inf`,
`0.35 < inf` holds and `probe.save(best_dir, ...)` replaces the 0.20 checkpoint
with the 0.35 one. `train_done.json` then records `"best_objective": 0.35`
(`train/utils/trainer.py:390-393`), the prediction step reloads `best_dir`
(`train/utils/trainer.py:395-397`), and `predictions.parquet`, `done.json`'s
`metrics` and every eval number below it come from the worse probe. The run
directory, the key and the commit are the ones the uninterrupted run would have
had, so nothing on disk says the checkpoint that was picked is not the best one
the run saw. The same run without the crash keeps the 0.20 checkpoint.

## Proposed fix

Restore the best objective on a resume, so the comparison at
`train/utils/trainer.py:309` is against the best score the run has actually
seen. `train_log.jsonl` already records every one of them — the resume path
opens it in append mode at `train/utils/trainer.py:231`, and each save writes
`log(event="save_best", ep=..., gstep=..., objective=best)` at
`train/utils/trainer.py:314`. In the `resume_step is not None` branch, read the
existing `train_log.jsonl` and set `best` (and `best_metrics`, from the matching
`event="eval"` line) to the lowest recorded `save_best` objective before the
step loop starts; a log with no `save_best` line means no checkpoint was ever
chosen and `inf` is then the right starting value.
