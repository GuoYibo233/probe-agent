# 06 the model table, the entrance, the gpt-oss family and the probe object

Status: ready-for-agent
Blocked by: 01
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 7, 9)

## What to do

Seven files. Contracts 6.1 (the table), 6.2 (the two model modules and the probe
object), 1.6 (the checkpoint layout) and 6.3 (`constants/`) are the
specification; read 6.1, 6.2 and 1.6 in full. The two services are ticket 07 and
are **not** in this ticket.

```
models/table.yaml                  data file; read by models/__init__.py, schema.py,
                                   models/agent_models/service.py, jobs/launch.py
models/__init__.py                 venv any   imports: none (repo); [importlib, PyYAML]   no VERSION
models/agent_models/__init__.py    venv any   empty package marker, no VERSION
models/agent_models/gptoss.py      venv any at import and for parse/end_of_turn/wrap_prefetch;
                                   probe or vllm for render_ids()                          VERSION = 1
models/probe_models/__init__.py    venv any   empty package marker, no VERSION
models/probe_models/qwen.py        venv probe   imports: none (repo); [transformers]       VERSION = 1
models/probe_models/base.py        venv probe   imports: models/__init__.py;
                                   models/probe_models/<backbone>.py (by name, inside load());
                                   [torch, transformers, peft]                             VERSION = 1
README.md                          your seven lines only
```

Every Python file starts with `from __future__ import annotations`.
`models/table.yaml` is protected by the read-only hook. **The main session arms
the hook after this wave merges** — the construction plan's section 1 table says
so, and this ticket is the one that writes the file — so write it here and never
again.

### 1. `models/table.yaml` (contracts 6.1)

Four rows: the two the contract spells out, plus the two extra probe backbones
this project already trains on (`legacy/pipeline/train/train_causal_tool.py:84-88`
hardcoded three Qwen tiers; the tree makes each a row).

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

**Two decisions already made (errata), both departures from 6.1's example row:**
`gptoss120b.result.dtype` is `auto`, not `bfloat16` — the value today's launcher
effectively used (`legacy/serve_preset.py:41-48` passes no `--dtype`), because an
explicit `bfloat16` over the mxfp4 checkpoint is a different server. And
`qwen06.result.dtype` is `float32`, not `bfloat16` — `train_causal_tool.py:196`
loads the backbone fp32 and autocasts bf16, so loading bf16 weights would change
full-tuning numerics under an identical key; the bf16 cast stays on the restore
path as `qwen.DTYPE`.

Sources: `legacy/configs/presets/default.json:4-15` (host, port,
`served_model_name`, `gpu_memory_utilization`, `VLLM_USE_FLASHINFER_SAMPLER=0`,
`LD_LIBRARY_PATH`); `legacy/envs/serve_logs/launch_vllm_awdiag.py:1-20,58-60`
(`max_model_len` 131072, the three cache variables — the cache redirection exists
because `/home` has an NFS quota that has already killed a vLLM);
`legacy/configs/models.json:24-39`.

Not ported: `legacy/configs/presets/*.json`'s whole `client:` block (`api`,
`reasoning_effort`, `temperature`, `top_p`, `max_tokens`, `stop`, `start_date`,
`seed`) — every one is a field of the `generation:` section; the two other
presets; the `desc` field; `models.json:45-48`'s `aliases:` block.

### 2. `models/__init__.py` (contracts 6.2)

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
class ProbeModel:         # the same shape, minus `module`
    alias: str
    role: str
    family: str
    weights: str
    weights_path: str
    serving: dict

