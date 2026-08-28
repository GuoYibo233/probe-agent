# 10 显存探针三种挑块方式：`--mem-probe-pick {tokens,cost,loop}`（默认 `cost`），探针前后恢复随机数状态

Status: ready-for-agent
Blocked by: （无）
Spec: `.scratch/kvshare-train/spec.md` 16.5（做法与字段）、16.9（测试）、16.10 #31 #32；机理依据 `.scratch/kvshare-train/design-attention.md` 8.6 节。改动只在 `pipeline/train/train_causal_share.py`（`run_mem_probe` 第 234 到 302 行、训练循环第 760 到 764 行、参数在 `--mem-probe` 之后加）、`pipeline/train/share_data.py`（加 `epoch_minibatches`）、`tests/test_share_trainer.py`、`tests/test_share_data.py`。不改 `run.py`、不改文档。

## 背景

终验里改后的探针（工单 06）最满块 54.38 GB 对整程 step 峰值 58.47 GB 仍低 4.1 GB。8-28-assistant-2 在 design-attention 8.6 节复现块形状后的判读：峰值窗口的块同时是「损失位最多」的块（B=3、L_pad 5,344、4,736 个损失位），每个损失位在输出层多占约 1.8 MB（四份 151,936 维向量），探针只按 token 数挑块会漏这一项；按 2.7 MB × token 加 1.8 MB × 损失位校正探针 54.38 + 1.83 × 2.752 − 2.7 × 0.352 = 58.5 GB，与实测 58.47 差 0.1 GB。gyb 要把退路做成开关。

## 要做的

1. `share_data.py` 加 `epoch_minibatches(events, seed, ep, events_per_mb) -> list[list[event]]`：`list(events)` 复制后 `random.Random(seed + ep).shuffle`，再按 `events_per_mb` 切——就是训练循环第 761 到 764 行现在做的事。训练循环改调它（唯一真源）。
2. `train_causal_share.py` 加 `--mem-probe-pick`（`choices=["tokens", "cost", "loop"]`，默认 `cost`），`run_mem_probe` 重构成一个骨架加三种挑块跑法：
   - 骨架（现有代码）：建优化器状态（`.grad` 赋零张量 → `zero_grad(set_to_none=False)` → lr 置 0 的 `opt.step()`）→ 对每个待测块 `reset_peak_memory_stats` → 跑 → 读 `max_memory_allocated` → 写 `mem_probe` 事件 → 最后 `opt.state.clear()`、恢复 lr、`opt.zero_grad(set_to_none=True)`。
   - `tokens`：现状——全集里 `worst_blocks` 挑最满块（两次前向反向）与最长事件（一次），`kind` 仍是 `fullest_block / longest_event`。
   - `cost`：用本次 run 的 `tr_events`（`--max-events` 抽样之后的那份，不是全集），`epoch_minibatches(tr_events, SEED, 0, events_per_mb)` 后每个逻辑小批过 `chunk_by_budget(mb, tok_budget)`，枚举全部物理块；挑 token 数（`len(block) × _l_pad(block)`）最大的一块和损失位数最大的一块（损失位数 = 块内全部行的 `seg_lab` 里 `!= -100` 的个数之和，行元组第 4 位），两块各在「状态已建、连做两次前向加反向、中间不清梯度」的条件下量峰值，`kind` 是 `max_tokens_block / max_losspos_block`；两块是同一块时只跑一次、两条事件都写同一个数并加 `same_block: true`。
   - `loop`：找到含损失位最多那一块的更新组（`epoch_minibatches` 之后按 `accum` 个逻辑小批一组，`n_g` 与训练循环同规则：末组不足 `accum` 时按实际个数），照训练循环原样跑一次更新：每个逻辑小批 `W = Σ row[5]`，`chunk_by_budget` 后 `backward_logical_minibatch(model, blocks, W, n_g, dev, mask_dtype, amp)`；组跑完 `clip_grad_norm_(model.parameters(), 1.0)`、lr 置 0 的 `opt.step()`（AdamW 在 lr=0 时参数不变），读峰值，然后骨架的清理。调度器 `sch` 不动。`kind` 是 `loop_group`，另加 `n_blocks, n_events`。
   - 探针整段前后保存并恢复随机数状态：`random.getstate()/setstate()`、`torch.get_rng_state()/set_rng_state()`、cuda 上 `torch.cuda.get_rng_state()/set_rng_state()`。目的：带探针与不带探针的 run 训练部分逐位相同（LoRA dropout 的随机流不被探针消耗）。
   - 事件字段统一：`pick, kind, B, L_pad, n_tokens (= B × L_pad), n_rows, n_loss_pos, peak_mem_gb, n_backward, with_optimizer_state, optimizer_state_prebuilt`（`loop_group` 的 `B / L_pad / n_tokens` 写组里最大那块的）；现有字段名 `n_events / packed_len_max` 保留不删（旧解析器读它们）。所有块跑完写一条 `mem_probe_summary`：`pick, worst_gb (= 各块 peak 的最大值), worst_kind`。`start` 事件加 `mem_probe_pick`。
   - 参数不变性：三种模式跑完，所有可训练参数逐位等于探针前（`loop` 模式靠 lr=0；测试里断言）。
3. 测试（spec 16.9 第四条）：
   - `tests/test_share_data.py`：`epoch_minibatches` 与「手抄训练循环旧写法」切出来的小批逐个相同（事件名序列相等）。
   - `tests/test_share_trainer.py`：(a) 手造 5 个小事件（一个行少但每行目标长——损失位最多；一个行多前缀长——token 最多），`cost` 挑到两块不同且 `kind` 各对；(b) 三种模式各跑一次 `run_mem_probe`：`opt.state` 为空、每个 param_group 的 lr 恢复、所有 `.grad` 为 None、参数逐位不变（`loop` 模式也是）、都写了 `mem_probe_summary` 且 `worst_gb` 等于各块最大值；(c) 小模型 `main()` 带 `--mem-probe --mem-probe-pick cost --device cpu` 与不带 `--mem-probe` 各跑一次（同 `--smoke --max-events 6 --log-every 1`），两份 `train_log.jsonl` 的 `step` 事件 `loss` 逐条相同（随机数状态恢复；小模型不挂 LoRA 时 dropout 为 0，这条测试要挂 `--lora` 才有区分度——`lora_util.wrap` 在 CPU 小模型上可用，测试里用 `--lora`）。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data` 通过。
- `grep -n "epoch_minibatches" pipeline/train/share_data.py pipeline/train/train_causal_share.py` 两个文件都命中，训练循环里不再有自己的 `shuffle`。
- `grep -n "mem_probe_summary\|get_rng_state" pipeline/train/train_causal_share.py` 命中。
- `--mem-probe-pick tokens` 的两条事件与改前字段兼容（旧键都在）。
- 不改 `run.py`。
