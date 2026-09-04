# research-loop plugin (v2, skeleton build started 2026-09-05)

This directory is the body of the research-loop plugin. It lives inside the new1 repository and is not a separate repository (part 00, ruling 2). The plugin gives a research repository five roles: idea, deploy, run, analysis, reviewer. The roles talk to each other only through nine ledgers under the research repository's `loop/` directory, and the ledgers are read and written only through the `bin/rl` command-line tool. Plugin-level hooks block exactly two kinds of writes: writing into another role's directory, and writing `loop/` directly (part 06, L13).

The design source is `plans/research-loop-parts/` (parts 00 to 30). The build steps are in part 30, section 3; the build guide of 2026-09-04 is `plans/2026-09-04-research-loop-work-guide.md`. Every piece of logic in this tree points back to a part number and line number, written as `06 L178`. Anything not yet ruled is marked `PENDING(issue NN)` (an entry in `plans/research-loop-parts/sync-inbox.md`) or `PENDING(part 22 L113)` (an entry in a part).

## What each directory holds (part 08, section 4)

| Directory or file | Contents |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `skills/` | Six skills: one entry skill and one per role; role skills do not declare hooks in their header |
| `agents/` | Five role agent definitions that only shape a subagent (prompt, preloaded role skill, narrowed tool set); no hooks |
| `common/` | Shared master documents: global rules, glossary, five-field spec template, reading order, review checklist; carries `rules_version` |
| `tables/` | Ledger list, handoff state-transition table, role json files, gyb's use-case table |
| `schemas/` | Row format of each of the nine ledgers |
| `scripts/` | Implementation of ledger writes and queries |
| `bin/rl` | Command entry point, including status, inbox, trace, reclaim, doctor |
| `hooks/` | Plugin-level hook file `hooks/hooks.json` plus scripts: write-permission hook, session registration hook, session close hook |
| `monitors/` | One launch watchdog, started only when a run session comes online |
| `tests/` | Tests, entry point `python3 research-loop/tests/run_all.py` |

There is no `workflows/` directory: dispatch starts one subagent per handoff, so no fan-out script is needed (part 08, L102).

## Models: fable is the exception gyb named on 2026-08-16

When a role is started by an agent (a subagent or a workflow), run, deploy and analysis use opus, and idea and reviewer use fable; when gyb loads a role by hand, the role uses the current session's model (part 00, ruling 3; written into the `model` field of the five role json files). Using fable for idea and reviewer disagrees with the machine-level `~/.claude/CLAUDE.md` rule "subagents do not use Fable by default"; the project rule wins: fable is the exception gyb named on 2026-08-16. The exception applies only to the plugin at run time, not to subagents dispatched during the build to write code or documents (HANDOFF, section 8).

## Status and commit conventions

Build step 1 was completed on 2026-09-05: the old plugin (0.1.0) was retired as a whole and stays in the git history before commit 3ae0bc9; no old file remains in the working tree (part 00, ruling 1). Empty directories are held by `.gitkeep` files because git does not record empty directories.

Commit prefix during the build is `research-loop v2:`; changes to the master documents after the plugin is in use take the prefix `research-loop rules:` and are followed by a run of `tests/run_all.py` (part 30, section 3).
