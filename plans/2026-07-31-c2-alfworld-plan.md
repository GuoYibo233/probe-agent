# c2 批次计划 —— ALFWorld 接入探针流水线

> 走 `.claude/skills/probe-pipeline/SKILL.md`,情形 B(加新环境),
> 改动清单 `references/extending.md §2`。收尾必须走 Phase E 回写 skill。
> 立于 2026-07-31。本文件是**计划**,结论归 `RESULTS.md`,方向归 `TIMELINE.md`。

## 0. Phase 0 五变量

| 变量 | 取值 |
|---|---|
| `<BATCH>` | `c2` |
| `<ENV>` | `alfworld` |
| `<MODELS>` | `q36` `gptoss`(被探测的 agent 模型,与 c1 的三模型不合并) |
| `<CELLS>` | `mtool` `mext` `ctool` `cgen`(四格全上) |
| `<DATA_ROOT>` | `pipeline/data/alf_official_v1/` |

run_id 形如 `c2_<model>_<cell>`,共 2×4 = 8 格。

## 1. 这批要回答什么问题

**主问题:动作空间的形状变了,探针的四格矩阵会怎么变?**

c1 跑的 appworld 是「**工具多、参数杂**」——143 类工具(q35),先验基线 0.174。
ALFWorld 恰好是它的**反面**:「**工具少、参数多**」——工具词表只有 13 个官方动作模板
(`go/take/move/open/close/heat/cool/clean/use/slice/examine/inventory/look`),
但每个参数是房间里的具体实体(`mug 1`/`countertop 3`),随场景变化。

由此派生三个可证伪的预期,收官时逐条对账:

1. **工具格(mtool/ctool)在 ALFWorld 上应该显著更容易**,因为只有 13 类。
   若连 13 类都达不到精度门槛,说明瓶颈不在类别数而在别处(思考文本本身不够早地暴露意图)。
2. **参数格(mext/cgen)才是这批的裁决格**。appworld 的参数多是 API 字面量,
   ALFWorld 的参数是场景实体,探针要从思考里定位"哪个物体"。
   这一格若开门,说明探针学到的是**语义指代**而不只是**工具名的表面线索**。
3. **tales 的负结论会不会重演?** `RESULTS.md:33` 判 tales 投机门不开,
   根因写的是「开放动作空间」。但 ALFWorld 的动作空间是**封闭的 13 个模板**,
   与 cookingworld 不同 —— 若 ALFWorld 开门,说明当初那条根因判定要收窄为
   「开放**参数**空间」而不是「开放动作空间」;若同样不开,则该判定得到加强。
   **无论哪种结果都要补一条 TIMELINE**,因为它动了 `WORKPLAN.md` 的判断。

## 2. 数据设定(细节归 `DATA.md`,这里只记决策与依据)

### 2.1 三堆来源:官方分区直接映射

| 我们的堆 | ALFWorld 官方分区 | 题数 | 任务配置数 |
|---|---|---|---|
| train | `train`(分层抽 200) | 200 | 200 |
| val | `valid_seen` 全量 | 140 | 137 |
| test | `valid_unseen` 全量 | 134 | 47 |

**已实测的三条边界事实**(`fig1_pilot/alfworld_data/json_2.1.1/`):

- trial 级(= 我们的 unit 粒度)**三堆两两交集为 0**,`build.py` 那条静默后写覆盖的雷踩不到。
- `train ∩ valid_seen` 在**任务配置层面**有 134 个重叠(valid_seen 共 137 个配置)
  —— valid_seen 就是「同房间同任务、换一条 trial」。这是 ALFWorld 的官方 seen 设计,
  **不是我们引入的污染**,但意味着 val 与 train 同分布,val 上选出的 θ 偏乐观。
- `train ∩ valid_unseen` = 0,**连场景号都零交集**(unseen 的 4 个房间 train 里一个都没有)。
  所以 test 是真正的 OOD,比 appworld 的 test 更严。

