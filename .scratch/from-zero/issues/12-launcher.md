# 12 the launcher

Status: ready-for-agent
Blocked by: 01, 02, 03, 04, 05, 06
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 6, 7, 9)

## What to do

One file: `jobs/launch.py`, plus its `README.md` entry. Contracts 8.1 (the start
row and the launch order), 2.5 (the git gate, the launch gate, the card
reservation), 3.4 (placement, the session name, the piece command), 7.4 (ports,
endpoint files, the attach test), 2.3 (refire and the teardown) and 8.3
(`meta.json`) are the specification; read 8.1, 2.5 and 3.4 in full.

```
jobs/launch.py   venv: probe (it runs on the login machine)
  imports: experimental_settings/schema.py, jobs/registry.py,
           data/trajectory_record.py (done_pairs, is_done, owner, release),
           data/environments/__init__.py (tasks and requested_pairs)
  used by: run.py
  reads:   constants/path_datasets.yaml (the venv per environment and the venvs map),
           constants/path_outputs.yaml (the login_host and the hosts list),
           models/table.yaml (the serving block), the run directory's settings.yaml
           and meta.json, service_<kind>_<replica>.json (its own run's and other live
           runs'), nvidia-smi, tmux, git
  writes:  the start row in jobs/runs.jsonl, meta.json launch entries,
           meta.json's split_files, dirty.patch, the piece commands
  venv:    probe
  carries NO VERSION (no stage's version list names it)
README.md        your one line only
```

**It is a library with no `__main__`:** `run.py` is the one command (0.2, 8.6).

### The names it offers

```python
PROBE_PORT_BASE = 8500                                                    # 7.4
def launch(stage, setting, run_dir, resolved, git) -> tuple[str, list[dict]]   # 0.2, 8.1
def refire(run_dir, git, piece=None) -> list[dict]                        # 0.2, 2.3
def teardown_services(run_dir) -> list[str]                               # 0.2, 2.3
def git_state(run_dir, allow_dirty) -> dict                               # 0.2, 2.5
```

Five more are module-internal but are pinned here, because the acceptance
exercises the decision rules without a card:

```python
def gate_open_row(open_rows, meta_by_run, live_sessions, now_ts, beats=None) -> str | None  # 2.5
def place(kind, cards_needed, free_by_host, *, serving_host, prefer_host,
          attached) -> str | None                                              # 3.4
def assign_ports(kind, replica, serving_port, taken) -> int                    # 7.4
def piece_command(python, module, run_dir, piece, n, gpus, log) -> str         # 3.4
def alive_check(pieces, window_s=30, poll_s=5) -> tuple[bool, list]            # 8.1
def is_ledger_path(path) -> bool                                               # 2.5
```

`is_ledger_path` is the ledger exemption of 2.5 as a pure test over one path
string — true for `jobs/runs.jsonl`, `jobs/RESULTS.md` and anything ending
`.lock`, false for everything else. It is pinned here because `B3` exercises the
exemption over a fabricated path list instead of dirtying the real ledger, which
spec section 9 forbids.

### Behaviour, by contract section

- **`git_state(run_dir, allow_dirty)` (2.5).** Refuses a dirty tree without
  `--allow-dirty`, naming the files; writes `<run_dir>/dirty.patch`
  (`git diff HEAD`) when the flag is given — which is why it takes the run
  directory; returns `{commit, branch, dirty, dirty_count, dirty_files}`;
  **fail-closed**, a failed git probe counts as dirty. `jobs/runs.jsonl`,
  `jobs/RESULTS.md` and `*.lock` **never** count as dirty (today's
  `LEDGER_PATHS` exemption, `legacy/ops/record.py:52-55`, which existed in three
  copies and now exists in one). **`commit` is the short sha**
  (`git rev-parse --short HEAD`, `record.py:75`) — errata, because
  `legacy/ops/runmeta.py:46` wrote the full one. `run.py` is its **one caller**,
  for all six stages.
- **`launch(...)` order (8.1, 8.6)**, inside one `registry.lock()` hold: read the
  registry (`registry.open_runs()`), run the launch gate, run 7.4's attach test,
  read the card reservation (`registry.free()`), assign the ports, append the
  start row with `status: "launching"`. **Then release the lock**; start the
  **service** pieces and run the alive check on them; for an `inject` run run the
  `check` client against the probe service once its port answers; only then start
  the **loop** pieces.
