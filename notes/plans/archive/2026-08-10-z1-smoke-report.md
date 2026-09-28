# z1 smoke acceptance report: all three METHOD.md §5 lines passed

2026-08-10. Batch plan: `plans/2026-08-10-z1-plan.md`. This report states only
facts. The output has been deleted per the user's instruction (deletion list
at the end); the numbers' original source is the z1 output before deletion,
and the key intermediate numbers have been transcribed into this report and
into `RESULTS.md`.

## Pipeline facts (from scratch to the live run)

| Segment | Facts |
|---|---|
| Collection | 20 tasks (train 12 / dev 4 / test_normal 4), gpt-oss-120b, `--api harmony --reasoning-effort high --start-date 2026-07-31`, about 44 minutes total, token count in 1,308,335 / out 475,082. 20/20 trajectories carry a final record |
| Annotation | 219 events / 8,572 samples / a 7-tool vocabulary; the three splits are 5,656 / 1,432 / 1,484; 9,420 parameter-annotation lines, found_rate 0.894; gates A/B/D pass, E skipped per the official task set; call-chain read-back 219/219 |
| Training | ctool and cgen both hit a CUDA OOM on the tokyo105 A6000 (48G); `--refire` to the tokyo108 H100 (95G) got them running: ctool 4 minutes (best calA_weighted_acc 0.6199), cgen 69 minutes (best_val_ce 0.2344, val_exact_call 0.69) |
| Evaluation | eval-tool-causal produced the REPLAY_REPORT: temperature 1.8227, chosen_theta {0.10: 0.75, 0.05: 0.775}, val trigger scan over 36 events |
| Live run | theta=0.65 manual (at that point in the val scan, coverage 0.64 / trig_acc 0.74), the first 2 test_normal tasks (3d9a636_1/2), max-steps 30, three arms run serially |

## §5 three acceptance lines

**(i) every fire identifiable by five items: passed.** After the fix, the
probe arm fired 10 times (7+3). The spec record carries all of them: which
step (step), which cut (cut, thinking-text coordinate), how confident (conf,
e.g. 0.711), what was predicted and what executing it returned
(pred_label + gen_call + exec_out + exec_ok, with one case at step=4 where
exec_ok=False, so the "note the error too" branch actually ran), and what was
injected (the full NOTE text). In the gen record for the same step, the NOTE
sits inside the thinking and the model can be seen continuing to write after
it (sample continuation opening: "We also need phone app API docs.").

**(ii) R3 token comparison: passed, 10/10.** For every injection event, the
whole refired string after injection was reconstructed; vLLM's
`prompt_token_ids` read-back of the server's tokenization matches the
openai_harmony re-encoding bit for bit, the longest string being 11,091
tokens. Before the fix, the first pass was likewise 13/13 (this check
measures the refired string's self-consistency, unrelated to the render
convention gap).

**(iii) empty-injection control: numbers below, whether the variance is
tolerable is a human call.** chat path vs the `--no-probe` arm on the same 2
tasks: 3d9a636_1 identical for the first 2 steps, diverges at step 2;
3d9a636_2 identical for the first 3 steps, diverges at step 3. At both
divergence steps, the prompt token count is exactly the same between the two
arms (1456, 5418); the divergence position is a single word mid-generation,
after an identical prefix ("prints" vs "will return"). This matches the
phenomenon in `learn/vllm/lessons/0004` (greedy decoding is not reproducible).
The two arms agree on task pass/fail (both tasks success=False, the same
kind of failure content).

## Two real problems the smoke test caught and fixed

1. **`/render` differs from the chat baseline by 2 characters (fixed in
   commit `99e538f` plus a rework, "character-error fix")**: `build_prefix`
   goes through the model's jinja template, and line 248 of the template
   inserts `\n\n` between the developer body and `<|end|>`; the chat
   endpoint's harmony renderer and the collection code's hand-assembled
   string both lack it (hcap has verified the two are otherwise
   bit-for-bit identical). Fix: after rendering, strip only that one
   trailing spot at the end of the developer segment. Before the fix, both
   (iii) tasks first diverged at step 0; after the fix, `/render` and the
   chat server's rendering are byte-for-byte identical (1533=1533), and
   first divergence moves back to step 2/3. The first submitted regex wrote
   `\1\2` as `\1\3` (`/render` 500), verified locally by running
   build_prefix, then reworked; none of the 124 unit tests cover
   build_prefix, this test gap is recorded here.
2. **probe_server `/health` echo bug (fixed in the same commit)**: `config()`
   echoed the module constant's default path (`c1_*`, which no longer
   exists), not the path actually loaded; loading itself always used the
   real argument (the z1 server's temperature 1.8227 is verifiable only from
   the z1 report). After the fix, the real path is echoed.

## Incidental runtime facts

- The vLLM server took 306s / ~120s to become ready across two launches (the
  NFS compile cache was warm).
- The sampler's incident chain fired for real for the first time: both
  training OOM deaths were judged "dead" and written into
  `incidents.jsonl` (together with an earlier manual kill of mth_datepin,
  3 entries in total); the incident agent failed to start in every case
  because cron's environment PATH could not resolve `claude`
  (`spawn_error`, recorded as is), matching the gap predicted in
  `ops/gpu_state.md` word for word.
- Training the gptoss trajectories on ctool/cgen (no fire-head, default
  hyperparameters) OOMs directly on a 48G A6000, runs on a 95G H100; wider
  than the skill's recorded finding that "OOM only happens with fire-head's
  double forward pass."
- Collection/training heartbeats, `launch --refire`, and `--service` liveness
  checks all went through their full chain on a real task.

## Deletion list execution record

Deleted per the user's instruction (commands at the end of the file); kept:
this report, the batch plan, the config, the `RESULTS.md`/`runs.jsonl`
records, and the two fix commits.
