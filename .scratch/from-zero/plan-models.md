# Build plan: `models/`

Folder group **models**, nine files, all of them in the fourth draft's fixed tree:
`models/table.yaml`, `models/__init__.py`, `models/agent_models/{__init__.py,
gptoss.py, service.py}`, `models/probe_models/{__init__.py, base.py, qwen.py,
service.py}`. Contracts read in full: Parts 6.1, 6.2, 7.1, 7.2, 7.4, 1.6, and the
0.2 entries for these nine files; Parts 1.5, 2.1, 2.2, 2.6, 3.3, 5.2, 5.3 read for
what crosses into this folder.

Conventions that hold for every file below.

- Every Python file starts with `from __future__ import annotations`, so PEP 604
  annotations (`str | None`) load under system `python3` (3.10.12, measured
  2026-09-17) as well as the three venvs.
- `venv: any` is proved by importing under four interpreters: `python3`,
  `external/appworld/venv/bin/python`, `external/probe-env/bin/python`,
  `external/vllm-env/bin/python`.
- `VERSION` is assigned at module level, column zero, exactly once, to an integer
  literal (3.3). The five files 2.2 names — `gptoss.py`, `agent_models/service.py`,
  `probe_models/base.py`, `qwen.py`, `probe_models/service.py` — carry one and
  start at `VERSION = 1`. The three `__init__.py` files and `table.yaml` carry
  none: no stage-table version list names them, and `models/__init__.py`'s tree
  line says "edited never".
- Runtime strings (errors, argparse help, log lines) are English.
- No file in this folder writes a registry row, reads `jobs/registry.py`, or
  starts a process on another host.

---

## 1. Files

### 1.1 `models/table.yaml`

**One sentence.** The model table: one row per alias, `role` and `family` at the
row, a keyed `result:` block and an unkeyed `serving:` block (6.1).

**Venv.** Data file; read by `models/__init__.py` (any), by
`experimental_settings/schema.py` (any), by `models/agent_models/service.py`
(the `serving:` block) and by `jobs/launch.py` (the `serving:` host and port).

**Content to write** — four rows. The two the contract spells out, plus the two
extra probe backbones this project already trains on (legacy
`train_causal_tool.py:84-88` hardcoded three Qwen tiers; the tree makes each a
row):

```yaml
gptoss120b:
  role: agent
  family: gptoss
  result:
    weights: gpt-oss-120b
    dtype: auto
    quantization: null
    max_model_len: 131072
    served_model_name: gpt-oss-120b
    env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: ""
  serving:
    host: tokyo108
    port: 8103
    gpu_memory_utilization: 0.92
    tensor_parallel_size: 1
    env:
      LD_LIBRARY_PATH: /home/y-guo/reproduce/new1/envs/cuda-compat-13.0
      CUDA_DEVICE_ORDER: PCI_BUS_ID
      VLLM_CACHE_ROOT: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache
      TRITON_CACHE_DIR: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton

qwen06:
  role: probe
  family: qwen
  result: {weights: qwen3-0.6b-base, dtype: float32}
  serving: {}

qwen17:
  role: probe
  family: qwen
  result: {weights: qwen3-1.7b-base, dtype: float32}
  serving: {}

qwen4:
  role: probe
  family: qwen
  result: {weights: qwen3-4b-base, dtype: float32}
  serving: {}
```

Sources: `legacy/configs/presets/default.json:4-15` (host, port,
`served_model_name`, `gpu_memory_utilization`, `VLLM_USE_FLASHINFER_SAMPLER=0`,
`LD_LIBRARY_PATH`), `legacy/envs/serve_logs/launch_vllm_awdiag.py:58-60`
(`CUDA_DEVICE_ORDER`, `VLLM_CACHE_ROOT`, `TRITON_CACHE_DIR`; the cache
redirection exists because `/home` has an NFS quota that has already killed a
vLLM), `legacy/envs/serve_logs/launch_vllm_awdiag.py:1-20` (native
`max_model_len` is 131072 and the w0 collection passed no `--max-model-len`, so
131072 is the value that reproduces it), `legacy/configs/models.json:24-39` and
`legacy/pipeline/train/train_causal_tool.py:84-88` (the weights aliases).

Two deliberate departures from 6.1's example row are in section 6 (errata 1 and
2): `gptoss120b.result.dtype` is `auto`, not `bfloat16`, and
`qwen06.result.dtype` is `float32`, not `bfloat16`.

**Not ported.** `legacy/configs/presets/*.json`'s whole `client:` block
(`api`, `reasoning_effort`, `temperature`, `top_p`, `max_tokens`, `stop`,
`start_date`, `seed`) — every one of those is a field of the `generation:`
section in `experimental_settings/schema.py` (5.2), not a model column. The two
other presets (`gptoss_default.json`, `gptoss_bfcl_high.json`), the `desc` field,
and `legacy/configs/models.json:45-48`'s `aliases:` block (an alias of an alias)
are dropped: 6.3 gives `path_models.yaml` one level, `alias -> {path, note}`.

### 1.2 `models/__init__.py`

**One sentence.** The entrance: `agent(alias)` and `probe(alias)` read
`table.yaml`, resolve the weights path out of `constants/path_models.yaml`, and
for an agent import the family module by name inside the function (6.2, 0.2).

**Venv.** `any` (standard library + PyYAML; no Polars, no NumPy).

**Names it must offer** (6.2, "What the two entrances return"):

```python
@dataclass(frozen=True)
class AgentModel:
    module: object        # the family module, imported by name inside agent()
    alias: str
    role: str             # "agent"
    family: str
    weights: str          # always the alias, never the path
    weights_path: str     # always the directory (or the hub id)
    serving: dict

@dataclass(frozen=True)
class ProbeModel:         # same shape, minus `module`
    alias: str
    role: str
    family: str
    weights: str
    weights_path: str
    serving: dict

def agent(alias: str) -> AgentModel: ...
def probe(alias: str) -> ProbeModel: ...
```

Behaviour, each clause with its section:

- `weights` is always the alias and `weights_path` always the directory (6.2).
- `agent()` refuses a row whose `role` is not `agent`, `probe()` a row whose
  `role` is not `probe`, and both refuse an unknown alias, naming the sorted
  known aliases of that role (the message shape of
  `legacy/model_registry.py:23-24`).
- `agent()` imports `models.agent_models.<family>` with `importlib.import_module`
  **inside the function** and refuses, naming the expected file path, when the
  module is missing. `probe()` imports nothing — `models/probe_models/base.py`
  imports the backbone module inside `load()` (6.2).
- `weights_path`: look the `result.weights` alias up in
  `constants/path_models.yaml`; an absolute path that does not exist raises
  `FileNotFoundError` naming the alias and the path (ported verbatim from
  `legacy/model_registry.py:26-27`, which exists to catch an unmounted NFS); a
  value that does not start with `/` is a hub id and passes through unchecked.
- `serving` is the row's `serving:` block, `{}` when absent. It is the one block
  a run may read live (6.1).
- Both YAML files are found relative to the repo root,
  `Path(__file__).resolve().parents[1]`.
- No `VERSION` (no version list names this file).

**Imports / used by** (0.2): imports none from the repo, `[importlib, PyYAML]`;
used by `agent/generate.py`, `agent/inject.py`, `models/agent_models/service.py`,
`models/probe_models/base.py`, `models/probe_models/service.py`,
`train/utils/trainer.py` — six, and `agent/loop.py` is deliberately not among
them. Reads `models/table.yaml`, `constants/path_models.yaml`; writes nothing.

**Legacy source.** `legacy/model_registry.py:15-28` (the table read, `resolve()`,
the existence check); `legacy/preset_loader.py:56-59` (`load_models`).

**Not ported.** `ALIASES` and the `name.lower()` normalisation
(`legacy/model_registry.py:18,22`) — an alias is written exactly as the table
spells it; the `__main__` CLI listing (`model_registry.py:31-37`) —
`run.py where`/`ls` is the place a person asks; `preset_loader.base_url_of`
(`legacy/preset_loader.py:150-155`) — a base URL now comes from a service
endpoint file (7.4), never from a config.

### 1.3 `models/agent_models/__init__.py`

**One sentence.** Empty package marker, so the client half of `service.py`
imports without the family's libraries (0.2).

**Venv.** `any`. **Content.** A one-line docstring and nothing else: no imports,
no `VERSION`, no re-export. **Used by** `models/agent_models/service.py` and
`models/agent_models/gptoss.py` as their package. **Legacy source.** None.

