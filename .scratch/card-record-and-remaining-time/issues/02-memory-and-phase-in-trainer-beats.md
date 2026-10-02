# 02 memory and phase in the trainer's beats; the probe service's memory line

Status: ready-for-agent
Blocked by: -
Spec: .scratch/card-record-and-remaining-time/spec.md (sections "The record", "Remaining time")

## What to do

1. **`mem_gib` in every train beat.** `registry.beat()` (`jobs/registry.py:332-348`) accepts
   an optional `mem_gib` like `loss`. The trainer (`train/utils/trainer.py`) passes
   `torch.cuda.max_memory_reserved() / 2**30`, rounded to 0.01, on every beat it emits,
   training and prediction alike.
2. **The prediction phase has its own unit.** After training the trainer re-emits
   `hb.emit(0, predict_total, "step")` (`trainer.py:567`), so the progress and the rate of
   the prediction phase mix with the training steps. The prediction beats use the unit
   `prediction split` instead of `step`; `ls` already prints the unit.
3. **The probe service prints its memory.** After it loads its checkpoints, the probe
   service (`models/probe_models/service.py`) prints one line to its log,
   `probe service memory: <x> GiB reserved after loading`, from
   `torch.cuda.memory_reserved()`.
4. README section 2 lines of the changed files updated where they describe beats or logs.

## Acceptance

- A CPU-only unit test checks that a beat written with `mem_gib` carries it and that a beat
  without it is unchanged.
- `tests/test_packed_loss.py` and the five CPU modules pass; `run.py selfcheck` green.
- `run.py version train --same --from <commit> --why ...` (and `inject` if its code set holds
  the probe service file): the output of no stage changes.
- A `--debug` walk of one `train_probe` setting is a GPU step: return it as BLOCKED with the
  ready-to-run command.

## Comments
