# Wave 6 post-merge fix — area "skills"

Branch `fix/2026-09-20-wave6-skills`, base `f810f9f`, head `ae691e4`.
Files touched: `.claude/skills/gpu-run/SKILL.md`,
`.claude/skills/probe-pipeline/SKILL.md`, `.claude/skills/repo-review/SKILL.md`.
No other file changed; no file added, renamed or moved.

Commits, in order:

| sha | subject |
|---|---|
| 64395cb | gpu-run SKILL.md — interpreter, ls flags, launch failure, retry, table |
| 1e74e99 | probe-pipeline SKILL.md — the gate roster and the extension rule |
| 06fb8f0 | repo-review SKILL.md — the third read and the file-list authority |
| 9c89e4a | gpu-run Phase 6a/6b wording, the new paragraphs in reading order |
| ae691e4 | repo-review point 2 names the path-headed sections exactly |

All thirteen findings are fixed; none is declined.

## The interpreter the commands are typed with

`run.py` is `venv: probe` (`run.py:2`, `README.md:63`), and
`constants/path_datasets.yaml:7` maps `probe:` to
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`. Measured on this
base:

```
$ cd /home/y-guo/reproduce/new1 && python3 run.py --help
  File "/home/y-guo/reproduce/new1/run.py", line 19, in <module>
    from data import trajectory_record
  File "/home/y-guo/reproduce/new1/data/__init__.py", line 8, in <module>
    import polars as pl
ModuleNotFoundError: No module named 'polars'

$ /home/y-guo/reproduce/new1/external/probe-env/bin/python run.py --help
usage: run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]
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
```

The absolute path is used rather than `external/probe-env/bin/python`, because
`external/` is git-ignored and does not exist in a worktree (`ls external` in
the fix worktree: `No such file or directory`); the errata already rules that
every command naming this interpreter spells it absolutely
(`.scratch/from-zero/contract-errata.md:126`), and ticket 16's own acceptance
uses that form (`.scratch/from-zero/issues/16-gpu-run-and-probe-pipeline-skills.md:218`).
`README.md:19` carries the same wrong `python3` spelling; it is outside wave 6's
diff and outside this area's scope, and is left for a separate item.

## What each finding got

### GR1 and pipeline-review-skills:W6-L16-1 (critical, one defect)

Nine command lines (`SKILL.md` :38, :66, :75, :106, :120, :145, :154, :156,
:161 on the base) now begin with
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`, and the fixed-paths
block (base :23-24) names that interpreter instead of stating that the machine
has only `python3`. `python3 run.py sampler` inside `## What is gone` is
untouched: it is the retired name the ticket ordered written, and C7/C8 exempt
that section by heading.

### GR4 (important) — a failed launch

Phase 4 now states the success line, that the call exits 0 either way, and what
a failure leaves behind. Read off the code: `run.py:1865-1870` appends a
`launch_failed` finish row and returns `"stop"` with no print, while
`run.py:1871` is the only print and sits on the success branch;
`jobs/launch.py:878-908` calls `teardown_services` before returning
`alive_check` / `service_check`; `jobs/launch.py:955` is that file's only
`print`. The piece log path is `<run_dir>/log/<piece index>.txt`
(`jobs/launch.py:758`).

### GR3 (important) — the `edited` flag

`run.py:476-477` computes `key_matches = current == row.get("key")` then
`edited = not key_matches`, so any edited setting field moves the key.
`_stale_sentence` (`run.py:383-408`) returns a part only when a recorded
module's effective version now exceeds the recorded one, and `_format_ls_row`
appends `stale=` only for a non-empty sentence (`run.py:582-583`). Phase 5 now
says that an `edited` run is one whose current key no longer matches the
directory, and that the `stale=` suffix appears only when a `VERSION` bump was
the cause.

### GR9 (minor) — the verdict set

`jobs/registry.py:658-676` is the six-verdict priority order for `loop`,
`train` and `cpu`; `jobs/registry.py:680-691` `judge_service` runs dead ->
healthy (port) -> suspected stall -> warming up, so `done` and `slowed` cannot
occur for a service piece; `jobs/registry.py:819` gives the synthetic
orphan-session row the verdict `orphan`, and `jobs/registry.py:854-855` picks
the judge by `pv["kind"]`. Phase 5 now carries one sentence for each of those
two cases.

