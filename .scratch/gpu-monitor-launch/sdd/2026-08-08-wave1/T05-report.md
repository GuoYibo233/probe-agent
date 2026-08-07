# T05 — 三个评测脚本接心跳

工单：`.scratch/gpu-monitor-launch/issues/05-eval-heartbeat.md`
实施计划锚点：`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 5（行 495-515）
分支：`ticket/20260808-par/T05`；工作树：`/home/y-guo/reproduce/new1-wt/20260808-par-T05`（已删除，分支保留）
base：`5be5d0827fe959cc1c016c8f99221c4d6a4218c8`
head：`b8cda45`

## 做了什么

工单四条要求：三文件接心跳（工具评测、mbert 调用评测、causal 调用评测）、
unit=item、批循环前 done=0、跟着已有进度 print 打心跳（没有的按 50 批补）、
写完报告后 status=done、多段循环的脚本只留一根进度轴。逐条对照：

**`pipeline/eval/eval_tool.py`**（工具评测，锚点计划里给的是 `:69` 的
`print(f"scored {i}/{len(rows)}")`）。这个文件里存在两类循环：`score()`/
`score_causal()`（对每个 split 跑模型打分，逐批打印进度——这是计划锚点指向
的那一段）和 `replay`/`bootstrap`/`economics`（θ 扫描与置信区间，纯 CPU
字典操作，没有进度 print）。按计划原文"eval_tool 有 score 段和 replay 段,
以最长的那段为进度分母,其他段不打心跳"，只在 `score()`（mbert 分类头路径）
和 `score_causal()`（因果探针路径，两者按 `--head` 互斥,一次运行只走一条）
里接心跳，replay/bootstrap 段完全不接。

- `score()`：函数入口 `heartbeat.emit(0, len(rows), "item")`；原有的
  `print(f"scored {i}/{len(rows)}")`（每 50 批一次）后面跟
  `heartbeat.emit(i, len(rows), "item")`。
- `score_causal()`：入口 `heartbeat.emit(0, len(events), "item")`（分母是
  events 数,跟原有 print 用的分母一致,不是 rows 数）；原有每 25 批一次的
  print 后跟 `heartbeat.emit(s, len(events), "item")`。
- `main()` 里 `test` 堆的行数 `rows_t` 在写完 `REPLAY_REPORT.md` 之后一定
  可取（因为 `test` 是所有口径下 split_names 的最后一个,且非 early-return
  分支下必跑），于是在报告文件写完之后加
  `heartbeat.emit(len(rows_t), len(rows_t), "item", status="done")`。
  `--adopt-logits-fingerprint` 那个提前 `return` 的工具性分支（只补 logits
  指纹档,不跑评测）没有接心跳——它不进入 score 段,也不是这张工单要盯的
  长程评测路径。

**`pipeline/eval/eval_mbert_call.py`**（mbert 调用评测,锚点 `:127` 的
`print(f"extracted {i}/...")`，在 `run_extractor()` 里）。这个文件同样有
两类循环：`run_extractor()`（老口径路径 `extract_points()` 必调，及
`--self-fire` 分支再调一次）和 `score_fire()`（只在 `--self-fire` 时对
val/test 各跑一次开火打分,自成一段）。只在 `run_extractor()` 接心跳，
`score_fire()` 不接——避免同一个脚本里跑出两根轴。

- `run_extractor()`：入口 `heartbeat.emit(0, len(items), "item")`；原有
  每 20 批一次的 print 后跟 `heartbeat.emit(i, len(items), "item")`。
- `main()` 里主提取遍历的计数 `cnts`（`per_ev, cnts = extract_points(...)`）
  在函数末尾仍在作用域内,用 `cnts["n_par"]` 当作 status=done 的 done/total：
  写完 `EXTRACT_REPORT.md` 之后 `heartbeat.emit(cnts["n_par"], cnts["n_par"],
  "item", status="done")`。`cnts["n_par"]` 在 `--readonly-env` 下无触发事件
  时可以是 0,`heartbeat.emit(0, 0, "item", status="done")` 本身不报错
  （verdicts.py 的已完成判定优先看 `status=="done"`,`total=0` 不会绕过它）。

**`pipeline/eval/eval_causal_call.py`**（causal 调用评测,计划给的锚点是
`:207` 的批循环并注明"没有现成进度 print"——但当前代码这个循环里其实已经
有一行 `print(f"generated {min(i+bs,len(prompts))}/{len(prompts)}",
flush=True)`，每批都打,不是"每 50 批"。计划写这份文档时这行 print 大概
还没加,这次直接顺着现状的锚点走,不额外造节奏）。同样两类循环：
`generate()`（老口径必调,`--self-fire` 分支再调一次）与 `score_fire()`
（只在 `--self-fire`）。只接 `generate()`。

- `generate()`：入口 `heartbeat.emit(0, len(prompts), "item")`；原有的
  逐批 print 后面跟 `heartbeat.emit(min(i+bs, len(prompts)), len(prompts),
  "item")`（沿用 print 自己算好的 done 值,没有另起一份计数）。
- `main()` 里 `n = len(per_ev)`（判分后的事件数,老口径路径下就是本次评测的
  规模）在函数末尾仍在作用域内,写完 `CALLGEN_REPORT.md` 之后
  `heartbeat.emit(n, n, "item", status="done")`。

三个文件都只加了 heartbeat 相关的行（import + 心跳调用），没有改动任何
既有评测口径、判分逻辑、字段名或输出格式。

## 怎么验证的

**语法检查**（工单验收项 1）：

```
$ for f in pipeline/eval/eval_tool.py pipeline/eval/eval_mbert_call.py pipeline/eval/eval_causal_call.py; do python3 -c "import ast; ast.parse(open('$f').read())" && echo "$f ok"; done
pipeline/eval/eval_tool.py ok
pipeline/eval/eval_mbert_call.py ok
pipeline/eval/eval_causal_call.py ok
```

**heartbeat 模块的 import 路径与 emit/parse 往返**（在这个工作树里没有
mbert-env/cprobe-env 这两个 venv——`.gitignore` 里 `*-env/` 排除,git
worktree 只带 git 追踪的文件,所以没法真跑三个评测脚本本体；用一段独立脚本
照抄脚本里 `sys.path.insert(..., parents[2] / "ops")` 的写法验证路径解析
与心跳格式）：

```
$ python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('pipeline/eval/eval_tool.py').resolve().parents[2] / 'ops'))
import heartbeat
import io
buf = io.StringIO()
heartbeat.emit(0, 10, 'item', stream=buf)
heartbeat.emit(5, 10, 'item', stream=buf)
heartbeat.emit(10, 10, 'item', status='done', stream=buf)
print(buf.getvalue())
print('parse:', [heartbeat.parse(l) for l in buf.getvalue().splitlines()])
"
@hb {"done": 0, "total": 10, "unit": "item", "ts": 1786139797.2}
@hb {"done": 5, "total": 10, "unit": "item", "ts": 1786139797.2}
@hb {"done": 10, "total": 10, "unit": "item", "ts": 1786139797.2, "status": "done"}

