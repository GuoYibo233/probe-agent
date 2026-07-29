---
name: gpu-run
description: new1 工程内运行任何 GPU 程序的唯一入口——全生命周期一条龙：读慢变量档案 → 实探空卡 → 挑卡分片 → smoke → tmux 发射 → 登记台账 → 告诉用户自助监控命令 → 定时巡检 → 结束收尾（汇报+释放显存+销号）或中途中断。Invoke whenever Dungeon♂Master says "跑程序"、"run"、"跑实验"、"跑一下"、"发射"、"用显卡跑"、"起个任务"、"train"、"inference"、or any GPU work needs starting in new1.
version: 1.0.0
---

# gpu-run — new1 GPU 任务全生命周期

一个任务从生到死的强制流水线。每一步都有产物，跳步 = 违规。

固定路径（NFS，处处一致）：
- 慢变量档案：`/home/y-guo/reproduce/new1/ops/gpu_state.md`
- 台账 CLI：`python /home/y-guo/reproduce/new1/ops/gpu_jobs.py`
- 发射方法论（挑卡规则/分片/tmux 模板）：`~/.claude/skills/launch-gpu-job/SKILL.md`

## Phase 0 — 读档案

Read `ops/gpu_state.md`。重点：别名去重（shiga=105, saitama=108）、
tokyo106/107 只有 CUDA 12.2、tokyo108 的 H100/H200 idx 分布。

## Phase 1 — 实探空卡（永不信缓存）

```bash
python /home/y-guo/reproduce/new1/ops/gpu_jobs.py free   # ≈6 秒
```

只用 OWNERS=FREE 的卡。别人的进程（哪怕 0% util）= 禁区。
自己的残留进程 = 先判断是不是热服务，不明确就问。

## Phase 2 — 挑卡 + 分片

按 launch-gpu-job SKILL 的规则：bf16 ≈ 2×params GB 估显存；
48G 装得下 → 105/106/107 优先，大模型 → 108；分片当且仅当
独立条目多且单卡 >1h；分片输出必须写不同文件。
**追加本工程约束**：要装新 CUDA 轮子的任务避开 106/107（12.2 坑）。

## Phase 3 — smoke 再放量

没被明确告知"已小规模验证过"的任务，先发几十条/几步的 smoke，
日志里见到真实进度（模型加载完、第一个 batch、tqdm 行）才准发全量。
smoke 失败就修；修不好带 traceback 汇报，不许硬发。

## Phase 4 — tmux 发射 + 登记 + 交监控入口

1. 一切进 tmux（禁 bare ssh / nohup）。session 名 `new1_<task>_<host>g<gpu>`，
   日志 `<workdir>/logs/<session>.log`。命令用 python subprocess 拼，防引号地狱。
2. 发射后立即登记台账（一个任务一次 register，多分片多个 --piece）：
   ```bash
   python ops/gpu_jobs.py register --name <task> --workdir <dir> \
     --piece tokyo106:0:new1_task_t106g0:/path/to/log \
     --piece tokyo106:1:new1_task_t106g1:/path/to/log2
   ```
3. 验证存活：tail 每个日志确认真实进度出现，才算发射成功。
4. **必须把这两条命令原样交给用户**（这是用户亲自监控的入口）：
   ```bash
   python /home/y-guo/reproduce/new1/ops/gpu_jobs.py           # 看一眼
   python /home/y-guo/reproduce/new1/ops/gpu_jobs.py watch     # 30s 自动刷新
   ```
   表里直接有每个分片的进度、实测速率、tqdm ETA、tmux 存活状态。

## Phase 5 — 巡检（Claude 侧）

用户能自助看，但 Claude 不当甩手掌柜：长任务定时巡检
（`gpu_jobs.py json` 给 agent 读），ETA 要靠两个时间点的 Δitems/Δt
交叉核对 tqdm 自报值（方法论见 `~/.claude/skills/monitor-job/SKILL.md`）。
发现 EXIT 且进度不满 → 读日志定位，能修则修后重发该分片。

## Phase 6a — 正常收尾（强制三连）

1. **汇报**：结果文件在哪、条数对不对（分片合并后 count == total）、
   关键数字一句话。
2. **释放**：杀掉所有残留 tmux session / vLLM 服务，
   `nvidia-smi` 确认显存归零。批量任务结束不许占卡过夜。
3. **销号**：`python ops/gpu_jobs.py finish <task>`。

## Phase 6b — 中途中断（用户喊停或巡检判死）

1. 逐分片 `ssh <host> tmux kill-session -t <session>`。
2. `nvidia-smi` 确认显存已释放。
3. 汇报已完成到哪、日志和半成品输出在哪、可否断点续跑。
4. `finish <task>` 销号，台账 history 里留档。

## 铁律

- 台账只通过 `gpu_jobs.py register/finish` 读写，不手改 jobs.json。
- 占用状态永远 Phase 1 现场实探，档案文件只记慢变量。
- 一个任务一个 name，重名先 finish 旧的。
