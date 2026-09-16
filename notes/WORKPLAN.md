# Work plan

> The current plan, subject to being overwritten. Decision history belongs to
> `TIMELINE.md`; the two must not swap roles.

The current main line is the np821 batch (full plan text in
`plans/archive/2026-08-21-np821-plan.md`, the convention decisions are in the two
TIMELINE 2026-08-21 entries). Position: the construction block is complete and closed
out in one commit, the execution block has not started yet.

1. **Execution block** (follow the dependency order in plan §4, entered via the driver
   `python3 run.py pipeline --config pipeline/configs/np821_gptoss.json`):
   NFS space precheck → collect 1260 trajectories → annotate (the cut-point
   distribution stop point decides `max_bounds`) → smoke test the three cells plus the
   placement table → four batches of training → evaluation → matrix → Phase D
   wrap-up + Phase E write-back to the skill.
2. **Write-back list** (do these together the next time the matching code is touched;
   explicitly not touched in this np821 batch):
   - The hardcoded `SEED = 20260729` at `pipeline/eval/eval_tool.py:49`: zero changes
     to the five evaluation scripts this batch; the next time the evaluation code is
     touched, fold the seed into the 42 family and rerun the G12 acceptance line.
   - The `SEED = 20260729` in `pipeline/train/train_mbert_tool.py` /
     `train_mbert_extract.py`: the m-line has been paused since 2026-08-21, change it
     together on the day it restarts.
   - The `SEED = 20260729` in the four split generators
     `pipeline/collect/gen_*_splits.py`: these are one-off generators for task lists
     already checked into the repo, the constant is the archival record of a frozen
     artifact, changing them means changing the split, and doing so requires
     re-deciding the task list along with it.
   - The `SEED = 20260729` at `envs/collect/build_dataset.py:27` (the registry's
     build-dataset-legacy, the old line's historical entry point already superseded by
     pipeline/annotate/): the constant is the archival record of the frozen artifact
     bert_data v2 (the release report's first header line prints this SEED), changing
     it means changing the reproduction convention for the old data, held to the same
     standard as the four split generators, do not touch it. This spot was missed
     during the full-repo inventory at construction time, added on 2026-08-22 during
     acceptance review.
   - `pipeline/inject/replay_inject.py:399` and `pipeline/inject/score_live.py:119`
     look up the trajectory file by `appworld_<unit>.jsonl`: for a multi-sample batch,
     the filename carries an `_r<k>` suffix, so every lookup comes up empty, and this
     is a silent count-and-discard with no error (replay_inject exits 0 and produces
     an empty plan). Whenever these two lines (replay injection, live-run scoring)
     need to consume multi-sample-batch data, change the lookup to build the path from
     the sample row's own `traj` field instead; in the same pass,
     `pipeline/inject/exec_calls.py:573`'s grouping by unit must also change to
     grouping by traj, otherwise the events from a task's four trajectories will all
     get pinned onto a single trajectory. The np821 execution block does not need
     either of these two lines.
