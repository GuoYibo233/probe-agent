# How to choose hyperparameters: a survey of 15 local papers and first-hand web sources (2026-08-26)

This report answers one question: for the training hyperparameters our np821 batch locked in (full-parameter learning rate 1e-5, LoRA learning rate 2e-4, 3 epochs, effective batch 32, 5% linear warmup then linear decay to 0, weight decay 0.01, gradient clipping 1.0, LoRA r=16 / alpha=32 / dropout 0.05), how the same kind of numbers were settled in the papers we have on hand and in public first-hand sources.

The report has four sections: §0 explains how the survey was done; §1 is the facts from each of the 15 local papers one by one; §2 is the facts from first-hand web sources grouped by angle; §3 puts our settings side by side with §1 and §2, listing only facts; §4 is interpretation, kept separate from the first three sections.

## 0 How the survey was done

There is no single unified paper library in the repo for "the papers we currently have"; what counts falls into three categories, 15 papers in total:

| Source | Papers | arxiv number |
|---|---|---|
| 3 papers cited by the 2026-08-09 report (`talks/20260809/SLIDES-text-en.md`) | ReAct; Toolformer; Do NOT Think That Much for 2+3=? (o1-class model overthinking) | 2210.03629; 2302.04761; 2412.21187 |
| 4 papers corresponding to reproduction repos under `~/reproduce` | ACE; Self-Distillation Enables Continual Learning (SDFT); AEL; Neural Thickets (the paper behind the RandOpt repo) | 2510.04618; 2601.19897; 2604.21725; 2603.12228 |
| 8 papers corresponding to the 7 benchmark environments under `envs/` | tau2-Bench; ALFWorld; TALES; AppWorld; Gorilla (BFCL's predecessor); ToolLLM (ToolBench); StableToolBench; ToolHop | 2506.07982; 2010.03768; 2504.14128; 2407.18901; 2305.15334; 2307.16789; 2403.07714; 2501.02506 |

BFCL's own paper (ICML 2025) has no arxiv entry: the extractor and the checker each queried the arxiv API by title and by author in five different phrasings, and every time only found other people's papers that cite BFCL, so the BFCL slot has only Gorilla.

Two opus subagents worked each paper: the first fetched the paper's full text (arxiv HTML or a PDF converted to text, appendices kept) to the local machine, and extracted every training setting and the evidence for "how it was chosen," counting each quote in the original text with `grep -c -F`; the second independently re-fetched the full text through a different route (the extractor used arxiv HTML, the checker used ar5iv or the PDF) and rechecked every quote and every number, defaulting to checking in the direction of overturning them. All 15 papers passed the check: 11 confirmed, 4 partially_confirmed (ReAct, Neural Thickets, ALFWorld, tau2-Bench). The failed items in the 4 partial ones were: one "Figure 8" in Neural Thickets is "Figure 7" in the PDF version (the HTML and PDF versions number figures differently); for ALFWorld, one item on the Seq2Seq baseline's training length was written as NOT STATED by the extractor, and the checker pointed out that Appendix B's "All text agents are trained for 50,000 episodes." covers that baseline; ReAct's and tau2-Bench's failed items were only differences in word-frequency counting convention (HTML includes navigation text, PDF doesn't). Not one hyperparameter number or "how it was chosen" quote was overturned.

The raw extraction and checking results are in `/home/y-guo/.claude/jobs/f768d4d4/tmp/papers_result.json` (the job's temporary directory, which disappears once the job is deleted).

## 1 The 15 local papers

### 1.1 The 8 that trained something

| Paper | What was trained | Learning rate | Batch size | Training length | Schedule and warmup | How it was chosen |
|---|---|---|---|---|---|---|
| ReAct (2210.03629) | Full-parameter SFT on PaLM-8B and PaLM-62B, 3,000 self-generated trajectories | Not stated | 64 | 4,000 steps (ReAct/Act), 2,000 steps (8B's Standard/CoT), 1,000 steps (62B's Standard/CoT) | Not stated | Step count set by observation, learning rate not stated |
| Toolformer (2302.04761) | Full-parameter SFT on GPT-J | 1e-5 | 128 | Up to 2k steps, checking dev-set PPL every 500 steps and picking the best | Linear warmup over the first 10%, nothing stated afterward | Only the numbers given, no reason |
| Overthinking (2412.21187) | SFT / DPO / RPO / SimPO on QwQ-32B-Preview | Not stated | Not stated | Not stated | Not stated | Zero training hyperparameters in the whole text |
| SDFT (2601.19897) | Full-parameter Qwen2.5-7B-Instruct, SDFT vs. SFT / DFT / CPT baselines | Swept {5e-6, 1e-5, 5e-5} (CPT swept {1e-6, 5e-6, 1e-5}) | Swept {16, 32, 64} | Swept {1, 2} epochs (SDFT on knowledge tasks swept {1, 2, 4}, CPT swept {1, 2, 4, 8}) | Cosine with warmup, 10 warmup steps | All three swept together, picked by validation set |
| Neural Thickets (2603.12228) | GRPO / PPO baselines, Qwen2.5-0.5B/1.5B/3B-Instruct and OLMo3-7B | actor 1e-6, critic 1e-5; Appendix D separately sweeps {1e-5, 1e-6, 1e-7} | 1024 (GRPO), 128 (PPO) | 200 steps (GRPO), 600 steps (PPO) | Not stated | Each method aligned by total FLOPs; Appendix D has one lr x batch-size grid |
| ALFWorld (2010.03768) | BUTLER::Brain (a Transformer seq2seq text agent, DAgger); Mask R-CNN detector | 0.001; detector 5e-4 | 64 (replay-buffer sampling); detector 8 | 50,000 episodes; detector 4 epochs | Not stated | Only the numbers given, no reason |
| Gorilla (2305.15334) | Full-parameter instruction fine-tuning on LLaMA-7B | 2e-5 | 64 | 5 epochs | Cosine decay, warmup ratio 0.03 | Only the numbers given, no reason |
| ToolLLM (2307.16789) | Full-parameter SFT on LLaMA-2 7B | 5e-5 | 64 | 2 epochs, checkpoint picked by dev set | Warmup ratio 4e-2, decay method not stated | Only the numbers given, no reason |

Of the 8, only two state weight decay: SDFT is 0, Gorilla is 0. Only two state gradient clipping: SDFT's Max Grad Norm is 1, ALFWorld's is 5. Three name their optimizer: SDFT uses adamw, Neural Thickets' GRPO/PPO uses AdamW, ALFWorld uses Adam; Toolformer, Gorilla, and ToolLLM state none. None of the 8 uses LoRA (every paper's "lora" word-frequency hits are all substrings like Colorado, exploration, Lora Aroyo).

### 1.2 Each paper's original text

Quotes are copied verbatim throughout; the location given is the paper's section.

