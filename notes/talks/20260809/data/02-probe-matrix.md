# Which probes were trained, and their accuracy

Source: `pipeline/runs/{MATRIX_REPORT,c2_MATRIX_REPORT,ro1aw_MATRIX_REPORT,ro1bf_MATRIX_REPORT}.md` (the risk-0.05-tier matrix) in the snapshot `b1f5b9c`, and the per-run entries in `RESULTS.md` (risk-0.1-tier numbers, numbers from the earlier ModernBERT era).

## Four kinds of probes were trained, called the four cells on the ledger

The four cells = two backbones times two tasks. Backbone one is ModernBERT-base (an encoder with about 150M
parameters), backbone two is Qwen3-0.6B-Base (a 600M-parameter causal language model).

- mtool: ModernBERT plus a classification head, reads the sample text, outputs a probability distribution over tool
  names.
- ctool: Qwen3-0.6B doing the same thing (called the causal head on the ledger), confidence is temperature-
  calibrated and fires once it clears θ.
- mext: a ModernBERT extraction head, locates the start and end span of parameter values in the text, evaluated only
  at mtool's trigger points.
- cgen: Qwen3-0.6B generates the whole call directly (tool name plus all parameters), evaluated only at ctool's
  trigger points.

The probe reads reassembled text (task + history + thinking prefix), re-encoded with its own tokenizer; it does not
read the agent model's internal state. Probing cost is one twentieth to one thirty-fourth of the probed model's
generation cost (the `cost_ratio` field in run `20260730_1716_bert_t8_causal` is 19.8 to 34.1).

Metric definitions: trigger ratio (coverage) = the share of all events in the test split where the probe's
confidence clears θ and it dares to fire; trigger accuracy (trig_acc) = the share of fired events where the tool
name is guessed correctly; earliness = how early or late the fire happens (a larger value means firing earlier);
full_call_ok = the share of triggered events where the whole call is entirely correct.

## The c1 batch: twelve cells on the AppWorld official split (2026-07-31)

