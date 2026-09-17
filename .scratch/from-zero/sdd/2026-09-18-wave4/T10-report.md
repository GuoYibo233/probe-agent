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
