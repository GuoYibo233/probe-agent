# T08 — 发射公共件（08-launch-common）报告

工单：`.scratch/gpu-monitor-launch/issues/08-launch-common.md`
需求细节来源：工单未引用 spec，按工单指示读了实施计划
`docs/plans/2026-08-08-gpu-monitor-launch.md` 的 Task 10（第 797-818 行）。
工作树：`/home/y-guo/reproduce/new1-wt/20260808-par-T08`，分支 `ticket/20260808-par/T08`。

## 做了什么

新建 `ops/launch_common.py`，对照工单三条能力逐条实现：

1. **探卡 `probe_free(host, gpus)`**：`ssh <host> nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader -i <gpus>`。
   stdout 非空 → `(False, "占用中: <首行>")`；ssh 超时/`OSError`/非零退出 →
   `(False, "探测失败: ...")`；stdout 为空 → `(True, "")`。fail-closed：探测
   失败与占用中同样返回非 FREE。

2. **tmux 发射模板**：`ALIAS = {"shiga": "tokyo105", "saitama": "tokyo108"}`
   照抄；`local_host()`（从 `launch_probe.py` 原来的模块级常量 `LOCAL` 改成
   按需算的函数，方便测试 monkeypatch，行为不变——都是 `hostname` 经 ALIAS
   折算）；`has_session(host, s)` 与 `tmux_launch(host, sess, inner_cmd)` 与
   `launch_probe.py:47-62` 的逻辑一致（本机走 `bash -c`，远程走
   `ssh -n host`；`tmux_launch` 的 inner 模板与调用方拼好的
   `cd <wd> && CUDA_VISIBLE_DEVICES=<g> <cmd> 2>&1 | tee <log>` 一致）。
   与 `launch_probe.py` 原来的 `launch()` 不同的一点：`tmux_launch` 不做
   「session 已存在就跳过」的判断——那是调用方（launch_cmd / 排卡发射器）
   的业务，工单 09/11 会各自处理；这一张不改任何现有发射器的行为，
   `launch_probe.py`/`launch_eval.py` 原样未动。

3. **`register_all(run_id, workdir, pieces, track, cmd_display, note=None, outdir=None, monitor=None)`**：
   三处登记按固定顺序（台账→记录→RUNMETA）不吞异常地做：
   - 台账：`gpu_jobs.mutate_reg` 里 `reg["active"]` 已有同名 job（`name==run_id`）
     就 `sys.exit`（重复 run_id 拒绝，锁内检查，护栏）；否则 append
     `{"name","workdir","note","started_at","pieces"}`，`pieces` 就是调用方
     传进来的 rich piece 列表（原样收，不重新构造字段）；`monitor` 只在非
     `None` 时才写进 job（避免下游 `job.get("monitor",{}).get("warmup_s")`
     在 `monitor` 显式为 `None` 时因为 key 存在但值不是 dict 而报错——这是
     我自己推的一条安全边界，工单原文没写这条，见下方"自查发现"）。
   - 记录：`subprocess.run([sys.executable, OPS/"record.py", "start", "--run-id", run_id, "--track", track, "--cmd", cmd_display, "--host", ..., "--gpu", ..., "--log", ...])`，
     多分片的 host/gpus/log 各自逗号拼成一个展示串传给这三个参数（工单原文
     只写了"..."没给多分片时的拼法，这是我做的裁决，见下方"自查发现"）；
     不 `capture_output`，让 `record.py` 自己的报错直接打到终端；`rc != 0`
     → `sys.exit(rc)` 原样透出并中止。
   - RUNMETA：`outdir` 给了才 `runmeta.append_runmeta(outdir, cmd_display, kind="launch")`；
     没给打印并在回执里带一行 `WARN 没给 --outdir，RUNMETA 没写`。
   - 返回三行回执文本（台账/记录/RUNMETA 各一行）。

同一 commit 更新了 `MAP.md`：在「记账与发射工具」表里加了 `ops/launch_common.py`
一行（放在 `ops/jobs.json` 和 `ops/launch_probe.py` 之间）。没有改
`run.py` 注册表——`launch_common.py` 本身不是一个可跑的任务，是给工单 09
（`run.py launch`）和工单 11（两个排卡发射器）用的库，工单原文明确写了
「这一张不改任何现有发射器的行为」。

## 怎么验证的

写了 `tests/test_launch_common.py`，14 个用例，覆盖工单两条验收要求外加
`local_host`/`has_session`/`tmux_launch` 的基本行为：

- `TestProbeFree`：空 stdout / 有进程行 / `subprocess.TimeoutExpired` /
  非零 rc 四种输入（工单点名的三种 + 我补的非零 rc 一种，理由见下方
  "自查发现"）对应四种返回。
- `TestRegisterAll`：`test_ledger_gets_rich_piece_full_fields` 断言台账
  `pieces[0]` 出现 `host/gpus/session/log/cmd/launched_at/kind/stall_line/escalate_line`
  全部九个字段；`test_duplicate_run_id_rejected_on_second_call` 断言同一
  `run_id` 第二次调用 `register_all` 抛 `SystemExit`，且台账里仍只有一条；
  另加 `test_no_monitor_key_when_not_given`（不给 `monitor` 时台账里没有
  这个 key）、`test_record_failure_aborts_but_ledger_already_written`
  （`record.py` 模拟 rc=1 时 `register_all` 抛出，但台账那一步已经落地）、
  `test_outdir_given_writes_runmeta` / `test_no_outdir_warns_instead_of_writing`。
  用 `monkeypatch gpu_jobs.REG_PATH` 指到 tmp 文件隔离台账（工单原文写法）。
