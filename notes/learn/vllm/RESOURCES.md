# vLLM Resources

Ranked by trust: the source installed on this machine > official docs > community. Our own logs are the only source of truth for "what actually happened on this machine," so they rank first.

## Knowledge

### Tier 1: locally verifiable primary material

- **The vLLM 0.26.0 source installed on this machine**: `envs/vllm-env/lib/python3.12/site-packages/vllm/`
  This is the actual version we run. The official docs describe the latest version, and the two disagree
  (already hit once, see `learning-records/0001`). For default parameter values and what names a registry holds, this is the source of truth.
  Common places to check: `config/cache.py` (memory and KV), `config/scheduler.py` (concurrency),
  `config/model.py` (context length), `envs.py` (environment variables),
  `tool_parsers/__init__.py` and `reasoning/__init__.py` (parser name tables).

- **Our own servers' startup logs**: `/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/*srv*.log`
  Every time a server starts, it prints its own real settings: KV pool size, concurrency limit,
  how memory was split, which parser got attached. Use it for any "what is this service's actual configuration" question.
  Lesson 1 teaches how to read it.

### Tier 2: official docs

- [vLLM Engine Arguments](https://docs.vllm.ai/en/latest/configuration/engine_args.html)
  The authoritative description and default values for every `vllm serve` flag. Use it to look up what a flag does.
  Warning: it describes the latest version, and defaults may differ from our installed 0.26.0; check the source when unsure.

- [vLLM Tool Calling](https://docs.vllm.ai/en/latest/features/tool_calling.html)
  The official description of `--enable-auto-tool-choice` and `--tool-call-parser`, plus the parser list.
  Use it when configuring tool calling for a new model. Warning: this page lags behind the code:
  `qwen3_coder` is in 0.26.0's registry but not listed on this page.

- [vLLM Parallelism and Scaling](https://docs.vllm.ai/en/latest/serving/parallelism_scaling.html)
  When to turn on tensor parallelism and when a single GPU is enough. Direct quote: "if the model fits on a single GPU,
  distributed inference is probably unnecessary." Use it for card-allocation decisions.

- [vLLM GitHub](https://github.com/vllm-project/vllm)
  Use it to find which commit introduced a given behavior, or to search issues for a matching error.

## Wisdom (Communities)

Not yet confirmed with gyb whether he wants to participate in the community. The following are candidates, unused so far:

- [vLLM GitHub Issues / Discussions](https://github.com/vllm-project/vllm/issues)
  Drop the raw error text into the search box; the hit rate is high. Good for the moment you hit "is this a bug or did I misconfigure it."

## Gaps

- The gpt-oss harmony format: current understanding comes entirely from the comments in `pipeline/inject/rebuild.py` and
  the vLLM source; no trustworthy format specification has been found yet. This is the next resource to fill in.
- No official guide exists for "multiple replicas on one machine"; our one-card-one-instance approach is currently backed only by that
  one line in the parallelism docs.
