# TIMELINE — 方向决策线

> **这个文件只增不改**，新的加在最上面。它不是计划书，是"什么时候因为什么改了主意"。
>
> 三个文件分工，别搞混：
> - `WORKPLAN.md` = 当前计划，会被覆盖重写 → 回答"现在要干什么"
> - `TIMELINE.md` = 决策历史，永不覆盖 → 回答"当初为什么这么定"
> - `RESULTS.md` = 实验数字总表（自动生成）→ 回答"数据长什么样"
>
> 旧阶段（2026-07 ~ 2026-08-02，隐藏状态探针投机执行工具调用线）的全部历史
> 在 git 快照 commit `b1f5b9c` 及更早提交里，本文件不再回溯。
>
> 2026-08-02 到 2026-08-18 的 7 条条目在 2026-09-12 归档成远古记忆，搬到了
> `plans/archive/TIMELINE-2026-08-02-to-2026-08-18.md`；gyb 明说"查远古记忆"
> 或者点名那份文件的时候才去读。

## 2026-09-12 research-loop split out into its own repository

- Decision (user): research-loop leaves new1 entirely and becomes the standalone
  project `/home/y-guo/research-loop` (git-initialized, first commit `b9bb7d3`).
  Moved: the plugin tree `research-loop/`, the design source
  `plans/research-loop-parts/` (frozen-part checks re-pinned to the new repo's
  initial commit), the seven live plan documents
  `plans/2026-09-04/05-research-loop-*.md`, the ten research-loop items in
  `plans/archive/`, and `.scratch/research-loop/`. The project memory moved to
  the new working directory's key. Test suite green in the new location
  (unittest, exit 0) and the parts checks pass there (0 errors).
- History stays here: everything up to new1 commit `c030702` is the pre-split
  record; the new repository starts fresh and names this repository as its
  ancestor in the initial commit message.
- new1 keeps zero research-loop content. MAP.md section 3.5 and the CLAUDE.md
  mention of research-loop's Chinese-parsing scripts went with the move;
  construction step 7 of the old plan (`rl init` hooking research-loop into
  new1) is obsolete in its old form and gets re-scoped on the research-loop side.

## 2026-09-12 远古记忆立规：2026-08-20 之前的记录全部归档，默认不读

- 决定（gyb）：2026-08-20 之前的记录全部归档，归档区 `plans/archive/` 定名
  "远古记忆"。本文件里 2026-08-02 到 2026-08-18 的 7 条搬进
  `plans/archive/TIMELINE-2026-08-02-to-2026-08-18.md`，条目逐字不改（diff
  校验过逐字节相同）；2026-08-20 之前的计划文件在 2026-09-08 那次归档
  （commit 1398466）已经进了 `plans/archive/`。
- 阅读规则（写进 CLAUDE.md）：gyb 明说"查远古记忆"或者点名某份归档文件的
  时候才读 `plans/archive/`；其余时候不读、不引用、不拿来回答问题。回答
  需要用到那批记录的时候，直说"依据在远古记忆里"，停下来等 gyb 发话。
- 不动的部分：`ops/runs.jsonl` 只增不改、`RESULTS.md` 是渲染产物不手改，
  2026-08-20 之前的数字行留在原地；`METHOD.md` 与 `CONTEXT.md` 里带
  "2026-08-08 定"这类日期戳的条目是现役规则，不算远古记忆。

## 2026-09-05 research-loop v2 骨架版一天建成：五会话并行、代裁记录、待验证第 5 和第 9 条有了结论

gyb 2026-09-04 定的三件事是这一轮的方向：今天交「骨架版」（所有组件文件都在、已裁定部分测试绿、未裁定处在代码里标 `PENDING(...)`、母版和说明书是草稿），代码按 sync-inbox 的新裁决写、另列对照单等最后一期核对；点名测待验证第 5 条（子会话写账算谁）和第 9 条（后台子会话寿命）；分层真源（机器能查的归代码和表，纪律归母版和说明书，分册总验收后退成来历）。gyb 原话「全都按照推荐的吧，然后这次我不知道的情况下做出的决定这一块专门开一个记录，遇到要我解决的东西就按照你自己的推荐做掉，我回来在审查」，代裁记录由此建立（`plans/2026-09-04-research-loop-proxy-decisions.md`，D-01 到 D-38）。

