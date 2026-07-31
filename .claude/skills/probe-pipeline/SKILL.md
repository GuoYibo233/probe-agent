---
name: probe-pipeline
description: new1 探针流水线的执行入口——从轨迹采集到矩阵报告的全链一条龙：定批次 → 采集(GPU) → 写码/改码(CPU，与采集并行) → 双验收线 → 造数据集 → 四格 smoke → 批量训练 → 依赖顺序评测 → 矩阵汇总 → 记账收官。Invoke whenever Dungeon♂Master says "跑流水线"、"跑一批探针"、"新数据集跑一遍"、"出矩阵"、"换个环境跑"、"run the pipeline"、或任何要把 collect/annotate/train/eval 串起来跑的活。单个 GPU 任务只用 gpu-run，这个 skill 管的是整条链。
version: 1.0.0
---

# probe-pipeline — 探针流水线全链执行

一条五段流水线（collect → annotate → train → eval → inject），
套在四阶段执行壳里（A 采集 / B 写码 / C 训练评测 / D 收官）。
每段之间卡一道门禁，**跳门禁 = 违规**。

配套文档（照抄命令去第一份，判断该不该改去第二份，卡住了去第三份）：
- 命令表：`references/stage-commands.md`
- 口径清单：`references/invariants.md`（改这里任何一条 → 新老数字不可比）
- 门禁与应急：`references/gates.md`（门禁编号 G1–G18，下文按编号引用）
- 扩展清单：`references/extending.md`（**加新模型 / 加新环境从这份进**，含静默失败点总表）

工程规则的上位法仍是 `CLAUDE.md`；GPU 发射的上位法仍是 `.claude/skills/gpu-run/SKILL.md`。
**本 skill 不自己发射 GPU 任务**——凡是要占卡的步骤一律转 gpu-run。

---

## Phase 0 — 定批次（先把这五个变量钉死，再动手）

| 变量 | 例（本轮 c1） | 定它的依据 |
|---|---|---|
| `<BATCH>` | `c1` | run_id 前缀，一批一个，全链四处一致 |
| `<ENV>` | `appworld` | appworld / bfcl / tales，决定事件抽取正则 |
| `<MODELS>` | `q35 q36 gptoss` | 被探测的 agent 模型，**永不合并同族**（q35≠q36） |
| `<CELLS>` | `mtool mext ctool cgen` | 骨架(mbert/causal) × 头(工具/参数) 四格 |
| `<DATA_ROOT>` | `pipeline/data/aw_official_v1/` | 数据集版本目录，**换口径就换版本号** |

钉完立刻做三件事：
1. 过一遍 `DATA.md §7` 检查清单（八条，每条都对应一个踩过的坑）。
2. 写一份批次计划到 `plans/<日期>-<batch>-plan.md`，说清这批要回答什么问题。
3. 确认 `<DATA_ROOT>` 是**新目录**——旧数据集一个字节都不动（G-铁律）。

现成范例照着改就行，别从零写：
标注配置 `pipeline/configs/aw_q35.json`、采集清单 `pipeline/collect/manifest_w0.json`、
排卡表 `ops/c1_placement.json`。

> 判断要不要走全链：只换模型/换数据集 → 全链；只补几个格 → 直接从 Phase C 进。

---

## Phase A — 采集（占大卡，墙钟 3–5h）

**这一段全部转 gpu-run skill**，本 skill 只负责给它正确的输入和验收标准。

1. 生成发射脚本：`python3 pipeline/collect/gen_launch.py --config <manifest.json>`
   （纯 CPU，只生成不执行；产出 `launch_servers.py` / `launch_clients.sh` / `MANIFEST.md`）
2. **派 gpu-runner** 起服务 + 发客户端。服务侧天花板是 tokyo108 六张大卡——
   27B 权重 54G、gpt-oss 63G，A6000 的 48G 装不下，一律单卡一实例。
