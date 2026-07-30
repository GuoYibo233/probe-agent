# T12c 被试保真度审查:ReMem / DynamicCheatsheet / AWM

日期:2026-07-30。审查对象:`related_work/evo_mem/`(按论文重建的骨架,**非官方实现**,
见 `related_work/evo_mem_INTEGRATION.md` §0)。
驱动侧:`benchmark_design/evomem_driver.py`(路线 b,我们自己的任务流)。
本文件回答 `evo_mem_INTEGRATION.md` §7 第 4 条:**三个被试的重建代码与原论文机制差在哪,
影响不影响跑分结论**。

审查方式:论文一律自己抓一手来源(arxiv abs / HTML 全文 / 官方 repo 的 prompt 文件),
引文逐字;抓不到标 UNREACHABLE 或 NOT FOUND。代码结论一律带文件行号,
行号对应本次审查时的工作树(`related_work/` 在 .gitignore 里,不入库)。

---

## 0. 先纠正一个前提:ReMem 的"原论文"就是 Evo-Memory 本身

任务书写的是"ReMem 原论文自己去抓"。查证结果:**arxiv 上没有一篇独立的 ReMem 论文。**
ReMem 是 Evo-Memory 这篇 benchmark 论文自己提出的方法 —— 它既是评测台也是方法:

> "To better benchmark experience reuse, we provide a baseline method, ExpRAG, for retrieving
> and utilizing prior experience, and further propose ReMem, an action-think-memory refine
> pipeline that tightly integrates reasoning, task actions, and memory updates to achieve
> continual improvement."
> —— arXiv:2511.20857 abstract,<https://arxiv.org/abs/2511.20857>

论文全名与作者(v1 2025-11-25,v2 2026-05-18):

> "Evo-Memory: Benchmarking LLM Agent Test-time Learning with Self-Evolving Memory"
> Tianxin Wei, Noveen Sachdeva, Benjamin Coleman, Zhankui He, Yuanchen Bei, Xuying Ning,
> Mengting Ai, Yunzhe Li, Jingrui He, Ed H. Chi, Chi Wang, Shuo Chen, Fernando Pereira,
> Wang-Cheng Kang, Derek Zhiyuan Cheng
> —— <https://arxiv.org/abs/2511.20857>

排除过的同名干扰项(都抓了 abstract,都不是本目标):
arXiv:2602.13530 "REMem: Reasoning with Episodic Memory in Language Agent"(Yiheng Shu 等,
2026-02,离线 memory graph + 在线 agentic retriever,对标 Mem0/HippoRAG 2);
arXiv:2506.23041 ReMem(ViT 蒸馏,与 agent 无关)。

**这条纠正对论文措辞有直接后果**:引 ReMem 只能引 Evo-Memory 那篇,
不能当成一个独立的 baseline 论文来 cite;而且 DC 与 AWM 是被 Evo-Memory *评测* 的外部方法,
它们有各自的原论文(见 §2、§3),而重建代码的 docstring 写的是
"Based on Suzgun et al. (2025) **as referenced in the paper**"
(`dynamic_cheatsheet.py:10`)、"Based on Wang et al. (2024) **as referenced in the paper**"
(`awm.py:6`)—— 即重建者是照 Evo-Memory 对 DC/AWM 的**一句话描述**写的,
不是照 DC/AWM 原论文写的。这解释了后面所有失真的来源。

Evo-Memory 对 DC/AWM 的全部描述就这么几句(逐字):

> "Dynamic Cheatsheet (DC) and Agent Workflow Memory (AWM) emphasize the reuse of procedural
> knowledge, encoding "how-to" information rather than static facts."
> "Memory-based agents for procedural knowledge, including Dynamic Cheatsheet (DC) with two
> variants Cumulative (Cu) and Synthesis (RS) and Agent Workflow Memory (AWM)"
> —— <https://arxiv.org/html/2511.20857v2>,§4.1.3 Methods

而 `dynamic_cheatsheet.py:3-4` 的 docstring 是
"Dynamic Cheatsheet emphasizes the reuse of procedural knowledge, encoding "how-to"
information rather than static facts." —— 逐字抄自上面那句。证据链闭合。

### 三档判语速查

| 被试 | 多轮(ALFWorld 类) | 单轮(2Wiki QA 类) | 一句话 |
|---|---|---|---|
| ReMem | **忠实** | **简化但方向一致** | 多轮 prompt 逐字复刻论文 Appendix C;单轮丢了 Rationale 字段,而库里那份忠实模板是死代码 |
| DC-Cu | 失真需声明 | 失真需声明 | cheatsheet 从"被整体重写的文档"退化成"append-only 的一句话列表";curator 只看到抽取后的短答案 |
| DC-RS | **失真需声明(机制缺失)** | **失真需声明(机制缺失)** | 原文的判别性机制是"先检索+先策展再作答",重建版是"先答后抽",DC-RS 退化成换了检索器的 DC-Cu;检索器还从 embedding 退成词袋 |
| AWM | 失真需声明 | **机制完全缺失** | 单轮路径根本不抽 workflow → 库永远空 → AWM 退化成一个上下文更弱的 ExpRAG |

---

## 1. ReMem

### 1.1 原文机制(Evo-Memory, arXiv:2511.20857)

**三个操作的定义**(§3.3):

> "At each step t, given the current input x_t, memory state M_t, and previous reasoning traces
> o^{1:n-1}_t at this step, the agent selects one of the operations: a^n_t ∈ {Think, Act, Refine}."

> "Think produces internal reasoning traces that help decompose the task and guide subsequent
> actions; Act executes an operation in the environment or outputs a response observable to the
> user; Refine performs meta-reasoning over memory, which exploiting useful experiences, pruning
> noise, and reorganizing M_t, to better support future reasoning and action. Within each step,
> the agent may perform multiple rounds of Think and Refine, and the step terminates once an Act
> operation is selected."
> —— <https://arxiv.org/pdf/2511.20857v1>,§3.3(原文语法瑕疵照抄)

**写入(Evolve)**:任务级条目,含反馈,每次交互后写:

> "Evolve. After obtaining ŷ_t, the agent constructs a new memory entry m_t = h(x_t, ŷ_t, f_t)
> that captures the current step's experience together with the feedback f_t, such as whether
> the task was completed."(§3.1)

> "Each memory entry m_i = S(x_i, ŷ_i, f_i) encodes a structured experience text with template S."(§3.2)

> "Feedback f_t is considered as the correctness signal."(§4.1.1 末)

**读取(Search)**:

> "For efficient retrieval and fair comparison across methods, we utilize the BAAI/bge-base-en-v1.5
> encoder as the retriever to index both queries and memory items. During inference, the current
> question is encoded as a query and compared with all stored memory embeddings, retrieving the
> top-k most relevant items (default k = 4) for contextual augmentation. This setting ensures a
> consistent retrieval budget across all methods."(Appendix A.2)

