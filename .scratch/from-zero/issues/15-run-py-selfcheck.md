# 15 run.py selfcheck

Status: ready-for-agent
Blocked by: 13, 14
Spec: .scratch/from-zero/spec.md (sections 1, 2, 3, 4, 5, 7)

## What to do

One file, edited: `run.py`. Add the `selfcheck` subcommand (replacing ticket 14's
one-line stub) and the two parsers it needs beside `readme_entries`, which ticket
14 already wrote. Contracts 8.6 (the subcommand and its check list), 0.1 (the
annotation format and what `selfcheck` proves), 3.3 (the literal rule), 2.6 (the
`PROBE_KIND` pair) and Part 1 (`DEFAULTS` / `REQUIRED`) are the specification.

```
run.py       venv: probe    the only file this ticket may touch, besides README.md
README.md    only if a line of it is wrong — say which and why in your report
```

By this wave every one of the 34 Python files is on the branch, so **a green
`selfcheck` is the deliverable**, not an aspiration.

### The parsers

```python
def readme_entries(path) -> dict[str, dict[str, str]]   # ticket 14 wrote this; reuse it
def imports_of(path) -> set[str]                        # ast over the file, never an import
def literal_of(path, name)                              # the one column-zero assignment
```

`imports_of` parses the file with `ast` and returns the dotted module names of
every `Import` and `ImportFrom`, **including the ones inside functions** — a
heavy import moved inside `serve()` is still an import of that module and the
annotation line must carry it. `literal_of` returns
`ast.literal_eval` of the **one column-zero** assignment to `name`; more than one
match and zero matches are both failures that name the file and the count.

**Three normalisation rules the checks below depend on**, stated here because
without them check 2 can never be green:

1. **`imports_of` joins `module.name` for an `ImportFrom` only when the join is a
   repo file.** `from data import training_data` yields `data.training_data` because
   `data/training_data.py` exists; `from dataclasses import dataclass` yields
   `dataclasses`, because neither `dataclasses/dataclass.py` nor
   `dataclasses/dataclass/__init__.py` is in this repo. Without the rule a
   `from <package> import <module>` import of a repo file is invisible to the
   graph, and every `data/` and `models/` annotation line disagrees with it.
2. **`readme_entries` strips what an annotation line carries for a reader.** On an
   `imports:` or `used by:` line it drops the bracketed third-party list
   (`[polars, numpy]`) and every parenthetical after a name
   (`data/trajectory_record.py (done_pairs, is_done, owner, release)` is the file
   `data/trajectory_record.py`; `models/probe_models/<backbone>.py (by name, inside
   load())` is a by-name entry, rule 3). What is compared is the set of repo file
   paths, nothing else.
3. **A `used by:` entry that is not an `ast` edge is checked differently.** Spec
   section 3 gives two such spellings, and both are legitimate:
   - `used by: <file> (by name)` — a dynamic import. `ast` cannot see
     `importlib.import_module(f"data.environments.{name}")`, so instead of the
     graph equality, check that the named file **exists** and that it holds the
     dynamic-import call: the entry is asserted against the import target, not
     against the graph. The three files in this state today are
     `data/environments/appworld.py` (imported by
     `data/environments/__init__.py`), `models/agent_models/gptoss.py` and
     `models/probe_models/qwen.py` (imported by name inside `models.agent()` /
     `models.probe()` and inside `base.load()`).
   - `used by: none (program)` — a stage program nobody imports. Check that no
     repo file's `imports_of` names it, and that it has a `__main__` block.

   Every other `used by:` line keeps the plain equality of check 2.

**`selfcheck` never imports a repo module to inspect it.** The only place it
starts an interpreter is the per-interpreter import test at the end.

### The checks, in the contract's order (8.6)

1. The README's file list against the tree: every `.py` under `run.py`,
   `constants/`, `experimental_settings/`, `data/`, `models/`, `agent/`,
   `train/`, `eval/`, `jobs/` has an entry, and every entry names a file that
   exists. The count is **34**.
2. Every annotation line against the real import graph, parsed with `ast`: the
   `imports:` line equals `imports_of` restricted to repo files, and the
   `used by:` line equals the set of repo files whose `imports_of` names this one
   — **under the three normalisation rules above**, so an entry ending
   `(by name)` and the literal `none (program)` take their own test instead of
   the equality. A line that disagrees is a failure naming both sides.
3. Every axis literal against the files behind it (5.3):
   `schema.AXES["inject.format"]` equals `agent/inject_format.py`'s `FORMATS`
   keys; `schema.AXES["inject.arm"]` equals `agent/inject.py`'s `ARMS`;
   `schema.AXES["probe.method"]` equals the intersection of the file stems under
   `train/methods/` and `eval/methods/`; `schema.AXES["data.env"]` equals the file
   stems under `data/environments/` minus `__init__`;
   `schema.AXES["data.instructions"]` is within the union of every environment's
   `INSTRUCTIONS` keys; `sample.split` and `inject.split` are within the union of
   every environment's `SPLIT_ROLE` keys; `generation.effort` is within the union
   of every family module's `EFFORTS`.
