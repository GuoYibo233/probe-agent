# T05: Three eval scripts wired to heartbeats

Ticket: `.scratch/gpu-monitor-launch/issues/05-eval-heartbeat.md`
Implementation plan anchor: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 5 (lines 495-515)
Branch: `ticket/20260808-par/T05`; worktree: `/home/y-guo/reproduce/new1-wt/20260808-par-T05` (already removed, branch kept)
base: `5be5d0827fe959cc1c016c8f99221c4d6a4218c8`
head: `b8cda45`

## What was done

The ticket's four requirements: wire three files to heartbeats (tool eval, mbert call eval, causal call eval),
unit=item, emit done=0 before the batch loop, follow the existing progress print to emit heartbeats (if there is none, add one every 50 batches),
emit status=done after the report is written, and scripts with multiple loop segments keep only one progress axis. Going through each in order:

**`pipeline/eval/eval_tool.py`** (tool eval; the anchor given by the plan is the `print(f"scored {i}/{len(rows)}")` at
`:69`). This file has two kinds of loop: `score()`/
`score_causal()` (running the model over each split and scoring it, printing progress per batch, this is the segment the plan's anchor
points to) and `replay`/`bootstrap`/`economics` (θ sweep and confidence intervals, pure CPU
dict operations, no progress print). Per the plan's original wording, "eval_tool has a score segment and a replay segment,
take the longer one as the progress denominator, don't emit heartbeats for other segments," heartbeats were wired only into `score()` (the mbert classification-head path)
and `score_causal()` (the causal-probe path; the two are mutually exclusive via `--head`, only one runs per invocation);
the replay/bootstrap segment gets no heartbeats at all.

- `score()`: at function entry, `heartbeat.emit(0, len(rows), "item")`; right after the existing
  `print(f"scored {i}/{len(rows)}")` (once every 50 batches), added `heartbeat.emit(i, len(rows), "item")`.
- `score_causal()`: at entry, `heartbeat.emit(0, len(events), "item")` (denominator is the
  events count, matching the denominator the existing print uses, not the rows count); right after the existing print every 25 batches,
  added `heartbeat.emit(s, len(events), "item")`.
- In `main()`, the `test` split's row count `rows_t` is always retrievable after `REPLAY_REPORT.md` has been written
  (because `test` is the last of the split_names under every convention, and the non-early-return branch always runs it), so
  `heartbeat.emit(len(rows_t), len(rows_t), "item", status="done")` was added right after the report file is written.
  The `--adopt-logits-fingerprint` early-`return` utility branch (which only fills in a logits
  fingerprint file, does not run eval) got no heartbeat. It does not enter the score segment, and is not the long-running eval path
  this ticket is targeting.

**`pipeline/eval/eval_mbert_call.py`** (mbert call eval; anchor `:127`'s
`print(f"extracted {i}/...")`, in `run_extractor()`). This file likewise has two kinds of loop:
`run_extractor()` (always called by the legacy-convention path via `extract_points()`, and called again in the
`--self-fire` branch) and `score_fire()` (only when `--self-fire`, running a fire-verdict scoring pass over val/test each once, its own
segment). Heartbeats were only wired into `run_extractor()`, not `score_fire()`, to avoid the same script producing two axes.

- `run_extractor()`: at entry, `heartbeat.emit(0, len(items), "item")`; right after the existing
  print every 20 batches, added `heartbeat.emit(i, len(items), "item")`.
- In `main()`, the main extraction loop's counter `cnts` (`per_ev, cnts = extract_points(...)`)
  is still in scope at the end of the function, using `cnts["n_par"]` as the done/total for status=done:
  after `EXTRACT_REPORT.md` is written, `heartbeat.emit(cnts["n_par"], cnts["n_par"],
  "item", status="done")`. `cnts["n_par"]` can be 0 under `--readonly-env` when no trigger events fire;
  `heartbeat.emit(0, 0, "item", status="done")` itself does not error (verdicts.py's
  done verdict first looks at `status=="done"`, and `total=0` does not bypass it).

**`pipeline/eval/eval_causal_call.py`** (causal call eval; the anchor the plan gives is the batch loop at
`:207`, noted "no existing progress print". But the current code's loop actually already
has a line `print(f"generated {min(i+bs,len(prompts))}/{len(prompts)}",
flush=True)`, printed every batch, not "every 50 batches." The plan doc was probably written before
this print line was added; this ticket followed the anchor as it stands, without inventing its own cadence). Same two kinds of loop:
`generate()` (always called under the legacy convention, called again in the `--self-fire` branch) and
`score_fire()` (only under `--self-fire`). Only `generate()` was wired.

- `generate()`: at entry, `heartbeat.emit(0, len(prompts), "item")`; right after the
  existing per-batch print, added `heartbeat.emit(min(i+bs, len(prompts)), len(prompts),
  "item")` (reusing the done value the print already computed, no separate counter started).
