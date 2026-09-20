# 30 the live cut enumeration is skipped on every chunk that carries no `.!?\n`, so each fire is one sentence late and the last cut of a step is never scored

Status: needs-triage
Severity: important
File: agent/step_with_probe.py:174
Contract: 7.3 (what the loop does per step, item 4: "It re-enumerates the cuts of the thinking **so far** on each chunk with `probe_input.cuts_live(thinking_so_far, cfg.build.min_think)`"), 1.7 (`cuts_live`'s offsets are at `m.start()`)
Errata: not recorded

## Finding

The streaming loop skips the whole cut pass for any chunk whose text carries no
sentence punctuation:

```python
for delta, ids in st:
    raw += delta
    gen_ids += ids
    bounds.append((len(raw), len(gen_ids)))
    out = mod.parse(delta, state)
    if not probing or n_inject >= cfg.inject.max_inject_per_step:
        continue
    if not any(c in delta for c in ".!?\n"):        # line 174
        continue
```

`cuts_live` enumerates `m.start()` of `SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")`
(`data/probe_input.py:18,37-43`). The lookbehind is zero width, so **both
alternatives match whitespace only**: a new cut appears exactly when the chunk
brings a whitespace character, and the `[.!?]` it needs is already in `raw` from
an earlier chunk. The filter tests for the punctuation instead, which is the
character that was already there.

vLLM streams roughly one word piece per chunk with the leading space attached,
so the chunk that ends a sentence is `" first."` (punctuation, no new whitespace,
no new cut) and the chunk that creates the cut is the next one, `" The"`
(whitespace, no punctuation) — which this filter drops. The cut is then
enumerated only when some later chunk happens to carry `.!?\n`.

Measured with the repo's own `cuts_live`
(`external/probe-env/bin/python`, a three-sentence thinking text split into
word-piece chunks):

```
cut 47  first available at chunk 9,  first enumerated at chunk 10 with the filter
cut 109 first available at chunk 16, first enumerated at chunk 23 with the filter
```

Chunk 23 is the last chunk of the text: cut 109 is reached only because the
third sentence also ends in a full stop.

## Failure scenario

An inject run, `arm: probe`, whose step thinking is
`"... I need the phone contacts first. The apis.phone.search_contacts endpoint
takes a query string. Let me call it with the name Alice."` and whose probe
crosses `inject.theta` at the cut after `"... query string."`:

- The cut becomes available at the chunk that brings the space before `"Let"`.
- The filter drops that chunk and every following one until the final `"."`
  arrives, seven chunks later.
- The fire therefore splices at a head seven tokens further on, and those seven
  tokens land in `spec.overflow_ids` and in `gen.discard` — tokens the fire
  existed to save.

And when the step's thinking ends on its last sentence boundary with no further
`.!?\n` chunk before the channel switch (`"... with the name Alice.\n"` is one
chunk carrying the punctuation, `"... with the name Alice"` followed by the
channel tokens is not), that final cut is never scored at all: the step does not
fire although the probe would have crossed theta there. Nothing in the record
says a cut was skipped — `spec.n_checked` counts only the cuts that were
scored — so the loss shows in no number.

## Proposed fix

Root cause: the guard tests the character that must already be present instead
of the character whose arrival creates a cut. In `agent/step_with_probe.py`,
test the condition under which `cuts_live` can return something new — the chunk
carries whitespace:

```python
if not any(c.isspace() for c in delta):
    continue
```

That is the same cheap skip for a chunk that cannot have produced a cut, and it
is true whenever a new `SENT_RE` match exists, because every match of
`(?<=[.!?])\s+|\n` starts at a whitespace character. 7.3's "on each chunk" is
then satisfied for every chunk that can carry a cut; dropping the guard entirely
also satisfies it and costs one regex scan of the thinking per chunk.
