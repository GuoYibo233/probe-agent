# spec: 缓存复用训练器（kvshare-train）

Status: ready-for-agent
日期: 2026-08-28。裁决来源是 `plans/2026-08-28-kvshare-draft.md` 第二节的七条（gyb 确认或授权按推荐锁定）；实施期间由 plan-8-28 会话自主拍板的决定编号记在同目录 `decisions.md`，本文引用时写「决定 N」。注意力前向的内核选择与验证结果在同目录 `design-attention.md`（8-28-assistant-2 交付）。

## 1 目标与范围

这一轮交付一个新的训练程序 `pipeline/train/train_causal_share.py`，服务 cgen 和 cparam 两个格（`--mode cgen|cparam`），做四件事：一个事件的全文只过一遍底座，每个切点的目标段接在共享的前缀后面算损失；不截断任何样本，全文超过上限的事件整条丢弃并计数；上限默认 8192（冒烟后可能退到 6144）；epoch 默认 1。同时 ctool（`train_causal_tool.py` 与 `eval_tool.py`）吃三项改动：丢弃规则、上限默认值、切点读取位置规则，并把更新单位改成 8 个事件。

格名不变（还是 cgen / cparam / ctool），数据不变，四个评测脚本一行不改。按 `extending.md` 第 113 到 121 行的判据，这次是「换实现」不是「加新格」，不走 §3.1 新格清单（决定 3）。

范围之外：评测端超长事件的处理、学习率扫描、`--fire-head`（决定 4）、第十四节的六条实验。旧的逐行训练器 `train_causal_callgen.py` 和 `train_causal_param.py` 一行不改，作为对齐参照冻结（决定 3）。

成功的样子：第 9 节的对齐检查通过（fp32 逐行 loss 最大绝对差 ≤ 2e-5，依据是 `design-attention.md` 的 CPU 实测 2.15e-6 与 H100 实测 4.41e-6）；H100 上新训练器按相同累计行数比的每秒行数高于旧训练器，两套对照各自配对（决定 9，数字都来自 `pipeline/runs/np821b06_gptoss_cgen/train_log.jsonl` ep 0，tokyo108 H100，2026-08-28 由 8-28-assistant-1 复核）：累计值 `ips`（本 epoch 累计行数 ÷ 训练秒数）在 1,600 / 9,600 / 19,200 行处对 2.76 / 3.26 / 3.97；窗口值 `ips_win` 在 0 到 1,600 / 8,000 到 9,600 / 17,600 到 19,200 行这三个窗口对 2.77 / 3.94 / 6.24（`plans/2026-08-28-plan.md` 第 12.10 节的三个数是窗口值；第 9.2 节 A_h100 的 2.75 是 1,600 行处的累计值）。六个数都要高；显存峰值按第 10 节的最坏块量，余量 10% 以上。

## 2 名字（全文只用这些词）

- 事件：train.jsonl 里 `event` 字段相同的一组行。事件全文 = 这组行里 `sent_idx` 最大那一行的 `text`。
- 行：jsonl 的一条记录，也是一个训练实例。行文本 = 这一行的 `text`，是事件全文的前缀。
- 切点：行文本的字符长度 `len(text)`。
- 前缀 token：事件全文分词得到的 token 序列 `full_ids`。
- 旧序列：旧训练器给一行构造的 prompt token 序列 `old_ids`（第 3.4 节）。
- 目标串 token：`tgt_ids`（第 3.3 节）。
- 公共前缀长度 p：`old_ids` 与 `full_ids` 的最长公共前缀的 token 数。
- 目标段：`old_ids[p:] + tgt_ids`。
- 拼接序列：一个事件的「前缀 token（截到最大 p）+ 全部目标段按行顺序拼接」。
- 逻辑小批：4 个事件的全部行，损失的归一化单位。
- 物理块：一个逻辑小批按 token 预算切出的一次前向所含的事件。
- 更新：一次 `opt.step()`；一次更新 = `--accum` 个逻辑小批，默认 2，即 8 个事件。
- 上限 `--max-len`：事件全文 token 数的上限，超过就整条丢弃。
- token 预算 `--tok-budget`：一个物理块允许的「事件数 × 块内最长拼接序列长度」上限。

## 3 数据与分词

### 3.1 输入

`<data>/train.jsonl` 与 `<data>/val.jsonl`，字段照旧训练器：`event`、`sent_idx`、`n_sents`、`text`、`label`、`label_call`、`w`。现役数据 `pipeline/data/nyapass_aw_v1/gptoss/`：train 186,479 行 4,127 个事件，val 115,211 行 2,556 个事件，`w` 全部是 1.0（2026-08-28 清点）。

### 3.2 事件分组与前缀性质

按 `event` 分组（事件顺序 = 在文件里首次出现的顺序，不按事件名重排），组内按 `sent_idx` 升序，事件全文取 `sent_idx` 最大那一行的 `text`（在 `--readonly-env` 过滤之前取，过滤只丢行不换全文）。前缀性质检查照 `train_causal_tool.py` 第 112 到 115 行：`random.Random(SEED)` 抽 50 个事件断言每一行的 `text` 都是全文的前缀。SEED = 42。

`load_events` 里各步的顺序写死（随机数发生器的消耗顺序决定抽样结果）：分组 → 前缀性质抽查（`random.Random(SEED)`，对丢弃之前的全部事件）→ 每个事件全文分词得到 `n_full`，按 3.5 丢弃超上限事件 → 按 `limit` 与 `order` 取子集（`order="random"` 用一个新建的 `random.Random(SEED)` 打乱；`order="shortest"` 按 `n_full` 升序）→ 只对留下的事件做逐行分词（3.3、3.4）与行级丢弃。逐行分词是新增的开销（train 186,479 行），放在取子集之后，`--smoke` / `--max-events` 才省得下来；`--mem-probe` 要全集的拼接长度，那一次例外，全集逐行分词一遍。

