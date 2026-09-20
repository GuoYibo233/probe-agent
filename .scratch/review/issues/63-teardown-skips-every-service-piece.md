# 63 The attached_to skip is taken for the whole run, so the service pieces nobody borrowed are never ended

Status: needs-triage
Severity: minor
File: jobs/launch.py:652
Contract: 2.3 ("Ending the service pieces"), 8.1
Errata: not recorded

## Finding

`teardown_services` tests `attached_to` once, for the run, and returns before it looks at any
piece:

```python
    meta = _read_json(run_dir / "meta.json") or {}
    run_id = _run_id_of_meta(meta)
    if run_id and _attached_elsewhere(run_id):
        return []
    ended = []
    for piece in meta.get("pieces") or []:
        if piece.get("kind") != "service":
            continue
```

`attached_to` is only ever written by an agent service: `_find_attach_target` (:770-802)
searches `service_agent_*.json` alone, and `launch()` passes `attached_to` only on the agent
serve line (:1013-1016). So the piece another run is holding open is one agent replica, while
the skip spares every service piece of the run — the other replicas and the probe service,
which no other run can be using.

The contract sentence is written per piece ("skipped for a service piece whose owning `run_id`
appears in the `attached_to` field of another live run's `service_<kind>_<replica>.json`"), and
its stated purpose is that nothing is left "holding their cards forever"; the rationale names
the probe service beside the vLLM server as what the teardown exists to stop.

## Failure scenario

A `baseline` `sample` run S is collecting with `replicas: 1`: piece 6 is its vLLM server on
tokyo108, piece 7 its `--render-only` probe service on `login_host`. An `inject` run I starts
while S runs, the attach test matches S's server, and I writes
`service_agent_0.json` with `attached_to: "sample-<key of S>"`.

S finishes. `run.py` writes S's `done.json` and calls `launch.teardown_services(S)`
(run.py:1842). `_attached_elsewhere("sample-<key>")` is true because I is open, so the
function returns `[]` — and S's probe service piece, which I neither found nor uses, keeps its
python process and its tmux session on the login machine for good. `run.py ls` flags S
`orphan`, and no command ends that piece: teardown is called once, at the moment the run
closes, and never again.

With `sample.replicas: 2` the same skip leaves replica 1's vLLM server running with its cards
held, which is the state 2.3's rationale calls "they hold their cards forever" and which
`run.py free` then reports busy.

## Proposed fix

Make the skip the per-piece test the contract states: `teardown_services` ends every
`kind: service` piece except the one another live run's `service_agent_*.json` is pointing at
— match on that document's `host` and `port` against the piece entry, the same two fields
`_find_attach_target` (:798-800) already uses to decide that a document is current. The
borrowed replica stays up and is flagged `orphan`; the rest of the run's services end.
