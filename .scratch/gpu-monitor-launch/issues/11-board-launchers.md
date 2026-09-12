# 11 — Two queue-based launchers wire up registration

**What to build:** launch-probe and launch-eval switch internally to
calling the common piece: the local tmux helper functions are deleted and
replaced with an import (the consolidate step of expand-then-consolidate),
each slot gets a FREE probe before launch (a non-FREE slot prints the
reason and is skipped, not a whole-table rejection, since a queue table
being half-empty is common), and each slot auto-registers the ledger and
record after launch (RUNMETA is still written by itself as before). Each
keeps its own guards untouched: launch-probe's queue table and smoke
mode, and launch-eval's hard dependency-order check and check for the
training product's existence. After this change, "the program guarantees
registration" holds across every launch path. Steps follow Task 13 of the
implementation plan.

**Blocked by:** 08 Common launch pieces

**Status:** resolved

- [ ] Both launchers still print normally under dry-run
- [ ] Full unit test suite green (the common piece's tests cover the
  registration path)
- [ ] commit

## Comments

- 2026-08-09 ticket-run: DONE. Branch ticket/20260808-par/T11 (base
  0914ef5, head b49705b, launch_probe/launch_eval wired to launch_common
  + two new test files), merge commit f8c9965 (a three-way MAP.md
  conflict resolved by hand: the sampler line takes the new convention,
  the two launcher lines take T11's). 1 fix round. Main-conversation
  review: all 22 tests across launch_probe/launch_eval/launch_common
  green; hand-testing dry-run was skipped (the worktree, carrying T12's
  uncommitted changes, could not pass the dirty-tree gate; both the
  implementer and the reviewer had already run it on a clean worktree and
  pasted the output). Fix-round decisions: eval's registration keeps the
  eval_ prefix on run_id to avoid colliding with a training job; a
  registration failure only WARNs and does not abort (tmux has already
  really launched). Three concerns noted as-is: the workdir semantics
  (the launcher passing the repo root vs. the ledger's history filling in
  the product directory) are inconsistent, a pre-existing issue that
  needs a cross-ticket ruling to unify; the queue-based launchers don't
  support overriding the verdict line (within scope); launch_probe's
  tests do exact string matching on the inner command (a template change
  would ripple through). This workflow died silently in a fix round
  yesterday; resumed this morning with the implementation replayed from
  cache and review run to completion. Report:
  sdd/2026-08-08-wave1/T11-report.md.
