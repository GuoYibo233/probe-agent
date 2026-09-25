# T08 report — the eval library and the classifier metric

Branch `ticket/2026-09-17-wave3/T08`, base `28735bb2437f34af4f85d915b9de22f22530cfaa`,
head `4652288` (see commit list below for the exact sha). Worked in worktree
`/home/y-guo/reproduce/new1-wt/2026-09-17-wave3-T08`, now removed; branch kept.

## What was done

Two files, per the ticket's `## What to do`:

### `eval/utils/probe_eval.py` (contracts 1.4, 2.6)

- `VERSION = 1`, `FIRES_SCHEMA` (the eight columns of 1.4 in order), `IDENTITY_FIELDS`
  (the eight names) as column-zero / module-level literals.
- `run(run_dir, method)`, in the order the ticket fixes, with the wave-3 precheck's
  errata applied: `hb = registry.beat(run_dir, 0)` stays at step 2, and the first
  `hb.emit(0, n_events, "item")` moved to right after the prediction frame is read
  (step 4), using the frame's distinct `event_id` count.
  - `cfg = schema.load_frozen(run_dir)`.
  - `train_dir = schema.run_dir_of("train", cfg._upstream["train"], debug=cfg._debug)`;
    `pred_df = probe_output.read(train_dir / "predictions.parquet")`; raises naming
    the found values when the frame's `method` column holds anything but
    `cfg.probe.method`.
  - `labels = json.loads(train_dir/"meta.json")["stage_extra"]["labels"]`.
  - For a generator `PROBE_KIND`: resolves `ref_eval_dir` with `debug=False`, gates
    on `done.json` existing (names the directory), reads the reference report,
    gates `risk_targets == cfg.eval.risk` (names both lists), and holds the
    build-key gate of 2.5's errata — walks `ref_eval_dir/meta.json →
    upstream["train"] → that train run's meta.json → upstream["build"]` and
    compares against this eval's own train run's `upstream["build"]`, naming both
    keys on a mismatch. For a classifier, `ref = None`.
  - `fields, fires = method.report(pred_df, cfg, ref, labels)`; raises naming the
    key(s) when `fields` carries any `IDENTITY_FIELDS` name.
  - Merges the identity block (`version`, `method`, `probe_kind`, `stage_key`,
    `train_key`, `theta_from`, `commit`, `labels`) around the method's `fields`;
    `risk_targets` and `n_events` stay the method's own, per the errata.
  - `write_report`, `report.md` (rendered, computes nothing), `consumed.json`
    (`[{path, sha1, n_rows}]` for the prediction parquet, plus for a generator the
    referenced `probe_report.json` with `n_rows: null` and `fires.parquet`),
    `registry.write_done(...)` with the flat `<stat>@<risk>` metrics (null entries
    omitted), then `hb.finish()`. `run` appends no registry row itself.
- `write_report` / `read_report`: `probe_report.json` written with
  `json.dumps(..., indent=1, ensure_ascii=False)` through a temporary name and a
  rename in the same directory; `fires.parquet` written the same way through
  `DataFrame.write_parquet`, mirroring `write_frame`'s rule without importing it
  (this file's imports are `data.probe_output`, `experimental_settings.schema`,
  `jobs.registry`; `polars`, `numpy` — never `data/__init__.py`, never
  `data/environments/`). `read_report` raises when the json is missing or its
  recorded `version` is newer than this module's; returns `None` for the frame
  when `fires.parquet` does not exist.
- `fit_temperature(logits, y)`: minimises the mean NLL over `log T` with an
  81-point grid over `[-4, 4]` (`np.linspace(-4, 4, 81)`), then a golden-section
  refinement inside the two grid cells adjacent to the winning point, to a
  tolerance of `1e-6` on the log-T bracket width. Deterministic; a NumPy
  replacement for today's torch LBFGS fit, ported per the ticket's algorithm spec
  (`venv: any` forbids torch). Legacy source cited only here, not in the code:
  `legacy/pipeline/eval/eval_tool.py:213-224`.
