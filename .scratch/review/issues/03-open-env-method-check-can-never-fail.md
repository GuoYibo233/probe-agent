# 03 open_env's nine-method check can never fail, so a half-written environment reaches a live run

Status: needs-triage
Severity: important
File: data/environments/__init__.py:97-109
Contract: 4.1 ("`open_env` ... checks that the nine methods exist and the seven class attributes are set")
Errata: not recorded. Errata "4.1 `open_env`" settles which class is instantiated and that the block is read first; it does not touch the method check.

## Finding

`open_env` tests the nine methods with `hasattr` on the instance:

```python
    missing_methods = sorted(
        m
        for m in ("tasks", "open", "step", "speculate", "judge", "close", "split_args", "build_call", "complete_call")
        if not hasattr(instance, m)
    )
```

`Environment` defines all nine itself (lines 47-72), each as a body that raises
`NotImplementedError`. A subclass therefore inherits every name, so
`hasattr(instance, m)` is true for all nine whatever the subclass wrote, and
`missing_methods` is always empty.

Confirmed by running a subclass that implements nothing and sets only the seven
attributes: the list of missing methods comes back `[]`.

The attribute half of the check does work, because `NAME`, `VERSION`,
`INSTRUCTIONS`, `NO_CODE_MESSAGE`, `RESULT_CAP`, `SEED` and `SPLIT_ROLE` are
bare annotations on `Environment` and bind no value.

## Failure scenario

`README.md` section 3 recipe 1 adds `data/environments/<env>.py` as the whole
cost of a new benchmark, and `open_env` is the only thing that checks the file
before a stage runs. An environment that implements eight of the nine methods
and forgets `complete_call` (or `speculate`, or `build_call`) loads without a
word:

- `run.py <workflow> <setting>` freezes the setting, takes the launch gate and
  starts the loop pieces on cards.
- Every task reaches the first fire and raises `NotImplementedError:
  complete_call` inside `agent/step_with_probe.py`.
- `agent/run_tasks.py:180` catches it per task and writes a `final` row with
  `abort="task_error:NotImplementedError"`, so `is_done` calls the record done
  and the piece walks on to the next task.
- The run finishes, `done.json` is written, and `score` computes success rates
  over a set of records every one of which aborted at its first fire.

The GPU time is spent and the failure is visible only in `final.abort`.

## Proposed fix

Test that the method is the environment's own, not the base class's stub, in
`data/environments/__init__.py`:

```python
    missing_methods = sorted(
        m for m in (...)
        if getattr(type(instance), m, None) is getattr(Environment, m)
    )
```

so the affirmative rule is "every one of the nine names is bound on the
environment's own class", and the loader refuses, naming the module and the
methods, exactly as it already does for the seven attributes.
