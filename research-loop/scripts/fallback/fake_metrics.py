#!/usr/bin/env python3
"""Fake metrics task -- plugin self-test fixture only (tables/config.json
`_fallback_rule`), the `metrics_cmd` counterpart to fake_experiment.py.
Registered into the fallback registry under the name "fake-metrics".

    fake_metrics.py --dir DIR

Reads DIR/mode.txt:

- "bad-metrics" -> stdout's last line is the literal text "this is not
  json" (exit 0) -- exercises record.py's "structured output invalid"
  rejection path (tables/rows.json structured_output_contract).
- anything else -> stdout's last line is a JSON object with two metrics
  derived deterministically from DIR/result.jsonl's raw bytes: "acc" =
  int(sha256(bytes).hexdigest(), 16) % 1000 / 1000, "rows" = line count.
  Same bytes in -> the same output, byte for byte (spec §9 scenario ③'s
  source of that consistency).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _lib  # noqa: E402,F401  (kept for the fallback/ directory's uniform
# sys.path-shim header; this task has no other _lib dependency)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fake metrics task (plugin self-test fixture).")
    parser.add_argument("--dir", type=Path, required=True)
    args = parser.parse_args(argv)

    mode = (args.dir / "mode.txt").read_text(encoding="utf-8").strip()
    if mode == "bad-metrics":
        print("this is not json")
        return 0

    data = (args.dir / "result.jsonl").read_bytes()
    n = sum(1 for line in data.split(b"\n") if line.strip())
    value = int(hashlib.sha256(data).hexdigest(), 16) % 1000 / 1000

    print(json.dumps({
        "metrics": [
            {"metric_name": "acc", "value": value, "n": n, "filter": None},
            {"metric_name": "rows", "value": n, "n": n, "filter": None},
        ],
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
