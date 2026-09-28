# 03 the registry and the ledger

Status: resolved
Blocked by: (none)
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 7, 9)

## What to do

One Python file, two seed files, one permanent test, one `.gitignore` line.
Contracts Part 8 (8.0 through 8.6) is the specification, with 2.3, 2.5, 1.5 and
3.4 for the rules it serves; read Part 8 in full.

```
jobs/registry.py                          venv any   imports: none (repo); [PyYAML]   carries NO VERSION
jobs/runs.jsonl                           created empty (0 bytes), in git
jobs/RESULTS.md                           the output of registry.render() over the empty ledger, in git
tests/test_registry_concurrent_append.py  venv probe (header line names it)
.gitignore                                one line: jobs/runs.jsonl.lock
README.md                                 your own lines only
```

`jobs/registry.py` is `venv: any` and imports **nothing from this repo** and
nothing heavier than PyYAML. `constants/path_outputs.yaml` is read **lazily**,
inside the functions that need it, and cached in a module global, so
`import jobs.registry`, `lock()`, `append_*`, `write_*` and `beat()` all work
before `constants/` exists.

**File shape:** two marked halves of one file, writer first then reader (Part 8's
own mitigation for not splitting it).

### The names the file offers

Writer half (8.0):

```python
DEFAULTS: dict                                                   # 8.5
def lock() -> ContextManager[None]                               # 8.0
def append_start(row: dict) -> None                              # 8.0
def append_finish(run_id: str, row: dict) -> None                # 8.0
def write_meta(run_dir, **fields) -> None                        # 8.0
def write_done(run_dir, *, stage, key, commit, counts, versions,
               metrics, report, pairs=None, stage_extra=None) -> None   # 8.0
def beat(run_dir: Path, piece: int) -> Heartbeat                 # 8.0
class Heartbeat:
    def emit(self, done: int, total: int, unit: str, **extra) -> None   # 8.0
    def finish(self) -> None                                     # 8.0
```

Reader half (8.0, 8.5):

```python
def ls(workflow: str | None = None, *, debug: bool = False,
       edited: dict[str, bool] | None = None,
       progress: dict[str, tuple[int, int]] | None = None) -> list[dict]
def where(stage: str, key: str, *, debug: bool = False) -> Path
def find(fields: dict) -> list[dict]
def kill(run_id: str) -> list[str]
def free() -> dict[str, list[int]]
def sync() -> list[str]
def open_runs() -> list[dict]
def live_sessions() -> set[str]
def session_alive(host: str, session: str) -> bool
def typical_gap_s(beat_ts: list[float]) -> float | None          # 8.5
def stall_line_s(beat_ts: list[float]) -> float                  # 8.5
def rates(first_beat: dict, recent_beats: list[dict]) -> tuple[float | None, float | None]
def judge(piece: dict) -> tuple[str, bool]                       # 8.5
def judge_service(piece: dict) -> tuple[str, bool]               # 8.5
```

Three more names are internal to the file but are pinned here, because the
acceptance addresses them and `jobs/launch.py` (ticket 12) reuses one:

```python
def render() -> None                    # rewrites jobs/RESULTS.md from jobs/runs.jsonl
def cards_busy() -> dict[str, set[int]] # the 2.5 busy test per host; free() is its complement
def fold(rows: list[dict]) -> dict[str, dict]   # run_id -> newest start + newest finish (8.2)
```

### Behaviour, by contract section

- **`DEFAULTS` (8.5).** `stall_line` 180 s, `escalate_line` 3, `warmup_s` 1800 s,
  `launch_timeout_s` 1800 s, **plus the five shape constants the verdict rules
  name inline** (errata): `stall_mult` 5.0, `typical_beats` 20, `min_intervals`
  3, `recent_beats` 10, `slow_ratio` 0.5, under their legacy names
  (`legacy/ops/verdicts.py:16-27`). There is no per-piece override.
  `port_fail_rounds` and `sample_interval_s` go with the sampler and are dropped.
- **`lock()` (8.0, 8.6).** One module-level file descriptor on
  `jobs/runs.jsonl.lock` plus a depth counter; `fcntl.flock(LOCK_EX)` at depth 0
  only, released when the outermost context exits. `append_start`,
  `append_finish` and `write_meta` call it unconditionally, so a caller that
  already holds it nests safely.
