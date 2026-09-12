# demo walkthrough: reading the trainer from the first line to the last, in execution order

## How to use this walkthrough

This walkthrough is ordered by the program's real execution order, 15 stops
in total, and each stop says four things: which lines of which file the code
is in, what those lines do, what values show up when stopped there on the
demo's fake artifacts, and which key to press in the debugger. The reading
order is the execution order, so start at stop 1 and read straight through,
do not skip ahead.

Line numbers are as of HEAD `c13404b`; the two main files
(`pipeline/train/train_causal_share.py` and `pipeline/train/share_data.py`)
were last changed in `3f5dd79`. Line numbers will drift over time, function
names will not, so every stop gives the function name too.

The numbers in the text come from three sources. Numbers like event counts,
row counts, concatenated lengths, and block counts are computed by the
trainer's own functions on the fake artifacts, and stopping at the
corresponding breakpoint shows the same numbers; training-process numbers
come from `demo/runs/cgen/train_log.jsonl`; alignment-check numbers come
from `demo/runs/cgen/ALIGN_CHECK.json`. The model is randomly initialized, so
every loss value only shows that the flow works, nothing more.

The debugger only needs five actions. F5 continues to the next breakpoint,
F10 executes the current line then stops on the next one (without stepping
into a called function), F11 steps into the function called on the current
line, Shift+F11 steps back out of the current function to its caller, and the
Debug Console lets you evaluate an expression at any time. `justMyCode` in
launch.json is false, so F11 can step into transformers and torch code; for
calls like `tok(...)` (the tokenizer) and `json.loads`, use F10 to step over
them, since stepping in shows nothing relevant to the trainer.

To start reading from zero: set a breakpoint at
`pipeline/train/train_causal_share.py:859` (the first line of `main()`),
select "demo: train cgen on CPU (tiny model)" from launch.json, press F5,
then press F10 repeatedly; step into each call the walkthrough names with F11,
and press Shift+F11 to come back once you have seen enough. After reading the
first pass through the loop body line by line, skip later iterations with a
conditional breakpoint: right-click the red dot, choose "Edit Breakpoint,"
and fill in an expression -- it only stops when the expression is true.

## Names to fix first

Every name below is used one way, consistently, throughout this document.

- Event: one step in a trajectory, meaning a stretch of thinking plus the one
  tool call at the end of that thinking. Rows in `train.jsonl` with the same
  `event` field belong to the same event.
- Row: one sample obtained by cutting an event at some cut point; `text` is
  the prompt truncated to that cut point, `label_call` is the call string. An
  event has as many rows as it has cut points, and `sent_idx` is the row's
  index within the event, counting from 0.
- Full text: the `text` of the row with the largest `sent_idx` in an event,
  i.e. the prompt with the thinking written out in full. Every row's `text`
  is a prefix of the full text.
- Target string: what a row is learning to generate. For the cgen cell, that
  is `label_call` plus an eos.
- Tail: the separator string inserted between `text` and the target string,
  `"\n[CALL] "` for the cgen cell (the constant `CALL_SEP`).
- Common prefix length `p`: after tokenizing "`text` plus the tail" for a
  row, the number of tokens that match the full text's tokenization, counted
  from the start.
- Target segment: the slice of a row inside the concatenated sequence, equal
  to the tail's tokens plus the target string's tokens; loss is computed only
  on the target string's tokens.
- Concatenated sequence: an event's full-text prefix plus every row's target
  segment, one per event.
- Logical minibatch: `--events-per-mb` events (4 in the demo); loss is a
  weighted average over all rows in this batch, by weight.
- Physical block: a group of events cut out of a logical minibatch by token
  budget, one forward pass per block.
- Padded length: the longest concatenated sequence in a physical block,
  rounded up to a multiple of 16; every sequence in the block is right-padded
  to this same length.
- Additive mask: a matrix shaped
  `[events in block, 1, padded length, padded length]`, visible positions are
  0, invisible positions are negative infinity, added onto the attention
  scores.
- One update: gradients accumulated over `--accum` logical minibatches (2 in
  the demo), then one parameter update.
