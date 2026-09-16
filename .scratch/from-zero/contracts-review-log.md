# Contracts review log

The document under review is `notes/plans/2026-09-17-contracts.md`. Each round
records what was applied to it and what was refused, with the reason.

## Round 1 — 2026-09-17, three reviewers, 45 findings

Findings arrived as JSON from three reviewers working independently, so several
of them are the same defect seen twice or three times. They are grouped below by
defect, not by reviewer.

### Two facts measured before editing

Two fixes needed a measurement rather than an opinion, and both were run on this
machine on 2026-09-17. They are now in the document's "Facts measured" section.

1. **Exclusive create on the outputs mount.** `/net/tokyo100-10g/data/str01_01`
   is NFSv4.0 (`findmnt -t nfs4`). Three hosts (shiga/tokyo105, tokyo106,
   tokyo107) ran 8 processes each, released at a common wall-clock barrier, and
   raced for 150 files: exactly one winner per file, 150 out of 150, with two of
   the three hosts winning files (83 and 67). That is what Part 1.1's `O_EXCL`
   claim now rests on, in place of the assumption a reviewer objected to.
2. **The cluster is really four hosts, reached over ssh.** `DEFAULT_HOSTS` in
   `legacy/ops/gpu_jobs.py:124` names tokyo105-108; `legacy/ops/launch_common.py:41`
   maps `shiga` -> tokyo105 and `saitama` -> tokyo108 because those two answer
   `hostname` with the alias. All four answer `ssh -o BatchMode=yes` and all four
   have the outputs mount. That is why the multi-host branch of the "multi-host
   is assumed everywhere and specified nowhere" finding was taken rather than
   the single-host branch.

### Applied — blocking

- **The live probe's text had no source for three of its four parameters.**
  Added Part 1.7, which pins `data/probe_input.py`'s two functions
  (`cuts(thinking, min_think, max_cuts)`,
  `assemble(task, history, thinking_prefix, hist_rounds, result_cap)`), the
  shape of `history`, where each parameter comes from offline and live, and the
  rule that both callers construct no probe text of their own. Added the
  inherited `build.{min_think, hist_rounds, result_cap}` to inject's "sections
  read" in 2.1 with a paragraph on why, to the inheritance rule in 5.4, and to
  5.7's "section for a stage the workflow does not name" refusal as an explicit
  exception (an inherited section is written by `freeze`, never stated).
- **The interpreter paths had no home.** `constants/path_datasets.yaml` gains a
  top-level `venvs:` map (`appworld|probe|vllm` -> absolute interpreter path);
  the per-environment `venv:` column is now a key of that map. `jobs/launch.py`
  and `run.py` name it in their `reads:` lines, 3.4's piece command takes its
  interpreter from it, and `selfcheck`'s three-venv import test reads it too.
- **Multi-host was assumed everywhere and specified nowhere.**
  `constants/path_outputs.yaml` gains a `hosts:` list (name, alias, cards), and
  3.4 states the transport: a remote piece is
  `ssh -o BatchMode=yes <host> tmux new-session -d …`, liveness and card probes
  are one `ssh <host> tmux ls` and one `ssh <host> nvidia-smi` per host, all
  fail-closed. `ls`, `free` and the launch gate name that list.
- **Nobody assigned a service port and no client could find an endpoint.**
  Added 7.4: `jobs/launch.py` assigns every service port inside the same lock
  hold as the launch gate (agent replica `i` at `serving.port + i`, probe
  service at the first free port at or above a `PROBE_PORT_BASE` literal in
  `launch.py`), records it in the piece entry, and each service piece writes its
  own `service_<kind>_<piece>.json` — renamed from `service_agent.json` /
  `service_probe.json` so that `replicas > 1` keeps one writer per file. Both
  clients take `Client(base_url)`. Loop piece `i` uses agent replica
  `i mod replicas`, named in its piece entry. `models/table.yaml` added to
  `jobs/launch.py`'s `reads:`, the endpoint files to `agent/loop.py`'s.
- **`meta.json` had many writers on NFS.** Deleted the `state` row from 8.3 and
  "meta.json's state" from 8.6; a piece's progress is its own heartbeat file,
  whose last line already carries `done`, `total`, `unit`, `ts` and `status`.
  `meta.json` is written only by `run.py` and `jobs/launch.py`. `split_files` is
  now resolved and written by `jobs/launch.py` before the pieces start, and
  `data/environments/__init__.py` is on its `imports:` line. `run.py sync`'s
  "done.json and state" became "done.json and heartbeat files".