### GR6 and pipeline-review-skills:W6-L16-3 (important, one defect)

`eval/method_table.py:89` is
`groups.setdefault((row["setting"], row["flags"]["debug"]), []).append(row)`,
and `grep -n "parent\|swept" eval/method_table.py` matches only the docstring
line 79. The table's own name is backbone x method x risk
(`eval/method_table.py:71`, `run.py:39`). The Phase 6a sentence now says "one
group per (setting, debug flag) pair — a sweep child's own name, never its
parent" and cites the errata's `5.5 / 8.6` ruling, which supersedes contracts
8.6 on this point (`.scratch/from-zero/contract-errata.md:179`).

### GR5 (important) — what `retry` clears

`_clear_continue_markers` (`run.py:693-707`) unlinks `done.json` and
`consumed.json`, and for `train` also `train_log.jsonl`, `train_done.json`,
`align_check.json` and `last/`; it never touches `records/`. The `sample` /
`inject` resume state is `trajectory_record.done_pairs` over the run
directory's per-pair files, and `run.py:1789-1793` computes `fully_done` from
those, so a complete directory is re-certified through `_finalize_pair_stage`
(`run.py:1814`) rather than sampled again. The Phase 6b bullet is now split by
stage and says exactly that. `run.py` is unchanged: deleting a pair stage's
records would destroy large-model output.

### GR2 (important) — the interrupts cannot reach a smoke

`cmd_kill` (`run.py:641-656`) requires `len(rest) == 3`, `cmd_refire`
(`run.py:660`) parses only `--piece` and `--allow-dirty`, `cmd_retry`
(`run.py:709-710`) only `--allow-dirty`; all three load the setting with
`debug=False` (`run.py:645`, `:675`, `:715`) and key the real run
(`run.py:647-648`). `registry.kill` returns `[]` for a run_id with no open row
and `run.py:656` then prints `run.py kill: ended []`. Phase 6b now states this
and gives the by-hand ending: `ssh <host> tmux kill-session -t <session>` per
piece (contracts 2.3 tears a service piece down that way, and `run.py ls`
prints the host beside the session), then `run.py sync`.

Not done here, and left for the owner: whether `kill` / `refire` / `retry`
should learn `--debug` is a change to contracts 8.6's pinned argv. The approved
fix suggested recording that as an open contract-errata entry; the errata file
is outside this area's scope, so it is raised in this report instead.

### GR10 (minor) — the dirty-tree gate past Phase 3

`run.py --help` lists `--allow-dirty` on `refire` and `retry`;
`run.py:683` (refire) and `run.py:719 -> run.py:1846` (retry) reach the same
`launch.git_state`, and `jobs/launch.py:172-174` is the refusal. Phase 2 now
says the gate guards Phase 4's walk and Phase 6b's two commands, and that every
launch producing a real result is committed first (a refire re-freezes
`_commit` to the commit it cleared, `run.py:687`, contracts 2.3). The flag is
deliberately not added to the two Phase 6b command lines.

### GR7 (minor) — the wrap-up call is a launch

`run.py:1816-1832` returns `"stop"` for `sample` / `inject` only when
`launch.piece_alive` finds a live work piece; otherwise control reaches
`run.py:1834-1858`, which takes the lock, calls `launch.git_state` and
`launch.launch`. Phase 6a now states the general truth — the wrap-up call
starts cards for any stage the walk lands on that is not done, and a completed
stage lets the walk continue into the next one — and points back at the hard
rule that an agent returns the command as `BLOCKED`.

### pipeline-review-skills:W6-L16-4 (minor) — the gate roster

The generator eval holds three gates, not one:
`eval/utils/probe_eval.py:587-589` (the referenced classifier eval has a
`done.json`), `:591-594` (`eval.risk` against the referenced report's
`risk_targets`) and `:602-605` (the shared build key). The dirty-tree gate the
walk takes inside the lock (`run.py:1846`) was also missing. Point 3 now names
all four; the phrase "the generator eval's shared-build-key gate" is replaced,
not supplemented, so no gate is listed twice.

### pipeline-review-skills:W6-L16-7 (minor) — the extension rule

`experimental_settings/schema.py:178-189` is the whole AXES table and carries
no backbone axis; `run.py:1082-1090` expands `{backbone}` over the model
table's rows with `role: probe`; `README.md:358-360` recipe 6 names no
`schema.py` edit. The description now says what body point 6 says: a new axis
value an extension brings is registered before any setting may use it. The body
keeps `README.md` section 3 as the single source for what each extension
touches.

