# 06 the gpu-run skill reads the record

Status: resolved
Blocked by: 01, 02, 03, 04, 05
Spec: .scratch/card-record-and-remaining-time/spec.md (section "The skill")

## What to do

No Python. The files you may touch:

```
.claude/skills/gpu-run/SKILL.md                         steps 1, 2, 5, 6
.claude/skills/gpu-run/references/card_performance.md   one new first paragraph
```

- Step 1: the agent reads the `## Runs by card type` table of `jobs/RESULTS.md` first, then
  the hand table for runs before the automatic record; a memory failure in either for the
  same task on a card type rules that card type out (advice, not a launcher refusal).
- Step 2: the speed comes from that table's median speed for the same task and card model.
- Step 5: the remaining time is the `left=` field of `run.py ls`.
- Step 6: item 3 (writing a row by hand) is removed.
- `card_performance.md` opens with one paragraph: the table is the frozen record of runs
  before the automatic card record began (name the date ticket 01 merged), and new runs are
  recorded in `jobs/RESULTS.md`.

## Acceptance

- Every command and field the skill names exists (`run.py --help`, a rendered
  `jobs/RESULTS.md`).
- The skill stays short: no explanation of how the registry builds the record.

## Comments

- 2026-10-02: done by the main conversation directly (two text files, no Python), after tickets 01 to 05 merged. Step 1 reads the `## Runs by card type` table first and says the launcher does not enforce the choice; step 2 takes the median speed from it (a debug row's speed does not transfer to full sizes); step 5 names the `left=` field; step 6's hand-written row is gone. `card_performance.md` opens with the frozen-history paragraph, and its "Maintaining the table" paragraph is removed. Covered by the final review.
