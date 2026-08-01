# gates — 门禁与应急处置

跑到某一步卡住了，先在 §1 找对应的门禁编号，再看 §3 有没有同款案例；判断"该停还是该修"看 §4。
命令行怎么敲见 `references/stage-commands.md`；哪些常量不许动见 `references/invariants.md`。

## 1. 门禁总表

| 编号 | 检查点 | 在哪一步 | 判据 | 不过时的标准动作 |
|---|---|---|---|---|
| G1 | 工作树干净 | 任何 GPU 发射前 | `git status --short` 为空 | 先 commit 再发射；不干净就发射，记录里的 HEAD 追不回真实代码（PLAY §0.11、§3.1） |
| G2 | 实探空卡 | 发射前 | `gpu_jobs.py free`，只用 `OWNERS=FREE` 的卡，永不信缓存 | 等卡或换机器（`CLAUDE.md`、PLAY §3.1） |
| G3 | 服务健康 | 采集放量前 | 日志出现 `Application startup complete`，且 `curl /v1/models` 返回模型名；**全部实例健康才放量** | 读服务日志定位；单实例救不活就把它的分片改指同模型另一实例的端口，不停摆（PLAY §3.2、§3.7） |
| G4 | 采集 smoke | 每模型各 1 题 | outdir 出现 `<env>_<tid>.jsonl`；`type:"gen"` 带非空 `reasoning`、`type:"env"` 带代码动作、末行 `type:"final"` | 先查服务日志再修；反复修不好按 §4 判断是否死局（PLAY §3.3） |
| G5 | outdir 命名 | 采集发射时 | 目录名必须是 `appworld_<model_key>` 这类标准名，尾巴对上 `MODEL_OF` 的键 | 改名重跑；名字不标准会被下游事件抽取**静默跳过**，见 §3.6（PLAY §3.3、ENG §4.2.1、§7） |
| G6 | 采集完整性 | Phase A 收尾 | 各 outdir 的 jsonl 文件数对上题数，且每个文件末行是 `type:"final"` | 用 `--resume` 重发缺题分片补齐；补齐后才算 A 段结束（PLAY §3.8.1-2） |
| G7 | 显存归零 | Phase A 收尾 | 服务 session 全杀，`nvidia-smi` 显存归零 | 批量任务结束不许占卡过夜，必须杀干净（PLAY §0.12、§3.8.3） |
| G8 | **ACCEPT_V3DIFF** | annotate 段末，不过不许进 train | 新旧样本数相等、主键单边为 0、九字段（text/label/w/depth/n_sents/traj/unit/model/step）不一致计数**全 0**，每个有旧基准的环境各跑一遍 | 修 annotate 代码重跑；反复过不了属"推翻前提"，按 §4 停下问用户（ENG §4.5、§9） |
| G9 | 题单行数 | annotate 自检 | 三个题单文件行数对上官方分区（本轮 90 / 57 / 168） | 注意题单文件**无末尾换行**，`wc -l` 会各少 1，别直接当真（ENG §4.6） |
| G10 | 三模型同题 | annotate 自检 | 三个模型**共用同一份题单**，且 train 堆 unit 集合相同（val/test 同理）。⚠️**允许有缺口**，见 G19：某个 unit 的轨迹一个可用事件都没出时该 unit 不进数据集，这不是 bug | 集合不同又解释不出缺口的原因 → 回查 `model_full` 过滤与题单归属逻辑（ENG §4.6、DATA.md §3.1）；缺口有原因 → 按 G19 逐条列进报告 |
| G11 | label_call 抽查 | annotate 自检 | 抽 20 条：工具名 == label，参数与 action 原文对得上 | 回查 `split_args_named` 与归一化（ENG §4.6） |
| G12 | **ACCEPT_EVAL** | eval 段末，不过不许进 Phase C 发射 | 重跑旧数据，`temperature / chosen_theta / test_frozen` 三块完全一致；新报告写临时目录，旧文件 md5 跑前跑后不变 | 修 eval 代码重跑；本轮就因"cached 时误跳 tokenizer 导致报告少两个字段"改回并重跑（ENG §6.5、ACCEPT_EVAL §4.4） |
| G13 | 对齐检查 | 因果格开训前 | `ALIGN_CHECK` PASS，FAIL 即 `exit 2`；先用 `--align-only` 单独跑一遍 | 看 §3.1：先判是数值噪声还是实现错误，放宽阈值必须记 TIMELINE（ENG §5.3、§9） |
| G14 | 四格 smoke | 批量训练发射前 | 各跑一次 50 步微训：loss 在降、ckpt 能存能读；ctool 含 ALIGN_CHECK PASS | 修脚本重 smoke，不许直接放量（PLAY §5.2、ENG §9） |
| G15 | bundle 校验 | 批量训练发射前 | `check_bundle.py` 对 smoke 产物跑通：能加载、出 softmax、打印预测/置信度/是否过 θ/真值 | 产物格式不合 `probe_server.py` 就改存盘格式（ENG §8、§9） |
| G16 | 双登记 | 发射后立刻 | `gpu_jobs.py register` 与 `record.py start` 同时做完 | 立刻补登记；台账只能通过 CLI 读写（`CLAUDE.md`、PLAY §3.5、§3.6） |
| G17 | 收尾销号 | 每个 run 结束 | `record.py finish --metric …` + `gpu_jobs.py finish` + 释放显存 + commit | 不销号就是占卡过夜；数字不进 `runs.jsonl` 就不进 `RESULTS.md`（PLAY §3.8、§5.5） |
| G18 | 总验收清单 | 批量训练发射前逐项打勾 | ENG §9 的七条：G8 / G12 / 产物清单齐 / 题单一致 / 四格 smoke / G15 / 全部新代码已 commit | 缺哪条补哪条，一条不缺才发射（ENG §9） |
| G19 | 题单缺口逐条列出 | annotate 段末 | 三模型共用一份题单，但**实现出的 unit 集合允许有缺口**；缺口必须逐条列进 `CALLSTR_CHECK.md` 并说明原因（轨迹一个可用事件都没出：思考 <40 字符 或 调用正则解析不出）。bfcl 实测缺口：q35 0 题、q36 4 题（`multi_turn_base_{63,84,176,187}`，其中 176 在 test 堆 → q36 test 只有 19 实例）、gptoss 1 题（`multi_turn_base_30`，val 堆） | 缺口列不出来 = G10 的字面版本失守，"三模型同题对比"这句话有水分，报告里必须改口成"近似同题"（`check_callstr.py` 偏差 2） |
| G20 | 真值调用串可回读 | annotate 段末，进 train 前 | 把每个事件的 `label_call` 喂给 `eval_causal_call.parse_call`，切回来的 `(key, norm(value))` 必须与该事件的 `args_named` 全等。回读率 = `params_all_ok` / `full_call_ok` 的**天花板**，必须写进报告。实测（事件级回读率，q35/q36/gptoss）：bfcl 0.9735 / 0.9763 / 0.9755，appworld 0.9932 / 0.9953 / 0.9985 | 回读率异常低（<0.95）先查 `make_call` 与 `split_named_raw` 的切法是不是漂了；正常低（参数值含逗号）**只记录不修口径**——给单个环境补逗号闸门会让它与已上账的 appworld 不是一把尺子（EXT §5 #21） |
| G21 | traj_runs 不许写父目录 | annotate 段末 | `traj_runs[]` 的每一项都是 run 目录**本身**（其下直接有 `<env>_<模型>` 子目录，且再往下没有嵌套的 run 目录）；且 `(event, sent_idx)` 全局唯一、一个 unit 只对一条 traj | 写成父目录 = 把 smoke 批次静默并进来，退 0 无告警、只是样本数悄悄涨（EXT §5 #20）。`check_callstr.py` 门禁 C + 门禁 B 硬拦 |
| G22 | 报告文案不撒谎 | annotate 段末 | 题单目录的 `SPLIT_REPORT.json` 写着 `official_split_exists: false` 时，`ANNOTATE_REPORT.md` 里不许出现"官方题单" | 在 config 里写 `split_desc` 说明真实切法（`build.py` 从该字段取文案，默认值保持旧说法）。`check_callstr.py` 门禁 E 硬拦（EXT §5 #18） |

