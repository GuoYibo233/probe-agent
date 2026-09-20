# 55 The README `reads:` lines of the two eval programs miss files they open

Status: needs-triage
Severity: minor
File: README.md:285
Contract: 0.1 (the five-line annotation format), 0.2 (`eval/utils/probe_eval.py`'s and `eval/score_run.py`'s annotation lines)
Errata: "Part 0.2 (`eval/utils/probe_eval.py` reads) / 2.5" is the ruling that added the middle of the three `meta.json` reads below; "Part 0.2 (`data/build_training_dataset.py`'s annotation lines)" is the precedent for naming `constants/path_datasets.yaml` on a `reads:` line

## Finding

`README.md:285` says probe_eval reads two `meta.json` files:

```
  reads:   prediction (parquet), its own and the referenced eval run's train meta.json (stage_extra.labels, upstream["build"]), probe report (json + parquet)
```

`run` opens three:

- `train_dir / "meta.json"`, for `stage_extra["labels"]`
  (`eval/utils/probe_eval.py:628-629`);
- `ref_eval_dir / "meta.json"`, for `upstream["train"]` — the referenced eval
  run's **own** meta, which the line does not mention
  (`eval/utils/probe_eval.py:648-649`);
- `ref_train_dir / "meta.json"`, for `upstream["build"]`
  (`eval/utils/probe_eval.py:654`).

The middle read is the one the errata ruled in: "the build reads the referenced
eval run's own `meta.json` `upstream["train"]` first, then that train run's
`meta.json` `upstream["build"]`". The README line records the ruling's second
half and not its first, and the code's own comment at
`eval/utils/probe_eval.py:650-652` explains why that read exists.

Neither eval file's `reads:` line names `constants/path_datasets.yaml`, which
`open_env` reads on every call before it imports anything
(`data/environments/__init__.py:77-82`): `eval/utils/probe_eval.py:477` calls
it for a generator report and `eval/score_run.py:171` calls it for every score
run. The same section's `data/build_training_dataset.py` line names that file
explicitly (`README.md:155`), and `eval/score_run.py`'s own line already names
a transitive read in the same shape — "the environment's split task-id files
(through `data/environments.requested_pairs`)" (`README.md:292`) — so the two
lines are inconsistent with the convention the section around them uses.

## Failure scenario

`run.py selfcheck` holds only the `imports:` and `used by:` lines against the
real import graph (`README.md:47-49`), so a wrong `reads:` line is never caught
by a program, and CLAUDE.md sends an agent to this file before it touches any
other ("read it before touching a file").

An agent asked to change how a referenced eval run is located — the errata
records that `schema.referenced_run_dir` already had to be introduced once for
exactly that reason — greps section 2 for the files that read a referenced
eval's `meta.json`, finds probe_eval credited only with the referenced
**train** run's meta, and leaves `eval/utils/probe_eval.py:648` out of its edit
list. The same holds for an edit to `constants/path_datasets.yaml`'s block
layout: section 2's `read by:` line for that file (`README.md:72`) lists five
readers and neither eval program, while both open it on every run.

## Proposed fix

Rewrite the two lines to name what the code opens.
`README.md:285` names three `meta.json` reads: its own train run's
(`stage_extra.labels`), the referenced eval run's own (`upstream["train"]`) and
that run's train run's (`upstream["build"]`), plus
`constants/path_datasets.yaml` (through `open_env`, the generator report only).
`README.md:292` gains `constants/path_datasets.yaml` (through `open_env` and
`requested_pairs`). In the same edit, add both eval programs to
`constants/path_datasets.yaml`'s own `read by:` line at `README.md:72`, which
lists five readers today and neither of them, so the two directions of that
fact agree.
