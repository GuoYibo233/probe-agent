# eval-stage acceptance (spec §6.5) -- 2026-07-31

Conclusion: **PASS**. Rerunning v3's bfcl classification head with the new
`pipeline/eval/eval_tool.py` under `--legacy-splits --cached-logits` produces a
`REPLAY_REPORT.json` **byte-for-byte identical** to the old
`envs/bert_runs/bfcl_v3/REPLAY_REPORT.json` (not just the temperature /
chosen_theta / test_frozen blocks -- the whole file is identical; the `.md` is
also byte-for-byte identical). The extra causal-probe run
(`bfcl_v3_causal_qwen`) is likewise byte-for-byte identical.

Zero GPU: both runs went through `--cached-logits`, only reading the old
`logits_*.pt` for CPU post-processing; the mbert side finished in 12 seconds.

## 0. Second-round correction (2026-08-28, does not change the historical conclusion above)

This document records the acceptance result under the 2026-07-31 code state,
when the criterion was "byte-for-byte identical." Starting with the second
round (ticket 07, spec 16.2), `eval_tool.py`'s `REPLAY_REPORT.json` now writes
extra fields regardless of what `--overlong` is given: `overlong_mode` plus
four count keys (`n_oow` / `n_skipped_bounds` / `n_dropped_events` /
`n_dropped_bounds`, written as 0 when they did not occur); the cgen / cparam
reports likewise gain `overlong_mode` and their own set of counts. Rerunning
this document's commands ① and ② now no longer produces a report
byte-for-byte identical to the old artifact -- **the new criterion is "every
existing key besides these few new ones is unchanged,"** no longer requiring
the whole file to be byte-identical.

## 1. Acceptance commands

