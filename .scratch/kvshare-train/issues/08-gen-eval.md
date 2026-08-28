# 08 新训练器加回生成式评估：`--gen-eval N`（默认 200）与 `--gen-bs`

Status: ready-for-agent
Blocked by: （无）
Spec: `.scratch/kvshare-train/spec.md` 16.3（做法）、16.9（测试）、16.10 #29 #30。改动只在 `pipeline/train/train_causal_share.py`、`pipeline/train/share_data.py`（行元组加第 6 位）、`tests/test_share_trainer.py`、`tests/test_share_data.py`（手造行元组补第 6 位）。不改旧脚本、不改 `run.py`、不改文档。

## 背景

旧训练器每次评估定种子抽 200 行做 greedy 生成，报 `val_exact_call`（cgen，`train_causal_callgen.py` 第 309 到 331 行 `eval_gen`、第 448 到 450 行抽样、第 535 到 538 行写日志）或 `val_exact_params`（cparam，`train_causal_param.py` 第 235 到 259、358 到 360、418 到 422 行），只进日志不选 best。新训练器第一轮按决定 4 去掉了。gyb 要做成开关加回来，推荐值开（200）。

## 要做的

1. `share_data.load_events`（第 205 行）行元组加第 6 位 `dict(tgt=<目标串>, tool=<工具名或 None>)`，按模式写死：cgen 分支 `gen=dict(tgt=r["label_call"], tool=None)`（cgen 分支没有 `tgt_str` 变量，第 179 到 183 行直接对 `r["label_call"]` 分词加 eos）；cparam 分支 `gen=dict(tgt=tgt_str, tool=r["label"])`。`tgt` 是不含 eos 的原串，`eval_gen` 拿它整串比对。第 0 到 5 位一个都不动。`pack_event` 第 274 行是六个名字的拆包 `_sent_idx, _text, p, seg_ids, seg_lab, _w = row`，7 位元组会 `ValueError`——改成 `_sent_idx, _text, p, seg_ids, seg_lab, _w = row[:6]`。其他按下标读行的地方（`share_data.py` 第 214 到 215 行，`train_causal_share.py` 第 179 / 470 / 789 行）不用改。测试里手造 6 位行元组的地方全部补上第 6 位：`tests/test_share_trainer.py` 第 374 / 437 / 495 行附近，`tests/test_share_data.py` 里的同类构造。
2. `train_causal_share.py` 加参数 `--gen-eval`（int，默认 200，0 关闭）、`--gen-bs`（int，默认 8）与 `--gen-eval-at`（`choices=["all", "last"]`，默认 `last`：只在 `frac == E` 那次评估做生成，`all` 每个评估点都做），三个都紧跟在 `--log-every` 之后（工单 09、10 也在同一段加参数，各有各的锚点；`start_kw` 字典里本工单加 `gen_eval / gen_bs` 两个键，放在 `log_every` 那个键之后；合并冲突主会话收账时解）。
3. 抽样（照 spec 16.3）：`ev_events` 加载完之后，摊平成行列表（事件按加载顺序、行按事件内顺序），不过滤（share_data 的行全部有目标；旧训练器 `callgen` 第 448 行过滤的 `r[5]` 是「有无 LM 目标」的布尔，不是权重，这里没有对应物），`random.Random(SEED).shuffle`，取前 N。存成两个模式各自需要的元组：cgen `(text, None, None, tgt)`，cparam `(text, None, None, tool, tgt)`。
4. 生成：调 `train_causal_callgen.eval_gen(model, tok, rows, dev, amp, args.max_len, args.gen_bs)` 或 `train_causal_param.eval_gen(...)`（按 `args.mode`），不写新的生成函数；两个旧函数各自处理 `padding_side / use_cache / model.eval() / model.train()`。调用点：每个评估点 `eval_ce` 之后、写 `eval` 事件之前；计时 `gen_s`。生成必须在 `_attn_ctx` 之外——现在 `_attn_ctx` 只包 `_forward_packed`，保持这样，不要为了省事把整个评估段包进去（spec 16.10 #29：无掩码的 `generate` 走 GQA，mem-efficient 内核报 `No available kernel`）。
5. 日志：`eval` 事件加 `val_exact_call`（cgen）或 `val_exact_params`（cparam）、`gen_n`（实际生成的行数）、`gen_s`（秒，保留 2 位）；`--gen-eval 0` 时、以及 `--gen-eval-at last` 下不是 epoch 末的评估点，三个键都不写。`start` 事件加 `gen_eval`、`gen_bs`、`gen_eval_at`。`save_best` 判据仍只看 `val_ce`。`train_s` 不含生成时间（现有训练时钟只包更新，确认不要动）。
6. 评估段的心跳（spec 16.3 倒数第二条）：`eval_ce(model, events, tok_budget, dev, amp, beat=None)` 加可选参数 `beat`（无参可调用），块循环里每 25 个物理块调一次 `beat()`；主流程传 `beat=lambda: heartbeat.emit(gstep, steps, "step")`（`heartbeat.emit` 的签名是 `emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None, status=None, stream=None)`，不要传别的关键字），并在调 `eval_gen` 之前与之后各 `heartbeat.emit(gstep, steps, "step")` 一次。原因：全量 val 有 115,211 行，加 200 行生成，这个窗口里现在没有任何心跳，采样器按 5 × 典型心跳间隔判停滞（`ops/verdicts.py` 第 14 行）会误报。
7. 测试（spec 16.9 第二条）放新文件 `tests/test_share_gen_eval.py`（不往 `test_share_trainer.py` 末尾加用例——工单 09、10 并行，三张往同一文件末尾加必撞；小模型的构造照 `test_share_trainer.py` 现有的辅助函数 import 过来用）：(a) `--gen-eval 3 --gen-bs 2 --gen-eval-at all --eval-per-epoch 2` 跑通，每条 `eval` 事件有 `val_exact_call`（或 cparam 的 `val_exact_params`）、`gen_n == 3`、`gen_s`；改 `--gen-eval-at last` 时只有 `frac == 2` 那条有；(b) `--gen-eval 0` 时 `eval` 事件没有这三个键；(c) 抽样函数单独测：同一批事件两次抽样结果相同；(d) 守卫测试：读 `train_causal_share.py` 源码，用 `ast` 找 `_attn_ctx` 的 `Call` 节点并断言父函数只有 `_forward_packed`（`def _attn_ctx` 那一行本身不算调用），失败信息写明 spec 16.10 #29；(e) `eval_ce` 传一个计数用的 `beat`，手造 ≥ 25 个物理块的事件列表时至少被调一次。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_share_gen_eval tests.test_share_trainer tests.test_share_data` 通过。
- `grep -n "gen_eval\|val_exact_" pipeline/train/train_causal_share.py` 命中；`grep -n "def eval_gen" pipeline/train/train_causal_share.py` 零命中（不许复制旧函数）。
- 小模型 CPU 上 `--smoke --max-events 6 --gen-eval 3 --gen-bs 2 --device cpu` 的 `train_log.jsonl` 里 `eval` 事件带三个新键。
- 不改 `run.py`、不改旧脚本。
