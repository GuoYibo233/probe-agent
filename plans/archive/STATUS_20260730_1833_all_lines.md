# 全线实验状态书（2026-07-30 18:33 JST 实探快照）

> 自包含文档：供压缩后的对话或任何 session 接上现状。所有数字实探自
> train_log.jsonl / REPLAY_REPORT / runs.jsonl / ops/jobs.json，词表沿用
> `plans/2026-07-30-task-plan.md` §0。HEAD = `dd9f3d3`。
> **数字口径警告**：下文训练侧数字是 calA 校准集加权准确率（best_calA_weighted_acc），
> 不是回放协议数字；最终判语一律以各 run 目录 REPLAY_REPORT 为准。

## 0. 大盘：三条战线并行

1. **A 线第三波训练总攻**：105/106 共 18 卡，17:13–17:16 发射，19 个训练已毕业 10 个，
   其余健康在跑（日志分钟级更新，无卡死）；A 线随毕业随回放，已出 5 份回放报告。
2. **清尾线 T12d fullhist**（本线，107 g1 起步）：vLLM 服务 18:29 就绪（port 8791），
   L0 档 smoke 第一对 `fullhist_L0_nomem_s0` 在跑（服务端 ~50 tok/s 生成中）。
   方案 A：一档一卡（还会铺 L1/L2 两卡），同卡先 nomem 后 fullhist 配对墙钟，
   种子 0–4 沿 8bfull 保逐集配对，30 run 估 5–7h，明晨收数。
   run_id `20260730_fig1_fullhist_8b`（record start 已入账，发射 commit `bac6964`）。
3. **T12c 程序件**：ALFWorld EnvAdapter 已 commit（`dd9f3d3`）；单轮 driver 成品
   `benchmark_design/evomem_driver.py` 已落盘、**未验收未 commit**（写码 agent 回报在
   父 session）。

## 1. 今日已收官的裁决（全部有 run_id 入账）

### 1a. 六格表终审（v2fix/v3 × 三环境）——投机门只在 bfcl 开

| 环境 | 终审 | 关键数字 | commit |
|---|---|---|---|
| bfcl | ✅ 门开 | v3 精度 99.3% / coverage 59.3%（θ=0.8 v2fix 对照:0.755/0.944/0.664） | `6a806e3` |
| appworld | ❌ 门不开 | 终审 93.3%，与 v2fix 一致，95% 门槛下负结论更硬（CI 0.086） | `b55d520` |
| tales | ❌ 门不开 | 精度天花板 84–87%（v2fix 0.87 / v3 84–85%），prior 0.556 下 risk10: 精度 83.9%/cov 33.6% | `affb530` |

T2 判语定稿 `5e87638`：v3 三格为参照系；翻倍判语=bfcl 真提升、appworld/tales 是
信号天花板不是数据量问题；CI 收窄（bfcl 0.024）。
v3 主线训练 best_calA（参照系）：**bfcl 0.7518 / appworld 0.6133 / tales 0.6947**（`8314bb8`）。

### 1b. 其他今日收官

- T4 换算段合入 `96d9605`（投机经济两派生数，--cached-logits 纯 CPU 重跑）。
- T1 bfcl_gptoss 补采 200 任务 + T3 v3.1 建库 `937706b`（含 build_dataset 排序修复 `40df390`）。
- T11 C1 收尾 `25f73ac`：采样方差检查，三主线结论跨种子稳健。
- T9 闭环管线：bfcl 四口径 `4c28928` + appworld/tales runner `4491f16`；
  探针服务性能三连修（单线程 HTTPServer `e9c7a7a`→关 reference_compile `b17f1c9`→
  禁 cuDNN sdp `715e4bc`），每请求从数百 ms 压到 8–15ms；fork 分支修复 `9f91011`。
- D 线 T12a/b/d(CPU)/f + T15 协议节起笔 `b9d31c8`（main.tex 4 页编译干净）。
- 三笔补记账入 runs.jsonl（`81e80f8`）：`20260728_fig1_8bfull`（8B 全矩阵:L2 +9.6%/
  L2minus -16.8%/L1 -19.6%，Sp@k 到 k=8 才转正）、`20260727_tracelab_simv0`
  （邻接相似>0.8 占 68.4%，50 窗近重复 96.1%）、`20260730_oracle_ceiling_8bfull`
  （回放上界只在 L2 非零 +21.0%，被失败任务封死）。
- **T12e 判定已完勿重复烧卡**（缺口 L0/L3/L4 档挂 T14 一起补，
  见 `benchmark_design/HANDOFF_T12_A.md` §二）。

## 2. 在飞五路训练逐格明细（18:32 实探）

### T5 消融（106 g0–g3，台账 bert_t5_ablation）

| 环境 | no-think | no-hist | v3 主线参照 |
|---|---|---|---|
| bfcl | **0.3409** ✅（回放报告 17:26 已出） | **0.7685** ✅（回放 18:18 后待出/已排队） | 0.7518 |
| appworld | **0.4632** ✅（回放 17:27 已出） | 在跑 ep0 gstep 1750/~6600 | 0.6133 |
| tales | **0.6402** ✅（回放 17:28 已出） | 在跑 ep0 gstep 1050 | 0.6947 |

初步信号：去思考 bfcl 0.75→0.34，思考文本携带主要增量信号，消融支撑成立。
**待解读异常**：bfcl no-hist (0.7685) 略高于全量 (0.7518)；tales no-think 0.6402
低于 tales 频率先验 0.672。均等回放报告定夺。

