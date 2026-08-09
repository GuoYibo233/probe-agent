# T11 — 两个排卡发射器接登记（11-board-launchers）报告

工单：`.scratch/gpu-monitor-launch/issues/11-board-launchers.md`
需求细节来源：工单指向实施计划 `docs/plans/2026-08-08-gpu-monitor-launch.md`
的 Task 13（第 896-916 行）。
工作树：`/home/y-guo/reproduce/new1-wt/20260808-par-T11`，
分支 `ticket/20260808-par/T11`。

## 做了什么

对照工单四条要求逐条实现：

1. **本地 tmux 辅助函数删掉换成 import**：`ops/launch_probe.py`（原
   `:47-62`）和 `ops/launch_eval.py`（原 `:62-77`）里各自的 `has_session`/
   `launch` 本地函数、以及为它们服务的模块级 `LOCAL`/`ALIAS` 计算全部删掉，
   换成 `from launch_common import has_session, tmux_launch, probe_free,
   register_all`。两个文件原来 `launch()` 的调用点（在 `main()` 的发射循环
   里）改成一个新的 `launch_and_register(...)` 函数，内部拼 inner 命令后
   调 `tmux_launch`——inner 模板与原来完全一致
   （`cd <wd> && CUDA_VISIBLE_DEVICES=<g> <cmd> 2>&1 | tee <log>`），
   `has_session` 存在性检查的 `SKIP (exists)` 行为原样保留。

2. **每格发射前 FREE 实探**：`launch_and_register` 在 `has_session`
   通过之后、真正 `tmux_launch` 之前调 `probe_free(host, str(gpu))`；
   非 FREE 只打印原因并 `return False` 跳过这一格（`SKIP (非 FREE):
   <sess>  <host> gpu<g>  <why>`），不整表拒绝——排卡表半空常见，与
   `run.py launch` 单任务"整次拒绝"口径不同，函数 docstring 里写明了
   这条差异。

3. **每格发射后自动补台账和 record**：`launch_and_register` 在
   `tmux_launch` 成功、`append_runmeta` 照旧写完之后，拼一个 rich piece
   （`host/gpus/session/log/cmd/launched_at/kind/stall_line/escalate_line`
   九个字段，`stall_line`/`escalate_line` 都传 `None`——两个排卡发射器不
   支持按格覆盖判定线，工单原文也没要求）调
   `register_all(rid, str(WD), [piece], track, cmd_display, outdir=None)`。
   `outdir=None` 是因为 RUNMETA 那一步已经在 `append_runmeta` 里单独写过
   了，工单原文明确写"RUNMETA 一步传 `outdir=None` 跳过，别写两遍"。
   `track` 两个文件不同：`launch_probe` 用 `f"probe_{batch}"`，
   `launch_eval` 用 `f"eval_{batch}"`。`launch_eval` 的 `rid` 按工单原文
   "用 sess 去掉前缀 `eval_` 的 `{batch}_{model}_{cell}`" 取
   `sess[len("eval_"):]`。`register_all` 抛出 `SystemExit`（比如撞了重复
   `run_id`，或者 `record.py start` 内部拒绝）只打 `WARN 登记失败(<rid>):
   <e>` 不重新抛出——tmux 那格已经真的发出去了，登记失败不能把已发射的
   任务藏起来不让 alive check 看见，工单原文明确写了这条"打 WARN 继续，
   不中断发射循环"。

4. **各自守卫一个不动**：`launch_probe.py` 的排卡表解析（`build()`）和
   smoke 模式（`--model`/`--host`/`--gpus` 四格 zip）逻辑一字未动；
   `launch_eval.py` 的依赖顺序硬检查（call 档发射前查 `dep_run/
   REPLAY_REPORT.json`）和训练产物存在检查（`run/best` 目录）逻辑一字未动
   ——`git diff` 里 `build()` 函数完全没有出现在改动范围内。