The risk-0.05 tier (the matrix report's original table, cells with no solution left blank):

| Model | Cell | θ | Trigger ratio | Trigger accuracy | earliness | full_call_ok |
|---|---|---|---|---|---|---|
| q35 | mtool | no solution | - | - | - | - |
| q35 | ctool | 0.975 | 0.0653 | 0.968 | 0.3131 | - |
| q35 | mext | cannot be scored (upstream mtool has no trigger point) | - | - | - | - |
| q35 | cgen | 0.975 | - | - | - | 0.8904 |
| q36 | mtool | 0.975 | 0.0705 | 0.973 | 0.4841 | - |
| q36 | ctool | no solution (fell back to the 0.1 tier) | - | - | - | - |
| q36 | mext | 0.975 | - | - | - | 0.9324 |
| q36 | cgen | 0.925 (0.1 tier) | - | - | - | 0.8135 |
| gptoss | mtool | no solution | - | - | - | - |
| gptoss | ctool | 0.975 | 0.2961 | 0.951 | 0.6343 | - |
| gptoss | mext | 0.975 (0.1 tier) | - | - | - | 0.6755 |
| gptoss | cgen | 0.975 | - | - | - | 0.7852 |

The risk-0.1-tier addendum for the tool cells (from the RESULTS entries): q35_ctool 0.925 / 0.1642 / 0.9292;
q36_ctool 0.925 / 0.2911 / 0.9368; q36_mtool 0.925 / 0.1724 / 0.9208; gptoss_ctool 0.925 / 0.4963 / 0.9057;
gptoss_mtool 0.975 / 0.1239 / 0.8642, this cell is ruled on the ledger as "did not hold up" (below the 0.90 contract
line on test, the point picked on val did not hold up on test).

The batch's three conclusions on the ledger (the TIMELINE 2026-07-31 entry): the causal head wins across the board
(on the gptoss side the trigger ratio 0.4963 is 4.0 times mtool's 0.1239); the difficulty-transfer risk materialized
in one case (gptoss_mtool); the gap between the loose and strict verdicts only shows up on the extraction route (the
three cgen cells give identical numbers under both verdicts, the two mext cells differ, 0.9595 versus 0.8874 and
0.7887 versus 0.4377).

## The c2 batch: seven ALFWorld cells reported, one skipped (2026-08-02)

Prior baseline is 0.548 on the q36 side and 0.470 on the gptoss side (the single action `go` is half of them). The
risk-0.05 tier:

| Model | Cell | θ | Trigger ratio | Trigger accuracy | earliness | full_call_ok |
|---|---|---|---|---|---|---|
| q36 | mtool | 0.575 | 0.9995 | 0.9473 | 0.8287 | - |
| q36 | ctool | 0.5 | 1.0 | 0.9441 | 0.8359 | - |
| q36 | mext | 0.575 | - | - | - | 0.9259 |
| q36 | cgen | 0.5 | - | - | - | 0.7768 |
| gptoss | mtool | 0.95 | 0.5988 | 0.9355 | 0.5769 | - |
| gptoss | ctool | 0.95 | 0.9397 | 0.9467 | 0.5767 | - |
| gptoss | mext | 0.95 | - | - | - | 0.8324 |
| gptoss | cgen | deliberately skipped (training would take 85.1 hours, over the 12-hour wall-clock cap) | - | - | - | - |

The batch's conclusion on the ledger (the TIMELINE 2026-08-02 entry): even in a high-prior, low-tool-count
environment the probe still separates out (q36_ctool hits full trigger ratio at the lowest threshold, θ=0.5); the
gap between the causal head and ModernBERT is in coverage, not in discriminative power (at the same θ=0.95, trigger
ratio 0.9397 versus 0.5988, accuracy 0.9467 versus 0.9355); how much is saved is decided by the probed model's
thinking length (gptoss's thinking is ten times longer, earliness 0.577 versus q36's 0.83).

## The ro1 batch: AppWorld and BFCL after read-only folding (wrapped up 2026-08-02)

The risk-0.05 tier, AppWorld (prior after folding, q35/q36/gptoss = 0.2333/0.2584/0.4041):

| Model | Cell | θ | Trigger ratio | Trigger accuracy | full_call_ok |
|---|---|---|---|---|---|
| q35 | mtool | 0.975 | 0.0054 | 0.8889 | - |
| q35 | ctool | 0.95 | 0.0882 | 0.9831 | - |
| q35 | mext | 0.975 | - | - | 0.7647 |
| q35 | cgen | 0.95 | - | - | 0.8741 |
| q36 | mtool | no solution (fell back to the 0.1 tier) | - | - | - |
| q36 | ctool | 0.975 | 0.0905 | 0.986 | - |
| q36 | mext | 0.925 (0.1 tier) | - | - | 0.8687 |
| q36 | cgen | 0.975 | - | - | 0.9433 |
| gptoss | mtool | no solution | - | - | - |
| gptoss | ctool | 0.95 | 0.3606 | 0.9481 | - |
| gptoss | mext | 0.975 (0.1 tier) | - | - | 0.625 |
| gptoss | cgen | 0.95 | - | - | 0.7562 |

BFCL (prior after folding, 0.5167/0.5094/0.4679), all twelve cells have a solution at both tiers, the 0.05 tier:

| Model | mtool (θ/ratio/accuracy) | ctool (θ/ratio/accuracy) | mext full_call_ok | cgen full_call_ok |
|---|---|---|---|---|
| q35 | 0.875 / 0.25 / 0.9333 | 0.875 / 0.3167 / 0.9211 | 0.8276 | 0.75 |
| q36 | 0.95 / 0.3113 / 0.9697 | 0.8 / 0.4245 / 0.8889 | 0.9375 | 0.8571 |
| gptoss | 0.725 / 0.3303 / 0.8889 | 0.825 / 0.3394 / 0.8919 | 0.8529 | 0.9412 |

Safety numbers for the abstention class: the false-trigger rate on non-read-only events is no higher than 0.047
across the board on the BFCL side, and no higher than 0.016 on the AppWorld q35/q36 side; the only cell in the whole
batch to break 0.05 is ro1aw_gptoss_mtool (0.2295). The co-trained autonomous-firing head has no working point in 12
of its 14 parameter cells, firing accuracy is stuck between 0.72 and 0.86.

## The earlier ModernBERT self-split era (2026-07-29 to 30)

- bfcl v2fix (run `20260729_2235`): at θ=0.8, trigger ratio 0.7553 / accuracy 0.9441 / earliness 0.664; at θ=0.925,
  ratio 0.6203 / accuracy 0.966. Prior 0.038.
- appworld v3 final review (run `20260730_0814`): 0.1-tier ratio 0.19 / accuracy 0.933, no feasible θ at the 0.05
  tier. Ruled on the ledger as "the gate does not open under the 95% standard."
- tales v3 final review (run `20260730_1645`): 0.1-tier ratio 0.336 / accuracy 0.839, 0.05 tier 0.147 / 0.85.
  Attributed on the ledger to "the open action space."
- bfcl v3 re-split (run `20260730_0204`): accuracy 0.9925 / ratio 0.5929, the difference from v2fix falls within
  overlapping confidence intervals, split variance is about plus or minus 3 percentage points.

## The causal-backbone ruling and the cross-model matrix (2026-07-30)

- The causal probe (run `20260730_1716_bert_t8_causal`): appworld 0.05-tier accuracy 0.9621 / ratio 0.3338 (no
  solution for ModernBERT on the same cell); bfcl 0.9779; tales 0.9077 (tales's 0.1-tier θ transfer failed to hold,
  marked on the ledger as tales-specific). Trigger ratio across the three environments is 2.5 to 4.3 times higher.
- Cross-model (run `20260730_1713_bert_t6_xqwen`): bfcl in-domain 0.9748 / cold transfer 0.897 / recalibration alone
  recovers 0.971 (at half the trigger ratio); appworld's recalibration does not fully recover it; tales is weak
  across the board. The gptoss-side counterpart (`20260730_1716_bert_t6_xgptoss`): in-domain strength is bfcl 0.9623
  > appworld 0.9298 > tales 0.7551, tales's cold-transfer trigger ratio is 0.0.
- The bfcl mixed-training ceiling (run `20260730_1835`): qwen side 0.9645/0.7478, gptoss side 0.9157/0.7615, against
  a pure-qwen ceiling of 0.509/0.349, ledger conclusion "the gain is in coverage, not in accuracy."
- The extraction head wrap-up (run `20260730_1713_bert_t7_extractor`): bfcl's whole-call accuracy at the trigger
  moment is 0.9179 (the ledger benchmarks this against the competing SPORK's 0.076), appworld can only attach 0.76 at
  the 0.1 tier; the ledger writes "the real bottleneck is that the value has not yet appeared at fire time
  (free-form-tier parameters have appeared only 0.235 of the time), not extraction itself."
- Signal decomposition (run `20260730_1713_bert_t5_ablation`): with the thinking removed, calibration-split weighted
  accuracy is bfcl 0.4381 / appworld 0.421 / tales 0.6054; the full-input baseline on the same metric is bfcl 0.7518
  / appworld 0.6133 / tales 0.6947 (run `20260730_0056_bert_probe_v3`, same v3 data, same script); with the history
  removed, bfcl is near flat at 0.982, appworld breaks the 95 line at 0.954 (these two are risk0.05-tier trigger
  accuracy, a different metric from the no-thinking ablation, not comparable side by side). The ledger's exact
  words: "history is harmful noise."
