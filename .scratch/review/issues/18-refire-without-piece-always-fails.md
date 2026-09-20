# 18 `run.py refire` without `--piece` reaches the launcher as `None` and dies on "no piece None recorded"

Status: needs-triage
Severity: minor
File: run.py:724-754
Contract: 8.6 and 2.3, which both spell the command `run.py refire <workflow> <setting> <stage> [--piece i]` — the flag in brackets
Errata: not recorded

## Finding

`cmd_refire` leaves `piece` at `None` when the flag is absent and passes it straight
through:

```python
def cmd_refire(rest: list[str]) -> int:
    piece = None
    ...
        pieces = launch.refire(run_dir, git, piece)
```

`jobs/launch.refire(run_dir, git, piece=None)` looks the index up in `meta.json` with no
`None` case (`jobs/launch.py:1167-1169`):

```python
    target = next((p for p in pieces if p.get("index") == piece), None)
    if target is None:
        sys.exit(f"jobs/launch.py refire: no piece {piece} recorded in {run_dir}/meta.json")
```

Nothing between the two fills a default, so the optional flag of the contract is in fact
required, and omitting it produces a message about a piece called `None`.

## Failure scenario

`run.py refire train_probe ctool_qwen3_0pt6b train` — a train run has exactly one piece,
index 0, so there is nothing to choose — exits with
`jobs/launch.py refire: no piece None recorded in <dir>/meta.json`. The operator reading
`run.py --help`, which prints `refire <workflow> <setting> <stage> [--piece i]`, has no
way to tell from that message that the flag is mandatory or which indices the run has.
The failure also arrives after both launch steps have run inside the lock
(`run.py:746-752`): `schema.freeze` has already rewritten that run directory's
`settings.yaml` with this attempt's `_commit`, and under `--allow-dirty` `git_state` has
already written `dirty.patch` into it, so a refire that restarted nothing still restamps
the run with a commit no piece of it ever ran.

## Proposed fix

Decide the missing case in `run.py`, which owns the argv. When `--piece` is absent, read
the run's `meta.json` pieces list and use the one work piece when the run has exactly
one; otherwise exit before the lock is taken, naming the recorded piece indices and the
flag — a message that says what to type. `run.py` already reads `meta.json` through
`_read_json` for the walk's partial-piece check, so the lookup needs no new reader and no
change to `jobs/launch.py`.
