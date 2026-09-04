"""Test 8: the hooks (30 L88-92; 06 L76-86 acceptance cases).

The write hook is driven directly: hooks/rl_hook.py write reads the PreToolUse input
JSON on stdin and prints a permissionDecision JSON (or nothing = allow). The five cases
of 30 L90 plus the Bash parsing, symlink, allowlist, unknown-agent-type and subagent
injection rules of 06 L13, L54-72, L102 and proxy decision D-15. Registration and
deregistration (skill, session-start, subagent-start/stop, session-end) go through
bin/rl and stay red until step 3b lands.
"""

import json
import os
import subprocess
import sys
import unittest

from helpers import PLUGIN_ROOT, Sandbox

HOOK = PLUGIN_ROOT / "hooks" / "rl_hook.py"


def run_hook(sb: Sandbox, event: str, payload: dict, env_extra: dict | None = None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("RL_")}
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    env["RL_COMMON_DIR"] = str(sb.common)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    if env_extra:
        env.update(env_extra)
    payload = {"session_id": "sess-top", "cwd": str(sb.root), "hook_event_name": "PreToolUse", **payload}
    proc = subprocess.run([sys.executable, str(HOOK), event], input=json.dumps(payload), cwd=sb.root,
                          env=env, capture_output=True, text=True, timeout=60)
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, out, proc.stderr


def decision(out):
    return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")


