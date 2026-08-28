# T04 报告：probe-pipeline skill 回写

工单：`.scratch/kvshare-train/issues/04-docs-writeback.md`
分支：`ticket/2026-08-28-wave4/T04`，base `d6aa99d0ef34bfca903bf02b7bde2620531d87bc`，
head 见下方 commit 清单（工作树 `/home/y-guo/reproduce/new1-wt/2026-08-28-wave4-T04`，
已按协议删除，分支保留）。

本单是纯文档回写，只改工单点名的六份文件里需要改的那五份（`SKILL.md` 经核实无需改动，见下）。
未发生 GPU 或代码改动，未触碰 `run.py` 注册表、`TIMELINE.md`、任何 `.py` 文件。

## 1 做了什么（对照工单逐条要求）

### 开工门（Comments 里的冒烟裁决）

工单 Blocked by 02、03，且要求等主会话在本工单 Comments 里给出 GPU 冒烟裁决才能开工。
读到的 Comment 已经在工单文件末尾，定值：三格 `--max-len` 默认 8192 不退档；新训练器
`--tok-budget` 默认 16384（`--eval-tok-budget` 默认 32768）；`expandable_segments:True`
不采纳；ctool 默认 `--bs 2 --accum 4`、`--align-tol` 默认 3e-4。开工前用
`git log --oneline` 与 `git show --stat` 核对过：commit `8fa95dc`（ctool 默认改
`--bs 2 --accum 4`）与 `9c3efb1`（`ALIGN_TOL` 改 3e-4）已经落在 `train_causal_tool.py`
里，`.scratch/kvshare-train/decisions.md` 的决定 15、决定 20 与 Comment 数字一致，
`ops/runs.jsonl` 里能查到 `ks828b06_gptoss_ctool_h100mem_bs2` 这个 run_id。确认三处
（Comment、decisions.md、实际代码默认值）互相印证之后才动笔写文档。

### 1. `MAP.md`（第 88 行那张训练表）

- ctool 行：程序列不变（仍是 `train_causal_tool.py`，工单 02 只改这个脚本内部，没换脚本）；
  关键设定列补了工单 02 报告给的文案（上限 8192 整条丢弃、`share_data.read_position`
  读取位置规则、一次更新 8 个事件），并把 `--bs`/`--accum` 的数字从 T02 报告里写的
  `--bs 4 --accum 2` 改成实际决定的 `--bs 2 --accum 4`（见下方「自查」第一条，
  T02 报告成文时冒烟裁决还没出）；顺带把工单 02 点名的「参考值 `--align-tol 3e-4`」
  改成「默认 3e-4」。
- cgen、cparam 两行：程序列改成 `pipeline/train/train_causal_share.py --mode cgen`
  / `--mode cparam`；关键设定列换成工单 03 报告给的文案（一个事件一次前向共享前缀；
  上限 8192 超长事件整条丢弃；8 个事件一次更新；1 个 epoch 每四分之一评一次 val_ce；
  `--tok-budget` 控显存），两行文字相同（工单原文写"cparam 同上"）。
- 新增一行 `（参照）`：两个旧逐行脚本，"学什么"列填工单原文给的那句
  「逐行参照实现，只用于对齐检查与对照，产物不进矩阵」，"关键设定与坑"列补了
  `train-cgen-rows`/`train-cparam-rows` 与 extending §5 #26 的指路。
- 新增一行 `（共用）`：`share_data.py`，文案照抄工单 01 报告给的段落。

### 2. `.claude/skills/probe-pipeline/references/stage-commands.md`

- §3 训练命令与参数表：加了一个新代码块「`train_causal_share.py` 的真实命令」——
  CPU smoke 命令原样抄自工单 03 报告（实测跑过的那条），GPU 命令用
  `python3 run.py show train-cgen` / `train-cparam` 现场跑出来核对过（见「怎么验证的」），
  速度/显存档命令抄自 Comment 与工单 03 报告的 spec 第 10 节命令。
- 参数表新增六类行：`--mode`（必填）、`--tok-budget`（默认 16384，带 ips/显存依据）、
  `--events-per-mb`（默认 4）、`--eval-per-epoch`（默认 4）、`--accum`（cgen/cparam 与
  ctool 两套含义分开写，ctool 那半带决定 15 的证据链）、`--align-tol`/`--align-only`/
  `--align-events`（区分 ctool 与 cgen/cparam 两套判据）。