- **A fourth seed could never be collected.** `done.json` for `sample` and
  `inject` gains `pairs`, the resolved (task, seed) list it certifies, and 2.3
  states the skip test for those two stages as the subset check against `pairs`,
  never the presence of the file. Scenario 2 rewritten accordingly.
- **The launch gate was not inside the lock.** 8.6 now scopes
  `jobs/launch.py`'s hold of `runs.jsonl.lock` across read-registry, the launch
  gate, the card reservation, the port assignment and the append; tmux sessions
  start after the release. Scenario 9 rewritten to match.
- **`baseline.yaml` could not load.** `score.baseline` removed from 5.7's
  required list, with the meaning of `null` stated in 5.2.
- **The "a new column never bumps VERSION" rule was unsafe.** Part 1's
  conventions now split it in two: optional-to-every-reader columns are free, a
  column any downstream stage reads costs a `VERSION` bump on its format file,
  and a reader raises (naming column, file and recorded version) rather than
  taking a default for a column it requires. 0.4's task-record row split into
  two rows accordingly, and 9(a) gained the decision.

### Applied — major

- `gptoss.py`'s `used by:` reduced to `models/__init__.py (by name)`;
  `models/agent_models/service.py` reaches the family through
  `models/__init__.py`'s `agent(alias)` inside the server main.
- 2.6 pins `trainer.run(run_dir, method)` and `probe_eval.run(run_dir, method)`,
  states that a method file's `main` is one line and that no method file imports
  `schema.py` or `registry.py`. The Setting reaches a method through its hooks'
  `cfg` argument, which the hook table already had.
- The class order: `base.py` owns it and writes it into `best/meta.json`; the
  trainer copies it into its own `done.json` under `stage_extra`; `run.py` folds
  that into `meta.json`; `probe_eval` reads it there.
- `theta_used` and `exact` in the probe report became dictionaries keyed by risk
  target, and a generator eval refuses when its `eval.risk` differs from the
  referenced report's `risk_targets`.
- Inject reads neither `models.probe` nor a `probe` section; 5.7 refuses both.
- `to_messages` takes `instructions` and `no_code` explicitly; both callers pass
  the environment's two class attributes.
- The `FORMATS` entry is pinned in 7.3 (`placement`, `needs_special`,
  `system_text`, `render`), with `p2` handed to the family's `wrap_prefetch` and
  the `ast` check stated.
- `PROBE_KIND` replaces every branch on a method name: the stage table's eval
  upstream, 5.7's required-field rule, and the report's two shapes. `schema.py`
  reads it as source text the way it reads `VERSION`.
- `/health` echoes `family` and `render`; `agent/loop.py` compares the family
  against its own `models.agent` row and `agent/inject.py` asks for the
  capabilities its format needs, so the two gpt-oss literals are gone.
- Both `service.py` files carry `VERSION`, folded into `sample` and `inject`.
- Backbone and family module interfaces added as Part 6.2 (six and nine names).
- `build`'s `consumed.json` records the split files it read; `ls`'s `consumed`
  flag covers them.
- `NO_CODE_MESSAGE` and `SEED` added to what an environment file's `VERSION`
  guards, with the note on 4.1.
- The generator eval gate compares `_upstream.build` keys instead of `labels`
  (a generator run has no head and no labels), and the same check holds between
  `inject.probe_score` and `inject.probe_gen`.
- `metrics` and `report` moved into `done.json`; 8.2's finish row is built from
  `done.json` alone, and a stage that always recomputes gets a new finish row
  whenever `finished_at` advances.
- Claims are released only on the login machine; a loop piece never deletes a
  file it does not own (1.1 and 2.3).
- Card reservation added to 2.5: a card is busy when a live registry row's piece
  entry holds it, not only when `nvidia-smi` sees a process.
- 5.4 states that every reference must agree on the inherited sections and that
  a disagreement is itself a load error; `meta.override` added to 5.2 and to
  5.7's merge order as a check after step 5.
- `--debug` applies only to the named setting's own workflow; a resolved
  reference is keyed without the overlay.
- `score` refuses unless the baseline holds a done record for every (task, seed)
  the scored run holds.
- `read_dir(dir, pairs)` reads exactly the requested pairs and skips unfinished
  files; `build` reads only the records of the pairs in its own key.

### Applied — minor

