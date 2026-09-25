# Repo test of 2026-09-25

Scheduled by gyb on 2026-09-24 20:56 UTC, fired 2026-09-25 01:11 UTC. Every time below is UTC
unless it is quoted from a registry row written on shiga (those carry JST, see finding O8).

State at fire time: branch `from-zero`, HEAD `f2d87ea`, tree clean, `run.py selfcheck` 31 files
0 problems, `run.py ls` prints "no runs" (every registry row was a debug row, and `ls` hides debug
rows by default; the ledger held 152 rows, 47 run ids, all from 2026-09-20 to 09-22). This
session runs on `yebis` (10.88.2.32, outside the cluster network, reaching the tokyo hosts
through an ssh ProxyCommand chain); `constants/path_outputs.yaml` says `login_host: shiga`.
Free cards at 01:12: tokyo105 1-7, tokyo106 0-9, tokyo107 0-3, tokyo108 0, 1, 4, 5.

Agents: one opus matrix reader, one opus setting-fragility assessor, one opus CPU runner
(phase 1-2); 24 opus refuters, three per cluster over eight clusters (phase 3); four opus
implementers in their own worktrees, each with an opus reviewer and a fix loop (phase 4). The
main conversation launched every GPU walk through the gpu-run skill. Every GPU walk was
`--debug --allow-dirty`.

## 1. Facts: what ran and what happened

### 1.1 Full workflows (matrix item 1)

| time | command (host) | outcome |
|---|---|---|
| 01:12 | `run.py train_probe ctool_qwen3_0pt6b --debug --allow-dirty --cards tokyo108:4` (yebis) | no launch: sample `96de225de2b4`, build `b565f5ab1b94`, train `bd4a5dcf5629` reused as finished; `eval-5f5a8f4f96f6` computed in place (26 items, rows at 01:14); the walk printed heartbeat lines only, rc 0 |
| 01:41 | `run.py baseline gpt_oss_120b_appworld --debug --allow-dirty` (yebis) | sample `96de225de2b4` reused (the same directory train_probe uses: the sample key folds no workflow name); `score-20eaad1deae5` recomputed (rows at 01:41); output empty, rc 0 |
| 01:20 | `run.py inject probe_p1_e1_theta_0pt80 --debug --allow-dirty --cards tokyo108:5 --cards tokyo105:2` (yebis) | agent service up on tokyo108:5 at 01:24:30, probe service up on shiga:8501 at 01:20:46, both endpoint files carried `base_url`; the loop piece never started; the launch polled for 1800 s and ended `run.py: inject-583c0e97913c: launch returned alive_check; ended ['inject-583c0e97913c-1', 'inject-583c0e97913c-2']` (rc 0, `launch_failed` row at 01:50, cards released) — finding X |
| 01:56 | the same command over `ssh tokyo105` | check client passed (`/render`, `/score conf 0.177`, `/gen`); `run.py: launched inject-583c0e97913c`; 3/3 tasks by 01:58; the loop ended the services |
| 01:59 | the same command over ssh (wrap-up) | finish row ok (elapsed 458.9 s); `score-4586e0cdeba8` ok (`success 0.0, base_success 0.0, delta_success 0.0, n_records 3`) |
| 01:59 | `run.py inject no_probe_p1_e1_theta_0pt80 --debug --allow-dirty --cards tokyo108:4 --cards tokyo105:3` (ssh tokyo105) | the probe arm's server had already ended, so no attach: agent service started on tokyo108:4, probe service on tokyo105:3; `launched inject-210ff860f998`; 3/3 tasks by 02:05 |
| 02:06 | the same command over ssh (wrap-up) | `inject-210ff860f998` ok, `score-ecd526d476c3` ok |

Each stage of each run has its run directory, `meta.json`, heartbeat file, `done.json` (or the
per-pair records for sample/inject), a start row and a finish row in `jobs/runs.jsonl`, and a
`run.py ls --debug` line; the ls lines are quoted in `scratchpad` logs and in section 1.4.

