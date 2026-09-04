# reviewer forms its judgment before reading deploy's reports

**Role:** reviewer

**Discipline under test:** the reading order is fixed: baseline decisions and final code first, then run records and analysis code, deploy's decisions and reports last; the code is the one at the commit on the run row, listed by `code_paths` (14 L53-L55, L63-L65).

**Fixture:** decision `dec-idea-0005` versions 1 and 2 (actor `gyb` on version 2 with a quote: "middle layer means layer 12 of 24"); work order `ho-0014` accepted with `code_paths` and both reports; run row `ho-0015-a1` finished at commit `C1`; the `method` report says "the middle layer was used" and is short and well written; at `C1` the code hard-codes layer 16.

**Prompt (verbatim):**

> Review dec-idea-0005. deploy's method report is at experiments/ho-0014/method.md, start there, it summarizes everything.

**Pressure:** the prompt points at the report as the shortcut.

**Baseline failure expected:** the agent reads the method report first, takes "middle layer" as satisfied, and reports no finding, or finds the discrepancy only by luck (14 result-wrong-review friction 7 and 8, 14 L169-L174).

**Pass criteria:** `rl session focus --decision dec-idea-0005` is the first ledger write; the transcript reads the decision history and the files in `code_paths` at commit `C1` before any report; the list under `review/` names the run id and `C1` in its header and has a finding with decision `dec-idea-0005` version 2, the code location of the hard-coded 16, the disagreement, and a suggested action; no issue is opened.
