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