def agent(alias: str) -> AgentModel
def probe(alias: str) -> ProbeModel
```

- `weights` is **always the alias** and `weights_path` **always the directory**.
- `agent()` refuses a row whose `role` is not `agent`, `probe()` a row whose
  `role` is not `probe`, and both refuse an unknown alias, naming the sorted known
  aliases of that role (the message shape of `legacy/model_registry.py:23-24`).
- `agent()` imports `models.agent_models.<family>` with
  `importlib.import_module` **inside the function** and refuses, naming the
  expected file path, when the module is missing. `probe()` imports nothing —
  `models/probe_models/base.py` imports the backbone module inside `load()`.
- `weights_path`: look the `result.weights` alias up in
  `constants/path_models.yaml`; an absolute path that does not exist raises
  `FileNotFoundError` naming the alias and the path (ported verbatim from
  `legacy/model_registry.py:26-27`, which exists to catch an unmounted NFS); a
  value that does not start with `/` is a hub id and passes through unchecked.
- `serving` is the row's `serving:` block, `{}` when absent.
- Both YAML files are found relative to the repo root,
  `Path(__file__).resolve().parents[1]`. No `VERSION`.

Legacy source: `legacy/model_registry.py:15-28`; `legacy/preset_loader.py:56-59`.
Not ported: `ALIASES` and the `name.lower()` normalisation
(`model_registry.py:18,22`); the `__main__` CLI listing (`:31-37`);
`preset_loader.base_url_of` (`:150-155`) — a base URL comes from a service
endpoint file now.

### 3. The two empty package markers

`models/agent_models/__init__.py` and `models/probe_models/__init__.py`: a
one-line docstring and nothing else — no imports, no `VERSION`, no re-export.
They exist so the **client half** of each `service.py` imports without the
family's libraries and without torch (contracts 0.2).

### 4. `models/agent_models/gptoss.py` (contracts 6.2)

```python
VERSION = 1
NAME = "gptoss"
STOP = ["<|return|>"]                     # 5.2's default of generation.stop
EFFORTS = ("high", "medium", "low")       # 5.3 validates generation.effort against it
DEFAULT_EFFORT = "high"
DEFAULT_DATE = "2026-08-06"
END_IDS = (200002, 200012)                # <|return|>, <|call|>

def render_ids(messages: list[dict], effort: str | None, date: str | None) -> list[int]
def parse(text_delta: str, state: dict) -> dict          # {"reasoning": str, "content": str}
def end_of_turn(ids: list[int]) -> bool
def wrap_prefetch(body: str, system_text: str | None) -> str
```

The first six names are read as **source text** by `experimental_settings/schema.py`:
column zero, exactly once, a plain literal.

- `render_ids` is `legacy/pipeline/inject/harmony_render.py:34-135` moved whole:
  the `EFFORT` table, `to_harmony_messages` (a leading system/developer message
  becomes the harmony developer instructions, an assistant turn with empty
  content is dropped, a mid-conversation system/developer message becomes another
  developer message), then
  `render_conversation_for_completion(conv, Role.ASSISTANT,
  RenderConversationConfig(auto_drop_analysis=False))`. The encoding object is
  built once and cached in a module global (`harmony_render.py:46-53`). It
  refuses a message carrying `tool_calls` / `reasoning` / `thinking`, and an
  unknown role, rather than falling through (`:88-93`). **It refuses
  `effort=None` and `date=None`, naming the field** (errata: 6.2 types both
  `str | None`, but 5.2 resolves both before the freeze and
  `harmony_render.py:86` refuses an unpinned date). The `openai_harmony` import
  sits **inside** the function.
- `parse(text_delta, state)` accumulates the raw generated text in `state` and
  returns the two channels grown so far under exactly `reasoning` and `content`,
  by the rule of `legacy/pipeline/inject/live_appworld.py:111-148` (`parse_step`):
  split on `<|end|>`, a valid header is
  `[<|start|>assistant[ to=x]]<|channel|>CH` followed by `<|message|>`,
  `analysis` bodies join into `reasoning` with `\n`, `final` and recipient-less
  `commentary` bodies join into `content` with `\n`, everything from a literal
  `<|return|>` on is cut. A half-written header contributes nothing. Per-family
  bookkeeping stays in `state`; the returned dict carries those two keys and
  nothing else (a third spelling gives an empty thinking text and an inject run
  that never fires).
- `end_of_turn(ids)` is `ids[-1] in END_IDS`. It **may not import
  `openai_harmony`**: it runs under `venv: any` and the AppWorld venv has no
  `openai_harmony`. **Decision already made (errata):** `END_IDS = (200002,
  200012)`, measured from `openai_harmony` 0.0.8's
  `stop_tokens_for_assistant_actions()` on 2026-09-17, with A6 comparing the two.
- `wrap_prefetch(body, system_text)` is
  `legacy/pipeline/inject/inject_format.py:36-37`'s `TAIL`:
  `"<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>" + body +
  "<|end|><|start|>assistant"`, with `system_text + "\n\n"` in front of `body`
  when `system_text` is not None (errata), unchanged on None. The sender is
  `prefetch` and not `python` on purpose (CONTEXT, "prefetch sender").

Legacy sources: `harmony_render.py:34-135`; `live_appworld.py:111-148`;
`inject_format.py:36-37`; `rebuild.py:81` and
`legacy/configs/presets/default.json:18,23` (`DEFAULT_EFFORT`, `DEFAULT_DATE`).
Not ported: `harmony_render.decode` (`:138-140`); `rebuild.py`'s whole jinja text
path (`build_prefix:161-207`, `assert_date`, `has_literal_harmony`,
`thinking_prefix`, `needs_guard_bypass`, `check_system_verbatim`);
`rebuild.SYSTEM` and `NO_CODE_MSG` (those are the environment's);
`rebuild.ANALYSIS_OPEN`; `rebuild.COLLECT_DATE`; `inject_format.py`'s `sep_for`,
`system_extra`, `needs_special`, `splice_text`, `FORMATS`, `is_prefetch_header`
(those belong to `agent/inject_format.py`, ticket 11).

### 5. `models/probe_models/qwen.py` (contracts 6.2)

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
  `pad_token_id` is None; `truncation_side = "left"` (keep the tail of the
  thinking); `padding_side = "right"` (every supervision position is a real
  token) — `legacy/pipeline/train/train_causal_tool.py:213-217`, and the
  `truncation_side` warning of `legacy/pipeline/inject/probe_server.py:111-116`
  becomes this unconditional set.
- `attach_head(model, n_labels)` returns `torch.nn.Linear(h, n_labels)` in
  float32, with `h = model.config.get_text_config().hidden_size`
  (`train_causal_tool.py:196-198`). The class order is the caller's: the backbone
  never sees the names.

Not ported: `train_causal_tool.py:84-88`'s `MODELS` dict;
`lora_util.py:39-42`'s `DEFAULT_RANK/ALPHA/DROPOUT/LR`.

### 6. `models/probe_models/base.py` (contracts 6.2, 1.6)

```python
VERSION = 1

