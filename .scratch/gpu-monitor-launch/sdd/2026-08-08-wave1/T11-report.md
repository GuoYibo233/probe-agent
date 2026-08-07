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
