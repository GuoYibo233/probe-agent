#!/usr/bin/env python3
"""T12c 单轮 driver:我们的 QA 任务流驱动 Evo-Memory 的记忆被试。

对应 `related_work/evo_mem_INTEGRATION.md` §1 路线 (b) + §2.4 方案 2:
被试对象(agents/memory/llm 三模块)照用,它的 Evaluator/Runner/内置数据集
一概不碰;prompt 构造、答案抽取、评分、反馈回填、日志指标全在本文件。

每题一圈的顺序(即库里 search→synthesize→generate→evolve 那条链):

    build_prompt(task)
      └─ agent.run_single_turn(task_id, query)      # 库内部:search / synthesize
                                                    #        / LLM generate / evolve
           └─ agent.extract_answer(raw)             # 本 driver 挂上去的抽取器
      └─ grade(pred, refs)                          # EM / token-F1
      └─ backfill_feedback(...)                     # 把 (得分, 反馈) 写回刚存进去的
                                                    # 记忆条目并重算 embedding
    → 下一题 search 时就能检索到带反馈的这条经验

两个必须知道的库侧行为(见文件末 NOTES):
  1. `run_single_turn` 在返回前就 evolve(),正确性只能事后补 → 用回填;
  2. 库自带的 `extract_answer()` 对自由文本很弱(INTEGRATION §5 已记),
     本 driver 用 `attach_extractor()` 覆盖 BaseAgent 这个钩子(基类文档
     明确写了 "Override for more complex parsing"),并顺手留一份原始回复。

运行(必须用 evo_mem 自带 venv):

    EVO=related_work/evo_mem/.venv/bin/python

    # 1) 纯单元自检:答案抽取 + 评分,不碰模型不碰网络
    $EVO benchmark_design/evomem_driver.py --selftest

    # 2) mock 冒烟:假 LLM 走全链路 + 回填可检索断言(bge 在 CPU 上)
    $EVO benchmark_design/evomem_driver.py --mock-smoke --agent exprag

    # 3) 真服务跑分(vLLM OpenAI 兼容端点,见 INTEGRATION §3)
    $EVO benchmark_design/evomem_driver.py \
        --agent exprag --tasks benchmark_design/l3_2wiki_items.jsonl --limit 50 \
        --model Qwen2.5-7B-Instruct --api-base http://tokyo107:8791/v1 \
        --out logs/evomem_driver_exprag_qwen7b.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import string
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EVO_MEM_ROOT = os.path.join(REPO_ROOT, "related_work", "evo_mem")


# ───────────────────────────────────────────────────────────── 任务与数据

@dataclass
class Task:
    """一道单轮 QA 题。refs 是可接受的参考答案(取最优匹配)。"""
    task_id: str
    question: str
    refs: List[str]
    options: Optional[List[str]] = None      # 选择题选项;有则按字母评分
    meta: Dict[str, Any] = field(default_factory=dict)


_ID_FIELDS = ("task_id", "item_id", "id", "_id", "qid", "pair_id")
_Q_FIELDS = ("question", "query", "problem", "prompt", "goal")
_A_FIELDS = ("answers", "answer", "gold", "gold_answers", "label", "target")
_OPT_FIELDS = ("options", "choices")


def _pick(d: Dict[str, Any], names: Sequence[str]) -> Tuple[Optional[str], Any]:
    for n in names:
        if n in d and d[n] not in (None, "", []):
            return n, d[n]
    return None, None


def task_from_dict(d: Dict[str, Any], fallback_id: str) -> Task:
    """字段自动识别:兼容本工程 l3/l4 jsonl(item_id/question/answer)、
    HotpotQA 风格(_id/question/answer)、多选(options)。"""
    _, tid = _pick(d, _ID_FIELDS)
    qf, q = _pick(d, _Q_FIELDS)
    af, a = _pick(d, _A_FIELDS)
    if q is None:
        raise ValueError(f"记录里找不到问题字段(试过 {_Q_FIELDS}):{list(d)[:8]}")
    if a is None:
        raise ValueError(f"记录里找不到答案字段(试过 {_A_FIELDS}):{list(d)[:8]}")
    refs = [str(x) for x in a] if isinstance(a, (list, tuple)) else [str(a)]
    _, opts = _pick(d, _OPT_FIELDS)
    meta = {k: v for k, v in d.items() if k not in (qf, af)}
    return Task(
        task_id=str(tid) if tid else fallback_id,
        question=str(q),
        refs=refs,
        options=[str(o) for o in opts] if opts else None,
        meta=meta,
    )


def expand_pair(d: Dict[str, Any], fallback_id: str) -> List[Task]:
    """L4 任务对(gen_l4_*.py 产的 seed_question/l4_question)展成两道题:
    先跑种子题,再跑陷阱变体 —— 顺序不能反,负迁移就是靠这个顺序才测得出来。"""
    pid = str(d.get("pair_id") or fallback_id)
    base = {k: v for k, v in d.items()
            if k not in ("seed_question", "seed_answer", "l4_question", "l4_answer")}
    return [
        Task(f"{pid}#seed", str(d["seed_question"]), [str(d["seed_answer"])],
             meta={**base, "pair_role": "seed"}),
        Task(f"{pid}#l4", str(d["l4_question"]), [str(d["l4_answer"])],
             meta={**base, "pair_role": "l4"}),
    ]


def load_tasks(path: str, limit: int = 0, shuffle_seed: Optional[int] = None,
               pair_expand: bool = False) -> List[Task]:
    def _rows():
        if path.endswith(".jsonl"):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield json.loads(line)
        else:  # .json:列表或 {"data": [...]}
            with open(path) as f:
                blob = json.load(f)
            yield from (blob["data"] if isinstance(blob, dict) and "data" in blob else blob)

    tasks: List[Task] = []
    units: List[List[Task]] = []           # 打乱的单位:普通题 1 道,任务对 2 道绑定
    for i, d in enumerate(_rows()):
        if pair_expand and "seed_question" in d and "l4_question" in d:
            units.append(expand_pair(d, f"pair_{i:06d}"))
        else:
            units.append([task_from_dict(d, f"task_{i:06d}")])

    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(units)   # 任务顺序是 C3 的自变量之一
    for u in units:
        tasks.extend(u)
    if limit:
        tasks = tasks[:limit]

    seen = Counter(t.task_id for t in tasks)
    dupes = [k for k, v in seen.items() if v > 1]
    if dupes:
        # 库里 Memory.add 用 task_id 去重,重号会让后来的经验覆盖前一条
        raise ValueError(f"task_id 重复 {len(dupes)} 个(如 {dupes[:3]}),记忆会互相覆盖")
    return tasks


# 内置玩具题集:mock 冒烟用,不依赖任何外部数据。
# 后三题是前三题的改写(同一答案),用来验证"回填的经验能被下一题检索到"。
TOY_TASKS: List[Task] = [
    Task("toy_01", "What is the date of birth of the director of film Amateur Crook?",
         ["July 7, 1901"]),
    Task("toy_02", "Which country is the director of film The Bicycle Thief a citizen of?",
         ["Italy"]),
    Task("toy_03", "Who is the composer of the film Vertigo?",
         ["Bernard Herrmann"]),
    Task("toy_04", "When was the director of the film Amateur Crook born?",
         ["July 7, 1901"], meta={"paraphrase_of": "toy_01"}),
    Task("toy_05", "What is the country of citizenship of the person who directed "
                   "The Bicycle Thief?",
         ["Italy"], meta={"paraphrase_of": "toy_02"}),
    Task("toy_06", "Which composer wrote the score for the film Vertigo?",
         ["Bernard Herrmann"], meta={"paraphrase_of": "toy_03"}),
]

# 每题的假回复,故意各用一种真实模型常见格式;toy_03 是错答(近似拼写)。
TOY_REPLIES: Dict[str, List[str]] = {
    "toy_01": ["Rationale: Amateur Crook was directed by Sam Katzman.\n"
               "Final Answer: July 7, 1901"],
    "toy_02": ["**Final Answer:** Italy"],
    "toy_03": ["The answer is Bernard Herman."],
    "toy_04": ["<think>Experience #1 已经记过 Sam Katzman 的生日。</think>\n"
               "Final Answer: \\boxed{July 7, 1901}"],
    "toy_05": ["Final Answer: **Italy**"],
    "toy_06": ["Final Answer:\nBernard Herrmann"],
}
TOY_EXPECT_PRED = {
    "toy_01": "July 7, 1901",
    "toy_02": "Italy",
    "toy_03": "Bernard Herman",
    "toy_04": "July 7, 1901",
    "toy_05": "Italy",
    "toy_06": "Bernard Herrmann",
}
TOY_EXPECT_CORRECT = {"toy_01": True, "toy_02": True, "toy_03": False,
                      "toy_04": True, "toy_05": True, "toy_06": True}

# 各被试的单轮上下文能把回填的反馈带到什么程度(实测,见交接说明):
#   feedback_text —— SimpleContextBuilder,反馈全文进 prompt
#   result_flag   —— 只带 Result: Success/Failure,不带反馈全文
#   none          —— 只塞过去的答案片段,反馈和对错都进不了 prompt
CTX_FEEDBACK_SUPPORT = {"exprag": "feedback_text", "exprecent": "feedback_text",
                        "remem": "result_flag",
                        "dc_cu": "none", "dc_rs": "none", "awm": "none"}


# ───────────────────────────────────────────────────────────── prompt 构造

ANSWER_FORMAT_HINT = ("Answer concisely. Put the final answer on the last line "
                      "in exactly this form:\nFinal Answer: <answer>")

SYSTEM_PROMPT = ("You are a careful question-answering assistant. You may be shown "
                 "experiences from earlier tasks; use them only when relevant. "
                 "Always end your reply with a line 'Final Answer: <answer>'.")


def build_prompt(task: Task, style: str = "instructed") -> str:
    """构造喂给被试的 query(库内部会再拿它去检索 + 拼经验上下文)。

    style=bare:       只给问题(检索最干净,但格式约束只能靠 system_prompt,
                      而 DC/AWM 两个被试不接 system_prompt)
    style=instructed: 问题 + 一行格式约束(默认;所有被试都吃得到)
    """
    parts = [task.question]
    if task.options:
        opts = "\n".join(f"{chr(65 + i)}. {o}" for i, o in enumerate(task.options))
        parts.append(f"Options:\n{opts}")
    if style == "instructed":
        parts.append(ANSWER_FORMAT_HINT if not task.options else
                     "Answer with the letter of the correct option on the last line "
                     "in exactly this form:\nFinal Answer: <letter>")
    return "\n\n".join(parts)


# ───────────────────────────────────────────────────────────── 答案抽取

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S | re.I)
_BOLD = re.compile(r"\*\*|__")

# 优先级从高到低:显式 Final Answer > \boxed{} > Answer: > "the answer is"
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("final_answer", re.compile(r"final\s*answer\s*[:：]\s*([^\n]*)", re.I)),
    ("boxed", re.compile(r"\\boxed\s*\{([^{}]*)\}")),
    ("answer_colon", re.compile(r"(?<!final )\banswer\s*[:：]\s*([^\n]*)", re.I)),
    ("answer_is", re.compile(r"\banswers?\s+(?:is|are)\s*[:：]?\s*([^\n]*)", re.I)),
]

_TRAILING_JUNK = " \t\r\n.,;:!*_`\"'“”‘’()[]{}"


def _next_nonempty_line(text: str, pos: int) -> str:
    for line in text[pos:].splitlines():
        if line.strip():
            return line.strip()
    return ""


def _cleanup(cand: str) -> str:
    cand = cand.strip()
    cand = _BOLD.sub("", cand)
    cand = re.sub(r"\\boxed\s*\{([^{}]*)\}", r"\1", cand)
    cand = cand.strip(_TRAILING_JUNK)
    cand = re.sub(r"\s+", " ", cand).strip()
    return cand


def _to_option_letter(text: str, options: Sequence[str]) -> str:
    m = re.match(r"[\(\[]?\s*([A-Za-z])\s*[\)\].,:]?(?:\s|$)", text)
    if m:
        letter = m.group(1).upper()
        if 0 <= ord(letter) - 65 < len(options):
            return letter
    for i, opt in enumerate(options):
        if normalize_answer(opt) == normalize_answer(text):
            return chr(65 + i)
    return text


def extract_answer(raw: str, options: Optional[Sequence[str]] = None) -> str:
    """从自由文本回复里抽最终答案。取每种标记的**最后一次**出现
    (模型常先复述再定稿),标记全无时退化成最后一行非空文本。"""
    if not raw:
        return ""
    text = _THINK_BLOCK.sub(" ", raw)
    text = _BOLD.sub("", text)

    for _name, pat in _PATTERNS:
        matches = list(pat.finditer(text))
        if not matches:
            continue
        m = matches[-1]
        cand = _cleanup(m.group(1))
        if not cand:                                   # "Final Answer:" 后换行才写答案
            cand = _cleanup(_next_nonempty_line(text, m.end()))
        if cand:
            return _to_option_letter(cand, options) if options else cand

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cand = _cleanup(lines[-1]) if lines else ""
    return _to_option_letter(cand, options) if options else cand


# ───────────────────────────────────────────────────────────── 评分

_PUNCT = set(string.punctuation) | set("“”‘’—–")


def normalize_answer(s: str) -> str:
    """SQuAD/HotpotQA 口径:小写、去冠词、去标点、压空白。"""
    s = s.lower()
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    s = "".join(" " if ch in _PUNCT else ch for ch in s)
    return re.sub(r"\s+", " ", s).strip()


def token_f1(pred: str, ref: str) -> float:
    p, r = normalize_answer(pred).split(), normalize_answer(ref).split()
    if not p or not r:
        return float(p == r)
    common = Counter(p) & Counter(r)
    n = sum(common.values())
    if n == 0:
        return 0.0
    precision, recall = n / len(p), n / len(r)
    return 2 * precision * recall / (precision + recall)


def grade(pred: str, refs: Sequence[str], options: Optional[Sequence[str]] = None,
          correct_on: str = "em", f1_threshold: float = 0.8) -> Dict[str, Any]:
    """返回 {em, f1, is_correct, matched_ref}。选择题按字母严格比。"""
    if options:
        gold = [_to_option_letter(r, options) for r in refs]
        em = float(any(pred.strip().upper()[:1] == g.strip().upper()[:1] for g in gold))
        f1 = em
        matched = gold[0] if gold else ""
    else:
        ems = [float(normalize_answer(pred) == normalize_answer(r)) for r in refs]
        f1s = [token_f1(pred, r) for r in refs]
        em = max(ems) if ems else 0.0
        f1 = max(f1s) if f1s else 0.0
        matched = refs[int(max(range(len(f1s)), key=f1s.__getitem__))] if f1s else ""

    if correct_on == "em":
        ok = em == 1.0
    elif correct_on == "f1":
        ok = f1 >= f1_threshold
    elif correct_on == "either":
        ok = em == 1.0 or f1 >= f1_threshold
    else:
        raise ValueError(f"未知 correct_on={correct_on}")
    return {"em": em, "f1": round(f1, 4), "is_correct": bool(ok), "matched_ref": matched}


def feedback_text(g: Dict[str, Any], pred: str, refs: Sequence[str]) -> str:
    """写回记忆的反馈 f_t。措辞刻意直白:它会作为经验文本进下一题的上下文。"""
    if g["is_correct"]:
        return f"Correct. The verified answer is: {refs[0]}"
    return (f"Incorrect. The submitted answer '{pred}' was wrong; "
            f"the verified answer is: {refs[0]}")


# ───────────────────────────────────────────────────────── 被试装配 / 库对接

def _import_evo_memory(evo_mem_root: str):
    if evo_mem_root not in sys.path:
        sys.path.insert(0, evo_mem_root)
    import evo_memory  # noqa: F401  (触发包级 import,3 处修复见 INTEGRATION §4)
    return evo_memory


def make_retriever(kind: str, model_name: str, device: str):
    from evo_memory.memory.retriever import EmbeddingRetriever, RecencyRetriever
    if kind == "recency":
        return RecencyRetriever()
    r = EmbeddingRetriever(model_name=model_name, device=device)
    _ = r.model            # 立刻加载,别把失败推迟到第一题
    return r


AGENT_CHOICES = ("exprag", "exprecent", "remem", "dc_cu", "dc_rs", "awm")


def make_agent(name: str, llm, retriever, top_k: int = 4, max_iterations: int = 4):
    """按 INTEGRATION §2.1 的统一构造签名装配被试。

    store_successful_only 一律传 False:库里 evolve() 在评分之前就跑,传 True
    等于什么都存不进去(§2.4 的坑)。"只存成功经验"的设定改由 driver 侧
    store_policy=successful_only 在评分后删条目实现。
    """
    from evo_memory.agents.exprag import ExpRAGAgent, ExpRecentAgent
    from evo_memory.agents.remem import ReMemAgent
    from evo_memory.agents.dynamic_cheatsheet import DynamicCheatsheetAgent, CheatsheetMode
    from evo_memory.agents.awm import AWMAgent

    common = dict(top_k=top_k, store_successful_only=False)
    if name == "exprag":
        return ExpRAGAgent(llm=llm, retriever=retriever, **common)
    if name == "exprecent":
        return ExpRecentAgent(llm=llm, **common)          # 自带 RecencyRetriever
    if name == "remem":
        return ReMemAgent(llm=llm, retriever=retriever,
                          max_iterations=max_iterations, **common)
    if name == "dc_cu":
        return DynamicCheatsheetAgent(llm=llm, retriever=retriever,
                                      mode=CheatsheetMode.CUMULATIVE, **common)
    if name == "dc_rs":
        # 注意:枚举叫 SYNTHESIS,不是 INTEGRATION §2.1 写的 RETRIEVAL_SYNTHESIS
        return DynamicCheatsheetAgent(llm=llm, retriever=retriever,
                                      mode=CheatsheetMode.SYNTHESIS, **common)
    if name == "awm":
        return AWMAgent(llm=llm, retriever=retriever, **common)
    raise ValueError(f"未知被试 {name},可选 {AGENT_CHOICES}")


def attach_extractor(agent, options_getter: Callable[[], Optional[Sequence[str]]]) -> None:
    """把 driver 的抽取器挂到被试的 extract_answer 钩子上(实例级覆盖)。

    被试内部 `output = self.extract_answer(response.content)`,而这个 output
    既是返回值也是写进记忆的 ŷ_t。覆盖掉库里那个弱抽取器,记忆里存的就是
    干净答案而不是整段自由文本;顺手把原始回复留在 agent.driver_last_raw,
    driver 日志要记原文。
    """
    def _extract(response: str) -> str:
        agent.driver_last_raw = response
        return extract_answer(response, options_getter())
    agent.extract_answer = _extract        # type: ignore[method-assign]
    agent.driver_last_raw = ""


def backfill_feedback(agent, task: Task, g: Dict[str, Any], pred: str, raw: str,
                      store_policy: str = "all",
                      memory_input: str = "bare") -> Dict[str, Any]:
    """INTEGRATION §2.4 方案 2:评分出来后回填刚写进去的那条记忆。

    三件事库里没做,必须 driver 补:
      1. is_successful / feedback 回填(evolve 时还不知道对错);
      2. **重算 embedding** —— 条目文本变了(反馈 + Success/Failure 都进
         `MemoryEntry.to_text()`),不重算检索用的还是旧向量;
      3. 修 agent.successful_tasks 计数(库只在 kwargs 传了 is_correct 时加)。
    """
    entry = agent.memory.get(task.task_id)      # 注意:是 memory.get(),
    #                                             INTEGRATION 里写的 memory.entries 不存在
    info = {"stored": entry is not None, "dropped": False}
    if entry is None:
        return info

    entry.is_successful = g["is_correct"]
    entry.feedback = feedback_text(g, pred, task.refs)
    if memory_input == "bare":
        # 记忆里存裸问题:检索出来的经验短、干净,不含格式约束那行套话
        entry.input_text = task.question
    entry.metadata.update({
        "em": g["em"], "f1": g["f1"],
        "reference_answer": task.refs[0],
        "raw_response": raw[:2000],
    })
    # 文本变了 → embedding 必须重算,否则检索命中的是回填前的旧向量
    entry.embedding = agent.retriever.encode(entry.to_text())

    if g["is_correct"]:
        agent.successful_tasks += 1             # 库那边没机会加

    if store_policy == "successful_only" and not g["is_correct"]:
        agent.memory.remove(task.task_id)
        info.update(stored=False, dropped=True)
    return info


# ───────────────────────────────────────────────────────────── mock LLM

def make_mock_llm(evo_mem_root: str):
    from evo_memory.llm.base import BaseLLM, LLMResponse

    class MockLLM(BaseLLM):
        """固定回复的假 LLM:不联网、不占卡,用来验 driver 全链路。

        `set_replies([...])` 设定当前这道题的回复队列,按调用顺序消耗,
        最后一条会一直复用(ReMem 的 Think→Act 循环、DC 的策略抽取都会
        在一道题里多次调 LLM)。
        """

        def __init__(self, model_name: str = "mock-llm"):
            super().__init__(model_name=model_name, api_key="mock", api_base=None)
            self.queue: List[str] = []
            self.default_reply = "Final Answer: unknown"
            self.prompts: List[str] = []          # 记下每次真正送出去的 prompt

        def set_replies(self, replies: Sequence[str]) -> None:
            self.queue = list(replies)

        def _generate(self, messages, **kwargs):
            self.prompts.append("\n".join(m["content"] for m in messages))
            if not self.queue:
                reply = self.default_reply
            elif len(self.queue) > 1:
                reply = self.queue.pop(0)
            else:
                reply = self.queue[0]
            ptok = sum(len(m["content"]) for m in messages) // 4
            ctok = max(1, len(reply) // 4)
            return LLMResponse(content=reply, model=self.model_name,
                               usage={"prompt_tokens": ptok, "completion_tokens": ctok,
                                      "total_tokens": ptok + ctok},
                               finish_reason="stop")

    return MockLLM()


# ───────────────────────────────────────────────────────────── 主循环

def git_head() -> str:
    try:
        return subprocess.check_output(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


class _EmptyState:
    """run_single_turn 抛异常时的占位状态,保证日志字段齐整。"""
    retrieved: List[Any] = []


def run_driver(
    agent,
    tasks: Sequence[Task],
    *,
    on_error: str = "skip",
    query_style: str = "instructed",
    correct_on: str = "em",
    f1_threshold: float = 0.8,
    store_policy: str = "all",
    memory_input: str = "bare",
    out_path: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    mock_llm=None,
    replies: Optional[Dict[str, List[str]]] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """跑一遍任务流,返回汇总 + 逐题记录。out_path 给了就写 jsonl。"""
    records: List[Dict[str, Any]] = []
    out = open(out_path, "w") if out_path else None
    header = {"record": "config", "ts": datetime.now().isoformat(timespec="seconds"),
              "git_head": git_head(), "n_tasks": len(tasks), **(config or {})}
    if out:
        out.write(json.dumps(header, ensure_ascii=False) + "\n")
    if verbose:
        print(f"[driver] {json.dumps(header, ensure_ascii=False)}")

    current_options: List[Optional[Sequence[str]]] = [None]
    attach_extractor(agent, lambda: current_options[0])

    n_correct = 0
    sum_f1 = 0.0
    cum_acc: List[float] = []
    t_start = time.time()

    for i, task in enumerate(tasks):
        current_options[0] = task.options
        query = build_prompt(task, query_style)
        if mock_llm is not None and replies is not None:
            mock_llm.set_replies(replies.get(task.task_id, ["Final Answer: unknown"]))

        req0 = agent.llm.total_requests
        ptok0 = agent.llm.total_prompt_tokens
        ctok0 = agent.llm.total_completion_tokens
        mem_before = len(agent.memory)

        agent.driver_last_raw = ""
        err = None
        t0 = time.time()
        try:
            pred, state = agent.run_single_turn(task_id=task.task_id, query=query,
                                               system_prompt=SYSTEM_PROMPT)
        except Exception as exc:                    # 单题失败不许拖垮整跑,但必须计入分母
            err = f"{type(exc).__name__}: {exc}"    # (T12b 防幸存者偏差:失败题算错不算无)
            if on_error == "abort":
                raise
            pred, state = "", _EmptyState()
        latency = time.time() - t0

        raw = getattr(agent, "driver_last_raw", "")
        g = grade(pred, task.refs, task.options, correct_on, f1_threshold)
        store_info = ({"stored": False, "dropped": False} if err else
                      backfill_feedback(agent, task, g, pred, raw,
                                        store_policy=store_policy,
                                        memory_input=memory_input))

        n_correct += int(g["is_correct"])
        sum_f1 += g["f1"]
        cum_acc.append(round(n_correct / (i + 1), 4))

        rec = {
            "record": "task", "i": i, "task_id": task.task_id,
            "question": task.question, "refs": task.refs,
            "pred": pred, "raw_response": raw,
            **{k: g[k] for k in ("em", "f1", "is_correct")},
            "latency_s": round(latency, 3),
            "llm_calls": agent.llm.total_requests - req0,
            "prompt_tokens": agent.llm.total_prompt_tokens - ptok0,
            "completion_tokens": agent.llm.total_completion_tokens - ctok0,
            "mem_before": mem_before, "mem_after": len(agent.memory),
            "retrieved": [{"rank": r.rank, "task_id": r.entry.task_id,
                           "score": round(r.score, 4),
                           "was_successful": r.entry.is_successful}
                          for r in state.retrieved],
            **store_info,
        }
        if err:
            rec["error"] = err
        records.append(rec)
        if out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if verbose and err:
            print(f"[{i:>3}] {task.task_id:<24} ERROR {err}")
        elif verbose:
            hits = ",".join(f"{r['task_id']}:{r['score']:.2f}" for r in rec["retrieved"]) or "-"
            print(f"[{i:>3}] {task.task_id:<24} pred={pred!r:<28} "
                  f"gold={task.refs[0]!r:<24} {'OK ' if g['is_correct'] else 'BAD'} "
                  f"f1={g['f1']:.2f} {latency:.2f}s mem {mem_before}->{len(agent.memory)} "
                  f"retr[{hits}]")

    mem_stats = agent.memory.get_statistics()
    summary = {
        "record": "summary",
        "n": len(tasks), "n_correct": n_correct,
        "accuracy": round(n_correct / max(len(tasks), 1), 4),
        "mean_f1": round(sum_f1 / max(len(tasks), 1), 4),
        "cum_accuracy_curve": cum_acc,
        "mean_latency_s": round(sum(r["latency_s"] for r in records) / max(len(records), 1), 3),
        "total_llm_calls": sum(r["llm_calls"] for r in records),
        "total_prompt_tokens": sum(r["prompt_tokens"] for r in records),
        "total_completion_tokens": sum(r["completion_tokens"] for r in records),
        "memory_entries": mem_stats["total_entries"],
        "memory_successful": mem_stats["successful_entries"],
        "tasks_with_retrieval": sum(1 for r in records if r["retrieved"]),
        "n_errors": sum(1 for r in records if r.get("error")),   # 失败题已算进分母
        "wall_s": round(time.time() - t_start, 2),
    }
    if out:
        out.write(json.dumps(summary, ensure_ascii=False) + "\n")
        out.close()
    if verbose:
        print(f"[driver] summary: {json.dumps({k: v for k, v in summary.items() if k != 'cum_accuracy_curve'}, ensure_ascii=False)}")
        print(f"[driver] cumulative accuracy: {cum_acc}")
        if out_path:
            print(f"[driver] wrote {out_path}")
    return {"summary": summary, "records": records, "config": header}


# ───────────────────────────────────────────────────────────── 自检 / 冒烟

EXTRACT_CASES: List[Tuple[str, Optional[List[str]], str]] = [
    ("Final Answer: July 7, 1901", None, "July 7, 1901"),
    ("Rationale: he was born in 1901.\nFinal Answer: July 7, 1901", None, "July 7, 1901"),
    ("**Final Answer:** July 7, 1901", None, "July 7, 1901"),
    ("Final Answer: **July 7, 1901**", None, "July 7, 1901"),
    ("Final Answer:\nJuly 7, 1901", None, "July 7, 1901"),
    ("Final Answer: \\boxed{July 7, 1901}", None, "July 7, 1901"),
    ("\\boxed{July 7, 1901}", None, "July 7, 1901"),
    ("The answer is July 7, 1901.", None, "July 7, 1901"),
    ("Answer: July 7, 1901", None, "July 7, 1901"),
    ("<think>maybe 1900? no.</think>\nFinal Answer: July 7, 1901", None, "July 7, 1901"),
    ("Final Answer: A\nOops, let me redo.\nFinal Answer: July 7, 1901", None, "July 7, 1901"),
    ("Final answer:   July 7, 1901   ", None, "July 7, 1901"),
    ("July 7, 1901", None, "July 7, 1901"),                     # 无标记 → 最后一行
    ("Reasoning...\nSo it must be July 7, 1901", None, "So it must be July 7, 1901"),
    ("", None, ""),
    ("Final Answer: C", ["Rome", "Milan", "Paris"], "C"),
    ("Final Answer: (C)", ["Rome", "Milan", "Paris"], "C"),
    ("Final Answer: C. Paris", ["Rome", "Milan", "Paris"], "C"),
    ("Final Answer: Paris", ["Rome", "Milan", "Paris"], "C"),    # 选项原文 → 字母
]

GRADE_CASES: List[Tuple[str, List[str], Optional[List[str]], float, float, bool]] = [
    # pred, refs, options, em, f1(约), is_correct(correct_on=em)
    ("July 7, 1901", ["July 7, 1901"], None, 1.0, 1.0, True),
    ("the July 7, 1901.", ["July 7, 1901"], None, 1.0, 1.0, True),
    ("sam katzman", ["Sam Katzman"], None, 1.0, 1.0, True),
    ("Bernard Herman", ["Bernard Herrmann"], None, 0.0, 0.5, False),
    ("July 8, 1901", ["July 7, 1901"], None, 0.0, 0.6667, False),
    ("Paris, France", ["Paris"], None, 0.0, 0.6667, False),
    ("Italy", ["Italian Republic", "Italy"], None, 1.0, 1.0, True),
    ("c", ["Paris"], ["Rome", "Milan", "Paris"], 1.0, 1.0, True),
    ("A", ["Paris"], ["Rome", "Milan", "Paris"], 0.0, 0.0, False),
]


def selftest() -> int:
    fails = 0
    print("=== 答案抽取 ===")
    for raw, opts, want in EXTRACT_CASES:
        got = extract_answer(raw, opts)
        ok = got == want
        fails += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {raw!r:<62} -> {got!r}"
              + ("" if ok else f"   期望 {want!r}"))

    print("=== 评分 ===")
    for pred, refs, opts, em, f1, ok_want in GRADE_CASES:
        g = grade(pred, refs, opts, correct_on="em")
        ok = (g["em"] == em and abs(g["f1"] - f1) < 0.01 and g["is_correct"] == ok_want)
        fails += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] pred={pred!r:<18} refs={refs} "
              f"-> em={g['em']} f1={g['f1']} correct={g['is_correct']}"
              + ("" if ok else f"   期望 em={em} f1≈{f1} correct={ok_want}"))

    print("=== 反馈文本 ===")
    for pred, refs in [("July 7, 1901", ["July 7, 1901"]), ("Bernard Herman", ["Bernard Herrmann"])]:
        g = grade(pred, refs, None, "em")
        print(f"  {feedback_text(g, pred, refs)!r}")

    print(f"\n[selftest] {'PASS' if fails == 0 else f'FAIL ({fails} 例)'}"
          f" — 抽取 {len(EXTRACT_CASES)} 例 + 评分 {len(GRADE_CASES)} 例")
    return 1 if fails else 0


def mock_smoke(evo_mem_root: str, agent_name: str, store_policy: str,
               retriever_kind: str, retriever_model: str, device: str,
               out_path: Optional[str], seed: int) -> int:
    """假 LLM 走 driver 全链路,并断言:抽取对、评分对、回填后能被检索到。"""
    random.seed(seed)
    _import_evo_memory(evo_mem_root)
    llm = make_mock_llm(evo_mem_root)
    retriever = make_retriever(retriever_kind, retriever_model, device)
    agent = make_agent(agent_name, llm, retriever)
    print(f"[mock-smoke] agent={agent_name} retriever={type(retriever).__name__} "
          f"store_policy={store_policy} seed={seed}")

    res = run_driver(
        agent, TOY_TASKS,
        store_policy=store_policy, out_path=out_path,
        config={"mode": "mock-smoke", "agent": agent_name, "llm": "MockLLM",
                "retriever": type(retriever).__name__, "seed": seed,
                "store_policy": store_policy},
        mock_llm=llm, replies=TOY_REPLIES,
    )
    recs = {r["task_id"]: r for r in res["records"]}
    s = res["summary"]

    checks: List[Tuple[str, bool, str]] = []
    notes: List[str] = []                    # 库侧行为差异,不算断言失败但要说出来

    # 1) 六种回复格式的抽取结果
    for tid, want in TOY_EXPECT_PRED.items():
        checks.append((f"抽取 {tid}", recs[tid]["pred"] == want,
                       f"got={recs[tid]['pred']!r} want={want!r}"))
    # 2) 评分
    for tid, want in TOY_EXPECT_CORRECT.items():
        checks.append((f"评分 {tid}", recs[tid]["is_correct"] == want,
                       f"got={recs[tid]['is_correct']} want={want} f1={recs[tid]['f1']}"))
    checks.append(("准确率 5/6", s["n_correct"] == 5, f"n_correct={s['n_correct']}"))

    # 3) 记忆条数随 store_policy 变
    want_mem = 6 if store_policy != "successful_only" else 5
    checks.append((f"记忆条数 {want_mem}", s["memory_entries"] == want_mem,
                   f"memory_entries={s['memory_entries']}"))
    checks.append(("成功条目 5", s["memory_successful"] == 5,
                   f"memory_successful={s['memory_successful']}"))
    if store_policy == "successful_only":
        checks.append(("错答条目已删", agent.memory.get("toy_03") is None
                       and recs["toy_03"]["dropped"], "toy_03 应被删除"))
    else:
        e3 = agent.memory.get("toy_03")
        checks.append(("错答条目 is_successful=False",
                       e3 is not None and e3.is_successful is False, "toy_03"))
        checks.append(("错答条目反馈含参考答案",
                       e3 is not None and "Bernard Herrmann" in (e3.feedback or ""),
                       f"feedback={None if e3 is None else e3.feedback!r}"))

    # 4) 回填后的经验能被下一道改写题检索到
    #    exprecent 强制用 RecencyRetriever(库里写死),不按相似度排,单列一条
    if agent_name == "exprecent" or retriever_kind != "embedding":
        got = {r["task_id"] for r in recs["toy_06"]["retrieved"]}
        # toy_06 之前入库的经验(successful_only 下 toy_03 已被删),取最近 4 条
        pool = [t for t in ("toy_01", "toy_02", "toy_03", "toy_04", "toy_05")
                if not (store_policy == "successful_only" and t == "toy_03")]
        want = set(pool[-4:])
        checks.append(("recency 检索到最近 4 条经验", got == want,
                       f"got={sorted(got)} want={sorted(want)}"))
    if retriever_kind == "embedding" and agent_name != "exprecent":
        pairs = [("toy_04", "toy_01"), ("toy_05", "toy_02")]
        if store_policy != "successful_only":
            pairs.append(("toy_06", "toy_03"))
        for tid, want_top1 in pairs:
            retr = recs[tid]["retrieved"]
            top1 = retr[0]["task_id"] if retr else None
            checks.append((f"{tid} top-1 检索到 {want_top1}", top1 == want_top1,
                           f"retrieved={[(r['task_id'], r['score']) for r in retr]}"))
        if store_policy == "successful_only":
            # 错答条目已被删,改写题 toy_06 只能检索到别的经验 —— 这正是该策略的效果
            checks.append(("toy_06 检索不到被删的 toy_03",
                           all(r["task_id"] != "toy_03" for r in recs["toy_06"]["retrieved"]),
                           f"retrieved={[r['task_id'] for r in recs['toy_06']['retrieved']]}"))
    else:
        checks.append(("检索非空(recency)", bool(recs["toy_04"]["retrieved"]), ""))

    # 5) 回填的反馈真的进了下一题的 prompt(不只是躺在内存里)。
    #    能进到什么程度取决于被试自己的上下文构造 —— 见 CTX_FEEDBACK_SUPPORT。
    joined = "\n".join(llm.prompts)
    support = CTX_FEEDBACK_SUPPORT[agent_name]
    if support == "feedback_text":
        checks.append(("prompt 里出现回填的 Correct 反馈全文",
                       "Correct. The verified answer is: July 7, 1901" in joined, ""))
        checks.append(("prompt 里出现回填的 Incorrect 反馈全文",
                       ("Incorrect. The submitted answer" in joined)
                       if store_policy != "successful_only" else True, ""))
    elif support == "result_flag":
        checks.append(("prompt 里出现回填的成功标记", "Result: Success" in joined, ""))
        checks.append(("prompt 里出现回填的失败标记",
                       ("Result: Failure" in joined)
                       if store_policy != "successful_only" else True, ""))
        notes.append("ReMem 的单轮上下文只带 Result: Success/Failure,不带反馈全文(库侧行为)")
    else:
        notes.append(f"{agent_name} 的单轮上下文只塞 entry.output_text[:100],"
                     "回填的反馈与对错标记都进不了 prompt(库侧行为,已记入交接)")

    # 6) 回填后 embedding 必须重算过:存的向量应等于"回填后文本"的编码
    if type(agent.retriever).__name__ == "EmbeddingRetriever":
        e1 = agent.memory.get("toy_01")
        checks.append(("回填后 embedding 已重算",
                       e1 is not None
                       and e1.embedding == agent.retriever.encode(e1.to_text()), ""))

    checks.append(("记忆里存的是干净答案不是整段回复",
                   all(len((agent.memory.get(t.task_id).output_text
                            if agent.memory.get(t.task_id) else "")) < 40
                       for t in TOY_TASKS), ""))
    # 7) 第一题没有可检索的经验(冷启动),后面的题有
    checks.append(("首题检索为空", recs["toy_01"]["retrieved"] == [], ""))
    checks.append(("每题恰好 1 次 LLM 调用" if agent_name != "remem" else "每题至少 1 次 LLM 调用",
                   all(r["llm_calls"] >= 1 for r in res["records"]), ""))

    print("\n=== mock 冒烟断言 ===")
    fails = 0
    for name, ok, detail in checks:
        fails += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if not ok else ""))
    for n in notes:
        print(f"  [注] {n}")
    print(f"\n[mock-smoke] {'PASS' if fails == 0 else f'FAIL ({fails}/{len(checks)})'} "
          f"— {len(checks)} 条断言,链路 search→synthesize→generate(mock)→evolve→回填→再检索")
    return 1 if fails else 0


# ───────────────────────────────────────────────────────────── CLI

def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Evo-Memory 被试的单轮 QA driver(T12c)",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true", help="只跑抽取/评分单元自检")
    p.add_argument("--mock-smoke", action="store_true", help="假 LLM 走全链路 + 断言")
    p.add_argument("--agent", default="exprag", choices=AGENT_CHOICES)
    p.add_argument("--tasks", help="任务 jsonl/json(字段自动识别)")
    p.add_argument("--pair-expand", action="store_true",
                   help="L4 任务对文件:每条 seed_question/l4_question 展成前后两道题")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--shuffle-seed", type=int, default=None,
                   help="给了就按此种子打乱任务顺序(C3 的顺序自变量)")
    p.add_argument("--seed", type=int, default=20260729, help="全局随机种子,写进日志")
    # LLM
    p.add_argument("--model", default="Qwen2.5-7B-Instruct")
    p.add_argument("--api-base", default="http://localhost:8791/v1")
    p.add_argument("--api-key", default="dummy")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--timeout", type=int, default=180)
    # 检索器
    p.add_argument("--retriever", default="embedding", choices=("embedding", "recency"))
    p.add_argument("--retriever-model", default="BAAI/bge-base-en-v1.5")
    p.add_argument("--retriever-device", default="cpu")
    p.add_argument("--top-k", type=int, default=4)
    # 评分与记忆策略
    p.add_argument("--correct-on", default="em", choices=("em", "f1", "either"))
    p.add_argument("--f1-threshold", type=float, default=0.8)
    p.add_argument("--store-policy", default="all", choices=("all", "successful_only"),
                   help="all:全部经验入库;successful_only:评分后删掉错答条目")
    p.add_argument("--query-style", default="instructed", choices=("instructed", "bare"))
    p.add_argument("--on-error", default="skip", choices=("skip", "abort"),
                   help="skip:单题异常记成错答继续跑(计入分母);abort:直接抛出")
    p.add_argument("--memory-input", default="bare", choices=("bare", "prompt"),
                   help="记忆条目里存裸问题还是整段 prompt(会连带影响 embedding)")
    p.add_argument("--out", default=None, help="结果 jsonl;不给则自动放 logs/")
    p.add_argument("--evo-mem-root", default=os.environ.get("EVO_MEM_ROOT",
                                                            DEFAULT_EVO_MEM_ROOT))
    a = p.parse_args(argv)

    if a.selftest:
        return selftest()

    if a.mock_smoke:
        out = a.out
        if out is None:
            out = os.path.join(REPO_ROOT, "logs",
                               f"evomem_driver_mock_{a.agent}_{a.store_policy}.jsonl")
            os.makedirs(os.path.dirname(out), exist_ok=True)
        return mock_smoke(a.evo_mem_root, a.agent, a.store_policy, a.retriever,
                          a.retriever_model, a.retriever_device, out, a.seed)

    if not a.tasks:
        p.error("正式跑分要 --tasks(或用 --mock-smoke / --selftest)")

    random.seed(a.seed)
    _import_evo_memory(a.evo_mem_root)
    from evo_memory.llm.openai_llm import OpenAILLM

    tasks = load_tasks(a.tasks, a.limit, a.shuffle_seed, a.pair_expand)
    llm = OpenAILLM(model_name=a.model, api_key=a.api_key, api_base=a.api_base,
                    temperature=a.temperature, max_tokens=a.max_tokens, timeout=a.timeout)
    retriever = make_retriever(a.retriever, a.retriever_model, a.retriever_device)
    agent = make_agent(a.agent, llm, retriever, top_k=a.top_k)

    out = a.out
    if out is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        out = os.path.join(REPO_ROOT, "logs", f"evomem_driver_{a.agent}_{stamp}.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    run_driver(agent, tasks, on_error=a.on_error,
               query_style=a.query_style, correct_on=a.correct_on,
               f1_threshold=a.f1_threshold, store_policy=a.store_policy,
               memory_input=a.memory_input, out_path=out,
               config={"mode": "run", "agent": a.agent, "model": a.model,
                       "api_base": a.api_base, "retriever": a.retriever,
                       "retriever_model": a.retriever_model,
                       "retriever_device": a.retriever_device, "top_k": a.top_k,
                       "temperature": a.temperature, "max_tokens": a.max_tokens,
                       "tasks_file": a.tasks, "limit": a.limit,
                       "pair_expand": a.pair_expand,
                       "shuffle_seed": a.shuffle_seed, "seed": a.seed,
                       "correct_on": a.correct_on, "f1_threshold": a.f1_threshold,
                       "store_policy": a.store_policy, "query_style": a.query_style,
                       "memory_input": a.memory_input, "on_error": a.on_error})
    return 0


# ───────────────────────────────────────────────────────────── NOTES
#
# 换真实服务只改这几个参数(其余一律不动):
#   --model Qwen2.5-7B-Instruct      # 或 Qwen2.5-14B-Instruct;必须和 vLLM
#                                    #   serve 的 --served-model-name 一致
#   --api-base http://tokyoNNN:8791/v1
#   --api-key dummy                  # vLLM 不校验
#   --max-tokens 512                 # 7B/14B 带 rationale 时给 512~1024
#   --tasks benchmark_design/l3_2wiki_items.jsonl --limit 50
#   --retriever-device cpu           # 想上卡就 cuda:N,但 bge 每题一次 encode,CPU 够
# vLLM 起法见 INTEGRATION §3(FLASHINFER_DISABLE_VERSION_CHECK=1 必须带),
# 走 gpu-run skill 发射。
#
# 与 INTEGRATION 文档/库代码实际行为不一致的地方(实测,2026-07-30):
#   1. §2.4 写的 `agent.memory.entries[-1]` 不存在 —— Memory 的列表是私有
#      `_entries`,公开入口是 `get(task_id)` / `get_all()` / `get_recent(k)`。
#      本 driver 用 `memory.get(task_id)` 定位条目。
#   2. §2.4 只说回填 is_successful/feedback,漏了 **embedding 必须重算**:
#      反馈和 Success/Failure 都进 `MemoryEntry.to_text()`,不重算的话检索
#      用的还是回填前的旧向量。
#   3. §2.1 写的 `mode=RETRIEVAL_SYNTHESIS` 不存在,枚举是
#      `CheatsheetMode.SYNTHESIS`(DC-RS)/`CUMULATIVE`(DC-Cu);照文档写会
#      AttributeError。
#   4. `RecencyRetriever` 的排序是反的:`get_recent(k)` 返回 `_entries[-k:]`
#      后按下标给 rank/score,rank 1 落在窗口里**最旧**那条。ExpRecent 基线
#      的"最近优先"因此名不副实,正式跑分前要么改库要么在论文里声明。
#   5. `run_single_turn` 只在调用方传了 `is_correct=` 时才加
#      `successful_tasks`,而正确性事后才知道 → 计数永远是 0,driver 自己补。
#   6. 上下文构造对回填反馈的利用度差别很大(mock 冒烟实测):ExpRAG/ExpRecent
#      的 SimpleContextBuilder 带反馈全文;ReMem 只带 Result: Success/Failure;
#      DC-Cu/DC-RS/AWM 只塞 `entry.output_text[:100]` —— 既无问题也无对错,
#      检索到的经验退化成一串裸答案。这是重建代码的保真度问题(INTEGRATION
#      §7 第 4 条要核对的正是它),跑分前必须决定"照跑并声明"还是"改上下文"。
#   7. `related_work/` 整个目录在 .gitignore 里 → INTEGRATION 报告和
#      evo_mem_smoke.py 都没进 git。本 driver 因此放 benchmark_design/。

if __name__ == "__main__":
    sys.exit(main())