### T6 跨模型双向矩阵（qwen 侧 106 g7–g9；gptoss 侧 105 g6–g7）

- qwen 侧（v3_1_xmodel/train-qwen）：bfcl **0.7651** ✅、appworld **0.607** ✅、
  tales 在跑 ep1 gstep 2200（15 it/s，快了）。
- gptoss 侧（train-gptoss）：bfcl 在跑 ep2 gstep 1550（loss 0.0011 接近收官）、
  appworld gstep 1000、tales gstep 1000（~6.6 it/s）。
- 四格评测（冷迁移/只换校准）在训练毕业后做，校准侧纯 CPU。

### T7 抽取头（106 g4–g6，run 目录 *_ext_v3）

- bfcl_ext_v3：ep1 中途评测 **calA_ans_acc 0.9464 / span_loose 0.8815 / span_strict 0.5885**。
  对标 SPORK 参数起步 7.6%——"选择档九成量级"验收线大概率能过。
- appworld_ext_v3 / tales_ext_v3：ep0 在跑（8.3 / 7.4 it/s）。

### T8 因果探针（105 g0–g5，台账 bert_t8_causal）——目前最大惊喜

| 格子 | 状态 | best_calA | vs ModernBERT 主线 |
|---|---|---|---|
| bfcl × LFM2.5-350M | ✅ 毕业（回放 17:47 已出） | **0.8330** | 0.7518 ↑ |
| bfcl × Qwen3-0.6B | ✅ 毕业（回放 17:46 已出） | **0.8012** | 0.7518 ↑ |
| tales × LFM | ✅ 毕业 | **0.7362** | 0.6947 ↑ |
| appworld × LFM | ✅ 毕业 | **0.6811** | 0.6133 ↑ |
| appworld × Qwen | 在跑 ep2（已 save_best 0.7111） | — | 0.6133 ↑（中途已超） |
| tales × Qwen (4096窗) | 在跑 ep1（0.93 it/s，最慢） | n_bound_dropped 883 | — |
| tales × Qwen-8k (8192窗对照) | 在跑 ep1（0.9 it/s） | n_bound_dropped 仅 2 | — |

**已出五格全部反超 ModernBERT**。若回放确认，T8 部署形态裁决干脆：因果探针
线性成本 + 分类更强。对齐检查全过（reldiff 判定，`62a18c3` 的 --align-tol）。
tales 4096 窗丢 883 句界 → A 线临场加 8192 窗对照（正确决定）。
LFM 许可非 Apache，汇报须标注。

## 3. 记录/台账状态

- 台账 active 五条：bert_t5_ablation / bert_t7_extractor / bert_t6_xqwen /
  bert_t8_causal / bert_t6_xgptoss——与实机 tmux/显存一致。
- `20260730_fig1_fullhist_8b`：record start 已入账；台账登记随 gpu-runner smoke 后补。
- runs.jsonl 今日新增 start 未 finish 的：五路训练各一 + fullhist 一条，
  各自毕业时走 Phase 6a 五连（record finish + 销号 + commit）。
- 工作树遗留（不归本线）：`ops/jobs.json` 活台账、`envs/loop/runs/`（B 线闭环原始数据，
  不入库）、`hotpot_inject/results_t11/`（同）、paper/ 散件与 `.claude/skills/paper-write/`
  （论文线自收）、`.claude/settings.json`（**必须留 untracked，勿删勿提交**）。

## 4. 接下来的关键节点

- **今晚 19–21 点**：no-hist×2、T6 剩余格、T7 三环境陆续毕业 → A 线回放收尾；
  tales 因果探针 qwen 系最晚（可能深夜）。
- **明晨**：fullhist 30 run 收数 → record finish → T12d 完全收官。
- **明天主战**：T10 闭环正式跑分（T9 基建齐，顺序 bfcl→appworld→tales，五口径）。
  注意：appworld/tales 投机门不开的负结果会影响截断组预期，θ 扫描范围该按此校准。
- **T12c 剩余**（T13 的最后依赖）：①ReMem/DynamicCheatsheet/AWM 与原论文行为核对；
  ②换正式模型（Qwen2.5-7B/14B-Instruct）上卡重冒烟（1 卡即够，
  vLLM 0.16.0 必须带 FLASHINFER_DISABLE_VERSION_CHECK=1，port 8791 模板见
  HANDOFF_T12_A.md §三）；③evomem_driver.py 验收 + commit。
- **未拍板项**：T16（WORKPLAN 重写 + 规划书入库）用户未点头，无人可动。

## 5. 监控命令备忘

```bash
python3 ops/gpu_jobs.py watch          # 台账+实机对账（交互式，30s 刷新）
python3 ops/gpu_jobs.py free           # 实探空卡
# 训练毕业判据：train_log.jsonl 尾行 event=done + best/ 有权重
tail -f logs/20260730_fig1_fullhist_L0.log   # fullhist L0 进度（L1/L2 同名类推）
tail -f logs/20260730_fig1_fullhist_srv_g1.log
```

## 6. 本快照的多 session 分工背景

主 session 群：A 线（调度/占卡/台账/commit 收口）、B 线（T9，已交付）、
C 线（探针程序件，已交付）、D 线（C3 纸面件，已交付）、
清尾线（本文作者：三笔补记账/T12e 判定/benchmark_design 收口/T12d 发射/T12c 两程序件）。
铁律沿用：GPU 发射唯一入口 gpu-run skill；commit 只 add 自己点名的文件；
`.claude/settings.json` 留 untracked。