References under `--debug` resolve to debug runs: `inject probe_p1_e1_theta_0pt80` resolved
`probe_score` to train `bd4a5dcf5629` and eval `5f5a8f4f96f6`, `probe_gen` to train
`94cbec080c4b`, `score.baseline` to sample `96de225de2b4`, all under `outputs/debug/` (the
matrix reader's read-only script `scratchpad/upstreams.py`; code at schema.py `_resolve_name_ref`).

### 1.2 A fresh chain through a command-line override, one stage at a time (items 1, 2, 3)

| time | command (yebis) | outcome |
|---|---|---|
| 01:18 | `run.py train_probe ctool_qwen3_0pt6b --debug --allow-dirty --cards tokyo108:4 sample.max_steps=5` | sample `22be0dad52f2` reused (a 2026-09-20 run whose frozen diff already held `sample.max_steps: 5`); `build-55cd38c24455` ran in place (9 rows); `train-602051218152` launched on tokyo108:4 (`run.py: launched ...`), done at 01:19:56 (2/2 steps) |
| 01:20 | the same command | train finish row ok; `eval-661699fd40e4` computed (26 items) |
| 01:23 | `run.py train_probe cgen_qwen3_0pt6b cparam_qwen3_0pt6b --debug --allow-dirty --cards tokyo108:0,1 sample.max_steps=5` | two launches from one pool in one call: `launched train-b4a83a32b921` (card 0), `launched train-f46997fdbf8d` (card 1); both share build `55cd38c24455` |
| 01:43 | the same command (wrap-up) | both train finish rows ok; `eval-0c15d71d5727` and `eval-b27cc9c67906` FAILED: `ValueError: the referenced classifier eval's train run has build key 'b565f5ab1b94', this eval's own train run has build key '55cd38c24455'` (probe_eval.py:680); the walk printed the traceback and exited 0 — finding O6 |

`run.py where` refused the override (`run.py where: usage: ...`), so the keys above were read
from the run directories after the fact (B2, by design per the refuters).

### 1.3 A specific stage: re-walk, retry, kill, refire (item 2)

| time | command (yebis) | outcome |
|---|---|---|
| 01:42 | `run.py retry train_probe ctool_qwen3_0pt6b eval --debug --allow-dirty` | eval recomputed (rows at 01:42), output empty, rc 0 |
| 02:01 | `run.py retry train_probe cparam_qwen3_0pt6b train --debug --allow-dirty --cards tokyo108:1` | markers cleared, `launched train-a956d422f5a0`; 2/2 steps by 02:02 |
| 02:03 | `run.py kill train_probe cparam_qwen3_0pt6b train --debug` | `run.py kill: ended ['train-a956d422f5a0-0']`; killed row; session gone |
| 02:04 | `run.py refire train_probe cparam_qwen3_0pt6b train --piece 0 --debug --allow-dirty --cards tokyo108:1` | warned `piece 0 already has 2 launch entries`, restarted; the piece died at once: `train_log.jsonl: already exists, this run directory has already been trained once and its train_log.jsonl would mix two runs; run.py retry to start fresh` — finding O10 |
| 02:07 | retry again | refused: `jobs/launch.py: refusing to launch: run_id 'train-a956d422f5a0' started 240s ago, within launch_timeout_s` |
| 02:08 | kill, then retry again | kill closed it; `launched train-a956d422f5a0`; finished 02:20 |
| 02:47 | `run.py train_probe cparam_qwen3_0pt6b --debug --allow-dirty --cards tokyo108:1` (merged code) | `run.py: reused sample-96de225de2b4 (...)`, `reused build-b565f5ab1b94`, `reused train-a956d422f5a0`, `run.py: eval-f3f1719bd3a3 ok; report .../eval/f3f1719bd3a3/report.md` |

What the code offers for one stage (matrix reader, file:line in `scratchpad/phase12.json`):
the walk skips finished stages (sample/inject by their per-pair records and a certifying
`done.json`, build/train by `done.json`) and always recomputes eval and score, so a re-walk
after the upstream is finished runs the next unfinished stage; `retry` is the only command that
runs exactly one stage (it clears the markers first, then calls the walk's stage step once);
`refire` restarts one dead loop or train piece; there is no command that runs a middle CPU
stage alone while keeping the later ones.

### 1.4 Error paths (item 5), before the fixes, 01:40-01:41

| case | command | rc | one output line |
|---|---|---|---|
| unknown workflow | `run.py nope ctool_qwen3_0pt6b --debug --allow-dirty` | 1 | `run.py: .../experimental_settings/nope.yaml does not exist` |
| unknown setting | `run.py train_probe nope --allow-dirty` | 1 | `run.py: nope: no such setting in .../train_probe.yaml` |
| unknown stage in retry | `run.py retry train_probe ctool_qwen3_0pt6b nope --debug --allow-dirty` | 1 | `run.py: 'nope' is not a stage; one of [...]` |
| unknown field | `... train.nope=1` | 1 | `run.py: train.nope: not a field of the schema` |
| field of a section the workflow lacks | `run.py baseline gpt_oss_120b_appworld --debug --allow-dirty train.lr=0.001` | 1 | `run.py: train.lr: not a field of the schema` (false text; fixed, B3) |
| bad axis value | `... probe.method=nope` | 1 | `run.py: probe.method: 'nope' is not one of ('ctool', 'cgen', 'cparam')` |
| sweep child of a setting with no sweep | `run.py train_probe ctool_qwen3_0pt6b/train.lr=0.0003 --debug --allow-dirty` | 1 | `run.py: ctool_qwen3_0pt6b/train.lr=0.0003: no such child of ctool_qwen3_0pt6b` |
| pinned ref to a run that does not exist | `... 'inject.probe_score={key: {train: 000000000000, eval: 000000000000}, method: ctool}'` | 1 | TRACEBACK `schema.py:1389 ... TypeError: unsupported operand type(s) for /: 'PosixPath' and 'int'` (fixed, B5) |
| nested override | `... train.predict=5` | 1 | TRACEBACK `schema.py:724 ... TypeError: 'int' object is not subscriptable` (fixed, B4) |
| dirty tree without --allow-dirty | untracked `dirty_probe.txt`, then `run.py train_probe ctool_qwen3_0pt6b --debug` | 1 | `jobs/launch.py: refusing a dirty working tree without --allow-dirty: dirty_probe.txt` |
| busy card | `... train.lr=0.0002 --cards tokyo108:2` | 1 | `jobs/launch.py: --cards names card(s) that are not free: tokyo108:2` |
| too-small card | `run.py baseline ... sample.max_steps=3 --cards tokyo106:0` | 1 | `jobs/launch.py: --cards names card(s) smaller than the 93 GiB this piece needs: tokyo106:0 (47 GiB)` |
| refire without --piece | `run.py refire train_probe ctool_qwen3_0pt6b train --debug --allow-dirty` | 1 | `jobs/launch.py refire: no piece None recorded in .../train/bd4a5dcf5629/meta.json` (fixed, A2/A3) |
| wrong --cards syntax | `... --cards tokyo108:5 tokyo105:2` | 1 | `jobs/launch.py: no host has 1 free card(s) of at least 0 GiB; probed tokyo108:0 free` (`tokyo105:2` was taken as a second setting name and never validated; fixed, C1) |
| where with an override | `run.py where train_probe ctool_qwen3_0pt6b sample --debug sample.max_steps=5` | 1 | `run.py where: usage: run.py where <workflow> <setting> <stage> [--debug]` (by design, B2) |
| where on a stage outside the workflow | `run.py where baseline gpt_oss_120b_appworld train --debug` | 1 | TRACEBACK `schema.py:1240 _substitute ... AttributeError: 'NoneType' object has no attribute 'method'` (fixed, B1) |

### 1.5 CPU commands (item 6)

`run.py selfcheck` 31 files 0 problems; `tests/test_registry_concurrent_append.py` 7 tests OK
and `tests/test_packed_loss.py` 3 tests OK, each in its own process, no fixture row reached
`jobs/runs.jsonl`; `run.py table` prints the empty non-debug matrix and `run.py table --debug`
six rows; `run.py sync` printed `0 run(s): []`; `run.py free` 13.7 s; `run.py find
probe.method=ctool` printed `no runs match` while ctool train rows exist (H1, by design: find
matches the frozen diff, which omits defaults). The runner's 19 CPU commands: 18 pass, 1
skipped (depended on GPU walks), 1 held (`run.py sync` while other runs were open); its full
table is `scratchpad/phase12.json`.

### 1.6 The acceptance run of the merged fixes

On the merged tree (HEAD `72aa81c`): selfcheck 0 problems, both tests OK, the 36 `run.py where`
lines (six settings, every stage, both debug flags) name the same 26 keys as before the fixes.
Every case of 1.4 that ended in a traceback or a false text now ends in one refusal line:
`run.py: 'train' is not a stage of baseline/gpt_oss_120b_appworld, whose workflow is ['sample',
'score']`; `run.py: train.lr: no stage of this file's workflow reads this section`; `run.py:
train.predict: expected a mapping, got int`; `run.py: inject.probe_score: pinned key stage train:
0 is not a 12-hex key (quote it in YAML when it is all digits)`; `run.py: tokyo105:2: no such
setting in .../inject.yaml`; `run.py: inject.theta: 1.5 is outside [0, 1], the range of the probe
confidence it is compared with`; `run.py: build.max_cuts: no stage of this file's workflow reads
this section`; `jobs/launch.py refire: .../train/bd4a5dcf5629 is finished (done.json present,
written by its newest launch); piece 0 is done, not dead; run.py retry ... starts it fresh`.
The end-to-end check of finding X's fix (an inject launch typed on yebis) is recorded in
section 6.

## 2. Findings

Thirty-one claims from the readers and the runner went through three opus refuters each (the
contracts lens, the reproduction lens, the root-cause lens); none was refuted: 10 defects, 15
gaps (the contracts are silent and a person is misled), 6 by design. The votes with evidence,
root cause and fix sketch per claim are in `scratchpad/phase3.json`. Five more findings are the
main conversation's own (X, O6, O8, O9, O10).

### 2.1 Fixed (commits on `from-zero`, `f2d87ea..72aa81c`)

| id | what was wrong | fix | commit |
|---|---|---|---|
| X (high) | a service port was probed, and the probe-service check client run, from wherever run.py ran; from yebis both fail, the alive check polls for 1800 s and `ls` reads every service as warming up | the port is probed on its own host (in place, or over ssh, fail-closed); the check client runs on `login_host` through the loop pieces' remote path; `ls` probes a service port only when its verdict reads it | 939dc1c, 54911cd |
| B1 | where/kill/refire/retry accepted a stage outside the setting's workflow and crashed | the stage is tested against the loaded setting's workflow | 4fa4f30 |
| B3 | an override on a section the workflow lacks was refused with a false text or accepted silently | two positive tests with the YAML path's own texts | 5666f74 |
| B4, E2, E3 | nested/scalar overrides crashed; sweeps over unknown nested fields loaded; sweep shape mistakes crashed | one path check against the dataclass declarations for overrides and sweeps; sweep block shape checked | 4538c0d |
| B5 | a pinned key parsed as an int crashed | every stage value must be a 12-hex string | 5cd5263 |
| C1 | a walk validated each setting only when it reached it, so a stray token launched the earlier settings first | every named setting loads before the first walk | 78982d9 |
| C3 | a CPU-only walk printed nothing; a failed CPU stage exited 0 | one outcome line per stage (`reused`, `ok; report`, `failed`), exit 1 on a failed CPU stage; stdout flushed before a child starts | 517bf78, 280679e, b6307b6 |
| D3 | heartbeat ages could be negative (`beat=-2s`) | the clock is read after each piece's heartbeat file | 3a84691 |
| A2, A3 | refire without `--piece` was always refused with `no piece None recorded`; refire accepted a finished run | an omitted `--piece` resolves to the run's one loop/train piece; a finished run is refused with the retry command | c352f45, ef1afcf |
| E1 | a YAML key stated twice collapsed silently to the last | refused, naming the key and both lines | d2bb3dd |
| E4 | a reference cycle recursed without bound | refused, naming the chain | a1d7e3d |
| E5 | malformed YAML shapes crashed | refused, naming the body | 20c295d, 9b20701 |
| E6 | the `workflow:` line was never validated | non-empty, every entry a stage, same-setting upstream first | c7123f2 |
| E7, E8 | unknown annotation words became `dict`; list elements were untyped | unknown spellings refused by name; every list element checked | 15cf898 |
| E9 | `build.split_ratio` shape and sum unchecked | three non-negative shares summing to 1 | 0871ce5 |
| F1 | `inject.theta` unchecked (80 loaded, a probe arm that never fires) | outside [0, 1] refused; off-grid stays allowed | 9c8d065 |
| F2 (high) | a new `build.split_source` / `build.weight_mode` value silently ran the other branch | explicit dispatch over the named values, else raise; output for the existing values unchanged | 9c14f39 |
| F3 | a new sample/inject field is not keyed and no check notices | selfcheck check 12: every schema field is keyed, projected or a ref; recipe 3 names the STAGES tuples | ee8c735, 6184aeb |
| F4 | a generator named as `probe_score`/`theta_from` loaded and failed late with a KeyError | the loader requires a classifier method; eval refuses a non-classifier `theta_from` report | 073fac8, c2dd28b |
| O9 | refire wrote the launches entry's `cards`/`cmd` as bare strings, launch as maps | refire passes `{index: value}` | 72aa81c |

Every fix was reviewed on its branch (`scratchpad/phase4.json`: four approvals, two after one
fix round); no VERSION was bumped because no existing setting's output changes; the errata
records every new refusal as open for the owner. Owner files (`experimental_settings/*.yaml`,
`models/table.yaml`, `notes/`) are untouched.

### 2.2 Left for gyb, with the ready design

- **Where run.py is typed (X, second half; O8).** Contracts 3.4 and 6.3 say run.py and
  jobs/launch.py run on `login_host` only and refuse any other host, naming it; no line
  implements that. Two facts make a launch from another host unsound even after the port fix:
  registry rows carry a naive local time (`registry.py:116 datetime.now()`), and yebis is UTC
  while the cluster is JST, so the 20 rows this test wrote from yebis read nine hours apart from
  every other row (ages, the launch gate's young window and `free`'s reservation are off by nine
  hours for a row read on the other kind of host); and the `fcntl` lock on the ledger assumes
  one machine (contracts :5334-5337). Decide: implement the 3.4/6.3 refusal (one host check at
  the top of a launch, `hostname` against `login_host`, and then the desktop session works
  through `ssh shiga run.py ...`), or make timestamps zoned and the lock cross-host.
- **Overrides do not reach name-form references (O6).** A generator setting swept or
  overridden on a build-side field resolves `eval.theta_from` to the un-overridden classifier
  and the shared-build-key gate refuses it, so a data-side sweep of the classifier/generator
  pair is not expressible. The smallest design: a name-form reference loads the referenced
  setting under the same overrides (schema.py `_resolve_name_ref`) and the frozen diff records
  them; the errata's 5.4 rulings decide whether that is wanted.
- **Override runs read `edited` forever (D2).** `_current_setting` reloads the row's setting
  with no overrides (run.py:335) and no record keeps them. Design: a start-row/meta field
  `overrides` (contracts 8.1/8.3) and `_current_setting` reloading with it.
- **A not-yet-started piece reads `dead(escalated)` (D1).** `judge` has no not-started state
  (registry.py:827); contracts 8.5 lists the verdict order without one. Design: a piece with no
  beat and a launch younger than `launch_timeout_s` reads `warming up`.
- **A cgen/cparam train reads `suspected stall` during validation (D4).** The trainer beats per
  optimizer step; validation is 300 s at debug size and the stall line is 180 s. Design: the
  method's `validate` hook takes the heartbeat and beats per batch (contracts 2.6 signature).
- **Refire of a train piece that never wrote `last/` (O10).** The trainer refuses a directory
  with `train_log.jsonl` and no `last/`; refire starts a session that dies at once and leaves an
  open start row that blocks `retry` for 30 min (`kill` closes it). Design: refire applies the
  trainer's continue rule before the start row (refuse with the retry command), or
  `train_log.jsonl` becomes per-incarnation like the heartbeat files (contracts 2.6 layout).
- **Train on a chosen build run (matrix item 4).** Absent: `STAGES['train']['upstream']` has one
  `same` entry and `REF_FIELDS` has no train field; a build is reused only by content address
  (same build-side fields and versions give one directory, `owners` lists every setting). The
  smallest design inside the existing files is in `scratchpad/phase12.json`
  (`chosen_build_as_train_input`): a `train.build_from` ref field, a second upstream entry with
  source `ref:train.build_from`, and `trainer.py:237` reading through `referenced_run_dir`.
- **By design, noted for the person who types the commands:** A1 (retry clears the markers
  before the gates; commit before retry), B2 (`where` takes no override, so an overridden walk's
  key is seen only after the walk), C2 (a launch refused at the card step leaves a frozen
  directory with no registry row), F5 (pinned refs skip the inheritance check), G1 (a string
  sweep child is named with quotes, `probe.tuning='lora'`), H1 (`find` matches the frozen diff,
  never a default value), E6's remainder (a workflow list holding both `inject` and a
  probe-reading stage loads and crashes at key time; contracts 2.1 names no rule).
- **Not exercised:** attaching a second inject run to a live agent service (the probe arm's loop
  finished in about three minutes, before the second arm launched); `run.py sync` on a ledger
  with open runs; a real-scale run of anything.

## 3. How error-prone adding settings is (item 6)

The assessor drove `experimental_settings/schema.py` with about 110 synthetic cases (script
`scratchpad/setting_fragility/drive_schema.py`, its output `out.txt`; it writes nothing in the
repo). Its verdicts before the fixes: adding a **named setting** was robust for wrong fields,
wrong types and unregistered axis values (caught with a message naming the field), fragile for
a pasted block not renamed (silent), a missing `workflow:` line (silent no-op walk), and
malformed shapes (tracebacks); adding a **sweep** was fragile (unknown nested field silent,
three shape mistakes traceback, string children named with quotes); adding a **reference** was
fragile for a cycle (RecursionError), a wrong probe kind (late KeyError) and an int-looking
pinned key (traceback); adding a **field** per README recipe 3 was fragile in two ways that
pass silently (an unknown annotation spelling refuses every load with a contradictory text; a
new sample/inject field is not keyed, so a finished run is reused for a different value);
adding an **axis value** was the worst case (a new `build.split_source` / `build.weight_mode`
value loads, passes selfcheck and silently runs the other branch). After the fixes every case
that crashed or passed silently in that list ends in a `SchemaError` message naming the field,
except the by-design items of section 2.2 and the child-name quotes. The assessor's full
report, per kind of addition with the refusal texts, is Appendix A (written before the fixes;
the "after" column is the verification table of `scratchpad/phase4.json`).

## 4. Side effects of this test

- `jobs/runs.jsonl` grew from 152 to 189 rows (committed in 7009616 and at the end of the
  session); `jobs/RESULTS.md` re-rendered (the first render after HEAD also dropped 33 stale
  fixture lines that ruling 2 had deleted from the ledger without re-rendering).
- New debug run directories under `outputs/debug/`: build 55cd38c24455, train 602051218152,
  b4a83a32b921, f46997fdbf8d, eval 661699fd40e4, 0c15d71d5727 (failed), b27cc9c67906 (failed),
  inject 583c0e97913c, 210ff860f998, score 4586e0cdeba8, ecd526d476c3; and two frozen
  directories with no registry row from the refused launches of 1.4 (train with
  `train.lr=0.0002`, sample with `sample.max_steps=3`; C2).
- The cparam debug train `a956d422f5a0` was retried, killed, refired and retried; its final
  incarnation finished at 02:20 and its eval `f3f1719bd3a3` was recomputed at 02:47.
- Twenty rows written from yebis carry UTC-naive times; every other row is JST-naive (O8).
- Four worktrees under `.claude/worktrees/wf_bb94e262-762-{1,2,3,4}` hold the merged branches;
  they can be removed with `git worktree remove`.

## 5. Where the evidence is

`scratchpad` = `/tmp/claude-12114/-home-y-guo-reproduce-new1/efdc6c2b-3dcf-4b47-ab0f-3ff8cd6691b2/scratchpad/`:
`notes-so-far.md` (the main conversation's log), `phase12.json` (matrix commands, runner
results, the single-stage and chosen-build answers), `phase3.json` (72 refuter votes),
`phase4.json` (four implementer reports and their reviews), `fragility.md`, `launch-*.log`,
`err-*.log`, `post-*.log`, `where_after_merge.txt`, `setting_fragility/`, `fix/`.

## 6. Acceptance of finding X's fix from yebis

At 02:46, on the merged tree, typed on yebis: `run.py inject probe_p1_e1_theta_0pt80 --debug
--allow-dirty --cards tokyo108:5 --cards tokyo105:2 inject.max_steps=5` (the override gives a
fresh inject key; its references resolve to the default-key ctool and cgen trains). The alive
check passed through the ssh port probes, the check client ran on `login_host` and printed its
five `check:` lines (`/render`, `/score conf 0.177`, `/gen`), and the walk printed `run.py:
launched inject-dfd404c89e8e`. From yebis `run.py ls inject --debug` read the run's pieces
`0:done@shiga ... 1:done@tokyo108 ... cards=5; 2:done@tokyo105 ... cards=2` at 02:52 (3/3 tasks;
`flags=edited,debug`, finding D2). The same command at 02:53 printed `run.py:
inject-dfd404c89e8e ok; report .../inject/dfd404c89e8e/done.json` and `run.py:
score-d9c7d1427666 ok; report .../score/d9c7d1427666/report.md` (finish row elapsed 438.7 s;
score `success 0.0, base_success 0.0, delta_success 0.0`), and `tmux ls` on tokyo108 and
tokyo105 showed no session of the run. Before the fix the same shape of launch from yebis
polled for 1800 s and ended `alive_check` (section 1.1).

## Appendix A. The setting-fragility assessment (opus assessor, before the fixes)

# Setting fragility assessment (matrix item 6)

Repo `/home/y-guo/reproduce/new1`, branch from-zero, HEAD f2d87ea. I edited no tracked file, and nothing under `experimental_settings/` or `notes/` was written. Every synthetic setting went into a scratch root (`.../scratchpad/setting_fragility/root/`). In that root every repo entry is a symlink, and `experimental_settings/` holds read-only symlinks to the owner's four YAML files next to the synthetic case files. The driver points `schema.ROOT` at that root, so a name-form ref such as `train_probe/ctool_qwen3_0pt6b` resolves to the owner's real file. Evidence for each case is in `.../setting_fragility/out.txt`, with case ids like `[G6]`.

**Ledger note, not caused by me.** At 01:16 UTC `git status` already showed `jobs/runs.jsonl` and `jobs/RESULTS.md` modified. HEAD holds 150 lines; the working copy had 152, later 161. Other sessions were running `--debug` walks at the time, on host yebis and on tokyo105/108. `run.py ls --debug` lists them: `train-f46997fdbf8d`, `train-b4a83a32b921`, `inject-583c0e97913c` and `eval-661699fd40e4`. This means the task's premise "jobs/runs.jsonl empty" did not hold while I ran. So "unchanged by the tests" was checked by counting the registry test's fixture run_ids (`sample-<proc>-<row>`). The count was 0 before both tests and 0 after both. The one line added during the tests is another session's `train-f46997fdbf8d` start row at 01:23.

**Where validation lives.** `run.py selfcheck` never loads a setting. Its eleven checks (run.py:1673-1685) touch `experimental_settings/*.yaml` only through check 11, which compares file stems with the reserved subcommand names. So the only CPU command that validates a setting is `run.py where <wf> <setting> <stage>`. For example, `where inject probe_p1_e1_theta_0pt80 inject` prints `.../outputs/inject/34276f9e71fb` with exit 0. A walk validates a setting only when it reaches that setting. `cmd_walk` (run.py:1769-1775) loads and walks each named setting in turn, so a malformed second setting is refused only after the first has launched.

**Message quality in general.** Every `SchemaError` names the dotted field. None names the setting or the file, except "no such setting in <file>". Almost none names the fix; the exceptions are meta.override, sweep children and theta_from being required. The walk and single-setting paths catch only `schema.SchemaError` (run.py:149-152, 1770-1773), so any other exception reaches the person as a Python traceback.

---

## 1. A new named setting (the common case)

**What a person touches.** One block in one workflow file under `experimental_settings/`, which is gyb's file.

**What happens to the setting.**
- It is merged in this order: defaults, then `common:`, then the named block, then the sweep child, then debug.yaml, then command-line overrides.
- A copy of `ctool_qwen3_0pt6b` under another name gets the same four keys `a7d8b62ee953 / 6d3bf5aff879 / a1cadf425fd2 / 0e33d06cf15f` [A2]. Name and notes are not in the key, so a copy reuses the original's run directories.
- The named block wins over `common:` [M1: `train.lr=1e-05, epochs=2`]. `common:` fills in what the named block leaves unstated [M2].

**Caught, each with a clear field-naming message:**
- Unknown field: `train.learning_rate: not a field of this section` [D1]. The nested form is caught too [D2].
- Unknown or foreign section: `trian: no stage of this file's workflow reads this section` [D3, C1].
- A section the inject workflow may not state: `probe` [C2], `build` [C3].
- A read-only `models.agent_row` [D4].
- Scalar types:
  - `train.lr: '1e-5' has type str, declared type is float` [E1]. YAML 1.1 reads `1e-5` as a string. The message does not say to write `1.0e-5`.
  - `train.epochs: True has type bool` [E2].
  - `sample.split: 'test' has type str, declared type is list[str]` [E3].
  - The nested `train.predict.cap` [E7].
- Axis values: `probe.method: 'cfoo' is not one of (...)` [F1], plus split, effort, env and tuning [F2-F4, F7]. `inject.format` is caught [F8], and so is `inject.split` [F9].
- Model aliases:
  - `models.agent: 'gpt5' is not a row of models/table.yaml` [F5].
  - `models.probe: 'gpt_oss_120b' has role 'agent', expected 'probe'` [F6].
- Required fields:
  - `inject.theta: is required and was not set` [B2], and `inject.probe_gen` [B3].
  - `eval.theta_from: is required when probe.method's PROBE_KIND is generator` [B1].
  - `inject.fire_nth_cut: must be 0 under arm: no_probe` [B4].
- Inheritance through name-form refs: `generation.temperature: stated 0.7 differs from the referenced run's 1.0; list it in meta.override to allow this` [J1, J5]. Listing the field in `meta.override` lets it load [J2, J6]. A typo in `meta.override` still gets refused [J3].
- `score.baseline` split/seed superset check [H18].
- A retired axis value: `inject.format: 'p1_e1' is retired` [Q6].

**Silent (the setting loads):**
- **Duplicate setting name in one file.** The second block replaces the first with no message [L1: `sample.max_steps=10; meta.notes='second definition, pasted and not renamed'`]. A field stated twice also silently keeps the last value [L2].
- **List element types are not checked.** `sample.seeds: ["42"]` loads, and the build key moves (`19d8f6adfddb` vs `6d3bf5aff879`) [E4]. `eval.risk: [0.10, "x"]` loads [E5].
- **Value ranges are not checked.**
  - `inject.theta: 80` (a typo for 0.80) loads with key `9f9f7dd2d757` [E9]. The live loop fires on `conf >= cfg.inject.theta` (agent/step_with_probe.py:210), so this probe-arm run never fires.
  - `build.split_ratio: [0.5, 0.1]` under `split_source: hash` loads [E8]. data/build_training_dataset.py:134-142 sends every task past the cumulative share to `test`, which here is 40%.
- **Names `common` and a second file with the same setting name** load [L4, L5]. This is harmless, because the registry carries workflow and setting separately.
- **`meta.override` entries are never validated.** `[train.lr, no.such.field]` loads [J4]. This is harmless, because a typo still gets refused through the inheritance check.
- **ctool with `eval.theta_from`.** The field is ignored: the eval key equals ctool_qwen3_0pt6b's `0e33d06cf15f` [H1].

**Crashes with a traceback instead of a message:**
- An empty setting body (`name:` with nothing under it): `TypeError: 'NoneType' object is not iterable` at schema.py:1096 [D5].
- A setting named `workflow`: `ValueError` at schema.py:1096 [L3].
- A section written as a list: `AttributeError` at schema.py:591 [M4].

**Verdict: fragile.** The per-field checks are good. But duplicate names and fields collapse silently, list elements and value ranges are unchecked (theta 80 produces a probe arm that never fires), and no CPU check covers every setting.

## 2. A sweep (`sweep:` inside a named setting, children `<setting>/<field>=<value>,...`)

**What a person touches.** One `sweep:` mapping in the named block.

**What works.**
- A well-formed sweep gives children `sweep_ok/train.lr=1e-05` and `sweep_ok/train.lr=3e-05` with distinct train keys `a1cadf425fd2` and `09a5eec0e9d9` [G1].
- An inject sweep can supply the required `inject.theta` [G14].

**Caught, with a clear message:**
- An unknown section: `sweep.trian.lr: not a field of the schema` [G4].
- A debug field: `sweep.sample.n_tasks: also set by debug.yaml, which would collapse the sweep` [G9].
- A sweep field also given as an override: `train.lr: overridden and swept at once` [G12].
- Wrong value types go through the normal type check [G11].
- A probe field under inject is refused [G15].
- A sweep parent named where one setting is expected: `names 2 settings; name a sweep child directly` [G13, H14].

**Caught, but the message names the wrong thing:**
- An unknown field names the dataclass rather than the dotted field: `Train.foo: not a field of this section` [G3].
- A sweep value given as a bare string (`probe.tuning: lora`) is iterated character by character, so the refusal reads `probe.tuning: 'l' is not one of ('full', 'lora')` [G8].

**Silent:**
- **A sweep over an unknown nested field (`train.predict.foo: [1, 2]`) loads.** It makes two children with the identical train key `a1cadf425fd2`, which is also the real ctool train key [G6]. `_sweep_children` checks only the first component after the section (schema.py:708). The stray key is then dropped by `_dict_to_dataclass`.

**Crashes:**
- A sweep over a field of a section this workflow lacks (`inject.theta` in train_probe): `KeyError: 'inject'` at schema.py:616 [G5].
- A scalar instead of a list: `TypeError: 'float' object is not iterable` at schema.py:713 [G7].
- A path through a scalar (`train.lr.x`): `TypeError` at schema.py:619 [G10].

**Usability:**
- A child's name uses `repr`, so a string-valued child is `sweep_str/probe.tuning='lora'` [G2]. The shell strips the quotes, and the stripped name `sweep_str/probe.tuning=lora` is refused with `no such child of sweep_str` [G2b]. The refusal does not list the valid children.
- Every field debug.yaml sets can never be swept, even without `--debug`. That includes real hyperparameters: `sweep.train.epochs` and `sweep.build.max_cuts` are refused [G16, G17].

**Verdict: fragile.** A silent no-op sweep [G6], three tracebacks, and child names that need shell quoting.

## 3. A new axis value (`schema.AXES`, plus the code that implements it)

**What a person touches.**
- `schema.py AXES`.
- The implementing file: FORMATS, ARMS, PROBE_KIND/MATCH_VERSION, a method file, an env file, or a family's EFFORTS.

**Tied to code by selfcheck check 3 (run.py:1180-1247):**
- `inject.format`: an equality check against the FORMATS keys [Q4 prints the mismatch].
- `inject.arm`: equality with ARMS.
- `probe.method`: must be a key of PROBE_KIND and MATCH_VERSION, and equal to the `train/methods/` stems [Q5 prints three problems].
- `data.env`: equal to the environment stems.
- `data.instructions`, both split axes and `generation.effort`: subset checks.

**Not tied to code: `build.weight_mode`, `build.split_source`, `probe.tuning`.**
- With `per_task`, `by_date` or `qlora` added to AXES alone, the setting loads and check 3 returns `[]` [Q1-Q3].
- The build code has an if/else. `weight = 1.0 if weight_mode == "uniform" else 1/n` (data/build_training_dataset.py:237), so `per_task` silently runs `per_event`. `if split_source == "env" ... else` hash (line 131), so `by_date` silently runs the hash split.
- `qlora` is refused only inside the train process (models/probe_models/base.py:317 `probe.tuning: ... is not one of`), which runs after the GPU launch.

**Verdict:**
- Robust for format, arm, method, env, instructions, split and effort.
- Fragile for `build.weight_mode` and `build.split_source`, which give a silent wrong dataset, and for `probe.tuning`, which fails only after the GPU launch.

## 4. A new ref (`eval.theta_from`, `inject.probe_score`, `inject.probe_gen`, `score.baseline`)

**What a person touches.** The ref string `<workflow>/<setting>`, or a pinned `{key: {...}, method: ...}` / `{dir: {...}}` mapping.

**Shape errors are all caught, with messages that name the field:**
- No slash [H5]; a missing workflow file [H6]; a missing setting [H7].
- A referenced workflow lacking the required stage: `workflow ['sample', 'score'] does not provide stage(s) ['eval']` [H8].
- An unknown mapping form [H9]; an int [H10].
- A pinned stage set that is wrong: `pinned key stages ['train'] != required ['eval']` [H11].
- `method:` on theta_from [H12]; `method:` missing on probe_score [H19].
- A sweep parent [H14].
- probe_gen that is not a whole-call generator: cparam and ctool are both refused [H16, H17].

**A ref to a run that does not exist.** The setting loads. The walk refuses before launch with `run.py: eval: upstream 'train' at .../outputs/train/2fd7ff1a3f71 has no done.json; run it first` [I1, I2]. For a pinned key the message names both roots [I3]. These refusals name the upstream and the directory, not the setting to run first.

**Silent at load, and failing late or never:**
- **`inject.probe_score` naming a generator (`train_probe/cgen_qwen3_0pt6b`) loads** [H15]. From code reading, not run: the walk's `_resolve_inject_temperature` reads `fields["temperature"]` (run.py:1998). The generator report's fields (eval/utils/probe_eval.py:523-528) carry no temperature, so this would be a KeyError traceback at inject pre-launch.
- **`eval.theta_from` naming a generator (cparam) loads** [H2]. The eval stage then indexes `ref_fields["chosen"]` (probe_eval.py:489), which a generator report does not have.
- **theta_from a classifier on a different dataset or risk list loads.** Seeds [7] vs 42 give build keys `132da315e6c9` vs `6d3bf5aff879` [H3]; a risk of [0.2] also loads [H4]. The eval stage refuses both only after sample, build and the GPU train have run (probe_eval.py:660 and 679).
- **Pinned refs skip the data/generation inheritance check.** An inject setting with pinned refs and `generation.temperature: 0.3` loads [H20]. Only the method is checked at walk time (run.py:1939-1953). This may be what contracts 5.4 intends.

**Crashes:**
- A ref cycle (a setting whose theta_from names itself): `RecursionError` [H13].

**Verdict: fragile.** Shape errors are handled well. But semantic mistakes (the wrong kind of probe, a mismatched dataset or risk list) are caught only after the GPU stages or as tracebacks, and a cycle crashes.

## 5. A new field (README section 3, recipe 3)

**What a person touches.** A dataclass field in `schema.py`, and the one module that reads it.

**What the recipe gets right.** For sections that `STAGES` names whole (train, build, eval, data, generation), the new field enters the key automatically. A `Train.new_knob=5` moves the train key from `c6115b18aabb` to `0df1120f77ab` [P2].

**Where it breaks:**
- **Sample and Inject list their keyed fields one by one** (schema.py:204-205, 270-274). A new `Inject.new_knob=5` keeps the inject key `34276f9e71fb`, while the value is frozen into settings.yaml [P1].
  - A finished run is therefore reused for a different value.
  - Recipe 3 says nothing about `STAGES[...]["sections"]` or `projection`.
  - No selfcheck check holds every field to a stage key, a projection or a ref. Today every field is covered [P5: `[]`], but nothing keeps it that way.
- **`_annot_types` (schema.py:558-570) maps any annotation it does not know to `dict`.**
  - A field annotated `tuple[int, ...] = (1,)` makes every setting refuse to load: `train.new_tuple: (1,) has type tuple, declared type is tuple[int, ...]` [P3].
  - `Optional[int]` refuses an int: `3 has type int, declared type is Optional[int]` [P4].

**Command-line overrides (`section.field=value`):**
- Caught:
  - An unknown field [N5].
  - A probe field under inject [N7].
  - An inherited field without `meta.override` [N8].
  - The generator-without-theta_from check [N6].
  - `train.lr=1e-5` gives a string-type refusal, with no fix named [N2].
- Wrong reason: an override for a section outside this workflow says `inject.theta: not a field of the schema` [N1]. It is a field of the schema; this workflow just does not read it.
- Crashes:
  - `train.predict=5`: `TypeError` at schema.py:724 [N3].
  - `train.lr.x=1`: `TypeError` at schema.py:609 [N4].
- Silent: `train.max_steps=` with the value forgotten sets None, meaning no cap [N12].

**Verdict:** robust for train/build/eval/data/generation fields. Fragile for sample/inject fields (a silently unkeyed field) and for any annotation outside the six spellings the loader knows.

## 6. A new workflow file

**What a person touches.** A new `experimental_settings/<stem>.yaml` with a `workflow:` line.

**Caught:**
- A stem equal to a reserved subcommand (check 11).
- A later stage whose upstream has not run: `upstream 'build' ... has no done.json; run it first` [O4b, O5b].

**Not validated at all: the `workflow:` list.**
- **No `workflow:` line.** The setting loads with `_workflow=[]` [O1]. `_walk_one` visits no stage, and `cmd_walk` returns 0 (run.py:1776-1783).
- **A typo (`[smaple, score]`).** A setting that states `sample:` is refused with a message about the section, not the typo [O2]. A setting that does not state it loads [O3], and the walk's first `schema.key("smaple", ...)` raises `KeyError: 'smaple'` at schema.py:1149 [O3b].
- **Stages out of order or with a gap** load [O4, O5]. They are refused only at walk time.
- **All six stages in one file** load [O6]. `schema.key("train", ...)` then crashes with `TypeError: 'NoneType' object is not subscriptable` at schema.py:1238 [O6b], because an inject workflow forces `models.probe=None`.

**Verdict: fragile.** Nothing checks the workflow line against `STAGES` or against a valid order.

## The `--debug` overlay on each workflow [K-*]

All four real settings load under `--debug`. Their keys differ from the real keys, and their directories are under `.../outputs/debug/`.

| Setting | Debug diff | Debug key | Real key |
|---|---|---|---|
| baseline, sample stage | `{sample.max_steps: 6}` | `96de225de2b4` | `a7d8b62ee953` |
| train_probe, build stage | `{build.max_cuts: 8, build.max_examples: 64, sample.n_tasks: 3}` | — | — |
| inject, inject stage | `{inject.max_steps: 6, inject.theta: 0.8}` | `583c0e97913c` | `34276f9e71fb` |

- In the inject setting, the upstreams resolve to the debug probe runs (`probe_score.eval: 5f5a8f4f96f6`).
- The overlay's `sample:` and `build:` sections are skipped for inject, as intended.
- The overlay is correct on every workflow. Its only cost is the sweep ban in section 2.

## run.py find

`run.py find probe.method=ctool` prints `no runs match`, yet the ledger holds ctool train rows: setting ctool_qwen3_0pt6b, diff `{"train.max_steps": 20, "train.predict.cap": 100}`. `registry.find` (jobs/registry.py:535) matches only against `diff`, which leaves out default values. So a query for a default value, here ctool, never matches.

## Summary verdicts

| Kind of addition | Verdict | Main reason |
|---|---|---|
| Named setting | fragile | duplicates collapse, list elements and ranges unchecked, no all-settings check |
| Sweep | fragile | silent no-op sweep on a nested typo, three tracebacks, quoted child names |
| New axis value | robust for 7 axes; fragile for `build.weight_mode`, `build.split_source`, `probe.tuning` | those three are not tied to code by selfcheck |
| New ref | fragile | semantic mismatches caught only after the GPU stages; a cycle crashes |
| New field | robust for whole-section stages; fragile for sample/inject and unusual annotations | a new sample/inject field can be silently left out of the key |
| New workflow file | fragile | the workflow line is never validated |

## Appendix B. The CPU runner's results (phase 2)

| id | item | outcome | rc | command | evidence |
|---|---|---|---|---|---|
| T0.1 | | pass | 0 | `for spec in ... run.py where $wf $s $st $d ... (as given)` | train_probe ctool_qwen3_0pt6b sample real .../outputs/sample/a7d8b62ee953 no-done / train_probe ctool_qwen3_0pt6b sample --debug .../outputs/debug/sample/96de225de2b4 done / train_probe ctool_qwen3_0pt6b build --debug .. |
| T0.2 | | pass | 0 | `external/probe-env/bin/python /tmp/claude-12114/-home-y-guo-reproduce-new1/efdc6c2b-3dcf-4b47-ab0f-3ff8cd6691b2/scratchpad/upstreams.py` | inject probe_p1_e1_theta_0pt80 inject debug 583c0e97913c /     probe_score.train bd4a5dcf5629 .../outputs/debug/train/bd4a5dcf5629 done /     probe_score.eval 5f5a8f4f96f6 .../outputs/debug/eval/5f5a8f4f96f6 done /     p |
| T1.8 | | skipped | -1 | `external/probe-env/bin/python run.py ls --debug` | depends_on T1.5 and T1.7, which are GPU walks held as BLOCKED |
| T3.2 | | pass | 1 | `external/probe-env/bin/python run.py where train_probe ctool_qwen3_0pt6b/train.lr=0.0003 train` | run.py: ctool_qwen3_0pt6b/train.lr=0.0003: no such child of ctool_qwen3_0pt6b / rc=1 |
| T3.3 | | pass | 1 | `external/probe-env/bin/python run.py where train_probe ctool_qwen3_0pt6b train; ... train --debug; ... train train.lr=0.0003` | .../outputs/train/a1cadf425fd2 / rc=0 / .../outputs/debug/train/bd4a5dcf5629 / rc=0 / run.py where: usage: run.py where <workflow> <setting> <stage> [--debug] / rc=1 |
| T3.4 | | pass | 0 | `external/probe-env/bin/python /tmp/claude-12114/-home-y-guo-reproduce-new1/efdc6c2b-3dcf-4b47-ab0f-3ff8cd6691b2/scratchpad/overrides.py` | base {'sample': '96de225de2b4', 'build': 'b565f5ab1b94', 'train': 'bd4a5dcf5629', 'eval': '5f5a8f4f96f6'} / {'sample.pieces': '2'} moves [] / {'sample.replicas': '2'} moves [] / {'sample.seeds': '[42, 43]'} moves ['build |
| T4.1 | | pass | 0 | `external/probe-env/bin/python /tmp/claude-12114/-home-y-guo-reproduce-new1/efdc6c2b-3dcf-4b47-ab0f-3ff8cd6691b2/scratchpad/upstreams.py` | train_probe cgen_qwen3_0pt6b eval debug 64464e0a216c /     train 94cbec080c4b .../outputs/debug/train/94cbec080c4b done /     theta_from.eval 5f5a8f4f96f6 .../outputs/debug/eval/5f5a8f4f96f6 done / train_probe ctool_qwen |
| E3 | | pass | 1 | `external/probe-env/bin/python run.py where train_probe ctool_qwen3_0pt6b nope` | run.py: 'nope' is not a stage; one of ['build', 'eval', 'inject', 'sample', 'score', 'train'] / rc=1 |
| E12 | | pass | 0 | `external/probe-env/bin/python /tmp/claude-12114/-home-y-guo-reproduce-new1/efdc6c2b-3dcf-4b47-ab0f-3ff8cd6691b2/scratchpad/overrides.py \| g` | inject probe_p1_e1_theta_0pt80 debug {'inject.theta': '0.81'} -> {'inject': '0fa7f15d6c52', 'score': '380dc1899315'} / inject probe_p1_e1_theta_0pt80 debug {'inject.theta': '1.5'} -> {'inject': '293245a11b65', 'score': ' |
| E13 | | pass | 1 | `external/probe-env/bin/python run.py where train_probe nope sample --debug` | run.py: nope: no such setting in /home/y-guo/reproduce/new1/experimental_settings/train_probe.yaml / rc=1 |
| C1 | | pass | 0 | `external/probe-env/bin/python run.py selfcheck` | selfcheck: 31 python files, 0 problems / rc=0 |
| C2 | | pass | 0 | `external/probe-env/bin/python tests/test_registry_concurrent_append.py` | Ran 7 tests in 0.238s /  / OK / rc=0 |
| C3 | | pass | 0 | `external/probe-env/bin/python tests/test_packed_loss.py` | Ran 3 tests in 2.483s /  / OK / rc=0 |
| C4 | | pass | 0 | `external/probe-env/bin/python run.py table; external/probe-env/bin/python run.py table train_probe --debug` | # eval matrix: backbone x method x risk / \| backbone \| method \| risk \| n \| coverage \| ... \| runs \| status \| / \|---\|...\| / (first call: no data rows, rc=0) / \| qwen3_0pt6b \| ctool \| 0.1 \| - \| ... \| 5 \|  |
| C5 | | pass | 0 | `external/probe-env/bin/python run.py find probe.method=cgen; external/probe-env/bin/python run.py find train.lr=0.0003` | run_id \| stage \| workflow/setting \| status \| commit / train-b4a83a32b921 \| train \| train_probe/cgen_qwen3_0pt6b \| launching \| f2d87ea / eval-64464e0a216c \| eval \| train_probe/cgen_qwen3_0pt6b \| ok \| 24a9f19 / |
| C6 | | blocked | -1 | `external/probe-env/bin/python run.py sync` | Read-only precheck (scratchpad/open_run_verdicts.py) at 01:34:05: / inject-4d9c736d3834 done.launch None ordinal 1 sync_ok_row False verdicts ['done', 'done', 'done', 'done'] launch_failed False / inject-583c0e97913c don |
| C7 | | pass | 0 | `external/probe-env/bin/python run.py free` | (01:35:32 UTC) / tokyo105: [1, 3, 4, 5, 6, 7] / tokyo106: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] / tokyo107: [0, 1, 2, 3] / tokyo108: [0, 1, 4] / rc=0 |
| C8 | | pass | 0 | `external/probe-env/bin/python run.py ls` | run.py ls: no runs / rc=0 |
| C9 | | pass | 0 | `external/probe-env/bin/python run.py ls --debug` | run_id \| stage \| workflow/setting \| status \| progress \| rate \| heartbeat \| flags \| pieces / train-f46997fdbf8d  stage=train  train_probe/cparam_qwen3_0pt6b  status=launching  progress=2/2 step  ... flags=edited,d |
| GIT | | pass | 0 | `git status --short` |  M jobs/RESULTS.md /  M jobs/runs.jsonl |