3. 门禁 **G3 服务健康**（六个全绿才放量）→ **G4 每模型 1 题 smoke** → 放量。
4. 长杆模型（题最多那个）客户端并发开高一档，拉平三路墙钟。
5. 收尾门禁 **G6 完整性**（文件数对上题数、每文件末行 `type:"final"`）
   → **G7 显存归零** → `gpu_jobs.py finish` → `record.py finish` → commit。

⚠️ **G5 outdir 命名**：必须是标准名 `appworld_<model_key>`，
名字不标准会被下游事件抽取**静默跳过**——这个坑不报错，只让样本数变少。

---

## Phase B — 写码 / 改码（纯 CPU，**与 Phase A 并行**）

这是全链最大的并行红利：采集占满 GPU 的那几小时，把代码全写完。

- 写码顺序：annotate → eval → train 四格 → collect 生成器 → inject 校验器。
- **一把写完再跑验收，不逐段试跑正式数据。**
- 派 subagent 并行施工（本轮三个并发，eval 因 import 依赖稍后发）。
  任务书标准结构见下文「派活的写法」。

段末两道复现验收线，**不过不许进 Phase C**：

| 门 | 验什么 | 判据 |
|---|---|---|
| **G8 ACCEPT_V3DIFF** | 新 annotate 代码喂旧轨迹 | 与旧数据集九字段逐条比，不一致计数**全 0**（两个环境各跑一遍） |
| **G12 ACCEPT_EVAL** | 新 eval 代码喂旧产物 | 温度 / chosen_theta / test_frozen 三块完全一致，报告写临时目录不碰旧文件 |

这两道门是整条流水线可信度的地基：**新代码喂旧数据必须复现旧数字**，
否则后面所有新数字都无法与历史对比。详见 `references/gates.md §2`。

---

## Phase C — 造数据集 → smoke → 训练 → 评测

### C1 造数据集（CPU）
每个模型跑一次 `build.py` + `param_label.py`（命令见 stage-commands §2）。
门禁 **G9 题单行数**（注意题单文件无末尾换行，`wc -l` 各少 1）、
**G10 三模型同题**（train 堆 unit 集合完全相同，否则不可横比）、**G11 label_call 抽查**。

⚠️ **三份题单必须两两无交集，这一条要人工验**：`build.py` 对"unit 不在任何题单里"
零容忍（退 1），但对"unit 同时在两份题单里"**一声不吭**——按 train→val→test 顺序
后写覆盖，test 赢。交叠会静默让 train/test 边界失守，而报告照出、退出码 0。
换环境时先跑一句 `comm` 对拍三份题单。

### C2 四格 smoke（占卡，转 gpu-run）
门禁 **G14**：四格各跑 500 训练/200 评估/1 epoch，判据是 loss 在降、ckpt 能存能读。
因果两格另有 **G13 对齐检查**——先 `--align-only` 单跑，FAIL 即 `exit 2`。
**smoke 不过不许放量**，一次都不许。

### C3 批量训练（占卡，转 gpu-run）
`<MODELS>` × `<CELLS>` 全独立，**一把全上并行**，墙钟 ≈ 单次时长。
发射前 **G1 工作树干净**（先 commit）→ **G2 实探空卡** → 发射 → **G16 双登记**
（`gpu_jobs.py register` + `record.py start`，一个都不能漏）。

排卡表落一份 `ops/<batch>_placement.json`，逐格写死 host/gpu/额外参数——
这样重发某一格时不用重新推理机位。

### C4 评测（**内部必须串行，这是唯一有依赖的一段**）

```
先评 6 个工具格 (mtool/ctool) ── 出 REPLAY_REPORT.json + logits_test.pt
                    ↓ 提供温度与触发点 θ
后评 6 个参数格 (mext 吃 mtool 的、cgen 吃 ctool 的)
```

**双档策略**：先取 `--risk 0.05`；该档 θ 为 null 就退 `--risk 0.10` 并在报告里显式标注；
两档皆无解 **记 N/A** ——不放宽风险目标、不借用别格触发点（两者都破口径，见 gates §3.4）。

