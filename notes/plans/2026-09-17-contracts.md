# new1 from zero: the contracts

Written 2026-09-17, before any code, against the fourth draft's Part 1 tree
(`notes/plans/2026-09-14-structure-from-zero.md`), the four Fable reviews and
their synthesis (`notes/plans/2026-09-17-structure-review-synthesis.md`), the
third draft's deleted Part 2 (`git show 771a6e5:plans/2026-09-14-structure-from-zero.md`),
`notes/CONTEXT.md`, and the old code under `legacy/`.

This document pins the interfaces between the files of that tree: the four
on-disk formats, the stage table, `run_dir`, the environment base class, the
setting schema, the model table, the two service protocols, and the registry.
It is not a design for shared code. Code becomes shared on its third
repetition; an interface is fixed on day one.

Three rules govern the whole document.

1. **The tree is fixed.** No file is added, removed, moved, split or renamed.
   A mechanism with no obvious file goes into the existing file whose tree line
   best covers it, and the choice is stated where it is made. A reviewer's fix
   that would need a structural change is not applied; it is listed in Part 9(b).
2. **Interfaces, not shared code.** What is pinned is what crosses a file
   boundary: a function signature, a column, a request body, a directory name.
3. **Every claim about today's behaviour is grounded.** Where this document says
   what the old code does, the file and line are named. Where it says what a
   library does, it was run or read in the venv on this machine on 2026-09-17.

Terms follow `notes/CONTEXT.md`: probe, cut, fire, inject, launch, heartbeat,
piece, refire, verdict. Two words are used in one meaning only:
**record** always means the task record on disk, never a line of the registry
(a line of `jobs/runs.jsonl` is a **registry row**, lifecycle C2); and
**environment** always means a benchmark, never a venv (a venv is named by its
directory under `external/`).

## Facts measured on this machine, 2026-09-17

| venv | python | polars | pyyaml | numpy | torch | transformers | openai_harmony | pydantic |
|---|---|---|---|---|---|---|---|---|
| `external/appworld/venv` | 3.12.13 | 1.44.2 | 6.0.3 | **absent** | absent | absent | absent | 1.10.26 |
| `external/probe-env` | 3.11.15 | 1.44.2 | 6.0.3 | 2.4.6 | 2.11.0+cu128 | 5.14.1 | 0.0.8 | 2.13.4 |
| `external/vllm-env` | 3.12.13 | 1.44.2 | 6.0.3 | 2.3.5 | 2.11.0+cu130 | 5.14.1 | 0.0.8 | 2.13.4 |

This settles grounding F3, which found Polars installed nowhere: Polars 1.44.2
and PyYAML 6.0.3 are now in all three venvs. vLLM is 0.26.0 in
`external/vllm-env`. Two further facts were read out of that vLLM install and
decide two contradictions between the drafts:

- `TokenizeCompletionRequest` exposes `model`, `prompt`, `add_special_tokens`
  and `return_token_strs`, and **nothing else**
  (`vllm/entrypoints/serve/tokenize/protocol.py:24-47`). There is no
  `split_special_tokens`, which is the flag
  `legacy/pipeline/inject/probe_server.py:88-95` sets on every encode.
- `create_tokenize` on a chat request calls `online_renderer.preprocess_chat`
  (`vllm/entrypoints/serve/tokenize/serving.py:84`), which for a gpt-oss model
  is the **jinja** path, not `_make_request_with_harmony`
  (`vllm/renderers/online_renderer.py:154-180`, which only the chat-completions
  path reaches). So `POST /tokenize {messages}` does **not** reproduce the chat
  endpoint's prompt ids for gpt-oss.
- The server's harmony date comes from `VLLM_SYSTEM_START_DATE` and otherwise
  from the machine clock
  (`vllm/entrypoints/openai/parser/harmony_utils.py:133-139`). It is therefore
  a launch-time environment variable, and this document keys it (Part 6.1).

One more fact was measured, because Part 1.1's claim primitive rests on it.
The outputs mount `/net/tokyo100-10g/data/str01_01` is **NFSv4.0**
(`findmnt -t nfs4`), and exclusive create is atomic across clients on it:
three hosts (shiga/tokyo105, tokyo106, tokyo107) running 8 processes each,
released at a common wall-clock barrier, raced for 150 files and produced
**exactly one winner per file, 150 times out of 150** (two of the three hosts
won files, 83 and 67). Home (`/home/y-guo`) is NFSv3 and holds no records.
That settles the swap from today's `mkdir` ticket
(`legacy/pipeline/inject/live_appworld.py:590-603`) to `O_EXCL` in Part 1.1:
the primitive the old docstring chose for NFS atomicity is not the only one
that has it on this mount.

**One precondition on the venvs.** `venv: any` in this document means *standard
library, PyYAML, Polars and NumPy*. Polars and PyYAML already satisfy that;
NumPy does not, because it is absent from `external/appworld/venv`. NumPy is a
dependency-free wheel, like Polars, and the first step of the construction plan
installs it there (`uv pip install --python external/appworld/venv/bin/python
numpy`). That keeps the tree's own line for `eval/` — "no GPU, no torch, every
file imports as any" — literally true while the temperature fit stays an
ordinary 1-D minimiser. Part 9(a)#15 records the alternative.

---

# Part 0. The tree, annotated

## 0.1 How to read an entry

Every code file carries five annotations. They are the contract, and the same
five lines are copied onto that file's line in `README.md`, in this order and
this punctuation, so that `run.py selfcheck` can parse them:

```
path/to/file.py — one sentence of what it does.
  imports: a.py, b.py          repo files this file imports (third-party in brackets)
  used by: c.py, d.py          repo files that import this file
  reads:   <format or file>    what it reads off disk
  writes:  <format or file>    what it writes to disk
  venv:    any | appworld | probe | vllm
```

`venv: any` means the file imports under **every interpreter in the `venvs:` map
of `constants/path_datasets.yaml`** (6.3) using only the standard library,
PyYAML, Polars and NumPy. The map is the list, not the number three: a new
benchmark adds a fourth entry (0.4), and the `any` guarantee and the selfcheck
that enforces it cover it the day it is added. A file whose *runtime* needs a
heavier venv than its *import* does is written `any at import, <venv> to run`
and keeps the heavy import inside the function that needs it. A file that is
started as a program and imported by nobody says `used by: none (program)`.
A dynamic import is written `used by: <file> (by name)`.

`run.py selfcheck` proves these lines against the code with `ast`, never by
importing: it parses every file's import statements, builds the real graph, and
fails when a README line disagrees. That is the mechanism the owner asked for —
three or four files per change is tolerable *because* the line says which three
or four, and the line cannot rot.

## 0.2 The tree

Reproduced entry for entry from the fourth draft's Part 1. The descriptions are
the owner's, shortened where they repeat; the annotations are this document's.

```
new1/
  README.md               for the future reader: this tree, one line per file, how to run, the extension
                          recipes. Edited whenever the tree changes; selfcheck fails on a Python file
                          missing from it, on an annotation line that disagrees with the code, and on an
                          axis value with no file behind it
  CLAUDE.md               the rules an agent reads on its own; the only other file at the root that is not code

  run.py                  the one command: run one or several named settings of one workflow file; ls, where,
                          find, free, kill, refire, retry, sync, table, selfcheck. Edited when a subcommand is
                          added or the stage walk changes
      imports: experimental_settings/schema.py, jobs/launch.py, jobs/registry.py,
               data/trajectory_record.py (done_pairs, is_done, owner, release),
               data/environments/__init__.py (open_env, requested_pairs: the requested
               (split, task_id, seed) list, which run.py computes on the setting it holds and
               projects to pairs, 2.3),
               eval/utils/probe_eval.py (read_report, to
               freeze a referenced temperature), eval/method_table.py (the table subcommand, 8.6)
      used by: none (program)
      reads:   experimental_settings/*.yaml (through schema), every run directory's settings.yaml /
               meta.json / done.json / consumed.json and the upstream files it names (the skip gate of
               2.3) / heartbeat/*.jsonl / service_<kind>_<replica>.json (for attached_to, 7.1),
               the sample or inject run's task records (through
               data/trajectory_record.py, for the completeness check, the progress count of 8.4 and the claim
               release), the environment's split task-id files (through
               data/environments/requested_pairs, for the subset skip test and done.json's pairs, 2.3),
               the probe report of
               a referenced classifier eval run (through eval/utils/probe_eval.read_report, 1.4),
               jobs/runs.jsonl, constants/path_outputs.yaml (the login_host refusal of 8.6; the
               outputs root reaches it through schema.run_dir, 3.1),
               constants/path_datasets.yaml (the venvs map, for selfcheck's
               per-interpreter import test), ssh and tmux (through
               jobs/registry.py's live_sessions, which is what the claim release of
               1.1 takes as its live-session set, 8.0)
      writes:  settings.yaml and settings_diff.yaml into a run directory (through schema.freeze),
               done.json for the piece stages, meta.json, the start rows of the three CPU stages it
               starts in place (2.3), finish rows and RESULTS.md (through jobs/registry.py)
      venv:    probe (the interpreter this repo's commands are typed with)
```

```
  constants/              where things are on this cluster: datasets, outputs, weights. Read by code;
                          nothing here changes a result or enters a key. Edited when something arrives or
                          moves on disk; a path may change only for the same bytes at a new place, and a
                          new set of weights is a new alias in models/table.yaml
    path_datasets.yaml      per environment: the clone's home, the interpreter that runs its loop, its data
                            root, and split name -> task-id file; plus the top-level venvs: map, which is
                            where every interpreter path in this repo is written down (Part 6.3)
      read by: data/environments/__init__.py (the splits block, to resolve a split name),
               data/environments/appworld.py (home, data root, split files),
               experimental_settings/schema.py (the splits block, to validate a split value at load),
               jobs/launch.py (the venv column and the venvs map), run.py (the venvs map, for selfcheck's
               per-interpreter import test)
    path_outputs.yaml       the outputs root on NFS, the debug subdirectory under it, the login_host and the
                            hosts: list, the cluster inventory (Part 6.3 holds the keys and their shape)
      read by: experimental_settings/schema.py (run_dir), jobs/registry.py (ls walks the root, and the
               hosts list for tmux and card probes), jobs/launch.py (the login_host and the hosts list),
               run.py (the login_host)
    path_models.yaml        weights alias -> the directory the weights live in
      read by: models/__init__.py, models/agent_models/service.py (the weights path of the row it serves)
```

```
  experimental_settings/  everything in here changes a result. The YAML files are gyb's: a new kind of
                          experiment is a new file, a new experiment is a new named setting in a file, a
                          tuning is an edited value. Agents read them and never edit them (a hook refuses).
                          schema.py is code and is edited for a new hyperparameter (with a default that
                          reproduces the old behavior) or a new value on an axis
    schema.py               the schema of a setting: every field with its default and a one-line comment, the
                            allowed values of each axis, the stage table; and the loader that reads a YAML
                            file against it (file -> setting, diff, key), plus run_dir and freeze
      imports: none (repo); [PyYAML, dataclasses, hashlib, re, ast]
      used by: run.py, jobs/launch.py, agent/loop.py, data/build_training_dataset.py, train/utils/trainer.py,
               eval/utils/probe_eval.py, eval/score_run.py, eval/method_table.py,
               models/agent_models/service.py, models/probe_models/service.py (ten; both services take
               load_frozen only, the agent one in its server main and the probe one in its check client)
      reads:   experimental_settings/*.yaml, models/table.yaml, constants/path_outputs.yaml,
               constants/path_datasets.yaml (the splits block of the chosen environment, to validate a
               split value), a run directory's settings.yaml, the VERSION line of every module the stage
               table names, the PROBE_KIND line of a method file, and the module-level literals of
               3.3's literal rule (a family module's STOP / EFFORTS / DEFAULT_EFFORT / DEFAULT_DATE, a
               backbone module's LORA_TARGETS, a train method file's CHECKPOINT_META, and an environment
               file's INSTRUCTIONS keys and SPLIT_ROLE keys) — all read as source text, never imported
      writes:  settings.yaml and settings_diff.yaml in a run directory
      venv:    any
    debug.yaml              only sizes, and Part 5.6 holds them; never a model and never a tuning;
                            --debug lays it over any setting
    baseline.yaml           workflow sample, score; named settings inside
    train_probe.yaml        workflow sample, build, train, eval; named settings inside
    inject.yaml             workflow inject, score; named settings inside
      read by: experimental_settings/schema.py only
```

```
  data/                   the benchmark environments, and every format that lives on disk between two
                          stages: the record (agent -> build), the example (build -> train), the prediction
                          (train -> eval). One format per interface, defined here and nowhere else.
                          Nothing else is added here; a new environment goes under environments/
    __init__.py             the conventions the three formats share: read_frame and write_frame (Part 1),
                            so every read returns a Polars DataFrame with the format's declared columns
                            and types; the id rule; the
                            VERSION / DEFAULTS / REQUIRED rule, including the raise on a missing
                            required column. Edited never
      imports: none (repo); [polars]
      used by: data/trajectory_record.py, data/training_data.py, data/probe_output.py, data/build_training_dataset.py (the id
               functions, which the builder calls rather than formatting a string)
      reads:   -   writes: -   venv: any
    environments/           one file per benchmark environment; the only place a new environment adds a file
      __init__.py           the contract and the entrance: class Environment declares the nine methods
                            (tasks, open, step, speculate, judge, close, split_args, build_call,
                            complete_call) with one line each and no logic, and the StepObservation
                            dataclass that step returns (4.2); open_env(name) imports
                            environments/<name>.py inside the function, checks the methods are there, and
                            returns the instance; requested_pairs(env, splits, tasks, n_tasks, seeds) is the
                            one definition of what a run asks for, as (split, task_id, seed) triples
                            (2.3); carries VERSION
        imports: none (repo); [importlib, PyYAML]
        used by: data/environments/appworld.py (subclass), agent/loop.py (open_env, StepObservation,
                 requested_pairs), agent/inject.py, data/build_training_dataset.py (open_env, requested_pairs),
                 train/methods/cgen.py, train/methods/cparam.py (open_env, for the environment their
                 validation metric's match takes, 2.6), eval/methods/cgen.py, eval/methods/cparam.py,
                 eval/score_run.py,
                 jobs/launch.py (tasks and requested_pairs, to resolve the split files before the pieces
                 start), run.py (open_env and requested_pairs, for the subset skip test and done.json's
                 pairs, 2.3)
        reads:   constants/path_datasets.yaml   writes: -   venv: any
      appworld.py           class AppWorld(Environment): the nine methods on the AppWorld package, its task
                            instruction variants, its no-code message, its call regex and Python call
                            syntax; carries VERSION
        imports: data/environments/__init__.py; [the appworld package, inside open()/step()/speculate()]
        used by: data/environments/__init__.py (by name)
        reads:   constants/path_datasets.yaml, the split task-id files
        writes:  the AppWorld per-task output directory, deleted by close()
        venv:    any at import and for the call-syntax methods; appworld to hold a world
    trajectory_record.py          the record one task run leaves: six row kinds, one file per (task, seed); write,
                            read, is_done, owner, to_messages; carries VERSION
      imports: data/__init__.py
      used by: agent/loop.py (meta, gen, env, final), agent/inject.py (spec, resume),
               data/build_training_dataset.py, eval/score_run.py,
               jobs/launch.py (done_pairs, is_done, owner, release),
               run.py (done_pairs, is_done, owner, release: the completeness check, the progress count
               of 8.4 and the claim release, all of which happen on the login machine, 1.1)
      reads/writes: task record (jsonl)
      venv:    any
    training_data.py              the row build writes per cut: the record and cut it came from, the text the probe
                            sees, and all three targets; write, read; carries VERSION
      imports: data/__init__.py
      used by: data/build_training_dataset.py (write), train/utils/trainer.py (read),
               train/methods/{ctool,cgen,cparam}.py (their target column)
      reads/writes: example (parquet)
      venv:    any
    probe_output.py           the row train writes per example after training: the example id, its target, the
                            true tool, the score and class logits (ctool) or the generated text (cgen,
                            cparam); write, read; carries VERSION
      imports: data/__init__.py
      used by: train/utils/trainer.py (write), eval/utils/probe_eval.py (read)
      reads/writes: prediction (parquet)
      venv:    any
    probe_input.py          what the probe is asked and shown: the cut positions in the reasoning (the
                            offline enumeration and the streaming one, which differ in their offset
                            convention and are therefore not comparable, Part 1.7; the event-level
                            min_think gate lives in data/build_training_dataset.py offline and in agent/inject.py
                            live, which scores no cut until the thinking reaches min_think, 1.7), and the text assembled
                            for the probe (the task, the clipped tool history, the thinking so far); pure
                            functions whose every parameter is passed in, never a module constant and never
                            read from a file, so the offline and the live caller cannot drift; carries
                            VERSION
      imports: none (repo); [re]
      used by: data/build_training_dataset.py, agent/inject.py
      reads:   -   writes: -   venv: any
    build_training_dataset.py        the program: records -> example rows for the three probe methods; the
                            train/val/test split, by either rule of build.split_source (5.2 for the
                            hash share, 2.5 for the env mapping); the report; the gates; carries VERSION
      imports: experimental_settings/schema.py, data/__init__.py (the id functions), data/trajectory_record.py,
               data/training_data.py, data/probe_input.py, data/environments/__init__.py, jobs/registry.py
      used by: none (program)
      reads:   the sample run's task records, the environment's split task-id files
      writes:  examples.parquet, consumed.json, report.md, heartbeat, done.json
      venv:    any
```

```
  models/                 the models: the table, the agent-model side, the probe-model side. A model's own
                          settings (format, serving, tokenizer quirks) live here; a run's settings live in
                          experimental_settings/
    __init__.py             the entrance: agent(alias) reads table.yaml and imports the family module inside
                            the function, returning it as AgentModel.module beside the row's alias, role,
                            family, weights (the alias) and weights_path (from constants/path_models.yaml)
                            and its serving block; probe(alias) returns the same shape as ProbeModel, minus
                            the module, without importing the backbone module —
                            models/probe_models/base.py imports that, by name, inside load(). The two return
                            types are in Part 6.2. Edited never; a new model is a row, a new family or
                            backbone a file
      imports: none (repo); [importlib, PyYAML]
      used by: agent/generate.py, agent/inject.py, models/agent_models/service.py,
               models/probe_models/base.py, models/probe_models/service.py, train/utils/trainer.py
               (six; agent/loop.py is not among them, 7.2)
      reads:   models/table.yaml, constants/path_models.yaml
      writes:  -   venv: any
    table.yaml              one row per alias, in two blocks: result (expanded into the setting before
                            keying) and serving (never keyed). Edited when a new model alias is wanted; a
                            model of an existing family or backbone needs only this row
      read by: models/__init__.py, experimental_settings/schema.py (the result block),
               models/agent_models/service.py (the serving block),
               jobs/launch.py (the serving block: host and port)
    agent_models/           one file per family (a family shares one conversation format), plus its service
      __init__.py           empty, so the client half of service.py imports without the family's libraries
        imports: none
        used by: models/agent_models/service.py, models/agent_models/gptoss.py (as their package)
        reads:   -   writes: -   venv: any
      gptoss.py             gpt-oss's format ("harmony"): messages -> token ids, parse a streamed reply, end
                            of turn, the model's own system message (date, effort), the control-token
                            wrapping of a prefetch message, and the family's own generation defaults; the
                            module interface is Part 6.2; carries VERSION
        imports: none (repo); [openai_harmony, inside render_ids()]
        used by: models/__init__.py (by name). Every other file reaches this module as the object
                 models/__init__.py's agent(alias) returns, and names no family file
        reads:   -   writes: -
        venv:    any at import and for parse/end_of_turn/wrap_prefetch; probe or vllm for render_ids()
      service.py            both ends of the served agent model: start or attach to the vLLM server for a
                            table row and check it (main, vllm venv); the loop's client, a raw token stream
                            with a seed (standard library); carries VERSION, which is folded into the
                            sample and inject keys for the reason 2.2 gives
        imports: models/__init__.py (the family through agent(alias), inside the server main),
                 experimental_settings/schema.py (load_frozen)
        used by: agent/generate.py (client), agent/loop.py (health); jobs/launch.py starts it as a
                 piece, which is a tmux command and not an import
        reads:   models/table.yaml (the serving block only, 7.1), constants/path_models.yaml, the run
                 directory's settings.yaml (models.agent_row — every keyed column — plus
                 generation.date and generation.effort)
        writes:  service_agent_<replica>.json and its piece log in the run directory (7.4)
        venv:    any at import; vllm to serve
    probe_models/           the probe model: the shared class, one file per backbone, plus its service
      __init__.py           empty, so the client half of service.py imports without torch
        imports: none
        used by: models/probe_models/base.py, models/probe_models/service.py,
                 models/probe_models/qwen.py (as their package)
        reads:   -   writes: -   venv: any
      base.py               the probe class every backbone shares: load, save, score a prefix, generate a
                            call; owns the classification head and the checkpoint layout; carries VERSION
        imports: models/__init__.py; models/probe_models/<backbone>.py (by name, inside load());
                 [torch, transformers, peft]
        used by: train/utils/trainer.py, train/methods/{ctool,cgen,cparam}.py,
                 models/probe_models/service.py (inside serve())
        reads/writes: the checkpoint layout (Part 1.6), including the class order in best/meta.json
                 (Part 1.3); it writes no run-level file and imports neither schema nor registry
        venv:    probe
      qwen.py               Qwen's tokenizer quirks, pad token, head attach point, LoRA target modules,
                            dtype; the module interface is Part 6.2; carries VERSION
        imports: none (repo); [transformers]
        used by: models/probe_models/base.py (by name)
        reads:   -   writes: -   venv: probe
      service.py            both ends of the probe service: the HTTP server that loads the probe and
                            answers score, generate, encode, decode and render, on the interface and host
                            Part 7.2 fixes, plus the
                            `check` subcommand, which is a client against a running service and loads no
                            checkpoint (main, probe venv); the loop's client (standard library); carries VERSION,
                            which is folded into the sample and inject keys for the reason 2.2 gives
        imports: models/__init__.py; experimental_settings/schema.py (load_frozen, for the check client's
                 expected values, 7.2); models/probe_models/base.py inside serve(); [http.server,
                 transformers and torch inside serve()]
        used by: agent/loop.py (client: render), agent/inject.py (client: score, generate, encode, decode);
                 jobs/launch.py starts it as a piece, which is a tmux command and not an import
        reads:   the checkpoint directories named on its command line, including each one's best/meta.json
                 (call_sep, passed into Probe.generate for /gen, and param_only, on which serve
                 refuses to start; 1.6, 7.2); the run directory's settings.yaml, the check
                 client only (7.2)
        writes:  service_probe_0.json and its piece log in the run directory (7.4)
        venv:    any at import; probe to serve
                            heavy imports in both service files sit inside the serving functions, so each
                            file imports as any
```

```
  agent/                  the loop that runs the agent model on tasks. Nothing is added here; a new way to
                          inject is an entry in inject_format.py, a new injection mechanism is an edit to
                          inject.py, and loop.py and generate.py change for neither
    loop.py                 run each task and seed: open, step, parse, act, until the environment reports the
                            task completed or max_steps is reached; claim tasks across pieces; write the
                            record. Picks the generation step by the setting: the inject section present ->
                            inject.step, absent -> generate.step; passes agent/inject.py's
                            system_text(cfg) into to_messages as extra_developer on every call (7.3, 1.1);
                            holds no probe code itself; carries VERSION
      imports: experimental_settings/schema.py (load_frozen), data/environments/__init__.py,
               data/trajectory_record.py, models/agent_models/service.py (client),
               models/probe_models/service.py (client, for render), agent/generate.py, agent/inject.py,
               jobs/registry.py. It names no family module and imports models/__init__.py nowhere: it
               renders through the probe service and compares the family the service echoes against
               cfg.models.agent_row["family"] (7.2)
      used by: none (program)
      reads:   its run directory's settings.yaml, the environment's split task-id files (through
               data/environments/requested_pairs, whose triples carry the split each task came from,
               2.3), and the
               service_agent_<replica>.json / service_probe_0.json endpoint files in its own run
               directory, whose names it computes from its own --piece index and settings.yaml's
               replicas (Part 7.4)
      writes:  task records (jsonl), heartbeat
      venv:    the environment's (appworld today)
    generate.py             the plain generation step: stream tokens from the agent model to end of turn;
                            exposes the token stream so inject.py iterates it instead of copying it. The
                            baseline path; carries VERSION
      imports: models/agent_models/service.py (client), models/__init__.py (the family module).
               The `probe` field of the `clients` dataclass this file declares is annotated `object`,
               not the probe client class, so this file imports models/probe_models/service.py
               nowhere (7.3)
      used by: agent/loop.py, agent/inject.py
      reads:   -   writes: -   venv: the environment's
    inject.py               the generation step with the probe: iterate generate's token stream, score at
                            each cut, on fire get the call, run it early through the environment, write the
                            result in (inject_format), start a new request from the spliced prefix, roll
                            back on mismatch. Replaces generate.step when the setting has an inject section;
                            offers system_text(cfg), the one place a format's system text reaches the
                            conversation (7.3);
                            declares the module-level literal ARMS, which is what schema's inject.arm
                            axis is checked against (5.3); carries VERSION
      imports: agent/generate.py, agent/inject_format.py, data/probe_input.py, data/trajectory_record.py,
               data/environments/__init__.py (type only; the object is passed in),
               models/probe_models/service.py (client), models/__init__.py (the family module).
               The setting is passed in by loop.py, so this file does not import schema
      used by: agent/loop.py
      reads:   -   writes: spec and resume rows, through data/trajectory_record.py
      venv:    the environment's
    inject_format.py        the table of the five ways an early result is written into the stream, as the
                            module-level literal FORMATS whose entries have the four fields of Part 7.3;
                            schema's inject.format axis is checked against its keys, so a sixth way is one
                            entry here and one schema value; carries VERSION
      imports: none
      used by: agent/inject.py; its keys are cross-checked against schema.py's axis by run.py selfcheck
      reads:   -   writes: -   venv: any
```

```
  train/                  train a probe. A training hyperparameter is a YAML line; a new training practice
                          is a schema.py value plus an edit to trainer.py; a new probe method is a file
                          under methods/ plus a schema.py value
    utils/
      trainer.py            the training loop every method shares: settings -> arguments, seed, backbone,
                            tuning (full or LoRA), checkpoints, metrics, heartbeat, resume, the alignment
                            gate; and its last step, the probe run over the prediction splits with one
                            prediction row per example written to disk (the probe is still on the card). A
                            directory with the checkpoint and no predictions is continued from that step;
                            carries VERSION
        imports: experimental_settings/schema.py, models/__init__.py, models/probe_models/base.py,
                 data/training_data.py, data/probe_output.py, jobs/registry.py; [torch, peft]
        used by: train/methods/{ctool,cgen,cparam}.py
        reads:   example (parquet), the checkpoint layout
        writes:  best/, last/, train_log.jsonl, align_check.json, train_done.json, predictions.parquet,
                 consumed.json (the example parquet it read), heartbeat, done.json (whose stage_extra
                 carries the class order, copied out of best/meta.json)
        venv:    probe
    methods/                one file per probe method, each complete on its own: its batches or packing, its
                            target, its loss, its validation metric; the files do not import each other, so
                            a fix in one is repeated in the other and the alignment test, run per method,
                            catches the one that was missed
      ctool.py              the classification probe: its batches, its head use, its loss, its validation
                            accuracy; carries VERSION
        imports: train/utils/trainer.py, models/probe_models/base.py, data/training_data.py,
                 eval/methods/ctool.py (its match function, per the tree's eval/methods line); [torch]
        used by: none (program)
        reads:   -   writes: - (everything goes through trainer.py)
        venv:    probe
      cgen.py               the call-generating probe: its packing, its instance strings and target, its loss
                            positions, its exact-match validation; carries VERSION
        imports: train/utils/trainer.py, models/probe_models/base.py, data/training_data.py,
                 eval/methods/cgen.py (its match function), data/environments/__init__.py (open_env, for
                 the environment that match takes, 2.6); [torch]
        used by: none (program)
        reads:   -   writes: - (everything goes through trainer.py)
        venv:    probe
      cparam.py             the argument-generating probe: its own packing and strings, the arguments as the
                            target; carries VERSION
        imports: train/utils/trainer.py, models/probe_models/base.py, data/training_data.py,
                 eval/methods/cparam.py (its match function), data/environments/__init__.py (open_env, for
                 the environment that match takes, 2.6); [torch]
        used by: none (program)
        reads:   -   writes: - (everything goes through trainer.py)
        venv:    probe
```

```
  eval/                   reads what is on disk and computes numbers; no GPU, no torch, every file imports
                          as any. A new probe method is a file under methods/; a new metric is an edit to
                          the file that reports it
    utils/
      probe_eval.py         shared by the three methods: read a train run's prediction rows and targets,
                            bootstrap the confidence interval, write the report (both of its files) and read
                            it back; carries VERSION
        imports: experimental_settings/schema.py, data/probe_output.py, jobs/registry.py; [polars, numpy]
        used by: eval/methods/{ctool,cgen,cparam}.py, run.py (read_report, to freeze a temperature),
                 eval/method_table.py
        reads:   prediction (parquet), its own and the referenced eval run's train meta.json
                 (stage_extra.labels, upstream["build"] — the second is what the 2.5 gate compares), probe
                 report (json + parquet)
        writes:  probe report (probe_report.json + fires.parquet), report.md, consumed.json (the
                 prediction parquet and any referenced report it read), heartbeat, done.json
        venv:    any
    methods/                one file per probe method, the metric computed from prediction rows;
                            train/methods/<name>.py calls this file's match function for its validation
                            metric, never its own copy. Each file carries VERSION and PROBE_KIND, the
                            second declared identically in the matching train/methods/<name>.py and
                            compared by selfcheck (Part 2.6)
      ctool.py              fit the temperature and theta on the val rows at the risk targets, freeze theta,
                            report on the test rows, write the fired rows; carries VERSION and PROBE_KIND
        imports: eval/utils/probe_eval.py; [polars, numpy]
        used by: train/methods/ctool.py (its match function)
        reads:   -   writes: - (everything goes through eval/utils/probe_eval.py)
        venv:    any
      cgen.py               exact match of the generated call at the frozen theta; carries VERSION and
                            PROBE_KIND
        imports: eval/utils/probe_eval.py, data/environments/__init__.py (open_env, for the
                 environment whose split_args and build_call report normalises with, 2.6);
                 [polars, numpy]
        used by: train/methods/cgen.py (its match function)
        reads:   -   writes: - (everything goes through eval/utils/probe_eval.py, which hands the
                 prediction frame and the referenced report to the report hook, 2.6)
        venv:    any
      cparam.py             exact match of the generated arguments at the frozen theta; carries VERSION and
                            PROBE_KIND
        imports: eval/utils/probe_eval.py, data/environments/__init__.py (open_env, for the
                 environment whose split_args and build_call report normalises with, 2.6);
                 [polars, numpy]
        used by: train/methods/cparam.py (its match function)
        reads:   -   writes: - (everything goes through eval/utils/probe_eval.py, which hands the
                 prediction frame and the referenced report to the report hook, 2.6)
        venv:    any
    score_run.py            a sample or inject run from its records: task success, speculation outcomes,
                            tokens and time; by seed; against a baseline; carries VERSION
      imports: experimental_settings/schema.py, data/trajectory_record.py, data/environments/__init__.py
               (open_env for split_args and build_call, and requested_pairs, 2.3),
               jobs/registry.py; [polars]
      used by: none (program)
      reads:   the task records of this run and of its baseline; the environment's split task-id files
               (through data/environments/requested_pairs, for the pair list both record gates of 2.5
               are stated over); the scored run's and the baseline run's settings.yaml (the same-setup
               gate of 2.5)
      writes:  run_report.json, report.md, heartbeat, done.json
      venv:    any
    method_table.py         the backbone x method table from the registry; groups sweep children, reports
                            mean and spread
      offers:  table(workflow: str | None = None, out: Path | None = None) -> str (8.6)
      imports: experimental_settings/schema.py, jobs/registry.py, eval/utils/probe_eval.py (read_report)
      used by: run.py (the table subcommand, 8.6; this file is not a stage and has no __main__)
      reads:   jobs/runs.jsonl, the probe reports the rows point at
      writes:  a markdown table on stdout or into a named file
      venv:    any
```

```
  jobs/                   a job is one stage run on cards: the code that starts it and records it, and the
                          record itself. Nothing is added here; batch runs are the sweep keyword in a
                          setting, not a script
    launch.py               the dirty-tree gate; pick free cards and ports; resolve the split files; one
                            tmux session per piece; the start row; the alive check; the `check` client gate on the
                            probe service; refire; and the teardown of a finished run's service pieces
                            (2.3). A piece on another host is started over ssh, and the per-host liveness
                            and card probes are fail-closed; the transport and that rule are Part 3.4's.
                            It is a library with no __main__: `run.py` is the only command
      offers:  launch(stage, setting, run_dir, resolved, git) -> tuple[str, list[dict]] (the outcome and
               the piece entries; `git` is the dict `run.py` already obtained from git_state for this
               launch, 2.5; the entries are appended to the start row inside the lock hold of 8.6),
               refire(run_dir, git, piece=None) -> list[dict], teardown_services(run_dir) -> list[str],
               git_state(run_dir, allow_dirty) -> dict (the dirty gate and the git fields of a start row
               in one function, called by run.py as well, 2.5)
      imports: experimental_settings/schema.py, jobs/registry.py, data/trajectory_record.py (done_pairs,
               is_done, owner, release: to release a dead piece's claims),
               data/environments/__init__.py (tasks and requested_pairs: to resolve the split files
               into meta.json before the pieces start, 8.3, and to refuse an out-of-split tasks id, 2.3)
      used by: run.py
      reads:   constants/path_datasets.yaml (the venv per environment and the venvs map),
               constants/path_outputs.yaml (the login_host and the hosts list), models/table.yaml (the
               serving block, for the agent service's preferred port), the run directory's settings.yaml
               and meta.json, service_<kind>_<replica>.json (its own run's, for the teardown of 2.3, and
               other live runs', for the attach test of 7.4), nvidia-smi, tmux, git
      writes:  the start row in jobs/runs.jsonl, meta.json launch entries, meta.json's split_files,
               dirty.patch, the piece commands
      venv:    probe (it runs on the login machine)
    registry.py             the registry: runs.jsonl rows under a lock, meta.json, the heartbeat, the
                            verdicts, ls/where/find/kill/free, RESULTS.md. Every stage imports it to write
                            its start and finish rows; run.py imports it for the subcommands. Both halves
                            import nothing from this repo and nothing heavier than PyYAML, which Part 0.1
                            already counts inside `venv: any`; the day ls or kill needs more, the
                            subcommand half becomes registry_cli.py
      imports: none (repo); [PyYAML]
      used by: run.py, jobs/launch.py, agent/loop.py, data/build_training_dataset.py, train/utils/trainer.py,
               eval/utils/probe_eval.py, eval/score_run.py, eval/method_table.py (eight; a service piece
               writes no registry file and is judged by its port, Part 8.5)
      reads:   constants/path_outputs.yaml, jobs/runs.jsonl, run directories' meta.json and heartbeat,
               ssh, tmux, nvidia-smi (the per-host session and card probes of ls, free and kill,
               fail-closed per 3.4)
      writes:  jobs/runs.jsonl, jobs/RESULTS.md, meta.json, heartbeat/<piece>-<launch>.jsonl (8.4),
               done.json
      venv:    any
    runs.jsonl              one registry row per stage run, appended at start and at finish by registry.py;
                            never edited by hand; in git
    runs.jsonl.lock         the lock every append takes; ignored by git
    RESULTS.md              rendered from runs.jsonl by registry.py; never edited by hand
  tests/                  empty for now (gyb, 2026-09-17). The four planned checks are in the fourth draft's
                          tree line; until they exist, four rules in this document are kept by hand
                          (Part 9(b)#17)
  .claude/skills/repo-review/SKILL.md      the two-day review: an agent reads the tree against the six
                          principles and writes tasks
  .claude/skills/gpu-run/references/gpu_state.md   cluster notes: drivers, CUDA, pitfalls; read by the
                          gpu-run skill only
  .claude/hooks/settings_readonly.sh       the hook that refuses any agent edit to
                          experimental_settings/*.yaml, and (Part 6.1) to models/table.yaml
  .scratch/review/issues/ the tasks the review writes, in the issue-tracker format already in use
  .claude/                as today

  notes/                  everything gyb writes by hand: TRAPS.md, METHOD.md, DATA.md, WORKPLAN.md,
                          TIMELINE.md, plans/ and docs/
  notebooks/              exploration; imports any module, is imported by none, writes no output directory
                          and no registry row
  figures/                one script per figure, moved here from a notebook when the figure is final
  external/               nothing written in this repo, nothing in git: the AppWorld clone and its venv, the
                          probe venv, the vLLM venv, the lock files. "environment" in this tree means a
                          benchmark, never a venv
```

## 0.3 The count

Python files, by directory: root 1 (`run.py`); `experimental_settings` 1
(`schema.py`); `data` 8 (`__init__.py`, `environments/__init__.py`,
`environments/appworld.py`, `trajectory_record.py`, `training_data.py`, `probe_output.py`,
`probe_input.py`, `build_training_dataset.py`); `models` 8 (`__init__.py`,
`agent_models/__init__.py`, `agent_models/gptoss.py`, `agent_models/service.py`,
`probe_models/__init__.py`, `probe_models/base.py`, `probe_models/qwen.py`,
`probe_models/service.py`); `agent` 4; `train` 4; `eval` 6; `jobs` 2.
**1 + 1 + 8 + 8 + 4 + 4 + 6 + 2 = 34**, the fourth draft's count. `tests/` is 0.

`train/`, `train/utils/`, `train/methods/`, `eval/`, `eval/utils/`,
`eval/methods/`, `agent/`, `jobs/`, `constants/` and `experimental_settings/`
have no `__init__.py` and get none: they are namespace packages (PEP 420),
which Python 3.11 and 3.12 both resolve when the repo root is on `sys.path`.
Every program is started as a module from the repo root, in the command shape
2.6 pins. The two empty `__init__.py` files
under `models/` are the owner's and stay, for the reason the tree gives them.

Four places, and only four, gain a *file* by extension, and the tree's own lines
name all four: `data/environments/<env>.py`,
`models/agent_models/<family>.py`, `models/probe_models/<backbone>.py`, and the
pair `train/methods/<m>.py` + `eval/methods/<m>.py`. Everywhere else an
extension is an edited line.

## 0.4 What each extension touches

This is the table the contracts exist to make true. "new" marks a file the
extension creates in one of those four places; everything else is an edit.
`README.md` is on every row (one line per file, plus the extension recipe) and
the setting YAML is on every row that needs one (written by gyb, not by an
agent); neither is repeated in the counts.

| Scenario | Files touched | Why it is not more |
|---|---|---|
| A new benchmark environment | `data/environments/<env>.py` (new, and it declares its own `SPLIT_ROLE` map beside the other class attributes, 4.1); `experimental_settings/schema.py` (one value on `data.env`, one on `data.instructions`, **and one value on `sample.split` / `inject.split` for every split name the new environment has that no existing one has**); `constants/path_datasets.yaml` (home, venv, data root, split files, **and a `venvs:` entry when the benchmark brings its own interpreter — which must carry PyYAML, Polars and NumPy, because `venv: any` is defined over every interpreter in that map, 0.1**) | The loop calls nine methods and nothing else; the call syntax, the instruction text and the no-code message are the environment's; the interpreter that runs the loop is a column in `path_datasets.yaml` (dependencies P7). `data/build_training_dataset.py` parses calls through the environment object, so it is untouched. |
| A fourth probe method | `train/methods/<m>.py` (new); `eval/methods/<m>.py` (new); `experimental_settings/schema.py` (one value on `probe.method`) | The example row is method-independent (Part 1.2): build writes one row per cut carrying every target, so `data/build_training_dataset.py` and `data/training_data.py` are untouched. The prediction row is method-independent (Part 1.3). `trainer.py` never branches on method: the method file is the program and hands its hooks down (Part 2.6). The head lives in `probe_models/base.py` (dependencies P10). The program name is `train.methods.<probe.method>`, computed from the axis value, so the stage table does not list methods. Nothing branches on the method's *name*: the stage table, the loader's required-field rule and the report's shape all branch on `PROBE_KIND` (Part 2.6), which is declared at column zero in **both** new files — `schema.py` reads the train file's copy as source text, `eval/utils/probe_eval.py` reads the eval file's off the module it was handed, and `selfcheck` fails when the two disagree. A method that is neither a classifier nor a generator needs a third `PROBE_KIND` and therefore also touches `data/probe_output.py` (a column for its output), `eval/utils/probe_eval.py` (a third report shape) and `models/probe_models/base.py` (a third head, beside the `attach_head` that is called only for `classifier`, 6.2). A generating method that is not a whole-call generator states it in its `CHECKPOINT_META` (2.6), which is what keeps `param_only` out of `base.py`'s branches. |
| A new training hyperparameter | `experimental_settings/schema.py` (field, default, comment); the one module that reads it (`train/utils/trainer.py` or one method file) | The key is over the *diff from the defaults* (Part 3.3), so a field whose default reproduces the old behaviour changes no key and reruns nothing. |
| A new field on the task record, read by nobody downstream | `data/trajectory_record.py` (the column and its entry in `DEFAULTS`); the one writer (`agent/loop.py` or `agent/inject.py`, 1.1 — an environment never writes a record row; a field that comes out of the environment reaches the record as a value one of the nine methods returned) | A column that every reader treats as optional is added with a declared default and leaves `VERSION` alone, so old record files still read and no key moves (dependencies P9). |
| A new field on the task record that a downstream stage reads | the same two files (same writers: `agent/loop.py` or `agent/inject.py`), **plus the column's name in `REQUIRED` and a `VERSION` bump**, which re-keys `sample` and `inject` and costs the recollection | Leaving `VERSION` alone would reuse the finished sample directory, in which the column is absent from every file, and hand the new reader its declared default for every row — silently (Part 1's DEFAULTS rule). The bump is the honest price of needing the field. |
| A sixth injection format that reuses a placement | `agent/inject_format.py` (one entry); `experimental_settings/schema.py` (one value on `inject.format`) | The axis values are a literal list in `schema.py` that `selfcheck` proves equal to `FORMATS.keys()`, so `schema.py` does not import `agent/`, and the two edits are the same two the environment and probe-method rows make. A *new placement* costs one more file, `models/agent_models/<family>.py`, which owns the control-token wrapping (synthesis 6) — one function per family, not one entry. |
| A new probe backbone | `models/probe_models/<backbone>.py` (new); `models/table.yaml` (one row); `constants/path_models.yaml` (one row) | Model aliases are validated against `table.yaml`, not against a schema axis, so there is one list of legal model names. `base.py` holds everything the backbones share. |
| A new agent-model family | `models/agent_models/<family>.py` (new); `models/table.yaml` (one row); `constants/path_models.yaml` (one row); `experimental_settings/schema.py` (one value on `generation.effort` for each reasoning tier the new family has that no existing family has, 5.3); **plus the family's rendering library installed in the probe venv and the vllm venv**, which is the precondition `/render` and the render-equals-server check impose (7.2), and which `selfcheck` proves by importing each family module under both interpreters | Every caller reaches the family through `models/__init__.py`'s `agent(alias)`, and no file anywhere names a family module or a family string: the two services import through `agent(alias)`, and the loop's attach check compares the family the service *echoes* against `cfg.models.agent_row["family"]`, the expansion of its own table row (5.2), rather than against a literal (Part 7.2). The prefetch wrapping lives in the family file, so `agent/inject_format.py` holds only placement, special-token need, system text and the body renderer (dependencies P4, grounding F4). The module's names are fixed in Part 6.2, `EFFORTS` among them: the loader validates `generation.effort` against the `EFFORTS` of the chosen alias's family (5.7), so a tier one family does not have fails at load instead of inside that family module after the cards are taken. |

Two changes that are not extensions but deserve the same treatment:

| Scenario | Files touched | Cost |
|---|---|---|
| Change the cut rule | `data/probe_input.py` (+ `VERSION`); a cut rule that *gains a parameter* also adds the field to `schema.py`'s `build` section **and to `PROBE_TEXT_FIELDS`** (1.7) | An inherent full rerun downstream: build re-keys, train follows through the build key, eval through the train key, inject through `probe_input`'s own version. The cost is on the file's README line so nobody is surprised. Leaving the new field out of `PROBE_TEXT_FIELDS` is the one edit that makes a live run silently disagree with its training: the live run would take the schema default while the probe was trained on another value, and the inject key would not move. |
| Rename an axis value | not allowed | A value is added and retired, never renamed (dependencies P6); `schema.py`'s `RETIRED` set is what makes retiring safe (3.3). |

---

# Part 1. On-disk formats

Four formats cross a stage boundary: the task record, the example, the
prediction and the probe report. Each is defined in exactly one file, which
owns the column list, the types, the id rule, the reader and the writer. No
other file constructs a row of that format by hand. Beside them, every run
directory holds the same small set of files (Part 1.5).

Conventions shared by the three formats in `data/`, defined in
`data/__init__.py`:

- **Reading returns a Polars DataFrame** with the format's declared schema.
  `read_frame` (below) reads the file's own schema first, **raises when a column of `REQUIRED`
  is absent from it** (below), selects the columns that are present,
  and then fills every declared column absent from the file with its `DEFAULTS`
  entry, so an older file reads as if the column had always been there. A column
  that is present but of the wrong type still fails loudly. *The reason it is
  written this way and not as one library call: a strict `pl.read_ndjson(path,
  schema=SCHEMA)` yields **null**, not the `DEFAULTS` entry, for a key no line
  carries, and `pl.read_parquet(path, columns=...)` raises on a column the file
  does not hold — so the optional-column rule below would reach its readers as
  null for jsonl and as an error for parquet.*
- **Records are jsonl, one file per task run**, written row by row and flushed
  after each row, so a killed piece keeps everything it wrote
  (`legacy/pipeline/inject/live_appworld.py:291-299`). **Examples and
  predictions are parquet**, written once in bulk into a temporary name beside
  the target and renamed, so a killed writer never leaves a half parquet.
- **Every format file declares `VERSION: int`, `DEFAULTS: dict[str, Any]` and
  `REQUIRED: frozenset[str]`.**
  `VERSION` bumps when an existing column changes meaning for the same settings,
  or when a column is removed. A read refuses a file whose recorded version is
  higher than the reading code's. `REQUIRED` is the set of columns a downstream
  stage reads; it is what makes the "never rely on `DEFAULTS` for a column you
  require" rule below executable, since `read` fills from `DEFAULTS` and destroys
  the absence information the moment it returns.

  A *new* column follows one of two rules, and which one depends on who reads it.

  | the new column is | how it is added | what it costs |
  |---|---|---|
  | optional to every reader (an audit field, a timing, something only a person looks at) | an entry in `DEFAULTS`, **no** `VERSION` bump | nothing: old files stay readable and no key moves (dependencies P9) |
  | read by a downstream stage (a new probe target, a new build gate's input) | an entry in `DEFAULTS`, a name in `REQUIRED` **and** a `VERSION` bump on the format file | the producing stage re-keys, so the data is recollected or rebuilt |

  *The failure the first rule prevents: adding one audit field to the record
  re-keying every sample and inject run, which is GPU days. The failure the
  second rule prevents, which is worse: a column added because a consumer needs
  it, with no bump, leaves the producing key unchanged, so the finished upstream
  directory is reused, the column is absent from every file in it, and the new
  consumer silently receives the declared default for every row —* `consumed.json`
  *does not catch it, because the hashes still match.* A reader therefore never
  relies on `DEFAULTS` for a column it requires, and the mechanism is
  `REQUIRED`: **`read_frame` in `data/__init__.py` (below) compares the file's own
  schema against the format file's `REQUIRED` set before it fills anything, and
  raises, naming the column, the path and the file's recorded version**, when a
  required column is absent from the file. Filling happens only for the columns
  outside that set, so `DEFAULTS` serves exactly the readers that treat a column
  as optional. A column moved under the second rule above is added to `REQUIRED`
  in the same edit as the `VERSION` bump, and `run.py selfcheck` (8.6) fails on a
  format file whose `REQUIRED` names a column its schema does not declare.
- **The id rule.** One chain, so every downstream join is a string equality.

  | level | id | built from |
  |---|---|---|
  | record | `<task_id>__s<seed>` | the task id and the trajectory's seed |
  | event (one step) | `<record_id>\|s<step>` | the record id and the step index |
  | example (one cut) | `<event_id>\|c<cut_index>` | the event id and the cut index |
  | prediction | equal to the example id | — |

  `|` is the separator: AppWorld task ids are of the form `50e1ac9_1` (checked
  by calling `load_task_ids` in the AppWorld venv) and contain neither `|` nor
  `:`. The three ids are built by `record_id`, `event_id` and `example_id` in
  `data/__init__.py`, never by string formatting at a call site, and each takes
  the id of the level above it, which is what makes the chain a single string
  equality:

  ```python
  def record_id(task_id: str, seed: int) -> str
  def event_id(record_id: str, step: int) -> str
  def example_id(event_id: str, cut_index: int) -> str
  ```

  *The reason they are named here: `data/trajectory_record.py` builds
  `<run_dir>/records/<task_id>__s<seed>.jsonl` paths inside `done_pairs` (1.1)
  and `data/build_training_dataset.py` builds every example id, so two files must agree on
  the argument order and the types, and the table above shows only the rendered
  strings.* Ids are stable
  across runs: the same task, seed, step and cut index in another run gives the
  same id, which is what lets `score` pair an inject run with its baseline task
  by task and seed by seed.
- **The shared reader and writer have names**, beside the three id functions, and
  the three format files call them with their own literals:

  ```python
  def read_frame(path: Path, *, schema: dict, defaults: dict,
                 required: frozenset[str], version: int) -> DataFrame
  def write_frame(path: Path, df: DataFrame, *, schema: dict) -> None
  ```

  `read_frame` picks jsonl or parquet by the suffix and raises, naming the path,
  on a column of `required` the file does not hold, on a recorded version above
  `version`, and on a declared column present with the wrong type; it fills every
  other declared column absent from the file from `defaults`. `write_frame`
  writes through a temporary name in the same directory and renames.
  *The reason they are named here: `data/trajectory_record.py`, `data/training_data.py` and
  `data/probe_output.py` are three files that must all reach the rules above
  through one call, and a rule referred to five times as "the shared reader" is
  three readers by the time three files are written.*

## 1.1 Task record — `data/trajectory_record.py`

**Layout.** One file per task run,
`<run_dir>/records/<task_id>__s<seed>.jsonl`. One file is one task and one
seed, never appended by two processes (lifecycle A5, grounding F6); today's
code already writes one file per trajectory
(`legacy/envs/collect/run_appworld.py:71-76`,
`legacy/pipeline/inject/live_appworld.py:290-299`). The first line is the
`meta` row and carries `owner_session`; the last line of a finished file is the
`final` row.

**Claiming.** A piece claims a task by creating the file with `O_EXCL`; the
`meta` row is written into it as soon as `Environment.open` has returned. A piece
that loses the race moves on. **The claim and the `meta` row are two steps, and
the offered functions split them**: `open_record(dir, task_id, seed)` performs
the exclusive create of an empty file and returns the `Writer` (None on a lost
race), and `agent/loop.py` writes the first row with
`writer.row("meta", ...)` once it has opened the world and captured `task_text`.
*The failure the split prevents: `meta` carries `task_text`, which 4.2's methods
do not hand out and which only `Environment.open` produces (below), so a claim
primitive that took the whole `meta` dict would force the loop to open the world
**before** it claims — two pieces holding one AppWorld world for the same
(task, seed), both writing the benchmark's per-task output directory that
`Environment.open` names by task and seed, and the loser calling `close()`, whose
one line is "delete the per-task outputs".* This
replaces today's `.claims/` directory of `mkdir` tickets, whose docstring chose
`mkdir` as "atomic on NFS"
(`legacy/pipeline/inject/live_appworld.py:590-603`): the file is the ticket, so
there is no second thing to clean up. The swap is grounded, not assumed — the
outputs mount is NFSv4.0 and a three-host, 24-process race for 150 files gave
exactly one winner per file every time (the measurement is in the facts section
above). Were that mount ever replaced by one where the measurement fails, the
claim goes back to `os.mkdir(<records>/<id>.claim)` followed by the record
write, and nothing else in this document changes.

**Done, partial, refire.** `is_done(path)` is "the last line parses and its
`type` is `final`" — **whatever `abort` says**. A `final` row with a non-null
abort is a finished task that failed, and it counts as done, so a task that
aborts every time cannot loop forever; `build` protects itself against a batch
that mostly aborted with `build.max_abort_frac` (Part 2.5) instead. A file that
is not done is **deleted and the task redone**: a trajectory cannot be resumed
mid-task because the world state died with the process, and deleting also
removes any half-written last line, which is what would otherwise break a
strict Polars read. **A claim is released only on the login machine**, by `jobs/launch.py` or
`run.py`: they delete the unfinished files whose `owner_session` is no longer a
live tmux session. **While any piece of that run still has a live session the
walk leaves the dead piece stopped**: it releases the claims, reports them, and
launches nothing, because 2.5's launch gate refuses that key anyway; restarting
that one piece beside its live siblings is `run.py refire`, which releases the
same claims first (2.3). **Once no piece of `kind` `loop` or `train` of that run
has a live session**, the walk relaunches the stage for the missing pairs, which
is 2.3's rule and the only way a run whose work pieces have all died advances at
all; the relaunch reuses the run's live service pieces, exactly as
`jobs/launch.refire` does. *The failure the scoping prevents: a service piece is
a piece of the run (2.1) and is a server that never exits on its own, torn down
only when `run.py` writes `done.json` (2.3) — so "no session of the run is live"
is false for the whole life of an unfinished run, and a `sample` or `inject` run
whose six loop pieces all died (one vLLM restart is enough) would release claims,
report them and launch nothing, forever.* *The reason the release does
not start anything by itself while siblings are live: the sampler is retired and
the only refire left is a person's (2.3, 9(a)#39), so a plain `run.py train_probe
ctool_q06` over a run with one dead piece among five live ones must release that
session's claims and say so, not silently start a seventh piece into a directory
six are writing.* **A record file whose
first line does not parse as a `meta` row is treated as unowned and is deleted by
the same login-machine release once its mtime is older than the margin its caller
passes in as `unowned_age_s`, which is
`registry.DEFAULTS["launch_timeout_s"]`** (8.5, the one constant 2.5, 7.4, 8.1
and 8.2 also read; `run.py` and `jobs/launch.py` both import `jobs/registry.py`
and pass the value in, exactly as they pass `registry.live_sessions()`, so
`data/trajectory_record.py` imports only `data/__init__.py`) — that is the state a
piece killed between the exclusive create and the first write leaves behind, and
`owner(path)` returns None for it, so no dead-session test can reach it. The age
margin is what keeps the release off a live claim: a live piece writes its `meta`
row as soon as `Environment.open` returns and flushes it (Part 1's flush-per-row
rule), which is inside the same `launch_timeout_s` the launcher already allows a
piece for reaching its first beat (8.5), so
a file that still has no `meta` row a `launch_timeout_s` later is one nobody is
writing, while a file the process never got to write again keeps that old mtime
and is still reached. *The failure the margin prevents: the release runs while
sibling pieces are live — 9(c)#4 refires piece 3 with five pieces still claiming
— so a rule with no margin races a live piece in the window between its `O_EXCL`
create and its flushed `meta` row, and the loser keeps writing into a path the
winner has re-created: two worlds for one (task, seed) and two writers at one
path.* *The failure the deletion itself prevents:
a zero-byte file that is neither done nor owned, which no rule releases, so the
task is never re-claimed and `build`'s gate (2.5) refuses forever with "missing
record" for a pair that will never be produced.* A loop piece never
deletes a file it does not own; it skips every file that exists. *The reason:
"the owner session is gone" can only be answered by `tmux ls` on the launching
host (today, `ssh <host> tmux ls`, `legacy/ops/gpu_jobs.py:76-84`), which a
piece in the environment's venv on a compute node cannot answer. A piece that
guessed would delete a live sibling's claimed record mid-task.*

**Row kinds.** Six, exactly today's six
(`legacy/pipeline/inject/live_appworld.py:34-42`): `meta`, `gen`, `spec`,
`resume`, `env`, `final`. A sample run writes `meta`, `gen`, `env`, `final`; an
inject run writes all six. One format serves both, which is what lets
`eval/score_run.py` pair an inject run with its baseline.

| kind | column | type | meaning |
|---|---|---|---|
| all | `type` | str | `meta`, `gen`, `spec`, `resume`, `env`, `final` |
| all | `step` | i32 | step index; null on `meta` |
| all | `ts` | f64 | the writing machine's clock; only ever diffed against another `ts` in the same file |
| meta | `version` | i32 | this format's `VERSION` at write time |
| meta | `record_id` | str | `<task_id>__s<seed>` |
| meta | `stage` | str | `sample` or `inject` |
| meta | `env` | str | environment name (`data.env`) |
| meta | `task_id` | str | the environment's task id |
| meta | `seed` | i64 | the trajectory seed, sent in the request body and recorded |
| meta | `env_seed` | i64 | the environment's own seed (AppWorld's `random_seed`, 100 today) |
| meta | `split` | str | the split the task came from, written by `agent/loop.py` out of the `(split, task_id, seed)` triple it is walking (2.3); it is what `build` maps through `env.SPLIT_ROLE` under `split_source: env` (2.5) |
| meta | `arm` | str | `sample`, `probe`, `no_probe`, `probe_nofill` (CONTEXT: with probe / no probe) |
| meta | `instructions` | str | the instruction-variant **name** (`data.instructions`), never the task's own text |
| meta | `task_text` | str | the environment's own instruction for this task, captured by `agent/loop.py` after `Environment.open`; the probe's text and `to_messages` are built from it |
| meta | `agent_model` | str | the alias from `models/table.yaml` |
| meta | `generation` | str | the resolved `generation` section as canonical JSON text, echoed back |
| meta | `inject` | str | the resolved `inject` section as canonical JSON text, or null on a sample run |
| meta | `commit` | str | the git commit the run was launched at: `cfg._commit`, read out of the frozen `settings.yaml` (1.5) and **never probed from git by a piece**, which runs days later on a refire and on a machine whose checkout may have moved |
| meta | `run_key` | str | the stage key of the run directory this file sits in |
| meta | `owner_session` | str | the tmux session that claimed this file |
| gen | `reasoning` | str | the thinking text of this step |
| gen | `content` | str | the answer text of this step |
| gen | `usage` | struct{in:i64,out:i64} | prompt and completion tokens |
| gen | `wall_s` | f64 | wall time of the step's generation |
| gen | `finish_reason` | str | the server's finish reason |
| gen | `stop_reason` | str | the server's stop reason |
| gen | `prefix_tok` | i32 | prompt length in tokens |
| gen | `prefix_sha` | str | sha1 of the prompt token ids; the one cheap way to compare two arms' prompts after the fact, which is what the 2026-08-18 identity investigation needed |
| gen | `gen_ids` | list[i32] | the generated token ids; null unless `store_token_ids` |
| gen | `n_inject` | i32 | injections in this step (0 on a sample run) |
| gen | `discard` | struct{chars:i64,tokens:i64,events:i32} | text and tokens thrown away by interruptions |
| spec | `fire_index` | i32 | 0-based fire number within the step |
| spec | `cut` | i32 | character offset in the thinking where the probe fired |
| spec | `n_checked` | i32 | how many cuts were scored before this one |
| spec | `conf` | f64 | the probe's confidence at the cut |
| spec | `pred_label` | str | the tool the score probe predicted |
| spec | `gen_call` | str | the call the generation probe wrote |
| spec | `exec_code` | str | the call as executed after requoting |
| spec | `arg_modes` | list[str] | which requote branch each argument took |
| spec | `exec_out` | str | the speculated call's output, clipped to the environment's `RESULT_CAP` |
| spec | `exec_ok` | bool | the speculation ran without an error |
| spec | `error_kind` | str | the error class, or null |
| spec | `note` | str | the exact text spliced into the stream |
| spec | `format` | str | the injection format used |
| spec | `head_tok` | i32 | tokens kept from the model's own output at the splice |
| spec | `head_chars` | i32 | characters kept |
| spec | `note_tok` | i32 | tokens the note added |
| spec | `discarded_chars` | i32 | characters thrown away at this interruption |
| spec | `overflow_ids` | list[i32] | the ids thrown away; null unless `store_token_ids` |
| spec | `spec_s` | f64 | wall time of snapshot + execute + restore |
| resume | `fire_index` | i32 | which fire this resend follows |
| resume | `overflow_tok` | i32 | how many ids were discarded last time |
| resume | `new_tok` | i32 | how many ids the resend produced |
| resume | `match_len` | i32 | how many leading ids matched |
| resume | `identical` | bool | the resend reproduced the discarded continuation exactly |
| resume | `stop_reason` | str | the server's stop reason for the resent request |
| env | `action` | str | the code the model ran, or null when it wrote no code block |
| env | `result` | str | the environment's output, clipped to `RESULT_CAP` |
| env | `error_kind` | str | the error class, or null |
| final | `steps` | i32 | steps taken |
| final | `completed` | bool | the agent called the environment's completion API |
| final | `abort` | str | why the run stopped early, or null |
| final | `judge` | str | the environment's own evaluation dict as canonical JSON text, for a person and for an audit; nothing parses it against a field list |
| final | `success` | bool | the one field every reader needs, taken from the evaluation dict's own `success` and declared as a column of its own; `eval/score_run.py` reads this and never the JSON |
| final | `tokens_in` / `tokens_out` | i64 | totals for the run |
| final | `wall_s` | f64 | wall time of the whole task |
| final | `finished_at` | f64 | unix time at close |

**`meta.generation` and `meta.inject` are text, not structs.** They are written
for a person and for `eval/score_run.py`'s same-setup comparison, which is a
string equality over the canonical text, and they are never parsed against a
declared field list. *The reason: Part 1's reading convention passes a declared
schema, so a struct column would have to enumerate its inner fields in
`data/trajectory_record.py`'s `SCHEMA`, and then every added `generation.*` or
`inject.*` field would be an edit to this format file — and, because `build` and
`score` read the record, a `VERSION` bump under the second `DEFAULTS` rule, which
re-keys `sample` and `inject` and costs a recollection. That would contradict 3.3
and 0.4, where adding a hyperparameter is free.* The authoritative copy of a
run's settings is its `settings.yaml`; these two columns are an echo, so a new
field in either section changes no column of this format and bumps no `VERSION`.

`final.judge` needs one shape, because today's sample side stores the evaluation
as a string (`legacy/envs/collect/run_appworld.py:231`) and the inject side as a
dict (`legacy/pipeline/inject/live_appworld.py:834`), and the scoring side has
to read it. One shape: **canonical JSON text plus a declared boolean `success`**,
the same rule `meta.generation` and `meta.inject` follow above. *The reason it is
not a struct: the evaluation dict's fields are the benchmark's, so a struct
column would have to enumerate them in `data/trajectory_record.py`'s `SCHEMA`, and a
second benchmark — or an AppWorld upgrade that adds a field — would then cost an
edit to this format file plus a `VERSION` bump and a full recollection, while
0.4's new-environment row lists neither this file nor that cost. `success` is a
column of its own because it is the one field a downstream stage reads, and a
declared column is what keeps `eval/score_run.py` off the JSON.*

`match_len` and `identical` are computed live in `agent/inject.py`, where the
ids are in memory, and stored on the `resume` row; `overflow_ids` is stored only
under `store_token_ids`, for a later audit.

**`task_text` is a required column from this format's first version.**
`meta.instructions` is a variant name, not the task goal, and the task goal is
the conversation's first user turn: `to_messages` cannot rebuild the history
without it and `data/build_training_dataset.py` cannot call `probe_input.assemble`, whose
first parameter is the task text. `build` runs in the `any` venv and the nine
methods of Part 4.2 hand out task *ids*, not task text, so the only place the
text can be captured is the loop, after `Environment.open`. Today's code already
does exactly that (`legacy/envs/collect/run_appworld.py:188,102` writes
`instruction = world.task.instruction`, `legacy/pipeline/annotate/build.py:69`
reads `task = meta.get("instruction")`). It gets an entry in `DEFAULTS` like
every other column, and `data/trajectory_record.py` carries `VERSION` from its first
version, because 1's second `DEFAULTS` rule applies: a downstream stage reads it.

**Who writes.** `agent/loop.py` writes `meta`, `gen`, `env`, `final`;
`agent/inject.py` writes `spec` and `resume` through the same writer object.
**Who reads.** `data/build_training_dataset.py` (events and cuts), `eval/score_run.py`
(outcomes, tokens, speculation), and the two login-machine programs
`jobs/launch.py` and `run.py` (`done_pairs`, `is_done`, `owner`, `release` — the
completeness check of 2.3 and the claim release above are both login-machine
work, so both reach the rule through this one file rather than carrying a second
copy).

**Offered functions.**
`open_record(dir, task_id, seed) -> Writer | None` (the `O_EXCL` create of an
empty file; None when another piece holds it, and the `meta` row is the caller's
first `row` call, above), `Writer.row(kind, **fields)`, `Writer.frame() -> DataFrame`
(the rows this writer has written so far, held in memory, in the same schema
`read` returns), `Writer.close()`,
`is_done(path) -> bool`, `owner(path) -> str | None`,
`done_pairs(dir, pairs) -> set[tuple[str, int]]`,
`release(dir, live_sessions, unowned_age_s) -> list[Path]` (the set comes from
`registry.live_sessions()` and the margin from
`registry.DEFAULTS["launch_timeout_s"]`, both passed in by the two
login-machine callers, 8.0, 8.5), `read(path) -> DataFrame`,
`read_dir(dir, pairs) -> DataFrame`,
`to_messages(df, upto_step, task_text: str, instructions: str, no_code: str,
extra_developer: str | None) -> list[dict]`.

`done_pairs` is what the two login-machine callers use, and it exists so that
neither formats a record path: it builds each candidate path from
`data/__init__.py`'s `record_id` and returns the subset of `pairs` whose file
`is_done`, reading one line of each file rather than every row. `run.py`'s
completeness check, its progress count (8.4) and `jobs/launch.py`'s claim release
all go through it. *The failure this prevents: both callers formatting
`<run_dir>/records/<task_id>__s<seed>.jsonl` themselves, which Part 1's id rule
forbids, and `read_dir` being used for a yes/no, which reads every row of every
record file to answer it.*

`read_dir` reads **exactly the (task, seed) files in `pairs`** and skips every
file whose `is_done` is false. Both halves matter, because a `sample` key
excludes the seed and task lists (Part 2.2), so one records directory holds
every request that ever shared the key, and it holds in-flight partial files
while another request is still collecting. *The failure this prevents: two
builds with different seed lists producing identical example sets from the same
directory, and a build run beside a larger collection reading a half-written
last line.*

`to_messages` rebuilds the conversation exactly as the model saw it, and both
the loop (live) and the builder (offline) use it, so there is one definition of
what the agent's history looks like. Its three text parameters come from two
different places, and neither is guessed: `task_text` is the `meta` row's own
column (the task goal, which is the conversation's first user turn), while
`instructions` and `no_code` are the environment's class attributes, because the
record carries only the instruction-variant *name*. Both callers pass
`df` (whose `meta` row holds `task_text`),
`env.INSTRUCTIONS[cfg.data.instructions]` and `env.NO_CODE_MESSAGE`.
That keeps the two texts entering from one place and keeps
`data/trajectory_record.py` free of any import of `data/environments/`.

**`extra_developer` is appended to the developer message inside
`to_messages`**, and it is the sixth parameter because the conversation is
rebuilt from scratch on every call: the live caller passes
`agent/inject.py`'s `system_text(cfg)` on **every** step (7.3), the offline
caller passes None. *The failure this prevents: with the text appended once,
outside this function, it is in step 0's prompt and gone from step 1 onwards,
because step 1's `messages` is a fresh `to_messages` result — different prompt
bytes with no error, no gate and no column that records it, since the `meta`
row's `inject` is an echo of the setting and not of the developer message. The
other way out, a loop that keeps its own growing message list and never calls
`to_messages`, is exactly the drift `to_messages` exists to prevent.*

**Where each caller's `df` comes from.** The live caller passes
`writer.frame()`, the offline caller passes `read(path)`, so neither builds a
message list of its own. *The failure this prevents: `agent/loop.py` holds a
`Writer`, not a frame, so without `Writer.frame()` a builder either invents one
or lets the loop assemble `messages` its own way — which is exactly the drift
`to_messages` exists to prevent — and re-reading its own jsonl off NFS once per
step is not something this document asks for.*

**The gen-and-env pairing.** A step is one `gen` row and one `env` row with the
same `step`. `build_training_dataset.py` joins them inside one file and **raises, naming
the record and the step, when a `gen` row has no `env` row** rather than
stopping the trajectory there. *The failure this prevents: today's builder
breaks out of the loop on a failed join
(`legacy/pipeline/annotate/build.py:75-80`, `if e is None: break`) and silently
drops the rest of a trajectory.*

## 1.2 Example — `data/training_data.py`

**Layout.** `<run_dir>/examples.parquet`, one file, written once by
`data/build_training_dataset.py`. The split is a column, not three files, so a change to
the split rule rewrites one file and any reader takes "the val rows" by filter.

**One row per cut, not per method.** This is the single decision that makes a
fourth probe method cheap: the row carries every target shape a method could
want, and the method picks its column at train time.

| column | type | meaning |
|---|---|---|
| `example_id` | str | `<record_id>\|s<step>\|c<cut_index>` |
| `event_id` | str | `<record_id>\|s<step>`, the unit that fires at most once |
| `record_id` | str | the record file this came from |
| `task_id` | str | the environment's task id; the split is by task |
| `seed` | i64 | the trajectory seed |
| `step` | i32 | step index in the trajectory |
| `cut` | i32 | character offset of the cut in the thinking |
| `cut_index` | i32 | 0-based index of the cut within the event |
| `n_cuts` | i32 | how many cuts this event has |
| `depth` | f32 | `cut / len(thinking)`, rounded to four places: the earliness measure |
| `text` | str | what the probe is shown, from `data/probe_input.py` |
| `tool` | str | the tool actually called at this step: ctool's target |
| `call` | str | the normalised whole call `tool(k=v, ...)`: cgen's target |
| `args` | list[struct{key:str,value:str}] | the parsed arguments in call order, kept for the build gates of 2.5 (a row whose `call` does not re-parse to its `tool` and `args`) and for a person; **not** cparam's training target, which `train/methods/cparam.py` derives from `call` and `tool` as a string (below) and writes into `prediction.target`, and never read by `eval/`, which sees only the prediction frame (1.3, 2.6) |
| `weight` | f32 | `1.0` under `uniform`, `1/n_cuts` under `per_event` |
| `split` | str | `train`, `val`, `test` |
| `env` | str | environment name |
| `agent_model` | str | the alias that produced the trajectory |
| `version` | i32 | this format's `VERSION` at write time |

`call` is built by the environment's `build_call(tool, args)`, which is the
**inverse** of that environment's `split_args` and is not today's `make_call`
(4.2, and the build gate of 2.5 is what executes the requirement).
cparam's target is derived from
`call` and `tool` the way
`legacy/pipeline/train/train_causal_param.py:105-113` derives it (strip
`tool + "("`, keep the closing parenthesis), and that derivation lives in
`train/methods/cparam.py`, because it is that method's business. cparam's target
is therefore a **string**, like every method's, which is what makes
`prediction.target` one `str` column for all three (1.3) and
`match(pred, target, env)` one signature (2.6). `args` and that string are two objects with two readers, and
the `args` row above says which is which, because training on the list instead of
the string would tokenise a different target and give different numbers.

There is no `method` column and no `target` column: the three methods read the
same rows. *The failure this prevents: three datasets per sample where one
suffices, and a cgen run trained on a ctool build.*

**Who writes.** `data/build_training_dataset.py`. **Who reads.**
`train/utils/trainer.py` (all rows of the requested split, handed to the method
file as a frame).

## 1.3 Prediction — `data/probe_output.py`

**Layout.** `<train run_dir>/predictions.parquet`, written by
`train/utils/trainer.py` as the last step of training with the probe still on
the card (principle 7). One row per example row of every split named by
`train.predict.splits` (5.2), **uniform across methods**: the
generating probes generate at every cut row, so eval can apply any theta later
without a GPU. That is the owner's decision; the construction plan measures the
cost in the smoke and the fallback is written down in Part 9(a)#2.

| column | type | meaning |
|---|---|---|
| `example_id` | str | joins to the example row and to the fired rows |
| `event_id` | str | copied from the example: the unit that fires at most once |
| `task_id` | str | copied from the example: the bootstrap resamples by task |
| `depth` | f32 | copied from the example: earliness |
| `split` | str | copied from the example |
| `tool` | str | copied from the example: the tool actually called at this step, whatever the method. It is ctool's `target` as well, and for the two generators it is the ground truth their `tool_ok` is computed against — `fires.parquet` carries only `label_pred`, the classifier's *prediction* (1.4) |
| `method` | str | the `probe.method` value that wrote this row (5.3); written by the method's own `predict` hook (2.6) |
| `target` | str | the example's target for this method, written here so eval opens one directory, and **written by the method's `predict` hook** (2.6), which already receives the example frame: `tool` for ctool and `call` for cgen, taken straight from the example row, and for cparam the string `train/methods/cparam.py` derives from `call` and `tool` (1.2) |
| `score` | f32 | ctool: the largest softmax probability at temperature 1; null for the generators |
| `label_pred` | str | ctool: the argmax class name; null for the generators |
| `logits` | list[f32] | ctool: the class logits in `labels` order; null for the generators |
| `text_pred` | str | cgen, cparam: the string `Probe.generate` returned (6.2) |
| `gen_tokens` | i32 | the generators: how many tokens were generated |
| `version` | i32 | this format's `VERSION` at write time |

**The column list has exactly two writers, and the split between them is the
line `trainer.py` never branches on a method.** The method's `predict` hook
returns `example_id`, `method`, `target` and its own output columns (`score`,
`label_pred`, `logits` for a classifier; `text_pred`, `gen_tokens` for a
generator); `train/utils/trainer.py` copies the five method-independent columns
`event_id`, `task_id`, `depth`, `split` and `tool` from the example row it
already holds, joining on `example_id`; and `data/probe_output.py`'s writer stamps
`version`. Everything is written once, in one place, from one frame, so that
**`eval/` reads exactly one upstream directory**, the train run, and nothing can
drift within a run. *The failure the split prevents: `target` is `tool` for
ctool, `call` for cgen and a string `train/methods/cparam.py` derives for cparam
(1.2), so a trainer that filled it would need an `if method == "cparam"` branch,
which 2.6 forbids outright — and a trainer that filled it from the example frame
would write `call` or null for cparam, which makes
`eval/methods/cparam.py`'s `params_all_ok` compare against the wrong string: a
wrong number with no error, under a key that moved correctly. The failure the
copy prevents: `probe_eval.py` having to resolve the build key out of a train
run's `meta.json` to find a label, which is a second path to the same number and
one more thing to get wrong.*

`logits` is kept because the temperature fit needs the whole class vector and
eval has no GPU; at about 150 classes and float32 that is roughly 600 bytes a
row, which parquet compresses well. *The failure this prevents: a calibration
fix that can only be applied by retraining (grounding F1).*

**The class order and its one owner.** `models/probe_models/base.py` owns the
head, so it owns the class order, and it writes `labels: list[str]` into
`best/meta.json` (Part 1.6) — the file it already writes.

**How the list is built, and by whom.** It is a hook on the method file,
`head_labels(df, cfg)` — 2.6 fixes what each method returns — because the class
order is the method's business and `train/utils/trainer.py` never branches on a
method. `trainer.run` calls the hook on the **whole** example frame before
`base.load` and passes the list and its length down (6.2);
`base.py` writes the list into `best/meta.json`, and a resume reads it back from
`ckpt_dir/meta.json` instead of calling the hook. *The failure the whole frame
prevents: a tool that appears in val or test and never in train is an expected,
documented condition — today's builder counts its vocabulary over the whole pile
for exactly that reason (`legacy/pipeline/annotate/build.py:404`) and
`legacy/pipeline/annotate/check_callstr.py:58-61` lists such tools as a known
deviation — so a class order taken from the training split alone leaves a val or
test row with no index at all.* *The failure the hook prevents:
today's order is `Counter.most_common()` with an unspecified tie-break
(`legacy/pipeline/annotate/build.py:404-406`, read back at
`train_causal_tool.py:388-396`), so two trainings of the same key on the same
parquet can order `logits` differently; eval reads `logits` positionally against
`labels` and would mislabel every classifier prediction, silently.*

`base.py` writes nothing at
the run level and imports neither `schema.py` nor `registry.py`.
`train/utils/trainer.py` copies that list into its own `done.json`, under
`stage_extra`, when it finishes; `run.py` folds `done.json`'s `stage_extra` into
the run's `meta.json` on the same walk that writes the finish row (8.2, 8.3);
and `eval/utils/probe_eval.py` reads it from the train run's `meta.json`, which
exists by then because the walk writes it before it launches `eval`. One writer
per file at every step, and `meta.json` keeps the two login-machine writers it
has in 8.3. *The failure this prevents: eval reading `logits` positionally
against a `labels` list nobody owns, which mislabels every classifier prediction
silently. And a separate `label_map.json`, which would be a fifth on-disk file
with no owner (grounding F7).*

**Who writes.** `train/utils/trainer.py`, through the method file's `predict`
hook. **Who reads.** `eval/utils/probe_eval.py`.

## 1.4 Probe report — defined in `eval/utils/probe_eval.py`

The owner's instruction places this format on `eval/utils/probe_eval.py`, whose
tree line says "write the report". It is the fourth format across a stage
boundary and the one the reviews found had no owner (dependencies P3,
grounding F1, synthesis 5).

**One format, two files, one owner.** `probe_report.json` holds the scalars;
`fires.parquet` holds one row per event that fired. They are written together
by `probe_eval.write_report` and read together by `probe_eval.read_report`, and
neither is ever read by hand:

```python
def write_report(run_dir: Path, fields: dict, fires: DataFrame | None) -> None
def read_report(run_dir: Path) -> tuple[dict, DataFrame | None]
```

**`fields` is assembled by `probe_eval.run`, not by the method.** The method's
`report` hook returns only the numbers of its own shape (2.6), so `probe_eval.run`
merges them with the identity block it already holds — `version`, `method`,
`probe_kind`, `stage_key`, `train_key`, `theta_from`, `commit` (`cfg._commit`,
1.5) and the `labels` it read out of the train run's `meta.json` — and hands
`write_report` the whole dict. **`probe_eval.run` raises, naming the key, when
the method's returned dict carries any of those names**, which is what keeps a
method's own copy of `labels` out of the report. `write_report` writes what it is
given and computes nothing.

Both take the run directory, never a key: the json and `fires.parquet` are
always read and written together, and nothing else opens either file. `fires` is
None for a generator shape, which writes no second file, and `read_report`
returns None for the frame when the directory holds none. It is not a fifth format: it is one report that
does not fit in one file, the way a checkpoint is one thing in several files.

**`probe_report.json`** — `<eval run_dir>/probe_report.json`. Two shapes, one
per `PROBE_KIND` (Part 2.6) and **not** one per method name: the classifier
shape carries the fitted temperature and the theta chosen per risk target; the
generator shape carries exact-match numbers at a theta taken from a named
classifier report. `method` is recorded on the row, but nothing branches on it,
which is what keeps a fourth method off this file's edit list. Both shapes
carry one entry per value of `eval.risk`, so a number never depends on an
unstated choice of risk target.

| field | type | meaning |
|---|---|---|
| `version` | int | the format's `VERSION` |
| `method` | str | the method name, recorded; nothing branches on it |
| `probe_kind` | str | `classifier` or `generator`: which of the two shapes this file is |
| `stage_key` | str | this eval run's key |
| `train_key` | str | the train run whose predictions were read |
| `theta_from` | str | generator: the classifier **eval** key whose theta was used; null for a classifier |
| `commit` | str | the commit this eval run was launched at: `cfg._commit`, like every other recorded commit (1.1, 1.5), and never probed from git here |
| `labels` | list[str] \| null | classifier: the class order, copied from the train run's `meta.json` `stage_extra` **by `probe_eval.run`**, from the same value it hands the method's `report` hook as its `labels` argument (2.6) — never from the dict the method returned, which is refused if it carries the name (above); null for a generator, which has no head and therefore no `labels` (2.5) |
| `temperature` | float | classifier: the softmax temperature fitted on the val rows |
| `risk_targets` | list[float] | the risk targets swept, from `eval.risk` |
| `grid` | list[struct] | classifier: every theta on the sweep grid with its val numbers, for a person to read |
| `chosen` | dict[str, float \| null] | classifier: risk target (as a string) to the theta chosen on val; null when no theta on the grid meets the constraint |
| `frozen` | dict[str, struct] | classifier: risk target to the test numbers at that theta: `n`, `coverage`, `trig_acc`, `earliness`, `wrong_spec`, `ci` |
| `theta_used` | dict[str, float] | generator: risk target (as a string) to the theta taken from the referenced report — one entry per value of `eval.risk`, keyed exactly like `frozen` |
| `exact` | dict[str, struct] | generator: risk target to `tool_ok`, `params_all_ok`, `full_call_ok`, `n`, `ci` at that risk's `theta_used`, over the test rows |
| `n_events` | dict[str,int] | events per split |

**Which rows the generator numbers are computed on.** `exact` is computed over
the `fires.parquet` rows whose `split` is `test`, matching the classifier's
`frozen` block, and `n_events` keeps the per-split counts for a reader.
*The failure this prevents: `fires.parquet` carries rows for every split, so
without the split named two builders pick differently and the exact-match numbers
stop being comparable with the classifier's frozen block.*

**How a generator's three exact-match tiers are computed.** `tool_ok` has one
source per method. A `cgen` report takes all three tiers from
`match(pred, target, env)`, which returns `{tool_ok, params_all_ok,
full_call_ok}` (2.6), so its `tool_ok` is the generated call's own tool. A
`cparam` report generates arguments only, so its `tool_ok` is
`fires.label_pred == prediction.tool` — the classifier's fired label against the
true tool the prediction row carries (1.3) — its `params_all_ok` is what `match`
returns for the two whole calls its caller rebuilt under 2.6's rule, and its
`full_call_ok` is `tool_ok and params_all_ok`.
*The failure this prevents: with no true tool on
the prediction row a builder either raises on a column that does not exist,
invents a tool prefix, or reports `full_call_ok == params_all_ok`, which is a
wrong number with no error.*

**When the referenced `chosen` is null for a risk target** — no theta on the
grid met that risk's constraint — the generator shape writes `theta_used[risk]`
as null and `exact[risk]` as a struct whose `n` is `0` and whose three
exact-match fields and `ci` are null, so the column shape stays uniform and
`eval/method_table.py` branches on neither. The eval does **not** refuse: the
other risk targets are still reportable, `fires.parquet` simply holds no rows at
that risk, and `eval/method_table.py` prints the blank.

`theta_used` and `exact` are dictionaries for the same reason `chosen` and
`frozen` are: `eval.risk` is a list. *The failure this prevents: a generator
report carrying one exact-match number whose meaning depends on an unstated
choice of risk target, which `eval/method_table.py` then cannot line up against
the classifier's per-risk rows.*

The names `coverage`, `trig_acc`, `earliness`, `wrong_spec` and the three
exact-match tiers are today's (`legacy/pipeline/eval/eval_tool.py:251-258`,
`legacy/pipeline/eval/eval_causal_call.py:1-40`), so old numbers and new ones
are comparable without a translation table. `chosen` follows today's rule: the
theta with the largest coverage among those whose `trig_acc >= 1 - risk` and
whose coverage is above zero (`legacy/pipeline/eval/eval_tool.py:514-517`).
The confidence interval is a bootstrap resampled **by task**
(`legacy/pipeline/eval/eval_tool.py:279-296`), seeded by `eval.bootstrap_seed`.

**`fires.parquet`** — `<classifier eval run_dir>/fires.parquet`, written only by
the classifier shape.

| column | type | meaning |
|---|---|---|
| `risk` | f32 | the risk target this selection belongs to |
| `theta` | f32 | the theta frozen at that risk |
| `split` | str | the split the event is in |
| `event_id` | str | the event that fired |
| `example_id` | str | the first cut of that event whose score reached theta |
| `score` | f32 | that cut's score |
| `depth` | f32 | that cut's depth |
| `label_pred` | str | the class the score probe predicted at that cut |

`eval/methods/cgen.py` and `eval/methods/cparam.py` join their own prediction
rows to this table on `example_id` and report exact match over the joined rows.
*The failure this prevents: the first-crossing rule existing in three files, as
it does today — `legacy/pipeline/eval/eval_tool.py:236`,
`eval_causal_call.py:536-549` ("the filtering logic matches eval_tool line for
line") and `eval_causal_param.py:363-365`.* The rule is executed once, by the
file that owns theta, and everyone else joins.

**Who writes.** `eval/utils/probe_eval.py` writes both files, through
`write_report`, from the field dict `probe_eval.run` assembled around what the
method's `report` hook returned (above) — a classifier
shape returns the fired frame, a generator shape returns None (2.6). No method
file opens either file: `report`'s signature carries no run directory, and the
referenced report reaches it as a parameter. **Who reads.**
`probe_eval.run` (the referenced classifier report, through
`probe_eval.read_report`, which it hands the generator method as `ref`),
`run.py` (the temperature, to freeze into an inject run's settings, Part 5.4),
`eval/method_table.py`.

**The probe service does not read this file.** `run.py` resolves
`inject.probe_score` to its classifier eval run, reads the report, and freezes the
temperature into the inject run's `settings.yaml` under `_resolved`;
`jobs/launch.py` passes it to the probe service on its command line. That
removes the only edge that would make `models/` depend on an `eval/` output
(the dependency review's cycle C3) and makes a live run's calibration visible
in its own directory instead of hidden in another run's report.

## 1.5 The run directory's own files

Every stage run writes into one directory, named in Part 3. The file set is the
same for every stage, which is what lets `run.py ls` treat them uniformly.

| file | written by | content |
|---|---|---|
| `settings.yaml` | `run.py`, through `schema.freeze`, before the first piece starts | the resolved setting projected onto this stage — Part 3.4 fixes which sections and fields are written — plus the `_` block: `_stage`, `_key`, `_upstream` (the naming below), `_versions` (module -> int), `_debug`, `_commit` (the commit `jobs/launch.git_state` returned for this launch, rewritten on every launch of this stage, which is the one commit a piece may record, 1.1) and `_resolved` (values derived from an upstream report, Part 5.4). This is the truth the stage runs from; a piece is never told a setting name (lifecycle A2) |
| `settings_diff.yaml` | the same writer | only the fields that differ from the schema defaults: the human summary, and exactly what the key was computed over |
| `meta.json` | `run.py` and `jobs/launch.py`, through `jobs/registry.py` | Part 8.3 |
| `heartbeat/<piece>-<launch>.jsonl` | `jobs/registry.py`, called by the piece | one line per beat, one file per piece **incarnation**, one writer per file; Part 8.4 has the line format and resolves `<launch>` |
| `log/<piece>.txt` | the piece's tmux session | stdout and stderr; a `cpu` piece writes none, because `run.py` starts it in place and its output goes to the terminal that typed the command (2.3) |
| `dirty.patch` | `jobs/launch.py` | `git diff HEAD` when `--allow-dirty` was used; absent otherwise |
| `done.json` | the stage's own program for a one-process stage; `run.py` for `sample` and `inject` (Part 2.3) | `{stage, key, commit, finished_at, counts, versions, metrics, report}`, plus `pairs` for `sample` and `inject`, plus `stage_extra` for a stage that has one (`train` puts `labels` there, 1.3). `commit` is `cfg._commit`, read out of `settings.yaml` like every other frozen value and **never probed from git by the stage** (1.1) |
| `consumed.json` | `build`, `train` and `eval`, each for the upstream files it read | `[{path, sha1, n_rows}]`; the one record of what a stage read, and what `ls`'s `consumed` flag is computed from |
| `service_<kind>_<replica>.json` | that one service piece | one file per service piece, `kind` being `agent` or `probe` and `<replica>` the replica index within that kind (an agent piece's own replica number, `0` for the one probe piece — **not** the global piece index, so a loop piece can compute the name, 7.4): the endpoint (`base_url`, carrying the host the piece was placed on, 7.2), the pid, the resolved flags, the keyed columns the service claims to serve, and `attached_to` (Part 7.1) — **the `run_id` of the run that owns the server**, written when this piece attached to it rather than starting one |
| the stage's outputs | the stage | records, examples, predictions, checkpoints, reports |

Four of those entries need their reason on the page.

- **How `_upstream` is keyed, since three mechanisms read entries out of it by
  name.** A **same-setting** upstream is keyed by its stage name (`build`,
  `train`, `sample`, `inject`); a **reference** is keyed
  `<field>.<stage>`. So a `build` run's map is `{sample}`, a `train` run's is
  `{build}`, an `eval` run's is `{train}` plus `{theta_from.eval}` for a
  generator method, an `inject` run's is
  `{probe_score.train, probe_score.eval, probe_gen.train}`, and a `score` run's
  is `{inject, baseline.sample}` (or `{sample, baseline.sample}` under a
  `[sample, score]` workflow). The three readers are named where they are used:
  2.5's shared-build gates read the build key **of a referenced train run**,
  whose own map is stage-named — the inject-side gate out of that run's
  `settings.yaml` as `_upstream["build"]`, the generator-eval gate out of its
  `meta.json` as `upstream["build"]` (8.3's field name), two reads of one value; 7.2's `/health` comparison is against
  `_upstream["probe_score.train"]` and `_upstream["probe_gen.train"]`; and
  `jobs/launch.py` resolves `--score-ckpt` and `--gen-ckpt` from those same two
  entries. *The failure this prevents: keyed by stage name, an inject run's two
  train keys collide; keyed by field name alone, `probe_score` needs two entries
  under one name. Neither shape is writable, so a builder cannot write
  `agent/inject.py`'s refusal or the generator eval's build-key gate at all.*
- **`done.json` carries the stage's own numbers.** `metrics` is a flat
  `dict[str, float]` each stage writes for itself (train: the best validation
  objective; eval: coverage and accuracy at each risk; score: task success and
  tokens), and `report` is the report file's name inside the directory, or null
  when the stage writes none. The finish row (Part 8.2) copies both verbatim, so
  `run.py` never opens a report and no stage's report needs a second reader.
  *The failure this prevents: `run.py` parsing `run_report.json` and a train log
  by hand — a fifth and sixth cross-file format with no owner, which is the
  defect Part 1.4 was written to fix for the probe report.*
- **`done.json` for `sample` and `inject` carries `pairs`**: the resolved
  (task, seed) list the marker certifies, written by `run.py` when it writes the
  marker. Those two stages exclude the task and seed lists from their keys
  (Part 2.2), so one directory serves several requests and presence alone cannot
  mean done (Part 2.3). They are also the two stages whose marker the stage
  itself does not write, so the other four fields `write_done` requires (8.0)
  have their source stated here: `run.py` writes
  `counts: {records: <len(pairs)>, tasks: <distinct task ids>,
  seeds: <distinct seeds>}`, `metrics: {}` — their numbers are `score`'s —
  `report: null`, and `versions: cfg._versions`, read out of the frozen
  `settings.yaml`.
- **`consumed.json` has three writers, not one.** `build` records the record
  files and the split files it read, `train` the example parquet, `eval` the
  prediction parquet and any referenced report. Naming all three is what makes
  `ls`'s `consumed` flag cover the whole chain instead of its first link.

There is no `failed.json`. Failure is not a file: it is the verdict `ls`
computes from a directory with no `done.json`, no live session and a stale
heartbeat (Part 8.5). One less thing to write, and no way for a stale marker to
lie. There is no `RUNMETA.json` either: its content is `meta.json`'s
`launches` list (lifecycle B6).

## 1.6 The checkpoint layout

Not a format between two stages, but the one directory shape two files share
(`train/utils/trainer.py` writes it, `models/probe_models/base.py` reads and
writes it, `models/probe_models/service.py` loads it). It is today's layout
(`legacy/pipeline/train/train_causal_tool.py:518-536`) plus `last/`:

```
<train run_dir>/best/     the weights (or the LoRA adapter, merged on save), the tokenizer,
                          head.pt for ctool, meta.json {backbone alias, tuning, labels,
                          call_sep, param_only, max_len, train_key}
<train run_dir>/last/     the same, plus {step, epoch, commit, rng_state}, rewritten every
                          train.checkpoint_hours; commit is cfg._commit (1.5), which is
                          what 2.4's resume test compares against
```

`call_sep` and `param_only` are **the method's values, not `base.py`'s**: they
come from `train/methods/<m>.py`'s `CHECKPOINT_META` (2.6), which
`train/utils/trainer.py` hands to `base.py` as `save`'s `extra`, and `base.py`
merges into `best/meta.json` without reading its keys. The other four —
`backbone`, `tuning`, `max_len`, `train_key` — reach the same file the same way,
as `save`'s `meta`, the identity block `trainer.run` builds from
`cfg.models.probe`, `cfg.probe.tuning`, `cfg.train.max_len` and `cfg._key` (6.2).
*The failure this prevents: `base.py` has no channel to those four values
otherwise, so the cheapest guess is a module-level constant or a default of
`full` — which trains a full-weight probe for a LoRA setting, under the LoRA
key.*

**Neither `call_sep` nor `param_only` is ever read back by `base.py`.** They
reach the two places that use them as *arguments supplied by a caller that knows
the method*: a generator's `predict` hook passes its own
`CHECKPOINT_META["call_sep"]` to `Probe.generate` (6.2, 2.6), and
`models/probe_models/service.py` passes the value it read out of the gen
checkpoint's `best/meta.json` (7.2). *The failure this prevents: a per-method
flag living in a shared file, which is the branch on the method that 2.6 exists
to forbid, and a fourth generating method that cannot say what its separator is
without editing `base.py`. The failure the argument form prevents, which is the
one an earlier draft left open: on the training path there is no `best/meta.json`
to read — `predict` runs with the probe still on the card and `best/` is chosen by
the very validation metric that calls `Probe.generate` — so a separator taken from
a file has no source at all at the moment a generator first generates.*

`best/meta.json` is what the probe service echoes on `/health`, so a stale
service is caught by comparing keys rather than by hope.

## 1.7 The probe's input — `data/probe_input.py`

Not a format between two stages either, but the one *text* two layers must
build identically: `data/build_training_dataset.py` builds it offline, in the `any`
venv, to train on; `agent/inject.py` builds it live, in the environment's venv,
to fire on. A divergence between the two invalidates every live run and shows
up in no number. So the three functions are pinned here the way the four formats
are, and both callers call them and construct no probe text of their own.

**Offered functions.** All three are pure: every parameter is passed in, nothing
is read from a file, and nothing is a module constant.

```python
def cuts(thinking: str, min_think: int, max_cuts: int) -> list[int]
def cuts_live(thinking_so_far: str, min_think: int) -> list[int]
def assemble(task: str, history: list[tuple[str, str]],
             thinking_prefix: str, hist_rounds: int, probe_result_cap: int) -> str
```

`probe_result_cap` is **not** `Environment.RESULT_CAP`. The environment clips an
observation to `RESULT_CAP` (the class attribute of 4.1) when it writes it into
the record; `assemble` clips it again, to `build.probe_result_cap` (the setting
field of 5.2), for the probe's own text. Two clips at two places, an order of
magnitude apart, so they carry two names.

**There are two cut rules, not one, and they are two functions because they
cannot be one.** The offline caller has the whole thinking text; the live caller
has a growing prefix. Both live in this file, so the shared part is still written
once, but neither pretends to be the other.

- `cuts` is the **offline** enumeration, called by `data/build_training_dataset.py`. It
  returns character offsets into the finished `thinking`, in increasing order,
  taken at `m.end()` of each sentence match (today's rule,
  `legacy/pipeline/annotate/rules.py:38`), with a terminal cut at
  `len(thinking)` included. When there are more than `max_cuts`, the list is
  thinned evenly inside this function.
- `cuts_live` is the **streaming** enumeration, called by `agent/inject.py`. Its
  offsets are at `m.start()`, it adds no terminal cut, and it does no thinning.
  Each of those three differences is forced: even thinning needs the total cut
  count, which is unknown until the step ends, and today's live code says so in
  its own docstring (`legacy/pipeline/inject/live_appworld.py:178-186`: the
  thinned set "changes as the text grows, which under a live run would invalidate
  the set of already-probed cuts"); a terminal cut at the current length is a cut
  in the middle of a sentence the model is still writing; and `m.end()` under
  chunking counts one sentence end twice when `. ` arrives in one chunk and the
  following `\n` in the next, which shifts "the Nth cut"
  (`live_appworld.py:165-175`). The live cap is the caller counting the cuts it
  has already scored, which is what `inject.max_cuts` means (5.2), so
  `cuts_live` takes no `max_cuts`.
- **The `min_think` filter is per cut**, in both functions:
  a cut at offset `p` is kept when `len(thinking[:p].strip()) >= min_think // 2`.
  The event-level gate — the whole step has no cuts when
  `len(thinking) < min_think` — lives in `data/build_training_dataset.py`, because it is
  a decision about which events become example rows. **The live side holds the
  same gate in its streaming form**: `agent/inject.py` scores no cut until
  `len(thinking_so_far.strip()) >= min_think`, and a step whose thinking never
  reaches it therefore never fires, at no cost; `cuts_live` keeps its per-cut
  filter unchanged. *The failure this prevents: without it a live step under
  `min_think` is scored at every cut while every such event was dropped whole
  from the training set — the probe's input population differs between training
  and the live run, which is the divergence this whole section exists to close
  and which shows up in no number.*
- **`example.cut` and `spec.cut` are therefore not the same coordinate**, and
  neither this document nor any program compares them. Both files' README lines
  say so: an offline cut is an `m.end()` offset in a finished thinking text, a
  live cut is an `m.start()` offset in a prefix. What must agree between the two
  layers is the *text the probe is shown* at a cut, which is `assemble`'s job and
  is one function.
- `assemble` returns the probe's text. `history` is `(action, observation)`
  pairs in the order they happened, newest last; `assemble` keeps the last
  `hist_rounds` of them and clips each observation to `probe_result_cap`
  characters, so the clipping is also one rule. `thinking_prefix` is
  `thinking[:cut]`.
- **`history` is the pairs of the *earlier* steps of the same trajectory, never
  the step it is inside**: at a cut the current step has produced no action and
  no observation yet. The offline caller builds the list from the record's `gen`
  and `env` rows of the steps before this one; the live caller is handed the same
  list, accumulated across the trajectory by `agent/loop.py`, which appends
  `(observation.action, observation.observation)` after each `Environment.step`
  and passes it into `step` beside the `meta` row's `task_text` (7.3). That is
  the only difference between them: one list rebuilt from disk, one list carried
  in memory, with the same contents. *The failure this prevents, and it is the
  failure this whole section exists for: a live caller that passed the current
  step's pairs would pass an empty list at every cut, so the live probe reads a
  history of `(start)` while the trained probe read three tool rounds — the same
  text nowhere compared, every live number wrong, and no gate anywhere.*

**Where the parameters come from.** Always the frozen setting, never a
constant. The builder passes the `build` fields in `PROBE_TEXT_FIELDS` and
`cfg.build.max_cuts`; the live injector passes the same `PROBE_TEXT_FIELDS` —
which an inject setting **inherits** from the run its `inject.probe_score`
resolved to (Part 5.4) — to `cuts_live` and `assemble`, and counts its own scored
cuts against `cfg.inject.max_cuts`.

**`PROBE_TEXT_FIELDS` is the name of that set, declared once.**
`experimental_settings/schema.py` declares
`PROBE_TEXT_FIELDS = ("min_think", "hist_rounds", "probe_result_cap")` as a
module-level literal beside the stage table, and every rule about the set names
the tuple instead of listing its members: this section, 2.1's inject row and its
paragraph, 2.2's note, 3.3's third resolution, 5.4's inheritance rule and 5.7's
"an inherited section is not affected". *The failure this prevents: a fourth
parameter of the probe's text — a second thinning knob, a tail cap — is added to
`schema.py` under `build` with a default, and five separately written rules go on
naming three fields. The live run then uses the schema default while the probe
was trained on another value, the inject key does not move, and nothing anywhere
compares the two. That is the failure this whole section exists to prevent,
reintroduced through the extension path 0.4 calls free, which is why 0.4's
cut-rule row now names the tuple.*
*The failure this prevents: today the live injector and the builder import
`assemble`, `MIN_THINK` and `SENT_RE` from one module
(`legacy/pipeline/inject/live_appworld.py:77`,
`legacy/pipeline/annotate/rules.py:21-22`), where `HIST_ROUNDS` and
`RESULT_CAP` are module constants, so they cannot differ. Turning them into
settings breaks that tie; inheritance is what ties them back together, and the
inherited values enter the inject key, so a live run whose probe text differs
from its training text cannot share a directory with one whose does not.*

`VERSION` on this file covers all three functions, and it is the version whose
bump is the expensive one (Part 0.4).

---

# Part 2. The stage table

Six stages, the owner's six. No stage is added. Serving the agent model and
serving the probe are **pieces** of `sample` and `inject`, not stages: they
produce no output directory of their own, they carry `kind: service` in the
registry row, and they are torn down with the stage (lifecycle B8). The retired
offline replay line would have been a seventh and is a proposal in Part 9(b).

The table lives in `experimental_settings/schema.py` as a literal dictionary,
`STAGES`, whose values are strings, tuples and flat mappings of strings and
nothing else — 2.1 fixes the shape of each cell. `run.py` walks
it, `jobs/launch.py` reads the piece rule and the venv from it, and `key` reads
the "sections read" and "versions" rows. Because it is literal data, changing a
stage's inputs is an edit to one dictionary entry and nothing imports upward to
make it work (dependencies P1, synthesis 8).

## 2.1 Sections read, upstream, program, venv

| stage | sections read (the keyed part) | upstream, and how it is found | program (module, entry) | venv | cards |
|---|---|---|---|---|---|
| `sample` | `data`, `models.agent`, `generation`, `sample.{split, max_steps, store_token_ids}` | none | `agent.loop`, `main(run_dir, piece)` | the environment's, from `constants/path_datasets.yaml`; `vllm` and `probe` for its service pieces | yes |
| `build` | `data`, `build`, `sample.{split, tasks, n_tasks, seeds}` | `sample` of the same setting, by its key | `data.build_training_dataset`, `main(run_dir)` | any | no |
| `train` | `models.probe`, `probe`, `train` | `build` of the same setting, by its key | `train.methods.<probe.method>`, `main(run_dir)` | probe | yes |
| `eval` | `probe.method`, `eval` | `train` of the same setting; and when the method's `PROBE_KIND` is `generator`, the setting named by `eval.theta_from`, resolved to **its classifier eval key** | `eval.methods.<probe.method>`, `main(run_dir)` | any | no |
| `inject` | `data`, `models.agent`, `generation`, the inherited `build` fields in `PROBE_TEXT_FIELDS` (1.7), `inject.{split, max_steps, theta, format, arm, fire_nth_cut, max_inject_per_step, max_cuts, max_new, chunk_tokens, tail_tokens, store_token_ids}` | the setting named by `inject.probe_score`, resolved to **both its train(classifier) key** (the weights) **and its classifier eval key** (the temperature); the setting named by `inject.probe_gen`, resolved to **its train(generator) key** | `agent.loop`, `main(run_dir, piece)` | the environment's; `vllm` and `probe` for its service pieces | yes |
| `score` | `score`, and the `sample` or `inject` section's `{split, tasks, n_tasks, seeds}` | the `inject` run, or the `sample` run, of the same setting and workflow; and, when `score.baseline` is set, the setting it names, resolved to **its sample key** | `eval.score_run`, `main(run_dir)` | any | no |

**Two cells of that row are literal data, not prose, because two files read
them.** Part 2's opening says `STAGES` holds literal data only and that
`jobs/launch.py` reads the piece rule and the venv from it, so the two cells the
table above writes as sentences have a shape:

- **venv** is a string for a stage whose pieces share one interpreter — `"probe"`
  for `train`, `"any"` for `build`, `eval` and `score` — and a mapping from piece
  kind to venv name for a stage with service pieces:
  `{"loop": "env", "service_agent": "vllm", "service_probe": "probe"}` for
  `sample` and `inject`. `"env"` means the `venv:` column of this setting's
  `data.env` row in `constants/path_datasets.yaml`, and `"any"` resolves as 6.3
  says; every other value is a key of that file's `venvs:` map.
- **the piece rule** is a tuple of `(kind, count, mode)` entries, where `count` is
  an integer or the name of the setting field that gives it and `mode` is None or
  the flag `jobs/launch.py` puts on that piece's command line:
  `(("loop", "pieces", None), ("service_agent", "replicas", None),
  ("service_probe", 1, "render_only"))` for `sample`, the same with
  `("service_probe", 1, None)` for `inject`, `(("train", 1, None),)` for `train`,
  and `(("cpu", 1, None),)` for the three stages `run.py` starts in place (2.3).
  `kind` is the stage table's spelling; the piece entry's own `kind` field (8.1)
  is `loop`, `train`, `cpu` or `service`, both service spellings writing
  `service`.

*The failure this prevents: `run.py` walks the table and `jobs/launch.py`
dispatches on it, so a shape left to the builder is invented twice and agrees
by luck.* 2.3's piece-rule column is the same data in words.

A stage never recomputes an upstream key: `settings.yaml`'s `_upstream` map was
written at creation and the stage calls
`schema.run_dir_of(upstream_stage, key, debug=cfg._debug)` with the key it read
out of that map
(the by-key form of 3.1; `run_dir(stage, setting)` is the by-setting form and is
what `run.py` calls). *The failure this prevents: a YAML
edit between launch and run sending a piece to a different directory than the
one registered (lifecycle A2).*

**The "sections read" column is the keyed part, not everything the program
opens.** Three stages read a field at run time that is not in their key: `eval`
for a generator method, `train` for a generator method, and `score` all call
`open_env(cfg.data.env)` — the two eval-side callers to reach `split_args` and
`build_call`, the train-side caller because a generator method's `validate` hook
computes its metric with `eval/methods/<m>.py`'s `match(pred, target, env)` and
must hand it an environment (2.6). The files behind those three stages are five —
`eval/methods/cgen.py`, `eval/methods/cparam.py`, `train/methods/cgen.py`,
`train/methods/cparam.py` and `eval/score_run.py` — and 0.2 lists
`data/environments/__init__.py` among all five files' imports. `schema.freeze` writes `data` into those runs'
`settings.yaml` anyway, under the projection rule of 3.4, so the program finds
it; it enters no key of its own, because each of those stages already
carries its upstream's key, and that chain fixes `data` and the environment
file's `VERSION` (a train key folds the build key, which folds `data` and
`data/environments/<env>.py`; an eval key folds the train key; a score key folds
the scored run's key, which folds the same two). Writing them into the projection
is what makes them reachable; folding them again would change no directory.

`sample` and `inject` run the same program. `agent/loop.py` picks `inject.step`
over `generate.step` when the setting has an `inject` section, per the fourth
draft. The two stages differ in their key, their directory, and the `stage`
field of their records.

**A reference resolves to every stage key the referring field needs.**
`inject.probe_score` needs weights *and* calibration, so it resolves to two
keys; `inject.probe_gen` needs only weights, so it resolves to one. Every
resolved key is written into `_upstream` under the naming of 1.5, because that
is how the stage finds the directory it reads.

**Which of the resolved keys enters the referring key, and the one carve-out.**
All of them, except `inject.probe_score`'s **eval** key. What enters in its place
is the `VERSION` of the two modules that compute the one number a live run takes
from that report — `eval/utils/probe_eval.py` and the referenced setting's
`eval/methods/<m>.py` (2.2). That number is
`_resolved.probe_temperature` (1.4, 5.4) and it is the only one: theta is
`inject.theta`, a person's required field, and never comes from the report. The
temperature is fitted on the train run's val prediction rows by those two
modules and reads no `eval.` field at all, so folding the whole classifier eval
key would re-key every inject setting that references it whenever `eval.risk`,
`eval.theta_grid`, `eval.bootstrap` or `eval.bootstrap_seed` is edited — a full
live recollection that cannot change one byte of the live run — while folding the
train key and those two `VERSION`s moves the inject directory exactly when the
temperature can have moved. *Why not fold the temperature value itself, which
would be exact: `key` would then have to read a report out of the output tree,
which 3.2's purity guarantee forbids, and an inject key would stop being
computable before its eval run exists.*

**`inject` reads the `build` fields in `PROBE_TEXT_FIELDS` and never states
them.** `data/probe_input.py` builds the probe's text out of those fields, plus
the stage's own `max_cuts` (Part 1.7). An inject
setting **inherits** them from the run its `inject.probe_score` resolved
to (5.4); `schema.freeze` writes them into the inject run's `settings.yaml`, and
they enter the inject key as stated values, so a live run whose probe text is
shaped differently from its training text lands in a different directory.
*The failure this prevents, and it is silent: the live probe seeing a text built
with three history rounds when it was trained on one built with five.*

**`inject` reads no `models.probe` and no `probe` section.** The two probes are
named by `inject.probe_score` and `inject.probe_gen`, and their train keys —
already folded in — carry the backbone, the method and the tuning. A single
`models.probe` alias cannot name two probes when the score probe and the
generation probe sit on different backbones, and `probe.method` has no meaning
for a run that uses one classifier and one generator at once. The loader
therefore refuses a `probe:` section or a `models.probe` field in a setting
whose workflow contains `inject` (5.7). *The failure this prevents: an inject
YAML writing `probe: {tuning: lora}` and getting its own directory for
identical behaviour, and one writing a `models.probe` that contradicts its
referenced probes not being refused at all.*

## 2.2 What enters each key

Read with Part 3.3. "Sections" means the fields of those sections that differ
from their schema default.

| stage | plus | minus | module VERSIONs folded in |
|---|---|---|---|
| `sample` | — | `sample.{seeds, tasks, n_tasks, pieces, replicas}` | `agent/loop.py`, `agent/generate.py`, `data/trajectory_record.py`, `data/environments/__init__.py`, `data/environments/<env>.py`, `models/agent_models/<family>.py`, `models/agent_models/service.py`, `models/probe_models/service.py` |
| `build` | the sample key | — | `data/build_training_dataset.py`, `data/probe_input.py`, `data/training_data.py`, `data/trajectory_record.py`, `data/environments/__init__.py`, `data/environments/<env>.py` |
| `train` | the build key | — | `train/utils/trainer.py`, `train/methods/<m>.py`, `eval/methods/<m>.py`, `data/training_data.py`, `data/probe_output.py`, `models/probe_models/base.py`, `models/probe_models/<backbone>.py` |
| `eval` | the train key; for a generator method the resolved `eval.theta_from` eval key | — | `eval/utils/probe_eval.py`, `eval/methods/<m>.py`, `data/probe_output.py` |
| `inject` | the resolved probe_score **train** key and the resolved probe_gen train key (the probe_score **eval** key is in `_upstream` and not in the key, 2.1) | `inject.{seeds, tasks, n_tasks, pieces, replicas}` | `agent/loop.py`, `agent/generate.py`, `agent/inject.py`, `agent/inject_format.py`, `data/probe_input.py`, `data/trajectory_record.py`, `data/environments/__init__.py`, `data/environments/<env>.py`, `models/agent_models/<family>.py`, `models/agent_models/service.py`, `models/probe_models/base.py`, `models/probe_models/service.py`, and — standing in for the probe_score eval key — `eval/utils/probe_eval.py` and the referenced setting's `eval/methods/<m>.py` |
| `score` | the scored run's key; the resolved baseline key | — | `eval/score_run.py`, `data/trajectory_record.py` |

**Which column is authoritative.** The "sections read" column of 2.1 is the
list `key` consults; the "minus" column here only records *why* those five
fields are absent from it, for a reader who expects a whole section. The two
never disagree, because 2.1's entry for `sample` and `inject` is an explicit
field list that already excludes them. The inherited `build` fields an inject
run carries — the ones in `PROBE_TEXT_FIELDS`, 1.7 — are in that list and
therefore in the key like any stated value.

**Both services carry a `VERSION`, and it is folded in.** The agent client owns
the completion request body (`add_special_tokens`, `skip_special_tokens`, the
stop handling, the chunking of text against ids) and the probe service owns
`/score`'s softmax-at-temperature and `/encode`'s special-token direction — each
decides the bytes a run produces. `sample` folds both, because its prompt ids
come from the probe service's `/render`; `inject` folds both for the same reason
and for `/score`. *The failure this prevents: changing a request-body flag,
reusing the old key, and writing the new bytes into the old directory.*

Four further entries need their reason on the page.

- **`build`'s key does not contain `probe.method`.** One build serves all three
  methods, because the example row carries all three targets (Part 1.2). A
  fourth method reuses an existing dataset rather than rebuilding it.
- **`sample` and `inject` exclude the task and seed lists.** Their directories
  are collections of per-task files, so asking for three more seeds adds files
  to the same directory instead of recollecting the first three. The consumers
  (`build`, `score`) put the lists into their own keys and refuse to run until
  the records they name are there (2.5), so what a consumer consumed is
  still fixed by its key. *The failure this prevents: adding a fourth seed
  throwing away three seeds of collected trajectories, which is GPU days.*
- **`train` folds `eval/methods/<m>.py`'s VERSION.** The tree's own line for
  `eval/methods/` says the train method calls this file's match function for its
  validation metric, so a change to the match changes which checkpoint becomes
  `best/`. *The failure this prevents: an eval fix silently leaving a
  differently-selected checkpoint in place under an unchanged key
  (dependencies P2).* The price is real: an eval match fix reruns training. The
  structural fix that would remove it is Part 9(b)#9.
- **`eval`'s key contains nothing `train` reads, and `train`'s key contains
  nothing under `eval.`.** The prediction run's sizing lives in `train.predict`
  (lifecycle B2), so editing `eval.risk` never reruns a training.

## 2.3 Pieces, claiming, done, continue

| stage | piece rule | how a piece claims work | done marker, and who writes it | continue |
|---|---|---|---|---|
| `sample` | `sample.pieces` loop pieces (the environment's venv), `sample.replicas` agent-service pieces (vllm, cards), 1 probe-service piece in render-only mode (probe, **no card**, and therefore placed on `login_host` and outside 3.4's card search, Part 7.2) | the requested list is `requested_pairs(env, splits, tasks, n_tasks, seeds)` (below), whose elements are `(split, task_id, seed)` triples; each loop piece walks that list rotated by its own index (`ids[piece:] + ids[:piece]`, today's pool mode, `legacy/pipeline/inject/live_appworld.py:718-723`) and claims by `O_EXCL` create | every requested pair has a done record; **`run.py` on the login machine** writes `done.json`, with the `pairs` list it certifies, on its walk, and in the same step ends the run's service pieces (below) | done files are skipped; what is left is claimed. Claims are released only on the login machine, and a loop piece never deletes a file it does not own (Part 1.1) |
| `inject` | `inject.pieces` loop pieces, `inject.replicas` agent-service pieces, 1 probe-service piece with both probes (probe, 1 card); `jobs/launch.py` gates the loop pieces on that piece's `check` client (7.2), and a non-zero exit is a `service_check` outcome from `launch` (8.1) | the same exclusive-create claim | the same, `run.py`, services ended with it | the same |
| `build` | 1 process, in place, started by `run.py` itself (2.6's command shape, no tmux, the `any` interpreter of 6.3) | — | the program writes `done.json` as its last action | done: reuse. Partial: start over (minutes of CPU), writing through a temporary name and renaming |
| `train` | 1 piece on 1 card. Two cards are two sweep children, not two pieces; there is no multi-card training in this repo and none is contracted | — | the program writes `train_done.json` after the last optimizer step and `done.json` after the prediction rows | Part 2.4 |
| `eval`, `score` | 1 process, in place, started by `run.py` itself | — | the program writes `done.json`, rewritten every run | never skipped: these stages always recompute (Part 2.4) |

**Who starts a CPU stage.** `run.py` builds and starts the command for `build`,
`eval` and `score` itself, in place, with no tmux and no ssh, and appends their
start row (8.1). `jobs/launch.py` starts no process for them, so the `venvs:`
lookup for a stage whose venv column is `any` (6.3) happens in one file and not
two.

**A CPU stage passes the same two gates, under the same lock.** Before it starts
one, `run.py` takes `runs.jsonl.lock` and, inside that hold, runs the two gates
that live on `jobs/launch.py` — the dirty-tree refusal through
`launch.git_state(run_dir, allow_dirty)`, which writes `dirty.patch` into that
run directory under `--allow-dirty` and returns the five git fields of the start
row (2.5), and the
open-row refusal through `registry.open_runs()` (2.5) — writes the run's
`meta.json` and its `launches` entry through `registry.write_meta` exactly as
`jobs/launch.py` does for a tmux stage (8.3), and appends the start row; then it
releases the lock and starts the process. `run.py` already imports
`jobs/launch.py` and `jobs/registry.py`, so the dirty gate stays one function in
one file and the open-row gate stays one call.

**`run.py` closes the row it opened.** It holds the pid and waits for the exit,
so **on a non-zero exit it appends a `failed` finish row for that `run_id`
immediately** (8.2), inside a fresh hold of the same lock. *The failure this
prevents: without it the launch gate of 2.5 refuses that key for
`registry.DEFAULTS["launch_timeout_s"]` — half an hour — on the strength of a
start row nothing closes, although `run.py` watched the process die. It bites
hardest on exactly the loop a person runs while iterating on
`eval/methods/ctool.py`: an eval that raises locks its own key for
thirty minutes, and `run.py retry` does not escape it, because retry launches
normally.* *The failure this
prevents: `build`, `eval` and `score` write the numbers that reach `RESULTS.md`,
and without this they would have no dirty-tree refusal, no `dirty.patch` and no
producer for the five git fields of their start rows — CLAUDE.md's iron rule that
a recorded HEAD leads back to the code that ran would hold for three of six
stages — and two sessions could start one `build` in the same second, both
rewriting `examples.parquet`, `consumed.json` and `report.md` in one directory.*

**Why `run.py` writes `done.json` for the piece stages.** A piece cannot know it
is the last one without scanning the whole directory over NFS, and if a piece
writes the marker, the finish row has no owner (lifecycle A3). `run.py` on the
login machine folds the directory's state, writes `done.json` when the
completeness check passes, and appends the finish row — one owner for both.
A one-process stage is its own last piece and writes its own marker.

**What the requested (task, seed) list is, and who owns the rule.** Five files
need that list — `jobs/launch.py` (to refuse an out-of-split `tasks` id, below;
`meta.json`'s `split_files` it resolves with `env.tasks` instead, 8.3),
`agent/loop.py` (to walk its rotation,
since a loop piece reads no `meta.json`, 7.4), `data/build_training_dataset.py` (for
`read_dir(dir, pairs)` and its own key), `eval/score_run.py` (for
`read_dir(dir, pairs)` over the scored run and over its baseline, 2.5) and
`run.py` (for the subset skip test below and for the `pairs` list it writes into
`done.json`) — so the rule is one function,
`requested_pairs(env, splits, tasks, n_tasks, seeds) -> list[tuple[str, str, int]]`
in `data/environments/__init__.py`, which all five already import. Its semantics,
in this order: for each `s` in `splits` **in the given order**, take `env.tasks(s)`
**in the file's order**, apply `tasks` as a filter over it, and keep the first
`n_tasks` of what is left **of that split**; concatenate those per-split lists in
the given split order; cross with `seeds` in the given order. A `tasks` id that
is in none of the splits is refused by `jobs/launch.py`, naming the id and the
split files.

**It returns `(split, task_id, seed)` triples, and the projection to pairs is
stated once, here.** The four callers that want pairs — `run.py`'s subset test
and `done.json`'s `pairs`, `jobs/launch.py`'s claim release,
`data/build_training_dataset.py`'s and `eval/score_run.py`'s `read_dir(dir, pairs)` — drop
the first element, so `done_pairs` and `read_dir` keep the `(task_id, seed)`
signatures 1.1 gives them. The fifth caller, `agent/loop.py`, walks the triples
themselves and writes each record's `meta.split` from the one it is on (1.1).
*The failure this prevents: the split a task was requested under decides every
example row's `split` column, through the record's `meta.split` and
`env.SPLIT_ROLE` (2.5), and a pair list throws it away — so the loop's cheapest
guess is `cfg.sample.split[0]`, which stamps every record `train`, leaves `val`
and `test` empty, writes no prediction rows and fits a temperature on an empty
frame. That is exactly the failure 9(a)#44 and #47 were written to prevent,
reintroduced one layer down, and no gate catches it.*

**`n_tasks` is a cap per split, not a cap on the concatenation**, and that is
what makes `--debug` runnable on `train_probe.yaml`. `sample.split` defaults to
more than one split (5.2) and `build` assigns every example row's split from the
record it read (2.5), so a cap on the
concatenation takes `debug.yaml`'s three tasks off the head of the `train` file
alone, leaves `val` and `test` empty, makes `train.predict.splits` write no
prediction rows, and makes the ctool eval fit a temperature on an empty frame —
the debug walk dies at the last stage of the flagship workflow, against
principle 4 and 5.6's own purpose. Per split, `debug.yaml` stays sizes-only and a
`--debug` walk collects 3 train, 3 dev and 3 test tasks, the smallest dataset
that still has all three splits. 9(a)#47 records the choice.

**`run.py` calls it too**, on the setting it already holds in memory, which is
what makes the subset test below and `done.json`'s `pairs` the same list `build`
will demand; `meta.json`'s `split_files` keeps its hash and audit role (the
consumed/split gate below) and is not a second source for the list. *The failure
this prevents: the rule is silent on whether `n_tasks` is applied before or after
`tasks` and on what an out-of-split id does, so independent implementations can
disagree by one task — and reading the list back out of `meta.json` is worse than
a disagreement, because that file holds the **previous** launch's request: it is
absent on a first walk, and after the ordinary edit that scales a collection up
(`sample.tasks`, `sample.n_tasks` or `sample.split`) it makes the walk find every
previously requested pair done and skip `sample`, while `build`'s key does
contain those three fields — so the new build directory refuses forever with
"missing record" for a pair nothing will ever produce, which 1.1 already names as
the unrecoverable state.*

**The skip test for `sample` and `inject` is the pair check, never the presence
of `done.json`.** Those two keys exclude the task and seed lists, so one
directory serves several requests, and the walk asks: is the current requested
(task, seed) list a subset of the records that are done? If it is, the stage is
skipped. If it is not, the stage is relaunched for the missing pairs only — the
exclusive-create claim already leaves the finished files alone — and `done.json`
is rewritten with the wider `pairs` list when they finish. **The relaunch happens
only once no piece of `kind` `loop` or `train` of that run has a live session**,
and it reuses the run's live service pieces, exactly as `jobs/launch.refire` does
(1.1): while a work piece is live the
launch gate refuses the key (2.5), and what the walk does instead is 1.1's — release the
dead sessions' claims, report them, and leave the pieces stopped, with
`run.py refire` the way to restart one beside live siblings. *The failure this
prevents: asking for a fourth seed, finding the `done.json` written for three,
skipping `sample`, and then having `build` refuse forever with "missing
records", with no command in this document that unblocks it. That would take
away exactly the cheapness 9(a)#20 exists to buy.* Every other stage's skip test
is the presence of `done.json`, because its key fixes its whole request.

**A skip is also an ownership event.** Whichever of the two tests skips a
finished directory, `run.py` adds this `{workflow, setting}` to that directory's
`meta.json` `owners` list when it is absent, through `registry.write_meta`, under
the `runs.jsonl.lock` hold it already takes (8.3, 8.6). *The failure this
prevents: `owners` is the only record of who reached a directory (8.3) and a
skipped stage never launches, so the flagship sharing cases — six sweep children
over one `sample` and one `build` directory (9(c)#6), a second `train.lr` setting
reusing both (9(c)#5) — would list only the first child, and `ls` and `where`,
which print those names beside the path (3.4), would name one owner for a
directory five settings depend on.*

**A finished directory is skipped only when what it consumed is still on disk
unchanged.** Before skipping, the walk compares the directory's `consumed.json`
entries — and, for `sample` and `inject`, `meta.json`'s `split_files` hashes —
against the files they name. On a mismatch the walk **refuses**, names the file
and both hashes, and stops; `run.py retry <workflow> <setting> <stage>` rebuilds.
*The failure this prevents, and it is the one gap `key` cannot close: under
`split_source: env` every example row's `split` column traces back to the split
task-id files in `constants/` — they decide which split each task was collected
under, which the record's `meta.split` carries and `env.SPLIT_ROLE` maps (2.5) —
and they enter no key (6.3 concedes this). A person
edits a split file, reruns, `run.py` sees `build`'s `done.json` and skips it, and
train and eval proceed over a dataset whose splits no longer match the files on
disk.* This keeps `key` pure (3.2 rule 2) and turns `ls`'s `split` and
`consumed` flags from notices into gates: the same comparison that prints the
flag is the one that stops the walk.

**Which service a loop piece talks to.** Loop piece `i` uses agent replica
`i mod replicas` and finds both endpoint files itself, by the rule in Part 7.4.
With `replicas: 1` every loop piece talks to the one server, which is today's
arrangement.

**Dead piece and refire.** A piece is dead when its tmux session is gone and its
stage has no `done.json` (Part 8.5).
`run.py refire <workflow> <setting> <stage> [--piece i]` is the command; it
resolves the run directory and calls `jobs/launch.refire(run_dir, git, piece)`,
which **first probes that piece's tmux session on the host recorded in its `meta.json`
entry (8.3) and refuses, naming the session and the host, while it is alive** —
fail-closed, so a failed or timed-out ssh counts as alive (3.4) — and only then
restarts it. **A refire takes the same two launch steps a first launch takes, in
the same place**: `run.py refire` resolves and holds the setting (it already must,
to resolve the run directory), and inside the `runs.jsonl.lock` hold it calls
`jobs/launch.git_state(run_dir, allow_dirty)` — the same dirty refusal and the
same `dirty.patch` (2.5) — and then
`schema.freeze(setting, stage, run_dir, resolved, commit)`, which rewrites
`_commit` to the commit this launch cleared, before it hands the same git dict to
`jobs/launch.refire(run_dir, git, piece)` for that refire's `launches` entry
(8.3). `refire` then
reads that piece's frozen command from `meta.json`, deletes the
unfinished record files whose `meta` row names the dead session, probes the
cards again, and restarts the piece in a new tmux session, appending a launch
entry. *The failure the two steps prevent: 1.5 says
`_commit` is rewritten on every launch, 3.4 says a refire records the commit its
own launch gate cleared, and 8.3's `launches` entry carries `commit`, `branch`,
`dirty_count` and `dirty_files`, which only `git_state` produces — so a refire
without them runs the current working tree while every record it writes is
stamped with the original `_commit`, and no dirty gate is taken at all.* *The failure the liveness test prevents: `refire ... --piece 3` typed
against a piece `ls` called `slowed` or `suspected stall` rather than `dead`
deletes record files a live process is still writing and then starts a second
session under a name that is a function of stage, key and piece index (3.4).
Everywhere else in this document a claim is released only after a liveness test;
the one command that deletes claims on purpose gets the same one.* The live pieces are untouched and the service pieces are reused.
**There is no refire quota.** `run.py refire` **warns** when this piece already
has more than one entry in `meta.json.launches` — counted as the entries whose
`pieces` list contains this piece index — names those entries, and proceeds.
*The reason CONTEXT's one-automatic-refire-per-piece rule is retired with the
sampler (9(a)#13, #39): the quota existed to stop an automatic refirer from
looping, and the only refire left is a person's. Kept, it would refuse the very
person it was meant to escalate to — a loop piece killed twice by an unrelated
node event would leave the run un-advanceable, and `retry` does not help for
`sample` or `inject`, which delete markers and not records. The count was also
ambiguous, since one launch entry covers many pieces, so a relaunch after a kill
already consumed piece 3's quota.* `jobs/launch.py` has no
`__main__`: `run.py` is the one command (0.2, 8.6).

**Ending the service pieces.** `teardown_services` has two callers. `run.py`
calls it when it writes `done.json` for a piece stage, and
**`jobs/launch.launch` calls it before it returns any outcome other than `up`**
(8.1), so a launch whose alive check or `service_check` failed does not leave the
service pieces that did come up holding their cards. For each piece entry with
`kind: service`, `ssh <host> tmux kill-session -t <session>`, **skipped for a
service piece whose owning `run_id` appears in the `attached_to` field of another
live run's `service_<kind>_<replica>.json`** — `attached_to` carries a `run_id`
(7.1, 1.5), and this is the same test `run.py kill` already uses (8.6).
*The failure this prevents: on the normal path the loop pieces exit when the
requested pairs are done and nothing ever stops the vLLM server or the probe
service, so they hold their cards forever; the next stage of the same walk and
every sweep child then compete for cards that a finished `sample` run still
occupies, and `run.py free` reports them busy because `nvidia-smi` still sees the
process.* *The failure the second caller prevents: a `service_check` failure is
the ordinary failure path, not a corner — it is the expected outcome of the
`<|end|>` encode fixture on a new backbone (9(d)) — and it closes the run with a
`launch_failed` finish row, so that run never reaches the done marker the first
caller waits for and its vLLM server holds its cards for good; `run.py kill` is
no way out either, because the newest finish row wins (8.2) and `killed` would
overwrite the reason the launch failed.* A service piece the teardown skipped
this way is what `ls` flags as `orphan` (8.6).

## 2.4 The continue rule for `train`, `eval` and `score`

`train` has three markers, and each state has one answer (lifecycle A6, which
found today's one-marker rule undecidable — `best/` exists both after a
training that died at step 40 and after one that died in the prediction step):

| state on disk | action |
|---|---|
| `done.json` present | reuse; run nothing |
| `train_done.json` present, `predictions.parquet` absent | load `best/`, run the prediction step only, write predictions and `done.json` |
| `last/` present and its recorded `commit` equals this run's `cfg._commit` | resume from `last/step` |
| `last/` present and its `commit` differs from `cfg._commit` | refuse, and say so; `run.py retry` starts fresh |
| `train_log.jsonl` present and none of the above applies | refuse (today's rule, `legacy/pipeline/train/train_causal_share.py:1017`): mixing two runs' logs into one directory leaves no way to tell them apart; `run.py retry` clears the directory first |
| none of the above | start fresh |

**`--retry` is resolved on the login machine and never rides on the piece
command.** `run.py retry <workflow> <setting> <stage>` means "start fresh": it
deletes `last/`, `train_log.jsonl` and the markers and then launches normally.
The piece command keeps the shape 2.6 and 3.4 pin — `-m <module> --run-dir <dir>
[--piece <i>/<n>]` and nothing else — so the trainer's continue rule stays a pure
function of what is on disk, and `meta.json`'s frozen piece command cannot carry
a one-time flag into every later refire.

`eval` and `score` **always recompute** inside their key: a rerun overwrites its
own directory and the report carries the commit (lifecycle A7). They are still
keyed, and their keys fold their own module VERSIONs, so a change to *how* a
number is computed lands in a new directory and the old number stays
retrievable. *The failure this prevents: a metric fix that never runs because a
finished directory was reused.* They cost seconds, so nothing is lost.

## 2.5 The gates each stage holds

- `build` refuses unless every requested (task, seed) has a done record, and
  names the missing ones (lifecycle B9). *The failure this prevents: a build over
  a half-finished sample producing a smaller dataset that looks finished.*
- `build` reads **only** the records of the pairs in its own key
  (`read_dir(dir, pairs)`, Part 1.1), never everything in the directory. *The
  failure this prevents: two builds with different seed lists reading the same
  over-full directory and producing the same dataset.*
- `build` refuses when the share of records whose `final.abort` is non-null
  exceeds `build.max_abort_frac` (5.2). *The failure this prevents: a
  dataset built silently over a batch that mostly failed.*
- `build` holds these gates: **a row whose `call` does not re-parse to its `tool`
  and `args`**; a task id in two splits; a task in none of the environment's
  official lists; an empty `text`; a `depth` outside [0, 1]; a `text` whose
  thinking part is not a prefix of the record's thinking. A gate failure stops
  the build and names the rows. The first of them is a **new** hard stop, not
  today's behaviour: `legacy/pipeline/annotate/check_callstr.py:263,273,288,299`
  hard-stops on model contamination, key uniqueness, traj_runs shape, task-list
  membership and report wording, while the call-string round trip is its
  Deviation 1, which "only measures, does not fix"
  (`check_callstr.py:20-27,48-51`). It becomes a stop here because `build_call` is
  now the inverse of `split_args` (4.2), so a row that fails it is a defect in the
  environment file rather than a known loss. *The failure this prevents: a
  ground-truth `call` that eval's parser cannot read back is score
  `params_all_ok` can never earn, however right the generation was.*
- **A step whose `env.action` is null produces no example rows** and is counted in
  the build report's skipped-event count. Such a step has a `gen` row and a paired
  `env` row, so 1.1's raise does not fire, but `env.split_args` has nothing to
  parse, so the event has no `tool`, no `call` and no `args` — the targets of all
  three methods. A non-null `action` that `env.split_args` returns None for is a
  gate failure instead, and stops the build naming the record and the step.
  *The failure this prevents: 4.2 creates the null case on purpose (`action=None`
  when the model wrote no code block, which is what makes the loop send
  `NO_CODE_MESSAGE`), and the three ways out — skip the event, write a row with
  nulls, raise — give three different datasets under one key.*
- **A tool that appears in val or test and never in train is not a gate.** It is
  a line in `data/build_training_dataset.py`'s `report.md` and a count in
  `done.json`'s `counts`. *The reason it is not a refusal: it is an expected,
  documented condition — today's vocabulary is counted over the whole pile for
  exactly that reason (`legacy/pipeline/annotate/build.py:404`) and
  `check_callstr.py:58-61` lists such tools as a known deviation, not a block —
  and with `debug.yaml`'s three tasks per split it is near-certain, so as a gate
  it would refuse every `--debug` build of `train_probe.yaml` with no escape
  command anywhere in this document, against principle 4 and 9(c)#8.* What makes
  the class list sufficient instead is 1.3's rule: `head_labels` is computed over
  the whole example frame.
- **`build.max_examples` is a cap per split, applied after the split column is
  assigned**: `data/build_training_dataset.py` keeps the first `max_examples` rows of each
  split in `example_id` order, so the cap is a deterministic function of its
  input. *The failure this prevents: applied over the concatenated frame it takes
  the head of one split — which under `--debug` is the same empty `val` and `test`
  that 9(a)#44 and #47 were written to prevent, one field further down.*
- `build` writes `consumed.json`: every record file it read, with its sha1 and
  row count, **and every split file it read**, with its path, sha1 and task
  count. The split files are a result-changing input that lives in `constants/`
  (6.3): under `split_source: env` they assign every row's split, and two of the
  gates above consult them. *The failure this prevents: editing a split file,
  leaving the build key unchanged, changing every `split` column in
  `examples.parquet`, and having two different datasets share one key — which
  `schema.freeze`'s collision check cannot catch, because `settings.yaml` is
  identical.* `ls`'s `consumed` flag covers those entries, so a changed split
  file shows on the build directory the way a changed record file does.
- **How a row's `split` is assigned under `split_source: env`.** A record's
  `meta.split` already names the benchmark split its task was collected from
  (1.1), and `data/build_training_dataset.py` maps it through `env.SPLIT_ROLE` (4.1) to
  the `train` / `val` / `test` value it writes into the example row's `split`
  column — so the benchmark's `dev` becomes the role `val`, and no file assigns a
  split by re-reading a split file per row. *The failure this prevents: the
  benchmark's split names (5.3) and the example row's split values (1.2) are two
  name sets, and without the map they are never connected (4.1).*
- `train` runs the alignment gate before the first optimizer step, under
  `train.align_check` (5.2), and stops on a mismatch above `1e-4`.
- A generator method's `eval` refuses when the referenced classifier eval has no
  `done.json`.
- A generator method's `eval` refuses when the referenced classifier eval's
  train run has a different build key from its own train run's, and
  names both keys. `eval/utils/probe_eval.py` holds this gate and reads the two
  train runs' **`meta.json` `upstream["build"]`** entries (8.3's field name);
  the inject-side gate below reads the same value out of a `settings.yaml`'s
  `_upstream["build"]` (1.5), so the two are two reads of one value and not two
  spellings of one field. The join is on `example_id`, and ids are stable across runs
  by construction (Part 1's id rule), so without this gate a generator eval can
  reference a classifier eval built from a different cut rule, `max_cuts` or
  split, and the join partly succeeds on ids that mean different cuts. *The
  failure this prevents: a wrong exact-match number with no error anywhere.*
  This replaces a comparison of `labels`, which cannot be made: a generator
  train run has no classification head and therefore no `labels`.
- The same check holds across the two probes of a live run:
  `inject.probe_score` and `inject.probe_gen` are refused unless their two train
  runs share a `_upstream["build"]` key. It is also what makes the inherited
  `build` fields of 2.1 unambiguous — both references agree on them.
  **`run.py` holds this gate**, on the walk where it already resolves the
  references and reads the classifier report to freeze
  `_resolved.probe_temperature`: it opens each referenced train run's
  `settings.yaml` and compares their two `_upstream["build"]` entries.
- **`inject` refuses when the live code is not the code its probes were trained
  under**, and **`run.py` holds this gate too**, on the same walk. For each
  referenced train run it opens that run's `settings.yaml`, follows
  `_upstream["build"]` through `run_dir_of` to that build run's `settings.yaml`,
  and compares: the build run's recorded `_versions` entry for
  `data/probe_input.py`, and each train run's recorded `_versions` entries for
  `models/probe_models/base.py` and for **its own** backbone module, against the
  `VERSION` lines `schema.py` reads from the current source of those files
  (3.3's text rule). On a disagreement it names the module and both numbers.
  *Why the comparison is against the current source and not against this run's
  own `_versions`: an inject run has no backbone module of its own — 2.1 makes
  the loader refuse a `models.probe` field in any setting whose workflow contains
  `inject`, and 2.2's inject version list names only `base.py` on that side — and
  the two referenced probes may sit on two different backbones, so there is no
  single `models/probe_models/<backbone>.py` entry an inject run could name.*
  `run.py`'s `reads:` line already covers every run directory's `settings.yaml`,
  so the gate needs no new file, no new format and no new key entry.
  *The failure this prevents, and 1.7 exists to prevent it: editing the cut rule
  re-keys `build`, `train` and `eval`, and re-keys `inject` through
  `probe_input`'s own version — but the referenced probes' train keys were fixed
  when they were trained, so the inject run gets a fresh directory and loads
  probes built under the old cut rule, with nothing comparing the two. It is
  reachable with a pinned `key:` reference, or simply by editing
  `probe_input.py` after training.* All three values are already in each run's
  frozen `settings.yaml` (`_versions`, 1.5), so the gate needs no new file and no
  new format.
- A generator method's `eval` refuses when its own `eval.risk` list differs from
  the referenced classifier report's `risk_targets`, since its `theta_used` and
  `exact` are keyed by risk target against that report (Part 1.4).
- `score` refuses a baseline whose `data`, `models.agent` or `generation`
  sections differ from the run being scored — CONTEXT's same-setup rule,
  enforced by a program instead of by memory. **Where it reads the two sections**:
  a `score` run's own projection carries neither (3.4), so `eval/score_run.py`
  opens the two upstream runs' own `settings.yaml` — `run_dir_of` on
  `_upstream["inject"]` (or `_upstream["sample"]`) and on
  `_upstream["baseline.sample"]` — and compares the `data`, `models.agent` and
  `generation` sections every `sample` and `inject` projection carries (2.1).
- **`score` builds its own pair list and both of its record gates are stated
  over that list**, never over "every pair the directory holds":
  `eval/score_run.py` calls
  `requested_pairs(env, <the scored stage's splits>, tasks, n_tasks, seeds)` with
  the `inject` or `sample` fields of its own frozen projection (2.1 puts them in
  its key) and then `read_dir(dir, pairs)` with the `(task_id, seed)` projection
  of that list (2.3) on the scored run and on the baseline directory. *The failure this prevents: `sample` and `inject`
  exclude the task and seed lists from their keys (2.2), so one directory holds
  every request that ever shared the key, and a directory-wide gate would make a
  `score` run's numbers depend on collections it never asked for — while
  `data/trajectory_record.py` offers no directory-glob reader for it to use anyway
  (1.1).*
- `score` refuses unless the baseline run holds a done record for every
  (task, seed) **of that list**, and names the missing pairs. This is the
  record-level check that the baseline actually finished; the *setup* mistake it
  used to catch is now caught at load instead (5.7), because waiting for it costs
  GPU days. *The failure the pair of them prevents: a baseline collected over
  `sample.split: [train]` paired against an inject run over `inject.split: [test]`,
  which passes every other gate and then reports a comparison computed over an
  empty intersection.*
- **The dirty-tree gate and the git fields of a start row are one function,**
  `jobs/launch.git_state(run_dir, allow_dirty) -> dict`: it refuses a dirty tree
  without `--allow-dirty`, writes `<run_dir>/dirty.patch` when the flag is given
  — which is why it takes the run directory, since the patch is a run-directory
  file (1.5) and both callers would otherwise write it themselves — and returns
  `commit`, `branch`, `dirty`, `dirty_count` and `dirty_files` for the start row
  (8.1), fail-closed. `jobs/runs.jsonl`, `jobs/RESULTS.md` and `*.lock` never
  count as dirty (today's `LEDGER_PATHS` exemption,
  `legacy/ops/record.py:52-55`, which existed in three copies and now exists in
  one). **`run.py` is its one caller**, for all six stages: it calls it once
  inside the `runs.jsonl.lock` hold — before `schema.freeze`, which takes its
  `commit` (3.4, 8.6) — and hands the same dict to `jobs/launch.launch` as its
  `git` argument (0.2) for the five git fields of the start row (8.1), so the
  gate, the exemption and the probe exist once and cover all six stages.
  *The failure the single caller prevents: `freeze` runs for every stage and
  needs the commit for `_commit`, so `run.py` must probe git even for a tmux
  stage; a second probe inside `jobs/launch.py` lets the start row's `commit`,
  `branch`, `dirty_count` and `dirty_files` disagree with the `_commit` every
  piece and every `done.json` record, and writes `dirty.patch` twice.*
- **`jobs/launch.py` refuses to launch a key whose newest start row has no finish
  row and any one of three things holds**: a live session on its host in
  `meta.json`'s `pieces` entry, **counting only pieces whose `kind` is not
  `service`** — a service piece never exits on its own and is torn down with the
  run (2.3), so counting it would make this clause true for the whole life of an
  unfinished run and block the relaunch 1.1 and the skip test above depend on;
  a heartbeat younger than the stall line; or a
  start row younger than `registry.DEFAULTS["launch_timeout_s"]` (8.5). It prints
  the session name when there is one, and the `run_id` with the row's age for a
  `launching` row that has no session yet (lifecycle A4). **The third clause holds
  only while no piece of that row has been observed dead** — 8.5's `dead` verdict
  over that row's pieces — so the timeout covers a piece that has not appeared yet
  and not one that has already gone. *The failure this prevents: a run that dies
  inside its first half hour is refused for the rest of that half hour although
  nothing of it is alive, which blocks the documented recovery of 9(c)#3.* The read of
  `runs.jsonl`, this gate and the append of the start row all happen inside one
  hold of `runs.jsonl.lock` (8.6), so two `run.py` calls a second apart cannot
  both pass it. *The failure the disjunction prevents, which a conjunction of the
  three does not: 8.1 appends the start row inside the lock with
  `status: "launching"` and starts the tmux sessions only after the lock is
  released, so at the moment the second caller takes the lock there is a start
  row, no live session and no heartbeat at all — and a conjunction passes. A
  service piece emits no heartbeat ever (8.4) and a loop piece emits its first
  beat only after the environment package import, so "a fresh heartbeat" stays
  false for a freshly launched run for as long as startup takes. Under a
  conjunction the second sweep child of 9(c)#6 launches a second set of six loop
  pieces and a second vLLM server into the directory the first is using, and
  9(c)#9's second session does what that walk says cannot happen.* It is the same
  shape as the card reservation below, and 8.1's ageing rule and 9(c)#9's
  narrative already assume it.
- `jobs/launch.py` treats a card as busy when `nvidia-smi` shows a compute
  process on it **or** when it appears in the `pieces` list of a run that has a
  start row with no finish row **and** either a live session **or a
  start row younger than `registry.DEFAULTS["launch_timeout_s"]`** (8.5); the reservation is
  read inside the same lock hold as the launch gate. The `pieces` list it reads
  is `meta.json`'s (8.3), which a refire rewrites, not the start row's, which is
  append-only and may name a host the piece has since left. *The failure this prevents:
  `nvidia-smi` lists a compute process only once that process has allocated
  device memory, which is after the torch import and the model load, so six
  sweep children launched in one walk — or two `run.py` calls seconds apart —
  would each probe the cards the previous one was just given and be told they
  are free. The second clause covers the narrower window the ordering in 8.1
  opens: the start row is appended inside the lock and the tmux sessions are
  started after it is released, so for a moment a just-launched piece has a row
  and no session, and a live-session test alone would report its cards free.*
  The same `launch_timeout_s` is what turns a stuck `launching` row into
  `launch_failed` on the next `ls` (8.1).

## 2.6 How a stage program is called, and the method hook

Every stage program has the same shape:

```
<venv python> -m <module> --run-dir <dir> [--piece <i>/<n>]
```

with the repo root as the working directory and **no setting name anywhere on
the command line** (lifecycle A2). Somewhere behind that command,
`schema.load_frozen(run_dir) -> Setting` is called, which parses `settings.yaml`
against the dataclasses and neither re-merges nor re-resolves references. A YAML
edit after launch, or days later before a refire, therefore cannot move a running
process.

**Who calls it.** For `sample`, `inject`, `build` and `score`, the program is
the file that does the work and calls `load_frozen` itself. For `train` and
`eval` the program is a *method* file, and the two library entry points do it
instead:

```python
# train/utils/trainer.py
def run(run_dir: Path, method) -> None
# eval/utils/probe_eval.py
def run(run_dir: Path, method) -> None
```

A method file's `main(run_dir)` is one line — `trainer.run(run_dir,
sys.modules[__name__])` or `probe_eval.run(run_dir, sys.modules[__name__])` —
and the library does the rest: `load_frozen`, the heartbeat and `done.json`. It
hands the `Setting` down to every hook as `cfg`, which is how a method reaches a
field. **No method file imports `schema.py` or
`registry.py`**, which is what makes the six annotation lines in 0.2 true and
keeps `schema.py`'s importer count at ten.

**The method hook.** `train/methods/<m>.py` is the program;
`train/utils/trainer.py` is the library. The method module defines exactly
these names, and `trainer.py` calls them and never branches on the method:

| name | signature | what it must do |
|---|---|---|
| `VERSION` | `int` | bumped when this file's output changes meaning |
| `PROBE_KIND` | `"classifier"` or `"generator"` | tells `base.py` which head to attach, and it is the one thing anything else branches on: `schema.py` reads it out of this file's source text with the same regex it uses for `VERSION` (3.3), so the stage table gives every generator an upstream `eval.theta_from` (2.1), the loader requires that field of every generator (5.7), and the report has one shape per kind (1.4). Nothing anywhere branches on the method's name |
| `CHECKPOINT_META` | `dict[str, Any]` | the method-specific values that must survive into the checkpoint and reach the probe service — `call_sep` and `param_only` today (1.6). `trainer.py` hands it to `base.py`, which merges it into `best/meta.json` **without reading its keys**, so neither shared file branches on the method. A whole-call generator declares `param_only: false`, an argument-only one `true`, and that is what 5.7 refuses an `inject.probe_gen` on at load and what the probe service's `serve` refuses to start on (7.2). `call_sep` never reaches `Probe.generate` through this file either: the method passes its own value down (6.2) |
| `head_labels(df, cfg)` | `DataFrame, Setting -> list[str] \| None` | the class order this method's head needs, computed over the **whole** example frame, every split included: for `ctool`, the unique values of the `tool` column sorted ascending by name (1.3); `None` for a generator, which has no head. `trainer.run` calls it on the whole frame it already holds, **before** `base.load`, and passes `labels=<that list>, n_labels=len(<that list>)` (6.2), and both as None when the hook returns None; a resume reads the list back from `ckpt_dir/meta.json` instead of calling the hook. *Without this row nothing between the method file and `base.load` carries a class list, and the computation would have to move into `trainer.py` — a branch on the method, which this table forbids, and the silent mislabelling 1.3 exists to prevent.* |
| `batches(df, tok, cfg)` | `DataFrame, Tokenizer, Setting -> Iterator[Batch]` | the method's own batching or packing; `cgen` and `cparam` each carry their own, per the tree's "no shared packing". `Batch` is the dictionary type `models/probe_models/base.py` declares (6.2), which is where the split between the backbone's keys and the method's own is fixed — including `event_end`, the required key that names the token each event's decision is taken at, whatever this method's packing puts in the sequence (6.2) |
| `loss(probe, batch)` | `Probe, Batch -> Tensor` | the training loss |
| `validate(probe, df, tok, cfg)` | `... -> dict[str, float]` | the validation metric, computed with `eval/methods/<m>.py`'s `match(pred, target, env)`; a generator method obtains the environment with `open_env(cfg.data.env)`, which its frozen `settings.yaml` carries because 3.4 writes `data` into a generator train run's projection, and a classifier passes `None`. A generator's `validate` generates through `Probe.generate` and supplies its own `CHECKPOINT_META["call_sep"]` exactly as its `predict` hook does (below, 6.2). The key `objective` is the number `best/` is chosen on, lower is better |
| `predict(probe, df, tok, cfg)` | `... -> Iterator[dict]` | one prediction row per example row, carrying `example_id`, `method`, `target` and this method's own output columns of `data/probe_output.py`, which 1.3 lists per `PROBE_KIND`. It writes `target` itself because the derivation is the method's (`tool` for ctool, `call` for cgen, and for cparam the string derived from `call` and `tool`, 1.2), and it already holds the example frame as `df`. A generator's `predict` calls `Probe.generate(texts, max_new, call_sep)` and passes its **own** module's `CHECKPOINT_META["call_sep"]` (6.2, 1.6), which is what keeps the separator off `base.py` and reachable while the probe is still on the card and no checkpoint exists yet. `trainer.run` joins the five method-independent columns 1.3 names on `example_id`, and `data/probe_output.py`'s writer stamps `version`, so a method writes neither and `trainer.py` still branches on nothing |
| `reference_loss(probe, df)` | `Probe, DataFrame -> Tensor` | the same loss computed one example row per sequence, in its plainest form, over a slice of the same example-row frame `trainer.run` hands `batches`. The gate is executable because both sides are pinned: `trainer.run` takes the first `train.events_per_mb * train.accum` rows of the training split, calls `batches` on that slice, sums `loss` over the batches it yields, and compares that against `reference_loss` on the same slice, **both normalised per example row**; 2.5 stops training on a difference above `1e-4` |

`reference_loss` closes the gap the structure review found (its item 1): the
tree keeps the alignment gate and drops `train/utils/reference.py`, so the gate
would have nothing to compare against. Putting the plain loss in the method
file, beside the packed loss it checks, keeps the gate working without adding a
file. It is the one piece of code a method's author writes twice on purpose.

**The eval hook.** `eval/methods/<m>.py` is a program in the same way and the
direction of control is the same: **`probe_eval.run(run_dir, method)` is the
driver**, the method file's `main` is one line, and the method never calls back
into the run. The method module defines exactly these names, and
`probe_eval.py` calls them:

| name | signature | what it must do |
|---|---|---|
| `VERSION` | `int` | bumped when this file's numbers change meaning |
| `PROBE_KIND` | `"classifier"` or `"generator"` | the same value as the matching `train/methods/<m>.py`, declared here too and read the same way (below) |
| `match(pred, target, env)` | `str, str, Environment \| None -> bool \| dict[str, bool]` | the comparison, offered to `train/methods/<m>.py` for its validation metric. The caller supplies the environment: `report` has `cfg` and calls `open_env(cfg.data.env)`, and so does a generator method's `validate` (above). `ctool` compares class names and is passed `None`, which it ignores; `cgen` returns `{tool_ok, params_all_ok, full_call_ok}` after normalising both sides through `env.split_args` and `env.build_call`; `cparam` compares argument lists and is handed two **whole calls**: its two callers — `report` and `validate` — prepend `tool + "("` (from the `tool` column their frame carries, 1.2, 1.3) to the predicted and the target argument string before calling it, because an argument string alone cannot be parsed by `env.split_args` (1.4). One signature holds for every method, which is what lets `train/methods/<m>.py` call this function instead of keeping a copy |
| `report(pred_df, cfg, ref, labels)` | `DataFrame, Setting, tuple[dict, DataFrame \| None] \| None, list[str] \| None -> tuple[dict, DataFrame \| None]` | the whole shape-specific computation. Returns the fields of `probe_report.json` that belong to this method's `PROBE_KIND` (1.4's classifier block or generator block) and `fires.parquet` as a frame, or None when the shape writes no second file. `ref` is the **whole** `read_report(<the referenced eval run_dir>)` tuple — the json fields and `fires.parquet` — that `probe_eval.run` already loaded when `PROBE_KIND` is `generator`, and None for a classifier; a `dict` alone could not carry the frame the generator joins on `example_id`. `labels` is the class order `probe_eval.run` read out of the train run's `meta.json` (`stage_extra.labels`, already on its `reads:` line), and None for a generator, which has no head. *The failure `labels` prevents: fitting a softmax temperature needs the true class's position inside `logits`, which is positional in `labels` order, and the only other source on hand is the val/test rows' own `target` values — whose sorted uniques are not the trained order, because the order was computed over the whole example frame (`head_labels`, above), so any tool absent from val and test shifts every index and mislabels every prediction, silently (1.3).* |

For a classifier, `report` fits the temperature and theta on the val rows and
freezes on test, taking the true class's position inside `logits` from `labels`
and returning the fired rows; for a generator it joins its own prediction rows to
the `fires` frame of `ref` on `example_id` and returns None for the frame. Either
way the dict it returns holds the fields 1.4 gives that `PROBE_KIND`'s shape and
nothing else: `probe_eval.run` assembles the identity block of 1.4 around them,
and raises when the returned dict carries one of its names.

*The failure `match`'s third parameter prevents: a generator method's training
validation must normalise both sides the way its eval does, and with no
environment to hand it, a builder has three ways out and all of them are wrong —
hardcode `appworld`; compare raw strings, which silently changes which checkpoint
becomes `best/` and therefore the numbers under an unchanged key; or add an
import the tree's annotation lines do not carry and fail `selfcheck`. The
environment is reachable because 3.4 writes `data` into a generator train run's
projection alongside a generator `eval`'s and `score`'s (2.1).*

**Who owns what, on both sides.** The library owns everything that is not the
computation: `load_frozen`, the heartbeat, `consumed.json`, `write_report` and
`done.json` are all `probe_eval.run`'s, exactly as `trainer.run` owns them on the
train side. **Neither library writes a registry row**: the start row is appended
by `jobs/launch.py` for a tmux stage or by `run.py` for a CPU stage, before the
process starts, and the finish row by `run.py` on its next walk (8.1, 8.2).
*The failure this prevents: `train/utils/trainer.py` runs on a compute node, so
an `append_start` call inside `trainer.run` would both duplicate the start row of
every train run and take an `fcntl` append on an NFSv3 home file from a compute
node — which is exactly what 8.6 exists to forbid.* `probe_eval.run` also loads the
referenced classifier report and holds the 2.5 gates, because both need the
frozen setting the method never reads directly. The method file contributes
`match` and `report` and nothing else — which is what keeps "no method file
imports `schema.py` or `registry.py`" true on the eval side as well.

**`PROBE_KIND` is declared in both method files, and `selfcheck` compares
them.** The train file's declaration is the one `schema.py` reads for the stage
table and the loader (3.3); the eval file's is the one `probe_eval.run` reads off
the module it was handed, to pick the report shape, write the `probe_kind` field
(1.4) and decide whether to load a referenced report. The eval side cannot reach
the train file's copy: both run under `venv: any`, and importing
`train/methods/<m>.py` would pull torch, which principle 7 forbids. Two
declarations of one fact are safe only because `run.py selfcheck` fails when the
pair disagrees — and they are one more line each in files that already carry a
`VERSION` apiece.

---

# Part 3. `run_dir` and keys

## 3.1 The signature and where it lives

```python
def key(stage: str, setting: Setting) -> str          # 12 lowercase hex characters
def run_dir(stage: str, setting: Setting) -> Path
def run_dir_of(stage: str, key: str, *, debug: bool) -> Path   # for an upstream key read from settings.yaml
```

`run_dir_of`'s caller passes the `_debug` flag of its own frozen
`settings.yaml`. *The failure this prevents: 3.4 puts a debug run under
`<root>/<debug_subdir>/<stage>/<key>` and applies `--debug` to every stage of its
own workflow, so a debug `build` run's upstream `sample` directory is itself
under the debug subdirectory — and 3.2 rule 2 forbids probing the output tree to
find out which root a key lives under. Without the flag every debug walk past the
first stage resolves its upstream to a path that has never existed.* A **resolved
reference** is a different case and passes `debug=False`: a reference is always
keyed and located without the overlay (3.4), so a debug run points at real
upstream directories.

All three live in **`experimental_settings/schema.py`**, whose tree line
already says it holds "the stage table; and the loader that reads a YAML file
against it (file -> setting, diff, key)".

Why there and not in `jobs/registry.py`: every stage below `jobs/` has to find
its own directory and its upstream's (build finds sample, train finds build,
eval finds train, inject finds three). If `run_dir` lived in `jobs/`, then
`data/`, `train/` and `eval/` would import the top layer to resolve a path,
which is the inversion the dependency review objects to (its P8). In
`schema.py` the function sits beside the stage table and the key it needs, and
`schema.py` imports nothing from the repo, so the graph keeps pointing down.
`jobs/` imports `schema.py`, never the other way round.

The hash itself is implemented last, per the owner's instruction: until then
`key` raises `NotImplementedError` and only the signature, the inputs and the
guarantees below are fixed.

## 3.2 The guarantees

1. **Determinism.** The same stage and the same setting give the same path, on
   any machine, in any venv.
2. **Purity.** `key` reads the setting, the stage table, `models/table.yaml`,
   `constants/path_outputs.yaml`, `constants/path_datasets.yaml` (the `splits:`
   block, which 5.3's load-time validation needs) and the `VERSION` and literal
   lines of the modules in 3.3's literal rule. It **never touches the output
   tree**, so `run.py where`
   and a whole sweep's paths can be printed before anything has run, and a
   missing NFS mount cannot change a key.
3. **Sensitivity.** The path changes when, and only when: a field the stage
   reads changes value; an upstream key changes; one of the folded `VERSION`s
   changes; a `result:` column of a named model changes; `debug` is on.
4. **Insensitivity.** The path does not change when a field the stage does not
   read changes, when `notes` changes, when a `serving:` column changes, when a
   field is *added* to the schema with a default (3.3), or when code changes
   without a `VERSION` bump.
5. **A field set back to its default** gives the same path as never setting it.
6. **Debug separation.** A debug run never shares a directory, and never shares
   a tmux session name, with a real one.
7. **Sweep children** each get their own path, because each child is a full
   setting whose swept field has a different value.

## 3.3 What the key is computed over

```
key(stage, setting) = sha256(canonical_json({
    "stage":    stage,
    "fields":   {dotted field name: value, for every field the stage reads
                 whose value differs from the schema default, minus the stage
                 table's "minus" list},
    "models":   {role: that role's expanded row, for each model role the stage's
                 "sections read" column names (2.1)},
                # each row being {"role": ..., "family": ..., **the result block}
                # of that alias's table row (5.2)
    "upstream": {name: key, for each upstream the stage table gives, minus the
                 references 2.1 marks as not keyed},
    "versions": {module path: VERSION, for each module in the version list —
                 including the modules that stand in for a reference the line
                 above drops},
    "debug":    true | absent,
}))[:12]
```

- **The `models` entry follows 2.1's "sections read" column, exactly as `fields`
  does.** It is `{"agent": models.agent_row}` for `sample` and `inject`,
  `{"probe": models.probe_row}` for `train`, and `{}` for `build`, `eval` and
  `score`, which reach the two rows through their upstream keys. *The failure
  this prevents: `models.probe_row` is absent from a setting whose workflow
  contains `inject` (5.2, since 2.1 makes the loader refuse `models.probe`
  there), so an unconditional entry makes `key("inject", setting)` fail before
  any card is taken; and a `sample` key would move when the probe alias changed,
  recollecting GPU days of trajectories the probe never touched — against 3.2
  rules 3 and 4.*
- **The one upstream carve-out.** `inject.probe_score`'s **eval** key is not
  folded: it stays in `_upstream`, where it locates the report, and the
  `VERSION`s of `eval/utils/probe_eval.py` and of the referenced setting's
  `eval/methods/<m>.py` stand in for it in the `versions` entry. Every other
  resolved key the stage table gives is folded. Part 2.1 states the carve-out and
  why it is the only one, 2.2's inject row names the two stand-in modules.
- **Four resolutions happen before the diff is taken, in this order.** They are
  the exception to the rule in the next bullet, and a builder implementing `key`
  needs them written down: (1) the named agent and probe rows' `role`, `family`
  and `result:` block are expanded into the setting **whole**, not diffed, into
  the two fields `models.agent_row` and `models.probe_row` (5.2);
  (2) `generation.{stop, effort, date}`, when null, are resolved against the
  family module of `models.agent` (5.2) and then diffed against the *resolved*
  value the schema would give for that family, so a setting that states the
  family's own value keys identically to one that leaves it null;
  (3) an inject setting's inherited `build` fields — the ones in
  `PROBE_TEXT_FIELDS` (1.7, 2.1, 5.4) — are written in by the resolution and
  diffed like stated values; (4) `probe.lora_targets`, when null, is resolved
  against `LORA_TARGETS` in the backbone module of `models.probe` and then diffed
  against that same resolved value, so stating the backbone's own list keys
  identically to leaving it null. Everything else is diffed against the
  dataclass default. *The failure (4) prevents: 5.2 says null "takes the backbone
  file's list" and the literal rule below reads `LORA_TARGETS` for exactly that
  purpose, but with the resolution unlisted it is undefined whether the resolved
  list or `null` enters the train key, so two settings that mean the same LoRA
  targets may or may not key alike.*
- **The diff from the defaults, not the resolved values.** This is what makes
  "add a hyperparameter" free: a field added with a default that reproduces the
  old behaviour equals its default in every existing setting, so it is absent
  from every key and nothing reruns. It is also what the fourth draft's own
  `schema.py` line assumes ("a new hyperparameter, with a default that
  reproduces the old behavior"). The price is the rule the fourth draft already
  states: **changing an existing default, or removing a field, requires bumping
  the `VERSION` of the module that reads it**, and until `tests/` exists that
  rule is kept by hand. `settings_diff.yaml` in every run directory is the same
  `fields` dictionary, so what a key was computed over is always visible.
- **`notes` never enters.** Nor does anything under `constants/`, nor the
  `serving:` block of a model row, nor `_resolved` values derived from an
  upstream report, **nor any of the four reference fields of 5.4 —
  `eval.theta_from`, `inject.probe_score`, `inject.probe_gen`, `score.baseline` —
  whose resolved keys are already in the `upstream` entry** (the upstream's key is
  already in the key). *The failure this prevents: 2.1's "sections read" column
  names whole sections for `eval` and `score`, and `theta_from` and `baseline` are
  fields of those sections, so the reference's raw **text** would enter `fields`
  while the key it resolves to enters `upstream` — one fact keyed twice, in two
  spellings. The three reference syntaxes of 5.4 would then stop being
  interchangeable: converting `eval.theta_from: train_probe/ctool_q06` to the
  pinned `key: {eval: <hex>}` that 5.4 says survives an edit to the named setting
  would move the eval directory and force a rerun, and renaming a referenced
  setting that still resolves to the same key would move the score directory.
  `inject` escapes it only because 2.1 gives that stage an explicit field list.*
- **Versions are read as text.** `schema.py` gets a module's `VERSION` by
  matching the literal `VERSION = <int>` line in the module's source file with a
  regex. It does not import the module. This keeps the number in the file a
  person edits (synthesis 8), costs no import, and works from every venv —
  which matters because `eval/` must compute a train key to find its upstream
  and must never import `train/utils/trainer.py`, which needs torch.
  `run.py selfcheck` fails when a module the stage table names has no `VERSION`
  line, or has one that is not an integer literal.

  For that regex to be unambiguous, the line has a shape: **`VERSION` is
  assigned at module level, at column zero, exactly once per file, to an integer
  literal.** A class that wants it as an attribute writes `VERSION = VERSION`
  inside the class body, which is indented and therefore not a second match —
  that is how an environment file satisfies both this rule and Part 4.1's class
  attribute. `selfcheck` fails on zero matches and on more than one.
  `PROBE_KIND` in a `train/methods/<m>.py` and in the matching
  `eval/methods/<m>.py` is read the same way, at column zero, exactly once, as a
  string literal.

  **The same shape covers the seven module-level literals the loader resolves
  defaults from and validates against**, which is what lets `schema.py` compute a
  default without importing the layer that holds it: `STOP`, `DEFAULT_EFFORT`,
  `DEFAULT_DATE` and `EFFORTS` in a `models/agent_models/<family>.py`,
  `LORA_TARGETS` in a `models/probe_models/<backbone>.py`,
  `SPLIT_ROLE` in a `data/environments/<env>.py` (5.3 validates every element of
  `sample.split` / `inject.split` against its keys, and 4.1 assigns it at column
  zero for exactly that reason), and
  `CHECKPOINT_META` in a `train/methods/<m>.py` (5.7 refuses an
  `inject.probe_gen` whose method is not a whole-call generator by reading
  `CHECKPOINT_META["param_only"]` out of it). Each is assigned at module level, at
  column zero, exactly once, to a literal, and `schema.py` reads it with
  `ast.literal_eval` over the parsed source — never by importing, because a
  family module's `render_ids` needs `openai_harmony`, a backbone module needs
  `transformers` and a train method file needs torch, while the loader runs in
  every venv. An environment file's
  `INSTRUCTIONS` keys are read the same way, for 5.7's `data.instructions`
  refusal and for `selfcheck`'s cross-check (4.4), and its `SPLIT_ROLE` keys for
  5.3's split validation. `selfcheck` fails on zero
  matches and on more than one for each of these names, exactly as it does for
  `VERSION`. *The failure this prevents: 5.2 promises that a null
  `generation.stop` resolves against the family module and enters the key
  resolved, and 5.2 promises the same for `probe.lora_targets` against the
  backbone file; without this rule there is no stated path from either file to a
  loader that imports nothing, so the first file a builder writes cannot be
  written.*
- **Retired values.** `schema.py` keeps `RETIRED: set[tuple[str, str]]` of
  (axis, value). A retired value loads from a frozen `settings.yaml`, so an old
  run still reproduces, and is refused in a new setting. Values are never
  renamed (dependencies P6). *The failure this prevents: every old directory
  becoming unreachable because a value was spelled differently.*

## 3.4 The directory, and how a piece names it

```
<root>/<stage>/<key>/                 a real run
<root>/<debug_subdir>/<stage>/<key>/  a debug run
```

`<root>` and `<debug_subdir>` are two of the keys of
`constants/path_outputs.yaml` (6.3). There is no `outputs` symlink at the repo
root; `run.py where` prints the path.

The directory is named by the key alone, with no setting name in it, because
the same key can be reached from several settings — that is the whole point of
sharing a sample or a build — and two names for one directory would be two
directories. Who owns a directory is `meta.json`'s `owners` list (8.3), and `ls`
and `where` print the names beside the path.

`--debug` is applied **before** keying and adds `debug: true` to the key
(lifecycle B4), so a debug run can never be mistaken for a real one, can never
collide with a real run's tmux session name, and is never considered for reuse
by a non-debug walk. Its registry rows carry `debug: true` and `ls` hides them
unless asked.

`--debug` applies **only to the setting named on the command line and to the
stages of its own workflow**. A resolved reference is always keyed without the
debug overlay, so a debug run points at real upstream directories. *The failure
this prevents: `--debug` on an inject setting resolving `probe_score` to a debug
train key whose directory has never existed, and `run.py` refusing for a missing
`done.json` — a debug run that can never be made to run at all.*

A sweep expands at load into children named `<setting>/<field>=<value>,...`,
each a full setting with its own keys; 5.5 fixes how that name is spelled. A
child is addressable on the command line by it, so
`run.py where train_probe 'ctool_q17_lr/train.lr=0.0003,train.seed=67' train`
works and one child can be refired.

**Freezing.** At the moment a stage starts — every launch, not only the first —
`schema.freeze(setting, stage, run_dir, resolved, commit)` writes `settings.yaml`
and `settings_diff.yaml` (the
signature is in 5.1; `stage` is the stage `run.py` is walking, which decides every
section of the projection below; `resolved` is what `run.py` obtained from an
upstream report, `commit` is the `commit` field of the `jobs/launch.git_state`
call `run.py` makes inside the same lock hold just before, and the Setting is
never mutated). `freeze` writes that commit into the `_` block as `_commit`, which is
where 1.1 and 1.5 take every recorded commit from: no piece and no stage probes
git for itself, so a refire days later records the commit its own launch gate
cleared rather than whatever HEAD happens to be on the compute node.
**`freeze` writes both files through a
temporary name in the same directory and renames, and `run.py` calls it inside
the `runs.jsonl.lock` hold that carries the launch gate and the start-row
append**, so the two files are written under the same serialisation as the gate;
8.6 owns that hold and its nesting. *The failure this
prevents: `freeze` is otherwise the one run-directory writer with neither a lock
nor a rename, while 9(c)#6's six sweep children share one sample and one build
directory and 9(c)#9 has two sessions on one key — two processes rewriting one
`settings.yaml` outside any lock, possibly while a piece of the first run is
reading it.*

**`settings.yaml` is a stage projection, not the whole setting.** `freeze`
writes only what *this* stage reads at run time: the sections the stage table
names (2.1), that stage's own non-keyed request fields (`seeds`, `tasks`,
`n_tasks`, `pieces`, `replicas`), the fields it inherits (an inject run's
`PROBE_TEXT_FIELDS`, 1.7), the run-time-only fields 2.1 names (`data` for a
generator `eval`, for `score`, and for `train` of a generator method — the three
that call `open_env`), and the
`_stage` / `_key` / `_upstream` / `_versions` / `_debug` / `_commit` /
`_resolved` block.
*The failure this prevents: one directory is reachable from several settings on
purpose — `sample` and `inject` exclude the seed and task lists from their keys
(2.2, 9(a)#20), and `meta.json.owners` records several owning settings — so a
whole-setting file would make a shared `sample` directory assert one owner's
`probe.method` and `train.lr` while another owner contradicts them.*

**The collision check compares `settings_diff.yaml`, not the file.** `freeze`
refuses to overwrite an existing `settings_diff.yaml` whose content differs:
that is the keyed projection, so a difference there means two settings collided
on one key, which is a bug in `key`, and it fails loudly rather than quietly
running the wrong experiment. When the keyed projection matches, the non-keyed
request fields are **merged** instead, per field: `seeds` becomes the ordered
union of the two lists; `tasks` is `null` when either side is `null`, because
`null` means "no restriction" (5.2) and the wider request absorbs the narrower,
and otherwise the ordered union; `pieces` and `replicas` take the new launch's
values. `meta.json` gets a launch entry recording the wider request.
*The failure the `tasks` rule prevents: a naive union of `null` with `[t1, t2]`
is undefined, and writing `[t1, t2]` narrows the recorded request of a directory
whose earlier owner asked for the whole split and already collected it.* *The failure this prevents: 2.3's flagship path, "asking for
a fourth seed relaunches the stage for the missing pairs only", relaunches into
a directory whose `settings.yaml` says `seeds: [42]` while the new request says
`seeds: [42, 67]`; a whole-file comparison would call that legitimate wider
request a key collision, and would fire again on every refire onto a different
piece count.*

A piece command is then:

```
tmux new-session -d -s <stage>-<key>-<piece>
  cd <repo root> && CUDA_VISIBLE_DEVICES=<ids> <venv python> -m <module> \
      --run-dir <dir> --piece <i>/<n>
```

The `--piece <i>/<n>` element is present **only for a `sample` or `inject` loop
piece**: every other piece is one process of its stage, and 2.1's program column
gives `build`, `train`, `eval` and `score` a `main(run_dir)` that takes no such
flag (2.6, 8.4).

`<venv python>` is the absolute interpreter path looked up in
the `venvs:` map of `constants/path_datasets.yaml` (6.3) under the key the stage
table's venv column names — by `jobs/launch.py` for a tmux piece, by `run.py`
for a CPU stage it starts in place (2.3). A stage whose venv column is `any` is
launched with the interpreter 6.3 resolves `any` to.

**Cards reach a loop or train piece as an environment variable, not a flag.**
`jobs/launch.py` exports `CUDA_VISIBLE_DEVICES=<ids>` inside the tmux command
and records the ids in the piece entry. Only the two services take cards as
flags (`--gpus`, `--device`), because they are servers a person may also start
by hand. A loop piece gets no card of its own; the cards of a `sample` or
`inject` run belong to its service pieces.

**Hosts.** The login machine and the cluster inventory are the `login_host:` key
and the `hosts:` list of `constants/path_outputs.yaml`, whose shape and whose
reason for living there are in 6.3. `jobs/launch.py` starts a piece on another
host as `ssh -o BatchMode=yes <host> tmux new-session -d …`; `ls` and `free`
probe with one `ssh <host> tmux ls` and one `ssh <host> nvidia-smi` per host.
Every probe is fail-closed: a failed or timed-out ssh counts as **busy** for a
card and as **alive** for a session, so an unclear probe never frees a card and
never declares a piece dead (today's rule,
`legacy/ops/gpu_jobs.py:76-93`, `legacy/ops/launch_common.py:56-80`).
**All of that is reached over ssh from `login_host` and from nowhere else**:
`run.py` and `jobs/launch.py` refuse to run on any other host, naming it (8.6),
so a piece on another machine is always started by a process on the login
machine.

**Which host a piece lands on.** The rule is one paragraph, and `jobs/launch.py`
applies it inside the same lock hold as the card reservation (2.5, 8.6):

- an **agent-service** piece is placed on its table row's `serving.host` and
  nowhere else (6.1);
- an **agent-service** piece **the attach test of 7.4 matched to a live server**
  takes no card, enters no card search, and is placed on that server's host,
  exactly as the `--render-only` probe piece below is exempted. *The failure this
  prevents: the first run's vLLM server is a compute process on those cards, so
  2.5's busy test counts them busy and "a run whose required cards are not free on
  any host is refused" fires before `--attach-only` is ever passed to the service —
  making 7.1's whole attach branch unreachable and stopping a baseline `sample`
  run and an `inject` run that share one agent model from running at the same
  time, which is the case 7.1 spends a table verifying;*
- a **probe-service** piece **that loads a checkpoint** (1 card, the `inject`
  case) and a **train** piece (1 card) are placed on
  the first host in `constants/path_outputs.yaml`'s `hosts:` list with enough
  free cards under 2.5's busy test, **preferring the host this run's agent
  service is on**, so a live run's probe service and its vLLM server share a
  machine;
- a **probe-service** piece started with `--render-only` (the `sample` case,
  2.3) **takes no card**, enters no card search and is placed on `login_host`
  beside the loop pieces. *The failure this prevents: it is a CPU-only process
  (7.2), so reserving a card for it would hold a card it never uses from the
  start row onwards (2.5) and would let a `sample` run be refused for want of
  cards it will not take — 9(c)#1, which launches one vLLM piece, one
  render-only probe piece and six loop pieces, would stop being runnable on a
  busy cluster;*
- **loop** pieces take no card and run on `login_host`, as do the three CPU
  stages (2.3).

The chosen host is written into the piece entry's `host` field, in the start row
(8.1) and in `meta.json`'s `pieces` list (8.3); the second is the one `ls`,
`kill`, `refire` and the card reservation read, because a refire may relocate a
piece and rewrites that entry while the start row stands. A run whose required cards are not
free on any host is **refused**, naming every host probed and its free count.
*The failure this prevents: "pick free cards and ports" over four hosts is not a
rule, so `jobs/launch.py` cannot be written and a person cannot predict where
`run.py train_probe ctool_q06` puts a training run, or whether the probe service
lands on a different machine from the vLLM server it shares a run with.*

The tmux session name is the piece's identity everywhere: in the start row, in
`ls`, in the record's `owner_session`, and in `kill`. It contains the key, so
two sessions for one piece cannot coexist on one host, and
`jobs/launch.launch` refuses a key that is already running on any host in that
list (2.5's gate). `jobs/launch.refire` does not: it restarts one named piece
beside live siblings and holds its own per-piece liveness refusal instead (2.3).

---

# Part 4. The environment base class — `data/environments/__init__.py`

## 4.1 The class and the entrance

```python
VERSION: int                      # of the base contract itself, keyed (below)

@dataclass
class StepObservation:            # what step returns; 4.2
    action: str | None
    observation: str
    error_kind: str | None
    completed: bool

class Environment:
    """A benchmark that hands out tasks, steps, can try a call early and undo
    it, and judges."""

    NAME: str                     # the value on the data.env axis
    VERSION: int                  # of this environment's file
    INSTRUCTIONS: dict[str, str]  # variant name -> the developer message
    NO_CODE_MESSAGE: str          # what the agent is told when it wrote no call
    RESULT_CAP: int               # characters an observation is clipped to (4000 today)
    SEED: int                     # the environment's own seed (100 for AppWorld)
    SPLIT_ROLE: dict[str, str]    # this benchmark's split name -> train | val | test

def open_env(name: str) -> Environment
def requested_pairs(env: Environment, splits: list[str], tasks: list[str] | None,
                    n_tasks: int | None, seeds: list[int]
                    ) -> list[tuple[str, str, int]]   # (split, task_id, seed)
```

**`SPLIT_ROLE` is the map from the benchmark's own split names to the three roles
`example.split` uses.** AppWorld's is `{"train": "train", "dev": "val",
"test": "test"}`: its `splits:` block in `constants/path_datasets.yaml` is keyed
`train`, `dev`, `test` (5.3, 6.3) while an example row's `split` column is
`train`, `val`, `test` (1.2). Under `build.split_source: env`,
`data/build_training_dataset.py` takes each row's split from the record's `meta.split`
through this map (2.5, 6.3). *The failure this prevents: without it the two name
sets are simply never connected, so a `dev` task's example row has no defined
`split` value at all and every builder invents one.*

`open_env` imports `data/environments/<name>.py` inside the function with
`importlib`, checks that the nine methods exist and the seven class attributes
are set, and returns an instance. Nothing else in the repo imports an environment
module by name, so adding one adds no import anywhere.

`requested_pairs` is the one definition of which (task, seed) pairs a run asks
for; its five callers, its ordering rule — including `n_tasks` as a cap per
split — and the projection of its triples to pairs are in 2.3. It is a module-level
function beside `open_env`, not a method, because it is the same rule for every
environment and reads nothing but `env.tasks(s)` for each requested split.

**This file's `VERSION` is keyed.** It folds into `sample`, `build` and `inject`
beside each environment file's own (2.2). The choice between the two the reviews
offered is made here: the base file is not only a declaration any more — it holds
`requested_pairs`, whose ordering decides which trajectories are collected and
which records are built, and `open_env`'s method check — so a change to it can
change a result, and a version nothing keys would move nothing.

`VERSION` in an environment file is assigned at module level, at column zero
(3.3), and the class body writes `VERSION = VERSION`. **`INSTRUCTIONS` and
`SPLIT_ROLE` follow the same device, for the same reason**: each is assigned
under 3.3's literal rule in every `data/environments/<env>.py`, and the class
body writes `INSTRUCTIONS =
INSTRUCTIONS` and `SPLIT_ROLE = SPLIT_ROLE`, which are indented and therefore not
second matches. `env.INSTRUCTIONS[...]` and `env.SPLIT_ROLE` keep working for
4.2's callers, and the loader keeps its only path to both: it reads them out of
the source with `ast.literal_eval` for 5.7's
`data.instructions` refusal and 5.3's split validation. *The failure this prevents: declared only as
class attributes they are indented, so the loader finds nothing, 4.4's
cross-check finds nothing, and `selfcheck` fails on zero matches for a file that
follows this document.* No other class attribute changes. **Editing
`NO_CODE_MESSAGE`, `SEED` or `SPLIT_ROLE` is a `VERSION` bump**, exactly as
editing the call regex is: the first is text the agent is shown, so it changes
the trajectory; the second chooses which world the task runs in; and the third
decides which role every example row's `split` column gets. None of the three is
named by a setting field or by a keyed `models/table.yaml` column, so the bump is
the only thing that moves the key (4.4).

The fourth draft's line says "eight methods" and then lists nine. Nine is right
(dependencies P11, smaller item 1); the count on the line is a slip and the
class declares the nine names the line lists.

## 4.2 The nine methods

| method | signature | returns | one line |
|---|---|---|---|
| `tasks` | `tasks(split: str) -> list[str]` | task ids in the file's order | the split's task list, read from the file named in `constants/path_datasets.yaml`; never shuffled |
| `open` | `open(task_id: str, seed: int) -> None` | — | enter a fresh world for this task and seed, named so two seeds never share the benchmark's own output directory; **the benchmark package is imported inside this method** |
| `step` | `step(reply_text: str) -> StepObservation` | `{action, observation, error_kind, completed}` | extract this environment's action out of the model's reply (`action=None` when it wrote none, which is what makes the loop send `NO_CODE_MESSAGE`), run it, clip the observation to `RESULT_CAP`, classify the error, and report whether the task's completion API was called |
| `speculate` | `speculate(call: str) -> dict` | 4.3 | run a predicted call early and leave the world untouched |
| `judge` | `judge() -> dict` | the benchmark's evaluation dict | did the task succeed; the dict always has a boolean `success`. `agent/loop.py` writes the dict into `final.judge` as canonical JSON text and its `success` into the declared `final.success` column (1.1), so no reader parses the benchmark's own fields |
| `close` | `close() -> None` | — | leave the world and delete the per-task outputs (AppWorld leaves about 90 KB per task) |
| `split_args` | `split_args(text: str) -> tuple[str, list[tuple[str, str]], tuple[int, int]] \| None` | tool name, named arguments in call order, and the character span; or None | parse the environment's action text into a call; the call regex is the environment's (today `first_call_named` plus `split_args_named`, `legacy/pipeline/annotate/rules.py:118-164`) |
| `build_call` | `build_call(tool: str, args: list[tuple[str, str]]) -> str` | the normalised call string | the inverse of `split_args`, and the definition of `example.call`. **Inverse means round-trippable**: AppWorld's writes `tool(k=v, ...)` with a value quoted through `repr()` whenever it holds a top-level `,`, `=`, quote or bracket, because `split_args` splits on top-level commas and strips one layer of quotes on the way back (`legacy/pipeline/annotate/rules.py:118-147`). Today's `make_call` joins unquoted (`legacy/pipeline/annotate/build.py:197-200`) and therefore is **not** an inverse: `legacy/pipeline/annotate/check_callstr.py:20-27,48-51` measures the loss and names an AppWorld-shaped example, `echo(content=Finally, in that file, ...)`, and says it "only measures, does not fix". Here the round trip is a hard gate (2.5), so the quoting is part of this method |
| `complete_call` | `complete_call(text: str) -> str \| None` | a complete call, or None | finish a call the probe generated but cut off (an unbalanced parenthesis, a missing quote); None when it cannot be balanced |

**`step` owns two things a reader might expect in the loop: the extraction and
the completion signal.** `agent/loop.py` hands it the model's reply text, writes
the `env` row from the returned `StepObservation` (`action`, `result` from
`observation`, `error_kind`), sends `NO_CODE_MESSAGE` when `action` is None, and
stops the trajectory when `completed` is true, writing it into the `final` row.
*The failure this prevents: the record demands both — `env.action` is "the code
the model ran, or null when it wrote no code block" and `final.completed` is "the
agent called the environment's completion API" — and no other method produces
either. `split_args` parses *the environment's action text*, which is downstream
of the extraction, and `judge()` is the end-of-episode evaluation, not a
per-step query. So the ```python-block rule and the completion test would have no
home but `agent/loop.py`, and a benchmark whose action syntax or completion
signal differs would force an edit there — which 0.4's row and `agent/`'s own
tree line ("loop.py and generate.py change for neither") both forbid.*

`split_args` keeps the tree's name and does the whole parse, span included. A
rename to `parse_call` would be a change to a tree line and is Part 9(b)#14.

**Who calls what.**
`agent/loop.py`: `tasks`, `open`, `step`, `judge`, `close`, and the two text
attributes `INSTRUCTIONS[cfg.data.instructions]` and `NO_CODE_MESSAGE`.
`agent/inject.py`: `speculate`, `complete_call`, `build_call`, on the object the
loop passes it; it never opens a world of its own.
`data/build_training_dataset.py`: `tasks`, `split_args`, `build_call`.
`eval/methods/{cgen,cparam}.py`: `split_args` and `build_call` only;
`train/methods/{cgen,cparam}.py`: `open_env`, for the environment their
`validate` hook hands to `eval/methods/<m>.py`'s `match` (2.6); a classifier
method calls nothing here.
`eval/score_run.py`: the same two, plus the requested list below.
`jobs/launch.py`: `tasks`, to resolve the split files into `meta.json` before the
pieces start (8.3), and `requested_pairs`, to refuse an out-of-split `tasks` id.
`agent/loop.py`, `data/build_training_dataset.py`, `eval/score_run.py` and `run.py` reach
the requested list through `requested_pairs` as well — the five callers 2.3
names; `run.py` calls it on the
setting it holds in memory, which is what makes its skip test and `done.json`'s
`pairs` the list `build` will demand.
That is why the package import must sit inside `open` — otherwise build and
eval would run only in the AppWorld venv (dependencies P11).

## 4.3 What `speculate` must guarantee

The order is today's, from `legacy/pipeline/inject/exec_calls.py:16-17,564-570`
and its copy in `legacy/pipeline/inject/live_appworld.py:305-321`:

1. **Snapshot** the world under a fixed checkpoint name before anything runs.
2. **Make the call executable** — AppWorld requotes the generated arguments
   against the live shell's namespace and records which branch each argument
   took (`arg_modes`) — and **run it**, clipping the output to `RESULT_CAP`.
   An unparsable call is run and allowed to fail, never skipped: skipping would
   erase the cost of a wrong guess.
3. **Restore** the snapshot and **refreeze the clock** in a `finally`, then read
   the clock back and **raise when it moved**.

Returns
`{"exec_code": str, "arg_modes": list[str], "exec_out": str, "exec_ok": bool,
"error_kind": str | None, "spec_s": float}` — exactly the fields the record's
`spec` row needs, so `agent/inject.py` copies the dict in rather than
reassembling it.

The guarantee is CONTEXT's genuine world: after `speculate` the world is what it
was before. The deferred test named in the tree (a speculated call leaves the
world unchanged, per environment, in that environment's venv) is the check;
until it exists, the clock assertion is the check, and it is a hard stop, not a
warning.

## 4.4 Instruction text, variants, venv, version

The instruction text lives in the environment file, in `INSTRUCTIONS`, keyed by
variant name. The variant is chosen by the axis `data.instructions` (default
`v1`, today's AppWorld developer message,
`legacy/envs/collect/run_appworld.py:24-43`), whose allowed values are literals
in `schema.py` and are cross-checked by `selfcheck` against the keys of every
environment's `INSTRUCTIONS`. A prompt variant is therefore a YAML line that
enters the key by name, not a code edit guarded by a hand-kept version
(structure 8, applied without moving the folder). *The failure this prevents:
the value gyb varies most often being invisible to the key.*

`VERSION` on an environment file guards what is left: the benchmark package's
interface, the observation clipping, **the no-code message**, **the environment
seed**, **the split-role map**, the error classes, the call regex, and the
speculate three-step. It
folds into the keys of `sample`, `build` and `inject`. The three in bold are
there because they change results and nothing else covers them: `INSTRUCTIONS`
was lifted to an axis and `RESULT_CAP` is the observation clipping, but
`NO_CODE_MESSAGE`, `SEED` and `SPLIT_ROLE` would otherwise be edited with every
key standing still and every finished directory reused.

**Venv.** The file imports under `any` (module level is `re`, `pathlib`,
PyYAML); the benchmark package is imported inside `open`, `step`, `speculate`,
`judge` and `close`. The interpreter that runs a loop piece comes from the
`venv:` column of that environment's row in `constants/path_datasets.yaml`, read
by `jobs/launch.py` (dependencies P7). That column is a location and enters no
key.

---

# Part 5. The setting schema — `experimental_settings/schema.py`

## 5.1 What the file holds

Four things, in this order, and nothing else: the dataclasses (fields,
defaults, one-line comments), the axis literals, the stage table (`STAGES`) with
`PROBE_TEXT_FIELDS` beside it (1.7), and
the loader (`load`, `load_frozen`, `freeze`, `diff`, `key`, `run_dir`,
`run_dir_of`). It imports nothing from the repo.

Two of those signatures are not obvious and are fixed here; `key`, `run_dir` and
`run_dir_of` are in Part 3.1.

```python
def load(workflow_file: Path, setting_name: str, *,
         debug: bool, overrides: dict) -> list[Setting]
def load_frozen(run_dir: Path) -> Setting
def freeze(setting: Setting, stage: str, run_dir: Path, resolved: dict,
           commit: str) -> None
```

`load` returns a **list**, because a `sweep:` block expands into children (5.5):
one element when there is none, the children in name order when there is one.
That list is what `run.py`'s walk iterates. `freeze` takes the `stage` it is
freezing for, because everything it writes is stage-dependent — the projection's
sections, `_stage`, `_key`, `_upstream` and `_versions` (3.4) — and `run.py`
passes the stage it is walking, which it already holds, having just called
`key(stage, setting)` and `run_dir(stage, setting)`. *The failure this prevents:
the stage is otherwise recoverable only by parsing `run_dir.parent.name`, in two
path shapes, which is a rule a builder has to invent.* `freeze` takes `resolved` — the
values `run.py` obtained from an upstream report, today only
`probe_temperature` (5.4) — and writes them under `_resolved`, and it takes
`commit`, the git commit `jobs/launch.git_state` returned for this launch, and
writes it under `_commit` (3.4, 1.1), so a `Setting` is
never mutated after it is keyed and no stage probes git for itself.

**Two things about the parsed `Setting` that three files test for.**

- The file's top-level `workflow:` line — the stage list — lands on the Setting as
  `cfg._workflow: list[str]`, in the same `_`-prefixed family as `_stage`, `_key`
  and `_debug`, and is **not** written into `settings.yaml`, since a stage never
  needs it. `run.py` walks it, and the loader reads it for four of 5.7's refusals
  and for "a reference that resolves to a setting whose workflow does not provide
  the stage the table asks for" (5.4). *The failure this prevents: the start row's
  `workflow` field is the workflow **file's** name (8.1), so without a second name
  one word carries two meanings.*
- **A section the merged setting does not hold is `None` on the Setting**, and is
  omitted from `settings.yaml`. The presence tests named elsewhere are therefore
  `cfg.inject is None`: 0.2's "the inject section present -> `inject.step`,
  absent -> `generate.step`", 7.3's `system_text(cfg)` returning None when there
  is no `inject` section, and 2.1's `probe` section and `models.probe_row` being
  absent from a setting whose workflow contains `inject`. *The failure this
  prevents: default-constructed dataclasses make `cfg.inject` truthy in every
  setting, so every `sample` run takes `inject.step`.*

The reviews want it split three ways (synthesis 1); the tree forbids that, so
the mitigations are: axis values are literals, so there is no upward import;
versions are read as source text, so there is no cycle; and the README line
names all ten importers, so "who breaks when I edit this" is answerable from
the line.

Configuration loading is PyYAML plus dataclasses, per the owner's decision. No
OmegaConf: it is not installed, it needs `antlr4-python3-runtime`, and the one
feature this repo used it for — `${a.b}` interpolation — is replaced by the
reference syntax in 5.4.

A settings file is:

```yaml
workflow: [sample, build, train, eval]   # which stages this file's settings run
common: {...}                            # applied to every named setting in the file
<name>:                                  # one named setting; a new experiment is a new name
  meta: {notes: "...", override: [...]}  # optional; the section of 5.2
  <section>: {...}
  sweep: {...}                           # optional
```

`notes` and `override` are fields of the `meta` **section** (5.2) and are
written inside it, never at the setting's top level — the loader's "a key that
is not in the schema" refusal (5.7) makes the other spelling fail at the first
YAML file, and `meta.override` is how 5.4 names the permission.

## 5.2 The sections and their fields

"key" marks whether the field enters the key of the stage that reads it.
Reference fields are marked `ref` and explained in 5.4.

**`meta`**

| field | type | default | key | one line |
|---|---|---|---|---|
| `notes` | str | `""` | no | what this experiment is for |
| `override` | list[str] | `[]` | no | dotted field names this setting is allowed to state differently from the runs it references (5.4); it is a permission, not a value, so it changes no key |

**`data`** — which benchmark, and which prompt.

| field | type | default | key | one line |
|---|---|---|---|---|
| `env` | axis | `appworld` | yes | which benchmark environment |
| `instructions` | axis | `v1` | yes | which variant of the environment's developer message |

**`models`** — which models, by alias in `models/table.yaml`.

| field | type | default | key | one line |
|---|---|---|---|---|
| `agent` | alias | `gptoss120b` | yes | the agent model, an alias string and nothing else, so `models.agent(cfg.models.agent)` and the command-line override `models.agent=<alias>` (5.7) keep working |
| `probe` | alias | `qwen06` | yes | the probe backbone; likewise |
| `agent_row` | dict | — | yes, through 3.3's `models` entry and never as a field of the diff | **read-only, written by the loader**: the agent alias's table row expanded — exactly `{role, family, **the result block}` (6.1), so the field and what the key is computed over are the same object. The absolute weights path is **not** in it: `weights` is the alias, and the path is resolved at run time through `models.agent(alias)` from `constants/path_models.yaml`, which enters no key (3.3). This is where the expansion of 3.3's first pre-diff resolution lands and what `freeze` writes into `settings.yaml`, so every reader of the expanded row names one field: `schema.key`, `agent/loop.py`, `agent/inject.py` and `models/probe_models/service.py`'s `check` client all compare against `cfg.models.agent_row["family"]` (7.2, 9(a)#46). Every keyed column of a model row is read here, under the rule in 6.2 |
| `probe_row` | dict | — | the same | the same for the probe alias; absent from a setting whose workflow contains `inject`, which names no `models.probe` (2.1) |

**`generation`** — how the agent model generates. One path for sample and
inject (CONTEXT's same-setup rule).

| field | type | default | key | one line |
|---|---|---|---|---|
| `temperature` | float | `1.0` | yes | sampling temperature |
| `top_p` | float \| null | `null` | yes | only sent when set, so the request body is byte-identical when it is not |
| `max_step_tokens` | int | `8192` | yes | the per-step generation budget |
| `stop` | list[str] \| null | `null` | yes | stop strings; null takes the family module's `STOP` (`["<\|return\|>"]` for gpt-oss) |
| `effort` | axis \| null | `null` | yes | the family's reasoning tier, written into the model's own system message; null takes the family's `DEFAULT_EFFORT` (`high` for gpt-oss) and stays absent for a family that has no tiers |
| `date` | str \| null | `null` | yes | the date pinned into that system message, so a rerun on another day renders the same prefix; null takes the family's `DEFAULT_DATE` (`2026-08-06` for gpt-oss); passed to the server as `VLLM_SYSTEM_START_DATE` (Part 6.1) |

The last three default to null rather than to a value because all three values
are gpt-oss's, not every family's: `<|return|>` is a harmony control token, and
a family with no reasoning tier has no `effort` and no pinned date at all. A
second family would otherwise inherit them silently, and the stop string in
particular would make the client send a token the new family never emits — a run
that is wrong rather than one that fails. The loader resolves null against the
family module of `models.agent` (Part 6.2) and writes the **resolved** value
into `settings.yaml`, so it is what enters the key and what a person reads back.

**`sample`** — running the agent alone.

| field | type | default | key | one line |
|---|---|---|---|---|
| `split` | list[axis] | `[train, dev, test]` | yes | which task splits to run, concatenated in the given order by `requested_pairs` (2.3). It is a **list** because one `sample` run has to cover every split the dataset below it needs: `build` assigns each example row's split from the record it read (2.5), so a single-split collection leaves `val` and `test` empty and `train.predict.splits` writes no prediction rows at all |
| `seeds` | list[int] | `[42]` | no | one task run per seed; the seed goes into the request body and the record |
| `tasks` | list[str] \| null | `null` | no | restrict to these task ids |
| `n_tasks` | int \| null | `null` | no | cap on tasks **per split** (2.3); null is the whole split |
| `max_steps` | int | `30` | yes | steps before the run is cut off |
| `store_token_ids` | bool | `false` | yes | keep the generated token ids in the record |
| `pieces` | int | `6` | no | how many loop processes |
| `replicas` | int | `1` | no | how many agent servers |

**`build`** — records to examples.

| field | type | default | key | one line |
|---|---|---|---|---|
| `max_cuts` | int | `64` | yes | cuts kept per event, thinned evenly when there are more |
| `min_think` | int | `40` | yes | characters of thinking below which a step has no cuts |
| `hist_rounds` | int | `3` | yes | tool rounds kept in the probe's text |
| `probe_result_cap` | int | `400` | yes | characters per environment result **inside the probe's text**; not `Environment.RESULT_CAP`, the clip the environment applies when it writes an observation into the record (1.7, 4.1) |
| `weight_mode` | axis | `uniform` | yes | `uniform` (weight 1 per cut) or `per_event` (1/n, the old convention) |
| `split_source` | axis | `env` | yes | `env` = the benchmark's official task lists; `hash` = `int(sha1(task_id.encode()).hexdigest()[:8], 16) / 2**32` compared against the cumulative `split_ratio` — never Python's `hash()`, which is salted per process and would give a different assignment on every build while the build key stood still |
| `split_ratio` | list[float] | `[0.8, 0.1, 0.1]` | yes | train/val/test shares, used only under `hash` |
| `max_examples` | int \| null | `null` | yes | cap on examples **per split**, like `sample.n_tasks` and `train.predict.cap`, taken after the split column is assigned (2.5); null is no cap; for `--debug` |
| `max_abort_frac` | float | `0.02` | yes | refuse to build when a larger share of records aborted |

**`probe`** — what the probe is.

| field | type | default | key | one line |
|---|---|---|---|---|
| `method` | axis | `ctool` | yes | which probe method this run trains and evaluates (5.3 lists the values) |
| `tuning` | axis | `full` | yes | how the backbone is tuned (5.3) |
| `lora_r` | int | `16` | yes | LoRA rank, read under `lora` |
| `lora_alpha` | int | `32` | yes | LoRA alpha |
| `lora_dropout` | float | `0.05` | yes | LoRA dropout |
| `lora_targets` | list[str] \| null | `null` | yes | null takes the backbone file's list |

**`train`**

| field | type | default | key | one line |
|---|---|---|---|---|
| `lr` | float | `1.0e-5` | yes | learning rate (a LoRA setting writes `5.0e-4` in its YAML) |
| `epochs` | int | `1` | yes | passes over the training split |
| `warmup_ratio` | float | `0.0` | yes | share of steps spent warming the schedule |
| `seed` | int | `42` | yes | seeds the init, the shuffle and the dropout |
| `max_len` | int | `8192` | yes | tokens per event; a longer event is dropped whole |
| `events_per_mb` | int | `4` | yes | events in one logical minibatch |
| `accum` | int | `2` | yes | logical minibatches per optimizer step |
| `grad_ckpt` | bool | `false` | yes | gradient checkpointing; kept in the key because it changes kernels |
| `max_steps` | int \| null | `null` | yes | stop early; for `--debug` |
| `align_check` | bool | `true` | yes | run the packed-versus-plain loss gate before training |
| `checkpoint_hours` | float | `2.0` | no | how often `last/` is written |
| `predict.splits` | list[str] | `["val","test"]` | yes | which splits get prediction rows |
| `predict.cap` | int \| null | `null` | yes | rows per split; for `--debug` |
| `predict.max_new` | int | `96` | yes | generation budget per row for cgen and cparam |

**`eval`**

| field | type | default | key | one line |
|---|---|---|---|---|
| `risk` | list[float] | `[0.10, 0.05]` | yes | the wrong-fire rates theta is frozen at |
| `theta_grid` | list[float] | `0.500..0.975 step 0.025` | yes | the thetas swept on val |
| `bootstrap` | int | `1000` | yes | resamples for the interval, grouped by task |
| `bootstrap_seed` | int | `42` | yes | seeds the resampling |
| `theta_from` | ref | `null` | yes, through 3.3's upstream entry and never as a field of the diff | required when the method's `PROBE_KIND` is `generator`: the classifier setting whose frozen theta selects the fired rows |

**`inject`** — the live run.

| field | type | default | key | one line |
|---|---|---|---|---|
| `split` | list[axis] | `[test]` | yes | which task splits to run, concatenated in the given order (2.3); a live run normally asks for one |
| `seeds` | list[int] | `[42]` | no | one task run per seed |
| `tasks` | list[str] \| null | `null` | no | restrict to these task ids |
| `n_tasks` | int \| null | `null` | no | cap on tasks **per split** (2.3); null is the whole split |
| `max_steps` | int | `30` | yes | steps before the run is cut off |
| `probe_score` | ref | required | yes, through 3.3's upstream entry and never as a field of the diff | the setting whose ctool probe decides when to fire |
| `probe_gen` | ref | required | yes, through 3.3's upstream entry and never as a field of the diff | the setting whose probe writes the whole call — a generating method whose `CHECKPOINT_META` says `param_only: false` (2.6), `cgen` today. A method that generates arguments only cannot serve this side, and 5.7 refuses it; a fourth generating method states which side it can serve in that same literal |
| `theta` | float | required | yes | the confidence threshold; CONTEXT: theta is always given by a person, and startup is refused without it |
| `arm` | axis | `probe` | yes | which control arm (5.3): `no_probe` is the machinery wired and never firing, `probe_nofill` fires and injects nothing |
| `format` | axis | `p1_e1` | yes | how an early result is written into the stream |
| `fire_nth_cut` | int | `0` | yes | fire at the n-th cut instead of by score; 0 = by score |
| `max_inject_per_step` | int | `1` | yes | injections allowed per step |
| `max_cuts` | int | `64` | yes | cuts scored per step |
| `max_new` | int | `96` | yes | the probe's generation budget per fire, sent on every `/gen` request (7.2); the live counterpart of `train.predict.max_new`, which an inject setting cannot hold because it states no `train` section (5.7) |
| `chunk_tokens` | int | `64` | yes | tokens per streaming segment between probe calls |
| `tail_tokens` | int | `1024` | yes | segment size once probing has stopped |
| `store_token_ids` | bool | `true` | yes | keep the generated and discarded token ids in the record |
| `pieces` | int | `6` | no | how many loop processes |
| `replicas` | int | `1` | no | how many agent servers |

The control arms are one axis, not a set of booleans: `arm` has three values and
carries the arm's whole identity, which is what CONTEXT already calls them
(`arm="probe"`, `arm="no_probe"`). The loader refuses `fire_nth_cut` above zero
under `arm: no_probe`, because that arm never fires. *The failure this prevents:
four independent flags that can be set to contradict each other, with the arm's
identity spread over four fields of the key and of the record's meta row.*

**`score`**

| field | type | default | key | one line |
|---|---|---|---|---|
| `baseline` | ref | `null` | yes, through 3.3's upstream entry and never as a field of the diff | the run to pair against, task by task and seed by seed; `null` means report this run's own numbers only |
| `by_seed` | bool | `true` | yes | report mean and spread across seeds |

`score.baseline` is **not** a required field. `null` means report this run's own
numbers only, which is exactly what `baseline.yaml` does — its workflow is
`[sample, score]` and the setting it would name is itself. A setting whose
workflow contains `inject` must name one, and `eval/score_run.py` refuses to
write a paired report without it.

There is no `logging` section: the third draft's optional MLflow tracker is
dropped with the sampler (Part 9(a)#13).

## 5.3 The axes, and where each value's code lives

| axis | values today | the code behind a value | selfcheck compares against |
|---|---|---|---|
| `data.env` | `appworld` | `data/environments/<value>.py` | the file names under `data/environments/` |
| `data.instructions` | `v1` | a key of that environment's `INSTRUCTIONS` | every environment's `INSTRUCTIONS` keys |
| `sample.split`, `inject.split` (each element of the list, 5.2) | `train`, `dev`, `test` | a key of the environment's `splits:` block in `constants/path_datasets.yaml`, and a key of its `SPLIT_ROLE` map (4.1) | the union of every environment's split keys |
| `generation.effort` | `high`, `medium`, `low` | a branch in `models/agent_models/gptoss.py`, declared in that file's `EFFORTS` literal | the union of every family module's `EFFORTS` |
| `probe.method` | `ctool`, `cgen`, `cparam` | `train/methods/<value>.py` and `eval/methods/<value>.py` | the intersection of those two directories |
| `probe.tuning` | `full`, `lora` | a branch in `models/probe_models/base.py` | — |
| `inject.format` | `note`, `p1_e1`, `p1_e2`, `p2_e1`, `p2_e2` | an entry in `agent/inject_format.py`'s `FORMATS` | `FORMATS`' keys, parsed with `ast` |
| `inject.arm` | `probe`, `no_probe`, `probe_nofill` | a branch in `agent/inject.py`, listed in that file's module-level `ARMS` literal | `ARMS`, parsed with `ast` |
| `build.weight_mode` | `uniform`, `per_event` | a branch in `data/build_training_dataset.py` | — |
| `build.split_source` | `env`, `hash` | a branch in `data/build_training_dataset.py` | — |

Model aliases are **not** an axis: they are validated against the rows of
`models/table.yaml`, which is the one registry of legal model names. The fourth
draft has two sources for them (the "register every value" rule and the model
table); this closes it in the table's favour, which is what makes a new backbone
a row rather than a row plus an axis line.

**An axis whose values are branches rather than files is dispatched through an
explicit mapping whose `else` raises**, naming the axis and the value; falling
through to a default branch is forbidden. That is the three rows whose selfcheck
column is `—` (`probe.tuning`, `build.weight_mode`,
`build.split_source`) and `generation.effort`, whose values are branches in a
family module and are additionally declared there as a literal; the three files
that hold such dispatch are
`data/build_training_dataset.py`, `models/probe_models/base.py` and
`models/agent_models/<family>.py`. *The failure this prevents: adding a third
split method is a value in `schema.py` plus a branch in `data/build_training_dataset.py`,
and if the branch is missed the value loads cleanly, falls through to whatever
the `if/else` ends on, and produces a dataset split by the old rule under a new
key — a wrong number, not a crash, which is the class every gate in this
document exists for.*

Three rows need a word on what "checked" means.

- **`generation.effort` is checked one way and validated another**, exactly as
  the split axis below. Every `models/agent_models/<family>.py` declares
  `EFFORTS: tuple[str, ...]` — the tiers that family accepts, empty when it has
  none — read at column zero with `ast.literal_eval` like `STOP` and
  `DEFAULT_EFFORT` (3.3). At load, `generation.effort` is validated against the
  `EFFORTS` of the family of the chosen `models.agent`, naming the family and its
  tiers (5.7); `selfcheck` compares the axis literals against the **union** of
  every family's `EFFORTS`. *The failure this prevents: the three values today
  are gpt-oss's, so a second family with different tiers takes
  `generation.effort: high` cleanly and fails inside the family module after the
  cards are taken — or, worse, drops it silently in `render_ids` and renders a
  different system message than the setting claims. 5.7 already treats the exactly
  parallel case for `data.instructions`.*
- **`inject.arm` is checked against a literal, not against control flow.**
  `agent/inject.py` declares `ARMS` at module level, holding the three values in
  the row above, and that is what `selfcheck` parses — the same mechanism as the
  `FORMATS` row beside it. Recovering three strings out of the branches of a
  file is not something an `ast` walk can be written to do.
- **The split axis is checked one way and validated another.** At load, **every
  element** of `sample.split` / `inject.split` is validated against the `splits:`
  block of the chosen `data.env` and against that environment's `SPLIT_ROLE`
  keys, so a split that environment does not have fails immediately with that
  environment named. `selfcheck` compares the axis literals against the **union** of every
  environment's split keys and flags a literal no environment offers. Union, not
  intersection: an intersection would retire `dev` for everyone the day a second
  environment arrives without one.

Axis values are literals in `schema.py`, never imported from the layer that
implements them, and `selfcheck` proves the literals equal what is on disk by
parsing, not importing. That is the whole of the settings layer's independence
(dependencies P1): a misspelled value still fails at load, and `schema.py` still
imports nothing.

## 5.4 References to another setting

Four fields point at another setting: `eval.theta_from`, `inject.probe_score`,
`inject.probe_gen`, `score.baseline`. One syntax:

```
<workflow>/<setting>            a name, resolved by loading that file and computing its key chain
key: {<stage>: <12 hex>, ...}   keys, pinned; survives an edit to the named setting
dir: {<stage>: <path>, ...}     directories, for runs made before this scheme
```

The loader resolves a reference at load time. The stage table says which
stage(s) of the referenced setting each field needs (Part 2.1), so a name
resolves to a fixed set of keys, all of which are written into `_upstream`, under
the naming of 1.5, and into `meta.json`. All of them
enter the referring stage's key except one, `inject.probe_score`'s eval key,
whose carve-out and its two stand-in `VERSION`s are stated in 2.1 and 2.2. A name that no
longer exists in its file is a load error, and `run.py` refuses to start a stage
whose referenced run has no `done.json`.

**A pinned reference carries one entry per stage the table names for that
field**, and no more: one for `eval.theta_from`, one for `inject.probe_gen` and
one for `score.baseline`; **two for `inject.probe_score`**, whose `train` entry
is the weights and whose `eval` entry is the temperature (2.1). A pinned
reference with a missing or an extra stage is a load error naming the field and
the stages the table asks for. *The failure this prevents: a bare `key:<hex>`
carries one key and does not say which stage it is, so a pinned `probe_score`
cannot express the pair at all and the loader cannot fold "the two resolved
probe_score keys" (2.2) out of it.*

**A pinned reference skips two checks, and is flagged for it.** It skips the
inheritance-agreement check below and the shared-build-key gate of 2.5, because
a directory made before this scheme has no `settings.yaml` to check against. A
setting that pins must therefore state the inherited sections itself and list
their dotted names in `meta.override`, and `ls` flags such a run `pinned`, so a
number computed against an unchecked upstream is visible rather than assumed.

**Inheritance, and what happens when two references disagree.** A referencing
setting **inherits** `data`, `models.agent` and `generation`, and an inject
setting additionally inherits the `build` fields in `PROBE_TEXT_FIELDS`
(Part 1.7). A setting may hold several references at once — an inject setting
holds three — so the rule is stated over all of them:

> **The agreement is per inherited group, not over all references at once.**
> `data`, `models.agent` and `generation` must agree across **every** reference
> of the setting. The `build` fields in `PROBE_TEXT_FIELDS` must agree only
> across the references the stage table resolves to a workflow that provides a
> `build` stage — `inject.probe_score` and `inject.probe_gen` — and a reference
> whose referenced workflow contains no `build` stage is not consulted for them.
> **A disagreement inside a group is a load error, naming both runs and the
> field; the setting inherits the agreed values.**

*The failure the scoping prevents: an inject setting's third reference is
`score.baseline`, which names a setting in `baseline.yaml` whose `workflow:` is
`[sample, score]` — and 5.7 refuses a section for a stage the workflow does not
name, so that setting cannot state a `build:` section at all and its
`PROBE_TEXT_FIELDS` are the schema defaults. Under a rule stated over all
references at once, every inject setting whose two probes were trained with a
non-default `min_think`, `hist_rounds` or `probe_result_cap` — the normal case,
since those are the knobs 1.7 exists to pin — would fail to load with "two
references disagree". The same holds in the other direction for a generator
setting's `eval.theta_from`.*

That is what makes the inheritance well defined without picking one reference as
authoritative, and the build gate in 2.5 (the two probe train runs must share a
`_upstream["build"]` key) is what makes the agreement reachable in practice.
Stating an inherited field differently in the setting is a load error unless
the field's dotted name is listed in the setting's `meta.override` (5.2). This
is the same-setup rule turned into a loader refusal: an inject arm cannot
silently differ from the data its probe was trained on, or from its baseline,
and a live run cannot feed its probe a text shaped differently from its
training text.

**Resolved values.** One number is derived from an upstream *report* rather than
from a setting: the softmax temperature that the probe service needs.
`run.py` reads it through `eval/utils/probe_eval.read_report(run_dir)` on the
directory that `_upstream["probe_score.eval"]` names, and `schema.freeze` writes
it into `settings.yaml` under `_resolved.probe_temperature`. It enters no key of
its own — `key` never reads the output tree (3.2 rule 2) — and what stands in for
it in the inject key is the train key it was fitted from plus the `VERSION`s of
the two modules that fitted it (2.1, 2.2). Nothing in `models/` ever opens an
`eval/` output.

## 5.5 The sweep keyword

```yaml
ctool_q17_lr:
  models: {probe: qwen17}
  probe: {method: ctool, tuning: lora}
  sweep: {train.lr: [1.0e-4, 3.0e-4, 5.0e-4], train.seed: [42, 67]}
```

expands at load into the cartesian product: six children named
`ctool_q17_lr/train.lr=0.0001,train.seed=42`,
`ctool_q17_lr/train.lr=0.0003,train.seed=67` and so on — fields sorted by name,
and **a value formatted with `repr()` of the parsed YAML value**, which is what
makes the name a fixed function of the file and lets a person type it back. (So
the YAML `3.0e-4` is addressed as `train.lr=0.0003`, not as `3e-04`; the rule is
pinned because a typed child name that formats differently misses its
directory.) Each child is a full setting with
its own keys; the children share the sample and build keys and therefore those
directories. `run.py` accepts a child name anywhere a setting name is accepted.
`eval/method_table.py` groups children by everything except the swept fields and
reports mean and spread, finding them through the `parent` and `swept` fields of
the registry row.

One `sweep:` block per named setting. Sweeping a field that `debug.yaml` also
sets is refused at load, because the children would collapse onto one key.

When several children want one shared upstream stage, the first child launches
it and the rest find the key already running and wait (Part 2.5's launch
refusal); the walk reports which key it is waiting on.

## 5.6 `debug.yaml`

Sizes only, never a model and never a tuning, so a debug run exercises the real
code path:

```yaml
sample:  {n_tasks: 3, seeds: [42], pieces: 1, replicas: 1, max_steps: 6}
build:   {max_cuts: 8, max_examples: 64}
train:   {epochs: 1, max_steps: 20, predict: {cap: 100}}
inject:  {n_tasks: 3, seeds: [42], pieces: 1, max_steps: 6}
eval:    {bootstrap: 50}
```

`inject` caps `max_steps` like `sample` does. *The failure this prevents: without
it a `--debug` inject run takes the schema default of 30 steps for each of its
three tasks, with the probe firing at every cut — the most expensive path in the
repo — so principle 4's "a few steps" and 9(c)#8's "only the sizes shrink" hold
for every workflow except the one they matter most in.*

Every field it sets exists in the schema, so the debug overlay adds no special
case to the loader. `n_tasks: 3` is three tasks
**per split** (2.3), so a `--debug` walk of `train_probe.yaml` builds all three
splits — which is what lets the walk reach `train.predict` and the eval at all.

**One file serves every workflow.** The overlay applies only the sections named
by this setting's `workflow:` line and ignores the rest, so `--debug` on
`baseline.yaml` (`[sample, score]`) or `inject.yaml` (`[inject, score]`) does not
introduce a `train:` or `build:` section into the setting. 5.7's
workflow-section refusal is evaluated over what the YAML file itself holds, never
over the merged setting, which is what keeps `debug.yaml` a single file and
principle 4 true for every workflow, not only for `train_probe.yaml`.

## 5.7 The merge order, and what the loader refuses

Merge, in order, each beating the one before:

1. the dataclass defaults;
2. the file's `common:` block;
3. the named setting;
4. `debug.yaml`, when `--debug` was given;
5. the command-line overrides `section.field=value`.

A list field is **replaced, never appended**. **Sweep expansion happens between
step 3 and step 4**, so the debug overlay and a command-line override both beat
a swept value — which is what makes 5.5's refusal of a sweep over a field
`debug.yaml` also sets correct: under that order the children would collapse
onto one key. A command-line override of a swept field is refused instead of
silently flattening the sweep. References are resolved after step 5; the
`meta.override` permission is checked after step 5, against the resolved
references; the model table's `result:` block is expanded last, immediately
before keying.

The loader refuses, naming the field in the message:

- a key that is not in the schema;
- a value outside an axis, or a retired value in a new setting;
- a `data.instructions` value that is not a key of the chosen environment's
  `INSTRUCTIONS`, read out of that environment file's source with `ast` (3.3's
  literal rule). *The failure this prevents: 4.4 gives that axis only a
  selfcheck-time cross-check against the union of every environment's keys, so a
  variant one environment does not have loads cleanly and fails as a `KeyError`
  inside `agent/loop.py` after the cards are taken;*
- a `models.agent` or `models.probe` alias whose `models/table.yaml` row's
  `role` is the wrong side;
- a `generation.effort` that is not in the `EFFORTS` of the family of the chosen
  `models.agent`, naming the family and the tiers it does have (5.3);
- a section for a stage the file's `workflow:` line does not name. **This one is
  evaluated against what the YAML file itself holds** — the `common:` block and
  the named setting, steps 2 and 3 — and never against the merged setting, so the
  `debug.yaml` overlay of step 4 cannot introduce a forbidden section (5.6). An
  *inherited* section is not affected either: the `build` fields in
  `PROBE_TEXT_FIELDS` that an inject setting inherits are resolved from its
  references and written into `settings.yaml` by `freeze`, never stated in the
  YAML file;
- a reference that does not resolve, or that resolves to a setting whose
  workflow does not provide the stage the table asks for;
- a referencing setting whose inherited sections (5.4) differ from the
  referenced run's without the field's dotted name in `meta.override`;
- two references of one setting that disagree on an inherited section, naming
  both runs and the field — **evaluated per inherited group** (5.4): `data`,
  `models.agent` and `generation` across every reference, the `build` fields in
  `PROBE_TEXT_FIELDS` only across the references whose workflow provides a
  `build` stage, since a reference into `baseline.yaml` (`[sample, score]`) may
  not state a `build:` section at all;
- a `probe:` section or a `models.probe` field in a setting whose workflow
  contains `inject` — the probes are named by `inject.probe_score` and
  `inject.probe_gen` (2.1);
- an `inject.probe_gen` whose referenced setting's `probe.method` is not a
  whole-call generator — concretely, whose `train/methods/<m>.py` declares
  `CHECKPOINT_META["param_only"]` true, or whose `PROBE_KIND` is not `generator`
  — naming the method (5.2, 2.6). *The failure this prevents: a `cparam` probe
  generates arguments only, so its `/gen` output is a syntactically plausible but
  toolless string, which `agent/inject.py` hands to `complete_call` and
  `speculate` and executes against the world: a wrong live run with no error
  anywhere;*
- a `score.baseline` whose baseline setting's `sample.split` list is not a
  superset of this
  setting's `inject.split` (or `sample.split`) list, or whose baseline `seeds` are
  not a superset of this setting's seeds — naming both settings, both split lists
  and both
  seed lists. *The failure this prevents: `inject.split` and `sample.split` have
  different defaults (5.2), and split and seeds are not among the
  sections 5.4 makes a reference inherit, so the likeliest setup mistake there is
  would otherwise be caught only by 2.5's record-level gate, after the inject run
  has finished — GPU days later. The loader already resolves `score.baseline`,
  so the mismatch is knowable before any card is taken;*
- `inject.fire_nth_cut` above zero under `arm: no_probe`;
- a `sweep:` over a field `debug.yaml` also sets, or over a field that is not in
  the schema;
- a command-line override of a field the setting sweeps;
- a required field left unset (`inject.theta`, `inject.probe_score`,
  `inject.probe_gen`, and `eval.theta_from` when the method's `PROBE_KIND` is
  `generator`). `score.baseline` is **not** on this list: its default `null`
  means "this run's own numbers only" (5.2), which is what `baseline.yaml`
  needs;
- a frozen `settings.yaml` that uses a field the schema has since removed —
  `load_frozen` says which field and which run directory, rather than silently
  defaulting.

---

# Part 6. The model table, the model modules, and constants

## 6.1 `models/table.yaml`

One row per alias, in two blocks. The rule for which block a column goes in is
one question: **does changing it change the bytes the model produces?** Yes goes
in `result:` and enters the key; no goes in `serving:` and never does. That is
the substance of the structure review's item 7 without moving the file.

```yaml
gptoss120b:
  role: agent
  family: gptoss
  result:
    weights: gpt-oss-120b          # alias into constants/path_models.yaml
    dtype: bfloat16
    quantization: null
    max_model_len: 131072
    served_model_name: gpt-oss-120b
    env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: ""
  serving:
    host: tokyo108
    port: 8103
    gpu_memory_utilization: 0.92
    tensor_parallel_size: 1
    env: {LD_LIBRARY_PATH: .../cuda-compat-13.0}

qwen06:
  role: probe
  family: qwen                     # models/probe_models/qwen.py
  result:
    weights: qwen3-0.6b-base
    dtype: bfloat16
  serving: {}
```

| column | block | why |
|---|---|---|
| `role` | row | `agent` or `probe`; decides which side of `models/` the family resolves against |
| `family` | row | the file under `agent_models/` or `probe_models/`; part of the row's identity, so it is keyed |
| `weights` | result | different weights, different outputs |
| `dtype`, `quantization` | result | they change the arithmetic |
| `max_model_len` | result | changes where a long prompt is refused, and therefore which tasks abort (grounding F8, dependencies P5) |
| `served_model_name` | result | the string the client sends; a mismatch is a different server |
| `host`, `port` | serving | where the same server runs |
| `gpu_memory_utilization`, `tensor_parallel_size` | serving | how much card it takes |
| `env` | serving | **only keys that name a location or a resource**: `LD_LIBRARY_PATH`, `CUDA_DEVICE_ORDER`, `VLLM_CACHE_ROOT`, `TRITON_CACHE_DIR` |
| `env_result` | result | every other environment variable, keyed like the rest of the block; `VLLM_USE_FLASHINFER_SAMPLER` and `VLLM_BATCH_INVARIANT` are `env_result` columns today |
| `extra_flags` | result | server flags change the arithmetic or the sampling as readily as a `result:` column does, so they are keyed |

**`role` and `family` are keyed with the `result:` block; only `serving:` is
outside the key**, which is the shape 3.3's `models` entry writes. *The
failure this prevents: repointing an alias's `family` at a different
conversation format leaves every key standing still, so the new prompt bytes are
written into the finished directory of the old ones, and the `--attach-only`
family echo of 7.2 compares against the new family while the records carry the
old key.*

**The `serving:` block is closed, not a bucket.** The escape clause "anything
here that turns out to change results moves to `result:`" is not a gate, and
this repo's own history has already varied a numerics switch inside it:
`legacy/ops/jobs.json` shows some vLLM launches with `VLLM_BATCH_INVARIANT=1`
and others without, with `VLLM_USE_FLASHINFER_SAMPLER=0` on every line. So the
rows above split the old `env` in two and move `extra_flags` across. *The
failure this prevents: two runs whose sampler or batch-invariance backend
differs getting one key and one directory.*
`VLLM_SYSTEM_START_DATE` is in neither: it has its own home in `generation.date`
(below) and stays there.

**`VLLM_SYSTEM_START_DATE` is not a `serving.env` entry.** It is set by
`models/agent_models/service.py` from `generation.date`, because the server
otherwise takes the date from its own clock
(`vllm/entrypoints/openai/parser/harmony_utils.py:133-139`) and a rerun in
November would render a different prefix. The date is a setting field, so it is
in the key on the setting side, where it belongs.

`experimental_settings/schema.py` expands `role`, `family` and the `result:`
block of the named agent and probe into the setting before keying, into the two
read-only fields `models.agent_row` and `models.probe_row` (5.2); `models.agent`
and `models.probe` stay the alias strings, and the absolute weights path stays
out of the expansion — it is a `constants/` lookup that enters no key and is
resolved at run time by `models/__init__.py` (6.2). **Every run-time reader of a
keyed column reads it from the frozen expansion, not from this file** (6.2, 7.1).
The `serving:` block is read live, and only by
`models/agent_models/service.py` at start and by `jobs/launch.py` for the
agent service's host and preferred port (3.4, 7.4). A new model of a known family or
backbone is one row here and one row in `constants/path_models.yaml`.

The owner's open question — whether the read-only hook covers `table.yaml` — is
answered **yes**: the `result:` block changes results exactly as a setting does,
so the hook that refuses agent edits to `experimental_settings/*.yaml` covers
`models/table.yaml` too.

## 6.2 The two model modules

Two of the four extension points that gain a file are model modules, and both
are imported **by name, inside a function**, by one caller each:
`models/__init__.py` imports the family module, `models/probe_models/base.py`
imports the backbone module. Each therefore needs the same kind of contract the
environment has in 4.2 and the train method has in 2.6 — the names it must
define — or the two importing files grow a branch per model. Neither table adds
a file: both are content the tree's own lines already promise.

**What the two entrances return.** Two small dataclasses declared in
`models/__init__.py`, so that nothing is attached to a module object and every
field has a name:

```python
models.agent(alias) -> AgentModel   # module, alias, role, family, weights, weights_path, serving
models.probe(alias) -> ProbeModel   #         alias, role, family, weights, weights_path, serving
```

`AgentModel.module` is the family module, imported by name inside the function;
that object is what 0.4 means when it says every caller reaches the family
through `agent(alias)` and names no family file. `ProbeModel` carries **no**
module, because `probe(alias)` imports nothing:
`models/probe_models/base.py` imports the backbone module by name inside
`load()`, using the row's `family`. *The failure this prevents: two annotation
lines in 0.2 said `base.py` imports the backbone while `models/__init__.py`'s
description said it did; whichever a builder picked, `selfcheck` would fail on
the other. And attaching per-alias attributes to a shared module object breaks
the moment two aliases share a family.*

**`weights` is always the alias and `weights_path` is always the directory** —
in `models/table.yaml`'s `result:` block (6.1), in the frozen
`cfg.models.agent_row` / `cfg.models.probe_row` (5.2) and in both return types
alike. *The failure this prevents: one name meaning the alias in the frozen row
and the resolved path in the entrance's return, held side by side by
`base.load`, whose `row` is the frozen row while it resolves the path through
`models.probe(cfg.models.probe)` — and by the probe service, whose `/health`
echo must carry the weights **alias** (7.2) and would otherwise have no source
for it.*

**Inside a run, every keyed column of a model row is read from the frozen
setting, never live from `models/table.yaml`.** `cfg.models.agent_row` and
`cfg.models.probe_row` are the expansions `run.py` froze before the pieces
started (5.2, 6.1), and they are what `agent/loop.py`, `agent/inject.py`,
`models/agent_models/service.py`, `models/probe_models/base.py` and the probe
service's `check` client read: `base.load`'s `row` parameter **is**
`cfg.models.probe_row`. The two entrances supply only what enters no key — the
family module, the weights path from `constants/path_models.yaml`, and the
`serving:` block, which is the one block a run may read live because it is
outside every key (6.1).

**There are two exceptions, and each is closed by a comparison.** The first is
the probe service's `serve`, below. The second is the family module: `family` is
a keyed column (6.1), and `agent/generate.py` and `agent/inject.py` reach the
family through `models.agent(cfg.models.agent)`, which resolves that column live
out of `models/table.yaml` (0.2 lists `models/__init__.py` among both files'
imports). **Both compare `module.NAME` against `cfg.models.agent_row["family"]`
before their first use and refuse on a difference** — the same comparison the
probe service's `/health` echo carries (7.2), and `NAME` is already pinned below
as "the value a table row's `family:` column carries", so it costs one line in
each file and no new import. *The failure this closes: an alias repointed between
the freeze and a launch or a refire gives `generate.step` a different
conversation format than the directory's key was computed over — the failure 6.1's
own paragraph forbids, with nothing else on this path to catch it.*

**The first exception, the probe service's `serve`**, takes an agent alias
on its command line, reads no `settings.yaml` in the server half (7.2, 0.2) and
therefore resolves two keyed columns live: `family` and `weights`. Both are
echoed on `/health` and compared against the frozen row by `agent/loop.py`
(7.2), and that comparison is what stands in for the frozen read there. *The
failure this closes: `family` was already echoed and compared, `weights` was
echoed nowhere, so an alias repointed between the freeze and a launch or a refire
gives `/encode`, `/decode` and `/render` a different tokenizer than the
directory's key was computed over — the exact failure this paragraph forbids, and
one 7.1 already prevents on the agent-service side.* *The failure this prevents: a `result:` column edited
between the freeze and a refire, or between a first launch and a relaunch into
the same directory, would give a piece a different `dtype`, `max_model_len` or
`weights` than the directory's key was computed over — which 6.1's own failure
paragraph says must not happen.*

**A family module — `models/agent_models/<family>.py`.** One file per
conversation format.

| name | signature | what it must do |
|---|---|---|
| `VERSION` | `int` | bumped when any of the below changes the bytes |
| `NAME` | `str` | the value a table row's `family:` column carries |
| `render_ids(messages, effort, date)` | `list[dict], str \| None, str \| None -> list[int]` | the conversation as the model's own prompt token ids, system message included; the heavy import (`openai_harmony`) sits inside this function |
| `parse(text_delta, state)` | `str, dict -> dict` | split a streamed reply into its channels, carrying `state` from chunk to chunk; returns the channels grown so far under **exactly two keys, `reasoning` and `content`** — the two `StepResult` fields `agent/generate.py` fills from it (7.3). Per-family bookkeeping (which channel is open, a partial control token) lives in `state` and never in the returned dict. *The failure this prevents: two spellings, `thinking` against `reasoning` or `final` against `content`, give an empty thinking text, so `cuts_live` returns no cuts and an inject run never fires* |
| `end_of_turn(ids)` | `list[int] -> bool` | whether the generated ids have closed the turn |
| `wrap_prefetch(body, system_text)` | `str, str \| None -> str` | wrap an injected prefetch body in the family's control tokens; this is what a `p2` placement calls (7.3) |
| `STOP` | `list[str]` | the family's stop strings, the default of `generation.stop` |
| `EFFORTS` | `tuple[str, ...]` | the reasoning tiers this family accepts, empty when it has none; the loader validates `generation.effort` against it and `selfcheck` takes the union over every family (5.3, 5.7) |
| `DEFAULT_EFFORT` | `str \| None` | the family's default reasoning tier, one of `EFFORTS`, or None when it has none |
| `DEFAULT_DATE` | `str \| None` | the date the family pins into its system message, or None |

**A backbone module — `models/probe_models/<backbone>.py`.** One file per probe
backbone; everything the backbones share is in `base.py`.

| name | signature | what it must do |
|---|---|---|
| `VERSION` | `int` | bumped when any of the below changes the training or the score |
| `DTYPE` | `str` | the dtype the weights are loaded in, unless a `result:` column overrides it |
| `LORA_TARGETS` | `list[str]` | the modules LoRA attaches to; the default of `probe.lora_targets` |
| `HEAD_LAYER` | `str` | the attribute path of the hidden state the classification head reads |
| `prepare_tokenizer(tok)` | `Tokenizer -> None` | the pad token and this backbone's tokenizer quirks, in place |
| `attach_head(model, n_labels)` | `Module, int -> Module` | build and attach the classification head; called only for `PROBE_KIND: classifier`. `n_labels == len(labels)`, and **the class order is the caller's**: `trainer.run` gets the list from the method's `head_labels` hook (2.6) and passes it to `base.load`, `base.py` passes the count here and writes the list into `best/meta.json` (1.3). The backbone never sees the names and never orders them |

`base.py` calls exactly these names and holds every branch that is not one of
them, which is what keeps "a new backbone is one file plus two rows" (0.4) true.

**The probe object — `models/probe_models/base.py`.** Five files manipulate it —
`train/utils/trainer.py`, the three `train/methods/<m>.py`, and
`models/probe_models/service.py` inside `serve()` — and 2.6's hooks take `probe`
and `tok` as parameters, so its names are pinned here like the two module
interfaces above. The tree line for this file already promises exactly these
("load, save, score a prefix, generate a call"); nothing here adds a file.

| name | signature | what it must do |
|---|---|---|
| `VERSION` | `int` | bumped when the head, the checkpoint layout or the score changes |
| `load` | `load(row, cfg, *, probe_kind, n_labels=None, labels=None, ckpt_dir=None) -> Probe` | build the probe: import the backbone module by name (6.2 above), load the weights at the row's `dtype`, `prepare_tokenizer`, `attach_head(model, n_labels)` when `probe_kind` is `classifier`, apply LoRA when `cfg.probe.tuning` is `lora`, and restore from `ckpt_dir` when one is given. `row` is the frozen `cfg.models.probe_row` — `role`, `family` and the `result:` block — and `base.py` resolves the absolute weights path for its `weights` alias through `models.probe(cfg.models.probe)`, the one value it takes live because it is a `constants/` location (above). `cfg` is the frozen `Setting`, **annotated `object` in this file**, so `base.py` still imports no `schema.py`; it reads exactly `cfg.probe.tuning`, the four `cfg.probe.lora_*` fields, `cfg.train.max_len` and `cfg.models.probe`, and nothing else (`train_key` reaches `meta.json` through `save`'s `meta`, below, so `base.py` never reads `cfg._key` either). On a restore — the probe service's `serve()`, which has checkpoints and no setting — `row` and `cfg` are both None and the backbone alias, the tuning and `max_len` come from `ckpt_dir/meta.json` instead (1.6). `labels` is the class order the caller computed — `trainer.run` calls the method's `head_labels(df, cfg)` hook on the whole example frame and passes `labels` and `n_labels` from it, both None for a generator (2.6, 1.3); a restore reads the list back out of `ckpt_dir/meta.json` instead and calls the hook not at all |
| `Probe.save` | `save(dir, *, labels=None, extra=None, meta=None) -> None` | write the checkpoint layout of 1.6 — weights or merged adapter, tokenizer, `head.pt` for a classifier, and `meta.json` carrying `labels`, every key of `meta` and every key of `extra`. `meta` is the identity block `trainer.run` passes — `{backbone: cfg.models.probe, tuning: cfg.probe.tuning, max_len: cfg.train.max_len, train_key: cfg._key}` — and `extra` is the method's `CHECKPOINT_META`, merged in unread (1.6, 2.6). Both are merged and neither is read, which is what keeps a per-method and a per-run value out of this file's branches |
| `Batch` | `dict[str, Any]` | what `batches` yields and `loss`, `reference_loss` and `forward` pass around. The keys `Probe.forward` consumes are `input_ids`, `attention_mask`, `event_end` and the optional `position_ids`, each a tensor; `event_end: LongTensor` is the method-supplied position of **the last non-pad token of each event** in the packed sequence, which is where the classification decision is taken (below); **every other key is the method's own** — targets, loss positions, packing offsets — and `base.py` never reads it. *The failure this prevents: three method files write three batch shapes, `forward` fits at most one of them, and the alignment gate cannot catch it because it compares `loss` against `reference_loss` inside one method* |
| `Outputs` | a dataclass declared in this file | what `forward` returns: `logits` (the classification head's for a classifier, the LM head's for a generator) and `hidden` (the state at the backbone module's `HEAD_LAYER`), both aligned to `input_ids`. A method's `loss` reads these two names and nothing else. **The classification head reads the hidden state at the last non-pad token of each event**, the positions `Batch["event_end"]` names, so a classifier's `logits` carry one row per event rather than one per token. *The failure this prevents: the decision position is chosen twice — by `base.py` when it serves and by `train/methods/ctool.py` when it packs — and a disagreement (the text's last token against an event's last token inside a packed sequence, or the token before the separator) scores the probe at a position it was never trained on: `/score` at every live cut, the `predict` hook's columns, the fitted temperature, theta and every classifier number, with no error and no gate, since `reference_loss` compares one method file against itself* |
| `Probe.tokenizer` | `Tokenizer` | the tokenizer `trainer.py` hands a method's `batches` and `predict` hooks as `tok`, so one object serves training and serving |
| `Probe.max_len` | `int` | the token budget an event is packed into, from `train.max_len` at training and from `best/meta.json` at serving |
| `Probe.forward` | `forward(batch: Batch) -> Outputs` | the backbone call a method's `loss` and `reference_loss` use, reading the four tensor keys of `Batch` and returning `Outputs`; it is the only place a method touches the model |
| `Probe.score` | `score(texts) -> tuple[list[list[float]], list[str]]` | the class logits in `labels` order and the argmax class name per text, **one event per text, read at that text's last token** — the served form of the same rule `event_end` carries on the packed path; `POST /score` applies the temperature to these (7.2) and `predict` writes them into the prediction row (1.3) |
| `Probe.generate` | `generate(texts, max_new, call_sep) -> list[str]` | the greedy continuation after `call_sep`, cut at the first newline and stripped. **The caller supplies the separator**, because it is the method's value and not `base.py`'s (1.6): a generator's `predict` and `validate` hooks pass their own module's `CHECKPOINT_META["call_sep"]` (2.6), and `models/probe_models/service.py` passes the value it read out of the gen checkpoint's `best/meta.json` (7.2). *The failure this prevents: with the separator read from a file inside this method there is no source for it on the training path at all — `predict` runs with `ckpt_dir=None` and `best/` is chosen by the very metric that generates — and the only ways out are for `base.py` to read a key of `extra`, which 1.6 forbids, or to hardcode a separator, which is wrong generations under a correct key* |

*The failure this prevents: this is the one object every train file manipulates,
and Part 6.2 pinned the two modules around it while leaving it unnamed. A builder
could not write `train/methods/ctool.py` or the probe service's `/score` and
`/gen` without inventing the interface, and three method authors would invent
three.*

## 6.3 `constants/`

Locations only. Nothing here enters a key; a path changes only when the same
bytes move, and new bytes are a new alias.

**`path_datasets.yaml`** — one top-level `venvs:` map, then one block per
environment:

```yaml
venvs:                                  # every interpreter this repo starts a program with
  appworld: /home/y-guo/reproduce/new1/external/appworld/venv/bin/python
  probe:    /home/y-guo/reproduce/new1/external/probe-env/bin/python
  vllm:     /home/y-guo/reproduce/new1/external/vllm-env/bin/python

appworld:
  home:  ...
  venv:  appworld                       # a key of venvs:
  data:  ...
  splits: {train: ..., dev: ..., test: ...}
```

| column | meaning |
|---|---|
| `venvs` (top level) | `appworld \| probe \| vllm` -> the absolute interpreter path. The one place the repo looks to answer "which python": `jobs/launch.py` for every tmux piece (a loop piece, a train piece, the vLLM service, the probe service), `run.py` for a CPU stage it starts in place (2.3). `run.py selfcheck` reads the same map for its "each `any` file imports under every interpreter in it" test. It is a map and not a convention because the three directories are not uniformly shaped (`external/appworld/venv`, `external/probe-env`, `external/vllm-env`), so nothing can be inferred from an environment's name |
| `home` | the clone's directory; the benchmark is entered there before its package is imported |
| `venv` | **which interpreter runs a loop piece for this environment** — a key of the `venvs:` map, not a path (dependencies P7; today the path lives in `legacy/run.py:63-75` and has no planned home) |
| `data` | the benchmark's data root |
| `splits` | split name -> the task-id file for that split, one id per line, no trailing newline (`legacy/pipeline/annotate/build.py:303-306`). The keys are the benchmark's own names (`train`, `dev`, `test` for AppWorld), which the environment's `SPLIT_ROLE` map (4.1) turns into the three roles an example row's `split` column carries. `experimental_settings/schema.py` reads this block too, to validate every element of `sample.split` / `inject.split` against the chosen `data.env` at load (5.3) |

**`any` is not a key of the `venvs:` map, and the launcher does not choose.**
The stage table's venv column reads `any` for `build`, `eval` and `score`; a
stage whose column is `any` is launched with **`venvs.probe`**, the interpreter
this repo's commands are typed with (`run.py`'s own venv line, 0.2). `any` is a
statement about *importing* — the file imports under every interpreter in the
map (0.1) — not a licence to pick one at launch, and the three CPU stages
therefore have exactly one resolvable interpreter. Only `run.py` performs that
lookup, because `run.py` is what starts a CPU stage (2.3).

The split lists are a location by placement and a result-changer by content
(dependencies P5). Four things close that gap without moving them: the
environment file owns reading them and its `VERSION` covers the reading rule;
the `sample` and `inject` directories' `meta.json` records each split file it
resolved, in `split_files` (Part 8.3); **`build`'s `consumed.json` records every
split file it read** (2.5), because `build` is the
stage that turns a split file into the `split` column of every example row; and
`run.py ls` flags a directory — sample, inject or build — whose recorded hash no
longer matches the file.

**`path_outputs.yaml`** — `root:` (the NFS outputs root), `debug_subdir:`
(`debug`), `login_host:` (the one machine `run.py` and `jobs/launch.py` may run
on, 8.6), and `hosts:`, the cluster inventory:

```yaml
root: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs
debug_subdir: debug
login_host: <the machine this repo's commands are typed on>   # gyb sets it once
hosts:
  - {name: tokyo105, alias: shiga,    cards: 4}
  - {name: tokyo106, cards: 8}
  - {name: tokyo107, cards: 8}
  - {name: tokyo108, alias: saitama,  cards: 8}
```

`hosts:` goes here because this is the only cluster-wide constants file — the
other two are per environment and per alias — and because a host list is a
location like any other and enters no key. It replaces today's literal
(`DEFAULT_HOSTS`, `legacy/ops/gpu_jobs.py:124`) and today's alias map
(`legacy/ops/launch_common.py:41`), which exist because `hostname` on tokyo105
answers `shiga`. `jobs/launch.py` reads it to start remote pieces and probe
cards; `jobs/registry.py` reads it for `ls` and `free` (Part 3.4 has the
transport and the fail-closed rule). `login_host` goes beside it because it is
the same kind of fact and because the whole concurrency story of 8.6 rests on
it.

**`path_models.yaml`** — `alias -> {path, note}`, today's
`legacy/configs/models.json` shape in YAML. `path` is an absolute directory or a
hub id; `note` says where the copy came from and when it was checked.

**Which side does a new column go to?** Ask what happens if it changes and
nothing else does. If a finished run's numbers would have been different, it is a
setting field or a `result:` column. If only the machine or the speed changes, it
is `constants/` or a `serving:` column.

---

# Part 7. Service protocols

Two services, one file each, both ends in the file, as the tree says. The client
half is standard library and imports under `any`; the server half is a `main`
whose heavy imports sit inside it. `jobs/launch.py` starts both as pieces of a
stage, assigns each one its port, and writes their registry rows with
`kind: service`. Who assigns a port, where it is written down and how a client
finds it are in 7.4; both client halves take a base URL and never guess one.

The loop runs in the environment's venv, which cannot hold `openai_harmony`
(pydantic 1.10.26 against pydantic 2, `legacy/envs/collect/common.py:14-20`) and
has no `transformers`. So the loop reaches both the agent model's tokenizer and
the probe through services. That is the constraint the whole of Part 7 exists to
satisfy.

## 7.1 The agent service — `models/agent_models/service.py` (vLLM)

**Server half** (`venv: vllm`):

```
python -m models.agent_models.service serve --run-dir <dir> --model <alias> \
    --port <n> --gpus <ids> [--attach-only]
```

It reads the alias's **keyed columns out of the run directory's frozen
`settings.yaml`, as `cfg.models.agent_row`** (5.2, 6.2) — never live from
`models/table.yaml`, whose row may have been edited since the freeze — its
`serving:` block live from `models/table.yaml`, which is the one block outside
every key, and the weights path from `constants/path_models.yaml`. It sets
`VLLM_SYSTEM_START_DATE` from `generation.date`, and either starts `vllm serve`
with those flags or attaches to a live server on the same host and port. The
port is not its own decision: `jobs/launch.py` puts it on the command line
(7.4). It writes its own `service_agent_<replica>.json` into the run directory,
with the fields 1.5 gives that file — one file per service piece, so one
writer per file, which is the same rule the heartbeat follows.

**When `--attach-only` is passed.** `jobs/launch.py` passes it when a live
registry row already owns a service piece on that host and port serving the same
`result:` block; otherwise it starts a server. The search for such a server runs
**before** any port is assigned, which is what makes this branch reachable at all
(7.4). The attaching run writes its own
`service_agent_<replica>.json` with `attached_to: <that run_id>`, which is what
makes an attachment visible from both sides and what `run.py kill` reads (8.6).
*The failure this prevents: `kill` having to decide "is another run attached to
this server" from a fact nobody recorded.*

**Attach is verified, not assumed.** The service asks `GET /v1/models` for the
served model name, compares it and every keyed column against
`cfg.models.agent_row` — the frozen row, not `models/table.yaml` — and refuses to
attach on any difference. *The failure this prevents:
pointing at the wrong server does not error, it produces wrong numbers — the
2026-08-18 lesson that `probe_cfg_problem` was written for
(`legacy/pipeline/inject/live_appworld.py:572-587`).*

Then it runs the check table before reporting healthy:

| check | how |
|---|---|
| health | `GET /health` answers before `jobs/launch.py`'s alive check gives up on the piece (8.1) |
| model | `GET /v1/models` names the row's `served_model_name` |
| render equals server | for one fixture conversation, `gptoss.render_ids(messages, effort, date)` computed in this venv equals the `prompt_token_ids` the chat endpoint returns for the same conversation (`POST /v1/chat/completions` with `max_tokens: 1`, `reasoning_effort`, `return_token_ids: true`), id for id |

The third check is the reason `render_ids` exists and the reason it must be
compared against the **chat** endpoint and not against `/tokenize`: on this vLLM
version `POST /tokenize {messages}` for a gpt-oss model goes through
`preprocess_chat`, the jinja path
(`vllm/entrypoints/serve/tokenize/serving.py:84`), while only the chat endpoint
reaches `_make_request_with_harmony`
(`vllm/renderers/online_renderer.py:154-180`). The jinja path is exactly the one
the 2026-08-18 investigation found diverges in two edge cases — an
empty-content assistant turn, and a literal `<|end|>` inside content — which
make a prompt permanently different from the baseline's from that step on
(`legacy/pipeline/inject/harmony_render.py:1-18`).

**Client half** (standard library, imported by `agent/generate.py` and
`agent/loop.py`). It is constructed with an explicit endpoint and an explicit
model name — `Client(base_url: str, served_model_name: str)` — both of which the
caller supplies: the base URL out of an endpoint file, the model name out of its
frozen `cfg.models.agent_row["served_model_name"]` (7.4). There is no default and
nothing is inferred from the table. *The failure this prevents: `model` is a
field of the completion body below and `served_model_name` is a keyed `result:`
column that 6.2 forbids reading live from `models/table.yaml` inside a run, while
`stream`'s `generation` argument carries no model name — so `agent/generate.py`
would have to invent a source, and the two it has are a `GET /v1/models` lookup
(a second source of truth for a keyed column, which the attach check below exists
to catch) or a literal. 6.1 says a wrong `served_model_name` "is a different
server".*

| call | request | response |
|---|---|---|
| `stream(prompt_ids, generation, seed)` | `POST /v1/completions` with `model`, `prompt` (token ids), `max_tokens`, `temperature`, `stop`, `top_p` and `seed` only when set, `add_special_tokens: false`, `skip_special_tokens: false`, `return_token_ids: true`, `stream: true`, `stream_options: {include_usage: true}` | an iterator of `(text_delta, token_ids_delta)` pairs, then `finish_reason`, `stop_reason` and `usage`; `close()` aborts server-side decoding |
| `health()` | `GET /health`, `GET /v1/models` | up, and the served model name |

The stream hands out text and ids per chunk **together**, because the text lags
the ids when vLLM withholds bytes for a stop string or an incomplete character,
and every consumer records chunk boundaries as `(chars, ids)` pairs
(`legacy/pipeline/inject/live_appworld.py:190-238,340-376`).

The prompt is always token ids, for sample and for inject alike: one generation
path, so a probe run and its baseline are compared on the same path. Retries:
three, with exponential backoff, on connection errors and 5xx; a 400 is passed
to the caller, which records `abort="context_overflow_400"` and lets the task be
judged honestly.

## 7.2 The probe service — `models/probe_models/service.py`

**Server half** (`venv: probe`):

```
python -m models.probe_models.service serve --run-dir <dir> \
    --agent-model <alias> --port <n> \
    [--score-ckpt <dir> --gen-ckpt <dir> --temperature <f>] \
    [--device cuda:0] [--render-only]
python -m models.probe_models.service check --base-url <url> --run-dir <dir>
```

`--score-ckpt`, `--gen-ckpt`, `--temperature` and `--device` are **absent under
`--render-only`**, which loads no probe and runs on the CPU; `jobs/launch.py`
passes all four only for the piece that loads checkpoints, which is the same
piece that takes a card (3.4). *The failure this prevents: a `sample` run's probe
piece is exactly the render-only case (2.3) and has no source for the other
three — its `_upstream` is empty, so `jobs/launch.py` cannot resolve
`--score-ckpt` or `--gen-ckpt` (1.5), and `_resolved.probe_temperature` is
written only for an inject run (5.4) — so the flagship first walk, 9(c)#1, could
not have its command built at all.*

**Both checkpoint flags take the train run directory**, which is what
`jobs/launch.py` gets by passing `_upstream["probe_score.train"]` and
`_upstream["probe_gen.train"]` through `run_dir_of`; the service opens
`<dir>/best/` and `<dir>/best/meta.json` inside it, matching 1.6's layout. *The
failure this prevents: the other reading — the flag carries `<run_dir>/best` and
the service opens `meta.json` directly — is as easy to write as this one, and the
two files are written against opposite halves of it as readily as against the
same, with the symptom a startup failure on every inject launch, after the cards
are taken.*

It is the loop's one door into the probe venv: the probe itself, and the agent
model's renderer and tokenizer, which the loop's venv cannot import.
`--render-only` loads no probe and answers `/render`, `/encode`, `/decode` and
`/health` only, on the CPU; `/score` and `/gen` then return 503 and never
pretend a probe is there, and `score_train_key`, `gen_train_key`, `temperature`
and `max_len` are null in the echo, since that mode loads no checkpoint. That is
what `agent/loop.py`'s refusal already tolerates on a `sample` run, which asks
only for `render == "ids"`, the family and the weights — the three the
render-only mode does echo (6.2, and the refusal itself is below). That is today's mode
(`legacy/pipeline/inject/probe_server.py:138-161,360-362`), and it is what a
`sample` run uses. The port comes from `jobs/launch.py` on the command line
(7.4), and the service writes its own `service_probe_0.json`, with the fields
1.5 gives that file.

**The server binds every interface on the host the piece was placed on**, and
`service_probe_0.json`'s `base_url` carries that host name, exactly as the agent
service's endpoint file does (7.1, 7.4). It is not a loopback server: 3.4 puts
the checkpoint-loading probe piece of an `inject` run on a GPU host while the
loop pieces run on `login_host`, so every `/score`, `/gen`, `/encode` and
`/decode` call crosses the network. *The failure this prevents: a builder reading
"local" binds `127.0.0.1`, and every inject run fails at its first probe call —
after the cards are taken. The `sample` case hides it, because the render-only
piece really does sit on `login_host` beside the loop pieces.*

**`check` is a client, not a second server.**
`check --base-url <url> --run-dir <dir>` issues one request of each route against
the **already-running** service, verifies the `/health` echo and **both
directions of `encode` on the `<|end|>` fixture of 9(d)** — `special=false` must
leave it as plain text, `special=true` must turn it into its control token — and
exits non-zero on any mismatch. That fixture has exactly this one owner: the
server does not check itself, which is the whole point of a client-side check
(9(a)#38), and `jobs/launch.py` turns the non-zero exit into the `service_check`
outcome of 8.1.
**It reads the run directory's frozen `settings.yaml` for the same facts
`agent/loop.py` and `agent/inject.py` read** — `models.agent_row["family"]` and
`models.agent_row["weights"]` (5.2),
`_upstream["probe_score.train"]` and `_upstream["probe_gen.train"]`, and
`_resolved.probe_temperature` — and compares them against `family`, `weights`,
`score_train_key`, `gen_train_key` and `temperature` in the echo, plus
`render == "ids"` and `encode_special`. *The failure this prevents: with a base
URL alone there is nothing to verify the echo against — the expected values all
live in the run directory — so `check` could only confirm that the service
answers, which the port probe already did, and `jobs/launch.py` would gate a whole
inject launch on a check that checks nothing. Reading the same file the loop reads
is also what makes the launch gate and the loop's own refusal (below) check the
same thing.* `jobs/launch.py` runs it after the
probe service piece's port answers and before the first loop piece starts, and a
non-zero exit is a `launch_failed` finish row (8.1). *The failure this prevents:
a `check` that loads everything itself would put a second copy of both
checkpoints on the one card the probe service already owns (2.3 gives the inject
probe piece exactly 1 card) — wasteful on a 0.6B pair and an OOM at every launch
on a 1.7B pair — while a `check` run before the service starts would prove
nothing about the process that will actually serve.*

| route | request | response |
|---|---|---|
| `POST /score` | `{"text": <probe input>}` | `{"conf": float, "label": str, "wall_s": float}` — `conf` is `max softmax(logits / temperature)`, `label` the argmax class name |
| `POST /gen` | `{"text": <probe input at the cut>, "max_new": int}` | `{"call": str, "wall_s": float}` — what `Probe.generate(texts, max_new, call_sep)` returns (6.2), the separator being the `call_sep` this service read out of the **gen checkpoint's `best/meta.json`** at startup and passed down (1.6), and the budget being the `max_new` the request carries — `agent/inject.py` sends `cfg.inject.max_new` (5.2) on every call, since it holds the frozen setting and this server reads none. Neither is ever a constant in this file: the budget changes the bytes a live run produces, so it enters the inject key and its own `settings.yaml` like every other result-changing value. `param_only` is read from the same file at startup and changes nothing about this route: the service **refuses to start** when it is true, naming the checkpoint, because an argument-only probe cannot serve this side — the same refusal 5.7 makes at load, taken again against the checkpoint that is actually on the card |
| `POST /render` | `{"messages": [...], "effort": str, "date": str}` | `{"prefix_ids": [int], "n_tokens": int}` — `models.agent(alias).render_ids(...)` |
| `POST /encode` | `{"text": str, "special": bool}` | `{"ids": [int]}` — the agent tokenizer's `encode(text, add_special_tokens=False, split_special_tokens=(not special))` |
| `POST /decode` | `{"ids": [int]}` | `{"text": str}` — `decode(ids, skip_special_tokens=False)` |
| `GET /health` | — | the startup echo: `family` and `weights` (the two keyed columns it resolved live through `models/__init__.py` from its `--agent-model` alias — `"gptoss"` and the weights alias today — which is why 6.2 names this service its one exception and why `agent/loop.py` compares both), `render` (`"ids"` when `/render` returns prompt token ids), `encode_special`, `decode`, `temperature`, `agent_model`, `score_train_key`, `gen_train_key`, `max_len`, `device`, the format version. **No `date`**: the service reads no `settings.yaml`, its `serve` line carries no date, and the date arrives per request on `/render`, so the field would have no source at startup |

**The threshold is not applied here.** `/score` returns the confidence and
`agent/inject.py` compares it against `inject.theta`. One place decides to fire,
and it is the place that also knows `arm`, `fire_nth_cut` and
`max_inject_per_step`. (Today the server also returns `fired`,
`legacy/pipeline/inject/probe_server.py:8`; dropping it removes a second copy of
the rule and keeps theta in the setting, where CONTEXT puts it.)

**Why `encode` and `decode` stay here**, and why this is not vLLM's `/tokenize`.
Legacy encodes the injected note with
`split_special_tokens=(not special)` (`probe_server.py:88-95`) so that a
control marker inside an execution result stays *plain text* for a `p1` format,
while a `p2` prefetch message gets real control tokens
(`live_appworld.py:506-508`). vLLM 0.26.0's `TokenizeCompletionRequest` exposes
`add_special_tokens` and nothing else
(`vllm/entrypoints/serve/tokenize/protocol.py:24-47`); `add_special_tokens`
controls BOS, not embedded markers, so the `special=false` direction — the
default one, used by every `p1` format — cannot be expressed at all. The tree's
own line for this file names `encode` and `decode`, and this is why.

**Why `/render` is here too.** The route is not on the file's tree line, which
names score, generate, encode and decode. It goes here under the rule that a
mechanism with no obvious file lands in the file whose line best covers it: the
loop needs prompt ids, `render_ids` needs `openai_harmony`, and this is the only
server the loop can reach that has it (7.1 shows why vLLM's `/tokenize` is not a
substitute). Part 9(a)#8 states the choice, its cost and its alternative.

**The precondition this imposes on every agent family.** `/render` runs
`render_ids` in the **probe** venv, while 7.1's render-equals-server check
compares it against a server in the **vllm** venv, so a family's rendering
library must be installed in both. gpt-oss satisfies this by accident —
`openai_harmony` 0.0.8 is in `external/probe-env` and `external/vllm-env`, per
the facts table — but a second family's library is an unstated precondition of
its own extension row otherwise, and the failure is an `ImportError` at the
start of every sample and inject run. 0.4's agent-family row now names it, and
`selfcheck` imports each family module under both interpreters.

**How the P4 coupling is avoided anyway.** The service reaches the agent family
through `models/__init__.py`'s `agent(alias)` and the tokenizer through the
weights path that `models/__init__.py` resolves from the same alias. It never
imports `models/agent_models/<family>.py` by name. A second agent family is
therefore still one file plus a table row, even though the rendering lives here
(dependencies P4, grounding F4).

**Client half** (standard library), constructed as `Client(base_url: str)` from
an endpoint file (7.4): `score(text)`, `generate(text, max_new)`,
`render(messages, effort, date)`, `encode(text, special)`, `decode(ids)`,
`health()`. `agent/loop.py` uses `render`; `agent/inject.py` uses the rest.

**How attach is verified, without naming a family.** Before its first request,
`agent/loop.py` refuses to run unless `/health` reports `render == "ids"`, **a
`family` equal to `cfg.models.agent_row["family"]` and a `weights` equal to
`cfg.models.agent_row["weights"]`** — the two keyed columns the loader expanded
its `models.agent` row into (5.2), read from its frozen `settings.yaml`, and the
two the server resolved live (6.2's exception). `agent/inject.py` refuses unless it also reports
`decode: true`, the capabilities its chosen `inject.format` needs — today that
is `encode_special: true` whenever `FORMATS[fmt].needs_special` is true — and
`score_train_key` / `gen_train_key` equal to the keys in its own
`settings.yaml`. Those are today's refusals
(`legacy/pipeline/inject/live_appworld.py:572-587`) with the key comparison
added and the two literals removed. *The failure this prevents: the old
refusals compared against `"harmony_ids"` and against a `p2_*` prefix, which are
gpt-oss's name and this table's spelling. A second agent family would make both
strings wrong and would force an edit to `agent/loop.py` and `agent/inject.py` —
contradicting 0.4's row and `agent/`'s own tree line, which says loop.py and
generate.py change for neither.*

## 7.3 The step interface, and what the loop does per step

**The one signature `generate.py` and `inject.py` share.** The whole claim of
the `agent/` layer — "the inject section present -> `inject.step`, absent ->
`generate.step`" (0.2) — is the claim that the two are substitutable, so the
signature is pinned here and is identical in both files:

```python
def step(env, clients, cfg, writer, messages, prefix_ids, history, task_text,
         step_index, seed) -> StepResult
```

`env` is the `Environment` object the loop opened; `clients` is the pair of
service clients the loop constructed from its endpoint files (7.4); `cfg` is the
frozen `Setting`; `writer` is the record `Writer` of 1.1; `messages` is the
conversation so far, which the loop rendered this step's ids from;
`prefix_ids` is that rendering; `history` and `task_text` are the probe's two
inputs from outside the current step; `step_index` and `seed` are this step's
index and the trajectory's seed.

**`agent/loop.py` owns all four parameters between `writer` and `step_index`,
and that is what makes the two implementations substitutable.**

- `messages` and `prefix_ids`: the loop holds the conversation and calls
  `probe_client.render(messages, effort, date)`
  **once per step**, then passes both the conversation and the ids down, so a
  step never reconstructs either. `generate.step` streams from it
  and `agent/inject.py` splices onto it (`prefix_ids + head_ids + note_ids`), so
  neither renders. *The failure this prevents: the pinned signature carried only
  `messages` while three places in this document (7.2's client-half line, 0.2's
  import lines, and the numbered list below) say the loop renders — so
  `generate.step` had to call `stream(clients, cfg, prefix_ids, seed)` and fill
  `StepResult.prefix_tok` and `prefix_sha` with ids it had no way to obtain, and
  `agent/generate.py`'s import line does not carry the probe client. The two
  spellings also cost two `/render` round trips per step.*
- `history` and `task_text`: the loop appends
  `(observation.action, observation.observation)` to a list after each
  `Environment.step` and passes the accumulated list — the pairs of the
  **earlier** steps, which is exactly what 1.7 defines — together with the `meta`
  row's `task_text`. Those are `probe_input.assemble`'s first two parameters, and
  without them on the signature `agent/inject.py` cannot build the probe's text
  at all. `generate.step` ignores both.

`StepResult` is a dataclass **declared in `agent/generate.py`** — the baseline
path owns it, and `agent/inject.py` already imports that file — carrying exactly
the `gen` row's non-derived fields: `reasoning`, `content`, `usage`, `wall_s`,
`finish_reason`, `stop_reason`, `prefix_tok`, `prefix_sha`, `gen_ids`,
`n_inject`, `discard`. `agent/loop.py` writes the `gen` row from it, which is
what makes 1.1's "who writes" division work: the loop owns `meta`, `gen`, `env`
and `final`, and `agent/inject.py` writes only `spec` and `resume` through the
same writer it was handed. On a sample run `n_inject` is 0 and `discard` is
zeroed.

`clients` is a dataclass declared in `agent/generate.py` beside `StepResult`,
with two fields, `agent` and `probe`, each a client object of 7.1 and 7.2;
`agent/loop.py` constructs it from its two endpoint files (7.4) and neither other
file builds one. **`probe` is annotated `object`, not the probe client class**,
so `agent/generate.py` imports `models/probe_models/service.py` nowhere and its
annotation line in 0.2 stays true; `agent/inject.py`, which does import that
file, is the only step implementation that calls through the field. *The reason it is pinned: it crosses three files and the
dataclass beside it is pinned down to its fields.*

**The stream `inject.py` iterates.** `agent/generate.py` exposes
`stream(clients, cfg, prefix_ids, seed)`, which returns the agent client's
iterator of `(text_delta, ids_delta)` pairs with its `close()` (7.1), so
`agent/inject.py` iterates generate's stream instead of building its own
request. That is the whole of the re-export named on `generate.py`'s tree line.

What the loop does per step, in terms of these calls, so that the two protocols
can be checked against one another:

1. **`agent/loop.py`** calls `probe_client.render(messages, effort, date)` ->
   `prefix_ids`, once, and hands the ids to `step` (above). Nothing below this
   line renders again.
2. `agent_client.stream(prefix_ids, generation, seed)` -> chunks;
   `agent/generate.py` accumulates text and ids and splits the reply into
   channels as it arrives, through the family's `parse`.
3. On a sample run that is all: at end of turn the step's `gen` row is written,
   the reply text is handed to `Environment.step`, which extracts the action and
   runs it (4.2), and the `env` row is written from the `StepObservation` it
   returns; a `completed` observation ends the trajectory.
4. On an inject run `agent/inject.py` iterates the same stream. It re-enumerates
   the cuts of the thinking **so far** on each chunk with
   `probe_input.cuts_live(thinking_so_far, cfg.build.min_think)` — the streaming
   rule of 1.7, which adds no terminal cut and does no thinning — scores each cut
   it has not scored before **once the thinking so far has reached
   `cfg.build.min_think`** (1.7's event-level gate in its streaming form), and
   stops scoring once it has scored `cfg.inject.max_cuts` of them. At each new cut it calls
   `probe_client.score(probe_input.assemble(task_text, history, thinking[:cut],
   cfg.build.hist_rounds, cfg.build.probe_result_cap))` (Part 1.7) — `task_text`
   and `history` being the two parameters the loop handed it; on the first
   confidence at or above `inject.theta` (or at the `fire_nth_cut`-th cut, under
   that arm) it closes the stream, calls
   `probe_client.generate(<the probe's text at the cut>, cfg.inject.max_new)`
   (7.2), completes
   the call through `Environment.complete_call`, `speculate`s it, builds the
   splice text through `agent/inject_format.py`, turns that text into ids with
   `probe_client.encode(note, special=FORMATS[fmt].needs_special)`, backs the
   head off to a token boundary — checked one id at a time with
   `probe_client.decode`, as `find_head` does today
   (`legacy/pipeline/inject/live_appworld.py:340-376`) — and starts a new
   request from `prefix_ids + head_ids + note_ids`.
5. The discarded ids go into the `spec` row; when the next fire or the end of
   the step arrives, the `resume` row records how much of the resent
   continuation matched them.

**What an entry of `FORMATS` is.** The table in `agent/inject_format.py` is a
module-level literal, `FORMATS: dict[str, Format]`, and an entry has exactly
four fields:

| field | type | meaning |
|---|---|---|
| `placement` | `"p1"` or `"p2"` | `p1` splices the body into the model's own reasoning; `p2` makes it a separate prefetch message |
| `needs_special` | `bool` | whether the body is encoded with real control tokens (`special=true`) or as plain text (`special=false`, the `p1` direction, 7.2) |
| `system_text` | `str \| None` | the extra system text this format needs, or None; **applied by `agent/loop.py` for a `p1` entry and by the family's `wrap_prefetch` for a `p2` entry, never both** |
| `render` | `render(call: str, exec_out: str, exec_ok: bool, error_kind: str \| None) -> str` | the body, written from the speculation result |

`agent/inject.py` reads those four fields and nothing else. For
`placement == "p2"` it passes the rendered body and `system_text` to the
family's `wrap_prefetch` (Part 6.2) and encodes the result; for `p1` it encodes
the rendered body directly.

**Who applies `system_text` for a `p1` format.** `agent/inject.py` offers one
more name, `system_text(cfg) -> str | None`, which returns
`FORMATS[cfg.inject.format].system_text` **only when that entry's `placement` is
`"p1"`**, and None otherwise — None for a `p2` entry, whose system text the
family's `wrap_prefetch` applies inside the prefetch wrapper, and None when the
setting has no `inject` section or its arm never fires. `agent/loop.py` passes
the result as `to_messages`'s `extra_developer` argument (1.1) on **every** call,
which is once per step, because the loop rebuilds the conversation from
`writer.frame()` each step and `to_messages` appends it to the developer message
inside itself. On a sample run and for a `p2` entry the argument is None. *The failure the condition prevents: an accessor that
returned the text for any placement would put a `p2` entry's non-null
`system_text` both in the developer message and inside `wrap_prefetch` — the
same text twice, different prompt bytes, and no error anywhere.* *The failure this prevents: without it a `p1` format's
`system_text` has no applier anywhere — inject.py cannot place it, because the
conversation's system message is built by `agent/loop.py` and rendered into
`prefix_ids` at the start of every step, before any fire, while inject.py starts
its resumed requests from spliced ids rather than from re-rendered messages. So
today's `p1_e2`-style format, an explanation carried in the system message, could
not be expressed, and adding one would cost an edit to `agent/loop.py`,
contradicting 0.4's "a sixth injection format is one entry plus one schema
value".* The call keeps `agent/inject_format.py` out of `loop.py`'s import list —
`loop.py` already imports `inject.py` — and the value is already in the inject key
through `inject.format`. That is the whole of the interface, which is what
lets 0.4 claim a sixth format is one entry plus one schema value: the entry's
author writes a `render` and picks a placement, and no other file learns its
name. A **new placement value**, unlike a new entry, costs one function in every
`models/agent_models/<family>.py`, which is why 0.4 counts it separately.
`selfcheck` compares `schema.py`'s `inject.format` literals against
`FORMATS`' keys, parsed out of the literal with `ast`.

## 7.4 Ports, endpoint files, and which replica a loop piece talks to

Nothing in this design lets a service pick its own port or a client guess one.
**`jobs/launch.py` assigns every service piece its port**, inside the same hold
of `runs.jsonl.lock` as the launch gate and the card reservation (2.5, 8.6), and
writes it into that piece's entry in the start row:

- an **agent service** piece is assigned in two ordered steps, and the order is
  the point. **First**, `jobs/launch.py` looks for an attachable server: a live
  registry row with a service piece of kind `agent` on this run's row's
  `serving.host` whose `service_agent_<replica>.json` claims the same `result:`
  block. If it finds one, it assigns that host and that port and passes
  `--attach-only` (7.1); that piece then takes no card and enters no card search,
  which is 3.4's fourth placement case, and 8.1 runs this test inside the lock
  hold before the reservation for exactly that reason. **Only when none is found**
  does it start a server, at
  its row's `serving.port` as the base with replica `i` at `base + i`; and only
  in that branch does a port already answering, or already held by a live
  registry row's piece entry, move the assignment to the next free one.
  *The failure the order prevents: with the relocation running first it always
  moves off exactly the port the attach test looks for, so `--attach-only` is
  unreachable — a second run wanting `gptoss120b` while a first still serves it at
  `tokyo108:8103` is assigned 8104 and launches a second 120B server on an
  occupied card, and the whole attach-verification mechanism of 7.1 is dead code.*
- a **probe service** piece takes the first free port at or above
  `PROBE_PORT_BASE`, a literal in `jobs/launch.py` (8500 today). The probe
  alias's `serving:` block in `models/table.yaml` is empty, so there is no port
  there to take, and `constants/` holds none.

Each service piece then writes its own `service_<kind>_<replica>.json` into the
run directory, carrying `base_url` among the fields of 1.5. One writer per file:
with `replicas` above 1 there are several agent-service pieces in one run
directory, and a single `service_agent.json` would be exactly the
many-writers-one-file hazard the heartbeat rule (8.4) exists to avoid.

**The name carries the replica index, not the piece index.** An agent service
piece writes `service_agent_<its replica number>.json`, counting from 0; the one
probe service piece writes `service_probe_0.json`. *The failure this prevents: a
piece index is an index into the run's whole piece list, loop pieces included, so
with `replicas: 1` and six loop pieces the service piece's index is not 0 and is
not anything a loop piece can compute; a loop piece that worked out
`i mod replicas` for itself still could not build the filename.*

**How a loop piece finds its endpoints.** Loop piece `i` computes
`i mod replicas` from its own `--piece i/n` and `settings.yaml`'s `replicas`,
opens `service_agent_<that>.json` and `service_probe_0.json` in its own run
directory, and reads **no other file** — no `meta.json`, no registry row, both
of which live on the login machine's side of the design. It waits for the two
files to appear (they are written before the alive check passes, so the wait is
short) and gives up after `registry.DEFAULTS["launch_timeout_s"]` (8.5), which it
reaches through the `jobs/registry.py` it already imports. `agent/loop.py`
constructs both clients: the probe client from its base URL alone, the agent
client from its base URL **and `cfg.models.agent_row["served_model_name"]`**, read
out of the same frozen `settings.yaml` it already holds (7.1) — so the one keyed
column the completion body carries enters from the frozen row and
`agent/generate.py` names no column. `agent/generate.py` and `agent/inject.py`
are handed the clients, and neither builds one. The `agent_replica` field on the
loop piece's entry in the start row (8.1) records the same number for `ls` to
print; the loop does not read it.

---

# Part 8. The registry — `jobs/registry.py`

Standard library and PyYAML only, imported by every stage, importing nothing from
the repo (0.1 already counts PyYAML inside `venv: any`, and this file parses
`constants/path_outputs.yaml` for the outputs root, `ls` and `free`).
That is what makes its position in the tree harmless: the layer order is a
reading order, and this file is a leaf.

The reviews want it split (synthesis 2, structure 5); the tree forbids that, so
the mitigations are: the writer functions and the reader functions sit in two
marked halves of the file, the README line names all eight importers, and **only
login-machine processes append to `runs.jsonl`** (8.6), which is the part of the
split that was about correctness rather than tidiness.

Terminology, settled here: the thing in `runs.jsonl` is a **registry row**.
"Record" means the task record and nothing else (lifecycle C2).

## 8.0 The names this file offers

This is the API eight programs call, split into the two halves the file is
written in. Without it each of them would invent its own call, and the
one-writer-per-file rules of 8.3 and 8.4 are enforced by this API alone.

**The writer half** — called by stages, on compute nodes and on the login
machine:

| name | signature | who calls it |
|---|---|---|
| `beat` | `beat(run_dir: Path, piece: int) -> Heartbeat` | every batch piece, once, before its main loop. It resolves `<launch>` from the run directory's own `heartbeat/` listing (8.4) and opens `heartbeat/<piece>-<launch>.jsonl` for append; it opens no `meta.json`, so 7.4's "a loop piece reads no other file" stands |
| `Heartbeat.emit` | `emit(done: int, total: int, unit: str, **extra) -> None` | the same piece, per beat; `extra` is the optional `tok_in`, `tok_out`, `loss` |
| `Heartbeat.finish` | `finish() -> None` | the same piece, once: the final beat with `status: "done"` |
| `write_done` | `write_done(run_dir, *, stage, key, commit, counts, versions, metrics, report, pairs=None, stage_extra=None) -> None` | the one-process stages for themselves (`data/build_training_dataset.py`, `train/utils/trainer.py`, `eval/utils/probe_eval.py`, `eval/score_run.py`), and `run.py` for `sample` and `inject` with `pairs` (2.3). It writes `done.json` through a temporary name and a rename |
| `write_meta` | `write_meta(run_dir, **fields) -> None` | `run.py` and `jobs/launch.py` only (8.3); it rewrites the whole file through a temporary name and a rename, under `lock()` like the two appends. `run.py` calls it for a CPU stage it starts in place — the run's `meta.json` and its `launches` entry — exactly as `jobs/launch.py` does for a tmux stage (2.3) |
| `lock` | `lock() -> ContextManager[None]` | `run.py` and `jobs/launch.py` (8.6), and `append_start`, `append_finish` and `write_meta` internally. **It is re-entrant by construction**: one module-level file descriptor per process plus a depth counter, the `fcntl` acquisition taken at depth 0 and released only when the outermost context exits, so a nested acquisition is a counter increment and never a second `fcntl` call. *The failure this prevents: `fcntl` record locks are per process and do not stack — a second acquisition on a second descriptor is granted without blocking, and the inner release, or the close of that inner descriptor, drops the process's lock on the file outright. A caller that believed it still held the lock would then append and re-render `RESULTS.md` unlocked, racing exactly the second session 9(c)#9 says is blocked* |
| `append_start` | `append_start(row: dict) -> None` | `jobs/launch.py` for a tmux stage, `run.py` for a CPU stage (2.3). Calls `lock()` unconditionally and re-renders `RESULTS.md`; a caller that already holds the lock gets the counter increment and nothing else |
| `append_finish` | `append_finish(run_id: str, row: dict) -> None` | `run.py` alone (8.2), the same way |

**The reader half** — called by `run.py` for its subcommands (8.6), and by
`jobs/launch.py` for the launch gate and the card reservation (2.5):

| name | signature |
|---|---|
| `ls` | `ls(workflow: str \| None = None, *, debug: bool = False, edited: dict[str, bool] \| None = None, progress: dict[str, tuple[int, int]] \| None = None) -> list[dict]` — one folded row per run, verdicts included. `edited` is the per-`run_id` map `run.py` computes and passes in, because this file imports nothing from the repo and so cannot call `key`; given None, `ls` leaves that column blank. `progress` is the same shape for a claiming stage: the per-`run_id` `(done, total)` that `run.py` computes with `data/trajectory_record.done_pairs` (1.1), for the same reason — this file cannot tell a done record from a claimed one; given None, `ls` shows the sum of beats (8.4) |
| `where` | `where(stage: str, key: str, *, debug: bool = False) -> Path` — the debug flag because a debug run lives under `<root>/<debug_subdir>/<stage>/<key>` and the root cannot be probed (3.1, 3.2 rule 2); the caller passes the `debug` field of the registry row the key came from (8.6) |
| `find` | `find(fields: dict) -> list[dict]` — what `run.py find` prints (8.6) |
| `kill` | `kill(run_id: str) -> list[str]` — the sessions it ended |
| `free` | `free() -> dict[str, list[int]]` — free cards per host, probed now |
| `sync` | `sync() -> list[str]` — the finish rows it wrote |
| `open_runs` | `open_runs() -> list[dict]` — the rows with a start and no finish; what the launch gate and the card reservation read |
| `live_sessions` | `live_sessions() -> set[str]` — one `ssh <host> tmux ls` per host of `constants/path_outputs.yaml`'s `hosts:` list, fail-closed per 3.4, so an unclear probe reports the session alive. It is the first of the two values `data/trajectory_record.release(dir, live_sessions, unowned_age_s)` takes, the second being `DEFAULTS["launch_timeout_s"]` (1.1, 8.5) — both passed in by this function's two callers, `run.py` and `jobs/launch.py`, so that format file imports no registry. It is also what 8.5's verdicts take as their liveness input |
| `session_alive` | `session_alive(host: str, session: str) -> bool` — the single-piece form, fail-closed the same way; `jobs/launch.refire` probes one session with it before it deletes that piece's claims (2.3) |

The verdict helpers of 8.5 are part of the reader half and are pure functions
over what these return.

*The failure the last two rows prevent: three mechanisms consume "which tmux
sessions are live" — the claim release of 1.1, the verdicts of 8.5 and refire's
own liveness refusal — and no name offered it, so either `run.py` grows an `ssh`
and a host list its 0.2 annotation does not carry, which `selfcheck` fails on, or
`run.py` and `jobs/launch.py` each write their own probe loop and 3.4's
fail-closed rule exists in two copies. This file already reads that host list and
already probes tmux for `ls`, so nothing new enters its dependency set.*

## 8.1 `jobs/runs.jsonl` — the start row

Append-only, one JSON object per line, never rewritten. Written once per stage
run by `jobs/launch.py`, or by `run.py` before it starts a CPU stage in place
(2.3).

**The order is fixed, because two mechanisms in this document depend on it.**
Inside one hold of `runs.jsonl.lock` (8.6): read the registry, run the launch
gate (2.5), **run the attach test of 7.4** — before the cards, so the reservation
already knows which agent pieces need one and which were matched to a live server
and take none (3.4) — read the card reservation, assign the ports (7.4), and
**append the start row with `status: "launching"`**. Then release the lock.

**What follows the release is two waves, not one.** Start the **service** pieces
and run the alive check on them; for an `inject` run, run the `check` client
against the probe service once its port answers (2.3, 7.2); and only then start
the **loop** pieces. The
start row already names the loop sessions, because it was written inside the
lock, so on a `service_check` outcome those entries stand for sessions that were
never created: `ls` reads them as dead pieces of a run that a `launch_failed`
finish row has closed (8.2), which is the same shape as any other launch that did
not come up. `jobs/launch.launch` returns
`(outcome, pieces)`: the outcome is `up`, or the reason it failed —
`alive_check`, or `service_check` when the probe service's `check` client exits
non-zero (2.3, 7.2) — and the piece entries come back either way, so the row
names the sessions that were started. **Before it returns any outcome but `up`,
`jobs/launch.launch` calls `teardown_services(run_dir)`** (2.3) and records in
the returned piece list which sessions it ended, so a failed launch leaves no
service piece holding cards for a run that a `launch_failed` finish row has
already closed; the `attached_to` skip rule still spares a server another live
run attached to. **A piece that dies before it starts still
leaves a row**: on anything but `up`, `run.py` appends a **finish** row
with `status: "launch_failed"` (8.2) — the start row is never rewritten, because
rows are append-only (the second half of lifecycle A3). *The failure the return
type prevents: with only the piece list coming back, `run.py` cannot tell a
launch that came up from one that did not, and there is no channel for either
failure path.* A `launching` row whose
start is older than `registry.DEFAULTS["launch_timeout_s"]` (8.5) and whose
sessions are not up is turned into `launch_failed` the same way on the next `ls`.

*The failure the order prevents: the alive check needs the sessions, so a row
written "after the alive check" is written after the sessions exist — and the
card reservation of 2.5 counts a card busy only when it is in a live row's
`pieces` list. At the moment the second sweep child takes the lock, the first
child's cards would then be in no row at all and would be reported free. That is
exactly the collision 9(c)#6 asserts is prevented, and the same hole lets two
sessions seconds apart take one card (9(c)#9). Appending inside the hold, with
`launching`, closes it; the reservation's second clause (2.5) is what covers the
window between the append and the sessions.*

| field | type | meaning |
|---|---|---|
| `ev` | str | `start` |
| `t` | str | local time, `YYYY-MM-DD HH:MM` |
| `run_id` | str | `<stage>-<key>`; the primary key, equal to the directory's tail and to the tmux session prefix |
| `stage`, `key`, `dir` | str | the stage, its key, its absolute run directory |
| `workflow`, `setting` | str | the workflow **file**'s name — not the stage list, which is `cfg._workflow` (5.1) — and the named setting that asked for it; the child name for a sweep child |
| `parent`, `swept` | str, dict | the sweep parent and the swept field values, for `method_table.py`; null otherwise |
| `debug` | bool | a debug run |
| `upstream` | dict | upstream or reference name -> key |
| `versions` | dict | module -> `VERSION`, as folded into the key |
| `diff` | dict | `settings_diff.yaml` as JSON: what the key was computed over, and what `run.py find` searches |
| `commit`, `branch`, `dirty`, `dirty_count`, `dirty_files` | str/str/bool/int/list | the git state at launch, fail-closed (a failed git probe counts as dirty), from `legacy/ops/record.py:58-83` |
| `host` | str | the login machine that launched |
| `pieces` | list | one entry per piece: `{index, kind, host, gpus, session, pid, log, port, endpoint_file, agent_replica, venv, cmd}`; `kind` is `loop`, `train`, `cpu` or `service`; `host` is where 3.4's placement rule put it; `venv` is a key of the `venvs:` map (6.3); `session` is set on a tmux piece and `pid` on a `cpu` piece, which `run.py` starts in place and therefore knows the pid of (8.5 judges it by that pid, 8.6 kills it by it); `port` and `endpoint_file` (`service_<kind>_<replica>.json`, 7.4) are set on a service piece and `agent_replica` on a loop piece, both for `ls` to print |
| `status` | str | `launching`, always. The row is never rewritten, so what became of a run is its verdict (8.5) while it is open and its finish row (8.2) once it is closed; a launch that never came up is closed by a `launch_failed` finish row |

## 8.2 `jobs/runs.jsonl` — the finish row

Written by `run.py` alone, in five places: when a walk first sees `done.json`
without a finish row (`ok`); when `run.py kill` ends a run (`killed`); when
`jobs/launch.launch` returns anything but `up` — a failed alive check or a
failed `service_check` — or when a `launching` row ages past
`registry.DEFAULTS["launch_timeout_s"]` (8.5)
with no sessions (`launch_failed`, 8.1); when `run.py sync` finds a run with no
`done.json` **whose pieces `judge` calls `dead`** (`failed`); and when a stage
`run.py` started in place exits non-zero (`failed`, 2.3), which it appends
immediately, inside a fresh hold of the lock it used for the start row.
*The failure the fourth writer prevents: `failed` was in the enum
with nothing in the document writing it, and 1.5 says failure is not a file, so
a dead run would stay open in `runs.jsonl` and in `RESULTS.md` forever. The
reason it is stated as `judge`'s verdict and not as "sessions gone **and**
heartbeat stale **and** no `done.json`": 8.5 already ranks `dead` — the per-kind
liveness test — above `suspected stall`, and its stall line is
`DEFAULTS["warmup_s"]` while a piece has too few beats, so a piece that died
before its first beat is not stale for half an hour and the conjunction leaves
its row open for that long. The fifth writer covers the case the walk cannot
reach at all: `run.py` holds the pid of a `build`, `eval` or `score` process and
sees the non-zero exit itself.*

| field | type | meaning |
|---|---|---|
| `ev` | str | `finish` |
| `t`, `run_id` | str | when, and which run |
| `status` | str | `ok`, `failed`, `killed`, `launch_failed` |
| `counts` | dict | what the stage produced, from its `done.json`: records done, example rows, train steps, events evaluated |
| `metrics` | dict | the stage's headline numbers, copied verbatim from `done.json`'s `metrics` (1.5) |
| `report` | str | `done.json`'s `report`: the report file inside the run directory, or null |
| `elapsed_s` | float | from the start row's time |

**The finish row is built from `done.json` alone.** Every field above is copied
out of it, so `run.py` opens no report and needs no reader for
`run_report.json` or for a train log — which is why `run.py`'s `reads:` line is
short and stays short (1.5).

**A stage that always recomputes gets a new finish row each time.** `eval` and
`score` rewrite their own `done.json` inside the same key (2.4), so `run.py`
appends a new finish row whenever `done.json`'s `finished_at` is later than the
newest finish row for that `run_id`. A later finish row for the same `run_id`
wins, so `RESULTS.md` and `run.py find` show the most recent computation.

**One `run_id` can also collect several start rows** — a relaunch after a dead
train piece (9(c)#3), a wider seed request into a shared `sample` directory
(2.3), every `eval` or `score` rerun (2.4) — and rows are never rewritten. So:
**for a given `run_id` every reader takes the newest start row and the newest
finish row**, `elapsed_s` is measured from the newest start row preceding that
finish, and `registry.ls` folds the newest start row's `pieces` list.
*The failure this prevents: the first eval's numbers standing in `RESULTS.md`
for code that has since changed, because a finish row already existed.* `RESULTS.md` is rendered from the
whole file by `registry.py` on every append and is never edited by hand. A run's
one-sentence conclusion does not live here: a conclusion is about a direction
and belongs in `notes/TIMELINE.md`, which is a person's file (lifecycle C3).

## 8.3 `meta.json`

One per run directory, rewritten (not appended) by `registry.py`:

| field | meaning |
|---|---|
| `meta_version` | this file's own version |
| `stage`, `key`, `dir` | identity |
| `versions`, `upstream`, `diff` | as in the start row |
| `debug` | a debug run |
| `owners` | every `{workflow, setting}` that has run into **or reused** this directory. A reuse is the ordinary case for a shared `sample` or `build` directory — six sweep children, a second `train.lr` setting — and a skipped stage never launches, so `run.py` adds the setting on the skip itself, under the lock it already takes (2.3) |
| `launches` | append-only, one entry per launch or refire: `{t, host, commit, branch, dirty_count, dirty_files, cards, pieces, cmd}` — this absorbs today's `RUNMETA.json` (lifecycle B6) |
| `pieces` | the piece list, each with its frozen command, which is what `run.py refire` re-runs. **`jobs/launch.refire` rewrites the refired piece's entry here** — `host`, `gpus`, `session`, `pid`, `cmd` — through `registry.write_meta`, inside the same lock hold as its `launches` entry, because a refire probes the cards again and may place the piece on another host while the start row that named the old one is append-only (8.1). This entry is therefore the current truth about a piece, and `ls`, `kill`, `refire` and the card reservation read `host` and `session` from it (8.6) |
| `split_files` | sample and inject: for each split file read, its path, sha1 and the resolved task-id list. **Resolved and written by `jobs/launch.py` before the pieces start**, so that the hash gate of 2.3 can tell whether a split file has changed under a finished directory and a person can see which ids a launch resolved. It is **not** where the requested (task, seed) list comes from: `run.py` calls `requested_pairs` for that, because this field records the launch that wrote it and not the request being walked now (2.3) |
| `stage_extra` | a free object; `train` puts the class order (`labels`) there. The stage writes it into its own `done.json` and `run.py` folds it in here on its walk (1.3), so this file keeps exactly two writers |

**`meta.json` is written only by login-machine processes** — `run.py` and
`jobs/launch.py` — through `registry.py`. A compute node writes only its own
heartbeat file, its outputs, and `done.json` when it is a one-process stage. A
piece reports progress **into its own `heartbeat/<piece>-<launch>.jsonl` and nowhere
else**, and `ls` folds those files in (8.5's verdict functions already take the
beat history). *The failure this prevents: six loop pieces read-modify-writing
one JSON file on NFS with no lock, losing each other's updates and leaving a
truncated file behind — which would then break `ls`, `run.py refire` (the frozen
piece commands are in that file) and the completeness walk. It is the same
failure the single-writer heartbeat rule was introduced to prevent, and there is
no second mechanism for it: the heartbeat's last line already carries `done`,
`total`, `unit`, `ts` and `status`.*

**Every rewrite is taken under the same `runs.jsonl.lock` hold as the registry
append that accompanies it, and is written through a temporary name in the same
directory and renamed.** The file has two writers and is rewritten whole, which
is the read-modify-write hazard the single-writer heartbeat rule exists to
avoid; the lock of 8.6 is what stands in for a single writer here, and the
rename is what keeps a killed writer from leaving a truncated file. *The failure
this prevents: two walks over one directory, or a walk folding `stage_extra`
while a refire appends a launch entry, losing an update or truncating the file —
which then breaks `ls`, `refire` (the frozen piece commands live here) and the
completeness walk.*

There is no `inputs` field. What a stage read is recorded in exactly one place,
`consumed.json` (1.5).

## 8.4 The heartbeat

Today's line format, kept exactly (`legacy/ops/heartbeat.py:15-33`), because the
verdict rules are written against it:

```
{"done": 12, "total": 400, "unit": "task", "ts": 1758000000.0,
 "tok_in": 1234, "tok_out": 567, "loss": 0.42, "status": "done"}
```

`done`, `total`, `unit` and `ts` are required; `tok_in`, `tok_out`, `loss` and
`status` are optional. `ts` is the writing machine's clock and is only ever
diffed against another `ts` from the same machine. `unit` is the stage's own
word: `task` for sample and inject, `step` for train, `row` for build, `item`
for eval, and `task` for score, which walks the records of the run it scores.

Two changes from today: the line goes into
`<run_dir>/heartbeat/<piece>-<launch>.jsonl`, one line per beat, as well as to
stdout, so the monitor does not parse a log tail; and **one file has exactly one
writer**, so no lock is needed on NFS. Every batch piece opens its file with
`registry.beat(run_dir, piece)` and emits `emit(0, total, unit)`
before its main loop — the signal that the model has finished loading — then one
beat per unit of work, then `finish()`, which writes the final beat with
`status: "done"` (8.0).

**`<launch>` is `1 +` the largest `n` for which `heartbeat/<piece>-<n>.jsonl`
already exists in this run directory, and `0` when none does**, so a refire of
piece 3 writes `heartbeat/3-1.jsonl` beside the dead incarnation's
`heartbeat/3-0.jsonl`. A piece may list that directory because it is the only
writer under its own prefix. *The reason the index is not read out of
`meta.json.launches`, which is where it looks as if it should live: 7.4 states
that a loop piece reads its two endpoint files and no other file — no
`meta.json`, no registry row, both of which are on the login machine's side of
the design — and one `launches` entry covers many pieces, so "the piece's entry
number" would also have to be defined as the newest entry whose `pieces` list
contains this index.*

**A one-process stage is piece 0.** All four of them — `build`, `train`, `eval`
and `score` — carry no `--piece` on their command line (2.1's program column,
2.6, 3.4), so each calls `beat(run_dir, 0)` and opens
`heartbeat/0-<launch>.jsonl` like any other piece. *The failure this prevents:
`train` is a one-process stage with a `main(run_dir)` and a card, and with the
rule stated over three stages nothing says which index
`train/utils/trainer.py` passes, so its heartbeat file has no resolvable name.* `ls` takes the last line of each piece's **newest**
heartbeat file and shows the sum of beats, **except for a claiming stage
(`sample`, `inject`), where it prints the `(done, total)` pair `run.py` handed it
in `progress`** (8.0), and falls back to the sum of beats when no such pair was
supplied. *The failure this
prevents: one file per piece index means a refired incarnation appends to
the dead one's file starting from `done: 0`, so a `sample` run that had finished
40 of 400 tasks displays as 2; and "one writer per file" stops being literally
true the moment a piece is refired.*

**What `total` means for a claiming piece.** A `sample` or `inject` loop piece
cannot know its own share in advance, because work is claimed by race (1.1). So
`total` is the **whole requested (task, seed) count**: every piece of the stage
reports the same total and its own `done`. That makes `done >= total` unreachable
for one piece, which is deliberate — a claiming piece's `done` verdict comes
from its final beat's `status`, and the stage's progress `ls` shows is the count
of done record files in the directory against that one total, which is correct
across a refire where a sum of beats is not. A **service** piece emits none:
vLLM is a third-party program that would not, and our own probe service has no
progress to report, so both are judged by their port instead (8.5). **A service
piece's launch time comes from its entry in the start row**, which is what lets
`judge_service` have a warm-up window without a heartbeat. That is also why
neither service imports `jobs/registry.py`.

## 8.5 Verdicts

Pure functions over (the piece's heartbeat history, its liveness, its kind), in
`registry.py`, ported from `legacy/ops/verdicts.py` without a change of
behaviour. Six values in a fixed priority order — `done`, `dead`,
`suspected stall`, `warming up`, `slowed`, `healthy` — which is CONTEXT's
vocabulary; the verdict is computed by the program and never guessed by an
agent.

| function | signature | rule |
|---|---|---|
| `typical_gap_s(beat_ts)` | `list[float] -> float \| None` | the median of the last 20 intervals; None below 3 intervals |
| `stall_line_s(beat_ts)` | `-> float` | `max(5 x typical gap, DEFAULTS["stall_line"])`; while there are too few beats, `DEFAULTS["warmup_s"]` |
| `rates(first_beat, recent_beats)` | `-> (avg, recent)` | done per second, over the whole run and over the last 10 beats |
| `judge(piece)` | `dict -> (verdict, escalated)` | `done` when `status == done` or `done >= total`; else `dead` when the piece is gone (the liveness test is per kind, below); else `suspected stall` when the beat age is past the stall line; else `warming up` before the first beat and within `DEFAULTS["warmup_s"]`; else `slowed` when the recent rate is below half the average; else `healthy`. `escalated` is true when the stall has lasted past `DEFAULTS["escalate_line"] x` the stall line |
| `judge_service(piece)` | `dict -> (verdict, escalated)` | over the piece's **start-row time**, its session liveness and **one port probe**, because a service piece emits no heartbeat (8.4) and there is no sampling history any more (9(a)#13): `dead` when the session is gone; `healthy` when the port answers; `warming up` when it does not answer and the piece's launch time is inside `DEFAULTS["warmup_s"]`; `suspected stall` when it does not answer past that, with `escalated` past `DEFAULTS["escalate_line"]` times it |

**Liveness is per kind.** A `loop`, `train` or `service` piece is alive while its
tmux session is — the set being `live_sessions()`'s (8.0), fail-closed as 3.4
says. A `cpu` piece has no session — `run.py`
starts `build`, `eval` and `score` in place — so it is alive while
`os.kill(pid, 0)` on `login_host` succeeds, against the `pid` its start-row entry
carries (8.1). Everything else in `judge` is unchanged. *The failure this covers:
with tmux as the only liveness signal, every in-flight `build`, `eval` and
`score` run reads `dead` from the moment it starts, and kind `cpu` falls through
`judge_service` as well.*

*The failure the `judge_service` restatement prevents: the old rule — "`suspected stall` after
three consecutive rounds of no answer", "`warming up` before the first answer" —
counts rounds and remembers a first-answer time, both of which lived in the
resident sampler's sampling history. `ls` computes a verdict on demand from one
pass, so it could never reach a third round and a hung service would be reported
`warming up` or `healthy` forever.*

**`DEFAULTS` holds every one of those numbers, in one dictionary**, so each is
written down once and changes only by an edit to this dictionary — CONTEXT's
monitoring parameters, kept. There is no per-piece override: nothing anywhere
would produce one (no setting field, no command-line flag), so the three optional
keys an earlier draft put on the start row's piece entry named a mechanism that
could never fire, and they are gone (8.1):

| entry | value | what it is |
|---|---|---|
| `stall_line` | 180 s | the floor under `5 x typical gap` in `stall_line_s` |
| `escalate_line` | 3 | multiples of the stall line at which `escalated` turns true |
| `warmup_s` | 1800 s | how long a piece may take to reach its first beat, and the stall line while it has too few |
| `launch_timeout_s` | 1800 s | how long a piece may take to exist |

`launch_timeout_s` is the one entry **no piece overrides**: it is a launcher
constant, not a monitoring one. Its value is the warm-up cap because both measure
the same thing. Five rules read it and each names
`registry.DEFAULTS["launch_timeout_s"]` rather than "the launch
timeout" — 1.1 (`run.py` and `jobs/launch.py` pass it into
`release(dir, live_sessions, unowned_age_s)` as the margin an unowned record
file is deleted after), 2.5 (a card stays busy under a start row younger than it, and the launch
gate refuses under the same clause), 7.4 (a loop piece gives up waiting for its
endpoint files after it), 8.1 and 8.2 (a `launching` row past it with no sessions
becomes `launch_failed`). *The failure this prevents: the
constant was named in five places and defined in none, so `run.py`,
`jobs/launch.py`, `jobs/registry.py` and `agent/loop.py` would each invent a
value — and a release that picked a shorter one than the launcher deletes a live
piece's claimed record mid-task, which is exactly the race 1.1's age margin
exists to prevent.*

What is gone: the resident sampler, the sampling history, the web page, the
incident agent, the autopsy and the escalation line's automatic consequence.
`run.py ls` computes the verdicts on demand from the heartbeat files and one
`tmux ls` per host over the `hosts:` list of `constants/path_outputs.yaml`
(6.3, fail-closed as 3.4 says); `escalated` survives as a flag `ls` prints, not as something
that starts a process. Part 9(a)#13 states this as a decision the owner can
veto, and it is the one change in this document that makes several CONTEXT.md
entries obsolete in the same commit.

## 8.6 The subcommands, the lock, and who may append

| subcommand | prints |
|---|---|
| `run.py ls [workflow]` | one line per run, folded from the **newest** start row and the newest finish row for that `run_id` (8.2), with each piece's current `host` and `session` taken from `meta.json`'s `pieces` list (8.3) and the start row used only for the launch time and the frozen request: `run_id`, stage, the names that own it, verdict per piece, progress (`done/total unit` and a rate, from the `progress` pair for a claiming stage and from the beats otherwise, 8.0 and 8.4), the heartbeat's age, the sessions and cards, and a flag column: `edited` (the named setting's current key no longer matches this directory; computed by `run.py` and passed in, 8.0), `behind` (a folded module's `VERSION` is ahead of the directory's), `consumed` (an upstream file's hash no longer matches `consumed.json`), `split` (a recorded split file has changed), `pinned` (a reference was given as `key:` or `dir:`, so the inheritance check and the shared-build-key gate were skipped, 5.4), `dirty`, `debug`, `orphan` (a tmux session of this repo matching no row, or a service piece still running after its owner run finished — either because a live run's `service_<kind>_<replica>.json` names that `run_id` in `attached_to` and the teardown skipped it, 2.3, or because the teardown failed) |
| `run.py where <workflow> <setting> <stage>` | the absolute run directory, whether or not it exists. It computes the path with `schema.run_dir`, which has the setting and therefore the `--debug` flag; `registry.where(stage, key, debug=…)` is used only for a key read out of a registry row, and the `debug` of that row is what it is passed (8.0) |
| `run.py find section.field=value …` | the rows whose `diff` matches every given field, newest first |
| `run.py kill <workflow> <setting> <stage>` | the pieces it ended, and writes the `killed` finish row; a tmux piece by its session, a `cpu` piece by its `pid`, both read from `meta.json`'s `pieces` list (8.3) rather than from the start row, which a refire may have left behind; refuses while any live run's `service_<kind>_<replica>.json` names this `run_id` in `attached_to` (7.1) |
| `run.py refire <workflow> <setting> <stage> [--piece i]` | the piece it restarted: it resolves the setting and the run directory, takes the dirty gate and re-freezes `_commit` as a first launch does, and calls `jobs/launch.refire(run_dir, git, piece)`, whose liveness refusal, claim release, card re-probe, launch entry and warn-without-quota are all in 2.3 |
| `run.py table [workflow]` | the backbone x method table, grouped by `parent`, with mean and spread. That file is not a stage, has no `__main__` and no run directory, so this is how its numbers are read, and the call that crosses the file boundary is pinned: `eval/method_table.table(workflow: str \| None = None, out: Path \| None = None) -> str`, which returns the rendered markdown and also writes it when `out` is given |
| `run.py retry <workflow> <setting> <stage>` | "start fresh" (2.4): it clears the directory of what the continue rule would resume from, then launches normally, so no flag rides on the piece command |
| `run.py free` | free cards per host, over the `hosts:` list of `constants/path_outputs.yaml`, probed now and never cached, under the busy test of 2.5 |
| `run.py sync` | folds every directory's `done.json` and heartbeat files into missing finish rows, writes the `failed` finish row of 8.2, and re-renders `RESULTS.md` |
| `run.py selfcheck` | the README's file list against the tree; every annotation line against the real import graph, parsed with `ast`; every axis literal against the files behind it; one integer `VERSION` line per module the stage table names, and one literal apiece for the names of 3.3's literal rule (`PROBE_KIND`, `STOP`, `EFFORTS`, `DEFAULT_EFFORT`, `DEFAULT_DATE`, `LORA_TARGETS`, `CHECKPOINT_META`, and `INSTRUCTIONS` and `SPLIT_ROLE` in every `data/environments/<env>.py`, 4.1); a `DEFAULTS` and a `REQUIRED` literal in every format file under `data/`, with every name in `REQUIRED` a column that file's schema declares (Part 1); the two `PROBE_KIND` declarations of a method equal to each other (2.6); every family's `DEFAULT_EFFORT` a member of its own `EFFORTS`, or both empty (5.3); every `models/table.yaml` row's `family` resolving to a file under `agent_models/` or `probe_models/` per its `role`, and its `weights` alias present in `constants/path_models.yaml`; no `/home/` or `/net/` path in code outside `constants/`; each `any` file imported under **every** interpreter of the `venvs:` map (6.3); and each family module imported under the probe and the vllm interpreter (7.2) |

`ls` is the only place a verdict is produced, and `find` is the only way to ask
"which runs used this value", which works because the start row carries `diff`.

**One machine, named.** `run.py` and `jobs/launch.py` **refuse to run on any
host but `login_host`**, the key in `constants/path_outputs.yaml` (6.3), and say
which host that is. Remote work is reached only over ssh from there (3.4).
*The failure this prevents: the whole concurrency story rests on "`runs.jsonl` is
appended only by processes on the login machine" with an `fcntl` lock, but the
repo — `jobs/runs.jsonl.lock` included — lives in `/home/y-guo`, which the facts
section records as NFSv3, and `constants/path_outputs.yaml` lists four hosts a
person can ssh into. Two `run.py` invocations on two hosts would take that lock
over NFSv3, which no measurement in this document covers, both pass the launch
gate and both launch into one run directory. 9(c)#9 assumes "the same login
machine"; this is what makes it true.*

**The lock.** `runs.jsonl` is appended only by `run.py` and `jobs/launch.py`,
both on that machine, and both reach it through `registry.lock()`, the re-entrant
context manager of 8.0 — one module-level descriptor per process and a depth
counter, so a nested acquisition never takes a second `fcntl` lock and never
drops the outer one.
**`run.py` takes it before it calls `jobs/launch.git_state` and freezes a run
directory** — in that order, since `freeze` writes `git_state`'s commit into
`_commit` (3.4, 5.1) — so `settings.yaml` and `settings_diff.yaml` are written
under the same serialisation as the gate. The span is the one 8.1 fixes:
`git_state`, the freeze, the launch gate, the attach test, the card reservation,
the port assignment and the start-row append, **released before any tmux session
is started**; `jobs/launch.py`'s own hold falls inside it as a counter
increment.

**`jobs/launch.py` holds it across more than the append.** One hold covers:
read the registry, evaluate the launch gate (2.5), run the attach test (7.4),
read the card reservation, assign the ports, and append the start row with
`status: "launching"` (8.1); the lock is released only
after that row is on disk, and the two waves of tmux sessions and the alive check
follow afterwards. A `meta.json` rewrite that accompanies an append is taken inside the
same hold (8.3).
*The failure this prevents: two `run.py` calls on the login machine starting
within the same second, both reading a file with no start row for the key, both
passing the gate, both appending, and both launching pieces into one run
directory — which is exactly what scenario 9 says cannot happen, and what a lock
scoped to the append alone does not prevent.*

Stage processes on compute nodes write **only** into their own run directory:
their heartbeat file, their outputs, and `done.json` when they are a one-process
stage. They take no lock at all, which removes cross-host `fcntl` locking on NFS
from the design (lifecycle B11) without splitting the file.

---

# Part 9. Decisions, proposals and their alternatives

## 9(a). Choices the owner could reasonably veto

Each line: the choice, the alternative it beat, why this one.

1. **The example row is method-independent** — one row per cut carrying `tool`,
   `call` and `args`; alternative: one example file per method, as today's build
   writes. Chosen because it takes `data/build_training_dataset.py` and `data/training_data.py`
   off the "fourth probe method" list and lets one build serve three methods; it
   costs unused columns and a parquet about 15% larger.
2. **The prediction row is method-independent and the generators predict at
   every cut row**; alternative (today's): generate only at the rows a ctool
   run's frozen theta selects. The owner already decided this; the construction
   plan measures the cost in the smoke, since today's `eval_causal_call.py`
   generates at most 8,533 rows where every row would be 507,104. The fallback
   is written down and not built: a `train.predict.trigger_run` field naming the
   ctool run whose theta selects the rows, which moves the filter back before
   generation.
3. **The key is the diff from the schema defaults**, not the resolved values;
   alternative: hash the resolved sections. Chosen because it makes "add a
   hyperparameter" free, which is the most frequent extension, and because the
   tree's own `schema.py` line assumes it; it costs the hand-kept rule that
   changing an existing default needs a `VERSION` bump.
4. **`run_dir` and `key` live in `experimental_settings/schema.py`**;
   alternative: `jobs/registry.py`. Chosen so `data/`, `train/` and `eval/`
   resolve paths without importing the top layer.
5. **`run_dir` never reads the output tree**, so `build`'s key folds the sample
   *key* and the requested subset rather than the consumed files' hashes;
   alternative: hash the input files into the key. Chosen so a key is computable
   before anything has run (sweeps, `where`, dry runs); the hashes go into
   `consumed.json` and `ls` checks them instead.
6. **`VERSION` is read out of a module's source text** by `schema.py`;
   alternatives: import the module (which breaks principle 7 the first time
   `eval/` computes a train key, because `trainer.py` needs torch), or list
   every number in `schema.py` (which moves the number away from the file a
   person edits).
7. **The temperature reaches the probe service through the frozen setting.**
   `run.py` reads the referenced classifier eval report through
   `probe_eval.read_report`, `schema.freeze` writes it into `settings.yaml` under
   `_resolved`, and `jobs/launch.py` puts it on the service's command line;
   alternatives: the service reads the report itself (today's, and an upward
   `models -> eval` import), or `jobs/launch.py` reads it (which makes the jobs
   layer import the eval layer). Chosen so `models/` and `jobs/` both stay clear
   of `eval/` outputs and a live run's calibration is visible in its own
   directory.
8. **Rendering, encoding and decoding stay on the probe service.**
   Alternative: move them onto the vLLM server through `/tokenize` and
   `/detokenize`. Rejected on two measured facts: vLLM 0.26.0's tokenize request
   has no `split_special_tokens`, so the `special=false` direction that every
   `p1` format needs cannot be expressed; and `/tokenize {messages}` for a
   gpt-oss model takes the jinja path, not harmony, which is the path the
   2026-08-18 investigation abandoned. The price is stated: a `sample` run
   starts one extra CPU process (the probe service in `--render-only` mode,
   today's flag), and the probe service holds the agent model's tokenizer. The
   P4 coupling is paid off a different way (7.2): the service reaches the family
   only through `models/__init__.py`, so a second agent family is still one file
   plus a row.
9. **The probe service returns a confidence; `agent/inject.py` compares it with
   theta**; alternative: the service returns `fired`, as today. Chosen so the
   fire rule lives in one place, the one that also knows the arm,
   `fire_nth_cut` and `max_inject_per_step`.
10. **Model aliases are validated against `models/table.yaml`, not an axis in
    `schema.py`**; alternative: an axis, per the "register every value" rule.
    Chosen so there is one list of legal model names. The table is covered by
    the read-only hook, which is also the answer to the fourth draft's open
    question.
11. **The run directory is named by the key alone**; alternative: include the
    setting name. Chosen because one key can be reached from several settings
    and two names would mean two directories; `ls` and `where` carry the names.
12. **`eval` and `score` always recompute inside their key**; alternative: skip
    when done, like the GPU stages. Chosen because they cost seconds and because
    a silently reused stale number is the failure principle 7 exists to prevent.
13. **The sampler, the web page, the incident agent, the autopsy, the sampling
    history and the escalation consequence are retired**; `run.py ls` computes
    verdicts on demand. The owner named this. It is repeated here because it
    makes eight CONTEXT.md entries obsolete (sampler, window, escalation line,
    incident agent, autopsy, incident record, sampling history, and the
    sampler's half of the verdict entry), and those entries must be rewritten in
    the same commit or the glossary will describe a process that does not exist.
14. **Six verdicts with the adaptive stall line, not four with a constant**;
    alternative: `done`/`dead`/`stalled`/`running` over one 1800 s line. Chosen
    because CONTEXT defines six, because the heartbeat file is a jsonl and
    therefore still carries the history the adaptive line needs, and because
    `warming up` is what keeps a model-loading piece from being called stalled.
15. **`venv: any` includes NumPy**, which means installing NumPy into
    `external/appworld/venv` (a dependency-free wheel, exactly as Polars was);
    alternatives: mark `eval/` as `venv: probe` (a deviation from the tree's
    eval line), or ban NumPy and rewrite the temperature fit as a golden-section
    search over `log T` in Polars expressions with a pure-Python bootstrap.
    Chosen because it keeps the tree's line literally true and keeps the fit an
    ordinary 1-D minimiser; today's fit is torch LBFGS
    (`legacy/pipeline/eval/eval_tool.py:213-224`) and its numbers are re-derived
    under the new one either way.
16. **A partial task record is deleted and the task redone**; alternative:
    resume a trajectory mid-task. Chosen because the world state dies with the
    process, and because deleting also removes the half-written last line that
    would break a strict Polars read.
17. **A `final` row with a non-null abort counts as done**; alternative: require
    `abort` to be null. Chosen because otherwise a task that aborts every time
    is deleted and redone forever; `build.max_abort_frac` is what protects the
    dataset instead.
18. **`run.py` on the login machine writes `done.json` for `sample` and
    `inject`**; alternatives: the first piece that sees no work left (which
    makes a compute node scan the whole directory over NFS, and leaves the run
    un-done forever if the last piece dies just after finishing), or "whoever
    observes it first" (which leaves the finish row without an owner).
19. **The control arms are one axis (`inject.arm`)**; alternative: independent
    booleans. Chosen because four booleans can be set to contradict each other,
    and because an arm is a named experiment in CONTEXT's vocabulary.
20. **The sample and inject keys exclude the task and seed lists**;
    alternative: include them, so a directory is exactly its request. Chosen
    because a fourth seed then costs one seed of collection instead of four; the
    consumers put the lists in their own keys and refuse until every requested
    pair is present.
21. **The method file is the program and `trainer.py` is the library** (the
    hooks in Part 2.6); alternative: `trainer.py` as the program, dispatching on
    `probe.method`. Chosen so `trainer.py` never branches on a method and a
    fourth method adds no line to it.
22. **`reference_loss` is a hook on each method file**, not a shared
    `train/reference.py`: the tree drops that file and keeps the alignment gate,
    which would otherwise have nothing to compare against. This is the one place
    where the contract asks for code to be written twice on purpose.
23. **`train`'s key folds `eval/methods/<m>.py`'s VERSION**; alternative: leave
    it out. Chosen because the tree's `eval/methods` line makes the eval match
    function the train validation metric, so it decides which checkpoint becomes
    `best/`; the price is that an eval match fix reruns training, and the
    structural fix that would remove the price is 9(b)#9.
24. **The instruction text is an axis value (`data.instructions`)**, not a code
    edit guarded by a `VERSION`; alternative: the fourth draft's wording. Chosen
    because a prompt variant is the value most likely to be varied and should
    enter the key by name like any other varied value.
25. **`generation.date` is passed to the vLLM server as
    `VLLM_SYSTEM_START_DATE`** and the render-equals-server check proves it took
    effect; alternative: leave the server on its own clock and pin the date only
    on the client. Chosen because the server would otherwise render a different
    system message on a different day
    (`vllm/entrypoints/openai/parser/harmony_utils.py:133-139`).
26. **Dropped, each because its only consumer is gone**: the resident sampler
    and its web page and incident half (retired above, with the CONTEXT entries
    named); the offline replay line (`legacy/pipeline/inject/replay_inject.py`
    and its six siblings — 9(b)#15 names what it would take to bring back); the
    read-only axis (`readonly_map`, `--readonly-env`) and the self-fire head;
    the `--overlong skip` and `drop-event` modes, leaving left-truncation only;
    the probing-cost and economics tables (a person can compute them from the
    report); the mbert line; the five non-AppWorld environments; `RUNMETA.json`
    (its content is `meta.json`'s `launches`); `pipeline/driver.py`'s
    `awaiting_decision` stop; `demo/prepare.py`; the presets and the collection
    manifests; and the chat-endpoint collection path — the baseline now runs the
    same streamed completion path as every other arm, so the same-setup rule
    holds by construction, and the chat endpoint survives only inside the
    render-equals-server check.
27. **Kept although each costs a mechanism**: the dirty-tree gate in
    `jobs/launch.py` with the three-path ledger exemption; the alignment gate
    before training; the clock guard inside `speculate`; the resume accounting
    (`match_len`, `identical`); `prefix_sha` on the `gen` row; the attach
    verification on both services. Each has an incident behind it in the old
    code, named where it appears above.

28. **Multi-host is kept, with the inventory in `constants/path_outputs.yaml`
    and ssh as the transport** (3.4, 6.3); alternative: declare the repo
    single-host — every loop, train and CPU piece on the machine `run.py` was
    typed on, the only remote thing a vLLM server attached to at its row's
    `serving.host`. Chosen because the cluster really is four machines
    (tokyo105-108, two of which answer `hostname` with `shiga` and `saitama`)
    and the old code already reaches all four; declaring one host would drop
    working capacity to make a document shorter. The price is one list in
    `constants/` and an ssh dependency inside `launch`, `ls` and `free`, all
    fail-closed.
29. **A new column on a format file is free only when no downstream stage reads
    it** (Part 1); alternative: the flat rule the drafts carried, "a new column
    never bumps `VERSION`". Chosen because the flat rule is silently wrong in
    the case that motivates most new columns — a consumer needs the field — and
    because there is no gate anywhere that catches it: the producing key does
    not move, the finished directory is reused, and the new reader gets the
    declared default for every row. The price is that adding a read column costs
    a recollection or a rebuild, which is the honest cost of needing the field.
30. **The claim primitive is `O_EXCL`, and the swap from today's `mkdir` ticket
    is measured, not assumed** (Part 1.1 and the facts section): the outputs
    mount is NFSv4.0 and a three-host, 24-process race gave exactly one winner
    per file, 150 times out of 150. The alternative was to keep
    `os.mkdir(<records>/<id>.claim)`, which the old docstring chose for NFS
    atomicity. Chosen because the file is then its own ticket and there is no
    second thing to clean up; if the outputs mount is ever replaced by one where
    the measurement fails, the `mkdir` primitive comes back and nothing else in
    this document changes.
31. **There are two cut rules, not one** (1.7): `cuts` offline at `m.end()` with
    a terminal cut and even thinning, `cuts_live` streaming at `m.start()` with
    neither; alternative: one function for both callers, which the first draft
    of this document pinned. Rejected because neither half of the offline rule
    is executable on a growing prefix — the thinning needs the total cut count
    and today's live code says in its own docstring that a thinned set
    "changes as the text grows"
    (`legacy/pipeline/inject/live_appworld.py:178-186`) — and because `m.end()`
    under chunking counts one sentence end twice. The price is that
    `example.cut` and `spec.cut` are not the same coordinate, which both files'
    lines now say.
32. **`settings.yaml` is a stage projection and the collision check is over
    `settings_diff.yaml`** (3.4); alternative: write the whole setting and
    refuse any difference. Rejected because `sample` and `inject` exclude the
    seed and task lists from their keys on purpose, so a legitimate wider
    request — the fourth seed of 9(a)#20 — would be refused as a key collision,
    and a shared directory's file would assert sections its other owners
    contradict.
33. **`env` and `extra_flags` are no longer a free bucket in `serving:`**
    (6.1): `serving.env` may hold only location and resource variables, every
    other variable is an `env_result:` column and `extra_flags` is a `result:`
    column. Alternative: keep the escape clause "anything that turns out to
    change results moves to `result:`". Rejected because this repo has already
    varied `VLLM_BATCH_INVARIANT` inside that bucket
    (`legacy/ops/jobs.json`), which would give two runs with different
    numerics one key and one directory. The price is that a genuinely
    cosmetic flag now costs a key change.
34. **`run.py` and `jobs/launch.py` refuse to run anywhere but `login_host`**
    (8.6); alternative: leave "the login machine" as a convention. Rejected
    because the lock file lives on NFSv3 home and four hosts can reach it, so
    the convention is the only thing between the design and two hosts passing
    the launch gate at once. The price is one key in `constants/` and a refusal
    a person can hit on the wrong terminal. **Confirmed by gyb, 2026-09-17:**
    the restriction stays, and `login_host` stays `shiga`, the one machine gyb
    launches from.
35. **`refire` and `retry` are `run.py` subcommands and `jobs/launch.py` has no
    `__main__`** (2.3, 2.4, 8.6); alternative: `jobs/launch.py --refire <dir>`,
    as earlier drafts wrote it, and a `--retry` flag on the piece command.
    Rejected because the tree calls `run.py` "the one command", and because a
    `--retry` on the piece command would be frozen into `meta.json`'s piece
    command and ride into every later refire.
36. **A finished directory is skipped only when what it consumed still matches
    what is on disk** (2.3); alternative: skip on `done.json` alone and leave
    `ls`'s `split` and `consumed` flags as notices. Rejected because the split
    task-id files enter no key (6.3 concedes it), so editing one and rerunning
    silently trains and evaluates over a dataset whose splits no longer match
    the files — a wrong number behind a flag on a command nobody is required to
    run. The price is one hash pass per skipped directory.
37. **The service pieces of a finished run are ended by the walk that writes its
    `done.json`** (2.3); alternative: leave them to `run.py kill`. Rejected
    because on the normal path nobody types `kill`: the loop pieces exit, the
    run is done, and the vLLM server holds its cards against the next stage of
    the same walk and against every sweep child.
38. **`--check` on the probe service is a client against the running service**
    (7.2), not a mode that loads the checkpoints itself; alternative: today's
    server-side `--check` flag. Rejected because 9(c)#7 runs it after the service is
    up, where a second loader puts a second copy of both probes on the one card
    the service already owns — an OOM at every launch on a 1.7B pair — while
    running it before the service starts proves nothing about the process that
    will serve.

39. **The refire quota is retired** (2.3, 8.6): `run.py refire` warns that a
    piece has been launched before and proceeds; alternative: CONTEXT's one
    automatic refire per piece, which earlier drafts kept. Rejected because the
    quota existed to stop an automatic refirer and #13 retired the only one, so
    the refusal would fall on the person it was meant to escalate to, and because
    its count was ambiguous (one launch entry covers many pieces). CONTEXT's
    refire-quota entry is obsolete with the eight #13 already names.
40. **An inject key folds its `probe_score`'s train key plus the `VERSION`s of
    the two modules that fit the temperature** — `eval/utils/probe_eval.py` and
    the referenced setting's `eval/methods/<m>.py` — **instead of that
    classifier eval run's key** (2.1, 2.2); the eval key stays in `_upstream`,
    which is what locates the report. Alternatives: fold the eval key, as earlier
    drafts did, which re-keys every inject setting whenever `eval.risk`,
    `eval.theta_grid`, `eval.bootstrap` or `eval.bootstrap_seed` is edited and
    forces a live recollection that cannot change a byte — the live run takes
    only the temperature from that report, and theta is `inject.theta`, a
    person's field; or fold the temperature *value*, which is exact but would
    make `key` read the output tree and break 3.2's purity guarantee, so an
    inject key would stop being computable before its eval run exists. The price
    of this one is that it is the only place in the document where a `VERSION`
    stands in for a key.
41. **`Environment.step` takes the model's reply text and owns both the action
    extraction and the completion signal** (4.2), returning a `StepObservation`;
    alternative: the loop extracts the code block and asks some other method
    whether the task is done. Chosen because the record needs both
    (`env.action`, `final.completed`), no other method produces either, and a
    benchmark whose action syntax or completion API differs would otherwise force
    an edit to `agent/loop.py`, which 0.4 and the `agent/` tree line forbid.
42. **`data/environments/__init__.py`'s `VERSION` is keyed** into `sample`,
    `build` and `inject` (2.2, 4.1); alternative: declare it a reader's note that
    enters no key. Chosen because that file is no longer a pure declaration: it
    holds `requested_pairs`, whose ordering decides which trajectories are
    collected and which records are built (2.3).
43. **`meta.generation` and `meta.inject` are canonical JSON text, not structs**
    (1.1); alternative: struct columns, as earlier drafts typed them. Rejected
    because Part 1's reading convention passes a declared schema, so a struct
    column would have to enumerate its inner fields in `data/trajectory_record.py`, and
    every new `generation.*` or `inject.*` field would then cost an edit there
    plus a `VERSION` bump and a recollection — which contradicts 3.3 and 0.4,
    where adding a hyperparameter is free. The price is that nothing may parse
    those two columns against a field list; the authoritative copy is
    `settings.yaml`.
44. **`sample.split` and `inject.split` are lists of splits, and the benchmark's
    split names reach the example row through `Environment.SPLIT_ROLE`** (5.2,
    4.1, 2.5); alternative: one split per run, as earlier drafts wrote it.
    Rejected because `build` assigns every example row's split from the records
    it read, so a single-split `sample` run produces a dataset with an empty
    `val` and an empty `test`, `train.predict.splits` writes no prediction rows,
    and the eval fits a temperature on nothing — the first walk of
    `train_probe.yaml` under the defaults. The legacy pipeline collected across
    three lists and mapped them (`legacy/pipeline/configs/p1_gptoss.json:10-14`,
    `legacy/pipeline/annotate/build.py:309-318`); this is that, with the mapping
    named and owned by the environment instead of by a config file. The price is
    one more class attribute per environment and a `sample.split` default that
    collects three lists.
45. **A format file declares `REQUIRED` beside `VERSION` and `DEFAULTS`**
    (Part 1); alternative: leave "a reader never relies on `DEFAULTS` for a
    column it requires" as a rule each reader keeps by hand. Rejected because
    the shared reader fills from `DEFAULTS` before it returns, so the absence a
    reader would have to notice is gone by the time it could look, and neither
    `read(path)` nor `read_dir(dir, pairs)` carries a channel for the
    requirement. The price is one literal per format file and one more
    `selfcheck` rule.
46. **The expanded model row lives in two named fields, `models.agent_row` and
    `models.probe_row`, while `models.agent` and `models.probe` stay alias
    strings** (5.2, 6.1); alternatives: turn the alias fields themselves into
    structs, which breaks every `models.agent(cfg.models.agent)` call and
    `--model <alias>` on the command line, or leave the expansion unnamed, which
    it was — four readers (`schema.key`, `agent/loop.py`, `agent/inject.py`, the
    probe service's `check` client) would each have guessed a different name and
    7.2's health refusal would have died on an `AttributeError`.
47. **`sample.n_tasks` and `inject.n_tasks` cap the tasks of *each* split, not
    the concatenation** (2.3, 5.2, 5.6); alternative: cap the concatenation, as
    Round 4 left it, and give `debug.yaml` a per-split block instead. Chosen
    because with a cap on the concatenation `debug.yaml`'s `n_tasks: 3` takes
    three tasks off the head of the `train` file alone, so a `--debug` walk of
    `train_probe.yaml` builds an empty `val` and an empty `test`, writes no
    prediction rows and fits a temperature on nothing — the flagship workflow's
    debug walk dies at its last stage, against principle 4. Per split,
    `debug.yaml` stays sizes-only and every `--debug` walk exercises the real code
    path end to end. The price is that `n_tasks: 10` over three splits asks for 30
    tasks, not 10, which the field's own comment now says. This is the
    consequence Round 4 flagged and left to the owner; it is applied here and is
    the one line in this list the owner is most likely to want to look at.
48. **`final.judge` is canonical JSON text with a declared boolean
    `final.success` beside it** (1.1); alternative: the struct column earlier
    drafts typed it as. Rejected for the reason 9(a)#43 gives for
    `meta.generation`: Part 1's reading convention passes a declared schema, so a
    struct would have to enumerate the benchmark's own evaluation fields in
    `data/trajectory_record.py`, and a second benchmark — or an AppWorld upgrade that
    adds a field — would cost an edit there plus a `VERSION` bump and a full
    recollection, while 0.4's new-environment row lists neither. `success` is a
    column because it is the one field `eval/score_run.py` reads, and a declared
    column keeps every reader off the JSON. The price is that a person reading a
    per-benchmark evaluation field reads text.

## 9(b). Reviewer fixes that would need a structural change — not applied

Each line: the fix, the file it would add, split or move, what it would buy.

1. **Split `experimental_settings/schema.py`** into `schema.py` (fields, axes,
   stage table), `loader.py` (merge, debug, overrides, sweep, references) and
   `key.py` (the hash). Buys: the file everyone edits stops being the file
   everyone imports. (synthesis 1, dependencies P1, structure 4)
2. **Split `jobs/registry.py`** into `ledger.py` (append, meta, heartbeat;
   imported by every stage) and `status.py` (ls, where, find, kill, render;
   imported by `run.py` only). Buys: a change to an `ls` column stops touching
   the file ten stages import. (synthesis 2, structure 5)
3. **Bring back `train/packing.py` and `train/reference.py`.** Buys: cgen and
   cparam stop being two 600-line near-copies of
   `legacy/pipeline/train/share_data.py`, and the alignment gate gets one
   reference instead of one per method. (synthesis 3, structure 1 and 2)
4. **Split `train/utils/trainer.py`** into `trainer.py`, `tuning.py` and
   `predict.py`. Buys: the prediction step becomes its own program with its own
   resume point, and the LoRA merge stops living inside the loop. (synthesis 4)
5. **`data/probe_report.py`** as the probe report's home, instead of defining it
   in `eval/utils/probe_eval.py`. Buys: "every format between two stages is
   defined in `data/`" holds without an exception, and `run.py` reads the report
   from `data/` rather than from `eval/`. (synthesis 5, dependencies P3)
6. **Split each `service.py` into `server.py` and `client.py`.** Buys: the venv
   boundary becomes a file boundary that `selfcheck` can import-test, instead of
   a convention that one stray top-level `import torch` breaks at night.
   (synthesis 6, structure 9)
7. **Move the model table to `experimental_settings/models.yaml` and the
   serving location to `constants/models.yaml`.** Buys: `models/` holds only
   code, and "everything in `experimental_settings/` changes a result" becomes
   true without the two-block convention of Part 6.1. (synthesis 7, structure 7)
8. **`environments/` as a top-level layer.** Buys: the folder sits beside its
   five callers instead of inside `data/`, whose own line already says a new
   environment goes elsewhere. (synthesis 11, structure 8)
9. **`data/methods/<m>.py`** for the per-method target construction and the
   match function both train validation and eval need. Buys: the `train -> eval`
   import disappears, `eval/methods/<m>.py`'s VERSION leaves the train key (and
   with it the cost in 9(a)#23), and a fourth method touches three files instead
   of two plus an axis. (synthesis 12, dependencies P2)
10. **Flatten `train/` and `eval/` and name the eval files by the metric**
    (`fire_threshold.py`, `exact_match.py`). Buys: the
    `train/methods/ctool.py` / `eval/methods/ctool.py` basename collision goes
    away in any file switcher, and the cgen/cparam eval copy collapses into one
    file. (synthesis 12, structure 12)
11. **`data/check_dataset.py`** for the build gates. Buys: the gates, edited when
    a new silent failure is found, stop sharing a file with example
    construction, edited for a new method or cut rule. (structure 11)
12. **`jobs/walk.py`** for the stage walk, leaving `run.py` a CLI. Buys: the walk
    stops growing inside the command that parses arguments; today's
    `legacy/pipeline/driver.py` is 1,615 lines of exactly that. (structure 4)
13. **`jobs/watch.py`**, if the sampler is kept rather than retired. Buys: the
    verdict engine and the web page keep a home and the CONTEXT entries stay
    true. (structure 6, lifecycle B7)
14. **Rename `Environment.split_args` to `parse_call`.** Buys: the method's name
    would say what Part 4.2 has to explain in a sentence.
15. **A seventh stage, `replay`, with its own file.** Buys: the offline
    injection line (`legacy/pipeline/inject/replay_inject.py`, 1,521 lines) has
    somewhere to come back to; it is injection over recorded records and fits
    none of the six stages. Retired in this document. (structure 13)
16. **Render `RESULTS.md` into `notes/`** with the other three ledgers instead of
    into `jobs/`. Buys: the four-ledger rule in CLAUDE.md stays literally true.
    (structure 13)
17. **`tests/` files**, deferred by the owner: the four checks the tree names.
    Until they exist, four rules in this document are kept by hand — the default
    rule (3.3), the alignment gate (2.6), the speculate guarantee (4.3), and the
    single-writer heartbeat and lock rule (8.6).
18. **`constants/cluster.yaml`** for the three cluster-wide facts these rounds
    of fixes had to place: the `hosts:` list (name, alias, cards), `login_host:`
    (the one machine `run.py` and `jobs/launch.py` may run on, 8.6) and the
    `venvs:` map (which interpreter each venv name means). All three are now
    lodged in files named after something else — `hosts:` and `login_host:` in
    `path_outputs.yaml`
    because it is the only cluster-wide file of the three, `venvs:` in
    `path_datasets.yaml` because the per-environment `venv:` column is a key of
    it — and neither file's tree line mentions them. Buys: `constants/` would
    say what each of its files is for without a sentence of explanation, and the
    three inventories that every launch reads would stop riding on the datasets
    and outputs files. It needs a new file, so it is not applied.
19. **`agent/probe_input.py` beside `agent/inject.py`**, or the reverse: one
    file that both the builder and the live injector import from the layer they
    share. Today's tie is an import
    (`legacy/pipeline/inject/live_appworld.py:77` imports the builder's rules
    module), and the tree puts the file under `data/` while one of its two
    callers is in `agent/`. Part 1.7 pins the interface instead, which is what
    the fixed tree allows. Buys: nothing in behaviour; it would make the shared
    rule's placement match its two callers.

## 9(c). The nine lifecycle scenarios, walked

These are the acceptance cases for the contracts: each one must pass through
the tables above without a gap. They are the construction plan's smoke list.

**1. First run of `train_probe.yaml:ctool_q06`.** `run.py train_probe ctool_q06`
loads the setting (5.7), expands the model rows, and walks
`workflow: [sample, build, train, eval]`. For `sample`, `run_dir` gives a path
with no `done.json`, so `run.py` takes `runs.jsonl.lock`, calls
`jobs/launch.git_state` for the dirty gate and the commit, freezes
`settings.yaml` (with that commit under `_commit`) through a temporary name and a
rename (3.4), and
`jobs/launch.py` probes cards, assigns ports and appends the
start row — all inside that one hold (3.4, 8.1, 8.6) — then, with the lock
released, starts the two service pieces in tmux (one vLLM, one render-only probe
piece), waits for their alive check, and only then starts the six loop pieces
(8.1's two waves). The walk stops there and prints the monitoring
command; an asynchronous GPU stage is never waited on. Each loop piece claims
(task, seed) files by exclusive create and writes records. On a later `run.py`
call, the walk finds every requested pair finished, writes `done.json` and the
finish row, ends the two service pieces (2.3), and moves to `build`: one CPU
process `run.py` starts in place under the `probe` interpreter (6.3), which
refuses if any
record is missing or if too many aborted, writes `examples.parquet`,
`consumed.json`, `report.md` and its own `done.json`. `train` launches one piece
on one card; the trainer reads the example parquet, runs the alignment gate,
trains, writes `train_done.json`, then predicts over val and test and writes
`predictions.parquet` and `done.json`. `eval` runs in place on the CPU, fits the
temperature and theta on val, freezes on test, and writes `probe_report.json`
and `fires.parquet`. Four directories, four keys, eight registry rows.

**2. Rerun unchanged.** The same command recomputes the same four keys (3.2
rule 1). For `sample` the skip test is the pair check (2.3): the requested
(task, seed) list is a subset of `done.json`'s `pairs`, so it is skipped —
asking for one more seed instead would relaunch for that seed alone. `build` and
`train` are skipped on their `done.json`, after the walk confirms that their
`consumed.json` entries — and the `sample` directory's `split_files` hashes —
still match the files on disk (2.3). `eval` reruns, because it always
recomputes, overwrites its report with the same numbers and today's commit, and
`run.py` appends a second finish row, because `done.json`'s `finished_at` is
newer than the last one (8.2). Nothing starts on a card. Cost: seconds.

**3. Partial train.** The piece died at step 40. `ls` shows `dead` (session
gone, heartbeat stale). The rerun finds no `done.json` and no `train_done.json`
but a `last/` whose commit equals this launch's `cfg._commit`, so the trainer resumes from step 40 into
the same directory. Had it died during prediction, `train_done.json` would be
present and only the prediction step would run. Had the commit moved, the
trainer refuses and says so; `run.py retry train_probe ctool_q06 train` clears
the directory and starts fresh (2.4).

**4. Dead piece.** One of six sample loop pieces died with two tasks claimed and
unfinished. `ls` shows five healthy and one `dead`.
`run.py refire train_probe ctool_q06 sample --piece 3` calls
`jobs/launch.refire`, which first probes that piece's session on its recorded
host and, finding it gone, reads the piece's frozen command from
`meta.json`, deletes the unfinished record files whose `meta` row names the dead
session (and any file with no `meta` row whose mtime is older than
`registry.DEFAULTS["launch_timeout_s"]`, 1.1), probes the card,
restarts the piece in a new tmux session, appends a launch entry and opens
`heartbeat/3-1.jsonl` — the next free `<launch>` under that piece's prefix, which
the piece resolves by listing its own `heartbeat/` directory (8.4). The five live
pieces are untouched and the service pieces are reused. A second death of the
same piece is refired the same way; `run.py refire` warns that this piece has
been launched before and names the earlier entries, and proceeds (2.3).

**5. Edit one value.** `train.lr` changes from 1e-5 to 3e-5. The sample and
build keys are unchanged, because neither stage reads `train` (3.2 rule 3), so
both directories are reused with no GPU work. The train key changes and, through
it, the eval key; two new directories appear, the old ones keep their own
`settings.yaml`, and `ls` shows both. Editing `eval.risk` instead changes only
the eval key and costs no GPU at all inside `train_probe.yaml`, because the
prediction rows cover every example and `train.predict` is its own sub-section —
and it costs none in `inject.yaml` either, because an inject key folds its
`probe_score`'s **train** key and the two modules that fit the temperature, not
the classifier eval key (2.1, 2.2). Folding that eval key would have made an
`eval.risk` edit re-key every inject setting referencing it, which is a full live
recollection that cannot change a byte. Editing the cut rule in
`data/probe_input.py` and bumping its VERSION changes the build key and, through
it, the train and eval keys, and the inject key through `probe_input`'s own
version; `sample` is untouched and its records are reused — so the edit costs a
full retraining, which is what that file's tree line says it costs.

**6. Sweep.** `sweep: {train.lr: [1e-4, 3e-4, 5e-4], train.seed: [42, 67]}`
expands at load into six children (5.5). All six share one sample key and one
build key. `run.py` walks the children in order; the first launches `sample`,
and the other five find an open start row for that key — young, or with a live
session, or beating — so the launch gate refuses on whichever clause holds (2.5)
and the walk says which key it is waiting on. When the shared stages are done, the six train runs launch on six
cards in one pass, and they do not collide: a card is busy once it appears in a
live registry row's piece entry, not only once `nvidia-smi` sees a process on it
(2.5), the reservation is read inside the same lock hold as the gate, and a
card is held from the moment the start row is appended — inside that hold, with
`status: "launching"` — rather than from the moment its tmux session comes up
(8.1). `run.py where train_probe 'ctool_q17_lr/train.lr=0.0003,train.seed=67' train`
addresses one child, the value formatted as 5.5 pins it;
`eval/method_table.py` groups them by `parent` and reports mean and spread.

**7. Inject referencing a probe.** `inject.yaml:ctool_q06_p1e1` names
`probe_score: train_probe/ctool_q06`, `probe_gen: train_probe/cgen_q06`,
`theta: 0.9`, `format: p1_e1`, `arm: probe`, and
`score.baseline: baseline/gptoss120b_appworld`. It names no `probe:` section and
no `models.probe`, which the loader would refuse (5.7). The loader resolves the
three references and checks the agreement **per inherited group** (5.4):
`data`, `models.agent` and `generation` across all three, and the `build` fields
in `PROBE_TEXT_FIELDS` (1.7) across the two whose workflow
provides a `build` stage — `probe_score` and `probe_gen` — since the baseline's
workflow is `[sample, score]` and may state no `build:` section at all. It
inherits the agreed values (a stated difference is a load error unless
`meta.override` names the field, and a disagreement inside a group is a
load error on its own, 5.4). Its `_upstream` carries four resolved keys —
`probe_score.train`, `probe_score.eval`, `probe_gen.train` on the inject side and
`baseline.sample` on the score side (1.5) — and the inject key folds the two train
keys, with `eval/utils/probe_eval.py` and `eval/methods/ctool.py` standing in for
the eval key (2.1, 2.2); the score key folds the baseline. The two probes' train
runs must share a build key (2.5), which is also what makes the inherited
`build` fields unambiguous. `run.py` refuses if any referenced run lacks
`done.json`, holds the two inject gates of 2.5, reads the ctool report and
freezes `_resolved.probe_temperature`.
`jobs/launch.py` starts the vLLM pieces and one probe service piece loading both
checkpoints with that temperature; once that piece's port answers it runs the
client-side gate
`python -m models.probe_models.service check --base-url <url> --run-dir <dir>`
against the running service (7.2), and only then the loop pieces. A non-zero
exit there is a `launch_failed` finish row and no loop piece starts.
`agent/inject.py` refuses to start unless `/health` echoes the two train keys it
expects, `models.agent_row["family"]`, and the capabilities its format
needs. The baseline's split and seeds were already checked
against this setting's at load (5.7), so a baseline collected over the wrong
split fails before a card is taken. Afterwards, `score` pairs the inject records
with the baseline records task by task and seed by seed, and refuses the pair if
the generation sections differ or if the baseline lacks a done record for any
(task, seed) the inject run holds (2.5).

**8. Debug.** `--debug` lays `debug.yaml` over the setting before keying, and
`debug: true` enters the key, so `run_dir` lands under
`<root>/debug/<stage>/<key>`. The tmux session name carries that key, so it
cannot collide with a real run's. The rows carry `debug: true` and `ls` hides
them unless asked. A non-debug walk never considers a debug directory for reuse,
because the keys differ. The debug run uses the same model, the same tuning and
the same code path; only the sizes shrink. `debug.yaml`'s `n_tasks: 3` is three
tasks **per split** (2.3, 5.6) and its `max_examples: 64` is 64 rows **per
split** (5.2, 2.5), so the walk collects 3 train, 3 dev and 3 test
tasks, `build` produces all three splits with rows in each, `train.predict` writes rows for `val`
and `test`, and the eval has a val frame to fit on — the debug walk reaches the
last stage of `train_probe.yaml` instead of dying there.

**9. Two sessions at once.** Two sessions run the same setting from the login
machine — the only machine either may run on, because both programs refuse
anywhere but `login_host` (8.6), which is what makes the `fcntl` lock
local-filesystem semantics. Both compute the same key. The first takes
`runs.jsonl.lock` and
holds it across reading the registry, the launch gate, the attach test, the card
reservation, the port assignment and the append of its start row (8.6), then
starts its tmux sessions. The second blocks on the lock, and when it gets it the start row is
already on disk, so its launch gate finds that row open and refuses: the gate is
a disjunction (2.5), and even before any session exists the row is `launching`
and younger than `registry.DEFAULTS["launch_timeout_s"]`, which is one of the
three clauses on its own. It prints the session name once there is one and the
run_id and the row's age while there is not. That is why
the lock covers the gate and not only the append: a lock scoped to the append
alone would let both pass the gate in the same second. Had the first died, the
second finds `dead` and is told to use `run.py retry` or `run.py refire`, so a
failure cannot loop. Because the file is append-only their git commits merge. A stage
process on a compute node takes no lock at all, and remote pieces are started
over ssh from the login machine (3.4), so two hosts cannot deadlock on NFS.

## 9(d). What this document does not decide

- **The hash function's implementation** and the exact canonical JSON form —
  float formatting is the one place a key could drift between Python versions.
  The owner's instruction is that keying is implemented last; only the
  signature, the inputs and the guarantees are fixed here (Part 3). The
  *name* a person types is not left open: a sweep child formats a value with
  `repr()` of the parsed YAML value (5.5, 3.4), so a typed child name always
  reaches its directory.
- **The cost of predicting at every cut row** for cgen and cparam. The
  construction plan measures it in the smoke; the fallback is written down
  (9(a)#2) and not built.
- **The exact instruction-variant texts.** `v1` is today's AppWorld developer
  message (`legacy/envs/collect/run_appworld.py:24-43`); further variants are
  the owner's to write.
- **Whether `p2_*` formats survive** the encode contract in 7.2: the `check`
  client of 7.2 proves both directions of `encode` on a fixture string containing
  a literal `<|end|>` — `special=false` must leave it as plain text,
  `special=true` must turn it into its control token — and exits non-zero
  otherwise, which `jobs/launch.py` turns into the `service_check` outcome of 8.1
  and `run.py` into a `launch_failed` finish row. Which way the check comes out on
  a new backbone is a fact to be measured, not a decision.
