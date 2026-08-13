# T10 fallback 铁轨五件 + freeze-legacy

Status: claimed
Blocked by: 03

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + `tables/config.json` `_fallback_rule`（兜底最低必做项原文）+
`tables/rows.json`（runmeta、structured_output_contract、runs_row_normal
含 `_dup_rule`/`_run_level_fields`、enums fake.mode）+
`tables/writes.json` maintenance_exempt.freeze-legacy + spec.md §3 R7、§5。
fallback 脚本开头统一三行 sys.path 垫片以 import `_lib`。

## 文件

- Create: `research-loop/scripts/fallback/registry.py`
- Create: `research-loop/scripts/fallback/launch.py`
- Create: `research-loop/scripts/fallback/record.py`
- Create: `research-loop/scripts/fallback/fake_experiment.py`
- Create: `research-loop/scripts/fallback/fake_metrics.py`
- Create: `research-loop/scripts/ledger_cmds/freezecmd.py`
- Create: `research-loop/tests/test_fallback.py`

## 要求

### registry.py（极简注册表 + --list 只读免门禁）

内置任务表：`fake-experiment` → [sys.executable, <同目录>/fake_experiment.py]、
`fake-metrics` → [sys.executable, <同目录>/fake_metrics.py]。
`--list`：打任务名一行一个，零副作用；`registry.py <task> [args…]`：
subprocess 转发、透传退出码；未知任务 stderr 报错 exit 4。

### launch.py LAUNCH_ORDER.json [--project-root P]

顺序执行发射单 argv + 脏树检查 + 写 RUNMETA + 登记极简台账（_fallback_rule
最低必做项）：

1. 读发射单。脏树检查：workdir 所在 git 仓 `git status --porcelain`，
   路径过 config dirty_exempt_globs（fnmatch）后仍非空 → exit 3
   `refuse to launch: dirty tree; escalate to deploy layer`（无放行旗标）。
2. expected_commit 校验：git_head(工程根) 去掉 -dirty 前的比对基（脏树已在
   上一步拒）≠ expected_commit → exit 3；`no-git` == `no-git` 放行（自测沙盒）。
3. jobs 登记（`ops/jobs.json`，plan.md §C5 形状，持 `<jobs>.lock`）：
   state=running、launch_order_ref、started_at、log_path。
4. `run_argv(argv, cwd=workdir, timeout=expected_runtime_s ×
   config.runtime_factor)`；stdout+stderr 落
   `<artifact_dir>/attempt<N>.log`；超时杀进程 → state=timeout。
5. RUNMETA（`<artifact_dir>/RUNMETA.json`）：{commit, argv, dirty_files: [],
   launch_order_ref: 发射单路径, attempts: [...], env_name, outputs: []}；
   已存在则**只追加 attempts 一条**（attempt_no 递增；前条的 argv/log_path/
   resources 一字节不动），顶层其余字段保留首次值。
   attempt 条目 = {attempt_no, argv, exit_code, log_path, resources,
   started_at, finished_at}（rows.json runmeta.attempts 原文形状）。
6. jobs 收尾：state=done（exit 0）/failed/timeout + finished_at。
   退出码透传子进程。

### record.py --launch-order PATH [--status S]（兜底普通行入口）

1. 读发射单 + `<artifact_dir>/RUNMETA.json`（缺 → exit 2）。
2. status：--status 给了用给的；缺省按最后一条 attempt 的 exit_code==0 → ok
   否则 failed。
3. status=ok：`split_cmd(metrics_cmd)` 跑（不经 shell），
   `last_json_line` 必须给 {"metrics": [...]} 非空数组，否则 exit 2
   `refuse: metrics output invalid; no row recorded; escalate per R8`
   （metrics 空数组或非数组同拒——§9）。一项 metric 一行：
   {run_id, status, output_dir=artifact_dir, runmeta_path, metric_name,
   value, n, filter（metric 项缺省取发射单 filter）, seed, dataset_version,
   batch_id, arm, quick, principle_id: null, commit: null,
   elapsed_s（末条 attempt 的起止差，秒整数）, gpu_count
   （resources.gpus 或 null）, recorded_at=now_iso(), schema_version: 1}。
4. status≠ok：单行，metric_name/value/n 全 null（schema conditional 放行）。
5. 每行过 runs.normal schema（validate 单入口）；同主键
   (run_id, metric_name, filter) 跨档查重 → 拒；同 run_id 已有行的
   run 级字段（`_run_level_fields` 清单）不一致 → 拒；
   全部行**一次锁内写完**（`<runs路径>.lock`，与 runs-append 同名协议）。

### fake_experiment.py --seed N --mode M --out DIR

mode 值域 = enums["fake.mode"]。写 `DIR/mode.txt`=M。
ok/bad-metrics：写 `DIR/result.jsonl` 5 行 `{"i": k, "v": seed*k}`，exit 0；
fail：stderr `simulated failure`，exit 1；
empty：建空 result.jsonl，exit 0；
timeout：sleep 30 后 exit 0（发射侧超时先杀）。

### fake_metrics.py --dir DIR

读 mode.txt：bad-metrics → stdout 尾行 `this is not json`，exit 0；
其余 → 尾行 JSON：metrics=[{metric_name: "acc", value: 由 result.jsonl
字节 sha256 决定的确定值（int(sha,16)%1000/1000）, n: 行数, filter: null},
{metric_name: "rows", value: 行数, n: 行数, filter: null}]。
同字节输入 → 逐字节相同输出（§9 场景③的一致性来源）。

### freeze-legacy --confirm（freezecmd.py，不收 --layer）

legacy 路径 = runs 路径同目录 `runs.legacy.jsonl`（optional_ledgers 默认）。
已存在 → exit 1 `freeze-legacy already done; repeat refused`。
无 --confirm → 打印将做什么，exit 1。执行：字节拷贝 → sha256 比对
（legacy == 原文件，机验①）→ 主文件清零 → 主文件 0 字节复核（机验②）→
stdout 提醒把 runs_legacy 补进 config 的 ledgers+owners 两处键。

## 测试（test_fallback.py，全部走 make_git_sandbox）

1. registry --list 出两个任务名；未知任务 exit 4。
2. launch ok：jobs 行 done、RUNMETA 齐、attempt1.log 存在、退出 0。
3. 脏树拒 exit 3；脏文件命中 dirty_exempt_globs → 放行。
4. expected_commit 错 → exit 3。
5. 同一发射单跑两次：attempts 长度 2、attempt1 的 argv 与 log_path 原封未动。
6. timeout mode + expected_runtime_s=1：state=timeout、exit 非 0（3 秒左右完）。
7. record ok：两个 metric 两行、run 级字段逐字相同、都过 schema；
   重复 record → 同主键拒；--status empty-output → 单行三 null 字段。
8. bad-metrics：record exit 2、runs 无新行。
9. freeze-legacy：两条机验过、重复执行拒、传 --layer 被 argparse 拒。

## Comments

- 2026-08-14 预警（T12 落地后的对接契约）：output_check.py 把发射单里的
  artifact_dir 按**本脚本进程的 cwd** 解析（相对路径时）。本工单的
  launch.py/record.py 若调用 output_check 或按发射单解析 artifact_dir，
  统一以工程根为 cwd（与 tests/helpers.run_script 的 cwd=root 约定一致），
  或直接在发射单里写绝对路径；两边解析基准不一致会静默指向错目录。
