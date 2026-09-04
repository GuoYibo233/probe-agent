"""rl_lib: shared library behind bin/rl.

Everything here transcribes a rule from plans/research-loop-parts/; each function
cites the part and line it carries (written as `03 L19`). Build step 3a delivers the
table loaders, exit codes, actor resolution, the lock and the ledger readers; step 3b
fills in the writers and validators (marked TODO(3b)).

Layout (08 L81-98): tables/ and schemas/ next to this file's parent directory; the
research repo is found by walking up from the working directory to the directory that
holds research-loop.json (08 L17).
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TABLES_DIR = PLUGIN_ROOT / "tables"
SCHEMAS_DIR = PLUGIN_ROOT / "schemas"
COMMON_DIR = PLUGIN_ROOT / "common"

ROLES = ("idea", "deploy", "run", "analysis", "reviewer")
ACTORS = ROLES + ("gyb",)
CLI_SESSION = "cli"  # a bare terminal records session_id cli (03 L40; 01 L69)

# Environment seams. CLAUDE_CODE_SESSION_ID is the session id in the Bash of a Claude Code
# session and equals the hook input's session_id (verify item 1 closed:
# plans/2026-09-05-research-loop-verify.md section 2.7); RL_SESSION_ID overrides it for tests.
ENV_SESSION_ID = "CLAUDE_CODE_SESSION_ID"
ENV_SESSION_ID_OVERRIDE = "RL_SESSION_ID"
# The plugin hook sets RL_CALLER=hook when it calls `rl session start/end`; the who column
# of those two commands is "hook, gyb" (05 L40). Construction seam, see tables/README.md.
ENV_CALLER = "RL_CALLER"
# Tests point rl at a sandbox copy of common/ so `feedback accept` writing rules_version
# back (09 L59) never touches the plugin tree. Construction seam, see tests/helpers.py.
ENV_COMMON_DIR = "RL_COMMON_DIR"


# ---------------------------------------------------------------- tables and schemas

def _load_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_table(name: str):
    """Load tables/<name>.json (name may be `roles/idea`)."""
    return _load_json(TABLES_DIR / f"{name}.json")


LEDGERS_TABLE = load_table("ledgers")
LEDGERS = {row["name"]: row for row in LEDGERS_TABLE["ledgers"]}
LEDGER_NAMES = list(LEDGERS)  # nine names, 03 L47-57
COMMANDS_TABLE = load_table("commands")
COMMANDS = {row["name"]: row for row in COMMANDS_TABLE["commands"]}
QUERY_KINDS = tuple(COMMANDS_TABLE["query_kinds"])  # 05 L100
TRANSITIONS = load_table("transitions")
EXIT_CODES_TABLE = load_table("exit_codes")
CONFIG_DEFAULTS = load_table("config_defaults")
GYB_USECASES = load_table("gyb-usecases")


def load_role(role: str) -> dict:
    if role not in ROLES:
        raise RLError("usage", f"unknown role {role!r}; roles are {', '.join(ROLES)}")
    return load_table(f"roles/{role}")


def load_schema(ledger: str) -> dict | None:
    entry = LEDGERS[ledger]
    if not entry.get("schema"):
        return None
    return _load_json(PLUGIN_ROOT / entry["schema"])


def write_commands_for(role_table: dict, ledger: str) -> list[str]:
    """Expand a role's ledger_writes entry for one ledger into full command names.

    `"*"` means every write command whose `ledger` in commands.json is that ledger;
    `decisions.<book>` keys map onto the decisions ledger (06 L180, tables/README.md).
    """
    key = ledger
    if ledger.startswith("decisions."):
        key = ledger
        ledger = "decisions"
    spec = role_table["ledger_writes"].get(key)
    if spec is None:
        return []
    if spec == "*":
        return [n for n, c in COMMANDS.items() if c["ledger"] == ledger and c["kind"] == "write"]
    return list(spec)


# ---------------------------------------------------------------- exit codes and errors

EXIT_BY_KIND = {row["kind"]: row["code"] for row in EXIT_CODES_TABLE["codes"] if row["kind"]}
# validation=2, forbidden=3, lock_timeout=4, usage=5, internal=1 (03 L217-226)


class RLError(Exception):
    """A refused command. `kind` is the fixed reason kind printed on the first stderr
    line and put into error.kind with --json (03 L226); `next_step` is the sentence that
    tells the caller what to do next (03 L221, L222, L224)."""

    def __init__(self, kind: str, message: str, next_step: str = "", details: dict | None = None):
        super().__init__(message)
        if kind not in EXIT_BY_KIND:
            raise ValueError(f"unknown error kind {kind!r}")
        self.kind = kind
        self.code = EXIT_BY_KIND[kind]
        self.message = message
        self.next_step = next_step
        self.details = details or {}

    def emit(self, as_json: bool) -> int:
        """03 L226: the first stderr line is always the kind; with --json the same value
        also goes to stdout as error.kind (both hold at once)."""
        print(self.kind, file=sys.stderr)
        print(self.message, file=sys.stderr)
        if self.next_step:
            print(self.next_step, file=sys.stderr)
        if as_json:
            payload = {"error": {"kind": self.kind, "code": self.code, "message": self.message,
                                 "next_step": self.next_step, **self.details}}
            print(json.dumps(payload, ensure_ascii=False))
        return self.code


def issue_command_for_gyb(text: str = "<what you need gyb to decide>") -> str:
    """The 'open an issue to gyb' command attached to exit 3 (03 L27, L222)."""
    return f"rl issue open --to gyb --kind request --text \"{text}\""


# ---------------------------------------------------------------- repo, config, paths

def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default cwd) to the directory holding research-loop.json.

    The research repo tree is defined in 08 L7-32; the config file is the marker."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / "research-loop.json").is_file():
            return candidate
    raise RLError("usage", "not inside a research repo: no research-loop.json found upwards from "
                  f"{cur}", "run `rl init` in the repo root from a bare terminal (08 L9)")


def load_config(repo: Path) -> dict:
    """research-loop.json with threshold defaults filled in (08 L57-79)."""
    cfg = _load_json(repo / "research-loop.json")
    for row in CONFIG_DEFAULTS["thresholds"]:
        cfg.setdefault(row["key"], row["default"])
    for row in CONFIG_DEFAULTS["keys"]:
        cfg.setdefault(row["key"], row["default"])
    return cfg


def loop_dir(repo: Path) -> Path:
    return repo / LEDGERS_TABLE["dir"]


def ledger_path(repo: Path, ledger: str, book: str | None = None) -> Path:
    """loop/<ledger>.jsonl; decisions needs a book (six files, 02 L9)."""
    entry = LEDGERS[ledger]
    if ledger == "decisions":
        if book not in entry["books"]:
            raise RLError("usage", f"decisions needs a book, one of {', '.join(entry['books'])}")
        return repo / entry["file"].replace("<actor>", book)
    return repo / entry["file"]


def sessions_state_dir(repo: Path) -> Path:
    return loop_dir(repo) / ".sessions"  # 06 L118


def rules_version(repo_or_plugin_common: Path | None = None) -> int:
    """First line of common/GLOBAL-RULES.md is `rules_version: N` (09 L59; agreed with the
    text session 2026-09-05: first line, colon, one space, integer)."""
    common = repo_or_plugin_common or Path(os.environ.get(ENV_COMMON_DIR) or COMMON_DIR)
    path = common / "GLOBAL-RULES.md"
    try:
        first = path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        raise RLError("internal", f"cannot read rules_version from {path}")
    m = re.fullmatch(r"rules_version: (\d+)", first.strip())
    if not m:
        raise RLError("internal", f"first line of {path} is not `rules_version: N`: {first!r}")
    return int(m.group(1))


# ---------------------------------------------------------------- session identity and actor

def current_session_id(env: dict | None = None) -> str | None:
    env = env if env is not None else os.environ
    return env.get(ENV_SESSION_ID_OVERRIDE) or env.get(ENV_SESSION_ID)


def read_state_file(repo: Path, session_id: str | None) -> dict | None:
    """loop/.sessions/<session_id>.json written by the plugin hook when a role skill is
    loaded (06 L118). Missing file means a bare terminal."""
    if not session_id:
        return None
    path = sessions_state_dir(repo) / f"{session_id}.json"
    if not path.is_file():
        return None
    return _load_json(path)


class Actor:
    """Who is writing (01 L63-72; 05 L11-25).

    role_session: the role of the session the command came from, None for a bare terminal.
    actor: the actor recorded on the row (a role, or gyb).
    session_id: recorded on the row; cli for a bare terminal.
    quote: gyb's words, required for --as-gyb from a role session (01 L70).
    """

    def __init__(self, role_session: str | None, actor: str, session_id: str, quote: str | None = None,
                 agent_id: str | None = None):
        self.role_session = role_session
        self.actor = actor
        self.session_id = session_id
        self.quote = quote
        self.agent_id = agent_id  # subagent rows carry it (proxy decision D-15)

    @property
    def is_gyb(self) -> bool:
        return self.actor == "gyb"

    @property
    def bare_terminal(self) -> bool:
        return self.role_session is None


def resolve_actor(repo: Path, as_gyb: bool = False, quote: str | None = None,
                  env: dict | None = None) -> Actor:
    """01 L69-70: a bare terminal (no state file) is gyb with session_id cli and needs no
    flag; a role session writes as its role; --as-gyb in a role session writes as gyb,
    keeps the session_id and must carry --quote (missing quote is exit 2).

    Subagents (proxy decision D-15, verify item 5): the hook injects RL_AGENT_TYPE and
    RL_AGENT_ID; the role comes from the agent type, the session_id stays the parent's,
    agent_id is carried onto every row the subagent writes."""
    env = env if env is not None else os.environ
    sid = current_session_id(env)
    # Subagent branch (proxy decision D-15; plans/2026-09-05-research-loop-verify.md 2.4-2.5):
    # the write hook injects RL_AGENT_TYPE and RL_AGENT_ID into a subagent's Bash commands
    # (export form, D-15 addendum); the subagent shares the parent's session_id, so the
    # role comes from the agent type, not from the state file.
    agent_role = role_from_agent_type(env.get("RL_AGENT_TYPE"))
    if env.get("RL_AGENT_TYPE") and agent_role is None:
        raise RLError("forbidden", f"unknown agent type {env.get('RL_AGENT_TYPE')!r}",
                      "subagents are started with the five plugin agent types (06 L102)")
    state = read_state_file(repo, sid)
    if agent_role is None and state is None:
        return Actor(None, "gyb", CLI_SESSION)
    role = agent_role or state.get("role")
    if role not in ROLES:
        raise RLError("internal", f"state file for session {sid} has no valid role: {state!r}")
    agent_id = env.get("RL_AGENT_ID") if agent_role else None
    if as_gyb:
        if not quote:
            raise RLError("validation", "--as-gyb in a role session needs --quote \"<gyb's words>\"",
                          "add --quote with the sentence gyb said (01 L70)")
        return Actor(role, "gyb", sid, quote, agent_id)
    return Actor(role, role, sid, agent_id=agent_id)


def check_force(actor: Actor, force: bool, reason: str | None) -> None:
    """--force is gyb's right (03 L27; 01 L90): a role using it is exit 3 with the
    open-an-issue command; gyb must give --reason, recorded as force_reason."""
    if not force:
        return
    if not actor.is_gyb:
        raise RLError("forbidden", "--force is gyb's right; a role command with --force is refused",
                      "ask gyb: " + issue_command_for_gyb("please force-write this row"))
    if not reason:
        raise RLError("validation", "--force needs --reason", "add --reason \"<why>\"; it is recorded as force_reason (03 L27)")


# ---------------------------------------------------------------- lock and ledger IO

class Lock:
    """loop/.lock, one global file lock; scan, assign and append happen inside it
    (03 L19). Waits lock.timeout_seconds (default 10) then exit 4 (03 L223)."""

    def __init__(self, repo: Path, timeout_seconds: float | None = None):
        self.path = loop_dir(repo) / ".lock"
        if timeout_seconds is None:
            timeout_seconds = load_config(repo)["lock.timeout_seconds"]
        self.timeout = float(timeout_seconds)
        self._fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self._fh.close()
                    self._fh = None
                    raise RLError("lock_timeout", f"could not take {self.path} within {self.timeout:g}s")
                time.sleep(0.02)

    def __exit__(self, *exc):
        if self._fh is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None


def read_rows(repo: Path, ledger: str, book: str | None = None) -> list[dict]:
    """All rows of one ledger file in file order (history included, 03 L11)."""
    path = ledger_path(repo, ledger, book)
    if not path.is_file():
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_decisions(repo: Path) -> list[dict]:
    rows = []
    for book in LEDGERS["decisions"]["books"]:
        rows.extend(read_rows(repo, "decisions", book))
    return rows


def key_field(ledger: str) -> str:
    return LEDGERS[ledger]["key"]


def session_key(session_id: str, agent_id: str | None) -> str:
    """sessions rows are chained per (session_id, agent_id or empty) (proxy decision D-15)."""
    return f"{session_id}#{agent_id}" if agent_id else session_id


def row_key(ledger: str, row: dict) -> str:
    if ledger == "sessions":
        return session_key(row["session_id"], row.get("agent_id"))
    return row[key_field(ledger)]


def latest(rows: list[dict], ledger: str) -> dict[str, dict]:
    """Latest version per key (03 L11, L36); sessions key on (session_id, agent_id)."""
    out: dict[str, dict] = {}
    for row in rows:
        k = row_key(ledger, row)
        if k not in out or row["version"] > out[k]["version"]:
            out[k] = row
    return out


_NUM_RE = re.compile(r"-(\d+)$")


def next_number(existing_ids: list[str], prefix: str, width: int = 4) -> str:
    """Numbering (03 L21): sequence from 1, four digits minimum, numeric order, never
    reissued. Call inside the lock."""
    top = 0
    for ident in existing_ids:
        if ident.startswith(prefix + "-"):
            m = _NUM_RE.search(ident)
            if m:
                top = max(top, int(m.group(1)))
    return f"{prefix}-{top + 1:0{width}d}"


def append_row(repo: Path, ledger: str, row: dict, book: str | None = None) -> None:
    """Append one json line. Callers hold the lock and have validated the row.
    TODO(3b): validation (schema + x-conditions + transition table + who-can-call)
    goes in front of this call, see validate_row()."""
    path = ledger_path(repo, ledger, book)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def skeleton(actor: Actor, status: str, version: int, force_reason: str | None = None,
             via: str | None = None) -> dict:
    """The seven common fields plus the two optional ones (03 L31-43)."""
    row = {
        "version": version,
        "status": status,
        "ts": now_iso(),
        "actor": actor.actor,
        "session_id": actor.session_id,
        "schema_version": 1,
    }
    if force_reason:
        row["force_reason"] = force_reason
    if via:
        row["via"] = via
    if actor.agent_id:
        row["agent_id"] = actor.agent_id
    return row


# ---------------------------------------------------------------- validation layer

def check_writer_alive(repo: Path, actor: Actor) -> None:
    """03 L15: a write whose session_id has a latest sessions row with status closed is
    refused with exit 3; nothing overrides it. Bare terminals (cli) are never closed."""
    if actor.bare_terminal:
        return
    rows = latest(read_rows(repo, "sessions"), "sessions")
    row = rows.get(session_key(actor.session_id, actor.agent_id))
    if row is not None and row["status"] == "closed":
        raise RLError("forbidden", f"session {actor.session_id} has been closed",
                      "reload the role to register a new session; --force cannot override this (03 L15)")


def role_book(actor: Actor) -> str:
    """Which decisions book a session writes: the role's, or gyb's from a bare terminal
    (02 L11). A role session writing --as-gyb still uses the role's book."""
    return actor.role_session or "gyb"


