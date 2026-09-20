# 53 Theta is chosen by comparing a four-decimal display rounding against the risk target

Status: needs-triage
Severity: minor
File: eval/utils/probe_eval.py:366
Contract: 1.4 ("`chosen` follows today's rule: the theta with the largest coverage among those whose `trig_acc >= 1 - risk` and whose coverage is above zero")
Errata: not recorded

## Finding

`_agg` rounds every statistic it returns to four decimals, for the report:

```python
    return {
        "n": n,
        "coverage": round(float(coverage), 4),
        "trig_acc": round(float(trig_acc), 4),
```
(`eval/utils/probe_eval.py:280-283`)

`grid` stores those rounded numbers (`grid.append({"theta": theta,
**_agg(recs)})`, `:360`), and the risk constraint is then tested on them:

```python
    chosen: dict[str, float | None] = {}
    for risk in cfg.eval.risk:
        candidates = [e for e in grid if e["trig_acc"] >= 1 - risk and e["coverage"] > 0]
        chosen[str(risk)] = max(candidates, key=lambda e: e["coverage"])["theta"] if candidates else None
```
(`eval/utils/probe_eval.py:364-367`)

So the decision that picks the frozen theta is taken on the display value on
one side and on the full double `1 - risk` on the other.

## Failure scenario

`eval.risk` is a free list of floats in the setting file. For `risk: [0.18]`,
`1 - 0.18` is `0.8200000000000001` (measured with this repo's interpreter; the
same holds for 0.41, 0.42 and 0.43 in the range 0.01 to 0.50).

Take a val crossing with 50 events, all 50 fired, 41 of them correct at
`theta = 0.6`. Its true trigger accuracy is exactly 0.82, which is the risk
target: `_agg` reports `trig_acc: 0.82` and the test reads `0.82 >=
0.8200000000000001`, which is False. That theta is dropped. If 0.82 is the best
trigger accuracy the grid reaches, `chosen["0.18"]` is null, `frozen` gets no
entry for the target, `report.md` prints "no theta on the grid met the
constraint" for a target one grid point meets exactly, and every generator eval
that takes its theta from that report writes `n: 0` and three null exact-match
numbers for that risk (1.4's null-theta rule).

The rounding also runs the other way: a true trigger accuracy of 0.949951
rounds to 0.95 and is accepted at `risk: 0.05`, so `frozen` reports the test
numbers at a theta whose val accuracy missed the target. That half needs more
than 20,000 fired val events to reach, since the rounding moves the value by at
most 5e-5.

## Proposed fix

Choose on the number and round for the report. Have `_agg` return the
unrounded `coverage`, `trig_acc`, `earliness` and `wrong_spec`, and round them
where the report is assembled — the `grid` entry at `:360` and the `frozen`
entry at `:381` — so the constraint reads the rate the crossing actually had.
State the comparison itself with the tolerance the double representation of
`1 - risk` needs (`trig_acc >= 1 - risk - 1e-9`), with the measured case
(`risk: 0.18` gives `0.8200000000000001`) named in a comment beside it, so a
theta that exactly meets its target is a candidate.
