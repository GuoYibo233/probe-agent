# T01 Report — `pipeline/train/share_data.py`

Ticket: `.scratch/kvshare-train/issues/01-share-data.md`
Branch: `ticket/2026-08-28-wave1/T01`, base `2e61f5f01e5a79535cdc9a8622eb32213d83e10b`,
head `8e9c712` (worktree `/home/y-guo/reproduce/new1-wt/2026-08-28-wave1-T01`, deleted per protocol, branch kept).

## 1 What was done (against each ticket requirement)

Ticket items 1 through 6 correspond one-to-one to the newly created `pipeline/train/share_data.py`:

1. **`load_events(path, tok, mode, max_len, ro=None, limit=0, order="random")`** —
   fixed order per spec 3.2: group (event order = first appearance in the file,
   not reordered by event name) → `random.Random(SEED)` draws 50 events for a
   prefix-property spot check (over all events before dropping) → tokenize the
   full text of each event to get `n_full`, drop the whole event and count it in
   `dropped_events` if it exceeds `max_len` → take a subset by `limit`/`order`
   (`"random"` creates a new `random.Random(SEED)`, shuffles, and takes the first
   `limit`; `"shortest"` sorts by `n_full` ascending; after taking the subset,
   reorder by first appearance in the file again, keeping the return contract
   "event order = file order" regardless of how the subset was taken) → only
   tokenize and apply row-level dropping line by line for the events that remain.
   Row-level dropping branches by mode: cgen uses
   `train_causal_callgen.CALL_SEP`/`MAX_TGT_TOK`, cparam uses
   `train_causal_param.param_prompt_tail`/`param_target` (a `None` return is
   counted as `assembly_mismatch`); both sets of constants/functions are imported
   lazily inside the `load_events` function body, not copied. The `ro` parameter
   for `--readonly-env` filters using the same convention as `CallDS`/`ParamDS`
   (a non-readonly item drops the whole event, counted in the `ro` dict passed in
   by the caller).
   The common prefix `p` (spec 3.4) and the construction and assertion of
   `seg_ids`/`seg_lab`, `len(old_ids[p:]) >= 1`, are copied as-is. The two hard
   stops are ported from `train_causal_param.py` lines 337~353: this split exits
   if it loads 0 rows; it exits if the cparam stripping failure rate exceeds
   `ASSEMBLY_MISMATCH_LIMIT` (0.05, the old script's constant is referenced
   directly, the number is not copied). The upper-bound assertion on concatenated
   length (`MAX_BOUNDS` is imported lazily from `pipeline/annotate/rules.py`) is
   implemented per spec 3.5.
   Each returned event `dict` carries, beyond the `event/n_full/packed_len/
   prefix_len/rows` the ticket names, one extra field, `full_ids` (the tokenized
   full text of the event) — `pack_event` needs `full_ids[:P]` to build the
   prefix, the ticket does not list this field but without it `pack_event` cannot
   build the concatenated sequence; the self-check stage confirmed this is a
   necessary addition, not scope creep (see section 4).
   One more decision made independently: once all of an event's rows have been
   emptied out by row-level dropping (readonly/target too long/mismatch), the
   event itself does not go into the final returned `events` list (its rows are
   already recorded separately in `dropped_rows_tgt`/`assembly_mismatch`/`ro`, and
   are not counted again separately). The ticket did not write this rule; it is a
   gap encountered during implementation — see the self-check notes in section 4
   for details.
2. **`pack_event(ev)`** — following the concatenation formula in spec section 4,
   returns `(tokens, positions, labels, row_index, seg_bounds)`, all as python
   lists.
3. **`allowed_mask(ev)`/`batch_mask(packed_list, L_pad)`** — the two share one
   private core, `_allowed_from_packed`, which uses torch to vectorize-construct
   an `[L, L]` bool tensor following the attention-allowed relation in spec
   section 4 (causal within the prefix, the k-th segment sees the first p_k
   positions of the prefix and the first i+1 tokens of its own segment, segments
   cannot see each other, the prefix cannot see any target segment).
   `batch_mask` right-pads to `L_pad` (asserted to be a multiple of 16), builds
   the `[B, 1, L_pad, L_pad]` bf16 additive mask (a pad position as query only
   sees itself, to prevent softmax from producing NaN), `position_ids` and
   `input_ids` (pad positions get id=0), and the loss-position index table — read
   directly off the `labels` array itself (no shifting): a target token where
   `labels[t] != -100` is computed by logits at position `t-1`, and the entry is
   `(batch_idx, t-1, labels[t], row_index[t])`.