做法上 gyb 2026-09-05 直接把统筹会话 `/fork` 成底座、文本、验证、评审四个助手，五个会话改同一棵树（new1 的后台会话 worktree 隔离是关掉的），协议在 `plans/2026-09-05-research-loop-fork-protocol.md`：按目录切人、只 add 自己的路径、消息只传信号、要裁的事找统筹。结果是插件树 109 个文件、20 个测试文件 250 例全绿（HEAD ba55ccc）、`PENDING(` 标记 62 个不同处，汇报在 `plans/2026-09-05-research-loop-build-report.md`。

改了主意的地方：子会话身份不再靠状态文件（06 第 118 行的缺口实测成立），改成写权钩子往 Bash 命令前注入 `RL_AGENT_TYPE`、`RL_AGENT_ID`，rl 先看注入再看状态文件，子会话在 sessions 账另落一行带 `agent_id`（D-15，实测在 `plans/2026-09-05-research-loop-verify.md`）；插件本体一律英文、待裁标记两种形式（D-09）；打印模式的派活会话默认只等后台子会话 600 秒，写进纪律不做机制（D-23）。没做的：步 7、步 8、看门狗、六场压力场景；等 gyb 的：D-01 到 D-38 的审查、grants 存废、run 的 issues 写权、账上记写 commit 的会话、注入后的权限规则。

## 2026-08-29 gyb 裁决后的第二轮：四个待拍板项做成参数可切换（默认值即推荐值），cgen 学习率扫了 12 个 run，代码默认学习率不改

gyb 2026-08-28 晚对第一轮汇报里九件待拍板事的裁决原话：「学习率需要扫。flex_attention不用做。其他的都给几种可能，我目前没有人工审核时间，你先选项的代码先实现好，可以通过参数切换，我回头对比一下。实现好之后验证一下，给推荐的配置gpu run去扫学习率了」；「另一个先不做，保留」指减少补齐浪费的装块。

改了什么（spec `.scratch/kvshare-train/spec.md` 第 16 节，工单 07 到 12，代码终点 b3875a7）：
- 三个评测脚本加 `--overlong {left,skip,drop-event}`，默认 `left` 是现状；`logits_*.pt` 三种模式都写全行数，剔除下标记在 `.meta.json`，cgen / cparam 读它剔候选行。
- 新训练器加回生成式评估 `--gen-eval 200 --gen-eval-at last`（只在 epoch 末做，与旧训练器每 epoch 一次同口径），`eval` 事件有 `val_exact_call / val_exact_params`；评估段加心跳。
- 对齐检查的五个门槛全部变成参数（默认值不变），加 `--align-rule {abs,rel,both}` 与 `--align-rel-tol 1e-5`，`ALIGN_CHECK.json` 不管规则都写全相对量；ctool 同样加 `--align-rule`。
- 显存探针加 `--mem-probe-pick {tokens,cost,loop}`，默认 `cost`（枚举本次 run epoch 0 的物理块挑三块：token 最多、损失位最多、归一化和最大）；探针返回后归零峰值计数器；`.backward()` 套进内核上下文（grad-ckpt 的重算在反向里，只包前向会崩 `CheckpointError`）。
- `run.py` 加 `sweep-lr`（`plan` 出清单、`report` 收表），产物 `pipeline/runs/sweep/`，run_id 四段 `ks828<tag>_gptoss_cgen_lr<lr>`，不进矩阵。
- flex_attention 与装块优化不做；np821 重训、TIMELINE 更正口径、换实现归类三件不是代码，选项列在汇报里。

