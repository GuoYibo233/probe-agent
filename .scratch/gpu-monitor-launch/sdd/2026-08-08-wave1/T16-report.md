# T16 报告 — 文档回写：两个 agent 定义

工单：`.scratch/gpu-monitor-launch/issues/16-docs-agents.md`
分支：`ticket/20260808-par/T16`（工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T16`，收尾时按协议删除）
base: `0d2c1ac9c5ee4ff5c4fda4d04e93fa1c8d6e53a9`
head: `9ba56ae8e64724e441f2e8dcce3da6c3c80e15cc`

需求细节来源：工单未直接引用 spec.md 的节，正文点名"步骤照实施计划 Task 17
执行"，读了 `docs/plans/2026-08-08-gpu-monitor-launch.md` 第 1022-1034 行
（Task 17: 文档回写 — 两个 agent 定义）。另外工单 Comments 两条（主会话
转记）覆盖了事故 agent 状态的措辞口径，第二条明确"覆盖上一条"，按第二条
执行。

## 做了什么（对照工单逐条）

工单验收项三条：

- [x] **job-monitor 定义里不再有两点测速的操作步骤**
  `.claude/agents/job-monitor.md` 正文重写：
  - 删掉了"速率要两个时间点"（先扫一遍全部任务、回头重新 tail、算
    Δitems/Δt、与 tqdm 自报 s/it 交叉核对）的整套手工流程，删掉检查清单
    里"两次快照 current 在涨"、"实测 ETA：真实剩余量 × 实测 s/it（sharded
    任务按 SKILL 的修正公式）"这些操作细节。
  - 改成一句话定调："判定、速率、ETA 现在由采样器算好——你读现成结论，
    不再自己测速、手算 ETA、解析 tqdm 行"，取数方式收成唯一一条
    `python3 run.py gpu-jobs json`，直接抄 `verdict`/进度/速率/ETA/session
    存活到健康表；json 查不到才退回手动读日志。
  - 只读铁律保留（新增"不补射"一项，呼应下面的分工段）；验尸流程保留
    （`已挂`或升级中的`疑似卡死`才验尸：session 存活 / 日志尾部 traceback /
    GPU util）；报告格式的表格结构原样保留，加一句"判定列直接抄
    `gpu-jobs json` 的 `verdict`"。
  - 新增"与事故 agent 的分工"一节：job-monitor 是人派的检查员（用户或主
    对话问起才派），事故 agent 是采样器自动拉的处置员（升级线一过——
    `V_STALL` 且 `escalated=true`，或 `V_DEAD`——自动记事故并拉无头
    `claude` 子进程去处理）；明确写"你不许替它执行补射（`launch
    --refire`）"，看到已挂/升级中的疑似卡死照旧只读日志定位死因，把建议
    动作写进报告交主对话或事故 agent 决定。

- [x] **gpu-runner 定义里发射只有 launch 一条路（排卡发射器照旧）**
  `.claude/agents/gpu-runner.md` 本地约束原第 3 条（发射命令从 run.py 拿）
  与第 4 条（双登记）合并改写为一条："发射一律 `python3 run.py launch`，
  工作树必须干净"：贴出 `launch <task> ... --run-id --track --piece ...`
  完整用法，讲清楚它一条命令走完验卡（fail-closed）→ tmux → 30 秒验活 →
  三处登记一口气 → 打印监控入口；`shardable` 任务多 `--piece` 自动注入
  分片参数；脏树硬门禁 + 台账白名单豁免的措辞照抄原文保留。原第 4 条
  （手打 `gpu-jobs register`/`record start`/`runmeta` 三条命令）整段删除。
  保留两个例外：
  - 例外一（排卡发射器）：`launch-probe`/`launch-eval` 照旧直接跑，不走
    `launch` 子命令，它们内部自动做 FREE 实探 + 三处登记（工单 11 的
    产物）。
  - 例外二（补射不是新任务）：新增 `launch --refire <run_id> --idx <N>`
    的说明——session 还活着拒绝、目标卡实探非 FREE 拒绝、成功后只更新
    该分片位四元组，不新开 record、不重复登记。
  报告格式的"登记回执"节从"gpu-jobs register/record start/runmeta 三条
  命令+各自输出"改成"贴 `launch` 的完整输出（回执 + 监控入口两行）；走
  排卡发射器时贴它自己打印的登记行；补射时贴补射输出"。其余条目（别名
  去重、禁止手搓、先 smoke、不问自己决定、项目隔离、日志归位、职责边界）
  未改动，仅顺延重新编号（3→3合并后，4-9 顺延为 4-8）。

- [x] **commit**：`9ba56ae`，见下方 commit 清单。

## 与工单 Comments 的对照（事故 agent 措辞口径）

工单 Comments 第二条（覆盖第一条）要求："分工段照工单原文写，注明'已
接线、未经真实演练'，不写'未上线'"。job-monitor.md 的分工段按此措辞写
（"已接线、未经真实演练，细节见 monitor-methodology.md 的 decision tree
一节"）。

核实：读了本分支 `ops/sampler.py`（`maybe_trigger_incidents` 第 170-172
行），当前仍是 `pass` 占位，注释写"事故触发在 Task 14(工单 12)实装,这里
先占位"——即工单 12（事故触发）实装代码尚未落到这条分支的提交历史里
（工单 12 在任务列表里状态是 in_progress，主仓工作树当时有
`ops/sampler.py`/`tests/test_incidents.py` 的未提交改动）。"已接线、未经
真实演练"是工单 Comments 明确指定的文档措辞（覆盖前一条口径，且是主会话
转记的用户裁决），T15 报告处理同一措辞时也确认过这一点并按 Comments 原文
写——两处文档口径与代码提交状态的关系一致，不是本单引入的新不一致。

## 怎么验证的

纯文档改动，只碰 `.claude/agents/job-monitor.md` 和
`.claude/agents/gpu-runner.md` 两个文件，不涉及 `run.py` 注册表：

```
$ grep -rl "job-monitor\|gpu-runner" tests/
（无输出，退出码 1）
```

两个文件都不在测试覆盖范围内，未跑单测。仍跑了一遍 `python3 run.py
selfcheck` 做低成本体检（工单未要求，但代价低）：

```
$ python3 run.py selfcheck
...
selfcheck: 63 任务 / 4 配方, 16 处缺失
```

16 处缺失全是 worktree 里没有的第三方 venv/脚本路径（`envs/appworld/venv`
等），与本次改动的两个 agent 文档文件无关——worktree 是从 git 对象重建的
工作树，未随带 `.gitignore` 掉的 venv 目录，这是 worktree 环境本身的已知
限制，不是本次改动引入的问题。

命令层面另跑了 `git diff --stat` / `git diff` 通读改动是否自洽，逐条对照
`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 17 的 Step 1/Step 2 原文
核对措辞是否落实。

