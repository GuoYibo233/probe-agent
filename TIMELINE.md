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

为什么默认值不改（决定 31）：学习率默认值是 `invariants.md` 锁的口径，改了新老数字不可比，要动 invariants、换批次前缀；gyb 说回头对比，所以扫描结果只进报表和汇报，改不改由 gyb 定。全参的最好档落在网格边上，助手 2 的规则是往那边再扫一档：决定 40，b06 与 b17 各补一个 lr2e-6 的 run（`ks828b06_gptoss_cgen_lr2e-6` 上 Ada、`ks828b17_gptoss_cgen_lr2e-6` 上 H200），29 日 03 时发，LoRA 不补；结果见 `SWEEP_REPORT` 与汇报。

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

## 2026-08-18 三臂逐 token 同（ident3_v1）：活跑重发改用模型自己的 token id，5 题 × 10 遍量噪声

- 触发：gyb 要求把 chat baseline / no probe / probe-but-nofill 做到逐 token 同，5 题
  每题每臂 10 遍看结果。探针权重已删，nofill 臂用伪触发（每步第 5 个句尾切口开火、
  中断、按模型自己的 id 重发、什么都不塞）。
- 决定（实现层，计划 `plans/2026-08-18-ident3.md` §5 E1–E13）：活跑流带
  `return_token_ids`，开火重发 = 前缀 + 模型自己生成的 id[:k] + 单独编码的 NOTE，
  不再把文本整段重分词；head = 盖住句尾标点的最短 id 前缀、切口按起点计数（两者只看
  token 序列不看流分块——vLLM 有 stop 串时压 9 字符不吐、生产快时多 token 并块，
  块边界不是 token 边界）；步预算按留下的 id 算；发射前门禁核 chat 的
  prompt_token_ids 与 /render 逐 id 相等。
- 事实（`ident3_v1`，RESULTS.md；`…/runs/ident3_v1/IDENT3_REPORT.md`）：150 跑 0 失败；
  跨臂 prompt id sha 1780/1780 全等（三臂喂引擎的 prompt 逐 id 同已成立）；
  2175 对同题配对没有一对整题逐 token 全同，每题每臂 10 遍 10 条不同轨迹；首分叉在
  第 0 步的比例同臂对 chat-chat 137/225、noprobe-noprobe 144/225、nofill-nofill
  131/225，跨臂 chat-noprobe 308/500、chat-nofill 499/500、noprobe-nofill 496/500；
  成功 chat 14/50、noprobe 13/50、nofill 20/50；nofill 564 次中断重发里 534 次
  （0.947）逐位复现被丢弃的溢出 token。三臂并行打同一副本（批组成随时变）。
- 与上一条"服务端数值抖动当噪声"的关系：这批数字是那层噪声在整题上的量；同臂
  10 遍之间就已经条条不同，臂间比较只能靠题量。
- 未做：真探针下的活跑（要先重训探针）；nofill 与 noprobe 首分叉几乎全在第 0 步而
  同臂对只有六成——这个差别没有分析，先记事实。

## 2026-08-18 立项：塞法回放（splice_replay_v1）——探针开火时结果怎么拼回去，先上帝视角量单步

- 触发：对比 with probe 重发 prompt 与 no probe 时量到重分词缝——NOTE 前导 `\n`
  与模型的 `.\n\n` 合成一个 token（换行切口 3558/3865 不齐，空格切口全齐）；
  顺势问"塞回去的方式"本身哪种最好。探针权重已删（`c1_gptoss_*`），活跑起不来。
- 决定（gyb）：不等探针，拿 5 条 chat baseline 轨迹做上帝视角回放：52 个单调用步 ×
  思考的 66/75/80/100% 句尾切口 × 十臂（思考内 4 种措辞 + system 预告 / 塞完强切
  正文 ×2 / 伪造整轮留思考 / harmony 原生 python 工具），每条只续一步，不跑到底、
  不 evaluate、不判预测对错。切口比例四个点是 gyb 定的。
- 裁决点 D1–D14 全在 `plans/2026-08-18-splice-replay.md` §6（缝修法 D5'：head 以
  空白结尾不加前导换行；n1 措辞改塞代码块原文 D13；`<|call|>` 是 eos、所有臂都停 D11）。
- 结果：`splice_replay_v1_srv`（RESULTS.md）；`…/pipeline/inject/runs/splice_replay_v1/SPLICE_REPORT.md`。
  上帝视角下退化的两种塞法（伪造整轮丢思考 = 跳到下一步；结果随下一轮到 = baseline）没跑。
- 未做：真探针下的活跑（要先重训探针）；把胜出塞法接进 live_appworld。

## 2026-08-18 裁决：服务端数值抖动当噪声，不再追逐字复现

- 触发：`cmp_chat_noprobe_5_srv4` 量了 7 个冷/暖分叉位——top-1/top-2 logprob 差全是
  0、0.125、0.25（bf16 logit 一格 0.125），6 个至少一态精确平局；两态同位 top-1
  logprob 差 ≤0.17 nat。分叉出在模型本来分不出高下的位上，是服务端 bf16 + 缓存
  命中数决定数值路径的属性，不是臂的属性；种子对 argmax 无用。