class WritePermission(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def _role(self, role, sid="sess-top"):
        return self.sb.role_session(role, session_id=sid, register=False)

    def _write(self, path, sid="sess-top", tool="Write", agent_type=None, agent_id=None):
        payload = {"session_id": sid, "tool_name": tool, "tool_input": {"file_path": path, "content": "x"}}
        if agent_type:
            payload["agent_type"] = agent_type
            payload["agent_id"] = agent_id or "a1"
        return run_hook(self.sb, "write", payload)

    def _bash(self, command, sid="sess-top", agent_type=None, agent_id=None):
        payload = {"session_id": sid, "tool_name": "Bash", "tool_input": {"command": command, "description": "t"}}
        if agent_type:
            payload["agent_type"] = agent_type
            payload["agent_id"] = agent_id or "a1"
        return run_hook(self.sb, "write", payload)

    def test_deploy_write_analysis_denied_with_issue_command(self):
        """30 L90; 06 L82, L92-98: deny, and the reason carries the open-issue command
        addressed to the directory owner with kind denied."""
        self._role("deploy")
        rc, out, err = self._write("analysis/x")
        self.assertEqual(rc, 0)
        self.assertEqual(decision(out), "deny")
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("rl issue open", reason)
        self.assertIn("--to analysis", reason)
        self.assertIn("--kind denied", reason)
        self.assertIn("deploy", reason)

    def test_any_role_write_loop_denied(self):
        """30 L90; 06 L52, L83: every role is denied a direct write into loop/, and the
        reason points at the rl write command instead of an issue command."""
        for i, role in enumerate(("idea", "deploy", "run", "analysis", "reviewer")):
            sid = f"sess-{role}"
            self._role(role, sid)
            rc, out, err = self._write("loop/x.jsonl", sid=sid)
            self.assertEqual(decision(out), "deny", f"{role}: {out} {err}")
            self.assertIn("rl ", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_run_write_experiments_denied(self):
        """30 L90; 06 L74, L84."""
        self._role("run")
        rc, out, err = self._write("experiments/x")
        self.assertEqual(decision(out), "deny")

    def test_deploy_write_repo_root_run_py_allowed(self):
        """30 L90; 06 L66, L85: other repo paths pass (discipline governs them)."""
        self._role("deploy")
        rc, out, err = self._write("run.py")
        self.assertEqual(rc, 0)
        self.assertIsNone(out, f"unexpected output {out}")

    def test_deploy_write_outside_repo_allowed(self):
        """30 L90; 06 L64, L86: a worktree path outside the repo passes."""
        self._role("deploy")
        outside = self.sb.root.parent / (self.sb.root.name + "-ql") / "ql-1" / "experiments" / "x.py"
        rc, out, err = self._write(str(outside))
        self.assertIsNone(out)

    def test_deploy_writes_its_own_directory(self):
        """06 L45: experiments/ belongs to deploy."""
        self._role("deploy")
        rc, out, err = self._write("experiments/train.py")
        self.assertIsNone(out)

    def test_idea_writes_notes_but_not_review(self):
        """06 L48, L50: notes/ is idea's (and gyb's, unhooked); review/ is reviewer's."""
        self._role("idea")
        self.assertIsNone(self._write("notes/plan.md")[1])
        self.assertEqual(decision(self._write("review/x.md")[1]), "deny")

    def test_absolute_path_is_folded_onto_the_repo(self):
        """06 L56: an absolute path is judged by its position in the repo."""
        self._role("deploy")
        rc, out, err = self._write(str(self.sb.root / "analysis" / "x.md"))
        self.assertEqual(decision(out), "deny")

    def test_symlink_is_not_followed(self):
        """06 L56: a symlink inside a role directory that points outside is judged by where
        it sits, so nobody bypasses the hook by planting a link."""
        self._role("deploy")
        target = self.sb.root.parent / (self.sb.root.name + "-elsewhere")
        target.mkdir(exist_ok=True)
        link = self.sb.root / "notes" / "out"
        os.symlink(target, link)
        try:
            rc, out, err = self._write("notes/out/file.md")
            self.assertEqual(decision(out), "deny")
        finally:
            link.unlink()
            target.rmdir()

    def test_allowlist_passes(self):
        """06 L58; 08 L79: hooks.path_allowlist entries pass whatever they resolve to."""
        self._role("deploy")
        self.sb.set_config("hooks.path_allowlist", ["analysis/shared"])
        rc, out, err = self._write("analysis/shared/x.py")
        self.assertIsNone(out, f"{out} {err}")
        rc, out, err = self._write("analysis/other.py")
        self.assertEqual(decision(out), "deny")

    def test_bare_session_is_never_blocked(self):
        """06 L72, L102: no state file = bare session, the hook does nothing (the CLAUDE.md
        section governs it, 06 L130-138)."""
        for path in ("loop/handoffs.jsonl", "analysis/x", "experiments/x"):
            rc, out, err = self._write(path, sid="sess-none")
            self.assertIsNone(out, path)

    def test_bash_redirect_tee_sed_mv_cp_are_judged(self):
        """06 L13, L70: write targets a hook can read off a Bash command."""
        self._role("deploy")
        denied = [
            "echo hi > analysis/x.md",
            "echo hi >> review/x.md",
            "cat a | tee notes/x.md",
            "sed -i 's/a/b/' review/x.md",
            "mv a.py notes/b.py",
            "cp -r src analysis/dst",
            "cd experiments && echo x > ../loop/issues.jsonl",
        ]
        for cmd in denied:
            rc, out, err = self._bash(cmd)
            self.assertEqual(decision(out), "deny", f"{cmd!r}: {out} {err}")
        allowed = [
            "echo hi > experiments/x.md",
            "cp a.py experiments/b.py",
            "python3 -c 'open(\"analysis/x\",\"w\").write(\"x\")'",  # unparsable: discipline (06 L29)
            "sed -i 's/a/b/' run.py",
            "ls analysis/",
            "cat analysis/x.md",
        ]
        for cmd in allowed:
            rc, out, err = self._bash(cmd)
            self.assertIsNone(out, f"{cmd!r}: {out} {err}")

    def test_host_launcher_writes_pass(self):
        """06 L70: the host launcher writing ops/jobs.json, ops/runs.jsonl, RUNMETA.json is
        an ordinary repo path and passes."""
        self._role("run")
        for cmd in ("python3 run.py launch > ops/jobs.json", "echo x >> ops/runs.jsonl"):
            rc, out, err = self._bash(cmd)
            self.assertIsNone(out, f"{cmd!r}: {out} {err}")

    def test_unknown_agent_type_is_strictest(self):
        """06 L102: an unknown agent type is refused the four role directories and loop/
        but not other paths."""
        for path in ("experiments/x", "analysis/x", "review/x", "notes/x", "loop/x.jsonl"):
            rc, out, err = self._write(path, agent_type="general-purpose")
            self.assertEqual(decision(out), "deny", path)
        rc, out, err = self._write("run.py", agent_type="general-purpose")
        self.assertIsNone(out)

    def test_subagent_role_from_agent_type_both_spellings(self):
        """06 L102; verify.md section 4 and 2.1: `research-loop:deploy` and bare `deploy`."""
        for at in ("research-loop:deploy", "deploy"):
            self.assertEqual(decision(self._write("analysis/x", agent_type=at)[1]), "deny", at)
            self.assertIsNone(self._write("experiments/x", agent_type=at)[1], at)

    def test_subagent_bash_gets_identity_injected_in_export_form(self):
        """Proxy decision D-15 and its addendum (verify.md 2.5): a subagent's Bash command
        is rewritten to `export RL_AGENT_TYPE=...; export RL_AGENT_ID=...; <command>` so
        chained commands still see the variables; the parent's calls are untouched."""
        rc, out, err = self._bash("cd experiments && rl handoff start ho-0001",
                                  agent_type="research-loop:deploy", agent_id="a12345")
        self.assertEqual(decision(out), "allow", f"{out} {err}")
        cmd = out["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertTrue(cmd.startswith("export RL_AGENT_TYPE='research-loop:deploy'; export RL_AGENT_ID='a12345'; "), cmd)
        self.assertTrue(cmd.endswith("cd experiments && rl handoff start ho-0001"))
        self.assertEqual(out["hookSpecificOutput"]["updatedInput"]["description"], "t")
        # parent (no agent_type): no rewrite
        self._role("deploy")
        rc, out, err = self._bash("rl handoff start ho-0001")
        self.assertIsNone(out)

    def test_hook_error_lets_the_call_through_with_a_stderr_line(self):
        """Proxy decision D-25: a broken hook input (here: malformed JSON) lets the call
        through (no decision on stdout, exit 0), prints one line
        `research-loop hook error: <reason>` on stderr, and injects no identity."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("RL_")}
        env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
        proc = subprocess.run([sys.executable, str(HOOK), "write"], input="{not json", cwd=self.sb.root,
                              env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("research-loop hook error:", proc.stderr)

    def test_outside_a_research_repo_the_hook_is_inert(self):
        """08 L17: no research-loop.json upwards means nothing to guard."""
        payload = {"cwd": "/tmp", "tool_name": "Write", "tool_input": {"file_path": "/tmp/loop/x.jsonl"}}
        rc, out, err = run_hook(self.sb, "write", payload)
        self.assertEqual(rc, 0)
        self.assertIsNone(out)


class RegistrationHooks(unittest.TestCase):
    """Registration and deregistration through bin/rl (06 L108-120; 04 L118-127;
    proxy decisions D-15 and D-21). Red until step 3b's `rl session` commands exist."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_session_start_writes_path_export_and_caches_model(self):
        """Proxy decision D-21 (verify.md 4.1): the PATH line lands in CLAUDE_ENV_FILE as an
        absolute path; the model from the SessionStart input is cached for registration
        (30 L22)."""
        env_file = self.sb.root / "envfile.sh"
        rc, out, err = run_hook(self.sb, "session-start",
                                {"hook_event_name": "SessionStart", "source": "startup", "model": "claude-x"},
                                env_extra={"CLAUDE_ENV_FILE": str(env_file)})
        self.assertEqual(rc, 0, err)
        text = env_file.read_text()
        self.assertIn(f'export PATH="{PLUGIN_ROOT / "bin"}:$PATH"', text)
        self.assertNotIn("$CLAUDE_PLUGIN_ROOT", text)
        self.assertEqual((self.sb.loop / ".sessions" / "sess-top.model").read_text().strip(), "claude-x")

    def test_skill_load_registers_the_session(self):
        """06 L112, L118: loading a role skill writes the state file and the sessions
        open row (actor = the role, launched_by manual, model from the cache)."""
        (self.sb.loop / ".sessions" / "sess-top.model").write_text("claude-x")
        rc, out, err = run_hook(self.sb, "skill", {"tool_name": "Skill", "tool_input": {"skill": "research-loop:deploy"}})
        self.assertEqual(rc, 0, err)
        state = json.loads((self.sb.loop / ".sessions" / "sess-top.json").read_text())
        self.assertEqual(state["role"], "deploy")
        row = self.sb.latest("sessions", "sess-top")
        self.assertIsNotNone(row, err)
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["actor"], "deploy")
        self.assertEqual(row["launched_by"], "manual")
        self.assertEqual(row["model"], "claude-x")

    def test_skill_load_inside_a_subagent_writes_no_state_file(self):
        """06 L118: a subagent (agent_type non-empty) writes no state file."""
        rc, out, err = run_hook(self.sb, "skill", {"tool_name": "Skill", "tool_input": {"skill": "research-loop:deploy"},
                                                   "agent_type": "research-loop:deploy", "agent_id": "a1"})
        self.assertFalse((self.sb.loop / ".sessions" / "sess-top.json").exists())

    def test_subagent_start_and_stop_register_and_close_their_own_chain(self):
        """Proxy decision D-15: the subagent's rows carry agent_id under the parent's
        session_id; SubagentStop closes that chain only."""
        self.sb.role_session("idea", session_id="sess-top")
        rc, out, err = run_hook(self.sb, "subagent-start", {"hook_event_name": "SubagentStart",
                                                             "agent_type": "research-loop:deploy", "agent_id": "a77"})
        self.assertEqual(rc, 0, err)
        rows = [r for r in self.sb.rows("sessions") if r.get("agent_id") == "a77"]
        self.assertEqual(len(rows), 1, err)
        self.assertEqual(rows[0]["role"], "deploy")
        self.assertEqual(rows[0]["launched_by"], "subagent")
        self.assertEqual(rows[0]["session_id"], "sess-top")
        rc, out, err = run_hook(self.sb, "subagent-stop", {"hook_event_name": "SubagentStop",
                                                            "agent_type": "research-loop:deploy", "agent_id": "a77"})
        rows = [r for r in self.sb.rows("sessions") if r.get("agent_id") == "a77"]
        self.assertEqual(rows[-1]["status"], "closed")
        self.assertEqual(self.sb.latest("sessions", "sess-top")["status"], "open")  # parent untouched

    def test_session_end_closes_and_deletes_the_state_file(self):
        """04 L120; 06 L114, L120; sync-inbox Q35(c): SessionEnd closes the session and
        deletes loop/.sessions/<session_id>.json."""
        self.sb.role_session("deploy", session_id="sess-top")
        state = self.sb.loop / ".sessions" / "sess-top.json"
        self.assertTrue(state.exists())
        rc, out, err = run_hook(self.sb, "session-end", {"hook_event_name": "SessionEnd", "reason": "other"})
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.sb.latest("sessions", "sess-top")["status"], "closed")
        self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
