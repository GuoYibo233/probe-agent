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

## Round 4 — 2026-09-17, 32 findings

The fourth pass read the document Round 3 produced. Several findings were the
same defect seen twice (the class-order hook, the eval `report` signature, the
render-only probe piece's card, the `step` signature), so the list below groups
by defect. Every blocking and major finding was applied, and every minor whose
fix was a sentence. Nothing was refused. No finding required adding, splitting,
moving or renaming a file of the tree, so Part 9(b) gained no refused fix; 9(a)
gained three new decisions (#44-#46).

### Applied — blocking

- **The live probe's text had no source, and two findings disagreed about who
  renders.** One signature now carries both fixes:
  `step(env, clients, cfg, writer, messages, prefix_ids, history, task_text,
  step_index, seed)`, identical in `agent/generate.py` and `agent/inject.py`.
  `agent/loop.py` renders once per step and passes the ids down (so the loop's
  render result is no longer discarded and no step renders a second time), and
  it owns the `(action, observation)` list, appending after each
  `Environment.step` and passing the accumulated pairs plus the `meta` row's
  `task_text`. 1.7's sentence "the live caller builds it from the step it is
  inside" was wrong and is replaced: `history` is the pairs of the **earlier**
  steps, in both callers, since at a cut the current step has produced none.
  7.3's numbered list now opens with the loop rendering and nothing below it
  renders again.
- **The class order had no channel from the method file to `base.load`.** 2.6's
  train hook table gains `head_labels(df, cfg) -> list[str] | None`, called by
  `trainer.run` on the training-split frame before `base.load`, which then gets
  `labels` and `n_labels` from it (both None for a generator) and reads the list
  back from `ckpt_dir/meta.json` on a resume. 1.3's "How the list is built"
  names the hook instead of saying the method passes the list to `base.py`;
  6.2's `load` and `attach_head` rows match.
- **The eval `report` hook could reach neither the class order nor the
  referenced frame.** It is now
  `report(pred_df, cfg, ref, labels) -> tuple[dict, DataFrame | None]`, with
  `ref` the whole `read_report(<referenced eval run_dir>)` **tuple** (a `dict`
  cannot carry the `fires` frame a generator joins on) and `labels` the list
  `probe_eval.run` already reads out of the train run's `meta.json`.
  `probe_eval.write_report` fills the report's `labels` field from that same
  value, not from the method's returned dict (1.4).
- **The prediction row carried no ground-truth tool, so `eval/methods/cparam.py`
  could not be written.** `data/prediction.py` gains a `tool` column, copied by
  `train/utils/trainer.py` with the other four carried columns, and 1.4 states
  how a generator's three tiers are computed: `tool_ok` is
  `fires.label_pred == prediction.tool`, `full_call_ok` is `tool_ok and
  params_all_ok`, and a cparam call is rebuilt as `tool + "(" + <arguments>`
  before `env.split_args`.
- **Walk 1 could not produce an evaluable dataset.** `sample.split` and
  `inject.split` are `list[axis]` (defaults `[train, dev, test]` and `[test]`),
  `requested_pairs(env, splits, tasks, n_tasks, seeds)` concatenates
  `env.tasks(s)` in the given order before applying `tasks` and `n_tasks`, and
  the environment class gains `SPLIT_ROLE: dict[str, str]` (AppWorld:
  `{train: train, dev: val, test: test}`), which is what maps the benchmark's
  split names onto the `train` / `val` / `test` values an example row carries.
  Under `split_source: env`, `data/build_dataset.py` takes each row's split from
  the record's `meta.split` through that map (2.5, 6.3). `SPLIT_ROLE` is covered
  by the environment file's `VERSION` (4.1, 4.4), the split axis is validated
  element by element (5.3, 5.7), and `score.baseline`'s split refusal became a
  superset test over two lists.

### Applied — major

- The expanded model row has a name: `models.agent_row` and `models.probe_row`,
  written by the loader, while `models.agent` and `models.probe` stay alias
  strings. 1.5, 3.3, 5.2, 6.1 and the two refusals in 7.2 all name the same
  field, and the two rows are keyed through 3.3's `models` entry and never as
  fields of the diff.
- Every format file declares `REQUIRED: frozenset[str]` beside `VERSION` and
  `DEFAULTS`; the shared reader in `data/__init__.py` raises before filling when
  a required column is absent from the file, and `selfcheck` checks the literal.
  Part 1's second `DEFAULTS` rule and 0.4's task-record row name it.
- 5.4's inheritance agreement is scoped per group: `data`, `models.agent` and
  `generation` across every reference, the `PROBE_TEXT_FIELDS` only across the
  references whose workflow provides a `build` stage. Without it no inject
  setting with non-default probe-text fields could load, because its
  `score.baseline` points into `baseline.yaml`, whose workflow may state no
  `build:` section. 5.7's refusal and 9(c)#7 say the same.
- `eval/score_run.py` builds its own pair list: `requested_pairs` is on its
  `imports:` line and it is the fourth caller (2.3); both `score` record gates
  are stated over that list instead of over "every pair the scored run holds".
- 1.4's "Who writes" gives both report files to `eval/utils/probe_eval.py`
  (2.6's contract, which the method's signature makes the only workable one),
  and the three `eval/methods/*.py` annotation lines became
  `reads: - writes: -`.
- `meta.json`'s field is `upstream`, not `_upstream`: 0.2's `probe_eval` line is
  corrected, the generator-eval gate in 2.5 names `meta.json`'s
  `upstream["build"]`, and 1.5 says the inject-side gate reads the same value out
  of a `settings.yaml`'s `_upstream["build"]`.
- 1.5's heartbeat `<launch>` parenthetical now matches 8.4: the next free index
  under the piece's own prefix, resolved by listing `heartbeat/`, so no
  compute-node piece opens `meta.json`.
- `system_text(cfg)` returns the format's text **only for a `p1` placement**, so
  a `p2` entry's text is not applied twice; the `FORMATS` field table says the
  same.
- 3.4's placement rule distinguishes the two probe-service pieces: one that
  loads a checkpoint takes 1 card and enters the card search, one started with
  `--render-only` takes none and goes on `login_host`. 7.2 marks `--device`
  optional and absent under `--render-only`; 2.3's `sample` row says the same.

### Applied — minor

`git_state(run_dir, allow_dirty)` in 0.2 and 2.5, with the reason it takes the
directory; `eval/method_table.table(workflow=None, out=None) -> str` pinned in
8.6 and on an `offers:` line; `registry.where(stage, key, *, debug=False)` in
8.0, with 8.6 saying `run.py where` computes the path with `schema.run_dir` and
uses `registry.where` only for a key read out of a row; 8.2 states that every
reader takes the newest start row and the newest finish row for a `run_id` and
that `elapsed_s` is measured from the newest start preceding the finish; 1.1's
release no longer starts the replacement piece (that is `run.py refire`);
`schema.freeze` writes through a temporary name and a rename inside the lock
hold; `jobs/launch.refire` rewrites the refired piece's entry in `meta.json`'s
`pieces`, which `ls`, `kill` and the card reservation read for a piece's current
host and session; Part 8's opening says "standard library and PyYAML";
`jobs/launch.py` added to `table.yaml`'s `read by:`; ssh, tmux and nvidia-smi
added to `jobs/registry.py`'s `reads:`; `build.result_cap` renamed
`build.probe_result_cap` everywhere (5.2, 1.7's `assemble`, `PROBE_TEXT_FIELDS`,
7.3's step 4, 9(c)#7) with half a sentence saying it is a different clip from
`Environment.RESULT_CAP`; 1.4's generator writes `exact[risk]` as a struct with
`n: 0` and null fields rather than as null.

### Applied with a correction

1. **"`run.py` calls `freeze` inside the same `runs.jsonl.lock` hold that
   carries the launch gate and the start-row append."** Applied with the
   mechanism written out, because for a tmux stage that hold is
   `jobs/launch.py`'s, not `run.py`'s: `run.py` takes the lock before the freeze
   and holds it across the launch, and `jobs/launch.py`'s own hold is taken
   inside it, which `fcntl` allows within one process. 3.4, 8.6 and 9(c)#1 say
   it the same way. The finding's scenario numbers ("walk 8", "walk 11") were
   read as 9(c)#6 (the sweep) and 9(c)#9 (two sessions), which are this
   document's numbering.
2. **"`eval/methods/cparam.py` rebuilds a parseable call as `tool + "(" + s`
   before calling `env.split_args`."** Applied with the rebuild on the
   **callers** of `match`, not inside it: `match(pred, target, env)` has no tool
   parameter, and both callers — `report` and `validate` — hold a frame with the
   `tool` column. So cparam's `match` is handed two whole calls.
3. **The `step` signature.** Two findings proposed two different extensions
   (`history` + `task_text`; `prefix_ids`). Both are right and both were merged
   into one signature. The second finding's alternative — deriving the history
   from `messages` inside `inject.py` — was not taken, because the shape of
   `messages` is the family's conversation format while `history` is
   `(action, observation)` pairs, and `agent/loop.py` already holds both. Its
   "while there" clause about `agent/generate.py`'s import line was applied in
   its second form: the `clients` dataclass annotates `probe` as `object`, so
   that file imports no probe client and its annotation line stays true.

### One consequence to flag, not an edit

With `sample.split` a list, `debug.yaml`'s `n_tasks: 3` applies to the
concatenation, so a `--debug` walk of `train_probe.yaml` collects three **train**
tasks and its build produces an empty `val` and an empty `test` — the same shape
of failure the split finding fixes, reintroduced at debug sizes. The fix the
finding specified keeps 2.3's ordering rule otherwise unchanged, so nothing was
changed here beyond it. Making `n_tasks` per split, or giving `debug.yaml` a
per-split cap, is gyb's call.

### 9(a) gained

#44 (the split lists and `SPLIT_ROLE`), #45 (`REQUIRED` on every format file),
#46 (the two named model-row fields).

## Round 5 — 2026-09-17, 31 findings

The fifth pass read the document Round 4 produced. Four pairs of findings were
the same defect seen twice (`requested_pairs` and `run.py`, the `ls` progress
count for a claiming stage, and the prediction row's `target`), so the list below
groups by defect. Every blocking and major finding was applied, and every minor
whose fix was a sentence. One finding was applied in the other reviewer's form,
one in a corrected form, and both are recorded under "Applied with a correction".
Nothing was refused. No finding required adding, splitting, moving or renaming a
file of the tree, so Part 9(b) gained no refused fix; 9(a) gained two new
decisions (#47-#48).

### Applied — blocking

- **The probe object could not receive the values its own contract makes it
  apply.** 6.2's two pinned signatures are now
  `load(row, cfg, *, probe_kind, n_labels=None, labels=None, ckpt_dir=None)` and
  `save(dir, *, labels=None, extra=None, meta=None)`. `cfg` is the frozen
  `Setting`, annotated `object` in `base.py` (which therefore still imports no
  `schema.py`), and the row says exactly what `base.py` reads off it:
  `cfg.probe.tuning`, the four `cfg.probe.lora_*` fields, `cfg.train.max_len` and
  `cfg.models.probe`. `meta` is the identity block `trainer.run` passes —
  `{backbone, tuning, max_len, train_key}` — which `save` merges into
  `best/meta.json` beside `labels` and the method's `extra`. On a restore `row`
  and `cfg` are both None and those values come from `ckpt_dir/meta.json`. 1.6
  says the same from the checkpoint's side. Without this, `base.py`'s cheapest
  guess for the tuning is a module constant or a default of `full`, which trains
  a full-weight probe for a LoRA setting under the LoRA key.
- **`Batch` and `Outputs` crossed a file boundary and were defined nowhere.**
  Two rows added to 6.2's probe-object table: `Batch` is `dict[str, Any]` whose
  `input_ids`, `attention_mask` and optional `position_ids` are what
  `Probe.forward` consumes, every other key being the method's own and never read
  by `base.py`; `Outputs` is a dataclass declared in `base.py` with `logits` and
  `hidden`, both aligned to `input_ids`. 2.6's `batches` row points at them.
  Without them the three method files write three batch shapes, `forward` fits at
  most one, and the per-method alignment gate cannot catch it.
- **The launch gate was a conjunction and the ordering in 8.1 falsified it.**
  2.5's gate is now a disjunction in the same shape as the card reservation two
  bullets below: refuse when the newest start row has no finish row and any one
  of a live session, a heartbeat younger than the stall line, or a start row
  younger than `launch_timeout_s` holds. The message is the session name when
  there is one, the run_id and the row's age for a `launching` row with no
  session yet. 9(c)#6 and 9(c)#9 were rewritten to name the clause each walk
  refuses on. Under the old conjunction the second sweep child launched a second
  set of pieces into a directory the first was using, and a service piece (which
  never beats) or a loop piece still importing its environment package made the
  gate pass for as long as startup takes.
- **`--debug` on `train_probe.yaml` could not run to completion.** `n_tasks` is
  now a cap **per split** in `requested_pairs`: the filter and the cap apply
  inside each split, and the per-split lists are concatenated in the given split
  order before the seeds cross. 2.3's ordering paragraph, 4.1/4.2's
  `requested_pairs` lines, the two `n_tasks` comments in 5.2, 5.6 and 9(c)#8 all
  say it. `debug.yaml` stays sizes-only and a `--debug` walk now collects 3 train,
  3 dev and 3 test tasks. This is the consequence Round 4 flagged and left to the
  owner; it is applied here and recorded as 9(a)#47, which is the entry the owner
  is most likely to want to look at.
- **3.3's `models` entry was unconditional, so an inject key could not be
  computed at all.** It now follows 2.1's "sections read" column, exactly as
  `fields` does: `{"agent": models.agent_row}` for `sample` and `inject`,
  `{"probe": models.probe_row}` for `train`, `{}` for `build`, `eval` and
  `score`. Without it `key("inject", setting)` reads a field 5.2 says is absent
  from an inject setting, and a `sample` key moves when the probe alias changes.
- **`INSTRUCTIONS` and `SPLIT_ROLE` were declared only as class attributes, so
  the loader had no path to either.** 4.1 extends the `VERSION` device to both:
  each is assigned at module level, at column zero, exactly once, in every
  `data/environments/<env>.py`, and the class body writes `INSTRUCTIONS =
  INSTRUCTIONS` and `SPLIT_ROLE = SPLIT_ROLE`, which are indented and not second
  matches. `env.INSTRUCTIONS[...]` and `env.SPLIT_ROLE` keep working for 4.2's
  callers.

### Applied — major

- **`run.py` computes the requested (task, seed) list itself** (two findings).
  `data/environments/__init__.py (open_env, requested_pairs)` is on `run.py`'s
  `imports:` line, the split task-id files on its `reads:` line, and `run.py` is
  the fifth caller on that file's `used by:` line and in 2.3's list. 2.3's
  "`run.py` does not call it" is replaced: it calls it on the setting it holds,
  which is what makes the subset skip test and `done.json`'s `pairs` the same
  list `build` will demand, and `meta.json`'s `split_files` keeps only its hash
  and audit role — 8.3's justification for that field was corrected to match.
  Reading the list back out of `meta.json` is absent on a first walk and stale
  after the ordinary edit that scales a collection up, which reaches 1.1's
  unrecoverable state by the most routine path there is.
- **A keyed model column could be read live from `models/table.yaml`.** 6.2 and
  7.1 now state that inside a run every consumer of a keyed column reads
  `cfg.models.agent_row` / `cfg.models.probe_row`, that `models.agent(alias)` and
  `models.probe(alias)` supply only the family module, the weights path and the
  `serving:` block — the one block a run may read live — and that `base.load`'s
  `row` **is** `cfg.models.probe_row`. The agent service compares `/v1/models`
  against the frozen row. 5.2, 6.1 and 0.2's two annotation blocks match, and the
  absolute weights path is now explicitly outside the frozen expansion, so
  3.3's `models` entry and the field it names are the same object.
- **The prediction row had two writers for one column** (two findings, with two
  incompatible fixes; see the correction below). 1.3's prose and 2.6's `predict`
  row now give the same division: `predict` returns `example_id`, `method`,
  `target` and its own output columns; `trainer.run` copies the five
  method-independent columns on `example_id`; `data/prediction.py`'s writer
  stamps `version`. `target` stays the method's, which is what keeps
  `if method == "cparam"` out of `trainer.py`.
- **3.3's upstream line contradicted 2.1's carve-out.** The formula now reads
  "minus the references 2.1 marks as not keyed", with a bullet naming the one:
  `inject.probe_score`'s eval key stays in `_upstream` while the two module
  `VERSION`s of 2.2 stand in for it in the `versions` entry. Folding it would
  re-key every inject setting on an `eval.risk` edit, which 9(a)#40 exists to
  avoid and 9(c)#5 asserts is avoided.
- **`SPLIT_ROLE` was validated at load through a path that did not exist.** It
  is the seventh name in 3.3's literal rule, is on `schema.py`'s `reads:` line in
  0.2 beside `INSTRUCTIONS`, and is in 8.6's selfcheck list (with `INSTRUCTIONS`,
  which was also missing there). 5.3's and 5.7's wording is unchanged.
- **The launch timeout was named in five places and defined in none.**
  `launch_timeout_s` is an entry of 8.5's `DEFAULTS` dictionary at 1800 s — the
  warm-up cap, since both measure how long a piece may take to exist — and the
  one entry no piece overrides. 1.1, 2.5, 7.4, 8.1 and 8.2 each name
  `registry.DEFAULTS["launch_timeout_s"]`. All four readers already import
  `jobs/registry.py`.
- **`ls` could not compute the progress of a claiming stage** (two findings).
  8.0's `ls` gains `progress: dict[str, tuple[int, int]] | None = None`, the
  per-`run_id` `(done, total)` `run.py` computes with
  `data/task_record.done_pairs`, exactly as it already hands in `edited`; 8.4 and
  8.6 say `ls` falls back to the sum of beats when it is not supplied. That keeps
  the done rule in one file and `jobs/registry.py` importing nothing from the
  repo.
- **`final.judge` was a struct, which the document rejects three paragraphs
  later.** It is `str` (canonical JSON text) with a declared `final.success |
  bool` beside it, the rule `meta.generation` and `meta.inject` already follow;
  4.2's `judge` row says the loop writes the dict as text and its `success` into
  the column. 9(a)#48 records it. Otherwise a second benchmark's evaluation
  fields cost an edit to `data/task_record.py`, a `VERSION` bump and a full
  recollection, which 0.4's new-environment row does not list.
- **No compute-node piece had a commit to record.** `run.py` calls
  `jobs/launch.git_state` before `schema.freeze` inside the one lock hold, and
  `freeze(setting, run_dir, resolved, commit)` writes it into the `_` block as
  `_commit`. 1.1's `meta.commit`, 1.5's `done.json` commit, 1.4's report
  `commit`, 1.6's `last/` commit and 2.4's resume test all name `cfg._commit`,
  and no stage probes git for itself. Otherwise a refire days later records
  whatever HEAD happens to be, and CLAUDE.md's rule that a recorded HEAD leads
  back to the code that ran holds by luck.

### Applied — minor

`[torch]` on the three `train/methods/*.py` import lines and `[polars, numpy]` on
the three `eval/methods/*.py` lines in 0.2 (without them the first `import torch`
fails selfcheck); `read_frame(path, *, schema, defaults, required, version)` and
`write_frame(path, df, *, schema)` named in Part 1 beside the three id functions,
with the five "the shared reader" references pointing at the name and 0.2's
`data/__init__.py` line carrying both; `parse`'s returned keys pinned to exactly
`reasoning` and `content`, the two `StepResult` fields, with per-family
bookkeeping in `state`; `probe_eval.run` assembles the report's full field dict
(the identity block plus what the hook returned) and raises when the method's
dict carries one of those names, so `write_report` computes nothing;
`done_pairs(dir, pairs)` added to 1.1's offered functions, built on `record_id`,
and named in `run.py`'s and `jobs/launch.py`'s import parentheses in 0.2, so
neither formats a record path and neither reads every row to answer a yes/no;
`jobs/launch.refire` probes the piece's session on its recorded host and refuses
while it is alive, fail-closed (2.3, 8.6, 9(c)#4); the probe service binds every
interface on the host the piece was placed on and its `base_url` carries that
host, with "local" dropped from the file's description in 0.2 (for an inject run
3.4 puts that piece on a GPU host while the loop pieces run on `login_host`);
1.1's "leaves the piece stopped" scoped to the case it was written for, with the
relaunch of 2.3 stated for the case where no session of the run is live;
`heartbeat` added to `eval/utils/probe_eval.py`'s and `eval/score_run.py`'s
`writes:` lines and `score`'s unit word added to 8.4;
`service_<kind>_<replica>.json` added to `jobs/launch.py`'s `reads:` line (7.4's
attach test and 2.3's teardown both read one); `stall_line`, `escalate_line` and
`warmup_s` added to 8.1's piece entry as optional keys, which is where 8.5's
per-piece override had to live; `agent/inject.py` added to 5.2's `agent_row`
reader list, matching 9(a)#46 and 9(c)#7; and 2.3's teardown restated over
`attached_to` as a `run_id` — the type 7.1 and 8.6 already use — instead of as a
file name, with 1.5's row saying so too.

### Applied with a correction

1. **The prediction row's `target`.** Two findings proposed two divisions: one
   had `predict` return `target` only for a method that derives it and
   `trainer.run` left-join the rest, the other had `predict` return `method`,
   `target` and its own outputs while `trainer.run` copies five columns. The
   second was applied. The first cannot be implemented without `trainer.py`
   knowing which methods copy `target` and which derive it, which is the branch
   on the method 2.6 forbids, and it contradicts its own "raise when a key
   arrives from both sides". The raise it asks for is unnecessary under the
   applied division, since the two sides share only `example_id`.
2. **`write_report` raising on `labels`.** As stated the fix is circular:
   `probe_eval.run` puts `labels` into the dict it passes, so a `write_report`
   that raised on `labels` would refuse every report. Applied where the merge
   happens: `probe_eval.run` raises, naming the key, when the **method's**
   returned dict carries `labels` or any other identity field. Same effect, and
   it is checkable at the only place both dicts exist. `theta_from` moved into
   that identity block for the same reason, since `probe_eval.run` holds
   `_upstream["theta_from.eval"]` and the method does not.

### Not applied

Nothing was refused. No finding required adding, splitting, moving or renaming a
file, so Part 9(b) gained no entry this round.

Three edits touched a tree line's *description* without touching the tree:
`data/__init__.py`'s line names `read_frame` and `write_frame`,
`models/probe_models/service.py`'s line drops "local" and says what the server
binds, and `models/__init__.py`'s line says `probe(alias)` returns the serving
block and the weights path rather than the `result:` block, which the frozen
setting now owns. None adds, removes, moves, splits or renames a file.

### 9(a) gained

#47 (`n_tasks` as a cap per split, with the debug walk as the reason and the
price stated — the Round 4 consequence the owner was asked to rule on), #48
(`final.judge` as canonical JSON text with a declared `final.success`).

## Consolidation — 2026-09-17, one editing pass over the whole document

The five rounds fixed findings where they were found, so the same fact ended up
stated in a column table and in a prose paragraph, in a stage-table row and in a
Part 9 walk, in a tree annotation and in the section that owns the mechanism.
This pass gave every named thing one source. No decision was changed and no tree
file was added, removed, moved, split or renamed.

The index built first is `.scratch/from-zero/contracts-index.md`: every function
signature, column, field, default, constant, marker file, directory-name shape,
axis value and module-level literal, with its owning section and every other
section that names it.

### What was collapsed

**83 edits.** 68 of them replaced a restated value or rule with a reference to
the section that owns it; 4 corrected a Part 0 annotation against Parts 1-8; 6
named or defined a constant that was used and undefined; 5 fixed a plain error.

The owners applied: the format's own section for a column (1.1-1.4), 1.5 for a
run-directory file, 1.7 for the probe-text rule, 2.1/2.2 for a stage's inputs and
key, 2.3 for pieces and the requested-pair rule, 2.5 for the gates, 2.6 for a
hook, 3.3 for the key formula, 3.4 for the directory and the freeze, 4.1/4.2 for
the environment, 5.2 for a setting field, 5.3 for an axis value, 5.5 for the
sweep child name, 6.1/6.2/6.3 for the model table, the modules and `constants/`,
7.1-7.4 for the protocols, 8.0-8.6 for the registry.

The values that had been stated more than once and now stand in one place:
`Environment.RESULT_CAP` (4.1), `build.probe_result_cap`, `build.max_abort_frac`,
`train.align_check`, `train.predict.splits`, `sample.split` and `inject.split`
and their `n_tasks` rule, the `probe.method` / `probe.tuning` / `inject.arm`
value lists, the family's own `STOP` (all 5.2 and 5.3), `PROBE_TEXT_FIELDS`'
three members (1.7), the `hosts:` columns (6.3), the `split_source: hash` formula
(5.2), the `debug.yaml` sizes (5.6), `meta.json`'s `owners` (8.3), `done.json`'s
`metrics` (1.5), the probe report's two field lists and its identity block (1.4),
the prediction row's per-kind output columns and its five copied columns (1.3),
the `<launch>` heartbeat index (8.4), the `ls` progress and `edited` maps
(8.0/8.4), the card-busy test (2.5), the refire and retry rules (2.3/2.4), the
`failed` finish row (8.2), the ssh transport and the fail-closed rule (3.4), the
lock nesting (8.6), the `any` venv resolution (6.3), and the endpoint file's
fields (1.5).

Prose that walked a table row by row was deleted where the table already said it
(2.6's closing restatement of the two report shapes, 8.6's restatements of
`refire`, `retry`, `free` and `sync`, 6.3's copy of the outputs-symlink
sentence). Prose that gives a reason or names the failure prevented was kept
everywhere, including where it repeats a rule in one sentence to make the reason
readable. Part 9(a) entries were left alone: a decision record repeats the fact
it decides on purpose.

### The disagreements settled, and the choice made

1. **What `settings.yaml` holds.** 1.5 called it "the fully resolved setting",
   3.4 "a stage projection, not the whole setting". **3.4 wins** — it is the
   Round 2 fix and 9(a)#32 records it; 1.5's row now states the `_` block and
   points at 3.4 for the projection.
2. **Which functions `jobs/launch.py` calls on `data/environments/__init__.py`.**
   Three spellings: `(tasks, …)` on its `imports:` line, `(tasks and
   requested_pairs, …)` on that file's `used by:` line, and "`tasks` only,
   through `requested_pairs`" in 4.2. **Both functions**: 2.3 counts `launch.py`
   among the five callers of `requested_pairs` (it refuses an out-of-split
   `tasks` id) and 8.3 gives `split_files` to `env.tasks`. All three lines now
   say that, and 2.3's five-file list says which function is for which job.
3. **`agent/loop.py` importing `models/__init__.py`.** The annotation carried the
   import; 0.4 and 7.2 route the family away from the loop — it renders through
   the probe service and compares the family the service echoes against
   `cfg.models.agent_row["family"]`. **Removed** from `loop.py`'s `imports:` and
   from `models/__init__.py`'s `used by:`, which is now six, with the reason on
   the line. This is the one edit in the pass the owner may want to check,
   because it rests on the absence of a caller rather than on a stated one.
4. **What `run.py` reads out of `constants/path_outputs.yaml`.** Its own line
   said "the login_host refusal and the outputs root"; that file's `read by:`
   line said "run.py (the login_host)". **The login_host only** — the root
   reaches `run.py` through `schema.run_dir` (3.1, 3.2 guarantee 2).
5. **What `run.py` writes.** Its `writes:` line omitted the start rows, although
   2.3 and 8.1 give it the start row of every CPU stage. **Added.**
6. **How many keys `constants/path_outputs.yaml` has.** 3.4 called `<root>` and
   `<debug_subdir>` "the two values in" it; 6.3 lists four keys. **Four** —
   3.4 now says "two of the keys".
7. **How many functions `data/probe_input.py` offers.** 1.7 said "Both are pure"
   and "the two functions" while pinning three (`cuts`, `cuts_live`,
   `assemble`); the tree line had already been corrected in Round 2. **Three.**
8. **Who writes `meta.json`.** 1.5's table said `jobs/registry.py`; 8.3 says only
   `run.py` and `jobs/launch.py` write it, through `registry.py`. **8.3** — 1.5's
   row now names the two callers.
9. **What `eval/score_run.py` calls on the environment.** 4.2 said `split_args`
   and `build_call` "only"; its `imports:` line and 2.3 also give it
   `requested_pairs`. **All three.**
10. **3.4's sweep example.** It addressed a child of `ctool_q06`, which sweeps
    nothing, while 5.5 and 9(c)#6 sweep `ctool_q17_lr`. **`ctool_q17_lr`**, and
    the spelling rule itself now lives only in 5.5.
11. **`tests/`'s cross-reference.** It cited 9(b)#16 for the four rules kept by
    hand; #16 is rendering `RESULTS.md` into `notes/` and the deferred tests are
    **#17**.

### The constants defined

- **`registry.DEFAULTS`** was described as "the constants in one dictionary" and
  its entries were named as per-piece overrides in 8.1, but only
  `launch_timeout_s` had a stated value; the other three lived inside prose
  formulas. 8.5 now holds the dictionary as a table: `stall_line` 180 s (the
  floor under `5 x typical gap`), `escalate_line` 3 (multiples of the stall line
  at which `escalated` turns true), `warmup_s` 1800 s, `launch_timeout_s` 1800 s.
  `stall_line_s`, `judge` and `judge_service` now name the entries instead of
  repeating 180, 3 and 1800.
- **The agent service's health wait.** 7.1's check table said `GET /health`
  "answers within the wait", and nothing in the document defined that wait. It
  is now `jobs/launch.py`'s alive check (8.1), which is the process that waits
  and the one that already reads `registry.DEFAULTS["launch_timeout_s"]`; the
  service still imports no registry (8.4).

### Part 0 checked against Parts 1-8

Every `imports` / `used by` / `reads` / `writes` / `venv` line was read against
the body. Four disagreed (numbers 2 to 5 above) and were fixed on the annotation,
never on the tree. Six tree-line *descriptions* were shortened where they
restated a rule the body owns — `jobs/launch.py` (the ssh transport),
`data/build_dataset.py` (the hash formula), `debug.yaml` (the sizes), both
`service.py` files (why they carry `VERSION`, and what the probe server binds),
and `agent/inject.py` (the `ARMS` tuple). None adds, removes, moves, splits or
renames a file. The annotated tree holds exactly 34 `.py` entries and 0.3's
arithmetic is unchanged: **1 + 1 + 8 + 8 + 4 + 4 + 6 + 2 = 34**.

### Line count

**4,943 before, 4,914 after** (-29). All 47 tables still have a consistent
column count.

## Round 6 — 2026-09-17, 27 findings (5 blocking, 9 major, 13 minor)

Three of the five blocking findings are the same defect seen three times — a
generating probe has no source for its `call_sep` — and are treated as one below.
Every blocking and major finding was applied; so was every minor one, because
each of the thirteen turned out to have a one-paragraph fix. Nothing needed a
file added, split, moved or renamed, so Part 9(b) gains no entry. Two findings
were applied by a different route than the one they proposed, and the reason is
on each.

### Applied — blocking

1. **A generating probe could not generate** (findings 1, 9 and 18, three
   readings of one hole). `Probe.generate(texts, max_new)` was defined as "the
   greedy continuation after `meta.json`'s `call_sep`", but on the training path
   there is no `meta.json`: `predict` and `validate` run with `ckpt_dir=None` and
   `best/` is chosen by the very metric that generates. Meanwhile 1.6 forbids
   `base.py` to read a key of `extra`. **Fixed on the call, not on the file**:
   6.2's row is now `generate(texts, max_new, call_sep)` and the caller supplies
   the separator — a generator's `predict` and `validate` hooks from their own
   module's `CHECKPOINT_META` (2.6's two rows say so), the probe service from the
   value it read out of the gen checkpoint's `best/meta.json` (7.2). 1.6 gained a
   paragraph stating that neither `call_sep` nor `param_only` is ever read back by
   `base.py`, and keeps its "merges `extra` unread" wording literally true.
   **Finding 9's own fix — putting both values on `base.load` — was refused**: it
   would make `train/utils/trainer.py` read a named key of each method's
   `CHECKPOINT_META`, including for `ctool`, which has no separator, and that is
   the per-method knowledge 2.6 keeps out of the shared file. The defect it
   names is closed by the route above.
   `param_only`'s half was closed the other way: it changes nothing about `/gen`,
   so 7.2 now says the service reads it at startup and **refuses to start** when
   it is true, naming the checkpoint — 5.7's load-time refusal taken again against
   the checkpoint that is actually on the card.
2. **A `p1` format's system text survived one step** (finding 2). 7.3 had
   `agent/loop.py` append it "once … before its first `render`", while 1.1 has
   the loop rebuild the conversation with `to_messages` every step, so the text
   was in step 0's prompt and gone from step 1 — different prompt bytes, no gate,
   no column. `to_messages` gained a sixth parameter, `extra_developer`, appended
   inside it (1.1), and 7.3 now says the loop passes `system_text(cfg)` on every
   call, None on a sample run and for a `p2` entry. 0.2's `loop.py` description
   follows.
3. **The registry lock was not re-entrant** (finding 8). 8.6 said `run.py` "holds
   it across the launch" and that `jobs/launch.py`'s nested hold is "what `fcntl`
   allows within one process" — but `fcntl` record locks do not stack, and the
   inner release or the close of the inner descriptor drops the process's lock
   outright, after which `run.py` would append its finish rows and re-render
   `RESULTS.md` unlocked. 8.0's writer half gained `lock()`, a re-entrant context
   manager (one module-level descriptor per process plus a depth counter, the
   `fcntl` acquisition at depth 0, released only when the outermost context
   exits); `append_start`, `append_finish` and `write_meta` call it
   unconditionally and the "unless the caller already holds the lock" clause
   became the counter's job. 8.6 now states the span 8.1 already fixed —
   `git_state`, the freeze, the gate, the attach test, the card reservation, the
   ports, the start-row append, released before any tmux session — and the
   sentence about what `fcntl` allows is gone.

### Applied — major

4. **The agent client had no source for `model`** (finding 3). `Client(base_url)`
   plus `stream(prompt_ids, generation, seed)` carried no model name, while
   `served_model_name` is a keyed `result:` column 6.2 forbids reading live. 7.1
   pins `Client(base_url: str, served_model_name: str)`; 7.4 says `agent/loop.py`
   passes `cfg.models.agent_row["served_model_name"]` from its frozen
   `settings.yaml`, so `agent/generate.py` still names no column.
5. **Nobody produced the live-session set** (finding 4). `release(dir,
   live_sessions)`, 8.5's verdicts and `refire`'s liveness refusal all consume it
   and 8.0's reader half offered nothing that returns it. Added
   `live_sessions() -> set[str]` and `session_alive(host, session) -> bool`, both
   fail-closed per 3.4, on `jobs/registry.py`, which already reads the host list
   and already probes tmux for `ls`; `ssh` and `tmux` were added to `run.py`'s
   `reads:` line in 0.2, which its annotation would otherwise have contradicted.
6. **`requested_pairs` threw away the split** (finding 10). The loop had to write
   `meta.split` and had only a pair list, so the cheapest guess —
   `cfg.sample.split[0]` — stamps every record `train` and ends with the eval
   fitting a temperature on an empty frame, which is 9(a)#44 and #47's failure one
   layer down. It now returns `(split, task_id, seed)` triples (4.1), 1.1 says the
   loop writes `meta.split` from the triple it is walking, and 2.3 states the
   projection to pairs once, so `done_pairs` and `read_dir` keep their signatures.
   0.2's `loop.py` reads line lost its one-split-era singular.
7. **A run that died early locked its own key for half an hour** (finding 11).
   Three edits: 8.2 gained a fifth finish-row writer — a stage `run.py` started in
   place and watched exit non-zero closes its own row with `failed`, stated in 2.3
   as well; 8.2's fourth writer is now stated as `judge`'s `dead` verdict instead
   of the three-part conjunction, since `stall_line_s` is `warmup_s` while a piece
   has too few beats; and 2.5's third gate clause now holds only while no piece of
   that row has been observed dead.
8. **The attach branch was unreachable** (finding 12). 3.4 gave an agent-service
   piece no card exemption, so 2.5's busy test counted the first run's vLLM cards
   busy and the launch was refused before `--attach-only` could be passed. Added
   the fourth placement case — a piece the attach test matched takes no card,
   enters no card search, and is placed on that server's host — and 8.1 now runs
   the attach test inside the lock hold **before** the card reservation.
9. **A reference was keyed twice, in two spellings** (finding 19). `eval` and
   `score` name whole sections in 2.1, so `eval.theta_from` and `score.baseline`
   entered `fields` as raw text while their resolved keys entered `upstream` —
   which makes 5.4's three reference syntaxes not interchangeable. 3.3's
   exclusion bullet now names all four reference fields, and the four rows in 5.2
   read "yes, through 3.3's upstream entry and never as a field of the diff".
10. **The probe service's `serve` line could not be built for a `sample` run**
    (finding 20). `--score-ckpt`, `--gen-ckpt` and `--temperature` were pinned as
    required, and a render-only piece has no source for any of them. They are
    bracketed now, with the same sentence `--device` already had.
11. **`weights` was resolved live and compared nowhere** (finding 21). 6.2 stated
    "every keyed column … never live from `models/table.yaml`" absolutely, while
    7.2 has the probe server resolve `family` and `weights` through
    `models/__init__.py`. `family` was echoed and compared; `weights` was not.
    `/health` now echoes `weights`, `agent/loop.py`'s refusal compares it, the
    `check` client compares it too, and 6.2's sentence names the one exception
    with the mechanism that stands in for the frozen read.

### Applied — minor

12. `STAGES`'s venv and piece-rule cells were prose that two files must decode
    identically; 2.1 now gives each a literal shape, and Part 2's opening says
    "strings, tuples and flat mappings" instead of "strings and tuples", which the
    venv mapping would otherwise have contradicted (finding 5).
13. 7.2 states that both checkpoint flags take the **train run directory** and the
    service opens `<dir>/best/` inside it (finding 6).
14. The three id functions' signatures are beside the id table in Part 1
    (finding 7).
15. `reference_loss(probe, df)` takes a slice of the example frame, and 2.6 pins
    which rows the gate compares and that both sides are normalised per example
    row (finding 12 of the list).
16. 9(d) lost "and the service refuses to start otherwise"; the `check` client of
    7.2 is the fixture's one owner and its non-zero exit is 8.1's `service_check`
    (finding 13).
17. 8.1 states the two waves after the lock is released — services, alive check,
    the `check` client for an inject run, then the loop pieces — and what a
    `service_check` outcome leaves in the start row (finding 14). **Applied with
    one qualifier the finding did not carry**: the `check` client runs for an
    `inject` run only, because 2.3's table gates only that stage on it and a
    `sample` run has no train keys for it to compare.
18. 3.4's merge paragraph is now per field: `tasks` null absorbs, `seeds` is the
    ordered union, `pieces` and `replicas` take the new launch's values
    (finding 15).
19. 8.4 names all four one-process stages as piece 0, and 3.4 says `--piece` is on
    a `sample` or `inject` loop piece only (finding 16).
20. 0.2's two eval-method import lines and `eval/score_run.py`'s now name
    `open_env`, the entrance, the way the train-side lines do, and `build_call` is
    back beside `split_args` (finding 22).
21. 4.2's "who calls what" gained `train/methods/{cgen,cparam}.py` (finding 23).
22. 2.1's "all four files' imports" is five, and names them (finding 24).
23. 5.2's `run.py --model <alias>` — a spelling defined nowhere — became the
    override syntax 5.7 owns, `models.agent=<alias>` (finding 25).
24. `debug.yaml`'s `inject:` block gained `max_steps: 6`, and "a default that
    means 'no cap'" became "exists in the schema, so the debug overlay adds no
    special case" (finding 26).
25. 1.4 leads with the per-method split of `tool_ok` instead of stating the
    `cparam` rule generally and correcting it a sentence later (finding 27).

### Refused

- **Finding 9's mechanism** (`call_sep` and `param_only` as `base.load`
  parameters). Refused: it moves a named per-method key into
  `train/utils/trainer.py`, which 2.6 forbids, and a classifier has no separator
  to pass. The hole it names is closed on the `Probe.generate` call instead
  (blocking 1 above), which is the same fix findings 1 and 18 asked for.
- **Finding 1's alternative for `param_only`** ("drop it from 7.2's `/gen` row and
  leave it to 5.7"). Refused: 5.7 refuses a *setting*, while the service holds the
  checkpoint the cards are already loaded with, and a pinned `key:` reference
  skips checks (5.4). It is kept as a startup refusal, which costs one sentence.

Nothing else was refused, and no finding contradicted an owner decision. The
per-stage keys, the hash-last rule, eval reading disk only, the retired sampler,
one record file per (task, seed), Polars/jsonl/parquet, PyYAML plus dataclasses,
never-keyed `constants/`, the expanded `table.yaml` rows and per-method packing
are all untouched.

### Consequences the owner may want to look at

Three of these fixes change a signature the fourth draft did not pin, and they
are the ones worth a second reading: `requested_pairs` returning triples (every
caller projects), `to_messages` taking a sixth parameter, and
`Probe.generate` taking the separator on the call. Each replaces a mechanism
that had no source for a value it was defined in terms of.

### Line count

**4,914 before, 5,160 after** (+246). Every table's column count is consistent
(checked by parsing, with backtick-quoted and escaped pipes excluded); the tree
still holds exactly 34 `.py` entries and 0.3's arithmetic is unchanged.

## Round 7 — 2026-09-17, 29 findings (5 blocking, 9 major, 15 minor)

One defect arrived twice, as two blocking findings with incompatible fixes (the
`/gen` route's missing `max_new`), so 28 distinct defects were considered. Everything was
applied except one of that pair's two mechanisms; nothing needed a file added,
split, moved or renamed, so Part 9(b) gains no entry.

### Applied — blocking

1. **The claim primitive and the `meta` row could not both be written as
   specified.** `open_record(dir, task_id, seed, meta)` took the whole `meta`
   dict at the `O_EXCL` create, while `meta.task_text` is captured after
   `Environment.open` — so the loop had to open the world before it claimed, and
   a lost race meant two pieces holding one AppWorld world for one (task, seed),
   with the loser's `close()` deleting the per-task outputs. 1.1 now splits the
   two steps: `open_record(dir, task_id, seed)` creates an empty file and returns
   the `Writer`, and `agent/loop.py` writes the first row with
   `writer.row("meta", ...)` once it has the task text. The unowned-file margin is
   restated as "as soon as `Environment.open` returns", which is inside the
   `launch_timeout_s` the launcher already allows a piece.
2. **`POST /gen` had no source for `max_new`.** `Probe.generate` is pinned with
   three arguments and the service reads no `settings.yaml`, carries no such
   flag, and gets nothing of that shape from `best/meta.json`. Added
   `inject.max_new` (int, 96, keyed) to 5.2, listed it in 2.1's inject field list
   so it enters the key, extended the `/gen` request body to
   `{"text", "max_new"}`, made the client half `generate(text, max_new)`, and had
   `agent/inject.py` send `cfg.inject.max_new` on each fire (7.3 step 4). The
   server stays free of `settings.yaml`.
3. **Walk 1 died at `build` on any real AppWorld dataset.** 2.5 made the
   call-string round trip a hard gate while 1.2 pinned `example.call` to today's
   `make_call`, which joins values unquoted
   (`legacy/pipeline/annotate/build.py:197-200`) against a parser that splits on
   top-level commas (`rules.py:118-147`) — `check_callstr.py:20-27,48-51` says so
   itself and calls it a measure-only deviation. 4.2's `build_call` row now
   states that inverse means round-trippable and that AppWorld quotes a value
   with `repr()` when it holds a top-level `,`, `=`, quote or bracket; 1.2 dropped
   the `make_call` clause (the change is covered by the environment file's
   `VERSION`); and 2.5 keeps the gate but says it is a **new** hard stop, naming
   which of today's checks actually hard-stop (`check_callstr.py:263,273,288,299`).
4. **`release`'s signature made `data/task_record.py` unwritable.** 1.1 read the
   margin out of `registry.DEFAULTS`, which that file does not import and whose
   eight importers are fixed. It is now
   `release(dir, live_sessions, unowned_age_s)`, with `run.py` and
   `jobs/launch.py` passing the constant in exactly as they pass
   `registry.live_sessions()`; 8.0's row and 8.5's fifth rule follow.
5. **`/gen`'s missing budget, second report** — the same defect as 2 above,
   fixed there. The alternative mechanism is refused below.

### Applied — major

6. **The classification position was pinned nowhere** and two files must agree on
   it. 6.2 now states that the head reads the hidden state at the **last non-pad
   token of each event**, adds `event_end: LongTensor` to the keys
   `Probe.forward` consumes, defines `Probe.score(texts)` as one event per text at
   its last token, and 2.6's `batches` row names the key. Without it `base.py`
   chooses a position when it serves and each method file chooses one when it
   packs, and a disagreement is a probe scored where it was never trained, under a
   correct key.
7. **Neither entrance's return shape was named, and `weights` meant two things.**
   6.2 now declares `AgentModel` and `ProbeModel` in `models/__init__.py` —
   `module` (agent only, so nothing is attached to a shared module object),
   `alias`, `role`, `family`, `weights` (always the alias), `weights_path`
   (always the directory) and `serving` — and states the naming rule across
   `table.yaml`, the frozen rows and both return types. That also gives the
   probe service's `/health` echo a source for the weights **alias** it must
   carry. 0.2's `models/__init__.py` description follows.
8. **`--debug` on `train_probe.yaml` could not reach `train`.** 2.5 refused a
   build in which a tool appears in val or test and never in train, which with
   three tasks per split is near-certain and is a documented condition at full
   size too (`build.py:404` counts the vocabulary over the whole pile;
   `check_callstr.py:58-61` lists such tools as a deviation, not a block). The row
   is demoted to a `report.md` line plus a `done.json` count; `head_labels` is now
   computed over the **whole** example frame (2.6, 1.3, 6.2); and 1.3's sentence
   propped up by the old gate is deleted, as is 2.6's use of it in the `labels`
   failure note.
9. **The relaunch path for `sample` and `inject` could never fire.** Service
   pieces are pieces of the run and never exit on their own, so "no session of the
   run is live" is false for the whole life of an unfinished run. 1.1 and 2.3 now
   read "no piece of `kind` `loop` or `train` has a live session" and say the
   relaunch reuses the live service pieces; 2.5's launch-gate live-session clause
   skips `kind: service`. The card reservation is untouched, so a finished run's
   server still holds its cards until the teardown.
10. **`build.max_examples` had no scope.** It is now a cap **per split** (5.2),
    applied after the split column is assigned and keeping the first rows of each
    split in `example_id` order (2.5), with the per-split wording added to
    9(c)#8 beside `n_tasks: 3`. Over the concatenation it reproduced the empty
    `val` and `test` that 9(a)#44 and #47 exist to prevent.
11. **A failed launch leaked cards.** `teardown_services` was bound to the one
    moment `run.py` writes `done.json`, which an `alive_check` or `service_check`
    failure never reaches. `jobs/launch.launch` now calls it before returning any
    outcome but `up` (8.1), and 2.3's teardown paragraph names both callers; the
    `attached_to` skip rule still spares another run's server.
12. **`git_state` had two callers and therefore two probes per launch.** 2.5 now
    makes `run.py` the single caller for all six stages, inside the lock and
    before `schema.freeze`, handing the dict down; 0.2's signature becomes
    `launch(stage, setting, run_dir, resolved, git)`. 3.4, 8.6 and 9(c)#1 needed
    no change.
13. **A second live read of a keyed column had no check.** `family` is keyed, and
    `agent/generate.py` and `agent/inject.py` resolve it live through
    `models.agent(...)`. 6.2 now names that second exception and closes it: both
    compare `module.NAME` against `cfg.models.agent_row["family"]` before their
    first use — one line each, no new import, the same comparison `/health`
    carries.
14. **`example.args` named a reader that cannot reach it.** `eval/` sees only the
    prediction frame (1.3, 2.6), so 1.2's row now names one reader, the build gate
    of 2.5, and says the column is never read by `eval/`.

### Applied — minor

15. `freeze(setting, stage, run_dir, resolved, commit)` takes the stage, since
    every section it writes is stage-dependent (5.1, 3.4, 2.3); `run.py` passes
    the stage it is walking.
16. `cfg._workflow: list[str]` is the parsed `workflow:` line's home on the
    Setting, written into no `settings.yaml`; 8.1's `workflow` field says it is
    the workflow **file's** name (5.1).
17. A section the merged setting does not hold is `None` on the Setting and
    omitted from `settings.yaml`, so the presence tests of 0.2 and 7.3 are
    `cfg.inject is None` (5.1).
18. 1.5 states what `run.py` puts in `done.json` for `sample` and `inject` —
    `counts`, `metrics: {}`, `report: null`, `versions` — the four fields
    `write_done` requires for the two stages whose writer is not the stage.
19. 2.5 states what `build` does with a step whose `env.action` is null (no
    example rows, counted as skipped) and that a non-null action `split_args`
    cannot parse stops the build.
20. 2.5 names the source of `score`'s same-setup comparison: the two upstream
    runs' own `settings.yaml`, through `run_dir_of` on `_upstream["inject"]` (or
    `["sample"]`) and `_upstream["baseline.sample"]`.
21. `eval/score_run.py`'s `reads:` line in 0.2 now carries both reads its own
    section already gives it: the environment's split task-id files through
    `requested_pairs` (which every other caller's line names) and those two
    `settings.yaml`.
22. 8.3's `owners` is "run into **or reused**", and 2.3 says the walk adds this
    setting on a skip, through `registry.write_meta` under the lock it holds —
    otherwise the flagship sharing cases record one owner.
23. 3.4's closing sentence is scoped to `jobs/launch.launch`, with
    `jobs/launch.refire` named as the exception that restarts one piece beside
    live siblings.
24. 2.3's refire list gained the two steps 1.5, 3.4 and 8.3 already assumed:
    `run.py refire` takes `git_state` and re-freezes `_commit` inside the lock,
    then hands the git dict to `refire(run_dir, git, piece)`.
25. 1.7's `min_think` bullet states the live form of the event gate —
    `agent/inject.py` scores no cut until the thinking so far reaches
    `min_think` — and 7.3 step 4 and 0.2's `probe_input.py` line carry it.
26. 7.2's render-only paragraph asks for the same three echo fields the loop's
    refusal does (`render`, `family`, `weights`), not two.
27. `orphan` had two opposite definitions; 2.3's mechanism wins and 8.6's cell
    now covers both survivors (the attached-to skip, and a teardown that failed).
28. The per-piece `DEFAULTS` override was unreachable — no setting field, no flag
    produced one — so the three optional keys leave 8.1's piece entry,
    `stall_line_s(beat_ts)` loses its parameter, and 8.5 says the numbers change
    only by an edit to the dictionary.
29. Three cross-references renumbered or dropped: `9(a)#14` -> `#15` in the facts
    section, `9(b)#13` -> `#15` in 9(a)#26, and 2.3's `(9(c)#6)` dropped, since no
    walked scenario is an eval rerun loop.

### Refused

- **The second `/gen` finding's mechanism** (carry `max_new` in the generating
  method's `CHECKPOINT_META`, into `best/meta.json`, read by the service at
  startup). Refused, while the defect it names is fixed by the other finding
  (blocking 2 above). Reason: `CHECKPOINT_META` is for values that are the
  *method's* (1.6, 2.6), and a generation budget is not one — 5.2 already carries
  `train.predict.max_new` as an ordinary setting field, so a per-method copy would
  be a second definition of one number, with a checkpoint's value able to
  contradict the setting's. Carrying it on the request keeps the budget where
  every other result-changing value lives, inside `experimental_settings/`, in the
  inject key and in the run's own `settings.yaml`, and still leaves the server
  reading no `settings.yaml`. `call_sep` stays in `CHECKPOINT_META`, because it
  really is the method's.

Nothing else was refused, no finding contradicted an owner decision, and none
misread the document. Interfaces first, per-stage keys, hash last, eval reading
disk only, cgen/cparam predicting at every cut, the retired sampler, one record
file per (task, seed), Polars/jsonl/parquet, PyYAML plus dataclasses, never-keyed
`constants/`, expanded `table.yaml` rows and per-method packing are all untouched.

### Consequences the owner may want to look at

- `inject.max_new` is a new keyed field, so every inject key moves once when it is
  added. It is the live counterpart of `train.predict.max_new` and cannot be
  inherited from the train side, because an inject setting states no `train`
  section.
- `head_labels` over the whole example frame changes which classes a head has for
  any dataset with a val- or test-only tool; the trade is that `--debug` reaches
  the last stage of `train_probe.yaml`, which the demoted gate blocked.
- `build_call` is no longer today's `make_call`: AppWorld's example rows will hold
  quoted argument values wherever a value carries a comma, an `=`, a quote or a
  bracket, so new `call` strings are not byte-comparable with the old pipeline's.

### Line count

**5,160 before, 5,373 after** (+213). Every table's column count is consistent
(checked by parsing, with backtick-quoted and escaped pipes excluded), and no
tree entry was added, split, moved or renamed.