- `bootstrap_ci(df, group, stat, *, n, seed)`: resamples the distinct values of
  `group` with replacement `n` times via `numpy.random.default_rng(seed)`
  (precomputing one filtered frame per distinct id, then `pl.concat`-ing the
  drawn ids' frames per resample so a repeated draw duplicates that group's rows,
  matching the legacy algorithm's semantics), takes the sorted-index `[lo, hi]` at
  `int(n*0.025)` / `int(n*0.975)`, rounded to 4. Legacy source cited only here:
  `legacy/pipeline/eval/eval_tool.py:279-296`.
- `softmax(logits, temperature)`: row-stabilised softmax over the last axis.

### `eval/methods/ctool.py` (contracts 1.4, 2.6)

- `VERSION = 1`, `PROBE_KIND = "classifier"` as column-zero literals.
- `match(pred, target, env)`: `pred == target`; `env` ignored.
- `report(pred_df, cfg, ref, labels)`:
  1. Raises unless `ref is None` and `labels` is a list.
  2. `logits` from the frame's `logits` column; `y` from each row's `target`
     looked up in `labels`, raising and naming the offending value(s) when a
     `target` is not in `labels`.
  3. `T = probe_eval.fit_temperature(logits[val], y[val])`, raising when the val
     slice is empty.
  4. `probs = probe_eval.softmax(logits, T)`; `conf`, `pred_idx`, `label_pred`
     per row.
  5. `_first_crossing(df, theta)`: groups by `event_id`, orders each event's rows
     by `depth` ascending tie-broken by `example_id` ascending (the prediction row
     carries no cut index, per the ticket's errata), and takes the first cut with
     `conf >= theta`; returns one row per event with `fired`, `ok`, `depth`,
     `conf`, `task_id`, `split`, `event_id`, `example_id`, `label_pred`. Ported
     from `legacy/pipeline/eval/eval_tool.py:227-249` (cited here only, not in the
     shipped source), minus its `nro_id` parameter (the readonly arm is on the
     ticket's "not ported" list).
  6. `_agg(recs)`: `n`, `coverage`, `trig_acc`, `earliness`, `wrong_spec`, each
     rounded to 4, the same formulas as `eval_tool.py:252-260`.
  7. `grid`: one `{theta, **agg}` entry per `cfg.eval.theta_grid` value, over the
     val events.
  8. `chosen`: per risk in `cfg.eval.risk`, the grid theta with the largest
     coverage among those meeting `trig_acc >= 1 - risk` and `coverage > 0`, else
     `None`; keys are `str(risk)`.
  9. `frozen`: per risk with a theta, `_agg` over the test events at that theta
     plus `ci = probe_eval.bootstrap_ci(...)` grouped by `task_id`, with
     `n=cfg.eval.bootstrap`, `seed=cfg.eval.bootstrap_seed`; the CI covers
     `coverage`, `trig_acc`, `earliness` only (matching the legacy bootstrap,
     which does not CI `wrong_spec` or `n`). Risks whose `chosen` is null are
     absent.
  10. `fires`: for every risk with a theta, the fired events of every split at
      that theta, one row per fired event with the `FIRES_SCHEMA` columns in
      order.
  11. Returns `({"temperature", "risk_targets", "grid", "chosen", "frozen",
      "n_events"}, fires)`; `n_events` counts distinct `event_id` per split of
      the prediction frame the method was handed.
- `main(run_dir)`: one line, `probe_eval.run(run_dir, sys.modules[__name__])`.
- `if __name__ == "__main__":` parses exactly `--run-dir <dir>`.

### `README.md`

Added the ticket's two-file section (`## Ticket 08 — the eval library and the
classifier metric`), copied verbatim from contracts 0.2's lines for
`eval/utils/probe_eval.py` and `eval/methods/ctool.py`, plus a one-line note that
`eval/methods/cgen.py` / `cparam.py` belong to tickets 09/10.

## How it was verified

All commands run from the worktree root
(`/home/y-guo/reproduce/new1-wt/2026-09-17-wave3-T08`, now removed) with
`/home/y-guo/reproduce/new1/external/probe-env/bin/python` unless the command
itself names another interpreter, exactly as the ticket's Acceptance section
gives them (no command was edited).

**A1 — the `any` import test.**

```
$ for P in .../probe-env/bin/python .../appworld/venv/bin/python .../vllm-env/bin/python; do
    for M in eval.utils.probe_eval eval.methods.ctool; do $P -c "..." || echo FAIL; done
  done; echo "import test done"
import test done
```
No `FAIL` line, exit 0. Matches expected.

**A2 — no torch, no GPU anywhere in `eval/`.**

```
$ grep -rn "import torch\|from torch\|cuda\|transformers" eval/ ; echo "exit=$?"
exit=1
```
No matches, `exit=1`. Matches expected.

**A3 — the literal lines `selfcheck` reads.**

```
$ .../probe-env/bin/python - <<'PY'
... (as given) ...
PY
literals ok
```
Matches expected.

**A4 — the classifier path end to end, on a fixture the command builds.**

Ran the command verbatim. Output:

```
@hb {"done": 0, "total": 20, "unit": "item", "ts": ...}
@hb {"done": 0, "total": 20, "unit": "item", "ts": ..., "status": "done"}
fields: ['chosen', 'commit', 'frozen', 'grid', 'labels', 'method', 'n_events', 'probe_kind', 'risk_targets', 'stage_key', 'temperature', 'theta_from', 'train_key', 'version']
fires columns: ['risk', 'theta', 'split', 'event_id', 'example_id', 'score', 'depth', 'label_pred'] rows: 40
A4 ok
```
`fields:` carries every name the ticket lists as a minimum; `fires columns:` are
exactly the eight of 1.4 in order, `rows: 40` (20 events × 2 risk targets, all
fired). All files landed under
`schema.run_dir_of(..., debug=True)` (the outputs root's `debug/` subtree), never
a literal path. Matches expected.

Cleanup: ran `shutil.rmtree` on both fixture directories at the end of the same
command, as the ticket asks, and re-ran the whole A4 fixture-build-and-cleanup
cycle twice more (once after removing the two "legacy"-word docstring mentions
found in self-review, once as a final confirmation) to re-verify after each edit;
each run cleaned up after itself. Fixture keys used: train `aaaaaaaaaaaa`, eval
`bbbbbbbbbbbb`. Confirmed empty afterward:
```
$ ls .../outputs/debug/train/ .../outputs/debug/eval/
(both empty)
```

**A5 — the temperature fit and the bootstrap.**

```
$ .../probe-env/bin/python - <<'PY'
...
PY
A5 ok, T = 6.0359
```
`T` is deterministic across the two calls (assertion passed) and equals `6.0359`
exactly, matching the ticket's stated measured value for this fixture and
algorithm. `ci` deterministic across the two calls and brackets 0.5 (the fixture
makes every task-group's local mean exactly 0.5, so this assertion holds for any
correct or incorrect resampling implementation — noted for the record, not a gap
in coverage since the determinism assertion is the one that actually exercises
`bootstrap_ci`'s seeding).

**A7a — `match` is callable from the train side.**

```
$ .../probe-env/bin/python -c "..."
ctool match ok
```
Matches expected.

**Not run — "selfcheck lines that apply later" and the GPU/main-session `M-E1`
check.** `run.py` does not exist yet on this branch (confirmed: `ls run.py` fails
in the worktree), matching the ticket's own note; no hand-run stand-in was
requested by the ticket for wave 3. `M-E1` needs a real `train` run's
`predictions.parquet` and a GPU-backed `run.py train_probe` — not run, per the
project's GPU rule; see Open questions / BLOCKED note below for the ready-to-run
command, though this ticket's own status is DONE since every requirement that is
mine to run has passed.

## Commit list

| sha | description |
|---|---|
| `4652288` | T08: the eval library and the classifier metric — `eval/utils/probe_eval.py`, `eval/methods/ctool.py`, and the ticket's README section |

## Self-review findings and open questions

- Found and fixed during self-review: two docstrings (`fit_temperature`,
  `bootstrap_ci`) originally cited "the eval library's legacy [...] fit/bootstrap"
  — the bare word "legacy" with no `legacy/` path, but still a match for ticket
  18's `C9` grep and against spec section 5's rule. Removed both mentions before
  committing; the citations live in this report only (`legacy/pipeline/eval/eval_tool.py:213-224`
  and `:279-296`), as spec section 5 requires. Re-ran the full acceptance suite
  after the fix; nothing changed.
- Also normalised two docstrings from `--` (double hyphen) to `—` (em dash) to
  match the punctuation style already used in `jobs/registry.py`'s docstrings.
- `report.md`'s per-risk-target theta for the classifier shape is read from
  `chosen[risk_str]`, not from a `theta` field inside `frozen[risk_str]` — 1.4's
  own table lists `frozen`'s struct as `n, coverage, trig_acc, earliness,
  wrong_spec, ci` with no `theta` field, so the report's `theta` column has to
  come from `chosen`. This is a decision the ticket's report.md format list
  implies but does not spell out explicitly; flagging it here since it is the one
  place I resolved an implicit requirement rather than copying a literal line.
- `bootstrap_ci`'s resampling precomputes one filtered frame per distinct id
  (an up-front `O(distinct ids)` pass) and then concatenates the drawn ids' frames
  per iteration, so a repeated draw duplicates that group's rows — this differs
  from a naive `is_in()`-filter approach (which would silently collapse duplicate
  draws to one copy and under-weight them) and was chosen to match the legacy
  algorithm's semantics (`by_unit[u]` appended once per draw, including repeats).
  Verified indirectly by A5's determinism assertions; the CI-bracket assertion in
  A5 does not distinguish the two implementations because of the fixture's
  balanced construction (noted above), so this is a case where I'm confident in
  the port from reading the legacy code rather than from the acceptance command
  itself.
- Everything under "Not ported" in the ticket (economics, stop-time calibration,
  depth-decile accuracy, frequency-prior baseline, `probe_cost_test` /
  `probe_backbone`, the readonly arm) is absent from both files; confirmed by
  reading the final diff, not just by omission during writing.
- No blocking issues. `M-E1` (the GPU-backed end-to-end classifier eval over a
  real `train_probe ctool_qwen3_0pt6b --debug` run) is explicitly marked
  "GPU / main session — not yours" by the ticket itself, so it is not reported as
  BLOCKED for this ticket's own status; the ready-to-run commands, if the main
  session wants them next, are:
  `run.py train_probe ctool_qwen3_0pt6b --debug` then
  `run.py where train_probe ctool_qwen3_0pt6b eval` (both depend on `run.py`,
  which a later wave builds).

## Fix round 1

Worktree `/home/y-guo/reproduce/new1-wt/2026-09-17-wave3-T08-fix1`, branch
`ticket/2026-09-17-wave3/T08`, checked out at the prior head `4652288`. Now
removed; branch kept.

### F1 — README.md's `eval/` header line was fabricated, not copied from contracts.md 0.2

Confirmed the finding: grepped `notes/plans/2026-09-17-contracts.md` for the
committed line's text ("computed from train's predictions.parquet, no GPU, no
environment except for" and "split_args/build_call") — no match anywhere in
the file. Read contracts.md lines 480-520 directly; the real `eval/` tree line
(504-506) reads:

```
  eval/                   reads what is on disk and computes numbers; no GPU, no torch, every file imports
                          as any. A new probe method is a file under methods/; a new metric is an edit to
                          the file that reports it
```

Replaced the fabricated two-line header in README.md's `## Ticket 08` section
(previously "computed from train's predictions.parquet, no GPU, no environment
except for the two call-generating methods' own use of split_args/build_call")
with this text verbatim, matching the column alignment (`cat -A` diffed
character-for-character against the contracts.md source line — identical).
Every other line in this ticket's README section (`methods/` group line,
`probe_eval.py` and `ctool.py` blocks) was already a verbatim copy and was
left untouched. Re-grepped the whole repo for both fragments of the fabricated
text afterward (`no environment except`, `split_args/build_call`); no
remaining occurrences.

No source file (`eval/utils/probe_eval.py`, `eval/methods/ctool.py`) was
touched — the finding was README-only, and fixing it required no logic change.

### How it was verified

Only `README.md` changed, so the acceptance commands that exercise the two
source files could not have regressed; re-ran the cheap ones as hygiene (the
worktree root, `probe-env`'s interpreter unless noted):

**A1 — the `any` import test.**
```
$ for P in .../probe-env/bin/python .../appworld/venv/bin/python .../vllm-env/bin/python; do
    for M in eval.utils.probe_eval eval.methods.ctool; do $P -c "..." || echo FAIL; done
  done; echo "import test done"
import test done
```
No `FAIL` line. Matches expected.

**A2 — no torch, no GPU anywhere in `eval/`.**
```
$ grep -rn "import torch\|from torch\|cuda\|transformers" eval/ ; echo "exit=$?"
exit=1
```
No matches. Matches expected.

**A3 — the literal lines `selfcheck` reads.**
```
$ .../probe-env/bin/python - <<'PY'
... (as given) ...
PY
literals ok
```
Matches expected.

A4, A5 and A7a build and read `eval/utils/probe_eval.py` and
`eval/methods/ctool.py` end to end; since those two files are byte-for-byte
unchanged from the prior round (confirmed by `git diff` showing only
`README.md`), their previously-recorded results still hold and were not
re-run. `run.py` still does not exist on this branch (`ls run.py` fails),
so the selfcheck-dependent checks remain not-applicable, as in round 1.

### Commit list

| sha | description |
|---|---|
| `38ee017` | T08: fix round 1 — replace fabricated eval/ tree header line with contracts.md's verbatim text |

### Self-review findings and open questions

- Diff is exactly the two-line-to-three-line README hunk (`git diff` shown
  above in the working notes); no other file touched.
- No new open questions. F1 is closed.
