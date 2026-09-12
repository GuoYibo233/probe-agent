# spec: generation settings into config files (gen-preset)

Status: ready-for-agent
Date: 2026-08-20. Decided by gyb, both key choices picked option a: move the model
table into config files; vLLM launch also reads from config. The goal is "py files
keep only logic, models and settings go into config, so later we can pick from many
sets of settings by name."

## Current state (before the change)

gpt-oss's generation settings are scattered across five places, with inconsistent
values:

| Location | temperature | max_tokens | effort | stop |
|---|---|---|---|---|
| `envs/collect/common.py:48` Chat default | 0.0 | 8192 | None (falls to medium in the harmony prompt) | none |
| `envs/collect/run_appworld.py:65` + `gen_launch.py:64` | same as above | same as above | chat mode pinned to high | none |
| `envs/collect/bfcl_gptoss/gpt_oss_chat.py:58-61` | BFCL's own | 16384 (hardcoded) | high (hardcoded) | none |
| `pipeline/inject/live_appworld.py:76,387-388,549` | 0.0 | 8192 | high | `["<|return|>"]` |
| `pipeline/inject/replay_inject.py:812-813,1283` | 0.0 | 8192 (CLI default) | not applicable (continuation) | `["<|return|>"]` |

Current state of model paths: `model_registry.py` claims to be the single mapping
but has zero importers; the 13 launchers in `envs/serve_logs/launch_vllm_*.py`
each hardcode their own path/port/environment variables; three models in active
use on NFS, LFM2.5-350M-Base, Qwen3-0.6B-Base, and MirrorAPI-Cache, are not in
the registry (MAP.md:177 records the first two; MirrorAPI-Cache is hardcoded
in run.py:414).

Trajectory meta currently only records env/task_id/model/instruction
(run_appworld.py:100-102); sampling parameters and effort leave no trace at all.

## Design

### File layout

```
configs/
  README.md          # first line states clearly the division of labor with pipeline/configs/
  models.json        # the single model address mapping (model_registry.py switches to reading from here)
  presets/
    gptoss_chat_high.json      # collection-line chat convention (= current gen_launch's gptoss extra flags)
    gptoss_harmony_medium.json # collection-line harmony convention (= current run_appworld --api harmony default)
    gptoss_bfcl_high.json      # BFCL line (= current gpt_oss_chat.py hardcoded values)
    gptoss_live_high.json      # live-run line (= current live_appworld default)
    gptoss_replay.json         # replay-continuation line (= current replay_inject run default)
```

