---
name: ticket-run
description: >-
  The sole entry point for executing tickets in batch from .scratch/<feature-name>/issues/
  — the main conversation splits tickets into waves by Blocked-by, dispatches one workflow
  per wave, tickets within a wave run in parallel (each ticket gets its own git worktree
  and its own branch), the workflow internally runs each ticket through "implement →
  review → fix loop (capped at 5 rounds)," and branch merging, reconciliation,
  adjudication, and final review return to the main conversation. Invoke whenever
  Dungeon♂Master says "execute tickets", or a batch of .scratch issues needs implementing.
  Chinese triggers: "执行工单" / "清 ticket" / "把这批 issue 做了" / "按 spec 实施".
version: 1.0.0
---

# ticket-run — the full lifecycle of batch ticket execution

Where the design comes from: the process skeleton is copied from superpowers's subagent-driven-development
(a brand-new implementer per task + one review per task + a fix loop capped at 5 rounds + a final
whole-branch review at the end); control flow is handed to a deterministic Workflow-tool script (the
round cap, gates, and resume-from-checkpoint are all hardcoded in JS, not left to the main conversation's
self-discipline); implementation discipline (TDD at the seams, running unit tests often, a full run at
the end, committing per unit) is hardcoded into the implementer's procedure.

Fixed paths:
- Wave script: `.claude/skills/ticket-run/wave.js`
- Role procedures: `.claude/skills/ticket-run/prompts/{implementer,reviewer,re-reviewer,final-reviewer}.md`
- Ticket conventions: `notes/docs/agents/issue-tracker.md`; status strings: `notes/docs/agents/triage-labels.md`
- Per-wave report directory: `.scratch/<feature-name>/sdd/<date>-wave<N>/` (goes into git, part of the review record)

## Phase 0 — Split into waves

1. Read `.scratch/<feature-name>/spec.md` and every ticket under `issues/`.
2. The executable set = the tickets the user named; if the user didn't name any, take every ticket with `Status: ready-for-agent`.
3. Build a dependency graph from each ticket's `Blocked by:` line, and cut it into waves: wave 1 = tickets with
   no unfinished prerequisite, wave 2 = tickets that only depend on wave 1, and so on.
4. Create a todo for each ticket, noting its wave number and Blocked by. The todo is only this session's view —
   the real source of truth is always the ticket file's `Status:` line; if the session breaks, rebuild the waves
   from the files.

Each wave holds 2 to 4 tickets. A single ticket takes up to 12 agent calls in the worst case (1 implementation +
1 review + 5 fix rounds, each round being 1 fix + 1 re-review); a wave that's too big will blow the budget of a
single workflow run.

## Phase 1 — Precheck and commit before launch

1. Do one precheck pass: tickets that contradict each other, a ticket that contradicts the spec, an approach a
   ticket requires that collides with a repo hard rule (skipping a new file's five annotation lines in `README.md`,
   writing a big artifact to home, hand-editing `jobs/RESULTS.md`) — gather all of these into one batch question
   and ask the user once before proceeding. If the scan finds nothing, proceed silently.
2. The working tree must be clean; commit anything uncommitted first (repo hard rule: commit before launch,
   otherwise the record can't trace back to the code).
3. Create this wave's report directory, change every ticket in this wave's `Status:` to `claimed`, and commit
   that together with the report directory.

## Phase 2 — Launch a wave

Launch with the Workflow tool; the script pins down the control flow:

```
Workflow({
  scriptPath: ".claude/skills/ticket-run/wave.js",
  args: {
    repo: "/home/y-guo/reproduce/new1",
    feature: "<feature-name>",
    wave: "<date>-wave<N>",
    promptDir: "/home/y-guo/reproduce/new1/.claude/skills/ticket-run/prompts",
    reportDir: "/home/y-guo/reproduce/new1/.scratch/<feature-name>/sdd/<date>-wave<N>",
    tickets: [{ id: "01", path: ".scratch/<feature-name>/issues/01-xxx.md" }, ...]
  }
})
```

Three rules hardcoded into the script, not to be changed at launch time:
- Tickets within a wave run in parallel; inside a single ticket everything runs strictly in sequence. Every
  ticket's changes all land on its own branch `ticket/<wave name>/T<NN>`, and the agent builds its own worktree
  under `<repo>-wt/` next to the repo, deleting it as soon as it's done (git's worktrees share the object store,
  so a review in the main repo can get the diff just from the sha). After launch, nobody touches the main repo's
  working tree; code merging happens at reconciliation time. Worktrees are only created and entered with git
  commands — the dispatch message bans the EnterWorktree tool, because a subagent that calls it hangs and
  never returns. How to tell a ticket is stuck: read the timestamp of the last line in the workflow directory's `agent-*.jsonl`; if
  it's been stalled for more than half an hour, TaskStop it and resume with `resumeFromRunId` below.
