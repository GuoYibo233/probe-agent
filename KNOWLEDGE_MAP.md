# Knowledge Map — agent 记忆 / 遗忘 / 多轮 + 工具调用投机

> **这张表只收已核实的研究。** 建立于 2026-07-15。
>
> 建表原因：本次调研中，环境的检索摘要层与 subagent 报告层被抓到**至少三次幻觉**，其中一次是在**真论文、大体正确的描述里，于唯一承载论点的那句话上插入一句伪造原文**。凡是靠"搜索说"进来的东西，一律不可信。

## 入库标准

| 级别 | 含义 | 能不能写进论文 |
|---|---|---|
| **A** | 我自己抓了 arxiv abs / HTML / PDF / 官方页面，拿到**逐字原文** | 能 |
| **B** | subagent 声称抓了原文核实，**我没复核** | 引用前自己再抓一遍 |
| **隔离** | 没核实、来源存疑、或已证实为幻觉 | **不能** |

---

# A 级 — 我亲自核对原文

## 级联更新 / 派生关系

### MEMOREPAIR — arXiv:2605.07242（2026-05）
Yang Zhao, Chengxiao Dai, Mengying Kou, Yue Xiu

**命名了这个问题：**
> "When a source artifact is deleted, corrected, or invalidated by tool or API migration, descendants derived from that source can remain visible and steer future actions with stale support. We formalize this failure mode as **the cascade update problem**."

**它自己承认的致命假设（Limitations）：**
> "MemoRepair relies on **complete influence provenance**: each durable artifact must record the artifacts used to derive it. Missing edges can leave affected descendants outside the withdrawn cascade… **dropping 1% of influence edges yields 17.7% Leak (≈18× amplification)**, a graceful linear degradation that identifies complete influence provenance as **the main system-level invariant** behind the contract guarantee."

**确认的事实：**
- 系统/方法论文，不是 benchmark。归约到最大权前驱闭包，s-t min-cut 求解。
- 陈旧记忆暴露 **69.8–94.3% → 0%**。**那个区间是六个不同记忆系统之间的差异**（Mem0、Zep/Graphiti、MemR3、A-MEM、O-Mem、TierMem），**不是**未解释的方差。
- 在 ToolBench（经 StableToolBench）+ MemoryArena 上评测，**照原样用，没有自己合成撤回事件**。
- 产物类型：`{record, cache, summary, skill}`
- **两次独立读取都没找到"标准答案的边从哪来"的描述。** 也**没有**验证过边本身是否正确——只测了"边错 1% 会怎样"。
- **没有评测语义派生**（模型读了一条事实然后写了条笔记），只讨论确定性的工具产物。

### MEME — arXiv:2605.12477（2026-05）
Seokwon Jung, Alexander Rubinstein, Arnas Uselis, Sangdoo Yun, Seong Joon Oh

> "defines six tasks… including three not scored by prior work: **Cascade and Absence (dependency reasoning) and Deletion**"
> "all systems collapse on dependency reasoning under the default configuration **(Cascade: 3%, Absence: 1% in average accuracy)**"
> "Each domain uses a single **hand-crafted knowledge graph** G reused across episodes"

**要点：图是手工造好预先给定的。** 依赖是事实之间的世界/逻辑关系，**不是** agent 自己产出的产物。1-hop / 2-hop 都有，但"full analysis across depths isn't the focus"。指标是二值准确率。

### STALE — arXiv:2605.06527（2026-05）
Hanxiang Chao, Yihan Bai, Rui Sheng, Tianle Li, Yushi Sun

三个探测维度：State Resolution / Premise Resistance / Implicit Policy Adaptation。400 个专家验证的冲突场景，1200 道题，最长 150K token。**顶级模型 55.2%。**

> "**Type II: Propagated Conflict.** The new observation m_n updates attribute b, and this change cascades through a causal or logical dependency to invalidate a belief about a structurally related but distinct attribute a"

**关键边界：只评测模型对提问的回答，不评测它以前产出的东西。** 没有任何部分测"agent 能不能修正自己先前的输出"。

### PLACEMEM — arXiv:2607.04089（2026-07）
Sukanta Ganguly

