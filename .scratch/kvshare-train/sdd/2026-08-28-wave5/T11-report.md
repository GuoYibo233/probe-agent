# T11 报告:学习率扫描的驱动与报表 `pipeline/train/sweep_lr.py`

工单:`.scratch/kvshare-train/issues/11-sweep-lr.md`
分支:`ticket/2026-08-28-wave5/T11`,commit `540d06b`,base `073382cbf2f636bf639ef9f2721d28cf1efa1ba2`。

## 做了什么

对照工单逐条:

1. **`pipeline/train/sweep_lr.py`,两个子命令。**
   - `plan [--grid <json>] [--data <dir>] [--out-root <dir>] [--py <python>] [--track kvshare-lr-sweep] [--write <plan.json>]`:
     网格常量 `GRID`(工单初值:`b06` qwen 全参 `[1e-5,5e-5,2e-4]` 16384 Ada
     `["--grad-ckpt"]`;`b17` qwen17 全参同上 16384 H200 `[]`;`l17` qwen17
     LoRA `[1e-4,5e-4,2e-3]` 16384 H200 `[]`;`l4` qwen4 LoRA 同上 16384 H100
     `["--grad-ckpt"]`)生成 12 条 run。run_id = `ks828<tag>_gptoss_cgen_lr<lr>`,
     `<lr>` 由 `fmt_lr()`(`f"{lr:.0e}"` 去掉指数前导零)得到。命令按工单给定
     顺序拼:`--mode cgen --base <base> --env appworld --data <data 绝对路径>
     --out <out 绝对路径> --lr <lr> --tok-budget <tb> --epochs 1
     --eval-per-epoch 4 --log-every 10 --mem-probe` 加 `--lora`(为真时)加
     `extra`。`--data` 默认 `pipeline/data/nyapass_aw_v1/gptoss`、`--out-root`
     默认 `pipeline/runs/sweep`,两者都解析成绝对路径写进命令;`--py` 默认
     `<仓库根>/cprobe-env/bin/python`(仓库根 = `Path(__file__).resolve().parents[2]`)。
     生成后自检 run_id 两两不同,撞车(如网格塞进 `1.2e-5`,`fmt_lr` 只留一位
     有效数字会与 `1e-5` 撞)`SystemExit` 并打印撞车两条(含 tag、lr 原值)。
     stdout 先打 Markdown 表(`run_id | tag | base | lora | lr | tok_budget |
     card | extra`),再打提示「把 --piece 占位换成排卡表里的实际卡」,然后
     12 行 `python3 run.py launch --cmd '<cmd>' --run-id <run_id> --track
     <track> --outdir <out> --piece <host>:<gpu>`(`shlex.quote` 整条训练命令
     字符串,`--piece` 占位符原样打印)。`--grid` 给 JSON 文件时整体替换
     `GRID`。`--write` 给了就落 JSON 数组(每条 `run_id, tag, base, lora, lr,
     tok_budget, card, cmd, outdir`)。
   - `report --runs <路径或 glob,nargs="+"> --out <目录>`:每个 run 目录读
     `train_log.jsonl`。`start` 事件取 `base, lora`(键在不在)`, lr,
     tok_budget, n_train_events, dropped_events_train`;全部 `eval` 事件取
     `frac, val_ce`,以及 `val_exact_call` 或 `val_exact_params`(两个键都不在
     写 `null`);`done` 取 `best_val_ce, best_frac, wall_s`;`step` 事件里
     `peak_mem_gb` 的最大值;`worst_gb` 优先取 `mem_probe_summary` 事件,没有
     就退化到取各 `mem_probe` 事件 `peak_mem_gb` 的最大值,再没有写 `null`。
     分组键 `(base, lora)`,组内按 lr 升序。写 `<out>/SWEEP_REPORT.json`(每条
     上述字段加 `run_id, status`)与 `<out>/SWEEP_REPORT.md`(表头 `run_id |
     lr | val_ce@<ep>.<frac>…(全部 run 出现过的 (ep,frac) 组合,动态生成、
     升序)| best_val_ce | best_frac | val_exact(best) | peak_mem_gb |
     worst_gb | wall_s | status`;`status` 是 `done` 或 `running`,running 的
     行 best 列写目前为止最低的 eval;每组 best_val_ce 最低的一行在 run_id
     前加 `*`)。表前一行写生成时间与读取目录数,表后不写结论句。目录下
     找不到 `train_log.jsonl` 打一行警告到 stderr 并跳过,不报错。

