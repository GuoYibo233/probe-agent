# T04 report: probe-pipeline skill write-back

Ticket: `.scratch/kvshare-train/issues/04-docs-writeback.md`
Branch: `ticket/2026-08-28-wave4/T04`, base `d6aa99d0ef34bfca903bf02b7bde2620531d87bc`,
head see the commit list below (worktree `/home/y-guo/reproduce/new1-wt/2026-08-28-wave4-T04`,
already deleted per protocol, branch kept).

This ticket is a pure documentation write-back, changing only the five files, out of the six the ticket
names, that actually needed changes (`SKILL.md` was verified to need no changes, see below).
No GPU or code changes occurred; the `run.py` registry, `TIMELINE.md`, and any `.py` file were not touched.

## 1 What was done (checked item by item against the ticket's requirements)

### Start-of-work gate (the smoke ruling in Comments)

The ticket is blocked by 02 and 03, and requires waiting for the main session to give a GPU smoke ruling
in this ticket's Comments before starting work.
The Comment read is already at the end of the ticket file, and settles the values: for all three cells,
`--max-len` defaults to 8192 with no fallback; the new trainer's
`--tok-budget` defaults to 16384 (`--eval-tok-budget` defaults to 32768); `expandable_segments:True`
was not adopted; ctool defaults to `--bs 2 --accum 4`, `--align-tol` defaults to 3e-4. Before starting work,
`git log --oneline` and `git show --stat` were used to check: commit `8fa95dc` (ctool default changed to
`--bs 2 --accum 4`) and `9c3efb1` (`ALIGN_TOL` changed to 3e-4) have already landed in `train_causal_tool.py`,
decision 15 and decision 20 in `.scratch/kvshare-train/decisions.md` match the Comment's numbers,
and the run_id `ks828b06_gptoss_ctool_h100mem_bs2` can be found in `ops/runs.jsonl`. Only after confirming
that all three sources (the Comment, decisions.md, and the actual code defaults) corroborate each other did
work on the documents begin.

### 1. `MAP.md` (the training table at line 88)

- ctool row: the program column is unchanged (still `train_causal_tool.py`; ticket 02 only changed the
  inside of this script, the script itself was not swapped); the key-settings column was filled in with
  the wording given in the ticket 02 report (cap of 8192, whole event dropped if over; the
  `share_data.read_position` read-position rule; 8 events per update), and the `--bs`/`--accum` numbers
  were changed from the `--bs 4 --accum 2` written in the T02 report to the actually decided
  `--bs 2 --accum 4` (see item 1 under "self-check findings and open questions" below; the smoke ruling
  had not come out yet when the T02 report was written); along the way, the "reference value
  `--align-tol 3e-4`" named in ticket 02 was changed to "default 3e-4".
- The cgen and cparam rows: the program column was changed to `pipeline/train/train_causal_share.py
  --mode cgen` / `--mode cparam`; the key-settings column was replaced with the wording given in the
  ticket 03 report (one forward pass shares the prefix per event; events over the 8192 cap are dropped
  whole; 8 events per update; 1 epoch, val_ce evaluated every quarter epoch; `--tok-budget` controls
  VRAM), the two rows carry the same text (the ticket's original text says "cparam same as above").
- A new row `(reference)` was added: the two old row-by-row scripts, the "what it learns" column was filled
  with the sentence given in the ticket's original text, "row-by-row reference implementation, used only
  for alignment checks and comparison, its output does not enter the matrix", the "key settings and
  pitfalls" column added a pointer to `train-cgen-rows`/`train-cparam-rows` and extending.md §5 #26.
- A new row `(shared)` was added: `share_data.py`, the wording copied verbatim from the paragraph given
  in the ticket 01 report.

### 2. `.claude/skills/probe-pipeline/references/stage-commands.md`

- §3 Training commands and parameter table: a new code block was added, "the real commands for
  `train_causal_share.py`". The CPU smoke command was copied as-is from the ticket 03 report (the one
  actually run and tested), the GPU commands were checked by running `python3 run.py show train-cgen` /
  `train-cparam` live (see "How this was verified"), the speed/VRAM tier commands were copied from the
  Comment and the spec section 10 command in the ticket 03 report.
