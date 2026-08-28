# 01 数据与分词模块 `pipeline/train/share_data.py`

Status: claimed
Blocked by: （无）
Spec: `.scratch/kvshare-train/spec.md` 第 2、3、5（只有装块那一条）、11.3、12 节

## 要做的

新建 `pipeline/train/share_data.py`，只放纯 CPU 逻辑（tokenizer 与 python 数据结构，不 import 任何模型），给工单 03 的训练器和工单 02 的 ctool 与 `eval_tool.py` 共用。**模块顶层只许 import stdlib 与 torch**：两个旧训练脚本的 import 必须写在 `load_events` 的函数体里（spec 3.3 的理由：旧脚本模块层有 transformers ≥ 5.14 的版本门，mbert-env 下 import 就 `SystemExit`，而 `eval_tool.py` 要在 mbert-env 下 import 本模块拿 `read_position`）。

1. `load_events(path, tok, mode, max_len, ro=None, limit=0, order="random")`：各步顺序照 spec 3.2 那段写死（分组 → 前缀抽查 → 全文分词与事件级丢弃 → 按 `limit`/`order` 取子集 → 只对留下的事件逐行分词与行级丢弃）；按 3.3 取行与目标串（函数体内 `import` 旧脚本 `train_causal_callgen` 的 `CALL_SEP / MAX_TGT_TOK / SEED` 与 `train_causal_param` 的 `param_prompt_tail / param_target`，不许复制；两道硬停照搬），按 3.4 算每一行的 `p / seg_ids / seg_lab`，最后断言 spec 3.5 的拼接长度上界（`MAX_BOUNDS` 从 `pipeline/annotate/rules.py` import，同样放函数体内）。返回事件列表（每个事件含 `event, n_full, packed_len, prefix_len P, rows=[(sent_idx, text, p, seg_ids, seg_lab, w)]`；事件顺序 = 文件里首次出现的顺序，行顺序 = `sent_idx` 升序，这两条保序是契约，对齐检查靠它按位置配对）和计数字典（`dropped_events, dropped_rows_tgt, assembly_mismatch, n_rows`）。`limit > 0` 的时候按 `order` 取前 limit 个事件：`"random"` = 新建 `random.Random(SEED)` 打乱后取前 limit 个（照 ctool 第 118 到 120 行）；`"shortest"` = 按 `n_full` 升序取前 limit 个（spec 第 8 节 `--smoke` 用）。另给一个 `worst_blocks(events, tok_budget)`，返回「`packed_len` 最大的单个事件」和「按 `chunk_by_budget` 的贪心能装下的、块内最长 `packed_len` 最大的那一块」两个事件列表，给训练器的 `--mem-probe` 用。
2. `pack_event(ev)`：返回一个事件的拼接序列 `tokens, positions, labels, row_index`（每个 token 属于第几行，前缀是 −1）和 `seg_bounds`（每段在拼接序列里的起止），按 spec 第 4 节。
3. `allowed_mask(ev)` 与 `batch_mask(packed_list, L_pad)`：前者返回一个事件 `[L, L]` 的 bool 张量（True = 可看，按 spec 第 4 节的关系），后者把一个物理块的若干事件右 pad 到 `L_pad`（16 的倍数）并造出 `[B, 1, L_pad, L_pad]` 的 bf16 加性掩码（可看 0、不可看 −inf；pad 作为 query 的行只让 pad 看自己）、`position_ids`、`input_ids`、以及损失位下标表 `(batch_idx, qpos, target_id, row_idx)`。
4. `chunk_by_budget(events, tok_budget)`：spec 第 5 节第二条的贪心装块，返回块列表，每块是事件列表；单个事件超预算独自成块。
5. `read_position(offsets, full_text, cut, keep)`：spec 11.3 的读取位置规则，输入 tokenizer 的 `offset_mapping` 列表、全文、切点字符位置、真实 token 数 `keep`，只在 `offsets[:keep]` 里找，返回 token 下标；找不到（没有真实 token 起始位置 < cut，或者要退回 j−1 而 j = 0）返回 −1。
6. 测试 `tests/test_share_data.py`，spec 12 的 (a) 到 (e)。真实分词器路径取旧脚本的 `MODELS["qwen"]`（测试里也要延迟 import 旧脚本，照 `tests/test_cparam_assembly.py` 第 21 到 29 行把 `ImportError` 与 `SystemExit` 都兜成 skip），不存在就 `skipTest`；val 集路径 `pipeline/data/nyapass_aw_v1/gptoss/val.jsonl`，不存在同样 skip。

## 验收

- `python3 -m unittest tests.test_share_data` 通过；在 cprobe-env 下也要过（`cprobe-env/bin/python -m unittest tests.test_share_data`）。
- `mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/train'); import share_data; print(share_data.read_position)"` 退出码 0（硬门，不许 try/skip 兜住）。
- 测试 (a) 覆盖 cgen 和 cparam 两种 mode，各 20 个事件，每一行 `full_ids[:p] + seg_ids == old_ids + tgt_ids`。
- `read_position` 的用例：全文 `'Spotify."\n\nWe'`、切点在第一个 `\n` 之后 → 返回覆盖 `."\n\n` 的那个 token；全文 `'done. Next'`、切点在空格之后 → 返回 `.` 所在 token（不是 `ĠNext`）；手造 offsets 首个起始位置 > 0 且切点更小 → −1；j = 0 且切点后非空白 → −1；一批两个长度不同的事件 `padding=True`，短事件每个切点的返回值 < keep 并且和单条不 pad 时相同。真实分词器与手造 offsets 各验一次。
- 不改任何现有文件（`MAP.md` 那一行 `(共用)` 由工单 04 加，你在报告里写好那一行的文案即可）。
