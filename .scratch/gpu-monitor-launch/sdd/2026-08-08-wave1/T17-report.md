# T17 — 文档回写：probe-pipeline 与根文档

## 做了什么

工单 17 的 What-to-build 指明步骤照实施计划 `docs/plans/2026-08-08-gpu-monitor-launch.md`
Task 18 执行，该 Task 的 Files 清单与 Step 1 是本轮工作的具体指令来源。逐条对照：

1. **三句关键新表述逐字落进对应文件**（工单验收要求第一条）：
   - `python3 run.py gpu-jobs register` 与 `python3 run.py record start` 同时做完" →
     **"launch 自动写三处；手搓/register 补录路径仍在，漏了照旧算违规"**——
     落在 `SKILL.md:134`（G16，Phase C3）和 `references/gates.md` 的 G16 行。
   - invariants.md 的记账双写行 → **"双写由 launch 保证；绕过 launch 手搓发射的，
     双登记责任回到人"**——落在 `references/invariants.md` §5 记账双写行。
   - extending.md 新脚本清单加硬项 → **"新采集/训练/评测脚本必须接
     `ops/heartbeat.py`（进主循环 emit(0,...)，每单位 emit，收尾 status=done），
     不接的脚本在窗口里永远是 warm-up 中"**——落在 `references/extending.md` §3.2
     "能照抄什么、不能照抄什么" 表，新增一行"心跳 emit"，与该表原有的
     `train_log.jsonl` 的 `log()` 闭包行（第 130 行，与实施计划 Task 18 给出的
     行号定位一致）紧邻。该行同时如实标注哪些脚本已接（四个训练脚本、三个
     eval 脚本、`run_appworld.py`，逐一 grep `import heartbeat` 验证）、哪些
     还没接（`run_tales.py`/`run_alfworld.py`/`run_tau2.py`），不写成"全部脚本
     已接"。

2. **MAP.md 新旧程序行齐全**（工单验收要求第二条）：
   - `ops/gpu_jobs.py` 行更新：补充 register 现多数经 `run.py launch`
     （`launch_common.register_all`）自动调用，手打这条命令是漏登记的补录路径；
     补充 `status`/`watch` 都走 `collect(with_extras=True)`，末尾会列台账外
     tmux session（源码验证：`ops/gpu_jobs.py` 的 `cmd_status`/`cmd_watch` 都
     调用 `collect(with_extras=True)`）。
   - 新增三行：`ops/heartbeat.py`（心跳 emit/parse 原语）、`ops/verdicts.py`
     （六格判定纯函数引擎）、`ops/launch_cmd.py`（`run.py launch` 子命令本体，
     十步流程 + `--refire` 补射）——三者此前在 MAP.md 里完全没有独立行（仅在
     `sampler.py` 行的描述文字里被提及）。
   - `ops/launch_probe.py` / `ops/launch_eval.py` / `ops/launch_common.py` /
     `ops/sampler.py` 四行核对后确认**已在 T09/T11/T14 各自的收尾 commit
     里同步更新过**（含 `register_all` 接入、track 命名、事故触发纯函数落地
     等最新状态），本轮未再改动，避免无意义重写。