系统立场论文 + 可执行的控制面原型。有 "cascading invalidation over live streamed backends"、versioned capsules、以及一个测 first-token 延迟 / 复用 / post-correction behavior 的 harness。

### Governed Shared Memory — arXiv:2606.24535（2026-06）
Yanki Margalit, Nurit Cohen-Inger, Erni Avram, Ran Taig, Oded Margalit

四个失败模式："unauthorized leakage, stale propagation, contradiction persistence, and provenance collapse"。

> ⚠️ **搜索摘要曾把 PLACEMEM 的"dependency edges between capsules and derived artifacts"错安到这篇头上，两次。** 本篇的 provenance **只追踪记忆项自身的 lineage**，不做派生产物的级联失效。

### AgentProp-Bench — arXiv:2604.16706（2026-04）
Bhaskar Gurram

**已排除，不相关。** 是工具调用管线里的**错误传播**（单轮、单参数注入），不是记忆失效。作者明确把多轮/多参数留给 future work。

---

## 多轮对话 / 早期承诺

### LLMs Get Lost In Multi-Turn Conversation — arXiv:2505.06120（2025-05-09）★ 用户提供
Philippe Laban, Hiroaki Hayashi, Yingbo Zhou, Jennifer Neville

**完整摘要（逐字）：**
> "Large Language Models (LLMs) are conversational interfaces. As such, LLMs have the potential to assist their users not only when they can fully specify the task at hand, but also to help them define, explore, and refine what they need through multi-turn conversational exchange. Although analysis of LLM conversation logs has confirmed that underspecification occurs frequently in user instructions, LLM evaluation has predominantly focused on the single-turn, fully-specified instruction setting. In this work, we perform large-scale simulation experiments to compare LLM performance in single- and multi-turn settings. Our experiments confirm that all the top open- and closed-weight LLMs we test exhibit significantly lower performance in multi-turn conversations than single-turn, with an average drop of **39%** across six generation tasks. Analysis of **200,000+** simulated conversations decomposes the performance degradation into two components: **a minor loss in aptitude and a significant increase in unreliability**. We find that LLMs often **make assumptions in early turns and prematurely attempt to generate final solutions, on which they overly rely**. In simpler terms, we discover that *when LLMs take a wrong turn in a conversation, they get lost and do not recover*."

**为什么它重要：** 它把「早期设定难以修改」这个现象**大规模验证了**，比头脑风暴文档早一年。文档里给这条标的"现象是否普遍需先验证"——已经验证过了。

**关键边界（今天最重要的观察）：** 这篇**没有记忆系统**。整段对话就在上下文里，什么都没被忘、没被压缩，纠正就在眼前。**模型照样不改。** 这给所有"靠修记忆结构解决"的路线设了天花板。

**原论文对推理模型的预防性回应（B 级，agent 引）：**
> "Additional test-time compute (reasoning tokens) does not help models navigate multi-turn underspecification, as the two reasoning models included in the experiment (o3, Deepseek-R1) deteriorate in similar ways to non-reasoning models."

### Found in Conversation (FiC) — arXiv:2605.24432（2026-05-23）
Tianlang Chen, Shirley Wu, Jure Leskovec

> "Across model families (Llama, Qwen, Phi, and OLMo) and sizes (3B-14B), FiC recovers **at least 92% of single-turn performance and reaches 100% on two Llama backbones**"
> "**View-Asymmetric Self-Distillation**, which distills across two views of the same task information — single-turn view for the teacher, multi-turn view for the student"

**要点：** 聚合差距基本被修好了。**但摘要里没有说它教会了模型"修正"还是只教会了"别过早下结论"**——从方法看（把单轮行为蒸馏进多轮），更像是**避免**承诺而非**修正**承诺。

---

## 机制工具

### Verbalizable Representations Form a Global Workspace in Language Models — transformer-circuits.pub/2026/workspace（2026-07-06）
Anthropic