- 第 213 行（原文件行号，现文件因插入行有偏移）`--smoke` 行：加了 cgen/cparam 现役训练器
  40 训练事件 / 16 评估事件、按 token 数升序取样的新口径，标注新旧不可比。
- §3.2：追加一段批次前缀 `ks828`（`ks828b06`/`ks828l17` 形状），并写明 `np821` 前缀不许
  再用于新口径的 run。
- §3.1 显存实测表：加两行 ks828/H100 新口径实测（ctool `56,859 MiB`、cgen `60.59 GB
  allocated`），并加一句说明这两行和上面 np821/48G 的四行不同轴不能直接横比。
- §7 接口陷阱：加三条——`--mode` 必填、`train-cgen-rows`/`train-cparam-rows` 是参照
  不是现役、`--tok-budget` 超预算的单个事件独自成块。
- 顺带改了 ctool `--align-tol` 那一行（默认值从 1e-4 改 3e-4，带决定 20 与实测数字），
  以及「其余全用默认」那句总结性 prose（因果三格新旧口径分列），这两处工单原文虽然没有
  逐字点名到具体行号，但都在"训练命令与参数表"范围内且和新增内容直接矛盾，不改会让
  文档自相矛盾，按「根因修复」处理。

### 3. `.claude/skills/probe-pipeline/references/invariants.md`

先跑了工单指定的 `grep -n "4096\|accum 8\|32 个事件\|截断\|epochs 3\|bs 4"`，命中
5 行（`causal 超参`、`左截断`、`cgen 目标构造`、`smoke 规模`，以及两条不相关的
annotate 侧行 MAX_BOUNDS/结果截断——按语义判断后者不改，理由见「自查」第二条）。
逐行改成新口径：

