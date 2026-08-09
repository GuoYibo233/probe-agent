# T15 报告 — 文档回写：gpu-run skill 与两份方法论

工单：`.scratch/gpu-monitor-launch/issues/15-docs-gpu-run.md`
分支：`ticket/20260808-par/T15`（工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T15`，已删除）
base: `86f2b8e2fa5846f4060262989974237ad824d108`
head: `146a289e3b14de7318dcf719cb4290fe140ab92c`

## 做了什么（对照工单逐条）

工单验收项三条：

- [x] **Phase 4 只剩 commit、launch、交监控入口三步**
  `.claude/skills/gpu-run/SKILL.md` 的 Phase 4 重写为三个编号步骤：
  1. commit 代码；
  2. `python3 run.py launch <task> ... --run-id --track --piece ...`（一条命令，
     贴出完整用法，说明它按 `ops/launch_cmd.py` 头注释钉死的十步做完探卡→
     tmux 发射→30 秒验活→台账/记录/RUNMETA 三处登记，手打三条登记命令的段落
     全删）；
  3. 交监控入口（`gpu-jobs`/`gpu-jobs watch`/浏览器 `localhost:8377`）。
  Phase 3（smoke）补一句：也可以先用 `launch --dry-run` 看命令，不发射不登记。

- [x] **Phase 5 不再含定时巡检的排程条款**
  原文里"起服务期 10 分钟粒度、跑批期 15-30 分钟"的排程条款和"ETA 靠两个
  时间点的 Δitems/Δt 交叉核对"的手工步骤整段删掉，改写成「采样器接管」：
  判定/升级由 `ops/sampler.py` 常设负责，Claude 只在①用户问起、②事故记录
  有新内容两种时机才派 `job-monitor`。按工单 Comments 里主会话转记的裁决，
  **事故 agent 自动验尸补射写成"未上线（暂缓）"**，并交代清楚原因：触发规则
  纯函数 `should_trigger` 已合并，但真正拉起 agent 的 `maybe_trigger_incidents`
  读代码确认目前只是 `pass` 占位（2026-08-08 用户裁决暂缓）——没有写成现状。

- [x] **commit**：`146a289`，见下方 commit 清单。

工单正文里额外要求的两份方法论改写：

- **`references/launch-methodology.md`**：
  - Step 4 标题从"Launch in tmux"改成"What `launch` does for you"，正文改成
    讲清楚 `run.py launch` 替你做了什么（探卡 fail-closed、session/log 命名
    规则、30 秒验活窗口、三处登记）；原来的 `subprocess`/`tmux new-session`
    模板保留，但改注为「只有 `--cmd` 逃生口还用得上的参考模板」。
  - Step 3 标题从"Shard if it pays"改成"Shard via `--piece`, not by hand"，
    讲清楚多个 `--piece` 会被 `launch` 自动注入 `--shard-id i --num-shards N`、
    且任务要在注册表标 `shardable: True` 才许多分片；死分片的恢复方式改成
    `launch --refire`。
  - Step 2（挑卡规则）原样保留，未改动。

- **`references/monitor-methodology.md`**：
  - 原来的「Mandatory rules / Standard procedure / Reading tqdm output /
    Sharded-job caveat」四节（两点测速、tqdm 解析、分片 ETA 修正的手工流程）
    合并改写成一节「程序职责说明：判定从哪来」：讲清楚这套活现在是
    `ops/heartbeat.py`+`ops/sampler.py`+`ops/verdicts.py` 的常设职责，附
    `ops/verdicts.py` 六格判定表（`V_DONE`/`V_DEAD`/`V_STALL`/`V_WARMUP`/
    `V_SLOW`/`V_OK` 各自的命中条件，摘自 `judge()`）和判定线/升级线两条公式
    （常数来自 `ops/verdicts.py` `DEFAULTS`，逐项列出默认值）。
  - 「Decision tree」一节保留，表头从"Condition"改成"判定"，输入从"ETA
    computed by hand"换成采样器给的 `verdict`/`escalated` 判定值，六行分支
    对应六格判定。

## 一处发现并自行修正的问题（未在工单里点名，但直接影响文档准确性）

写 Phase 4/5 与 monitor-methodology 初稿时，我按工单字面把 `ops/verdicts.py`
的六格判定描述成"`gpu-jobs`/`gpu-jobs watch`/`gpu-jobs json` 表里已经能看到"。
读代码核对后发现这是错的：

- `ops/gpu_jobs.py` 的 `collect()` 至今仍是老的 `parse_log()`（正则抓日志尾部
  tqdm 行），`fmt_table` 的列是 `job/host/gpus/state/progress/rate/eta/session`，
  没有 `verdict`/`escalated` 列；`json` 子命令也只是 `print(json.dumps(collect()))`，
  同一套老逻辑。
- 采样器（`ops/sampler.py`）把判定写进的是它自己的 `MONITOR_DIR/latest.json`，
  和 `ops/gpu_jobs.py` 读写的 `ops/jobs.json`（台账注册表）是两份互不相通的
  文件；采样器不写台账。
- 六格判定目前**只有**采样器自带的网页出口能看到：`http://localhost:8377`
  （HTML）与 `http://localhost:8377/json`（原文 `latest.json`），这是工单 06
  已完成的产物。
