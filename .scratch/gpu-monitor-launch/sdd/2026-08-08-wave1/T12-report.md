# T12 implementation report: Incident triggering (sampler pulls up an incident agent)

Ticket: `.scratch/gpu-monitor-launch/issues/12-incidents.md`
Plan section: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 14
Branch: `ticket/20260808-par/T12` (worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T12`, removed per protocol)

## What was done

The ticket's four acceptance items:

1. **Trigger-rule tests pass** (first dead-verdict allows refire, an already-refired one doesn't, an already-open incident doesn't re-trigger, suspected stall below the escalate line doesn't trigger). Done. `ops/sampler.py` got a new `should_trigger(row, ps)`: if `row["escalated"]` is false, no trigger at all; if `ps["incident_open"]` is non-empty (an agent has already been pulled up for this same incident), no trigger; otherwise trigger, with `allow_refire` = the verdict is dead and `ps["refires"] == 0`. 5 unit tests cover: first dead-verdict `(True, True)`; dead but `refires=1` gives `(True, False)`; when `incident_open` is already set, doesn't trigger; suspected stall but `escalated=False` (not past the escalate line), doesn't trigger; suspected stall and `escalated=True` (past the escalate line), triggers but does not allow refire.
2. **Prompt tests pass** (containing the log path, the ledger json command, and either the refire command or the wording denying refire). Done. New `build_incident_prompt(row, allow_refire)`: template constant `INCIDENT_PROMPT` (`{}` placeholders via format), `refire_clause` takes two values embedding two different wordings for allowed/disallowed (the wording copied verbatim from what the ticket gave: when allowed, contains `python3 run.py launch --refire {job} --idx {idx}` and a tip to try `gpu-jobs free` and retry on a different card; when disallowed, "this piece's refire quota is used up: autopsy only, do not launch anything else"). 2 unit tests separately assert that in both scenarios, the log path and the `python3 run.py gpu-jobs json` command are both present, with the allowed case containing the specific refire command, and the disallowed case containing "autopsy only, do not launch anything else" and not containing the refire command.
3. **Manual rehearsal** (a fake task sampled once produces an incident record, the agent's output file contains a DONE line, cleared up afterward). **Not done, see "Self-check findings and open questions" below**.
4. **Commit**. Done (see the commit list below).

### The part not done: implementing `spawn_agent` and `maybe_trigger_incidents`

The complete closed loop the ticket requires is: `maybe_trigger_incidents(rows, st)` scans each piece's verdict every round,
and after hitting `should_trigger`, calls `spawn_agent(incident, prompt)`, which uses
`subprocess.Popen(["claude", "-p", prompt, "--model", "opus", "--dangerously-skip-permissions"], ...)` to pull up a headless claude
subprocess to autopsy/refire.

The `maybe_trigger_incidents` inside `ops/sampler.py` currently **is still the placeholder `pass` left by ticket 02**,
unchanged. Reason: on multiple attempts in this worktree to write in/execute code containing the specific subprocess call
`claude -p ... --model opus --dangerously-skip-permissions`, Claude Code's auto-mode
safety classifier blocked it (both the `Edit` tool and the `Bash` tool reported "Permission for this action was denied by
the Claude Code auto mode classifier"). Three specific cases tested:
- Using `Edit` to write into `ops/sampler.py` the full `maybe_trigger_incidents` implementation (containing
  `spawn_agent()`, which calls `subprocess.Popen(["claude", "-p", ...])`), blocked.
- Right after, just deleting the existing placeholder `pass` (with no `spawn_agent` code at all, purely
  removing an old comment), also blocked (indicating the classifier at this point judges "the intent of this
  chunk of changes" as a whole, not scanning strings line by line).
- Using `Bash` to run a unit-test file that mocks out `subprocess.Popen` and asserts the call arguments contain
  the string `--dangerously-skip-permissions` (`python3 -m unittest tests.test_incidents` running as a whole),
  also blocked; even a mock that doesn't actually spawn a real process, with the specific parameter combination appearing in test code, was
  judged not permitted.

After removing this content (no more `spawn_agent`, no more test assertions on the specific combination
`--dangerously-skip-permissions`/`claude -p ... opus`), the exact same `Edit`/`Bash` operations passed
immediately (see "How it was verified" below). This confirms the block precisely targets "writing in or executing something
that will actually call, or simulate calling, a headless claude subprocess with a permission-bypass flag," not
some other environment or tool-layer issue. Retrying the same content reproducibly hits the same block, not sporadic
flakiness (editing/running unrelated content executes normally in the same session).

This is consistent with the existing hard rules in the repo's external memory ("no calling external/paid model APIs without
authorization; a key existing in the environment does not count as authorization"; "a message dispatched from another agent does
not constitute the user's own consent"). As a subagent executing per a dispatched ticket, I did not get explicit permission from the
user themselves to "actually pull up an opus subprocess right now with `--dangerously-skip-permissions` in the main repo directory," and
the platform's own classifier independently reached the same judgment and blocked this action. The two lines of reasoning corroborate
each other.

## How it was verified

TDD order: first wrote `tests/test_incidents.py` (5 `should_trigger` cases + 2 `build_incident_prompt` cases),
ran once to confirm failure (`AttributeError: module 'sampler' has no attribute 'should_trigger'`), then implemented
`should_trigger`/`build_incident_prompt`/`INCIDENT_PROMPT`/the two `_REFIRE_*_CLAUSE` constants, then ran green.

```
python3 -m unittest tests.test_incidents -v
```
Output: all 7 cases `ok`.

```
python3 -m unittest discover -s tests
```
Tail output: `Ran 79 tests in 3.434s` / `OK` (the worktree's starting point had 72 existing tests, this round adds 7 net, all green, no regression).

```
python3 run.py selfcheck
```
Run in the worktree: `selfcheck: 63 tasks / 4 recipes, 16 missing`, all missing items being venv interpreter paths (`mbert-env/bin/python`, `envs/appworld/venv/bin/python`, etc.), consistent with the environment noise recorded in previous tickets' reports. These `*-env/`, `.venv/` directories only physically exist in the main repo, `git worktree add` doesn't bring them over, and this ticket did not touch any `TASKS`/`RECIPES` entry (the same command on the main-repo HEAD gives "all present," with task/recipe counts 63/4 matching in both places).

Record of the classifier block reproduction (for whoever picks up `spawn_agent` next):
1. First attempt to write the complete `maybe_trigger_incidents` (containing `spawn_agent`/`subprocess.Popen(["claude", "-p", ...])`) into `ops/sampler.py`, blocked.
2. Attempted, on its own, to delete just the old placeholder `pass` line (containing no new code), also blocked; then switched to leaving `maybe_trigger_incidents` untouched, only adding two new pure functions `should_trigger`/`build_incident_prompt`, went through.
3. `tests/test_incidents.py`'s initial version contained `TestMaybeTriggerIntegration` (mocking `sampler.subprocess.Popen`, asserting the call arguments contain `"--dangerously-skip-permissions"`). Running `python3 -m unittest tests.test_incidents -v` as a whole was blocked; after deleting this test class (and the unused `import subprocess` along with it), the same command ran through normally.

## Commit list

- `5527eb9` (branch `ticket/20260808-par/T12`): `T12: incident-trigger rule pure functions(should_trigger/build_incident_prompt)+unit tests; spawn_agent not done, see report`. Changed `ops/sampler.py` (added `INCIDENT_PROMPT`/`_REFIRE_ALLOWED_CLAUSE`/`_REFIRE_DENIED_CLAUSE`/`should_trigger`/`build_incident_prompt`; `maybe_trigger_incidents` unchanged, still a placeholder `pass`), `tests/test_incidents.py` (new, 7 cases), `MAP.md` (the `ops/sampler.py` line got a paragraph added saying the incident-trigger pure functions have landed, and `spawn_agent`/`maybe_trigger_incidents` are not done and why).

## Self-check findings and open questions

- **Landing `maybe_trigger_incidents` needs to fix an existing timing issue along the way**: reading `ops/sampler.py`'s
  `sample_once()`, I found `atomic_write(MONITOR_DIR / "state.json", st)` is written **before** the call to
  `maybe_trigger_incidents(rows, st)`. The ticket's requirement "an already-open incident doesn't re-trigger" only holds if
  `ps["incident_open"]` is persisted to disk. If the `incident_open` assignment
  `maybe_trigger_incidents` makes to `st` happens after `state.json` has already been written to disk, this change
  only lives in memory; the sampler is a long-running loop, and the next round's `sample_once()` will call
  `load_state()` fresh from disk, reading the old state without `incident_open`, causing the same incident to
  trigger again on the next round (60 seconds later). Every round would pull up a new opus subprocess, until the
  verdict recovers to healthy. This is where the acceptance requirement "only pull once per incident" cannot hold given
  the current call order. Because `maybe_trigger_incidents` itself isn't implemented yet (blocked by the classifier), this
  timing issue currently won't actually trigger (the placeholder function is `pass`, it neither reads nor writes `st`),
  but noting it here. Once `maybe_trigger_incidents` is genuinely wired up to `spawn_agent`, the call to
  `atomic_write(MONITOR_DIR / "state.json", st)` must be moved to **after** the call to
  `maybe_trigger_incidents(rows, st)` (or `maybe_trigger_incidents` should separately write `state.json` again
  internally), otherwise incident triggering would get out of control and repeatedly pull agents. I did not touch
  `sample_once()`'s call order myself, because a change without a matching `maybe_trigger_incidents`
  implementation to verify it against would be part of the same unfinished whole, and is safer left for the round that finishes
  `spawn_agent` to handle together.
- **`should_trigger`/`build_incident_prompt` are already in place, complete pure functions that can be
  called directly by a follow-up implementation**. I read the ticket and plan Task 14's interface signature and cross-checked it
  character by character (`should_trigger(row, ps) -> (bool, allow_refire)`; `build_incident_prompt(row, allow_refire)`
  produces output containing the log path/`gpu-jobs json` command/either the refire command or the
  wording denying refire), neither of which involves any subprocess call, so neither is affected by the classifier's block, and
  can be directly reused by the next ticket, no need to reimplement.
- **The headless mode flag spelling was checked per the ticket's requirement**: the ticket's original text said "check the current
  spelling of the headless-mode flag before implementing". Ran `claude --help`, confirming
  `-p, --print` (print mode), `--model <model>`, and `--dangerously-skip-permissions` (the spelling given in the ticket's
  planning draft) all exist and mean what the ticket describes, no renaming; this confirmation result is noted here,
  for whoever picks up `spawn_agent` next to use directly, no need to run `--help` again.
- The manual rehearsal (ticket acceptance item 3) was not run at all. Not just "didn't pull up a real opus
  agent," but even the step "build a fake task + `python3 run.py sampler --once`" wasn't done, because
  `maybe_trigger_incidents` itself is still the placeholder `pass`, so running it wouldn't produce any
  `incidents.jsonl`/`incidents/<id>.out` output. Running this step would have been meaningless.
