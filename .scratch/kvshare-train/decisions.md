# kvshare-train 决定台账

这份台账由 8-28-assistant 会话代 plan-8-28 会话记录。plan-8-28 每做一个决定发一条消息过来，这里按收到的顺序原样追加并编号，不改写、不合并。每条的格式是「决定 N：<内容> / 理由：<理由> / 依据：<文件或数字>」。

## 决定 0：前置裁决的引用

前置裁决全部来自 `plans/2026-08-28-kvshare-draft.md` 第二节，一共七条，gyb 已确认或者授权按推荐锁定。这七条不在这里重复抄，只写引用：

- 2.1 上限候选 8192，冒烟定，组批按 token 预算动态定
- 2.2 更新单位：8 个事件一次更新，三个格同口径
- 2.3 学习率：默认值不动，冒烟之后扫描定
- 2.4 分词口径：公共前缀规则
- 2.5 epoch 数按格各自定（cgen 和 cparam 1 个，ctool 照旧 3 个）
- 2.6 ctool 的读取位置规则在第 5 步一起修
- 2.7 新训练器的其他设定（每四分之一 epoch 评估、step 日志加 lr 字段、累加器清零位置、切点抽样不采纳、注意力掩码形态）

目标见同一文件第一节，骨架与状态见第三节，第五轮实测事实见第四节。

## 决定 1

先把工作树里另一个会话留下的 36 个未提交改动（预设口径统一那批）和 plans/ 下三份笔记单独提交为 bd9a3d5，再开始本轮工作。 / 理由：ticket-run Phase 1 要求发射前工作树干净；提交前验过自洽（run.py selfcheck 74 任务全部就位；unittest 三个被改测试文件 Ran 87 tests OK）。 / 依据：.claude/skills/ticket-run/SKILL.md Phase 1 第 2 条；仓库 CLAUDE.md「发射实验前先 commit」。

## 决定 2

新训练器的小批损失照抄旧 cgen 的公式 Σw·ce / Σw，val_ce 同口径。 / 理由：数据里 w 全是 1.0（train 186,479 行、val 115,211 行，2026-08-28 清点），照抄公式等于草稿 2.2 的行等权，同时让对齐检查可以逐行逐公式对照。 / 依据：train_causal_callgen.py 第 494 到 505 行、第 259 到 291 行。

## 决定 3

新训练器按「换实现」处理，不算新格：cgen/cparam 格名不变，CELLS/TASKS 的两格改指新脚本 train_causal_share.py 加 --mode，旧的逐行训练器一行不改、冻结为对齐参照，另挂 train-cgen-rows / train-cparam-rows 两个任务。丢弃、上限、epoch 三项改动落在新训练器和 ctool 上。 / 理由：extending.md 第 113 到 121 行把「格没变、数据没变、评测脚本没改」归为新训法轴，不走 §3.1 新格清单；旧脚本冻结才能当参照。 / 依据：extending.md 第 113 到 121 行；gyb 原话「其他的改动针对所有」按格理解仍然成立（三个格都吃）。

## 决定 4

新训练器不做生成式评估（去掉 val_exact_call / val_exact_params 与 --gen-bs），不支持 --fire-head。 / 理由：每四分之一 epoch 评一次的时候生成式评估的成本不成比例，真正的生成评测由 eval_causal_call.py / eval_causal_param.py 做；开火头是另一根实验轴，不在这一轮。 / 依据：草稿 2.7 第一条；train_causal_callgen.py 第 300 到 320 行。

## 决定 5

事件级丢弃只看事件全文的 token 数是否超过 --max-len，不看拼接序列长度；拼接序列的显存由 --tok-budget 兜底。 / 理由：plan 第四节按全文 token 数统计的丢弃表（8192 丢 1 个、6144 丢 58 个）直接可用；评测脚本从 meta.json 读 max_len 的语义不变。 / 依据：plans/2026-08-28-plan.md 第四节的表。

## 决定 6

新训练器直接调用旧脚本的 build() 拿 tokenizer 与模型，只给 build() 加一个默认 None 的 attn_impl 关键字参数。 / 理由：pad=eos、截断方向、fp32 构造这些设定只有一份真源，对齐检查才有意义。 / 依据：train_causal_callgen.py 第 216 到 225 行。

## 决定 7

--tok-budget 默认 16384，--events-per-mb 4，--accum 2，--eval-per-epoch 4，--smoke 为 40 个训练事件 / 16 个评估事件；对齐检查默认抽 6 个全文 ≤ 2048 token 的 val 事件，fp32 容差 1e-4（ctool 的 ALIGN_TOL 就是 1e-4，草稿里写的 3e-4 是记错）。 / 理由：预算 16384 让一个 8192 前缀的事件（拼接约 9,700 token）独自成块、两个 4,000 token 的事件同块，冒烟量完再改；容差沿用仓库已有的那条线。 / 依据：train_causal_tool.py 第 76 行 ALIGN_TOL = 1e-4。

## 决定 8

ctool 的 n_bound_dropped 字段保留，含义改成「找不到读取位置的切点数」，预期恒 0；读取位置规则收在 share_data.read_position 一个函数，训练 collate、align_check、eval_tool.score_causal 三处 import。 / 理由：字段删掉会让读日志的下游改动面变大；三处各写一份必漂移。 / 依据：extending.md 第 137 行「四个训练脚本之间几乎不共享代码」那条的教训。

## 决定 7 更正

「3e-4 是记错」这句撤回。事实是代码默认 ALIGN_TOL 1e-4（train_causal_tool.py:76），np821 四张排卡表给 ctool 传 --align-tol 3e-4（ops/np821b06_placement.json:9-10），那条线比的是隐状态与 logits；本 spec 比的是逐行 ce，1e-4 是自定初值，等 design-attention.md 的 CPU 实测再定。「拼接约 9,700 token」改成「约 9,100 到 9,500」。

## 决定 9

速度对照按相同累计行数比三个点：1,600 / 9,600 / 19,200 行处旧训练器 2.77 / 3.94 / 6.24（np821b06_gptoss_cgen 的 train_log，tokyo108 H100，plan 12.10），三个点都要高；新训练器 step 日志的 ips 保留旧定义（本 epoch 累计行数 ÷ 已用秒数，train_causal_callgen.py:516），另加 ips_win 窗口值和 rows 累计行数；冒烟用 --max-events 450 盖住 19,200 行。 / 理由：2.75 是爬升段 1,600 行那一点的数，只比那一点会把爬升当成加速。 / 依据：plan 12.10、9.1。

## 决定 10

新口径的批次前缀是 ks828 加档位训法段（ks828b06、ks828l17），run_id 形如 ks828b06_gptoss_cgen，冒烟落 pipeline/runs/smoke/<run_id>_smoke；np821 前缀不再用于新口径。 / 理由：extending.md:165 一个批次一档底座一种训法都写进前缀，新口径与 np821 不同口径。 / 依据：extending.md:121、:165。

## 决定 11

分波改成 01 → {02, 03} → 主会话 GPU 对齐检查与冒烟 → 04；MAP.md 的四处改动全部挪到 04，01/02/03 只在报告里给文案；04 的 Blocked by 加「等冒烟裁决的 Comment」；工单 03 加「另需 design-attention.md 落地」；新训练器接 ops/heartbeat.py 三处（spec §7、工单 03 验收加 grep）；工单 03 的 CPU 冒烟产物改写 pipeline/runs/smoke/share_cpu_<mode>_smoke；spec §3.5 的上界改用 rules.py 的 MAX_BOUNDS = 64；§8 rows 任务 notes 加「产物不进矩阵」；§13 与工单 04 加 extending §5 的 #26、stage-commands 第 213 行 smoke 限额、批次前缀；工单 01 的自相矛盾句改掉。 / 理由：就是你 M3、M4、M5、L1 到 L5、N1 那几条。 / 依据：同你的审查。

## 决定 12

注意力实现按 8-28-assistant-2 的 design-attention.md 定死——形态 A（打包一次前向）加 sdpa mem-efficient 内核，训练/评估/对齐三处前向都显式包 sdpa_kernel([EFFICIENT_ATTENTION])，退到 math 就报错不爆显存；掩码由调用方造成 bf16 加性、每物理块一份、L 补到 16 的倍数；position_ids 显式；损失位用下标表；pad 的 query 行只看自己；flex_attention 留作冒烟后的优化。对齐容差改两道：fp32 逐行 ≤ 1e-5 且逐 token ≤ 1e-4 且不超同次运行基线 3 倍（判定）；bf16 均值 ≤ 2e-2 最大 ≤ 1e-1（只告警，只在 cuda 上做）。 / 理由：CPU 实测形态 A 对旧训练器逐行差 2.15e-6 与基线相同，math 内核 L=9,100 时 28 层留 148 GB。 / 依据：design-attention.md 第二到第五节。

## 决定 13

新训练器 meta.json 的 max_len 写 8192 之后，两个 call 评测脚本的提示左截长度会从 4,000 变成 8,096（它们用 max_len − max_new），这是有意的，评测端和训练端同口径；评测显存按 8192 估。 / 理由：不截断就是这一轮的目标；评测脚本不改。 / 依据：eval_causal_call.py 第 586 行、eval_causal_param.py 第 416 行读 max_len。

## 决定 14

对齐检查的配对改成「抽中事件的原始行按 (event, sent_idx) 升序写临时 jsonl，同一份文件喂 share_data.load_events 和旧 CallDS/ParamDS（limit=0），按位置配对并逐位断言 text 相同、丢弃计数相同」；share_data 模块顶层只许 stdlib 与 torch，旧训练脚本在函数体内延迟 import；read_position 加 keep 参数只扫真实 token，找不到返回 −1，两处调用保留 if j<0 守卫；build() 加 path=None 第二个关键字参数给小模型测试进门；epoch 末尾不满 accum 的一组也更新，U = ceil(M/accum)；评估点集合 {ceil(U·k/E)} 去重；ALIGN_CHECK.json 键名沿用 ctool 的大写 PASS；ctool 也冒烟一次并且退档 6144 时跟着退；ctool 读取位置回写不许写成「活跑错位已修」。 / 理由：workflow 确认的 8 条（C1 到 C8）加未核清单里我认可的那些。 / 依据：train_causal_callgen.py:55-60（版本门）、:167-168（行元组无 event/sent_idx）；eval_tool.py:142（keep）；run.py cmd_list/cmd_show 直接下标 desc。

## 决定 15

ctool 冒烟在 H100 上 `--bs 4 --accum 2` 爆显存或峰值超过 84 GiB（余量不足 10%），默认值改 `--bs 2 --accum 4`（仍是 8 个事件一次更新），再不行 `--grad-ckpt` 进排卡表 extra 不改默认值。 / 理由：stage-commands.md:238 实测 4096 × bs 4 时 ctool 峰值 60.2 GiB，上限翻到 8192 且撤掉截断最多翻倍，超过 H100 的 93.6 GiB；草稿 2.2 锁的是更新单位不是 bs。 / 依据：8-28-assistant 第三遍审查 S3。

## 决定 16

`--mem-probe` 的峰值含优化器状态（探针反向之后 lr 置 0 做一次 opt.step 分配 AdamW 状态再清掉）；最满块按「B 取 2 到 events_per_mb，B × L_pad ≤ 预算的最长组合里取乘积最大」定义；对齐检查的基线超 max(3 × 基线, 1e-6) 只告警不判定；尾组更新除数用实际小批数 n_g；速度对照用累计 rows / train_s 线性插值。 / 理由：8-28-assistant 第三遍审查 P1、S2、S4、S5、S9。 / 依据：AdamW 状态 0.6B 4.8 GB、1.7B 13.6 GB 比 10% 裁决线大；GPU 关 TF32 后基线可能为 0。

## 决定 17

`--tok-budget` 速度档候选改成 16384 与 24576（不再试 32768）；对齐检查的参照路径（旧 collate + inst_ce）不套 sdpa_kernel([EFFICIENT]) 上下文，只有新路径套。 / 理由：GPU 七步验证——形态 A 每 token 约 2.72 MB，32,768 的块约 92 GiB 装不下 H100 93.10 GiB；参照路径单行不补齐没有掩码，HF 开 enable_gqa 走 8 头 K/V，mem-efficient 不支持 GQA 报 No available kernel。 / 依据：design-attention.md 第七节；gpu_result.json（pipeline/runs/smoke/kvshare_gpu_kernel_check/）。

### 决定 17 附：GPU 七步验证的三个事实（plan-8-28 提供，来源 tokyo108 GPU 0 H100 NVL 93.10 GiB）

最长事件（L 9,381 补到 9,392）bf16 加性掩码补 16 的峰值 26.65 GiB，另外三种掩码变体 31.11 到 31.20 GiB，四种 row_loss_mean 逐位相同 3.2452；不套上下文时默认内核是 cuDNN；`--grad-ckpt` 把最长单事件峰值从 31.1 压到 6.35 GiB，`--lora` 不省激活（31.16）。第三次补射正在跑第 6 步的 bf16/fp32 对齐差。

8-28-assistant 核对（读 `pipeline/runs/smoke/kvshare_gpu_kernel_check/gpu_result.json`，文件时间 2026-08-28 09:35:47，steps_done 九步齐、errors 空）：mask_variants 的 bf16_aligned16 峰值 26.65 GiB，bool_unaligned 31.11、bf16_unaligned 31.20、bool_aligned16 31.17，四种 row_loss_mean 都是 3.2452，与上文一致；default_selection（cuDNN）峰值 31.11、row_loss_mean 3.2500，比四种 EFFICIENT 变体的 3.2452 高 4.8e-3；grad_ckpt 峰值 6.34 GiB（上文写 6.35），lora 31.18 GiB（上文写 31.16），以文件为准。第 6 步结果：fp32（5 个事件 34 行 505 个目标 token）新路径对旧训练器整批的逐行最大差 4.41e-6、逐 token 最大差 3.05e-5，同次基线（旧单行对旧整批）5.01e-6 / 6.91e-5；bf16 autocast 逐行最大 3.07e-2、平均 9.31e-3，基线 3.03e-2 / 8.83e-3，逐 token 最大 0.232 对基线 0.183。

## 决定 18

对齐检查 fp32 第一道门槛由逐行 1e-5 / 逐 token 1e-4 改成逐行 2e-5（--align-tol 默认）/ 逐 token 3e-4；bf16 第二道 2e-2 / 1e-1 不动。 / 理由：H100 mem-efficient 上同一批 34 行的 fp32 逐行最大差 4.41e-6 是 CPU 2.15e-6 的 2 倍，正式检查抽 6 个事件约 380 行 7,000 token 比验证多 10 倍、最大值随样本数涨（CPU 34 行到 151 行时 2.15e-6 到 2.62e-6），按 4.41e-6 × 1.3 估约 6e-6，1e-5 只剩 1.7 倍余量会误拦开训；2e-5 留 3 倍，离掩码错位的真错 1e-2 仍差 500 倍；逐 token 的 GPU 基线 6.91e-5 已贴近 1e-4。基线偏大是因为参照路径的单行批没有掩码走 math 内核，和整批的 mem-efficient 不同内核，所以基线只当告警。 / 依据：8-28-assistant-2 对 gpu_result.json 第 6 步的判读，design-attention.md 第七节终稿与 5.2；HEAD 368f3b1。grad_ckpt 6.34、lora 31.18 按文件为准，台账 record finish 已经按 6.34 / 31.18 记（runs.jsonl 里 kvshare_gpu_kernel_check 的 finish 条目）。

## 进度时间线（不是决定，plan-8-28 报的事实按收到顺序记）

### 2026-08-28 第一波（工单 01）收账

工单 01 一轮过评审，分支 ticket/2026-08-28-wave1/T01（base 2e61f5f，head d48c287）合并为 c4f900b；两环境 test_share_data 各 21 个测试 OK，mbert-env import share_data 退出码 0；share_data.py 465 行、tests/test_share_data.py 484 行，顶层 import 只有 json/random/sys/pathlib/torch。工单 01 记 resolved，工单 02/03 claimed（2216c44），第二波 workflow 已发射（wf_378f118f-079）。实现者报的两个与本轮无关的既有测试失败：test_splice_replay（仓库记忆记过）、test_no_env_reads_default_preset（预设那批，未深查）。

8-28-assistant 核对（HEAD 2216c44，登录机干净 shell，2026-08-28 09:5x）：`tests/test_preset.py:460` 的 `test_no_env_reads_default_preset` 单跑在系统 python3（3.10.12）和 cprobe-env 下都 OK；整个 `tests.test_preset` 两环境各 39 个测试 OK；系统 python3 全量 discover 356 个测试，1 个 error（`test_splice_replay` 的 import，仓库记忆里那条），16 个 skip，没有失败。这条测试的前提是环境变量 `NEW1_PRESET_JSON` 缺席（`tests/test_preset.py:455-460`），测试文件最后一次改动是 bd9a3d5（预设那批，早于第一波的 base 2e61f5f），第一波只新增了 share_data.py 和 tests/test_share_data.py。实现者那边失败的具体输出我没有看到。

### 2026-08-28 第二波（工单 02、03）收账

第二波 T02（0 轮修复，479b887）与 T03（2 轮修复，312038d）合并为 12c4a2b，收账提交 10f1d12。复核数字：selfcheck 76 任务就位；cprobe-env 下 test_share_trainer / test_ctool_readpos / test_share_data / test_cparam_assembly / test_lora_merge 共 Ran 58 tests OK（232 秒）；mbert-env import eval_tool / eval_mbert_call 都 ok；train_causal_share.py 788 行，heartbeat.emit 与 sdpa_kernel 各 3 处；diff 2216c44..12c4a2b 七个文件 +1,583/−39。T03 遗留两条 minor（ALIGN_CHECK.json 多一个 bf16_warn 诊断键；断言分支没测到），实现者的手算逐 token CE 已交 assistant-2 复核。GPU 阶段正在发射：ks828b06 smoke 档三格上 H200 3/4/5；速度档三个 run（b16k / b24k / b16k_es）上 H100 0/1/2，run_id ks828b06_gptoss_cgen_speed_*。

