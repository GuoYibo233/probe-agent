# new1 from zero: the construction plan

Written 2026-09-17, after the contracts
(`notes/plans/2026-09-17-contracts.md`) and against the fourth draft's fixed
tree (`notes/plans/2026-09-14-structure-from-zero.md`, Part 1). It answers one
question the contracts do not: **in what order the 34 files are written, by
whom, and what proves each one works.**

Three documents, three jobs. The tree says which files exist. The contracts say
what crosses between them. This plan says who builds what, in which wave, and
with which command the work is accepted. Nothing here changes the tree or the
contracts; where the contracts had to be decided, the decision is in section 5
and in `.scratch/from-zero/contract-errata.md`.

The tickets themselves are `.scratch/from-zero/issues/NN-*.md`, and the rules
every implementer follows are `.scratch/from-zero/spec.md`.

---

## 1. How the build is organised

**Eighteen tickets in seven waves.** A wave is a set of tickets whose inputs are
all merged already and which touch no file in common. Waves run one after
another; the tickets inside a wave run in parallel.

**One worktree per ticket.** Execution goes through
`.claude/skills/ticket-run/SKILL.md`: the main session groups the tickets into
the waves of section 3, pre-checks and commits, then dispatches one workflow per
wave. Inside the workflow each ticket gets its own git worktree and its own
branch off the wave's base commit, an implementer writes the files, a reviewer
reads the diff against the ticket, and the implement-review-fix loop runs up to
five rounds. Branch merging, the accounting ruling and the final review of the
whole branch come back to the main session. Implementer and reviewer models are
sonnet/opus as the skill fixes them; no implementer ever starts a GPU process.

**Two consequences of the worktree.** `external/` is git-ignored and is not
materialised in a worktree, so every acceptance command names its interpreter by
absolute path in the main tree (`/home/y-guo/reproduce/new1/external/...`), which
is also what `constants/path_datasets.yaml`'s `venvs:` map holds. And a ticket
sees only what earlier waves merged: a ticket may never assume a sibling in its
own wave.

**README.md is the one shared file.** Every ticket adds its own files' five
annotation lines (contracts 0.1) to `README.md`; ticket 14 assembles the whole
file from contracts 0.2 and 0.4. Merge conflicts on `README.md` are expected and
are resolved by the main session at wave merge, by keeping every ticket's lines —
**in waves 1 through 4.** At the **wave-5 merge the rule is different**: ticket
14 rewrites `README.md` whole from contracts 0.2 and 0.4 and already carries all
34 entries, ticket 13's four `train/*.py` blocks among them, so the conflict is
resolved by taking **ticket 14's file wholesale and discarding ticket 13's four
blocks**. Keeping both would append a second copy of four entries that are
already there, and nothing downstream would catch it: `readme_entries` returns a
dict, so ticket 14's `D1` and ticket 15's selfcheck check 1 both still count 34.
Diff ticket 13's four blocks against ticket 14's before discarding, and say in
the merge note that you did.

**What the main session runs, and nobody else.** Anything that takes a card,
reaches another host, or changes the harness:

| when | what |
|---|---|
| before wave 1 | nothing |
| after wave 1 | the hosts inventory check (M-G1); the NFS write check (M-G2) |
| after wave 2 | arm the read-only hook in `.claude/settings.json` (ticket 01 ships the script and the snippet, an agent never edits its own harness configuration). **Not after wave 1**: `models/table.yaml` is written by ticket 06 in wave 2, and the hook refuses every `Write`/`Edit` to it; the hook also matches on the path's **tail**, so ticket 04's fixture script — which copies `experimental_settings/*.yaml` into a temp tree with `cp` — is refused too. Wave 2 is the last wave that writes a protected file |
| before wave 3 | `uv pip install --python /home/y-guo/reproduce/new1/external/appworld/venv/bin/python numpy` — `venv: any` includes NumPy (contracts 0.1) and `eval/` fails its import test in that venv without it |
| after wave 6 | the whole GPU list of section 2, then the three end-to-end `--debug` walks of section 4. Their run-directory keys are what ticket 18's TIMELINE entry quotes, so wave 7 does not start until they have been run |

**Every GPU check in this plan is listed for the main session only.** An
implementer that reaches one returns BLOCKED with the ready-to-run command, per
the branch CLAUDE.md.

---

## 2. Per folder: the files, the legacy sources, and the acceptance

Nine folder groups. The per-folder build plans in `.scratch/from-zero/plan-*.md`
hold the full reasoning, the port-by-port "not ported" lists and the script
bodies; what follows is the index. Every check below is a command; where the
command is a multi-line fixture script, the script body is in the ticket that
owns the check, **under the same identifier, in the ticket named beside it**.
Identifiers are unique inside a ticket, not across the eighteen, so a line of
this index that could be read two ways names its ticket.

Interpreters, named once and used by every command:

```
PY_SYS=python3                                                           # 3.10.12, stdlib + PyYAML 5.4.1
PY_PROBE=/home/y-guo/reproduce/new1/external/probe-env/bin/python        # 3.11, torch, transformers, peft, polars, numpy
PY_AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python       # 3.12, appworld, polars
PY_VLLM=/home/y-guo/reproduce/new1/external/vllm-env/bin/python          # 3.12, vllm, polars, numpy
```

### 2.1 settings — `constants/`, `experimental_settings/`, the hook

| file | one line |
|---|---|
| `constants/path_datasets.yaml` | where each environment, its splits and each dataset live, plus the `venvs:` map |
| `constants/path_outputs.yaml` | the NFS outputs root, the debug subdirectory, `login_host`, the host inventory |
| `constants/path_models.yaml` | weights alias -> the directory the weights live in |
| `experimental_settings/schema.py` | every setting field with its default, the axes, the stage table, and the loader (file -> setting, diff, key, run_dir, freeze) |
| `experimental_settings/debug.yaml` | sizes only; `--debug` lays it over any setting |
| `experimental_settings/baseline.yaml` | workflow `sample, score`; named setting `gpt_oss_120b_appworld` |
| `experimental_settings/train_probe.yaml` | workflow `sample, build, train, eval`; `ctool_qwen3_0pt6b`, `cgen_qwen3_0pt6b`, `cparam_qwen3_0pt6b` |
| `experimental_settings/inject.yaml` | workflow `inject, score`; `probe_p1_e1_theta_0pt80`, `no_probe_p1_e1_theta_0pt80` |
| `.claude/hooks/settings_readonly.sh` | the PreToolUse hook that refuses an agent edit to `experimental_settings/*.yaml` and `models/table.yaml` |

**Legacy sources.** `legacy/run.py:63-75` (the interpreter map);
`legacy/envs/collect/run_appworld.py:149` (the AppWorld home);
`legacy/pipeline/configs/p1_gptoss.json:10-14` (the official split files);
`legacy/pipeline/annotate/build.py:303-306` (one task id per line);
`legacy/ops/gpu_jobs.py:124` and `legacy/ops/launch_common.py:41` (the hosts and
the alias map); `legacy/configs/models.json` (the weights aliases and their
notes); `legacy/preset_loader.py:66-148` (the merge discipline);
`legacy/configs/presets/default.json` (the generation defaults);
`legacy/pipeline/train/train_causal_share.py:931-1005` and
`train_causal_tool.py:89-91` (the train defaults);
`legacy/pipeline/annotate/rules.py:20-22`, `build.py:18,205` (the build
defaults); `legacy/pipeline/eval/eval_tool.py:51,279` (the theta grid and the
bootstrap); `legacy/pipeline/inject/live_appworld.py:617-634` (the inject
defaults); `legacy/run.py:76-110` (`CELLS`/`EVAL_CELLS`, which `STAGES`
replaces).

