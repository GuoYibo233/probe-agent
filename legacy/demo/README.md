# demo: step through the trainer with a debugger on CPU

## This directory is for watching the trainer run step by step on a machine with no GPU

The trainer under study is `pipeline/train/train_causal_share.py`, the
cache-reuse trainer shared by the cgen and cparam cells. Cache reuse means:
an event's (one step in a trajectory, with several cut points, each cut point
one row of sample) full text passes through the model only once, and each
row's target segment is appended after the shared prefix to compute loss, so
the same prefix is not recomputed across rows. Real training loads a Qwen3
backbone from 0.6B to 4B and reads a 1.2 GB `train.jsonl` on NFS, neither of
which is suited to waiting inside a debugger.

The trainer itself has not had a single character changed. The trainer
already left two doors open: `--base` given a directory path goes through
`build(path=...)` to load a model from any directory, and `--device cpu`
touches no GPU. The demo just swaps out what is behind those two doors:

- The model is swapped for `demo/tiny_qwen3/`: a randomly initialized Qwen3
  with two layers, hidden size 64, 9.78 million parameters (the
  `9780928 params` printed by `prepare.py`), whose tokenizer is copied from
  the real Qwen3-0.6B-Base. The structure is the same family as the real
  backbone, so both `model.model` and `model.lm_head`, which the trainer
  needs, are present.
- The data is swapped for `demo/data/train.jsonl` and `demo/data/val.jsonl`:
  synthetic AppWorld-style samples, 12 events / 61 rows in the training set,
  6 events / 27 rows in the validation set. Fields match the real data
  one-for-one; cut points use `rules.boundaries`, the prompt uses
  `rules.assemble`, and the call string uses `build.make_call` -- all three
  are the real functions from the annotate stage, only the trajectory
  content is authored.

Both fake artifacts are built by a single `demo/prepare.py` command, with a
fixed seed, so rebuilding produces the same files. Per the project's iron
rule, big artifacts go straight to net storage: `prepare.py` makes
`demo/tiny_qwen3` and `demo/runs` symlinks pointing at directories of the
same name under
`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/demo/`, the same
approach as `pipeline/data` and `pipeline/runs`, so home keeps only code,
the data jsonl, and the symlinks.

"The code for training" here means this line currently in service (the
cache-reuse trainer shared by cgen / cparam). The same fake artifacts can
also be pointed at the ctool cell's `train_causal_tool.py`, but that script's
`--base` only accepts the three names qwen / qwen17 / qwen4 -- that script
would need this `path=` door added first.

## Two commands run the whole demo

The first command builds the fake artifacts, done in ten seconds (the
tokenizer is copied from NFS, the model is written to net storage):

```
python3 run.py demo-prep
```

The second command enters the debugger. `.vscode/launch.json` has three
configurations; in VS Code's Run and Debug panel, select "demo: train cgen on
CPU (tiny model)" and press F5 to start; to watch the cparam cell, select the
second configuration instead. Both configurations set `CUDA_VISIBLE_DEVICES`
to empty, so the process sees no GPU at all. The whole run (the alignment
check plus two epochs of training) finishes in 15 seconds on shiga. The
`"type": "debugpy"` in the config needs the current Python Debugger
extension; if the extension is too old, changing `"type"` to `"python"` works
too.

To watch the trainer run through once without entering the debugger:

```
python3 run.py demo-train --mode cgen --out demo/runs/cgen
```

The trainer refuses to train again when the `--out` directory already has a
`train_log.jsonl`; this gate prevents two runs' artifacts from mixing into
the same `best/`. A second run needs `--force`; the two training
configurations in launch.json already carry `--force`, so F5 can be pressed
repeatedly.

## Every argument exists to exercise some layer of the training loop

launch.json and `demo-train` use the same set of arguments:

- `--epochs 2 --eval-per-epoch 2`: two epochs, evaluated twice per epoch, so
  the evaluation points, saving best, and reshuffling with a new seed for the
  next epoch all get exercised.
