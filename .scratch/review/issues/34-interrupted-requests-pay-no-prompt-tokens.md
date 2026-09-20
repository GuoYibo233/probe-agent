# 34 an interrupted request's prompt tokens are never counted, so `gen.usage.in` and `final.tokens_in` undercount exactly the steps that fired

Status: needs-triage
Severity: minor
File: agent/step_with_probe.py:266-270
Contract: 1.1 (`gen.usage`: "prompt and completion tokens"; `final.tokens_in`/`tokens_out`: "totals for the run")
Errata: not recorded

## Finding

The per-stream usage fold reads the server's usage chunk when there is one and
falls back to the streamed id count when there is not:

```python
        if st.usage:
            usage_in += st.usage.get("prompt_tokens", 0)
            usage_out += st.usage.get("completion_tokens", 0)
        else:
            usage_out += st.n_ids
```

`Stream.usage` is filled only by the final chunk vLLM sends under
`stream_options: {"include_usage": True}` (`models/agent_models/service.py:338`,
`:281-282`). A fire breaks out of the stream iteration before that chunk
arrives (`agent/step_with_probe.py:262-264`, then `st.close()` at `:277`), so
for every request a fire cut short `st.usage` is `None` and the `else` branch
runs. That branch adds to `usage_out` only; **`usage_in` gets nothing**.

A step with `F` fires issues `F + 1` requests, each carrying a prompt of
`len(prefix_ids) + len(gen_ids so far)` tokens, and the `gen` row records the
prompt of the last one alone.

## Failure scenario

An inject run with `arm: probe`, `max_inject_per_step: 1`, `max_step_tokens:
8192`, on a step whose prompt is 6,000 tokens and that fires after 400 generated
tokens:

- Request 1 is cut off at the fire: 6,000 prompt tokens, uncounted.
- Request 2 runs to the end: 6,000 + 350 kept tokens of prompt, counted.
- `gen.usage.in` records ~6,350 where the step cost ~12,350.

Every `probe` and `probe_nofill` step that fires is understated by one whole
prompt, while the paired `no_probe` and `sample` runs, which never fire, are
exact. A person comparing `final.tokens_in` between the arms — the input-side
cost of the injection method — reads the interruption as free.
`eval/score_run.py` does not read the column today (its docstring's
`TODO(gyb, 2026-09-18)` lists `tokens_in` among the fields the owner had removed
from the report), so nothing else catches it.

## Proposed fix

Root cause: the fallback branch assumes a stream with no usage chunk generated
tokens and consumed no prompt, which is true of no request. In
`agent/step_with_probe.py`, count the prompt of every request from what the step
already knows, since it built the prompt itself:

```python
        if st.usage:
            usage_in += st.usage.get("prompt_tokens", 0)
            usage_out += st.usage.get("completion_tokens", 0)
        else:
            usage_in += request_prompt_tok      # len(prefix_ids) + len(gen_ids) at the send
            usage_out += st.n_ids
```

with `request_prompt_tok` captured beside the `stream(...)` call at line 165,
which is the one place that knows the ids it sent.
