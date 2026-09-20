# 17 `run.py`'s `reads:` line and two `read by:` lines leave out four files `selfcheck` opens directly

Status: needs-triage
Severity: minor
File: README.md:65, README.md:78, README.md:169
Contract: 0.1 (the five-line annotation format: "`reads:` what it reads off disk"), README section 2 ("this file lists every one of them with that one line"); check 1's own comment at run.py:881-882 says why the line is required — "`reads:` and `writes:`, which no check reads, are required here because a line nobody requires rots"
Errata: not recorded

## Finding

`selfcheck` opens four things `run.py`'s annotation does not mention, none of them
through `schema`:

- `models/table.yaml` — `run.py:845-847` (`_table_rows`), used by checks 3, 4, 8 and 10
  through `_families` and `_resolve_versions_entry`;
- `constants/path_models.yaml` — `run.py:1517-1518`, check 8's weights-alias test;
- `README.md` — `run.py:1646` (`readme_entries`), the input of checks 1, 2 and 10;
- the source text of every `.py` file under `run.py` and the eight code roots —
  `run.py:238-240` (`_parse`) and `run.py:1303`, which checks 2, 4, 5 and 9 walk.

The `read by:` lines of the two config files name their other readers and stop short of
`run.py`:

```
constants/path_models.yaml — ...
  read by: models/__init__.py, models/agent_models/service.py (the weights path of the row it serves)

models/table.yaml — ...
  read by: models/__init__.py, experimental_settings/schema.py (the result block), models/agent_models/service.py (the serving block), jobs/launch.py (the serving block: host and port)
```

`run.py`'s own `reads:` line credits `schema` with the `VERSION` and `VERSION_HISTORY`
readings and names `constants/path_outputs.yaml` and `constants/path_datasets.yaml`,
so the omissions are not a convention about indirect reads: these four are direct opens
in `run.py`.

## Failure scenario

The README is what the project's rules send an agent to before it touches a file ("read
it before touching a file, and update the file's own line whenever you change it"), and
check 2 proves only the `imports:` and `used by:` lines (run.py:1117-1123), so nothing
catches this. Someone
changing the shape of `models/table.yaml` reads its `read by:` line, updates the four
files it names, and leaves `run.py selfcheck`'s checks 3, 4, 8 and 10 broken — the one
command that would have told them. The same line is what an extension recipe (README
section 3, item 6 and 7: "`models/table.yaml` (one row)") is checked against.

## Proposed fix

Write the four reads onto the three lines: add `models/table.yaml`,
`constants/path_models.yaml`, `README.md` and "the source text of every `.py` file of the
tree (selfcheck's `ast` passes)" to `run.py`'s `reads:` line, and add
`run.py (selfcheck's checks 3, 4, 8 and 10)` to `models/table.yaml`'s `read by:` line and
`run.py (selfcheck's check 8)` to `constants/path_models.yaml`'s. `README.md` has no
entry of its own in section 2, so `run.py`'s line is its only record.

Ticket 24 of this review rewrites the same two `read by:` lines for a different missing
reader (the probe service), so the two edits land on one line each and should be applied
together.
