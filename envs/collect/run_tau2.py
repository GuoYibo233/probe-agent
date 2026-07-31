"""tau2-bench(客服域)驱动:每步「一段思考 + 一条工具调用或一句对用户说的话」全录。

要回答什么问题
--------------
给探针流水线补一个**对话型**工具调用环境:agent 扮客服,一个 LLM 用户模拟器扮
客户,agent 每轮要么调一个域工具(airline 14 个 / retail 16 个),要么对客户说一句
话。落盘格式与 run_appworld.py / run_alfworld.py 逐字段对齐(meta/gen/env/final
四种行 + `--resume` 认 `"type": "final"`),下游 annotate 只需加一个分支就能吃。

解释器
------
只能用 tau2 自己的 venv(它才装了 tau2 + loguru + openai):
  envs/tau2-bench/.venv/bin/python envs/collect/run_tau2.py ...

用法
----
  envs/tau2-bench/.venv/bin/python envs/collect/run_tau2.py \
      --base-url http://HOST:8101/v1 --model qwen3.5-27b \
      --user-base-url http://HOST:8102/v1 --user-model qwen3.6-27b \
      --domain airline --split test --n 2 \
      --outdir envs/runs/smoke_tau2/tau2_q35 --exp smoke_tau2
自测(纯 CPU,不发任何 HTTP、不碰显卡):
  envs/tau2-bench/.venv/bin/python envs/collect/run_tau2.py --selftest

与 appworld / alfworld 的差别
----------------------------
1. 有**第二个 LLM**:用户模拟器。它的提示词里含 agent 从未见过的场景真值,所以
   它的生成单独记成 `type: "user"` 行,并且**任何时候都不许把 type="user" 的内容
   喂进探针输入**(build.py 只认 gen/env,不认识的 type 直接忽略,天然隔离)。
2. 工具参数是**嵌套 JSON**(list[dict] / dict),不是 appworld 那种扁平 kwarg。
3. agent 每轮有两种合法输出:调工具,或对客户说话。说话那轮不产生工具调用。

已知偏差(七条,读数字前必须知道)
--------------------------------
1. **文本协议,不是原生 function call**。common.py:20-91 的 Chat 两条路都不传
   `tools=`(:30-35 raw 路自己拼 `<|im_start|>` 模板,:77-80 chat 路也没有 tools
   参数),改它等于动 appworld/alfworld/tales 三个采集器的共同口径。所以这里和
   appworld(python 代码块)/alfworld(`ACTION:` 行)同一路子:`TOOL: <name>` +
   一个 ```json 参数块,由本采集器合成 tau2 的 ToolCall 交给环境执行。
   **后果:与 tau2-bench 官方排行榜的数字不可比**(官方用原生 function call)。
2. **一轮只允许一次工具调用**。tau2 原生支持一轮多调(MultiToolMessage),限成
   一次会拉长轨迹、也偏离官方设定;放开则探针的「一步一个标签」口径要改。
3. **NL 断言未评**,retail 的官方 reward 算不全。实测 retail 114 题里 112 题的
   reward_basis = {DB, NL_ASSERTION},NL 断言要 LLM 裁判
   (evaluator/evaluator_nl_assertions.py 调 generate)。本采集器只用
   EvaluationType.ALL_IGNORE_BASIS(ENV+ACTION+COMMUNICATE,零 LLM),再按 task
   自己的 basis 折出 official_reward。airline 50 题全是 {DB, COMMUNICATE},两项
   都不用 LLM,**official_reward 完整**;retail 112/114 题会是
   `official_reward_complete: false`。
4. **`action` 串在两种参数值上会静默丢参**:值里含未配平 `(`(tau2 的
   `calculate(expression=...)` 天生带括号)时 rules.first_call_named 返回 `[]`
   (参数全丢);值里含**奇数个**转义 `\\"` 时相邻两个键会被并成一个。两者都不
   报错。所以每步都做一次往返自检,不一致就在 env 行上打 `args_lossy: true` 并
   计数(final 行的 `n_args_lossy`)——这是唯一的报警器。env 行另写结构化的
   `tool_name` / `tool_args`(原始 dict),下游可以完全不解析 action 串。
5. **SAY 轮不产生事件**:env 行的 `action` 是 None,build.py:64-65 的
   `if not action: continue` 在 `hist.append` 之前,所以 agent 对客户说的话
   **整段不进探针题干的历史**。原话留在 env 行的 `said` 字段里,两种口径都留着,
   选哪种是数据设定级决定(见下面「未定项」)。
6. **只读题的 official_reward 可以白送 1.0**。self-test 实测:airline task 1 的
   golden actions 只有 get_user_details / get_reservation_details 两个读操作,
   communicate_info 是空表 —— 所以 DB 哈希天然相等、COMMUNICATE 天然满分,一个
   什么正事都没干的 agent 折出来的 official_reward 就是 1.0(同一次运行里
   ALL_IGNORE_BASIS 的 reward 是 0.0,因为 ACTION 检查没过)。**official_reward 和
   reward 必须并排读**,单看前者会把摆烂读成满分。
7. **用户模拟器默认打同一个服务、用同一个模型**(`--user-model` 缺省 = `--model`)。
   自说自话是混淆项,轨迹分布会偏,而且这件事在任何数字里都看不出来。缺省时打一行
   WARN;tau2 官方 smoke 用的是 q35 agent + q36 user。

还差什么才能真正放量采集
------------------------
- 一个 **vLLM /v1 服务**(agent 侧):`--base-url http://<host>:<port>/v1`
  `--model <served-model-name>`。系统提示实测 airline ≈ 23k 字符(policy 7676 +
  14 个工具的 openai_schema 14623)≈ 6k token,retail 略小;服务必须
  `--max-model-len 65536` 量级,否则多轮后必然截断。
- 建议**第二个服务**(用户模拟器侧)`--user-base-url/--user-model`,不然就是偏差
  第 7 条。GPU 侧的起服务/挑卡/发射一律走 gpu-run skill,本文件不碰显卡。
- 三堆题单文件(annotate 侧要 train/val/test 三个 txt,每行一个
  `<domain>/<task_id>`)。airline/retail **官方只有 train/test/base**,没有 val,
  见「未定项」。

未定项(需要人拍板,不该采集器自己猜)
------------------------------------
- airline/retail 没有 val 堆(实测 split 只有 train/test/base;airline 30/20/50、
  retail 74/40/114),而 build.py:33 的 SPLITS 写死三堆。从 train 切一刀还是改
  SPLITS,是数据设定级决定。
- agent 与用户模拟器该不该用不同模型、固定用哪个当用户。
- 只跑 airline+retail 还是加 telecom(telecom 有用户侧工具、task id 长成
  `[mms_issue]airplane_mode_on|...` 不能直接当文件名,是一块独立工作量)。
- 一轮多调要不要放开;SAY 轮要不要进探针题干历史;retail 的 NL 断言要不要接 LLM
  裁判(不接的话 RESULTS.md 里不能把这个数叫 reward)。
- tau2 仓库该钉哪个 tag(README 明说 <1.0.1 与 >=1.0.1 不可比,改的是
  banking_knowledge;我们只跑 airline/retail 按 README 不受影响,但**具体 tag 本
  文件没核**,标 NOT FOUND,要记进 DATA.md)。

下游待办(本次不改代码,只把接口对齐到「加分支就能用」)
----------------------------------------------------
① pipeline/annotate/rules.py 加 `TAU2_CALL = re.compile(r"tau2\\.(\\w+)\\.(\\w+)\\(")`
   —— 与本文件 TAU2_CALL 同形(action 串刻意做成与 AW_CALL 的 `apis.x.y(` 同形,
   这样参数切法直接复用 first_call_named,不用重新设计)。
② build.py:66-96 的 jsonl_events 加 tau2 分支(照抄 appworld 那 11 行,
   tool = f"tau2.{m.group(1)}.{m.group(2)}"),+ build.py:152-167 的 collect_events
   加 `tau2_*/tau2_*.jsonl` 的 glob。**不加就落进 else 的 tales catch-all**:
   label 变成 `action.split()[0]`,也就是整条 `tau2.airline.book_reservation(...)`
   当一个动词,数据能造、报告正常、只有肉眼看工具词表才发现(extending.md §5 #5)。
③ param_label.py:43-81 与 :125-143 同样两处。
④ eval_causal_call.py:118-124 的 name_re 加 tau2 分支(不加会落 BFCL_CALL 兜底,
   tool_ok 全塌且退出码 0)。
⑤ pipeline/collect/gen_launch.py:ENV_TABLE 加 tau2 行时解释器路径不合模板
   (`$E/{venv}/venv/bin/python` 对不上 `tau2-bench/.venv`),要给 ENV_TABLE 加
   `py` 字段并改 :276;客户端函数还没有 `--domain` 槽位。
"""

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from loguru import logger

