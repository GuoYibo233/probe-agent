# Long-running task monitoring and launch — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land `docs/design/2026-08-08-gpu-monitor-launch.md`: scripts emit heartbeats, the sampler computes verdicts, three exits read the same sampling history, an incident automatically pulls up an incident agent to refire, and launching collapses into one `run.py launch` subcommand.

**Architecture:** Four new modules (`ops/heartbeat.py` the heartbeat, `ops/verdicts.py` the pure-function verdict engine, `ops/sampler.py` the resident sampler, `ops/launch_common.py`+`ops/launch_cmd.py` for launching) plus three kinds of rework (wiring scripts up with heartbeats, changing the `ops/gpu_jobs.py` exits to read the sampling history, wiring the two queueing launchers into the same registration). The verdict engine is a pure function with zero IO, so unit tests carry the full weight there; all the IO lives in the sampler, tested with an integration smoke test using `--once` mode against a fake log.

**Tech Stack:** Pure Python standard library (every new module under ops has zero third-party dependencies, any venv can import it); tests use stdlib `unittest`; the web page uses `http.server`, no frontend dependency.

## Global Constraints

- New modules under ops **use the standard library only** (design §2: all 11 interpreters must be able to import them).
- Every task must pass `python3 run.py selfcheck` at wrap-up before committing (CLAUDE.md: extension code and registry updates land in the same commit).
- Tests are run uniformly with `python3 -m unittest discover -s tests -v` (run from the repo root; this machine has no `python`, only `python3`).
- The sampling history / incident record land on NFS: `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/` (large artifacts do not go into home, do not go into git; `.gitignore` does not need to change — the directory is outside the repo).
- The incident agent's model is pinned to **opus** (specified by the user on 2026-08-08, not sonnet).
- Verdict names and their exact meaning follow `CONTEXT.md`'s glossary and design document §4 without exception; no inventing new ones.
- Do not read or write anything under `/home/y-guo/ACL2026`.
- Constants are all centralized in `ops/verdicts.py`'s `DEFAULTS`; no scattering them as hardcoded values (design §10: producing a false positive should be tunable from one place).

---

### Task 1: Heartbeat module `ops/heartbeat.py`

**Files:**
- Create: `ops/heartbeat.py`
- Create: `tests/test_heartbeat.py`

**Interfaces:**
- Produces: `emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None, status=None, stream=None)`; `parse(line) -> dict | None`; the constant `PREFIX = "@hb "`. Every later task uses these two signatures.

- [ ] **Step 1: Write the failing test** `tests/test_heartbeat.py` (create the `tests/` directory together with an empty `tests/__init__.py`):

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
        self.assertNotIn("tok_in", rec)          # optional field not given -> doesn't appear

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
        self.assertIsNone(heartbeat.parse('@hb {"done": 1}'))  # missing a required field


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `python3 -m unittest tests.test_heartbeat -v`
Expected: FAIL (`ModuleNotFoundError: heartbeat`)

- [ ] **Step 3: Implement `ops/heartbeat.py`**

```python
#!/usr/bin/env python3
"""Heartbeat: the sole channel by which a long-running task script reports progress to the
sampler (design document §2).

One line = the prefix "@hb " + one JSON object. Required: done/total/unit/ts, optional:
tok_in/tok_out (cumulative values)/loss/status ("done" = normal finish).
Before entering the main loop, emit(0, total, unit) once first -- that is the marker for
"model loading finished."
Standard library only: any venv must be able to import this file.
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
    """Heartbeat line -> dict; returns None if the line is not a valid heartbeat (the monitoring
    side trusts only this entry point)."""
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

- [ ] **Step 4: Run the test, confirm it passes**

Run: `python3 -m unittest tests.test_heartbeat -v`
Expected: PASS (4 test cases)

- [ ] **Step 5: Commit**

```bash
git add ops/heartbeat.py tests/__init__.py tests/test_heartbeat.py
git commit -m "monitor: heartbeat module ops/heartbeat.py (emit/parse, stdlib-only)"
```

---

### Task 2: Verdict engine `ops/verdicts.py` (pure functions)

**Files:**
- Create: `ops/verdicts.py`
- Create: `tests/test_verdicts.py`

**Interfaces:**
- Produces: the `DEFAULTS` config dict; `typical_gap_s(beat_ts, cfg)`; `stall_line_s(beat_ts, cfg, override=None)`; `rates(first_beat, recent_beats, cfg)`; `judge(p, cfg) -> (verdict string, whether the escalation line is reached)`. The verdict string constants `V_DONE/V_DEAD/V_STALL/V_WARMUP/V_SLOW/V_OK` = "done"/"dead"/"stalled"/"warming up"/"slowing down"/"healthy".
- The input `p` to `judge` (Task 4, the sampler, is responsible for assembling this dict): `kind` ("batch"|"service"), `alive` (True|False|None = probe failed, carry over the previous round), `done`, `total`, `status`, `has_beat`, `beat_age_s` (time since the most recent new heartbeat was seen, under the sampler's own clock), `since_launch_s`, `stall_s` (None = not enough interval samples, use the warm-up ceiling as a stand-in), `escalate_s` (None = stall line × escalate_mult), `warmup_s`, `avg_rate`, `recent_rate`, `port_ok`, `port_ever_ok`, `port_fail_rounds`.

- [ ] **Step 1: Write the failing test** (one cell of the design §4 verdict table at a time, plus edge cases, at least one test case per cell):

```python
import unittest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))
import verdicts as V


def p(**kw):
    """Default state for a batch piece; overridden per cell in the unit tests."""
    base = dict(kind="batch", alive=True, done=5, total=100, status=None,
                has_beat=True, beat_age_s=10.0, since_launch_s=600.0,
                stall_s=180.0, escalate_s=None, warmup_s=1800.0,
                avg_rate=1.0, recent_rate=1.0,
                port_ok=None, port_ever_ok=False, port_fail_rounds=0)
    base.update(kw)
    return base


