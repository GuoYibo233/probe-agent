# Setting text for the owner to paste (draft of 2026-09-29)

Three files are the owner's: `experimental_settings/baseline.yaml`,
`experimental_settings/train_probe.yaml`, `experimental_settings/inject.yaml`.
The blocks below are proposals; names may change. `TASKS` stands for the
20-task list in `task-list.md`, written out in full in each place. Field names
follow the code changes of 2026-09-29 (`train.import_from`); if a reviewer
renames the field, this draft follows.

## 1. baseline.yaml: the 20-task baseline

```yaml
gpt_oss_120b_appworld_t20:
  meta:   {notes: "20 random test tasks (task-list.md, draw seed 42), one seed; the baseline of the 2026-09-29 inject sweep"}
  sample: {split: [test], seeds: [42], tasks: TASKS, pieces: 6, replicas: 1}
  score:  {by_seed: true}
```

## 2. train_probe.yaml: eight imported probes

Each names the same sample as the baseline so the sample directory is shared.
`A` stands for `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs`.

```yaml
imp_ctool_0pt6b_full:
  meta:   {notes: "August np821b06 ctool imported (3-epoch weights), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: TASKS, pieces: 6, replicas: 1}
  models: {probe: qwen3_0pt6b}
  probe:  {method: ctool, tuning: full}
  train:  {import_from: A/np821b06_gptoss_ctool, max_len: 16384}
  eval:   {risk: [0.10, 0.05]}

imp_cgen_0pt6b_full:
  meta:   {notes: "August np821b06 cgen imported (end of pass 1), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: TASKS, pieces: 6, replicas: 1}
  models: {probe: qwen3_0pt6b}
  probe:  {method: cgen, tuning: full}
  train:  {import_from: A/np821b06_gptoss_cgen, max_len: 16384}
  eval:   {theta_from: train_probe/imp_ctool_0pt6b_full}

imp_ctool_1pt7b_full:   # as above with qwen3_1pt7b, A/np821b17_gptoss_ctool
imp_cgen_1pt7b_full:    # qwen3_1pt7b, A/np821b17_gptoss_cgen, theta_from train_probe/imp_ctool_1pt7b_full

imp_ctool_1pt7b_lora:
  meta:   {notes: "August np821l17 ctool imported (LoRA r16 a32, merged), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: TASKS, pieces: 6, replicas: 1}
  models: {probe: qwen3_1pt7b}
  probe:  {method: ctool, tuning: lora, lora_r: 16, lora_alpha: 32}
  train:  {import_from: A/np821l17_gptoss_ctool, max_len: 16384}
  eval:   {risk: [0.10, 0.05]}

imp_cgen_1pt7b_lora:    # qwen3_1pt7b, lora, A/np821l17_gptoss_cgen, theta_from train_probe/imp_ctool_1pt7b_lora
imp_ctool_4b_lora:      # qwen3_4b, lora, A/np821l4_gptoss_ctool
imp_cgen_4b_lora:       # qwen3_4b, lora, A/np821l4_gptoss_cgen, theta_from train_probe/imp_ctool_4b_lora
```

Check at the debug smoke: the build stage runs on a test-only sample, so its
train and val roles are empty. The import writes no predictions and the
imported eval fits nothing, so nothing reads those roles, but the build
itself must not refuse an empty role. If it does, that is a build change for
the agent, not a setting change.

## 3. inject.yaml: the sweep

One probe-arm setting and one no-fill setting per pair, plus two no-probe
settings. `meta.override` lists the probe-text field so the inject setting
may state a history length different from the probe's build (the schema's
inheritance rule). The sweep block lives inside the named setting.

```yaml
common:
  data:   {env: appworld, instructions: v1}
  models: {agent: gpt_oss_120b}

sw_0pt6b_full:
  meta:  {notes: "probe arm, 0.6B full pair, 4 formats x 3 thetas x 2 history lengths",
          override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: TASKS
    arm: probe
    probe_score: train_probe/imp_ctool_0pt6b_full
    probe_gen: train_probe/imp_cgen_0pt6b_full
    pieces: 6
    replicas: 1
  sweep:
    inject.theta: [0.6, 0.75, 0.9]
    inject.format: [p1_e1, p1_e2, p2_e1, p2_e2]
    build.hist_rounds: [3, 30]
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

nf_0pt6b_full:
  meta:  {notes: "no-fill arm, 0.6B full pair: the cut and resume with nothing spliced",
          override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: TASKS
    arm: probe_nofill
    format: p1_e1
    probe_score: train_probe/imp_ctool_0pt6b_full
    probe_gen: train_probe/imp_cgen_0pt6b_full
    pieces: 6
    replicas: 1
  sweep:
    inject.theta: [0.6, 0.75, 0.9]
    build.hist_rounds: [3, 30]
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

# sw_1pt7b_full / nf_1pt7b_full, sw_1pt7b_lora / nf_1pt7b_lora, sw_4b_lora / nf_4b_lora:
# the same two blocks with the pair's probe_score / probe_gen names.

np_plain:
  meta:  {notes: "no-probe arm: machinery wired, never fires, plain system prompt"}
  inject:
    split: [test]
    seeds: [42]
    tasks: TASKS
    theta: 0.6
    arm: no_probe
    format: p1_e1
    probe_score: train_probe/imp_ctool_0pt6b_full
    probe_gen: train_probe/imp_cgen_0pt6b_full
    pieces: 6
    replicas: 1
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

np_paragraph:
  meta:  {notes: "no-probe arm with the e2 explanatory paragraph in the system prompt"}
  inject:
    split: [test]
    seeds: [42]
    tasks: TASKS
    theta: 0.6
    arm: no_probe
    format: p1_e2
    probe_score: train_probe/imp_ctool_0pt6b_full
    probe_gen: train_probe/imp_cgen_0pt6b_full
    pieces: 6
    replicas: 1
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}
```

Counts: 4 x 24 = 96 probe-arm children, 4 x 6 = 24 no-fill children, 2
no-probe settings: 122 runs.

The existing two settings of inject.yaml (`probe_p1_e1_theta_0pt80`,
`no_probe_p1_e1_theta_0pt80`) can stay; they are not part of the sweep.