## commit 清单

- `9ba56ae` — `T16: job-monitor 瘦身读现成判定;gpu-runner 发射段改 launch`
  改动文件：`.claude/agents/job-monitor.md`、`.claude/agents/gpu-runner.md`

## 自查发现与存疑

1. **`gpu-runner.md` frontmatter 的 `description` 未改**：其中"实测速率多少、
   真实 ETA"等措辞描述的是用户可以问 job-monitor 什么，不是 gpu-runner 自身
   行为，工单 Comments 没有点名 frontmatter，Task 17 的 Step 1/2 也只提正文
   两处（发射段合并、报告格式登记回执），未动 frontmatter，判断不需要改。
2. **`monitor-methodology.md` 的六格判定表与 decision tree 已经是 T15 改过的
   版本**：本单直接引用它（"六格判定的含义和 decision tree 写在……里"）而
   不是重复贴一遍表格，是否需要在 job-monitor.md 里内联复述判定表工单未
   点名，我判断"引用同一份单一真源"比复述两份更不容易走样，按引用处理。
3. **报告格式表格里"实测速率"改成了"速率"**：原表头是"实测速率"、"真实
   ETA"，强调"实测"二字对应旧的手工测速流程；既然改成直接抄 json 字段，
   "实测"这个修饰词不再准确（是采样器算的，不是 job-monitor 自己实测的），
   我把表头改成"速率"、"ETA"。工单没有逐字规定表头文案，这是我对"两点测速
   操作细节全删"这条要求的延伸判断，如果评审认为应该保留"实测"二字可以
   revert 这两个字。

未发现需要 `BLOCKED`/`NEEDS_CONTEXT` 的缺口——两条验收项、Comments 口径、
Task 17 的 Step 1/2 均已对照落实，工作树已清干净可以 commit。