- In `main()`, `n = len(per_ev)` (the event count after scoring, which under the legacy path is
  this eval run's own size) is still in scope at the end of the function; after
  `CALLGEN_REPORT.md` is written, `heartbeat.emit(n, n, "item", status="done")`.

All three files only had heartbeat-related lines added (imports + heartbeat calls), with no change to any
existing eval convention, scoring logic, field names, or output format.

## How it was verified

**Syntax check** (ticket acceptance item 1):

```
$ for f in pipeline/eval/eval_tool.py pipeline/eval/eval_mbert_call.py pipeline/eval/eval_causal_call.py; do python3 -c "import ast; ast.parse(open('$f').read())" && echo "$f ok"; done
pipeline/eval/eval_tool.py ok
pipeline/eval/eval_mbert_call.py ok
pipeline/eval/eval_causal_call.py ok
```

**Import path of the heartbeat module and the emit/parse round trip** (this worktree does not have the
mbert-env/cprobe-env venvs. `.gitignore`'s `*-env/` excludes them, and git worktree only carries git-tracked files,
so the three eval scripts cannot actually be run in full; verified the path resolution and heartbeat format with a standalone script that
copies the `sys.path.insert(..., parents[2] / "ops")` pattern used in the scripts):

```
$ python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('pipeline/eval/eval_tool.py').resolve().parents[2] / 'ops'))
import heartbeat
import io
buf = io.StringIO()
heartbeat.emit(0, 10, 'item', stream=buf)
heartbeat.emit(5, 10, 'item', stream=buf)
heartbeat.emit(10, 10, 'item', status='done', stream=buf)
print(buf.getvalue())
print('parse:', [heartbeat.parse(l) for l in buf.getvalue().splitlines()])
"
@hb {"done": 0, "total": 10, "unit": "item", "ts": 1786139797.2}
@hb {"done": 5, "total": 10, "unit": "item", "ts": 1786139797.2}
@hb {"done": 10, "total": 10, "unit": "item", "ts": 1786139797.2, "status": "done"}

parse: [{'done': 0, 'total': 10, 'unit': 'item', 'ts': 1786139797.2}, {'done': 5, 'total': 10, 'unit': 'item', 'ts': 1786139797.2}, {'done': 10, 'total': 10, 'unit': 'item', 'ts': 1786139797.2, 'status': 'done'}]
```

`parents[2]` for `pipeline/eval/*.py` lands on the repo root, and `ops/heartbeat.py`
can be imported normally under this repo-root layout. All three files use the same path expression.

**`python3 run.py selfcheck`**: in this worktree it reports 16 "missing interpreter/program" items
(`mbert-env`, `cprobe-env`, `envs/*/venv`, etc.); in the untouched main worktree, `selfcheck` gives
"62 tasks / 4 recipes, all present." These venv directories are excluded by `.gitignore`'s `*-env/` pattern,
and `git worktree add` only checks out git-tracked files, so the new worktree naturally lacks these venvs. This is a gap in the
worktree's own environment, not a registry problem introduced by this change. This ticket did not change `run.py` or any
registry entry; the three eval scripts were already registered in `run.py`, and this change only adds heartbeat calls inside the scripts.

**What was not run**: actually executing the three scripts themselves (would need a GPU, mbert-env/cprobe-env, and
an already-trained run directory). The implementer's protocol forbids launching GPU processes, and this ticket itself does not
require the eval to actually run. The acceptance items are only the syntax check, "one progress axis," and commit.

## Commit list

- `b8cda45`: `T05: eval: three eval scripts wired to heartbeats (unit=item)`
  (`pipeline/eval/eval_tool.py`, `eval_mbert_call.py`, `eval_causal_call.py`,
  +20 lines total, nothing deleted)

## Self-check findings and open questions

- **"The longer segment" is a judgment call, not a measurement.** The ticket's original wording, "for scripts with multiple loop
  segments, the longest one is the progress denominator," names eval_tool's score segment vs. replay segment, and gives its
  anchor pointing precisely at the score segment's print. This principle was extended by analogy to the other two files
  (run_extractor vs. score_fire; generate vs. score_fire), on the grounds that: the
  legacy path always runs run_extractor()/generate(), `--self-fire` is an optional path off by default, and the
  ticket's given anchor itself only points at that legacy path's print. But no actual dataset was used to compute the item counts of both segments.
  if some run's `--self-fire` val+test fire-scoring batch count exceeds the
  legacy extraction batch count, this "longest" judgment could reverse for that run. This is judged acceptable, because
  the acceptance item is "only one progress axis," not "the numerically longest segment," and score_fire not emitting any
  heartbeats at all already guarantees it will never create a second axis.
- **Calling the same heartbeat function multiple times makes done jump backward across calls.** `eval_tool.py`'s
  `score()`/`score_causal()` are each called once per split (val/test, or legacy calA/calB/test),
  and each call's internal `done` starts counting from 0, with `total` set to that call's own
  `len(rows)` (or `len(events)`), not one global accumulating count across the whole script. Across
  splits, `done` will drop from the previous split's high value back to 0. verdicts.py's
  `rates()` has protection for this: when `last["done"] >= first_beat["done"]`
  does not hold, the rate for that window is simply recorded as None, with no negative rate computed or error raised; `judge()`'s
  done verdict looks at either `status=="done"` or `done>=total`. Since
  `i` in `range(0, len(rows), bs)` is always strictly less than `len(rows)`, heartbeats within the batch loop can
  never produce `done>=total`, and cannot be mistakenly verdicted done early. This was confirmed by reading
  `ops/verdicts.py`'s source, not guessed. `eval_mbert_call.py`'s
  `run_extractor()` (called a second time inside `extract_points()` when `--self-fire` is on) and
  `eval_causal_call.py`'s `generate()` (likewise) are in the same situation, with the same conclusion.
- **status=done's done/total is "the count computed on the last pass this run made," not
  "the sum of everything the script ever processed."** The three files use `len(rows_t)`,
  `cnts["n_par"]`, and `n = len(per_ev)` respectively, all sizes from the legacy-convention main path, not including
  the extra amount handled by the `--self-fire` branch. This is a deliberate simplification; the ticket does not require heartbeat's
  `total` to exactly equal the total amount of data the script ever processed, only that it
  emit status=done at the point of normal completion.
