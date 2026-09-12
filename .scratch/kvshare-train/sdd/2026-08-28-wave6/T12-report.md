# T12 Implementer Report: Round 2 Documentation Writeback

Ticket: `.scratch/kvshare-train/issues/12-docs-writeback-round2.md`
spec: `.scratch/kvshare-train/spec.md` §16.7 (checklist), §16.10 (silent failure points #28-#34)
Branch: `ticket/2026-08-28-wave6/T12` (base `ed88ad7`, head `b43ede0`)
Worktree: `/home/y-guo/reproduce/new1-wt/2026-08-28-wave6-T12` (deleted at wrap-up, branch kept)

## I. What was done (checked against the ticket's requirements item by item)

Per the ticket's instructions, first read `git log --oneline 7668166..HEAD`
(the 34 commits after merging) and the Comments on the five tickets (07-11),
to confirm the post-merge state of the code (rather than the ticket's original
text). There were a few places during reconciliation where the code deviated
from the ticket's original text (for example, ticket 10's `loop` probe was
changed per decision 32 to "run one group on each of the three blocks and take
the max", not the ticket's original wording of "only run the group with the
most loss positions"); before writing the documentation, every point was
calibrated against the current code (`--help` output + `grep -n
"add_argument"` to directly check the default values).

1. **`stage-commands.md` §3**:
   - Added four rows to the parameter table: `--gen-eval`/`--gen-bs`/`--gen-eval-at`,
     `--align-tok-tol`/`--align-bf16-mean-tol`/`--align-bf16-max-tol`/`--align-baseline-factor`,
     `--align-rule`/`--align-rel-tol` (noted that ctool only has these two new
     flags), `--mem-probe-pick` (one criterion sentence for each of the three
     values); plus another row for `--overlong` (three eval scripts, each of the
     three values written out clearly with its criteria and corresponding count
     keys).
   - Added a "learning-rate sweep" subsection after the real command block for
     `train_causal_share.py`, giving one command each for `sweep-lr plan
     --write` and `sweep-lr report --runs ... --out ...`.
   - Added three rows to §3's output checklist: `sweep-lr`'s
     `SWEEP_REPORT.json/.md`, the `mem_probe`/`mem_probe_summary` events
     produced by each cell's `--mem-probe`, and the `overlong_mode` and count
     keys newly added to the three eval scripts' reports.
   - §3.1 ③'s card-allocation rule was changed to reference
     `mem_probe_summary.worst_gb` (a named field rather than the vague "the
     probe of the fullest block"); the 1.1x margin and ②'s fragmentation
     discount remain two separately written criteria, not merged into one
     formula.
   - §3.2 gained a sentence noting the learning-rate sweep run_id has four
     segments, `ks828<tag>_gptoss_cgen_lr<lr>`, with output at
     `pipeline/runs/sweep/`, not entering the matrix, not entering
     `summarize_matrix`.
   - §7's card-allocation explanation near line 517, for the old probe field
     `longest_event`, was changed to `mem_probe_summary`'s `worst_gb`, with a
     clear statement of what `scope=full`/`scope=run` mean, and the limitation
     that under `--smoke`/`--max-events`, `scope=run` cannot represent the full
     dataset (corresponds to silent failure point #36).

2. **`invariants.md`**: updated the "cgen/cparam picking best" row, adding a
   sentence about the active trainer's `--gen-eval` (default 200, 0 disables)/
   `--gen-eval-at` (default `last`) convention and decision 28; §3 gained two
   new rows, "default value of the memory-probe block-picking method"
   (`--mem-probe-pick` default `cost`) and "default value of the alignment
   criterion" (`--align-rule` default `abs`, the four coarse-screening
   thresholds' default values equal the round-1 constants); §4 gained one new
   row, "default handling of overlong events on the eval side" (`--overlong`
   default `left`).

3. **`extending.md`**:
   - Added seven entries, #28 to #34, to the §5 silent-failure-point table,
     checking the trigger conditions one by one against the post-merge code
     (see "How it was verified" below); the first column of line numbers was
     changed to the `#N` format (matching how the code comments refer to
     "silent failure point #31"/"#32"/"#33"; the original table's rows 1-27
     were bare numbers, the seven newly added ones uniformly carry `#`. This
     inconsistency is noted below under "Self-check findings and open
     questions").
   - The "precedent for changing an implementation" section in §3 (line 123)
     changed "the four eval scripts are unchanged, word for word" to "scoring
     is unchanged word for word, round 2 added one switch, `--overlong`, to
     input construction (all fields unchanged when it defaults to `left`)",
     and added a sentence that all four round-2 switches are parameters, their
     default values equal the recommended values, and no new cell is
     introduced.
   - The row about the three-segment run_id shape in §3.4 (near line 167)
     gained a sentence that the learning-rate sweep run_id has four segments.

4. **`MAP.md`**: added a row for `sweep_lr.py` to the training-section table
   (labeled "(sweep)"); the `cgen`/`cparam` rows each gained a sentence about
   the new switches; the `share_data.py` row gained the five new functions
   (`full_token_ids`/`n_full_tokens`/`event_full_texts`/`select_keys`/`epoch_minibatches`);
   the rows of the three eval-section scripts
   (`eval_tool.py`/`eval_causal_call.py`/`eval_causal_param.py`) each gained a
   sentence about `--overlong`.

5. **`run.py`**: only changed the `notes` strings of the seven tasks named by
   the ticket. `train-cgen`/`train-cparam` gained three sentences for
   `--gen-eval`, `--align-rule`, `--mem-probe-pick`; `train-ctool` gained one
   sentence for `--align-rule`; `eval-tool-causal`/`eval-ccall`/`eval-cparam`
   gained one sentence for `--overlong`; `eval-tool-mbert` was given the
   sentence "the mbert head only supports `--overlong left`". None of the
   other keys, `stage`/`py`/`script`/`gpu`/`args`/`desc`, etc., were touched
   (checked with `git diff run.py`, only the `notes=[...]` list changed).

6. **`gates.md`**: the G13 (alignment check) row gained a sentence. The smoke
   gate only reads `PASS` from `ALIGN_CHECK.json`; the `rule` field (the newly
   written `abs`/`rel`/`both` from round 2) goes into the JSON but does not
   affect this gate.

7. **Three small wrap-up changes**: `extending.md` line 123 (see the merged
   explanation under item 1); `stage-commands.md` §7 (see the merged
   explanation under item 1); `pipeline/eval/ACCEPT_EVAL.md` gained a section,
   "§0 Round 2 correction", stating that this document records the code state
   as of 2026-07-31, and that starting from round 2, `REPLAY_REPORT.json`
   always writes the extra `overlong_mode` and the four count keys
   (`n_oow`/`n_skipped_bounds`/`n_dropped_events`/`n_dropped_bounds`)
   regardless of what value `--overlong` is given; "byte-for-byte identical"
   is no longer required, the new criterion is "all existing keys besides
   these few new ones are unchanged".

No `.py` logic was changed, no test file was changed (`git diff --stat` shows
only the seven documents / `run.py`'s notes, no other files).

## II. How it was verified

**Every parameter default value was checked directly against `--help` or the
source's `add_argument`**, not copied from the ticket/spec text. Commands used
for the check and key output (running the scripts in the worktree with the
main repo's `cprobe-env` interpreter):

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python3 pipeline/eval/eval_causal_call.py --help
  → --overlong {left,skip,drop-event}  default left (the --help text says "unchanged byte for byte")
/home/y-guo/reproduce/new1/cprobe-env/bin/python3 pipeline/train/train_causal_share.py --help
  → --gen-eval / --gen-bs / --gen-eval-at{all,last} / --mem-probe-pick{tokens,cost,loop}
    / --align-rule{abs,rel,both} / --align-rel-tol / --align-tok-tol /
    --align-bf16-mean-tol / --align-bf16-max-tol / --align-baseline-factor all listed
/home/y-guo/reproduce/new1/cprobe-env/bin/python3 pipeline/train/train_causal_tool.py --help
  → --align-rule{abs,rel,both} / --align-rel-tol listed, without those four coarse-screening threshold flags
grep -n "add_argument(.--(overlong|gen-eval|...)" pipeline/train/*.py pipeline/eval/*.py
  → train_causal_share.py:880  --gen-eval    default=200
    train_causal_share.py:882  --gen-bs      default=8
    train_causal_share.py:884  --gen-eval-at default="last"
    train_causal_share.py:889  --mem-probe-pick default="cost"
    train_causal_share.py:904/908/910/912/914 four coarse-screening thresholds default=2e-5/3e-4/2e-2/1e-1/3.0
    train_causal_share.py:917/920  --align-rule default="abs" / --align-rel-tol default=1e-5
    train_causal_tool.py:342/345   --align-rule default="abs" / --align-rel-tol default=1e-5
    eval_causal_call.py:484 / eval_causal_param.py:323 / eval_tool.py:324
      --overlong default="left"
```

The above default values fully match what I wrote into the documentation.

`pipeline/eval/eval_tool.py --help` additionally confirmed that `--overlong`
is effective only for `--head causal`, and that passing anything other than
`left` to the mbert head directly triggers `SystemExit`, consistent with the
newly added notes sentence for `eval-tool-mbert` in `run.py`.

The five new functions in `share_data.py` were checked for their names and
line locations with `grep -n "^def full_token_ids\|^def n_full_tokens\|..."`,
their function bodies/docstrings were read directly (`share_data.py:71-151`,
`:453-464`), and `epoch_minibatches`'s `random.Random(seed + ep).shuffle` was
compared word for word against the training loop's old code.

Every one of the #28-#34 entries newly added to `extending.md` §5 was found
a corresponding location in the post-merge code:

```
grep -n "silent failure point #\|silent point #" pipeline/train/*.py pipeline/eval/*.py
  train_causal_share.py:496  spec 16.5, silent failure point #31 (probe random-number state)
  train_causal_share.py:527  opt.state.clear()  # #32: a step with lr=0 still writes state, clear it
  eval_tool.py:450           silent failure point #33 (overlong_mode cache impersonation)
```
The code itself already marks #31/#32/#33 with comments, confirming that the
trigger conditions I checked match the implementation.
#34 was checked directly by reading `train_causal_tool.py:93-96` (filter first
by `label in label2id`, then take the last row) and `share_data.py:87-101`'s
`event_full_texts` (no filtering, directly takes the row with the largest
`sent_idx`), confirming the two rules differ. #28/#29/#30 were checked
respectively: `select_keys`'s `n_excluded_by_ctool` count, the call-site
location of `_attn_ctx` (`grep -n "_attn_ctx("` matches only one place, inside
the body of the `_forward_packed` function), and `pack_event`'s `row[:6]`
unpacking code.

**Acceptance commands** (the three named by the ticket + selfcheck):

```
$ python3 run.py selfcheck
selfcheck: 77 tasks / 4 recipes / 3 presets, all present
```
(The worktree itself lacks the venv symlinks. `cprobe-env`/`mbert-env`/
`envs/appworld`, etc. are all gitignored, and `git worktree add` does not
bring them along. First temporarily symlinked the corresponding main-repo
directories to get `selfcheck` to run clean, then deleted these symlinks
right after verification; `git status --short` now shows only the seven
changed documents.)

```
$ grep -c "overlong" .claude/skills/probe-pipeline/references/stage-commands.md MAP.md run.py
stage-commands.md:2  MAP.md:4  run.py:6         # all three hit, satisfies acceptance ①
$ grep -n "#34" .claude/skills/probe-pipeline/references/extending.md
300:| #34 | ...                                  # hit, satisfies acceptance ②
$ grep -c "worst_gb" .claude/skills/probe-pipeline/references/stage-commands.md
3
$ grep -c "runs/sweep" .claude/skills/probe-pipeline/references/stage-commands.md
5                                                 # both hit, satisfies acceptance ③
```

No `.py` logic or tests were changed, so no unit tests were run; the change to
`run.py` is only strings, and `ast.literal_eval` was used to extract and print
the seven tasks' `notes` lists once, to confirm the concatenated Chinese
sentences had not lost any spaces (a few real cases of Python adjacent
string-literal concatenation missing a space were actually caught during this
process, already fixed, see the next section).

## III. Commit list

- `b43ede0` T12: round 2 documentation writeback,
  stage-commands/invariants/extending/gates/MAP/run.py/ACCEPT_EVAL
  (79 lines inserted, 16 lines deleted, seven files: `stage-commands.md`,
  `invariants.md`, `extending.md`, `gates.md`, `MAP.md`, `run.py`,
  `pipeline/eval/ACCEPT_EVAL.md`)
- `4f10aec` T12: self-check fix, extending §5 #35/#36 dangling references
  redirected to spec 16.10 (issue found during self-check, see next section;
  one sentence each changed in `stage-commands.md`+`invariants.md`)

## IV. Self-check findings and open questions

- **Found and fixed**: in `run.py`, following that file's existing style, I
  split long sentences into multiple adjacent string literals written across
  physical lines (Python concatenates them automatically, without inserting a
  space); the first version had five places where a trailing space was
  missing at the end of a line, which after concatenation would produce
  several word-glued artifacts (a Chinese clause running straight into the
  `reldiff_hidden` identifier with no space, the `--gen-eval-at{all,last}`
  flag running straight into the following word, and `.meta.json` running
  straight into `excluded_idx`). This was found by using `ast` to pull out the
  `notes` lists of the seven tasks in the `TASKS` dictionary, actually
  evaluate them, and print them; all instances have now been fixed and
  re-checked once more with the same method, and all seven notes now read
  smoothly sentence by sentence. `MAP.md`'s cgen/cparam rows also had one
  instance of "missing a space before the closing bracket" at the end (`cost）|`
  was missing a space), likewise fixed.
- **Open question, for the main conversation to decide**: in the original §5
  silent-failure-point table of `extending.md`, rows 1-27 were all bare
  numbers in the "#" column (`| 26 |`); for my newly added rows 28-34, to
  make the `grep "#34"` acceptance command hit, and also to match the way
  code comments refer to things like "silent failure point #31", I changed
  them to carry a `#` prefix (`| #34 |`). This makes the "#" column's format
  inconsistent between the first 27 rows and the last 7. The ticket's
  acceptance criteria explicitly require `grep -n "#34"` to hit, and the
  table's original bare-number style cannot make that hit (I tried it, `grep
  "#34"` is empty against the bare-number version); faced with a choice
  between the two, I chose to change the format so the acceptance passes, but
  did not go back and uniformly change rows 1-27 to carry `#` as well (that
  would go beyond the ticket's scope of "add #28 to #34", and would be acting
  on my own initiative). Whether this front-back inconsistency should be
  unified later is left to the main conversation's judgment.
- **Open question, already corrected on the spot**: the spec 16.10 text
  actually lists nine entries, #28 through #36 (in the order 28, 29, 30, 31,
  32, 33, 35, 36, 34), but the ticket's step 5 explicitly says "add #28 to
  #34", and the acceptance grep also only checks `"#34"`. I followed the
  ticket's literal wording and added only the seven, 28-34; #35 (ctool's
  `--overlong` changes `n_events_scored`, affecting the matrix cross-cell
  convention) and #36 (`mem_probe_summary`'s `scope=run` cannot represent the
  full dataset) were **not** written into the `extending.md` §5 table. In the
  first version, I wrote cross-references like "see extending §5 #35"/"#36"
  in three places in `invariants.md`/`stage-commands.md`, but `extending.md`
  itself did not have these two entries. A dangling reference found during
  self-check, already changed in `4f10aec` to point at `spec 16.10 #35`/`#36`
  instead (those two entries do genuinely exist in the spec, so pointing
  there is accurate). Whether #35/#36 should also be formally added into the
  `extending.md` §5 table in a later ticket (outside this ticket's scope) is
  left to the main conversation's judgment.
