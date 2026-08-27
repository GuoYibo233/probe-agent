# 超参数怎么选：本地 15 篇论文与网络一手资料的调查（2026-08-26）

这份报告回答一个问题：我们 np821 批锁死的训练超参数（全参学习率 1e-5、LoRA 学习率 2e-4、3 个 epoch、有效批 32、5% 线性热身后线性降到 0、weight decay 0.01、梯度裁剪 1.0、LoRA r=16 / alpha=32 / dropout 0.05），在我们手头的论文和公开的一手资料里，同类数字是怎么定下来的。

报告分四节：第 0 节说调查怎么做的；第 1 节是本地 15 篇论文逐篇的事实；第 2 节是网络一手资料按角度的事实；第 3 节把我们的设定和前两节摆在一起，只列事实；第 4 节是解读，和前三节分开。

## 0 调查是怎么做的

“我们目前有的论文”在仓库里没有一个统一的论文库，能算进来的是三类，一共 15 篇：

| 来源 | 论文 | arxiv 号 |
|---|---|---|
| 2026-08-09 报告（`talks/20260809/SLIDES-text-en.md`）引用的 3 篇 | ReAct；Toolformer；Do NOT Think That Much for 2+3=?（o1 类模型过度思考） | 2210.03629；2302.04761；2412.21187 |
| `~/reproduce` 下复现仓库对应的 4 篇 | ACE；Self-Distillation Enables Continual Learning（SDFT）；AEL；Neural Thickets（RandOpt 仓库对应的论文） | 2510.04618；2601.19897；2604.21725；2603.12228 |
| `envs/` 下 7 个基准环境对应的 8 篇 | τ²-Bench；ALFWorld；TALES；AppWorld；Gorilla（BFCL 的前身）；ToolLLM（ToolBench）；StableToolBench；ToolHop | 2506.07982；2010.03768；2504.14128；2407.18901；2305.15334；2307.16789；2403.07714；2501.02506 |

BFCL 自己的论文（ICML 2025）在 arxiv 上没有条目：抽取员和核对员各自用 arxiv API 按标题、按作者查了五种写法，都只查到引用 BFCL 的别人的论文，所以 BFCL 这一格只有 Gorilla 一篇。

每篇论文两个 opus subagent：第一个把论文全文（arxiv HTML 或 PDF 转文本，附录保留）抓到本机，抽出每一个训练设置和“怎么选的”证据，每条引文都用 `grep -c -F` 在原文里数一遍；第二个独立换一条路线重新抓全文（抽取员用 arxiv HTML 的，核对员用 ar5iv 或 PDF），逐条引文、逐个数字复查，默认往推翻的方向查。15 篇全部过了核对：11 篇 confirmed，4 篇 partially_confirmed（ReAct、Neural Thickets、ALFWorld、τ²-Bench）。4 篇 partially 的失败项分别是：Neural Thickets 一处“Figure 8”在 PDF 版里是“Figure 7”（HTML 版和 PDF 版图编号不同）；ALFWorld 一处 Seq2Seq 基线的训练长度抽取员写 NOT STATED，核对员指出附录 B 的“All text agents are trained for 50,000 episodes.”覆盖这条基线；ReAct 和 τ²-Bench 的失败项只是词频统计口径不同（HTML 带导航文字，PDF 不带）。没有一条超参数数字或者“怎么选的”引文被推翻。

原始抽取和核对结果在 `/home/y-guo/.claude/jobs/f768d4d4/tmp/papers_result.json`（job 临时目录，job 删除后消失）。

## 1 本地 15 篇论文

### 1.1 训练过东西的 8 篇

| 论文 | 训练的是什么 | 学习率 | 批大小 | 训练长度 | 调度与热身 | 怎么选的 |
|---|---|---|---|---|---|---|
| ReAct（2210.03629） | PaLM-8B 与 PaLM-62B 全参 SFT，3,000 条自生成轨迹 | 没写 | 64 | 4,000 步（ReAct/Act）、2,000 步（8B 的 Standard/CoT）、1,000 步（62B 的 Standard/CoT） | 没写 | 步数按观察定，学习率没写 |
| Toolformer（2302.04761） | GPT-J 全参 SFT | 1·10⁻⁵ | 128 | 最多 2k 步，每 500 步看开发集 PPL 挑最好的 | 前 10% 线性热身，之后没写 | 只给数字，没给理由 |
| 过度思考（2412.21187） | QwQ-32B-Preview 的 SFT / DPO / RPO / SimPO | 没写 | 没写 | 没写 | 没写 | 全文零个训练超参数 |
| SDFT（2601.19897） | Qwen2.5-7B-Instruct 全参，SDFT 与 SFT / DFT / CPT 基线 | 扫 {5e-6, 1e-5, 5e-5}（CPT 扫 {1e-6, 5e-6, 1e-5}） | 扫 {16, 32, 64} | 扫 {1, 2} 个 epoch（知识任务 SDFT 扫 {1, 2, 4}，CPT 扫 {1, 2, 4, 8}） | cosine 带热身，热身 10 步 | 三个量一起扫，按验证集挑 |
| Neural Thickets（2603.12228） | GRPO / PPO 基线，Qwen2.5-0.5B/1.5B/3B-Instruct 与 OLMo3-7B | actor 1e-6，critic 1e-5；附录 D 另扫 {1e-5, 1e-6, 1e-7} | 1024（GRPO）、128（PPO） | 200 步（GRPO）、600 步（PPO） | 没写 | 各方法按总 FLOPs 对齐；附录 D 有一次 lr × 批大小网格 |
| ALFWorld（2010.03768） | BUTLER::Brain（Transformer seq2seq 文本智能体，DAgger）；Mask R-CNN 检测器 | 0.001；检测器 5e-4 | 64（回放缓冲采样）；检测器 8 | 50,000 个 episode；检测器 4 个 epoch | 没写 | 只给数字，没给理由 |
| Gorilla（2305.15334） | LLaMA-7B 全参指令微调 | 2e-5 | 64 | 5 个 epoch | cosine 衰减，warmup ratio 0.03 | 只给数字，没给理由 |
| ToolLLM（2307.16789） | LLaMA-2 7B 全参 SFT | 5×10⁻⁵ | 64 | 2 个 epoch，按开发集挑 checkpoint | warmup ratio 4×10⁻²，衰减方式没写 | 只给数字，没给理由 |

8 篇里 weight decay 只有两篇写了：SDFT 是 0，Gorilla 是 0。梯度裁剪只有两篇写了：SDFT 的 Max Grad Norm 是 1，ALFWorld 是 5。优化器写了名字的有三篇：SDFT 用 adamw，Neural Thickets 的 GRPO/PPO 用 AdamW，ALFWorld 用 Adam；Toolformer、Gorilla、ToolLLM 都没写优化器。8 篇里没有一篇用 LoRA（每篇的“lora”词频命中全是 Colorado、exploration、Lora Aroyo 这类子串）。

### 1.2 每篇的原文

引文一律原样抄，位置写的是论文的章节。

