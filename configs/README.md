# configs/ — 生成设置的唯一真源

这个目录管生成设置（模型地址、vLLM 启动参数、采样参数）；
`pipeline/configs/` 管的是数据批次（哪些轨迹、怎么切分），两边不要混。

两样东西：

- `models.json`：唯一的模型地址映射。`model_registry.py` 从这里读,
  脚本一律经 `resolve()` 取路径，不许硬编码。
- `presets/<名>.json`：一份文件一套生成设置。`model` 是 models.json 里的
  别名；`server` 节是 vLLM 启动参数（`serve_preset.py` 吃，
  发射走 `run.py show serve-preset`）；`client` 节是采样参数
  （api / reasoning_effort / temperature / top_p / max_tokens / stop /
  start_date / seed，采集器、活跑、回放的 `--preset` 吃，BFCL handler 走
  环境变量 `NEW1_PRESET_JSON`）。节里的 null = 不指定，落到调用方原有缺省。

三条规矩：

1. 命令行显式给的参数永远压过预设值（merge 逻辑在 `preset_loader.py`）。
2. 加一套新设置 = 加一份 json。加完跑 `python3 run.py selfcheck`
   （校验别名解析与字段类型）和 `python3 -m unittest tests.test_preset`。
3. 用了预设的跑，run_id 里带上预设名（DATA.md 检查清单第 9 条）。

现有六份 gptoss 预设分两类：五份（chat_high / harmony_medium / bfcl_high /
live_high / replay）与 2026-08-20 改造前散在五处的写死值逐项等价，
等价性由 `tests/test_preset.py` 钉死；第六份 `gptoss_default` 是 OpenAI
官方推荐口径（temperature=1.0 / top_p=1.0 / top_k=0 / min_p=0.0 /
effort medium / 上下文 131072，出处与对照写在它的 desc 里），不对应任何旧写死值。
别手改预设去"顺手调参"——调参就新开一份预设，名字说清口径。