> "The Jacobian lens identifies a vector representation that **encodes the potential for the model to verbalize that token in the future**."
> "We define the **J-space** as the set of points expressible as a **sparse nonnegative combination** of J-lens vectors."
> "The model can speak fluently, parse its input, and **perform a great deal of automatic inference with its J-space suppressed**"
> "In some cases, the information relevant to the automatic computation is present in the J-space but unused for the task; **in others, it is not present at all**."
> "The J-space component typically accounts for only a small fraction of total activation variance (varying by layer, but **never more than 10%**)."

**测试模型：** Claude Sonnet 4.5 / Haiku 4.5 / Opus 4.5–4.6。**这些数是 Claude 的，Qwen 上未知。**

**作者自陈的局限：**
> "The Jacobian lens is an **imperfect tool**, which we believe only **approximately and incompletely** captures the model's underlying workspace structure."
> "It only identifies vectors associated with concepts that correspond to **single tokens** in the model's vocabulary, but many important concepts correspond to multiple tokens."

**⚠️ 一个必须记住的边界：** 论文**没有**主张模型能内省自己的 J-space。它主张的是 **J-space 的内容能预测模型会说出什么**。从前者推到"绕开 J-space 的影响模型报告不出来"，**是推论，不是论文的话**。

### anthropics/jacobian-lens（GitHub, Apache 2.0）
> "This repo fits the lens on **open-weights decoder transformers**, applies it, and renders the interactive layer × position view shown below. **Examples use Qwen**; other HuggingFace decoders adapt cleanly."
> "linearly transports a residual-stream vector at any layer and position into the final-layer basis, then decodes it with the model's unembedding into **a ranked list of vocabulary tokens**."

**API：** `from_hf` / `fit` / `JacobianLens.from_pretrained` / `.apply` / `.merge` / `.save`
**walkthrough.ipynb 示例模型：** `Qwen/Qwen3.5-4B`（备选 `Qwen3.6-27B`）
**每层一个 `[d_model, d_model]` 矩阵。** ~100 条 prompt 够拟合，成本由 backward pass 主导。

**❗只有读出。** 没有分解（J-space vs 非 J-space）、没有抑制、没有注入。论文做的实验，**盒子里没全给**。而且 J-space 是**锥不是子空间**，所以"减掉它"要解带非负约束的优化，不是投影。
标着 "Reference implementation. Not maintained and not accepting contributions."

---

## 方法论警告

### MemDelta — arXiv:2606.29914（2026-06）
Kuan Wang

> "reported gains often mix changes in the memory method with changes in **the language model, embedding model, or retrieval pipeline**"

**这组数可能是整个调研里最重要的东西：**

| | 效应量 |
|---|---|
| 换个模型 | **±31pp**（Sonnet 偏好 RAG +31，Gemini 偏好全上下文 +14） |
| 换个 embedding | **±6.2pp** |
| RAG vs 全上下文 | 47.2% vs 49.8%，**p=0.34（无差别）** |
| Mem0 vs 云 RAG | 6 类问题只赢 2 类，**代价 50 倍** |

**agent 自己管记忆，还不如最朴素的检索。**

**含义：这个领域测的效应，可能小于它的噪声。** 任何"我们的记忆系统好 3 个点"的主张都在噪声里。**这个结论比任何选题都更该先处理。**

### PersistBench — arXiv:2602.01146（2026-02）
> ⚠️ **标题骗人。** 叫 "When Should Long-Term Memories Be Forgotten by LLMs?"，**实际是安全论文**——讲跨域泄漏和记忆诱导的谄媚。18 个模型，跨域失败率中位数 53%，谄媚 97%。**跟"什么时候该忘"基本无关。**

---

## 工具调用投机 / 思考中途注入（2026-07-25 占位核查）

> **占位结论：椅子半占。** 机械注入已有先例（Gim 2024 → SIA），隐藏态触发的预取注入在**检索域**已被 PPRAG 做完。仍空的闭环：**隐藏态触发 → 带参数的通用工具投机执行 → 思考中途回填 → 与模型最终发出的调用做事后验证**，以及那条"注入时机 vs 收益 vs 风险"曲线。

### Predictive Prefetching RAG — arXiv:2605.17989（ICML26）
**对第三档威胁最大的一篇。** 2026-07-25 重核，比 07-20 的记录更强。