- **`append_start` / `append_finish` (8.1, 8.2).** Append one JSON object per
  line to `jobs/runs.jsonl`, never rewrite, then `render()`. Start-row fields are
  8.1's table: `ev, t, run_id, stage, key, dir, workflow, setting, parent, swept,
  debug, upstream, versions, diff, commit, branch, dirty, dirty_count,
  dirty_files, host, pieces, status`, with `status` always `"launching"` and
  `workflow` the workflow **file's** name. A piece entry's keys are
  `{index, kind, host, gpus, session, pid, log, port, endpoint_file,
  agent_replica, venv, cmd}` and `kind` is one of `loop | train | cpu | service`.
  Finish-row fields are 8.2's: `ev, t, run_id, status, counts, metrics, report,
  elapsed_s`, with `status` one of `ok | failed | killed | launch_failed`.
- **`t`** is local time `"%Y-%m-%d %H:%M"` (8.1). It is the only launch-time
  source, so `elapsed_s` and `since_launch_s` are computed by parsing it back.
- **`fold` (8.2).** Per `run_id` take the **newest** start row and the **newest**
  finish row; `elapsed_s` is measured from the newest start row preceding that
  finish; `ls` folds the newest start row's `pieces` list.
- **`write_meta` (8.3).** Rewrite the whole `meta.json` through a temporary name
  in the same directory and `os.replace`, under `lock()`. Fields are 8.3's:
  `meta_version, stage, key, dir, versions, upstream, diff, debug, owners,
  launches, pieces, split_files, stage_extra`; `launches` is append-only,
  `pieces` is replaced entry by entry, and a field the caller does not pass keeps
  its stored value.
- **`write_done` (1.5, 8.0).** `{stage, key, commit, finished_at, counts,
  versions, metrics, report}` plus `pairs` and `stage_extra` when given, written
  through a temporary name and a rename.
- **`beat` / `Heartbeat` (8.4).** `<launch>` is `1 +` the largest `n` for which
  `heartbeat/<piece>-<n>.jsonl` exists in this run directory, `0` when none does.
  The **file** holds the bare JSON object per line (`done, total, unit, ts`
  required; `tok_in, tok_out, loss, status` optional) and **stdout** keeps
  legacy's `@hb ` prefix (errata; `legacy/ops/heartbeat.py:15,32`). `finish()`
  writes the final beat with `status: "done"`. `beat` opens no `meta.json`.
  **Every timestamp is `time.clock_gettime(time.CLOCK_REALTIME)`, never
  `time.time()`** — a loop piece writes beats with an AppWorld world open, which
  freezes the process clock (errata, measured 2026-09-17).
- **Verdicts (8.5).** Six values in priority order `done, dead, suspected stall,
  warming up, slowed, healthy`. `judge` and `judge_service` are **pure functions**
  over a piece dict whose keys are pinned here (errata):
  `{kind, alive, status, done, total, has_beat, beat_ts, beat_age_s,
  since_launch_s, port_ok, avg_rate, recent_rate}`, assembled by `ls`.
  **`avg_rate` and `recent_rate` are the round-1 addition** (errata): 8.5's
  `slowed` rule is "the recent rate is below half the average" and legacy's
  `judge` reads exactly those two keys (`legacy/ops/verdicts.py:110-113`), so
  without them `slowed` can never be returned and one of the six verdicts never
  prints. `ls` computes them with `rates(first_beat, recent_beats)` over the
  piece's beat file — `first_beat` the first `{ts, done}` object in it,
  `recent_beats` the last `DEFAULTS["typical_beats"]` — and passes `None` for
  both when there are too few beats. Liveness is per kind:
  `loop`/`train`/`service` are alive while their tmux session is in
  `live_sessions()`; a `cpu` piece is alive while `os.kill(pid, 0)` on the login
  machine succeeds.
- **`live_sessions` / `session_alive` (8.0, 3.4).** One
  `ssh -o BatchMode=yes <host> "tmux ls -F '#S' 2>/dev/null; true"` per host of
  `constants/path_outputs.yaml`'s `hosts:` list, **fail-closed**: a failed or
  timed-out probe reports the session **alive**. Returns bare session names.
  **The local host is probed without `ssh`** (errata): normalise both the host
  name and this machine's `hostname` through the `hosts:` entries' `alias`
  column, and when they are the same name run `tmux ls -F '#S' 2>/dev/null; true`
  through `bash -c` instead — `legacy/ops/launch_common.py:41-67` has exactly
  that short-circuit, for the session test and for the tmux launch alike. Without
  it every session probe on `login_host` — which is where `run.py`,
  `jobs/launch.py` and every loop piece live (3.4) — pays an `ssh` round trip to
  itself and reports **alive** fail-closed whenever `ssh` to self is not
  configured, which would make `jobs/launch.refire`'s liveness refusal
  unfalsifiable and ticket 12's `B7` pass for the wrong reason.
- **`free` / `cards_busy` (2.5, 8.6).** A card is busy when `nvidia-smi` shows a
  compute process on it, **or** when it appears in the `pieces` list of a
  `meta.json` whose run has a start row with no finish row **and** either a live
  session **or** a start row younger than `DEFAULTS["launch_timeout_s"]`. Probed
  now, never cached; fail-closed, so an unclear probe counts the card busy.
  **Decision already made (errata):** this test lives here, not in
  `jobs/launch.py`, which calls `registry.free()` inside its lock hold.
- **`kill` (8.6).** End each piece of the run — a tmux piece by its session, a
  `cpu` piece by its `pid` — reading `host`/`session`/`pid` from `meta.json`'s
  `pieces` list, not from the start row; refuse while any live run's
  `service_<kind>_<replica>.json` names this `run_id` in `attached_to`. Return
  the sessions it ended; `run.py` writes the `killed` finish row.
- **`sync` (8.6, 8.2).** Fold every run directory's `done.json` and heartbeat
  files into the missing finish rows, write the `failed` row for a run with no
  `done.json` whose pieces `judge` calls `dead`, re-render `RESULTS.md`. It
  appends those rows **itself** through `append_finish` (errata) and returns the
  `run_id`s.
- **`ls` (8.6).** One folded dict per run with the piece verdicts, the heartbeat
  age, the progress (the `progress` pair when given, else the sum of beats) and
  the flag set `edited, behind, consumed, split, pinned, dirty, debug, orphan`.
  `edited` and `progress` are passed in by `run.py`, because this file imports
  nothing from the repo. A `launching` row older than
  `DEFAULTS["launch_timeout_s"]` with no sessions is **reported**
  `launch_failed`; `run.py` writes the row. Each folded row carries the start
  row's `stage`, `key`, `dir`, `diff`, `parent` and `swept`, which
  `eval/method_table.py` reads (errata).
  **`ls` calls `live_sessions()` only when the folded row set is non-empty**
  (errata): a verdict needs liveness and there is no verdict to compute over zero
  rows, so `run.py ls` and `eval/method_table.table()` against an empty ledger
  issue **no `ssh` at all**. `cards_busy` / `free` stay the only other host
  probers. This is what lets tickets 10 and 14 run `table` and `ls` in an
  implementer's worktree, where `ssh` is forbidden (spec section 7).
- **`render` (8.2, errata).** One markdown table, newest run first, one row per
  `run_id` folded from its newest start and newest finish row, columns
  `run_id | started | stage | workflow/setting | commit | status | numbers |
  report`, with a header line saying the file is generated and must not be edited
  by hand. No per-run detail blocks.

### Legacy sources

| what | where |
|---|---|
| append-only event stream, fold, `now()` | `legacy/ops/record.py:47-48, 84-120` |
| the rendered markdown table | `legacy/ops/record.py:137-215` (keep 143-172, drop the detail blocks 173-212) |
| `flock` read-modify-write under one lock | `legacy/ops/gpu_jobs.py:64-73` |
| per-host `tmux ls` over ssh, fail-closed | `legacy/ops/gpu_jobs.py:76-94` |
| the fail-closed `nvidia-smi` card probe | `legacy/ops/launch_common.py:70-88` |
| liveness-gated deregistration (the shape `kill` follows) | `legacy/ops/gpu_jobs.py:439-472` |
| the six verdicts, `typical_gap_s`, `stall_line_s`, `rates`, `judge`, `_judge_service` | `legacy/ops/verdicts.py:16-116` |
| the heartbeat line and `emit` | `legacy/ops/heartbeat.py:15-33` |
| temp-name + rename, and the corrupt-file rename | `legacy/ops/runmeta.py:55-84` |

**Not ported, and none of it comes across:** the resident sampler
(`legacy/ops/sampler.py`, whole file); `latest.json` / `MONITOR_DIR` and the
freshness fallback (`gpu_jobs.py:34-42, 213-249, 301-363, 489-500`); the web page
and the watch loop (`gpu_jobs.py:374-384`); tqdm log-tail parsing
(`gpu_jobs.py:44-47, 97-118`); the `{"active", "history"}` ledger shape and the
`register`/`finish`/`json` CLI (`gpu_jobs.py:50-73, 390-501`); `record.py`'s CLI
and its `track`/`note`/`conclusion` fields (`record.py:218-335`); the per-run
detail blocks of `RESULTS.md`; `verdicts.DEFAULTS["port_fail_rounds"]` and
`["sample_interval_s"]` and the round-counting service rule
(`verdicts.py:17,26,74-88`), replaced by 8.5's one-port-probe rule;
`heartbeat.parse` (`heartbeat.py:36-47`).

### The two seed files and the ignore line

- `jobs/runs.jsonl`: created **empty** (0 bytes) so the first append has a file to
  append to and git tracks it.
- `jobs/RESULTS.md`: the output of `registry.render()` over the empty ledger —
  the title, the generated-file warning, and a "no runs yet" line.
- `.gitignore`: add the single line `jobs/runs.jsonl.lock` (the tree's own line
  for that file). Change nothing else in `.gitignore`.

### `tests/test_registry_concurrent_append.py`

The fourth of the four checks the tree's `tests/` line names: "two pieces
appending to `runs.jsonl` at once both land". A `unittest.TestCase` (pytest is
not installed on this machine) whose header line names its venv (`probe`). It
forks 8 processes that each append 20 start rows into a **temp copy** of the
tree and asserts that 160 lines land and that every line parses as JSON.

## Acceptance

Run from the repo root and paste the real output. **No command here may write
into the real `jobs/runs.jsonl`**: the registry resolves its paths from
`__file__`, so every functional check runs against a throw-away copy in a temp
tree. Confirm with `git status --porcelain jobs/` at the end.

```bash
PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python
AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
VL=/home/y-guo/reproduce/new1/external/vllm-env/bin/python
```

**A1 — imports as `any` under every interpreter of the `venvs:` map, and under system python3.**
```bash
for P in "$PR" "$AW" "$VL"; do
  $P -c "import sys; sys.path.insert(0,'.'); from jobs import registry as r; print(r.DEFAULTS['launch_timeout_s'], r.DEFAULTS['stall_line'])"
