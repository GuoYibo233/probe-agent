# WORKPLAN — what to do now

The current plan, overwritten in place. Why things were decided: `TIMELINE.md`.

## Where we are

- The from-zero tree replaced the old one on 2026-09-20.
- All three workflows pass end to end with `--debug`.
- The repo test of 2026-09-25 is done; its open items were ruled the same day.

## Next

1. First full-scale `sample`: `baseline gpt_oss_120b_appworld`. Set `sample.pieces` from
   measured throughput first (6 is a placeholder).
2. `train_probe` at full scale on that sample: ctool, then cgen and cparam.
3. `inject` arms (`probe`, `no_probe`) scored against the baseline.

## Open

- Eval walkthrough (steps 33–36) not finished; `train/methods/cgen.py` and `cparam.py`
  not yet read by gyb.
- A console to browse one run's details (a separate design; output directories stay
  `<stage>/<key>`).
- Training on a chosen `build` run is not possible yet (a design is in the 2026-09-25
  repo test report).
- Stale owner docs: the contracts sections listed in the errata, and the file list in
  `plans/2026-09-14-structure-from-zero.md`.
- `TIMELINE.md` entries for 2026-09-21 to 09-25.
