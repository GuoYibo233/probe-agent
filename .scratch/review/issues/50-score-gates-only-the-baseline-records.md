# 50 score gates the baseline's records and never the scored run's

Status: needs-triage
Severity: important
File: eval/score_run.py:195
Contract: 2.5 ("`score` builds its own pair list and **both of its record gates are stated over that list**", and "`score` refuses unless the baseline run holds a done record for every (task, seed) of that list"), 2.2 ("the consumers (`build`, `score`) put the lists into their own keys and refuse to run until the records they name are there")
Errata: not recorded

## Finding

`main` builds its pair list from its own frozen projection and resolves the
scored run's directory:

```python
    triples = requested_pairs(env, sec.split, sec.tasks, sec.n_tasks, sec.seeds)
    pairs = [(task_id, seed) for _, task_id, seed in triples]

    scored_dir = schema.run_dir_of(scored, cfg._upstream[scored], debug=cfg._debug)
```
(`eval/score_run.py:175-178`)

The one record gate it holds sits inside the `if cfg.score.baseline is not
None:` block and names the baseline directory alone:

```python
        done = trajectory_record.done_pairs(base_dir, pairs)
        missing = [pair for pair in pairs if pair not in done]
        if missing:
            raise ValueError(
                f"score_run: baseline {base_dir} is missing a done record for pair(s) {missing}")
```
(`eval/score_run.py:195-199`)

`scored_dir` is never tested. It is read through `read_dir`, which skips every
pair whose file is absent or unfinished (`data/trajectory_record.py:254-263`):

```python
    for i, pair in enumerate(pairs, start=1):
        scored_frames.append(trajectory_record.read_dir(scored_dir, [pair]))
```
(`eval/score_run.py:205-206`)

so a missing record leaves no trace in the frame, and `_run_block` computes
`success` over `rec.height` — the records that happened to be there
(`eval/score_run.py:73-84`). With no baseline set, the stage holds no record
gate at all.

`run.py`'s pre-launch test for the same stage asks only for the presence of a
file: `_refuse_missing_upstream` raises when the upstream directory has no
`done.json` (`run.py:1893-1894`) and compares no pair list.

## Failure scenario

A `sample` key excludes `sample.seeds` and `sample.tasks` (2.2), so two
settings that differ only in their seed list share one records directory.
Setting `a` has `seeds: [42]`, setting `b` is identical with `seeds: [42, 43,
44]`.

1. `run.py baseline a` collects one record per task and writes `done.json`
   into the shared sample directory.
2. `run.py retry baseline b score` resolves the score run directory, clears its
   markers and calls `_stage_step` for `score` alone (`run.py:786-788`); the
   `sample` stage is never walked, so nothing compares `b`'s three-seed request
   against what is on disk. `_refuse_missing_upstream` finds the `done.json`
   step 1 wrote and passes.
3. `score_run` builds 3 × n_tasks pairs, `read_dir` returns records for seed 42
   only, and the stage finishes `ok`.

`run_report.json` then carries `n_pairs: 3 * n_tasks`, `n_seeds: 3` and
`run.n_records: n_tasks`, and `run.success` is the success rate of one seed
under a key that states three. The same numbers go into `report.md` and into
the registry row's `metrics.success` (`eval/score_run.py:246-259`), which is
what `jobs/RESULTS.md` prints. Nothing in the run says a record was missing.

The ordinary walk hides this, because it re-tests the pair list at the `sample`
stage and relaunches before it reaches `score` (`run.py:2005-2011`) — which is
why the gate is owed here rather than there: 2.5 puts it in this file precisely
so that the numbers cannot be computed over a collection the setting never
asked for.

## Proposed fix

State the gate that already exists over both directories. Directly after
`scored_dir` is resolved (`eval/score_run.py:178`), call
`trajectory_record.done_pairs(scored_dir, pairs)` and raise, naming the
directory and the missing pairs, when any pair of the list has no done record —
the same three lines `eval/score_run.py:195-199` already spell for the
baseline, and outside the `score.baseline` branch so that a run with no
baseline is gated too. `done_pairs` reads one line per record file, so the
whole check costs one pass over the pair list before any frame is read.
