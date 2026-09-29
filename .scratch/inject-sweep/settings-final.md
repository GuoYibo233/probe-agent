# Final setting text (2026-09-29), every placeholder expanded

Replace the blocks pasted from settings-draft.md with these. Nothing here is abbreviated.

## 1. The baseline setting file: append

```yaml
gpt_oss_120b_appworld_t20:
  meta:   {notes: "20 random test tasks (.scratch/inject-sweep/task-list.md, draw seed 42), one seed; the baseline of the 2026-09-29 inject sweep"}
  sample: {split: [test], seeds: [42], tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3], pieces: 6, replicas: 1}
  score:  {by_seed: true}
```

## 2. The train_probe setting file: append the eight settings

```yaml
imp_ctool_0pt6b_full:
  meta:   {notes: "August np821b06 ctool imported (0.6B full; 3-epoch weights), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3], pieces: 6, replicas: 1}
  models: {probe: qwen3_0pt6b}
  probe:  {method: ctool, tuning: full}
  train:  {import_from: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/np821b06_gptoss_ctool, max_len: 16384}
  eval:   {risk: [0.10, 0.05]}

imp_cgen_0pt6b_full:
  meta:   {notes: "August np821b06 cgen imported (0.6B full; end of pass 1), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3], pieces: 6, replicas: 1}
  models: {probe: qwen3_0pt6b}
  probe:  {method: cgen, tuning: full}
  train:  {import_from: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/np821b06_gptoss_cgen, max_len: 16384}
  eval:   {theta_from: train_probe/imp_ctool_0pt6b_full}

imp_ctool_1pt7b_full:
  meta:   {notes: "August np821b17 ctool imported (1.7B full; 3-epoch weights), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3], pieces: 6, replicas: 1}
  models: {probe: qwen3_1pt7b}
  probe:  {method: ctool, tuning: full}
  train:  {import_from: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/np821b17_gptoss_ctool, max_len: 16384}
  eval:   {risk: [0.10, 0.05]}

imp_cgen_1pt7b_full:
  meta:   {notes: "August np821b17 cgen imported (1.7B full; end of pass 1), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3], pieces: 6, replicas: 1}
  models: {probe: qwen3_1pt7b}
  probe:  {method: cgen, tuning: full}
  train:  {import_from: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/np821b17_gptoss_cgen, max_len: 16384}
  eval:   {theta_from: train_probe/imp_ctool_1pt7b_full}

imp_ctool_1pt7b_lora:
  meta:   {notes: "August np821l17 ctool imported (1.7B LoRA r16 a32, merged; 3-epoch weights), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3], pieces: 6, replicas: 1}
  models: {probe: qwen3_1pt7b}
  probe:  {method: ctool, tuning: lora, lora_r: 16, lora_alpha: 32}
  train:  {import_from: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/np821l17_gptoss_ctool, max_len: 16384}
  eval:   {risk: [0.10, 0.05]}

imp_cgen_1pt7b_lora:
  meta:   {notes: "August np821l17 cgen imported (1.7B LoRA r16 a32, merged; end of pass 1), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3], pieces: 6, replicas: 1}
  models: {probe: qwen3_1pt7b}
  probe:  {method: cgen, tuning: lora, lora_r: 16, lora_alpha: 32}
  train:  {import_from: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/np821l17_gptoss_cgen, max_len: 16384}
  eval:   {theta_from: train_probe/imp_ctool_1pt7b_lora}

imp_ctool_4b_lora:
  meta:   {notes: "August np821l4 ctool imported (4B LoRA r16 a32, merged; 3-epoch weights), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3], pieces: 6, replicas: 1}
  models: {probe: qwen3_4b}
  probe:  {method: ctool, tuning: lora, lora_r: 16, lora_alpha: 32}
  train:  {import_from: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/np821l4_gptoss_ctool, max_len: 16384}
  eval:   {risk: [0.10, 0.05]}

imp_cgen_4b_lora:
  meta:   {notes: "August np821l4 cgen imported (4B LoRA r16 a32, merged; end of pass 1), served window 16k"}
  sample: {split: [test], seeds: [42], tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3], pieces: 6, replicas: 1}
  models: {probe: qwen3_4b}
  probe:  {method: cgen, tuning: lora, lora_r: 16, lora_alpha: 32}
  train:  {import_from: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/np821l4_gptoss_cgen, max_len: 16384}
  eval:   {theta_from: train_probe/imp_ctool_4b_lora}

```