`pipeline/configs/` manages data batches (which trajectories, how they're split);
`configs/` manages generation settings (model, server parameters, sampling
parameters). The first line of each README points to the other.

### models.json structure

```json
{
  "models": {"alias": {"path": "...", "note": "..."}},
  "aliases": {"qwen3.6": "qwen3.6-27b", "qwen3.5": "qwen3.5-27b"}
}
```

Move all entries of `model_registry.py`'s MODELS/ALIASES, and add three:
LFM2.5-350M-Base, Qwen3-0.6B-Base, MirrorAPI-Cache (all paths under
`/net/tokyo100-10g/data/str01_01/y-guo/models/`, verified on disk with ls on
2026-08-20). `model_registry.py` becomes a thin shell that reads the json,
`resolve()`'s signature and behavior do not change one bit, and the CLI
behavior of `python3 model_registry.py <alias>` does not change either.

### Preset structure (configs/presets/<name>.json)

```json
{
  "desc": "One sentence stating which line this set of settings is for and what convention it follows",
  "model": "gpt-oss-120b",
  "server": {
    "host": "tokyo108",
    "port": 8103,
    "served_model_name": "gpt-oss-120b",
    "gpu_memory_utilization": 0.92,
    "max_model_len": null,
    "env": {"VLLM_USE_FLASHINFER_SAMPLER": "0",
            "LD_LIBRARY_PATH": "/home/y-guo/reproduce/new1/envs/cuda-compat-13.0"},
    "extra_flags": ""
  },
  "client": {
    "api": "chat",
    "reasoning_effort": "high",
    "temperature": 0.0,
    "top_p": null,
    "max_tokens": 8192,
    "stop": null,
    "start_date": null,
    "seed": null
  }
}
```

Both the server section and the client section can be omitted (live-run/replay
presets carry no server section; the service is started separately). null means
"not specified, use the caller's original default." GPU card numbers do not go
into the preset: picking a card is gpu-run's job at launch time; `serve_preset.py`
takes it via `--gpu`.

### Reader preset_loader.py (repo root, pure standard library)

- `load_models()` / `load_preset(name)` / `list_presets()`.
- `validate(preset)`: reports errors for all three cases: unknown keys, type
  errors, and a model alias not in models.json.
- `merge_client(cli, client_node, fallbacks)`: three-level priority, explicit
  CLI value > preset value > original default. None in the cli dict counts as
  "not explicitly given."
- Fields in entry-script argparse that used to carry meaningful defaults (such
  as live's --effort high, replay's --max-tokens 8192) change to default=None,
  and the original default values move into fallbacks, so that "the user gave
  it" and "fell to default" can be told apart. The effect does not change.

### Seven entry points wire up --preset

run_appworld / run_alfworld / run_tales / run_tau2 / live_appworld /
replay_inject (the run subcommand) each get a `--preset name` flag added.
After merging, it's passed to Chat/the request body. When the preset carries
a server section, `--model` and `--base-url` can be omitted: model takes
server.served_model_name, base_url takes `http://{host}:{port}/v1`; an
explicit value still overrides as before. **When --preset is not passed, all
behavior stays byte-for-byte identical to now.**

bfcl's gpt_oss_chat.py is a file copied into the BFCL venv with no CLI of its
own; it changes to reading the environment variable `NEW1_PRESET_JSON` (the
preset file's absolute path): when set, it takes max_tokens/reasoning_effort
from the client section; when not set, it falls back to the current
hardcoded values.

### Leaving traces

- Chat gets a `settings()` method that returns a dict of api/model/temperature/
  max_tokens/reasoning_effort/start_date; the four collectors put
  `gen_settings=chat.settings()` and `preset=<name or None>` into the TrajLog
  meta. On the annotate side, build.py only reads by key, so extra keys are
  harmless.
- live_appworld's meta dict (inside run_task) gets the preset name added.
- serve_preset.py copies the full preset text to the log directory as
  `<session>.preset.json` at launch time.
- RUNMETA auto-captures argv, so the preset name rides along with argv into
  RUNMETA; nothing extra needed.
- run_id carrying the preset name becomes one item on the DATA.md checklist.

### serve_preset.py (repo root) + run.py registration

Reads the preset's server section plus models.json to resolve the path, and
assembles an ssh+tmux command isomorphic to launch_vllm_gptoss.py's.
Arguments: `--preset` required, `--gpu` required, `--host/--port/--session`
override the preset, `--dry-run` only prints without executing. session
defaults to `new1_vllm_<host>_<preset name>`.

run.py TASKS adds:

```python
"serve-preset": dict(stage="live", py="sys", script="serve_preset.py",
                     handoff=True, gpu=True, ...)
```

handoff+gpu: show prints the command, it passes the dirty-tree gate, and the
launch itself goes through gpu-run. gen_launch.py's `GPTOSS_CLIENT_EXTRA`
changes to `--preset gptoss_chat_high` (equivalent item-for-item to the old
string once expanded); the doc line is updated in sync.

### Acceptance

1. `run.py selfcheck` extended: run validate over each preset one by one;
   every models.json entry has path+note, and aliases point to keys that
   exist.
2. tests/test_preset.py (unittest, runnable with sys python3):
   - each of the five presets passes validate;
   - resolve("gpt-oss-120b") equals the pre-change path string (guards
     against a copy-paste error while moving it);
   - one test case each for merge_client's three-level priority;
   - equivalence: gptoss_chat_high expands to == {api:chat, effort:high,
     temp:0.0, max_tokens:8192}; the other four presets each checked against
     the current-state table;
   - the vllm serve command string serve_preset --dry-run generates for
     gptoss_chat_high is compared word-by-word against
     launch_vllm_gptoss.py's CMD (port/flags/environment variables).
3. Each entry point runs `--help` or py_compile with its own venv's python,
   confirming it can import after the change.
4. Old command equivalence: using the appworld venv to invoke
   run_appworld's settings-parsing function, the two argument sets
   `--preset gptoss_chat_high` and `--api chat --reasoning-effort high`
   produce Chat parameter dicts equal key by key.

### Not doing

- The 13 old launch_vllm_*.py files are left untouched, kept as history.
- No presets are built for the qwen line (this round only covers gpt-oss;
  the mechanism is general, adding one json file is enough).
- Picking a card (GPU number) in vLLM server-side parameters does not go
  into the preset.
- CELLS/EVAL_CELLS (the training/eval four cells) are left untouched; probe
  training is not a generation setting.

### Wrap-up checklist

MAP.md (three lines for configs/, serve_preset.py and preset_loader.py; the
model_registry line updated; the "missing entry" item in §Known Pitfalls
struck out); the `--api chat --reasoning-effort high` spots in probe-pipeline's
references/stage-commands.md and extending.md are rewritten to the --preset
phrasing; bfcl RUNBOOK.md gets NEW1_PRESET_JSON added; configs/README.md and
pipeline/configs/README.md point to each other; DATA.md checklist gets one
more item; TIMELINE gets an entry added; once `run.py selfcheck` is all
green, code + registry + config go in the same commit.