> "demonstrates up to 43.5% end-to-end latency reduction and 62.4% improvement in time-to-first-token"
> "exploiting semantic precursors in generation dynamics that emerge several tokens before uncertainty becomes critical"

**§4.1 预测器读什么（这条是 07-25 新增的关键事实）：**
> "𝐇t, 𝐀t, and 𝐕t denote internal LLM representations from middle-upper layers (i.e., 30–45% of model depth), and 𝐨t contains output distribution statistics"

**即：隐藏态 + 注意力矩阵 + value 向量 + 输出分布统计。"读内部状态做预取"在检索域已被占。** 43.5% 与 PASTE 的 43.5% 撞数是巧合，两篇原文均核实有此数。剩余 delta：只有"检索"一种工具、query 之外无参数结构、无副作用门控、无事后验证环。

### Speculative Interaction Agents (SIA) — arXiv:2605.13360
类型：系统。实时语音 agent 场景。

> "We also propose Speculative Tool Calling as a method to manage task execution when the agent is still unsure if it has received the full information or if additional user information may later be provided."
> "our method can be applied out-of-the-box to existing real-time cloud APIs, providing 1.3-1.7× speedups with minor accuracy loss"

**§3.3 注入句（逐字，二次核实）：**
> "Similar to (Gim et al., 2024), as tool calls finish execution, the results can be injected immediately into the context of the model."

**边界：** 它赌的是**用户**还会不会补信息，不读模型内部状态（一次全文读取未见任何 hidden state / activation 表述——是一次读取的结论，非穷尽）。注入发生在异步结果就绪时，非隐藏态预测触发。edge 模型需 SFT（clock-based training）。机械注入的先例链上溯到 **AsyncLM（Gim et al. 2024,已核实,见下）**。

### AsyncLM 2412.07017（Gim, Lee, Zhong;2026-07-27 亲核,A 级）

> "the current approach to LLM function calling is inherently synchronous, where each call blocks LLM inference … AsyncLM introduces an interrupt mechanism to asynchronously notify the LLM in-flight when function calls return. We design an in-context protocol for function calls and interrupts, provide fine-tuning strategy to adapt LLMs to the interrupt semantics … reduce end-to-end task completion latency from 1.6x-5.4x … on … BFCL."

**边界与占位:** 调用仍由模型自己发出——AsyncLM 消掉"等",不消掉"想",不预测、不提前、不读隐藏态;中断语义靠微调习得。与本项目互补(投机出的调用可以走它的异步执行底座),两侧 related work 必引。机械注入先例链源头就此闭合:AsyncLM(2024) → SIA(2026)。

### IdleSpec — arXiv:2605.22154
类型：推理方法。**与第三档互补而非竞争：它拿空闲换准确率，我们拿预测换延迟。**

> "IdleSpec iteratively generates plan candidates during idle periods and, once observations become available, aggregates them to guide the next reasoning step."
> "on the GAIA and FRAMES, IdleSpec achieves 55.6% average accuracy with Gemini-2.5-Flash, surpassing the vanilla baseline without idle-time usage by 5.1%"

投机的是**计划候选**，不是工具结果；不提前执行工具。好 baseline 候选。

### 依赖图探针 — arXiv:2605.25310
类型：表征分析（送弹药的）。Qwen3-32B 主实验，Llama-3.3-70B 复现 patching。

> "an edge i→j iff call i's output supplies an argument of call j"
> "Our claims concern representation, not behavioural control, and span two model families and one primary domain."

**承重句已二次核实（abs + html 两条路径，逐字一致）。** 残差流里连调用间依赖拓扑都线性可解码，且作者明说不做行为控制——把"拿它做系统"的门敞着。注意：它解码的是**依赖结构**，不是工具名或参数值。

### Auton Agentic AI Framework — arXiv:2602.23720
类型：框架/立场论文。**解除警报**（搜索转述称它"预测工具输出并继续推理"——摘要中无此内容；按规矩这只证明**摘要**没有，全文未查，但立场论文无实验，威胁级别低）。

> "describes runtime optimizations -- including parallel graph execution, speculative inference, and dynamic context pruning -- that reduce end-to-end latency for multi-step agent workflows"

---

## 二轮占位核查（2026-07-27，可学习投机器四头设计的定位检查，五篇亲核）

