# How the probes were actually trained

Source: the `pipeline/train/train_causal_tool.py` and `train_mbert_tool.py` script text in the snapshot `b1f5b9c`
(every number in this file is copied from the code's default values and from `DATA.md`); the sample-construction
rules are in `01-settings.md`.

## The training objective

The supervision signal is fully automatic, with zero manual labeling: every real tool-call step in a trajectory is
one event, an event is cut into several prefix positions at the thinking's sentence boundaries, and the label at
each position is the tool name actually called at that step. What the probe learns is "given the thinking written
up to this point, predict which tool this step will ultimately call."

## The causal head (ctool, the winning main-line scheme)

- Backbone Qwen3-0.6B-Base, full-parameter fine-tuning, the head is one `nn.Linear` layer (final hidden state →
  distribution over tool names).
- One forward pass over the whole event: the whole sample text is encoded once, and supervision is taken
  simultaneously at the token positions corresponding to every sentence boundary (the script comment's exact words,
  "one forward pass over the whole segment"). Position weight w=1/m_i (split evenly within the event), aligning the
  training distribution to the deployment distribution, in deployment the probe is asked once at every sentence
  boundary.
- Hyperparameters (script defaults): lr 1e-5, AdamW weight_decay 0.01, linear schedule with 5% warmup, 3 epochs,
  batch 4 events × gradient accumulation 8, max_len 4096, left truncation on overlong samples
  (`truncation_side="left"`, the comment's exact words, "keep the thinking's tail").
- Precision scheme: fp32 weights, bf16 autocast for compute. This is the fix settled on after the bf16
  hard-training incident (the update magnitude at the chosen lr was below bf16 weight resolution, the model was
  effectively frozen).
- Before training starts, an alignment check must pass: the final hidden state and logits from the whole-segment
  single forward pass and from a token-by-token incremental forward pass must match under fp32 (tolerance 1e-4,
  TF32 disabled); training is refused if it does not pass. This is the gate against the Mamba hybrid architecture
  silently computing wrong.
- Seed fixed at 20260729 (data, shuffling, and initialization all share this source).

## The ModernBERT head (mtool, the baseline scheme that lost the comparison)

- Backbone ModernBERT-base (an encoder of about 150M), plus a classification head, likewise full-parameter
  fine-tuning.
- Hyperparameter defaults: lr 2e-5, batch 8 × accumulation 4, 3 epochs, max_len 4096, bf16 autocast.
- Its score gap against the causal head is in coverage, not in discriminative power (the c2 batch at the same
  θ=0.95: trigger ratio 0.9397 versus 0.5988, accuracy 0.9467 versus 0.9355).

## The other two cells (evaluated only at the trigger point, no separate pipeline)

- mext: a ModernBERT extraction head, locates the start and end span of parameter values in the text, evaluated
  only at mtool's trigger points.
- cgen: Qwen3-0.6B generates the whole call directly (tool name + all parameters), evaluated only at ctool's
  trigger points.

## Calibration after training (the probe's last two steps before shipping)

The trained probe is not used directly: first a temperature is fit for its confidence on the fit-temperature split,
then a θ satisfying the risk constraint is scanned for on the threshold-scan split (the risk0.1 tier requires
trigger accuracy no lower than 90%, the risk0.05 tier no lower than 95%), and finally the frozen θ is reported on
the test split. θ is not a training artifact, it is a calibration artifact.
