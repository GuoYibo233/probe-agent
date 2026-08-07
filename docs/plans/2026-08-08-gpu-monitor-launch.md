# 长程任务监控与发射 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 `docs/design/2026-08-08-gpu-monitor-launch.md`：脚本打心跳，采样器算判定，三个出口读同一份采样历史，出事自动拉事故 agent 补射，发射收成 `run.py launch` 一条子命令。

**Architecture:** 四个新模块（`ops/heartbeat.py` 心跳、`ops/verdicts.py` 判定纯函数、`ops/sampler.py` 常驻采样器、`ops/launch_common.py`+`ops/launch_cmd.py` 发射）加三类改造（脚本接心跳、`ops/gpu_jobs.py` 出口改读采样历史、两个排卡发射器接同一套登记）。判定引擎是纯函数、零 IO，单元测试全压在它身上；IO 都在采样器里，用 `--once` 模式配假日志做集成冒烟。

**Tech Stack:** 纯 Python 标准库（ops 下所有新模块零第三方依赖，任何 venv 都能 import）；测试用 stdlib `unittest`；网页用 `http.server`，无前端依赖。

## Global Constraints

- ops 下新模块**只用标准库**（设计 §2：11 个解释器谁都要能 import）。
- 每个任务收尾必须跑 `python3 run.py selfcheck` 通过再 commit（CLAUDE.md：扩展代码与注册表更新同一个 commit）。
- 测试统一 `python3 -m unittest discover -s tests -v`（仓库根执行；本机没有 `python`，只有 `python3`）。
- 采样历史/事故记录落 NFS：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/`（大产物不进 home，不进 git；`.gitignore` 不用改——目录在仓库外）。
- 事故 agent 模型钉 **opus**（用户 2026-08-08 指定，不用 sonnet）。
- 判定的名字、口径一律照 `CONTEXT.md` 词汇表与设计文档 §4，不许另造。
- 不读写 `/home/y-guo/ACL2026` 下任何东西。
- 常数集中放 `ops/verdicts.py` 的 `DEFAULTS`，不许散落硬编码（设计 §10：跑出误报要能一处调）。

---

### Task 1: 心跳模块 `ops/heartbeat.py`

**Files:**
- Create: `ops/heartbeat.py`
- Create: `tests/test_heartbeat.py`

**Interfaces:**
- Produces: `emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None, status=None, stream=None)`；`parse(line) -> dict | None`；常量 `PREFIX = "@hb "`。后续所有任务按这两个签名用。

- [ ] **Step 1: 写失败测试** `tests/test_heartbeat.py`（`tests/` 目录与空的 `tests/__init__.py` 一并建）：

```python
import io
import json
import unittest

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))
import heartbeat


class TestHeartbeat(unittest.TestCase):
    def test_emit_required_fields(self):
        buf = io.StringIO()
        heartbeat.emit(3, 100, "task", stream=buf)
        line = buf.getvalue()
        self.assertTrue(line.startswith("@hb "))
        rec = json.loads(line[4:])
        for k in ("done", "total", "unit", "ts"):
            self.assertIn(k, rec)
        self.assertEqual(rec["done"], 3)
        self.assertNotIn("tok_in", rec)          # 选填不给就不出现

    def test_emit_optional_fields(self):
        buf = io.StringIO()
        heartbeat.emit(0, 10, "step", tok_in=123, tok_out=45,
                       loss=0.5, status="done", stream=buf)
        rec = json.loads(buf.getvalue()[4:])
        self.assertEqual((rec["tok_in"], rec["tok_out"]), (123, 45))
        self.assertEqual(rec["status"], "done")

    def test_parse_roundtrip(self):
        buf = io.StringIO()
        heartbeat.emit(7, 9, "task", tok_out=1, stream=buf)
        rec = heartbeat.parse(buf.getvalue())
        self.assertEqual(rec["done"], 7)

    def test_parse_rejects_garbage(self):
        self.assertIsNone(heartbeat.parse("task=1 SKIP (done)"))
        self.assertIsNone(heartbeat.parse("@hb not-json"))
        self.assertIsNone(heartbeat.parse('@hb {"done": 1}'))  # 缺必填


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_heartbeat -v`
Expected: FAIL（`ModuleNotFoundError: heartbeat`）

- [ ] **Step 3: 实现 `ops/heartbeat.py`**

```python
#!/usr/bin/env python3
"""心跳:长程任务脚本向采样器上报进度的唯一通道(设计文档 §2)。

一行 = 前缀 "@hb " + 一个 JSON。必填 done/total/unit/ts,选填
tok_in/tok_out(累计值)/loss/status("done"=正常收尾)。
进主循环先 emit(0, total, unit) 一条——那是"模型加载完了"的标志。
只用标准库:任何 venv 都要能 import 本文件。
"""
import json
import sys
import time

PREFIX = "@hb "
_REQUIRED = ("done", "total", "unit", "ts")


def emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None,
         status=None, stream=None):
    rec = {"done": int(done), "total": int(total), "unit": str(unit),
           "ts": round(time.time(), 1)}
    if tok_in is not None:
        rec["tok_in"] = int(tok_in)
    if tok_out is not None:
        rec["tok_out"] = int(tok_out)
    if loss is not None:
        rec["loss"] = round(float(loss), 5)
    if status is not None:
        rec["status"] = str(status)
    out = stream or sys.stdout
    out.write(PREFIX + json.dumps(rec) + "\n")
    out.flush()


def parse(line):
    """心跳行 -> dict;不是合法心跳行返回 None(监控端只认这个入口)。"""
    line = line.strip()
    if not line.startswith(PREFIX):
        return None
    try:
        rec = json.loads(line[len(PREFIX):])
    except ValueError:
        return None
    if not isinstance(rec, dict) or any(k not in rec for k in _REQUIRED):
        return None
    return rec
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_heartbeat -v`
Expected: PASS（4 个用例）

- [ ] **Step 5: Commit**

```bash
git add ops/heartbeat.py tests/__init__.py tests/test_heartbeat.py
git commit -m "monitor: 心跳模块 ops/heartbeat.py(emit/parse,stdlib-only)"
```

---

### Task 2: 判定引擎 `ops/verdicts.py`（纯函数）

**Files:**
- Create: `ops/verdicts.py`
- Create: `tests/test_verdicts.py`

**Interfaces:**
- Produces: `DEFAULTS` 配置 dict；`typical_gap_s(beat_ts, cfg)`；`stall_line_s(beat_ts, cfg, override=None)`；`rates(first_beat, recent_beats, cfg)`；`judge(p, cfg) -> (判定字符串, 是否达升级线)`。判定字符串常量 `V_DONE/V_DEAD/V_STALL/V_WARMUP/V_SLOW/V_OK` = "已完成"/"已挂"/"疑似卡死"/"warm-up 中"/"变慢"/"健康"。
- `judge` 的输入 `p`（采样器 Task 4 负责攒出这个 dict）：`kind`("batch"|"service")、`alive`(True|False|None=探测失败沿用上一轮)、`done`、`total`、`status`、`has_beat`、`beat_age_s`(最近一次看到新心跳距现在，采样器自己的钟)、`since_launch_s`、`stall_s`(None=间隔样本不够，用 warm-up 上限顶)、`escalate_s`(None=判定线×escalate_mult)、`warmup_s`、`avg_rate`、`recent_rate`、`port_ok`、`port_ever_ok`、`port_fail_rounds`。

- [ ] **Step 1: 写失败测试**（设计 §4 判定表逐格 + 边界，每格至少一个用例）：

```python
import unittest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))
import verdicts as V


def p(**kw):
    """batch 分片的默认状态,单测里按格覆盖。"""
    base = dict(kind="batch", alive=True, done=5, total=100, status=None,
                has_beat=True, beat_age_s=10.0, since_launch_s=600.0,
                stall_s=180.0, escalate_s=None, warmup_s=1800.0,
                avg_rate=1.0, recent_rate=1.0,
                port_ok=None, port_ever_ok=False, port_fail_rounds=0)
    base.update(kw)
    return base


