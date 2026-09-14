# Three reviews of the from-zero structure plan: synthesis

2026-09-14. Three read-only Fable 5.1 reviewers (effort max) read
`plans/2026-09-14-structure-from-zero.md` at commit 07adb8f, each from one
seat:

- the future reader: `plans/2026-09-14-structure-review-newcomer.md` (11 findings, nine scenario walkthroughs, a names table)
- the engineer who builds it: `plans/2026-09-14-structure-review-builder.md` (15 findings, an environment table, a merger table, the homeless code, what the loader must do)
- the experiment-management skeptic: `plans/2026-09-14-structure-review-skeptic.md` (15 findings, a key failure table, five workflow shapes, the monitor protections, the abstraction bar)

The main session spot-checked the three claims that change the design most,
and all three hold: the probe is scored on an assembled text prompt, not on
raw token ids (`pipeline/inject/live_appworld.py:482-483`,
`pipeline/annotate/rules.py:55-62`); the live run loads a ctool run and a cgen
run and reads its score temperature from the eval report
(`pipeline/inject/probe_server.py:118-119, 154-156`); a task file counts as
done when it holds a final record, which an aborted task also gets
(`envs/collect/run_appworld.py:79-82, 221-235`).

All three reviewers accept the layer cut, the settings-as-workflow-files idea,
the key with the commit recorded but not keyed, the debug overlay, the shared
modules in `data/` and `models/` (each verified against three or more copies
today), and the deletions.

## A. Confirmed errors, fixed in the third draft without asking

Each line names the finding (N = newcomer, B = builder, S = skeptic).

1. **What the probe reads.** The probe scores an assembled text: the task, the last three tool rounds with results clipped, and the thinking prefix. One module, `data/probe_input.py`, holds the cut positions and that assembly, used by the builder offline and by the generation step live; the raw token stream serves only the splice. The two cut rules that exist today (offline: sentence ends thinned to 64; live: sentence starts, unthinned) become one, the live one, with the builder's cap a keyed setting; every existing dataset changes. (N1, B5, S8)
2. **Inject needs two probes and eval's temperature.** `inject.probe_score` names a ctool eval run, `inject.probe_gen` a cgen eval run; inject's upstream stage is eval, not train. (B4)
3. **Keys.** A consumer of sample or inject files keys on the subset it consumes (split, seeds, task count) and reads an explicit file list, never a glob; `traj_per_task` is dropped, the seed list is the count. A reference `<workflow>/<setting>` resolves by loading that setting from its file and recomputing its key chain; the resolved key enters the referencing key; a bare key may be written instead of a name to pin an old run. A golden-defaults test fails when an existing field's default changes without a `VERSION` bump of the stage that reads it. Pure modules (probe input, call syntax) carry a `VERSION` that each stage folds into its key. Deterministic consumers key on the upstream output manifest (file list plus hashes), so a `VERSION` bump that changes no bytes stops there instead of cascading through days of training. (N2, N5, B3, S1, S3, S4, S8, S9)
4. **Run states.** `meta.json` carries running, stalled, failed or done, and one launch entry per start. A walk that meets a running key prints its session and exits. A failed directory needs `--retry`. `--force` reruns a stage into a fresh directory. A run can be started from a saved settings file. (N6, S5, S11)
5. **Done means finished, not written.** A task file is done only when its final record has no abort; aborted files are redone. The loop stops after a run of consecutive connection failures. `run.py ls` probes each server piece's health and each tmux session's liveness, so a dead server under a live loop shows as dead. (S2, B14)
6. **One generation path.** Sample and the inject control both use the streamed row with the probe switch off; today's default sampling path is the hand-rendered completion, not the chat endpoint. The chat request survives only inside the render-equals-server check. One record format, with a `VERSION` from the first day. (B6)
7. **The environment interface.** `tasks(split)`, `open(task, seed)`, `step(code)`, `speculate(call)` (requote, save, run, restore, time guard, returning the observation and its error kind), `judge()`, `close()`. Call finding belongs to the environment (AppWorld, BFCL, ALFWorld and tau2 each have their own regex today); the shared file keeps argument splitting and call completion. A rollback test comes from today's shadow self-test. (N3, B7)
8. **Concurrency.** Pieces and replicas are settings values; the claim protocol stays; a piece never opens another piece's file for writing. (B9, S15)
9. **Environments.** `any` means importable in all three environments, OmegaConf and PyYAML included. `run.py` runs under the agent environment; the system python (3.10, no lock) stops being an interpreter. The header names the venv (`# env: appworld`) because a second environment brings its own. The three lock files are regenerated with omegaconf and peft. The OpenAI package is dropped for the standard library client. (N4, B10)
10. **Train.** No continue-from-checkpoint exists today. The third draft: `last/` is saved by wall time (a setting), resume happens only at the same commit, otherwise the directory starts over; ctool's shuffle is seeded. The alignment gate stays as `train.align_check` on the real model before training, and the CPU test uses a tiny random-init model fixture. (B2, B8, S7, S11)
11. **Debug.** The overlay changes sizes only (tasks, seeds, examples, steps), never the backbone or the tuning; it is applied before the command-line overrides; `serve_agent` attaches to a live server with the same model and generation settings, so a debug sample does not wait five minutes for a server. (B15, S7, S13)
12. **Ledger.** Appends go under a file lock; rows are keyed by stage, key and start time; the last finish row wins; the dirty patch is saved into the run directory; the diff is stored as JSON inside the row so the ledger module stays standard library. (S6, S11, B10)
13. **Tracker.** wandb cannot be imported in the agent environment (it needs pydantic 2; AppWorld pins 1.10) and the nodes appear to have no internet. The recommendation becomes MLflow with a file store on NFS, run as a separate process on the login machine that reads the metrics files; default none. (S12)
14. **Tree and names.** `RESULTS.md` listed once; `gpu_state.md` under `constants/`; `settings/config.py` becomes `settings/shape.py`, and the run directory holds `settings.yaml` and `settings_diff.yaml`; `build.py` becomes `build_dataset.py`; `agent_model.py` becomes `agent_client.py` with `probe_client.py` beside it; `matrix.py` becomes `method_table.py`; the three parts of the system prompt are named on their lines; `logging` joins the section list; each axis declares its allowed values in the shape; one stage table in one file; the "Replaces" lists drop the replay-line files, `extract_completed.py`, `input_modes.py` and the sweeps into "not carried over"; the tests list grows by generate, loop, build, score_run, train and rollback; the examples use gpt-oss-120b, the only gpt-oss row in the model table. (N7 to N11, B11 to B13, S15)

