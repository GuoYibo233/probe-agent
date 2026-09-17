# Build plan — folder group `jobs`

Files: `jobs/launch.py`, `jobs/registry.py`, `jobs/runs.jsonl`, `jobs/RESULTS.md`,
`run.py`, `README.md`. The tree is fixed (`notes/plans/2026-09-14-structure-from-zero.md`
Part 1); nothing here adds, moves or renames a file. Interfaces come from
`notes/plans/2026-09-17-contracts.md` — Parts 8, 2.3, 2.4, 2.5, 2.6, 3.4, 1.1, 1.5,
7.1, 7.2, 7.4, 0.2, 0.3, 0.4 and the selfcheck list in 8.6.

One file outside the list is touched, by ticket T1 only: `.gitignore` gains the single
line `jobs/runs.jsonl.lock`, which the tree's own line for that file mandates
("the lock every append takes; ignored by git"). No other file outside the group is
edited by any ticket here.

---

## 1. Files

### 1.1 `jobs/registry.py`

**One sentence.** The registry: `runs.jsonl` rows under a lock, `meta.json`, the
heartbeat, the verdicts, `ls`/`where`/`find`/`kill`/`free`/`sync`, and `RESULTS.md`.

**venv.** `any` (standard library + PyYAML; measured: `yaml` imports under
`/usr/bin/python3` 3.10.12 as 5.4.1 and under all three venvs as 6.0.3).

**imports / used by (0.2).**
`imports: none (repo); [PyYAML]`.
`used by: run.py, jobs/launch.py, agent/loop.py, data/build_dataset.py,
train/utils/trainer.py, eval/utils/probe_eval.py, eval/score_run.py,
eval/method_table.py` (eight; a service piece writes no registry file and is judged by
its port, 8.5).
`reads: constants/path_outputs.yaml, jobs/runs.jsonl, run directories' meta.json and
heartbeat, ssh, tmux, nvidia-smi` (the per-host session and card probes of `ls`, `free`
and `kill`, fail-closed per 3.4).
`writes: jobs/runs.jsonl, jobs/RESULTS.md, meta.json, heartbeat/<piece>-<launch>.jsonl
(8.4), done.json`.

**File shape.** Two marked halves, writer first then reader (Part 8's own mitigation for
not splitting the file). `constants/path_outputs.yaml` is read lazily, inside the
functions that need it, and cached in a module global, so `import jobs.registry`,
`lock()`, `append_*`, `write_*` and `beat()` work before `constants/` exists.

**Names it must offer.** Writer half (§8.0):

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

Reader half (§8.0, §8.5):

```python
def ls(workflow: str | None = None, *, debug: bool = False,
       edited: dict[str, bool] | None = None,
       progress: dict[str, tuple[int, int]] | None = None) -> list[dict]   # 8.0
def where(stage: str, key: str, *, debug: bool = False) -> Path  # 8.0
def find(fields: dict) -> list[dict]                             # 8.0
def kill(run_id: str) -> list[str]                               # 8.0
def free() -> dict[str, list[int]]                               # 8.0
def sync() -> list[str]                                          # 8.0
def open_runs() -> list[dict]                                    # 8.0
def live_sessions() -> set[str]                                  # 8.0
def session_alive(host: str, session: str) -> bool               # 8.0
def typical_gap_s(beat_ts: list[float]) -> float | None          # 8.5
def stall_line_s(beat_ts: list[float]) -> float                  # 8.5
def rates(first_beat: dict, recent_beats: list[dict]) -> tuple[float | None, float | None]  # 8.5
def judge(piece: dict) -> tuple[str, bool]                       # 8.5
def judge_service(piece: dict) -> tuple[str, bool]               # 8.5
```

Pinned by this plan (not in the contracts; internal to the file but named so the
acceptance can exercise them and so `jobs/launch.py` reuses one copy):

```python
def render() -> None                    # rewrites jobs/RESULTS.md from jobs/runs.jsonl
def cards_busy() -> dict[str, set[int]] # the 2.5 busy test per host; free() is its complement
def fold(rows: list[dict]) -> dict[str, dict]   # run_id -> newest start + newest finish (8.2)
```

**Behaviour the ticket pins, by contract section.**

- `DEFAULTS` (8.5): `stall_line` 180 s, `escalate_line` 3, `warmup_s` 1800 s,
  `launch_timeout_s` 1800 s, plus the five shape constants of the ported verdict rules
  (errata 1): `stall_mult` 5.0, `typical_beats` 20, `min_intervals` 3,
  `recent_beats` 10, `slow_ratio` 0.5. There is no per-piece override.
- `lock()` (8.0, 8.6): one module-level file descriptor on `jobs/runs.jsonl.lock` plus a
  depth counter; `fcntl.flock(LOCK_EX)` at depth 0 only, released when the outermost
  context exits. `append_start`, `append_finish` and `write_meta` call it
  unconditionally.
