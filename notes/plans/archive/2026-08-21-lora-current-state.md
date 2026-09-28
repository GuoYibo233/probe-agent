# LoRA experiment-line status report (2026-08-21, a draft for consulting someone)

This report surveys what the LoRA training line in the new1 project currently looks like: what the configuration is, where the configuration came from, what measured numbers it has produced. The whole report states only facts, and every number notes which file it comes from; nowhere in the report is there any evaluation or recommendation, and the open questions are listed separately in the last section.

## 1. Background: what LoRA fine-tuning is applied to

The model being fine-tuned is the probe, whose job is to watch a large model that is solving a task (gpt-oss-120b working on tasks in the AppWorld environment) and, every time it finishes writing a sentence of thinking, predict from the text which tool call it is about to make next. The probe has three training methods in total, each its own independent training task:

1. ctool: predicts only the tool name. The last-layer hidden state is taken from the backbone, with a linear classification head attached on top for multi-class classification.
2. cgen: generates the whole call string (tool name plus parameters), standard language-model fine-tuning.
3. cparam: given the tool name, generates only the parameter part inside the parentheses, also language-model fine-tuning.

The backbone is the Base pretrained version of the Qwen3 family, at three sizes: 0.6B, 1.7B, 4B (weights on NFS, path mapping at `pipeline/train/train_causal_tool.py:70-72`). The input sequence cap is 4096 tokens, with overlong sequences truncated from the left (`train_causal_tool.py:189`); the backbone weights are loaded in fp32 (`train_causal_tool.py:169`), and the forward pass uses bf16 autocast (`train_causal_tool.py:410`), i.e. mixed-precision training.

## 2. LoRA's current configuration

All three training scripts share the same implementation, `pipeline/train/lora_util.py`, with no divergence. The configuration is entirely the defaults in the code:

| Item | Value | Source |
|---|---|---|
| rank | 16 | `lora_util.py:30` |
| alpha | 32 | `lora_util.py:31` |
| dropout | 0.05 | `lora_util.py:32` |
| learning rate | 2e-4 | `lora_util.py:33` (when `--lr` is passed explicitly, `--lr` takes precedence, `lora_util.py:53-61`) |
| where the adapter is attached | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj | `lora_util.py:27-28`, the comment calls it "Qwen3's standard seven: four for attention plus three for MLP" |
| bias | none | `lora_util.py:76` |

Parameters that keep training outside the adapter: ctool's linear classification head is always fully trained (`train_causal_tool.py:372` wraps only the backbone, the head is not in the wrapped scope); if cgen turns on a binary fire-head, that head is also fully trained (`train_causal_callgen.py:458-459` explicitly appends it to the optimizer); cparam has no head at all, so with LoRA on, the only trainable parameters are the adapter itself (`train_causal_param.py:362` comment). The vocabulary output layer (lm_head) is not among the seven targets, and after the peft wrapping it is frozen along with the rest of the backbone's parameters.

Apart from the learning rate, the training recipe entirely reuses the full-parameter one, with nothing tuned separately for LoRA: batch size 4, gradient accumulation 8 (effectively 32 per step), 3 epochs, 5% warmup, gradient clipping 1.0 (`invariants.md` §3 training-side convention table). The full-parameter learning rate is 1e-5.

Checkpointing: every time the validation metric hits a new low, a deep copy of the adapter is made, merged and unloaded back into the backbone, and the whole HF weight set is saved into `best/` (`lora_util.py:80-101`), so the evaluation side needs zero changes, it just reads an ordinary set of weights. Measured environment versions: peft 0.20.0, transformers 5.14.1, torch 2.11.0+cu128 (measured output of `uv pip list` against cprobe-env).

## 3. Where this configuration came from

LoRA support was added on 2026-08-21 itself (commit `822cfce`). The basis for picking the four numbers rank 16, alpha 32, dropout 0.05, learning rate 2e-4 is recorded nowhere, not in the commit message, not in source comments, not in a plan document; the review record says "the LoRA line's hyperparameters follow the flag defaults, and are not part of the locked-hyperparameter comparison" (`plans/2026-08-21-review-findings.md:100`), meaning these numbers were used straight off convention defaults, with no tuning done and no hyperparameter comparison run.