- **The launch gate (2.5).** Refuse a key whose newest start row has no finish row
  and any one of three things holds: a live session on its host in `meta.json`'s
  `pieces` entry, **counting only pieces whose `kind` is not `service`**; a
  heartbeat younger than the stall line; or a start row younger than
  `registry.DEFAULTS["launch_timeout_s"]`, that third clause holding **only while
  no piece of that row has been observed `dead`**. Print the session name when
  there is one, else the `run_id` and the row's age.
- **`beats`, and what "observed dead" means** (errata). The second and third
  clauses both need the pieces' heartbeat history, which the row does not carry,
  so `gate_open_row` takes a fifth argument: `beats`, a
  `{run_id: {piece index: [beat ts, ...]}}` map; a run or a piece missing from it
  has emitted nothing, and `None` means no piece of any row has. `launch` builds
  it by reading `<row["dir"]>/heartbeat/<piece>-*.jsonl` for each open row, inside
  the same lock hold. The second clause is then
  `now_ts - max(beat ts) < registry.stall_line_s(beat_ts)` for any non-service
  piece. **A piece counts as observed `dead` only when it is not alive *and* has
  at least one beat** (a `cpu` piece: has a recorded pid) — 8.5 makes a piece
  `dead` on `alive is False` alone, which would drop the third clause for every
  run whose tmux sessions have not started yet and let two `run.py` calls a second
  apart both pass, the exact race 2.5's disjunction and `M-J8` exist to prevent.
  2.5's own words are the rule: the timeout "covers a piece that has not appeared
  yet and not one that has already gone", and a first beat is what tells the two
  apart.
- **Piece rule and venv come from `schema.STAGES`** (2.1): `venv` is a string or a
  `{piece kind: venv name}` mapping with `"env"` meaning this setting's
  `data.env` row's `venv:` column in `constants/path_datasets.yaml` and `"any"`
  resolving to `venvs.probe` (6.3); the piece rule is
  `(kind, count_field_or_int, mode)` tuples.
- **Placement (3.4).** The agent service goes on its table row's `serving.host`;
  **an agent service the attach test matched takes no card, enters no card search
  and lands on that server's host**; a checkpoint-loading probe service (1 card)
  and a `train` piece (1 card) take the first host in
  `constants/path_outputs.yaml`'s `hosts:` list with enough free cards,
  preferring the host this run's agent service is on; a `--render-only` probe
  piece takes no card and lands on `login_host`; loop pieces take no card and run
  on `login_host`. A run whose required cards are free on no host is refused,
  naming every host probed and its free count.
- **The piece command (3.4, errata):**
  `tmux new-session -d -s <stage>-<key>-<piece> "cd <repo root> &&
  CUDA_VISIBLE_DEVICES=<ids> <venv python> -m <module> --run-dir <dir>
  [--piece <i>/<n>] 2>&1 | tee -a <run_dir>/log/<piece>.txt"`, with
  `--piece <i>/<n>` present **only** on a `sample` or `inject` loop piece. The
  redirection is errata: 3.4's piece command carries none while 1.5 requires
  `log/<piece>.txt`; it appends (`tee -a`) because the file name carries no
  launch index (`legacy/ops/launch_cmd.py:196-202`). A piece on another host is
  started as `ssh -o BatchMode=yes <host> tmux new-session -d …`.
  **The session name must be spelled exactly as `agent/loop.py` spells
  `meta.owner_session`: `f"{stage}-{key}-{piece}"`.**
- **Ports (7.4).** The agent service first looks for an attachable live server
  (same `serving.host`, whose `service_agent_<replica>.json` claims the same
  `result:` block) and, finding one, takes that host and port and passes
  `--attach-only`; only when none is found does it start a server at
  `serving.port + replica`, moving to the next free port when one is taken. A
  probe service takes the first free port at or above `PROBE_PORT_BASE`.
- **The two service command lines are 7.1's and 7.2's, verbatim.**
  `--score-ckpt` and `--gen-ckpt` are the **train run directories** resolved from
  `_upstream["probe_score.train"]` and `_upstream["probe_gen.train"]` through
  `schema.run_dir_of`; `--temperature` is `resolved["probe_temperature"]`; the
  agent service gets `--replica <i>`; all four bracketed probe flags are
  **absent** under `--render-only`.