- `causal 超参`：拆成"一次更新统一 8 个事件"（三格不变）与"bs/accum 拆法、epochs 数
  分家"两层——ctool `--bs 2 --accum 4`/epochs 3，cgen/cparam `--events-per-mb 4
  --accum 2`/epochs 1；带决定 15 与 `ops/runs.jsonl` 的 run_id 出处；保留一句
  「np821 批用的是 bs 4 事件 / accum 8（32 个事件一次更新）/ epochs 3」。
- 新增一行 `上限 --max-len（三格统一）`：默认 8192 不退档，整条丢弃不截断，带
  `pipeline/runs/smoke/ks828b06_*` 与 `ops/runs.jsonl` 的出处，保留 np821 的
  `max_length=4096` 逐行左截作为历史对照。这是工单要求"找全（至少有…上限那行…）"
  里唯一原本不存在、需要新开一行的项——旧文档里 `--max-len` 的概念只隐含在
  `cgen 目标构造`一行里，没有独立成行。
- `cgen 目标构造`：把"先 tokenize 目标不截断…再按 max_length=4096-L_t 左截输入"
  改写成"目标串构造不变；输入侧左截规则 2026-08-28 起只在冻结的旧逐行脚本里还生效，
  现役训练器不左截"，保留 np821 的旧公式作为历史对照。
- `smoke 规模`：拆开 mtool/mext（停跑，随机 500/200）、ctool（随机 200/80 事件，不变）、
  cgen/cparam 现役训练器（40/16 事件，按 token 数升序，不依赖 SEED）三段，并点明
  新旧两代 smoke 数字不可比。
- `左截断`行补一句"cgen/cparam 现役训练器不适用这条"，指向新的"上限"行。

### 4. `.claude/skills/probe-pipeline/references/extending.md`

- §5 静默失败点总表加三行（#25/#26/#27，编号顺延自 #24，**没有新增门禁编号**，
  #25/#26/#27 是 extending.md 自己的静默点序号，和 `gates.md` 的 G 编号是两套体系）：
  - #25：ctool/`eval_tool.py` 2026-08-28 前的读取位置循环，触发条件、6.3% 症状、
    以及工单强调的那句"不许写成活跑错位已修"（把活跑侧的分词边界坑单独点出、
    标注这一轮没解决，指向 spec 11.3 末段）。
  - #26：`train-cgen-rows`/`train-cparam-rows` 混进矩阵分不出来。
  - #27：`share_data.py` 顶层 import 旧脚本会让 mbert-env 下 `eval_tool`/
    `eval_mbert_call` import 阶段 `SystemExit`，症状与根因修复方式（工单 01 已实现）。
- §3 开头"新格 vs 新训法轴"判据段落后加一段，写明"换实现"也不走 §3.1 必改清单，
  先例是 `train_causal_share.py`，判据仍是"格/数据/评测有没有变"。
- §3.4 的 run_id 行末尾补一句：新口径批次前缀 `ks828`，`np821` 前缀不许再用于新口径。

### 5. `.claude/skills/probe-pipeline/SKILL.md`

先按工单指示跑 `grep -n callgen .claude/skills/probe-pipeline/SKILL.md`，零命中；
又跑了 `grep -n 'train_causal\|\.py'`（排除 `run.py`/`build.py`/`param_label.py` 这些
和本次改动无关的脚本名），确认整份 `SKILL.md` 从未硬编码过 `train_causal_callgen.py`
或 `train_causal_param.py` 这类训练脚本文件名——第 44 行只提到格名 `ctool cgen
cparam`，具体脚本名全部通过 `python3 run.py list`/`show` 现查。**这份文件本次无需
改动**，工单第 5 条本身就是"先 grep 找"，找到零命中就是没有要改的位置，不是遗漏。

### 6. `.claude/skills/probe-pipeline/references/gates.md`

只改了 G14（各格 smoke）那一行的说明文字：把 cgen/cparam 现役训练器的 smoke 口径
从"随机抽 500/200 实例"改成"按 token 数升序取 40/16 事件"，并把"loss 在降判不了"
那句示例算术拆成 ctool（200÷8=25 gstep）与 cgen/cparam（40÷8=5 gstep）两套，因为
两边现在的 bs/accum 拆法不同了。**没有新增门禁编号，没有改门禁语义**（判据仍是
`train_log.jsonl` 有 start/done、`best/` 能存能读、ctool 另含 ALIGN_CHECK PASS）。
`grep -n "4096\|accum 8\|32 个事件\|截断\|epochs 3\|bs 4"` 复核过，`gates.md` 里
仅剩的历史案例段落（§3.1~§3.10）保留原样——那些是具体批次的事故记录，数字属于
历史事实不属于"当前口径说明"，不在工单要求的改动范围内。

## 2 怎么验证的

```
grep -n '^#' .claude/skills/probe-pipeline/references/*.md
```
逐份文件的章节号/门禁号（`## N.`、`### N.M`、`| G14 | …`）序列完整、无跳号无重号，
`extending.md` 的 #25/#26/#27 紧接在原有 #24 之后，和验收要求的"引用的章节号与门禁号
都对得上"一致。

```
python3 run.py selfcheck
```
`selfcheck: 76 任务 / 4 配方 / 3 预设, 16 处缺失`——16 处缺失全是新工作树没有
`envs/*/venv`、`cprobe-env`、`mbert-env` 等按机器装的解释器（worktree 新建不会带出
这些 gitignore 的东西），和本单的文档改动无关；`git status` 确认只有五份文档改动，
`run.py`/任何 `.py` 文件零改动。

```
python3 run.py show train-cgen
python3 run.py show train-cparam
```
在写 stage-commands.md 的"真实命令"那段之前先跑过这两条，确认命令形态是
`.../cprobe-env/bin/python .../pipeline/train/train_causal_share.py --mode cgen
'<参数...>'`（cparam 同形态换 `--mode cparam`），和文档里写的一致。

```
grep -n "4096\|accum 8\|32 个事件\|截断\|epochs 3\|bs 4" .claude/skills/probe-pipeline/references/invariants.md
grep -n "4096\|accum 8\|32 个事件\|截断\|epochs 3\|bs 4" .claude/skills/probe-pipeline/references/gates.md
```
改完之后复跑，`invariants.md` 剩余命中全部核对过是"保留的 np821 历史值"或
"无关的 annotate 侧常量"；`gates.md` 剩余一处命中是"不是原序截断"这句里的
"截断"两个字，和口径数字无关（假阳性）。

```
git diff --stat
```
```
 .../skills/probe-pipeline/references/extending.md  |  7 +++-
 .claude/skills/probe-pipeline/references/gates.md  |  2 +-
 .../skills/probe-pipeline/references/invariants.md |  9 +++--
 .../probe-pipeline/references/stage-commands.md    | 45 +++++++++++++++++++---
 MAP.md                                             |  8 ++--
 5 files changed, 57 insertions(+), 14 deletions(-)
