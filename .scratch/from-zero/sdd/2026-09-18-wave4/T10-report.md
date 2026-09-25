# T10 report — the generator metrics, the run scorer and the matrix table

Branch `ticket/2026-09-18-wave4/T10`, base `46f5375`, head `5b0dc71`. Worked in
worktree `/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T10` (removed at the
end; branch kept).

The ticket text I worked from already carries the wave-4 precheck's five
corrections (T10-1 through T10-6): `split_args`'s plain 3-tuple unpacked
without attribute access, A6a's single-expression filter, A8's baseline built
in the non-debug tree with `temperature` restored before the second refusal,
and `method_table`'s flat-dotted `diff` with `backbone` read off the eval
row's train row. I followed the corrected text throughout; no further
disagreement between the ticket and the contracts came up.

## What was done, against each requirement

**`eval/methods/cgen.py`** (contracts 1.4, 2.6). `VERSION = 1`,
`PROBE_KIND = "generator"`. `match(pred, target, env)` unpacks
`env.split_args`'s plain 3-tuple, raises naming the target when the target
does not parse, returns all three `False` when the prediction does not parse,
and otherwise runs the union-by-key comparison of contracts 1.4/2.6 with the
`noparam` short-circuit dropped (stated in the module docstring, second
sentence). `report(pred_df, cfg, ref, labels)` checks `ref` is a
`(fields, fires)` tuple and `labels` is `None`, opens `env = open_env(cfg.data.env)`,
filters `pred_df` to `split == "test"`, and per risk in `cfg.eval.risk` reads
`theta_used` from `ref_fields["chosen"]`; when null it writes the all-null
`exact` block and does not refuse; otherwise it joins `test` to the
referenced classifier's fired `example_id`s at that risk (single filter
expression over `risk` and `split`, no chained `.filter()` calls), calls
`match` per joined row, and reports the three rates rounded to 4 with `n` and
a bootstrap CI grouped by `task_id`. `main` is the one-line
`probe_eval.run(run_dir, sys.modules[__name__])`, plus a `--run-dir`
`argparse` block.

**`eval/methods/cparam.py`** (contracts 1.4, 2.6) — same shape,
duplicated on purpose (the ticket says the comparison body is written twice;
`cgen.py` and `cparam.py` import neither of each other). `match` is the same
whole-call comparison; its callers (this file's `report`,
`train/methods/cparam.py`'s `validate`) are the ones that prepend
`tool + "("` before calling it. `report`'s step 4 differs from `cgen`'s: it
joins the referenced fires' `example_id` and `label_pred` (aliased to
`fired_label` before the join, see "self-review" below), computes
`tool_ok = fired_label == prediction.tool`,
`params_all_ok = match(tool + "(" + text_pred, tool + "(" + target, env)["params_all_ok"]`,
and `full_call_ok = tool_ok and params_all_ok`.

**`eval/score_run.py`** (contracts 2.5, 2.3, 1.1). `VERSION = 1`,
`main(run_dir)` does, in order: `cfg = schema.load_frozen(run_dir)`,
`env = open_env(cfg.data.env)`; `scored = "inject" if "inject" in cfg._upstream else "sample"`;
build `pairs` from `requested_pairs(env, sec.split, sec.tasks, sec.n_tasks, sec.seeds)`
where `sec` is `cfg.inject` or `cfg.sample`; resolve `scored_dir` with
`cfg._debug` and, when `cfg.score.baseline` is set, `base_dir` with
`debug=False`; the same-setup gate (`schema.load_frozen` on both directories,
compare `data`, `models.agent`, `generation` field by field, refuse naming
both directories and the first differing field); the baseline-completeness
gate (`trajectory_record.done_pairs(base_dir, pairs)` must cover every pair,
refuse naming the missing ones); a heartbeat with unit `"task"`, one beat per
pair; `trajectory_record.read_dir` over both directories; the run/baseline/
paired/spec/resume/by_seed blocks of contracts 1.1's pinned field list, every
rate rounded to 4 and null on a zero denominator; `run_report.json` and
`report.md` (summary line plus one line per task); `registry.write_done` with
the `done.json` metrics list the errata pins (`success`, `base_success`,
`delta_success`, `tokens_out`, `spec_exec_ok`, `spec_tool_agree`,
`spec_call_agree`, `n_records`, null entries omitted) and no `consumed.json`.

**`eval/method_table.py`** (contracts 8.6). No `VERSION`, no `__main__`.
`table(workflow=None, out=None)`: `rows = registry.ls(workflow, debug=False)`,
filtered to `stage == "eval"` for the table rows while the whole result is
kept for the train-row lookup; grouped by `parent` or `setting`; per row,
`method = diff.get("probe.method", <schema default>)` off the flat dotted
`diff`; `backbone` read off the eval row's `meta.json`
`upstream["train"]` naming a `stage == "train"` row in the same `ls` result,
`diff.get("models.probe", <schema default>)`, or `"?"` when the `meta.json`
or the named train row is absent; one output row per `(backbone, method, risk)`
found in the group's ready reports, with the four `frozen` columns filled from
a classifier report and the three `exact` columns from a generator report
(the other side `-`); `mean ± spread` (sample standard deviation) per cell,
the bare value for a one-run group, `-` for no value at all; `runs` the group
size; `status` `"OK"` or `"PENDING n/m"`.

**`README.md`** — added a `## Ticket 10` section with this ticket's four
files' lines, copied from contracts 0.2 (the `methods/` sub-lines plus
`score_run.py` and `method_table.py`), and a short paragraph naming the two
decisions the ticket left to the implementer (the `backbone` source and the
uniform mean/spread/bare-value/`-` cell rule).

## How it was verified

All commands run from the worktree root with
`PY=/home/y-guo/reproduce/new1/external/probe-env/bin/python` (the `$PY` the
ticket names) unless stated otherwise; the appworld and vllm interpreters
were used for A1 as the ticket asks.

**A1 — import test, six files, three venvs.**
```
for P in .../probe-env/bin/python .../appworld/venv/bin/python .../vllm-env/bin/python; do
  for M in eval.utils.probe_eval eval.methods.ctool eval.methods.cgen eval.methods.cparam eval.score_run eval.method_table; do ...
```
Output: `import test done`, no `FAIL` line, exit 0. Matches expectation.

**A2 — no torch, no GPU.**
```
grep -rn "import torch\|from torch\|cuda\|transformers" eval/ ; echo "exit=$?"
```
Output: no matches, `exit=1`. Matches expectation.

**A3 — the literal lines.**
```
"$PY" - <<'PY'  # the ticket's literal-VERSION / literal-PROBE_KIND script
PY
```
Output: `literals ok`. Matches expectation.

**A6a — the reference classifier eval fixture.** Output:
`reference fires: 40 ['test', 'val']`, then `A6a ok`, exit 0. Matches
expectation exactly (once the single-expression filter from the precheck is
used, per the ticket text as given).