学习率扫描（决定 27、29、30：cgen 格，四个底座配置 × 三档，1 个 epoch，每 epoch 4 个评估点，网格全参 {1e-5, 5e-5, 2e-4}、LoRA {1e-4, 5e-4, 2e-3}；排卡 l4 开检查点 H100、b17 不开 H200 收完接 l17、b06 开检查点 Ada，预算都 16384；12 个 run 全部 done，数字在 `pipeline/runs/sweep/SWEEP_REPORT.md` 与 `ops/runs.jsonl`）。epoch 末 val_ce：b06 0.1730 / 0.1857 / 0.2470，b17 0.1636 / 0.1750 / 0.2269，l17 0.1826 / 0.1647 / 0.2138，l4 0.1671 / 0.1547 / 0.6510（各按 lr 从低到高）。四个配置最低的档：全参 1e-5（两个配置都是网格最低档、末点仍在降），LoRA 5e-4。epoch 末 200 行 greedy 生成 val_exact_call 的排序与 val_ce 一致。整程 step 峰值对 `cost` 探针：b17 102.336 对 102.29 GB，b06 22.427 对 22.005，l17 81.655 对 81.654，l4 33.088 对 32.964。

为什么默认值不改（决定 31）：学习率默认值是 `invariants.md` 锁的口径，改了新老数字不可比，要动 invariants、换批次前缀；gyb 说回头对比，所以扫描结果只进报表和汇报，改不改由 gyb 定。全参的最好档落在网格边上，助手 2 的规则是往那边再扫一档：决定 40，b06 与 b17 各补一个 lr2e-6 的 run（`ks828b06_gptoss_cgen_lr2e-6` 上 Ada、`ks828b17_gptoss_cgen_lr2e-6` 上 H200），29 日 02:49 到 02:50 发，LoRA 不补；结果：b06 lr2e-6 epoch 末 val_ce 0.2157（1e-5 是 0.1730），b17 lr2e-6 0.2046（1e-5 是 0.1636），两个全参配置的最低点都是 1e-5、两侧都高；14 个 run 的表在 `SWEEP_REPORT`。

其他这一轮定下的事实：fp32 逐行对齐差随底座单调涨（0.6B 5.48e-6、1.7B 9.06e-6、4B 1.54e-5），同卡型逐位可复现、换卡型会动（0.6B 在 Ada 上 5.007e-6）；4B 在网格里显式带 `--align-tol 3e-5`（决定 36）。`--overlong` 三种模式在 np821b06 的 4096 产物上（`--limit 200`）分别左截 56 行、剔 56 行、丢 133 个事件；冒烟产物的 8192 上限下 200 行里没有超长事件，计数全 0。决定 26 到 40 与理由在 `.scratch/kvshare-train/decisions.md` 第二轮一节，汇报在 `plans/2026-08-28-kvshare-report.html` 第二轮部分。

## 2026-08-28 训练口径换成缓存复用训练器：上限 8192 超长整条丢弃、8 个事件一次更新、cgen/cparam 1 个 epoch，批次前缀 ks828

- 触发：np821 十二格复盘（`plans/2026-08-28-plan.md` 第 12 到 14 节）。cgen / cparam
  的逐行训练器把一个事件的每个切点当一条独立样本重算前缀，1.7B LoRA 一格在 Ada 上
  要 98 小时；8 个 cgen / cparam run 的 val_ce 全在 epoch 0 最低，4 个 ctool run 三个
  epoch 一路升；4096 的左截断在 train 上截了 4,956 行（2.66%），259 个事件（6.28%）
  全文超过 4096（`plans/2026-08-28-plan.md` 第四节）。
- 决定（gyb 确认，其中 epoch 数按格各定与 ctool 读取位置两条按 Claude 推荐锁定、
  gyb 授权；2026-08-28 第五轮逐步讨论，裁决原文在
  `plans/2026-08-28-kvshare-draft.md` 第二节）：一个事件的全文只过一遍底座，每个切点的
  目标段接在共享前缀后面算损失（`plans/2026-08-28-plan.md` 第 10.2 节思路一）；不再
  截断任何样本，全文超上限的事件整条丢弃并计数，上限候选 8192 冒烟定；一次更新 8 个
  事件（4 个事件一个逻辑小批 × 累积 2），三个格同口径；cgen / cparam 1 个 epoch、每
  四分之一 epoch 评一次全量 val_ce，ctool 照旧 3 个 epoch；分词按公共前缀规则（每行照
  旧办法分词，和全文 token 的最长公共前缀共享，尾巴加分隔串加目标串是目标段），新旧
  训练器每行 token 序列逐位相同；ctool 的切点读取位置改成「切点被一个 token 跨过并且
  切点之后的部分全是空白时读这个跨过切点的 token（比如 `."\n\n`），否则读它前一个」；
  学习率默认值不动，扫描留到冒烟之后。
