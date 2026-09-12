# Group meeting slide-by-slide draft (17-page version)

> Note 2026-08-10: after the English copy was iterated to v3 in another session, the total page count changed to 15
> pages (old pages 3+4 merged, old page 12 dropped; the old-to-new page number mapping is at the head of the
> `SLIDES-text-en.md` file). `SLIDES-text-en.md` is the final version of record; this file keeps the 17-page
> structure as backing draft.
> Figure file names already follow the v3 new page numbers (`figs/`, the two retired figures are in `figs/unused/`).

Three lines of information per page: one-sentence summary, page elements (figure/table/bullets), number sources.
Number sources are all in the `data/` files.

## Background (pages 1 to 5)

### Page 1: title page
- One sentence: a probe predicts an agent's tool calls ahead of time, a piece of research in progress.
- Elements: title + name and date + a one-line subtitle (e.g. "training a small probe to predict, midway through the
  model's thinking, which tool it will call next").

### Page 2: what an agent and a tool call are (merged page)
- One sentence: each step of an agent is a loop of "think a bit, call a tool, look at the result, keep thinking."
- Elements:
  - Figure: loop diagram (thinking → tool call → environment result → back to thinking), four boxes in a ring.
  - Example box: one real trajectory step excerpt, a snippet of the thinking text (head and tail trimmed) plus the
    real call at the end (e.g. `apis.supervisor.show_profile(...)`), the thinking part shows an ellipsis to indicate
    its length.
  - The example is cut from an hcap trajectory (the only run in the current-phase RESULTS) or an old trajectory.

### Page 3: thinking is expensive
- One sentence: thinking tokens are long and expensive, and they are the largest share.
- Elements (three bullets, can pair with a comparison bar chart):
  - gptoss's median thinking length per step is 2991 characters, q36's is 292, a tenfold difference (the bar chart
    just draws these two bars).
  - Running the AppWorld 168-question set once costs 3.3M to 5.7M billed tokens per arm.
  - Thinking can also run away: some trajectories hit the 8192-token generation cap in a single step.
- Sources: `data/01-settings.md`, `data/04-live-runs.md`, `data/07-current-phase.md`.

### Page 4: related work, ReAct
- One sentence: ReAct established the "think while calling tools" agent paradigm, the source of the loop on page 2.
- Elements: a paper screenshot or a redrawn version of its "reasoning and acting interleaved" diagram + one citation
  line (Yao et al., 2022, arxiv 2210.03629) + one bullet (reasoning text sets the plan, actions pull information from
  the environment).

### Page 5: lead-in, from overthinking to agents
- One sentence: in the chat setting, people have studied preventing overthinking; the agent setting has a unique
  cheap property, which tool to call is roughly a multiple-choice question.
- Elements:
  - Bullet 1: the chat/math setting already has systematic study (Chen et al., 2024, arxiv 2412.21187: on easy
    problems, a large share of thinking tokens is wasted).
  - Bullet 2: I bring the goal of saving thinking to the agent setting.
  - Bullet 3 (the multiple-choice intuition): AppWorld has 183 tools in total, ALFWorld has a dozen or so common
    actions, so what to call next is a choice over a closed set, not open-ended generation.
  - Optional fine print: multiple choice also has a "guessing floor," always guessing `go` on ALFWorld already scores
    0.548, later results all have to be read against this prior line (sets up page 13).

## The idea (pages 6 to 7)

### Page 6: where the idea starts, Toolformer
- One sentence: Toolformer showed that "inserting an API call and its result mid-text" works; carry that one step
  further, does the call have to wait for the model to finish writing it itself, or can a bystander issue it early?
- Elements: the paper's text-with-inserted-call diagram (screenshot or redrawn) + one citation line (Schick et al.,
  2023, arxiv 2302.04761) + a closing question bullet: "can the position and content of the insertion be decided
  ahead of time by a cheap bystander?"

### Page 7: the core of the method
- One sentence: train a cheap small probe that reads as little of the thinking prefix as possible and predicts ahead
  of time which tool this step will call.
- Elements:
  - Figure (this is the main figure of the whole talk): a stream of thinking text with cut marks at sentence
    boundaries; the probe reads "task + history + thinking prefix" on the side; a cut where confidence clears θ is
    marked "fire: predicted tool name."
  - Bullet 1: the probe's cost is about 1/20 to 1/34 of the agent model's.
  - Bullet 2: it reads reassembled text, it does not touch the agent model's internal state.
  - Bullet 3: it only fires once confidence clears the threshold θ, θ trades off accuracy against earliness (sets up
    page 14).
- Source: `data/02-probe-matrix.md`.

## What was done (pages 8 to 12)

### Page 8: overview of experiment settings
- One sentence: two tasks × two execution models, all on local vLLM, split by the official problem sets.
- Elements: a 2×2 grid (rows AppWorld/ALFWorld, columns gptoss/q36), each cell showing the test-split event count
  (2138 / 3150 / 3497 / 2146); two bullets below: official problem-set split (AppWorld train 90 / val 57 / test 168
  questions), split by task instance to prevent leakage.
- Source: `data/01-settings.md`.

### Page 9: task and model traits and differences
- One sentence: one task has a low prior and the other a high prior, the two models' thinking length differs
  tenfold, together spanning four cases.
- Elements: two small tables.
  - Task table: AppWorld (phone-app operations, 183 tools, prior 0.16 to 0.40) versus ALFWorld (text household
    chores, few actions with many parameters, `go` is half of them, prior 0.47 to 0.55).
  - Model table: gptoss (120B, median thinking 2991 characters) versus q36 (27B, median thinking 292 characters).
- Source: `data/01-settings.md`.

