# 02 ctool 的丢弃规则、默认值、读取位置规则、日志

Status: ready-for-agent
Blocked by: 01
Spec: `.scratch/kvshare-train/spec.md` 第 11 节，读取位置规则的函数来自工单 01 的 `share_data.read_position`

## 要做的

改 `pipeline/train/train_causal_tool.py` 与 `pipeline/eval/eval_tool.py`：

1. 丢弃规则（spec 11.1）：`load_events` 现在没有 tokenizer；给它加 `tok` 与 `max_len` 参数，分组后对每个事件算 `len(tok(full, add_special_tokens=False)["input_ids"])`，超过就丢弃并计数，返回值多带一个计数。`main()` 里 train / val 两次调用都传，`start` 事件加 `dropped_events_train, dropped_events_val`。`collate`（第 137 到 138 行）与 `align_check`（第 209 到 210 行）的 `truncation=True` 改 `truncation=False`。`n_bound_dropped` 字段保留，`step` 与 `eval` 事件照旧写，注释改成「找不到读取位置的切点数，预期 0」。
2. 默认值（spec 11.2）：`--max-len` 8192，`--accum` 2，`--bs` 4 不变，`--epochs` 3 不变。docstring 与 argparse help 同步。
3. 读取位置规则（spec 11.3）：`collate` 第 140 到 158 行、`eval_tool.py` `score_causal` 第 128 到 153 行，两处都改成调用 `share_data.read_position(offsets, full, cut, keep)`，`keep = int(enc["attention_mask"][i].sum())`（`train_causal_tool.py` 第 143 行、`eval_tool.py` 第 142 行）保留并作为第四个实参传进去。只删原来的 `for t in range(keep-1, -1, -1): if 0 < ends[t] <= b` 循环体；`if j < 0` 的守卫两处都保留（训练侧 `dropped += 1`，评测侧 `n_oow` 计数第 128、150 到 152 行原样）。`align_check`（第 201 到 243 行）没有切点循环，只改第 209 行的 `truncation`。`eval_tool.py` 里 `import share_data` 可以放模块顶层（`share_data` 顶层不 import 训练脚本，spec 3.3），但要沿用第 43 到 44 行那种 `sys.path` 写法。
4. 日志（spec 11.4）：`step` 事件加 `lr`（`sch.get_last_lr()[0]`）；`loss` 改成自上一条 step 以来全部小批损失的平均，累加器写完日志清零。
5. 测试 `tests/test_ctool_readpos.py`：(a) 用手造的 offsets 与全文验证 `collate` 走新规则后读出的 token 下标（可以直接测 `read_position`，再测 `collate` 在真实分词器上的一个事件）；(b) `load_events` 的丢弃计数：造两个事件，一个全文 token 数 > max_len，断言返回的事件数与计数；(c) `eval_tool.score_causal` 与 `train_causal_tool.collate` 对同一个全文在上限以内的事件同一批切点读出的 token 下标相同（超上限的事件训练侧丢弃、评测侧左截，不进这条）；(d) `eval_tool.score_causal` 在一个左截事件上，窗口外的切点计进 `n_oow` 而不是落进 cols。

## 验收

- `python3 -m unittest tests.test_ctool_readpos` 通过（两个环境都过；测试 import 训练脚本要照 `tests/test_cparam_assembly.py` 第 21 到 29 行兜 `SystemExit` 成 skip）。
- `cprobe-env/bin/python -m py_compile pipeline/train/train_causal_tool.py pipeline/eval/eval_tool.py` 通过。
- 硬门（`py_compile` 抓不到 import 期退出，必须真 import，不许 try/skip 兜住）：`mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/eval'); import eval_tool; print('ok')"` 打印 ok；`mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/eval'); import eval_mbert_call; print('ok')"` 打印 ok。
- `git diff` 里 `eval_tool.py` 只有 `score_causal` 的读取位置那一段和 import 变化，左截断 `truncation=True` 保留（spec 11.5）。
- `MAP.md` 不动（ctool 那一行的新文案「上限 8192 超长事件整条丢弃；一次更新 8 个事件；读取位置读跨切点的空白 token」由工单 04 写，你在报告里给出文案）。
- 现有的心跳接线（`heartbeat.emit` 第 401、427、458 行）保持原样。
