---
name: research-loop
description: Use when gyb wants to set up the research loop in a repository, asks which role to open next, or asks whether old code should move. Only gyb invokes this skill.
disable-model-invocation: true
---

# research-loop

<!-- Sources: 08 L106 (three things and nothing else), 08 L108 and D-13 (only gyb invokes; the header field is the mechanism, rl init refusing inside a role session is the second gate), 08 L112-L116 (the five routes), 08 L118 (loading a role), 08 L9-L13 and L36 (what rl init builds, rerun safety, the questions it asks), 08 L122 and 11 L62 (migration). -->

This skill does three things: initialize a repository for the loop, remind about migration, and point to the next role. It does nothing else. gyb invokes it; no model does.

## Initialize

Run `rl init` from a bare terminal, never inside a role session; it refuses there. It creates the configuration file `research-loop.json`, the ledger directory `loop/`, the four role directories `experiments/`, `analysis/`, `review/` and `notes/`, seeds the shared statistics helpers under `analysis/`, and appends one section of three sentences to the repository's CLAUDE.md without touching anything already there: without gyb's permission, `experiments/`, `analysis/`, `review/` and `loop/` are changed only inside a session that loaded the matching role; a session that loaded run follows run's skill, which is a superset of the host's GPU procedure, so the host's single-entry rule reads as the run skill there; and the ledger files under `loop/` plus the lock file do not count as a dirty tree. It asks the repository-bound configuration keys one by one (artifact roots, the GPU state file, the host launcher's four command templates, how the repository runs things, the host's own ledgers); a skipped key stays empty and is listed at the end. Rerunning is safe: what exists is left alone, what is missing is added, and the command prints two columns, existed and created. It never edits host code and never writes into the repository's own agent or settings files. Inside a role session the plugin's session-start hook puts `bin/rl` on the PATH, so every skill writes the bare `rl`; when that hook is not installed, call it by its full path under the plugin root instead.

## Migration

Moving old code into `experiments/` means moving the files, not registering a pointer: the write hook judges by path, so code that stays outside `experiments/` stays outside the hook. Whether and when to move is gyb's manual call; deploy only points out old code it meets. Day-to-day changes to host files outside `experiments/` are reported on deploy's detail report, not here.

## Which role next

1. A batch of results is in: open analysis to produce the numbers, then idea to record the decisions.
2. A new idea: open idea to record the decision, then let idea open the work orders.
3. A result looks wrong: open reviewer and name the decision.
4. A quick look without a decision or a report: gyb names the quick lane in the deploy or analysis session; everything else takes the normal path.
5. Periodic tidying, on gyb's own schedule since there is no reminder: `rl status`, then `rl reclaim` to list, `rl reclaim --apply` to release, pull orders up owner by owner, then `rl doctor`.

A role is loaded by typing `/research-loop:` followed by the role name in a terminal, one role per session.
