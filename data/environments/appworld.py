"""The AppWorld benchmark: hands out its tasks with each task's own date, steps a model's call through a live world, says which calls change that world, speculates one call early, and judges task completion."""
from __future__ import annotations

import ast
import os
import re
import shutil
import socket
import time
from pathlib import Path

import yaml

from data.environments import Environment, StepObservation

INSTRUCTIONS = {"v1": """You are an autonomous agent operating a phone-like environment \
on behalf of your supervisor.

Rules:
- Each turn, write exactly ONE ```python ... ``` code block. It is executed \
in a persistent IPython shell and you ONLY see what is printed — always wrap \
calls whose result you need in print(...), e.g. \
print(apis.spotify.show_playlists(...))
- Call app APIs as: apis.{app_name}.{api_name}(...)
- Explore first: apis.api_docs.show_app_descriptions(), \
apis.api_docs.show_api_descriptions(app_name=...), \
apis.api_docs.show_api_doc(app_name=..., api_name=...)
- Your supervisor's identity: print(apis.supervisor.show_profile()) gives \
their email/phone; print(apis.supervisor.show_account_passwords()) gives \
their password for each app. NEVER guess usernames or passwords.
- Login pattern: token = apis.spotify.login(username=<supervisor email>, \
password=<password from the list>)["access_token"], then pass \
access_token=token to that app's other APIs.
- When the task is fully done, call apis.supervisor.complete_task() \
(pass answer=... if the task asks a question).""",
                # v2 is v1 with the last rule rewritten: AppWorld compares the answer as an exact
                # string and expects none on a task that asks for an action, and v1 said neither.
                "v2": """You are an autonomous agent operating a phone-like environment \
on behalf of your supervisor.

Rules:
- Each turn, write exactly ONE ```python ... ``` code block. It is executed \
in a persistent IPython shell and you ONLY see what is printed — always wrap \
calls whose result you need in print(...), e.g. \
print(apis.spotify.show_playlists(...))
- Call app APIs as: apis.{app_name}.{api_name}(...)
- Explore first: apis.api_docs.show_app_descriptions(), \
apis.api_docs.show_api_descriptions(app_name=...), \
apis.api_docs.show_api_doc(app_name=..., api_name=...)
- Your supervisor's identity: print(apis.supervisor.show_profile()) gives \
their email/phone; print(apis.supervisor.show_account_passwords()) gives \
their password for each app. NEVER guess usernames or passwords.
- Login pattern: token = apis.spotify.login(username=<supervisor email>, \
password=<password from the list>)["access_token"], then pass \
access_token=token to that app's other APIs.
- When the task is fully done, call apis.supervisor.complete_task(). \
If the task asks a question, pass its answer as answer=... and make it the \
bare value alone (a number, a name, yes or no), e.g. answer=4 and never \
answer="The streak is 4 days". If the task asks you to do something, call \
complete_task() with no answer."""}
SPLIT_ROLE = {"train": "train", "dev": "val", "test": "test"}

# Regex patterns as plain strings, not compiled Pattern objects: schema.py's ast.literal_eval
# scan of this file's module-level assignments (3.3) must find only INSTRUCTIONS and
# SPLIT_ROLE as non-string-literal shapes; every other module-level name here is a literal too.
CALL_START = r"apis\.(\w+)\.(\w+)\("
CODE_BLOCK = r"```python\s*(.*?)```"
IDENT = r"^[A-Za-z_]\w*$"
POSKEY = r"^pos\d+$"
ALWAYS_STR = {"app_name", "api_name"}
CKPT = "probe"
# The line put after an output that was longer than RESULT_CAP, so the model knows it read a part.
CUT_NOTE = "\n[output cut: {n} more characters not shown]"
# AppWorld documents every API with an HTTP method; GET is the one that reads. A GET that takes
# this parameter saves a file into the file system app, so it writes as well.
READ_METHOD = "GET"
FILE_WRITE_PARAM = "download_to_file_path"


def _split_args_named(argstr: str) -> list[tuple[str, str]]:
    """Quote- and bracket-aware split of an argument list on top-level commas, named or positional."""
    vals: list[str] = []
    buf = ""
    depth = 0
    quote: str | None = None
    for ch in argstr:
        if quote is not None:
            buf += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf += ch
        elif ch in "([{":
            depth += 1
            buf += ch
        elif ch in ")]}":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            vals.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        vals.append(buf.strip())

    out: list[tuple[str, str]] = []
    pos = 0
    for v in vals:
        m = re.match(r"(\w+)\s*=\s*(.+)", v, re.S)
        if m:
            out.append((m.group(1), _unwrap(m.group(2).strip())))
        else:
            out.append((f"pos{pos}", _unwrap(v.strip())))
            pos += 1
    return out


