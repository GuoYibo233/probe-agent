# 23 _open_stream retries every 4xx but 400, against 7.1 and against _request in the same file

Status: needs-triage
Severity: minor
File: models/agent_models/service.py:311-313
Contract: 7.1 ("Retries: three, with exponential backoff, on connection errors and 5xx; a 400 is passed to the caller")
Errata: not recorded (errata "7.1: `stream(prompt_ids, generation, seed)`..." fixes the shape of `generation` and repeats "a 400 re-raises as `urllib.error.HTTPError` and everything else retries three times"; it settles the 400 case, not the other 4xx)

## Finding

The file holds two request helpers with two different rules for a 4xx. The
plain one raises at once, as the contract says:

```python
108         except urllib.error.HTTPError as e:
109             if e.code < 500 or attempt == retries - 1:
110                 raise
111             last_exc = e
```

The streaming one keys on the single code 400:

```python
311         except urllib.error.HTTPError as e:
312             if e.code == 400 or attempt == _RETRIES - 1:
313                 raise
314             last_exc = e
```

so a 401, 404, 404-with-a-body, 413 or 422 from `POST /v1/completions` is slept
on and re-sent twice before the caller ever sees it, with the backoff of line
319 (`_RETRY_BASE_S * 2 ** attempt`, so 1 s then 2 s).

## Failure scenario

The one 4xx a healthy path produces today is the 400 of a context overflow, and
that one is handled: 400 raises at once and `agent/run_tasks.py:166-169` records
`abort="context_overflow_400"`. The deviation bites on the other 4xx vLLM
defines. `POST /v1/completions` answers
`404 {"message": "The model `X` does not exist."}` when its `model` field names
a model the server does not serve, and the loop's `model` field is
`cfg.models.agent_row["served_model_name"]`, frozen once at the launch
(`agent/run_tasks.py:93`) and never re-checked against the server the endpoint
file points at (ticket 22). Reach that state — a vLLM restarted by hand on the
row's `serving.port` with another model, or the agent server of an
`--attach-only` target replaced while this run keeps its endpoint file — and
every step of every task pays three requests and `1 + 2 = 3` s of sleep
(`models/agent_models/service.py:319`) before `agent/run_tasks.py:180-189` can
write its `abort="task_error:HTTPError"` row. The piece then walks its whole
rotation at three times the request cost, writing aborted records, where the
contract's rule would have surfaced the 404 on the first request.

I could not construct a first-party path that produces a non-400 4xx while both
services are healthy, so this is a latent deviation rather than a live bug; it
is written up because the contract sentence, the sibling helper eleven lines
above and this loop state three different rules for the same case.

## Proposed fix

Give `_open_stream` the rule `_request` already has, so one sentence covers both
helpers: retry a 5xx, pass every 4xx to the caller.
`models/agent_models/service.py:311-313` becomes

```python
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == _RETRIES - 1:
                raise
            last_exc = e
```

The 400 path is unchanged (400 < 500 raises at once), which is what
`agent/run_tasks.py:166-169` reads to write `abort="context_overflow_400"`.
