# What experiment settings the old phase used

Source: `DATA.md` (the data-settings ledger) in the pre-wipe snapshot `b1f5b9c`. This file only carries over facts, it adds no judgment.

## Three agent models were probed, all served locally

| Short name | Model | Serving mode |
|---|---|---|
| q35 | qwen3.5-27b | vLLM raw mode, template assembled by hand, thinking segment not dropped |
| q36 | qwen3.6-27b | vLLM raw mode; Mamba hybrid architecture, `--max-num-seqs` had to be lowered to 256 |
| gptoss | gpt-oss-120b | vLLM chat mode, thinking taken from `message.reasoning` |

Zero paid APIs, everything ran on the tokyo105 to 108 cards.

## The test bed went through two generations, the numbers from the two are not comparable

The first generation was self-split: three environments, AppWorld, TALES (a cooking text game), and BFCL
(multi_turn_base, 200 questions), with the data version going from v2 to v3_1 (v3 folded in an extra batch of
collection beyond v2, v3_1 only rebuilt BFCL to fold in the 200 gpt-oss entries). The second generation switched to
the official problem sets:

- `aw_official_v1`: the AppWorld official split, train 90 / val 57 / test_normal 168 task instances, one dataset per
  model, the three models' problem sets match exactly set by set (so same-question comparison holds).
- `alf_official_v1`: the ALFWorld official directory mapping (train takes a stratified sample of 200 configurations /
  val 140 / test 134), two copies for q36 and gptoss, matching problem sets.
- `bfcl_mtb_v1`: BFCL's new-pipeline dataset (the one the ro1 batch used throughout), split 140/40/20. The old
  `DATA.md` §8.3 admits it never got around to writing up how this dataset was built.

One correction worth noting (found by the old `DATA.md` §8.2's own self-check): the TALES settings written in §1.1
(seed 101 to 120, two difficulty tiers) were an exploration batch, not one of which entered the training data; what
actually went into the data was the `full_v1` batch (seed 31 to 50, 40-step cap), and that batch had "all three
models at 0% win rate."

## How trajectories become training samples

The rule has not changed since it was finalized on 2026-07-29 (fixed at the top of `build_dataset.py`):

- The agent finishes a task and leaves one trajectory; every step in the trajectory that calls a tool is one event.
- One event is cut into prefixes at the sentence boundaries of its thinking text, each prefix is one sample, capped
  at 64 (over the cap, sample evenly, the last one is always kept). A sentence boundary is defined as a newline, or
  `.!?` followed by whitespace.
- Sample text = task description + `[HISTORY]` segment (last 3 turns, each environment return capped at 400
  characters) + `[THINKING]` prefix.
- Label = the tool name actually called at this step, fully automatic with no manual work.
- Every event carries equal weight in the training loss (`w=1/m_i`). Reason: in deployment the probe is asked once
  at every sentence boundary, so the training distribution should be aligned to the deployment distribution.
- The split is done by task instance, so the trajectories of the same question under different models move together
  into the same split, to prevent sibling leakage.
- Events whose thinking is shorter than 40 characters are dropped outright. Samples over 4096 tokens are left-
  truncated by the training script.
- Seeds are fixed across the board: data 20260729, training 42 or 20260729 (check the seed column in RESULTS row by
  row).

## The evaluation protocol has three steps, on the ledger called "calA fit temperature, calB scan θ, test freeze"

The data is cut into four splits (train 70% / fit-temperature 10% / threshold-scan 10% / test 10%; in the
official-split era, splits followed the official problem sets). Step one fits a temperature for the probe's
confidence on the fit-temperature split; step two scans the threshold-scan split for a θ that satisfies the risk
constraint (the risk0.1 tier requires trigger accuracy no lower than 90%, the risk0.05 tier no lower than 95%); step
three reports the frozen θ on the test split. The passing bar is beating the frequency prior baseline.

## The frequency prior baseline moves with the data, check the table before citing a number

The prior baseline is defined as: the accuracy on the test split of "always guess the most frequent tool in the
training set."

| Dataset | Test-split event count | Prior baseline | Most frequent tool |
|---|---|---|---|
| v2 appworld | 305 | 0.226 | `apis.api_docs.show_api_doc` |
| v2 tales | 201 | 0.672 | `open` |
| v2 bfcl | 237 | 0.038 | `startEngine` |
| v3 appworld | 791 | 0.298 | same as above |
| v3 tales | 408 | 0.556 | `open` |
| v3 bfcl | 226 | 0.049 | `startEngine` |
| v3_1 bfcl | 335 | 0.042 | `startEngine` |
| aw_official_v1 q35 side | 3356 | 0.174 | `apis.api_docs.show_api_doc` |
| aw_official_v1 q36 side | 3150 | 0.159 | same as above |
| aw_official_v1 gptoss side | 2138 | 0.404 | same as above |
| alf_official_v1 q36 side | 2146 | 0.548 | `go` |
| alf_official_v1 gptoss side | 3497 | 0.470 | `go` |

Two sourcing warnings (both are verbatim from the old `DATA.md` §3.1 and §3.2):

1. gptoss's thinking text is long (median 2991 characters per step, versus 292 for q36), so its cut points pack
   densely close to the 64 cap; that is why it has the fewest events but the most samples. Comparing models by
   sample count gives a counterintuitive conclusion, comparisons should be by event count.
2. gptoss's prior baseline is high (AppWorld 0.404 / ALFWorld 0.470); reading absolute accuracy overrates the probe
   on the gptoss side.

## Read-only folding (a sourcing convention added by the ro1 batch, 2026-08-01)

Speculation only fires on read-only tools. The ground-truth table was manually reviewed tool by tool: of AppWorld's
183 tools, 100 are read-only (read-only events are 80.0% of the total), of BFCL's 106, 57 are (51.3%); any
login/authentication tool is ruled non-read-only across the board. Folding does not change the data files: the
vocabulary becomes "read-only tools + a trailing sentinel `<NON_READONLY>`," and evaluation triggering adds one more
condition, "argmax is not the sentinel." ALFWorld's read-only events are only 4.6%, this scheme is not applied to it.
