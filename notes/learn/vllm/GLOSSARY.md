# vLLM Glossary

Fixed terminology for this new1 line of work when dealing with vLLM. One concept, one word; aliases are listed under _avoid_.
Only words gyb can already use correctly go in here; newly taught concepts stay in the lessons first.

## Serving and GPU memory

**KV cache pool**:
The block of GPU memory a service claims once at startup, used to store context that has already been computed. Its capacity decides how many requests this service can hold at the same time.
_Avoid_: KV cache, cache, memory pool

**Per-request context limit**:
The maximum number of tokens one request is allowed to occupy, set by `--max-model-len`; if not given, it is taken automatically from the model config.
_Avoid_: max_model_len, context window, context length

**Concurrency limit**:
KV cache pool capacity divided by the per-request context limit, printed in the log as `N.NNx`. It is the number of requests the service can hold "if every request used the full limit," not measured throughput.
_Avoid_: concurrent count, max concurrency, throughput

**Memory fraction**:
`--gpu-memory-utilization`, how much of the whole card a service claims. The default in 0.26.0 is 0.92.
Counted per instance: running two instances on the same card means each one claims this fraction separately.
_Avoid_: memory occupancy rate, gpu util

## Endpoints and parsing

**completions endpoint**:
`/v1/completions`. The client assembles the whole string itself and the server feeds it into the model as-is. The inject line can only go through this one.
_Avoid_: completion interface, raw endpoint, raw interface

**chat endpoint**:
`/v1/chat/completions`. The client only supplies messages, and the server applies the chat template and parses the reasoning segment into the `reasoning` field.
_Avoid_: conversation interface, chat completions

**reasoning parser**:
`--reasoning-parser`, the component the server uses to cut the reasoning segment out of the model's output. For gpt-oss, vLLM attaches `openai_gptoss` automatically.
_Avoid_: reasoning parser (Chinese gloss), inference parser

## Settings

**Settings**:
The service configuration a batch of data was produced under: context limit, memory fraction, which endpoint, which parser attached. Two batches produced under different settings cannot be compared directly.
_Avoid_: setup, configuration, config (these words mean something else elsewhere in this repo)
