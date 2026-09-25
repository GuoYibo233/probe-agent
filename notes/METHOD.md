# METHOD — speculative tool calls from a probe

What the method is. How to run it: `README.md` and the probe-pipeline skill.
Terms: `CONTEXT.md`. Numbers: `jobs/RESULTS.md`.

This is an experiment. The core loop is fixed. Everything else is an axis we try.
Whether it works is judged only by run numbers, never written here in advance.

## 1. Core loop

The agent model does a task step by step. At each cut in its thinking, the probe reads
the text so far. When the trigger rule fires, the probe writes the call, the call runs
early in a saved-then-restored world, and the call plus its result are written back into
the stream. The model continues from there.

Today: gpt-oss-120b on AppWorld, Qwen3-0.6B-Base probes. `sample` runs the loop without
the probe, `inject` runs it with the probe; both use `agent/run_tasks.py`.

## 2. Hard rules

**Same setup.** Baseline and method use the same model, server, sampling and decoding.
The method adds nothing the baseline lacks.
- Checked with the `no_probe` arm: all machinery wired, never fires. Score it against the
  baseline (`score.baseline`); a person judges the drift.
- Exact byte-equality is not expected. The server's prefix cache changes the numerical
  path, so greedy output can diverge at near-ties (measured 2026-08-18). Arms are
  compared over many tasks instead.

**Injected text behaves like the model's own text.**
- R1: `p1` formats write only inside the open thinking.
- R2: `p1` injected text carries no special tokens.
- R3: the stream after injection is still a legal harmony token sequence.
- `p2` formats close the thinking on purpose and so relax R1 and R2 (decided 2026-09-12).

**Scoring is whole-task.** Task success and token cost only; a single call is never
scored as right or wrong (2026-09-12).

## 3. Axes

| # | Axis | Today | Setting field | Open |
|---|---|---|---|---|
| 1 | What the probe reads | task + last tool rounds + thinking so far, as text (`data/probe_input.py`) | `build.hist_rounds`, `build.probe_result_cap` | read the agent model's hidden states |
| 2 | Probe model | Qwen3-0.6B-Base, full tuning | `models.probe`, `probe.tuning` | larger backbones, LoRA |
| 3 | Where the call comes from | cgen writes the whole call | `inject.probe_gen` | cparam (tool from ctool, arguments from cparam) |
| 4 | When to fire | ctool confidence ≥ θ, first cut that crosses | `inject.theta`, `inject.probe_score`; `eval.risk` freezes θ | `inject.fire_nth_cut` as a control |
| 5 | What is written back | one of five formats | `inject.format` (`p1_e1`, `p1_e2`, `p2_e1`, `p2_e2`, `note`) | — |
| 6 | How often | at most one injection per step | `inject.max_inject_per_step` | — |
| 7 | Tool type | read and write tools treated the same | — | treat them differently |
| 8 | When to stop probing in a step | cut cap, thinking closes, step token budget | `inject.max_cuts`, `generation.max_step_tokens` | — |

A fired call always runs; whatever comes back, errors included, is injected.

## 4. Acceptance check for a new mechanism

On a few tasks:
1. Every fire is fully visible in the task record: step, cut, confidence, predicted call,
   its result, the text injected, and what the model wrote next.
2. The stream after injection re-encodes to the same tokens.
3. `no_probe` against the baseline: a count of same vs. diverged steps, judged by a person.
