# 02 — Sampler runs one round end to end, three files land on disk

**What to build:** The sampler can walk one sampling round start to finish:
read the ledger's list of active jobs, tail each piece's log to pick up
heartbeats, probe tmux liveness (fail-closed on probe failure), call the
verdict engine to compute the verdict, and write three files to disk, the
latest result, the accumulated state, and the per-round history (in the NFS
monitor directory, with an environment variable able to point the directory
elsewhere). Two more accounting rules are also nailed down at this step: the
timeline restarting after a refire, and the same heartbeat not being counted
twice. `run.py sampler` is wired into the registry, with a smoke mode that
samples one round and exits. Steps follow Task 6 of the implementation plan.

**Blocked by:** 01 Heartbeat module and verdict engine

**Status:** resolved

- [ ] Sampler tests pass: a fake ledger with two pieces (one alive, one
  dead); the alive one's verdict is healthy or warming up, the dead one's
  verdict is dead, cumulative token counts read correctly
- [ ] All three on-disk files appear and are json.load-able; sampling
  another round does not re-append heartbeats from an unchanged log
- [ ] `python3 run.py sampler --once` runs to completion on the real ledger
  without crashing
- [ ] `python3 run.py selfcheck` passes and commit

## Comments

- 2026-08-08 ticket-run: DONE. Branch ticket/20260808-par/T02 (base
  5be5d08, head d7f3435, added ops/sampler.py + tests/test_sampler.py,
  wired sampler into run.py, added a MAP.md line), merge commit 93d5bdd (a
  line-add conflict between MAP.md and T08 resolved by taking the union,
  the two lines were unrelated to each other). 0 fix rounds, no minors.
  Two cannotVerify items handled by the main conversation: selfcheck was
  hand-tested in the full post-merge environment with all 63 tasks in
  place (the rc=1 seen in the worktree is a structural issue from a
  missing venv, and this evidentiary explanation holds); the kind="service"
  end-to-end chain belongs to ticket 13's scope, to be checked when T13 is
  wrapped up. For acceptance item three, the main conversation hand-tested
  `sampler --once` on the real ledger with exit 0, the NFS monitor
  directory producing latest.json/state.json, and rows=0 consistent with
  the ledger currently having no active jobs. Six concerns read, all
  implementation-tradeoff notes (load_reg being its own module, build_row
  collecting the whole job dict, state.json having three extra keys,
  incident fields left for ticket 12, service integration tests left for
  ticket 13, the selfcheck worktree limitation), no action needed. Report:
  sdd/2026-08-08-wave1/T02-report.md.
