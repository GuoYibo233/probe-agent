# T10 report — fallback five + freeze-legacy

工单：`.scratch/research-loop/issues/10-fallback-freeze.md`
分支：`ticket/20260814-wave4/T10`（工作树 `new1-wt/20260814-wave4-T10`，已删除）
base：`963bdaaf26fb897482e61c3fc4a6629005ec25c0`
head：`c6846e2` （`ticket/20260814-wave4/T10` 唯一一条 commit）

## 做了什么

七个文件，均在 `research-loop/` plugin 内，不改 `run.py`/`MAP.md`（工单范围声明）：

- `research-loop/scripts/fallback/registry.py`
- `research-loop/scripts/fallback/launch.py`
- `research-loop/scripts/fallback/record.py`
- `research-loop/scripts/fallback/fake_experiment.py`
- `research-loop/scripts/fallback/fake_metrics.py`
- `research-loop/scripts/ledger_cmds/freezecmd.py`
- `research-loop/tests/test_fallback.py`

对照工单六条要求逐条核对：

### registry.py

内置任务表 `{"fake-experiment": [sys.executable, .../fake_experiment.py],
"fake-metrics": [sys.executable, .../fake_metrics.py]}`（路径用
`_lib.plugin_root() / "scripts" / "fallback"` 算，不是手写相对路径）。
`--list` 一行一个任务名、零副作用（不读写任何文件）；`<task> [args...]`
`subprocess.run` 转发、透传 `returncode`；未知任务与空参数都走 stderr 报错、
exit 4（空参数不是工单点名的分支，按实现者规程"边界处补测试"处理，见下）。

### launch.py LAUNCH_ORDER.json [--project-root P]

按工单六步顺序实现：

1. **脏树检查**：`workdir` 解析为 `project_root / order["workdir"]`
   （`--project-root` 给了用给的，没给 `_lib.find_project_root()`，再没有
   退 `Path.cwd()`）；`git status --porcelain` 在该目录跑，非 git 仓库
   （返回码非 0）视为无脏树门禁（自测沙盒场景）；命中的路径经
   `tables/config.json dirty_exempt_globs` 逐条 `fnmatch` 过滤，剩余非空
   → stderr 逐字 `refuse to launch: dirty tree; escalate to deploy layer`，
   exit 3，不写任何 jobs/RUNMETA。
2. **expected_commit 校验**：`_lib.git_head(project_root)` 去掉 `-dirty`
   后缀（豁免残留的脏文件仍可能让 git_head 带后缀，工单原文点名这条）跟
   `order["expected_commit"]` 比，不等 → exit 3（消息里带 expected/got 两个值，
   工单没给字面文案，仿脏树消息的语气自拟）。
3. **jobs 登记**（`ops/jobs.json`，`_lib.locked` 持 `<jobs>.lock`）：
   `run_id -> {launch_order_ref, state: "running", started_at, finished_at:
   null, log_path}`，`launch_order_ref` 是命令行给的发射单路径原样字符串
   （不 resolve，跟 T12 output_check.py"路径按给定形式保留"的做法一致）。
4. **`_lib.run_argv(order["argv"], cwd=workdir, timeout=expected_runtime_s
   × runtime_factor)`**：`runtime_factor` 取 `cfg.get("runtime_factor")`
   （沙盒里显式设成 3，跟 `helpers.make_sandbox` 一致）；stdout+stderr 落
   `<artifact_dir>/attempt<N>.log`（stderr 非空时加一行 `--- stderr ---`
   分隔，纯可读性，不影响后续任何解析）；超时时 `_lib.run_argv` 内部的
   `subprocess.run(timeout=...)` 已经杀进程并返回 `exit_code=None`，
   launch.py 据此判 `state=timeout`、自身进程 exit 1（工单只要求"exit 非
   0"，没给具体值——子进程超时没有真实退出码可透传，1 是我选的哨兵值）。
