# Contracts synthesis notes

How `notes/plans/2026-09-17-contracts.md` was assembled from draft B (the
winner by total score), the grafts the three judges proposed, the
contradictions they listed, and the tree violations they found.

Two facts I measured myself before settling anything, because three of the
contradictions turn on them and the judges disagreed about one of them:

- `vllm/entrypoints/serve/tokenize/protocol.py:24-47` (vLLM 0.26.0 in
  `external/vllm-env`): `TokenizeCompletionRequest` has `model`, `prompt`,
  `add_special_tokens`, `return_token_strs` and nothing else. No
  `split_special_tokens`. The judges were right.
- `vllm/entrypoints/serve/tokenize/serving.py:84`: `create_tokenize` on a chat
  request calls `online_renderer.preprocess_chat`, the **jinja** path. Only the
  chat-completions path reaches `_make_request_with_harmony`
  (`vllm/renderers/online_renderer.py:154-180`). **No judge noticed this.** It
  means B's `render(messages) = POST /tokenize {messages}` does not reproduce
  the chat endpoint's rendering for gpt-oss at all — it is the jinja path that
  `legacy/pipeline/inject/harmony_render.py:1-18` records as diverging in two
  edge cases on 2026-08-18. That killed the "move rendering to vLLM" half of
  the argument outright, not just the encode half.
