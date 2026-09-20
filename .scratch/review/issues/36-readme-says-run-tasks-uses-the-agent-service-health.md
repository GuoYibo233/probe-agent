# 36 README says `agent/run_tasks.py` uses the agent service for `health`, while the health refusal it takes is against the probe service

Status: needs-triage
Severity: minor
File: README.md:187
Contract: 0.1 (the five-line annotation format), 7.2 ("`agent/loop.py` refuses to run unless `/health` reports `render == \"ids\"` ... `agent/loop.py` uses `render`"), 7.4 (the loop constructs both clients from its endpoint files)
Errata: not recorded

## Finding

```
models/agent_models/service.py — both ends of the served agent model: ...
  used by: agent/step_without_probe.py (client), agent/run_tasks.py (health); jobs/launch.py starts it as a piece, ...
```

Every `health()` call in the repo:

```
models/probe_models/service.py:197   health = client.health()      # the check client
agent/run_tasks.py:97                health = clients.probe.health()
agent/step_with_probe.py:54          health = probe.health()
```

`agent/run_tasks.py` imports `models/agent_models/service.py` for its `Client`
and constructs one (`agent/run_tasks.py:22,93`); it never calls that client's
`health()`. The refusal at `agent/run_tasks.py:97-109` — `render`, `family`,
`weights` — is read off the **probe** service's `/health`, which is where 7.2
puts those three fields. `Client.health` in
`models/agent_models/service.py:348-361` has no caller anywhere in the tree.

The companion line for the probe service is short in the other direction:

```
models/probe_models/service.py — ...
  used by: agent/run_tasks.py (client: render), agent/step_with_probe.py (client: score, generate, encode, decode)
```

`agent/run_tasks.py` calls `render` **and** `health` (line 97), and
`agent/step_with_probe.py` calls `health` as well (line 54, inside
`ensure_health`).

`run.py selfcheck` check 2 holds the file names equal to the import graph, which
both lines satisfy; the parenthetical reader's notes sit outside what it checks.

## Failure scenario

The README line is what an agent reads before touching a file (`CLAUDE.md`: "read
it before touching a file"). An agent asked to add a field to the agent
service's `/health` echo, or to tighten the loop's attach verification, reads
that `agent/run_tasks.py` is the caller of the agent service's health route,
edits `models/agent_models/service.py:348` and the loop's refusal to match, and
ships a check no process runs — while the refusal that does run, against the
probe service, is left as it was. The same line also hides that
`models/agent_models/service.Client.health` is dead: nothing in the tree calls
it, and the annotation is the only thing claiming otherwise.

## Proposed fix

In `README.md`, write what each caller uses:

- line 187: `used by: agent/step_without_probe.py (client), agent/run_tasks.py
  (client); jobs/launch.py starts it as a piece, ...`
- line 215: `used by: agent/run_tasks.py (client: render, health),
  agent/step_with_probe.py (client: health, score, generate, encode, decode); ...`

Whether `models/agent_models/service.Client.health` keeps a body once no
annotation claims a caller is a second question, and it belongs to that file's
reviewer, not to this line.
