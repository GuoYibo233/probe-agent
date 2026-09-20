# 62 refire cannot restart a service piece: the frozen serve command does not match the piece-command regex

Status: needs-triage
Severity: important
File: jobs/launch.py:1204
Contract: 2.3 ("Dead piece and refire" — no kind is excluded), 8.3 (`pieces`: "each with its frozen command, which is what `run.py refire` re-runs"), 3.4
Errata: not recorded

## Finding

`refire` plans for a service piece. It picks the placement kind off the piece entry and claims
that piece's cards (jobs/launch.py:1194-1202):

```python
    if kind != "loop" and cards_needed > 0:
        placement_kind = ("service_agent" if (kind == "service" and str(target.get("endpoint_file") or "").startswith("service_agent"))
                            else "train" if kind == "train" else "service_probe")
```

Then it rebuilds the command through the work-piece path (:1204-1206):

```python
    module, old_run_dir, piece_i, piece_n, log = _parse_piece_cmd(target.get("cmd") or "")
    python = _interpreter_for(target.get("venv"))
    new_cmd = piece_command(python, module, old_run_dir, piece_i, piece_n, new_gpus, log)
```

`_PIECE_CMD_RE` (:1129-1132) requires `-m <module> --run-dir <dir>` adjacent:

```python
_PIECE_CMD_RE = re.compile(
    r"-m (?P<module>\S+) --run-dir (?P<run_dir>\S+)(?: --piece (?P<i>\d+)/(?P<n>\d+))? "
    r"2>&1 \| tee -a (?P<log>\S+)$"
)
```

A service piece's frozen command is `_agent_service_cmd`'s (:339-343):
`... -m models.agent_models.service serve --run-dir <dir> --model <alias> --port <p> --gpus '<ids>' --replica <i> 2>&1 | tee -a <log>`.
The token after the module is `serve`, not `--run-dir`, and `-m ` occurs nowhere else in the
line, so `_PIECE_CMD_RE.search` finds nothing and `_parse_piece_cmd` exits:
`jobs/launch.py refire: could not parse the frozen command: ...`. The probe service command
(:349-358) has the same shape and the same result.

Even with a regex that matched, `piece_command` (:315-325) would emit a `loop`/`train`-shaped
line — `-m models.agent_models.service --run-dir <dir>` — dropping `serve`, `--model`,
`--port`, `--gpus` and `--replica`, so the restarted server would not start.

## Failure scenario

A `sample` run of `baseline.yaml` has pieces 0-5 `loop`, 6 `service_agent`, 7 `service_probe`
(the order `STAGES["sample"]["pieces"]` fixes, experimental_settings/schema.py:203-204). The
vLLM server on tokyo108 dies overnight; `run.py ls` shows piece 6 `dead` and the six loop
pieces stalled waiting on the endpoint.

`run.py refire baseline gpt_oss_120b_appworld sample --piece 6` then:

1. passes the liveness refusal (the session is gone),
2. calls `trajectory_record.release(...)` (:1186), deleting the unfinished claims of every
   record whose owner session is not live — a real change on disk,
3. and exits at :1204 with "could not parse the frozen command".

The run is left with its claims released, no server, and no way to restart the server through
the one command: `refire` is the only command 2.3 gives for a dead piece beside live siblings,
and `retry` deletes markers and relaunches the whole run instead.

## Proposed fix

Refire reuses the frozen command and changes only what a refire changes — the cards — instead
of re-deriving the command's shape. In `refire`, substitute the card tokens in
`target["cmd"]`: `CUDA_VISIBLE_DEVICES=<old>` for a `loop`/`train`/`cpu` piece, `--gpus
'<old>'` and `--device cuda:<old>` for a service piece, with the new ids, and keep every other
token as frozen. That deletes `_PIECE_CMD_RE` and `_parse_piece_cmd` and makes one rule cover
all four kinds, which is what 8.3 means by "its frozen command, which is what `run.py refire`
re-runs".