- **`service_check` (7.2, 8.1).** For an inject run, run
  `<probe python> -m models.probe_models.service check --base-url <url> --run-dir <dir>`
  after the probe piece's port answers and **before the first loop piece**; a
  non-zero exit is the `service_check` outcome.
- **The return value (8.1)** is `(outcome, pieces)` with outcome `up`,
  `alive_check` or `service_check`; the piece entries come back either way.
  **Before returning any outcome but `up`**, call `teardown_services(run_dir)` and
  record in the returned list which sessions it ended (2.3: a `service_check`
  failure is the ordinary failure path, and without this the vLLM server holds
  its cards for good).
- **`teardown_services(run_dir)` (2.3).** For each `meta.json` piece entry with
  `kind: service`, `ssh <host> tmux kill-session -t <session>`, **skipped for a
  piece whose owning `run_id` appears in the `attached_to` field of another live
  run's `service_<kind>_<replica>.json`**. Returns the sessions it ended.
- **`refire(run_dir, git, piece=None)` (2.3).** Probe that piece's tmux session on
  the host in its `meta.json` entry, through `registry.session_alive(host,
  session)`, and **refuse while it is alive**, naming the session and the host
  (fail-closed, so a failed or timed-out ssh counts as alive). **A host that
  normalises to `login_host` is probed locally, with no `ssh`** (errata against
  8.0/3.4; `legacy/ops/launch_common.py:41-67` has the same short-circuit for
  both the session test and the tmux launch), which is what lets `B7` run in an
  implementer's worktree; **warn** when this piece already has more than one entry in
  `meta.json.launches`, name those entries, and proceed — **there is no refire
  quota**; release that piece's claims through
  `data/trajectory_record.release(run_dir, registry.live_sessions(), registry.DEFAULTS["launch_timeout_s"])`
  — **the run directory**, not `<run_dir>/records`, because
  `data/trajectory_record.py` appends `records/` itself (errata); probe the cards
  again; restart the piece in a new tmux session; rewrite that piece's
  `meta.json` entry (`host`, `gpus`, `session`, `pid`, `cmd`) and append a
  `launches` entry carrying the `git` dict it was handed — both through
  `registry.write_meta` inside one lock hold.
- **`meta.json.split_files` (8.3).** Resolved and written **before the pieces
  start**, one entry per split file with its path, sha1 and resolved task-id list,
  through `env.tasks(split)`; a `tasks` id that is in none of the splits is
  refused here, naming the id and the split files (2.3), via `requested_pairs`.
- **The host refusal (8.6).** `jobs/launch.py` refuses to run on any host but
  `login_host`, naming it. **Both sides are normalized through the `hosts:`
  entries' `alias` column** (errata: this machine answers `shiga` to `hostname`
  while the `hosts:` list calls it `tokyo105`;
  `legacy/ops/launch_common.py:41`).
- **The alive check (errata; 8.1 names one and never defines it).** A `loop`,
  `train` or `cpu` piece passes when its log file grows inside a 30 s window
  polled every 5 s and its session exists with no `Traceback` in the last 4 KB
  (`legacy/ops/launch_cmd.py:220-242`); a `service` piece passes when its
  `service_<kind>_<replica>.json` appears and its port answers, bounded by
  `DEFAULTS["launch_timeout_s"]`.
- **The card-busy test is not here** (errata): it lives in `jobs/registry.py`
  (`cards_busy` / `free`, which already probes `nvidia-smi`), and this file calls
  `registry.free()` inside its lock hold.

### Legacy sources

| what | where |
|---|---|
| dirty-tree probe, ledger exemption, fail-closed git | `legacy/ops/record.py:51-82` |
| writing the dirty-tree patch | `legacy/ops/record.py:247-267` |
| local-vs-ssh tmux launch and session test, the alias map | `legacy/ops/launch_common.py:41-67` |
| fail-closed card probe | `legacy/ops/launch_common.py:70-88` |
| the inner shell command | `legacy/ops/launch_cmd.py:196-202` |
| the alive check | `legacy/ops/launch_cmd.py:205-242` |
| launch ordering: probe every card, refuse the whole call, then launch, then check | `legacy/ops/launch_cmd.py:291-314` |
| refire: liveness refusal, card re-probe, resend the frozen command, rewrite the piece entry | `legacy/ops/launch_cmd.py:359-449` |

