# 01 constants, the setting files, and the read-only hook

Status: claimed
Blocked by: (none)
Spec: .scratch/from-zero/spec.md (sections 1, 2, 4, 7, 9)

## What to do

Eight data files and one shell script. No Python. Nothing in the repo is imported
and nothing is run that needs a card.

Files you may touch, and nothing else:

```
constants/path_datasets.yaml        data file, parsed by every interpreter
constants/path_outputs.yaml         data file
constants/path_models.yaml          data file
experimental_settings/debug.yaml    data file
experimental_settings/baseline.yaml data file
experimental_settings/train_probe.yaml
experimental_settings/inject.yaml
.claude/hooks/settings_readonly.sh  shell, run by the Claude Code harness with system python3
README.md                           your own files' lines only
```

### 1. `constants/path_datasets.yaml` (contracts 6.3)

Where each environment lives, plus the `venvs:` map — the one place an
interpreter path is written down. Write exactly this:

```yaml
# Where things are on this cluster. Locations only: nothing here changes a
# result or enters a key (contracts 6.3). A path changes only when the same
# bytes move; new bytes are a new alias.

venvs:                                  # every interpreter this repo starts a program with
  appworld: /home/y-guo/reproduce/new1/external/appworld/venv/bin/python
  probe:    /home/y-guo/reproduce/new1/external/probe-env/bin/python
  vllm:     /home/y-guo/reproduce/new1/external/vllm-env/bin/python

appworld:
  home:  /home/y-guo/reproduce/new1/external/appworld
  venv:  appworld                       # a key of venvs:
  data:  /home/y-guo/reproduce/new1/external/appworld/data
  splits:
    train: /home/y-guo/reproduce/new1/external/appworld/data/datasets/train.txt
    dev:   /home/y-guo/reproduce/new1/external/appworld/data/datasets/dev.txt
    test:  /home/y-guo/reproduce/new1/external/appworld/data/datasets/test_normal.txt
```

The three split files hold 90, 57 and 168 task ids, one per line, no trailing
newline. `test_challenge.txt` (417 ids) is deliberately not a split: today's line
uses `test_normal` as `test` (`legacy/pipeline/configs/p1_gptoss.json:10-14`).

Legacy sources: `legacy/run.py:63-75` (the `PY` interpreter map),
`legacy/envs/collect/run_appworld.py:149` (the hardcoded AppWorld home),
`legacy/pipeline/configs/p1_gptoss.json:10-14` (`official_split_files`),
`legacy/pipeline/annotate/build.py:303-306` (the one-id-per-line rule).

Not ported: the other seven interpreters of the `PY` map (`mbert`, `alfworld`,
`tales`, `tau2`, `toolhop`, `stbserver`, `bash`) and every non-AppWorld
environment block; the per-batch keys of the old pipeline configs (`traj_runs`,
`data_out`, `run_family`, `model_short`, `split_mode`, `seed`, `trajs_per_unit`,
`max_bounds`) — those are setting fields, not locations.

### 2. `constants/path_outputs.yaml` (contracts 6.3)

```yaml
# The outputs root, the debug subdirectory, the login machine and the cluster
# inventory. Locations only; nothing here enters a key (contracts 6.3).

root: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs
debug_subdir: debug
login_host: shiga          # what `hostname` answers on the machine this repo is typed on
hosts:
  - {name: tokyo105, alias: shiga,   cards: 8}
  - {name: tokyo106, cards: 10}
  - {name: tokyo107, cards: 4}
  - {name: tokyo108, alias: saitama, cards: 6}
```

**Decision already made (errata):** the card counts are the measured table of
`.claude/skills/gpu-run/references/gpu_state.md` (tokyo105/shiga 8x RTX A6000,
tokyo106 10x RTX A6000, tokyo107 4x RTX 6000 Ada, tokyo108/saitama 3x H100 NVL +
3x H200 NVL), 28 in total — not contracts 6.3's illustrative 4/8/8/8.
`login_host` is `shiga`, the value `hostname` returns on this machine, which is
`tokyo105`'s alias in the same list.

Legacy sources: `legacy/ops/gpu_jobs.py:124` (`DEFAULT_HOSTS`),
`legacy/ops/launch_common.py:41` (`ALIAS = {"shiga": "tokyo105", "saitama":
"tokyo108"}`), the NFS root in `legacy/pipeline/configs/*.json`'s `data_out`.

Not ported: the `outputs` symlink at the repo root; the per-batch `data_out`
paths; `launch_common.local_host()`'s normalisation, which is `jobs/`'s business.

