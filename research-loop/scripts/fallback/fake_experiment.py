#!/usr/bin/env python3
"""Fake experiment task -- plugin self-test fixture only (tables/config.json
`_fallback_rule`: "兜底三件同时充当 plugin 自测的假铁轨"), not one of the
plugin's nine real scripts. Registered into the fallback registry under the
name "fake-experiment" (registry.py).

    fake_experiment.py --seed N --mode M --out DIR

`M` is one of `tables/rows.json` enums["fake.mode"]:

- ok / bad-metrics: write DIR/result.jsonl (5 lines, {"i": k, "v": seed*k}
  for k in 0..4), exit 0. Both modes produce the same product; it's
  fake_metrics.py that behaves differently for bad-metrics.
- fail: stderr "simulated failure", exit 1.
- empty: create an empty DIR/result.jsonl, exit 0.
- timeout: sleep 30s then exit 0 -- the launch side is expected to kill this
  well before that (its own timeout is expected_runtime_s * runtime_factor).

DIR/mode.txt = M is written first, for every mode -- fake_metrics.py reads
it to decide the bad-metrics branch, and it's the one artifact every mode
leaves behind even on failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _lib  # noqa: E402


def main(argv=None) -> int:
    modes = _lib.load_tables()["rows"]["enums"]["fake.mode"]
    parser = argparse.ArgumentParser(description="Fake experiment task (plugin self-test fixture).")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--mode", choices=modes, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "mode.txt").write_text(args.mode, encoding="utf-8")

    if args.mode in ("ok", "bad-metrics"):
        with open(out / "result.jsonl", "w", encoding="utf-8") as f:
            for k in range(5):
                f.write(json.dumps({"i": k, "v": args.seed * k}) + "\n")
        return 0

    if args.mode == "fail":
        print("simulated failure", file=sys.stderr)
        return 1

    if args.mode == "empty":
        (out / "result.jsonl").write_text("", encoding="utf-8")
        return 0

    # args.mode == "timeout" (argparse choices already gate this to the
    # remaining enum value)
    time.sleep(30)
    return 0


if __name__ == "__main__":
    sys.exit(main())