done
python3 -c "import sys; sys.path.insert(0,'.'); from jobs import registry; print('sys ok')"
```
Expected: `1800 180` three times, then `sys ok`; exit 0 each.

**A2 — the re-entrant lock, and that a second process really blocks.**
```bash
"$PR" - <<'PY'
import sys, time, subprocess; sys.path.insert(0,'.')
from jobs import registry as r
with r.lock():
    with r.lock():
        p = subprocess.Popen([sys.executable, "-c",
            "import sys,time; sys.path.insert(0,'.');\n"
            "from jobs import registry as r\n"
            "t=time.time()\n"
            "with r.lock(): print('waited %.1f' % (time.time()-t))"])
        time.sleep(2)
print("outer released")
p.wait()
PY
```
Expected: `outer released` first, then `waited 2.0` (any value >= 1.5); exit 0.

**A3 — start row, finish row, fold, `RESULTS.md`, `open_runs`, `find`.**
```bash
T=$(mktemp -d); mkdir -p $T/jobs $T/constants; cp jobs/registry.py $T/jobs/
cat > $T/constants/path_outputs.yaml <<'Y'
root: TMPROOT/out
debug_subdir: debug
login_host: shiga
hosts:
  - {name: tokyo105, alias: shiga, cards: 8}
Y
sed -i "s|TMPROOT|$T|" $T/constants/path_outputs.yaml
"$PR" - "$T" <<'PY'
import sys, json, pathlib; T = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(T))
from jobs import registry as r
rd = T/"out/sample/abc123abc123"; rd.mkdir(parents=True)
row = dict(ev="start", t="2026-09-17 10:00", run_id="sample-abc123abc123",
           stage="sample", key="abc123abc123", dir=str(rd),
           workflow="baseline", setting="gpt_oss_120b_appworld", parent=None, swept=None,
           debug=False, upstream={}, versions={"agent/loop.py": 1}, diff={"sample.max_steps": 40},
           commit="deadbee", branch="from-zero", dirty=False, dirty_count=0, dirty_files=[],
           host="shiga", status="launching",
           pieces=[dict(index=0, kind="loop", host="shiga", gpus="", session="sample-abc123abc123-0",
                        pid=None, log=str(rd/"log/0.txt"), port=None, endpoint_file=None,
                        agent_replica=0, venv="appworld", cmd="...")])