5. **RUNMETA**：不存在时新建 `{commit, argv, dirty_files: [], launch_order_ref,
   attempts: [attempt1], env_name, outputs: []}`；已存在时只 append 一条
   attempt（`attempt_no = len(既有 attempts) + 1`），顶层其余字段（含
   `commit`/`argv`/`env_name`）保持磁盘上原值不重算，配合"前条 attempt 的
   argv/log_path/resources 不动"——因为压根不touch 旧 attempt dict，只 append
   新的。写盘用临时文件 + `os.replace`（原子替换），没有额外加锁——工单
   六步原文只给 jobs 登记和 runs 入账两处点名"持锁"，RUNMETA 没有点名，
   我按字面执行；atomic-replace 本身足够防半写坏文件。
6. **jobs 收尾**：`state = done(exit0)/failed/timeout` + `finished_at`；
   `process_exit` 三态透传（done→0，failed→子进程真实 exit_code，
   timeout→1 号哨兵）。

`argv` 全程原样执行，不重新拼装、不查注册表——工单/spec §5 明确"argv 是
权威执行体"，`registry_task` 只是归属声明，那层校验属于 T08 写发射单的
范围，不在 launch.py 里重复。

### record.py --launch-order PATH [--status S]

五步照工单实现：读发射单 + RUNMETA（RUNMETA 缺、或 attempts 为空 → exit 2）；
`--status` 给了用给的，没给按最后一条 attempt 的 `exit_code==0` 判
ok/failed；status=ok 时 `_lib.split_cmd` 切 `metrics_cmd`（不经 shell）→
`_lib.run_argv(cwd=project_root)` → `_lib.last_json_line` 解出的
`{"metrics":[...]}` 非空数组才继续，否则 stderr 逐字
`refuse: metrics output invalid; no row recorded; escalate per R8`、exit 2、
不写任何行；每个 metric 项拼一行（`filter` 缺省回落发射单的 `filter`）。
status≠ok 时单行、`metric_name`/`value`/`n` 三个都 null。

写入前在同一把 `runs.jsonl.lock` 内：先按 `_run_level_fields`
（`status/output_dir/runmeta_path/seed/dataset_version/batch_id/arm/quick/
commit/elapsed_s/gpu_count`，工单原文列的字段清单，硬编码成常量而不是从
`rows.json` 的说明字符串里解析——那段是文档键，生成器不读，不当机器可解析
源）跟该 `run_id` 已有行比对，不一致就 `_lib.fail`；再按
`(run_id, metric_name, filter)` 主键跨档（含归档）查重，命中就 `_lib.fail`；
两关都过了才逐行 `_lib.validate`（对 `runs.normal` schema）再逐行
`jsonl_append`——检查全在锁内、写入在检查全过之后才发生，保证"一次锁内
写完，要么全上要么全不上"。

`elapsed_s` = RUNMETA 最后一条 attempt 的 `finished_at - started_at`
（`datetime.fromisoformat` 相减取整秒）；`gpu_count` = 发射单
`resources.gpus`（缺则 null）。

record.py 是独立入口（不挂 `ledger.py` 分发器），异常处理仿 `ledger.py`
自己的约定：`main()` 包一层 `try/except _lib.RLError` → stderr + exit 2，
跟主分发器"RLError 到 stderr、exit 2"的语义对齐，虽然这个脚本自己跑、
不经过那个 except 块。

### fake_experiment.py / fake_metrics.py

按工单五种 mode 逐条实现：ok/bad-metrics 写 5 行
`{"i": k, "v": seed*k}`（k=0..4，工单没定起始索引，我取 0 起）；fail 写
stderr `simulated failure` + exit 1；empty 建空文件 + exit 0；timeout
`time.sleep(30)`。`mode.txt` 在所有分支之前统一先写。fake_metrics.py 读
`mode.txt`，`bad-metrics` 输出 `this is not json`，其余算
`int(sha256(result.jsonl 字节).hexdigest(), 16) % 1000 / 1000` 当 `acc`
的值、行数当 `n` 和 `rows` 的值——跟工单公式逐字一致。

### freezecmd.py（`ledger.py freeze-legacy --confirm`）

