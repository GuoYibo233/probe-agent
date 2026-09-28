# T14 report — run.py: the walk and the nine subcommands, and README.md

Branch `ticket/2026-09-18-wave5/T14`, base `f520b875a97234ca43eb241ca3bb8ec49c3a497e`,
head `089596a624af596d0f49a0f4ec60ed0c834c3b58`. Worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave5-T14`, removed at the end of this ticket per the
worktree protocol; the branch is kept.

## What was done

Two files, as the ticket names: `run.py` (new) and `README.md` (rewritten whole, replacing the
per-ticket placeholder sections with the assembled tree).

**`run.py`**

- The command line (section 1): `run.py <workflow> <setting> [<setting> ...] [--debug]
  [--allow-dirty] [section.field=value ...]`, plus the nine reserved subcommands' own shapes.
  `section.field=value` tokens are told apart from a sweep child's own name (which also carries
  `=`, always after a `/`) by requiring the left-hand side to hold no `/` and at least one `.`
  (`_is_override_token`); the right-hand side is passed to `schema.load` as raw text, which
  parses it with `yaml.safe_load` itself (5.7 step 5) — `run.py` does not parse it a second time.
- `--help` (and a bare `run.py`) print one usage line (the walk form) plus the ten subcommand
  names, each on its own line, indented by exactly two spaces with the name first, per section
  1's pinned layout. Verified against ticket 16/17's own regex,
  `^\s{2,}([a-z][a-z0-9_-]*)`, which recovers exactly the ten names on lines 7-16 of the
  `--help` block (see C1 below) — nothing else, because the walk-form usage line itself is not
  indented and carries no other match.
- The ten reserved names are declared in `RESERVED_SUBCOMMANDS`, any other first word is a
  workflow file's stem; a missing workflow file is refused, naming the `.yaml` path.
- `normalize_host(name, hosts)` and `require_login_host(current, hosts, login_host)` are
  module-level functions, called once at the top of `main()`, before argv is even parsed —
  `run.py` refuses to run on any host but `login_host` (8.6), whatever subcommand was asked for.
- The walk (`cmd_walk` / `_walk_one` / `_stage_step`), covering all eight numbered steps of the
  ticket's section 2:
  1. `key`/`run_dir` computed with `schema.key`/`schema.run_dir`.
  2. The skip test: the pair check (`trajectory_record.done_pairs` against the requested list,
     built with `data.environments.requested_pairs` and projected to `(task_id, seed)`) for
     `sample`/`inject`; `done.json` presence for every other stage.
  3. Before a skip: `_refuse_on_stale_inputs` compares `consumed.json` entries (and, for
     `sample`/`inject`, `meta.json`'s `split_files` entries) against the files they name by
     sha1, refusing and naming both hashes on a mismatch; on a skip, `_record_owner` adds
     `{workflow, setting}` to `meta.json`'s `owners`, under `registry.lock()`.
  4. A partly-done `sample`/`inject` directory: `_piece_alive` (a small local duplicate of
     `jobs.launch._piece_alive`'s fail-closed rule, since that name is private to `jobs/launch.py`)
     decides whether any `loop`/`train` piece is live; while one is, `trajectory_record.release`
     runs, is reported, and nothing launches; once none is, the walk falls through to launch.
  5. Completeness reached (first time `done.json` doesn't yet exist for a now-fully-done
     `sample`/`inject` directory): `_finalize_pair_stage` writes `done.json` through
     `registry.write_done`, calls `launch.teardown_services`, and appends the `ok` finish row.
  6. Launch: `_refuse_missing_upstream` refuses when any upstream (from `schema.upstream`) has
     no `done.json`, for every stage; for `inject`, `_check_inject_probe_methods` (the
     `key:`/`dir:` `method:` sibling against the referenced train run's frozen `probe.method`,
     errata "5.4 / 2.1"), `_check_inject_shared_build_key` and `_check_inject_code_currency`
     (2.5's two `run.py`-held gates) run, and `_resolve_inject_temperature` reads the referenced
     classifier report to fill `resolved["probe_temperature"]`.
  7. Inside one `registry.lock()` hold: `launch.git_state`, `schema.freeze`, `versions_of` /
     `upstream` / `fields_of`, `registry.write_meta`; then a card stage calls `launch.launch`
     (outcome `up` prints the monitor command and stops the walk; anything else appends
     `launch_failed`); a CPU stage's own helper, `_start_cpu_stage`, applies
     `launch.gate_open_row` over `registry.open_runs()` (mirroring the card-stage gate, since a
     CPU stage never goes through `jobs/launch.py`), then spawns the process, captures its pid,
     and appends the start row — matching the errata's ordering (pid captured before the row is
     appended, inside the same hold, lock released only afterward, then `proc.wait()`).
  8. A `done.json` with no finish row yet gets one on the first walk that sees it
     (`_backfill_finish_row`, gated on the run_id being open per `registry.open_runs()`).
- The nine subcommands (section 3): `ls` (computes `edited` via `_compute_edited`/
  `_current_key` and `progress` via `_compute_progress`, both fed from `registry.find({})`'s
  full row set, then calls `registry.ls` once), `where` (`schema.run_dir`, `--debug` taken from
  the loaded setting per errata's own C4 usage), `find` (parses `section.field=value` with
  `yaml.safe_load` and calls `registry.find`), `kill` (`registry.kill` plus a `killed` finish
  row, only when the run_id is currently open), `refire` (re-freezes `_commit` with the
  *existing* `_resolved` block reused rather than erased, then `launch.refire`), `retry`
  (`_clear_continue_markers` deletes `done.json`/`consumed.json` always, plus `train`'s
  `last/`/`train_log.jsonl`/`train_done.json`/`align_check.json` when the stage is `train`, then
  calls `_stage_step` once), `table` (`eval.method_table.table`, with `--debug` wired through
  per errata "8.6 / 8.1"), `free` (`registry.free`), `sync` (`registry.sync`).
- `selfcheck` raises `SystemExit("selfcheck arrives in ticket 15")`, verbatim as the ticket
  pins.
- `readme_entries(path)` parses `README.md`'s `path — sentence` header lines and their
  two-space-indented label lines into `path -> {label: value}`; ticket 15's `selfcheck` reuses
  it, `where`/`ls` sit beside it in the file as the ticket asks.
- No `/home/` or `/net/` literal anywhere in the file (D3); no `VERSION` line (run.py's tree
  line carries none); the module docstring's first sentence is copied verbatim onto its
  `README.md` line.

**`README.md`** — four sections, in the order section 4 of the ticket names:

1. What this repo is and how to run it: the seven principles in one-line form, the command
   shapes, the `--debug` line, the outputs-root/`where` rule, the `login_host` refusal.
2. The tree, one entry per file, in contracts 0.1's exact five-line format (`path — sentence.`
   then `imports:`/`used by:`/`reads:`/`writes:`/`venv:`, each on its own line, flush left with
   the full relative path as the header) — a deliberate departure from contracts 0.2's own
   nested tree-drawing indentation, which 0.1's own example already shows as flush-left paths;
   flush-left, single-line labels are what makes `readme_entries` a five-line regex parser
   instead of a tree walker, and they are what 0.1 itself pins. All 31 Python files (27 already
   on disk in this worktree, plus the four `train/*.py` files ticket 13 is landing in this same
   wave — their entries are contracts 0.2's text, with the one correction the errata names,
   `train/utils/trainer.py`'s third-party import list dropping `peft`), plus the non-Python
   entries the ticket names (`constants/*.yaml`, `experimental_settings/*.yaml`,
   `models/table.yaml`, `jobs/runs.jsonl`, `jobs/RESULTS.md`, `tests/`) and `CLAUDE.md`, which
   contracts 0.2's own tree carries too ("the only other file at the root that is not code") —
   see the open question below on that one addition.
3. The extension recipes, one bullet per contracts 0.4 scenario (seven, the two "new field on
   the task record" sub-cases folded into one bullet per the ticket's own count) plus the two
   non-extension rows (the cut rule, renaming an axis value), each stating what is touched, in
   order, and what it costs — the fourth-probe-method recipe is written against the *built*
   tree (one `eval/utils/probe_eval.py` edit, `match_<m>` plus two table entries), not against
   contracts 0.4's stale `eval/methods/<m>.py (new)` row, per the "0.2 / 2.1 / 2.6" errata
   ruling.
4. The ledgers: `jobs/runs.jsonl` append-only, `jobs/RESULTS.md` rendered, `notes/` the owner's.

For every earlier ticket's file, the substance (imports/used by/reads/writes/venv) is that
ticket's own already-landed text, reformatted only — each of those was already reconciled
against the errata by its own implementer (the wave-5 precheck's point 1 says as much for the
`eval/methods/` fold and the `agent/` renames, and I checked a sample of the others — `data/`,
`models/`, `jobs/registry.py`, `jobs/launch.py` — against the real files' docstrings and
top-level imports and found them accurate).

## How it was verified

All commands run from the worktree root with
`/home/y-guo/reproduce/new1/external/probe-env/bin/python` (`$PR`), per the ticket's `$PR`
definition. Every one below is the exact acceptance command, with its real output pasted.

**C1 — usage and the reserved names.**
```
$ "$PR" run.py; echo "rc=$?"
usage: run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]

The first word is one of the ten reserved subcommands below, or else the stem of a
workflow file under experimental_settings/.

subcommands:
  ls          [workflow] [--debug] -- one folded line per run
  where       <workflow> <setting> <stage> [--debug] -- the absolute run directory for one stage
  find        section.field=value ... -- the runs whose settings_diff matches every given field
  kill        <workflow> <setting> <stage> -- end one run's pieces, write the killed finish row
  refire      <workflow> <setting> <stage> [--piece i] [--allow-dirty] -- restart one dead piece
  retry       <workflow> <setting> <stage> [--allow-dirty] -- clear markers, then launch it fresh
  table       [workflow] [--out FILE] [--debug] -- the backbone x method x risk table
  free        -- the free cards per host
  sync        -- fold done.json and heartbeats into missing finish rows
  selfcheck   -- the tree's self-consistency checks
rc=0

$ "$PR" run.py nosuchworkflow x 2>&1 | tail -1
run.py: /home/y-guo/reproduce/new1-wt/2026-09-18-wave5-T14/experimental_settings/nosuchworkflow.yaml does not exist
```
Exit code of the second command was 1 (checked separately: `rc=1`). Ticket 16's `C8` and ticket
17's `C8` regex, run against the block above: `re.findall(r"^\s{2,}([a-z][a-z0-9_-]*)", txt,
re.M)` returns exactly `['ls', 'where', 'find', 'kill', 'refire', 'retry', 'table', 'free',
'sync', 'selfcheck']`, 10 names, on lines 7-16 of the printed block (counting the blank line
after "usage:" as line 2).

**C2 — the host normalization and the login-host refusal.**
```
$ "$PR" -c "
import sys; sys.path.insert(0,'.')
import run
hosts = [{'name':'tokyo105','alias':'shiga','cards':8},{'name':'tokyo106','cards':10}]
print(run.normalize_host('shiga', hosts), run.normalize_host('tokyo106', hosts))
try:
    run.require_login_host('tokyo999', hosts, 'tokyo105')
    print('NO REFUSAL')
except SystemExit as e:
    print('refused:', 'tokyo999' in str(e) and 'tokyo105' in str(e))"
tokyo105 tokyo106
refused: True
```
Exit code 0.

**C3 — the read-only subcommands against the live (empty) registry.**
```
$ "$PR" run.py ls; echo "rc=$?"
run.py ls: no runs
rc=0
$ "$PR" run.py ls --debug; echo "rc=$?"
run.py ls: no runs
rc=0
$ "$PR" run.py find stage=sample; echo "rc=$?"
run.py find: no runs match
rc=0
$ "$PR" run.py table; echo "rc=$?"
# eval matrix: backbone x method x risk

| backbone | method | risk | n | coverage | trig_acc | earliness | wrong_spec | tool_ok | params_all_ok | full_call_ok | runs | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
rc=0
$ git status --porcelain jobs/
(empty)
```
No `ssh` was issued: the ledger (`jobs/runs.jsonl`) is empty in this worktree, so
`registry.ls`'s own guard (ticket 03, errata "8.6 (ls and the host probe)") never calls
`live_sessions()`; `registry.find` and `eval.method_table.table` over an empty ledger never
probe a host either. Confirmed by the commands returning immediately with no delay and no
`ssh`/`Permission denied`/timeout text anywhere in the output.

**C4 — `where` answers for every keyable stage, real and debug.**
```
$ set -e
$ for a in "baseline gpt_oss_120b_appworld sample" "baseline gpt_oss_120b_appworld score" \
           "train_probe ctool_qwen3_0pt6b sample" "train_probe ctool_qwen3_0pt6b build"; do
    "$PR" run.py where $a
    "$PR" run.py where $a --debug
  done
  echo "C4 ok"
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/sample/a7d8b62ee953
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/sample/96de225de2b4
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/87858c091092
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/score/20eaad1deae5
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/sample/a7d8b62ee953
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/sample/96de225de2b4
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/build/6d3bf5aff879
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/build/b565f5ab1b94
C4 ok
```
Exit 0. Eight absolute paths of the pinned shape, `sample`'s two real/debug pairs repeating
identically across `baseline`/`train_probe` as expected (both settings' `sample` sections are
identical, per each file's `common:` block).

**C5 — key purity against a private copy of the tree.** The read-only hook refuses `cp -a`
against `experimental_settings`, so the private copy is built with `git archive` from a commit
(per the wave-5 precheck's point 3); I committed the worktree's `run.py`/`README.md` first
(commit `1f60634`, superseded by the later commits below) so `git archive HEAD` had them.
```
$ set +e
$ T5=$(mktemp -d)
$ git archive HEAD run.py constants experimental_settings data models agent eval jobs | tar -x -C "$T5"
$ "$PR" -c "
import yaml, pathlib
p = pathlib.Path('$T5/constants/path_outputs.yaml')
d = yaml.safe_load(p.read_text()); d['root'] = '$T5/no_such_outputs_root'
p.write_text(yaml.safe_dump(d))"
$ A=$("$PR" run.py where baseline gpt_oss_120b_appworld sample)
$ B=$(cd "$T5" && "$PR" run.py where baseline gpt_oss_120b_appworld sample)
$ echo "repo root: $A"
repo root: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/sample/a7d8b62ee953
$ echo "temp root: $B"
temp root: /tmp/tmp.XxBC1OcQfn/no_such_outputs_root/sample/a7d8b62ee953
$ test ! -e "$T5/no_such_outputs_root" && echo "outputs root still absent"
outputs root still absent
$ test "$(basename "$A")" = "$(basename "$B")" && echo "C5 ok"
C5 ok
$ rm -rf "$T5"
```
Two different prefixes, same 12-hex last segment (`a7d8b62ee953`); the temp outputs root was
never created; exit 0.

**C6 — `baseline.yaml` and `train_probe`'s `sample`/`build` load, key and freeze under
`--debug` and without it.**
```
$ "$PR" - <<'PY'
import pathlib, yaml
from experimental_settings import schema
CASES = [("baseline.yaml", None), ("train_probe.yaml", ["sample", "build"])]
for f, only in CASES:
    p = pathlib.Path("experimental_settings") / f
    doc = yaml.safe_load(p.read_text())
    stages = doc["workflow"] if only is None else only
    names = [k for k in doc if k not in ("workflow", "common")]
    for name in names:
        for dbg in (False, True):
            for cfg in schema.load(p, name, debug=dbg, overrides={}):
                keys = {s: schema.key(s, cfg) for s in stages}
                dirs = {s: schema.run_dir(s, cfg) for s in stages}
                assert cfg._workflow == doc["workflow"], (f, name, cfg._workflow)
                for s in stages:
                    assert len(keys[s]) == 12, (f, name, s, keys[s])
                    assert dirs[s].name == keys[s], (f, name, s)
                    assert ("/debug/" in str(dirs[s])) == dbg, (f, name, s, dbg)
                print(f, name, "debug" if dbg else "real",
                      " ".join(f"{s}={keys[s]}" for s in stages))
print("C6 ok")
PY
baseline.yaml gpt_oss_120b_appworld real sample=a7d8b62ee953 score=87858c091092
baseline.yaml gpt_oss_120b_appworld debug sample=96de225de2b4 score=20eaad1deae5
train_probe.yaml ctool_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879
train_probe.yaml ctool_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94
train_probe.yaml cgen_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879
train_probe.yaml cgen_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94
train_probe.yaml cparam_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879
train_probe.yaml cparam_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94
C6 ok
```
Exit 0. This command exercises `experimental_settings/schema.py` directly, not `run.py`, and
was already true before this ticket; run here to confirm it still holds and to produce the
`baseline` sample key (`a7d8b62ee953`) and `build` key (`6d3bf5aff879`) C4/C5 above reuse.

**D1 — every README entry parses into the five annotations.**
```
$ "$PR" -c "
import sys; sys.path.insert(0,'.')
import run
ent = run.readme_entries('README.md')
py = [p for p in ent if p.endswith('.py')]
print(len(py), all(set(ent[p]) >= {'imports','used by','reads','venv'} for p in py))"
31 True
```
Exit 0.

**D2 — the file count on disk, and the README covering every file that exists.**
```
$ find run.py constants experimental_settings data models agent eval jobs \
       -name '*.py' | wc -l
27
$ find run.py constants experimental_settings data models agent eval jobs \
       -name '*.py' | while read -r f; do grep -qF "$f" README.md || echo "MISSING $f"; done
(no output)
```
27, no `MISSING` line.

**D3 — no absolute cluster path in `run.py`.**
```
$ grep -n "/home/\|/net/" run.py || echo NO_ABS_PATH
NO_ABS_PATH
```

**Extra checks not in the ticket's Acceptance list, run for my own confidence:**
- `"$PR" run.py selfcheck; echo "rc=$?"` → `selfcheck arrives in ticket 15` / `rc=1`, matching
  the ticket's pinned placeholder verbatim.
- `"$PR" tests/test_registry_concurrent_append.py` → `OK` (`Ran 1 test in 0.211s`), confirming
  the shared registry module still works after the walk was wired up against it.
- `python3 run.py selfcheck` (system interpreter, not `$PR`) fails at import
  (`ModuleNotFoundError: No module named 'polars'`, raised inside `data/__init__.py`, which
  `run.py` imports through `data.trajectory_record`). This is expected and not a defect:
  `run.py`'s own tree line gives it `venv: probe`, not `venv: any`, so it is never required to
  import under system `python3` (spec section 4's `any` rule is scoped to the three venvs of
  the `venvs:` map, which does not include system `python3`).
- `git status --porcelain jobs/` stayed empty across every acceptance run above, and
  `git status --porcelain` at the end of the session shows only the ticket's own three commits,
  a clean tree.

## The commit list

- `1f60634` — `T14: WIP run.py for C5's private-copy test`. The first working draft, committed
  early so C5's `git archive HEAD` had a `run.py` to copy.
- `d2f519a` — `T14: assemble README.md from contracts 0.2/0.4, reconciled with the errata`.
- `089596a` (head) — `T14: finish run.py's walk, subcommands and self-review fixes`. Folds the
  self-review fix (computing `schema.upstream(stage, cfg)` once and reusing it, instead of
  twice) and the docstring/README sentence match into the working draft.

## Self-review findings and decisions the ticket did not make

Every one of these is a place the ticket's prose leaves a real choice; I made the call, and
each is safely contained (no acceptance command in this ticket exercises the branch it affects,
since the full walk over a card stage is explicitly out of my scope — "GPU / main session — not
yours").

1. **`--help`'s layout drops the ten per-subcommand usage synopses I first drafted.** My first
   draft printed `run.py <subcommand> ...` on its own indented line for each of the ten, which
   the pinned regex also matched (`run.py` -> `run`), producing 20 names instead of 10 — still a
   superset containing the real ten, so it would not have broken ticket 16/17's presence check,
   but it was noisy and I could not see a reason the ticket would want it. I moved each
   subcommand's own argument shape onto its `subcommands:` line instead (`ls [workflow]
   [--debug] -- one folded line per run`), leaving exactly one un-indented `usage:` line in the
   whole block. Confirmed the regex now recovers exactly the ten names, nothing else.
2. **`cfg._versions`/`cfg._commit` in step 5 ("write done.json ... versions=cfg._versions") is
   the *frozen* setting, not the in-memory `cfg` the walk is holding.** The walk's own `cfg`
   comes from `schema.load()`, whose `_versions`/`_commit` fields are never populated (they are
   `load_frozen`-only fields, per `schema.py`'s own `Setting` dataclass); reading them off that
   `cfg` would always give `{}`/`None`. I read `schema.load_frozen(run_dir)._versions`/
   `._commit` instead (`_finalize_pair_stage`) — the run directory's `settings.yaml` must
   already exist at this point, because the only way a `sample`/`inject` directory reaches full
   completeness is a prior launch by this same `run.py`, which always freezes before launching.
3. **Item 7's "then `registry.write_meta(...)`" is written once, before the card/CPU branch,
   and I kept it that way even though `jobs.launch.launch` (called for a card stage) already
   calls `registry.write_meta` again itself with the full piece list.** The two calls do not
   conflict — `write_meta`'s fields are set, not merged, per name, so the second call's
   `pieces`/`split_files`/`launches` simply supersede the first's absence of them — but it does
   mean a card stage's `meta.json` is written twice inside one lock hold. I read this as
   intentional: it is what makes a CPU stage's `meta.json` (which never reaches
   `jobs/launch.py`) get the same `stage`/`key`/`dir`/`versions`/`upstream`/`diff`/`debug`
   fields a card stage's does, from one call site.
4. **`registry.open_runs()`'s refusal for a CPU stage** is implemented as a call to
   `jobs.launch.gate_open_row` (the same function a card stage's own `launch()` calls
   internally), fed `registry.open_runs()` filtered to this `run_id`, this run's own
   `meta.json`, and a local heartbeat reader (`_read_beats`) that duplicates
   `jobs.launch._read_beats_for_run`'s logic, because that name is private to `jobs/launch.py`.
   This is the literal reading of section 2.3's own sentence ("the open-row refusal through
   `registry.open_runs()` (2.5)") — the "(2.5)" citation is what points at `gate_open_row` as
   the gate being applied, not a bespoke, narrower check. One real gap this inherits from
   `jobs/launch.py`'s own `_piece_alive`, worth the owner's eye: that function's liveness test
   is tmux-session-based, and a `cpu`-kind piece has no `session` field at all — so
   `gate_open_row`'s clause (a) can never see a CPU piece as "live" through this path, and its
   clause (c) exemption ("observed dead") triggers as soon as a pid is recorded, whatever the
   process is actually doing. In practice this only matters inside `launch_timeout_s` (30
   minutes) of a CPU stage's own launch, and `jobs/registry.py`'s own `_pid_alive` (used by
   `ls`'s verdicts) does check the real pid — it is just not the function `gate_open_row` calls.
   I did not touch `jobs/launch.py` to fix this, since it is outside this ticket's two files.
5. **`retry` and `refire` and `kill` never take `--debug`, matching this ticket's own section 1
   command-line list exactly** (only the walk itself and `ls`/`where`/`table` show `--debug`
   there). The practical cost: none of the three can target a debug run's stage. I read this as
   intentional — debug runs are for interactive iteration, not something a person kills, refires
   or retries by name — but it is a real, if narrow, gap I would flag if the owner disagrees.
6. **The `README.md` header format is flush-left full relative paths** (`data/trajectory_record.py
   — the record ...`), not contracts 0.2's own nested tree-drawing indentation (`trajectory_record.py`
   under a `data/` heading, at six spaces). Contracts 0.1's own canonical example already shows a
   flush-left `path/to/file.py`, so I read 0.1 as pinning the shape section 4 asks me to reproduce,
   and 0.2's nesting as that document's own illustration of the same facts inside its bigger tree
   picture. This is also what makes `readme_entries` a two-regex parser instead of a tree walker.
7. **`CLAUDE.md` got its own README entry**, even though the ticket's own list of "non-Python
   entries" (section 4, point 2) does not name it. Contracts 0.2's tree does list it ("the only
   other file at the root that is not code"), and including it costs nothing against any
   acceptance check (D1 filters to `.py`, D2 only requires every `.py` file to be *present*, not
   that the file list be exact). Flagged here in case the owner wants it dropped for a literal
   match against the ticket's own six-category list.
8. **`ls`'s and `find`'s printed row format is my own** — no line shape is pinned anywhere in the
   contracts or the ticket beyond "one folded line per run" / "the rows whose `diff` matches".
   I chose a plain `key=value`-style single line per row; ticket 15's `selfcheck` does not parse
   `run.py`'s own stdout, so this is free to change later without touching a contract.
9. **`registry.open_runs()`-derived elapsed_s (`_elapsed`)** returns `0.0` when no open start
   row exists for a `run_id` at the moment a finish row is written (an edge case: a `done.json`
   with no registry row at all, e.g. hand-placed for a smoke test). This only affects the
   `elapsed_s` field's value, never whether the finish row is written.

## Open questions for the owner (none block this ticket; all are documented decisions above)

- Whether `CLAUDE.md`'s README entry should stay (point 7 above).
- Whether `retry`/`refire`/`kill` should grow a `--debug` flag (point 5).
- The `jobs/launch.py` CPU-liveness gap described in point 4, which predates this ticket and is
  outside its two files.

## Fix round 1

Branch `ticket/2026-09-18-wave5/T14`, worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave5-T14-fix1`, base (previous head)
`089596a624af596d0f49a0f4ec60ed0c834c3b58`, new head `6e85a880164dcb3275a7de0a20746767507f8195`
(commit `6e85a88`, see the commit list below). Two open findings, both fixed.

### F1 (critical) — dead sample/inject claims never released before a relaunch

**Root cause, confirmed by reading the code paths named in the finding.** In `_stage_step`'s
partial-piece block, the old code called `trajectory_record.release(...)` only inside
`if any(_piece_alive(p, sessions, hosts_cfg) for p in work_pieces):` — i.e. only on the branch
where at least one of this run's own loop/train pieces was still alive. On the branch where
`work_pieces` was non-empty but **none** was alive (every piece's tmux session gone — a node
reboot, an OOM sweep, a killed host), the code fell straight through to the launch path with no
release call anywhere on it (confirmed `jobs/launch.py`'s `launch()` never calls
`trajectory_record.release` either — it just re-plans a fresh `piece_plan` and starts new tmux
sessions with new indices). `data/trajectory_record.py`'s own `release(dir, live_sessions,
unowned_age_s)` deletes exactly the unfinished record files whose owner session is not in
`live_sessions`; skipping the call left every dead session's claim file on disk, still "owned"
by a session that no longer exists. A fresh loop piece's own claim rule (`O_EXCL` create, skip
any file that exists) then skips those pairs forever — the run is permanently stuck with no
error message, matching the finding's cited contract passage almost exactly.

**Fix.** Moved the `release()` call outside the `if any(...)` branch so it always runs whenever
`work_pieces` is non-empty, and made the alive/dead decision purely about whether to stop the
walk (launch nothing) or fall through to relaunch:

```python
if stage in ("sample", "inject"):
    meta = _read_json(run_dir / "meta.json") or {}
    work_pieces = [p for p in (meta.get("pieces") or []) if p.get("kind") in ("loop", "train")]
    if work_pieces:
        sessions = registry.live_sessions()
        released = trajectory_record.release(
            run_dir, sessions, registry.DEFAULTS["launch_timeout_s"])
        if released:
            print(f"run.py: released {len(released)} dead claim(s) under {run_dir}")
        if any(launch.piece_alive(p, sessions) for p in work_pieces):
            print(f"run.py: {run_dir} has a live piece; launching nothing")
            return "stop"
```

This is safe on the "some piece alive" branch too: `release()`'s own per-file rule
(`who not in live_sessions`) never touches a claim owned by a session that is in `sessions`, so
calling it unconditionally cannot delete a live piece's own in-progress claim — it only ever
removes claims already owned by dead sessions, whether or not a *different* piece of the same
run is still alive. Verified directly (not through an acceptance command — no acceptance
command in this ticket reaches a card stage, per the ticket's own "GPU / main session — not
yours" scoping) with two standalone scripts against fake run directories:

- A fully-dead run (two `loop` pieces, both sessions absent from `live_sessions`, one unfinished
  claim file owned by one of them): `trajectory_record.release` deleted the claim file,
  `any(launch.piece_alive(...))` read `False` — the corrected code now falls through to
  relaunch instead of leaving the stuck file in place.
- A partly-alive run (one `loop` piece's session live, one dead, one claim file per piece):
  `release` deleted only the dead piece's claim file and left the live piece's claim file in
  place; `any(launch.piece_alive(...))` read `True` — the corrected code still stops without
  launching, matching the ticket's own "while any piece... has a live session... launch
  nothing" text.

I read the ticket's own step-4 wording ("while any piece... has a live session, release the
dead sessions' claims... and launch nothing; once none has, relaunch...") as ambiguous on
whether release is scoped to the "some alive" clause only or applies to both — the finding
flagged this ambiguity itself. Given `release()`'s own documented per-file semantics (contracts
1.1: "a live session, or a host whose probe never answered" is the only thing that keeps a
claim; nothing in that semantics is conditioned on a sibling piece of the same run being alive),
and the stuck-forever consequence of not releasing on the "none alive" branch, I read the
unconditional call as the correct root-cause fix rather than a special case, and applied it
directly rather than adding a bypass for the all-dead branch.

### F2 (important) — run.py duplicated jobs/launch.py's private liveness/heartbeat helpers

**Root cause.** `run.py`'s own `_piece_alive` and `_read_beats` were near-verbatim copies of
`jobs/launch.py`'s `_piece_alive` (2-arg form, using that file's own `_canonical_host` for the
`failed_hosts` check) and `_read_beats_for_run`, kept separate only because the implementer read
the leading underscore as a signal the names should not be imported across the module boundary.
That leaves two independently-maintained copies of fail-closed liveness logic and heartbeat-file
parsing with nothing enforcing they stay identical.

**Fix.** Promoted both functions in `jobs/launch.py` from private to public — `_piece_alive` ->
`piece_alive`, `_read_beats_for_run` -> `read_beats_for_run` — updating their docstrings to say
`run.py` now calls them directly, and updated every internal call site in `jobs/launch.py`
(`gate_open_row`'s two call sites, `alive_check`'s one, `launch()`'s one for the beats reader).
Deleted `run.py`'s own `_piece_alive` and `_read_beats` definitions entirely and pointed both of
their call sites at the shared functions: `_start_cpu_stage`'s `beats = {run_id:
launch.read_beats_for_run(run_dir)}`, and `_stage_step`'s `any(launch.piece_alive(p, sessions)
for p in work_pieces)`. `jobs/launch.py`'s `piece_alive` takes only `(piece, live_sessions)` — it
reads its own module's `_canonical_host`/`constants/path_outputs.yaml` internally rather than
taking a `hosts_cfg` argument — so switching to it also let `_stage_step` drop its now-unused
`hosts_cfg = _hosts_config()` line; `_hosts_config()` itself stays, since `main()`'s
`require_login_host` call still needs it. Grepped `jobs/launch.py`, `tests/`, `README.md` and
the contracts for the two old private names first, to confirm nothing else referenced them by
name (the contracts document does not mention either function at all — they are implementation
detail, not part of `jobs/launch.py`'s documented interface — and no test calls them directly),
so the rename has no other call sites to update. No README change was needed: `run.py`'s own
`imports:` line already names `jobs/launch.py` generically, without enumerating functions.

### How it was verified

All commands run from the worktree root with `$PR` =
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`, after the fix commit
(`6e85a88`) landed. Every acceptance command from the ticket was re-run in full and matched the
original report's output exactly (same ten subcommand names on the same lines, same refusal
messages, same eight `where` paths, same C5 key-purity result, same `31 True` / `27` / `NO_ABS_PATH`).

```
$ "$PR" -c "import ast; ast.parse(open('run.py').read()); ast.parse(open('jobs/launch.py').read()); print('SYNTAX OK')"
SYNTAX OK

$ "$PR" run.py; echo "rc=$?"
usage: run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]
...
  ls          [workflow] [--debug] -- one folded line per run
  where       <workflow> <setting> <stage> [--debug] -- the absolute run directory for one stage
  find        section.field=value ... -- the runs whose settings_diff matches every given field
  kill        <workflow> <setting> <stage> -- end one run's pieces, write the killed finish row
  refire      <workflow> <setting> <stage> [--piece i] [--allow-dirty] -- restart one dead piece
  retry       <workflow> <setting> <stage> [--allow-dirty] -- clear markers, then launch it fresh
  table       [workflow] [--out FILE] [--debug] -- the backbone x method x risk table
  free        -- the free cards per host
  sync        -- fold done.json and heartbeats into missing finish rows
  selfcheck   -- the tree's self-consistency checks
rc=0
$ "$PR" run.py nosuchworkflow x >/dev/null 2>&1; echo "rc=$?"
rc=1

$ "$PR" -c "... run.normalize_host/require_login_host ..."
tokyo105 tokyo106
refused: True

$ "$PR" run.py ls; echo "rc=$?"           # run.py ls: no runs / rc=0
$ "$PR" run.py ls --debug; echo "rc=$?"   # run.py ls: no runs / rc=0
$ "$PR" run.py find stage=sample; echo "rc=$?"   # run.py find: no runs match / rc=0
$ "$PR" run.py table; echo "rc=$?"        # empty matrix header / rc=0
$ git status --porcelain jobs/runs.jsonl jobs/RESULTS.md   # empty -- no runtime writes

$ for a in "baseline gpt_oss_120b_appworld sample" "baseline gpt_oss_120b_appworld score" \
           "train_probe ctool_qwen3_0pt6b sample" "train_probe ctool_qwen3_0pt6b build"; do
    "$PR" run.py where $a; "$PR" run.py where $a --debug
  done
# same eight paths as the original report, C4 ok

$ T5=$(mktemp -d); git archive HEAD run.py constants experimental_settings data models agent eval jobs | tar -x -C "$T5"
# ... path_outputs.yaml root repointed at a nonexistent dir ...
repo root: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/sample/a7d8b62ee953
temp root: /tmp/tmp.oZz3p4KF1C/no_such_outputs_root/sample/a7d8b62ee953
outputs root still absent
C5 ok

$ "$PR" - <<'PY'   # the baseline.yaml / train_probe.yaml key/freeze sweep
...
C6 ok

$ "$PR" -c "... run.readme_entries('README.md') ..."
31 True

$ find run.py constants experimental_settings data models agent eval jobs -name '*.py' | wc -l
27
$ find ... | while read -r f; do grep -qF "$f" README.md || echo "MISSING $f"; done
(no output)

$ grep -n "/home/\|/net/" run.py || echo NO_ABS_PATH
NO_ABS_PATH

$ "$PR" run.py selfcheck; echo "rc=$?"
selfcheck arrives in ticket 15
rc=1

$ "$PR" tests/test_registry_concurrent_append.py
Ran 1 test in 0.206s
OK
```

**F1-specific checks, run against standalone fake run directories (not part of the ticket's own
acceptance list, since no acceptance command in this ticket reaches a partial-piece walk):**

```
# fully-dead run: two loop pieces, both sessions absent from live_sessions,
# one unfinished claim file owned by one of the dead sessions.
released: ['/tmp/.../records/task1__0.jsonl']
record file still exists: False
any piece alive: False
# -> corrected code now falls through to relaunch instead of stopping with the stale
#    claim file still in place.

# partly-alive run: one loop piece's session live, one dead, one claim file each.
released: ['task_dead__0.jsonl']
live claim still exists: True
dead claim still exists: False
any piece alive: True
# -> corrected code still returns "stop" (launches nothing), and the live piece's own
#    claim file is untouched.
```

### The commit list

- `6e85a88` — `T14: release dead sample/inject claims before every relaunch, share
  liveness/heartbeat helpers with jobs/launch.py`. Both findings fixed in one commit: F1's
  `_stage_step` reordering and F2's `jobs/launch.py` rename plus `run.py`'s call-site switch and
  duplicate-function deletion.

### Self-review

- Full diff re-read end to end: `git diff --stat` shows exactly the two ticket-adjacent files
  touched (`run.py`, `jobs/launch.py`); no other file changed. `jobs/launch.py` is outside this
  ticket's own two named files (`run.py`, `README.md`), but F2 cannot be fixed as a root-cause
  fix without editing the module that owns the duplicated logic — promoting two already-private,
  contract-undocumented helpers to public names, with every internal call site updated to match,
  is the minimal edit that removes the duplication rather than papering over it; no other line of
  `jobs/launch.py` changed.
- Checked `jobs/launch.py`, `tests/`, `README.md` and `notes/plans/2026-09-17-contracts.md` for
  every other reference to the two renamed names before renaming; none exist outside
  `jobs/launch.py` itself.
- Re-ran the full acceptance list end to end after the fix commit; every command's output matches
  the original report's byte for byte (the sample/task keys, the ten subcommand names and their
  line positions, the eight `where` paths, `31 True`, `27`, `NO_ABS_PATH`).
- No refactor beyond the two findings: the `_hosts_config()` function itself was not touched
  (still used by `main()`'s login-host refusal); only its now-unused call inside `_stage_step`
  was removed as a direct consequence of switching to `launch.piece_alive`.

### Open questions

None from this fix round. Both findings are fixed as root-cause changes, not patches; the three
open questions from the original report (the `CLAUDE.md` README entry, `--debug` on
`retry`/`refire`/`kill`, the pre-existing `jobs/launch.py` CPU-liveness gap in `gate_open_row`)
are unchanged and still open for the owner.
