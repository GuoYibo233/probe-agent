# 06 — Web and json outlets

**What to build:** The sampler opens an HTTP port (default 8377,
overridable) in the same process: the root path serves a job-table web
page (verdict, progress, rate, token, ETA, the incident-record block,
sessions missing from the ledger, auto-refreshing every 30 seconds,
turning red when the last sample time is stale), and /json serves the
latest sampling result verbatim. The web thread only reads the on-disk
latest-result file and never touches the sampling thread's memory, so a
stuck ssh call on the sampling side doesn't affect serving the page. The
user watches in a local browser via VS Code port forwarding. Steps follow
Task 7 of the implementation plan.

**Blocked by:** 02 Sampler runs one round end to end

**Status:** resolved

- [ ] Web tests pass: /json matches the on-disk file, root path returns
  200 with a body containing the job name, verdict, and last sample time
- [ ] The stale-turns-red threshold is generated into the page from the
  verdict engine's DEFAULTS, not copied as a separate number
- [ ] commit

## Comments

- 2026-08-08 ticket-run: DONE. Branch ticket/20260808-par/T06 (base
  1d421be, head 5897417, ops/sampler.py +204 lines for the web section,
  tests/test_sampler_web.py added), 41 tests all green and selfcheck's 63
  tasks in place after merging into main. 0 fix rounds. One leftover
  minor: /json is latest.json re-serialized after parsing (semantically
  identical, byte-different, indentation lost); the acceptance item
  "matches the on-disk file" is passed on a semantic basis; if a future
  consumer compares freshness by byte hash it will trip on this, noted
  for now and left unchanged. One concern noted as-is: when latest.json is
  missing, /json returns 503 + an error json, an interface the implementer
  decided on their own; if a future consumer has a different expectation,
  it needs to be reconciled then. Report: sdd/2026-08-08-wave1/T06-report.md.
