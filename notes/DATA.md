# DATA — data settings and conventions

Settings and conventions only, no conclusions (those are in `jobs/RESULTS.md`).

## Before a new experiment

1. **Same data?** Numbers from different `sample` runs are not comparable. Name the run key.
2. **Prior baseline** (always guess the most frequent tool): recompute it for every dataset,
   never carry it over.
3. **Timing** is compared only between runs on the same card model.
4. **Seeds** are fixed in the setting and appear in the report.
5. **A rebuilt dataset** is compared byte for byte with the old one.
6. **New generation settings** go in a new named setting; never edit the one that produced
   existing runs.
7. **A changed judgment call** from `WORKPLAN.md` gets a `TIMELINE.md` entry.

## Datasets on the from-zero tree

None at full scale yet. Only `--debug` runs exist (see `jobs/RESULTS.md`).

## Datasets from the old tree (before 2026-09-20)

Built by the old `pipeline/`. Kept for reference; not comparable with new runs.
Full detail is in git before the from-zero rewrite.

**nyapass_aw_v1** (2026-08-22, the np821 batch)
- gpt-oss-120b, effort high, temperature 1.0, top_p 1.0, max 8192 tokens per step, 30 steps.
  Four vLLM instances on tokyo108 (2 H100 + 3/4/5 H200).
- All 315 AppWorld tasks (train 90 / dev 57 / test 168), 4 trajectories each (seeds 42, 67,
  4267, 6742) = 1260 trajectories.
- Weight 1 per cut, at most 64 cuts per event, dev used as val.
- 15216 events, 693583 samples, 150 tool classes. Test prior baseline 0.387.

**aw_p1_v1** (2026-08-21, the p1 batch)
- gpt-oss-120b, effort high, temperature 0.0, 30 steps, seed 20260729. Run on two H200 cards on
  tokyo108.
- All 315 AppWorld tasks, 1 trajectory each.
- Weight 1/m per cut within an event, at most 64 cuts per event.
- 4048 events, 175359 samples, 83 tool classes. Test prior baseline 0.419.