- 把 `gpu-jobs`/`watch`/`json` 三个终端出口接读这份采样历史，是工单 07
  「终端出口改读采样历史」要做的事，我确认它当前状态是 `in_progress`，尚未
  接线（`.scratch/gpu-monitor-launch/issues/07-terminal-outlet.md`）。

按 CLAUDE.md「不许猜数据结果/不许把没验证的东西写成现状」的铁律，把三处文档
改成如实区分「网页已经能看/终端接线中」：

- SKILL.md Phase 4 交监控入口：终端表格描述改回原来准确的
  "进度/实测速率/ETA/tmux 存活状态"，另起一句说明网页 `localhost:8377`
  （及 `/json`）已经在展示六格判定，终端三个出口"接读这份采样历史还在推进"。
- SKILL.md Phase 5：job-monitor 读判定写成"`gpu-jobs json`（终端出口接好之后
  就是这份判定；接好之前先读网页 `localhost:8377/json`）"，并把"写进
  `ops/jobs.json`"改成准确的"写进它自己的状态文件"。
- monitor-methodology.md「程序职责说明」与「Decision tree」两节同步改成
  同样的准确表述。

这不是工单点名要求的内容，是我在核对代码时发现的准确性问题，顺手在同一次
改动里修正，没有另开范围。

## 怎么验证的

这是纯文档改动，不涉及 `run.py` 注册表，未跑 `selfcheck`（改的三个文件都不
在测试覆盖范围内——`grep -rl "gpu-run\|SKILL.md\|monitor-methodology\|
launch-methodology" tests/` 无匹配）。验证手段是逐条读实现代码核对文档陈述：

- `ops/launch_cmd.py`（十步流程、`parse_launch_argv`、`build_pieces`、
  `build_inner`、`verify_alive`、`cmd_refire` 的补射语义）
- `ops/launch_common.py`（`register_all` 三处登记顺序与失败语义）
- `ops/verdicts.py`（六格判定常量、`judge()`/`_judge_service()` 命中条件、
  `DEFAULTS` 各常数值、`stall_line_s`/`typical_gap_s` 的公式）
- `ops/sampler.py`（`MONITOR_DIR` 定位、`maybe_trigger_incidents` 现状为
  `pass`、`should_trigger`/`build_incident_prompt` 已合并、`WebServer` 的
  `/`、`/json` 两个路径、`read_incidents_tail` 的落地路径）
- `ops/gpu_jobs.py`（`collect()`/`fmt_table()`/`cmd_status`/`cmd_watch`/
  `main()` 的 `json` 分支，确认终端出口尚未接采样历史）
- `.scratch/gpu-monitor-launch/issues/07-terminal-outlet.md`（核对该工单的
  实际状态与验收范围）
