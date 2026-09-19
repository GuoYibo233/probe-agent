"""The training loop every probe method shares: settings to arguments, seed, backbone, tuning, checkpoints, metrics, heartbeat, resume, the alignment gate, and the prediction step."""
# venv: probe
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from pathlib import Path

import polars as pl
import torch

from experimental_settings import schema
import models
from models.probe_models import base
from data import training_data, probe_output
from jobs import registry

# VERSION rule: read this before you edit this file (errata "3.3 / 8.6", gyb 2026-09-18).
# Bump VERSION only when some existing setting would now produce a different output of a stage
# that lists this file in the stage table of experimental_settings/schema.py. A new feature
# behind a new setting field whose default reproduces the old behaviour, a message, a comment
# or a report layout does not bump.
# Every bump adds one VERSION_HISTORY entry: {<new version>: {"why": "<one sentence>",
# "stale": (<stage names>)}}. "stale" names the stages (sample, build, train, eval, inject,
# score) whose existing outputs can no longer be used; leave "stale" out and every stage is
# stale. The key folds the highest version that made a stage stale, so a bump that leaves a
# stage usable keeps that stage's run directory. When unsure, list the stage.
VERSION = 2
VERSION_HISTORY = {
    2: {"why": "The training, validation and prediction forwards run under bfloat16 autocast on a "
               "card, the form the float32 model row was written for (errata 6.1); version 1 ran "
               "them in float32 and the two generator methods ran out of memory on a 48 GB card.",
        "stale": ("train",)},
}

# The learning-rate schedule, stated here because a reader looks for it: train.warmup_ratio
# defaults to 0.05 in experimental_settings/schema.py, the share of steps the previous pipeline
# hardcoded, so a setting that says nothing warms over the first 5% of its steps and a setting
# that wants no warmup writes warmup_ratio: 0.0 explicitly.

LOG_EVERY = 50   # a step line and a heartbeat beat land every this many optimizer steps; a module constant, changes no number


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, obj) -> None:
    path = Path(path)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    tmp.replace(path)


def _lr_lambda(step: int, warmup_steps: int, total_steps: int) -> float:
    """Linear rise to 1.0 over warmup_steps, then linear decay to 0.0 by total_steps -- the shape of transformers.get_linear_schedule_with_warmup."""
    if step < warmup_steps:
        return step / max(warmup_steps, 1)
    if total_steps <= warmup_steps:
        return 0.0
    return max(0.0, (total_steps - step) / max(total_steps - warmup_steps, 1))


def _bf16_forward(probe):
    """The autocast every training, validation and prediction forward runs under: float32 weights, bfloat16 compute on a card, plain float32 on the cpu. `.backward()` stays outside it, and the alignment gate never enters it, so that gate compares the two losses in float32."""
    on_card = next(probe.backbone.parameters()).device.type == "cuda"
    return torch.autocast("cuda", dtype=torch.bfloat16, enabled=on_card)


def _dropped_overlong_events(df: pl.DataFrame, tok, max_len: int) -> int:
    """The count of events whose longest row's text tokenizes past max_len -- the same rule every method's batches() drops whole events on, computed once here for done.json's counts."""
    dropped = 0
    for _event_id, group in df.group_by("event_id"):
        longest = max(group["text"].to_list(), key=len)
        ids = tok(longest, add_special_tokens=False, truncation=False)["input_ids"]
        if len(ids) > max_len:
            dropped += 1
    return dropped


def _rng_state_hex() -> dict:
    cuda_hex = None
    if torch.cuda.is_available():
        cuda_hex = torch.cuda.get_rng_state().numpy().tobytes().hex()
    return {"torch": torch.get_rng_state().numpy().tobytes().hex(), "cuda": cuda_hex}


def _checkpoint_meta(cfg) -> dict:
    return {"backbone": cfg.models.probe, "tuning": cfg.probe.tuning,
            "max_len": cfg.train.max_len, "train_key": cfg._key}