ReAct：训练超参数全在附录 B.1，一共四句话（核对员独立确认附录 B.1 只有这四句）：“For all finetuning we use a batch size of 64. On PaLM-8B, we finetune ReAct and Act methods for 4,000 steps and Standard and CoT methods for 2,000 steps. On PaLM-62B, we finetune ReAct and Act methods for 4,000 steps and Standard and CoT methods for 1,000 steps. We find ReAct and Act methods generally benefit from more training steps (and more training data), while Standard and CoT methods degrade soon after finetuning.”学习率、优化器、调度、weight decay 全文没有出现（“learning rate”在全文出现 0 次）。

Toolformer：第 4.1 节：“We finetune M on C* using a batch size of 128 and a learning rate of 1·10−5 with linear warmup for the first 10% of training. Details of our finetuning procedure are given in Appendix B.”附录 B：“We use up to 25k examples per API. Max sequence length 1,024. Effective batch size of 128.”“Training up to 2k steps, where we evaluate PPL on a small development set from CCNet containing 1,000 examples every 500 steps. We pick the checkpoint that performs best.”第 4.4 节把同一套设置原样用到 GPT-2 的 124M 到 1.6B 四个尺寸上：“Apart from this, we follow the experimental setup described in Section 4.1.”也就是说 Toolformer 从 124M 到 6.7B 五个尺寸用的是同一个学习率 1e-5，论文没有说明为什么。

过度思考（2412.21187）：抽取员在 arxiv HTML 版和 PDF 版各查了一遍，“learning rate”“epoch”“batch size”“optimizer”“warmup”“hyperparameter”“1e-”“e-5”都是 0 次命中。论文里关于训练的选择只有两类：方法之间的比较（“Consequently, SimPO is used as the default post-training method in the subsequent experiments.”）和数据构造的选择（“However, in our preliminary experiments, we found it less effective than using the longest sampled response as the negative example.”）。

SDFT：附录 B.1：“All experiments were conducted using the Hugging Face TRL library. Each experiment was conducted on a single NVIDIA H200 GPU.”“For each method, we performed a hyperparameter sweep over learning rates, batch sizes, and training epochs. We report test results for the model checkpoint that achieved the best validation performance on the target task.”“Tables 3 and 4 present the full hyperparameter search spaces and final selected values for the Skill Learning and Knowledge Acquisition settings, respectively.”表 3 的说明：“Table 3: Hyperparameters used for the Skill Learning experiments. Curly braces {} indicate a sweep over the specified values.”表 3 里学习率一行是 {5e-6, 1e-5, 5e-5}，批大小一行是 {16,32,64}，epoch 一行是 {1,2}，其余行是单值：Warmup steps 10、Max Grad Norm 1、Weight Decay 0、Optimizer adamw、LR Scheduler “Cosine w. warmup”、bfloat16 True。抽取员和核对员都指出一个缺口：附录 B.1 说表里有“final selected values”，但是表里学习率、批大小、epoch 三行只有花括号里的候选集，最终选中的值没有印在任何地方。关于 epoch 数，附录 B.1 有两句：“Across all tasks, we found that SDFT benefits from training for multiple epochs”和“In contrast, SFT tends to overfit rapidly and showed no performance gains beyond a single epoch in most cases.”统计口径：“Unless mentioned otherwise, all experiments were run over 3 random seeds. We report mean performance and 95% confidence intervals across seeds.”复现仓库 `~/reproduce/SDFT/README.md` 第 59 到 60 行和第 80 到 81 行的示例命令写的是 `--learning_rate 5e-5` 和 `--num_train_epochs 2`；仓库自带的 `distil_config.py` 里 learning_rate 的默认值是 1e-6，README 命令行把这个默认值覆盖掉了。仓库里的值是仓库证据，论文本身没有把 5e-5 写成选中值。

Neural Thickets（RandOpt）：这篇的训练是 RL 基线，和我们的 SFT 不是一回事，记在这里是因为论文里有两种“怎么定超参数”的做法。附录 E.3：“To ensure a fair comparison, we align the hyperparameters such that all methods consume equivalent total training FLOPs. We balance the batch size and iteration counts to account for algorithmic overheads. For instance, GRPO uses a larger batch size ( B=1024 ) compared to PPO ( B=128 ) due to the latter’s additional memory cost for the critic network.”表 3 里 Actor Learning Rate 是 1e-6，Critic Learning Rate 是 1e-5，Optimizer 是 AdamW。附录 D 有一次网格：“We grid-search GRPO and PPO on 8 GPUs over learning rates 1e-5 , 1e-6 , and 1e-7 ; batch size (PPO) ranges from 128 to 2048, and group size (GRPO) ranges from 512 to 8192 .”结果“best accuracy is 78.0% at batch size 256 (lr= 1e-5 ), while larger-batch runs such as batch size 2048 reach at most 77.5%.”第 7 节的蒸馏 SFT 只写了 epoch：“We then select hard examples and perform supervised fine-tuning (SFT) on the base model for 2 epochs, obtaining a distilled model.”学习率没写。

ALFWorld：训练的不是语言模型，是一个 Transformer seq2seq 文本智能体。附录 B：“For all experiments, we use Adam (Kingma and Ba,, 2014) as the optimizer.”“The learning rate is set to 0.001 with a clip gradient norm of 5.”“We sample a batch of 64 data points from the replay buffer.”“All text agents are trained for 50,000 episodes.”“All experiment settings in TextWorld are run with 8 random seeds.”挑模型的办法：“For each task category, we select the agent with best evaluation performance in TextWorld (from 8 random seeds)”。全文唯一一句给理由的话是关于序列长度的：“Following the training strategy used in the recurrent DQN literature”。检测器在附录 D：“fine-tune the detector for 4 epochs with a batch size of 8 and a learning rate of”5e-4。

Gorilla：附录 8.2：“We train Gorillafor 5 epochs with the 2e-5 learning rate with cosine decay. The details are provide in Tab. 4. We finetune it on 8xA100 with 40G memory each.”表 4（“Table 4: Hyperparameters for training Gorilla”）六行：learning rate 2e-5、epochs 5、batch size 64、warmup ratio 0.03、weight decay 0、max seq length 2048。优化器、seed、精度没写。核对员枚举了全文四张表，表 4 是唯一一张超参数表。

ToolLLM：附录 A.3：“For the training hyper parameters, we use a learning rate of 5×10−5 , a warmup ratio of 4×10−2 , a total batch size of 64 , a maximum sequence length of 8192 , and use a position interpolation ratio of 2 .”“We train the model for two epochs and select the model checkpoint”“with the best performance on the development set”。优化器、衰减方式、weight decay、梯度裁剪都没写。

### 1.3 没训任何东西的 7 篇

ACE、AEL、τ²-Bench、TALES、AppWorld、StableToolBench、ToolHop 七篇全是提示、评测或者环境论文，核对员逐篇用“fine-tun”“learning rate”“epoch”“LoRA”“optimizer”重新查过，都是零个训练设置。

这 7 篇里有一处“在开发集上选值”的记录值得留着当对照：AppWorld 附录 E.4 关于推理时的轮数上限，“We allow a maximum of 15 turns (each consisting of a batch of any number of function calls). We tried the limit of 10, 15, and 20 on the Dev set and found the performance to saturate at 15.”这是推理设置，不是训练超参数。

