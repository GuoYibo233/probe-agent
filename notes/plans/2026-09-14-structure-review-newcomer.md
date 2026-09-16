# Review of the from-zero structure plan, perspective 1: the future reader

Written by a read-only Fable 5.1 reviewer (effort max) at gyb's request on
2026-09-14. Input: `plans/2026-09-14-structure-from-zero.md` at commit 07adb8f.
Role given: a new PhD student who joins in six months, reads only the README
(the Part 1 tree plus the two short sections) and Part 2 as docstrings, and
walks nine scenarios. Reproduced verbatim below, with the HTML entities of the
transport decoded.

---

## Verdict

The tree is readable and most file names now say what the file does; the fixes for `rules.py`, `harmony`, `probe_model.py` and the trainer split hold up. Two things a newcomer cannot get right from the plan text: what the probe is actually shown (the plan's own module lines contradict today's code) and how a setting in one workflow file refers to a run of another (ambiguous name, shared sections not carried over, the example itself inconsistent). The settings design is understandable apart from that reference rule, the missing forced-rerun entry, and the key leaving seeds out; fix findings 1 to 6 before the README is written, the rest is naming.

## Findings

**1. The probe's input has no single home, and `probe.py`'s signature describes a mechanism that does not exist.**
Plan: `agent_model.stream(prompt_ids)` exists "because the probe needs the exact prefix" (Part 2, `models/agent_model.py`) and `Probe.score(prefix_ids)` (Part 2, `models/probe.py`). Today `/score` and `/gen` receive `text=assemble(task, hist, t_all[:cut])` (`pipeline/inject/live_appworld.py:482-483`, `:500-501`), an assembled prompt with `Task:` / `[HISTORY]` (last 3 rounds, results clipped to 400 chars) / `[THINKING]` markers (`pipeline/annotate/rules.py:21-22`, `:55-62`), tokenized by the probe's own tokenizer (`pipeline/inject/probe_server.py:164-167`). The raw id stream serves the splice seam (`live_appworld.py:486-494`), not the probe. So the plan gives the cut positions one home (`cut_points.py`) but the prompt the probe reads has two: `build.py` offline ("the prompt of the example") and `generate.py` live (unstated). A newcomer who changes the prompt for training silently diverges the live run, which is the drift the plan set out to remove. Change: one file, `data/probe_input.py`: "where in the reasoning the probe is asked, and what it is shown (task, clipped history, thinking prefix)", used by `build.py` and `generate.py`; `Probe.score(text)`; delete the "exact prefix" sentence from `agent_model.py` (the raw stream is for splicing). If the plan intends the probe to read raw agent tokens, that is a method change and must be said out loud.

**2. `<workflow>/<setting>` references are ambiguous and carry no shared sections; the plan's own example is inconsistent.**
Plan: editing a setting gives a new directory and keeps the old one ("If you edit a setting"); `inject.probe: train_probe/ctool_on_qwen06`, "the ledger resolves the name to the directory" (Part 2, after the yaml blocks). Which directory, when the name has two keys? Also the inject stage reads `data, models, generation, probe` (stage table), but the example inject setting states none of them, so they come from `config.py` defaults, not from the probe's training run. The example already shows the failure: `train_probe` common uses `gptoss20b`, `baseline.yaml` defines `gptoss120b_appworld`, `inject.yaml` references `baseline/gptoss20b_appworld`, which is defined nowhere; `gptoss20b` is not in today's model table (`configs/models.json:24-27`). Change: one paragraph stating (a) a name resolves by loading that workflow's setting as it is now and recomputing its key chain; a missing directory stops the walk and prints the command that produces it; `<workflow>/<setting>__<key>` pins an old one; (b) the referencing setting inherits the referenced run's shared sections (`data`, `models`, `generation`, `probe`), and any value it states differently is a load error unless listed under an explicit `override:`. Fix the example.

