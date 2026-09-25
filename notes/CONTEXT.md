# CONTEXT — glossary

One name per idea, used the same way in talk, docs and code. Chinese in
parentheses is the term used in chat.

## Running things

- **Setting**: one experiment, a named block in an `experimental_settings/<workflow>.yaml` file.
- **Workflow**: the file a setting lives in, and its fixed list of stages:
  `baseline` (sample, score), `train_probe` (sample, build, train, eval),
  `inject` (inject, score).
- **Stage**: one step of a workflow: `sample`, `build`, `train`, `eval`, `inject`, `score`.
- **Sweep child**: one setting expanded from a sweep, named `<name>/<field>=<value>,...`.
- **Reference**: a setting field that names another setting's run
  (`eval.theta_from`, `inject.probe_score`, `inject.probe_gen`, `score.baseline`).
- **Run key**: `<stage>-<12 hex>`, a hash of the setting's diff from the defaults plus the
  stage's era. It names the run directory, the tmux session, the registry row and the
  commit that closes out a result.
- **Era**: a number per stage in `jobs/versions.yaml`. A new era row sends later runs of
  that stage (and everything downstream) to new directories.
- **Same row**: a `jobs/versions.yaml` row saying a code change leaves a stage's output
  unchanged.
- **Code gate**: before reusing a run directory, `run.py` checks that the stage's code
  still matches what that run ran, or that same rows connect the two.
- **Job (长程任务)**: one stage run that holds cards.
- **Piece (分片)**: one process of a job. `sample` and `inject` split into several loop
  pieces (`pieces` field); `train` is one piece; each served model is a service piece.
- **Launch (发射)**: starting a job's pieces in tmux and writing its start row, done
  only by `run.py`.
- **Refire (补射)**: restarting a dead piece of an unfinished run (`run.py refire`).
- **Retry**: starting a run fresh (`run.py retry`), after `kill`.
- **Heartbeat (心跳)**: the progress lines a piece writes to its run's `heartbeat/` files.
- **Verdict (判定)**: a piece's health, computed from heartbeats by `run.py ls`:
  healthy, warming up, slowed, suspected stall, dead, done, not started.
- **Registry**: `jobs/runs.jsonl`, one start row and one finish row per stage run,
  rendered to `jobs/RESULTS.md`.

## The method

- **Agent model**: the large model doing the task (gpt-oss-120b today).
- **Probe (探针)**: a small model that reads the agent model's thinking so far and
  predicts its next tool call.
- **ctool / cgen / cparam**: the three probe methods. ctool classifies the tool and
  gives the confidence used to fire; cgen writes the whole call; cparam writes only the
  arguments, given the tool name.
- **Backbone**: the probe's base model (Qwen3-0.6B-Base today).
- **Cut (切口)**: a sentence boundary in the thinking. The probe reads, and injection
  happens, only at cuts.
- **Event**: all the cuts of one step before one tool call; one training group.
- **Fire (出手)**: the moment the trigger rule says yes at a cut.
- **θ (theta)**: the confidence threshold for firing. Always given by a person, never
  defaulted. `eval` freezes one θ per target wrong-fire rate (`eval.risk`).
- **Speculate**: run the predicted call early, in a saved-then-restored copy of the
  world, so no state is left behind.
- **Inject (注入)**: write the predicted call and its result back into the stream at the
  cut, and let the model continue.
- **Format**: how an injection is written: placement `p1` (inside the open thinking) or
  `p2` (after closing the thinking, as a message from sender `prefetch`), crossed with
  explanation `e1` (inline each time) or `e2` (once in the system prompt, plus a
  `[Prefetch]` marker). `note` is the old text.
- **Arm**: `probe` (fires and injects), `no_probe (空注入对照)` (all machinery wired, never
  fires), `probe_nofill` (fires but injects nothing).
- **Same-setup rule (同设铁律)**: baseline and method use the same model, service,
  sampling and decoding; the method adds no decoding trick the baseline lacks.
- **Core loop / axis (主干 / 轴)**: the fixed loop, and the parts of it we swap to try
  (see `METHOD.md`).
