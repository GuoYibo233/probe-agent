# vLLM Resources

按信任度排：本机装的源码 > 官方文档 > 社区。我们自己的日志是"这台机器上到底发生了什么"
的唯一真源，排在最前面。

## Knowledge

### 一等：本地可验证的一手材料

- **本机装的 vLLM 0.26.0 源码** — `envs/vllm-env/lib/python3.12/site-packages/vllm/`
  这是我们真正在跑的那个版本。官方文档描述的是最新版，两者会不一致（已经撞到过一次，
  见 `learning-records/0001`）。查参数默认值、查注册表里有哪些名字，一律以这里为准。
  常用落点：`config/cache.py`（显存与 KV）、`config/scheduler.py`（并发）、
  `config/model.py`（上下文长度）、`envs.py`（环境变量）、
  `tool_parsers/__init__.py` 与 `reasoning/__init__.py`（解析器名字表）。

- **我们自己的服务器启动日志** — `/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/*srv*.log`
  每台服务起来时把自己的真实口径全打出来了：KV 池多大、并发上限多少、
  显存怎么分的、自动挂了哪个解析器。用于：任何"这台服务到底什么配置"的问题。
  第一课就是教怎么读它。

### 二等：官方文档

- [vLLM Engine Arguments](https://docs.vllm.ai/en/latest/configuration/engine_args.html)
  所有 `vllm serve` 旗标的权威说明与默认值。用于：查一个旗标是干什么的。
  ⚠️ 描述的是最新版，默认值可能与我们装的 0.26.0 不同，拿不准回去查源码。

- [vLLM Tool Calling](https://docs.vllm.ai/en/latest/features/tool_calling.html)
  `--enable-auto-tool-choice` 与 `--tool-call-parser` 的官方说明和解析器清单。
  用于：给新模型配工具调用。⚠️ 这一页落后于代码——`qwen3_coder` 在 0.26.0 的注册表里，
  文档页没列。

- [vLLM Parallelism and Scaling](https://docs.vllm.ai/en/latest/serving/parallelism_scaling.html)
  什么时候该开张量并行、什么时候单卡就够。原话："if the model fits on a single GPU,
  distributed inference is probably unnecessary."用于：排卡决策。

- [vLLM GitHub](https://github.com/vllm-project/vllm)
  用于：查某个行为是哪个 commit 引入的、翻 issue 找同款报错。

## Wisdom (Communities)

尚未与 gyb 确认是否愿意参与社区。以下是候选，未使用过：

- [vLLM GitHub Issues / Discussions](https://github.com/vllm-project/vllm/issues)
  报错原文丢进搜索框，命中率高。适合：撞到"这是 bug 还是我配错了"的时候。

## Gaps

- gpt-oss 的 harmony 格式：目前的理解全部来自 `pipeline/inject/rebuild.py` 的注释和
  vLLM 源码，还没找到一份可信的格式规范文档。这是下一步该补的资源。
- 没有针对"多副本同机部署"的官方指南；我们的一卡一实例做法目前只有
  parallelism 文档那一句话背书。