class TestJudge(unittest.TestCase):
    def test_done_beats_everything(self):        # 优先级 1:已完成压过活着
        self.assertEqual(V.judge(p(done=100))[0], V.V_DONE)
        self.assertEqual(V.judge(p(alive=False, status="done", done=3))[0],
                         V.V_DONE)

    def test_dead(self):                          # 优先级 2:含零心跳就死的
        v, esc = V.judge(p(alive=False))
        self.assertEqual(v, V.V_DEAD)
        self.assertTrue(esc)                      # 已挂当场达升级线
        v, _ = V.judge(p(alive=False, has_beat=False, done=None, total=None))
        self.assertEqual(v, V.V_DEAD)

    def test_stall_and_escalate(self):            # 优先级 3 + 升级线
        v, esc = V.judge(p(beat_age_s=200.0))     # 停摆 200s > 判定线 180s
        self.assertEqual(v, V.V_STALL)
        self.assertFalse(esc)                     # 未过 180×3
        v, esc = V.judge(p(beat_age_s=600.0))
        self.assertEqual(v, V.V_STALL)
        self.assertTrue(esc)

    def test_warmup_and_warmup_timeout(self):     # 优先级 4 + 上限
        self.assertEqual(V.judge(p(has_beat=False, since_launch_s=300.0))[0],
                         V.V_WARMUP)
        v, _ = V.judge(p(has_beat=False, since_launch_s=2000.0))
        self.assertEqual(v, V.V_STALL)            # 超 warm-up 上限转疑似卡死

    def test_stall_line_fallback_when_few_intervals(self):
        # 间隔样本不足:stall_s=None,长首题不误报(停摆 400s < warmup 1800s)
        self.assertEqual(V.judge(p(stall_s=None, beat_age_s=400.0))[0], V.V_OK)

    def test_slow_needs_recent_rate(self):        # 优先级 5
        self.assertEqual(V.judge(p(recent_rate=0.4))[0], V.V_SLOW)
        self.assertEqual(V.judge(p(recent_rate=None))[0], V.V_OK)

    def test_probe_fail_keeps_previous_alive(self):
        # alive=None(探测失败折算后未知)不判已挂
        self.assertNotEqual(V.judge(p(alive=None))[0], V.V_DEAD)

    def test_service(self):
        s = dict(kind="service", alive=True, done=None, total=None, status=None,
                 has_beat=False, beat_age_s=0.0, since_launch_s=120.0,
                 stall_s=None, escalate_s=None, warmup_s=1800.0,
                 avg_rate=None, recent_rate=None,
                 port_ok=False, port_ever_ok=False, port_fail_rounds=0)
        self.assertEqual(V.judge(s)[0], V.V_WARMUP)          # 端口还没应答过
        s.update(port_ok=True, port_ever_ok=True)
        self.assertEqual(V.judge(s)[0], V.V_OK)
        s.update(port_ok=False, port_fail_rounds=3)
        self.assertEqual(V.judge(s)[0], V.V_STALL)           # 连续 3 轮不应答
        s.update(alive=False)
        self.assertEqual(V.judge(s)[0], V.V_DEAD)


