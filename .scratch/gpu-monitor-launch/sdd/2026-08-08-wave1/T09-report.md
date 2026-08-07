# T09 — `run.py launch` 子命令

工单: `.scratch/gpu-monitor-launch/issues/09-launch-cmd.md`
参照: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 11(工单点名的实施步骤来源)

## 做了什么

新建 `ops/launch_cmd.py`,实现 `cmd_launch(argv)` 以及三个可单测的纯逻辑函数
`parse_launch_argv`/`build_pieces`/`verify_alive`。`run.py` 挂了 `launch` 分派、
文件头加一行用法、`TASKS["collect-aw"]` 加 `shardable=True`。

逐条对工单验收要求:

1. **分片注入测试通过:两个分片注入编号 0 和 1,非 shardable 多分片拒绝,同机同卡两个分片拒绝**
   `build_pieces(p, t)`:
   - `t.get("shardable")` 为真且 `--piece` 给了 ≥2 个 → 每个分片的命令追加
     `--shard-id <i> --num-shards <N>`(i 从 0 起,顺序即 `--piece` 出现顺序)。
   - 没标 `shardable` 的任务给 ≥2 个 `--piece` → `SystemExit`。
   - 两个 `--piece` 的 `host:gpus` 完全相同 → `SystemExit`(同机同卡互踩)。
   - `--cmd` 模式:`t=None`,命令原样(`p["cmd"]` 直接当 `cmd_str`,不查 `TASKS`,
     不做分片注入——工单没要求 `--cmd` 模式也分片,按字面"命令原样"实现)。
   - session 名 = `new1_<run_id>_t<host去掉tokyo>g<gpus 逗号换连字符>`
     (如 `tokyo108:0,1` → `new1_<rid>_t108g0-1`)。

2. **dry-run 冒烟:采集任务两分片打出两条带分片编号的完整命令,登记函数没被调**
   `--dry-run` 时打印每个分片的 `inner` 命令(含 `cd`/`CUDA_VISIBLE_DEVICES`/`tee`
   的完整 tmux 内命令,不只是裸脚本调用),然后直接 `return 0`——`probe_free`/
   `tmux_launch`/`register_all` 全部不碰。实测:

   ```
   python3 run.py launch collect-aw --run-id smoke_x --track smoke \
     --piece tokyo106:0 --piece tokyo106:1 --dry-run --allow-dirty \
     -- --base-url http://x/v1 --model m --outdir /tmp/x
   ```

   输出两条,分别含 `--shard-id 0 --num-shards 2` 和 `--shard-id 1 --num-shards 2`
   (原文见下方"怎么验证的")。

3. **`python3 run.py selfcheck` 通过(launch 挂进 run.py),commit**
   见下方验证记录。

流程按计划 Task 11 的十步实现,顺序未换:参数解析(手写 iter,`--` 之后一切
透传给任务/`--cmd`,不再当 launch 旗标)→ task/`--cmd` 模式判定 → `gate_dirty`
(honor_dry=True,`--dry-run` 放行)→ `run_id`/`track` 必填校验 → `build_pieces`
(分片注入 + session/log 命名,`log = <workdir>/logs/<sess>.log`,workdir 取
`t["cwd"]`/`--workdir`/ROOT)→ dry-run 分支提前返回 → 逐 piece `probe_free`
(任何一张非 FREE 整次 `SystemExit`,列出全部原因)→ 逐 piece 建 log 目录 +
`tmux_launch` → `verify_alive`(30 秒窗口,5 秒一轮:全部 piece 日志字节数
增长即提前通过;窗口到时逐 piece 查 `has_session` + tail 4KB 有没有
`Traceback` 判定最终成败——失败的打印分片信息 + 日志末 40 行,已发射的不回滚,
`return 1` 且不登记)→ `register_all(...)` 组装 rich piece(host/gpus/session/
log/cmd/launched_at/kind/stall_line/escalate_line)+ job 级 `monitor`(只有
`--warmup-line` 给了才带 `warmup_s`,没给就不传 `monitor` 参数,符合 T08 收账
"`monitor=None` 时不写 job 的 `monitor` key"的约定)→ 打印监控入口
(`gpu-jobs` / `watch` / 网页 `localhost:8377`)。

## 怎么验证的

