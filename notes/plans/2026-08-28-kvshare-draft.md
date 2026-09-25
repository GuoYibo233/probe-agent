# 2026-08-28 draft: the cache-reuse trainer's rulings and skeleton (staging area for round 5 discussion)

This file is the staging area for round 5 of discussion on 2026-08-28, meant so a conversation after a compact does not need to reread the context to keep going. Round 5 follows sections 1 through 14 of `plans/2026-08-28-plan.md` (sections 12 through 14 are the np821 review another session did the same day, which round 5 has read and absorbed). The file has four blocks: section 1 is the goal, section 2 is the rulings already locked in, section 3 is the skeleton and each step's status, section 4 is the facts measured this round. As of writing this file, not one line of the repo's code has changed; HEAD is still `dddd4da`; this round has not launched any GPU task, only run tokenizer checks on CPU.

## I. Goal (confirmed by gyb)

This round's deliverable is a new training program, ending when it passes smoke testing. The new program does four things: an event's full text passes through the base model only once, and each cut point's target segment is appended after the shared prefix to compute loss, which is idea one in `plans/2026-08-28-plan.md` section 10.2; no sample is truncated any more, an event whose full text exceeds the cap is dropped whole and counted; the cap changes from 4096 to a candidate value of 8192; cgen and cparam's number of training passes is fixed at 1 epoch.