- Six new categories of rows were added to the parameter table: `--mode` (required), `--tok-budget`
  (default 16384, with ips/VRAM justification), `--events-per-mb` (default 4), `--eval-per-epoch`
  (default 4), `--accum` (the cgen/cparam meaning and the ctool meaning written separately, the ctool
  half carries the evidence chain for decision 15), and `--align-tol`/`--align-only`/`--align-events`
  (distinguishing the ctool criterion from the cgen/cparam criterion).
- Line 213 (the original file's line number; the current file is offset by the inserted lines) the
  `--smoke` row: added the cgen/cparam active trainer's new convention of 40 training events / 16
  evaluation events, sampled in ascending order of token count, and noted that the old and new numbers
  are not comparable.
- §3.2: added a paragraph on the batch prefix `ks828` (in the shape `ks828b06`/`ks828l17`), and stated
  that the `np821` prefix must not be used any more for runs under the new convention.
- §3.1 the measured-VRAM table: added two rows of ks828/H100 measurements under the new convention
  (ctool `56,859 MiB`, cgen `60.59 GB allocated`), and added a sentence noting that these two rows are on
  a different axis from the four np821/48G rows above and cannot be compared side by side directly.
- §7 Interface pitfalls: three items were added: `--mode` is required, `train-cgen-rows`/
  `train-cparam-rows` are reference only, not the active ones, and an individual event that exceeds the
  `--tok-budget` becomes its own block.
- Along the way, the ctool `--align-tol` row was also changed (the default changed from 1e-4 to 3e-4,
  with decision 20 and the measured numbers), as was the summary prose sentence "everything else uses the
  default" (the old and new conventions for the three causal cells listed separately). The ticket's
  original text did not name these two spots by exact line number, but both fall within the scope of
  "training commands and parameter table" and directly contradict the new content; not changing them
  would leave the document self-contradictory, so they were handled as "root-cause fixes".

### 3. `.claude/skills/probe-pipeline/references/invariants.md`

First ran the grep the ticket specified, `grep -n "4096\|accum 8\|32 events\|truncation\|epochs 3\|bs 4"`,
which hit 5 lines (`causal hyperparameters`, `left truncation`, `cgen target construction`, `smoke scale`, plus two unrelated
annotate-side rows, MAX_BOUNDS / result truncation; judged by meaning that the latter two were not
changed, reasoning in self-check item 2 below). Changed line by line to the new convention:

- `causal hyperparameters`: split into two layers, "8 events per update across the board" (unchanged for all three
  cells) and "the bs/accum split and the epoch count now differ by cell": ctool `--bs 2 --accum 4`/
  epochs 3, cgen/cparam `--events-per-mb 4 --accum 2`/epochs 1; with decision 15 and the run_id from
  `ops/runs.jsonl` as the source; kept a sentence, "the np821 batch used bs 4 events / accum 8
  (32 events per update) / epochs 3".
- A new row `cap --max-len (unified across the three cells)` was added: default 8192 with no fallback, whole event dropped
  rather than truncated, with `pipeline/runs/smoke/ks828b06_*` and `ops/runs.jsonl` as the source, keeping
  np821's row-by-row left truncation at `max_length=4096` as a historical comparison. This is the only
  item, among the ticket's requirement to "find everything (at least the cap row...)", that did not exist
  before and needed a new row opened for it: in the old document, the concept of `--max-len` was only
  implicit in the `cgen target construction` row, it did not have its own row.
- `cgen target construction`: rewrote "first tokenize the target without truncation... then left-truncate the input
  by max_length=4096-L_t" into "the target-string construction is unchanged; the input-side
  left-truncation rule, as of 2026-08-28, only still applies inside the frozen old row-by-row scripts,
  the active trainer does not left-truncate", keeping np821's old formula as a historical comparison.
- `smoke scale`: split into three parts, mtool/mext (stopped running, random 500/200), ctool (random
  200/80 events, unchanged), and the cgen/cparam active trainer (40/16 events, ascending by token count,
  not dependent on SEED), and pointed out that the old-generation and new-generation smoke numbers are
  not comparable.
- Added a sentence to the `left truncation` row, "does not apply to the cgen/cparam active trainer", pointing to
  the new "cap" row.

### 4. `.claude/skills/probe-pipeline/references/extending.md`

- Added three rows to the §5 silent-failure-point master table (#25/#26/#27, numbering continuing from
  #24, **no new gate number was added**, #25/#26/#27 are extending.md's own silent-point numbering, a
  separate system from `gates.md`'s G numbering):
  - #25: ctool/`eval_tool.py`'s read-position loop before 2026-08-28, its trigger condition, the 6.3%
    symptom, and the sentence the ticket emphasized, "must not be written as if the live-run misalignment
    is already fixed" (calling out the live-run-side tokenization-boundary pitfall separately, noting it
    was not resolved this round, pointing to the last paragraph of spec 11.3).
  - #26: `train-cgen-rows`/`train-cparam-rows` getting mixed into the matrix with no way to tell them
    apart.
  - #27: `share_data.py`'s top-level import of the old script causes a `SystemExit` during the
    `eval_tool`/`eval_mbert_call` import step under mbert-env, the symptom and the root-cause fix
    (already implemented by ticket 01).
- Added a paragraph after the "new cell vs. new training-method axis" criterion paragraph at the start of
  §3, stating that "swapping the implementation" also does not go through the §3.1 mandatory-change
  checklist, with `train_causal_share.py` as the precedent, the criterion is still "did the
  cell/data/evaluation change".
- Added a sentence at the end of the run_id row in §3.4: the new-convention batch prefix is `ks828`, the
  `np821` prefix must not be used any more for the new convention.

### 5. `.claude/skills/probe-pipeline/SKILL.md`

First, as the ticket instructed, ran `grep -n callgen .claude/skills/probe-pipeline/SKILL.md`, zero hits;
then ran `grep -n 'train_causal\|\.py'` (excluding script names such as `run.py`/`build.py`/
`param_label.py` that are unrelated to this change), confirming that the whole `SKILL.md` has never
hardcoded training-script file names like `train_causal_callgen.py` or `train_causal_param.py`; line 44
only mentions the cell names `ctool cgen cparam`, the actual script names are all looked up live via
`python3 run.py list`/`show`. **This file needed no changes this round**; ticket item 5 itself is "grep
first to find them"; finding zero hits means there is no location that needs changing, not an oversight.

### 6. `.claude/skills/probe-pipeline/references/gates.md`

Only changed the explanatory text of the G14 row (per-cell smoke): changed the cgen/cparam active
trainer's smoke convention from "randomly draw 500/200 instances" to "take 40/16 events in ascending
order of token count", and split the "loss going down does not tell you anything" example arithmetic into
two sets, ctool (200÷8=25 gstep) and cgen/cparam (40÷8=5 gstep), because the two sides now have different
bs/accum splits. **No new gate number was added, no gate semantics were changed** (the criterion is still
`train_log.jsonl` has start/done, `best/` can be written and read, ctool additionally includes
ALIGN_CHECK PASS). Rechecked with `grep -n "4096\|accum 8\|32 events\|truncation\|epochs 3\|bs 4"`, the
historical-case paragraphs still remaining in `gates.md` (§3.1 through §3.10) were left as they are:
those are incident records for specific batches, the numbers belong to historical fact, not "explanation
of the current convention", and are outside the scope of change the ticket asked for.

## 2 How this was verified

```
grep -n '^#' .claude/skills/probe-pipeline/references/*.md
```
For each file, the sequence of section numbers/gate numbers (`## N.`, `### N.M`, `| G14 | ...`) is
complete, with no skipped or duplicate numbers, and extending.md's #25/#26/#27 follow directly after the
existing #24, matching the acceptance requirement that "the section numbers and gate numbers referenced
all check out".

```
python3 run.py selfcheck
```
`selfcheck: 76 tasks / 4 recipes / 3 presets, 16 missing`: all 16 missing items are because the new worktree
does not have per-machine-installed interpreters such as `envs/*/venv`, `cprobe-env`, `mbert-env` (a
freshly created worktree does not bring along these gitignored items), unrelated to this ticket's
documentation changes; `git status` confirmed only the five documentation files changed, zero changes to
`run.py` or any `.py` file.

```
python3 run.py show train-cgen
python3 run.py show train-cparam
```
Ran these two commands before writing the "real commands" section of stage-commands.md, confirming that
the command shape is `.../cprobe-env/bin/python .../pipeline/train/train_causal_share.py --mode cgen
'<args...>'` (cparam has the same shape with `--mode cparam` swapped in), matching what is written in the
document.

```
grep -n "4096\|accum 8\|32 events\|truncation\|epochs 3\|bs 4" .claude/skills/probe-pipeline/references/invariants.md
grep -n "4096\|accum 8\|32 events\|truncation\|epochs 3\|bs 4" .claude/skills/probe-pipeline/references/gates.md
```
Reran after finishing the changes; every remaining hit in `invariants.md` was checked to be either a
"retained np821 historical value" or an "unrelated annotate-side constant"; the one remaining hit in
`gates.md` is the word "truncation" inside the sentence "not truncated in original order", unrelated to
the convention numbers (a false positive).

```
git diff --stat
```
```
 .../skills/probe-pipeline/references/extending.md  |  7 +++-
 .claude/skills/probe-pipeline/references/gates.md  |  2 +-
 .../skills/probe-pipeline/references/invariants.md |  9 +++--
 .../probe-pipeline/references/stage-commands.md    | 45 +++++++++++++++++++---
 MAP.md                                             |  8 ++--
 5 files changed, 57 insertions(+), 14 deletions(-)
```
Reread the full diff for each file; for the tables, used `awk -F'|'` to count the pipe characters on each
row, and the new rows have the same pipe count as the rest of the original table (MAP.md 5 pipes, the two
stage-commands tables 6/4 pipes respectively, invariants 5 pipes, the extending.md §5 table 5 pipes),
ruling out the problem of dropping characters while hand-editing a markdown table.

No unit tests were written: this ticket only changes markdown documents, there is no code change, and
there is no natural "test seam"; the ticket's own acceptance section is also entirely grep/manual checks,
and does not name any `.py` test file.

## 3 Commit list

- `9601eb0` T04: probe-pipeline skill write-back (MAP.md training table + four references documents,
  implemented item by item per ticket 04; `SKILL.md` verified via grep to need no changes)

(The commit sha is subject to the actual `git log`; see the structured field head below.)

## 4 Self-check findings and open questions

1. **ctool's `--bs`/`--accum` numbers: the ticket body writes `--bs 4 --accum 2` in two places, but the
   actual decision and the code are `--bs 2 --accum 4`**. Ticket item 2 ("change ctool's parameter table
   default values (fix `--max-len`, `--accum 2`...") and item 3 ("ctool is bs 4 x accum 2") both write
   this combination, but the Comment at the end of the ticket clearly states "ctool defaults to
   `--bs 2 --accum 4`", and decision 15/21 in `.scratch/kvshare-train/decisions.md` and the `argparse`
   default values in `train_causal_tool.py` (`--bs` defaults to 2, `--accum` defaults to 4, the help text
   reads "defaults to 4, combines with --bs 2 to form 8 events per update") both match the Comment;
   commit `8fa95dc`'s description reads "decision 15's fallback: 8192 x bs 4 OOMs on the first training
   batch on H100, bs 2 peaks at 56,859 MiB". Judged that the two spots of "bs 4 x accum 2" in the ticket
   body are leftover draft text from before the smoke ruling came out, and were not updated along with
   the Comment; ticket item 3 itself also states "ctool's `--bs/--accum` follow the settled values in the
   Comment", which hands ruling authority over to the Comment. The whole document was written
   consistently as `--bs 2 --accum 4`; the three independent sources (the Comment, decisions.md, and the
   actual code) corroborate each other, leaving no doubt, so this did not stop to ask NEEDS_CONTEXT, but
   this judgment is recorded here for review.
2. **Among the grep hits in `invariants.md`, the two rows `MAX_BOUNDS` (line 24) and `result
   truncation RESULT_CAP` (line 26) were not changed**: they belong to the §2 data-side convention (the cap on cut
   points during the annotate stage and the truncation length of environment returns), a completely
   separate matter from this trainer implementation swap; they were only hit by grep because they
   literally contain the two characters that mean "truncation," judged an unrelated false positive, and
   left as they are.
3. **The trigger-condition description of §5 silent-failure-point table #25 is more specific than the
   spec's original text**: spec 11.3 only writes "6.3% of cut points read one word before the
   sentence-ending punctuation", the trigger condition given in ticket item 4 is "the token before the
   cut point crosses over the cut point and the cut point is followed by whitespace"; I merged the two
   into one row, using the ticket's wording for the trigger condition and the spec's wording for the
   symptom number, without separately reading the pre-change historical version of `train_causal_tool.py`
   line by line to check whether this mechanism description of the trigger condition corresponds exactly
   to the bug at the time (ticket 02 has already removed this loop, the old code can only be dug up from
   git log, and this was not done this round). If this description diverges from the historical
   implementation details, it should be corrected in favor of the original text of spec 11.3 and ticket
   item 4.
4. **The semantics of the two new rows added in stage-commands.md §3.1 are slightly forced**: the
   original table's semantics are "the peak value of each of the three cells, ctool/cgen/cparam, under
   the same batch shape", but the two rows I added only have data for a single cell each (one row fills
   only the ctool column, one row fills only the cgen column, the cparam column and the other cell's
   column are both filled with "—"), which fits the literal instruction in the ticket's Comment, "add a
   row '...' and '...'", into a table structure that does not fully match; a sentence was already added
   below the table, "the last two rows are ks828 new-convention measurements on H100, on a different axis
   from the four np821/48G rows above, not directly comparable side by side"; judged that handling it
   this way is closer to the ticket's literal requirement of "add a row to the table" than opening a
   separate standalone subsection, but structurally it is indeed less tidy than the original table.

## 5 Fix round 1 (review finding F1)

Review finding F1 (important): acceptance item 4, "the report lists the file and line number of every
change", was not fulfilled item by item. Section 1 above describes changes by paragraph name/table row
name, and most give no line number for the changed file. The finding itself checked the actual content of
the six files against the ticket, the spec, the T01/T02/T03 reports, and the argparse default values of
`train_causal_tool.py`/`train_causal_share.py` word for word, and judged "the content is accurate, the
gap is only that no line numbers were given".

### 5.1 How it was handled

Only added line numbers, changed no content in any of the six files. The finding itself had already
confirmed the content was correct, and the ticket's hard rule "no expanding the scope into a rewrite"
also does not allow using this fix as an excuse to rewrite the document body. Before starting work,
checked out the T04 branch (tip `39da84e`) into a separate git worktree, and for each file reran
`grep -n` to locate the actual line number, in **the current file**, of every change described in
section 1 (`git diff -U0 d6aa99d0..39da84e -- <file>` first located the rough range of the hunk, then
`grep -n` pinned down the exact line number, the two corroborating each other); the table below is the
result of this check:

**`MAP.md` (training table)**

| Line | Change |
|---|---|
| 92 | ctool row: key-settings column rewritten (cap `--max-len` 8192, `share_data.read_position` read-position rule, `--bs 2 --accum 4`, `--align-tol` default 3e-4) |
| 93 | cgen row: program column changed to `train_causal_share.py --mode cgen`; key-settings column replaced with new wording |
| 94 | cparam row: program column changed to `--mode cparam`; key-settings column same wording as cgen |
| 95 | New row `(reference)`: the two old row-by-row scripts |
| 98 | New row `(shared)`: `share_data.py` |

**`.claude/skills/probe-pipeline/references/stage-commands.md`**

| Line | Change |
|---|---|
| 210 | `--align-tol` row: ctool default changed to 3e-4, added the cgen/cparam criterion |
| 211 | `--align-only` row: scope changed from "ctool only" to "both ctool and cgen/cparam" |
| 212 | New row `--align-events` |
| 213 | New row `--mode` (required) |
| 214 | New row `--tok-budget` (default 16384) |
| 215 | New row `--events-per-mb` |
| 216 | New row `--eval-per-epoch` |
| 217 | New row `--accum` (ctool and cgen/cparam meanings listed side by side) |
| 219 | `--smoke` row: split into three parts, mtool/mext+old scripts / ctool / cgen-cparam active (40/16, sampled in ascending order) |
| 228 | The "everything else uses the default" paragraph: rewritten hyperparameters for the new convention across the three causal cells, keeping np821 historical values |
| 239 | New subsection heading, "the real commands for `train_causal_share.py`" |
| 241–259 | New code block: CPU smoke command, `run.py show train-cgen`/`train-cparam`, speed/VRAM-tier commands |
| 261 | `### 3.1 Measured-VRAM Table` subsection heading (pre-existing, unchanged; two new rows added below, see 271–272) |
| 271 | §3.1 table new row: ctool 0.6B full-parameter 8192×`--bs 2` measurement (56,859 MiB) |
| 272 | §3.1 table new row: cgen new trainer `--tok-budget 16384` measurement (60.59 GB allocated) |
| 274 | Explanatory sentence below the table rewritten, added "the last two rows are ks828 new convention... different axis, not directly comparable side by side" |
| 276 | `### 3.2 The Relationship Between LoRA Batches and Full-Parameter Batches` subsection heading (pre-existing, unchanged; new paragraph added below, see 280) |
| 280 | §3.2 new paragraph: batch prefix `ks828`, `np821` prefix must not be used any more for the new convention |
| 515 | §7 new entry: `--mode` is required for `train_causal_share.py` |
| 516 | §7 new entry: `train-cgen-rows`/`train-cparam-rows` are reference, not active |
| 517 | §7 new entry: an individual event exceeding `--tok-budget` becomes its own block |

**`.claude/skills/probe-pipeline/references/invariants.md`**

| Line | Change |
|---|---|
| 45 | `causal hyperparameters` row: split into two sets, ctool (`--bs 2 --accum 4`/epochs 3) and cgen/cparam (`--events-per-mb 4 --accum 2`/epochs 1), keeping the np821 historical-value sentence |
| 46 | `left truncation` row: added the sentence "does not apply to the cgen/cparam active trainer" |
| 47 | New row `cap --max-len (unified across the three cells)`: default 8192 with no fallback, whole event dropped rather than truncated |
| 48 | `cgen target construction` row: rewritten to "active does not left-truncate, the left-truncation rule only still applies in the frozen old scripts", keeping np821's old formula |
| 53 | `smoke scale` row: split into three parts, mtool/mext (random 500/200), ctool (random 200/80), cgen/cparam active (40/16, ascending by token count) |

**`.claude/skills/probe-pipeline/references/extending.md`**

| Line | Change |
|---|---|
| 123 | New paragraph: ""swapping the implementation" also does not go through §3.1", precedent `train_causal_share.py` |
| 167 | `run_id has no backbone-tier segment` row: appended at the end of the row, "the same applies to swapping the implementation, written into the batch prefix", added `ks828` |
| 291 | §5 new row #25: ctool/`eval_tool.py` read-position rule |
| 292 | §5 new row #26: `train-cgen-rows`/`train-cparam-rows` getting mixed into the matrix with no way to tell them apart |
| 293 | §5 new row #27: `share_data.py`'s top-level import of the old script blows up mbert-env |

**`.claude/skills/probe-pipeline/references/gates.md`**

| Line | Change |
|---|---|
| 23 | `G14` row: smoke-convention explanatory text rewritten into two conventions, ctool/cgen-cparam active; the arithmetic in the sentence `loss going down does not tell you anything` split into two tiers; no new gate number added, no gate semantics changed |

`.claude/skills/probe-pipeline/SKILL.md` was not changed this ticket (`grep -n callgen`/`grep -n
'train_causal\|\.py'` zero hits, ticket item 5 itself is "grep first to find them", zero hits means there
is no location that needs changing; this round's review keeps this conclusion, and did not re-run a new
search).

### 5.2 How this was verified

First checked out the T04 branch into a separate worktree to verify the real line numbers in the current
file (see the process above); after verifying, confirmed that the six ticket-named files **need no
content changes**: the finding itself had already verified the content was accurate, this round only
puts the line numbers into the report. To confirm this judgment had no gaps, reran the consistency checks
the original report used:

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave4-T04-fix1
git status --short
```
Output was empty: the worktree has zero changes against the T04 branch tip, confirming that "fixing F1
does not require changing any document content".

```
grep -n '^#' .claude/skills/probe-pipeline/references/*.md
```
Rechecked the section-number/gate-number sequence once more; `invariants.md`'s `## 6.`/`## 7.`, and
`gates.md`'s `## 1.` through `## 5.` (including `### 3.1`-`### 3.10`) are continuous with no skipped or
duplicate numbers, matching the original report's conclusion.

```
git diff -U0 d6aa99d0ef34bfca903bf02b7bde2620531d87bc..39da84e -- MAP.md \
  .claude/skills/probe-pipeline/references/stage-commands.md \
  .claude/skills/probe-pipeline/references/invariants.md \
  .claude/skills/probe-pipeline/references/extending.md \
  .claude/skills/probe-pipeline/references/gates.md
```
Read the hunk header (`@@ -a,b +c,d @@`) for each file to check the starting line number in the new file,
then used `grep -n` to pin down the exact line; the two methods gave matching line numbers (for example,
stage-commands.md's `@@ -232,0 +239,22 @@` and the line 239 given by `grep -n "real command"` confirm each
other); the line numbers in the two tables above were verified this way.

No unit tests or new code tests were written this round: the object of this fix is a completeness gap in
the report document itself, no `.py`/`.md` (the ticket's six files) content changes were produced, there
is no new code test seam; `run.py selfcheck` was not rerun this round, because no file in the worktree
changed relative to the T04 branch tip (`git status --short` already verified this), rerunning it would
only get exactly the same result as the original report.

### 5.3 Commit list

**No new commit was added this round**: fixing F1 only required adding line numbers to the report;
after this round's check, the content of the six ticket-named files was confirmed to need no changes, the
worktree has zero diff against the branch tip, there is nothing to commit. The branch
`ticket/2026-08-28-wave4/T04` still stops at `39da84e` (the commit of T04's original implementation). The
worktree `/home/y-guo/reproduce/new1-wt/2026-08-28-wave4-T04-fix1` has been deleted per protocol.

### 5.4 Self-check findings and open questions

- The branch tip's actual commit sha is `39da84e`, which does not match the `9601eb0` written in section
  3 of the original report: `9601eb0` is most likely a temporary local sha from before the original
  implementer had converged on a final commit (this sha no longer exists in the repository,
  `git cat-file -t 9601eb0` reports "Not a valid object name"). This discrepancy is outside the scope of
  F1 (F1 only asked about missing line numbers); following "fix items point by point, do not expand the
  scope into a rewrite", section 3's historical record was not changed; it is recorded here for review;
  every line-number check this round was done against the branch's actual tip `39da84e`, unaffected by
  this historical-record discrepancy.