### Page 10: where the data comes from
- One sentence: the agent does a task and leaves a trajectory; each call step is cut into prefixes at the thinking
  text's sentence boundaries, the label is the tool name it actually called at that step, fully automatic with no
  manual work.
- Elements:
  - Figure: one trajectory → one call step → sentence boundaries marked on the thinking text → one sample per
    prefix, arrows pointing to the shared label (the true tool name for that step).
  - Bullet: sample text = task + last 3 turns of history + thinking prefix; up to 64 prefixes per event; split by
    task instance.
- Sources: `data/01-settings.md`, `data/08-training-details.md`.

### Page 11: how the probe is trained
- One sentence: full-parameter fine-tuning of Qwen3-0.6B plus a linear classification head, one forward pass over
  the whole event, with all sentence-boundary positions supervised at once.
- Elements:
  - Figure: one token sequence with several positions marked as supervision points (same label), annotated "one
    forward pass over the whole segment."
  - Bullet 1: position weight 1/m_i, in deployment the probe is asked at every sentence boundary, the training
    distribution is aligned to the deployment distribution.
  - Bullet 2: hyperparameters in one line (lr 1e-5, 3 epochs, max_len 4096 with left truncation to keep the thinking
    tail on overlong samples, fp32 weights + bf16 compute, seed fixed).
  - Optional bullet: a control with the ModernBERT-base backbone trained through the same pipeline (leaves an opening
    for the page-13 comparison).
- Source: `data/08-training-details.md`.

### Page 12: how θ is set
- One sentence: θ is not a training artifact, it is a calibration artifact, fit temperature, scan the threshold,
  freeze it and report on the test split.
- Elements:
  - Figure: a four-split data flow bar (train 70% → fit temperature 10% → scan threshold 10% → test 10%), arrows
    labeled with what each step does.
  - Bullet: the risk-tier contract, the 0.1 tier requires trigger accuracy no lower than 90%, the 0.05 tier no lower
    than 95%; the passing bar is beating the frequency prior.
- Source: `data/01-settings.md`.

## Results (pages 13 to 15)

### Page 13: main result, the four-cell single-point table
- One sentence: the four cells' trigger accuracy is 0.94 to 0.95, all beating the prior, but the trigger ratio
  varies widely by task, accuracy and coverage must be read together.
- Elements:
  - Table (the only element on this page, enlarged):

    | Task | Model | θ | Trigger ratio | Trigger accuracy | Prior baseline |
    |---|---|---|---|---|---|
    | AppWorld | q36 | 0.925 (0.1 tier) | 0.29 | 0.937 | 0.159 |
    | AppWorld | gptoss | 0.975 | 0.30 | 0.951 | 0.404 |
    | ALFWorld | q36 | 0.5 | 1.00 | 0.944 | 0.548 |
    | ALFWorld | gptoss | 0.95 | 0.94 | 0.947 | 0.470 |

  - Fine print below the table: the AppWorld q36 row is the 0.1 tier (the 0.05 tier has no solution), the rest are
    the 0.05 tier; the accuracy denominator is "events the probe dares to fire on."
- Source: `data/02-probe-matrix.md`.

### Page 14: the θ trade-off curve
- One sentence: the higher θ is, the more accurate the guess and the fewer the fires, a clean trade-off curve, θ is
  set by risk preference.
- Elements:
  - Figure: a dual-y-axis or two-line chart, x-axis θ (six points, 0.5 to 0.95), one line for trigger ratio
    (0.91 → 0.42), one line for tool-name accuracy (0.66 → 0.93) (AppWorld × gptoss).
  - Corner note: the curve and the page-13 table take their reading points on different bases (the curve's θ=0.95
    point is 0.925, the table's θ=0.975 point is 0.951), marked "a different evaluation basis."
- Source: `data/03-offline-inject.md`'s θ scan table (only the two prediction columns used).

### Page 15: how early, and where the signal is
- One sentence: at the moment of firing the thinking is far from finished; take the thinking away and accuracy
  collapses, the signal really is in the thinking.
- Elements:
  - Bullet 1 (earliness): earliness 0.58 to 0.84 (a larger value means firing earlier; on the ALFWorld q36 side
    0.836 is earliest, on the gptoss side it is around 0.58).
  - Figure or paired bar comparison (signal): ablation, with the thinking segment removed, weighted accuracy on the
    calibration split drops from 0.613 to 0.421 on AppWorld and from 0.752 to 0.438 on BFCL (same metric, same data,
    control baseline from run `20260730_0056_bert_probe_v3`).
  - Fine print: the ablation batch was done with the early self-split partition plus the ModernBERT probe, a
    different test-bed generation from the page-13 official-split numbers, only the directional conclusion is taken,
    not the absolute values.
- Source: `data/02-probe-matrix.md`.

## Findings and plans (pages 16 to 17)

### Page 16: findings so far
- One sentence: on the share of events the probe dares to fire on (three tenths to all of them, depending on the
  task), once the thinking is written far enough it can already predict the tool name at above 94% accuracy.
- Elements: just this one sentence (enlarged, centered), with three lines of fine print below pointing back to the
  evidence pages: accuracy and coverage (page 13), the trade-off curve (page 14), earliness and signal (page 15).

### Page 17: plans going forward
- One sentence: next, explore along three axes, how to feed the prediction back in, where the parameters come from,
  and splitting by tool type.
- Elements (three bullets):
  - How to feed the prediction back into the thinking (new schemes for what to feed back and when).
  - Where the parameters come from: fill in the whole call beyond the tool name (span extraction / pin the tool name
    and let the parameter model write its own parameters).
  - Tool type: handle read-only tools and write tools separately (read-only tools can boldly jump ahead, write tools
    need caution).
- Wording caution: the phrasing is "axes we plan to explore," not "haven't done yet" (the offline injection
  experiments have been done, just not covered this time).