### 3.3 行的取舍与目标串（照抄旧训练器，不许另写一套）

- cgen：目标串 = `tok(label_call, add_special_tokens=False) + [eos]`（`train_causal_callgen.py` 第 162 到 163 行）；`len(tgt_ids) > MAX_TGT_TOK`（160）的行丢弃并计数 `dropped_rows_tgt`（第 164 到 166 行）。`--readonly-env` 打开时非只读的行整条丢弃，计数照 `readonly_map` 的口径（第 133 到 142 行）。
- cparam：prompt 尾巴 = `param_prompt_tail(label)` = `CALL_SEP + label + "("`；目标串 = `param_target(label, label_call) + [eos]`，`param_target` 返回 None 的行丢弃并计数 `assembly_mismatch`（`train_causal_param.py` 第 89 到 106 行、第 129 到 136 行）。
- 每一行都是实例，没有别的筛选。
- 旧脚本的两道硬停照搬：cparam 的剥离失败率（`param_target` 返回 None 的行占比）train 或 val 超过 5% 就退出（`train_causal_param.py` 里那道闸门，实现者按 `assembly_mismatch` grep 到原文后照抄阈值与措辞）；train 或 val 装载后 0 行就退出。
- 实现方式：`share_data.py` 直接 `import` 两个旧脚本的常量和函数（`CALL_SEP`、`MAX_TGT_TOK`、`param_prompt_tail`、`param_target`、`MODELS`、`SEED`），不许复制粘贴一份。这两句 import 必须写在 `load_events` 的函数体里（延迟 import），`share_data.py` 的模块顶层只许 stdlib 与 torch：三个旧脚本除了 `__main__` 守卫，模块层还有一道 `transformers >= 5.14` 的版本门（`train_causal_callgen.py` 第 55 到 60 行、`train_causal_param.py` 第 53 到 58 行、`train_causal_tool.py` 第 50 到 55 行，不满足就 `raise SystemExit`），mbert-env 钉死 transformers 4.57.6（`invariants.md` 第 53 行），而 `eval_tool.py` 是 mbert 与 causal 两条线共用的脚本（`run.py` 的 `eval-tool-mbert` 用 `py="mbert"`），顶层链式 import 会让 `eval-tool-mbert` 与 `eval-mcall` 在 import 阶段退出（`tests/test_cparam_assembly.py` 第 8 到 12 行记过同一现象）。`read_position` 不碰任何训练脚本。

### 3.4 公共前缀规则（草稿 2.4，gyb 已锁）

对每一行：

```
old_ids  = tok(text + TAIL, add_special_tokens=False)     # TAIL: cgen 是 CALL_SEP，cparam 是 param_prompt_tail(label)
full_ids = tok(full_text, add_special_tokens=False)
p        = LCP(old_ids, full_ids)                          # 逐 token 比到第一个不同处
seg_ids  = old_ids[p:] + tgt_ids
seg_lab  = [-100] * len(old_ids[p:]) + tgt_ids
```

断言 `len(old_ids[p:]) >= 1`（分隔串的 `[`、`CALL`、`]`、`Ġ` 四个 token 不会出现在全文延续里，实测尾巴多出的 token 数只有 −1、0、1 三种，草稿 4.3）。这条规则使新训练器每一行的 token 序列和旧训练器逐 token 相同。

`add_special_tokens` 的取值、pad/eos/截断方向的 tokenizer 设置，照 `train_causal_callgen.py` 的 `build()` 第 216 到 223 行；新训练器直接调用旧脚本的 `build()` 拿 tokenizer 和模型（决定 6）。`build()` 只允许加两个带默认值的关键字参数：`attn_impl=None`（None 保持旧行为，否则传给 `from_pretrained` 的 `attn_implementation`）和 `path=None`（None 时照旧查 `MODELS[base]`，否则直接从这个目录装模型与 tokenizer，给第 12 节的小模型测试用）。

### 3.5 丢弃规则（草稿 2.1，gyb 已锁；决定 5）

- 事件级：`len(full_ids) > max_len` 的事件整条丢弃，计数 `dropped_events`（train / val 各一个数，写进 `start` 事件）。判据只看事件全文的 token 数，不看拼接序列长度（拼接序列由 token 预算兜底）。`plans/2026-08-28-plan.md` 第四节的表：8192 时 train 丢 1 个事件，6144 丢 58 个。
- 行级：3.3 的两条照旧。
- 没有任何截断：`tok(...)` 一律 `truncation=False`。加载完数据后断言「最长的拼接序列长度 ≤ `max_len + MAX_BOUNDS × (MAX_TGT_TOK + 8)`」，`MAX_BOUNDS` 从 `pipeline/annotate/rules.py` import（现值 64，每个事件的行数上限；平均行数 45.2 只是均值，1,930 个事件顶到 64 行，`plans/2026-08-28-plan.md` 第 12.3 节），断言不成立就报错退出（防 tokenizer 版本漂移把尾巴撑长）。

## 4 前向形态

语义定义在这里，内核选择与实现路径以 `design-attention.md` 为准（2026-08-28 已交付，CPU 等价验证通过，验证脚本与结果收在 `verify/`）。定下来的实现路径（决定 12）：

