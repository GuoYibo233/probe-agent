# 07 评测端超长事件的三种处理：三个评测脚本加 `--overlong {left,skip,drop-event}`

Status: ready-for-agent
Blocked by: （无；第二轮起点 HEAD 7668166 之后）
Spec: `.scratch/kvshare-train/spec.md` 16.2（判据）、16.9（测试）、16.10 #28。改动只在 `pipeline/train/share_data.py`（抽一个函数）、`pipeline/train/train_causal_tool.py`（改调那个函数）、`pipeline/eval/eval_causal_call.py`、`pipeline/eval/eval_causal_param.py`、`pipeline/eval/eval_tool.py`、新测试 `tests/test_eval_overlong.py`。不改 `train_causal_share.py`、不改 `run.py`、不改 skill 文档（文档归工单 12）。

## 背景

新训练器把事件全文 token 数大于 `--max-len`（8192）的事件整条丢弃（`share_data.load_events`），ctool 训练器也一样（`train_causal_tool.load_events` 返回 `(events, dropped)`）。评测端现在的做法是左截：cgen / cparam 的 `generate()` 把提示左截到 `max_len − max_new`（`eval_causal_call.py` 第 213 到 214 行、`eval_causal_param.py` 第 208 到 209 行，`tok.truncation_side = "left"` 在第 590 / 420 行），ctool 的 `score_causal`（`eval_tool.py` 第 116 到 160 行）把全文左截到 `max_len`，窗口外的边界记零 logits 并计 `n_oow`。gyb 要三种处理都做成开关，回头对比。

## 要做的

1. `share_data.py`：把 `load_events` 里「事件全文分词不截断、数 token 数」的那几行抽成模块级函数 `n_full_tokens(tok, full_text) -> int`，`load_events` 改调它；`train_causal_tool.load_events` 的丢弃判据也改调它（现在那里是自己分词数长度；改完两边用同一个函数，数值不变）。取「事件全文」的规则（分组后 `sent_idx` 最大那一行的 `text`）如果在 `load_events` 里是内联写的，也抽成一个函数 `group_rows(rows) -> {event: [rows 按 sent_idx 升序]}` 或等价的可复用形式，评测脚本的 `drop-event` 调同一个。
2. `eval_causal_call.py` 与 `eval_causal_param.py` 各加 `--overlong`，`choices=["left", "skip", "drop-event"]`，默认 `left`。三种模式的判据照 spec 16.2 逐条实现：
   - `left`：行为不变，只加计数 `n_left_truncated`（提示 = `text + sep`（cparam 是 `text + param_prompt_tail`，按脚本现有的提示构造），分词不截断数长度，大于 `max_len − max_new` 的行数）。
   - `skip`：提示长度大于 `max_len − max_new` 的行不进 `prompts`、不进 `keys`（也就不进总表、按工具分桶、样本），计数 `n_skipped_rows`。
   - `drop-event`：对 `keys` 里的每个事件，从 `--data` 的行里取该事件 `sent_idx` 最大那一行的 `text` 当全文，`n_full_tokens` 大于 `meta["max_len"]` 的事件整个从 `keys` 去掉，计数 `n_dropped_events`；剩下的行里提示仍超长的左截并计 `n_left_truncated`。只对 `keys` 里的事件分词（test 集 391,893 行，别对全集分词）。
   - 报告：JSON 与 MD 都写 `overlong_mode` 和 `n_left_truncated / n_skipped_rows / n_dropped_events` 三个计数（没发生的写 0，键不省略）。ACCEPT 脚本读的现有键一个都不改名。
3. `eval_tool.py` 的 `score_causal` 与调用它的主流程加 `--overlong`（同样三个值，默认 `left`）：
   - `left`：不变。
   - `skip`：窗口外边界（`read_position` 返回 −1 的那些）不进任何分母、不产生触发点——实现上把这些行从 `rows` 里剔除并把剔除下标返回给调用方（或返回一个 mask），调用方在算指标与 REPLAY_REPORT 之前先剔；计数 `n_skipped_bounds`。
   - `drop-event`：`n_full_tokens(tok, 全文) > max_len` 的事件整个剔除（全部边界），计数 `n_dropped_events`、`n_dropped_bounds`。
   - `REPLAY_REPORT.json/.md` 写 `overlong_mode` 与三个计数（`n_oow` 照旧保留）。`logits_*.pt` 与 `.meta.json` 的形状要和剔除后的行数一致，下游 cgen 评测按事件键取触发点，不按下标（实现者读 `eval_causal_call.py` 读 REPLAY_REPORT 的那段确认；如果下游按下标对齐 `rows`，就在 `.meta.json` 里写清剔除后的行清单）。
4. 测试 `tests/test_eval_overlong.py`（spec 16.9 第一条）：真实分词器 `MODELS["qwen"]` 路径不存在就 `skipTest`。手造 3 个事件（一个全文超过很小的 `max_len`、一个提示刚好超过 `max_len − max_new`、一个正常），断言：(a) `n_full_tokens` 对同一段文本与 `load_events` 的 `dropped_events` 判据一致；(b) cgen 的行筛选函数（把第 2 条里的筛选抽成一个纯函数 `select_rows(mode, ...)`，方便测）在三种模式下的计数与留下的行集合；(c) `score_causal` 在三种模式下的计数与剔除集合（小模型可用 `Qwen3Config` 随机初始化一个 2 层的 backbone 加一个线性头，照 `tests/test_share_trainer.py` 的做法）。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_eval_overlong tests.test_share_data tests.test_ctool_readpos` 通过。
- `grep -n "n_full_tokens" pipeline/train/share_data.py pipeline/train/train_causal_tool.py pipeline/eval/eval_tool.py pipeline/eval/eval_causal_call.py pipeline/eval/eval_causal_param.py` 五个文件都命中。
- 三个评测脚本 `--help` 都列出 `--overlong`，默认 `left`。
- 不加 `--overlong` 时三个脚本的行为与改前逐字段相同（报告只多了 `overlong_mode` 与计数键）。
- `python3 run.py selfcheck` 通过（不改注册表也要跑一遍）。
