# 24 The README's reader lines for models/table.yaml and constants/path_models.yaml leave out the probe service and understate the agent service

Status: needs-triage
Severity: minor
File: README.md:169
Contract: 6.2 ("The first exception, the probe service's `serve`, ... resolves two keyed columns live: `family` and `weights`")
Errata: not recorded (errata "6.2: the two exceptions ... -> `models/agent_models/service.py` resolves family and weights live through `models.agent(alias)` and compares both against `cfg.models.agent_row`" adds the agent service to the live readers and no README line followed it)

## Finding

Three lines describe who reads the model table and what they take from it, and
all three are wrong about the two service files.

`README.md:169`, for `models/table.yaml`:

```
  read by: models/__init__.py, experimental_settings/schema.py (the result block), models/agent_models/service.py (the serving block), jobs/launch.py (the serving block: host and port)
```

`README.md:78`, for `constants/path_models.yaml`:

```
  read by: models/__init__.py, models/agent_models/service.py (the weights path of the row it serves)
```

`README.md:216`, the probe service's own `reads:` line:

```
  reads:   the checkpoint directories named on its command line, including each one's best/meta.json; the run directory's settings.yaml, the check client only
```

What the code does:

- `models/probe_models/service.py:76` calls `models.agent(args.agent_model)`,
  which reads `models/table.yaml` (role, family, `result.weights`) and
  `constants/path_models.yaml` (the weights path), and `:79` opens the agent
  model's tokenizer from that path. `:112` echoes `m.family` and `m.weights` on
  `/health`, which is the live read contracts 6.2 calls "the first exception"
  and which `agent/run_tasks.py:100-109` compares against the frozen row. None
  of the three lines names this file.
- `models/agent_models/service.py:183` calls `models.agent(args.model)` and
  `:184` compares `m.family` and `m.weights` against the frozen row, so it does
  not read "the serving block" only (`README.md:169`) and its own `reads:` line
  at `README.md:188` repeats the same understatement, `models/table.yaml (the
  serving block only)`. That live read is required by the errata entry quoted
  above.
- `README.md:215` gives `agent/run_tasks.py (client: render)` while
  `agent/run_tasks.py:97` also calls the probe client's `health()`.

`run.py selfcheck` cannot catch any of this: check 1 tests that entries exist
and check 2 tests `imports:`/`used by:` against the import graph, so the
`reads:` and `read by:` lines are unchecked prose.

## Failure scenario

The lines are what an agent reads before touching a file (`CLAUDE.md`: "read it
before touching a file"). As written they say that inside a run only the agent
service and `jobs/launch.py` touch `models/table.yaml`, and only for the block
that is outside every key. An agent acting on that — say, one asked to decide
what an edit to a row's `family` or `result.weights` can disturb — concludes
that a running probe service is unaffected, when in fact
`models/probe_models/service.py:76` resolves both columns live at startup and
`agent/run_tasks.py:100-109` refuses to run on a difference. The same lines
also hide the second live path into `constants/path_models.yaml`, so a weights
alias moved in that file reads as touching one service when it touches two.

## Proposed fix

Correct the four lines in place, naming the files and the columns they take:

- `README.md:78` -> `read by: models/__init__.py, models/agent_models/service.py
  (the weights path of the row it serves), models/probe_models/service.py (the
  weights path of the agent row it renders and tokenizes for)`
- `README.md:169` -> `... models/agent_models/service.py (the serving block, and
  family and weights live for the comparison against the frozen row),
  models/probe_models/service.py (family and weights live, 6.2's first
  exception), jobs/launch.py (the serving block: host and port)`
- `README.md:188` -> `reads: models/table.yaml (the serving block, plus family
  and weights for the frozen-row comparison), ...`
- `README.md:215-216` -> add `health` to `agent/run_tasks.py (client: render)`
  and add `models/table.yaml and constants/path_models.yaml (through
  models/__init__.py), the agent model's tokenizer files` to the `reads:` line.
