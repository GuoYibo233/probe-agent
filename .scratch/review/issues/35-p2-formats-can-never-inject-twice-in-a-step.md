# 35 under a p2 format the step stops probing after the first splice, so `inject.max_inject_per_step` above 1 can never take effect

Status: needs-triage
Severity: minor
File: agent/step_with_probe.py:250-256
Contract: 5.2 (`inject.max_inject_per_step`: "injections allowed per step"), 7.3 (item 4: the step re-enumerates and scores cuts until it has scored `inject.max_cuts` of them)
Errata: "6.2 / 7.3 (`parse(text_delta, state)` inside the two steps)" pins the post-splice rebuild to `state = {}` plus one `mod.parse(raw, state)`, and "7.3/6.2 (a p2 entry's `system_text`)" pins what `wrap_prefetch` produces; neither says what the thinking prefix becomes after a p2 splice.

## Finding

After a fire the step rebuilds its text state from the spliced stream:

```python
                raw = head_txt + note
                gen_ids = head_ids + note_ids
                bounds = [(len(raw), len(gen_ids))]
                state = {}
                out = mod.parse(raw, state)
                checked = set()
                accepted = (len(head_txt) - ts) + len(note)
```

For a `p1` entry `note` is plain text spliced into the open analysis message, so
`parse(raw)["reasoning"]` still ends `raw` and probing continues.

For a `p2` entry `note` is `mod.wrap_prefetch(body, fmt.system_text)`
(`agent/step_with_probe.py:231`), which is
`"<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>" + body +
"<|end|><|start|>assistant"` (`models/agent_models/gptoss.py:142-143`).
`gptoss.parse` skips that segment — its header starts with `<|start|>prefetch`,
which is neither `<|start|>assistant` nor `<|channel|>`, so line 122's `continue`
drops it — and the trailing `<|start|>assistant` has no `<|message|>`, so it is
dropped too. `reasoning` is therefore the head thinking alone, while `raw` ends
with the control tokens, and the next chunk hits:

```python
            thinking_so_far = out["reasoning"]
            if not raw.endswith(thinking_so_far):
                probing = False
                continue
```

`probing` goes false and stays false for the rest of the step. The same reset
also leaves `accepted` — `(len(head_txt) - ts) + len(note)` — measured against
the pre-splice thinking origin, while the model's new analysis message restarts
the thinking at offset 0, so even with the `endswith` test passing every later
cut would be dropped by `cut <= accepted` at line 184.

## Failure scenario

`run.py inject <setting>` with `inject: {format: p2_e1, max_inject_per_step: 3,
max_cuts: 64}`:

- The first crossing of `theta` fires and splices the prefetch message.
- From the next chunk on, the step scores no further cuts, whatever the thinking
  goes on to say.
- Every `gen` row of that run has `n_inject <= 1`, and no `spec` row ever
  carries `fire_index: 1`.

The setting is accepted by the loader, enters the inject key, and produces a run
indistinguishable from `max_inject_per_step: 1` — a directory and a set of
numbers for an arm that was never run. The same setting under `p1_e1` does
inject up to three times, so the two placements silently mean different things.

## Proposed fix

Root cause: the post-splice rebuild is written for a splice that stays inside
the open thinking message, and a `p2` splice closes it and opens a new one. In
`agent/step_with_probe.py`, rebuild the two quantities the next chunk needs from
what `parse` reports after the splice rather than from the pre-splice origin:
take `ts` and `accepted` from the rebuilt `out["reasoning"]`
(`ts = len(raw) - len(out["reasoning"])`, `accepted = len(out["reasoning"])`),
which is the same value for a `p1` splice and the correct one for a `p2` splice,
and start `bounds` at `[(ts, <the id count at that offset>)]` so a cut inside the
new message still finds a boundary.

The cheaper alternative is to state the restriction instead of fixing it:
`experimental_settings/schema.py` refuses `max_inject_per_step > 1` together
with a `p2` format, naming both fields, so the setting that cannot be run cannot
be written. That is a decision for the owner, since it takes a placement's
second injection off the table.
