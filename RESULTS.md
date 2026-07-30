# RESULTS — 实验统计数字总表

> 本文件由 `python ops/record.py render` 自动生成，**不要手改**。
> 数据源是 append-only 的 `ops/runs.jsonl`；改数字请补一条 finish 事件。
> 方向决策的来龙去脉看 [TIMELINE.md](TIMELINE.md)，原始数据不在 git 里。

| run_id | 日期 | 方向 | commit | 模型 | 状态 | 关键数字 | 结论 |
|---|---|---|---|---|---|---|---|
| `20260730_t12c_smoke_7b` | 2026-07-30 18:46 | c3 | `871f502+dirty` | Qwen2.5-7B-Instruct | ok | smoke_pass=6/6 n_errors_total=0 acc_exprag=0.2 acc_exprecent=0.2 acc_remem=0.0 acc_dc_cu=0.0 acc_dc_rs=0.0 acc_awm=0.0 llm_calls_remem=58 llm_calls_dc=30 | T12c 验收达成:六被试正式模型(Qwen2.5-7B-Instruct)全链路冒烟无错,每被试 15 题 summary 齐;低分为闭卷 L3 预期,另暴露 dc_*/awm 答案抽取不压长句+EM-only 判定两个可分离问题,T13 放量前处理;每题 LLM 调用次数不等(remem 1-4/dc 2/其余 1)计入 token 账 |
| `20260730_1835_bert_t6_bfcl_mixed` | 2026-07-30 18:38 | c2 | `871f502+dirty` | ModernBERT-base | ok | best_calA=0.7847 ceiling_qwen_acc005=0.9645 ceiling_qwen_cov005=0.7478 ceiling_gptoss_acc005=0.9157 | bfcl v3_1 混训天花板:qwen侧0.9645/0.7478,gptoss侧0.9157/0.7615;coverage较纯qwen v3天花板(0.509/0.349)大幅抬升,混训增益在覆盖不在精度 |
| `20260730_fig1_fullhist_8b` | 2026-07-30 18:20 | c3 | `bac6964+dirty` | Qwen3-8B | ok | acc_L0=0.62to0.94 acc_L1=0.98to1.00 acc_L2=0.84to0.86 tok_ratio_L0=0.84 tok_ratio_L1=1.17 tok_ratio_L2=2.5 wall_ratio_L0=0.73 wall_ratio_L1=0.66 wall_ratio_L2=1.21 truncated=0/150 avg_eps_included=4.5 | T12d 全历史基线收官(30 run 300 集,同卡 nomem/fullhist 配对)。档位用代码标签(L0/L1/L2),对应正式编号 L2/L2-/L1,见 DATA.md 6.1:L0=完全一样的题 +32pp 且总 token x0.84(省在输出侧,输出 token -28%,模仿前集少走弯路);L1=几乎一样的题 天花板已满 +2pp 略贵(x1.17);L2=同类但换了东西的题 +2pp 却 x2.50——档位越远全历史越不划算,与 oracle 天花板(只在完全一样那一档非零)构成上下界,支撑选择性记忆动机;预算截断全程未触发,此为无删减全历史。更正:前一条 finish 把 L0 写成'近重复档',按两套编号都不成立(L0=完全重复),数字不变。 |
| `20260730_oracle_ceiling_8bfull` | 2026-07-30 18:02 | c3 | `62a18c3+dirty` | - | ok | ceiling_L2_total=+21.0% ceiling_L2_per_ep=+23.4% ceiling_L1=0% ceiling_L2minus=0% | 逐字回放上界只在 L2 非零且被失败任务封死(能回放的集本来便宜);L2 以上的省必须来自泛化——天花板基线并列汇报的动机 |
| `20260727_tracelab_simv0` | 2026-07-30 18:02 | c3 | `62a18c3+dirty` | - | ok | adj_sim_gt0.8=68.4% adj_sim_0.3-0.8=17.2% adj_sim_lt0.3=14.5% near_dup_within50=96.1% high_sim_cross_project=10.8% | 重复相似任务是真实负载主体;跨 project 假相似 10.8% 为 L4 现实原型;仪器只见工具构成,边界已在论文声明 |
| `20260728_fig1_8bfull` | 2026-07-30 18:02 | c3 | `62a18c3+dirty` | Qwen3-8B | ok | total_tok_saving_L2=+9.6% total_tok_saving_L2minus=-16.8% total_tok_saving_L1=-19.6% acc_delta_all=0pp | 8B 红利小于 4B;按正典货币(总token)近重复档也为负(输入税),Sp@k 到 k=8 才转正;详见 fig1_pilot/ANALYSIS_8bfull.md + benchmark_design/METRICS_SMOKE_8bfull.md |
| `20260730_1716_bert_t6_xgptoss` | 2026-07-30 17:16 | T6 | `62a18c3+dirty` | ModernBERT-base | running | - | - |
| `20260730_1716_bert_t8_causal` | 2026-07-30 17:16 | T8 | `62a18c3+dirty` | Qwen3-0.6B-Base / LFM2.5-350M-Base | ok | appworld_causal_qwen_acc005=0.9621 appworld_causal_qwen_cov005=0.3338 bfcl_causal_qwen_acc005=0.9779 tales_causal_qwen_acc005=0.9077 cost_ratio_bfcl=19.8 cost_ratio_appworld=26.4 cost_ratio_tales=34.1 | 因果探针裁决:appworld 95%门被打开(ModernBERT无解->0.9621/0.3338),coverage全面2.5-4.3x,earliness降0.05-0.13,成本1/20-1/34;8192窗口对照=噪声级收益,窗口非瓶颈;tales risk0.1档θ迁移失守为其特有 |
| `20260730_1713_bert_t6_xqwen` | 2026-07-30 17:13 | C2-2t | `5e87638+dirty` | - | ok | bfcl_home_acc005=0.9748 bfcl_coldxfer_acc005=0.897 bfcl_recal_acc005=0.971 appworld_home_acc005=0.949 tales_home_acc01=0.7619 | qwen训练侧矩阵:bfcl 主场0.975/冷迁移0.897/换校准救回0.971(cov减半);appworld换校准救不满;tales全弱.部署结论:换agent模型时bfcl重做校准即可,appworld/tales需重训 |
| `20260730_1713_bert_t7_extractor` | 2026-07-30 17:13 | C2-2t | `5e87638+dirty` | - | running | - | - |
| `20260730_1713_bert_t5_ablation` | 2026-07-30 17:13 | C2-2t | `5e87638+dirty` | - | running | - | - |
| `20260730_1645_bert_replay_tales_v3` | 2026-07-30 16:45 | C2-2t | `b55d520+dirty` | ModernBERT-base | ok | prior_baseline=0.556 risk10_coverage=0.336 risk10_trig_acc=0.839 risk05_coverage=0.147 risk05_trig_acc=0.85 depth09_acc=0.78 temperature=3.092 n_events_test=408 | 终审负结果:数据翻倍把高θ coverage从0拉到14.7%,但精度天花板84-85%离95%差10pt,tales投机门不开;开放动作空间是根因 |
| `20260730_0814_bert_replay_appworld_v3` | 2026-07-30 08:14 | C2-2t | `9f91011+dirty` | ModernBERT-base | ok | prior_baseline=0.298 risk10_coverage=0.19 risk10_trig_acc=0.933 risk05_feasible=0 depth09_acc=0.579 temperature=2.149 n_events_test=791 | 终审负结果:数据翻倍精度仍钉在93.3%(v2fix 93.1%),风险0.05档无可行θ,appworld投机门95%标准下不开;v2fix边缘悬案了结 |
| `20260730_0446_bert_replay_tales_v2fix` | 2026-07-30 04:46 | C2-2t | `715e4bc+dirty` | ModernBERT-base | ok | prior_baseline=0.672 risk10_coverage=0.0 risk05_coverage=0.0 calB_theta090_trig_acc=0.87 calB_theta095_trig_acc=0.875 depth09_acc=0.802 temperature=3.189 n_events_test=201 | 负结果:精度天花板0.87够不到95%约束,无可行工作点,tales投机门v2fix开不了;深度曲线0.644-0.802非冻结,待v3(数据翻倍)终审 |
| `20260730_0413_hotpot_t11_var` | 2026-07-30 04:14 | C1 | `40df390+dirty` | Qwen/Qwen3-8B | ok | n_records=1338 seeds=3 comp_early_soft_drop=0.18 bridge_deadzone_dtok=-153 | 采样方差检查:comparison早注毒性/死区/both_start最优三结论跨种子稳健;bridge hop2子集小样本已标注 |
| `20260730_0350_bfcl_gptoss_topup` | 2026-07-30 03:50 | collect | `96d9605+dirty` | gpt-oss-120b | ok | n_traj=200 think_nonempty=200 bfcl_events_v3_1=3325 | gpt-oss 补采 200/200 全量落盘,思考/解析双判据全过;并入 v3_1 后 bfcl 事件 2265->3325,双重建逐字节一致 |
| `20260730_0204_bert_replay_bfclv3` | 2026-07-30 02:04 | C2-2t | `381b834+dirty` | modernbert-base | ok | trig_acc_risk05=0.9925 coverage_risk05=0.5929 theta_risk05=0.95 trig_acc_risk10=0.8955 coverage_risk10=0.8894 earliness_risk05=0.6152 wrong_spec_risk05=0.0044 prior_baseline=0.049 train_best_calA=0.7518 | bfcl 结论对重切分稳健:精度99.3%/coverage59.3%,与 v2fix(96.6%/62.0%)CI 互覆;切分方差~±3pt 即误差棒 |
| `20260730_0109_bert_replay_awfix` | 2026-07-30 01:09 | C2-2t | `35529fb+dirty` | modernbert-base | ok | trig_acc_risk05=0.931 coverage_risk05=0.1902 theta_risk05=0.925 trig_acc_risk10=0.8842 coverage_risk10=0.3115 earliness_risk05=0.5631 prior_baseline=0.226 n_fired_risk05=58 train_best_calA=0.6206 | appworld 中间档：先验碾过、coverage19%不趴地、精度93.1%差口气(n=58,CI过线)；v3 数据翻倍后重判 |
| `20260730_0056_bert_probe_v3` | 2026-07-30 00:56 | C2-2t | `35529fb+dirty` | modernbert-base | ok | bfcl_best_calA=0.7518 appworld_best_calA=0.6133 tales_best_calA=0.6947 | v3三训全毕业:数据翻倍训练侧tales+7pt(0.6947),appworld持平(0.6133),bfcl略降(0.7518,切分不同不可比) |
| `20260729_2238_bert_replay_bfclfix` | 2026-07-29 22:38 | C2-2t | `3e36694+dirty` | modernbert-base | ok | trig_acc_risk05=0.966 coverage_risk05=0.6203 theta_risk05=0.925 trig_acc_risk10=0.9441 coverage_risk10=0.7553 earliness_risk05=0.6224 wrong_spec_risk05=0.0211 prior_baseline=0.038 calib_conf_vs_acc=0.964/0.966 | bfcl 投机门开了：θ=0.925 下精度96.6%/coverage62%/earliness0.62，校准近完美；废版负结论翻盘 |
| `20260729_2235_bert_replay_bfcl_v2fix` | 2026-07-29 22:35 | C2-2t | `3e36694+dirty` | modernbert-base | ok | trig_acc@theta0.8=0.9441 coverage@theta0.8=0.7553 earliness@theta0.8=0.664 wrong_spec@theta0.8=0.0422 trig_acc@theta0.925=0.966 coverage@theta0.925=0.6203 prior_baseline=0.038 train_best_calA_weighted_acc=0.8057 | v2fix 翻案:bfcl 有可行θ,θ=0.8 时 cov0.76/acc0.94,θ=0.925 时 acc0.97;深度曲线 0.69→0.86 上行,先验 0.038 被碾过 |
| `20260729_2202_bert_probe_v2fix` | 2026-07-29 22:02 | C2-2t | `54a4a4b+dirty` | modernbert-base | ok | bfcl_best_calA=0.8057 appworld_best_calA=0.6206 tales_best_calA=0.6204 | v2fix三训全毕业:混合精度修复有效(bfcl为废版2.5倍);回放裁决bfcl胜/appworld边缘/tales负 |
| `20260729_2106_bert_replay_bfcl_v2` | 2026-07-29 21:06 | C2-2t | `8cce422+dirty` | modernbert-base | ok | best_val_weighted_acc=0.3262 replay_feasible_theta_risk10=none replay_feasible_theta_risk05=none max_coverage_at_theta0.5=0.0642 trig_acc_at_theta0.5=0.5714 conf_ceiling=0.7 prior_baseline=0.038 | bfcl 负结果：置信度天花板~0.7，无 θ 满足精度≥90%约束；样本acc~27%(先验7倍)但开不了投机门 |

