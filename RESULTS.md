# RESULTS — 实验统计数字总表

> 本文件由 `python ops/record.py render` 自动生成，**不要手改**。
> 数据源是 append-only 的 `ops/runs.jsonl`；改数字请补一条 finish 事件。
> 方向决策的来龙去脉看 [TIMELINE.md](TIMELINE.md)，原始数据不在 git 里。

| run_id | 日期 | 方向 | commit | 模型 | 状态 | 关键数字 | 结论 |
|---|---|---|---|---|---|---|---|
| `20260729_2238_bert_replay_bfclfix` | 2026-07-29 22:38 | C2-2t | `3e36694+dirty` | modernbert-base | ok | trig_acc_risk05=0.966 coverage_risk05=0.6203 theta_risk05=0.925 trig_acc_risk10=0.9441 coverage_risk10=0.7553 earliness_risk05=0.6224 wrong_spec_risk05=0.0211 prior_baseline=0.038 calib_conf_vs_acc=0.964/0.966 | bfcl 投机门开了：θ=0.925 下精度96.6%/coverage62%/earliness0.62，校准近完美；废版负结论翻盘 |
| `20260729_2235_bert_replay_bfcl_v2fix` | 2026-07-29 22:35 | C2-2t | `3e36694+dirty` | modernbert-base | running | - | - |
| `20260729_2202_bert_probe_v2fix` | 2026-07-29 22:02 | C2-2t | `54a4a4b+dirty` | modernbert-base | running | - | - |
| `20260729_2106_bert_replay_bfcl_v2` | 2026-07-29 21:06 | C2-2t | `8cce422+dirty` | modernbert-base | ok | best_val_weighted_acc=0.3262 replay_feasible_theta_risk10=none replay_feasible_theta_risk05=none max_coverage_at_theta0.5=0.0642 trig_acc_at_theta0.5=0.5714 conf_ceiling=0.7 prior_baseline=0.038 | bfcl 负结果：置信度天花板~0.7，无 θ 满足精度≥90%约束；样本acc~27%(先验7倍)但开不了投机门 |

## 逐条详情

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
- **方向**：C2-2t ｜ **状态**：running ｜ **起止**：2026-07-29 22:35 → 未收尾
- **代码**：`3e36694`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 2
- **模型 / 种子**：modernbert-base / -
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v2fix`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES=2 /home/y-guo/reproduce/new1/mbert-env/bin/python /home/y-guo/reproduce/new1/envs/bert/eval_replay.py --env bfcl --run /home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v2fix`

### `20260729_2202_bert_probe_v2fix`

- **想验证什么**：混合精度修复后三环境重训(v2 作废);补记:实际 21:17 由 1cc975d5 发射,记录时代码已合回并 commit
- **方向**：C2-2t ｜ **状态**：running ｜ **起止**：2026-07-29 22:02 → 未收尾
- **代码**：`54a4a4b`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 0
- **模型 / 种子**：modernbert-base / 20260729
- **参数**：fix=fp32_weights_autocast_bf16
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
