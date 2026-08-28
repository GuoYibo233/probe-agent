# 07 评测端超长事件的三种处理：三个评测脚本加 `--overlong {left,skip,drop-event}`

Status: resolved
Blocked by: （无；第二轮起点 HEAD 7668166 之后）
Spec: `.scratch/kvshare-train/spec.md` 16.2（判据）、16.9（测试）、16.10 #28。改动只在 `pipeline/train/share_data.py`（抽一个函数）、`pipeline/train/train_causal_tool.py`（改调那个函数）、`pipeline/eval/eval_causal_call.py`、`pipeline/eval/eval_causal_param.py`、`pipeline/eval/eval_tool.py`、新测试 `tests/test_eval_overlong.py`。不改 `train_causal_share.py`、不改 `run.py`、不改 skill 文档（文档归工单 12）。

## 背景

新训练器把事件全文 token 数大于 `--max-len`（8192）的事件整条丢弃（`share_data.load_events`），ctool 训练器也一样（`train_causal_tool.load_events` 返回 `(events, dropped)`）。评测端现在的做法是左截：cgen / cparam 的 `generate()` 把提示左截到 `max_len − max_new`（`eval_causal_call.py` 第 213 到 214 行、`eval_causal_param.py` 第 208 到 209 行，`tok.truncation_side = "left"` 在第 590 / 420 行），ctool 的 `score_causal`（`eval_tool.py` 第 116 到 160 行）把全文左截到 `max_len`，窗口外的边界记零 logits 并计 `n_oow`。gyb 要三种处理都做成开关，回头对比。

## 要做的

1. `share_data.py`：把 `load_events` 第 146 到 147 行那次全文分词抽成模块级函数 `full_token_ids(tok, full_text) -> list[int]`（原样保留 `add_special_tokens=False, truncation=False`），紧接着定义 `n_full_tokens(tok, full_text) -> int`，函数体 `return len(full_token_ids(tok, full_text))`。`load_events` 第 145 到 153 行的循环改成 `full_ids = full_token_ids(tok, e["full_text"])` 后照旧判 `len(full_ids) > max_len`、照旧写 `e["full_ids"] = full_ids` 与 `e["n_full"] = len(full_ids)`（分词次数不变，一个事件仍只分一次）；`train_causal_tool.load_events` 第 128 行改成 `n_full = share_data.n_full_tokens(tok, e["full"])`（它只要计数；原来没写 `truncation=False`，默认本来就不截断，数值不变）。另外两个只给评测端用的纯函数也放 `share_data.py`：`event_full_texts(rows) -> dict[event, full_text]`（`sent_idx` 最大那一行的 `text`；不要动 `load_events` 里 `events_all.append(dict(...))` 那段分组——那段钉着 spec 3.2 的随机数消耗顺序）和 `select_keys(mode, keys, n_full, prompt_len, excluded_rows, max_len, max_new) -> (kept_keys, counts)`（`n_full` 与 `prompt_len` 是按 key 查的字典，`excluded_rows` 是 ctool 传来的剔除行集合，`counts` 是 `n_left_truncated / n_skipped_rows / n_dropped_events / n_excluded_by_ctool` 四个整数的字典），cgen 与 cparam 两个脚本都调这一个函数（两个脚本已把 `pipeline/train` 挂进 `sys.path`；各写一份就是两份真源）。
2. `eval_causal_call.py` 与 `eval_causal_param.py` 各加 `--overlong`，`choices=["left", "skip", "drop-event"]`，默认 `left`。三种模式的判据照 spec 16.2 逐条实现：
   - 提示长度 `L(k)`：cgen 是 `len(tok(fired[k]["row"]["text"] + sep, add_special_tokens=False, truncation=False)["input_ids"])`（与 `generate()` 第 213 行的分词口径一致）；cparam 对同一批 `keys` 造两套提示（第 432 到 433 行 `for tag, given in (("gt_tool", gt_given), ("pred_tool", pred_given))`，两块共用同一批 `keys`——第 403 到 404 行注释、第 440 行 `n = len(keys)`、第 446 行顶层 `n_events_scored`），`L(k)` 取两套提示 token 数的最大值，三种模式都只用这一个 `L(k)`，两块的分母因此仍是同一批 `keys`。
   - 三步顺序写死：readonly 排除（第 576 到 580 行）→ `--overlong` 筛选（分词器加载之后，调 `select_keys`）→ `--limit`（第 581 到 582 行）；cparam 的筛选落在第 429 行 `pred_given` 建好之后、第 432 行的循环之前，只改 `keys` 一个列表。`n_events_fired` 保持筛选前的原义。
   - `left`：行为不变，只加计数 `n_left_truncated`（`L(k)` 大于 `max_len − max_new` 的行数）。
   - `skip`：`L(k)` 大于 `max_len − max_new` 的行不进 `prompts`、不进 `keys`（也就不进总表、按工具分桶、样本），计数 `n_skipped_rows`。
   - `drop-event`：对 `keys` 里的每个事件，按 `share_data` 的分组规则（`share_data.py` 第 121 到 131 行：不过滤行，`sent_idx` 最大那一行的 `text`）取全文，`n_full_tokens` 大于 `meta["max_len"]` 的事件整个从 `keys` 去掉，计数 `n_dropped_events`；剩下的行里提示仍超长的左截并计 `n_left_truncated`。只对 `keys` 里的事件分词（test 集 391,893 行，别对全集分词）。
   - 与 ctool 评测的衔接（spec 16.2「衔接」段）：两个脚本第 569 / 397 行 `assert len(rows) == logits.shape[0]` 按下标对齐 `logits_test.pt`，这个断言保留。cgen / cparam 自己从 logits 加 θ 算触发点（第 495 到 497 行只从 REPLAY_REPORT 读 `temperature` 与 `chosen_theta`），所以读 `logits_test.meta.json` 的 `excluded_idx`（第 3 条让 eval_tool 写的；键不存在——旧缓存——按空列表）之后，这些行不许当触发点候选（零 logits 过 softmax 是均匀分布，不能靠 θ 挡），一个事件在剩下的行里挑触发点；剔得只剩零个候选行的事件没有触发点、不判分，计数 `n_excluded_by_ctool`（数事件）。ctool 用 `skip` 只剔窗口外的边界，同一事件窗口内的行照常可以触发，这条规则把 ctool 的「剔边界」原样映射成这里的「剔候选」。
   - 报告：JSON 与 MD 都写 `overlong_mode` 和 `n_left_truncated / n_skipped_rows / n_dropped_events / n_excluded_by_ctool` 四个计数（没发生的写 0，键不省略）；cparam 另写诊断键 `n_left_truncated_by_tag = {"gt_tool": n, "pred_tool": n}`（各按自己那套提示长度数；cgen 不写）。ACCEPT 脚本读的现有键一个都不改名。`--self-fire` 路径（第 378 行 `self_fire_block`，自己另调 `generate()`）不动，报告里的 `overlong_mode` 只描述主路径。