`kind` 字段：`launch_probe` 传 `"train"`，`launch_eval` 传
`f"eval_{stage}"`（`eval_tool`/`eval_call`）——与两个文件原本
`append_runmeta(..., kind=...)` 用的值一致，`verdicts.judge()` 只对
`kind=="service"` 特判，其余值走批处理判定路径，两个值都不是
`"service"`，不影响判定。

同一 commit 更新了 `MAP.md` 里 `ops/launch_probe.py`/`ops/launch_eval.py`
两行，写明已接 `launch_common` 和自动登记行为。没有改 `run.py` 注册表——
两个文件的 CLI 签名、`launch-probe`/`launch-eval` 任务条目、dry-run 输出
格式全部没变，`run.py` 里对这两个任务的描述仍然准确。

## 怎么验证的

新增 `tests/test_launch_probe.py`（4 个用例）、`tests/test_launch_eval.py`
（4 个用例），覆盖新的 `launch_and_register` 边界四条路径：session 已存在
跳过、目标卡非 FREE 跳过、正常发射并登记 rich piece 全字段、登记抛
`SystemExit` 时只 WARN 不中断（且发射结果仍算成功，返回 `True`）。

```
python3 -m unittest tests.test_launch_probe tests.test_launch_eval -v
```

输出（尾部）：

```
test_launches_and_registers_rich_piece (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_register_failure_warns_but_launch_still_reported (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_skips_when_gpu_not_free (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_skips_when_session_exists (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_launches_and_registers_rich_piece_rid_strips_eval_prefix (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_register_failure_warns_but_launch_still_reported (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_skips_when_gpu_not_free (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_skips_when_session_exists (tests.test_launch_eval.TestLaunchAndRegister) ... ok

Ran 8 tests in 0.007s

OK
```

全量：

```
python3 -m unittest discover -s tests -v
```

37 个测试全绿（含 T01/T02/T03/T08 之前写的 `test_heartbeat.py`/
`test_verdicts.py`/`test_launch_common.py`，此工作树里还没有其它并行工单
的测试文件）。`ops/jobs.json`/`RESULTS.md` 没被动过（`git status
--porcelain` 只有我改的 5 个文件）。

工单验收项"两个发射器 dry-run 照常打印"：`pipeline/data/` 在这个工作树
里不存在（不是回归——`pipeline/data/` 本来就不进 git，是 NFS 大产物；
主仓 `/home/y-guo/reproduce/new1` 下也没有现成的 `pipeline/data/`，检查
过了确实找不到任何一批已采集的数据可以直接拿来跑，不是工作树隔离导致的
缺失），用 `/tmp` 下建的假数据目录（`mkdir -p /tmp/.../q35`）+ 假训练产物
目录（`mkdir -p pipeline/runs/zz_q35_mtool/best`，跑完立即删掉）走通了
两条 dry-run 命令，确认 CLI 解析、`build()`、dry-run 打印路径在删掉本地
`has_session`/`launch` 换成 import 之后没有被破坏：

```
python3 run.py launch-probe smoke --batch zz --data-root /tmp/t11_smoke_data \
    --env appworld --model q35 --dry-run --allow-dirty
```
```
[launch-probe] cwd=.../new1-wt/20260808-par-T11
  python3 .../ops/launch_probe.py smoke --batch zz --data-root /tmp/t11_smoke_data --env appworld --model q35 --dry-run
[dry-run] tokyo107 gpu0 new1_zz_q35_mtool_smoke_t107g0
    .../mbert-env/bin/python .../pipeline/train/train_mbert_tool.py --data /tmp/t11_smoke_data/q35 --out .../pipeline/runs/smoke/zz_q35_mtool_smoke --env appworld --smoke
（另外三格类似）
共 4 格(dry-run,未发射)
```

```
python3 run.py launch-eval tool --batch zz --data-root /tmp/t11_smoke_eval_data \
    --env appworld --placement /tmp/t11_eval_placement.json --dry-run --allow-dirty
```
```
[launch-eval] cwd=.../new1-wt/20260808-par-T11
  python3 .../ops/launch_eval.py tool --batch zz --data-root /tmp/t11_smoke_eval_data --env appworld --placement /tmp/t11_eval_placement.json --dry-run
[dry-run] tokyo106 gpu0 eval_zz_q35_mtool
    .../mbert-env/bin/python .../pipeline/eval/eval_tool.py --env appworld --run .../pipeline/runs/zz_q35_mtool --data /tmp/t11_smoke_eval_data/q35 --head mbert
共 1 格(dry-run,未发射)
```