已存在 → stderr `freeze-legacy already done; repeat refused`、exit 1；无
`--confirm` → stderr 打印将做的事、exit 1；`--confirm` 时：读原始字节 →
写 legacy 文件 → sha256 比对（机验①，legacy 逐字节等于原文件）→ 主文件
清零（`write_bytes(b"")`）→ 主文件 size==0 复核（机验②）→ stdout 提醒把
`runs_legacy` 补进 config 的 `ledgers`/`owners` 两处键。legacy 路径直接从
`runs_path.parent / "runs.legacy.jsonl"` 算，不经
`cfg.ledger_path("runs_legacy")`——工单原文"legacy 路径 = runs 路径同目录"，
这样即使项目还没把 `runs_legacy` 挂进 `research-loop.json`（freeze-legacy
本来就是挂接前跑的一次性迁移），路径也不依赖那两个还不存在的键。全程持
`runs_path` 的锁（`<runs路径>.lock`，跟 record.py/runs-append 同一把）——
工单六步原文没点名这条锁，`writes.json` 的 `archive` 维护动作明确要求
"全程持该账文件锁"，`freeze-legacy` 虽然文档没重复这句但性质相同（改主
账文件），按同等谨慎加了。命令本身已经在 T03 的 `ledger.py`
`_SUBCOMMAND_MODULES` 里注册好（`"freeze-legacy": "freezecmd"`），本工单
不用改 `ledger.py`。

## 怎么验证的

`tests/test_fallback.py` 12 条，全部走 `helpers.make_git_sandbox` 加一层
自建的 `_sandbox()`（额外提交一个 `.gitignore` 把 `ops/` 整个忽略掉——
测试运行时写的发射单、jobs.json、fake 产物全在 `ops/` 下，这样脏树门禁
测试才能针对一个真正被跟踪的文件，而不是被自己的运行时写入误伤）：

```
$ python3 research-loop/tests/run_all.py test_fallback
PASS test_fallback.test_freeze_legacy_checks_pass_repeat_refused_and_layer_flag_rejected
PASS test_fallback.test_launch_accepts_explicit_project_root_when_cwd_differs
PASS test_fallback.test_launch_and_record_fall_back_to_cwd_when_no_project_root_is_found
PASS test_fallback.test_launch_ok_writes_runmeta_and_marks_jobs_done
PASS test_fallback.test_launch_rejects_dirty_tree_but_honors_dirty_exempt_globs
PASS test_fallback.test_launch_rejects_expected_commit_mismatch
PASS test_fallback.test_launch_rerun_appends_attempt_and_leaves_the_first_untouched
PASS test_fallback.test_launch_timeout_kills_the_process_and_marks_jobs_timeout
PASS test_fallback.test_record_bad_metrics_output_is_refused_with_no_new_rows
PASS test_fallback.test_record_ok_writes_two_metric_rows_with_matching_run_level_fields
PASS test_fallback.test_record_status_override_writes_a_single_row_with_null_metric_fields
PASS test_fallback.test_registry_list_two_tasks_and_unknown_task_exits_4
-- run_all: 12 passed, 0 failed
```

工单九条测试 ↔ 测试函数对照：

| 工单条目 | 测试函数 |
|---|---|
| 1 registry --list 两名/未知 exit4 | `test_registry_list_two_tasks_and_unknown_task_exits_4` |
| 2 launch ok：jobs done/RUNMETA 齐/attempt1.log/exit0 | `test_launch_ok_writes_runmeta_and_marks_jobs_done` |
| 3 脏树拒 exit3；豁免放行 | `test_launch_rejects_dirty_tree_but_honors_dirty_exempt_globs` |
| 4 expected_commit 错 exit3 | `test_launch_rejects_expected_commit_mismatch` |
| 5 重跑两次 attempts=2、attempt1 不动 | `test_launch_rerun_appends_attempt_and_leaves_the_first_untouched` |
| 6 timeout+expected_runtime_s=1，~3s | `test_launch_timeout_kills_the_process_and_marks_jobs_timeout` |
| 7a record ok 两行/run级字段一致/过schema | `test_record_ok_writes_two_metric_rows_with_matching_run_level_fields`（前半） |
| 7b 重复 record 同主键拒 | 同上（后半，同一函数续做第二次 record） |
| 7c --status empty-output 单行三 null | `test_record_status_override_writes_a_single_row_with_null_metric_fields` |
| 8 bad-metrics：record exit2、无新行 | `test_record_bad_metrics_output_is_refused_with_no_new_rows` |
| 9 freeze-legacy 两机验/重复拒/--layer 被拒 | `test_freeze_legacy_checks_pass_repeat_refused_and_layer_flag_rejected` |