def _epoch_cfg(cfg, epoch: int):
    """A shallow copy of cfg whose train.seed is cfg.train.seed + epoch, for the one call to
    method.batches() this epoch makes -- every other reader of cfg (validate, the alignment gate,
    logging, checkpoint meta) keeps the original, unshifted object. copy.copy works uniformly on
    the real schema.Setting dataclass and on a test fixture's types.SimpleNamespace alike."""
    epoch_train = copy.copy(cfg.train)
    epoch_train.seed = cfg.train.seed + epoch
    epoch_cfg = copy.copy(cfg)
    epoch_cfg.train = epoch_train
    return epoch_cfg


def _batches_with_flags(batch_iter):
    """Pair each batch with the two facts one-item lookahead gives: whether it is the last physical
    block of its own logical minibatch, and whether it is the last block the iterator yields, which
    is the end of the epoch. Both are read off the lookahead rather than from a minibatch count
    computed ahead of time from the split's raw event count, which is wrong by however many events
    a method's batches() drops (overlong events, unassembled targets, ...)."""
    prev = next(batch_iter, None)
    while prev is not None:
        nxt = next(batch_iter, None)
        is_mb_end = nxt is None or nxt["mb"] != prev["mb"]
        yield prev, is_mb_end, nxt is None
        prev = nxt


