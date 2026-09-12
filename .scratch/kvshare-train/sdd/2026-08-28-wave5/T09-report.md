# T09 Report: Parameterize All Alignment-Check Thresholds, Add the Relative Criterion `--align-rule {abs,rel,both}`

Ticket: `.scratch/kvshare-train/issues/09-align-tolerance-params.md`
Spec: `.scratch/kvshare-train/spec.md` 16.4 (criteria and key names), 16.9 item 3 (tests)
Branch: `ticket/2026-08-28-wave5/T09` (worktree `new1-wt/2026-08-28-wave5-T09`, deleted, branch kept)
base: `07907db08b50d66c1c193588f22b5cc97b24b4b3`
head: `ebbf4e2` (after `f7e833f`)

## I. What was done (checked against the ticket item by item)

### 1. `train_causal_share.py`

- Deleted the module-top constants `TOK_DIFF_TOL` (3e-4), `BF16_MEAN_TOL` (2e-2),
  `BF16_MAX_TOL` (1e-1), along with the outdated comment above them saying "fixed
  value, not a command-line argument"; `ALIGN_LEN_FILTER`, `REF_BATCH`,
  `REF_INST_CE_DRIFT_TOL` untouched.
- Added six new parameters, all placed after `--align-events` and before
  `lora_util.add_args(ap)`: `--align-tok-tol` (default 3e-4),
  `--align-bf16-mean-tol` (default 2e-2), `--align-bf16-max-tol` (default 1e-1),
  `--align-baseline-factor` (default 3.0), `--align-rule`
  (`choices=["abs","rel","both"]`, default `abs`), `--align-rel-tol` (default
  1e-5). `--align-tol` (2e-5) already existed, not added again.
- All three old-constant references in `run_align_check` were replaced with
  `args.align_tok_tol` / `args.align_bf16_mean_tol` / `args.align_bf16_max_tol`;
  the hardcoded multiplier `3 ×` for the baseline warning was replaced with
  `args.align_baseline_factor ×`.
- Judgment logic:
  - `abs_ok = row_diff <= args.align_tol and tok_diff <= args.align_tok_tol`
    (byte-for-byte identical to the pre-change `pass_ok` expression, just split
    out into an intermediate variable).
  - `ref_scale = mean(|ce_ref_i|)` (takes the absolute value of `row_ref`, the
    return value of the one pass over the whole `REF_BATCH` reference path, and
    then takes one overall mean, not a per-row division of each ce individually).
  - When `ref_scale == 0`, `rel_max_abs_diff = None`, `rel_ok = False`; otherwise
    `rel_max_abs_diff = row_diff / ref_scale`, `rel_ok = rel_max_abs_diff <=
    args.align_rel_tol`.
  - One of three chosen by `args.align_rule`: `abs` takes `abs_ok`, `rel` takes
    `rel_ok`, `both` takes the AND of the two; `pass_ok = hard_ok and rule_ok`
    (`hard_ok`, the consistency of row count / drop count, must hold regardless of
    which rule is used; this was already a hard prerequisite before the change
    and has not changed).
- `ALIGN_CHECK.json` was filled out with the nine keys named by the ticket
  (`tol` was already among the existing keys, not duplicated): `rule, tol,
  tok_tol, rel_tol, ref_scale, rel_max_abs_diff, bf16_mean_tol, bf16_max_tol,
  baseline_factor`; the existing keys (`PASS, n_events, n_rows, n_tgt_tokens,
  max_abs_diff, max_tok_diff, baseline_max_abs_diff, bf16_mean_abs_diff,
  bf16_max_abs_diff, attn_impl, mismatch_idx, baseline_warn`) were left
  completely untouched. Both failure exits (the normal exit when the judgment
  fails, and the self-check failure exit for `RefBaselineDriftError`) carry the
  new keys. The normal exit carries all nine, the drift exit, per the ticket's
  requirement, adds only `rule` and `rel_tol` (that path exits abnormally before
  `abs_ok`/`rel_ok` are even computed, so the other seven keys have no value yet
  at that stage).
- Still `sys.exit(2)`; the failure message gains a line "rule --align-rule
  <rule>", and under the `rel`/`both` rule an extra line for the relative
  difference and `ref_scale` (when `ref_scale == 0`, this instead prints the
  explanation line "ref_scale is 0 ... the rel rule judges failure").
- The `start` event gains `align_rule=args.align_rule`, immediately after
  `align_bf16_warn` (the anchor point specified by the ticket).

### 2. `train_causal_tool.py`

- `align_check()` gains two keyword arguments `rule="abs"`, `rel_tol=1e-5`. The
  relative quantities reuse the existing `absmax_hidden`,
  `reldiff_hidden = d_h / max(absmax_hidden, 1e-9)`, `absmax_logits`,
  `reldiff_logits`, without giving them a second name; only the computation was
  moved to before the judgment logic. Judgment: `abs` = the current
  `max(d_h, d_l) < tol`; `rel` = `reldiff_hidden <= rel_tol and reldiff_logits <=
  rel_tol` (both quantities checked, same as the `abs` rule); `both` = both
  conditions at once. The original comment "for diagnostics, does not
  participate in the judgment" was rewritten to: under the `abs` rule these two
  quantities are only a diagnostic reference, under the `rel`/`both` rules they
  participate in the judgment.
