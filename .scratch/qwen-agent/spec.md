# Qwen as the agent model: plan

Written 2026-10-01 while gyb is away (his instruction: "keep everything else the same, but
substitute gpt-oss with Qwen; for Qwen's distinct settings, research them"). The
collection settings are those of `.scratch/full-history-probe/spec.md`; only the agent
model and what is specific to it change.

Status labels: DECIDED (gyb's word), PROPOSED (mine, waiting for his word), FACT.

## 1. What the research found (one Opus agent, own knowledge first, then fetched sources)

- The model closest to gpt-oss-120b's role (open weights, reasoning on, one card) is a
  Qwen mixture-of-experts model with about 3B active parameters: Qwen3-30B-A3B-Thinking-2507
  (thinking always on, 262,144-token native window, 61 GB in bf16) or Qwen3.5-35B-A3B
  (thinking switchable, 72 GB in bf16, carries a vision encoder). Neither was on the net
  disk; both are being downloaded to `/net/tokyo100-10g/data/str01_01/y-guo/models/`.
- The cached Qwen3-32B and Qwen3-30B-A3B have a 32,768-token native window and reach
  131,072 only with YaRN, which the tree's vLLM 0.26 takes through `--hf-overrides`.
- Qwen has no reasoning tiers; a thinking budget is a cap applied from outside. So the
  family has no effort values and the setting names none.
- The Qwen3 cards prescribe temperature 0.6, top_p 0.95, top_k 20 for thinking mode and
  say "DO NOT use greedy decoding"; the Qwen3.5 card prescribes temperature 1.0, top_p
  0.95, top_k 20, presence penalty 1.5 for general tasks. AppWorld's own config for
  Qwen3-235B-A22B-Thinking-2507 uses temperature 0 and 50 steps.
- A silent default: Qwen's `generation_config.json` holds top_p 0.95 and top_k 20, and
  vLLM applies a model-file value to every field a request leaves out. Our client sends
  temperature only, so a Qwen run samples with top_p 0.95 and top_k 20 unless the server
  is started with `--generation-config vllm`. gpt-oss's file holds no sampling values, so
  its runs used neither.
- The ChatML template has no date slot; the loop's `developer` message has to be sent as
  `system` (the Qwen3 template drops an unknown role silently, the Qwen3.5 template
  raises). Thinking is `<think>…</think>` before the content; the 2507-Thinking and
  Qwen3.5 templates put `<think>` in the prompt so the output holds only `</think>`.
- Both venvs already hold transformers 5.14.1 with the Qwen3 and Qwen3.5 classes; vLLM
  0.26 registers the model classes and has the `qwen3` reasoning parser (not needed, the
  loop parses text itself).

## 2. Settings for the Qwen collection

| Setting | Value | Status |
|---|---|---|
| Agent model | Qwen3-30B-A3B-Thinking-2507 first; Qwen3.5-35B-A3B second | PROPOSED |
| Temperature | 0.6 for Qwen3-2507, 1.0 for Qwen3.5 (each card's value) | PROPOSED; gyb's "distinct settings" clause |
| top_p / top_k | the model file's 0.95 / 20 (left to vLLM's model-file default) | PROPOSED |
| Thinking | on, no budget | PROPOSED |
| Date | first line of the system text, "Current date: <task date>" | PROPOSED |
| Window | 131,072 (native 262,144 for both candidates; no YaRN) | FACT |
| Everything else | as the gpt-oss collection: 50 steps, 30,000 tokens per step, replies cut at 20,000 characters, 5 runs per task, v2 wording | DECIDED |

## 3. What the repo needs (recipe 7)

- `models/agent_models/qwen3.py`: the family module, committed as 1948104 with its CPU
  test module `tests/test_qwen3_family.py` (13 tests green) and the README lines. Three
  shared files changed with it (`models/__init__.py` binds the weights directory to the
  family so the template can be read; `gptoss.py` gained the two no-op counterparts;
  `service.py`'s render check sends the family's own request), covered by the same rows
  of 7335596.
- `constants/path_models.yaml`: the two rows are in 1948104.
- `models/table.yaml`: gyb's file. `run.py selfcheck` is red on check 4 until the rows
  below exist ("models/agent_models/qwen3.py is under the code layers, but no stage's
  code tuple names it"). The rows to paste:

```yaml
qwen3_30b_a3b_thinking_2507:
  role: agent
  family: qwen3
  result:
    weights: qwen3-30b-a3b-thinking-2507
    dtype: bfloat16
    quantization: null
    max_model_len: 131072
    served_model_name: qwen3-30b-a3b-thinking-2507
    env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: ""
  serving:
    host: tokyo108
    port: 8104
    gpu_memory_utilization: 0.92
    tensor_parallel_size: 1
    env:
      LD_LIBRARY_PATH: /home/y-guo/reproduce/new1/envs/cuda-compat-13.0
      CUDA_DEVICE_ORDER: PCI_BUS_ID
      VLLM_CACHE_ROOT: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache
      TRITON_CACHE_DIR: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton

qwen3pt5_35b_a3b:
  role: agent
  family: qwen3
  result:
    weights: qwen3.5-35b-a3b
    dtype: bfloat16
    quantization: null
    max_model_len: 131072
    served_model_name: qwen3.5-35b-a3b
    env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: "--language-model-only"
  serving:
    host: tokyo108
    port: 8105
    gpu_memory_utilization: 0.92
    tensor_parallel_size: 1
    env:
      LD_LIBRARY_PATH: /home/y-guo/reproduce/new1/envs/cuda-compat-13.0
      CUDA_DEVICE_ORDER: PCI_BUS_ID
      VLLM_CACHE_ROOT: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache
      TRITON_CACHE_DIR: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton
```

  `--language-model-only` keeps Qwen3.5's vision tower unloaded. Add
  `--generation-config vllm` to `extra_flags` if open point 3 is decided as "unsent".
- `experimental_settings/draft/`: a Qwen setting block beside the gpt-oss one, once the
  table rows exist (the block only changes `models.agent` and, per open point 2,
  `generation.temperature`).
- The GPU proof: a `--debug` walk of that setting; the server's render check compares
  the local ids with vLLM's chat endpoint id for id.
- Servers run on tokyo108 only (the vLLM venv does not run on the 47 GiB machines).

## 4. Open points for gyb

1. Which model first (section 2's proposal, or the cached Qwen3-32B with YaRN).
2. Temperature: the card's value per model, or 1.0 everywhere for sameness with gpt-oss.
3. top_p and top_k: the model file's values, or truly unsent (`--generation-config vllm`).

## 5. Qwen3.6-35B-A3B and Qwen3.8-27B (gyb named these two on 2026-10-02)

### 5.1 What the hub's files say (read 2026-10-02, 03:40 JST)

- Both repositories are public, ungated and apache-2.0: `Qwen/Qwen3.6-35B-A3B` (71.9 GB,
  36.0B parameters in bf16) and `Qwen/Qwen3.8-27B` (55.6 GB, 27.8B parameters in bf16).
  Both downloads were started at 03:40 JST into
  `/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3.6-35B-A3B` and `.../Qwen3.8-27B`
  (logs under `/net/tokyo100-10g/data/str01_01/y-guo/hf/download_<name>.log`).
- Qwen3.6-35B-A3B has the model class of Qwen3.5-35B-A3B
  (`Qwen3_5MoeForConditionalGeneration`, 256 experts, a vision tower) and a 262,144-token
  window. Its chat template differs from Qwen3.5's in two lines: a `preserve_thinking`
  option that is off unless a request asks for it, and the string form of a tool call's
  arguments.
- Qwen3.8-27B is a dense model (`Qwen3_5ForConditionalGeneration`, 64 layers, a vision
  tower) with a 262,144-token window. Its chat template adds three reasoning tiers,
  `xhigh`, `medium` and `low`; a request that names none gets `xhigh`, which writes the
  line "Reasoning effort is set to xhigh. ..." at the start of the system message
  (`medium` writes no line). `preserve_thinking` is on unless a request turns it off.
- Both `generation_config.json` files hold temperature 1.0, top_p 0.95, top_k 20. Both
  cards give temperature 1.0, top_p 0.95, top_k 20 for thinking mode; the Qwen3.6 card
  adds presence penalty 1.5 for general tasks, the Qwen3.8 card presence penalty 0.0.
- The tree's vLLM registers both model classes and the probe venv's transformers holds
  `qwen3_5` and `qwen3_5_moe`. Neither model has been loaded or served here yet.

### 5.2 What fits the committed family module, and what does not

- `models/agent_models/qwen3.py` sends the role and the content of each message and the
  thinking switch, nothing else, and reads the template and the end-of-turn ids from the
  bound weights directory. Qwen3.6-35B-A3B therefore needs no code change.
- Qwen3.8-27B runs through the same module at the template's own tier, `xhigh`. Naming
  another tier in a setting needs a code change: the family's `EFFORTS` and the
  `generation.effort` values in `experimental_settings/schema.py` (PROPOSED, not written).
- The proof for both is the `--debug` walk: the server's render check compares the local
  ids with vLLM's chat endpoint id for id.

### 5.3 Rows for gyb to paste

`constants/path_models.yaml` (the edit was refused to the agent session on 2026-10-02, so
these two rows are pasted by hand as well):

```yaml
qwen3.6-35b-a3b:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3.6-35B-A3B
  note: own replica, registered 2026-10-02; MoE (36B total, 3B active, the model class of Qwen3.5-35B-A3B) with a vision tower that --language-model-only leaves unloaded, bf16; agent family qwen3
qwen3.8-27b:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3.8-27B
  note: own replica, registered 2026-10-02; dense 27.8B with a vision tower that --language-model-only leaves unloaded, bf16; its chat template writes a reasoning-effort line into the system message (xhigh when the request names none); agent family qwen3
```

`models/table.yaml`:

```yaml
qwen3pt6_35b_a3b:
  role: agent
  family: qwen3
  result:
    weights: qwen3.6-35b-a3b
    dtype: bfloat16
    quantization: null
    max_model_len: 131072
    served_model_name: qwen3.6-35b-a3b
    env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: "--language-model-only"
  serving:
    host: tokyo108
    port: 8106
    gpu_memory_utilization: 0.92
    tensor_parallel_size: 1
    env:
      LD_LIBRARY_PATH: /home/y-guo/reproduce/new1/envs/cuda-compat-13.0
      CUDA_DEVICE_ORDER: PCI_BUS_ID
      VLLM_CACHE_ROOT: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache
      TRITON_CACHE_DIR: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton

qwen3pt8_27b:
  role: agent
  family: qwen3
  result:
    weights: qwen3.8-27b
    dtype: bfloat16
    quantization: null
    max_model_len: 131072
    served_model_name: qwen3.8-27b
    env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: "--language-model-only"
  serving:
    host: tokyo108
    port: 8107
    gpu_memory_utilization: 0.92
    tensor_parallel_size: 1
    env:
      LD_LIBRARY_PATH: /home/y-guo/reproduce/new1/envs/cuda-compat-13.0
      CUDA_DEVICE_ORDER: PCI_BUS_ID
      VLLM_CACHE_ROOT: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache
      TRITON_CACHE_DIR: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton
```

`experimental_settings/draft/full_history_qwen.yaml`, two blocks per model in the shape
of the file's Qwen3.5 blocks (temperature 1.0 is both cards' thinking-mode value):

```yaml
collection_2026_10_02_qwen3pt6_35b_a3b_full_history_ctool_qwen3_0pt6b_full:
  meta:   {notes: "the full-history classification probe on trajectories from Qwen3.6-35B-A3B; temperature 1.0 per the model card, the rest as the gpt-oss collection"}
  models: {agent: qwen3pt6_35b_a3b, probe: qwen3_0pt6b}
  generation: {temperature: 1.0}
  probe:  {method: ctool, tuning: full}
  build:  {hist_rounds: 50, probe_result_cap: 1500, probe_text_max_chars: 100000}
  train:  {lr: 1.0e-5, epochs: 3, max_len: 32768, grad_ckpt: true, save_passes: true}
  eval:   {risk: [0.10, 0.05]}

collection_2026_10_02_qwen3pt6_35b_a3b_three_rounds_ctool_qwen3_0pt6b_full:
  meta:   {notes: "the three-round control on the same Qwen3.6-35B-A3B collection"}
  models: {agent: qwen3pt6_35b_a3b, probe: qwen3_0pt6b}
  generation: {temperature: 1.0}
  probe:  {method: ctool, tuning: full}
  build:  {hist_rounds: 3, probe_result_cap: 400}
  train:  {lr: 1.0e-5, epochs: 3, max_len: 8192, grad_ckpt: true, save_passes: true}
  eval:   {risk: [0.10, 0.05]}

collection_2026_10_02_qwen3pt8_27b_full_history_ctool_qwen3_0pt6b_full:
  meta:   {notes: "the full-history classification probe on trajectories from Qwen3.8-27B at the template's own reasoning tier (xhigh); temperature 1.0 per the model card, the rest as the gpt-oss collection"}
  models: {agent: qwen3pt8_27b, probe: qwen3_0pt6b}
  generation: {temperature: 1.0}
  probe:  {method: ctool, tuning: full}
  build:  {hist_rounds: 50, probe_result_cap: 1500, probe_text_max_chars: 100000}
  train:  {lr: 1.0e-5, epochs: 3, max_len: 32768, grad_ckpt: true, save_passes: true}
  eval:   {risk: [0.10, 0.05]}

collection_2026_10_02_qwen3pt8_27b_three_rounds_ctool_qwen3_0pt6b_full:
  meta:   {notes: "the three-round control on the same Qwen3.8-27B collection"}
  models: {agent: qwen3pt8_27b, probe: qwen3_0pt6b}
  generation: {temperature: 1.0}
  probe:  {method: ctool, tuning: full}
  build:  {hist_rounds: 3, probe_result_cap: 400}
  train:  {lr: 1.0e-5, epochs: 3, max_len: 8192, grad_ckpt: true, save_passes: true}
  eval:   {risk: [0.10, 0.05]}
```

### 5.3a The first smoke, 2026-10-02 05:02 JST: both servers died at startup

`sample-71747e8787c5` (Qwen3.6-35B-A3B, tokyo108 card 3) and `sample-2a60b1340c81`
(Qwen3.8-27B, tokyo108 card 5), both `--debug --allow-dirty`, both `launch_failed`
(`alive_check`). Both servers loaded their weights (64.69 GiB in 470.7 s and 50.22 GiB in
346.7 s, `log/1.txt` "Model loading took") and then died in vLLM's startup sampler run with
`FileNotFoundError: [Errno 2] No such file or directory: 'ninja'`.

Cause: the rows of 5.3 as first written carried `env_result: {}`. vLLM then uses the
FlashInfer top-k / top-p sampler (`log/1.txt` "Using FlashInfer for top-p & top-k
sampling."), which compiles its kernel with `ninja` at first use; `ninja` is in the vLLM
venv's `bin/` but on no `PATH` the server process has, and tokyo108 has no system `ninja`.
The `gpt_oss_120b` row switches that sampler off with
`env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}`, so its servers never reached this.

Fix: the four Qwen rows carry the same `env_result` as the `gpt_oss_120b` row, which also
keeps one sampler implementation across the agent models. The rows of sections 3 and 5.3
above are corrected; the two rows already pasted into `models/table.yaml` still carry
`env_result: {}` and need the same edit by gyb. `env_result` is part of the key, so the
sample directories move; nothing real has run under the old key.

### 5.4 Open points for gyb on these two

1. Qwen3.8-27B's reasoning tier: DECIDED (gyb, 2026-10-02: "use Extra-high"). It is the
   template's `xhigh`, which applies when a request names no tier, so no code change.
2. top_p and top_k, as open point 3 of section 4; the Qwen3.6 card's presence penalty 1.5
   is not sent by our client either way.