自补 2 条（implementer.md："没点名就在你改动的边界处补测试"，两条脚本都
写了 `_lib.find_project_root() or Path.cwd()` 这条防御性回落，工单九条
测试里没人经过它——全部走 `helpers.run_script(cwd=root-带config)`，
`find_project_root()` 永远命中，那条 `or Path.cwd()` 分支和 `--project-root`
显式覆盖分支都是没验证过的代码路径）：

- `test_launch_accepts_explicit_project_root_when_cwd_differs`：进程 cwd
  设成跟项目无关的另一个目录，显式传 `--project-root <root>`，断言 launch
  仍然成功、RUNMETA 落在正确位置——验证 `--project-root` 覆盖分支真的被走到，
  不是没人调用的死代码。
- `test_launch_and_record_fall_back_to_cwd_when_no_project_root_is_found`：
  全新 git 仓库、不放 `research-loop.json`（先断言
  `_lib.find_project_root(root) is None` 确认夹具真的"未接线"），
  不传 `--project-root`，跑 launch.py 再跑 record.py，两个都在没有配置
  文件的情况下成功完成——验证两脚本在完全未接线的裸仓库里仍可用（`Config`
  在配置文件不存在时退回表里的默认路径，`cfg.ledger_path` 不依赖配置文件
  存在）。

之后跑了全量套件确认没有连带破坏：

```
$ python3 research-loop/tests/run_all.py
...
-- run_all: 153 passed, 0 failed
```

（141 条既有 + 12 条新增 = 153。）

`run.py selfcheck` 未跑：本工单没有改动 `run.py` 注册表（工单范围声明
"不改 run.py / MAP.md"），实现者规程里"改了 run.py 注册表相关的东西才跑
selfcheck"这条不适用；用 `git diff --stat -- run.py MAP.md`（本报告写作
时再次确认）两文件确实零改动。

## commit 清单

- `c6846e2` `T10: research-loop plugin -- fallback five + freeze-legacy` ——
  七个新文件一次提交（registry/launch/record/两个 fake 任务/freezecmd/
  测试文件是同一个功能面——兜底铁轨三件本身就要互相闭环才能自测，freeze-legacy
  虽然逻辑独立但工单把它跟兜底三件放在同一张票、共用同一份测试文件，没有
  再拆的自然边界）。

## 自查发现与存疑

- **timeout 场景 launch.py 自身进程的退出码是我选的哨兵值（1）**：工单
  "退出码透传子进程"这句对正常完成/失败场景literal 成立（`process_exit =
  exit_code`），但超时场景子进程被 kill、`_lib.run_argv` 返回
  `exit_code=None`，没有真实退出码可透传。测试 6 只要求"exit 非 0"，我选
  了 1；如果验收者希望这里用更具体的约定值（比如 shell 里常见的 124，
  `timeout(1)` 命令的惯例退出码），这是可以讨论、不改变任何其他行为的
  一行改动。
- **RUNMETA 写入没有加文件锁**：工单六步原文只给 jobs 登记（step 3）和
  runs 入账（record.py step 5）两处点名"持 `<name>.lock`"，RUNMETA
  没有点名。我用临时文件 + `os.replace` 做原子替换（避免半写坏文件），
  但没有用 `_lib.locked` 防两个并发 launch.py 进程互相踩 attempts 列表
  （读-改-写不是原子的，理论上存在竞态：两个进程同时读到 `attempts` 长度
  1，都算出 `attempt_no=2`，都写 `attempt_no=2` 覆盖对方）。工单测试 5
  是"同一发射单跑两次"但两次调用是顺序的（我的测试也是顺序调用，不是
  并发调用），没有触发这条竞态。如果验收者认为 RUNMETA 也该持锁（跟
  jobs.json/runs.jsonl 同等对待），这是需要回工单或 spec 补一句的点，
  不是我能自行拍板的范围——工单原文六步的字面意思就是只有 jobs 和 runs
  两处点名持锁，我按字面执行了。