4. **`chunk_by_budget(events, tok_budget)`** — events are sorted descending by
   `packed_len` and packed greedily: a block's "number of events × the longest
   `packed_len` within the block" ≤ `tok_budget`; a single event over budget
   forms its own block by itself. On top of this, `worst_blocks` returns "the
   single event with the largest `packed_len`" and "the block, among the packing
   result, whose largest `packed_len` within it is the largest across blocks".
5. **`read_position(offsets, full_text, cut, keep)`** — per spec 11.3: `j` = the
   last real token whose start position is `< cut`; if `end_j <= cut`, read `j`;
   if `end_j > cut` and `full_text[cut:end_j]` is entirely whitespace, also read
   `j`; otherwise read `j-1`; two cases return -1 (no starting point found, or
   needing to fall back to `j-1` when `j=0`).
6. **Tests `tests/test_share_data.py`** — see section 2.

## 2 How it was verified

```
cprobe-env/bin/python -m unittest tests.test_share_data -v
```
All 18 test cases passed (two `TestPrefixRule` cases use the real Qwen3-0.6B-Base
tokenizer and a sample from the val set, the three `TestReadPosition` cases also
use the real tokenizer):
```
Ran 18 tests in 15.664s
OK
```
(The worktree did not have the `pipeline/data` symlink — it is a bare-name
symlink under gitignore, a new worktree does not bring it along — a local
symlink was added pointing back to
`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data` so that
`TestPrefixRule` would actually run instead of being skipped; this symlink was
not committed to git and does not affect the main repo.)

```
python3 -m unittest tests.test_share_data -v
```
The system python3 does not have torch, the whole module is cleanly skipped as
`unittest.loader.ModuleSkipped` (exit code 0), following the existing
convention in `tests/test_cparam_assembly.py`.

```
python3 -m unittest discover -s tests -v
```
Under the full discover run, `test_share_data` likewise correctly lands on
`ModuleSkipped`, not counted as a failure. The full run produces
`FAILED (failures=1, errors=1, skipped=18)` — both failures are unrelated to
this ticket and existed before I touched anything:
- `test_splice_replay` (`_FailedTest`, needs `openai_harmony` inside
  cprobe-env) — this is an old known issue recorded in the repo's existing
  memory (`new1-unittest-quirks`: "the full test run always leaves 1 error").
- `test_no_env_reads_default_preset` (`test_preset.TestBfclHandlerPreset`) —
  related to `configs/presets/default.json`, entirely unrelated to
  `share_data`/the trainer, not investigated further (out of this ticket's
  scope, only the two files this ticket should touch were touched).

```
mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/train'); import share_data; print(share_data.read_position)"
```
Exit code 0 (hard gate passed).

```
cprobe-env/bin/python -m unittest tests.test_cparam_assembly tests.test_lora_merge
```
All 22 test cases across the two existing test files passed, confirming no side
effects.

```
python3 run.py selfcheck
```
`74 tasks / 4 recipes / 3 presets, 16 gaps` — all 16 gaps are because the local
worktree lacks per-machine-installed interpreters/symlinks such as
`envs/*/venv`, `cprobe-env`, `mbert-env` (a newly created worktree does not
bring along these gitignored things), not a registry structure problem; this
ticket did not change `run.py` or any registry entry, `git status` shows only
the two new files `share_data.py` and `test_share_data.py`.

## 3 Commit list

- `8e9c712` T01: created `pipeline/train/share_data.py` (the data and
  tokenization module shared by cgen/cparam) + `tests/test_share_data.py`. A
  single commit, two new files, no existing file changed.

## 4 Self-check findings and open questions

- **The `event` dict carries an extra `full_ids` field**: the fields listed in
  ticket item 1 are `event, n_full, packed_len, prefix_len P, rows`, `full_ids`
  is not mentioned. But `pack_event` needs `full_ids[:P]` to build the prefix,
  and `pack_event` is the deliverable of item 2 of the same ticket; without this
  field it cannot be implemented. Judged this to be an omission in the ticket's
  enumeration rather than a deliberate exclusion, added this field, and flagged
  it here in the report for review.