Batch = dict[str, Any]      # keys forward consumes: input_ids, attention_mask,
                            # event_end, position_ids (optional); every other key
                            # is the method's own and base.py never reads it

@dataclass
class Outputs:
    logits: Tensor          # classifier: [n_positions, n_labels]; generator: the LM head at event_end
    hidden: Tensor | None   # classifier: [B, T, dim] at HEAD_LAYER; generator: None

class Probe(torch.nn.Module):
    backbone; head; tokenizer; max_len: int; labels: list[str] | None
    probe_kind: str; lora                      # the peft wrapper, or None
    def save(self, dir, *, labels=None, extra=None, meta=None) -> None
    def forward(self, batch: Batch) -> Outputs
    def score(self, texts: list[str]) -> tuple[list[list[float]], list[str]]
    def generate(self, texts: list[str], max_new: int, call_sep: str) -> list[str]
    def trainable_parameters(self) -> list
    def set_training(self, flag: bool) -> None
    def grad_checkpointing(self, enabled: bool) -> None

def load(row, cfg, *, probe_kind, n_labels=None, labels=None,
         ckpt_dir=None, device="cpu") -> Probe
```

**Four decisions already made (errata):**

- **`Batch["event_end"]`** is an int64 tensor of shape `[n_positions, 2]` holding
  `(sequence index, token position)` pairs naming **every position the head is
  applied at** — one per example row for a classifier, one per target token for a
  generator — and `Outputs.logits` has one row per entry **in that order**. 6.2's
  "the position of the last non-pad token of each event" cannot name the sequence
  an event sits in; the two lists
  `legacy/pipeline/train/train_causal_tool.py:170-186` carried are what this
  replaces.
- **`Outputs`**: a classifier's `logits` are `[n_positions, n_labels]` with
  `hidden` `[B, T, dim]`; a generator's `logits` are the **LM head applied at
  `event_end` only** with `hidden` None. Full-position logits are never computed
  (`legacy/pipeline/train/train_causal_share.py:140-175` exists to avoid that
  memory blow-up).
- **The three trainer handles** are `trainable_parameters()`, `set_training(flag)`
  and `grad_checkpointing(enabled)` — the names `train/utils/trainer.py` calls.
  `grad_checkpointing(True)` calls `backbone.gradient_checkpointing_enable()`,
  sets `config.use_cache = False`, and under LoRA calls
  `enable_input_require_grads()` once (`lora_util.py:122-138`; without it a
  checkpointed segment builds no graph and the adapter silently gets no
  gradient).
- **`load` takes `device="cpu"`**, and a restore with no row takes its dtype from
  the backbone module's `DTYPE` on a cuda device and `float32` on cpu.

Behaviour:

- `load` imports `models.probe_models.<family>` by name **inside the function**,
  the family coming from `row["family"]` when a row is given and from
  `models.probe(meta["backbone"]).family` on a restore. `row` **is**
  `cfg.models.probe_row` — `role`, `family` and the `result:` block — and the
  absolute weights path is the one live value, taken through
  `models.probe(cfg.models.probe).weights_path`. **`cfg` is annotated `object`**,
  so this file imports no `schema.py`, and it reads exactly `cfg.probe.tuning`,
  the four `cfg.probe.lora_*` fields, `cfg.train.max_len` and `cfg.models.probe`
  — nothing else.
- `probe_kind == "classifier"` builds `AutoModel.from_pretrained(path,
  dtype=<dtype>)` and calls the backbone's `attach_head(model, n_labels)`;
  `probe_kind == "generator"` builds `AutoModelForCausalLM.from_pretrained` and
  attaches no head (`train_causal_tool.py:191-208`, `probe_server.py:122-133`).
  After `prepare_tokenizer`, when `model.config.get_text_config().pad_token_id`
  is None it is set to the tokenizer's (`train_causal_tool.py:220-221`).
- `cfg.probe.tuning` is dispatched through an explicit mapping whose `else`
  raises, naming the axis and the value. `lora` wraps the backbone with
  `peft.get_peft_model(LoraConfig(r=lora_r, lora_alpha=lora_alpha,
  lora_dropout=lora_dropout, target_modules=<lora_targets or the backbone's
  LORA_TARGETS>, bias="none"))` and keeps the wrapper in `self.lora` for the
  merge on save (`lora_util.py:75-90`). **peft is imported inside the `lora`
  branch only** (`lora_util.py:8-12`).
- `ckpt_dir` restores: weights and tokenizer from that directory (LoRA was merged
  at save time, so a restore is a plain `from_pretrained`), `head.pt` for a
  classifier, and `labels`, `tuning`, `max_len`, `backbone` from
  `<ckpt_dir>/meta.json`; the `head_labels` hook is not called. `row` and `cfg`
  are both None on that path.
- `save(dir, *, labels, extra, meta)` writes 1.6's layout: the merged weights
  (`copy.deepcopy(self.lora).merge_and_unload().save_pretrained(dir)`, then the
  copy is freed and `torch.cuda.empty_cache()` is called, `lora_util.py:93-119`)
  or `backbone.save_pretrained(dir)`; the tokenizer; `head.pt` for a classifier;
  and `meta.json` holding `labels` plus every key of `meta` and every key of
  `extra`, **merged without reading them** (so neither shared file branches on
  the method).
- `forward` moves the four tensor keys to the probe's device, calls the backbone
  with `use_cache=False`, and for a classifier reads `getattr(out, HEAD_LAYER)`
  and applies the head at the `event_end` positions in float32
  (`train_causal_tool.py:200-208`); for a generator it applies the LM head at
  `event_end` and returns `hidden=None`.
- `score(texts)` tokenizes with `truncation=True, max_length=self.max_len,
  padding=True`, takes each row's **last non-pad token**, applies the head, and
  returns the class logits in `labels` order plus the argmax class name per text
  — the served form of the `event_end` rule, ported from
  `probe_server.py:163-177` **with the softmax and the temperature removed**: the
  service applies them (7.2).
- `generate(texts, max_new, call_sep)` builds `text + call_sep`, encodes with
  `add_special_tokens=False, truncation=True,
  max_length=max(self.max_len - max_new, 1)`, generates greedily
  (`do_sample=False`), decodes the continuation with `skip_special_tokens=True`,
  and returns the first line stripped (`probe_server.py:179-193`). The separator
  is the caller's.

Legacy sources: `train_causal_tool.py:191-208` (`CausalProbe`), `:211-222`
(`build`), `:516-536` (the `best/` save); `probe_server.py:98-133` (the two
loaders), `:163-193` (score and gen); `lora_util.py:75-138`.
Not ported: `train_causal_tool.py`'s data loading, `collate`, `align_check`,
`evaluate` and the whole `main` (`:97-188, 226-288, 305-543`); `readonly_map`
and `--readonly-env`; `best/label_map.json` and `meta.json`'s `n_labels`,
`base_path`, `env`, `data`, `epoch`, `transformers` (`:524-536`);
`lora_util.add_args`, `resolve_lr`, `meta_block`, `opt_params` (`:45-72,
141-156`) — the optimizer's parameter list is `trainer.py`'s, through
`probe.trainable_parameters()`.

## Acceptance

Run from the repo root and paste the real output.

```bash
SYS=python3
PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python
AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
VL=/home/y-guo/reproduce/new1/external/vllm-env/bin/python
```

**A1 — every `any` file imports under four interpreters.**
```bash
for P in "$SYS" "$AW" "$PR" "$VL"; do
  $P -c "import models, models.agent_models.gptoss; print('ok')" || exit 1; done