2. **`run.py` `TASKS` 加 `"sweep-lr"`**:`stage="train", py="cprobe",
   script="pipeline/train/sweep_lr.py"`,`desc` 与 `notes` 按工单要求(两个
   子命令用法、`GRID` 常量位置、发射仍走 gpu-run);字段集照
   `gen-toolhop-splits` 先例(stage/py/script/desc/notes),不写 `gpu` 键。

3. **`tests/test_sweep_lr.py`**(纯 CPU,不 import torch):
   - `TestFmtLr`:六个学习率值的格式化(`1e-05→1e-5` 等六个例子)。
   - `TestPlan`:默认 `GRID` 出 12 条不重复 run_id,每条 `cmd` 含正确的
     `--lr` 与 `--log-every 10`,`lora` 为真/假的 `--lora` 有/无,`outdir` 以
     run_id 结尾;CLI 层面 `main(["plan", "--write", ...])` 打 12 行
     `python3 run.py launch` 且每行含 `--piece <host>:<gpu>` 占位,写出的
     JSON 9 个字段齐全;给一个含 `1e-5` 与 `1.2e-5` 的 `--grid` 时
     `SystemExit`。
   - `TestReport`:手造两个 run 目录(一个 `start`+4 条 `eval`+`done`+2 条
     `step`+`mem_probe_summary`,一个只有 `start`+1 条 `eval`),`report` 出
     JSON 两条、`status` 各是 `done`/`running`、running 行的 `best_val_ce`
     等于它唯一一条 eval 的值、Markdown 里 done 那行(`best_val_ce` 更低)
     标 `*` 而 running 那行不标、`val_ce@` 动态列数等于两个目录出现过的
     `(ep, frac)` 并集大小(4);另一个用例验证目录下没有 `train_log.jsonl`
     时 `report` 返回 0、跳过、JSON 是空列表。

**没做的/超出范围的**:不改训练器(`train_causal_share.py` 零改动)、不改
`MAP.md`(工单点明归工单 12)。

## 怎么验证的

```
cd <worktree>
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_sweep_lr -v
```
```
Ran 6 tests in 0.007s
OK
```
(六个用例:`test_examples` `test_default_grid_twelve_unique_rows`
`test_cli_plan_prints_twelve_launch_lines_and_writes_json`
`test_grid_with_colliding_lr_exits`
`test_report_two_runs_status_star_and_columns`
`test_missing_train_log_is_skipped_not_error`。cprobe-env 不在这台 worktree
里,用主仓的解释器二进制、cwd 切到 worktree 跑。)

```
python3 -m unittest tests.test_sweep_lr -v
```
```
Ran 6 tests in 0.006s
OK
```
(系统 python3 同样全绿,脚本不 import torch。)

```
python3 run.py selfcheck
```
worktree 里没有任何 venv(它们不进 git),原样跑出 15~16 处「缺解释器/缺
脚本」,全部是 `cprobe-env` `mbert-env` `envs/*/venv` 这类未跟踪目录缺失,
与本工单改动无关——`sweep-lr` 本身不在缺失清单里。临时把这些目录从主仓
`/home/y-guo/reproduce/new1/` 软链进 worktree(诊断用,验完就删,没有进
commit)复核一次:
```
selfcheck: 77 任务 / 4 配方 / 3 预设, 全部就位
```
删软链后 `git status --porcelain` 干净(只剩本工单的三个改动文件),确认
诊断没有污染分支。