```
$ python3 -m unittest tests.test_launch_cmd -v
```
```
test_dry_run_does_not_probe_or_launch (tests.test_launch_cmd.TestCmdLaunchDryRun) ... ok
test_dry_run_prints_shard_commands_and_skips_register (tests.test_launch_cmd.TestCmdLaunchDryRun) ... ok
test_non_free_piece_rejects_all_and_no_register (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_success_registers_rich_pieces (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_verify_alive_failure_skips_register (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_missing_run_id_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_missing_track_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_unknown_task_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_cmd_mode_flags (tests.test_launch_cmd.TestParseLaunchArgv) ... ok
test_task_positional_and_flags (tests.test_launch_cmd.TestParseLaunchArgv) ... ok
test_fails_on_traceback_in_tail (tests.test_launch_cmd.TestVerifyAlive) ... ok
test_fails_when_session_gone (tests.test_launch_cmd.TestVerifyAlive) ... ok
test_ok_when_alive_and_no_traceback (tests.test_launch_cmd.TestVerifyAlive) ... ok
... (共 19 条，含 TestBuildPieces 6 条)
----------------------------------------------------------------------
Ran 19 tests in 0.311s

OK
```

```
$ python3 -m unittest discover -s tests -v   # 全仓测试(与其它已合并工单共存)
```
```
Ran 54 tests in 0.573s

OK
```

```
$ python3 run.py selfcheck
```
```
selfcheck: 63 任务 / 4 配方, 16 处缺失
缺解释器/程序: .../envs/appworld/venv/bin/python  (任务 collect-aw)
... (16 条,全部是 envs/*/venv、cprobe-env、mbert-env 等第三方 venv 缺失)
```
这 16 条在**主仓工作树**(`/home/y-guo/reproduce/new1`)跑 `selfcheck` 是
`全部就位`(已核对)。venv 目录不进 git(`.gitignore`),`git worktree add`
只材质化 git 追踪的文件,worktree 里天然没有这些第三方 venv——这是并行工作树
本身的产物,不是这次改动引入的问题;`shardable=True` 这类新增字段本身不参与
`selfcheck` 的检查项(只查 `py`/`prog`/`script`/`cwd` 存在性、`RECIPES`/
`EVAL_CELLS` 引用)。

```
$ python3 run.py launch collect-aw --run-id smoke_x --track smoke \
    --piece tokyo106:0 --piece tokyo106:1 --dry-run --allow-dirty \
    -- --base-url http://x/v1 --model m --outdir /tmp/x
```
```
[dry-run] tokyo106 gpu0 new1_smoke_x_t106g0
    cd .../new1-wt/20260808-par-T09 && CUDA_VISIBLE_DEVICES=0 .../envs/appworld/venv/bin/python .../envs/collect/run_appworld.py --base-url http://x/v1 --model m --outdir /tmp/x --shard-id 0 --num-shards 2 2>&1 | tee .../logs/new1_smoke_x_t106g0.log
[dry-run] tokyo106 gpu1 new1_smoke_x_t106g1
    cd .../new1-wt/20260808-par-T09 && CUDA_VISIBLE_DEVICES=1 .../envs/appworld/venv/bin/python .../envs/collect/run_appworld.py --base-url http://x/v1 --model m --outdir /tmp/x --shard-id 1 --num-shards 2 2>&1 | tee .../logs/new1_smoke_x_t106g1.log

共 2 分片(dry-run,未发射,未登记)
```
两条命令都带 `--shard-id`/`--num-shards`,与工单验收项 2 逐字对上。

## commit 清单

- `0144ea0` — `T09: run.py launch 子命令(验卡→tmux→验活→三处登记一条命令;shardable 注入)`
  改动:`ops/launch_cmd.py`(新建)、`tests/test_launch_cmd.py`(新建)、`run.py`
  (加 launch 分派 + 用法行 + `collect-aw` 的 `shardable=True`)。

## 自查发现与存疑

- **`--service`/`--port` 没有专门逻辑**:计划 Task 11 的 `Produces` 命令签名里
  写了 `[--service --port N]`,但十个编号步骤里没有任何一步提到怎么处理它们,
  设计文档 §6 的发射段也没提。`--service` 我实现成一个识别的布尔旗标,给了就把
  该次发射所有 piece 的 `kind` 设成 `"service"`(默认 `"batch"`),仅此而已;
  `--port` 没有单独识别,落进"未知旗标透传给任务"的分支——vLLM 这类服务本来就
  要把 `--port` 传给真正的 `vllm serve` 命令,当任务参数处理是合理的落点。
  但 `verdicts.py`/计划 Task 15(vLLM 服务档)提到 service 分片要靠
  `probe_port(host, port)` 判活,而 rich piece 的字段表(T08 docstring 定的)
  里根本没有 `port` 字段——这个字段从 piece 传到采样器的路径,整份计划文档里
  没有交代。这不在本工单的验收范围内(工单 13 vLLM 服务档改的是
  `ops/sampler.py`,不是 `launch_cmd.py`),我没有替它发明字段,留给做工单 13
  的人去定,或者回头找用户确认这处计划空白怎么补。
