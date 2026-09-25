# T01 report — constants, the setting files, and the read-only hook

Branch: `ticket/2026-09-17-wave1/T01`, base `cca3ca3a506cf5b2a8d990e641ec160e40e8465f`,
head `035b18868dcf1149fca81c83b93af12a7aaafca4` (see commit list below for the
per-commit shas; the head above is the fourth commit).

## What was done

All eight files the ticket named were written, plus `README.md`. Nothing else
was touched.

1. **`constants/path_datasets.yaml`** — written exactly as the ticket's
   verbatim block: the `venvs:` map (appworld/probe/vllm interpreters) and the
   `appworld:` block (home, venv, data, splits). Matches contracts 6.3.
2. **`constants/path_outputs.yaml`** — written exactly as given: `root`,
   `debug_subdir: debug`, `login_host: shiga`, and the four-host `hosts:` list
   with the errata's measured card counts (8/10/4/6, 28 total), not contracts
   6.3's illustrative 4/8/8/8.
3. **`constants/path_models.yaml`** — written exactly as given, all five
   aliases (`gpt-oss-120b`, `qwen3-0.6b-base`, `qwen3-1.7b-base`,
   `qwen3-4b-base`, `lfm2.5-350m-base`). Checked every `path` with
   `os.path.isdir`: **all five existed** on 2026-09-17 (see A4 output below),
   so nothing was dropped.
4. **`experimental_settings/debug.yaml`** — sizes-only overlay, written
   exactly as given (contracts 5.6).
5. **`experimental_settings/baseline.yaml`** — workflow `[sample, score]`,
   one named setting `gptoss_aw`, `score.baseline` left unset (`null`) on
   purpose.