**A6 — cgen and cparam against that report.** First run:
`cgen exact@0.05 = {'tool_ok': 1.0, 'params_all_ok': 0.8, 'full_call_ok': 0.8, 'n': 10, ...}`,
`cgen A6 ok`. `cparam` failed on the first attempt
(`AssertionError: 0.0` on `tool_ok`) — see "self-review" below for the cause
and the fix. After the fix, rerun (fixtures cleaned and rebuilt first):
`cparam exact@0.05 = {'tool_ok': 1.0, 'params_all_ok': 0.8, 'full_call_ok': 0.8, 'n': 10, ...}`,
`cparam A6 ok`. Both match the ticket's expected arithmetic
(`n=10`, `tool_ok=1.0`, `params_all_ok=0.8`, `full_call_ok=0.8`).

**A7 — `match` from the train side.** Output: `A7 ok`. Matches expectation,
including `cgen.match(good, none0, env)["params_all_ok"] is False` (the
dropped `noparam` short-circuit).

**A8 — `score_run` end to end, plus the two refusals.**
- Main run: `A8 ok` — `score keys` carried every pinned top-level field;
  `rep["run"]["success"] == 1.0`, `rep["baseline"]["success"] == 0.0`,
  `rep["paired"]["n"] == 2`, `rep["paired"]["delta_success"] == 1.0`,
  `rep["spec"]["n"] == 0`, `rep["by_seed"]["42"]["n_records"] == 2`,
  `done.json` had `stage == "score"` and `report == "report.md"`, and no
  `consumed.json` was written.
- Same-setup gate: after setting the baseline's `generation.temperature` to
  `0.7`, the rerun raised
  `ValueError: score_run: same-setup gate failed between .../debug/sample/1111aaaa1111 and .../sample/2222bbbb2222: generation.temperature differs`,
  `exit=1`. Names both directories and the first differing field, as required.
- Baseline-completeness gate: after restoring `temperature: 1.0` and deleting
  one baseline record file (`82e2fac_1__s42.jsonl`), the rerun raised
  `ValueError: score_run: baseline .../sample/2222bbbb2222 is missing a done record for pair(s) [('82e2fac_1', 42)]`,
  `exit=1`. Names the missing pair, as required.
- I reran the whole A8 sequence a second time after a small import cleanup
  (folding a `from data.trajectory_record import done_pairs` into the module
  import already in scope); the rerun reproduced the same `A8 ok` result.

**Clean-up.** After A6a/A6, deleted the six fixture directories and confirm
their keys: `4444dddd4444`, `5555eeee5555` (non-debug), `dddddddddddd`,
`eeeeeeeeeeee`, `6666ffff6666`, `7777aaaa7777` (debug). After A8 (both runs),
deleted the three fixture directories: `1111aaaa1111` (debug sample),
`3333cccc3333` (debug score), `2222bbbb2222` (non-debug sample, the
baseline). A final recursive `find` over the outputs root for all nine keys
returned nothing.

**A9 — `method_table`.**
```
"$PY" - <<'PY' ... eval.method_table.table() ...
```
Output: a markdown table with header line starting `#` and the row
`| backbone | method | risk | n | ... |` present, empty body (the registry
holds no eval row in this worktree), `exit=0`. `jobs/runs.jsonl` in the
worktree is 0 bytes, so `registry.ls`'s `all_entries` is empty and it returns
before calling `live_sessions()` — no `ssh` was issued, confirmed by the
command completing instantly with no ssh-related output.

**`README.md`.** No `run.py` on this branch yet, so `run.py selfcheck` was not
run, per the ticket's "selfcheck lines that apply later" note.

## Commits

- `5b0dc71` — `T10: eval/methods/cgen.py, eval/methods/cparam.py, eval/score_run.py, eval/method_table.py`
  (all four ticket files plus the README section, one commit).

## Self-review findings and open questions

1. **Bug I found and fixed before committing**: `cparam.report`'s first draft
   joined `fires_risk.select(["example_id", "label_pred"])` onto `test`
   directly. `test` (the predictions frame) already carries its own
   `label_pred` column (null for every generator row, per `data/probe_output.py`'s
   schema), so the join collided the two `label_pred` columns and Polars kept
   the left (null) one under the plain name — every `tool_ok` came out
   `False`. Fixed by aliasing the referenced classifier's column to
   `fired_label` before the join. Caught by A6, not by A7 (A7 never builds
   a frame with both columns present).
2. **`method_table`'s cell-formatting rule beyond what the ticket pins.** The
   ticket fixes the shape (`mean ± spread`, bare value for one run) but not
   whether the `n` column is formatted as an integer or with the same 4
   decimals as the rate columns. I formatted `n` with `_fmt_n` (integer for
   one run, `mean ± spread` at 1 decimal for a sweep group) rather than
   reusing the 4-decimal rate formatter, since `n` is always a count. Noted
   in the README's ticket-10 paragraph as a decision, not asserted by any
   acceptance command (A9 runs over an empty registry).
