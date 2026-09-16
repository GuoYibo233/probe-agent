# The new probe trains three kinds of models; this document records the decisions and open items from the 2026-08-21 discussion

This document records the outcome of the 2026-08-21 discussion between gyb and Claude on the new probe's training methods. What was settled is in the first six sections, what wasn't settled is gathered in the last section. The mechanism descriptions in the document have all been checked against the repo's current code, and every number notes its source.

## This discussion settled four overall decisions

First, the ModernBERT line is no longer run. The mtool and mext cells, two of the four cells, are stopped; the probe now focuses solely on the causal-model line.

Second, the causal line's backbone expands from the single Qwen3-0.6B-Base size to three sizes: 0.6B, 1.7B, 4B. The purpose of adding sizes is to compare performance across the three scales side by side, not because 0.6B is insufficient; gyb said this explicitly in the discussion.

Third, training splits into three kinds of models. The first predicts only the tool type; the second generates the whole call; the third, given the tool type, generates only the parameters. The point of having the second and third coexist is to measure the payoff of "letting a multiple-choice step decide the tool type": both use the same batch of samples and the same ground truth, differing only in how the string is assembled, so any gap measured between them can only come from whether the tool name is given in advance.

Fourth, on pilot order, gyb leans toward running the first round of experiments on 1.7B first. Three kinds times three sizes makes nine cells in total, and which ones to fill first has not been finalized.

## The first kind, predicting only the tool type, trains the way ctool does now

The mechanism is described as it currently stands in `pipeline/train/train_causal_tool.py`. One record of training data is one tool-call event: all the text before the call happens is cut at every sentence end, producing a series of samples that are prefixes of each other, and every sample's label is that call's tool name. The input text's assembly is fixed at three segments (the `assemble` function in `pipeline/annotate/rules.py`):

```
Task: <task description>
[HISTORY]
<previous call> -> <environment return>
[THINKING]
<thinking prefix>
```