def check_who_can_call(actor: Actor, command: str, env: dict | None = None) -> None:
    """Who-can-call (05 command table, role json ledger_writes); gyb is exempt (01 L65).

    Rules carried: `init` is refused inside a role session (05 L39, 08 L9); `session
    start` / `session end` are the hook's or gyb's (05 L40; the hook marks itself with
    RL_CALLER=hook); every other write must be in the role's ledger_writes (06 L156);
    query commands are open to everyone (05 L100)."""
    env = env if env is not None else os.environ
    spec = COMMANDS[command]
    if spec["kind"] == "query":
        return
    if actor.is_gyb:
        return
    role = actor.role_session
    if spec["kind"] == "admin":
        raise RLError("forbidden", f"rl {command} runs only from a bare terminal, not inside a {role} session",
                      "open a bare terminal (no role loaded) and run it there (08 L9)")
    if command in ("session start", "session end"):
        if env.get(ENV_CALLER) == "hook":
            return
        raise RLError("forbidden", f"rl {command} is called by the plugin hook or by gyb, not by a {role} session",
                      "let the hook register and close sessions (04 L118-120)")
    table = load_role(role)
    ledger = spec["ledger"]
    if ledger == "decisions":
        allowed = write_commands_for(table, f"decisions.{role}")
    elif ledger is None:
        allowed = []  # reclaim, doctor --ack/--unack: gyb only (05 L94-95)
    else:
        allowed = write_commands_for(table, ledger)
    if command not in allowed:
        raise RLError("forbidden", f"{role} may not run `rl {command}` (not in its ledger_writes, tables/roles/{role}.json)",
                      "ask the owner of that ledger, or gyb: " + issue_command_for_gyb(f"{role} needs `rl {command}`"))


