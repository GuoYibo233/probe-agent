# Full-history probes: plan

Written 2026-09-30 from the step-by-step settings walk with gyb. The goal: probes that read
the task, every earlier tool round and the current step's thinking so far, trained on a new
collection under the current harness.

Status of each item: DECIDED (gyb said so in the walk), RECOMMENDED (my proposal, waiting
for his word), MEASURE (the value comes from a measurement, not a choice).

## 1. What changes, in one picture

```
collect (new harness, 5 runs per task, 50 steps)
   -> build (all rounds, result clip sized to the window, measured)
   -> train (3 passes, a copy of the weights per pass, token limit measured)
   -> eval (choose the pass to read; default the best pass)
   -> inject (choose the pass to read; default the best pass)
```

## 2. Settings, group by group

### 2.1 Collection

| Setting | Now | New | Status |
|---|---|---|---|
| Step limit per task | 30 | 50 | DECIDED |
| Temperature | 1.0 | 1.0 | DECIDED (unchanged) |
| Generated-token budget per step | 8,192 | 30,000 | DECIDED |
| Tool reply cap | 12,000 characters per reply | 20,000 characters per reply | DECIDED (the per-reply reading, 4.1) |
| Date in the system message | each task's own date | unchanged | DECIDED ("whatever works") |
| Runs per task | 1 (seed 42) | 5 | DECIDED; the seed list is gyb's to name |
| Splits, agent model, instruction wording | train / dev / test, gpt-oss-120b, v2 | unchanged | DECIDED |

The step limit, the token budget, the seeds and the temperature are setting fields already,
so they go into the new named setting. The reply cap is a constant in the AppWorld
environment file, so it is a code change (section 3, item 1).

### 2.2 Build

| Setting | Now | New | Status |
|---|---|---|---|
| History rounds | 3 | every earlier round | DECIDED; the value is the step limit, 50, since a record never has more rounds than steps |
| Result clip per round | 400 characters | as large as the window allows | MEASURE (section 5, measurement 1) |
| Over-long text | none (the trainer drops the event) | the oldest rounds are cut from the text, in the build and on the live side alike | DECIDED (gyb, 2026-09-30, 4.2) |
| Cuts per event, minimum thinking, weight, split source | 64, 40, uniform, official lists | unchanged | DECIDED |

### 2.3 Probe model

| Setting | Now | New | Status |
|---|---|---|---|
| Backbone | Qwen3-0.6B-Base | unchanged, first | DECIDED; 1.7B and 4B after the 0.6B result |
| Tuning | full | unchanged | DECIDED |
| Window | 32,768 tokens | the hard ceiling of every length below | fact |

### 2.4 Training

| Setting | Now | New | Status |
|---|---|---|---|
| Passes over the data, classifier and generators | 1 | gyb settles the passes in another session; not part of this plan | OWNER (gyb, 2026-09-30) |
| Per-pass weight copies | none (best/ and last/ only) | a copy per pass, off by default | DECIDED (gyb, 2026-09-30) |
| Token limit per event | 8,192, drop the event | measured; an over-long text loses its oldest rounds (4.2) | MEASURE (section 5, measurement 2); the rule is DECIDED |
| Gradient checkpointing | off | on only if the measured run does not fit the card | DECIDED (gyb, 2026-09-30), conditional on measurement 2 |
| Seeds | 1 | 3 for the final configuration | DECIDED (gyb, 2026-09-30) |
| Learning rate, warmup, optimizer, head, LoRA shape | 1e-5, 5%, AdamW 0.01, linear head | unchanged | DECIDED |

### 2.5 Evaluation and injection

| Setting | Now | New | Status |
|---|---|---|---|
| Which weights the evaluation reads | the best pass | a choice of pass; default the best pass | DECIDED (gyb, 2026-09-30); design in 4.3 |
| Which weights the injected probe reads | the best pass | a choice of pass; default the best pass | DECIDED (gyb, 2026-09-30) |
| Wrong-fire rates, threshold grid, bootstrap | 10% and 5%, 0.5 to 0.975, 1,000 | unchanged | DECIDED |