**3. Call syntax is per environment; `call_syntax.py` "the one regex" is AppWorld's.**
Plan: tree line for `data/call_syntax.py` and Part 2 ("the one regular expression"). Today: `AW_CALL` and `BFCL_CALL` (`pipeline/annotate/rules.py:67-68`), the 13 ALFWorld templates and `ALF_CALL` (`rules.py:203-265`), `TAU2_CALL` (`envs/collect/run_tau2.py:169`), the `ACTION:` line (`envs/collect/run_alfworld.py:88`), the python fence (`envs/collect/run_appworld.py:45`). The environment's five methods (Part 2, `data/appworld.py`) do not include "what a call looks like", so scenario 5 has nowhere to put ALFWorld's grammar. Change: make call finding the sixth method of the environment file (`calls(text)`, `complete_call`), keep `call_syntax.py` only for what is shared (argument splitting), and say so in the tree line.

**4. A second environment needs its own uv environment; the three-environment header breaks at scenario 5.**
Plan: three uv environments and `# env: agent | probe | vllm | any` (tree line for `envs/`; "What keeps the tree this shape", item 2). Today nine interpreters (`run.py:63-75`); alfworld has its own venv (`run.py:68`, `.gitignore:45`) because AppWorld pins pydantic 1 (`envs/collect/common.py:15-18`). Change: the header names the venv (`# env: appworld`), "agent" means "the venv of the environment named by `data.env`", and the `STAGES` sample row takes its environment from the environment file.

**5. Seeds and tasks are outside the key, so a downstream stage goes stale silently.**
Plan: "asking for more tasks or seeds adds files to the same directory (the task list and the seed list are left out of the key on purpose)"; build and score key only on upstream keys and `VERSION` (Part 2, "Identity, reuse, versions"). A build that consumed one seed stays "done" after the sample gains two more; same for a baseline's score. Change: build and score list the seeds and the task count they consume in their own section, keyed; a mismatch with the upstream directory is reported by `run.py ls`. Also `sample: {traj_per_task: 3, seeds: [42, 67, 4267]}` is redundant: today `len(seeds) == n` is enforced (`envs/collect/run_appworld.py:65-67`); keep `seeds` only.

**6. No forced rerun and no "run from a saved settings file": scenarios 7 and 8 stall.**
Plan: the `run.py` command list (Part 2, `run.py`) has no `--force` and takes only names from the current file; `VERSION` is bumped "when its output changes meaning for the same settings, and only then". Rerunning an old run at its commit recomputes the same key and is skipped; adding a metric to `score_run.py` is not a meaning change, so old score directories stay "done" and never gain the field. Change: add `--force` (reruns the stage into a fresh directory, old one kept), `run.py <dir>/settings.yaml` as an accepted first argument, and one sentence: "a new output field bumps `VERSION` of a quick stage (build, score); for train and eval use `--force`".

**7. "Record" means two things; "setting" and "config" mean one thing.**
`task_record.py` is "the record one task run leaves" while `ledger.py` is "the record: runs.jsonl rows" and `launch.py` "write[s] the record's start" (tree lines 55, 86, 87; Part 2, `scripts/ledger.py`). And `settings/config.py`, run-dir `config.yaml`, `diff.yaml`. Change: ledger text says "ledger" only; `settings/shape.py`; run-dir `settings.yaml` and `settings_diff.yaml`.

**8. The system prompt is composed by three files and no line says so.**
Today: the environment instructions (`envs/collect/run_appworld.py:24`) become the developer message (`envs/collect/common.py:118-120`); the harmony system message with date and effort is separate (`common.py:21-30`); the injection format appends a paragraph (`pipeline/inject/inject_format.py:31-34`, applied at `live_appworld.py:389`). Plan: `appworld.py` "also its system prompt"; `template_gptoss.py`; `inject_format.py`. A newcomer editing "the system prompt" opens `models/` first. Change: `appworld.py`'s line reads "the task instructions the agent reads (the developer message)"; `template_gptoss.py`'s line adds "(and the model's own system message: date, effort)".

**9. The two clients are in different places.**
`models/agent_model.py` is an HTTP client, while `models/probe.py` loads weights; the probe's client is "a small class at the top of `agent/generate.py`" (Part 2). A newcomer looking for "how the loop talks to the probe" opens `serve_probe.py` or `probe.py`. Change: `models/agent_client.py` and `models/probe_client.py` (stdlib), side by side with the two `serve_*.py`.

