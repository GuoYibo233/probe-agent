# RESULTS — 实验统计数字总表

> 本文件由 `python ops/record.py render` 自动生成，**不要手改**。
> 数据源是 append-only 的 `ops/runs.jsonl`；改数字请补一条 finish 事件。
> 方向决策的来龙去脉看 [TIMELINE.md](TIMELINE.md)，原始数据不在 git 里。

| run_id | 日期 | 方向 | commit | 模型 | 状态 | 关键数字 | 结论 |
|---|---|---|---|---|---|---|---|
| `20260730_0814_bert_replay_appworld_v3` | 2026-07-30 08:14 | C2-2t | `9f91011+dirty` | ModernBERT-base | ok | prior_baseline=0.298 risk10_coverage=0.19 risk10_trig_acc=0.933 risk05_feasible=0 depth09_acc=0.579 temperature=2.149 n_events_test=791 | 终审负结果:数据翻倍精度仍钉在93.3%(v2fix 93.1%),风险0.05档无可行θ,appworld投机门95%标准下不开;v2fix边缘悬案了结 |
| `20260730_0446_bert_replay_tales_v2fix` | 2026-07-30 04:46 | C2-2t | `715e4bc+dirty` | ModernBERT-base | ok | prior_baseline=0.672 risk10_coverage=0.0 risk05_coverage=0.0 calB_theta090_trig_acc=0.87 calB_theta095_trig_acc=0.875 depth09_acc=0.802 temperature=3.189 n_events_test=201 | 负结果:精度天花板0.87够不到95%约束,无可行工作点,tales投机门v2fix开不了;深度曲线0.644-0.802非冻结,待v3(数据翻倍)终审 |
| `20260730_0413_hotpot_t11_var` | 2026-07-30 04:14 | C1 | `40df390+dirty` | Qwen/Qwen3-8B | ok | n_records=1338 seeds=3 comp_early_soft_drop=0.18 bridge_deadzone_dtok=-153 | 采样方差检查:comparison早注毒性/死区/both_start最优三结论跨种子稳健;bridge hop2子集小样本已标注 |
| `20260730_0350_bfcl_gptoss_topup` | 2026-07-30 03:50 | collect | `96d9605+dirty` | gpt-oss-120b | ok | n_traj=200 think_nonempty=200 bfcl_events_v3_1=3325 | gpt-oss 补采 200/200 全量落盘,思考/解析双判据全过;并入 v3_1 后 bfcl 事件 2265->3325,双重建逐字节一致 |
| `20260730_0204_bert_replay_bfclv3` | 2026-07-30 02:04 | C2-2t | `381b834+dirty` | modernbert-base | ok | trig_acc_risk05=0.9925 coverage_risk05=0.5929 theta_risk05=0.95 trig_acc_risk10=0.8955 coverage_risk10=0.8894 earliness_risk05=0.6152 wrong_spec_risk05=0.0044 prior_baseline=0.049 train_best_calA=0.7518 | bfcl 结论对重切分稳健:精度99.3%/coverage59.3%,与 v2fix(96.6%/62.0%)CI 互覆;切分方差~±3pt 即误差棒 |
| `20260730_0109_bert_replay_awfix` | 2026-07-30 01:09 | C2-2t | `35529fb+dirty` | modernbert-base | ok | trig_acc_risk05=0.931 coverage_risk05=0.1902 theta_risk05=0.925 trig_acc_risk10=0.8842 coverage_risk10=0.3115 earliness_risk05=0.5631 prior_baseline=0.226 n_fired_risk05=58 train_best_calA=0.6206 | appworld 中间档：先验碾过、coverage19%不趴地、精度93.1%差口气(n=58,CI过线)；v3 数据翻倍后重判 |
| `20260730_0056_bert_probe_v3` | 2026-07-30 00:56 | C2-2t | `35529fb+dirty` | modernbert-base | running | - | - |
| `20260729_2238_bert_replay_bfclfix` | 2026-07-29 22:38 | C2-2t | `3e36694+dirty` | modernbert-base | ok | trig_acc_risk05=0.966 coverage_risk05=0.6203 theta_risk05=0.925 trig_acc_risk10=0.9441 coverage_risk10=0.7553 earliness_risk05=0.6224 wrong_spec_risk05=0.0211 prior_baseline=0.038 calib_conf_vs_acc=0.964/0.966 | bfcl 投机门开了：θ=0.925 下精度96.6%/coverage62%/earliness0.62，校准近完美；废版负结论翻盘 |
| `20260729_2235_bert_replay_bfcl_v2fix` | 2026-07-29 22:35 | C2-2t | `3e36694+dirty` | modernbert-base | ok | trig_acc@theta0.8=0.9441 coverage@theta0.8=0.7553 earliness@theta0.8=0.664 wrong_spec@theta0.8=0.0422 trig_acc@theta0.925=0.966 coverage@theta0.925=0.6203 prior_baseline=0.038 train_best_calA_weighted_acc=0.8057 | v2fix 翻案:bfcl 有可行θ,θ=0.8 时 cov0.76/acc0.94,θ=0.925 时 acc0.97;深度曲线 0.69→0.86 上行,先验 0.038 被碾过 |
| `20260729_2202_bert_probe_v2fix` | 2026-07-29 22:02 | C2-2t | `54a4a4b+dirty` | modernbert-base | ok | bfcl_best_calA=0.8057 appworld_best_calA=0.6206 tales_best_calA=0.6204 | v2fix三训全毕业:混合精度修复有效(bfcl为废版2.5倍);回放裁决bfcl胜/appworld边缘/tales负 |
| `20260729_2106_bert_replay_bfcl_v2` | 2026-07-29 21:06 | C2-2t | `8cce422+dirty` | modernbert-base | ok | best_val_weighted_acc=0.3262 replay_feasible_theta_risk10=none replay_feasible_theta_risk05=none max_coverage_at_theta0.5=0.0642 trig_acc_at_theta0.5=0.5714 conf_ceiling=0.7 prior_baseline=0.038 | bfcl 负结果：置信度天花板~0.7，无 θ 满足精度≥90%约束；样本acc~27%(先验7倍)但开不了投机门 |