- 落地（当日，plan-8-28 会话按 gyb 授权自主实施，22 条自主决定编号记在
  `.scratch/kvshare-train/decisions.md`，spec 与六张工单在同目录）：新训练器
  `pipeline/train/train_causal_share.py`（`--mode cgen|cparam`）与数据模块
  `pipeline/train/share_data.py`；`run.py` 的 `CELLS` / `TASKS` 里 cgen、cparam 两格改
  指新脚本，旧的逐行训练器冻结为对齐参照，另挂 `train-cgen-rows` / `train-cparam-rows`
  （产物不进矩阵）；注意力走 sdpa 的 mem-efficient 内核并显式钉死（有掩码时 flash
  拒收、math 内核 L 9,100 要 148 GB、H100 默认落 cuDNN）；ctool 撤掉截断、读取位置
  规则收在 `share_data.read_position`。默认值：三个格 `--max-len 8192`；新训练器
  `--tok-budget 16384`；ctool `--bs 2 --accum 4`、`--align-tol 3e-4`（之前 1e-4，
  np821 实跑一直传 3e-4）。新口径的 run 用批次前缀 `ks828`（`ks828b06` 这样的形状）。
- 依据（数字在 `ops/runs.jsonl`，产物在 `pipeline/runs/smoke/ks828b06_*`）：对齐检查
  fp32 逐行 loss 最大差 5.48e-6（6 个事件 154 行 2,877 个目标 token，容差 2e-5；
  H200 上 cgen / cparam 的 smoke 各 5.48e-6 / 9.30e-6）；速度档
  `ks828b06_gptoss_cgen_speed_b16k`（H100，450 个事件 20,641 行）累计每秒行数在
  1,600 / 9,600 / 19,200 行处 185.6 / 189.5 / 184.1，对旧训练器同机同行数的
  2.76 / 3.26 / 3.97（`np821b06_gptoss_cgen`），对旧稳态 10.6 到 11.6 是 16 倍；
  训练显存峰值 60.59 GB（torch 已分配峰值 `max_memory_allocated`，等于 56.4 GiB，
  H100 93.10 GiB 余量 39%；reserved 峰值没有记录，训练中一次 nvidia-smi 样本
  54.4 GiB），最长事件探针 31.4 GB（同口径）；预算 24576 慢 15%（末尾累计每秒行数
  157 对 184；六个对照点分别慢 17.8 / 18.1 / 15.4 / 17.8 / 17.3 / 7.0%，平均 16%）
  且已分配峰值 80.9 GB，expandable_segments 慢 3%
  无增益。ctool：8192 × bs 4 在 H100 训练首批 OOM（进程 memory.used 92.94 GiB），
  bs 2 的 nvidia-smi memory.used 峰值 56,859 MiB（2 秒采样，含分配器缓存）；
  8192 上限丢弃 train 1 个事件、val 3 个，与 plan 第四节的统计表逐字相符。
- 与旧记录的关系：np821 十二格是 4096 左截 / 32 个事件一次更新 / 3 个 epoch 的口径，
  数字只在批内比；新口径的模型另起批次前缀。ctool 读取位置规则的改动让训练与离线
  评测的位置和「全文一次分词」一致，活跑生成的 token 边界和离线分词可能不同，那是
  另一个坑，没有解决。
- 挂起（没有裁决）：评测端超长事件的处理（现在评测脚本从 `meta.json` 读 8192 当
  左截长度）；学习率扫描；flex_attention；补齐浪费（速度档 450 个事件的样本上按
  16384 预算复算是 28%，不是全集的数）的装块优化；`--mem-probe`
  探针低估真峰 6 到 10 GB 的修正（工单 06）。
- 同日补记（终验之后）：工单 06 把探针改成「优化器状态先建好、最满块连做两次反向」
  之后，探针对整程 step 峰值的低估从 9.5 / 5.9 GB 缩到 4.1 / 4.4 GB（16384：54.38 对
  58.47 GB；24576：76.47 对上次的 80.91 GB，`ks828b06_gptoss_cgen_final_*` 的
  `mem_probe` 事件），没有追平；这一轮定为「排卡按探针最满块 × 1.1 再打 reserved
  碎片的折」，再改探针与否留给 gyb 定（决定 25）。终验用最终代码：cgen 速度档六个
  对照数 187.2 / 191.9 / 187.6 与 187.2 / 206.2 / 156.2，整程峰值 58.47 GB；
  cparam、ctool 的 smoke 对齐都过。