## 2 网络一手资料

### 2.0 这一部分怎么查的

网络这批按 10 个角度分头查：模型官方微调配方、LoRA 文献、全参学习率扫描、调度与热身、epoch 与批大小、训练库默认值、weight decay 与梯度裁剪、探针训练、跨模型规模迁移、工具调用 SFT 配方。每个角度一个 opus 负责搜索并且只从自己抓到本机的原始文本（arxiv HTML / PDF / GitHub 原文件 / 官方文档页）里抄逐字引文，另一个 opus 换一条抓取路线重新抓每个 URL、逐条引文 `grep -c -F`、逐个数字复查。10 个角度一共 96 条发现，核对员 96 条全部抓到了原始网页，96 条引文全部逐字命中，73 条整条 confirmed，23 条 partially_confirmed。23 条 partially 里没有一条是引文或者超参数数字错了，全是搜索员在“numbers”和“paraphrase”两个转述字段里的差错（比如一篇论文的训练步数写成 10⁴ 而原文是 50,000 步；一条引文归到了 SFT 段落而原文在 PPO 段落）或者“怎么选的”标签打得比原文证据强。核对员还各自补了一篇搜索员漏掉的一手来源（Llama 2、QLoRA、InstructGPT、Qwen2、ToolAlpaca、LoRA Land、Tenney 2019、alignment-handbook 的 zephyr 配置），补的引文核对员自己抓了原文并且逐字核过，下面标为“核对员补”。

下面按超参数分小节，每小节先列表格再引原文。表格里“怎么选的”一栏只有四种：扫描（原文写了扫过哪些值）、沿用（原文写了跟的是谁）、只给数字（原文有数没有理由）、没写数字。

原始搜索和核对结果在 `/home/y-guo/.claude/jobs/f768d4d4/tmp/web_result.json`。

### 2.1 全参微调的学习率

| 来源 | 模型规模 | 全参 SFT 学习率 | 怎么选的 |
|---|---|---|---|
| Tulu 3（arXiv 2411.15124） | Llama 3 8B / 70B / 405B | 8B 5e-6、70B 2e-6、405B 2e-6 | 扫描：8B 上扫 {2e-6, 5e-6, 1e-5, 2e-5} × 损失求和还是求平均 × epoch 2 到 7 |
| OLMo 2（arXiv 2501.00656） | 7B / 13B / 32B | 7B 2e-5、13B 5e-6、32B 4e-6 | 扫描：每个尺寸单独扫，7B 扫 {1e-5, 2e-5, 3e-5}，13B 扫 {1e-6, 4e-6, 5e-6, 7.5e-6, 8e-6}，32B 扫 {1e-6, 2e-6, 3e-6, 4e-6, 5e-6} |
| Unveiling the Secret Recipe（arXiv 2412.13337） | Granite 3B / 7B、Llama 3.2 3B、Mistral 7B | Granite 2e-5、Mistral 1e-6 | 扫描：{1e-6, 5e-6, 2e-5, 3e-5, 4e-5, 6e-5, 8e-5, 1e-4} |
| Massive SFT experiments（arXiv 2506.14681） | Llama 3 8B | 1e-5 | 扫描：学习率 {2e-7, 1e-6, 2e-6, 1e-5, 2e-5, 1e-4} × 批 {32, 64, 128, 256} × weight decay {0, 0.1} × {LoRA, 全参}，96 个组合 |
| LoRA Learns Less and Forgets Less（arXiv 2405.09673） | Llama 2 7B | 代码任务 5e-5、数学任务 1e-5 | 扫描：[1e-5, 5e-4] |
| InstructGPT（arXiv 2203.02155，核对员补） | 1.3B / 6B / 175B | 1.3B 与 6B 9.65e-6，175B 5.03e-6 | 扫描：“a geometric search over 7 LRs” |
| DeepSeek LLM（arXiv 2401.02954） | 7B / 67B | 7B 1e-5、67B 5e-6 | 只给数字（epoch 数的改动给了理由） |
| LoRA 原论文（arXiv 2106.09685）表 12 | GPT-3 175B | 5e-6 | 扫描：“We use the same hyperparameters for all datasets after tuning learning rate.” |
| Llama 2（arXiv 2307.09288，核对员补） | 7B 到 70B | 2e-5，cosine | 只给数字 |
| Llama 3（arXiv 2407.21783） | 最大的模型 | 1e-5，8.5K 到 9K 步 | 只给数字 |
| Qwen2.5 技术报告（arXiv 2412.15115） | 全系列 | 从 7e-6 降到 7e-7 | 只给数字 |
| Qwen3 技术报告（arXiv 2505.09388） | 全系列 | 没写数字 | 全文没有任何学习率数字 |
| SmolLM2（arXiv 2502.02737） | 1.7B | 3.0e-4 | 只给数字 |
| Alpaca（GitHub README） | LLaMA 7B / 13B | 7B 2e-5、13B 1e-5 | 只给数字 |
| Tulu 1（arXiv 2306.04751） | 7B 到 65B | 2e-5，30B 和 65B 用 1e-5 | 只给数字 |
| Tulu 2（arXiv 2311.10702） | 7B 到 70B | 2e-5，70B 用 1e-5 | 只给数字 |
| LIMA（arXiv 2305.11206） | 65B | 1e-5 线性降到 1e-6 | 沿用：“We follow standard fine-tuning hyperparameters” |
| APIGen / xLAM-1B、7B（arXiv 2406.18518） | 1.3B / 6.7B | 5e-6，两个尺寸同一个值 | 只给数字 |
| Gorilla（arXiv 2305.15334） | LLaMA 7B | 2e-5 | 只给数字 |
| ToolLLM（arXiv 2307.16789） | LLaMA 2 7B | 5e-5 | 只给数字 |
| ToolAlpaca（arXiv 2306.05301，核对员补） | Vicuna 7B / 13B | 2e-5 | 只给数字 |
| Qwen 官方 finetune 脚本（QwenLM/Qwen） | 不分尺寸 | 1e-5 | 只给数字 |
| LLaMA-Factory Qwen3 示例配置 | Qwen3-4B | 1e-5 | 只给数字 |
| torchtune Qwen3 配置 | 0.6B / 1.7B / 4B / 8B | 0.6B 2e-5、1.7B 2e-5、4B 5e-6、8B 5e-6 | 只给数字 |
| TRL SFTConfig 默认值 | 不分尺寸 | 2e-5 | 库默认值 |
| transformers TrainingArguments 默认值 | 不分尺寸 | 5e-5 | 库默认值 |

