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
