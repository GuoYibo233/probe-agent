#!/usr/bin/env python3
"""research-loop plugin hook script. One script, one sub-command per hook event
(hooks/hooks.json): write, skill, session-start, subagent-start, subagent-stop,
session-end. Reads the hook input JSON on stdin (Claude Code hooks reference,
https://code.claude.com/docs/en/hooks) and prints the decision JSON on stdout.

What it carries (each rule cites its part and line):
- write: the write-permission hook (06 L37-98). Blocks only two kinds of writes inside the
  research repo: another role's directory, and loop/ directly (06 L13, L41-52). Paths are
  judged as typed, folded onto the repo root without following symlinks (06 L56); paths
  outside the repo and paths on hooks.path_allowlist pass (06 L58-64). The role comes
  first from agent_type, then from the session state file, and a bare session is not
  blocked at all (06 L102). A denial names the role, the reason and the issue command
  (06 L92-98). For a subagent's Bash command it also injects RL_AGENT_TYPE and
  RL_AGENT_ID in export form (proxy decision D-15 and its addendum).
- skill: registration when a role skill is loaded in the top-level session (06 L112):
  writes loop/.sessions/<session_id>.json and calls `rl session start` as the hook.
- session-start: puts <plugin>/bin on PATH through CLAUDE_ENV_FILE (proxy decision D-21)
  and caches the model from the hook input for the later registration (30 L22).
- subagent-start / subagent-stop: register and close the subagent's own sessions chain
  (proxy decision D-15).
- session-end: `rl session end` for the whole session, then delete the state file
  (06 L114, L120; 04 L120-127).

The script never imports scripts/rl_lib.py: hooks must stay cheap and independent of
the library's import cost; every ledger write goes through bin/rl as a subprocess.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
RL = PLUGIN_ROOT / "bin" / "rl"
ROLES = ("idea", "deploy", "run", "analysis", "reviewer")
# 06 L43-48: directory -> the only role that may write it (notes/ also gyb, whose bare
# terminal is never hooked, 06 L50).
DIR_OWNER = {"experiments": "deploy", "analysis": "analysis", "review": "reviewer", "notes": "idea"}
LEDGER_DIR = "loop"  # 06 L52: direct writes to loop/ are always denied


# ---------------------------------------------------------------- helpers

def read_input() -> dict:
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def emit(obj: dict | None = None) -> None:
    if obj is not None:
        print(json.dumps(obj))


def find_repo_root(cwd: str | None) -> Path | None:
    """The research repo is the directory holding research-loop.json, found upwards from
    the session cwd (08 L17). None means the hook is not inside a research repo."""
    if not cwd:
        return None
    cur = Path(cwd)
    for candidate in (cur, *cur.parents):
        if (candidate / "research-loop.json").is_file():
            return candidate
    return None


def load_config(repo: Path) -> dict:
    try:
        return json.loads((repo / "research-loop.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def role_from_agent_type(agent_type: str | None) -> str | None:
    """`research-loop:<role>` from the plugin's agents/, bare `<role>` from --agents
    (plans/2026-09-05-research-loop-verify.md section 4 and 2.1); unknown -> None."""
    if not agent_type:
        return None
    name = agent_type.rsplit(":", 1)[-1]
    return name if name in ROLES else None


def state_path(repo: Path, session_id: str) -> Path:
    return repo / LEDGER_DIR / ".sessions" / f"{session_id}.json"  # 06 L118


def read_state(repo: Path, session_id: str | None) -> dict | None:
    if not session_id:
        return None
    path = state_path(repo, session_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def rl_env(session_id: str, agent_type: str | None = None, agent_id: str | None = None) -> dict:
    env = dict(os.environ)
    env["RL_CALLER"] = "hook"  # who column "hook, gyb" for session start/end (05 L40)
    env["RL_SESSION_ID"] = session_id
    env.pop("RL_AGENT_TYPE", None)
    env.pop("RL_AGENT_ID", None)
    if agent_type:
        env["RL_AGENT_TYPE"] = agent_type
    if agent_id:
        env["RL_AGENT_ID"] = agent_id
    return env


def run_rl(args: list[str], cwd: Path, env: dict, timeout: float = 25) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RL), *args], cwd=str(cwd), env=env,
                          capture_output=True, text=True, timeout=timeout)


def fold_path(raw: str, repo: Path, cwd: str | None) -> str | None:
    """06 L56: absolute paths are folded onto the repo root, relative paths onto the
    session cwd, symlinks are not followed. Returns the repo-relative posix path, or
    None when the path is outside the repo."""
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = Path(cwd or os.getcwd()) / p
    norm = Path(os.path.normpath(str(p)))
    try:
        rel = norm.relative_to(repo)
    except ValueError:
        return None
    return rel.as_posix()


_WRITE_REDIRECT = re.compile(r"(?:^|\s)(?:\d?>>?|&>)\s*([^\s;&|]+)")


def sq(value: str) -> str:
    """Always single-quote for the export injection (D-15 addendum: shell-escaped)."""
    return "'" + value.replace("'", "'\\''") + "'"


def bash_write_targets(command: str, cwd: str | None) -> list[tuple[str, str | None]]:
    """06 L13, L70: the write targets a hook can read off a Bash command: redirections,
    tee, sed -i, mv/cp destinations. Returns (target, cwd at that point) pairs; a `cd`
    earlier in the chain moves the cwd for the later pieces. Anything else is left to
    discipline (06 L29)."""
    targets: list[tuple[str, str | None]] = []
    vcwd = cwd
    for piece in re.split(r"\|\||&&|;|\n", command):
        piece = piece.strip()
        if not piece:
            continue
        for m in _WRITE_REDIRECT.finditer(piece):
            targets.append((m.group(1), vcwd))
        for sub in piece.split("|"):
            try:
                words = shlex.split(sub.strip())
            except ValueError:
                continue
            while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
                words = words[1:]
            if not words:
                continue
            prog = Path(words[0]).name
            args = words[1:]
            if prog == "cd":
                if args:
                    vcwd = os.path.normpath(os.path.join(vcwd or os.getcwd(), args[0]))
                continue
            if prog == "tee":
                targets.extend((a, vcwd) for a in args if not a.startswith("-"))
            elif prog == "sed" and any(a == "-i" or a.startswith("-i") for a in args):
                files = [a for a in args if not a.startswith("-")]
                if files and not any(a in ("-e", "--expression") or a.startswith("-e") for a in args):
                    files = files[1:]
                targets.extend((a, vcwd) for a in files)
            elif prog in ("mv", "cp", "install", "rsync"):
                positional = [a for a in args if not a.startswith("-")]
                if len(positional) >= 2:
                    targets.append((positional[-1], vcwd))
            elif prog in ("touch", "mkdir", "rm", "truncate", "dd"):
                targets.extend((a, vcwd) for a in args if not a.startswith("-") and "=" not in a)
    return targets


def judge(rel: str, role: str) -> tuple[str, str] | None:
    """Return (owner_or_ledger, reason) when the write must be denied, else None
    (06 L41-52, L68)."""
    top = rel.split("/", 1)[0]
    if top == LEDGER_DIR:
        return ("loop", f"loop/ holds the nine ledgers and is written only through rl (03 L9; 06 L52)")
    owner = DIR_OWNER.get(top)
    if owner and owner != role:
        return (owner, f"{top}/ belongs to {owner} (06 L45-48)")
    return None


def denial(role: str, rel: str, why: tuple[str, str], tool: str) -> dict:
    """06 L92-98: tell the model who it is, why it was stopped, and the issue command
    (kind denied, --to the directory owner; a direct loop/ write gets the rl write command
    hint instead of an issue command)."""
    owner, reason = why
    if owner == "loop":
        next_step = ("Use the rl write command for that ledger instead (rl handoff ..., rl issue ..., "
                     "rl decision ..., see tables/commands.json).")
    else:
        next_step = (f"Open an issue to the owner: rl issue open --to {owner} --kind denied "
                     f"--handoff <your-order-id> --text \"{role} needs a change in {rel}\"")
    text = (f"research-loop: you are a {role} session; {tool} to {rel} was denied because {reason}. "
            f"{next_step}")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": text}}


# ---------------------------------------------------------------- events

def hook_write(inp: dict) -> int:
    repo = find_repo_root(inp.get("cwd"))
    if repo is None:
        return 0  # not a research repo: nothing to guard
    tool = inp.get("tool_name")
    tool_input = inp.get("tool_input") or {}
    agent_type = inp.get("agent_type") or ""
    agent_id = inp.get("agent_id") or ""
    role = None
    strictest = False
    if agent_type:
        role = role_from_agent_type(agent_type)
        if role is None:
            strictest = True  # 06 L102: unknown type -> deny the four role dirs and loop/
    else:
        state = read_state(repo, inp.get("session_id"))
        if state is None:
            return 0  # bare session: never blocked (06 L72, L102)
        role = state.get("role")
        if role not in ROLES:
            return 0
    cfg = load_config(repo)
    allow = {p.rstrip("/") for p in cfg.get("hooks.path_allowlist", []) or []}
    if tool in ("Write", "Edit"):
        raw_targets = [(tool_input.get("file_path", ""), inp.get("cwd"))]
    elif tool == "Bash":
        raw_targets = bash_write_targets(tool_input.get("command", ""), inp.get("cwd"))
    else:
        return 0
    for raw, at_cwd in raw_targets:
        rel = fold_path(raw, repo, at_cwd)
        if rel is None:
            continue  # outside the repo: pass (06 L64)
        if rel in allow or any(rel.startswith(a + "/") for a in allow):
            continue  # 06 L58
        if strictest:
            top = rel.split("/", 1)[0]
            if top in DIR_OWNER or top == LEDGER_DIR:
                emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": f"research-loop: unknown agent type {agent_type!r}; writes to {rel} are refused under the strictest policy (06 L102)"}})
                return 0
            continue
        why = judge(rel, role)
        if why:
            emit(denial(role, rel, why, tool))
            return 0
    # subagent identity injection for Bash (proxy decision D-15 and addendum: export form)
    if tool == "Bash" and agent_type and role:
        command = tool_input.get("command", "")
        injected = (f"export RL_AGENT_TYPE={sq(agent_type)}; "
                    f"export RL_AGENT_ID={sq(agent_id)}; {command}")
        new_input = dict(tool_input)
        new_input["command"] = injected
        # No permissionDecision: with updatedInput alone Claude Code only rewrites the
        # input and the permission flow stays the user's (hooks reference 2.1.260;
        # 06 L13 only authorises the two blocks; proxy decision D-25).
        emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": new_input}})
    return 0


def skill_role(inp: dict) -> str | None:
    """Which role skill is being loaded. PreToolUse(Skill) tool_input carries `skill` and
    `args`; UserPromptExpansion carries command_name as the prefixed full name
    `research-loop:<role>` (plans/2026-09-05-research-loop-verify.md 7.1). The other
    candidates stay as fallbacks; both spellings `research-loop:<role>` and `<role>` are
    accepted."""
    ti = inp.get("tool_input") or {}
    candidates = [ti.get("skill"), ti.get("name"), ti.get("skill_name"), ti.get("command"),
                  inp.get("command_name"), inp.get("skill_name")]
    for c in candidates:
        if isinstance(c, str) and c:
            role = role_from_agent_type(c.strip().lstrip("/"))
            if role:
                return role
    return None


def hook_skill(inp: dict) -> int:
    """06 L112, L118: loading a role skill in the top-level session registers the session;
    a subagent (agent_type non-empty) writes no state file (its registration is
    subagent-start)."""
    if inp.get("agent_type"):
        return 0
    role = skill_role(inp)
    if role is None:
        return 0
    repo = find_repo_root(inp.get("cwd"))
    sid = inp.get("session_id")
    if repo is None or not sid:
        return 0
    path = state_path(repo, sid)
    if path.is_file():
        # 06 L106: one session, one role; a second load is discipline, the machine does
        # not define it, so the first state file stays.
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    model = "unknown"
    cache = path.with_suffix(".model")
    if cache.is_file():
        model = cache.read_text(encoding="utf-8").strip() or "unknown"
    state = {"session_id": sid, "role": role, "model": model, "launched_by": "manual",
             "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    path.write_text(json.dumps(state), encoding="utf-8")
    proc = run_rl(["session", "start", "--role", role, "--model", model, "--launched-by", "manual"],
                  repo, rl_env(sid))
    if proc.returncode != 0:
        print(f"research-loop: session start failed ({proc.stderr.strip()})", file=sys.stderr)
    return 0


def hook_session_start(inp: dict) -> int:
    """Proxy decision D-21: put <plugin>/bin on PATH for every later Bash call of this
    session and its subagents; also cache the model for the registration hook
    (30 L22: the SessionStart input carries model in interactive sessions)."""
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        line = f'export PATH="{PLUGIN_ROOT / "bin"}:$PATH"\n'
        try:
            with open(env_file, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as err:
            print(f"research-loop: could not write CLAUDE_ENV_FILE: {err}", file=sys.stderr)
    repo = find_repo_root(inp.get("cwd"))
    sid = inp.get("session_id")
    model = inp.get("model")
    if repo and sid and model:
        cache = state_path(repo, sid).with_suffix(".model")
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(str(model), encoding="utf-8")
        except OSError:
            pass
    return 0


def hook_subagent_start(inp: dict) -> int:
    """Proxy decision D-15: a subagent gets its own sessions chain under the parent's
    session_id, keyed by agent_id; role from agent_type; model unknown (SubagentStart has
    no model field, verify.md 2.7)."""
    repo = find_repo_root(inp.get("cwd"))
    role = role_from_agent_type(inp.get("agent_type"))
    sid, aid = inp.get("session_id"), inp.get("agent_id")
    if repo is None or role is None or not sid or not aid:
        return 0
    proc = run_rl(["session", "start", "--role", role, "--model", "unknown", "--launched-by", "subagent"],
                  repo, rl_env(sid, inp.get("agent_type"), aid))
    if proc.returncode != 0:
        print(f"research-loop: subagent session start failed ({proc.stderr.strip()})", file=sys.stderr)
    return 0


def hook_subagent_stop(inp: dict) -> int:
    """Proxy decision D-15 (4): close the subagent's chain and hand back the orders it
    held (via subagent_stop). A subagent killed with its parent gets no SubagentStop
    (verify.md 2.6); SessionEnd covers it."""
    repo = find_repo_root(inp.get("cwd"))
    role = role_from_agent_type(inp.get("agent_type"))
    sid, aid = inp.get("session_id"), inp.get("agent_id")
    if repo is None or role is None or not sid or not aid:
        return 0
    proc = run_rl(["session", "end", "--end-reason", "hook"], repo, rl_env(sid, inp.get("agent_type"), aid))
    if proc.returncode != 0:
        print(f"research-loop: subagent session end failed ({proc.stderr.strip()})", file=sys.stderr)
    return 0


def hook_session_end(inp: dict) -> int:
    """04 L120-127; 06 L114, L120: deregister the whole session (release every held
    order, close still-open subagent rows, closed version), then delete the state file.
    Plugin SessionEnd hooks get a 1.5 s budget (hooks reference, SessionEnd); the doctor
    and reclaim are the backstops when this does not finish (04 L129)."""
    repo = find_repo_root(inp.get("cwd"))
    sid = inp.get("session_id")
    if repo is None or not sid:
        return 0
    state = state_path(repo, sid)
    if state.is_file():
        # Plugin SessionEnd hooks get a 1.5 s budget that hooks.json cannot raise (hooks
        # reference, SessionEnd), so the deregistration runs detached (setsid) and this
        # hook returns at once; the state file is deleted by that background step after
        # `rl session end` finished (proxy decision D-26).
        log = state.with_suffix(".end.log")
        script = (f"{shlex.quote(sys.executable)} {shlex.quote(str(RL))} session end --end-reason hook; "
                  f"rm -f {shlex.quote(str(state))}")
        with open(log, "ab") as fh:
            subprocess.Popen(["/bin/sh", "-c", script], cwd=str(repo), env=rl_env(sid),
                             stdout=fh, stderr=fh, start_new_session=True)
    cache = state.with_suffix(".model")
    if cache.is_file():
        try:
            cache.unlink()
        except OSError:
            pass
    return 0


HANDLERS = {
    "write": hook_write,
    "skill": hook_skill,
    "session-start": hook_session_start,
    "subagent-start": hook_subagent_start,
    "subagent-stop": hook_subagent_stop,
    "session-end": hook_session_end,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in HANDLERS:
        print("usage: rl_hook.py <write|skill|session-start|subagent-start|subagent-stop|session-end>", file=sys.stderr)
        return 0  # never block on a usage error of our own
    try:
        inp = read_input()
        return HANDLERS[argv[0]](inp)
    except Exception as err:  # noqa: BLE001
        # proxy decision D-25: a broken hook lets the call through, prints one stderr
        # line and injects no identity.
        print(f"research-loop hook error: {type(err).__name__}: {err}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