- `append_start` / `append_finish` (8.1, 8.2): append one JSON object per line to
  `jobs/runs.jsonl`, never rewrite, then `render()`. Start-row fields are 8.1's table
  (`ev, t, run_id, stage, key, dir, workflow, setting, parent, swept, debug, upstream,
  versions, diff, commit, branch, dirty, dirty_count, dirty_files, host, pieces,
  status`), the piece entry's keys are
  `{index, kind, host, gpus, session, pid, log, port, endpoint_file, agent_replica,
  venv, cmd}`, `kind` one of `loop|train|cpu|service`, `status` always `launching`.
  Finish-row fields are 8.2's (`ev, t, run_id, status, counts, metrics, report,
  elapsed_s`), `status` one of `ok|failed|killed|launch_failed`.
- `t` is local time `"%Y-%m-%d %H:%M"` (8.1); it is the only launch-time source, so
  `elapsed_s` and `since_launch_s` are computed by parsing it back.
- `fold` (8.2): per `run_id` take the **newest** start row and the **newest** finish
  row; `elapsed_s` measured from the newest start row preceding that finish; `ls` folds
  the newest start row's `pieces` list.
- `write_meta` (8.3): rewrite the whole `meta.json` through a temporary name in the same
  directory and `os.replace`, under `lock()`. Fields are 8.3's table
  (`meta_version, stage, key, dir, versions, upstream, diff, debug, owners, launches,
  pieces, split_files, stage_extra`); `launches` is append-only, `pieces` is replaced
  entry by entry.
- `write_done` (1.5, 8.0): `{stage, key, commit, finished_at, counts, versions,
  metrics, report}` plus `pairs` and `stage_extra` when given, written through a
  temporary name and a rename.
- `beat` / `Heartbeat` (8.4): `<launch>` is `1 +` the largest `n` for which
  `heartbeat/<piece>-<n>.jsonl` exists in this run directory, `0` when none does; the
  file holds one bare JSON object per line (`done, total, unit, ts` required;
  `tok_in, tok_out, loss, status` optional) and the same object also goes to stdout
  behind legacy's `@hb ` prefix (errata 3). `finish()` writes the final beat with
  `status: "done"`. `beat` opens no `meta.json`.
- Verdicts (8.5): six values in priority order `done, dead, suspected stall,
  warming up, slowed, healthy`. `judge` and `judge_service` are pure functions over a
  piece dict whose keys this plan pins (errata 2):
  `{kind, alive, status, done, total, has_beat, beat_ts, beat_age_s, since_launch_s,
  port_ok}`. Liveness is per kind: `loop`/`train`/`service` alive while their tmux
  session is in `live_sessions()`; `cpu` alive while `os.kill(pid, 0)` on the login
  machine succeeds.
- `live_sessions` / `session_alive` (8.0, 3.4): one
  `ssh -o BatchMode=yes <host> "tmux ls -F '#S' 2>/dev/null; true"` per host of
  `constants/path_outputs.yaml`'s `hosts:` list, fail-closed — a failed or timed-out
  probe reports the session **alive**. Returns the bare session names.
- `free` / `cards_busy` (2.5, 8.6): a card is busy when `nvidia-smi` shows a compute
  process on it, **or** when it appears in the `pieces` list of a `meta.json` whose run
  has a start row with no finish row **and** either a live session **or** a start row
  younger than `DEFAULTS["launch_timeout_s"]`. Probed now, never cached; fail-closed, so
  an unclear probe counts the card busy.
- `kill` (8.6): end each piece of the run — a tmux piece by its session, a `cpu` piece by
  its `pid` — reading `host`/`session`/`pid` from `meta.json`'s `pieces` list, not from
  the start row; refuse while any live run's `service_<kind>_<replica>.json` names this
  `run_id` in `attached_to`. Returns the sessions it ended; `run.py` writes the `killed`
  finish row.
- `sync` (8.6, 8.2): fold every run directory's `done.json` and heartbeat files into the
  missing finish rows, write the `failed` row for a run with no `done.json` whose pieces
  `judge` calls `dead`, re-render `RESULTS.md`; it appends those rows itself through
  `append_finish` (errata 9) and returns the `run_id`s.
- `ls` (8.6): one folded dict per run with the piece verdicts, the heartbeat age, the
  progress (`progress` pair when given, else the sum of beats), and the flag set
  `edited, behind, consumed, split, pinned, dirty, debug, orphan`. `edited` and
  `progress` are passed in by `run.py` because this file imports nothing from the repo.
  A `launching` row older than `DEFAULTS["launch_timeout_s"]` with no sessions is
  reported `launch_failed` (8.1) — `ls` reports it, `run.py` writes the row.
- `render` (8.2, errata 10): one markdown table, newest run first, one row per `run_id`
  folded from its newest start and newest finish row, columns
  `run_id | started | stage | workflow/setting | commit | status | numbers | report`,
  with the header line saying the file is generated and must not be edited by hand.

**Legacy sources (algorithms to port).**

| what | legacy file:lines |
|---|---|
| append-only event stream, fold, `now()` | `legacy/ops/record.py:47-48, 84-120` |
| the rendered markdown table | `legacy/ops/record.py:137-215` |
| `flock` read-modify-write under one lock | `legacy/ops/gpu_jobs.py:64-73` |
| per-host `tmux ls` over ssh, fail-closed | `legacy/ops/gpu_jobs.py:76-94` |
| the fail-closed `nvidia-smi` card probe | `legacy/ops/launch_common.py:70-88` |
| liveness-gated deregistration (the shape `kill` follows) | `legacy/ops/gpu_jobs.py:439-472` |
| the six verdicts, `typical_gap_s`, `stall_line_s`, `rates`, `judge`, `_judge_service` | `legacy/ops/verdicts.py:16-116` |
| the heartbeat line and `emit` | `legacy/ops/heartbeat.py:15-33` |
| temp-name + rename, and the corrupt-file rename | `legacy/ops/runmeta.py:55-84` |

**Not ported, stated.** The resident sampler and its sampling history
(`legacy/ops/sampler.py`, whole file); `latest.json` / `MONITOR_DIR` and the freshness
fallback (`gpu_jobs.py:34-42, 213-249, 301-363, 489-500`); the web page and the watch
loop (`gpu_jobs.py:374-384`); tqdm log-tail parsing (`gpu_jobs.py:44-47, 97-118`); the
`{"active", "history"}` ledger shape and the `register`/`finish`/`json` CLI
(`gpu_jobs.py:50-73, 390-501`); `record.py`'s CLI and its `track`/`note`/`conclusion`
fields (`record.py:218-335`); the per-run detail blocks of `RESULTS.md`
(`record.py:173-212`); `verdicts.DEFAULTS["port_fail_rounds"]`,
`["sample_interval_s"]` and the round-counting service rule
(`verdicts.py:26, 17, 74-88`), replaced by 8.5's one-port-probe rule;
`heartbeat.parse` (`heartbeat.py:36-47`), superseded by reading the jsonl file.

### 1.2 `jobs/launch.py`

**One sentence.** The dirty-tree gate; pick free cards and ports; resolve the split
files; one tmux session per piece; the start row; the alive check; the `check` client
gate on the probe service; refire; and the teardown of a finished run's service pieces.

**venv.** `probe` (it runs on the login machine).

**imports / used by (0.2).**
`imports: experimental_settings/schema.py, jobs/registry.py, data/task_record.py
(done_pairs, is_done, owner, release), data/environments/__init__.py (tasks and
requested_pairs)`.
`used by: run.py`.
`reads: constants/path_datasets.yaml (the venv per environment and the venvs map),
constants/path_outputs.yaml (the login_host and the hosts list), models/table.yaml (the
serving block), the run directory's settings.yaml and meta.json,
service_<kind>_<replica>.json (its own run's and other live runs'), nvidia-smi, tmux,
git`.
`writes: the start row in jobs/runs.jsonl, meta.json launch entries, meta.json's
split_files, dirty.patch, the piece commands`.
It is a library with **no `__main__`**: `run.py` is the only command (0.2, 8.6).

**Names it must offer (0.2, 2.5).**

```python
PROBE_PORT_BASE = 8500                                                    # 7.4
def launch(stage, setting, run_dir, resolved, git) -> tuple[str, list[dict]]   # 0.2, 8.1
def refire(run_dir, git, piece=None) -> list[dict]                        # 0.2, 2.3
def teardown_services(run_dir) -> list[str]                               # 0.2, 2.3
def git_state(run_dir, allow_dirty) -> dict                               # 0.2, 2.5
```

Pinned by this plan (module-internal, named so the acceptance can exercise the decision
rules without a card):

```python
def gate_open_row(open_rows, meta_by_run, live_sessions, now_ts) -> str | None  # 2.5
def place(kind, cards_needed, free_by_host, *, serving_host, prefer_host,
          attached) -> str | None                                              # 3.4
def assign_ports(kind, replica, serving_port, taken) -> int                    # 7.4
def piece_command(python, module, run_dir, piece, n, gpus, log) -> str         # 3.4
def alive_check(pieces, window_s=30, poll_s=5) -> tuple[bool, list]            # 8.1
```

**Behaviour the ticket pins, by contract section.**

- `git_state(run_dir, allow_dirty)` (2.5): refuses a dirty tree without `--allow-dirty`,
  naming the files; writes `<run_dir>/dirty.patch` (`git diff HEAD`) when the flag is
  given; returns `{commit, branch, dirty, dirty_count, dirty_files}`; fail-closed — a
  failed git probe counts as dirty. `jobs/runs.jsonl`, `jobs/RESULTS.md` and `*.lock`
  never count as dirty. `commit` is the short sha (errata 12). `run.py` is its one
  caller, for all six stages.
- `launch(...)` order (8.1, 8.6), inside one `registry.lock()` hold: read the registry
  (`registry.open_runs()`), run the launch gate, run 7.4's attach test, read the card
  reservation (`registry.free()`), assign the ports, append the start row with
  `status: "launching"`. Then release the lock; start the **service** pieces and run the
  alive check on them; for an `inject` run run the `check` client against the probe
  service once its port answers; only then start the **loop** pieces.
- The launch gate (2.5): refuse a key whose newest start row has no finish row and any
  one of three things holds — a live session on its host in `meta.json`'s `pieces` entry,
  counting only pieces whose `kind` is not `service`; a heartbeat younger than the stall
  line; or a start row younger than `registry.DEFAULTS["launch_timeout_s"]`, that third
  clause holding only while no piece of that row has been observed `dead`. Print the
  session name when there is one, else the `run_id` and the row's age.
- Piece rule and venv come from `schema.STAGES` (2.1): venv is a string or a
  `{piece kind: venv name}` mapping with `"env"` meaning this setting's `data.env` row's
  `venv:` column in `constants/path_datasets.yaml` and `"any"` resolving to
  `venvs.probe` (6.3); the piece rule is `(kind, count_field_or_int, mode)` tuples.
- Placement (3.4): agent service on its table row's `serving.host`; an agent service the
  attach test matched takes no card, enters no card search and lands on that server's
  host; a checkpoint-loading probe service (1 card) and a train piece (1 card) take the
  first host in `constants/path_outputs.yaml`'s `hosts:` list with enough free cards,
  preferring the host this run's agent service is on; a `--render-only` probe piece takes
  no card and lands on `login_host`; loop pieces take no card and run on `login_host`. A
  run whose required cards are free on no host is refused, naming every host probed and
  its free count.
- The piece command (3.4, errata 6):
  `tmux new-session -d -s <stage>-<key>-<piece>  "cd <repo root> &&
  CUDA_VISIBLE_DEVICES=<ids> <venv python> -m <module> --run-dir <dir>
  [--piece <i>/<n>] 2>&1 | tee -a <run_dir>/log/<piece>.txt"`, with `--piece <i>/<n>`
  present **only** on a `sample` or `inject` loop piece. A piece on another host is
  started as `ssh -o BatchMode=yes <host> tmux new-session -d …`.