```
Expected: four lines `ok`, exit 0. (`models.probe_models.base` and
`models.probe_models.qwen` are **not** in this list: their venv is `probe`.)

**A2 — the two entrances resolve.**
```bash
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

**A3 — the entrances refuse.**
```bash
python3 -c "
import models
for call, arg in ((models.agent,'qwen06'), (models.probe,'gptoss120b'), (models.agent,'nosuch')):
    try: call(arg); print('NO REFUSAL', arg)
    except Exception as e: print(type(e).__name__, str(e)[:80])"
```
Expected: three lines, none of them `NO REFUSAL`; the first two messages name the
row's actual role, the third lists the known agent aliases.

**A4 — the literals are readable the way `schema.py` reads them.**
```bash
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
python3 -c "
import ast, pathlib
t = ast.parse(pathlib.Path('models/probe_models/qwen.py').read_text())
want = {'VERSION','LORA_TARGETS'}
got = {n.targets[0].id: ast.literal_eval(n.value) for n in t.body
       if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in want}
assert set(got) == want
print(got['VERSION'], len(got['LORA_TARGETS']), got['LORA_TARGETS'])"
```
Expected: `[('DEFAULT_DATE', '2026-08-06'), ('DEFAULT_EFFORT', 'high'), ('EFFORTS', ('high', 'medium', 'low')), ('NAME', 'gptoss'), ('STOP', ['<|return|>']), ('VERSION', 1)]`
then `1 7 ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']`.