### 1.4 `models/agent_models/gptoss.py`

**One sentence.** gpt-oss's conversation format: the harmony render to prompt
token ids, the streamed-reply channel split, the end-of-turn test, the
prefetch wrapping, and the family's own generation defaults (6.2, 0.2).

**Venv.** `any` at import and for `parse` / `end_of_turn` / `wrap_prefetch`;
`probe` or `vllm` for `render_ids()`, whose `openai_harmony` import sits inside
the function (0.2).

**Names it must offer** (6.2's family-module table; `EFFORTS`, `STOP`,
`DEFAULT_EFFORT`, `DEFAULT_DATE`, `NAME`, `VERSION` are also read as source text
by `schema.py`, at column zero, exactly once, per 3.3):

```python
VERSION = 1
NAME = "gptoss"
STOP = ["<|return|>"]                     # 5.2's default of generation.stop
EFFORTS = ("high", "medium", "low")       # 5.3 validates generation.effort against it
DEFAULT_EFFORT = "high"
DEFAULT_DATE = "2026-08-06"
END_IDS = (200002, 200012)                # <|return|>, <|call|> — see errata 7

def render_ids(messages: list[dict], effort: str | None, date: str | None) -> list[int]
def parse(text_delta: str, state: dict) -> dict          # {"reasoning": str, "content": str}
def end_of_turn(ids: list[int]) -> bool
def wrap_prefetch(body: str, system_text: str | None) -> str
```

Behaviour:

- `render_ids` is `legacy/pipeline/inject/harmony_render.py:34-135` moved
  whole: the `EFFORT` table, `to_harmony_messages` (leading system/developer
  message becomes the harmony developer instructions, an assistant turn with
  empty content is dropped, a mid-conversation system/developer message becomes
  another developer message), then
  `render_conversation_for_completion(conv, Role.ASSISTANT,
  RenderConversationConfig(auto_drop_analysis=False))`. The encoding object is
  built once and cached in a module global (`harmony_render.py:46-53`). It
  refuses a message carrying `tool_calls` / `reasoning` / `thinking`, and an
  unknown role, rather than falling through (`harmony_render.py:88-93`).
  It refuses `effort=None` and `date=None`, naming the field (errata 9).
- `parse(text_delta, state)` accumulates the raw generated text in `state` and
  returns the two channels grown so far under exactly `reasoning` and `content`,
  by the rule of `legacy/pipeline/inject/live_appworld.py:111-148` (`parse_step`):
  split on `<|end|>`, a valid header is `[<|start|>assistant[ to=x]]<|channel|>CH`
  followed by `<|message|>`, `analysis` bodies join into `reasoning` with `\n`,
  `final` and recipient-less `commentary` bodies join into `content` with `\n`,
  everything from a literal `<|return|>` on is cut. A half-written header
  contributes nothing, which is the streaming form of
  `live_appworld.py:151-162`'s `think_span` returning None. Per-family
  bookkeeping stays in `state`; the returned dict carries the two keys and
  nothing else (6.2's failure note: a third spelling gives an empty thinking text
  and an inject run that never fires).
- `end_of_turn(ids)` is `ids[-1] in END_IDS`. It may not import
  `openai_harmony`: it runs under `venv: any`, and the AppWorld venv has no
  `openai_harmony` (facts table). `END_IDS` was measured on 2026-09-17 with
  `openai_harmony` 0.0.8 in `external/probe-env`:
  `stop_tokens_for_assistant_actions() == [200002, 200012]` (errata 7).
- `wrap_prefetch(body, system_text)` is
  `legacy/pipeline/inject/inject_format.py:36-37`'s `TAIL`:
  `"<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>"
  + body + "<|end|><|start|>assistant"`, with `system_text + "\n\n"` in front of
  `body` when `system_text` is not None (errata 8). The sender is `prefetch` and
  not `python` on purpose (CONTEXT, "prefetch sender").

**Imports / used by** (0.2): imports nothing from the repo,
`[openai_harmony, inside render_ids()]`; used by `models/__init__.py` by name
only — every other file reaches this module as `agent(alias).module` and names no
family file. Reads and writes nothing.

**Legacy source.** `harmony_render.py:34-135`;
`live_appworld.py:111-148`; `inject_format.py:36-37`;
`rebuild.py:81` (`REASONING_EFFORT = "high"` -> `DEFAULT_EFFORT`);
`legacy/configs/presets/default.json:18,23` (`reasoning_effort`, `start_date`
-> `DEFAULT_EFFORT`, `DEFAULT_DATE`).

