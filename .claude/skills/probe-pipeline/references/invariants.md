# invariants — 一个字都不能改的口径

本文件列出探针流水线里**换数据集、换 agent 模型、换环境都不许动**的常量与规则。
**改动这里任何一条 = 新老数字不可比**，必须新起数据集版本号 / run_id 批次号，并在 `TIMELINE.md` 补一条说明改了什么、为什么改、作废了哪些旧数字。

命令行怎么敲见 `references/stage-commands.md`；门禁与应急见 `references/gates.md`。

## 1. 为什么有这份清单

口径漂移是**静默**的：改了 batch size、换了切分、挪了门槛，代码照样跑通，报告照样出数字，只是这批数字和历史那批不再是同一把尺子量出来的，而没有任何一处会报错。

本工程已经踩过三次：C3 那条线的档位编号有两套、代码那套和正式那套**取值正好颠倒**（`DATA.md` §6.1）；BFCL 的频率先验基线随数据版本变，同一个环境有 0.038 / 0.049 / 0.042 三个值，拿错一个就把探针的"超过基线多少"读反（`DATA.md` §4、§7.2）；耗时那一列必须两条臂跑在同型号卡上，否则整列作废（`DATA.md` §6.2、§7.4）。

所以规则是**抄写优先**：标了【照抄】的函数、常量、正则从源文件原样复制，一个字符不改；不确定该抄还是该写，默认抄；规格没覆盖的决策点停下来问用户，不要猜（`plans/2026-07-31-pipeline-engineering.md` §0.2、§0.4）。

## 2. 数据侧口径

| 口径 | 固定值 | 写死在哪 | 改了会怎样 |
|---|---|---|---|
| 种子 SEED | `20260729` | `pipeline/annotate/rules.py`；出处 `build_dataset.py`（ENG §2.2） | 重跑不再逐样本一致，"可重跑"这条证据链断掉；DATA.md §7.5 明确写了这是铁律 |
| 最短思考长度 MIN_THINK | `40` 字符 | `rules.py`（ENG §2.2） | 切点集合变→样本数变→`w=1/m` 全变→与历史任何一版都不可比 |
| 每事件最大切点 MAX_BOUNDS | `64` | `rules.py`（ENG §2.2） | 同上；且 gptoss 的切点中位数已到 51、贴着 64（DATA.md §3.1），一动它 gptoss 的样本量会跳变 |
| 历史轮数 HIST_ROUNDS | `3` | `rules.py`（ENG §2.2） | 输入 text 变→探针看到的上下文变→触发准确率不可比 |
| 结果截断 RESULT_CAP | `400` | `rules.py`（ENG §2.2） | 同上 |
| 句边界正则 SENT_RE | `(?<=[.!?])\s+\|\n` | `rules.py`（ENG §2.2） | 切点位置变，`depth` 和 earliness 全变 |
| 文本拼版式 | `Task: …\n[HISTORY]\n…\n[THINKING]\n<前缀>`（`assemble()` 产出） | `rules.py`（ENG §3.2） | 训练分布和注入时线上分布对不上，注入段直接失效 |
| 样本权重 | `w = 1/m`，m = 该事件切点数，round 6 位 | `rules.py` / `build.py`（PLAN §1.2、ENG §3.2） | 每事件总贡献不再恒为 1，长思考的事件会主导损失，跨模型比较作废（gptoss 切点密，受影响最大） |
| 参数值归一化 | `strip()` 后 `strip("\"'")`，空值跳过 | 照抄 `envs/bert/param_label.py`（ENG §3.3） | 宽松/严格两档的差距被人为拉开或抹平（本轮结论"差距只出现在抽取路线"就靠这一条口径成立，TIMELINE 2026-07-31 c1 条③） |
| 参数名规则 | kwarg 取名字，位置参数取 `pos0/pos1/…` | 照抄 `split_args_named()`（ENG §3.3） | 键匹配判定变，参数正确率整体漂移 |
| `label_call` 格式 | `f"{label}({', '.join(f'{k}={v}')})"`，无参数时 `f"{label}()"` | `build.py`（ENG §3.3） | cgen 的训练目标串变形，`val_exact_call` 与 `full_call_ok` 两个数字与历史不可比 |
| 参数区间定位 | `str.rfind`——取值在该样本自己 text 里**最靠末尾**一次出现的区间，找不到 `found=false` | `param_label.py`（ENG §3.4） | mext 的 span 标注变，抽取头训练目标变 |
| 分区判法 | 认官方题单、任务实例级归属；unit 不在任何题单里**报错退出**，不许静默丢 | `build.py`【改动②】（ENG §4.2.3、PLAN §1.6） | 静默丢题会让三个模型的题单不再一致，"同题对比"这条前提垮掉（DATA.md §3.1） |
| 堆名 | 只有 `train / val / test` 三堆；旧代码读 `calA`/`calB` 的地方一律读 `val` | ENG §2.5 | 温度和门槛必须在同一个 val 上定；分开定就变成另一套评测法 |
| 标注策略 | 全自动、**失败轨迹照用**——学"模型会做什么"不是"应该做什么" | PLAN §1.3 | 筛掉失败轨迹等于换了学习目标，探针不再刻画真实模型行为 |
| 轨迹目录命名 | `appworld_<model_key>`，尾巴必须对上 `MODEL_OF` 的键 | `build.py` 的 glob pattern（ENG §4.2.1） | 名字不标准 → 整个目录被事件抽取**静默跳过**，数据集少一大块且不报错（实测坑，见 gates.md §3.6） |
| 旧数据 | `envs/` 下一切旧文件、`envs/bert_data/v3*`、`envs/bert_runs/*` 只读 | ENG §0.5、PLAY §0.7 | 旧数字的复现基准被破坏，两条验收线从此无法重跑 |