_SCHEMA_CACHE: dict[str, dict] = {}


def merged_schema(ledger: str) -> dict:
    """The ledger schema with the skeleton's properties folded in (draft-07 $ref to a
    sibling file is resolved by hand so no resolver is needed)."""
    if ledger in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[ledger]
    schema = load_schema(ledger)
    if schema is None:
        raise RLError("usage", f"ledger {ledger} has no schema", "see tables/ledgers.json pending")
    skel = _load_json(SCHEMAS_DIR / "_skeleton.schema.json")
    merged = dict(schema)
    merged.pop("allOf", None)
    merged.pop("$id", None)  # a repo-relative $id makes jsonschema 3.2.0 resolve internal refs as URLs
    props = dict(skel["properties"])
    props.update(schema.get("properties", {}))
    merged["properties"] = props
    merged["required"] = sorted(set(skel["required"]) | set(schema.get("required", [])))
    _SCHEMA_CACHE[ledger] = merged
    return merged


def validate_shape(ledger: str, row: dict, skip_required: bool = False) -> None:
    """Types, enums, patterns and unconditional required fields (schemas/*.schema.json).
    skip_required=True (gyb --force --reason, 03 L27) keeps the type, enum and pattern
    checks and drops only the required lists, so a forced row still fits the ledger."""
    schema = merged_schema(ledger)
    if skip_required:
        schema = {k: v for k, v in schema.items() if k != "required"}
        props = {}
        for name, prop in schema.get("properties", {}).items():
            props[name] = {k: v for k, v in prop.items() if k not in ("required", "minItems")} if isinstance(prop, dict) else prop
        schema["properties"] = props
    try:
        import jsonschema  # system python has 3.2.0; the hook runs with the same interpreter
    except ImportError:  # pragma: no cover - fall back to the required-field check only
        missing = [k for k in schema.get("required", []) if k not in row]
        if missing:
            raise RLError("validation", f"{ledger} row is missing {', '.join(missing)}")
        return
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        where = "/".join(str(p) for p in e.path) or "(row)"
        raise RLError("validation", f"{ledger} row rejected at {where}: {e.message}",
                      f"fix the field and retry (schemas/{ledger}.schema.json)")


