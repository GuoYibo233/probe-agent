# T14: Sampler goes live, implementation report

## Status: BLOCKED

Of the ticket's three acceptance items, the 1st is done, the 2nd was verified by an equivalent means, and the 3rd is stuck on the permission system and could not be done. The crontab watchdog step was blocked by Claude Code's auto-mode permission classifier, the crontab-write action was directly denied. This is not something I was technically unable to do; the permission system did not allow it. Details in "Self-check findings and open questions" below.

## What was done (against the ticket point by point)

The ticket points to implementation plan Task 9, three steps: start the daemon process, install the watchdog, verify. Executed in order:

**Step 1: start the daemon process.** Ran the following in the main repo `/home/y-guo/reproduce/new1` (not my temporary worktree):

```
tmux new-session -d -s new1_sampler 'python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'
```

The log's `[sampler] cwd=/home/y-guo/reproduce/new1` confirms the process's cwd points at the main repo, not the worktree; the constraint explicitly required in the ticket's comments (must not point at a temporary worktree, because worktrees get deleted at wrap-up) is satisfied. The session is currently alive (`tmux ls` shows `new1_sampler: 1 windows`), the log has three lines, no error:

```
[sampler] cwd=/home/y-guo/reproduce/new1
  python3 /home/y-guo/reproduce/new1/ops/sampler.py
[sampler] web on :8377
```

**Step 2: install the watchdog.** Per the plan, backed up crontab first (`crontab -l > /tmp/crontab.bak`, this step itself wasn't blocked, and confirmed there was no crontab at the time: `no crontab for y-guo`), then attempted to install the following line into it:

```
*/5 * * * * tmux has-session -t new1_sampler 2>/dev/null || tmux new-session -d -s new1_sampler 'python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'
```

The write action (`... | crontab -`) was denied by Claude Code's auto-mode permission classifier, error message verbatim:

> Permission for this action was denied by the Claude Code auto mode classifier. Reason: Blocked by classifier. ... To allow this type of action in the future, the user can add a Bash permission rule to their settings.

Tried twice (once combining the backup and install in one command, once running just the install line alone); both times it was blocked; `crontab -l` (pure read) wasn't affected, ran normally. Per the implementer's protocol requirement of "must not work around a permission denial," I did not try any other means to get around this block (e.g. directly writing the file under `/var/spool/cron`, using `at` instead, or writing a python library to change crontab). Crontab is currently empty, untouched by me, `/tmp/crontab.bak` is an empty file (backed up before the change, its content matches the empty state before the change).

**Step 3: verify.**

- `curl -s localhost:8377/json` returns valid JSON, already verified:
  ```
  {"sampled_at": 1786143706.27, "rows": [], "extras": {"tokyo105": ["7-29run", "7-31run", "flow-8-1", "new1_sampler", "rc-claude"]}, "incidents_tail": []}
  ```
  `rows` being empty is really the case. The ledger (`ops/jobs.json`'s `active`) was empty at the time, no GPU task was registered and running, this is not a sampler problem. `extras` shows `new1_sampler`'s own session, the out-of-ledger reminder mechanism is working, matching the design.
- Looking at the task table in the browser (via port forwarding): I don't have a real browser available, used `curl -s -o /tmp/t14-root.html -w "HTTP %{http_code}"` instead to check the root path's return. HTTP 200, and the body contains `<title>new1 long-running task monitor</title>`, `<h2>task table</h2>`, `<table...>`, currently showing "no registered running tasks" (matching the empty ledger). This is an equivalent verification, not the ticket's required visual confirmation in a browser; a user with browser port forwarding opening `localhost:8377` should see the same content, but that statement is my inference based on the returned code content, not something I saw with my own eyes in a browser.
- Kill the session and wait 5 minutes to see if crontab pulls it back: could not do this, because Step 2 wasn't installed successfully, no watchdog to test. **Did not actually kill this currently-running session to test it**, because with no watchdog in place, killing it would really take it offline, not a test.

## How it was verified

- `python3 -m unittest discover -s tests -v` (run in my worktree, before the deployment action, to confirm the starting-point code was healthy):
  ```
  Ran 41 tests in 3.249s
  OK
  ```
- `NEW1_MONITOR_DIR=/tmp/t14-monitor-smoke python3 run.py sampler --once` smoke test (an isolated directory, not touching the production monitor directory): ran through, `latest.json` is valid JSON, `rows` empty (the isolated directory has no ledger).
- After deployment, `curl -s localhost:8377/json | python3 -m json.tool`: valid JSON, content shown above.
- `curl -s -o /tmp/t14-root.html -w "HTTP %{http_code}"`: `HTTP 200`, content shown above.
- `tmux ls | grep sampler`: `new1_sampler: 1 windows (created Sat Aug 8 07:23:39 2026)`, checked multiple times after deployment, still there.
- `tail -30 /net/.../monitor/sampler.log`: three lines, no traceback.

## Commit list

None. This ticket, per implementation plan Task 9, only involves "the login machine's crontab (system state, not a repo file)" and the persistent tmux session, and does not change any repo file; the worktree's `git status --short` stayed clean throughout, nothing to commit. The worktree has already been removed via `git worktree remove`; branch `ticket/20260808-par/T14` is kept around (`base == head == ec1da2841499d0689e464e8743a33cb8851022b3`, no new commit).

## Self-check findings and open questions

1. **Crontab-writing was blocked by the Claude Code permission system, this isn't a matter of my own judgment about whether to do it.** The ticket's usual convention "no launching GPU processes" is the only self-restriction. The sampler isn't a GPU process, and the ticket comments also explicitly required me to point tmux/crontab at the main repo, all of this pointed toward "this step should actually be executed by me." But the auto-mode classifier blocked the action of "writing to crontab" itself, and its error message suggests "the user can add a Bash permission rule to allow it." This is an environment-level permission boundary; I have no permission to work around it, and per protocol shouldn't. **This needs a user decision**: either the user installs this crontab line themselves (the backup file is at `/tmp/crontab.bak`, the line to install is pasted above at Step 2), or the user adds a Bash permission rule to Claude Code allowing crontab writes and this step is rerun.
2. **I left the tmux session running, did not kill it.** Even though acceptance item 3 (crontab pulling it back within 5 minutes) can't be done, the session itself is already running, satisfying the "going live" half of "after going live, the web page can see real tasks" ("real tasks" half needs to wait until a real GPU task is registered into the ledger, which isn't something I control, the ledger is currently empty). Leaving this session running is deliberate. The ticket's goal is to have it running persistently; not having a watchdog yet doesn't mean it should be turned off now, turning it off would actually be a step backward. If the user thinks it should wait until the watchdog is installed before going live together, please tell me and I'll go kill it.
3. **Acceptance item 2 (looking at the task table in a browser), I only did the equivalent curl-based verification**, having no real browser available. Already noted above that this is an equivalent verification, not the originally-required verification method; it would be more reliable for the user to confirm it once themselves via port forwarding.
4. **A leftover reminder (named in the ticket comments, not mine to do)**: once tickets 12 (incident triggering) and 13 (vLLM service ledger) are merged into main, this `new1_sampler` session is still running the pre-merge code, and needs a restart to pick up the new code. This needs to be handled by the main session after 12/13 are merged.
5. At deployment time, the main repo's `git status --short` had one uncommitted change,
   `.scratch/gpu-monitor-launch/sdd/2026-08-08-wave1/T09-report.md`, which is the parallel-running T09 ticket writing its own report, unrelated to this ticket. I did not touch it.
