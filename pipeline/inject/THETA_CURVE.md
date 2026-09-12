# theta sweep curve: token savings vs. correctness

- 6 points, theta from 0.5 to 0.95
- miss_policy = skip
- 2138 events total (every tool-call event in the test segment)

> **Token-saving ratio = the deployment ledger**: the numerator is the total
> tokens actually saved in the inject segment; the denominator is the total
> tokens across **every fired event** in the nofill segment. An event that
> fired but predicted wrong, and so was not injected, saves 0 tokens but still
> counts in the denominator -- the cost of the probe guessing wrong is not
> allowed to be erased from this axis.
> **The correctness axis measures call agreement** (whether the whole
> predicted call matches the real one), **not task-level success**.
> Adoption rate = the continuation went off and did something else (meaning it
> swallowed the injection); re-call rate = the injected tool got called again
> anyway.
> **skip basis**: a wrong prediction is not injected, so the cost of a wrong
> guess never enters the **injected content** ledger (it only enters the
> token-saving denominator).

## Main table

| theta | coverage | fired | injected | token-saving ratio (deployment) | total tokens saved | mean saved per injection | median per injection | saving positive | tool match | full call match | adopted | re-called | late-fire share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.5 | 0.9097 | 1945 | 670 | -0.01041 | -42776 | -63.8 | 0 | 0.497 | 0.6607 | 0.3445 | 0.6239 | 0.3224 | 0.0955 |
| 0.7 | 0.8036 | 1718 | 717 | -0.00796 | -25096 | -35.0 | -15 | 0.4742 | 0.7509 | 0.4173 | 0.6067 | 0.3473 | 0.1688 |
| 0.8 | 0.7175 | 1534 | 724 | -0.03605 | -93718 | -129.4 | -29 | 0.4544 | 0.8044 | 0.472 | 0.6257 | 0.3343 | 0.2017 |
| 0.875 | 0.5968 | 1276 | 736 | -0.01397 | -29206 | -39.7 | -27 | 0.4592 | 0.8621 | 0.5768 | 0.6318 | 0.337 | 0.2636 |
| 0.925 | 0.4963 | 1061 | 686 | -0.10299 | -144259 | -210.3 | -40 | 0.4344 | 0.9057 | 0.6466 | 0.6297 | 0.3367 | 0.2697 |
| 0.95 | 0.4242 | 907 | 626 | 0.00446 | 5969 | 9.5 | -37 | 0.4233 | 0.925 | 0.6902 | 0.6326 | 0.3163 | 0.2684 |

## The two lines on the main figure (x-axis is coverage)

| coverage | theta | token-saving ratio | call agreement rate |
|---|---|---|---|
| 0.9097 | 0.5 | -0.01041 | 0.3445 |
| 0.8036 | 0.7 | -0.00796 | 0.4173 |
| 0.7175 | 0.8 | -0.03605 | 0.472 |
| 0.5968 | 0.875 | -0.01397 | 0.5768 |
| 0.4963 | 0.925 | -0.10299 | 0.6466 |
| 0.4242 | 0.95 | 0.00446 | 0.6902 |

## Is timing worth learning (same batch of fired events, only the firing moment changes)

> All three columns are on the deployment-ledger basis with the same
> denominator. **Current** = inject when the prediction is correct;
> **depth threshold** = only inject at a certain fraction into the thinking
> segment (a ready-made signal, nothing to learn); **oracle timing** = only
> inject, after the fact, on events that truly save tokens (the ceiling of
> perfect timing).
> Ratio reached vs. the ceiling = current / oracle timing. The lower this
> column is, the more room a timing head has.

| theta | current | depth threshold (best cut point) | oracle timing | ratio reached | injections that lose tokens | saved | lost |
|---|---|---|---|---|---|---|---|
| 0.5 | -0.01041 | 0.02726 (depth<0.2) | 0.11168 | -0.0932 | 337/670 | 459132 | 501908 |
| 0.7 | -0.00796 | 0.02255 (depth<0.15) | 0.15969 | -0.0498 | 377/717 | 503616 | 528712 |
| 0.8 | -0.03605 | 0.0354 (depth<0.15) | 0.17766 | -0.2029 | 395/724 | 461921 | 555639 |
| 0.875 | -0.01397 | 0.05202 (depth<0.45) | 0.25448 | -0.0549 | 398/736 | 532094 | 561300 |
| 0.925 | -0.10299 | -0.00584 (depth<0.25) | 0.2945 | -0.3497 | 388/686 | 412526 | 556785 |
| 0.95 | 0.00446 | 0.09709 (depth<0.85) | 0.34318 | 0.013 | 361/626 | 459180 | 453211 |

## Serving-side control (same theta, same plan, only the serving condition rerun)

> Greedy continuation has numeric jitter under changes in server-side batch
> composition (this known bias is already listed in replay_inject.py's file
> header). This table measures exactly that jitter: same theta, same plan,
> rerun against a different batch of servers, how much the token-saving ratio
> differs. **This difference is the curve's noise floor** -- swings on the
> curve smaller than it cannot be read as a real trend.

| theta | main curve token-saving ratio | control token-saving ratio | diff | main curve call agreement rate | control call agreement rate | control source |
|---|---|---|---|---|---|---|
| 0.875 | -0.01397 | -0.03533 | -0.02136 | 0.5768 | 0.5768 | aw_gptoss_th0875_h100 |
| 0.925 | -0.10299 | -0.0653 | +0.03769 | 0.6466 | 0.6466 | aw_gptoss_th0925_h100 |
| 0.95 | 0.00446 | -0.14834 | -0.15280 | 0.6902 | 0.6902 | aw_gptoss_th095_h100 |

**Noise floor for the summed metric = 0.15280** (the largest absolute diff
among the control pairs, 3 pairs total).

### Per-metric: noise floor vs. main-curve span

> Noise floor = the largest absolute diff between the two runs at the same
> theta, across the three control pairs (only the serving condition changed).
> Span = the max minus the min of this metric across the six points on the
> main curve.
> **A metric whose noise floor >= its span cannot go into the main figure** --
> everything it measures is jitter.

| metric | noise floor | main curve span | span/noise | plottable |
|---|---|---|---|---|
| token-saving ratio (summed) | 0.1528 | 0.1075 | 0.7x | **no** |
| median tokens saved | 7.0000 | 40.0000 | 5.7x | yes |
| saving positive | 0.0258 | 0.0737 | 2.9x | borderline |
| call agreement rate | 0.0000 | 0.3457 | infx | yes |
| adoption rate | 0.0122 | 0.0259 | 2.1x | borderline |
| runaway rate (not injected) | 0.0199 | 0.0302 | 1.5x | **no** |
| runaway rate (injected) | 0.0177 | 0.0259 | 1.5x | **no** |

> Criterion: the span must be at least 3x the noise to be readable, 2-3x is
> borderline, under 2x is unreadable.