8-28-assistant 核对（13:05）：HEAD 10f1d12；`git diff --stat 2216c44 12c4a2b` 七个文件 +1,583/−39（eval_tool.py 11、train_causal_callgen.py 22、train_causal_share.py 788、train_causal_tool.py 55、run.py 57、tests/test_ctool_readpos.py 265、tests/test_share_trainer.py 424）；train_causal_share.py 788 行，heartbeat.emit 3 处、sdpa_kernel 3 处。`run.py gpu-jobs watch` 在 13:04:50 的采样里台账为空（六个 GPU run 那时还没登记，或按冒烟规矩不登记）。

## 决定 19

8-28-assistant-2 对训练器的只读审查（无「必须改」、7 条建议）按这样处理——S1（末层隐状态改用 model.model(...).last_hidden_state 过 lm_head，不用 output_hidden_states）、S2（bf16 粗筛那遍关掉参照路径的漂移自检，fp32 保留）、S3（backward 移出 autocast）、S5（对齐候选长度筛取 min(2048, max_len)）、S6（参照路径先释放 logits 再调 inst_ce）加工单 03 的两条 minor（F2 去掉 ALIGN_CHECK.json 多出的 bf16_warn 键；N2 补断言分支测试）合成工单 05，第三波 workflow 已发射（45c881e）；S4（每个事件在主线程造 [L,L] 掩码约 0.1 到 0.3 秒一次更新，估算没量）等速度档的 ips 出来再定；S7（--mem-probe 全集用 ro=None，偏保守）不改。已经在发射的六个 GPU run 不撤：S2 若触发会在开训前几分钟 exit(2)，损失小；不触发则数字有效（S1/S3/S5/S6 都不改数值）。 / 理由：审查没有必须改项，先让冒烟出数；修正走工单保留评审记录。 / 依据：assistant-2 的审查（行号按 12c4a2b 的 train_causal_share.py：S1 133-136、S2 429-430 与 331-338、S3 708-710、S5 268、S6 319-331）。

## 决定 20

train_causal_tool.py 的 ALIGN_TOL 默认值 1e-4 改 3e-4（只改常量与 help 文案，判定逻辑不动；文档回写进工单 04：stage-commands.md:210 与 MAP.md:92）。 / 理由：ks828b06 smoke 档的 ctool 在 8,167 token 的最长 val 事件上 maxdiff_hidden 1.03e-4、reldiff_hidden 1.46e-6（纯 fp32 噪声，脚本自己的判读口径）被 1e-4 拦下退出；上限 8192 后长窗口是常态；c1 与 np821 实跑一直传 3e-4（stage-commands.md:210 记过这个坑）。 / 依据：logs/new1_ks828b06_gptoss_ctool_smoke_t108g3.log 尾部的 ALIGN_CHECK 块；ops/np821b06_placement.json:9-10。ctool smoke 已用新默认补射。

### 2026-08-28 冒烟首批事实（plan-8-28 报）

cgen smoke（H200 gpu4）151 秒跑完，ALIGN PASS max_abs_diff 5.48e-6，best_val_ce 1.2938；cparam smoke 153 秒，9.30e-6，1.5926；两个都 record finish 并销号。速度档三个 run 的 ALIGN_CHECK 逐字相同：6 个事件 154 行 2,877 目标 token，max_abs_diff 5.48e-6、max_tok_diff 4.29e-5、基线 1.08e-5、bf16 均值 8.43e-3 最大 4.32e-2，tol 2e-5，PASS。mem_probe（含优化器状态）：最长事件 L_pad 9,504 峰值 31.43 GB；最满块 b16k 是 B=2 L_pad 8192 峰值 51.11 GB，b24k 是 B=3 L_pad 8192 峰值 75.05 GB。

8-28-assistant 核对与计算（读三份 `pipeline/runs/smoke/ks828b06_gptoss_cgen_speed_{b16k,b16k_es,b24k}/train_log.jsonl`，三个 run 都已有 done 事件；ctool smoke 日志 `logs/new1_ks828b06_gptoss_ctool_smoke_t108g3.log` 里 n_tokens 8167、maxdiff_hidden 1.03e-4、tol 1e-4、PASS false、reldiff_hidden 1.46e-6，与决定 20 所述一致）。三个 run 都是 450 个训练事件 20,641 行、57 次更新、log_every 3、对齐 max_abs_diff 5.48e-6；`peak_mem_gb` 是 `torch.cuda.max_memory_allocated() / 1e9`（train_causal_share.py:234、:732），单位是十进制 GB，只含已分配、不含 reserved 碎片。对照点按 spec §10 算法：累计值用 step 事件的 (rows, train_s) 夹住对照行数线性插值，窗口值用夹住窗口两端的插值做差商。

| run | 累计 ips @1,600 / 9,600 / 19,200 行（旧 2.76 / 3.26 / 3.97） | 窗口 ips @0–1,600 / 8,000–9,600 / 17,600–19,200（旧 2.77 / 3.94 / 6.24） | step 峰值最大 GB（GiB） | 最满块 mem_probe GB | 训练 112–131 s 之外的 wall_s |
|---|---|---|---|---|---|
| b16k（预算 16384） | 185.6 / 189.5 / 184.1 | 185.6 / 203.8 / 145.3 | 60.59（56.4） | 51.11 | 582.9 |
| b16k_es（同上 + expandable_segments） | 180.4 / 178.8 / 177.0 | 180.4 / 188.3 / 148.5 | 60.56（56.4） | 51.10 | 590.6 |
| b24k（预算 24576） | 152.5 / 155.3 / 155.8 | 152.5 / 168.6 / 135.2 | 80.91（75.4） | 75.05 | 621.4 |

六个对照点三个 run 全部高于旧训练器，倍数最低的是 17,600–19,200 行窗口对 6.24（b16k 23.3 倍，b24k 21.7 倍）。对 H100 93.10 GiB（torch 报的总量）按 GiB 算余量：b16k 39.4%，b24k 19.1%；按 max_memory_allocated 算，不含 reserved。两种预算下训练中的 step 峰值都高于 mem_probe 最满块的数（b16k 60.59 对 51.11，b24k 80.91 对 75.05）。expandable_segments 那个 run 的最终累计 ips 177.77 对不开的 183.73，峰值相同。三个 run 的 epoch 末 val_ce（450 个 val 事件 20,034 行）0.2608 / 0.2615 / 0.2604。

plan-8-28 采纳的口径：60.59 GB = 56.4 GiB 余量 39.4%，b24k 75.4 GiB 余量 19.1%；24576 慢 15%（184 对 157）。

### nvidia-smi 的三条单次样本（不是峰值；plan-8-28 报，发射员 2026-08-28 13:17 JST 一次 nvidia-smi）

采样器历史（monitor/history/<job>.jsonl）只记进度判定不记显存，reserved 的数只有这一次样本：GPU0（b16k，训练中第 12 次更新附近）memory.used 55,683 MiB（54.4 GiB）；GPU1（b24k，mem_probe 阶段）92,689 MiB（90.5 GiB），是 95,830 的 96.7%；GPU2（b16k_es，起步）14,483 MiB（14.1 GiB）。b16k 整程的 reserved 峰值没有记录，汇报按「allocated 56.4 GiB，一次训练中样本 54.4 GiB reserved」写，不写整程 reserved 峰值。

8-28-assistant 注：b24k 那条样本落在 mem_probe 最满块阶段，那一刻 allocated 峰值 75.05 GB = 69.9 GiB，reserved 90.5 GiB，两者差约 20 GiB，卡上只剩 3.3%；这是单次样本，不能外推成 b16k 的 reserved 峰值。b16k 那条 54.4 GiB reserved 低于同一窗口 step 事件记的 allocated 峰值 60.04 GB = 55.9 GiB，说明样本没有落在峰值时刻。

## 决定 21（冒烟裁决）

