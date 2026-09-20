# 22 The agent client's health() has no caller, so the loop never tests the agent server it is about to use

Status: needs-triage
Severity: minor
File: models/agent_models/service.py:348-361
Contract: 7.1 (client half: `health()` -> `GET /health`, `GET /v1/models`)
Errata: not recorded

## Finding

The agent client offers the health call the contract pins:

```python
348     def health(self) -> dict:
349         root = self.base_url[:-len("/v1")] if self.base_url.endswith("/v1") else self.base_url
350         up = True
351         try:
352             _request(root + "/health", None, timeout=10.0, retries=1)
...
361         return {"up": up, "served_model_names": names}
```

Nothing calls it. `grep -rn "health" --include=*.py agent/ jobs/ run.py train/ eval/ data/`
returns only probe-service calls: `agent/run_tasks.py:97`
(`clients.probe.health()`) and `agent/step_with_probe.py:54`
(`probe.health()`). `agent/run_tasks.py:92-95` builds the agent client and
hands it straight to the two step files, which use `stream` alone.

`README.md:187` says otherwise:

```
  used by: agent/step_without_probe.py (client), agent/run_tasks.py (health); jobs/launch.py starts it as a piece, ...
```

`agent/run_tasks.py` does import this file, so `run.py selfcheck` check 2 is
satisfied by the import edge and never sees that the parenthetical names a call
the file does not make. `README.md:223` gives the same import the other
qualifier, `models/agent_models/service.py (client)`, so the two lines already
disagree with each other.

## Failure scenario

The agent service writes `service_agent_0.json` only after `/health` answers and
the two checks pass (`models/agent_models/service.py:215-221`), and the loop
piece waits for that file (`agent/run_tasks.py:88`). Between that write and the
loop's first request the vLLM process can be gone — an engine OOM on a card
shared with another job, or any crash after its `/health` answered, and the
window is real because `jobs/launch.py:1114-1119` starts the loop pieces in a
second wave, after the service wave and (on an inject run) the probe `check`
client. The loop then starts its walk with no test of the agent server
at all: the first `stream()` inside `step` raises `urllib.error.URLError` after
three retries, and `agent/run_tasks.py:180-189` catches every exception per task
and writes

```
final  abort="task_error:URLError"  success=false
```

then moves to the next task and does it again. A dead agent server therefore
produces a full rotation of task records that all look like judged failures,
and `eval/score_run.py` counts them as `n_abort`. The probe service gets the
opposite treatment three lines earlier: `agent/run_tasks.py:97-109` refuses to
start at all when its `/health` echo is wrong.

## Proposed fix

Give the agent client's `health()` the caller the README already claims, next to
the probe refusal that is already there. In `agent/run_tasks.py`, after the
probe health block at line 97-109 and before the walk, refuse on a server that
is down or does not serve the frozen model name:

```python
agent_health = clients.agent.health()
if not agent_health["up"]:
    raise SystemExit(f"agent.run_tasks: agent service {agent_doc['base_url']} does not answer /health")
want = cfg.models.agent_row["served_model_name"]
if want not in agent_health["served_model_names"]:
    raise SystemExit(
        f"agent.run_tasks: agent /v1/models does not name {want!r} "
        f"(has {agent_health['served_model_names']})"
    )
```

That is one refusal per loop piece, taken once before the walk, in the same
place and shape as the probe refusal. `README.md:187`'s `(health)` qualifier is
then true; if the owner would rather the loop stay silent here, the fix is the
other direction — drop `health()` from this file and the `(health)` qualifier
from `README.md:187` — but one of the two has to move, because today the line
describes a call that does not exist.
