# 06 `--mem-probe` 改成真实最坏情况（优化器状态已建、最满块连做两次反向）

Status: ready-for-agent
Blocked by: 05
Spec: `.scratch/kvshare-train/spec.md` 第 10 节「最坏块」那一条（本工单同步改它的措辞）；改动只在 `pipeline/train/train_causal_share.py`、`tests/test_share_trainer.py` 与 spec 第 10 节那一段。

## 背景（实测）

ks828b06 速度档（H100，`--tok-budget 16384`）：`mem_probe` 最满块（B=2，L_pad 8192，含 lr=0 的 `opt.step`）报 51.11 GB，训练中 `step` 事件的 `peak_mem_gb` 最大 60.59 GB；`--tok-budget 24576` 时探针 75.05 对训练 80.91。差额的机理（8-28-assistant-2 判读）：探针的峰值取的是「反向期间：权重 + 激活 + 正在生成的梯度」和「step 之后：权重 + 梯度 + 状态」两个时刻的大者，而训练的真峰在第二个逻辑小批的反向期间，此时优化器状态（0.6B 全参 4.8 GB）和第一个小批留下的梯度（2.4 GB）都还在；`accum=2` 时两个最满块同组是真实会出现的最坏情况。

## 要做的

1. `run_mem_probe`（`train_causal_share.py` 第 220 到 245 行附近）改成：先 `opt.zero_grad(set_to_none=False)` 并做一次 lr 置 0 的 `opt.step()` 把优化器状态建好（`torch.cuda.reset_peak_memory_stats()` 在这之后）；然后对最满块连做两次「前向 + 反向」，中间不 `zero_grad`（梯度累积）；第二次反向之后读 `max_memory_allocated` 作为 `fullest_block` 的 `peak_mem_gb`；最长事件那一块同样在状态已建、梯度未清的条件下做一次前向加反向再读峰值；最后 `opt.state.clear()`、恢复 lr、`opt.zero_grad(set_to_none=True)`。`mem_probe` 事件字段加 `n_backward`（1 或 2）与 `optimizer_state_prebuilt: true`。
2. spec 第 10 节「最坏块」那一条的做法改成上面这段（只改那一条）。
3. `tests/test_share_trainer.py` 加一个小模型 CPU 用例：调用 `run_mem_probe` 后 `opt.state` 为空、各 param_group 的 lr 恢复原值、所有参数的 `.grad` 为 None，并且返回/记录的两条 `mem_probe` 事件字段齐全（CPU 上 `peak_mem_gb` 允许为 0）。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data` 通过。
- `grep -n "n_backward" pipeline/train/train_causal_share.py` 命中。
- 不改 `share_data.py`、不改注册表、不改旧脚本。
- 真正的验收判据是实测（主会话在 H100 上做，工单不做）：改后 `--mem-probe` 报的 `fullest_block.peak_mem_gb` ≥ 同预算速度档整程 `step` 峰值——`--tok-budget 16384` 对 60.59 GB、`24576` 对 80.91 GB。上面「状态先建好、连做两次反向」是按机理推的改法，不是验收：按机理算探针少算 4.8 + 2.4 = 7.2 GB，而实测差是 9.5（b16k）和 5.9（b24k），两个都对不上 7.2，说明还有别的量；改完探针数仍然低于训练峰值的话，把探针改成「直接按训练循环的写法连做两个逻辑小批（含 accum=2 的真实更新）」再量。