## 逐条详情

### `20260730_t12c_smoke_7b`

- **想验证什么**：T12c 验收件:六被试换正式模型重冒烟,每被试一次冒烟通过记录
- **结论**：T12c 验收达成:六被试正式模型(Qwen2.5-7B-Instruct)全链路冒烟无错,每被试 15 题 summary 齐;低分为闭卷 L3 预期,另暴露 dc_*/awm 答案抽取不压长句+EM-only 判定两个可分离问题,T13 放量前处理;每题 LLM 调用次数不等(remem 1-4/dc 2/其余 1)计入 token 账
- **方向**：c3 ｜ **状态**：ok ｜ **起止**：2026-07-30 18:46 → 2026-07-30 18:57
- **代码**：`871f502`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **模型 / 种子**：Qwen2.5-7B-Instruct / 20260729
- **数字**：smoke_pass=6/6 n_errors_total=0 acc_exprag=0.2 acc_exprecent=0.2 acc_remem=0.0 acc_dc_cu=0.0 acc_dc_rs=0.0 acc_awm=0.0 llm_calls_remem=58 llm_calls_dc=30
- **原始数据**：`logs/20260730_t12c_smoke`（不在 git 里）
- **命令**：`benchmark_design/evomem_driver.py --agent {exprag,exprecent,remem,dc_cu,dc_rs,awm} --tasks l3_2wiki_items.jsonl --limit 15 (vLLM tokyo108)`