**Not ported.** `harmony_render.decode` (`:138-140`) — decoding is the probe
service's `/decode` through the HF tokenizer, not harmony's encoding;
`rebuild.py`'s whole jinja text path (`build_prefix:161-207`, `assert_date`,
`has_literal_harmony`, `thinking_prefix`, `needs_guard_bypass`,
`check_system_verbatim`) — the id path replaced it on 2026-08-18 and the offline
replay line that still used it is dropped (9(a)#26); `rebuild.SYSTEM` and
`NO_CODE_MSG` — those are the environment's `INSTRUCTIONS` and
`NO_CODE_MESSAGE` (4.1), not the family's; `rebuild.ANALYSIS_OPEN` — v4 stopped
prefilling the channel header; `rebuild.COLLECT_DATE = "2026-07-31"` — superseded
by `DEFAULT_DATE = "2026-08-06"` (5.2); `inject_format.py`'s `sep_for`,
`system_extra`, `needs_special`, `splice_text`, `FORMATS`,
`is_prefetch_header` — those belong to `agent/inject_format.py` (7.3), not to a
family module.

### 1.5 `models/agent_models/service.py`

**One sentence.** Both ends of the served agent model: the server main that
starts or attaches to a vLLM server for a table row and runs the check table,
and the loop's client, a raw token stream with a seed (7.1, 0.2).

**Venv.** `any` at import; `vllm` to serve. Every heavy import sits inside the
server main.

**Names it must offer:**

```python
VERSION = 1                                # folded into the sample and inject keys (2.2)

# server half
def build_command(row: dict, serving: dict, weights_path: str, port: int,
                  gpus: str, date: str | None) -> tuple[list[str], dict[str, str]]
def serve(args) -> None
def main(argv=None) -> int                 # `python -m models.agent_models.service serve ...`

# client half (standard library)
class Stream:                              # yields (text_delta, token_ids_delta)
    finish_reason: str | None
    stop_reason: str | None
    usage: dict | None
    n_chunks: int
    n_ids: int
    def __iter__(self): ...
    def close(self) -> None: ...

class Client:
    def __init__(self, base_url: str, served_model_name: str) -> None: ...
    def stream(self, prompt_ids: list[int], generation: dict,
               seed: int | None) -> Stream: ...
    def health(self) -> dict: ...          # {"up": bool, "served_model_names": [str]}
```

**Command line** (7.1, with `--replica` added by errata 10):

```
python -m models.agent_models.service serve --run-dir <dir> --model <alias> \
    --port <n> --gpus <ids> --replica <i> [--attach-only]
```

Server behaviour, clause by clause:

1. `cfg = schema.load_frozen(run_dir)`; the keyed columns come from
   `cfg.models.agent_row` — `role`, `family` and the whole `result:` block — and
   never live from `models/table.yaml` (6.2, 7.1).
2. `m = models.agent(args.model)` gives the family module, `weights_path` and
   the live `serving:` block. Compare `m.family` against
   `cfg.models.agent_row["family"]` and `m.weights` against
   `cfg.models.agent_row["weights"]` and refuse on a difference, naming both
   (errata 15; the same comparison 6.2 imposes on `agent/generate.py`).
3. `build_command` assembles
   `<sys.executable's directory>/vllm serve <weights_path>
   --served-model-name <served_model_name> --host 0.0.0.0 --port <port>
   --gpu-memory-utilization <g> --tensor-parallel-size <t>
   --max-model-len <max_model_len> --dtype <dtype>
   [--quantization <q>] [<extra_flags>]` and the environment
   `serving.env` (locations) `+ result.env_result` (keyed)
   `+ VLLM_SYSTEM_START_DATE=<date>` `+ CUDA_VISIBLE_DEVICES=<gpus>`.
   `quantization` is omitted when null; `extra_flags` is split with `shlex`.
   Ported from `legacy/serve_preset.py:41-52`, plus `VLLM_SYSTEM_START_DATE`
   (6.1, 9(a)#25) which legacy never set.
4. `--attach-only`: do not start a server; ask `GET /v1/models` on
   `http://<serving.host>:<port>/v1`, compare the served model name and every
   keyed column against `cfg.models.agent_row`, and refuse to attach on any
   difference (7.1). `jobs/launch.py` decides when to pass the flag (7.4).
5. Check table before reporting healthy (7.1): `/health` answers within
   `registry.DEFAULTS["launch_timeout_s"]`; `GET /v1/models` names the row's
   `served_model_name`; and **render equals server** —
   `m.module.render_ids(CHECK_MESSAGES, cfg.generation.effort,
   cfg.generation.date)` computed in this venv equals the `prompt_token_ids` the
   chat endpoint returns for the same conversation
   (`POST /v1/chat/completions`, `max_tokens: 1`, `reasoning_effort`,
   `return_token_ids: true`), id for id. `CHECK_MESSAGES` is a module-level
   literal of four messages: a system message, a user message, an assistant turn
   with **empty** content, and an assistant turn containing a literal `<|end|>`
   — the two shapes the 2026-08-18 investigation found diverging
   (`legacy/pipeline/inject/harmony_render.py:1-18`).
6. Write `service_agent_<replica>.json` into the run directory, with the keys of
   errata 13; `attached_to` is the owning row's `run_id` when `--attach-only`
   was used and null otherwise (7.1, 1.5).
7. Then `exec`/wait on the vLLM process, so the tmux piece lives as long as the
   server.

Client behaviour: `Stream` is `legacy/pipeline/inject/live_appworld.py:188-239`
verbatim in shape — SSE lines, `usage` when `include_usage` gives it,
`finish_reason` / `stop_reason` from the choice, `(text, ids)` handed out
together per chunk because the text lags the ids when vLLM withholds bytes.
The request body is `model`, `prompt` (ids), `max_tokens`, `temperature`,
`stop`, `top_p` and `seed` **only when set**, `add_special_tokens: false`,
`skip_special_tokens: false`, `return_token_ids: true`, `stream: true`,
`stream_options: {include_usage: true}` (7.1;
`live_appworld.py:252-270` for the "only when set" rule). `generation` is a
plain dict carrying exactly `max_tokens`, `temperature`, `top_p`, `stop`
(errata 11). Opening the stream retries three times with exponential backoff on
connection errors and 5xx (`live_appworld.py:241-249`); a 400 is re-raised as
`urllib.error.HTTPError` for the caller to record as
`abort="context_overflow_400"` (7.1).

**Imports / used by** (0.2): imports `models/__init__.py` (the family through
`agent(alias)`, inside the server main) and `experimental_settings/schema.py`
(`load_frozen`); used by `agent/generate.py` (client) and `agent/loop.py`
(health); `jobs/launch.py` starts it as a tmux piece, which is not an import.
Reads `models/table.yaml` (the `serving:` block only),
`constants/path_models.yaml`, and the run directory's `settings.yaml`. Writes
`service_agent_<replica>.json` and its piece log.

**Legacy source.** `legacy/serve_preset.py:32-56` (the `vllm serve` command and
its environment); `legacy/envs/serve_logs/launch_vllm_awdiag.py:55-62` (the four
location environment variables); `live_appworld.py:188-270` (the stream, the
retries, the "only when set" sampling keys).

**Not ported.** `serve_preset.py:53-56,68-81` — the ssh + tmux + `tee` assembly,
the `WORKDIR` log convention, `--session`, `--dry-run` and the
`<session>.preset.json` copy: starting a piece is `jobs/launch.py`'s (7.4,
3.4) and the settings copy is `settings.yaml`. Every handwritten launcher under
`legacy/envs/serve_logs/` (`launch_vllm_*.py`, the `*_job.sh` scripts) is
dropped whole: one row in `table.yaml` plus `jobs/launch.py` replaces all
eighteen. `legacy/preset_loader.py`'s `merge_client` three-tier priority,
`require_temperature`, `validate`, `list_presets` — the setting loader's job now
(5.7).

### 1.6 `models/probe_models/__init__.py`

**One sentence.** Empty package marker, so the client half of `service.py`
imports without torch (0.2).

**Venv.** `any`. **Content.** A one-line docstring, nothing else. **Used by**
`models/probe_models/base.py`, `models/probe_models/service.py`,
`models/probe_models/qwen.py` as their package. **Legacy source.** None.

### 1.7 `models/probe_models/qwen.py`

**One sentence.** Qwen's backbone details: dtype, LoRA targets, the head's
hidden-state attribute, the tokenizer quirks and the head constructor (6.2).

**Venv.** `probe`.

**Names it must offer** (6.2's backbone-module table; `LORA_TARGETS` is also read
as source text by `schema.py`, column zero, exactly once, per 3.3):

```python
VERSION = 1
DTYPE = "bfloat16"          # the restore/serving dtype; a row's result.dtype overrides at training
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]
HEAD_LAYER = "last_hidden_state"

def prepare_tokenizer(tok) -> None
def attach_head(model, n_labels: int)      # -> torch.nn.Module, the head
```

- `prepare_tokenizer` sets, in place: `pad_token = eos_token` when
  `pad_token_id` is None, `truncation_side = "left"` (keep the tail of the
  thinking), `padding_side = "right"` (every supervision position is a real
  token) — `legacy/pipeline/train/train_causal_tool.py:213-217`, and the
  `truncation_side` warning of `legacy/pipeline/inject/probe_server.py:111-116`
  becomes this unconditional set.
- `attach_head(model, n_labels)` returns `torch.nn.Linear(h, n_labels)` in
  float32, with `h = model.config.get_text_config().hidden_size`
  (`train_causal_tool.py:196-198`). The class order is the caller's: the backbone
  never sees the names (6.2).
- `DTYPE` is the dtype a restore loads in when no row is given
  (`probe_server.py:107-108,130-132` loads bf16 on cuda); a training load takes
  `row["dtype"]`, which `table.yaml` sets to `float32`
  (`train_causal_tool.py:196`). See errata 2 and 3.

**Imports / used by** (0.2): imports nothing from the repo, `[transformers]`;
used by `models/probe_models/base.py` by name. Reads and writes nothing.

**Legacy source.** `train_causal_tool.py:196-198,213-217`;
`lora_util.py:36-37`; `probe_server.py:107-116`.

**Not ported.** `train_causal_tool.py:84-88`'s `MODELS` dict — three hardcoded
paths, now three rows in `table.yaml` plus `constants/path_models.yaml`;
`lora_util.py:39-42`'s `DEFAULT_RANK/ALPHA/DROPOUT/LR` — `probe.lora_*` fields
with their defaults in `schema.py` (5.2).

### 1.8 `models/probe_models/base.py`

**One sentence.** The probe object every backbone shares: build or restore,
save the checkpoint layout, score a prefix, generate a call (6.2, 1.6).

**Venv.** `probe`.

**Names it must offer** (6.2's probe-object table, with the three additions of
errata 3, 4, 5, 6):

```python
VERSION = 1

Batch = dict[str, Any]      # keys forward consumes: input_ids, attention_mask,
                            # event_end, position_ids (optional); every other key
                            # is the method's own and base.py never reads it

@dataclass
class Outputs:
    logits: Tensor          # classifier: [n_events, n_labels]; generator: [B, T, vocab]
    hidden: Tensor | None   # classifier: [B, T, dim] at HEAD_LAYER; generator: None

class Probe(torch.nn.Module):
    backbone; head; tokenizer; max_len: int; labels: list[str] | None
    probe_kind: str; lora                      # the peft wrapper, or None
    def save(self, dir, *, labels=None, extra=None, meta=None) -> None
    def forward(self, batch: Batch) -> Outputs
    def score(self, texts: list[str]) -> tuple[list[list[float]], list[str]]
    def generate(self, texts: list[str], max_new: int, call_sep: str) -> list[str]
    def enable_grad_checkpointing(self) -> None

def load(row, cfg, *, probe_kind, n_labels=None, labels=None,
         ckpt_dir=None, device="cpu") -> Probe
```

Behaviour:

- `load` imports `models.probe_models.<family>` by name inside the function
  (6.2), the family coming from `row["family"]` when a row is given and from
  `models.probe(meta["backbone"]).family` on a restore. `row` **is**
  `cfg.models.probe_row` — `role`, `family` and the `result:` block — and the
  absolute weights path is the one live value, taken through
  `models.probe(cfg.models.probe).weights_path` (6.2). `cfg` is annotated
  `object`, so this file imports no `schema.py`, and it reads exactly
  `cfg.probe.tuning`, the four `cfg.probe.lora_*` fields, `cfg.train.max_len`
  and `cfg.models.probe` — nothing else (6.2).
- `probe_kind == "classifier"` builds `AutoModel.from_pretrained(path,
  dtype=<dtype>)` and calls the backbone's `attach_head(model, n_labels)`;
  `probe_kind == "generator"` builds `AutoModelForCausalLM.from_pretrained` and
  attaches no head (`train_causal_tool.py:191-208`, `probe_server.py:122-133`).
  After `prepare_tokenizer`, when
  `model.config.get_text_config().pad_token_id` is None it is set to the
  tokenizer's (`train_causal_tool.py:220-221`).
- `cfg.probe.tuning` is dispatched through an explicit mapping whose `else`
  raises, naming the axis and the value (5.3). `lora` wraps the backbone with
  `peft.get_peft_model(LoraConfig(r=lora_r, lora_alpha=lora_alpha,
  lora_dropout=lora_dropout, target_modules=<lora_targets or the backbone's
  LORA_TARGETS>, bias="none"))` and keeps the wrapper in `self.lora` for the
  merge on save (`lora_util.py:75-90`). peft is imported inside the `lora`
  branch only (`lora_util.py:8-12`).
- `ckpt_dir` restores: weights and tokenizer from that directory (LoRA was
  merged at save time, so a restore is a plain `from_pretrained`), `head.pt` for
  a classifier, and `labels`, `tuning`, `max_len`, `backbone` from
  `<ckpt_dir>/meta.json`; the hook is not called (2.6, 1.6). `row` and `cfg` are
  both None on that path.
- `save(dir, *, labels, extra, meta)` writes 1.6's layout: the merged weights
  (`copy.deepcopy(self.lora).merge_and_unload().save_pretrained(dir)`, then the
  copy is freed and `torch.cuda.empty_cache()` is called —
  `lora_util.py:93-119`) or `backbone.save_pretrained(dir)`, the tokenizer,
  `head.pt` for a classifier, and `meta.json` holding `labels` plus every key of
  `meta` and every key of `extra`, merged unread (1.6, 6.2).
- `forward` moves the four tensor keys to the probe's device, calls the backbone
  with `use_cache=False`, and for a classifier reads
  `getattr(out, HEAD_LAYER)` and applies the head at the `event_end` positions
  in float32 (`train_causal_tool.py:200-208`); for a generator it returns the LM
  logits and `hidden=None`.
- `score(texts)` tokenizes with `truncation=True, max_length=self.max_len,
  padding=True`, takes each row's **last non-pad token**, applies the head, and
  returns the class logits in `labels` order plus the argmax class name per text
  — the served form of the `event_end` rule (6.2), ported from
  `probe_server.py:163-177` with the softmax and the temperature removed: the
  service applies them (7.2).
- `generate(texts, max_new, call_sep)` builds `text + call_sep`, encodes with
  `add_special_tokens=False, truncation=True,
  max_length=max(self.max_len - max_new, 1)`, generates greedily
  (`do_sample=False`), decodes the continuation with
  `skip_special_tokens=True`, and returns the first line stripped
  (`probe_server.py:179-193`). The separator is the caller's (1.6, 6.2).
- `enable_grad_checkpointing()` calls
  `backbone.gradient_checkpointing_enable()`, sets `config.use_cache = False`,
  and under LoRA calls `enable_input_require_grads()` once
  (`lora_util.py:122-138`; without it a checkpointed segment builds no graph and
  the adapter silently gets no gradient).

**Imports / used by** (0.2): imports `models/__init__.py` and
`models/probe_models/<backbone>.py` (by name, inside `load()`),
`[torch, transformers, peft]`; used by `train/utils/trainer.py`,
`train/methods/{ctool,cgen,cparam}.py` and `models/probe_models/service.py`
(inside `serve()`). Reads and writes the checkpoint layout of 1.6, the class
order included; it writes no run-level file and imports neither `schema.py` nor
`registry.py`.

**Legacy source.** `train_causal_tool.py:191-208` (`CausalProbe`),
`:211-222` (`build`), `:516-536` (the `best/` save);
`probe_server.py:98-133` (the two loaders), `:163-193` (score and gen);
`lora_util.py:75-138`.

**Not ported.** `train_causal_tool.py`'s data loading, `collate`, `align_check`,
`evaluate` and the whole `main` (`:97-188, 226-288, 305-543`) — those are
`train/utils/trainer.py`'s and the method files' (2.6); `readonly_map` and
`--readonly-env` (`:366-369, 390-395, 434-439`) — the read-only axis is dropped
(9(a)#26); `best/label_map.json` and `meta.json`'s `n_labels`, `base_path`,
`env`, `data`, `epoch`, `transformers` (`:524-536`) — 1.6 fixes `meta.json`'s
seven keys and 1.3 puts the class order in `labels`; `lora_util.add_args`,
`resolve_lr`, `meta_block`, `opt_params` (`:45-72, 141-156`) — flags are setting
fields (5.2), the meta block is `CHECKPOINT_META` plus `save`'s `meta` (1.6,
2.6), and the optimizer's parameter list is `trainer.py`'s
(`[p for p in probe.parameters() if p.requires_grad]`).

### 1.9 `models/probe_models/service.py`

**One sentence.** Both ends of the probe service: the HTTP server that loads the
probe and answers score, gen, render, encode, decode and health, the `check`
client that verifies a running one, and the loop's client (7.2, 7.4).

**Venv.** `any` at import; `probe` to serve. `torch`, `transformers` and
`models/probe_models/base.py` are imported inside `serve()`.

**Names it must offer:**

```python
VERSION = 1                                # folded into the sample and inject keys (2.2)

def serve(args) -> None
def check(args) -> int                     # 0 on success, non-zero on any mismatch
def main(argv=None) -> int

class Client:                              # standard library
    def __init__(self, base_url: str) -> None: ...
    def score(self, text: str) -> dict              # {"conf","label","wall_s"}
    def generate(self, text: str, max_new: int) -> dict   # {"call","wall_s"}
    def render(self, messages: list[dict], effort: str, date: str) -> dict
                                                    # {"prefix_ids","n_tokens","wall_s"}
    def encode(self, text: str, special: bool) -> dict    # {"ids","wall_s"}
    def decode(self, ids: list[int]) -> dict              # {"text","wall_s"}
    def health(self) -> dict
```

**Command line** (7.2, verbatim):

```
python -m models.probe_models.service serve --run-dir <dir> \
    --agent-model <alias> --port <n> \
    [--score-ckpt <dir> --gen-ckpt <dir> --temperature <f>] \
    [--device cuda:0] [--render-only]
python -m models.probe_models.service check --base-url <url> --run-dir <dir>
```

Server behaviour:

- The three probe flags and `--device` are **absent under `--render-only`**,
  which loads no probe and runs on the CPU (7.2).
- Both checkpoint flags take the **train run directory**; the service opens
  `<dir>/best/` and `<dir>/best/meta.json` inside it (7.2, 1.6). From the gen
  checkpoint's `meta.json` it reads `call_sep` (passed into
  `Probe.generate` on every `/gen`) and `param_only`: when `param_only` is true
  the service **refuses to start**, naming the checkpoint (7.2, 5.7). From the
  score checkpoint's `meta.json` it reads `max_len` and `train_key`.