- `main()` gains `--align-rule` (same three values, default `abs`) and
  `--align-rel-tol` (default 1e-5); the `align_check()` call site passes
  `rule=args.align_rule, rel_tol=args.align_rel_tol`. `ALIGN_CHECK.json` gains
  only two more keys, `rule, rel_tol` (the relative quantities were already in
  the report). The failure print message gains a line with the rule name, and
  `rel_tol` is also printed into the relative-difference line.

### 3. Tests

New file `tests/test_align_rules.py` (did not change the tail end of
`test_share_trainer.py` / `test_ctool_readpos.py`; only changed the `Namespace`
of one existing test case in `test_share_trainer.py`, reason below):

- `TestAlignRulesShare`: hand-built 3 short cgen events (2 rows each, the row
  `text` strings concatenated to strictly guarantee the prefix property required
  by the spot-check in `share_data.load_events`), without reading
  `pipeline/data/nyapass_aw_v1/gptoss`. Goes through the real CLI entry point
  `tcs.main()` (`sys.argv` patched, following the pattern of
  `TestMainSmokeCPU._run_smoke`), `--base` pointing at a temporarily saved
  `Qwen3Config` small-model directory, `--align-only`. Four test cases:
  - `test_three_rules_pass_with_all_new_keys`: runs each of the three rules
    `abs/rel/both` once, `ALIGN_CHECK.json` contains all nine new keys each
    time, the `rule` field matches the passed-in value, `PASS` is true every
    time.
  - `test_align_rel_tol_negative_fails`: `--align-rule rel --align-rel-tol -1`
    exits with code 2.
  - `test_baseline_factor_zero`: after `--align-baseline-factor 0`, first
    asserts the `baseline_factor` key equals 0.0; only asserts `baseline_warn`
    is true if `max_abs_diff > 1e-6` (the condition given by the last sentence
    of ticket item 1. On this small model, `max_abs_diff` measured exactly
    0.0, so this test case currently only reaches the assertion on the
    `baseline_factor` key half; the branch code is left in place for manual
    review).
  - `test_run_align_check_drift_exit_has_rule_and_rel_tol`: monkeypatches
    `_ref_forward` to directly raise `RefBaselineDriftError`, asserts that the
    minimal report written by `run_align_check` has `rule`/`rel_tol` matching
    the passed-in value.
- `TestAlignRulesTool`: builds a temporary model directory following the
  approach in `tests/test_share_trainer.py` line 59 (the `Qwen3Config`
  parameters in `_tiny_config`) and lines 625 to 632
  (`AutoModelForCausalLM.from_config(...).save_pretrained` +
  `tok.save_pretrained`), calling `tct.CausalProbe(model_dir, n_labels=4)`
  directly and then `tct.align_check(...)`, without going through `main()`,
  without reading the active data directory. Two test cases: all three rules
  pass and the report carries `reldiff_hidden/reldiff_logits/rule/rel_tol`;
  `rel_tol=-1` judges failure (`PASS=False`; since it does not go through the
  CLI there is no `sys.exit`).
- `tests/test_share_trainer.py`: the hand-built `argparse.Namespace` in
  `TestRunAlignCheckHandlesRefBaselineDriftError` (lines 316 to 318) was missing
  the six new attributes. Without adding them, the `except
  RefBaselineDriftError` branch of `run_align_check`, which reads
  `args.align_rule`/`args.align_rel_tol`, would raise `AttributeError`. Added
  the six attributes, with values equal to the CLI defaults. This change is
  within the file scope allowed by the ticket (one of the four files listed at
  the head of the ticket), and does not count as "adding a test case at the
  end"; it is maintaining an existing test case.

The small-model construction (`_tiny_config`/`QWEN_PATH`/`SEED`) is reused via
`from tests.test_share_trainer import _tiny_config, QWEN_PATH, SEED`, not
redefined a second time.

## II. How it was verified

