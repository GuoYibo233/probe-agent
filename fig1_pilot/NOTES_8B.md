# Qwen3-8B 小矩阵试跑记录 (step 14)

日期: 2026-07-27。硬件: shiga GPU1/GPU2 (48G)。后端: `hf_server.py` (Plan B,
与 redo106 同款; shiga 驱动跑不了 vLLM wheel — libcudart.so.13 缺失, 见
vllm_serve.log)。入口: `run_8b_L1_shiga.sh` (新文件, 原脚本未动)。
矩阵: Qwen3-8B, {L1} × {mem, nomem} × seed0 × k=5, `--think --max-tokens 2048`。
每 cell 独占一张卡一个 server, 两 cell 并行, 全程 tmux (`new1_fig1_8b_*`),
日志在 `../logs/new1_fig1_8b_run.log` + `results/8b_L1_*_s0.log`。

## 结果

结果文件: `results/8b_L1_nomem_s0.jsonl`, `results/8b_L1_mem_s0.jsonl`。
两个 cell 的 5 集 stream 完全相同 (同 seed 同 pool), 逐集配对可比。

### 8B L1/nomem (GPU1)

| ep | success | steps | wall_s | tok_in | tok_out |
|---|---|---|---|---|---|
| 1 | 1 | 4 | 84.5 | 2156 | 2753 |
| 2 | 1 | 4 | 109.2 | 2115 | 3594 |
| 3 | 1 | 12 | 136.3 | 6797 | 4372 |
| 4 | 1 | 5 | 93.4 | 2608 | 3025 |
| 5 | 1 | 16 | 128.6 | 9938 | 4208 |

mean: success **1.00** · wall **110s** · steps 8.2

### 8B L1/mem (GPU2)

| ep | success | steps | wall_s | tok_in | tok_out |
|---|---|---|---|---|---|
| 1 | 1 | 4 | 84.0 | 2156 | 2753 |
| 2 | 1 | 4 | 55.5 | 2391 | 1824 |
| 3 | 1 | 12 | 162.7 | 8304 | 5342 |
| 4 | 1 | 4 | 47.8 | 3186 | 1571 |
| 5 | 1 | 4 | 29.6 | 3384 | 973 |

mean: success **1.00** · wall **76s** · steps 5.6

### 与 4B (Qwen3.5-4B, tokyo108 vLLM) L1 对照

| cell | success (ep1-5 mean) | wall_s/ep | steps/ep |
|---|---|---|---|
| 8B nomem s0, k=5 | 1.00 | 110 | 8.2 |
| 8B mem s0, k=5 | 1.00 | 76 | 5.6 |
| 4B nomem s0 ep1-5 | 0.80 | 417 | 15.2 |
| 4B mem s0 ep1-5 | 0.80 | 388 | 17.6 |
| 4B nomem 5seed ep1-5 | 0.72 | 617 | 20.6 |
| 4B mem 5seed ep1-5 | 0.84 | 410 | 15.8 |

wall 跨硬件/跨 serving 栈不可比 (shiga 48G + HF serial vs H100 vLLM); 8B 更快
主要是 steps 和思考 token 少得多, 不是硬件快。

## 8B 上代码有没有坑

- `fig1_run.py` 零改动直接跑通 8B: `--model Qwen/Qwen3-8B` + hf_server 即可,
  enable_thinking 模板参数对 Qwen3-8B 有效, 无解析/接口问题。
- 唯一环境坑: shiga 上 vLLM 起不来 (CUDA13 runtime 缺失), 必须走 hf_server。
  hf_server 串行处理请求 → 一 cell 一 server 一卡, 不能共享。
- 可比性坑 (非 bug): `build_stream` 的 L1 stream 依赖 k — k=5 与 k=10 同 seed
  抽出的 trial 子集/顺序不同, 所以本次 8B 集合与 4B seed0 的前 5 集不是同一批
  游戏 (同 pool: ToiletPaper→ToiletPaperHanger)。step-16 全矩阵用 k=10 即与
  4B 逐集同游戏, 严格配对。
- 信号坑: 8B 在 L1 直接打满 success=1.00, L1 的 accuracy 维度会 ceiling,
  学习曲线信号将主要落在 wall/steps 维度和 L0/L2 (4B 上 L0 只有 ~0.2 成功率,
  8B 未必打满)。

## step-16 全矩阵排程 (2026-07-27 07:44 启动)

矩阵: Qwen3-8B, {L0,L1,L2}×{nomem,mem}×seed0-4×k=10 = 30 runs (15 对)。
配对规则同 run_full.sh: 每 (level,seed) 对在**同一张卡**上先 nomem 后 mem。
worker: `run_8bfull_worker.sh`; 输出 `results/8bfull_{L}_{setting}_s{S}.jsonl`。
后端: **全部 10 卡统一 hf_server** (Plan B)。tokyo107 先试了 vLLM 0.16
(import 通过), 但 serve 时 EngineCore 初始化失败 (07:45, 见
`../logs/new1_fig1m_srv107_g*.log` 首段报错; 驱动 535/CUDA12.2 vs cu13 wheel),
08:02 按 redo106 先例切回 hf_server, runner 的 wait_ready 窗口内无缝接上。
**wall 提醒**: L0/L1 + L2s0 在 shiga (48G), L2 s1-4 在 tokyo107 (RTX 6000 Ada
48G) — 跨机 wall 不可比, 对内 (mem vs nomem) 永远同卡同后端可比。

| run(对) | 卡 | server 会话 | runner 会话 | 端口 |
|---|---|---|---|---|
<!-- runner 会话全在 shiga; server 会话 srv107_* 在 tokyo107 的 tmux 里 -->
| L0 s0 → L1 s0 | shiga g1 | new1_fig1m_srv_g1 | new1_fig1m_run_c0 | 8731 |
| L0 s1 → L1 s1 | shiga g2 | new1_fig1m_srv_g2 | new1_fig1m_run_c1 | 8732 |
| L0 s2 → L1 s2 | shiga g4 | new1_fig1m_srv_g4 | new1_fig1m_run_c2 | 8734 |
| L0 s3 → L1 s3 | shiga g5 | new1_fig1m_srv_g5 | new1_fig1m_run_c3 | 8735 |
| L0 s4 → L1 s4 | shiga g6 | new1_fig1m_srv_g6 | new1_fig1m_run_c4 | 8736 |
| L2 s0 | shiga g7 | new1_fig1m_srv_g7 | new1_fig1m_run_c5 | 8737 |
| L2 s1 | tokyo107 g0 | new1_fig1m_srv107_g0 | new1_fig1m_run_c6 | 8712 |
| L2 s2 | tokyo107 g1 | new1_fig1m_srv107_g1 | new1_fig1m_run_c7 | 8713 |
| L2 s3 | tokyo107 g2 | new1_fig1m_srv107_g2 | new1_fig1m_run_c8 | 8714 |
| L2 s4 | tokyo107 g3 | new1_fig1m_srv107_g3 | new1_fig1m_run_c9 | 8715 |

(shiga g0/g3 未占用 — tray 实验在用。runner 全部跑在 shiga 本机,
远端只跑 model server; 日志: `../logs/new1_fig1m_{srv,run}_*.log`。)

## step-16 全矩阵可行性

两 cell (共 10 集) 端到端 ~13 分钟 (含建env+载模型)。全矩阵 30 runs × 10 eps
= 300 集 ≈ 6 倍集数 × 每集略长 (L0/L2 步数更多), 两张卡按 run_full.sh 的
"同卡先 nomem 后 mem"配对设计跑, 估计 5-10 小时, 一夜可完。
