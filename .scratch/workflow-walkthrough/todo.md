# Workflow walkthrough: todo list

gyb walks through the from-zero workflow step by step (session of 2026-09-21) and
states what should change. Every change he asks for is recorded here and executed
later in one batch; nothing on the open list is edited before he says so.

Each entry: what gyb asked for, at which step of the walkthrough, and what the
change touches as far as it is known.

## Open

(none yet)

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