ReAct: the training hyperparameters are entirely in Appendix B.1, four sentences in total (the checker independently confirmed Appendix B.1 has only these four sentences): "For all finetuning we use a batch size of 64. On PaLM-8B, we finetune ReAct and Act methods for 4,000 steps and Standard and CoT methods for 2,000 steps. On PaLM-62B, we finetune ReAct and Act methods for 4,000 steps and Standard and CoT methods for 1,000 steps. We find ReAct and Act methods generally benefit from more training steps (and more training data), while Standard and CoT methods degrade soon after finetuning." Learning rate, optimizer, schedule, and weight decay never appear in the whole text ("learning rate" appears 0 times).

Toolformer: Section 4.1: "We finetune M on C* using a batch size of 128 and a learning rate of 1*10-5 with linear warmup for the first 10% of training. Details of our finetuning procedure are given in Appendix B." Appendix B: "We use up to 25k examples per API. Max sequence length 1,024. Effective batch size of 128." "Training up to 2k steps, where we evaluate PPL on a small development set from CCNet containing 1,000 examples every 500 steps. We pick the checkpoint that performs best." Section 4.4 applies the same setup verbatim to GPT-2's four sizes from 124M to 1.6B: "Apart from this, we follow the experimental setup described in Section 4.1." In other words, Toolformer uses the same learning rate, 1e-5, across five sizes from 124M to 6.7B, and the paper does not explain why.

Overthinking (2412.21187): the extractor checked both the arxiv HTML and PDF versions, and "learning rate," "epoch," "batch size," "optimizer," "warmup," "hyperparameter," "1e-," "e-5" all had 0 hits. The paper's only training-related choices are of two kinds: comparisons between methods ("Consequently, SimPO is used as the default post-training method in the subsequent experiments.") and choices in data construction ("However, in our preliminary experiments, we found it less effective than using the longest sampled response as the negative example.").

SDFT: Appendix B.1: "All experiments were conducted using the Hugging Face TRL library. Each experiment was conducted on a single NVIDIA H200 GPU." "For each method, we performed a hyperparameter sweep over learning rates, batch sizes, and training epochs. We report test results for the model checkpoint that achieved the best validation performance on the target task." "Tables 3 and 4 present the full hyperparameter search spaces and final selected values for the Skill Learning and Knowledge Acquisition settings, respectively." Table 3's caption: "Table 3: Hyperparameters used for the Skill Learning experiments. Curly braces {} indicate a sweep over the specified values." In Table 3, the learning-rate row is {5e-6, 1e-5, 5e-5}, the batch-size row is {16,32,64}, the epoch row is {1,2}, and the rest of the rows are single values: Warmup steps 10, Max Grad Norm 1, Weight Decay 0, Optimizer adamw, LR Scheduler "Cosine w. warmup", bfloat16 True. Both the extractor and the checker pointed out one gap: Appendix B.1 says the table has "final selected values," but the learning rate, batch size, and epoch rows in the table only carry the candidate sets in curly braces, and the final chosen value is not printed anywhere. On epoch count, Appendix B.1 has two sentences: "Across all tasks, we found that SDFT benefits from training for multiple epochs" and "In contrast, SFT tends to overfit rapidly and showed no performance gains beyond a single epoch in most cases." Statistical convention: "Unless mentioned otherwise, all experiments were run over 3 random seeds. We report mean performance and 95% confidence intervals across seeds." The example commands at lines 59-60 and 80-81 of the reproduction repo `~/reproduce/SDFT/README.md` write `--learning_rate 5e-5` and `--num_train_epochs 2`; the repo's own `distil_config.py` has a default learning_rate of 1e-6, and the README's command line overrides that default. The value in the repo is evidence from the repo; the paper itself never writes 5e-5 as the selected value.

Neural Thickets (RandOpt): its training is an RL baseline, not the same thing as our SFT; it's recorded here because the paper has two kinds of "how hyperparameters were set." Appendix E.3: "To ensure a fair comparison, we align the hyperparameters such that all methods consume equivalent total training FLOPs. We balance the batch size and iteration counts to account for algorithmic overheads. For instance, GRPO uses a larger batch size (B=1024) compared to PPO (B=128) due to the latter's additional memory cost for the critic network." In Table 3, Actor Learning Rate is 1e-6, Critic Learning Rate is 1e-5, Optimizer is AdamW. Appendix D has one grid: "We grid-search GRPO and PPO on 8 GPUs over learning rates 1e-5, 1e-6, and 1e-7; batch size (PPO) ranges from 128 to 2048, and group size (GRPO) ranges from 512 to 8192." Result: "best accuracy is 78.0% at batch size 256 (lr=1e-5), while larger-batch runs such as batch size 2048 reach at most 77.5%." Section 7's distillation SFT only states the epoch count: "We then select hard examples and perform supervised fine-tuning (SFT) on the base model for 2 epochs, obtaining a distilled model." The learning rate is not stated.

ALFWorld: what is trained is not a language model, but a Transformer seq2seq text agent. Appendix B: "For all experiments, we use Adam (Kingma and Ba,, 2014) as the optimizer." "The learning rate is set to 0.001 with a clip gradient norm of 5." "We sample a batch of 64 data points from the replay buffer." "All text agents are trained for 50,000 episodes." "All experiment settings in TextWorld are run with 8 random seeds." How the model is picked: "For each task category, we select the agent with best evaluation performance in TextWorld (from 8 random seeds)". The only sentence in the whole text that gives a reason is about sequence length: "Following the training strategy used in the recurrent DQN literature". The detector is in Appendix D: "fine-tune the detector for 4 epochs with a batch size of 8 and a learning rate of" 5e-4.

Gorilla: Appendix 8.2: "We train Gorilla for 5 epochs with the 2e-5 learning rate with cosine decay. The details are provide in Tab. 4. We finetune it on 8xA100 with 40G memory each." Table 4 ("Table 4: Hyperparameters for training Gorilla") has six rows: learning rate 2e-5, epochs 5, batch size 64, warmup ratio 0.03, weight decay 0, max seq length 2048. Optimizer, seed, and precision are not stated. The checker enumerated all four tables in the paper; Table 4 is the only hyperparameter table.

ToolLLM: Appendix A.3: "For the training hyper parameters, we use a learning rate of 5x10-5, a warmup ratio of 4x10-2, a total batch size of 64, a maximum sequence length of 8192, and use a position interpolation ratio of 2." "We train the model for two epochs and select the model checkpoint" "with the best performance on the development set." Optimizer, decay method, weight decay, and gradient clipping are all not stated.

### 1.3 The 7 that trained nothing

ACE, AEL, tau2-Bench, TALES, AppWorld, StableToolBench, and ToolHop are all prompting, evaluation, or environment papers; the checker re-searched each one for "fine-tun," "learning rate," "epoch," "LoRA," "optimizer," and every one turned up zero training settings.

One record among these 7 of "picking a value on the dev set" is worth keeping as a comparison point: AppWorld Appendix E.4, on the cap on inference-time turns: "We allow a maximum of 15 turns (each consisting of a batch of any number of function calls). We tried the limit of 10, 15, and 20 on the Dev set and found the performance to saturate at 15." This is an inference setting, not a training hyperparameter.

