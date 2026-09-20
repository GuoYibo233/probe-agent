# 12 The inject code-currency gate compares raw `VERSION`s, so any bump of a probe-side module blocks every inject run for good

Status: needs-triage
Severity: important
File: run.py:1924-1948
Contract: 2.5 ("`inject` refuses when the live code is not the code its probes were trained under")
Errata: the ruling "3.3 / 8.6 (what a `VERSION` bump invalidates)" rewrote what a bump means — the key folds a file's *effective* version for a stage, and "a bump that leaves a stage usable keeps that stage's run directory". The entry does not mention this gate, and the gate was not brought along.

## Finding

The gate reads each referenced run's frozen `_versions` — which record the file's real
`VERSION` (errata "3.3 / 8.6": "`_versions` in `settings.yaml` and `meta.json` keeps
recording the file's real `VERSION`") — and compares them for equality against the
current source:

```python
        for src_dir, mod, recorded in checks:
            current = schema.module_version(mod)
            if recorded != current:
                sys.exit(
                    f"run.py: inject refuses: {label} ({src_dir}) recorded {mod} VERSION "
                    f"{recorded}, current source VERSION is {current}")
```

`schema.module_version` is the raw `VERSION` reader. The stale test the same file uses
for `ls` (`run.py:404-429`) is the other one: `schema.effective_version(path, stage)`
against the recorded number, which is what the key folds.

## Failure scenario

`models/probe_models/base.py` is at `VERSION = 2` today with
`VERSION_HISTORY = {2: {..., "stale": ("train",)}}`. Suppose a later change to that file
touches the serving path only and its author writes the entry the rule asks for,
`3: {"why": "...", "stale": ("inject",)}` — trained checkpoints stay usable, live runs
must be recollected. Then:

- every existing `train` run keeps its key and its directory, and the walk skips it on
  `done.json` (`run.py:2016`), so its `settings.yaml` is never re-frozen and its
  `_versions["models/probe_models/base.py"]` stays `2` forever;
- the `inject` key moves, as intended, and the walk builds a fresh inject directory;
- the gate above then exits with `recorded 2, current source VERSION is 3` on every
  launch of that fresh run.

No flag escapes it (`--allow-dirty` covers git, not this), `run.py retry` re-enters the
same gate, and the only way to launch an inject run again is to retrain both probes —
GPU days for a bump whose own entry says the train outputs are fine. The same holds for
a `data/probe_input.py` or backbone bump declared `stale: ("eval",)`. The gate as written
is the one place in the tree where a bump still costs the large-model outputs the ruling
was written to protect.

## Proposed fix

Compare the same way the key does. For each of the three modules, refuse when the
module's effective version for the stage that produced the recorded number stands above
that number: `schema.effective_version("data/probe_input.py", "build") > recorded` for
the build run's entry, and `schema.effective_version(mod, "train") > recorded` for the
two train-run entries. Keep the message naming the module and both numbers, and add the
bump's own `why` from `schema.version_history(mod)`, the way `_stale_sentence` already
does, so a refusal says which bump made the probes stale.
