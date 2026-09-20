# 33 `SYSTEM_EXTRA` starts with its own `\n\n`, and both appliers add one too, so every prompt that carries it gets a doubled separator

Status: needs-triage
Severity: minor
File: agent/injected_text_formats.py:28-31
Contract: 7.3 (`system_text` is "the extra system text this format needs", applied by the loop for a `p1` entry and by `wrap_prefetch` for a `p2` entry)
Errata: "Part 1.1 (`to_messages`'s shape)" pins the developer message as `instructions`, "plus `\"\\n\\n\" + extra_developer` when it is not None"; errata "7.3/6.2 (a p2 entry's `system_text`)" pins `wrap_prefetch` to put `system_text + "\n\n"` in front of the body. Neither entry gives the table's string a separator of its own.

## Finding

The table's string opens with a blank line:

```python
SYSTEM_EXTRA = (
    "\n\nSometimes a prefetched result appears while you reason, either as a line starting with "
    "[Prefetch] or as a message from a sender named prefetch. It means the system already ran "
    "that call for you; use the result without calling it again.")
```

Both places that apply it add the separator the errata pins:

- `data/trajectory_record.py:275`:
  `developer = instructions if extra_developer is None else f"{instructions}\n\n{extra_developer}"`
- `models/agent_models/gptoss.py:140-141`:
  `body = system_text + "\n\n" + body`

Measured with `external/probe-env/bin/python`:

```
developer = 'INSTRUCTIONS TEXT.\n\n\n\nSometimes a prefetched result appears while you reason, ...'
wrap      = '<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>\n\nSometimes a prefetched ...'
```

Four newlines between the instructions and the sentence, and a prefetch message
whose body begins with a blank line before its first word.

## Failure scenario

`run.py inject <setting>` with `format: p1_e2` (or any p2 entry, today `p2_e2`):

- Every step of every task renders a developer message with three blank lines
  where the format author wrote one, so every `gen.prefix_sha` in the run is the
  sha of a prompt nobody intended.
- Under `p2_e2` the spliced prefetch message reads
  `<|message|>\n\nSometimes ...`, a leading blank line inside a control-token
  message the model is meant to read as a system note, and that exact text is
  what `spec.note` records.
- The two formats that carry no `system_text` (`note`, `p1_e1`, `p2_e1`) do not
  get the extra blank lines, so the five arms of the format comparison differ in
  whitespace layout for a reason that is not the axis under test.

## Proposed fix

Root cause: the separator belongs to the applier, and the table's entry carries
a second copy of it. In `agent/injected_text_formats.py`, write `SYSTEM_EXTRA`
as the sentence alone, starting at `"Sometimes a prefetched result ..."`, and
leave the `\n\n` to `to_messages` and to `wrap_prefetch`, which the errata
already makes the two owners of it. No other file changes; a sixth format's
`system_text` then follows the same rule without knowing which of the two
appliers it will reach.

The text itself is not a keyed value — the key carries `inject.format`, the
entry's name — so the re-keying comes from the `VERSION` rule alone:
`agent/injected_text_formats.py` is in the inject row's `versions` list
(`experimental_settings/schema.py:285`), so this edit bumps its `VERSION` with
`VERSION_HISTORY = {2: {"why": ..., "stale": ("inject",)}}`, because an existing
`p1_e2` or `p2_e2` setting now produces different prompt bytes. No inject run
exists today.