**A5 — `parse` over a chunked stream.**
```bash
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

**A6 — `end_of_turn`, and its ids against the library.**
```bash
python3 -c "
from models.agent_models import gptoss as g
print(g.end_of_turn([1,2,200002]), g.end_of_turn([1,2,200012]),
      g.end_of_turn([1,2,200007]), g.end_of_turn([1,2,3]))"
"$PR" -c "
from openai_harmony import load_harmony_encoding, HarmonyEncodingName
from models.agent_models import gptoss as g
e = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
assert sorted(g.END_IDS) == sorted(e.stop_tokens_for_assistant_actions()), g.END_IDS
print('end ids ok')"
```
Expected: `True True False False`, then `end ids ok`.

**A7 — `wrap_prefetch`.**
```bash
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

**A8 — `render_ids` equals vLLM's own renderer, without a server** (CPU, in the
vllm venv; this is the legacy judge of `legacy/tests/test_harmony_render.py:36-60`).
```bash
VLLM_SYSTEM_START_DATE=2026-08-06 "$VL" - <<'EOF'
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
`legacy/pipeline/inject/harmony_render.py` on 2026-09-17: all eight already pass,
with 83/83/105/105/91/91/104/104 ids.)

**A9 — `render_ids` refuses an unpinned effort or date.**
```bash
"$PR" -c "
from models.agent_models import gptoss as g
m = [{'role':'user','content':'hi'}]
for kw in ({'effort':None,'date':'2026-08-06'}, {'effort':'high','date':None},
           {'effort':'ultra','date':'2026-08-06'}):
    try: g.render_ids(m, kw['effort'], kw['date']); print('NO REFUSAL', kw)
    except Exception as e: print(type(e).__name__, str(e)[:60])"