**G19–G22 的实现都在一个脚本里**：`pipeline/annotate/check_callstr.py --config <同一份 config>`，纯 CPU、跑在 `build.py` + `param_label.py` 之后，产物 `<DATA_ROOT>/CALLSTR_CHECK.md`。它内部编号 A–E（A 一模型一数据集 / B 样本键唯一 / C traj_runs 层级 / D 题单归属**全量**核对（比 G11 的抽 20 条更严）/ E 文案一致）全部 `sys.exit(1)` 硬拦，另有四类"只报不拦"的已知偏差（回读损失 / 题单缺口 / test 有 train 无的工具 / test 堆厚度告警）。

## 2. 两条复现验收线

这两道门（G8、G12）是整条流水线可信度的地基。核心论点一句话：**新代码喂旧数据必须复现旧数字**——先证明管子不漏水，再往里灌新东西（PLAN §1.2）。它们值得单独拎出来，是因为其余门禁都只证明"这次跑通了"，只有这两道证明"这次跑出来的数和历史那批是同一把尺子量的"。而且它们**零 GPU、几十秒量级**，成本极低却是唯一能拦住静默口径漂移的机制。

### 2.1 ACCEPT_V3DIFF（G8，annotate 段）

- **验什么**：事件抽取 + 切样本这个核心与上一版数据集逐条一致。切分法不同（官方分区 vs 自切），**所以不比堆归属**，只比样本本身（ENG §4.5）。
- **怎么跑**：用新 `rules.py` + `build.py` 的抽取与造样本代码跑旧数据当年的输入目录，**不过滤模型、不切分**；与旧数据四堆合并后按主键 `(event, sent_idx)` 建索引对比（ENG §4.5.1-2）。
- **判据**：两边样本数相等；主键单边为 0；同主键条数相等；九字段逐字段不一致计数全 0。新增字段（`label_call`、`args_named`）不比。
- **本轮结果**：bfcl 与 appworld 两侧 PASS，全 0。bfcl 逐条比对 36343 条、appworld 111767 条，主键单边 / 重复 / 条数不等全为 0（`pipeline/annotate/ACCEPT_V3DIFF.md`）。
- **一处口径补丁值得记住**：旧数据建库之后才采完的采集目录（本轮是 `bfcl_gptoss`，32163 条样本），旧数据里根本没有，整批剔除后再比；**剔除清单不写死目录名，取自旧数据自己的采集目录集合**——这样换数据集时判据自动成立（`ACCEPT_V3DIFF.md` 开头）。