- The agent side: `m = models.agent(args.agent_model)` resolves `family` and
  `weights` live — the one exception 6.2 allows, closed by the `/health` echo
  and `agent/loop.py`'s comparison — and gives `render_ids` and the HF tokenizer
  at `m.weights_path`. It never imports a family file by name (7.2, P4).
- The server **binds `0.0.0.0`** and `service_probe_0.json`'s `base_url`
  carries the host the piece was placed on, because an inject run's probe piece
  sits on a GPU host while the loop pieces run on `login_host` (7.2, 3.4).
- `ThreadingHTTPServer`, with one lock around every model call (errata 14): one
  probe service serves `sample.pieces` / `inject.pieces` loop processes at once.
- Routes, exactly 7.2's table: `POST /score` -> `{"conf","label","wall_s"}`,
  `conf` being `max softmax(logits / temperature)` over what `Probe.score`
  returned and `label` the argmax class name; `POST /gen` with a `max_new` in
  the body -> `{"call","wall_s"}`; `POST /render` -> `{"prefix_ids","n_tokens"}`;
  `POST /encode` -> `{"ids"}` from
  `encode(text, add_special_tokens=False, split_special_tokens=(not special))`;
  `POST /decode` -> `{"text"}` from `decode(ids, skip_special_tokens=False)`;
  `GET /health` -> the startup echo `family`, `weights`, `render` (`"ids"`),
  `encode_special`, `decode`, `temperature`, `agent_model`, `score_train_key`,
  `gen_train_key`, `max_len`, `device`, `version`. Under `--render-only`,
  `/score` and `/gen` return **503** and `temperature`, `score_train_key`,
  `gen_train_key`, `max_len` are null. Every response carries `wall_s`
  (`probe_server.py:271`), and an exception becomes a 500 whose body carries the
  original error text (`probe_server.py:273-274`).
