#!/usr/bin/env python3
"""Minimal fallback task registry (tables/config.json `_fallback_rule`,
issues/10-fallback-freeze.md).

    registry.py --list              -- print each task name, one per line,
                                        no side effects
    registry.py <task> [args...]    -- subprocess-forward to that task's
                                        argv + args, passthrough exit code

Unknown task -> stderr error, exit 4. The only two tasks this fallback ships
are the plugin's own self-test fixtures (fake-experiment / fake-metrics,
tables/rows.json enums["fake.mode"]) -- a real project's registry_cmd has an
open task list, this one does not (tables/config.json _fallback_rule:
"除此之外不复刻任何高级功能").
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _lib  # noqa: E402

_FALLBACK_DIR = _lib.plugin_root() / "scripts" / "fallback"

_TASKS = {
    "fake-experiment": [sys.executable, str(_FALLBACK_DIR / "fake_experiment.py")],
    "fake-metrics": [sys.executable, str(_FALLBACK_DIR / "fake_metrics.py")],
}


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] == "--list":
        for name in _TASKS:
            print(name)
        return 0

    if not argv:
        print("usage: registry.py --list | <task> [args...]", file=sys.stderr)
        return 4

    task = argv[0]
    if task not in _TASKS:
        print(f"registry: unknown task: {task}", file=sys.stderr)
        return 4

    cmd = _TASKS[task] + argv[1:]
    proc = subprocess.run(cmd)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
