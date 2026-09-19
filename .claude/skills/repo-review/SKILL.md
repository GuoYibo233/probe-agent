---
name: repo-review
description: >-
  The two-day review: an agent reads the tree against `README.md`'s seven principles
  and writes tasks. It runs `run.py selfcheck` first and stops if that is not green,
  reads `README.md`, then the file under review, then the contracts section that covers
  that file, and writes one ticket per finding into
  `.scratch/review/issues/` in the issue-tracker format — it edits no code and no file
  under `notes/`. Invoke whenever Dungeon♂Master says "review the repo" or a periodic
  tree review is due. Chinese triggers: "审查仓库" / "复盘整棵树" / "两天复盘" / "查一遍仓库".
version: 1.0.0
---

# repo-review — the two-day review

The tree's own line for this file: **"the two-day review: an agent reads the tree
against the six principles and writes tasks."** That count is stale — `README.md`
opens "Seven principles hold the tree together" — and stays quoted as written, because
the fixed tree is never reworded. This file reviews against the **seven** principles
`README.md` section 1 states.

1. **What it reviews.** The tree against the owner's principles as `README.md` states
   them: one experiment is one setting; outputs keyed by setting and version; the layer
   boundaries `data/ models/ agent/ train/ eval/ jobs/`; `--debug` runs any setting
   tiny; no near-duplicate and no framework; `README.md` for the next reader; everything
   on disk and `eval/` CPU-only.

2. **What it reads, in order.** `README.md`, then the file under review, then the
   section of `notes/plans/2026-09-17-contracts.md` that covers that file: the part or
   section whose heading carries the file's own path where there is one — Part 4 for
   `data/environments/__init__.py`, Part 5 for `experimental_settings/schema.py`, Part 8
   for `jobs/registry.py`, the format sections of Part 1 and the two service sections of
   Part 7 — otherwise the part that covers the mechanism the file implements: Part 1 for
   an on-disk format, Part 2 for a stage program, Part 3 for anything that computes a
   key or a run directory, Part 6 for the model table and the constants. Contracts 0.2
   is where `README.md` section 2's annotation lines are reproduced from, and it still
   spells the pre-2026-09-18 tree (`eval/methods/`, the old `agent/` names), so it adds
   nothing to the annotation lines already read in `README.md` and is not the section to
   read here. It runs `run.py selfcheck` first and stops if that is not green — a review
   over a tree that fails its own checks reports noise.

3. **What it writes.** One ticket per finding into `.scratch/review/issues/`, in the
   issue-tracker format of `notes/docs/agents/issue-tracker.md`, with the Status line
   taking one of the five labels of `notes/docs/agents/triage-labels.md`. It edits no
   code and no file under `notes/`.

4. **What it never does.** Start a GPU process — it returns `BLOCKED` with the
   ready-to-run command; edit `experimental_settings/*.yaml` or `models/table.yaml`; or
   propose a file the tree's Part 1 does not name — as `README.md` section 2 currently
   spells that tree, after the 2026-09-18 fold of the three per-method eval files into
   `eval/utils/probe_eval.py` and the `agent/` renames, which is the list
   `run.py selfcheck` check 1 enforces.
