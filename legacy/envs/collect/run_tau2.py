"""tau2-bench (customer-service domain) driver: records every step in full -- "one chunk of
thinking + one tool call or one line said to the user".

What question this answers
--------------
Adds a **conversational** tool-call environment to the probe pipeline: the agent plays customer
service, an LLM user simulator plays the customer, and each turn the agent either calls one
domain tool (14 for airline / 16 for retail) or says one line to the customer. The on-disk
format matches run_appworld.py / run_alfworld.py field for field (the four row types
meta/gen/env/final, with `--resume` recognizing `"type": "final"`), so downstream annotate only
needs one added branch to consume it.

Interpreter
------
Must use tau2's own venv (it's the one with tau2 + loguru + openai installed):
  envs/tau2-bench/.venv/bin/python envs/collect/run_tau2.py ...

Usage
----
  envs/tau2-bench/.venv/bin/python envs/collect/run_tau2.py \
      --base-url http://HOST:8101/v1 --model qwen3.5-27b \
      --user-base-url http://HOST:8102/v1 --user-model qwen3.6-27b \
      --domain airline --split test --n 2 \
      --outdir envs/runs/smoke_tau2/tau2_q35 --exp smoke_tau2
Self-test (pure CPU, sends no HTTP, touches no GPU):
  envs/tau2-bench/.venv/bin/python envs/collect/run_tau2.py --selftest

Differences from appworld / alfworld
----------------------------
1. There is a **second LLM**: the user simulator. Its prompt contains scenario ground truth the
   agent never sees, so its generations are logged separately as `type: "user"` rows, and
   **content with type="user" must never be fed into the probe input at any point** (build.py
   only recognizes gen/env; unrecognized types are simply ignored, giving natural isolation).
2. Tool arguments are **nested JSON** (list[dict] / dict), not the flat kwargs appworld uses.
3. The agent has two legal outputs per turn: call a tool, or speak to the customer. A speaking
   turn produces no tool call.

Known biases (seven, must know before reading the numbers)
--------------------------------
1. **Text protocol, not native function calling**. Neither path of the Chat in common.py:20-91
   passes `tools=` (the raw path at :30-35 builds its own `<|im_start|>` template; the chat
   path at :77-80 also has no tools parameter), and changing this would touch the shared
   convention of all three collectors, appworld/alfworld/tales. So this file follows the same
   approach as appworld (python code blocks) / alfworld (`ACTION:` lines): `TOOL: <name>` plus
   a ```json argument block, which this collector assembles into a tau2 ToolCall and hands to
   the environment.
   **Consequence: not comparable to the official tau2-bench leaderboard numbers** (the official
   benchmark uses native function calling).
2. **Only one tool call per turn is allowed**. tau2 natively supports multiple calls per turn
   (MultiToolMessage); restricting it to one lengthens trajectories and also departs from the
   official setting; relaxing it would require changing the probe's "one label per step"
   convention.
3. **NL assertions are not evaluated**, so retail's official reward can't be fully computed.
   Measured: 112 of retail's 114 tasks have reward_basis = {DB, NL_ASSERTION}, and NL
   assertions need an LLM judge (evaluator/evaluator_nl_assertions.py calls generate). This
   collector only uses EvaluationType.ALL_IGNORE_BASIS (ENV+ACTION+COMMUNICATE, zero LLM
   calls), then folds in official_reward per each task's own basis. All 50 airline tasks are
   {DB, COMMUNICATE}, neither of which needs an LLM, so **official_reward is complete** for
   them; the 112/114 retail tasks get `official_reward_complete: false`.
4. **The `action` string silently drops arguments for two kinds of values**: a value
   containing an unbalanced `(` (tau2's `calculate(expression=...)` naturally has one) makes
   rules.first_call_named return `[]` (all arguments lost); a value containing an **odd**
   number of escaped `\\"` merges two adjacent keys into one. Neither case raises an error. So
   every step runs a round-trip self-check, and any mismatch marks `args_lossy: true` on the
   env row and increments a counter (the final row's `n_args_lossy`) -- this is the only alarm
   for it. The env row separately carries the structured `tool_name` / `tool_args` (the raw
   dict), so downstream consumers can skip parsing the action string entirely.
5. **A SAY turn produces no event**: the env row's `action` is None, and the
   `if not action: continue` in build.py:64-65 runs before `hist.append`, so what the agent
   says to the customer **never enters the probe prompt's history at all**. The original words
   stay in the env row's `said` field, so both readings remain available; which one to use is
   a data-setting decision (see "Open decisions" below).
6. **A read-only task's official_reward can hand out a free 1.0**. Measured in self-test:
   airline task 1's golden actions are only the two read operations get_user_details /
   get_reservation_details, and communicate_info is an empty list -- so the DB hash matches
   trivially, COMMUNICATE is trivially full marks, and an agent that does nothing useful at all
   still folds out an official_reward of 1.0 (in the same run, ALL_IGNORE_BASIS's reward is
   0.0, because the ACTION check fails). **official_reward and reward must be read side by
   side**; reading only the former turns doing nothing into a perfect score.
7. **The user simulator defaults to hitting the same service with the same model**
   (`--user-model` defaults to `--model`). Talking to itself is a confound, it skews the
   trajectory distribution, and nothing in any of the numbers shows this. A WARN line prints
   when the default is used; the official tau2 smoke test uses a q35 agent + q36 user.

What's still needed for real-scale collection
------------------------
- One **vLLM /v1 service** (agent side): `--base-url http://<host>:<port>/v1`
  `--model <served-model-name>`. Measured system prompt for airline is about 23k characters
  (7676 for the policy + 14623 for the 14 tools' openai_schema), about 6k tokens; retail is a
  bit smaller. The service must run at roughly `--max-model-len 65536`, otherwise multi-turn
  runs will eventually truncate.
- A **second service** (user simulator side) `--user-base-url/--user-model` is recommended,
  otherwise you hit bias #7. Starting/picking/launching GPU-side services always goes through
  the gpu-run skill; this file never touches a GPU.
- Three task-list files (annotate needs train/val/test as three txt files, one
  `<domain>/<task_id>` per line). airline/retail **officially only have train/test/base**, no
  val -- see "Open decisions".

Open decisions (need a human call, the collector should not guess)
------------------------------------
- airline/retail have no val split (measured: the only splits are train/test/base; airline is
  30/20/50, retail is 74/40/114), while build.py:33's SPLITS hardcodes three splits. Whether to
  carve one out of train or change SPLITS is a data-setting decision.
- Whether the agent and the user simulator should use different models, and which one is fixed
  as the user.
- Whether to run only airline+retail or also add telecom (telecom has user-side tools, and its
  task ids look like `[mms_issue]airplane_mode_on|...`, which can't be used directly as a
  filename -- a separate chunk of work).
- Whether to allow multiple calls per turn; whether a SAY turn should enter the probe prompt's
  history; whether retail's NL assertions should go through an LLM judge (if not, RESULTS.md
  must not call that number reward).
- Which tag to pin the tau2 repo to (the README states explicitly that <1.0.1 and >=1.0.1 are
  not comparable, the change being to banking_knowledge; we only run airline/retail, which per
  the README are unaffected, but **this file did not check the specific tag** -- marked NOT
  FOUND, needs recording in DATA.md).

Downstream to-dos (no code changed this round, only aligning the interface so a branch is
enough to use it)
----------------------------------------------------
① pipeline/annotate/rules.py: add `TAU2_CALL = re.compile(r"tau2\\.(\\w+)\\.(\\w+)\\(")`
   -- matches this file's TAU2_CALL in shape (the action string is deliberately made the same
   shape as AW_CALL's `apis.x.y(`, so the argument-splitting logic can reuse first_call_named
   directly, with no redesign needed).
② build.py:66-96's jsonl_events: add a tau2 branch (copy the 11 lines from appworld,
   tool = f"tau2.{m.group(1)}.{m.group(2)}"), plus build.py:152-167's collect_events: add the
   `tau2_*/tau2_*.jsonl` glob. **Skip this and it falls into the else tales catch-all**: the
   label becomes `action.split()[0]`, i.e. the whole `tau2.airline.book_reservation(...)`
   counted as one verb -- the data still builds, the report still runs, and only eyeballing the
   tool vocabulary would catch it (extending.md section 5, item 5).
③ param_label.py:43-81 and :125-143, the same two spots.
④ eval_causal_call.py:118-124's name_re: add a tau2 branch (without it, it falls through to the
   BFCL_CALL fallback, tool_ok collapses entirely, and the exit code is still 0).
⑤ pipeline/collect/gen_launch.py's ENV_TABLE: adding a tau2 row, the interpreter path doesn't
   fit the template (`$E/{venv}/venv/bin/python` doesn't match `tau2-bench/.venv`) --
   ENV_TABLE needs a `py` field and a change to :276; the client function also has no
   `--domain` slot yet.
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
from common import Chat, TrajLog, chat_of, settings_from_args  # noqa: E402
from rules import MODEL_OF, SEED, first_call_named  # noqa: E402

# Silence loguru before importing tau2: tau2.registry dumps a large block of DEBUG registry
# output at import time (measured), and it floods the tmux log.
logger.remove()
logger.add(sys.stderr, level="WARNING")

# v1 only includes these two domains. Hard reason: both have env.user_tools is None (measured),
# so no user-side tools are involved; telecom has user_tools, and its task ids look like
# `[mms_issue]airplane_mode_on|bad_...`, which simply can't be used as a filename.
DOMAINS = ("airline", "retail")

# Same shape as the pattern that downstream to-do ① adds to rules.py. Deliberately matches
# AW_CALL's `apis.(\w+).(\w+)\(` structure exactly, so first_call_named's paren-balancing and
# argument splitting can be reused as-is.
TAU2_CALL = re.compile(r"tau2\.(\w+)\.(\w+)\(")

# [Copied verbatim from envs/tau2-bench/src/tau2/orchestrator/orchestrator.py:46-48's
#  DEFAULT_FIRST_AGENT_MESSAGE] -- the opening line is a constant, so it costs no LLM call.
FIRST_AGENT_MESSAGE = "Hi! How can I help you today?"

# [Copied verbatim from envs/tau2-bench/src/tau2/user/user_simulator_base.py:51-53]
USER_STOP_TOKENS = ("###STOP###", "###TRANSFER###", "###OUT-OF-SCOPE###")

# [Copied verbatim from envs/tau2-bench/src/tau2/config.py:5's DEFAULT_MAX_ERRORS]
DEFAULT_MAX_ERRORS = 10

# Character cap for stuffing the environment's response back into context [copied verbatim
# from envs/collect/run_appworld.py:105]
RESULT_CAP = 4000

# [Copied verbatim from envs/tau2-bench/src/tau2/agent/llm_agent.py:24-31's AGENT_INSTRUCTION]
# Same source as the official version, not a word changed -- swapping it out would mean
# changing the task setting itself.
AGENT_INSTRUCTION = """
You are a customer service agent that helps the user according to the <policy> provided below.
In each turn you can either:
- Send a message to the user.
- Make a tool call.
You cannot do both at the same time.