During training, the whole text goes through only one forward pass; at the token position corresponding to each sentence end, the last-layer hidden state is taken out and fed to a linear classification head to guess the tool name, and the loss is a weighted cross-entropy, with the weight split evenly across the boundaries of the same event (`w = 1/m` in `build.py`, where m is that event's number of boundaries). The gradient doesn't only update the classification head, the whole backbone is fine-tuned along with it, and nothing in the code freezes any parameters. Before training starts, an alignment check must pass: the last-position hidden states from one whole-text forward pass and from a token-by-token incremental forward pass must match; this is an iron rule of the pipeline. The trained model can produce a set of per-tool confidence scores at any sentence end, and the choice of firing threshold theta relies entirely on this set of confidence scores.

gyb confirmed one convention in the discussion: parameters do not enter the first kind's training. Broken down, that's three places. The supervision target is only the tool name; when the training code loads data, it reads only the text, label, and weight fields, and even though the samples store the complete call string and parameter table, the loading function never touches them. This call's parameters are also not in the input text; the thinking prefix stops before the call happens, so this call's parameters belong to the future, and putting them in the input would leak the answer. The history segment is the only place parameters appear: calls that already happened in earlier turns are laid out as is with their own parameters, keeping at most the most recent 3 turns, with an environment return truncated past 400 characters (both are constants in `rules.py`); these are facts about the past, and count as legitimate context.

## The second kind, generating the whole call, trains the way cgen does now

The mechanism is described as it currently stands in `pipeline/train/train_causal_callgen.py`. One sample carries three fields: text, the ground-truth call string, weight. The assembly is that the input string equals the text followed by a fixed separator string `\n[CALL] `, and the target string equals the whole call string plus an end token. The loss is computed only on the target segment's tokens, the input segment is never penalized; what's being taught is "what to write right after the separator string." This is standard language-model fine-tuning, with all parameters in motion. To keep left-truncation from eating into the target, the code first tokenizes the target string separately, discards and counts overlong samples entirely, then left-truncates the input by the remaining budget. Choosing the best checkpoint looks only at the weighted cross-entropy of the target segment on the validation set.

## The third kind, given the type, generating only the parameters, is a new cell to be built

The third kind changes one thing from the second: the input string extends from "text plus separator string" to "text plus separator string plus tool name plus opening parenthesis," and the target string shortens from the whole call string to just the parameter part inside the parentheses. Taking the call string `apis.spotify.login(username=x, password=y)` from the comment at the top of `train_causal_callgen.py` as an example, samples for the two kinds look like this:

```
Second kind  input:  ...task description, history, thinking prefix...\n[CALL]
             target: apis.spotify.login(username=x, password=y)<eos>

Third kind   input:  ...task description, history, thinking prefix...\n[CALL] apis.spotify.login(
             target: username=x, password=y)<eos>
```

The third kind's model itself writes only the part after the opening parenthesis; the tool name and the opening parenthesis are part of what's fed into the model as input. For a call with no parameters, the target string is left with just a closing parenthesis plus an end token.

The data needs no new annotation. `build.py`, which builds the data, already holds the tool name (`ev["tool"]`) and the parameter table (`args_named`) separately before assembling the ground truth, and after assembling both halves it also stores them in each sample's `label` and `args_named` fields. The third kind's input string takes the tool name from the `label` field, and its target string assembles the parameter part from `args_named` using the same assembly rule as `make_call`. The acceptance gate `check_callstr` already guarantees that every call string can be split back into tool name and parameters by the evaluation side's `parse_call`, so the boundary between the two halves is clean. The change lands in the training script's string-assembly function; the entire upstream chain, collection, annotation, acceptance, needs no change at all. The size of the change is on the order of ten lines; ten lines is an estimate, not counted precisely.

During training, the tool name in the input string always uses the ground truth. At use time, the tool name comes from the first kind of model's prediction, so there is one place where training and use don't match: the model has never seen a sample where "the tool name was given wrong," and once the tool name is wrong the parameters mostly go wrong along with it. This mismatch has to be measured with the evaluation's two conventions (see the next section).

The discussion also went over another option, constrained decoding: the second kind still generates the whole call as before, but on the tokens that write the tool name, the vocabulary is restricted to the set of valid tool names. This was not adopted, because the decoding logic would have to maintain its own "which position am I at, what should be restricted," which is roundabout to write, and the tool name would still end up decided twice, once by the generating model and once by the classification head, leaving the same awkwardness of two sources of truth.

## At use time, the three kinds form two systems for comparison

Regardless of which system, the firing step is always done by the first kind: confidence is checked at each sentence end, and firing only happens past the threshold theta. After firing, writing the call string splits into two paths. System A is the first kind plus the second kind: the second kind writes out the whole call itself, deciding the tool name a second time, and the name reported by the first kind is used only to trigger firing. System B is the first kind plus the third kind: the tool name reported by the first kind is spliced directly into the third kind's input, the third kind only fills in the parameters, and the complete call string only comes from concatenating the two models' outputs. The two systems' firing parts are exactly the same; the whole difference is in the half that writes the call, so the comparison's result can be cleanly attributed to one single thing: whether the tool name is regenerated or carried over from the classification head.

The third kind's evaluation has to run under two conventions. One convention feeds in the ground-truth tool name, measuring the model's pure parameter-filling ability; the other feeds in the first kind's prediction, measuring system B's real-world performance. The gap between the two conventions is exactly the loss that leaks through from the first kind picking the wrong tool.

The discussion gave three reasons for choosing generation over adding a head to produce parameters. A parameter's value is often not copied straight out of the preceding text, the model has to compose it itself, and a head-based approach cannot compose a value that never appeared in the preceding text. Downstream execution and injection consume a complete call string, and generation's output is directly that string. The evaluation code for the generation path, `eval_causal_call.py`, already exists.

## The only measured numbers for training cost are from one small-sample round; anything larger is entirely projected

Facts first. The only round of measured causal-line training time on record is the 2026-08-10 z1 smoke test, on a small sample of 20 tasks, on an H100, where ctool trained for 4 minutes and cgen for 69 minutes (the `train_wall_min` field of the finish entries in `ops/runs.jsonl`, which holds the training's wall-clock minutes). For the c1 full-matrix round before the clean sweep, the ledger records all six causal trainings' start time as 09:12 on 2026-07-31 and end time somewhere between 17:02 and 17:34, which are recording times, not the real start and end; a single training's wall-clock duration on the full data cannot be read from the ledger, all that can be said is that the 12 trainings, including the ModernBERT line, wrapped up within that same day. Both of 0.6B's two cells OOM'd on the 48G A6000; z1 only got running after switching to an H100. That ctool is cheaper than cgen is a measurement (4 minutes versus 69 minutes), but the reason has not been investigated; ctool is likewise a full-model fine-tune, not training just a head.

Below is a projection, not a measurement. Fine-tuning's compute scales roughly linearly with parameter count; 1.7B has about three times 0.6B's parameter count, so training once on the same data takes about three times as long: cgen is projected at a bit over three hours on the small sample, and on the order of one day on the full data, assuming an H100 or H200 is used. 4B's full-parameter fine-tuning may only be worthwhile if switched to a parameter-saving approach like LoRA that trains only a small fraction of the parameters; this size has not been worked out in detail.

## Three things are still undecided, and four preparations are needed before starting

Three things are still undecided. Which batch of data to use is undecided: the dataset directory on NFS is currently empty, this comparison will need to go through collection and dataset building first, and which environment to collect from, whose model's trajectories to collect, have not been discussed yet. Which of the nine cells to run first is undecided, there is only the leaning of "run the first round of experiments on 1.7B first." Whether the 4B size uses full-parameter fine-tuning or LoRA is undecided.

Four preparations are needed before starting. Download Qwen3's 1.7B and 4B weights to the model drive on NFS; currently the drive has only one copy of Qwen, 0.6B-Base. Add aliases for the new sizes to ctool's `--base` argument. Change cgen's hardcoded 0.6B backbone to be selectable. As a new cell, the third kind goes through the three-part set: training code, the run.py registry, the probe-pipeline skill write-back, in the same commit; the registered name is decided once settled.