- A third fact I found while settling it:
  `vllm/entrypoints/openai/parser/harmony_utils.py:133-139` takes the harmony
  system date from `VLLM_SYSTEM_START_DATE` and otherwise from the machine
  clock. No draft mentioned this; the contracts now pin the env var from
  `generation.date` (Part 6.1, 9(a)#25).

Venv table re-measured: it is exactly as draft B states (polars 1.44.2 and
PyYAML 6.0.3 in all three; numpy absent from `external/appworld/venv`; pydantic
1.10.26 there against 2.13.4 elsewhere; openai_harmony 0.0.8 in probe and vllm).

---

## Grafts applied

| # | Graft | Source | What I did |
|---|---|---|---|
| 1 | `fires.parquet` beside `report.json` | A, Part 1.4 (all three judges) | Applied, with one change of framing: it is **not** a fifth format. The probe report is one format in two files, `probe_report.json` and `fires.parquet`, written and read by one pair of functions in `eval/utils/probe_eval.py`. That removes judge 1's tree-violation reading ("a fifth on-disk inter-stage format defined outside `data/`") while keeping the mechanism. Columns: risk, theta, split, event_id, example_id, score, depth, label_pred. This is the single most important graft: B's stated upstream for `eval(cgen)` was unimplementable as written. |
| 2 | Keep `/encode` and `/decode` on the probe service | C, 7.2 + 9(a)#7 (judges 1, 2, 3) | Applied, and extended to `/render` as well, for the second vLLM fact above. B's move was its one clear tree-line violation and it also loses the `special=false` direction that every `p1` format needs. |
| 3 | Reach the agent family through `models/__init__.py`, not by importing `gptoss.py` | judge 2's wording inside graft 3 | Applied. This is what lets the probe service keep render/encode/decode **and** still leave a second agent family at one file plus a table row — the P4 fix survives the reversal of B's move. C imported `gptoss` by name inside `serve()` and paid the coupling; B moved the routes and paid the correctness. Neither was necessary. |
| 4 | The nine lifecycle scenarios as a closing part | C, 9(c) (judges 1, 2, 3) | Applied as Part 9(c), rewritten against this document's own tables and named as the construction plan's smoke list. Judge 2 is right that this is where a missing mechanism shows: writing it is what forced me to state that `run.py` stops after launching an async GPU stage (scenario 1) and what the other five sweep children do (scenario 6). |
| 5 | `build.max_abort_frac`; `train` refuses a directory holding `train_log.jsonl`; a final row with a non-null abort counts as done | C, 2.6 (judge 1) | All three applied (Part 2.4, 2.5, 1.1). The third fixes a real bug in A: under A's rule an aborted task is never done, so `launch.py` deletes and redoes it on every refire, forever. |
| 6 | One owner for `done.json` and the finish row | C, 2.2 + 9(a)#10 (judges 1, 3) | Applied with a split C did not make explicit: a **one-process** stage (build, train, eval, score) writes its own `done.json`, because it is its own last piece; only the **piece** stages (sample, inject) leave it to `run.py` on the login machine. |
| 7 | The `arm` axis instead of independent booleans | C, 5.1 (judge 3) | Applied: `inject.arm` with `probe` / `no_probe` / `probe_nofill`, and a loader refusal for `fire_nth_cut > 0` under `no_probe`. B's four booleans can contradict each other and spread the arm's identity over four key fields. |
| 8 | `meta.json.split_files` with the path, hash and resolved id list, and an `ls` flag | C, 8.3 (judge 2) | Applied. B described the mechanism in prose (6.2) but gave it no field to write into. |
| 9 | Write the start row even when the alive check fails, with `status: launch_failed`; `schema.freeze` refuses to overwrite a differing `settings.yaml` | C, 8.2 + 3.6 (judge 3) | Both applied (Part 8.1, 3.4). The freeze refusal is the only key-collision detector anyone proposed and costs one comparison. |
| 10 | A reference resolves to every stage key the referring field needs | A, 5.4 (judge 2) | Applied in the stage table: `inject.probe_score` resolves to **two** keys (train for the weights, eval for the temperature), `probe_gen` to one. B resolved `probe_score` to its eval key only and then passed `--score-ckpt` on the service command line with nothing naming that directory. |
| 11 | The per-item drop list with a reason each, and the matching list of kept mechanisms | A, 9(a)#18-19 (judge 1) | Applied as 9(a)#26 and #27, and the CONTEXT.md entries that retire with the sampler are named (9(a)#13) — eight of them, counted. |
| 12 | `train` folds `eval/methods/<m>.py`'s VERSION | A, 2.2 (judges 1, 2) | Applied, because I reverted B's relocation of the match function (see contradiction 3 below), which is exactly the condition judge 1 attached to this graft. Its price (an eval match fix reruns training) is stated in 9(a)#23 and the structural fix that removes it is 9(b)#9. |
| 13 | A's house style: each mechanism followed by the failure it prevents, with the legacy file and line | A, Parts 1-3 (judge 2) | Applied where a real incident exists, in italics. Not applied everywhere — B's tables are better as tables, and a failure clause on every row would be noise. |
| 14 | Label order in the train run's `meta.json` rather than a `label_map.json` | A, 1.3 (judge 3) | Applied: `stage_extra.labels`. Both B and C introduced a fifth on-disk file with no format definition. |

## Grafts rejected

| Graft | Source | Why not |
|---|---|---|
| Pin `eval/` to the probe venv and let it import numpy | A, 9(a)#12 (judges 1, 2, 3 all wanted this) | Rejected in that form, because it is a stated deviation from the tree's own `eval/` line ("every file imports as any") and my instruction is to remove tree violations, not to restate them. I took the same *outcome* by a different route: `venv: any` is defined to include NumPy, and the construction plan installs NumPy into `external/appworld/venv` — a dependency-free wheel, exactly as Polars already was, one command. The tree line stays literally true and eval still gets an ordinary 1-D minimiser instead of B's golden-section search in Polars expressions. If the owner refuses the install, the fallback is A's annotation, and it is named in 9(a)#15. |
| Four verdicts with one 1800 s stall line | A, 8.4 (judge 2) | Rejected. CONTEXT defines six and the glossary is the owner's fixed vocabulary; retiring the sampler does not require retiring the words. A's argument is that the beat history existed to feed the sampler — but under B's and C's design the heartbeat is a jsonl file per piece, so the history is on disk anyway and the adaptive line costs a median over twenty numbers. `warming up` is also what keeps a model-loading piece from being called stalled, which matters more now that nothing escalates automatically. Recorded as 9(a)#14 with A's alternative. |
| C's `/score` returning `fired` | implied by graft 2 | Rejected: I kept the route on the probe service but not the threshold. Theta stays in the setting and `agent/inject.py` compares, so the fire rule has one home — A's and B's position, and the one that also knows `arm`, `fire_nth_cut` and `max_inject_per_step`. Taking C's routes did not oblige me to take C's semantics. |
| A's five row kinds (merging `gen` and `env`) | A, 1.1 | Rejected: the brief says the six row kinds of today's live record must have a home, and A's merge is a format change justified by an incident (`legacy/pipeline/annotate/build.py:75-80`, the silent `break` on a failed join) that is better fixed directly. The contracts keep six kinds and make the builder **raise, naming the record and the step**, when a `gen` row has no `env` row. Same incident, no format change. |
| A's drop of `weight_mode`, `prefix_sha` and the per-cut weight column | A, 1.2 | Rejected: each is one column or one axis, they cost nothing to keep, and `prefix_sha` is the cheap way to compare two arms' prompts after the fact — which is exactly what the 2026-08-18 identity investigation needed and did not have. |
| A's "no manifest file" | A, 9(a)#7 | Rejected in favour of B's and C's `consumed.json`: the completeness rule fixes *what* was consumed, but only a recorded hash catches an upstream that changed afterwards, and `ls` flags it. It costs one file that nothing has to stay in step with, because it enters no key. |

## Contradictions, and how each was settled

Numbered as they appear across the three judges; each settled in one sentence in
Part 9 or at the point of use.

1. **What the key is computed over.** Diff from the schema defaults (A, B), not
   the resolved sections (C). The fourth draft's own `schema.py` line says a new
   hyperparameter comes "with a default that reproduces the old behavior", which
   is only free under diff keying; C's choice would orphan every finished
   directory on the first schema edit, and C never states that. Price recorded:
   changing an existing default needs a VERSION bump, kept by hand until
   `tests/` exists. (9(a)#3)
2. **eval's venv and numpy.** Settled by making the fact go away: NumPy is
   installed into the AppWorld venv so `any` has one definition, and eval keeps
   `venv: any` as its tree line says. (9(a)#15, and the precondition at the top
   of the document.)
3. **Where the validation match function lives.** The tree's `eval/methods` line
   wins: `train/methods/<m>.py` imports `eval/methods/<m>.py`'s `match`. B moved
   it into `data/example.py` and did not list the move in its 9(b) — all three
   judges called that a silent relocation of a tree-stated interface. The
   consequence (fold eval's VERSION into the train key) is applied, the cost is
   stated, and B's design is preserved as 9(b)#9 for the owner. There is no
   cycle: `eval/methods/*` imports only `eval/utils/probe_eval.py` and `data/`,
   all `any`, no torch.
4. **Whether `train` folds `eval/methods/<m>.py`'s VERSION.** Yes, given 3.
   (9(a)#23)
5. **Who turns text into ids, and with which knob.** The probe service, with
   `split_special_tokens=(not special)`. vLLM cannot express the
   `special=false` direction at all, and that is the *default* direction, used by
   every `p1` format (`legacy/pipeline/inject/live_appworld.py:506-508`). B's
   startup check `decode(encode(s, special=True)) == s` tests only the direction
   vLLM can do, so B's own gate would have passed while the prompt changed
   silently. The contracts' check tests both directions. (9(a)#8, Part 7.2)
6. **Who renders harmony.** Also the probe service, for the second fact at the
   top of these notes, which is stronger than the `split_special_tokens`
   argument and which no draft had: `/tokenize {messages}` on this vLLM is the
   jinja path for gpt-oss. The render-equals-server check therefore compares
   `gptoss.render_ids` against the **chat** endpoint's `prompt_token_ids`, not
   against `/tokenize`. Cost paid openly: a `sample` run starts one extra CPU
   process in `--render-only` mode — which is today's flag, not an invention
   (`legacy/pipeline/inject/probe_server.py:138-161,360-362`). The P4 coupling
   is paid off through `models/__init__.py` instead. (9(a)#8, Part 7.2)
7. **Which rows the generating evals score.** `fires.parquet`, joined on
   `example_id` (graft 1). The first-crossing rule is executed once, by the file
   that owns theta. (Part 1.4)
8. **The prediction row's shape and eval's upstream count.** Between A (minimal
   row, join back to `examples.parquet`) and C (copy six columns, never read the
   example file), I took C's direction with A's discipline: copy the five
   columns eval actually needs — `event_id` (first crossing is per event),
   `task_id` (the bootstrap resamples by task,
   `legacy/pipeline/eval/eval_tool.py:279-296`), `depth` (earliness), `split`
   and `target` — so `eval/` opens exactly one upstream directory and never
   resolves a build key. They are written once from one frame, so they cannot
   drift within a run. (Part 1.3)
9. **The task record's row kinds.** Six, B and C. (Rejected graft above.)
10. **When a record counts as done.** The last row being `final`, whatever
    `abort` says (B, C). (9(a)#17)
11. **Whether a partial record is resumed or deleted.** Deleted and redone: the
    world state died with the process, and deleting also removes the
    half-written last line. (9(a)#16)
12. **The verdict vocabulary.** Six with the adaptive line. (9(a)#14)
13. **Who writes `done.json`.** `run.py` for the piece stages; the program
    itself for a one-process stage. (9(a)#18)
14. **Per-cut weighting.** Kept as `build.weight_mode`. (Rejected graft above.)
15. **How the control arms are spelled.** `inject.arm`, one axis. (9(a)#19)
16. **Whether the probe service applies theta.** No. (9(a)#9)
17. **How theta and the temperature reach the probe service.** Neither A's (the
    service reads the report), nor C's (`models` imports `eval`), nor B's
    (`jobs` imports `eval`). `run.py` — the top layer, which may import
    anything — reads the report through `probe_eval.read_report` and
    `schema.freeze` writes the temperature into `settings.yaml` under
    `_resolved`; `launch.py` reads the frozen setting. `models/` and `jobs/`
    both stay clear of eval outputs, and the number is visible in the run
    directory. Theta never goes to the service at all, because the service does
    not apply it. (9(a)#7, Part 5.4)
18. **The environment base class surface.** Nine methods, `split_args` kept.
    (Part 4.2; the rename is 9(b)#14.)
19. **Whether the sample and inject keys contain the task and seed lists.** No
    (A, B). A fourth seed adds files instead of discarding three seeds of
    collection; the consumers key the lists and refuse until complete.
    (9(a)#20)
20. **How `schema.py` learns a module's VERSION.** By reading the literal
    `VERSION = <int>` line as source text (B, C), not by importing (A): eval
    must compute a train key without importing torch. (9(a)#6)
21. **Where `run_dir` lives.** `experimental_settings/schema.py` — all three
    drafts agreed; recorded because the lifecycle review proposed
    `jobs/registry.py`. (9(a)#4)
22. **B's "run.py writes nothing of its own"** (judge 3's smaller finding).
    Corrected: `run.py` writes `settings.yaml` and `settings_diff.yaml` through
    `schema.freeze`, `done.json` for the piece stages, and the finish rows. The
    annotation is the line `selfcheck` verifies, so it has to be true.

## Tree violations, and how each was removed

| Violation | Judge | Resolution |
|---|---|---|
| A renames `split_args` to `parse_call` and declares eleven methods | 1, 2, 3 | Not applied. Nine methods with the tree's names (Part 4.2); the instruction text and the no-code message are class attributes, not methods; the rename is 9(b)#14. |
| A annotates every `eval/` file `venv: probe`, against the tree's eval line | 1, 2 | Removed by installing NumPy into the AppWorld venv so `venv: any` holds for eval as the line says (contradiction 2). A's annotation survives only as the named fallback in 9(a)#15. |
| A defines `fires.parquet` as a second inter-stage format outside `data/` | 1 | Removed by defining the probe report as **one format in two files**, with one writer and one reader in `eval/utils/probe_eval.py` — the file the owner sanctioned. Stated explicitly in Part 1.4 so it is not a silent addition; moving the whole report to `data/probe_report.py` stays as 9(b)#5. |
| B moves the per-method match into `data/example.py`, against the tree's `eval/methods` line, without listing it | 1, 2, 3 | Reverted: `train/methods/<m>.py` imports `eval/methods/<m>.py`'s `match`, as the line says. B's design is recorded as a proposal, 9(b)#9, with what it would buy. |
| B's probe service keeps only score, generate and health, against its tree line naming encode and decode | 2, 3 | Reverted: encode and decode stay, implemented with `split_special_tokens`, which is also the only correct implementation (contradiction 5). |
| B has `jobs/launch.py` import `eval/utils/probe_eval.py` | 2 | Removed: `run.py` reads the report and freezes the value; `jobs/` imports only `schema`, `registry` and `data/task_record.py` (contradiction 17). |
| C adds `/render` to the probe service, which its tree line does not name | 1, 2, 3 | Kept, and stated openly at the point of use (Part 7.2) and in 9(a)#8 with its cost and alternative — which is the process the owner's instruction prescribes for a mechanism with no obvious file. The evidence is stronger than C had: not only does vLLM lack `split_special_tokens`, its `/tokenize {messages}` is the jinja path for gpt-oss. |
| C annotates `eval/utils/probe_eval.py` as `any (polars, numpy)` while numpy is absent from the AppWorld venv | 1, 2, 3 | Removed the same way as A's: the annotation becomes true by installing NumPy, and the document says so as a precondition rather than leaving a claim its own `selfcheck` would fail. |

## What I added that no draft had

- The date pin: `generation.date` is passed to vLLM as `VLLM_SYSTEM_START_DATE`
  and proved by the render-equals-server check
  (`vllm/entrypoints/openai/parser/harmony_utils.py:133-139`). Without it a
  rerun in November renders a different system message and the key says nothing
  changed. (Part 6.1, 9(a)#25)
- The `gen`/`env` pairing rule in Part 1.1, which is how the six-kind record
  answers the incident A used to justify merging two kinds.
- The precise `chosen` theta rule and the by-task bootstrap, taken from
  `legacy/pipeline/eval/eval_tool.py:514-517,279-296`, so Part 1.4 is
  implementable without reopening the legacy file.
- `run_dir_of(stage, key)` as a third signature: every stage resolves its
  upstream from the key in `_upstream`, never by recomputing a key.