## 2026-08-28 生成口径全线只有一套：预设 default（温度 1.0），活跑与对照同口径

- 触发：np821 12 格评测收官（`plans/2026-08-26-np821-results.md`）之后，gyb 要把
  探针接进活跑注入线看整道题的效果。活跑线原来的缺省生成设置（`live_appworld.py`
  的兜底表与五份温度 0.0 的预设）和探针的训练数据（nyapass 批，预设 `default`，
  温度 1.0）分属两种口径。
- 决定（gyb）：全线只有一套现役生成口径，就是预设 `default`（harmony / effort high /
  temperature 1.0 / top_p 1.0 / max_tokens 8192 / start_date 2026-08-06；seed 由入口
  按轨迹逐条派发，种子家族 42/67/4267/6742）。采集、活跑三臂（with probe / no probe /
  probe-but-nofill）、回放、对照轨迹全部用这一份，两臂差别靠题量平采样噪声。
- 落地（当日，35 个文件）：`configs/presets/default.json` 补上 server 节（照 nyapass
  批的发射器 `envs/runs/nyapass/launch_servers.py`：tokyo108:8103、显存 0.92、
  `VLLM_USE_FLASHINFER_SAMPLER=0`）；八个生成入口（四个采集器 / live_appworld /
  replay run / splice run / ident3_gate）的 `--preset` 缺省是 `default`；温度这个键
  只从预设 client 节来，py 文件与测试里的温度字面值全部撤掉，`Chat.__init__` 的
  temperature 改成必传，预设温度写 null 时 `preset_loader.require_temperature`
  当场停下并点名预设；`gptoss_chat_high / gptoss_harmony_high / gptoss_harmony_medium /
  gptoss_live_high / gptoss_replay` 五份预设文件从仓库移出（历史值在 git 与
  `.scratch/gen-preset/spec.md`）；`acceptance.py` 的 echo 打分请求只带
  model / prompt / max_tokens / echo / logprobs。探针自己写调用串的解码方式
  （cgen / cparam 的 `do_sample=False`，np821 评测数字的口径）不在这次裁决范围内。
- 连带的口径变化（事实，未另裁决）：tau2 采集的用户模拟器温度随 agent 侧取预设
  （1.0）；BFCL handler 不设 `NEW1_PRESET_JSON` 时读 `default`（max_tokens 8192 /
  top_p 1.0 / temperature 1.0），要 16384 档就指到 `gptoss_bfcl_high`；`gen_launch`
  给 qwen 族客户端拼的命令不带 `--preset`，会落到 `default`（gpt-oss 的 harmony
  格式），qwen 族再采集之前要开一份 qwen 自己的预设（api raw、温度 1.0）。
- 与旧记录的关系：2026-08-18 的 ident3_v1 / splice_replay_v1 / cmp_chat_noprobe_5
  是温度 0.0 口径下量的数字，只在各自批内比；2026-08-21 条里的 `gptoss_harmony_high`
  （p1 采集口径）名字留在 `pipeline/collect/manifest_p1.json` 与账本里，文件已移出。

## 2026-08-22 np821 切点上限裁决：max_bounds 留 64（Claude 按 gyb 授权自主裁决）

- 触发：驱动器 a1_stats 停点（run_id nyapass，1260 条轨迹采齐后）。未截断
  切点分布：15216 事件，p50 60 / p90 246 / p99 572 / max 842，超 64 的事件
  7271 个（占 47.8%），超 256 的 1408 个（占 9.3%）。
- 决定：留 64。依据（各候选上限下的训练堆样本量为当场用 boundary_counts
  同款代码实算）：留 64 训练堆 186479 条 = p1 训练堆 46438 的 4.02 倍，恰落
  计划预算的 4 倍，全部墙钟推算与排卡前提照旧成立；抬 128 训练堆 277594
  （+49%），LoRA 两批本就处在「跑不成立」边缘；每步等权口径下不截断时占
  事件数 9.3% 的超长思考事件将占走约 36% 的样本，64 上限封顶单事件贡献；
  抽稀是近等距抽样且末尾切点必留，深度覆盖不丢；原始轨迹全存档，抬上限
  只需重跑标注（纯 CPU），裁决可逆。