r.append_start(row)
print("open:", [x["run_id"] for x in r.open_runs()])
r.append_finish("sample-abc123abc123", dict(ev="finish", t="2026-09-17 10:40",
    run_id="sample-abc123abc123", status="ok", counts={"records": 12}, metrics={},
    report=None, elapsed_s=2400.0))
print("open after finish:", r.open_runs())
print("lines:", len((T/"jobs/runs.jsonl").read_text().strip().splitlines()))
print("results has run:", "sample-abc123abc123" in (T/"jobs/RESULTS.md").read_text())
print("find:", [x["run_id"] for x in r.find({"sample.max_steps": 40})])
PY
```
Expected, in order: `open: ['sample-abc123abc123']`, `open after finish: []`,
`lines: 2`, `results has run: True`, `find: ['sample-abc123abc123']`; exit 0.

**A4 — `write_meta`, `write_done`: fields and atomicity.**
```bash
"$PR" - "$T" <<'PY'
import sys, json, pathlib; T = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(T))
from jobs import registry as r
rd = T/"out/sample/abc123abc123"
r.write_meta(rd, stage="sample", key="abc123abc123", dir=str(rd), owners=[{"workflow":"baseline","setting":"a"}])
r.write_meta(rd, owners=[{"workflow":"baseline","setting":"a"},{"workflow":"baseline","setting":"b"}])
m = json.loads((rd/"meta.json").read_text())
print("owners:", len(m["owners"]), "stage kept:", m["stage"])
r.write_done(rd, stage="sample", key="abc123abc123", commit="deadbee",
             counts={"records": 12}, versions={"agent/loop.py": 1}, metrics={},
             report=None, pairs=[["t1", 42]])