def _unwrap(value: str) -> str:
    """Take one layer of quotes off a value that is one whole string literal, else return it as it is.

    One layer is the delimiter pair of a single, double or triple quoted literal, found by the
    rules `_call_close` walks by (a backslash escapes the next character), and the value is
    unwrapped only when that literal's closing delimiter is its last character: `'say "hi"'`
    reads as `say "hi"`, while `"a" + "b"` and `f'{x}'` stay whole. No escape is undone.
    """
    if not value or value[0] not in "\"'":
        return value
    quote = value[0] * 3 if value.startswith(value[0] * 3) else value[0]
    i = len(quote)
    while i < len(value):
        if value[i] == "\\":
            i += 2
            continue
        if value.startswith(quote, i):
            return value[len(quote):i] if i + len(quote) == len(value) else value
        i += 1
    return value


def _call_close(text: str, start: int) -> int | None:
    """Index of the `)` closing the call whose `(` is at `start`; None when it never closes.

    Python source rules, so a parenthesis that belongs to a value is left alone: inside a
    string literal only the closing quote counts (single, double and triple quoted), a
    backslash escapes the next character, and `#` runs to the end of the line. This is the
    one walk `split_args` and `complete_call` both use.
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
        if c == "#":
            nl = text.find("\n", i)
            if nl < 0:
                return None
            i = nl + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _first_call_named(text: str) -> tuple[str, str, list[tuple[str, str]], int, int] | None:
    """The first `apis.<app>.<api>(...)` call in text: (app, api, named args, call start, index right after the close)."""
    m = re.search(CALL_START, text)
    if m is None:
        return None
    i = m.end() - 1
    j = _call_close(text, i)
    if j is None:
        return None
    return m.group(1), m.group(2), _split_args_named(text[i + 1:j]), m.start(), j + 1


def _closes_the_call(written: str) -> bool:
    """Whether `_call_close` still reaches the call's own `)` after `written` went in before it.

    The writer asks the reader itself rather than carrying a copy of its rules, so the two
    cannot drift: `written` is put in as the whole argument body of a one-argument call, and
    the answer is yes when the reader closes that call at the parenthesis the writer appended.
    It is no for a `#` that comments that parenthesis out, for a stray `(` or `)`, and for a
    quote the reader leaves open — including one whose closing quote a backslash escapes.
    """
    return _call_close(f"({written})", 0) == len(written) + 1


def _stays_one_argument(value: str) -> bool:
    """Whether `_split_args_named` keeps a bare `value` whole and reads its key with it.

    That reader counts every bracket kind and carries no backslash escape, and it ends an
    argument on a `,` and reads a key off an `=`, both whenever they stand outside every
    bracket and every quote. So a bare value holds neither of those two characters in the
    open, keeps its bracket depth at zero and dips below it at no point, and leaves no quote
    open — an open bracket or quote swallows the arguments that follow.
    """
    brackets = 0
    quote: str | None = None
    for ch in value:
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            brackets += 1
        elif ch in ")]}":
            brackets -= 1
            if brackets < 0:
                return False
        elif ch in ",=" and brackets == 0:
            return False
    return brackets == 0 and quote is None


def _bare_safe(value: str) -> bool:
    """Whether `value` can be written bare into a call and read back as itself.

    Both readers have to agree with the writer: `_call_close`, which has to reach the call's
    closing parenthesis, and `_split_args_named`, which has to keep the value whole. On top of
    the two the re-parse strips whitespace off the ends of a bare value, so a value that
    carries its own leading or trailing whitespace is quoted instead, and takes a layer of
    quotes off a value that is one whole string literal (`_unwrap`), so such a value is
    quoted too.
    """
    if value == "":
        return False
    if value != value.strip():
        return False
    if _unwrap(value) != value:
        return False
    return _closes_the_call(value) and _stays_one_argument(value)


def _quote_value(tool: str, key: str, value: str) -> str:
    """Bare unless the value needs protecting; never `repr()` (errata E5)."""
    if _bare_safe(value):
        return value
    has_single = "'" in value
    has_double = '"' in value
    if has_single and has_double:
        raise ValueError(
            f"appworld.build_call: {tool} argument {key!r} value {value!r} holds both a single and a double quote"
        )
    q = '"' if has_single else "'"
    wrapped = f"{q}{value}{q}"
    if _closes_the_call(wrapped):
        return wrapped
    raise ValueError(
        f"appworld.build_call: {tool} argument {key!r} value {value!r} needs quoting and ends in a backslash "
        f"that escapes its closing {q}, so the call it would be written into never closes"
    )


def _requote(call: str, user_ns: dict) -> tuple[str, list[str]]:
    """Turn a dequoted predicted call string into executable python, and record which branch each argument took."""
    found = _first_call_named(call or "")
    if found is None:
        return f"print({call})", ["unparsable_raw"]
    app, api, named, _, _ = found
    tool = f"apis.{app}.{api}"
    parts: list[str] = []
    modes: list[str] = []
    for key, value in named:
        positional = bool(re.match(POSKEY, key))
        if key in ALWAYS_STR:
            piece, mode = repr(value), "forced_str"
        else:
            try:
                ast.literal_eval(value)
                piece, mode = value, "literal"
            except Exception:
                if re.match(IDENT, value) and value in user_ns:
                    piece, mode = value, "shell_var"
                else:
                    piece, mode = repr(value), "quoted"
        parts.append(piece if positional else f"{key}={piece}")
        modes.append(("pos_" + mode) if positional else mode)
    return f"print({tool}({', '.join(parts)}))", modes


def _error_kind(out: str | None) -> str | None:
    """Classify an `execute()` return's error kind; None when it is not an error."""
    if out is None or not out.startswith("Execution failed"):
        return None
    if "timed out" in out:
        return "timeout"
    if "Syntax error in line" in out:
        return "SyntaxError"
    m = re.search(r"Response status code is (\d+)", out)
    if m:
        return f"http_{m.group(1)}"
    for line in reversed([x.strip() for x in out.splitlines() if x.strip()]):
        m = re.match(r"^([A-Za-z_][\w.]*)\s*:", line)
        if m:
            return m.group(1).rsplit(".", 1)[-1]
    return "unknown"