- `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 16（工单指定的执行步骤
  原文）

命令层面只跑了 `git diff --stat` / `git diff` 通读一遍改动是否自洽，没有可
自动化验证文档正确性的测试。

## commit 清单

- `146a289` — `T15: gpu-run skill 对齐 launch+采样器新流程(Phase4/Phase5 收编,两份方法论改写)`
  改动文件：`.claude/skills/gpu-run/SKILL.md`、
  `.claude/skills/gpu-run/references/launch-methodology.md`、
  `.claude/skills/gpu-run/references/monitor-methodology.md`

## 自查发现与存疑

1. **frontmatter description 与固定路径两行做了工单没点名的顺带更新**：
   `SKILL.md` 顶部 `description:` 字段（原文写"tmux 发射→登记台账→…→定时
   巡检"）和"固定路径"清单里两条引用行（"tmux 模板"、无口径说明的"测速与
   ETA 方法论"）与重写后的 Phase 4/5 及两份方法论内容不一致，我顺手改了这
   两处让全文自洽。工单验收项没有点这两处的名，如果评审认为超出范围可以
   revert 掉这两小段（对应 diff 里 description 那一行 + 固定路径两行）。

2. **`launch-methodology.md` 的 Step 5（Verify）/Step 6（Monitor without
   polling）没有改**：Step 6 里仍留着"ETA claims need ≥60s of tqdm
   observation (see `monitor-methodology.md`)"这句，是旧手工流程的措辞，和
   `monitor-methodology.md` 改写后的内容有点对不上。工单原文只点名"tmux 模板
   一节"和"分片一节"两处要改，Step 5/6 不在列，我按工单字面没动；如果要连带
   扫掉这处残留，需要额外授权（工单没给，我没自行扩大范围）。

3. **`monitor-methodology.md` 的 Gotchas 一节（tail -c/\r 解析、tqdm 过滤、
   process count）没有改**：这段内容本质上还是"手工读日志"的操作细节，工单
   点名的是"两点测速/ETA 修正/tqdm 解析三节"，我把这理解为"Mandatory rules
   + Standard procedure + Reading tqdm output + Sharded-job caveat"四节，
   Gotchas 不在其中，且我在新写的「程序职责说明」里加了一句"手工流程只在
   采样查不到时才退回去用"，把 Gotchas 定位成了那条退路的操作细节，所以留
   着没删。这是我对"三节"范围的裁决，不是工单原文逐字点名，如果理解有偏差
   需要回头再改。

4. **`--kind` 三个取值（train/eval_tool/eval_call）与 `launch_common.py`
   实际写的 `kind="launch"` 不一致**：我读 `ops/launch_common.py`
   `register_all` 时发现它给 RUNMETA 传的固定是 `kind="launch"`，但
   SKILL.md 原文（我这次改写时原样保留了这句提示）说"手搓补记时 `--kind`
   要用 `train`/`eval_tool`/`eval_call` 三个词之一"——这是给"手搓 tmux 发射、
   没走 `launch`"这种旧路径的提示，跟 `launch` 自己写的 `kind="launch"`
   是两条不同路径，我判断不算矛盾就没动；但这确实是个没人点名过的代码/文档
   潜在不一致点，记在这里供后续工单（尤其 18 收官自检）核对。

---

## 修复第 1 轮（2026-08-08）

分支 `ticket/20260808-par/T15` 复用（未新建）；base 不变
（`86f2b8e2fa5846f4060262989974237ad824d108`），本轮 commit 落在原 head
`146a289e` 之后。工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T15-fix1`
（已按协议删除）。

主会话交付的两条 findings：

### F1（critical）——事故 agent 措辞用旧口径

**问题**：`SKILL.md` Phase 5 与 `monitor-methodology.md` Decision tree 里
写的"事故 agent 自动验尸补射：未上线（暂缓）"，是工单 15 Comments 第一条
（旧口径，转记自主会话）的措辞。工单 15 Comments 第二条（同日，明确标注
"覆盖上一条"）说用户随后授权、`spawn_agent`+`maybe_trigger_incidents` 接线
已由主会话实装，要求改写成"已接线、未经真实演练"。

**核实**：上一轮报告写作时这条 comment 2 尚未挂到工单文件上（报告全文未
提及），故上一轮按 comment 1 的口径写是当时信息下的合理产物，不是失误。
本轮先读了工单 15 当前 Comments 确认 comment 2 的原文和"覆盖上一条"标注；
再读工单 12 Comments 最新一条（同日，`git diff` 主仓未提交改动里的
`.scratch/gpu-monitor-launch/issues/12-incidents.md`）拿到实装细节的准确
措辞来源：`spawn_agent`（无头 `claude` 子进程，模型钉 opus，detach 不
wait，输出进 `monitor/incidents/<事故编号>.out`）+ `maybe_trigger_incidents`
（命中写 `incidents.jsonl` → 拉 agent → `incident_open` 置位防重复）+
`sample_once` 里 `state.json` 落盘挪到触发之后（修时序坑），单测新增 4 个，
"手动演练经用户再次裁决取消：全链只有单测背书，没有真实拉过一次 opus"。
同时读了工作树里的 `ops/sampler.py`（分支内仍是 `maybe_trigger_incidents`
的 `pass` 占位——接线代码是主仓未提交改动，没有随 T15 或 T12 分支落地），
确认这处"已接线"是文档口径层面的授权指令，不是当前这条分支上可运行的代码
状态；按工单原文"若你已按旧口径写完，主会话收账时会核对并改正"的指示，
仍照 comment 2 给的措辞改写文档。