class TestJudge(unittest.TestCase):
    def test_done_beats_everything(self):        # priority 1: done overrides alive
        self.assertEqual(V.judge(p(done=100))[0], V.V_DONE)
        self.assertEqual(V.judge(p(alive=False, status="done", done=3))[0],
                         V.V_DONE)

    def test_dead(self):                          # priority 2: includes dying with zero heartbeats
        v, esc = V.judge(p(alive=False))
        self.assertEqual(v, V.V_DEAD)
        self.assertTrue(esc)                      # dead reaches the escalation line on the spot
        v, _ = V.judge(p(alive=False, has_beat=False, done=None, total=None))
        self.assertEqual(v, V.V_DEAD)

    def test_stall_and_escalate(self):            # priority 3 + escalation line
        v, esc = V.judge(p(beat_age_s=200.0))     # stalled 200s > stall line 180s
        self.assertEqual(v, V.V_STALL)
        self.assertFalse(esc)                     # has not passed 180x3
        v, esc = V.judge(p(beat_age_s=600.0))
        self.assertEqual(v, V.V_STALL)
        self.assertTrue(esc)

    def test_warmup_and_warmup_timeout(self):     # priority 4 + ceiling
        self.assertEqual(V.judge(p(has_beat=False, since_launch_s=300.0))[0],
                         V.V_WARMUP)
        v, _ = V.judge(p(has_beat=False, since_launch_s=2000.0))
        self.assertEqual(v, V.V_STALL)            # past the warm-up ceiling, turns into suspected stall

    def test_stall_line_fallback_when_few_intervals(self):
        # not enough interval samples: stall_s=None, a long first item doesn't false-positive
        # (stalled 400s < warmup 1800s)
        self.assertEqual(V.judge(p(stall_s=None, beat_age_s=400.0))[0], V.V_OK)

    def test_slow_needs_recent_rate(self):        # priority 5
        self.assertEqual(V.judge(p(recent_rate=0.4))[0], V.V_SLOW)
        self.assertEqual(V.judge(p(recent_rate=None))[0], V.V_OK)

    def test_probe_fail_keeps_previous_alive(self):
        # alive=None (unknown after folding in a probe failure) does not judge dead
        self.assertNotEqual(V.judge(p(alive=None))[0], V.V_DEAD)

    def test_service(self):
        s = dict(kind="service", alive=True, done=None, total=None, status=None,
                 has_beat=False, beat_age_s=0.0, since_launch_s=120.0,
                 stall_s=None, escalate_s=None, warmup_s=1800.0,
                 avg_rate=None, recent_rate=None,
                 port_ok=False, port_ever_ok=False, port_fail_rounds=0)
        self.assertEqual(V.judge(s)[0], V.V_WARMUP)          # the port has never answered yet
        s.update(port_ok=True, port_ever_ok=True)
        self.assertEqual(V.judge(s)[0], V.V_OK)
        s.update(port_ok=False, port_fail_rounds=3)
        self.assertEqual(V.judge(s)[0], V.V_STALL)           # 3 consecutive rounds unanswered
        s.update(alive=False)
        self.assertEqual(V.judge(s)[0], V.V_DEAD)