不必等训练全批收官，**逐格收官逐格派评测**（同一个 subagent 用 SendMessage 续派）。

### C5 矩阵汇总
`python3 pipeline/eval/summarize_matrix.py --runs-dir ... --out ... --risk 0.05`
两档各出一份表。⚠️ 这个脚本有三个显示局限（N/A 显示成 PENDING、
表固定读单一风险档、参数格两列无条件读可能混档），
**引用矩阵表时必须配文字说明**，别让读者误读。

---

## Phase D — 收官（强制六连，缺一不可）

1. **记数字**：每个 run 一条 `record.py finish --metric ... --conclusion ...`。
   （⚠️ record.py 三个语法坑见 gates §3.7）
2. **补方向**：结论动了 `WORKPLAN.md` 任何一条判断 → 往 `TIMELINE.md` 追加一条。
3. **补口径**：数据集的造法与设定写进 `DATA.md`（**只写设定不写结论**）。
4. **释放**：杀光 tmux session，`nvidia-smi` 三机确认本项目零占用。
5. **销号**：每个任务 `gpu_jobs.py finish`，台账清空。
6. **提交**：代码 + `ops/runs.jsonl` + `RESULTS.md` + 报告 `.md`，
   commit message 里带 `<BATCH>` 与关键数字。

---

## 派活的写法（本轮方法论的核心）

**主对话只做四件事：派活、验收裁决、git 提交、任务台账。**
一切实干（写代码、跑命令、发射、评测、记账）交 subagent。

| 活 | 派谁 | 备注 |
|---|---|---|
| 写代码 / 记账 / 清点 | `general-purpose`（opus） | 任务明确就用 opus，别上 Fable |
| 发射与评测 | `gpu-runner` | 探卡→smoke→tmux→登记→验活一条龙 |
| 长任务巡检 | `job-monitor` | 只读，kill 建议写报告里由主对话定 |

**同一个 subagent 用 SendMessage 续派**，上下文不重建（本轮发射员续派 3 次、评测员 6 次）。

任务书标准结构（五段，缺一段就会有人跑偏）：
1. **先读哪份规格的哪几节**（并声明"规格与任务书冲突时以规格为准"）
2. **硬口径**：表格化——格 / 脚本 / 解释器 / 路径，一格一行
3. **施工纪律**：不碰 git、旧文件只读、不改别人的脚本、
   崩了先读 traceback 不许硬试超两次、双环境各跑一遍 `py_compile`
4. **验收标准**：什么算过、什么算不过
5. **回报格式**：要求它列出**自行决策点**（这是发现偏差的主要手段）

⚠️ subagent 报的数字要抽验。本轮就出现过它凭印象写"差 <2e-5"、
下游记账员实读文件发现是 2.0027e-5 的情况——**数字必须从文件读**要写进任务书。

---

## 铁律

- **门禁不过就停**，不许"先跑着看看"。smoke 不过不发射、对齐 FAIL 全线停等裁决、
  评测无触发点就 SystemExit 而不是硬指一个 θ。
- **旧数据与旧数字一个字节不动**，新产物一律进新目录新版本号。
- **test 冻结一次**。θ 在 val 上选定后，test 上的数字无论多难看都原样报告——
  难看的那一格恰恰是矩阵要量的东西。
- **run_id 四处一致**：数据目录名 / tmux session / 台账 name / commit message。
- `RESULTS.md` 是渲染产物不手改；`runs.jsonl` append-only；台账只经 `gpu_jobs.py`。
- **发射前先 commit**，脏工作树下记录里的 HEAD 追不回真实代码。
- **唯一允许停下问用户的情形是"推翻前提"**——目标 split 根本跑不了、
  权重路径失效、验收线反复过不了。其余一律自动处置（详见 gates §4）。
  停之前先把已完成部分收尾干净。