3. **`eval/score_run.py`'s `spec` block's `tool_agree`/`call_agree` fallback
   when either side fails to parse.** The ticket describes the happy path
   (parse both `spec.gen_call` and `env.action`, compare); it does not say
   what `tool_agree`/`call_agree` should be when one side is null or fails
   `env.split_args`. I default both to `False` in that case (`recalled` is
   computed separately, from `gen_call`'s own parse and a plain substring
   test on the raw `env.action` text, independent of whether `env.action`
   itself parses). None of the acceptance fixtures write `spec` rows
   (`A8`'s fixture is a `sample` run, which never writes `spec`), so this
   path is untested by acceptance and is a judgment call, not a verified
   number.
4. **`_by_seed_block`'s spread with exactly one seed.** The ticket asks for
   "the mean and the sample standard deviation across seeds"; a sample
   standard deviation is undefined for one seed. I wrote `0.0` for that case
   (A8's own fixture has exactly one seed, `42`, and only asserts
   `rep["by_seed"]["42"]["n_records"] == 2`, not the `mean`/`spread` blocks).
5. Everything else in the four files follows the ticket's pseudocode and the
   corrected acceptance scripts literally; I found no other place where the
   ticket, the contracts and the merged code disagreed.

No open questions beyond the two GPU/main-session checks the ticket itself
marks as not the implementer's (`M-E2`, `M-E3`), which I did not attempt.

## Fix round 1

Worked in worktree `/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T10-fix1`
(removed at the end; branch kept), checking out the existing branch
`ticket/2026-09-18-wave4/T10` at `5b0dc71`. Two findings, both in
`eval/score_run.py`.

**F1 — `_by_seed_block` crashes with `StopIteration` on zero records.**
`metric_names` was read from `next(iter(per_seed.values()))`; when the scored
run has zero records, `seeds` is `[]`, `per_seed` is `{}`, and `next` on an
empty iterator raises. Root-cause fix: `_run_block(rec)` already returns a
full all-null dict with the exact metric-key set for a zero-row frame (it has
its own `n == 0` guard), so `metric_names` is now read from `_run_block(rec)`
directly instead of from an arbitrary element of `per_seed`. This makes
`_by_seed_block` consistent with `_run_block`, `_paired_block`, `_spec_block`
and `_resume_block`, which all already return an all-null block on an empty
input rather than crashing.

```python
-    metric_names = [k for k in next(iter(per_seed.values())) if k not in ("n_records", "n_abort")]
+    metric_names = [k for k in _run_block(rec) if k not in ("n_records", "n_abort")]
```

**F2 — baseline completeness gate recomputes `done_pairs` once per pair.**
`missing = [pair for pair in pairs if pair not in trajectory_record.done_pairs(base_dir, pairs)]`
called `done_pairs` (which itself scans the whole `pairs` list) once per
element of the comprehension, an O(n^2) file-system scan. Root-cause fix:
call `done_pairs` once and filter the pair list against the returned set,
matching the sibling stage file's already-correct pattern
(`data/build_training_dataset.py`'s `done = trajectory_record.done_pairs(sample_dir, pairs); missing = [pair for pair in pairs if pair not in done]`).

```python
-        missing = [pair for pair in pairs if pair not in trajectory_record.done_pairs(base_dir, pairs)]
+        done = trajectory_record.done_pairs(base_dir, pairs)
+        missing = [pair for pair in pairs if pair not in done]
```

### How it was verified

`PY=/home/y-guo/reproduce/new1/external/probe-env/bin/python` for all
commands below, run from the worktree root.

**Direct regression test for F1**, on a zero-row `_finals` frame built with
the same schema `_finals` produces:
```
block = _by_seed_block(rec)   # rec.height == 0
```
Output: `{'mean': {'success': None, 'success_no_abort': None, 'steps_mean': None,
'completed': None, 'tokens_in': None, 'tokens_out': None, 'n_inject_per_task':
None, 'discard_chars': None, 'discard_tokens': None, 'wall_s_mean': None},
'spread': {...same, all None...}}`, no exception, exit 0. Confirmed against
the pre-fix code (`git stash`, rerun the same script) that it raises
`StopIteration` there — the fix is exercised by a real before/after
comparison, not just presumed.

**A8 — `score_run` end to end, plus both refusals (exercises F2's code
path).** Rebuilt the same fixture as the original A8 run (`1111aaaa1111`
debug sample, `2222bbbb2222` non-debug baseline sample, `3333cccc3333` debug
score). Main run: `A8 ok` with the same assertions as the original report
(`rep["run"]["success"] == 1.0`, `rep["baseline"]["success"] == 0.0`,
`rep["paired"]["n"] == 2`, `rep["paired"]["delta_success"] == 1.0`,
`rep["spec"]["n"] == 0`, `rep["by_seed"]["42"]["n_records"] == 2`, `done.json`
`stage == "score"` and `report == "report.md"`, no `consumed.json`). Then the
same-setup gate refusal (baseline `temperature` set to `0.7`): raised
`ValueError: score_run: same-setup gate failed between .../debug/sample/1111aaaa1111
and .../sample/2222bbbb2222: generation.temperature differs`, `exit=1`. Then,
after restoring `temperature: 1.0` and deleting the baseline record
`82e2fac_1__s42.jsonl`, the completeness gate — now running through the
single-call `done_pairs` — raised
`ValueError: score_run: baseline .../sample/2222bbbb2222 is missing a done
record for pair(s) [('82e2fac_1', 42)]`, `exit=1`. Both match the ticket's
expected messages; the completeness-gate refusal confirms F2's fix still
correctly detects a missing pair.

**A1 — import test, six files, three venvs.** Rerun in full: `import test
done`, no `FAIL` line, exit 0.

**A2 — no torch, no GPU.** Rerun: no matches, `exit=1`.

**A9 — `method_table`.** Rerun (unaffected by this round's changes, checked
for regression): markdown table with header `# eval matrix: backbone x method
x risk` and the `| backbone | method | risk |` row present, empty body
(empty registry in this worktree), `exit=0`.

**Clean-up.** Deleted the three A8 fixture directories after use and
confirmed removal: `1111aaaa1111` (debug sample), `3333cccc3333` (debug
score), `2222bbbb2222` (non-debug baseline sample). A recursive `find` over
the outputs root for all three keys returned nothing afterward.

### Commits

- `32e8c48` — `T10: fix round 1 — score_run._by_seed_block StopIteration on
  zero records, done_pairs O(n^2) rescan` (both findings, one commit).

### Self-review and open questions

Both fixes are single-line-scope root-cause corrections in the exact
functions the findings name; no other code in `eval/score_run.py` was
touched, and no refactor beyond the two findings was done. F1's fix reuses
`_run_block`'s existing null-shape guarantee rather than adding a new
special-cased empty check, keeping the block functions' zero-input behavior
uniform across the file. No open questions.

## Post-merge fix round 1

Worked in worktree `/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T10-postfix1`
(removed at the end; branch kept), on the existing branch
`ticket/2026-09-18-wave4/T10-postfix`, created from `from-zero`'s tip at
`e8b257d` (this is the merged, post-review branch, not `ticket/2026-09-18-wave4/T10`
from the implementation round). Three findings from the wave-4 post-merge
review's `post-merge-review.json`, all verified `real` and all in
`eval/score_run.py`. `PY=/home/y-guo/reproduce/new1/external/probe-env/bin/python`
for every command below.

**SCORE-1 — `spec.tool_agree`, `call_agree` and `recalled` always 0.0.**
`_spec_block` joined the spec frame to the env rows on `(record_id, step)`,
but the spec frame already carries every column of
`data/trajectory_record.SCHEMA`, `action` included (null on every spec row,
since only `agent/loop.py`'s `env` row writer ever sets `action`). Polars
therefore named the env side's column `action_right`, and the code read
`row["action"]` — the spec row's own null — so `ap` was always `None` and
every rate was computed off the always-false branch. Root-cause fix: the env
side's `action` is selected under a name of its own, `env_action`, before
the join, and the comparison reads that column:

```python
-    env_rows = df.filter(pl.col("type") == "env").select(["record_id", "step", "action"])
+    env_rows = df.filter(pl.col("type") == "env").select(
+        ["record_id", "step", pl.col("action").alias("env_action")])
     joined = spec.join(env_rows, on=["record_id", "step"], how="left")
     ...
-        action = row["action"]
+        action = row["env_action"]
```

**SCORE-2 — `TypeError` on an inject run whose every `spec.conf` is null.**
`conf_mean` and `discarded_chars` (and nine other fields across the file)
computed `round(float(series.mean()), 4)` directly; `Series.mean()` of an
all-null column returns `None`, and `float(None)` raises before
`run_report.json`, `report.md` or `done.json` is written. Root-cause fix:
every mean in the file now goes through one null-safe helper, `_mean`,
applying the same rule `_rate` already applies to a zero denominator:

```python
def _mean(series: pl.Series) -> float | None:
    """The series' mean rounded to 4, or None when it holds no non-null value (Series.mean of an all-null column)."""
    value = series.mean()
    return round(float(value), 4) if value is not None else None
```

All eleven `.mean()` call sites in the file (`_run_block`'s seven,
`_paired_block`'s two, `_spec_block`'s two, `_resume_block`'s one — eleven
total across four functions) were checked and now go through `_mean`.
Checked `.sum()` too, per the finding's instruction: measured directly
(`external/probe-env`, a fresh all-null `Float64` and all-null `Boolean`
Polars series), `Series.sum()` of an all-null column returns `0`/`0.0`, never
`None`, so no `.sum()` call site in the file shares this failure shape; only
`.mean()` does.

**SCORE-3 — every heartbeat beat emitted before any record is read.**
`main` emitted `hb.emit(0, len(pairs), "task")` and then all `len(pairs)`
per-task beats in one loop, entirely before `trajectory_record.read_dir` was
called once over the whole pair list. Root-cause fix: the pairs are now read
one at a time, `trajectory_record.read_dir(dir, [pair])` per requested pair
(scored and, when paired, baseline), and the beat for a pair is emitted
right after both its reads complete; the frames are concatenated afterward.
Both gates (same-setup, baseline completeness) still run over the whole pair
list before the first read, unchanged.

```python
-    for i in range(1, len(pairs) + 1):
+    scored_frames: list[pl.DataFrame] = []
+    base_frames: list[pl.DataFrame] = []
+    for i, pair in enumerate(pairs, start=1):
+        scored_frames.append(trajectory_record.read_dir(scored_dir, [pair]))
+        if base_dir is not None:
+            base_frames.append(trajectory_record.read_dir(base_dir, [pair]))
         hb.emit(i, len(pairs), "task")

-    df = trajectory_record.read_dir(scored_dir, pairs)
-    bdf = trajectory_record.read_dir(base_dir, pairs) if base_dir is not None else None
+    df = pl.concat(scored_frames) if scored_frames else pl.DataFrame(schema=trajectory_record.SCHEMA)
+    bdf = None
+    if base_dir is not None:
+        bdf = pl.concat(base_frames) if base_frames else pl.DataFrame(schema=trajectory_record.SCHEMA)
```

### How it was verified

**A1 — import test, six files, three venvs.** Rerun in full: `import test
done`, no `FAIL` line, exit 0.

**A2 — no torch, no GPU.** Rerun: no matches, `exit=1`.

**A3 — the literal lines.** Rerun: `literals ok`, exit 0.

**A8 — `score_run` end to end, plus both refusals.** Rebuilt the same
fixture as the earlier rounds (`1111aaaa1111` debug sample, `2222bbbb2222`
non-debug baseline sample, `3333cccc3333` debug score). Main run: `A8 ok`
with the same assertions as before (`rep["run"]["success"] == 1.0`,
`rep["baseline"]["success"] == 0.0`, `rep["paired"]["n"] == 2`,
`rep["paired"]["delta_success"] == 1.0`, `rep["spec"]["n"] == 0`,
`rep["by_seed"]["42"]["n_records"] == 2`, `done.json` `stage == "score"` and
`report == "report.md"`, no `consumed.json`), and the heartbeat file for
this run now reads (interleaved, one beat per task read, as SCORE-3
requires):
```
{"done": 0, "total": 2, "unit": "task", ...}
{"done": 1, "total": 2, "unit": "task", ...}
{"done": 2, "total": 2, "unit": "task", ...}
{"done": 2, "total": 2, "unit": "task", ..., "status": "done"}
```
Then the same-setup gate refusal (baseline `temperature` set to `0.7`):
`ValueError: score_run: same-setup gate failed between .../debug/sample/1111aaaa1111
and .../sample/2222bbbb2222: generation.temperature differs`, `exit=1`. Then,
after restoring `temperature: 1.0` and deleting the baseline record
`82e2fac_1__s42.jsonl`, the completeness gate raised
`ValueError: score_run: baseline .../sample/2222bbbb2222 is missing a done
record for pair(s) [('82e2fac_1', 42)]`, `exit=1`. Both match the ticket's
expected messages. Cleaned up all three directories afterward; a `find`
over the outputs root for the three keys returned nothing.

**SCORE-1 — direct fixture, mktemp -d, `data/trajectory_record.py`'s
writer, `_spec_block` called on the frame read back (not the outputs
root).** Two records, two steps each (four spec rows total): record 1
step 0 has `gen_call` byte-identical to that step's `env.action`
(`apis.a.x(k=1)` both sides — expect `tool_agree`/`call_agree`/`recalled`
all true for that row); record 1 step 1 has the same tool but a different
argument (`gen_call=apis.a.x(k=2)` against `env.action=apis.a.x(k=1)` —
`tool_agree` true, `call_agree` false, `recalled` true, since the tool name
is still a substring of the env action text); record 2 step 0 has a
`gen_call` that does not parse (`"not a call at all"`); record 2 step 1 has
`env.action=None` (a null action row) with a `gen_call` for a different
tool (`apis.b.y(k=1)`). Every step also carries a `resume` row, to confirm
the presence of another row kind sharing the `step` column does not disturb
the join.

```
spec block: {'n': 4, 'exec_ok': 1.0, 'tool_agree': 0.5, 'call_agree': 0.25, 'recalled': 0.5, 'conf_mean': 0.9, 'discarded_chars': 3.0, 'error_kinds': {}}
SCORE-1 fixture ok
```
`n=4`, `tool_agree=0.5` (2/4: step 0 of each kind of match plus the
different-argument row), `call_agree=0.25` (1/4: only the byte-identical
row), `recalled=0.5` (2/4: the two rows whose parsed tool name appears in a
non-null `env.action`) — matches hand computation.

**Before/after comparison for SCORE-1** (`git stash` to the pre-fix code,
same fixture script, `git stash pop` after): pre-fix gives
`{'tool_agree': 0.0, 'call_agree': 0.0, 'recalled': 0.0, ...}` on the same
four rows — confirms the defect and the fix are both exercised by a real
before/after run, not just presumed.

**SCORE-2 — direct fixture (same mktemp -d approach) plus a full
`main()` end-to-end run.** Direct fixture: one record, two steps, both
spec rows carrying `conf=None, pred_label=None` (the shape
`agent/inject.py` writes under `inject.fire_nth_cut > 0`):
```
spec block (all-null conf): {'n': 2, 'exec_ok': 1.0, 'tool_agree': 1.0, 'call_agree': 1.0, 'recalled': 1.0, 'conf_mean': None, 'discarded_chars': 3.0, 'error_kinds': {}}
SCORE-2 fixture ok
```
Before/after: the same script against the pre-fix code (`git stash`) raises
`TypeError: float() argument must be a string or a real number, not
'NoneType'` at the `conf_mean` line, confirming the defect.

End-to-end `main()` run: an `inject`-scored score run (`_upstream` carrying
`inject` and `baseline.sample`, `inject.fire_nth_cut: 1` in the frozen
setting) whose two spec rows both carry `conf=None, pred_label=None`, paired
against a `sample` baseline. `main()` completed with exit 0:
```
spec block: {'n': 2, 'exec_ok': 1.0, 'tool_agree': 1.0, 'call_agree': 1.0, 'recalled': 1.0, 'conf_mean': None, 'discarded_chars': 3.0, 'error_kinds': {}}
done metrics: {'success': 1.0, 'base_success': 0.0, 'delta_success': 1.0, 'tokens_out': 20.0, 'spec_exec_ok': 1.0, 'spec_tool_agree': 1.0, 'spec_call_agree': 1.0, 'n_records': 2}
SCORE-2 e2e ok
```
`run_report.json`, `report.md` and `done.json` were all written, and
`done.json`'s `metrics` correctly omits `conf_mean` (it is not one of the
pinned `done.json` metric names, and the pinned ones present are all
non-null). Cleaned up the three fixture directories (keys `8888iiii8888`,
`9999jjjj9999`, `aaaakkkkaaaa`) afterward; a `find` over the outputs root
returned nothing.

**SCORE-3 — a real `score_run.main()` run with a read that raises on the
second pair.** Built a two-pair `sample` fixture and a `score` run over it
(no baseline, to isolate the scored-side read loop), then monkeypatched
`data.trajectory_record.read_dir` to raise `RuntimeError` on its second
invocation and called `score_run.main(rdir)` directly (not through
`subprocess`, so the monkeypatch reaches the module). The call raised as
expected, and the heartbeat file left behind was:
```
{"done": 0, "total": 2, "unit": "task", ...}
{"done": 1, "total": 2, "unit": "task", ...}
```
— stopped at `done=1` of `total=2`, no `status: "done"` line, and no
`done.json` was written. This is the exact shape the finding names: a
score run that dies mid-read leaves a heartbeat that does not reach
`done >= total`, so `registry.judge` (which tests `done >= total` before
`alive`) no longer reports it `done`.

**Before/after comparison for SCORE-3** (`git stash` to the pre-fix code,
same script): the pre-fix code calls `trajectory_record.read_dir` exactly
once, over the whole pair list, so the monkeypatch's "raise on the second
call" never fires (there is only one call) — and the heartbeat file already
reached `{"done": 2, "total": 2, ..., "status": "done"}` *before* that one
read call ran, confirming the defect directly: every beat is emitted before
any record is read, whether or not the read later fails.

**Clean-up.** Deleted all fixture directories from the SCORE-1, SCORE-2 and
SCORE-3 checks above (the SCORE-1 and SCORE-2 direct fixtures wrote nothing
under the outputs root — they call `_spec_block` on an in-memory frame built
under `mktemp -d`, per the finding's own instruction). The SCORE-2 e2e keys
(`8888iiii8888`, `9999jjjj9999`, `aaaakkkkaaaa`) and the SCORE-3 keys
(`bbbb1111bbbb`, `cccc2222cccc`) were removed by their scripts; the A8
keys (`1111aaaa1111`, `2222bbbb2222`, `3333cccc3333`) were removed after the
A8 rerun. A final `find` over the outputs root for all eight keys returned
nothing.

### Commits

- `3117e32` — `T10: post-merge fix round 1 (SCORE-1, SCORE-2, SCORE-3)`
  (all three findings, one commit).

### Self-review and open questions

Every fix is a root-cause correction in the exact function the finding
names — no special case was added around the wrong logic, the wrong logic
was replaced outright. SCORE-1's fix is a one-name change (`env_action`
instead of colliding on `action`); SCORE-2's fix introduces one small
helper (`_mean`) and routes every existing `.mean()` call through it,
touching no other arithmetic; SCORE-3's fix reorders the existing read and
beat calls without changing what either does. No refactor beyond the three
findings was done, and no other file was touched. AGENT-1, LAUNCH-1,
LAUNCH-3 and LAUNCH-4 (the other findings the wave-4 review verified `real`)
are outside `eval/score_run.py` and are not this ticket's — they belong to
tickets 11 and 12 respectively. No open questions.

## Owner rulings applied, round 1

Worked in worktree `/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T10-table-ruling1`
(removed at the end; branch kept), on a fresh branch
`ticket/2026-09-18-wave4/T10-table-ruling` cut from `from-zero`'s tip at
`d1a4e60`. Three owner rulings on `eval/method_table.py`, all applied.
`PY=/home/y-guo/reproduce/new1/external/probe-env/bin/python` for every
command below.

**RULING-1 — backbone off the train run's own directory, not a registry-row
match.** `_backbone_of` no longer takes `all_rows` and no longer searches the
`registry.ls(...)` result for a `stage == "train"` row whose `key` matches.
It now reads the eval row's own `meta.json` for `upstream["train"]` (as
before), then locates the train run directory directly with
`schema.run_dir_of("train", train_key, debug=row["flags"]["debug"])` (the
eval row's own debug placement — an eval's train upstream sits in the same
workflow walk) and reads that directory's own `meta.json`, taking
`backbone = diff.get("models.probe", <schema default>)`. A missing eval
`meta.json`, a missing `upstream["train"]`, or a missing train-directory
`meta.json` all print `"?"`. This removes the dependency on the train run
being present in the same `registry.ls` result — the registry-row lookup is
gone, `table` calls `registry.ls` once and no longer needs to keep the whole
unfiltered result around for a second pass.

```python
def _backbone_of(row: dict) -> str:
    meta_path = Path(row["dir"]) / "meta.json"
    if not meta_path.exists():
        return "?"
    meta = json.loads(meta_path.read_text())
    train_key = (meta.get("upstream") or {}).get("train")
    if train_key is None:
        return "?"
    debug = row.get("flags", {}).get("debug", False)
    train_dir = schema.run_dir_of("train", train_key, debug=debug)
    train_meta_path = train_dir / "meta.json"
    if not train_meta_path.exists():
        return "?"
    train_meta = json.loads(train_meta_path.read_text())
    diff = train_meta.get("diff") or {}
    return diff.get("models.probe", schema.SECTION_CLASSES["models"]().probe)
```

**RULING-2 — a `debug` switch, passed straight to `registry.ls`.**
`table`'s signature is now
`table(workflow: str | None = None, out: Path | None = None, *, debug: bool = False) -> str`;
the body calls `registry.ls(workflow, debug=debug)` instead of the
hard-coded `debug=False`, and keeps the `stage == "eval"` filter. With
`debug=False` (the default) the table is exactly what it was; with
`debug=True` a `--debug` walk's eval rows are listed too. Ticket 14's
`run.py` will expose this as `run.py table [workflow] --debug`, per the
owner's ruling text.

**RULING-3 — sweep children are parallel settings, never grouped by
parent.** The grouping line changed from
`group_key = row.get("parent") or row.get("setting")` to
`groups.setdefault(row["setting"], []).append(row)` — the group key is
always the row's own `setting` name, a sweep child's full name included.
`row["parent"]` and `row["swept"]` are read nowhere in the file now (checked
with `grep -n "parent\|swept" eval/method_table.py`: the only remaining hit
is the word "parent" inside a docstring sentence, not a dict read). A group
still holds every run recorded under one setting name and reports
`mean ± spread` over those runs, the bare value for a group of one.

Both `README.md`'s `## Ticket 10` file line for `method_table.py` and its
"Decisions made" paragraph were updated to match: the `offers:` signature
now carries the `debug` keyword, the `reads:` line names the train run's own
`meta.json`, and the prose states the setting-keyed grouping and the
`schema.run_dir_of`-located backbone instead of the old registry-row lookup
and parent-keyed grouping.

### How it was verified

**A1 — import test, six files, three venvs.** Rerun in full over
`external/probe-env`, `external/appworld/venv`, `external/vllm-env`:
`import test done`, no `FAIL` line, exit 0.

**A3 — the literal lines.** Rerun: `literals ok`, exit 0.

**A9 — `method_table` over the (still empty in this worktree) real
registry.**
```
| backbone | method | risk | n | coverage | trig_acc | earliness | wrong_spec | tool_ok | params_all_ok | full_call_ok | runs | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
```
Header starting `#`, the `| backbone | method | risk |` row present, empty
body, `exit=0`. Completed instantly with no `ssh`-related output — this
worktree's `jobs/runs.jsonl` is empty, so `registry.ls`'s early return
(before `live_sessions()`) still fires, unaffected by RULING-2's new
`debug` parameter.

**Fabricated-ledger check for all three rulings**, in a `mktemp -d` tree
(`/tmp/tmp.BbGMo2Lu19`, removed after the run), with `jobs/registry.py`'s
`_runs_path`/`_lock_path`/`_results_path` and
`experimental_settings/schema.py`'s `_outputs_config` monkeypatched to a
second `tempfile.mkdtemp()` tree inside the same process, and
`registry.live_sessions` stubbed to `lambda: set()` so no `ssh`/`tmux` call
is made at any point. Ledger rows were appended directly as JSON lines
(bypassing `registry.append_start`, since no real launch is being
simulated); run directories carried a hand-written `meta.json` and, where a
report was needed to produce a table row, a minimal generator
`probe_report.json` (`probe_kind: "generator"`, one risk `0.05`, `exact`
block with `tool_ok/params_all_ok/full_call_ok = 1.0`, `n = 10`).

1. **Backbone from the train directory's own `meta.json`, `"?"` when
   absent.** One non-debug eval row's train key pointed at a train
   directory whose `meta.json` carried `diff: {"models.probe":
   "qwen3_1pt7b"}`; a second non-debug eval row's train key pointed at a
   train directory that exists but carries no `meta.json` at all. Output:
   ```
   | qwen3_1pt7b | cgen | 0.05 | 10 | - | - | - | - | 1.0000 | 1.0000 | 1.0000 | 1 | OK |
   | ? | cgen | 0.05 | 10 | - | - | - | - | 1.0000 | 1.0000 | 1.0000 | 1 | OK |
   ```
   Both rows present, `qwen3_1pt7b` and `?` each appearing exactly once.
   Confirmed check: `check 1 ok: backbone off the train run's own meta.json
   (found qwen3_1pt7b and ?)`.
2. **`table(debug=True)` lists a debug eval row, `table()` does not.** A
   third eval row was appended with `debug: true` in its start row and a
   train reference to a `qwen3_0pt6b` backbone. `table()` (default
   `debug=False`) rendered no row carrying `qwen3_0pt6b`; `table(debug=True)`
   did. Confirmed check: `check 2 ok: table(debug=True) lists the debug
   eval row, table() does not`.
3. **Two sweep children of one parent render as two separate groups.** Two
   more eval rows were appended sharing one sweep parent
   (`parent: "cgen_sweep"`) but distinct setting names
   (`cgen_sweep/train.lr=0.0001,train.seed=42` and
   `cgen_sweep/train.lr=0.0003,train.seed=42`), each with its own report.
   Output added two more `qwen3_1pt7b | cgen | 0.05` rows, each with
   `runs = 1` — no row anywhere in the table carries `runs = 2`. Confirmed
   check: `check 3 ok: the two sweep children render as two separate groups
   (runs=1 each), not merged`.

Full script output ended `ALL FABRICATED-LEDGER CHECKS OK`. The temp
ledger/outputs tree (`tempfile.mkdtemp()`'s own directory, distinct from
the script's own `mktemp -d` home) was removed after the run
(`rm -rf /tmp/tmpz761skbb`); nothing was written under the real outputs
root or into the real `jobs/runs.jsonl`/`jobs/RESULTS.md`.

### Commits

- `1dd95ff` — `T10: eval/method_table.py -- apply owner rulings round 1`
  (backbone off the train run's own `meta.json` via `schema.run_dir_of`, a
  `debug` switch on `table()`, sweep children grouped by their own setting
  name; both files, one commit).

### Self-review and open questions

Each ruling replaced the ruled-over logic outright — `_backbone_of` no
longer takes or reads `all_rows` at all (the registry-row search is gone,
not special-cased around), the grouping line reads `row["setting"]` only
(no `or row.get("parent")` fallback survives), and `debug` flows straight
into `registry.ls` with no branch of its own. No file outside
`eval/method_table.py` and `README.md` was touched. No open questions.

## Owner rulings applied, round 1 (score_run, cgen, cparam)

Worked in worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T10-score-ruling1` (removed at
the end; branch kept), on a fresh branch
`ticket/2026-09-18-wave4/T10-score-ruling` cut from `from-zero`'s tip at
`d1a4e60` (base). Head after the commit: `a120a60`. Two owner rulings, on
`eval/score_run.py`, `eval/methods/cgen.py` and `eval/methods/cparam.py`, both
applied. `PY=/home/y-guo/reproduce/new1/external/probe-env/bin/python` for
every command below.

**RULING-4 — the score report keeps only the success rates and the probe
agreement rates.** Every removed field's computation was deleted outright,
not special-cased around:

- `_finals` now selects only `record_id`, `task_id`, `seed` off the meta rows
  and `record_id`, `success`, `abort` off the final rows — the `steps`,
  `completed`, `tokens_in`, `tokens_out`, `wall_s` columns and the whole
  gen-row sum join (`n_inject_sum`, `usage_out_sum`, `discard_chars_sum`,
  `discard_tokens_sum`) are gone, since no kept field reads them.
- `_run_block` returns only `n_records`, `n_abort`, `success`,
  `success_no_abort`; `steps_mean`, `completed`, `tokens_in`, `tokens_out`,
  `n_inject_per_task`, `discard_chars`, `discard_tokens`, `wall_s_mean` and
  their computations are gone.
- `_paired_block` returns only `n`, `success`, `base_success`,
  `delta_success`; `tokens_out` and `base_tokens_out` are gone.
- `_spec_block` returns only `n`, `tool_agree`, `call_agree`, `recalled`;
  `exec_ok`, `conf_mean`, `discarded_chars`, `error_kinds` and their
  computations are gone. The agreement logic itself is unchanged: a
  `gen_call` or `env.action` that fails to parse already fell through to the
  `else` branch (`tool_agree_vals.append(False)`, `call_agree_vals.append(False)`)
  before this ruling, which is exactly the owner's option-A rule, so nothing
  needed to change there — re-verified below with a fixture built for this
  ruling.
- `_resume_block` and `_by_seed_block` are deleted in full, and `main` no
  longer calls them or reads `cfg.score.by_seed`; that setting is now read by
  nothing in the file (noted in the docstring TODO).
- `_render_report_md`'s per-task line is now
  `task_id | seed | success | base_success`, four columns, dropping `steps`,
  `n_inject`, `tokens_out`.
- `done.json`'s `metrics` are now `success`, `base_success`, `delta_success`,
  `spec_tool_agree`, `spec_call_agree`, `n_records`, with `tokens_out` and
  `spec_exec_ok` removed; the existing null-filter (`metrics = {name: value
  for name, value in metrics.items() if value is not None}`) is unchanged and
  still applies.
- The now-unused `_mean` helper and the `statistics` import are deleted; `_rate`
  stays, since the four kept rate fields all still go through it.
- Both gates (same-setup, baseline completeness) and the pair-by-pair read
  with one beat per task (the SCORE-3 fix) are untouched — verified by
  rerunning A8's two refusals and reading the heartbeat file below.
- The module docstring's first line is now "Score a sample or inject run from
  its task records: success rates and probe agreement rates, paired against a
  baseline," matched in `README.md`'s `score_run.py` line (the previous
  wording named `tokens and time` and `by seed`, both gone). A
  `TODO(gyb, 2026-09-18)` block follows the first line, listing every removed
  field by name and stating the owner decides later what the report holds,
  and noting `score.by_seed` is now unread.

**RULING-5 — the exact-match rule of the generator accuracy is marked
open.** No logic changed in `eval/methods/cgen.py` or `cparam.py`. Each
file's module docstring got one `TODO(gyb, 2026-09-18)` block, right after the
first line and before the existing `noparam` paragraph, stating that the
matching rule behind `match()`'s `tool_ok`, `params_all_ok` and
`full_call_ok` is open and the owner decides it later.

### How it was verified

**A1 — import test, six files, three venvs.** Rerun in full over
`external/probe-env`, `external/appworld/venv`, `external/vllm-env`:
```
import test done
```
No `FAIL` line, exit 0.

**A3 — the literal lines.** Rerun:
```
literals ok
```
Exit 0. `VERSION` and `PROBE_KIND` are untouched by both rulings, as expected.

**A7 — `match` callable from the train side.** Rerun verbatim:
```
A7 ok
```
Confirms RULING-5 changed no logic: `cgen.match`'s and `cparam.match`'s
behaviour, including the dropped `noparam` short-circuit, is exactly as
before.

**A8 — `score_run` end to end, plus both refusals, with the ruling's fields
retired named.** Rebuilt the ticket's own fixture verbatim (`1111aaaa1111`
debug sample, `2222bbbb2222` non-debug baseline sample, `3333cccc3333` debug
score — created under the real outputs root by the ticket's own command, as
the acceptance text does, then deleted). Heartbeat file for the run, one beat
per task read plus the finish beat, unchanged from the post-merge fix shape:
```
@hb {"done": 0, "total": 2, "unit": "task", ...}
@hb {"done": 1, "total": 2, "unit": "task", ...}
@hb {"done": 2, "total": 2, "unit": "task", ...}
@hb {"done": 2, "total": 2, "unit": "task", ..., "status": "done"}
```
Main run assertions, with the retired ones dropped and a check added that
`by_seed` and `resume` no longer appear on the report:
```
score keys: ['baseline', 'baseline_key', 'commit', 'n_pairs', 'n_seeds', 'n_tasks', 'paired', 'run', 'scored_key', 'scored_stage', 'spec', 'stage_key', 'version']
done metrics: {'success': 1.0, 'base_success': 0.0, 'delta_success': 1.0, 'n_records': 2}
A8 ok (ruling-adjusted)
```
`rep["scored_stage"] == "sample"`, `rep["n_pairs"] == 2`,
`rep["run"]["success"] == 1.0`, `rep["baseline"]["success"] == 0.0`,
`rep["paired"]["n"] == 2`, `rep["paired"]["delta_success"] == 1.0`,
`rep["spec"]["n"] == 0`, `done.json`'s `stage == "score"` and
`report == "report.md"`, `report.md` exists, no `consumed.json` — all held.
**Retired by this ruling, and why:** the ticket's original A8 line
`assert rep["spec"]["n"] == 0 and rep["by_seed"]["42"]["n_records"] == 2`
had its second half retired — `rep["by_seed"]` no longer exists, since
RULING-4 deletes the whole by-seed block; `rep["spec"]["n"] == 0` is
unretired and still checked, since `spec.n` is a kept field. No other A8
assertion referenced a removed field. The acceptance text itself was not
edited, per instruction.

Then the same-setup gate refusal (baseline `temperature` set to `0.7`):
```
ValueError: score_run: same-setup gate failed between .../debug/sample/1111aaaa1111 and .../sample/2222bbbb2222: generation.temperature differs
exit=1
```
Then, after restoring `temperature: 1.0` and deleting the baseline record
`82e2fac_1__s42.jsonl`, the completeness gate:
```
ValueError: score_run: baseline .../sample/2222bbbb2222 is missing a done record for pair(s) [('82e2fac_1', 42)]
exit=1
```
Both messages match the ticket's expected wording and both gates ran
unchanged by this ruling. **Clean-up:** deleted all three fixture
directories afterward — `debug/sample/1111aaaa1111`, `sample/2222bbbb2222`
(non-debug), `debug/score/3333cccc3333` — and a `find` over the outputs root
for the three keys returned nothing.

**SCORE-1 fixture rerun (post-merge fix), gen_call equal to env.action on
every step.** A direct fixture built under `mktemp -d`
(`data/trajectory_record.py`'s writer, `_spec_block` called on the frame held
in memory, nothing written under the outputs root): one record, two steps,
each step's `spec.gen_call` byte-identical to that step's `env.action`
(`apis.a.x(k=1)` and `apis.b.y(k=2)`). Result:
```
SCORE-1 equal-call fixture spec block: {'n': 2, 'tool_agree': 1.0, 'call_agree': 1.0, 'recalled': 1.0}
SCORE-1 equal-call fixture ok
```
`n=2`, `tool_agree=1.0`, `call_agree=1.0`, `recalled=1.0` — the SCORE-1
post-merge fix (the `env_action` column rename that stopped `_spec_block`
from reading the spec row's own null `action` column) still holds under
RULING-4's trimmed-down `_spec_block`.

### Commits

- `a120a60` — `T10: owner rulings round 1 (RULING-4, RULING-5)` (both
  rulings, one commit).

### Self-review and open questions

Both rulings replaced the ruled-over logic outright: no removed field is
computed anywhere in the file and then merely dropped from the output dict,
and no special case or flag was added around either ruling. `eval/score_run.py`
is 76 lines shorter (336 -> 261 after also removing the now-dead `_mean`
helper and `statistics` import); `eval/methods/cgen.py` and `cparam.py` gained
only their four-line TODO blocks, no logic line changed, confirmed by A7's
unchanged output. `README.md`'s `score_run.py` line was updated to match the
new docstring first line, since the old one named fields (`tokens and time`,
`by seed`) that no longer exist; `cgen.py` and `cparam.py`'s README lines
needed no change, since their one-line summaries ("exact match of the
generated call/arguments at the frozen theta") were never about the tiers'
computation rule and stay true. No file outside `eval/score_run.py`,
`eval/methods/cgen.py`, `eval/methods/cparam.py` and `README.md` was touched.

Open question carried forward for the owner, not mine to resolve: RULING-4's
`score.by_seed` setting is now read by nothing in the codebase (noted in the
docstring TODO) — whether the setting itself should also be removed from
`experimental_settings/schema.py` is outside this ticket's file list and the
owner's to decide alongside "what a score report holds."

## Owner rulings applied, round 2

Worked in worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T10-table-ruling2` (removed at
the end; branch kept), checking out the existing branch
`ticket/2026-09-18-wave4/T10-table-ruling` at `1dd95ff` (base
`d1a4e60ffb50436bd4a8d7e8a3df5b194e71fe54`, the same base the round-1 branch
was cut from — round 2 continues that branch rather than starting a new one).
Head after the commit: `b497315`. One finding applied, N1-1, in
`eval/method_table.py`.

**N1-1 — `table(debug=True)` averaged a debug run and a real run of the same
setting into one cell.** Root cause: `registry.ls(workflow, debug=True)`
drops the `debug` filter rather than selecting only debug rows
(`jobs/registry.py`: `if not debug: entries = [e for e in entries if not
e["start"].get("debug")]`), so a `debug=True` call returns every debug **and**
non-debug row. `table`'s grouping key was `row["setting"]` alone (round 1's
`RULING-3`), so a `--debug` walk of a setting that already has a real eval run
landed in the same group as that real run and the two were averaged — the
exact shape the finding reproduced: a real `cls_main` row (`n=1000, coverage
0.9000`) and a debug `cls_main` row (`n=4, coverage 0.1000`) folded into one
printed row, `n = 502.0 ± 704.3, coverage = 0.5000 ± 0.5657, runs = 2`,
matching neither run and carrying no column that says a debug run is mixed
in. This defeats the owner's purpose for the `debug` switch (round 1's
`RULING-2`): `M-E2` verifies the generator eval on a `--debug` walk, and the
number the table shows is unusable whenever a non-debug run of the same
setting already exists.

