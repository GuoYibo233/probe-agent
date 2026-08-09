# Slide copy, English draft (15 pages), v3

Changes from v2 (user's revision round, 2026-08-10):
old P3+P4 merged; old P12 (θ calibration) dropped; old P7 two bullets deleted;
old P9 rewritten as text-only descriptions; old P10 rewritten as a process;
old P13 now carries the θ-selection statement; old P17 injection bullet expanded.
Page numbers below are the new ones (15 total). Old→new: 5→4, 6→5, 7→6, 8→7,
9→8, 10→9, 11→10, 13→11, 14→12, 15→13, 16→14, 17→15.

Fixed glossary (use everywhere, slides and figures): coverage / precision /
confidence threshold θ / majority-class baseline / reasoning prefix /
sentence boundary / earliness / ablation.

---

## Page 1 — Title

**Predicting an Agent's Next Tool Call from Partial Reasoning**
*A lightweight probe predicts the tool call before the reasoning is finished — work-in-progress report*

(name, group, date)

---

## Page 2 — Agents and tool calls

Bullets:
- An agent solves a task in steps: **reason → call a tool → observe the result → continue reasoning**.
- Each step ends in one tool call; everything before it is reasoning text.

Example-box caption:
- *One real step: a long reasoning segment (truncated) ending in a single call, e.g. `apis.supervisor.show_profile(...)`*

---

## Page 3 — Reasoning is expensive (merged: ReAct + cost)

Bullets:
- Tool agents follow the **ReAct** pattern: reasoning text makes the plan, actions get information from the environment. (Yao et al., 2022, arXiv:2210.03629)
- Median reasoning length per step: **2,991 characters** (gpt-oss-120b) vs **292** (qwen3.6-27b).
- One evaluation run over 168 AppWorld tasks: **3.3M–5.7M tokens**.
- Some single steps reach the **8,192-token** generation limit.

---

## Page 4 — From overthinking in chat to agents

Bullets:
- Prior work studies overthinking in chat and math settings: many reasoning tokens are spent on easy problems. (Chen et al., 2024, arXiv:2412.21187)
- We study the same cost problem in the agent setting.
- Key difference in the agent setting: **the next tool call is a classification problem over a fixed tool set**, not open-ended generation.

Footnote:
- *Classification has a trivial baseline: always predicting the most frequent tool. All results are compared against this majority-class baseline.*

---

## Page 5 — Toolformer: inserting API calls into text

Bullets:
- A language model can learn where to insert an API call in the middle of text, and how to use the returned result in the following text. (Schick et al., 2023, arXiv:2302.04761)
- Our question: can a **separate small model** predict the call before the agent writes it out itself?

---

## Page 6 — Our method: a probe that reads the reasoning prefix

Bullets:
- A small probe model (**1/20–1/34** of the agent model's inference cost) runs alongside the agent.
- At each sentence boundary, the probe reads plain text: task description + recent history + reasoning prefix.
- When the probe's confidence exceeds a threshold **θ**, it outputs a prediction of the next tool.

---

## Page 7 — Setup: 2 tasks × 2 agent models

Grid-cell labels (number of test events):
- AppWorld × gpt-oss-120b: **2,138** · AppWorld × qwen3.6-27b: **3,150**
- ALFWorld × gpt-oss-120b: **3,497** · ALFWorld × qwen3.6-27b: **2,146**

Bullets:
- Official task splits (AppWorld: 90 train / 57 validation / 168 test tasks).
- Data is split by task, so no task appears in both training and test.
- All models are run with vLLM; one probe is trained per task × model pair.

---

## Page 8 — The two tasks and two models

Task descriptions (text only, no numbers):
- **AppWorld**: the agent operates phone apps (email, shopping, music, …) through API calls to finish everyday tasks — many distinct tools, each with its own arguments.
- **ALFWorld**: the agent acts in a text-described household (go somewhere, pick something up, put it down, …) to complete chores — few action types, repeated often.

Models:
- **gpt-oss-120b** and **qwen3.6-27b**.

---

## Page 9 — From trajectories to training data (as a process)

Bullets (in order):
1. Run the agent on the training tasks and record complete trajectories.
2. Take every tool-call step; the reasoning text before the call is the raw material.
3. Cut that reasoning text at sentence boundaries; each prefix becomes one training sample (at most 64 per step).
4. Label each sample with the tool that was actually called at that step.

Note line:
- Sample text = task description + last 3 turns of history + reasoning prefix.

---

## Page 10 — Probe training

Bullets:
- Qwen3-0.6B-Base, full fine-tuning, with a linear classification head over tool names.
- One forward pass per event, with supervision at every sentence-boundary position.
- Each position is weighted 1/mᵢ, so the training distribution matches deployment, where the probe is queried at every sentence boundary.
- Learning rate 1e-5 · 3 epochs · max length 4,096 with left truncation (the end of the reasoning is kept) · fp32 weights with bf16 computation · fixed random seed.
- Baseline probe: ModernBERT-base (150M), same procedure.

---

## Page 11 — Main result: precision and coverage

Lead bullet (carries the θ-selection statement):
- **We choose θ on a validation split so that precision reaches ~0.95, then freeze it.** Coverage is what remains: the fraction of events where the probe is still confident enough to predict.

| Task | Model | θ | Coverage | Precision | Majority-class baseline |
|---|---|---|---|---|---|
| AppWorld | qwen3.6 | 0.925 (risk 0.1) | 29% | 0.937 | 0.159 |
| AppWorld | gpt-oss | 0.975 | 30% | 0.951 | 0.404 |
| ALFWorld | qwen3.6 | 0.5 | 100% | 0.944 | 0.548 |
| ALFWorld | gpt-oss | 0.95 | 94% | 0.947 | 0.470 |

Footnote:
- *The AppWorld × qwen3.6 row uses the 0.90 precision target (no θ reached 0.95); all other rows use the 0.95 target. Precision is computed only on events where the probe made a prediction.*

---

## Page 12 — Precision–coverage trade-off over θ

Axis/series labels:
- x: confidence threshold θ (0.5 → 0.95)
- series 1: coverage (0.91 → 0.42)
- series 2: tool-name accuracy (0.66 → 0.93)

Bullet:
- Higher θ: fewer predictions, higher accuracy. θ is chosen according to the acceptable error rate.

Corner note:
- *AppWorld × gpt-oss. Numbers come from a different evaluation run than page 11 (here θ = 0.95 gives 0.925; there θ = 0.975 gives 0.951).*

---

## Page 13 — How early the prediction happens, and what it depends on

Bullets:
- Earliness **0.58–0.84** (higher = earlier): predictions happen well before the reasoning is finished.
- Ablation: removing the reasoning text from the input drops the calibration-split weighted accuracy from **0.613 to 0.421** (AppWorld). The prediction depends on the reasoning text, not on the task description alone.

Footnote:
- *The ablation was run on an earlier dataset version with the ModernBERT probe: the direction of the effect is the result; absolute numbers are not comparable to page 11.*

---

## Page 14 — Summary of current results

Center sentence:
> **On 30%–100% of events (depending on the task), the next tool can be predicted with ≥ 94% precision, well before the reasoning is finished.**

Small pointers: precision and coverage (p.11) · trade-off over θ (p.12) · earliness and ablation (p.13)

---

## Page 15 — Future work: three directions

Bullets:
- **Injection**: execute the predicted call early and feed it back to the agent — where to insert it (into the ongoing chain of thought, or elsewhere in the context), and whether to hand the model the tool result before it asks for it.
- **Predicting the arguments**: beyond the tool name — extract argument values from the text, or fix the tool name and let the agent model write the arguments.
- **Tool types**: handle read-only and state-changing tools differently — early execution is safe for read-only tools, not for state-changing ones.

Wording note (not on slide): describe these as "directions we explore next",
not "not tried yet" — offline injection experiments exist but are outside this talk.
