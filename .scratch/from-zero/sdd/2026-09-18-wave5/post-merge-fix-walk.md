# Wave 5 post-merge fix — the walk and the subcommands (`run.py`, `jobs/registry.py`)

Area: `run.py`, `jobs/registry.py` (the `ls` parameters and the fields 8.6's line needs),
`README.md`'s annotation lines for those two files.
Findings fixed: `WALK-1` (= `SEAMS-3`), `WALK-2`, `WALK-3`, `SUBCOMMANDS-1` (= `SEAMS-8`),
`SUBCOMMANDS-3`, `SEAMS-5`.

Base `9c3b963`, branch `fix/2026-09-18-wave5-walk`, head `63ed7f9`, worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave5-fix-walk-r1` (removed at the end; the branch
stays). The dispatch names `df3c473` as the base; when the worktree was created the repo's
`HEAD` was `9c3b963`, which is `df3c473` plus the commit that recorded
`post-merge-review.json` and changes no code (`git show --stat 9c3b963`: one file,
`.scratch/from-zero/sdd/2026-09-18-wave5/post-merge-review.json`). The branch therefore
starts at `9c3b963` and carries the same code as `df3c473`.

Commits:

| sha | what |
|---|---|
| `b822293` | the six findings: the `stage_extra` fold, the widened pair request, the always-recompute stages, the pinned reference's root, the eight-flag ls line |
| `6149123` | the ls line prints the beat unit only when the beats gave one |
| `63ed7f9` | a skip rewrites `meta.json` only when it brings a new owner |

The repro scripts are under `/tmp/wave5walk/` (`fixture.py`,
`r1_stage_extra_and_recompute.py`, `r2_widened_and_score.py`, `r3_pinned_debug_keys.py`,
`r3b_pinned_real_keys_under_debug.py`, `r4_ls_line.py`, `c6_sweep.py`). Each runs against a
private export of the branch (`git archive HEAD run.py constants experimental_settings data
models agent eval jobs train | tar -x -C "$T"`) whose `constants/path_outputs.yaml` `root` is
repointed into that export, so nothing touches the real outputs root, the real ledger or
another session's tree. Every script stubs `registry.live_sessions` or leaves the ledger empty:
no `ssh` was issued and no GPU process was started.

---

## WALK-1 (= SEAMS-3) — the walk folds `done.json`'s `stage_extra` into `meta.json`

**Root cause.** Contracts 8.3 gives `meta.json` exactly two writers and puts the fold on the
walk: "the stage writes it into its own `done.json` and `run.py` folds it in here on its walk
(1.3)". `run.py` had no occurrence of `stage_extra` at all: the finished branch ran
`_refuse_on_stale_inputs` → `_record_owner` → `_backfill_finish_row`, and that last function
reads `done.json` only for `counts`, `metrics` and `report`. `train/utils/trainer.py:350-355`
writes `stage_extra={"labels": labels}` into its own `done.json`, and
`eval/utils/probe_eval.py:578-579` reads `train_meta["stage_extra"]["labels"]` out of the train
run's `meta.json` with no default, so every eval stage raised `KeyError('labels')`.

**The change.** `_fold_stage_extra(run_dir, done)` (run.py) writes `done.json`'s `stage_extra`
into `meta.json` through `registry.write_meta` under `registry.lock()`. It is called on both
places where the walk first sees a stage's `done.json`: the finished branch of `_stage_step`,
and the CPU-stage path right after a zero exit, before the `ok` finish row — the same walk that
writes the finish row, as 8.3 says.

**Repro.** `/tmp/wave5walk/r1_stage_extra_and_recompute.py` builds the debug train directory of
`train_probe/ctool_qwen3_0pt6b` exactly as a finished train run leaves it (frozen settings, the
`meta.json` `run.py` writes before a launch, a start row, and `registry.write_done(...,
stage_extra={"labels": [...]})` as `trainer.py` calls it), walks the train stage, then makes the
verbatim `probe_eval.py:578-579` read. It then writes a 12-row `predictions.parquet` and lets
the walk run the eval stage in place, twice.

```
$ cd $T && external/probe-env/bin/python /tmp/wave5walk/r1_stage_extra_and_recompute.py $T
train dir: /tmp/wave5walk/v3-Y1Nc/outputs/debug/train/79f74a7f74d0
before: meta.stage_extra = {}
outcome: continue
after:  meta.stage_extra = {'labels': ['phone.login', 'phone.pay']}
        done.stage_extra = {'labels': ['phone.login', 'phone.pay']}
registry rows: [('start', 'train-79f74a7f74d0', 'launching'), ('finish', 'train-79f74a7f74d0', 'ok')]
probe_eval.py:578-579 read: ['phone.login', 'phone.pay']

eval dir: /tmp/wave5walk/v3-Y1Nc/outputs/debug/eval/a8b67d485d63
first walk of the eval stage: continue
eval done.json metrics: {'coverage@0.1': 1.0, 'trig_acc@0.1': 1.0, 'earliness@0.1': 0.5, 'wrong_spec@0.1': 0.0, 'coverage@0.05': 1.0, 'trig_acc@0.05': 1.0, 'earliness@0.05': 0.5, 'wrong_spec@0.05': 0.0}
eval owners: [{'workflow': 'train_probe', 'setting': 'ctool_qwen3_0pt6b'}]
second walk of the eval stage: continue
eval done.json rewritten in place: 2026-09-18 20:33 (was 2026-09-18 20:33)
rows for the eval run: [('start', 'eval-a8b67d485d63', 'launching'), ('finish', 'eval-a8b67d485d63', 'ok'), ('start', 'eval-a8b67d485d63', 'launching'), ('finish', 'eval-a8b67d485d63', 'ok')]
report.md present: True
```

The labels reach `meta.json`, the read that used to raise returns them, and the eval stage the
finding said could never run now runs to a report and an `ok` finish row. The review's own
repro printed `after: meta.stage_extra = {}` and `eval's read (probe_eval.py:579) raises
KeyError: 'labels'` at the same key `79f74a7f74d0`.

---

## WALK-2 — a widened `sample`/`inject` request completes again

**Root cause.** The completion step was guarded by `if stage in ("sample", "inject") and not
done_path.exists()`, so only the first completion of a directory ever wrote `done.json`, ended
the service pieces and appended a finish row. Contracts 2.3 makes the skip test the pair check
"never the presence of `done.json`" precisely so one directory serves several requests, and says
`done.json` "is rewritten with the wider `pairs` list when they finish", with the services ended
in the same step. The second completion fell into `_backfill_finish_row`, which returns early
because the run already has a finish row, so the relaunch's start row stayed open forever, its
vLLM and probe pieces kept their cards, and `done.json` kept the narrower request's counts.

**The change.** `_certifies_request(done, pairs)` (run.py) answers whether the directory's
`done.json` already certifies every requested pair, by its recorded `pairs` list. The finished
branch runs `_finalize_pair_stage` whenever the request is not yet certified — a first
completion and a widened one alike — and takes the fold-and-backfill path when it is. That also
keeps the completion idempotent: a later walk of the same certified directory writes no new
`done.json`, calls no teardown and appends no second finish row (the reviewer's note that
"finalize whenever the directory is complete" would be too coarse).

**Repro.** `/tmp/wave5walk/r2_widened_and_score.py` builds the 9-pair `--debug` sample directory
of `baseline/gpt_oss_120b_appworld` with every record done, a `done.json` recording the earlier
3-pair request, a `meta.json` holding a service piece, and rows start / finish(ok) / start;
`launch.teardown_services` is stubbed to count calls.

```
$ cd $T && external/probe-env/bin/python /tmp/wave5walk/r2_widened_and_score.py $T
requested pairs: 9

-- before --
done.json counts: {'records': 3, 'tasks': 3, 'seeds': 1} pairs: 3
rows: [('start', 'sample-96de225de2b4', 'launching'), ('finish', 'sample-96de225de2b4', 'ok'), ('start', 'sample-96de225de2b4', 'launching')]

-- after the walk --
outcome: continue
done.json counts: {'records': 9, 'tasks': 9, 'seeds': 1} pairs: 9
teardown_services calls: 1
rows: [('start', 'sample-96de225de2b4', 'launching'), ('finish', 'sample-96de225de2b4', 'ok'), ('start', 'sample-96de225de2b4', 'launching'), ('finish', 'sample-96de225de2b4', 'ok')]

-- a second walk of the same certified directory --
outcome: continue
done.json finished_at unchanged: True
teardown_services calls: 1
rows: [('start', 'sample-96de225de2b4', 'launching'), ('finish', 'sample-96de225de2b4', 'ok'), ('start', 'sample-96de225de2b4', 'launching'), ('finish', 'sample-96de225de2b4', 'ok')]
```

The review's case B printed `done.json: {'counts': {'records': 3, ...}, 'n_pairs': 3}`,
`teardown_services calls: 0` and no new finish row for the same fixture.

---

## WALK-3 — `eval` and `score` always recompute inside their key

**Root cause.** The skip test was `fully_done = done_path.exists()` for every stage but
`sample` and `inject`, so a finished `eval` or `score` directory was skipped. 2.3's stage table
gives those two the continue rule "never skipped: these stages always recompute (Part 2.4)",
and 2.4 repeats it with its reason ("a metric fix that never runs because a finished directory
was reused ... They cost seconds, so nothing is lost").

**Ticket 14 is overridden here, and this is the sentence that overrides it.** Ticket 14's
section 2 step 2 says "Every other stage skips on the presence of `done.json`", which is 2.3's
general prose sentence. The contracts win over the ticket (implementer protocol), and 2.3's own
stage table, 2.4 and 8.2 name `eval` and `score` specifically three times. The built code
followed the losing sentence; it now follows the table. The constant carrying it is
`ALWAYS_RECOMPUTE = ("eval", "score")` in `run.py`, with that reasoning in the comment above it.

**The change.** The skip test is per stage: `sample`/`inject` take the pair check,
`eval`/`score` are never skipped, every other stage skips on `done.json`. A rerun therefore
enters the launch path, overwrites its own directory and gets its own `ok` finish row from the
CPU path. Because a stage that never skips also never takes the skip that records an owner,
the launch path now writes this setting into `meta.json`'s `owners` as well (8.3: `owners`
holds every setting that has "run into **or** reused" the directory).

**Repro, the eval half** — the second half of the `r1` output above: the second walk of the same
eval directory recomputed (`report.md` rewritten, a new `finished_at`) and the ledger holds two
start rows and two `ok` finish rows for `eval-a8b67d485d63`.

**Repro, the score half** — the last block of `r2`, the review's own case: a `score` directory
holding a `done.json` with `metrics {'success': 0.11}`.

```
-- the score stage with its own done.json on disk --
score done.json metrics: {'success': 0.11}
SystemExit: jobs/launch.py: refusing a dirty working tree without --allow-dirty: git probe failed
processes spawned: 2 [['git', '-C', '/tmp/wave5walk/v3-eEAI', 'status'], ['git', '-C', '/tmp/wave5walk/v3-eEAI', 'status']]
```

The stage is no longer skipped: the walk entered the launch path and the dirty gate spoke,
which is exactly what the review's *fresh* control printed and the opposite of its *finished*
case (`outcome: continue`, `processes spawned: 0`). The export is not a git repository, so the
git probe fails and `git_state` is fail-closed; the two recorded spawns are one `git status`
invocation seen twice, because the fixture counts `subprocess.run` and the `subprocess.Popen`
it makes internally.

**8.2's companion rule.** "`run.py` appends a new finish row whenever `done.json`'s
`finished_at` is later than the newest finish row for that `run_id`" is held here by the walk
itself: `eval` and `score` never skip, so `run.py` runs every recomputation in place and
appends that run's own `ok` row on a zero exit — two rows for two runs in the repro above. The
literal comparison is not implemented, because the newest finish row's time is not in anything
`jobs/registry.py`'s reader half returns (`find` folds a finish row's `status`, `counts`,
`metrics`, `report` and `elapsed_s`, not its `t`), and this fix's scope keeps `registry.py` to
what `ls` needs. Open for the owner: expose the finish row's time (or a `rows()` reader) if the
comparison is wanted for a directory recomputed by something other than a walk — today nothing
but `run.py` starts an `eval` or a `score`.

---

## SUBCOMMANDS-1 (= SEAMS-8) and SUBCOMMANDS-3 — the `ls` line

**Root cause.** `cmd_ls` computed only `edited` and `progress`, `registry._ls_row` folded four
flags (`edited`, `debug`, `dirty`, `orphan`), and `_format_ls_row` printed run_id, stage,
names, status, `progress=done/total`, those flags and `index:verdict`. Contracts 8.6 pins eight
flags (`edited`, `behind`, `consumed`, `split`, `pinned`, `dirty`, `debug`, `orphan`), progress
as `done/total unit` **with a rate**, the heartbeat's age, and the sessions and cards. Ticket
14's Comments entry of 2026-09-18 pins `behind`'s semantics on `run.py`, read through
`experimental_settings/schema.py`; `run.py` called neither `schema.version_history` nor
`schema.effective_version`.

**The change.**

- `run.py._compute_row_flags(rows)` computes the five flags this file owns, per run_id, because
  `jobs/registry.py` imports nothing from the repo:
  - `edited`: today's key of the named setting against the row's key (as before).
  - `behind`: the row recorded a `VERSION` below the file's current one **and** its key still
    equals today's — ticket 14's "behind and usable". Read through `schema.versions_of`, the
    same reader that wrote the row's `versions` block, so a `<path>#<TABLE>.<method>` entry and
    a `<path>@<stage>` stand-in are compared the way the stage table spells them.
  - a run whose key moved is stale, and the line then carries a `stale=` field naming the file
    whose bump did it and quoting that entry's `why`, read through `schema.effective_version`
    and `schema.version_history` (a file whose effective version for this stage now stands
    above the recorded version is the file whose bump moved the key).
  - `consumed`: an entry of the directory's `consumed.json` whose sha1 no longer matches the
    file it names; `split`: the same over `meta.json`'s `split_files` — the same comparison the
    walk's skip gate makes.
  - `pinned`: the run's own frozen `settings.yaml` gives one of `schema.REF_FIELDS` as a
    `key:`/`dir:` mapping (5.4).
- `jobs/registry.ls` takes `behind`, `consumed`, `split` and `pinned` beside `edited` and
  `progress`, folds the eight flags in 8.6's order, and carries the line's remaining columns:
  the beat `unit`, `avg_rate`, `recent_rate` and `beat_age_s` folded over the work pieces, and
  per piece its `gpus` and `beat_age_s`. `_orphan_session_row` carries the same eight flags.
- `_format_ls_row` prints `run_id stage workflow/setting status progress=<done>/<total> <unit>
  rate=<recent>/s beat=<age>s flags=<...> pieces=<index>:<verdict>@<host>:<session>
  cards=<gpus>`, plus `stale=<file> VERSION <n>: "<why>"` on a stale row.

**Repro.** `/tmp/wave5walk/r4_ls_line.py` builds three runs in a private tree — a live `sample`
run with two pieces, beats, a changed consumed file and a changed split file; a finished `build`
run; an `inject` run whose two probe references are pinned — then bumps
`data/trajectory_record.py` in that export to `VERSION = 2` with
`VERSION_HISTORY = {2: {"why": ..., "stale": ("build",)}}`. That bump leaves the `sample` key
where it is and moves the `build` key, which is exactly the two cases ticket 14's comment
separates. `registry.live_sessions` is stubbed (no `ssh`).

```
$ cd $T && external/probe-env/bin/python /tmp/wave5walk/r4_ls_line.py $T
bumped data/trajectory_record.py to VERSION 2, stale for build alone
sample key unchanged: True
build key moved: True

run_id | stage | workflow/setting | status | progress | rate | heartbeat | flags | pieces
sample-a7d8b62ee953  stage=sample  baseline/gpt_oss_120b_appworld  status=launching  progress=4/315 record  rate=0.0167/s  beat=62s  flags=behind,consumed,split,dirty  pieces=0:healthy@tokyo105:sample-a7d8b62ee953-0; 1:warming up@tokyo106:sample-a7d8b62ee953-1 cards=0,1
build-6d3bf5aff879  stage=build  train_probe/ctool_qwen3_0pt6b  status=ok  progress=0/0  rate=-  beat=-  flags=edited,dirty  pieces=0:warming up@tokyo105  stale=data/trajectory_record.py VERSION 2: "the record now writes the discard block per step, so a dataset built from an older record is not comparable"
inject-34934c81696b  stage=inject  inject/probe_p1_e1_theta_0pt80  status=launching  progress=0/168  rate=-  beat=-  flags=edited,pinned,dirty  pieces=0:warming up@tokyo107:inject-34934c81696b-0 cards=3

sample-a7d8b62ee953 flags: {'edited': False, 'behind': True, 'consumed': True, 'split': True, 'pinned': False, 'dirty': True, 'debug': False, 'orphan': False}
build-6d3bf5aff879 flags: {'edited': True, 'behind': False, 'consumed': False, 'split': False, 'pinned': False, 'dirty': True, 'debug': False, 'orphan': False}
inject-34934c81696b flags: {'edited': True, 'behind': False, 'consumed': False, 'split': False, 'pinned': True, 'dirty': True, 'debug': False, 'orphan': False}
```

Against the review's repro, which printed `flags=-` for the behind row and `flags=edited` with
no file and no `why` for the moved-key row: the behind row now says `behind`, the stale row
names `data/trajectory_record.py`, its version 2 and that entry's sentence, and the line carries
the unit (`record`), the rate, the heartbeat age, both sessions with their hosts and the service
piece's cards.

---

## SEAMS-5 — a pinned `key:`/`dir:` reference is resolved under its own root

**Root cause.** `_refuse_missing_upstream` used `debug = cfg._debug if e["source"] == "same"
else False`, and the four inject gates hard-coded `debug=False`. That is right for a name-form
reference, which `schema._resolve_name_ref` loads with `debug=False`, but wrong for a pinned
reference: `schema.key` puts `"debug": true` into the payload (3.3), so a debug run's key names a
directory under `<root>/debug/`. Errata "3.4 / 9(c)#8" pins the debug keys of the construction
plan's section-4 `--debug` walk into `inject.yaml`'s references, and that walk stopped at the
upstream check. The same hard-coded `False` sat on the build directory a train run names.

**The change.** One resolution point, `_upstream_dirs(stage, cfg, upstream_map)`, which the
upstream check and all four gates now take instead of the key map:

- a `same`-source upstream is keyed from this very setting, so it lives under this walk's root;
- a name-form reference is loaded by the schema with `debug=False`, so its run is under the real
  root;
- a pinned reference carries a key whose payload holds its own debug flag, so
  `_pinned_run_dir(stage, key)` answers with the directory, under either root, whose frozen
  `settings.yaml` records that key ("schema tells which"), falling back to the directory that
  exists for a pre-scheme `dir:` reference that has no `settings.yaml`, and to `None` when
  neither root holds it (the refusal then names both candidates).
- `_check_inject_code_currency` resolves a train run's `build` directory under the root that
  train run itself was written in, read from its frozen `_debug`.

**Repro.** `/tmp/wave5walk/r3_pinned_debug_keys.py` builds the debug build, train and eval runs
of `train_probe/ctool_qwen3_0pt6b` and `cgen_qwen3_0pt6b`, then loads
`inject.yaml/probe_p1_e1_theta_0pt80` with `--debug` and the three pinned debug keys, the way
the construction plan's section-4 walk types them.

```
$ cd $T && external/probe-env/bin/python /tmp/wave5walk/r3_pinned_debug_keys.py $T
the three pinned debug keys: 79f74a7f74d0 a8b67d485d63 d3fd86ac86e2
the debug train dir of the ctool probe: /tmp/wave5walk/v3-dJ9O/outputs/debug/train/79f74a7f74d0
the real-root path the same key would name: /tmp/wave5walk/v3-dJ9O/outputs/train/79f74a7f74d0
that path exists: False

upstream map: {'probe_score.train': '79f74a7f74d0', 'probe_score.eval': 'a8b67d485d63', 'probe_gen.train': 'd3fd86ac86e2'}
resolved probe_score.train: /tmp/wave5walk/v3-dJ9O/outputs/debug/train/79f74a7f74d0
resolved probe_score.eval: /tmp/wave5walk/v3-dJ9O/outputs/debug/eval/a8b67d485d63
resolved probe_gen.train: /tmp/wave5walk/v3-dJ9O/outputs/debug/train/d3fd86ac86e2
upstream check: passed
gate 1 (the pinned methods against the frozen probe.method): passed
gate 2 (the two train runs share a build key): passed
gate 3 (the recorded VERSIONs equal the live source): passed
gate 4 (the temperature read out of the pinned eval report): {'probe_temperature': 1.37}
```

The review's repro exited with `run.py: inject: upstream 'probe_score.train' at
<root>/outputs/train/79f74a7f74d0 has no done.json; run it first` on the same key.

**The trap the reviewer named** — "flipping to `cfg._debug` alone is wrong, because a debug run
pinning a real run's key would then look under `<root>/debug/`" — is covered:
`/tmp/wave5walk/r3b_pinned_real_keys_under_debug.py` builds *real* train and eval runs and pins
their keys from both a `--debug` and a real inject setting.

```
$ cd $T && external/probe-env/bin/python /tmp/wave5walk/r3b_pinned_real_keys_under_debug.py $T
the three pinned real keys: 61b4c576b703 a4a903bff5de df43b5d7c091

inject setting loaded with debug = True
  resolved probe_score.train: /tmp/wave5walk/v3-QpJK/outputs/train/61b4c576b703
  resolved probe_score.eval: /tmp/wave5walk/v3-QpJK/outputs/eval/a4a903bff5de
  resolved probe_gen.train: /tmp/wave5walk/v3-QpJK/outputs/train/df43b5d7c091
  upstream check and the four gates: {'probe_temperature': 0.91}

inject setting loaded with debug = False
  resolved probe_score.train: /tmp/wave5walk/v3-QpJK/outputs/train/61b4c576b703
  resolved probe_score.eval: /tmp/wave5walk/v3-QpJK/outputs/eval/a4a903bff5de
  resolved probe_gen.train: /tmp/wave5walk/v3-QpJK/outputs/train/df43b5d7c091
  upstream check and the four gates: {'probe_temperature': 0.91}
```

---

## `README.md`

`run.py`'s entry: the `reads:` line adds the `VERSION` and `VERSION_HISTORY` tables of the
modules a stage lists, read through `schema.versions_of`, `schema.effective_version` and
`schema.version_history` for ls's `behind` flag; the `writes:` line says which parts of
`meta.json` the walk writes (its `owners` list, and the `stage_extra` it folds out of a finished
stage's `done.json`). `jobs/registry.py`'s entry needed no change: its sentence, imports, reads
and writes are unchanged by this fix.

---

## Acceptance

Run from the worktree root at `63ed7f9`;
`$PR = /home/y-guo/reproduce/new1/external/probe-env/bin/python`.

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
run.py: /home/y-guo/reproduce/new1-wt/2026-09-18-wave5-fix-walk-r1/experimental_settings/nosuchworkflow.yaml does not exist
rc=1
```

Ten names, one per line, two-space indent, the name first; the block is unchanged by this fix.

**C2 — host normalization and the login-host refusal.**

```
tokyo105 tokyo106
refused: True
rc=0
```

**C3 — the read-only subcommands against the live (empty) registry, no `ssh`.**

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

**D1 — every README entry parses into the five annotations.**

```
31 True
rc=0
```

**D2 — the file count on disk, and the README covering every file that exists.** `train/` has
merged, so the `find` list carries it and the count is **31**, not the ticket's wave-5 27.

```
$ find run.py constants experimental_settings data models agent eval jobs train -name '*.py' | wc -l
31
$ find ... | while read -r f; do grep -qF "$f" README.md || echo "MISSING $f"; done
(no MISSING line)
```

**D3 — no absolute cluster path in `run.py`.**

```
NO_ABS_PATH
```

**C6 — the sweep, `inject.yaml` included.** `/tmp/wave5walk/c6_sweep.py` is ticket 14's C6
script with `CASES = [("baseline.yaml", None), ("train_probe.yaml", None), ("inject.yaml",
None)]`: every stage of every workflow, real and `--debug`, now that `train/` is on disk. (It is
a file rather than a heredoc because the read-only hook refuses a Bash line that names
`experimental_settings`.)

```
$ PYTHONPATH=. "$PR" /tmp/wave5walk/c6_sweep.py
baseline.yaml gpt_oss_120b_appworld real sample=a7d8b62ee953 score=87858c091092
baseline.yaml gpt_oss_120b_appworld debug sample=96de225de2b4 score=20eaad1deae5
train_probe.yaml ctool_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=61b4c576b703 eval=a4a903bff5de
train_probe.yaml ctool_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=79f74a7f74d0 eval=a8b67d485d63
train_probe.yaml cgen_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=df43b5d7c091 eval=56617b259481
train_probe.yaml cgen_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=d3fd86ac86e2 eval=a46f046c0a9d
train_probe.yaml cparam_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=b23d4b289bcc eval=036214306ef8
train_probe.yaml cparam_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=cf4adecfed4f eval=0ed129795cd5
inject.yaml probe_p1_e1_theta_0pt80 real inject=aae002fac6f4 score=01f6905104d2
inject.yaml probe_p1_e1_theta_0pt80 debug inject=0526b23c02b4 score=e0718097e945
inject.yaml no_probe_p1_e1_theta_0pt80 real inject=8ab0cc207990 score=168b9aa8f852
inject.yaml no_probe_p1_e1_theta_0pt80 debug inject=0894c6b1fc6b score=0c2121914267
C6 ok
rc=0
```

The debug keys agree with the fixtures above (`train=79f74a7f74d0`, `eval=a8b67d485d63`,
`d3fd86ac86e2`), which is what makes the SEAMS-5 repro the construction plan's own case.

**The one test that touches these files.**

```
$ PYTHONPATH=. "$PR" -m unittest tests.test_registry_concurrent_append
Ran 1 test in 0.196s

OK
$ git status --porcelain
(empty)
```

---

## Decisions the requirements did not make

1. **Base.** `9c3b963` rather than the dispatch's `df3c473`: the repo had moved on by the
   commit that recorded the review, which changes no code.
2. **`run.py` step 2 versus the contracts (WALK-3).** Stated above: 2.3's stage table, 2.4 and
   8.2 win over ticket 14's general sentence, and the reason sits in the comment above
   `ALWAYS_RECOMPUTE`.
3. **8.2's `finished_at` comparison** is satisfied by the walk appending a row per
   recomputation; the literal comparison is left out because the newest finish row's time is not
   in `registry`'s reader half and this fix keeps `registry.py` to what `ls` needs. Open above.
4. **Owners on a launch.** Since `eval` and `score` now never skip, the skip that recorded an
   owner never happens for them, so the launch path records its own setting into `owners`. 8.3
   defines `owners` as every setting that has run into or reused the directory, so the launch
   case was always inside the definition; before this fix nothing wrote it.
5. **How "the root a pinned key belongs to" is decided.** The directory, under either root,
   whose frozen `settings.yaml` records that key; a directory with no `settings.yaml` (5.4's
   pre-scheme `dir:` case) is taken if it exists; otherwise the refusal names both candidates.
   The reviewer called the rule an owner design call — this one needs no new field, since a key
   payload already carries the run's debug flag and the frozen file already records the key.
6. **A train run's build directory** is resolved under that train run's own root, read from its
   frozen `_debug`.
7. **`registry.ls`'s signature** gained four keyword parameters beside `edited` and `progress`,
   in the same style and for the same stated reason (this file imports nothing from the repo).
   8.0 pins the old signature; the precedent for extending a pinned signature is the owner's
   `table(..., debug=False)` ruling of 2026-09-18.
8. **`_ls_row` also carries** the beat `unit`, `avg_rate`, `recent_rate` and `beat_age_s` at run
   level and `gpus` and `beat_age_s` per piece — the columns 8.6 pins that were computed inside
   `_piece_verdict_dict` and dropped. The run-level rate is the sum over the work pieces (the
   run's throughput), the beat age is the newest beat of any work piece, and the unit is the
   last beat's.
9. **The ls line's layout** (field order, `key=value` spelling, `;` between pieces, the trailing
   `stale=` field) is mine: 8.6 pins what the line carries, not how it reads. The unit is printed
   only when the beats gave one, so a run that has not beaten yet prints `progress=0/168` rather
   than inventing a unit.
10. **`behind` is `None`** for a row whose setting can no longer be loaded, exactly as `edited`
    already was, and the `stale` sentence is computed only for a row whose key moved.
11. **`consumed` and `split` hash the files they name on every `ls`.** That is the comparison
    8.6 describes and the one the walk's gate makes. A `build` run's `consumed.json` can name a
    large dataset, so an `ls` over many runs pays that read; if it becomes slow, a recorded size
    or mtime beside the sha1 would let the flag short-circuit, which is a change to what
    `consumed.json` records and therefore the owner's.
12. **`pinned` is read from the run's own frozen `settings.yaml`**, not from the setting as it
    loads today, so a run keeps the flag after its setting is edited or deleted.

## Left for the owner (seen while fixing, outside these six findings)

- **5.4 says a pinned reference skips the shared-build-key gate** ("it skips the
  inheritance-agreement check below and the shared-build-key gate of 2.5"); `run.py` runs that
  gate for every inject stage, pinned or not. It passes in the fixtures above because both
  pinned train runs do share a build key, so nothing is blocked today. The reviewer of SEAMS-5
  recorded it as a separate deviation, and it is not one of my six findings.
- **`eval/utils/probe_eval.py` resolves its own referenced directories with `debug=False`**
  (the `theta_from` eval directory at line 586, and that eval's own train directory at line
  598), which is
  the same class of defect as SEAMS-5 one file over: a `--debug` generator eval pinned to a
  debug classifier eval would look under the real root. Not my file.
- **`registry.sync()` folds `done.json`'s `counts`, `metrics` and `report` into a missing finish
  row and does not fold `stage_extra`**, so a run closed by `sync` rather than by a walk leaves
  `meta.json`'s `stage_extra` empty until the next walk over that directory. Folding it there
  too is a `registry.py` change outside this fix's scope.

---
---

# Round 2 — the two findings the reviewer left open

Base `63ed7f9` (round 1's head), branch `fix/2026-09-18-wave5-walk`, head `20aba0a`, worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave5-fix-walk-r2` (removed at the end; the branch
stays). One file changed, `run.py`; `jobs/registry.py` and `README.md` needed no change and
have none.

| sha | what |
|---|---|
| `20aba0a` | `WALK-FIX-1`: `ls` reads a setting, its key, its versions block and its request once per (setting, stage), not once per ledger row |

`WALK-FIX-5` gets no commit: the change it asks for belongs to the construction plan's
acceptance command, not to `run.py`, and the evidence is below.

The repro scripts are under `/tmp/wave5walk-r2/` (`fixture.py` and `r3_pinned_debug_keys.py`,
`r4_ls_line.py`, `c6_sweep.py` carried over from round 1; `export.sh`, `r5_ls_cost.py`,
`r6_ls_end_to_end.py`, `r7_theta_from_under_debug.py` new). `export.sh` makes a private export
of the worktree (HEAD plus every changed file) whose `constants/path_outputs.yaml` `root` the
fixture repoints into that export, so nothing touches the real outputs root, the real ledger or
another session's tree. Every script that reaches the registry stubs `registry.live_sessions`
or leaves the ledger empty: no `ssh` was issued and no GPU process was started.

---

## WALK-FIX-1 — `ls` reads a setting once per stage, not once per ledger row

**Root cause.** Three readers on the `ls` path did per-row what is per-setting work, and each
of them re-reads and re-parses source text:

- `_compute_row_flags` cached the loaded setting in `settings[(workflow, setting, debug)]` and
  then threw the cache away on the next line — `current = None if cfg is None else
  _current_key(workflow_name, setting_name, stage, debug)` — and `_current_key` called
  `_current_setting` again, so every row paid a fresh `schema.load`.
- `_behind_versions(row, cfg)` called `schema.versions_of(row["stage"], cfg)` per row, and
  `schema._parse_module` is not memoised, so each call re-read and re-`ast.parse`d every module
  the stage lists.
- `_stale_sentence(row)` called `schema.effective_version` and `schema.version_history` per row
  for each module the row recorded, which is the same parse again, on exactly the rows an
  operator runs `ls` for after a `VERSION` bump.

Round 1 introduced the first two; the third came with them. The base `df3c473` cached the
finished key by `(workflow, setting, stage, debug)` and did the work once.

**The change.** `_current_key_and_versions(stage, cfg)` reads today's key and the versions block
off the already-cached setting, and `_compute_row_flags` holds it in `readings[(workflow,
setting, debug, stage)]`. `_behind_versions(recorded, current)` now takes the two blocks and
compares them, reading nothing. `_stale_sentence(stage, recorded)` is a function of the stage
and the row's recorded versions and nothing else, so the loop holds its answer in
`sentences[(stage, recorded items)]`.

**The same defect, ten lines down, on the same command.** `_compute_progress` loaded the
setting and opened the environment once per `sample`/`inject` row — `schema.load` plus
`requested_pairs` per row — which is the same wrong logic on the same `ls` call and the reason
`ls` over a sample ledger still cost seconds after the three readers above were fixed. That
request is a function of the setting and the stage, so `_requested_pairs_of` reads it once per
`(workflow, setting, debug, stage)`; `trajectory_record.done_pairs` reads the row's own
directory and stays per row. This function is unchanged since `df3c473`, so it is not a
regression — see decision 2 below.

**Repro.** `/tmp/wave5walk-r2/r5_ls_cost.py` builds N ledger rows of one (workflow, setting,
stage) and runs the flag computation over them with `schema.load` and `schema._parse_module`
counted; `/tmp/wave5walk-r2/r6_ls_end_to_end.py` appends N start rows to a private ledger and
times `run.cmd_ls([])` whole, with `registry.live_sessions` stubbed. Both run against a private
export of the commit under test.

The reviewer's own shape, 40 rows of one (workflow, setting, stage), at `63ed7f9`:

```
$ cd $T && "$PR" /tmp/wave5walk-r2/r5_ls_cost.py $T 40
today's train key of train_probe/ctool_qwen3_0pt6b: 61b4c576b703
rows whose key still matches (behind path): rows=40 schema.load calls=41 module parses=1566 wall clock 5.36 s
    first row: edited=False behind=False stale=''
rows whose key has moved (stale path): rows=40 schema.load calls=41 module parses=1766 wall clock 6.11 s
    first row: edited=True behind=False stale=''
```

at `df3c473`, where the same script measures `_compute_edited`, the one flag that commit has:

```
$ cd $D && "$PR" /tmp/wave5walk-r2/r5_ls_cost.py $D 40
today's train key of train_probe/ctool_qwen3_0pt6b: 61b4c576b703
rows whose key still matches (behind path): rows=40 schema.load calls=1 module parses=32 wall clock 0.11 s
    first row: edited=False
rows whose key has moved (stale path): rows=40 schema.load calls=1 module parses=32 wall clock 0.11 s
    first row: edited=True
```

and at `20aba0a`:

```
$ cd $A && "$PR" /tmp/wave5walk-r2/r5_ls_cost.py $A 40
today's train key of train_probe/ctool_qwen3_0pt6b: 61b4c576b703
rows whose key still matches (behind path): rows=40 schema.load calls=1 module parses=39 wall clock 0.14 s
    first row: edited=False behind=False stale=''
rows whose key has moved (stale path): rows=40 schema.load calls=1 module parses=51 wall clock 0.17 s
    first row: edited=True behind=False stale=''
```

The seven parses above `df3c473`'s 32 are the one `versions_of` the `behind` flag adds, read
once for the whole ledger; the twelve more on the stale path are the one stale sentence.

The failure scenario the finding states — "a ledger of 300 runs costs about 22 s per `run.py
ls`" — end to end, `run.cmd_ls([])` over 300 rows of one setting:

| 300 rows of | `df3c473` | `63ed7f9` | `20aba0a` |
|---|---|---|---|
| `train` | 1 load, 32 parses, 0.14 s | 301 loads, 13206 parses, **44.34 s** | 1 load, 51 parses, **0.21 s** |
| `sample` | 301 loads, 1516 parses, 6.79 s | 601 loads, 11105 parses, **40.66 s** | 2 loads, 45 parses, **1.01 s** |

```
$ cd $B && "$PR" /tmp/wave5walk-r2/r6_ls_end_to_end.py $B train 300      # 63ed7f9
run.py ls over 300 train rows: schema.load calls=301 module parses=13206 wall clock 44.34 s
lines printed: 301
first line: train-000000000000  stage=train  train_probe/ctool_qwen3_0pt6b  status=launching  progress=0/0  rate=-  beat=-  flags=edited  pieces=0:dead@tokyo105:train-000000000000-0

$ cd $A && "$PR" /tmp/wave5walk-r2/r6_ls_end_to_end.py $A train 300      # 20aba0a
run.py ls over 300 train rows: schema.load calls=1 module parses=51 wall clock 0.21 s
lines printed: 301
first line: train-000000000000  stage=train  train_probe/ctool_qwen3_0pt6b  status=launching  progress=0/0  rate=-  beat=-  flags=edited  pieces=0:dead@tokyo105:train-000000000000-0

$ cd $B && "$PR" /tmp/wave5walk-r2/r6_ls_end_to_end.py $B sample 300     # 63ed7f9
run.py ls over 300 sample rows: schema.load calls=601 module parses=11105 wall clock 40.66 s
lines printed: 301
first line: sample-000000000000  stage=sample  baseline/gpt_oss_120b_appworld  status=launching  progress=0/315  rate=-  beat=-  flags=edited  pieces=0:dead@tokyo105:sample-000000000000-0

$ cd $A && "$PR" /tmp/wave5walk-r2/r6_ls_end_to_end.py $A sample 300     # 20aba0a
run.py ls over 300 sample rows: schema.load calls=2 module parses=45 wall clock 1.01 s
lines printed: 301
first line: sample-000000000000  stage=sample  baseline/gpt_oss_120b_appworld  status=launching  progress=0/315  rate=-  beat=-  flags=edited  pieces=0:dead@tokyo105:sample-000000000000-0
```

The 301 printed lines and the first line are the same on both commits. The 1.01 s left on the
sample ledger is `done_pairs` reading 300 run directories, which is per-row work by definition;
the two remaining `schema.load` calls are one for the flags and one for the request.

**Nothing the line carries changed.** Round 1's `r4_ls_line.py` rerun at `20aba0a` prints
round 1's output character for character — the `behind` row, the stale row with its file,
version and `why`, the `pinned` row, the unit, the rate, the heartbeat, the hosts and the cards:

```
$ cd $B && "$PR" /tmp/wave5walk-r2/r4_ls_line.py $B
bumped data/trajectory_record.py to VERSION 2, stale for build alone
sample key unchanged: True
build key moved: True

run_id | stage | workflow/setting | status | progress | rate | heartbeat | flags | pieces
sample-a7d8b62ee953  stage=sample  baseline/gpt_oss_120b_appworld  status=launching  progress=4/315 record  rate=0.0167/s  beat=62s  flags=behind,consumed,split,dirty  pieces=0:healthy@tokyo105:sample-a7d8b62ee953-0; 1:warming up@tokyo106:sample-a7d8b62ee953-1 cards=0,1
build-6d3bf5aff879  stage=build  train_probe/ctool_qwen3_0pt6b  status=ok  progress=0/0  rate=-  beat=-  flags=edited,dirty  pieces=0:warming up@tokyo105  stale=data/trajectory_record.py VERSION 2: "the record now writes the discard block per step, so a dataset built from an older record is not comparable"
inject-34934c81696b  stage=inject  inject/probe_p1_e1_theta_0pt80  status=launching  progress=0/168  rate=-  beat=-  flags=edited,pinned,dirty  pieces=0:warming up@tokyo107:inject-34934c81696b-0 cards=3

sample-a7d8b62ee953 flags: {'edited': False, 'behind': True, 'consumed': True, 'split': True, 'pinned': False, 'dirty': True, 'debug': False, 'orphan': False}
build-6d3bf5aff879 flags: {'edited': True, 'behind': False, 'consumed': False, 'split': False, 'pinned': False, 'dirty': True, 'debug': False, 'orphan': False}
inject-34934c81696b flags: {'edited': True, 'behind': False, 'consumed': False, 'split': False, 'pinned': True, 'dirty': True, 'debug': False, 'orphan': False}
```

---

## WALK-FIX-5 — `eval.theta_from` under a `--debug` walk: the fix is the acceptance command, not `run.py`

**What the finding asks.** The construction plan's section-4 line 3,
`run.py train_probe cgen_qwen3_0pt6b --debug`, refuses at the eval stage, because
`train_probe.yaml` gives `cgen` (and `cparam`) the name form
`eval: {theta_from: train_probe/ctool_qwen3_0pt6b}` and a name form is resolved against the
real root. The finding leaves the owner two options: a fourth pinned override on the acceptance
command, or letting a name-form reference follow the walk's root. **The second option resolves
nothing**, and this is the fact the finding did not have:

**A name form is resolved without the debug overlay before it is located.**
`schema._resolve_name_ref` loads the referenced setting with `debug=False`, so the key it hands
back is the **real** ctool eval key `a4a903bff5de`, while the debug ctool eval run the
acceptance's line 2 produced is `a8b67d485d63`. Pointing that key at the debug root names
`<root>/debug/eval/a4a903bff5de`, a directory that has never existed either. Making the walk
find the debug run would mean keying the reference **with** the overlay, which is
`experimental_settings/schema.py`'s work and is refused twice by the contracts in the same
words: 3.1, "a resolved reference is a different case and passes `debug=False`: a reference is
always keyed and located without the overlay (3.4), so a debug run points at real upstream
directories"; 3.4, "`--debug` applies only to the setting named on the command line and to the
stages of its own workflow. A resolved reference is always keyed without the debug overlay."

**The remedy the errata already chose, applied to the same block's earlier lines.** Errata
"3.4 / 9(c)#8" states the case for `inject.yaml`'s three references and answers it with the
`key:` form of 5.4, and the construction plan's own paragraph under the section-4 block gives
the reason in general terms: "a resolved reference is always keyed without the debug overlay, so
a named reference would point at a real directory that has never existed; the `key:` form of 5.4
pins it instead, `ls` flags the run `pinned`". `eval.theta_from` on lines 3 and 4 of that same
block is that case one workflow earlier. It needs no code: round 1's `_upstream_dirs` resolves a
pinned key under the root the key belongs to, and `eval.theta_from` in the `key:` form carries
one entry (`eval`) and no `method:`, which is what 5.4 and the errata's "5.4 / 2.1" require of
that field.

**Repro.** `/tmp/wave5walk-r2/r7_theta_from_under_debug.py` builds the debug build/train/eval
runs of `ctool_qwen3_0pt6b` and the debug build/train runs of `cgen_qwen3_0pt6b` — what lines 2
and 3 of the acceptance leave on disk — and then asks the three questions.

```
$ cd $A && "$PR" /tmp/wave5walk-r2/r7_theta_from_under_debug.py $A
line 2 of the acceptance left the debug ctool eval at: /tmp/wave5walk-r2/exp-mfoU/outputs/debug/eval/a8b67d485d63
the debug ctool eval key: a8b67d485d63  the real ctool eval key: a4a903bff5de

-- 1. the name form, which is what train_probe.yaml gives cgen --
upstream map: {'train': 'd3fd86ac86e2', 'theta_from.eval': 'a4a903bff5de'}
resolved train: /tmp/wave5walk-r2/exp-mfoU/outputs/debug/train/d3fd86ac86e2 exists=True
resolved theta_from.eval: /tmp/wave5walk-r2/exp-mfoU/outputs/eval/a4a903bff5de exists=False
upstream check: run.py: eval: upstream 'theta_from.eval' at /tmp/wave5walk-r2/exp-mfoU/outputs/eval/a4a903bff5de has no done.json; run it first

-- 2. the same key under the walk's own (debug) root --
that path: /tmp/wave5walk-r2/exp-mfoU/outputs/debug/eval/a4a903bff5de exists= False

-- 3. the key: form of 5.4, pinned on the command line --
run.py reads that command line as: settings=['cgen_qwen3_0pt6b'] debug=True overrides={'eval.theta_from': '{key: {eval: a8b67d485d63}}'}
upstream map: {'train': 'd3fd86ac86e2', 'theta_from.eval': 'a8b67d485d63'}
resolved train: /tmp/wave5walk-r2/exp-mfoU/outputs/debug/train/d3fd86ac86e2 exists=True
resolved theta_from.eval: /tmp/wave5walk-r2/exp-mfoU/outputs/debug/eval/a8b67d485d63 exists=True
upstream check: passed
the cgen eval run this walk writes: /tmp/wave5walk-r2/exp-mfoU/outputs/debug/eval/e6ae01565cd4

-- 4. what the eval stage itself then does with that same pinned key --
probe_eval.py:586 resolves theta_from.eval to: /tmp/wave5walk-r2/exp-mfoU/outputs/eval/a8b67d485d63
that directory has a done.json: False
so the stage raises: /tmp/wave5walk-r2/exp-mfoU/outputs/eval/a8b67d485d63: the referenced classifier eval (theta_from) has no done.json
```

Block 1 is the finding's refusal, reproduced. Block 2 kills the "follow the walk's root" option:
the key itself is the real one, so the debug root holds no such directory. Block 3 is the
remedy, end to end from the command line: `run.py`'s own argv parser reads the override,
the loader takes the pinned form, and the upstream check passes.

**Block 4 is the part the owner has to hear: the command alone is not enough.** Once `run.py`
lets the stage start, `eval/utils/probe_eval.py` resolves the same key itself, and it passes
`debug=False` (line 586 for the `theta_from` eval directory, line 598 for that eval's own train
directory), so the stage raises on the real-root path of a debug key. Block 4 makes that read
verbatim against the fixture. That file is the probe area's, not mine, and neither round of this
wave's fixes has changed those two lines (`git show fix/2026-09-18-wave5-probe:eval/utils/probe_eval.py`
carries `debug=False` on both). **A `--debug` walk of `cgen`/`cparam` therefore needs both**: the
pinned override on the command line, and `probe_eval.py` resolving a pinned key under the root
that key belongs to, the way `run.py._upstream_dirs` does.

**The two lines the owner adds to the section-4 acceptance** (`<KE_ctool_debug>` is
`run.py where train_probe ctool_qwen3_0pt6b eval --debug`, taken after line 2):

```
$PY run.py train_probe cgen_qwen3_0pt6b   --debug "eval.theta_from={key: {eval: <KE_ctool_debug>}}"
$PY run.py train_probe cparam_qwen3_0pt6b --debug "eval.theta_from={key: {eval: <KE_ctool_debug>}}"
```

Pinning moves that walk's own eval key (`e6ae01565cd4` above, against `a46f046c0a9d` for the
unpinned `--debug` cgen in the `C6` sweep), because the eval key folds the resolved
`theta_from.eval` key. That is correct and not a side effect: it is a different run, the cgen
probe evaluated against the debug classifier's theta rather than the real one. The four keys
`inject.yaml`'s own line pins are read off these runs as before.

The plan document and the errata are not mine to edit (`notes/` is the owner's, and the errata
is the planners'), so this is returned as a decision rather than written into either.

---

## Acceptance (round 2)

Run from the worktree root at `20aba0a`;
`$PR = /home/y-guo/reproduce/new1/external/probe-env/bin/python`. Same set as round 1: the
commands that touch `run.py`.

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
$ "$PR" run.py nosuchworkflow x 2>&1 | tail -1; echo "rc=${PIPESTATUS[0]}"
run.py: /home/y-guo/reproduce/new1-wt/2026-09-18-wave5-fix-walk-r2/experimental_settings/nosuchworkflow.yaml does not exist
rc=1
```

**C2 — host normalization and the login-host refusal.**

```
tokyo105 tokyo106
refused: True
rc=0
```

**C3 — the read-only subcommands against the live (empty) registry, no `ssh`.**

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

**D1 — every README entry parses into the five annotations.**

```
31 True
rc=0
```

**D2 — the file count on disk, and the README covering every file that exists** (`train/` has
merged, so the `find` list carries it and the count is 31, as in round 1).

```
$ find run.py constants experimental_settings data models agent eval jobs train -name '*.py' | wc -l
31
$ find ... | while read -r f; do grep -qF "$f" README.md || echo "MISSING $f"; done
(no MISSING line)
```

**D3 — no absolute cluster path in `run.py`.**

```
NO_ABS_PATH
```

**C6 — the sweep, `inject.yaml` included** (`/tmp/wave5walk-r2/c6_sweep.py`, round 1's widened
script: every stage of every workflow, real and `--debug`).

```
$ PYTHONPATH=. "$PR" /tmp/wave5walk-r2/c6_sweep.py
baseline.yaml gpt_oss_120b_appworld real sample=a7d8b62ee953 score=87858c091092
baseline.yaml gpt_oss_120b_appworld debug sample=96de225de2b4 score=20eaad1deae5
train_probe.yaml ctool_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=61b4c576b703 eval=a4a903bff5de
train_probe.yaml ctool_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=79f74a7f74d0 eval=a8b67d485d63
train_probe.yaml cgen_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=df43b5d7c091 eval=56617b259481
train_probe.yaml cgen_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=d3fd86ac86e2 eval=a46f046c0a9d
train_probe.yaml cparam_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=b23d4b289bcc eval=036214306ef8
train_probe.yaml cparam_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=cf4adecfed4f eval=0ed129795cd5
inject.yaml probe_p1_e1_theta_0pt80 real inject=aae002fac6f4 score=01f6905104d2
inject.yaml probe_p1_e1_theta_0pt80 debug inject=0526b23c02b4 score=e0718097e945
inject.yaml no_probe_p1_e1_theta_0pt80 real inject=8ab0cc207990 score=168b9aa8f852
inject.yaml no_probe_p1_e1_theta_0pt80 debug inject=0894c6b1fc6b score=0c2121914267
C6 ok
rc=0
```

Every key is round 1's key: the fix changes no key.

**The pinned-reference repro of round 1, rerun** (`r3_pinned_debug_keys.py`, the `SEAMS-5`
machinery `WALK-FIX-5` leans on):

```
$ cd $A && "$PR" /tmp/wave5walk-r2/r3_pinned_debug_keys.py $A
the three pinned debug keys: 79f74a7f74d0 a8b67d485d63 d3fd86ac86e2
the debug train dir of the ctool probe: /tmp/wave5walk-r2/exp-mTgc/outputs/debug/train/79f74a7f74d0
the real-root path the same key would name: /tmp/wave5walk-r2/exp-mTgc/outputs/train/79f74a7f74d0
that path exists: False

upstream map: {'probe_score.train': '79f74a7f74d0', 'probe_score.eval': 'a8b67d485d63', 'probe_gen.train': 'd3fd86ac86e2'}
resolved probe_score.train: /tmp/wave5walk-r2/exp-mTgc/outputs/debug/train/79f74a7f74d0
resolved probe_score.eval: /tmp/wave5walk-r2/exp-mTgc/outputs/debug/eval/a8b67d485d63
resolved probe_gen.train: /tmp/wave5walk-r2/exp-mTgc/outputs/debug/train/d3fd86ac86e2
upstream check: passed
gate 1 (the pinned methods against the frozen probe.method): passed
gate 2 (the two train runs share a build key): passed
gate 3 (the recorded VERSIONs equal the live source): passed
gate 4 (the temperature read out of the pinned eval report): {'probe_temperature': 1.37}
```

**The one test that touches these files.**

```
$ PYTHONPATH=. "$PR" -m unittest tests.test_registry_concurrent_append
Ran 1 test in 0.199s

OK
$ git status --porcelain
(empty)
```

---

## Decisions the requirements did not make (round 2)

1. **Base.** `63ed7f9`, round 1's head on the same branch, as the dispatch names.
2. **`_compute_progress` is fixed too, although the finding names only `_compute_row_flags`.**
   It carries the identical wrong logic — the setting reloaded once per ledger row — on the
   identical command, and it is the whole remaining cost of `ls` over a sample ledger once the
   named readers are fixed (6.71 s of the 6.79 s a 300-row sample ledger took). It is not a
   round-1 regression: `df3c473` has the same function, which is why the table above shows the
   base at 301 loads for that row set. Fixing one half and leaving the other would have left the
   finding's own failure scenario standing for the most common kind of row.
3. **What is memoised and what is not.** The three readings that are functions of
   (setting, stage) — the setting, its key with its versions block, and its requested pairs —
   are read once; the stale sentence is a function of (stage, the row's recorded versions) and
   is read once per distinct pair. Everything that reads the row's own directory stays per row:
   `done_pairs`, `consumed.json`, `meta.json`'s `split_files`, the frozen `settings.yaml`. Every
   cache is local to the call, so nothing survives into the walk, where a file's version may
   change between two stages of one command.
4. **The sha1 cost of `consumed` and `split` is untouched**, as round 1's decision 11 left it:
   `ls` still hashes every file a run's `consumed.json` and `split_files` name. That is the
   comparison 8.6 describes; short-circuiting it needs a recorded size or mtime beside the sha1,
   which changes what `consumed.json` records and is the owner's.
5. **`WALK-FIX-5` gets no code change.** Stated in full above: the name form is keyed without
   the debug overlay, so the debug root holds no directory under that key either, and keying it
   with the overlay is refused by contracts 3.1 and 3.4 in the same words. The remedy is the
   errata's own device, the `key:` form, on lines 3 and 4 of the section-4 acceptance, and it
   works today with no change to `run.py` (block 3 of the `r7` output). The two ready-to-run
   command lines are above; the plan and the errata are not mine to edit. The command unblocks
   `run.py`'s gate only: the stage then needs `eval/utils/probe_eval.py` to resolve the same
   pinned key under the root it belongs to (block 4, and the first open item below).

## Left for the owner (round 2, seen while fixing)

- **A walk refuses at the stage, not before it.** Line 3 of the section-4 acceptance spends the
  sample, build and train GPU time before the eval stage's upstream check speaks. 5.4 puts the
  check on the stage ("`run.py` refuses to start a stage whose referenced run has no
  `done.json`"), and a chain-wide check up front would refuse a legitimate fresh walk, whose
  later stages' upstream runs do not exist yet. A reference to **another** setting is knowable
  before the first stage starts, so a pre-walk check of the reference fields alone would have
  caught this one for free; that is new behaviour the contracts do not ask for, so it is not in
  this fix.
- **`eval/utils/probe_eval.py` resolves its own referenced directories with `debug=False`** —
  round 1 recorded it, and `WALK-FIX-5` makes it blocking rather than latent: it is the second
  half of what a `--debug` walk of `cgen`/`cparam` needs, shown in block 4 of the `r7` output
  above. Lines 586 and 598 are the two, and the file is the probe area's.
- **Round 1's other open items stand**: 5.4's "a pinned reference skips the shared-build-key
  gate", and `registry.sync()` not folding `stage_extra`.
