# Stuck-word table (used by exp-status, only grows, never edited)

Every original term in the project uses only the one name in the second column throughout the whole document. The third column is a violation no matter where it appears; scan for it with a string search once the document is written. The fourth column has other legitimate uses; a hit there needs a human eye to judge. First table built 2026-09-04 (the status document for the kvshare-train line).

| Original term in the project | The one name used throughout | Always a violation as an alias | Alias that depends on context |
|---|---|---|---|
| gpt-oss-120b (the model whose trajectories are collected) | the probed model | the collected model, the large model, the host model, the main model | the model |
| The collective name for the three small models ctool / cgen / cparam | probe | the small model, the prediction head, the detector, probe (lowercase generic) | the head |
| ctool | ctool (the probe that only judges tool type and decides whether to fire) | the classification probe, the tool head, the firing probe | the classification head |
| cgen | cgen (the probe that generates the whole call string) | the generation probe, the call generator | generation |
| cparam | cparam (the probe that fills in only the parameters given the tool name) | the parameter probe, the parameter generator | parameters |
| cell | cell | the task cell, the training cell, the box, the unit | format |
| Qwen3-0.6B/1.7B/4B-Base | base model | the foundation model, the base model (alt. phrasing), backbone, the underlying model | the model |
| The code names of the four base-model configurations, b06 / b17 / l17 / l4 | b06, b17, l17, l4 (spelled out on first appearance) | configuration one, the small-model tier, the large base | configuration |
| train_causal_share.py | cache-reuse trainer | the new trainer, the packing trainer, the shared trainer, the kvshare trainer, the prefix-sharing trainer | trainer |
| train_causal_callgen.py / train_causal_param.py | row-by-row trainer | the old trainer, the old script, the reference trainer | the reference path |
| event (the group of rows before the same tool call) | event | set, episode, sample group, one task | one call |
| row (one jsonl record, one training instance) | row | sample, instance, entry, cut-point sample | sample |
| cut point (a row text's character length, that is, a sentence boundary) | cut point | cut, firing point, breakpoint | boundary |
| event's full text (the text of the row with the largest sent_idx) | event's full text | full text (bare), the whole segment, the complete text | text |
| target string / target segment | target string (the call string to generate plus the end token), target segment (the tail after the common prefix plus the target string) | the answer segment, the label segment, the tail segment | the tail |
| logical minibatch | logical mini-batch | mini-batch (bare), mini-batch (alt. spelling), micro-batch | batch |
| physical block | physical block | block (bare), physical batch, chunk | batch |
| one opt.step() | one update | one step, step (bare), one iteration | step |
| --tok-budget | token budget | the budget (bare), the block budget, the packing cap | the cap |
| --max-len | the event's full-text token cap | the cap (bare), the maximum length, the truncation length | length |
| --mem-probe | memory probe | probe (bare, when meaning specifically the memory probe), the memory probe (alt. phrasing), probe (lowercase generic) | detection |
| The three values of --mem-probe-pick | block-picking method tokens / cost / loop | probe mode, the three probes | mode |
| Alignment check (row-by-row loss comparison between the old and new paths) | alignment check | alignment acceptance, equivalence check, consistency check, alignment gate | alignment |
| val_ce | validation cross-entropy | val loss, validation loss, validation-set loss | loss |
| --gen-eval / val_exact_call | generative evaluation / whole-string exact-match rate | generation eval, exact-match rate (bare), exact match | generation |
| --grad-ckpt | gradient checkpoint | checkpoint (bare), recompute, gc | save state |
| --overlong | overlong-event handling switch | overlong switch, truncation switch, overlong mode | mode |
| The three values of --overlong | left-truncation (left), skip rows (skip), drop events (drop-event) | truncation tier, skip tier, drop tier | tier |
| Full-parameter fine-tuning | full-parameter fine-tuning | full fine-tuning, full-parameter training, full FT | full-parameter |
| LoRA | LoRA (low-rank adapter, training only the small matrices attached beside the linear layers) | adapter training, low-rank training | adapter |
| Learning-rate sweep | learning-rate sweep | hyperparameter sweep, grid search, hyperparameter search, sweep (bare) | sweep |
| Batch prefix ks828 | batch prefix ks828 | the new prefix, the new batch number, the ks batch | batch |
| run (one registered GPU execution) | run | task, job, a run-through, one pass | task |
| Whole-run step peak (torch's allocated peak, decimal GB) | whole-run peak | the real peak, the training peak, the memory peak, peak memory | peak |
| The three data splits | train split, val split, test split | train set, validation set, test set (when appearing alone) | set |
| Firing threshold θ | firing threshold θ | threshold, the firing line, triggers | threshold |
| The decision ledger decisions.md | decision ledger | decision log, decision record, ledger (when referring specifically to it) | ledger |
| The plan-8-28 session | main session | I/me, the plan session, the main conversation | session |
| 8-28-assistant | helper 1 | the recorder, the reviewer, assistant-1 | helper |
| 8-28-assistant-2 | helper 2 | the readout person, the memory helper, assistant-2 | helper |
| The gpu-runner sub-agent | launcher | the launch sub-agent, launcher (alt. capitalization), gpu-runner | launch |
| The sub-agent in ticket-run that works tickets | implementer | the worker, the executor, agent | implementation |
| The web report artifact | report page | artifact, the report page (alt. phrasing), web page | report |
| The two units for memory | GB (decimal, torch's allocated peak) and GiB (binary, nvidia-smi and card capacity) | G, gigabyte | memory |

Rows added after the first check round on 2026-09-04 (the ones from the alias-finder's 35 groups that genuinely needed unifying, plus renames the checker reported). The `--max-len` row's "the cap" moved from the third column to the fourth: once the document's opening defines "the event's full-text token cap (called the cap below)," the short form may be used.

| Original term in the project | The one name used throughout | Always a violation as an alias | Alias that depends on context |
|---|---|---|---|
| One fixed set of training or generation settings | convention (new convention = the set decided on 8-28; old convention = np821's set) | the new scheme, the new approach, the new training method | setting |
| The position of a target token | loss position | loss pos, target position, supervised position | target token |
| The matching start shared by a row's tokenization and the event's full-text tokenization | common prefix | the shared prefix, shared prefix (alt. phrasing), the prefix part | prefix |
| The physical block where the whole-run peak occurs | the whole-run-peak block | the peak block, the real-peak block | block |
| wall_s | whole-run wall clock | total wall clock, wall-clock time, total duration | wall clock |
| The complete data for train / val / test | full dataset | the full amount, all the data, the whole set | full |
| ctool's accuracy field on the val split, calA_weighted_acc | val-split weighted accuracy (the field name keeps the old split name calA) | calibration-set weighted accuracy, calibration-split accuracy | accuracy |
| bounds in the eval scripts | cut point | boundary, bound | edge |
| The eval script's full_call_ok | full-call exact-match rate (the eval script's) | whole-string exact-match rate (that is the trainer's val_exact_call) | exact-match rate |
| The sixth item's heading among the six | configuration details | worth-noting configuration details, things to note | details |
| Acceptance when a person is not present | checker (the sub-agent that finds fault section by section) | the reviewer (alt. phrasing), the referee | check |
| The sub-agent doing final review in ticket-run | final reviewer | the reviewer (alt. phrasing), reviewer | final review |
| How the five temperature-0.0 preset files were handled | delete | move out of the repository, move away | remove |
| The segment where training starts slower than it runs later | the slow-start segment | the ramp-up segment, the warm-up segment, steady state | the start |