## B. Decisions only gyb can make

1. **One file per layer against measured size.** The builder read the two trainers: ctool batches whole events and trains a classification head; cgen and cparam pack rows into one sequence with a custom mask and train the language model head. The shared part is the optimizer loop; the merged file measures about 1,500 lines, and the merged evaluator about 1,100. The instruction was "these tools should be in one file". Options: (a) keep one `train.py` and one `eval_probe.py` and accept the size; (b) split at the seam the code has: `train_ctool.py`, `train_gen.py` (cgen and cparam), `packing.py`; `eval_score.py`, `eval_gen.py`. Recommended: (b), because a file whose two halves share nothing but the loop is two files under the "one thing per file" rule, and a 1,500-line file is where the copy-paste disease starts again.
2. **How an output directory is named.** Today's draft: `<stage>/<workflow>/<setting>__<key>`. The skeptic's case: nine trainings share one sample directory named after whichever setting ran first, and an edit to a file's `common` block leaves directories whose names match no setting. Options: (a) keep the name prefix; (b) name the directory by the key alone, keep an owners list in `meta.json`, and let `run.py ls` show names, status and what differs. Recommended: (b); the ledger and `ls` are the readable view, the directory name is the identity.
3. **A `sweep:` key.** Three sweep tools exist today (preset, learning rate, theta), which is the third repetition. Options: (a) a grid is N named settings written by hand; (b) a `sweep:` key inside a named setting expands at load into child settings, and the method table groups children by everything but the swept fields with mean and spread. Recommended: (b), one keyword, about forty lines in the loader.

## C. Adopted answers to the two earlier questions

- **A second environment.** Not carried in the tree; designed for now (call finding in the environment file, the venv named in the header, the environment chosen by `data.env`). The README's `data/` block names the old runner file and the commit that holds it.
- **Notebooks.** Three rules on the line: a notebook imports any module and no module imports a notebook; a notebook never writes into an output directory or the ledger; a notebook that produces a figure or a table becomes a script under `figures/`.

## D. Notes for the migration plan, not the structure

- Removing the read-only feature is an edit through train and eval, not a file deletion.
- The gpu-run and probe-pipeline skills, their references, and the project `CLAUDE.md` name today's commands and are rewritten with the tree.
- `demo/` is at the repository root; its tiny model builder becomes a test fixture; `.gitignore` and `.vscode/launch.json` change with it.
- The split files and trajectory roots inside today's manifests and stage configs become rows in `constants/`.
- The memory probe, the logits cache of the ctool evaluator, and the trainer's own generation eval are dropped unless a result needs them.
- With the splits of decision 1 and the two client files, the count is about 27 Python files.
