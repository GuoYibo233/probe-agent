# 13 — vLLM service record

**What to build:** Service-type pieces (vLLM) display correctly in the
window: alive/dead is judged only by port response (the /health path,
per real testing), the throughput line is only parsed for token rate to
put into the display slot and never enters the verdict, and not printing
a throughput line while idle does not count as a stall. The fixture for
parsing the throughput line uses the real log text verified on
2026-08-08. When registering a service piece, the log field must be
filled with the real path (vLLM's logs are not under the job directory).
Steps follow Task 15 of the implementation plan.

**Blocked by:** 02 Sampler runs one round end to end

**Status:** resolved

- [x] Throughput-line parsing tests pass: real sample lines yield
  generation rate, prompt rate, and concurrency count; no match returns
  None
- [x] A service piece does not go through heartbeat parsing; the verdict
  is decided only by the port probe
- [x] commit

## Comments

- 2026-08-08 transcribed by the main conversation (from T09's wrap-up):
  T09 implemented --service as a boolean flag that sets kind="service",
  with --port dropping into the pass-through arguments, but the
  rich-piece field table has no port field: the whole plan never defines
  the path for port to travel from launch to the sampler's
  probe_port(host, port). When T13 implements this, it must either land
  port in a piece/ledger field the sampler can read, or state clearly in
  its report where port comes from; this is an item the main
  conversation must check when T13 wraps up.
- 2026-08-09 ticket-run interim account: DONE on branch
  ticket/20260808-par/T13 (base 2ce9834, head 3540212), 0 fix rounds, one
  minor (sampler.py's continuation-line indent is off by one space).
  **Merge held back**: the branch changes ops/sampler.py, the same file
  as T12's changes waiting in the worktree for the user to commit
  together; the merge, test run, and marking resolved wait until that
  lands. A real gap confirmed by review (transcribed to ticket 18 and
  the final report): the port field has no automatic write path from
  launch, launch's --port only passes through and never enters the rich
  piece, register doesn't support --port/--kind, so making a real vLLM
  service record take effect requires manually calling register_all() or
  hand-editing jobs.json; whether to open another ticket to fill this in
  is for the user to decide. The assumption that /health returns 200 is
  consistent with T02 and has not been tested against a real service.
  Report: sdd/2026-08-08-wave1/T13-report.md.
- 2026-08-09 main-conversation wrap-up: after T12's commit (088bac9)
  landed, the branch was merged (merge commit bd2d991). Two conflicts:
  sampler.py's import (both sides kept), and MAP.md's sampler line (HEAD
  as the base with T13's service-piece sentence folded in). 117 tests
  all green after merging. The port-passing gap is still noted in ticket
  18, with the user to decide whether to open another ticket. Marked
  resolved.
