# 66 One unparsable line in jobs/runs.jsonl stops every registry call, including the appends

Status: needs-triage
Severity: minor
File: jobs/registry.py:356
Contract: 8.2, 8.6, README section 4 ("never edited by hand")
Errata: not recorded

## Finding

The ledger reader parses every line with no guard:

```python
def _read_rows() -> list[dict]:
    ...
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
```

Every other line-oriented reader in the same file tolerates a line it cannot parse:
`_beats_full` catches `json.JSONDecodeError` and drops the line (:765-768), and so do
`jobs/launch.read_beats_for_run` (:836-839) and `jobs/launch._last_beat_status` (:511-513).

`_read_rows` feeds `fold`, and through it `render`, `open_runs`, `_folded_rows` / `find`,
`ls`, `cards_busy` / `free`, `kill` and `sync` — and `render` runs inside `append_start` and
`append_finish`, so one bad line also stops a launch from recording itself.

Two ways a bad line reaches the file, neither of them a hand edit:

- A merge. `jobs/runs.jsonl` is in git, two sessions append to it on two branches (the
  ticket-run workflow gives each ticket its own worktree and branch), and the repo has no
  `.gitattributes`, so git's text merge conflicts on two appends at the end of the file and
  writes `<<<<<<<`, `=======`, `>>>>>>>` markers into the working tree. `git_state`'s ledger
  exemption (jobs/launch.py:134-139) means the dirty gate does not refuse that tree either.
- A torn write: an `ENOSPC` or a `SIGKILL` between the buffer flushes of a start row longer
  than the 8 KB default buffer leaves a partial line under `_append_row` (:159-163).

## Failure scenario

A merge leaves three marker lines in `jobs/runs.jsonl`. From that moment every command —
`run.py ls`, `run.py free`, `run.py sync`, `run.py table`, and any walk, because
`jobs/launch.launch` calls `registry.open_runs()` inside its lock hold — ends in

```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

with no file name and no line number in the message. The repo's own rule says the ledger is
never edited by hand, so the state reads as unrecoverable until someone reads this source file
to work out which line is at fault.

## Failure scenario (second form)

A `sample` start row carrying eight piece entries with their frozen commands is torn by a full
`/home`. The next `run.py ls` crashes; so does the next launch's `append_start`, so the run
that is about to take eight cards cannot be recorded at all.

## Proposed fix

`_read_rows` keeps reading: a line that does not parse is skipped, with one message on stderr
naming `jobs/runs.jsonl` and the 1-based line number, so `ls`, `sync` and the appends keep
working and the person is told exactly which line to repair. The same rule
`_beats_full` already applies to a heartbeat file, applied to the ledger the appends depend
on.
