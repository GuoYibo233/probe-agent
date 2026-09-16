# Replay evaluation -- bfcl
- Temperature T=1.522
- 226 test events; frequency-prior baseline 0.049

- **Risk<=0.1** theta=0.725: coverage 0.8894 (CI (0.8313, 0.9498)), trigger accuracy 0.8955 (CI (0.8488, 0.9333)), earliness 0.6897 (CI (0.6291, 0.751)), wrong-speculation rate 0.0929
- **Risk<=0.05** theta=0.95: coverage 0.5929 (CI (0.4862, 0.6912)), trigger accuracy 0.9925 (CI (0.9759, 1.0)), earliness 0.6152 (CI (0.5655, 0.6708)), wrong-speculation rate 0.0044

## Depth-bucket acc (sample-level, diagnostic)
{"0.0": 0.729, "0.1": 0.731, "0.2": 0.751, "0.3": 0.801, "0.4": 0.789, "0.5": 0.799, "0.6": 0.826, "0.7": 0.841, "0.8": 0.861, "0.9": 0.868}

## Stop-time calibration (first firing point)
{"0.9-1.0": {"n": 134, "mean_conf": 0.975, "acc": 0.993}}

## Speculation economics conversion (T4 offline estimate, basis aligned with the T10 fork control)
| basis | theta | expected token-saving ratio (truncation) | expected overlap-latency ratio (prefetch) |
|---|---|---|---|
| test risk<=0.1 | 0.725 | 0.6134 | 0.5388 |
| test risk<=0.05 | 0.95 | 0.3648 | 0.3608 |

calB, all theta values:
| theta | tokens saved | overlap latency |
|---|---|---|
| 0.5 | 0.7046 | 0.5846 |
| 0.525 | 0.6967 | 0.5778 |
| 0.55 | 0.6846 | 0.5734 |
| 0.575 | 0.6774 | 0.5707 |
| 0.6 | 0.6705 | 0.5753 |
| 0.625 | 0.6648 | 0.5777 |
| 0.65 | 0.6591 | 0.5734 |
| 0.675 | 0.6397 | 0.5699 |
| 0.7 | 0.6319 | 0.5679 |
| 0.725 | 0.6257 | 0.5644 |
| 0.75 | 0.6127 | 0.5583 |
| 0.775 | 0.6059 | 0.5515 |
| 0.8 | 0.594 | 0.5401 |
| 0.825 | 0.5752 | 0.5343 |
| 0.85 | 0.5615 | 0.5208 |
| 0.875 | 0.5454 | 0.5093 |
| 0.9 | 0.53 | 0.4955 |
| 0.925 | 0.4875 | 0.4583 |
| 0.95 | 0.4417 | 0.4208 |
| 0.975 | 0.3843 | 0.3695 |