- Alignment check: before training starts, the same data is run through both
  the new path (one forward pass over the concatenated sequence) and the
  reference path (the old trainer's row-by-row forward pass) to compute
  per-row loss, and the two are compared for agreement.
- New path and reference path: the two computation routes in the alignment
  check; the new path is this trainer, the reference path is the old
  trainer `train_causal_callgen.py`'s `collate` plus `inst_ce`.

## Stop 1: main() parses arguments first, fixing the learning rate, seed, and device

Location: `pipeline/train/train_causal_share.py:858` to 952, function `main()`.

Lines 859 to 935 register command-line arguments one by one, line 936's
`lora_util.add_args(ap)` then adds the `--lora` family of arguments, and line
937 parses. Line 938's `lora_util.resolve_lr`
(`pipeline/train/lora_util.py:53`) fixes the learning rate: `--lr` was not
given on the command line, and `--lora` was not turned on either, so it takes
the full-parameter default `train_causal_callgen.FULL_LR`, which is 1e-5.

Lines 940 to 942 feed `train_causal_callgen.SEED` (42) into both torch and
random. Lines 945 to 948 are a gate: if the `--out` directory already has a
`train_log.jsonl` and `--force` was not given, it exits right there.
launch.json gives `--force`, so the demo passes this gate every time. Lines
950 to 952 fix the device: `dev` is `"cpu"`, `amp` (whether to use bf16
automatic mixed precision) is False, `mask_dtype` (the mask's data type) is
float32.

What to look at when stopped: stop at line 954, and typing `args` in the
Debug Console shows every argument, with `lr` at 1e-05.

## Stop 2: build() loads the tokenizer and the small model

Location: called at `pipeline/train/train_causal_share.py:954` to 957, the
function body is in `pipeline/train/train_causal_callgen.py:216` to 238.

Line 954 judges whether `--base` gave a name or a path: `"demo/tiny_qwen3"` is
not among the three names in `train_causal_callgen.MODELS` (qwen, qwen17,
qwen4), so `base_kw` is `dict(path="demo/tiny_qwen3")`. Press F11 at line 956
to step into `build`.

`build`'s line 226 gets the model directory, line 227 loads the tokenizer,
and lines 228 to 231 fix pad to eos, truncation side to left, and padding
side to right. The demo's tokenizer is copied from the real
Qwen3-0.6B-Base, both pad and eos are 151643. Line 232 sets the seed again,
line 234's `AutoModelForCausalLM.from_pretrained` loads the weights in
float32 and pins the attention implementation to `sdpa`; the terminal prints
`Loading weights: 100%|...| 24/24`. Line 238 returns the tokenizer, the
model (already moved to cpu), and the model path.

What to look at when stopped: back at line 959, typing
`sum(p.numel() for p in model.parameters())` in the Debug Console gives
9780928; `model.config` has `hidden_size` 64, `num_hidden_layers` 2,
`num_attention_heads` 4, `num_key_value_heads` 2, `vocab_size` 151669;
`model.model` is a `Qwen3Model` (the backbone), `model.lm_head` is the output
layer. Both attributes get called separately, later, at stop 10.

## Stop 3: run_align_check() proves the packed forward pass and the row-by-row forward pass compute the same loss

Location: called at `pipeline/train/train_causal_share.py:963`, function body
at lines 681 to 853.

This stop is the gate before training starts: the same validation events go
through both the new path and the reference path to compute per-row loss,
and the two must have a max difference below a threshold, or a report gets
written and then `sys.exit(2)`. After pressing F11 to step in, the following
follows the code's actual order.

Line 688 calls `model.eval()`, line 692 sets float32 matmul precision to
highest (the alignment check needs a strict comparison of fp32 results).

Line 698's `_align_candidates` (lines 554 to 581) draws events from
`val.jsonl`: first grouped by `event`, each group's row with the largest
`sent_idx` gives the full text for that group, events whose full text is at
most 2048 tokens (`ALIGN_LEN_FILTER`) become candidates, and
`random.Random(42).sample` draws `--align-events` of them. The demo draws 3
events: `appworld_demo/appworld_demo17_1_r0|s1` (6 rows),
`appworld_demo/appworld_demo12_1_r0|s1` (4 rows), and
`appworld_demo/appworld_demo16_1_r0|s0` (3 rows), 13 rows total.

Line 701's `_write_align_tmpfile` (lines 584 to 594) writes these 13 rows,
sorted by `(event, sent_idx)`, into a temp file whose name starts with
`kvshare_align_`, placed in the system temp directory and deleted at line
848. Both paths read this same file, so the row order naturally agrees
between them.

Line 709 loads the temp file written at line 701 with the new path's
`share_data.load_events` (stop 5 covers `load_events` in detail), and line
714 loads the same temp file with the reference path's
`train_causal_callgen.CallDS` (`pipeline/train/train_causal_callgen.py:118`).
`CallDS` stores each row as a six-tuple
`(text, tgt, w, label_call, ready, has_lm)`, where `tgt` is `label_call`
tokenized plus eos. Lines 716 to 726 check that the two sides agree on row
count, row order, and drop counts.

Line 728's `_ref_forward` (lines 597 to 665) is the reference path's forward
pass, 4 rows per batch (`REF_BATCH`). Line 634 calls the old trainer's
`collate` (`train_causal_callgen.py:181`): each row has `text + CALL_SEP`
tokenized, left-truncated to `max_len - len(tgt)`, then `tgt` appended;
`labels` is -100 over the prompt part and the target tokens over the target
part, right-padded within the batch. Line 636 runs the whole batch through
the model, getting the logits at every position; lines 638 to 641 do the
"predict the next token" shift: the logits at position `t-1` correspond to
the label at position `t`, and cross-entropy is only computed where the
label is not -100. Line 653 calls the old trainer's `inst_ce`
(`train_causal_callgen.py:241`) once more, getting the per-row mean
cross-entropy; lines 654 to 661 assert that the locally aggregated per-row
result agrees with `inst_ce`'s return value to within 1e-6, raising
`RefBaselineDriftError` if not. Line 730 runs `_ref_forward` once more with 1
row per batch, giving the "unpadded" baseline, used to judge how much
difference padding itself introduces.

Line 732's `_new_forward` (lines 668 to 678) is the new path's forward pass:
each event is passed once through `_forward_packed` (stop 10) individually,
then `_aggregate_rows` aggregates the results per row.

Lines 734 to 763 compare: `row_diff` is the max absolute per-row difference,
`tok_diff` is the max absolute per-token difference, `baseline_diff` is the
difference between the 4-row batch and the 1-row batch, and `ref_scale` is
the mean absolute value of the reference path's per-row loss (the
denominator for the relative criterion). Under `--align-rule abs`, `abs_ok`
requires `row_diff <= 2e-5` and `tok_diff <= 3e-4`. The bf16 coarse-screening
at line 767 only runs on cuda, skipped on CPU, so the two bf16 fields in the
report are null. Lines 784 to 798 write `ALIGN_CHECK.json`, and lines 800 to
823 exit if PASS is false. The `finally` block at lines 846 to 853 deletes
the temp file, restores matmul precision, and calls `model.train()`.

What to look at when stopped: stop at line 734; `row_new`, `row_ref`, and
`row_ref_solo` are each lists of length 13, `tok_new` and `tok_ref` are
length 161. The demo's report: `max_abs_diff` 0.0, `max_tok_diff`
9.5367431640625e-07, `baseline_max_abs_diff` 0.0, `ref_scale`
11.913296479445238, PASS true.

## Stop 4: the LoRA and gradient-checkpointing branches are both skipped in the demo

Location: `pipeline/train/train_causal_share.py:964` to 990.

Line 964: `--align-only` was not given, continue. Line 967: `args.lora` is
False, `lora_wrap` is None, the model trains with all parameters. Line 968:
`--grad-ckpt` was not given, skipped. Line 973: `model.train()`. Lines 975 to
979: the read-only-tool mode (`--readonly-env`) is off, all three variables
are None. Lines 981 to 990: not `--smoke`, so `order` is `"random"`, `n_tr`
and `n_ev` are both 0 (no event-count limit), `epochs` is 2.

## Stop 5: load_events() turns the jsonl into events and rows

Location: called twice at
`pipeline/train/train_causal_share.py:992` to 997 (training set, validation
set), function body at `pipeline/train/share_data.py:156` to 334.

Press F11 to step in at line 992. The function body has six sections in a
fixed order, and the reason for the fixed order is in the comment at lines
159 to 162: the order random numbers are consumed in determines the sampling
result.

The first section (lines 204 to 217) groups: reads the jsonl line by line,
grouping by `event`, with events ordered by first appearance in the file and
rows within a group sorted ascending by `sent_idx`; the full text is taken
from the row with the largest `sent_idx`. The demo's training set comes out
to 12 events.

The second section (lines 220 to 223) spot-checks the prefix property:
`random.Random(42)` draws at most 50 events, asserting that every row's
`text` is a prefix of the full text. The demo only has 12 events, so all 12
get checked.

The third section (lines 230 to 237) tokenizes the full text:
`full_token_ids` gives `full_ids`, and events whose length exceeds
`--max-len` (8192) are dropped whole and counted in `dropped_events`. Nothing
is dropped in the demo.

The fourth section (lines 240 to 247) takes a subset: `limit` is 0, skipped.

The fifth section (lines 254 to 295) tokenizes row by row, the section most
worth reading closely; stop at line 263 and step through with F10 one line at
a time. For the cgen cell: line 264's `tail` is `CALL_SEP`, line 265's
`tgt_str` is this row's `label_call`, lines 267 to 269 give `tgt_ids` as
`label_call` tokenized plus eos. Line 279 drops rows whose target exceeds 160
tokens (`MAX_TGT_TOK`). Line 282 tokenizes `text + tail` as a whole to get
`old_ids`, line 284's `_lcp` (lines 51 to 57) compares `old_ids` against
`full_ids` token by token to get the common prefix length `p`, and line 285's
`tail_ids` is `old_ids` from `p` onward. Lines 290 to 291 concatenate the
target segment: `seg_ids = tail_ids + tgt_ids`, and `seg_lab` is -100 over
`tail_ids`'s positions and the target token itself over `tgt_ids`'s
positions. Line 293 stores this row as the seven-tuple
`(sent_idx, text, p, seg_ids, seg_lab, w, gen)`, where `gen` is a dict for
generative evaluation.

The sixth section (lines 302 to 306) computes two event-level lengths:
`prefix_len` is the max of all rows' `p`, and `packed_len` is `prefix_len`
plus the sum of all target segments' lengths. Lines 309 to 330 are three hard
stops (0 rows, the cparam stripping failure rate, concatenated length over
the ceiling), and lines 332 to 334 return the event list and the counts.

What to look at when stopped, using the training set's first event
`appworld_demo/appworld_demo00_1_r0|s1` as an example (stop at line 304, with
the conditional-breakpoint expression
`e["event"].endswith("demo00_1_r0|s1")`). The full text is 147 tokens
(`n_full`), the 4 rows' `p` are 109, 123, 136, and 146, `prefix_len` is 146,
every row's target segment is 15 tokens (5 for the tail plus 10 for the
target), and `packed_len` is 146 plus 4 times 15, equal to 206. All four
rows' target strings are the same,
`apis.todoist.show_tasks(status=pending)`, and `w` is 0.25 for all of them.

