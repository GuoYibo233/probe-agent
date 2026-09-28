# T12 report — the launcher (`jobs/launch.py`)

Branch: `ticket/2026-09-18-wave4/T12`, base `46f5375253f01e92f94432038ff5e552cd7439cd`,
head `3a484c9`.

## What was done

One file, `jobs/launch.py` (venv `probe`, no entry-point guard, no `VERSION`),
plus its `README.md` entry (Ticket 12 section, appended after Ticket 09's).

Against the ticket's requirements:

- **The five public names** (`PROBE_PORT_BASE`, `launch`, `refire`,
  `teardown_services`, `git_state`) and the **six module-internal, pinned
  names** (`gate_open_row`, `place`, `assign_ports`, `piece_command`,
  `alive_check`, `is_ledger_path`) all exist with exactly the signatures the
  ticket pins.
- **`git_state`** (2.5): probes `git status --porcelain` and `git rev-parse`
  under the repo root, filters ledger paths via `is_ledger_path`, refuses a
  dirty tree without `allow_dirty` (naming the files), writes
  `<run_dir>/dirty.patch` (`git diff HEAD`) exactly when the tree is dirty,
  and is fail-closed (`dirty=True` on any git-probe exception).
- **`is_ledger_path`**: true for `jobs/runs.jsonl`, `jobs/RESULTS.md`, and
  any path ending `.lock`.
- **`gate_open_row`** (2.5, and the reviewer-round-1 "observed dead" errata):
  implements the three-clause disjunction over pieces of `kind != "service"`
  — a live session, a fresh heartbeat (via `registry.stall_line_s`), or a
  start row younger than `launch_timeout_s` while no piece has been
  *observed dead* (not alive and has emitted at least one beat; a `cpu`
  piece via its recorded `pid`).
- **`place`** (3.4): `loop` and a card-less `service_probe` go to
  `login_host`; an agent service always goes to `serving_host`, taking no
  card and no search when `attached`; everything else (a checkpoint-loading
  `service_probe`, `train`) takes the first host with enough free cards,
  preferring `prefer_host`.
- **`assign_ports`** (7.4): agent replica `serving_port + replica`, probe
  `PROBE_PORT_BASE`, both bumped past `taken`.
- **`piece_command`** (3.4, errata): the `cd <repo root> &&
  CUDA_VISIBLE_DEVICES=<ids> <python> -m <module> --run-dir <dir> [--piece
  <i>/<n>] 2>&1 | tee -a <log>` shape, `--piece` only when given.
- **`alive_check`** (errata, 8.1): a `loop`/`train`/`cpu` piece passes on log
  growth + live session + no `Traceback` in the log's last 4 KB inside the
  window; a `service` piece passes on its endpoint file appearing and its
  port answering; returns as soon as everything passes.
- **`teardown_services`** (2.3, wave-4 precheck errata): ends every `kind:
  service` piece via local `tmux kill-session` (no `ssh`) when the host
  normalises to `login_host`, `ssh ... tmux kill-session` otherwise, skipped
  whole when this run's `run_id` appears in another live run's
  `service_*.json` `attached_to`.
- **`refire`** (2.3): refuses fail-closed while `registry.session_alive`
  reports the piece's session alive; warns (never refuses) past one prior
  `launches` entry for the piece; releases unfinished claims through
  `data/trajectory_record.release(run_dir, ...)` (the run directory, not
  `.../records`); re-probes the cards and may relocate a card-taking piece;
  restarts it in a new tmux session under the *same* session name; rewrites
  the piece's `meta.json` entry and appends a `launches` entry in one
  `registry.write_meta` call.
- **`launch`** (8.1, 2.5, 3.4, 7.4, 2.3, 8.3): inside one `registry.lock()`
  hold — reads `registry.open_runs()` scoped to this run's key, runs the
  launch gate, the 7.4 attach test for an agent-service piece, the card
  reservation (`registry.free()`), port assignment, resolves and writes
  `meta.json.split_files` (through `env.tasks`/`requested_pairs`, refusing an
  out-of-split `tasks` id), and appends the `status: "launching"` start row
  and `meta.json`. Releases the lock, then starts pieces in two waves for
  `sample`/`inject` (service pieces + alive check, an `inject` run's
  `service_check` client call, then loop pieces) or the one piece for
  `train`; calls `teardown_services` before returning any outcome but `up`
  and marks the ended sessions in the returned piece list.
- The two service command lines (7.1/7.2, plus errata's `--replica`/
  `--attached-to` and the render-only omission of the four checkpoint/device
  flags).

## How it was verified

Repo root for the acceptance commands is the worktree,
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T12`. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`, as the ticket
requires (this repo's own `external/` is git-ignored and not materialised in
the worktree).

**B1 — imports, no entry-point guard.**
```
8500 True True True True
has main guard: False
```
Matches expected `8500 True True True True` / `has main guard: False`, exit 0.

**B2 — `git_state`'s five fields and the real commit.**
```
['branch', 'commit', 'dirty', 'dirty_count', 'dirty_files']
True
patch written: True
```
Matches, exit 0.

**B3 — the ledger exemption, and the dirty-tree refusal.**
```
kept: ['data/trajectory_record.py', 'README.md']
no ledger file in dirty_files: True
refused: jobs/launch.py: refusing a dirty working tree without --allo
```
Matches; the worktree is dirty (the new `jobs/launch.py` and the edited
`README.md`), so the refusal branch ran, as the ticket says is the normal
case. Ran twice — once before, once after the `README.md` edit — with the
same result both times.

**B4 — the launch gate over fabricated rows.**
```
1 True
2 True
3 True
4 True
5 True
6 True
```
Matches the expected `1 True` through `6 True` exactly, including line 3
against line 2 (the "observed dead" distinction) and line 6 (a live
*service* session alone does not hold the launch gate's clause).

**B5 — placement, ports, the piece command.**
```
shiga
shiga
tokyo107
shiga
8102 8502
cd .../jobs -wt.../T12 && CUDA_VISIBLE_DEVICES= /p/py -m agent.loop --run-dir /o/sample/k --piece 0/6 2>&1 | tee -a /o/sample/k/log/0.txt
```
`shiga` is this repo's configured `login_host`
(`constants/path_outputs.yaml`), so the first two lines (`loop`,
`service_probe` render-only) match "the configured login host"; `tokyo107`
matches the attached agent service's own host with no card search;
`shiga` matches the train piece's preferred host (its one free card);
`8102 8502` matches; the command ends
`-m agent.loop --run-dir /o/sample/k --piece 0/6 2>&1 | tee -a /o/sample/k/log/0.txt`
with `cd <repo root> &&` at its head. Matches, exit 0.

**B6 — `teardown_services` with no service piece.**
```
[]
```
Matches; no `ssh` attempted (the one piece is `kind: loop`, so the function
never reaches the kill branch at all).

**B7 — `refire` refuses a live piece, no `ssh` issued.**
```
refused: True
no ssh issued
```
Matches. The refusal message names the session (`'selfcheck-refire-probe'
in str(e)` is `True`), and the `ssh` shim's marker file was never created —
`registry.session_alive`'s local short-circuit fired because the piece's
recorded host (`$(hostname)`) normalises to the same machine
`jobs/launch.py` itself runs `refire` on.

**B8 — no absolute cluster path, no `VERSION`.**
```
NO_ABS_PATH
NO_VERSION
```
Matches, exit 0.

**README / selfcheck.** `run.py` does not exist yet on this branch (wave 6),
so `run.py selfcheck` was not run, per the spec's section 7 and the ticket's
"Selfcheck lines that apply later" note. `README.md` carries `jobs/launch.py`'s
five-line entry, copied from the ticket's own header block, under a new
"## Ticket 12" section appended after Ticket 09's.

## The commit

- `3a484c9` — `T12: add jobs/launch.py, the launcher` (adds `jobs/launch.py`
  and the `README.md` entry).

## Self-review findings and open questions

- **`launch()`'s piece-construction, service commands, the attach test and
  the split-files resolution are untested by this ticket's own acceptance
  section** — every acceptance command here is a no-GPU, no-tmux pure or
  near-pure check (B1–B8), and the ticket's own "GPU / main session — not
  yours" list (`M-J3`–`M-J8`) is exactly the set of scenarios that would
  exercise `launch()` end to end; I never launched a process on a card or on
  another host, per the repo's hard rule. I implemented `launch()` and the
  service-command builders as carefully as I could against contracts 7.1,
  7.2, 7.4, 3.4, 2.3 and 8.1, but they carry more inference than the tested
  functions do, and a few points are genuinely my own decision rather than
  something the ticket or the contracts state outright:
  - The **start row's `parent`/`swept` fields**: `Setting` (the schema
    dataclass) carries no `_parent`/`_swept` attribute I could find, and
    `launch()`'s signature takes no such parameter either, so I write both
    `None` always. If a sweep child's parent/swept values are meant to reach
    the registry through some other channel, that channel is not visible
    from this file and would need a follow-up ticket or a clarification from
    the contracts.
  - **The 7.4 attach test's match key**: I compare a candidate
    `service_agent_*.json`'s `claims` dict against `setting.models.agent_row`
    key-for-key (`role`, `family`, `weights`, `dtype`, `quantization`,
    `max_model_len`, `served_model_name`, `env_result`, `extra_flags` — the
    exact shape `_model_row` in `experimental_settings/schema.py` builds).
    This is my reading of "claims the same `result:` block"; ticket 07's
    errata entry pins `claims`'s shape for the *service's own* echo file but
    I have not seen ticket 07's actual `service.py` to confirm the field
    names line up exactly.
  - **`refire`'s card relocation** re-derives `cards_needed` from the old
    piece's comma-separated `gpus` string and calls `place()` again with
    `prefer_host` = the old host; this is my interpretation of "probes the
    cards again... and restarts the piece... a refire may relocate a piece"
    (3.4) — the ticket does not spell out the exact re-placement rule for a
    refire the way it does for a first launch.
  - **`refire`'s reconstructed piece command**: since `meta.json`'s piece
    entry does not carry the module name or the `--piece i/n` values as
    separate fields (only the frozen `cmd` string, per 8.1's field list), I
    parse them back out of the stored `cmd` with a regex matched to
    `piece_command`'s own output shape. This works for any piece this file
    itself launched (proven live by B7, whose `cmd` is `"true"`, i.e. a
    non-matching string — B7 never reaches this code path because it exits
    on the liveness refusal first) but would raise if handed a `cmd` from
    outside this file's own shape.
  - **Agent-service `--gpus`/probe-service `--device`**: I pass the raw,
    unmasked card id(s) (no `CUDA_VISIBLE_DEVICES` for a service piece, per
    3.4's "only the two services take cards as flags"), and `--device
    cuda:<id>` for the probe service. The contracts do not pin the exact
    `--device` string format; `cuda:<id>` is the conventional PyTorch
    spelling and my own choice.
- **The service piece's `endpoint_file` distinguishes agent from probe by
  its filename prefix**, not by a separate field on the piece dict — 8.1's
  piece-entry field list has one `kind` value, `"service"`, for both, and I
  did not add a field beyond that list.
- **I added one bookkeeping field, `run_dir`, to the in-memory piece dicts
  `launch()` builds**, used only by `alive_check` (to find a service piece's
  endpoint file) before being stripped by `_strip_runtime()` prior to every
  write to the registry or the return value. It never reaches `meta.json`,
  the start row, or a returned piece dict.
- No acceptance command's output was edited to make it pass; no new test
  file was written (the ticket names no `tests/` seam for this file); no
  `experimental_settings/*.yaml` or `models/table.yaml` edit was made; no
  file outside `jobs/launch.py` and `README.md` was touched.
- **Legacy citations** live only in this report and were not carried into
  the shipped source (spec section 5's rule); the shipped docstrings and
  comments cite contract section numbers and errata, not `legacy/` paths.

## Fix round 1 (findings F1, F2)

Both findings were correct; both are root-cause fixes, not patches, and both
touch only `jobs/launch.py`.

**F1 (critical) — legacy citation in shipped source.** `alive_check`'s
docstring read `(errata against `legacy/ops/launch_cmd.py:220-242`)`, the one
place this file's actual claim in the "self-review" section above ("legacy
citations live only in this report") was false. Spec section 5's hard rule is
categorical: no `legacy/` mention anywhere in the shipped source, because
ticket 18's C9 greps the code directories for the word after `legacy/` is
deleted. Fixed by rewording the parenthetical to cite 8.1's own errata note
instead of the legacy path, matching how every other docstring in this file
already does it (e.g. `git_state`, `piece_command`, `teardown_services`).
`grep -ni legacy jobs/launch.py` now finds nothing.

**F2 (critical) — `--gpus ""` corrupts the attached agent-service argv.**
`launch()`'s `service_agent` branch sets `gpus, port = "", attach["port"]`
when attaching to a live server, and `_agent_service_cmd` unconditionally
built `parts` with `"--gpus", gpus` in it. `' '.join(parts)` on a list
containing an empty string produces a double space, which a real shell (the
one `tmux new-session` hands the whole command string to) collapses under
ordinary word-splitting — the empty token vanishes and `--replica`'s value
takes `--gpus`'s place in the argv, corrupting `--replica`, `--attach-only`
and `--attached-to` for the exact path 7.4's attach mechanism and M-J7 exist
to exercise. Root-cause fix: `_agent_service_cmd` now omits `--gpus` entirely
when `gpus` is falsy (a card-less, attached piece), the same conditional
pattern `_probe_service_cmd` already uses to omit its four checkpoint/device
flags under `--render-only`. `--replica` is now appended unconditionally after
the optional `--gpus` block, so its position in argv no longer depends on
whether `--gpus` was emitted.

### How it was verified

Repo root for these commands is the fix worktree,
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T12-fix1`. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**F2, a direct check of `_agent_service_cmd`'s argv in both branches**
(`shlex.split` over the built command's inner segment, standing in for the
real shell tmux hands the command to):
```
cd .../T12-fix1 && /p/py -m models.agent_models.service serve --run-dir /o/run --model alias --port 8100 --replica 0 --attach-only --attached-to train-k1 2>&1 | tee -a /o/run/log/0.txt
['/p/py', '-m', 'models.agent_models.service', 'serve', '--run-dir', '/o/run', '--model', 'alias', '--port', '8100', '--replica', '0', '--attach-only', '--attached-to', 'train-k1']
OK attached case
['/p/py', '-m', 'models.agent_models.service', 'serve', '--run-dir', '/o/run', '--model', 'alias', '--port', '8100', '--gpus', '0,1', '--replica', '1']
OK non-attached case
```
Attached case: `--gpus` is absent and `--replica`/`--attach-only`/
`--attached-to` all carry their correct values, in argv, after shell-style
splitting. Non-attached case: `--gpus 0,1` is present and unchanged, showing
the fix does not touch the card-taking path.

**F1, confirming no legacy citation remains:**
```
$ grep -ni legacy jobs/launch.py
(no output, exit 1)
```

**The ticket's own B1-B8 acceptance commands, rerun verbatim against the
fixed file** (same interpreter and repo root as above), to confirm the fix
changed nothing else:

B1:
```
8500 True True True True
has main guard: False
```
B2:
```
['branch', 'commit', 'dirty', 'dirty_count', 'dirty_files']
True
patch written: True
```
B3:
```
kept: ['data/trajectory_record.py', 'README.md']
no ledger file in dirty_files: True
refused: jobs/launch.py: refusing a dirty working tree without --allo
```
B4:
```
1 True
2 True
3 True
4 True
5 True
6 True
```
B5:
```
shiga
shiga
tokyo107
shiga
8102 8502
cd .../T12-fix1 && CUDA_VISIBLE_DEVICES= /p/py -m agent.loop --run-dir /o/sample/k --piece 0/6 2>&1 | tee -a /o/sample/k/log/0.txt
```
B6:
```
[]
```
B7:
```
refused: True
no ssh issued
```
B8:
```
NO_ABS_PATH
NO_VERSION
```
All eight match the ticket's expected output exactly, and `git status
--porcelain` after B3/B6/B7 showed only `jobs/launch.py` modified (their
temp-directory writes went to `mktemp -d` paths outside the repo, not into
the ledger or repo root).

`python3 -m py_compile jobs/launch.py` — `COMPILE_OK`.

### Commit

- `0c4063d` — `T12: fix round 1 - drop legacy citation, stop --gpus
  corrupting attached agent-service argv` (both fixes, one file).

### Open questions

None. Both findings were narrow, root-cause fixable within the existing
function shapes, and fully covered by the ticket's own acceptance suite plus
a targeted argv check for the one code path (`_agent_service_cmd`'s attached
branch) that B1-B8 do not otherwise exercise, per the original report's
self-review note that `launch()`'s service-command builders are untested by
the ticket's own no-GPU acceptance section.

## Post-merge fix round 1

Branch `ticket/2026-09-18-wave4/T12-postfix`, worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T12-postfix1`, base `e8b257d`
(the branch `from-zero` tip after the wave-4 post-merge review commit),
commit `3661305`. Three findings from
`.scratch/from-zero/sdd/2026-09-18-wave4/post-merge-review.json`'s `launch`
scope, all against `jobs/launch.py` and all fixed root-cause: the wrong
logic is replaced, nothing is patched around.

### LAUNCH-1 (critical) — the attached agent-service command line omitted `--gpus`

`_agent_service_cmd` wrote `--gpus` only `if gpus:`, and `launch()`'s
attached branch sets `gpus = ""`, so an attached replica's command line
carried no `--gpus` at all. The merged `models/agent_models/service.py`
declares `srv.add_argument("--gpus", required=True)`, so that argv died at
`argparse` with exit code 2 before `serve()` ever ran, and contract 7.1 pins
`--port <n> --gpus <ids> [--attach-only]` with `--gpus` **outside** the
brackets — unbracketed on every serve line, attached or not. The flag was
dropped by this ticket's own fix round 1 (commit `0c4063d`), which was
fixing a different bug: an unquoted empty value being swallowed whole by
`' '.join`, corrupting `--replica`'s position in argv.

Root-cause fix: `_agent_service_cmd` now puts `--gpus` on the command line
unconditionally, with its value passed through `shlex.quote`. An empty
string quotes to `''`, a real, non-vanishing shell token, so an attached
piece's argv carries `--gpus ''` and every flag after it keeps its
position; a serving piece's `--gpus 0,1` is unaffected (`shlex.quote`
leaves a comma-and-digit string unchanged).

**Verification** (repo root is the worktree, `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`, per the ticket
and the dispatch's absolute-interpreter rule; nothing was started on a
card, and `service.serve`/`service.serve` were stubbed so the parser ran
with no real vLLM process behind it):

Agent service, attached and serving, parsed by
`models.agent_models.service.main` itself:
```
ATTACHED CMD: cd .../T12-postfix1 && /PY -m models.agent_models.service serve --run-dir /run/dir --model alias --port 8103 --gpus '' --replica 0 --attach-only --attached-to sample-abc 2>&1 | tee -a /l.txt
attached rc= 0 gpus= '' attach_only= True
SERVING CMD: cd .../T12-postfix1 && /PY -m models.agent_models.service serve --run-dir /run/dir --model alias --port 8100 --gpus 0,1 --replica 1 2>&1 | tee -a /l.txt
serving rc= 0 gpus= '0,1' attach_only= False
OK: both agent-service argvs parsed cleanly
```
Both commands were split with `shlex.split` on the segment after
`-m models.agent_models.service`, fed to `service.main(argv)` with
`service.serve` monkeypatched to record `args` instead of running, and both
parsed with exit 0, `gpus` and `attach_only` exactly as expected.

The finding also asked for the same parse check on the probe service line
(serving and `--render-only`), against `models/probe_models/service.py`'s
own parser, the same way:
```
SERVING CMD: cd .../T12-postfix1 && /PY -m models.probe_models.service serve --run-dir /run/dir --agent-model alias --port 8500 --score-ckpt /x --gen-ckpt /y --temperature 0.7 --device cuda:0 2>&1 | tee -a /l.txt
serving rc= 0 render_only= False score_ckpt= /x device= cuda:0
RENDER-ONLY CMD: cd .../T12-postfix1 && /PY -m models.probe_models.service serve --run-dir /run/dir --agent-model alias --port 8500 --render-only 2>&1 | tee -a /l.txt
render-only rc= 0 render_only= True score_ckpt= None device= None
OK: both probe-service argvs parsed cleanly
```
`_probe_service_cmd` was untouched (its four checkpoint/device flags are
correctly bracketed under `--render-only` per 7.2, and `--device` is
optional on the service's own parser, not required like the agent
service's `--gpus`), and both its shapes parse cleanly; no fix was needed
there.

### LAUNCH-3 (important) — `_piece_alive` was not fail-closed

`_piece_alive` was a bare `bool(session) and session in live_sessions`,
ignoring `failed_hosts`, the field `registry.live_sessions()`'s
`_ProbedSessions` carries for a host whose `tmux ls` probe never answered.
`jobs/registry._alive_on` already implements 3.4/8.0's fail-closed rule — a
piece on a failed host is alive — and both of `_piece_alive`'s callers
(`gate_open_row`'s clauses (a) and (c), and `alive_check`'s liveness test)
lost that rule entirely, so an unreachable host could open the launch gate
over a live run (the exact collision 9(c)#9/M-J8 exist to prevent) or make
`alive_check` tear down a run that had actually come up.

Root-cause fix: `_piece_alive` now checks the piece's host against
`live_sessions`'s `failed_hosts` first (read via `getattr` so a plain set,
which the ticket's B4 passes, simply has none and behaves exactly as
before), with the host canonicalised through this file's own
`_canonical_host` first — the same normalisation every other host
comparison in `jobs/launch.py` already applies — so a loop or render-only
piece recorded under the login machine's alias still matches a canonical
`hosts:` entry in `failed_hosts`.

**Verification** ($PR as above), reproducing the finding's own evidence
shape and confirming the fix:
```
registry._alive_on: True
launch._piece_alive: True
gate_open_row over a live piece on a failed host: refusing to launch 'k1': live session 'train-k1-0' on host 'tokyo106'
plain set, no failed_hosts -> _piece_alive: False
alias host canonicalised -> True
```
`launch._piece_alive` now agrees with `registry._alive_on` (`True`, not the
finding's reported `False`), `gate_open_row` now refuses the launch instead
of admitting it, a plain set (no `failed_hosts` attribute) still behaves as
before (`False` when the session is absent), and a piece recorded under an
alias (`shiga`) is still caught when `failed_hosts` names the canonical
host (`tokyo105`). B4's own six lines (rerun below) are unaffected because
every set B4 passes is a plain `set`/`{...}` literal with no `failed_hosts`
attribute.

### LAUNCH-4 (important) — `launch()` wrote no `meta.json` `launches` entry

The one `registry.write_meta` call inside `launch()`'s lock hold passed no
`launches`, so the initial launch of every run left that list empty;
`refire` was the only writer, so its "more than one entry" warning
(`jobs/launch.py`'s `prior` count) fired one refire late.

Root-cause fix: a new shared builder, `_launch_entry(git, *, host, cards,
pieces, cmd) -> dict`, returns contract 8.3's nine-field shape (`t, host,
commit, branch, dirty_count, dirty_files, cards, pieces, cmd`) from the
`git` dict a caller was handed. `refire` was rewritten to call it instead
of building its dict inline (same values, same shape, no behaviour
change there: `host=new_host`, `cards=new_gpus`, `pieces=[piece]`,
`cmd=new_cmd`, exactly as before). `launch()` now calls the same builder
once, inside the same lock hold and the same `write_meta` call that already
writes the start row's `pieces`, `versions`, `upstream` and `diff`: `host`
is `_login_host()` (8.1's own field carries the same meaning — "the login
machine that launched" — for the start row written in the same call), and
`cards`/`cmd` are `{piece index: value}` maps over every piece this launch
placed, generalising refire's single-piece string to the multi-piece,
multi-host case a first launch is. This is an implementer decision beyond
what the ticket or contracts pin exactly (8.3 names the four fields but not
their shape for a many-piece launch); a single string per launch was not
usable across pieces sharing no one host and no one card, so a per-piece
map was the smallest change that keeps refire's shape as a one-entry case
of it.

**Verification** ($PR as above), an end-to-end `launch()` of the real
setting `experimental_settings/baseline.yaml`'s `gpt_oss_120b_appworld`
(workflow `[sample, score]`, stage `sample`) under `--debug`, in a
`mktemp -d` run directory, with `registry.lock/open_runs/live_sessions/
free/write_meta/append_start`, `launch._on_login_host`, `launch._start_tmux`
and `launch.alive_check` stubbed in-process (no ssh, no tmux, no card
probe, no ledger write — `registry.write_meta` and `registry.append_start`
were captured into local lists rather than touching this worktree's own
`jobs/runs.jsonl`/`meta.json`):
```
outcome: up
n pieces returned: 3
write_meta calls: 1
write_meta kwargs (sorted): ['debug', 'diff', 'dir', 'key', 'launches', 'pieces', 'split_files', 'stage', 'upstream', 'versions']
launches after launch(): True 1
entry fields (sorted): ['branch', 'cards', 'cmd', 'commit', 'dirty_count', 'dirty_files', 'host', 'pieces', 't']
field set matches contract 8.3: True
entry host: shiga
entry pieces (indices): [0, 1, 2]
entry cards: {0: '', 1: '0', 2: ''}
append_start calls: 1
start row pieces count: 3
```
`meta.json`'s `launches` holds exactly one entry with the nine 8.3 fields
after `launch()`. A `refire` was then run against a real `meta.json`
written to the same scratch directory (this part used the real
`registry.write_meta`, only `registry.session_alive`/`live_sessions`/`free`,
`launch._start_tmux` and `data.trajectory_record.release` stubbed, so the
actual append-and-merge logic of `write_meta` ran):
```
launches after refire: 2
  entry 0 fields: ['branch', 'cards', 'cmd', 'commit', 'dirty_count', 'dirty_files', 'host', 'pieces', 't']
  entry 1 fields: ['branch', 'cards', 'cmd', 'commit', 'dirty_count', 'dirty_files', 'host', 'pieces', 't']
```
Two entries, both nine-field, after one refire — matching the finding's own
acceptance ask exactly.

The same run's built piece commands were inspected directly (not started)
to confirm LAUNCH-1's fix holds on the real, non-attached path a `sample`
launch takes when no live server is already up:
```
loop    | cd .../T12-postfix1 && CUDA_VISIBLE_DEVICES= .../external/appworld/venv/bin/python -m agent.loop --run-dir <rd> --piece 0/1 2>&1 | tee -a <rd>/log/0.txt
service | cd .../T12-postfix1 && .../external/vllm-env/bin/python -m models.agent_models.service serve --run-dir <rd> --model gpt_oss_120b --port 8104 --gpus 0 --replica 0 2>&1 | tee -a <rd>/log/1.txt
service | cd .../T12-postfix1 && .../external/probe-env/bin/python -m models.probe_models.service serve --run-dir <rd> --agent-model gpt_oss_120b --port 8500 --render-only 2>&1 | tee -a <rd>/log/2.txt
```

### The ticket's own B1-B8, rerun against the fixed file

Same worktree, same `$PR`. All eight match the ticket's expected output
exactly:

B1:
```
8500 True True True True
has main guard: False
```
B2:
```
['branch', 'commit', 'dirty', 'dirty_count', 'dirty_files']
True
patch written: True
```
B3:
```
kept: ['data/trajectory_record.py', 'README.md']
no ledger file in dirty_files: True
refused: jobs/launch.py: refusing a dirty working tree without --allo
```
B4:
```
1 True
2 True
3 True
4 True
5 True
6 True
```
B5:
```
shiga
shiga
tokyo107
shiga
8102 8502
cd .../T12-postfix1 && CUDA_VISIBLE_DEVICES= /p/py -m agent.loop --run-dir /o/sample/k --piece 0/6 2>&1 | tee -a /o/sample/k/log/0.txt
```
B6:
```
[]
```
B7:
```
refused: True
no ssh issued
```
B8:
```
NO_ABS_PATH
NO_VERSION
```

`python3 -m py_compile jobs/launch.py` (via `$PR`) — `COMPILE_OK`. B3, B6
and B7 each ran in their own `mktemp -d` directory, as the ticket's wave-4
precheck correction and this dispatch both require; `git status --porcelain`
after the full B1-B8 run showed only `jobs/launch.py` modified (all
temp-directory writes and the end-to-end launch()/refire() test above went
to `mktemp -d` paths outside the repo, never into this worktree's own
`jobs/runs.jsonl`, `jobs/RESULTS.md` or `meta.json`).

### Self-review

- Every change is root-cause: the wrong logic (`if gpus:`, a bare session
  test, a `write_meta` call with no `launches`) is replaced outright, not
  wrapped in a special case. No condition was written as a negation of
  another condition.
- `grep -ni legacy jobs/launch.py`, `grep -n "/home/\|/net/" jobs/launch.py`
  and `grep -c '^VERSION' jobs/launch.py` were rerun after the fix: no
  legacy citation, no absolute path, no `VERSION` line.
- Only `jobs/launch.py` was touched; `README.md`'s existing `jobs/launch.py`
  entry already states both fixed behaviours (`--gpus <ids>` is implied by
  7.1 and was never spelled out as conditional in the README, and `writes:`
  already named "meta.json launch entries" before this fix made it true),
  so no README line was wrong and none was changed.
- `refire`'s own tested behaviour (B7's refusal path) is unchanged; its
  successful path was refactored to call the new shared builder with the
  exact same argument values it built inline before, so its output shape
  for a one-piece refire is unchanged (a single-key `{index: value}` map
  where the old code wrote a bare string is the one visible difference,
  and no code in this file — or, so far as `.scratch/from-zero` records,
  anywhere on this branch — reads `launches` back).
- Two minor findings from the same review round (LAUNCH-6, LAUNCH-7,
  LAUNCH-8, LAUNCH-9 and the `seams` scope's SEAMS-4 through SEAMS-7) were
  left alone: they were not in this dispatch's "Open findings" list, and
  fixing them was not asked for.

### Commit

- `3661305` — `T12: post-merge fix round 1 - always pass --gpus,
  fail-closed piece liveness, meta.json launches entry` (all three fixes,
  one file) on branch `ticket/2026-09-18-wave4/T12-postfix`, base `e8b257d`.

### Open questions

None. All three findings were fixable at their root within the existing
function shapes; the one implementer decision without a pinned answer
(the `cards`/`cmd` shape for a many-piece launch's `launches` entry) is
recorded above for the owner.
