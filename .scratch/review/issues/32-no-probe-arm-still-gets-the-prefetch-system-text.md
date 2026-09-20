# 32 `system_text` returns the p1 format's system text under `arm: no_probe`, so the control arm's developer message describes a mechanism that never fires

Status: needs-triage
Severity: important
File: agent/step_with_probe.py:35-40
Contract: 7.3 ("Who applies `system_text` for a `p1` format": returns `FORMATS[cfg.inject.format].system_text` only when the placement is `p1`, "and None otherwise — None for a `p2` entry ... and None when the setting has no `inject` section **or its arm never fires**")
Errata: not recorded. Errata "7.2 (the injector's `/health` refusal)" rules that the health refusal is taken under all three arms; nothing rules on the arm for `system_text`.

## Finding

```python
def system_text(cfg) -> str | None:
    """FORMATS[cfg.inject.format].system_text when that entry's placement is p1, None otherwise ..."""
    if cfg.inject is None:
        return None
    fmt = FORMATS[cfg.inject.format]
    return fmt.system_text if fmt.placement == "p1" else None
```

Two of 7.3's three None cases are implemented — no `inject` section, and a `p2`
entry — and the third, "its arm never fires", is not. `arm: no_probe` is the arm
that never fires: `agent/step_with_probe.py:157` sets
`probing = cfg.inject.arm != "no_probe"`, and with `probing` false the cut loop
is never entered, so no note is ever built and no `spec` row is ever written.

`agent/run_tasks.py:115` computes the value once and hands it to `to_messages`
on every step:

```python
    extra = step_with_probe.system_text(cfg)
    ...
            messages = to_messages(
                writer.frame(), step_index, task_text,
                env.INSTRUCTIONS[cfg.data.instructions], env.NO_CODE_MESSAGE, extra,
            )
```

`to_messages` appends it to the developer message
(`data/trajectory_record.py:275`). Two of the five formats carry a non-null
`system_text` at `placement: "p1"` — `p1_e2`
(`agent/injected_text_formats.py:67`) is the only one today, and any future p1
entry with an explanation in the system message is the second.

## Failure scenario

`run.py inject <setting>` with `inject: {arm: no_probe, format: p1_e2}`, the
control arm of the injection-format comparison:

- Every step's developer message ends with `SYSTEM_EXTRA`: "Sometimes a
  prefetched result appears while you reason, either as a line starting with
  [Prefetch] or as a message from a sender named prefetch. It means the system
  already ran that call for you; use the result without calling it again."
- No prefetch ever appears in that run, by construction.
- `gen.prefix_sha` of the `no_probe` run therefore differs at step 0 from the
  paired `sample` baseline's for the same `(task_id, seed)`, and
  `eval/score_run.py`'s `paired.delta_success` against that baseline measures
  the injection **plus** a developer-message change.
- Nothing on disk records the difference: `meta.inject` is a canonical-JSON echo
  of the `inject` section (`agent/run_tasks.py:54`), not of the developer
  message, and `meta.generation` does not carry it either, so the same-setup
  comparison in `eval/score_run.py` passes.

## Proposed fix

Root cause: the accessor implements two of the three conditions 7.3 states. In
`agent/step_with_probe.py`, return the text only for a run that can splice one —
a `p1` entry under an arm that fires:

```python
    fmt = FORMATS[cfg.inject.format]
    if fmt.placement == "p1" and cfg.inject.arm in FIRING_ARMS:
        return fmt.system_text
    return None
```

with the firing arms named beside `ARMS` in the same file (`probe` and
`probe_nofill` today; `no_probe` is the arm that never fires). One question for
the owner rides on it: `probe_nofill` fires but splices an empty note
(`agent/step_with_probe.py:213-215`), so under that arm the system text also
describes something the model never sees; 7.3's wording ("never fires") keeps it
and the text's own content argues for dropping it.
