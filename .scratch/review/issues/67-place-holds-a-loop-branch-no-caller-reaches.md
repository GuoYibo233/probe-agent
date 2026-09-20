# 67 3.4's loop placement rule is written twice, and the copy inside place() has no caller

Status: needs-triage
Severity: minor
File: jobs/launch.py:281
Contract: 3.4 ("Which host a piece lands on. The rule is one paragraph, and `jobs/launch.py` applies it"), README section 1 (no near-duplicate files)
Errata: not recorded

## Finding

`place` is the function that holds 3.4's placement paragraph, and its first branch is the loop
rule:

```python
def place(kind, cards_needed, free_by_host, *, serving_host, prefer_host, attached) -> str | None:
    if kind == "loop":
        return _login_host()
    if kind == "service_probe" and cards_needed == 0:
        return _login_host()
```

Nothing ever passes `kind="loop"`. The four call sites are `place("train", ...)` (:986),
`place("service_agent", ...)` (:1002), `place("service_probe", ...)` (:1027) and `refire`'s
`placement_kind`, which is one of `service_agent`, `train`, `service_probe` and is reached only
under `if kind != "loop" and cards_needed > 0` (:1194-1198). `place` is not imported anywhere
else (it appears only in `jobs/launch.py`).

`launch()` places a loop piece with its own copy of the rule instead (:970-976):

```python
            if kind == "loop":
                venv = _resolve_venv(entry["venv"]["loop"], env_name)
                python = _interpreter_for(venv)
                host = _login_host()
```

So the rule "loop pieces take no card and run on `login_host`" exists in two places, and the
one that reads as the rule's home is dead.

## Failure scenario

The cluster gains a second login-capable machine, or loop pieces are moved off `login_host`
(3.4's paragraph is the one place that decides this). An agent following the README's
"every file does one thing its name says" reads `place`, changes its loop branch, runs
`run.py selfcheck` — green, nothing imports the branch — and the change has no effect at all:
every loop piece still lands where `launch()`'s inline `_login_host()` puts it. The same trap
catches any reviewer reading `place` to answer "where do loop pieces run".

## Proposed fix

Keep one copy. `launch()` calls `place("loop", 0, free_by_host, serving_host=None,
prefer_host=None, attached=False)` for a loop piece, the way it already does for the other
three kinds, so every placement decision goes through the function 3.4's paragraph lives in
and the dead branch becomes the live rule.
