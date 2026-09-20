# 01 speculate runs `print(None)` and records a successful prefetch when the probe's call cannot be completed

Status: needs-triage
Severity: critical
File: data/environments/appworld.py:230-234, data/environments/appworld.py:350-376
Contract: 4.3 (what `speculate` must guarantee), 4.2 (`complete_call`), 1.1 (the `spec` row)
Errata: not recorded. Errata "4.2 `complete_call`" fixes that it returns None when no call balances; nothing says what the caller or `speculate` does with that None.

## Finding

`_requote` formats a call it cannot parse straight into a `print(...)` expression:

```python
def _requote(call: str, user_ns: dict) -> tuple[str, list[str]]:
    found = _first_call_named(call or "")
    if found is None:
        return f"print({call})", ["unparsable_raw"]
```

`agent/step_with_probe.py:218-220` is the only live caller and hands it the result of
`complete_call`, which is `None` whenever the generated text holds no
`apis.<app>.<api>(` that closes:

```python
gen_call = clients.probe.generate(probe_text, cfg.inject.max_new)["call"]
completed_call = env.complete_call(gen_call)
spec = env.speculate(completed_call)
```

With `call is None` the f-string renders the Python literal `None`, so the code
that runs in the world is `print(None)`. It succeeds, so
`speculate`'s `error_kind = _error_kind(exec_out)` (line 368) is `None` and
`"exec_ok": error_kind is None` (line 373) is `True`, with `exec_out` `"None\n"`.

This is on disk in every `--debug` inject run of the section-4 walks. In
`outputs/debug/inject/*/records/*.jsonl`, 19 of the 32 `spec` rows that carry an
`exec_code` hold `print(None)`, and one of them reads:

```
gen_call  = '1000000000000000000000000000000000000000000000000000000000000000000000000000000000'
exec_code = 'print(None)'
arg_modes = ['unparsable_raw']
exec_out  = 'None\n'
exec_ok   = True
error_kind= None
note      = '[Prefetch: The system already ran 10000000...0000 for you and got:\nNone\n\nYou can use this result without calling it.]\n'
```

The `note` is the text spliced into the agent's own reasoning stream:
`agent/injected_text_formats.py`'s five renderers interpolate `call` and
`exec_out` and read neither `exec_ok` nor `error_kind`, so a speculation that
never happened is presented to the model as a successful prefetch.

## Failure scenario

An inject run whose probe emits a truncated or non-call string at a fire (the
`cgen` budget is `inject.max_new`, so a cut-off call is ordinary):

1. `complete_call` returns `None`.
2. `speculate(None)` runs `print(None)` in the live world, which succeeds.
3. The `spec` row records `exec_ok=true`, `error_kind=null`, `exec_out="None\n"`.
4. The agent is told "The system already ran <the probe's raw text> for you and
   got: None. You can use this result without calling it." and continues the
   trajectory on that sentence.

Result: the injected text of the arm under test is fabricated on those fires,
and `eval/score_run.py` reads a record whose speculation block says the early
execution succeeded. Contract 4.3's "an unparsable call is run and allowed to
fail" is inverted into "a missing call is run and reported as a success". On the
debug corpus this is the majority of fires.

## Proposed fix

Root cause: `speculate` accepts something that is not a call and reports the
result of the wrapper expression as the result of the call.

In `data/environments/appworld.py`:

- `speculate` refuses a call that is not a non-empty string, naming it, beside
  the two guards it already has ("called before open", "no frozen clock"): a
  speculation is the early execution of a call, and there is no call here.
- `_requote`'s `unparsable_raw` branch keeps running the text (4.3: never
  skipped), and `speculate` reports that branch as a failure: when `arg_modes`
  is `["unparsable_raw"]` the returned `exec_ok` is `False` and `error_kind` is
  `"unparsable_call"`, whatever the wrapper printed, so a text that is not a
  call can never be reported as a successful execution.

The companion line is `agent/step_with_probe.py:218-220`, which must stop
handing `None` to `speculate`: 4.3 wants the guess run, so it passes `gen_call`
itself when `complete_call` returns None.
