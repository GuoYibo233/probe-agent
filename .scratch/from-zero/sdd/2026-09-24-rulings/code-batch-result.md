# Session "code-batch" of 2026-09-24: rulings 7, 8, 9, 10, 11, 13, 14, 16, 17 and 18

The executing session read `rulings.md` and ran one opus implementer per ruling, one
finder plus one refuter per review round, `run.py selfcheck` and the two test modules in
separate processes before every commit. Nine rulings are committed on `from-zero`; ruling
18 waits uncommitted in a worktree because the rename moves every key, which the ruling
says gyb is told about before the commit.

## Commits on from-zero (oldest first)

| ruling | commit | what changed |
|---|---|---|
| 7 | a7c733c | `agent/run_tasks.py`: the service-failure rule kept as a comment, confirmed as coded; the TODO gone |
| 17 | d955265 | `experimental_settings/schema.py`: the per-branch staleness TODO stays with the ruling added |
| 16 | f089db8 | `.claude/hooks/settings_readonly.sh`: any mention of `python`, `perl`, `yq` or `ed` beside a protected setting file's name is refused; the owner TODO gone |
| 8 | 4b47ad1 | `run.py refire` refuses a service or cpu piece by index and kind before the dirty-tree gate and the freeze (`jobs/launch.refire_target`); a dead service piece is handled by `run.py kill` then re-running the walk; gpu-run 1.1.1, gpu-runner agent, README |
| 10 | 8bc8a90 | launch() already released the lock before its tmux waves (7e347b2); refire now holds its own lock from the liveness test through its one tmux start; errata closes the three lock entries; gpu-run 1.1.2 Phase 4 and the gpu-runner agent state the two holds |
| 9 | 76cab53 | a name-form reference is loaded under the referring setting's debug flag, so a `--debug` walk resolves it to the referenced setting's debug run; no non-debug key moved, six debug keys moved; gpu-run 1.1.3 Phase 3; errata closes the two pinned-reference entries |
| 11 | bd67cff | errata: the attach-only comparison accepted, the 7.1 / 7.4 entry closed |
| 13 | 90ffdc0 | errata: version-history decisions (a), (b), (c) accepted, the open-to-reversal wording closed |
| 14 | c755e80 | errata: the four selfcheck assumptions and the two ticket-16 entries closed |

## Ruling 18, waiting for gyb

Worktree `.claude/worktrees/agent-acf9438e590c21fa0`, branch
`owner/2026-09-24-format-rename`, based on 76cab53, uncommitted: the three `git mv`
renames staged, 29 other files modified (code, README.md, the stage table, tickets, folder
plans). Reviewed in one round (finder, six findings fixed, refuter: all ten claims hold).
`run.py selfcheck` 31 files 0 problems, both tests OK, every module imports under
probe-env.

**The key question:** a file path enters every key. The stage table's `versions` entries
carry the path string as the payload name (`schema._key_versions`), and every stage lists
at least one of the three files (sample, inject, score: the record file; build: the record
and training-data files; train: the training-data and probe-output files; eval: the
probe-output file). All 36 keys (every setting, every stage, with and without `--debug`)
move once at the commit; the table is in the worktree's report
(`/tmp/.../scratchpad/r18-before.txt`, `r18-after.txt`, and the implementer's report in
the session transcript). No non-debug run exists on the outputs root (every start row in
`jobs/runs.jsonl` carries `debug: true`), so the cost is the debug directories: after the
commit every `--debug` walk starts fresh, and `run.py ls` shows the old rows as `edited`
with no `stale=` sentence (the old file name no longer exists for `effective_version` to
read). To commit: `cd` into the worktree, `git add -A`, commit on the branch, merge into
`from-zero`, `git worktree remove` the directory. The `--debug` walks that prove the
renamed tree runs are GPU launches (BLOCKED, through the gpu-run skill): `train_probe
ctool_qwen3_0pt6b --debug`, then `cgen_qwen3_0pt6b`, `cparam_qwen3_0pt6b`, `baseline
gpt_oss_120b_appworld --debug`, `inject probe_p1_e1_theta_0pt80 --debug`.

## Found while executing, for gyb (no ruling asked)

- Ruling 7: "a service that dies ends the run as `launch_failed`" holds only when every
  piece of the run reads `dead`, service pieces included; a probe service dying alone
  leaves the agent vLLM service `healthy`, so the run stays open with its loop pieces
  dead and the agent's cards reserved. The comment in `agent/run_tasks.py` states the
  code's rule.
- Ruling 17: the TODO's own examples (the five injected-text formats, the LoRA / full
  tuning branch) are branches that already exist, so "until a second branch exists" needs
  gyb's meaning of "branch" before anyone can say the trigger is met.
- Ruling 16: `git add experimental_settings/inject.yaml` and a commit message that names a
  protected file beside `add`, `rm ` or an interpreter name are refused by the hook (the
  `dd ` and `rm ` substrings); `git commit -F <file>` is the way round. A protected path
  spelled through a shell variable passes the hook, as before.
- Ruling 11 (errata entry): `jobs/launch._find_attach_target` never tests `attached_to`,
  so an open attaching run's own endpoint file can be matched and `attached_to` then
  names that run; once it closes, the owning run's teardown ends the server a later
  attached run still uses.
- Ruling 13 (errata entry): `run.py._stale_sentence`'s `@` branch never runs, because
  recorded `versions` names come from `schema.versions_of` and carry no `@`; an eval-only
  bump of `eval/utils/probe_eval.py` that moves an inject key leaves that file out of the
  stale sentence `ls` prints.
- Errata line 209 (the endpoint-timeout exit leaving service pieces up) is stale: the
  exit goes through `failed("service_check")`, which runs `teardown_launch`. Not closed,
  no ruling names it.
- The contracts (`notes/plans/2026-09-17-contracts.md`) still say a resolved reference is
  keyed without the debug overlay (3.1 :2425-2428, 3.4 :2627-2632) and still name the
  three format files by their old names (44 places); the owner TODO list in `rulings.md`
  leaves out contracts 0.2, whose six annotation lines the wave-6 precheck found wrong.