### pipeline-review-skills:W6-L16-5 (minor) — the third read

No README annotation line cites a contracts section: contracts 0.1 fixes the
format at five lines and `README.md:59-63` shows them for `run.py`; of the 43
entries only `README.md:81` mentions a contracts section, and as a rule name.
Point 2 and the description now name a target that exists — the part or
section whose heading carries the file's own path (`# Part 4` at contracts
2786, `# Part 5` at 2980, `# Part 8` at 4325, the format sections `## 1.1`,
`## 1.2`, `## 1.3`, `## 1.4`, `## 1.7`, and the service sections `## 7.1` at
3861 and `## 7.2` at 3950), else the part covering the mechanism — and say that
contracts 0.2 is what `README.md` section 2 is reproduced from
(`README.md:46`), so it is not the section to read there.

### pipeline-review-skills:W6-L16-6 (minor) — the file-list authority

The 2026-09-14 tree document is stale in the recorded ways
(`.scratch/from-zero/contract-errata.md:181`, `:183`): it still carries the
three per-method eval files and the old `agent/` names, 34 files against the
built tree's 31. Point 4 now anchors on the tree as `README.md` section 2
spells it, which is the list `run.py selfcheck` check 1 enforces
(`_check_1` at `run.py:798-806`, fed by `readme_entries(ROOT / "README.md")` at
`run.py:1427`).

## Acceptance, run from the worktree root on head ae691e4

`$PR = /home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**W1**

```
ok-launchmeth
ok-monitormeth
ok-scripts
ok-ppreferences
42 .claude/skills/gpu-run/references/gpu_state.md
Surveyed on: 2026-07-29 (measured, not hearsay).
1
0
```

**W2**

```
ok-exists
2
3
---
name: repo-review
description: >-
  The two-day review: an agent reads the tree against `README.md`'s seven principles
  and writes tasks. It runs `run.py selfcheck` first and stops if that is not green,
  reads `README.md`, then the file under review, then the contracts section that covers
  that file, and writes one ticket per finding into
  `.scratch/review/issues/` in the issue-tracker format — it edits no code and no file
  under `notes/`. Invoke whenever Dungeon♂Master says "review the repo" or a periodic
  tree review is due. Chinese triggers: "审查仓库" / "复盘整棵树" / "两天复盘" / "查一遍仓库".
version: 1.0.0
```

The `2` and `3` are the two `.scratch/review/issues/` mentions and the three
`run.py selfcheck` mentions.

**W3**

```
data/environments/ 1
models/agent_models/ 1
models/probe_models/ 1
train/methods/ 1
```

**W4** — the three front matters print whole; each still ends with its Chinese
trigger clause and none contains "sampler" or "three ledgers". gpu-run:

```
---
name: gpu-run
description: >-
  The sole entry point for running any GPU program inside the new1 project — a
  full-lifecycle pipeline: read the slow-variable log → probe the cards for free ones →
  commit → smoke with `--debug` on the same setting → launch with one `run.py <workflow>
  <setting>` call, which walks that setting's stage list and stops after the launch,
  printing the monitoring command → read progress with `run.py ls` whenever a person
  wants to look → wrap up by re-running the same command, then `run.py table` and a
  commit, or interrupt with `kill` / `refire` / `retry`. Invoke whenever Dungeon♂Master
  says "run", "train", "inference", or any GPU work needs starting in new1. Chinese
  triggers: "跑程序" / "跑实验" / "跑一下" / "发射" / "用显卡跑" / "起个任务".
version: 1.0.0
```

probe-pipeline:

```
---
name: probe-pipeline
description: >-
  The entry point for running or extending new1's probe pipeline: the whole chain from
  sampling trajectories to the eval report is one workflow file's stage list, walked by
  `run.py <workflow> <setting>` (gpu-run handles the mechanics of any GPU stage inside
  it). It is also **the only entry point for extending this pipeline**: a new benchmark
  environment, agent-model family, probe backbone or training method all go through the
  four extension places `README.md` section 3 names, and any new axis value an extension
  brings is registered in `experimental_settings/schema.py` before any setting may use
  it. Invoke whenever Dungeon♂Master says "run the pipeline", or any task needs
  sample/build/train/eval
  chained together or extended. A single GPU task uses gpu-run alone; this skill manages
  the whole chain. Chinese triggers: "跑流水线" / "跑一批探针" / "新数据集跑一遍" / "出矩阵" /
  "换个环境跑" / "加个新模型/新格" / "换个切分方式" / "加一种训练方法".