def run(run_dir: Path, method) -> None:
    """Drive one train run: load the frozen setting, resume or start fresh per the continue rule, run the alignment gate and the step loop, checkpoint, predict, mark done. `method` is the caller's own module (a train/methods/<m>.py); this function never branches on which one it is."""
    run_dir = Path(run_dir)
    cfg = schema.load_frozen(run_dir)
    hb = registry.beat(run_dir, 0)

    done_path = run_dir / "done.json"
    train_done_path = run_dir / "train_done.json"
    predictions_path = run_dir / "predictions.parquet"
    last_dir = run_dir / "last"
    best_dir = run_dir / "best"
    train_log_path = run_dir / "train_log.jsonl"

    if done_path.exists():
        return

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
            raise SystemExit(
                f"{last_dir}: recorded commit {last_meta.get('commit')!r} differs from this "
                f"run's commit {cfg._commit!r}; run.py retry to start fresh")
    elif train_log_path.exists():
        raise SystemExit(
            f"{train_log_path}: already exists, this run directory has already been trained "
            "once and its train_log.jsonl would mix two runs; run.py retry to start fresh")

    torch.manual_seed(cfg.train.seed)

    build_dir = schema.run_dir_of("build", cfg._upstream["build"], debug=cfg._debug)
    examples_path = build_dir / "examples.parquet"
    df = training_data.read(examples_path)
    _atomic_write_json(run_dir / "consumed.json", [{
        "path": str(examples_path), "sha1": _sha1(examples_path), "n_rows": df.height,
    }])

    if resume_step is not None or predict_only:
        ckpt_meta = json.loads((ckpt_dir / "meta.json").read_text())
        labels = ckpt_meta.get("labels")
    else:
        labels = method.head_labels(df, cfg)

    n_labels = len(labels) if labels else None
    weights_path = models.probe(cfg.models.probe).weights_path  # resolved for the start log line only
    # base.load's own pinned signature (ticket 06: "load(row, cfg, *, probe_kind, n_labels=None,
    # labels=None, ckpt_dir=None, device='cpu') -> Probe") carries device as a real keyword,
    # defaulting to "cpu"; contracts 2.6 and 6.2 echo the signature without it, an abbreviation of
    # the same interface, not a disagreement with ticket 06. The train launch line carries no
    # --device flag (unlike the probe service's launch line, which does) and no cfg field carries
    # one, so this loop is the only place that can supply it. jobs/launch.py scopes the process to
    # one physical GPU through CUDA_VISIBLE_DEVICES, so torch.cuda.is_available() alone tells this
    # process whether that GPU is there; leaving device out would pin the backbone to base.load's
    # "cpu" default and the run would never touch the GPU it was launched on.
    device = "cuda" if torch.cuda.is_available() else "cpu"
    probe = base.load(cfg.models.probe_row, cfg, probe_kind=method.PROBE_KIND,
                       n_labels=n_labels, labels=labels, ckpt_dir=ckpt_dir, device=device)

    train_df = df.filter(pl.col("split") == "train")
    val_df = df.filter(pl.col("split") == "val")

    if not predict_only:
        logf = open(train_log_path, "a")

        def log(**kw) -> None:
            kw["ts"] = time.clock_gettime(time.CLOCK_REALTIME)
            logf.write(json.dumps(kw, ensure_ascii=False) + "\n")
            logf.flush()

        n_train_events = train_df["event_id"].n_unique()
        m_per_epoch = max(math.ceil(n_train_events / cfg.train.events_per_mb), 1)
        steps_per_epoch = max(math.ceil(m_per_epoch / cfg.train.accum), 1)
        full_steps = steps_per_epoch * cfg.train.epochs
        steps = min(full_steps, cfg.train.max_steps) if cfg.train.max_steps is not None else full_steps

        if resume_step is None:
            log(event="start", key=cfg._key, commit=cfg._commit, method=cfg.probe.method,
                weights_path=weights_path, n_train_events=n_train_events,
                n_train_rows=train_df.height, n_val_rows=val_df.height, steps=steps,
                epochs=cfg.train.epochs, max_len=cfg.train.max_len,
                events_per_mb=cfg.train.events_per_mb, accum=cfg.train.accum,
                lr=cfg.train.lr, seed=cfg.train.seed)

        if cfg.train.align_check and resume_step is None:
            _run_alignment_gate(run_dir, probe, method, train_df, cfg)

        # base.load hands the probe back in eval mode (transformers' from_pretrained ends with
        # model.eval()), and training mode is what dropout and transformers' activation
        # checkpointing both read, so this loop turns it on for every path that trains -- a setting
        # with align_check: false and every resume reach the step loop without passing through the
        # alignment gate, which runs in eval mode by design.
        probe.set_training(True)
        if cfg.train.grad_ckpt:
            probe.grad_checkpointing(True)

        hb.emit(0, steps, "step")   # the model has finished loading (8.4)

        opt = torch.optim.AdamW(probe.trainable_parameters(), lr=cfg.train.lr, weight_decay=0.01)
        warmup_steps = int(steps * cfg.train.warmup_ratio)
        sch = torch.optim.lr_scheduler.LambdaLR(
            opt, lr_lambda=lambda s: _lr_lambda(s, warmup_steps, steps))

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
        last_checkpoint_t = time.monotonic()
        seen_mbs: set = set()
        window_loss_sum = 0.0
        window_loss_n = 0
        last_logged_step = 0
        last_epoch_validated = -1
        last_epoch_seen = 0

        def _log_step(ep: int) -> None:
            """One step line and one loss-carrying beat, over the losses seen since the last one."""
            nonlocal window_loss_sum, window_loss_n, last_logged_step
            loss_val = window_loss_sum / max(window_loss_n, 1)
            log(event="step", ep=ep, gstep=gstep, loss=loss_val, lr=sch.get_last_lr()[0])
            hb.emit(gstep, steps, "step", loss=loss_val)
            window_loss_sum = 0.0
            window_loss_n = 0
            last_logged_step = gstep

        def _validate_and_maybe_save(ep: int) -> None:
            nonlocal best, best_metrics, last_epoch_validated
            probe.set_training(False)
            with _bf16_forward(probe):
                metrics = method.validate(probe, val_df, probe.tokenizer, cfg)
            probe.set_training(True)
            log(event="eval", ep=ep, gstep=gstep, **metrics)
            if metrics["objective"] < best:
                best = metrics["objective"]
                best_metrics = dict(metrics)
                probe.save(best_dir, labels=labels, extra=method.CHECKPOINT_META,
                           meta=_checkpoint_meta(cfg))
                log(event="save_best", ep=ep, gstep=gstep, objective=best)
            last_epoch_validated = ep

        for ep in range(cfg.train.epochs):
            if gstep >= steps:
                break
            # method.batches is called fresh once per epoch: its own signature (2.6) and this
            # ticket's own acceptance fixture (A3.3) carry no epoch, so the per-epoch shuffle
            # (construction-plan prose: random.Random(cfg.train.seed + epoch)) is threaded in by
            # handing this one call a per-epoch cfg copy instead of an argument batches() reads.
            batch_iter = method.batches(train_df, probe.tokenizer, _epoch_cfg(cfg, ep))
            for batch, is_mb_end, is_epoch_end in _batches_with_flags(batch_iter):
                mb = batch["mb"]
                last_epoch_seen = ep

                if gstep < skip_target:
                    # fast-forward past steps a crashed incarnation already completed, without
                    # recomputing gradients for them
                    if is_mb_end:
                        seen_mbs.add(mb)
                    if len(seen_mbs) >= cfg.train.accum or is_epoch_end:
                        gstep += 1
                        seen_mbs = set()
                    continue

                with _bf16_forward(probe):
                    loss = method.loss(probe, batch)
                (loss / batch["mb_weight"] / cfg.train.accum).backward()
                window_loss_sum += float(loss.detach()) / float(batch["mb_weight"])
                window_loss_n += 1
                # a logical minibatch counts towards the accumulation once its last physical block
                # has its gradient in, so the step never fires with part of a minibatch missing
                if is_mb_end:
                    seen_mbs.add(mb)

                if len(seen_mbs) >= cfg.train.accum or is_epoch_end:
                    torch.nn.utils.clip_grad_norm_(probe.trainable_parameters(), 1.0)
                    opt.step()
                    sch.step()
                    opt.zero_grad()
                    gstep += 1
                    seen_mbs = set()

                    # the first step and the last one always leave a line, so a short run -- a
                    # --debug smoke stops at train.max_steps = 20, below LOG_EVERY -- still shows
                    # its loss in train_log.jsonl and in the heartbeat
                    if gstep == 1 or gstep % LOG_EVERY == 0 or gstep >= steps:
                        _log_step(ep)

                    now = time.monotonic()
                    if now - last_checkpoint_t >= cfg.train.checkpoint_hours * 3600:
                        hb.emit(gstep, steps, "step")
                        probe.save(last_dir, labels=labels, extra=method.CHECKPOINT_META,
                                   meta={**_checkpoint_meta(cfg), "step": gstep, "epoch": ep,
                                         "commit": cfg._commit, "rng_state": _rng_state_hex()})
                        torch.save({"opt": opt.state_dict(), "sch": sch.state_dict()},
                                   last_dir / "optimizer.pt")
                        last_checkpoint_t = now

                    if is_epoch_end:
                        hb.emit(gstep, steps, "step")   # a long validation must not cross the stall line (8.4)
                        _validate_and_maybe_save(ep)
                        hb.emit(gstep, steps, "step")

                    if gstep >= steps:
                        break

        if gstep > last_logged_step and window_loss_n > 0:
            _log_step(last_epoch_seen)   # the run ended on a step no cadence had logged

        if last_epoch_validated != last_epoch_seen:
            hb.emit(gstep, steps, "step")
            _validate_and_maybe_save(last_epoch_seen)
            hb.emit(gstep, steps, "step")

        logf.close()

        (run_dir / "train_done.json").write_text(json.dumps({
            "key": cfg._key, "commit": cfg._commit, "steps": gstep,
            "best_objective": best, "finished_at": time.clock_gettime(time.CLOCK_REALTIME),
        }, ensure_ascii=False))

        probe = base.load(cfg.models.probe_row, cfg, probe_kind=method.PROBE_KIND,
                           n_labels=n_labels, labels=labels, ckpt_dir=best_dir,
                           device=device)  # device: see the first base.load call above
        train_val_metrics = best_metrics
    else:
        train_done = json.loads(train_done_path.read_text())
        train_val_metrics = {"objective": train_done["best_objective"]}

    probe.set_training(False)
    # The prediction pass is the longest phase of a generator run, and 8.4 asks every piece for an
    # emit(0, total, unit) before its main loop: the predict-only path of 2.4 skips the step loop
    # entirely, so without this beat it writes nothing until finish() and registry.judge reads it
    # as a suspected stall. `total` counts the splits plus the one frame their rows are written
    # into, so the last beat of this loop reads done < total and only finish() makes the piece
    # done (8.5's first rule); the unit stays 8.4's word for the train stage.
    predict_splits = list(cfg.train.predict.splits)
    predict_total = len(predict_splits) + 1
    hb.emit(0, predict_total, "step")
    pred_rows: list[dict] = []
    for i, split in enumerate(predict_splits):
        split_df = df.filter(pl.col("split") == split).sort("example_id")
        if cfg.train.predict.cap is not None:
            split_df = split_df.head(cfg.train.predict.cap)
        with _bf16_forward(probe):
            pred_rows.extend(method.predict(probe, split_df, probe.tokenizer, cfg))
        hb.emit(i + 1, predict_total, "step")

    if pred_rows:
        pred_df = pl.DataFrame(pred_rows, strict=False)
        pred_df = pred_df.join(
            df.select(["example_id", "event_id", "task_id", "depth", "split", "tool"]),
            on="example_id", how="left")
    else:
        pred_df = df.select(["example_id", "event_id", "task_id", "depth", "split", "tool"]).head(0)
    probe_output.write(run_dir / "predictions.parquet", pred_df)

    dropped_overlong = _dropped_overlong_events(train_df, probe.tokenizer, cfg.train.max_len)

    registry.write_done(
        run_dir, stage="train", key=cfg._key, commit=cfg._commit,
        counts={"train_rows": train_df.height, "val_rows": val_df.height,
                "predictions": pred_df.height, "dropped_overlong": dropped_overlong},
        versions=cfg._versions, metrics=dict(train_val_metrics), report=None,
        stage_extra={"labels": labels})
    hb.finish()


