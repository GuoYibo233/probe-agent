# 10 显存探针三种挑块方式：`--mem-probe-pick {tokens,cost,loop}`（默认 `cost`），探针前后恢复随机数状态

Status: resolved
Blocked by: （无）
Spec: `.scratch/kvshare-train/spec.md` 16.5（做法与字段）、16.9（测试）、16.10 #31 #32；机理依据 `.scratch/kvshare-train/design-attention.md` 8.6 节。改动只在 `pipeline/train/train_causal_share.py`（`run_mem_probe` 第 234 到 302 行、训练循环第 760 到 764 行、参数在 `--mem-probe` 之后加）、`pipeline/train/share_data.py`（加 `epoch_minibatches`）、`tests/test_share_trainer.py`、`tests/test_share_data.py`。不改 `run.py`、不改文档。

## 背景

终验里改后的探针（工单 06）最满块 54.38 GB 对整程 step 峰值 58.47 GB 仍低 4.1 GB。8-28-assistant-2 在 design-attention 8.6 节复现块形状后的判读：峰值窗口的块同时是「损失位最多」的块（B=3、L_pad 5,344、4,736 个损失位），每个损失位在输出层多占约 1.8 MB（四份 151,936 维向量），探针只按 token 数挑块会漏这一项；按 2.7 MB × token 加 1.8 MB × 损失位校正探针 54.38 + 1.83 × 2.752 − 2.7 × 0.352 = 58.5 GB，与实测 58.47 差 0.1 GB。gyb 要把退路做成开关。

## 要做的

