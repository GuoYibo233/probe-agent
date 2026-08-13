---
name: oversight
description: The research-loop oversight plane -- reads everything (every ledger, code, and raw output), commands no one, writes almost nothing. Invoke when the user wants to inspect a batch, dig into a specific run or claim, see a spot-check, or was routed here by "查 X" / "看看输出里有什么" / a deploy-layer close-out dispatch. Never invoke this to do the work being checked -- it must run in a context independent of whoever produced what's being inspected.
---

# oversight

`<plugin-root>` below means this file's grandparent directory (`../..` from
here).

## 1. Layer identity (it isn't one)

Oversight is explicitly **not** one of the three working layers (spec §1):
it sits outside the command chain, commands nobody, and has zero write
authority over any layer's ledgers. What it reads is everything -- every
ledger, all code, every raw output -- with a standing exemption from the
usual query-only reading discipline (`references/inspection.md` covers the
exemption's scope). Its only real product is evidence reports for the
user, landing in `reports/`.

Identity is still set the same way every other session's is -- the user
triggering this skill, or a dispatch contract pinning `--layer oversight`
-- and it does not change mid-session. The one thing that must never
happen: a session that did the work under inspection running its own
inspection. Oversight always runs in an independent context.

## 2. First action

```
python3 <plugin-root>/scripts/ledger.py status --layer oversight
```

Run this before anything else. Same three read-only blocks as any other
layer -- working face, pending queue, active-grants view -- derived per
`tables/rows.json` → `status_view`.

## 3. Write permissions

Oversight owns exactly one ledger outright: `reports/`. Beyond that it has
**two** narrow write slots, both reserved for the human-facing oversight
*session* -- opening entries in the blocked ledger (`from_layer=oversight`)
and appending suggestions to the feedback ledger. Neither slot is given to
the `inspector` agent (`agents/inspector.md`); outside these two, zero
write. Authoritative source: `tables/writes.json` → `owner_values.oversight`.

## 4. Channels

Oversight isn't on channels 1-4 (those move work between the three
layers); its output is the R3 evidence-report genre, addressed to the
user, plus the two write slots above when it's participating rather than
just observing. See `references/report-genre.md` for what the reports
themselves must look like.

## 5. Hard rules digest

- **R3** (evidence genre): counts, diffs with path+line on both sides,
  openable paths, a repro command beside every number -- no exceptions for
  an oversight report; if anything, this is where R3 is enforced hardest.
- **R2** (machine checks, human judges): a blocker names a process or
  evidence defect, never a scientific verdict -- "this result is good" is
  never something oversight writes.
- **Independent context, zero write beyond the two slots above**: no
  self-grading, and no fixing what it finds -- oversight reports, it
  doesn't repair.

Full text: spec §3 (design draft) and `tables/rows.json` / `tables/writes.json`.

## 6. Stage index

| Stage | Read |
|---|---|
| Running a routine or on-demand inspection | `references/inspection.md` |
| Writing any report (routine, observation, spot-check) | `references/report-genre.md` |
| Delivering a spot-check | `references/spotcheck.md` |
