# Owner rulings of 2026-09-24 and the hand-off to the executing sessions

gyb decided every open item of the 2026-09-23 inventory in one sitting on
2026-09-24. This file is the record; the sessions that execute them read it
first. Nothing below is started until gyb says so in the executing session.

## State when this file was written

- Branch `from-zero` is the working branch; its tip has moved past `bf134b5`
  with the other session's bug-fix merges (`f6d9193`, `ed426ac`: retry tests
  liveness first, `--debug` on kill/refire/retry, the monitoring line, the
  registry verdicts, `cards_busy`, the endpoint-timeout teardown, the test
  sys.path, the errata closures). Check `git log --oneline -10` for the
  current tip.
- Branch `owner/2026-09-23-cards`, checked out in the worktree
  `.claude/worktrees/cards-2026-09-23`, holds ruling 1 uncommitted (9 files,
  reviewed in two rounds, findings fixed). Its `jobs/registry.py`
  `cards_busy` line was made to conflict on purpose with from-zero's, so the
  merge cannot silently keep a call to the removed private helper.
- Subagent policy since 2026-09-23: every subagent is opus, few per task
  (one implementer; one finder plus one refuter per review round), low
  effort for mechanical steps.

## The rulings

1. Card facts live in one file, `constants/cards.yaml` (per host, per card
   index: model, `memory_gib` rounded down: 47 / 93 / 140); the `hosts:`
   block leaves `constants/path_outputs.yaml`; one loader
   `registry.hosts()`; `jobs/launch.py` `place()` lands an agent service
   only on a host whose free cards are at least as large as the smallest
   card of its table row's serving host, `--cards` pools are filtered the
   same way and a too-small named card is refused by name; a measured
   task x card table `.claude/skills/gpu-run/references/card_performance.md`
   for people and agents, appended after every GPU run; the gpu-run skill
   (1.1.0) picks cards from the two files. Built on the branch above.
   Still to do at merge: resolve the `cards_busy` hunk keeping
   `canonical_host(host_name)` and dropping from-zero's
   `cfg = _outputs_config()` line; change `gpu_state.md`'s 95G / 143G /
   48G to 93 / 140 / 47 GiB; `run.py selfcheck`; the two test modules in
   separate processes; commit.
2. `jobs/runs.jsonl`: one recorded cleanup. Delete the 42 fixture rows
   (commit `deadbee`, dir under `/tmp/`), keep the 10 `launch_failed` rows
   of `train-f895049ab1dc`. Re-render `jobs/RESULTS.md` through
   `jobs/registry.py`. The commit message states what was removed, why,
   and the two identifying facts. This is the one sanctioned exception to
   "never hand-edited".
3. tokyo105: delete the crontab line that relaunches `new1_sampler` every
   five minutes, and kill the `new1_sampler` tmux session.