### B-PASTE — arXiv:2604.16469（2026-04-09，Yanfei Song，单作者）
> "maintains a bounded beam of future execution subgraphs, **ranks them by expected critical-path reduction rather than raw execution probability**, and schedules only high-value branch prefixes on transient slack resources"
> "speculating likely future tool invocations from **mined control-flow and data-flow regularities**"（继承 PASTE）

**⚠️ 时机/价值感知的投机调度在系统层已被占。** 但：不读隐藏态，收益=工作流结构估算的关键路径缩减，与模型认知状态无关——看不见死区那类现象。我们的措辞必须定为"从模型内部状态学注入时机"。

### Cost-Aware Speculative Execution — arXiv:2606.07846（2026-06-05，Faisal Fareed，单作者）
> "pricing each speculation in real dollars at separate input and output rates" / "via an **expected-value rule with a failure-weighted cost term**"
> "five-stage calibration pipeline (offline replay, shadow, canary, online calibration, drift-triggered kill-switch)"

同上占位系统层"要不要投机"的成本收益，校准式而非学习式，不读内部状态，成本单位是美元不是思考 token。

### SpecExit — arXiv:2509.24248（2025-09-29）
> "predicts both future tokens and **an early-exit signal directly from a lightweight draft model** without probing overhead"
> "reducing average generation length by 66% and achieving a 2.5x speedup … **leverages the inherent signals from hidden states** to provide effective early-exit signals"

无工具调用。**"投机思考本身/推理早退"赛道已拥挤**（另见 2504.15895 Dynamic Early Exit、2604.06787、2510.10103 等，均未逐篇核），不做该方向 novelty 主张；反向用途：隐藏态携带时机信号的**友军证据**。

### Ghost Tool Calls — arXiv:2606.02483（2026-06-01，Mohammadi/Klein/Arora/Bindschaedler）
> "**Timing is the issue, not authorization**: no commit-time cleanup, read-only restriction, or access-control allow-list unsends what an observer already holds"
> "only **issue-time policies** that change or suppress the speculative call's argument or destination projection before dispatch reduce it"

隐私正交，非 novelty 威胁；入设计空间（层②只读门控的隐私对应物），讨论段引用。

### OLIVIA — arXiv:2605.11169（2026-05-11，UCSD/Adobe/UIUC）
> "models the LLM's final action-selection layer as a **contextual linear bandit** over candidate actions, **with frozen hidden states as decision contexts**"
> "In deployed settings where agents **repeatedly handle related multi-step tasks**…"

无投机、无预取、不预测未来调用（在候选动作间打分）。但"隐藏态+在线决策层+重复相似任务"三个关键词都贴着我们——**benchmark 侧与方法侧 related work 都必引**。

# B 级 — agent 核对，我未复核（引用前自己再抓一遍）

## 哲学 / 经典

**Harman, *Change in View*, MIT Press 1986, ch. 4** — "Karen's Aptitude Test"
> "later she is informed that **the report about her aptitude scores was incorrect**!… How should Karen revise her views?"
> "The **foundations theory** says she should abandon all beliefs whose **justifications depend in part on** her prior belief about her aptitude test scores."
> "**People do not seem to keep track of the justifications of their beliefs.**"

**Doyle 1979（TMS）** — 确认 TMS 是**记录** justification 的：
> "The Truth Maintenance System (TMS) is a problem solver subsystem for performing these functions by **recording and maintaining the reasons** for program beliefs."

## provenance / lineage（这条线证明「推断 vs 记录」不是新意）

- **RELIC**, PVLDB 14(12):2795–2798, **2021** — 已经立过这个区分，且已用 TP/FP/FN 对隐藏 ground truth 打分：
  > "Most prior work deals with lineage capture… which requires active API calls or logging 'hooks'… **This not useful in a retrospective context**."
- **NeuroTaint / TaintBench**, arXiv:2604.23374（2026-04）— **推断边、有 benchmark、F1 0.928**：
  > "NeuroTaint therefore audits execution traces offline to **reconstruct provenance**… **rather than relying on exact string matches** or pre-defined source-sink paths alone."
  > 但：source/sink 是标注给定的，二值可达性，安全污点语义，零 retraction 命中。
