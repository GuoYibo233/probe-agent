# 02 memory and phase in the trainer's beats; the probe service's memory line

Status: resolved
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
4. README section 2 lines of the changed files updated where they describe beats or logs,
   except the `jobs/registry.py` entry, which ticket 01 edits in parallel.

## Acceptance

- A CPU-only unit test checks that a beat written with `mem_gib` carries it and that a beat
  without it is unchanged.
- `tests/test_packed_loss.py` and the five CPU modules pass; `run.py selfcheck` green.
- No `jobs/versions.yaml` row on this branch: the main conversation writes the `--same` rows
  for `train`, `sample` and `inject` after the merge (spec, "Code-era rows").
- A `--debug` walk of one `train_probe` setting is a GPU step: return it as BLOCKED with the
  ready-to-run command.

## Comments

- 2026-10-02, wave 1 (ticket-run): the implementer returned BLOCKED for the GPU walk only, so the wave script ran no review; one separate opus review found no spec gap (F1: two README/docstring merge conflicts with ticket 01, resolved as the union; F2: "every beat" now reads "every counting beat"). Commits 521c1cf..337a028, merged at 56d49a0; same rows for train, sample and inject at 92917b0.
  - GPU check by the main conversation: `run.py train_probe ctool_qwen3_0pt6b --debug --cards tokyo105:7` (train-3e562de5abb9, RTX A6000 47 GiB): every counting beat carries `mem_gib` (4.75 at load, 42.77 after the training step, 43.64 at the end of prediction), the prediction beats read `prediction split`, and the finish row's card record holds `peak_gib` 43.64, `failure` null and the train speed over the `step` beats only. eval-841ca6060041 ok.
  - Not exercised on a card: the probe service's memory line (needs an inject walk). `notes/plans/2026-09-17-contracts.md` 8.4 still names `step` as the train unit and lists only tok_in, tok_out and loss as optional beat fields; that file is gyb's.
