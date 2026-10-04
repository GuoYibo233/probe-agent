"""The tau2-bench benchmark (airline, retail, telecom): a customer-service conversation run by tau2's own orchestrator, its user simulator answering on the agent model's server, the agent's tool calls written as text, one call speculated early on a copy of the domain's world, and tau2's own reward as the judgment."""
from __future__ import annotations

import ast
import copy
import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import yaml

from data.environments import Environment, StepObservation

# The part of the developer message that is ours: tau2's own agent prompt (its AGENT_INSTRUCTION
# and the domain policy, in its SYSTEM_PROMPT) comes first, word for word, and this text follows
# it, because the official agent hands its tools to the model through the API's function calling
# while this loop reads tool calls out of the reply text. The format sentences are BFCL's
# prompting-mode ones word for word (its "classic" style, Python calls in a list), followed by
# what replaces the placeholders and one example, and {tools} is replaced by the domain's tool
# schemas, one JSON object per tool, the way BFCL's prompting mode lists its functions. Two
# softer single-call wordings failed in the 2026-10-05 debug runs: the Qwen3.6 agent answered
# in its native <tool_call> markup, then wrapped each call as func_name(get_user_details(...)).
INSTRUCTIONS = {"v1": """<tool_call_format>
If you decide to invoke any of the function(s), you MUST put it in the format of [func_name1(params_name1=params_value1, params_name2=params_value2...), func_name2(params)] You SHOULD NOT include any other text in the response.
Write the function's own name in place of func_name and its parameter names in place of params_name, and give each value as a JSON value (a string in double quotes, a number, true, false, null, a list or an object). For example, a function get_weather with the parameters city and days is invoked as [get_weather(city="Paris", days=3)]. A reply that is not in this format is sent to the user as your message.
The result of a tool call comes back to you as a list of {'role': 'tool', 'name': <the call>, 'content': <its output>}.
</tool_call_format>
<tools>
Here is a list of functions in JSON format that you can invoke.
{tools}
</tools>"""}
SPLIT_ROLE = {"airline_train": "train", "airline_test": "test",
              "retail_train": "train", "retail_test": "test",
              "telecom_train": "train", "telecom_test": "test"}

# A task id here is "<domain>_<tau2 task id>": the domain names carry no underscore, tau2's ids
# may, so the id splits on its first underscore.
DOMAINS = ("airline", "retail", "telecom")
# The name this module registers its agent under in tau2's registry: the agent that returns the
# loop's reply as its own message.
AGENT_NAME = "new1_loop_agent"
# The name of tau2's user simulator as registered here (VisibleReplyUserSimulator in _load), and
# the tag that closes a reasoning model's thinking in a reply text.
USER_NAME = "new1_visible_reply_user_simulator"
THINK_END = "</think>"
# tau2's user simulator talks to the agent model's own server through litellm's OpenAI-compatible
# provider; the temperature is tau2's own default for the user (DEFAULT_LLM_TEMPERATURE_USER).
USER_PROVIDER = "openai"
USER_TEMPERATURE = 0.0
# The judge of a task that carries NL assertions (40 of retail's 114 train and test tasks; no
# airline or telecom task has any): tau2's default is gpt-4.1 at temperature 0
# (DEFAULT_LLM_NL_ASSERTIONS), a paid model; here it is the agent model on its own server at the
# same temperature, asked for a JSON object because the evaluator reads the reply with json.loads.
NL_JUDGE_TEMPERATURE = 0.0
# The tool that hands the conversation to a human agent. tau2 types it GENERIC, as it changes no
# database, but no undo takes the hand-off back, so it is never tried early.
HANDOFF_TOOL = "transfer_to_human_agents"
# A bare name followed by "(": where a written call starts.
CALL_START = r"(?<![\w.])[A-Za-z_]\w*\("
# A reply that is one fenced block, ```json ... ``` or ``` ... ```, counts as its inside.
FENCE = r"^```[\w-]*\s*\n?(.*?)\n?```$"
JSON_NAMES = {"true": True, "false": False, "null": None}
# tau2.utils.llm_utils's two functions that price an LLM call.
COST_LOG_FUNCTIONS = ("get_response_cost", "get_cost")
# The official harness shows a tool's output whole; this cap is about the agent model's context
# in characters, so it cuts nothing a task produces and generation.result_cap can still lower it.
CUT_NOTE = "\n[output cut: {n} more characters not shown]"