## 逐条详情

### `20260730_0814_bert_replay_appworld_v3`

- **想验证什么**：appworld v3 终审:v2fix边缘(93.1%/19.0%),v3数据翻倍重判,先验0.226
- **结论**：终审负结果:数据翻倍精度仍钉在93.3%(v2fix 93.1%),风险0.05档无可行θ,appworld投机门95%标准下不开;v2fix边缘悬案了结
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-30 08:14 → 2026-07-30 08:25
- **代码**：`9f91011`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 2
- **模型 / 种子**：ModernBERT-base / 42
- **参数**：theta_sweep=calB risk=0.10/0.05 data=v3
- **数字**：prior_baseline=0.298 risk10_coverage=0.19 risk10_trig_acc=0.933 risk05_feasible=0 depth09_acc=0.579 temperature=2.149 n_events_test=791
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_data/v3`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES=2 mbert-env/bin/python envs/bert/eval_replay.py --env appworld --run envs/bert_runs/appworld_v3 --data envs/bert_data/v3`

### `20260730_0446_bert_replay_tales_v2fix`

- **想验证什么**：tales v2fix 回放:硬门槛频率先验0.672,判精度95%/coverage/先验三判据
- **结论**：负结果:精度天花板0.87够不到95%约束,无可行工作点,tales投机门v2fix开不了;深度曲线0.644-0.802非冻结,待v3(数据翻倍)终审
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-30 04:46 → 2026-07-30 08:09
- **代码**：`715e4bc`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 2
- **模型 / 种子**：ModernBERT-base / 42
- **参数**：theta_sweep=calB risk=0.10/0.05
- **数字**：prior_baseline=0.672 risk10_coverage=0.0 risk05_coverage=0.0 calB_theta090_trig_acc=0.87 calB_theta095_trig_acc=0.875 depth09_acc=0.802 temperature=3.189 n_events_test=201
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_data/v2`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES=2 mbert-env/bin/python envs/bert/eval_replay.py --env tales --run envs/bert_runs/tales_v2fix`

### `20260730_0413_hotpot_t11_var`