6. **`experimental_settings/train_probe.yaml`** — workflow
   `[sample, build, train, eval]`, **three** named settings
   (`ctool_q06`, `cgen_q06`, `cparam_q06`) per the ticket's errata decision
   (the settings plan listed only two; a `cparam` setting is needed for the
   loader's `param_only` refusal and the cparam `--debug` walk). Floats are
   written with a decimal point (`1.0e-5`), never the bare-exponent form that
   PyYAML parses as a string.
7. **`experimental_settings/inject.yaml`** — workflow `[inject, score]`, two
   named settings (`p1e1_t080`, `no_probe_t080`), neither stating a `probe:`
   section or `models.probe` field, both referencing `train_probe/ctool_q06`
   and `train_probe/cgen_q06` and scoring against `baseline/gptoss_aw`.
8. **`.claude/hooks/settings_readonly.sh`** — the PreToolUse hook, written
   last (after all seven YAML files, so it could not block its own ticket).
   Reads the JSON payload on stdin, uses system `python3` with only the
   standard library, and:
   - blocks `Write`/`Edit`/`MultiEdit` whose `file_path` (or any
     `edits[].file_path`) has a protected tail;
   - blocks `NotebookEdit` whose `notebook_path` has a protected tail;
   - blocks `Bash` whose command text mentions a protected path **and**
     contains one of `>`, `>>`, `tee`, `sed -i`, `cp `, `mv `, `rm `,
     `truncate`, `dd `, `patch`, `chmod`, `install`;
   - allows everything else, including a plain read (`cat`, `grep`, `git
     show`) of a protected file.
   Protected tail: `experimental_settings/<anything>.yaml` (and `.yml`), and
   `models/table.yaml`. Made executable (`chmod +x`).
   `.claude/settings.json` was **not** edited, per the ticket; the arming
   snippet is reproduced at the end of this report for the main session.
9. **`README.md`** — created (did not exist yet on this branch). Added only
   this ticket's own tree lines, copied from contracts 0.2's `constants/` and
   `experimental_settings/` blocks: the group header for each directory, one
   line per file (path + one sentence), and a `read by:` line per file (no
   `venv:` line on a data file, per the ticket). Ticket 14 assembles the full
   tree; conflicts on this file at wave merge are expected and are resolved by
   keeping every ticket's lines.

### Decisions the ticket already made (errata), followed as given

- `path_outputs.yaml`'s host card counts and `login_host` use the errata's
  measured `gpu_state.md` table (8/10/4/6, `login_host: shiga`), not contracts
  6.3's illustrative numbers. Verified: `hostname` on this machine answers
  `shiga` (checked directly, matches `socket.gethostname()` in A3).
  `.claude/skills/gpu-run/references/gpu_state.md` lines 62-65 give the
  measured table (tokyo105/shiga 8x A6000, tokyo106 10x A6000, tokyo107 4x RTX
  6000 Ada, tokyo108/saitama 3x H100 NVL + 3x H200 NVL = 6 total).
- `train_probe.yaml` ships three named settings (not two), per the ticket's
  and the errata's explicit instruction.

No other decision was left to me: the ticket gave every file's content
verbatim.

## How it was verified

All commands were run from the worktree root
(`/home/y-guo/reproduce/new1-wt/2026-09-17-wave1-T01`), which is the repo root
for this branch. `external/` is git-ignored and lives only under the main
repo's checkout (`/home/y-guo/reproduce/new1/external/...`), so the four
interpreter paths in `constants/path_datasets.yaml` name that location
directly (absolute paths, as the ticket requires), and every acceptance
command below resolved them correctly from the worktree.

### A1 — all seven YAML files parse, under all four interpreters

```
$ for P in python3 \
    /home/y-guo/reproduce/new1/external/probe-env/bin/python \
    /home/y-guo/reproduce/new1/external/appworld/venv/bin/python \
    /home/y-guo/reproduce/new1/external/vllm-env/bin/python; do
    $P -c "
import glob, yaml
fs = sorted(glob.glob('constants/*.yaml') + glob.glob('experimental_settings/*.yaml'))
for f in fs: yaml.safe_load(open(f))
print(len(fs), 'parsed')"
  done
7 parsed
7 parsed
7 parsed
7 parsed
```
Exit 0 each. Matches expected.

### A2 — `path_datasets.yaml` is complete and every path it names exists

```
$ python3 -c "..."
['dev', 'test', 'train'] {'train': 90, 'dev': 57, 'test': 168}
```
Exit 0. Matches expected exactly.

### A3 — `path_outputs.yaml` keys, the login host, the inventory, and the root

```
$ python3 -c "..."
root True debug True
```
Exit 0. Matches expected exactly. This also created
`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug` on NFS
(it did not exist before this run).

### A4 — `path_models.yaml`: every alias resolves to something that is there

```
$ python3 -c "..."
gpt-oss-120b         True /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b
qwen3-0.6b-base      True /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base
qwen3-1.7b-base      True /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-1.7B-Base
qwen3-4b-base        True /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-4B-Base
lfm2.5-350m-base     True /net/tokyo100-10g/data/str01_01/y-guo/models/LFM2.5-350M-Base
```
All `True`; `gpt-oss-120b` and `qwen3-0.6b-base` both present, as required.

### A5 — the setting files are shaped the way the schema will read them

```
$ python3 -c "..."
baseline ['sample', 'score'] ['gptoss_aw']
train_probe ['sample', 'build', 'train', 'eval'] ['ctool_q06', 'cgen_q06', 'cparam_q06']
inject ['inject', 'score'] ['p1e1_t080', 'no_probe_t080']
debug {'n_tasks': 3, 'seeds': [42], 'pieces': 1, 'replicas': 1, 'max_steps': 6} {'epochs': 1, 'max_steps': 20, 'predict': {'cap': 100}}
```
Matches the expected block exactly, line for line.

### A6 — every number that must be a number is one, and every reference resolves

```
$ python3 -c "..."
references resolve, floats are floats
```
Exit 0. Matches expected.

### A7 — the hook blocks what it must and passes what it must

```
$ h=.claude/hooks/settings_readonly.sh
$ t(){ printf '%s' "$2" | $h >/dev/null 2>/tmp/hookerr; echo "$1 -> $?"; }
$ t protected-write  '{"tool_name":"Write","tool_input":{"file_path":"/home/y-guo/reproduce/new1/experimental_settings/inject.yaml","content":"x"}}'
$ t protected-edit   '{"tool_name":"Edit","tool_input":{"file_path":"experimental_settings/debug.yaml","old_string":"a","new_string":"b"}}'
$ t table-yaml       '{"tool_name":"Write","tool_input":{"file_path":"models/table.yaml","content":"x"}}'
$ t constants-ok     '{"tool_name":"Write","tool_input":{"file_path":"constants/path_models.yaml","content":"x"}}'
$ t schema-ok        '{"tool_name":"Write","tool_input":{"file_path":"experimental_settings/schema.py","content":"x"}}'
$ t bash-read-ok     '{"tool_name":"Bash","tool_input":{"command":"cat experimental_settings/debug.yaml"}}'
$ t bash-write       '{"tool_name":"Bash","tool_input":{"command":"sed -i s/a/b/ experimental_settings/debug.yaml"}}'
$ t bash-redirect    '{"tool_name":"Bash","tool_input":{"command":"echo x > models/table.yaml"}}'
$ cat /tmp/hookerr
protected-write -> 2
protected-edit -> 2
table-yaml -> 2
constants-ok -> 0
schema-ok -> 0
bash-read-ok -> 0
bash-write -> 2
bash-redirect -> 2
experimental_settings/*.yaml and models/table.yaml are the owner's files: an agent never edits them (contracts 5.1, 6.1). Propose the change as a task instead.
```
Matches expected exactly, including the refusal message text.

### `run.py selfcheck`

`run.py` does not exist yet on this branch (arrives in wave 6, ticket 15), so
this step was skipped per the implementer protocol.

## Commit list

Four commits, by logical unit, on `ticket/2026-09-17-wave1/T01`:

1. `b00d4a0` — T01: add constants/ location files (datasets, outputs, models)
2. `604283c` — T01: add experimental_settings/ workflow files (debug, baseline, train_probe, inject)
3. `138ab3f` — T01: add settings_readonly.sh PreToolUse hook
4. `035b188` — T01: add README.md tree entries for constants/ and experimental_settings/

## Snippet for the main session (arm the hook after wave 2)

Not applied by me, per the ticket ("Never edit `.claude/settings.json`"). To
arm after wave 2 (not after wave 1, since `models/table.yaml` does not exist
until ticket 06 in wave 2):

```json
{"hooks": {"PreToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash",
  "hooks": [{"type": "command",
             "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/settings_readonly.sh"}]}]}}
```

## Self-review findings and open questions

- **YAGNI check**: no file was touched beyond the ticket's list; `README.md`
  was created fresh (it did not exist on this branch) with only this ticket's
  lines, per spec section 3's "README.md is the one file two tickets of the
  same wave may both touch."
- **`constants/path_models.yaml`'s `note` fields cite `legacy/`** (e.g.
  `legacy train_causal_tool.py:86`), exactly as the ticket's verbatim block
  specifies. Spec section 5's "no citation of `legacy/` in the shipped source"
  bullet is stated under "what every Python file carries," and this is a data
  YAML file whose content the ticket dictated character for character — I
  followed the ticket's exact text rather than improvising a paraphrase, but
  flag it here since ticket 18's `C9` greps the code directories for the word
  `legacy` and this is a plain-text hit if that grep's scope includes
  `constants/`. Worth the main session's attention at wave-18 time, not mine
  to change now (the ticket's content is exact, not something I may edit).
- **`A7`'s `bash-write` and `bash-redirect` cases only "mention" a protected
  path through a substring match** (`experimental_settings/<name>.ya?ml` or
  `models/table.yaml` appearing anywhere in the command text), matching the
  ticket's "the command mentions a protected path" wording literally. This
  means a command that merely echoes or greps such a string without any of
  the listed write markers still passes (correct, tested by `bash-read-ok`),
  and a command that both mentions the string and carries a write marker
  anywhere in the line is blocked even if the marker is unrelated to that
  particular path (e.g. `cp a b && rm experimental_settings/x.yaml` — a
  conservative false-positive in the block direction, never in the pass
  direction). No acceptance case exercises this edge, so I left it as the
  simplest correct reading of the ticket's rule.
- No other decisions or open questions. All eight files' content is exact
  transcription of the ticket's verbatim blocks; all seven acceptance commands
  and the hook test passed with output identical to what the ticket expected.
- Nothing was found that belongs in another ticket.