The worktree does not have `pipeline/data` by default (that directory is
entirely excluded by `.gitignore`; it is a local convenience symlink in the main
repo's worktree, not tracked by git, and the worktree naturally cannot get it).
To avoid verifying only the weak result of "the test cases related to real data
are skipped", verification was done in two rounds:

**Round 1 (worktree as-is, `pipeline/data` absent)**: verifying the new test
file itself, and the test cases that do not depend on the real dataset:

```
cd new1-wt/2026-08-28-wave5-T09
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
    tests.test_align_rules tests.test_share_trainer tests.test_ctool_readpos
```
Output: `Ran 16 tests in 10.968s` `OK (skipped=8)`. All 8 skips are existing
test cases in `test_share_trainer.py` that depend on
`pipeline/data/nyapass_aw_v1/gptoss` (the `skipTest` in the `setUpClass` of
`TestMainSmokeCPU`, `TestRunAlignCheckHandlesRefBaselineDriftError`, etc.), not
new test cases added by this ticket. The new test cases (6 in
`test_align_rules`) and `test_ctool_readpos` (10 of them) all actually ran and
passed.

**Round 2 (temporarily built a local symlink pointing at the same data on the
net drive, deleted immediately after verification, did not touch the main
repo)**: re-ran the 8 existing test cases skipped in round 1, confirming this
change did not break them, and verifying that the six new `Namespace`
attributes I added in `test_share_trainer.py` genuinely let that drift branch
run through normally (not merely syntactically correct while skipped):

```
ln -s /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data \
    new1-wt/2026-08-28-wave5-T09/pipeline/data
cd new1-wt/2026-08-28-wave5-T09
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
    tests.test_align_rules tests.test_share_trainer tests.test_ctool_readpos
rm new1-wt/2026-08-28-wave5-T09/pipeline/data   # deleted immediately after verification
```
Output: `Ran 28 tests in 338.091s` `OK` (0 skips, all actually ran and passed).
In this round, `TestMainSmokeCPU.test_cgen_smoke`/`test_cparam_smoke` (existed
before the change, asserting `ALIGN_CHECK.json`'s `PASS` is true) all passed,
verifying the acceptance requirement "the judgment is the same as before the
change when no new parameters are passed". They run with the default
parameters (`--align-rule` not passed, takes the default value `abs`), going
through exactly the newly added `abs_ok` branch, byte-for-byte identical to the
pre-change expression.

`TestRunAlignCheckHandlesRefBaselineDriftError.test_run_align_check_reports_drift_error_instead_of_crashing`
(this ticket changed its `Namespace`) also actually ran in this round, and the
output report confirmed it carries the two new keys `"rule": "abs", "rel_tol":
1e-05`, exit code still 2. Key excerpt of `ALIGN_CHECK.json`:
```
{
 "PASS": false,
 "stage": "ref_forward_drift",
 "error": "...",
 "ref_inst_ce_drift_tol": 1e-06,
 "rule": "abs",
 "rel_tol": 1e-05
}
```

**The four grep commands in the acceptance checklist** (run inside the
worktree):

```
grep -n "TOK_DIFF_TOL\|BF16_MEAN_TOL\|BF16_MAX_TOL" pipeline/train/train_causal_share.py
```
→ zero matches (exit 1).

```
grep -n "rel_max_abs_diff" pipeline/train/train_causal_share.py
```
→ 6 matches (in the computation, the judgment, writing the report, and the
failure message).

```
grep -n "hidden_scale\|rel_maxdiff_hidden" pipeline/train/train_causal_tool.py
```
→ zero matches (exit 1), no second name was introduced.

"The judgment of both scripts is the same as before the change when no new
parameters are passed". See the round-2 passing results above for the `abs`
(default) branch among the three rules in
`TestMainSmokeCPU`/`TestAlignRulesShare`/`TestAlignRulesTool`, and a manual pass
over the diff: the `abs_ok` expression is byte-for-byte identical to the
pre-change `pass_ok`, and `train_causal_tool.py`'s `abs` branch
`max(d_h, d_l) < tol` also has not had a single character changed.

This ticket did not modify `run.py`, does not touch the registry, `run.py
selfcheck` was not run.

## III. Commit list

- `f7e833f` T09: parameterize all alignment-check thresholds, add the relative
  criterion --align-rule {abs,rel,both},
  `pipeline/train/train_causal_share.py`, `pipeline/train/train_causal_tool.py`
- `ebbf4e2` T09: add tests/test_align_rules.py to test the parameterized
  alignment criteria, add the new attributes for the drift test case,
  `tests/test_align_rules.py` (new), `tests/test_share_trainer.py`

## IV. Self-check findings and open questions

- The `test_baseline_factor_zero` test case: measured on this hand-built small
  model, `max_abs_diff` is exactly `0.0` (on fp32 CPU, the old and new paths
  compute identical per-row ce for these hand-built events; floating-point
  error is not exposed at this model/data scale), so under
  `--align-baseline-factor 0`, `baseline_warn` measures `False` (`0.0 > max(0,
  1e-6)` is false). The test case handles this per the conditional branch given
  by the last sentence of ticket item 1 (only assert `baseline_warn` is true
  when the difference > 1e-6, otherwise fall back to asserting the
  `baseline_factor` key faithfully records the passed-in value); both branches
  of code are present, but this hand-built data currently only covers the
  latter branch. The branch where `baseline_warn=True` was not actually
  exercised by this batch of data. This is a scenario foreseen by the ticket
  text itself, not an omission, but is recorded here for the record.
- A check of the default-value mnemonics for the six new parameters like
  `--align-tok-tol` and of "one source per thing": confirmed that all three
  internal old-constant references in `run_align_check` have been replaced, and
  that `main()` does not open a second default-value dictionary.
- Key order of `ALIGN_CHECK.json`: Python 3.7+ dicts preserve order, all new
  keys are appended after the existing keys, `json.dumps`'s output order
  matches the order in which `dict(...)` is written in the source, which does
  not affect any existing code that reads by key name (`gates.md` only reads
  `PASS`, the writeback ticket 12 will handle the rest).
- No gap requiring `NEEDS_CONTEXT`/`BLOCKED` was found, the ticket itself has no
  ambiguity.