`--max-len` 默认保持 8192；`--tok-budget` 默认 16384；`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 不采纳；S4（掩码构造挪出主线程）不做；三个格同一个上限 8192。 / 理由：最长事件探针 31.4 GB，b16k 训练 step 峰值 60.59 GB = 56.4 GiB 对 93.10 GiB 余量 39%；b24k 慢 15%（157 对 184）且峰值 75.4 GiB 只余 19%、探针阶段单次 nvidia-smi 样本 90.5 GiB reserved 只余 3.3%；b16k_es 慢 3% 峰值相同；六个对照数全部高出旧训练器 23 到 67 倍，对旧稳态 10.6 到 11.6 行每秒是 16 倍；末尾窗口 145 是那段事件每行 token 多（按补齐 token 算吞吐 12.9k 对中段 16.9k token/s 同量级），不是尾组或评估。 / 依据：三份 train_log.jsonl；assistant-2 的复核脚本 verify/speed_judge.py；assistant-1 独立插值一致。

## 决定 22

`--mem-probe` 探针低估真峰（b16k 51.1 对 60.6，b24k 75.1 对 80.9）的机理是探针在优化器状态未建、梯度已清的条件下量，而训练真峰在第二个逻辑小批反向期间（状态 4.8 GB 加上一小批梯度 2.4 GB 都在）；开工单 06 把探针改成「状态先建好、最满块连做两次反向不清梯度、第二次反向后读峰值」，Blocked by 05，第四波和工单 04 一起跑。这一轮的裁决用训练 step 峰值而不是探针数（spec §10 已写明）。 / 理由：assistant-2 的判读；探针的用途就是替全量训练预估峰值，低估 10 GB 会让 48G 卡的排卡判错。 / 依据：同上。

8-28-assistant 注：决定 22 的机理是判读不是实测。按它的算法探针少算 4.8 + 2.4 = 7.2 GB，而观察到的差是 b16k 9.5 GB（60.59 − 51.11）、b24k 5.9 GB（80.91 − 75.05），两个都对不上 7.2；工单 06 的验收应当写成「改后探针数 ≥ 同预算速度档整程 step 峰值」这种实测判据，不能以机理成立为验收。

（ctool 的 bs/accum 定值还差 H100 上的显存数：H200 上 smoke PASS 但没记显存，plan-8-28 已在 H100 gpu0 补一个带 nvidia-smi 采样的 ctool smoke，run_id ks828b06_gptoss_ctool_h100mem，2 秒采一次 memory.used。）

### 2026-08-28 ctool H100 显存补测（plan-8-28 报）

ks828b06_gptoss_ctool_h100mem（gpu0，max_len 8192，bs 4 accum 2，smoke 200/80 事件）对齐 PASS、start 已写，训练第一批前向就 OOM：进程占 92.94 GiB 时再要 154 MiB 失败（logs/new1_ks828b06_gptoss_ctool_h100mem_t108g0.log 第 89 行），nvidia-smi 2 秒采样 115 个样本最后一次 87,179 MiB（p50 13,037、p90 72,023）。对 stage-commands.md:238 那句「4096 × bs 4 峰值 60.2 GiB」：8192 × bs 4 超过 93.1 GiB，翻倍那句成立。决定 15 的退路生效：ctool 默认改 --bs 2 --accum 4（仍 8 个事件一次更新），复测 ks828b06_gptoss_ctool_h100mem_bs2 在 gpu0 跑。

8-28-assistant 核对（读同一份日志）：OOM 原文「Tried to allocate 154.00 MiB … this process has 92.94 GiB memory in use. Of the allocated memory 77.61 GiB is allocated by PyTorch, and 14.58 GiB is reserved」，也就是碎片 14.58 GiB（np821 那次是 8.63 GiB，stage-commands.md:244）；对齐块 maxdiff_hidden 1.03e-4、tol 0.0003、PASS true（决定 20 的新默认已生效）；start 事件 n_train 200、n_eval 80、steps 25、dropped_events_train 1、dropped_events_val 3——这两个丢弃数和 plan 第四节 8192 那一行（train 丢 1 个事件、val 丢 3 个）逐字相符，是 ctool 丢弃规则的第一次实跑验证。nvidia-smi 最后一个样本 87,179 MiB 低于 OOM 时刻的 92.94 GiB，2 秒采样没有踩到峰值。

### 2026-08-28 ctool H100 bs2 复测（plan-8-28 报）

ks828b06_gptoss_ctool_h100mem_bs2（H100 gpu0，8192，--bs 2 --accum 4）跑通：nvidia-smi 2 秒采样 165 个样本最大 56,859 MiB、p90 56,855（平台，不是尖峰）、p50 34,699；25 次更新；对齐 PASS；dropped_events 1/3；calA_weighted_acc 0.394 / lastbound 0.4125（smoke 规模）。ctool 没记 max_memory_allocated，只有这一组采样数。决定 15 退路坐实：train_causal_tool.py 默认改 --bs 2 --accum 4（仍 8 个事件一次更新）。工单 04 的 Comment 定值：--max-len 8192（三格）、新训练器 --tok-budget 16384、ctool --bs 2 --accum 4 --align-tol 3e-4。

8-28-assistant 核对（只核范围，不预测）：56,859 MiB = 55.5 GiB，对 H100 93.10 GiB 余量 40%。两个参照：① 同样每批 16,384 个补齐 token 的 ctool 4096 × bs 4 实测 60.2 GiB（stage-commands.md:238），本次 55.5 比它低 8%；② cgen 在 8192 / 每批 2 的 B_h100 峰值 90,859 MiB（plan 9.2）按 4096 下 ctool 对 cgen 的峰值比 60.2 / 76.8 = 0.78 折算是 71,200 MiB = 69.5 GiB，本次比它低 20%。观察值落在两个参照之下，方向上和「ctool 不算全词表 logits、每 token 便宜」相容；smoke 是随机 200 个事件，最长的一对（两个约 8,000 token 的事件同批）有没有出现在这 25 次更新里日志里查不到。就算按参照 ② 的 69.5 GiB 当最坏一批，余量也有 25%，48G 卡（47.51 GiB）两个数都装不下。平台形状（p90 = max）与 CUDA 分配器 reserved 只涨不落的行为一致，max 是整程 reserved 的高水位，正是排卡要的数。

### 2026-08-28 TIMELINE 条目落地

`TIMELINE.md` 最上面新加「2026-08-28 训练口径换成缓存复用训练器：上限 8192 超长整条丢弃、8 个事件一次更新、cgen/cparam 1 个 epoch，批次前缀 ks828」（HEAD ad22297，第 13 到 54 行）。8-28-assistant 按台账 0 到 22、草稿第二节、plan 第 9.2 / 12.10 / 第四节逐句核过，结果发给 plan-8-28：一处数字无出处（第 18 行「4096 的左截断在 train 上砍掉 6% 的前缀 token」，plan 第四节没有这个数，草稿 2.1 的「6% 以内」说的是 6144 丢 58 个事件的估算）、一处两种量纲混写（第 44 行的 60.59 GB 是 torch 已分配峰值，第 46 行的 56,859 MiB 是 nvidia-smi）、一处跨文件不一致（第 45 行「24576 慢 15%」对 design-attention.md 8.5 的「慢 18%」）、三处措辞（第 19 行裁决归属、第 26 行读取位置规则的压缩说法、第 53 行 28% 的出处与样本范围）。runs.jsonl 第 118 到 133 行确有 ks828 九个 run 的 start/finish；issues/ 下确有 01 到 06 六张工单；三个速度档与 ctool 的 start 事件都写 dropped_events_train 1、dropped_events_val 3。

六处全部按上述改法改了（d2a86ff，TIMELINE.md 14 行增 7 行删）：截断统计改成 4,956 行 2.66% / 259 事件 6.28% 带 plan 第四节出处；决定归属写成「gyb 确认，epoch 数与 ctool 读取位置两条按推荐锁定、gyb 授权」；读取位置规则改成跨切点 token 的准确措辞；60.59 GB 标明 torch 已分配峰值、reserved 未记录、一次样本 54.4 GiB，56,859 MiB 标明 nvidia-smi 含分配器缓存；24576 写成「末尾累计慢 15%（157 对 184）；六个对照点平均慢 18%」；28% 标明速度档 450 事件样本。

## 决定 23

TIMELINE「只增不改」的执行口径——同一会话同一天写成、三十分钟内、没有被任何文件引用的条目，事实错误在原处更正并在提交信息里写明「同日更正」；隔天或被引用之后的条目只追加更正段。 / 理由：错误数字留在正文、更正挂在后面，读的人要自己对账。 / 依据：仓库 CLAUDE.md「TIMELINE 人写，只增不改」的目的是不改写决策历史，不是保留刚写错的数字。

8-28-assistant 注：这条是 plan-8-28 对仓库规矩「TIMELINE 只增不改」的自行解释，gyb 没有确认过；本轮按它执行了一次（d2a86ff，原处改了 7 行）。写 artifact 时应当把这条单独列给 gyb 看，由 gyb 定这个口径要不要写进 CLAUDE.md。

### 更正：24576 对 16384 的慢幅口径（b83ec21）

24576 对 16384 六个对照点分别慢 17.8 / 18.1 / 15.4 / 17.8 / 17.3 / 7.0%，算术平均 15.6%，TIMELINE 与 design 8.5 都写成「末尾累计慢 15%（157 对 184）；六点平均 16%」（b83ec21）；之前的 18% 是第一个点的数，不是平均，assistant-2 核出来的。

8-28-assistant 注：六个百分数按我自己算的六点（185.6→152.5、189.5→155.3、184.1→155.8、185.6→152.5、203.8→168.6、145.3→135.2）复算是 17.8 / 18.0 / 15.4 / 17.8 / 17.3 / 7.0，平均 15.6，与更正一致。我在核 TIMELINE 那条消息里写的「18% 是六个对照点的平均」是错的，六个数我列对了、平均值说错了，更正以 b83ec21 为准。

### 2026-08-28 第三波（工单 05）收账

工单 05（第三波，1 轮修复）分支 base 45c881e head 6c507cc 合并为 a89da00（spec §9 字段列表一行冲突，取主干加 baseline_warn），复核 cprobe-env 39 个测试 OK、output_hidden_states 0 命中、selfcheck 76；收账提交 f1e0a1f；工单 06 第四波 b 已发射（wf_df547174-750），工单 04 第四波 a 仍在跑（wf_1712edbf-529）。06 合并后计划在 H100 上用最终代码再跑一次 smoke 档三格加 b16k 速度档（含 --mem-probe），作为终验；然后 ticket-run Phase 4 终审、artifact。

8-28-assistant 核对：HEAD f1e0a1f，a89da00 与 6c507cc 在 git log 里；`git diff --stat 10f1d12 a89da00` 14 个文件 +1,007/−55，其中 train_causal_share.py 119 行改动、train_causal_tool.py 17 行、tests/test_share_trainer.py 162 行；train_causal_share.py 里 output_hidden_states 0 命中。

### 2026-08-28 第四波 a（工单 04）收账

工单 04（第四波 a，1 轮修复）分支 base d6aa99d head 39da84e 合并为 9fc83b7，五份文件 +57/−14（extending.md §3 换实现先例与 §5 #25 到 #27、gates.md、invariants.md 第 45/47/48/53 行、stage-commands.md §3/§3.1/第 213 行/§7、MAP.md 五行），收账提交在其后（d38d8a1）。实现者把工单正文残留的 ctool `--bs 4 --accum 2` 按 Comment 统一成 `--bs 2 --accum 4`，plan-8-28 复核同意。剩工单 06（第四波 b，在跑）、终验冒烟、终审、artifact。

### 2026-08-28 第四波 b（工单 06）收账

工单 06（第四波 b，2 轮修复）分支 base f1e0a1f head d97ed61 合并为 907d143，收账 e952c37；复核 cprobe-env 三个测试文件 OK、selfcheck 76、n_backward 与 ctool peak_mem_gb 都在。实现者抓到工单原文的技术缺口：全体 .grad 为 None 时 opt.step() 不分配 AdamW 状态，所以建状态前先做一次不计入测量的前向反向（小张量实测状态从空变成含 exp_avg/exp_avg_sq）。六张工单全部 resolved。终验四个 run 正在发射（HEAD e952c37）：ks828b06_gptoss_cgen_final_b16k（450 事件全速度档带探针，H100 0）、ks828b06_gptoss_cgen_final_b24k_probe（只跑探针，H100 1）、ks828b06_gptoss_cparam_final_smoke（H100 2）、ks828b06_gptoss_ctool_final_smoke（H200 3）。artifact 草稿里 P1 到 P3 三处等终验数一起改。

8-28-assistant 核对：HEAD e952c37，907d143 与 d97ed61 在 log 里；`git diff --stat f1e0a1f d97ed61` 五个文件 +196/−23（train_causal_share.py 73、train_causal_tool.py 20、test_share_trainer.py 107、test_ctool_readpos.py 17、spec.md 2）；train_causal_tool.py 第 258 行 `_peak_mem_gb`、第 461 与 468 行写进 step 与 eval 事件；issues/06 的 Status 是 resolved。终验的验收判据照决定 22：改后探针数不低于同预算整程 step 峰值（b16k 60.59 GB、b24k 80.91 GB）。

### 2026-08-28 终验发射与全量测试（plan-8-28 报）

终验四个 run 在 HEAD 1414e8e 发射（第一次被发射员在脏树门禁拦下——plan-8-28 给探针加 reset_peak_memory_stats 那一行时发射员正在发，改动比发射早 11 秒，发射员一个 session 都没起；改动提交为 234dfad 后 plan-8-28 自己发的）。全量测试：系统 python3 discover 358 个用例 1 error（test_splice_replay，仓库记忆里的老毛病）18 skip；cprobe-env 五个文件 65 个 OK；终审员自己跑 cprobe-env 全量 discover 433 个 OK（13 skip）。

## 决定 24

ticket-run Phase 4 终审（opus，起点 2cbce57 终点 e952c37）报 4 条挡合并、16 条观察。处理：F1（探针 longest_event 被 fullest_block 污染）在终审看的版本之后已按 assistant-2 的复核修掉（234dfad），终验 run 用的是修后代码；F2（SKILL.md §C2 两处过时：smoke 限额与对齐门说法）、F3（stage-commands §3 输出列表缺 ALIGN_CHECK.json、退出码段过时）派 sonnet 一次修完，连同两条观察（spec §1 与 11.3 自相矛盾、extending #25 触发条件的 ≤）一起，之后一次范围限定复审；F4（探针实测判据）就是终验。其余观察（_pad16 与 _l_pad 两份、_peak_mem_gb 两份、事件分组三份、packed_len_max 写的是 L_pad、readonly 审计分母口径不同、driver 的 smoke 门只查 ctool 的 PASS 等）不改，记进汇报的遗留清单。 / 理由：ticket-run Phase 4 的规程；F1 已修；其余是重复逻辑与口径注记，没有一条会让数字算错。 / 依据：终审报告（tasks 输出）、234dfad。

8-28-assistant 核对：git log 顺序是 907d143 → e952c37 → 234dfad → 1414e8e；234dfad 只改 train_causal_share.py 加 4 行（第 278、287 行两处 reset_peak_memory_stats）；runs.jsonl 第 134 到 137 行是四个终验 run 的 start（15:09 到 15:11）。一处要注意：234dfad 的提交信息写的是「终验 run 用的是改前代码，只影响 longest_event 那个数的含义」，和上文「终验 run 用的是修后代码」相反；提交信息是发射被拦之前写的、改不了，以四个 run 目录里 RUNMETA.json 记的 commit 为准：`pipeline/runs/smoke/ks828b06_gptoss_cgen_final_b16k/RUNMETA.json` 记 commit 1414e8ee…、branch main、dirty false，所以终验 run 用的是改后代码，决定 24 的说法对，234dfad 的提交信息错。

终验中途读到的数（15:2x，final_b16k 跑到第 33 次更新，b24k_probe 已 done）：final_b16k 的 mem_probe fullest_block（B=2，L_pad 8192，n_backward 2）54.376 GB、longest_event（L_pad 9,504）36.474 GB；同一个 run 前 11 条 step 的 peak_mem_gb 最大 57.306（第 12 次更新），已经高于探针的 54.376；同样的事件与种子下，上一次速度档 b16k 前 11 条 step 的峰值是 52.0 / 56.0 / 55.6 / 60.04 / 53.8 / 53.0 / 56.2 / 58.0 / 56.0 / 57.2 / 49.4，这次是 49.3 / 52.7 / 52.4 / 57.3 / 51.9 / 50.2 / 52.3 / 54.8 / 53.0 / 54.5 / 46.1，逐条低 2 到 4 GB。b24k_probe 的 fullest_block（B=3）76.471 GB、longest_event 36.488 GB，上一次速度档 b24k 的整程 step 峰值是 80.91。

终验两个 smoke 的数（8-28-assistant 读日志，都已 done）：cparam_final_smoke（H100 gpu2）40 训练事件 / 16 评估事件，5 次更新，对齐 PASS 9.30e-6（ALIGN_CHECK.json：6 个事件 154 行 1,916 目标 token，逐 token 4.72e-5，bf16 均值 9.74e-3 最大 4.87e-2，tol 2e-5），四次评估 val_ce 2.515 → 1.9863 → 1.6994 → 1.5927，step 峰值 12.0 到 15.1 GB，wall_s 89.65，dropped_events 1 / 3；和 H200 上那次 smoke 的 2.5151 → 1.5926 一致。ctool_final_smoke（H200 gpu3，默认 bs 2 accum 4，steps 25）对齐 PASS maxdiff_hidden 1.03e-4（tol 3e-4，n_tokens 8,167），calA_weighted_acc 0.3973 / lastbound 0.4125，eval 事件第一次带 peak_mem_gb 47.337 GB（= 44.1 GiB，torch 已分配），n_bound_dropped 0，dropped_events 1 / 3；对照 H100 bs2 那次 nvidia-smi 的 56,859 MiB（55.5 GiB，含分配器缓存），已分配比卡上占用低 11.4 GiB。

终验 final_b16k 完成（8-28-assistant 读日志算，HEAD 1414e8e，H100 gpu0，450 事件 20,641 行 57 次更新，log_every 3）：累计 ips 在 1,600 / 9,600 / 19,200 行处 187.2 / 191.9 / 187.6（对旧 2.76 / 3.26 / 3.97 是 67.8 / 58.9 / 47.3 倍），窗口 ips 在 0–1,600 / 8,000–9,600 / 17,600–19,200 行是 187.2 / 206.2 / 156.2（对旧 2.77 / 3.94 / 6.24 是 67.6 / 52.3 / 25.0 倍），六点全过；末尾累计 ips 188.17，train_s 109.69，wall_s 585.3，epoch 末 val_ce 0.261（20,034 行子集），对齐 PASS 5.48e-6，dropped_events 1 / 3。显存：19 条 step 的 peak_mem_gb 最大 58.472 GB（第 42 次更新），mem_probe fullest_block 54.376 GB、longest_event 36.474 GB。决定 22 的验收判据「改后探针数不低于同预算整程 step 峰值」在同一个 run 里不成立：探针比整程峰值低 4.1 GB；b24k 只有探针 76.471，对上次速度档整程峰值 80.91 低 4.4 GB。同一批事件、同一个种子下，这次 19 条 step 峰值逐条比上次速度档 b16k 低 2.1 到 3.9 GB（最大值 58.47 对 60.59）。

plan-8-28 报的终验汇总（四个 run 全部 done、零错误、台账已 finish 销号）：final_b16k 六点插值累计 187.23 / 191.91 / 187.63、窗口 187.23 / 206.20 / 156.24，整程 step 峰值 58.472 GB，train_s 109.69，wall_s 585.3，val_ce 0.261；探针 fullest 54.376、longest 36.474；b24k_probe 探针 fullest 76.471、longest 36.488，wall_s 432.5；cparam_final_smoke ALIGN 9.30e-6（1,916 token）、val_ce 1.5927、wall_s 89.65（H100）；ctool_final_smoke（H200）ALIGN 1.03e-4 PASS、自记 peak_mem_gb 47.337 GB、dropped 1/3、calA 0.3973。四份 ALIGN_CHECK 与上一轮逐位相同。8-28-assistant 核对：六点与我独立算的逐点一致（到小数点后一位），其余各数与我上面读的相同。

## 决定 25

工单 06 的实测判据（探针 ≥ 整程 step 峰值）没过：改后探针最满块 54.38 对整程 58.47（低 4.1 GB），b24k 探针 76.47 对上次整程 80.91（低 4.4 GB），改前是低 9.5 / 5.9。这一轮不再改探针：把它定为「带实测偏差的估计」——排卡时探针最满块的数加 10% 再判余量；「按真实训练循环连做两个小批」的退路列进需要 gyb 拍板的事。 / 理由：偏差从 9.5 缩到 4.1 GB，两个预算下偏差量级相同（4.1 / 4.4）；再改一轮要再一轮工单加 GPU 复测，而排卡靠加 10% 已经覆盖；剩余差额的成因等 assistant-2 从 step 序列判读。 / 依据：final_b16k 与 b24k_probe 的 mem_probe 事件、final_b16k 的 step 序列、上次 b16k/b24k 的 step 序列。

8-28-assistant 注：加 10% 对现有两个数够用：54.376 × 1.1 = 59.81 高于 58.47（余 1.3 GB），76.471 × 1.1 = 84.12 高于 80.91（余 3.2 GB）；两个预算的探针偏差是 7.5% 和 5.8%。这个 10% 只盖已分配峰值之间的差，reserved 碎片那一道折（stage-commands.md:244）是另外一层，排卡时两道都要打。

### 2026-08-28 artifact 草稿核对

plan-8-28 写好 artifact 草稿 `plans/2026-08-28-kvshare-report.html`（HEAD 71dcc2a，终验一节待补），8-28-assistant 按台账逐段核。核过没问题的：一句话结果四个数；对齐表前四行与 gpu_result.json、三个速度档和 cgen smoke 的 ALIGN_CHECK.json（都是 6 个事件 154 行 2,877 token，5.48e-6 / 4.29e-5 / 8.43e-3 / 4.32e-2）一致；速度表四行与我算的插值一致；显存表八行（含 math 内核校准点 L 2,552、实测差 12.17 GiB 对解析式 10.87）；smoke 表的 cgen / cparam 行和 ctool 的 0.408（H200 smoke 的 eval 事件 calA_weighted_acc 0.408、lastbound 0.425）；23 条决定的三行；需要拍板的八件；文件路径。发现的错误与遗漏发给了 plan-8-28：助手 1 三遍的发现数是 35 不是 24（13 + 9 + 13）；「工单 6 张全部 resolved」与「工单 06 已加字段」在 06 仍是 claimed（无合并提交）的时候写早了；「GPU run 11 个」与 runs.jsonl 的 9 个 run_id、logs 的 12 次发射都对不上；cparam smoke 对齐样本是 6 个事件 154 行 1,916 token 不是「抽 2 个事件」；解读段两处没有依据的判断（24576 慢的原因归到 pad 更多、OOM 那批说成四个 8192 长的事件）。invariants.md:45 的 epochs 理由已按核对改掉（8c4d587）。

8-28-assistant 核对：`git diff --stat d6aa99d 39da84e` 五个文件 +57/−14 对（extending 7、gates 2、invariants 9、stage-commands 45、MAP 8）；extending.md §5 第 291 到 293 行是 #25 到 #27；invariants.md:47 写「默认 8192 不退档（2026-08-28 冒烟裁决）」、:53 smoke 行已分 ctool 与 cgen/cparam；gates.md G14 那行改了 smoke 说明；MAP.md:95 是（参照）行、:98 是 share_data 的（共用）行；两份 skill 文档里 `--bs 4 --accum 2` 只剩在工单 02/04 的 Comments 里当历史。一处要补改：invariants.md:45 给 cgen/cparam `--epochs` 改 1 附的理由「每个事件全文只过一遍底座，不用像旧逐行训练器那样多轮吃同一份切点」不是裁决的理由，草稿 2.5 的理由是 plan 12.7 的 8 个 cgen/cparam run 的 val_ce 全在 epoch 0 最低（新训练器每个 epoch 同样把每个切点过一遍，只是前缀共享）。

## 封口（2026-08-28，8-28-assistant 写）

这份台账到这里封口。最终 HEAD 是 7fab3dd（收官提交：终审 F2/F3 与两条观察的文档修复经复审、stage-commands 加排卡两条规则、TIMELINE 同日补记终验、四个终验 run 台账收官、汇报定稿），selfcheck 76 个任务就位，工作树干净（8-28-assistant 核：`git status --short` 零行）。台账内容是决定 0 到 25 加两条更正（决定 7 更正、24576 慢幅口径更正），时间线止于终验收官（四个终验 run 全部 done 并在 runs.jsonl 第 138 到 141 行 finish 销号）。给 gyb 的汇报已发布：https://claude.ai/code/artifact/0bbbe221-da05-4fcc-951f-8b2c04f2ef84（源文件 plans/2026-08-28-kvshare-report.html），汇报里「需要 gyb 拍板的事」是九件：决定 23 的 TIMELINE 同日更正口径、学习率扫描的规模、评测端超长事件的处理、flex_attention 与装块优化、np821 十二格是否按新口径重训、决定 4 去掉训练中的生成式评估、决定 18 与 20 的自定容差、决定 3 与 10 的归类和前缀命名、决定 25 显存探针的退路。8-28-assistant 这一天对 spec、工单、TIMELINE 和汇报的审查发现合计 35 条（第一遍 13、第二遍 9、第三遍 13），加 TIMELINE 6 处、汇报 9 处，全部记在时间线各节里。台账里凡是标「8-28-assistant 注」或「核对」的段落是记录员的核实与注记，不是 plan-8-28 的决定。

## 第二轮（2026-08-28 晚，gyb 裁决之后）

封口之后台账重新开写，决定从 26 起续编，签名沿用 8-28-assistant。

8-28-assistant 注：第二轮开工时 HEAD 是 7668166，工作树干净（`git status --short` 零行）。封口段写的最终 HEAD 7fab3dd 之后又有两个提交：70d8d9b 是封口段本身的提交（plan-8-28 提的），7668166 是 design-attention 第 8.6 节的终验判读（assistant-2 写：探针 4.1 GB 的差额来自损失位数，建议按 2.7 MB × token + 1.8 MB × 损失位挑块）。这两个提交没有改代码。

### gyb 原话（经 plan-8-28 转来，照录）

2026-08-28 晚，对汇报里九件待拍板的事：

> 学习率需要扫。flex_attention不用做。其他的都给几种可能，我目前没有人工审核时间，你先选项的代码先实现好，可以通过参数切换，我回头对比一下。实现好之后验证一下，给推荐的配置gpu run去扫学习率了，你和助手我都压缩了一下。保持原来的工作方法即可

前一版消息里还有一句，plan-8-28 说指的是减少补齐浪费的装块优化：

> 另一个先不做，保留

### 决定 26

plan-8-28 对九件事的对应安排（原文照录）：第二件学习率扫描做；第四件 flex_attention 不做、装块优化不做；第三件评测端超长、第六件生成式评估字段、第七件容差、第九件探针退路四件各做成命令行参数可切换的几个选项，默认值我定一个推荐值；第一、五、八件不是代码，只在报告里写选项，等 gyb 回头选。做法沿用上一轮：spec 加第 16 节、工单 07 到 12、ticket-run workflow（sonnet/opus）、收账、终验、然后 gpu-run 发学习率扫描。 / 理由与依据：这条消息没有单列理由与依据行；九件的编号按封口段列的顺序，安排逐件对应上面 gyb 的原话。

8-28-assistant 注：汇报里第二件问的是学习率扫描的规模（最小版还是每个底座各扫），gyb 原话只说「学习率需要扫」和「给推荐的配置 gpu run 去扫学习率」，规模没有定，决定 26 也没有定，这一项到 spec §16 写的时候要有一个明确的定值或者一个待定标记。

### 决定 27（写在 spec §16.1，提交 485081e；plan-8-28 没有另发消息，以下照抄 spec 原文）

学习率扫描：「做。规模定为每个底座配置各扫一组：b06 / b17 / l17 / l4 四个配置 × 三个学习率 = 12 次 run，cgen 格，1 个 epoch，按 `val_ce` 最低选（16.6；决定 27）」。 / 理由与依据：spec §16.1 没有单列；网格初值（全参 1e-5 / 2e-5 / 5e-5，LoRA 1e-4 / 2e-4 / 5e-4）来自草稿 2.3，spec §16.6 写明「8-28-assistant-2 的网格建议到了之后改常量」。

### 决定 28（写在 spec §16.1 末尾，提交 485081e；照抄 spec 原文）

「推荐值（决定 28，扫描发射时用的就是这一套）：`--overlong left`（评测口径不变，扫描不评测）、`--gen-eval 200`、`--align-rule abs`（门槛默认值不变）、`--mem-probe --mem-probe-pick cost`。每个开关的默认值等于推荐值，除了 `--overlong`——它的默认值 `left` 是为了让已有评测命令的行为一个字不变。」 / 理由与依据：spec §16.1 没有单列。

8-28-assistant 注：决定 29（学习率网格）与决定 30（排卡与 `tok_budget`）plan-8-28 说要等 assistant-2 的 design-attention 第九节，此刻（485081e）还没有编号内容；这一节的 spec 与工单 07 到 12 的审查发现记在下面的时间线里。

### 第二轮时间线

**2026-08-28 晚，spec §16 与工单 07 到 12 第一遍审查（8-28-assistant，对 485081e）。** 六张工单引用的行号逐个对过当前代码，全部对得上（`eval_causal_call.py` 214 / 590，`eval_causal_param.py` 209 / 420，`eval_tool.py` 116 到 160，`train_causal_callgen.py` 309 到 331 / 361 / 449 / 536 到 538，`train_causal_param.py` 235 到 258 / 359 / 420 到 422，`share_data.py` 205，`train_causal_share.py` 78 到 81 / 234 到 302 / 434 到 570 / 761 到 764，`design-attention.md` 8.6 的 B=3、L_pad 5,344、4,736、2.7 MB、1.8 MB、58.5，test 集 391,893 行，`run.py launch` 的 `--cmd / --run-id / --track / --outdir` 都在 `ops/launch_cmd.py:52`）。发现 15 条发给 plan-8-28，最重的四条：cgen / cparam 评测按下标对齐 ctool 的 `logits_test.pt` 并硬断言行数相等（`eval_causal_call.py:569`、`eval_causal_param.py:397`），ctool 评测一开 `skip` / `drop-event` 下游就断言退出，spec 16.2 末段「cgen 的 n_dropped_events 会是 0」的前提不成立；`share_data.pack_event` 第 274 行是六个名字的拆包，行元组加第 7 位会 ValueError，spec 16.3「按下标读的代码不受影响」不覆盖这一处；工单 08 / 09 / 10 同一波并行改 `train_causal_share.py` 的 `main()` 参数与 `start_kw`（724 到 746 行）和 `tests/test_share_trainer.py` 末尾，07 / 08 / 10 同时改 `share_data.py`，合并会冲突；ctool 的 `align_check` 已经有 `absmax_hidden` / `reldiff_hidden`（`train_causal_tool.py:243-250`，决定 20 引的就是 `reldiff_hidden 1.46e-6`），spec 16.4 再加 `hidden_scale` / `rel_maxdiff_hidden` 是一物两名。其余：16.4 的依据「ce 量级约 2.5」在 gpu_result.json 里没有（文件里是 `row_loss_mean` 2.1379、逐行 `max_rel` 3.10e-6，1e-5 对 3.1e-6 是 3.2 倍不是 5 倍）；16.8 对 b17 / l17 / l4 三个从没在新训练器上跑过的配置没有 smoke 步；16.6 的发射命令没带 `--log-every`（默认 50，b06 一个 epoch 约 57 次更新）；ctool 的「全文」取的是按 label2id 过滤后的最大 sent_idx 行（`train_causal_tool.py:93-96`），share_data 不过滤；扫描 run_id 多一段 `_lr1e-5`，extending §3.4:167 的三段形状要在工单 12 补写；16.11 引草稿 2.3「尺寸沿用」给 cparam 沿用当依据是错引；16.1 末句「除了 --overlong」自相矛盾；工单 10 没点名两个现有测试的 `Namespace(tok_budget, events_per_mb)` 要补字段；16.5 与工单 10 对旧字段保留不一致；`gpu=False` 不是注册表现有 CPU 条目的写法；生成评估拉长无心跳窗口。

**2026-08-28 晚，plan-8-28 对 15 条的处理（b7dbbea，原话照录）。** 「1 下游按下标——定为 logits 保持全行数、剔除行写零、`.meta.json` 记 `overlong_mode` 与 `excluded_idx`，cgen/cparam 读它剔行并计 `n_excluded_by_ctool`，`--cached-logits` 模式不同硬停（静默点 #33）；2 `pack_event` 第 274 行改 `row[:6]`，工单 08 点名；3 并行不改串行，改成各工单固定落点加测试分新文件（08 `test_share_gen_eval.py`、09 `test_align_rules.py`、10 `test_mem_probe_pick.py`），冲突主会话收账时解；4 ctool 沿用 `reldiff_hidden / reldiff_logits`，`rel` 规则两个都判，JSON 只加 `rule / rel_tol`；5 依据改按 `gpu_result.json` 的 `row_new_vs_old_batched.max_abs` 4.41e-6 与 `max_rel` 3.10e-6 写，`ref_scale` 定为 `mean(|ce_ref|)` 并写明为什么不用逐行；6 16.8 加三个新配置先冒烟加 b06 再冒烟一次；7 plan 命令带 `--log-every 10`；8 「全文」各评测脚本跟自己的训练器同规则（静默点 #34）；9 工单 12 加 extending §3.4 与 stage-commands §3.2 的四段 run_id 与 sweep 目录；10 改成决定 31；11 「除了」删了；12 工单 10 点名两个 Namespace 用例补字段、`_peak_gb` 抽函数让 `worst_gb` 断言有区分度；13 spec 补「`n_events / packed_len_max` 保留」；14 不写 `gpu` 键；15 16.3 加 `eval_ce` 的 `beat` 回调与生成前后心跳，16.8 提 `--stall-line`。」

### 决定 31（写在 spec §16.1 与 §16.11，提交 b7dbbea；照抄 spec 原文）

「决定 31，cparam 与 ctool 不单独扫，cgen 扫出来的值按训法（全参 / LoRA）写成默认值，cparam 沿用」；§16.11：「cgen 扫出来的值按训法（全参 / LoRA）写成默认值，cparam 沿用，ctool 不动；要不要单独扫列进汇报」。 / 理由与依据：spec 没有单列；来历是 8-28-assistant 第一遍审查第 10 条（原文错引草稿 2.3「尺寸沿用」，改成编号裁决）。

**2026-08-28 晚，复审（8-28-assistant，对 b7dbbea）。** 15 条的处理逐条核过，写法与代码对得上（工单 07 引的 `eval_tool.py:124` `full = items[-1][2]["text"]`、`heartbeat.emit` 签名 `ops/heartbeat.py:17-18`、采样器按 `(ts, done)` 去重所以只刷时间戳的心跳能推停滞线 `ops/sampler.py:374-377`、工单 09 锚点 `:624 / :626`、工单 10 的 step 日志 `:813-817`、16.4 的 4.41e-6 / 2.1379 = 2.06e-6）。复审新发现 6 条发给 plan-8-28：16.8 让三个新配置的 smoke 出 `worst_gb` 当排卡依据，但 `--smoke` 取的是全文 token 数最短的 40 个训练事件（`train_causal_share.py:600-602`），而 16.5 定 `cost` / `loop` 用本次 run 的 `tr_events`，smoke 下的 `cost` 探针踩的是 40 个最短事件，这个数当不了排卡依据（`tokens` 才另载全集，`:751-753`）；16.8 给 b06 再冒烟的 run_id `ks828b06_gptoss_cgen_smoke` 已经存在于 `pipeline/runs/smoke/`，训练器守卫（`:635`）不带 `--force` 秒退，台账也按 run_id 记；16.2 cgen 侧「`excluded_idx` 非空就把这些下标对应的行从 `keys` 去掉」没说清行与事件的单位（ctool `skip` 只剔窗口外的边界、事件可能在窗口内的行触发）；16.6 与工单 11 的「约 506 次更新」按 train.jsonl 4,127 个事件减 1 个丢弃算是 516；工单 07 第 5 条「新函数放在 `load_events` 之前、`read_position` 之后」不可能（`load_events` 在 `:73`，`read_position` 在 `:439`）；16.3 / 工单 08 的「只留 w > 0 的行」和旧训练器的判据（`callgen:448` 的 `r[5]` 是有无 LM 目标）不是同一条，share_data 的行全部有目标、`w = float(r["w"])` 是数据权重，这份数据 val / train 的 w 全是 1.0，过滤是空操作。

**2026-08-28 晚，plan-8-28 第二次修订（07907db，原话照录）。** 「第二次修订已提交（07907db），wave5（工单 07 到 11 并行）已发射；你的 6 条全部采纳（smoke 用 `--mem-probe-pick tokens`、b06 换 `smoke2/smoke3`、`excluded_idx` 按候选行剔且整个事件没有候选行才不判分、516 次更新、落点改 `_pad16` 之后、抽样不过滤），另外 opus 四视角审阅整理出 20 条也一并改了（`full_token_ids/n_full_tokens` 拆层、cparam 两套提示取最大值加 `n_left_truncated_by_tag`、`--head mbert` 只支持 left、全集只在 tokens 模式装、`select_keys/event_full_texts` 放 share_data、readonly→overlong→limit 顺序、`loop_group` 字段定义、run_id 自检与 `--piece` 占位、报表列动态、决定 31 改成默认值这一轮不改、静默点 #35 #36、工单 12 头部改七条 notes 与 ACCEPT_EVAL）。助手 2 第九节（b106d64）定了决定 29（网格全参 {1e-5, 5e-5, 2e-4}、LoRA ×10）、决定 30（l4 开检查点上 H100 ×3，b17 不开上 H200 ×3 收完接 l17，b06 开检查点上 Ada ×3，预算都 16384）、`cost` 探针改三块加并列规则、`--gen-eval-at last`。」

### 决定 29（写在 spec §16.6，提交 07907db；依据 design-attention 9.7，b106d64；照抄 spec 原文）

「每个配置三个学习率（决定 29，按 8-28-assistant-2 第九节 9.4：全参 `1e-5, 5e-5, 2e-4`，LoRA 逐点乘 10 `1e-4, 5e-4, 2e-3`，四个底座按训法各用一套、不按底座改——三个锚点是旧值 1e-5、平方根规则 3.4e-5、总位移相等 1.8e-4，相差 18 倍，跨度从最小版的 5 倍放到 20 倍，下端留旧值当对照；最好点落在边上就往那边再加一档）」。 / 理由与依据：design-attention.md 9.7（三个锚点的算法：旧训练器一次更新 32 行对新训练器平均 361 行是 11.3 倍，平方根 3.4；旧调度 epoch 0 的学习率积分是峰值的 4,653 倍对新调度整程 258 倍，比值 18.0）。8-28-assistant 注：spec 原文写的出处「第九节 9.4」，网格那一问在 9.7，9.4 是排卡。

### 决定 30（写在 spec §16.8，提交 07907db；依据 design-attention 9.1 到 9.4，b106d64；照抄 spec 原文）

「12 个 run 按决定 30 排卡（8-28-assistant-2 第九节 9.1 的显存模型：固定项 + 每 token 2.44 MB + 每损失位 1.8 MB，校验整程峰值块算 58.5 对实测 58.47；峰值乘 1.1 后对卡容量：b06 不开检查点 64.4 GB、开检查点 26.2；b17 不开 108.9 只能 H200、开 50.7；l17 不开 86.5 上 H100 只余 13%、上 H200 57%、开 28.3；l4 只能开检查点 47.2）：l4 开检查点上 H100 三张（估 2 到 2.7 小时，整批的墙钟由它定），b17 不开检查点上 H200 三张（估 66 到 75 分钟），b17 收完 H200 三张接 l17 不开检查点（估 60 到 70 分钟），b06 开检查点上 Ada 三张（估 2.1 到 2.4 小时）；四个配置 `tok_budget` 都是 16384（块序列一致）。」 / 理由与依据：design-attention.md 9.4 的排卡表与方案乙（assistant-2 推荐乙：l4 三个 run 无论怎么排都要 2 到 2.7 小时，乙把其余九个压到 l4 的长度以内）。8-28-assistant 核对：spec 里的八个峰值数与 9.4 表格的「乘 1.1」列逐个相同，四个配置的卡与时长和方案乙逐项相同。

### 决定 31 更正（07907db）

b7dbbea 版的决定 31 是「cgen 扫出来的值按训法（全参 / LoRA）写成默认值，cparam 沿用」；07907db 改成（spec §16.1 与 §16.11 原文）：「决定 31，扫描结果只进报表，代码默认值这一轮不改（16.11），cparam 与 ctool 不单独扫」；§16.11：「改学习率默认值：决定 31——扫描结果只进 `SWEEP_REPORT` 与汇报，这一轮不改代码默认值（`FULL_LR` / `lora_util` 的 `DEFAULT_LR` 是 `invariants.md` 锁的口径，改动等于新老数字不可比，要动 invariants、换批次前缀、补 TIMELINE，由 gyb 看完对比再定）；cparam 与 ctool 不单独扫，要不要扫列进汇报。」 / 理由：spec 原文里那句括号。依据：plan-8-28 消息里「决定 31 改成默认值这一轮不改」是 opus 四视角审阅的 20 条之一。

**2026-08-28 晚，第三遍审查（8-28-assistant，对 07907db，spec 层面；wave5 已发射，这一遍的发现按 plan-8-28 的说法在收账时当补丁清单）。** 新引的行号全部对得上当前代码（`eval_causal_param.py` 403-404 / 429 / 432-433 / 440 / 446，`eval_causal_call.py` 378 / 495-497 / 576-582，`eval_tool.py` 353-360，`train_causal_tool.py` 177-184，`launch_cmd.py` 136，`extending.md` 123，`stage-commands.md` 517，`ACCEPT_EVAL.md` 第 5 到 7 行，`summarize_matrix.py` 58 / 69）；决定 30 的八个峰值数与四个配置的排法和 9.4 逐项相同。发现 9 条发给 plan-8-28，最重的一条：16.8 三个新配置的 smoke 命令行只写了 `--smoke --mem-probe --mem-probe-pick tokens --gen-eval 200`，没写配置自己的 `--base / --lora / --grad-ckpt`，而 `tokens` 探针踩的是全集最满块，l4 不开检查点按 9.4 表在任何卡上都装不下（峰值估计 152 GB），smoke 命令不带 `--grad-ckpt` 就在探针处 OOM。其余：16.8 生成评估 KV 缓存「0.6B 约 1 GB」按 9.1 的配置算是 28 层 × 8 个 KV 头 × 128 × K 与 V 两份 × bf16 2 字节 = 114,688 字节每 token，乘 8 × (8,096 + 96) 个 token 是 7.5 GB（4B 的 36 层算出来 9.7 GB，spec 写的 10 对）；16.2「readonly → overlong → limit」的顺序要求分词器在 `--limit`（`:582`）之前加载，现在加载在 `:587`，spec 没写要提前；16.3 日志一条的 `start` 字段漏 `gen_eval_at`（工单 08 有）；16.9 工单 10 那条还是「5 个事件挑两块」（工单 10 已改 6 个事件三块）；16.9 工单 08 (a) 没带 `--gen-eval-at all`，默认 `last` 下只有最后一次评估有那三个键；16.5 `loop` 的组是「含损失位最多那一块」，9.5 的建议是「含代价最大块的那一组」并且建议 `loop` 可以不做；16.7 invariants 那条「默认带生成式评估 200 行」要补「只在 epoch 末」；16.6 报表列 `val_exact_call(best 那一点)` 在 `last` 模式下只有 epoch 末那次有值，best 不在末点时这一列是空。

### 决定 32（plan-8-28 消息原话，spec §16.5 写在 073382c）

「决定 32——`loop` 探针改成对 `cost` 挑出的三块各跑一组取大者（助手 2 核：真峰块在第 490 组、损失位最多块在第 475 组，只跑后者在不开检查点的配置上低约 6%），工单 10 发射时写的是旧规则，收账时由主会话改代码；第三块的 kind 定名 `max_cost_block`。」spec §16.5 原文：「`loop`：对 `cost` 挑出的三块（`max_tokens_block / max_losspos_block / max_cost_block`）各找到它所在的更新组（连续 `accum` 个逻辑小批），每组照训练循环原样跑一次更新、取三组的大者（8-28-assistant-2 核：epoch 0 的真峰块在第 490 组，损失位最多的块在第 475 组，只跑后者在不开检查点的配置上比真峰低约 6%；开检查点的配置两者是同一块）。工单 10 发射时写的是「只跑含损失位最多块的那一组」，收账时按这条改（决定 32）。」 / 理由与依据：design-attention.md 9.2（第 490 组与第 475 组两块的位置、6% 的差）与 9.5；来历是 8-28-assistant 第三遍审查第 7 条（`loop` 的组规则与 9.5 有出入）。

**2026-08-28 晚，073382c 的两处 16.8 更正（plan-8-28 消息原话）。** 「spec 16.8 两处按助手 2 更正：生成评估 KV 缓存 0.6B 是 7.4 GB（不是 1 GB，结论不变），`tokens` 探针冒烟的对照值改用四个预期值（b17 94.9、l17 74.5、l4 38.1、b06 17.9）而不是估计表里的数。」spec 16.8 第 330 行原文：「三个新配置用 `tokens` 探针冒烟时，`worst_gb` 会系统性低于 9.4 表里的估计（`tokens` 挑的是全集两个最长事件拼成的块，16,384 个 token 只有 1,984 个损失位，比真峰块少 2,300 到 3,700 个损失位），对照值按 8-28-assistant-2 给的预期：b17 不开检查点 94.9（表 99.0）、l17 不开 74.5（78.6）、l4 开检查点 38.1（42.9）、b06 开检查点 17.9（23.8）；冒烟数和这四个预期值对，不和表里的数对。」

8-28-assistant 核对：四个预期值在 design-attention.md 里没有原文（只经消息转来），按 9.1 的系数和 8.6 记的 `tokens` 最满块形状（16,384 个 token、1,984 个损失位）重算：b17 不开检查点 30.97 + 3.68 × 16.384 + 1.8 × 1.984 = 94.8，l17 不开 10.60 + 60.29 + 3.57 = 74.5，l4 开检查点 24.66 + 0.60 × 16.384 + 3.57 = 38.1，b06 开检查点 10.86 + 0.21 × 16.384 + 3.57 = 17.9，四个数都能从 9.1 复现；「少 2,300 到 3,700 个损失位」是 4,271 − 1,984 = 2,287 与 5,696 − 1,984 = 3,712。KV 缓存 7.4 GB 是 8 × 8,096 个提示 token × 114,688 字节（不含 96 个新 token；含则 7.5）。第三遍审查 9 条里的第 2 条（KV 数）与第 7 条（`loop` 组规则）由这次提交处理。

**2026-08-28 晚，plan-8-28 对第三遍 9 条的处理（321d8bd，原话照录）。** 「9 条处理完（`git log -1`）：1 smoke 命令改成带 `GRID` 里该配置的 `--base/--lora/extra` 并按决定 30 的卡种；2 KV 改 7.5 / 9.7 GB；3 spec 写明 tokenizer 与 max_len 提前到 `--limit` 之前——工单 07 发射时没这句，收账时按补丁清单查实现者的顺序；4 `start` 加 `gen_eval_at`；5、6 16.9 两条对齐工单；7 `loop` 在 073382c 已改成 cost 三块各跑一组取大者（决定 32），你审的 07907db 是改前的；8 invariants 写 `--gen-eval-at last`；9 报表 `val_exact` 列取有值的点并标 frac。收账补丁清单目前两条：工单 07 的筛选顺序（tokenizer 提前）、工单 10 的 loop 三组规则。」

8-28-assistant 核对（321d8bd 对 073382c，spec.md 7 处改动）：16.2 加了「把 tokenizer 与 `max_len` 的读取提前到 `--limit` 之前（cparam 第 411 到 420 行同样），不许把筛选放到 `--limit` 之后」；16.3 的 `start` 三个键与 `last` 模式下中间评估点不写三个键；16.6 报表 `val_exact_call(有值的那个评估点的值并标出它的 frac)`；16.7 invariants 写 `--gen-eval 200 --gen-eval-at last`；16.8 smoke 命令加「该配置在 `GRID` 里的 `--base <base> [--lora] <extra>`」并按决定 30 的卡种，KV 缓存改成 65,536 个 token × 每 token 0.115 MB（28 层）= 7.5 GB、4B 0.147 MB = 9.7 GB；16.9 工单 08 (a) 带 `--gen-eval-at all --eval-per-epoch 2`。收账补丁清单（wave5 发射后 spec 改动、工单原文没跟上的）：工单 07 的筛选顺序（tokenizer 提前到 `--limit` 之前）、工单 10 的 `loop` 三组规则（决定 32）。

**2026-08-28 晚，wave5 收账（plan-8-28 报，原话照录）。** 「wave5 收账完，请记台账。五张全部 DONE：07（1 轮修复，base 07907db head eadb3f8，合并 df14ccd）、08（0 轮，head b8a31f2，合并 3d17e3f）、09（0 轮，head ebbf4e2，合并 d1642bb）、10（0 轮，head e272ffd，合并 12b998c，`start_kw` 一处冲突手解——08 的三个 gen 键与 10 的 mem_probe_pick 都留）、11（1 轮，base 073382c head e0677fc，合并 0ce99d4）。ticket-run Phase 3 写「合并起冲突就停下报告用户」，这次的冲突是两张工单在同一个字典各加自己的键，我按 gyb「中途你先自己做决定」解了，记成决定 33。收账补丁：决定 32 的 loop 三组规则由我直接改代码（19d92e9，每组一条 `mem_probe` 带 `group_of`，summary 加 `worst_group_of`），顺手修了三种模式 `worst_kind` 在峰值全 0 时停在 None（并列取第一块）；补丁 1（tokenizer 提前）核过实现者的顺序本来就对。裁决与遗留都写在五张工单的 Comments（ed88ad7）。合并后 selfcheck 77 个任务、四个新测试文件 30 个用例 OK、全量 discover 在后台跑。已发 wave6（工单 12 文档）和五个 GPU 冒烟（b17/l17 H200、l4 H100 带检查点，探针 tokens；b06 smoke2 cost、smoke3 loop）。」

### 决定 33

ticket-run Phase 3 写的是「合并起冲突就停下报告用户」；wave5 工单 10 合并时 `train_causal_share.py` 的 `start_kw` 字典一处冲突（工单 08 加的 `gen_eval / gen_bs / gen_eval_at` 与工单 10 加的 `mem_probe_pick` 落在同一段），plan-8-28 按 gyb「中途你先自己做决定」自己解了：两边的键都留。 / 理由：冲突是两张工单在同一个字典各加自己的键，没有语义分歧。 / 依据：合并提交 12b998c 的提交信息；gyb 2026-08-28 晚原话「你先选项的代码先实现好」与「中途你先自己做决定」（后一句在 plan-8-28 的消息里引述，我这边没有 gyb 直接的原文）。

8-28-assistant 核对（23:11，HEAD ed88ad7，工作树干净）：消息里的十二个提交号全部在 log 里且提交信息相符（工单 07 的一轮修复是 530c997「修复 F1/F2 ctool 剔除行接线」加 eadb3f8「补 F3 回归测试」；工单 11 的一轮是 e0677fc「补测 worst_gb 兼容旧探针分支」）；五张工单 Status 都是 resolved，工单 12 仍 ready-for-agent；`python3 run.py selfcheck` 输出「77 任务 / 4 配方 / 3 预设, 全部就位」；`tests/` 里五个新测试文件（test_eval_overlong、test_share_gen_eval、test_align_rules、test_mem_probe_pick、test_sweep_lr）都在；合并后 `train_causal_share.py` 第 1035 到 1042 行的 `start_kw` 同时有 `gen_eval / gen_bs / gen_eval_at / mem_probe / mem_probe_pick / align_rule`。「30 个用例 OK」「全量 discover 在后台跑」两句我没有复跑，照消息记。五个 GPU 冒烟：消息说已发，但 23:11 时 `ops/jobs.json` 的 active 是空列表、`ops/runs.jsonl` 最后一条仍是 15:23 的终验 finish、`logs/` 里没有 b17 / l17 / l4 / smoke2 / smoke3 的日志——收账提交 ed88ad7 是 23:09:32，发射可能还在进行；这一条等三处登记出现后再补记。plan-8-28 回复是第一种：发射员（gpu-runner）正在逐个用 `python3 run.py launch --cmd ... --run-id ... --track kvshare-train --outdir ... --piece tokyo108:<gpu>` 发，不是手搓。8-28-assistant 23:12 复查：`logs/new1_ks828b17_gptoss_cgen_smoke_t108g3.log` 已在（23:11:38 建，0 字节），`ops/jobs.json` active 有 `ks828b17_gptoss_cgen_smoke` 一条，`ops/runs.jsonl` 有它的 start；其余四个等发射员回执到了再记。

**2026-08-28 晚，五个冒烟的结果（plan-8-28 报，原话照录）。** 「五个冒烟的事实（`verify/smoke_check.py` 读的，run 目录在 pipeline/runs/smoke/）：b17（H200，不开检查点，tokens）对齐 PASS 9.06e-6，探针最满块 98.25 GB 对预期 94.8（+3.6%），×1.1 = 108.1，step 峰值 70.42，val_ce 1.59，81 行生成 86.4 s，wall 818.8 s；l17（H200，LoRA，tokens）对齐 9.06e-6，最满块 77.62 对 74.5（+4.2%），×1.1 = 85.4，step 峰值 49.92，val_ce 1.3977，生成 90.5 s，wall 877.7；b06 smoke2（cost）worst 15.35（max_tokens_block，预期 15.4）、smoke3（loop 两组）worst 15.22（worst_group_of max_losspos_block+max_cost_block），两者 val_ce 1.2917 / val_exact_call 0.1728 逐位相同，对齐 5.48e-6 与第一轮四份逐位相同；l4（H100，LoRA+检查点，tokens）对齐 PASS 1.54e-5（容差 2e-5，余量 1.3 倍）之后在探针第一次反向崩：`CheckpointError: Recomputed values ... have different metadata`（[2,32,8192,8192] 对 [2,1,8192,8192]，cpu 对 cuda）。根因：grad-ckpt 的重算发生在 `.backward()` 里，`_attn_ctx` 只包了前向，重算走默认内核。修法（决定 34）：`backward_logical_minibatch` 与 `_fwd_bwd_block` 的 `.backward()` 也套 `_attn_ctx`，守卫测试允许的调用点改成这三个函数，spec 16.3 与静默点 #37，提交 b5cee8d；受影响的三个测试文件 31 个用例 OK。五条台账已 `record finish` + `gpu-jobs finish`（l4 那条记 crashed=1）。已重发 `ks828l4_gptoss_cgen_smoke2`（H100 gpu0）和 `ks828b06_gptoss_cgen_smoke4`（H100 gpu1，开检查点、tokens，给 Ada 排卡的实测数）。请记台账；另外请你留意 l4 的对齐差 1.54e-5 离 2e-5 只有 1.3 倍，这是给 gyb 第七件（容差）的一条新事实，汇报里要写。」

### 决定 34

`--grad-ckpt` 的重算发生在 `.backward()` 里，`_attn_ctx` 只包前向时重算走默认内核，torch 报 `CheckpointError`；修法是 `backward_logical_minibatch` 与 `_fwd_bwd_block` 的 `.backward()` 也套 `_attn_ctx`，守卫测试允许的调用点改成前向一处加反向两处，spec 16.3 与静默点 #37。 / 理由：l4 冒烟实测（`ks828l4_gptoss_cgen_smoke`，探针第一次反向就崩）。 / 依据：`logs/new1_ks828l4_gptoss_cgen_smoke_t108g0.log` 第 49 到 56 行；提交 b5cee8d（spec.md 3 行、train_causal_share.py 15 行、test_share_gen_eval.py 15 行）。

8-28-assistant 核对（23:41，读五个目录的 `ALIGN_CHECK.json` 与 `train_log.jsonl`、崩溃日志、runs.jsonl）：消息里的数逐个对得上文件——b17 `max_abs_diff` 9.06e-6（逐 token 6.20e-5，6 事件 154 行，tol 2e-5，rule abs）、`fullest_block` 98.245 GB（B=2、L_pad 8,192、16,384 token、1,984 损失位、两次反向）、`longest_event` 70.421（L_pad 9,504）、四次 val_ce 1.9731 / 1.7464 / 1.6327 / 1.59、epoch 末 `val_exact_call` 0.1852（gen_n 81，gen_s 86.4）、wall_s 818.81；l17 对齐同 b17 的 9.06e-6（对齐在 LoRA 包装之前，同底座同样本）、fullest 77.618、longest 49.921、val_ce 2.2094 / 1.7973 / 1.5276 / 1.3977、exact 0.1852（81 行，90.52 s）、wall 877.7；smoke2 `cost` 三块 `max_tokens_block`（B=4、L_pad 400、1,600 token、355 损失位）15.345、`max_losspos_block` 与 `max_cost_block` 同一块（B=4、L_pad 384、388 损失位）15.254，summary worst 15.345 / scope run；smoke3 `loop` 两组 15.219（group_of `max_losspos_block+max_cost_block`）与 15.059（`max_tokens_block`），worst 15.219；smoke2 与 smoke3 的四次 val_ce（1.7044 / 1.4555 / 1.3365 / 1.2917）、exact 0.1728、五条 step 的 `grad_norm`（68.0955 / 70.4724 / 46.029 / 38.2472 / 49.3397）逐位相同，对齐 5.48e-6 与第一轮相同；l4 对齐 PASS 1.538e-5（逐 token 9.82e-5），日志里没有 step 与 mem_probe 事件，崩溃日志第 51 到 56 行三组张量：位置 37 是 [2, 32, 8192, 8192] 对 [2, 1, 8192, 8192]（都在 cuda:0），位置 41 是 [2, 32, 8192] 对 [2, 32, 8192, 1]，位置 43 是 cpu 的 int64 标量对 cuda——消息里「cpu 对 cuda」指的是位置 43，不是形状那一对；runs.jsonl 五条 finish 都在（23:40），l4 那条 `status` 字段写的是 ok、`metrics.crashed` 是 1。预期值的核算：98.245 / 94.83 = 1.036，77.618 / 74.46 = 1.042；b06 smoke2 的「预期 15.4」按 9.1 的系数对那一块算是 10.86 + 2.44 × 1.6 + 1.8 × 0.355 = 15.40。

8-28-assistant 注（消息里没有的一条，发给 plan-8-28）：四个跑完的 run 里 gstep 1 的 `peak_mem_gb` 都恰好等于探针最后一块的峰值——b17 70.421（= longest_event）、l17 49.921（= longest_event）、smoke2 15.254（= 最后一块 max_cost_block）、smoke3 15.059（= 最后一组 max_tokens_block）；gstep 2 到 5 才是训练自己的数：b17 37.764 / 37.767 / 38.021 / 38.022，l17 17.322 / 16.775 / 17.474 / 17.001，smoke2 14.924 到 15.091，smoke3 14.931 到 15.092。探针每块跑之前归零峰值计数器，探针结束到第一次 step 日志（`train_causal_share.py` 第 1131 到 1133 行读峰值后才归零）之间没有归零，所以第一条 step 的峰值是探针带过来的。消息里的「step 峰值 70.42 / 49.92」是这个数，不是训练 step 的峰值；b17 smoke 的训练 step 峰值是 38.0 GB。重发的 `ks828l4_gptoss_cgen_smoke2` 与 `ks828b06_gptoss_cgen_smoke4` 到 23:41 在 `logs/`、`jobs.json` active、runs.jsonl 里都还没有。五个目录的 RUNMETA.json（`launches` 列表）记的 commit：b17 是 b7ff390，其余四个是 35fd401，都 dirty false——也就是决定 32 的补丁 19d92e9 之后、b5cee8d 之前的代码；l4 的崩溃是在 b5cee8d 之前的代码上，符合消息的说法。

**2026-08-28 晚，plan-8-28 对三条注记的处理（原话照录）。** 「三条都处理：探针返回后归零峰值计数器（根因修，`main()` 里 `run_mem_probe` 之后加 `reset_peak_memory_stats`，提交在 `git log -1`），记决定 35，读法注记「带 --mem-probe 的 run 第一条 step 的 peak_mem_gb 在此提交之前是探针最后一块的数」进汇报与 stage-commands 的补丁清单（工单 12 正在跑，我在它收账时补这一句）；l4 那条 finish 用 `--status fail` 追加了一条（runs.jsonl 只增不改，RESULTS.md 按最新一条渲染）；「cpu 对 cuda」按你核的记（位置 43 的 int64 标量）。l4 smoke2 与 b06 smoke4 的登记出现后你补记。」

### 决定 35

`main()` 里 `run_mem_probe` 返回之后归零峰值计数器（`torch.cuda.reset_peak_memory_stats()`），带 `--mem-probe` 的 run 第一条 step 的 `peak_mem_gb` 才是训练自己的数；此提交之前的 run（第一轮全部与本轮五个冒烟）第一条 step 的 `peak_mem_gb` 是探针最后一块的数，读法注记进汇报与 stage-commands。 / 理由：根因修。 / 依据：8-28-assistant 从五个冒烟的 gstep 1 核出（上一条注记）；提交 479aa4b（train_causal_share.py 加 4 行，同一提交把 runs.jsonl 里 l4 smoke 的 finish 追加一条 `status: fail`，23:43）。

8-28-assistant 核对与补记（23:47）：479aa4b 的改动是 `if dev.startswith("cuda"): torch.cuda.reset_peak_memory_stats()` 四行，注释写明来历；runs.jsonl 里 `ks828l4_gptoss_cgen_smoke` 现在有两条 finish（23:40 status ok、23:43 status fail「同一 run 的补记」），旧的一条没改。两个重发冒烟的三处登记已出现：`ks828l4_gptoss_cgen_smoke2`（runs.jsonl start 23:41，日志 `logs/new1_ks828l4_gptoss_cgen_smoke2_t108g0.log` 23:45 在写，命令带 `--base qwen4 --lora --grad-ckpt`）与 `ks828b06_gptoss_cgen_smoke4`（start 23:42，日志 `_t108g1.log` 23:43 在写，命令带 `--base qwen --grad-ckpt --log-every 1`），jobs.json active 两条，两个 RUNMETA 记的 commit 都是 5abd3a0、dirty false——在决定 35 的 479aa4b 之前，所以这两个 run 的第一条 step 峰值仍是探针带过来的数，读结果时要跳过 gstep 1。

另有一条时间线事实：4622eb7 是 assistant-2 写的 design-attention 9.8 节（冒烟对第九节的校准），要点照原文：1.7B 不开检查点的每 token 系数从 b17 / l17 四个实测点反推是 3.89 / 3.90 / 3.87 / 3.88，取 3.88 MB（9.1 推的 3.68 低 5%）；用 3.88 重算 b17 不开检查点真峰 102.2 GB、乘 1.1 是 112.5（H200 75%，H100 装不下），l17 81.9、乘 1.1 是 90.0（H100 只余 10% 不能上，H200 60%）；plan-8-28 消息里的 108.1 与 85.4 是 tokens 块实测直接乘 1.1，少了 4.1 GB 的损失位差额，落卡结论相同，决定 30 维持；l4 的 CheckpointError 判读是前向走 efficient、反向里的检查点重算走了 H100 默认的 cuDNN（位置 41 的 [2, 32, 8192] 是 efficient 的 logsumexp 形状、[2, 32, 8192, 1] 是 cuDNN 的；位置 37 是 expand 后的掩码视图，存储仍是 268 MB，不是 8.6 GB 的分数矩阵）；三个底座的逐行对齐差 5.48e-6 / 9.06e-6 / 1.54e-5 是 1 / 1.65 / 2.8 倍，同卡型逐位可复现（b06 六个 run 三张 H100 逐位相同、b17 与 l17 两张 H200 逐位相同），建议 l4 在 GRID 的 `extra` 里显式带 `--align-tol 3e-5`（23% 的余量太薄，3e-5 离 1e-2 的真错仍差 300 倍）；`verify/smoke_check.py` 的 1.7B 系数已改 3.88。这些是 assistant-2 的判读；l4 的容差 plan-8-28 随后定为决定 36（下一条）。两个重发 run 记的 5abd3a0 含 b5cee8d 的修法（`git merge-base --is-ancestor` 核过），在 479aa4b 之前。

### 决定 36（plan-8-28 消息原话）

「决定 36——l4 在 GRID 的 extra 显式带 `--align-tol 3e-5`（4B 对齐差 1.54e-5 离 2e-5 只 23% 余量；助手 2 9.8 节：三个底座的差随层数与累加长度单调涨、同卡型逐位可复现，b06 六个 run 全 5.4836e-6、b17/l17 两张 H200 同 9.0599e-6，放宽是给换卡型或换 torch 留余量），b06/b17/l17 不动。排卡数修正（9.8）：1.7B 每 token 系数 3.88 MB，b17 真峰 102.2 乘 1.1 是 112.5（H200 75%），l17 81.9 乘 1.1 是 90.0（只能 H200），排法维持。GRID 与 spec 的改动在下一条提交。」 / 理由与依据：消息里已写；design-attention 9.8 第三段（`ks828l4_gptoss_cgen_smoke/ALIGN_CHECK.json` 的 1.537799835205078e-05）。8-28-assistant 注：b06 六个 run 全 5.4836e-6 与 b17 / l17 的 9.0599e-6 我在五个冒烟目录里核过（smoke2 / smoke3 与第一轮四份都是 5.4836273193359375e-06，b17 与 l17 都是 9.059906005859375e-06）；这是给 gyb 第七件（容差）的新事实：容差又多了一档自定值（l4 3e-5），汇报要写。GRID 与 spec 的改动是 8f69002（23:48：`sweep_lr.py` 第 45 行 l4 的 `extra=["--grad-ckpt", "--align-tol", "3e-5"]`，第 43 行注释写了理由；spec 16.6 / 16.8 记决定 36 与 9.8 的排卡修正数），8-28-assistant 核过。

**2026-08-28 夜，wave6 收账（plan-8-28 报，原话照录）。** 「wave6 收账：工单 12 DONE 0 轮（base ed88ad7 head 4f10aec，合并 1998522，无冲突），评审两条 minor（extending §5 新行带 `#` 前缀与旧行不一致、#30 位序 7 对 6 混记）和实现者两条 concern（#35/#36 未进 extending、交叉引用指向 spec）我在合并后直接改：新行去前缀、#30 改「从 0 数的第 6 位」、补 #35 到 #37、stage-commands 的 loop 说明改决定 32 的三组规则、§3.1 加读法④（决定 35），收账提交 caf29de，selfcheck 77。ticket-run Phase 4 终审已派 opus（起点 07907db 终点 caf29de，含四个工单外的直接改动 19d92e9 / b5cee8d / 479aa4b / 8f69002）。」