### `20260730_1835_bert_t6_bfcl_mixed`

- **想验证什么**：bfcl 的 v3 主线是纯 qwen 数据,混训天花板行必须用 v3_1(qwen+gptoss 合流)重训一条;tales/appworld 的 v3 本就含双侧无此问题
- **结论**：bfcl v3_1 混训天花板:qwen侧0.9645/0.7478,gptoss侧0.9157/0.7615;coverage较纯qwen v3天花板(0.509/0.349)大幅抬升,混训增益在覆盖不在精度
- **方向**：c2 ｜ **状态**：ok ｜ **起止**：2026-07-30 18:38 → 2026-07-30 23:57
- **代码**：`871f502`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 3
- **模型 / 种子**：ModernBERT-base / 20260729
- **参数**：data=v3_1 n_train=47799 n_labels=106 steps=4482 epochs=3 bs=8 accum=4
- **数字**：best_calA=0.7847 ceiling_qwen_acc005=0.9645 ceiling_qwen_cov005=0.7478 ceiling_gptoss_acc005=0.9157
- **原始数据**：`envs/bert_runs/bfcl_v3_1_mixed`（不在 git 里）
- **命令**：`envs/bert/train_probe.py --env bfcl --data envs/bert_data/v3_1 --out envs/bert_runs/bfcl_v3_1_mixed (tmux bert_t6_bfcl_mixed_t106g3, 先 --smoke 通过再全量)`

