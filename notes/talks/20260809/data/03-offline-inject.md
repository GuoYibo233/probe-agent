# What the offline injection experiments measured

Offline injection = replaying an already-collected trajectory to a given step, inserting the predicted call and its
result at the thinking cut, letting the model keep writing from there, and measuring how many tokens that saves
going forward and whether the injection is adopted. All of it was done on AppWorld × gptoss, 2138 events, triggering
with ctool's θ.

Source: `pipeline/inject/runs/aw_gptoss_r10/INJECT_REPORT.md`, `aw_gptoss_th*/INJECT_REPORT.md`,
`aw_gptoss_splice_th0925/INJECT_REPORT.md` in the snapshot `b1f5b9c`, and the corresponding entries in `RESULTS.md`.

## The timing experiment: injection is adopted, but token savings depend strongly on injection depth (run `20260801_0113_inject_aw_gptoss_r10`)

Basis: risk=0.1, θ=0.925, 1061 events triggered, 689 injectable. The control arm nofill is a replay built the same
way, truncated the same way, differing only in the injected line. The two arms overall:

| Arm | n | Median tokens saved | Share with positive savings | Re-called the injected tool | Advance rate |
|---|---|---|---|---|---|
| nofill | 1061 | 0 | - | 0.8812 | 0.0971 |
| inject | 689 | -27 | 0.4514 | 0.3396 | 0.6168 |

Advance rate 0.62 versus 0.10, re-call rate 0.34 versus 0.88, are the direct numbers behind "the injection is
adopted by the model." Bucketed by trigger depth (the share of thinking already written when firing), the inject
arm's mean tokens saved:

| Depth bucket | n | Mean tokens saved |
|---|---|---|
| 0.0 to 0.2 | 362 | +377.7 |
| 0.2 to 0.4 | 93 | +14.0 |
| 0.4 to 0.6 | 47 | +284.5 |
| 0.6 to 0.8 | 33 | -635.8 |
| 0.8 to 1.0 | 154 | -696.8 |

Of the fires the probe triggers by confidence, 21.8% fall in the worst bucket, 0.8 to 1.0. TIMELINE calls this batch
of numbers "the first reproduction of the dead zone under a real agent environment driven by a real probe."

## θ scan: the working characteristics at six points; the summed-basis token savings are ruled uninterpretable (run `20260801_0407/0413` series)

| θ | Trigger ratio | Whole-call match rate | Tool-name match rate | Median tokens saved | Oracle-timing ceiling | Adoption rate |
|---|---|---|---|---|---|---|
| 0.5 | 0.9097 | 0.3445 | 0.6607 | 0 | 0.1117 | 0.6239 |
| 0.7 | 0.8036 | 0.4173 | 0.7509 | -15 | 0.1597 | 0.6067 |
| 0.8 | 0.7175 | 0.472 | 0.8044 | -29 | 0.1777 | 0.6257 |
| 0.875 | 0.5968 | 0.5768 | 0.8621 | -27 | 0.2545 | 0.6318 |
| 0.925 | 0.4963 | 0.6466 | 0.9057 | -40 | 0.2945 | 0.6297 |
| 0.95 | 0.4242 | 0.6902 | 0.925 | -37 | 0.3432 | 0.6326 |

(The "oracle-timing ceiling" is the `oracle_timing_ceiling` field: the upper bound on the savings share if every
injection picked the optimal timing. "Adoption rate" is the `adopted` field.) The higher θ is, the more accurate the
whole call and the fewer the fires, a clean trade-off curve. But the "token savings share" on the summed basis at
all six points is marked uninterpretable: the noise floor measured by the serving-side control, 0.1528, is larger
than the full span across the six points, 0.1075; the root cause is runaway generation hitting the 8192 generation
cap (the same event can differ by 8161 tokens between two runs).

## Truncate-and-splice-back, eight arms: the tool-name-pinned transition arm wins (run `20260801_2257_inject_aw_gptoss_splice`)

This batch changed the main control: tokens saved are measured against the original trajectory (the tokens the
model actually spent writing from the cut to issuing the call on its own, at the time). Of the eight arms, four
skeleton arms are different phrasings of "the probe pins the tool name, the model only fills in the parameters":

| Arm | Median tokens saved | Share with positive savings | Description |
|---|---|---|---|
| skel_switch | +239 | 0.8935 | channel-switch bytes + fence + skeleton (the winning arm) |
| switch_only | +143 | 0.7512 | only switches channel, the whole call is written by the model itself |
| inject_stop | +181 | 0.6079 | SYSTEM NOTE injection + stop after the result |
| skel_bare | +69 | 0.6635 | a bare skeleton in the thinking segment |
| skel_a | +42 | 0.59 | thinking-segment skeleton phrasing A |
| skel_b | +27 | 0.591 | thinking-segment skeleton phrasing B |
| inject | +1 | 0.5 | SYSTEM NOTE injection (does not stop) |
| nofill | +3 | - | pipeline health-check arm (the whole batch's numbers are only cleared for release once nofill closely matches the original trajectory) |

skel_switch's skeleton completion rate is 1.0, its tool name is rewritten 0.0 of the time, and after completion it
still thinks for 0 more characters; the three thinking-segment skeleton arms are rewritten 11% to 13% of the time
and still think for 235 to 730 more characters after completion. On the execution side: the calls skel_switch sends
to real execution match the original trajectory's execution result at a rate of 0.728 (0.803 within the bucket where
the probe guessed the tool name correctly), overtaking switch_only, where the model writes the whole call itself
(0.538); the ledger's explanation is "pinning the tool name pulls the model back to the original trajectory's
behavior," noting that switch_only's low score is mostly reasonable deviation and a systematic underestimate.
Acceptance cross-check: the token-by-token acceptance arm has a whole-call exact-match rate of 0.128, the two
cross-check paths disagree at a rate of 0.126 (the measured scale of vLLM logprob jitter).