8-28-assistant 核对：4f10aec（23:44「T12: 自查修复——extending §5 #35/#36 空指改指 spec 16.10」）、1998522（23:56 合并工单 12）、caf29de（23:58 收账）、8f69002（23:48 决定 36）四个提交都在；工单 12 Status resolved；`python3 run.py selfcheck` 77 任务；`extending.md` §5 第 296 到 303 行是 #30 到 #37，#30 那行写「从 0 数的第 6 位」，#35 到 #37 各一行；`stage-commands.md` 第 230 行的 `--mem-probe-pick` 参数行与第 295 行的读法段 grep 命中「三组」与「决定 35」。终审的结论等 plan-8-28 报了再记。

**2026-08-29 00:06，两个重发冒烟收官（plan-8-28 报，原话照录）。** 「两个重发冒烟收官（e658f56，RUNMETA 记 5abd3a0，含 b5cee8d 的修法）：l4 smoke2（H100，LoRA+检查点，tokens）零 Traceback，对齐 PASS 1.5378e-5 与崩掉那次逐位相同，探针最满块 28.82 / 最长事件 23.89 GB（预期 38.1，低 24%），step 峰值 gstep 2 到 5 是 18.74 / 33.09 / 33.19 / 33.18（gstep 1 的 23.885 是探针带的；33 那三条我判是每个评估点 save_merged 的 fp32 副本 16 GB，已发助手 2 核），val_ce 1.5572 → 0.7443，val_exact_call 0.1975，生成 81 行 35.66 s，wall 1003.4 s；b06 smoke4（H100，全参+检查点，tokens）探针 15.84 / 13.85（预期 17.9，低 11.5%），step 峰值 12.0 上下，val_ce 与 val_exact_call 和不开检查点的 smoke2 逐位相同（1.2917 / 0.1728），wall 663.3 s。全量单测在最终代码上后台重跑中，终审在跑。」

