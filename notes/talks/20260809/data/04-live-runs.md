# What each of the three live-run versions measured

Live run = the whole question run online: the agent does the task from scratch in AppWorld, the probe scores every
thinking cut in real time, and fires once it clears θ (predicts the call, executes it for real, feeds the result
back into the cut); success or failure is judged once the whole question finishes. The test bed is fixed as the
AppWorld official test_normal split, 168 questions × gpt-oss-120b, and every version has two arms: the probe arm
(fires for real) and the no-fire arm (the whole machinery is hooked up but it never fires once, what the current
vocabulary calls the no-probe control). The external anchor is w0 = the chat baseline's success rate, 0.2857
(48/168).

Source: the `RESULTS.md` entries `20260802_0136_live_aw_gptoss`, `live_aw_gptoss_v2`, `live_aw_gptoss_v3`,
`20260802_0240_live_aw_effort`, `20260802_0306_live_aw_probe_effort` in the snapshot `b1f5b9c`, and
`pipeline/inject/runs/live_aw_gptoss/{probe,noprobe}/LIVE_REPORT.md`.

## The main-line numbers across the three versions

| Version | What was fixed | Probe-arm success rate | No-fire-arm success rate | Billed tokens (probe/no-fire) | Injections per question |
|---|---|---|---|---|---|
| v1 (08-02 01:36) | none | 0.119 (20/168) | 0.0714 (12/168) | 5.32M / 5.72M (saves 7%) | 1.35 |
| v2 (08-02 05:47) | the stop-token bug | 0.190 (32/168) | 0.173 (29/168) | 3.35M / 3.92M (saves 14.7%) | 1.66 |
| v3 (08-02 17:45) | the commentary parsing | 0.238 (40/168) | 0.268 (45/168) | 3.47M / 3.56M (saves 2.4%) | 1.46 |
| v4 (08-02 20:22 launched) | made logic-isomorphic with the w0 chat path | was running at the wipe, no wrap-up numbers | same as left | - | - |

What the two fixes were: v2 fixed the stop-token bug where gpt-oss only stops on `<|return|>`, and once the final
segment ended with `<|end|>` it fabricated a new turn that contaminated content (after the fix, contaminated steps
went from 1235/2157 on v1's no-fire arm to 0/4692, and questions hitting the 64k context wall went from 27 versus 39
to 0 on both arms). v3 fixed the parsing of the commentary channel.

## Each version's verbatim conclusion on the ledger (copied from the RESULTS conclusion column)

- v1: "within the same live-run framework the probe wins across the board: success rate 11.9%>7.1%, tokens saved
  7%, 12 fewer questions hit the 64k cap; but the framework itself is not yet aligned with w0 (after excluding
  cap-hitting questions, 9.3% vs 31.8%), the absolute-value basis still needs fixing."
- v2: "after the stop-token fix, v2: probe arm 32/168 vs no-probe 29/168, billed tokens still save 14.7%, under the
  same framework the probe costs no accuracy and purely gains tokens; both arms recover substantially from v1
  (20/12) but are still below w0's 28.6% (greedy-decoding chaos plus answer padding, already attributed, not a
  bug)."
- v3: "after the commentary fix: noprobe 45/168 falls inside w0's noise band (a chat re-run today reproduces 28.6%
  at 47+/166); probe arm 40, token savings shrink to 2.4%, v2's double win included a bonus from the broken
  framework; the remaining one-sided gap = answer padding (ADD 55 versus a baseline noise of 9, 22 questions are
  pure bad luck), suspected cause = a segment seam or a pre-fill, np1shot_fp and v4 are verifying it."

The live-run line stopped at the wipe on v3's open question: the probe arm is 5 questions behind the no-fire arm;
the ledger attributes the one-sided gap to the probe arm's answer-padding failures (the ADD class is 55 questions
against a baseline noise of 9, 22 questions the ledger calls "pure bad luck"), the suspected cause named is a
segment seam or a pre-fill, and the job of verifying it was handed to v4, which never finished running.

## The fine-grained accounting of fire quality (v1 probe-arm LIVE_REPORT)

Across 226 fires, the execution success rate is 0.9867 (only 1 error is AttributeError, 2 are http_422); the
predicted tool name matches the step's real call 0.1947 of the time, the whole call matches 0.1195 of the time. At
v2 the execution success rate is 0.9892 (279 fires); at v3 the tool-name match rate is 0.1878 (245 fires).

## The effort control: numbers for two alternative routes (same batch as v1)

Turning gpt-oss's reasoning effort down from high to save tokens: the low tier's success rate is 0.0655 (11/168),
the med tier's is 0.0714 (12/168), against the high tier's w0 of 0.2857; med spends 2.6 times the tokens of low
(1.37M versus 0.52M). Ledger conclusion: "saving tokens cannot be done by turning effort down."

Taking the probe trained on the high tier and using it directly on the low tier: at the low tier it almost never
fires (0.06 times per question, the 10 fires it does make all get the tool name wrong but do no harm), the score is
0.0893, slightly above the low baseline of 0.0655; at the med tier it fires often (0.72 times per question) but the
tool name is only right 0.2893 of the time, dragging the score down to 0.0476, below the med baseline of 0.0714.
Ledger conclusion: "both θ and the probe must be calibrated per effort tier, moving them across tiers directly
hurts the score."
