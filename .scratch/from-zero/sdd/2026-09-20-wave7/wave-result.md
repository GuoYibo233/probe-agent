# Wave 7 result (2026-09-20, session new1-08)

Session wave7 held this wave and never started it (no record on disk, both tickets
`ready-for-agent`); gyb handed it to this session the same day.

## Tickets

| ticket | branch | merged as | fix rounds | acceptance on the merged tree |
|---|---|---|---|---|
| 17 `CLAUDE.md`, exp-status, the agents, the remaining skills | `ticket/2026-09-20-wave7/T17` | 25f01d4 | 0 | C5, C7, C8, C12, C13, C15 pass |
| 18 the migration | `ticket/2026-09-20-wave7b/T18` | 814c908 | 0 | C5, C6, C9, C10, C14, C15, C16 pass |

Both ticket bodies were corrected before dispatch (`precheck.md`). The 284 untracked
files and 4 NFS symlinks that `git rm -r legacy/` left behind were moved to
`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/legacy-untracked-2026-09-20/`.

## The section-4 `--debug` walks

All three walk. Keys: sample `96de225de2b4`, baseline score `20eaad1deae5`, build
`b565f5ab1b94`, ctool train `0f3e343f0eca` / eval `b5999ae061f9`, cgen train
`b45633250e8b` / eval `e5d6ba9d8c7b`, cparam train `5b398c217e13` / eval
`ef9644a7e92f`, inject `c96e48a8be3d` / score `d49397cf4dd9`, forced-fire inject
`27d4bad1b70a` / score `a4e05cb2fbe3`.

Facts measured: the plain inject run never crossed theta 0.80 (no `spec` row); the
forced rerun (`inject.fire_nth_cut=1`) wrote 18 `spec` and 18 `resume` rows over 3
tasks; the probe service's `encode_special` check reads True on this backbone; the
prediction step took 3.06 s per row for cgen on an H200 and 0.69 s per row for cparam
on an A6000 (128 rows each).

## Defects found by running, each fixed at its cause

1. `models/agent_models/service.py`: an empty `/health` body was decoded as JSON, so the
   service never counted as healthy (be60c4c).
2. `train/utils/trainer.py`: no bfloat16 autocast; cgen and cparam ran out of memory on
   48 GB cards. VERSION 2, stale train.
3. `jobs/launch.py` `alive_check`: a fixed 30-second window closed a run that was still
   importing torch.
4. `models/probe_models/base.py` `Probe.generate`: the whole frame in one call;
   `GENERATE_BATCH = 8`.
5. `schema.referenced_run_dir`: three stage-side lookups located a referenced run with
   `debug=False` (08337dc).
6. `jobs/registry.py` `fold`: a finish row that preceded a relaunch's start row read as
   the run's state.
7. `models/agent_models/service.py` `serve`: the checks refuse with `SystemExit`, which
   `except Exception` never caught, so a refused start left vLLM on the card (found by
   M-M2, 55fb302; widened to a `finally` by the review).
8. `train/utils/trainer.py`: the resume checkpoint was overwritten in place, and a kill
   during the write left `last/optimizer.pt` truncated (found by M-T3, 2a9e2a1).
9. `tests/test_registry_concurrent_append.py`: the forked child imported the real
   `jobs.registry` whenever the parent already held it, and wrote fixture rows into the
   real `jobs/runs.jsonl` (74cfc76).

## Reviews

- `walk-fixes-review.json`: four opus finders over fixes 1-7, each finding re-checked by
  an opus refuter: 12 verified (2 critical, 7 important, 3 minor), 2 refuted. Fixed on
  three branches, each reviewed (`walk-fixes-fix.json`), merged as a624d10, c86c989,
  1deb32f.
- `final-review.json`: five opus lenses over the whole branch plus a completeness critic:
  19 verified (3 critical, 8 important, 8 minor), 8 refuted, 4 critic findings. Fixed on
  three branches, each reviewed (`final-review-fix.json`), merged as 17dbc0d, 9ac7299,
  67fb3b0.

## The GPU list of the construction plan's section 2

Pass: M-G1, M-G2, M-G3 (B4, C1, C2, D1-D5 against the real tree; C3-C5 never run), M-J1,
M-J2, M-J3, M-J4, M-J8 (the second call launches nothing; the refusal is `run.py`'s
live-piece line, not the gate's), M-M1, M-M2, M-M3, M-M4, M-M5, M-M6, M-A1, M-A2, M-A3,
M-A4 (`identical` true on 10 of 18 rows under `probe_nofill`), M-D1, M-T1, M-T2 (gate
`PASS: false`, diff 0.151, no optimizer step), M-T3 (the `resume` event at step 2, the
log appended, counts 64 / 64 / 128; an earlier attempt met the refusal on a moved commit),
M-T4, M-T5 (`best/model.safetensors` 2.38 GB, no adapter file, `tuning: lora`), M-T6,
M-E1, M-E2, M-E3, M-W1, M-W2.

Not run: M-J5 (needs the `<|end|>` encode fixture to fail, and it passes on this
backbone); M-J6 and M-J7 (`refire` and `kill` take no `--debug`, so neither can address a
debug run, and no full-scale run was started); M-M7 as a separate item (the predict-only
path and the probe service both reload `best/`); M-W3; M-W4 (the permission classifier
refused removing the sampler's crontab line and its `new1_sampler` tmux session).

## Open for the owner

- `jobs/runs.jsonl` lines 103-135 and 137-145 are 42 fixture rows of defect 9 (run ids
  `sample-<n>-<m>`, directories under `/tmp/tmp*/out/sample/shared`), committed in
  b59bdf2, and `jobs/RESULTS.md` renders them. The registry is never edited by hand, so
  they stand until the owner rules.
- The same file holds ten `launch_failed` rows of `train-f895049ab1dc`, written by this
  session's relaunch loop during the first M-T3 attempt.
- M-W4, and the two tmux sessions `new1_fmt_smoke_srv_t108g0` and
  `new1_fmt_smoke_probe_t108g1` of 2026-09-12 that still hold tokyo108 cards 0 and 1.
- `.claude/hooks/settings_readonly.sh` refuses a read-only command that names a setting
  file beside a write word and does not see an edit made through `python`, `perl`, `yq`
  or `ed` (final review, critic F2, not verified by a second reviewer; agents do not edit
  the hook).
- `run.py ls` prints no escalation mark although contracts 8.5 says `escalated` survives
  as a flag `ls` prints (final review D6).
- The three `data/*_format.py` renames, the owner's change to the fixed tree.
- The contracts sentences the 2026-09-20 changes made stale are listed in
  `final-review-fix.json` under `stale_sentences` (2.4's retry and continue rule, 1.5's
  `done.json` fields, 8.2's finish-row rule, 8.4's eval total, 8.5's `escalated`).