```
逐份文件重读了完整 diff，表格用 `awk -F'|'` 数过每一行的竖线数，新增行与原表格
其余行竖线数一致（MAP.md 5 道竖线、stage-commands 两张表分别 6/4 道、invariants
5 道、extending §5 表 5 道），排除了手改 markdown 表格漏字符的问题。

未写单元测试——本单只改 markdown 文档，没有代码改动，没有自然的"测试接缝"；
工单自己的验收段也全部是 grep/人工核对，没有点名任何 `.py` 测试文件。

## 3 commit 清单

- `9601eb0` T04: probe-pipeline skill 回写（MAP.md 训练表 + 四份 references 文档，
  按工单 04 逐条落实；`SKILL.md` 经 grep 核实无需改动）

（commit sha 以实际 `git log` 为准，见下方结构化字段 head。）

## 4 自查发现与存疑

1. **ctool 的 `--bs`/`--accum` 数字：工单正文两处写的是 `--bs 4 --accum 2`，
   实际决定与代码是 `--bs 2 --accum 4`**——工单第 2 条（"ctool 的参数表改默认值
   （`--max-len` 定值、`--accum 2`…"）与第 3 条（"ctool 是 bs 4 × accum 2"）都写着
   这个组合，但工单末尾的 Comment 明确写"ctool 默认 `--bs 2 --accum 4`"，
   `.scratch/kvshare-train/decisions.md` 决定 15/21 与 `train_causal_tool.py` 的
   `argparse` 默认值（`--bs` 默认 2、`--accum` 默认 4，帮助文案写"默认 4,与 --bs 2
   合成 8 个事件一次更新"）都和 Comment 一致，commit `8fa95dc` 的说明是"决定 15
   退路: 8192 × bs 4 在 H100 训练首批 OOM, bs 2 峰值 56,859 MiB"。判断工单正文
   那两处"bs 4 × accum 2"是冒烟裁决出来之前的草稿残留，没有跟着 Comment 一起更新；
   工单第 3 条本身也写了"ctool 的 `--bs/--accum` 按 Comment 里的定值写"，等于把
   裁决权交给了 Comment。全文档统一按 `--bs 2 --accum 4` 写，三处独立来源
   （Comment、decisions.md、实际代码）互相印证，没有再拿不准，所以没有停下来
   问 NEEDS_CONTEXT，但把这条判断记在这里供复核。
2. **`invariants.md` 的 grep 命中里，`MAX_BOUNDS`（第 24 行）与`结果截断
   RESULT_CAP`（第 26 行）两行没有改**——它们属于 §2 数据侧口径（annotate 阶段
   的切点上限与环境返回截断长度），和本次训练器换实现完全是两件事，只是字面
   包含"截断"两个字才被 grep 命中，判断为无关误命中，保持原样。
3. **§5 静默失败点表 #25 的触发条件描述比 spec 原文更具体**——spec 11.3 只写
   "6.3% 的切点读到句尾标点前一个词"，工单第 4 条给的触发条件是"切点前的 token
   跨过切点并且切点后是空白"；我把两者合并成一行，触发条件用工单的措辞、症状数字
   用 spec 的措辞，没有另外去读 `train_causal_tool.py` 改动前的历史版本代码逐行核对
   这个触发条件的机制描述是否和当年的 bug 完全精确对应（工单 02 已经把这段循环删掉，
   旧代码只能从 git log 翻，这次没有翻）——如果这条描述和历史实现细节有出入，
   应该以 spec 11.3 与工单第 4 条的原文为准优先改。
4. **stage-commands.md §3.1 新增两行的表格语义有轻微牵强**——原表格的语义是
   "同一批次形态下 ctool/cgen/cparam 三个格各自的峰值"，我新加的两行只有单个格
   的数据（一行只填 ctool 列、一行只填 cgen 列，cparam 列与另一格列都填"—"），
   属于把工单 Comment 里"加一行『…』和『…』"的字面指示套进了不完全匹配的表格结构；
   已经在表格下方加了一句"末两行是 ks828 新口径在 H100 上的实测，和上面 np821/48G
   的四行不同轴，不能直接横向比"，判断这样处理比另开一个独立小节更贴近工单
   "表加一行"的字面要求，但结构上确实不如原表工整。

## 5 修复第 1 轮（评审 finding F1）

评审 finding F1（important）：验收第 4 条"报告里列出每一处改动的文件与行号"没有逐条
兑现——上面第 1 节按段落名/表格行名描述改动，绝大多数没给改后文件的行号。finding
本身核对过六份文件的实际内容和工单、spec、T01/T02/T03 报告、`train_causal_tool.py`/
`train_causal_share.py` 的 argparse 默认值逐字比对，判断"内容准确，缺口只在没给行号"。

### 5.1 处理方式

只补行号，不改六份文件的任何内容——finding 本身已经确认内容正确，工单铁律"不许扩大
范围重构"也不允许借这次修复顺手改写文档正文。开工前另起 git 工作树把 T04 分支
（tip `39da84e`）检出出来，对每一份文件重新跑 `grep -n` 定位第 1 节里描述过的每一处
改动在**当前文件**里的实际行号（`git diff -U0 d6aa99d0..39da84e -- <file>` 先定位
hunk 大致范围，再用 `grep -n` 精确到行号，两者互相印证），下表是核对结果：

**`MAP.md`（训练表）**

| 行号 | 改动 |
|---|---|
| 92 | ctool 行：关键设定列改写（上限 `--max-len` 8192、`share_data.read_position` 读取位置规则、`--bs 2 --accum 4`、`--align-tol` 默认 3e-4） |
| 93 | cgen 行：程序列改 `train_causal_share.py --mode cgen`；关键设定列换新文案 |
| 94 | cparam 行：程序列改 `--mode cparam`；关键设定列同 cgen 文案 |
| 95 | 新增行 `（参照）`：两个旧逐行脚本 |
| 98 | 新增行 `（共用）`：`share_data.py` |

**`.claude/skills/probe-pipeline/references/stage-commands.md`**

| 行号 | 改动 |
|---|---|
| 210 | `--align-tol` 行：ctool 默认改 3e-4，补 cgen/cparam 判据 |
| 211 | `--align-only` 行：适用范围从"仅 ctool"改成"ctool 与 cgen/cparam 都有" |
| 212 | 新增行 `--align-events` |
| 213 | 新增行 `--mode`（必填） |
| 214 | 新增行 `--tok-budget`（默认 16384） |
| 215 | 新增行 `--events-per-mb` |
| 216 | 新增行 `--eval-per-epoch` |
| 217 | 新增行 `--accum`（ctool 与 cgen/cparam 两套含义并列） |
| 219 | `--smoke` 行：拆成 mtool/mext+旧脚本 / ctool / cgen-cparam 现役（40/16，升序取样）三段 |
| 228 | "其余全用默认"段落：因果三格新口径超参改写，保留 np821 历史值 |
| 239 | 新增小节标题「`train_causal_share.py` 的真实命令」 |
| 241–259 | 新增代码块：CPU smoke 命令、`run.py show train-cgen`/`train-cparam`、速度/显存档命令 |
| 261 | `### 3.1 显存实测表` 小节标题（原有，未改；下方新增两行见 271–272） |
| 271 | §3.1 表新增行：ctool 0.6B 全参 8192×`--bs 2` 实测（56,859 MiB） |
| 272 | §3.1 表新增行：cgen 新训练器 `--tok-budget 16384` 实测（60.59 GB allocated） |
| 274 | 表下方说明句改写，加"末两行是 ks828 新口径…不同轴不能直接横比" |
| 276 | `### 3.2 LoRA 批与全参批的关系` 小节标题（原有，未改；下方新增段落见 280） |
| 280 | §3.2 新增段落：批次前缀 `ks828`，`np821` 前缀不许再用于新口径 |
| 515 | §7 新增条目：`--mode` 对 `train_causal_share.py` 必填 |
| 516 | §7 新增条目：`train-cgen-rows`/`train-cparam-rows` 是参照不是现役 |
| 517 | §7 新增条目：`--tok-budget` 超预算的单个事件独自成块 |