## 3. Code changes

Every item keeps today's behaviour under its default, so the existing runs keep their keys.

1. **Reply cap 20,000** in the AppWorld environment file (`data/environments/appworld.py`).
   Cost: an era row for `sample` and `inject` (the text the agent sees changes).
2. **Per-pass weight copies** in the shared trainer (`train/utils/trainer.py`): a training
   setting, default off, under which the validation at the end of each pass also saves the
   weights under the pass number (a directory per pass beside `best/`). The copies are in the
   served form (merged under LoRA), like `best/`, since they are read, never resumed from.
   Cost: disk, one checkpoint per pass; a schema field with a default that reproduces today.
3. **Pass choice on the evaluation side.** The GPU half of the evaluation is the prediction
   step at the end of `train`, which reads `best/`. Design in 4.3; the code lands in
   `train/utils/trainer.py` (which copies get prediction rows), `data/probe_output.py` (the
   rows say which pass they came from), `eval/utils/probe_eval.py` (the evaluation reads the
   chosen pass's rows) and `experimental_settings/schema.py` (the field).
4. **Pass choice on the inject side.** The probe service (`models/probe_models/service.py`)
   loads `best/` of the two train runs; a setting names the pass directory instead, default
   `best/`. The field joins the inject key, since it changes what the probe says.
5. **Token-length line in the build report** (`data/build_training_dataset.py`): the report
   gives text lengths in characters today; measurement 1 needs tokens. The build runs on the
   CPU and the tokenizer library needs no torch, so this is a report line, not a new stage.
6. **Truncation of over-long events** (4.2, decided) in the probe text builder
   (`data/probe_input.py`) and a setting field beside the history length, so the build and
   the live side produce the same text. The budget is stated in characters, so the builder
   needs no tokenizer and the live side applies the same rule at the same cost; measurement 1
   maps the character budget to tokens and sets the train limit above it.
7. **Settings**: one new named setting per probe in `experimental_settings/train_probe.yaml`
   (gyb's file; I draft the block, he pastes it). Names follow the exact-names rule.
8. **README section 2 and 3 lines, `run.py selfcheck`, the `--debug` walk of `train_probe`**
   for acceptance, and the era rows the code gate asks for, all in the same commits.

## 4. Open decisions

### 4.1 What "20,000" means for the tool reply

AppWorld's paper does not cap each reply; it trims the whole history to 20,000 characters and
keeps the last two steps' outputs in full. Our loop caps each reply.

- **Cap each reply at 20,000 characters (recommended)**: one number changes, the loop stays.
- **Copy the paper's history trimming**: a new mechanism in the agent loop; the agent's
  context changes shape.

Decided 2026-09-30: the first, cap each reply at 20,000 characters.

### 4.2 An event whose text passes the token limit

Today the trainer drops the event whole. Every fine-tuning source the check found truncates
instead. With all rounds kept, the dropped events would be the late steps of long tasks, the
steps where history matters most.

- **Cut the oldest rounds from the text, in the build, so that training and live use see the
  same shape (recommended)**: the probe always sees the task, the newest rounds and the
  thinking; the only loss is the oldest rounds of the longest tasks. Cost: a field in the
  build section (in the build key and in the inject key), and the live side applies the same
  rule.
- **Keep dropping**: no code; the training set loses its longest events, and the live probe
  meets texts it never trained on.
- **Raise the clip budget until nothing is dropped**: only if measurement 1 shows the longest
  event fits the window at a clip that still shows the probe something useful.

Decided 2026-09-30: the first, cut the oldest rounds in the build and on the live side.

### 4.3 How the evaluation chooses a pass

The evaluation stage reads prediction rows that the train stage writes from `best/`; it never
loads weights. A pass choice on the evaluation side therefore needs prediction rows for that
pass to exist.

- **The train stage writes prediction rows for every kept pass copy, and the evaluation
  setting picks one (recommended)**: the evaluation stays a CPU stage and can switch passes
  without a new GPU run. Cost: the prediction step runs once per kept pass (about 20 to 45
  minutes per pass on the August test size), and the rows carry the pass they came from.
- **The pass choice is a train field and the prediction step reads that copy**: cheaper, but
  a different pass means a new train directory, which retrains from scratch, since the train
  key changes.

### 4.4 Passes and seeds

Decided 2026-09-30: three seeds for the final configuration.

Decided 2026-10-02 (gyb, in this plan's code session and again in the coordinating
session): the full-history probe trains for 3 passes, the draft setting's value. The
per-pass copies make the pass count a cheap question: one three-pass run gives all three
answers.

## 5. Measurements before the settings are final

1. **Text length against the clip.** On the new collection, build with every round and a
   candidate clip; the report's token line gives the distribution per step depth and the
   share of events over 8k, 16k, 24k and 32k tokens. The clip is the largest value at which
   the longest event still fits 32,768 tokens, or, under 4.2's truncation, at which the share
   of truncated events is small. Rough arithmetic: 32,768 tokens is about 100,000 characters;
   over 50 rounds that is about 2,000 characters per round for the code block plus its clipped
   result, before the task and the thinking.
2. **Memory and speed at the measured limit.** A `--debug` train of the 0.6B classifier at
   the chosen token limit on the target card, through the gpu-run skill: peak memory and
   seconds per event. Gradient checkpointing goes on only if this does not fit.

## 6. Order of work

1. Code items 1 to 6; selfcheck; the `--debug` walk; era rows; commit. Items 2, 3 and 4
   (the pass copies and the pass choice) belong with the passes work in gyb's other session;
   items 1, 5 and 6 (reply cap, token-length line, truncation) can go first and separately.
2. gyb pastes the new setting blocks.
3. Collection: 315 tasks x 5 runs at 50 steps. Measured rate: about 59 task runs per hour per
   H200 card at 30 steps; the 50-step limit and the 30,000-token budget make a run longer by
   an unmeasured amount. On four tokyo108 cards: about 7 hours at the 30-step rate.
4. Build with every round and the candidate clip; measurement 1; fix the clip and the limit.
5. Measurement 2; the 0.6B classifier, 3 passes; evaluation of each pass.
6. The 3-round control probe on the same collection, for the fair comparison.
7. The generators and the larger backbones, after the classifier result.

## 6a. Run log of the collection (sample-e09d7f1730d6)

- 2026-10-01 11:18 JST: launched from `draft/full_history` on tokyo108 cards 1, 3, 5 (three
  servers, 18 loop pieces) after the draft setting's `--debug` walk passed end to end.
  Measured rate 110 to 140 task runs per hour (one server shared with a full-test run until
  16:20), against the 177 estimated from the 30-step rate.
- 12:59 JST: loop piece 15 stopped advancing; its record `302c169_1__s4267` and its log
  `log/15.txt` have pages stuck on tokyo108's NFS client (`folio_wait_bit_common`): any
  read of either file from tokyo108 blocks, reads from another machine work. `run.py ls`
  did not flag the piece.
- 16:23 JST: killed by me at 598 finished records, to relaunch on six servers; that
  relaunch was refused by the session's permission classifier and was not retried.
- 16:24 and 17:24 JST: two relaunch walks on the original three cards hung on the two
  stuck files (the second after writing its start row). Both files were copied to the
  session scratchpad and removed from the run directory; the hung `run.py` processes on
  tokyo108 (2367565, 2376903) are in uninterruptible disk wait with a kill pending.
- 17:59 JST: relaunched on cards 1, 3, 5; the partial directory is continued.
- Open for gyb: the six-server relaunch (`sample.replicas=6 sample.pieces=36` on all six
  tokyo108 cards) halves the remaining time; a loop piece stuck in an NFS write is not
  seen by `run.py ls`, and a walk that reads a stuck file hangs without a message.

## 7. Data reused, not re-collected

The August trajectories (1,260 runs, 4 seeds, 30 steps, the old harness) stay on the net
disk as a second source; they need a record-format conversion before the current build can
read them. Not in this plan's path; kept as an option for a same-data comparison with the
imported 3-round probes.
