# tau2 telecom: what the model table needs, and where the flag should live

Written 2026-10-06 while finishing the tau2 and BFCL branch
(`environment-tau2-bench-2026-10-05`). Facts first, then the decision for gyb.

## Facts

1. tau2's user simulator calls tools only in the telecom domain (airline and retail users
   have no tools). tau2's own client sends the tool schemas with `tool_choice: auto` whenever
   tools exist (`external/tau2-bench/src/tau2/utils/llm_utils.py`, the `generate` function).
2. vLLM accepts such a request only when the server runs with `--enable-auto-tool-choice
   --tool-call-parser <name>`. For gpt-oss the server ignores the flag and always parses tool
   calls; the server log of the gpt-oss telecom test reads "For gpt-oss, we ignore
   --enable-auto-tool-choice and always enable tool use" and carries no refused request.
   So gpt-oss needs no table change.
3. Qwen3.6-35B-A3B and Qwen3.8-27B need the flag. Their chat templates write tool calls as
   `<tool_call><function=...>` XML, which the installed vLLM 0.26.0 parses with the parser named
   `qwen3_xml` (registered in `vllm/tool_parsers/__init__.py`; `hermes` reads JSON inside
   `<tool_call>` and would misread these models).
4. The place for a server flag today is the `extra_flags` field of a model row, and that field
   sits in the row's `result:` block, which expands into the setting before keying. Adding a
   flag there changes the key of every run that names the row: the two finished Qwen
   collections (`sample-363859498f89`, `sample-62d6f3de27bf`) and every build, train and eval
   on them would be re-keyed, and a new walk would recollect from scratch.
5. The flag changes no output for a request that carries no tools. AppWorld, airline, retail
   and BFCL requests carry none (the loop writes calls as text), so a Qwen run of those
   environments produces the same records with or without the flag.
6. The gpt-oss telecom test itself (`sample-802ef60c7aec`, three tasks) is not a pass: two
   tasks aborted with tau2's own error "UserMessage must have either content or tool_calls",
   that is, the simulated user's reply came back from the server with neither text nor a
   parsed call. The server refused nothing. The mechanism is UNVERIFIED (the request and
   response bodies are not logged); it is a tau2.py-side question, not a table one, and it
   stays open after the merge.

## The decision

Where should a serving flag live that changes the server's behaviour only for requests that
carry tools?

- **A. In the serving block, which is never keyed (recommended).** A new `serving.extra_flags`
  (or a narrower `serving.tool_call_parser`) that `models/agent_models/service.py`'s
  `build_command` appends beside the keyed `result.extra_flags`. Pros: no finished run is
  re-keyed; the fact that the flag changes nothing for a tool-less request is exactly what
  "serving, not result" means in the table's own contract; one code change, one README line,
  one same row per stage that opens a server (sample, inject). Cons: a telecom run's key does
  not record that the parser was on; a telecom run without it fails outright, so no finished
  telecom directory is ambiguous.
- **B. New aliases that carry the flag in the keyed block.** Rows such as
  `qwen3pt6_35b_a3b_tool_calls` with the flag in `result.extra_flags`, on their own ports,
  named only by tau2 telecom settings. Pros: no code change. Cons: two rows per Qwen model that
  differ in a serving detail; a telecom collection and an airline collection of the same model
  cannot share one server; the table grows by one row for every future agent model.
- **C. Add the flag to the existing rows' keyed field.** Pros: one line each. Cons: re-keys
  every Qwen run that exists; the two finished collections and their probes become
  unreachable from any new walk.

## The rows, for each option

Option A, after the code change, under each Qwen row's `serving:` block:

```yaml
    extra_flags: "--enable-auto-tool-choice --tool-call-parser qwen3_xml"
```

Option B, two new rows (ports 8108 and 8109 are the next free ones on tokyo108):

```yaml
qwen3pt6_35b_a3b_tool_calls:
  role: agent
  family: qwen3
  result:
    weights: qwen3.6-35b-a3b
    dtype: bfloat16
    quantization: null
    max_model_len: 131072
    served_model_name: qwen3.6-35b-a3b
    env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: "--language-model-only --max-num-seqs 64 --enable-auto-tool-choice --tool-call-parser qwen3_xml"
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

qwen3pt8_27b_tool_calls:
  role: agent
  family: qwen3
  result:
    weights: qwen3.8-27b
    dtype: bfloat16
    quantization: null
    max_model_len: 131072
    served_model_name: qwen3.8-27b
    env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: "--language-model-only --max-num-seqs 64 --enable-auto-tool-choice --tool-call-parser qwen3_xml"
  serving:
    host: tokyo108
    port: 8109
    gpu_memory_utilization: 0.92
    tensor_parallel_size: 1
    env:
      LD_LIBRARY_PATH: /home/y-guo/reproduce/new1/envs/cuda-compat-13.0
      CUDA_DEVICE_ORDER: PCI_BUS_ID
      VLLM_CACHE_ROOT: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache
      TRITON_CACHE_DIR: /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton
```

Option C, in each existing Qwen row's `result.extra_flags`:

```yaml
    extra_flags: "--language-model-only --max-num-seqs 64 --enable-auto-tool-choice --tool-call-parser qwen3_xml"
```

Whichever option, the parser name is UNVERIFIED on a live server until one telecom debug walk
on a Qwen model passes; the gpt-oss row stays as it is.