⚠️ **test 的 134 题只摊在 47 个任务配置上**(41 个配置各 3 条 trial),
有效多样性比题数低。引用 test 数字时必须配这句说明,别让读者按 134 个独立样本读。

### 2.2 题单必须入库(ALFWorld 没有官方清单文件)

官方**不提供** id 清单,枚举方式是遍历目录,而顺序是 `os.walk` 的文件系统序、跨机不保证一致。
所以题单由 `pipeline/collect/gen_alfworld_splits.py` 生成一次并入库
(`envs/alfworld/splits/{train,val,test}.txt`),之后一律以入库的 txt 为准。

- 种子 `20260729`(全线同值)。**已验幂等**:两次重跑三份 md5 逐字节相同。
- train 抽样两条口径(本脚本自定,非官方):
  ① **六类任务等比例**分层(34/34/33/33/33/33)——原始 train 分布严重倾斜
  (pick_two 813 vs look_at 308),而 test 侧接近均匀(17–31),不分层会让探针偏向 pick_two;
  ② **每个任务配置最多取一条 trial**——train 的 1465 个配置摊着 3553 条,
  每配置一条让 200 条覆盖 200 个不同配置。
- val/test 全量,六类分布与论文 Table 1 逐字对上(35/27/25/24/16/13 与 31/24/23/21/18/17)。
- ⚠️ **与 appworld 的题单有一处不同**:我们这三份**有末尾换行**,`wc -l` 与条数相等;
  appworld 那三份没有,`wc -l` 各少 1。skill 的 G9 判据写的是后者,别照搬。

## 3. 口径决策:自然语言动作 → 工具名 + 具名参数

ALFWorld 的动作不是函数调用,是自然语言。**取模板细分口径**(用户 2026-07-31 拍板):

| 原始动作 | label / label_call |
|---|---|
| `take mug 1 from desk 1` | `take` / `take(obj=mug 1, from=desk 1)` |
| `go to countertop 1` | `go` / `go(to=countertop 1)` |
| `heat potato 1 with microwave 1` | `heat` / `heat(obj=potato 1, with=microwave 1)` |
| `move mug 1 to sinkbasin 1` | `move` / `move(obj=mug 1, to=sinkbasin 1)` |
| `inventory` | `inventory` / `inventory()` |

依据 `alfworld/data/alfred.twl2` 的 13 条官方模板做**最长前缀匹配**,介词位切成具名参数。

**否掉的方案**:沿用 `build.py:70-79` 的 catch-all 动词切法
(`take(arg=mug 1 from desk 1)`)。它零代码改动、tales 用它训过 11 个 run,
但介词进参数、多词动词腰斩(`go to X` → `go(arg=to X)`)、参数是一整个不可切的长串
—— mext 只有一个 span 可学、cgen 要现编整串,等于把这批的裁决格(§1 预期 2)废掉。

## 4. 环境与语法(已实测)

- 环境自建:`envs/alfworld/venv`(uv),与 `envs/appworld/venv`、`envs/tales/venv` 对称。
  版本钉死 `alfworld==0.4.2` / `textworld==1.7.0` / `fast-downward-textworld==20.6.4` /
  `TatSu==5.8.3` / `jericho==3.3.1` / `numpy==2.2.6` —— 这组在本机已装成功过
  (`fig1_pilot/fig1-env`),照抄不让 pip 自己解。
- 数据软链到已有的 `fig1_pilot/alfworld_data`(2.1G),不重复占盘。
- ⚠️ **语法断代(头号静默失败点)**:alfworld ≥0.4.0 把 `put X in/on Y` 改成了
  `move X to Y`(`alfred.twl2:211` 实测是新语法)。而 ReAct / Reflexion 公开的那份
  few-shot prompt **全是老语法**,照抄进来每个放置动作都会收到 `Nothing happens.`,
  episode 全体超时失败,**且一声不吭**,看上去像模型菜。提示词必须自己写。