三段原文。Tulu 3 第 4 节：“We used an effective batch size of 128 and a maximum sequence length of 4,096 tokens. We trained for two epochs using a learning rate of 5e-6 for our 8B models, and 2e-6 for our 70B models, which we found after a hyperparameter search.”OLMo 2 附录：“We conducted a hyperparameter sweep for SFT and DPO, using earlier development checkpoints, with results detailed in Table 17 and Figure 12. A key finding was that OLMo 2 required significantly higher learning rates compared to the Llama 3.1 training recipe described by Lambert et al. (2024).”OLMo 2 表 17 是 7B 上六个配置的平均分：2 epoch / 1e-5 / sum 三次分别是 49.97、49.74、49.59，3 epoch / 4e-6 / sum 是 49.76，3 epoch / 4e-6 / mean 是 48.25，2 epoch / 2e-6 / mean 是 48.18。Unveiling the Secret Recipe：“Low learning rates are crucial for optimal performance. We found that 2×10⁻⁵ works well for Granite models, while 1×10⁻⁶ performs best for Mistral. […] Practitioners should start with these values and, if necessary, perform a localized search by testing slightly higher or lower learning rates to find the optimal setting for their specific model.”

Llama 3 关于自己 1e-5 的全部说明是一句话：“We found these hyperparameter settings to work well across different rounds and data mixes.”Alpaca 的 README 关于批大小写的是“Global batch size has not been tested for optimality.”

### 2.2 LoRA 的学习率、秩、alpha、dropout

| 来源 | 模型规模 | 秩 r / alpha / dropout | LoRA 学习率 | 怎么选的 |
|---|---|---|---|---|
| LoRA 原论文（arXiv 2106.09685） | GPT-3 175B；GPT-2 | GPT-2：r=4，alpha=32 | GPT-3 2e-4（同表全参 5e-6）；GPT-2 2e-4 | 学习率扫描；alpha 不调 |
| QLoRA（arXiv 2305.14314） | LLaMA 7B 到 65B | r=64，alpha=16；dropout 0.1（7B、13B）/ 0.05（33B、65B）；全部线性层 | 7B、13B 2e-4；33B、65B 1e-4 | 扫描：dropout {0, 0.05, 0.1}，r {8, 16, 32, 64, 128, 256}，作用层五种；alpha 固定，扫学习率 |
| LoRA Learns Less and Forgets Less（arXiv 2405.09673） | Llama 2 7B | r ∈ {16, 64, 256}，alpha=2r，dropout 0.05，七个投影 | 最好值 2e-4（数学）/ 5e-4（代码）；r=256 时用 1e-4 | 扫描 [1e-5, 5e-4] |
| LoRA Without Regret（Thinking Machines 博客，2025） | 14 个 Llama 与 Qwen 模型 | r 从 1 扫到 512；alpha=32 | LoRA 最优学习率是全参的 10 倍（拟合值 9.8） | 扫描；alpha 是惯例 |
| Learning Rate Scaling across LoRA Ranks（arXiv 2602.06204） | 理论加六组实验 | 标准 alpha/r 缩放下最优学习率不随 r 变，随宽度按 n^(−1/2) 下降 | 公式 | 理论 |
| Beware of the Batch Size（arXiv 2602.09492） | LLaMA 2 7B / 13B | r ∈ {32, 64, 128, 256} | 每个批大小扫 1e-5 到 3e-3 | 扫描 |
| LoRA vs Full Fine-tuning: An Illusion of Equivalence（arXiv 2410.21228） | RoBERTa | alpha=2r 与 alpha=8 对比 | alpha·η 固定 2.4e-3 | 沿用 |
| Tulu 2 QLoRA（arXiv 2311.10702） | 7B 到 70B | r=64，alpha=16，dropout 0.1 | 1e-4，5 个 epoch | “found in smaller-scale experiments” |
| Lightning AI LoRA insights（Raschka，2023） | Llama 2 7B | 试过 r=8/alpha=16 和 r=16/alpha=32 | 3e-4 | 扫描 |
| ToolACE（arXiv 2409.00920） | Llama 3.1 8B | r=16，alpha=32，全部模块 | 1e-4，3 个 epoch | “one of the most common settings” |
| RouteNator（arXiv 2505.10495） | 0.5B 到 7B 七个模型 | r=16，alpha=32，dropout 0.05，七个投影 | 1e-4，3 个 epoch，裁剪 0.3 | 只给数字，跨尺寸固定为了可比 |
| Internalizing Tool Knowledge（arXiv 2605.17774） | Gemma 4 E4B、Qwen3 | r 扫 {8, 16, 32, 64}，峰值 32；alpha=64 | 2e-4，2 个 epoch | 秩扫描 |
| Octopus v2（arXiv 2404.01744） | Gemma 2B | r=16，alpha=32，六个投影 | 5e-5，和全参同一个值 | 只给数字 |
| Granite-Function Calling（arXiv 2407.00121） | 20B | QLoRA r=8，alpha=32，dropout 0.1 | 5e-5，3 个 epoch | 只给数字 |
| SimpleTool（arXiv 2603.00030） | Qwen3-4B | r=512，alpha=1024 | 1e-5 | 秩扫描 {64, 256, 512, 1024} |
| alignment-handbook zephyr-7b-beta（核对员补） | Mistral 7B | r=16，alpha=16，dropout 0.05，七个投影 | 2e-4，1 个 epoch | 只给数字 |
| PEFT LoraConfig 默认值 | 不分尺寸 | r=8，alpha=8，dropout 0.0 | 库里没有学习率 | 库默认值 |
| Unsloth 文档 | 不分尺寸 | r 选 16 或 32；alpha=r 或 2r；dropout 0 | 2e-4 起步 | 建议 |
| LLaMA-Factory Qwen3 示例 | Qwen3-4B | r=8，alpha 默认 2r，全部线性层 | 1e-4 | 只给数字 |
| Axolotl Qwen3 示例 | 8B / 32B | r=32/alpha=64 或 r=16/alpha=32，dropout 0 | 2e-4 | 只给数字 |
| torchtune Qwen3 配置 | 0.6B 到 32B | 0.6B、1.7B r=32/alpha=64；4B 以上 r=8/alpha=16 | 0.6B 1e-4、1.7B 2e-5、4B 以上 3e-4 | 只给数字 |
| Qwen 官方 finetune 脚本 | 不分尺寸 | r=64，alpha=16，dropout 0.05 | 3e-4 | 只给数字 |

LoRA 原论文关于 alpha 的原话：“When optimizing with Adam, tuning α is roughly the same as tuning the learning rate if we scale the initialization appropriately. As a result, we simply set α to the first r we try and do not tune it.”QLoRA 的原话：“We keep LoRA α fixed and search the learning rate, since LoRA α is always proportional to the learning rate. We find that LoRA dropout 0.05 is useful for small models (7B, 13B), but not for larger models (33B, 65B). We find LoRA r is unrelated to final performance if LoRA is used on all layers”。LoRA Learns Less and Forgets Less 的结论段：“we recommend: (a) using LoRA for instruction finetuning and not continued pretraining; (b) if GPU memory allows, targeting “All” transformer modules with a rank of 256, since ranks 16 − 64 tend not to suffice for code tasks; (c) using α = 2r, and (d) sweeping over learning rates between [1e − 5, 5e − 4], picking the highest value that enables stable training.”同一篇：“LoRA’s best learning rates should be set one order of magnitude higher than that of full finetuning, often ranging between 5e−5 and 5e−4 for these combinations of model architecture and dataset.”LoRA Without Regret：“Our experiments showed that the optimal LR for LoRA is consistently 10x the one used for FullFT in the same application, for both supervised learning and reinforcement learning.”以及关于 alpha：“We use α=32 for the experiments in this article, following standard practice from other implementations.”ToolACE：“As for the hyper-parameters setting, we adopt one of the most common settings, which sets the rank as 16 and alpha as 32 for all modules.”LoRA+（arXiv 2402.12354）对 LoRA 学习率现状的描述：“there are no principled guidelines on how to set the learning rate, apart from common choices of order 1e-4.”

