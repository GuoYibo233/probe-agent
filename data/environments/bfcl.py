"""The BFCL multi-turn benchmark (base, miss_func, miss_param, long_context): BFCL's prompting-mode system prompt and call format, its scripted user turns, its own executor stepping the calls through the task's API instances, one call speculated early on copies of those instances, and BFCL's own multi-turn checker as the judgment."""
from __future__ import annotations

import ast
import copy
import json
import os
import re
import socket
import time
from pathlib import Path
from types import SimpleNamespace

import yaml

from data.environments import Environment, StepObservation

# A variant names BFCL's own system-prompt configuration, the format string its
# formulate_system_prompt reads; v1 is its DEFAULT_SYSTEM_PROMPT_FORMAT, the prompt every
# prompting-mode model is scored under: calls as [func(param=value), ...], function docs in JSON,
# plain text, the classic wording.
INSTRUCTIONS = {"v1": "ret_fmt=python&tool_call_tag=False&func_doc_fmt=json&prompt_fmt=plaintext&style=classic"}
# BFCL is an evaluation set with no training split of its own: every category is a test set, and
# a probe trained on BFCL records takes build.split_source: hash.
SPLIT_ROLE = {"multi_turn_base": "test", "multi_turn_miss_func": "test",
              "multi_turn_miss_param": "test", "multi_turn_long_context": "test"}

# The functions whose run leaves an API instance different from before it, read off BFCL's own
# source and checked against its ground truth: every official ground-truth call of the four
# categories was run on the task's instances and its state compared before and after, and each
# function the ground truth never calls was read. A state is every attribute, the private ones
# included: get_flight_cost fills the price table book_flight reads, and get_current_speed and
# get_outside_temperature_from_google move their instance's random generator.
WRITE_TOOLS = {
    # GorillaFileSystem
    "cd", "cp", "echo", "mkdir", "mv", "rm", "rmdir", "touch",
    # MessageAPI
    "add_contact", "delete_message", "message_login", "send_message",
    # TwitterAPI
    "authenticate_twitter", "comment", "follow_user", "mention", "post_tweet", "retweet", "unfollow_user",
    # TicketAPI
    "close_ticket", "create_ticket", "edit_ticket", "logout", "resolve_ticket", "ticket_login",
    # TradingBot
    "add_to_watchlist", "cancel_order", "fund_account", "place_order", "remove_stock_from_watchlist",
    "trading_login", "trading_logout", "withdraw_funds",
    # TravelAPI
    "authenticate_travel", "book_flight", "cancel_booking", "get_flight_cost", "purchase_insurance",
    "register_credit_card", "set_budget_limit",
    # VehicleControlAPI
    "activateParkingBrake", "adjustClimateControl", "fillFuelTank", "get_current_speed",
    "get_outside_temperature_from_google", "lockDoors", "pressBrakePedal", "releaseBrakePedal",
    "setCruiseControl", "setHeadlights", "set_navigation", "startEngine",
}
# A bare name followed by "(": where a written call starts.
CALL_START = r"(?<![\w.])[A-Za-z_]\w*\("
# BFCL's default_decode_execute_prompting strips these characters off both ends of a reply.
STRIP_CHARS = "`\n "
# BFCL shows a function's output whole; this cap is about the agent model's context in
# characters, so it cuts nothing a task produces and generation.result_cap can still lower it.
CUT_NOTE = "\n[output cut: {n} more characters not shown]"


def _char_offset(source: str, lineno: int, col_offset: int) -> int:
    """The character index in `source` of an ast position (1-based line, UTF-8 byte column)."""
    lines = source.splitlines(keepends=True)
    head = sum(len(line) for line in lines[:lineno - 1])
    return head + len(lines[lineno - 1].encode()[:col_offset].decode())


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


def _decoded(text: str) -> tuple[str, int, list[ast.Call]] | None:
    """A reply read the way BFCL's default_decode_execute_prompting reads it: the ends stripped of backticks, newlines and spaces, wrapped in [ ] when it is not, and parsed as a list of calls to bare names.

    Returns the wrapped source, the index in `text` where the source's first character sits
    (one less when an opening bracket was added), and the calls; None when the text is no such
    list, an empty list included.
    """
    raw = text or ""
    stripped = raw.strip(STRIP_CHARS)
    lead = len(raw) - len(raw.lstrip(STRIP_CHARS))
    source = stripped
    if not source.startswith("["):
        source = "[" + source
        lead -= 1
    if not source.endswith("]"):
        source = source + "]"
    try:
        body = ast.parse(source, mode="eval").body
    except SyntaxError:
        return None
    if not (isinstance(body, ast.List) and body.elts):
        return None
    for node in body.elts:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            return None
    return source, lead, body.elts