Line 285's `tail_ids` has a detail worth seeing with your own eyes at the
breakpoint. `CALL_SEP` tokenized on its own is 5 tokens
(`[198, 58, 25427, 60, 220]`), but the first row's `tail_ids` decodes to
`."\n\n[CALL] `, with the tail also swallowing the `."` at the end of
`text`. The reason is that when the characters at the end of `text` are
tokenized together with the separator string, the tokens near the boundary
differ from the tokens in the full text, so the common prefix already breaks
before `."`, giving `p` 109 rather than `text`'s own token count. This is
exactly why line 284 compares token by token instead of counting `text`'s own
token count. The last row (`sent_idx` 3) has `p` 146, one less than the full
text's 147, again from retokenization at the boundary.

The training set comes out to 12 events, 61 rows; the validation set is 6
events, 27 rows; all four drop counts are zero, and these four numbers get
written into `train_log.jsonl`'s `start` record.

## Stop 6: sample_gen_eval_rows() draws the 4 rows used for generative evaluation

Location: called at `pipeline/train/train_causal_share.py:999`, function
body at lines 245 to 263.

Line 257 flattens the validation set's 6 events / 27 rows into one list,
lines 258 to 260's `random.Random(42).shuffle` then take the first
`--gen-eval` (4) of them, and line 262 packs each row as
`(text, None, None, tgt)`. The demo draws these 4 target strings, in order:
`apis.phone.send_message(phone_number=555-0134, message=Please get on venmo.)`,
`apis.venmo.show_account()`, `apis.venmo.show_account()`, and
`apis.supervisor.show_profile()`.

