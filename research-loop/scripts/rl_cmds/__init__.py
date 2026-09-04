"""Command handlers, one module per command group (`handoff.py`, `decision.py`, ...).

Each module exposes `cmd_<sub>(args: list[str], ctx: dict) -> dict | str | None`.
`ctx["opts"]` holds the global flags (json, as_gyb, force, quote, reason),
`ctx["command"]` the full command name, `ctx["spec"]` its row from tables/commands.json.
Handlers raise rl_lib.RLError to refuse. Build step 3b fills this package.
"""
