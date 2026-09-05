"""rl init: build the research repo's tree (08 L7-36; 05 L39).

Only the role-session gate is built here. What `rl init` creates belongs to build step 7
(the 2026-09-04 work guide, section 4, the `rl init` products row), so every other call
ends in exit 1 internal saying so.
"""

from __future__ import annotations

from pathlib import Path

import rl_lib


def cmd_main(args, ctx):
    """rl init (05 L39; 08 L9-13): gyb's command, and only from a bare terminal.

    08 L9: reading a session state file (loop/.sessions/<session_id>.json) is the refusal,
    exit 3, with the hint to run it from a bare terminal instead and the open-an-issue
    command every exit 3 carries (03 L222). The gate is the session, not the actor, so
    `--as-gyb` inside a role session does not get past it: rl_lib resolves a role session
    to a role_session whatever actor it writes as (01 L69-70).
    """
    try:
        repo = rl_lib.find_repo_root()
    except rl_lib.RLError:
        # `rl init` is what creates research-loop.json, the file find_repo_root looks for
        # (08 L17), so a repo without one is where it belongs; the session state file is
        # looked for under the current tree.
        repo = Path.cwd()
    actor = rl_lib.resolve_actor(repo)
    if actor.role_session is not None:
        raise rl_lib.RLError("forbidden",
                             f"rl init does not run inside a {actor.role_session} session",
                             "run it from a bare terminal (no role loaded) in the repo root "
                             "(08 L9); or ask gyb: "
                             + rl_lib.issue_command_for_gyb("please run rl init in this repo"))
    raise rl_lib.RLError("internal", "rl init is built in step 7",
                         "see the 2026-09-04 work guide, section 4 (the `rl init` products row) "
                         "and 08 L15-36 for what it creates")