def _condition_holds(cond: dict, row: dict, book: str | None) -> bool:
    """The small `if` language used by schemas/*.x-conditions."""
    for key, want in cond.items():
        if key == "status_in":
            if row.get("status") not in want:
                return False
        elif key == "status_not":
            if row.get("status") == want:
                return False
        elif key == "kind_in":
            if row.get("kind") not in want:
                return False
        elif key == "session_id_not":
            if row.get("session_id") == want:
                return False
        elif key == "version_gt":
            if not row.get("version", 0) > want:
                return False
        elif key == "book":
            if book != want:
                return False
        elif key == "has":
            if want not in row:
                return False
        else:
            if row.get(key) != want:
                return False
    return True


def check_conditions(ledger: str, row: dict, book: str | None = None) -> None:
    """Required-by-status (03 L13): apply every x-conditions entry that has `if` and
    `then_required`. Entries with prose `then`/`rule` are carried by the handlers."""
    schema = load_schema(ledger) or {}
    for cond in schema.get("x-conditions", []):
        if "if" not in cond or "then_required" not in cond:
            continue
        if not _condition_holds(cond["if"], row, book):
            continue
        # a present empty list (released_handoffs: []) is a value; "at least one" rules
        # live in the schema (minItems) or the transition preconditions (04 L32)
        missing = [k for k in cond["then_required"] if row.get(k) in (None, "")]
        if missing:
            raise RLError("validation",
                          f"{ledger} row with {cond['if']} needs {', '.join(missing)} ({cond.get('source', '')})",
                          "add the missing field(s); gyb may bypass with --force --reason (03 L27)")


