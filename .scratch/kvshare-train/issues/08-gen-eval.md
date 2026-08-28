# 08 新训练器加回生成式评估：`--gen-eval N`（默认 200）与 `--gen-bs`

Status: ready-for-agent
Blocked by: （无）
Spec: `.scratch/kvshare-train/spec.md` 16.3（做法）、16.9（测试）、16.10 #29 #30。改动只在 `pipeline/train/train_causal_share.py`、`pipeline/train/share_data.py`（行元组加第 6 位）、`tests/test_share_trainer.py`、`tests/test_share_data.py`（手造行元组补第 6 位）。不改旧脚本、不改 `run.py`、不改文档。

## 背景

旧训练器每次评估定种子抽 200 行做 greedy 生成，报 `val_exact_call`（cgen，`train_causal_callgen.py` 第 309 到 331 行 `eval_gen`、第 448 到 450 行抽样、第 535 到 538 行写日志）或 `val_exact_params`（cparam，`train_causal_param.py` 第 235 到 259、358 到 360、418 到 422 行），只进日志不选 best。新训练器第一轮按决定 4 去掉了。gyb 要做成开关加回来，推荐值开（200）。

## 要做的

1. `share_data.load_events`（第 205 行）行元组加第 6 位 `dict(tgt=<目标串>, tool=<工具名或 None>)`：`tgt` 是分词前的目标串 `tgt_str`（cgen 是整条调用串，cparam 是参数串——就是现在传给 `tok(...)` 的那个字符串）；`tool` 在 cparam 分支是拼 `tail` 时用的工具名，cgen 分支是 `None`。第 0 到 5 位一个都不动。`pack_event / allowed_mask / batch_mask / worst_blocks` 里凡是按下标读行的地方不需要改，但要通读一遍确认没有 `len(row) == 6` 这种断言。测试里手造行元组的地方全部补上第 6 位。
2. `train_causal_share.py` 加参数 `--gen-eval`（int，默认 200，0 关闭）与 `--gen-bs`（int，默认 8），加在 `--log-every` 之后。
3. 抽样（照 spec 16.3）：`ev_events` 加载完之后，摊平成行列表（事件按加载顺序、行按事件内顺序），只留第 5 位 `w > 0` 的行，`random.Random(SEED).shuffle`，取前 N。存成两个模式各自需要的元组：cgen `(text, None, None, tgt)`，cparam `(text, None, None, tool, tgt)`。
4. 生成：调 `train_causal_callgen.eval_gen(model, tok, rows, dev, amp, args.max_len, args.gen_bs)` 或 `train_causal_param.eval_gen(...)`（按 `args.mode`），不写新的生成函数；两个旧函数各自处理 `padding_side / use_cache / model.eval() / model.train()`。调用点：每个评估点 `eval_ce` 之后、写 `eval` 事件之前；计时 `gen_s`。生成必须在 `_attn_ctx` 之外——现在 `_attn_ctx` 只包 `_forward_packed`，保持这样，不要为了省事把整个评估段包进去（spec 16.10 #29：无掩码的 `generate` 走 GQA，mem-efficient 内核报 `No available kernel`）。
5. 日志：`eval` 事件加 `val_exact_call`（cgen）或 `val_exact_params`（cparam）、`gen_n`（实际生成的行数）、`gen_s`（秒，保留 2 位）；`--gen-eval 0` 时三个键都不写。`start` 事件加 `gen_eval`、`gen_bs`。`save_best` 判据仍只看 `val_ce`。`train_s` 不含生成时间（现有训练时钟只包更新，确认不要动）。
6. 测试（spec 16.9 第二条）：在 `tests/test_share_trainer.py` 现有的小模型 `main()` 用例上加：(a) `--gen-eval 3 --gen-bs 2` 跑通，`eval` 事件有 `val_exact_call`（或 cparam 的 `val_exact_params`）、`gen_n == 3`、`gen_s`；(b) `--gen-eval 0` 时 `eval` 事件没有这三个键；(c) 抽样函数单独测：同一批事件两次抽样结果相同；(d) 守卫测试：读 `train_causal_share.py` 源码，断言 `_attn_ctx(` 的调用只出现在 `_forward_packed` 函数体内（按 `ast` 找 `Call` 节点的父函数，或按行号区间 grep），失败信息写明 spec 16.10 #29。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data` 通过。
- `grep -n "gen_eval\|val_exact_" pipeline/train/train_causal_share.py` 命中；`grep -n "def eval_gen" pipeline/train/train_causal_share.py` 零命中（不许复制旧函数）。
- 小模型 CPU 上 `--smoke --max-events 6 --gen-eval 3 --gen-bs 2 --device cpu` 的 `train_log.jsonl` 里 `eval` 事件带三个新键。
- 不改 `run.py`、不改旧脚本。