### 2.3 epoch 数

| 来源 | 数据量 | epoch | 怎么选的 |
|---|---|---|---|
| Tulu 3 | 约百万条 | 2 | 扫描 2 到 7，“training for longer did not yield further improvements” |
| SDFT（本地第 1 节） | 各任务几千到几万条 | 扫 {1, 2} | “SFT tends to overfit rapidly and showed no performance gains beyond a single epoch in most cases” |
| DeepSeek LLM | 未写 | 7B 4 个，67B 2 个 | “since we observed the overfitting problem is serious on the 67B model” |
| Lightning AI LoRA insights | Alpaca 5 万条 | 1 遍好于 2 遍 | 扫描：“the increased iterations result in worse performance across the board” |
| OLMo 2 表 17 | 同一数据 | 2 与 3 差 0.2 分，同配置三次重复差 0.38 分 | 扫描 |
| InstructGPT（核对员补） | 未写 | 16，residual dropout 0.2 | 原文写了选法，核对员只抄到学习率那句 |
| LIMA | 1,000 条 | 训 15 个，从第 5 到第 10 个 epoch 里手挑 | “perplexity does not correlate with generation quality” |
| Massive SFT experiments | 每集约 1,000 条 | 10 个，每个 epoch 存一版 | 扫描 |
| Alpaca / Vicuna / ToolAlpaca / ToolACE / Granite / Octopus v2 / RouteNator | 各不相同 | 3 | 只给数字 |
| Gorilla | 约 1.6 万条 | 5 | 只给数字 |
| APIGen | 未写 | 4 | 只给数字 |
| ToolLLM / Llama 2 / Qwen2.5 / Tulu 1 / Tulu 2 / SmolLM2 | 十几万到百万条 | 2 | 只给数字 |
| Scaling Data-Constrained LMs（arXiv 2305.16264，预训练） | 最多 9000 亿 token | 重复到 4 遍损失几乎不变，16 遍以后急剧变差 | 拟合的缩放律 |
| transformers TrainingArguments / LLaMA-Factory | 不分 | 3 | 库默认值 |
| torchtune / Axolotl | 不分 | 1 | 库默认值 |

Tulu 3 的原话：“Surprisingly, we additionally found that training for longer did not yield further improvements, and so used 2 epochs for training.”Scaling Data-Constrained Language Models 的原话：“while models trained for a single epoch consistently have the best validation loss per compute, differences tend to be insignificant among models trained for up to 4 epochs and do not lead to differences in downstream task performance. … The returns from additional epochs may heavily depend on hyperparameters such as learning rate, dropout, or the optimizer choice.”这篇是预训练，核对员标了“和我们的 SFT 场景不同”。

### 2.4 批大小

| 来源 | 有效批大小 | 怎么选的 |
|---|---|---|
| Massive SFT experiments（8B 全参） | 从 {32, 64, 128, 256} 里选出 32 | 扫描 |
| Unveiling the Secret Recipe（3B / 7B） | 128、3,840、7,680 三档，大的一直更好 | 扫描 |
| Beware of the Batch Size（LoRA） | 存在一个内部最优点，只改批大小能差 10 个点以上；最优点不随 r 和模型大小动，随数据量动 | 扫描 |
| LoRA Without Regret（LoRA） | LoRA 对大批更不耐受；TRL 文档据此建议有效批小于 32 | 扫描 |
| QLoRA | 7B、13B 用 16；33B 用 32；65B 用 64 | 扫描后按尺寸翻倍 |
| InstructGPT（核对员补） | 1.3B、6B 用 32；175B 用 8 | 扫描 |
| Tulu 3 / OLMo 2 / Alpaca / Vicuna / ToolAlpaca / Tulu 2 | 128 | 只给数字（Alpaca 明写没测过） |
| Llama 2 / Gorilla / ToolLLM / ReAct | 64 | 只给数字 |
| ToolACE | 48 | 只给数字 |
| APIGen | 每卡 6，累积 2 步 | 只给数字 |
| RouteNator / LLaMA-Factory LoRA 示例 | 8 | 只给数字 |
| torchtune | 2 × 8 = 16 | 库默认值 |
| Measuring the Effects of Data Parallelism（arXiv 1811.03600） | 没有通用值；换批大小要重调全部优化参数 | 扫描 |
| 临界批大小三篇（arXiv 1812.06162、2001.08361、2410.21676） | 临界批大小由损失或者数据量决定，不直接由模型大小决定 | 拟合 |

Measuring the Effects of Data Parallelism 的原话：“We were unable to find reliable support for any of the previously proposed heuristics for adjusting the learning rate as a function of batch size. Thus we are forced to recommend that practitioners tune all optimization parameters anew when they change the batch size or they risk masking the true behavior of the training procedure.”

### 2.5 热身与学习率调度

| 来源 | 热身 | 调度 | 怎么选的 |
|---|---|---|---|
| Tulu 3 | 比例 0.03 | 线性衰减 | 只给数字 |
| OLMo 2 | 印的是 0.3 | 线性 | 只给数字 |
| Llama 2 SFT | 没写 | cosine | 只给数字 |
| Qwen2.5 / Qwen2 SFT | 没写 | 7e-6 降到 7e-7 | 只给数字 |
| Gorilla | 比例 0.03 | cosine | 只给数字 |
| ToolLLM | 比例 0.04 | 没写 | 只给数字 |
| Toolformer（本地） | 前 10% 线性 | 没写 | 只给数字 |
| APIGen | 50 步 | cosine | 只给数字 |
| xLAM | 100 步 | cosine | 只给数字 |
| Octopus v2 | 10 步 | 线性 | 只给数字 |
| LIMA / InstructGPT | 没有热身 | 线性到 1e-6 / cosine 到 10% | 沿用 / 扫描 |
| Unveiling the Secret Recipe | 试了 0、25、100 步，0 步不差 | 常数学习率和 cosine 打平 | 扫描 |
| LoRA Without Regret | 无热身 | 常数 | 扫描 |
| transformers TrainingArguments | 默认 0 | 默认线性 | 库默认值 |
| LLaMA-Factory / Axolotl | 比例 0.1 | cosine | 库示例 |
| Unsloth 文档 | 5% 到 10% | 线性或 cosine | 建议 |
| Why Warmup the Learning Rate?（arXiv 2406.09405，小模型） | 热身的作用是让更高的峰值学习率不发散；有尖峰就加长 | | 扫描 |
| Analyzing & Reducing the Need for LR Warmup（arXiv 2410.23922，124M 预训练） | 扫 0%、2%、5%、10%、20%；不热身留下永久差距，短热身够用 | | 扫描 |
| Straight to Zero（arXiv 2502.15938，预训练） | 全部 10% | 线性降到 0 好于降到 1/10 或 cosine | 扫描 |
| Scaling Laws and Compute-Optimal Training Beyond Fixed Training Durations（arXiv 2405.18392，预训练） | | 常数加 10% 到 20% 冷却打平或超过 cosine | 扫描 |
| MiniCPM（预训练） | “as long as the warmup stage is enough, it affects little performance” | 衰减段占 10% 够 | 扫描 |