- **`gate_of` 没有导入/使用**:计划 Task 11 的 `Consumes` 列了
  `run.TASKS/PY/build_cmd/gate_dirty/gate_of`,但十步流程里没有任何一步
  实际用到 `gate_of`(launch 用自己的 `gate_dirty` 统一门禁,不走
  `TASKS`/`gate_of`/`print_handoff`/`run_direct` 那条旧路由)。我没有导入
  `gate_of`,避免死代码;如果这是遗漏的用途(比如想让 launch 尊重某任务
  `gate=False` 时走别的路径),需要用户或后续工单澄清。
- **`--cmd` 模式多 `--piece` 不做分片注入**:工单验收项只测了 task 模式的分片
  注入,`--cmd` 模式的"命令原样"(Step1 测试原话)我理解为哪怕给多个
  `--piece`,每个分片也是同一条命令,不追加任何东西——这与 task 模式的分片
  拒绝规则(非 shardable 报错)不对称:`--cmd` 模式给多个 `--piece` 完全不拒绝
  也不分片,直接原样复制发射。工单和计划都没写 `--cmd` 模式该不该拒绝多分片,
  我按最贴近字面"命令原样"的读法实现,行为记在这里供复核。
- **`--workdir` 只在 `--cmd` 模式生效**:计划原文"workdir 默认 ROOT,task 有
  cwd 用 cwd"只提了 task 分支,命令签名也只在 `--cmd` 模式那行写了
  `--workdir DIR`。我据此实现成:task 模式忽略 `--workdir`(即便给了也不用,
  只用 `t.get("cwd", ROOT)`),`--cmd` 模式才吃 `--workdir`。如果用户想要
  task 模式也能覆盖 workdir,需要另外定接口。
- **多分片的 `cmd_display`(给 `record.py`/RUNMETA 用的单条命令展示串)**:
  计划没定义多分片时这个字段该长什么样,我实现成:单分片直接用该分片命令;
  多分片用 `"; "` 拼接每个分片的完整命令。这是我在没有更明确规格时做的最小
  合理选择,不是照抄某处既有写法,值得在下一次真实多分片发射后肉眼核对
  `RESULTS.md` 渲染效果是否可读(工单 09 的 Comments 里也提到这条要主会话
  核对一次)。
- 没有发射任何真实 GPU 进程或 tmux session,`probe_free`/`tmux_launch`/
  `register_all`/网络调用在测试里全部 mock,没有触碰真实台账
  (`ops/jobs.json`)、`ops/runs.jsonl`、任何 GPU 机器。

## 修复轮 1(2026-08-08)

评审揪出一条 important finding:

### F1 — 同机同卡去重只查字符串完全相同,重叠的 GPU 段不拦

**问题**:`build_pieces()` 原来的判重逻辑是 `key = (host, gpus)` 存进
`seen` 这个 set,`gpus` 用的是 `--piece` 里冒号后半段的原始字符串。两个
`--piece` 只有字符串**完全相同**才会被拦(`tokyo106:0` 和 `tokyo106:0`)。
但一个 piece 可以是多卡串(如 `tokyo108:0,1`,`test_session_name_format`
测试里已经在用这种形式),`--piece tokyo106:0,1 --piece tokyo106:1,2`
两个字符串不相等,不会被拒绝,而它们在 gpu1 上是真实重叠的——会把两个进程
同时发到同一张卡上,这是发射前验卡(`probe_free`)之外的一处静默漏判。