- 形态 A：一个事件打包成一条序列一次前向；多事件沿批维摆，按 token 预算组批。形态 B（前缀 `use_cache` 再各段接缓存）不用：和 `--grad-ckpt` 互斥、每段 cat 出的 K/V 副本在 8192 事件上约 20 GB。
- 内核：`attn_implementation="sdpa"`；在 cuda 设备上，训练、评估、对齐检查三处前向都包在 `torch.nn.attention.sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])` 里。有掩码时 flash 直接拒绝；H100 上实测 torch 的默认选择落到 cuDNN（`design-attention.md` 第七节：峰值 31.47 对 mem-efficient 的 31.43 GiB），所以要显式钉死 mem-efficient，不随 torch 默认顺序和 cuDNN 版本漂移（sdpa 文档写明 cuDNN 路径可能选非确定性算法）；显式限定之后一旦退到 math 就报错退出而不是爆显存（math 内核每层留一份 fp32 的 `(1, 16, L, L)`：L = 9,100 时每层 5.3 GB、28 层 148 GB）。CPU 上不套这个上下文（会抛 `No viable backend for scaled_dot_product_attention`），CPU 走默认内核。`--attn-impl` 默认 `sdpa`，只接受 `sdpa`（flex_attention 留作冒烟后的优化，不在这一轮）。
- 掩码：调用方自己造加性掩码（可看 0、不可看 −inf），形状 `[B, 1, L, L]`，每个物理块造一份，L 补到 16 的倍数。掩码 dtype 必须等于 query 进 sdpa 时的 dtype：autocast bf16 下用 bf16，第 9 节的 fp32 对齐检查下用 fp32（fp32 query 配 bf16 掩码会被 torch 拒收：`Expected attn_mask dtype to be bool or float or to match query dtype`；fp32 掩码在 autocast 下会被逐层 cast 出 28 份副本）。不许传 bool 掩码（torch 的 sdpa 每层各转一份 float，`attention.cpp` 的 `convert_boolean_attn_mask`，28 × 166 MB ≈ 4.6 GB）。
- position_ids：显式传张量，每段从 p_k 接着数（`modeling_qwen3.py` 直接吃调用方给的 position_ids）；补到 16 的 pad 位也要给 position_ids（接着数）。
- 损失位：用 `(batch 下标, query 位置, 目标 token id, 行号)` 的下标表，先从末层隐状态 gather 出损失位再过 `lm_head`（或者用 `logits_to_keep`），不算全位置 logits（L = 9,100 的全位置 logits 是 2.8 GB bf16，评估块 32,768 个位置就是 10 GB）；每行 ce 的定义仍是第 4 节末段。
- `--grad-ckpt` 与 `--lora` 在这个形态下都验证过（CPU：梯度检查点下 loss 差 0；peft 下 loss 差 0 且只有适配器参数有梯度）。

一个事件的拼接序列：

```
tokens    = full_ids[:P] + seg_1 + seg_2 + ... + seg_K        # P = max_k p_k，K = 事件的行数
positions = [0..P-1] + [p_1, p_1+1, ...] + [p_2, p_2+1, ...] + ...
labels    = [-100]*P + seg_lab_1 + ... + seg_lab_K
```

注意力允许关系（True = 可看）：前缀内部因果；第 k 段的第 i 个 token 可看前缀的前 p_k 个位置和本段的前 i+1 个 token；段与段之间互不可见；前缀看不到任何目标段。物理块内多个事件走 batch 维，右侧 pad：真实 token 看不到 pad，pad 作为 query 的那些行只让 pad 看自己（整行不可看会让 softmax 出 NaN，`design-attention.md` 第 2.3 节），pad 位置不算损失。

每行 loss：按 `inst_ce`（`train_causal_callgen.py` 第 231 到 248 行）的口径，本段目标 token 位置上的交叉熵求平均（logits 在位置 t 预测位置 t+1 的 token，只算 `label != -100` 的位置，分母是本行目标 token 数）。第一个目标 token 由本段最后一个 prompt token 预测，这个 token 在本段内（3.4 的断言保证）。

## 5 损失与更新单位（草稿 2.2，gyb 已锁）

- 逻辑小批 = 4 个事件（`--events-per-mb` 默认 4）的全部行 R。`W = Σ_{r∈R} w_r`。
- 逻辑小批按 token 预算拆成物理块 C_1..C_m：事件按拼接序列长度降序，贪心装块，块的「事件数 B × 块内最长拼接序列补到 16 的倍数后的长度 L_pad」≤ `--tok-budget`（判据用 L_pad，和掩码的补齐同口径）；单个事件超预算时独自成块（允许超预算）。
- 每个物理块：`loss_C = Σ_{r∈C} w_r · ce_r / W`，`(loss_C / n_g).backward()`，`n_g` 是这一组里实际的逻辑小批数（前面各组都是 `accum`，epoch 末尾那一组是 `min(accum, M − 组起点)`）。m 个块的梯度之和等于整个逻辑小批一次算完的梯度，也等于旧训练器 `loss = (ce·w).sum()/w.sum()` 再 `(loss/accum).backward()`（第 494 到 505 行）。
- 每一组（`--accum`，默认 2，个逻辑小批）：`clip_grad_norm_(1.0)` → `opt.step()` → `sch.step()` → `opt.zero_grad()`。epoch 末尾不满 `accum` 的一组也做一次更新，除数按上面的 `n_g` 取（旧训练器不做尾组更新，梯度会漏到下一个 epoch；新训练器不许漏，也不许让尾组的步长打折）。
- 优化器与调度器照旧：`AdamW(weight_decay=0.01)`，`get_linear_schedule_with_warmup(opt, int(steps*0.05), steps)`。每 epoch 的更新数 `U = ceil(M / accum)`，`M = ceil(n_events / events_per_mb)` 是逻辑小批数；`steps = U · epochs`。这个 U 就是第 6 节评估时机用的 U。
- 事件顺序：每个 epoch 用 `random.Random(SEED + ep)` 打乱事件列表，按顺序每 4 个一个逻辑小批（最后一个可以不满）。
- 学习率默认值不动：全参 `FULL_LR = 1e-5`，LoRA 走 `lora_util.resolve_lr`（默认 2e-4）。`--lora`、`--grad-ckpt` 的接线照旧训练器（`lora_util.wrap / prepare_grad_ckpt / opt_params / save_merged / meta_block`）。
- `--epochs` 默认 1。

## 6 评估与最好版本（草稿 2.7）