`data/__init__.py` added to `build_dataset.py`'s imports (and the builder to its
`used by:`); `consumed.json` writers named and added to `trainer.py`'s and
`probe_eval.py`'s `writes:`; `inputs` deleted from 8.3; `CUDA_VISIBLE_DEVICES`
stated in 3.4; `ARMS` literal in `agent/inject.py` and the selfcheck column
changed to match; `load` and `freeze` signatures written in 5.1; 2.2 states that
2.1's "sections read" is authoritative and "minus" only records why; `qwen.py`
carries `VERSION`; the `VERSION` line's shape fixed in 3.3 (module level, column
zero, exactly once, integer literal; a class writes `VERSION = VERSION`);
scenario 5 now names train in the cut-rule cost; sweep expansion moved between
steps 3 and 4 of 5.7 with a command-line override of a swept field refused;
split values validated at load against the chosen environment and checked by
selfcheck against the union; `total` defined for a claiming piece in 8.4; 0.4's
sixth-format row names the schema edit; the generation defaults `stop`, `effort`
and `date` default to null and resolve against the family module.

### Not applied, and why

1. **"Add `models.probe` and `probe` to the inherited sections in 5.4 and to
   5.7's refusal list"** (reviewer 1, major). Not applied: another reviewer
   found the same defect and proposed dropping both from inject's key instead,
   and the two fixes cannot both hold. Dropping is right. An inject run uses two
   probes; when they sit on different backbones, a single `models.probe` alias
   cannot name them, and `probe.method` has no meaning for a run that uses one
   classifier and one generator at once. Inheriting would also have to pick one
   of three references arbitrarily. The document now drops both from 2.1 and
   refuses them in 5.7, which fixes the same failure the finding describes.
2. **"State the single-host rule in 3.4 and drop 'any host' from 2.5"**
   (reviewer 1, the first branch of an either/or). Not taken: the measurement
   above shows four real hosts that the old code already reaches. Declaring the
   repo single-host would drop working capacity to make a document shorter. The
   second branch of the same finding was applied in full.