### `20260730_fig1_fullhist_8b`

- **想验证什么**：T12d 全历史基线:第三臂 fullhist,每集塞入全部前集轨迹,超预算最旧先截;配对 nomem 重跑供同硬件墙钟对照
- **结论**：T12d 全历史基线收官(30 run 300 集,同卡 nomem/fullhist 配对)。档位用代码标签(L0/L1/L2),对应正式编号 L2/L2-/L1,见 DATA.md 6.1:L0=完全一样的题 +32pp 且总 token x0.84(省在输出侧,输出 token -28%,模仿前集少走弯路);L1=几乎一样的题 天花板已满 +2pp 略贵(x1.17);L2=同类但换了东西的题 +2pp 却 x2.50——档位越远全历史越不划算,与 oracle 天花板(只在完全一样那一档非零)构成上下界,支撑选择性记忆动机;预算截断全程未触发,此为无删减全历史。更正:前一条 finish 把 L0 写成'近重复档',按两套编号都不成立(L0=完全重复),数字不变。
- **方向**：c3 ｜ **状态**：ok ｜ **起止**：2026-07-30 18:20 → 2026-07-31 03:10
- **代码**：`bac6964`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **模型 / 种子**：Qwen3-8B / 20260729
- **数字**：acc_L0=0.62to0.94 acc_L1=0.98to1.00 acc_L2=0.84to0.86 tok_ratio_L0=0.84 tok_ratio_L1=1.17 tok_ratio_L2=2.5 wall_ratio_L0=0.73 wall_ratio_L1=0.66 wall_ratio_L2=1.21 truncated=0/150 avg_eps_included=4.5
- **原始数据**：`fig1_pilot/results`（不在 git 里）
- **命令**：`fig1_pilot/run_fullhist_worker.sh 方案A(3档×5种子,同卡先nomem后fullhist配对,--seed 0-4 沿8bfull保逐集配对,budget 24576 tok)`