### 3. `constants/path_models.yaml` (contracts 6.3)

One block per alias, `alias -> {path, note}`. `path` is an absolute directory or
a hub id; `note` says where the copy came from and when it was checked.

```yaml
# Weights alias -> where the weights are. A new set of weights is a new alias
# here plus a row in models/table.yaml (contracts 6.1, 6.3).

gpt-oss-120b:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b
  note: own replica, accepted 2026-07-28 (15 shards + tokenizer, ~61G); MoE, fits one H200
qwen3-0.6b-base:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base
  note: own replica, 1.2G; the probe backbone of the cgen/ctool line since 2026-08-20
qwen3-1.7b-base:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-1.7B-Base
  note: own replica; the 1.7B tier of the three-tier backbone sweep (legacy train_causal_tool.py:86)
qwen3-4b-base:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-4B-Base
  note: own replica; the 4B tier of the same sweep (legacy train_causal_tool.py:87)
lfm2.5-350m-base:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/LFM2.5-350M-Base
  note: own replica, 681M; used by the cgen cell, registered 2026-08-20
```

Check each `path` with `os.path.isdir` and **drop any row whose directory is
gone**, listing what you dropped in your report. All five existed on 2026-09-17.

Legacy sources: `legacy/configs/models.json` (the whole `models:` block with its
notes), `legacy/pipeline/train/train_causal_tool.py:84-88` (the three Qwen
paths), `legacy/model_registry.py:15-31` (the reader).

Not ported: `models.json`'s `aliases:` block (an alias of an alias — 6.3 gives
this file one level); `modernbert-base` and `mirrorapi-cache` (retired lines).

### 4. `experimental_settings/debug.yaml` (contracts 5.6)

Sizes only. No `workflow:` line and no named settings: it is an overlay.

```yaml
# Sizes only -- never a model and never a tuning, so a --debug run exercises the
# real code path (contracts 5.6). Every field here exists in the schema, and the
# overlay applies only the sections this setting's workflow: line names.
sample:  {n_tasks: 3, seeds: [42], pieces: 1, replicas: 1, max_steps: 6}
build:   {max_cuts: 8, max_examples: 64}
train:   {epochs: 1, max_steps: 20, predict: {cap: 100}}
inject:  {n_tasks: 3, seeds: [42], pieces: 1, max_steps: 6}
eval:    {bootstrap: 50}
```

### 5. `experimental_settings/baseline.yaml`

```yaml
# Workflow: collect trajectories with the agent model alone, then score them.
# A new experiment is a new named setting in this file (contracts 5.1).
workflow: [sample, score]

common:
  data:   {env: appworld, instructions: v1}
  models: {agent: gptoss120b}

gptoss_aw:
  meta:   {notes: "AppWorld trajectories from gpt-oss-120b with no probe; the baseline an inject run is scored against"}
  sample: {split: [train, dev, test], seeds: [42], pieces: 6, replicas: 1}
  score:  {by_seed: true}
```

`score.baseline` is left unset on purpose: `null` means "report this run's own
numbers only", which is what a baseline file needs (5.2).

### 6. `experimental_settings/train_probe.yaml`

**Decision already made (errata):** this file ships **three** named settings, not
the two the settings plan listed — the loader's `param_only` refusal and the
cparam `--debug` walk both need a cparam setting.

```yaml
# Workflow: collect, build the dataset, train a probe, evaluate it.
workflow: [sample, build, train, eval]

common:
  data:   {env: appworld, instructions: v1}
  models: {agent: gptoss120b}
  sample: {split: [train, dev, test], seeds: [42], pieces: 6, replicas: 1}

ctool_q06:
  meta:   {notes: "classification probe, Qwen3-0.6B-Base, full tuning; the theta source for the generating probes"}
  models: {probe: qwen06}
  probe:  {method: ctool, tuning: full}
  train:  {lr: 1.0e-5, epochs: 1}
  eval:   {risk: [0.10, 0.05]}

cgen_q06:
  meta:   {notes: "whole-call generating probe on the same dataset; theta is frozen by ctool_q06"}
  models: {probe: qwen06}
  probe:  {method: cgen, tuning: full}
  train:  {lr: 1.0e-5, epochs: 1}
  eval:   {theta_from: train_probe/ctool_q06}

cparam_q06:
  meta:   {notes: "argument-generating probe on the same dataset; param_only, so it can never be an inject.probe_gen"}
  models: {probe: qwen06}
  probe:  {method: cparam, tuning: full}
  train:  {lr: 1.0e-5, epochs: 1}
  eval:   {theta_from: train_probe/ctool_q06}
```

