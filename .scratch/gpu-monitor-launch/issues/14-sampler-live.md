# 14 — Sampler goes live

**What to build:** The sampler stays resident in a tmux session on the
login machine (session name new1_sampler, log tee'd to the monitor
directory), with crontab checking the session every 5 minutes and
pulling it back up if it's gone (back up crontab before installing). The
sampler is stateless and picks back up from the sampling history after a
restart. Once live, the web page shows real jobs. Steps follow Task 9 of
the implementation plan.

**Blocked by:** 06 Web and json outlets

**Status:** resolved

- [ ] curl on this machine's port 8377 /json produces valid JSON
- [ ] A browser (via port forwarding) sees the job table
- [ ] Killing the session gets the sampler pulled back up by crontab
  within 5 minutes

## Comments

- 2026-08-08 transcribed by the main conversation (deployment
  constraints to follow before launch, implementation must comply):
  first, the resident tmux session and the crontab watchdog line must
  point at the main repo /home/y-guo/reproduce/new1's code and run.py,
  never at your own temporary worktree path (it gets deleted at wrap-up,
  so pointing there leaves it dangling); second, once the later tickets
  12 (incident trigger) and 13 (vLLM service record) merge into main, the
  sampler needs one restart to pick up the new code; note this in your
  report as a reminder to the main conversation, not something for you to
  do.
- 2026-08-08 ticket-run: BLOCKED → ready-for-human. Completed: the
  resident session new1_sampler is up in tmux on the login machine,
  pointing at the main repo /home/y-guo/reproduce/new1 (not a worktree);
  curl localhost:8377/json produces valid JSON, and the root path
  returns 200 with the job-table HTML (verified via curl equivalence,
  with browser eyeball confirmation via port forwarding left to the
  user). Not completed: the crontab watchdog, since installing crontab
  was blocked by the permission classifier for both the subagent and the
  main conversation (crontab -l, being read-only, was unaffected; the
  current crontab is empty, backed up at /tmp/crontab.bak), so
  acceptance item 3 (pulling the sampler back within 5 minutes of
  killing the session) could not be tested as a result. The branch has
  no commits (this ticket only touches system state, not repo files),
  and the branch has been deleted. The watchdog line to install is in
  the report's Step 2 (sdd/2026-08-08-wave1/T14-report.md). The user
  needs to pick one of two options: execute the install command from the
  report themselves in the conversation with the `!` prefix, or add a
  Bash permission rule to settings allowing crontab writes and have the
  main conversation re-run this step.
- 2026-08-08 ticket-run re-check wrap-up: resolved. After the user's
  explicit instruction in the conversation, the watchdog crontab was
  installed successfully (the line has one correction beyond T14's
  original report: cd into the main repo before running run.py inside
  the tmux command, otherwise cron pulling it up with cwd=$HOME can't
  find run.py). Final state of the three acceptance items: (1) curl
  /json valid JSON, confirmed (includes sessions missing from the ledger
  as extras); (2) job-table HTML verified via curl equivalence, confirmed
  (browser eyeball confirmation left to the user, via VS Code port
  forwarding on 8377); (3) killing the session and cron pulling it back,
  tested for real: killed at 08:17:35, pulled back at 08:20:01 (160
  seconds < 5 minutes), confirmed. The current session is running the
  latest main including T12's pure functions; after T13 merges, one more
  restart is needed (noted by the main conversation).