**10. Tree inconsistencies a reader trips on.**
`RESULTS.md` is at the root (line 33) and in `ledger/` (line 91). `logging.tracker` (Part 2, "Logs and tracking") is an eleventh section not in the list of ten. `ledger/gpu_state.md` is hand-written cluster notes, not a ledger; it matches `constants/` ("written by hand; nothing in here changes a result"). `scripts/ledger.py` is imported by every stage for heartbeats and name resolution (today `ops/heartbeat.py:19`, imported at `envs/collect/run_appworld.py:20-21`), so "scripts" misleads.

**11. A fourth method touches five files and nothing lists them; values are not validated.**
Plan: method rows in `build.py`, `probe.py`, `train.py`, `eval_probe.py` (Part 2); the loader rejects unknown keys, not unknown values. Scenario 3 becomes a grep for `ctool`; scenario 9 cannot make an old setting fail loudly. Change: `shape.py` declares the allowed values of each axis (`method`, `tuning`, `format`, `env`, `template`) and the README's extension list names the four files.

## Scenario walkthroughs

1. **Learning rate.** `settings/train_probe.yaml`, `train: {lr: ...}` under the named setting; `run.py train_probe ctool_on_qwen06 --launch`; sample and build reused, train and eval get new directories. Hesitation: edit in place or add a new name? Both work, but an in-place edit silently retargets every `inject.probe: train_probe/ctool_on_qwen06` (finding 2).
2. **Warmup steps.** `settings/config.py`, one field with default `0` in the `train` dataclass; read it in `train/train.py`; no `VERSION` bump. No hesitation.
3. **Fourth method.** `config.py` (values, not stated), `data/build.py`, `models/probe.py`, `train/train.py`, `eval/eval_probe.py`; bump build's `VERSION` (its output gains a file). Hesitation: no list of these files anywhere (finding 11).
4. **Qwen3-8B agent.** `constants/models.yaml` row, `constants/path_models.yaml` row, `models/template_qwen.py` (a hand-assembled Qwen prompt exists today, `envs/collect/common.py:97-102`), one named setting in `baseline.yaml`. Hesitations: two constants files for one model; whether `generation.date`, which is gpt-oss's "Current date" (`common.py:24`), is ignored by Qwen; whether `to_messages()` in `task_record.py` depends on the template's `parse`.
5. **ALFWorld.** `data/alfworld.py`, a `path_datasets.yaml` row, a named setting. Stuck on: the call grammar (finding 3), the venv (finding 4), and per-environment constants such as the step cap (`pipeline/annotate/build.py:241`) that the plan's `build.py` (reads `build` only) does not mention.
6. **Two temperatures.** Two baseline settings and two inject settings, each stating `generation.temperature`, each inject naming its baseline. Hesitation: the inject example omits `generation`, so I do not know it is honored, or whether it must equal the probe's training temperature (finding 2).
7. **Last month's run.** `run.py find probe.method=ctool` → `run.py where` → `diff.yaml`, `meta.json` commit → `git checkout`; then the same command is skipped as done (finding 6). A pre-renewal row has `run_id`, `track`, `cmd` and no key (`ops/runs.jsonl`, last row), so `find` by field cannot see it.
8. **New live metric.** `eval/score_run.py`; `VERSION`? (finding 6). Wall-clock per fired call needs timestamps in the speculation event; today's event fields are cut, confidence, call, requote branch, result (`live_appworld.py:37`), so `agent/speculate.py` and `loop.py`'s record `VERSION` change too, and inject reruns. The README must say where the record's fields are listed.
9. **Retire a method.** Delete its rows in the four files and its value in `config.py`, delete the named settings; ledger rows and NFS directories stay. Hesitation: whether `run.py ls`/`find` still show rows whose method no longer loads; the plan should say `find` never validates against the current shape.

## Names