- Writes `service_probe_0.json` with the keys of errata 13 (7.4, 1.5).

`check --base-url <url> --run-dir <dir>` is a client, not a second server
(7.2, 9(a)#38). It reads the run directory's frozen `settings.yaml` through
`schema.load_frozen` and compares, one request per route:

| expected, from `settings.yaml` | against the echo |
|---|---|
| `cfg.models.agent_row["family"]` | `family` |
| `cfg.models.agent_row["weights"]` | `weights` |
| `cfg._upstream["probe_score.train"]` | `score_train_key` |
| `cfg._upstream["probe_gen.train"]` | `gen_train_key` |
| `cfg._resolved.probe_temperature` | `temperature` |
| — | `render == "ids"`, `encode_special is True` |

plus **both directions of the `<|end|>` fixture** (9(d)): `encode("a<|end|>b",
special=false)` must contain no control-token id and decode back to the same
text, `encode(..., special=true)` must contain the `<|end|>` id. When the frozen
setting holds no `inject` section (a `sample` run, whose probe piece is the
render-only case), the last three rows are required to be **null** instead. Any
mismatch prints the field, the expected and the seen value, and exits non-zero —
which `jobs/launch.py` turns into the `service_check` outcome of 8.1.

Client behaviour: every method returns the route's decoded JSON body (errata
12), and every call retries three times with exponential backoff on connection
errors and 5xx, raising on a body carrying `error`
(`legacy/pipeline/inject/live_appworld.py:272-289`).

**Imports / used by** (0.2): imports `models/__init__.py`,
`experimental_settings/schema.py` (`load_frozen`, for the check client's
expected values), `models/probe_models/base.py` inside `serve()`,
`[http.server, transformers and torch inside serve()]`; used by `agent/loop.py`
(client: render) and `agent/inject.py` (client: score, generate, encode,
decode); `jobs/launch.py` starts it as a piece. Reads the checkpoint directories
named on its command line including each `best/meta.json`, and the run
directory's `settings.yaml` (the check client only). Writes
`service_probe_0.json` and its piece log.

**Legacy source.** `probe_server.py:88-95` (`encode_ids`), `:136-161` (the
render-only branch), `:195-215` (render, encode, decode), `:217-225` (the health
echo), `:228-277` (the HTTP server and the handler); `live_appworld.py:272-289`
(the retrying JSON client).

**Not ported.** `probe_server.py:8,176` — `fired` in `/score`'s response and the
`--theta` flag: theta lives in the setting and `agent/inject.py` compares
(7.2, 9(a)#9); `:280-343` — the whole `selftest` subcommand and its
`logits_test.pt` / `plan.jsonl` comparison, which went with the offline replay
line (9(a)#26) and is replaced by `check`; `:83-85` — the hardcoded `CTOOL`,
`CGEN`, `GPTOSS_TOK` defaults, now flags and a table row; `:205` — `prefix`, the
decoded text in `/render`'s response, which existed for human eyes;
`:225` — `start_date` in the health echo (7.2 has no `date`: the date arrives
per request on `/render`); `:218-224` — `theta`, `ctool`, `cgen`,
`render_only`, `n_labels` in the echo, replaced by 7.2's twelve fields.

---

## 2. Order of construction, and what must exist first

| step | files | needs first |
|---|---|---|
| 1 | `models/table.yaml`, `models/__init__.py`, `models/agent_models/__init__.py`, `models/probe_models/__init__.py` | `constants/path_models.yaml` (constants folder), holding the aliases `gpt-oss-120b`, `qwen3-0.6b-base`, `qwen3-1.7b-base`, `qwen3-4b-base` as `{path, note}` |
| 2 | `models/agent_models/gptoss.py` | nothing outside the folder |
| 3 | `models/probe_models/qwen.py`, then `models/probe_models/base.py` | step 1 (`models.probe`) |
| 4 | `models/agent_models/service.py` | steps 1-2; `experimental_settings/schema.py` (`load_frozen`, and a `Setting` carrying `models.agent_row`, `generation.effort`, `generation.date`) |
| 5 | `models/probe_models/service.py` | steps 1-4; `experimental_settings/schema.py` (`load_frozen`, and `_upstream`, `_resolved.probe_temperature` on the frozen setting) |

Nothing in this folder needs `data/`, `agent/`, `train/`, `eval/` or `jobs/` to
exist. Two names this folder **owes** other folders, which their planners should
take from here rather than invent: `Batch`'s `event_end` shape (errata 5, read by
`train/methods/*.py`) and the probe client's dict returns (errata 12, read by
`agent/loop.py` and `agent/inject.py`).

---

## 3. Acceptance, CPU

Every command is run from the repo root, `/home/y-guo/reproduce/new1`. `$SYS` is
`python3`, `$AW` is `external/appworld/venv/bin/python`, `$PROBE` is
`external/probe-env/bin/python`, `$VLLM` is `external/vllm-env/bin/python`.

**A1 — every `any` file imports under four interpreters** (0.1, 6.3).

```
for P in python3 external/appworld/venv/bin/python \
         external/probe-env/bin/python external/vllm-env/bin/python; do
  $P -c "import models, models.agent_models.gptoss, models.agent_models.service,
         models.probe_models.service; print('ok')" || exit 1; done
```

Expected: four lines `ok`, exit 0. (`models.probe_models.base` and
`models.probe_models.qwen` are **not** in this list: their venv is `probe`.)

**A2 — the two entrances resolve** (6.2).

```
python3 -c "
import models, pathlib
a = models.agent('gptoss120b'); p = models.probe('qwen06')
print(a.role, a.family, a.weights, a.module.NAME, a.serving['host'], a.serving['port'])
print(p.role, p.family, p.weights, hasattr(p, 'module'))
print(pathlib.Path(a.weights_path).is_dir(), pathlib.Path(p.weights_path).is_dir())"
```

Expected exactly:

```
agent gptoss gpt-oss-120b gptoss tokyo108 8103
probe qwen qwen3-0.6b-base False
True True
```

**A3 — the entrances refuse** (6.2).

```
python3 -c "
import models
for call, arg in ((models.agent,'qwen06'), (models.probe,'gptoss120b'), (models.agent,'nosuch')):
    try: call(arg); print('NO REFUSAL', arg)
    except Exception as e: print(type(e).__name__, str(e)[:80])"
```

Expected: three lines, none of them `NO REFUSAL`; the first two messages name the
row's actual role, the third lists the known agent aliases.

**A4 — `gptoss.py`'s literals are readable the way `schema.py` reads them**
(3.3: column zero, exactly once, a literal).

```
python3 -c "
import ast, pathlib
t = ast.parse(pathlib.Path('models/agent_models/gptoss.py').read_text())
want = {'VERSION','NAME','STOP','EFFORTS','DEFAULT_EFFORT','DEFAULT_DATE'}
got = {}
for n in t.body:
    if isinstance(n, ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0], ast.Name) \
       and n.targets[0].id in want:
        k = n.targets[0].id
        assert k not in got, ('twice at column zero', k)
        got[k] = ast.literal_eval(n.value)
assert set(got) == want, sorted(want - set(got))
print(sorted(got.items()))"
```

Expected: exit 0 and
`[('DEFAULT_DATE', '2026-08-06'), ('DEFAULT_EFFORT', 'high'), ('EFFORTS', ('high', 'medium', 'low')), ('NAME', 'gptoss'), ('STOP', ['<|return|>']), ('VERSION', 1)]`.
Run the same command against `models/probe_models/qwen.py` with
`want = {'VERSION','LORA_TARGETS'}` (`$PROBE` not needed; `ast` never imports),
expecting the seven Qwen target modules.

**A5 — `parse` over a chunked stream** (6.2).

