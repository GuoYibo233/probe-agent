# TIMELINE — why we changed direction

Newest first. Append only. `WORKPLAN.md` is what to do now; `jobs/RESULTS.md` is the numbers.
Before 2026-08-20: `plans/archive/` ("ancient memory"), read only when gyb asks.
Entries were shortened on 2026-09-25; the full text is in git.

## 2026-09-20 The from-zero rewrite replaces the old tree

- **Decision:** the old tree (~60 Python files) becomes the 31-file tree of
  `plans/2026-09-14-structure-from-zero.md` (interfaces: `plans/2026-09-17-contracts.md`).
  Six stages, one command (`run.py`), one experiment = one setting, run directories named by
  key, `--debug` runs any setting tiny, `eval/` reads only disk.
- **Retired:** the resident sampler and its web page, incident agents, autopsy, the
  one-refire quota, the old `run.py` task registry, `MAP.md`, `ops/jobs.json`, `RUNMETA.json`,
  presets, offline replay, the chat-endpoint collection path, the five non-AppWorld
  environments.
- **Old numbers** keep their old provenance. The old tree is at tag
  `checkpoint-2026-09-17-before-from-zero`.
- **Accepted by:** `--debug` walks of all three workflows and `run.py selfcheck` with 0 problems.

## 2026-09-12 The whole repo is translated to English

- **Decision:** one pass over everything, ledgers and archive included, as a one-time
  exception to the append-only rules.
- **Kept in Chinese:** skill and agent trigger phrases, and the original term after each
  glossary entry.

## 2026-09-12 research-loop moves to its own repository

- **Decision:** research-loop leaves new1 for `/home/y-guo/research-loop`. History up to new1
  commit `c030702` stays here.

## 2026-09-12 Ancient memory: everything before 2026-08-20 is archived

- **Decision:** `plans/archive/` is read only when gyb says so or names a file. The seven
  TIMELINE entries from 2026-08-02 to 08-18 moved there unchanged.

## 2026-09-12 The injection format becomes an experiment axis

- **Why:** gyb wants to test how a prefetched result is put back. Old single-step results
  were dropped: "we only care about the final result".
- **Decision:** four arms, placement (`p1` inside the thinking, `p2` after it as a message
  from `prefetch`) × explanation (`e1` inline each time, `e2` once in the system prompt).
  The call always runs in a saved-then-restored world. Scoring is whole-task success and
  token cost only. `p2` relaxes METHOD R1/R2 for this experiment.

## 2026-09-05 research-loop v2 skeleton built in one day

- Five parallel sessions built the plugin skeleton (109 files, 250 tests green). Moved out
  of this repo on 2026-09-12.

## 2026-08-29 Second round of the new trainer: open items become switches, cgen LR sweep

- **Decision (gyb):** sweep the learning rate; skip flex_attention; make every other open
  item a parameter with the recommended value as default.
- **Sweep:** cgen, four configurations × three rates. Lowest val_ce: full-parameter 1e-5,
  LoRA 5e-4. An extra 2e-6 point confirmed 1e-5 for full-parameter. The default LR stays
  unchanged until gyb compares.
- **Memory (16384 token budget, whole-run step peak):** b17 1.7B full, no grad checkpoint,
  H200: 102.336 GB; b06 0.6B full + grad checkpoint, Ada: 22.427 GB; l17 1.7B LoRA, H200:
  81.655 GB; l4 4B LoRA + grad checkpoint, H100: 33.088 GB.

## 2026-08-28 Training switches to the cache-reuse trainer

- **Why:** the row-by-row trainer recomputed every prefix (one 1.7B LoRA cell: 98 h).
- **Decision:** an event's full text goes through the model once, and each cut's target is
  scored against the shared prefix. No truncation: an event over 8192 tokens is dropped
  whole. 8 events per update. cgen/cparam 1 epoch, ctool 3. Batch prefix `ks828`.
- **Result:** 16× faster than the old trainer. Alignment check max diff 5.48e-6.
- **Memory (H100, 93.10 GiB):** cgen at 16384 budget: allocated peak 60.59 GB (56.4 GiB),
  final whole-run peak 58.47 GB. At 24576: 80.9 GB and 15% slower. ctool 8192 × bs 4 OOMs on
  the first batch; bs 2 peaks at 56,859 MiB (nvidia-smi).

## 2026-08-28 One generation convention for everything

- **Decision (gyb):** collection, live arms and controls all use one setting: harmony,
  effort high, temperature 1.0, top_p 1.0, 8192 tokens, date 2026-08-06, seeds from 42 / 67 /
  4267 / 6742. Arm differences are averaged out over many tasks.
- Temperature-0.0 results from 2026-08-18 are comparable only within their own batch.

## 2026-08-22 np821 cut cap stays at 64

- **Why:** 64 keeps the training split at ~4× p1's, inside the budget. 128 would add 49%.
  The cap thins evenly and keeps the last cut; it can be raised later by rebuilding on CPU.

## 2026-08-21 np821 convention: temperature 1, 4 trajectories per task, weight 1 per cut

- **Decision (gyb):** temperature 1.0; all 315 AppWorld tasks × 4 trajectories; weight 1 per
  cut is the long-term default; seeds 42 / 67 / 4267 / 6742. Four training batches: 0.6B
  full, 1.7B full, 1.7B LoRA, 4B LoRA.
- Temperature-1 numbers are not comparable with temperature-0 numbers.

## 2026-08-21 The p1 temperature-0 convention is closed

- p1 data stays unchanged, used only to reproduce the acceptance line. No new batches on it.

## 2026-08-21 First training round: 0.6B and 1.7B full-parameter, LoRA on small cards

- **Decision (gyb):** main line full-parameter with fixed hyperparameters (lr 1e-5,
  3 epochs, batch 32); base-model size is the only variable. A separate LoRA line runs on the
  48G cards, because z1's test found 0.6B full-parameter OOMs on 48G.

## 2026-08-21 Three probe types × three sizes; the ModernBERT line stops

- **Decision (gyb):** stop mtool/mext. Causal probes only, at 0.6B / 1.7B / 4B. Three types:
  ctool (tool only), cgen (whole call), cparam (arguments given the tool, new).
- **Why cparam:** cgen and cparam share data and ground truth, so their gap measures only
  whether the tool name is given.

## 2026-08-20 Generation settings move into config files

- **Why:** settings were scattered over five places with different values.
- **Decision:** model paths and generation settings are chosen by name from config files,
  never hard-coded in `.py`. (Replaced on 2026-09-20 by `experimental_settings/` and
  `models/table.yaml`.)