8-28-assistant 核对（读两个目录的 `ALIGN_CHECK.json`、`train_log.jsonl`、`RUNMETA.json`，两份日志，runs.jsonl）：数逐个对得上。l4 smoke2：对齐 1.537799835205078e-05（逐 token 9.82e-5，154 行），与崩掉那次的 ALIGN_CHECK.json 逐位相同；`fullest_block` 28.822（B=2、L_pad 8,192、1,984 损失位）、`longest_event` 23.885（L_pad 9,504）；step 1 到 5 的 `peak_mem_gb` 是 23.885 / 18.737 / 33.089 / 33.185 / 33.18；四次 val_ce 1.5572 / 1.1088 / 0.8522 / 0.7443（每次都创新低，best_frac 4）；epoch 末 exact 0.1975（81 行，35.66 s）；wall_s 1003.39；日志里 Traceback 0 处。b06 smoke4：`fullest_block` 15.836、`longest_event` 13.849；step 1 到 5 是 13.849 / 12.01 / 12.002 / 12.006 / 12.014；四次 val_ce 1.7044 / 1.4555 / 1.3365 / 1.2917、exact 0.1728 与 smoke2 / smoke3 逐位相同（开检查点不改数值，spec 16.8 那句在这份数据上成立）；gen_s 69.36；wall_s 663.31；Traceback 0 处。两个 RUNMETA 都是 5abd3a0、dirty false；runs.jsonl 两条 finish 在 00:06。事实层面的一条补充：l4 smoke2 日志里 step 3、4、5 各是紧接在 eval frac 1、2、3 之后记的第一条 step（时间戳 …885.7 / …017.0 / …153.6，各在 eval …735.6 / …886.0 / …017.3 之后），而 step k 的峰值窗口从 step k−1 记日志时归零起算，所以 33 GB 这三条的窗口都含一次评估加一次存最好版本；「是 save_merged 的 fp32 副本 16 GB」是 plan-8-28 的判读，等 assistant-2 核。探针对预期的差：28.82 对 38.1 是低 24.4%，15.84 对 17.9 是低 11.5%（9.1 的开检查点系数 0.60 / 0.21 是外推值，9.8 说等实测再校）。另见 jobs.json active 里新出现一条 plan-8-28 消息里没提的 run：`ks828b06_ovl_skip_ctool`（runs.jsonl start 00:06，命令是 `eval_tool.py --head causal --env appworld --run pipeline/runs/smoke/ks828b06_gptoss_ctool_final_smoke --data pipeline/data/nyapass_aw_v1/gptoss --over…`，日志 `logs/new1_ks828b06_ovl_skip_ctool_t107g0.log` 00:07 在写），看名字是 ctool 评测在 `--overlong skip` 下的一次 GPU 验证，用途等 plan-8-28 说明。

