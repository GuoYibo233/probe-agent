# T03 — 采集脚本接心跳（`run_appworld.py`）报告

工单：`.scratch/gpu-monitor-launch/issues/03-collect-heartbeat.md`
依赖：01（`ops/heartbeat.py`，main 上已 resolved，commit c890cec）
步骤依据：`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 3（line 390-445）

## 做了什么

对照工单三条验收要求逐条实现，全部落在 `envs/collect/run_appworld.py`：

1. **心跳 import**：`sys.path.insert` 一行之后加了
   `sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))`
   和 `import heartbeat  # noqa: E402`，放在 `from common import Chat, TrajLog`
   之前（第 15-17 行）。

2. **进主循环先打 done=0**：`shard ... exp=...` 那行 print 之后、
   `for tid in ids:` 之前加了
   ```python
   tok_in = tok_out = 0
   n_done = 0
   heartbeat.emit(0, len(ids), "task", tok_in=0, tok_out=0)
   ```
   （第 80-82 行）。`heartbeat.emit` 是 T01 已落地的模块，签名
   `emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None, status=None, stream=None)`。

3. **每题推进 done、累计 token**：
   - `g = chat(msgs)` 之后加了
     `tok_in += g["usage"]["in"]; tok_out += g["usage"]["out"]`
     （第 105-106 行）。`g["usage"]` 的字段名 `in`/`out` 是
     `envs/collect/common.py:161,182,220-221` 现成的，common.py 未改动。
   - resume 的 SKIP 分支（`continue` 之前）加了 `n_done += 1` 和一条
     `heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in, tok_out=tok_out)`
     （第 88-92 行）——工单点名"resume 跳过的题同样推进 done"，这里覆盖到。
   - 每题正常收尾（`print(f"task={tid} steps=...")` 之后）同样加了
     `n_done += 1` + 一条心跳（第 134-138 行）。
   - `main()` 末尾、`for tid in ids:` 循环结束后，加了正常收尾标志：
     `heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in, tok_out=tok_out, status="done")`
     （第 140-141 行）。

三条验收要求（语法检查+--help、每题/SKIP 都推进 done+循环结束 status=done、commit）
全部完成。

## 怎么验证的

工单指定的验证命令是 appworld venv 下跑语法检查和 `--help`（证明心跳模块
在该 venv 里 import 得动，这是"stdlib-only"约束的实测）。

`envs/appworld` 整个目录是 gitignored（venv/data/runs 都不进 git），
`git worktree add` 不会把它带进新工作树，所以 venv 物理上只存在于主仓
`/home/y-guo/reproduce/new1/envs/appworld/venv/`。脚本本身用绝对路径
`os.chdir("/home/y-guo/reproduce/new1/envs/appworld")`，与工作树位置无关，
所以直接指向主仓 venv 跑工作树里的脚本文件是等价的、也是唯一可行的验证方式。

```
$ /home/y-guo/reproduce/new1/envs/appworld/venv/bin/python -c \
    "import ast,sys; ast.parse(open('envs/collect/run_appworld.py').read()); print('syntax ok')"
syntax ok

$ /home/y-guo/reproduce/new1/envs/appworld/venv/bin/python envs/collect/run_appworld.py --help
usage: run_appworld.py [-h] --base-url BASE_URL --model MODEL [--split SPLIT]
                       [--n N] [--max-steps MAX_STEPS] --outdir OUTDIR
                       [--exp EXP] [--api {raw,chat,harmony}]
                       [--reasoning-effort REASONING_EFFORT]
                       [--start-date START_DATE] [--shard-id SHARD_ID]
                       [--num-shards NUM_SHARDS] [--resume]
options:
  ...
```

`--help` 正常打印到底（含所有参数），证明 `import heartbeat` 在
appworld venv（stdlib-only 约束）下成功，没有触发任何 ImportError。

另外跑了 `python3 -c "import py_compile; py_compile.compile(...)"`（复核语法）：
`py_compile ok`。

工单没有点名单测接缝（心跳 emit/parse 的单测已在 T01 覆盖），这次改动
是脚本里插桩调用，没有新增可独立单测的纯函数，因此没有另写测试文件——
按实现者规程"没点名就在改动的边界处补测试"，边界处的验证就是工单指定的
这条 `--help` 实测，已跑过。

`run.py selfcheck` 在这个工作树里跑会报 16 处"缺解释器"（appworld/alfworld/
tau2/toolhop/bfcl 等 venv 全部缺失），原因是这些 venv 目录本身就是
gitignored、未进 git wordktree，不是本次改动引入的问题——在主仓
`/home/y-guo/reproduce/new1` 里跑同一个 `python3 run.py selfcheck`，
结果是"62 任务 / 4 配方, 全部就位"。本工单没有改动 `run.py` 注册表，
不属于"改了注册表相关的东西"的强制门槛，但仍确认过主仓侧 selfcheck 干净。

## commit 清单

- `9838281` — `T03: collect: run_appworld 接心跳(每题 done/累计 token,done=0 标加载完)`
  （工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T03`，分支
  `ticket/20260808-par/T03`，diff 1 file changed, 17 insertions）

## 自查发现与存疑

- 自查完整 diff：只有 `envs/collect/run_appworld.py` 一个文件，17 行新增，
  没有删除或改动既有逻辑行，没有超出工单范围的改动。
- 没有引入新依赖、没有碰 `common.py`（工单明确写了"common.py 不用改"）。
- 没有触碰 `run.py` 注册表——这张工单不需要，`envs/collect/run_appworld.py`
  的调用方式（`python3 run.py collect-aw ...`）没有变化。
- 存疑点：`heartbeat.emit` 的 `tok_in`/`tok_out` 传的是"这一刻的累计值"
  而不是增量，这与心跳协议"tok_in/tok_out 都是累计值"的定义（spec.md
  "心跳协议"一节）一致，写法上没有歧义，记在这里是为了让评审知道我确认过
  这一点而不是漏看。
- 没有其他存疑；未触发 NEEDS_CONTEXT 或 BLOCKED 条件。