def validate_row(repo: Path, ledger: str, row: dict, actor: Actor, command: str,
                 book: str | None = None, force: bool = False, internal: bool = False) -> None:
    """Order of checks (03 L15, L27; 05 L21): writer session alive -> who can call ->
    shape -> required-by-status. `force` (gyb only, checked by check_force) skips the
    completeness checks (shape and required-by-status), never the first two."""
    if command != "session start":
        # proxy decision D-28: `session start` is the way back after a session was closed
        # (03 L15 "reload the role"), so it alone is exempt from the closed-session refusal
        # and writes the next open version of the same chain.
        check_writer_alive(repo, actor)
    if not internal:
        # internal=True: rows rl writes on its own behalf (session end's release rows,
        # notices, session amend's own who rule, 03 L176), where the ledger_writes table
        # does not apply
        check_who_can_call(actor, command)
    # 03 L27; 01 L90: gyb's --force --reason bypasses the completeness checks (required
    # fields, existence) but never the shape: types, enums and patterns still hold.
    validate_shape(ledger, row, skip_required=force)
    if not force:
        check_conditions(ledger, row, book)


# ---------------------------------------------------------------- transition table

def transition_rows() -> list[dict]:
    return TRANSITIONS["rows"]


def find_transition(subcommand: str, from_status: str | None, quick_lane: bool = False) -> dict:
    """The row of tables/transitions.json for this sub-command and current status;
    a transition not in the table is exit 2 for everyone (04 L55)."""
    head = subcommand.split(" --")[0]
    matches = []
    for row in transition_rows():
        sub = row["subcommand"].split(" [")[0].split(" --")[0]
        if sub != head:
            continue
        if row["subcommand"].startswith(head + " --quick-lane") != subcommand.startswith(head + " --quick-lane"):
            continue
        frm = row["from"]
        if frm is None:
            if from_status is None:
                matches.append(row)
        elif from_status is not None and from_status in (frm if isinstance(frm, list) else [frm]):
            matches.append(row)
    if not matches:
        raise RLError("validation", f"`rl {subcommand}` from status {from_status!r} is not in the transition table",
                      "look up tables/transitions.json; --force cannot add a transition (04 L55); to change status use withdraw then reopen")
    return matches[0]