### `20260730_oracle_ceiling_8bfull`

- **想验证什么**：oracle 零成本回放上界,在 8bfull nomem 流上算
- **结论**：逐字回放上界只在 L2 非零且被失败任务封死(能回放的集本来便宜);L2 以上的省必须来自泛化——天花板基线并列汇报的动机
- **方向**：c3 ｜ **状态**：ok ｜ **起止**：2026-07-30 18:02 → 2026-07-30 18:02
- **代码**：`62a18c3`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **数字**：ceiling_L2_total=+21.0% ceiling_L2_per_ep=+23.4% ceiling_L1=0% ceiling_L2minus=0%
- **原始数据**：`benchmark_design/ORACLE_CEILING_8bfull.md`（不在 git 里）
- **命令**：`benchmark_design/oracle_ceiling.py --legacy-levels`

### `20260727_tracelab_simv0`

- **想验证什么**：生态效度:真实负载里相似重复任务占多大比例
- **结论**：重复相似任务是真实负载主体;跨 project 假相似 10.8% 为 L4 现实原型;仪器只见工具构成,边界已在论文声明
- **方向**：c3 ｜ **状态**：ok ｜ **起止**：2026-07-30 18:02 → 2026-07-30 18:02
- **代码**：`62a18c3`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **数字**：adj_sim_gt0.8=68.4% adj_sim_0.3-0.8=17.2% adj_sim_lt0.3=14.5% near_dup_within50=96.1% high_sim_cross_project=10.8%
- **原始数据**：`tracelab_analysis`（不在 git 里）
- **命令**：`tracelab_analysis/similarity_v0.py`

### `20260728_fig1_8bfull`

