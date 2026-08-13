"""`ledger.py freeze-legacy --confirm` (issues/10-fallback-freeze.md;
tables/writes.json maintenance_exempt.freeze-legacy).

A one-time migration, not a layer write: freezes the legacy runs.jsonl into
runs.legacy.jsonl (owners=frozen) and zeroes the main file so record.py and
`runs-append` start it from zero rows. Does not take --layer -- legality
here comes entirely from the two mechanical checks below (byte-identical
copy, zeroed main file), not from the schema/write-right machinery that
_lib.validate() and the ledger's owner checks provide for regular rows;
this module never touches either.

legacy path = the runs ledger's own directory + "runs.legacy.jsonl" (the
same value `tables/ledgers.json` optional_ledgers.runs_legacy's default_path
resolves to when runs.jsonl sits at its own default path -- computed here
from the actual runs path rather than a second lookup, since research-
loop.json's ledgers/owners keys for runs_legacy are not expected to be
wired yet at freeze time: the reminder this command prints on success is
what tells the operator to add them).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import _lib


def _legacy_path(runs_path: Path) -> Path:
    return runs_path.parent / "runs.legacy.jsonl"


def run(args) -> int:
    root = _lib.find_project_root()
    cfg = _lib.load_config(root)
    runs_path = Path(cfg.ledger_path("runs"))
    legacy_path = _legacy_path(runs_path)

    if legacy_path.exists():
        print("freeze-legacy already done; repeat refused", file=sys.stderr)
        return 1

    if not args.confirm:
        print(
            f"would freeze {runs_path} into {legacy_path} (byte copy), then "
            f"zero {runs_path}; pass --confirm to execute",
            file=sys.stderr,
        )
        return 1

    with _lib.locked(runs_path):
        original = runs_path.read_bytes() if runs_path.exists() else b""

        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_bytes(original)
        # mechanical check (1): legacy is byte-identical to the original.
        if hashlib.sha256(legacy_path.read_bytes()).hexdigest() != hashlib.sha256(original).hexdigest():
            _lib.fail("runs_legacy", "bytes", "legacy copy is not byte-identical to the original")

        runs_path.parent.mkdir(parents=True, exist_ok=True)
        runs_path.write_bytes(b"")
        # mechanical check (2): the main file is zero bytes (zero rows).
        if runs_path.stat().st_size != 0:
            _lib.fail("runs", "bytes", "main file was not zeroed by freeze-legacy")

    print(
        "freeze-legacy done: add 'runs_legacy' to research-loop.json's "
        "ledgers and owners keys."
    )
    return 0


def register(subparsers):
    parser = subparsers.add_parser(
        "freeze-legacy",
        help="One-time migration: freeze legacy runs.jsonl into runs.legacy.jsonl.",
    )
    parser.add_argument("--confirm", action="store_true")