- `val_ce` 的口径照 `eval_ce`（第 259 到 291 行）：全部 val 行的 `Σ w·ce / Σ w`，用第 4 节的拼接前向算（同样只在损失位过 `lm_head`），`torch.no_grad` 加 bf16 autocast，物理块预算 `--eval-tok-budget`（默认 = 2 × `--tok-budget`）。`w_tot <= 0` 硬停照旧。
- 时机：每个 epoch 评 `E = --eval-per-epoch`（默认 4）次，评估点是 `{ceil(U·k/E) : k = 1..E}` 这个集合（U < E 时重复的点合并，只评一次），本 epoch 的更新次数到达其中一个点就评一次全量 val；k = E 的那个点是 epoch 末。
- 最好版本：`val_ce` 最低的一次，写 `<out>/best/`，布局与旧训练器逐项同构（第 530 到 552 行）：全参 `model.save_pretrained`，LoRA `lora_util.save_merged`；`tok.save_pretrained`；`meta.json` 的旧字段逐字段照旧训练器的写法（`base, base_path, data, max_len, seed, epoch, call_sep, transformers`；`readonly_env` 只在打开时才写这个键——`eval_causal_call.py` 判的是键在不在，不是值；`lora`、`grad_ckpt` 照旧；cparam 的 `param_only: true`），新增 `trainer: "share"`, `frac`（评估点序号 1 到 E）, `gstep`, `tok_budget`, `events_per_mb`, `accum`, `attn_impl`。评测脚本读 `call_sep`、`max_len`、`param_only`、`data`（三方对拍）、`readonly_env`（键在不在）（`eval_causal_call.py` 第 513 到 516、585 到 586 行；`eval_causal_param.py` 第 342 到 345、415 到 416 行）。`max_len` 写 8192 之后两个评测脚本的提示左截长度会从 4,000 变成 8,096（它们用 `max_len − max_new`），这是有意的：评测端不截断和训练端同口径；评测显存在评测排卡时按 8192 估（决定 13）。
- 不做生成式评估（旧 `val_exact_call` / `val_exact_params` 与 `--gen-bs` 去掉，决定 4）。

## 7 日志 `<out>/train_log.jsonl`

事件与字段（旧字段保留名字，新字段加在后面）：

- `start`：`base, base_path, env, mode, n_train_events, n_train_rows, n_eval_events, n_eval_rows, dropped_events_train, dropped_events_val, dropped_rows_tgt_train, dropped_rows_tgt_val, assembly_mismatch_train/val（cparam）, steps, epochs, smoke, max_len, max_tgt_tok, tok_budget, eval_tok_budget, events_per_mb, accum, eval_per_epoch, log_every, mem_probe, lr, attn_impl, seed, device, readonly_env, lora（条件）, align_pass, align_maxdiff, align_bf16_warn`。
- `step`（每 `--log-every` 次更新一条，默认 50）：`ep, gstep, rows, loss, lr, ips, ips_win, eps, train_s, peak_mem_gb`。`rows` = 本 epoch 到现在处理的累计行数；`loss` = 自上一条 step 以来全部逻辑小批损失的平均，累加器在写完日志时清零（草稿 2.7 对第 13.7 节的修正）；`train_s` = 本 epoch 累计的训练秒数，评估期间时钟暂停（旧训练器的评估在 epoch 之后，第 486 行的 t0 从不含评估时间，新训练器在 epoch 中间评估所以必须扣掉）；`ips` = `rows / train_s`（口径和旧第 516 行一致）；`ips_win` = 自上一条 step 以来的行数 ÷ 这段的训练秒数；`eps` = 累计事件数 ÷ `train_s`；`peak_mem_gb` = `torch.cuda.max_memory_allocated()` 换算 GB，取完重置。
- `mem_probe`（`--mem-probe` 打开时，训练开始前写两条）：`kind`（`longest_event` / `fullest_block`）, `n_events, packed_len_max, peak_mem_gb`。做法见第 10 节。
- 心跳（`extending.md` 第 144 行，不接的脚本在监控窗口里永远是 warm-up）：照旧训练器第 71、481、517、554 行——`import heartbeat`（`ops/heartbeat.py`），训练开始前 `heartbeat.emit(0, steps, "step")`，每条 `step` 日志同时 `heartbeat.emit(gstep, steps, "step", loss=...)`，收尾 `heartbeat.emit(gstep, steps, "step", status="done")`。
- `eval`：`ep, frac, gstep, val_ce, n_eval_rows`。
- `save_best`：`ep, frac, gstep, val_ce`。
- `done`：`best_val_ce, best_ep, best_frac, total_rows, wall_s`。驱动器只认 `done` 事件是否存在（`pipeline/driver.py` 第 772、810 行）。
- `<out>/train_log.jsonl` 已存在时拒绝二次训练，`--force` 放行（照旧 第 380 到 383 行）。

## 8 命令行与注册表

