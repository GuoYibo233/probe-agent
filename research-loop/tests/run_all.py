#!/usr/bin/env python3
"""Stdlib test runner for the research-loop plugin.

Usage:
    python3 research-loop/tests/run_all.py            # run every test_*.py
    python3 research-loop/tests/run_all.py test_lib   # run one module

Discovers test_*.py files next to this script and runs every top-level
callable whose name starts with test_. No third-party dependencies.
Exit code: 0 when everything passes, 1 otherwise.
"""
import importlib.util
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    wanted = {name.removesuffix(".py") for name in sys.argv[1:]}
    files = sorted(HERE.glob("test_*.py"))
    if wanted:
        missing = wanted - {f.stem for f in files}
        if missing:
            print(f"no such test module(s): {', '.join(sorted(missing))}")
            return 1
        files = [f for f in files if f.stem in wanted]
    passed, failed = 0, []
    for f in files:
        try:
            mod = load_module(f)
        except Exception:
            print(f"FAIL {f.stem} (import error)")
            traceback.print_exc()
            failed.append(f"{f.stem} (import)")
            continue
        tests = [(n, fn) for n, fn in sorted(vars(mod).items())
                 if n.startswith("test_") and callable(fn)]
        for name, fn in tests:
            try:
                fn()
            except Exception:
                print(f"FAIL {f.stem}.{name}")
                traceback.print_exc()
                failed.append(f"{f.stem}.{name}")
            else:
                passed += 1
                print(f"PASS {f.stem}.{name}")
    print(f"-- run_all: {passed} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