- **TRACE-Bench / TRACER**, arXiv:2605.09934 — "sentence-level provenance reconstruction"，relation space = Quotation / Compression / **Inference**。无 retraction，单轨迹内。
- **MemLineage**, arXiv:2605.14421 — 定义了 `LmSelfEval`（让 LLM 判"p 在多大程度上影响了 c"）**但从没跑过**：
  > "the LmSelfEval judge is exercised by a **scripted judge that returns a pre-set per-step weight schedule**"
  > "a real LLM judge that **hallucinates EXTERNAL parents**… we leave a real-LLM utility sweep **to follow-up**"
- **ARGUS**, arXiv:2605.03378 — **"Influence-Provenance Graph (IPG)" 这个词已被占用。换词。**
- **Schema Lineage Extraction**, arXiv:2508.07179 — 1700 条人工标注 lineage，12 个模型
- **FTRACE**, arXiv:2205.11482 — fact tracing，"the first quantitative benchmark"
- **provenance survey**, arXiv:2606.04990 — §7.2 让问题合法化但没认领：
  > "String-level matching and citation presence are therefore **insufficient**… robust claim-level provenance for long agent executions **remains open**"
  > ❗**它引用了零篇 MEMOREPAIR / MEME / PLACEMEM / ForgetEval / Supersede / STALE。两个社区互不引用。**

## 多轮 / 承诺

- **MINT**, arXiv:2604.04325（2026-04，医疗诊断）— **推翻"承诺不可逆"**：
  > "incorrect-to-correct answer revisions occur at up to **10.6 times** the rate of correct-to-incorrect flips, revealing a **latent capacity for self-correction** that premature commitment forecloses"
- **When Correct Beliefs Collapse**, arXiv:2605.23932（临床对话）：
  > "LLMs can exhibit severe multi-turn sycophancy… **abandoning initial correct diagnosis under escalating pressure**"
  > ⚠️ 与 MINT 同为**医疗域**。"两条文献"可能是一条。**这一条待验，且它决定「顽固 vs 墙头草」不对称成不成立。**
- **CCOPD / Same Evidence, Different Answers**, arXiv:2605.30251（2026-05）— 已占用 "self-anchored drift" 这个名字：
  > "responses produced under partial information introduce unsupported assumptions, and those assumptions later distort the final answer"
- **When Agents Commit Too Soon**, arXiv:2606.22936（2026-06）— 占了"premature commitment"+ 表征诊断，但明确做不到区分对错：
  > "It does not track correctness: committed-wrong and committed-correct questions are **not separable** in activation similarity."
- **When Attention Closes**, arXiv:2605.12922（2026-05, Dongre et al./Hakkani-Tür）— 机制圈地，但瞄的是**另一个**失败（丢线索，不是承诺）
- **Intent Mismatch**, arXiv:2602.07338（2026-02, CityU HK）— **反驳 Laban 的分解**：根因是意图对齐落差，不是 unreliability
- **ERGO**, arXiv:2510.14077 — "+56.6% average gain, aptitude +24.7%, unreliability −35.3%"
- **RLAAR**, arXiv:2510.18731 — "62.6% → 75.1%"

**agent 逐篇核实后的结论（B 级，很重要）：**
> "**None makes a model revise a commitment it has already made.**"
> 每个修法都靠**阻止或绕开**承诺——拒答、熵触发重置、滚动记忆、全上下文蒸馏、删掉那一轮。

**Laban 原论文 Table 2（agent 从原文取，纠正了我的错误猜测）：**
GPT-4o-mini：Full **86.8** → Sharded **50.4** → Recap **66.5** / Snowball **61.8**
GPT-4o：Full **93.0** → Sharded **59.1** → Recap **76.6**
→ **"重启+摘要"只挽回约一半。简单 prompt 修复解决不了。**

---

# 🚫 隔离区 — 不许引用