def _canonical(node: ast.AST, source: str) -> str:
    """One text per value, so the same value written two ways reads the same: the repr of a Python literal, else the value's own source text."""
    try:
        return repr(ast.literal_eval(node))
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return ast.get_source_segment(source, node)


# BFCL's modules, imported once per process inside the benchmark's own interpreter (_load).
_BFCL: dict = {}


def _load(home: str) -> SimpleNamespace:
    """Import BFCL's prompting-mode helpers, data loaders and executor (its project root set first, so its result and lock directories sit in the clone) and return the names this module uses."""
    if "b" in _BFCL:
        return _BFCL["b"]
    os.environ["BFCL_PROJECT_ROOT"] = home
    from bfcl_eval.constants.default_prompts import (
        DEFAULT_USER_PROMPT_FOR_ADDITIONAL_FUNCTION_PROMPTING, MAXIMUM_STEP_LIMIT)
    from bfcl_eval.eval_checker.multi_turn_eval import multi_turn_utils
    from bfcl_eval.model_handler.utils import (
        default_decode_execute_prompting, format_execution_results_prompting, formulate_system_prompt)
    from bfcl_eval.utils import load_dataset_entry, load_ground_truth_entry

    _BFCL["b"] = SimpleNamespace(
        ADDITIONAL_FUNCTION_PROMPT=DEFAULT_USER_PROMPT_FOR_ADDITIONAL_FUNCTION_PROMPTING,
        MAXIMUM_STEP_LIMIT=MAXIMUM_STEP_LIMIT, multi_turn_utils=multi_turn_utils,
        decode_execute=default_decode_execute_prompting,
        format_execution_results=format_execution_results_prompting,
        formulate_system_prompt=formulate_system_prompt,
        load_dataset_entry=load_dataset_entry, load_ground_truth_entry=load_ground_truth_entry,
    )
    return _BFCL["b"]


class _PromptingHandler:
    """The one handler method BFCL's multi-turn evaluation calls: the prompting-mode decoder every locally served model uses (OSSHandler.decode_execute)."""

    def __init__(self, decode_execute) -> None:
        self._decode_execute = decode_execute

    def decode_execute(self, result, has_tool_call_tag):
        return self._decode_execute(result, has_tool_call_tag)


