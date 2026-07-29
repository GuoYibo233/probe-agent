# 全量采集批次 v1（2026-07-29 发射）

三组任务并行采集，用途：探针训练数据 + C2-1 数据生成管线放量。
与另一个会话的任务隔离——本批次自建了三套 vLLM 服务，未使用 8102。

## 服务（tokyo108，本批次专用）

| 模型 | GPU | 端口 | tmux session | api 模式 |
|---|---|---|---|---|
| qwen3.5-27b | H200 GPU3 | 8101 | `new1_srv_q35_t108g3` | raw（自拼模板，`<think>` 不丢） |
| gpt-oss-120b | H200 GPU5 | 8103 | `new1_srv_gptoss_t108g5` | chat（harmony，取 `message.reasoning`） |
| qwen3.6-27b | H100 GPU0 | 8104 | `new1_srv_q36_t108g0` | raw |

两个 Qwen 服务挂了**双 served-model-name**（别名 + 权重全路径），因为 BFCL 用全路径当
model 名发 `/v1/completions`，只挂别名会 404。

启动脚本：`envs/serve_logs/launch_vllm_trio.py`

**踩到的坑**：Qwen3.6-27B 是 Mamba 混合架构，H100（95G）上默认 `max_num_seqs=1024`
超出可用 Mamba cache 块数（612），引擎初始化直接失败。降到 `--max-num-seqs 256`
即可（H200 上不会触发）。

## 三组任务

客户端全部是纯 CPU 的 HTTP 进程，跑在 **tokyo106** 的 tmux 里，不占显存。
日志目录 `envs/runs/logs/`。

### 1. AppWorld dev 全量 57 题 × 3 模型
- `--max-steps 30`（校准批用的 20，怀疑准确率低有一半是截断造成的，先排除这个混淆因素）
- 每模型 4 分片并发，session `new1_aw_<M>_s<0..3>`
- 输出 `envs/runs/full_appworld/{q35,q36,gptoss}/appworld_<task_id>.jsonl`
- 完成判据：每模型 57 个文件，每个含一行 `{"type": "final"}`

### 2. TALES 多房间加难版 × 20 seed × 3 模型
- 难度串 `numLocations=6, numIngredients=3, numDistractorItems=10, includeDoors=0, limitInventorySize=0`
- seed 101–120，`--max-steps 60`，每模型 2 分片，session `new1_tl_<M>_<a|b>`
- 输出 `envs/runs/full_tales_L1/{q35,q36,gptoss}/tales_cookingworld_s<seed>.jsonl`

**为什么是这套参数**：单房间版三个模型都能打穿，且存在死局——菜谱要求烧烤但
1 个房间里没有后院/烤架，游戏无解。多房间同时解决"太浅"和"死局"两个问题。
60 步是实测定的：40 步下 gpt-oss 顶格截断（score 44），60 步给足空间后
q35 两局全通（10/20 步）、gpt-oss 三局通一局——难度上来了但没打死，模型阶梯保住了。

### 3. BFCL multi_turn_base 全 200 题 × 两个 Qwen
- `bfcl generate --model Qwen/Qwen3-32B --local-model-path <权重路径> --skip-server-setup`
- `LOCAL_SERVER_ENDPOINT=tokyo108` + `LOCAL_SERVER_PORT=8101|8104` 决定连哪个服务
- session `new1_bfcl_<M>`，输出 `envs/runs/full_bfcl_<M>/Qwen_Qwen3-32B/multi_turn/`
- 完成判据：结果 json 各 200 行

`--skip-server-setup` 是关键，漏了 bfcl 会自己起 vLLM 占卡。

## 脚本改动

- `collect/run_appworld.py`：加 `--shard-id/--num-shards/--resume`；`--n 0` = 整个 split；
  分片时 experiment_name 自动带 `_s<i>` 后缀，避免并发时 AppWorld 实验目录互踩。
- `collect/run_tales.py`：加 `--resume`（跳过已写完 `final` 的 seed）。

两个改动都向后兼容，不带新参数时行为与之前一致。

## 结果（三组均已 100% 完成）

汇总脚本 `collect/summarize_full.py`，与 CALIB_v0.md 同口径。

| 格子 | n | acc | 思考中位/步（字符） | 调用/轨迹 | 步数均值 |
|---|---|---|---|---|---|
| AppWorld dev × q35 | 57 | 0.21 | 378 | 20.3 | 20.5 |
| AppWorld dev × q36 | 57 | **0.63** | 261 | 17.6 | 17.6 |
| AppWorld dev × gptoss | 57 | 0.35 | 387 | 13.7 | 13.8 |
| TALES L1（6 房间）× q35 | 20 | 0.90 | 674 | 25.1 | 25.1 |
| TALES L1 × q36 | 20 | **1.00** | 835 | 20.5 | 23.2 |
| TALES L1 × gptoss | 20 | 0.40 | 2356 | 46.9 | 46.9 |

