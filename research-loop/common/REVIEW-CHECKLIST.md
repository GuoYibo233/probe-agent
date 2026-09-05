# Review checklist: the judgment questions reviewer checks one subagent per question

<!-- Sources: 09 L17 (file name and purpose, ruled 2026-08-18), 05 L221 (the two example questions and the "list only, gyb opens issues" ruling of 2026-08-17), 14 L25-L31 (baseline), 14 L37-L45 (the three things under review), 14 L53-L55 (reading order), 14 L61-L69 (which commit, code_paths, method report as anchor), 14 L79-L89 (five columns of a finding), 06 L29 and 09 L44 (rule-08 afterwards check). Items not covered by one of those lines carry PENDING(part 09 L23): gyb walks this file line by line before it is final. -->

`rl doctor` runs only the checks a script can decide. This file holds the checks that need reading and judgment. reviewer takes one question at a time, starts one sonnet subagent per question, and writes what comes back into the list under `review/`. Nothing here opens an issue; gyb reads the list and opens issues with gyb's own permissions.

## Baseline
The baseline is the set of decision rows whose actor is `gyb` or `idea`, wherever the row lives. Literature is not a baseline. What gyb meant but did not say is not a baseline. deploy's own decisions are under review, not a baseline.

## A. The code against the decisions
- A1. Does the method report quote every decision id and version the work order cites, and does the code do what each of those decisions says? (05 L221, first example.)
- A2. Is the code under review the one at the commit recorded on the runs ledger row, and does it match the files listed in `code_paths` on the work order? (14 L63-L65.)
- A3. Which choices in the code affect results and have no decision row anywhere? Report each in column 5 of the list. (14 L89.)
- A4. Are host files changed outside `experiments/` listed in the detail report, with a deploy decision whose source points at that file? (14 L67.)

## B. The run against the order
- B1. Does the run's actual config match the config on the launch-order attempt that produced it? (05 L221, second example.)
- B2. Were run id, track and command copied from the launch order rather than composed by run? (principle-09.)
- B3. Does every failed attempt have an issue with its stage, and is the run row cited as evidence the latest attempt with exit status ok? (principle-10; 12 L98-L107.)

## C. The analysis code against what gyb asked
- C1. Does every number and figure in the notebook map to an `approved` evaluation at the version in force when it was computed? (rule-05.)
- C2. Did every comparison, aggregation or figure across runs go through an analysis order? (rule-04.)
- C3. Do the figure's grouping and axes match the approved figure evaluation? PENDING(part 09 L23)
- C4. reviewer reads the analysis code and the notebook; the statistics themselves are analysis's work and are not re-done here. (14 L45.)

## D. Traces the machine cannot judge
- D1. Do rows written with `--as-gyb` carry a quote that reads as gyb's own words from that moment, not a paraphrase? (principle-01.)
- D2. Do the writes in git history match the sessions ledger: every commit inside a role directory by a session that held that role at that time? (rule-08.) The runs row joins a commit to the run session that launched it; no field joins the commit to the session that wrote it, so this check has no ledger-side anchor: PENDING(issue 51).
- D3. Was every issue that a fix answered replied to and closed? (rule-09.)

## Reading order for every question
First the decisions with actor `gyb` or `idea` and the final code, to form a judgment. Then the run records and the analysis code. Last deploy's decisions and the two deploy reports, for cross-checking only. (14 L53-L55.)

## Shape of a finding
One list file per review, named `review/<date>-<decision id>.md`, with a header naming the run id and the commit under review. Each finding has five columns: decision id and version; location in code or records; where they disagree; suggested action; choices made in code that no decision covers. (14 L75-L87.)