REPO = "/home/y-guo/reproduce/new1"
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, f"{REPO}/pipeline/annotate")
from common import Chat, TrajLog  # noqa: E402
from rules import MODEL_OF, SEED, first_call_named  # noqa: E402

# loguru 静音必须在 import tau2 之前:tau2.registry 在 import 时就吐一大段
# DEBUG 注册表(实测),会把 tmux 日志冲掉。
logger.remove()
logger.add(sys.stderr, level="WARNING")

# v1 只放这两个域。硬理由:两者 env.user_tools is None(实测),不涉及用户侧工具;
# telecom 有 user_tools,且 task id 长成 `[mms_issue]airplane_mode_on|bad_...`
# 根本不能当文件名。
DOMAINS = ("airline", "retail")

# 与下游待办① 要加进 rules.py 的那条同形。刻意与 AW_CALL 的 `apis.(\w+).(\w+)\(`
# 一模一样的结构,这样 first_call_named 的括号配平 + 参数切分能原样复用。
TAU2_CALL = re.compile(r"tau2\.(\w+)\.(\w+)\(")

# 【照抄 envs/tau2-bench/src/tau2/orchestrator/orchestrator.py:46-48
#  的 DEFAULT_FIRST_AGENT_MESSAGE】—— 开场白是常量,不花一次 LLM 调用。
FIRST_AGENT_MESSAGE = "Hi! How can I help you today?"

# 【照抄 envs/tau2-bench/src/tau2/user/user_simulator_base.py:51-53】
USER_STOP_TOKENS = ("###STOP###", "###TRANSFER###", "###OUT-OF-SCOPE###")

# 【照抄 envs/tau2-bench/src/tau2/config.py:5 的 DEFAULT_MAX_ERRORS】
DEFAULT_MAX_ERRORS = 10

# 环境返回塞回上下文时的字符上限【照抄 envs/collect/run_appworld.py:105】
RESULT_CAP = 4000

# 【照抄 envs/tau2-bench/src/tau2/agent/llm_agent.py:24-31 的 AGENT_INSTRUCTION】
# 与官方同源,一字不改 —— 换掉它就等于换了任务设定。
AGENT_INSTRUCTION = """
You are a customer service agent that helps the user according to the <policy> provided below.
In each turn you can either:
- Send a message to the user.
- Make a tool call.
You cannot do both at the same time.

Try to be helpful and always follow the policy. Always make sure you generate valid JSON only.
""".strip()

# 我们自己的回复格式段。三条与 run_alfworld.py:42-79 同一语气写死:
#   ① 先推理几句再动作 —— rules.MIN_THINK=40 字符的门槛会把没思考的步**整步丢掉**,
#      「只回一条调用、不许有别的字」那种提示词会让 reasoning 为空,采回来是空数据。
#   ② 回复最后必须是且只是两种块之一(SAY 或 TOOL+JSON),因为解析器只认这两种。
#   ③ 一轮只许一个块;工具名逐字抄自 <tools>;参数必须是合法 JSON。
REPLY_FORMAT = """How to reply, every single turn:

- First reason it out, in a few sentences: what the customer actually needs, \
which policy rule applies, what you still do not know, and why the block you \
are about to send is the right next move. Never skip this reasoning.
- Then end your reply with exactly ONE block, with nothing after it. Only two \
block shapes exist:

  (a) Speak to the customer — one line:
      SAY: <what you say to the customer>

  (b) Call one tool — a line naming the tool, then one fenced JSON object with \
its arguments:
      TOOL: <tool_name>
      ```json
      {"arg_name": "value"}
      ```

- Exactly one block per turn. You cannot speak and call a tool in the same \
turn, and you cannot call two tools in the same turn.
- <tool_name> must be copied VERBATIM from the <tools> list above. Never invent \
a tool name and never guess at a shortened one.
- The JSON object must be valid JSON: double-quoted keys, no trailing commas, \
no comments, no Python literals (`None`/`True` are not JSON — write \
`null`/`true`). Nested objects and arrays are fine; pass them as real JSON.
- A tool with no arguments still needs its block: `{}`.
- Everything the customer tells you arrives as a plain message. Tool output \
arrives prefixed with `Tool result:`; it is never something the customer said."""