class TestLinesAndRates(unittest.TestCase):
    def test_typical_gap_median(self):
        ts = [0, 10, 20, 30, 100]                 # 间隔 10,10,10,70 -> 中位 10
        self.assertEqual(V.typical_gap_s(ts), 10)

    def test_stall_line_floor(self):
        ts = [0, 1, 2, 3, 4]                      # 密心跳:5×1s < 3×60s 下限
        self.assertEqual(V.stall_line_s(ts), 180.0)
        self.assertEqual(V.stall_line_s(ts, override=42.0), 42.0)
        self.assertIsNone(V.stall_line_s([0, 10]))  # 只有 1 个间隔 -> None

    def test_rates(self):
        first = {"ts": 0.0, "done": 0}
        recent = [{"ts": 100.0 + i * 10, "done": 50 + i} for i in range(5)]
        avg, rc = V.rates(first, recent)
        self.assertAlmostEqual(avg, 54 / 140.0)   # (54-0)/(140-0)
        self.assertAlmostEqual(rc, 4 / 40.0)      # 窗口内 Δdone/Δts
        self.assertEqual(V.rates(first, recent[:1]), ((50 - 0) / 100.0, None))
        self.assertEqual(V.rates(None, []), (None, None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_verdicts -v`
Expected: FAIL（`ModuleNotFoundError: verdicts`）

- [ ] **Step 3: 实现 `ops/verdicts.py`**

```python
#!/usr/bin/env python3
"""判定引擎:纯函数,零 IO(设计文档 §4)。采样器喂状态进来,拿判定出去。
六格判定按固定优先级判,命中即停:已完成→已挂→疑似卡死→warm-up 中→变慢→健康。
时钟纪律:跨机不比钟——beat_age_s/since_launch_s 由采样器用自己的钟算好喂进来,
心跳 ts 只在 rates() 里同机做差。所有常数收在 DEFAULTS,别处不许硬编码。
"""
from statistics import median

V_DONE, V_DEAD, V_STALL = "已完成", "已挂", "疑似卡死"
V_WARMUP, V_SLOW, V_OK = "warm-up 中", "变慢", "健康"

DEFAULTS = dict(
    sample_interval_s=60.0,   # 采样器一轮的间隔
    stall_mult=5.0,           # 判定线 = 5 × 典型心跳间隔
    stall_floor_samples=3,    # 判定线下限 = 3 轮采样(采样粒度以下分不清停没停)
    escalate_mult=3.0,        # 升级线 = 判定线 × 3
    warmup_line_s=1800.0,     # warm-up 上限,默认 30 分钟
    recent_beats=10,          # 近期速率窗口:最近 ≤10 条心跳
    typical_beats=20,         # 典型心跳间隔:最近 ≤20 个间隔的中位数
    min_intervals=3,          # 攒够 3 个间隔才用自适应判定线
    slow_ratio=0.5,           # 变慢 = 近期速率 < 平均 × 0.5
    port_fail_rounds=3,       # 服务:连续 3 轮端口不应答 = 疑似卡死
)


def typical_gap_s(beat_ts, cfg=DEFAULTS):
    """最近 ≤typical_beats 个心跳间隔的中位数;间隔不足 min_intervals 个返回 None。"""
    ts = list(beat_ts)[-(cfg["typical_beats"] + 1):]
    gaps = [b - a for a, b in zip(ts, ts[1:]) if b >= a]
    if len(gaps) < cfg["min_intervals"]:
        return None
    return median(gaps)


def stall_line_s(beat_ts, cfg=DEFAULTS, override=None):
    """判定线(秒)。override=发射时的 --stall-line;样本不足返回 None
    (调用方用 warm-up 上限顶着,长 task/长 step 开局不误报)。"""
    if override is not None:
        return float(override)
    gap = typical_gap_s(beat_ts, cfg)
    if gap is None:
        return None
    return max(cfg["stall_mult"] * gap,
               cfg["stall_floor_samples"] * cfg["sample_interval_s"])


def rates(first_beat, recent_beats, cfg=DEFAULTS):
    """(平均速率, 近期速率),单位 done/秒;算不出的为 None。
    first_beat: 首条心跳 {'ts','done'}(采样器累计状态里存的,不依赖日志尾)。
    recent_beats: 最近 ≤typical_beats 条心跳(升序)。分母全在心跳时间轴上。"""
    if not first_beat or not recent_beats:
        return None, None
    last = recent_beats[-1]
    avg = None
    dt = last["ts"] - first_beat["ts"]
    if dt > 0 and last["done"] >= first_beat["done"]:
        avg = (last["done"] - first_beat["done"]) / dt
    w = recent_beats[-cfg["recent_beats"]:]
    recent = None
    if len(w) >= 2:
        dtw = w[-1]["ts"] - w[0]["ts"]
        if dtw > 0 and w[-1]["done"] >= w[0]["done"]:
            recent = (w[-1]["done"] - w[0]["done"]) / dtw
    return avg, recent


def _judge_service(p, cfg):
    if p["alive"] is False:
        return V_DEAD, True
    if p.get("port_ok"):
        return V_OK, False
    if not p.get("port_ever_ok"):
        if p["since_launch_s"] > p["warmup_s"]:
            esc = p["since_launch_s"] > p["warmup_s"] * cfg["escalate_mult"]
            return V_STALL, esc
        return V_WARMUP, False
    n = p.get("port_fail_rounds", 0)
    if n >= cfg["port_fail_rounds"]:
        esc = n >= cfg["port_fail_rounds"] * cfg["escalate_mult"]
        return V_STALL, esc
    return V_OK, False


def judge(p, cfg=DEFAULTS):
    """一个分片一轮恰好一格。返回 (判定, 是否达升级线)。
    已完成、变慢对服务类不适用(设计 §4 末尾),服务走 _judge_service。"""
    if p["kind"] == "service":
        return _judge_service(p, cfg)
    done, total = p.get("done"), p.get("total")
    if p.get("status") == "done" or (done is not None and total
                                     and done >= total):
        return V_DONE, False
    if p["alive"] is False:
        return V_DEAD, True
    warm = not p["has_beat"]
    age = p["since_launch_s"] if warm else p["beat_age_s"]
    line = p["warmup_s"] if (warm or p.get("stall_s") is None) else p["stall_s"]
    if age > line:
        esc_line = (p["escalate_s"] if p.get("escalate_s") is not None
                    else line * cfg["escalate_mult"])
        return V_STALL, age > esc_line
    if warm:
        return V_WARMUP, False
    if (p.get("recent_rate") is not None and p.get("avg_rate")
            and p["recent_rate"] < cfg["slow_ratio"] * p["avg_rate"]):
        return V_SLOW, False
    return V_OK, False
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_verdicts -v`
Expected: PASS（11 个用例）

- [ ] **Step 5: Commit**

```bash
git add ops/verdicts.py tests/test_verdicts.py
git commit -m "monitor: 判定引擎 ops/verdicts.py(六格优先级+自适应两线+速率,纯函数)"
```

---

### Task 3: 采集脚本接心跳（`run_appworld.py`）

**Files:**
- Modify: `envs/collect/run_appworld.py:14-15`（import 区）、`:76`（主循环前）、`:78-124`（循环体）

**Interfaces:**
- Consumes: Task 1 的 `heartbeat.emit`。token 数据源是 `common.Chat.__call__` 返回 dict 里的 `g["usage"]["in"]` / `g["usage"]["out"]`（`envs/collect/common.py:161,182,220-221`，现成，common.py 不用改）。

- [ ] **Step 1: 加 import**（`sys.path.insert(0, str(Path(__file__).parent))` 一行之后）：

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import heartbeat  # noqa: E402
```

- [ ] **Step 2: 主循环前打 done=0**（`print(f"shard {args.shard_id}...")` 之后、`for tid in ids:` 之前）：

```python
tok_in = tok_out = 0
n_done = 0
heartbeat.emit(0, len(ids), "task", tok_in=0, tok_out=0)
```

- [ ] **Step 3: 累计 token 与每题心跳**。改两处：
  1. `g = chat(msgs)` 之后（`log.w({"type": "gen", ...})` 之前）加：

```python
                tok_in += g["usage"]["in"]
                tok_out += g["usage"]["out"]
```

  2. 每题收尾 `print(f"task={tid} steps=...")` 之后加（resume SKIP 分支的 `continue` 之前也加一份，SKIP 的题同样推进 done）：

```python
            n_done += 1
            heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in, tok_out=tok_out)
```

  循环结束（`main()` 末尾）加正常收尾标志：

```python
    heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in, tok_out=tok_out,
                   status="done")
```

- [ ] **Step 4: 验证**

Run: `envs/appworld/venv/bin/python -c "import ast,sys; ast.parse(open('envs/collect/run_appworld.py').read()); print('syntax ok')"` 然后 `envs/appworld/venv/bin/python envs/collect/run_appworld.py --help`
Expected: `syntax ok`；--help 正常打印（heartbeat import 在 appworld venv 下成功——这就是"stdlib only"约束的实测）

- [ ] **Step 5: Commit**

```bash
git add envs/collect/run_appworld.py
git commit -m "collect: run_appworld 接心跳(每题 done/累计 token,done=0 标加载完)"
```

---

### Task 4: 训练脚本接心跳（四格）

**Files:**
- Modify: `pipeline/train/train_mbert_tool.py`、`train_mbert_extract.py`、`train_causal_tool.py`、`train_causal_callgen.py`（四个文件同一模式；各文件的 `log()` 闭包位置见 `probe-pipeline/references/extending.md:130`：mtool:132-138 / mext:265-267 / ctool:313-315 / cgen:234-236，行号以 grep 现查为准）

**Interfaces:**
- Consumes: `heartbeat.emit`。总步数 = 各脚本已算好的 `steps` 变量（mtool 在 `train_mbert_tool.py:172`），当前步 = `gstep`，loss = 现有 step 日志里的滑动均值。

- [ ] **Step 1: mtool 的三处插入**（其余三格照同一锚点重复）：
  1. 文件头 import 区加：

```python
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat
```

  2. `log(event="start", ...)`（mtool:185）之后加：`heartbeat.emit(0, steps, "step")`
  3. `gstep % 50 == 0` 的 `log(event="step", ...)`（mtool:208-210）之后加：

```python
                    heartbeat.emit(gstep, steps, "step",
                                   loss=round(run / (50 * args.accum), 4))
```

  注意：这一行在 `run = 0.0` 复位**之前**插，取的是同一个滑动均值。
  4. `log(event="done", ...)`（mtool:222）之后加：`heartbeat.emit(gstep, steps, "step", status="done")`

- [ ] **Step 2: 其余三格重复**。先 `grep -n "event=\"start\"\|event=\"step\"\|event=\"done\"\|steps =" pipeline/train/train_mbert_extract.py pipeline/train/train_causal_tool.py pipeline/train/train_causal_callgen.py` 找锚点，逐文件插同样四处（变量名以各文件实际为准——总步数变量、全局步变量、loss 滑动均值表达式照抄它自己 `log(event="step")` 里已有的那份）。

- [ ] **Step 3: 验证**

Run: `for f in pipeline/train/train_*.py; do mbert-env/bin/python -c "import ast; ast.parse(open('$f').read())" && echo "$f ok"; done`
Expected: 四个 ok。再 `mbert-env/bin/python -c "import sys; sys.path.insert(0,'ops'); import heartbeat; print('import ok')"` 与 `cprobe-env/bin/python -c "同上"`——两个训练 venv 都能 import。

- [ ] **Step 4: Commit**

```bash
git add pipeline/train/train_mbert_tool.py pipeline/train/train_mbert_extract.py \
        pipeline/train/train_causal_tool.py pipeline/train/train_causal_callgen.py
git commit -m "train: 四格训练脚本接心跳(unit=step,报滑动 loss)"
```

---

### Task 5: 评测脚本接心跳（三个）

**Files:**
- Modify: `pipeline/eval/eval_tool.py`（锚点 `:69` 的 `print(f"scored {i}/{len(rows)}")`）、`pipeline/eval/eval_mbert_call.py`（锚点 `:127` 的 `print(f"extracted {i}/...")`）、`pipeline/eval/eval_causal_call.py`（锚点 `:207` 起的批循环）

**Interfaces:**
- Consumes: `heartbeat.emit`。unit 用 `"item"`（评测的进度分母是样本条数）。

- [ ] **Step 1: 逐文件插入**。import 区加与 Task 4 相同的四行（parents[2] 对 pipeline/eval 同样落在仓库根）。主批循环开始前 `heartbeat.emit(0, <总数表达式>, "item")`；每个已有进度 print 的位置跟一条 `heartbeat.emit(<当前 i>, <总数>, "item")`；脚本正常结束点（写报告文件之后）`heartbeat.emit(<总数>, <总数>, "item", status="done")`。eval_causal_call.py 没有现成进度 print，就在 `:207` 的 `for i in range(0, len(prompts), bs):` 循环体尾部按同样节奏（每 50 批一条）加。多段循环的文件（eval_tool 有 score 段和 replay 段）以**最长的那段**为进度分母，其他段不打心跳——一个脚本一条进度轴，别打出两根。

- [ ] **Step 2: 验证**

Run: `for f in pipeline/eval/eval_tool.py pipeline/eval/eval_mbert_call.py pipeline/eval/eval_causal_call.py; do python3 -c "import ast; ast.parse(open('$f').read())" && echo "$f ok"; done`
Expected: 三个 ok

- [ ] **Step 3: Commit**

```bash
git add pipeline/eval/eval_tool.py pipeline/eval/eval_mbert_call.py pipeline/eval/eval_causal_call.py
git commit -m "eval: 三个评测脚本接心跳(unit=item)"
```

---

### Task 6: 采样器核心 `ops/sampler.py`（采样循环，先不带网页与事故）

**Files:**
- Create: `ops/sampler.py`
- Create: `tests/test_sampler.py`
- Modify: `run.py`（TASKS 加 `"sampler"` 条目）

**Interfaces:**
- Consumes: `gpu_jobs.load_reg` / `gpu_jobs.live_sessions` / `gpu_jobs.DEFAULT_HOSTS`（`ops/gpu_jobs.py:37,62,107`，import 复用，不复制）；`heartbeat.parse`；`verdicts.judge/rates/stall_line_s`。
- Produces（后续任务和出口读的落盘格式）：
  - `MONITOR_DIR = /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/`（环境变量 `NEW1_MONITOR_DIR` 可覆盖——单测用它指到 tmp）
  - `latest.json`（原子写）：`{"sampled_at": <epoch>, "rows": [...], "extras": {...}, "incidents_tail": [...]}`；每行 row：`{"job","idx","host","gpus","session","kind","verdict","escalated","done","total","unit","progress_pct","avg_rate","recent_rate","tok_in","tok_out","loss","eta_s","log","probe_failed","refires"}`
  - `state.json`（原子写）：`{"<job>#<idx>": {"first_beat":{"ts","done"},"recent_beats":[≤20 条 {"ts","done","tok_in","tok_out","loss","status"}],"last_new_beat_mono","last_done","launched_at","alive_last","probe_fail_rounds","port_ever_ok","port_fail_rounds","verdict","escalated_since_mono","incident_open","refires"}`
  - `history/<job>.jsonl`（append）：每轮每分片一行 row（同 latest 的 row + `"t"`）
  - 函数 `sample_once(now_mono, now_wall) -> latest dict`；`main()` 支持 `--once`（采一轮就退，冒烟用）与 `--interval N`

- [ ] **Step 1: 写失败测试**。fixture：tmp 目录里造 `jobs.json`（一个任务两分片，piece 带 `log` 指向 tmp 里手写的日志文件——一份日志尾部有三条心跳行，另一份没有心跳只有普通文本）；monkeypatch `sampler.live_sessions = lambda hosts: {"tokyo106": {"new1_x_t106g0"}}`（第 1 分片活、第 2 分片名字不在集合里）。断言 `sample_once()` 返回的 rows：分片 0 判定 ∈ {健康, warm-up 中}（有心跳、alive）、分片 1 判定 = 已挂；latest.json / state.json / history 文件真的落了盘且能 json.load；再跑一轮，分片 0 的 `recent_beats` 不重复追加同一条心跳（同 ts 同 done 不算新心跳）。测试骨架：

```python
import json, os, pathlib, tempfile, time, unittest
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))


class TestSampleOnce(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.td.name)
        os.environ["NEW1_MONITOR_DIR"] = str(d / "monitor")
        log0 = d / "a.log"
        now = time.time()
        log0.write_text(
            "loading...\n"
            f'@hb {{"done": 0, "total": 10, "unit": "task", "ts": {now-120:.1f}}}\n'
            f'@hb {{"done": 1, "total": 10, "unit": "task", "ts": {now-60:.1f}, "tok_in": 100, "tok_out": 20}}\n'
            f'@hb {{"done": 2, "total": 10, "unit": "task", "ts": {now-1:.1f}, "tok_in": 210, "tok_out": 41}}\n')
        log1 = d / "b.log"
        log1.write_text("Traceback (most recent call last):\n  boom\n")
        self.jobs = d / "jobs.json"
        self.jobs.write_text(json.dumps({"active": [{
            "name": "x", "workdir": str(d), "started_at": "2026-08-08 00:00",
            "monitor": {"warmup_s": 1800},
            "pieces": [
                {"host": "tokyo106", "gpus": "0", "session": "new1_x_t106g0",
                 "log": str(log0), "launched_at": now - 3600, "kind": "batch"},
                {"host": "tokyo106", "gpus": "1", "session": "new1_x_t106g1",
                 "log": str(log1), "launched_at": now - 3600, "kind": "batch"},
            ]}], "history": []}))
        import importlib
        import sampler
        importlib.reload(sampler)
        self.S = sampler
        self.S.REG_PATH = str(self.jobs)
        self.S.live_sessions = lambda hosts: {"tokyo106": {"new1_x_t106g0"}}

    def tearDown(self):
        self.td.cleanup()
        os.environ.pop("NEW1_MONITOR_DIR", None)

    def test_round(self):
        latest = self.S.sample_once()
        rows = {r["idx"]: r for r in latest["rows"]}
        self.assertIn(rows[0]["verdict"], ("健康", "warm-up 中"))
        self.assertEqual(rows[1]["verdict"], "已挂")
        self.assertEqual(rows[0]["tok_in"], 210)
        mon = pathlib.Path(os.environ["NEW1_MONITOR_DIR"])
        self.assertTrue((mon / "latest.json").exists())
        self.assertTrue((mon / "state.json").exists())
        self.assertTrue((mon / "history" / "x.jsonl").exists())
        n1 = len(json.loads((mon / "state.json").read_text())
                 ["x#0"]["recent_beats"])
        self.S.sample_once()                      # 日志没变,不重复计心跳
        n2 = len(json.loads((mon / "state.json").read_text())
                 ["x#0"]["recent_beats"])
        self.assertEqual(n1, n2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**（`ModuleNotFoundError: sampler`）

- [ ] **Step 3: 实现 `ops/sampler.py`**。结构（函数逐个写，行为按注释钉死）：

```python
#!/usr/bin/env python3
"""采样器:长程任务的常驻监控进程(设计文档 §3-§5)。
每轮:读台账 → tail 日志抓心跳(NFS 本地读) → ssh 探存活 → verdicts.judge
→ append 采样历史 + 原子写 latest.json/state.json。
本文件只做 IO 和攒状态,判定口径全在 ops/verdicts.py。stdlib only。
用法: sampler.py [--once] [--interval 60] [--port 8377](网页 Task 7 加)
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(OPS))
import heartbeat, verdicts
from gpu_jobs import load_reg, live_sessions, DEFAULT_HOSTS, REG_PATH  # noqa

MONITOR_DIR = Path(os.environ.get(
    "NEW1_MONITOR_DIR",
    "/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor"))

def read_beats(log_path, max_bytes=262144):
    """日志尾 256KB 里的所有心跳行(升序)。tqdm 的 \r 先换 \n。"""

def atomic_write(path, obj): ...        # tmp + os.replace,与 run.py save_state 同款

def load_state(): ...                    # state.json 不在/坏了 -> {}

def piece_key(job, idx): ...             # f"{job}#{idx}"

def update_piece_state(st, job, idx, piece, beats, alive, now_mono):
    """攒一个分片的累计状态(设计 §3):
    - launched_at 变了(补射) -> 整段状态重开,refires += 1
    - beats 里比 last_done/last_ts 新的条目 append 进 recent_beats(截 ≤20),
      并刷新 last_new_beat_mono = now_mono
    - first_beat 只在第一次见到心跳时记
    - alive: None(探测失败) -> alive_last 沿用,probe_fail_rounds += 1;
      True/False -> 直取,probe_fail_rounds = 0
    - 服务类:port_ok 由 probe_port() 出,port_ever_ok/port_fail_rounds 同理攒"""

def probe_port(host, port, timeout=3):
    """服务类分片的端口探测:HTTP GET http://host:port/health,
    连接被拒/超时 -> False。vLLM 的 /health 返回 200(Task 15 核对后如有出入改这里)。"""

def build_row(job, idx, piece, ps, now_mono):
    """状态 -> 出口 row:调 verdicts.stall_line_s(override=piece 里的 stall_line)
    / rates / judge,算 progress_pct 和 eta_s(近期速率没值退回平均;都没值 None)。"""

def sample_once():
    reg = load_reg()
    hosts = {p["host"] for j in reg["active"] for p in j["pieces"]} | set(DEFAULT_HOSTS)
    live = live_sessions(hosts)
    st = load_state()
    rows, per_job_lines = [], {}
    now_mono, now_wall = time.monotonic(), time.time()
    for job in reg["active"]:
        for idx, piece in enumerate(job["pieces"]):
            sess_set = live.get(piece["host"])
            alive = None if sess_set is None else (piece["session"] in sess_set)
            beats = read_beats(piece["log"])
            ps = update_piece_state(st, job["name"], idx, piece, beats,
                                    alive, now_mono)
            row = build_row(job["name"], idx, piece, ps, now_mono)
            rows.append(row)
            per_job_lines.setdefault(job["name"], []).append(dict(row, t=now_wall))
    extras = {h: sorted(s - registered) ...}     # 照 gpu_jobs.collect 的 extras 逻辑
    latest = {"sampled_at": now_wall, "rows": rows, "extras": extras,
              "incidents_tail": read_incidents_tail()}
    for jname, lines in per_job_lines.items():
        append_jsonl(MONITOR_DIR / "history" / f"{jname}.jsonl", lines)
    atomic_write(MONITOR_DIR / "state.json", st)
    atomic_write(MONITOR_DIR / "latest.json", latest)
    maybe_trigger_incidents(rows, st)            # Task 14 前先放空函数 pass
    return latest

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float,
                    default=verdicts.DEFAULTS["sample_interval_s"])
    a = ap.parse_args()
    while True:
        t0 = time.monotonic()
        try:
            sample_once()
        except Exception as e:                   # 单轮失败不许弄死常驻进程
            print(f"[sampler] round failed: {e}", file=sys.stderr, flush=True)
        if a.once:
            break
        time.sleep(max(1.0, a.interval - (time.monotonic() - t0)))
```

  关键实现约束（都来自设计文档，写代码时逐条对）：
  - **时钟**：`last_new_beat_mono` 用 `time.monotonic()`；`beat_age_s = now_mono - last_new_beat_mono`；`since_launch_s = now_wall - piece["launched_at"]`（launched_at 是发射机的挂钟，登录机和发射机都是 NTP 机器，分钟级误差可接受——分片没有 launched_at 字段（手工 register 的旧格式）就用 job["started_at"] 解析，再没有就当 now，即宽松处理）。
  - **新心跳判定**：`(b["ts"], b["done"]) > (last_ts, last_done)` 才算新。
  - **`stall_line_s` 的 override** 从 `piece.get("stall_line")` 取；`escalate_s` 从 `piece.get("escalate_line")`；`warmup_s` 从 `job.get("monitor", {}).get("warmup_s")`，缺省 `verdicts.DEFAULTS["warmup_line_s"]`。
  - **探测失败连续 10 轮**：row 加 `"probe_failed": true` 且 `probe_fail_rounds` 进 row，出口负责亮红——采样器不因此触发事故（fail-closed）。

- [ ] **Step 4: run.py 挂注册表**。`TASKS` 的 ops 段加：

```python
    "sampler": dict(
        stage="ops", py="sys", script="ops/sampler.py",
        desc="长程任务采样器(常驻;60s 一轮采心跳/探存活/算判定,开网页)",
        notes=["常驻进程,登录机 tmux 里跑: tmux new-session -d -s new1_sampler "
               "'python3 run.py sampler'",
               "落盘在 NFS monitor/(latest.json/state.json/history/incidents),不进 git",
               "冒烟: python3 run.py sampler --once 采一轮就退"]),
```

- [ ] **Step 5: 跑测试 + selfcheck 确认通过**

Run: `python3 -m unittest tests.test_sampler -v && python3 run.py selfcheck`
Expected: PASS；selfcheck 全部就位

- [ ] **Step 6: Commit**

```bash
git add ops/sampler.py tests/test_sampler.py run.py
git commit -m "monitor: 采样器核心(采心跳/探存活/判定/落盘 latest+state+history)+注册 sampler 任务"
```

---

### Task 7: 采样器网页（HTTP 线程 + /json）

**Files:**
- Modify: `ops/sampler.py`（加 HTTP 线程与 `--port`）
- Create: `tests/test_sampler_web.py`

**Interfaces:**
- Produces: `GET /` = HTML 任务表；`GET /json` = latest.json 原文（Content-Type application/json）。端口默认 8377，`--port` 覆盖。网页线程只读 latest.json，不碰采样线程的内存——采样卡住不影响出页（设计 §3）。

- [ ] **Step 1: 写失败测试**：fixture 写一份 latest.json（含 sampled_at 与两行 rows），起 `sampler.WebServer(port=0, monitor_dir=...)`（port=0 让 OS 分配，测试从 `server.server_address[1]` 拿真实端口），`urllib.request` 抓 `/json` 断言与文件一致、抓 `/` 断言 200 且 body 含任务名与判定字符串、含 `sampled_at` 的时间戳文本。

- [ ] **Step 2: 实现**：`http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler`；`do_GET` 按 path 分流；HTML 用一个 `render_html(latest)` 纯函数拼（表列：JOB/分片/HOST/GPU/判定/进度/速率/token/ETA/SESSION；`<meta http-equiv="refresh" content="30">` 自动刷新；页顶最后采样时刻，内嵌一段 `<script>`：`sampled_at` 距现在 > 3×60s 就把横幅类名换成红色——阈值从 `verdicts.DEFAULTS["sample_interval_s"]` 乘 3 生成进页面，不再抄一个数）；事故记录块渲染 `incidents_tail`；台账外 session 渲染 `extras`。`main()` 加 `--port`，非 `--once` 时先起 web 线程（daemon=True）再进采样循环。

- [ ] **Step 3: 跑测试确认通过** `python3 -m unittest tests.test_sampler_web -v`

- [ ] **Step 4: Commit**

```bash
git add ops/sampler.py tests/test_sampler_web.py
git commit -m "monitor: 采样器网页出口(/ 任务表 + /json,只读 latest.json)"
```

---

### Task 8: 终端出口改读采样历史（`ops/gpu_jobs.py`）

**Files:**
- Modify: `ops/gpu_jobs.py`（`cmd_status`/`cmd_watch`/`json` 三个出口；`free`/`register`/`finish` 一行不动）

**Interfaces:**
- Consumes: `latest.json`（Task 6 的格式）。
- Produces: 三个出口的读取顺序：latest.json 存在且 `sampled_at` 距现在 ≤ 300 秒 → 用它渲染（表头第一行 `最后采样 HH:MM:SS`）；否则打印一行警告 `采样器不在跑(最后采样 <时刻|无>),现场实探一次` 后走现有 `collect()` 老路。`json` 出口同理：新鲜时输出 latest.json 原文，否则输出老 `collect()` 结果外加 `"sampler_stale": true` 字段。

- [ ] **Step 1: 实现** `read_latest()`（返回 `(latest_dict|None, age_s|None)`）与 `fmt_table_v2(rows)`（列：JOB/HOST/GPU/判定/PROGRESS/RATE/TOK/ETA/SESSION；PROGRESS = `done/total (pct%) unit`；RATE = `recent_rate` 有值取它、乘 3600 显示 `/h` 或保留 `/s` 按数量级、没值 `-`；TOK = `tok_in/tok_out` 千分位缩写如 `1.2M/340k`；ETA = `eta_s` 转 `HH:MM`）。`DONE 该收尾` 与 `EXIT 看日志` 的两段提示行为保留（判定=已完成/已挂 时输出对应提示，措辞沿用现有 `fmt_table`）。

- [ ] **Step 2: 手动验证**（没有采样器在跑的机器上）：

Run: `python3 run.py gpu-jobs && python3 run.py gpu-jobs json | python3 -c "import json,sys; json.load(sys.stdin); print('json ok')"`
Expected: 警告行 + 老表照出；`json ok`。再造一份假 latest.json（`NEW1_MONITOR_DIR` 指向 tmp）确认新表出得来、表头带最后采样时刻。

- [ ] **Step 3: Commit**

```bash
git add ops/gpu_jobs.py
git commit -m "monitor: gpu-jobs 三出口改读采样历史(新鲜用之,过期亮警告退回实探)"
```

---

### Task 9: 采样器上线（tmux + crontab 看门狗）

**Files:**
- Modify: 登录机 crontab（系统状态，不是仓库文件）

- [ ] **Step 1: 起常驻进程**

```bash
tmux new-session -d -s new1_sampler 'cd /home/y-guo/reproduce/new1 && python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'
```

- [ ] **Step 2: 装看门狗**（`crontab -l` 先备份到 `/tmp/crontab.bak`，再追加一行）：

```
*/5 * * * * tmux has-session -t new1_sampler 2>/dev/null || tmux new-session -d -s new1_sampler 'cd /home/y-guo/reproduce/new1 && python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'
```

- [ ] **Step 3: 验证**：`curl -s localhost:8377/json | python3 -m json.tool | head`（出合法 JSON）；浏览器（VS Code 端口转发）开 `localhost:8377` 看到任务表；`tmux kill-session -t new1_sampler` 后等 5 分钟确认 crontab 把它拉回来（`tmux ls` 里再次出现）。

---

### Task 10: 发射公共件 `ops/launch_common.py`

**Files:**
- Create: `ops/launch_common.py`
- Create: `tests/test_launch_common.py`

**Interfaces:**
- Produces（Task 11-13 全靠这些签名）：
  - `ALIAS = {"shiga": "tokyo105", "saitama": "tokyo108"}`；`local_host()`；`has_session(host, sess)`；`tmux_launch(host, sess, inner_cmd)`——这三个从 `ops/launch_probe.py:47-62` 原样搬（搬完 Task 13 让 launch_probe 反过来 import 这里的，删它自己那份）。
  - `probe_free(host, gpus) -> (ok: bool, why: str)`：`ssh <host> nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader -i <gpus>`；stdout 非空 → `(False, "占用中: <首行>")`；ssh 失败/超时 → `(False, "探测失败: ...")`（fail-closed）；空 → `(True, "")`。
  - `register_all(run_id, workdir, pieces, track, cmd_display, note=None, outdir=None, monitor=None) -> str`：三处登记一口气——①台账：`gpu_jobs.mutate_reg` 直接 append job（rich piece：host/gpus/session/log/cmd/launched_at/kind/stall_line/escalate_line；job 级 `monitor={"warmup_s":...}`，`note`）；②实验记录：`subprocess.run([sys.executable, str(OPS/"record.py"), "start", "--run-id", run_id, "--track", track, "--cmd", cmd_display, "--host", ..., "--gpu", ..., "--log", ...])`（subprocess 隔离 record 的 sys.exit；rc≠0 原样透出并中止——record 拒绝重复 run_id 是护栏不是障碍）；③RUNMETA：`outdir` 给了才 `runmeta.append_runmeta(outdir, cmd_display, kind="launch")`，没给打一行 `WARN 没给 --outdir,RUNMETA 没写`。返回登记回执文本。

- [ ] **Step 1: 写失败测试**：`probe_free` 用 monkeypatch 替 `subprocess.run` 喂三种结果（空 stdout / 有进程行 / raise TimeoutExpired）断言三种返回；`register_all` 用 `NEW1_MONITOR_DIR`+tmp 的 jobs.json（monkeypatch `gpu_jobs.REG_PATH`）断言台账里出现 rich piece 全字段、重复 run_id 第二次调用抛 SystemExit。

- [ ] **Step 2: 实现**（照上面接口签名；`tmux_launch` 的 inner 模板与 launch_probe.py:57 完全一致：`cd <wd> && CUDA_VISIBLE_DEVICES=<g> <cmd> 2>&1 | tee <log>`，env 变量有就前置 `K=V` 对）。

- [ ] **Step 3: 跑测试确认通过**，然后 Commit：

```bash
git add ops/launch_common.py tests/test_launch_common.py
git commit -m "launch: 公共件(探卡 fail-closed/tmux 模板/三处登记一口气)"
```

---

### Task 11: `run.py launch` 子命令（task 模式 + --cmd 模式）

**Files:**
- Create: `ops/launch_cmd.py`
- Create: `tests/test_launch_cmd.py`
- Modify: `run.py`（main() 加 dispatch；`collect-aw` 条目加 `shardable=True`；文件头 usage 文档加一行 launch 用法）

**Interfaces:**
- Consumes: `run.TASKS/PY/build_cmd/gate_dirty/gate_of`（`sys.path` 到仓库根后 `from run import ...`，照 launch_probe.py:41-42 的既有做法）；Task 10 全部。
- Produces: 命令行（设计 §6 定稿的签名）：

```
python3 run.py launch <task> [任务参数...] --run-id ID --piece host:gpus [--piece ...]
    --track 方向 [--note ...] [--outdir DIR]
    [--stall-line 秒] [--escalate-line 秒] [--warmup-line 秒]
    [--service --port N] [--allow-dirty] [--dry-run]
python3 run.py launch --cmd '<完整命令>' --run-id ID --workdir DIR --piece ... (其余同上)
```

- [ ] **Step 1: 写失败测试**（把纯逻辑拆成可测函数）：`build_pieces(argv 解析结果, task_entry)` 的分片注入——2 个 piece + `shardable=True` → 两条命令分别带 `--shard-id 0/1 --num-shards 2`；非 shardable + 2 piece → SystemExit；session 名 = `new1_<run_id>_t<host去掉tokyo>g<gpus 逗号换连字符>`；同 host 同 gpus 两个 piece → SystemExit。`--cmd` 模式不查注册表、命令原样。dry-run 输出含全部 inner 命令且不碰任何登记（monkeypatch register_all 断言没被调）。

- [ ] **Step 2: 实现 `cmd_launch(argv)`**。流程钉死成十步，一步不许换序：
  1. 手写参数解析（gpu_jobs.py 的 iter 风格；未知参数留给任务透传，`--` 之后全透传）。
  2. task 模式：`t = TASKS[task]`；`--cmd` 模式跳过注册表。
  3. `gate_dirty(...)`（honor_dry=True：`--dry-run` 放行；沿用 run.py:546 的实现，import 复用）。
  4. run_id 必填校验；`--track` 必填（record start 硬要求）。
  5. pieces 解析 + 分片注入 + session/log 命名（log = `<workdir>/logs/<sess>.log`，workdir 默认 ROOT，task 有 cwd 用 cwd）。
  6. `--dry-run` → 打印每分片 host/gpu/session/inner 命令，返回 0。
  7. 逐 piece `probe_free`，任何一张不 FREE → SystemExit 列出原因（一张都不发射）。
  8. 逐 piece `tmux_launch`。
  9. **验活 30 秒**：每 5 秒一轮,轮内逐 piece 查 `has_session` + 日志文件字节数增长 + tail 4KB 无 `Traceback`；全部 piece 见到输出即提前通过；30 秒后 session 没了或 tail 有 Traceback → 打印失败分片与日志尾 40 行，**已发射的不回滚**（杀进程是人的决定），返回 1 且不登记——发射失败不落账。
  10. `register_all(...)` + 打印监控入口（`python3 run.py gpu-jobs` / `watch` / 网页 `localhost:8377`）。
  在 `run.py:main()` 的 `if cmd == "selfcheck"` 之后加：

```python
    if cmd == "launch":
        sys.path.insert(0, str(ROOT / "ops"))
        from launch_cmd import cmd_launch
        return cmd_launch(rest)
```

- [ ] **Step 3: 跑测试 + selfcheck**，冒烟一发 dry-run：

Run: `python3 -m unittest tests.test_launch_cmd -v && python3 run.py selfcheck && python3 run.py launch collect-aw --run-id smoke_x --track smoke --piece tokyo106:0 --piece tokyo106:1 --dry-run --allow-dirty -- --base-url http://x/v1 --model m --outdir /tmp/x`
Expected: 测试过；dry-run 打出两条带 `--shard-id 0/1` 的 inner 命令

- [ ] **Step 4: Commit**

```bash
git add ops/launch_cmd.py tests/test_launch_cmd.py run.py
git commit -m "launch: run.py launch 子命令(验卡→tmux→验活→三处登记一条命令;shardable 注入)"
```

---

### Task 12: 补射模式 `launch --refire`

**Files:**
- Modify: `ops/launch_cmd.py`、`tests/test_launch_cmd.py`

**Interfaces:**
- Produces: `python3 run.py launch --refire <run_id> --idx <分片号> [--piece host:gpus] [--allow-dirty]`。行为：台账里找该 job 的第 idx 个 piece → 那个 session 必须已经死了（`has_session` 为真 → SystemExit "session 还活着,补射只对死分片"）→ 目标卡 = `--piece` 给的或原卡，`probe_free` 验，不 FREE → SystemExit（事故 agent 拿这个报错回去换卡重试）→ 用 piece 里存的 `cmd` 原样重发（session 名不变，log 换新文件 `<sess>.r<refires+1>.log`）→ `mutate_reg` 更新该 piece 的 host/gpus/log/`launched_at=now` → 不新开 record、不重复 register（补射不是新任务）。采样器看到 `launched_at` 变了自动重开该分片的心跳时间轴并 `refires+=1`（Task 6 已实现）。

- [ ] **Step 1: 写失败测试**：tmp 台账 + monkeypatch `has_session`/`probe_free`/`tmux_launch`，断言：活 session 拒绝；非 FREE 拒绝；成功路径下台账 piece 的 log/launched_at 更新且 cmd 未变、没有第二个 job 出现。

- [ ] **Step 2: 实现 + 跑测试通过 + Commit**

```bash
git add ops/launch_cmd.py tests/test_launch_cmd.py
git commit -m "launch: --refire 按台账原命令补射死分片(只补死的,验卡 fail-closed)"
```

---

### Task 13: 两个排卡发射器接同一套登记

**Files:**
- Modify: `ops/launch_probe.py`（`has_session/launch` 换成 import `launch_common`；`main()` 发射循环里 RUNMETA 之后补台账+record）
- Modify: `ops/launch_eval.py`（同样）

**Interfaces:**
- Consumes: `launch_common.probe_free/register_all/has_session/tmux_launch`。

- [ ] **Step 1: launch_probe 改造**：
  1. 删掉本地 `has_session`/`launch`（:47-62），换 `from launch_common import has_session, tmux_launch, probe_free, register_all`（sys.path 已有 ops）。原 `launch()` 的调用点改为拼 inner 后调 `tmux_launch`（inner 模板一致，行为不变）。
  2. 发射前逐格 `probe_free(host, str(gpu))`，不 FREE 的格打印原因**跳过该格**（排卡表半空常见，整表拒绝会把好格拖死——与 launch 单任务"整次拒绝"口径不同，注释里写明原因）。
  3. 每格 LAUNCHED 后：RUNMETA 照旧，再 `register_all(run_id=rid, workdir=str(WD), pieces=[该格 rich piece], track=f"probe_{args.batch}", cmd_display=cmd, outdir=None)`——outdir 已由 RUNMETA 自己写了，register_all 里 RUNMETA 一步传 `outdir=None` 跳过，别写两遍。record start 若因 run_id 已存在而 rc≠0（smoke 后重发 full 的正常路径是不同 run_id，不该撞；撞了说明重复发射）→ 打 WARN 继续，不中断发射循环。
- [ ] **Step 2: launch_eval 同样四处**（track=f"eval_{args.batch}"；rid 用 sess 去掉前缀 eval_ 的 `{batch}_{model}_{cell}`）。
- [ ] **Step 3: 验证**：`python3 run.py launch-probe smoke --batch zz --data-root pipeline/data/<现存任一> --env appworld --model q35 --dry-run --allow-dirty` 照常打印；单测跑 `python3 -m unittest discover -s tests -v` 全绿（launch_common 的测试覆盖了 register_all）。
- [ ] **Step 4: Commit**

```bash
git add ops/launch_probe.py ops/launch_eval.py
git commit -m "launch: 排卡发射器接 launch_common(FREE 实探+自动台账/record,RUNMETA 照旧)"
```

---

### Task 14: 事故触发（采样器拉事故 agent）

**Files:**
- Modify: `ops/sampler.py`（实装 `maybe_trigger_incidents`）
- Create: `tests/test_incidents.py`

**Interfaces:**
- Produces: `monitor/incidents.jsonl`（append）：`{"id": "<job>#<idx>@<epoch>", "t", "job", "idx", "session", "verdict", "log", "allow_refire", "agent_pid"}`；`monitor/incidents/<id>.out` = 事故 agent 的 stdout。
- 触发规则（设计 §5，全在纯函数 `should_trigger(row, ps) -> (bool, allow_refire)` 里判，单测压它）：`row["escalated"]` 为真，且 `ps["incident_open"]` 为空（同一次事故只拉一次；分片判定回到健康/warm-up/已完成时清 `incident_open`）。`allow_refire` = (判定==已挂 且 `ps["refires"] == 0`)。

- [ ] **Step 1: 写失败测试**：`should_trigger` 四种情形（首次已挂→(True,True)；已挂但 refires=1→(True,False)；已有 incident_open→(False,_)；疑似卡死未达升级线→(False,_)）；`build_incident_prompt(row, allow_refire)` 输出里含日志路径、`gpu-jobs json` 命令、补射命令或"不许补射"。

- [ ] **Step 2: 实现**。agent 拉起：

```python
def spawn_agent(incident, prompt):
    out = open(MONITOR_DIR / "incidents" / f"{incident['id']}.out", "w")
    p = subprocess.Popen(
        ["claude", "-p", prompt, "--model", "opus",
         "--dangerously-skip-permissions"],
        stdout=out, stderr=subprocess.STDOUT,
        cwd="/home/y-guo/reproduce/new1", start_new_session=True)
    return p.pid
```

  实施时先跑 `claude --help` 核对无头模式与免确认旗标的当前拼写（`-p/--print`、`--model`、`--dangerously-skip-permissions` 或 `--permission-mode bypassPermissions`），以 help 输出为准改这一处。提示词模板（写成模块级常量 `INCIDENT_PROMPT`，`{}` 占位 format）：

```
你是 new1 工程的事故 agent,只干"把实验办好"一件事,不写给人看的报告。
事故: 任务 {job} 分片 {idx}(session {session},host {host},GPU {gpus})判定 {verdict}。
日志: {log}
先看现场: tail -c 8192 '{log}' | tr '\r' '\n' | tail -40
台账 json: cd /home/y-guo/reproduce/new1 && python3 run.py gpu-jobs json
规则(不许越线):
- {refire_clause}
- 判定是 疑似卡死: 只读日志定位原因,禁止 kill 任何 session、禁止改任何文件。
- 只碰这一个分片,别的任务一概不动。
- 结束时输出一行: DONE <你做了什么,15 字内>。
```

  `refire_clause` 两个取值：允许时 =「判定是 已挂: 读日志定位死因后补射一次: `python3 run.py launch --refire {job} --idx {idx}`;原卡被占(命令会报错)时 `python3 run.py gpu-jobs free` 挑空卡后加 `--piece <host>:<gpus>` 重试一次」；不允许时 =「这个分片补射额度已用完: 只验尸,不许再发射任何东西」。
  触发后 `ps["incident_open"] = incident_id`；采样器**不等** agent 结束（Popen 即走）；下一轮判定回到 已完成/健康/warm-up 中 时清 `incident_open`。

- [ ] **Step 3: 跑测试通过 + 手动演练**：造一个假任务（register 一个指向不存在 session 的 piece + 有心跳未完的日志）→ `python3 run.py sampler --once` → 断言 incidents.jsonl 出现一条、`incidents/<id>.out` 里事故 agent 真跑了（读到 DONE 行）。演练完 `gpu-jobs finish <假任务> --force` 清场。

- [ ] **Step 4: Commit**

```bash
git add ops/sampler.py tests/test_incidents.py
git commit -m "monitor: 事故触发(升级线->claude -p opus,防抖+补射限额,记录 incidents)"
```

---

### Task 15: vLLM 服务档（端口探测 + 吞吐行显示）

**Files:**
- Modify: `ops/sampler.py`（`read_beats` 对 `kind=="service"` 的分片改走 `read_vllm_stats`；`probe_port` 核对）
- Create: `tests/test_vllm_stats.py`

- [ ] **Step 1: fixture 用已核实的真实样本**（2026-08-08 从
  `/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_diag_srv_a.log`
  取的原文，vllm 0.26.0，格式串在
  `envs/vllm-env/lib/python3.12/site-packages/vllm/v1/metrics/loggers.py:263-313`）：

```
(APIServer pid=263921) INFO 08-02 19:50:14 [loggers.py:310] Engine 000: Avg prompt throughput: 785.1 tokens/s, Avg generation throughput: 671.8 tokens/s, Running: 4 reqs, Waiting: 0 reqs, GPU KV cache usage: 11.2%, Prefix cache hit rate: 97.1%
```

  已知事实：默认每 10 秒一条（`VLLM_LOG_STATS_INTERVAL`，`vllm/envs.py:47`）；
  引擎空闲时该行降级 debug 不进 stdout——所以吞吐行断流不算停摆，判定只看端口
  （设计 §4 已定）。另注意 vLLM serve 的日志不在 `<workdir>/logs/`，发射器把它
  重定向到 `/net/.../vllm_cache/logs/`（`envs/serve_logs/launch_vllm_awdiag.py`
  写死）——服务分片 register 时 log 字段要填真实路径。
- [ ] **Step 2: 写失败测试**：`parse_vllm_stats(tail_text)` 从上面 fixture 行里抽 `{"gen_tok_s": 671.8, "prompt_tok_s": 785.1, "running": 4}`；无匹配 → None。
- [ ] **Step 3: 实现**：service 分片不走 heartbeat.parse，`read_vllm_stats(log)` 抓吞吐行 → row 的 `tok_out` 速率显示位（只做显示，不进判定——判定走 `probe_port`，`/health` 路径实测：起服务的机器上 `curl -s -o /dev/null -w '%{http_code}' localhost:<port>/health`，vLLM OpenAI server 返回 200 无 body；对不上就以实测为准改 `probe_port`）。
- [ ] **Step 4: 跑测试通过 + Commit**

```bash
git add ops/sampler.py tests/test_vllm_stats.py
git commit -m "monitor: vLLM 服务档(端口探测进判定,吞吐行只做速率显示)"
```

---

### Task 16: 文档回写 — gpu-run skill 与两份方法论

**Files:**
- Modify: `.claude/skills/gpu-run/SKILL.md`、`references/launch-methodology.md`、`references/monitor-methodology.md`

- [ ] **Step 1: SKILL.md**。Phase 4 整段改写：发射三步（commit → `python3 run.py launch <task> ... --run-id X --track Y --piece host:gpus` → 读它打印的监控入口交给用户），双登记/RUNMETA/record 手打命令段全删（launch 保证）；Phase 4 第 6 步交给用户的命令换成 `python3 run.py gpu-jobs`、`watch`、浏览器 `localhost:8377`；Phase 5 改写为采样器条款：常设巡检撤销，判定/升级/事故 agent 由采样器负责，Claude 只在用户问起或事故记录有内容时派 job-monitor 读 `gpu-jobs json`；Phase 6a 五连保留（已完成只是判定，销号仍 fail-closed）。Phase 3 smoke 段补一句：smoke 也可用 `launch --dry-run` 先看命令。
- [ ] **Step 2: launch-methodology.md**：tmux 模板一节改为「launch 替你做了什么」（模板本身留作 `--cmd` 逃生口的参考）；挑卡规则一节保留（挑卡仍是 agent 的判断）；分片一节改成 shardable + 多 `--piece` 用法。
- [ ] **Step 3: monitor-methodology.md**：两点测速/ETA 修正/tqdm 解析三节改写为「程序职责说明」（口径 = `ops/verdicts.py` 的 DEFAULTS，表格列出六格判定与两线公式），保留「decision tree」一节但判断输入改成判定值不是原始日志。
- [ ] **Step 4: Commit**

```bash
git add .claude/skills/gpu-run/
git commit -m "docs: gpu-run skill 改写(Phase4 收成一条 launch,Phase5 巡检制度换采样器)"
```

---

### Task 17: 文档回写 — 两个 agent 定义

**Files:**
- Modify: `.claude/agents/job-monitor.md`、`.claude/agents/gpu-runner.md`

- [ ] **Step 1: job-monitor.md** 瘦身：删两点测速、ETA 手算、tqdm 解析全部操作细节（改一句「判定/速率/ETA 由采样器算好,你读 `python3 run.py gpu-jobs json` 的现成结论」）；保留只读铁律、验尸流程（读日志定位死因）、报告格式（健康表的"判定"列直接抄 json 的 verdict）；加一段与事故 agent 的分工：你是人派的检查员，半夜自动处置的是采样器拉的事故 agent，别替它补射。
- [ ] **Step 2: gpu-runner.md**：第 3 条（发射命令从 run.py 拿）与第 4 条（双登记）合并改写为「发射一律 `python3 run.py launch ...`,验卡/tmux/三处登记它包了;launch-probe/launch-eval 两个排卡发射器照旧直接跑（它们内部同样自动登记）」；报告格式的「登记回执」节改成贴 launch 的输出。
- [ ] **Step 3: Commit**

```bash
git add .claude/agents/job-monitor.md .claude/agents/gpu-runner.md
git commit -m "docs: job-monitor 瘦身读现成判定;gpu-runner 发射段改 launch"
```

---

### Task 18: 文档回写 — probe-pipeline、handoff、根文档

**Files:**
- Modify: `.claude/skills/probe-pipeline/SKILL.md`（:74-75 收尾链、:134 G16、:172-173 释放销号、:221-222 agent 分工表）、`references/gates.md`（G2/G16/G17）、`references/stage-commands.md`（:19、:352）、`references/invariants.md`（记账双写行）、`references/extending.md`（:130 + 新脚本清单加「接心跳」一条）
- Modify: `.claude/skills/handoff/SKILL.md:42`（进度来源指 `gpu-jobs json`/采样历史）
- Modify: `CLAUDE.md`（gpu-run 段加一句：发射与登记收成 `run.py launch`，用户自助监控 = `gpu-jobs watch` + 网页 8377）、`MAP.md`（gpu_jobs.py/launch_probe.py/launch_eval.py 三行更新；heartbeat.py/verdicts.py/sampler.py/launch_cmd.py/launch_common.py 各加一行，格式照现有表）、`ops/gpu_state.md` 页首指引补采样器一行

- [ ] **Step 1: 逐文件改**。G16 双登记的新表述统一为：「launch 自动写三处;手搓/register 补录路径仍在,漏了照旧算违规」。invariants 的记账双写行改为「双写由 launch 保证;绕过 launch 手搓发射的,双登记责任回到人」。extending.md 新脚本清单加一条硬项：「新采集/训练/评测脚本必须接 `ops/heartbeat.py`(进主循环 emit(0,...),每单位 emit,收尾 status=done),不接的脚本在窗口里永远是 warm-up 中」。
- [ ] **Step 2: Commit**

```bash
git add .claude/skills/probe-pipeline/ .claude/skills/handoff/SKILL.md CLAUDE.md MAP.md ops/gpu_state.md
git commit -m "docs: probe-pipeline/handoff/CLAUDE/MAP/gpu_state 对齐 launch+采样器"
```

---

### Task 19: 收官自检

- [ ] **Step 1: 全量测试与体检**

Run: `python3 -m unittest discover -s tests -v && python3 run.py selfcheck`
Expected: 全绿；selfcheck 全部就位

- [ ] **Step 2: 文档一致性扫尾**：`grep -rn "双登记\|record start --run-id\|gpu-jobs register" .claude/ CLAUDE.md MAP.md` 逐条确认剩下的引用都是「launch 自动做/补录路径」语境，没有残留「手打三条命令」的旧流程叙述。
- [ ] **Step 3: CONTEXT.md 复核**：词汇表与实现对一遍（尤其 shardable、监控参数字段名），有出入按实现改词汇表并注明日期。
- [ ] **Step 4: 最终 Commit + 汇报**：改动清单、新命令速查（launch/refire/sampler/watch/网页）、看门狗 crontab 行、已知限制（v1 不做的清单照设计 §9）。