## Stop 7: computing the update count, building the optimizer and the learning-rate schedule, writing the start record

Location: `pipeline/train/train_causal_share.py:1015` to 1063.

Line 1015: the evaluation token budget is twice the training budget, equal
to 1536. Line 1017: `max_tgt_tok` takes cgen's 160. Lines 1020 to 1023
compute the update count: `M` (logical minibatches per epoch) is 12 divided
by 4, rounded up, equal to 3; `U` (updates per epoch) is 3 divided by 2,
rounded up, equal to 2; `steps` is 2 times 2 epochs, equal to 4.

Lines 1025 to 1027: `lora_util.opt_params` returns all parameters unchanged
(24 tensors) when LoRA is off; `AdamW` with learning rate 1e-5, weight decay
0.01; `get_linear_schedule_with_warmup`'s warmup step count is
`int(4 * 0.05)`, equal to 0, total steps 4. The linear schedule multiplies
the learning rate by `(4 - s) / 4` after the `s`-th `sch.step()`, so the
actual learning rates used across the four updates are, in order, 1e-5,
7.5e-6, 5e-6, and 2.5e-6. The step record's `lr` field in `train_log.jsonl`
is read after `sch.step()` (line 1147), so step 1 records 7.5e-6 and step 4
records 0.0 -- what gets recorded is always the value for the next step.

Line 1029 opens `train_log.jsonl` in append mode, so rerunning with `--force`
leaves the old records in place, and the file ends up with records from both
runs. Lines 1031 to 1035's `log()` writes one line of JSON and prints it to
the terminal each time it is called. Lines 1037 to 1062 write the `start`
record, with fields from this stop's computed settings, stop 1's arguments,
and stop 3's alignment-check result. Line 1063's
`heartbeat.emit(0, 4, "step")` (`ops/heartbeat.py:17`) writes a line of JSON
starting with `@hb ` to standard output, for the cluster's sampler to judge
liveness; no sampler is reading it in the demo, so it can be ignored.

