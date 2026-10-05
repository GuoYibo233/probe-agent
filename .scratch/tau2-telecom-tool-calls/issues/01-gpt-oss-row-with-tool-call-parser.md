# 01 — a gpt-oss-120b row with tool-call parsing, for tau2 telecom

Status: ready-for-human
Blocked by: none

## Why

tau2's telecom domain gives the simulated customer phone tools of its own; the customer asks the
agent model's server for tool calls through the chat API, and vLLM returns a tool call only
when the server starts with automatic tool choice and a tool-call parser. Without them the Qwen
rows refuse the request and gpt-oss drops the call (both seen in the 2026-10-05 debug runs), so
every telecom task fails on its first customer turn.

gyb chose option 1 on 2026-10-06: a second row for the same gpt-oss-120b weights with the two
flags, used only by tau2 settings. The existing row stays as it is, so no AppWorld run is
re-keyed. The flags change nothing the agent loop asks for (it streams raw completions and the
probe service's render check asks for no tools); they only let the chat API return tool calls.

## What to add to models/table.yaml (the owner's file)

A copy of the `gpt_oss_120b` row with two differences, the extra flags and its own port:

```yaml
gpt_oss_120b_with_tool_call_parser:
  role: agent
  family: gptoss
  result:
    weights: gpt-oss-120b
    dtype: auto
    quantization: null
    max_model_len: 131072
    served_model_name: gpt-oss-120b
    env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: "--enable-auto-tool-choice --tool-call-parser openai"
  serving:
    host: tokyo108
    port: 8108
    gpu_memory_utilization: 0.92
    tensor_parallel_size: 1
    env:
      LD_LIBRARY_PATH: /home/y-guo/reproduce/new1/envs/cuda-compat-13.0
      CUDA_DEVICE_ORDER: PCI_BUS_ID
      VLLM_CACHE_ROOT: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache
      TRITON_CACHE_DIR: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton
```

`openai` is the tool-call parser vLLM 0.26 registers for gpt-oss's harmony format
(`vllm/tool_parsers/__init__.py`). Port 8108 is the next one after the Qwen rows' 8106 and 8107.
No `constants/path_models.yaml` row is needed: the weights alias is the existing one.

## After the row is in

The agent writes draft settings for tau2 on this row (telecom's train and test splits, and
airline and retail as well so one tau2 collection uses one row) and runs the telecom test:
first a debug collection, then the full-length chain the airline and retail test ran.

## Comments