4. One integer `VERSION` line at column zero per module the stage table names,
   and one literal apiece for `PROBE_KIND`, `STOP`, `EFFORTS`, `DEFAULT_EFFORT`,
   `DEFAULT_DATE`, `LORA_TARGETS`, `CHECKPOINT_META`, `INSTRUCTIONS` and
   `SPLIT_ROLE`.
5. A `DEFAULTS` and a `REQUIRED` literal in every format file under `data/`, with
   **every name in `REQUIRED` a declared column of that file's `SCHEMA`**
   (Part 1).
6. The two `PROBE_KIND` declarations of a method — `train/methods/<m>.py` and
   `eval/methods/<m>.py` — are equal (2.6).
7. Every family module's `DEFAULT_EFFORT` is in its own `EFFORTS`.
8. Every `models/table.yaml` row's `family` resolves to a file under
   `models/agent_models/` or `models/probe_models/` per its `role`, and its
   `result.weights` alias is present in `constants/path_models.yaml` (6.1).
9. No `/home/` or `/net/` path in code outside `constants/`.
10. Each `any` file imports under **every** interpreter of
    `constants/path_datasets.yaml`'s `venvs:` map, and each family module imports
    under the probe **and** the vllm interpreter (0.4's precondition for a new
    family). This is the one check that starts a subprocess.
11. A workflow file whose stem is one of the ten reserved subcommand names is
    refused, naming the file (errata).

Print **one line per problem** and exit 1 on any; on success print
`selfcheck: 34 python files, 0 problems` and exit 0. Shape ported from
`legacy/run.py:1172-1267` (count, one line per problem, exit 1 on any).

## Acceptance

Run from the repo root and paste the real output. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**D2 — selfcheck's parsers, on fixtures the command writes.**
```bash
"$PR" -c "
import sys, pathlib, tempfile; sys.path.insert(0,'.')
import run
d = pathlib.Path(tempfile.mkdtemp()); f = d/'m.py'
f.write_text('VERSION = 3\nimport os\nfrom data import training_data\nclass A:\n    VERSION = VERSION\n')
print(run.literal_of(f, 'VERSION'))
print(sorted(run.imports_of(f)))
g = d/'bad.py'; g.write_text('VERSION = 1\nVERSION = 2\n')
try:
    print('two matches ->', run.literal_of(g, 'VERSION'))
except SystemExit as e:
    print('two matches -> refused:', 'bad.py' in str(e))"
```
Expected: `3`; `['data.training_data', 'os']`; then a refusal naming the file for the
two-match case (or a `None` plus a printed problem, whichever the implementation
uses — more than one match **is** a failure). `data.training_data` and not
`['data', 'os']` is rule 1 above: the join is taken because `data/training_data.py` is
a repo file. Run the same command with `from dataclasses import dataclass` in the
fixture and paste that too — it must print `['dataclasses', 'os']`.

**D3 — the whole-tree selfcheck.**
```bash
"$PR" run.py selfcheck; echo "rc=$?"
```
Expected: `selfcheck: 34 python files, 0 problems` and `rc=0`.

**D4 — each check actually fires.** For each of the eleven checks above, break one
thing in a **scratch copy of the tree** (never in the worktree's own files —
copy the tree to a temp directory, break it there, and run `selfcheck` with that
directory as the working directory), confirm `selfcheck` names it and exits 1,
then restore. Paste one line per check: the check number, what you broke, and the
message `selfcheck` printed. The eleven breakages:

| # | break |
|---|---|
| 1 | delete one `.py` line from `README.md` |
| 2 | add `import jobs.registry` to `models/probe_models/base.py` |
| 3 | add a sixth key to `agent/inject_format.py`'s `FORMATS` |
| 4 | add a second column-zero `VERSION` to `data/training_data.py` |
| 5 | add a name to `data/probe_output.py`'s `REQUIRED` that its `SCHEMA` does not declare |
| 6 | change `eval/methods/cgen.py`'s `PROBE_KIND` to `"classifier"` |
| 7 | change `models/agent_models/gptoss.py`'s `DEFAULT_EFFORT` to `"ultra"` |
| 8 | delete one alias block from `constants/path_models.yaml`, so a `models/table.yaml` row's `result.weights` no longer resolves |
| 9 | put a literal `/net/tokyo100-10g/...` path in `eval/score_run.py` |
| 10 | add `import torch` at module level to `eval/utils/probe_eval.py` |
| 11 | `touch <scratch>/experimental_settings/free.yaml` — **undone by deleting the whole scratch copy** (`rm -rf "$S"`) and re-copying the tree, never by removing the single file: the hook's Bash rule blocks any command naming `experimental_settings/<anything>.yaml` together with `rm `, so the obvious undo exits 2 |