d = json.loads((rd/"done.json").read_text())
print("done keys:", sorted(d))
print("no temp left:", sorted(p.name for p in rd.iterdir()))
PY
```
Expected: `owners: 2 stage kept: sample`; then
`done keys: ['commit', 'counts', 'finished_at', 'key', 'metrics', 'pairs', 'report', 'stage', 'versions']`;
then a directory listing holding no `*.tmp*`; exit 0.

**A5 — the heartbeat file, its name and its `<launch>` index.**
```bash
"$PR" - "$T" <<'PY'
import sys, json, pathlib; T = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(T))
from jobs import registry as r
rd = T/"out/sample/abc123abc123"
h = r.beat(rd, 3); h.emit(0, 10, "task"); h.emit(5, 10, "task", tok_in=100, tok_out=7); h.finish()
h2 = r.beat(rd, 3); h2.emit(0, 10, "task"); h2.finish()
print(sorted(p.name for p in (rd/"heartbeat").iterdir()))
lines = [json.loads(l) for l in (rd/"heartbeat/3-0.jsonl").read_text().splitlines()]
print(len(lines), sorted(lines[0]), lines[-1]["status"])
PY
```
Expected: `['3-0.jsonl', '3-1.jsonl']`, then
`3 ['done', 'total', 'ts', 'unit'] done`; exit 0.

**A6 — the verdicts, as pure functions.**
```bash
"$PR" -c "
import sys; sys.path.insert(0,'.')
from jobs import registry as r
print(r.typical_gap_s([0.0,60.0,120.0,180.0]))
print(r.typical_gap_s([0.0,60.0]))
print(r.stall_line_s([0.0,60.0]), r.stall_line_s([0.0,60.0,120.0,180.0]))
print(r.rates({'ts': 0.0, 'done': 0}, [{'ts': 0.0, 'done': 0}, {'ts': 100.0, 'done': 10}]))
base = dict(kind='loop', alive=True, status=None, done=1, total=10, has_beat=True,
            beat_ts=[0.0,60.0,120.0,180.0], beat_age_s=10.0, since_launch_s=300.0, port_ok=None,
            avg_rate=0.1, recent_rate=0.1)