**2026-08-29 00:08，`--overlong` 端到端 GPU 验证（plan-8-28 说明，原话照录）。** 「是的，那是 `--overlong` 三种模式的端到端 GPU 验证（工单 07 的运行时行为，spec 16.8 之外、任务 #12「验证」里的一项）：发射员在 tokyo107 一张 Ada 上串行跑六个 run，顺序 left → skip → drop-event，每个模式先 `eval-tool-causal --limit 200` 写进 `ks828b06_gptoss_ctool_final_smoke`（run_id `ks828b06_ovl_<mode>_ctool`），再 `eval-ccall --limit 200`（`--ctool-run` 那个目录、`--cgen-run ks828b06_gptoss_cgen_smoke2`，run_id `ks828b06_ovl_<mode>_ccall`），每轮的 REPLAY_REPORT / 报告 / `.meta.json` 复制到 `/home/y-guo/.claude/jobs/b39c625e/tmp/ovl/<mode>/` 留对照，六条各自 `record finish` 与销号。你看到的是第二轮（skip）的 ctool 那一步，left 那两条应该已经在 history 里。六个都收完我把三种模式的计数表发你。」

8-28-assistant 核对（00:08）：jobs.json history 里 ovl 的条目是 `ks828b06_ovl_left_ctool` 与 `ks828b06_ovl_skip_ctool` 两条，runs.jsonl 的 start / finish 也只有这两条（left 23:59 → 00:02，skip 00:06 → 00:08），没有 `ovl_left_ccall`；对照目录里 `left/ctool/` 与 `skip/ctool/` 各有 REPLAY_REPORT.json/.md 与两份 `.meta.json`，三个模式的 `ccall/` 子目录都还是空的——实际顺序到 00:08 是 ctool left → ctool skip，不是消息说的每个模式先 ctool 再 ccall。两份 REPLAY_REPORT.json 的计数：left 与 skip 都是 `n_oow` 0、`n_skipped_bounds` 0、`n_dropped_events` 0、`n_dropped_bounds` 0、`n_events_test` 7、`limit` 200；两份 `logits_test.meta.json` 与 `logits_val.meta.json` 都是 `rows` 200、`excluded_idx` 空列表，`overlong_mode` 各写 left / skip，权重指纹相同。也就是说 `--limit 200` 取到的 200 行里没有一条边界在 8192 的窗口之外（ctool run 的 meta `max_len` 8192），skip 这一轮走的是零剔除的路径，和 left 的差别只有报告与 meta 里的 `overlong_mode` 一个字段；drop-event 按同样的 200 行也会是零计数。要在 GPU 上看到非零剔除，200 行里得含全文超过 8192 token 的事件——test 集里这样的事件在第几行我没查。这一条已发给 plan-8-28。

**2026-08-29 00:1x，plan-8-28 对上面两条的处理（原话照录）。** 「两条都对。1 顺序：发射员的回执还没到，看它怎么解释；三个 ctool 先跑再跑 ccall 的话，后跑的 ccall 读到的是最后一个模式写的 logits 与 REPLAY_REPORT——这一批六个 run 全是零剔除，所以结果上分不出，但顺序偏差我记进它的 Comments。2 零剔除：这六个 run 只验接线（报告有键、meta 有模式、`--cached-logits` 校验），剔除路径靠工单 07 的 CPU 用例（小 max_len）。要在真实数据上看到非零剔除，我打算再做一组「固定件」：把 ctool 冒烟目录和 cgen smoke2 目录各复制一份（`..._ml2048`），只把 `best/meta.json` 的 `max_len` 改成 2048，同样 `--limit 200` 跑三个模式，200 行里超过 2048 token 的行就会被截 / 剔 / 丢（决定 37：改的是副本不是原 run，副本目录名带 `_ml2048`、不进矩阵）。这一组等六个收完、扫描发射之后在 tokyo107 上跑，不占扫描的卡。」

### 决定 37

`--overlong` 的非零剔除验证用固定件：把 `ks828b06_gptoss_ctool_final_smoke` 与 `ks828b06_gptoss_cgen_smoke2` 两个目录各复制一份、目录名带 `_ml2048`，只把副本的 `best/meta.json` 里 `max_len` 改成 2048，同样 `--limit 200` 跑三个模式；改的是副本不是原 run，副本不进矩阵；等六个 ovl run 收完、扫描发射之后在 tokyo107 上跑。 / 理由：`--limit 200` 在 8192 的窗口下四个计数全 0，验不了剔除路径；把窗口缩到 2048 让同一批 200 行里出现被截 / 剔 / 丢的行。 / 依据：8-28-assistant 00:08 的核对（两份 REPLAY_REPORT 计数全 0、`excluded_idx` 空）。8-28-assistant 注：ovl 六个 run 的顺序偏差（ctool 三个先跑再跑 ccall 的话，ccall 读到的是最后一个模式写的 `logits_test.pt` 与 REPLAY_REPORT）plan-8-28 记进发射员的 Comments，这一批因为全是零剔除结果上分不出。

**2026-08-29 00:2x，design 9.9 进文档、决定 30 两轮冒烟后维持（plan-8-28 报，原话照录）。** 「助手 2 的 9.9 已进文档（70f53dd）：spec 16.8 补开检查点两点重推的系数与扫描真峰（l4 33.7 乘 1.1 是 37.0，b06 22.1 乘 1.1 是 24.3，排法维持），stage-commands §3.1 加读法⑤（LoRA 配置核「固定项 + fp32 底座」不超卡容量，save_merged 副本进墙钟不进排卡）。请记：决定 30 在两轮冒烟后维持，依据 9.8 与 9.9。等终审、全量单测与 ovl 六个 run 的回执到了就发扫描。」

### 决定 30 维持（两轮冒烟之后）

排法不变：l4 开检查点上 H100 三张，b17 不开检查点上 H200 三张收完接 l17 不开检查点，b06 开检查点上 Ada 三张，`tok_budget` 都 16384。 / 依据：design-attention 9.8（5a6c01a 之前的 4622eb7：1.7B 不开检查点每 token 3.88 MB，b17 真峰 102.2 乘 1.1 是 112.5 只上 H200，l17 81.9 乘 1.1 是 90.0 不上 H100）与 9.9（5a6c01a：开检查点的系数与固定项改按两个重发冒烟的实测——l4 每 token 0.549 MB、固定项 16.25 GB，比 9.1 的 24.66 少的 8.4 GB 是冻结权重的 bf16 副本在开检查点时只在重算那一层瞬时存在；b06 每 token 0.122、固定项 10.27；9.1 里 0.6B 开检查点 0.21 MB 的推导作废；扫描真峰 l4 33.7（代价最大块是 15,360 个 token 加 4,992 个损失位）乘 1.1 是 37.0（H100 37%），b06 22.1 乘 1.1 是 24.3（Ada 48%）；`save_merged` 的 fp32 副本时刻 l4 32.3、l17 17.5，都低于各自的训练峰值，不进排卡规则；4B 一次 `save_merged` 126 到 149 秒、四个评估点大概率次次创新低，一个 l4 run 多约 9 分钟进墙钟）。

8-28-assistant 核对：70f53dd 只改两处（spec.md 第 330 行加「重发冒烟之后（9.9）」那一句，stage-commands.md 第 295 行的读法段加⑤），数与 5a6c01a 的 9.9 原文一致。9.9 里对 l4 冒烟 step 3 到 5 的 33.09 到 33.19 的判读是「固定项 16.25 加 fp32 底座副本 16.09 是 32.3，再加评估段的瞬时张量约 0.8；峰值出现在 `save_best` 之后的下一条 step 日志里是因为 step 的峰值计数器在写日志的时候才 reset」——和我上一条记的事实（step 3、4、5 各是紧接 eval 之后的第一条 step，窗口含评估与存档）相合，这是 assistant-2 的判读、plan-8-28 那句「16 GB 是 save_merged 的副本」由它核过。

**2026-08-29 00:2x，ovl 六个 run 收官（plan-8-28 转发射员回执，原话照录）。** 「ovl 六个 run 的事实（发射员回执，台账已由它 finish 销号并提交 eee0a5e）：三个 ctool（`ks828b06_gptoss_ctool_final_smoke`，`--limit 200`，max_len 8192）零 Traceback，四个计数全 0、`n_events_test` 7、`chosen_theta` 两档都 null（calB 只 5 个事件，trig_acc 最高 0.4），三份 REPLAY_REPORT 除 `overlong_mode` 外逐键相同，`logits_test/val.meta.json` 都有 `overlong_mode` 与空 `excluded_idx`；发射员用分词器核过 test/val 各前 8000 行 174/179 个事件没有一个超过 8192。三个 ccall 偏离了我的指令：冒烟组合跑不动（θ null 直接 SystemExit；`--limit` 的 ctool 只写 200 行 logits 而 ccall 读整份 test 391,893 行按下标硬断言），它改用 `np821b06_gptoss_ctool` 全量产物（θ 0.975，max_len 4096）配替身目录 `pipeline/runs/smoke/ovl_ccall_np821b06_cgen/`（只有 `best -> np821b06_gptoss_cgen/best` 软链，np821 原件未动），`--limit 200`：left `n_left_truncated` 56、skip `n_skipped_rows` 56、drop-event `n_dropped_events` 133，`n_excluded_by_ctool` 都 0（旧产物 meta 没有 excluded_idx，按空处理），主指标 left 与 skip 相同（tool_ok 0.91 / params_all_ok 0.905 / full_call_ok 0.855，`n_param_instances` 203 对 201）、drop-event 0.915 / 0.915 / 0.86。顺序偏差：三个 ctool 先跑完再跑三个 ccall（同目录后轮覆盖前轮，`ks828b06_gptoss_ctool_final_smoke/` 现在留的是 drop-event 那轮）。我接受这两处偏离（决定 38：验证目的达到——ccall 三个分支在真实超长事件上走到；ctool 的剔除分支仍靠 CPU 用例加决定 37 的 `_ml2048` 固定件）。副本在 `/home/y-guo/.claude/jobs/b39c625e/tmp/ovl/`。」

### 决定 38

接受发射员的两处偏离：ccall 三轮改用 `np821b06_gptoss_ctool` 全量产物（θ 0.975，max_len 4096）配替身目录 `pipeline/runs/smoke/ovl_ccall_np821b06_cgen/`（只有 `best` 软链到 `np821b06_gptoss_cgen/best`，原件未动）；三个 ctool 先跑完再跑三个 ccall（同目录后轮覆盖前轮）。验证目的算达到：ccall 三个分支在真实超长事件上走到；ctool 的剔除分支仍靠工单 07 的 CPU 用例加决定 37 的 `_ml2048` 固定件。 / 理由：冒烟组合跑不动（ctool 冒烟的 θ 两档都 null 让 ccall 直接 SystemExit；`--limit 200` 的 ctool 只写 200 行 logits，ccall 读整份 test 按下标硬断言）。 / 依据：发射员回执；对照件 `/home/y-guo/.claude/jobs/b39c625e/tmp/ovl/<mode>/{ctool,ccall}/`；提交 eee0a5e。