- 非法动作的统一回话就是 `Nothing happens.`(TextWorld 故意做得含糊)。
- 成败判 `infos["won"][0]`,**不能判 `dones`**——done 还包括步数耗尽。
- 步数上限 50(论文与代码同值),比 appworld 的 30 高。

## 5. 阶段安排

| 阶段 | 内容 | 占卡 |
|---|---|---|
| A | 采集 948 题(2 模型 × 474)。转 gpu-run。 | 是 |
| B | **与 A 并行**:annotate 的 alfworld 分支、eval 分支、八处 `--env` choices、configs | 否 |
| C | 造数据 → 四格 smoke → 8 格训练 → 依赖顺序评测 → 矩阵 | 是 |
| D | 收官六连 | — |
| E | **回写 skill**(见 §7) | — |

## 5.1 放量前 smoke 的实测结论(2026-07-31 22:4x–23:0x,12 题 220 步)

两轮:第一轮每模型 1 题(val 最易的 `look_at_obj_in_light`),
第二轮每模型 4 题(`pick_and_place` / `clean` / `heat` / `pick_two`,从 val 各取第一条)。
产物在临时目录,**未污染正式采集目录**。

| | 题 | 步 | 通关 | 非法动作率 | 最短思考(字符) | **短于 40 字符的步** |
|---|---|---|---|---|---|---|
| q36 | 5 | 88 | 4/5 | 4.5% | 78 | **0** |
| gptoss | 5 | 132 | 3/5 | 1.5% | 516 | **0** |

- **思考长度**:合计 220 步**一步都没有短于 40 字符**,最短 78。
  `build.py` 的整步丢弃(§6.4 的头号风险)在这批不成立。
  q36 中位 241 / gptoss 中位 2523;单步最长 q36 22854、gptoss 33118。
- **每题平均步数**:q36 **21.2**、gptoss **31.8**。未通关的都是撞 50 步上限,不是崩。
- **每步中位耗时**(单分片,无并发):q36 2.05s / gptoss 2.24s。
- **动作含逗号 0 条**,gen/env 全程配对(含 NO_ACTION 兜底触发的那几步)。
- **服务**:gptoss 在 H100(95G)上起得来且**未降参数**,KV cache 20.45 GiB,
  `--gpu-memory-utilization 0.92` 原样保留,跨批次可比性未破坏。

## 6. 已知风险(开工前就知道的,收官时逐条对账)

1. ~~**语法断代**(§4)~~ —— ✅ **2026-07-31 已实测排除,而且是结构性排除**。
   提示词里**一个动作模板都没写死**,只要求模型"从当轮 `admissible_commands` 逐字抄",
   候选由环境每轮给出,所以永远跟着 alfworld 版本走。实测三重证据:
   ① 候选里出现 `move alarmclock 2 to desk 1`,老语法 `put X in/on Y` 命中 0 条;
   ② gptoss 真发了 `move ...`,环境回 `You move the alarmclock 2 to the desk 1.`;
   ③ 主动发一条老语法 `put cup 1 in countertop 1` 做对照 → `Nothing happens.`。
2. **cgen 格零里程**。tales 已替 annotate/mtool/ctool 趟过自然语言动作的口径
   (11 个训练 run、2 次回放评测),但**自然语言动作上从来没跑过一次 cgen**。
   要盯 `eval_causal_call.py:138` 的切法一致性 assert:
   annotate 侧从不切逗号、eval 侧永远切,参数值里一旦出现逗号就静默扣分。
   ALFWorld 的实体名(`mug 1`)天然无逗号,但**收完数据要 grep 一遍确认**。
3. **unit 含斜杠**(`<task_config>/<trial>`,~90 字符)。采集器落盘文件名必须转义,
   否则会当成子目录。
4. ~~**`reasoning` 短于 40 字符的步会被 `build.py` 整步丢弃**~~ —— ✅ **已实测排除**:
   220 个 smoke 步一步都没低于门槛,最短 78 字符(见 §5.1)。
   `fig1_pilot/fig1_run.py` 的提示词明令"只回一条命令、不许有别的字"、**根本不产思考**,
   所以它不能直接当采集器;`run_alfworld.py` 重写成了 appworld/tales 那种「思考 + 一条动作」。