### 2.2 ACCEPT_EVAL（G12，eval 段）

- **验什么**：评测后处理（首次越阈回放、温度拟合、θ 扫描、bootstrap、stop-time 校准、深度十桶、先验基线、经济换算）与旧脚本一致。
- **怎么跑**：`--legacy-splits --cached-logits`，复用旧 `logits_*.pt` 只做 CPU 后处理，报告写 `--report-dir` 指的临时目录（ENG §6.5、ACCEPT_EVAL §1）。
- **判据**：`temperature / chosen_theta / test_frozen` 三块完全一致，且**绝不覆盖旧文件**。
- **本轮结果**：PASS，且强于要求——整份 `REPLAY_REPORT.json` 与 `.md` 都与旧产物**逐字节相同**；mbert 头 12 秒跑完；自加的因果头那一份同样逐字节相同；旧文件 md5 跑前跑后未变（`ACCEPT_EVAL.md` §1、§2）。
- **最容易被打乱的一处**：bootstrap 置信区间能逐位对上，说明 `random.Random(SEED)` 的**取用次序**也与旧脚本一致——改动评测代码时最先破的就是这个，专门确认它（`ACCEPT_EVAL.md` §2）。

## 3. 本轮真实发生过的意外与处置

### 3.1 因果格对齐检查 FAIL（G13）