## 2 First-hand web sources

### 2.0 How this part was searched

The web batch was searched from 10 angles, each handled independently: official model fine-tuning recipes, LoRA literature, full-parameter learning-rate sweeps, warmup and schedule, epoch and batch size, training library defaults, weight decay and gradient clipping, probe training, cross-model-scale transfer, tool-call SFT recipes. For each angle, one opus was responsible for searching and copying verbatim quotes only from raw text it fetched to the local machine itself (arxiv HTML / PDF / GitHub source files / official doc pages), and a second opus re-fetched each URL through a different route, and rechecked every quote with `grep -c -F` and every number. The 10 angles produced 96 findings in total; the checker fetched the raw web page for all 96, all 96 quotes hit verbatim, 73 were confirmed whole, 23 were partially_confirmed. Not one of the 23 partial ones had a wrong quote or a wrong hyperparameter number; they were all slips by the searcher in the "numbers" or "paraphrase" transcription fields (for example, one paper's training step count was written as 10^4 when the original text says 50,000 steps; one quote was attributed to an SFT paragraph when the original was in a PPO paragraph) or the "how it was chosen" tag was stronger than the original evidence. The checkers also each added one first-hand source the searcher had missed (Llama 2, QLoRA, InstructGPT, Qwen2, ToolAlpaca, LoRA Land, Tenney 2019, the alignment-handbook's zephyr config); the checker fetched and verified these added quotes verbatim themselves, marked below as "added by the checker."

The sections below are organized by hyperparameter, each listing a table first and then quoting the original text. The "how it was chosen" column in the tables has only four values: swept (the original states which values were swept), followed (the original states whose value it follows), only the number given (a number with no reason), no number stated.

The raw search and checking results are in `/home/y-guo/.claude/jobs/f768d4d4/tmp/web_result.json`.

### 2.1 Full-parameter fine-tuning learning rate

| Source | Model size | Full-parameter SFT learning rate | How it was chosen |
|---|---|---|---|
| Tulu 3 (arXiv 2411.15124) | Llama 3 8B / 70B / 405B | 8B 5e-6, 70B 2e-6, 405B 2e-6 | Swept: on 8B swept {2e-6, 5e-6, 1e-5, 2e-5} x loss sum vs. mean x epoch 2 to 7 |
| OLMo 2 (arXiv 2501.00656) | 7B / 13B / 32B | 7B 2e-5, 13B 5e-6, 32B 4e-6 | Swept: each size swept separately, 7B swept {1e-5, 2e-5, 3e-5}, 13B swept {1e-6, 4e-6, 5e-6, 7.5e-6, 8e-6}, 32B swept {1e-6, 2e-6, 3e-6, 4e-6, 5e-6} |
| Unveiling the Secret Recipe (arXiv 2412.13337) | Granite 3B / 7B, Llama 3.2 3B, Mistral 7B | Granite 2e-5, Mistral 1e-6 | Swept: {1e-6, 5e-6, 2e-5, 3e-5, 4e-5, 6e-5, 8e-5, 1e-4} |
| Massive SFT experiments (arXiv 2506.14681) | Llama 3 8B | 1e-5 | Swept: learning rate {2e-7, 1e-6, 2e-6, 1e-5, 2e-5, 1e-4} x batch {32, 64, 128, 256} x weight decay {0, 0.1} x {LoRA, full-parameter}, 96 combinations |
| LoRA Learns Less and Forgets Less (arXiv 2405.09673) | Llama 2 7B | code task 5e-5, math task 1e-5 | Swept: [1e-5, 5e-4] |
| InstructGPT (arXiv 2203.02155, added by the checker) | 1.3B / 6B / 175B | 1.3B and 6B 9.65e-6, 175B 5.03e-6 | Swept: "a geometric search over 7 LRs" |
| DeepSeek LLM (arXiv 2401.02954) | 7B / 67B | 7B 1e-5, 67B 5e-6 | Only the number given (the epoch-count change has a reason given) |
| The LoRA original paper (arXiv 2106.09685) Table 12 | GPT-3 175B | 5e-6 | Swept: "We use the same hyperparameters for all datasets after tuning learning rate." |
| Llama 2 (arXiv 2307.09288, added by the checker) | 7B to 70B | 2e-5, cosine | Only the number given |
| Llama 3 (arXiv 2407.21783) | Largest model | 1e-5, 8.5K to 9K steps | Only the number given |
| Qwen2.5 technical report (arXiv 2412.15115) | Whole family | Decreasing from 7e-6 to 7e-7 | Only the number given |
| Qwen3 technical report (arXiv 2505.09388) | Whole family | No number stated | Not a single learning-rate number in the whole text |
| SmolLM2 (arXiv 2502.02737) | 1.7B | 3.0e-4 | Only the number given |
| Alpaca (GitHub README) | LLaMA 7B / 13B | 7B 2e-5, 13B 1e-5 | Only the number given |
| Tulu 1 (arXiv 2306.04751) | 7B to 65B | 2e-5, 30B and 65B use 1e-5 | Only the number given |
| Tulu 2 (arXiv 2311.10702) | 7B to 70B | 2e-5, 70B uses 1e-5 | Only the number given |
| LIMA (arXiv 2305.11206) | 65B | 1e-5 linearly decayed to 1e-6 | Followed: "We follow standard fine-tuning hyperparameters" |
| APIGen / xLAM-1B, 7B (arXiv 2406.18518) | 1.3B / 6.7B | 5e-6, same value for both sizes | Only the number given |
| Gorilla (arXiv 2305.15334) | LLaMA 7B | 2e-5 | Only the number given |
| ToolLLM (arXiv 2307.16789) | LLaMA 2 7B | 5e-5 | Only the number given |
| ToolAlpaca (arXiv 2306.05301, added by the checker) | Vicuna 7B / 13B | 2e-5 | Only the number given |
| Qwen's official finetune script (QwenLM/Qwen) | Size-agnostic | 1e-5 | Only the number given |
| LLaMA-Factory Qwen3 example config | Qwen3-4B | 1e-5 | Only the number given |
| torchtune Qwen3 config | 0.6B / 1.7B / 4B / 8B | 0.6B 2e-5, 1.7B 2e-5, 4B 5e-6, 8B 5e-6 | Only the number given |
| TRL SFTConfig default | Size-agnostic | 2e-5 | Library default |
| transformers TrainingArguments default | Size-agnostic | 5e-5 | Library default |