8-28-assistant 核对（读六份对照件与 runs.jsonl）：三份 ctool REPLAY_REPORT.json 的 `overlong_mode` 各是 left / skip / drop-event，`n_oow / n_skipped_bounds / n_dropped_events / n_dropped_bounds` 都是 0，`n_events_test` 7，`chosen_theta` 是 `{"0.1": null, "0.05": null}`；三份 ccall CALLGEN_REPORT.json：left `n_left_truncated` 56（其余计数 0），skip `n_skipped_rows` 56，drop-event `n_dropped_events` 133，三份 `n_excluded_by_ctool` 0、`limit` 200、`theta` 0.975、`n_events_fired` 2227、`n_events_scored` 200；主指标 left 与 skip 都是 `tool_ok` 0.91 / `params_all_ok` 0.905 / `full_call_ok` 0.855，`n_param_instances` 203 / 201，drop-event 0.915 / 0.915 / 0.86、`n_param_instances` 189；替身目录里 `best` 是到 `/net/…/pipeline/runs/np821b06_gptoss_cgen/best` 的软链加一份 CALLGEN_REPORT.json（00:18，最后一轮 drop-event 的）；`ks828b06_gptoss_ctool_final_smoke/REPLAY_REPORT.json` 现在的 `overlong_mode` 是 drop-event（这个冒烟目录的报告已不是它 finish 时那份）；runs.jsonl 六条 finish 00:02 / 00:08 / 00:10 / 00:14 / 00:16 / 00:18（run_id 里 drop-event 写作 `dropevent`）。一条读法上的事实：三个 ccall 的 `n_events_scored` 都是 200 而 drop-event 丢了 133 个事件，说明 `--limit 200` 是在 `--overlong` 筛选之后取的（spec 16.2 定的顺序），所以三种模式判分的 200 个事件不是同一批事件（skip 去掉 56 行后再取 200，drop-event 去掉 133 个事件后再取 200），三行主指标之间不是同一批样本上的比较；「发射员用分词器核过 test/val 各前 8000 行 174/179 个事件没有一个超过 8192」这一句我没有复算，照回执记。

**2026-08-29 00:3x，ticket-run Phase 4 终审结论与扫描第一阶段发射（plan-8-28 报，原话照录）。** 「终审（opus，07907db..caf29de，自己也跑了全量单测 479 OK 与 selfcheck 77）三条挡合并：F1 cgen/cparam 的 `drop-event` 取全文用的是 `label in label2id` 过滤后的行（`eval_causal_call.py:636`、`eval_causal_param.py:475`），等于 ctool 规则而非 spec 16.2 要的 share_data 规则，超长事件在最大 sent_idx 行 label 不在词表时会静默留下；F2 `--mem-probe-pick tokens` 在 `--readonly-env` 下复用了折叠过的 `tr_events` 却标 `scope=full`（`train_causal_share.py:1064`）；F3 extending #29、spec 16.9 (c)、守卫测试 docstring 三处还是「只许 `_forward_packed` 一处」的旧说法。八条观察里我顺手修四条（sweep_lr 的 `(x is None, x)` 排序在两个 None 时 TypeError；`val_exact(best)` 列改成取有值的点并标 frac；`--piece` 占位改 `<gpus>`；`run_mem_probe` 的清理移进 finally），其余记遗留（eval_tool 判据分词 `add_special_tokens=False` 对实际喂模型的 True，Qwen3 无差；mbert 分支 meta 少四个计数键；`n_left_truncated_by_tag` 在 `--limit` 之前统计；`baseline_warn=True` 分支未被数据走到；`ev_row_idx` 死计算）。决定 39：三条挡合并都不在扫描的运行路径上（扫描不评测、不开 readonly），扫描第一阶段 9 个 run 现在按 HEAD eee0a5e 发（l4 三条 H100 gpu0-2、b17 三条 H200 gpu3-5、b06 三条 tokyo107 Ada gpu0-2），修复由 sonnet 在独立 worktree 做、不脏主树，合并后范围限定复审。l17 三条等 b17 收完发第二阶段。登记回执到了转你。」

### 决定 39

终审的三条挡合并（F1 cgen / cparam `drop-event` 的全文规则、F2 `tokens` 探针在 `--readonly-env` 下标 `scope=full`、F3 三处「只许 `_forward_packed` 一处」的旧说法）都不在扫描的运行路径上（扫描不评测、不开 readonly），扫描第一阶段 9 个 run 按 HEAD eee0a5e 发：l4 三条 H100 gpu0-2、b17 三条 H200 gpu3-5、b06 三条 tokyo107 Ada gpu0-2；修复由 sonnet 在独立 worktree 做、不脏主树，合并后范围限定复审；l17 三条等 b17 收完发第二阶段。 / 理由：消息里已写。 / 依据：终审报告（07907db..caf29de）。

8-28-assistant 核对：F1 对——`eval_causal_call.py:569` 与 `eval_causal_param.py:397` 的 `rows = [r for r in raw_rows if r["label"] in label2id]` 是按词表过滤后的行，第 636 到 637 行与第 475 到 476 行的 `share_data.event_full_texts([r for r in rows if r["event"] in key_set])` 拿的就是这份过滤后的行，取到的「全文」是过滤后最大 `sent_idx` 那一行，spec 16.2 要的是 share_data 不过滤的规则（静默点 #34 记的正是两边的差）；F2 对——`train_causal_share.py:1061-1064` 在 `not args.smoke and args.max_events == 0` 时直接 `full_tr_events = tr_events`，没有排除 `--readonly-env`（`tr_events` 那时是按只读表折叠过的），而 summary 写 `scope=full`；F3 对——`extending.md:295` #29 那行仍写「只许落在 `_forward_packed` 函数体内」，`tests/test_share_gen_eval.py:237-242` 的类 docstring 仍写「只能在 `_forward_packed` 内」而第 249 行起的 `ALLOWED_ATTN_CTX_CALLERS` 已是三个函数，spec 16.9 (c) 同。四条顺手修的改动到我写这段时（HEAD a50039c）还没有进 log，扫描按 eee0a5e 发，这四条不在扫描的代码里（sweep_lr 排序只影响 report，`run_mem_probe` 的 finally 只影响异常路径）。「全量单测 479 OK」是终审自己跑的，我没复跑。9 个 run 的登记等回执到了再记。

**2026-08-29 00:48，扫描第一阶段 9 个 run 的登记（plan-8-28 报，原话照录）。** 「扫描第一阶段 9 个 run 的登记：发射员用 `run.py launch` 逐个发，RUNMETA 记 commit 0f5adb8（你的台账提交，代码与 eee0a5e 相同），track `kvshare-lr-sweep`，产物 `pipeline/runs/sweep/<run_id>`。发射时刻（2026-08-29）：l4 lr1e-4 00:26:32 tokyo108 g0、l4 lr5e-4 00:27:16 g1、l4 lr2e-3 00:27:49 g2、b17 lr1e-5 00:28:22 g3、b17 lr5e-5 00:28:54 g4、b17 lr2e-4 00:29:27 g5、b06 lr1e-5 00:29:59 tokyo107 g0、b06 lr5e-5 00:30:33 g1、b06 lr2e-4 00:31:06 g2。00:48 九个存活、零 Traceback、对齐全 PASS（b17 9.06e-6、l4 1.54e-5、b06 5.48e-6 与冒烟逐位相同）；`cost` 探针 worst_gb：b17 三个 102.29（max_tokens_block）、l4 三个 32.964（max_losspos_block）、b06 三个 22.005（max_losspos_block）；第一条 step 峰值 b17 93.955、l4 30.912、b06 19.581；ips b17 156 到 166、l4 48.7 到 49.2、b06 81.2 到 81.5；steps 516。发射到第一条 step：b17 约 8 分钟、l4 9、b06 12（对齐检查加 train/val 全集分词，静默无输出，发射员一度误判卡死后核实是分词阶段）。l17 三条等 b17 收完发第二阶段。」

8-28-assistant 核对（00:51，读九个目录的 `train_log.jsonl` / `ALIGN_CHECK.json` / `RUNMETA.json`，jobs.json，runs.jsonl，九份日志）：jobs.json active 九条，host / gpu 与消息一致（l4 tokyo108 g0-2、b17 tokyo108 g3-5、b06 tokyo107 g0-2）；runs.jsonl 九条 start 00:27 到 00:31，track `kvshare-lr-sweep`；九份 RUNMETA 都是 0f5adb8、dirty false；九份日志 Traceback 0 处；九个 `start` 事件 steps 516、tok_budget 16384、`mem_probe_pick` cost、`gen_eval_at` last，l4 三条带 lora，学习率各对。对齐：b17 三条 9.060e-6、l4 三条 1.538e-5 与冒烟逐位相同；**b06 三条是 5.007e-6，不是消息说的 5.48e-6**——冒烟的 5.4836e-6 是在 H100 上（tokyo108），这三条在 tokyo107 的 Ada 上，9.8 说过「会动对齐差的只有换卡型」，三条 Ada 之间逐位相同，PASS。探针 `worst_gb`（scope run，`--max-events 0` 时 `tr_events` 是全集）：b17 102.29（`max_tokens_block`，9.8 的估计 102.2），l4 32.964（`max_losspos_block`，9.9 的估计 33.7），b06 22.005（`max_losspos_block`，9.9 的估计 22.1）。step 峰值到 00:51：b17 三条第一条 93.955、第 120 到 130 次更新时最大 99.965（H200 150.8 GB）；l4 三条最大 32.271；b06 三条最大 19.831。ips：b17 165.94 → 154.95 / 156.05 → 153.56 / 162.99 → 153.93，l4 48.77 → 47.0 / 48.69 → 47.86 / 49.24 → 48.58，b06 81.21 → 80.85 / 81.39 → 80.46 / 81.53 → 80.62。b17 lr1e-5 与 lr5e-5 已过第一个评估点：val_ce 0.2161 与 0.2815（frac 1）。

**2026-08-29 00:5x，终审修复合并（plan-8-28 报，原话照录）。** 「终审修复已合并：sonnet 在独立 worktree 里一次修完 F1 到 F3 与四条观察（分支 worktree-agent-aa6a91c7dd84dd29a，base eee0a5e，head 3f5dd79，合并 6b27eaa，无冲突，10 个文件）：F1 两个评测脚本改用 `raw_rows` 取全文并加用例（修前失败、修后通过）；F2 复用条件加 `args.readonly_env is None` 并加用例；F3 三处说法改「三处调用点」；O1 排序 None 替身；O2 `val_exact` 取最后一个有值的点、列名 `val_exact(@ep.frac)`、JSON 加 `val_exact_frac`；O3 `--piece <host>:<gpus>`；O4 探针清理进 finally。修复者自报 41 个用例通过、selfcheck 77。范围限定复审（sonnet）在跑，结果到了转你；扫描的 9 个 run 用的是修复前的代码（0f5adb8），差别不在训练路径。」

8-28-assistant 核对：6b27eaa 在 log 里，10 个文件 +317/−25（extending 2、spec 2、eval_causal_call 5、eval_causal_param 5、sweep_lr 41、train_causal_share 14、test_eval_overlong +102、test_mem_probe_pick +117、test_share_gen_eval 13、test_sweep_lr 41）；F1：`eval_causal_call.py:639-640` 与 `eval_causal_param.py:478-479` 的 `event_full_texts` 现在传的是 `[r for r in raw_rows if r["event"] in key_set]`；F2：`train_causal_share.py:1073` 的复用条件是 `args.readonly_env is None and (not args.smoke) …`；F3：`extending.md:295` 的 #29、spec 16.9 (c)（第 337 行）、`tests/test_share_gen_eval.py:237-243` 的 docstring 三处都改成「只许落在前向 `_forward_packed` 与反向 `backward_logical_minibatch` / `_fwd_bwd_block` 三处，生成路径永远不许」；O2 / O3：`sweep_lr.py:137` 的占位是 `--piece <host>:<gpus>`，:181-224 有 `val_exact_frac`；`python3 run.py selfcheck` 77。「41 个用例通过」是修复者自报，我没复跑。9 个扫描 run 的 RUNMETA 是 0f5adb8，不含这次合并，训练路径（`train_causal_share.py` 这次改的是探针 finally 与 readonly 条件）不受影响。

**2026-08-29 01:0x，决定 37 的固定件造好（plan-8-28 报，原话照录）。** 「决定 37 的固定件已造：`pipeline/runs/smoke/ks828b06_gptoss_ctool_final_smoke_ml2048/best/` 七个文件软链到原 run 的 best/，只有 `meta.json` 是新写的（`max_len` 2048，加一行 `fixture_note` 说明来历），原 run 未动。ccall 那侧冒烟产物选不出 θ、且 ccall 三个分支已在 np821 的 4096 产物上走到，所以固定件只跑 ctool 三个模式（run_id `ks828b06_ovl2048_<mode>_ctool`，tokyo107 一张空 Ada，`--limit 200`），发射员在发；产物副本落 `/home/y-guo/.claude/jobs/b39c625e/tmp/ovl_ml2048/<mode>/`。」

### 决定 37 调整

固定件只做 ctool 一侧（`ks828b06_gptoss_ctool_final_smoke_ml2048`），只跑 ctool 三个模式（run_id `ks828b06_ovl2048_<mode>_ctool`，`--limit 200`，tokyo107 一张 Ada）；cgen smoke2 那侧的副本不造。 / 理由：ctool 冒烟产物选不出 θ（两档都 null），ccall 跑不动；ccall 的三个分支已在决定 38 的 np821 4096 产物上走到。 / 依据：决定 38 的六个 run 事实。

8-28-assistant 核对：固定件 `best/` 里七个文件（chat_template.jinja、config.json、head.pt、label_map.json、model.safetensors、tokenizer_config.json、tokenizer.json）都是到原 run `best/` 的软链，只有 `meta.json` 是普通文件，`max_len` 2048，`fixture_note` 原文「决定 37 固定件: ks828b06_gptoss_ctool_final_smoke 的副本, 权重与分词器为软链, 只把 max_len 从 8192 改成 2048, 用来在真实数据上验证 --overlong skip/drop-event 的非零剔除; 不进矩阵, 不是训练产物」；原 run 的 `best/meta.json` 仍是 8192、没有 `fixture_note`。到我核的时候 jobs.json active 里还没有 `ovl2048` 条目，`logs/` 与对照目录 `ovl_ml2048/` 也还没有，三个 run 的结果到了再记。

**2026-08-29 01:2x，固定件三个 run 收官（plan-8-28 报，原话照录）。** 「固定件三个 run（`ks828b06_ovl2048_{left,skip,dropevent}_ctool`，tokyo107 gpu3，RUNMETA 记 9351e16，各自 finish 销号，台账文件脏着等收官一起提交）：零 Traceback。REPLAY_REPORT 四个计数三档全 0、`n_events_test` 7、θ 两档 null——因为实现者定的口径是报告只记 test 堆，而 test 堆 `--limit 200` 的 200 行在 2048 下也没有窗口外边界。非零剔除在 val 堆的 `logits_val.meta.json`：left `n_oow` 41；skip `n_oow` 41、`n_skipped_bounds` 41、`excluded_idx` 下标 81 到 121；drop-event `n_dropped_events` 1、`n_dropped_bounds` 64、`excluded_idx` 81 到 144。三份 REPLAY_REPORT 逐键比：left 对 skip 只差 `overlong_mode` 与 `temperature`（1.201 对 1.2014）；对 drop-event 另有 `theta_sweep_calB` 每档 n 5 变 4、`speculation_economics` 17 处、`temperature` 1.2456。两份 meta 的 `rows` 都 200、权重指纹一致。请记；另记一条遗留（不改代码）：REPLAY_REPORT 应带 val 堆的计数（`*_val` 后缀），现在只在 meta 里。副本在 `/home/y-guo/.claude/jobs/b39c625e/tmp/ovl_ml2048/`。」

8-28-assistant 核对（读 `ovl_ml2048/<mode>/` 三份 REPLAY_REPORT.json 与六份 `.meta.json`，三份日志，RUNMETA，runs.jsonl）：数逐个对得上。三份 REPLAY_REPORT 四个计数全 0、`n_events_test` 7、`chosen_theta` 两档 null，`temperature` 1.201 / 1.2014 / 1.2456；`logits_val.meta.json`：left `n_oow` 41、`excluded_idx` 空；skip `n_oow` 41、`n_skipped_bounds` 41、`excluded_idx` 41 个下标、区间 81 到 121；drop-event `n_dropped_events` 1、`n_dropped_bounds` 64、`excluded_idx` 64 个、区间 81 到 144（skip 剔的 41 个窗口外边界落在 drop-event 剔的那一个事件的 64 个边界之内）；三份 `logits_test.meta.json` 计数全 0、`excluded_idx` 空；六份 meta `rows` 都 200、权重指纹都是 model.safetensors 732cb44fe64ef8ee；我按键展平比较：left 对 skip 只差 `overlong_mode` 与 `temperature` 两键，left 对 drop-event 差 `overlong_mode`、`temperature`、`theta_sweep_calB`（每档 n 5 变 4）、`speculation_economics.calB_sweep` 四处（后者内部的 17 处差别我没逐个数，照消息记）；三份 RUNMETA 都是 9351e16、dirty false；三份日志 Traceback 0；runs.jsonl 三条 finish 01:17 / 01:19 / 01:20。遗留一条（不改代码）：REPLAY_REPORT 只记 test 堆的四个计数，val 堆的剔除只在 `logits_val.meta.json` 里，应加 `*_val` 后缀的计数进报告。这组的意义只到接线层面：test 堆在 2048 下 `--limit 200` 仍是零剔除，非零剔除只出现在 val 堆的 meta 里。

**2026-08-29 01:2x，终审修复的范围限定复审（plan-8-28 报，原话照录）。** 「范围复审（sonnet，自己跑了 41 个用例两遍 OK、selfcheck 77）：F1、F3、O1、O2、O3、O4 通过（依据行号：`eval_causal_call.py:562/569/640`、`eval_causal_param.py:390/397/479`、`train_causal_share.py:1073` 与 `537-549`、`sweep_lr.py:137/174-187/223-224/260-261/274`）；F2 代码通过、但新用例 `TestMemProbePickTokensReadonlyEnvReloadsFull` 整份扫了现役 `val.jsonl`（13 秒）违反 16.9 前言，已派 sonnet 在独立 worktree 改成手造两个事件（标签从 readonly 表取），回来合并。旧说法全仓只剩 decisions.md:381 的历史引文，按只增不改留着。」