脚本 `pipeline/train/train_causal_share.py`。参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--mode` | 必填，`cgen` / `cparam` | 目标串与尾巴的构造走哪一套 |
| `--base` | `qwen` | `qwen / qwen17 / qwen4`，路径表复用旧脚本的 `MODELS` |
| `--env` | `appworld` | 日志标签 |
| `--data`, `--out` | 必填 | 同旧 |
| `--max-len` | 8192 | 事件全文 token 上限（3.5） |
| `--tok-budget` | 16384 | 物理块预算（决定 7；冒烟后可能改） |
| `--eval-tok-budget` | 0 = 2 × tok-budget | 评估物理块预算 |
| `--events-per-mb` | 4 | 逻辑小批事件数 |
| `--accum` | 2 | 累积的逻辑小批数 |
| `--lr` | None | 同旧，走 `lora_util.resolve_lr` |
| `--epochs` | 1 | |
| `--eval-per-epoch` | 4 | 每 epoch 评估次数 |
| `--smoke` | off | 40 个训练事件 / 16 个评估事件 / 1 epoch；取法是按事件全文 token 数升序取前 N 个（train 与 val 同规则） |
| `--max-events` | 0 | 调试限事件数；单独给的时候 `random.Random(SEED)` 打乱后取前 N 个（照 ctool）；和 `--smoke` 同时给的时候 N 覆盖 40 / 16，取法仍是升序 |
| `--log-every` | 50 | 每几次更新写一条 `step` |
| `--mem-probe` | off | 训练前踩最坏块量显存（第 10 节） |
| `--device` | cuda | |
| `--grad-ckpt`, `--readonly-env`, `--force` | 同旧 | |
| `--attn-impl` | `sdpa` | 注意力实现路径，这一轮只有 `sdpa`（第 4 节） |
| `--align-only`, `--align-tol` | off, 2e-5 | 第 9 节（fp32 逐行 ce 的最大绝对差） |
| `--align-events` | 6 | 对齐检查抽的事件数 |
| `lora_util.add_args(ap)` | | `--lora` 一族 |

`launch_probe.py` 第 80 到 89 行发射时拼的是 `[py, script, --data, --out, --env] + base_args (+ --smoke)`，所以：

- `run.py` 的 `CELLS`：`"cgen": (PY["cprobe"], ".../train_causal_share.py", ["--mode", "cgen"])`，`"cparam": (..., ["--mode", "cparam"])`；`CELL_ORDER` 不变。
- `run.py` 的 `TASKS`：`train-cgen` / `train-cparam` 改指新脚本并带 `--mode`；新增 `train-cgen-rows` / `train-cparam-rows` 指向旧脚本，字段照现有 `train-cgen` 条目逐项给全（`desc, stage="train", py="cprobe", script, args, gpu=True, notes` 等，`cmd_list` / `cmd_show` 直接下标取 `desc` 与 `stage`，缺一个就 KeyError 而 selfcheck 查不出），notes 写「逐行参照实现，只用于对齐检查与对照；产物不进矩阵，run_id 不许用现役批次前缀」。
- `EVAL_CELLS` 不变。`python3 run.py selfcheck` 通过；另外 `python3 -c "import ops.launch_probe"` 必须成功（`run.py` 第 1045 到 1138 行的 `cmd_selfcheck` 只遍历 `TASKS`、`RECIPES`、`EVAL_CELLS` 和 `configs/`，不查 `CELLS` 本体；`CELLS` 的消费方是 `ops/launch_probe.py` 第 80 行，`extending.md` 第 6 到 13 行）。
- `MAP.md` 第 88 行那张表的改动全部放工单 04（三张工单同时改同一张表会合并冲突）：cgen、cparam 两行的程序列改成新脚本，关键设定列写新口径；新增一行 `(参照)` 给两个旧脚本；新增一行 `(共用)` 给 `share_data.py`；ctool 行补新口径。
- 批次前缀（`extending.md` 第 165 行：一个训练批次只跑一档底座加一种训法，两者写进批次前缀）：新口径的批次前缀是 `ks828` 加档位训法段，如 `ks828b06`、`ks828l17`，run_id `ks828b06_gptoss_cgen`；冒烟落 `pipeline/runs/smoke/<run_id>_smoke`（决定 10）。np821 前缀不许再用于新口径的 run。

## 9 对齐检查（内置，照 ctool 的做法）

训练开始前（以及 `--align-only`），并且在 `lora_util.wrap` 之前（照 ctool 第 369 到 372 行的顺序；否则 LoRA dropout 0.05 让两条路各自随机）、`model.eval()` 状态下：`random.Random(SEED)` 从 val 事件里抽 `--align-events` 个（只抽 `len(full_ids) ≤ 2048` 的事件，控制耗时），在 fp32 下（autocast 关；掩码 fp32；cuda 上再 `torch.set_float32_matmul_precision("highest")`、`torch.backends.cuda.matmul.allow_tf32 = False`、`torch.backends.cudnn.allow_tf32 = False`，照 ctool 第 208 行，检查完恢复）：

- 进料：把抽中事件的全部原始 jsonl 行按 `(event, sent_idx)` 升序写进一个 `tempfile` 临时 jsonl，同一个临时路径同时喂给 `share_data.load_events`（`limit=0`）和旧脚本的 `CallDS` / `ParamDS`（`limit=0`——旧脚本的 `limit` 是对行打乱后截断，不是选事件）。`--readonly-env` 打开时参照路径传的 `ro` 是一个同 `set`、计数清零、`labels` 为空的副本（`CallDS` 会往 `ro` 里累加 `labels / dropped / kept`，第 135 到 142 行；传训练器正在用的那个会把 `READONLY.json` 的审计翻倍）。参照路径只读这个临时文件，不对全量 val 构造 `CallDS`。
- 新路径：第 4 节的拼接前向，得到每行 ce。
- 参照路径：import 旧脚本的 `collate`、`inst_ce`，把 `CallDS` / `ParamDS` 的行按旧方式（每行单独 `text + TAIL` 加目标串，`max_len` 传同一个值）过同一个模型，得到每行 ce。参照路径不套 `sdpa_kernel([EFFICIENT_ATTENTION])`，用默认内核选择；只有新路径（形态 A，永远带 4D 掩码）套。原因（GPU 七步验证第 6 步的报错原文 `both fused kernels require query, key and value to have the same num_heads. Query [1,16,463,128], Key [1,8,463,128]`）：凡是没有掩码的 sdpa 调用，HF 会跳过建掩码并开 `enable_gqa=True`（K/V 保持 8 头），mem-efficient 不支持 GQA，强制 EFFICIENT 下就是 `No available kernel`；新路径带掩码时 HF 先 `repeat_kv` 到 16 头，不受影响。旧 `inst_ce` 对整批全部位置算全词表 logits（fp32 下 行数 × L × 151,936 × 4 字节，一个 64 行 2048 token 的事件约 82 GB），所以参照路径按旧训练器的 `--bs 4` 每 4 行一批过；第一道门禁里的基线「单行不补齐对整批补齐」也按 4 行一批定义。
- 配对按位置：旧脚本的行元组里没有 `event` / `sent_idx`（`train_causal_callgen.py` 第 167 到 168 行、`train_causal_param.py` 第 137 到 138 行），所以两条断言：`len(ds.rows) == 新路径总行数`；逐位 `ds.rows[i][0] == 新路径第 i 行的 text`（元组第 0 位是 `text`）。另外两侧的丢弃计数相等：`CallDS.dropped` 对新路径的 `dropped_rows_tgt`；`ParamDS` 的丢弃与 mismatch 对 `dropped_rows_tgt` / `assembly_mismatch`。任一条不过就 `sys.exit(2)`，不匹配的下标写进 `ALIGN_CHECK.json`。
- 第一道（判定）：fp32 下逐行 `|ce_new − ce_ref|` 的最大值 ≤ `--align-tol`（默认 2e-5），逐目标 token 的最大差 ≤ 3e-4；同一次运行再算一个基线——参照路径「单行不补齐」对「4 行一批右补齐」的逐行差——新路径的差超过 `max(3 × 基线, 1e-6)` 就在 `ALIGN_CHECK.json` 里打 `baseline_warn: true` 并在 `start` 事件告警（只告警不判定：GPU 上关了 TF32 之后基线可能是 0 或 1e-7 量级，3 × 0 = 0 会把任何非零差判死）。依据：`design-attention.md` 的 CPU 验证，5 个事件 34 行 505 个目标 token，形态 A 对旧训练器的逐行最大差 2.15e-6（相对 8.4e-7）、逐 token 2.77e-5，基线差同为 2.15e-6；42 行 L 2,145 的大事件逐行 1.19e-6、逐 token 1.43e-5、基线 5.96e-7。GPU 七步验证第 6 步（H100，mem-efficient，同一批 34 行 505 token，fp32 关 TF32）：逐行最大差 4.41e-6（均值 1.66e-6）、逐 token 3.05e-5，基线逐行 5.01e-6、逐 token 6.91e-5；bf16 逐行均值 9.31e-3、最大 3.07e-2。门槛定成逐行 2e-5、逐 token 3e-4 的理由（决定 18）：GPU 逐行噪声是 CPU 的 2 倍，正式检查抽 6 个事件约 380 行 7,000 token 比验证多 10 倍，最大值随样本数涨（CPU 34 行到 151 行时 2.15e-6 涨到 2.62e-6），按 4.41e-6 × 1.3 估约 6e-6，1e-5 只剩 1.7 倍余量会误拦开训；2e-5 留 3 倍，离掩码错位那种真错的 1e-2 仍差 500 倍；逐 token 的 GPU 基线 6.91e-5 已经贴近 1e-4，7,000 个 token 的最大值大概率越线，3e-4 离真错 1e-2 差 30 倍。基线偏大的原因（按 `gpu_result.json` 的 `kernel_eligibility` 排除推断，不是实测：flash 不接 fp32、efficient 不接无掩码的 GQA、cudnn 不接 fp32）：fp32 下参照路径的「单行」批没有掩码，只剩 math 内核可走，和「整批」的 mem-efficient 不是同一内核，所以基线只当告警，把关靠绝对线。
- 第二道（只报告并告警，只在 cuda 设备上做；CPU 上旧脚本的 autocast 本来就不开，字段写 null）：同一批行用 bf16 autocast 再跑一遍，逐行平均绝对差 > 2e-2 或最大 > 1e-1 就在 `start` 事件里打 `align_bf16_warn: true`。依据：CPU bf16 下形态 A 对旧训练器逐行最大 3.6e-2、平均 8.9e-3，基线（旧训练器补齐对不补齐）3.0e-2 / 5.3e-3，同量级；这一道只能抓整段错位。
- 结果写 `<out>/ALIGN_CHECK.json`，键名沿用 ctool 那份的大写 `PASS`（驱动器的 smoke 门禁读的是 `PASS`）：`PASS, n_events, n_rows, n_tgt_tokens, max_abs_diff, max_tok_diff, baseline_max_abs_diff, tol, bf16_mean_abs_diff, bf16_max_abs_diff, attn_impl, mismatch_idx, baseline_warn`；不通过 `sys.exit(2)`，`start` 事件带 `align_pass, align_maxdiff, align_bf16_warn`。
- ctool 的 `--align-tol`（代码默认 1e-4，`train_causal_tool.py` 第 76 行；np821 排卡表传 3e-4，`ops/np821b06_placement.json` 第 9 到 10 行）验的是「整段一次前向对逐 token 增量前向」的末位隐状态与分类头 logits 的 fp32 绝对差，不比较 loss，所以这里不沿用那个数。

## 10 冒烟（主会话走 gpu-run，工单不做）

两类跑法分开：

- 冒烟档：`launch_probe` 的 smoke 档自动追加 `--smoke`（`ops/launch_probe.py` 第 88 到 89 行），run_id `ks828b06_gptoss_cgen_smoke`，只验「能跑、能存、日志齐、对齐检查过」。
- 速度与显存档：不带 `--smoke`，像 `plans/2026-08-28-plan.md` 第 9.1 节的六个 bslen 冒烟那样手发（走 gpu-run，登记规矩照冒烟），产物 `pipeline/runs/smoke/ks828b06_gptoss_cgen_speed`。参数：`--max-events 450`（随机取，约 20,000 行，盖住 19,200 行那个对照点）、`--log-every 3`（每 3 次更新 24 个事件约 1,100 行一条 step，三个对照点都有记录）、`--eval-per-epoch 1`（epoch 中间不评估，`train_s` 照样扣评估时间）、`--mem-probe`，tokyo108 H100。对照第 1 节的六个数：`step` 事件的 `rows` 与 `train_s` 都是累计值，任意跨度的速度 = Δrows ÷ Δtrain_s；`ips` 在 1,600 / 9,600 / 19,200 行处取夹住该行数的两条记录线性插值出 `train_s`，再算 rows ÷ train_s；`ips_win` 在 0 到 1,600 / 8,000 到 9,600 / 17,600 到 19,200 三个跨度上，两端各用夹住它的两条记录插值出 `train_s`，再算 Δrows ÷ Δtrain_s（`--log-every 3` 的记录约 1,085 行一条，盖不住 1,600 行的跨度，所以要插值）。不按更新次数比（tokyo108 的爬升段，第 12.10 节）。`--tok-budget` 取 16384 与 24576 各跑一次（GPU 七步验证：形态 A 每 token 约 2.72 MB，16,384 的块约 50 GiB，32,768 约 92 GiB 装不下 H100 的 93.10 GiB，`design-attention.md` 第七节）；`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 作为开关一起量。
- 最坏块（`stage-commands.md` 第 244 行记过的坑：随机样本踩不到最长序列，峰值由块内最长序列决定）：`--mem-probe` 打开时训练器先把 train 全集加载完（丢弃规则之后、`--max-events` 抽样之前），取两块：拼接序列最长的那个事件独自成块；「最满块」= 在全集里 B 取 2 到 `events_per_mb`，对每个 B 取拼接序列最长的 B 个事件里 `B × L_pad ≤ tok_budget` 成立的最长组合（按 `packed_len` 降序扫），几个 B 里取 `B × L_pad` 最大的那一个（装块只在 4 个事件的逻辑小批内做，块里永远不超过 `events_per_mb` 个事件）。优化器在探针之前建好；每块做一次前向加反向，然后把各 param_group 的 lr 临时置 0 做一次 `opt.step()`（AdamW 的状态就此分配、参数不动：fp32 参数 × 2 份状态，0.6B 是 4.8 GB、1.7B 全参 13.6 GB，比 10% 的裁决线还大），记 `peak_mem_gb`，再 `opt.state.clear()`、恢复 lr、`zero_grad`，写两条 `mem_probe` 事件（字段加 `B, L_pad, with_optimizer_state: true`），然后再抽样开训。
- ctool 也冒烟一次（`launch_probe` 的 smoke 档，run_id `ks828b06_gptoss_ctool_smoke`，H100）：ctool 的 `collate` 撤掉截断、上限翻到 8192 而 `--bs` 仍是 4 个事件右 pad 到批内最长，单批显存最多翻倍（`stage-commands.md` 第 238 行实测：0.6B 全参不带 gc、4096 × bs 4 时 ctool 峰值 60.2 GiB，翻倍就超过 H100 的 93.6 GiB）。退路按顺序试：H100 上 `--bs 4 --accum 2` 爆显存或峰值超过 84 GiB（余量不足 10%）→ 默认值改 `--bs 2 --accum 4`（仍是 8 个事件一次更新，草稿 2.2 锁的是更新单位不是 bs）→ 再不行加 `--grad-ckpt` 作为排卡表的 extra（不改默认值）。裁决记进工单 04 的 Comment 和 TIMELINE（决定 15）。
- 裁决：最坏块的 `peak_mem_gb`（含优化器状态）对 H100 的 95,830 MiB 余量不足 10% 就把 `--max-len` 默认改 6144（重跑一次最坏块确认），ctool 的默认值跟着一起退（三个格同一个上限，训练事件集才不分叉）。冒烟的裁决（`--max-len`、`--tok-budget`、ctool 的 `--bs/--accum` 定值）出来之后才发工单 04，`invariants.md` 写的是定值。

