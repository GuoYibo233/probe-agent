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
