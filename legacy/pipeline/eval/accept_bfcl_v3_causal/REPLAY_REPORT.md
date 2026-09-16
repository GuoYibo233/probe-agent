# Replay evaluation -- bfcl (causal probe, qwen)
- Temperature T=1.388
- 226 test events; frequency-prior baseline 0.049

- **Risk<=0.1** theta=0.8: coverage 0.8805 (CI (0.8265, 0.9321)), trigger accuracy 0.9347 (CI (0.9006, 0.9672)), earliness 0.6826 (CI (0.6295, 0.7397)), wrong-speculation rate 0.0575
- **Risk<=0.05** theta=0.925: coverage 0.8009 (CI (0.7381, 0.8679)), trigger accuracy 0.9779 (CI (0.9487, 1.0)), earliness 0.5596 (CI (0.4973, 0.6189)), wrong-speculation rate 0.0177

## Depth-bucket acc (sample-level, diagnostic)
{"0.0": 0.771, "0.1": 0.804, "0.2": 0.801, "0.3": 0.872, "0.4": 0.877, "0.5": 0.887, "0.6": 0.895, "0.7": 0.918, "0.8": 0.938, "0.9": 0.924}

## Stop-time calibration (first firing point)
{"0.9-1.0": {"n": 181, "mean_conf": 0.963, "acc": 0.978}}

## Speculation economics conversion (T4 offline estimate, basis aligned with the T10 fork control)
| basis | theta | expected token-saving ratio (truncation) | expected overlap-latency ratio (prefetch) |
|---|---|---|---|
| test risk<=0.1 | 0.8 | 0.601 | 0.5579 |
| test risk<=0.05 | 0.925 | 0.4482 | 0.4339 |

calB, all theta values:
| theta | tokens saved | overlap latency |
|---|---|---|
| 0.5 | 0.7302 | 0.5902 |
| 0.525 | 0.7187 | 0.58 |
| 0.55 | 0.7102 | 0.5846 |
| 0.575 | 0.7055 | 0.583 |
| 0.6 | 0.6969 | 0.582 |
| 0.625 | 0.6914 | 0.5787 |
| 0.65 | 0.6895 | 0.5811 |
| 0.675 | 0.6783 | 0.5782 |
| 0.7 | 0.6676 | 0.5774 |
| 0.725 | 0.6611 | 0.5845 |
| 0.75 | 0.6533 | 0.5808 |
| 0.775 | 0.6416 | 0.5697 |
| 0.8 | 0.6234 | 0.5636 |
| 0.825 | 0.6 | 0.5462 |
| 0.85 | 0.5716 | 0.5254 |
| 0.875 | 0.549 | 0.512 |
| 0.9 | 0.5126 | 0.4821 |
| 0.925 | 0.4623 | 0.4382 |
| 0.95 | 0.3832 | 0.3695 |
| 0.975 | 0.2873 | 0.2873 |

## Probing cost (test, token compute to probe the entire trajectory)
- ModernBERT basis: bert_tokens=1722227 (rereads the prefix once per sentence boundary)
- Causal basis: causal_tokens=86784 (reads the whole event once)
- ratio=19.845x
- Basis: both sides count tokens with the qwen backbone's tokenizer, without
  max_len truncation; only tokens the probe reads are counted, not the agent's
  own generation.