def check_who_can_write(trow: dict, actor: Actor, order: dict | None, env: dict | None = None,
                        issue_answerer_role: str | None = None) -> None:
    """The who_can_write column (04 L59-76) with gyb exempt (04 L57 header rule 1)."""
    if actor.is_gyb:
        return
    env = env if env is not None else os.environ
    role = actor.role_session
    allowed = trow["who_can_write"]
    ok = False
    for who in allowed:
        if who in ROLES and role == who:
            ok = True
        elif who == "from_role" and order is None:
            ok = True  # opening: from_role is the writer's role
        elif who in ("from_role", "owner") and order is not None and order.get("from_role") == role:
            ok = True
        elif who == "to_role" and order is not None and order.get("to_role") == role:
            ok = True
        elif (who == "holder" and order is not None and order.get("holder") == actor.session_id
              and (order.get("agent_id") or None) == (actor.agent_id or None)):
            ok = True  # proxy decision D-15 addendum: holder pairs (session_id, agent_id or empty)
        elif who == "session_end_hook" and env.get(ENV_CALLER) == "hook":
            ok = True
        elif who == "issue_answerer" and issue_answerer_role == role:
            ok = True
        # "reclaim" is gyb's command, covered by the exemption above
    if not ok:
        raise RLError("forbidden", f"{role} may not write `rl {trow['subcommand']}` on this order (who_can_write: {', '.join(allowed)}; {trow['_source']})",
                      "ask the owner, or gyb: " + issue_command_for_gyb(f"{role} needs `rl {trow['subcommand']}`"))


def role_from_agent_type(agent_type: str | None) -> str | None:
    """A subagent's agent_type is `research-loop:<role>` when started from the plugin's
    agents/ (plans/2026-09-05-research-loop-verify.md section 4) and the bare role name
    when given through --agents (same file, 2.1); both spellings are accepted; unknown
    names give None (06 L102)."""
    if not agent_type:
        return None
    name = agent_type.rsplit(":", 1)[-1]
    return name if name in ROLES else None