**Not ported:** the `TASKS` registry and the `--cmd` escape hatch
(`launch_cmd.py:74-138, 245-278`); `--dry-run`, `--service`, `--port`,
`--stall-line`, `--escalate-line`, `--warmup-line` and the `shardable` check
(`:59-64, 141-193, 271-276`); `register_all`'s three registrations
(`launch_common.py:91-163`), collapsed into one start row; `RUNMETA.json`
(`legacy/ops/runmeta.py`, whole file), absorbed by `meta.json.launches`; the
env-secrets rule and the `refires` counter read out of the sampler state
(`launch_cmd.py:377-385, 424-426`); the `new1_<run_id>_t<h>g<g>` session naming
(`:180-183`), replaced by 3.4's `<stage>-<key>-<piece>`; the per-refire log file
(`:427`), replaced by `tee -a` into one `log/<piece>.txt`.

## Acceptance

Run from the repo root and paste the real output. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`. **No command here may
launch a process on a card or on another host**; everything that would is section
"GPU / main session" below.

**B1 — imports under the probe interpreter, and no `__main__`.**
```bash
"$PR" -c "
import sys; sys.path.insert(0,'.')
from jobs import launch
print(launch.PROBE_PORT_BASE, hasattr(launch,'launch'), hasattr(launch,'refire'),
      hasattr(launch,'teardown_services'), hasattr(launch,'git_state'))
print('has main guard:', '__main__' in open('jobs/launch.py').read())"
```
Expected: `8500 True True True True` and `has main guard: False`, exit 0.

**B2 — `git_state` returns the five start-row fields and the real commit.**
```bash
T2=$(mktemp -d)
"$PR" -c "
import sys, subprocess, pathlib; sys.path.insert(0,'.')
from jobs import launch
g = launch.git_state(pathlib.Path('$T2'), True)
print(sorted(g))
print(g['commit'] == subprocess.run(['git','rev-parse','--short','HEAD'],capture_output=True,text=True).stdout.strip())
print('patch written:', (pathlib.Path('$T2')/'dirty.patch').exists() == g['dirty'])"
```
Expected: `['branch', 'commit', 'dirty', 'dirty_count', 'dirty_files']`; `True`;
`patch written: True`; exit 0.

**B3 — the ledger exemption, and the refusal on a dirty tree.** **No command here
writes into `jobs/runs.jsonl` or `jobs/RESULTS.md`** (spec section 9): the
exemption is proved as a pure function over a fabricated path list, and the
refusal against the worktree as it stands.
```bash
"$PR" -c "
import sys, pathlib; sys.path.insert(0,'.')
from jobs import launch
paths = ['jobs/runs.jsonl', 'jobs/RESULTS.md', 'jobs/runs.jsonl.lock',
         'data/trajectory_record.py', 'README.md']
print('kept:', [p for p in paths if not launch.is_ledger_path(p)])
g = launch.git_state(pathlib.Path('$T2'), True)
print('no ledger file in dirty_files:', not any(launch.is_ledger_path(f) for f in g['dirty_files']))
try:
    launch.git_state(pathlib.Path('$T2'), False)
    print('NO REFUSAL (clean worktree)')
except SystemExit as e:
    print('refused:', str(e).splitlines()[0][:60])"
```
Expected: `kept: ['data/trajectory_record.py', 'README.md']`;
`no ledger file in dirty_files: True`; then `refused: …` naming the dirty files,
which is the normal case in your worktree because you have just written
`jobs/launch.py` and `README.md`. If it prints `NO REFUSAL (clean worktree)`
instead, append a newline to `README.md` — **this ticket's own file, never a
ledger** — rerun the second half, then `git checkout README.md`. Paste whichever
branch ran.

**B4 — the launch gate, as a pure decision over rows.** Every row's `t` is built
from the clock inside the command, so the answers do not depend on the minute the
wave runs.
```bash
"$PR" -c "
import sys, time; sys.path.insert(0,'.')
from jobs import launch, registry
now = time.time()
TO = registry.DEFAULTS['launch_timeout_s']
young = time.strftime('%Y-%m-%d %H:%M', time.localtime(now - 60))
aged  = time.strftime('%Y-%m-%d %H:%M', time.localtime(now - 3*TO))
def row(rid, stage, kind, t):
    return dict(run_id=rid, stage=stage, key=rid.split('-')[1], t=t, dir='/nonexistent/'+rid,
                pieces=[dict(index=0, kind=kind, host='tokyo106', session=rid+'-0')])