Three passages of original text. Tulu 3 Section 4: "We used an effective batch size of 128 and a maximum sequence length of 4,096 tokens. We trained for two epochs using a learning rate of 5e-6 for our 8B models, and 2e-6 for our 70B models, which we found after a hyperparameter search." OLMo 2's appendix: "We conducted a hyperparameter sweep for SFT and DPO, using earlier development checkpoints, with results detailed in Table 17 and Figure 12. A key finding was that OLMo 2 required significantly higher learning rates compared to the Llama 3.1 training recipe described by Lambert et al. (2024)." OLMo 2's Table 17 gives average scores for six 7B configurations: 2 epoch / 1e-5 / sum three runs are 49.97, 49.74, 49.59; 3 epoch / 4e-6 / sum is 49.76; 3 epoch / 4e-6 / mean is 48.25; 2 epoch / 2e-6 / mean is 48.18. Unveiling the Secret Recipe: "Low learning rates are crucial for optimal performance. We found that 2x10^-5 works well for Granite models, while 1x10^-6 performs best for Mistral. [...] Practitioners should start with these values and, if necessary, perform a localized search by testing slightly higher or lower learning rates to find the optimal setting for their specific model."

Llama 3's entire explanation of its own 1e-5 is one sentence: "We found these hyperparameter settings to work well across different rounds and data mixes." Alpaca's README says of batch size: "Global batch size has not been tested for optimality."

### 2.2 LoRA's learning rate, rank, alpha, dropout

