"""Test harness for the research-loop plugin (build step 3a, 30 L29-31).

Tests drive the plugin the way a session would: they build a throw-away research repo
(the tree `rl init` would create, 08 L15-22), then run `bin/rl` as a subprocess and read
the ledger files back. They never import the command handlers, so a red test means the
CLI contract is unmet, not that an internal function moved.

Session simulation. `rl` learns its own session from RL_SESSION_ID (test seam) or
CLAUDE_CODE_SESSION_ID, and the session's role from loop/.sessions/<session_id>.json
(06 L118). A bare terminal is the absence of a state file (01 L69). Because these tests run
inside a Claude Code session, CLAUDE_CODE_SESSION_ID is scrubbed from every child
environment; only RL_SESSION_ID decides. `RL_CALLER=hook` marks the calls the plugin
hook makes (`session start`, `session end`; who column "hook, gyb", 05 L40).
`RL_COMMON_DIR` points `rl` at the sandbox's own common/ so `feedback accept` writing
rules_version back (09 L59) never touches the plugin tree.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RL = PLUGIN_ROOT / "bin" / "rl"
TABLES = PLUGIN_ROOT / "tables"

ROLES = ("idea", "deploy", "run", "analysis", "reviewer")
DECISION_BOOKS = ("idea", "deploy", "run", "analysis", "reviewer", "gyb")
LEDGER_FILES = [
    "issues.jsonl", "handoffs.jsonl", "runs.jsonl", "grants.jsonl", "feedback.jsonl",
    "evaluations.jsonl", "sessions.jsonl", "scratch.jsonl",
] + [f"decisions.{b}.jsonl" for b in DECISION_BOOKS]
EXIT_KIND = {1: "internal", 2: "validation", 3: "forbidden", 4: "lock_timeout", 5: "usage"}


@dataclass
class Result:
    rc: int
    out: str
    err: str
    argv: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str | None:
        """First stderr line: the fixed reason kind on every non-zero exit (03 L226)."""
        first = self.err.strip().splitlines()[0] if self.err.strip() else ""
        return first or None

    @property
    def json(self):
        return json.loads(self.out) if self.out.strip() else None

    def __str__(self):
        return f"rl {' '.join(self.argv)} -> rc={self.rc}\nstdout: {self.out}\nstderr: {self.err}"


class Sandbox:
    """A throw-away research repo with the `rl init` tree already in place."""

    def __init__(self, root: Path):
        self.root = root
        self.loop = root / "loop"
        self.common = root / "common"

    # ---- building ---------------------------------------------------------
    @classmethod
    def create(cls, rules_version: int = 1, git: bool = True) -> "Sandbox":
        root = Path(tempfile.mkdtemp(prefix="rl-sandbox-"))
        sb = cls(root)
        (sb.loop / ".sessions").mkdir(parents=True)
        for name in LEDGER_FILES:
            (sb.loop / name).touch()
        for d in ("experiments", "analysis/common", "analysis/scratch", "review", "notes", "artifacts"):
            (root / d).mkdir(parents=True)
        sb.common.mkdir()
        (sb.common / "GLOBAL-RULES.md").write_text(f"rules_version: {rules_version}\n\n# rules (sandbox copy)\n")
        cfg = {"artifact_root": str(root / "artifacts"),
               "analysis_artifact_root": str(root / "artifacts" / "analysis"),
               "gpu_state_path": "ops/gpu_state.md",
               "launcher.free_cmd": "", "launcher.launch_cmd": "", "launcher.finish_cmd": "", "launcher.abort_cmd": "",
               "repo_run": {"env": "sandbox", "entry": "python3 run.py", "notes": ""},
               "host_ledgers": [],
               "quick_lane.worktree_root": str(root.parent / (root.name + "-ql"))}
        defaults = json.loads((TABLES / "config_defaults.json").read_text())
        for row in defaults["thresholds"]:
            cfg.setdefault(row["key"], row["default"])
        (root / "research-loop.json").write_text(json.dumps(cfg, indent=2))
        (root / ".gitignore").write_text("loop/.sessions/\nartifacts/\n")
        if git:
            sb.git("init", "-q")
            sb.git("config", "user.email", "test@example.com")
            sb.git("config", "user.name", "rl-test")
            (root / "README.md").write_text("sandbox\n")
            sb.git("add", "-A")
            sb.git("commit", "-q", "-m", "init sandbox")
        return sb

    def destroy(self):
        shutil.rmtree(self.root, ignore_errors=True)
        ql = self.root.parent / (self.root.name + "-ql")
        shutil.rmtree(ql, ignore_errors=True)

    def git(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=True)

    def set_config(self, key, value):
        path = self.root / "research-loop.json"
        cfg = json.loads(path.read_text())
        cfg[key] = value
        path.write_text(json.dumps(cfg, indent=2))

    def write_file(self, rel: str, text: str = "x\n") -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    # ---- running rl --------------------------------------------------------
    def env(self, session: str | None = None, caller: str | None = None, extra: dict | None = None) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "RL_SESSION_ID", "RL_CALLER")}
        env["RL_COMMON_DIR"] = str(self.common)
        if session:
            env["RL_SESSION_ID"] = session
        if caller:
            env["RL_CALLER"] = caller
        if extra:
            env.update(extra)
        return env

    def rl(self, *args, session: str | None = None, caller: str | None = None, stdin: str | None = None,
           extra_env: dict | None = None, timeout: float = 60) -> Result:
        """Run one rl command in the sandbox. No `session` means a bare terminal (gyb)."""
        argv = [str(a) for a in args]
        proc = subprocess.run([str(RL), *argv], cwd=self.root, env=self.env(session, caller, extra_env),
                              capture_output=True, text=True, input=stdin, timeout=timeout)
        return Result(proc.returncode, proc.stdout, proc.stderr, argv)

    def rl_ok(self, *args, **kw) -> Result:
        r = self.rl(*args, **kw)
        assert r.rc == 0, f"expected exit 0:\n{r}"
        return r

    def parallel(self, calls: list[tuple], workers: int = 2) -> list[Result]:
        """Run several rl calls concurrently. Each call is (args_tuple, kwargs_dict)."""
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(self.rl, *a, **kw) for a, kw in calls]
            return [f.result() for f in futures]

    # ---- sessions -----------------------------------------------------------
    def role_session(self, role: str, session_id: str | None = None, model: str = "test-model",
                     launched_by: str = "manual", register: bool = True) -> str:
        """Simulate loading a role skill: write the state file the hook writes (06 L118)
        and, unless register=False, register the session the way the hook does
        (`rl session start`, actor = the role, 04 L118)."""
        assert role in ROLES, role
        sid = session_id or f"sess-{role}-{uuid.uuid4().hex[:8]}"
        state = {"session_id": sid, "role": role, "model": model, "launched_by": launched_by}
        (self.loop / ".sessions" / f"{sid}.json").write_text(json.dumps(state))
        if register:
            r = self.rl("session", "start", "--role", role, "--model", model, "--launched-by", launched_by,
                        session=sid, caller="hook")
            assert r.rc == 0, f"session start failed:\n{r}"
        return sid

    # ---- reading ledgers ------------------------------------------------------
    def rows(self, ledger: str, book: str | None = None) -> list[dict]:
        if ledger == "decisions":
            files = [self.loop / f"decisions.{b}.jsonl" for b in ([book] if book else DECISION_BOOKS)]
        else:
            files = [self.loop / f"{ledger}.jsonl"]
        out = []
        for f in files:
            if f.exists():
                out.extend(json.loads(l) for l in f.read_text().splitlines() if l.strip())
        return out

    def latest(self, ledger: str, key_value: str, book: str | None = None) -> dict | None:
        key = {"runs": "run_id", "scratch": "ql_tag", "sessions": "session_id"}.get(ledger, "id")
        best = None
        for row in self.rows(ledger, book):
            if row.get(key) == key_value and (best is None or row["version"] > best["version"]):
                best = row
        return best

    def count(self, ledger: str, book: str | None = None) -> int:
        return len(self.rows(ledger, book))


# ---- common fixtures used by several tests --------------------------------------

def make_decision(sb: Sandbox, session: str | None = None, text: str = "try lr 1e-4",
                  source: str | None = None) -> str:
    """Add a decision with a file source that exists (02 L42); returns its id."""
    if source is None:
        sb.write_file("notes/seed.md", "# seed\nline\n")
        source = "file:notes/seed.md"
    r = sb.rl("decision", "add", "--text", text, "--source", source, "--json", session=session)
    assert r.rc == 0, f"decision add failed:\n{r}"
    return r.json["id"]


def open_work_order(sb: Sandbox, session: str | None, decision_id: str, to_role: str = "deploy",
                    explanation: str = "build it", track: str = "probe", extra: tuple = ()) -> str:
    r = sb.rl("handoff", "open", "--type", "work_order", "--to", to_role, "--decision", f"{decision_id}@1",
              "--explain", explanation, "--track", track, *extra, "--json", session=session)
    assert r.rc == 0, f"work_order open failed:\n{r}"
    return r.json["id"]


def open_launch_order(sb: Sandbox, session: str | None, parent_id: str, command: str = "python3 train.py",
                      workdir: str = "experiments", extra: tuple = ()) -> str:
    r = sb.rl("handoff", "open", "--type", "launch_order", "--to", "run", "--parent", parent_id,
              "--command", command, "--workdir", workdir,
              "--config", "model=m", "--config", "params=1", "--config", "dataset=d", "--config", "split=s",
              *extra, "--json", session=session)
    assert r.rc == 0, f"launch_order open failed:\n{r}"
    return r.json["id"]