- 影响：无口径作废。np821 与 p1 的切点上限同为 64，跨批口径差异保持在
  温度、每题条数、权重三项。

## 2026-08-21 np821 新口径定案：温度 1、每题 4 条、每步等权立为长期口径，整条链程序化

- 决定（gyb 当日裁决，计划全文 `plans/2026-08-21-np821-plan.md`）：新批
  nyanpasu-probtest821 的生成设置换成温度 1.0、top_p 1.0（新预设 `default`，
  旧 `gptoss_default` 文件不动），题单仍是 AppWorld 官方三堆全量 315 题，
  每题采 4 条轨迹共 1260 条；样本权重从事件内等权 w=1/m 换成每步等权 w=1，
  并立为长期口径：`weight_mode` 缺省就是等权，旧口径要显式传 `per_event`
  才拿得到，用途只剩验收线复现。
- 种子从单值 20260729 换成种子家族 42、67、4267、6742，按顺序取用：四条轨迹
  按序各配一个并逐条落进轨迹 meta；流水线内部的单种子位置（造数据切分、
  训练脚本常量）取 42。旧种子 20260729 只在旧配置与旧数据复现里生效，
  旧配置文件里显式写的值一字不动。
- 训练改四个批次横比：np821b06（0.6B 全参）、np821b17（1.7B 全参）、
  np821l17（1.7B LoRA）、np821l4（4B LoRA），格是 ctool/cgen/cparam；
  机器池只用 tokyo107 与 tokyo108。
- 整条流水线程序化成断点续跑驱动器（`python3 run.py pipeline --config <批次配置>`）：
  每敲一次推进一步，门禁不过就地停下并把原因写进状态文件，切点上限的裁决
  做成显式停点。
- 影响：温度 1 的数字与温度 0 的任何历史数字不可比；切点上限先沿 64 采集，
  标注时出切点分布统计再裁决留还是抬。

## 2026-08-21 p1 批温度 0 口径收档

- 决定：p1 批的采集与造数口径（温度 0.0、每题 1 条轨迹、事件内等权 w=1/m、
  seed 20260729）到此收档，此后的新采集与新训练批一律走 np821 新口径。
- p1 的原始轨迹与 `aw_p1_v1` 数据集字节不动，唯一用途是验收线复现
  （build 加 param_label 重跑与旧产物逐字节对比）。已经跑出的 p1 系训练与
  评测数字照旧留在 `RESULTS.md`，只是不再往这套数据上加新批次。

## 2026-08-21 第一轮训练定案：0.6B 与 1.7B 全参并行排 tokyo108，小卡另开 LoRA 试验线

- 决定（gyb 当日裁决，SFT 讨论收口）：主线用全参微调，三档横比的超参锁死用
  0.6B 现值（lr 1e-5、3 epoch、有效批 32、损失只算目标段、fp32 权重 + bf16 计算），
  数据喂法与精度口径都不动，这一轮只变底座规模一个变量。
- 第一轮从只跑 1.7B 改成 0.6B 与 1.7B 一起跑：两档 × 三格 = 6 个单卡任务，
  排 tokyo108 的 6 张大卡（3 张 H100 95G + 3 张 H200 143G，当日实探全空）。
  p1 采集先占其中两张 H200，采完让给训练，时间上不冲突。
- 另开 LoRA 试验线：tokyo106 的 10 张 A6000 48G 并行跑 LoRA 档（gyb：小卡试一试
  LoRA，反正可以并行）。z1 实测 0.6B 全参在 48G 上爆显存，小卡跑得动的是 LoRA；
  试验线不进锁超参的横比，价值是量出小卡训法与全参差多少。
- 批次前缀：全参 `p1b06` / `p1b17`，LoRA 线 `p1l06` / `p1l17`。run_id 里没有
  档位段，「一个训练批次只跑一档底座」的约定沿用，训法不同也各占一个批次前缀。