def meta(r): return {r['run_id']: {'pieces': r['pieces']}}
r1 = row('train-k1', 'train', 'train', young)
print(1, launch.gate_open_row([r1], meta(r1), {'train-k1-0'}, now) is not None)
print(2, launch.gate_open_row([r1], meta(r1), set(), now) is not None)
print(3, launch.gate_open_row([r1], meta(r1), set(), now, {'train-k1': {0: [now-2000.0, now-1900.0]}}) is None)
print(4, launch.gate_open_row([r1], meta(r1), set(), now, {'train-k1': {0: [now-120.0, now-60.0]}}) is not None)
r2 = row('train-k2', 'train', 'train', aged)
print(5, launch.gate_open_row([r2], meta(r2), set(), now) is None)
r3 = row('sample-k3', 'sample', 'service', aged)
print(6, launch.gate_open_row([r3], meta(r3), {'sample-k3-0'}, now) is None)"
```
Expected, line by line:

| line | what it is | expected |
|---|---|---|
| 1 | a live work session on an open row | `True` (refused) |
| 2 | a row a minute old whose piece has **no session and no beat** — it has not appeared yet, so the third clause still holds | `True` (refused) |
| 3 | the same row, its piece having beaten and then gone (last beat 1900 s old, past the 1800 s stall line that two beats give, and no session): **observed dead**, so the third clause is dropped and no other holds | `True` (`is None`, not refused) |
| 4 | the same row with a last beat 60 s old: dead by liveness, but the heartbeat is inside the stall line, so the **second** clause holds | `True` (refused) |
| 5 | a row three timeouts old, no session, no beat | `True` (`is None`, not refused) |
| 6 | a live **service** session alone, on an aged row — 2.5's `kind != service` clause | `True` (`is None`, not refused) |

so six lines reading `1 True` through `6 True`, exit 0. Line 3 against line 2 is
the whole point of the "observed dead" rule, and line 2 is what stops two
`run.py` calls a second apart (`M-J8`).

**B5 — placement, ports and the piece command.**
```bash
"$PR" -c "
import sys; sys.path.insert(0,'.')
from jobs import launch
free = {'tokyo106': [0,1], 'tokyo107': [], 'shiga': [2]}
print(launch.place('loop', 0, free, serving_host=None, prefer_host=None, attached=False))
print(launch.place('service_probe', 0, free, serving_host=None, prefer_host=None, attached=False))
print(launch.place('service_agent', 1, free, serving_host='tokyo107', prefer_host=None, attached=True))
print(launch.place('train', 1, free, serving_host=None, prefer_host='shiga', attached=False))
print(launch.assign_ports('service_agent', 1, 8100, {8101}), launch.assign_ports('service_probe', 0, None, {8500,8501}))
print(launch.piece_command('/p/py','agent.loop','/o/sample/k','0','6','', '/o/sample/k/log/0.txt'))"
```
Expected: the configured login host for the loop piece and for the render-only
probe piece; `tokyo107` for the attached agent service (its server's host, no
card search); `shiga` for the train piece (the preferred host with a free card);
`8102 8502`; and a command string ending
`-m agent.loop --run-dir /o/sample/k --piece 0/6 2>&1 | tee -a /o/sample/k/log/0.txt`
with `cd <repo root> &&` at its head. Exit 0.

**B6 — `teardown_services` on a run with no service piece.**
```bash
T3=$(mktemp -d)
"$PR" -c "
import sys, json, pathlib; sys.path.insert(0,'.')
from jobs import launch
rd = pathlib.Path('$T3'); (rd/'meta.json').write_text(json.dumps({'pieces':[{'index':0,'kind':'loop','host':'shiga','session':'s-0'}]}))
print(launch.teardown_services(rd))"
```
Expected: `[]`, exit 0, and no ssh attempted.

**B7 — `refire` refuses a live piece.** With a real local tmux session standing
in for a live piece (no GPU, no model). **This check relies on the local-host
short-circuit of `jobs/registry.session_alive`** (ticket 03, errata against
8.0/3.4): when the host normalises to `login_host`, the session probe is a local
`tmux ls -F '#S'` with no `ssh` at all. Without it this check would either make
an implementer run `ssh` — which spec section 7 forbids — or get "alive"
fail-closed from a refused `ssh` and pass for the wrong reason. The shim below
proves no `ssh` was issued.
```bash
tmux new-session -d -s selfcheck-refire-probe 'sleep 60'
SHIM=$(mktemp -d)
printf '#!/bin/sh\ntouch %s/ssh_was_called\nexit 255\n' "$SHIM" > "$SHIM/ssh"
chmod +x "$SHIM/ssh"
PATH="$SHIM:$PATH" "$PR" -c "
import sys, json, pathlib; sys.path.insert(0,'.')
from jobs import launch
rd = pathlib.Path('$T3')
(rd/'meta.json').write_text(json.dumps({'pieces':[{'index':0,'kind':'loop','host':'$(hostname)','session':'selfcheck-refire-probe','cmd':'true','gpus':''}]}))
try:
    launch.refire(rd, {'commit':'x','branch':'y','dirty':False,'dirty_count':0,'dirty_files':[]}, 0)
    print('NO REFUSAL')