- **jobs.json 条目多了 `finished_at: null`（登记阶段）字段**：工单 step 3
  只列 `state=running、launch_order_ref、started_at、log_path` 四个字段，
  没提 `finished_at`；我在登记阶段就把它设成 `null` 占位（收尾阶段
  step 6 再回填真实值），理由是 `plan.md §C5` 给的 jobs 台账形状本来就
  包含 `finished_at` 这个键位，登记阶段先占位、收尾阶段回填是同一个
  字段生命周期的两端，不算多做工单没要的事——如果验收者认为登记阶段
  就不该出现这个键（等收尾时才 `dict.update` 加进去），是可以讨论的
  实现细节，不影响任何测试断言。
- **fake_experiment.py 的 5 行数据 k 从 0 起**：工单"5 行 `{"i": k, "v":
  seed*k}`"没定起始索引，我取 `range(5)`（k=0..4）。没有测试断言具体的
  `i`/`v` 值（只断言行数 n=5 和 acc 的 sha 派生值落在 [0,1) 区间），
  如果验收者期望 k 从 1 起，这也是一行改动，不影响其余任何行为。
- 没有发现需要 `NEEDS_CONTEXT` 或 `BLOCKED` 的缺口：工单给的数值/命名/
  接口签名（六个脚本的参数形状、五种 fake mode 的精确行为、record.py
  五步、freeze-legacy 的两条机验与两个拒绝分支、九条测试清单）都是完整、
  不矛盾的，没有需要用户裁决的地方。Comments 里 2026-08-14 的 T12 对接
  预警（`output_check.py` 按脚本进程 cwd 解析 artifact_dir）已经在
  launch.py/record.py 里落实：两者的 `artifact_dir`/`workdir`/RUNMETA 路径
  统一以 `project_root`（`--project-root` 或 `_lib.find_project_root()`
  或退 `Path.cwd()`）为基准解析，不依赖裸 `Path.cwd()` 单独解析——跟
  `tests/helpers.run_script` 的 `cwd=root` 约定天然对齐，也覆盖了
  `--project-root` 显式给出、cwd 跟项目无关的情形（测试
  `test_launch_accepts_explicit_project_root_when_cwd_differs` 专门验证
  了这条）。本工单没有直接调用 `output_check.py`（T10 范围不包含它），
  这条预警对 T10 而言是"保持同一套路径解析基准"的一致性要求，已经满足。

## 修复轮 1（2026-08-14）

分支：`ticket/20260814-wave4/T10`（复用原分支，工作树
`new1-wt/20260814-wave4-T10-fix1`，已删除）
base（修复前 head）：`c6846e2`

### F1：RUNMETA 读-改-写没有持锁，并发发射静默丢 attempt

**怎么修的**：`launch.py` 里从"读 RUNMETA 算 attempt_no"到"append 完新
attempt 落盘"这整段，原来全程不持锁，现在整段包进
`with _lib.locked(runmeta_file):`。`_lib.locked` 是仓库里已有的
flock 排他锁工具（`ledger.py`/`record.py` 写 `runs.jsonl`、launch.py 自己
写 `jobs.json` 时都在用同一个函数），语义和"jobs 登记持
`<jobs>.lock`"是同一套机制，不是新引入的锁模型。

把锁的粒度定在"整段"而不是"只锁读和只锁写两小段"，是因为 attempt_no
是在跑子进程之前算出来的（要决定 `attempt<N>.log` 的文件名），但真正落盘
的 `attempt` 记录要等子进程跑完才有 `exit_code`/`finished_at`——如果中途
释放锁，另一个并发进程会插进来读到同一份"旧" attempts、算出同一个
attempt_no，问题原样重现，只是窗口从"读到写"缩小成"释放到重新获取"，
没有真正堵上。所以选择让 attempt_no 的决定和最终落盘绑在同一次持锁里，
代价是两个并发跑同一张发射单的进程会互相排队（先到的跑完、写完 RUNMETA，
后到的才能开始跑）——但两个进程本来就是在跑同一条 argv、写同一个
artifact_dir，本该串行，这不是新增的限制，是把之前隐含的"应该串行却其实
在并发写元数据"的错误状态改成"确实串行"。

`jobs.json` 的登记/收尾两处锁保持原来的写法不动（`_lib.locked(jobs_path)`
分别在 RUNMETA 锁内部（登记）和 RUNMETA 锁外部（收尾）各持一次）——原实现
里这两处已经点名持锁，本轮不改它们的粒度，只是登记那次现在嵌套在 RUNMETA
锁内部（登记这个动作本身跟"决定这次是第几个 attempt"发生在同一个时间点，
嵌套没有引入新的锁序：全仓库里没有别的地方先拿 jobs 锁、再去拿
RUNMETA 锁，所以不会死锁）。

改动只涉及缩进重排 + 一段解释性注释 + 模块 docstring 补一句说明，没有改
任何字段形状、任何分支判断、任何返回值——`git diff` 逐行核对过，纯粹是
把已有代码块套进一个 `with` 块。

**怎么验证的**：

新增一条并发回归测试
`test_launch_concurrent_same_order_does_not_lose_an_attempt`
（`research-loop/tests/test_fallback.py`）：给同一张发射单起两个真正并发
的 `subprocess.Popen`（`argv` 换成 `python3 -c "import time;
time.sleep(1)"`，比 `fake-experiment` 的近瞬时执行给并发窗口留出一秒，
足够两个独立进程真正重叠到临界区里），两个都跑完后断言 RUNMETA 里
`attempts` 长度是 2、`attempt_no` 集合是 `{1, 2}`，`jobs.json` 里
`state=done`、`finished_at` 有值。