Try to be helpful and always follow the policy. Always make sure you generate valid JSON only.
""".strip()

# Our own reply-format section. Three rules, written in the same firm tone as
# run_alfworld.py:42-79:
#   ① Reason for a few sentences before acting -- rules.MIN_THINK=40's character threshold
#      discards a step with no thinking **entirely**; a prompt saying "reply with only the
#      call and nothing else" leaves reasoning empty, so what gets collected is empty data.
#   ② The reply must end with exactly one of two block types (SAY or TOOL+JSON), because the
#      parser only recognizes those two.
#   ③ Only one block per turn; the tool name must be copied verbatim from <tools>; the
#      arguments must be valid JSON.
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
SAY_MARK = "SAY:"          # Cut by position from the right, not with a regex: see the note in parse_reply.

# Character-set gate for task id: it must be usable directly as part of a filename (measured:
# airline/retail are all plain numbers 0..113, all legal). Reject illegal ones on the spot;
# never silently produce a weird filename.
ID_RE = re.compile(r"[A-Za-z0-9_.-]+")


# ---------- unit id and on-disk naming ----------

def escape_unit(uid):
    """unit id contains a slash (`<domain>/<task_id>`); before writing to disk, `/` -> `__`.

    [Copied verbatim from envs/collect/run_alfworld.py:85-96's escaping convention].
    Both the domain name and the task id pass the ID_RE gate (no separators other than `_`,
    and **no `__`**), so this mapping is a reversible bijection:
    unescape_unit(escape_unit(u)) == u.
    """
    return uid.replace("/", "__")


def unescape_unit(name):
    return name.replace("__", "/")


# ---------- parse: model reply -> one block ----------

def brace_scan(text):
    """Starting from the first `{`, count depth until it balances and return that substring
    (braces on both ends included); return None if it never balances.

    The fallback for when there is no fence (```json). Braces inside a string don't count
    toward depth, and `\\"` doesn't count as closing a quote.
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
    """Model reply -> (kind, name, args, say, reason). A pure function, unit-testable.

    kind has four values, priority fixed as **TOOL > SAY > none**:
      tool        name/args are valid
      parse_fail  found TOOL: but the argument block can't be retrieved or isn't a valid JSON
                  object; reason explains why
      say         no TOOL:, but SAY: present; say holds that line
      none        neither block is present (the caller falls back to a nudge)
    `TOOL:` takes the **last** match -- the model sometimes restates the format instructions
    before giving the final call.
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
    # SAY follows the same convention as TOOL: take the content after the **last** `SAY:`. The
    # system prompt spells out `SAY: <what you say to the customer>` verbatim, and the model
    # restating it is a behavior already guarded against (see the TOOL comment above); if SAY took
    # the first match, the whole format instructions would be treated as what was said to the
    # customer -- passed straight to the user simulator, written into the env row's said, and on
    # into the evaluator -- wrong in three places at once, with no counter to catch it.
    # Note that this case **cannot** copy TOOL's finditer[-1]: TOOL_RE captures only one word, so
    # it can have multiple hits, but under re.S, SAY_RE's `(.+)` is greedy, so the first SAY:
    # swallows the entire rest (including any later SAY:) in one bite; finditer then has only one
    # hit, and taking the last one is the same as not doing so. Verified by testing.
    # So it cuts by marker position from the right instead.
    i = content.rfind(SAY_MARK)
    if i >= 0:
        say = content[i + len(SAY_MARK):].strip()
        if say:
            return "say", None, None, say, None
    return "none", None, None, None, "no_block"


# ---------- normalize the call string + round-trip self-check ----------

def canon_action(domain, name, args):
    """-> `tau2.<domain>.<tool>(k=v, ...)`, with values as JSON literals.

    Same shape as AW_CALL's `apis.<app>.<api>(`, so the downstream branch is just a copy of
    appworld's 11 lines, with no need to redesign label_call / argument splitting.
    """
    inner = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}"
                      for k, v in args.items())
    return f"tau2.{domain}.{name}({inner})"


def is_args_lossy(action, args):
    """Round-trip self-check: cut the action string again with rules.first_call_named; the key
    order must come out identical.

    Failing to cut back = downstream re-cutting arguments from the action string will silently
    mislabel. **Raises no exception** (one odd argument must not lose the whole trajectory) --
    it just returns True so the caller can tag and count it. Two kinds of values have actually
    been measured to break this:
      - a value containing an unbalanced `(` (e.g. `calculate(expression="((1+2)")`) -> cuts to `[]`
      - a value containing an odd number of escaped `\\"` -> merges two adjacent keys into one
    Neither case makes first_call_named raise an error, so this function is the only alarm for
    it.
    """
    named = first_call_named(action, TAU2_CALL) or []
    return [k for k, _ in named] != list(args.keys())


# ---------- tau2 dependencies (lazy import, same approach as run_appworld.py:61) ----------

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
    """System prompt = official instructions + official policy + tool schema + our format section.

    Measured for airline: policy is 7676 characters + 14623 characters for the 14 tools'
    openai_schema, about 23k characters total, roughly 6k tokens.
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
    """The user simulator's system prompt, taken verbatim from the official
    UserSimulator.system_prompt.

    Only reads its property (a pure property, zero LLM calls; measured about 2.6k characters
    for airline, including the official data/tau2/user_simulator/simulation_guidelines.md);
    **does not go through tau2's LiteLLM path** -- that path needs litellm plus a cost table,
    and it can't give us the thinking section in the form we need. Passing llm='dummy' is just
    a placeholder: the system_prompt computation path never looks at it.
    """
    us = T.UserSimulator(llm="dummy",
                         instructions=str(task.user_scenario.instructions))
    return us.system_prompt


def is_user_stop(text):
    return any(tok in (text or "") for tok in USER_STOP_TOKENS)


def basis_of(task):
    """task.evaluation_criteria.reward_basis -> ['DB', 'COMMUNICATE', ...]."""
    crit = getattr(task, "evaluation_criteria", None)
    return [str(b).split(".")[-1] for b in (crit.reward_basis if crit else [])]


def fold_official(basis, breakdown, reward):
    """Fold out the official-convention score from task's own reward_basis -> (score, whether
    complete, what's missing, note).

    We only run EvaluationType.ALL_IGNORE_BASIS (ENV+ACTION+COMMUNICATE, zero LLM calls), so
    the breakdown **never has NL_ASSERTION**. For tasks whose basis includes NL_ASSERTION
    (112/114 in retail), only the DB half can be folded out, complete=False -- this number
    **must not be called reward**.
    An empty breakdown means RewardInfo's early-exit path (evaluator.py:119-134: termination
    not AGENT_STOP/USER_STOP gives 0 directly; no criteria gives 1); in that case reward is
    carried through as-is and marked incomplete + note, so that "hit the step limit while
    talking" doesn't get read as "did it wrong".
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


# ---------- main loop ----------

def run_task(T, env, domain, task, chat, user_chat, args, out_path):
    """Run one task, write one jsonl, return one summary line as a string.

    Hard invariant: **every step has exactly one gen row and one env row, and steps are
    consecutive starting from 0**. The moment a step has a gen row but no env row,
    build.py:64-65 breaks the rest of that trajectory's steps.
    """
    t0 = time.time()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    unit = f"{domain}/{task.id}"

    # The environment's initial state. Measured: initial_state is None for every airline/retail
    # task, but this still goes through the general path passing task.initial_state's three
    # fields, keeping an extension point open.
    init = getattr(task, "initial_state", None)
    idata = getattr(init, "initialization_data", None) if init else None
    iacts = getattr(init, "initialization_actions", None) if init else None
    ihist = list(getattr(init, "message_history", None) or []) if init else []
    env.set_state(idata, iacts, list(ihist))

    # tau2-side message sequence (handed to the official evaluator). Must **include the
    # initial_state history** -- the comment in evaluator_env.py:27-39 states explicitly that
    # full_trajectory needs to carry it.
    tmsgs = list(ihist)
    tmsgs.append(T.AssistantMessage(role="assistant",
                                    content=FIRST_AGENT_MESSAGE))

    # Run one user turn first to get the opening request. The user side keeps its own separate
    # msgs, with roles flipped by hand: what the agent says goes in as 'user', what the user says
    # goes in as 'assistant'
    # [copied verbatim from envs/tau2-bench/src/tau2/user/user_simulator_base.py:62-90's
    #  flip_roles semantics].
    umsgs = [{"role": "system", "content": user_system_prompt(T, task)}]
    umsgs.append({"role": "user", "content": FIRST_AGENT_MESSAGE})
    ug = user_chat(umsgs)
    opening = (ug["content"] or "").strip()
    if not opening:
        # An empty opening line is not a made-up edge case: common.py:62-63 states explicitly that
        # "overlong thinking gets truncated: it all counts as thinking, content is empty", and that
        # Chat is shared across every collector in the repo. Left unchecked, meta.instruction ends up
        # an empty string, and every sample's first line built by build.py:53 is an empty `Task: `,
        # losing the whole prompt with no trace -- while the trajectory still runs to completion, exit
        # code 0, and nothing in any number shows it. So retry once, and drop it if it's still empty.
        ug = user_chat(umsgs)
        opening = (ug["content"] or "").strip()
    if not opening:
        print(f"  SKIP {domain}/{task.id}: the user simulator gave an empty opening both times, not writing to disk",
              flush=True)
        return None
    umsgs.append({"role": "assistant", "content": opening})
    tmsgs.append(T.UserMessage(role="user", content=opening))
    # This user record must be written after meta (build.py:50 takes recs[0] directly as meta), so
    # cache it first and write it once TrajLog is built.
    pending_user = {"type": "user", "step": -1, "phase": "open", **ug}

    # instruction takes the **opening request**, not user_scenario: build.py:53 pastes it verbatim
    # into the probe prompt's Task line, and user_scenario contains known_info / task_instructions
    # the agent has never seen -- putting that in would leak information (the probe would cheat on
    # ground truth, inflating scores invisibly).
    # The scenario ground truth is saved separately as user_scenario_hidden -- deliberately named
    # neither task nor instruction, to avoid build.py's two lookup keys.
    log = TrajLog(out_path, {
        "env": "tau2", "task_id": unit, "model": args.model,
        "instruction": opening, "domain": domain, "split": args.split,
        "exp": args.exp, "user_model": args.user_model, "seed": args.seed,
        "max_steps": args.max_steps, "max_errors": args.max_errors,
        "tau2_task_id": task.id,
        "user_scenario_hidden": str(task.user_scenario),
        # selftest runs through _ScriptedChat, which has no settings method, so record None.
        "preset": getattr(args, "preset", None),
        "gen_settings": getattr(chat, "settings", lambda: None)(),
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
            # A hallucinated tool name still gets handed to the environment: it returns a ToolMessage with
            # error=True, and during replay environment.set_state treats an unknown tool as a no-op, so
            # evaluation doesn't crash.
            tm = env.get_response(tc)
            n["tool"] += 1
            n["env_error"] += int(bool(tm.error))
            rec = {"type": "env", "step": step,
                   "action": action if known else None,
                   "result": (tm.content or "")[:RESULT_CAP],
                   "error": bool(tm.error),
                   "tool_name": name, "tool_args": cargs}
            if not known:
                # When action=None, build.py:64-65's `if not action: continue` skips this step, so a
                # hallucinated tool name never enters the tool vocabulary; writing it into action would
                # silently pollute the vocabulary.
                n["bad_tool"] += 1
                rec["bad_tool"] = name
                rec["raw_call"] = action
            if lossy:
                rec["args_lossy"] = True
            log.w(rec)
            # This content handed to the evaluator must be None (matching the official LLMAgent): filling
            # in the model's thinking text would let CommunicateEvaluator find the required info inside it
            # and award points, inflating the COMMUNICATE component with thinking text.
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
            # action=None: a SAY turn is not a tool call, so it produces no probe event (bias item 5).
            log.w({"type": "env", "step": step, "action": None,
                   "said": say, "result": ureply})
            msgs.append({"role": "user", "content": ureply})
            if is_user_stop(ureply):
                term = T.TerminationReason.USER_STOP
                break
            continue

        # parse_fail / none: this must also add an env entry (otherwise build.py cuts off all later
        # steps of the whole trajectory)
        # [Copy the nudge path from envs/collect/run_alfworld.py:211-223]
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

    # Official evaluation. Do not use uuid for id -- the engineering hard rule requires reruns to
    # be sample-for-sample identical.
    sim = T.SimulationRun(
        id=f"{args.exp}__{domain}__{task.id}", task_id=task.id,
        start_time=start_iso, end_time=end_iso,
        duration=round(time.time() - t0, 2),
        termination_reason=term, messages=tmsgs, seed=args.seed)
    ev, reward, eval_error = None, None, None
    try:
        ri = T.evaluate_simulation(sim, task, T.EvaluationType.ALL_IGNORE_BASIS,
                                   solo_mode=False, domain=domain)
        # **Must call model_dump(mode="json")**: reward_breakdown's keys are the RewardType
        # enum, so json.dumps directly raises TypeError -> the final line never gets written ->
        # `--resume` never sees the `"type": "final"` it expects -> this task gets recollected
        # from scratch on every rerun and never finishes.
        ev = ri.model_dump(mode="json")
        reward = ri.reward
    except Exception as e:              # Eval failure does not discard the trajectory
        # The ALL_IGNORE_BASIS branch does not pass strict_replay=False when calling EnvEvaluator
        # (evaluator.py:279-285); replay raises if the tool output does not match what was recorded.
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


# ---------- self-test (pure CPU: no HTTP, no GPU) ----------

class _ScriptedChat:
    """Test double, **used only inside --selftest**: returns canned replies in sequence; same signature as common.Chat."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.i = 0

    def __call__(self, messages, tries=4):
        assert self.i < len(self.replies), "canned replies ran out (the script and the loop step count don't match)"
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

    # (1) parse_reply: 8 canned replies
    cases = [
        ("normal TOOL",
         'reasoning...\nTOOL: get_user_details\n```json\n{"user_id": "mia_li_3668"}\n```',
         ("tool", "get_user_details", {"user_id": "mia_li_3668"})),
        ("unfenced JSON",
         'thinking\nTOOL: list_all_airports\n{}',
         ("tool", "list_all_airports", {})),
        ("SAY",
         'I should confirm first.\nSAY: Sure, may I have your user id?',
         ("say", None, None)),
        ("restatement before TOOL",
         'The format is TOOL: some_tool then json. So:\n'
         'TOOL: get_reservation_details\n```json\n{"reservation_id": "EHGLP3"}\n```',
         ("tool", "get_reservation_details", {"reservation_id": "EHGLP3"})),
        ("JSON broken",
         'TOOL: calculate\n```json\n{"expression": }\n```',
         ("parse_fail", "calculate", None)),
        ("nothing at all", 'I am thinking about the policy.', ("none", None, None)),
        ("TOOL name doesn't exist (parsing still succeeds, the gate is in the main loop)",
         'TOOL: totally_made_up\n```json\n{"a": 1}\n```',
         ("tool", "totally_made_up", {"a": 1})),
        ("arg value contains unbalanced brackets",
         'TOOL: calculate\n```json\n{"expression": "((1+2)"}\n```',
         ("tool", "calculate", {"expression": "((1+2)"})),
    ]
    for label, reply, want in cases:
        kind, name, cargs, _say, _r = parse_reply(reply)
        got = (kind, name, cargs) if kind != "say" else (kind, None, None)
        chk(got == want, f"parse_reply[{label}] got={got} want={want}")

    # (2) canon_action round-trip self-check: 6 real-shape cases have all keys in the correct
    # order, 2 known-bad shapes must trigger the alarm
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
            f"the lossy alarm should fire [{name}] {act}")

    # (3) fold_official: three conventions
    o, c, m, nt = fold_official(["DB", "COMMUNICATE"],
                               {"DB": 1.0, "ACTION": 0.0, "COMMUNICATE": 1.0},
                               0.0)
    chk((o, c, m, nt) == (1.0, True, [], None),
        f"fold[airline settings] {(o, c, m, nt)}")
    o, c, m, nt = fold_official(["DB", "NL_ASSERTION"],
                               {"DB": 1.0, "ACTION": 1.0, "COMMUNICATE": 1.0},
                               1.0)
    chk((o, c, m) == (1.0, False, ["NL_ASSERTION"]),
        f"fold[retail settings: NL not scored -> incomplete] {(o, c, m)}")
    o, c, m, nt = fold_official(["DB", "COMMUNICATE"], {}, 0.0)
    chk((o, c) == (0.0, False) and nt, f"fold[early-exit path carries a note] {(o, c, nt)}")

    # (4) Actually run airline task '1' end to end: real environment + real official evaluator,
    # only the two LLMs are doubles
    T = load_tau2()
    domain = "airline"
    env = T.registry.get_env_constructor(domain)()
    chk(env.user_tools is None, "airline has no user-side tools")
    tasks = T.registry.get_tasks_loader(domain)("base")
    task = next((t for t in tasks if t.id == "1"), None)
    chk(task is not None, "airline base has task id '1'")

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
    # Use the system temp directory; never hard-code a session-private path -- hard-coding one
    # guarantees a FileNotFoundError 100% of the time in a different session, and the crash
    # reason has nothing to do with the collection logic, so whoever reads the log will think
    # the code is broken
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / f"tau2_{escape_unit(f'{domain}/{task.id}')}.jsonl"
        line = run_task(T, env, domain, task, _ScriptedChat(agent_script),
                        _ScriptedChat(user_script), args, out_path)
        print("  scripted run:", line, flush=True)

        # (5) Read it back and assert the structure
        raw = out_path.read_text()
        # This one guards the RewardType enum keys in reward_breakdown: json.dumps directly raises
        # TypeError and drops the final line, and --resume looks for exactly that line, so the task
        # never finishes collecting.
        chk('"type": "final"' in raw,
            "the `\"type\": \"final\"` marker that --resume relies on actually lands in the file")
        recs = [json.loads(l) for l in open(out_path)]
        chk(recs[0]["type"] == "meta" and recs[0]["task_id"] == "airline/1",
            f"first line is meta + task_id carries the domain prefix: {recs[0].get('task_id')}")
        chk(recs[0]["instruction"] == user_script[0],
            "instruction = the opening request (not user_scenario)")
        chk("user_scenario_hidden" in recs[0]
            and "task" not in recs[0], "scenario ground truth is saved separately, doesn't occupy build.py's value key")
        chk(recs[-1]["type"] == "final", "last line is final")
        gens = [r["step"] for r in recs if r["type"] == "gen"]
        envs = [r["step"] for r in recs if r["type"] == "env"]
        chk(gens == list(range(len(agent_script))), f"gen steps are consecutive: {gens}")
        chk(envs == gens, f"exactly one env per step: {envs}")
        fin = recs[-1]
        chk(fin["termination"] == "user_stop",
            f"termination=user_stop, actually got {fin['termination']}")
        chk(fin["n_bad_tool"] == 1, f"n_bad_tool=1, actually got {fin['n_bad_tool']}")
        chk(fin["n_parse_fail"] == 1,
            f"n_parse_fail=1, actually got {fin['n_parse_fail']}")
        chk(fin["n_args_lossy"] == 1,
            f"n_args_lossy=1, actually got {fin['n_args_lossy']}")
        chk(fin["n_say"] == 1, f"n_say=1, actually got {fin['n_say']}")
        chk("eval_error" not in fin,
            f"official eval runs clean: {fin.get('eval_error')}")
        chk(fin["reward"] is not None, "reward has a value")
        chk(fin["official_reward_complete"] is True,
            f"airline basis is fully offline-scorable: miss={fin['official_reward_missing']}")
        # action can be cut out with the correct key via TAU2_CALL + first_call_named
        acts = [r for r in recs if r["type"] == "env" and r.get("action")]
        chk(len(acts) >= 1, "at least one env record carries an action")
        hit = 0
        for r in acts:
            named = first_call_named(r["action"], TAU2_CALL) or []
            if [k for k, _ in named] == list(r["tool_args"].keys()):
                hit += 1
        chk(hit >= 1, f"at least one action has its key order sliced right ({hit}/{len(acts)})")
        # Hallucinated tool names do not go into action (otherwise they pollute the tool vocabulary)
        bt = [r for r in recs if r["type"] == "env" and r.get("bad_tool")]
        chk(len(bt) == 1 and bt[0]["action"] is None and bt[0]["raw_call"],
            "hallucinated tool: action=None + raw_call keeps the string")
        # User-simulator content appears only in type='user' lines, never in any gen line
        us = [r for r in recs if r["type"] == "user"]
        chk(len(us) == 2, f"two user records (opening + one reply), actually got {len(us)}")

    # (6) retail side: the environment can be built offline, has no user-side tools, and the
    # basis for tasks 112/114 carries NL_ASSERTION
    renv = T.registry.get_env_constructor("retail")()
    chk(renv.user_tools is None, "retail has no user-side tools")
    rtasks = T.registry.get_tasks_loader("retail")("base")
    nl = sum(1 for t in rtasks if "NL_ASSERTION" in basis_of(t))
    chk((len(rtasks), nl) == (114, 112),
        f"retail base has 114 tasks, of which 112 have basis containing NL_ASSERTION, actually got "
        f"{(len(rtasks), nl)}")
    rt = next(t for t in rtasks if "NL_ASSERTION" in basis_of(t))
    _o, c, m, _n = fold_official(basis_of(rt),
                                 {"DB": 1.0, "ACTION": 1.0, "COMMUNICATE": 1.0},
                                 1.0)
    chk(c is False and m == ["NL_ASSERTION"],
        f"real retail tasks must fold to incomplete: complete={c} miss={m}")

    # (7) Piece splitting: truncate with --n first, then take modulo; the three pieces have no
    # overlap and no gaps
    ids = [t.id for t in rtasks][:10]
    shards = [ids[i::3] for i in range(3)]
    flat = [x for s in shards for x in s]
    chk(sorted(flat) == sorted(ids) and len(set(flat)) == len(ids),
        f"shards have no overlap and no gaps: {shards}")

    print(f"SELFTEST {'PASS' if ok == tot else 'FAIL'} {ok}/{tot}", flush=True)
    if ok != tot:
        sys.exit(1)


# ---------- entry point ----------

def main():
    ap = argparse.ArgumentParser()
    # Skeleton copied verbatim from envs/collect/run_alfworld.py:131-147
    ap.add_argument("--base-url")
    ap.add_argument("--model")
    ap.add_argument("--split", default="test")
    ap.add_argument("--n", type=int, default=1, help="0 = the whole split")
    ap.add_argument("--max-steps", type=int, default=40,
                    help="cap on agent generation rounds. The official DEFAULT_MAX_STEPS=200 "
                         "(tau2/config.py:4) and one tool round trip counts as 2 steps; the 40 "
                         "counts only agent rounds -- changing this value changes the termination distribution")
    ap.add_argument("--outdir")
    ap.add_argument("--exp", default="smoke")
    ap.add_argument("--preset", default="default",
                    help="a set of generation settings from configs/presets/<name>.json;"
                         " default: default; args explicitly given on the command line override preset values"
                         " (the user simulator's endpoint, model, and api are given by the --user-* trio,"
                         " temperature uses the same preset as the agent side)")
    ap.add_argument("--api", default=None, choices=["raw", "chat"],
                    help="default raw (when the preset gives none either)")
    ap.add_argument("--reasoning-effort", default=None)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--resume", action="store_true",
                    help="skip tasks already finished in outdir")
    # tau2-specific
    ap.add_argument("--domain", default="airline", choices=DOMAINS)
    ap.add_argument("--user-base-url", default=None, help="default = --base-url")
    ap.add_argument("--user-model", default=None, help="default = --model")
    ap.add_argument("--user-api", default=None, choices=["raw", "chat"],
                    help="default = --api")
    ap.add_argument("--max-errors", type=int, default=DEFAULT_MAX_ERRORS,
                    help="cap on tool errors, same value as tau2/config.py:5")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--selftest", action="store_true",
                    help="pure CPU self-test: sends no HTTP, touches no GPU")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    # --base-url/--model do not use argparse's required=True, so --selftest does not need to
    # feed a fake URL
    if not args.outdir:
        raise SystemExit("missing --outdir (required unless --selftest)")
    # When --base-url/--model are missing and the preset cannot fill them in either,
    # settings_from_args raises an error and exits
    eff = settings_from_args(args)
    args.base_url, args.model = eff["base_url"], eff["model"]
    args.api, args.reasoning_effort = eff["api"], eff["reasoning_effort"]
    args.user_base_url = args.user_base_url or args.base_url
    args.user_model = args.user_model or args.model
    args.user_api = args.user_api or args.api
    if args.user_model == args.model and args.user_base_url == args.base_url:
        print("WARN the user simulator and the agent use the same service and the same model -- talking to itself is a confound,"
              "the trajectory distribution will be skewed, and this won't show up in any number."
              "The official tau2 smoke test uses q35 as agent + q36 as user.", flush=True)

    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    # Directory-name gate (extending.md §5 #1): build.py:45-47 identifies a directory by
    # `<env>_<model_key>`; if the tail is not in rules.MODEL_OF it does `continue` and skips
    # **the whole directory**, exits 0, no message; the glob is also hard-coded as
    # `tau2_*/tau2_*.jsonl`. Both can only be warned about (a smoke directory was never meant
    # to enter annotate anyway), but the consequence must be printed, never silent.
    tail = outdir.name.rsplit("_", 1)[-1]
    if tail not in MODEL_OF:
        print(f"WARN outdir tail {tail!r} isn't in rules.MODEL_OF {sorted(MODEL_OF)} "
              f"-- annotate will silently skip the whole dir {outdir.name}/ (exits 0, no message)",
              flush=True)
    if not outdir.name.startswith("tau2_"):
        print(f"WARN outdir name {outdir.name!r} doesn't start with tau2_ -- "
              f"build.py's glob `tau2_*/tau2_*.jsonl` won't pick it up", flush=True)

    T = load_tau2()
    splits = T.registry.get_task_splits_loader(args.domain)()
    if args.split not in splits:
        raise SystemExit(f"--split {args.split} is invalid, {args.domain} only has "
                         f"{sorted(splits)} (note: **there is no val**)")
    tasks = T.registry.get_tasks_loader(args.domain)(args.split)
    for t in tasks:
        if not ID_RE.fullmatch(t.id):
            raise SystemExit(f"task id can't be used as a filename: {t.id!r}")

    chat = chat_of(eff)
    # The user simulator uses the same preset's temperature as the agent (Chat's temperature
    # must be passed)
    user_chat = Chat(args.user_base_url, args.user_model, api=args.user_api,
                     temperature=eff["temperature"],
                     reasoning_effort=args.reasoning_effort)

    # Piece splitting: truncate with --n first, then take modulo [copied from
    # envs/collect/run_alfworld.py:158-160]. Task order = the order returned by
    # get_tasks_loader (the tasks.json file order, deterministic across machines);
    # no shuffling, no sorting -- consistent with appworld.
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
        # Create a new environment instance for each task (measured: airline 0.09s / retail 0.03s)
        env = T.registry.get_env_constructor(args.domain)()
        if env.user_tools is not None:
            raise SystemExit(
                f"{args.domain} has user-side tools -- this collector only records agent-side calls, "
                f"it would silently drop user-side calls, refusing to run")
        # None = this task was cut off (empty opening, already logged a SKIP line in run_task).
        # It is not written to disk, so --resume retries it next time -- this is "not collected yet",
        # not "silently treated as collected".
        line = run_task(T, env, args.domain, task, chat, user_chat, args,
                        out_path)
        if line is not None:
            print(line, flush=True)


if __name__ == "__main__":
    main()