- **现象**：`ctool` 开训前的对齐检查报 FAIL，hidden maxdiff 达 `1.678e-4`，超过 `ALIGN_TOL = 1e-4`。
- **判断依据**：看的是**差值的量级构成**而不是单个数字过没过线——三个 `ctool` 的 hidden maxdiff 落在 8.39e-5 ~ 1.68e-4、logits maxdiff 1.69e-5 ~ 2.00e-5、相对差 2.3e-6 ~ 3.3e-6。相对差在 1e-6 量级是 fp32 累加噪声的典型幅度，若是实现错误（如分块增量喂喂错位置）差值会大得多且不成比例。台账里 T8 有同款先例。
- **处置**：按 T8 先例把门槛放宽到 `3e-4`，三格全部 PASS 放行，并把这条决策与实测差值写进 `TIMELINE.md`（2026-07-31 c1 条·取舍其一）。
- **事后评价**：正确但**必须留证据**。`--align-tol` 属于可调旋钮（invariants §6）——它是门禁阈值不进梯度，所以放宽不改数字；但放宽等于降低正确性判定标准，不记 TIMELINE 就变成"悄悄把红灯改成绿灯"。判据要写成"差值构成符合数值噪声特征"，不能写成"差得不多"。

### 3.2 四个 run 在 A6000 48G 上 OOM

- **现象**：批量训练发射后，四个 run 在 48G 的 A6000 上显存不足。
- **判断依据**：两条路可选——降 batch size，或开梯度检查点。降 bs 会改变有效批大小，同一格的三个模型就不再跑在同一训练配方上，**跨模型可比性直接破掉**（invariants §3 的 mbert/causal 超参行）；`--grad-ckpt` 只是把中间激活丢掉、反向时重算，梯度逐位相同，换的是显存与速度。
- **处置**：加 `--grad-ckpt` 重发，超参一个不动。
- **事后评价**：这是"旋钮判据"的标准案例——**先问这个开关影响的是显存还是梯度**。凡是能用数学中性的开关解决的资源问题，都不许动超参。

### 3.3 `gptoss_cgen` 速率异常

- **现象**：加了 `--grad-ckpt` 之后该 run 跑到 22.15 s/step，ETA 26.7 小时，远超同批其他 run 的 1–2.5 小时量级。
- **判断依据**：`--grad-ckpt` 的代价是时间换显存，在这一格上代价被放大到不可接受；而 gptoss 的思考文本长、切点密（边界数中位数 51，DATA.md §3.1），样本最重。既然瓶颈是显存，换一张显存更大的卡就能把开关关掉。
- **处置**：杀掉、把残局归档到 `pipeline/runs/_aborted_c1_gptoss_cgen_t106g3`（不删、留痕），迁到 tokyo108 的 H200 上**不带 grad-ckpt** 重发，实际墙钟 5h13m（TIMELINE 2026-07-31 c1 条·取舍其二）。
- **事后评价**：ETA 异常要**当场比同批其他 run**，不要等。残局用 `_aborted_` 前缀归档而不是删除，这样矩阵汇总不会误认它是有效格，同时保留了现场。换卡属自由旋钮，唯一后果是这一格的墙钟不能和 A6000 上的其他格横比（DATA.md §7.4）。

### 3.4 `q35_mtool` 两档 θ 皆 null，连带 mext 无法评测

- **现象**：θ 扫描在两个风险档（0.10 / 0.05）上都找不到解——val 上最高 trig_acc 只有 0.871，够不到 0.90 的契约线，`chosen_theta` 两档全 null。上游没有触发点，下游 `c1_q35_mext` 就没得评。
- **判断依据**：能"抢救"的两条路都破口径——放宽风险目标等于换契约（invariants §4 的 RISK_TARGETS 行）；借用别格（如 ctool）的触发点，那评的就不再是 mbert 这条路线了（invariants §4 的触发点来源行）。
- **处置**：**如实记 N/A**。`c1_q35_mext` 在矩阵表里标 N/A 并注明原因"上游 `c1_q35_mtool` 两档 θ 皆 null，没有触发点可评"，写进 TIMELINE（2026-07-31 c1 条·触发）。
- **事后评价**：无解本身就是结论——它正是"因果头全面胜出"这条判断的一半证据（同源的 `c1_q35_ctool` 把两档无解变成双档有解）。缺格要在矩阵表里显式标记（`summarize_matrix.py` 用 `PENDING` 标缺报告的格，ENG §6.4），不能留空让人以为忘了跑。

### 3.5 `gptoss_mtool` 风险契约在 test 上未兑现