先在修复后的代码上跑：

```
$ python3 research-loop/tests/run_all.py test_fallback
...
PASS test_fallback.test_launch_concurrent_same_order_does_not_lose_an_attempt
...
-- run_all: 13 passed, 0 failed
```

再临时把 `launch.py` 换回修复前的版本（`git show
c6846e2:research-loop/scripts/fallback/launch.py`），跑同一条新测试 3 次
确认它能稳定复现 F1 描述的症状（不是偶发 flaky）：

```
$ python3 research-loop/tests/run_all.py test_fallback   # x3，均如下
...
  File ".../test_fallback.py", line 327, in test_launch_concurrent_same_order_does_not_lose_an_attempt
    assert len(runmeta["attempts"]) == 2
AssertionError
FAIL test_fallback.test_launch_concurrent_same_order_does_not_lose_an_attempt
-- run_all: 12 passed, 1 failed
```

3 次全部在同一条断言（`len(attempts) == 2`）上失败，实际落盘的
`attempts` 长度是 1——跟 finding 描述的"先完成的那次 attempt 记录被静默
丢弃"完全对应。把 `launch.py` 换回修复后的版本，再跑 3 次全部通过：

```
$ python3 research-loop/tests/run_all.py test_fallback   # x3，均如下
-- run_all: 13 passed, 0 failed
```

最后跑全量套件确认无连带破坏：

```
$ python3 research-loop/tests/run_all.py
...
-- run_all: 154 passed, 0 failed
```

（153 条修复前既有 + 1 条本轮新增 = 154。）

`run.py selfcheck` 未跑：本轮改动不涉及 `run.py`/`MAP.md`
（`git diff --stat -- run.py MAP.md` 输出为空，本工单范围声明本就排除这两
个文件）。

### commit 清单（修复轮 1）

- 分支 `ticket/20260814-wave4/T10` 上追加一条 `T10:` 前缀 commit
  （改 `research-loop/scripts/fallback/launch.py` 加锁范围 +
  `research-loop/tests/test_fallback.py` 加并发回归测试；两文件 diff
  详见 `git show` 该 commit）。

### 自查发现与存疑（修复轮 1）

- F1 是本轮唯一未决 finding，已按上文方式修掉，没有引入新的待裁决点。
- 原报告"自查发现与存疑"里关于 timeout 哨兵退出码（1）、jobs.json
  `finished_at: null` 占位、`fake_experiment.py` 起始索引 k=0 的三条存疑
  与本轮无关，未改动，原样保留供后续验收者裁决。