The motivation for opening this line is recorded in `TIMELINE.md:13-30`: the main line runs full-parameter on big cards, and a separate LoRA experiment line was opened for small cards (gyb's own words, "try LoRA on the small cards, it can run in parallel anyway"); the z1 batch measured that 0.6B full-parameter blows out memory on a 48G card, and what a small card can run is LoRA; the reasoning behind the tradeoff was "LoRA saves VRAM, not compute (the forward and backward passes still go through the whole backbone); when a big card is available, the main line stays full-parameter... lock the hyperparameters first to get a baseline, add a comparison round later if tuning is needed."

## 4. The scale of the training data

The following is the data consumed by the round that got interrupted (the p1 batch), from the `DATA.md` aw_p1_v1 section: the train split has 46438 samples (90 tasks, 1098 tool-call events), the validation split has 29202; 3 epochs works out to 4356 optimizer steps (32 samples per step, matching the steps field on the first line of train_log.jsonl). The median task-description length is 4645 characters, with anything past 4096 tokens truncated from the left.

Note: this batch of data is about to retire. The next batch's convention is temperature 1, 4 trajectories collected per task, samples weighted equally per step; the sample size will only be known once collection finishes; if each trajectory's cut density is comparable to p1's, the train split would be about 4 times p1's size (this is a projection, not a measurement).

## 5. Measurement one: VRAM

A full round of testing was done before launch, as a smoke test on the tokyo106 A6000 (48G) (log `logs/new1_p1l*`): three backbone sizes times three cells makes nine cells; without gradient checkpointing, eight cells OOM, and only the 0.6B ctool cell passes directly; with `--grad-ckpt` added uniformly across all nine cells, all of them pass. VRAM usage at the moment of OOM in the logs: 0.6B's two cells 43.97 GiB, 1.7B's two cells 47.5 GiB, 4B's two cells 47.33 GiB (the OOM error lines in each smoke log). The plan document separately records two peak numbers (0.6B ctool without checkpointing 46114 MiB, 4B cgen/cparam with checkpointing 46426 MiB, `plans/2026-08-21-p1-collection-plan.md:116,118`); these two numbers have no second source in the logs, they can only be traced back to the plan document itself.

## 6. Measurement two: speed, and the six trainings that got interrupted

At 12:44 on 2026-08-21, nine LoRA trainings were launched (three backbone sizes times three cells, all with gradient checkpointing, one per A6000 card). The three ctool trainings finished the same day; the six cgen/cparam trainings were stopped and killed by gyb at 22:42 (commit `b17d9cb`), having run for about 9 hours 58 minutes by the time they were killed (the launch and end times in the `ops/jobs.json` ledger, subtracted). None of the six killed trainings reached the 1st epoch boundary, none had saved any checkpoint, so there are no validation-set numbers for them.

Speed and progress at the moment of being killed (the last line of `train_log.jsonl` in each output directory; the ips field holds the number of training samples processed per second):

| Training | Backbone | Progress (step/total) | ips |
|---|---|---|---|
| p1l06 cgen | 0.6B | 1300/4356 (29.8%) | 1.17 |
| p1l06 cparam | 0.6B | 1350/4356 (31.0%) | 1.22 |
| p1l17 cgen | 1.7B | 1000/4356 (23.0%) | 0.92 |
| p1l17 cparam | 1.7B | 1000/4356 (23.0%) | 0.92 |
| p1l4 cgen | 4B | 450/4356 (10.3%) | 0.41 |
| p1l4 cparam | 4B | 450/4356 (10.3%) | 0.41 |

Extrapolating this speed to the whole run (139314 samples divided by ips, a projection, not a measurement): about 32 to 33 hours for 0.6B, about 42 hours for 1.7B, about 94 hours for 4B. The 4B projection matches the actual progress (9.97 hours to reach 10.3%).

The three completed ctool LoRA trainings took much less time: 0.6B and 1.7B wrapped up in about 1.5 hours, 4B in about 3.5 hours (subtracting ledger times). ctool does only one forward pass over the whole text per event, a different way of processing samples than the two generation cells.

## 7. Complete results already available on the same data

Below are the numbers already wrapped up on the p1 data, LoRA and full-parameter can be looked at side by side. The metric field `best_calA_weighted_acc` holds the highest value across the three epochs of the sample-weighted tool-name accuracy on the validation split (source: each finish line in `ops/runs.jsonl`):

| Cell | Backbone | LoRA | Full-parameter |
|---|---|---|---|
| ctool | 0.6B | 0.6878 | 0.6924 |
| ctool | 1.7B | 0.6628 | 0.6685 |
| ctool | 4B | 0.6689 | never run |

LoRA has no completed numbers at all for the cgen and cparam cells (all six were interrupted); the full-parameter side's final values: cgen's masked validation cross-entropy is 0.4043 for 0.6B and 0.4531 for 1.7B, cparam is 0.3493 for 0.6B and 0.332 for 1.7B (`ops/runs.jsonl` lines 50, 51, 58, 59).

## 8. Context for the next batch

When consulting someone, this background can be brought along: the next batch (nyanpasu-probtest821) plans four training batches, 0.6B running full-parameter only, 1.7B running one each of full-parameter and LoRA, 4B running LoRA only; all three cells run. The data switches to a new collection at temperature 1, 4 trajectories per task, equal weight per step, with the sample size projected to rise to around 4 times p1's (a projection). Available hardware: ten A6000 48G cards on tokyo106; on the big-card side, p1's full-parameter 1.7B was scheduled on an H200.

## 9. Open questions

1. rank, alpha, dropout, and learning rate are all currently convention defaults, not a single comparison has been run; there is no evidence on whether this set of values suits this task (4096-length sequences, tens of thousands of samples, a Base backbone).
2. The epoch count and batch size reuse the full-parameter recipe; whether they should be set separately given that LoRA's learning rate is 20 times higher has not been discussed.
3. The adapter is attached to only seven linear layers, with embedding and lm_head both frozen; whether it's appropriate to leave the output layer untrained for cgen and cparam, which are generation tasks, has not been discussed.
4. Speed: once the data grows 4x, extrapolating from §6's ips puts a single 4B LoRA cell at around 370 hours (94 hours times 4, a projection); whether running it this way on an A6000 is viable has not been decided.
5. Whether the epoch count should be lowered once the data doubles has not been discussed.