3. `eval_tool.py` 的 `score_causal` 与调用它的主流程加 `--overlong`（同样三个值，默认 `left`）：
   - `left`：不变。
   - `skip`：窗口外边界（`read_position` 返回 −1 的那些）不进任何分母、不产生触发点；计数 `n_skipped_bounds`。
   - `drop-event`：`n_full_tokens(tok, 全文) > max_len` 的事件整个剔除（全部边界），计数 `n_dropped_events`、`n_dropped_bounds`。这里的「全文」按 ctool 训练器自己的规则（`train_causal_tool.py` 第 93 到 96 行：先按 `label in label2id` 过滤行，再取最后一行的 `text`）——`eval_tool.py` 的 `rows` 本来就是过滤后的，`score_causal` 第 124 行取的 `full` 就是这个；不要改成 share_data 的不过滤规则（spec 16.10 #34 记了两边的差别）。
   - 形状不变：三种模式下 `logits_*.pt` 都写全行数，剔除的行写零 logits（和现在 `n_oow` 的行一样），`score_causal` 返回 `(out, excluded_idx)`，`excluded_idx` 是剔除行的下标列表（`left` 下空列表）。调用方把 `excluded_idx` 写进 `logits_*.meta.json`（现有键 `weights / rows / adopted` 之外加 `overlong_mode` 与 `excluded_idx`），算指标与 REPLAY_REPORT 之前先按 `excluded_idx` 剔行。下游 cgen / cparam 按下标对齐 `logits_test.pt`（`eval_causal_call.py` 第 569 行硬断言），所以行数不能变。
   - `--cached-logits` 路径（`eval_tool.py` 第 404 行附近读缓存）：`.meta.json` 的 `overlong_mode` 与本次 `--overlong` 不同（或键不存在而本次不是 `left`）就 `SystemExit` 并写明两种模式；相同就照常，并从 `.meta.json` 读回 `excluded_idx`。
   - `REPLAY_REPORT.json/.md` 写 `overlong_mode` 与三个计数，另把 `n_oow` 也写进去（现在只是 `score_causal` 第 158 行的 print，不在报告里）。
   - `--overlong` 只对 `--head causal` 生效：`max_len` 与 `tok` 只在 causal 分支里赋值（第 353 到 360 行），`--head mbert` 传非 `left` 的值直接 `SystemExit` 并说明，mbert 的报告 `overlong_mode` 恒写 `left`、三个计数写 0。