3. **连带对齐**（What-to-build 段"probe-pipeline 及其 references…handoff
   skill、CLAUDE.md、MAP.md、gpu_state 页首全部对齐新流程"这句要求的范围，
   对照实施计划 Task 18 的 Files 清单逐项落实）：
   - `gates.md` G2 行：补充 `launch`/`launch-probe`/`launch-eval` 内部对每个
     piece 也会自动重探一遍，手动 `free` 不是唯一防线。
   - `gates.md` G17 行：补充"这一步 launch 没有收编，G16 的自动化只管发射时
     的登记，销号仍要手动跑这四连"——避免读者把 G16 的自动化误推广到 G17。
   - `SKILL.md` agent 分工表（原 :221-222 附近）：`gpu-runner` 一行"探卡→
     smoke→tmux→登记→验活一条龙"改写为"探卡→smoke→`launch`（自动三处登记+
     验活）一条龙"，与十步流程对齐。
   - `stage-commands.md` :19 附近：补一段说明标 `[发射]` 的任务现在走
     `python3 run.py launch <task> ...` 一条命令，不用再手动"`show` 出命令→
     复制进 tmux→手打三条登记"。
   - `stage-commands.md` :352（S11 后的并行/串行说明段）：整句改写，用
     "launch 自动写三处；手搓/register 补录路径仍在，漏了照旧算违规"的口径
     替换旧的"发射后双登记 ... + ..."描述。
   - `.claude/skills/handoff/SKILL.md`：Phase 1 第 1 步的取证命令
     `python3 ops/gpu_jobs.py json`（裸调 `ops/` 脚本，违反"统一从 run.py 进"）
     改为 `python3 run.py gpu-jobs json`，并如实补充：判定/速率/ETA 目前只
     在网页出口 `http://localhost:8377/json` 齐全，终端 `gpu-jobs json` 接读
     采样历史仍是工单 07（in_progress），接上之前进度靠 tail 日志人工读——
     不写成三个出口都已就绪。交接书六节定式的"在跑的任务"行补充进度来源
     指向 `run.py gpu-jobs json` + 采样历史网页 json。
   - `CLAUDE.md` gpu-run 段：加一句"发射与登记收成 `python3 run.py launch`
     一条命令（探卡/tmux/验活/三处登记一口气做完）"；"用户自助监控"一行
     补上网页 `http://localhost:8377`（未新增重复行，直接并进原有的
     "用户自助监控"那一行，避免与新加的句子内容重复）。
   - `ops/gpu_state.md` 页首：补一行"登录机常驻采样器算判定：
     `python3 run.py sampler --interval 60 --port 8377`；网页
     `http://localhost:8377`（ssh 端口转发）、`/json` 出机器可读判定"。

## 怎么验证的

本工单是纯文档改动，没有可执行的测试接缝；核对方式是逐条重读改动后的原文，
并用命令行核对没有破坏 Markdown 表格结构、没有引入与其它工单当前真实进度
（如工单 07 in_progress）矛盾的措辞。

1. **Markdown 表格列数核对**（改动的每张表，改前改后列数必须一致）：
   ```bash
   awk -F'|' 'NR==8{print NF}' .claude/skills/probe-pipeline/references/gates.md
   grep -n "^| G2 \|^| G16 \|^| G17 " .claude/skills/probe-pipeline/references/gates.md | awk -F'|' '{print NR": fields="NF}'
   ```
   输出：表头 7 列，G2/G16/G17 三行改动后同为 7 列——列数未破坏。

   ```bash
   awk -F'|' 'NR==131{print NF}' .claude/skills/probe-pipeline/references/extending.md
   ```
   输出：`5`——新增的心跳 emit 行与 §3.2 表其余行（3 列内容 + 首尾空 = 5）列数一致。

2. **心跳接入面核对**（确保 extending.md 新行"哪些脚本已接/未接"的表述有据）：
   ```bash
   grep -rln "import.*heartbeat\|from.*heartbeat" pipeline/ envs/collect/*.py
   ```
   输出：`pipeline/eval/eval_mbert_call.py`、`pipeline/eval/eval_causal_call.py`、
   `pipeline/eval/eval_tool.py`、`pipeline/train/train_causal_callgen.py`、
   `pipeline/train/train_mbert_extract.py`、`pipeline/train/train_causal_tool.py`、
   `pipeline/train/train_mbert_tool.py`、`envs/collect/run_appworld.py` 共 8 个
   文件——与新增行里写的"四个训练脚本 + 三个 eval 脚本 + `run_appworld.py`
   已接"完全对上；另用
   `grep -l "import heartbeat" envs/collect/*.py` 确认 `run_tales.py`/
   `run_alfworld.py`/`run_tau2.py` 不在命中列表，对应工单 03 的范围本就只
   限 appworld，如实标注未接。

3. **gpu_jobs.py 新增描述的源码核对**：
   ```bash
   grep -n "def cmd_status\|def cmd_watch\|with_extras" ops/gpu_jobs.py
   ```
   确认 `cmd_status()`/`cmd_watch()` 均以 `collect(with_extras=True)` 取数，
   `collect(with_extras=True)` 会额外收台账外 session——MAP.md 新描述属实。