The entry point is the repo root `run.py`: the two tasks `eval-tool-mbert` /
`eval-tool-causal` both map to the two `--head` values of the same
`eval_tool.py` (`--head` and the interpreter are both fixed by the registry,
no longer written in the command). Both tasks are registered as launch-class;
`python3 run.py <task> ...` only prints the command without running it -- these
two are pure-CPU acceptance runs (`--cached-logits`), so run the printed
command as-is (printing the command still goes through the dirty-tree gate:
add `--allow-dirty` to get a print when the working tree is dirty; this is not
a bypass of run.py, it is run.py's own escape hatch).

The command given in the spec (this actual run added `--report-dir`, reason in
§4 deviation ①):

```bash
python3 run.py eval-tool-mbert --env bfcl \
  --run  /home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v3 \
  --data /home/y-guo/reproduce/new1/envs/bert_data/v3 \
  --legacy-splits --cached-logits \
  --report-dir /home/y-guo/reproduce/new1/pipeline/eval/accept_bfcl_v3
```

Warning: `bfcl_v3` is **a frozen old run whose `logits_*.pt` has no
fingerprint file** -- running the command above as-is would be blocked by the
check in §1.1. Backfill the fingerprint first, then run (method and reason in
§1.1).

The second command I added myself (the same acceptance run for the causal-head
path):

```bash
python3 run.py eval-tool-causal --env bfcl \
  --run  /home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v3_causal_qwen \
  --data /home/y-guo/reproduce/new1/envs/bert_data/v3 \
  --legacy-splits --cached-logits \
  --report-dir /home/y-guo/reproduce/new1/pipeline/eval/accept_bfcl_v3_causal
```

Warning: same as above -- this one also needs a fingerprint file backfilled
per §1.1 before running with `--cached-logits`.

Artifacts land in `pipeline/eval/accept_bfcl_v3{,_causal}/`; the old directory
was not touched by a single byte (the old `REPLAY_REPORT.json`'s md5 was the
same before and after the run, `18f948fe...`; the causal one is `1893a059...`).

### 1.1 The old frozen run's logits have no fingerprint file, so one must be backfilled first

Since 2026-08-02 (audit B9), `eval_tool.py` writes each `logits_<sp>.pt` a
matching `logits_<sp>.meta.json`, recording the fingerprint of the `best/`
weights that produced it (**the size of every weight file plus a sha1 of the
first and last 64KB, not the mtime**) along with the row count. With
`--cached-logits`, missing this file triggers `SystemExit` -- an old cache
gives no way to tell which weights it came from, and is not allowed to
impersonate one.

Both of this document's acceptance commands read logits produced **before this
mechanism existed**, so they have no `.meta.json`. Fix: swap `--cached-logits`
in the command for `--adopt-logits-fingerprint` and run it once first, **not
changing a single other argument** (`--env` / `--run` / `--data` /
`--legacy-splits` still all need to be given; `--report-dir` may or may not be
given, this run writes no report):

```bash
python3 run.py eval-tool-mbert --env bfcl \
  --run  /home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v3 \
  --data /home/y-guo/reproduce/new1/envs/bert_data/v3 \
  --legacy-splits --adopt-logits-fingerprint
```

What it does: writes a `.meta.json` for every `logits_<sp>.pt` already present
under `--run`, then **exits directly, without evaluating**. The condition for
letting it through is that the mtime of every weight file under `best/` is not
newer than these logits -- only this proves "the current weights are the ones
that produced these logits"; if the weights were updated, it reports "weights
are newer than logits" and refuses to adopt. Once backfilled, run the original
command above with `--cached-logits` for the acceptance run.

Not adopting is also an option: **drop `--cached-logits` and recompute once**
-- recomputing writes the fingerprint automatically. The cost is that these
two runs are no longer the zero-GPU 12-second acceptance runs, and the
recomputed report must still be byte-for-byte identical to the old artifact
to count.

## 2. Field-comparison checklist and per-field conclusion

The basis for judgment is the three blocks named in the spec; per-field
results below (both acceptance runs reach the same conclusion):

| field | bfcl_v3 (mbert head) | bfcl_v3_causal_qwen (causal head) |
|---|---|---|
| `temperature` | matches: 1.5218 | matches: 1.3883 |
| `chosen_theta` | matches: {"0.1": 0.725, "0.05": 0.95} | matches: {"0.1": 0.8, "0.05": 0.925} |
| `test_frozen["0.1"]` | matches: theta=0.725, n=226, coverage 0.8894, trig_acc 0.8955, earliness 0.6897, wrong_spec 0.0929, all three ci entries equal | matches: theta=0.8, n=226, coverage 0.8805, trig_acc 0.9347, earliness 0.6826, wrong_spec 0.0575, all three ci entries equal |
| `test_frozen["0.05"]` | matches: theta=0.95, n=226, coverage 0.5929, trig_acc 0.9925, earliness 0.6152, wrong_spec 0.0044, all three ci entries equal | matches: theta=0.925, n=226, coverage 0.8009, trig_acc 0.9779, earliness 0.5596, wrong_spec 0.0177, all three ci entries equal |

Fields outside the basis for judgment were also compared, all matching (so
`diff` on the whole file is empty): `env`, `theta_sweep_calB` (all 20 theta
levels' agg all equal), `stoptime_calibration_test`,
`depth_bucket_acc_test`, `prior_baseline_event_acc`, `n_events_test` (226),
`speculation_economics` (both the calB_sweep and test_frozen sections), and
the causal-head-only `probe_backbone`, `probe_cost_test`.

The bootstrap confidence intervals line up bit for bit, which shows that
`random.Random(SEED=20260729)`'s draw order also matches the old script --
this is the spot most easily thrown out of order by a code change, and it was
specifically checked.

## 3. Other new-basis smoke runs done along the way (not part of §6.5, but verified the new branch while at it)

With `--legacy-splits` turned off, the new val/test basis path, run through
with 4 events of small data on CPU:

```bash
python3 run.py eval-tool-causal --env bfcl \
  --device cpu --run /tmp/eval_smoke/run --data /tmp/eval_smoke/data \
  --report-dir /tmp/eval_smoke/rep
```

(Same as above: run.py prints the command, and this `--device cpu` smoke run
was done by running the printed command as-is; run/best is a read-only
symlink pointing at `envs/bert_runs/bfcl_v3_causal_qwen/best`; logits are
written into /tmp, the old directory was not written to.) What this path
verifies: `CausalProbe` is imported from `pipeline/train/train_causal_tool.py`
and loads the backbone + head.pt, does one forward pass per whole event to get
the boundary-position logits, fits both temperature and theta on val, freezes
test, and counts `probe_cost_test`. No GPU throughout.

## 4. Deviations and decisions made on my own (spots the spec does not cover)

1. **Added `--report-dir`** (default = `--run`, behavior unchanged). Spec §6.5
   requires "write the new report to a temporary directory, never overwrite
   the old file," but the source script hardcodes writing the report into the
   run directory; without this switch there is no way to run acceptance
   without touching the old files. No effect on the basis.
2. **Added `--device`** (default cuda). The source `eval_replay.py` hardcodes
   `dev` to "cuda"; `eval_replay_causal.py` already had `--device`. After
   merging into one script, it is exposed uniformly, needed for CPU
   acceptance runs / smoke runs.
3. **`--data` semantics fork**: under the new basis, `--data` points directly
   at `<data_out>` (spec §6.1②), but the old v3 data is `<data>/<env>/`, two
   levels deep. So under `--legacy-splits`, `--data` falls back to the old
   semantics (appending `/<env>`), the only spot like this, documented in
   `--help`.
4. **The causal head's tokenizer loads unconditionally**:
   `--cached-logits` only skips the model, not the tokenizer -- because
   `probe_cost_test` needs it to count tokens. This is **copied as-is** from
   the old `eval_replay_causal.py`'s behavior (the old script also does an
   unconditional `AutoTokenizer.from_pretrained`); the first version I wrote
   skipped it together with the cached path, which caused the report to be
   missing two fields, already fixed and rerun for acceptance.
5. **The causal head's two diagnostic fields appear only under
   `--head causal`** (`probe_backbone`, `probe_cost_test`). Spec §3.6's field
   checklist does not list them, but the old causal report has them; keeping
   them means the new and old causal reports can be reconciled byte for byte,
   and the mbert report's field set has not gained a single extra one.
6. **`.md` title**: the causal head keeps the old title
   `# Replay evaluation -- bfcl (causal probe, qwen)`, the mbert head keeps
   `# Replay evaluation -- bfcl`. Without this split, the md would not match
   byte for byte.
7. **Old field names are left unchanged everywhere** (§2.5): under the new
   basis, both temperature and theta are fit on val, but the report still
   calls them `theta_sweep_calB`, `stoptime_calibration_test`, and the line
   "no theta satisfies the constraint on calB" in the md is likewise copied
   unchanged. Downstream scripts that read by name are unaffected.
8. **Whether the acceptance artifacts go into git is undecided**: the
   `REPLAY_REPORT.json` under `pipeline/eval/accept_bfcl_v3{,_causal}/` is not
   covered by `.gitignore` (only `pipeline/data` and `pipeline/runs` are).
   Kept as acceptance evidence; whether it goes into the repo is for the main
   session to decide.