All three take the same `sample` and `build` fields, so their train runs share a
`_upstream["build"]` key — the gate of 2.5 that `eval.theta_from` and an inject
run's two references both depend on. **Floats carry a decimal point**
(`1.0e-5`, never `1e-5`): PyYAML parses the second as a **string** (measured
2026-09-17 on 5.4.1 and 6.0.3), and the loader's type check is what catches it.

### 7. `experimental_settings/inject.yaml`

```yaml
# Workflow: run the agent live with the probe, then score against a baseline.
workflow: [inject, score]

common:
  data:   {env: appworld, instructions: v1}
  models: {agent: gptoss120b}

p1e1_t080:
  meta:  {notes: "live run: fire at theta 0.80, injection format p1_e1, probe arm"}
  inject:
    split: [test]
    seeds: [42]
    theta: 0.80
    arm: probe
    format: p1_e1
    probe_score: train_probe/ctool_q06
    probe_gen: train_probe/cgen_q06
    pieces: 6
    replicas: 1
  score: {baseline: baseline/gptoss_aw}

no_probe_t080:
  meta:  {notes: "control arm: the machinery wired and never firing"}
  inject:
    split: [test]
    seeds: [42]
    theta: 0.80
    arm: no_probe
    format: p1_e1
    probe_score: train_probe/ctool_q06
    probe_gen: train_probe/cgen_q06
    pieces: 6
    replicas: 1
  score: {baseline: baseline/gptoss_aw}
```

Neither setting states a `probe:` section or a `models.probe` field — the loader
refuses both for a workflow containing `inject` (2.1, 5.7) — and neither states
the inherited `build` fields, which `freeze` writes (5.4). The baseline's
`sample.split` `[train, dev, test]` is a superset of `inject.split` `[test]` and
its seeds are a superset, which is 5.7's baseline refusal.

### 8. `.claude/hooks/settings_readonly.sh`