# ---------------------------------------------------------------- shared write pipeline (interface for rl_cmds)

def parse_args(args: list[str], multi: tuple[str, ...] = (), flags: tuple[str, ...] = ()) -> tuple[list[str], dict]:
    """Small option parser for handlers: `--name value` pairs; names in `multi` collect a
    list; names in `flags` are booleans; everything else is positional (03 L224: a wrong
    argument is exit 5 usage)."""
    positional: list[str] = []
    opts: dict = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            name = a[2:]
            if "=" in name:
                name, value = name.split("=", 1)
            elif name in flags:
                opts[name] = True
                i += 1
                continue
            else:
                if i + 1 >= len(args):
                    raise RLError("usage", f"--{name} needs a value")
                value = args[i + 1]
                i += 1
            if name in multi:
                opts.setdefault(name, []).append(value)
            else:
                opts[name] = value
        else:
            positional.append(a)
        i += 1
    return positional, opts


def context(ctx: dict) -> tuple[Path, Actor, bool, str | None]:
    """(repo, actor, force, force_reason) for a handler; runs the actor and --force
    rules (01 L63-90)."""
    repo = find_repo_root()
    opts = ctx["opts"]
    actor = resolve_actor(repo, as_gyb=opts.get("as_gyb", False), quote=opts.get("quote"))
    force = bool(opts.get("force"))
    check_force(actor, force, opts.get("reason"))
    return repo, actor, force, (opts.get("reason") if force else None)


def write_row(repo: Path, ledger: str, fields: dict, actor: Actor, command: str, *, status: str,
              version: int, book: str | None = None, force: bool = False, force_reason: str | None = None,
              via: str | None = None, internal: bool = False) -> dict:
    """Build skeleton + fields, validate (writer alive, who-can-call, shape, status-bound
    required unless gyb --force), append. The caller holds the Lock and has assigned ids
    inside it (03 L19)."""
    row = skeleton(actor, status, version, force_reason=force_reason, via=via)
    row.update(fields)
    if actor.quote and "quote" not in row and actor.is_gyb and not actor.bare_terminal:
        row["quote"] = actor.quote  # 01 L70: --as-gyb rows carry the quote
    validate_row(repo, ledger, row, actor, command, book=book, force=force, internal=internal)
    append_row(repo, ledger, row, book)
    return row


def next_version_of(repo: Path, ledger: str, key_value: str, book: str | None = None) -> tuple[dict | None, int]:
    """(latest row or None, next version number) for one key (03 L11, L36). For sessions
    pass session_key(session_id, agent_id) (proxy decision D-15)."""
    rows = read_rows(repo, ledger, book) if ledger != "decisions" or book else read_decisions(repo)
    best = None
    for r in rows:
        if row_key(ledger, r) == key_value and (best is None or r["version"] > best["version"]):
            best = r
    return best, (best["version"] + 1 if best else 1)


def result(row: dict, ledger: str, extra: dict | None = None) -> dict:
    """--json result: at least the row key and version (tests/helpers.py)."""
    out = {key_field(ledger): row[key_field(ledger)], "version": row["version"], "status": row["status"]}
    if extra:
        out.update(extra)
    return out


SKELETON_KEYS = ("version", "status", "ts", "actor", "session_id", "schema_version", "force_reason", "via", "agent_id")
VERSION_ONLY_KEYS = ("adopted", "quote")  # 04 L29: adopted belongs to the start version only; quote to the version it was said on


def copy_content(row: dict) -> dict:
    """The content of `row` for the next version: skeleton keys and version-only keys
    dropped (03 L11: a change is one more complete row). One copy rule for every
    module (reviewer note on 71c7c1b)."""
    return {k: v for k, v in row.items() if k not in SKELETON_KEYS and k not in VERSION_ONLY_KEYS}


def owner_of(order: dict) -> str:
    """Owner is from_role (04 L19). A quick-lane supplement is written with actor deploy,
    from_role gyb (the owner) and to_role deploy (who did the work), so 04 L19, 07 L96 and
    07 L116 hold at once (proxy decision D-24)."""
    return order.get("from_role", "gyb")