| current name | verdict | proposed name | reason |
|---|---|---|---|
| `settings/config.py` | change | `settings/shape.py` | "setting" and "config" name one thing; the plan itself calls it "the shape" |
| run dir `config.yaml` / `diff.yaml` | change | `settings.yaml` / `settings_diff.yaml` | same |
| `data/cut_points.py` | confirm, widen | `data/probe_input.py` | clear replacement for `rules.py`; must also hold what the probe is shown (finding 1) |
| `data/call_syntax.py` | confirm the name, not the scope | keep; move the regex into the environment file | it is AppWorld's syntax (finding 3) |
| `data/task_record.py` | confirm | keep | clearer than `trajectory.py`; strip "record" from the ledger lines |
| `data/build.py` | change | `data/build_dataset.py` | "build" alone reads as a packaging step |
| `models/template_gptoss.py` | confirm | keep | says the model and that it is a format; `harmony` is now a parenthetical |
| `models/agent_model.py` | change | `models/agent_client.py` | it is a client; `probe.py` beside it loads weights |
| class at top of `agent/generate.py` | change | `models/probe_client.py` | both clients beside both servers |
| `models/probe.py` | confirm | keep | the line "backbone plus head; load, score, generate" answers gyb's "what does this file do?" |
| `train/train.py` | confirm | keep | one trainer, method and tuning as values |
| `eval/matrix.py` | change | `eval/method_table.py` | "matrix" is project jargon |
| `scripts/` | change | `ops/` | it holds a library every stage imports (heartbeat, resolve), not run-me scripts |
| `ledger/gpu_state.md` | change | `constants/gpu_state.md` | hand-written cluster facts, not a ledger |
| `envs/` | keep, reword the line | — | one word for uv environments and benchmark clones; the line must name both |

## What the plan gets right

- One trainer with method and tuning as values; the alignment proof as a test, not a stage.
- `--debug` as an overlay on the same code path, outputs outside the ledger.
- The key: differing values plus upstream keys plus `VERSION`; the commit recorded, not keyed.
- Resolved settings and diff saved in every run directory; `ls`/`where`/`find` over the ledger.
- The environment behind a fixed set of methods; the loop never holds environment code.
- The date as a settings value: today two constants disagree (`envs/collect/common.py:60` 2026-08-06; `pipeline/inject/rebuild.py:90` 2026-07-31).
- The selfcheck rule against `/home/` and `/net/` in code: today `probe_server.py:83-85`, `live_appworld.py:83`, `exec_calls.py:131`.
- OmegaConf without Hydra; delete instead of archive.

## README must add

1. The one-paragraph story: what the probe predicts, what runs early, the five stages and what each writes.
2. The extension recipes: a hyperparameter (one file), a method (four files plus the value list), an agent model (two constants rows plus a template file), an environment (one file, one row, one venv), a metric (one file plus `VERSION`).
3. Which uv environment runs each stage, the `# env:` header, and that a benchmark environment brings its own venv.
4. What the probe is shown and that offline and live share one file for it.
5. The three parts of the system prompt and their files.
6. The reference rule `<workflow>/<setting>`, what is inherited from the referenced run, and how to pin an old key.
7. When `VERSION` is bumped and when `--force` is used.
8. What `--debug` shrinks and what it does not (the agent model still needs a card; there is no small gpt-oss in the table).
9. The NFS output root and directory pattern; pre-renewal ledger rows are found by `run_id`, not by key.
10. A ten-term glossary: probe, cut, fire, speculate, inject, theta, method, tuning, backbone, format, plus workflow, setting, stage, key, piece.
11. Commit before launch and the dirty-tree refusal.

Keep out: the "Replaces ..." lists, the OmegaConf-versus-Hydra reasoning, the tracker discussion, the two-day review procedure, the not-carried-over list, file counts, the ancient-memory rule (CLAUDE.md).

## Open questions

**(a) ALFWorld in the tree.** From the newcomer's seat a file that is listed but does not run is worse than no file: the README line would be false and the two-day review would flag it forever. Today's ALFWorld driver runs in its own venv with its own prompt and grammar (`envs/collect/run_alfworld.py:1-70`, `rules.py:203-265`), and none of it has been exercised by the probe pipeline recently. Leave it out, but design for it now: put call finding into the environment file (finding 3) and name the venv in the header (finding 4), so that "a second environment is one file" is true when it comes back. Add one README line under `data/`: the file name and the commit that holds it, because a newcomer cannot ask git for a file they do not know existed.

**(b) The notebooks line.** "Throwaway work" does not tell me what I may do. Say the three rules plainly: a notebook imports any module and no module imports a notebook; a notebook never writes into an output directory or the ledger, and no number in `RESULTS.md` comes from one; a notebook that produces a figure or a table becomes a script under `figures/`. And say whether they are committed; if yes, with outputs cleared, and not listed one per line in the README.