## 3. 训练侧口径

| 口径 | 固定值 | 写死在哪 | 改了会怎样 |
|---|---|---|---|
| mbert 超参 | lr 2e-5 / bs 8 / accum 4 / epochs 3 / maxlen 4096 / 左截断 / fp32 权重 + bf16 autocast / warmup 5% / clip 1.0 | `train_mbert_tool.py`、`train_mbert_extract.py`（ENG §5.1、§5.2） | 有效批大小或学习率一变，同一格跨模型的成绩不再是同一训练配方下的比较 |
| causal 超参 | lr 1e-5 / bs 4 事件 / accum 8 / epochs 3 / warmup 5% / clip 1.0 / fp32 + bf16 autocast | `train_causal_tool.py`、`train_causal_callgen.py`（ENG §5.3、§5.4） | 同上；且 cgen 的超参是**故意对齐 ctool** 的，动一个就破坏"同一骨架两个头"的对照 |
| 左截断 | `truncation_side="left"`，`padding_side="right"`，pad=eos | 照抄 `train_causal_probe.py` 的 `build()`（ENG §5.4） | 右截会吃掉紧邻调用的思考尾巴，正是探针最该看的那一段 |
| cgen 目标构造 | 先 tokenize 目标不截断（>160 token 的实例丢弃并计数），再按 `max_length = 4096 - L_t` 左截输入，`labels` 前缀段填 `-100` | `train_causal_callgen.py`（ENG §5.4） | 顺序反了就会被左截吃掉目标，损失算在错的位置上 |
| cgen 损失 | 逐实例目标段 mean CE，批损失 `Σ(w_i·ce_i)/Σw_i` | `train_causal_callgen.py`（ENG §5.4） | 丢掉 w 加权 = 丢掉事件等权，与其余三格口径分家 |
| cgen 选 best | 唯一依据是 val 全量 masked-CE（越低越好）；`val_exact_call`（200 条 greedy）只进日志不选 best | ENG §5.4 | 用 exact_call 选 best 会让 val 被用两次（选点 + 报数），破坏 val/test 分工 |
| smoke 规模 | 500 训练 / 200 评估 / 1 epoch，四格统一 | ENG §5.1、§5.4 | 只影响冒烟，但改了就失去"和历史 smoke 同口径"的对照价值 |
| 解释器 | mbert 格 `mbert-env`（transformers 4.57.6 钉死）、causal 格 `cprobe-env`（≥5.14），谁也不许升级谁 | PLAY §0.13、ENG §2.1 | 混架构在旧版上会**静默算错**（分块增量喂），这是对齐检查存在的理由 |
| 对齐检查 | 因果格开训前必过，FAIL 即 `exit 2` | `train_causal_tool.py`（ENG §5.3） | 跳过它 = 允许一个数值上错误的骨架进入训练，产出的一切数字都不作数 |
| `--out` | 必填，无默认值 | ENG §5.1.3 | 默认值会让两次训练悄悄覆盖同一目录 |
| 只读折叠（ro1 起，`--readonly-env` 开启时） | 真值表 `pipeline/annotate/readonly/{appworld,bfcl}.json`；mtool/ctool 词表 = 只读工具原顺序 + 末位哨兵 `<NON_READONLY>`；mext/cgen 只训真值只读的事件；**不传 flag 与旧行为字节级等价**（G12 用 c1 报告 cmp 验证过） | `pipeline/train/readonly_map.py`（唯一实现，四格共用） | 折叠规则或哨兵位置一变，ro1 起所有带此旗的数字与旧批不可比；登录/认证类判非只读是 2026-08-01 用户拍板，改判要过 TIMELINE |
| 开火真值 ready | ready = 真值工具只读 ∧ 该边界上事件全部参数 found=true（无参事件空真）；found 按 `(event, sent_idx)` 联表 `params/<split>.jsonl` | `train_mbert_extract.py` / `train_causal_callgen.py` 的 `--fire-head` 路径与两个 call 脚本的 `load_ready` | ready 定义一变，θ_fire 与开火精度全线重算，且与 ro1 批不可比 |

