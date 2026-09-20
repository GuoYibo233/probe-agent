# 42 The resume checkpoint's rng_state is recorded and never restored

Status: needs-triage
Severity: minor
File: train/utils/trainer.py:197
Contract: 1.6 (the checkpoint layout: `last/` holds `{step, epoch, commit, rng_state}`), 2.4
Errata: touched by "1.6 (`last/`): the optimizer and scheduler state have no home -> `trainer.run` writes `<run_dir>/last/optimizer.pt` itself beside `Probe.save`'s output; `rng_state` in `last/meta.json` is `{"torch": hex, "cuda": hex|null}` and the epoch order is recomputed from `random.Random(cfg.train.seed + epoch)`" — that entry fixes the field's shape and the epoch order; it does not rule that the saved draw state is discarded

## Finding

The trainer captures the torch and cuda generator states at every periodic
checkpoint and writes them into `last/meta.json`:

```python
def _rng_state_hex() -> dict:
    cuda_hex = None
    if torch.cuda.is_available():
        cuda_hex = torch.cuda.get_rng_state().numpy().tobytes().hex()
    return {"torch": torch.get_rng_state().numpy().tobytes().hex(), "cuda": cuda_hex}
```
(`train/utils/trainer.py:121-125`, written at `train/utils/trainer.py:366-369`)

No caller reads it back. The only seeding a resumed run does is the same call a
fresh run makes:

```python
    torch.manual_seed(cfg.train.seed)
```
(`train/utils/trainer.py:197`)

and the resume branch touches the optimizer and the scheduler only
(`train/utils/trainer.py:273-280`). `grep -n "rng_state" train/ models/ run.py`
finds the write and nothing else. The value it would restore is exactly right:
`resume_step` is `last/meta.json`'s `step` (`train/utils/trainer.py:186`), the
fast-forward runs no forward pass (`train/utils/trainer.py:329-337`), so the
first recomputed step is the step whose draws the saved state begins.

## Failure scenario

A `train_probe` setting with `probe.tuning: lora` — `probe.lora_dropout`
defaults to 0.05, so the forward pass draws from the torch generator at every
step. The run is killed at step 900 and resumed. From step 901 on, the dropout
masks are the ones a generator freshly seeded with `cfg.train.seed` produces
after zero draws, not the ones the uninterrupted run would have drawn after 900
steps. The resumed run therefore ends on different weights, a different `best/`
and different `predictions.parquet` rows than the same setting run without the
crash — under the same key, the same commit and the same `settings.yaml`, with
the state that would have made the two identical sitting unread in
`last/meta.json`.

## Proposed fix

Restore the saved state where the optimizer and the scheduler are restored. In
the `resume_step is not None` branch of `train/utils/trainer.py:273-280`, after
`torch.manual_seed(cfg.train.seed)` has run, read `last_meta["rng_state"]` and
call `torch.set_rng_state` on the `torch` entry and
`torch.cuda.set_rng_state` on the `cuda` entry when it is not null, rebuilding
each tensor from its hex with `torch.frombuffer(bytes.fromhex(...),
dtype=torch.uint8)`. A `last/meta.json` written without the field keeps today's
behaviour.