- **An event whose every row is dropped at the row level does not go into the
  returned list**: the ticket text does not write this rule; it is a gap
  encountered during implementation — if this kind of record ("the event is
  present, its rows are an empty list") were kept, `pack_event` would build an
  "event" that has only a prefix, `packed_len=prefix_len`, and zero loss
  positions, taking up a slot in `--smoke`/`chunk_by_budget` while producing no
  training signal at all. Excluded per the gap criterion, no new counting field
  added (its rows are already recorded separately in `dropped_rows_tgt`/
  `assembly_mismatch`/`ro["dropped"]`). The `ev_long_tgt` case in the
  `test_cgen_and_cparam_drop_counts` test covers this branch (the first version
  of the test did not account for this gap; the assertion
  `"ev_long_tgt" not in kept_events` produced a FAIL first, and passed only
  after this exclusion logic was added — noted here because this is a
  root-cause fix, not a patch; a patch approach would have been to loosen the
  assertion in the test rather than change the implementation).
- **The two hard stops in `load_events` (0 rows / cparam stripping failure
  rate)**: the ticket text's "port the two hard stops as-is" only appears in
  the parenthetical note of item 1, the acceptance section (a)~(e) does not
  specifically list testing the hard stops as required; I additionally added
  the two cases `test_hard_stop_zero_rows` and
  `test_hard_stop_assembly_mismatch_rate` to assert that `SystemExit` really
  does get raised, judging this to be testing a function the ticket required
  rather than scope creep, but it does genuinely go beyond what (a)~(e)
  literally list in the acceptance section, flagged here for review.
- **The tests for `chunk_by_budget`/`worst_blocks` use hand-built
  `dict(event=.., packed_len=..)`**, rather than going through the full event
  structure produced by `load_events` — these two functions only ever read the
  single key `packed_len`, and a hand-built fixture makes the "greedy packing"
  logic clearer to test in isolation; the real full event structure has
  already been run once through `load_events`'s output shape in
  `TestPrefixRule`, together the two sides give full coverage, judged that
  there is no need to stack another layer testing chunking with real events.
- **Not yet verified**: functions such as `load_events`/`pack_event` have not
  been run under a genuine large-scale training scenario (the edge case of
  --max-len 8192, 64 rows/event), that is the responsibility of ticket 03 (the
  trainer) and gpu-run smoke testing; this ticket has only verified logical
  correctness at CPU unit-test scale.

## 5 MAP.md text for ticket 04

Ticket 04 is responsible for adding a row `(shared)` to the training table at
`MAP.md` line 88 (this ticket does not change `MAP.md`; per ticket item 24's
requirement, the text is written here):

```
| (shared) | `pipeline/train/share_data.py` | pure-CPU data and tokenization
module shared by the new cgen/cparam trainer (`train_causal_share.py`, ticket
03) and ctool/`eval_tool.py` (ticket 02): `load_events` groups by event,
computes the common prefix `p`, builds the target-segment `seg_ids`/`seg_lab`;
`pack_event`/`allowed_mask`/`batch_mask` build the concatenated sequence and
attention mask for form A; `chunk_by_budget`/`worst_blocks` pack greedily by
token budget; `read_position` is the single source of truth for the cut-point
read-position rule used by ctool/`eval_tool.py` |
module top level only has stdlib+torch, imports of
`train_causal_callgen`/`train_causal_param`/`rules.MAX_BOUNDS` are all deferred
to inside the `load_events` function body (mbert-env's transformers 4.57.6
cannot get past the version gate at the top level of the old training script
modules, and `eval_tool.py` needs to import this module under mbert-env to get
`read_position`); `mbert-env/bin/python -c "import sys;
sys.path.insert(0,'pipeline/train'); import share_data"` is a hard gate, must
exit code 0 |
```

## 6 Fix round 1 (2026-08-28, commit `d48c287`)

Branch `ticket/2026-08-28-wave1/T01`, base is still `2e61f5f`, this round's
head is `d48c287` (worktree
`/home/y-guo/reproduce/new1-wt/2026-08-28-wave1-T01-fix1`, deleted per
protocol, branch kept). Three outstanding findings were received, each fixed
in `pipeline/train/share_data.py`, no other file was touched.

### F1 (critical) — `worst_blocks` is missing the `events_per_mb` parameter, the fullest-block algorithm does not match the ticket

**Fix**: changed the signature to `worst_blocks(events, tok_budget,
events_per_mb)`, no longer borrowing `chunk_by_budget`'s approach of running
greedy packing over the full set of events and then picking "the block whose
largest `packed_len` within it is the largest" — that algorithm's per-block
event count is not constrained by `events_per_mb`, and a block like that would
not occur in real training. The new algorithm follows the ticket text: `B`
ranges from 2 to `events_per_mb`; sort `events` descending by `packed_len`;
for each `B`, scan with a sliding window of size `B` from the longest end
downward (under descending order, the longest within the window is exactly
the window's first element, and this value only decreases or stays the same
as the window moves down), take the first window that satisfies
`B * L_pad <= tok_budget` as the optimal group for that `B`; among the
optimal groups for the several values of `B`, take the one with the largest
`B * L_pad` as the "fullest block". When no window satisfying the condition
can be found (not enough events, or the budget too small to fit even 2
events), this returns an empty list (the ticket did not write this edge case,
judged that "no valid combination" should honestly return empty, not force
together a combination that does not satisfy the budget).

**Verification**: wrote `test_worst_blocks` (a hand-computed example with
`events_per_mb=3`, `tok_budget=200`, the B=2 optimal group `{b,c}`
(product=192) is larger than the B=3 optimal group (product=96), the single
event `a` with the largest `packed_len` is in fact not in the fullest block —
because pairing `a` with the second-largest `b` already exceeds the budget).
The same case also runs the old algorithm's approach (running
`chunk_by_budget` directly over the full set of events and then picking "the
block whose largest `packed_len` within it is the largest") for comparison,
the result is the single-event block `{a}`, different from the correct
answer `{b,c}`, asserting that this difference genuinely exists (not
something I merely assumed exists). Added two more edge cases:
`test_worst_blocks_no_valid_group_when_budget_too_small` (budget cannot even
fit 2 events, the fullest block returns an empty list),
`test_worst_blocks_empty_events` (empty `events`, both return an empty list,
keeping the original behavior).

### F2 (critical) — `chunk_by_budget`'s budget criterion uses `packed_len` instead of `L_pad`

**Fix**: added the helper function `_pad16(n)` (`((n + 15) // 16) * 16`, the
same convention as `batch_mask`'s `L_pad` padding), `chunk_by_budget`'s
budget criterion was changed from `n * cand_max <= tok_budget` to
`n * _pad16(cand_max) <= tok_budget`. `worst_blocks`'s sliding-window
criterion likewise uses `_pad16(window[0]["packed_len"])`.

**Verification**: wrote `test_budget_uses_padded_length`: two events with
`packed_len=161`, `tok_budget=322` — before padding, `2*161=322<=322` would
pass (they would be wrongly packed into the same block), after padding
`L_pad=_pad16(161)=176`, `2*176=352>322` does not pass, asserting the two
events end up as separate blocks each. The existing
`test_greedy_budget`/`test_single_event_over_budget_alone` cases pass without
modification (their assertions use the weak `<=` inequality, switching the
criterion from `packed_len` to `L_pad` only makes packing more conservative
and does not break these two assertions).

### F3 (critical) — `batch_mask` hardcodes `position_ids` at pad positions to 0, instead of "continuing the count"

**Fix**: `position_ids` in the pad range (`[L, L_pad)`) was changed from
"keeping the initialized 0" to numbering continuously starting after this
event's last real position (`positions[-1]`)
(`torch.arange(last_pos + 1, last_pos + 1 + (L_pad - L))`); when `positions`
is empty (`L=0`), taking `last_pos` as -1 is only an edge-case fallback to
prevent `IndexError`, not extra functionality — continuing the count from -1
gives 0, 1, 2..., which is consistent with the "continue the count" rule
itself. The `batch_mask` docstring was updated at the same time to remove the
incorrect statement that "`position_ids` at pad positions is 0".

**Verification**: added two position-by-position assertions in
`test_batch_mask`: for event A (`prefix_len=3`, real positions
`[0,1,2,1,2,3,3,4,5,2,3,4]`, the last real position is 4), the 4 pad
positions should be `[5,6,7,8]`; for event B (`prefix_len=0`, real positions
`[0,1]`), the 14 pad positions should be `[2..15]`. Both were actually run
and passed. The existing mask-related assertions (a pad position as query
only sees itself, real tokens cannot see pad) are unaffected — F3 only
changes the value of `position_ids`, not the computation of `allowed`/`mask`,
and under RoPE-style relative position encoding this discrepancy never
affected any real output to begin with (the finding itself says so too),
this change purely brings the implementation into alignment with the spec,
in the text sense.

### How it was verified (this round)

```
cprobe-env/bin/python -m unittest tests.test_share_data -v
```
All 21 test cases passed (18 existing + 3 newly added:
`test_budget_uses_padded_length`,
`test_worst_blocks_no_valid_group_when_budget_too_small`,
`test_worst_blocks_empty_events`; the existing
`test_worst_blocks`/`test_batch_mask` cases had their assertion content
changed, not counted as new):
```
Ran 21 tests in 15.858s

OK
```
(The worktree likewise did not have the three local symlinks
`pipeline/data`/`cprobe-env`/`mbert-env` — a known situation inherited from
the previous round, gitignored bare-name symlinks are not brought along by
`git worktree add` — added three local symlinks pointing back to the
corresponding directories/envs in the main repo in order to run; these three
symlinks were not committed to git, do not affect the main repo, and
disappear together once the worktree is deleted.)

```
mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/train'); import share_data; print(share_data.read_position)"
```
Exit code 0 (the hard gate still passes, this round did not touch this
function).

```
cprobe-env/bin/python -m unittest tests.test_cparam_assembly tests.test_lora_merge
```
All 22 test cases across the two existing test files passed, confirming no
side effects.

```
python3 -m unittest discover -s tests -v
```
`test_share_data` still correctly lands on `unittest.loader.ModuleSkipped`
(the system python3 has no torch), not counted as a failure. The full run
produces `FAILED (failures=1, errors=1, skipped=17)` — one failure
(`test_no_env_reads_default_preset`) and one error (`test_splice_replay`) are
both existing issues recorded in the previous round's report, unrelated to
`share_data`, this round did not change any file involved in them. `skipped`
went from 18 in the previous round to 17; the number itself was not
investigated further this round (it is not within the scope of these
findings, and is not caused by `share_data`/`test_share_data` — the one skip
corresponding to these two files consistently lands on `ModuleSkipped` in
both rounds), left for later handling as needed.

```
python3 run.py selfcheck
```
`74 tasks / 4 recipes / 3 presets, 14 gaps` — the gap count is 2 less than
the previous round's 16, because the local `cprobe-env`/`mbert-env` symlinks
added this round let the corresponding tasks' interpreter paths be found,
not a registry structure change; this round did not change `run.py` or any
registry entry, the tracked files in `git status` are only the two files
`share_data.py` and `test_share_data.py`.

### Commit list (this round)

- `d48c287` T01: fixed 3 findings (the `worst_blocks` signature and
  algorithm, the `chunk_by_budget` budget criterion, pad `position_ids`). A
  single commit, changes to two existing files, no file added or removed.

### Self-check findings and open questions (this round)

- **`worst_blocks` returns an empty list when no valid combination can be
  found**: the ticket text does not write this edge case, it is a behavior
  decision newly added during the fix (handled per the empty criterion, not
  scope creep); already flagged above in the F1 section and in
  `test_worst_blocks_no_valid_group_when_budget_too_small`.
- **`chunk_by_budget`'s two existing tests (`test_greedy_budget`,
  `test_single_event_over_budget_alone`) pass both before and after the
  criterion change**, because their assertions use the weak `<=` inequality
  and did not construct values that "cross the budget boundary before and
  after padding" — this is exactly the root cause F2 pointed out, "the tests
  did not catch this discrepancy"; this round's newly added
  `test_budget_uses_padded_length` fills in this discriminating power
  specifically.
- **Not yet verified**: the fixes for these three findings have only been
  verified for logical correctness at CPU unit-test scale; the full chain
  where `worst_blocks` actually feeds into the card-arrangement decision in
  spec section 10 (called by the trainer inside `--mem-probe`, checked
  against real H100 memory numbers) remains the responsibility of ticket 03
  and gpu-run smoke testing, this round did not run it.