def _unfenced(text: str) -> str:
    """The text with surrounding whitespace off, and the inside of one fenced block when the whole text is that block."""
    s = (text or "").strip()
    m = re.match(FENCE, s, re.S)
    return m.group(1).strip() if m else s


def _call_close(text: str, start: int) -> int | None:
    """Index of the `)` closing the call whose `(` is at `start`; None when it never closes.

    Python source rules, so a parenthesis inside a string literal is left alone: inside a
    literal only its closing quote counts (single, double and triple quoted), and a backslash
    escapes the next character.
    """
    i, depth = start, 0
    quote: str | None = None
    while i < len(text):
        c = text[i]
        if quote is not None:
            if c == "\\":
                i += 2
                continue
            if text.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if c in "\"'":
            quote = c * 3 if text.startswith(c * 3, i) else c
            i += len(quote)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _calls(text: str) -> list[ast.Call] | None:
    """The calls a reply is made of: one call, or a list or tuple of calls, each to a bare name, and nothing else; None for every other text."""
    try:
        body = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    nodes = body.elts if isinstance(body, (ast.List, ast.Tuple)) else [body]
    if not nodes:
        return None
    for node in nodes:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            return None
    return nodes


def _value(node: ast.AST):
    """The JSON value an argument node writes: a Python literal, with JSON's true, false and null read too; ValueError for anything that is no literal."""
    if isinstance(node, ast.Name) and node.id in JSON_NAMES:
        return JSON_NAMES[node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_value(e) for e in node.elts]
    if isinstance(node, ast.Dict):
        if any(k is None for k in node.keys):
            raise ValueError("a ** splat in an object")
        return {_value(k): _value(v) for k, v in zip(node.keys, node.values)}
    return ast.literal_eval(node)


def _canonical(node: ast.AST, source: str) -> str:
    """One text per value, so the same value written two ways reads the same: the compact JSON of a literal, else the value's own source text."""
    try:
        return json.dumps(_value(node), ensure_ascii=False)
    except (ValueError, TypeError, SyntaxError):
        return ast.get_source_segment(source, node)


def _args(call: ast.Call, source: str) -> list[tuple[str, str]]:
    """A call's arguments as (name, canonical value) pairs, positional ones named pos0, pos1, ... in order."""
    out = [(f"pos{i}", _canonical(a, source)) for i, a in enumerate(call.args)]
    out += [(k.arg if k.arg is not None else "**", _canonical(k.value, source)) for k in call.keywords]
    return out


def _tool_call_arguments(call: ast.Call) -> dict:
    """A call's arguments as tau2 takes them, a name -> value object; ValueError for a positional argument, a ** splat or a value that is no JSON value."""
    if call.args:
        raise ValueError(f"{call.func.id}: positional arguments; tau2 tools take named arguments only")
    out = {}
    for k in call.keywords:
        if k.arg is None:
            raise ValueError(f"{call.func.id}: a ** splat")
        out[k.arg] = _value(k.value)
    return out


def _char_offset(source: str, lineno: int, col_offset: int) -> int:
    """The character index in `source` of an ast position (1-based line, UTF-8 byte column)."""
    lines = source.splitlines(keepends=True)
    head = sum(len(line) for line in lines[:lineno - 1])
    return head + len(lines[lineno - 1].encode()[:col_offset].decode())


# tau2's classes, imported once per process inside the benchmark's own interpreter (_load).
_TAU2: dict = {}