1. `share_data.py` 加 `epoch_minibatches(events, seed, ep, events_per_mb) -> list[list[event]]`：`list(events)` 复制后 `random.Random(seed + ep).shuffle`，再按 `events_per_mb` 切——就是训练循环第 761 到 764 行现在做的事。训练循环改调它（唯一真源）。
2. `train_causal_share.py` 加 `--mem-probe-pick`（`choices=["tokens", "cost", "loop"]`，默认 `cost`），`run_mem_probe` 重构成一个骨架加三种挑块跑法：
   - 骨架（现有代码）：建优化器状态（`.grad` 赋零张量 → `zero_grad(set_to_none=False)` → lr 置 0 的 `opt.step()`）→ 对每个待测块 `reset_peak_memory_stats` → 跑 → 读 `max_memory_allocated` → 写 `mem_probe` 事件 → 最后 `opt.state.clear()`、恢复 lr、`opt.zero_grad(set_to_none=True)`。
   - `tokens`：现状——全集里 `worst_blocks` 挑最满块（两次前向反向）与最长事件（一次），`kind` 仍是 `fullest_block / longest_event`。全集只在这个模式下加载：`main()` 第 750 到 754 行现在无条件装 train 全集（186,479 行逐行分词，约 8 分钟），改成只在 `args.mem_probe_pick == "tokens"` 时装，并且 `--max-events 0` 且不带 `--smoke` 时 `tr_events` 本来就是全集、直接复用不再装；`run_mem_probe` 签名改成同时收 `tr_events` 与 `full_events`（后者只在 `tokens` 下非 None）。
   - `cost`：用本次 run 的 `tr_events`（`--max-events` 抽样之后的那份，不是全集），`epoch_minibatches(tr_events, SEED, 0, events_per_mb)` 后每个逻辑小批过 `chunk_by_budget(mb, tok_budget)`，枚举全部物理块；挑三块：(i) token 数（`len(block) × _l_pad(block)`）最大的，并列时取损失位多的；(ii) 损失位数最大的（损失位数 = 块内全部行的 `seg_lab` 里 `!= -100` 的个数之和，行元组第 4 位），并列时取 token 多的；(iii) `n_tokens / max_n_tokens + n_loss_pos / max_n_loss_pos` 最大的（两个分母是全部块里的最大值）。重复的块只跑一次（事件照写、加 `same_as: <另一块的 kind>`），各在「状态已建、连做两次前向加反向、中间不清梯度」的条件下量峰值，`kind` 是 `max_tokens_block / max_losspos_block / max_cost_block`。依据在 `design-attention.md` 9.2（并列的 token 最多块有 8 个、只挑两块会低 3.6 GB）。
   - `loop`：找到含损失位最多那一块的更新组（`epoch_minibatches` 之后按 `accum` 个逻辑小批一组，`n_g` 与训练循环同规则：末组不足 `accum` 时按实际个数），照训练循环原样跑一次更新：每个逻辑小批 `W = Σ row[5]`，`chunk_by_budget` 后 `backward_logical_minibatch(model, blocks, W, n_g, dev, mask_dtype, amp)`；组跑完 `clip_grad_norm_(model.parameters(), 1.0)`、lr 置 0 的 `opt.step()`（AdamW 在 lr=0 时参数不变），读峰值，然后骨架的清理。调度器 `sch` 不动。`kind` 是 `loop_group`，另加 `n_blocks, n_events`。
   - 探针整段前后保存并恢复随机数状态：`random.getstate()/setstate()`、`torch.get_rng_state()/set_rng_state()`、cuda 上 `torch.cuda.get_rng_state()/set_rng_state()`。目的：带探针与不带探针的 run 训练部分逐位相同（LoRA dropout 的随机流不被探针消耗）。
   - 事件字段统一：`pick, kind, B, L_pad, n_tokens (= B × L_pad), n_rows, n_loss_pos, peak_mem_gb, n_backward, with_optimizer_state, optimizer_state_prebuilt`（`loop_group`：`B / L_pad / n_tokens` 写组里最大那块的，`n_rows / n_loss_pos` 整组求和，`n_backward` 是组内物理块总数，另加 `n_blocks, n_events, max_block_n_loss_pos`）；现有字段名 `n_events / packed_len_max` 保留不删。所有块跑完写一条 `mem_probe_summary`：`pick, worst_gb (= 各块 peak 的最大值), worst_kind, scope（tokens 写 "full"，cost / loop 写 "run"）, n_events_considered（挑块时枚举的事件数）`。`start` 事件加 `mem_probe_pick`。
   - 顺带（8-28-assistant-2 第九节的建议）：`step` 事件加 `grad_norm`，值是这次更新 `clip_grad_norm_` 的返回值（`float`，裁剪前的总范数）。
   - 新写的手造行元组一律写 7 位，第 6 位填 `dict(tgt="", tool=None)`（工单 08 并行把行元组从 6 位改成 7 位，spec 16.10 #30；文本上不冲突但合并后 6 位元组会让 `pack_event` 报 `ValueError`）。
   - 参数不变性：三种模式跑完，所有可训练参数逐位等于探针前（`loop` 模式靠 lr=0；测试里断言）。
   - 读峰值的那一句抽成模块级函数 `_peak_gb(dev)`（cuda 上 `torch.cuda.max_memory_allocated() / 1e9`，其他设备 0.0），探针的每块与 step 日志（第 813 到 817 行）都调它——测试靠 monkeypatch 它来给假峰值。
   - 参数 `--mem-probe-pick` 紧跟在 `--mem-probe` 之后（工单 08、09 也在参数段加参数，锚点不同）；`start_kw` 里本工单加 `mem_probe_pick` 一个键，放在 `mem_probe` 那个键之后；合并冲突主会话收账时解。
   - 现有测试要跟着改：`tests/test_share_trainer.py` 第 548 行与第 577 行附近两个探针用例构造的是 `argparse.Namespace(tok_budget=100000, events_per_mb=4)`，`run_mem_probe` 读 `args.mem_probe_pick / args.accum` 会 `AttributeError`，给这两个 Namespace 补 `mem_probe_pick="tokens", accum=2`（保持它们测的是旧路径）。