- Ports (7.4): the agent service first looks for an attachable live server (same
  `serving.host`, whose `service_agent_<replica>.json` claims the same `result:` block)
  and, finding one, takes that host and port and passes `--attach-only`; only when none
  is found does it start a server at `serving.port + replica`, moving to the next free
  port when one is taken. A probe service takes the first free port at or above
  `PROBE_PORT_BASE`.
- The two service command lines are 7.1's and 7.2's, verbatim; `--score-ckpt` and
  `--gen-ckpt` are the **train run directories** resolved from
  `_upstream["probe_score.train"]` and `_upstream["probe_gen.train"]` through
  `schema.run_dir_of`, `--temperature` is `resolved["probe_temperature"]`, and all four
  bracketed flags are **absent** under `--render-only`.
- `service_check` (7.2, 8.1): for an inject run, run
  `<probe python> -m models.probe_models.service check --base-url <url> --run-dir <dir>`
  after the probe piece's port answers and before the first loop piece; a non-zero exit
  is the `service_check` outcome.
- Return value (8.1): `(outcome, pieces)` with outcome `up`, `alive_check` or
  `service_check`; the piece entries come back either way. **Before returning any outcome
  but `up`**, call `teardown_services(run_dir)` and record in the returned list which
  sessions it ended.
- `teardown_services(run_dir)` (2.3): for each `meta.json` piece entry with
  `kind: service`, `ssh <host> tmux kill-session -t <session>`, skipped for a piece whose
  owning `run_id` appears in the `attached_to` field of another live run's
  `service_<kind>_<replica>.json`. Returns the sessions it ended.
- `refire(run_dir, git, piece=None)` (2.3): probe that piece's tmux session on the host
  in its `meta.json` entry and **refuse while it is alive**, naming the session and the
  host (fail-closed); warn when this piece already has more than one entry in
  `meta.json.launches` and proceed (**no quota**); release that piece's claims through
  `data/task_record.release(<run_dir>/records, registry.live_sessions(),
  registry.DEFAULTS["launch_timeout_s"])`; probe the cards again; restart the piece in a
  new tmux session; rewrite that piece's `meta.json` entry (`host`, `gpus`, `session`,
  `pid`, `cmd`) and append a `launches` entry carrying the `git` dict it was handed —
  both through `registry.write_meta` inside one lock hold.
- `meta.json.split_files` (8.3): resolved and written **before the pieces start**, one
  entry per split file with its path, sha1 and resolved task-id list, through
  `env.tasks(split)`; a `tasks` id that is in none of the splits is refused here, naming
  the id and the split files (2.3), through `requested_pairs`.
- Host refusal (8.6): `jobs/launch.py` refuses to run on any host but `login_host`,
  naming it; the comparison normalizes both sides through the `hosts:` entries' `alias`
  column (errata 7).

**Legacy sources.**

| what | legacy file:lines |
|---|---|
| dirty-tree probe, ledger exemption, fail-closed git | `legacy/ops/record.py:51-82` |
| writing the dirty-tree patch | `legacy/ops/record.py:247-267` |
| local-vs-ssh tmux launch and session test, the alias map | `legacy/ops/launch_common.py:41-67` |
| fail-closed card probe | `legacy/ops/launch_common.py:70-88` |
| the inner shell command (`cd … && CUDA_VISIBLE_DEVICES=… … | tee …`) | `legacy/ops/launch_cmd.py:196-202` |
| the alive check (log growth, session test, Traceback in the tail) | `legacy/ops/launch_cmd.py:205-242` |
| launch ordering: probe every card, refuse the whole call, then launch, then check | `legacy/ops/launch_cmd.py:291-314` |
| refire: liveness refusal, card re-probe, resend the frozen command, rewrite the piece entry | `legacy/ops/launch_cmd.py:359-449` |

**Not ported, stated.** The `TASKS` registry and the `--cmd` escape hatch
(`launch_cmd.py:74-138, 245-278`); `--dry-run`, `--service`, `--port`, `--stall-line`,
`--escalate-line`, `--warmup-line` and the `shardable` check
(`launch_cmd.py:59-64, 141-193, 271-276`); `register_all`'s three registrations
(`launch_common.py:91-163`), collapsed into one start row; `RUNMETA.json`
(`legacy/ops/runmeta.py`, whole file), absorbed by `meta.json.launches`; the
env-secrets rule and the `refires` counter read out of the sampler state
(`launch_cmd.py:377-385, 424-426`); the `new1_<run_id>_t<h>g<g>` session naming
(`launch_cmd.py:180-183`), replaced by 3.4's `<stage>-<key>-<piece>`; the per-refire
log file (`launch_cmd.py:427`), replaced by `tee -a` into one `log/<piece>.txt`.

### 1.3 `run.py`

**One sentence.** The one command: run one or several named settings of one workflow
file; `ls`, `where`, `find`, `free`, `kill`, `refire`, `retry`, `sync`, `table`,
`selfcheck`.