Analyzing & Reducing the Need for Learning Rate Warmup 的原话：“Not using warmup results in faster initial progress for a given learning rate, but eventually falls behind leaving a permanent gap. […] Although we present new methods we consider promising, we still recommend the use of a short warmup in practice.”Unveiling the Secret Recipe 关于 SFT 的原话：“Our experiments indicate that omitting warmup steps and using a constant learning rate instead of cosine decay does not negatively impact performance, simplifying the training process without sacrificing model quality.”核对员对四篇调度论文都标了“预训练场景，不是 SFT”，Secret Recipe 那篇是 SFT。

### 2.6 weight decay 与梯度裁剪

| 来源 | weight decay | 梯度裁剪 | 怎么选的 |
|---|---|---|---|
| AdamW 原论文（arXiv 1711.05101） | 最优值随更新步数变，没有给固定数；“0.01”在全文不出现 | | 理论加扫描 |
| PyTorch `torch.optim.AdamW` | 默认 1e-2 | | 库默认值，源码无说明 |
| transformers TrainingArguments | 默认 0.0，文档写“Typical values: 0.01 (standard), 0.1 (stronger regularization), 0.0” | 默认 1.0，文档写“Typical values: 1.0 (standard), 0.5 (more conservative), 5.0 (less aggressive)” | 库默认值 |
| Massive SFT experiments（8B） | 扫 {0, 0.1}，选 0 | | 扫描 |
| Qwen2.5 / Qwen2 SFT | 0.1，“To address overfitting” | 1.0 | 只给数字 |
| Llama 2 SFT | 0.1 | SFT 段没写（PPO 段 1.0） | 只给数字 |
| GPT-3（预训练） | 0.1，“to provide a small amount of regularization” | 1.0 | 只给数字 |
| LIMA | 0.1 | | 沿用 |
| Tulu 1 / Tulu 2 / Gorilla / Alpaca / SDFT / LoRA Learns Less | 0 | SDFT 1；LoRA Learns Less 1 | 只给数字 |
| QLoRA | | 0.3 | 只给数字 |
| RouteNator | | 0.3 | 只给数字 |
| ALFWorld（本地） | | 5 | 只给数字 |
| Tenney 2019 探针（核对员补） | | 5.0 | 只给数字 |
| Unsloth 文档 | 0.01，最多 0.1 | | 建议 |
| Pascanu 2013（arXiv 1211.5063，梯度裁剪出处） | | 阈值按自己训练里的平均梯度范数定；原文用的是 6 和 45；1.0 不出现 | 经验 |

Pascanu 的原话：“One good heuristic for setting this threshold is to look at statistics on the average norm over a sufficiently large number of updates. In our experiments we have noticed that for a given task and model size, training is not very sensitive to this hyperparameter and the algorithm behaves well even for rather small thresholds.”AdamW 原论文的原话：“Optimal weight decay depends on the total number of batch passes/weight updates. Our empirical analysis of SGD and Adam suggests that the larger the runtime/number of batch passes to be performed, the smaller the optimal weight decay.”核对员在 10 个角度里都没有找到一篇解释为什么裁剪阈值取 1.0 而不是 0.5 或者 5.0 的一手来源。

### 2.7 同一套超参数跨模型规模

| 来源 | 场景 | 跨尺寸的做法 |
|---|---|---|
| Tulu 3 | SFT 8B → 70B | 学习率 5e-6 → 2e-6，理由是引用：“it is common to lower the learning rate and increase batch size when doing SFT with larger models (Touvron et al., 2023)” |
| QLoRA | LoRA 7B → 65B | “all hyperparameter settings found at 7B generalize (including number of epochs) except learning rate and batch size. We halve the learning rate for 33B and 65B while doubling the batch size.” |
| OLMo 2 | SFT 7B / 13B / 32B | 每个尺寸单独扫，2e-5 / 5e-6 / 4e-6 |
| DeepSeek LLM | SFT 7B → 67B | 学习率 1e-5 → 5e-6，epoch 4 → 2 |
| Alpaca | SFT 7B → 13B | 2e-5 → 1e-5，epoch 3 → 5 |
| Tulu 1 / Tulu 2 | SFT 7B → 65B / 70B | 2e-5 → 1e-5 |
| InstructGPT（核对员补） | SFT 1.3B / 6B → 175B | 9.65e-6 → 5.03e-6，批 32 → 8 |
| Llama 2 奖励模型（核对员补） | 7B 到 70B | 70B 用 5e-6，其余 1e-5 |
| torchtune Qwen3 配置 | 全参 0.6B 到 8B | 0.6B、1.7B 2e-5；4B、8B 5e-6 |
| When Scaling Meets LLM Finetuning（arXiv 2402.17193） | 1B 到 16B | 只在 1B 上网格搜索学习率和批大小，然后全尺寸沿用 |
| Toolformer（本地） | 124M 到 6.7B | 同一套设置 |
| RouteNator | 0.5B 到 7B LoRA | 同一套设置，理由是可比 |
| LoRA Land（arXiv 2405.00732，核对员补） | 2B 到 8B LoRA | “We deliberately maintain that all LLMs are fine-tuned with the same training parameters” |
| Unveiling the Secret Recipe | 同为 7B 的 Granite 与 Mistral | 最优学习率相差 20 倍（2e-5 对 1e-6） |
| OLMo 2 | 同为 7B 级 | Llama 3.1 配方的学习率对 OLMo 2 太低 |
| Kaplan 2020（预训练） | | LR(N) ≈ 0.003239 − 0.0001395 log(N) |
| µP / Tensor Programs V（arXiv 2203.03466） | 预训练 | 标准参数化下宽度 256 → 8192 最优学习率移动约一个数量级；µP 下不动 |
| Cerebras-GPT（arXiv 2304.03208） | 预训练 111M 到 13B | 标准参数化 6e-4 → 1.2e-4；µP 全部 6e-3 |
| MiniCPM / µP 实证研究（arXiv 2404.05728） | 预训练 | µP 基础学习率 0.04B 到 2.1B 不动；2M 到 10B 同一个 2⁻⁶ 最优 |
| Scaling Exponents（arXiv 2407.05872） | 预训练 | 按层缩放后基础学习率随宽度的幂指数约 −0.05 |
| Learning Rate Scaling across LoRA Ranks（arXiv 2602.06204） | LoRA | 标准 alpha/r 缩放下最优学习率 ∝ n^(−1/2)，n 是宽度 |
| LoRA Without Regret | LoRA 与全参 | 最优学习率拟合成 (2000 / hidden size) 的幂 |

核对员在这个角度的“没找到”一栏写的是：没有一篇来源给出 SFT 阶段 epoch 数随模型规模怎么变的规则，DeepSeek 那一句是唯一的观察；也没有一篇来源给出 SFT 阶段学习率随规模的公式，所有公式都来自预训练。