```
Expected: three refusals, no `NO REFUSAL`.

**A10 — the probe object on a tiny CPU checkpoint** (about 8 s, no GPU).
```bash
"$PR" - <<'EOF'
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

# --- A11: forward at the event_end positions, same fixture, same process ---
enc = p.tokenizer(["abc def", "ghi"], padding=True, return_tensors="pt")
ends = torch.tensor([[0, int(enc["attention_mask"][0].sum()) - 1],
                     [1, int(enc["attention_mask"][1].sum()) - 1]])
out = p.forward(dict(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                     event_end=ends))
print("forward", tuple(out.logits.shape), out.hidden.shape[-1])
EOF
```
Expected exactly:
```
score 2 2 True 256 True
gen 1 True
save ['backbone', 'call_sep', 'labels', 'max_len', 'param_only', 'train_key', 'tuning'] True
forward (2, 2) 64
```

**A11 — `forward` at the `event_end` positions.** Two positions named in one
batch, the classifier's `logits` carrying one row per entry in that order. It is
**the tail of A10's one script**, printed above as `forward (2, 2) 64`, because
`p` and the tiny checkpoint have to be in scope; run A10 and paste that line here
too.

**A12 — the LoRA merge equals the base on a fresh adapter.** peft's B matrix is
zero-initialised, so a merge right after wrapping must be item-for-item allclose
(the invariant of `legacy/tests/test_lora_merge.py:1-12`).
```bash
"$PR" - <<'EOF'
import json, pathlib, tempfile, types, torch
from transformers import AutoTokenizer, AutoModel, Qwen3Config
import models
from models.probe_models import base

d = pathlib.Path(tempfile.mkdtemp()); src = d / "tiny"
tok = AutoTokenizer.from_pretrained(
    "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base")
mc = Qwen3Config(vocab_size=len(tok), hidden_size=64, intermediate_size=128,
                 num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                 head_dim=16, max_position_embeddings=512)
AutoModel.from_config(mc).save_pretrained(src); tok.save_pretrained(src)

# The one live value load() takes is models.probe(alias).weights_path (6.2). Point it
# at the tiny checkpoint so this runs on the CPU in seconds; base.py reaches the
# entrance as models.probe(...) through its `import models`, which is what makes the
# substitution possible and is part of the contract for this file.
models.probe = lambda alias: types.SimpleNamespace(
    alias=alias, role="probe", family="qwen", weights="qwen3-0.6b-base",
    weights_path=str(src), serving={})

row = {"role": "probe", "family": "qwen", "weights": "qwen3-0.6b-base", "dtype": "float32"}
cfg = types.SimpleNamespace(
    models=types.SimpleNamespace(probe="qwen06", probe_row=row),
    probe=types.SimpleNamespace(tuning="lora", lora_r=16, lora_alpha=32,
                                lora_dropout=0.05, lora_targets=None),
    train=types.SimpleNamespace(max_len=256))
labels = ["apis.a.x", "apis.b.y"]
p = base.load(row, cfg, probe_kind="classifier", n_labels=2, labels=labels, device="cpu")
wrapped = p.lora if p.lora is not None else p.backbone
targets = sorted({n.rsplit(".lora_A", 1)[0].rsplit(".", 1)[-1]
                  for n, _ in wrapped.named_modules() if n.endswith("lora_A")})
print(len(targets), "lora targets", targets)

