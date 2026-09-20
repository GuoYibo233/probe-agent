# 08 README credits jobs/launch.py and run.py with record functions neither of them calls

Status: needs-triage
Severity: minor
File: README.md:63, README.md:126
Contract: 0.1 (the five-line annotation format), 1.1 ("Who reads ... `jobs/launch.py` and `run.py` (`done_pairs`, `is_done`, `owner`, `release`)")
Errata: not recorded.

## Finding

Two annotation lines name four functions where the code uses one and two:

```
run.py — ...
  imports: ..., data/trajectory_record.py (done_pairs, is_done, owner, release), ...

data/trajectory_record.py — ...
  used by: agent/run_tasks.py (meta, gen, env, final), agent/step_with_probe.py (spec, resume),
           data/build_training_dataset.py, eval/score_run.py, jobs/launch.py (done_pairs, is_done,
           owner, release), run.py (done_pairs, is_done, owner, release: the completeness check,
           the progress count and the claim release)
```

Every `trajectory_record.` reference in the two programs:

```
jobs/launch.py:1186   trajectory_record.release(...)
run.py:354 (comment), 537, 561, 2011   trajectory_record.done_pairs(...)
run.py:2046   trajectory_record.release(...)
```

`jobs/launch.py` calls `release` only, and neither program calls `is_done` or
`owner` in any spelling. The two functions are reached only from inside
`data/trajectory_record.py`, by `done_pairs`, `read_dir` and `release`.

`run.py selfcheck` check 2 holds the `imports:` and `used by:` lines equal to
the import graph, which both lines satisfy; the parenthetical function lists sit
outside what it checks, which is why this survived.

## Failure scenario

The annotation lines are what an agent reads before touching a file
(`CLAUDE.md`: "read it before touching a file"). An agent asked to change the
claim rule reads that `jobs/launch.py` decides doneness and ownership through
`is_done` and `owner`, goes looking for that code in the launcher, and either
writes a second copy of the rule there or edits the wrong side. The same lines
also state, wrongly, that `run.py`'s completeness check reaches `is_done`
directly, when it reaches it through `done_pairs`, which is the whole point of
`done_pairs` existing (contract 1.1: "it exists so that neither formats a record
path").

## Proposed fix

In `README.md`, write the functions each caller actually uses: `jobs/launch.py
(release)` on line 126, and `run.py (done_pairs, release: the completeness
check, the progress count and the claim release)` on lines 63 and 126. The
contract sentence in 1.1 that both lines copy is `notes/` and stays as it is;
this ticket is the record that the README is the current statement of the tree
(README section 2) and that 1.1's function list is wider than the code.