## 4. 评测侧口径

| 口径 | 固定值 | 写死在哪 | 改了会怎样 |
|---|---|---|---|
| 评测三步 | 温度在 val 拟 → θ 在 val 扫 → **test 冻结考一次** | `eval_tool.py`（PLAN §1.2、ENG §6.1.1） | 回头在 test 上调 θ = 用测试集选点，所有覆盖率/准确率全部虚高，论文级失效 |
| θ 网格 | 0.5 → 0.975 步长 0.025，共 20 档 | `THETAS`（ENG §2.2） | 网格一变，"两档皆无解"这类判定的含义就变了（本轮 `c1_q35_mtool` 正是判到无解） |
| 风险目标 | `RISK_TARGETS = [0.10, 0.05]`，矩阵汇总表报 0.05 档 | ENG §2.2、§6.4 | 放宽风险目标 = 换了契约，等于给不合格的格发通行证（见 gates.md §3.4 的裁决） |
| bootstrap | `BOOT = 1000`，随机数取用次序也算口径 | ENG §2.2 | 置信区间不再能与旧报告逐位对上；本轮 ACCEPT_EVAL 专门确认过这一点（`ACCEPT_EVAL.md` §2） |
| 触发点来源 | mext 用 mtool 的 REPLAY_REPORT（温度 + `chosen_theta`），cgen 用 ctool 的 | ENG §6.2、§6.3.1 | 借用别格的触发点 = 参数格评的不再是自己那条路线（gates.md §3.4 裁决拒绝过这个做法） |
| 参数三档 | 宽松（归一化后相等）/ 严格（原串相等）/ 整调用；键不匹配即该参数错；无参事件单独成列 | ENG §6.3.5、PLAN §1.4 | 判分松紧一变，跨路线比较作废 |
| 报告字段名 | 一律沿用旧名：`theta_sweep_calB`、`stoptime_calibration_test`、`depth_bucket_acc_test`、`prior_baseline_event_acc`、`speculation_economics`、`temperature` | ENG §3.6、§2.5、`ACCEPT_EVAL.md` §4.7 | 下游脚本按名读；`probe_server.py` 靠 `temperature` 这个键装载探针，改名即断链 |
| 先验基线 | 每个数据集报 test 堆的频率先验，随版本和模型变；`--readonly-env` 下**在折叠后词表上取最高频**（de1c781） | `ANNOTATE_REPORT.md` / `router_stats.md`（ENG §4.2.7、DATA.md §3.1）；折叠版在 `eval_tool.py` 的 `readonly_stats` | 拿错基线会把 gptoss（先验 0.404）的探针成绩高估——它的门槛比 q35 的 0.174 高一倍多；折叠前取会把"最高频是非只读工具"的环境（bfcl）先验错印成 0.0，探针被制造假优势 |
| readonly 触发条件（`--readonly-env` 开启时） | 触发 = conf ≥ θ **且 argmax ≠ 弃权哨兵**；参数指标只算真值为只读的触发事件 | 三个 eval 的 `replay`/`replay_fire`（ro1 批起） | 少了哨兵闸门，弃权类形同虚设，非只读事件会被投机执行——这正是本方案要挡的事故 |
| self-fire 选点 | θ_fire 在 val 扫、test 冻结一次（与 θ 同纪律）；约束是 **`fire_acc ≥ 1-risk`（开火精度）**，不是扫描表里按全事件归一的 `wrong_fire_rate` | 两个 call 脚本的 `pick_theta`（与 eval_tool 选 θ 同机制） | 换成 wrong_fire_rate 约束等于换契约，ro1 的"14 格仅 2 格有工作点"判定作废 |