The PreToolUse hook that refuses any agent edit to `experimental_settings/*.yaml`
and to `models/table.yaml` (the tree's own line; contracts 6.1 answers the
owner's open question with **yes, the table is covered**).

- Reads the PreToolUse JSON payload on stdin (`tool_name`, `tool_input`). Its
  inline check uses system `python3` (3.10, standard library only).
- Protected paths, matched on the path's **tail** so an absolute, a relative and
  a worktree path all match: `experimental_settings/<anything>.yaml` (and
  `.yml`), and `models/table.yaml`.
- `Write`, `Edit`, `MultiEdit`, `NotebookEdit`: block when `tool_input.file_path`
  (or any `edits[].file_path`, or `notebook_path`) is protected.
- `Bash`: block when the command mentions a protected path **and** contains any
  of `>`, `>>`, `tee`, `sed -i`, `cp `, `mv `, `rm `, `truncate`, `dd `, `patch`,
  `chmod`, `install`. A read (`cat`, `head`, `grep`, `git show`) passes.
- Block = exit code **2** with the message on stderr; everything else exits 0.
  The message is exactly:
  `experimental_settings/*.yaml and models/table.yaml are the owner's files: an agent never edits them (contracts 5.1, 6.1). Propose the change as a task instead.`
- The script never writes a file and never calls the network. Make it executable.

**Write the hook last, after the seven YAML files**, so it cannot block its own
ticket. **Do not edit `.claude/settings.json`**: an agent does not change its own
harness configuration. Put this snippet in your report instead; the main session
installs it (contracts 0.2's tree line for the hook leaves it unarmed):

```json
{"hooks": {"PreToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash",
  "hooks": [{"type": "command",
             "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/settings_readonly.sh"}]}]}}
```

### 9. `README.md`

Add one entry per data file you wrote: the path, one sentence, and a `read by:`
line naming the files that read it (contracts 0.2's `constants/` and
`experimental_settings/` blocks). A data file's entry has no `venv:` line.

## Acceptance

Run every command from the repo root and paste its real output.

**A1 — all seven YAML files parse, under all four interpreters.**

```bash
for P in python3 \
  /home/y-guo/reproduce/new1/external/probe-env/bin/python \
  /home/y-guo/reproduce/new1/external/appworld/venv/bin/python \
  /home/y-guo/reproduce/new1/external/vllm-env/bin/python; do
  $P -c "
import glob, yaml
fs = sorted(glob.glob('constants/*.yaml') + glob.glob('experimental_settings/*.yaml'))
for f in fs: yaml.safe_load(open(f))
print(len(fs), 'parsed')"
done
```
Expected: `7 parsed` four times, exit 0 each.

**A2 — `path_datasets.yaml` is complete and every path it names exists.**

```bash
python3 -c "
import os, yaml
d = yaml.safe_load(open('constants/path_datasets.yaml'))
assert set(d['venvs']) == {'appworld','probe','vllm'}, d['venvs']
for k, p in d['venvs'].items(): assert os.access(p, os.X_OK), (k, p)
aw = d['appworld']
assert set(aw) == {'home','venv','data','splits'}, sorted(aw)
assert aw['venv'] in d['venvs']
assert os.path.isdir(aw['home']) and os.path.isdir(aw['data'])
n = {}
for s, f in aw['splits'].items():
    n[s] = len([l for l in open(f).read().split(chr(10)) if l.strip()])
print(sorted(aw['splits']), n)"
```
Expected: `['dev', 'test', 'train'] {'train': 90, 'dev': 57, 'test': 168}`, exit 0.

**A3 — `path_outputs.yaml` keys, the login host, the inventory, and the root.**

```bash
python3 -c "
import os, socket, yaml
d = yaml.safe_load(open('constants/path_outputs.yaml'))
assert set(d) == {'root','debug_subdir','login_host','hosts'}, sorted(d)
assert d['debug_subdir'] == 'debug'
assert d['login_host'] == socket.gethostname(), (d['login_host'], socket.gethostname())
assert [h['name'] for h in d['hosts']] == ['tokyo105','tokyo106','tokyo107','tokyo108']
assert [h['cards'] for h in d['hosts']] == [8, 10, 4, 6]
assert sum(h['cards'] for h in d['hosts']) == 28
assert {h['name']: h.get('alias') for h in d['hosts']}['tokyo105'] == 'shiga'
assert {h['name']: h.get('alias') for h in d['hosts']}['tokyo108'] == 'saitama'
os.makedirs(os.path.join(d['root'], d['debug_subdir']), exist_ok=True)
print('root', os.path.isdir(d['root']), 'debug', os.path.isdir(os.path.join(d['root'], d['debug_subdir'])))"
```
Expected: `root True debug True`, exit 0. This command also creates the outputs
root on NFS; it did not exist on 2026-09-17.

**A4 — `path_models.yaml`: every alias resolves to something that is there.**

```bash
python3 -c "
import os, yaml
d = yaml.safe_load(open('constants/path_models.yaml'))
for a, r in d.items():
    assert set(r) == {'path','note'}, (a, sorted(r))
    ok = os.path.isdir(r['path']) if r['path'].startswith('/') else True
    print(f'{a:20s} {ok} {r[\"path\"]}')
    assert ok, a"
```
Expected: one line per alias, every one `True`; at least `gpt-oss-120b` and
`qwen3-0.6b-base` present.

**A5 — the setting files are shaped the way the schema will read them.**

```bash
python3 -c "
import yaml
STAGE_OF = {'sample':'sample','build':'build','probe':'train','train':'train',
            'eval':'eval','inject':'inject','score':'score'}
FREE = {'meta','data','models','generation'}
for f, wf in [('baseline',['sample','score']),
              ('train_probe',['sample','build','train','eval']),
              ('inject',['inject','score'])]:
    d = yaml.safe_load(open(f'experimental_settings/{f}.yaml'))
    assert d['workflow'] == wf, (f, d['workflow'])
    names = [k for k in d if k not in ('workflow','common')]
    for n in names + (['common'] if 'common' in d else []):
        for sec in d[n]:
            assert sec in FREE or STAGE_OF[sec] in wf, (f, n, sec)
    print(f, wf, names)
dbg = yaml.safe_load(open('experimental_settings/debug.yaml'))
assert set(dbg) == {'sample','build','train','eval','inject'}, sorted(dbg)
assert 'workflow' not in dbg
print('debug', dbg['sample'], dbg['train'])"
```
Expected exactly:
```
baseline ['sample', 'score'] ['gptoss_aw']
train_probe ['sample', 'build', 'train', 'eval'] ['ctool_q06', 'cgen_q06', 'cparam_q06']
inject ['inject', 'score'] ['p1e1_t080', 'no_probe_t080']
debug {'n_tasks': 3, 'seeds': [42], 'pieces': 1, 'replicas': 1, 'max_steps': 6} {'epochs': 1, 'max_steps': 20, 'predict': {'cap': 100}}
```

**A6 — every number that must be a number is one, and every reference resolves.**

```bash
python3 -c "
import yaml
tp = yaml.safe_load(open('experimental_settings/train_probe.yaml'))
for n in ('ctool_q06','cgen_q06','cparam_q06'):
    assert isinstance(tp[n]['train']['lr'], float), (n, type(tp[n]['train']['lr']))
for n in ('cgen_q06','cparam_q06'):
    f, name = tp[n]['eval']['theta_from'].split('/')
    assert name in yaml.safe_load(open(f'experimental_settings/{f}.yaml')), n
inj = yaml.safe_load(open('experimental_settings/inject.yaml'))
for n, s in inj.items():
    if n in ('workflow','common'): continue
    assert isinstance(s['inject']['theta'], float), (n, s['inject']['theta'])
    for fld in ('probe_score','probe_gen'):
        f, name = s['inject'][fld].split('/')
        assert name in yaml.safe_load(open(f'experimental_settings/{f}.yaml')), (n, fld)
    f, name = s['score']['baseline'].split('/')
    assert name in yaml.safe_load(open(f'experimental_settings/{f}.yaml'))
    assert 'probe' not in s and 'probe' not in (s.get('models') or {})
print('references resolve, floats are floats')"
```
Expected: `references resolve, floats are floats`, exit 0.

**A7 — the hook blocks what it must and passes what it must.**

```bash
h=.claude/hooks/settings_readonly.sh
t(){ printf '%s' "$2" | $h >/dev/null 2>/tmp/hookerr; echo "$1 -> $?"; }
t protected-write  '{"tool_name":"Write","tool_input":{"file_path":"/home/y-guo/reproduce/new1/experimental_settings/inject.yaml","content":"x"}}'
t protected-edit   '{"tool_name":"Edit","tool_input":{"file_path":"experimental_settings/debug.yaml","old_string":"a","new_string":"b"}}'
t table-yaml       '{"tool_name":"Write","tool_input":{"file_path":"models/table.yaml","content":"x"}}'
t constants-ok     '{"tool_name":"Write","tool_input":{"file_path":"constants/path_models.yaml","content":"x"}}'
t schema-ok        '{"tool_name":"Write","tool_input":{"file_path":"experimental_settings/schema.py","content":"x"}}'
t bash-read-ok     '{"tool_name":"Bash","tool_input":{"command":"cat experimental_settings/debug.yaml"}}'
t bash-write       '{"tool_name":"Bash","tool_input":{"command":"sed -i s/a/b/ experimental_settings/debug.yaml"}}'
t bash-redirect    '{"tool_name":"Bash","tool_input":{"command":"echo x > models/table.yaml"}}'
cat /tmp/hookerr
```
Expected exactly:
```
protected-write -> 2
protected-edit -> 2
table-yaml -> 2
constants-ok -> 0
schema-ok -> 0
bash-read-ok -> 0
bash-write -> 2
bash-redirect -> 2
```
and the last `cat` printing the refusal message naming the two protected paths.

### Selfcheck lines that apply later

`run.py selfcheck` arrives in wave 6 (ticket 15). Over these files it will check:
every alias in `models/table.yaml` has a row in `constants/path_models.yaml`
(6.1); every axis literal of `experimental_settings/schema.py` matches what is on
disk (5.3); each `any` file imports under every interpreter of the `venvs:` map
(0.1, 6.3). A1-A4 are the hand-run stand-ins until then.

### GPU / main session — not yours

- Arm the hook: merge the snippet above into `.claude/settings.json`, then
  attempt a real edit to `experimental_settings/debug.yaml` and confirm the
  refusal comes through the harness.
- `M-G1` the hosts inventory:
  `for h in tokyo105 tokyo106 tokyo107 tokyo108; do printf '%s ' $h; ssh -o BatchMode=yes $h 'hostname; nvidia-smi -L | wc -l' | tr '\n' ' '; echo; done`
  must show tokyo105 answering `shiga` with 8 cards, tokyo106 10, tokyo107 4,
  tokyo108 answering `saitama` with 6.
- `M-G2` the outputs root writable from a compute host:
  `ssh -o BatchMode=yes tokyo106 'd=/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug; touch $d/.probe_from_tokyo106 && ls -l $d/.probe_from_tokyo106 && rm $d/.probe_from_tokyo106 && echo WRITABLE'`
  must print `WRITABLE`.

## Comments