def _run_alignment_gate(run_dir: Path, probe, method, train_df: pl.DataFrame, cfg) -> None:
    """2.5 / 2.6: compare the packed loss against the plain loss over the first events_per_mb * accum rows of the train split, before the first optimizer step. torch.backends.cuda.matmul.allow_tf32 is held False only for the duration of this comparison, and the probe is left in eval mode -- run() is the one place that puts it into training mode, right before the step loop, so that the paths which skip this gate get there too."""
    n = cfg.train.events_per_mb * cfg.train.accum
    slice_df = train_df.sort("example_id").head(n)

    probe.set_training(False)
    prev_tf32 = torch.backends.cuda.matmul.allow_tf32
    torch.backends.cuda.matmul.allow_tf32 = False
    try:
        with torch.no_grad():
            packed = sum(float(method.loss(probe, b))
                         for b in method.batches(slice_df, probe.tokenizer, cfg))
            plain = float(method.reference_loss(probe, slice_df))
    finally:
        torch.backends.cuda.matmul.allow_tf32 = prev_tf32

    n_rows = slice_df.height
    packed_n = packed / max(n_rows, 1)
    plain_n = plain / max(n_rows, 1)
    diff = abs(packed_n - plain_n)
    tol = 1e-4
    result = {"PASS": diff <= tol, "packed": packed_n, "plain": plain_n, "diff": diff,
              "tol": tol, "n_rows": n_rows, "method": method.__name__}
    _atomic_write_json(run_dir / "align_check.json", result)
    if not result["PASS"]:
        raise SystemExit(
            f"{run_dir}/align_check.json: packed loss {packed_n} and plain loss {plain_n} differ "
            f"by {diff} > tol {tol}; the packing in {method.__name__}.batches has a bug")