3. 测试（spec 16.9 第四条）放新文件 `tests/test_mem_probe_pick.py`（不往现有文件末尾加用例——工单 08、09 并行；小模型与事件的构造 import 现有测试的辅助函数），另加 `tests/test_share_data.py` 末尾一个 `epoch_minibatches` 用例（工单 08 只改那个文件里手造元组的位数，不在末尾加东西）：
   - `tests/test_share_data.py`：`epoch_minibatches` 与「手抄训练循环旧写法」切出来的小批逐个相同（事件名序列相等）。
   - `tests/test_mem_probe_pick.py`：(a) 手造 6 个小事件（一个行少但每行目标长——损失位最多；一个行多前缀长——token 最多；两个 token 数并列但损失位不同——并列规则要挑损失位多的），`cost` 挑到的 `max_tokens_block` 是并列里损失位多的那块、`max_losspos_block` 与它不同、`max_cost_block` 按公式算出来的那块，`kind` 各对；(b) 三种模式各跑一次 `run_mem_probe`：`opt.state` 为空、每个 param_group 的 lr 恢复、所有 `.grad` 为 None、参数逐位不变（`loop` 模式也是）、都写了 `mem_probe_summary`；`worst_gb` 的断言用 `unittest.mock.patch` 把 `train_causal_share._peak_gb` 换成每次调用返回递增值（1.0、2.0、…）的假函数，断言 `worst_gb` 等于各块 `peak_mem_gb` 的最大值且 `worst_kind` 对（CPU 上真值恒 0.0，不 patch 就是 0 == 0，没有区分度）；(c) 小模型 `main()` 带 `--mem-probe --mem-probe-pick cost --device cpu --lora` 与不带 `--mem-probe`（同样 `--lora`）各跑一次（同 `--smoke --max-events 6 --log-every 1`），两份 `train_log.jsonl` 的 `step` 事件 `loss` 逐条相同（随机数状态恢复；小模型不挂 LoRA 时 dropout 为 0 没有区分度，`lora_util.wrap` 在 CPU 小模型上可用）。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_mem_probe_pick tests.test_share_trainer tests.test_share_data` 通过。
- `grep -n "epoch_minibatches" pipeline/train/share_data.py pipeline/train/train_causal_share.py` 两个文件都命中，训练循环里不再有自己的 `shuffle`。
- `grep -n "mem_probe_summary\|get_rng_state\|def _peak_gb" pipeline/train/train_causal_share.py` 三个都命中。
- `--mem-probe-pick tokens` 的两条事件与改前字段兼容（旧键都在）。
- 不改 `run.py`。

## Comments

- 2026-08-28 plan-8-28 收账：wave5 实现 0 轮修复过评审，分支 `ticket/2026-08-28-wave5/T10`（base `07907db`，head `e272ffd`），合并为 `12b998c`，`train_causal_share.py` 的 `start_kw` 一处冲突手解（08 的 `gen_*` 三个键与 10 的 `mem_probe_pick` 都留）。收账补丁（决定 32，spec 16.5 在工单发射后改的）由主会话在合并后直接改代码：`_mem_probe_loop` 改成对 `_pick_cost_blocks` 挑出的三块各找所在更新组、同组只跑一次、每组一条 `mem_probe`（加 `group_of`、`group_idx`）、`mem_probe_summary` 取大者（加 `worst_group_of`）；每组之间 `reset_peak_memory_stats` 与 `zero_grad(set_to_none=True)`。实现者 concern「峰值全为 0.0（CPU 真值）时 `worst_kind` 停在 None」一并修：三种模式的比较改成 `worst_kind is None or peak > worst_gb`（并列取第一块）。另两条 concern 记录不改：(c) 端到端 smoke 用例里 6 个事件太少、cost 三块落在同一块（`same_as` 链路走到，三块互不相同由 (a) 手造数据覆盖）；worktree 里到 NFS 的两个软链是实现者临时补建的。cannotVerify：`_peak_gb` 的 cuda 分支与 cost/loop 在真实 GPU 上的数值要等 16.8 的冒烟。补丁后 `tests.test_mem_probe_pick` 等四个新文件 30 个用例 OK。新测试 `tests/test_mem_probe_pick.py`。
