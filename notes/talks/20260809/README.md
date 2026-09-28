# This folder is the data backing for the 2026-08-09 group meeting report

This holds the write-up of every experiment run before today (2026-08-09), prepared for the report.
The data itself is not new, all of it is taken from records already in the repo, and not a single number was changed while organizing it.

## Where the data comes from

- All records from the old phase (2026-07-26 to 2026-08-02) are in the pre-wipe snapshot commit `b1f5b9c`.
  To check any number, run `git show b1f5b9c:<file path>` to see the original text.
- Records from the current phase (after the 2026-08-08 restart) are in the working tree's `RESULTS.md` and `METHOD.md`.
- The raw data on NFS (trajectories, weights, logs) was deleted at the 2026-08-02 wipe and cannot be recovered.
  So the numbers in this folder are the finest granularity that can still be traced.

## File list

| File | What question it answers |
|---|---|
| `data/01-settings.md` | What experiment settings the old phase used |
| `data/02-probe-matrix.md` | Which probes were trained, and their accuracy |
| `data/03-offline-inject.md` | What the offline injection experiments measured |
| `data/04-live-runs.md` | What each of the three live-run versions measured |
| `data/05-other-lines.md` | What the other two research lines (memory, multi-hop injection) measured |
| `data/06-timeline-and-incidents.md` | The order direction decisions happened in, and what engineering incidents came up along the way |
| `data/07-current-phase.md` | What the current phase has in hand |

## Three sourcing rules to know before citing these numbers

1. `METHOD.md` §5's ruling says "old-phase numbers are not to be used as a reference at all", meaning the new phase's
   experiments do not take the old numbers as a baseline. It is up to the presenter what standing these numbers take
   on in the report.
2. The test bed went through two generations (self-split v2 through v3_1, and the official problem sets
   `aw_official_v1` and so on). The old `DATA.md`'s exact words were "under the same appworld name these are two
   completely different test beds", the numbers from the two generations are not comparable.
3. The gptoss-side prior baseline (0.404) is more than double the q35/q36 side (0.174/0.159); the old `DATA.md`
   §3.1's exact words were "looking at absolute precision overrates the gptoss-side probe."
   Comparing models means reading the prior alongside the number.