BFCL multi_turn_base 官方状态比对评分（`bfcl evaluate`，200/200 全跑完）：

| 模型 | acc | 评分目录 |
|---|---|---|
| qwen3.5-27b | **70.00%** | `full_bfcl_q35_score/` |
| qwen3.6-27b | 59.00% | `full_bfcl_q36_score/` |

### 判读

- **AppWorld 是这批最成功的格子**。步数 20→30 之后 q36 从校准时的 0.40 升到 0.63
  进了目标带，三模型 0.21 / 0.35 / 0.63 阶梯干净，调用链 13.7–20.3 调用/轨迹，
  比校准批（12.2）还肥。探针与 C2-1 的主力数据源确认成立。
- **q35 在 AppWorld 上 0.21，加步数没救回来**——说明它的失败不是被截断，是真做不动
  difficulty-2。作为阶梯低端点有用，但别指望调参能把它拉进带内。
- **TALES L1 对两个 Qwen 太浅**：q36 二十局全通（1.00）、q35 0.90，"被打穿"的问题
  没解决，只对 gpt-oss（0.40）成立。死局 bug 确实消除了（多房间后后院/烤架可达）。
  → 因此追加了 L2 档，见下。
- **gpt-oss 在 TALES 上思考量爆炸**（中位 2356 字符/步，是 Qwen 的 3 倍），
  步数也顶到 46.9，但准确率只有 0.40——想得多不等于做得对。这个"高思考低成功"
  的组合对投机研究反而是肥肉。
- **BFCL 上 q3.6 反而低于 q3.5（59% vs 70%）**。别急着当成模型能力结论：BFCL 对两个
  模型套的都是 `Qwen/Qwen3-32B` 这个 handler 的聊天模板，q3.6 的模板差异可能被
  抹掉了。要下结论得先确认模板对不对。

## TALES L2 加难档（追加）

L1 没解决"太浅"，所以按最初设想补了第二档。

- 难度串 `numLocations=11, numIngredients=4, numDistractorItems=10, includeDoors=0, limitInventorySize=0`
- 同样 seed 101–120，`--max-steps 80`（比 L1 的 60 再放宽，避免准确率被截断压低
  变成假难度），每模型 4 分片，session `new1_tl2_<M>_<a..d>`
- 输出 `envs/runs/full_tales_L2/{q35,q36,gptoss}/`
- 难度生效已实证：同 seed 下可达房间数 6 → 11，菜谱食材 3 种 → 4 种

### L1 vs L2 对照（各 20 局，全部跑完）

| 模型 | L1 acc | L2 acc | L1 思考中位 | L2 思考中位 | L1 调用/轨迹 | L2 调用/轨迹 |
|---|---|---|---|---|---|---|
| q35 | 0.90 | 0.55 | 674 | 972 | 25.1 | 52.5 |
| q36 | **1.00** | **0.65** | 835 | 1493 | 20.5 | 45.5 |
| gptoss | 0.40 | 0.15 | 2356 | 3108 | 46.9 | 74.0 |

**L2 达成了目的**：q36 从饱和的 1.00 掉到 0.65，正落在 0.6–0.9 带内。
q35 到 0.55，略低于带；gptoss 0.15，这一档对它太难。

**两档合起来才是完整的旋钮**，别只留一档：
- q36 的可用档是 L2（L1 已饱和无区分度）
- q35 的可用档是 L1（0.90，L2 掉出带外）
- gptoss 两档都在带外（0.40 / 0.15），它在 TALES 上就是弱，不是调难度能救的

**L2 是全批次最肥的轨迹来源**：45–74 调用/轨迹、思考中位 972–3108 字符/步，
远超 AppWorld（13.7–20.3 调用、261–387 字符）。要长链条 + 长思考的探针数据，
优先用 L2；要模型阶梯干净的，用 AppWorld。

### 踩到的坑：gpt-oss 的 500 会带走整条分片

L2 的 gptoss shard d 跑到 s120 时被 vLLM 服务端 500 打断：
`unexpected tokens remaining in message header` —— harmony 解析器在模型思考
特别长时收不干净。异常直接冒泡，整个 shard 的剩余 seed 全丢。

已修：`collect/common.py` 的 `Chat.__call__` 加了 4 次退避重试（1/2/4 秒），
重试完仍失败才抛。补跑 s120 一次通过。**这个改动对所有环境都生效**，
以后长跑不会再因为一次服务端抖动丢掉整条分片。

## 待办

- BFCL 的模板问题（q3.6 用 Qwen3-32B handler 是否合适）值得单独查一次——
  q3.6 在 BFCL 上反而低于 q3.5（59% vs 70%），与 AppWorld/TALES 上的排序相反。