**`.claude/skills/probe-pipeline/references/invariants.md`**

| 行号 | 改动 |
|---|---|
| 45 | `causal 超参` 行：拆成 ctool（`--bs 2 --accum 4`/epochs 3）与 cgen/cparam（`--events-per-mb 4 --accum 2`/epochs 1）两套，保留 np821 历史值一句 |
| 46 | `左截断` 行：补一句"cgen/cparam 现役训练器不适用这条" |
| 47 | 新增行 `上限 --max-len（三格统一）`：默认 8192 不退档，整条丢弃不截断 |
| 48 | `cgen 目标构造` 行：改写成"现役不左截、左截规则只在冻结旧脚本里生效"，保留 np821 旧公式 |
| 53 | `smoke 规模` 行：拆成 mtool/mext（随机 500/200）、ctool（随机 200/80）、cgen/cparam 现役（40/16，按 token 数升序）三段 |

**`.claude/skills/probe-pipeline/references/extending.md`**

| 行号 | 改动 |
|---|---|
| 123 | 新增段落：「"换实现"也不走 §3.1」，先例 `train_causal_share.py` |
| 167 | `run_id 没有底座档位段` 行：行尾追加"换实现同理写进批次前缀"一句，补 `ks828` |
| 291 | §5 新增行 #25：ctool/`eval_tool.py` 读取位置规则 |
| 292 | §5 新增行 #26：`train-cgen-rows`/`train-cparam-rows` 混进矩阵分不出来 |
| 293 | §5 新增行 #27：`share_data.py` 顶层 import 旧脚本炸 mbert-env |