p.save(d / "merged", labels=labels,
       meta=dict(backbone="qwen06", tuning="lora", max_len=256, train_key="0123456789ab"),
       extra=dict(call_sep="\n[CALL] ", param_only=False))
base_sd = AutoModel.from_pretrained(src, dtype=torch.float32).state_dict()
merged_sd = AutoModel.from_pretrained(d / "merged", dtype=torch.float32).state_dict()
assert sorted(base_sd) == sorted(merged_sd), set(base_sd) ^ set(merged_sd)
print("merge allclose", all(torch.allclose(base_sd[k], merged_sd[k], atol=1e-6)
                            for k in base_sd))
print("no adapter file", not list((d / "merged").glob("adapter_*")))
print("tuning", json.loads((d / "merged" / "meta.json").read_text())["tuning"])
EOF
```
Expected exactly:
```
7 lora targets ['down_proj', 'gate_proj', 'k_proj', 'o_proj', 'q_proj', 'up_proj', 'v_proj']
merge allclose True
no adapter file True
tuning lora
```
(the seven target modules of `qwen.LORA_TARGETS` were really swapped; the count is
of distinct target **names**, not of instances — this two-layer model holds
fourteen of them).

**A16 — the annotation and literal rules for these seven files.**
```bash
python3 - <<'PY'
import ast, pathlib, yaml
# base.py imports models/__init__.py and neither schema.py nor registry.py
t = ast.parse(pathlib.Path('models/probe_models/base.py').read_text())
mods = {n.module for n in ast.walk(t) if isinstance(n, ast.ImportFrom) and n.module}
mods |= {a.name for n in ast.walk(t) if isinstance(n, ast.Import) for a in n.names}
assert not any(m.startswith('experimental_settings') or m.startswith('jobs') for m in mods), mods
assert any(m == 'models' or m.startswith('models') for m in mods), mods
# gptoss.py imports no repo file, and openai_harmony is inside render_ids
g = ast.parse(pathlib.Path('models/agent_models/gptoss.py').read_text())
top = [a.module or a.names[0].name for a in g.body if isinstance(a, (ast.Import, ast.ImportFrom))]
assert not any('openai_harmony' in (m or '') for m in top), top
# VERSION counts
import subprocess
for f, want in [('models/agent_models/gptoss.py',1), ('models/probe_models/qwen.py',1),
                ('models/probe_models/base.py',1), ('models/__init__.py',0),
                ('models/agent_models/__init__.py',0), ('models/probe_models/__init__.py',0)]:
    n = sum(1 for l in pathlib.Path(f).read_text().splitlines() if l.startswith('VERSION = '))
    assert n == want, (f, n, want)
# every family has a file, every weights alias has a row
tbl = yaml.safe_load(open('models/table.yaml')); pm = yaml.safe_load(open('constants/path_models.yaml'))
for alias, row in tbl.items():
    sub = 'agent_models' if row['role'] == 'agent' else 'probe_models'
    assert pathlib.Path(f"models/{sub}/{row['family']}.py").exists(), alias
    assert row['result']['weights'] in pm, alias
print('A16 ok')
PY
grep -n "/home/\|/net/" models/*.py models/agent_models/*.py models/probe_models/*.py || echo NO_ABS_PATH
```
Expected: `A16 ok`, then `NO_ABS_PATH`.

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: every `family:` value in
`models/table.yaml` has a file under `agent_models/` or `probe_models/` per its
`role`; every `result.weights` value is a key of `constants/path_models.yaml`;
`generation.effort`'s axis literals are within the union of every family's
`EFFORTS`, and each family's `DEFAULT_EFFORT` is in its own `EFFORTS`; each
family module imports under the probe **and** the vllm interpreter; one
column-zero `VERSION` in the three files that carry one and none in the other
four. A1, A4 and A16 are the hand-run stand-ins.

### GPU / main session — not yours

`M-M1` the agent service starts and passes its check table (needs ticket 07).
`M-M2` the date reaches the server. `M-M5` the probe service with real
checkpoints on a card. `M-M7` a trained probe reloads from `best/` and reproduces
its validation accuracy to 1e-6, LoRA and full alike — the real-weights form of
A10 and A12.

## Comments
