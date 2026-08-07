# T01 — 心跳模块与判定引擎，单测全绿

工单：`.scratch/gpu-monitor-launch/issues/01-heartbeat-verdicts.md`
需求依据：`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 1（心跳模块）、Task 2（判定引擎）。
本单未直接引用 spec.md 的任何节（工单点名的是实施计划，不是 spec），未读 spec.md。

## 做了什么（对照工单四条验收）

1. **心跳测试通过：必填字段齐、选填不给不出现、parse 往返一致、垃圾行返回 None**
   - 新建 `ops/heartbeat.py`：`emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None, status=None, stream=None)` 与 `parse(line) -> dict | None`，常量 `PREFIX = "@hb "`。代码与计划 Task 1 Step 3 给出的实现逐字一致。
   - 新建 `tests/test_heartbeat.py`，4 个用例：必填字段齐全、选填字段按需出现/不出现、emit→parse 往返、三种垃圾行（非 `@hb ` 前缀 / 非法 JSON / 缺必填字段）均返回 `None`。

2. **判定测试通过：六格每格至少一个用例，判定线下限、warm-up 上限、探测失败不判已挂、服务类四格都有边界用例**
   - 新建 `ops/verdicts.py`：`DEFAULTS` 配置字典、`typical_gap_s`、`stall_line_s`、`rates`、`judge`（含内部 `_judge_service` 处理 `kind="service"` 分支），六个判定常量 `V_DONE/V_DEAD/V_STALL/V_WARMUP/V_SLOW/V_OK`。代码与计划 Task 2 Step 3 给出的实现逐字一致。
   - 新建 `tests/test_verdicts.py`，11 个用例，覆盖：
     - `test_done_beats_everything`：已完成优先级压过 alive/status
     - `test_dead`：alive=False 判已挂且当场达升级线
     - `test_stall_and_escalate`：停摆超判定线判疑似卡死，超升级线（判定线×3）才 escalate=True
     - `test_warmup_and_warmup_timeout`：warm-up 中，超 warm-up 上限转疑似卡死
     - `test_stall_line_fallback_when_few_intervals`：`stall_s=None`（间隔样本不足）时用 warm-up 上限顶着，不误报
     - `test_slow_needs_recent_rate`：近期速率 < 平均×0.5 判变慢，近期速率缺失判健康
     - `test_probe_fail_keeps_previous_alive`：`alive=None`（探测失败）不判已挂
     - `test_service`：服务类四格（端口未应答过→warm-up、应答过→健康、连续 3 轮不应答→疑似卡死、alive=False→已挂）
     - `TestLinesAndRates` 三个用例：`typical_gap_s` 中位数、`stall_line_s` 下限与 override 与样本不足返回 None、`rates` 平均/近期速率及 first_beat/recent_beats 为空的边界。

3. **两个模块只用标准库，常数全部收在判定引擎的 DEFAULTS 配置里**
   - `ops/heartbeat.py` 只 import `json`、`sys`、`time`。
   - `ops/verdicts.py` 只 import `statistics.median`。
   - 判定引擎里出现的所有阈值（判定线倍数、下限采样轮数、升级线倍数、warm-up 上限、近期速率窗口、典型心跳间隔窗口、最少间隔数、变慢比例、服务端口连续失败轮数）全部收在 `DEFAULTS` dict，函数体内没有散落的硬编码常数。

4. **`python3 run.py selfcheck` 通过，两个任务各自 commit**
   - `python3 run.py selfcheck` 输出 `selfcheck: 62 任务 / 4 配方, 全部就位`（本工单没有新增/改动 run.py 注册表条目——heartbeat 和 verdicts 是被其他任务 import 的纯库模块，不是独立可跑任务，plan 里 Task 1/2 也未要求挂注册表）。
   - Task 1 单独一个 commit，Task 2 单独一个 commit（清单见下）。

## 怎么验证的

```
$ python3 -m unittest tests.test_heartbeat -v
test_emit_optional_fields (tests.test_heartbeat.TestHeartbeat) ... ok
test_emit_required_fields (tests.test_heartbeat.TestHeartbeat) ... ok
test_parse_rejects_garbage (tests.test_heartbeat.TestHeartbeat) ... ok
test_parse_roundtrip (tests.test_heartbeat.TestHeartbeat) ... ok

Ran 4 tests in 0.000s

OK
```

```
$ python3 -m unittest tests.test_verdicts -v
test_dead (tests.test_verdicts.TestJudge) ... ok
test_done_beats_everything (tests.test_verdicts.TestJudge) ... ok
test_probe_fail_keeps_previous_alive (tests.test_verdicts.TestJudge) ... ok
test_service (tests.test_verdicts.TestJudge) ... ok
test_slow_needs_recent_rate (tests.test_verdicts.TestJudge) ... ok
test_stall_and_escalate (tests.test_verdicts.TestJudge) ... ok
test_stall_line_fallback_when_few_intervals (tests.test_verdicts.TestJudge) ... ok
test_warmup_and_warmup_timeout (tests.test_verdicts.TestJudge) ... ok
test_rates (tests.test_verdicts.TestLinesAndRates) ... ok
test_stall_line_floor (tests.test_verdicts.TestLinesAndRates) ... ok
test_typical_gap_median (tests.test_verdicts.TestLinesAndRates) ... ok

Ran 11 tests in 0.000s

OK
```

```
$ python3 run.py selfcheck
selfcheck: 62 任务 / 4 配方, 全部就位
```

```
$ python3 -m unittest discover -s tests -v
（15 项全 ok，heartbeat 4 + verdicts 11）
Ran 15 tests in 0.001s
OK
```

## Commit 清单

- `c890cec` — T01: monitor: 心跳模块 ops/heartbeat.py(emit/parse,stdlib-only)
  （`ops/heartbeat.py`、`tests/__init__.py`、`tests/test_heartbeat.py`）
- `ba3cdbb` — T01: monitor: 判定引擎 ops/verdicts.py(六格优先级+自适应两线+速率,纯函数)
  （`ops/verdicts.py`、`tests/test_verdicts.py`）

## 自查发现与存疑

- 两个模块的实现代码和测试代码在计划文档里已经写死（Step 1/Step 3 给出完整源码），本单严格照抄，没有自行发挥的空间，也没有发现和计划代码不一致需要临场决策的地方。
- `run.py selfcheck` 的"任务/配方全部就位"是通用自检，本单没有改动 `run.py` 注册表，这条验收项等同于"没弄坏别的东西"，不是本单新增内容的针对性检查。
- 没有发现需要偏离工单/计划的情况，也没有遗留的歧义点。