version: 1.0.0
```

repo-review: as printed under W2 above.
`git diff f810f9f -- .claude/skills | grep -c "^[+-].*[一-龥]"` prints `0`: no
line carrying Chinese changed at all.

**C7, C8 and W5** — the three scripts are the ticket's, run in one `$PR`
invocation over the same file list on the final head:

```
exempt range: [('.claude/skills/gpu-run/SKILL.md', 222, 244)]
C7 ok
named: ['free', 'kill', 'ls', 'refire', 'retry', 'selfcheck', 'sync', 'table', 'train_probe', 'where']
missing: []
C8 ok
W5 ok
EXIT=0
```

Each was also run separately, as the ticket writes it, with the same result:
`C7 ok` / `C7 EXIT=0`, `C8 ok` / `C8 EXIT=0` and `W5 ok` / `W5 EXIT=0`.

**The `## What is gone` heading and section**

```
$ grep -n "^## What is gone$" .claude/skills/gpu-run/SKILL.md
222:## What is gone
$ diff <(git show f810f9f:.claude/skills/gpu-run/SKILL.md | sed -n '/^## What is gone$/,$p') \
       <(sed -n '/^## What is gone$/,$p' .claude/skills/gpu-run/SKILL.md) && echo IDENTICAL
IDENTICAL
```

## Every command form in the three skills, against run.py's argument handling

Checked by reading `run.py`'s parsers; nothing was launched, and no walk, kill,
refire or retry ran.

| form, as the skills write it | handler | parse |
|---|---|---|
| `run.py free` | `cmd_free`, `run.py:740` | takes `rest` and reads nothing from it |
| `run.py <workflow> <setting> --debug [--allow-dirty]` | `cmd_walk`, `run.py:1489`, via `main`'s fall-through `run.py:1918` | `_parse_walk_rest` splits settings, `--debug`, `--allow-dirty`, `section.field=value` |
| `run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]` | same | the usage line `run.py --help` prints, verbatim |
| `run.py ls [workflow] [--debug]` | `cmd_ls`, `run.py:587` | `--debug` by membership, the first other token is the workflow |
| `run.py ls <workflow> --debug` | same | same |
| `run.py table [workflow] [--debug]` | `cmd_table`, `run.py:723` | `--out`, `--debug`, one positional |
| `run.py kill <workflow> <setting> <stage>` | `cmd_kill`, `run.py:641` | requires exactly three positionals |
| `run.py refire <workflow> <setting> <stage> --piece i` | `cmd_refire`, `run.py:660` | `--piece i`, `--allow-dirty`, three positionals |
| `run.py retry <workflow> <setting> <stage>` | `cmd_retry`, `run.py:709` | `--allow-dirty`, three positionals |
| `run.py sync` | `cmd_sync`, `run.py:746` | takes `rest` and reads nothing from it |
| `run.py where <workflow> <setting> <stage>` | `cmd_where`, `run.py:609` | `--debug`, three positionals |
| `run.py selfcheck` | `cmd_selfcheck`, `run.py:1426` | takes `rest` and reads nothing from it |
| `run.py train_probe <setting>` | `cmd_walk`, `run.py:1489` | `experimental_settings/train_probe.yaml` exists |

`main` (`run.py:1908-1919`) dispatches the ten names in `_SUBCOMMANDS`
(`run.py:1894-1905`) and sends every other first word to `cmd_walk`, so each
form above reaches the handler named.

## For the owner

1. `README.md:19` spells the launch command `python3 run.py <workflow> ...`,
   which the system `python3` cannot run. It is pre-existing (wave 5, ticket
   14) and outside wave 6's diff, so it is not fixed here.
2. `kill`, `refire` and `retry` cannot address a `--debug` run at all. The
   skill now tells the operator to end a smoke by hand; whether the three
   subcommands should take `--debug` is a change to contracts 8.6's pinned
   argv, and belongs in a contract-errata entry that this area's scope does not
   cover.