## Stop 8: each epoch first shuffles events, cuts logical minibatches, and fixes the evaluation points

Location: `pipeline/train/train_causal_share.py:1092` to 1111.

Line 1093's `share_data.epoch_minibatches`
(`pipeline/train/share_data.py:453` to 464): copies the event list,
`random.Random(42 + ep).shuffle` shuffles it, and cuts every 4 into one
logical minibatch. The demo's epoch 0 gives three logical minibatches, in
order (event numbers only): demo07, demo05, demo02, demo08; demo09, demo06,
demo11, demo03; demo04, demo00, demo01, demo10. Epoch 1 switches to seed 43
and reshuffles into a different order.

Lines 1101 to 1104 fix the evaluation points: `k` runs from 1 to `E`
(`--eval-per-epoch`, equal to 2), and the evaluation point
`p = ceil(U * k / E)`, giving the dict `{1: 1, 2: 2}`, meaning each epoch
evaluates once after the 1st update (`frac` 1) and again after the 2nd update
(`frac` 2). Lines 1106 to 1111 zero out this epoch's counters.

## Stop 9: one parameter update is the gradient accumulation of two logical minibatches

Location: `pipeline/train/train_causal_share.py:1112` to 1134.

Lines 1113 to 1115 take one group from the logical-minibatch list:
`group_size` is the smaller of `--accum` (2) and the number of remaining
logical minibatches, so the epoch's first group is 2 logical minibatches, and
the second group has only 1, with `n_g` becoming 1 accordingly. `n_g` is
later divided into the loss, to keep the gradient's scale the same as a full
group even when the group is not full.

Lines 1118 to 1127 do three things for each logical minibatch in the group.
Line 1119: `W` is the sum of weights over all rows in the current logical
minibatch; one event's rows sum to 1 in weight (`w` equals 1 divided by the
row count), and there are 4 events, so `W` is roughly 4 (the difference comes
from `w` being rounded to 6 decimal places). Line 1120's
`share_data.chunk_by_budget` (`pipeline/train/share_data.py:467` to 496) cuts
physical blocks: events are sorted descending by `packed_len` and packed
greedily, with the rule that "events in block times padded length" must not
exceed `--tok-budget` (768). The demo's epoch 0, first logical minibatch, has
four `packed_len` values 349, 238, 236, 203: the first two pad to 352, and 2
times 352 is 704, not over 768, so they go into the first block; adding the
third would make it 3 times 352, equal to 1056, over budget, so the third and
fourth start a new block (padded to 240). All three logical minibatches each
cut into 2 blocks. Epoch 1's second logical minibatch is 239, 236, 203, 137:
the first three at 3 times 240, equal to 720, share one block, and 137 gets
its own block.

Press F11 to step into line 1121's `backward_logical_minibatch` (lines 178
to 213): line 205 iterates over physical blocks, line 207's `block_row_ce`
(stop 10) computes this block's per-row mean cross-entropy `ce_per_row` and
per-row weight `w`, line 208's `loss_c` is the weighted sum divided by the
whole logical minibatch's `W`, and line 210's `(loss_c / n_g).backward()`
runs backward. The gradients of several physical blocks accumulate this way
onto the parameters' `.grad`, and then accumulate again with the other
logical minibatch's gradient in the group. Lines 211 to 212 add `loss_c` into
the current logical minibatch's running loss and add up the row count.

Back in `main()`, line 1128's `clip_grad_norm_` clips the overall gradient
norm to 1.0 and returns the pre-clip norm; `train_log.jsonl`'s `grad_norm`
records exactly this pre-clip norm (step 1 is 2.1414, above 1.0, so this
step's gradient gets scaled down to 1 divided by 2.1414 of its original
size). Line 1129's `opt.step()` updates the parameters, line 1130's
`sch.step()` advances the learning-rate schedule, line 1131 zeros the
gradient, and line 1132 increments `gstep`.

What to look at when stopped: stop at line 1121, look at `len(group)`,
`n_g`, `W`, `[[ev["packed_len"] for ev in b] for b in blocks]`. Stop at line
1128, look at `gstep`, `sch.get_last_lr()`, then step past line 1130 with F10
and look at `sch.get_last_lr()` again.

## Stop 10: _forward_packed() concatenates one physical block into a sequence, builds the mask, and computes per-token cross-entropy

Location: `block_row_ce` at
`pipeline/train/train_causal_share.py:169` to 175, `_forward_packed` at
lines 123 to 157, `_aggregate_rows` at lines 160 to 166; concatenation and
masking are in `pipeline/train/share_data.py:339` to 450.

This is exactly where this trainer differs from the old trainer, worth
walking through line by line. Using stop 5's event demo00 as an example,
first understand it with a block that has only this one event, then look at
a real block.