- **想验证什么**：T11 C1 收尾：HotpotQA 采样方差批次，temperature=0.6 三种子 × 8 分片 = 24 任务，测跨种子 mean±std
- **结论**：采样方差检查:comparison早注毒性/死区/both_start最优三结论跨种子稳健;bridge hop2子集小样本已标注
- **方向**：C1 ｜ **状态**：ok ｜ **起止**：2026-07-30 04:14 → 2026-07-30 04:43
- **代码**：`40df390`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo105 GPU 0,1,2,3,4,5,6,7
- **模型 / 种子**：Qwen/Qwen3-8B / 1
- **参数**：temperature=0.6 gen_seeds=1,2,3 n_per_type=40 shards=8 budget=2500 hop1_offsets=-1,25,0 hop2_offsets=0
- **数字**：n_records=1338 seeds=3 comp_early_soft_drop=0.18 bridge_deadzone_dtok=-153
- **原始数据**：`/home/y-guo/reproduce/new1/hotpot_inject/results_t11`（不在 git 里）
- **命令**：`jlens-env/bin/python hotpot_inject/hotpot_v1.py --model Qwen/Qwen3-8B --n 40 --types comparison,bridge --hop1-offsets=-1,25,0 --hop2-offsets=0 --both-start --budget 2500 --temperature 0.6 --gen-seed {1,2,3} --shard {0..7}/8 --out hotpot_inject/results_t11/hp8b_T06_s{SEED}_shard{I}of8.jsonl`

### `20260730_0350_bfcl_gptoss_topup`

- **想验证什么**：补 v1 缺口:bfcl 无 gpt-oss 轨迹,跨模型双向矩阵需要它
- **结论**：gpt-oss 补采 200/200 全量落盘,思考/解析双判据全过;并入 v3_1 后 bfcl 事件 2265->3325,双重建逐字节一致
- **方向**：collect ｜ **状态**：ok ｜ **起止**：2026-07-30 03:50 → 2026-07-30 04:34
- **代码**：`96d9605`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo108 GPU 0
- **模型 / 种子**：gpt-oss-120b / -
- **数字**：n_traj=200 think_nonempty=200 bfcl_events_v3_1=3325
- **原始数据**：`envs/runs/full_v2_topup/bfcl_gptoss`（不在 git 里）
- **命令**：`bfcl generate --model openai/gpt-oss-120b --test-category multi_turn_base(经 chat 端点,reasoning high)`

### `20260730_0204_bert_replay_bfclv3`

- **想验证什么**：bfcl v3(重建重切分,无新数据)对照 v2fix 的 96.6%/62%,量化切分方差;train best_calA 0.7518 vs 0.8057
- **结论**：bfcl 结论对重切分稳健:精度99.3%/coverage59.3%,与 v2fix(96.6%/62.0%)CI 互覆;切分方差~±3pt 即误差棒
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-30 02:04 → 2026-07-30 02:05
- **代码**：`381b834`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 2
- **模型 / 种子**：modernbert-base / 20260729
- **参数**：run_dir=bfcl_v3 data=v3
- **数字**：trig_acc_risk05=0.9925 coverage_risk05=0.5929 theta_risk05=0.95 trig_acc_risk10=0.8955 coverage_risk10=0.8894 earliness_risk05=0.6152 wrong_spec_risk05=0.0044 prior_baseline=0.049 train_best_calA=0.7518
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v3`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES=2 mbert-env/bin/python envs/bert/eval_replay.py --env bfcl --run envs/bert_runs/bfcl_v3 --data envs/bert_data/v3`

### `20260730_0109_bert_replay_awfix`

- **想验证什么**：appworld 修复版回放：三判据=精度≥95%/coverage 不趴地/打赢先验 0.226；train best_calA 0.6206
- **结论**：appworld 中间档：先验碾过、coverage19%不趴地、精度93.1%差口气(n=58,CI过线)；v3 数据翻倍后重判
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-30 01:09 → 2026-07-30 01:13
- **代码**：`35529fb`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 2
- **模型 / 种子**：modernbert-base / 20260729
- **参数**：run_dir=appworld_v2fix
- **数字**：trig_acc_risk05=0.931 coverage_risk05=0.1902 theta_risk05=0.925 trig_acc_risk10=0.8842 coverage_risk10=0.3115 earliness_risk05=0.5631 prior_baseline=0.226 n_fired_risk05=58 train_best_calA=0.6206
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs/appworld_v2fix`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES=2 mbert-env/bin/python envs/bert/eval_replay.py --env appworld --run envs/bert_runs/appworld_v2fix`

### `20260730_0056_bert_probe_v3`

