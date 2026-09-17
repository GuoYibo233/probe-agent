# new1

This file is assembled whole from the contracts document at the end of the
from-zero build (ticket 14). Until then, each ticket appends its own files'
lines here; merge conflicts on this file across tickets of one wave are
expected and are resolved by keeping every ticket's lines.

## Ticket 03 — the registry and the ledger

```
jobs/registry.py — the registry: runs.jsonl rows under a lock, meta.json, the
heartbeat, the verdicts, ls/where/find/kill/free/sync, RESULTS.md.
  imports: none (repo); [PyYAML]
  used by: run.py, jobs/launch.py, agent/loop.py, data/build_dataset.py,
           train/utils/trainer.py, eval/utils/probe_eval.py,
           eval/score_run.py, eval/method_table.py
  reads:   constants/path_outputs.yaml, jobs/runs.jsonl, run directories'
           meta.json and heartbeat, ssh, tmux, nvidia-smi
  writes:  jobs/runs.jsonl, jobs/RESULTS.md, meta.json,
           heartbeat/<piece>-<launch>.jsonl, done.json
  venv:    any

jobs/runs.jsonl — one registry row per stage run, appended at start and at
finish by registry.py; never edited by hand; in git.

jobs/RESULTS.md — rendered from runs.jsonl by registry.py; never edited by
hand.

tests/test_registry_concurrent_append.py — two pieces appending to
runs.jsonl at once both land: eight forked processes append 20 start rows
each into a throw-away copy of the tree; asserts 160 lines land and every
line parses as JSON.
  venv:    probe
```

## How to run (ticket 03's own piece)

`jobs/registry.py` is a library with no `__main__`; nothing here is run
directly. Every stage program calls `append_start`/`append_finish`,
`write_meta`, `write_done` and `beat` to record itself; `run.py` (ticket 14)
calls `ls`, `where`, `find`, `kill`, `free`, `sync` for its subcommands.

Run the concurrent-append check with the probe interpreter:

```
external/probe-env/bin/python tests/test_registry_concurrent_append.py
```