- **现象**：0.10 档在 val 上选中 θ=0.975，到 test 上 trig_acc 只有 0.8642，低于 0.90 的契约线。
- **判断依据**：**test 冻结一次是铁律**（invariants §4 评测三步行、PLAN §1.2）。回头在 test 上换 θ 就是拿测试集选点，所有数字作废。
- **处置**：数字原样报告，不调 θ、不重扫。
- **事后评价**：这不是事故，这正是计划里写明"接受了的设定"要量的东西——温度和门槛在 dev（易题）上校准、在 test_normal（难题）上用，**难度迁移**风险如实兑现，论文如实写（PLAN §3）。它成了本轮三条结论之一（TIMELINE 2026-07-31 c1 条②）。

### 3.6 采集 outdir 命名不标准 → 下游静默跳过（G5）

- **现象**：事件抽取按目录名尾巴认模型（glob `appworld_*/appworld_*.jsonl` + `MODEL_OF` 键匹配），`appworld_q35_tn` 这类名字对不上键，**整个目录被跳过且不报错**——数据集少一大块，没有任何一处告警。
- **判断依据**：这是实测过的坑，两份规格都专门标注（PLAY §3.3、ENG §4.2.1、§7）。
- **处置**：outdir 一律用 `appworld_<model_key>` 标准名；同一模型的不同 split 轨迹落**同一个** outdir（文件名按 task_id 天然不冲突）。
- **事后评价**：这类"静默跳过"是最危险的一类失败——它不触发任何门禁，只能靠 G6 的条数核对和 G10 的题单一致性抓住。所以 G6 要数文件数，不能只看"跑完了没报错"。

### 3.7 `record.py` 的三个语法坑（G16 / G17）

- **现象与成因**：
  1. **`--metric` 的值含 `.` 或 `e` 会被强转数值**——`ops/record.py:106` 是 `v = float(v) if ("." in v or "e" in v.lower()) else int(v)`，转不动才 `except` 退回字符串。所以像 `1e-4`、`0.05` 会变成 float，而含 `e` 的英文单词侥幸没转成也是走的异常路径。
  2. **`null` 会以字符串 `"null"` 落账**（同上，`float("null")` 抛异常→退回字符串），账面上看起来像有值。
  3. **同一个 run_id 不许二次 `start`**；`finish` 找不到 run_id 会直接退出并提示先 `start`（`ops/record.py:234`）。
- **处置**：记 N/A 的格（如 §3.4 的 `c1_q35_mext`）用 `--conclusion` 写清原因，不要靠 `--metric x=null` 表达；发射前确认这个 run_id 没 start 过。
- **事后评价**：记账 CLI 的语法坑不会让实验失败，但会让 `RESULTS.md` 里出现类型不一致的列，事后统计时要多一道清洗。约定：**能进 metric 的只有真数字，解释性内容一律进 conclusion**。

### 3.8 开火头双前向让长思考模型档 OOM（ro1 批，两轮共 8 个）

- **现象**：ro1 批带 `--fire-head` 的训练，q36/gptoss × 两环境在 48G 卡上先后 8 个 OOM（ctool 4 个、mext 4 个），**q35 全程零事故**。mext 尤其意外——0.1B 的模型、c1 批同卡同数据跑得好好的。
- **成因**：开火头走独立样本流，每步**多一次全长前向**，激活显存近乎翻倍；代价随思考长度上升，所以只打长思考模型（q36/gptoss 的边界数中位数是 q35 的数倍到数十倍）。
- **处置**：按 §3.2 同款判据加 `--grad-ckpt` 原卡重发（mext 当时还没有这个旗，补旗即一次 commit `fbe4d15`，训练逻辑零改动）。8 个全部重发成功，超参一个未动。
- **事后评价**：§3.2 的判据第二次验证成立，同时补一条经验：**给训练加"额外前向"类的新头时，显存预算按最长思考的模型档估**，q35 上冒烟通过不代表 gptoss 档放得下；发射前在排卡表里给长思考档预留 `--grad-ckpt` 是零成本的保险。

## 4. 死局判据