```
python3 -c "
from models.agent_models import gptoss as g
full = ('<|channel|>analysis<|message|>I will look it up. Then act.<|end|>'
        '<|start|>assistant<|channel|>final<|message|>Here is the code.<|return|>')
st, out = {}, None
for i in range(0, len(full), 7):
    out = g.parse(full[i:i+7], st)
print(sorted(out)); print(repr(out['reasoning'])); print(repr(out['content']))
st2, o2 = {}, None
for piece in ('<|channel|>ana', 'lysis<|mess'):
    o2 = g.parse(piece, st2)
print(repr(o2['reasoning']), repr(o2['content']))"
```

Expected exactly:

```
['content', 'reasoning']
'I will look it up. Then act.'
'Here is the code.'
'' ''
```

**A6 — `end_of_turn`, and its ids against the library** (6.2, errata 7).

```
python3 -c "
from models.agent_models import gptoss as g
print(g.end_of_turn([1,2,200002]), g.end_of_turn([1,2,200012]),
      g.end_of_turn([1,2,200007]), g.end_of_turn([1,2,3]))"
external/probe-env/bin/python -c "
from openai_harmony import load_harmony_encoding, HarmonyEncodingName
from models.agent_models import gptoss as g
e = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
assert sorted(g.END_IDS) == sorted(e.stop_tokens_for_assistant_actions()), g.END_IDS
print('end ids ok')"
```

Expected: `True True False False`, then `end ids ok`.

**A7 — `wrap_prefetch`** (6.2, 7.3, errata 8).

```
python3 -c "
from models.agent_models import gptoss as g
print(repr(g.wrap_prefetch('show_playlists() = [..]', None)))
print(repr(g.wrap_prefetch('show_playlists() = [..]', 'Sometimes a prefetch appears.')))"
```

Expected exactly:

```
'<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>show_playlists() = [..]<|end|><|start|>assistant'
'<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>Sometimes a prefetch appears.\n\nshow_playlists() = [..]<|end|><|start|>assistant'
```

**A8 — `render_ids` equals vLLM's own renderer, without a server** (7.1's third
check, run on the CPU against vLLM 0.26.0's three functions; this is the legacy
judge of `legacy/tests/test_harmony_render.py:36-60`).

```
VLLM_SYSTEM_START_DATE=2026-08-06 external/vllm-env/bin/python - <<'EOF'
from vllm.entrypoints.openai.parser.harmony_utils import (
    build_harmony_preamble, extract_instructions_from_messages,
    parse_chat_inputs_to_harmony_messages, render_for_completion)
from models.agent_models import gptoss as g
def judge(msgs, effort):
    instr, rest = extract_instructions_from_messages(list(msgs))
    hm = build_harmony_preamble(instructions=instr, tools=None,
                                reasoning_effort=effort, with_custom_tools=False)
    hm.extend(parse_chat_inputs_to_harmony_messages(rest))
    return render_for_completion(hm)
base = [{"role":"system","content":"SYS rules"},
        {"role":"user","content":"Task from supervisor: Do X."}]
cases = {"base": base,
         "two": base+[{"role":"assistant","content":"```python\nprint(1)\n```"},
                      {"role":"user","content":"Execution output:\n1"}],
         "empty_assistant": base+[{"role":"assistant","content":""},
                                  {"role":"user","content":"Execution output:\n1"}],
         "literal_marker": base+[{"role":"assistant","content":"a<|end|>b"},
                                 {"role":"user","content":"Execution output:\n2"}]}
for k, m in cases.items():
    for eff in ("high","low"):
        print(k, eff, "equal:", judge(m, eff) == g.render_ids(m, eff, "2026-08-06"))
EOF
```

Expected: eight lines, every one ending `equal: True`. (Measured against
`legacy/pipeline/inject/harmony_render.py` on 2026-09-17: all eight already
pass, with 83/83/105/105/91/91/104/104 ids.)

**A9 — `render_ids` refuses an unpinned effort or date** (errata 9).

```
external/probe-env/bin/python -c "
from models.agent_models import gptoss as g
m = [{'role':'user','content':'hi'}]
for kw in ({'effort':None,'date':'2026-08-06'}, {'effort':'high','date':None},
           {'effort':'ultra','date':'2026-08-06'}):
    try: g.render_ids(m, kw['effort'], kw['date']); print('NO REFUSAL', kw)
    except Exception as e: print(type(e).__name__, str(e)[:60])"
```

Expected: three refusals, no `NO REFUSAL`.

**A10 — the probe object on a tiny CPU checkpoint** (6.2, 1.6). The fixture is
built by the command itself: a randomly initialised two-layer Qwen3 plus the real
Qwen3-0.6B-Base tokenizer (validated on 2026-09-17: 8 s, no GPU).

```
external/probe-env/bin/python - <<'EOF'
import json, pathlib, tempfile, torch
from transformers import AutoTokenizer, AutoModelForCausalLM, Qwen3Config
from models.probe_models import base
d = pathlib.Path(tempfile.mkdtemp()); best = d / "best"
tok = AutoTokenizer.from_pretrained(
    "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base")
cfg = Qwen3Config(vocab_size=len(tok), hidden_size=64, intermediate_size=128,
                  num_hidden_layers=2, num_attention_heads=4,
                  num_key_value_heads=2, head_dim=16, max_position_embeddings=512)
AutoModelForCausalLM.from_config(cfg).save_pretrained(best); tok.save_pretrained(best)
labels = ["apis.spotify.login", "apis.supervisor.show_profile"]
torch.save(torch.nn.Linear(64, 2).state_dict(), best / "head.pt")
(best / "meta.json").write_text(json.dumps(dict(
    backbone="qwen06", tuning="full", labels=labels, call_sep="\n[CALL] ",
    param_only=False, max_len=256, train_key="0123456789ab")))
p = base.load(None, None, probe_kind="classifier", ckpt_dir=best, device="cpu")
logits, names = p.score(["thinking so far", "another prefix"])
print("score", len(logits), len(logits[0]), names[0] in labels, p.max_len, p.labels == labels)
gen = base.load(None, None, probe_kind="generator", ckpt_dir=best, device="cpu")
out = gen.generate(["thinking so far"], 8, "\n[CALL] ")
print("gen", len(out), "\n" not in out[0])
p.save(d / "again", labels=labels, meta=dict(backbone="qwen06", tuning="full",
       max_len=256, train_key="0123456789ab"), extra=dict(call_sep="\n[CALL] ", param_only=False))
m = json.loads((d / "again" / "meta.json").read_text())
print("save", sorted(m), (d / "again" / "head.pt").exists())
EOF
```

Expected exactly:

```
score 2 2 True 256 True
gen 1 True
save ['backbone', 'call_sep', 'labels', 'max_len', 'param_only', 'train_key', 'tuning'] True
```

**A11 — `forward` at the `event_end` positions** (6.2, errata 5). Same fixture;
two events packed into one sequence, the classifier's `logits` carry one row per
event and match `score` on the same prefixes to 1e-4.

```
external/probe-env/bin/python -c "<the A10 fixture>; import torch
enc = p.tokenizer(['abc def', 'ghi'], padding=True, return_tensors='pt')
ends = torch.tensor([[0, int(enc['attention_mask'][0].sum())-1],
                     [1, int(enc['attention_mask'][1].sum())-1]])
out = p.forward(dict(input_ids=enc['input_ids'], attention_mask=enc['attention_mask'],
                     event_end=ends))
print(tuple(out.logits.shape), out.hidden.shape[-1])"
```

Expected: `(2, 2) 64`.

**A12 — the LoRA merge equals the base on a fresh adapter** (1.6; peft's B matrix
is zero-initialised, so a merge right after wrapping must be item-for-item
allclose — the invariant of `legacy/tests/test_lora_merge.py:1-12`). Build the
same tiny checkpoint, `load(..., cfg=<a stub with probe.tuning='lora', the four
lora fields and train.max_len>)`, `save` immediately, reload, and compare every
tensor of the two backbone state dicts.

Expected: `merge allclose True` and `7 lora layers` (the seven target modules of
`qwen.LORA_TARGETS` were really swapped).

**A13 — the probe service end to end on the CPU, render-only** (7.2). No GPU, no
`schema.py` path exercised; `--run-dir` is a fresh temporary directory, since the
server half reads no `settings.yaml`.