print(r.judge(dict(base, status='done')))
print(r.judge(dict(base, alive=False)))
print(r.judge(dict(base, beat_age_s=100000.0)))
print(r.judge(dict(base, has_beat=False, since_launch_s=10.0)))
print(r.judge(dict(base, recent_rate=0.02)))
print(r.judge(base))
print(r.judge_service(dict(kind='service', alive=True, port_ok=True, since_launch_s=10.0)))
print(r.judge_service(dict(kind='service', alive=True, port_ok=False, since_launch_s=10.0)))
print(r.judge_service(dict(kind='service', alive=True, port_ok=False, since_launch_s=99999.0)))
print(r.judge_service(dict(kind='service', alive=False, port_ok=False, since_launch_s=10.0)))
"
```
Expected, line by line: `60.0`; `None`; `1800.0 300.0`; `(0.1, 0.1)`;
`('done', False)`; `('dead', True)`; `('suspected stall', True)`;
`('warming up', False)`; `('slowed', False)`; `('healthy', False)`; then the four
`judge_service` lines `('healthy', False)`; `('warming up', False)`;
`('suspected stall', True)`; `('dead', True)`; exit 0. **All six verdicts of 8.5
appear**, which is what the `avg_rate` / `recent_rate` keys are for.

**A7 — the concurrent-append check.**
```bash
"$PR" tests/test_registry_concurrent_append.py
```
Expected: `OK` from unittest, exit 0.

**A8 — the ledger seed files, and the ignore line.**
```bash
test ! -s jobs/runs.jsonl && echo "ledger empty"
head -3 jobs/RESULTS.md
git check-ignore jobs/runs.jsonl.lock
git status --porcelain jobs/
```
Expected: `ledger empty`; then the title line, the generated-file warning and the
"no runs yet" line; then `jobs/runs.jsonl.lock`; then, from `git status`, only
the two new tracked files (and nothing modified).

**A9 — no absolute cluster path in the code.**
```bash
grep -n "/home/\|/net/" jobs/registry.py || echo NO_ABS_PATH
```
Expected: `NO_ABS_PATH`.

**A10 — `ls` over an empty ledger probes no host.** Tickets 10 and 14 run
`table` and `ls` in a worktree where `ssh` is forbidden, so the short-circuit is
load-bearing. `ls` must reach `live_sessions` through the **module global**, which
is what makes this check possible.
```bash
T4=$(mktemp -d); mkdir -p $T4/jobs $T4/constants; cp jobs/registry.py $T4/jobs/
: > $T4/jobs/runs.jsonl
cat > $T4/constants/path_outputs.yaml <<'Y'
root: TMPROOT/out
debug_subdir: debug
login_host: tokyo105
hosts:
  - {name: tokyo105, alias: shiga, cards: 8}
