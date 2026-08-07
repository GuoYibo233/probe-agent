# T04 报告 — 四个训练脚本接心跳

工单：`.scratch/gpu-monitor-launch/issues/04-train-heartbeat.md`
分支：`ticket/20260808-par/T04`，base `5be5d0827fe959cc1c016c8f99221c4d6a4218c8`

## 做了什么

对照工单四条验收要求，逐条落实。步骤照 `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 4（行 449-491）执行，锚点先用 `grep -n "event=\"start\"\|event=\"step\"\|event=\"done\"\|steps ="` 现查，四个文件行号与计划文档给的略有出入（后三格计划文档只给了 mtool 的锚点，其余"照同一模式重复"），实际锚点：

| 文件 | start | step | done | steps 变量 |
|---|---|---|---|---|
| `pipeline/train/train_mbert_tool.py` | 185 | 207-210 | 222 | 172 |
| `pipeline/train/train_mbert_extract.py` | 467-474 | 516-519 | 545-546 | 453 |
| `pipeline/train/train_causal_tool.py` | 366-371 | 392-396 | 417 | 353 |
| `pipeline/train/train_causal_callgen.py` | 426-434 | 466-469 | 496 | 413 |

四个文件同一模式，各插四处：

1. import 区加（`import readonly_map`/最后一个模块内 import 之后）：
   ```python
   import sys as _sys
   from pathlib import Path as _Path
   _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
   import heartbeat
   ```
   四个文件均已有裸 `from pathlib import Path`（部分还有裸 `import sys`），用 `_sys`/`_Path` 别名避免遮蔽，与计划文档给的插入片段一致。

2. `log(event="start", ...)` 调用结束后加 `heartbeat.emit(0, steps, "step")`——一条 done=0 的心跳，标"模型加载完了"。

3. `gstep % 50 == 0` 分支里 `log(event="step", ...)` 调用之后、`run = 0.0` 复位**之前**加：
   ```python
   heartbeat.emit(gstep, steps, "step",
                  loss=round(run / (50 * args.accum), 4))
   ```
   loss 表达式逐文件照抄该文件 `log(event="step")` 里已有的那份滑动均值算式（四个文件算式相同：`run / (50 * args.accum)`），不是另起一份。

4. `log(event="done", ...)` 调用之后加 `heartbeat.emit(gstep, steps, "step", status="done")`。

- [x] 四个文件语法检查通过
- [x] mbert-env 和 cprobe-env 两个训练 venv 都能 import 心跳模块
- [x] loss 取的是各文件 step 日志里已有的那份滑动均值，插在复位之前
- [x] commit

## 怎么验证的

**语法检查**（工单要求 + 计划文档 Step 3）：

```
$ for f in pipeline/train/train_*.py; do python3 -c "import ast; ast.parse(open('$f').read())" && echo "$f ok"; done
pipeline/train/train_causal_callgen.py ok
pipeline/train/train_causal_tool.py ok
pipeline/train/train_mbert_extract.py ok
pipeline/train/train_mbert_tool.py ok
```

**两个训练 venv import 心跳模块**：worktree 里没有 `mbert-env/`、`cprobe-env/`（这两个目录被 `.gitignore` 排除，`git worktree add` 不带未跟踪文件），改用主仓的 venv 解释器、把 `sys.path` 指向 worktree 里的 `ops/` 目录来测——`heartbeat.py` 本身这次没改动，测的是"这个 venv 能不能 import 心跳模块"这件事，和它物理落在哪个目录无关：

```
$ mbert-env/bin/python -c "import sys; sys.path.insert(0,'/home/y-guo/reproduce/new1-wt/20260808-par-T04/ops'); import heartbeat; print('mbert-env import ok', heartbeat.__file__)"
mbert-env import ok /home/y-guo/reproduce/new1-wt/20260808-par-T04/ops/heartbeat.py

$ cprobe-env/bin/python -c "import sys; sys.path.insert(0,'/home/y-guo/reproduce/new1-wt/20260808-par-T04/ops'); import heartbeat; print('cprobe-env import ok', heartbeat.__file__)"
cprobe-env import ok /home/y-guo/reproduce/new1-wt/20260808-par-T04/ops/heartbeat.py
```

**diff 自查**：`git diff --stat` 显示四个文件各改动 9 行（4 处插入，每处 1-2 行），未改动任何既有逻辑、既有 `log()` 调用、既有变量。逐文件核对了 `heartbeat.emit(gstep, ...)` 在 `run = 0.0` 之前的行序。

未涉及 `run.py` 注册表，未跑 `selfcheck`（工单与计划都没要求，改动范围内也没有新增/改动任务）。

## commit 清单

- `f4b9f67` — `T04: 四格训练脚本接心跳(unit=step,报滑动 loss)`：四个训练脚本各加 4 处 `heartbeat.emit` 调用，共 36 行新增，无删改。

## 自查发现与存疑

- 计划文档 Task 4 的行号只给了 `train_mbert_tool.py` 一份，其余三个文件写"其余三格照同一锚点重复"、"变量名以各文件实际为准"。本次按工单要求现场 `grep` 取锚点，四个文件的 `log(event="step")` 里 loss 算式恰好都是 `run / (50 * args.accum)`，未发现取值口径不一致的情况。
- `train_causal_tool.py`、`train_causal_callgen.py` 两个文件顶部已有裸 `import sys`；插入的 `import sys as _sys` 与计划文档给的片段字面一致，用别名避免和已有 `sys` 冲突，未改动任何已有 `sys` 用法。
- 无其余存疑点。
