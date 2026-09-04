#!/usr/bin/env python3
"""Run every tests/test_*.py with unittest and print one line per test file.

Build rule (30 L187): a build step is closed only when this is all green.
Usage: python3 tests/run_all.py [-k substring] [-v]
"""

import argparse
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", default=None, help="only test files whose name contains this")
    ap.add_argument("-v", action="store_true")
    ns = ap.parse_args()
    sys.path.insert(0, str(HERE))
    files = sorted(HERE.glob("test_*.py"))
    if ns.k:
        files = [f for f in files if ns.k in f.name]
    total = unittest.TestResult()
    overall = 0
    for f in files:
        suite = unittest.defaultTestLoader.loadTestsFromName(f.stem)
        result = unittest.TextTestRunner(verbosity=2 if ns.v else 0, stream=sys.stderr).run(suite)
        bad = len(result.failures) + len(result.errors)
        overall += bad
        skipped = len(result.skipped)
        print(f"{'GREEN' if bad == 0 else 'RED  '} {f.name}: ran={result.testsRun} failed={len(result.failures)} "
              f"errors={len(result.errors)} skipped={skipped}")
    print("ALL GREEN" if overall == 0 else f"{overall} failing")
    return 0 if overall == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