| Source | Model size | Rank r / alpha / dropout | LoRA learning rate | How it was chosen |
|---|---|---|---|---|
| The LoRA original paper (arXiv 2106.09685) | GPT-3 175B; GPT-2 | GPT-2: r=4, alpha=32 | GPT-3 2e-4 (same table's full-parameter is 5e-6); GPT-2 2e-4 | Learning-rate swept; alpha not tuned |
| QLoRA (arXiv 2305.14314) | LLaMA 7B to 65B | r=64, alpha=16; dropout 0.1 (7B, 13B) / 0.05 (33B, 65B); all linear layers | 7B, 13B 2e-4; 33B, 65B 1e-4 | Swept: dropout {0, 0.05, 0.1}, r {8, 16, 32, 64, 128, 256}, five kinds of target layers; alpha fixed, learning rate swept |
| LoRA Learns Less and Forgets Less (arXiv 2405.09673) | Llama 2 7B | r in {16, 64, 256}, alpha=2r, dropout 0.05, seven projections | Best value 2e-4 (math) / 5e-4 (code); r=256 uses 1e-4 | Swept [1e-5, 5e-4] |
| LoRA Without Regret (Thinking Machines blog, 2025) | 14 Llama and Qwen models | r swept from 1 to 512; alpha=32 | LoRA's optimal learning rate is 10x full-parameter's (fitted value 9.8) | Swept; alpha is convention |
| Learning Rate Scaling across LoRA Ranks (arXiv 2602.06204) | Theory plus six experiment groups | Under standard alpha/r scaling, the optimal learning rate doesn't move with r, drops with width as n^(-1/2) | Formula | Theory |
| Beware of the Batch Size (arXiv 2602.09492) | LLaMA 2 7B / 13B | r in {32, 64, 128, 256} | Each batch size swept 1e-5 to 3e-3 | Swept |
| LoRA vs Full Fine-tuning: An Illusion of Equivalence (arXiv 2410.21228) | RoBERTa | alpha=2r vs. alpha=8 compared | alpha*eta held at 2.4e-3 | Followed |
| Tulu 2 QLoRA (arXiv 2311.10702) | 7B to 70B | r=64, alpha=16, dropout 0.1 | 1e-4, 5 epochs | "found in smaller-scale experiments" |
| Lightning AI LoRA insights (Raschka, 2023) | Llama 2 7B | Tried r=8/alpha=16 and r=16/alpha=32 | 3e-4 | Swept |
| ToolACE (arXiv 2409.00920) | Llama 3.1 8B | r=16, alpha=32, all modules | 1e-4, 3 epochs | "one of the most common settings" |
| RouteNator (arXiv 2505.10495) | Seven models, 0.5B to 7B | r=16, alpha=32, dropout 0.05, seven projections | 1e-4, 3 epochs, clip 0.3 | Only the number given, fixed across sizes for comparability |
| Internalizing Tool Knowledge (arXiv 2605.17774) | Gemma 4 E4B, Qwen3 | r swept {8, 16, 32, 64}, peak at 32; alpha=64 | 2e-4, 2 epochs | Rank swept |
| Octopus v2 (arXiv 2404.01744) | Gemma 2B | r=16, alpha=32, six projections | 5e-5, same value as full-parameter | Only the number given |
| Granite-Function Calling (arXiv 2407.00121) | 20B | QLoRA r=8, alpha=32, dropout 0.1 | 5e-5, 3 epochs | Only the number given |
| SimpleTool (arXiv 2603.00030) | Qwen3-4B | r=512, alpha=1024 | 1e-5 | Rank swept {64, 256, 512, 1024} |
| alignment-handbook zephyr-7b-beta (added by the checker) | Mistral 7B | r=16, alpha=16, dropout 0.05, seven projections | 2e-4, 1 epoch | Only the number given |
| PEFT LoraConfig default | Size-agnostic | r=8, alpha=8, dropout 0.0 | No learning rate in the library | Library default |
| Unsloth documentation | Size-agnostic | r chosen as 16 or 32; alpha=r or 2r; dropout 0 | 2e-4 as a starting point | Recommendation |
| LLaMA-Factory Qwen3 example | Qwen3-4B | r=8, alpha default 2r, all linear layers | 1e-4 | Only the number given |
| Axolotl Qwen3 example | 8B / 32B | r=32/alpha=64 or r=16/alpha=32, dropout 0 | 2e-4 | Only the number given |
| torchtune Qwen3 config | 0.6B to 32B | 0.6B, 1.7B r=32/alpha=64; 4B and above r=8/alpha=16 | 0.6B 1e-4, 1.7B 2e-5, 4B and above 3e-4 | Only the number given |
| Qwen's official finetune script | Size-agnostic | r=64, alpha=16, dropout 0.05 | 3e-4 | Only the number given |

The LoRA original paper's own words on alpha: "When optimizing with Adam, tuning alpha is roughly the same as tuning the learning rate if we scale the initialization appropriately. As a result, we simply set alpha to the first r we try and do not tune it." QLoRA's own words: "We keep LoRA alpha fixed and search the learning rate, since LoRA alpha is always proportional to the learning rate. We find that LoRA dropout 0.05 is useful for small models (7B, 13B), but not for larger models (33B, 65B). We find LoRA r is unrelated to final performance if LoRA is used on all layers". LoRA Learns Less and Forgets Less's conclusion paragraph: "we recommend: (a) using LoRA for instruction finetuning and not continued pretraining; (b) if GPU memory allows, targeting "All" transformer modules with a rank of 256, since ranks 16-64 tend not to suffice for code tasks; (c) using alpha = 2r, and (d) sweeping over learning rates between [1e-5, 5e-4], picking the highest value that enables stable training." Same paper: "LoRA's best learning rates should be set one order of magnitude higher than that of full finetuning, often ranging between 5e-5 and 5e-4 for these combinations of model architecture and dataset." LoRA Without Regret: "Our experiments showed that the optimal LR for LoRA is consistently 10x the one used for FullFT in the same application, for both supervised learning and reinforcement learning." And on alpha: "We use alpha=32 for the experiments in this article, following standard practice from other implementations." ToolACE: "As for the hyper-parameters setting, we adopt one of the most common settings, which sets the rank as 16 and alpha as 32 for all modules." LoRA+ (arXiv 2402.12354)'s description of the state of LoRA learning rates: "there are no principled guidelines on how to set the learning rate, apart from common choices of order 1e-4."

### 2.3 Epoch count

| Source | Data volume | Epochs | How it was chosen |
|---|---|---|---|
| Tulu 3 | About a million | 2 | Swept 2 to 7, "training for longer did not yield further improvements" |
| SDFT (local §1) | A few thousand to tens of thousands per task | Swept {1, 2} | "SFT tends to overfit rapidly and showed no performance gains beyond a single epoch in most cases" |
| DeepSeek LLM | Not stated | 4 for 7B, 2 for 67B | "since we observed the overfitting problem is serious on the 67B model" |
| Lightning AI LoRA insights | Alpaca, 50,000 | 1 pass better than 2 | Swept: "the increased iterations result in worse performance across the board" |
| OLMo 2 Table 17 | Same data | 2 vs. 3 differ by 0.2 points, three repeats of the same config differ by 0.38 points | Swept |
| InstructGPT (added by the checker) | Not stated | 16, residual dropout 0.2 | The original states how it was chosen, the checker only quoted the learning-rate sentence |
| LIMA | 1,000 | Trained 15, hand-picked from epoch 5 to 10 | "perplexity does not correlate with generation quality" |
| Massive SFT experiments | About 1,000 per episode | 10, one version saved per epoch | Swept |
| Alpaca / Vicuna / ToolAlpaca / ToolACE / Granite / Octopus v2 / RouteNator | Varies | 3 | Only the number given |
| Gorilla | About 16,000 | 5 | Only the number given |
| APIGen | Not stated | 4 | Only the number given |
| ToolLLM / Llama 2 / Qwen2.5 / Tulu 1 / Tulu 2 / SmolLM2 | Hundreds of thousands to a million | 2 | Only the number given |
| Scaling Data-Constrained LMs (arXiv 2305.16264, pretraining) | Up to 900 billion tokens | Loss barely changes up to 4 repeats, degrades sharply past 16 | Fitted scaling law |
| transformers TrainingArguments / LLaMA-Factory | Agnostic | 3 | Library default |
| torchtune / Axolotl | Agnostic | 1 | Library default |

Tulu 3's own words: "Surprisingly, we additionally found that training for longer did not yield further improvements, and so used 2 epochs for training." Scaling Data-Constrained Language Models' own words: "while models trained for a single epoch consistently have the best validation loss per compute, differences tend to be insignificant among models trained for up to 4 epochs and do not lead to differences in downstream task performance. ... The returns from additional epochs may heavily depend on hyperparameters such as learning rate, dropout, or the optimizer choice." This one is a pretraining paper, and the checker tagged it "different from our SFT setting."

### 2.4 Batch size

| Source | Effective batch size | How it was chosen |
|---|---|---|
| Massive SFT experiments (8B full-parameter) | 32 chosen from {32, 64, 128, 256} | Swept |
| Unveiling the Secret Recipe (3B / 7B) | Three levels 128, 3,840, 7,680, bigger always better | Swept |
| Beware of the Batch Size (LoRA) | An internal optimum exists, batch size alone can swing more than 10 points; the optimum doesn't move with r or model size, moves with data volume | Swept |
| LoRA Without Regret (LoRA) | LoRA is less tolerant of large batches; TRL's documentation recommends effective batch under 32 based on this | Swept |
| QLoRA | 7B, 13B use 16; 33B uses 32; 65B uses 64 | Swept then doubled by size |
| InstructGPT (added by the checker) | 1.3B, 6B use 32; 175B uses 8 | Swept |
| Tulu 3 / OLMo 2 / Alpaca / Vicuna / ToolAlpaca / Tulu 2 | 128 | Only the number given (Alpaca states outright it was never tested) |
| Llama 2 / Gorilla / ToolLLM / ReAct | 64 | Only the number given |
| ToolACE | 48 | Only the number given |
| APIGen | 6 per card, 2 accumulation steps | Only the number given |
| RouteNator / LLaMA-Factory LoRA example | 8 | Only the number given |
| torchtune | 2 x 8 = 16 | Library default |
| Measuring the Effects of Data Parallelism (arXiv 1811.03600) | No universal value; changing batch size requires retuning all optimization parameters | Swept |
| Three critical-batch-size papers (arXiv 1812.06162, 2001.08361, 2410.21676) | Critical batch size is set by loss or data volume, not directly by model size | Fitted |

Measuring the Effects of Data Parallelism's own words: "We were unable to find reliable support for any of the previously proposed heuristics for adjusting the learning rate as a function of batch size. Thus we are forced to recommend that practitioners tune all optimization parameters anew when they change the batch size or they risk masking the true behavior of the training procedure."

### 2.5 Warmup and learning-rate schedule

| Source | Warmup | Schedule | How it was chosen |
|---|---|---|---|
| Tulu 3 | Ratio 0.03 | Linear decay | Only the number given |
| OLMo 2 | Printed as 0.3 | Linear | Only the number given |
| Llama 2 SFT | Not stated | Cosine | Only the number given |
| Qwen2.5 / Qwen2 SFT | Not stated | 7e-6 down to 7e-7 | Only the number given |
| Gorilla | Ratio 0.03 | Cosine | Only the number given |
| ToolLLM | Ratio 0.04 | Not stated | Only the number given |
| Toolformer (local) | Linear over first 10% | Not stated | Only the number given |
| APIGen | 50 steps | Cosine | Only the number given |
| xLAM | 100 steps | Cosine | Only the number given |
| Octopus v2 | 10 steps | Linear | Only the number given |
| LIMA / InstructGPT | No warmup | Linear to 1e-6 / cosine to 10% | Followed / swept |
| Unveiling the Secret Recipe | Tried 0, 25, 100 steps, 0 steps no worse | Constant learning rate ties cosine | Swept |
| LoRA Without Regret | No warmup | Constant | Swept |
| transformers TrainingArguments | Default 0 | Default linear | Library default |
| LLaMA-Factory / Axolotl | Ratio 0.1 | Cosine | Library example |
| Unsloth documentation | 5% to 10% | Linear or cosine | Recommendation |
| Why Warmup the Learning Rate? (arXiv 2406.09405, small models) | Warmup's role is keeping a higher peak learning rate from diverging; lengthen it if there are spikes | | Swept |
| Analyzing & Reducing the Need for LR Warmup (arXiv 2410.23922, 124M pretraining) | Swept 0%, 2%, 5%, 10%, 20%; no warmup leaves a permanent gap, short warmup suffices | | Swept |
| Straight to Zero (arXiv 2502.15938, pretraining) | All 10% | Linear decay to 0 beats decay to 1/10 or cosine | Swept |
| Scaling Laws and Compute-Optimal Training Beyond Fixed Training Durations (arXiv 2405.18392, pretraining) | | Constant plus 10% to 20% cooldown ties or beats cosine | Swept |
| MiniCPM (pretraining) | "as long as the warmup stage is enough, it affects little performance" | 10% decay segment suffices | Swept |

Analyzing & Reducing the Need for Learning Rate Warmup's own words: "Not using warmup results in faster initial progress for a given learning rate, but eventually falls behind leaving a permanent gap. [...] Although we present new methods we consider promising, we still recommend the use of a short warmup in practice." Unveiling the Secret Recipe's own words on SFT: "Our experiments indicate that omitting warmup steps and using a constant learning rate instead of cosine decay does not negatively impact performance, simplifying the training process without sacrificing model quality." The checker tagged all four scheduling papers as "a pretraining setting, not SFT"; the Secret Recipe paper is SFT.

### 2.6 Weight decay and gradient clipping

| Source | Weight decay | Gradient clipping | How it was chosen |
|---|---|---|---|
| The AdamW original paper (arXiv 1711.05101) | The optimum changes with the number of update steps, no fixed number given; "0.01" never appears in the text | | Theory plus sweep |
| PyTorch `torch.optim.AdamW` | Default 1e-2 | | Library default, no explanation in source |
| transformers TrainingArguments | Default 0.0, documentation says "Typical values: 0.01 (standard), 0.1 (stronger regularization), 0.0" | Default 1.0, documentation says "Typical values: 1.0 (standard), 0.5 (more conservative), 5.0 (less aggressive)" | Library default |
| Massive SFT experiments (8B) | Swept {0, 0.1}, chose 0 | | Swept |
| Qwen2.5 / Qwen2 SFT | 0.1, "To address overfitting" | 1.0 | Only the number given |
| Llama 2 SFT | 0.1 | Not stated for the SFT segment (1.0 for the PPO segment) | Only the number given |
| GPT-3 (pretraining) | 0.1, "to provide a small amount of regularization" | 1.0 | Only the number given |
| LIMA | 0.1 | | Followed |
| Tulu 1 / Tulu 2 / Gorilla / Alpaca / SDFT / LoRA Learns Less | 0 | SDFT 1; LoRA Learns Less 1 | Only the number given |
| QLoRA | | 0.3 | Only the number given |
| RouteNator | | 0.3 | Only the number given |
| ALFWorld (local) | | 5 | Only the number given |
| Tenney 2019 probe (added by the checker) | | 5.0 | Only the number given |
| Unsloth documentation | 0.01, up to 0.1 | | Recommendation |
| Pascanu 2013 (arXiv 1211.5063, the origin of gradient clipping) | | Threshold set from the average gradient norm in one's own training; the original text uses 6 and 45; 1.0 never appears | Empirical |

Pascanu's own words: "One good heuristic for setting this threshold is to look at statistics on the average norm over a sufficiently large number of updates. In our experiments we have noticed that for a given task and model size, training is not very sensitive to this hyperparameter and the algorithm behaves well even for rather small thresholds." The AdamW original paper's own words: "Optimal weight decay depends on the total number of batch passes/weight updates. Our empirical analysis of SGD and Adam suggests that the larger the runtime/number of batch passes to be performed, the smaller the optimal weight decay." Across all 10 angles, the checker did not find a single first-hand source explaining why the clipping threshold is set to 1.0 rather than 0.5 or 5.0.

### 2.7 The same set of hyperparameters across model scales

| Source | Scenario | Cross-scale approach |
|---|---|---|
| Tulu 3 | SFT 8B -> 70B | Learning rate 5e-6 -> 2e-6, the reason cited: "it is common to lower the learning rate and increase batch size when doing SFT with larger models (Touvron et al., 2023)" |
| QLoRA | LoRA 7B -> 65B | "all hyperparameter settings found at 7B generalize (including number of epochs) except learning rate and batch size. We halve the learning rate for 33B and 65B while doubling the batch size." |
| OLMo 2 | SFT 7B / 13B / 32B | Each size swept separately, 2e-5 / 5e-6 / 4e-6 |
| DeepSeek LLM | SFT 7B -> 67B | Learning rate 1e-5 -> 5e-6, epoch 4 -> 2 |
| Alpaca | SFT 7B -> 13B | 2e-5 -> 1e-5, epoch 3 -> 5 |
| Tulu 1 / Tulu 2 | SFT 7B -> 65B / 70B | 2e-5 -> 1e-5 |
| InstructGPT (added by the checker) | SFT 1.3B / 6B -> 175B | 9.65e-6 -> 5.03e-6, batch 32 -> 8 |
| Llama 2 reward model (added by the checker) | 7B to 70B | 70B uses 5e-6, the rest use 1e-5 |
| torchtune Qwen3 config | Full-parameter 0.6B to 8B | 0.6B, 1.7B 2e-5; 4B, 8B 5e-6 |
| When Scaling Meets LLM Finetuning (arXiv 2402.17193) | 1B to 16B | Grid search for learning rate and batch size only at 1B, then followed at all sizes |
| Toolformer (local) | 124M to 6.7B | Same setup |
| RouteNator | 0.5B to 7B LoRA | Same setup, for comparability |
| LoRA Land (arXiv 2405.00732, added by the checker) | 2B to 8B LoRA | "We deliberately maintain that all LLMs are fine-tuned with the same training parameters" |
| Unveiling the Secret Recipe | Granite and Mistral, both 7B | Optimal learning rates differ 20x (2e-5 vs. 1e-6) |
| OLMo 2 | Same 7B class | The Llama 3.1 recipe's learning rate is too low for OLMo 2 |
| Kaplan 2020 (pretraining) | | LR(N) ~ 0.003239 - 0.0001395 log(N) |
| muP / Tensor Programs V (arXiv 2203.03466) | Pretraining | Under standard parameterization, width 256 -> 8192 shifts the optimal learning rate about one order of magnitude; under muP it doesn't move |
| Cerebras-GPT (arXiv 2304.03208) | Pretraining, 111M to 13B | Standard parameterization 6e-4 -> 1.2e-4; muP is 6e-3 throughout |
| MiniCPM / muP empirical study (arXiv 2404.05728) | Pretraining | muP's base learning rate doesn't move from 0.04B to 2.1B; the same 2^-6 is optimal from 2M to 10B |
| Scaling Exponents (arXiv 2407.05872) | Pretraining | After per-layer scaling, the base learning rate's exponent with width is about -0.05 |
| Learning Rate Scaling across LoRA Ranks (arXiv 2602.06204) | LoRA | Under standard alpha/r scaling, the optimal learning rate is proportional to n^(-1/2), where n is width |
| LoRA Without Regret | LoRA and full-parameter | The optimal learning rate is fitted as a power of (2000 / hidden size) |

On this angle, what the checker wrote in the "not found" column is: not one source gives a rule for how epoch count should change with model size at the SFT stage, DeepSeek's one sentence is the sole observation; nor does any source give a formula for how the SFT-stage learning rate scales with size, every formula comes from pretraining.

### 2.8 Training probe heads

| Source | Probe | Optimization setting | How it was chosen |
|---|---|---|---|
| Alain & Bengio 2016 (arXiv 1610.01644) | Linear probe | Only states early stopping on a 10^4-example validation set | No number stated |
| Hewitt & Liang 2019 (control tasks) | Linear / MLP | Adam; halve the learning rate if dev-set loss doesn't drop, stop after 4 in a row; weight decay swept {0.01, 0.1, 1.0, 10.0}, dropout swept {0.2, 0.4, 0.6, 0.8}, step count swept {50000 ... 1500} | Swept, chosen by selectivity |
| Voita & Titov 2020 (MDL probing) | MLP | Adam 0.001, followed Hewitt & Liang's halving rule | Followed |
| Hewitt & Manning 2019 (structural probe) | Linear transform | Adam 0.001, batch 20, up to 40 epochs, reset on plateau with learning rate x 0.1 | Only the number given |
| Tenney 2019 (added by the checker) | Edge probing | Adam, batch 32, learning rate 1e-4, clip 5.0 | Only the number given |
| CCS (arXiv 2212.03827) | Linear direction | AdamW 0.01, 1000 epochs, 10 restarts taking the lowest loss | "which we found was good for consistently achieving low unsupervised loss" |
| Tuned Lens (arXiv 2303.08112) | Affine | SGD Nesterov, learning rate 1.0, 250 steps, clip 1, weight decay 1e-3 | Only the number given |
| SAPLMA (arXiv 2304.13734) | Three-layer MLP | Adam, 5 epochs, "We do not fine-tune any of these hyper-parameters for this task." | States outright it wasn't tuned |
| scikit-learn LogisticRegression | Linear | L-BFGS, C=1.0; LogisticRegressionCV cross-validates over a 10-point log grid from 1e-4 to 1e4 | Library default |

These probes all freeze the backbone and train only the head. Our ctool head (`Linear(hidden->150)`) trains together with the backbone and shares one learning rate with it, a different approach from these sources, so this subsection is background only.

## 3 Our settings placed alongside the first two sections (facts only)

| Our setting | Value | Where the value came from (per §0 and prior verification) | Values from sources in §1/§2 that swept | Values from sources in §1/§2 that only gave a number |
|---|---|---|---|---|
| Full-parameter learning rate | 1e-5 | The value from when the script was written on 2026-07-31, no reason recorded, locked on 08-21 | 7B to 8B: Tulu 3 5e-6, OLMo 2 2e-5, Massive SFT 1e-5, LoRA Learns Less 1e-5 / 5e-5, Secret Recipe 2e-5 (Granite) / 1e-6 (Mistral); 1.3B to 6B: InstructGPT 9.65e-6; GPT-3 175B: 5e-6 | Under 2B: SmolLM2 1.7B 3e-4, torchtune 0.6B / 1.7B 2e-5, APIGen 1.3B 5e-6, Toolformer 124M to 6.7B 1e-5; 4B: torchtune 5e-6, LLaMA-Factory 1e-5; 7B class: Llama 2 2e-5, Gorilla 2e-5, ToolLLM 5e-5, Alpaca 2e-5, Qwen2.5 starting at 7e-6 |
| LoRA learning rate | 2e-4, 20x full-parameter's | `lora_util.py` line 33's default value, the repo states outright it's convention, not tuned | The LoRA original paper 2e-4 (full-parameter 5e-6, 40x); QLoRA 7B / 13B 2e-4; LoRA Learns Less 2e-4 to 5e-4 best, uses 1e-4 in practice (full-parameter 5e-6, 20x); LoRA Without Regret 10x full-parameter's; Internalizing Tool Knowledge 2e-4 | ToolACE 1e-4, RouteNator 1e-4, zephyr 2e-4, Unsloth 2e-4, Axolotl 2e-4, LLaMA-Factory 1e-4 (full-parameter 1e-5, 10x), Qwen script 3e-4 (full-parameter 1e-5, 30x), torchtune 0.6B 1e-4 / 1.7B 2e-5 / 4B 3e-4, Octopus v2 5e-5 (same as full-parameter), SimpleTool Qwen3-4B 1e-5 |
| LoRA r / alpha / dropout | 16 / 32 / 0.05, seven projections | Convention default, not tuned | QLoRA: dropout 0.05 helps 7B, 13B, r on all linear layers is unrelated to the result; LoRA Learns Less: alpha=2r, r 16 to 64 insufficient for code tasks; Internalizing Tool Knowledge: r peaks at 32 within {8, 16, 32, 64}; Lightning: r=16/alpha=32 beats r=8/alpha=16 | ToolACE r=16/alpha=32 "one of the most common settings"; RouteNator r=16/alpha=32/dropout 0.05, seven projections; zephyr r=16/alpha=16/dropout 0.05, seven projections; PEFT default r=8/alpha=8/dropout 0; LoRA Without Regret alpha=32 is convention |
| Epochs | 3, keeping the version with the lowest val_ce | Locked on 08-21 | Tulu 3 swept 2 to 7, chose 2; SDFT's SFT gains nothing past 1; Lightning's 2nd pass is worse than the 1st; OLMo 2's 2 vs. 3 are within noise; DeepSeek 67B dropped from 4 to 2 due to overfitting | 3: Alpaca, Vicuna, ToolAlpaca, ToolACE, Granite, Octopus v2, RouteNator, the TrainingArguments default, LLaMA-Factory; 2: ToolLLM, Llama 2, Qwen2.5, Tulu 1 / 2; 5: Gorilla; 4: APIGen |
| Effective batch size | 32 | Locked on 08-21 | Massive SFT's full-parameter chose 32 from {32, 64, 128, 256}; QLoRA 7B 16; InstructGPT 1.3B / 6B 32; Secret Recipe bigger is always better (3,840 vs. 128); on the LoRA side: Beware of the Batch Size has an internal optimum, LoRA Without Regret recommends under 32 | 128: Tulu, OLMo 2, Alpaca; 64: Llama 2, Gorilla, ToolLLM, ReAct; 48: ToolACE; 16: torchtune; 8: RouteNator |
| Warmup and schedule | 5% linear warmup, linear decay to 0 | Followed from p1 | Secret Recipe: SFT with no warmup and a constant learning rate is no worse; four pretraining papers: short warmup suffices, linear decay to 0 is best | Tulu 3 0.03 linear; Gorilla 0.03 cosine; ToolLLM 0.04; Toolformer 10%; LLaMA-Factory / Axolotl 0.1 cosine; TrainingArguments default no warmup, linear; LIMA / InstructGPT no warmup |
| Weight decay | 0.01 | Equal to PyTorch AdamW's default | Massive SFT swept {0, 0.1}, chose 0 | 0.1: Qwen2.5, Llama 2, LIMA, GPT-3; 0: Tulu 1 / 2, Gorilla, Alpaca, SDFT, LoRA Learns Less; TrainingArguments default 0, documentation calls 0.01 standard |
| Gradient clipping | 1.0 | Convention | No source has swept or explained 1.0 | 1.0: Qwen2.5, GPT-3, SDFT, LoRA Learns Less, the TrainingArguments default; 0.3: QLoRA, RouteNator; 5: ALFWorld, Tenney |
| Across 0.6B / 1.7B / 4B | The same set of values | 08-21 ruling: only vary backbone size, one variable at a time | Swept and changed the learning rate by size: Tulu 3, QLoRA, OLMo 2, InstructGPT; swept once then followed across all sizes: When Scaling Meets LLM Finetuning | Lowered the learning rate by size: DeepSeek, Alpaca, Tulu 1 / 2, torchtune; same set across all sizes: Toolformer, RouteNator, LoRA Land, APIGen |

The three backbones' widths (`config.json`'s `hidden_size`, on the NFS model directory): Qwen3-0.6B-Base 1024, Qwen3-1.7B-Base 2048, Qwen3-4B-Base 2560. By arXiv 2602.06204's n^(-1/2) rule, the optimal-LoRA-learning-rate ratio from 0.6B to 1.7B is (1024/2048)^(1/2) = 0.71, and from 0.6B to 4B is (1024/2560)^(1/2) = 0.63.