**venv.** `probe` (the interpreter this repo's commands are typed with).

**imports / used by (0.2).**
`imports: experimental_settings/schema.py, jobs/launch.py, jobs/registry.py,
data/task_record.py (done_pairs, is_done, owner, release),
data/environments/__init__.py (open_env, requested_pairs),
eval/utils/probe_eval.py (read_report), eval/method_table.py (table)`.
`used by: none (program)`.
`reads`/`writes`: 0.2's lines, verbatim, into the README.

**Command line (errata 11).**

```
python3 run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]
python3 run.py ls [workflow] [--debug]
python3 run.py where <workflow> <setting> <stage>
python3 run.py find section.field=value ...
python3 run.py kill <workflow> <setting> <stage>
python3 run.py refire <workflow> <setting> <stage> [--piece i] [--allow-dirty]
python3 run.py retry <workflow> <setting> <stage> [--allow-dirty]
python3 run.py table [workflow] [--out FILE]
python3 run.py free
python3 run.py sync
python3 run.py selfcheck
```

The ten subcommand names are reserved; any other first token is a workflow **file** stem
resolved to `experimental_settings/<name>.yaml`. `section.field=value` tokens become
`load`'s `overrides` (5.7 step 5).

**The walk** (2.3, 2.4, 2.5, 3.4, 8.1, 8.2, 9(c)#1). For each `Setting` that
`schema.load(file, name, debug=…, overrides=…)` returns (a list; a `sweep:` gives
children, 5.5), for each stage of `cfg._workflow` in order:

1. `key = schema.key(stage, cfg)`, `run_dir = schema.run_dir(stage, cfg)`.
2. Skip test. For `sample` and `inject` it is the **pair check**: build the requested
   list with `requested_pairs(env, splits, tasks, n_tasks, seeds)`, project the triples
   to `(task_id, seed)` pairs, and compare against
   `task_record.done_pairs(<run_dir>/records, pairs)`; a subset means skip. Every other
   stage skips on the presence of `done.json`.
3. Before a skip: compare the directory's `consumed.json` entries — and, for `sample` and
   `inject`, `meta.json`'s `split_files` hashes — against the files they name; on a
   mismatch **refuse**, naming the file and both hashes, and stop. On a skip, add this
   `{workflow, setting}` to `meta.json`'s `owners` through `registry.write_meta`, under
   the lock.
4. A `sample`/`inject` directory that is partly done: while any piece of `kind` `loop` or
   `train` of that run has a live session, release the dead sessions' claims through
   `task_record.release(...)`, report them, and launch nothing; once none has, relaunch
   for the missing pairs, reusing the run's live service pieces.
5. Completeness reached: write `done.json` through
   `registry.write_done(run_dir, …, pairs=pairs, counts={records: len(pairs),
   tasks: …, seeds: …}, metrics={}, report=None, versions=cfg._versions)` (1.5), call
   `launch.teardown_services(run_dir)`, append the `ok` finish row, and go on to the next
   stage.
6. Otherwise launch. For `inject`, first hold 2.5's two `run.py` gates — the two
   referenced train runs share a `_upstream["build"]` key, and the recorded `_versions`
   of `data/probe_input.py`, `models/probe_models/base.py` and each train run's own
   backbone module equal the current source `VERSION`s — and read the classifier report
   with `probe_eval.read_report(...)` to fill `resolved["probe_temperature"]` (5.4).
   Refuse when any referenced run has no `done.json`.
7. Inside one `registry.lock()` hold: `git = launch.git_state(run_dir, allow_dirty)`,
   then `schema.freeze(setting, stage, run_dir, resolved, git["commit"])`, then
   `registry.write_meta(...)`, then
   - a card stage (`sample`, `inject`, `train`): `outcome, pieces =
     launch.launch(stage, cfg, run_dir, resolved, git)` (which takes the same lock
     re-entrantly and appends the start row); after the hold, on any outcome but `up`
     append a `launch_failed` finish row and stop; on `up` print the monitoring command
     (`run.py ls <workflow>`) and **stop the walk** — an asynchronous GPU stage is never
     waited on;
   - a CPU stage (`build`, `eval`, `score`): run `registry.open_runs()`'s refusal, spawn
     the process in place with the `venvs.probe` interpreter and the command shape of
     2.6, capture its pid **inside the hold** (errata 5), append the start row with a
     single `kind: cpu` piece entry, release the lock, wait for the exit; on a non-zero
     exit append a `failed` finish row immediately inside a fresh hold and stop; on zero
     append the `ok` finish row from the stage's own `done.json` and continue.
8. A directory whose `done.json` exists with no finish row gets an `ok` finish row on the
   walk that first sees it (8.2).

**Subcommands** (8.6). `ls` computes `edited` (the named setting's current key against the
directory) and `progress` (`task_record.done_pairs` against the requested total) itself
and passes both into `registry.ls`; `where` uses `schema.run_dir` (it has the setting and
therefore `--debug`); `find` passes the parsed `section.field=value` dict to
`registry.find`; `kill` calls `registry.kill` and writes the `killed` finish row;
`refire` resolves the setting and the run directory, takes `launch.git_state` and
re-freezes `_commit` inside the lock, then calls `launch.refire(run_dir, git, piece)`;
`retry` deletes `last/`, `train_log.jsonl` and the markers and launches normally (2.4);
`table` calls `eval.method_table.table(workflow=None, out=None) -> str` (8.6);
`free` prints `registry.free()`; `sync` prints `registry.sync()`.

**Host refusal** (8.6): `run.py` refuses to run on any host but `login_host`, naming it
and the host it is on, with the alias normalization of errata 7.

**`selfcheck`** (8.6) — implemented by ticket T4. Its checks, in the contract's order:
the README's file list against the tree; every annotation line against the real import
graph, parsed with `ast` and never by importing; every axis literal against the files
behind it (`schema` axis values vs `agent/inject_format.FORMATS` keys, method names vs
`train/methods/*.py` + `eval/methods/*.py`, `data.env` vs `data/environments/*.py`);
one integer `VERSION` line at column zero per module the stage table names, and one
literal apiece for `PROBE_KIND`, `STOP`, `EFFORTS`, `DEFAULT_EFFORT`, `DEFAULT_DATE`,
`LORA_TARGETS`, `CHECKPOINT_META`, `INSTRUCTIONS` and `SPLIT_ROLE`; a `DEFAULTS` and a
`REQUIRED` literal in every format file under `data/`, with every name in `REQUIRED` a
declared column; the two `PROBE_KIND` declarations of a method equal; every family's
`DEFAULT_EFFORT` in its own `EFFORTS`; every `models/table.yaml` row's `family` resolving
to a file under `agent_models/` or `probe_models/` per its `role`, and its `weights`
alias present in `constants/path_models.yaml`; no `/home/` or `/net/` path in code
outside `constants/`; each `any` file imported under **every** interpreter of the
`venvs:` map; each family module imported under the probe and the vllm interpreter.
It also refuses a workflow file whose stem is a reserved subcommand name (errata 11).

**Legacy sources.** `legacy/run.py:799-827` (the dirty gate, which moves into
`launch.git_state`), `legacy/run.py:830-840` (`tail_of`, for the failed-launch report),
`legacy/run.py:1270-1305` (the subcommand dispatch shape),
`legacy/run.py:1172-1267` (the selfcheck shape: count, print one line per problem, exit
1 on any).

**Not ported, stated.** `TASKS` and `RECIPES` and everything that reads them
(`legacy/run.py:80-768, 872-1083, 1117-1171`); the recipe engine and `status`
(`legacy/run.py:881-1111`); `build_cmd` / `task_env` / `gate_of` / `run_direct` /
`print_handoff` (`legacy/run.py:771-869`); the `PY` interpreter map, replaced by
`constants/path_datasets.yaml`'s `venvs:`; the `configs/` preset and model-table checks
inside selfcheck (`legacy/run.py:1237-1264`), replaced by the `models/table.yaml` and
`constants/path_models.yaml` checks of 8.6.

### 1.4 `jobs/runs.jsonl`

One registry row per stage run, appended at start and at finish by `jobs/registry.py`;
never edited by hand; in git. Created by T1 as an **empty file** (0 bytes) so the first
append has a file to append to and git tracks it. No code reads it except
`jobs/registry.py`.

### 1.5 `jobs/RESULTS.md`

Rendered from `jobs/runs.jsonl` by `jobs/registry.py` on every append; never edited by
hand. Created by T1 as the output of `registry.render()` over the empty ledger: the
title, the generated-file warning, and the "no runs yet" line.

### 1.6 `README.md`

**One sentence.** For the future reader: this tree, one line per file, how to run, the
extension recipes.

Four sections, in this order:

1. **What this repo is and how to run it** — the principle list's one-line form, the
   command shapes of run.py above, the `--debug` line, and the rule that outputs live
   under `constants/path_outputs.yaml`'s `root` and `run.py where` prints the path (3.4).
2. **The tree, one entry per file** — reproduced from contracts 0.2, which is
   authoritative, in 0.1's exact five-line annotation format and punctuation, because
   `run.py selfcheck` parses it:
   ```
   path/to/file.py — one sentence of what it does.
     imports: a.py, b.py
     used by: c.py, d.py
     reads:   <format or file>
     writes:  <format or file>
     venv:    any | appworld | probe | vllm
   ```
   All 34 Python files of 0.3 plus the non-Python entries (`constants/*.yaml`,
   `experimental_settings/*.yaml`, `models/table.yaml`, `jobs/runs.jsonl`,
   `jobs/RESULTS.md`, `tests/`).
3. **The extension recipes** — 0.4's seven scenario rows plus the two non-extension rows,
   each as "what you edit, in order, and what it costs".
4. **The ledgers** — `jobs/runs.jsonl` append-only, `jobs/RESULTS.md` rendered, both
   never hand-edited; `notes/` is the owner's.

**Legacy source.** `legacy/MAP.md` is the ancestor (the code map: what each program does
and how to use it); nothing is copied from it, because every line of section 2 comes from
contracts 0.2.

---

## 2. Order of construction, and what must exist first

1. **`jobs/registry.py`** — first; it imports nothing from the repo. Needs at run time
   (not at import): `constants/path_outputs.yaml` with `root`, `debug_subdir`,
   `login_host` and `hosts:` (6.3), from the constants/settings folder.
2. **`jobs/runs.jsonl` + `jobs/RESULTS.md` + the `.gitignore` line** — with it, in the
   same ticket.
3. **`jobs/launch.py`** — after registry. Needs:
   `experimental_settings/schema.py`: `STAGES`, `load_frozen`, `run_dir_of`;
   `data/task_record.py`: `done_pairs`, `is_done`, `owner`, `release`;
   `data/environments/__init__.py`: `open_env`, `requested_pairs`, `Environment.tasks`;
   `constants/path_datasets.yaml` (the `venvs:` map and each environment's `venv` column);
   `models/table.yaml` (the `serving:` block).
   At run time only (never imported): `models/agent_models/service.py serve` and
   `models/probe_models/service.py serve|check`.
4. **`run.py`** — after both. Needs additionally:
   `experimental_settings/schema.py`: `load`, `key`, `run_dir`, `freeze`, plus the two
   names errata 8 adds, `upstream(stage, setting)` and `module_version(path)`;
   `eval/utils/probe_eval.py`: `read_report`;
   `eval/method_table.py`: `table(workflow=None, out=None) -> str`.
5. **`README.md` + `run.py selfcheck`** — last, after every folder has landed its files,
   because a green selfcheck is a statement about the whole tree.

---

## 3. Acceptance, CPU (the implementer runs these from the repo root)

Interpreters: `python3` = `/usr/bin/python3` (3.10.12, PyYAML 5.4.1, no numpy);
`external/probe-env/bin/python` (3.11); `external/appworld/venv/bin/python` (3.12);
`external/vllm-env/bin/python` (3.12).

None of these commands writes into the real `jobs/runs.jsonl`: the registry resolves its
paths from `__file__`, so every functional check runs against a throw-away copy of the
file in a temp tree.

### A. `jobs/registry.py`

**A1 — imports as `any` under every interpreter of the `venvs:` map.**
```bash
for P in external/probe-env/bin/python external/appworld/venv/bin/python \
         external/vllm-env/bin/python; do
  $P -c "import sys; sys.path.insert(0,'.'); from jobs import registry as r; print(r.DEFAULTS['launch_timeout_s'], r.DEFAULTS['stall_line'])"
done
```
Expected: `1800 180` printed three times, exit 0 each time. The three interpreters are
the `venvs:` map's, which is what `venv: any` and `selfcheck` are defined over (the
wrapup planner's 0.1 erratum). One extra line, because this file is standard library
plus PyYAML and nothing else:
`/usr/bin/python3 -c "import sys; sys.path.insert(0,'.'); from jobs import registry"`
must also exit 0 (measured: system PyYAML is 5.4.1).

**A2 — the re-entrant lock, and that a second process really blocks.**
```bash
external/probe-env/bin/python - <<'PY'
import sys, time, subprocess; sys.path.insert(0,'.')
from jobs import registry as r
with r.lock():
    with r.lock():
        t0 = time.time()
        p = subprocess.Popen([sys.executable, "-c",
            "import sys,time; sys.path.insert(0,'.');"
            "from jobs import registry as r;"
            "t=time.time();\nwith r.lock(): print('waited %.1f' % (time.time()-t))"])
        time.sleep(2)
print("outer released")
p.wait()
PY
```
Expected: `outer released` printed first, then `waited 2.0` (any value >= 1.5), exit 0.

**A3 — start row, finish row, fold, `RESULTS.md`, `open_runs` (throw-away tree).**
```bash
T=$(mktemp -d); mkdir -p $T/jobs $T/constants; cp jobs/registry.py $T/jobs/
cat > $T/constants/path_outputs.yaml <<'Y'
root: TMPROOT/out
debug_subdir: debug
login_host: shiga
hosts:
  - {name: tokyo105, alias: shiga, cards: 4}
Y
sed -i "s|TMPROOT|$T|" $T/constants/path_outputs.yaml
external/probe-env/bin/python - "$T" <<'PY'
import sys, json, pathlib; T = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(T))
from jobs import registry as r
rd = T/"out/sample/abc123abc123"; rd.mkdir(parents=True)
row = dict(ev="start", t="2026-09-17 10:00", run_id="sample-abc123abc123",
           stage="sample", key="abc123abc123", dir=str(rd),
           workflow="baseline", setting="gptoss120b_appworld", parent=None, swept=None,
           debug=False, upstream={}, versions={"agent/loop.py": 1}, diff={"sample.max_steps": 40},
           commit="deadbee", branch="from-zero", dirty=False, dirty_count=0, dirty_files=[],
           host="shiga", status="launching",
           pieces=[dict(index=0, kind="loop", host="shiga", gpus="", session="sample-abc123abc123-0",
                        pid=None, log=str(rd/"log/0.txt"), port=None, endpoint_file=None,
                        agent_replica=0, venv="appworld", cmd="…")])
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
`lines: 2`, `results has run: True`, `find: ['sample-abc123abc123']`, exit 0. The real
`jobs/runs.jsonl` is unchanged (`git status --porcelain jobs/` prints nothing).

**A4 — `write_meta`, `write_done` atomicity and fields.**
```bash
external/probe-env/bin/python - "$T" <<'PY'
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
Expected: `owners: 2 stage kept: sample`;
`done keys: ['commit', 'counts', 'finished_at', 'key', 'metrics', 'pairs', 'report', 'stage', 'versions']`;
the directory listing holds no `*.tmp`; exit 0.

**A5 — the heartbeat file, its name and its `<launch>` index.**
```bash
external/probe-env/bin/python - "$T" <<'PY'
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
Expected: `['3-0.jsonl', '3-1.jsonl']` (a second `beat` on the same piece opens the next
`<launch>` index), then `3 ['done', 'total', 'ts', 'unit'] done` — three beats, the first
carrying exactly the four required keys, the last carrying `status: "done"`; exit 0.

**A6 — the verdicts, as pure functions.**
```bash
external/probe-env/bin/python -c "
import sys; sys.path.insert(0,'.')
from jobs import registry as r
D = r.DEFAULTS
print(r.typical_gap_s([0.0,60.0,120.0,180.0]))
print(r.typical_gap_s([0.0,60.0]))
print(r.stall_line_s([0.0,60.0]), r.stall_line_s([0.0,60.0,120.0,180.0]))
base = dict(kind='loop', alive=True, status=None, done=1, total=10, has_beat=True,
            beat_ts=[0.0,60.0,120.0,180.0], beat_age_s=10.0, since_launch_s=300.0, port_ok=None)
print(r.judge(dict(base, status='done')))
print(r.judge(dict(base, alive=False)))
print(r.judge(dict(base, beat_age_s=100000.0)))
print(r.judge(base))
print(r.judge_service(dict(kind='service', alive=True, port_ok=True, since_launch_s=10.0)))
print(r.judge_service(dict(kind='service', alive=True, port_ok=False, since_launch_s=10.0)))
print(r.judge_service(dict(kind='service', alive=True, port_ok=False, since_launch_s=99999.0)))
print(r.judge_service(dict(kind='service', alive=False, port_ok=False, since_launch_s=10.0)))
"
```
Expected, line by line: `60.0`; `None`; `1800.0 300.0`; `('done', False)`;
`('dead', True)`; `('suspected stall', True)`; `('healthy', False)`;
`('healthy', False)`; `('warming up', False)`; `('suspected stall', True)`;
`('dead', True)`; exit 0.

**A7 — the concurrent-append check, the one `tests/` file this group adds.**
`tests/test_registry_concurrent_append.py` (header `# venv: probe`) forks 8 processes
that each append 20 start rows into a temp copy of the tree and asserts that 160 lines
land and that every line parses as JSON.
```bash
external/probe-env/bin/python tests/test_registry_concurrent_append.py
```
Expected: `OK` from unittest, exit 0. (This is the fourth of the four checks the tree's
`tests/` line names: "two pieces appending to runs.jsonl at once both land".)

**A8 — the ledger seed files are what the code produces.**
```bash
test ! -s jobs/runs.jsonl && echo "ledger empty"; head -3 jobs/RESULTS.md
```
Expected: `ledger empty`, then the title line, the generated-file warning, and the
"no runs yet" line; `git check-ignore jobs/runs.jsonl.lock` prints the path.

### B. `jobs/launch.py`

**B1 — imports under the probe interpreter, and no `__main__`.**
```bash
external/probe-env/bin/python -c "
import sys; sys.path.insert(0,'.')
from jobs import launch
print(launch.PROBE_PORT_BASE, hasattr(launch,'launch'), hasattr(launch,'refire'),
      hasattr(launch,'teardown_services'), hasattr(launch,'git_state'))
print('has main guard:', '__main__' in open('jobs/launch.py').read())
"
```
Expected: `8500 True True True True` and `has main guard: False`, exit 0.

**B2 — `git_state` returns the five start-row fields and the real commit.**
```bash
T2=$(mktemp -d)
external/probe-env/bin/python -c "
import sys, subprocess, pathlib; sys.path.insert(0,'.')
from jobs import launch
g = launch.git_state(pathlib.Path('$T2'), True)
print(sorted(g))
print(g['commit'] == subprocess.run(['git','rev-parse','--short','HEAD'],capture_output=True,text=True).stdout.strip())
print('patch written:', (pathlib.Path('$T2')/'dirty.patch').exists() == g['dirty'])
"
```
Expected: `['branch', 'commit', 'dirty', 'dirty_count', 'dirty_files']`; `True`;
`patch written: True`; exit 0.

**B3 — the ledger exemption, and the refusal on a dirty tree.**
```bash
printf '\n' >> jobs/RESULTS.md
external/probe-env/bin/python -c "
import sys, pathlib; sys.path.insert(0,'.')
from jobs import launch
g = launch.git_state(pathlib.Path('$T2'), True)
print('ledger exempt:', not any('jobs/RESULTS.md' in f for f in g['dirty_files']))
try:
    launch.git_state(pathlib.Path('$T2'), False)
    print('NO REFUSAL')
except SystemExit as e:
    print('refused:', str(e).splitlines()[0][:40])
"
git checkout jobs/RESULTS.md
```
Expected: `ledger exempt: True`; then either `refused: …` naming the dirty files when the
worktree has other modifications, or — on a clean worktree — no refusal, in which case
the implementer repeats the second half after `touch jobs/launch.py` to prove the
refusal fires. Paste whichever branch ran.

**B4 — the launch gate, as a pure decision over rows.**
```bash
external/probe-env/bin/python -c "
import sys, time; sys.path.insert(0,'.')
from jobs import launch, registry
now = time.time()
rows = [dict(run_id='train-k1', stage='train', key='k1', t='2026-09-17 10:00', pieces=[dict(index=0,kind='train',host='tokyo106',session='train-k1-0')])]
meta = {'train-k1': {'pieces': [dict(index=0,kind='train',host='tokyo106',session='train-k1-0')]}}
print(launch.gate_open_row(rows, meta, {'train-k1-0'}, now) is not None)
print(launch.gate_open_row(rows, meta, set(), now) is not None)
srv = [dict(run_id='sample-k2', stage='sample', key='k2', t='2026-09-17 10:00', pieces=[dict(index=0,kind='service',host='tokyo106',session='sample-k2-0')])]
msrv = {'sample-k2': {'pieces': [dict(index=0,kind='service',host='tokyo106',session='sample-k2-0')]}}
print(launch.gate_open_row(srv, msrv, {'sample-k2-0'}, now + 2*registry.DEFAULTS['launch_timeout_s']) is None)
"
```
Expected: `True` (a live work session refuses); `True` (a start row younger than
`launch_timeout_s` refuses on its own); `True` (a live **service** session alone, on an
aged row, does not refuse — 2.5's `kind != service` clause); exit 0.

**B5 — placement and ports.**
```bash
external/probe-env/bin/python -c "
import sys; sys.path.insert(0,'.')
from jobs import launch
free = {'tokyo106': [0,1], 'tokyo107': [], 'shiga': [2]}
print(launch.place('loop', 0, free, serving_host=None, prefer_host=None, attached=False))
print(launch.place('service_probe', 0, free, serving_host=None, prefer_host=None, attached=False))
print(launch.place('service_agent', 1, free, serving_host='tokyo107', prefer_host=None, attached=True))
print(launch.place('train', 1, free, serving_host=None, prefer_host='shiga', attached=False))
print(launch.assign_ports('service_agent', 1, 8100, {8101}), launch.assign_ports('service_probe', 0, None, {8500,8501}))
print(launch.piece_command('/p/py','agent.loop','/o/sample/k','0','6','', '/o/sample/k/log/0.txt'))
"
```
Expected: `login_host` for the loop piece and for the render-only probe piece (printed as
the configured login host name); `tokyo107` for the attached agent service (its server's
host, no card search); `shiga` for the train piece (the preferred host with a free card);
`8102 8502`; and a command string ending
`-m agent.loop --run-dir /o/sample/k --piece 0/6 2>&1 | tee -a /o/sample/k/log/0.txt`
with `cd <repo root> &&` at its head. Exit 0.

**B6 — `teardown_services` on a run with no service piece.**
```bash
T3=$(mktemp -d)
external/probe-env/bin/python -c "
import sys, json, pathlib; sys.path.insert(0,'.')
from jobs import launch
rd = pathlib.Path('$T3'); (rd/'meta.json').write_text(json.dumps({'pieces':[{'index':0,'kind':'loop','host':'shiga','session':'s-0'}]}))
print(launch.teardown_services(rd))
"
```
Expected: `[]`, exit 0, and no ssh is attempted.

**B7 — `refire` refuses a live piece.** With a real local tmux session standing in for a
live piece (no GPU, no model):
```bash
tmux new-session -d -s selfcheck-refire-probe 'sleep 60'
external/probe-env/bin/python -c "
import sys, json, pathlib; sys.path.insert(0,'.')
from jobs import launch
rd = pathlib.Path('$T3')
(rd/'meta.json').write_text(json.dumps({'pieces':[{'index':0,'kind':'loop','host':'$(hostname)','session':'selfcheck-refire-probe','cmd':'true','gpus':''}]}))
try:
    launch.refire(rd, {'commit':'x','branch':'y','dirty':False,'dirty_count':0,'dirty_files':[]}, 0)
    print('NO REFUSAL')
except SystemExit as e:
    print('refused:', 'selfcheck-refire-probe' in str(e))
"
tmux kill-session -t selfcheck-refire-probe
```
Expected: `refused: True`, exit 0.

### C. `run.py`

**C1 — usage and the reserved names.**
```bash
external/probe-env/bin/python run.py; echo "rc=$?"
external/probe-env/bin/python run.py nosuchworkflow x 2>&1 | tail -1
```
Expected: the usage block listing the walk form and the ten subcommands, `rc=0`; then a
message naming `experimental_settings/nosuchworkflow.yaml` as missing, exit non-zero.

**C2 — the host normalization and the login-host refusal.**
```bash
external/probe-env/bin/python -c "
import sys; sys.path.insert(0,'.')
import run
hosts = [{'name':'tokyo105','alias':'shiga','cards':4},{'name':'tokyo106','cards':8}]
print(run.normalize_host('shiga', hosts), run.normalize_host('tokyo106', hosts))
try:
    run.require_login_host('tokyo999', hosts, 'tokyo105')
    print('NO REFUSAL')
except SystemExit as e:
    print('refused:', 'tokyo999' in str(e) and 'tokyo105' in str(e))
"
```
Expected: `tokyo105 tokyo106`; `refused: True`; exit 0.

**C3 — the read-only subcommands run against an empty ledger.**
```bash
external/probe-env/bin/python run.py ls; echo "rc=$?"
external/probe-env/bin/python run.py find stage=sample; echo "rc=$?"
```
Expected: for each, a one-line "no runs" message (or a header with no rows) and `rc=0`;
`git status --porcelain jobs/` stays empty.

**C4 — the walk's skip test and the CPU-stage row pair, on a fixture.** Once
`experimental_settings/`, `constants/` and `data/` have landed (wave dependency), on a
prepared throw-away outputs root:
```bash
external/probe-env/bin/python run.py where train_probe ctool_q06 sample
external/probe-env/bin/python run.py where train_probe ctool_q06 build
```
Expected: two absolute paths under `constants/path_outputs.yaml`'s `root`, of the shape
`<root>/sample/<12 hex>` and `<root>/build/<12 hex>`, printed whether or not they exist,
exit 0 both times.

### D. `README.md` and `selfcheck`

**D1 — every README entry parses into the five annotations.**
```bash
external/probe-env/bin/python -c "
import sys; sys.path.insert(0,'.')
import run
ent = run.readme_entries('README.md')
py = [p for p in ent if p.endswith('.py')]
print(len(py), all(set(ent[p]) >= {'imports','used by','reads','venv'} for p in py))
"
```
Expected: `34 True`, exit 0.

**D2 — selfcheck's parsers, on fixtures written in the command.**
```bash
external/probe-env/bin/python -c "
import sys, pathlib, tempfile; sys.path.insert(0,'.')
import run
d = pathlib.Path(tempfile.mkdtemp()); f = d/'m.py'
f.write_text('VERSION = 3\nimport os\nfrom data import example\nclass A:\n    VERSION = VERSION\n')
print(run.literal_of(f, 'VERSION'))
print(sorted(run.imports_of(f)))
g = d/'bad.py'; g.write_text('VERSION = 1\nVERSION = 2\n')
print(run.literal_of(g, 'VERSION'))
"
```
Expected: `3`; `['data.example', 'os']`; then a refusal naming two matches for `VERSION`
(a raised `SystemExit` or a `None` plus a printed problem, whichever the implementation
uses — the ticket pins "more than one match is a failure"), exit 0 for the first two
lines.

**D3 — the whole-tree selfcheck.** This is the integration line, run by the integrator
once every folder has landed, not by the T4 implementer:
```bash
external/probe-env/bin/python run.py selfcheck; echo "rc=$?"
```
Expected: `selfcheck: 34 python files, 0 problems` and `rc=0`.

### Selfcheck lines that apply to this group's own files

- `jobs/registry.py` is `venv: any`: it must import under **every** interpreter of
  `constants/path_datasets.yaml`'s `venvs:` map (A1 above is the same check).
- `jobs/launch.py` is `venv: probe` and has no `__main__` (B1).
- Neither `jobs/registry.py` nor `run.py` may hold a `/home/` or `/net/` literal outside
  `constants/` (8.6). Check:
  `grep -n "/home/\|/net/" run.py jobs/*.py` prints nothing.
- Every annotation line of `run.py`, `jobs/launch.py` and `jobs/registry.py` in
  `README.md` must equal the real import graph (D3).
- `jobs/registry.py` carries no `VERSION` line: it is in no stage's version list (2.2),
  and selfcheck only demands one from modules the stage table names.

---

## 4. Acceptance, GPU or cross-host (for the main session, not the implementer)

These need ssh to other hosts, cards, or both. Each names what it must show.

1. **Per-host probes.**
   `external/probe-env/bin/python run.py free`
   Must print one line per host of `constants/path_outputs.yaml`'s `hosts:` list with its
   free card ids, and must print an empty list — never a full one — for a host whose ssh
   fails (fail-closed, 3.4). Cross-check one host by hand with
   `ssh <host> nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`.
2. **Live sessions.**
   `external/probe-env/bin/python -c "import sys;sys.path.insert(0,'.');from jobs import registry as r;print(sorted(r.live_sessions()))"`
   Must list the tmux sessions of every host, and must report a session **alive** when the
   ssh to its host is broken (test by pointing one `hosts:` entry at an unreachable name).
3. **A first debug walk** (needs every folder):
   `external/probe-env/bin/python run.py train_probe ctool_q06 --debug`
   Must, for `sample`: append exactly one start row with `status: "launching"` whose
   `pieces` list holds one `service_agent`, one `service_probe` (render-only, no card,
   on `login_host`) and `sample.pieces` loop pieces; create the tmux sessions named
   `sample-<key>-<i>`; print the monitoring command; and stop without waiting.
   `run.py ls train_probe` must then show the piece verdicts and a progress pair.
4. **Completeness, teardown, finish row.** On a later `run.py train_probe ctool_q06
   --debug`, once every requested pair is done: `done.json` appears with a `pairs` list
   equal to the requested pairs, both service tmux sessions are gone, exactly one `ok`
   finish row is appended, and the walk continues into `build` in place.
5. **The `service_check` gate.** On an `inject` setting, with the probe service's
   `<|end|>` encode fixture failing: `launch` must return `service_check`, no loop piece
   may start, `teardown_services` must have ended the service sessions, and `run.py` must
   append a `launch_failed` finish row.
6. **Refire.** Kill one loop piece's tmux session, then
   `run.py refire train_probe ctool_q06 sample --piece 3`: it must delete only that
   piece's unfinished record files, restart the session under the same name, append a
   `launches` entry, leave the five live pieces untouched, reuse the service pieces, and
   the refired piece must open `heartbeat/3-1.jsonl`.
7. **Kill and the attach skip.** With two runs sharing one vLLM server,
   `run.py kill <workflow> <setting> sample` on the attaching run must refuse while the
   other run's `service_agent_0.json` names it in `attached_to`, and `run.py ls` must flag
   the surviving server `orphan` after its owner finished.
8. **Two sessions at once.** Two `run.py <workflow> <setting>` calls a second apart on the
   login machine: the second must refuse on the launch gate, naming the `run_id` and the
   row's age (9(c)#9), and no second tmux session may appear.

---

## 5. Tickets

### T1 — The registry: rows, lock, heartbeat, verdicts, subcommand readers

**Files.** `jobs/registry.py` (new), `jobs/runs.jsonl` (new, empty),
`jobs/RESULTS.md` (new, rendered), `tests/test_registry_concurrent_append.py` (new),
`.gitignore` (one line: `jobs/runs.jsonl.lock`).

**What to do.** Section 1.1 in full: the writer half, then the reader half, in two marked
halves of one file; the signatures exactly as listed there, each with its contract
section; the row and field tables of 8.1, 8.2, 8.3, 8.4; the verdicts of 8.5 ported from
`legacy/ops/verdicts.py:16-116`; the render of section 1.5; the "not ported" list is
binding — none of the sampler, `latest.json`, tqdm parsing or the `active/history` ledger
comes across. `constants/path_outputs.yaml` is read lazily so the file imports and its
writer half works before that file exists.

**Acceptance.** A1–A8 of section 3, plus the two `grep` selfcheck lines.
`run.py selfcheck` does not exist yet; do not run it.

**Needs from other folders.** At run time only, for A3 and the reader half:
`constants/path_outputs.yaml` with `root`, `debug_subdir`, `login_host`, `hosts:` (6.3).
A1, A2, A4, A5, A6, A7 need nothing.

### T2 — The launcher: git gate, cards, ports, tmux, start row, refire, teardown

**Files.** `jobs/launch.py` (new).

**What to do.** Section 1.2 in full: the four offered functions with the signatures of
0.2, the five internal helpers pinned there, the launch order of 8.1 inside one
`registry.lock()` hold, the launch gate of 2.5, the placement rule of 3.4, the port rule
and attach test of 7.4, the two service command lines of 7.1 and 7.2, the `check` client
gate, the `(outcome, pieces)` return with the teardown before any outcome but `up`, the
refire of 2.3 with its liveness refusal and its warn-without-quota, and `split_files` of
8.3. Port the algorithms from the legacy lines named in section 1.2 and drop what its
"not ported" list names. No `__main__`.

**Acceptance.** B1–B7 of section 3. Everything that needs a card or another host is
section 4 and is returned as BLOCKED with the ready-to-run command.

**Needs from other folders.** `jobs/registry.py` (T1: `lock`, `open_runs`, `append_start`,
`write_meta`, `free`, `live_sessions`, `session_alive`, `DEFAULTS`);
`experimental_settings/schema.py`: `STAGES`, `load_frozen`, `run_dir_of`;
`data/task_record.py`: `done_pairs`, `is_done`, `owner`, `release`;
`data/environments/__init__.py`: `open_env`, `requested_pairs`, `Environment.tasks`;
`constants/path_datasets.yaml` (`venvs:` map, per-environment `venv` column);
`constants/path_outputs.yaml` (`login_host`, `hosts:`); `models/table.yaml`
(`serving:` block).

### T3 — `run.py`: the walk and the nine subcommands

**Files.** `run.py` (new).

**What to do.** Section 1.3, everything except `selfcheck`: the command line of errata 11,
the walk's eight steps with their contract sections, the gates `run.py` holds (2.5's two
inject gates, the consumed/split-hash gate of 2.3, the `owners` write on a skip), the
CPU-stage path of 2.3 with the pid captured inside the lock (errata 5), the finish-row
writers of 8.2, and the nine subcommands of 8.6 (`ls`, `where`, `find`, `kill`, `refire`,
`retry`, `table`, `free`, `sync`). Register no `selfcheck` subcommand — ticket T4 adds it.
Port the dispatch shape from `legacy/run.py:1270-1305` and `tail_of` from
`legacy/run.py:830-840`; drop everything its "not ported" list names.

**Acceptance.** C1–C4 of section 3, plus the `grep` selfcheck line. C4 needs the settings
and constants folders; if they have not landed, run C1–C3 and say so.

**Needs from other folders.** `jobs/registry.py` (T1) and `jobs/launch.py` (T2);
`experimental_settings/schema.py`: `load`, `load_frozen`, `key`, `run_dir`, `run_dir_of`,
`freeze`, `STAGES`, and the two names errata 8 adds — `upstream(stage, setting)` and
`module_version(path)`; `data/task_record.py`: `done_pairs`, `is_done`, `owner`,
`release`; `data/environments/__init__.py`: `open_env`, `requested_pairs`;
`eval/utils/probe_eval.py`: `read_report`; `eval/method_table.py`: `table`.

### T4 — `README.md` and `run.py selfcheck`

**Files.** `README.md` (new), `run.py` (edit: add the `selfcheck` subcommand and the
parsers `readme_entries`, `imports_of`, `literal_of`).

**What to do.** Section 1.6's four README sections, with section 2 of the README copied
entry for entry from contracts 0.2 in 0.1's exact five-line format (it is what selfcheck
parses), and section 3 from contracts 0.4. Then `selfcheck` as section 1.3 lists it: the
README file list against the tree, every annotation line against an `ast`-parsed import
graph (never by importing), the axis literals against the files behind them, the
`VERSION` and literal-line rules of 3.3, the `DEFAULTS`/`REQUIRED` rule of Part 1, the
`PROBE_KIND` pair, `DEFAULT_EFFORT` in `EFFORTS`, the `models/table.yaml` row checks, the
`/home/`-`/net/` rule, and the per-interpreter import tests. Print one line per problem
and exit 1 on any.

**Acceptance.** D1 and D2 of section 3. D3 (`run.py selfcheck` green over the whole tree)
is the integrator's, after every folder has landed; report it as the outstanding line.

**Needs from other folders.** For the README text: nothing (contracts 0.2 is
authoritative). For a green D3: every folder's files, and specifically
`experimental_settings/schema.py`'s `STAGES` and axis literals,
`agent/inject_format.py`'s `FORMATS`, the `PROBE_KIND` pair in each
`train/methods/<m>.py` and `eval/methods/<m>.py`, `models/table.yaml`,
`constants/path_models.yaml` and `constants/path_datasets.yaml`'s `venvs:` map.

---

## 6. Contract errata settled here

Appended verbatim to `.scratch/from-zero/contract-errata.md`.

1. **8.5** lists four `DEFAULTS` entries while the verdict rules name five more numbers
   inline (5x the typical gap, 20 intervals, 3 intervals, 10 beats, half the average) ->
   `DEFAULTS` also carries `stall_mult: 5.0`, `typical_beats: 20`, `min_intervals: 3`,
   `recent_beats: 10`, `slow_ratio: 0.5` under their legacy names
   (`legacy/ops/verdicts.py:16-27`), so 8.5's "every one of those numbers, in one
   dictionary" stays literally true; `port_fail_rounds` and `sample_interval_s` are
   dropped with the sampler.
2. **8.5** gives `judge(piece)` and `judge_service(piece)` the type `dict` and never lists
   its keys -> the piece dict is
   `{kind, alive, status, done, total, has_beat, beat_ts, beat_age_s, since_launch_s,
   port_ok}`, assembled by `registry.ls`.
3. **8.4** shows one line format for two sinks ("into `heartbeat/<piece>-<launch>.jsonl`
   … as well as to stdout") -> the file holds the bare JSON object per line and stdout
   keeps legacy's `@hb ` prefix (`legacy/ops/heartbeat.py:15,32`).
4. **2.5** puts the card-busy test on `jobs/launch.py` while **8.0/8.6** make
   `registry.free()` report free cards under that same test -> the test lives in
   `jobs/registry.py` (`cards_busy`/`free`, which already probes `nvidia-smi` per its 0.2
   reads line) and `jobs/launch.py` calls `registry.free()` inside its lock hold.
5. **8.1** appends the start row inside the lock while its `cpu` piece entry carries a
   `pid` that exists only after the process starts -> `run.py` spawns the CPU process
   inside the hold, records its pid in the start row, releases the lock, then waits.
6. **3.4**'s piece command carries no redirection while **1.5** requires
   `log/<piece>.txt` -> the tmux inner command ends
   `2>&1 | tee -a <run_dir>/log/<piece>.txt` (`legacy/ops/launch_cmd.py:196-202`),
   appending because the file name carries no launch index.
7. **8.6** refuses to run anywhere but `login_host` but names no comparison rule, while
   this machine answers `shiga` to `hostname` and the `hosts:` list calls it `tokyo105`
   -> both sides are normalized through the `hosts:` entries' `alias` column
   (`legacy/ops/launch_common.py:41`).
8. **5.1** names the loader's functions and none of them hands `run.py` the resolved
   upstream map before `freeze`, which 2.5's two inject gates and 5.4's temperature read
   need -> `experimental_settings/schema.py` also offers
   `upstream(stage, setting) -> dict[str, str]` (the map `freeze` writes into `_upstream`,
   which `freeze` itself calls) and `module_version(repo_relative_path) -> int` (3.3's
   text reader); `run.py` calls both.
9. **8.2** says `run.py` alone writes finish rows while **8.0** gives `sync()` the return
   "the finish rows it wrote" -> `registry.sync()` appends them itself through
   `append_finish`, and it counts as one of run.py's five places because `run.py` is its
   only caller.
10. **8.2** names `RESULTS.md` as rendered from `runs.jsonl` and never fixes its shape ->
    one markdown table, newest run first, one row per `run_id` folded from its newest
    start and newest finish row, columns
    `run_id | started | stage | workflow/setting | commit | status | numbers | report`
    (`legacy/ops/record.py:143-172`), without that file's per-run detail blocks.
11. **0.2** lists `run.py`'s subcommands and never fixes the argv shape of the walk ->
    `run.py <workflow> <setting> [<setting> …] [--debug] [--allow-dirty]
    [section.field=value …]`, with the ten subcommand names reserved and `selfcheck`
    refusing a workflow file whose stem is one of them.
12. **8.1** sources the git fields from `legacy/ops/record.py:58-83` while
    `legacy/ops/runmeta.py:46` writes the full sha -> `commit` is the short sha
    (`git rev-parse --short HEAD`, `record.py:75`).
13. **8.1** names an alive check without defining it -> a `loop`, `train` or `cpu` piece
    passes when its log file grows inside a 30 s window polled every 5 s and its session
    exists with no `Traceback` in the last 4 KB
    (`legacy/ops/launch_cmd.py:220-242`); a `service` piece passes when its
    `service_<kind>_<replica>.json` appears and its port answers, bounded by
    `DEFAULTS["launch_timeout_s"]`.
14. **1.1** gives `done_pairs(dir, pairs)`, `read_dir(dir, pairs)` and
    `release(dir, live_sessions, unowned_age_s)` a `dir` that is never said to be the run
    directory or its `records/` subdirectory -> `jobs/launch.py` and `run.py` pass
    `<run_dir>/records`.
