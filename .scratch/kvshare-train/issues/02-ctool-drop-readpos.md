# 02 ctool 的丢弃规则、默认值、读取位置规则、日志

Status: ready-for-agent
Blocked by: 01
Spec: `.scratch/kvshare-train/spec.md` 第 11 节，读取位置规则的函数来自工单 01 的 `share_data.read_position`

## 要做的

改 `pipeline/train/train_causal_tool.py` 与 `pipeline/eval/eval_tool.py`：

1. 丢弃规则（spec 11.1）：`load_events` 现在没有 tokenizer；给它加 `tok` 与 `max_len` 参数，分组后对每个事件算 `len(tok(full, add_special_tokens=False)["input_ids"])`，超过就丢弃并计数，返回值多带一个计数。`main()` 里 train / val 两次调用都传，`start` 事件加 `dropped_events_train, dropped_events_val`。`collate`（第 137 到 138 行）与 `align_check`（第 209 到 210 行）的 `truncation=True` 改 `truncation=False`。`n_bound_dropped` 字段保留，`step` 与 `eval` 事件照旧写，注释改成「找不到读取位置的切点数，预期 0」。
2. 默认值（spec 11.2）：`--max-len` 8192，`--accum` 2，`--bs` 4 不变，`--epochs` 3 不变。docstring 与 argparse help 同步。
3. 读取位置规则（spec 11.3）：`collate` 第 140 到 158 行、`eval_tool.py` `score_causal` 第 128 到 153 行，两处都改成调用 `share_data.read_position(offsets, full, cut)`。两处原来的 `for t in range(keep-1, -1, -1): if 0 < ends[t] <= b` 循环删掉。`align_check`（第 201 到 243 行）没有切点循环，只改第 209 行的 `truncation`。
4. 日志（spec 11.4）：`step` 事件加 `lr`（`sch.get_last_lr()[0]`）；`loss` 改成自上一条 step 以来全部小批损失的平均，累加器写完日志清零。
5. 测试 `tests/test_ctool_readpos.py`：(a) 用手造的 offsets 与全文验证 `collate` 走新规则后读出的 token 下标（可以直接测 `read_position`，再测 `collate` 在真实分词器上的一个事件）；(b) `load_events` 的丢弃计数：造两个事件，一个全文 token 数 > max_len，断言返回的事件数与计数；(c) `eval_tool.score_causal` 与 `train_causal_tool.collate` 对同一个事件同一批切点读出的 token 下标相同。

## 验收

- `python3 -m unittest tests.test_ctool_readpos` 通过（两个环境都过）。
- `cprobe-env/bin/python -m py_compile pipeline/train/train_causal_tool.py pipeline/eval/eval_tool.py` 通过。
- `git diff` 里 `eval_tool.py` 只有 `score_causal` 的读取位置那一段和 import 变化，左截断 `truncation=True` 保留（spec 11.5）。
- `MAP.md` 不动（ctool 那一行的新文案「上限 8192 超长事件整条丢弃；一次更新 8 个事件；读取位置读跨切点的空白 token」由工单 04 写，你在报告里给出文案）。
- 现有的心跳接线（`heartbeat.emit` 第 401、427、458 行）保持原样。