5. **不要用 ReAct 的 `think:` 单独成步**。那会在轨迹里造出
   `action=think:..., result=OK.` 的假步,污染事件与 `build.py` 的 gen/env 配对契约。
6. **三个静默口**:`summarize_matrix.py:67` 的 `--models` 默认表不含新模型组合;
   `summarize_matrix.py:21` 的 `CELLS`;`gen_launch.py:117-122` 会把 outdir **强制**
   改成 `appworld_<model_key>`。漏一个就是白跑一批。
7. **`input_modes.py:58` 的 `--env` 没有 choices** —— extending.md §2.1 的"七处"清单
   漏了它,实际是八处。传错环境名不会被 argparse 拦。

## 7. 收官必须回写 skill 的条目(Phase E 预登记)

发现一条记一条,**不留到以后**:

- `extending.md §2` —— ALFWorld 标注为「已接」,并把每处分支该填什么补上
  (原文只能给"要改哪些位置",给不出"每处该填什么")。
- `extending.md §7` —— 删掉「ALFWorld 在本仓库不存在」(**已证伪**);
  「tales 链路未验证」按 c2 的实测结果更新。
- `extending.md §2.1` —— `--env` choices 从七处改为**八处**(补 `input_modes.py:58`,
  且它**无 choices**,是静默口)。
- `extending.md §5` —— 新静默点从 **#20** 起顺延。
- `gates.md` —— 新门禁从 **G19** 起顺延,不许复用旧号。
  本批至少要新立一道:**采集前的语法版本自证**(§6.1)。
- `SKILL.md` Phase 0 的 `<ENV>` 候选加 `alfworld`;C1 节的 G9 判据补上
  「题单末尾换行与否因环境而异」这条(§2.2)。
- `invariants.md` —— 记 c2 的口径:模板细分切法、三堆映射、train 分层抽样两条口径,
  以及"切不动即整步丢弃并分原因计数"这条兜底策略。

### 施工中新发现、必须回写的(逐条记,发现的当下就写)

- **`extras=["gamefile"]` 只挂 `AlfredDemangler` 拿不到,永远是 `None`**。
  填这个字段的是另一个 wrapper `AlfredInfos`(`alfworld/agents/environment/alfred_tw_env.py:37`)。
  已实测对照。→ `extending.md §5` 新静默点。
- **`ops/launch_c1.py` 的批次前缀写死**:`:53` 的 `rid = f"c1_{model}_{cell}"`、
  `:54` 的 `aw_official_v1`、`:72` smoke 写死 `"q35"`。c2 要用它就得泛化成
  带 `--batch` / `--data-root` 的版本,否则会长出 `launch_c3.py`、`launch_c4.py`。
  → extending.md §7 存疑的那条("若它是正式组件,情形 A 还要多改一处")**成立**。
- **题单末尾换行与否因环境而异**:appworld 三份无末尾换行(`wc -l` 各少 1),
  ALFWorld 这三份有(`wc -l` = 条数)。skill 的 G9 判据写的是前者。
- **服务日志文件是 0 字节**:vLLM 走 `tee` 时 stdout 全缓冲,进度只能从
  `tmux capture-pane` 读,`tail log` 看不到东西。→ `gates.md §3` 加案例。
- **台账 name 必须与批次对得上**:施工中出现过一条 smoke 服务记成 `inject_smoke`、
  workdir 指 `pipeline/inject` 的情况,违反"run_id 四处一致"。
  → 派活的任务书里要显式给定台账 name。
- **提示词的抗版本漂移写法**:不写死动作模板、只要求"从当轮候选逐字抄"。
  这条比"这次写对了"强一个量级,值得写进 `extending.md §2.2` 作为新环境的通用做法。