except SystemExit as e:
    print('refused:', 'selfcheck-refire-probe' in str(e))"
test ! -e "$SHIM/ssh_was_called" && echo "no ssh issued"
tmux kill-session -t selfcheck-refire-probe
rm -rf "$SHIM"
```
Expected: `refused: True`, then `no ssh issued`, exit 0. The shim `ssh` exits
255, so had the probe taken the remote path the refusal would still have fired
(fail-closed) but `ssh_was_called` would exist and the second line would be
missing — which is the difference between passing and passing for the wrong
reason.

**B8 — no absolute cluster path, and no `VERSION`.**
```bash
grep -n "/home/\|/net/" jobs/launch.py || echo NO_ABS_PATH
test "$(grep -c '^VERSION' jobs/launch.py)" = 0 && echo NO_VERSION
```
Expected: `NO_ABS_PATH`, then `NO_VERSION`, exit 0. The second line is wrapped in
`test` because `grep -c` **exits 1 when the count is zero**, so a bare `grep -c`
expecting `0` would report a correct implementation as a failed command.

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: `jobs/launch.py` is `venv: probe` and
has no `__main__` (B1); its `README.md` annotation line against the `ast`-parsed
import graph; no `/home/` or `/net/` literal (B8); and that it carries no
`VERSION` line, because no stage's version list names it.

### GPU / main session — not yours

An implementer that reaches any of these returns BLOCKED with the command.

- `M-J3` the first debug walk (`run.py train_probe ctool_qwen3_0pt6b --debug`): exactly
  one start row with `status: "launching"` whose `pieces` list holds one
  `service_agent`, one `service_probe` (render-only, no card, on `login_host`)
  and `sample.pieces` loop pieces; tmux sessions named `sample-<key>-<i>`; the
  monitoring command printed; and the walk stopping without waiting.
- `M-J4` on a later walk, once every requested pair is done: `done.json` with a
  `pairs` list equal to the requested pairs, both service tmux sessions gone,
  exactly one `ok` finish row, and the walk continuing into `build` in place.
- `M-J5` the `service_check` gate on an inject setting with the `<|end|>` encode
  fixture failing: `launch` returns `service_check`, **no loop piece starts**,
  `teardown_services` has ended the service sessions, and `run.py` appends a
  `launch_failed` finish row.
- `M-J6` refire: kill one loop piece's tmux session, then
  `run.py refire train_probe ctool_qwen3_0pt6b sample --piece 3` — it deletes only that
  piece's unfinished record files, restarts the session under the same name,
  appends a `launches` entry, leaves the five live pieces untouched, reuses the
  service pieces, and the refired piece opens `heartbeat/3-1.jsonl`.
- `M-J7` with two runs sharing one vLLM server, `run.py kill` on the attaching
  run refuses while the other run's `service_agent_0.json` names it in
  `attached_to`, and `run.py ls` flags the surviving server `orphan` after its
  owner finished.
- `M-J8` two `run.py` calls a second apart: the second refuses on the launch
  gate, naming the `run_id` and the row's age, and no second tmux session
  appears.

## Comments
