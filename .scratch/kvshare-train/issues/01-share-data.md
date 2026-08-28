# 01 数据与分词模块 `pipeline/train/share_data.py`

Status: ready-for-agent
Blocked by: （无）
Spec: `.scratch/kvshare-train/spec.md` 第 2、3、5（只有装块那一条）、11.3、12 节

## 要做的

新建 `pipeline/train/share_data.py`，只放纯 CPU 逻辑（tokenizer 与 python 数据结构，不 import torch 模型），给工单 03 的训练器和工单 02 的 ctool 共用。

1. `load_events(path, tok, mode, max_len, ro=None, limit=0, order="random")`：按 spec 3.2 分组与前缀性质检查，按 3.3 取行与目标串（`import` 旧脚本 `train_causal_callgen` 的 `CALL_SEP / MAX_TGT_TOK / SEED` 与 `train_causal_param` 的 `param_prompt_tail / param_target`，不许复制），按 3.4 算每一行的 `p / seg_ids / seg_lab`，按 3.5 丢弃超上限事件并计数，再断言 spec 3.5 的拼接长度上界（`MAX_BOUNDS` 从 `pipeline/annotate/rules.py` import）。返回事件列表（每个事件含 `event, n_full, packed_len, prefix_len P, rows=[(sent_idx, p, seg_ids, seg_lab, w)]`，按 `event` 字段排序）和计数字典（`dropped_events, dropped_rows_tgt, assembly_mismatch, n_rows`）。`limit > 0` 的时候按 `order` 取前 limit 个事件：`"random"` = `random.Random(SEED)` 打乱后取前 limit 个（照 ctool 第 118 到 120 行）；`"shortest"` = 按 `n_full` 升序取前 limit 个（spec 第 8 节 `--smoke` 用）。另给一个 `worst_blocks(events, tok_budget)`，返回「`packed_len` 最大的单个事件」和「按 `chunk_by_budget` 的贪心能装下的、块内最长 `packed_len` 最大的那一块」两个事件列表，给训练器的 `--mem-probe` 用。
2. `pack_event(ev)`：返回一个事件的拼接序列 `tokens, positions, labels, row_index`（每个 token 属于第几行，前缀是 −1）和 `seg_bounds`（每段在拼接序列里的起止），按 spec 第 4 节。
3. `allowed_mask(ev)`：返回 `[L, L]` 的 bool 张量（这一处允许 import torch，只用张量构造），True = 可看，按 spec 第 4 节的关系。
4. `chunk_by_budget(events, tok_budget)`：spec 第 5 节第二条的贪心装块，返回块列表，每块是事件列表；单个事件超预算独自成块。
5. `read_position(offsets, full_text, cut)`：spec 11.3 的读取位置规则，输入 tokenizer 的 `offset_mapping` 列表、全文、切点字符位置，返回 token 下标。
6. 测试 `tests/test_share_data.py`，spec 12 的五条（a 到 e）。真实分词器路径取旧脚本的 `MODELS["qwen"]`，不存在就 `skipTest`；val 集路径 `pipeline/data/nyapass_aw_v1/gptoss/val.jsonl`，不存在同样 skip。

## 验收

- `python3 -m unittest tests.test_share_data` 通过；在 cprobe-env 下也要过（`cprobe-env/bin/python -m unittest tests.test_share_data`）。
- 测试 (a) 覆盖 cgen 和 cparam 两种 mode，各 20 个事件，每一行 `full_ids[:p] + seg_ids == old_ids + tgt_ids`。
- `read_position` 在两个例子上：全文 `'Spotify."\n\nWe'`、切点在第一个 `\n` 之后 → 返回覆盖 `."\n\n` 的那个 token；全文 `'done. Next'`、切点在空格之后 → 返回 `.` 所在 token（不是 `ĠNext`）。用真实分词器验证，并额外用手造的 offsets 列表各验一次。
- 不改任何现有文件（`MAP.md` 那一行 `(共用)` 由工单 04 加，你在报告里写好那一行的文案即可）。