- **想验证什么**：C3 全矩阵复跑:8B 上记忆红利与档位关系
- **结论**：8B 红利小于 4B;按正典货币(总token)近重复档也为负(输入税),Sp@k 到 k=8 才转正;详见 fig1_pilot/ANALYSIS_8bfull.md + benchmark_design/METRICS_SMOKE_8bfull.md
- **方向**：c3 ｜ **状态**：ok ｜ **起止**：2026-07-30 18:02 → 2026-07-30 18:02
- **代码**：`62a18c3`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **模型 / 种子**：Qwen3-8B / 20260729
- **数字**：total_tok_saving_L2=+9.6% total_tok_saving_L2minus=-16.8% total_tok_saving_L1=-19.6% acc_delta_all=0pp
- **原始数据**：`fig1_pilot/results`（不在 git 里）
- **命令**：`fig1_pilot/launch_fleet.sh (8bfull_*,3档×mem/nomem×5seed×10ep)`

### `20260730_1716_bert_t6_xgptoss`

- **想验证什么**：跨模型换底座:用 gpt-oss 侧轨迹训 ModernBERT 探针,与 qwen 侧对照(T6);bfcl 一条排在 t8 g0 队列末尾
- **方向**：T6 ｜ **状态**：running ｜ **起止**：2026-07-30 17:16 → 未收尾
- **代码**：`62a18c3`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo105 GPU 6,7
- **模型 / 种子**：ModernBERT-base / 20260729
- **参数**：data=envs/bert_data/v3_1_xmodel/train-gptoss max_len=4096 bs=8 accum=4 epochs=3
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs`（不在 git 里）
- **命令**：`envs/bert/train_probe.py --env {tales,appworld,bfcl} --data envs/bert_data/v3_1_xmodel/train-gptoss --out envs/bert_runs/<env>_v3_xgptoss`

### `20260730_1716_bert_t8_causal`

- **想验证什么**：因果底座(Qwen3-0.6B/LFM2.5-350M)+线性头替代 ModernBERT 探针:整段一次前向、按事件监督;含 tales 8192 窗口对照;开训前逐 token 对齐检查全过
- **结论**：因果探针裁决:appworld 95%门被打开(ModernBERT无解->0.9621/0.3338),coverage全面2.5-4.3x,earliness降0.05-0.13,成本1/20-1/34;8192窗口对照=噪声级收益,窗口非瓶颈;tales risk0.1档θ迁移失守为其特有
- **方向**：T8 ｜ **状态**：ok ｜ **起止**：2026-07-30 17:16 → 2026-07-30 20:23
- **代码**：`62a18c3`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo105 GPU 0,1,2,3,4,5
- **模型 / 种子**：Qwen3-0.6B-Base / LFM2.5-350M-Base / 20260729
- **参数**：max_len=4096 bs=4 accum=8 lr=1e-05 epochs=3 variant_8k=max_len=8192,bs=2,grad_ckpt,align_tol=3e-4
- **数字**：appworld_causal_qwen_acc005=0.9621 appworld_causal_qwen_cov005=0.3338 bfcl_causal_qwen_acc005=0.9779 tales_causal_qwen_acc005=0.9077 cost_ratio_bfcl=19.8 cost_ratio_appworld=26.4 cost_ratio_tales=34.1
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_runs`（不在 git 里）
- **命令**：`envs/bert/train_causal_probe.py --base {qwen,lfm} --env {bfcl,appworld,tales} --out envs/bert_runs/<env>_v3_causal_<base>`

### `20260730_1713_bert_t6_xqwen`

