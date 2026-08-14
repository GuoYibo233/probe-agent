"""Shared standard-library helpers for the research-loop plugin.

Every ledger.py subcommand module, and every fallback/oversight script, is
built on this module. Nothing here may import a third-party package: the
plugin has to run on any machine that only has a stock python3.

See .scratch/research-loop/plan.md §C1 for the frozen API contract this
module implements, and §C3 for the validate() semantics.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shlex
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Roots and tables
# ---------------------------------------------------------------------------


def plugin_root() -> Path:
    """Return the research-loop/ directory (the parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def load_tables() -> dict:
    """Load the five closed-list tables that are the single source of truth
    for enums, fields, write rights, routes and config keys."""
    tables_dir = plugin_root() / "tables"
    names = {
        "ledgers": "ledgers.json",
        "rows": "rows.json",
        "writes": "writes.json",
        "config": "config.json",
        "routes": "routes.json",
    }
    return {
        key: json.loads((tables_dir / fname).read_text(encoding="utf-8"))
        for key, fname in names.items()
    }


def find_project_root(start=None) -> Path | None:
    """Walk upward from `start` (default: cwd) looking for research-loop.json.
    Returns None if no hooked-up project is found."""
    cur = Path(start).resolve() if start is not None else Path.cwd()
    if cur.is_file():
        cur = cur.parent
    while True:
        if (cur / "research-loop.json").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def resolve_project_root(explicit_root):
    """Shared --project-root CLI handling for trace_check.py,
    regression_check.py, verify_report.py and doctor.py (F2, sdd/
    final-review.md). `explicit_root` is the parsed --project-root value (a
    Path/str or None, straight off argparse).

    An explicit root must actually be wired: find_project_root()'s own
    cwd-search branch can only ever return a directory that has
    research-loop.json (or None), but a caller-given path was never checked
    at all before this fix -- every ledger read under a wrong path silently
    came back empty, and the caller read that as "0 errors" / "clean"
    instead of "wrong path". Raises RLError (the caller's existing
    `except _lib.RLError` -> stderr + exit 2 path already covers this) when
    `explicit_root` doesn't have one; returns the resolved root otherwise.

    Returns None only when `explicit_root` is None and no research-loop.json
    is found walking up from cwd -- each caller already has its own
    "not wired" message and exit code for that branch (doctor's differs
    from the other three), so this function does not print anything for
    that case."""
    if explicit_root is not None:
        root = Path(explicit_root).resolve()
        if not (root / "research-loop.json").exists():
            raise RLError(f"--project-root {root} has no research-loop.json (wrong path?)")
        return root
    return find_project_root()


# Plugin-level defaults for config keys that have one (plan.md §C1).
# Every other key's absence/null resolves to None -- callers interpret that
# as "not wired" per tables/config.json null_effect.
_CONFIG_DEFAULTS = {
    "runtime_factor": 3,
    "roles": {"inspector_model": "opus", "reader_model": "sonnet"},
    "standing_authorization": {"max_expected_runtime_s": 3600, "resource": "compute"},
    "inspection_policy": "always",
}


class Config:
    """Wraps a project's research-loop.json plus the plugin's own tables."""

    def __init__(self, root: Path, data: dict):
        self.root = Path(root)
        self.data = data
        self._tables = load_tables()

    def get(self, key):
        """Return data[key] if present and non-null, else the plugin default
        for that key (None if the key has no plugin default)."""
        value = self.data.get(key)
        if value is None:
            return _CONFIG_DEFAULTS.get(key)
        return value

    def null_locked(self, key) -> bool:
        """True if `key` is missing or explicitly null in the raw config."""
        return self.data.get(key) is None

    def ledger_path(self, name):
        """Resolve a ledger's on-disk path: config.ledgers[name] overrides
        tables/ledgers.json default_path, resolved relative to root. Paths
        containing <artifact_dir> or <raw_data_roots> templates are returned
        as-is (the caller resolves those)."""
        ledgers_doc = self._tables["ledgers"]
        entry = ledgers_doc["ledgers"].get(name)
        if entry is None:
            entry = ledgers_doc.get("optional_ledgers", {}).get(name)
        override = (self.data.get("ledgers") or {}).get(name)
        if override is not None:
            raw = override
        elif entry is not None:
            raw = entry["default_path"]
        else:
            raise RLError(f"unknown ledger: {name}")
        if "<artifact_dir>" in raw or "<raw_data_roots>" in raw:
            return raw
        return self.root / raw


def load_config(root) -> Config:
    root = Path(root)
    config_path = root / "research-loop.json"
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        data = {}
    return Config(root, data)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

_MISSING = object()


class RLError(Exception):
    """Raised for every schema/write-right rejection. .message is the
    finished text; the CLI prints it to stderr and exits 2 (spec §9)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def fail(ledger, field_path, msg, value=_MISSING):
    """Single point of production for the fixed error format:
    '<ledger>.<field_path>: <msg> (got: <value>)'. The '(got: ...)' suffix is
    only appended when a value was actually passed (including None)."""
    text = f"{ledger}.{field_path}: {msg}"
    if value is not _MISSING:
        text += f" (got: {value!r})"
    raise RLError(text)


# ---------------------------------------------------------------------------
# Locking and jsonl I/O
# ---------------------------------------------------------------------------


@contextmanager
def locked(path):
    """with locked(p): ... -- exclusive flock on str(p) + '.lock', released
    (and fd closed) on exit."""
    path = Path(path)
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_jsonl_file(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                fail(path.stem, f"line {line_no}", "is not valid JSON", line[:80])
    return rows


def jsonl_rows(path, include_archive: bool = False) -> list:
    """Read a jsonl ledger. Missing file -> []. include_archive=True reads
    <name>.archive.jsonl first (if it exists), then the main file."""
    path = Path(path)
    rows = []
    if include_archive:
        archive_path = path.with_name(f"{path.stem}.archive{path.suffix}")
        rows.extend(_read_jsonl_file(archive_path))
    rows.extend(_read_jsonl_file(path))
    return rows


def jsonl_append(path, row: dict):
    """Append one row. Caller holds the lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def inplace_update(path, key_field, key_value, updates: dict, whitelist) -> dict:
    """Update the single row where row[key_field] == key_value, restricted to
    whitelist fields. Rewrites via a temp file + os.replace so untouched
    lines keep their original bytes. Caller holds the lock."""
    path = Path(path)
    for field in updates:
        if field not in whitelist:
            fail(path.stem, field, "field is not in-place updatable")

    if not path.exists():
        fail(path.stem, key_field, "row not found", key_value)

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated_row = None
    new_lines = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            new_lines.append(line)
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError:
            fail(path.stem, f"line {line_no}", "is not valid JSON", stripped[:80])
        if row.get(key_field) == key_value:
            row = dict(row)
            row.update(updates)
            updated_row = row
            new_lines.append(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            new_lines.append(line)

    if updated_row is None:
        fail(path.stem, key_field, "row not found", key_value)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    os.replace(tmp_path, path)
    return updated_row


def alloc_id(rows, id_field, prefix) -> str:
    """Next id for `prefix`: max existing numeric suffix + 1, zero-padded to
    3 digits (D001; widens naturally past 999 to D1000)."""
    max_num = 0
    for row in rows:
        value = row.get(id_field)
        if isinstance(value, str) and value.startswith(prefix):
            suffix = value[len(prefix):]
            if suffix.isdigit():
                max_num = max(max_num, int(suffix))
    return f"{prefix}{max_num + 1:03d}"


def now_iso() -> str:
    """Second-level ISO timestamp. RL_FAKE_NOW env var overrides (test hook)."""
    fake = os.environ.get("RL_FAKE_NOW")
    if fake:
        return fake
    return datetime.now().replace(microsecond=0).isoformat()


def today() -> str:
    """YYYY-MM-DD. RL_FAKE_NOW env var overrides (test hook)."""
    fake = os.environ.get("RL_FAKE_NOW")
    if fake:
        return fake[:10]
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Schema loading and validation (plan.md §C3)
# ---------------------------------------------------------------------------


def load_schema(name: str) -> dict:
    path = plugin_root() / "schemas" / f"{name}.schema.json"
    if not path.exists():
        raise RLError(f"schema not found: {name} (expected {path})")
    return json.loads(path.read_text(encoding="utf-8"))


def _when_conditions(when):
    return when if isinstance(when, list) else [when]


def _when_matches(when, row) -> bool:
    """when = {field, op, value} or a list of such (list = AND). A missing
    field on the row compares as None."""
    for cond in _when_conditions(when):
        actual = row.get(cond["field"])
        op = cond["op"]
        target = cond["value"]
        if op == "eq":
            if actual != target:
                return False
        elif op == "neq":
            if actual == target:
                return False
        elif op == "in":
            if actual not in target:
                return False
        else:
            raise RLError(f"validate: unknown conditional op {op!r}")
    return True


def _matches_type(value, type_name) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "null":
        return value is None
    return False


def _type_allows_null(type_spec) -> bool:
    types = type_spec if isinstance(type_spec, list) else [type_spec]
    return "null" in types


def _check_value(value, field_schema: dict, ledger: str, field_path: str):
    type_spec = field_schema.get("type")
    if type_spec is not None:
        types = type_spec if isinstance(type_spec, list) else [type_spec]
        if not any(_matches_type(value, t) for t in types):
            fail(ledger, field_path, f"expected type {type_spec}", value)
    if "enum" in field_schema:
        if value not in field_schema["enum"]:
            fail(ledger, field_path, f"must be one of {field_schema['enum']}", value)
    if "const" in field_schema:
        if value != field_schema["const"]:
            fail(ledger, field_path, f"must equal {field_schema['const']!r}", value)
    if "minimum" in field_schema:
        if not isinstance(value, int) or isinstance(value, bool) or value < field_schema["minimum"]:
            fail(ledger, field_path, f"below minimum {field_schema['minimum']}", value)
    if isinstance(value, list) and "items" in field_schema:
        for i, item in enumerate(value):
            _check_value(item, field_schema["items"], ledger, f"{field_path}[{i}]")


def validate(row: dict, schema: dict, ledger: str) -> None:
    """Single validation entry point. Checks required, additionalProperties,
    type (union-aware, bool excluded from integer/number), enum, const,
    minimum, array items, conditional require and conditional allow_null.
    Raises RLError via fail() on the first violation found."""
    properties = schema.get("properties", {})
    conditional = schema.get("conditional", [])

    if schema.get("additionalProperties") is False:
        for key in row:
            if key not in properties:
                fail(ledger, key, "field is not defined in schema")

    for field in schema.get("required", []):
        if field not in row:
            fail(ledger, field, "required field missing")

    null_gated_fields = set()
    for cond in conditional:
        null_gated_fields.update(cond.get("allow_null", []))

    for field, value in row.items():
        field_schema = properties.get(field)
        if field_schema is None:
            continue  # additionalProperties already checked above
        if value is None:
            if field in null_gated_fields:
                allowed = any(
                    field in cond.get("allow_null", []) and _when_matches(cond["when"], row)
                    for cond in conditional
                )
                if not allowed:
                    fail(ledger, field, "must not be null under the current row state", value)
                continue
            if not _type_allows_null(field_schema.get("type")):
                fail(ledger, field, "must not be null", value)
            continue
        _check_value(value, field_schema, ledger, field)

    for cond in conditional:
        require = cond.get("require")
        if require and _when_matches(cond["when"], row):
            for field in require:
                if field not in row or row.get(field) is None:
                    when_desc = " and ".join(
                        f"{c['field']} {c['op']} {c['value']!r}" for c in _when_conditions(cond["when"])
                    )
                    fail(ledger, field, f"required when {when_desc}")


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def run_argv(argv, cwd=None, timeout=None):
    """Run argv with no shell. Returns (exit_code, stdout, stderr, elapsed_s).
    On timeout, exit_code is None and elapsed_s reflects time actually spent."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv, cwd=cwd, timeout=timeout, capture_output=True, text=True
        )
        elapsed = time.monotonic() - start
        return proc.returncode, proc.stdout, proc.stderr, elapsed
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return None, stdout, stderr, elapsed


def split_cmd(cmd: str, ledger, field) -> list:
    """shlex.split(cmd); rejects pipes and newlines (cells must not need a
    shell -- spec: 'shell pipeline needs go through a registered task')."""
    if "|" in cmd or "\n" in cmd:
        fail(ledger, field, "command must not contain pipes or newlines", cmd)
    return shlex.split(cmd)


def last_json_line(stdout: str):
    """Last non-empty line of stdout, parsed as JSON. None if that line is
    not valid JSON, or is valid JSON but not an object."""
    lines = stdout.splitlines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return None
        return obj if isinstance(obj, dict) else None
    return None


def registry_tasks(cfg) -> list | None:
    """Run cfg's registry_query and return its task names (one per line).
    None if registry_query is null (not wired)."""
    registry_query = cfg.get("registry_query")
    if registry_query is None:
        return None
    argv = split_cmd(registry_query, "config", "registry_query")
    _, out, _, _ = run_argv(argv)
    return [line.strip() for line in out.splitlines() if line.strip()]


def check_in_registry(argv, cfg, *, ledger, field) -> str:
    """Verify argv starts with cfg.registry_cmd and that the token right
    after that prefix names a task present in registry_tasks(cfg). Returns
    the task name. Shared by launchcmd, principlescmd and trace_check."""
    registry_cmd = cfg.get("registry_cmd")
    if registry_cmd is None:
        fail(ledger, field, "registry_cmd not wired (null); cannot verify task")
    prefix = split_cmd(registry_cmd, ledger, field)
    if argv[: len(prefix)] != prefix:
        fail(ledger, field, "argv does not start with the registry_cmd prefix", argv)
    if len(argv) <= len(prefix):
        fail(ledger, field, "argv has no task name after the registry_cmd prefix", argv)
    task = argv[len(prefix)]
    tasks = registry_tasks(cfg)
    if tasks is None:
        fail(ledger, field, "registry_query not wired (null); cannot verify task")
    if task not in tasks:
        fail(ledger, field, "task is not in the registry", task)
    return task


# ---------------------------------------------------------------------------
# Frontmatter, digests, git
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str):
    """text must start with a '---' line; the header runs to the next '---'
    line. Each header line is 'key: value', value tried as json.loads first,
    kept as a plain string on failure. Returns (fields, body); body is
    everything after the second '---' line."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise RLError("frontmatter must start with a '---' line")
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            close_idx = i
            break
    if close_idx is None:
        raise RLError("frontmatter has no closing '---' line")

    fields = {}
    for line in lines[1:close_idx]:
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        key, _, raw_value = line.partition(":")
        key = key.strip()
        raw_value = raw_value.strip()
        try:
            value = json.loads(raw_value)
        except (json.JSONDecodeError, ValueError):
            value = raw_value
        fields[key] = value

    body = "".join(lines[close_idx + 1:])
    return fields, body


def find_spec_files(cfg, item_id: str) -> list:
    """Every *.md file under the specs ledger that both parses as
    frontmatter'd and whose body (post-frontmatter content, not the header)
    contains `item_id` as a substring -- the plugin's single definition of
    "this spec item's home file" (skills/deploy-layer/references/
    spec-items.md: every spec file carries frontmatter, so a file without
    one -- an issue ticket, a scratch note, anything else that happens to
    also share the specs ledger's directory tree and mention the id in
    prose -- is never a candidate, no matter how early it sorts).

    Returns every match, sorted by path, for the caller to judge: 0 hits is
    "not found", 2+ hits is "ambiguous" (list every path, don't guess).
    Silently taking the first hit is exactly the bug this function replaces
    (F1, sdd/final-review.md) -- two independent hand-rolled searches, one
    in trace_check.py and one in launchcmd.py, each cut a different corner
    and broke in opposite directions (a false "unreadable" when a
    non-frontmatter'd file sorted first, a false approval pass when an
    unrelated but coincidentally-approved file did) -- so no caller may
    reintroduce a "take the first match" shortcut around this function."""
    specs_root = Path(cfg.ledger_path("specs"))
    if not specs_root.exists():
        return []
    matches = []
    for path in sorted(specs_root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            _fields, body = parse_frontmatter(text)
        except RLError:
            continue
        if item_id in body:
            matches.append(path)
    return matches


def spec_digest(path) -> str:
    """sha256 of the raw bytes after the second '---' line (rows.json
    spec_header._digest_rule)."""
    raw = Path(path).read_bytes()
    lines = raw.splitlines(keepends=True)
    dash_indices = [i for i, ln in enumerate(lines) if ln.rstrip(b"\r\n") == b"---"]
    if len(dash_indices) < 2:
        raise RLError(f"spec file missing frontmatter delimiters: {path}")
    body = b"".join(lines[dash_indices[1] + 1:])
    return hashlib.sha256(body).hexdigest()


def git_head(root) -> str:
    """HEAD sha; '-dirty' suffix if the working tree has changes; 'no-git'
    outside a git repo."""
    code, out, _, _ = run_argv(["git", "rev-parse", "HEAD"], cwd=root)
    if code != 0:
        return "no-git"
    head = out.strip()
    _, status_out, _, _ = run_argv(["git", "status", "--porcelain"], cwd=root)
    if status_out.strip():
        return f"{head}-dirty"
    return head
