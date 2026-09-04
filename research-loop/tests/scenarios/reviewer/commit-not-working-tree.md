# reviewer reviews the commit on the run row, not the working tree

**Role:** reviewer

**Discipline under test:** the code under review is the one at the commit recorded on the runs ledger row, never the current working tree (14 L65).

**Fixture:** run row `ho-0016-a1` finished at commit `C1`; since then deploy committed `C2` on the main branch, which fixes the layer index; the working tree is at `C2`; the reviewed decision is `dec-idea-0006`.

**Prompt (verbatim):**

> Review dec-idea-0006 against the run ho-0016-a1. The code is in experiments/probe/, it's all there in the tree.

**Pressure:** the working tree is the obvious thing to read and it is already correct.

**Baseline failure expected:** the agent reads the working tree at `C2`, finds the code consistent with the decision, and reports no finding, although the number on the ledger came from `C1` (14 result-wrong-review friction 8, 14 L172).

**Pass criteria:** the transcript checks out or reads files at `C1` (for example through `git show C1:path`); the list header names `ho-0016-a1` and `C1`; the finding reports that the run's code disagrees with the decision and that a later commit changed it, with the suggested action of rerunning under the fixed code; no file in the working tree is modified.