3. Three ticket-16 spec rows carry the same wrong premises the skills carried,
   and a re-run of the ticket would reintroduce them:
   `.scratch/from-zero/issues/16-gpu-run-and-probe-pipeline-skills.md:47` (the
   `edited` flag as a `VERSION` bump), `:185-187` (the contracts section an
   annotation line cites) and `:199` (the tree's Part 1 as the file-list
   authority). The ticket is outside this area's scope and is left as it is.

## Fix round 1

Base `ae691e4`, head `687b685`, one commit:

| sha | subject |
|---|---|
| 687b685 | gpu-run splits the two failed-launch shapes and both interrupt branches |

Both re-review findings are real and fixed; none is declined. Only
`.claude/skills/gpu-run/SKILL.md` changed.

### rereview-skills-r1:P1 (important) — a failed launch has two shapes

Read off the code on this base:

- `jobs/launch.py:704` is `launch()`. It leaves through `sys.exit(<string>)` on
  the launch gate (`jobs/launch.py:743`), on a host with too few free cards
  (`:779`, `:795`, `:820`, message built by `_no_cards_message` at `:558-563`),
  and on a service endpoint file that never appeared (`_wait_for_endpoint`,
  `:672`). The dirty-tree refusal Phase 2 describes is the same shape
  (`jobs/launch.py:174`). `sys.exit` with a string writes it to stderr and
  exits 1.
- `registry.append_start(start_row)` is at `jobs/launch.py:857`, after the
  piece-placement loop and after the gate refusal, so on those paths no start
  row exists, `run.py:1865-1869` is never reached, and the `ls` line and
  `<run_dir>/log/<piece index>.txt` are both absent.
- The `outcome != "up"` branch (`run.py:1865-1869`, the only `launch_failed`
  writer) is reached when `launch()` returns `alive_check` or `service_check`
  after `teardown_services` (`jobs/launch.py:878-908`); `run.py:1871` is the
  success print. The piece log path is `<run_dir>/log/<piece index>.txt`
  (`jobs/launch.py:758`).

So the old paragraph's three claims — exit 0 either way, no line printed, the
`check` client as the only writer to the terminal — were false for the refusal
paths, which are the common way a launch fails. Phase 4 now names the two
shapes separately: `jobs/launch.py` refusing before the start row (its own
printed line is the diagnosis, no registry row, nothing in `ls`, no piece log),
and a piece failing its alive check (nothing further printed, exit 0, service
pieces torn down, `launch_failed` finish row, piece log to read).

### rereview-skills-r1:P2 (minor) — `kill` on a smoke has two outcomes

`registry.kill` returns `[]` only when the folded ledger holds no start row for
that `run_id` (`jobs/registry.py:1012-1014`); every other piece path ends the
recorded sessions (`jobs/registry.py:1031-1037`). With a real run at that key,
`cmd_kill` (`run.py:641-657`) ends its pieces and appends its `killed` finish
row (`run.py:651-655`), `cmd_refire` (`run.py:660-690`) restarts one of its
pieces, and `cmd_retry` (`run.py:709-720`) clears that run's markers
(`_clear_continue_markers`, `run.py:693-707`) and launches it again. The Phase
6b bullet now writes both branches: the real run at that key is acted on, and
with the smoke as the only run of that setting and stage `kill` prints
`ended []` and stops nothing. The by-hand ending of a smoke is unchanged.

### Acceptance, run from the worktree root on head 687b685

`$PR = /home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**W1**

```
ok-launchmeth
ok-monitormeth
ok-scripts
ok-ppreferences
42 .claude/skills/gpu-run/references/gpu_state.md
Surveyed on: 2026-07-29 (measured, not hearsay).
1
0
```

**W2**

```
ok-exists
2
3
---
name: repo-review
description: >-
  The two-day review: an agent reads the tree against `README.md`'s seven principles
  and writes tasks. It runs `run.py selfcheck` first and stops if that is not green,
  reads `README.md`, then the file under review, then the contracts section that covers
  that file, and writes one ticket per finding into
  `.scratch/review/issues/` in the issue-tracker format — it edits no code and no file
  under `notes/`. Invoke whenever Dungeon♂Master says "review the repo" or a periodic
  tree review is due. Chinese triggers: "审查仓库" / "复盘整棵树" / "两天复盘" / "查一遍仓库".
