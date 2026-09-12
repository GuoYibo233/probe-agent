# 16 — Doc write-back: two agent definitions

**What to build:** job-monitor is trimmed down: the operational details
of two-point rate measurement, hand-computed ETA, and tqdm parsing are
all deleted, replaced with reading gpu-jobs json's ready-made verdict
plus autopsy on demand; the read-only hard rule, the autopsy flow, and
the report format are kept; a section on the division of labor with the
incident agent is added (job-monitor is a human-dispatched reviewer, the
incident agent is the sampler's middle-of-the-night responder, don't
refire on its behalf). gpu-runner's launch section becomes launch across
the board, the double-registration section is deleted, and the
registration receipt becomes pasting launch's output. Steps follow Task
17 of the implementation plan.

**Blocked by:** 07 Terminal outlet switches to reading the sampling
history, 09 launch subcommand, 12 Incident trigger

**Status:** resolved

- [ ] job-monitor's definition no longer has the two-point rate
  measurement operational step
- [ ] gpu-runner's definition has only one path for launching, launch
  (the queue-based launchers unchanged)
- [ ] commit

## Comments

- 2026-08-08 transcribed by the main conversation (current-state
  phrasing that must be read before writing docs): the incident agent's
  automatic spawning in ticket 12 was deferred by user ruling on
  2026-08-08. Write the job-monitor/incident-agent division-of-labor
  section per the ticket, but note that the incident agent's automatic
  spawning is currently not live (deferred), and unattended automatic
  handling in the middle of the night does not exist yet; the half about
  job-monitor reading json's ready-made verdict is written as usual.
- 2026-08-08 phrasing update (overrides the previous entry): the user
  subsequently authorized it, and the incident agent's automatic
  spawning has been wired in by the main conversation (including the
  refire-permission rule), but the manual rehearsal was cancelled; write
  the division-of-labor section per the ticket's original text, noting
  "wired in, not yet rehearsed for real," not "not live yet."
- 2026-08-09 ticket-run: DONE. Branch ticket/20260808-par/T16 (base
  0d2c1ac, head 9ba56ae, two agent definitions +81/-69), merged. 0 fix
  rounds. Acceptance met: zero residue of "two-point rate measurement" in
  job-monitor's definition (grep returns 0), gpu-runner launches
  exclusively via launch (with the queue-based launchers kept as the
  usual exception). Two leftover minors: gpu-runner has an extra
  "exception two, --refire refire" section written in (the ticket didn't
  call for it; review confirmed it matches launch_cmd.py's
  implementation exactly, harmless and kept); both definitions'
  frontmatter description still carries the old wording "measured
  rate/real ETA," while the body has already changed to "rate/ETA," can
  be aligned in passing at final wrap-up. Three concerns noted as-is
  (dropping "measured" from the table header is an extrapolated
  judgment call; leaving frontmatter untouched is a scope judgment call;
  the mismatch between the "wired in, not rehearsed" phrasing and the
  sampler placeholder state on the branch's baseline is a known
  commit-timing issue that disappears once the user's unified commit
  lands). Report: sdd/2026-08-08-wave1/T16-report.md.
