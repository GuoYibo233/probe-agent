# 07 an argument value is stripped of every quote character at its ends, not of one layer

Status: needs-triage
Severity: minor
File: data/environments/appworld.py:91-96
Contract: 4.2 (`build_call` is the inverse of `split_args`: "`split_args` splits on top-level commas and strips one layer of quotes on the way back")
Errata: "4.2 `build_call`" replaces `repr()` with bare quoting and measures the round trip; it does not touch how many quote layers the reader strips.

## Finding

`_split_args_named` ends each value with `str.strip("\"'")`, which removes every
leading and trailing character that is a single or double quote:

```python
        m = re.match(r"(\w+)\s*=\s*(.+)", v, re.S)
        if m:
            out.append((m.group(1), m.group(2).strip().strip("\"'")))
        else:
            out.append((f"pos{pos}", v.strip().strip("\"'")))
```

Contract 4.2 pins one layer, which is what makes `build_call` an inverse. Run
against the repo's own code:

```
'print(apis.x.y(k="\'quoted\'"))'  -> args [('k', 'quoted')]
                                   -> build_call 'apis.x.y(k=quoted)'
                                   -> round-trip gate: passes
```

The value the world executed was the string `'quoted'` (six characters); the
example row records the bare name `quoted`. The round-trip gate of
`data/build_training_dataset.py:188-192` compares `split_args(build_call(tool,
args))` with `(tool, args)` and cannot see the loss, because both sides went
through the same stripping.

Over the 200 non-empty actions on disk under
`outputs/**/records/*.jsonl`, no value has a quote at either end after the
strip, so no instance is in today's corpus.

## Failure scenario

A trajectory step calls an API with a value that is itself a quoted string — an
AppWorld search term written as `query="'hey jude'"`, or a JSON-ish payload
wrapped twice. `build` writes `example.call` as `apis.spotify.search(query=hey
jude)` with the quotes gone, the gate passes, and:

- cgen is trained to generate a call whose argument is a bare token where the
  ground truth was a quoted string, and `eval`'s `full_call_ok` scores against
  that same wrong target;
- live, `_requote` re-reads the generated `hey jude`, fails `ast.literal_eval`,
  fails the identifier test, and quotes it as `'hey jude'`, so the speculated
  call differs from the call the trajectory made — a wrong `exec_out` with no
  error anywhere.

## Proposed fix

Strip one matched pair, in `data/environments/appworld.py`: a value whose first
and last characters are the same quote character and whose length is at least
two loses exactly those two characters, and a value that is not so wrapped is
left as it is. That is the affirmative form of contract 4.2's "strips one layer
of quotes on the way back", and it keeps `build_call`'s existing rules (which
already decide bare-or-quoted through `_bare_safe`) an exact inverse of it. The
file's `VERSION` bumps with a `VERSION_HISTORY` entry marking `build` and
`inject` stale, since it changes `example.args` and `example.call`.