def _load(data_root: str) -> SimpleNamespace:
    """Import tau2 (its data root set first, litellm kept on its local price table, tau2's step logs kept off the piece log) and register the loop's agent once; return the names this module uses."""
    if "t" in _TAU2:
        return _TAU2["t"]
    os.environ["TAU2_DATA_DIR"] = data_root
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    # Every model call of this benchmark goes to the agent model's own server with an explicit
    # key (the user simulator and the NL-assertion judge); this process holds no paid
    # provider's key, so a tau2 default that names a paid model fails instead of being billed.
    for name in [k for k in os.environ if k.endswith("_API_KEY")]:
        del os.environ[name]
    from loguru import logger
    logger.remove()
    # tau2 prices every LLM call through litellm's table, which has no row for a model served
    # here, so each user turn would log an error and a warning about the price; those two
    # cost-accounting functions stay out of the piece log, every other warning goes in.
    logger.add(sys.stderr, level="WARNING",
               filter=lambda record: record["function"] not in COST_LOG_FUNCTIONS)

    from tau2.agent.base_agent import HalfDuplexAgent
    from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT
    from tau2.data_model.message import AssistantMessage, MultiToolMessage, ToolCall
    from tau2.data_model.simulation import TerminationReason, TextRunConfig
    from tau2.environment.toolkit import ToolType
    from tau2.evaluator import evaluator_nl_assertions
    from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
    from tau2.metrics.agent_metrics import is_successful
    from tau2.orchestrator.orchestrator import Role
    from tau2.registry import registry
    from tau2.runner.build import _build_env_kwargs, build_text_orchestrator
    from tau2.user.user_simulator import UserSimulator
    from tau2.utils.utils import get_now

    class LoopAgent(HalfDuplexAgent):
        """tau2's agent seat, filled by the loop: each turn it returns the message the loop's agent model wrote, which `Tau2.step` hands it before the orchestrator asks."""

        def __init__(self, tools, domain_policy):
            super().__init__(tools=tools, domain_policy=domain_policy)
            self.pending = None

        def get_init_state(self, message_history=None):
            return None

        def generate_next_message(self, message, state):
            if self.pending is None:
                raise RuntimeError("tau2: the orchestrator asked the agent for a turn the loop has not written")
            out, self.pending = self.pending, None
            return out, state

        def set_seed(self, seed):
            """The agent model's sampling seed is the loop's own; tau2's seed reaches the user simulator only."""
            del seed

    def loop_agent_factory(tools, domain_policy, **kwargs):
        del kwargs
        return LoopAgent(tools, domain_policy)

    class VisibleReplyUserSimulator(UserSimulator):
        """tau2's user simulator, whose message is the text after the model's closing think tag.

        A reasoning model served without a reasoning parser (the Qwen rows) returns its thinking
        and its answer as one text, and the thinking quotes the user's hidden scenario; the
        message the agent reads is the answer alone, as a model served with a parser (gpt-oss)
        already returns it.
        """

        def _generate_next_message(self, message, state):
            user_message = super()._generate_next_message(message, state)
            if user_message.content is not None and THINK_END in user_message.content:
                user_message.content = user_message.content.rsplit(THINK_END, 1)[1].strip()
            return user_message

    if registry.get_agent_factory(AGENT_NAME) is None:
        registry.register_agent_factory(loop_agent_factory, AGENT_NAME)
    if USER_NAME not in registry.get_users():
        registry.register_user(VisibleReplyUserSimulator, USER_NAME)

    _TAU2["t"] = SimpleNamespace(
        AGENT_INSTRUCTION=AGENT_INSTRUCTION, SYSTEM_PROMPT=SYSTEM_PROMPT,
        AssistantMessage=AssistantMessage, MultiToolMessage=MultiToolMessage, ToolCall=ToolCall,
        TerminationReason=TerminationReason, TextRunConfig=TextRunConfig, ToolType=ToolType,
        EvaluationType=EvaluationType, evaluate_simulation=evaluate_simulation,
        evaluator_nl_assertions=evaluator_nl_assertions,
        is_successful=is_successful, Role=Role, registry=registry,
        build_env_kwargs=_build_env_kwargs, build_text_orchestrator=build_text_orchestrator,
        get_now=get_now,
    )
    return _TAU2["t"]