### 2.8 探针头的训练

| 来源 | 探针 | 优化设置 | 怎么选的 |
|---|---|---|---|
| Alain & Bengio 2016（arXiv 1610.01644） | 线性探针 | 只写了在 10⁴ 条验证集上早停 | 没写数字 |
| Hewitt & Liang 2019（control tasks） | 线性 / MLP | Adam；开发集损失不降就学习率减半，连续 4 次停；weight decay 扫 {0.01, 0.1, 1.0, 10.0}，dropout 扫 {0.2, 0.4, 0.6, 0.8}，步数扫 {50000 … 1500} | 扫描，按 selectivity 选 |
| Voita & Titov 2020（MDL probing） | MLP | Adam 0.001，沿用 Hewitt & Liang 的减半规则 | 沿用 |
| Hewitt & Manning 2019（structural probe） | 线性变换 | Adam 0.001，批 20，最多 40 个 epoch，平台期重置并且学习率乘 0.1 | 只给数字 |
| Tenney 2019（核对员补） | edge probing | Adam，批 32，学习率 1e-4，裁剪 5.0 | 只给数字 |
| CCS（arXiv 2212.03827） | 线性方向 | AdamW 0.01，1000 个 epoch，10 次重启取损失最低 | “which we found was good for consistently achieving low unsupervised loss” |
| Tuned Lens（arXiv 2303.08112） | 仿射 | SGD Nesterov，学习率 1.0，250 步，裁剪 1，weight decay 1e-3 | 只给数字 |
| SAPLMA（arXiv 2304.13734） | 三层 MLP | Adam，5 个 epoch，“We do not fine-tune any of these hyper-parameters for this task.” | 明写没调 |
| scikit-learn LogisticRegression | 线性 | L-BFGS，C=1.0；LogisticRegressionCV 在 1e-4 到 1e4 的 10 点对数网格上交叉验证 | 库默认值 |

这些探针全是冻结底座、单独训头。我们 ctool 的头（`Linear(hidden→150)`）和底座一起训、共用一个学习率，和这批来源的做法不同，所以这一小节只当背景。

## 3 我们的设定和前两节摆在一起（只列事实）

| 我们的设定 | 值 | 值的来历（第 0 节和之前的查证） | 前两节里扫过的来源给出的值 | 前两节里只给数字的来源给出的值 |
|---|---|---|---|---|
| 全参学习率 | 1e-5 | 2026-07-31 写脚本时的值，没有记录理由，08-21 锁死 | 7B 到 8B：Tulu 3 5e-6，OLMo 2 2e-5，Massive SFT 1e-5，LoRA Learns Less 1e-5 / 5e-5，Secret Recipe 2e-5（Granite）/ 1e-6（Mistral）；1.3B 到 6B：InstructGPT 9.65e-6；GPT-3 175B：5e-6 | 小于 2B 的：SmolLM2 1.7B 3e-4，torchtune 0.6B / 1.7B 2e-5，APIGen 1.3B 5e-6，Toolformer 124M 到 6.7B 1e-5；4B：torchtune 5e-6，LLaMA-Factory 1e-5；7B 级：Llama 2 2e-5，Gorilla 2e-5，ToolLLM 5e-5，Alpaca 2e-5，Qwen2.5 7e-6 起 |
| LoRA 学习率 | 2e-4，是全参的 20 倍 | `lora_util.py` 第 33 行默认值，仓库明写惯例、没调 | LoRA 原论文 2e-4（全参 5e-6，40 倍）；QLoRA 7B / 13B 2e-4；LoRA Learns Less 2e-4 到 5e-4 最好，正式用 1e-4（全参 5e-6，20 倍）；LoRA Without Regret 全参的 10 倍；Internalizing Tool Knowledge 2e-4 | ToolACE 1e-4，RouteNator 1e-4，zephyr 2e-4，Unsloth 2e-4，Axolotl 2e-4，LLaMA-Factory 1e-4（全参 1e-5，10 倍），Qwen 脚本 3e-4（全参 1e-5，30 倍），torchtune 0.6B 1e-4 / 1.7B 2e-5 / 4B 3e-4，Octopus v2 5e-5（和全参相同），SimpleTool Qwen3-4B 1e-5 |
| LoRA r / alpha / dropout | 16 / 32 / 0.05，七个投影 | 惯例默认，没调 | QLoRA：dropout 0.05 对 7B、13B 有用，r 在全部线性层上和结果无关；LoRA Learns Less：alpha=2r，r 16 到 64 对代码任务不够；Internalizing Tool Knowledge：r 在 {8, 16, 32, 64} 里峰值 32；Lightning：r=16/alpha=32 好于 r=8/alpha=16 | ToolACE r=16/alpha=32 “one of the most common settings”；RouteNator r=16/alpha=32/dropout 0.05 七个投影；zephyr r=16/alpha=16/dropout 0.05 七个投影；PEFT 默认 r=8/alpha=8/dropout 0；LoRA Without Regret alpha=32 是惯例 |
| epoch | 3，按 val_ce 存最好的一版 | 08-21 锁死 | Tulu 3 扫 2 到 7 选 2；SDFT 的 SFT 1 个以后不涨；Lightning 2 遍差于 1 遍；OLMo 2 的 2 与 3 在噪声内；DeepSeek 67B 因过拟合从 4 降到 2 | 3：Alpaca、Vicuna、ToolAlpaca、ToolACE、Granite、Octopus v2、RouteNator、TrainingArguments 默认、LLaMA-Factory；2：ToolLLM、Llama 2、Qwen2.5、Tulu 1 / 2；5：Gorilla；4：APIGen |
| 有效批大小 | 32 | 08-21 锁死 | Massive SFT 全参从 {32, 64, 128, 256} 选 32；QLoRA 7B 16；InstructGPT 1.3B / 6B 32；Secret Recipe 越大越好（3,840 对 128）；LoRA 一侧：Beware of the Batch Size 有内部最优点，LoRA Without Regret 建议小于 32 | 128：Tulu、OLMo 2、Alpaca；64：Llama 2、Gorilla、ToolLLM、ReAct；48：ToolACE；16：torchtune；8：RouteNator |
| 热身与调度 | 5% 线性热身，线性降到 0 | p1 沿用 | Secret Recipe：SFT 不热身、常数学习率都不差；预训练四篇：短热身够用、线性降到 0 最好 | Tulu 3 0.03 线性；Gorilla 0.03 cosine；ToolLLM 0.04；Toolformer 10%；LLaMA-Factory / Axolotl 0.1 cosine；TrainingArguments 默认无热身、线性；LIMA / InstructGPT 无热身 |
| weight decay | 0.01 | 等于 PyTorch AdamW 默认值 | Massive SFT 扫 {0, 0.1} 选 0 | 0.1：Qwen2.5、Llama 2、LIMA、GPT-3；0：Tulu 1 / 2、Gorilla、Alpaca、SDFT、LoRA Learns Less；TrainingArguments 默认 0，文档称 0.01 为 standard |
| 梯度裁剪 | 1.0 | 惯例 | 没有一篇来源扫过或者解释过 1.0 | 1.0：Qwen2.5、GPT-3、SDFT、LoRA Learns Less、TrainingArguments 默认；0.3：QLoRA、RouteNator；5：ALFWorld、Tenney |
| 跨 0.6B / 1.7B / 4B | 同一套值 | 08-21 裁决：只变底座规模一个变量 | 扫过并且按尺寸改学习率的：Tulu 3、QLoRA、OLMo 2、InstructGPT；扫一次然后全尺寸沿用的：When Scaling Meets LLM Finetuning | 按尺寸降学习率的：DeepSeek、Alpaca、Tulu 1 / 2、torchtune；全尺寸同一套的：Toolformer、RouteNator、LoRA Land、APIGen |