- **想验证什么**：T6 跨模型: qwen 侧轨迹训 router,与 gptoss 侧对照迁移性
- **结论**：qwen训练侧矩阵:bfcl 主场0.975/冷迁移0.897/换校准救回0.971(cov减半);appworld换校准救不满;tales全弱.部署结论:换agent模型时bfcl重做校准即可,appworld/tales需重训
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-30 17:13 → 2026-07-30 23:57
- **代码**：`5e87638`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 7,8,9
- **模型 / 种子**：- / 42
- **参数**：data=v3_1_xmodel/train-qwen
- **数字**：bfcl_home_acc005=0.9748 bfcl_coldxfer_acc005=0.897 bfcl_recal_acc005=0.971 appworld_home_acc005=0.949 tales_home_acc01=0.7619
- **原始数据**：`envs/bert_runs/{tales,appworld,bfcl}_v3_xqwen`（不在 git 里）
- **命令**：`envs/bert/train_probe.py --data envs/bert_data/v3_1_xmodel/train-qwen`

### `20260730_1713_bert_t7_extractor`

- **想验证什么**：T7 抽取头: 在 v3 事件上联训 答/span/param 三头,看参数级抽取准确率能否支撑投机执行
- **方向**：C2-2t ｜ **状态**：running ｜ **起止**：2026-07-30 17:13 → 未收尾
- **代码**：`5e87638`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 4,5,6
- **模型 / 种子**：- / 42
- **参数**：data=v3 params=v3_params
- **原始数据**：`envs/bert_runs/{bfcl,appworld,tales}_ext_v3`（不在 git 里）
- **命令**：`envs/bert/train_extractor.py --env {bfcl,appworld,tales} (data v3 + params v3_params)`

### `20260730_1713_bert_t5_ablation`

- **想验证什么**：T5 输入消融: 砍掉 THINKING / HISTORY 段后 calA 加权 acc 掉多少
- **方向**：C2-2t ｜ **状态**：running ｜ **起止**：2026-07-30 17:13 → 未收尾
- **代码**：`5e87638`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 0,1,2,3
- **模型 / 种子**：- / 42
- **参数**：input_mode=no-think+no-hist data=v3
- **原始数据**：`envs/bert_runs/{env}_v3_{nothink,nohist}`（不在 git 里）
- **命令**：`envs/bert/train_probe.py --data envs/bert_data/v3 --input-mode no-think/no-hist, 6 条 = 3 env x 2 mode`

### `20260730_1645_bert_replay_tales_v3`

- **想验证什么**：tales v3 终审:v2fix天花板0.87判负,v3训练侧+7pt(0.6947 vs 0.6204),看精度天花板是否过95%
- **结论**：终审负结果:数据翻倍把高θ coverage从0拉到14.7%,但精度天花板84-85%离95%差10pt,tales投机门不开;开放动作空间是根因
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-30 16:45 → 2026-07-30 17:03
- **代码**：`b55d520`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 2
- **模型 / 种子**：ModernBERT-base / 42
- **参数**：theta_sweep=calB risk=0.10/0.05 data=v3
- **数字**：prior_baseline=0.556 risk10_coverage=0.336 risk10_trig_acc=0.839 risk05_coverage=0.147 risk05_trig_acc=0.85 depth09_acc=0.78 temperature=3.092 n_events_test=408
- **原始数据**：`/home/y-guo/reproduce/new1/envs/bert_data/v3`（不在 git 里）
- **命令**：`CUDA_VISIBLE_DEVICES=2 mbert-env/bin/python envs/bert/eval_replay.py --env tales --run envs/bert_runs/tales_v3 --data envs/bert_data/v3`

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
- **结论**：v3三训全毕业:数据翻倍训练侧tales+7pt(0.6947),appworld持平(0.6133),bfcl略降(0.7518,切分不同不可比)
- **方向**：C2-2t ｜ **状态**：ok ｜ **起止**：2026-07-30 00:56 → 2026-07-30 16:45
- **代码**：`35529fb`  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo106 GPU 3
- **模型 / 种子**：modernbert-base / 20260729
- **参数**：data=v3 n_train=tales142621/appworld71002/bfcl25061
- **数字**：bfcl_best_calA=0.7518 appworld_best_calA=0.6133 tales_best_calA=0.6947
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