> "Unless otherwise specified, retrieval and generation operate within the same pipeline, and the
> retrieved items are appended to the prompt following the order of relevance, from most to least
> similar."(Appendix A.2 末)

**prompt 模板**(Appendix C,多轮):

> "RELEVANT EXPERIENCE FROM SIMILAR TASKS / ================================================== /
> [Experience #1] / Goal: [similar goal] / Trajectory: [action sequence] /
> Correctness: [success/failure] / [Experience #2, #3, ...]"

> "Format 1 - Prune experiences: / Think-Prune: <IDs> / Remove unhelpful experiences from
> 'RELEVANT EXPERIENCE' section (e.g., "1,3" or "2-4")"

**prompt 模板**(Appendix C,单轮):

> "You are a helpful assistant with access to LOCAL EXPERIENCE MEMORY. Each memory may contain
> past experience, rationales, domains, and skills."

**论文没说的三件事**(标 NOT FOUND,不许当已核实用):
1. ReMem 专属的 memory entry 模板 —— §3.3 通篇只讲三个操作,不讲写什么;(x, ŷ, f) 的定义写在通用框架 §3.1 和 ExpRAG §3.2 里。
2. 主设置是否只存成功经验 —— RQ4 把"成功+失败都存"当独立设置测(> "Table 4 evaluates how agents perform when both successful and failed task experiences are stored in memory."),**暗示**主表可能过滤,但没有一句明说。
3. Think-Prune 是否真从持久库删条目 —— 论文两处措辞冲突:prompt 写的是 "Remove ... from 'RELEVANT EXPERIENCE' section"(只剪当前 prompt 的检索段),Appendix B.2 却统计跨数据集的 pruning rate 并说 "the pruning mechanism effectively identifies and discards domain-irrelevant experiences"(读起来像删库)。**无法定论**。

官方代码:NOT FOUND。论文只承诺
> "will release all code and configurations for reproducibility."(§1)
全文无指向本工作的 github 链接;GitHub 搜 "Evo-Memory" 与一作 weitianxin 的仓库列表均无此项(线索,非证据)。

### 1.2 重建版实际行为

**多轮上下文:逐字复刻论文模板。** `remem.py:401-403` 生成的经验块是

```
[Experience #1]
Goal: {entry.input_text}
Trajectory: {traj}
Correctness: Success/Failure
```

字段名与顺序和 Appendix C 的 "Goal / Trajectory / Correctness" 完全一致;
`remem.py:442-457` 的 OUTPUT FORMAT 三格(Think-Prune / Think / Action)连括号里的例子
`(e.g., "1,3" or "2-4")` 都一样。同一段文字也出现在
`memory/context.py:196-211` 的 `StructuredContextBuilder` 里。

**Think/Refine/Act 循环:结构对。** `remem.py:110-140`(单轮)、`remem.py:248-278`(多轮)
是 `for iteration in range(max_iterations)` 里循环 Think/Refine,遇到 Act 就跳出 —— 与
"may perform multiple rounds of Think and Refine, and the step terminates once an Act
operation is selected" 一致。`parse_response`(`remem.py:471-512`)按
`Think-Prune:` / `Think:` / `Final Answer:` / `Action:` 四个前缀分派,兜底当 Act。

**Refine 只裁 prompt,不动库。** `_handle_refinement`(`remem.py:280-299`)唯一的实际效果是

```python
state.retrieved = [r for i, r in enumerate(state.retrieved) if (i + 1) not in ids_to_prune]
```

即从**本题当前的检索结果列表**里剔除,持久 `Memory` 一条不删。而 `state.retrieved` 在
`remem.py:104` 只算一次,所以剪枝只影响同一道题后续 iteration 的 prompt,下一题重新检索时
被剪掉的条目原样回来。全库范围核对:`Memory.prune_by_relevance`(`memory/base.py:220`,
docstring 自称 "implements the memory refinement aspect of ReMem")**零调用者**;
`Memory.remove` / `remove_by_ids` 在整个 `evo_memory/` 里也没有任何 agent 调用
(只有我们 driver 的 `store_policy=successful_only` 会调)。**Evolve 严格 append-only。**

**单轮上下文:与论文自己印的模板不一致 —— 而忠实版就躺在同一个仓库里当死代码。**
`remem.py:334-369` 的 `_build_single_turn_context` 给出的经验块是

```
[Memory {i+1}]
Question: {entry.input_text[:300]}...
Answer: {entry.output_text[:300]}...
Result: Success/Failure
```

只有 Question / Answer / Result 三个字段,**没有 rationale、没有 domain/skills**,
输出格式只要 `Final Answer:`(`remem.py:364-367`),**不要 Rationale**。
而论文 Appendix C 的单轮模板明写 "Each memory may contain past experience, rationales,
domains, and skills",这句连同 Rationale/Domain 字段和
"- Rationale: your short reasoning, may cite memory if useful / - Final Answer: your final answer"
的输出要求,**逐字存在于 `memory/context.py:290-299` 的 `SingleTurnContextBuilder` 里** ——
而这个类被**任何 agent 都不引用**(全仓 grep:只有它自己的定义处 `context.py:240`)。

后果链条:`remem.py:159-160` 把 reasoning trace 写进
`state.action_history[0].metadata["rationale"]`,`_build_single_turn_context` 从不读它;
唯一读 `entry.metadata["rationale"]` 的代码是死掉的 `SingleTurnContextBuilder`
(`context.py:278-279`)。**rationale 被记录了,但永远进不了 prompt。**

**三个被试共有的"死接口"**:ReMem 构造时装了 `StructuredContextBuilder`
(`remem.py:63`)并传给基类,但 `self.synthesize()` / `context_builder.build()`
在 ReMem 里一次都没被调用 —— 全仓只有 `exprag.py:104` 和 `amem.py:123,254` 调。
`prompts/templates.py` 里的 `REMEM_THINK_PROMPT` / `REMEM_REFINE_PROMPT` /
`MEMORY_MERGE_PROMPT` / `MEMORY_PRUNE_PROMPT` / `MULTITURN_REFLECT_PROMPT`
被 `evo_memory/` 内任何模块引用零次(只有 `prompts/__init__.py` 转出)。

**没接线的构造参数**:`enable_pruning` / `pruning_threshold`(`remem.py:76-77`)赋值后再无读取。

**LLM 调用次数**:每题 1..`max_iterations` 次(driver 传 `max_iterations=4`,
`evomem_driver.py:403-404`)。

### 1.3 差距判语

- **多轮:忠实。** prompt 模板、字段名、三格输出格式、Think/Refine/Act 循环终止条件,
  逐条对得上论文 Appendix C 与 §3.3。这是三个被试里唯一能说"照论文实现"的一个。
- **单轮:简化但方向一致。** 机制骨架(检索 top-k=4 bge → Think/Prune 循环 → 作答 → 写库)
  都在,差在**经验块少了 rationale / domain 字段,输出不要求 Rationale**。
  方向没反,但"ReMem 靠 rationale 迁移解法"这条通路在单轮上是断的,
  而论文单轮模板明确要 rationale。**这一条必须声明**,而且它是**可低成本修复的**:
  把 `ReMemAgent` 的 context_builder 换成库里现成的 `SingleTurnContextBuilder` 即可,
  那份代码就是论文模板的逐字复刻。
- **Refine 语义:不算失真,但要声明口径。** 重建版只剪当前 prompt 的检索段 ——
  这与论文 prompt 的字面要求("Remove ... from 'RELEVANT EXPERIENCE' section")一致,
  与论文 Appendix B.2 那句"discards domain-irrelevant experiences"读起来不一致。
  **论文自己没说清,我们照 prompt 字面实现,并在论文里注明取的是这一解读**,
  这是唯一诚实的做法。相应地要声明:**我们跑的 ReMem 记忆是 append-only 的**。
- **驱动侧 NOTES #6 的顾虑要下调一档。** 兄弟任务记的"ReMem 只带 Result: Success/Failure,
  不带反馈全文"其实**符合论文**:Appendix C 的经验块本来就只有 `Correctness: [success/failure]`,
  没有反馈散文这个字段。这不是失真,是原设计。真正的失真是丢了 rationale。

---

## 2. DynamicCheatsheet(DC-Cu / DC-RS)

### 2.1 原文机制(Suzgun et al., arXiv:2504.07952,v1 2025-04-10,仅此一版)

> "Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory"
> Mirac Suzgun, Mert Yuksekgonul, Federico Bianchi, Dan Jurafsky, James Zou
> —— <https://arxiv.org/abs/2504.07952>;官方 repo <https://github.com/suzgunmirac/dynamic-cheatsheet>

摘要里两句定调:

> "Crucially, DC's memory is self-curated, focusing on concise, transferable snippets rather than
> entire transcript."
> "This test-time learning enhances performance substantially across a range of tasks without
> needing explicit ground-truth labels or human feedback."
> —— <https://arxiv.org/abs/2504.07952>

**两模式的顺序差别(这是判别性机制)**,Figure 3 伪代码(HTML 版是 PNG,以下为读图转录,
已与官方 repo 代码逐字对照):

> "DC-Cu. (Cumulative) — 1: M₀ ← ∅ ▷ Memory initialization / 2: for i ∈ [1,…,n] do /
> 3: ỹᵢ = Gen(xᵢ, M_{i−1}) ▷ Solution generation / 4: Mᵢ = Cur(M_{i−1}, xᵢ, ỹᵢ) ▷ Memory curation"
> "DC-RS (Retrieval and Synthesis) — 1: M₀ ← ∅ ▷ Memory initialization / 2: for i ∈ [1,…,n] do /
> 3: Rᵢ = Retr(xᵢ, {(xⱼ, ỹⱼ)}_{j<i}, k) ▷ Retrieval / 4: Mᵢ = Cur(M_{i−1}, xᵢ, Rᵢ) ▷ Memory curation /
> 5: ỹᵢ = Gen(xᵢ, Mᵢ) ▷ Solution generation"
> —— <https://arxiv.org/html/2504.07952v1/x2.png>,Figure 3

论文自己点明这个顺序为什么重要:

> "DC-Cu has two potential drawbacks. First, it updates the memory after processing an input query,
> rather than refining it before generating a response. This means the model lacks the opportunity
> to incorporate new insights from the current query while reasoning through its solution. Second,
> DC-Cu does not store or revisit past input-output pairs unless explicitly retained in memory."
> —— <https://arxiv.org/html/2504.07952v1>,§2.2 开头

> "To address these issues, DC-RS modifies the sequence of memory updates and introduces a retrieval
> mechanism, Retr, into the curation process."(§2.2)

**curator 看到什么(任务书问的核心)**:

> "Cur does not have access to ground-truth labels; so, it has to assess the correctness and
> efficiency of the solutions by itself before updating the memory. In our experiments, we instruct
> a single model to perform this crucial step."
> —— <https://arxiv.org/html/2504.07952v1>,§2.1.2

DC-Cu 的 curator prompt 只有三个槽位(官方 repo 纯文本文件,字节级):

> ```
> ## PREVIOUS CHEATSHEET
> [[PREVIOUS_CHEATSHEET]]
> ## CURRENT INPUT
> [[QUESTION]]
> ## MODEL ANSWER TO THE CURRENT INPUT
> [[MODEL_ANSWER]]
> ```
> —— <https://raw.githubusercontent.com/suzgunmirac/dynamic-cheatsheet/main/prompts/curator_prompt_for_dc_cumulative.txt>

> "Before updating the cheatsheet, however, you should first assess the correctness of the provided
> solution and strategically incorporate code blocks, insights, and solutions into the new cheatsheet."
> —— 同上文件

DC-RS 的 curator 槽位不同(**不含当前题的模型输出** —— 此刻还没生成):

> ```
> ## PREVIOUS CHEATSHEET
> [[PREVIOUS_CHEATSHEET]]
> ## NOTES FOR CHEATSHEET
> [[PREVIOUS_INPUT_OUTPUT_PAIRS]]
> ## NEXT INPUT:
> [[NEXT_INPUT]]
> ```
> —— <https://arxiv.org/html/2504.07952v1/x9.png>(Figure 15,读图转录);字节级同文见
> <https://raw.githubusercontent.com/suzgunmirac/dynamic-cheatsheet/main/prompts/curator_prompt_for_dc_retrieval_synthesis.txt>

**所以任务书那个问题的答案是三段**:curator **含任务原文**、**含模型的完整解答**
(DC-Cu;DC-RS 里是检索到的历史 input-output 对)、**不含对错标签,对错由 curator 自己判**。
代码级佐证:`language_model.py:423` 只填三个槽位,全文 grep `ground_truth` / `label` /
`correct_answer` **零命中**
(<https://raw.githubusercontent.com/suzgunmirac/dynamic-cheatsheet/main/dynamic_cheatsheet/language_model.py>)。

**cheatsheet 是被整体重写的一份文档,不是 append-only 的列表** —— 这是最关键的一句:

> "N.B. Keep in mind that once the cheatsheet is updated, any previous content not directly included
> will be lost and cannot be retrieved. Therefore, make sure to explicitly copy any (or all) relevant
> information from the previous cheatsheet to the new cheatsheet!"
> —— <https://arxiv.org/html/2504.07952v1/x8.png>,Figure 14 末 N.B.;repo 同文

> "Selective Knowledge Retention: / - Preserve only high-value strategies, code blocks, insights, and
> reusable patterns that significantly contribute to problem-solving. / - Discard redundant, trivial,
> or highly problem-specific details that do not generalize well."(Figure 14)

> "During memory curation, Cur mainly considers: (i) the usefulness and generalizability of the newly
> produced answer ..., (ii) refinement or removal of existing memory entries (i.e., if an existing
> memory entry was incorrect or superseded by a more efficient or versatile strategy, Cur may remove
> or update it), and (iii) clarity and compactness of the entire memory ..."(§2.1.2)

**利用**:整块贴,软上限 ~2000–2500 词,generator 只看 cheatsheet:

> "CHEATSHEET: / ''' / [[CHEATSHEET]] / ''' ... Now it is time to solve the following question. /
> CURRENT INPUT: / ''' / [[QUESTION]] / '''"(Figure 13,读图转录;代码同构 `language_model.py:546`)

> "N.B. Make sure that all information related to the cheatsheet is wrapped inside the <cheatsheet>
> block. The cheatsheet can be as long as circa 2000-2500 words."(Figure 15;repo 同文)

条目**条数**上限:NOT FOUND(只有词数软上限);另有 usage counter:

> "4. Implement a Usage Counter / - Each entry must include a usage count: Increase the count every
> time a strategy is successfully used in problem-solving. / - Use the count to prioritize frequently
> used solutions over rarely applied ones."(Figure 14)

**DC-RS 的检索**:

> "DC-RS first retrieves[脚注1: We used OpenAI's text-embedding-3-small model to map input queries
> (raw questions) to embedding vectors.] top-k most similar inputs, along with their model-generated
> outputs, from previously seen examples ...[脚注2: We set k to 3 in all our experiments.]"(§2.2)

> "The retrieval mechanism ranks historical inputs based on cosine similarity with the current query,
> selecting the most relevant past examples along with their generated solutions."(Figure 3 caption)

关键对照基线,说明 "synthesis" 这一步的增量在哪:

> "(4) Dynamic Retrieval (DR). A final baseline uses retrieval but no curation. Specifically, for each
> new query, it retrieves the most similar past interactions and directly pastes them, verbatim, into
> the prompt. DR can help the model see relevant input-output pairs but not directly codify any
> abstract or generalized solutions."(§2.3)

初始状态空:SUPPORTED(`M₀ ← ∅`)。是否跨任务共享一份:**NOT FOUND**,论文没写。

命名核对:Evo-Memory 用的是 "two variants Cumulative (Cu) and Synthesis (RS)",
与重建版枚举 `CheatsheetMode.CUMULATIVE / SYNTHESIS` 一致;
INTEGRATION §2.1 写的 `RETRIEVAL_SYNTHESIS` 是错的(driver NOTES #3 已记)。

### 2.2 重建版实际行为

**cheatsheet 的数据结构:一个 Python list,元素是 `{"strategy": 一句话, "context": query[:100]}`**
(`dynamic_cheatsheet.py:78, 234-237`)。不是一份文档,没有 `<cheatsheet>` 块,没有分节,
没有 usage counter。

**写入:append-only + 精确字符串去重 + 滚动窗口。** `_add_strategy`
(`dynamic_cheatsheet.py:227-241`):

```python
for entry in self.cheatsheet:
    if strategy.lower() == entry["strategy"].lower():
        return                      # 只挡逐字重复
self.cheatsheet.append({...})
if len(self.cheatsheet) > self.max_cheatsheet_size * 2:      # 40
    self.cheatsheet = self.cheatsheet[-self.max_cheatsheet_size:]   # 砍到最近 20
```

**没有任何重写 / 合并 / 淘汰过时条目的动作** —— 原文 curator 的三条职责
(distill / refine-or-remove / consolidate)一条都没实现,只剩下"往后面加一句"。
过期或错误的策略永远留在库里,只会因为窗口滑动被挤掉,与"是否被更好的策略取代"无关。

**curator 看到什么:题目 200 字 + 抽取后的短答案 200 字,没有对错。**
`_extract_strategy`(`dynamic_cheatsheet.py:243-257`):

```python
prompt = f"""Extract a general strategy or rule from this Q&A that could help solve similar problems.

Question: {query[:200]}
Answer: {output[:200]}

Strategy (one sentence, general and reusable):"""
```

"不含对错"这一点**与原文一致**(原文 curator 也没有 ground truth)。
但 `output` 是什么很要命:它是 `self.extract_answer(response.content)`
(`dynamic_cheatsheet.py:110`)的返回值,而我们的 driver 用 `attach_extractor`
(`evomem_driver.py:417-429`)把这个钩子替换成了只抽 `Final Answer:` 后面那截。
所以在我们的 2Wiki QA 上,curator 实际看到的 `Answer:` 是 **"Italy"** 这种一两个词,
不是模型的推理过程。原文喂给 curator 的是 `[[MODEL_ANSWER]]` = generator 的**完整输出**,
DC 的整个卖点("distill code snippets and insights into transferable snippets")就建立在这上面。
**这是本次审查发现的 DC 最严重的失真。**

另外,还有一个原文**没有**的信息通道:`_build_context`(`dynamic_cheatsheet.py:295-297`)
在 cheatsheet 之外又贴了一段 "Past Examples",内容是

```python
exp_str = "\n".join([f"- {r.entry.output_text[:100]}..." for r in retrieved[:3]])
```

即 bge 检索到的过去条目的**裸答案前 100 字**,既无问题也无对错。原文的 generator
只看 cheatsheet(DC-RS 的检索结果是喂 curator 的,不是喂 generator 的)。
driver NOTES #6 记的就是这条。要注意:**这里"加上对错"并不是向原文靠拢** ——
原文这条通路根本不存在。向原文靠拢的做法是**把它删掉**,并让 curator 看到完整解答。

**DC-Cu 的顺序:对。** `run_single_turn` 是 取 cheatsheet(99)→ 生成(109)→ 抽策略(113)→
加库(115),对应 `ỹᵢ = Gen(xᵢ, M_{i−1})` 然后 `Mᵢ = Cur(M_{i−1}, xᵢ, ỹᵢ)`。

**DC-RS 的顺序:错,判别性机制整个缺失。** `run_single_turn` 里 DC-RS 与 DC-Cu 走的是
**同一条写入路径**(都是 113-115 行的先答后抽),唯一区别在读:
`self.mode == SYNTHESIS` 时走 `_retrieve_strategies` 而不是 `_get_cumulative_strategies`
(`dynamic_cheatsheet.py:96-99`)。原文 DC-RS 的核心 —— **在作答之前先检索、先让 curator
重写 cheatsheet,generator 再看这份新鲜 cheatsheet**(`Mᵢ = Cur(M_{i−1}, xᵢ, Rᵢ)`
排在 `ỹᵢ = Gen(xᵢ, Mᵢ)` 之前)—— 在重建版里不存在。重建版的 DC-RS 只是"换了个检索器的 DC-Cu"。

**DC-RS 的检索器:从 embedding 退化成词袋。** `_retrieve_strategies`
(`dynamic_cheatsheet.py:203-221`):

```python
query_words = set(query.lower().split())
...
overlap = len(query_words & (strategy_words | context_words))
if overlap > 0: scored.append(...)
scored.sort(...); return [s for s, _ in scored[:self.synthesis_top_k]]   # top-5
```

原文是 `text-embedding-3-small` 余弦相似度 top-3,检索对象是**过去的 input-output 对**;
重建版是**未去停用词的词集交集**大小,检索对象是**策略句**,top-5。
未去停用词意味着几乎任何 query 与任何策略句都有非零 overlap(the / to / a / of),
排序信号基本被停用词噪声占满 —— **DC-RS 的"检索"在我们的数据上接近任意取 5 条**。
注意重建版明明接收了 `retriever`(bge)并且在 `state.retrieved` 那条通路上用了它
(`dynamic_cheatsheet.py:103`),偏偏 cheatsheet 检索不用 —— Evo-Memory 声称的
"same retrieval configuration ... across all methods"(Appendix A.2)在这里被破坏了。

**初始状态空**:`self.cheatsheet = []`(`dynamic_cheatsheet.py:78`),与原文 `M₀ ← ∅` 一致。

**规模不匹配**:`max_cheatsheet_size=20`(`dynamic_cheatsheet.py:45`),每条是一句话
(`_extract_strategy` 限 `10 < len < 200` 字符,`dynamic_cheatsheet.py:255`)→
整个 cheatsheet 上限约 20 句、几百词;原文软上限 2000–2500 词、含代码块。
在 50 题切片上,DC-Cu 的窗口到第 20 题才填满,之后开始丢最早的策略。

**多轮路径的额外差别**:多轮只在 `success` 时抽策略(`dynamic_cheatsheet.py:187-190`),
单轮**每题都抽**(113 行,无条件)。原文两边都是每题都策展。

**死接口**:构造了 `CheatsheetContextBuilder`(`dynamic_cheatsheet.py:61`)但从不调用 ——
`self.synthesize()` 在 DC 里零次调用,`CheatsheetContextBuilder.cheatsheet` 这个 list
永远是空的,它那个 `synthesize_cheatsheet(llm_synthesize_fn)`(`context.py:326-336`,
唯一一处试图用 LLM 做 synthesis 的代码)是死代码。

**不吃 system_prompt**:`self.llm.generate(prompt=context)`(`dynamic_cheatsheet.py:109`)
不传 system prompt,格式约束只能靠 query 里那行(driver `query_style=instructed`,
`evomem_driver.py:219-234`)。

**LLM 调用次数:每题 2 次**(作答 1 次 + 抽策略 1 次)。ReMem 1–4 次、AWM 1 次。
报 token / 延迟时不能忽略这个差别。

### 2.3 差距判语

- **DC-Cu:失真需声明。** 顺序对、初始态对、"无 ground truth"对,但记忆的**形态**变了 ——
  从"被 curator 整体重写、会删会并会压缩的一份 ~2000 词文档"退化成
  "append-only 的一句话列表 + 滚动窗口"。原文 §2.1.2 列的 curator 三条职责
  (distill / refine-or-remove / consolidate)只剩第一条的极简版。
  再叠上 curator 只看到抽取后的短答案,DC 的核心机制
  ("从完整解答里蒸馏可迁移片段与代码")在我们的跑分里基本不发生。
  **它测出来的东西更接近"自动生成的一句话提示池",不是 Dynamic Cheatsheet。**
- **DC-RS:失真需声明,且是机制缺失级。** 原文用整节篇幅论证 DC-RS 相对 DC-Cu 的增量
  就是"先检索+先策展再作答";重建版把这个顺序改回了 DC-Cu 的顺序,
  只保留了一个词袋检索器当读取过滤。**跑出来的 DC-RS vs DC-Cu 的差异,
  测的是"读 20 条 vs 读词袋 top-5",不是论文里那个 DC-RS。**
  这一格如果要进论文表格,必须写清"我们的 DC-RS 只保留了检索侧变体"。
- **一条把顾虑下调的话**:driver NOTES #6 担心"DC/AWM 的上下文既无问题也无对错"。
  就 DC 而言,**"无对错"是原设计,不是 bug**(原文 curator 也自己判对错);
  真问题是(a)curator 只看到短答案而非完整解答,(b)多出了一条原文没有的
  "裸答案 Past Examples"通路。修的方向是"给 curator 完整输出 + 删掉 Past Examples",
  不是"加对错标签"。

---

## 3. AWM(Agent Workflow Memory)

### 3.1 原文机制(arXiv:2409.07429,v1 2024-09-11,仅此一版)

> "Agent Workflow Memory"
> Zora Zhiruo Wang, Jiayuan Mao, Daniel Fried, Graham Neubig
> —— <https://arxiv.org/abs/2409.07429>;官方 repo <https://github.com/zorazrw/agent-workflow-memory>(Apache-2.0)

**workflow 是什么**(§2.2):

> "Similar to an experience, a workflow comprises two components: first, a textual description of
> the workflow d; and second, a series of steps to finish the workflow (p1,p2,⋯), as shown in Figure 2."

> "The workflow trajectory contains a series of steps (p1,p2,⋯) to finish the process described in d.
> Each p consists of three parts, demonstrated in pn in Figure 2, Step 3. (1) A description of the
> current environment state in NL, such as "Order {id} is shown"; (2) The reasoning process elaborated
> by the agent to decide which action to generate based on observations, such as "Order {id} is found,
> I will now terminate the task."; and (3) an action represented as an executable program over the
> environment, i.e., stop() that realizes termination."
> —— <https://arxiv.org/html/2409.07429v1>,§2.2

逐字例子(§A.2,WebArena):

> ```
> ## shopping: Browse Products in a Specific Category
> To browse products in a specific category, I need to navigate to the relevant main category. I will start by hovering over the main category menu item to reveal the subcategories.
> hover('main_category_id')
> To browse products in the specific subcategory, I need to click on the subcategory link.
> click('subcategory_id')
> ```

Mind2Web 侧带变量占位:

> ```
> # travel: enter_flight_locations
> Given that you are on the flight booking page, this workflow enters the departure and destination city/airport for your flight.
> [link] From Departure Airport or City Your Origin -> CLICK
> [textbox] Origin City or Airport -> TYPE: {your-origin-city}
> [link] {best-popup-option} -> CLICK
> ```

**抽取(induction)**:LM 从**多条经验拼在一起**的 prompt 里找**跨任务重复的子例程**,
粒度是子任务而非整条轨迹,并把具体值抽象成变量:

> "To produce workflows that more accurately capture reusable trajectories across tasks, we propose
> an LM-based module I that prompts the agent to extract common sub-routines from one or more input
> experiences."(§2.3)

> "Different from task instructions that specify concrete, less-repetitive tasks, e.g., "Buy dry cat
> food on Amazon and deliver to my address", we deliberately prompt models to induce workflows at
> finer granularities, i.e., a sub-task "search for a product on Amazon" that frequently re-appears
> as part of multiple similar instructions."(§2.3)

> "Meanwhile, instead of giving example-specific values (e.g., "dry cat food"), we enhance workflow
> generality by abstracting out example-specific contexts, i.e., replacing "dry cat food" with a more
> general name "{product-name}" by specifying this in the workflow induction prompts."(§2.3)

> "These workflows are segmented (based on double-line breaks in the model output) and stored
> separately in the workflow memory."(§2.3)

induction prompt(§A.1,论文自称 "the exact prompt"):

> "Given a list of web navigation tasks, your task is to extract the common workflows."
> "Each given task contains a natural language instruction, and a series of actions to solve the task.
> You need to find the repetitive subset of actions across multiple tasks, and extract each of them
> out as a workflow."
> "Each workflow should be a commonly reused sub-routine of the tasks. Do not generate similar or
> overlapping workflows. Each workflow should have at least two steps. Represent the non-fixed
> elements (input text, button strings) with descriptive variable names as shown in the example."

**offline / online**:

> "As seen in Figure 3, AWM first takes in all training examples from a website by concatenating them
> into a single prompt, and feeds them to the LM to create a set of workflows at 'training' time;
> I(E_train) → W_offline."(§2.3 Offline)

> "We adopt the LM-based evaluation model of Pan et al. (2024) to output a binary label,
> L_eval(e^t) ∈ {0,1}, that judges if e^t successfully solves q^t by prompting a neural model. If e^t
> is predicted as success, i.e., 1, we then transform it into workflow(s) I(e^t) → {w^t} and add {w^t}
> into the agent memory M^t + {w^t} → M^{t+1}"(§2.3 Online)

**复用:全部贴进去,不做 per-query 检索**:

> "Second, AWM incorporates all induced workflows into the agent memory at inference time to solve
> test instructions L(q, M + W_offline, o_i^test) → a_i^test."(§2.3 Offline)

> "For both benchmarks, we conduct AWM on a website basis. In other words, we group examples by their
> associated websites, and respectively run AWM on each group. This mechanism maintains an small
> collection of workflows that are nonetheless relevent to the test tasks."(§3,原文拼写如此)

规模上不需要检索的原因:

> "As shown in Table 10, neural-based induction produces 7.3–7.4 workflows per example, which is
> efficient and do not add too much content to the memory."(§A.3)

替换 few-shot 示例:

> "We integrate the element filtering adopted in both methods, and added workflows instead of
> retrieved examples in Synapse, to verify the superiority of reusable workflows over concrete
> examples."(§3.2)

**主结论**:

> "We experiment on two major web navigation benchmarks — Mind2Web and WebArena — that collectively
> cover 1000+ tasks from 200+ domains ... AWM substantially improves the baseline results by 24.6%
> and 51.1% relative success rate on Mind2Web and WebArena while reducing the number of steps taken
> to solve WebArena tasks successfully."
> —— <https://arxiv.org/abs/2409.07429>,abstract

论文自认的边界(对我们判语有用):

> "Despite more accurate element selection, AWM gets slightly lower action F1 scores than MindAct,
> possibly because the augmented workflows may guide the agent to take certain actions aligning to
> the workflows, which are not always relevant to the particular environment state at hand. While
> following the workflows generally results in more successful task trajectories, agents still
> encounter some challenges in identifying places to diverge from the workflow guidelines."(§3.2.1)

未核实项:induction prompt 结尾 "as shown in the example" 提到的那个 few-shot 例子
论文没印出来(需查 repo);workflow 在 prompt 里的确切位置只有一句脚注
"Memory is usually implemented as a system prompt or auxiliary information in the main prompt
context"(§2.1 footnote 1),AWM 实验走哪一路 NOT FOUND。

### 3.2 重建版实际行为

**最要紧的一条:单轮任务上 AWM 从不抽 workflow。**
`_extract_workflow` 唯一的调用点在 `run_multi_turn`(`awm.py:250-253`,
`if success and len(state.action_history) >= self.min_workflow_steps`)。
`run_single_turn`(`awm.py:140-179`)只调 `workflow_library.search(query, top_k=2)`
(`awm.py:156`)去**读**,从不**写**。所以在我们的 2Wiki 单轮切片上:

- `WorkflowLibrary.workflows` 永远是空 dict;
- `search` 第 61-62 行 `if not self.workflows: return []` 直接返回空;
- `_build_context`(`awm.py:322-342`)只剩下 "Past Examples" 那一段,内容是
  `r.entry.output_text[:100]`(`awm.py:336`)—— bge 检索到的过去条目的裸答案前 100 字。

**结论:单轮 AWM = 一个上下文比 ExpRAG 更弱的检索基线**(ExpRAG 走
`SimpleContextBuilder`,贴 `entry.to_text()` 全文含 Task/Output/Feedback/Result;
AWM 只贴 100 字裸答案)。**它跑出来的分数不含任何 AWM 机制**,
把它列进表格当 "AWM" 一格是不能接受的。

**多轮路径的 workflow 形态**:`_extract_workflow`(`awm.py:276-320`)

```python
actions = [a.content for a in action_history if a.action_type == ActionType.ACT][:10]
prompt = f"""Create a reusable workflow from this successful task.
Goal: {goal}
Actions taken: {' -> '.join(actions)}
Provide:
Name: [short descriptive name]
Description: [one sentence description]"""
```

即 **LLM 只负责起名字和写一句描述,steps 直接就是这一条 episode 的原始动作串**
(`awm.py:316` `steps=actions`)。对比原文的三处硬性要求:

| 原文 | 重建版 |
|---|---|
| 每步含"环境状态描述 + agent 推理 + 可执行动作"三部分 | 只有裸动作字符串 |
| 从**多条**经验里挖**跨任务重复的子例程** | 从**单条** episode 整体造一个 workflow |
| 把具体值换成变量(`{product-name}`) | 无任何抽象化,具体物件名原样留着 |
| 一条经验产出 ~7 个子例程,按 double-line-break 切分 | 一条 episode 产出恰好 1 个 workflow |
| 去重靠 prompt 里 "Do not generate similar or overlapping workflows" | md5(goal+actions) 当 id(`awm.py:310`),只挡完全相同的重复 |

**复用方式相反**:原文"全部贴,不检索"(靠按网站分组把库控制在 ~7 条);
重建版是 `WorkflowLibrary.search` 做**词袋 top-k**(`awm.py:59-80`):

```python
goal_words = set(goal.lower().split())
overlap = len(goal_words & (desc_words | name_words | applicable_words))
score = overlap * (1 + workflow.success_rate)
```

未去停用词,单轮 top-2 / 多轮 top-3。和 DC-RS 一样,注入的 bge `retriever` 在这条通路上不用。

**多出来的机制**:`_get_workflow_guidance(step_idx)`(`awm.py:266-274`)把
`current_workflow.steps[step_idx]` 当 "Suggested Next Step" 直接贴进 prompt
(`awm.py:363-364`)—— 即**按下标逐步复读某一条历史 episode 的第 k 个动作**。
原文没有这个机制:原文把 workflow 当可读的参考资料放进 memory,由 agent 自己决定用不用,
而且论文专门用一小节讲 agent 需要"identify places to diverge from the workflow guidelines"。
重建版这个 index-aligned 复读是**比原文更强的硬约束**,方向相反。

**库的淘汰策略也是原文没有的**:`WorkflowLibrary.add`(`awm.py:47-57`)满 50 条时按
`success_rate * usage_count` 最小的踢掉。原文没有容量上限或淘汰机制。

**offline / online**:重建版只有 online 一路(边跑边从自己的成功轨迹里抽),
没有 offline(预先从训练集抽一批 workflow)。这一路对得上原文的 online 设定,
但原文 online 用一个 LM evaluator 打成功标签,重建版用环境返回的
`info["success"]`(`awm.py:242`)—— 在有真 reward 的 ALFWorld 上这是**更强**的信号,
要声明。

**死接口**:构造了 `SimpleContextBuilder`(`awm.py:125`)但 `self.synthesize()` 零调用。

**LLM 调用次数**:单轮每题 1 次;多轮每步 1 次 + 成功后 1 次抽 workflow。

### 3.3 差距判语

- **单轮(我们的 2Wiki L3 切片):机制完全缺失,不能当 AWM 报。**
  workflow induction 在单轮路径里一次都不触发,库恒空,被试退化为
  "bge top-k 检索 + 只看过去 100 字裸答案"的弱化 ExpRAG。
  两条出路,必须选一条并写进论文:
  (a) **不在单轮任务上报 AWM**(最干净,也符合原文 —— AWM 只在 web navigation 上验过,
      原文从没在单轮 QA 上跑过);
  (b) 自己补一个单轮 induction(把 rationale 抽成 workflow),但那是**我们发明的变体**,
      得改名(如 "AWM-single, our adaptation"),不能叫 AWM。
  我的建议是 (a)。
- **多轮(ALFWorld):失真需声明。** 骨架方向一致(从成功轨迹抽可复用流程、下次贴进 prompt),
  但三处关键失真:workflow 是**单条 episode 的裸动作串**而非跨任务子例程、
  **没有变量抽象**、复用从"全贴"改成"词袋 top-k";再加一处**方向相反**的多出机制
  (按下标硬提示下一动作)。合起来测出来的更像"逐字复读最相似的一条历史 episode",
  而不是 AWM 的"抽象子例程复用"。
- **driver NOTES #6 对 AWM 的记录要升级措辞。** 那条写的是"上下文只塞
  `output_text[:100]`,退化成一串裸答案"。**在单轮上这不是上下文构造的小问题,
  而是整个被试机制不存在** —— 因为 workflow 段本来就永远是空的,
  剩下的裸答案段就是它的全部。

---

## 4. 三个被试共有的四个结构性问题

这四条不属于任何单个被试,但会同时影响三格,写论文时要一次性交代:

1. **`context_builder` 是死接口。** 基类的 `synthesize()`/`ContextBuilder.build()`
   全仓只被 `exprag.py:104` 与 `amem.py:123,254` 调用。ReMem / DC / AWM 三个都在
   构造函数里装了 builder(`remem.py:63`、`dynamic_cheatsheet.py:61`、`awm.py:125`)
   然后**自己用私有 `_build_*_context` 内联拼 prompt**。
   讽刺的是,`memory/context.py` 里那三个 builder 恰恰是**离论文最近的版本** ——
   `SingleTurnContextBuilder`(`context.py:240-301`)是 Evo-Memory Appendix C 单轮模板的
   逐字复刻,而它**没有任何引用者**。所以"重建版不如论文"和"仓库里有更忠实的代码"
   这两件事同时成立。

2. **`prompts/templates.py` 全是死代码。** `REMEM_THINK_PROMPT` / `REMEM_REFINE_PROMPT` /
   `MEMORY_SUMMARIZE_PROMPT` / `MEMORY_MERGE_PROMPT` / `MEMORY_PRUNE_PROMPT` /
   `MULTITURN_REFLECT_PROMPT` 被 `evo_memory/` 内任何模块引用**零次**
   (只有 `prompts/__init__.py` 把它们转出)。也就是说库里"看起来有"的反思、
   摘要、合并、剪枝能力,一条都没接线。

3. **Evolve 严格 append-only,没有任何被试会删改持久记忆。**
   `Memory.remove` / `remove_by_ids` / `prune_by_relevance`
   (`memory/base.py:198, 212, 220`)在 `evo_memory/` 内**零调用者**;
   `_prune_oldest` 只在 `max_size=1000` 撑满时触发(50 题跑分永远不会)。
   这直接限定了三个被试能表现出的"记忆演化"上限:只有加,没有编辑。

4. **检索器不统一,破坏了 Evo-Memory 声称的公平性。**
   Evo-Memory Appendix A.2 说 "This setting ensures a consistent retrieval budget across
   all methods";但重建版里 DC-RS 的策略检索(`dynamic_cheatsheet.py:209-216`)与
   AWM 的 workflow 检索(`awm.py:64-73`)都是**未去停用词的词袋交集**,
   完全绕过注入的 bge retriever(bge 只用在 `state.retrieved` 那条通路上)。
   在英文 QA 上停用词会主导 overlap,这两处检索的有效信号非常弱。
   另外 `RecencyRetriever` 的排序是反的(`retriever.py:283-288`:
   `get_recent(k)` 返回 `_entries[-k:]` 后按下标给 rank,rank 1 落在窗口里**最旧**那条),
   影响 ExpRecent 而非本文三个被试,但同一段声明里一起交代更省事(driver NOTES #4 已记)。

**每题 LLM 调用次数差异**(报 token/延迟必须说):
ReMem 1–4 次(`max_iterations=4`)、DC-Cu/DC-RS 各 2 次(作答 + 抽策略)、AWM 单轮 1 次、
ExpRAG/ExpRecent 1 次。

---

## 5. 论文里怎么措辞

沿用已定的调子:**不说"采用官方实现",只说"参照 Evo-Memory 的统一接口"**。
下面是可直接改写进 Experimental Setup / Appendix 的骨架与必须声明的清单。

### 5.1 定位句(建议写法)

> We compare against memory-augmented agents following the unified (F, U, R, C) interface and the
> search–synthesize–evolve protocol of Evo-Memory (Wei et al., 2025). Because no official
> implementation of that framework was available at the time of writing, we build on a public
> reconstruction of its agent and memory modules and drive it with our own task loop, scoring, and
> feedback pipeline. The reconstruction reproduces Evo-Memory's published prompt templates for
> multi-turn tasks verbatim, but it re-implements the two external procedural-memory baselines
> (Dynamic Cheatsheet and AWM) from the one-line descriptions given in Evo-Memory rather than from
> their original papers. We therefore treat these two as *simplified variants* and report them as
> such; the simplifications are enumerated below.

要点:
- ReMem 归到 Evo-Memory 这篇 cite(**不能**当独立论文引);
- DC 引 Suzgun et al. 2025 (arXiv:2504.07952),AWM 引 Wang et al. 2024 (arXiv:2409.07429),
  但**必须加 "simplified variant / our re-implementation" 的限定词**;
- "官方实现不可得"这句要留退路:Evo-Memory 只说 "will release all code",
  截至本次核实无 URL(§1.1)。投稿前重查一次,若已放出应优先换官方。

### 5.2 必须声明的简化点(按被试)

**ReMem —— 标"忠实/轻度简化",两条声明:**
1. Refine 操作按论文 prompt 的字面语义实现:只从当前 prompt 的
   "RELEVANT EXPERIENCE" 段剔除条目,**不删持久记忆库**;因此我们跑的记忆是 append-only。
   (论文正文对此措辞不一致,我们取 prompt 字面解读。)
2. 单轮经验块只含 Question / Answer / Correctness,**不含论文单轮模板里的
   rationale / domain / skills 字段**,输出也不要求 Rationale。
   → **这一条建议直接修掉再跑**:把 `ReMemAgent` 的单轮上下文换成库里现成的
   `SingleTurnContextBuilder`,它就是论文模板的逐字复刻。修掉之后这条声明可以删。

**DC-Cu —— 标"简化变体",三条声明:**
1. 记忆是**一句话策略的 append-only 列表 + 最近 20 条滚动窗口**,
   不是原文那份被 curator 每轮整体重写的 ~2000 词文档;
   原文的 refine-or-remove 与 consolidate 两项职责未实现。
2. curator 看到的是**题目(截 200 字)+ 抽取后的最终答案(截 200 字)**,
   不是原文的 generator 完整输出;**与原文一致的是都不给 ground-truth 标签**,
   对错由模型自评。
3. generator 侧额外贴了一段检索到的历史裸答案(每条 100 字),
   这条通路原文没有;**保留它就要声明,删掉它才更接近原文**。

**DC-RS —— 标"仅保留检索侧变体",两条声明(最重的一格):**
1. 原文 DC-RS 的判别性机制是"**先检索 → 先由 curator 重写 cheatsheet → 再作答**"
   (`Mᵢ = Cur(M_{i−1}, xᵢ, Rᵢ)` 排在 `ỹᵢ = Gen(xᵢ, Mᵢ)` 之前);
   我们的实现沿用 DC-Cu 的"先答后抽"顺序,**这个机制未实现**。
   我们的 DC-RS 与 DC-Cu 只在**读取侧过滤**上不同。
2. 检索用**词袋交集 top-5**(检索对象是策略句),
   不是原文的 `text-embedding-3-small` 余弦 top-3(检索对象是历史 input-output 对)。

**AWM —— 分任务类型分别处理:**
1. **单轮任务:建议整格不报。** 单轮路径不触发 workflow induction,
   库恒空,被试等价于一个弱化的检索基线。若审稿人问起就直说:
   AWM 原文只在 web navigation 上验证,没有单轮 QA 设定。
   若坚持要报,必须改名为我们自己的变体并说明 induction 是我们补的。
2. **多轮任务:标"简化变体",四条声明:**
   (a) workflow 的 steps 是**单条成功 episode 的裸动作串**,
       没有原文要求的"环境状态描述 + 推理 + 可执行动作"三段结构;
   (b) **不做跨任务子例程挖掘**(原文从拼接的多条经验里挖重复子例程,
       一条经验产出 ~7 个),我们一条 episode 产出 1 个 workflow;
   (c) **不做变量抽象**(原文把具体值换成 `{product-name}` 之类占位符);
   (d) 复用方式是**词袋 top-k 检索**而非原文的"全部注入";
       并且我们额外加了一个原文没有的 index-aligned "Suggested Next Step" 提示,
       它比原文的软参考更硬 —— 这一条尤其要声明,因为它可能同时抬高
       "重复任务变快"和压低"需要偏离历史路径时的成功率"。

**跨被试的四条通用声明**(放 Appendix 一段即可,内容见 §4):
context_builder 死接口(库里更忠实的模板未被使用)、
反思/合并/剪枝 prompt 全未接线、
所有被试的 Evolve 都是 append-only(无记忆编辑)、
DC-RS 与 AWM 的检索绕过统一 embedding retriever 改用词袋
(顺带交代 `RecencyRetriever` 排序反向对 ExpRecent 的影响)。
再加一句每题 LLM 调用次数不等(ReMem 1–4 / DC 2 / 其余 1),
说明 token 与延迟对比里已计入这一差异。

### 5.3 一句话给自己的行动建议

跑分前建议只做**两处**低成本修改,能把两条最难看的声明变没:
① ReMem 单轮换用库里现成的 `SingleTurnContextBuilder`(论文模板逐字版);
② AWM 单轮那一格**不跑**。
剩下的失真都写进声明,不动库代码 —— 因为一改就不再是"参照公开重建实现",
需要重新交代我们改了什么,得不偿失。

---

## 附:引用的一手来源

- Evo-Memory(ReMem 出处):<https://arxiv.org/abs/2511.20857> ·
  <https://arxiv.org/html/2511.20857v2> · <https://arxiv.org/pdf/2511.20857v1>
- Dynamic Cheatsheet:<https://arxiv.org/abs/2504.07952> ·
  <https://arxiv.org/html/2504.07952v1> ·
  Figure 13/14/15 为 PNG,已读图转录并与官方 repo 纯文本 prompt 逐字对照:
  <https://arxiv.org/html/2504.07952v1/x2.png> · <https://arxiv.org/html/2504.07952v1/x7.png> ·
  <https://arxiv.org/html/2504.07952v1/x8.png> · <https://arxiv.org/html/2504.07952v1/x9.png> ·
  <https://github.com/suzgunmirac/dynamic-cheatsheet>
  (`prompts/curator_prompt_for_dc_cumulative.txt`、
  `prompts/curator_prompt_for_dc_retrieval_synthesis.txt`、
  `dynamic_cheatsheet/language_model.py`)
- AWM:<https://arxiv.org/abs/2409.07429> · <https://arxiv.org/html/2409.07429v1> ·
  <https://github.com/zorazrw/agent-workflow-memory>
- 排除的同名干扰项:<https://arxiv.org/abs/2602.13530>(REMem, Shu et al. 2026,不同论文)·
  <https://arxiv.org/abs/2506.23041>(ReMem, ViT 蒸馏,无关)

**引用注意**:DC 的 prompt 模板在 arXiv HTML 版里是图片,本文件的 prompt 引文经读图转录
并与官方 repo 的纯文本文件逐字对照过(两处一致)。若要在论文里引 prompt 原文,
**引用对象写 repo 文件**,或自己开 PDF 复核 Figure 14/15。

**已知未核实项**(不许当结论用):Evo-Memory 主设置是否只存成功经验(NOT FOUND);
Evo-Memory 的 Think-Prune 是否真删持久库(论文自相矛盾,无法定论);
Evo-Memory 官方代码是否已发布(截至本次核实无 URL);
DC 是否跨 benchmark 共享一份 cheatsheet(论文没写);
DC 的 memory 条数上限(只有 ~2000–2500 词软上限);
AWM induction prompt 里那个未印出的 few-shot 例子;
AWM 的 workflow 在 prompt 里的确切插入位置(只有一句 "usually ... system prompt or
auxiliary information" 的脚注)。