三个底座的宽度（`config.json` 的 `hidden_size`，NFS 模型目录）：Qwen3-0.6B-Base 1024，Qwen3-1.7B-Base 2048，Qwen3-4B-Base 2560。按 arXiv 2602.06204 的 n^(−1/2) 规则，0.6B 到 1.7B 的最优 LoRA 学习率比值是 (1024/2048)^(1/2) = 0.71，0.6B 到 4B 是 (1024/2560)^(1/2) = 0.63。

## 4 解读

下面是我的解读，前三节的事实不依赖这一节。

关于全参学习率 1e-5：这个值落在扫描类来源给出的区间里面。7B 到 8B 上扫出来的最优值分布在 1e-6 到 2e-5 之间，1.3B 到 6B 上唯一一次扫描（InstructGPT）得到 9.65e-6，1e-5 在这个范围的中间。但是两件事从这些来源里看得很清楚：第一，同一尺寸换一个底座最优值可以差 20 倍（Secret Recipe 的 Granite 对 Mistral），OLMo 2 也明说 Llama 的配方对自己太低，所以别人扫出来的值只能说明量级，说明不了 Qwen3-Base 上的最优点；第二，没有任何来源在 Qwen3 上扫过 SFT 学习率，Qwen3 报告自己一个学习率数字都没印，torchtune 给 Qwen3 0.6B / 1.7B 的 2e-5 和 4B 的 5e-6 也是没有说明的配置值。1e-5 是一个量级正确、没有在这个底座上验证过的值。

关于 LoRA 的 2e-4 和 r=16 / alpha=32 / dropout 0.05：这四个数和 ToolACE 称为“最常见设置”的那一组完全一样，RouteNator 在 0.5B 到 7B 上用的也是这一组，所以“惯例”这个说法在文献里有实证。扫描类来源对这四个数的判断分开看：alpha=2r 有三篇支持（LoRA Learns Less、Lightning、Illusion of Equivalence 里 alpha=8 的对照更差）；dropout 0.05 有 QLoRA 一篇支持并且明写对 7B 以下有用；r=16 有两篇反对意见的方向不同，LoRA Learns Less 说代码任务 r 16 到 64 不够，QLoRA 说作用于全部线性层的时候 r 和结果无关，Internalizing Tool Knowledge 在工具任务上扫出峰值 32。学习率 2e-4 本身在三篇扫描里都是最好值或者最好值的邻居，但是它和我们全参 1e-5 的比值是 20 倍，两篇专门测这个比值的来源（LoRA Learns Less、LoRA Without Regret）给的都是 10 倍左右。这个 20 倍和 LoRA 原论文的 40 倍、Qwen 脚本的 30 倍同向，比十倍规则高一倍。两个数里如果有一个偏了，现有证据分不清是全参的 1e-5 偏低还是 LoRA 的 2e-4 偏高。

关于 3 个 epoch：扫过 epoch 的来源没有一篇支持第 3 个 epoch 有收益，Tulu 3 在百万级数据上 2 个封顶，SDFT 在几千到几万条上 1 个封顶，Lightning 在 5 万条上第 2 遍反而变差。用 3 的来源全部是只给数字的（Alpaca 一系和三个训练库默认值）。我们 b06 cgen 的 val_ce 在第 0 个 epoch 最低（0.4793），之后两个 epoch 上升到 0.6371 和 0.6697，和这些来源报告的方向一致。因为我们存的是 val_ce 最低的那一版，第 2 和第 3 个 epoch 在 b06 cgen 上花掉的是时间，没有污染评测用的权重；上一轮已经说过，这个上升本身分不清是学习率、epoch 还是数据的原因。

关于批 32、5% 热身线性降到 0、weight decay 0.01、裁剪 1.0：批 32 是 Massive SFT 在 8B 全参上扫出来的值，也是 InstructGPT 在 1.3B 上用的值，LoRA 一侧 LoRA Without Regret 建议小于 32。热身和调度在 SFT 上唯一一篇扫描（Secret Recipe）说不热身、常数学习率都不差，预训练那几篇说短热身够用、线性降到 0 最好；我们的 5% 线性热身加线性降到 0 和这两组结论都不冲突。weight decay 0.01 是 PyTorch 默认值，唯一一次 SFT 扫描选的是 0，Qwen 自家 SFT 用 0.1，三个值在文献里都有人用，没有一篇比过 0.01；AdamW 原论文说最优 weight decay 随更新步数变，b06 cgen 的 17,484 步（其余格子步数不同）没有对应的数字。裁剪 1.0 没有任何来源解释过，出处论文用的是 6 和 45。这四个值里 weight decay 0.01 和裁剪 1.0 是最没有证据的两个，但是也没有反证。

关于跨三个尺寸用同一套值：文献里两种做法都有，理由不同。按尺寸降学习率的做法更常见（Tulu 3、QLoRA、OLMo 2、InstructGPT、DeepSeek、Alpaca、torchtune），降的幅度在 8B 到 70B 之间是 2 到 2.5 倍，在 1.3B 到 175B 之间是 1.9 倍；全尺寸同一套的做法（Toolformer、RouteNator、LoRA Land、When Scaling Meets LLM Finetuning）给的理由都是可比性。我们的三个尺寸宽度是 1024 / 2048 / 2560，按 LoRA 那篇 n^(−1/2) 的规则，4B 的最优 LoRA 学习率大约是 0.6B 的 0.63 倍，这个差距小于文献里扫描网格的相邻两档（通常 2 倍到 2.5 倍），也就是说三个尺寸共用一个学习率在 LoRA 一侧大概率落在同一格里。全参一侧没有 SFT 的公式，只有 torchtune 从 1.7B 到 4B 把配置值从 2e-5 降到 5e-6 这一处没有说明的记录。锁死的决定在可比性上站得住，代价是 4B 那一格可能没有跑在自己的最优点上，这个代价现有数据量不出来。

关于“别人怎么选”的做法本身：扫描类来源的共同做法是固定其他设定，在对数刻度上取 3 到 5 个学习率跑一遍，按验证集指标挑（Tulu 3、OLMo 2、SDFT、Secret Recipe 都是这个流程，OLMo 2 还写了先 1 个种子挑配置、选定以后再补到 4 个种子），LoRA 一侧多一条“取不发散的最大学习率”（LoRA Learns Less）。TIMELINE 2026-08-21 那条写的“将来要自调再加对照轮”对应的就是这个流程，这一轮没有做。要做的话文献给出的最小版本是一个尺寸、一个任务、三个学习率各一跑。