8-28-assistant 注：`tests/test_mem_probe_pick.py:242` 是 `class TestMemProbePickTokensReadonlyEnvReloadsFull`，第 304 行 `for split in ("train.jsonl", "val.jsonl")` 两个现役数据文件都读（不只 val）；decisions.md 第 381 行是这份台账里照录的历史原话，台账只增不改，留着。改后的用例合并了再记。

**2026-08-29 01:30，b17 三条跑完、l17 交发射（plan-8-28 报，原话照录）。** 「b17 三个 run 跑完（`done` 事件）：lr1e-5 best_val_ce 0.1636（frac 4，wall 2789.4 s）、lr5e-5 0.175（frac 4，2820.8 s）、lr2e-4 0.2269（frac 4，2830.4 s），三个最好点都在 epoch 末。l17 三条（`ks828l17_gptoss_cgen_lr1e-4 / 5e-4 / 2e-3`）已交发射员在 tokyo108 H200 gpu3-5 发第二阶段，回执到了转你。b17 的 record finish 我按 `sweep-lr report` 的数补。」

8-28-assistant 核对（01:31，读三个目录的 `train_log.jsonl`）：三条 `done` 与消息一致——lr1e-5 `best_val_ce` 0.1636、`best_frac` 4、`wall_s` 2789.38；lr5e-5 0.175 / 4 / 2820.75；lr2e-4 0.2269 / 4 / 2830.43；`total_rows` 都是 186,415。四个评估点的 val_ce：lr1e-5 0.2161 / 0.188 / 0.1737 / 0.1636，lr5e-5 0.2815 / 0.2198 / 0.1972 / 0.175，lr2e-4 0.4505 / 0.3229 / 0.2935 / 0.2269；epoch 末生成评估（200 行）`val_exact_call` 0.65 / 0.595 / 0.54，`gen_s` 270.13 / 272.66 / 292.47 秒；`train_s` 1204.76 / 1232.21 / 1236.54，末尾累计 ips 152.79 / 149.39 / 148.86，step 日志各 51 条（log_every 10）；三条的整程 step 峰值都是 102.336 GB、都在第 500 次更新（同种子同块序列），比 `cost` 探针的 worst 102.29 高 0.05，决定 30 按 102.2 × 1.1 = 112.5 排的 H200；`grad_norm` 最大 51.21 / 23.53 / 26.71。runs.jsonl 三条 finish 01:30；jobs.json active 剩 l4 三条与 b06 三条。l17 三条到 01:31 还没有登记（active、start、日志都没有）。

**2026-08-29 01:3x，复审修复合并、验证任务收口（plan-8-28 报，原话照录）。** 「复审修复合并：`tests/test_mem_probe_pick.py` 的 ReadonlyEnv 用例改成从 `readonly_map.load_table("appworld")` 取第一个只读与第一个非只读标签手造两个事件（分支 worktree-agent-a125518770d120467，head 4c74000，合并 b3875a7），单跑 2.9 秒，模块 6 个用例 OK。记一条遗留：同文件另外两个类（`TestRunMemProbeThreeModes`、`TestMemProbeRngRestorationViaMain`，wave5 工单 10 的实现者写的）仍读现役 val 集（`VAL_PATH`），当时收账没抓到，违反 16.9 前言，本轮不改。验证任务到此收口：全量单测 479 OK、selfcheck 77、四配置冒烟、`--overlong` 端到端（ovl 六个加固定件三个）、终审三条修复经复审。」

8-28-assistant 核对：b3875a7 合并 4c74000，只改 `tests/test_mem_probe_pick.py`（+25/−39）；第 248 行起的 `TestMemProbePickTokensReadonlyEnvReloadsFull` 第 275 行调 `readonly_map.load_table("appworld")`；第 94 行的 `TestRunMemProbeThreeModes`（第 104 行按 `VAL_PATH` 跳过）与第 185 行的 `TestMemProbeRngRestorationViaMain`（第 200 行按 `TRAIN_PATH` / `VAL_PATH` 跳过）仍读现役数据，遗留照记。「全量单测 479 OK」「模块 6 个用例 OK、单跑 2.9 秒」按报记，我没复跑。

**2026-08-29 01:47，b06 三条跑完（plan-8-28 报，原话照录）。** 「b06 三个 run 跑完并 record finish 销号：lr1e-5 best_val_ce 0.173（frac 4，val_exact_call 0.63，wall 3654.8 s）、lr5e-5 0.1857（0.615，3678.9 s）、lr2e-4 0.247（0.49，3617.9 s）；三个整程 step 峰值 22.427 GB 对 cost 探针 22.005（真峰估计 22.1），对齐 5.007e-6（Ada）。剩 l4 三个（约第 300/516）与 l17 三个（刚发）。」

8-28-assistant 核对（01:48，读九个目录的日志与三本台账）：b06 三条 `done` 与消息一致——lr1e-5 0.173 / frac 4 / wall 3654.8，lr5e-5 0.1857 / 4 / 3678.88，lr2e-4 0.247 / 4 / 3617.85；四个评估点 val_ce：lr1e-5 0.2358 / 0.208 / 0.1844 / 0.173，lr5e-5 0.2988 / 0.2316 / 0.2122 / 0.1857，lr2e-4 0.4921 / 0.3555 / 0.2999 / 0.247；epoch 末 200 行生成 `val_exact_call` 0.63 / 0.615 / 0.49，`gen_s` 59.89 / 66.91 / 55.17 秒；`train_s` 2332.25 / 2351.0 / 2346.38，末尾累计 ips 78.93 / 78.3 / 78.45；整程 step 峰值三条都是 22.427 GB（cost 探针 22.005，9.9 估计 22.1，Ada 51 GB）；对齐 5.007e-6；runs.jsonl 三条 finish 01:47。l17 三条已登记：runs.jsonl start 01:32 / 01:32 / 01:33，jobs.json active 在 tokyo108 g3 / g4 / g5，RUNMETA 都是 ac36171（含 6b27eaa 的终审修复，不含 b3875a7 那条只改测试的合并）、dirty false，对齐 9.060e-6（与 b17、l17 冒烟逐位相同，H200），cost 探针 worst 81.654（9.8 的估计 81.9），到 01:48 各跑到第 30 到 40 次更新、step 峰值 79.784，ips 139.6 到 142.2。l4 三条到 01:48 跑到第 300 到 330 次更新，step 峰值最大 33.088（cost 探针 32.964，9.9 估计 33.7），前两个评估点 val_ce：lr1e-4 0.2198 / 0.1979，lr5e-4 0.2137 / 0.1944，lr2e-3 2.6527 / 0.9333。

**2026-08-29 01:5x，l17 三条的登记回执（plan-8-28 转，原话照录）。** 「l17 三条登记：发射员 `run.py launch`，RUNMETA 记 ac36171（你的台账提交，代码同 6b27eaa 之后的主干），发射时刻 lr1e-4 01:31:54 tokyo108 g3、lr5e-4 01:32:27 g4、lr2e-3 01:32:59 g5；第一次 01:31:31 被脏树门禁拦下（脏文件是你正在改的 decisions.md），你 commit 后原样重发，没用 `--allow-dirty`。三条 `cost` 探针 worst_gb 81.654（max_tokens_block，预期 81.9），第一条 step 峰值 79.784，ips 145.7 / 147.9 / 140.8，对齐 PASS，卡上占用 87.36 GB 对 143.77。」

8-28-assistant 注：与我 01:48 从文件核的一致（start 01:32 / 01:32 / 01:33 是 runs.jsonl 的分钟戳，回执给的是秒级发射时刻；`worst_kind` 是 `max_tokens_block`）。「卡上占用 87.36 GB 对 143.77」是发射员从卡上读的，我没有另读。脏树门禁那一次：01:31:31 我的 decisions.md 正在编辑、还没提交（记 b17 收官那一段，提交 ac36171 在 01:31 之后），发射员被 `run.py launch` 的脏树门禁拦下、等我提交后重发；教训是我这边编辑到提交的窗口要短，编辑一落盘就提交，不在发射窗口里留脏文件。

**2026-08-29 02:37，l17 三条跑完（plan-8-28 报，原话照录）。** 「l17 三个 run 跑完并 record finish 销号：lr1e-4 best_val_ce 0.1826（frac 4，val_exact_call 0.585，wall 3077.9 s）、lr5e-4 0.1647（0.63，2883.8 s）、lr2e-3 0.2138（0.54，2991.0 s）；整程 step 峰值 81.655 对 cost 探针 81.654，对齐 9.06e-6。剩 l4 三个。」

8-28-assistant 核对（02:38，读六个目录的日志与台账）：l17 三条 `done` 与消息一致——lr1e-4 0.1826 / frac 4 / wall 3077.89，lr5e-4 0.1647 / 4 / 2883.83，lr2e-3 0.2138 / 4 / 2991.0；四个评估点 val_ce：lr1e-4 0.2384 / 0.2145 / 0.1928 / 0.1826，lr5e-4 0.2325 / 0.1963 / 0.1814 / 0.1647，lr2e-3 0.4343 / 0.4036 / 0.277 / 0.2138；epoch 末 200 行生成 `val_exact_call` 0.585 / 0.63 / 0.54，`gen_s` 283.45 / 306.4 / 257.06 秒；`train_s` 1360.23 / 1319.02 / 1360.31，末尾累计 ips 135.33 / 139.56 / 135.32；整程 step 峰值三条都是 81.655 GB（cost 探针 81.654，9.8 估计 81.9，H200）；runs.jsonl 三条 finish 02:37；jobs.json active 只剩 l4 三条。l4 三条到 02:38 都到第 510 次更新（516 次为满）：lr1e-4 四个评估点 0.2198 / 0.1979 / 0.1769 / 0.1671、epoch 末 `val_exact_call` 0.63（`gen_s` 342.12 秒）、`done` 未写；lr5e-4 前三点 0.2137 / 0.1944 / 0.175；lr2e-3 前三点 2.6527 / 0.9333 / 0.7557；三条整程 step 峰值 33.088；`train_s` 3991.94 / 3884.76 / 3955.91。

**2026-08-29 02:4x，12 个 run 全部 done（plan-8-28 报，原话照录）。** 「12 个 run 全部 done，l4 三条已 record finish 销号：lr1e-4 best_val_ce 0.1671（val_exact_call 0.63，wall 7081.2 s）、lr5e-4 0.1547（0.655，7284.8 s）、lr2e-3 0.651（0.335，7211.8 s）；整程 step 峰值 33.088 对 cost 探针 32.964，对齐 1.5378e-5（容差 3e-5）。全表 `pipeline/runs/sweep/SWEEP_REPORT.{json,md}`（12 行，每组 `*`：b06 lr1e-5 0.173、b17 lr1e-5 0.1636、l17 lr5e-4 0.1647、l4 lr5e-4 0.1547）。台账三件已提交。接下来我写 TIMELINE 2026-08-29 条、更新记忆、把第二轮汇报插进 artifact 重发；这几样提交后请你核 TIMELINE 与汇报（同上一轮：数字对文件、措辞），然后台账封口（最终 HEAD、决定 26 到 39、待 gyb 比较的清单）。」

8-28-assistant 核对（02:45，读 12 个目录的日志与 `SWEEP_REPORT.json/.md`，台账提交 cbbff5b）：l4 三条 `done` 与消息一致——lr1e-4 0.1671 / frac 4 / wall 7081.17，lr5e-4 0.1547 / 4 / 7284.76，lr2e-3 0.651 / 4 / 7211.81；四个评估点 val_ce：lr1e-4 0.2198 / 0.1979 / 0.1769 / 0.1671，lr5e-4 0.2137 / 0.1944 / 0.175 / 0.1547，lr2e-3 2.6527 / 0.9333 / 0.7557 / 0.651；epoch 末生成 `val_exact_call` 0.63 / 0.655 / 0.335；整程 step 峰值三条都是 33.088（cost 探针 32.964，9.9 估计 33.7，H100）。`SWEEP_REPORT.json` 12 行，`best_val_ce / best_frac / wall_s / peak_mem_gb / worst_gb` 逐行与各自 `train_log.jsonl` 相同（我逐行比过，零处不符），`status` 全 done；`.md` 里带 `*` 的四行是 b06 lr1e-5、b17 lr1e-5、l17 lr5e-4、l4 lr5e-4，与消息一致。12 条的 `best_frac` 都是 4（都在 epoch 末）。JSON 里 `val_exact` 12 行与各自日志 epoch 末的 `val_exact_call` 相同（b06 0.63 / 0.615 / 0.49，b17 0.65 / 0.595 / 0.54，l17 0.585 / 0.63 / 0.54，l4 0.63 / 0.655 / 0.335，按 lr 升序），`val_exact_frac` 都是 "0.4"（ep 0、frac 4），`evals` 列表里四个点的 val_ce 与日志逐个相同。12 个 run 的最终事实汇总（只摆数）：每组最低 val_ce 的学习率——b06 1e-5（0.173）、b17 1e-5（0.1636）、l17 5e-4（0.1647）、l4 5e-4（0.1547）；b06 与 b17 最低点在网格下端 1e-5（决定 29 的判读规则：落在边上要往那边再加一档 3e-6），l17 与 l4 在中间；l4 lr2e-3 的 val_ce 四个点 2.6527 / 0.9333 / 0.7557 / 0.651、exact 0.335。

**2026-08-29 03:0x，TIMELINE 条与汇报第二轮提交，决定 40（plan-8-28 报，原话照录）。** 「TIMELINE 2026-08-29 条与汇报第二轮部分已提交（bf66af7），artifact 同 URL 重发。决定 40：两个全参配置的最低点在网格下端，b06 与 b17 各补一档 lr2e-6（run_id `ks828b06_gptoss_cgen_lr2e-6` 上 tokyo107 Ada、`ks828b17_gptoss_cgen_lr2e-6` 上 tokyo108 H200），发射员在发，跑完补进表与汇报；LoRA 不补。请你按上一轮的办法核 TIMELINE 那一条与汇报第二轮部分（数字对文件、措辞、有没有没依据的判断），发现列给我；两个补扫 run 收官、汇报补完之后台账封口。」

### 决定 40

两个全参配置（b06、b17）的最低 val_ce 都在网格下端 1e-5，各补一档 lr2e-6 一个 run（`ks828b06_gptoss_cgen_lr2e-6` 上 tokyo107 Ada、`ks828b17_gptoss_cgen_lr2e-6` 上 tokyo108 H200），跑完补进 SWEEP_REPORT 与汇报；LoRA 两个配置的最低点在中间档，不补。 / 理由：决定 29 写的判读规则「最好点落在边上就往那边再加一档」。 / 依据：SWEEP_REPORT 12 行（b06 0.173 / 0.1857 / 0.247，b17 0.1636 / 0.175 / 0.2269）；design-attention 9.7。8-28-assistant 注：到 03:0x `logs/new1_ks828b06_gptoss_cgen_lr2e-6_t107g0.log` 已建，jobs.json active 与 runs.jsonl 里两条都还没有登记，回执到了补记。

**2026-08-29 03:0x，TIMELINE 2026-08-29 条与汇报第二轮部分的审查（8-28-assistant，对 bf66af7）。** 数字逐个对 12 个 run 的日志、SWEEP_REPORT、冒烟目录与对照件；「代码终点 b3875a7」核过（`git diff --stat b3875a7 HEAD -- pipeline tests run.py ops/*.py` 为空）。发现发给 plan-8-28 的：解读段「cost 挑出的块就是整程峰值那一块（b17 差 0.05 GB，其余差 1.5 到 1.9%）」——实际 b17 +0.046 GB（0.05%）、l17 +0.001 GB、l4 +0.124 GB（0.37%）、b06 +0.422 GB（1.9%），「其余 1.5 到 1.9%」不对，一句话结果里的「−0.05 到 −1.9%」下端是 −0.001%，「就是整程峰值那一块」是没核过块身份的推断；l17 两边「各高 0.017 到 0.018」实际是 +0.018（1e-4）与 +0.049（2e-3）；「lr5e-4 与 lr1e-4 从第 30 次起 loss 在 0.15 到 0.36」实际下限 0.123 / 0.131；「l17 lr2e-3 … 末条 1.01」实际 0.88；「九个全参与 LoRA 低两档的 run 里 grad_norm 超过各自中位 5 倍的只有第 10 次那一条」——那是十个 run，六个全参各有一条（第 10 次，b17 lr2e-4 第 30 次），四个 LoRA 低两档一条都没有；决定 26 到 39「共 14 条」与台账指向「26 到 39」而同一份汇报已列决定 40（TIMELINE 同）；决定 27 的理由段用了裁决之后才有的数且 l4 写「约 1.5 小时」（实测 118 到 121 分钟）、引草稿 2.3「一个 epoch 只要几小时」草稿里没有这句（台账记的决定 27 没有理由）；决定 28 的理由「cost 探针实测最准」也是事后数；「四个新测试文件 30 个用例」合并的是五个新测试文件；「b06 在 H100 上六个 run 全是 5.4836e-6」到现在是九个（第一轮六个加 smoke2 / 3 / 4）；TIMELINE 没写决定 40 的动作（只写了规则）；措辞两处（「loss 冲到」「末点也没有平掉」改成数字）；「479 OK」要写明是 cprobe-env 的全量（系统 python 那套恒剩 1 error）。核过没问题的：12 行表、训练之外的墙钟（22 / 26 / 26 到 29 / 52 到 57 分钟）、l4 lr2e-3 的 loss 序列（第 30 / 70 / 130 / 250 / 末 0.4978 / 4.2674 / 3.4479 / 1.0461 / 0.5433，grad_norm 最大 77.70 在第 110 次）、l17 lr2e-3 grad_norm 最大 32.30 在第 220 次、生成秒数四组、冒烟七行、`--overlong` 两张对照表、对齐差按卡型、决定 30 / 35 / 36 / 39 的数与提交号。
