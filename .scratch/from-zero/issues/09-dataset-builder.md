# 09 the dataset builder

Status: claimed
Blocked by: 02, 03, 04, 05
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 6, 7)

## What to do

One file: `data/build_training_dataset.py`, plus its `README.md` entry. Contracts 2.5
(every gate), 1.2 (the example row), 1.7 (the probe's input), 2.3 (the requested
pair list) and 1.5 (`consumed.json`, `done.json`) are the specification.

```
data/build_training_dataset.py   venv: any (2.1's build row; run.py starts it in place with the
                        `any` interpreter, 2.3)
  imports: experimental_settings/schema.py, data/__init__.py (the id functions),
           data/trajectory_record.py, data/training_data.py, data/probe_input.py,
           data/environments/__init__.py, jobs/registry.py; [polars, PyYAML]
  used by: none (program)
  reads:   the sample run's task records, constants/path_datasets.yaml (the splits
           block of cfg.data.env, for the split files' paths), the environment's
           split task-id files
  writes:  examples.parquet, consumed.json, report.md, heartbeat, done.json
  venv:    any
  VERSION = 1      (2.2 folds it into the build key)
README.md           your one line only
```

**Entry point** (2.6): `def main(run_dir: Path) -> None`, plus an
`if __name__ == "__main__":` block whose only flag is `--run-dir`. **No setting
name anywhere on the command line.** It calls `schema.load_frozen(run_dir)`
itself.

### The walk, in order