class BFCL(Environment):
    """BFCL's multi-turn categories in prompting mode, run the way its inference_multi_turn_prompting runs them, one model reply per step."""

    NAME = "bfcl"
    INSTRUCTIONS = INSTRUCTIONS
    # Every reply is either calls or the end of the user's turn, so no reply goes without an action.
    NO_CODE_MESSAGE = "Reply with the function calls in the format [func_name(params_name=params_value, ...)], or with no call to end the turn."
    RESULT_CAP = 500000
    # The world takes no seed from outside: each API class seeds its own generator from its scenario.
    SEED = 0
    SPLIT_ROLE = SPLIT_ROLE

    def __init__(self) -> None:
        path = Path(__file__).resolve().parents[2] / "constants" / "path_datasets.yaml"
        with open(path) as f:
            block = yaml.safe_load(f)["bfcl"]
        self.home = block["home"]
        self.data = block["data"]
        self.splits = block["splits"]
        self._loaded_categories: set[str] = set()
        self._entries: dict[str, dict] = {}
        self._ground_truth: dict[str, list] = {}
        self._n_open = 0
        self._entry: dict | None = None
        self._category: str | None = None
        self._model_name: str | None = None
        self._turn = 0
        self._steps_in_turn = 0
        self._responses: list[list[str]] = []
        self.task_text: str | None = None
        self.task_date: str | None = None

    # ---- the task lists, read without BFCL ----

    def tasks(self, split: str) -> list[str]:
        if split not in self.splits:
            raise ValueError(f"bfcl.tasks: unknown split {split!r}, has {sorted(self.splits)}")
        lines = Path(self.splits[split]).read_text().splitlines()
        return [json.loads(line)["id"] for line in lines if line.strip()]

    # ---- call syntax, read without BFCL ----

    def split_args(self, text: str) -> tuple[str, list[tuple[str, str]], tuple[int, int]] | None:
        found = _decoded(text)
        if found is None:
            return None
        source, lead, calls = found
        first = calls[0]
        # The named arguments alone: BFCL's decoder reads keywords only, so a positional argument
        # never reaches the API (sort('a.txt') runs as sort()).
        args = [(k.arg, _canonical(k.value, source)) for k in first.keywords if k.arg is not None]
        span = (lead + _char_offset(source, first.lineno, first.col_offset),
                lead + _char_offset(source, first.end_lineno, first.end_col_offset))
        return first.func.id, args, span

    def build_call(self, tool: str, args: list[tuple[str, str]]) -> str:
        call = f"{tool}({', '.join(f'{key}={value}' for key, value in args)})"
        found = _decoded(call)
        if found is None or len(found[2]) != 1:
            raise ValueError(f"bfcl.build_call: {call!r} does not read back as one call")
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

    # ---- one task ----

    def _instance_prefix(self, model_name: str) -> str:
        """The start of every instance name BFCL's executor gives the instances of `model_name` (its own rule: the name with -./: replaced by _)."""
        return re.sub(r"[-./:]", "_", model_name)

    def _drop_instances(self, model_name: str) -> None:
        """Delete every API instance BFCL's executor holds for `model_name`, the copies its checker made under that name included."""
        namespace = vars(_load(self.home).multi_turn_utils)
        prefix = self._instance_prefix(model_name)
        for key in [k for k in namespace if k.startswith(prefix + "_")]:
            del namespace[key]

    def _long_context(self) -> bool:
        return "long_context" in self._category or "composite" in self._category

    def _execute(self, calls: list[str], model_name: str) -> tuple[list[str], dict]:
        b = _load(self.home)
        return b.multi_turn_utils.execute_multi_turn_func_call(
            calls, self._entry["initial_config"], self._entry["involved_classes"], model_name,
            self._entry["id"], long_context=self._long_context(), is_evaL_run=False)

    def instructions(self, variant: str) -> str:
        if self._entry is None:
            raise RuntimeError("bfcl.instructions: called before open")
        b = _load(self.home)
        prompt = b.formulate_system_prompt(format_sensitivity_config=self.INSTRUCTIONS[variant],
                                           functions=self._entry["function"])
        # system_prompt_pre_processing_chat_model's rule: a system message the question carries
        # follows the function prompt.
        first = self._entry["question"][0]
        if first and first[0]["role"] == "system":
            prompt = prompt + "\n\n" + first[0]["content"]
        return prompt

    def _turn_message(self, turn: int) -> str:
        """The user's message that opens `turn`: the scripted one, or BFCL's prompt that hands over the held-out functions at a miss_func turn."""
        b = _load(self.home)
        holdout = self._entry.get("missed_function", {})
        if str(turn) in holdout:
            return b.ADDITIONAL_FUNCTION_PROMPT.format(functions=holdout[str(turn)])
        return "\n\n".join(m["content"] for m in self._entry["question"][turn] if m["role"] == "user")

    def open(self, task_id: str, seed: int) -> None:
        del seed  # the scripted turns and the API instances take no seed
        b = _load(self.home)
        category = task_id.rsplit("_", 1)[0]
        if category not in self.SPLIT_ROLE:
            raise ValueError(f"bfcl.open: task id {task_id!r} names no category of {sorted(self.SPLIT_ROLE)}")
        if category not in self._loaded_categories:
            for entry in b.load_dataset_entry(category):
                self._entries[entry["id"]] = entry
            for gt in b.load_ground_truth_entry(category):
                self._ground_truth[gt["id"]] = gt["ground_truth"]
            self._loaded_categories.add(category)
        if task_id not in self._entries:
            raise ValueError(f"bfcl.open: category {category!r} holds no task with id {task_id!r}")
        self._entry = copy.deepcopy(self._entries[task_id])
        self._category = category
        # BFCL's executor keeps a task's instances in a module namespace under the model's name;
        # one name per open, so no two task runs of this process ever share an instance.
        self._n_open += 1
        self._model_name = f"new1_{socket.gethostname()}_{os.getpid()}_{self._n_open}"
        self._execute([], self._model_name)
        self._turn = 0
        self._steps_in_turn = 0
        self._responses = [[]]
        self.task_text = self._turn_message(0)

    def _capped(self, out: str) -> str:
        """`out` whole when it fits RESULT_CAP characters, else its first RESULT_CAP characters and one line saying how many were left out."""
        if len(out) <= self.RESULT_CAP:
            return out
        return out[:self.RESULT_CAP] + CUT_NOTE.format(n=len(out) - self.RESULT_CAP)

    def step(self, reply_text: str) -> StepObservation:
        """One model reply, as one step of BFCL's inference_multi_turn_prompting: calls are run and their results returned; a reply that decodes to no call ends the user's turn and the next turn's message comes back, or the task ends after the last turn; more than MAXIMUM_STEP_LIMIT steps in one turn end the task."""
        b = _load(self.home)
        self._responses[self._turn].append(reply_text)
        action = (reply_text or "").strip()
        try:
            decoded = b.decode_execute(reply_text, has_tool_call_tag=False)
            turn_ends = len(decoded) == 0 or (len(decoded) == 1 and len(decoded[0]) == 0)
        except Exception:
            decoded, turn_ends = [], True
        if turn_ends:
            self._turn += 1
            self._steps_in_turn = 0
            if self._turn == len(self._entry["question"]):
                return StepObservation(action, "", None, True)
            self._responses.append([])
            return StepObservation(action, self._turn_message(self._turn), None, False)

        results, _ = self._execute(decoded, self._model_name)
        observation = b.format_execution_results(None, results, {"model_responses_decoded": decoded})
        failed = any(r.startswith("Error during execution") for r in results)
        self._steps_in_turn += 1
        # BFCL's force quit: the whole task is failed (its checker finds fewer turns than the
        # ground truth holds, unless this was the last turn).
        force_quit = self._steps_in_turn > b.MAXIMUM_STEP_LIMIT
        return StepObservation(action, self._capped(observation), "execution_error" if failed else None, force_quit)

    def changes_state(self, call: str) -> bool:
        """Whether running `call` would leave the task's API instances different: its first call is to a function of WRITE_TOOLS; a text with no call changes nothing."""
        m = re.search(CALL_START, call or "")
        return m is not None and m.group(0)[:-1] in WRITE_TOOLS

    def speculate(self, call: str) -> dict:
        """Run the first call written in `call`, read by BFCL's decoder as step reads a reply, through BFCL's executor on deep copies of the task's instances and return its result; the task's own instances are never touched."""
        if self._entry is None:
            raise RuntimeError("bfcl.speculate: called before open")
        b = _load(self.home)
        t0 = time.clock_gettime(time.CLOCK_MONOTONIC)
        written = self.complete_call(call) or (call or "")
        try:
            decoded = b.decode_execute(written, has_tool_call_tag=False)
        except Exception:
            decoded = []
        if not decoded or not decoded[0]:
            spec_s = time.clock_gettime(time.CLOCK_MONOTONIC) - t0
            return {"exec_code": written, "arg_modes": [], "exec_out": f"Error: {written!r} decodes to no call",
                    "exec_ok": False, "error_kind": "unparsable", "spec_s": spec_s}
        written = decoded[0]
        namespace = vars(b.multi_turn_utils)
        live = self._instance_prefix(self._model_name)
        spec_name = f"{self._model_name}_spec"
        spec = self._instance_prefix(spec_name)
        for key in [k for k in namespace if k.startswith(live + "_" + self._instance_prefix(self._entry["id"]) + "_")]:
            namespace[spec + key[len(live):]] = copy.deepcopy(namespace[key])
        try:
            results, _ = self._execute([written], spec_name)
        finally:
            self._drop_instances(spec_name)
        exec_out = self._capped(b.format_execution_results(None, results, {"model_responses_decoded": [written]}))
        exec_ok = not results[0].startswith("Error during execution")
        spec_s = time.clock_gettime(time.CLOCK_MONOTONIC) - t0
        return {"exec_code": written, "arg_modes": [], "exec_out": exec_out, "exec_ok": exec_ok,
                "error_kind": None if exec_ok else "execution_error", "spec_s": spec_s}

    def judge(self) -> dict:
        """BFCL's own multi-turn evaluation of the replies, turn by turn (_evaluate_single_multi_turn_entry: the force-terminated check, the prompting decoder, then multi_turn_checker's state and response checks against the ground truth)."""
        judge_name = f"{self._model_name}_judge"
        try:
            b = _load(self.home)
            from bfcl_eval.eval_checker.eval_runner import _evaluate_single_multi_turn_entry
            result = _evaluate_single_multi_turn_entry(
                _PromptingHandler(b.decode_execute), self._entry["id"], copy.deepcopy(self._responses),
                self._ground_truth[self._entry["id"]], copy.deepcopy(self._entry), judge_name, self._category,
            )
            out = {"success": bool(result["valid"]), "turns": len(self._responses)}
            if "error" in result:
                out["error"] = json.loads(json.dumps(result["error"], default=str))
            return out
        except Exception as exc:
            return {"success": False, "eval_error": f"{type(exc).__name__}: {exc}"[:600]}
        finally:
            self._drop_instances(judge_name)

    def close(self) -> None:
        if self._entry is None:
            return
        self._drop_instances(self._model_name)
        self._entry = None
        self._category = None
        self._model_name = None
        self._turn = 0
        self._steps_in_turn = 0
        self._responses = []
        self.task_text = None
        self.task_date = None