Scope: cache reuse is done for cgen, and cparam uses the same code (checked against `train_causal_param.py` lines 152 through 166: cparam's input per row is text plus separator string plus tool name plus open parenthesis, target is the parameter string plus end token, the same structure as cgen); the three changes, drop, cap, epoch, apply to all three cells; the eval side only changes the parts the new trainer forces it to change.

What success looks like: for randomly drawn events, the row-by-row loss the new trainer computes differs from the existing row-by-row trainer's row-by-row loss within tolerance; in smoke testing on H100, the new trainer's rows-per-second exceeds the current 2.75 rows (`plans/2026-08-28-plan.md` section 9.2, A_h100 smoke test's `ips` at update 50), with at least 10% headroom on the memory peak.

## II. Rulings already locked in

Each entry gives the ruling itself and the reason actually settled on in discussion.

### 2.1 Cap candidate 8192, fixed by smoke testing; batches are sized dynamically by token budget

TIMELINE records this as "cap candidate 8192, smoke testing measures the peak using the longest event within 8192, falling back to 6144 if H100's headroom is under 10%; batches are sized dynamically by token budget, with an especially long event forming its own batch."

Reason: gyb's first instinct was to set 6144 directly, based on "8192 with two at a time is too slow," a number from the old row-by-row trainer (section 9.2: B_h100 at 2 rows per batch does 1.45 rows per second, against A_h100's 2.75). The new trainer has no such thing as "two at a time"; how many events go in one batch is set by the token budget. The cap of 6144 versus 8192 only differs by 58 events in train (the table in section 4: 6144 drops 58 events, 8192 drops 1), and these 58 events, estimated at about 7,000 tokens each, total roughly 400,000, within 6% of the 7,008,045 prefix tokens, so the cap does not determine speed. What the cap determines is two things: the memory peak when the single longest event passes through the base model along with the computation graph for an average of 45 target segments held until the backward pass (neither 6144 nor 8192 has been measured); and how many test events get dropped in evaluation (8192 drops 16 events, 1,024 rows, 0.26%; 6144 drops 218 events, 13,728 rows, 3.50%). gyb's own words were "keep it dynamic in general, so it doesn't blow up memory; handling especially long ones separately is one way to do it too."

### 2.2 Update unit: 8 events per update, same convention across all three cells

One parameter update is 2 logical mini-batches, each of 4 events; the loss is the average cross-entropy over all rows of these 4 events (rows weighted equally within a mini-batch, mini-batches weighted equally against each other), character-for-character the same as ctool's current code (`train_causal_tool.py` lines 404 through 429), except the accumulation count changes from 8 to 2. Memory dynamics are handled at the physical layer: a logical mini-batch's 4 events are split into 1 to 4 forward passes by token budget, and each forward pass's summed row loss is divided by that logical mini-batch's total row count, giving exactly the same gradient as computing it all at once. One epoch is 516 updates (4,126 events ÷ 8), and one cgen update is about 360 rows. All three cells use the same update unit; ctool itself also changes from 32 events to 8, no longer matching np821's ctool convention.

Reason: the closer one update's row count is to the old convention's 32 rows, the less the learning rate needs to be extrapolated. At 32 events per update (about 1,450 rows, 45x), the three lines of reasoning converge on an estimate of 5e-5; at 8 events (about 360 rows, 11x), the square-root rule gives 1e-5 to 3.3e-5, falling back into an already-proven range. SFT sources surveyed in the literature also lean toward small batches (`plans/archive/2026-08-26-hparam-survey.md` section 2.4: Massive SFT picked 32 from {32, 64, 128, 256}, LoRA Without Regret recommends an effective batch under 32). gyb's own words were "let's make the update size smaller then, it feels like too much."

Candidates dropped: 32 events per update (exactly matching np821's ctool), 4 events per update, 16 events per update.

### 2.3 Learning rate: default unchanged, sweep to be decided after smoke testing

The code's default values are unchanged: full-parameter 1e-5 (`train_causal_callgen.py` line 82, `FULL_LR`), LoRA 2e-4 (`lora_util.py`). Smoke testing only measures speed and memory; the learning-rate value does not affect it. After the new trainer passes smoke testing, a sweep will be run, picking the best by val_ce and writing it in as the new default:

- The minimum version sweeps two groups: 0.6B full-parameter cgen sweeps {1e-5, 2e-5, 5e-5}, 1.7B LoRA cgen sweeps {1e-4, 2e-4, 5e-4}, 1 epoch each, with sizes following the same mode.
- If smoke testing shows one epoch only takes a few hours, upgrade to sweeping one group per base model (4 base models x 3 values = 12 runs of 1-epoch training), comparing each size at its own optimum, the approach Tulu 3 and OLMo 2 use.

Reason: the survey report's section 4 concludes that no source has swept the SFT learning rate on Qwen3-Base; every approach in the literature fixes other settings, takes 3 values on a log scale, and picks by validation set. What needs a separate sweep is the two modes, full-parameter and LoRA (whose optima differ 10x), not the three sizes: the three base models' widths are 1024 / 2048 / 2560, and by arXiv 2602.06204's n^(-1/2) formula, 4B's optimum is 0.63 times 0.6B's, smaller than the 2 to 2.5x gap between adjacent tiers on the sweep grid. gyb's own words were "then I think sweep it."

Repository facts needed for the sweep (obtained by round 5 reading the logs): under "32 events per update, 1e-5," ctool's three batches' `calA_weighted_acc` at the end of three epochs are b06 0.6279 / 0.6773 / 0.6883, b17 0.6462 / 0.6749 / 0.6867, l17 0.6508 / 0.6702 / 0.6974 (each run's `train_log.jsonl` eval events); cgen b06's step event `loss` (the average loss over all mini-batches in the last 50 updates, `train_causal_callgen.py` lines 513 through 515) is 2.0384 at update 50, 0.24 at update 200, 0.0791 at update 1,000, 0.006 at update 5,800.

### 2.4 Tokenization convention: the common-prefix rule

Each row is tokenized the old trainer's way (row text plus separator string tokenized together, target string appended separately); this token sequence is compared token by token against the event's full-text tokens from the start, and the matching segment shares the cache, with the remaining tail plus the separator string and target string together forming this row's target segment. cparam's tail is the separator string plus tool name plus open parenthesis, the same rule.

Reason: the measurements in section 4, 4.1 through 4.3. This rule makes the new trainer's per-row token sequence match the old trainer's token for token, at the cost of only the last token or two of the prefix not being shared. Three consequences follow: the alignment acceptance check can directly use the existing row-by-row trainer as a reference, comparing loss row by row on the same row; the eval side's cgen and cparam input construction needs no change (both eval scripts already tokenize row text plus separator string together); the live-run prefix-truncation method (section 13.8) is unaffected.

### 2.5 Epoch count set per cell (locked on Claude's recommendation, gyb authorized on 2026-08-28 with "just settle everything you'd otherwise wait on me for")

cgen and cparam use 1 epoch, ctool keeps its 3, with epoch count remaining a per-cell parameter.

Reason: section 12.7's 8 cgen/cparam runs all have their lowest val_ce at epoch 0; section 12.8's 4 ctool runs keep rising over three epochs, not yet flattening at epoch 2, so "1 epoch" is a proven regression for ctool, while one ctool run only takes 1 to 3 hours. Section 13.3's 6 epochs is a separate experiment, not part of this round.

### 2.6 ctool's read-position rule gets fixed together at step 5 (locked on Claude's recommendation, same authorization as above)

The current rule is "the last token whose end position does not exceed the cut point" (`train_causal_tool.py` lines 144 through 149, the same rule at `eval_tool.py` lines 141 through 147). It changes to: find the token that crosses the cut point; if everything after the cut point is whitespace, read this token, otherwise (for example `ĠNext`, which carries the start of the next word) back off to the previous token.

Reason: the measurement in section 4, 4.4: 6.3% of cut points currently read the position of the word before the end-of-sentence punctuation. Training and offline evaluation follow the same rule, so np821's ctool numbers are internally consistent, not miscalculated, but the convention "the probe reads the end-of-sentence hidden state" is not achieved on this 6.3%; during a live run, the probe fires at the end-of-sentence token, one token off from the position read during training. Since the new version of ctool has to be retrained under the new convention anyway, this fix costs little extra time.

### 2.7 Other settings for the new trainer

- Evaluate full val_ce once per quarter epoch, saving the best version. Reason: training only 1 epoch would otherwise degrade the choice of best into just saving the last version (section 13.1); once the prefix is shared, computing one full val_ce only needs passing through 2,556 events, so evaluation becomes cheap.
- The step log gains an `lr` field; the accumulator now resets to zero when the log line is written (section 13.7: currently `run` resets at the start of the epoch while the divisor is fixed at 400, making the first step's loss after crossing an epoch boundary read artificially low).
- Section 13.4's cut-point subsampling is not adopted: once the prefix is shared, the 45 target segments cost almost no extra compute; the weighting convention follows ctool (equal weight per step, the 08-21 ruling).
- Per-row weight within an update, 4 events per logical mini-batch, physical batches split by token budget: see 2.2.
- The planned attention implementation is "one ctool-style forward pass, with all the target segments appended after the sequence, using one attention mask so that segment k sees only the first p_k positions of the prefix plus itself, with position indices continuing to count up from p_k." This shape is closest to ctool's. The most fragile point: which kernel sdpa picks with a custom mask; picking wrong would materialize the attention matrix and blow up memory on an 8192-token event, so the kernel choice must be verified on CPU or a single card before the spec is written.

## III. Skeleton and status

1. `locked` TIMELINE records one entry for the new convention (the text of 2.1, plus 2.2's update unit, 2.5's epoch count, 2.4's tokenization rule), a different convention from np821's twelve cells.
2. `locked` The new trainer's convention details: 2.2's update unit, 2.3's learning-rate process, 2.4's tokenization rule, 2.7's other settings.
3. `pending` Write the rulings into a spec and tickets, in `.scratch/kvshare-train/` (`spec.md` plus `issues/NN-<name>.md`, convention in `docs/agents/issue-tracker.md`). The spec needs to cover: the cache-reuse forward-pass design and attention mask (including kernel-choice verification results), splitting physical batches by token budget, the common-prefix rule, the definition of alignment acceptance (randomly drawn events, row-by-row loss compared against the existing row-by-row trainer, tolerance set at the same line as ctool's `--align-tol 3e-4`), the drop rule for all three cells, evaluation every quarter epoch, log fields, ctool's read-position rule. Why write the spec first: steps 4 through 6 need to dispatch sub-agents to implement in parallel, and without a spec, each implementer would guess at a different convention.
4. `pending` Implement the cache-reuse trainer (one shared version for cgen and cparam), registered in `run.py`'s registry (extension checklist in `.claude/skills/probe-pipeline/references/extending.md`).
5. `pending` Change all three trainers' truncation to whole-event drop-and-count when an event's full text exceeds the cap, change `--max-len`'s default to the candidate value, change cgen and cparam's epoch default to 1, change ctool's read-position rule per 2.6.
6. `pending` Alignment acceptance: randomly draw some events, compare the new trainer's row-by-row loss against the existing row-by-row trainer's, and only allow smoke testing once the difference is within tolerance.
7. `pending` Smoke testing goes through the gpu-run skill: measure the new cgen trainer's rows per second and memory peak on H100, against A_h100's 2.75. The smoke-test design needs to handle section 12.10's ramp-up segment (on tokyo108, every run's first 2,000 steps are slower than steady state; b06 cgen climbs from 2.77 to 11.3 rows per second): compare the new and old trainers at the same row count, not the same update count; section 13.2's `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` can be measured alongside as a switch.
8. `pending` `python3 run.py selfcheck` passes, commit, write back to the skill per probe-pipeline's Phase E.

Pending items:

- How the eval side handles overlong events (skip and count, or keep left-truncating). Not needed for smoke testing; to be decided when the new model needs evaluation. The tokenization construction does not need to change (2.4).
- The learning-rate sweep (2.3); whether to run the minimum version or sweep each base model separately is decided once smoke testing gives the hours needed for one epoch.
- `plans/2026-08-28-plan.md` section 7 item 5 (whether temporary scripts like `toklen.py` enter the repository) and item 6 (three corrections to the artifact) have not been touched.
- The six experiments in section 14 (allocator smoke test, ctool at 6 epochs, cut-point subsampling, token normalization, and so on) have not been ruled on by gyb and are independent of this round.

Next action: work through step 3 (write the spec and tickets). Step 3's most fragile point is the attention mask's kernel choice; verify it before writing the spec.

## IV. Facts measured in round 5 (CPU, Qwen3-0.6B-Base tokenizer, 300 events randomly drawn from the val set, 12,987 rows)

All four checks are combined into one script: `/home/y-guo/.claude/jobs/b39c625e/tmp/tokjunction_check.py` (the task's temporary directory, cleared along with the task when it is deleted), run from the repo root with `cprobe-env/bin/python`, taking about two minutes. The separator string `\n[CALL] ` splits into five tokens, `Ċ`, `[`, `CALL`, `]`, `Ġ`.

### 4.1 The old sequence and "offset prefix + separator string" almost never match on the same row

The sequence the old cgen trainer gets by tokenizing "row text + separator string" together, versus the sequence from tokenizing "the event's full text cut at the cut point by character offset (the largest token whose end position is ≤ the cut point) + separator string" separately: only 2 of 12,987 rows match. The reason is that whitespace at the seam merges with the separator string's newline into one token: when a row's text ends in two newlines, the old sequence has `.ĊĊĊ` as one token, while in the full text it is `.ĊĊ` plus the separator string's own `Ċ`, two tokens.

### 4.2 Tokenizing row text alone cannot reproduce the offset prefix

Three approaches tried: A, tokenize the row text directly; B, tokenize the row text and drop the trailing token if it is pure whitespace; C, rstrip the row text before tokenizing. Broken down by the type of whitespace at the end of the row text:

| whitespace type (row count) | A matches | B matches | C matches |
|---|---|---|---|
| one space (6,228) | 3 | 6,225 | 6,225 |
| one newline (2,662) | 1,806 | 1,394 | 49 |
| two newlines (3,684) | 3,681 | 3,647 | 1 |
| no whitespace (300, end of event) | 300 | 300 | 300 |
| three newlines (65) | 65 | 65 | 0 |

No single approach matches on every type. The reason single-newline rows fail to match is that a token like `)ĊĊ` straddles the cut point (the cut point is right after the first newline, and the second newline belongs to the next row's text); under the rule "end position ≤ cut point," the whole token gets assigned to after the cut point.

### 4.3 The common-prefix rule matches on every row

Comparing the old sequence (row text plus separator string tokenized together) against the full-text tokens' longest common prefix: 6,231 rows are 0 tokens shorter than the offset prefix, 5,761 rows are 1 token shorter, 136 rows are 2 tokens shorter, and 859 rows are actually 1 token longer. The target segment's token count, compared with "the separator string's 5 tokens plus the target string," differs by only -1, 0, or 1: 0 for 11,812 rows, -1 for 859 rows, 1 for 316 rows. Not one row differs by 2 or more.

### 4.4 The character distance from ctool's read position to the cut point

By the rule in `train_causal_tool.py` lines 144 through 149 (searching backward for the first t with `0 < ends[t] <= b`): 0 characters, 5,868 (45.2%); 1 character, 6,304 (48.5%); 2 characters, 593 (4.6%); 3 characters, 193 (1.5%); 4 characters, 28 (0.2%); 5 characters, 1. An example at a distance of 2 or more characters: the full text is `Spotify."\n` followed by the next row's `\nWe`; the tokenizer merges `."\n\n` into one token, which crosses the cut point, and the token actually read is `ĠSpotify`. The 400 samples reported in `plans/2026-08-28-plan.md` section 12.5 report 375 total across the 0- and 1-character tiers, with the remaining 25 not broken out, matching the 6.3% here.

### 4.5 Verified current state

HEAD `dddd4da`, with the working tree holding only the uncommitted `plans/2026-08-26-hparam-survey.md`, `plans/2026-08-28-plan.md`, and this file. Two temporary directories still exist: `/home/y-guo/.claude/jobs/9822b062/tmp/toklen/` (the stats script and per-row lengths), `/home/y-guo/.claude/jobs/bbbecca7/tmp/` (the shutdown script, the permutation-reproduction script, the smoke-test summary). All six smoke-test output directories `pipeline/runs/smoke/bslen_*_smoke` are present. Under `.scratch/` there are three directories, gen-preset, gpu-monitor-launch, research-loop, and not yet kvshare-train.