parse: [{'done': 0, 'total': 10, 'unit': 'item', 'ts': 1786139797.2}, {'done': 5, 'total': 10, 'unit': 'item', 'ts': 1786139797.2}, {'done': 10, 'total': 10, 'unit': 'item', 'ts': 1786139797.2, 'status': 'done'}]
```

`parents[2]` 对 `pipeline/eval/*.py` 落在仓库根,`ops/heartbeat.py`
在这个仓库根布局下可正常 import——三个文件用的是同一条路径表达式。

**`python3 run.py selfcheck`**：在这个工作树里跑出 16 处"缺解释器/程序"
（`mbert-env`、`cprobe-env`、`envs/*/venv` 等）,在主工作树（未改动）跑
`selfcheck` 是"62 任务 / 4 配方,全部就位"。这些 venv 目录被 `.gitignore`
按 `*-env/` 排除,`git worktree add` 只签出 git 追踪的文件,新工作树里
本来就没有这些 venv——是工作树本身的环境缺口,不是这次改动引入的注册表
问题。这张工单没有改 `run.py` 或任何注册表条目,三个评测脚本本来就在
`run.py` 里已注册,这次只是给脚本内部加了心跳调用。

**没有跑的**：三个脚本本体的真实执行（需要 GPU、mbert-env/cprobe-env、
已训练的 run 目录）。实现者规程禁止发射 GPU 进程,这条工单本身也不要求
跑通评测——验收项只有语法检查、"一根进度轴"、commit 三条。

## commit 清单

- `b8cda45` — `T05: eval: 三个评测脚本接心跳(unit=item)`
  （`pipeline/eval/eval_tool.py`、`eval_mbert_call.py`、`eval_causal_call.py`，
  共 +20 行，无删除）

## 自查发现与存疑

- **"最长的那段"是判断出来的,不是量出来的。** 工单原文"多段循环的脚本以
  最长的那段为进度分母"点名的是 eval_tool 的 score 段 vs replay 段,给的
  锚点也精确指向 score 段的 print。我把这条原则类推到另外两个文件
  （run_extractor vs score_fire；generate vs score_fire）,判断依据是：
  老口径路径必跑 run_extractor()/generate(),`--self-fire` 是默认关闭的
  可选路径,而且工单给的锚点本身也只指向老口径那段的 print。但我没有拿
  实际数据集算过两段各自的 item 数谁更大——如果某次跑法 `--self-fire`
  的 val+test 开火打分批次数超过老口径提取批次数,"最长"这个判断在那次
  跑法上可能反过来。这条我判断可以接受,因为工单验收项是"只有一根进度轴"
  而不是"数值上最长的那段",而且 score_fire 完全不接心跳本身就保证了
  它不会制造第二根轴。
- **多次调用同一个心跳函数,done 会跨调用往回跳。** `eval_tool.py` 的
  `score()`/`score_causal()` 在 val/test（或 legacy 的 calA/calB/test）
  每个 split 各调一次,每次调用内部 `done` 都从 0 起数、`total` 用当次
  `len(rows)`（或 `len(events)`）——不是全脚本一个累加的全局计数。跨
  split 时 `done` 会从上一个 split 的高位掉回 0。verdicts.py 的
  `rates()` 对这种情况有保护：`last["done"] >= first_beat["done"]`
  不成立时直接把该窗口的速率记 None,不会算出负速率或报错；`judge()`
  的"已完成"判定同时看 `status=="done"` 或 `done>=total`——由于
  `range(0, len(rows), bs)` 里的 `i` 恒小于 `len(rows)`,批循环内部的
  心跳永远不会出现 `done>=total`,不会被误判成提前"已完成"。这条我读了
  `ops/verdicts.py` 源码核实过,不是猜的。`eval_mbert_call.py` 的
  `run_extractor()`（`--self-fire` 打开时会在 `extract_points()` 里被
  调第二次）和 `eval_causal_call.py` 的 `generate()`（同样)也是同一种
  情况,结论一样。
- **status=done 的 done/total 用的是"这次跑最后一次算出来的计数",不是
  "整个脚本处理过的东西的总和"。** 三个文件分别用 `len(rows_t)`、
  `cnts["n_par"]`、`n = len(per_ev)`——都是老口径主路径的规模,不含
  `--self-fire` 分支额外处理的量。这是有意的简化,工单没有要求心跳的
  `total` 必须精确等于脚本处理过的全部数据量,只要求"正常结束点打
  status=done"。