TOOL_RE = re.compile(r"TOOL:\s*([A-Za-z_]\w*)")
FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
SAY_MARK = "SAY:"          # 按位置从右边切,不用正则:见 parse_reply 里的说明

# task id 的字符集闸门:必须能直接当文件名的一段(实测 airline/retail 全是 0..113
# 的纯数字,全部合法)。不合法当场掐掉,不静默造出怪文件名。
ID_RE = re.compile(r"[A-Za-z0-9_.-]+")


# ---------- unit id 与落盘命名 ----------

def escape_unit(uid):
    """unit id 含斜杠(`<domain>/<task_id>`),落盘前 `/` -> `__`。

    【照抄 envs/collect/run_alfworld.py:85-96 的转义约定】。
    域名与 task id 都过 ID_RE 闸门(不含 `_` 之外的分隔符、且**没有 `__`**),
    所以这个映射单射可逆:unescape_unit(escape_unit(u)) == u。
    """
    return uid.replace("/", "__")


def unescape_unit(name):
    return name.replace("__", "/")


# ---------- 解析:模型回复 -> 一个块 ----------

def brace_scan(text):
    """从第一个 `{` 起数深度到配平,返回那段子串(含两端花括号);数不平返回 None。

    没有围栏(```json)时的退路。字符串内的花括号不计深度,`\\"` 不算引号结束。
    """
    i = text.find("{")
    if i < 0:
        return None
    depth, in_str, esc = 0, False, False
    for j in range(i, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return None


def parse_reply(content):
    """模型回复 -> (kind, name, args, say, reason)。纯函数,可单测。

    kind 四种,优先级固定 **TOOL > SAY > none**:
      tool        name/args 有效
      parse_fail  找到了 TOOL: 但参数块取不到或不是合法 JSON 对象;reason 说明原因
      say         没有 TOOL:,有 SAY:;say 是那句话
      none        两种块都没有(调用方走 nudge)
    `TOOL:` 取**最后一个**命中 —— 模型偶尔会先复述格式说明再给最终调用。
    """
    content = content or ""
    hits = list(TOOL_RE.finditer(content))
    if hits:
        m = hits[-1]
        name = m.group(1)
        tail = content[m.end():]
        fm = FENCE_RE.search(tail)
        blob = fm.group(1) if fm else brace_scan(tail)
        if blob is None:
            return "parse_fail", name, None, None, "no_json_block"
        try:
            args = json.loads(blob)
        except Exception as e:
            return "parse_fail", name, None, None, f"bad_json: {e}"
        if not isinstance(args, dict):
            return "parse_fail", name, None, None, "json_not_object"
        return "tool", name, args, None, None
    # SAY 与 TOOL 同口径:取**最后一个** `SAY:` 之后的内容。system 提示里逐字
    # 写着 `SAY: <what you say to the customer>`,模型复述它是已经防过的行为
    # (见上面 TOOL 那行注释);SAY 若取第一个,整段格式说明就会被当成对客户说的
    # 话,一路传给用户模拟器、写进 env 行的 said、再进评测器 —— 三处全错而没有
    # 任何计数器会响。
    # 注意这里**不能**照搬 TOOL 的 finditer[-1]:TOOL_RE 只捕一个词所以有多个
    # 命中,而 SAY_RE 在 re.S 下 `(.+)` 是贪婪的,第一个 SAY: 就把后面整段(含
    # 后续 SAY:)一口吃掉,finditer 只有一个命中,取末位等于没取。实测验过。
    # 所以按标记位置从右边切。
    i = content.rfind(SAY_MARK)
    if i >= 0:
        say = content[i + len(SAY_MARK):].strip()
        if say:
            return "say", None, None, say, None
    return "none", None, None, None, "no_block"


# ---------- 规范化调用串 + 往返自检 ----------

def canon_action(domain, name, args):
    """-> `tau2.<domain>.<tool>(k=v, ...)`,值是 JSON 字面量。

    与 AW_CALL 的 `apis.<app>.<api>(` 同形,所以下游加分支只是照抄 appworld 那
    11 行,不用重新设计 label_call / 参数切分。
    """
    inner = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}"
                      for k, v in args.items())
    return f"tau2.{domain}.{name}({inner})"


def is_args_lossy(action, args):
    """往返自检:action 串再被 rules.first_call_named 切一遍,键序必须一模一样。

    切不回来 = 下游按 action 串重切参数时会静默错标签。**不抛异常**(不能因为一个
    怪参数丢整条轨迹),只返回 True 让调用方打标 + 计数。已实测两种真会翻车的值:
      - 值里含未配平 `(`(如 `calculate(expression="((1+2)")`)-> 切出 `[]`
      - 值里含奇数个转义 `\\"` -> 相邻两个键被并成一个
    两者 first_call_named 都不报错,所以这个函数是唯一的报警器。
    """
    named = first_call_named(action, TAU2_CALL) or []
    return [k for k, _ in named] != list(args.keys())


# ---------- tau2 依赖(延迟 import,与 run_appworld.py:61 同一路子) ----------

def load_tau2():
    from tau2.data_model.message import (AssistantMessage, ToolCall,
                                         ToolMessage, UserMessage)
    from tau2.data_model.simulation import SimulationRun, TerminationReason
    from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
    from tau2.registry import registry
    from tau2.user.user_simulator import UserSimulator
    return SimpleNamespace(
        AssistantMessage=AssistantMessage, ToolCall=ToolCall,
        ToolMessage=ToolMessage, UserMessage=UserMessage,
        SimulationRun=SimulationRun, TerminationReason=TerminationReason,
        EvaluationType=EvaluationType, evaluate_simulation=evaluate_simulation,
        registry=registry, UserSimulator=UserSimulator)


