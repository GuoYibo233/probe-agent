# 14 run.py: the walk and the nine subcommands, and README.md

Status: ready-for-agent
Blocked by: 02, 03, 04, 05, 08, 10, 12
Spec: .scratch/from-zero/spec.md (sections 1, 2, 3, 4, 6, 7, 9)

## What to do

Two files: `run.py` and `README.md`. Contracts 2.3 (the walk, the skip tests, who
starts a CPU stage), 2.4 (the continue rule and `retry`), 2.5 (the gates `run.py`
holds), 8.1 and 8.2 (the rows), 8.6 (the subcommands), 3.4 and 0.2/0.4 (the
README) are the specification; read 2.3, 2.5 and 8.6 in full.

```
run.py       venv: probe (the interpreter this repo's commands are typed with)
  imports: experimental_settings/schema.py, jobs/launch.py, jobs/registry.py,
           data/task_record.py (done_pairs, is_done, owner, release),
           data/environments/__init__.py (open_env, requested_pairs),
           eval/utils/probe_eval.py (read_report), eval/method_table.py (table)
  used by: none (program)
  carries NO VERSION
README.md    the whole file, assembled from contracts 0.2 and 0.4, reconciling the
             lines earlier tickets added
```

**`selfcheck` is ticket 15.** This ticket reserves all ten subcommand names (so a
workflow file whose stem is one of them can be refused) and lists all ten in
`--help`, but `run.py selfcheck` raises `SystemExit("selfcheck arrives in ticket
15")` for now. Ticket 15 replaces that one line.

### 1. The command line (errata; 0.2 lists the subcommands and fixes no argv shape)

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

**The `--help` layout is pinned, because two later tickets parse it.** The usage
block prints the walk form, then one subcommand **per line, indented by exactly
two spaces, the name first**:

```
  free        print the free cards per host
  ls          one folded line per run
  ...
```

Tickets 16 and 17 both recover the existing subcommand set with
`re.findall(r"^\s{2,}([a-z][a-z0-9_-]*)", help_txt, re.M)` and fail when a name
they cite is missing from it, so a comma-separated list on one line, or a single
space of indent, fails a later ticket for something this one did. Say in your
report which line of your `--help` output each of the ten names sits on.

The ten subcommand names are **reserved**; any other first token is a workflow
**file** stem resolved to `experimental_settings/<name>.yaml`.
`section.field=value` tokens become `load`'s `overrides` (5.7 step 5), each
right-hand side parsed with `yaml.safe_load`, so a reference can be pinned from
the command line.

### 2. The walk (2.3, 2.4, 2.5, 3.4, 8.1, 8.2)

For each `Setting` that `schema.load(file, name, debug=…, overrides=…)` returns
(a list; a `sweep:` gives children), for each stage of `cfg._workflow` in order:

1. `key = schema.key(stage, cfg)`, `run_dir = schema.run_dir(stage, cfg)`.
2. **The skip test.** For `sample` and `inject` it is the **pair check**: build
   the requested list with `requested_pairs(env, splits, tasks, n_tasks, seeds)`,
   project the triples to `(task_id, seed)` pairs, and compare against
   `task_record.done_pairs(run_dir, pairs)` — **the run directory**;
   `data/task_record.py` appends `records/` itself (errata). A subset means skip.
   Every other stage skips on the presence of `done.json`.
3. **Before a skip**: compare the directory's `consumed.json` entries — and, for
   `sample` and `inject`, `meta.json`'s `split_files` hashes — against the files
   they name; on a mismatch **refuse**, naming the file and both hashes, and stop
   (`run.py retry` rebuilds). On a skip, add this `{workflow, setting}` to
   `meta.json`'s `owners` through `registry.write_meta`, under the lock — a skip
   is an ownership event (8.3, 2.3).