## 4 Interpretation

What follows is my interpretation; the facts in the first three sections do not depend on this section.

On the full-parameter learning rate of 1e-5: this value falls inside the range given by sources that swept. The optimal values swept at 7B to 8B spread from 1e-6 to 2e-5, the one sweep at 1.3B to 6B (InstructGPT) landed at 9.65e-6, and 1e-5 sits in the middle of that range. But two things are plain from these sources: first, the optimal value can differ 20x across different backbones at the same size (Secret Recipe's Granite versus Mistral), and OLMo 2 states outright that Llama's recipe was too low for it, so other people's swept values can only indicate the order of magnitude, not the optimum on Qwen3-Base; second, no source has ever swept an SFT learning rate on Qwen3, the Qwen3 report itself prints not one learning-rate number, and torchtune's Qwen3 values of 2e-5 for 0.6B/1.7B and 5e-6 for 4B are also unexplained configuration values. 1e-5 is a value correct in order of magnitude but never verified on this backbone.

On LoRA's 2e-4 and r=16 / alpha=32 / dropout 0.05: these four numbers are exactly the same set ToolACE calls the "most common setting," and RouteNator uses the same set from 0.5B to 7B, so the claim of "convention" has empirical support in the literature. Looking at what sources that swept say about these four numbers separately: alpha=2r has three papers supporting it (LoRA Learns Less, Lightning, and Illusion of Equivalence's alpha=8 comparison performing worse); dropout 0.05 has QLoRA's support, which states outright it helps under 7B; r=16 has two dissenting opinions pointing different directions, with LoRA Learns Less saying r 16 to 64 is insufficient for code tasks, QLoRA saying r is unrelated to the result when applied to all linear layers, and Internalizing Tool Knowledge sweeping to a peak of 32 on tool tasks. The learning rate 2e-4 is itself the best value or next to it in all three sweeps, but its ratio to our full-parameter 1e-5 is 20x, while the two sources that specifically measured this ratio (LoRA Learns Less, LoRA Without Regret) both give about 10x. This 20x moves in the same direction as the LoRA original paper's 40x and the Qwen script's 30x, one notch above the ten-times rule. If one of the two numbers is off, the existing evidence cannot tell whether the full-parameter 1e-5 is too low or the LoRA 2e-4 is too high.