```
D=$(mktemp -d); external/probe-env/bin/python -m models.probe_models.service serve \
  --run-dir $D --agent-model gptoss120b --port 8599 --render-only > $D/srv.log 2>&1 &
# wait for $D/service_probe_0.json, then:
external/probe-env/bin/python -c "
from models.probe_models.service import Client
c = Client('http://127.0.0.1:8599')
h = c.health(); print(h['family'], h['weights'], h['render'], h['encode_special'],
                      h['temperature'], h['score_train_key'], h['max_len'])
print(c.encode('a<|end|>b', False)['ids'])
print(c.encode('a<|end|>b', True)['ids'])
print(c.decode(c.encode('a<|end|>b', False)['ids'])['text'])
r = c.render([{'role':'system','content':'SYS rules'},
              {'role':'user','content':'Task from supervisor: Do X.'}], 'high', '2026-08-06')
print(r['n_tokens'], len(r['prefix_ids']))
try: c.score('x'); print('NO 503')
except Exception as e: print('score refused')"
```

Expected exactly (the two encode lines were measured on 2026-09-17 with
transformers 5.14.1 and the gpt-oss-120b tokenizer):

```
gptoss gpt-oss-120b ids True None None None
[64, 27, 91, 419, 91, 29, 65]
[64, 200007, 65]
a<|end|>b
83 83
score refused
```

and `$D/service_probe_0.json` exists carrying `kind`, `replica`, `base_url`,
`host`, `port`, `pid`, `started_at`, `flags`, `claims`, `attached_to`.

**A14 — the agent service's command and environment, without a GPU** (7.1).

```
external/vllm-env/bin/python -c "
from models.agent_models.service import build_command
import models
m = models.agent('gptoss120b')
row = dict(role='agent', family='gptoss', weights='gpt-oss-120b', dtype='auto',
           quantization=None, max_model_len=131072, served_model_name='gpt-oss-120b',
           env_result={'VLLM_USE_FLASHINFER_SAMPLER': '0'}, extra_flags='')
argv, env = build_command(row, m.serving, m.weights_path, 8103, '0', '2026-08-06')
print(' '.join(argv[1:]))
print(sorted(env.items()))"
```

Expected: the argv line reads
`serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b
--served-model-name gpt-oss-120b --host 0.0.0.0 --port 8103
--gpu-memory-utilization 0.92 --tensor-parallel-size 1 --max-model-len 131072
--dtype auto`, with no `--quantization`; and the env holds
`CUDA_DEVICE_ORDER=PCI_BUS_ID`, `CUDA_VISIBLE_DEVICES=0`, `LD_LIBRARY_PATH`,
`TRITON_CACHE_DIR`, `VLLM_CACHE_ROOT`, `VLLM_SYSTEM_START_DATE=2026-08-06`,
`VLLM_USE_FLASHINFER_SAMPLER=0`.

**A15 — the completion request body** (7.1). Point a `Client` at a
`http.server` stub that records the body, iterate one SSE chunk, and print the
body's keys.

Expected: `model`, `prompt`, `max_tokens`, `temperature`, `add_special_tokens`,
`skip_special_tokens`, `return_token_ids`, `stream`, `stream_options` present;
`top_p`, `stop` and `seed` **absent** when they are None and present when they
are set; the iterator yields `('he', [123])` pairs and `usage` is filled after
`[DONE]`.

**A16 — selfcheck lines that apply to these files** (0.1, 0.2, 3.3, 5.3). Until
`run.py selfcheck` exists, these are the same tests as commands:

- every one of the nine files has its five annotation lines (`imports`,
  `used by`, `reads`, `writes`, `venv`) in `README.md`, matching the 0.2 entries
  quoted in section 1;
- `ast` over each file's imports equals its `imports:` line — in particular
  `models/probe_models/base.py` imports `models/__init__.py` and **not**
  `experimental_settings/schema.py` or `jobs/registry.py`; `models/__init__.py`
  imports no repo file; `models/agent_models/gptoss.py` imports no repo file and
  has `openai_harmony` **inside** `render_ids`;
- `VERSION` matches column zero exactly once in the five files that carry one and
  is absent from the three `__init__.py`;
- `schema.py`'s `generation.effort` axis literals are a subset of the union of
  every family module's `EFFORTS` (5.3) — today `{'high','medium','low'}` from
  `gptoss.py` alone;
- every `family:` value in `models/table.yaml` has a file:
  `models/agent_models/<family>.py` for an `agent` row,
  `models/probe_models/<family>.py` for a `probe` row;
- every `result.weights` value in `models/table.yaml` is a key of
  `constants/path_models.yaml`.

---

## 4. Acceptance, GPU or cross-host (for the main session)

None of these may be run by an implementer; each is a ready-to-run command for
the main session, through the gpu-run skill.

**G1 — the agent service starts, checks and serves.** On the host in the row
(`tokyo108`), with a run directory whose `settings.yaml` names `gptoss120b`:

```
external/vllm-env/bin/python -m models.agent_models.service serve \
  --run-dir <run_dir> --model gptoss120b --port 8103 --gpus 0 --replica 0
```

Must show: the three check-table lines pass — `/health` answers inside
`registry.DEFAULTS["launch_timeout_s"]`, `GET /v1/models` names
`gpt-oss-120b`, and **render equals server** for all four `CHECK_MESSAGES`
shapes, id for id; `<run_dir>/service_agent_0.json` appears with
`base_url: http://tokyo108:8103/v1`, the pid, and `claims` equal to the frozen
`result:` block plus `role` and `family`.