4. Sweep the AppWorld working directories that killed pieces left on NFS
   (368 directories, 330 MB on 2026-09-23; the location is in
   `data/environments/appworld.py`'s TODO near line 394). One sweep, no
   code change.
5. `pieces` for sample and inject stays the placeholder 6 until a
   full-scale sample measures throughput (gyb sets it then).
6. `inject.theta` stays 0.80 until the full ctool eval gives the risk
   thresholds (gyb sets it then).
7. `agent/run_tasks.py`: a probe-service 500 ends the piece; a service
   that dies ends the run as `launch_failed`. Confirmed as coded; remove
   the "to confirm" TODO, keep the rule as a comment.
8. A dead service piece is handled by re-running the walk, which relaunches
   the whole run; `run.py refire` covers loop and train pieces only. Write
   that in the gpu-run skill (Phase 6b) and replace `jobs/launch.py`'s
   TODO near line 1203 with the rule.
9. A `--debug` walk of a setting whose probe reference is in name form
   resolves the reference under the debug outputs root (the referenced
   train run of the same debug walk). Code fix at the cause in `run.py`
   (near line 1881) / `experimental_settings/schema.py`; remove the TODO.
10. The registry lock is released once the start row is written; the
    service start, the alive checks and the loop start run outside it; a
    failed start re-takes the lock to append the `launch_failed` row.
    Contracts 8.1 / 8.6 are then true again; close the errata entries that
    recorded the divergence.
11. The attach-only comparison (served model name and `max_model_len` on
    the service, the rest through the serving run's claims on
    `jobs/launch.py`) is accepted; close errata line 154's "open".
12. The stall line over a long prediction pass: no change.
13. Version-history decisions in errata 184 (a), (b), (c): accepted as
    coded; close the "open to reversal" wording.
14. selfcheck assumptions in errata 198-203 (README is the authority over
    contracts 0.2; `FORMATS` read through a keys-only parser;
    `SCHEMA` / `DEFAULTS` / `REQUIRED` read structurally; the package marker
    line equals the sibling set): accepted; close them.
15. Implementer decisions listed in tickets 10, 12 and 07 (the `n` column
    as an integer; a call that does not parse counts as not agreeing; a
    single seed's spread is 0.0; the start row's `parent` and `swept` are
    null; `refire` re-derives the card count from the old `gpus` string and
    prefers the old host; the attached endpoint's `pid` is null): accepted.
16. `.claude/hooks/settings_readonly.sh` leans toward catching writes: add
    the `python3 -c`, `perl -pi`, `yq -i` and `ed` shapes; over-refusal of
    read-only commands is accepted.
17. The per-branch staleness plan (`when` field, pre-commit hook, judging
    agent) is not built until a second branch exists. Leave the TODO in
    `experimental_settings/schema.py` with this ruling added.
18. Rename the three format files as the TODO in `data/training_data.py`
    says: `data/training_data.py` -> `data/training_data_format.py`,
    `data/trajectory_record.py` -> `data/trajectory_record_format.py`,
    `data/probe_output.py` -> `data/probe_output_format.py`; rewrite the
    first docstring line; sweep every code directory, README.md,
    `experimental_settings/schema.py`'s stage table, the tickets and the
    folder plans; `notes/` (tree document, contracts) is gyb's. Check first
    whether a file path enters any key; if it does, the rename moves keys
    and gyb is told before the commit.
19. The tree document and the contracts (`notes/plans/`) are stale in the
    sections the errata lists; gyb rewrites them himself. Recorded in the
    owner TODO list below.
20. `notes/WORKPLAN.md` (old pipeline), `notes/TIMELINE.md` (no entry after
    09-20), `notes/CONTEXT.md` (Ledger, Sampler, Incident agent, Autopsy
    retired): gyb edits them himself. Recorded in the owner TODO list.
21. `.scratch/review/issues/` (55 tickets, all needs-triage): delete the
    directory.
22. Output directories stay `<stage>/<key>`. Instead gyb wants a console
    to browse a run's details. A separate design, not part of the batches
    below.
23. The step-by-step walkthrough is stopped: eval (steps 33-36) is marked
    unfinished, `train/methods/cgen.py` and `train/methods/cparam.py`
    unread.

## Owner TODO list (gyb edits these himself)

- `notes/plans/2026-09-14-structure-from-zero.md`: 31 files, no
  `eval/methods/`, the renamed `agent/` files, the three `_format` names
  after ruling 18, `constants/cards.yaml`.
- `notes/plans/2026-09-17-contracts.md`: the sections the errata marks
  stale (1.5, 1.6, 1.7, 2.3, 2.4, 3.4, 6.2, 6.3, 7.4, 8.1, 8.2, 8.4, 8.5,
  8.6, Part 9(a) decision 31).
- `notes/WORKPLAN.md`: rewrite for the from-zero tree (next step: the
  full-scale sample).
- `notes/TIMELINE.md`: entries for 2026-09-21 to 09-24 (the walkthrough,
  the executed owner TODOs, the bug batch, the card files, these rulings).
- `notes/CONTEXT.md`: delete Ledger (`ops/jobs.json`), Sampler, Incident
  agent, Autopsy.
- eval walkthrough not done (ruling 23).

## Execution, split into sessions that do not touch the same files

Session "merge-cards" (first, alone): ruling 1. Files: run.py, jobs/*,
constants/*, .claude/skills/gpu-run/*, .claude/agents/gpu-runner.md,
README.md, the errata. Ends with a commit on from-zero and the worktree
removed (`git worktree remove`).

Session "records" (parallel with merge-cards): rulings 2, 3, 4, 21, and
this file's owner TODO list copied to `.scratch/owner-todo.md`. Touches
jobs/runs.jsonl, jobs/RESULTS.md, the cluster, `.scratch/`. Commit each
ruling separately.

Session "code-batch" (after merge-cards is on from-zero): rulings 7, 8, 9,
10, 11, 13, 14, 16, 17, then 18 last (the rename touches every directory,
so it goes after the others). One opus implementer per ruling, one finder
plus one refuter per review round, selfcheck and the two tests (separate
processes) before each commit, `--debug` walks returned as BLOCKED for gyb.

Later, its own session: ruling 22, the run console, starting from a design
gyb approves.