Line 135 calls `share_data.pack_event` (`share_data.py:339` to 369) for each
event in the block. The concatenated sequence `tokens` is the full text's
first `prefix_len` tokens followed by every row's target segment; demo00 is
146 plus 4 times 15, equal to 206 tokens. `positions` is the position number
of every token: the prefix is 0 through 145, and the `k`-th row's target
segment continues counting from that row's own `p`, with the four segments
starting at 109, 123, 136, and 146. This way the `k`-th row's target segment
sees exactly the same position numbers it would see if "`text` plus tail
plus target" were tokenized on its own, as in the old trainer. `labels` is
-100 throughout the prefix and `seg_lab` over the target-segment part.
`row_index` marks which row each token belongs to, -1 for the prefix.
`seg_bounds` is each segment's half-open interval within `tokens`; for
demo00 that is `[(146, 161), (161, 176), (176, 191), (191, 206)]`.

Line 136's `_l_pad` pads the block's longest concatenated sequence up to a
multiple of 16; demo00 alone in a block gives 208. Line 137's
`share_data.batch_mask` (`share_data.py:402` to 450) builds four things.
`input_ids` is shaped `[events in block, padded length]`, with padding
positions filled with 0. `position_ids` continues counting from each event's
last real position number at the padding positions. `mask` is decided by
`_allowed_from_packed` (`share_data.py:372` to 393), three rules combined:
inside the prefix it is ordinary causal attention (only self and earlier);
inside a target segment, a token only sees earlier tokens within the same
row; a token in a target segment can also see prefix tokens at positions
less than that row's `p`. Segments cannot see each other, and the prefix
cannot see any target segment. Padding positions, as a query, only see
themselves (an entirely invisible row would make softmax produce NaN).
Visible positions are filled with 0, invisible ones with negative infinity.
`loss_idx` lists every target token that gets a loss: whenever `labels[t]`
is not -100, it records `(event index, t - 1, labels[t], row_index[t])`,
meaning the hidden state at position `t - 1` is responsible for predicting
the token at position `t` -- the same shift as at lines 638 to 639 in the
reference path.