def build_system(env):
    """系统提示 = 官方 instructions + 官方 policy + 工具 schema + 我们的格式段。

    实测 airline:policy 7676 字符 + 14 个工具的 openai_schema 14623 字符,
    总计约 23k 字符 ≈ 6k token。
    """
    tools_json = json.dumps([t.openai_schema for t in env.get_tools()],
                            ensure_ascii=False, indent=1)
    return "\n".join([
        "<instructions>", AGENT_INSTRUCTION, "</instructions>",
        "<policy>", env.get_policy(), "</policy>",
        "<tools>", tools_json, "</tools>",
        "<reply_format>", REPLY_FORMAT, "</reply_format>",
    ])


def user_system_prompt(T, task):
    """用户模拟器的系统提示,逐字取自官方 UserSimulator.system_prompt。

    只读它的属性(纯属性、零 LLM 调用,实测 airline 约 2.6k 字符,含官方
    data/tau2/user_simulator/simulation_guidelines.md),**不走 tau2 的 LiteLLM
    通路** —— 那条要 litellm + 成本表,而且思考段拿不到我们要的口径。llm 传
    'dummy' 只是占位:system_prompt 的计算路径完全不看它。
    """
    us = T.UserSimulator(llm="dummy",
                         instructions=str(task.user_scenario.instructions))
    return us.system_prompt


def is_user_stop(text):
    return any(tok in (text or "") for tok in USER_STOP_TOKENS)


def basis_of(task):
    """task.evaluation_criteria.reward_basis -> ['DB', 'COMMUNICATE', ...]。"""
    crit = getattr(task, "evaluation_criteria", None)
    return [str(b).split(".")[-1] for b in (crit.reward_basis if crit else [])]


def fold_official(basis, breakdown, reward):
    """按 task 自己的 reward_basis 折出官方口径的分 -> (分, 是否完整, 缺哪些, 备注)。

    我们只跑 EvaluationType.ALL_IGNORE_BASIS(ENV+ACTION+COMMUNICATE,零 LLM),
    所以 breakdown 里**永远没有 NL_ASSERTION**。basis 里带 NL_ASSERTION 的题
    (retail 112/114)只能折出 DB 那一半,complete=False —— 这个数**不能叫 reward**。
    breakdown 为空 = RewardInfo 早退路径(evaluator.py:119-134:termination 不是
    AGENT_STOP/USER_STOP 直接给 0;没有 criteria 给 1),此时原样带出 reward 并
    标 incomplete + note,免得「聊到步数上限」被读成「做错了」。
    """
    if not breakdown:
        return reward, False, list(basis), \
            "no reward_breakdown (premature termination or no criteria)"
    official, miss = 1.0, []
    for b in basis:
        if b in breakdown:
            official *= float(breakdown[b])
        else:
            miss.append(b)
    return official, not miss, miss, None


# ---------- 主循环 ----------