- 决定（gyb）：当噪声。不做"关前缀缓存 + 串行"的复现验证，不追两臂逐字同；
  两臂对比靠题量平这层噪声。上一条"没定案前不放量"的挂起解除。
- 未验、留档：同进程内"关缓存 + 串行"是否逐字稳定；跨进程重启是否稳定。

## 2026-08-18 五题实跑：no probe 与 chat baseline 的分叉来自前缀缓存状态，不来自端点

- 触发：`cmp_chat_noprobe_5`（tokyo108 单副本 gpt-oss-120b，`VLLM_SYSTEM_START_DATE`
  钉 2026-07-31；两臂各跑 test_normal 前 5 题，串行、一次只飞一个请求）。
- 事实：五题第 0 步 prompt token 数两臂全等（341/341/341/336/337）；3 题第 0 步
  输出就不同，2 题到第 2/3 步才分叉；成败 chat 3/5、no probe 3/5，题不同。
  同 prompt 反复打：暖缓存下 completions(ids) 与 chat 逐字同；清缓存后重发与
  暖时不同（13/13），冷/暖两态内部各自两端点逐字同（13/13）。chat 跑里第 0 步
  "异样"的三题正是当时那条 prompt 首次进服务（缓存未命中）。
- 决定：no probe 与 chat baseline 的口径对齐到此为止（渲染/采样/停止/切分已逐层
  同）；两臂要可比，下一步是把服务端状态压成一致（候选：`--no-enable-prefix-caching`
  + 串行；`VLLM_BATCH_INVARIANT=1` 对 MXFP4 起不来，作废）。没定案前不放量。
- 产物：`/net/.../pipeline/inject/runs/cmp_chat_noprobe_5/{chat,noprobe,analysis}`；
  台账 `cmp_chat_noprobe_5_srv{,2,3}`。

## 2026-08-18 no probe 的 prompt 改成 chat 端点同款 token id，三个臂定名

- 决定：no probe 与 chat baseline 之间凡是代码能对齐的差异一律向 chat 端点
  对齐：`/render` 不再走 jinja 出文本，改照抄 vLLM chat 端点的渲染直接出
  token id，驱动器把 prompt 以 id 列表发；chat baseline 的 `--reasoning-effort`
  缺省改 high、单题异常按题兜底。服务端批组成的数值抖动不在客户端能对的
  范围，留待发射时试 `VLLM_BATCH_INVARIANT`。
- 依据：同日逐层对 vLLM 0.26.0 源码并实测，jinja 文本路在两处与 chat 端点
  不齐（空 content 的 assistant 轮被 chat 端点整条丢掉；content 里字面
  `<|...|>` 标记被 completions 端点收成真特殊 token），任一触发后每步 prompt
  永久偏离；其余各层（采样参数、停止 token、输出切分、环境种子）对码相同。
  细节在 `METHOD.md` §2.1 与 §6-⑤⑥，裁判测试 `tests/test_harmony_render.py`。
- 定名：chat baseline / with probe / no probe（`CONTEXT.md`，同日）。
- 与旧记录的关系：2026-08-02 `awdiag_job.sh` 排查「活跑 noprobe 17.3% vs
  w0 28.6%」时上述两处与 `\n\n` 渲染差、chat 侧日期未钉都还在，那次数字
  不能归因到单一原因。

## 2026-08-08 探针线重启，定性为实验空间，METHOD.md 立为方法真源

- 决定：重启探针投机执行工具调用这条线，定性从"一个定死的方法"改成
  "一个实验空间"：主干循环定死，探针读什么、用什么模型、参数怎么来、
  触发怎么判、塞什么、何时塞、工具类型怎么分、一步之内何时收手，
  一共八根轴排队待试。方法规范落在根目录 `METHOD.md`（当日定稿），
  文档为准、操作向文档改齐。
- 定案要点：θ 永远手动给定，不给就拒绝启动；同设铁律与空注入对照立为
  机制验收；注入格式同效四判据（R1 到 R4）；工具类型暂不区分；
  旧阶段数字一概不作参照；现役 setting 是 gpt-oss-120b 加 AppWorld。
- 依据：2026-08-08 的 grilling 会话逐题定案，词汇当日收进 `CONTEXT.md`
  （同时把词汇表范围从监控/发射扩成全仓库）。

## 2026-08-02 清场，开新阶段

- 决定：旧阶段实验全部终止，结果不再需要。仓库只保留现役代码
  （`run.py` 注册表引用的 `pipeline/` `ops/` `envs/`）、部署好的环境、模型权重。
- 删除：NFS 实验产物约 116G（pipeline 训练/注入产物、new1_runs、bert_runs、
  bert_data、原始轨迹）；home 侧旧线代码目录、方向/论文文档、一次性发射脚本、
  文献 clone。删前先打快照 commit，git 里可回溯（NFS 数据除外，已不可恢复）。
- 保留：`envs/` 各基准环境（alfworld 数据挪到 NFS `envs/alfworld_data`，
  软链已改指）、mbert-env / cprobe-env / vllm-env 等虚拟环境、
  `/net/tokyo100-10g/data/str01_01/y-guo/models` 模型权重。
- 四本账（TIMELINE / DATA / runs.jsonl→RESULTS / WORKPLAN）清零重建骨架，
  记账机制（`ops/record.py`、`ops/gpu_jobs.py`、run.py 注册表）原样保留。