3. **`cuts(thinking, cfg)` and `assemble(task, history, thinking_prefix, cfg)`**
   (reviewer 2's signature for Part 1.7). Not applied in that form.
   `data/probe_input.py` imports nothing from the repo, so it cannot name a
   `Setting` type; and a `cfg` parameter would let the two callers pass
   different sections of it, which is the divergence the function exists to
   prevent. The explicit-parameter form from the other reviewer was used, with
   this reviewer's definition of `history` and of who derives it.
4. **"Add `probe_eval.read_frozen`-style access if a method needs `cfg`"**
   (reviewer 1, inside the method-entry-point fix). Not applied: no new
   accessor is needed. Every hook in 2.6's table already takes `cfg`, and the
   library hands the loaded Setting down.
5. **"`train/utils/trainer.py` copies `labels` into the run's `meta.json`
   through `jobs/registry.py`"** (reviewer 1). Not applied literally, because it
   contradicts the blocking finding that `meta.json` has only login-machine
   writers — the trainer runs on a compute node. Applied in a merged form that
   satisfies both: the trainer writes `stage_extra` into its own `done.json`,
   which it owns and writes once, and `run.py` folds it into `meta.json` on the
   walk that writes the finish row.

No finding required adding, splitting, moving or renaming a file of the tree, so
nothing from this round went into Part 9(b) as a refused fix. Two placements the
fixes forced were recorded there as proposals instead, since both would need a
new file:

- **9(b)#18** `constants/cluster.yaml` for the `hosts:` list and the `venvs:`
  map, which now ride on `path_outputs.yaml` and `path_datasets.yaml`.
- **9(b)#19** putting the shared probe-input rule beside its two callers rather
  than under `data/`.

Three decisions the owner can veto were added to 9(a): #28 multi-host with the
inventory in `constants/`, #29 the split `DEFAULTS` rule and its price, #30 the
measured `O_EXCL` claim primitive and the fallback if the mount changes.

## Round 2 — 2026-09-17, three reviewers, 41 findings

The second pass read the document Round 1 produced. Every blocking and major
finding was applied, every minor whose fix was a sentence was applied, and no
finding was refused. Nothing required adding, splitting, moving or renaming a
file of the tree, so Part 9(b) gained no refused fix; 9(b)#18 was widened
instead, and 9(a) gained eight new decisions.

### Applied — blocking

- **The eval side had no hook contract and two directions of control.** 2.6
  gained an eval hook table mirroring the train one — `VERSION`, `PROBE_KIND`,
  `match(pred, target)` and `report(pred_df, cfg, ref) -> (dict, DataFrame |
  None)` — and states that `probe_eval.run(run_dir, method)` is the driver, the
  method file's `main` is one line, and the method never calls back. A
  paragraph now assigns `load_frozen`, the registry rows, the heartbeat,
  `consumed.json`, `write_report` and `done.json` to the library on both sides,
  replacing the closing sentence that gave control to the method.
- **`PROBE_KIND` was unreachable on the eval side.** It is now declared at
  column zero in `eval/methods/<m>.py` as well as in the train file; `schema.py`
  reads the train copy as source text, `probe_eval.run` reads the eval copy off
  the module it was handed, and `selfcheck` fails when the pair disagrees. The
  alternative — an accessor on `schema.py` — was not taken, because 5.1 fixes
  that file's public surface at "nothing else".
- **`step` was never pinned, so `inject.step` was not demonstrably
  substitutable for `generate.step`.** 7.3 opens with the shared signature
  `step(env, clients, cfg, writer, messages, step_index, seed) -> StepResult`,
  `StepResult` as a dataclass in `agent/generate.py` carrying the `gen` row's
  non-derived fields, `agent/loop.py` writing the `gen` row from it, and
  `generate.stream(...)` as the iterator `inject.py` re-uses.
- **`jobs/registry.py` had no stage-facing API.** New 8.0: the writer half
  (`beat` / `Heartbeat.emit` / `Heartbeat.finish`, `write_done`, `write_meta`,
  `append_start`, `append_finish`) and the reader half (`ls`, `where`, `find`,
  `kill`, `free`, `sync`, `open_runs`), each with its callers.
- **`any` was not a key of the `venvs:` map.** 6.3 states that `any` is a claim
  about importing, not a launcher choice, and that a stage whose venv column is
  `any` is launched with `venvs.probe`; 2.3 and 3.4 say `run.py` itself builds
  and starts a CPU stage in place, so exactly one file performs the lookup. The
  other reviewer's form — adding an `any:` row to the map — was not taken,
  because it would put the same interpreter path in the file twice and would
  then be counted by 0.1's "every interpreter in the map" rule.
- **`run.py` used `is_done` and `owner` without importing them.**
  `data/task_record.py (is_done, owner, release)` is on `run.py`'s `imports:`
  line, `run.py` on that file's `used by:` line and in 1.1's "who reads", and
  the run's task records on `run.py`'s `reads:` line. `release` joined 1.1's
  offered functions, where `launch.py`'s annotation already named it.
- **Two entries disagreed about who imports a backbone, and `probe(alias)` had
  no return type.** `models/__init__.py`'s description now matches 6.2 and both
  annotation lines: `agent(alias)` imports the family module, `probe(alias)`
  returns the row and imports nothing. 6.2 states both return types above the
  two name tables.
- **The loader could not compute the defaults 5.2 promises.** 3.3's literal
  rule now covers `STOP`, `DEFAULT_EFFORT`, `DEFAULT_DATE`, `LORA_TARGETS` and
  an environment's `INSTRUCTIONS` keys, read with `ast.literal_eval` over the
  source; `ast` is on `schema.py`'s import bracket, the family and backbone
  modules and `constants/path_datasets.yaml` on its `reads:` line, and the five
  names in `selfcheck`.
- **One `cuts` could not serve both callers.** 1.7 now pins
  `cuts(thinking, min_think, max_cuts)` (offline, `m.end()`, terminal cut,
  even thinning) and `cuts_live(thinking_so_far, min_think)` (streaming,
  `m.start()`, no terminal cut, no thinning, the cap counted by the caller),
  states the per-cut `min_think` filter and where the event-level gate lives,
  and says on both files' lines that `example.cut` and `spec.cut` are not the
  same coordinate. 7.3 step 4 calls `cuts_live`. 9(a)#31 records the decision.
- **The record had no column for the task's own text.** `meta.task_text` added
  to 1.1 with its writer (`agent/loop.py`, after `Environment.open`), a
  `DEFAULTS` entry, `VERSION` on `data/task_record.py` from the first version,
  and `task_text` in `to_messages`'s parameter list; `meta.instructions` is
  marked as a variant name and never the task text.
- **`freeze` refused legitimate wider requests.** 3.4 now writes
  `settings.yaml` as a stage projection (the stage's sections, its non-keyed
  request fields, its inherited fields, the run-time-only `data` that a
  generator `eval` and `score` need, and the `_` block), compares
  `settings_diff.yaml` for the collision check, and merges the non-keyed request
  fields on a match with a launch entry recording the wider request. 2.1 gained
  the paragraph on run-time-only fields; 9(a)#32 records the decision.
- **The start row could not be both after the alive check and before the
  sessions.** 8.1 fixes the order: inside one lock hold — registry, gate,
  reservation, ports, append with `status: "launching"`; then release, sessions,
  alive check; a failure is a `launch_failed` **finish** row, never a rewrite.
  2.5's reservation clause gained "or a start row younger than the launch
  timeout", 8.6 and scenarios 1, 6 and 9 were rewritten to match.

### Applied — major

- `args`' column comment says what it is for and that it is not cparam's
  training target; 1.2 states that cparam's target is a string and 1.3's
  `target` row says which method takes and which derives it.
- Endpoint files are named by the **replica** index (`service_agent_<replica>.json`,
  `service_probe_0.json`), so a loop piece computes the name from its own
  `--piece i/n` and `settings.yaml`'s `replicas` and reads no `meta.json`.
  Renamed in 0.2, 1.5, 7.1, 7.2, 7.4, 8.1, 8.6 and 2.3.
- `jobs/launch.py` gained an `offers:` line (`launch`, `refire`,
  `teardown_services`) and is a library with no `__main__`; `refire` and `retry`
  are `run.py` subcommands, in the tree line, in 8.6's table, in 2.3, 2.4 and in
  scenarios 3 and 4. 9(a)#35.
- The class order has a construction rule: `train/methods/ctool.py` computes it
  from the train split's unique `tool` values sorted ascending, `base.py` writes
  it into `best/meta.json`, a resume reads it back; 6.2's `attach_head` row says
  `n_labels == len(labels)` and that the order is the caller's.
- `schema.py` reads `constants/path_datasets.yaml` (0.2, 3.2 guarantee 2, that
  file's `read by:` line), and 5.7 refuses a `data.instructions` value the
  chosen environment does not have; 0.4's new-environment row names the split
  axis values and the new venv's PyYAML/Polars/NumPy.
- `role` and `family` are keyed with the `result:` block (3.3's `models` entry
  and a paragraph in 6.1).
- `serving:` is closed: `serving.env` holds only location and resource
  variables, every other variable is an `env_result:` column and `extra_flags`
  is a `result:` column, with `VLLM_USE_FLASHINFER_SAMPLER` and
  `VLLM_BATCH_INVARIANT` named. The sample row moved accordingly. 9(a)#33.
- A finished directory is skipped only when its `consumed.json` entries — and,
  for `sample` and `inject`, `meta.json`'s `split_files` hashes — still match
  the files on disk; on a mismatch the walk refuses and names both hashes
  (2.3, 8.6, scenario 2). 9(a)#36.
- `inject` gained the version gate: the build run behind its `probe_score`
  train run must agree with this run's `data/probe_input.py` VERSION, and both
  referenced train runs with its `models/probe_models/base.py` and backbone
  VERSIONs (2.5).
- The service pieces of a finished run are ended by the walk that writes
  `done.json`, through `jobs/launch.teardown_services`, skipping a piece another
  live run is attached to; `ls` flags the leftover as `orphan`
  (2.3, 0.2, 8.6). 9(a)#37.
- A record file whose first line does not parse as a `meta` row is unowned and
  is deleted by the login-machine release, whatever its age (1.1).
- `judge_service` is restated over the piece's start-row time, its session
  liveness and one port probe, with the reason the old rounds-counting form
  could never fire; 8.4 says a service's launch time comes from its start-row
  entry.
- A pinned reference is `key: {<stage>: <hex>}` / `dir: {<stage>: <path>}` with
  one entry per stage the table names (two for `probe_score`), skips the
  inheritance check and the shared-build-key gate, must state the inherited
  sections under `meta.override`, and is flagged `pinned` by `ls` (5.4, 8.6).
- `login_host:` added to `constants/path_outputs.yaml`; `run.py` and
  `jobs/launch.py` refuse to run on any other host, so the `fcntl` lock on
  NFSv3 home is always taken by one machine (6.3, 3.4, 8.6, scenario 9).
  9(a)#34.
- `--check` became `python -m models.probe_models.service check --base-url
  <url>`, a client against the running service; `jobs/launch.py` runs it after
  the port answers and before the first loop piece, and a non-zero exit is a
  `launch_failed` finish row (7.2, 2.3, scenario 7). 9(a)#38.

### Applied — minor

5.1's skeleton shows `meta: {notes, override}` (both reviewers raised it);
`jobs/registry.py`'s bracket is `[PyYAML]` and its tree line no longer says
"standard library" (both reviewers); the three `read by:` lines gained
`models/agent_models/service.py`, `jobs/launch.py` and
`data/environments/__init__.py`, and path_models.yaml lost the
"everyone else reaches it through `models/__init__.py`" clause; 2.1 calls
`run_dir_of`; the sweep child name is `repr()` of the parsed YAML value and the
two examples now use values from the swept list (`train.lr=0.0003`);
`run.py sync` writes the `failed` finish row and 8.2 names all four writers of
the enum; `probe_eval.py`'s `reads:` line names both train `meta.json`s;
`selfcheck` validates every `table.yaml` row's `family` and `weights` and 5.7
refuses an alias whose `role` is the wrong side; 0.1 and 8.6 count "every
interpreter in the `venvs:` map" instead of three; 0.4's two task-record rows
drop "or the environment file"; 5.3 states that a branch-backed axis is
dispatched through an explicit mapping whose `else` raises, naming the three
files; 0.4's agent-family row and 7.2 name the rendering library in both venvs;
8.3 takes every `meta.json` rewrite under the registry lock and through a
rename; 1.4's generator shape writes null and `n: 0` for a risk whose referenced
`chosen` is null; the heartbeat file is `heartbeat/<piece>-<launch>.jsonl` and
`ls` takes the newest file per piece and counts done record files for a claiming
stage.

### Not applied, and why

Nothing was refused. Two findings were applied in the other reviewer's form
where the two fixes could not both hold, and both are recorded above: the `any`
venv lookup (6.3 resolves `any` to `venvs.probe` rather than adding an `any:`
row, which would duplicate a path and be miscounted by 0.1) and `PROBE_KIND`
(declared twice and compared by `selfcheck` rather than exposed through a new
`schema.py` accessor, which 5.1 forbids).

Two edits touched a tree line's *description* without touching the tree:
`data/probe_input.py`'s line no longer says "two pure functions" (there are
three), and `models/probe_models/service.py`'s line says `check` is a client
subcommand. Neither adds, removes, moves, splits or renames a file.

9(b) gained no refused fix. 9(b)#18 was widened to cover `login_host:` beside
`hosts:` and `venvs:`. 9(a) gained #31 (two cut rules), #32 (the stage
projection), #33 (the closed `serving:` block), #34 (`login_host`), #35
(`refire` and `retry` on `run.py`), #36 (the consumed check before a skip), #37
(service teardown) and #38 (`check` as a client).