- `--events-per-mb 4 --accum 2` (the trainer's defaults): the 12 training
  events are cut into 3 logical minibatches, one parameter update per 2
  logical minibatches, so one epoch is 2 updates, the second update has only
  1 logical minibatch, `n_g` goes from 2 to 1, and the not-a-full-group
  branch gets exercised.
- `--tok-budget 768`: a logical minibatch's 4 events are packed into blocks
  by concatenated length; at a budget of 768, epoch 0's three logical
  minibatches each split into 2 physical blocks (the `[2, 2, 2]` printed by
  `prepare.py`; epoch 1 reshuffles, and the block count can differ), so the
  layer of "one logical minibatch splits into several physical blocks,
  gradients accumulate" is not left idle.
- `--log-every 1`: every update writes one step-log line.
- `--gen-eval 4 --gen-bs 2`: the end-of-epoch evaluation additionally runs
  generative evaluation on 4 rows; generative evaluation calls
  `model.generate`, so the generation path is exercised too.
- `--align-events 3`: the pre-training alignment check draws 3 validation
  events.

## Breakpoints go on these ten functions, in main()'s order

To read from the first line, in execution order, see
`demo/WALKTHROUGH.md`: that walkthrough has 15 stops, and each stop gives the
line numbers, what those lines do, what values show up when stopped on the
fake artifacts, and which key to press. The ten functions below are the
short version of the walkthrough.

Line numbers will drift, function names will not, so set breakpoints by
function name:

1. `train_causal_callgen.build`: loads the tokenizer and model. In the demo,
   `--base` is a directory path, taking the `path=` branch.
2. `run_align_check`: the pre-training alignment check. The same validation
   events go through both the new path (`_new_forward`, one packed forward
   pass) and the reference path (`_ref_forward`, the old trainer's row-by-row
   forward pass), and the per-row loss diff must be under `--align-tol`. If
   not, `sys.exit(2)`, with the report written to `ALIGN_CHECK.json`.
3. `share_data.load_events`: loads one split. Groups by event, tokenizes the
   full text, computes each row's common prefix length `p` against the full
   text, and concatenates the target segment `seg_ids` / `seg_lab`. An event
   is `dict(event, n_full, packed_len, prefix_len, full_ids, rows)`, and each
   row in `rows` is the seven-tuple
   `(sent_idx, text, p, seg_ids, seg_lab, w, gen)`.
4. `share_data.epoch_minibatches`: one epoch shuffles events with the seed
   plus the epoch number, 4 events per logical minibatch.
5. `share_data.chunk_by_budget`: one logical minibatch is greedily packed
   into blocks by a token budget, each block being one physical block.
6. `share_data.pack_event` and `share_data.batch_mask`, called inside
   `_forward_packed`: concatenates one event into a single sequence (the
   shared prefix plus each row's target segment) and builds the attention
   mask. `batch_mask` returns a `mask` shaped `[B, 1, L_pad, L_pad]`, an
   additive mask where visible positions are 0 and invisible positions are
   negative infinity; `loss_idx` is the (batch index, query position, target
   id, row number) for each target token. This masking step is exactly where
   the cache-reuse trainer differs from the row-by-row trainer.
7. `backward_logical_minibatch`, calling `block_row_ce`: one physical block's
   forward pass, per-token CE aggregated per row, weighted per row, then
   backward.
8. `clip_grad_norm_`, `opt.step()`, `sch.step()` inside `main()`: one
   parameter update.
9. `eval_ce` and `train_causal_callgen.eval_gen`: the full weighted CE over
   the validation set, and the end-of-epoch generative evaluation.
10. `model.save_pretrained(out / "best")`: saved whenever val_ce hits a new
    low.

The most direct way to see the mask is to stop at `batch_mask`'s return, and
for the first event run `(mask[0, 0] == 0).int()`, which gives the 0/1 matrix
of "which token can see which token."

## A few branches on CPU differ from GPU

Do not treat the following as bugs when you see them:

- `_attn_ctx` returns an empty context on CPU; `sdpa_kernel([EFFICIENT_ATTENTION])`
  only takes effect on cuda.
- `amp` is False, `torch.autocast("cuda", enabled=False)` is a no-op, and the
  mask uses fp32.
- `_peak_gb` is always 0 on CPU, so `peak_mem_gb` in the step log stays 0.0.
- The bf16 coarse-screening step in the alignment check only runs on cuda;
  `bf16_mean_abs_diff` in `ALIGN_CHECK.json` is null.
- The model is randomly initialized, so the loss and val_ce values are
  meaningless -- only the flow through the code matters.

## Artifacts live on net storage, and reappear when rebuilt after deletion

`demo/runs/<mode>/` holds `train_log.jsonl`, `ALIGN_CHECK.json` and `best/`,
structured the same as real-training artifacts; it does not enter the repo,
the matrix, or the ledgers. `demo/tiny_qwen3` and `demo/runs` are symlinks,
with the real files in the mirror directory on net storage, and both symlinks
are in `.gitignore`; deleting them and rerunning `demo-prep` brings them back.
`demo/data/*.jsonl` is checked into the repo, so samples can be read in an
editor without running any script.