回归测试(改了 `run.py` 注册表,跑了受它影响的几个用例做兜底,没有全量跑
discover——那需要各环境的 venv,不在本工单范围):
```
python3 -m unittest tests.test_sweep_lr tests.test_launch_cmd tests.test_gpu_jobs tests.test_driver -v
```
```
Ran 144 tests in 4.615s
OK
```

CLI 手测:
```
python3 pipeline/train/sweep_lr.py plan
```
打出 12 行表格、12 行 `python3 run.py launch ...--piece <host>:<gpu>`,人工
核对四个配置各三个 lr、run_id 命名、`--lora` 有无、`extra` 拼接均与工单口径
一致(`ks828b06_gptoss_cgen_lr1e-5` … `ks828l4_gptoss_cgen_lr2e-3` 共 12 个,
两两不同)。

```
python3 pipeline/train/sweep_lr.py plan --write /tmp/t11_plan_check.json
```
落盘 12 条,每条含 `run_id, tag, base, lora, lr, tok_budget, card, cmd,
outdir` 九个字段。

## commit 清单

- `540d06b` — T11: 学习率扫描驱动与报表 `pipeline/train/sweep_lr.py`(plan/report),注册 `sweep-lr`(单一逻辑单元:新脚本 + 新测试 + `run.py` 注册表条目)。

## 自查发现与存疑

- 自查时发现 `build_plan()` 有一个未使用的 `track` 形参、文件顶部有一个未使用的 `import re`(最初打算用正则做 `fmt_lr`,后来改成字符串切片实现),当场删掉了两处,连带更新了调用点与测试。
- 工单第 1 条对 `--write` JSON 字段的描述(`run_id, tag, base, lora, lr, tok_budget, card, cmd, outdir` 九个字段)与 spec 16.6 原文(`run_id, cmd, outdir, card, tag, lr` 六个字段)不一致;按实现者规程「工单文件是唯一需求源」,以工单九字段为准实现——这不是歧义或缺信息,是工单在 spec 基础上做了补充,没有停下的必要,但记在这里供合并时核对。
- `report` 输出 JSON 里每条 eval 记录用的键名是我自定的 `ep/frac/val_ce/val_exact`(工单原话是「取 frac, val_ce, val_exact_call(或 val_exact_params)」,没有钦定输出 JSON 里这一层的字段名,只钦定了要取哪些源键)。`val_exact` 是从源事件的 `val_exact_call` 或 `val_exact_params`(键不在时另一个)取来的统一字段,没有另外在顶层输出 `val_exact_call`/`val_exact_params` 两个键。这是我在没有更明确依据时做的实现选择,不是对工单的偏离,但因为不是工单文本直接给出的名字,列在这里说明依据,供其他工单(尤其是要读这份 JSON 的下游代码)对齐命名时参考。
- `SWEEP_REPORT.json` 每条记录额外带了一个下划线前缀的内部字段 `_best_ep`——不对,写 JSON 前已经过滤掉了(`cmd_report` 里 `json_records` 是排除 `_best_ep` 后的版本),只在内存里传递给 Markdown 生成那一步找 `val_exact(best)` 用,最终产物 JSON 干净,没有多出字段。
- 没有跑 GPU、没有碰训练器,`plan` 打出来的命令没有实际发射验证过(工单范围内本就不做这件事,由主会话走 gpu-run 冒烟)。

## 修复第 1 轮(F1)

工作树:`/home/y-guo/reproduce/new1-wt/2026-08-28-wave5-T11-fix1`,检出已有分支
`ticket/2026-08-28-wave5/T11`(检出前 HEAD `540d06b`)。

### 待修 finding

- **F1(important)**:`summarize_run()` 里 `worst_gb` 的三条取值路径——优先
  `mem_probe_summary.worst_gb`,其次退化到各 `mem_probe` 事件
  `peak_mem_gb` 最大值(工单第 1 条明文要求的兼容旧探针分支),都没有写
  `null`——测试只覆盖了第一条(`_make_done_run` 带 `mem_probe_summary`)和
  第三条(`_make_running_run` 完全没有显存事件),中间那条 `elif
  mem_probes: ...` 分支从未被任何用例触发。评审已确认该分支本身取值正确
  (不是功能性 bug),纯粹是缺测试覆盖。

