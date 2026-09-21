# Workflow walkthrough: todo list

gyb walks through the from-zero workflow step by step (session of 2026-09-21) and
states what should change. Every change he asks for is recorded here and executed
later in one batch; nothing on the open list is edited before he says so.

Each entry: what gyb asked for, at which step of the walkthrough, and what the
change touches as far as it is known.

## Open

5. Make the outputs tree readable by a person (step 4, key and run directory).
   Today a run lives at `<root>/<stage>/<key>`, and the 12-hex key says nothing
   about what the run is. gyb's layout: the top level is the benchmark
   (`appworld`), the next level is the model, and the run directory under it is
   named by its setting values plus `<key>`. gyb's clarification: "setting" here
   means the values that tell runs apart, such as `ctool`, and never the named
   setting's own name. The name is therefore a function of the run's content, so
   settings with an equal key get an equal name and sharing one directory stays
   as it is.
   Proposed shape: each stage's row in the stage table gains a short list of the
   fields whose values are spelled into the name, always, whether or not they
   differ from the default (the diff alone would drop `ctool`, which is the
   default method): nothing for `sample`, `build` and `score`; method, probe
   backbone and tuning for `train` and `eval`; arm, format and theta for
   `inject`. Example: `appworld/gpt_oss_120b/train/ctool-qwen3_0pt6b-full-<key>`.
   The name is for reading only; the key alone still identifies the run.
   Open points, to settle with gyb before the batch:
   - where the stage goes: a level of its own (as in the example), or a prefix
     of the directory name;
   - which model names the level: the agent model (every workflow has one, and
     the probe backbone is then part of the name), or the probe backbone for
     train and eval;
   - which fields each stage spells into its name.
   Touches: `schema.run_dir_of` and `referenced_run_dir` (every path goes through
   them), `registry.ls` / `sync` (they walk the root), the existing run
   directories on NFS (a migration or a cut-over), README section 1.

## Done

1. Remove the login-host refusal at the start of `run.py` (step 1, reading the
   arguments). Done in dc57f54: `run.py` and `jobs/launch.py` run on any host,
   start rows and cpu piece entries record the machine the command ran on.
2. Let the person name the cards a launch runs on (step 3, placement). Done in
   dc57f54: `--cards <host>:<ids>` on the walk, `refire` and `retry`; never part
   of the setting, so no key moves.
3. The GPU agent reads the live free-card list and allocates cards by the size of
   the job (step 3). Done in dc57f54: sizing tables in the gpu-run skill's
   Phase 1, the gpu-runner agent passes `--cards` on every launch.
4. Follow-up of 1: a cpu piece's pid was tested on the machine the command was
   typed on. Done in dc57f54: `registry.pid_alive` / `end_pid` go to the host the
   piece entry names; the launch gate's alive test uses them.

Not yet exercised: a real GPU launch with `--cards`; the next smoke run covers it.