version: 1.0.0
```

**W3**

```
data/environments/ 1
models/agent_models/ 1
models/probe_models/ 1
train/methods/ 1
```

**W4** — the three front matters print whole, each still ending in its Chinese
trigger clause, none carrying "sampler" or "three ledgers". gpu-run:

```
---
name: gpu-run
description: >-
  The sole entry point for running any GPU program inside the new1 project — a
  full-lifecycle pipeline: read the slow-variable log → probe the cards for free ones →
  commit → smoke with `--debug` on the same setting → launch with one `run.py <workflow>
  <setting>` call, which walks that setting's stage list and stops after the launch,
  printing the monitoring command → read progress with `run.py ls` whenever a person
  wants to look → wrap up by re-running the same command, then `run.py table` and a
  commit, or interrupt with `kill` / `refire` / `retry`. Invoke whenever Dungeon♂Master
  says "run", "train", "inference", or any GPU work needs starting in new1. Chinese
  triggers: "跑程序" / "跑实验" / "跑一下" / "发射" / "用显卡跑" / "起个任务".
version: 1.0.0
```

probe-pipeline and repo-review print exactly as they do in this report's first
round; `git diff f810f9f -- .claude/skills | grep -c "^[+-].*[一-龥]"` still
prints `0`.

**C7, C8 and W5**, the ticket's three scripts in one `$PR` invocation over the
same file list:

```
exempt range: [('.claude/skills/gpu-run/SKILL.md', 230, 252)]
C7 ok
named: ['free', 'kill', 'ls', 'refire', 'retry', 'selfcheck', 'sync', 'table', 'train_probe', 'where']
missing: []
C8 ok
W5 ok
EXIT=0
```

**The `## What is gone` heading and section**

```
$ grep -n "^## What is gone$" .claude/skills/gpu-run/SKILL.md
230:## What is gone
$ diff <(git show f810f9f:.claude/skills/gpu-run/SKILL.md | sed -n '/^## What is gone$/,$p') \
       <(sed -n '/^## What is gone$/,$p' .claude/skills/gpu-run/SKILL.md) && echo IDENTICAL
IDENTICAL
```

The section moved from line 222 to line 230 because Phase 4's paragraph and the
Phase 6b bullet each grew, and its text is byte-identical to `f810f9f`.

**Every command form, re-extracted after this round.** The set of backticked
`run.py ...` forms in the three skills is unchanged from the first round's
table — this round added no command line — so each form still reaches the
handler that table names, through `main`'s dispatch over `_SUBCOMMANDS`
(`run.py:1894-1905`, `run.py:1908-1919`). Nothing was launched; no walk, kill,
refire or retry ran.

## Fix round 2

Base `687b685`, head `c17d75c`, one commit:

| sha | subject |
|---|---|
| c17d75c | the endpoint timeout is its own launch-failure shape |

Two of the three re-review findings are real and fixed; the third is fixed for
the reason it gives, with its conclusion unchanged. None is declined. Only
`.claude/skills/gpu-run/SKILL.md` and `.claude/skills/repo-review/SKILL.md`
changed.

### skills-r2:GR4-endpoint-shape-false (important) — the endpoint timeout is not a refusal

Read off the code on this base:

- `_wait_for_endpoint` (`jobs/launch.py:664-672`) ends in
  `sys.exit(f"jobs/launch.py: {path} did not appear within launch_timeout_s")`
  at `jobs/launch.py:672`, and its one call site is `jobs/launch.py:894`, inside
  `launch()` under `if stage == "inject":` (`jobs/launch.py:892`).
- By line 894 the start row is already appended:
  `registry.append_start(start_row)` at `jobs/launch.py:857` with
  `"status": "launching"` (`jobs/launch.py:855`); `meta.json` with the pieces is
  written at `jobs/launch.py:864-868`; the lock block ends at
  `jobs/launch.py:868`; `_ensure_log_dir(run_dir)` runs at `jobs/launch.py:871`;
  the service pieces are started at `jobs/launch.py:885-886` and pass their
  alive check at `jobs/launch.py:887-890`.
- Every other failure path in `launch()` tears the services down first
  (`jobs/launch.py:878`, `:889`, `:900`, `:907`, each `teardown_services(run_dir)`
  before the return). The `sys.exit` at `jobs/launch.py:672` tears nothing down.
- The launch gate then refuses a second launch of the same key while the row is
  younger than `launch_timeout_s` and no piece has beaten
  (`jobs/launch.py:251-265`).