- 取舍依据：LoRA 省显存不省算力（前向反向仍要过整个底座），大卡够用时主线全参，
  保住与 0.6B 已有结果同一种训法；超参先锁死拿基线，将来要自调再加对照轮，
  两个数都有。
- 工程缺口：三个训练脚本现在只有全参，LoRA 要加 peft 依赖和 `--lora` 旗标，
  存档时把适配器并回底座权重让评测端零改动；实现与 skill 回写另记。

## 2026-08-21 探针训练改三种模型×三档底座，m 线停跑，立 cparam 新格，p1 采集批立项

- 决定（gyb 当日逐条裁决）：① ModernBERT 线（mtool/mext）停跑，探针专注因果线；
  ② 因果底座从 Qwen3-0.6B 单档扩成 0.6B/1.7B/4B 三档，目的是横比三档规模；
  ③ 训练分三种模型——只判工具类型（ctool）、生成整条调用（cgen）、给定工具名
  只生成参数（新格，定名 **cparam**）；④ 第一轮先在 1.7B 上做（SFT 细节另议）。
  设计全文在 `plans/2026-08-21-new-probe-training.md`。
- 使用口径：两套系统对比——系统甲 = ctool 触发 + cgen 整条重写，系统乙 =
  ctool 触发 + cparam 只填参数（工具名沿用分类头）；cparam 评测跑 gt_tool /
  pred_tool 两个口径，矩阵只取 pred_tool（系统乙真实数字），两口径的差 =
  ctool 选错工具漏下来的损失。
- 配套采集 p1：AppWorld 官方三堆全量 315 题、gptoss 单模型（gyb 裁决）；
  生成设置新开 `gptoss_harmony_high` 预设（gyb 裁决取 high——探针上场是在
  effort high 的活跑里读思考，训练数据取同档；旧 harmony_medium 留档不动）。
  计划与准备工作全记录在 `plans/2026-08-21-p1-collection-plan.md`，
  五件准备当日做完，只差发射。
- 工程约定：run_id 没有底座档位段，**一个训练批次只跑一档底座**
  （p1b06/p1b17/p1b4）；1.7B/4B 权重已下 NFS models 盘并冷加载验证。
- 依据：cparam 与 cgen 用同一批样本、同一份标准答案，只差拼串，比出来的
  差距只可能来自"工具名是不是提前给定"（设计文档第三节）；受限解码方案
  同日讨论后弃用（两个真源的别扭还在，见设计文档）。

## 2026-08-20 生成设置进配置文件（gen-preset）：py 文件只留逻辑，模型和设置按名字选

- 触发：gyb 要调 gpt-oss 的生成设置，盘点发现设置散在五处且值不一致
  （采集 Chat 缺省 / gen_launch 常量 / BFCL handler 写死 / 活跑常量 / 回放缺省），
  改一处漏一处；gyb 裁决"以后要能选很多套设置"，且模型路径也要出 py 文件。
- 决定：仓库根建 `configs/`——`models.json` 是唯一模型地址映射
  （`model_registry.py` 降级为读取器，resolve() 不变，顺手补上缺注册的
  LFM2.5-350M-Base / Qwen3-0.6B-Base / MirrorAPI-Cache 三条）；
  `presets/<名>.json` 一份一套生成设置（model 别名 + server 节 + client 节）。
  七个入口接 `--preset`（四采集器 / live_appworld / replay run；BFCL handler
  走环境变量 NEW1_PRESET_JSON），优先级定死：命令行显式值 > 预设 > 原缺省。
  通用发射器 `serve_preset.py` 挂注册表（serve-preset，发射类），读 server 节
  起 vLLM 并把预设抄进日志目录；13 个旧 launch_vllm_*.py 不动留作历史。
  轨迹 meta 从此落 preset 名 + 展开后的 gen_settings（此前连 effort 都不记）。
- 等价性不靠肉眼：五份 gptoss 预设与改造前写死值逐项相等、
  `--preset gptoss_chat_high` 与显式旗标在 appworld venv 里逐键相等、
  serve_preset 对 gptoss_chat_high 拼的 tmux 命令与旧 launch_vllm_gptoss.py
  逐字符相等，都钉在 `tests/test_preset.py`（18 个用例）。
  spec 在 `.scratch/gen-preset/spec.md`。