def run_task(T, env, domain, task, chat, user_chat, args, out_path):
    """跑一题,落一个 jsonl,返回一行摘要字符串。

    硬不变量:**每个 step 恰好一条 gen + 一条 env,step 从 0 连续**。
    一旦某 step 有 gen 无 env,build.py:64-65 就会 break 掉整条轨迹的后续步。
    """
    t0 = time.time()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    unit = f"{domain}/{task.id}"

    # 环境初始状态。airline/retail 实测 initial_state 全为 None,但仍走通用路径
    # 传 task.initial_state 的三件套,留好扩展口。
    init = getattr(task, "initial_state", None)
    idata = getattr(init, "initialization_data", None) if init else None
    iacts = getattr(init, "initialization_actions", None) if init else None
    ihist = list(getattr(init, "message_history", None) or []) if init else []
    env.set_state(idata, iacts, list(ihist))

    # tau2 侧的消息序列(交给官方评测器)。必须**含 initial_state 的历史** ——
    # evaluator_env.py:27-39 的注释明说 full_trajectory 要带上它。
    tmsgs = list(ihist)
    tmsgs.append(T.AssistantMessage(role="assistant",
                                    content=FIRST_AGENT_MESSAGE))

    # 先跑一次用户轮,拿开场诉求。用户侧另维护一条 msgs,角色手工翻转:
    # agent 说的话进去当 'user',用户自己说的话当 'assistant'
    # 【照抄 envs/tau2-bench/src/tau2/user/user_simulator_base.py:62-90 的
    #  flip_roles 语义】。
    umsgs = [{"role": "system", "content": user_system_prompt(T, task)}]
    umsgs.append({"role": "user", "content": FIRST_AGENT_MESSAGE})
    ug = user_chat(umsgs)
    opening = (ug["content"] or "").strip()
    if not opening:
        # 空开场不是臆想的边界:common.py:62-63 明写"思考超长被截断:全部算思考,
        # 内容为空",全仓采集器共用那个 Chat。放任下去 meta.instruction 就是空串,
        # build.py:53 拼出来的每条样本第一行都是空的 `Task: `,题干信息整条丢光,
        # 而轨迹照样跑完、退出码 0、任何数字都看不出来。所以重试一次,仍空就掐掉。
        ug = user_chat(umsgs)
        opening = (ug["content"] or "").strip()
    if not opening:
        print(f"  SKIP {domain}/{task.id}: 用户模拟器两次都给出空开场,不落盘",
              flush=True)
        return None
    umsgs.append({"role": "assistant", "content": opening})
    tmsgs.append(T.UserMessage(role="user", content=opening))
    # 这条 user 记录要在 meta 之后写(build.py:50 直接 recs[0] 当 meta),
    # 所以先缓存,等 TrajLog 建好再落盘。
    pending_user = {"type": "user", "step": -1, "phase": "open", **ug}

    # instruction 取**开场诉求**,不是 user_scenario:build.py:53 把它原样拼进探针
    # 题干的 Task 行,而 user_scenario 里含 agent 从未见过的 known_info /
    # task_instructions,填进去就是信息泄漏(探针靠真值作弊,虚高且看不出来)。
    # 场景真值另存 user_scenario_hidden —— 故意不叫 task 也不叫 instruction,
    # 避开 build.py 的两个取值键。
    log = TrajLog(out_path, {
        "env": "tau2", "task_id": unit, "model": args.model,
        "instruction": opening, "domain": domain, "split": args.split,
        "exp": args.exp, "user_model": args.user_model, "seed": args.seed,
        "max_steps": args.max_steps, "max_errors": args.max_errors,
        "tau2_task_id": task.id,
        "user_scenario_hidden": str(task.user_scenario),
    })
    log.w(pending_user)

    msgs = [{"role": "system", "content": build_system(env)},
            {"role": "user", "content": opening}]

    n = dict(tool=0, say=0, bad_tool=0, parse_fail=0, args_lossy=0, env_error=0)
    term = T.TerminationReason.MAX_STEPS
    step = -1
    for step in range(args.max_steps):
        g = chat(msgs)
        log.w({"type": "gen", "step": step, **g})
        content = g["content"] or ""
        msgs.append({"role": "assistant", "content": content})
        kind, name, cargs, say, reason = parse_reply(content)

        if kind == "tool":
            action = canon_action(domain, name, cargs)
            lossy = is_args_lossy(action, cargs)
            n["args_lossy"] += int(lossy)
            known = name in {t.name for t in env.get_tools()}
            tc = T.ToolCall(id=f"call_{step}", name=name, arguments=cargs,
                            requestor="assistant")
            # 幻觉工具名仍然交给环境:它会返回 error=True 的 ToolMessage,
            # 回放时 environment.set_state 把未知工具当 no-op,评测不会崩。
            tm = env.get_response(tc)
            n["tool"] += 1
            n["env_error"] += int(bool(tm.error))
            rec = {"type": "env", "step": step,
                   "action": action if known else None,
                   "result": (tm.content or "")[:RESULT_CAP],
                   "error": bool(tm.error),
                   "tool_name": name, "tool_args": cargs}
            if not known:
                # action=None 时 build.py:64-65 的 `if not action: continue` 会跳过
                # 该步,幻觉工具名进不了工具词表;写进 action 则词表被静默污染。
                n["bad_tool"] += 1
                rec["bad_tool"] = name
                rec["raw_call"] = action
            if lossy:
                rec["args_lossy"] = True
            log.w(rec)
            # 交给评测器的这条 content 必须是 None(与官方 LLMAgent 一致):把
            # 模型的思考文本填进去,CommunicateEvaluator 会在里面找到 required
            # info 而给分,COMMUNICATE 分量会被思考文本刷高。
            tmsgs.append(T.AssistantMessage(role="assistant", content=None,
                                            tool_calls=[tc]))
            tmsgs.append(tm)
            msgs.append({"role": "user",
                         "content": f"Tool result:\n{(tm.content or '')[:RESULT_CAP]}"})
            if n["env_error"] >= args.max_errors:
                term = T.TerminationReason.TOO_MANY_ERRORS
                break
            continue

        if kind == "say":
            n["say"] += 1
            tmsgs.append(T.AssistantMessage(role="assistant", content=say))
            umsgs.append({"role": "user", "content": say})
            ug = user_chat(umsgs)
            ureply = (ug["content"] or "").strip()
            umsgs.append({"role": "assistant", "content": ureply})
            tmsgs.append(T.UserMessage(role="user", content=ureply))
            log.w({"type": "user", "step": step, "phase": "reply", **ug})
            # action=None:SAY 轮不是工具调用,不产生探针事件(偏差第 5 条)。
            log.w({"type": "env", "step": step, "action": None,
                   "said": say, "result": ureply})
            msgs.append({"role": "user", "content": ureply})
            if is_user_stop(ureply):
                term = T.TerminationReason.USER_STOP
                break
            continue

        # parse_fail / none:也必须补一条 env(否则整条轨迹的后续步被 build.py 掐掉)
        # 【照抄 envs/collect/run_alfworld.py:211-223 的 nudge 路】
        if kind == "parse_fail":
            n["parse_fail"] += 1
            log.w({"type": "env", "step": step, "action": None,
                   "result": "PARSE_FAIL", "parse_reason": reason,
                   "tool_name": name})
            nudge = ("Your tool arguments could not be parsed "
                     f"({reason}). Send the block again: a line "
                     "`TOOL: <tool_name>` followed by one fenced ```json "
                     "object of valid JSON arguments.")
        else:
            log.w({"type": "env", "step": step, "action": None,
                   "result": "NO_ACTION", "parse_reason": reason})
            nudge = ("No block found. End your reply with exactly one block: "
                     "either `SAY: <one line>` or `TOOL: <tool_name>` followed "
                     "by one fenced ```json object of arguments.")
        msgs.append({"role": "user", "content": nudge})

    end_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    for i, m in enumerate(tmsgs):
        m.turn_idx = i

    # 官方评测。id 不用 uuid —— 工程铁律要求重跑逐样本一致。
    sim = T.SimulationRun(
        id=f"{args.exp}__{domain}__{task.id}", task_id=task.id,
        start_time=start_iso, end_time=end_iso,
        duration=round(time.time() - t0, 2),
        termination_reason=term, messages=tmsgs, seed=args.seed)
    ev, reward, eval_error = None, None, None
    try:
        ri = T.evaluate_simulation(sim, task, T.EvaluationType.ALL_IGNORE_BASIS,
                                   solo_mode=False, domain=domain)
        # **必须 model_dump(mode="json")**:reward_breakdown 的键是 RewardType
        # 枚举,直接 json.dumps 抛 TypeError -> final 行写不出来 -> `--resume`
        # 认的 `"type": "final"` 永远不出现 -> 这道题每次重跑都从头再采,采不完。
        ev = ri.model_dump(mode="json")
        reward = ri.reward
    except Exception as e:              # 评测失败不弃轨迹
        # ALL_IGNORE_BASIS 分支调 EnvEvaluator 时没传 strict_replay=False
        # (evaluator.py:279-285),回放时工具输出与录下来的不一致就抛。
        eval_error = f"eval_error: {type(e).__name__}: {e}"

    basis = basis_of(task)
    official, complete, miss, note = None, False, list(basis), "eval failed"
    if ev is not None:
        official, complete, miss, note = fold_official(
            basis, ev.get("reward_breakdown") or {}, reward)

    fin = {"type": "final", "steps": step + 1, "termination": term.value,
           "reward": reward, "reward_basis": basis,
           "reward_breakdown": (ev or {}).get("reward_breakdown"),
           "official_reward": official,
           "official_reward_complete": complete,
           "official_reward_missing": miss,
           "n_tool": n["tool"], "n_say": n["say"],
           "n_bad_tool": n["bad_tool"], "n_parse_fail": n["parse_fail"],
           "n_args_lossy": n["args_lossy"], "n_env_error": n["env_error"],
           "eval": ev}
    if note:
        fin["official_reward_note"] = note
    if eval_error:
        fin["eval_error"] = eval_error
    log.w(fin)
    log.close()
    return (f"task={unit} steps={step + 1} term={term.value} "
            f"reward={reward} official={official}"
            f"{'' if complete else '(incomplete)'} "
            f"tool={n['tool']} say={n['say']} bad={n['bad_tool']} "
            f"pf={n['parse_fail']} lossy={n['args_lossy']} "
            f"err={n['env_error']}"
            + (f" {eval_error}" if eval_error else ""))