**CPU acceptance** (ticket 01, ticket 04):

- `A1` all seven YAML files parse under all four interpreters -> `7 parsed` x4.
- `A2` `path_datasets.yaml` complete, every path present, split sizes `train 90 / dev 57 / test 168`.
- `A3` `path_outputs.yaml` keys, `login_host == hostname`, host list, card counts `8,10,4,6` summing to 28, and it creates `<root>/debug/`.
- `A4` every `path_models.yaml` alias resolves to a directory that exists.
- `A5` the setting files' shape: workflow lines, section-to-stage membership, `debug.yaml`'s five size blocks.
- `A6` every float is a float and every reference names an existing setting.
- `A7` the hook: three blocks, three passes, two Bash cases, exit code 2 with the message on stderr.
- `B1` `schema.py` imports under all four interpreters and its `ast` import graph names no repo package.
- `B2` every default equals contracts 5.2, and mutable defaults are per instance.
- `B3` `STAGES` has the six stages, the eleven cells and exactly one `carry` upstream (`inject`'s `probe_score.eval`).
- `B4` every axis literal equals what is on disk (run again after every wave).
- `B5` `module_version` / `module_literal`: column zero, exactly once, raising on zero and on two matches.
- `C1`-`C5` the loader on a fixture repo root: the flagship load with the model row expanded, the stage-scoped `--debug` overlay, overrides and the `sweep:` expansion, all eighteen refusals of 5.7 each naming its field, and the per-group reference inheritance.
- `D1`-`D6` keys and the run directory: twelve hex, determinism, `--debug` separation, `meta.notes` insensitivity, a restated default keying identically, the `VERSION` fold and the one carve-out, `run_dir` / `run_dir_of`, `freeze`'s projection and its collision check, `load_frozen`'s round trip and its refusal of a removed field.

**GPU / main session.** None in this folder. Four cross-host or harness items:
`M-G1` the hosts inventory (`ssh` each host, `hostname` and `nvidia-smi -L | wc -l`
against `constants/path_outputs.yaml`); `M-G2` the outputs root writable from
`tokyo106`; `M-G3` rerun the **read-only** commands `B4`, `C1`, `C2` and
`D1`-`D5` against the real tree once every folder has merged — **never `C3`,
`C4` or `C5`, which write into `$FIX/experimental_settings/*.yaml` and would
overwrite the owner's files if `S.ROOT` were the repo root**. (Re-create
`/tmp/mkfix.sh` with the **Write tool**, not a shell heredoc: the armed hook
matches on the path's tail and refuses a `Bash` command whose text carries
`cp experimental_settings/*.yaml`, which that script body does; the Write tool on
`/tmp/mkfix.sh` is not blocked and is the way through.); `M-G4` arm the hook
in `.claude/settings.json` after wave 2 and re-test it through the harness.

### 2.2 data — the three on-disk formats, the probe's input, the builder

| file | one line |
|---|---|
| `data/__init__.py` | the id chain, `read_frame` / `write_frame`, the `VERSION`/`DEFAULTS`/`REQUIRED` rule |
| `data/trajectory_record.py` | the record one task run leaves: six row kinds, the `O_EXCL` claim, the readers, the conversation rebuild |
| `data/training_data.py` | the row `build` writes per cut, with all three methods' targets |
| `data/probe_output.py` | the row `train` writes per example after training |
| `data/probe_input.py` | the cut positions and the text the probe sees, offline and live |
| `data/build_training_dataset.py` | the program: records -> example rows, the split, the gates, the report |

**Legacy sources.** `legacy/pipeline/inject/live_appworld.py:290-299` (the jsonl
writer and the flush rule), `:34-42` (the six row kinds), `:590-603` (the claim
this replaces), `:165-175` (`sent_starts`);
`legacy/envs/collect/run_appworld.py:71-76,180,189-234` (one file per
trajectory, `is_done`, the four sample-side kinds), `:191-215` (the conversation
shape); `legacy/pipeline/annotate/rules.py:26-62` (`SENT_RE`, `boundaries`,
`clip`, `assemble`); `legacy/pipeline/annotate/build.py:61-118` (trajectory ->
event), `:205-228` (event -> sample rows), `:299-318,367-372` (the official
split), `:442-534` (the report);
`legacy/pipeline/annotate/check_callstr.py:20-27,48-51,257-320` (the gates and
the call round trip).

**CPU acceptance** (tickets 02 and 09):

- `A1` (tickets 02 and 09, one apiece) every file imports under the three venv interpreters — ticket 02's over its five, ticket 09's over all six once the builder lands.
- `A2` `data/probe_input.py` also imports under system `python3`.
- `A3` (tickets 02 and 09, one apiece) one column-zero `VERSION = <int>` in the five files that carry one, none in `data/__init__.py`.
- `A4` `REQUIRED` and `DEFAULTS` cover `SCHEMA` in all three formats.
- `B1` the id chain: `50e1ac9_1__s42`, `|s3`, `|c2`.
- `B2` `read_frame`/`write_frame`: round trip, `DEFAULTS` filling, the required-column raise, the version raise, an all-null jsonl column counting as absent, a wrong-typed value raising with the path, and `write_frame` refusing a non-parquet suffix.
- `C1` the two cut rules against values computed from the legacy code: `cuts(T,40,64) == [21,45,60,79]`, `cuts(T,40,3) == [21,60,79]`, `cuts(T,40,2) == [21,79]`, `cuts_live(T,40) == [20,44,59]`, and `max_cuts < 2` raising.
- `C2` `assemble` byte for byte, including the 393-character clip.
- `D1` the claim, the six kinds, the round trip, `is_done` / `owner` / `done_pairs` / `read_dir` / `to_messages` / `release`, run through the real entry points.
- `D2` a killed writer's file reads to its last flushed row.
- `E1` `training_data.write` / `read` and `probe_output.write` / `read`: declared column order, the stamped `version`, the struct-list `args`.
- `E2` a generator's prediction row reads back with the classifier columns null.
- `F1` (ticket 09) `python -m data.build_training_dataset --help` names `--run-dir` and nothing else.
- `F2` (ticket 09) the end-to-end build over a fixture run directory built with the real writers; the fixture script is a scratch copy of the code tree with its own outputs root and its own split-file copies, and `F3`-`F7` are variants of it.
- `F3` (ticket 09) each gate of 2.5 fires and names what it found (seven variants).
- `F4` (ticket 09) the three skip-and-count cases — null action, api-less code block, short thinking — are skipped, counted, and absent from `examples.parquet`.
- `F5` (ticket 09) `consumed.json` names record files and split files, each with a sha1.
- `F6` (ticket 09) the per-split `max_examples` cap is a deterministic function of its input.
- `F7` (ticket 09) the history rule matches the live side: a null-action step leaves no `[HISTORY]` entry, an api-less code block does.

