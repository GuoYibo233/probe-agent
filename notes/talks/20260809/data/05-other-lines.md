# What the other two research lines (memory, multi-hop injection) measured

These two lines were worked on in parallel with the probe line, and were terminated together at the wipe. The
numbers are still on the ledger, organized here for reference.

## The c3 memory line: is it worth stuffing past experience into the prompt

The test bed is ALFWorld, the model under test is Qwen3-8B (the pilot batch used 4B). Tasks are graded by
similarity, the canonical numbering: L2 = an identical question, L2⁻ = an almost identical question, L1 = the same
kind of question with different objects swapped in. Note that the original file names use a different numbering
that runs exactly reversed (in the code, L0 = canonical L2); the conversion table is in the old `DATA.md` §6.1.

### The full matrix of the arm that stores successful experience (mem) versus the one that does not (nomem) (run `20260728_fig1_8bfull`, 5 seeds × 10 episodes)

| Canonical tier | Success rate mem/nomem | Wall-clock change | Output tokens mem/nomem | Input tokens mem/nomem | Total token change |
|---|---|---|---|---|---|
| L1 partial similarity | 0.84 / 0.84 | -7% | 8288 / 8698 (saves 5%) | 13610 / 9605 (costs 42% more) | costs 20% more |
| L2⁻ near-duplicate | 1.00 / 1.00 | -12% | 3199 / 3634 | 5154 / 3519 | costs 16.8% more |
| L2 exact duplicate | 0.60 / 0.60 | -12% | 6133 / 6874 | 13973 / 15377 | saves 9.6% |

(The total token change is converted from the `total_tok_saving_*` field in the RESULTS row: the field is "the
share saved," a negative value means it costs more, e.g. L2⁻'s field value of -16.8% converts to "costs 16.8%
more.")

The ledger's reading (`fig1_pilot/ANALYSIS_8bfull.md`'s conclusion section, an interpretation on the ledger itself):
the core trade memory makes is spending cheap input tokens to save expensive output tokens, so a paper's accounting
must list input and output separately; storing only successful experience does not rescue the 40% of tasks the
model could not do in the first place; 8B's payoff is smaller than the pilot batch's 4B (wall-clock -12% versus
-31%).

### The full-history baseline (run `20260730_fig1_fullhist_8b`, 30 runs, 300 episodes, matched on the same card)

Stuffing the entire past into the prompt verbatim: for identical questions, success rate +32 percentage points,
total tokens ×0.84 (the saving is on the output side, output tokens -28%); for almost-identical questions, +2pp,
tokens ×1.17; for same-kind-different-object questions, +2pp, tokens ×2.50. Ledger conclusion: "the farther the
tier, the less full history pays off."
The verbatim-replay ceiling (run `20260730_oracle_ceiling_8bfull`): nonzero only on the exact-duplicate tier (saves
up to 21.0%), forming an upper and lower bound together with full history; the ledger writes "supports the
motivation for selective memory."

### How realistic the workload is (run `20260727_tracelab_simv0`)

In real coding-agent trajectories, 68.4% of adjacent tasks have similarity above 0.8, and within a 50-task window
96.1% are near-duplicates. Ledger conclusion: "repeated, similar tasks make up the bulk of real workloads."

## The C1 multi-hop injection line: feeding a tool result into the thinking early, timing is the key

The test bed is real multi-hop QA from HotpotQA / 2WikiMultihopQA plus a synthetic two-hop task, using the gold
passage as the tool result, with Qwen3-8B as the main model (two 4B generations serve as a protocol control).
Source: `hotpot_inject/FINDINGS.md` (two waves) and `oracle_inject/FINDINGS.md`.

### The dead zone reproduces across tasks

The synthetic lookup task (the oracle batch, 5 models × 60 questions): injecting at the opening saves 86 to 232
tokens, accuracy 0.98 to 1.00; injecting 25 to 50 tokens before the call point is net-negative and drops accuracy by
5 to 15 percentage points. The token-savings curve is non-monotonic, the ledger names this "the decision-zone dead
zone," and writes one warning aimed at the probe route, verbatim: "only injecting once confidence is high ≈
injecting close to the call point ≈ landing in the dead zone."

Real multi-hop (the Hotpot bridge type, 8B): opening injection saves +383, injecting 25 tokens early gives -215; the
same shape reproduces on 2wiki and on 4B; at temperature 0.6, three seeds re-run without flipping sign (run
`20260730_0413_hotpot_t11_var`, bridge -153±69). On the synthetic two-hop task the dead zone escalates from a token
loss to an accuracy collapse (at d=25 the injection accuracy drops from 1.00 to 0.67).

### The best action across the board is injecting all the evidence at the opening (both_start)

8B hotpot bridge: saves +457, accuracy +17pp; the comparison type's -18pp jump-the-gun toxicity from a
single-document opening injection is erased by "injecting both documents together" (-2pp, within the noise band).
Mixing in one irrelevant document costs nothing (the tray experiment: saves 454 versus 457, soft 0.69 versus 0.67).

### The cost table for being credulous

Injecting a wrong value: synthetic two-hop acc 0.00 (8B, the correct value at the same position gets acc 1.00);
injecting a distractor passage on the real task drops soft from 0.49 to 0.15 (-34pp), and it still "saves" +319
tokens. The ledger's exact words: "it short-circuits the thinking at the cost of a wrong answer." Whether
authorizing wording is necessary splits by model scale: 4B collapses on an unauthorized opening injection (acc
0.00), 8B's unauthorized curve nearly overlaps the authorized one.

### Protocol robustness is a property of the model

Baseline normal rate: Qwen3-8B 93% to 96%, Qwen3-4B (the previous generation) 92%, Qwen3.5-4B only 40% (48%
spontaneously derails into repetition). Ledger conclusion: "4B's finding is that it cannot handle injection at all,
only 8B's finding is actually about when to inject."