# ---------- 自测(纯 CPU:不发 HTTP、不碰显卡) ----------

class _ScriptedChat:
    """测试替身,**只在 --selftest 里用**:按顺序吐罐头回复,签名与 common.Chat 同。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.i = 0

    def __call__(self, messages, tries=4):
        assert self.i < len(self.replies), "罐头回复用光了(脚本与循环步数不匹配)"
        r = self.replies[self.i]
        self.i += 1
        return {"reasoning": "scripted reasoning, long enough to pass the "
                             "MIN_THINK=40 character gate in rules.py.",
                "content": r, "raw": None,
                "usage": {"in": 0, "out": 0}, "wall_s": 0.0}


def selftest():
    ok, tot = 0, 0

    def chk(cond, what):
        nonlocal ok, tot
        tot += 1
        if cond:
            ok += 1
        else:
            print(f"FAIL: {what}", flush=True)
        return cond

    # (1) parse_reply:8 条罐头回复
    cases = [
        ("正常 TOOL",
         'reasoning...\nTOOL: get_user_details\n```json\n{"user_id": "mia_li_3668"}\n```',
         ("tool", "get_user_details", {"user_id": "mia_li_3668"})),
        ("无围栏 JSON",
         'thinking\nTOOL: list_all_airports\n{}',
         ("tool", "list_all_airports", {})),
        ("SAY",
         'I should confirm first.\nSAY: Sure, may I have your user id?',
         ("say", None, None)),
        ("TOOL 前有复述",
         'The format is TOOL: some_tool then json. So:\n'
         'TOOL: get_reservation_details\n```json\n{"reservation_id": "EHGLP3"}\n```',
         ("tool", "get_reservation_details", {"reservation_id": "EHGLP3"})),
        ("JSON 坏",
         'TOOL: calculate\n```json\n{"expression": }\n```',
         ("parse_fail", "calculate", None)),
        ("什么都没有", 'I am thinking about the policy.', ("none", None, None)),
        ("TOOL 名不存在(解析仍成功,闸门在主循环)",
         'TOOL: totally_made_up\n```json\n{"a": 1}\n```',
         ("tool", "totally_made_up", {"a": 1})),
        ("参数值含未配平括号",
         'TOOL: calculate\n```json\n{"expression": "((1+2)"}\n```',
         ("tool", "calculate", {"expression": "((1+2)"})),
    ]
    for label, reply, want in cases:
        kind, name, cargs, _say, _r = parse_reply(reply)
        got = (kind, name, cargs) if kind != "say" else (kind, None, None)
        chk(got == want, f"parse_reply[{label}] got={got} want={want}")

    # (2) canon_action 往返自检:6 个真实形状键序全对,2 个已知翻车形状报警器要响
    good = [
        ("airline", "get_user_details", {"user_id": "mia_li_3668"}),
        ("airline", "list_all_airports", {}),
        ("airline", "book_reservation", {
            "user_id": "mia_li_3668", "origin": "SFO", "destination": "JFK",
            "flight_type": "one_way", "cabin": "business",
            "flights": [{"flight_number": "HAT001", "date": "2024-05-20"}],
            "passengers": [{"first_name": "Mia", "last_name": "Li",
                            "dob": "1990-04-05"}],
            "payment_methods": [{"payment_id": "credit_card_4421486",
                                 "amount": 1234.5}],
            "total_baggages": 2, "nonfree_baggages": 0, "insurance": "no"}),
        ("airline", "calculate", {"expression": "(100 + 200) * 3"}),
        ("retail", "modify_pending_order_items", {
            "order_id": "#W0000000", "item_ids": ["1", "2"],
            "new_item_ids": ["3", "4"], "payment_method_id": None}),
        ("retail", "f", {"a": True, "b": 1.5, "c": "value, with comma"}),
    ]
    for domain, name, cargs in good:
        act = canon_action(domain, name, cargs)
        named = first_call_named(act, TAU2_CALL) or []
        chk([k for k, _ in named] == list(cargs.keys()),
            f"roundtrip[{name}] keys={[k for k, _ in named]}")
        chk(not is_args_lossy(act, cargs), f"not lossy[{name}]")
    bad = [
        ("airline", "calculate", {"expression": "((1+2)", "x": "z"}),
        ("retail", "f", {"q": 'say "hi', "r": "z"}),
    ]
    for domain, name, cargs in bad:
        act = canon_action(domain, name, cargs)
        chk(is_args_lossy(act, cargs),
            f"lossy 报警器要响[{name}] {act}")

    # (3) fold_official:三种口径
    o, c, m, nt = fold_official(["DB", "COMMUNICATE"],
                               {"DB": 1.0, "ACTION": 0.0, "COMMUNICATE": 1.0},
                               0.0)
    chk((o, c, m, nt) == (1.0, True, [], None),
        f"fold[airline 口径] {(o, c, m, nt)}")
    o, c, m, nt = fold_official(["DB", "NL_ASSERTION"],
                               {"DB": 1.0, "ACTION": 1.0, "COMMUNICATE": 1.0},
                               1.0)
    chk((o, c, m) == (1.0, False, ["NL_ASSERTION"]),
        f"fold[retail 口径:NL 未评 -> incomplete] {(o, c, m)}")
    o, c, m, nt = fold_official(["DB", "COMMUNICATE"], {}, 0.0)
    chk((o, c) == (0.0, False) and nt, f"fold[早退路径带 note] {(o, c, nt)}")

    # (4) 真跑一集 airline task '1':真环境 + 真官方评测器,只有两个 LLM 是替身
    T = load_tau2()
    domain = "airline"
    env = T.registry.get_env_constructor(domain)()
    chk(env.user_tools is None, "airline 没有用户侧工具")
    tasks = T.registry.get_tasks_loader(domain)("base")
    task = next((t for t in tasks if t.id == "1"), None)
    chk(task is not None, "airline base 里有 task id '1'")

    agent_script = [
        "Let me think about what the customer needs before doing anything.",
        'I need the airport list.\nTOOL: list_all_airports\n```json\n{}\n```',
        'Try a tool that does not exist.\nTOOL: totally_made_up\n'
        '```json\n{"a": 1}\n```',
        'Compute something with an unbalanced paren in the value.\n'
        'TOOL: calculate\n```json\n{"expression": "((1+2)"}\n```',
        'Broken arguments on purpose.\nTOOL: calculate\n```json\n'
        '{"expression": }\n```',
        'I will just talk to the customer now.\n'
        'SAY: I am sorry, I cannot help with that. Anything else?',
    ]
    user_script = [
        "Hi, I want to check something about my reservation.",
        "No, that is all. ###STOP###",
    ]
    args = SimpleNamespace(
        model="scripted-agent", user_model="scripted-user", split="base",
        exp="selftest", seed=SEED, max_steps=8,
        max_errors=DEFAULT_MAX_ERRORS)
    # 用系统临时目录,别钉任何会话私有路径 —— 钉了就换个会话 100% FileNotFoundError,
    # 而挂掉的原因跟采集逻辑毫无关系,读日志的人会以为代码坏了
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / f"tau2_{escape_unit(f'{domain}/{task.id}')}.jsonl"
        line = run_task(T, env, domain, task, _ScriptedChat(agent_script),
                        _ScriptedChat(user_script), args, out_path)
        print("  scripted run:", line, flush=True)

        # (5) 读回来断言结构
        raw = out_path.read_text()
        # 这一条守的是 reward_breakdown 的 RewardType 枚举键:直接 json.dumps 会抛
        # TypeError 把 final 行打掉,而 --resume 认的就是这个串,于是该题永远采不完。
        chk('"type": "final"' in raw,
            "--resume 认的 `\"type\": \"final\"` 标记真的落在文件里")
        recs = [json.loads(l) for l in open(out_path)]
        chk(recs[0]["type"] == "meta" and recs[0]["task_id"] == "airline/1",
            f"首行 meta + task_id 带域前缀: {recs[0].get('task_id')}")
        chk(recs[0]["instruction"] == user_script[0],
            "instruction = 开场诉求(不是 user_scenario)")
        chk("user_scenario_hidden" in recs[0]
            and "task" not in recs[0], "场景真值另存,不占 build.py 的取值键")
        chk(recs[-1]["type"] == "final", "末行 final")
        gens = [r["step"] for r in recs if r["type"] == "gen"]
        envs = [r["step"] for r in recs if r["type"] == "env"]
        chk(gens == list(range(len(agent_script))), f"gen step 连续: {gens}")
        chk(envs == gens, f"每 step 恰好一条 env: {envs}")
        fin = recs[-1]
        chk(fin["termination"] == "user_stop",
            f"termination=user_stop 实得 {fin['termination']}")
        chk(fin["n_bad_tool"] == 1, f"n_bad_tool=1 实得 {fin['n_bad_tool']}")
        chk(fin["n_parse_fail"] == 1,
            f"n_parse_fail=1 实得 {fin['n_parse_fail']}")
        chk(fin["n_args_lossy"] == 1,
            f"n_args_lossy=1 实得 {fin['n_args_lossy']}")
        chk(fin["n_say"] == 1, f"n_say=1 实得 {fin['n_say']}")
        chk("eval_error" not in fin,
            f"官方评测跑通: {fin.get('eval_error')}")
        chk(fin["reward"] is not None, "reward 有值")
        chk(fin["official_reward_complete"] is True,
            f"airline basis 全可离线评: miss={fin['official_reward_missing']}")
        # action 能被 TAU2_CALL + first_call_named 切出正确键
        acts = [r for r in recs if r["type"] == "env" and r.get("action")]
        chk(len(acts) >= 1, "至少一条 env 带 action")
        hit = 0
        for r in acts:
            named = first_call_named(r["action"], TAU2_CALL) or []
            if [k for k, _ in named] == list(r["tool_args"].keys()):
                hit += 1
        chk(hit >= 1, f"至少一条 action 键序切得对({hit}/{len(acts)})")
        # 幻觉工具名不进 action(否则污染工具词表)
        bt = [r for r in recs if r["type"] == "env" and r.get("bad_tool")]
        chk(len(bt) == 1 and bt[0]["action"] is None and bt[0]["raw_call"],
            "幻觉工具: action=None + raw_call 留串")
        # 用户模拟器的内容只在 type='user' 行里,不在任何 gen 行里
        us = [r for r in recs if r["type"] == "user"]
        chk(len(us) == 2, f"两条 user 记录(开场 + 一次回复),实得 {len(us)}")

    # (6) retail 侧:环境能离线建、没有用户侧工具、112/114 题的 basis 带 NL_ASSERTION
    renv = T.registry.get_env_constructor("retail")()
    chk(renv.user_tools is None, "retail 没有用户侧工具")
    rtasks = T.registry.get_tasks_loader("retail")("base")
    nl = sum(1 for t in rtasks if "NL_ASSERTION" in basis_of(t))
    chk((len(rtasks), nl) == (114, 112),
        f"retail base 114 题、其中 112 题 basis 含 NL_ASSERTION,实得 "
        f"{(len(rtasks), nl)}")
    rt = next(t for t in rtasks if "NL_ASSERTION" in basis_of(t))
    _o, c, m, _n = fold_official(basis_of(rt),
                                 {"DB": 1.0, "ACTION": 1.0, "COMMUNICATE": 1.0},
                                 1.0)
    chk(c is False and m == ["NL_ASSERTION"],
        f"retail 真题折出来必须 incomplete: complete={c} miss={m}")

    # (7) 分片切分:先 --n 截断再取模,三片无交无漏
    ids = [t.id for t in rtasks][:10]
    shards = [ids[i::3] for i in range(3)]
    flat = [x for s in shards for x in s]
    chk(sorted(flat) == sorted(ids) and len(set(flat)) == len(ids),
        f"分片无交无漏: {shards}")

    print(f"SELFTEST {'PASS' if ok == tot else 'FAIL'} {ok}/{tot}", flush=True)
    if ok != tot:
        sys.exit(1)


# ---------- 入口 ----------

def main():
    ap = argparse.ArgumentParser()
    # 骨架逐字照抄 envs/collect/run_alfworld.py:131-147
    ap.add_argument("--base-url")
    ap.add_argument("--model")
    ap.add_argument("--split", default="test")
    ap.add_argument("--n", type=int, default=1, help="0 = 整个 split")
    ap.add_argument("--max-steps", type=int, default=40,
                    help="agent 生成轮数上限。官方 DEFAULT_MAX_STEPS=200 "
                         "(tau2/config.py:4)且一次工具往返算 2 步,这里的 40 "
                         "只数 agent 轮 —— 改这个值会改 termination 分布")
    ap.add_argument("--outdir")
    ap.add_argument("--exp", default="smoke")
    ap.add_argument("--api", default="raw", choices=["raw", "chat"])
    ap.add_argument("--reasoning-effort", default=None)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--resume", action="store_true",
                    help="跳过 outdir 里已写完的题")
    # tau2 专属
    ap.add_argument("--domain", default="airline", choices=DOMAINS)
    ap.add_argument("--user-base-url", default=None, help="缺省 = --base-url")
    ap.add_argument("--user-model", default=None, help="缺省 = --model")
    ap.add_argument("--user-api", default=None, choices=["raw", "chat"],
                    help="缺省 = --api")
    ap.add_argument("--max-errors", type=int, default=DEFAULT_MAX_ERRORS,
                    help="工具报错上限,与 tau2/config.py:5 同值")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--selftest", action="store_true",
                    help="纯 CPU 自测:不发 HTTP、不碰显卡")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    # --base-url/--model 不用 argparse 的 required=True,这样 --selftest 不必喂假 URL
    for flag in ("base_url", "model", "outdir"):
        if not getattr(args, flag):
            raise SystemExit(f"缺 --{flag.replace('_', '-')}(非 --selftest 必填)")
    args.user_base_url = args.user_base_url or args.base_url
    args.user_model = args.user_model or args.model
    args.user_api = args.user_api or args.api
    if args.user_model == args.model and args.user_base_url == args.base_url:
        print("WARN 用户模拟器与 agent 用同一个服务同一个模型 —— 自说自话是混淆项,"
              "轨迹分布会偏,而且这件事在任何数字里都看不出来。"
              "tau2 官方 smoke 用 q35 agent + q36 user。", flush=True)

    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    # 目录名闸门(extending.md §5 #1):build.py:45-47 按 `<env>_<model_key>` 认目录,
    # 尾巴不在 rules.MODEL_OF 里就 continue 掉**整个目录**,退 0、不提示;
    # glob 也写死 `tau2_*/tau2_*.jsonl`。两条都只能警告(smoke 目录本来就不入 annotate),
    # 但必须把后果印出来,不能静默。
    tail = outdir.name.rsplit("_", 1)[-1]
    if tail not in MODEL_OF:
        print(f"WARN outdir 尾巴 {tail!r} 不在 rules.MODEL_OF {sorted(MODEL_OF)} 里 "
              f"—— annotate 会静默跳过整个目录 {outdir.name}/(退 0、无提示)",
              flush=True)
    if not outdir.name.startswith("tau2_"):
        print(f"WARN outdir 名 {outdir.name!r} 不以 tau2_ 开头 —— "
              f"build.py 的 glob `tau2_*/tau2_*.jsonl` 扫不到它", flush=True)

    T = load_tau2()
    splits = T.registry.get_task_splits_loader(args.domain)()
    if args.split not in splits:
        raise SystemExit(f"--split {args.split} 不合法,{args.domain} 只有 "
                         f"{sorted(splits)}(注意:**没有 val**)")
    tasks = T.registry.get_tasks_loader(args.domain)(args.split)
    for t in tasks:
        if not ID_RE.fullmatch(t.id):
            raise SystemExit(f"task id 不能当文件名: {t.id!r}")

    chat = Chat(args.base_url, args.model, api=args.api,
                reasoning_effort=args.reasoning_effort)
    user_chat = Chat(args.user_base_url, args.user_model, api=args.user_api,
                     reasoning_effort=args.reasoning_effort)

    # 分片:先 --n 截断再取模【照抄 envs/collect/run_alfworld.py:158-160】。
    # 任务顺序 = get_tasks_loader 的返回序(tasks.json 文件序,跨机确定),
    # 不 shuffle、不排序 —— 与 appworld 一致。
    if args.n:
        tasks = tasks[: args.n]
    tasks = tasks[args.shard_id:: args.num_shards]
    print(f"shard {args.shard_id}/{args.num_shards}: {len(tasks)} tasks "
          f"domain={args.domain} split={args.split} exp={args.exp}", flush=True)

    for task in tasks:
        unit = f"{args.domain}/{task.id}"
        out_path = outdir / f"tau2_{escape_unit(unit)}.jsonl"
        if args.resume and out_path.exists() and \
                '"type": "final"' in out_path.read_text():
            print(f"task={unit} SKIP (done)", flush=True)
            continue
        # 每题新建一个环境实例(实测 airline 0.09s / retail 0.03s)
        env = T.registry.get_env_constructor(args.domain)()
        if env.user_tools is not None:
            raise SystemExit(
                f"{args.domain} 有用户侧工具 —— 本采集器只记 agent 侧调用,"
                f"会静默漏掉用户侧调用,拒绝跑")
        # None = 该题被掐掉了(空开场,已在 run_task 里打过 SKIP 行)。不落盘,
        # 所以 --resume 下次还会重试它 —— 是"没采到"而不是"静默当采过了"。
        line = run_task(T, env, args.domain, task, chat, user_chat, args,
                        out_path)
        if line is not None:
            print(line, flush=True)


if __name__ == "__main__":
    main()