4. 测试 `tests/test_eval_overlong.py`（spec 16.9 第一条）：真实分词器 `MODELS["qwen"]` 路径不存在就 `skipTest`。手造 3 个事件（一个全文超过很小的 `max_len`、一个提示刚好超过 `max_len − max_new`、一个正常），断言：(a) `n_full_tokens` 对同一段文本与 `load_events` 的 `dropped_events` 判据一致；(b) `share_data.select_keys` 在三种模式下的计数与留下的 key 集合，以及给定 `excluded_rows` 时的剔除（部分行被剔的事件留下、全部候选行被剔的事件去掉并计入 `n_excluded_by_ctool`）；再加一条 cparam 用例：一个 key 的真值工具名与预测工具名 token 数不同、只有 `pred_tool` 那套超过 `max_len − max_new`，断言 `skip` 下这个 key 被剔（最大值规则）、`n_skipped_rows == 1`，`left` 下 `n_left_truncated == 1` 且 `n_left_truncated_by_tag == {"gt_tool": 0, "pred_tool": 1}`；(c) `score_causal` 在三种模式下返回的 `out` 行数都等于输入行数、`excluded_idx` 与计数各对、被剔除行的 logits 全零（小模型可用 `Qwen3Config` 随机初始化一个 2 层的 backbone 加一个线性头，照 `tests/test_share_trainer.py` 的做法）；(d) `--cached-logits` 的模式校验：手造一个 `.meta.json` 写 `overlong_mode: "skip"`，用 `left` 读它要 `SystemExit`；(e) `--head mbert` 传 `--overlong skip` 必须 `SystemExit`。测试全部用手造的小事件，不读 `pipeline/data/` 下的现役数据目录。
5. 并行落点：工单 08 与 10 同时在改 `share_data.py`（08 改第 205 行的行元组与第 274 行的拆包，10 在文件末尾加 `epoch_minibatches`）；本工单只动 `load_events` 里第 145 到 153 行那段和新加的四个函数，新函数放在 `_pad16`（第 60 行）之后、`load_events`（第 73 行）之前，不要动别处，合并冲突主会话收账时解。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_eval_overlong tests.test_share_data tests.test_ctool_readpos` 通过。
- `grep -n "full_token_ids\|n_full_tokens" pipeline/train/share_data.py pipeline/train/train_causal_tool.py pipeline/eval/eval_tool.py pipeline/eval/eval_causal_call.py pipeline/eval/eval_causal_param.py` 五个文件都命中；`grep -n 'tok(e\["full_text"\]' pipeline/train/share_data.py` 零命中（`load_events` 不再内联分词）；`grep -n "def select_keys" pipeline/` 只命中 `share_data.py` 一处。
- 三个评测脚本 `--help` 都列出 `--overlong`，默认 `left`。
- 不加 `--overlong` 时三个脚本的行为与改前逐字段相同（报告只多了 `overlong_mode` 与计数键）。
- `python3 run.py selfcheck` 通过（不改注册表也要跑一遍）。

## Comments

- 2026-08-28 plan-8-28 收账：wave5 实现 1 轮修复过评审，分支 `ticket/2026-08-28-wave5/T07`（base `07907db`，head `eadb3f8`），合并为 `df14ccd`（无冲突）。评审 minors 两条：F4 `score_causal` 返回值从二元组改成三元组 `(out, excluded_idx, counts)`（多出的 `counts` 带 `n_oow / n_skipped_bounds / n_dropped_events / n_dropped_bounds` 进报告，主会话接受）；N1 `ev_row_idx` 的构建在 `--self-fire` 下成了不被使用的死计算（O(len(rows))，不影响输出，记遗留）。实现者的五条裁决主会话全部接受：`select_keys` 的 `keys` 参数是 `dict[key] -> list[候选行下标]`，只判「候选行是否全部被 ctool 剔除」，触发点在剔除候选行之后由主流程从剩余行里算（`eval_causal_call.py` 第 587 到 594 行 `cand_idx`，符合 spec 16.2 衔接段）；`.meta.json` 多写四个计数；REPLAY_REPORT 的 `overlong_mode` 与计数固定取 test 堆；`--overlong` 对 val 堆（拟温度、扫 θ）同样生效；改了 `tests/test_ctool_readpos.py` 两处调用点。收账补丁清单第 1 条（tokenizer 与 `max_len` 提前到 `--limit` 之前）核过：主路径 `excluded_rows` 在第 587 行、tokenizer 第 612 行、`select_keys` 第 640 行、`--limit` 第 648 行，顺序对；第 420 行的 `--limit` 是 fire_head 旧路径，不在范围内。