**改法**：
- `SKILL.md` Phase 5（原 126-131 行）：标题句改成"事故 agent 自动验尸补射：
  已接线、未经真实演练。"，正文改写成交代清楚接线细节（谁在 2026-08-08
  授权由谁实装、`should_trigger` 命中后先写 `incidents.jsonl` 再 spawn 无头
  `claude` 子进程、`incident_open` 防重复触发的机制），并保留一句限定
  "手动演练经用户裁决取消——全链只有单测背书，没有真实拉过一次 agent，
  第一次真实事故发生时这条链是首跑"，原来"读日志定位死因、能修则 `--refire`
  补射"的收尾句保留。
- `monitor-methodology.md` Decision tree 表格 `V_STALL`/`escalated=true` 行：
  "自动拉事故 agent 补射目前**未上线（暂缓）**"改成"并自动拉起一个无头
  事故 agent 去处理（**已接线、未经真实演练**）"，其余表述不动。

### F2（important）——launch-methodology.md 悬空引用

**问题**：`launch-methodology.md` Step 6 一行"ETA claims need ≥60s of tqdm
observation (see `monitor-methodology.md` in this same directory)."是旧手工
测速流程的措辞，本次改写已经把 `monitor-methodology.md` 的"两点测速/手工
parse tqdm 行"整套流程删掉，改成"读采样器判定"，这条引用指向的内容已经不
存在，读者顺着查会找不到对应操作。

**核实**：上一轮报告自查项 2 已经点出这处不一致，未处理的理由是"工单原文
只点名 tmux 模板一节和分片一节，Step 5/6 不在列，没有额外授权不擅自扩大
范围"。本轮 finding 明确要求按"和本次改写内容明显拧着"处理，属于本次改写
直接产生的新悬空引用，不是独立的范围外重构，予以修复。

**改法**：把这句改成指向 `monitor-methodology.md` 现有的判定出口表述——
"ETA claims come from the sampler's verdict, not hand-parsed tqdm: read
`python3 run.py gpu-jobs json` once the terminal outlet reads sampler
history, or `http://localhost:8377/json` in the meantime (see
`monitor-methodology.md` in this same directory)."，与 `monitor-methodology.md`
「程序职责说明」一节里"读判定优先用 `gpu-jobs json`……接好之前先读网页
`/json`……不要再手翻日志、手算 tqdm 行"的措辞对齐。

### 怎么验证的

纯文档改动（改动文件仍是 `SKILL.md`/`launch-methodology.md`/
`monitor-methodology.md` 这三个已有文件里的既有措辞，未新增文件、未碰
`run.py` 注册表），复核了一遍上一轮的测试覆盖结论仍成立：

```
$ grep -rl "gpu-run\|SKILL.md\|monitor-methodology\|launch-methodology" tests/
（无输出，退出码 1）
```

三个文件都不在测试覆盖范围内，未跑 `selfcheck`（未碰注册表）。验证手段是
读源改动核对措辞：`ops/sampler.py`（`should_trigger`/`build_incident_prompt`/
`maybe_trigger_incidents`/`spawn_agent` 在这条分支上的实际代码状态，确认
仍是 `pass` 占位，接线在主仓未提交改动里）、工单 15 Comments 全文、工单 12
Comments 最新一条全文（措辞原文出处）。另跑 `git diff` 通读改动是否自洽、
是否只动了 finding 点名的三处。

### commit 清单

- `b0cd20d` — `T15: 修复第1轮——事故 agent 口径改为已接线未演练，补 launch-methodology 悬空引用`
  改动文件：`.claude/skills/gpu-run/SKILL.md`、
  `.claude/skills/gpu-run/references/launch-methodology.md`、
  `.claude/skills/gpu-run/references/monitor-methodology.md`

head: `b0cd20d`

### 自查发现与存疑

- 未新增遗留问题。原报告自查项 1（description/固定路径两行的顺带更新）、
  项 3（Gotchas 一节未改）、项 4（`--kind` 三个取值与 `kind="launch"` 的
  潜在不一致）本轮未涉及，维持原状，供后续工单核对。
- "已接线、未经真实演练"这句口径本身依赖工单 12 Comments 最新一条描述的
  代码状态；那份代码目前在主仓工作树是未提交改动（`ops/sampler.py`/
  `tests/test_incidents.py` 等 modified 未 commit），一旦后续以不同方式落地
  或口径再变，这两处文档措辞需要跟着复核，不是本轮能锁死的终态。