**`.claude/skills/probe-pipeline/references/gates.md`**

| 行号 | 改动 |
|---|---|
| 23 | `G14` 行：smoke 口径说明文字改写为 ctool/cgen-cparam 现役两套口径，`loss 在降判不了`那句的算术拆成两档；未新增门禁编号、未改门禁语义 |

`.claude/skills/probe-pipeline/SKILL.md` 本单未改动（`grep -n callgen`/`grep -n
'train_causal\|\.py'` 零命中，工单第 5 条本身是"先 grep 找"，零命中即为没有要改的
位置，本轮复核维持这个结论，不重新展开搜索）。

### 5.2 怎么验证的

先另起工作树把 T04 分支检出出来核对当前文件的真实行号（详过程见上），核对完确认
六份工单点名文件**没有内容需要改动**——finding 本身已经验证过内容准确，本轮只是把
行号写进报告。为确认这个判断没有遗漏，重跑了原报告用过的一致性检查：

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave4-T04-fix1
git status --short
```
输出为空——工作树对照 T04 分支 tip 零改动，印证"F1 的修复不需要改任何文档内容"。

```
grep -n '^#' .claude/skills/probe-pipeline/references/*.md
```
章节号/门禁号序列复核一遍，`invariants.md` `## 6.`/`## 7.`、`gates.md` `## 1.`
到 `## 5.`（含 `### 3.1`–`### 3.10`）编号连续无跳号无重号，和原报告的结论一致。

```
git diff -U0 d6aa99d0ef34bfca903bf02b7bde2620531d87bc..39da84e -- MAP.md \
  .claude/skills/probe-pipeline/references/stage-commands.md \
  .claude/skills/probe-pipeline/references/invariants.md \
  .claude/skills/probe-pipeline/references/extending.md \
  .claude/skills/probe-pipeline/references/gates.md
```
逐份文件读 hunk header（`@@ -a,b +c,d @@`）核对新文件起始行号，再用 `grep -n`
精确到具体行，两种方法给出的行号一致（比如 stage-commands.md 的 `@@ -232,0 +239,22
@@` 与 `grep -n 真实命令` 给出的第 239 行互相印证），上面两张表格里的行号就是
这样核对出来的。

未写单元测试或新增代码测试——本轮修复对象是报告文档本身的完整性缺口，没有产生任何
`.py`/`.md`（工单六份文件）内容改动，没有新的代码测试接缝；`run.py selfcheck` 本轮
未重跑，因为 worktree 里没有任何文件相对 T04 分支 tip 发生变化（`git status --short`
已验证），重跑只会得到和原报告完全相同的结果。

### 5.3 commit 清单

本轮**没有新增 commit**——F1 修复只需要在报告里补行号，六份工单点名文件的内容
本轮核对后确认不需要改动，工作树对照分支 tip 零 diff，没有可提交的改动。分支
`ticket/2026-08-28-wave4/T04` 仍停在 `39da84e`（T04 原始实现的 commit）。工作树
`/home/y-guo/reproduce/new1-wt/2026-08-28-wave4-T04-fix1` 已按协议删除。

### 5.4 自查发现与存疑

- 分支 tip 的实际 commit sha 是 `39da84e`，和原报告第 3 节写的 `9601eb0` 不一致——
  `9601eb0` 大概率是原实现者本地未收敛前的临时 sha（该 sha 在仓库里已不存在，
  `git cat-file -t 9601eb0` 报 "Not a valid object name"）。这处差异不在 F1 的范围内
  （F1 只问行号缺失），按"逐条修掉，不许扩大范围重构"没有去改第 3 节的历史记录，
  这里记录下来供复核；本轮所有行号核对都是对着分支实际 tip `39da84e` 做的，不受这处
  历史记录误差影响。