**G2 — the date really reaches the server** (9(a)#25). With
`generation.date: 2026-08-06`, the render-equals-server check passes; restart
the server with `VLLM_SYSTEM_START_DATE` unset and the same check must **fail**,
proving the variable is what pins the prefix and not the machine clock.

**G3 — attach** (7.1, 7.4). With G1's server still up, a second run's service
piece started with `--attach-only` on the same host and port exits 0, writes
`attached_to: <the first run_id>`, and takes no card; the same command against a
server whose `served_model_name` differs exits non-zero without attaching.

**G4 — the stream** (7.1). From `login_host`, in the AppWorld venv:
`Client('http://tokyo108:8103/v1', 'gpt-oss-120b').stream(prefix_ids,
{'max_tokens': 64, 'temperature': 1.0, 'top_p': None, 'stop': ['<|return|>']},
42)` yields `(text, ids)` pairs whose ids concatenate to a sequence
`gptoss.end_of_turn` reports True for, `usage` is filled, and `close()` partway
through returns immediately with `usage is None`.

**G5 — the probe service with real checkpoints on a card** (7.2). On a GPU host:

```
external/probe-env/bin/python -m models.probe_models.service serve \
  --run-dir <inject run_dir> --agent-model gptoss120b --port 8500 \
  --score-ckpt <ctool train run_dir> --gen-ckpt <cgen train run_dir> \
  --temperature <fitted T> --device cuda:0
external/probe-env/bin/python -m models.probe_models.service check \
  --base-url http://<that host>:8500 --run-dir <inject run_dir>
```

`check` must exit 0 and print each compared field; `/score` must return a `conf`
in [0,1] and a `label` from the checkpoint's `labels`; `/gen` must return one
line of call text. The `check` must be issued **from `login_host`**, proving the
server bound `0.0.0.0` and not loopback (7.2).

**G6 — the refusals on the card** (7.2, 5.7). Starting the probe service with a
`--gen-ckpt` whose `best/meta.json` says `param_only: true` must exit non-zero
naming that checkpoint, before any card is taken; `check` against a service
started with the wrong checkpoints must exit non-zero on
`score_train_key` / `gen_train_key`.

**G7 — a probe trained and reloaded** (1.6, 6.2). After the first real `train`
run of a `ctool` setting: `base.load(..., ckpt_dir=<run_dir>/best,
device='cuda:0')` reproduces the training run's own validation accuracy on the
val split to 1e-6, and a `lora` run's `best/` loads with the same call as a
`full` run's (the merge contract of 1.6).

---

## 5. Tickets

### M1 — the model table and the entrance

**Files.** `models/table.yaml`, `models/__init__.py`,
`models/agent_models/__init__.py`, `models/probe_models/__init__.py`.

**What to do.** Sections 1.1, 1.2, 1.3, 1.6 above: write the four-row table,
the two dataclasses and the two entrance functions with their refusals, and the
two empty package markers. No `VERSION` in any of the four.

**Acceptance.** A1 (restricted to `import models`), A2, A3, and the last two
bullets of A16 (every `family:` has a file — `gptoss.py` after M2 —, every
`result.weights` is a key of `constants/path_models.yaml`).

**Needs from other folders.** `constants/path_models.yaml` with the aliases
`gpt-oss-120b`, `qwen3-0.6b-base`, `qwen3-1.7b-base`, `qwen3-4b-base`. The
implementer must **not** create that file.

### M2 — the gpt-oss family module

**Files.** `models/agent_models/gptoss.py`.

**What to do.** Section 1.4: `VERSION`, `NAME`, `STOP`, `EFFORTS`,
`DEFAULT_EFFORT`, `DEFAULT_DATE`, `END_IDS`, `render_ids`, `parse`,
`end_of_turn`, `wrap_prefetch`, porting
`legacy/pipeline/inject/harmony_render.py:34-135`,
`legacy/pipeline/inject/live_appworld.py:111-148` and
`legacy/pipeline/inject/inject_format.py:36-37`, with the "not ported" list
honoured.

**Acceptance.** A1, A4, A5, A6, A7, A8, A9.

**Needs from other folders.** None. (M1 is a sibling ticket, not a blocker:
`gptoss.py` imports nothing; only A8's `models.agent_models` package path needs
M1's `__init__.py`.)

### M3 — the probe object and the Qwen backbone

**Files.** `models/probe_models/qwen.py`, `models/probe_models/base.py`.

**What to do.** Sections 1.7 and 1.8: the six backbone names, then `Batch`,
`Outputs`, `Probe` (a `torch.nn.Module` with `save`, `forward`, `score`,
`generate`, `enable_grad_checkpointing`) and `load`, porting
`legacy/pipeline/train/train_causal_tool.py:191-222,516-536`,
`legacy/pipeline/inject/probe_server.py:98-133,163-193` and
`legacy/pipeline/train/lora_util.py:75-138`. Honour errata 2-6: the training
dtype comes from the row, a restore's from `DTYPE` (cuda) or `float32` (cpu);
`event_end` is `[n_events, 2]`; a generator's `hidden` is None; `forward` moves
the tensors to the probe's device.

**Acceptance.** A4 (against `qwen.py`), A10, A11, A12, and the `base.py` bullet
of A16 (it imports `models/__init__.py` and neither `schema.py` nor
`registry.py`).

**Needs from other folders.** M1's `models.probe`. Nothing else — `cfg` is
annotated `object`, so no `experimental_settings/schema.py` import.

### M4 — the two services

**Files.** `models/agent_models/service.py`, `models/probe_models/service.py`.

**What to do.** Sections 1.5 and 1.9: for each file the server main (argparse,
the resolution rules, the checks, the endpoint file) and the standard-library
client, plus the probe service's `check` subcommand. Honour errata 10-15:
`--replica` on the agent serve line, `generation` as a four-key dict, dict
returns from every probe client method, the endpoint file's key names,
`ThreadingHTTPServer` with one lock, and the agent service's live-versus-frozen
comparison of `family` and `weights`.

**Acceptance.** A1, A13, A14, A15, and the `imports` bullet of A16 for both
files. G1-G6 are the main session's and are **not** this ticket's to run: an
implementer that needs a GPU returns BLOCKED with the ready-to-run command.

**Needs from other folders.** M1 (`models.agent`), M2 (`render_ids` for the
agent service's check table and the probe service's `/render`), M3
(`base.load` inside `serve()`), and `experimental_settings/schema.py` —
`load_frozen(run_dir) -> Setting` carrying `models.agent_row`,
`generation.effort`, `generation.date`, `_upstream["probe_score.train"]`,
`_upstream["probe_gen.train"]`, `_resolved.probe_temperature`, and `inject`
being None on a setting without that section (5.1). `jobs/launch.py` must pass
`--replica <i>` to the agent service piece and `--render-only` to a `sample`
run's probe piece (2.1's piece rule).

---

## 6. Contract errata settled here

Each line is also appended to
`.scratch/from-zero/contract-errata.md`.

1. **6.1** writes `dtype: bfloat16` in `gptoss120b`'s `result:` block -> the
   table writes `dtype: auto`, the value today's launcher effectively used
   (`legacy/serve_preset.py:41-48` passes no `--dtype`), because an explicit
   `bfloat16` over the mxfp4 checkpoint is a different server.
2. **6.1** writes `dtype: bfloat16` in `qwen06`'s `result:` block -> the table
   writes `dtype: float32`, because `legacy/pipeline/train/train_causal_tool.py:196`
   loads the backbone in fp32 and autocasts bf16; loading bf16 weights changes
   full-tuning numerics under an identical key. The bf16 cast stays on the
   restore path, as `qwen.DTYPE`.
3. **6.2**'s `load` signature carries no device, while 7.2's `serve` takes
   `--device` and 1.6's restore has nowhere else to put it -> `load(..., device="cpu")`,
   and a restore with no row takes its dtype from the backbone module's `DTYPE`
   on a cuda device and `float32` on cpu.
4. **6.2** says `Outputs.logits` and `Outputs.hidden` are "both aligned to
   `input_ids`" and, four lines later, that a classifier's logits carry one row
   per event -> a classifier's `logits` are `[n_events, n_labels]` with `hidden`
   `[B, T, dim]`; a generator's `logits` are `[B, T, vocab]` with `hidden` None.
5. **6.2** makes `Batch["event_end"]` "the position of the last non-pad token of
   each event", which cannot say which sequence an event sits in -> `event_end`
   is a LongTensor of shape `[n_events, 2]` holding `(row, col)` index pairs into
   `input_ids`, the two lists `legacy/.../train_causal_tool.py:170-186` carried.
6. **6.2** names no way to move the probe to a card, build the optimizer's
   parameter list or turn on gradient checkpointing -> `Probe` subclasses
   `torch.nn.Module` with `backbone`, `head`, `tokenizer`, `max_len`, `labels`,
   `probe_kind`, `lora`, and offers `enable_grad_checkpointing()`
   (`legacy/.../lora_util.py:122-138`); `forward` moves every tensor of `Batch`
   to the probe's device, so a method builds CPU tensors.
7. **6.2** puts `end_of_turn` under `venv: any`, where `openai_harmony` is absent
   -> `gptoss.py` carries `END_IDS = (200002, 200012)` as a module literal,
   measured from `openai_harmony` 0.0.8's `stop_tokens_for_assistant_actions()`
   on 2026-09-17, with an acceptance command comparing the two.
8. **7.3/6.2** say a `p2` entry's `system_text` is applied "by the family's
   `wrap_prefetch`" without saying where -> `wrap_prefetch` puts
   `system_text + "\n\n"` in front of the body **inside** the prefetch message,
   and is unchanged on None.
9. **6.2** types `render_ids`'s `effort` and `date` as `str | None` ->
   `gptoss.render_ids` refuses None for either, naming the field, since 5.2 has
   the loader resolve both before the freeze and
   `legacy/.../harmony_render.py:86` refuses an unpinned date for the same
   reason.
10. **7.1**'s serve command line has no replica, while 7.4 names the endpoint
    file `service_agent_<replica>.json` -> `serve` takes `--replica <i>`
    (default 0) and `jobs/launch.py` passes it.
11. **7.1** gives `stream(prompt_ids, generation, seed)` no shape for
    `generation`, and the per-request `max_tokens` (`max_step_tokens` minus the
    ids already generated, `legacy/.../live_appworld.py:449`) has no other
    source -> `generation` is a dict with exactly `max_tokens`, `temperature`,
    `top_p`, `stop`, built by `agent/generate.py`; `top_p`, `stop` and `seed`
    are left out of the body when None; a 400 re-raises as
    `urllib.error.HTTPError` and everything else retries three times.
12. **7.3** writes `probe_client.render(...) -> prefix_ids` while 7.2's route
    returns a body -> every probe client method returns the route's decoded JSON
    dict, `render` included, and a caller takes `["prefix_ids"]`.
13. **1.5** names `service_<kind>_<replica>.json`'s fields in prose only -> the
    file holds `kind`, `replica`, `base_url`, `host`, `port`, `pid`,
    `started_at`, `flags`, `claims`, `attached_to`; `claims` is the frozen
    `result:` block plus `role` and `family` for the agent service and
    `{family, weights, score_train_key, gen_train_key, max_len, temperature}`
    for the probe service; the agent `base_url` ends in `/v1`, the probe's does
    not.
14. **7.2** leaves the server's concurrency open, and one probe service answers
    `sample.pieces` loop processes at once (legacy served one driver,
    `probe_server.py:277`) -> `ThreadingHTTPServer` with one lock around every
    model call.
15. **6.2** lists two exceptions to "every keyed column is read from the frozen
    setting" and leaves out the agent service, which 0.2 gives the
    `models/__init__.py` import -> `models/agent_models/service.py` resolves
    `family` and `weights` live through `models.agent(alias)` and compares both
    against `cfg.models.agent_row` before its first use, refusing on a
    difference.
