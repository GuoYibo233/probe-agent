# The order direction decisions happened in, and what engineering incidents came up along the way

Source: `TIMELINE.md` (the decisions verbatim) in the snapshot `b1f5b9c`, and the relevant `RESULTS.md` entries. The
parenthetical after each item is the run_id or commit that triggered it.

## The decision line (earliest to latest)

1. 2026-07-29: set up version control and the three-layer recording system (before this, the code side was
   completely disconnected, the code versions behind the old results could not be recovered).
2. 2026-07-29: the v2 three-way training run was voided, the bf16 hard-training precision defect meant the update
   magnitude at lr 2e-5 was below bf16 weight resolution, the model was effectively frozen; after the fix, the A/B
   smoke-test accuracy differed by 19x (0.156 versus 0.008).
3. 2026-07-29: the fixed version passed verification, the speculation gate opened for bfcl (`20260729_2235`).
4. 2026-07-30: v3 final review, the speculation gate opened only for bfcl; appworld and tales were ruled "adding
   data cannot save it" (`20260730_0814` / `20260730_1645`).
5. 2026-07-30: the causal-probe ruling, the probe backbone was switched to Qwen3-0.6B-Base, and appworld's gate
   opened; the "too-short a window is the root cause" hypothesis was voided (`20260730_1716_bert_t8_causal`).
6. 2026-07-30: the cross-model matrix settled the deployment conclusion, swapping the agent model on bfcl only
   needs redoing calibration; the mixed-training ceiling's gain is in coverage, not in accuracy
   (`20260730_1713` / `20260730_1835`).
7. 2026-07-30: the full-history baseline established the motivation for selective memory (the c3 line,
   `20260730_fig1_fullhist_8b`).
8. 2026-07-31: all twelve c1 cells wrapped up, the causal head replaced the classification head as the main line,
   the AppWorld official split became the standard test bed; a fourth layer, `DATA.md`, was added to the recording
   system.
9. 2026-08-01: the offline-injection timing experiment, the dead zone was reproduced for the first time in a real
   agent environment (`20260801_0113_inject_aw_gptoss_r10`).
10. 2026-08-02: the eight-arm splice-back wrap-up, skel_switch (transition plus skeleton) was set as the primary
    form of truncate-and-splice-back (`20260801_2257_inject_aw_gptoss_splice`).
11. 2026-08-02: the ro1 batch wrapped up, read-only plus the abstention class went live; the co-trained firing head
    was ruled below standard.
12. 2026-08-02: the six-arm live-run wrap-up (v1), the probe won within the same framework; both effort control
    routes were ruled dead ends; static sharding was ruled dead and changed to dynamic task claiming.
13. 2026-08-02: after the stop-token fix, v2 was re-run, v1's absolute values on both arms were voided, and the
    ledger records the probe's winning conclusion as "reinforced."
14. 2026-08-02: the c2 batch wrapped up, ALFWorld was brought in, the "few tools, many parameters" counter-case was
    established.
15. Late night, 2026-08-02: the wipe, all old-phase experiments were terminated, about 116G of NFS artifacts were
    deleted, the four ledgers were zeroed out and rebuilt (carried out after the snapshot commit `b1f5b9c`).
16. 2026-08-08: the probe line restarted, its characterization changed from "a fixed method" to "an experiment
    space," `METHOD.md` was established as the source of truth for the method (the first entry in the current
    `TIMELINE.md`).

## Engineering incidents and silent failure points (usable for the engineering-story slide, all on the ledger)

- The bf16 hard-training defect: the update magnitude at the chosen lr was below weight resolution, the model was
  effectively frozen but training still finished normally and produced a report. The symptom was a flat depth curve
  at 0.26 and confidence pinned to the floor. The fix was fp32 weights plus autocast.
- A disk-quota hollow checkpoint: when the home quota was full, `model.safetensors` had an apparent size of 598MB
  but occupied only 1.0MB (0%) on disk, `torch.load` raised no error, the training log still wrote done, the
  evaluation exit code was 0, no link in the whole chain complained. The only place it showed was that the
  evaluation report's coverage was 0.000 across all 20 θ values. This established a new gate: verify the
  checkpoint's actual disk blocks at the end of training.
- The stop-token bug (live run v1): gpt-oss only stops on `<|return|>`, and once the final segment ended with
  `<|end|>` it fabricated a new turn that contaminated content; 1235 of 2157 steps on v1's no-fire arm were
  contaminated. The fix included 9 unit tests.
- A harmony parsing 500: when thinking is especially long the server-side parser fails to clean up, the exception
  propagates up and drops every remaining seed in the whole shard. The fix was 4 client-side backoff retries.
- A BFCL thinking-text false negative: the thinking lives in the top-level `reasoning_content` field of the result
  (list[list[str]]); looking for it under the assistant entry in `inference_log` returns an empty list, which
  misdiagnoses "this batch has no thinking."
- An ALFWorld syntax break: from 0.4.0 on, `put X in/on Y` changed to `move X to Y`; using the old syntax gets
  `Nothing happens.` on every placement action, silently. The countermeasure is to not hardcode the action template
  in the prompt, and instead have the model copy verbatim from `admissible_commands`.
- Nondeterministic ordering in the dataset-building script: the recursive glob's return order was nondeterministic,
  combined with dedup by id, the event count drifted between 2265 and 2267 across two rebuilds. After fixing it to
  `sorted(glob)`, v3_1 did two rebuilds and byte-for-byte compared them.
- Static sharding: the fattest 10% of questions accounted for 19% of generation with zero success, one question
  could stall a whole shard. Changed to dynamic task claiming with mkdir as an atomic ticket.
