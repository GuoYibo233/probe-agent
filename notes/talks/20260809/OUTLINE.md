# Group meeting slide outline (only items the user explicitly said to cover)

Inclusion rule: only records content the user said, in their own words in conversation, that they want to cover;
assistant suggestions never go into this file. Appended as the conversation continues.

## Background section

- what an agent is
- preventing overthinking: used as a lead-in, someone earlier worked on preventing chat-scenario overthinking, and I
  want to bring that to the agent scenario; the agent scenario's distinguishing feature is that which tool to call is
  roughly a multiple-choice question (user's own words: "the tool's output is roughly a multiple-choice question")
- what a tool call is
- content about saving tokens and the like (user's own words: "anyway, cover something about saving tokens and the
  like")
- one or two representative pieces of prior work by others, one sentence each on what it set out to do
  (verification results are back, candidates below, every abstract has been fetched and verified in person, which
  ones to keep is the user's call:)
  - ReAct (arxiv 2210.03629, Yao et al.): has the large model generate reasoning text and environment actions in
    alternation, defining the "think while calling tools" agent paradigm.
  - Alternate (kept if the word overthinking is kept): Do NOT Think That Much for 2+3=?
    (arxiv 2412.21187, Chen et al.): the first systematic study of overthinking in o1-class models, showing that on
    easy problems a large share of thinking tokens is wasted.
- tighten the background: merge "what an agent is" and "what a tool call is" into one page

## The idea (the core of the method)

- start from Toolformer, not counted as background, counted as the start of the idea
  (arxiv 2302.04761, Schick et al.: self-supervised learning of where in generation to call which API and how to
  fold the result into the following prediction, establishing "inserting a tool call and its result mid-text" as an
  object of study.)
- train a probe that predicts the coming tool call from (as little as possible of) the thinking content

## What was done

- built a few agent tasks, had the model execute them, then had the probe predict from that
- cover two tasks; the execution models used first are gptoss and qwen3.6
- introduce each task's and each model's traits and their differences from each other, and say why these were chosen
- how these probes were actually trained needs to be spelled out clearly (the verified training process is written
  up in `data/08-training-details.md`)
- what tasks and what data the trained models were run on
- do not talk about injection yet, only cover prediction accuracy
- plot one curve: correct fraction and trigger fraction at different trigger thresholds θ
  - only show the gptoss (AppWorld) six-point curve, other cells get a single-point table
  - data source: `data/03-offline-inject.md`'s θ scan table (the two pure-prediction-metric columns, injection need
    not be mentioned)
  - mixing caution: the curve and the matrix table take their gptoss numbers at different reading points, mark the
    source for each

## Findings at the current stage

- training can predict the tool ahead of time

## Plans going forward (only new ideas about direction)

- explore how to feed the prediction back in (new schemes for what to feed back)
- where the parameters come from (mext span extraction / skeleton-arm and other alternative routes)
- tool types (handle read-only and write tools separately)

## Positioning

- this is a group-meeting report, presenting research that is half done (user's own words: "just present the
  research that's half done")
