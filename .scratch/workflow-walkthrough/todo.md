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
   named `<setting>` plus `<key>`.
   Open points, to settle with gyb before the batch:
   - where the stage goes (one setting has up to four stages, each with its own
     key): a level of its own, or part of the directory name;
   - which model names the level: the agent model (every workflow has one), or
     the probe backbone for train and eval;
   - one directory is shared by every setting whose key is equal (today the
     baseline setting and the three train_probe settings share one sample
     directory, and the three train_probe settings share one build directory),
     so a directory name can carry only one of their names: name it after the
     first setting that created it and find it by its key suffix, or keep
     `<stage>/<key>` as the real directory and add a per-setting tree of
     symlinks in gyb's layout.
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