### 怎么修的

生产代码 `pipeline/train/sweep_lr.py` 未改动——`elif mem_probes:` 分支的
逻辑本身没有问题,不需要根因修复,需要补的是测试。

在 `tests/test_sweep_lr.py` 的 `TestReport` 里新增:

- `_make_run_with_mem_probe_events_only()`:手造一个只含 `start` + 一条
  `eval` + 两条 `mem_probe`(`peak_mem_gb` 分别 18.3、21.5,无
  `mem_probe_summary`)的 run 目录。
- `test_worst_gb_falls_back_to_mem_probe_max_without_summary()`:对这个目录
  直接调 `SL.summarize_run(d)`,断言 `rec["worst_gb"] == 21.5`(两条
  `mem_probe` 里的最大值),把之前零覆盖的 `elif` 分支钉住。

未触及 `plan` 子命令、`run.py` 注册表、`MAP.md`,不属于本轮 finding 范围。

### 怎么验证的

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave5-T11-fix1
python3 -m unittest tests.test_sweep_lr -v
```
```
test_examples (tests.test_sweep_lr.TestFmtLr) ... ok
test_cli_plan_prints_twelve_launch_lines_and_writes_json (tests.test_sweep_lr.TestPlan) ... ok
test_default_grid_twelve_unique_rows (tests.test_sweep_lr.TestPlan) ... ok
test_grid_with_colliding_lr_exits (tests.test_sweep_lr.TestPlan) ... ok
test_missing_train_log_is_skipped_not_error (tests.test_sweep_lr.TestReport) ... ok
test_report_two_runs_status_star_and_columns (tests.test_sweep_lr.TestReport) ... ok
test_worst_gb_falls_back_to_mem_probe_max_without_summary (tests.test_sweep_lr.TestReport) ... ok

Ran 7 tests in 0.011s

OK
```
(系统 python3;6 条旧用例全绿,新增第 7 条覆盖 F1。)

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_sweep_lr -v
```
```
Ran 7 tests in 0.010s

OK
```
(worktree 里没有 `cprobe-env`,用主仓的解释器二进制、cwd 切到 worktree
跑,验收里点名的两个解释器都过。)

回归(改动是测试文件,`run.py` 注册表本身没动,仍按上一轮的同一组用例复核
一遍兜底):
```
python3 -m unittest tests.test_sweep_lr tests.test_launch_cmd tests.test_gpu_jobs tests.test_driver -v
```
```
Ran 145 tests in 4.537s

OK
```
(上一轮同一组是 144 条,本轮多出的 1 条就是新增的 F1 用例;其余 144 条
结果与上一轮一致,均为 `sweep-lr` 之外任务打印到 stdout 的无关日志噪音,
非失败。)

### commit 清单

- `e0677fc` — T11: 补测 worst_gb 兼容旧探针分支(F1)(单一改动:
  `tests/test_sweep_lr.py` 新增一个 run-目录构造器 + 一条测试,生产代码零
  改动)。

### 自查发现与存疑

- 逐行核对本轮 diff:只加了 `tests/test_sweep_lr.py` 里的一个 helper 方法
  和一条测试方法,27 行全部是新增,没有改动或删除既有代码,没有涉及
  `plan`、`run.py`、`MAP.md`,没有超出 F1 范围的改动。
- 新测试直接调用 `SL.summarize_run()`(模块级公开函数),没有走完整的
  `report` CLI 往返——这样能精确隔离 F1 点名的那条 `elif` 分支,不受
  `cmd_report` 里其他逻辑(分组、动态列、Markdown 拼装)干扰,判断这样测更
  贴合 finding 的诉求(finding 原话是「隔离环境里手造了一个只含
  mem_probe 事件的 run_log 验证」,与直接调 `summarize_run` 是同一种验证
  方式)。
- 没有发现新的 finding。