## Round 3 — 2026-09-17, three reviewers, 43 findings

The third pass read the document Round 2 produced. Two reviewers reported the
same blocking defect (`match` has no environment), so the list below groups by
defect. Every blocking and major finding was applied; every minor whose fix was a
sentence was applied. One finding was applied in a corrected form and one in a
partially corrected form, both recorded under "Applied with a correction".
Nothing required adding, splitting, moving or renaming a file of the tree, so
Part 9(b) gained no refused fix; 9(a) gained five new decisions (#39-#43).

### Applied — blocking

- **2.6 gave the two libraries the registry rows, which a compute node may not
  write.** "The registry rows" is gone from both the `main(run_dir)` sentence and
  the "Who owns what, on both sides" paragraph, and the paragraph now states that
  neither library writes one: the start row is `jobs/launch.py`'s or `run.py`'s,
  the finish row `run.py`'s (8.1, 8.2). Without this a builder would put
  `append_start` inside `trainer.run` — a duplicate start row per train run and
  an `fcntl` append to an NFSv3 home file from a compute node, which 8.6 exists
  to forbid.
- **`models/probe_models/base.py` had no interface, although five files
  manipulate its object.** 6.2 gained a third table, "The probe object", pinning
  `VERSION`, `load`, `Probe.save`, `Probe.tokenizer`, `Probe.max_len`,
  `Probe.forward`, `Probe.score` and `Probe.generate`, with where `tok` comes
  from and where the class order and `CHECKPOINT_META` are written. The tree line
  for that file already promised exactly these names.
- **`match(pred, target)` could not reach an environment** (two reviewers). The
  eval hook is now `match(pred, target, env)`, the caller supplies the object
  (`report` and a generator's `validate` both call `open_env(cfg.data.env)`;
  a classifier is passed `None` and ignores it), 3.4's projection writes `data`
  into a generator **train** run's `settings.yaml` beside a generator `eval`'s and
  `score`'s, 2.1's run-time-only paragraph names three stages instead of two, and
  `data/environments/__init__.py` is on `train/methods/{cgen,cparam}.py`'s import
  lines and in that file's `used by:`.
- **`run_dir_of` could not tell a debug upstream from a real one.** The
  signature is `run_dir_of(stage, key, *, debug)`, the caller passes its own
  frozen `_debug`, and a resolved reference passes `debug=False` because a
  reference is always keyed without the overlay. 2.1's call site updated.
- **The inject version gate compared against entries an inject run does not
  have.** It now compares each referenced train run's recorded `_versions` for
  `base.py` and for **its own** backbone, and the build run's recorded
  `data/probe_input.py`, against the `VERSION` lines `schema.py` reads from the
  current source (3.3's text rule). The reason is on the page: an inject setting
  may not name a `models.probe`, and two probes may sit on two backbones.
- **The port assignment made `--attach-only` unreachable.** 7.4 now orders the
  two steps: inside the lock hold `jobs/launch.py` first looks for an attachable
  agent server (a live row's `agent` piece on this row's `serving.host` whose
  endpoint file claims the same `result:` block) and passes `--attach-only`; only
  when none is found does it start one at `serving.port + replica`, and only that
  branch relocates off a busy port. 7.1 points at the ordering.
- **No rule said which host a card-taking piece lands on.** 3.4 gained a
  placement paragraph: agent service on its row's `serving.host`; probe service
  and train piece on the first host in `hosts:` with enough free cards under
  2.5's busy test, preferring the host this run's agent service is on; loop pieces
  and CPU stages on `login_host`. The chosen host goes into the piece entry's
  `host` field, and a run with no host free is refused naming every host probed.
- **`_upstream` was "name -> key" with three readers and a collision.** 1.5 pins
  the naming: a same-setting upstream is keyed by its stage name, a reference by
  `<field>.<stage>`. The three readers are named where they are used (2.5's
  shared-build gate, 7.2's `/health` comparison, `jobs/launch.py`'s checkpoint
  resolution), and `_upstream.build` became `_upstream["build"]` everywhere.

### Applied — major

- `Writer.frame()` added to 1.1's offered functions, with the rule that the live
  caller passes `writer.frame()` and the offline caller `read(path)`.
- `check --base-url <url> --run-dir <dir>`: the client reads the same three facts
  `agent/inject.py` reads out of the frozen `settings.yaml` and compares them
  against the echo (7.2, 2.3, 9(c)#7). `models/probe_models/service.py` therefore
  imports `schema.py` for `load_frozen`, which takes that file's importer count
  from nine to ten (0.2, 2.6, 5.1).
- A CPU stage now runs the same two gates as a tmux stage, inside one hold of
  `runs.jsonl.lock`, and writes `meta.json` and its `launches` entry through
  `registry.write_meta` (2.3, 8.0). Without it three of six stages had no
  dirty-tree refusal, no `dirty.patch` and no producer for the five git fields of
  their start rows.
- `jobs/launch.git_state(allow_dirty) -> dict` is the dirty gate and the git
  fields in one function, called by `jobs/launch.py` and by `run.py` (0.2's
  `offers:` line, 2.5).
- `eval/method_table.py` is read through `run.py table [workflow]`: the
  subcommand is on run.py's tree line, in its `imports:`, in 8.6's table, and the
  file's `used by:` is `run.py`.
- `launch(...) -> tuple[str, list[dict]]`, the first element `up` or the reason
  (`alive_check`, `service_check`); `run.py` writes the `launch_failed` finish row
  on anything else and the piece entries come back either way (0.2, 8.1, 8.2).
- `Environment.step(reply_text) -> StepObservation` (`action`, `observation`,
  `error_kind`, `completed`): the environment owns the action extraction and the
  completion signal, so a new benchmark adds no line to `agent/loop.py` (4.1,
  4.2, 7.3 step 3). 9(a)#41.
- `agent/inject.py` offers `system_text(cfg)` and `agent/loop.py` appends it to
  the developer message before its first render, which is what makes a `p1`
  format's system text expressible at all (7.3, 0.2).
- `meta.generation` and `meta.inject` are `str` (canonical JSON text), not
  structs, so a new field in either section costs no edit to
  `data/task_record.py` and no `VERSION` bump (1.1). 9(a)#43.
- `EFFORTS` added to the family-module table and to 3.3's literal rule; 5.7
  refuses a `generation.effort` outside the chosen family's tiers; 5.3 gives the
  axis a selfcheck column (the union over families); 0.4's agent-family row names
  the schema edit.
- `PROBE_TEXT_FIELDS` declared once in `schema.py` beside the stage table; 1.7,
  2.1, 2.2, 3.3, 3.4, 5.4 and 5.7 name the tuple instead of listing three fields,
  and 0.4's cut-rule row says that leaving a new field out of it is the one edit
  that makes a live run silently disagree with its training.
- `CHECKPOINT_META` added to the train-method hook table; 1.6 says `call_sep` and
  `param_only` come from it and are merged into `best/meta.json` unread; 7.2's
  `/gen` takes both from the checkpoint; 0.4's fourth-method row names
  `base.py` in the third-`PROBE_KIND` clause.
- `requested_pairs(env, split, tasks, n_tasks, seeds)` added to
  `data/environments/__init__.py` with its ordering pinned (2.3, 4.1, 4.2), so
  the three files that need the list stop computing it three ways.
- `pid` added to the piece entry; 8.5 judges a `cpu` piece by `os.kill(pid, 0)`
  on `login_host`, 8.6 kills it by that pid, and 1.5 says a `cpu` piece writes no
  `log/<piece>.txt`.
- `edited` is computed by `run.py` and passed into `registry.ls` as an optional
  per-`run_id` map (8.0, 8.6), because `jobs/registry.py` may not import
  `schema.py`.
- The refire quota is retired: `run.py refire` warns, naming the earlier launch
  entries for this piece, and proceeds (2.3, 8.6, 9(c)#4). 9(a)#39.
- `score.baseline`'s split and seed mismatch is refused at load (5.7); 2.5 keeps
  the record-level gate as the check that the baseline finished.

### Applied — minor

`run.py`'s `reads:` line gained `path_outputs.yaml`, `consumed.json` and the
files it names, the `service_<kind>_<replica>.json` files and the probe report;
`write_report` and `read_report` signatures written in 1.4; `labels` marked
classifier-only, null for a generator; `date` dropped from `/health` with the
render-only nulls stated; `probe.lora_targets` added as 3.3's fourth pre-diff
resolution; `clients` pinned as a dataclass in `agent/generate.py`;
`data/environments/__init__.py`'s `VERSION` folded into the `sample`, `build` and
`inject` version lists with the reason (4.1); the four shorthand annotation
blocks in 0.2 expanded to literal five-line blocks and the two empty
`__init__.py` files given full ones; the `DEFAULTS` reading mechanism restated
(read the file's schema, select what is present, fill the rest from `DEFAULTS`),
since neither named library call delivers it; `split_source: hash` pinned to
`int(sha1(task_id)[:8], 16) / 2**32` and never Python's `hash()` (5.2, 0.2);
`beat`'s `<launch>` resolved from the run directory's own `heartbeat/` listing
instead of `meta.json`, and a one-process stage declared piece 0 (8.0, 8.4); the
unowned-record-file deletion given an age margin of the launch timeout (1.1,
9(c)#4); the generator `exact` block computed over the test rows (1.4);
`inject.probe_gen` refused unless its method is a whole-call generator, read off
`CHECKPOINT_META["param_only"]` (5.7, 5.2); and 5.6/5.7 state that the
workflow-section refusal is evaluated over the YAML file itself, so `--debug`
works on every workflow.

### Applied with a correction

1. **"Fold `_resolved.probe_temperature` into the inject key instead of the
   classifier eval key"** (major). The complaint is right and was applied; the
   literal fix was not, because it breaks 3.2 guarantee 2: `key` would have to
   read a report out of the output tree, and an inject key would stop being
   computable before its eval run exists (9(a)#5 rests on that too). What was
   applied instead keeps the key pure and buys the same thing: the inject key
   folds the `probe_score` **train** key plus the `VERSION`s of the two modules
   that fit the temperature (`eval/utils/probe_eval.py` and the referenced
   setting's `eval/methods/<m>.py`), and the classifier eval key stays in
   `_upstream`, where it is needed to locate the report. Editing `eval.risk`,
   `eval.theta_grid`, `eval.bootstrap` or `eval.bootstrap_seed` therefore no
   longer re-keys an inject setting. 2.1's justification (which named theta,
   a number the live run never takes from that report) was corrected, 2.2's plus
   column and version list rewritten, 5.4 updated, and 9(c)#5 now states the
   consequence. 9(a)#40 records the choice and both alternatives.
2. **The `_upstream` naming finding listed `baseline.sample` among an *inject*
   run's entries.** Applied with that one entry moved: `score.baseline` is the
   `score` stage's reference, not the `inject` stage's (2.2's key table and
   9(c)#7 both say so, and `settings.yaml` is a per-stage projection). So an
   inject run's map is
   `{probe_score.train, probe_score.eval, probe_gen.train}` and a score run's is
   `{inject, baseline.sample}`. The naming rule itself — stage name for a
   same-setting upstream, `<field>.<stage>` for a reference — was applied exactly
   as proposed.

### Not applied

Nothing was refused outright. No finding required adding, splitting, moving or
renaming a file, so Part 9(b) gained no entry this round.

Two edits touched a tree line's *description* without touching the tree:
`data/environments/__init__.py`'s line now names `StepObservation`,
`requested_pairs` and its own `VERSION`, and `agent/loop.py`'s line names the
`system_text` call and says the loop runs until the environment reports the task
completed. Neither adds, removes, moves, splits or renames a file.

9(a) gained #39 (the refire quota retired, which makes CONTEXT's refire-quota
entry obsolete alongside the eight #13 already names), #40 (what stands in for
the classifier eval key in an inject key), #41 (`step` owns the extraction and
the completion signal), #42 (the environment base file's `VERSION` is keyed) and
#43 (the two record columns are canonical JSON text).
