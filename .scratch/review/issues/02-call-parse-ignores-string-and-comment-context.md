# 02 split_args parses calls out of strings and comments, so an example row's tool and args can come from text that never ran

Status: needs-triage
Severity: important
File: data/environments/appworld.py:142-151, data/environments/appworld.py:60-97
Contract: 4.2 (`split_args`: "parse the environment's action text into a call"), 1.2 (`tool`, `call`, `args`)
Errata: not recorded. Errata "2.5 / integrator entry 2" records that the call finder "became quote-aware" and re-measured the parse counts; that change made `_call_close` quote-aware after the match, and did not make the match itself context-aware.

## Finding

`_first_call_named` anchors the parse on a plain regex search:

```python
def _first_call_named(text: str) -> tuple[str, str, list[tuple[str, str]], int, int] | None:
    m = re.search(CALL_START, text)
    if m is None:
        return None
    i = m.end() - 1
    j = _call_close(text, i)
```

`CALL_START = r"apis\.(\w+)\.(\w+)\("` matches anywhere, including inside a
string literal and inside a `#` comment. `_call_close` (line 100) is careful
about exactly those two contexts, but it is only ever entered at the offset the
regex already chose, so the walk starts inside the string or the comment and
happily closes there.

`_split_args_named` (line 60) is not comment-aware at all: its character walk
tracks quotes and brackets and treats `#` as an ordinary character, so a comment
inside a multi-line call is split on the next top-level comma and becomes an
argument value.

Measured with the repo's own code (`external/probe-env/bin/python`, the three
cases below), all three round-trip through `build_call` and therefore pass
`data/build_training_dataset.py`'s round-trip gate:

```
'# apis.api_docs.show_api_doc(app_name="spotify")\nprint(apis.spotify.login(username=e, password=p))'
  -> tool 'apis.api_docs.show_api_doc', args [('app_name', 'spotify')]   (the executed call is apis.spotify.login)

'print("Now calling apis.supervisor.complete_task()")\napis.supervisor.complete_task()'
  -> tool 'apis.supervisor.complete_task'   (right here by luck; the mention wins whenever it differs)

'print(apis.spotify.login(username=email,  # supervisor email\n                         password=pw))'
  -> args [('username', 'email'), ('pos0', '# supervisor email\n                         password=pw')]
  -> call "apis.spotify.login(username=email, '# supervisor email\n                         password=pw')"
```

Over the 200 non-empty actions on disk in
`outputs/**/records/*.jsonl` the regex's tool agrees with a `tokenize`-based
scan on all 200, so no instance is in today's tiny debug corpus.

## Failure scenario

A sample run collects a step whose code block is

```python
# apis.api_docs.show_api_doc(app_name="spotify")
print(apis.spotify.login(username=e, password=p))
```

`build` writes an example row whose `tool` is `apis.api_docs.show_api_doc` and
whose `call` is `apis.api_docs.show_api_doc(app_name=spotify)`, while the world
executed `apis.spotify.login`. The round-trip gate passes, nothing is counted
under `counts.events_skipped_no_call`, and the row enters the training set: the
ctool probe is trained to predict a label the trajectory never called, and every
`eval` number computed against `prediction.tool` (1.3) uses that wrong ground
truth. The third case above poisons `call` and `args` instead of `tool`, so
cgen's and cparam's targets carry a comment as an argument value.

The same parse runs live: `eval/score_run.py` computes `spec_tool_agree` and
`spec_call_agree` by parsing the record's `env.action` with the same function,
so the agreement numbers move with it.

## Proposed fix

One walk decides what is code, and the call finder and the argument splitter
both use it. In `data/environments/appworld.py`:

- `_call_close`'s quote and comment rules become a small scanner that yields the
  offsets that are outside every string and every comment; `_first_call_named`
  takes the first `CALL_START` match whose start is such an offset, and
  `_split_args_named` ends an argument on a top-level comma and reads a key off
  an `=` only at such an offset (a `#` outside a quote runs to the end of the
  line and belongs to no argument).
- The file's `VERSION` bumps with a `VERSION_HISTORY` entry marking `build` and
  `inject` stale, since the parse decides `example.tool`, `example.call` and the
  live speculation.