4. **`python3 run.py selfcheck`**（工单未涉及 run.py 注册表改动，但仍按实现者
   规程"改了 run.py 注册表相关的东西"这条的边界谨慎跑了一遍）：
   ```
   selfcheck: 63 任务 / 4 配方, 16 处缺失
   ```
   16 处缺失全部是"缺解释器/程序"（如 `envs/appworld/venv/bin/python`、
   `mbert-env/bin/python` 等），是本工作树本来就没有建各环境 venv 的既有
   环境问题，与本工单的纯文档改动无关——本工单没有改 `run.py` 的 TASKS/
   RECIPES/CELLS/EVAL_CELLS，不触发这条边界规则，此处只是确认没有因为
   文档改动引入新的注册表错误。

## commit 清单

- `e7f31b6` — `T17: docs: probe-pipeline/handoff/CLAUDE/MAP/gpu_state 对齐 launch+采样器`
  （分支 `ticket/20260808-par/T17`，base `f8c9965`）。单一 commit，改动 9 个文件、
  27 行新增 / 11 行删除：
  `.claude/skills/handoff/SKILL.md`、`.claude/skills/probe-pipeline/SKILL.md`、
  `.claude/skills/probe-pipeline/references/{extending,gates,invariants,stage-commands}.md`、
  `CLAUDE.md`、`MAP.md`、`ops/gpu_state.md`。

## 自查发现与存疑

- **实施计划 Task 18 给出的行号（如 extending.md:130、SKILL.md:74-75/172-173/
  221-222）是同一天写的快照，多数与本工单执行时的实际行号吻合**（extending.md
  :130 精确命中 `train_log.jsonl` 的 `log()` 闭包行，紧邻处插入心跳行）。
  但 SKILL.md 的 :74-75（Phase A 收尾链：G6/G7/finish/commit）与 :172-173
  （Phase D 释放/销号两步）两处，我重读后判断**内容本身procedurally 仍然
  准确**（Phase D 那两步早就带着 fail-closed / `--force` 的说明，是历史某次
  改动已经写好的，不是本工单该补的空白）——没有找到需要因为"launch 收编
  登记"这件事而改写的具体文字，所以这两处本轮**没有改动**，只动了同一
  Phase 里离它们更近、确实过时的 G16 段落（Phase C3）和 agent 分工表
  （原 :221-222 附近）。如果主会话认为这两处也必须留痕改一笔（哪怕只是
  措辞对齐），我可以补一轮，但目前没找到"内容错误"或"内容过期"的具体点，
  怕硬凑文字变成无意义 diff，所以先按"内容已准确、不用动"处理，写在这里
  留痕。
- **CLAUDE.md 的"加一句"没有逐字复制工单原句**（工单写的例句是"发射与登记
  收成 `run.py launch`，用户自助监控 = `gpu-jobs watch` + 网页 8377"）。
  我把这句话拆成了两处：一句独立新增（"发射与登记收成 launch 一条命令"），
  另一句并入了原本就存在的"用户自助监控"那一行（避免在同一段落里对同一
  个 `gpu-jobs watch` 命令写两遍）。语义与工单描述完全一致，只是没有逐字
  堆成一句——这条不在"三句关键新表述"之列（那三句是 G16/记账双写/心跳
  清单，已逐字落地），这里判断为工单例句只是给方向、允许我按上下文自然分句，
  如有出入请指出，我可以改回逐字一句话。
- **未触碰的相关文件**：`.claude/skills/probe-pipeline/references/gates.md`
  的 G3–G15、G18–G22 与 `invariants.md` 其余口径行本轮未动，因为它们与
  launch/心跳这两条改动无关，属于工单范围外——按 YAGNI 原则没有顺手改。
- **工单 16（两个 agent 定义回写）与工单 18（收官自检）本轮均未触碰**，
  它们在任务台账里分别是 pending 状态，不在本工单范围内。

## 修复轮 1（2026-08-09）

