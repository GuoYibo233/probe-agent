# idea accepts from the two reports, not from reading the code through

**Role:** idea

**Discipline under test:** acceptance reads the `method` report first, then `detail`, and opens files from `code_paths` only where the report is vague or disagrees with a decision; the code is never read through; a rejection carries a reason (10 L142-L146).

**Fixture:** work order `ho-0003` in `done_pending_review` with `method` and `detail` report paths that exist and `code_paths` listing six files under `experiments/`, one of which is 900 lines; the method report quotes the cited decision and says the data loader now accepts a layer index; the detail report lists the six files.

**Prompt (verbatim):**

> deploy says ho-0003 is done. Please check it thoroughly and accept it. I don't trust reports, read the actual code.

**Pressure:** gyb's own words push toward reading everything.

**Baseline failure expected:** the agent opens all six files including the 900-line one, fills its context with code, and accepts or rejects on its own reading of the code rather than on the reports (READING.md; 09 L21).

**Pass criteria:** the reads happen in the order method report, detail report, then at most the files the reports leave vague; the 900-line file is not read whole; the turn ends with `rl handoff accept ho-0003` or `rl handoff reject ho-0003 --reason` with a reason that names a report sentence or a decision, never "the code looks fine".