## 11 ctool 的改动（`train_causal_tool.py` 与 `eval_tool.py`）

1. 丢弃规则：`load_events` 之后（或在其中）对每个事件算 `len(tok(full, add_special_tokens=False))`，超过 `max_len` 的事件整条丢弃，计数 `dropped_events`（train / val 各一个，进 `start` 事件）。`collate` 与 `align_check` 里的 `truncation=True` 改成 `truncation=False`。`n_bound_dropped` 字段保留，含义改成「找不到读取位置的切点数」，预期恒为 0。
2. 默认值：`--max-len` 8192；`--accum` 2（`--bs` 仍是 4，一次更新 8 个事件，草稿 2.2；ctool 冒烟爆显存就按第 10 节的退路改成 `--bs 2 --accum 4`，工单 04 按 Comment 里的定值回写）；`--epochs` 仍是 3（草稿 2.5）。
3. 读取位置规则（草稿 2.6）：`read_position(offsets, full_text, cut, keep)`，只在 `offsets[:keep]` 这段真实 token 里找（`keep` 是这一行 `attention_mask` 的和；pad 的 offset 是 `(0, 0)`，起始位置 0 恒小于切点，不排除就会取到最后一个 pad——`collate` 和 `score_causal` 都是 4 个事件右 pad 一次分词，批内除最长事件外每个事件都有 pad）。对切点 b，取 j = 起始位置 < b 的最后一个真实 token（也就是覆盖字符 b−1 的 token）。`end_j ≤ b` 时读 j；`end_j > b` 并且 `full_text[b:end_j]` 全是空白时读 j；否则读 j−1。两种情况返回 −1 表示找不到：没有任何真实 token 的起始位置 < b（`eval_tool.py` 左截窗口外的切点）；要读 j−1 而 j = 0。调用方保留原有的 `if j < 0` 守卫：训练侧 `dropped += 1`（`n_bound_dropped`，`truncation=False` 加事件级丢弃之后预期恒 0），`eval_tool.py` 的 `n_oow` 计数照旧（第 128、150 到 152 行；左截保留的时候 test 集上有切点落在窗口外，`n_oow` 不为 0）。两处同一条规则：`collate` 第 140 到 158 行、`eval_tool.py` 的 `score_causal` 第 128 到 153 行（`align_check` 第 201 到 243 行只比整段前向与逐 token 增量前向的末位隐状态和 logits，没有切点循环，不改）。规则实现收在 `share_data.read_position` 一个函数里，两处 import，只删原来的 `for t in range(keep-1, -1, -1)` 循环体。

   这条规则让训练与离线评测的读取位置和「全文一次分词」的 token 边界一致；活跑时模型自己生成的 token 边界和离线全文分词可能不同（比如活跑先出 `."\n` 再出 `\n`，离线合成一个 `."\n\n`），那是分词边界的另一个坑，这一轮不解决，回写时不许写成「活跑错位已修」。
