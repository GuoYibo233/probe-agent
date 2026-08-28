# 03 训练器 `pipeline/train/train_causal_share.py` 与注册表

Status: ready-for-agent
Blocked by: 01
Spec: `.scratch/kvshare-train/spec.md` 第 4 到 9 节、第 12 节；注意力实现照 `.scratch/kvshare-train/design-attention.md`（已落地），拼接序列与掩码的构造有一份 CPU 验证过的参考实现 `.scratch/kvshare-train/verify/packed_common.py`（只当参考读，代码要按工单 01 的 `share_data` 接口重写，不许直接 import 那个文件）

## 要做的

1. 新建 `pipeline/train/train_causal_share.py`。数据走工单 01 的 `share_data`；tokenizer 与模型走旧脚本 `train_causal_callgen.build(dev, base, attn_impl=...)`（给 `build()` 加一个关键字参数 `attn_impl=None`，None 保持旧行为，这是旧脚本唯一允许的改动）。前向按 spec 第 4 节与 `design-attention.md` 的推荐形态（掩码 dtype、position_ids、内核）。损失与更新按第 5 节，评估与 `best/` 按第 6 节，日志与心跳按第 7 节（`step` 事件的 `ips` 是本 epoch 累计行数 ÷ 已用秒数，`ips_win` 是窗口值，`rows` 是累计行数；`heartbeat.emit` 三处照旧脚本第 71、481、517、554 行），命令行按第 8 节，对齐检查按第 9 节。`--lora` / `--grad-ckpt` / `--readonly-env` / `--force` / `READONLY.json` 的接线照旧脚本。
2. `run.py`：`CELLS["cgen"]`、`CELLS["cparam"]` 改指新脚本并带 `["--mode", "cgen"]` / `["--mode", "cparam"]`；`TASKS` 的 `train-cgen` / `train-cparam` 同步改；新增 `train-cgen-rows` / `train-cparam-rows` 指旧脚本（`stage="train", py="cprobe", gpu=True`，notes 写「逐行参照实现，只用于对齐检查与对照；产物不进矩阵，run_id 不许用现役批次前缀」）。
   命令行按 spec 第 8 节的表，含 `--log-every`、`--mem-probe`、`--max-events` 与 `--smoke` 的取法（`--smoke` 走 `share_data.load_events(order="shortest")`，单独 `--max-events` 走 `order="random"`）；`--mem-probe` 按 spec 第 10 节：先加载 train 全集（limit=0），用 `share_data.worst_blocks` 取两块各做一次前向加反向、写两条 `mem_probe` 事件、梯度清零，再按 limit 抽样开训。`step` 事件的 `train_s` 在评估期间暂停计时。`python3 run.py selfcheck` 通过，`python3 -c "import ops.launch_probe"` 通过，`python3 run.py show train-cgen` 打印的命令含 `train_causal_share.py --mode cgen`。
3. `MAP.md` 不动（cgen、cparam 两行和 `(参照)` 一行由工单 04 写；你在报告里给出文案：「一个事件一次前向共享前缀；上限 8192 超长事件整条丢弃；8 个事件一次更新；1 个 epoch 每四分之一评一次 val_ce；`--tok-budget` 控显存」）。
4. 测试 `tests/test_share_trainer.py`，spec 12 的三条 (a)(b)(c)。小模型用 `transformers.Qwen3Config` 随机初始化，`vocab_size` 取真实分词器的词表大小（分词器不存在就 skip）；测试产物写 `tempfile` 目录（小模型只有几 MB）。

## 验收

- `python3 -m unittest tests.test_share_trainer tests.test_share_data tests.test_cparam_assembly tests.test_lora_merge` 通过（cprobe-env 下也过）。
- `grep -n "heartbeat.emit" pipeline/train/train_causal_share.py` 命中三处（起步、每条 step、收尾 `status="done"`）。
- `cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen --data pipeline/data/nyapass_aw_v1/gptoss --out pipeline/runs/smoke/share_cpu_cgen_smoke --device cpu --smoke --max-events 6 --align-events 2 --base qwen --force` 在 CPU 上跑通（产物目录是 NFS 软链下的既有冒烟落点，0.6B fp32 的 `best/` 约 2.4 GB 不许写 /tmp 或 home；0.6B fp32 在 CPU 上 6 个短事件可以接受几分钟；`--smoke` 按全文 token 数升序取前 N 个，所以 6 个事件都是最短的），产出 `ALIGN_CHECK.json`（`pass: true`，`max_abs_diff ≤ 1e-4`）、`train_log.jsonl` 五种事件、`best/meta.json`（含 `trainer: "share"`、`call_sep`、`max_len`）。cparam 同样跑一次，`--out pipeline/runs/smoke/share_cpu_cparam_smoke`。
- 旧脚本除 `build()` 的关键字参数外零改动（`git diff --stat` 里 `train_causal_callgen.py` 只有那一处，`train_causal_param.py` 无改动）。
- `EVAL_CELLS`、`summarize_matrix.py`、四个评测脚本无改动。
- GPU 上的对齐检查与冒烟不在本工单：把准备好的命令写进报告即可。