- **想验证什么**：v3 数据(补采并入,tales/appworld 样本翻倍)三环境重训,对照 v2fix 看数据量对触发精度/coverage 的边际收益
- **方向**：C2-2t ｜ **状态**：running ｜ **起止**：2026-07-30 00:56 → 未收尾
- **代码**：`35529fb`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 3
- **模型 / 种子**：modernbert-base / 20260729
- **参数**：data=v3 n_train=tales142621/appworld71002/bfcl25061
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES={3,4,5} mbert-env/bin/python envs/bert/train_probe.py --env {tales,appworld,bfcl} --data envs/bert_data/v3 --out envs/bert_runs/{env}_v3`

### `20260729_2238_bert_replay_bfclfix`

- **想验证什么**：修复版 checkpoint(best_calA 0.8057)上重测回放：三判据=触发精度≥95%/coverage 不趴地/打赢先验 0.038；对照废版结论是否翻盘
- **结论**：bfcl 投机门开了：θ=0.925 下精度96.6%/coverage62%/earliness0.62，校准近完美；废版负结论翻盘
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-29 22:38 → 2026-07-29 22:38
- **代码**：`3e36694`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 2
- **模型 / 种子**：modernbert-base / 20260729
- **参数**：run_dir=bfcl_v2fix
- **数字**：trig_acc_risk05=0.966 coverage_risk05=0.6203 theta_risk05=0.925 trig_acc_risk10=0.9441 coverage_risk10=0.7553 earliness_risk05=0.6224 wrong_spec_risk05=0.0211 prior_baseline=0.038 calib_conf_vs_acc=0.964/0.966
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v2fix`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES=2 mbert-env/bin/python envs/bert/eval_replay.py --env bfcl --run envs/bert_runs/bfcl_v2fix`

### `20260729_2235_bert_replay_bfcl_v2fix`

- **想验证什么**：v2fix 修复版 checkpoint 的 bfcl 回放评测，验证是否推翻废版负结果（废版无可行θ）
- **结论**：v2fix 翻案:bfcl 有可行θ,θ=0.8 时 cov0.76/acc0.94,θ=0.925 时 acc0.97;深度曲线 0.69→0.86 上行,先验 0.038 被碾过
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-29 22:35 → 2026-07-29 22:40
- **代码**：`3e36694`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 2
- **模型 / 种子**：modernbert-base / -
- **数字**：trig_acc@theta0.8=0.9441 coverage@theta0.8=0.7553 earliness@theta0.8=0.664 wrong_spec@theta0.8=0.0422 trig_acc@theta0.925=0.966 coverage@theta0.925=0.6203 prior_baseline=0.038 train_best_calA_weighted_acc=0.8057
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v2fix`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES=2 /home/y-guo/reproduce/new1/mbert-env/bin/python /home/y-guo/reproduce/new1/envs/bert/eval_replay.py --env bfcl --run /home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v2fix`

### `20260729_2202_bert_probe_v2fix`

- **想验证什么**：混合精度修复后三环境重训(v2 作废);补记:实际 21:17 由 1cc975d5 发射,记录时代码已合回并 commit
- **结论**：v2fix三训全毕业:混合精度修复有效(bfcl为废版2.5倍);回放裁决bfcl胜/appworld边缘/tales负
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-29 22:02 → 2026-07-30 08:15
- **代码**：`54a4a4b`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 0
- **模型 / 种子**：modernbert-base / 20260729
- **参数**：fix=fp32_weights_autocast_bf16
- **数字**：bfcl_best_calA=0.8057 appworld_best_calA=0.6206 tales_best_calA=0.6204
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES={0,1,2} mbert-env/bin/python train_probe_fix.py --env {tales,appworld,bfcl} --out envs/bert_runs/{env}_v2fix`

### `20260729_2106_bert_replay_bfcl_v2`

- **想验证什么**：bfcl 探针回放评测：calA 拟温度→calB 扫θ→test 冻结；判据=触发精度≥95% 且 coverage 不趴地，必须打赢频率先验 0.038
- **结论**：bfcl 负结果：置信度天花板~0.7，无 θ 满足精度≥90%约束；样本acc~27%(先验7倍)但开不了投机门
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-29 21:06 → 2026-07-29 21:08
- **代码**：`8cce422`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo105 GPU 2
- **模型 / 种子**：modernbert-base / 20260729
- **数字**：best_val_weighted_acc=0.3262 replay_feasible_theta_risk10=none replay_feasible_theta_risk05=none max_coverage_at_theta0.5=0.0642 trig_acc_at_theta0.5=0.5714 conf_ceiling=0.7 prior_baseline=0.038
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v2`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES=2 mbert-env/bin/python envs/bert/eval_replay.py --env bfcl`