两条命令都在 dry-run 分支直接 `return`，不碰 `probe_free`/`tmux_launch`/
`register_all`，与工单"dry-run 照常打印"的要求一致（dry-run 逻辑本身
这次改动完全没碰）。

`run.py selfcheck` 在这个工作树里跑出 `16 处缺失`，全部是
`envs/*/venv`、`mbert-env`、`cprobe-env` 之类的解释器路径缺失——
在主仓 `/home/y-guo/reproduce/new1`（同一个 HEAD 之前，没有我的改动）
跑同一条命令是 `63 任务 / 4 配方, 全部就位`，对比确认这 16 处缺失是
`git worktree add` 不带走未跟踪文件（venv 目录整个不进 git）导致的
工作树隔离限制，与本工单的代码改动无关；`launch-probe`/`launch-eval`
两个任务本身不在缺失清单里。

## commit 清单

- `1d1d84b` — `T11: 排卡发射器接 launch_common(FREE 实探+自动台账/record,RUNMETA 照旧)`
  （`ops/launch_probe.py`、`ops/launch_eval.py`、`MAP.md` 改动，
  `tests/test_launch_probe.py`、`tests/test_launch_eval.py` 新建）

## 自查发现与存疑

1. **`register_all` 的 `workdir` 参数传了 `str(WD)`（仓库根）**：工单
   原文没有点名这个参数该传什么。两个发射器的 inner 命令都是
   `cd {WD} && ...`，进程真实 cwd 就是仓库根，我判断传 `str(WD)` 是
   忠实反映实情的选择；对照台账历史记录（`ops/jobs.json` 的
   `history` 里 `hcap` 那条 job 的 `workdir` 是它自己产物目录，不是
   仓库根）来看，"workdir" 字段在不同发射路径下语义不完全统一
   （有的填产物目录、有的填进程 cwd），这个工单没有要求统一，我没有
   动这个既有的不一致，只是给这两个新接入的发射路径选了"进程真实
   cwd"这个解释,判断是能安全裁决的点，不影响任何测试断言或验收项。

2. **`stall_line`/`escalate_line` 固定传 `None`**：工单原文和实施计划
   Task 13 都没提到这两个排卡发射器要支持按格覆盖判定线/升级线（这是
   `run.py launch`——工单 09——的能力,签名里有 `--stall-line`/
   `--escalate-line`）。我直接固定传 `None`，让采样器退到
   `verdicts.DEFAULTS` 的自适应判定线。如果后续要给这两个发射器也加
   覆盖能力，需要额外开工单，不在这张范围内。

3. 为改动边界补的两个测试文件里，`test_launches_and_registers_rich_piece`
   （launch_probe）用字符串精确匹配断言了 `tmux_launch` 收到的 inner
   命令文本，绑定了 `f"cd {WD} && CUDA_VISIBLE_DEVICES={gpu} {cmd}
   2>&1 | tee {log}"` 这个具体格式；如果以后这个模板改了这条测试会跟着
   炸，这是有意为之（模板是"inner 模板一致，行为不变"这条验收要求的
   直接体现，值得钉死）。

没有发现需要改的风格不一致问题；`launch_and_register` 的 docstring
风格、`WARN` 前缀打印方式都照抄了 `launch_common.register_all` 和两个
文件原有的 `append_runmeta` 失败处理写法。两个文件里 `shlex` 仍在
`build()`/`cell_cmd_parts()` 里用，`subprocess` 已经不再需要（探卡/
tmux 全部转给 `launch_common`），删掉了 `import subprocess`。

---

## 修复第 1 轮（F1）

