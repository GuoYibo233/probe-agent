---
name: research-loop
description: Thin routing shell for the research-loop plugin -- matches what the user just said against the routing table and hands off to the right layer skill or action. Invoke first whenever a research-loop phrase is heard and no layer session is already active (a new idea, "run this", "what's pending", "check X", "I've decided", etc.) -- this skill decides where it goes, then gets out of the way.
---

# research-loop -- routing shell

`<plugin-root>` below means this file's grandparent directory (`../..` from
here).

## Job

One line: read the user's sentence, look it up in
`<plugin-root>/tables/routes.json`, hand off to whatever it names. That's the
whole job -- this skill never decides what a layer does, never runs a ledger
write itself, and carries no other content.

## How to read the table

`tables/routes.json` is the single source of the routing table; nothing in
this file repeats a row from it. Each entry has a trigger phrase (`say`), a
stage tag, a target (`to`), and a `kind` (`handoff` or `command`). Match on
intent, not exact string. Four rules about the table, not its rows:

- **Every bare CLI string in the `to` column is one invocation shape**:
  `python3 <plugin-root>/scripts/<file>.py ...` for a standalone script, or
  `python3 <plugin-root>/scripts/ledger.py <subcommand> ...` for anything
  the ledger CLI owns. No row spells out the interpreter or the script
  path a second time -- this is the one place that convention is stated,
  and every `to` value in the table follows it.
- **`kind` tells a layer/role/rail target apart from a command target.**
  `handoff` hands control to a layer skill, `inspector`, or a project rail
  -- and only a `handoff` target is capable of setting the receiving
  session's layer identity ("Layer identity, restated once" below).
  `command` executes in place, in this session, right now -- it never
  changes who this session is, and this session stays exactly where it was
  once the command returns.
- **Every entry can fire at any time.** `stage` is a common-case label for
  when people usually reach for that entry, not a whitelist that blocks it
  outside that stage.
- **The table is a discoverable index, not the only door.** Anything in it
  can also be triggered by naming the target action directly, table lookup
  or not.

**No match**: don't guess which layer the user means. List the `say` column
back to them and ask which one fits, or ask directly what they want. Never
default to a layer silently.

## Gate before handing off to a rail

If the target this sentence resolves to is a `rails.*` entry (config §7 --
i.e. the handoff leaves the plugin body for a project rail), run
`python3 <plugin-root>/scripts/ledger.py config-check` first. A null
`rails.*` key means that rail is locked (`tables/config.json` null-lock
rule, no silent downgrade) -- refuse the handoff and name the null key(s) to
the user. Handoffs that stay inside the plugin (routing to a layer skill)
don't need this check here; the receiving layer's own SKILL.md runs
`config-check` where its own work needs it.

## Layer identity, restated once

Full rule: each layer's SKILL.md §"Layer identity" and spec §1. A session's
layer identity is set at exactly one of two entry points -- the user
triggering a layer skill (including arriving here and being handed off), or
a subagent dispatch contract pinning it. This router *is* one of those two
entry points: the handoff it performs is what sets the receiving session's
layer identity, for that session's whole lifetime. This skill itself never
claims a layer identity -- it only routes.