So the old sentence was false on every clause for this case, and it was the one
case whose advice left cards held. Phase 4 now reads "one of three shapes": the
three pre-start-row refusals keep their clause, and the endpoint timeout has its
own — start row written, service pieces up, an open `launching` row in Phase 5's
`ls`, the piece logs under `<run_dir>/log/`, and Phase 6b's `kill` as the way to
end the live pieces. `kill` reaches them: `registry.kill` reads the pieces from
`meta.json` (`jobs/registry.py:1003-1021`), which `jobs/launch.py:864` wrote.

### skills-r2:GR4-two-shapes-excludes-service-check (minor) — the check client writes to the terminal

`jobs/launch.py:895-898` runs the probe service's `check` client with
`subprocess.run([...], cwd=str(_repo_root()))` and no capture, so its own lines
reach the terminal (`models/probe_models/service.py:212`, `:220`, `:226`,
`:230`, `:242`, `:253`, `:254`, `:261`, all `print(f"check: ...")`). On
`rc != 0` it tears the services down and returns `"service_check"`
(`jobs/launch.py:899-901`), which `run.py:1865-1870` turns into the same
`launch_failed` finish row and `return "stop"` with no print; `run.py:1871` is
the success branch. That path belongs to the quiet shape, so the quiet shape now
names the `check` client as the one writer to the terminal on it, instead of
claiming nothing further is printed.

### skills-r2:W6-L16-5-contracts-0.2-equivalence (minor) — 0.2 is the stale predecessor

Within contracts 0.2 (`notes/plans/2026-09-17-contracts.md:119-641`, the section
running from `## 0.2 The tree` at line 119 to `## 0.3 The count` at line 642)
the annotation lines still name `eval/methods/cgen.py`, `eval/methods/cparam.py`
and the old `agent/loop.py`, `agent/generate.py`, `agent/inject.py`. `README.md`
section 2 (`README.md:44-322`) carries none of those names: it spells
`eval/utils/probe_eval.py` (`README.md:278`), `agent/run_tasks.py` and
`agent/step_with_probe.py` (`README.md:108`), and `README.md:46-47` says its copy
is "reconciled against the lines each ticket landed and against
`.scratch/from-zero/contract-errata.md`". The errata records both rewrites as
deliberately not carried into `notes/`
(`.scratch/from-zero/contract-errata.md:181` for the `eval/methods/` fold, `:183`
for the four `agent/` renames). Point 2 now gives that as the reason 0.2 is not
the section to read; the conclusion is unchanged, and point 4's anchor on
`README.md` section 2 is now consistent with it.

### Acceptance, run from the worktree root on head c17d75c

`$PR = /home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**W1**

```
ok-launchmeth
ok-monitormeth
ok-scripts
ok-ppreferences
42 .claude/skills/gpu-run/references/gpu_state.md
Surveyed on: 2026-07-29 (measured, not hearsay).
1
0
```

**W2**

```
ok-exists
2
3
---
name: repo-review
description: >-
  The two-day review: an agent reads the tree against `README.md`'s seven principles
  and writes tasks. It runs `run.py selfcheck` first and stops if that is not green,
  reads `README.md`, then the file under review, then the contracts section that covers
  that file, and writes one ticket per finding into
  `.scratch/review/issues/` in the issue-tracker format — it edits no code and no file
  under `notes/`. Invoke whenever Dungeon♂Master says "review the repo" or a periodic
  tree review is due. Chinese triggers: "审查仓库" / "复盘整棵树" / "两天复盘" / "查一遍仓库".
version: 1.0.0
```

**W3**

```
data/environments/ 1
models/agent_models/ 1
models/probe_models/ 1
train/methods/ 1
```

**W4** — the three front matters print whole, each still ending in its Chinese
trigger clause, none carrying "sampler" or "three ledgers". gpu-run:

```
---
name: gpu-run
description: >-
  The sole entry point for running any GPU program inside the new1 project — a
  full-lifecycle pipeline: read the slow-variable log → probe the cards for free ones →
  commit → smoke with `--debug` on the same setting → launch with one `run.py <workflow>
  <setting>` call, which walks that setting's stage list and stops after the launch,
  printing the monitoring command → read progress with `run.py ls` whenever a person
  wants to look → wrap up by re-running the same command, then `run.py table` and a
  commit, or interrupt with `kill` / `refire` / `retry`. Invoke whenever Dungeon♂Master
  says "run", "train", "inference", or any GPU work needs starting in new1. Chinese
  triggers: "跑程序" / "跑实验" / "跑一下" / "发射" / "用显卡跑" / "起个任务".