工作树：`/home/y-guo/reproduce/new1-wt/20260808-par-T11-fix1`，
同一分支 `ticket/20260808-par/T11`（检出已有分支，不新建）。

### F1（critical）：launch-eval 的 run_id 与 launch-probe 完全同名，标准流程下 register_all 必撞

**评审指出的问题**：`ops/launch_eval.py:86` 原来 `rid = sess[len("eval_"):]`，
`sess = f"eval_{batch}_{model}_{cell}"`，去掉 `eval_` 前缀后等于
`f"{batch}_{model}_{cell}"`——与 `ops/launch_probe.py` 的 `build()` 给同一格
训练 job 用的 `rid`（`f"{batch}_{model}_{cell}"`）逐字符相同。`register_all`
的去重检查（`ops/launch_common.py` `if any(j["name"]==run_id for j in
reg["active"])`）只看 `jobs.json` 的 `active` 列表；训练 job 从 `active`
移出只发生在 `gpu_jobs finish`（销号），按 `probe-pipeline/SKILL.md`，
销号排在 Phase D（收官），明确排在 C4 评测之后（C4 小节原文：'不必等
训练全批收官，逐格收官逐格派评测'）。标准跑法下，`launch-eval` 调
`register_all` 时同名训练 job 几乎总还在 `active` 里，`register_all` 会
`sys.exit(f"run_id {run_id} 已在台账里…")`，被 `launch_and_register` 的
`except SystemExit` 吞成一行 WARN——tmux 评测任务照常发出去，但从头到尾
没有台账条目，也没有 `record.py` 记录。

**复核加深的一层**：追查 `ops/record.py` 后发现问题比评审描述的还要严重——
`record.py start`（`register_all` 第②步）自己也有一层独立的重复检查
（`record.py:237-238` `if ev["run_id"] in load(): sys.exit(...)`）。`load()`
是把 `runs.jsonl` 里全部历史事件按 `run_id` 折叠出来的，`finish` 只是往
事件流里再 append 一条 `finish` 事件，不会把 `run_id` 从 `load()` 的返回值
里删掉。也就是说，即便训练 job 已经在 `jobs.json` 里 `finish` 销号完毕
（绕开了评审描述的第一层撞车），只要这个 `run_id` 曾经在 `record.py` 里
`start` 过，`record.py start` 自己就会再撞一次、独立于 `jobs.json` 的
`active` 列表状态——`rid = sess[len("eval_"):]` 这个写法在**任何**训练/
评测时序下都会撞车，不只是"标准跑法下几乎总撞"。

**修法**：把 `rid = sess[len("eval_"):]` 改成 `rid = sess`（不去掉
`eval_` 前缀）。选这个修法而不是另起一套编码规则的理由：
1. 结构上不可能再跟训练 rid 撞——训练 rid 是 `x = f"{batch}_{model}_{cell}"`，
   评测 rid 现在是 `f"eval_{x}"`，`"eval_" + x == x` 对任何非空 `x` 都无解，
   不依赖 `batch`/`model`/`cell` 的具体取值，是构造上的保证而不是"通常不会"。
2. 有历史先例：`ops/gpu_jobs.py` 的 `cmd_finish` 里有一条审计注释——
   "防提前销号(审计实例 eval_c2_q36_mtool 16:52 被销号,实际跑到 18:17)"，
   说明这个项目历史上真实跑过、台账里真实登记过的评测 job name 就是带
   `eval_` 前缀的完整 session 名，不是去掉前缀的版本。改成 `rid = sess`
   是回到这个已经验证过的命名先例，不是发明新规则。
3. 没有下游代码依赖"评测 rid 等于训练 rid 去掉前缀"这个约定——搜索了
   `ops/*.py`、`run.py`、`tests/*.py` 里所有 `eval_` 相关字符串，没有
   找到任何地方假设两者的 rid 存在这种对应关系。