What to look at when stopped (stop at `share_data.py:450`, with the
conditional-breakpoint expression
`len(packed_list) == 1 and len(packed_list[0][0]) == 206`).
`input_ids.shape` is `(1, 208)`, `mask.shape` is `(1, 1, 208, 208)`,
`len(loss_idx)` is 40 (4 rows times 10 target tokens), `loss_idx[0]` is
`(0, 150, 13725, 0)` (position 150 is the tail's last token in the first
row's target segment, 13725 is the target string's first token), and
`loss_idx[-1]` is `(0, 204, 151643, 3)` (the fourth row's eos).
`(mask[0, 0] == 0).int()` is the 0/1 matrix, and
`(mask[0, 0] == 0).int().sum(1)` is how many tokens each position can see:
the `i`-th position in the prefix sees `i + 1` tokens; the first token of
each of the four segments sees 110, 124, 137, and 147 tokens, each equal to
that segment's `p` plus 1.

Back in `_forward_packed`. Lines 138 to 140 move all three things to the
device, casting the mask to `mask_dtype` (float32 on CPU). Line 141's
`_base_model_and_head` takes out the backbone `model.model` and the output
layer `model.lm_head`. Line 143 calls only the backbone, passing in
`input_ids`, the additive mask, and `position_ids`, with `use_cache=False`,
getting `last_hidden_state`, shaped `[events in block, padded length, 64]`.
Lines 146 to 148 pull out the batch index, query position, and target id
tensors by `loss_idx`, and lines 149 to 153 convert each target token's row
number into a global row number within the block (the first event's rows
come first, then the second event's rows continue counting). Line 154 takes
the hidden state only at loss positions, line 155 runs only the loss
positions through the output layer to get logits, shaped
`[target token count, 151669]` -- not the logits at every position. Line 156
computes per-token cross-entropy, and line 157 returns `ce`, `global_row`,
and the block's total row count.

Line 172's `_aggregate_rows` uses `index_add` to sum by row number and
divide by each row's token count, giving each row's mean cross-entropy, on
the same basis as `inst_ce`. Line 173 takes out each row's weight `w`.

What a real block looks like: the demo's epoch 0, first logical minibatch's
first block, is two events with `packed_len` 349 and 238 (5 rows each),
padded length 352, `input_ids.shape` is `(2, 352)`, `mask.shape` is
`(2, 1, 352, 352)`, line 157's `ce.shape` is `(170,)` (170 target tokens),
10 rows in the block, and `global_row` ranges from 0 to 9.

The first time the breakpoint at line 138 stops is during stop 3's alignment
check (`events` has only 1 event), and stop 13's evaluation also passes
through line 138. To see only the forward pass during training, add the
condition `model.training`: both the alignment check and evaluation run
under `model.eval()`, and only the training loop runs under `model.train()`.

## Stop 11: where the mask and position_ids go once they enter transformers

Location: F11 at `pipeline/train/train_causal_share.py:143`. This stop can
be skipped -- only needed when you want to confirm "the mask the trainer
built is really used as-is by the attention layer."

Steps into `Qwen3Model.forward`
(`cprobe-env/lib/python3.11/site-packages/transformers/models/qwen3/modeling_qwen3.py:378`).
Line 392 looks up the word embeddings. Line 397's
`if position_ids is None` does not hold, so the trainer's position numbers
are kept. Lines 403 to 415 call `create_causal_mask`
(`transformers/masking_utils.py:871`); `create_causal_mask` calls
`_preprocess_mask_arguments` at line 936 (itself at line 767), line 818
judges the incoming mask is a four-dimensional tensor and returns it
unchanged, and lines 939 to 940 return early. So the trainer's additive mask
is not touched, not a single value. Line 421 uses `position_ids` to compute
the rotary position encoding, which is where the trainer's choice to
continue each target segment's position numbers from its own `p` takes
effect. Lines 423 to 432 pass through the 2 `Qwen3DecoderLayer`s in turn.

`Qwen3DecoderLayer.forward` (line 305) is the standard "norm, attention,
residual, norm, MLP, residual." `Qwen3Attention.forward` (line 252): lines
263 to 265 compute q, k, v and normalize q and k, line 268 adds the rotary
position encoding, lines 273 to 275 select the attention function by
`config._attn_implementation` (`sdpa`), and line 277 calls it.

The attention function is `sdpa_attention_forward`
(`transformers/integrations/sdpa_attention.py:79`). Lines 97 to 100: 4 query
heads against 2 key-value heads, and `use_gqa_in_sdpa` (lines 28 to 38)
returns False when a mask is given, so the keys and values get duplicated
into 4 heads by `repeat_kv`. Line 120: `is_causal` becomes False, because the
mask is not empty -- the whole causal relationship is expressed by the mask.
Lines 154 to 163 call
`torch.nn.functional.scaled_dot_product_attention`, with `attn_mask` being
exactly the trainer's additive mask. On CPU, `_attn_ctx`
(`train_causal_share.py:98`) returns an empty context, and torch picks the
kernel itself.

## Stop 12: every update writes one step-log line

Location: `pipeline/train/train_causal_share.py:1136` to 1152.

`--log-every 1`, so every update writes. Line 1137's `loss` is the average
of this group's logical minibatches' `loss_c` (step 1 is 11.931). Lines 1138
to 1142 are throughput: `ips` is rows per second so far in the current
epoch, `ips_win` is rows per second since the last log line, and `eps` is
events per second. Line 1143's `_peak_gb` is always 0.0 on CPU. Lines 1146 to
1149 write the record: `rows` is the epoch's cumulative row count (42 at
step 1, 61 at step 2), `lr` is the learning rate for the next step (explained
at stop 7), and `grad_norm` is the pre-clip gradient norm. Line 1150 writes
another heartbeat line.

The demo's four updates give `loss` in order 11.931, 11.9355, 11.9387,
11.9094, all near `ln(151669)` equal to 11.929. 11.929 is the cross-entropy
of a uniform distribution over 151669 words, and a randomly initialized
model's computed loss lands right around that.

## Stop 13: eval_ce() and eval_gen() give val_ce and the hit rate at the evaluation points

Location: `pipeline/train/train_causal_share.py:1154` to 1175, `eval_ce` at
lines 217 to 242, `eval_gen` at
`pipeline/train/train_causal_callgen.py:309` to 332.

Line 1154's `u` (the current epoch's completed update count) only evaluates
when it is in the evaluation-point dict, with `frac` being the matching
index. Press F11 at line 1156 to step into `eval_ce`: line 226 calls
`model.eval()`, line 228 cuts the validation set's 6 events into blocks by a
budget of 1536, and the demo cuts them into two blocks, the first being the
five events with `packed_len` 281, 247, 237, 209, 166 (padded to 288, 5 times
288 is 1440, not over 1536, one more would go over), the second being just
the one event at 108. Lines 231 to 234 call `block_row_ce` for each block,
accumulating "per-row cross-entropy times weight" in the numerator and
weight in the denominator, and line 242 returns the weighted average --
this is `val_ce`. Line 237 switches back to `model.train()`. The demo's
four evaluations give `val_ce` in order 11.9023, 11.9013, 11.9006, 11.9003.

