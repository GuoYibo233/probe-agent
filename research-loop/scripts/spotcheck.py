#!/usr/bin/env python3
"""Oversight-face fixed-seed sampler (R3, plan.md §C6).

Usage:
    spotcheck.py --file PATH --seed N [--k K]

Picks min(K, total line count) line numbers out of FILE via
`random.Random(seed).sample(...)` -- the same (file, seed, K) always
produces the same sample, in the same order, so a re-run is a byte-for-byte
repeat of the first (this script's own reproducibility contract) and a
one-byte edit anywhere in the file changes `fingerprint` (sha256 is over the
file's raw bytes, independent of how the sample itself comes out).

stdout is a single JSON object:
    {"fingerprint": {"rows": <int>, "sha256": <hex>},
     "samples": [{"ref": "<path>:<line>", "excerpt": <line's first 80 chars>}, ...]}

`path` in each `ref` is FILE exactly as given on the command line (not
resolved to an absolute path) -- so a ref is directly re-checkable by
whatever cwd the caller already has FILE relative to. `rows` and line
numbers both come from `splitlines()` on the UTF-8-decoded text (an
unterminated last line still counts as a row -- consistent with the
sha256, which is computed once over the whole file up front, before any
line splitting).

Exit 0 on success; 2 if FILE cannot be read.

Spec: .scratch/research-loop/issues/13-oversight.md; spec.md R3 (§3);
plan.md §C6.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

_DEFAULT_K = 5
_EXCERPT_CHARS = 80


def run(file_arg: str, seed: int, k: int) -> dict:
    path = Path(file_arg)
    raw = path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()

    lines = raw.decode("utf-8", errors="replace").splitlines()
    rows = len(lines)

    sample_size = min(k, rows)
    line_numbers = random.Random(seed).sample(range(1, rows + 1), sample_size)

    samples = [
        {"ref": f"{file_arg}:{n}", "excerpt": lines[n - 1][:_EXCERPT_CHARS]}
        for n in line_numbers
    ]

    return {
        "fingerprint": {"rows": rows, "sha256": sha256},
        "samples": samples,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Fixed-seed spot-check sample: a reproducible pointer list into FILE plus its whole-file fingerprint.",
    )
    parser.add_argument("--file", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--k", type=int, default=_DEFAULT_K)
    args = parser.parse_args(argv)

    try:
        result = run(args.file, args.seed, args.k)
    except OSError as exc:
        print(f"spotcheck: could not read {args.file}: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