Fix, applied at the root — the grouping key itself, not a filter layered on
top of it: the group key is now `(row["setting"], row["flags"]["debug"])`
instead of `row["setting"]` alone.

```python
-    groups: dict[str, list[dict]] = {}
+    groups: dict[tuple[str, bool], list[dict]] = {}
     for row in eval_rows:
-        groups.setdefault(row["setting"], []).append(row)
+        groups.setdefault((row["setting"], row["flags"]["debug"]), []).append(row)
```

`table()` (default `debug=False`) is unaffected — `registry.ls(..., debug=False)`
already excludes every debug row before grouping runs, so its groups were
already debug-free. `table(debug=True)` now renders the real run and the
debug run of one setting as two separate rows/groups, each `runs = 1`,
instead of one merged `runs = 2` row. No new column names which run is
debug — the printed column set stays the contract-pinned thirteen — the fix
is that the two numbers are no longer combined, not that the table narrates
the difference. `README.md`'s `## Ticket 10` file line and the
"Decisions made" paragraph for `method_table.py` were updated to state the
`(setting, debug)` grouping key and why `registry.ls`'s own filter shape
makes it necessary.

### How it was verified

`PY=/home/y-guo/reproduce/new1/external/probe-env/bin/python` for every
command below, run from the worktree root.