**怎么修的**:`ops/launch_cmd.py` 的 `build_pieces()` 里,把 `seen = set()`
+ 字符串 key 精确匹配,换成按 host 累积一个"已占用 gpu id 集合"
(`claimed_by_host: dict[host] -> set[gpu_id]`)。每个新 `--piece` 先把
`gpus` 按逗号拆成 gpu id 的 set,与该 host 已经累积的集合求交集;交集非空
就 `SystemExit`(报出具体冲突的 gpu id),交集为空就把这些 id 并入累积
集合继续。这个改法同时覆盖了原来的精确重复场景(完全重复必然交集非空)
和新发现的部分重叠场景,也不会误伤同机不重叠的卡(如 `0,1` 与 `2,3`
应当放行)。报错文案沿用原来的措辞("同机同卡两个分片会互相踩,拆成不同
卡或分开发射"),只是判定条件从字符串相等换成了集合求交。

改动范围只有 `build_pieces()` 内部这一段判重逻辑,函数签名、返回结构、
调用方 `cmd_launch()` 都没动,没有扩大范围重构。

**测试**:在 `tests/test_launch_cmd.py` 的 `TestBuildPieces` 里补两条:

- `test_overlapping_multi_gpu_pieces_rejected`:`tokyo106:0,1` +
  `tokyo106:1,2`(重叠 gpu1)应当 `SystemExit`。
- `test_disjoint_multi_gpu_pieces_same_host_allowed`:`tokyo106:0,1` +
  `tokyo106:2,3`(不重叠)应当放行,产出 2 个 piece。

原有的 `test_duplicate_host_gpu_piece_rejected`(完全重复的
`tokyo106:0` + `tokyo106:0`)不改,验证新逻辑没有回退旧场景。

```
$ python3 -m unittest tests.test_launch_cmd -v
```
```
test_cmd_mode_command_verbatim_no_registry (tests.test_launch_cmd.TestBuildPieces) ... ok
test_disjoint_multi_gpu_pieces_same_host_allowed (tests.test_launch_cmd.TestBuildPieces) ... ok
test_duplicate_host_gpu_piece_rejected (tests.test_launch_cmd.TestBuildPieces) ... ok
test_no_piece_rejected (tests.test_launch_cmd.TestBuildPieces) ... ok
test_non_shardable_rejects_multi_piece (tests.test_launch_cmd.TestBuildPieces) ... ok
test_overlapping_multi_gpu_pieces_rejected (tests.test_launch_cmd.TestBuildPieces) ... ok
test_session_name_format (tests.test_launch_cmd.TestBuildPieces) ... ok
test_shardable_two_pieces_get_shard_flags (tests.test_launch_cmd.TestBuildPieces) ... ok
test_dry_run_does_not_probe_or_launch (tests.test_launch_cmd.TestCmdLaunchDryRun) ... ok
test_dry_run_prints_shard_commands_and_skips_register (tests.test_launch_cmd.TestCmdLaunchDryRun) ... ok
test_non_free_piece_rejects_all_and_no_register (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_success_registers_rich_pieces (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_verify_alive_failure_skips_register (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_missing_run_id_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_missing_track_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_unknown_task_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_cmd_mode_flags (tests.test_launch_cmd.TestParseLaunchArgv) ... ok
test_task_positional_and_flags (tests.test_launch_cmd.TestParseLaunchArgv) ... ok
test_fails_on_traceback_in_tail (tests.test_launch_cmd.TestVerifyAlive) ... ok
test_fails_when_session_gone (tests.test_launch_cmd.TestVerifyAlive) ... ok
test_ok_when_alive_and_no_traceback (tests.test_launch_cmd.TestVerifyAlive) ... ok

----------------------------------------------------------------------
Ran 21 tests in 0.314s

OK
```

```
$ python3 -m unittest discover -s tests -v   # 全仓测试
```
```
Ran 56 tests in 0.551s

OK
```
(比修复前多 2 条,即新补的两条重叠/不重叠测试;其余用例的输出行原样不变。)

```
$ python3 run.py selfcheck
```
在这个修复轮的工作树(`/home/y-guo/reproduce/new1-wt/20260808-par-T09-fix1`)
里跑,输出 `16 处缺失`,与 T09 首轮报告记录的一致——16 条全部是
`envs/*/venv`、`cprobe-env`、`mbert-env` 等第三方 venv 目录在这个新建的
`git worktree` 里天然不存在(不进 git),不是这次改动引入的问题。在主仓
工作树(`/home/y-guo/reproduce/new1`)跑同一条命令确认为 `全部就位`。

### commit 清单(修复轮 1)

- `0160809` — `T09: 修复 F1——同机同卡去重改按 GPU 集合重叠判定,不再只查字符串相等`
  改动:`ops/launch_cmd.py`(`build_pieces()` 判重逻辑)、
  `tests/test_launch_cmd.py`(补两条重叠/不重叠测试)。

### 自查发现与存疑(修复轮 1)

- 只改了 `build_pieces()` 里判重这一段,没有动分片注入、session 命名、
  `--cmd` 模式等其它逻辑,没有借机重构或顺手改工单没点名的地方。
- gpu id 按逗号拆分后没有做数字合法性校验(比如 `"0,1,"` 会拆出一个空
  字符串),但原来的代码在这块也没做校验,不在这条 finding 的修复范围内,
  没有顺手加。