Lines 1160 to 1161 decide whether this evaluation also generates: with
`--gen-eval-at last`, only the evaluation where `frac` equals `E` (the end
of the epoch) generates, so it happens once per epoch. Line 1165's cgen cell
uses `train_causal_callgen.eval_gen`: lines 313 to 314 temporarily switch
padding side to left and turn on the kv cache (both required for
generation), lines 316 to 320 batch `--gen-bs` (2) rows at a time,
tokenizing `text + CALL_SEP` and left-truncating to `max_len - 96`, line 322's
`model.generate` greedily generates up to 96 new tokens (`MAX_GEN_TOK`),
stopping at eos, lines 326 to 329 decode the newly generated part, take the
first line stripped of leading/trailing whitespace, and compare it character
by character against the target string, counting a match as a hit. Lines
330 to 332 restore the padding side and cache setting, returning the hit
rate. All 4 rows miss in the demo, so `val_exact_call` is 0.0; the record's
`gen_n` is 4 and `gen_s` is the seconds spent generating.

## Stop 14: save best/ whenever val_ce hits a new low

Location: `pipeline/train/train_causal_share.py:1176` to 1206.

Line 1176: `vce < best`, and `best` starts at positive infinity, so the first
evaluation always saves. Lines 1179 to 1185: with LoRA off,
`model.save_pretrained(out / "best")` writes `config.json`,
`generation_config.json`, `model.safetensors`, and `tok.save_pretrained`
writes the tokenizer's four files. Lines 1186 to 1204 write `meta.json`,
recording the backbone, data directory, seed, epoch, `frac`, `gstep`, the
three batch settings, and the attention implementation. Line 1205 writes the
`save_best` record. The demo's four evaluations get a lower `val_ce` each
time, so all four save, and `best/` ends up as the weights after step 4,
with `meta.json`'s `epoch` 1, `frac` 2, `gstep` 4.

## Stop 15: the done record and heartbeat wrap-up

Location: `pipeline/train/train_causal_share.py:1208` to 1211.

Writes the `done` record: `best_val_ce` 11.9003, `best_ep` 1, `best_frac` 2,
`total_rows` 122 (61 rows each for two epochs), `wall_s` is the seconds from
line 1065 to line 1208 (5.41 and 5.63 seconds across the two runs). The last
heartbeat line carries `status="done"`. The program ends.

## The cparam cell and the cgen cell differ in only five places

Selecting the second configuration in launch.json is the cparam cell, the
same trainer, `--mode cparam`. The difference is in these five places.

The first is in `share_data.py:270` to 278: the tail is
`param_prompt_tail(label)`, equal to `CALL_SEP + label + "("`
(`train_causal_param.py:89`); the target string is
`param_target(label, label_call)` (`train_causal_param.py:94`), which strips
`label + "("` off the front of `label_call`, and takes what remains,
including the closing paren, as the target; rows that cannot be stripped are
dropped and counted in `assembly_mismatch`. In other words, the cparam cell
puts the tool name in the prompt and only learns the arguments. The second
is in `train_causal_share.py:1017` to 1018, where the target-length ceiling
takes `train_causal_param.MAX_TGT_TOK`, the same value, 160. The third is at
lines 1165 to 1166, where generative evaluation uses
`train_causal_param.eval_gen` (`train_causal_param.py:235`), building the
prompt with `param_prompt_tail`, and comparing the tuple's 5th field, the
argument string. The fourth is in the alignment check at lines 712 to 714,
where the reference path uses `ParamDS`, and lines 725 to 726 additionally
check the `assembly_mismatch` count. The fifth is in the records: the
`start` record gets two extra `assembly_mismatch` fields (lines 1057 to
1059), and `meta.json` gets one extra `param_only` field (lines 1201 to
1202).

## The fake artifacts are built by prepare.py using the annotate stage's real functions

Reading the trainer does not require reading `demo/prepare.py`, but these
four functions are worth a look if you want to know where every field in the
fake data comes from. `_synth_event` (`demo/prepare.py:135` to 153) randomly
picks a task, a tool, and zero to two turns of history, and strings together
a stretch of thinking whose first sentence restates the task and whose last
sentence names the tool. `make_rows` (lines 156 to 175) follows
`pipeline/annotate/build.py`'s `make_samples` field by field: cut points use
`rules.boundaries`, the prompt uses `rules.assemble`, the call string uses
`build.make_call`, and `w` equals 1 divided by the number of cut points.
`write_data` (lines 178 to 195) uses seed 20260907 to write 12 training
events and 6 validation events. `write_model` (lines 198 to 223) builds a
two-layer, hidden-64 model with `Qwen3Config`, randomly initialized via
`from_config` after `torch.manual_seed`, and saves it together with the real
tokenizer. `self_check` (lines 226 to 256) loads the fake artifacts once
using the trainer's own `build`, `load_events`, and `chunk_by_budget`,
printing the lengths and block counts.