4. `step` 事件加 `lr` 字段；`loss` 改成「自上一条 step 以来全部小批损失的平均」，累加器写日志时清零。
5. `eval_tool.py` 的左截断照旧不动（评测端超长处理是挂起项）。

## 12 测试（CPU 可跑，`python3 -m unittest`）

- `tests/test_share_data.py`：(a) 公共前缀规则——真实 Qwen3-0.6B-Base 分词器（路径在 `MODELS["qwen"]`，不存在就 `skipTest`），val 集抽 20 个事件，断言每一行 `full_ids[:p] + seg_ids == old_ids + tgt_ids`；(b) 丢弃规则计数；(c) 物理块贪心装块的预算与「超预算独自成块」；(d) 掩码与 position_ids 的构造在一个手造的 3 行小事件上逐位断言，含 pad 行只看自己；(e) 读取位置规则：`Spotify."\n` + `\nWe`（读跨切点 token）、`. ` + `Next`（退回前一个 token）、手造 offsets 首个起始位置 > 0 且切点更小（返回 −1）、j = 0 且切点后非空白（返回 −1）、一批两个长度不同的事件 `padding=True` 时短事件每个切点的 j < keep 且和单条不 pad 时相同；(f) `mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/train'); import share_data"` 退出码 0（写成验收命令，不写进 unittest）。
- `tests/test_share_trainer.py`：用 `Qwen3Config(hidden_size=64, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2, intermediate_size=128, vocab_size=<真实分词器词表大小>)` 随机初始化（全参，不挂 LoRA——LoRA dropout 0.05 每次前向重新采样，梯度等式对 LoRA 不成立），`save_pretrained` 到 `tempfile` 目录并把真实 tokenizer 存进去，CPU fp32：(a) 拼接前向的每行 ce 与旧路径（import 旧脚本的 `collate` + `inst_ce`）逐行差 ≤ 1e-5；(b) 一个逻辑小批拆成 1 块和拆成 3 块的参数梯度逐元素差 ≤ 1e-6；(c) 用 `main()` 跑 `--base <那个临时目录> --smoke --max-events 6 --log-every 1 --device cpu --align-events 2`（`--base` 接受目录路径，走 `build(path=...)`），产出 `best/meta.json`、`ALIGN_CHECK.json`（`PASS` 真）、`train_log.jsonl` 的五种事件（6 个事件只有 1 次更新，`--log-every 1` 才写得出 `step`）。
- `tests/test_ctool_readpos.py`：读取位置规则与丢弃计数；训练侧 `collate` 与 `eval_tool.score_causal` 对同一个全文在上限以内的事件读出相同下标（超上限的事件训练侧已丢弃、评测侧左截，两边本来就不同，不进这条测试）。
- 现有 `tests/test_cparam_assembly.py`、`tests/test_lora_merge.py` 照常通过。