- `TestLocalAndSession`：`local_host` 经 ALIAS 折算、`has_session`/
  `tmux_launch` 本机走 `bash`、远程走 `ssh` 的分支各一个用例。

运行：

```
python3 -m unittest tests.test_launch_common -v
```

输出（尾部）：

```
test_has_session_local_uses_bash (tests.test_launch_common.TestLocalAndSession) ... ok
test_has_session_remote_uses_ssh (tests.test_launch_common.TestLocalAndSession) ... ok
test_local_host_applies_alias (tests.test_launch_common.TestLocalAndSession) ... ok
test_tmux_launch_builds_new_session_cmd (tests.test_launch_common.TestLocalAndSession) ... ok
test_free_when_stdout_empty (tests.test_launch_common.TestProbeFree) ... ok
test_occupied_when_stdout_has_process (tests.test_launch_common.TestProbeFree) ... ok
test_probe_fails_on_nonzero_rc (tests.test_launch_common.TestProbeFree) ... ok
test_probe_fails_on_timeout (tests.test_launch_common.TestProbeFree) ... ok
test_duplicate_run_id_rejected_on_second_call (tests.test_launch_common.TestRegisterAll) ... ok
test_ledger_gets_rich_piece_full_fields (tests.test_launch_common.TestRegisterAll) ... ok
test_no_monitor_key_when_not_given (tests.test_launch_common.TestRegisterAll) ... ok
test_no_outdir_warns_instead_of_writing (tests.test_launch_common.TestRegisterAll) ... ok
test_outdir_given_writes_runmeta (tests.test_launch_common.TestRegisterAll) ... ok
test_record_failure_aborts_but_ledger_already_written (tests.test_launch_common.TestRegisterAll) ... ok

Ran 14 tests in 0.157s

OK
```

再跑全量：

```
python3 -m unittest discover -s tests -v
```

29 个测试（含 T01 之前写的 `test_heartbeat.py`/`test_verdicts.py`）全绿，
`ops/jobs.json`/`RESULTS.md` 没被动过（`git status --porcelain` 确认）。

`run.py selfcheck` 跑了一遍（没改注册表，非强制项，顺手确认没引入新问题）：
输出 `62 任务 / 4 配方, 16 处缺失`，16 条全是这个工作树没有各 env 的
venv/解释器（`envs/appworld/venv/bin/python` 之类），是工作树本身的环境
缺失，与本工单改动无关，`launch_common.py`/`launch_common` 相关任务不在
缺失清单里（因为它压根没进注册表）。

## commit 清单

- `c55e47a` — `T08: 发射公共件 ops/launch_common.py(探卡fail-closed/tmux模板/三处登记一口气)`
  （`ops/launch_common.py` 新建、`tests/test_launch_common.py` 新建、
  `MAP.md` 加一行）

## 自查发现与存疑

工单原文对 `register_all` 的描述里有两处细节没写全，我按"能安全裁决"的
标准自己定了，记在这里供评审核对：

1. **`monitor` 为 `None` 时台账 job 要不要写 `monitor` key**：工单写
   "job 级 `monitor={"warmup_s":...}`"，没说不给 `monitor` 参数时怎么办。
   实施计划另一处（Task 6 采样器，第 698 行）写了消费端逻辑：
   `warmup_s` 从 `job.get("monitor", {}).get("warmup_s")` 取，缺省退到
   `verdicts.DEFAULTS`。如果 `register_all` 在 `monitor=None` 时仍然写
   `job["monitor"] = None`，消费端 `job.get("monitor", {})` 会因为 key
   存在而返回 `None`（不会退到 `{}`），再 `.get("warmup_s")` 就会在 `None`
   上报 `AttributeError`。我判断这是能安全裁决的坑，选择"`monitor` 是
   `None` 就不写这个 key"，用 `test_no_monitor_key_when_not_given` 钉住。
   **这条不在工单验收清单里，值得工单 09（`run.py launch`）落地时确认
   一下它会不会给一个非空 `monitor` dict。**

2. **多分片时 `record.py start` 的 `--host`/`--gpu`/`--log` 怎么填**：
   `record.py` 的 `cmd_start` 每个参数只接受一个字符串值，而
   `register_all` 的 `pieces` 是列表（工单 09 的分片场景一次发射可能是
   多个 host:gpu）。工单原文只写了 "`--host`, ..., `--gpu`, ..., `--log`, ..."，
   没给多分片时的拼法。我选的是把各分片的 `host`/`gpus`/`log` 分别用逗号
   拼成一个字符串（`"tokyo106,tokyo107"` 这种）。这个字段在 `RESULTS.md`
   里只是展示用，不影响记录体系的其它字段，风险低，我判断能安全裁决；
   但拼法本身没有测试断言具体值（只断言了 `subprocess.run` 被调用且
   `rc==0` 路径正常），**工单 09 落地、真正产出多分片调用时最好肉眼核对
   一下 `RESULTS.md` 里这行长什么样，看是否需要换个更好读的格式。**

3. `probe_free` 补了一种工单没点名的输入（ssh 命令本身 rc 非零但没超时、
   stdout 也是空——比如远程 `nvidia-smi` 报错或 host key 拒连）：按
   fail-closed 原则也判成"探测失败"。工单验收清单写的是"空卡、占用中、
   探测超时三种输入"，我多测了一种，不影响这三种原有断言，认为是必要的
   补充覆盖，不算 YAGNI（同一个函数的另一条分支，不是额外功能）。

没有发现需要改的风格不一致问题；`has_session`/`tmux_launch`/`local_host`
的 ssh/bash 分支写法与 `ops/launch_probe.py:47-62` 保持一致（本机
`bash -c`、远程 `ssh -n host`）。