Y
sed -i "s|TMPROOT|$T4|" $T4/constants/path_outputs.yaml
"$PR" - "$T4" <<'PY'
import sys, pathlib; T = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(T))
from jobs import registry as r
def boom(*a, **k): raise AssertionError("ls probed a host over an empty ledger")
r.live_sessions = boom
print("empty ls:", r.ls())
print("empty ls --debug:", r.ls(debug=True))
PY
```
Expected: `empty ls: []` and `empty ls --debug: []`, exit 0, no `AssertionError`.

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: `jobs/registry.py` imports under every
interpreter of the `venvs:` map (A1); its `README.md` annotation line equals the
`ast`-parsed import graph; it carries **no** `VERSION` line, because no stage's
version list names it (2.2); and no `/home/` or `/net/` literal (A9).

### GPU / main session — not yours

`M-J1` `run.py free` per host, cross-checked by hand with
`ssh <host> nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`,
and fail-closed on a broken ssh (an unreachable host prints an **empty** free
list, never a full one). `M-J2` `live_sessions()` lists every host's tmux
sessions and reports a session **alive** when the ssh to its host is broken.

## Comments

- 2026-09-17 wave 1 closeout: implementation passed review after 2 fix rounds, branch `ticket/2026-09-17-wave1/T03` (base `cca3ca3`, head `ecfd925`), merged as `361dabd`. Main-session checks after the merge: `jobs.registry` imports under the three interpreters; `tests/test_registry_concurrent_append.py` passes (1 test, OK); `M-J1` `free()` and `cards_busy()` against the real cluster agree with a by-hand `nvidia-smi --query-compute-apps` per host (busy: tokyo105 card 0, tokyo106 cards 0 and 1, tokyo108 cards 0 and 1, tokyo107 none), and an unreachable host yields an empty free list and an all-busy card set; `M-J2` `live_sessions()` lists the 12 tmux sessions a by-hand `tmux ls` shows on the four hosts, `session_alive` answers True for an unreachable host and False for a missing session on a reachable one. Remaining minors (not blocking, for the final review): F5 `ConnectTimeout=5` added to the pinned ssh command; NF2 `_known_sessions()` reads every historical run's `meta.json` on every `ls()`; NF3 the synthetic orphan row uses the verdict string `orphan`, outside the six pinned verdicts. Deferred by design to tickets 12, 14, 15: the `behind/consumed/split/pinned` flags of `ls()`, selfcheck, the `/health` protocol behind `_probe_port`. Report `sdd/2026-09-17-wave1/T03-report.md`.
- 2026-09-17 wave 1 closeout, third fix round: a re-review of the merged code found N1 (important): `ls()` reported every live tmux session on the shared hosts that matched no registry row as this repo's orphan, including sessions of unrelated work. Fixed on the recreated branch `ticket/2026-09-17-wave1/T03` (base `6cb1171`, head `ec1c026`, `jobs/registry.py` only): `_is_repo_session_name` keeps only names shaped `<stage>-<12 hex key>-<piece index>` (contracts 3.1 and 3.4) as orphan candidates. Re-review: N1 addressed. Merged as `d8fffbb`. Main-session checks after the merge: `jobs.registry` imports under the probe, appworld and vllm interpreters and system `python3`; `tests/test_registry_concurrent_append.py` passes (1 test, OK); against the real cluster with a throw-away ledger holding one fake run, `live_sessions()` returned 12 sessions on tokyo105 to tokyo108, none has this repo's name shape, and `ls()` returned the fake run's row and zero `orphan_session` rows. New minor for the final review: N2, the name shape carries no repo-specific prefix, so a foreign session that happens to be named `<word>-<12 hex>-<digits>` would still be reported; closing it needs a prefix in the session-naming rule (contracts 3.4, `jobs/launch.py`, ticket 12).
- 2026-09-18, owner ruling applied at the wave-4 closeout (main session of
  wave 4; record `.scratch/from-zero/sdd/2026-09-18-wave4/owner-rulings.json`,
  report `T03-registry-ruling-report.md`). `_alive_on` tested the piece's raw
  host string against `failed_hosts`, which holds canonical names, so a piece
  recorded under an alias (`shiga`, `saitama`) on a host whose probe failed was
  reported **dead**, against 3.4's fail-closed rule; it now canonicalises the
  host first (branch `ticket/2026-09-18-wave4/T03-alias-ruling`, `08d31a8`,
  merged as `772ecb6`). The fix report and the commit message state the
  direction backwards ("reported alive instead of dead"); this entry is the
  correct one. Minor left open: `cards_busy` keys busy cards by the raw host
  string while `free()` reads the canonical name, latent while no GPU piece is
  recorded under an alias.