**A1 — import test, six files, three venvs.** Rerun in full over
`external/probe-env`, `external/appworld/venv`, `external/vllm-env`:
```
import test done
```
No `FAIL` line, exit 0.

**A3 — the literal lines.** Rerun:
```
literals ok
```
Exit 0.

**A9 — `method_table` over the (still empty in this worktree) real
registry.**
```
# eval matrix: backbone x method x risk

| backbone | method | risk | n | coverage | trig_acc | earliness | wrong_spec | tool_ok | params_all_ok | full_call_ok | runs | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
```
Header starting `#`, the `| backbone | method | risk |` row present, empty
body, `exit=0`, elapsed 0.001 s — the empty-ledger `live_sessions()`
short-circuit still fires (confirmed by the near-instant return; no
`ssh`-related output).

**Fabricated-ledger check, all three items the dispatch names**, in a
`mktemp -d` script directory (`/tmp/tmp.By38XpTARu`, removed after the run)
with a *separate* `tempfile.mkdtemp()` scratch tree monkeypatched into the
process for the ledger and the outputs root
(`jobs/registry.py`'s `_runs_path`/`_lock_path`/`_results_path` and
`experimental_settings/schema.py`'s `_outputs_config`), and
`registry.live_sessions` stubbed to `lambda: set()` so no `ssh`/`tmux` call
is made. Ledger rows were appended directly as JSON lines; run directories
carried a hand-written `meta.json` and, per row, a minimal `probe_report.json`.

1. **Backbone from the train directory's own `meta.json`, `"?"` when
   absent.** One non-debug eval row's train key pointed at a train
   directory whose `meta.json` carried `diff: {"models.probe":
   "qwen3_1pt7b"}`; a second non-debug eval row's train key pointed at a
   train directory that exists but carries no `meta.json`. Output:
   ```
   | qwen3_1pt7b | ctool | 0.05 | 40 | 0.7500 | 0.8000 | 0.3000 | 0.0500 | - | - | - | 1 | OK |
   | ? | ctool | 0.05 | 40 | 0.7500 | 0.8000 | 0.3000 | 0.0500 | - | - | - | 1 | OK |
   ```
   `check 1 ok: backbone off the train run's own meta.json (qwen3_1pt7b) and
   '?' when absent`.
2. **`table(debug=True)` lists a debug eval row and `table()` does not — the
   N1-1 regression itself.** A real eval row (`cls_main`, `n=1000, coverage
   0.9000`) and a debug eval row of the same setting name (`cls_main`,
   `n=4, coverage 0.1000`) were appended. `table()` (`debug=False`):
   ```
   | qwen3_1pt7b | ctool | 0.05 | 1000 | 0.9000 | 0.8500 | 0.2500 | 0.0200 | - | - | - | 1 | OK |
   ```
   one row, the real run only. `table(debug=True)`:
   ```
   | qwen3_1pt7b | ctool | 0.05 | 1000 | 0.9000 | 0.8500 | 0.2500 | 0.0200 | - | - | - | 1 | OK |
   | qwen3_1pt7b | ctool | 0.05 | 4 | 0.1000 | 0.5000 | 0.5000 | 0.5000 | - | - | - | 1 | OK |
   ```
   two rows, `runs = 1` each, no `±` anywhere and no `502`. `check 2a ok`,
   `check 2b ok`. **Before/after comparison**: the same script run against
   the pre-fix code (`git stash` to `1dd95ff`, rerun, `git stash pop`)
   reproduced the exact defect the finding names on the same fixture —
   `table(debug=True)` printed one merged row,
   `| qwen3_1pt7b | ctool | 0.05 | 502.0 ± 704.3 | 0.5000 ± 0.5657 | 0.6750 ± 0.2475 | 0.3750 ± 0.1768 | 0.2600 ± 0.3394 | - | - | - | 2 | OK |`
   — confirming the defect and the fix are both exercised by a real
   before/after run on the fix's own regression fixture, not just presumed.
3. **Two sweep children of one parent render as two separate groups.** Two
   eval rows sharing one sweep parent (`parent: "cgen_sweep"`) but distinct
   setting names (`cgen_sweep/train.lr=0.0001,train.seed=42` and
   `cgen_sweep/train.lr=0.0003,train.seed=42`), each with its own generator
   report, rendered as two rows, each `runs = 1` — no row carries `runs = 2`.
   `check 3 ok`.

Full script output ended `ALL N1-1 FABRICATED-LEDGER CHECKS OK`. The
`tempfile.mkdtemp()` ledger/outputs scratch tree and the `mktemp -d` script
directory were both removed after the run; nothing was written under the
real outputs root or into the real `jobs/runs.jsonl`/`jobs/RESULTS.md`.

### Commits

- `b497315` — `T10: eval/method_table.py -- fix N1-1, debug/non-debug rows of
  one setting no longer merge` (the grouping-key fix, `eval/method_table.py`
  and `README.md`, one commit).

### Self-review and open questions

The fix replaces the ruled-over logic outright: the group key is
`(row["setting"], row["flags"]["debug"])` everywhere in the file now, with no
leftover `row["setting"]`-only path and no special case guarding the
mixed-debug scenario — a debug row simply can never share a group with a
non-debug row, by construction of the key. No column was added to the
contract-pinned thirteen to narrate which run is debug; the fix is that the
two runs' numbers are never combined, which is what the finding asked to be
true. No file outside `eval/method_table.py` and `README.md` was touched.
No open questions.