**The read-only hook is armed by this wave, and it matches on the path's tail.**
`.claude/hooks/settings_readonly.sh` refuses a `Write`/`Edit` whose path ends in
`experimental_settings/<anything>.yaml` or `models/table.yaml`, and a `Bash`
command that names such a path together with `>`, `>>`, `tee`, `sed -i`, `cp `,
`mv `, `rm `, `truncate`, `dd `, `patch`, `chmod` or `install`. **Copying the tree
to a temp directory does not escape it**, because only the tail is matched. That
is why breakage 8 works on `constants/path_models.yaml` — the other side of the
same check 8, and `constants/` is not protected — and why breakage 11 uses
`touch`, which is not one of the blocked verbs and is all check 11 needs (it
reads the file's **stem**, not its contents). Do not look for a way around the
hook for the two protected files: there is no breakage in this list that needs
one.

**D5 — `--help` lists ten subcommands, `selfcheck` among them.**
```bash
"$PR" run.py --help
```
Expected: the usage block naming
`free, ls, where, find, kill, refire, retry, table, sync, selfcheck` and the walk
form.

**D6 — `where` answers for every stage of every workflow, real and debug.**
Ticket 14 could run this only over `baseline` and over `train_probe`'s `sample`
and `build`, because `train/` had not merged in wave 5 and a `train`, `eval` or
`inject` key reads `train/utils/trainer.py`'s and `train/methods/<m>.py`'s
`VERSION` lines. Wave 6 has them, so the full sweep lands here.
```bash
set -e
for a in "baseline gpt_oss_120b_appworld sample" "baseline gpt_oss_120b_appworld score" \
         "train_probe ctool_qwen3_0pt6b sample" "train_probe ctool_qwen3_0pt6b build" \
         "train_probe ctool_qwen3_0pt6b train"  "train_probe ctool_qwen3_0pt6b eval" \
         "train_probe cgen_qwen3_0pt6b train"   "train_probe cgen_qwen3_0pt6b eval" \
         "train_probe cparam_qwen3_0pt6b train" "train_probe cparam_qwen3_0pt6b eval" \
         "inject probe_p1_e1_theta_0pt80 inject"      "inject probe_p1_e1_theta_0pt80 score" \
         "inject no_probe_p1_e1_theta_0pt80 inject"  "inject no_probe_p1_e1_theta_0pt80 score"; do
  "$PR" run.py where $a
  "$PR" run.py where $a --debug
done
echo "D6 ok"
```
Expected: twenty-eight absolute paths of the shape `<root>/<stage>/<12 hex>` and
`<root>/debug/<stage>/<12 hex>`, printed whether or not the directories exist;
`D6 ok`, exit 0. No command here launches anything or creates a directory.

**D7 — every named setting of all three workflow files loads, keys and freezes
under `--debug` and without it.** Ticket 14's `C6`, unrestricted.
```bash
"$PR" - <<'PY'
import pathlib, yaml
from experimental_settings import schema
for f in ["baseline.yaml", "train_probe.yaml", "inject.yaml"]:
    p = pathlib.Path("experimental_settings") / f
    doc = yaml.safe_load(p.read_text())
    stages = doc["workflow"]
    names = [k for k in doc if k not in ("workflow", "common")]
    for name in names:
        for dbg in (False, True):
            for cfg in schema.load(p, name, debug=dbg, overrides={}):
                keys = {s: schema.key(s, cfg) for s in stages}
                dirs = {s: schema.run_dir(s, cfg) for s in stages}
                assert cfg._workflow == stages, (f, name, cfg._workflow)
                for s in stages:
                    assert len(keys[s]) == 12, (f, name, s, keys[s])
                    assert dirs[s].name == keys[s], (f, name, s)
                    assert ("/debug/" in str(dirs[s])) == dbg, (f, name, s, dbg)
                print(f, name, "debug" if dbg else "real",
                      " ".join(f"{s}={keys[s]}" for s in stages))
print("D7 ok")
PY
```
Expected: one line per (file, setting, debug/real) naming a 12-hex key per stage,
then `D7 ok`, exit 0. The `inject` settings need their references to resolve; a
reference resolves to a **key**, not to a directory, so the loader must key them
whether or not any upstream run exists — report it if it does not.

### GPU / main session — not yours

None in this ticket. After this wave merges, the main session runs the GPU list
of the construction plan's section 2 and the three end-to-end `--debug` walks of
its section 4, whose run keys ticket 18's TIMELINE entry quotes.

## Comments

- 2026-09-18, from gyb (errata "3.3 / 8.6 (what a `VERSION` bump invalidates)"): selfcheck enforces the strict shape the key path leaves lenient. For every file with a column-zero `VERSION`: the VERSION rule comment block sits directly above it with the pinned text; `VERSION_HISTORY` exists at column zero exactly once and is a plain literal; its keys are exactly 2..`VERSION`; every entry has a non-empty `why`; every `stale` value is a tuple of stage names of `schema.STAGES`. A file at `VERSION = 1` has `VERSION_HISTORY = {}`.