class AppWorld(Environment):
    """The AppWorld benchmark: one Python code block per turn, executed in a persistent shell."""

    NAME = "appworld"
    INSTRUCTIONS = INSTRUCTIONS
    NO_CODE_MESSAGE = "No ```python``` block found. Reply with exactly one python code block."
    # The longest API list of one app (spotify, 91 APIs) prints about 9,100 characters; at the
    # earlier 4,000 it lost the player calls the tasks needed, with nothing saying it was cut.
    RESULT_CAP = 12000
    SEED = 100
    SPLIT_ROLE = SPLIT_ROLE

    def __init__(self) -> None:
        path = Path(__file__).resolve().parents[2] / "constants" / "path_datasets.yaml"
        with open(path) as f:
            block = yaml.safe_load(f)["appworld"]
        self.home = block["home"]
        self.data = block["data"]
        self.splits = block["splits"]
        if self.data != f"{self.home}/data":
            raise ValueError(f"appworld: constants/path_datasets.yaml data {self.data!r} is not <home>/data")
        self._world = None
        self._experiment_name: str | None = None
        self._clock: str | None = None
        self.task_text: str | None = None
        self.task_date: str | None = None

    def tasks(self, split: str) -> list[str]:
        if split not in self.splits:
            raise ValueError(f"appworld.tasks: unknown split {split!r}, has {sorted(self.splits)}")
        text = Path(self.splits[split]).read_text()
        return [line for line in text.split("\n") if line]

    def split_args(self, text: str) -> tuple[str, list[tuple[str, str]], tuple[int, int]] | None:
        found = _first_call_named(text)
        if found is None:
            return None
        app, api, args, start, end = found
        return f"apis.{app}.{api}", args, (start, end)

    def build_call(self, tool: str, args: list[tuple[str, str]]) -> str:
        parts = []
        for key, value in args:
            quoted = _quote_value(tool, key, value)
            parts.append(quoted if re.match(POSKEY, key) else f"{key}={quoted}")
        return f"{tool}({', '.join(parts)})"

    def complete_call(self, text: str) -> str | None:
        s = text or ""
        m = re.search(CALL_START, s)
        if m is None:
            return None
        j = _call_close(s, m.end() - 1)
        if j is None:
            return None
        return s[m.start():j + 1]

    def open(self, task_id: str, seed: int) -> None:
        os.environ["APPWORLD_ROOT"] = self.home
        from appworld import AppWorld as _World

        # This name is the world's working directory under <home>/experiments/outputs/, and
        # close() below removes it. Two runs may hold the same task at the same time (a baseline
        # sample beside an inject run, a --debug walk beside a real one), so the name carries
        # the host and the id of this process next to the task and the seed: one process holds
        # one world at a time, and no other process ever has this directory.
        experiment_name = f"{task_id}__s{seed}__{socket.gethostname()}_{os.getpid()}"
        world = _World(task_id=task_id, experiment_name=experiment_name, random_seed=self.SEED)
        self._world = world
        self._experiment_name = experiment_name
        self.task_text = world.task.instruction
        # The day the task's world is set on (2023-05-18 for most tasks, other days for some):
        # the date the model is told, so "yesterday" and "last year" mean what the task means.
        self.task_date = world.task.datetime.date().isoformat()
        clock = world.execute("print(DateTime.now())").strip()
        self._clock = None if clock.startswith("Execution failed") else clock

    def _capped(self, out: str) -> str:
        """`out` whole when it fits RESULT_CAP characters, else its first RESULT_CAP characters and one line saying how many were left out."""
        if len(out) <= self.RESULT_CAP:
            return out
        return out[:self.RESULT_CAP] + CUT_NOTE.format(n=len(out) - self.RESULT_CAP)

    def step(self, reply_text: str) -> StepObservation:
        m = re.search(CODE_BLOCK, reply_text, re.S)
        if m is None:
            return StepObservation(None, "NO_CODE_BLOCK", None, False)
        code = m.group(1)
        out = self._capped(str(self._world.execute(code)))
        return StepObservation(code, out, _error_kind(out), self._world.task_completed())

    def changes_state(self, call: str) -> bool:
        """Whether running `call` would leave the world different from before it: its first API call is one AppWorld documents with a method other than GET, or a GET that saves a file.

        A text with no call in it, and a call to an API the task's apps do not have, change
        nothing: the first runs no API and the second fails before it reaches an app.
        """
        if self._world is None:
            raise RuntimeError("appworld.changes_state: called before open")
        found = _first_call_named(call or "")
        if found is None:
            return False
        app, api = found[0], found[1]
        docs = self._world.task.api_docs
        if app not in docs or api not in docs[app]:
            return False
        doc = docs[app][api]
        saves_a_file = any(p["name"] == FILE_WRITE_PARAM for p in doc["parameters"])
        return doc["method"] != READ_METHOD or saves_a_file

    def speculate(self, call: str) -> dict:
        if self._world is None:
            raise RuntimeError("appworld.speculate: called before open")
        if self._clock is None:
            raise RuntimeError("appworld.speculate: open recorded no frozen clock, refusing the drift guard")
        world = self._world
        t0 = time.clock_gettime(time.CLOCK_MONOTONIC)
        code_x, modes = _requote(call, world.shell.user_ns)
        world.save_state(CKPT)
        try:
            exec_out = self._capped(str(world.execute(code_x)))
        finally:
            world.load_state(CKPT)
            world._set_datetime()
            now = world.execute("print(DateTime.now())").strip()
            if now != self._clock:
                raise RuntimeError(f"appworld.speculate: clock drifted after restore: {now!r} != {self._clock!r}")
        spec_s = time.clock_gettime(time.CLOCK_MONOTONIC) - t0
        error_kind = _error_kind(exec_out)
        return {
            "exec_code": code_x,
            "arg_modes": modes,
            "exec_out": exec_out,
            "exec_ok": error_kind is None,
            "error_kind": error_kind,
            "spec_s": spec_s,
        }

    def judge(self) -> dict:
        try:
            ev = self._world.evaluate()
            d = ev.to_dict() if hasattr(ev, "to_dict") else ev
            if not (isinstance(d, dict) and isinstance(d.get("success"), bool)):
                raise ValueError(f"appworld.judge: evaluate() returned a shape with no boolean success: {d!r}")
            return d
        except Exception as exc:
            return {"success": False, "eval_error": str(exc)[:600]}

    # TODO(gyb, 2026-09-22): a piece that is killed never reaches close(), and the directory's
    # name carries its process id, so no later run reuses or removes it (the old name was taken
    # again by the next run of the same task). <home>/experiments/outputs/ held 368 directories
    # and 330 MB on 2026-09-22. If it matters: a sweep of names whose process is gone on this host.
    def close(self) -> None:
        if self._world is None:
            return
        self._world.close()
        shutil.rmtree(Path(self.home) / "experiments" / "outputs" / self._experiment_name, ignore_errors=True)
        self._world = None
        self._experiment_name = None
        self.task_text = None
        self.task_date = None
        self._clock = None