## 5. 命名与记账口径

| 口径 | 固定值 | 写死在哪 | 改了会怎样 |
|---|---|---|---|
| run_id 四处一致 | 原始数据目录名 = tmux session 前缀 = 台账 name = commit message | `CLAUDE.md`、PLAY §0.10 | 出了问题追不回是哪次跑、用的哪版代码 |
| 训练 run_id 模板 | `<批次>_<model_short>_<cell>`，cell ∈ `{mtool, mext, ctool, cgen}` | ENG §2.4 | 汇总脚本按目录名认格，命名一乱矩阵表就拼不出来 |
| 模型称呼 | qwen3.5 与 qwen3.6 **永远是两个模型**，任何场合不写成"qwen 侧" | PLAY §0.6 | 合并会掩盖两代模型的差异，这是用户明确的红线 |
| 记账双写 | 发射时 `record.py start` + `gpu_jobs.py register`；收尾 `record.py finish` + `gpu_jobs.py finish` | `CLAUDE.md`、PLAY §0.10 | 漏登记就是占卡不销号；数字进不了 `runs.jsonl` 就不进 `RESULTS.md` |
| 只增不改 | `ops/runs.jsonl` append-only；`RESULTS.md` 是渲染产物不许手改 | `CLAUDE.md`、ENG §0.5 | 手改渲染产物下次渲染即被覆盖，且账实不符 |
| 发射前 commit | 工作树必须干净 | PLAY §0.11 | 记录里存的 HEAD 追不回真实代码，实验等于没留痕 |
| 新产物新目录 | 旧数据与旧数字一个字节不动，新东西一律新目录 + 新版本号 | PLAY §0.7 | 覆盖旧产物 = 永久失去复现基准 |

## 6. 允许调的旋钮

判据只有一条：**这个旋钮影响的是显存和墙钟，还是影响梯度与数字？** 前者随便调，后者进第 2–5 节。