## 3. The inject setting file

The file already has a `common:` block at the top; do not add a second one (a duplicate key is refused). Append the ten settings below after the existing ones.

```yaml
sw_0pt6b_full:
  meta:  {notes: "probe arm, 0.6B full pair: 4 formats x 3 thetas x 2 history lengths", override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
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
  meta:  {notes: "no-fill arm, 0.6B full pair: the cut and resume with nothing spliced", override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
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

sw_1pt7b_full:
  meta:  {notes: "probe arm, 1.7B full pair: 4 formats x 3 thetas x 2 history lengths", override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
    arm: probe
    probe_score: train_probe/imp_ctool_1pt7b_full
    probe_gen: train_probe/imp_cgen_1pt7b_full
    pieces: 6
    replicas: 1
  sweep:
    inject.theta: [0.6, 0.75, 0.9]
    inject.format: [p1_e1, p1_e2, p2_e1, p2_e2]
    build.hist_rounds: [3, 30]
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

nf_1pt7b_full:
  meta:  {notes: "no-fill arm, 1.7B full pair: the cut and resume with nothing spliced", override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
    arm: probe_nofill
    format: p1_e1
    probe_score: train_probe/imp_ctool_1pt7b_full
    probe_gen: train_probe/imp_cgen_1pt7b_full
    pieces: 6
    replicas: 1
  sweep:
    inject.theta: [0.6, 0.75, 0.9]
    build.hist_rounds: [3, 30]
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

sw_1pt7b_lora:
  meta:  {notes: "probe arm, 1.7B LoRA r16 a32, merged pair: 4 formats x 3 thetas x 2 history lengths", override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
    arm: probe
    probe_score: train_probe/imp_ctool_1pt7b_lora
    probe_gen: train_probe/imp_cgen_1pt7b_lora
    pieces: 6
    replicas: 1
  sweep:
    inject.theta: [0.6, 0.75, 0.9]
    inject.format: [p1_e1, p1_e2, p2_e1, p2_e2]
    build.hist_rounds: [3, 30]
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

nf_1pt7b_lora:
  meta:  {notes: "no-fill arm, 1.7B LoRA r16 a32, merged pair: the cut and resume with nothing spliced", override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
    arm: probe_nofill
    format: p1_e1
    probe_score: train_probe/imp_ctool_1pt7b_lora
    probe_gen: train_probe/imp_cgen_1pt7b_lora
    pieces: 6
    replicas: 1
  sweep:
    inject.theta: [0.6, 0.75, 0.9]
    build.hist_rounds: [3, 30]
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

sw_4b_lora:
  meta:  {notes: "probe arm, 4B LoRA r16 a32, merged pair: 4 formats x 3 thetas x 2 history lengths", override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
    arm: probe
    probe_score: train_probe/imp_ctool_4b_lora
    probe_gen: train_probe/imp_cgen_4b_lora
    pieces: 6
    replicas: 1
  sweep:
    inject.theta: [0.6, 0.75, 0.9]
    inject.format: [p1_e1, p1_e2, p2_e1, p2_e2]
    build.hist_rounds: [3, 30]
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

nf_4b_lora:
  meta:  {notes: "no-fill arm, 4B LoRA r16 a32, merged pair: the cut and resume with nothing spliced", override: [build.hist_rounds]}
  inject:
    split: [test]
    seeds: [42]
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
    arm: probe_nofill
    format: p1_e1
    probe_score: train_probe/imp_ctool_4b_lora
    probe_gen: train_probe/imp_cgen_4b_lora
    pieces: 6
    replicas: 1
  sweep:
    inject.theta: [0.6, 0.75, 0.9]
    build.hist_rounds: [3, 30]
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

np_plain:
  meta:  {notes: "no-probe arm: machinery wired, never fires, plain system prompt"}
  inject:
    split: [test]
    seeds: [42]
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
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
    tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3]
    theta: 0.6
    arm: no_probe
    format: p1_e2
    probe_score: train_probe/imp_ctool_0pt6b_full
    probe_gen: train_probe/imp_cgen_0pt6b_full
    pieces: 6
    replicas: 1
  score: {baseline: baseline/gpt_oss_120b_appworld_t20}

```