1. `cfg = schema.load_frozen(run_dir)`; `hb = registry.beat(run_dir, 0)`.
2. `env = open_env(cfg.data.env)`.
3. `triples = requested_pairs(env, cfg.sample.split, cfg.sample.tasks,
   cfg.sample.n_tasks, cfg.sample.seeds)`;
   `pairs = [(t, s) for _split, t, s in triples]` (2.3's projection).
4. `sample_dir = schema.run_dir_of("sample", cfg._upstream["sample"],
   debug=cfg._debug)` — the key is **read out of `_upstream`, never recomputed**
   (2.1).
5. **Completeness gate** (2.5): `done = trajectory_record.done_pairs(sample_dir,
   pairs)`; raise, naming the missing pairs, when `done` does not cover `pairs`.
   **`done_pairs` takes the run directory**; `data/trajectory_record.py` appends
   `records/` itself (errata).
6. `hb.emit(0, len(pairs), "row")`, then one beat per record read. **Decision
   already made (errata):** `build` emits one beat per **record**, with `done` and
   `total` counted in records, and keeps 8.4's word `row`, because the verdict
   functions read the word and only diff `ts` and `done`.
7. Resolve the split files: read `constants/path_datasets.yaml`, take the
   `splits:` block of `cfg.data.env` for each split's **path**; take each split's
   ids from `env.tasks(split)`. Hash each file with sha1.
8. **Split gates** (2.5): a task id that appears in two splits, and a task id of
   the records that is in none of the environment's official lists, each stop the
   build and name the ids.
9. `df = trajectory_record.read_dir(sample_dir, pairs)`.
10. **Abort gate** (2.5): the share of records whose `final.abort` is non-null
    above `cfg.build.max_abort_frac` stops the build, naming the share and the
    field.
11. Per record, join the `gen` and `env` rows on `step`. **A `gen` row with no
    `env` row raises**, naming the record and the step (1.1's gen-and-env
    pairing) — it does not break out of the trajectory.
12. Per event, in step order, with `history` accumulated across the trajectory:
    - `thinking = (gen.reasoning or "").strip()`,
      `action = (env.action or "").strip()`.
    - `action` empty -> **skip the event, count it as
      `events_skipped_no_action`, and append nothing to `history`**
      (`legacy/pipeline/annotate/build.py:81-83`; 2.5's null-action rule).
    - `env.split_args(action)` returns `None` on a non-empty action -> **skip the
      event and count it as `events_skipped_no_call`**; append `(action,
      env.result)` to `history` as for any executed step.
      **Decision already made (errata):** 2.5 states this as a hard stop that ends
      the build. Measured over the 315 p1 trajectories on 2026-09-17, **34 of
      4,074 non-null actions (0.83%) in 22 trajectories** do not parse: 24 (in 13
      trajectories) are code blocks that call no api at all — they inspect the
      namespace, parse text with `re`, or print a variable — and 10 (in 9
      trajectories) do name an api whose call never closes its parentheses for the
      paren walk `split_args` uses. So the gate as written stops every build over
      real data. The build skips and counts **both kinds** under
      `events_skipped_no_call`, exactly as it does for a null action, and
      `report.md` lists the count. This is the same reasoning 2.5 itself uses to
      demote the unseen-tool gate to a report line. Ticket 05's `B4` pins the
      matching pair: `4074 4040 4040`.
    - `len(thinking) < cfg.build.min_think` or `thinking == ""` -> skip the event,
      count it as `events_skipped_short_think`, **but append `(action,
      env.result)` to `history`** (`build.py:86,117`: the `hist.append` sits after
      the yield and outside the `if`, so a too-short step still enters the
      history).
    - otherwise: `tool, args, _span = env.split_args(action)`;
      `call = env.build_call(tool, args)`;
      `offsets = probe_input.cuts(thinking, cfg.build.min_think, cfg.build.max_cuts)`;
      one row per offset with
      `text = probe_input.assemble(task_text, history, thinking[:cut],
      cfg.build.hist_rounds, cfg.build.probe_result_cap)`,
      `depth = round(cut / len(thinking), 4)`,
      `weight = 1.0` under `uniform` and `round(1.0 / n_cuts, 6)` under
      `per_event` (`build.py:213`), and the ids from `data/__init__.py`'s
      `record_id` / `event_id` / `example_id` — **never a formatted string at the
      call site**.
    - then append `(action, env.result)` to `history`.
    **The history rule is shared with `agent/loop.py`** (errata): both append only
    when the action is not None, and the offline and live histories must be
    identical (1.7).
13. **The `split` column.** Under `split_source: env`: the record's `meta.split`
    through `env.SPLIT_ROLE` (2.5, 4.1). Under `hash`:
    `int(sha1(task_id.encode()).hexdigest()[:8], 16) / 2**32` against the
    cumulative `cfg.build.split_ratio` (5.2) — **never Python's `hash()`**.
14. **Row gates** (2.5), each stopping the build and naming the rows: the **call
    round trip** (`env.split_args(call)` must give back this row's `tool` and
    `args`); an empty `text`; a `depth` outside [0, 1]; and the thinking-prefix
    check, spelled **`row.text.endswith(thinking[:cut])`** (errata — `assemble`
    puts the thinking prefix last, and splitting `text` on the `[THINKING]`
    marker would mis-fire on an observation that contains that marker).
15. **Per-split cap**: keep the first `cfg.build.max_examples` rows of **each**
    split in `example_id` order, so the cap is a deterministic function of its
    input (2.5).
16. `training_data.write(run_dir / "examples.parquet", frame)`.
17. `consumed.json`: every record file it read, by `trajectory_record.record_path`,
    with its sha1 and row count; **and** every split file, with its path, sha1 and
    task count (2.5, 1.5).
18. `report.md` (below).
19. `registry.write_done(run_dir, stage="build", key=cfg._key,
    commit=cfg._commit, counts=<below>, versions=cfg._versions, metrics={},
    report="report.md")`, then `hb.finish()`.

**`counts` (errata, with the new entry of step 12):** `{records, events,
events_skipped_no_action, events_skipped_no_call, events_skipped_short_think,
examples, examples_train, examples_val, examples_test, tools,
tools_unseen_in_train}`. `metrics` is `{}` — 1.5 names train, eval and score as
the metric owners, and a build's numbers are counts.

**`report.md`** carries, ported in content from `build.py:462-489`: the identity
line (key, env, agent model, commit, debug); records / events / events skipped by
each of the three reasons / examples; cuts per event (min, median, max, and the
cap); per split, tasks · events · examples; the tool vocabulary (class count,
top 5, classes appearing fewer than 5 times); **the tools that appear in val or
test and never in train, listed** (2.5 demotes that gate to a report line);
examples per depth decile; `text` length p50 / p90 / max; the abort share against
`max_abort_frac`; and how many rows the per-split `max_examples` cap dropped.

### Legacy sources

| what | where |
|---|---|
| trajectory -> event | `legacy/pipeline/annotate/build.py:61-118` (the `appworld` branch only) |
| event -> sample rows | `legacy/pipeline/annotate/build.py:205-228` (`make_samples`) |
| the official-task-list split | `legacy/pipeline/annotate/build.py:303-318` (`read_unit_list`, `official_split`) and the missing-unit refusal `:367-372` |
| the report | `legacy/pipeline/annotate/build.py:442-534` |
| the call round trip, today a measurement | `legacy/pipeline/annotate/check_callstr.py:20-27, 48-51, 307-320` |
| the structural gates | `legacy/pipeline/annotate/check_callstr.py:257-305` (gates A, B, D) |

**Not ported, and none of it is recreated:** `bfcl_events`
(`build.py:120-169`) and the `tales` / `alfworld` branches of `jsonl_events`
(`:93-116`); `collect_events`' multi-directory concatenation (`:172-187`) and
`MODEL_OF` filtering (`:64,360`); `traj_files` and `scan_raw_trajs`
(`:248-298`); `router_stats.md` (`:408-433`), `qa_sample.txt` (`:436-440`) and
`tool_vocab.json` (`:404-406`); the `random.Random(seed)` sampling behind
self-checks 1 and 3 (`:337,376-402`) — both become whole-frame gates, so the
builder draws no random number and needs no seed; `make_call` (`:197-200`) and
`norm_named` (`:192-194`) — replaced by `env.build_call`, which 4.2 makes the
**inverse** of `env.split_args`; gate A (`check_callstr.py:257-265`), gate C
(`:110-120`) and gate E (`:290-305`); Deviations 2, 3 and 4
(`check_callstr.py:52-65`) as separate sections — they become `report.md` lines
and `counts` entries.

**Explicitly not ported anywhere in `data/`:**
`legacy/pipeline/train/share_data.py:583-611` (`read_position`, the
character-cut-to-token-index rule). One example row is one sequence whose `text`
ends at the cut, and the decision is taken at that sequence's last non-pad token.

## Acceptance

Run from the repo root and paste the real output. `$AW` is
`/home/y-guo/reproduce/new1/external/appworld/venv/bin/python`.

**A1 — every file in `data/` imports under all three venvs, this one included.**
```bash
for P in /home/y-guo/reproduce/new1/external/probe-env/bin/python \
         /home/y-guo/reproduce/new1/external/appworld/venv/bin/python \
         /home/y-guo/reproduce/new1/external/vllm-env/bin/python; do
  "$P" -c "import sys; sys.path.insert(0,'.');
import data, data.trajectory_record, data.training_data, data.probe_output, data.probe_input, data.build_training_dataset
print('imports ok', sys.version.split()[0])"
done
```
Expected: `imports ok 3.11.15`, `imports ok 3.12.13`, `imports ok 3.12.13`.

**A3 — one column-zero `VERSION`.**
```bash
grep -c '^VERSION = [0-9][0-9]*$' data/build_training_dataset.py
```
Expected: `1`.

**F1 — the command shape of 2.6, and no setting name on the command line.**
```bash
"$AW" -m data.build_training_dataset --help 2>&1 | head -5
"$AW" -m data.build_training_dataset --run-dir /nonexistent; echo "exit=$?"
```
Expected: the help text names `--run-dir` and **no** `--setting`, `--config`,
`--env` or `--out`; the second command exits non-zero with a message naming
`/nonexistent`.

**The fixture, written once and reused by F2 through F7.** It builds a scratch
copy of the code tree so that a variant may edit `constants/`, the split files
and, for the last two gates, the environment and probe-input files — those two
gates exist to catch a defective `data/environments/appworld.py` or
`data/probe_input.py`, so a fixture that does not touch them cannot fire them.
The scratch copy also gets its own outputs root, so nothing lands on NFS.

```bash
cat > /tmp/mkbuildfix.sh <<'SH'
set -eu
VARIANT=${1:-ok}
AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
REPO=$(pwd)
FIX=$(mktemp -d)
for d in constants experimental_settings data models jobs; do
  [ -e "$REPO/$d" ] && cp -a "$REPO/$d" "$FIX/"
done
mkdir -p "$FIX/outputs/debug" "$FIX/splits"
cd "$FIX"
"$AW" - "$VARIANT" <<'PY'
import json, pathlib, shutil, sys, yaml
sys.path.insert(0, ".")
VARIANT = sys.argv[1]
FIX = pathlib.Path(".").resolve()

# 1. a private outputs root and private copies of the three split files
po = FIX / "constants/path_outputs.yaml"
d = yaml.safe_load(po.read_text()); d["root"] = str(FIX / "outputs")
po.write_text(yaml.safe_dump(d))
pdp = FIX / "constants/path_datasets.yaml"
d = yaml.safe_load(pdp.read_text())
for s, src in list(d["appworld"]["splits"].items()):
    dst = FIX / "splits" / (s + ".txt")
    shutil.copyfile(src, dst)
    d["appworld"]["splits"][s] = str(dst)
pdp.write_text(yaml.safe_dump(d))

# 2. the two gates that need a defective repo file
if VARIANT == "bad_call":
    p = FIX / "data/environments/appworld.py"
    p.write_text(p.read_text() +
                 "\n\nAppWorld.build_call = lambda self, tool, args: tool + '()'\n")
if VARIANT == "bad_text":
    p = FIX / "data/probe_input.py"
    p.write_text(p.read_text() +
                 "\n\n_assemble_orig = assemble\n"
                 "def assemble(*a, **k):\n    return _assemble_orig(*a, **k) + '.'\n")

from experimental_settings import schema
from data import trajectory_record
from data.environments import open_env, requested_pairs
env = open_env("appworld")

SK, BK = "5a11e5a11e50", "b011db011db0"
sdir = schema.run_dir_of("sample", SK, debug=True); sdir.mkdir(parents=True, exist_ok=True)
bdir = schema.run_dir_of("build",  BK, debug=True); bdir.mkdir(parents=True, exist_ok=True)

triples = requested_pairs(env, ["train", "dev", "test"], None, 2, [42])
assert len(triples) == 6, triples

LONG  = "I will look at the supervisor profile first, then decide what to do next."
GOOD0 = "print(apis.supervisor.show_profile())"
NOAPI = "print(len('inspecting the namespace'))"
GOOD4 = "print(apis.phone.search_contacts(query='alice'))"
STEPS = [                                   # think, action, result
    (LONG, GOOD0, "{'name': 'alice'}"),                                  # 0 normal
    ("The model wrote no code block this time, so nothing ran at all.",   # 1 null action
     None, "NO_CODE_BLOCK"),
    ("I will just count the characters of that string before I go on.",   # 2 no api call
     NOAPI, "24"),
    ("Short.", GOOD0, "{'name': 'alice'}"),                               # 3 short thinking
    (LONG, GOOD4, "[{'name': 'alice'}]"),                                 # 4 normal
]
for i, (split, tid, seed) in enumerate(triples):
    w = trajectory_record.open_record(sdir, tid, seed)     # the RUN DIRECTORY
    w.row("meta", stage="sample", env="appworld", task_id=tid, seed=seed, env_seed=100,
          split=split, arm="sample", instructions="v1", task_text="Play my playlist.",
          agent_model="gpt_oss_120b", generation="{}", inject=None, commit="deadbeef",
          run_key=SK, owner_session="sample-" + SK + "-0")
    for step, (think, action, result) in enumerate(STEPS):
        w.row("gen", step=step, reasoning=think, content="```python\nx\n```",
              usage={"in": 10, "out": 20}, wall_s=1.0, n_inject=0,
              discard={"chars": 0, "tokens": 0, "events": 0})
        w.row("env", step=step, action=action, result=result, error_kind=None)
    if VARIANT == "orphan_gen" and i == 0:           # a gen row whose step has no env row
        w.row("gen", step=9, reasoning=LONG, content="x",
              usage={"in": 1, "out": 1}, wall_s=1.0, n_inject=0,
              discard={"chars": 0, "tokens": 0, "events": 0})
    aborted = (VARIANT == "abort" and i == 0)
    w.row("final", steps=len(STEPS), completed=not aborted,
          abort="context_overflow_400" if aborted else None,
          judge='{"success": true}', success=not aborted,
          tokens_in=50, tokens_out=100, wall_s=2.0, finished_at=0.0)
    w.close()

if VARIANT == "missing_record":
    trajectory_record.record_path(sdir, triples[0][1], triples[0][2]).unlink()
if VARIANT == "two_splits":                  # the dev list's first id also in train
    tr = FIX / "splits/train.txt"; dv = FIX / "splits/dev.txt"
    tr.write_text(tr.read_text().rstrip("\n") + "\n" + dv.read_text().splitlines()[0])
if VARIANT == "unknown_task":                # a recorded task id in no official list
    gone = triples[0][1]
    for s in ("train", "dev", "test"):
        p = FIX / "splits" / (s + ".txt")
        p.write_text("\n".join(l for l in p.read_text().splitlines() if l.strip() != gone))

frac = "0.0" if VARIANT == "abort" else "0.5"
cap  = "1" if VARIANT == "cap" else "null"
(bdir / "settings.yaml").write_text("""
data: {env: appworld, instructions: v1}
sample: {split: [train, dev, test], seeds: [42], tasks: null, n_tasks: 2,
         max_steps: 30, store_token_ids: false}
build: {max_cuts: 64, min_think: 40, hist_rounds: 3, probe_result_cap: 400,
        weight_mode: uniform, split_source: env, split_ratio: [0.8, 0.1, 0.1],
        max_examples: %s, max_abort_frac: %s}
_stage: build
_key: %s
_upstream: {sample: %s}
_versions: {}
_debug: true
_commit: deadbeef
_resolved: {}
""" % (cap, frac, BK, SK))
print(FIX); print(sdir); print(bdir)
PY
SH
chmod +x /tmp/mkbuildfix.sh
```

Every command below starts from the repo root and does

```bash
read -r FIX SDIR BDIR < <(bash /tmp/mkbuildfix.sh <variant> | paste -sd' ')
```

and then runs the builder **inside `$FIX`**, because that is the tree whose
`constants/` the fixture repointed.

**F2 — the end-to-end build.**
```bash
read -r FIX SDIR BDIR < <(bash /tmp/mkbuildfix.sh ok | paste -sd' ')
(cd "$FIX" && "$AW" -m data.build_training_dataset --run-dir "$BDIR"); echo "exit=$?"
ls "$BDIR"
(cd "$FIX" && "$AW" -c "
import sys; sys.path.insert(0,'.')
import data.training_data as ex
df = ex.read('$BDIR/examples.parquet')
print(df.height, sorted(set(df['split'].to_list())), list(df.columns))")
```
Expected: `exit=0`; the directory holds `examples.parquet`, `consumed.json`,
`report.md`, `done.json` and `heartbeat/0-0.jsonl`; the read prints a non-zero
row count, `['test', 'train', 'val']` (the six records are two per benchmark
split and `SPLIT_ROLE` maps `dev` to `val`), and the full declared column list of
`data/training_data.py`'s `SCHEMA` **in order**.

**F3 — each gate of 2.5 fires and names what it found.** One command per row; the
variant name is the fixture argument. Every one must exit non-zero and print the
named thing.
```bash
for V in missing_record abort orphan_gen two_splits unknown_task bad_call bad_text; do
  read -r FIX SDIR BDIR < <(bash /tmp/mkbuildfix.sh $V | paste -sd' ')
  echo "=== $V ==="
  (cd "$FIX" && "$AW" -m data.build_training_dataset --run-dir "$BDIR" > /tmp/g_$V.txt 2>&1)
  echo "exit=$?"
  tail -3 /tmp/g_$V.txt
done
```

**Why the builder's output goes to a file first.** The obvious form,
`( … | tail -3 )` followed by `echo "exit=${PIPESTATUS[0]}"`, always prints
`exit=0`: the subshell is one pipeline element, so `PIPESTATUS[0]` holds the
subshell's own status, which is the status of the last command **inside** it —
`tail`, which always succeeds. Measured on this machine 2026-09-17: the construct
prints `exit=0` even when the inner command is `false`. With the redirection the
`$?` that `echo` reads is the builder's own, so a gate that does not fire is
visible instead of being reported as a pass.

| variant | what it changes | the message must contain |
|---|---|---|
| `missing_record` | one requested (task, seed) has no record file | the missing `(task_id, seed)` pairs |
| `abort` | `build.max_abort_frac: 0.0` and one record's `final.abort` is non-null | the abort share and `max_abort_frac` |
| `orphan_gen` | a `gen` row at step 9 with no `env` row | the record id and the step index |
| `two_splits` | the dev list's first task id appended to the train list | the task id and both splits |
| `unknown_task` | one recorded task id removed from all three lists | the task id |
| `bad_call` | `AppWorld.build_call` patched to drop its arguments | the `example_id` and both sides of the round trip |
| `bad_text` | `probe_input.assemble` patched to append a `.` | the `example_id` |

Expected: seven blocks, each with a non-zero `exit=` and a message naming what
the row's right-hand column says.

**F4 — the three skip-and-count cases are skipped, not raised, and are counted.**
```bash
read -r FIX SDIR BDIR < <(bash /tmp/mkbuildfix.sh ok | paste -sd' ')
(cd "$FIX" && "$AW" -m data.build_training_dataset --run-dir "$BDIR")
(cd "$FIX" && "$AW" -c "
import sys, json; sys.path.insert(0,'.')
import data.training_data as ex
c = json.load(open('$BDIR/done.json'))['counts']
print(c['events_skipped_no_action'], c['events_skipped_no_call'],
      c['events_skipped_short_think'], c['events'], c['examples'])
df = ex.read('$BDIR/examples.parquet')
ids = set(df['event_id'].to_list())
bad = [e for e in ids if e.endswith('|s1') or e.endswith('|s2') or e.endswith('|s3')]
print('skipped events present in examples.parquet:', bad)")
```
Expected: `6 6 6 30 <n>` — one skipped step of each kind in each of the six
records, 5 steps x 6 records = 30 events (`counts.events` is every gen/env pair
seen, skipped ones included; the three skip counters are what say how many
produced no rows), and a non-zero example count — then
`skipped events present in examples.parquet: []`. The three skipped steps are
step 1 (null action), step 2 (api-less code block) and step 3 (short thinking).

**F5 — `consumed.json` names both kinds of input.**
```bash
"$AW" -c "
import json; e = json.load(open('$BDIR/consumed.json'))
paths = [x['path'] for x in e]
print(sum(1 for p in paths if p.endswith('.jsonl')), sum(1 for p in paths if not p.endswith('.jsonl')))
print(all('sha1' in x for x in e))"
```
Expected: `6 3` (six record files, three split files), then `True`.

**F6 — the per-split `max_examples` cap is deterministic.** Two independent
fixtures with `build.max_examples: 1`, built and compared.
```bash
read -r FIXA SA BA < <(bash /tmp/mkbuildfix.sh cap | paste -sd' ')
read -r FIXB SB BB < <(bash /tmp/mkbuildfix.sh cap | paste -sd' ')
(cd "$FIXA" && "$AW" -m data.build_training_dataset --run-dir "$BA")
(cd "$FIXB" && "$AW" -m data.build_training_dataset --run-dir "$BB")
(cd "$FIXA" && "$AW" -c "
import sys; sys.path.insert(0,'.')
import data.training_data as ex
a = ex.read('$BA/examples.parquet'); b = ex.read('$BB/examples.parquet')
assert a.equals(b), 'the cap is not a deterministic function of its input'
print('deterministic cap ok', a.height, sorted(a['split'].to_list()))")
```
Expected: `deterministic cap ok 3 ['test', 'train', 'val']` — one row per split,
identical across the two builds.

**F7 — the history rule matches the live side.** Step 4 follows the null-action
step 1, the api-less step 2 and the short-thinking step 3, and `hist_rounds` is
3, so its `[HISTORY]` block must hold steps 0, 2 and 3 and **never** step 1's
`NO_CODE_BLOCK`.
```bash
read -r FIX SDIR BDIR < <(bash /tmp/mkbuildfix.sh ok | paste -sd' ')
(cd "$FIX" && "$AW" -m data.build_training_dataset --run-dir "$BDIR")
(cd "$FIX" && "$AW" -c "
import sys; sys.path.insert(0,'.')
import data.training_data as ex
df = ex.read('$BDIR/examples.parquet')
row = df.filter(df['event_id'].str.ends_with('|s4')).sort('example_id').to_dicts()[0]
t = row['text']
print(repr(t))
print('no-code observation absent:', 'NO_CODE_BLOCK' not in t)
print('api-less action present:',  \"print(len('inspecting the namespace'))\" in t)
print('api-less result present:', '24' in t)")
```
Expected: the printed `text`, then `no-code observation absent: True`,
`api-less action present: True`, `api-less result present: True`. This is 1.7's
rule that the offline and the live history are the same string: `agent/loop.py`
appends to `history` only when `obs.action` is not None, and so does this file.

**Clean up**: every fixture lives under its own `mktemp -d`, writes its outputs
into `$FIX/outputs`, and touches neither the NFS outputs root nor the repo's own
`constants/`. Delete the fixture directories at the end and say in your report
how many you made.

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: this file imports under every
interpreter of the `venvs:` map (A1); one column-zero integer `VERSION` (A3); its
`README.md` annotation line against the `ast`-parsed import graph, including the
third-party list `[polars, PyYAML]` and the `constants/path_datasets.yaml` read
(errata: 0.2's own annotation lines for this file were incomplete); and no
`/home/` or `/net/` path in code.

### GPU / main session — not yours

`M-D1` a real `--debug` `sample` run's records build:
```bash
run.py train_probe ctool_qwen3_0pt6b --debug        # the walk reaches build itself
<appworld python> -c "
import sys; sys.path.insert(0,'.')
import data.training_data as ex
df = ex.read('<debug build dir>/examples.parquet')
print(df.height, df['split'].value_counts().sort('split'))"
```
must show a non-zero row count in **all three** splits (`train`, `val`, `test`) —
the failure 2.3's per-split `n_tasks` cap and 4.1's `SPLIT_ROLE` map exist to
prevent, and the one thing a fixture cannot prove.

## Comments

- 2026-09-17, wave 3 precheck (main session, before dispatch).
  - The corpus counts quoted in step 4 ("34 of 4,074", "24 ... and 10 ...",
    "`4074 4040 4040`") were measured before the wave-2 post-merge fix made
    `split_args` quote-aware. The last entry of
    `.scratch/from-zero/contract-errata.md` holds the re-measured numbers and
    wins: 4,074 non-null actions, 4,050 parsed, 4,050 round-tripped, 24 returning
    None, all 24 code blocks that call no api, in 13 of 315 trajectories. Over p1
    `counts.events_skipped_no_call` has that one kind of input; the skip-and-count
    rule itself is unchanged.
  - `build_call` raises `ValueError` (naming the tool, the key and the value) for
    a value that needs quoting and ends in an odd number of backslashes. None of
    the 5,297 argument values of the p1 corpus holds a backslash. The owner has
    not ruled on it (ticket 05's Comments): let it raise, do not route around it.
  - Known script defect, report it as it is and do not bend code to pass it:
    acceptance `F3`'s `unknown_task` variant only removes an id from the split
    lists, and the builder derives both the requested pairs and the records it
    reads from those lists, so the run stops at step 5's completeness gate and the
    unknown-task split gate is never reached by that variant.