| 旋钮 | 可调范围 | 为什么不影响数字 |
|---|---|---|
| `--grad-ckpt`（梯度检查点） | 随时开关 | 数学中性：只是把中间激活丢掉、反向时重算，梯度与参数更新逐位相同，换的是显存与速度。本轮 `c1_gptoss_cgen` 的 OOM 就是用它解的，而不是降 bs（gates.md §3.2）；ro1 批开火头双前向在 q36/gptoss 长序列档上引发的 8 个 OOM（ctool 4 + mext 4）同样只用它解（gates.md §3.8），mext 的这个旗就是那次补的（fbe4d15） |
| 排卡与机位（哪台机、哪张卡、A6000/H200） | 自由 | 不进梯度。**唯一约束**：要比耗时就必须两条臂同型号卡，否则耗时那一列作废（`DATA.md` §7.4）。`c1_gptoss_cgen` 迁到 H200 重跑，准确率口径不受影响，只有墙钟从 ETA 26.7h 变成 5h13m（TIMELINE 2026-07-31 c1 条·取舍其二） |
| 采集并发数、分片数、每实例流数 | 自由 | 每题独立求解、`--resume` 幂等，分片只决定谁跑哪几题，轨迹内容与题目归属都不变。本轮故意给题多的模型开高一档并发来拉平墙钟（PLAY §3.4） |
| 服务端口、session 名后缀、实例数 | 自由 | 服务只是把同一份权重摆出来；一个实例挂了把分片改指同模型另一实例，结果相同（PLAY §3.7） |
| `--align-tol` | **可放宽，但必须记 TIMELINE 并写明理由与实测差值** | 它是门禁阈值不是训练超参，不进梯度。但放宽 = 降低"实现正确性"的判定标准，所以要留证据链。本轮按 T8 先例放宽到 `3e-4`，依据是三个 ctool 的 hidden maxdiff 8.39e-5 ~ 1.68e-4、相对差 2.3e-6 ~ 3.3e-6，判为 fp32 数值噪声（TIMELINE 2026-07-31 c1 条·取舍其一） |
| eval 的 `--report-dir` / `--device` / `--cached-logits` | 自由 | 只改"报告写哪、算在哪、要不要复用已存 logits"，后处理数学不变。本轮 ACCEPT_EVAL 在 `--device cpu` + `--cached-logits` 下产出与旧报告**逐字节相同**，即证（`ACCEPT_EVAL.md` §1、§4.1、§4.2）。注意 `--cached-logits` 只跳模型不跳 tokenizer——`probe_cost_test` 要用它数 token（`ACCEPT_EVAL.md` §4.4） |
| run_id 的批次前缀（`c1_` → `c2_` …） | 自由，且换数据就**应该**换 | 纯命名。但必须四处一起换（第 5 节） |
| 日志/报告的标题文字 | 自由，**除非在做逐字节验收** | 验收要求 md 也逐字节相同，所以验收路径下标题得沿用旧文案（`ACCEPT_EVAL.md` §4.6） |

**明确不算旋钮的两个诱惑**：① 用降 batch size 解 OOM——有效批大小变了，跨模型不再是同一配方（gates.md §3.2）；② 用放宽风险目标或借用别格触发点来抢救"无解"的格——两者都直接破口径（gates.md §3.4）。

## 7. 换环境 / 换数据集时**必须**同步改的

这些是该变的，列清楚免得漏改（对照 ENG §2.3 的 config schema）：

1. **`env` 名**：config 的 `"env"` 字段；它决定 `build.py` 走哪条事件抽取分支、调用解析用 `AW_CALL` 还是 `BFCL_CALL`（ENG §4.1、§6.3.4）。新环境要新写一条抽取分支和一条调用正则。
2. **题单文件**：`official_split_files` 的三条路径。**没有官方多分区的环境要自己切一次三堆**（bfcl 就是这种，PLAN §1.6）；自切就必须固定种子并把切法写进 `DATA.md`。
3. **轨迹来源**：`traj_runs` 列表——列全该数据集要吃的所有采集目录；本轮三个模型共用同一组目录，靠 `model_full` 过滤分家（ENG §4.2 改动①、DATA.md §3.1）。
4. **模型字段**：`model_short` / `model_full`，且 `model_short` 要能对上 `MODEL_OF` 的键与采集 outdir 的尾巴（ENG §2.2、§4.2.1）。
5. **`data_out` 版本号**：新数据集一律新版本目录（本轮是 `aw_official_v1`）。同时在 `DATA.md` §3 补一条版本条目、§4 补规模与先验基线（PLAY §5.1）。
6. **run_id 批次前缀**：新一轮训练换新前缀，四处一起换（第 5 节）。
7. **`tool_vocab.json` 与先验基线**：随数据自动重算，但**报数时要引用这一版的基线**，不能沿用上一版的数（`DATA.md` §7.2）。
8. **两条验收线的比对基准**：换环境后 ACCEPT_V3DIFF 要指向该环境自己的旧数据；没有旧数据的全新环境，这道门退化为"新旧代码同输入自比"，要在验收文件里写明这一点（本轮 bfcl + appworld 两侧都有旧基准，`ACCEPT_V3DIFF.md`）。
9. **`TIMELINE.md`**：换场地、换主线口径都要补条（本轮补的是"appworld 官方分区成为标准场地"，TIMELINE 2026-07-31）。