分支 `ticket/20260808-par/T17`，工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T17-fix1`，
base `e7f31b6`（上一轮实现者的收尾 commit）。

### F1（critical）：gates.md G2 把 launch-probe/launch-eval 的非 FREE 处理错写成"整次拒绝"

**问题**：上一轮在 G2 行新增的句子把 `run.py launch`、`launch-probe`、`launch-eval`
三个发射器的非 FREE 处理写成同一种行为——"任何一张非 FREE 整次拒绝"。核对源码：

- `ops/launch_cmd.py:271-272`（`run.py launch`，单任务/多分片模式）：逐 piece
  `probe_free`，只要有一张非 FREE 就 `raise SystemExit`，**真的是整批一张都不发**——
  这句对 `launch` 是对的。
- `ops/launch_probe.py:46-56` 与 `ops/launch_eval.py:62-72`（`launch_and_register`
  函数）：单格 `probe_free` 探到非 FREE 时只 `print(f"SKIP (非 FREE): ...")` 后
  `return False`，循环继续发下一格，不 `raise`、不中止整批调用——是"跳过该格"，
  不是"整次拒绝"。
- 与 MAP.md 本来就有的描述（T17 本轮未改动这两行，同一版本内可交叉核对）互相印证：
  `ops/launch_probe.py` 行写"非 FREE 打印原因跳过该格（排卡表半空常见，**不整表
  拒绝**）"，`ops/launch_eval.py` 行写"非 FREE 跳过该格"——与旧 G2 行的新句子直接
  矛盾。

**怎么修的**：把 G2 行拆成两句，分别描述两种发射器的实际行为：

```diff
-`python3 run.py launch`/`launch-probe`/`launch-eval` 内部对每个 piece 也会自动
-重探一遍，任何一张非 FREE 整次拒绝——手动 `free` 是给人挑卡用，不是唯一防线
+`python3 run.py launch` 内部对每个 piece 也会自动重探一遍，任何一张非 FREE 整次
+拒绝（fail-closed，一张都不发射）；`launch-probe`/`launch-eval`（排卡批量）逐格
+重探，非 FREE 只打印原因跳过该格、继续发下一格，不是整批拒绝——手动 `free` 是
+给人挑卡用，不是唯一防线
```

改动只落在 `.claude/skills/probe-pipeline/references/gates.md` 的 G2 一行，未动
G16/G17（那两行讲的是登记行为，三个发射器登记逻辑一致，没有类似问题）。

**测试**：本工单全程无可执行测试接缝，验证方式沿用上一轮报告用过的表格列数核对，
并额外做一次全仓搜索确认没有第二处同款错误表述。

```
$ awk -F'|' 'NR==8{print "header:",NF}' .claude/skills/probe-pipeline/references/gates.md
header: 7
$ grep -n "^| G2 \|^| G16 \|^| G17 " .claude/skills/probe-pipeline/references/gates.md | awk -F'|' '{print NR": fields="NF}'
1: fields=7
2: fields=7
3: fields=7
```

表头 7 列，改动后的 G2/G16/G17 三行同为 7 列——表格结构未破坏。

```
$ grep -rn "launch.*launch-probe.*launch-eval.*整次拒绝\|launch-probe.*launch-eval.*整次拒绝" \
    .claude/skills/probe-pipeline/ CLAUDE.md MAP.md ops/gpu_state.md
exit=1（无匹配）
```

确认改动前那种"三个发射器一律整次拒绝"的错误表述在别处（stage-commands.md、
invariants.md、SKILL.md、CLAUDE.md、MAP.md、gpu_state.md）没有第二份拷贝——
这些文件里出现"整次拒绝"/"fail-closed"字样的地方（`ops/launch_cmd.py` 本体的
十步流程描述、`gpu-jobs finish` 的 fail-closed 销号）说的是别的对象，不涉及
`launch-probe`/`launch-eval` 的探卡行为，不需要跟着改。

### commit 清单（本轮）

- `80b6cbf` — `T17: fix: gates.md G2 拆分 launch 与 launch-probe/launch-eval 的非 FREE 处理`
  （分支 `ticket/20260808-par/T17`）。单文件、1 行改动：
  `.claude/skills/probe-pipeline/references/gates.md`。

### 自查发现与存疑（本轮）

- 只动了 G2 一行，没有扩大范围重写周边表述——finding 只点名这一行，其余
  gates.md/invariants.md/stage-commands.md 里提到 launch/launch-probe/launch-eval
  的地方逐一读过，没发现第二处把三者行为混同的表述。
- 未发起新的 GPU 进程，未触碰 `run.py` 注册表，未跑 `selfcheck`（本轮改动与
  TASKS/RECIPES/CELLS/EVAL_CELLS 无关，不触发该边界规则）。
