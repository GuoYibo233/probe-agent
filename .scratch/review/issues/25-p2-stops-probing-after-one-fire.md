# 25 After a p2 injection the step stops scoring, so inject.max_inject_per_step above 1 is reachable for p1 and not for p2

Status: needs-triage
Severity: minor
File: models/agent_models/gptoss.py:113-130
Contract: 7.3 (the per-step list, item 4), 6.2 (`parse`: "returns the channels grown so far under exactly two keys")
Errata: not recorded (errata "7.3 / 6.2: `parse` returns only the two grown channel texts ... -> the build derives `ts = len(raw) - len(thinking_so_far)` while `raw.endswith(thinking_so_far)` holds and stops scoring for the rest of the step when it stops holding" defines the rule; it does not record that one of the two placements always trips it)

## Finding

`parse` splits the raw text on `<|end|>` and keeps a segment only when its
header opens with `<|start|>assistant` or `<|channel|>`:

```python
119                 header, sep, body = seg.partition("<|message|>")
120                 header = header.strip()
121                 if not sep or not (header.startswith("<|start|>assistant") or header.startswith("<|channel|>")):
122                     continue
...
130         return {"reasoning": "\n".join(reasoning), "content": "\n".join(content)}
```

`wrap_prefetch`, twelve lines below in the same file, writes a segment whose
header is neither:

```python
142         return ("<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>"
143                 + body + "<|end|><|start|>assistant")
```

so the prefetch body is dropped, and the model's analysis before and after the
splice come back as two segments joined by `"\n"` at line 130. Measured on
2026-09-21 with `external/probe-env/bin/python` over
`head + wrap_prefetch("PREFETCH BODY", None)`:

```
after the p2 splice: reasoning='I should check the phone app. '
  raw.endswith(reasoning): False
after resuming:      reasoning='I should check the phone app. \nNow I will call the api.'
  raw.endswith(reasoning): False
```

and over the p1 shape (the body spliced into the model's own analysis message)
`raw.endswith(reasoning)` is True both before and after the resume.

`agent/step_with_probe.py` reads exactly that test, once per chunk, and turns a
False into a permanent stop for the step:

```python
177             if not raw.endswith(thinking_so_far):
178                 probing = False
179                 continue
```

after rebuilding `raw = head_txt + note` and `state = {}` at lines 250-254.

## Failure scenario

`experimental_settings/schema.py:139` defaults `max_inject_per_step` to 1, so
today line 172 (`n_inject >= cfg.inject.max_inject_per_step`) stops the step
first and the two placements behave alike. Set the keyed field to 2 and run the
four settled arms:

```
inject:
  format: p1_e1   ->  fires up to twice per step
  format: p2_e1   ->  fires once per step, always
```

because the first p2 fire rewrites `raw` into a form whose thinking is no longer
its suffix, `probing` goes False on the next chunk carrying `.`, `!`, `?` or a
newline, and no further cut of that step is ever scored. There is no error, no
record row and no counter: `n_inject` simply stops at 1, and a p1-against-p2
comparison at `max_inject_per_step: 2` reads as "the p2 placement fires less",
which is an artefact of the parser, not of the arm.

## Proposed fix

The offset rule `ts = len(raw) - len(thinking_so_far)` needs the thinking to be
a suffix of `raw`, and a p2 splice puts a whole prefetch message after the
thinking, so no spelling of `parse` can restore that. Make the limit the loader
states rather than something a family's control tokens decide: in
`experimental_settings/schema.py`, beside the existing inject refusals
(`schema.py:949-950`), refuse a setting whose format's placement is `p2` while
`inject.max_inject_per_step` is above 1, naming both fields —

```
inject.max_inject_per_step: <n> is above 1 while inject.format <fmt> places the
body as a prefetch message (p2); a p2 splice ends the step's scoring, so only
p1 formats can fire more than once per step
```

— and record the placement asymmetry in
`.scratch/from-zero/contract-errata.md` under 7.3, so the per-step list of item
4 reads the same as the code. Until the refusal lands, `p2_*` settings must
leave `max_inject_per_step` at its default.