class TestLinesAndRates(unittest.TestCase):
    def test_typical_gap_median(self):
        ts = [0, 10, 20, 30, 100]                 # intervals 10,10,10,70 -> median 10
        self.assertEqual(V.typical_gap_s(ts), 10)

    def test_stall_line_floor(self):
        ts = [0, 1, 2, 3, 4]                      # dense heartbeats: 5x1s < the 3x60s floor
        self.assertEqual(V.stall_line_s(ts), 180.0)
        self.assertEqual(V.stall_line_s(ts, override=42.0), 42.0)
        self.assertIsNone(V.stall_line_s([0, 10]))  # only 1 interval -> None

    def test_rates(self):
        first = {"ts": 0.0, "done": 0}
        recent = [{"ts": 100.0 + i * 10, "done": 50 + i} for i in range(5)]
        avg, rc = V.rates(first, recent)
        self.assertAlmostEqual(avg, 54 / 140.0)   # (54-0)/(140-0)
        self.assertAlmostEqual(rc, 4 / 40.0)      # Δdone/Δts within the window
        self.assertEqual(V.rates(first, recent[:1]), ((50 - 0) / 100.0, None))
        self.assertEqual(V.rates(None, []), (None, None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `python3 -m unittest tests.test_verdicts -v`
Expected: FAIL (`ModuleNotFoundError: verdicts`)

- [ ] **Step 3: Implement `ops/verdicts.py`**

```python
#!/usr/bin/env python3
"""Verdict engine: pure functions, zero IO (design document §4). The sampler feeds state in,
gets a verdict out.
The six-cell verdict is judged by a fixed priority order, stopping at the first match:
done -> dead -> suspected stall -> warming up -> slowed -> healthy.
Clock discipline: never compare clocks across machines -- beat_age_s/since_launch_s are computed
by the sampler using its own clock and fed in; the heartbeat ts is only diffed against itself,
on the same machine, inside rates(). All constants are collected in DEFAULTS; hardcoding
elsewhere is not allowed.
"""
from statistics import median

V_DONE, V_DEAD, V_STALL = "done", "dead", "suspected stall"
V_WARMUP, V_SLOW, V_OK = "warming up", "slowed", "healthy"

DEFAULTS = dict(
    sample_interval_s=60.0,   # the interval of one sampler round
    stall_mult=5.0,           # stall line = 5 x the typical heartbeat interval
    stall_floor_samples=3,    # stall line floor = 3 sampling rounds (below sampling granularity, can't tell stopped from not-yet)
    escalate_mult=3.0,        # escalation line = stall line x 3
    warmup_line_s=1800.0,     # warm-up ceiling, 30 minutes by default
    recent_beats=10,          # recent rate window: the most recent <=10 heartbeats
    typical_beats=20,         # typical heartbeat interval: median of the most recent <=20 intervals
    min_intervals=3,          # need at least 3 intervals before using the adaptive stall line
    slow_ratio=0.5,           # slowed = recent rate < average x 0.5
    port_fail_rounds=3,       # service: 3 consecutive rounds with no port answer = suspected stall
)


def typical_gap_s(beat_ts, cfg=DEFAULTS):
    """Median of the most recent <=typical_beats heartbeat intervals; returns None if fewer than
    min_intervals intervals are available."""
    ts = list(beat_ts)[-(cfg["typical_beats"] + 1):]
    gaps = [b - a for a, b in zip(ts, ts[1:]) if b >= a]
    if len(gaps) < cfg["min_intervals"]:
        return None
    return median(gaps)


def stall_line_s(beat_ts, cfg=DEFAULTS, override=None):
    """The stall line (seconds). override = the --stall-line given at launch time; returns None
    if there are not enough samples (the caller falls back to the warm-up ceiling, so a long
    task/long step does not false-positive at the start)."""
    if override is not None:
        return float(override)
    gap = typical_gap_s(beat_ts, cfg)
    if gap is None:
        return None
    return max(cfg["stall_mult"] * gap,
               cfg["stall_floor_samples"] * cfg["sample_interval_s"])


def rates(first_beat, recent_beats, cfg=DEFAULTS):
    """(average rate, recent rate), in done/second; None where it cannot be computed.
    first_beat: the first heartbeat {'ts','done'} (stored in the sampler's cumulative state,
    does not depend on the tail of the log). recent_beats: the most recent <=typical_beats
    heartbeats (ascending). The denominator is always on the heartbeat timeline."""
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
    """Exactly one cell per piece per round. Returns (verdict, whether the escalation line is
    reached). Done and slowed do not apply to service pieces (design §4, end); services go
    through _judge_service."""
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

- [ ] **Step 4: Run the test, confirm it passes**

Run: `python3 -m unittest tests.test_verdicts -v`
Expected: PASS (11 test cases)

- [ ] **Step 5: Commit**

```bash
git add ops/verdicts.py tests/test_verdicts.py
git commit -m "monitor: verdict engine ops/verdicts.py (six-cell priority + adaptive two lines + rates, pure functions)"
```

---

### Task 3: Wire the collection script up with heartbeats (`run_appworld.py`)

**Files:**
- Modify: `envs/collect/run_appworld.py:14-15` (the import area), `:76` (before the main loop), `:78-124` (the loop body)

**Interfaces:**
- Consumes: Task 1's `heartbeat.emit`. The token data source is `g["usage"]["in"]` / `g["usage"]["out"]` in the dict returned by `common.Chat.__call__` (`envs/collect/common.py:161,182,220-221`, already there, no need to change common.py).

- [ ] **Step 1: Add the import** (after the line `sys.path.insert(0, str(Path(__file__).parent))`):

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import heartbeat  # noqa: E402
```

- [ ] **Step 2: Emit done=0 before the main loop** (after `print(f"shard {args.shard_id}...")`, before `for tid in ids:`):

```python
tok_in = tok_out = 0
n_done = 0
heartbeat.emit(0, len(ids), "task", tok_in=0, tok_out=0)
```

- [ ] **Step 3: Accumulate tokens and emit a heartbeat per item**. Change two spots:
  1. After `g = chat(msgs)` (before `log.w({"type": "gen", ...})`), add:

```python
                tok_in += g["usage"]["in"]
                tok_out += g["usage"]["out"]
```

  2. After each item's wrap-up `print(f"task={tid} steps=...")`, add (also add one before the `continue`
     of the resume SKIP branch, since a SKIPped item still advances done):

```python
            n_done += 1
            heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in, tok_out=tok_out)
```

  At the end of the loop (the end of `main()`), add the normal-finish marker:

```python
    heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in, tok_out=tok_out,
                   status="done")
```

- [ ] **Step 4: Verify**

Run: `envs/appworld/venv/bin/python -c "import ast,sys; ast.parse(open('envs/collect/run_appworld.py').read()); print('syntax ok')"` then `envs/appworld/venv/bin/python envs/collect/run_appworld.py --help`
Expected: `syntax ok`; --help prints normally (the heartbeat import succeeds under the appworld venv -- this is the real-world test of the "stdlib only" constraint)

- [ ] **Step 5: Commit**

```bash
git add envs/collect/run_appworld.py
git commit -m "collect: wire run_appworld up with heartbeats (per-item done/cumulative tokens, done=0 marks loading finished)"
```

---

### Task 4: Wire the training scripts up with heartbeats (four cells)

**Files:**
- Modify: `pipeline/train/train_mbert_tool.py`, `train_mbert_extract.py`, `train_causal_tool.py`, `train_causal_callgen.py` (same pattern across all four files; the location of each file's `log()` closure is in `probe-pipeline/references/extending.md:130`: mtool:132-138 / mext:265-267 / ctool:313-315 / cgen:234-236, treat line numbers as approximate, re-check with grep)

**Interfaces:**
- Consumes: `heartbeat.emit`. Total steps = each script's already-computed `steps` variable (mtool has it at `train_mbert_tool.py:172`), current step = `gstep`, loss = the running mean already in the existing step log.

- [ ] **Step 1: Three insertion points for mtool** (repeat at the same anchors for the other three cells):
  1. In the file-header import area, add:

```python
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat
```

  2. After `log(event="start", ...)` (mtool:185), add: `heartbeat.emit(0, steps, "step")`
  3. After the `log(event="step", ...)` under `gstep % 50 == 0` (mtool:208-210), add:

```python
                    heartbeat.emit(gstep, steps, "step",
                                   loss=round(run / (50 * args.accum), 4))
```

  Note: this line is inserted **before** the `run = 0.0` reset, taking the same running mean.
  4. After `log(event="done", ...)` (mtool:222), add: `heartbeat.emit(gstep, steps, "step", status="done")`

- [ ] **Step 2: Repeat for the other three cells**. First run `grep -n "event=\"start\"\|event=\"step\"\|event=\"done\"\|steps =" pipeline/train/train_mbert_extract.py pipeline/train/train_causal_tool.py pipeline/train/train_causal_callgen.py` to find the anchors, then insert the same four spots per file (go by each file's actual variable names -- the total-steps variable, the global-step variable, and the loss running-mean expression should be copied from what already exists in that file's own `log(event="step")` call).

- [ ] **Step 3: Verify**

Run: `for f in pipeline/train/train_*.py; do mbert-env/bin/python -c "import ast; ast.parse(open('$f').read())" && echo "$f ok"; done`
Expected: four "ok" lines. Then `mbert-env/bin/python -c "import sys; sys.path.insert(0,'ops'); import heartbeat; print('import ok')"` and `cprobe-env/bin/python -c "<same>"` -- both training venvs must be able to import it.

- [ ] **Step 4: Commit**

```bash
git add pipeline/train/train_mbert_tool.py pipeline/train/train_mbert_extract.py \
        pipeline/train/train_causal_tool.py pipeline/train/train_causal_callgen.py
git commit -m "train: wire the four training cells up with heartbeats (unit=step, reports the running loss)"
```

---

### Task 5: Wire the evaluation scripts up with heartbeats (three of them)

**Files:**
- Modify: `pipeline/eval/eval_tool.py` (anchor `:69`'s `print(f"scored {i}/{len(rows)}")`), `pipeline/eval/eval_mbert_call.py` (anchor `:127`'s `print(f"extracted {i}/...")`), `pipeline/eval/eval_causal_call.py` (the batch loop starting at anchor `:207`)

**Interfaces:**
- Consumes: `heartbeat.emit`. Use unit `"item"` (evaluation's progress denominator is the sample count).

- [ ] **Step 1: Insert per file**. Add the same four import lines as Task 4 (parents[2] also lands at the repo root for pipeline/eval). Before the main batch loop starts: `heartbeat.emit(0, <total-count expression>, "item")`; alongside every existing progress print: `heartbeat.emit(<current i>, <total>, "item")`; at the script's normal end point (after writing the report file): `heartbeat.emit(<total>, <total>, "item", status="done")`. eval_causal_call.py has no existing progress print, so add one at the tail of the loop body of `:207`'s `for i in range(0, len(prompts), bs):` at the same cadence (one every 50 batches). For files with multiple loop segments (eval_tool has a score segment and a replay segment), use **the longest segment** as the progress denominator, and don't emit heartbeats from the other segments -- one script, one progress axis, don't emit two.

- [ ] **Step 2: Verify**

Run: `for f in pipeline/eval/eval_tool.py pipeline/eval/eval_mbert_call.py pipeline/eval/eval_causal_call.py; do python3 -c "import ast; ast.parse(open('$f').read())" && echo "$f ok"; done`
Expected: three "ok" lines

- [ ] **Step 3: Commit**

```bash
git add pipeline/eval/eval_tool.py pipeline/eval/eval_mbert_call.py pipeline/eval/eval_causal_call.py
git commit -m "eval: wire the three evaluation scripts up with heartbeats (unit=item)"
```

---

### Task 6: Sampler core `ops/sampler.py` (the sampling loop, without the web page or incidents yet)

**Files:**
- Create: `ops/sampler.py`
- Create: `tests/test_sampler.py`
- Modify: `run.py` (add a `"sampler"` entry to TASKS)

**Interfaces:**
- Consumes: `gpu_jobs.load_reg` / `gpu_jobs.live_sessions` / `gpu_jobs.DEFAULT_HOSTS` (`ops/gpu_jobs.py:37,62,107`, imported and reused, not duplicated); `heartbeat.parse`; `verdicts.judge/rates/stall_line_s`.
- Produces (the on-disk format later tasks and exits read):
  - `MONITOR_DIR = /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/` (overridable via the `NEW1_MONITOR_DIR` env var -- unit tests point it at a tmp dir)
  - `latest.json` (atomic write): `{"sampled_at": <epoch>, "rows": [...], "extras": {...}, "incidents_tail": [...]}`; each row: `{"job","idx","host","gpus","session","kind","verdict","escalated","done","total","unit","progress_pct","avg_rate","recent_rate","tok_in","tok_out","loss","eta_s","log","probe_failed","refires"}`
  - `state.json` (atomic write): `{"<job>#<idx>": {"first_beat":{"ts","done"},"recent_beats":[<=20 entries of {"ts","done","tok_in","tok_out","loss","status"}],"last_new_beat_mono","last_done","launched_at","alive_last","probe_fail_rounds","port_ever_ok","port_fail_rounds","verdict","escalated_since_mono","incident_open","refires"}`
  - `history/<job>.jsonl` (append): one row per piece per round (the same row as latest, plus `"t"`)
  - Function `sample_once(now_mono, now_wall) -> latest dict`; `main()` supports `--once` (sample one round then exit, for smoke testing) and `--interval N`

- [ ] **Step 1: Write the failing test**. Fixture: build a `jobs.json` in a tmp dir (one task, two pieces, each piece's `log` points to a hand-written log file in the tmp dir -- one log has three heartbeat lines at the tail, the other has no heartbeat, just plain text); monkeypatch `sampler.live_sessions = lambda hosts: {"tokyo106": {"new1_x_t106g0"}}` (piece 0's name is alive, piece 1's name is not in the set). Assert on the rows returned by `sample_once()`: piece 0's verdict in {healthy, warming up} (has a heartbeat, alive), piece 1's verdict = dead; the latest.json / state.json / history files are really written to disk and can be json.load'd; run one more round and confirm piece 0's `recent_beats` does not append the same heartbeat twice (same ts, same done does not count as a new heartbeat). Test skeleton:

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
        self.assertIn(rows[0]["verdict"], ("healthy", "warming up"))
        self.assertEqual(rows[1]["verdict"], "dead")
        self.assertEqual(rows[0]["tok_in"], 210)
        mon = pathlib.Path(os.environ["NEW1_MONITOR_DIR"])
        self.assertTrue((mon / "latest.json").exists())
        self.assertTrue((mon / "state.json").exists())
        self.assertTrue((mon / "history" / "x.jsonl").exists())
        n1 = len(json.loads((mon / "state.json").read_text())
                 ["x#0"]["recent_beats"])
        self.S.sample_once()                      # the log hasn't changed, heartbeats aren't recounted
        n2 = len(json.loads((mon / "state.json").read_text())
                 ["x#0"]["recent_beats"])
        self.assertEqual(n1, n2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test, confirm it fails** (`ModuleNotFoundError: sampler`)

- [ ] **Step 3: Implement `ops/sampler.py`**. Structure (write the functions one by one, behavior pinned down by the comments):

```python
#!/usr/bin/env python3
"""Sampler: the resident monitoring process for long-running tasks (design document §3-§5).
Each round: read the ledger -> tail the logs to pick up heartbeats (read locally from NFS) ->
ssh to probe liveness -> verdicts.judge -> append to the sampling history + atomically write
latest.json/state.json.
This file only does IO and accumulates state; the verdict logic lives entirely in
ops/verdicts.py. stdlib only.
Usage: sampler.py [--once] [--interval 60] [--port 8377] (the web page is added in Task 7)
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
    """All heartbeat lines in the last 256KB of the log (ascending). tqdm's \r is turned into \n first."""

def atomic_write(path, obj): ...        # tmp + os.replace, the same pattern as run.py save_state

def load_state(): ...                    # state.json missing/corrupt -> {}

def piece_key(job, idx): ...             # f"{job}#{idx}"

def update_piece_state(st, job, idx, piece, beats, alive, now_mono):
    """Accumulate one piece's cumulative state (design §3):
    - launched_at changed (refired) -> the whole state block reopens, refires += 1
    - entries in beats newer than last_done/last_ts are appended to recent_beats (capped at <=20),
      and last_new_beat_mono = now_mono is refreshed
    - first_beat is recorded only the first time a heartbeat is seen
    - alive: None (probe failed) -> carry over alive_last, probe_fail_rounds += 1;
      True/False -> taken directly, probe_fail_rounds = 0
    - service type: port_ok comes from probe_port(), port_ever_ok/port_fail_rounds accumulate the same way"""

def probe_port(host, port, timeout=3):
    """Port probe for a service-type piece: HTTP GET http://host:port/health,
    connection refused/timeout -> False. vLLM's /health returns 200 (if this differs after
    checking in Task 15, change it here)."""

def build_row(job, idx, piece, ps, now_mono):
    """State -> exit row: call verdicts.stall_line_s (override = the piece's stall_line)
    / rates / judge, compute progress_pct and eta_s (falls back to the average rate when the
    recent rate has no value; None if neither has a value)."""

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
    extras = {h: sorted(s - registered) ...}     # follows gpu_jobs.collect's extras logic
    latest = {"sampled_at": now_wall, "rows": rows, "extras": extras,
              "incidents_tail": read_incidents_tail()}
    for jname, lines in per_job_lines.items():
        append_jsonl(MONITOR_DIR / "history" / f"{jname}.jsonl", lines)
    atomic_write(MONITOR_DIR / "state.json", st)
    atomic_write(MONITOR_DIR / "latest.json", latest)
    maybe_trigger_incidents(rows, st)            # leave as an empty pass function until Task 14
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
        except Exception as e:                   # a single failed round must not kill the resident process
            print(f"[sampler] round failed: {e}", file=sys.stderr, flush=True)
        if a.once:
            break
        time.sleep(max(1.0, a.interval - (time.monotonic() - t0)))
```

  Key implementation constraints (all from the design document, check off each one while writing the code):
  - **Clock**: `last_new_beat_mono` uses `time.monotonic()`; `beat_age_s = now_mono - last_new_beat_mono`; `since_launch_s = now_wall - piece["launched_at"]` (launched_at is the launch machine's wall clock; both the login machine and the launch machine are NTP machines, so minute-level error is acceptable -- if a piece has no launched_at field (an old format from manual register), parse job["started_at"] instead, and if that's missing too, just use now, i.e. handle it loosely).
  - **New-heartbeat test**: only `(b["ts"], b["done"]) > (last_ts, last_done)` counts as new.
  - **`stall_line_s`'s override** is taken from `piece.get("stall_line")`; `escalate_s` from `piece.get("escalate_line")`; `warmup_s` from `job.get("monitor", {}).get("warmup_s")`, defaulting to `verdicts.DEFAULTS["warmup_line_s"]`.
  - **10 consecutive rounds of probe failure**: add `"probe_failed": true` to the row plus put `probe_fail_rounds` into the row; the exit is responsible for lighting it up red -- the sampler does not trigger an incident because of this (fail-closed).

- [ ] **Step 4: Hook it into run.py's registry**. Add to the ops section of `TASKS`:

```python
    "sampler": dict(
        stage="ops", py="sys", script="ops/sampler.py",
        desc="Long-running task sampler (resident; one round every 60s: pick up heartbeats/probe liveness/compute verdicts, serves the web page)",
        notes=["Resident process, run in a tmux session on the login machine: tmux new-session -d -s new1_sampler "
               "'python3 run.py sampler'",
               "Lands on NFS monitor/ (latest.json/state.json/history/incidents), does not go into git",
               "Smoke test: python3 run.py sampler --once samples one round then exits"]),
```

- [ ] **Step 5: Run the tests + selfcheck, confirm they pass**

Run: `python3 -m unittest tests.test_sampler -v && python3 run.py selfcheck`
Expected: PASS; selfcheck all green

- [ ] **Step 6: Commit**

```bash
git add ops/sampler.py tests/test_sampler.py run.py
git commit -m "monitor: sampler core (pick up heartbeats/probe liveness/verdict/write latest+state+history) + register the sampler task"
```

---

### Task 7: Sampler web page (HTTP thread + /json)

**Files:**
- Modify: `ops/sampler.py` (add the HTTP thread and `--port`)
- Create: `tests/test_sampler_web.py`

**Interfaces:**
- Produces: `GET /` = the HTML task table; `GET /json` = the raw content of latest.json (Content-Type application/json). Port defaults to 8377, overridable with `--port`. The web thread only reads latest.json, it does not touch the sampling thread's memory -- the sampler hanging does not affect serving the page (design §3).

- [ ] **Step 1: Write the failing test**: the fixture writes a latest.json (with sampled_at and two rows), start `sampler.WebServer(port=0, monitor_dir=...)` (port=0 lets the OS assign one, the test gets the real port from `server.server_address[1]`), fetch `/json` with `urllib.request` and assert it matches the file, fetch `/` and assert 200 with a body containing the task name and the verdict string, plus the timestamp text containing `sampled_at`.

- [ ] **Step 2: Implement**: `http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler`; `do_GET` dispatches by path; the HTML is assembled by one pure function `render_html(latest)` (table columns: JOB/piece/HOST/GPU/verdict/progress/rate/token/ETA/SESSION; `<meta http-equiv="refresh" content="30">` for auto-refresh; the last-sample time at the top of the page, with an inline `<script>`: switch the banner's class name to red once `sampled_at` is more than 3x60s in the past -- the threshold is generated into the page from `verdicts.DEFAULTS["sample_interval_s"]` times 3, not copied as a separate number); the incident record block renders `incidents_tail`; sessions outside the ledger render `extras`. `main()` adds `--port`, and starts the web thread (daemon=True) before entering the sampling loop when not in `--once` mode.

- [ ] **Step 3: Run the test, confirm it passes**: `python3 -m unittest tests.test_sampler_web -v`

- [ ] **Step 4: Commit**

```bash
git add ops/sampler.py tests/test_sampler_web.py
git commit -m "monitor: sampler web exit (/ task table + /json, read-only against latest.json)"
```

---

### Task 8: Switch the terminal exits to reading the sampling history (`ops/gpu_jobs.py`)

**Files:**
- Modify: `ops/gpu_jobs.py` (the three exits `cmd_status`/`cmd_watch`/`json`; leave `free`/`register`/`finish` untouched)

**Interfaces:**
- Consumes: `latest.json` (Task 6's format).
- Produces: the read order for the three exits: if latest.json exists and `sampled_at` is <= 300 seconds ago -> render from it (table header's first line: `last sampled HH:MM:SS`); otherwise print a warning line `sampler is not running (last sampled <time|never>), probing live now` and fall back to the existing `collect()` path. The `json` exit works the same way: output latest.json's raw content when fresh, otherwise output the old `collect()` result plus a `"sampler_stale": true` field.

- [ ] **Step 1: Implement** `read_latest()` (returns `(latest_dict|None, age_s|None)`) and `fmt_table_v2(rows)` (columns: JOB/HOST/GPU/verdict/PROGRESS/RATE/TOK/ETA/SESSION; PROGRESS = `done/total (pct%) unit`; RATE = take `recent_rate` if it has a value, multiply by 3600 to show `/h` or keep `/s` depending on magnitude, `-` if no value; TOK = `tok_in/tok_out` abbreviated with thousands separators like `1.2M/340k`; ETA = `eta_s` converted to `HH:MM`). The two prompt behaviors `DONE, time to wrap up` and `EXIT, check the log` are kept (printed when the verdict is done/dead, wording follows the existing `fmt_table`).

- [ ] **Step 2: Verify manually** (on a machine with no sampler running):

Run: `python3 run.py gpu-jobs && python3 run.py gpu-jobs json | python3 -c "import json,sys; json.load(sys.stdin); print('json ok')"`
Expected: the warning line + the old table still prints; `json ok`. Then build a fake latest.json (`NEW1_MONITOR_DIR` pointed at a tmp dir) and confirm the new table renders and the header carries the last sample time.

- [ ] **Step 3: Commit**

```bash
git add ops/gpu_jobs.py
git commit -m "monitor: switch gpu-jobs' three exits to reading the sampling history (use it when fresh, warn and fall back to a live probe when stale)"
```

---

### Task 9: Bring the sampler online (tmux + a crontab watchdog)

**Files:**
- Modify: the login machine's crontab (system state, not a repo file)

- [ ] **Step 1: Start the resident process**

```bash
tmux new-session -d -s new1_sampler 'cd /home/y-guo/reproduce/new1 && python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'
```

- [ ] **Step 2: Install the watchdog** (back up `crontab -l` to `/tmp/crontab.bak` first, then append one line):

```
*/5 * * * * tmux has-session -t new1_sampler 2>/dev/null || tmux new-session -d -s new1_sampler 'cd /home/y-guo/reproduce/new1 && python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'
```

- [ ] **Step 3: Verify**: `curl -s localhost:8377/json | python3 -m json.tool | head` (produces valid JSON); open `localhost:8377` in a browser (via VS Code port forwarding) and see the task table; `tmux kill-session -t new1_sampler`, then wait 5 minutes and confirm the crontab brings it back (it shows up again in `tmux ls`).

---

### Task 10: Launch common module `ops/launch_common.py`

**Files:**
- Create: `ops/launch_common.py`
- Create: `tests/test_launch_common.py`

**Interfaces:**
- Produces (Tasks 11-13 depend entirely on these signatures):
  - `ALIAS = {"shiga": "tokyo105", "saitama": "tokyo108"}`; `local_host()`; `has_session(host, sess)`; `tmux_launch(host, sess, inner_cmd)` -- these three are moved verbatim from `ops/launch_probe.py:47-62` (once moved, Task 13 makes launch_probe import them back from here instead, and deletes its own copy).
  - `probe_free(host, gpus) -> (ok: bool, why: str)`: `ssh <host> nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader -i <gpus>`; non-empty stdout -> `(False, "occupied: <first line>")`; ssh failure/timeout -> `(False, "probe failed: ...")` (fail-closed); empty -> `(True, "")`.
  - `register_all(run_id, workdir, pieces, track, cmd_display, note=None, outdir=None, monitor=None) -> str`: register in three places in one go -- (1) the ledger: `gpu_jobs.mutate_reg` directly appends the job (a rich piece: host/gpus/session/log/cmd/launched_at/kind/stall_line/escalate_line; job-level `monitor={"warmup_s":...}`, `note`); (2) the experiment record: `subprocess.run([sys.executable, str(OPS/"record.py"), "start", "--run-id", run_id, "--track", track, "--cmd", cmd_display, "--host", ..., "--gpu", ..., "--log", ...])` (subprocess isolates record's sys.exit; rc != 0 is surfaced as-is and aborts -- record refusing a duplicate run_id is a guard rail, not an obstacle); (3) RUNMETA: `runmeta.append_runmeta(outdir, cmd_display, kind="launch")` only when `outdir` is given, otherwise print one line `WARN --outdir not given, RUNMETA not written`. Returns the registration receipt text.

- [ ] **Step 1: Write the failing test**: for `probe_free`, monkeypatch `subprocess.run` to feed it three kinds of results (empty stdout / a process line / raise TimeoutExpired) and assert the three return values; for `register_all`, use `NEW1_MONITOR_DIR` + a tmp jobs.json (monkeypatch `gpu_jobs.REG_PATH`) and assert the ledger gets a rich piece with all fields, and that calling it a second time with the same run_id raises SystemExit.

- [ ] **Step 2: Implement** (following the interface signatures above; `tmux_launch`'s inner template is exactly the same as launch_probe.py:57: `cd <wd> && CUDA_VISIBLE_DEVICES=<g> <cmd> 2>&1 | tee <log>`, prefixed with `K=V` pairs when there are env vars).

- [ ] **Step 3: Run the test, confirm it passes**, then Commit:

```bash
git add ops/launch_common.py tests/test_launch_common.py
git commit -m "launch: common module (fail-closed card probe/tmux template/three-way registration in one go)"
```

---

### Task 11: `run.py launch` subcommand (task mode + --cmd mode)

**Files:**
- Create: `ops/launch_cmd.py`
- Create: `tests/test_launch_cmd.py`
- Modify: `run.py` (add dispatch in main(); add `shardable=True` to the `collect-aw` entry; add one line for launch usage in the file-header usage doc)

**Interfaces:**
- Consumes: `run.TASKS/PY/build_cmd/gate_dirty/gate_of` (`from run import ...` after adding the repo root to `sys.path`, following launch_probe.py:41-42's existing pattern); all of Task 10.
- Produces: the command line (the signature finalized in design §6):

```
python3 run.py launch <task> [task args...] --run-id ID --piece host:gpus [--piece ...]
    --track track [--note ...] [--outdir DIR]
    [--stall-line seconds] [--escalate-line seconds] [--warmup-line seconds]
    [--service --port N] [--allow-dirty] [--dry-run]
python3 run.py launch --cmd '<full command>' --run-id ID --workdir DIR --piece ... (the rest as above)
```

- [ ] **Step 1: Write the failing test** (split the pure logic into testable functions): `build_pieces`(the argv parse result, task_entry)'s shard injection -- 2 pieces + `shardable=True` -> the two commands carry `--shard-id 0/1 --num-shards 2` respectively; not shardable + 2 pieces -> SystemExit; session name = `new1_<run_id>_t<host with tokyo stripped>g<gpus with commas turned into hyphens>`; two pieces with the same host and same gpus -> SystemExit. `--cmd` mode does not consult the registry, the command is passed through as-is. dry-run's output contains every inner command and touches no registration (monkeypatch register_all and assert it was not called).

- [ ] **Step 2: Implement `cmd_launch(argv)`**. The flow is pinned down as ten steps, in this exact order:
  1. Hand-written argument parsing (in gpu_jobs.py's iter style; unknown arguments are passed through to the task, everything after `--` is passed through as-is).
  2. Task mode: `t = TASKS[task]`; `--cmd` mode skips the registry.
  3. `gate_dirty(...)` (honor_dry=True: `--dry-run` is let through; reuses run.py:546's implementation via import, not duplicated).
  4. run_id is a required check; `--track` is required (a hard requirement of record start).
  5. Parse pieces + inject shard args + name the session/log (log = `<workdir>/logs/<sess>.log`, workdir defaults to ROOT, uses cwd when the task has one).
  6. `--dry-run` -> print each piece's host/gpu/session/inner command, return 0.
  7. Run `probe_free` on each piece; if any card is not FREE -> SystemExit listing the reasons (nothing gets launched at all).
  8. Run `tmux_launch` on each piece.
  9. **Verify liveness for 30 seconds**: one round every 5 seconds, checking each piece's `has_session` + growth in the log file's byte count + no `Traceback` in the last 4KB of the tail; passes early once every piece has shown output; if after 30 seconds a session is gone or the tail has a Traceback -> print the failed pieces and the last 40 lines of their logs, **launched pieces are not rolled back** (killing a process is a human decision), return 1 and register nothing -- a failed launch does not get booked.
  10. `register_all(...)` + print the monitoring entry points (`python3 run.py gpu-jobs` / `watch` / the web page at `localhost:8377`).
  Add, after `if cmd == "selfcheck"` in `run.py:main()`:

```python
    if cmd == "launch":
        sys.path.insert(0, str(ROOT / "ops"))
        from launch_cmd import cmd_launch
        return cmd_launch(rest)
```

- [ ] **Step 3: Run the tests + selfcheck**, fire one dry-run smoke test:

Run: `python3 -m unittest tests.test_launch_cmd -v && python3 run.py selfcheck && python3 run.py launch collect-aw --run-id smoke_x --track smoke --piece tokyo106:0 --piece tokyo106:1 --dry-run --allow-dirty -- --base-url http://x/v1 --model m --outdir /tmp/x`
Expected: tests pass; dry-run prints two inner commands carrying `--shard-id 0/1`

- [ ] **Step 4: Commit**

```bash
git add ops/launch_cmd.py tests/test_launch_cmd.py run.py
git commit -m "launch: run.py launch subcommand (probe cards -> tmux -> verify liveness -> three-way registration in one command; shardable injection)"
```

---

### Task 12: Refire mode `launch --refire`

**Files:**
- Modify: `ops/launch_cmd.py`, `tests/test_launch_cmd.py`

**Interfaces:**
- Produces: `python3 run.py launch --refire <run_id> --idx <piece number> [--piece host:gpus] [--allow-dirty]`. Behavior: find that job's idx-th piece in the ledger -> that session must already be dead (`has_session` true -> SystemExit "session is still alive, refire only applies to a dead piece") -> the target card = whatever `--piece` gives, or the original card, verified with `probe_free`, not FREE -> SystemExit (the incident agent takes this error back and retries on a different card) -> resend the `cmd` stored on the piece verbatim (the session name is unchanged, the log switches to a new file `<sess>.r<refires+1>.log`) -> `mutate_reg` updates that piece's host/gpus/log/`launched_at=now` -> does not open a new record, does not register again (a refire is not a new task). The sampler, seeing `launched_at` change, automatically reopens that piece's heartbeat timeline and does `refires+=1` (already implemented in Task 6).

- [ ] **Step 1: Write the failing test**: a tmp ledger + monkeypatch `has_session`/`probe_free`/`tmux_launch`, asserting: a live session is rejected; not-FREE is rejected; on the success path the ledger piece's log/launched_at are updated and cmd is unchanged, and no second job appears.

- [ ] **Step 2: Implement + run the test until it passes + Commit**

```bash
git add ops/launch_cmd.py tests/test_launch_cmd.py
git commit -m "launch: --refire re-launches a dead piece with its original ledger command (only dead pieces, fail-closed card probe)"
```

---

### Task 13: Wire the two queueing launchers into the same registration

**Files:**
- Modify: `ops/launch_probe.py` (replace `has_session/launch` with an import of `launch_common`; add the ledger + record write-through after RUNMETA in `main()`'s launch loop)
- Modify: `ops/launch_eval.py` (same)

**Interfaces:**
- Consumes: `launch_common.probe_free/register_all/has_session/tmux_launch`.

- [ ] **Step 1: launch_probe rework**:
  1. Delete the local `has_session`/`launch` (:47-62), replace with `from launch_common import has_session, tmux_launch, probe_free, register_all` (ops is already on sys.path). Change the original `launch()` call site to assemble the inner command and then call `tmux_launch` (same inner template, unchanged behavior).
  2. Before launching, run `probe_free(host, str(gpu))` per cell; a cell that is not FREE prints the reason and **skips that cell** (a half-empty queue table is common; rejecting the whole table would drag down the good cells too -- this differs from launch's single-task "reject the whole thing" policy, note the reason in a comment).
  3. After each cell is LAUNCHED: RUNMETA as before, then `register_all(run_id=rid, workdir=str(WD), pieces=[that cell's rich piece], track=f"probe_{args.batch}", cmd_display=cmd, outdir=None)` -- RUNMETA has already been written by itself, so register_all's own RUNMETA step is skipped by passing `outdir=None`, don't write it twice. If record start's rc != 0 because the run_id already exists (the normal path of resending full after smoke uses a different run_id, so it shouldn't collide; a collision means a duplicate launch) -> print a WARN and keep going, don't abort the launch loop.
- [ ] **Step 2: The same four spots for launch_eval** (track=f"eval_{args.batch}"; rid uses `{batch}_{model}_{cell}` from sess with the eval_ prefix stripped).
- [ ] **Step 3: Verify**: `python3 run.py launch-probe smoke --batch zz --data-root pipeline/data/<any existing one> --env appworld --model q35 --dry-run --allow-dirty` prints as usual; run the unit tests with `python3 -m unittest discover -s tests -v`, all green (launch_common's tests cover register_all).
- [ ] **Step 4: Commit**

```bash
git add ops/launch_probe.py ops/launch_eval.py
git commit -m "launch: wire the queueing launchers into launch_common (live FREE probe + automatic ledger/record, RUNMETA unchanged)"
```

---

### Task 14: Incident trigger (the sampler pulls up an incident agent)

**Files:**
- Modify: `ops/sampler.py` (implement `maybe_trigger_incidents`)
- Create: `tests/test_incidents.py`

**Interfaces:**
- Produces: `monitor/incidents.jsonl` (append): `{"id": "<job>#<idx>@<epoch>", "t", "job", "idx", "session", "verdict", "log", "allow_refire", "agent_pid"}`; `monitor/incidents/<id>.out` = the incident agent's stdout.
- Trigger rule (design §5, judged entirely inside the pure function `should_trigger(row, ps) -> (bool, allow_refire)`, unit tests carry the weight): `row["escalated"]` is true, and `ps["incident_open"]` is empty (the same incident only pulls up one agent; `incident_open` is cleared once the piece's verdict returns to healthy/warming up/done). `allow_refire` = (verdict==dead and `ps["refires"] == 0`).

- [ ] **Step 1: Write the failing test**: four cases for `should_trigger` (first time dead -> (True,True); dead but refires=1 -> (True,False); incident_open already set -> (False,_); stalled but not past the escalation line -> (False,_)); `build_incident_prompt(row, allow_refire)`'s output contains the log path, the `gpu-jobs json` command, and either a refire command or "refiring is not allowed."

- [ ] **Step 2: Implement**. Pulling up the agent:

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

  During implementation, first run `claude --help` to check the current spelling of headless mode and the no-confirmation flag (`-p/--print`, `--model`, `--dangerously-skip-permissions` or `--permission-mode bypassPermissions`), and change this spot to match the help output. Prompt template (write it as the module-level constant `INCIDENT_PROMPT`, with `{}` placeholders filled by format):

```
You are the incident agent for the new1 project. You do exactly one thing, "get the experiment
handled," and you do not write a report for a human to read.
Incident: task {job} piece {idx} (session {session}, host {host}, GPU {gpus}) verdict {verdict}.
Log: {log}
Look at the scene first: tail -c 8192 '{log}' | tr '\r' '\n' | tail -40
Ledger json: cd /home/y-guo/reproduce/new1 && python3 run.py gpu-jobs json
Rules (do not cross these lines):
- {refire_clause}
- If the verdict is suspected stall: only read the log to locate the cause, killing any session is
  forbidden, changing any file is forbidden.
- Only touch this one piece, do not touch any other task.
- When done, output one line: DONE <what you did, under 15 words>.
```

  The two values of `refire_clause`: allowed = "If the verdict is dead: read the log to locate the cause of death, then refire once: `python3 run.py launch --refire {job} --idx {idx}`; if the original card is occupied (the command will error), run `python3 run.py gpu-jobs free` to pick a free card and retry once with `--piece <host>:<gpus>` added"; not allowed = "This piece's refire quota is used up: autopsy only, launching anything again is forbidden."
  After triggering, `ps["incident_open"] = incident_id`; the sampler **does not wait** for the agent to finish (Popen returns immediately); `incident_open` is cleared once the next round's verdict returns to done/healthy/warming up.

- [ ] **Step 3: Run the tests until they pass + a manual dry run**: build a fake task (register a piece pointing at a nonexistent session + a log with heartbeats but not finished) -> `python3 run.py sampler --once` -> assert one line shows up in incidents.jsonl, and that `incidents/<id>.out` shows the incident agent really ran (a DONE line is read). After the dry run, clean up with `gpu-jobs finish <fake task> --force`.

- [ ] **Step 4: Commit**

```bash
git add ops/sampler.py tests/test_incidents.py
git commit -m "monitor: incident trigger (escalation line -> claude -p opus, debounce + refire quota, records incidents)"
```

---

### Task 15: The vLLM service track (port probe + throughput display)

**Files:**
- Modify: `ops/sampler.py` (`read_beats` switches to `read_vllm_stats` for `kind=="service"` pieces; check `probe_port`)
- Create: `tests/test_vllm_stats.py`

- [ ] **Step 1: the fixture uses an already-verified real sample** (original text taken on 2026-08-08 from
  `/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_diag_srv_a.log`,
  vllm 0.26.0, the format string is in
  `envs/vllm-env/lib/python3.12/site-packages/vllm/v1/metrics/loggers.py:263-313`):

```
(APIServer pid=263921) INFO 08-02 19:50:14 [loggers.py:310] Engine 000: Avg prompt throughput: 785.1 tokens/s, Avg generation throughput: 671.8 tokens/s, Running: 4 reqs, Waiting: 0 reqs, GPU KV cache usage: 11.2%, Prefix cache hit rate: 97.1%
```

  Known facts: one line every 10 seconds by default (`VLLM_LOG_STATS_INTERVAL`, `vllm/envs.py:47`);
  the line downgrades to debug and does not go to stdout when the engine is idle -- so the
  throughput line going quiet does not count as a stall, the verdict only looks at the port
  (already decided in design §4). Also note that the vLLM serve log is not under `<workdir>/logs/`,
  the launcher redirects it to `/net/.../vllm_cache/logs/` (hardcoded in
  `envs/serve_logs/launch_vllm_awdiag.py`) -- the log field must hold the real path when
  registering a service piece.
- [ ] **Step 2: Write the failing test**: `parse_vllm_stats(tail_text)` extracts `{"gen_tok_s": 671.8, "prompt_tok_s": 785.1, "running": 4}` from the fixture line above; no match -> None.
- [ ] **Step 3: Implement**: a service piece does not go through heartbeat.parse, `read_vllm_stats(log)` grabs the throughput line -> feeds the row's `tok_out` rate display field (display only, does not enter the verdict -- the verdict goes through `probe_port`; the `/health` path was verified in practice: on the machine running the service, `curl -s -o /dev/null -w '%{http_code}' localhost:<port>/health`, the vLLM OpenAI server returns 200 with no body; if it doesn't match, change `probe_port` to match what's actually observed).
- [ ] **Step 4: Run the test until it passes + Commit**

```bash
git add ops/sampler.py tests/test_vllm_stats.py
git commit -m "monitor: vLLM service track (port probe feeds the verdict, throughput line is display-only for rate)"
```

---

### Task 16: Documentation write-back — the gpu-run skill and two methodology references

**Files:**
- Modify: `.claude/skills/gpu-run/SKILL.md`, `references/launch-methodology.md`, `references/monitor-methodology.md`

- [ ] **Step 1: SKILL.md**. Rewrite the whole of Phase 4: launching becomes three steps (commit -> `python3 run.py launch <task> ... --run-id X --track Y --piece host:gpus` -> read the monitoring entry points it prints and hand them to the user); delete the whole double-registration/RUNMETA/record hand-typed command section (launch guarantees it now); Phase 4 step 6's commands handed to the user become `python3 run.py gpu-jobs`, `watch`, the browser at `localhost:8377`; rewrite Phase 5 as the sampler clause: the standing check-in regime is retired, the verdict/escalation/incident agent are the sampler's responsibility, Claude only dispatches job-monitor to read `gpu-jobs json` when the user asks or when the incident record has content; keep Phase 6a's five steps (done is just a verdict, deregistering is still fail-closed). Add one sentence to the Phase 3 smoke section: smoke can also use `launch --dry-run` to preview the command first.
- [ ] **Step 2: launch-methodology.md**: turn the tmux template section into "what launch does for you" (the template itself stays as a reference for the `--cmd` escape hatch); keep the card-picking-rules section (picking a card is still the agent's judgment call); turn the sharding section into shardable + multi-`--piece` usage.
- [ ] **Step 3: monitor-methodology.md**: rewrite the two-point speed measurement / ETA correction / tqdm parsing sections into "a description of the program's responsibility" (the exact meaning follows `ops/verdicts.py`'s DEFAULTS, with a table listing the six-cell verdict and the two-line formulas); keep the "decision tree" section but change the judgment input from raw logs to verdict values.
- [ ] **Step 4: Commit**

```bash
git add .claude/skills/gpu-run/
git commit -m "docs: rewrite the gpu-run skill (Phase 4 collapses into one launch command, Phase 5's check-in regime is replaced by the sampler)"
```

---

### Task 17: Documentation write-back — the two agent definitions

**Files:**
- Modify: `.claude/agents/job-monitor.md`, `.claude/agents/gpu-runner.md`

- [ ] **Step 1: slim down job-monitor.md**: delete all the operational detail about two-point speed measurement, hand-computing ETA, and tqdm parsing (replace with one sentence: "the verdict/rate/ETA are already computed by the sampler, you read the ready-made conclusion from `python3 run.py gpu-jobs json`"); keep the read-only iron rule, the autopsy procedure (read the log to locate the cause of death), the report format (the health table's "verdict" column is copied straight from the json's verdict); add a paragraph on the division of labor with the incident agent: you are the inspector a person dispatches, the one handling things automatically in the middle of the night is the incident agent the sampler pulls up, don't refire in its place.
- [ ] **Step 2: gpu-runner.md**: merge item 3 (get the launch command from run.py) and item 4 (double registration) and rewrite them as "launching is always `python3 run.py launch ...`, it covers the card probe/tmux/three-way registration; the two queueing launchers launch-probe/launch-eval still run directly as before (they also register automatically internally)"; change the report format's "registration receipt" section to paste launch's output instead.
- [ ] **Step 3: Commit**

```bash
git add .claude/agents/job-monitor.md .claude/agents/gpu-runner.md
git commit -m "docs: slim down job-monitor to read the ready-made verdict; change gpu-runner's launch section to launch"
```

---

### Task 18: Documentation write-back — probe-pipeline, handoff, root documents

**Files:**
- Modify: `.claude/skills/probe-pipeline/SKILL.md` (:74-75 the wrap-up chain, :134 G16, :172-173 releasing/deregistering, :221-222 the agent division-of-labor table), `references/gates.md` (G2/G16/G17), `references/stage-commands.md` (:19, :352), `references/invariants.md` (the double-write bookkeeping line), `references/extending.md` (:130 + add a "wire up heartbeats" item to the new-script checklist)
- Modify: `.claude/skills/handoff/SKILL.md:42` (the progress source points to `gpu-jobs json`/the sampling history)
- Modify: `CLAUDE.md` (add one sentence to the GPU section: launching and registration collapse into `run.py launch`, the user's self-service monitoring = `gpu-jobs watch` + the web page at 8377), `MAP.md` (update the three lines for gpu_jobs.py/launch_probe.py/launch_eval.py; add one line each for heartbeat.py/verdicts.py/sampler.py/launch_cmd.py/launch_common.py, following the existing table format), `ops/gpu_state.md` (add one line about the sampler to the page-top pointer)

- [ ] **Step 1: Change each file**. Unify G16's double-registration wording as: "launch writes all three places automatically; the manual/register fallback path still exists, and missing it still counts as a violation." Change invariants' double-write bookkeeping line to "the double write is guaranteed by launch; for a hand-typed launch that bypasses launch, the double-registration responsibility falls back to the person." Add one hard item to extending.md's new-script checklist: "a new collection/training/evaluation script must be wired up with `ops/heartbeat.py` (emit(0,...) entering the main loop, emit per unit, status=done at wrap-up); a script not wired up stays permanently in warming up in the window."
- [ ] **Step 2: Commit**

```bash
git add .claude/skills/probe-pipeline/ .claude/skills/handoff/SKILL.md CLAUDE.md MAP.md ops/gpu_state.md
git commit -m "docs: align probe-pipeline/handoff/CLAUDE/MAP/gpu_state with launch+the sampler"
```

---

### Task 19: Final self-check

- [ ] **Step 1: Full test run and health check**

Run: `python3 -m unittest discover -s tests -v && python3 run.py selfcheck`
Expected: all green; selfcheck all set

- [ ] **Step 2: Documentation-consistency sweep**: `grep -rn "double registration\|record start --run-id\|gpu-jobs register" .claude/ CLAUDE.md MAP.md` and confirm every remaining reference is in the context of "launch does it automatically / the fallback registration path," with no leftover narrative about the old "hand-type three commands" flow.
- [ ] **Step 3: CONTEXT.md review**: go over the glossary against the implementation (especially shardable and the monitoring-parameter field names); where they differ, change the glossary to match the implementation and note the date.
- [ ] **Step 4: Final Commit + report**: the changelog, a quick-reference for the new commands (launch/refire/sampler/watch/the web page), the watchdog crontab line, known limitations (the v1 not-doing list from design §9).