On 3 epochs: not one source that swept epochs supports a gain from the 3rd epoch, Tulu 3 caps at 2 on million-scale data, SDFT caps at 1 on a few thousand to tens of thousands, Lightning's 2nd pass on 50,000 examples gets worse instead. The sources using 3 are entirely ones that only gave a number (the Alpaca family and three training libraries' defaults). Our b06 cgen's val_ce is lowest at epoch 0 (0.4793), rising to 0.6371 and 0.6697 over the next two epochs, matching the direction these sources report. Because we keep the version with the lowest val_ce, epochs 2 and 3 spent on b06 cgen only cost time, they did not contaminate the weights used for evaluation; as noted in the previous round, this rise itself cannot be distinguished as caused by the learning rate, the epoch count, or the data.

On batch 32, 5% linear warmup with linear decay to 0, weight decay 0.01, clip 1.0: batch 32 is the value Massive SFT swept to on 8B full-parameter, and also the value InstructGPT used at 1.3B; on the LoRA side, LoRA Without Regret recommends under 32. The one SFT sweep on warmup and schedule (Secret Recipe) says no warmup and a constant learning rate are no worse, while the pretraining papers say a short warmup suffices and linear decay to 0 is best; our 5% linear warmup plus linear decay to 0 doesn't conflict with either set of conclusions. Weight decay 0.01 is PyTorch's default, the one SFT sweep chose 0, Qwen's own SFT uses 0.1, all three values have users in the literature, and none has been shown to beat 0.01; the AdamW original paper says the optimal weight decay changes with the number of update steps, and there is no corresponding number for b06 cgen's 17,484 steps (the other cells have different step counts). Clipping at 1.0 has no source explaining it at all, the paper it originates from uses 6 and 45. Of these four values, weight decay 0.01 and clip 1.0 have the least evidence, but there's no counter-evidence either.