**GPU / main session.** `M-D1` a real `--debug` `sample` run's records build, and
`examples.parquet` has a non-zero row count in **all three** splits. `M-D2` the
`O_EXCL` claim across three hosts, 24 processes, 150 files, exactly 150 winners.

### 2.3 environments — `data/environments/`

| file | one line |
|---|---|
| `data/environments/__init__.py` | the `Environment` base with its nine methods and seven attributes, `StepObservation`, `open_env`, `requested_pairs` |
| `data/environments/appworld.py` | `class AppWorld(Environment)`: the nine methods on the AppWorld package, its instructions, its no-code message, its call syntax |

**Legacy sources.** `legacy/envs/collect/run_appworld.py:24-43` (the developer
message), `:45,149-150,157-160,176,186-190,203-235` (the world, the code-block
regex, the request order, the evaluation);
`legacy/pipeline/inject/rebuild.py:76-78` (the no-code message and its record
mark); `legacy/pipeline/inject/exec_calls.py:137,142,152-229,269-306,545-570`
(the result cap, the seed, `requote`, `error_kind`, the three-step);
`legacy/pipeline/inject/live_appworld.py:305-321,693,754-762,776-778,806-819`
(speculate, the world handling, the frozen clock);
`legacy/pipeline/annotate/rules.py:67,118-164` (`AW_CALL`, `split_args_named`,
`first_call_named`); `legacy/pipeline/annotate/build.py:197-200,299-306`
(`make_call`'s shape, `read_unit_list`);
`legacy/pipeline/inject/parse_call.py:27-69` (`complete_call`).

**CPU acceptance** (ticket 05):

- `A0` / `A0b` imports under the three venvs and, loaded by path, under system `python3`.
- `A1` `StepObservation`'s four fields.
- `A2` `open_env` refuses an unknown environment, naming it and the blocks the file has.
- `A3` `requested_pairs`: per-split cap, split order, task-major seed cross, four exact lists.
- `A4` one column-zero `VERSION`, no `/home/` or `/net/` literal.
- `B0` the seven class attributes: `appworld 1 4000 100 ['v1'] {...} AppWorld`.
- `B1` `tasks` in file order: `train 90 82e2fac_1 aa8502b_3`, `dev 57 50e1ac9_1 4fab96f_3`, `test 168 3d9a636_1 bde252e_3`.
- `B2` `split_args` on the three shapes, span included.
- `B3` `build_call` is the inverse on the four shapes that break a naive join.
- `B4` the round trip over the real p1 corpus: `4074 4040 4040`.
- `B5` `complete_call` on the eight legacy cases: `8 of 8`.
- `B6` the three column-zero literals, no absolute path, no module-level benchmark import.
- `C0` the whole life cycle on one dev task, including `DIR_AFTER False`.
- `C1` `speculate` leaves the world and the clock unchanged, and `spec_s` is a positive float (the check for the frozen process clock).
- `C2` `speculate` before `open` refuses; a second `close` is a no-op.
- `C3` rerun `B0`-`B6` once the world half of `appworld.py` has landed, and paste them.

**GPU / main session.** None: AppWorld is CPU. Three whole-tree checks: a
`--debug` sample walk leaving nine records with the right `meta.split`; a
`--debug` inject walk whose `spec` rows carry the six speculation fields and
whose logs hold no clock-drift `RuntimeError`; `run.py selfcheck`.

### 2.4 models — the table, the two model sides, the two services

| file | one line |
|---|---|
| `models/table.yaml` | one row per alias: `role`, `family`, a keyed `result:` block, an unkeyed `serving:` block |
| `models/__init__.py` | `agent(alias) -> AgentModel`, `probe(alias) -> ProbeModel` |
| `models/agent_models/__init__.py` | empty package marker |
| `models/agent_models/gptoss.py` | harmony: messages -> ids, parse a streamed reply, end of turn, the prefetch wrapping, the family defaults |
| `models/agent_models/service.py` | the vLLM server main and the loop's raw token-stream client |
| `models/probe_models/__init__.py` | empty package marker |
| `models/probe_models/qwen.py` | Qwen's dtype, LoRA targets, head attach point, tokenizer quirks |
| `models/probe_models/base.py` | the probe object: build or restore, save, score, generate |
| `models/probe_models/service.py` | the probe HTTP server, its `check` client, the loop's client |

**Legacy sources.** `legacy/configs/presets/default.json:4-23` and
`legacy/envs/serve_logs/launch_vllm_awdiag.py:55-62` (the serving block);
`legacy/configs/models.json` and
`legacy/pipeline/train/train_causal_tool.py:84-88` (the aliases);
`legacy/model_registry.py:15-28` (the entrance);
`legacy/pipeline/inject/harmony_render.py:34-135` (`render_ids`);
`legacy/pipeline/inject/live_appworld.py:111-148` (`parse`), `:188-270` (the
stream, the retries, the "only when set" rule), `:272-289` (the retrying JSON
client); `legacy/pipeline/inject/inject_format.py:36-37` (`wrap_prefetch`);
`legacy/serve_preset.py:32-56` (the `vllm serve` command);
`legacy/pipeline/train/train_causal_tool.py:191-222,516-536` (the probe object
and the `best/` save); `legacy/pipeline/train/lora_util.py:75-138` (LoRA and the
merge); `legacy/pipeline/inject/probe_server.py:88-277` (the routes, the two
loaders, score and gen, the health echo).

**CPU acceptance** (tickets 06 and 07):

- `A1` every `any` file imports under four interpreters.
- `A2` the two entrances resolve: `agent gptoss gpt-oss-120b gptoss tokyo108 8103` / `probe qwen qwen3-0.6b-base False` / `True True`.
- `A3` the entrances refuse a wrong role and an unknown alias.
- `A4` `gptoss.py`'s six literals read exactly as `schema.py` reads them; the same against `qwen.py`'s two.
- `A5` `parse` over a chunked stream, including a half-written header contributing nothing.
- `A6` `end_of_turn`, and `END_IDS` equal to `openai_harmony`'s `stop_tokens_for_assistant_actions()`.
- `A7` `wrap_prefetch`, both with and without a system text.
- `A8` `render_ids` equals vLLM 0.26.0's own renderer on four message shapes x two efforts: eight `equal: True`.
- `A9` `render_ids` refuses an unpinned effort, an unpinned date and an unknown effort.
- `A10` the probe object on a tiny CPU checkpoint: `score 2 2 True 256 True` / `gen 1 True` / the seven `meta.json` keys.
- `A11` (ticket 06) `forward` at the `event_end` positions: `forward (2, 2) 64`, printed by A10's own script, which it is the tail of.
- `A12` (ticket 06) the LoRA merge equals the base on a fresh adapter, seven target names swapped.
- `A13` the probe service end to end on CPU in render-only mode, including the two `<|end|>` encode directions (`[64, 27, 91, 419, 91, 29, 65]` plain, `[64, 200007, 65]` special) and `/score` answering 503.
- `A14` the agent service's argv and environment without a GPU.
- `A15` the completion request body's keys, and the three that are absent when unset.
- `A16` the annotation and literal rules for these nine files — **one `A16` per ticket**: ticket 06's over its seven, ticket 07's over its two.

**GPU / main session.** `M-M1` the agent service starts, passes its three-line
check table and writes `service_agent_0.json`. `M-M2` the date really reaches the
server (`VLLM_SYSTEM_START_DATE` unset must fail the same check). `M-M3`
`--attach-only` attaches, writes `attached_to` and takes no card; a differing
`served_model_name` refuses. `M-M4` the stream yields `(text, ids)` pairs whose
ids end a turn, with `usage` filled and `close()` returning at once. `M-M5` the
probe service with real checkpoints on a card, `check` issued from `login_host`.
`M-M6` the two refusals: a `param_only: true` gen checkpoint, and a `check`
against the wrong checkpoints. `M-M7` a trained probe reloads from `best/` and
reproduces its validation accuracy to 1e-6, LoRA and full alike.

### 2.5 agent — the loop and the two generation steps

| file | one line |
|---|---|
| `agent/inject_format.py` | the five ways an early result is written into the stream, as one `FORMATS` literal |
| `agent/generate.py` | the plain generation step, and the token stream `inject.py` iterates |
| `agent/inject.py` | the generation step with the probe: score at each live cut, fire, speculate, splice, resume |
| `agent/loop.py` | run each requested triple: claim, open, step, act, judge, close; write the record |

**Legacy sources.** `legacy/pipeline/inject/inject_format.py:1-78` (the whole
table); `legacy/pipeline/inject/live_appworld.py:324-337` (`token_boundary`),
`:340-376` (`find_head`), `:379-383` (`ids_sha`), `:396-408` (`log_resume`),
`:411-569` (`gen_step`, both halves), `:572-587` (the `/health` refusal),
`:606-757` (the program, the rotation, the claim, the per-task guard),
`:759-838` (`run_task`); `legacy/envs/collect/run_appworld.py:109-244` (the
sample-side walk, the heartbeat, the abort capture, the `final` row).

**CPU acceptance** (ticket 11):

- `A1` `inject_format.py` imports under four interpreters and lists the five keys.
- `A2` the four fields, and `needs_special == (placement == "p2")`.
- `A3` the five rendered bodies byte-identical to the legacy table.
- `A4` `system_text` set on exactly `p1_e2` and `p2_e2`, with the legacy paragraph.
- `A5` no control token anywhere in `inject_format.py`.
- `B1` `agent/generate.py` imports under the appworld and probe venvs; `StepResult`'s eleven fields in order.
- `B2` `Clients` has two fields and the file names `probe_models` nowhere.
- `B3` `step`'s ten-parameter signature, identical to `inject.step`'s.
- `B4` the real `generate.step` on a stub client: `step ok stop <|return|>`.
- `B5` `ids_sha` reproduces the legacy sha1.
- `C1` `ARMS` at column zero; `inject.step`'s signature equals `generate.step`'s.
- `C2` `system_text` for the six cases.
- `C3` `find_head` on the legacy lag fixture, and its raise on a mismatched decode.
- `C4` a whole fired step against stub clients and a real record writer: one `spec` row, one `resume` row, the `p1` body, the speculation dict copied in, the discard account.
- `C5` the two control arms never call the probe.
- `D1` `agent/loop.py` imports under the appworld venv and imports `models/__init__.py` nowhere.
- `D2` `-m agent.loop --help` names exactly `--run-dir` and `--piece`.
- `D3` a `--debug`-sized sample walk on stubs: one record file per triple, each ending in a `final` row, plus the heartbeat file.
- `D4` the record's columns read back through `data/trajectory_record.read`.
- `D5` the `/health` refusal in its three forms.
- `D6` two pieces cover the requested list and claim nothing twice.

**GPU / main session.** `M-A1` a `--debug` sample walk end to end, with
`owner_session` matching a session name `run.py ls` prints. `M-A2` a `--debug`
inject walk with a non-zero `spec` row count. `M-A3` the arm comparison: `probe`
vs `no_probe` at the same seed and task, same `meta.generation` text. `M-A4` the
resume account: one `resume` row per `spec` row, and `identical` true on a
majority of rows under `probe_nofill`.

### 2.6 train — the shared loop and the three probe methods

| file | one line |
|---|---|
| `train/utils/trainer.py` | the training loop every method shares, and its last step, the prediction rows |
| `train/methods/ctool.py` | the classification probe: its packing, its head use, its weighted loss, its validation accuracy |
| `train/methods/cgen.py` | the call-generating probe: its packing, its target segment, its exact-match validation |
| `train/methods/cparam.py` | the argument-generating probe: its per-row prompt tail and its derived target |
| `tests/test_packed_loss.py` | the permanent per-method check that the packed loss equals the plain one |

**Legacy sources.** `legacy/pipeline/train/train_causal_share.py:199-241`
(per-block backward and the normalisation), `:243-270` (the heartbeat during a
long validation), `:272-295` (the deterministic generation subsample),
`:1017-1020` (the refusal on an existing log), `:1095-1137` (the optimizer, the
schedule, the log), `:1164-1281` (the update loop);
`legacy/pipeline/train/train_causal_tool.py:97-189,308-323,487-489,509-536`
(events, batches, validation, the weighted loss, the `best/` save);
`legacy/pipeline/train/share_data.py:55-62,169-357,362-533` (the prefix-shared
packing, the block-diagonal mask, the blocks);
`legacy/pipeline/train/train_causal_callgen.py:100-105,137-237,268-365`;
`legacy/pipeline/train/train_causal_param.py:88-197,214-277`;
`legacy/pipeline/train/lora_util.py:122-150`.

**CPU acceptance** (ticket 13):

- `A3.1` the literal rules of 3.3 over the four files, plus the `PROBE_KIND` pair against the eval side.
- `A3.2` the four modules import under the probe venv: `1 classifier generator generator True`.
- `A3.3` the packed loss equals the plain loss per method on a tiny CPU model: three `OK` lines, every `diff` below `1e-4`.
- `A3.4` the whole `trainer.run` on CPU with two stubs: the prediction column list, `['test', 'val'] 24`, the labels, `align_check.json` `True`, `best/` and `train_done.json`, the heartbeat ending `done`.
- `A3.5` the 2.4 continue rule, three states: reuse, predict-only, refuse.
- `A3.6` `python -m unittest tests.test_packed_loss -v`: three tests, `OK`.
- `A3.7` the selfcheck lines for these four files.

**GPU / main session.** `M-T1` a `--debug` train per method with the artefact
list. `M-T2` a deliberately broken packing proves the alignment gate fires
before the first optimizer step. `M-T3` resume from `last/`. `M-T4` the
predict-only continue path. `M-T5` a LoRA run whose `best/` holds merged full
weights. `M-T6` two methods over one build key.

### 2.7 eval — the library, the three metrics, the run scorer, the table

| file | one line |
|---|---|
| `eval/utils/probe_eval.py` | the eval driver, the probe report, the temperature fit, the bootstrap |
| `eval/methods/ctool.py` | fit the temperature and theta on val, freeze on test, write the fired rows |
| `eval/methods/cgen.py` | exact match of the generated whole call at the frozen theta |
| `eval/methods/cparam.py` | exact match of the generated arguments at the frozen theta |
| `eval/score_run.py` | a sample or inject run from its records, by seed, against a baseline |
| `eval/method_table.py` | the backbone x method table from the registry |

**Legacy sources.** `legacy/pipeline/eval/eval_tool.py:213-224` (the temperature
fit), `:227-260` (the first-crossing replay and `agg`), `:279-296` (the
bootstrap), `:500-532,513-518` (the grid and the `chosen` rule), `:598-692` (the
report); `legacy/pipeline/eval/eval_causal_call.py:129-226,379-410,700-745`;
`legacy/pipeline/eval/eval_causal_param.py:93-119,123-292,296-328`;
`legacy/pipeline/inject/score_live.py:57-216`;
`legacy/pipeline/eval/summarize_matrix.py:31-131`.

**CPU acceptance** (tickets 08 and 10):

- `A1` all six files import under the three venv interpreters (after the NumPy install).
- `A2` no `torch`, no `cuda`, no `transformers` anywhere under `eval/`.
- `A3` the literal lines: one `VERSION` in the five stage files, `PROBE_KIND` per method file, none in `method_table.py`.
- `A4` (ticket 08) the classifier path end to end on a fixture: the report fields, `fires.parquet`'s eight columns and 40 rows, `n_events == {"val": 10, "test": 10}`, `done.json`, `report.md`, `consumed.json`.
- `A5` (ticket 08) the temperature fit and the bootstrap: deterministic across two calls, the fixture over-confident rather than separable so the fit lands at about `T = 6.0` inside `1.0 < T < 20.0`, the interval bracketing 0.5.
- `A6a` / `A6` (ticket 10) its own non-debug reference classifier eval, then the two generator methods against it: `exact@0.05` with `n: 10`, `tool_ok: 1.0`, `params_all_ok: 0.8`, `full_call_ok: 0.8`, and no `fires.parquet`.
- `A7a` (ticket 08) / `A7` (ticket 10) `match` is callable from the train side, ticket 10's with the environment, including the dropped `noparam` short-circuit.
- `A8` (ticket 10) `score_run` end to end on a record fixture, then the two refusals (the same-setup gate and the baseline completeness gate).
- `A9` (ticket 10) `method_table.table()` renders a markdown table with the pinned header, and issues no `ssh` against the empty ledger.
- the selfcheck lines for these six files are each ticket's "Selfcheck lines that apply later" section; there is no separate command.

**GPU / main session.** `M-E1` the first real classifier eval over a real
`predictions.parquet`. `M-E2` the generator eval against it, and `run.py table`.
`M-E3` the first real `score` over an inject run and its baseline.

### 2.8 jobs — the registry, the launcher, `run.py`, `README.md`

| file | one line |
|---|---|
| `jobs/registry.py` | rows under a lock, `meta.json`, the heartbeat, the verdicts, `ls/where/find/kill/free/sync`, `RESULTS.md` |
| `jobs/runs.jsonl` | one registry row per stage run, appended at start and at finish; in git |
| `jobs/RESULTS.md` | rendered from `runs.jsonl`; never edited by hand |
| `jobs/launch.py` | the git gate, cards and ports, the tmux pieces, the start row, the alive check, refire, teardown |
| `run.py` | the one command: the stage walk plus `ls, where, find, free, kill, refire, retry, sync, table, selfcheck` |
| `README.md` | the tree, one line per file, how to run, the extension recipes |
| `tests/test_registry_concurrent_append.py` | two pieces appending to `runs.jsonl` at once both land |

**Legacy sources.** `legacy/ops/record.py:47-48,51-83,84-120,137-215,247-267`
(the event stream, the dirty gate, the fold, the render, the patch);
`legacy/ops/gpu_jobs.py:64-94,439-472` (the lock, the per-host `tmux ls`, the
liveness-gated deregistration); `legacy/ops/launch_common.py:41-88` (the alias
map, the local-vs-ssh launch, the fail-closed card probe);
`legacy/ops/launch_cmd.py:196-242,291-314,359-449` (the inner shell command, the
alive check, the launch ordering, refire);
`legacy/ops/verdicts.py:16-116` (the six verdicts);
`legacy/ops/heartbeat.py:15-33`; `legacy/ops/runmeta.py:55-84`;
`legacy/run.py:799-840,1172-1305` (the dirty gate, `tail_of`, the selfcheck and
dispatch shapes).

**CPU acceptance** (tickets 03, 12, 14, 15):

- `A1` `jobs/registry.py` imports under the three venvs and under system `python3`.
- `A2` the re-entrant lock, and a second process really blocking.
- `A3` start row, finish row, fold, `RESULTS.md`, `open_runs`, `find`, on a throw-away tree.
- `A4` `write_meta` / `write_done`: field lists, `owners` growth, no temp file left.
- `A5` the heartbeat file, its `<launch>` index, the four required keys, the final `status: "done"`.
- `A6` the verdicts as pure functions: fourteen pinned lines, all six verdicts of 8.5 among them (the piece dict carries `avg_rate` and `recent_rate`, without which `slowed` is unreachable).
- `A7` `tests/test_registry_concurrent_append.py`: 160 lines land, every one parses.
- `A8` the ledger seed files, and `jobs/runs.jsonl.lock` ignored by git.
- `A9` no absolute cluster path in `jobs/registry.py`.
- `A10` `ls` over an empty ledger probes no host — the line tickets 10 and 14 depend on, since an implementer never runs `ssh`.
- `B1` `jobs/launch.py` imports and has no `__main__`.
- `B2` `git_state` returns the five start-row fields and the real short sha.
- `B3` the ledger exemption and the dirty refusal.
- `B4` the launch gate as a pure decision over rows — six lines, every row's `t` built from the clock, including the `kind != service` clause and the "observed dead needs a beat" rule.
- `B5` placement and ports, five lines and the piece command string.
- `B6` `teardown_services` on a run with no service piece: `[]`, no ssh.
- `B7` `refire` refuses a live piece, against a real local tmux session, with a shim proving no `ssh` was issued (the local-host short-circuit of `registry.session_alive`).
- `B8` no `/home/` or `/net/` literal in `jobs/launch.py`, and no `VERSION` line.
- `C1` (ticket 14) `run.py` usage, the ten reserved names, the missing-workflow message.
- `C2` (ticket 14) the host normalization and the `login_host` refusal.
- `C3` (ticket 14) the read-only subcommands against an empty ledger, with no `ssh` issued.
- `C4` / `C5` / `C6` (ticket 14) `where`, key purity and load-key-freeze, **restricted to what wave 5 can key**: `baseline`'s two stages and `train_probe`'s `sample` and `build`. `train/` is ticket 13's and merges at the end of the same wave, and a `train`, `eval` or `inject` key reads `train/utils/trainer.py`'s and `train/methods/<m>.py`'s `VERSION` lines as source text.
- `D1` (ticket 14) every README entry parses into the five annotations: `34 True`.
- `D2` (ticket 14) the `.py` files **on disk in that worktree**: `30`, every one named in `README.md`. The 34-file check is `D3` below and ticket 18's `C6`.
- `D2` (ticket 15) selfcheck's parsers on fixtures: `literal_of`, `imports_of` with the repo-file join rule, and the two-match refusal.
- `D3` (ticket 15) `run.py selfcheck` green over the whole tree: `34 python files, 0 problems`.
- `D4` (ticket 15) each of the eleven checks fires against a scratch copy of the tree.
- `D5` (ticket 15) `run.py --help` lists the ten subcommands, `selfcheck` among them, in the layout ticket 14 pins (one per line, indented two spaces) — which tickets 16 and 17 parse.
- `D6` / `D7` (ticket 15) the full `where` sweep and the full load-key-freeze sweep, over every stage of every workflow — ticket 14's `C4` and `C6` unrestricted, run in wave 6 once `train/` has merged.

**GPU / main session.** `M-J1` `run.py free` per host, cross-checked by hand, and
fail-closed on a broken ssh. `M-J2` `live_sessions` lists every host's sessions
and reports a session alive when its host is unreachable. `M-J3` the first debug
walk's start row, piece list and tmux sessions. `M-J4` completeness, teardown and
exactly one `ok` finish row. `M-J5` the `service_check` gate produces
`launch_failed` with no loop piece and a completed teardown. `M-J6` refire of one
piece leaves the others untouched and opens `heartbeat/<piece>-1.jsonl`. `M-J7`
`kill` refuses while another run is attached, and `ls` flags the survivor
`orphan`. `M-J8` two `run.py` calls a second apart: the second refuses on the
launch gate.

### 2.9 wrapup — the agent-facing documents and the migration

| file | one line |
|---|---|
| `.claude/skills/gpu-run/SKILL.md` | the GPU lifecycle, rewritten around `run.py`'s stage walk |
| `.claude/skills/gpu-run/references/gpu_state.md` | trimmed to the measured cluster facts (lines 1-55 deleted, 56-97 kept) |
| `.claude/skills/repo-review/SKILL.md` | **new**: the two-day review, the one file of the fixed tree no other ticket writes |
| `.claude/skills/probe-pipeline/SKILL.md` | the chain is one `run.py` call over a workflow file |
| `.claude/skills/exp-status/SKILL.md`, `handoff`, `paper-write`, `ticket-run` | path-and-command edits only |
| `.claude/agents/{gpu-runner,job-monitor,env-runner}.md` | the retired commands replaced |
| `CLAUDE.md` | the steady-state rules of the new tree |
| `.gitignore` | the version-control boundary, with every rule naming a deleted directory removed |
| `docs/` | moved whole to `notes/docs/`, the one move the tree's `notes/` line still asks for |
| `legacy/` | deleted |
| `notes/TIMELINE.md` | one entry appended at the top |

**CPU acceptance** (tickets 16, 17, 18):

- `W1` (ticket 16) the deletions landed; `gpu_state.md` is 42 lines starting at the survey line and holds no sampler token.
- `W2` (ticket 16) `.claude/skills/repo-review/SKILL.md` exists and names `.scratch/review/issues/`.
- `W3` (ticket 16) the four extension places are each named in the probe-pipeline skill.
- `W4` (ticket 16) the Chinese trigger clauses survived in all three skills.
- `C7` (ticket 16 over its three skill directories, ticket 17 over `CLAUDE.md`, `README.md` and all of `.claude/`) no retired command survives; the one exemption is the gpu-run skill's `## What is gone` section, located by its heading text.
- `C8` (tickets 16 and 17) every `run.py <subcommand>` the documents name exists in `run.py --help`.
- `C11` (ticket 17) the diff of the six edited documents is paths and command names only.
- `C12` (ticket 17) the four `ticket-run` prompts are one copy, not two.
- `C13` (ticket 17) `CLAUDE.md` says the five things it must.
- `C15` (ticket 17) no bare `TIMELINE.md` / `RESULTS.md` / `runs.jsonl` / `plans/` spelling survives in `CLAUDE.md` or `.claude/`.
- `C5` (tickets 17 and 18) `run.py selfcheck` exit 0 — a regression check either side of the deletion.
- `C6` (ticket 18) the file count is 34 and every one is named in `README.md`.
- `C9` (ticket 18) `legacy/` is gone and nothing refers to it.
- `C10` (ticket 18) the `.gitignore` boundary still holds, `envs/` included.
- `C14` (ticket 18) the TIMELINE entry is on top and names the real keys.
- `C16` (ticket 18) `docs/` has moved to `notes/docs/` as three renames, and no bare `docs/agents/...` citation survives in `CLAUDE.md`, `README.md` or `.claude/`.

The load-key-freeze sweep and the `where` sweep that an earlier draft of this
list called `C1`-`C4` are ticket 15's `D6` and `D7` and ticket 14's `C3`-`C6`
(section 2.8); they are not run again here.

**GPU / main session.** The three end-to-end walks of section 4, plus `M-W1` the
`<|end|>` encode fixture against a live render-only service (the one open
question of 9(d)), `M-W2` the cross-host rules (`run.py ls` refused off
`login_host`; `run.py free` fail-closed), `M-W3` the two-session gate, and `M-W4`
removing the sampler's crontab line and its resident tmux session on
`login_host`.

---

## 3. The wave table

`Blocked by` names ticket numbers. Every ticket also touches `README.md` for its
own files' lines; that is not a dependency and not a conflict (section 1).

| # | title | files | Blocked by | wave |
|---|---|---|---|---|
| 01 | constants, the setting files, and the read-only hook | `constants/path_datasets.yaml`, `constants/path_outputs.yaml`, `constants/path_models.yaml`, `experimental_settings/{debug,baseline,train_probe,inject}.yaml`, `.claude/hooks/settings_readonly.sh` | (none) | 1 |
| 02 | the three on-disk formats and the probe's input | `data/__init__.py`, `data/probe_input.py`, `data/trajectory_record.py`, `data/training_data.py`, `data/probe_output.py` | (none) | 1 |
| 03 | the registry and the ledger | `jobs/registry.py`, `jobs/runs.jsonl`, `jobs/RESULTS.md`, `tests/test_registry_concurrent_append.py`, `.gitignore` | (none) | 1 |
| 04 | the setting schema and its loader | `experimental_settings/schema.py` | 01 | 2 |
| 05 | the environment contract and AppWorld | `data/environments/__init__.py`, `data/environments/appworld.py` | 01 | 2 |
| 06 | the model table, the entrance, the gpt-oss family and the probe object | `models/table.yaml`, `models/__init__.py`, `models/agent_models/__init__.py`, `models/agent_models/gptoss.py`, `models/probe_models/__init__.py`, `models/probe_models/qwen.py`, `models/probe_models/base.py` | 01 | 2 |
| 07 | the two model services | `models/agent_models/service.py`, `models/probe_models/service.py` | 04, 06 | 3 |
| 08 | the eval library and the classifier metric | `eval/utils/probe_eval.py`, `eval/methods/ctool.py` | 02, 03, 04 | 3 |
| 09 | the dataset builder | `data/build_training_dataset.py` | 02, 03, 04, 05 | 3 |
| 10 | the generator metrics, the run scorer and the matrix table | `eval/methods/cgen.py`, `eval/methods/cparam.py`, `eval/score_run.py`, `eval/method_table.py` | 02, 03, 04, 05, 08 | 4 |
| 11 | the agent loop: formats, generation, injection, the task walk | `agent/inject_format.py`, `agent/generate.py`, `agent/inject.py`, `agent/loop.py` | 02, 03, 04, 05, 06, 07 | 4 |
| 12 | the launcher | `jobs/launch.py` | 01, 02, 03, 04, 05, 06 | 4 |
| 13 | the training loop and the three probe methods | `train/utils/trainer.py`, `train/methods/ctool.py`, `train/methods/cgen.py`, `train/methods/cparam.py`, `tests/test_packed_loss.py` | 02, 03, 04, 05, 06, 08, 10 | 5 |
| 14 | `run.py`: the walk and the nine subcommands, and `README.md` | `run.py`, `README.md` | 02, 03, 04, 05, 08, 10, 12 | 5 |
| 15 | `run.py selfcheck` | `run.py`, `README.md` (only when a line of it is wrong) | 13, 14 | 6 |
| 16 | the gpu-run, probe-pipeline and repo-review skills | `.claude/skills/gpu-run/SKILL.md`, `.claude/skills/gpu-run/references/gpu_state.md`, `.claude/skills/gpu-run/references/launch-methodology.md` (delete), `.claude/skills/gpu-run/references/monitor-methodology.md` (delete), `.claude/skills/gpu-run/scripts/gpu_status.sh` (delete), `.claude/skills/probe-pipeline/SKILL.md`, `.claude/skills/probe-pipeline/references/*` (delete), `.claude/skills/repo-review/SKILL.md` (new) | 14 | 6 |
| 17 | `CLAUDE.md`, exp-status, the agents and the remaining skills | `CLAUDE.md`, `.claude/skills/exp-status/SKILL.md`, `.claude/agents/gpu-runner.md`, `.claude/agents/job-monitor.md`, `.claude/agents/env-runner.md`, `.claude/skills/handoff/SKILL.md`, `.claude/skills/paper-write/SKILL.md`, `.claude/skills/ticket-run/SKILL.md`, `.claude/skills/ticket-run/prompts/*.md`, `.scratch/from-zero/prompts/implementer.md` (its `legacy/` lines, before the copy) | 15, 16 | 7 |
| 18 | the migration: move `docs/`, delete `legacy/`, clean `.gitignore`, write the TIMELINE entry | `docs/` (`git mv docs notes/docs`), `legacy/` (delete), `.gitignore`, `notes/TIMELINE.md` | 15, 16 | 7 |

Wave sizes: 3, 3, 3, 3, 2, 2, 2. Between wave 6 and wave 7 the main session runs
the GPU list of section 2 and the three walks of section 4; ticket 18 quotes
their keys.

**Ticket 14 stays in wave 5, beside ticket 13, and its acceptance is cut to fit.**
`run.py` imports nothing from `train/`, so it can be written before `train/`
exists — but `schema.key("train", cfg)` reads `train/utils/trainer.py`'s and
`train/methods/<m>.py>`'s `VERSION` lines as source text, and an `eval` or
`inject` key folds a train key. So ticket 14's `C4`, `C5` and `C6` cover
`baseline`'s two stages and `train_probe`'s `sample` and `build` only, its `D2`
expects the **30** Python files that exist in its worktree while `README.md`
already carries all 34 entries, and the full `where` and load-key-freeze sweeps
move to ticket 15 as `D6` and `D7` in wave 6. The alternative — moving ticket 14
to a wave of its own — would serialize waves 5 through 8 for one dependency that
only the acceptance has.

---

## 4. The end-to-end acceptance: three `--debug` walks

The acceptance of the whole tree is that each of the three workflow files walks
under `--debug`. The main session runs them under the rewritten gpu-run skill;
cards are picked by `run.py` itself, so no card is named by hand. Each walk is
run twice: the first call launches and stops, the second call — once the pieces
have finished — writes `done.json`, appends the finish row, tears the service
pieces down and continues into the next stage.

```
PY=/home/y-guo/reproduce/new1/external/probe-env/bin/python
$PY run.py baseline    gpt_oss_120b_appworld  --debug      # workflow: sample, score
$PY run.py train_probe ctool_qwen3_0pt6b  --debug      # workflow: sample, build, train, eval
$PY run.py train_probe cgen_qwen3_0pt6b   --debug
$PY run.py train_probe cparam_qwen3_0pt6b --debug
$PY run.py inject      probe_p1_e1_theta_0pt80  --debug \
   "inject.probe_score={key: {train: <KS>, eval: <KE>}}" \
   "inject.probe_gen={key: {train: <KG>}}" \
   "score.baseline={key: {sample: <KB>}}"
$PY run.py ls --debug
```

The four pinned keys come from `run.py where ... --debug` on the runs the first
three walks produced. The pinning is the errata line for contracts 3.4 / 9(c)#8:
a resolved reference is always keyed **without** the debug overlay, so a named
reference would point at a real directory that has never existed; the `key:` form
of 5.4 pins it instead, `ls` flags the run `pinned`, and the inheritance check,
2.5's shared-build-key gate and 5.7's baseline superset refusal are skipped.

**What each stage must leave on disk.**

| stage | in `<root>/debug/<stage>/<key>/` |
|---|---|
| `sample` | `settings.yaml`, `settings_diff.yaml`, `meta.json`, `records/<task_id>__s<seed>.jsonl` x 9 (3 splits x 3 tasks x 1 seed), each ending in a `final` row and carrying a `meta.split` from `{train, dev, test}`; `heartbeat/<piece>-0.jsonl`; `log/<piece>.txt`; `service_agent_0.json` and `service_probe_0.json` while the services run; `done.json` with a `pairs` list of length 9 after the second call, and both service sessions gone |
| `build` | `examples.parquet` with a non-zero row count in **all three** of `train`, `val`, `test`; `consumed.json` naming the record files and the split files with sha1s; `report.md`; `heartbeat/0-0.jsonl`; `done.json` whose `counts` carries the records, events, skipped events and per-split example counts |
| `train` | `align_check.json` with `"PASS": true` and a difference below `1e-4`; `train_log.jsonl` with `start`, `step`, `eval` and `save_best` lines; `best/` with `meta.json` (`backbone`, `tuning`, `labels` for ctool, `call_sep`, `param_only`, `max_len`, `train_key`); `train_done.json`; `predictions.parquet` whose `split` column holds exactly `val` and `test`; `consumed.json`; `done.json` with `metrics.objective` and `stage_extra.labels`; `heartbeat/0-0.jsonl` ending `"status": "done"` |
| `eval` | `probe_report.json` (a `temperature`, a `chosen` entry per risk target, `frozen` numbers with a bootstrap interval); `fires.parquet` for a classifier and none for a generator; `report.md`; `consumed.json`; `done.json` with `metrics` of the form `<stat>@<risk>` |
| `inject` | the same shape as `sample`, plus `spec` and `resume` rows in the records, and `_resolved.probe_temperature` in `settings.yaml`. The probe service piece holds one card and carries `--score-ckpt`, `--gen-ckpt` and `--temperature`; `jobs/launch.py` runs the `check` client before the first loop piece |
| `score` | `run_report.json` (the run block, the baseline block, the paired block, the spec block, the resume block, by seed), `report.md`, `heartbeat/0-0.jsonl`, `done.json` |

**Three facts to measure while the walks run, and report as facts only.** The
seconds per generated prediction row for `cgen` and for `cparam`, extrapolated to
the full example count (contracts 9(d) and 9(a)#2); which way the `<|end|>`
encode fixture comes out on this backbone, which decides whether the `p2_*`
injection formats are runnable at all; and whether a `--debug` inject run with
`arm: probe` crosses `theta` at all (if it never does, rerun once with
`inject.fire_nth_cut=1` to force one fire through the whole path).

---

## 5. Contract errata

`.scratch/from-zero/contract-errata.md` holds the full list, 131 entries, in the
format `<contracts section>: <what it says> -> <what the build does> (planner:
<folder>)`. The nine folder planners contributed 111 of them, the integrator six
(below), the round-1 ticket review six more, marked `planner: reviewer round 1`
— the piece dict's two rate keys, the launch gate's "observed dead" rule and
`gate_open_row`'s `beats` argument, `ctool`'s `Batch["target"]` carrying a class
name, where `generation.{stop, effort, date}` are resolved, `Writer.row` refusing
a stamped column, and `ls` probing no host over an empty ledger — and the round-2
ticket review eight more, marked `planner: reviewer round 2`:
`data/trajectory_record.REQUIRED` cut to the twelve columns every record file carries,
the per-task guard's `final` row and its `meta`-first rule, `inject.py`'s
`bounds` starting at `(0, 0)`, `loop.main`'s `piece` being the `(i, n)` pair,
`registry.session_alive`'s local-host short-circuit, `launch.is_ledger_path`,
the pinned `run.py --help` layout, and the `docs/` -> `notes/docs/` move.
The six the integrator had to settle, because two folders disagreed or because a
stated gate would have stopped every build, are:

1. **1.1, the `dir` parameter.** The data plan makes `dir` the run directory and
   has `data/trajectory_record.py` append `records/`; the jobs and eval plans pass
   `<run_dir>/records`. The build takes the first: `open_record`, `record_path`,
   `done_pairs`, `read_dir` and `release` are all called with the **run
   directory**, and only `data/trajectory_record.py` spells `records/`.
2. **2.5, a non-null action that `split_args` returns None for.** Stated as a
   hard stop. Measured over all 315 p1 trajectories on 2026-09-17: **34 of 4,074
   non-null actions (0.83%), in 22 trajectories** — 24 (in 13 trajectories) are
   code blocks that call no api at all, and 10 (in 9 trajectories) name an api
   whose call never closes its parentheses for the paren walk. So the gate as
   written stops every build over real data. The build skips such an event and
   counts it as `counts.events_skipped_no_call`, listed in `report.md`, exactly
   as a null action is — which is the same reasoning 2.5 itself uses to demote
   the unseen-tool gate to a report line. **Worth the owner's eye** (section 6).
3. **6.2, gradient checkpointing.** The models plan names
   `enable_grad_checkpointing()`, the train plan `grad_checkpointing(enabled)`.
   The build takes the train plan's three names, because `train/utils/trainer.py`
   is the caller: `Probe.trainable_parameters()`, `Probe.set_training(flag)`,
   `Probe.grad_checkpointing(enabled)`.
4. **6.3, the hosts inventory.** The settings plan writes 4/8/8/8 cards. The
   build writes the measured table of
   `.claude/skills/gpu-run/references/gpu_state.md`: tokyo105 (alias shiga) 8,
   tokyo106 10, tokyo107 4, tokyo108 (alias saitama) 6 — 28 in total.
5. **5.2, `train_probe.yaml`'s named settings.** The settings plan ships
   `ctool_qwen3_0pt6b` and `cgen_qwen3_0pt6b` only, while the loader's `param_only` refusal and
   the cparam `--debug` walk both need a cparam setting. The file also ships
   `cparam_qwen3_0pt6b`, whose `eval.theta_from` is `train_probe/ctool_qwen3_0pt6b`.
6. **0.1, the interpreter paths in every acceptance command.** `external/` is
   git-ignored and absent from a worktree, so a relative
   `external/probe-env/bin/python` does not resolve where an implementer works.
   Every command in every ticket names the interpreter by its absolute path in
   the main tree, which is what `constants/path_datasets.yaml`'s `venvs:` map
   holds.

---

## 6. Open decisions for the owner

Facts and open questions only; no recommendation is attached to any of them.

1. **Two keyed inject fields have no reader.** `inject.chunk_tokens` and
   `inject.tail_tokens` are in the inject key and in `meta.inject`, and nothing
   reads them: legacy's v4 rewrite to one stream per step left them unused
   (`live_appworld.py:95-108,442-455`) and the port follows v4. Either they get a
   reader or they leave the key.
2. **An action `split_args` cannot parse.** Errata 2 above skips and counts it.
   The contract as written stops the build. The measurement is 34 of 4,074
   non-null actions, 0.83%, in 22 of 315 trajectories: 24 code blocks that call
   no api at all, and 10 whose api call never closes its parentheses for the
   paren walk. The second kind is not "a code block that calls no api"; both are
   counted under one name, `events_skipped_no_call`.
3. **Validation cadence.** `validate` runs at every epoch end, plus once at the
   end of training when `train.max_steps` cut the last epoch short. Legacy had
   `--eval-per-epoch 4`; no schema field exists for it. Adding
   `train.evals_per_epoch` with a default of 1 would change no key (3.3).
4. **`train.warmup_ratio` defaults to 0.0**, while legacy hardcoded
   `int(steps * 0.05)`. A setting that wants the old schedule writes
   `warmup_ratio: 0.05`.
5. **The cost of predicting at every cut row.** Measured during the walks of
   section 4 for `cgen` and `cparam`, and extrapolated to the full example count.
   The fallback (`train.predict.trigger_run`, 9(a)#2) is written down and not
   built.
6. **Whether the `p2_*` injection formats survive** the encode contract on this
   backbone. The `check` client's `<|end|>` fixture measures it; the walks of
   section 4 use `p1_e1`, which needs neither direction.
7. **The setting YAML files are a placeholder.** The build ships one workflow
   file per tree line with the named settings above, whose values are schema
   defaults except where a required field or a reference forces one. They are
   gyb's files and gyb overwrites them.
8. **`notes/CONTEXT.md`'s obsolete entries.** Sampler, Window, Escalation line,
   Incident agent, Autopsy, Incident record, Sampling history, the sampler's half
   of Verdict, Ledger, Refire's quota sentence, shardable, Monitoring parameters
   and chat baseline all describe machinery that no longer exists. An agent does
   not edit `notes/`, so ticket 18 lists them inside the TIMELINE entry and the
   rewrite is gyb's.
9. **What the deletion of `legacy/` gives up**, all of it reachable at tag
   `checkpoint-2026-09-17-before-from-zero` and commit `647dc45`: the offline
   replay line, the five non-AppWorld environments, the read-only axis, the
   self-fire head, `--overlong skip` and `drop-event`, the probing-cost and
   economics tables, the mbert line, the presets and the collection manifests,
   and the chat-endpoint collection path.
