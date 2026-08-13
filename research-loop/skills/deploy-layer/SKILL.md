---
name: deploy-layer
description: The research-loop deploy layer -- code's home turf. Turns approved principles into a spec, spec items into tickets, tickets into code, then writes launch orders, runs criteria, and collects numbers. Invoke when the user wants a spec written or approved, work ticketed and built, a decision point resolved, an experiment launched, or a batch closed out -- or was handed off here by the research-loop router.
---

# deploy-layer

`<plugin-root>` below means this file's grandparent directory (`../..` from
here).

## 1. Layer identity

The deploy layer is code's home turf (spec §1, "部署层" row): it turns
principles into a spec, a spec into tickets, tickets into code (review and
tests happen here), then launches experiments and collects numbers.
Downward it hands the run layer "what to run" (a launch order, one job,
fully specified); upward it hands the idea layer "how to read" (a batch
report's `how_to_read` header field). Bugs the run layer escalates come back
here for fixing.

Identity is set at exactly one of two entry points: the user triggering
this skill (including via the router), or a subagent dispatch contract
pinning `--layer deploy`. It does not change mid-session; needing another
layer's work goes through cross-layer transport (a dispatch or a new
session carrying a ledger entry), never a mid-session switch.

## 2. First action

```
python3 <plugin-root>/scripts/ledger.py status --layer deploy
```

Run this before anything else, every session. Three read-only blocks: this
layer's working face (specs in flight, open tickets, pending/unrecorded
launch orders, batches awaiting a report or an inspection), this layer's
pending queue (open entries addressed to deploy, plus answered entries
deploy raised now awaiting confirmation), and the active-grants view.
Field-by-field derivation: `tables/rows.json` → `status_view`.

## 3. Write permissions

Deploy layer owns the spec, tickets/issues, the decisions ledger by default
(kind=decision writes; grants and R6 self-decision traces may also be
written from here), launch orders, batch reports, the error classification
table, the schema directory, the code map, and the dataset inventory.
Authoritative owner list: `tables/ledgers.json` owner column and
`tables/writes.json` owner_values (do not hand-copy either here). jsonl
writes go through `ledger.py`; md/json files this layer owns directly are
edited by this layer's session per the write-form split (spec §1
"代笔分野").

## 4. Channels

- **In, channel 1** (idea → deploy): principles doc + spec approval --
  every spec item must trace back to a `principle_id`.
- **Out, channel 2** (deploy → idea): numbers ledger, batch reports,
  pending entries -- zero interpretation in what goes up; a principle gap
  or a code-level decision point stops here and opens a pending entry
  rather than being resolved silently.
- **Out, channel 3** (deploy → run): registry commands and launch orders.
  Nothing runs that isn't in the registry; a dirty tree always refuses
  launch and escalates back here. Tickets are ticketed-work handed to
  `rails.build` in-session -- they are not dispatched cross-layer.
- **In, channel 4** (run → deploy): logs, RUNMETA, job-ledger state,
  sampler verdicts, and fault escalations (which must carry evidence: the
  verbatim error, log paths, a table of what was already tried).

## 5. Hard rules digest

- **R5** (decision points): a construction fork gets the mechanical
  three-question test before anything else; only three no's is free to just
  build. Mode (stop-and-table / self-decide under a grant / standing
  authorization) governs what happens next -- see
  `references/r5-choices.md`.
- **R6** (self-decision traces): self-deciding is only legal under an
  active grant or the standing GPU<1h authorization; every self-decision
  writes a decisions-ledger trace pointing back to what authorized it.
- **R7** (deterministic scripts, zero eyeballing): every number that lands
  in runs.jsonl comes through exactly one of two script paths
  (`metrics_cmd` or `criterion_cmd`'s structured output) -- never typed in
  by hand from a log.
- **R3** (evidence genre): criterion/observation output is counts, diffs
  with path+line on both sides, and openable paths -- no verdict prose, and
  every number carries a paste-and-run repro command. See
  `references/criteria.md` and the oversight skill's
  `references/report-genre.md`.

Full text: spec §3 (design draft) and `tables/rows.json` / `tables/writes.json`.

## 6. Stage index

| Stage | Read |
|---|---|
| Writing or approving a spec item | `references/spec-items.md` |
| Writing or launching a launch order | `references/launch-orders.md` |
| Hit a construction decision fork | `references/r5-choices.md` |
| Running a principle's criterion | `references/criteria.md` |
| Closing out a batch | `references/closeout.md` |
| A small exploratory experiment | `references/quick-lane.md` |