## 13 文档回写（工单 04，主会话补 TIMELINE）

- `MAP.md` 训练表（第 8 节，四处改动全在工单 04）。
- `.claude/skills/probe-pipeline/references/stage-commands.md` §3 训练命令与参数表、第 213 行的 smoke 限额行（新训练器 40 个训练事件 / 16 个评估事件）、§3.4 或对应位置补批次前缀 `ks828`、§7 接口陷阱（新脚本的 `--mode` 必填、`--tok-budget`、`train-*-rows` 是参照）。
- `references/invariants.md` 对应节：上限（冒烟定值）、丢弃规则、更新单位 8 个事件、cgen/cparam 1 个 epoch、`--tok-budget` 定值。
- `references/extending.md` §5 静默表加两行：#25 ctool 读取位置在 6.3% 的切点读的是句尾标点前一个词（草稿 4.4），症状是数字内部一致、活跑开火位置差一个 token；#26 `train-cgen-rows` / `train-cparam-rows` 走旧脚本（4096、左截、3 个 epoch），产物 `meta.json` 没有 `trainer` 字段，run_id 形状和现役相同，拿去评测会混进矩阵分不出来。§3 开头的「新格 / 新训法轴」判据加一句「换实现」的先例，§3.4 补一句新口径写进批次前缀。
- `references/gates.md`：只改写着旧口径数字（4096 / 32 个事件 / 截断）的说明文字，不加门禁编号。
- `TIMELINE.md`：主会话写（草稿第三节第 1 步，加批次前缀 `ks828`、冒烟定下的上限、ctool 的 bs/accum 定值）。

## 14 不做的事

- 不改 `summarize_matrix.py`、`check_bundle.py`、四个评测脚本的输入构造。
- 不改旧的逐行训练器（冻结为参照）。
- 不做学习率扫描、不做生成式评估、不做 `--fire-head`。
- 不动 `eval_tool.py` 的左截断。

## 15 本次会碰到的静默失败点（`extending.md` §5）

- #11（`--env` 传错只污染标签）：新脚本沿用，`launch_probe` 传的 `--env` 照旧。
- #13（跨模型串 run 与 data 只有形状 assert）：不因本次改动变化；`meta.json` 的 `data` 字段照旧写绝对路径。
- #9 / #14 / #15：格名不变、报告文件名不变，所以不触发；工单 03 的自查项之一是确认 `EVAL_CELLS` 与 `summarize_matrix.py` 一行未动。
- 新增（第 13 节回写）：#25 ctool 读取位置差一个 token；#26 rows 参照任务的产物混进矩阵；#27 `share_data` 顶层 import 旧训练脚本会让 mbert-env 下的 `eval_tool` / `eval_mbert_call` 在 import 阶段 `SystemExit`（3.3 节）。
