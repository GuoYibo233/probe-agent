---
name: probe-pipeline
description: >-
  The entry point for running or extending new1's probe pipeline: the whole chain from
  sampling trajectories to the eval report is one workflow file's stage list, walked by
  `run.py <workflow> <setting>` (gpu-run handles the mechanics of any GPU stage inside
  it). It is also **the only entry point for extending this pipeline**: a new benchmark
  environment, agent-model family, probe backbone or training method all go through the
  four extension places `README.md` section 3 names, and any new axis value an extension
  brings is registered in `experimental_settings/schema.py` before any setting may use
  it. Invoke whenever Dungeon♂Master says "run the pipeline", or any task needs
  sample/build/train/eval
  chained together or extended. A single GPU task uses gpu-run alone; this skill manages
  the whole chain. Chinese triggers: "跑流水线" / "跑一批探针" / "新数据集跑一遍" / "出矩阵" /
  "换个环境跑" / "加个新模型/新格" / "换个切分方式" / "加一种训练方法".
version: 1.0.0
---

# probe-pipeline: running and extending the probe chain

1. **The chain is a workflow file.** `experimental_settings/train_probe.yaml` has
   `workflow: [sample, build, train, eval]`; `run.py train_probe <setting>` walks it.
   There is no per-stage command table any more: every stage program is called
   `<venv python> -m <module> --run-dir <dir> [--piece i/n]` by `run.py` or
   `jobs/launch.py`, never by a person. A batch of related experiments is the `sweep:`
   keyword inside one named setting, not a script.

2. **Who writes what.** `experimental_settings/*.yaml` and `models/table.yaml` are
   gyb's files; an agent reads them and never edits them — a hook refuses the edit. An
   agent proposes a named setting as a task for gyb to add. `experimental_settings/schema.py`
   is code and is edited for a new field or a new axis value, with a default that
   reproduces the old behaviour.

3. **The gates are in the programs.** Every gate that can stop a stage is held by the
   program that can fail it, and is listed in contracts 2.5, as amended by
   `.scratch/from-zero/contract-errata.md`: `build`'s record completeness, its abort
   share, its split gates (a task id in two splits, a task id in none of the
   environment's official lists) and its row gates (an empty `text`, a `depth` outside
   `[0, 1]`, a text whose thinking part is not a prefix of the record's thinking);
   `train`'s alignment gate; the generator eval's **three** gates — the referenced
   classifier eval has a `done.json`, `eval.risk` equals that report's `risk_targets`,
   and the two train runs share a build key; `inject`'s **three** `run.py`-held gates —
   the shared-build-key gate and the code-currency gate
   of contracts 2.5, plus the `5.4 / 2.1` errata ruling that compares a `key:`/`dir:`
   reference's stated `method:` against the referenced train run's frozen
   `probe.method`; `score`'s same-setup and baseline-pair gates; the launch gate, the
   dirty-tree gate and the card reservation.
   Two things that read like build gates are not gates: an event whose call `build_call`
   refuses, that fails the round-trip gate, or whose non-null action `split_args` cannot
   parse is skipped and counted under `counts.events_skipped_no_call`; `report.md`
   carries that count and, for the `build_call`-refusal and round-trip cases only, one
   line per event naming the record, the step and the reason (the errata's two rulings
   of 2026-09-17 and 2026-09-18: the build reports a rare data problem and goes on). And
   `build.max_examples` is a cap per split, applied after the split column is assigned,
   not a gate.

4. **The acceptance of any chain change is the `--debug` walk of its workflow file**,
   plus `run.py selfcheck` before delivery.

5. **Extending.** The four places a file is added are `data/environments/<env>.py`,
   `models/agent_models/<family>.py`, `models/probe_models/<backbone>.py`, and
   `train/methods/<m>.py`, whose eval side is a `PROBE_KIND` entry, a `MATCH_VERSION`
   entry and a `match_<m>` function in `eval/utils/probe_eval.py`. What each extension
   touches is **`README.md` section 3, "The extension recipes"**, and that one section
   is the only place this skill points at for what an extension touches — it keeps no
   copy here, because a second copy is a copy that rots.

6. **Write-back.** The new file's five annotation lines go into `README.md` in the same
   commit that adds it, `run.py selfcheck` proves them against the real import graph,
   and a new axis value is registered in `experimental_settings/schema.py` before any
   YAML file may use it.