On using the same set of values across the three sizes: both approaches exist in the literature, for different reasons. Lowering the learning rate by size is more common (Tulu 3, QLoRA, OLMo 2, InstructGPT, DeepSeek, Alpaca, torchtune), with the drop running 2 to 2.5x between 8B and 70B and 1.9x between 1.3B and 175B; the same-set-across-all-sizes approach (Toolformer, RouteNator, LoRA Land, When Scaling Meets LLM Finetuning) all give comparability as the reason. Our three sizes' widths are 1024 / 2048 / 2560; by the LoRA paper's n^(-1/2) rule, 4B's optimal LoRA learning rate is about 0.63x 0.6B's, a gap smaller than the adjacent steps in the literature's sweep grids (usually 2x to 2.5x), meaning that sharing one learning rate across the three sizes probably lands in the same cell on the LoRA side. The full-parameter side has no SFT formula, only torchtune's one unexplained record of dropping the configured value from 2e-5 to 5e-6 between 1.7B and 4B. The decision to lock the values holds up on comparability grounds, at the cost that the 4B cell may not be running at its own optimum, a cost the current data cannot size.

On the practice of "how other people choose" itself: the common approach among sources that swept is to fix everything else, run 3 to 5 learning rates on a log scale, and pick by a validation metric (Tulu 3, OLMo 2, SDFT, Secret Recipe all follow this process, and OLMo 2 additionally writes that it first picks a config with 1 seed, then adds up to 4 seeds once decided); the LoRA side adds one more move, "take the largest learning rate that doesn't diverge" (LoRA Learns Less). The TIMELINE entry for 2026-08-21, "add a comparison round later if self-tuning is needed," corresponds exactly to this process, which was not done this round. If it were to be done, the smallest version the literature gives is one size, one task, three learning rates, one run each.