**唯一允许停下来问用户的情形：推翻前提的事。** 原文列举的三类是——目标 split 的任务在环境里根本跑不了、权重路径失效、双验收线反复过不了（PLAY §0 前言、§6）。

**停之前必须把已完成的部分收尾干净**（PLAY §0 前言）：核对并落盘已完成的产物、杀掉还在占卡的服务、`nvidia-smi` 确认归零、`gpu_jobs.py finish` 销号、`record.py finish` 记上已有的数字与中断原因、commit。

**其余一律自动处置，不找用户**（PLAY §6）：分片挂 → 修 + 重发；实例挂 → 分片改指同模型另一端口；OOM → 砍并发或换更大的卡重发（**不是降 bs**，见 §3.2）；单题超时卡死 → 跳过该题并记入报告缺口。

**前提**：这条自动化授权来自用户说过的那一句"发射"——说了之后整条链做到底，链内动作（包括杀 vLLM 释放显存、批量发射训练）免再批；**链外的新主意仍要问**（PLAY §0 前言、§0.1）。

**两个已知的仪器坑，别误判成故障**（PLAY §6）：① appworld 包内置 freezegun 冻结了进程内时钟，**不要用 `time.time()` 测单题耗时**，要测就用 jsonl 文件 mtime 差；② `evaluate()` 在 test 分区可能报错——采集器已容错（评测失败不弃轨迹），属正常。

## 5. 已知缺口

**有意不做（本轮划定的边界）**：

- `test_challenge` 区 417 题不碰（PLAN §1.6）。
- 注入段只定产物存盘格式、不跑端到端实验；等矩阵结果出来、知道哪格值得注入之后另行立项（PLAN §1.9）。
- 第 3 波整体不在本轮：bfcl 三堆单切（数据已齐、零采集）→ 环境扩展（ALFWorld 已探明可低成本接入，候选第三站）→ 注入端到端实验（PLAN §2）。
- bfcl 降为第二站、串行做；本轮只跑 appworld（PLAN §1.5）。

**欠账（该做没做，下一轮补）**：

- **`aw_official_v1` 自己的"重建两次逐字节比"没做**（上一版 v3_1 当年做过）。目前"重跑必得同一份数据"是靠固定种子 + 采集脚本幂等 + ACCEPT_V3DIFF 三条推出来的，**不是直接实测过的**（DATA.md §3.1）。→ `bfcl_mtb_v1` 这批**已补**：三个模型各重建一次、`train/val/test.jsonl` + `tool_vocab.json` + `router_stats.md` + `qa_sample.txt` 全部 `cmp` 零差异，q35 的 `params/*.jsonl` + `CHECK_50.md` 同样零差异；题单 `gen_bfcl_splits.py` 跑两遍也逐字节一致。appworld 那批仍是欠账，但顺手实测过：改 `build.py` 报告文案后重建 `aw_official_v1/q35`，三个 jsonl 与 `tool_vocab.json` 与线上产物 `cmp` 零差异。
- ACCEPT_EVAL 的验收产物（`pipeline/eval/accept_bfcl_v3{,_causal}/`）入不入 git 未定——它们不在 `.gitignore` 的 `pipeline/data`、`pipeline/runs` 覆盖范围内，留作验收凭证，归属待定（ACCEPT_EVAL §4.8）。
- ~~BFCL 参数重抽多出 217 个事件原因未查~~ → **已排除是新线的问题**。`param_label.collect_events` 与 `build.bfcl_events` 在新流水线里是两份**逐字相同**的实现，`bfcl_mtb_v1` 三个模型的 `PARAM_LABEL_REPORT.md` 里"数据集有而重抽缺"全是 **0**；"重抽有而数据集无"分别是 2116 / 2269 / 2265，正好等于 `3325 − 该模型事件数`（重抽不按模型过滤，扫的是全部三个 bfcl 目录），完全可预测。老那 217 的差是旧代码两份实现漂移造成的，与新线无关。
- DATA.md §8 的既有缺口本轮未动：BFCL 聊天模板未查、表面相似度过滤 τ 未接、参数三档的档位表还是 v2 事件算的、全历史臂 24576 token 预算的来历没记账。
- 采集矩阵不齐：三模型 × 三环境九格都有数据但量差很远（DATA.md §8.1）。
