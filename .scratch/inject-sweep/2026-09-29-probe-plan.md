# Probe line for the inject sweep: confirmed action list (2026-09-29)

Discussed step by step with gyb on 2026-09-29 (detail-check). Every step below
is locked unless marked otherwise. Revised once the same day: no training this
round, small test subset only, August calibration imported, history length
becomes a sweep axis.

## Goal (confirmed)

Get four usable probe pairs (ctool for the trigger, cgen for the call) into the
new pipeline with no training this round, so that an inject sweep over many
settings can run on a small subset of the test tasks. Success: four
`train_probe` pairs with train and eval runs in the registry, each carrying the
August calibration temperature, and a baseline sample of the same small task
subset the inject runs are scored against. Not doing: any probe training,
full 315-task runs, probe architecture changes.

## Facts the plan rests on

- No real-scale run exists on this tree; every registry row is a `--debug` walk.
- The August np821 batch (old outputs tree, `pipeline/runs/np821*`) holds four
  tiers x {ctool, cgen, cparam}, trained on 1260 trajectories = 315 tasks x seeds
  42 / 67 / 4267 / 6742, with the same cut rule, the same probe text (task, last
  3 history rounds as "agent action -> environment result" clipped to 400
  characters, thinking so far) and the same Qwen3 base weights as this tree.
  Training knobs that differ from this tree's defaults: 3 epochs (ctool kept
  the end of pass 3; cgen kept the end of pass 1 because val worsened after),
  max length 4096 left-truncated, batch 2 x 4.
- Only `best/` survived per run; no 1-epoch ctool checkpoint exists.
- The August ctool theta sweeps (val, 2556 events): the four tiers coincide
  within a few points; accuracy 0.65 -> 0.96 and coverage 0.98 -> 0.24..0.37
  over theta 0.5 -> 0.975. Calibration temperatures 1.196 / 1.236 / 1.240 /
  1.270 for 0.6B full / 1.7B full / 1.7B LoRA / 4B LoRA.
- The probe's history length (`build.hist_rounds`) is a setting, is in the
  inject key, and the live side assembles from it; an owner note of
  2026-09-22 in `data/probe_input.py` already asks for the whole record.

## Action list

1. Sample (locked). A small subset of the test split, the same subset the
   inject runs use; its size and seeds are decided in the inject-side
   detail-check. It serves as the scoring baseline and as the sample the
   train_probe walk builds from. Reason: with no training and the calibration
   imported, nothing needs the train or dev splits. Who: gyb edits the
   setting files; the launch goes through gpu-run.
2. Build (locked, code change first). Remove the abort gate and its
   `build.max_abort_frac` field; skip only the aborted step of a record and
   keep the steps before it; print the skipped count in the build report.
   Reason: an aborted step has no next call to label, the earlier steps are
   ordinary data. Who: agent; `run.py version build --why` row before the
   walk.
3. Import path (locked, code change). New field `train.import_from: <path>`.
   When set, the train stage verifies the checkpoint's base weights match the
   setting's probe row, copies the checkpoint into its own run directory,
   writes the new meta (train key, served window, label map, call separator)
   and the August calibration temperature, and writes no predictions. The
   eval stage of an imported run records the imported temperature and the
   August theta sweep as imported numbers and fits nothing. The registry rows
   record the source path. Reason: eval and inject resolve a probe by a train
   run directory and its key, and the live service applies the eval's
   temperature; nothing else hands them the August weights and calibration
   honestly. Who: agent; `run.py version train --why` and `run.py version
   eval --why` rows. Implementation checks: label strings, not head indices,
   at the service boundary. The served window is the setting's train.max_len
   (implemented 2026-09-29; the schema default is 8192, so every import
   setting states the window it wants, 16384 here, and the checkpoint's
   4096 is recorded beside it as trained_max_len).
4. Eight imported settings (locked). In the train_probe file: per tier
   (`qwen3_0pt6b` full, `qwen3_1pt7b` full, `qwen3_1pt7b` lora r16 a32,
   `qwen3_4b` lora r16 a32) a ctool and a cgen setting with
   `train.import_from` pointing at the August directory and a served window
   of 16k tokens. Notes field of each ctool: "3-epoch August weights". One
   walk `run.py train_probe <eight names>` shares the sample and build. Who:
   gyb writes the settings; the walk goes through gpu-run (import is CPU
   work, but the stage is a GPU stage in the table).
5. Thetas (locked). Three shared thetas 0.6 / 0.75 / 0.9 for every pair, one
   `sweep:` block over theta and format. Reason: the four August curves
   coincide, and two frozen thetas above 0.85 would sample only the
   low-coverage corner.
6. History length axis (locked, option 1 of 2026-09-29). The same August
   probes are run with the last 3 rounds (what they were trained on) and
   with every earlier round of the record, the served window widened to 16k
   so the long text is not cut from the left. What it measures: whether the
   trained-on-3 probe survives the longer input. A probe trained on the long
   input (option 2) is deferred to a later round.

## Dropped during the discussion

- Retraining the 12 cells on the new sample: dropped for reuse and for "no
  training this round".
- A 1-epoch ctool: no such checkpoint survived.
- Per-tier frozen thetas from the eval report: replaced by the three shared
  values.
- The 0.6B LoRA and 4B full tiers: no August checkpoint exists; the grid is
  four pairs, not six.
- Full sample of all splits (1248 trajectories, 10 to 40 h): dropped once
  training and prediction were both out; the sample shrinks to the inject
  task subset.
- Retraining one pair on the long history input (option 2): deferred, not
  refused.

## Open (next detail-check: the inject side)

- How many test tasks and which seeds.
- The arm and format grid: 4 pairs x 5 formats x 3 thetas x 2 history
  lengths for the probe arm, plus probe_nofill and no_probe arms.
- Loop processes per agent server and how many servers.

## Suggested order of execution

Code changes (steps 2 and 3) first, since the walk cannot start without
them; gyb's setting edits (steps 1 and 4) in parallel; then one smoke walk
with `--debug`, then the real walk.