class Tau2(Environment):
    """tau2-bench in half-duplex text mode: tau2's orchestrator, environment, user simulator and evaluator, with the agent's turns written by this loop."""

    NAME = "tau2"
    INSTRUCTIONS = INSTRUCTIONS
    # What the agent model is told after a reply this loop could not read (an empty reply, or a
    # call whose arguments are not named JSON values); the conversation does not move.
    NO_CODE_MESSAGE = ("That reply was not read. A tool call is written as [func_name(params_name=params_value, ...)] "
                       "with the function's own name in place of func_name, every argument given by its parameter name, "
                       "and every value a JSON value, for example [get_weather(city=\"Paris\", days=3)]; any other reply "
                       "is a message to the user. Reply with a tool call or a message to the user.")
    RESULT_CAP = 500000
    # The domain's world takes no seed: it is its database file; the user simulator, the one
    # sampled party, takes the loop's seed through tau2's Orchestrator(seed=...).
    SEED = 0
    SPLIT_ROLE = SPLIT_ROLE

    def __init__(self) -> None:
        path = Path(__file__).resolve().parents[2] / "constants" / "path_datasets.yaml"
        with open(path) as f:
            block = yaml.safe_load(f)["tau2"]
        self.home = block["home"]
        # tau2's DATA_DIR: the domains are under <data>/tau2/domains/.
        self.data = block["data"]
        self.splits = block["splits"]
        if self.data != f"{self.home}/data":
            raise ValueError(f"tau2: constants/path_datasets.yaml data {self.data!r} is not <home>/data")
        self._base_url: str | None = None
        self._served_model_name: str | None = None
        self._tasks_by_domain: dict[str, dict] = {}
        self._orch = None
        self._task = None
        self._domain: str | None = None
        self._env_kwargs: dict | None = None
        self._finalized = False
        self.task_text: str | None = None
        self.task_date: str | None = None

    # ---- the task lists, read without tau2 ----

    def tasks(self, split: str) -> list[str]:
        if split not in self.splits:
            raise ValueError(f"tau2.tasks: unknown split {split!r}, has {sorted(self.splits)}")
        domain, _, key = split.partition("_")
        ids = json.loads(Path(self.splits[split]).read_text())[key]
        return [f"{domain}_{tau2_id}" for tau2_id in ids]

    # ---- call syntax, read without tau2 ----

    def split_args(self, text: str) -> tuple[str, list[tuple[str, str]], tuple[int, int]] | None:
        source = _unfenced(text)
        calls = _calls(source)
        if calls is None:
            return None
        first = calls[0]
        start = (text or "").find(source)
        span = (start + _char_offset(source, first.lineno, first.col_offset),
                start + _char_offset(source, first.end_lineno, first.end_col_offset))
        return first.func.id, _args(first, source), span

    def build_call(self, tool: str, args: list[tuple[str, str]]) -> str:
        parts = [value if re.match(r"^pos\d+$", key) else f"{key}={value}" for key, value in args]
        call = f"{tool}({', '.join(parts)})"
        calls = _calls(call)
        if calls is None or len(calls) != 1:
            raise ValueError(f"tau2.build_call: {call!r} does not read back as one call")
        return call

    def complete_call(self, text: str) -> str | None:
        s = text or ""
        m = re.search(CALL_START, s)
        if m is None:
            return None
        j = _call_close(s, m.end() - 1)
        if j is None:
            return None
        return s[m.start():j + 1]

    # ---- the agent server, for the user simulator ----

    def bind_agent(self, base_url: str, served_model_name: str) -> None:
        self._base_url = base_url
        self._served_model_name = served_model_name

    # ---- one conversation ----

    def instructions(self, variant: str) -> str:
        if self._orch is None:
            raise RuntimeError("tau2.instructions: called before open")
        t = _load(self.data)
        env = self._orch.environment
        official = t.SYSTEM_PROMPT.format(agent_instruction=t.AGENT_INSTRUCTION, domain_policy=env.get_policy())
        tools = "\n".join(json.dumps(tool.openai_schema["function"], ensure_ascii=False) for tool in env.get_tools())
        return official + "\n\n" + self.INSTRUCTIONS[variant].replace("{tools}", tools)

    def open(self, task_id: str, seed: int) -> None:
        if self._base_url is None:
            raise RuntimeError("tau2.open: no agent server bound; the user simulator answers on it (bind_agent)")
        t = _load(self.data)
        domain, _, tau2_id = task_id.partition("_")
        if domain not in DOMAINS:
            raise ValueError(f"tau2.open: task id {task_id!r} names no domain of {DOMAINS}")
        if domain not in self._tasks_by_domain:
            self._tasks_by_domain[domain] = {
                task.id: task for task in t.registry.get_tasks_loader(domain)(task_split_name=None)}
        if tau2_id not in self._tasks_by_domain[domain]:
            raise ValueError(f"tau2.open: domain {domain!r} holds no task with id {tau2_id!r}")
        task = copy.deepcopy(self._tasks_by_domain[domain][tau2_id])
        config = t.TextRunConfig(
            domain=domain, agent=AGENT_NAME, user=USER_NAME,
            llm_user=f"{USER_PROVIDER}/{self._served_model_name}",
            llm_args_user={"temperature": USER_TEMPERATURE, "api_base": self._base_url, "api_key": "EMPTY"},
        )
        # tau2's evaluator reads its judge from these two module names at every call.
        t.evaluator_nl_assertions.DEFAULT_LLM_NL_ASSERTIONS = f"{USER_PROVIDER}/{self._served_model_name}"
        t.evaluator_nl_assertions.DEFAULT_LLM_NL_ASSERTIONS_ARGS = {
            "temperature": NL_JUDGE_TEMPERATURE, "api_base": self._base_url, "api_key": "EMPTY",
            "response_format": {"type": "json_object"}}
        orch = t.build_text_orchestrator(config, task, seed=seed)
        self._orch, self._task, self._domain = orch, task, domain
        self._env_kwargs = t.build_env_kwargs(config, task)
        self._finalized = False
        # Orchestrator.run's first lines, then its loop up to the first turn that is the agent's:
        # the agent's greeting goes to the user, and the user's first message is the task.
        orch._run_start_time = t.get_now()
        orch._run_start_perf = time.perf_counter()
        orch.initialize()
        self._advance()
        if orch.done:
            raise RuntimeError(f"tau2.open: the conversation of {task_id} ended before the agent's first turn "
                               f"({orch.termination_reason})")
        self.task_text = orch.message.content

    def _advance(self) -> None:
        """Step the orchestrator, checking its termination after every step as Orchestrator.run does, until the next turn is the agent's or the conversation is over."""
        t = _load(self.data)
        orch = self._orch
        while not orch.done and orch.to_role != t.Role.AGENT:
            orch.step()
            orch._check_termination()

    def _capped(self, out: str) -> str:
        """`out` whole when it fits RESULT_CAP characters, else its first RESULT_CAP characters and one line saying how many were left out."""
        if len(out) <= self.RESULT_CAP:
            return out
        return out[:self.RESULT_CAP] + CUT_NOTE.format(n=len(out) - self.RESULT_CAP)

    @staticmethod
    def _tool_results(calls_text: list[str], results: list) -> str:
        """Tool results as the agent reads them: BFCL's prompting form, one {'role': 'tool', 'name', 'content'} per call."""
        return repr([{"role": "tool", "name": c, "content": r.content} for c, r in zip(calls_text, results)])

    def step(self, reply_text: str) -> StepObservation:
        t = _load(self.data)
        orch = self._orch
        source = _unfenced(reply_text)
        calls = _calls(source)
        # A reply the text protocol cannot read reaches neither the user nor the world: like
        # AppWorld's reply without a code block, it gets NO_CODE_MESSAGE (action None) and the
        # agent's turn is asked again; the official agent, whose calls come out of the API's
        # function calling, has no such reply.
        if source == "":
            return StepObservation(None, "", "empty_reply", False)
        if calls is None:
            message = t.AssistantMessage(role="assistant", content=source)
            calls_text: list[str] = []
        else:
            try:
                tool_calls = [
                    t.ToolCall(id=f"call_{len(orch.trajectory)}_{k}", name=c.func.id,
                               arguments=_tool_call_arguments(c), requestor="assistant")
                    for k, c in enumerate(calls)
                ]
            except (ValueError, SyntaxError):
                return StepObservation(None, "", "malformed_call", False)
            message = t.AssistantMessage(role="assistant", content=None, tool_calls=tool_calls)
            calls_text = [ast.get_source_segment(source, c) for c in calls]

        orch.agent.pending = message
        orch.step()
        orch._check_termination()
        self._advance()

        delivered = orch.message
        error_kind = None
        if calls_text and orch.from_role == t.Role.ENV and orch.to_role == t.Role.AGENT:
            results = delivered.tool_messages if isinstance(delivered, t.MultiToolMessage) else [delivered]
            observation = self._tool_results(calls_text, results)
            if any(r.error for r in results):
                error_kind = "tool_error"
        else:
            observation = delivered.content or ""
        return StepObservation(source, self._capped(observation), error_kind, orch.done)

    def changes_state(self, call: str) -> bool:
        """Whether running `call` would leave the conversation's world different: its first call is to a tool tau2 types WRITE, or to the hand-off to a human agent.

        A text with no call in it, and a call to a tool the domain does not have, change nothing:
        the first runs nothing and the second fails before it reaches the database.
        """
        if self._orch is None:
            raise RuntimeError("tau2.changes_state: called before open")
        t = _load(self.data)
        m = re.search(CALL_START, call or "")
        if m is None:
            return False
        name = m.group(0)[:-1]
        tools = self._orch.environment.tools
        if name not in tools.get_tools():
            return False
        return tools.tool_type(name) == t.ToolType.WRITE or name == HANDOFF_TOOL

    def speculate(self, call: str) -> dict:
        """Run the first call written in `call` on a deep copy of the domain's environment and return what it answered; the conversation's own environment is never touched."""
        if self._orch is None:
            raise RuntimeError("tau2.speculate: called before open")
        t = _load(self.data)
        t0 = time.clock_gettime(time.CLOCK_MONOTONIC)
        written = self.complete_call(call) or (call or "")
        calls = _calls(written)
        if calls is None:
            exec_out, exec_ok, error_kind = f"Error: {written!r} is not a call", False, "unparsable"
        else:
            try:
                tool_call = t.ToolCall(id="speculate_0", name=calls[0].func.id,
                                       arguments=_tool_call_arguments(calls[0]), requestor="assistant")
            except (ValueError, SyntaxError) as exc:
                exec_out, exec_ok, error_kind = f"Error: the call's arguments are not JSON values: {exc}", False, "malformed_call"
            else:
                world = copy.deepcopy(self._orch.environment)
                result = world.get_response(tool_call)
                exec_out = self._capped(self._tool_results([written], [result]))
                exec_ok = not result.error
                error_kind = None if exec_ok else "tool_error"
        spec_s = time.clock_gettime(time.CLOCK_MONOTONIC) - t0
        return {"exec_code": written, "arg_modes": [], "exec_out": exec_out, "exec_ok": exec_ok,
                "error_kind": error_kind, "spec_s": spec_s}

    def judge(self) -> dict:
        """tau2's own reward of the conversation (EvaluationType.ALL: database, actions, communicated values; no LLM judge); success is tau2's is_successful(reward)."""
        try:
            t = _load(self.data)
            orch = self._orch
            if not orch.done:
                # The loop's step cap ended the conversation before tau2 did.
                orch.done = True
                orch.termination_reason = t.TerminationReason.MAX_STEPS
            simulation = orch._finalize()
            self._finalized = True
            simulation.policy = orch.environment.get_policy()
            reward_info = t.evaluate_simulation(
                simulation=simulation, task=self._task, evaluation_type=t.EvaluationType.ALL,
                solo_mode=False, domain=self._domain, env_kwargs=self._env_kwargs,
            )
            return {"success": bool(t.is_successful(reward_info.reward)), "reward": reward_info.reward,
                    "termination_reason": str(simulation.termination_reason),
                    "reward_info": reward_info.model_dump(mode="json")}
        except Exception as exc:
            return {"success": False, "eval_error": f"{type(exc).__name__}: {exc}"[:600]}

    def close(self) -> None:
        if self._orch is None:
            return
        if not self._finalized:
            self._orch._cleanup()
        self._orch = None
        self._task = None
        self._domain = None
        self._env_kwargs = None
        self._finalized = False
        self.task_text = None
        self.task_date = None