4. **A `sample`/`inject` directory that is partly done**: while any piece of
   `kind` `loop` or `train` of that run has a live session, release the dead
   sessions' claims through `task_record.release(run_dir,
   registry.live_sessions(), registry.DEFAULTS["launch_timeout_s"])`, report
   them, and **launch nothing**; once none has, relaunch for the missing pairs,
   reusing the run's live service pieces.
5. **Completeness reached**: write `done.json` through
   `registry.write_done(run_dir, …, pairs=pairs, counts={records: len(pairs),
   tasks: …, seeds: …}, metrics={}, report=None, versions=cfg._versions)`, call
   `launch.teardown_services(run_dir)`, append the `ok` finish row, and go on to
   the next stage.
6. **Otherwise launch.** For `inject`, first hold 2.5's two `run.py` gates —
   (a) the two referenced train runs share a `_upstream["build"]` key, and (b) the
   recorded `_versions` of `data/probe_input.py`,
   `models/probe_models/base.py` and **each train run's own backbone module**
   equal the current source `VERSION`s, read with `schema.module_version` — and
   read the classifier report with `probe_eval.read_report(...)` to fill
   `resolved["probe_temperature"]` (5.4). Refuse when any referenced run has no
   `done.json`. The resolved upstream map comes from
   `schema.upstream(stage, cfg)`, which the loader offers for exactly this
   (errata: nothing in 5.1 hands `run.py` the map before `freeze`).
7. **Inside one `registry.lock()` hold**: `git = launch.git_state(run_dir,
   allow_dirty)`, then `schema.freeze(setting, stage, run_dir, resolved,
   git["commit"])`, then `registry.write_meta(...)`, then
   - a **card stage** (`sample`, `inject`, `train`):
     `outcome, pieces = launch.launch(stage, cfg, run_dir, resolved, git)` (which
     takes the same lock re-entrantly and appends the start row); after the hold,
     on any outcome but `up` append a `launch_failed` finish row and stop; on `up`
     print the monitoring command (`run.py ls <workflow>`) and **stop the walk** —
     an asynchronous GPU stage is never waited on;
   - a **CPU stage** (`build`, `eval`, `score`): run `registry.open_runs()`'s
     refusal, spawn the process in place with the `venvs.probe` interpreter and
     the command shape of 2.6, **capture its pid inside the hold** (errata: 8.1
     appends the start row inside the lock while its `cpu` piece entry carries a
     pid that exists only after the process starts), append the start row with a
     single `kind: cpu` piece entry, release the lock, wait for the exit; **on a
     non-zero exit append a `failed` finish row immediately** inside a fresh hold
     and stop; on zero append the `ok` finish row from the stage's own `done.json`
     and continue.
8. A directory whose `done.json` exists with no finish row gets an `ok` finish
   row on the walk that first sees it (8.2).

### 3. The subcommands (8.6)

- `ls` computes `edited` (the named setting's current key against the directory)
  and `progress` (`task_record.done_pairs` against the requested total) itself and
  passes both into `registry.ls`.
- `where` uses `schema.run_dir` (it has the setting and therefore `--debug`).
- `find` passes the parsed `section.field=value` dict to `registry.find`.
- `kill` calls `registry.kill` and writes the `killed` finish row.
- `refire` resolves the setting and the run directory, takes
  `launch.git_state` and **re-freezes `_commit`** inside the lock, then calls
  `launch.refire(run_dir, git, piece)` (2.3: a refire takes the same two launch
  steps a first launch takes).
- `retry` deletes `last/`, `train_log.jsonl` and the markers and launches
  normally (2.4). **`--retry` never rides on the piece command**: the piece
  command keeps the shape 2.6 and 3.4 pin.
- `table` calls `eval.method_table.table(workflow, out)`.
- `free` prints `registry.free()`.
- `sync` prints `registry.sync()`.

**The host refusal (8.6):** `run.py` refuses to run on any host but `login_host`,
naming it and the host it is on, with both sides normalized through the `hosts:`
entries' `alias` column (errata). Offer `normalize_host(name, hosts)` and
`require_login_host(current, hosts, login_host)` as module-level functions, so
the acceptance can address them.

Legacy sources: `legacy/run.py:1270-1305` (the subcommand dispatch shape),
`:830-840` (`tail_of`, for the failed-launch report), `:799-827` (the dirty gate,
which moves into `launch.git_state`).
**Not ported:** `TASKS` and `RECIPES` and everything that reads them
(`legacy/run.py:80-768, 872-1083, 1117-1171`); the recipe engine and `status`
(`:881-1111`); `build_cmd` / `task_env` / `gate_of` / `run_direct` /
`print_handoff` (`:771-869`); the `PY` interpreter map, replaced by
`constants/path_datasets.yaml`'s `venvs:`; the `configs/` preset and model-table
checks inside selfcheck (`:1237-1264`).

### 4. `README.md` (contracts 0.1, 0.2, 0.4)

Four sections, in this order:

1. **What this repo is and how to run it** — the tree's principle list in its
   one-line form, the command shapes above, the `--debug` line, and the rule that
   outputs live under `constants/path_outputs.yaml`'s `root` and `run.py where`
   prints the path (3.4).
2. **The tree, one entry per file** — reproduced from contracts 0.2, which is
   **authoritative**, in 0.1's exact five-line annotation format and punctuation,
   because `run.py selfcheck` parses it:
   ```
   path/to/file.py — one sentence of what it does.
     imports: a.py, b.py
     used by: c.py, d.py
     reads:   <format or file>
     writes:  <format or file>
     venv:    any | appworld | probe | vllm
   ```
   All **34** Python files of 0.3 plus the non-Python entries (`constants/*.yaml`,
   `experimental_settings/*.yaml`, `models/table.yaml`, `jobs/runs.jsonl`,
   `jobs/RESULTS.md`, `tests/`). Earlier tickets added their own lines as they
   landed; reconcile them against 0.2 and against
   `.scratch/from-zero/contract-errata.md` where an erratum corrected an
   annotation line (`data/build_dataset.py`'s `imports:` and `reads:`,
   `train/utils/trainer.py`'s third-party list, `eval/score_run.py`'s `reads:`).
3. **The extension recipes** — contracts 0.4's seven scenario rows plus the two
   non-extension rows, each as "what you edit, in order, and what it costs".
4. **The ledgers** — `jobs/runs.jsonl` append-only, `jobs/RESULTS.md` rendered,
   both never hand-edited; `notes/` is the owner's.

Legacy source: `legacy/MAP.md` is the ancestor and **nothing is copied from it**;
every line of section 2 comes from contracts 0.2.

## Acceptance

Run from the repo root and paste the real output. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`. **No command here may
launch a GPU stage.**

**C1 — usage and the reserved names.**
```bash
"$PR" run.py; echo "rc=$?"
"$PR" run.py nosuchworkflow x 2>&1 | tail -1
```
Expected: the usage block listing the walk form and **all ten** subcommand names,
one per line and indented by two spaces as section 1 pins, `rc=0`; then a message
naming `experimental_settings/nosuchworkflow.yaml` as missing, exit non-zero.
Ticket 16's `C8` and ticket 17's `C8` parse this block with
`^\s{2,}([a-z][a-z0-9_-]*)`, so paste the block verbatim into your report.

**C2 — the host normalization and the login-host refusal.**
```bash
"$PR" -c "
import sys; sys.path.insert(0,'.')
import run
hosts = [{'name':'tokyo105','alias':'shiga','cards':8},{'name':'tokyo106','cards':10}]
print(run.normalize_host('shiga', hosts), run.normalize_host('tokyo106', hosts))
try:
    run.require_login_host('tokyo999', hosts, 'tokyo105')
    print('NO REFUSAL')
except SystemExit as e:
    print('refused:', 'tokyo999' in str(e) and 'tokyo105' in str(e))"
```
Expected: `tokyo105 tokyo106`; `refused: True`; exit 0.

**What this ticket cannot key yet, and where the rest of the sweep lives.** This
ticket runs in wave 5 **beside ticket 13**, so `train/` does not exist in your
worktree, and a ticket may never assume a sibling of its own wave (the
construction plan, section 1). `schema.key("train", cfg)` reads
`STAGES["train"]["versions"]` — `train/utils/trainer.py` and
`train/methods/<m>.py` — as source text, and `module_version` raises on a missing
file, so **any command that keys a `train` stage raises here through no fault of
the implementation**. An `eval` key folds the train key (3.3's `upstream` entry)
and an `inject` key folds its referenced probes' train keys, so those raise too.
`C4`, `C5` and `C6` below are therefore restricted to what wave 5 can key:
`baseline`'s two stages and `train_probe`'s `sample` and `build`. **The full
sweep over every stage of every workflow is ticket 15's `D6` and `D7`**, run in
wave 6 once `train/` has merged. Do not re-order the waves and do not drop the
four `train/*.py` entries from `README.md` to make a count match: `run.py` itself
imports nothing from `train/`, which is why it can be written now.

**C3 — the read-only subcommands run against the live (empty) registry.**
```bash
"$PR" run.py ls; echo "rc=$?"
"$PR" run.py ls --debug; echo "rc=$?"
"$PR" run.py find stage=sample; echo "rc=$?"
"$PR" run.py table; echo "rc=$?"
git status --porcelain jobs/
```
Expected: for each, a one-line "no runs" message or a header with no rows, and
`rc=0`; `git status --porcelain jobs/` stays empty. **None of the four may issue
an `ssh`**, and that is part of the check: `ls` computes its verdicts through
`registry.live_sessions()`, one `ssh` per host, and ticket 03 pins that it is
called only when the folded row set is non-empty. The ledger is empty in your
worktree, so all four return without touching a host. If any of them hangs or
prints an ssh error, report it as a ticket-03 defect; an implementer never runs
`ssh` (spec section 7).

**C4 — `where` answers for every keyable stage, real and debug.**
```bash
set -e
for a in "baseline gptoss_aw sample" "baseline gptoss_aw score" \
         "train_probe ctool_q06 sample" "train_probe ctool_q06 build"; do
  "$PR" run.py where $a
  "$PR" run.py where $a --debug
done
echo "C4 ok"
```
Expected: eight absolute paths of the shape `<root>/<stage>/<12 hex>` and
`<root>/debug/<stage>/<12 hex>`, printed whether or not the directories exist;
`C4 ok`, exit 0. The `train`, `eval` and `inject` rows are ticket 15's `D6`.

**C5 — a key is pure: the same setting keys the same against an outputs root that
does not exist.** **Nothing here touches the real outputs root.** That root is
shared by every ticket, every wave and the main session's debug walks; renaming
it, even for two commands, breaks any run writing there at that moment, and a
non-zero exit in between (with `set -e` still in force from `C4`) would leave it
renamed for everything downstream. The proof runs against a private copy of the
tree instead, the same trick ticket 09's fixture uses.
```bash
set +e
T5=$(mktemp -d)
cp -a run.py constants experimental_settings data models agent eval jobs "$T5"/
"$PR" -c "
import yaml, pathlib
p = pathlib.Path('$T5/constants/path_outputs.yaml')
d = yaml.safe_load(p.read_text()); d['root'] = '$T5/no_such_outputs_root'
p.write_text(yaml.safe_dump(d))"
A=$("$PR" run.py where baseline gptoss_aw sample)
B=$(cd "$T5" && "$PR" run.py where baseline gptoss_aw sample)
echo "repo root: $A"
echo "temp root: $B"
test ! -e "$T5/no_such_outputs_root" && echo "outputs root still absent"
test "$(basename "$A")" = "$(basename "$B")" && echo "C5 ok"
rm -rf "$T5"
```
Expected: two paths with different prefixes and the **same** 12-hex last
segment; `outputs root still absent` (`where` prints a path, it does not create
one); `C5 ok`, exit 0. That is what key purity means here: the key is a function
of the setting and the versions, not of what is on disk under the outputs
root.

**C6 — `baseline.yaml`'s named setting loads, keys and freezes under `--debug`
and without it**, plus `train_probe`'s `sample` and `build`. No launch, no card,
no output directory.
```bash
"$PR" - <<'PY'
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
```
Expected: one line per (file, setting, debug/real) naming a 12-hex key per listed
stage, then `C6 ok`, exit 0. `CASES` walks the two files the script names,
`baseline.yaml` and `train_probe.yaml`, and **`inject.yaml` is not among them**:
loading an inject setting resolves `inject.probe_score` and `inject.probe_gen` to
key chains (5.4, "a name, resolved by loading that file and computing its key
chain"), and those chains read `train/utils/trainer.py`'s and
`train/methods/<m>.py`'s `VERSION` lines, which are not on disk in a wave-5
worktree. Do not add the third file here; the unrestricted sweep is ticket 15's
`D7`, run in wave 6.

**D1 — every README entry parses into the five annotations.**
```bash
"$PR" -c "
import sys; sys.path.insert(0,'.')
import run
ent = run.readme_entries('README.md')
py = [p for p in ent if p.endswith('.py')]
print(len(py), all(set(ent[p]) >= {'imports','used by','reads','venv'} for p in py))"
```
Expected: `34 True`, exit 0. (`readme_entries` is the parser ticket 15's
`selfcheck` uses; write it here, with `where`/`ls`, so D1 can run.)

**D2 — the file count on disk, and the README covering every file that exists.**
```bash
find run.py constants experimental_settings data models agent eval jobs \
     -name '*.py' | wc -l
find run.py constants experimental_settings data models agent eval jobs \
     -name '*.py' | while read -r f; do grep -qF "$f" README.md || echo "MISSING $f"; done
```
Expected: `30`, and no `MISSING` line. **30, not 34**: `train/` is ticket 13's and
merges at the end of this same wave, so the four `train/*.py` files are not on
disk in your worktree — `1 run.py + 1 schema.py + 8 data + 8 models + 4 agent +
6 eval + 2 jobs`. `README.md` still carries all **34** entries, the four `train/`
ones included, because it is assembled from contracts 0.2 and `D1` counts them
(`34 True`). Do not drop a `train/` line to make this command print 34, and do
not add `train` to the `find` list. The 34-file check is **ticket 15's `D3`** and
**ticket 18's `C6`**, both after wave 5 merges.

**D3 — no absolute cluster path in `run.py`.**
```bash
grep -n "/home/\|/net/" run.py || echo NO_ABS_PATH
```
Expected: `NO_ABS_PATH`.

### Selfcheck lines that apply later

Ticket 15 adds `run.py selfcheck` and the parsers `imports_of` and `literal_of`
beside `readme_entries`. Over this ticket's files it will check: the README's file
list against the tree (D2); `run.py`'s own annotation line against the
`ast`-parsed import graph; the `/home/`-`/net/` rule (D3); and that no workflow
file's stem is one of the ten reserved subcommand names.

### GPU / main session — not yours

Every walk that reaches a card stage. `M-J3` through `M-J8` in ticket 12, and the
three end-to-end `--debug` walks of the construction plan's section 4. An
implementer that reaches one returns BLOCKED with the command.

## Comments