`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 13 Step 2 原文写的就是
"rid 用 sess 去掉前缀 eval_ 的 `{batch}_{model}_{cell}`"——这条撞车是计划
文本本身携带的缺陷，上一轮实现者是照办的，不是实现偏离了计划。这次修复
没有回改这份计划文档（不在工单范围内，且这段 Task 13 已经执行完毕，没有
后续工单会再读这一步去重新执行）。

**改的文件**：
- `ops/launch_eval.py`：`rid = sess[len("eval_"):]` → `rid = sess`，加了
  一段注释解释为什么不能去前缀（撞车机制 + 结构保证 + 历史先例三点）。
- `tests/test_launch_eval.py`：测试名从
  `test_launches_and_registers_rich_piece_rid_strips_eval_prefix` 改成
  `test_launches_and_registers_rich_piece_rid_keeps_eval_prefix`；断言从
  `self.assertEqual(run_id, "c2_q36_mtool")` 改成
  `self.assertEqual(run_id, "eval_c2_q36_mtool")` 并加了一行
  `self.assertNotEqual(run_id, "c2_q36_mtool")` 把"不能等于训练 rid"这条
  钉死成显式断言；文件头 docstring 同步改了措辞。
- `MAP.md`：`ops/launch_eval.py` 那一行里"run_id 取 session 去掉 `eval_`
  前缀"改成"run_id = session 原样，不去掉前缀"，附一句撞车原因。

### 验证

```
python3 -m unittest tests.test_launch_probe tests.test_launch_eval -v
```

尾部输出：

```
test_launches_and_registers_rich_piece (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_register_failure_warns_but_launch_still_reported (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_skips_when_gpu_not_free (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_skips_when_session_exists (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_launches_and_registers_rich_piece_rid_keeps_eval_prefix (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_register_failure_warns_but_launch_still_reported (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_skips_when_gpu_not_free (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_skips_when_session_exists (tests.test_launch_eval.TestLaunchAndRegister) ... ok

Ran 8 tests in 0.007s

OK
```

发射模拟打印里能看到修复生效——WARN 那一行现在带的是完整前缀名：

```
WARN 登记失败(eval_c2_q36_mtool): run_id 已在台账里
```

（改之前这一行会打印 `WARN 登记失败(c2_q36_mtool): ...`，跟训练 rid 撞的
就是这个字符串。）

全量：

```
python3 -m unittest discover -s tests -v
```

37 个测试全绿，与改动前数量一致（这一轮没加新测试文件，只改了已有的一个
断言 + 测试名）。

```
python3 run.py selfcheck
```

`62 任务 / 4 配方, 16 处缺失`——16 处缺失全部是 `envs/*/venv`、
`mbert-env`、`cprobe-env` 之类的解释器路径，与上一轮报告记录的一致
（`git worktree add` 不带走未跟踪的 venv 目录，工作树隔离导致，与本轮
代码改动无关）；`launch-probe`/`launch-eval` 两个任务本身不在缺失清单里。

dry-run 路径这一轮没有重新跑：F1 的改动只碰 `launch_and_register` 内部
`rid` 这一行赋值，`build()`/`main()` 的 dry-run 分支（`args.dry_run` 为真
时直接 `return`，不进 `launch_and_register`）完全没有触碰这行代码，
上一轮报告里两条 dry-run 命令的输出仍然如实反映当前代码的 dry-run 行为；
`launch_and_register` 本身的四条路径由上面的单测直接覆盖（含新改的
`rid` 断言），判断不需要重复跑一次真实 CLI dry-run 来确认。

### commit 清单（本轮）

- `b49705b` — `T11: 修复评测 rid 与训练 rid 撞车(F1)——eval rid 保留 eval_ 前缀不去掉`
  （`ops/launch_eval.py`、`tests/test_launch_eval.py`、`MAP.md`）

### 自查发现与存疑（本轮）

未发现新的问题。这一轮改动只涉及一处赋值语句 + 对应测试断言 + 两处文档
描述行，没有触碰上一轮报告里记录的另外两条自查存疑（`workdir` 传
`str(WD)`、`stall_line`/`escalate_line` 固定传 `None`）——它们不在这次
findings 范围内，按"逐条修掉，不许扩大范围重构"的指示原样保留。