| 条目 | 状态 |
|---|---|
| **arXiv:2605.12087 关于 "retraction" 的那句引文** | **已证实为伪造。** subagent 在真论文、真引文之间插了一句原文里根本不存在的话，且正好落在承载论点的位置。全文核查："retracted"/"retraction" 二词在该论文中**完全不出现**。 |
| **Laban 2505.06120 的 ICLR 2026 接收 / outstanding paper** | **未核实。** openreview 挡爬虫，该说法只来自搜索摘要和一个营销博客。 |
| **MEMOREPAIR 零引用** | 弱证据。Semantic Scholar 限流，覆盖也滞后。 |
| Taxidou et al. 2017 摘要 | 出版商屏蔽，未核实 |
| Doyle 1992 "Foundations versus coherence" 章节内容 | 仅有书目数据，内容未核实 |
| ConvMemory v3, arXiv:2606.26753 | 未核实 |
| provenance survey 的 relation space（"Support, Derive, Depend-on…"） | 未核实 |
| Laban 各模型细分数字（GPT-4.1 91.7→70.7 等） | 来自二手博客，未对原文 |

| SIA "不读隐藏状态" 这一绝对表述 | 一次全文读取未见 ≠ 不存在；引用前需二次全文检查 |

---

# 已确认死亡的方向（别写）

| 想法 | 死于 | 时间 |
|---|---|---|
| 相关性 → 遗忘阻力 | 混淆变量：相关性与波动性大致正交（**注：这是一段推理，不是证据。可重开。**） | — |
| 派生持久性 / 撤回不传播 | MEMOREPAIR 已命名 cascade update problem | 2026-05 |
| 「没人测推断出来的图」 | NeuroTaint / TaintBench，F1 0.928 | 2026-04 |
| 「事后推断 vs 当场记录」这个区分 | RELIC，PVLDB | **2021** |
| "influence provenance graph" 这个词 | ARGUS 占用 | 2026-05 |
| 把记忆做成网 | Zep/Graphiti、A-MEM 本来就是网，**且就在 MEMOREPAIR 那 70–94% 的基线表里** | 2024– |
| 早期设定难修改（现象） | Laban 大规模验证 | 2025-05 |
| 早期设定难修改（修复） | FiC 挽回 92–100% | 2026-05 |
| 早期设定难修改（机制） | Intent Mismatch + When Agents Commit Too Soon + When Attention Closes，三家在抢 | 2026-02 ~ 06 |
| 「第一个把工具/检索结果中途注入上下文」的说法 | 机械注入：Gim 2024 → SIA；隐藏态触发预取注入（检索域）：PPRAG。**闭环+通用工具+事后验证仍空** | 2026-07-25 |

---

# 待验的开放问题

1. **「顽固 vs 墙头草」不对称是真的，还是医疗域假象？** MINT 和 When Correct Beliefs Collapse 都是医疗。**这条决定该方向成不成立。**（agent 调查中）
2. **有没有人在同一批模型、同一设定下，直接比过"证据推"vs"社会压力推"？** 若有，方向死。
3. **真实 agent 的派生里，机械可得的边占多少、语义的占多少？** 若机械的占绝大多数，MEMOREPAIR 的假设基本成立，整个 provenance 洞是边角料。**从未核实过。**
4. **FiC 是教会了"修正"还是只教会了"别过早下结论"？** 要读全文。
5. **MemDelta 的噪声结论若成立，这个领域现在还能不能做可测的工作？**
6. ~~**上帝视角注入（oracle injection）能省多少思考 token？**~~ **已回答（2026-07-26，自有实验，oracle_inject/FINDINGS.md）：省得动，方向活。** 授权措辞下开场注入省 81–91% 思考 token（Qwen3.5-4B/Qwen3-4B/Qwen3-8B），acc 0.98–1.00；但曲线非单调——贴近调用点（提前25–50 tok）注入是**负收益死区**；授权措辞是实测必要条件（无授权则脱轨或守协议归零）；授权导致错误注入全毒（acc 0.02–0.14）。新警报：探针高置信时点 ≈ 死区，收益大头在"很早注入"= 记忆预取侧。
7. **PPRAG 的隐藏态预测器搬到通用工具调用上还成立吗？** 检索只有 query 一个自由度；带结构化参数的工具是否还有"提前几个 token 的语义前兆"。**这条决定我们对 PPRAG 的 delta 是真是空。**
