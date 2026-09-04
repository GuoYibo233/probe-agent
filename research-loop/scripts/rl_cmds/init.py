"""rl init: build the research repo's tree (08 L7-36; 05 L39).

Only the role-session gate is built here. `rl init` itself is build step 7 (30 L200), so
every other call ends in exit 1 internal saying so.
"""

from __future__ import annotations

from pathlib import Path

import rl_lib


def cmd_main(args, ctx):
    """rl init (05 L39; 08 L9-13): gyb's command, and only from a bare terminal.

    08 L9: reading a session state file (loop/.sessions/<session_id>.json) is the refusal,
    exit 3, with the hint to run it from a bare terminal instead. The gate is the session,
    not the actor, so `--as-gyb` inside a role session does not get past it: rl_lib
    resolves a role session to a role_session whatever actor it writes as (01 L69-70).
    """
    try:
        repo = rl_lib.find_repo_root()
    except rl_lib.RLError:
        # `rl init` is what creates research-loop.json, so a repo without one is where it
        # belongs (08 L15); the session state file is looked for under the current tree.
        repo = Path.cwd()
    actor = rl_lib.resolve_actor(repo)
    if actor.role_session is not None:
        raise rl_lib.RLError("forbidden",
                             f"rl init does not run inside a {actor.role_session} session",
                             "run it from a bare terminal (no role loaded) in the repo root (08 L9)")
    raise rl_lib.RLError("internal", "rl init is built in step 7",
                         "see 30 L200 (build step 7) and 08 L15-36 for what it creates")