version: 1.0.0
```

probe-pipeline:

```
---
name: probe-pipeline
description: >-
  The entry point for running or extending new1's probe pipeline: the whole chain from
  sampling trajectories to the eval report is one workflow file's stage list, walked by
  `run.py <workflow> <setting>` (gpu-run handles the mechanics of any GPU stage inside
  it). It is also **the only entry point for extending this pipeline**: a new benchmark
  environment, agent-model family, probe backbone or training method all go through the
  four extension places `README.md` section 3 names, and any new axis value an extension
  brings is registered in `experimental_settings/schema.py` before any setting may use
  it. Invoke whenever Dungeon♂Master says "run the pipeline", or any task needs
  sample/build/train/eval
  chained together or extended. A single GPU task uses gpu-run alone; this skill manages
  the whole chain. Chinese triggers: "跑流水线" / "跑一批探针" / "新数据集跑一遍" / "出矩阵" /
  "换个环境跑" / "加个新模型/新格" / "换个切分方式" / "加一种训练方法".
version: 1.0.0
```

repo-review: as printed under W2 above.
`git diff f810f9f -- .claude/skills | grep -c "^[+-].*[一-龥]"` prints `0`: no
line carrying Chinese changed at all.

**C7, C8 and W5**, the ticket's three scripts in one `$PR` invocation over the
same file list:

```
exempt range: [('.claude/skills/gpu-run/SKILL.md', 236, 258)]
C7 ok
named: ['free', 'kill', 'ls', 'refire', 'retry', 'selfcheck', 'sync', 'table', 'train_probe', 'where']
missing: []
C8 ok
W5 ok
EXIT=0
```

Each was also run separately, as the ticket writes it, with the same result:
`C7 ok` / `C7 EXIT=0`, `C8 ok` / `C8 EXIT=0` and `W5 ok` / `W5 EXIT=0`.

**The `## What is gone` heading and section**

```
$ grep -n "^## What is gone$" .claude/skills/gpu-run/SKILL.md
236:## What is gone
$ diff <(git show f810f9f:.claude/skills/gpu-run/SKILL.md | sed -n '/^## What is gone$/,$p') \
       <(sed -n '/^## What is gone$/,$p' .claude/skills/gpu-run/SKILL.md) && echo IDENTICAL
IDENTICAL
```

The section sits at line 236, six lines below round 1's 230, because Phase 4's
paragraph grew by six lines; its text is byte-identical to `f810f9f`.

**Every command form, re-extracted after this round.** The set of backticked
`run.py ...` forms in the three skills is byte-identical to round 1's — this
round added and removed no command line, checked with
`diff <(git show 687b685:... | grep -o 'run\.py ...') <(grep -o ... )`, which
prints nothing. Re-read off the code on this base: `main` (`run.py:1908-1919`)
sends `argv[0]` to `_SUBCOMMANDS` (`run.py:1894-1905`: `ls`, `where`, `find`,
`kill`, `refire`, `retry`, `table`, `free`, `sync`, `selfcheck`) and every other
first word to `cmd_walk` (`run.py:1489`), so `run.py train_probe <setting>`
walks. `cmd_ls` (`run.py:587-589`) takes `--debug` by membership and the first
other token as the workflow; `cmd_where` (`run.py:609-614`) takes `--debug` and
exactly three positionals; `cmd_kill` (`run.py:641-643`) exactly three tokens;
`cmd_refire` (`run.py:660-666`) `--piece i`, `--allow-dirty` and three
positionals; `cmd_retry` (`run.py:709-714`) `--allow-dirty` and three
positionals; `cmd_table` (`run.py:723-730`) `--out`, `--debug` and one
positional; `cmd_free` (`run.py:740`), `cmd_sync` (`run.py:746`) and
`cmd_selfcheck` (`run.py:1426`) read nothing from `rest`;
`_parse_walk_rest` (`run.py:1469-1476`) splits settings, `--debug`,
`--allow-dirty` and `section.field=value`. Nothing was launched; no walk, kill,
refire or retry ran.