- Every agent's model is explicitly hardcoded to opus. Not passing a model would inherit the main conversation's
  Fable, which collides with the hard rule banning Fable for subagents.
- The fix loop caps at 5 rounds; once it hits the cap, it returns with unresolved findings and the script does
  not adjudicate.

The workflow runs in the background; wait for the completion notification. If it hangs midway or the script
needs changing, resume with the runId from the tool result paired with `resumeFromRunId` — tickets that
already finished hit the cache and won't rerun; if a return value looks suspicious, read the `journal.jsonl`
in the transcript directory before judging.

## Phase 3 — Reconciliation (after each wave returns)

The workflow returns a structured result per ticket (including each one's branch name). Merge the code first,
then do the status accounting:

1. For `DONE` tickets, `git merge --no-ff ticket/<wave name>/T<NN>` one by one in ticket-number order. If a
   merge conflicts, stop and report to the user — a conflict itself means these two tickets weren't actually
   independent, and the wave split was wrong.
2. Don't merge `CAP_TRIPPED` branches yet; decide whether to merge or discard once the adjudication below is done.
3. Cleanup: delete merged branches once merging is done, `git worktree prune`, and delete leftover directories
   under `<repo>-wt/`.

Then handle each ticket by status:

- `DONE`: change the ticket's `Status:` to `resolved`, and append an entry under the ticket's `## Comments`:
  commit range, number of fix rounds, remaining minors, implementer concerns.
- `CAP_TRIPPED` (hit all 5 rounds with findings still unresolved): the main conversation adjudicates each one —
  if the review was wrong, shelve it and write down why; a real problem nobody depends on also gets shelved; a
  real problem that a later ticket needs to build on stops and gets reported to the user. Adjudications go into
  the ticket's Comments one by one, never silently dropped.
- `BLOCKED` / `NEEDS_CONTEXT`: if what's missing is context, fill it in and send this ticket out alone in
  another wave; if what's missing is a user decision, change `Status:` to `ready-for-human` and report it up.
  Work that needs a GPU comes back as BLOCKED (implementers are forbidden from launching GPU processes) — the
  main conversation goes through gpu-run.
- The `cannotVerify` list (items the review couldn't check in the diff): the main conversation checks these
  itself; if verification finds a real gap, treat it as a finding and send this ticket out for another wave of
  fixing.

Once reconciliation is done, commit once (ticket status lines + Comments + report directory), then launch the
next wave, until the waves are empty.

## Phase 4 — Final review and report

Once all waves are done, do one whole-branch final review, a single agent without a workflow:

1. Use the Agent tool to dispatch opus, with the prompt pointed at `prompts/final-reviewer.md`, giving it the
   starting commit (the HEAD before the first wave launched), the ending HEAD, the spec path, every ticket
   path, and the minors and shelved list accumulated during reconciliation.
2. If the final review has findings: dispatch one opus fix agent to fix the whole list in one pass (never one
   agent per item), then dispatch one scope-limited re-review. Anything remaining is adjudicated per Phase 3's
   CAP_TRIPPED rule.
3. Report to the user: each ticket's final status and commit range, the shelved list, and the final review's
   conclusion. State facts only, no commentary.

## Hard-rule wiring

- Already hardcoded in the implementer's procedure: the file's five annotation lines go into `README.md` and
  `run.py selfcheck` proves them, big artifacts only written to NFS, uv managing the environment, no launching
  GPU processes, no hand-editing `jobs/RESULTS.md`. Review catches these as spec gaps, but the main conversation
  checks again at reconciliation.
- This skill manages code tickets. If a ticket itself needs to run a GPU experiment, the implementation part
  goes through this skill as usual, and the launch part goes back to the main conversation through gpu-run.
- If this skill's workflow or script changes, write it back into this file per the repo's convention, in the
  same commit.
