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
- 发射方法论（挑卡规则/分片/tmux 模板）：`.claude/skills/gpu-run/references/launch-methodology.md`
- 测速与 ETA 方法论：`.claude/skills/gpu-run/references/monitor-methodology.md`
- 探卡脚本：`.claude/skills/gpu-run/scripts/gpu_status.sh`

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

按 `references/launch-methodology.md` 的规则：bf16 ≈ 2×params GB 估显存；
48G 装得下 → 105/106/107 优先，大模型 → 108；分片当且仅当
独立条目多且单卡 >1h；分片输出必须写不同文件。
**追加本工程约束**：要装新 CUDA 轮子的任务避开 106/107（12.2 坑）；
已有的 cu128 轮子（如 mbert-env 的 torch）上 106/107 前必须先花 10 秒实测能跑。

## Phase 3 — smoke 再放量

没被明确告知"已小规模验证过"的任务，先发几十条/几步的 smoke，
日志里见到真实进度（模型加载完、第一个 batch、tqdm 行）才准发全量。
smoke 失败就修；修不好带 traceback 汇报，不许硬发。

## Phase 4 — 发射前 commit + tmux 发射 + 双登记 + 交监控入口

**执行方式**：发射环节整段派 `gpu-runner` agent 干（探卡/smoke/tmux/登记/验活
打包给它，opus 够用），不在主对话手搓——主对话负责规划与写脚本。

0. **发射前先 commit 代码**。实验记录里存的 git HEAD，只有工作树干净时才追得回
   真实跑的那版代码。脏工作树 `record.py` 会打 ⚠️ 但不拦你——追溯断链是你自己的损失。
1. 一切进 tmux（禁 bare ssh / nohup）。session 名 `new1_<task>_<host>g<gpu>`，
   日志 `<workdir>/logs/<session>.log`。命令用 python subprocess 拼，防引号地狱。
2. 发射后立即登记台账（一个任务一次 register，多分片多个 --piece）：
   ```bash
   python ops/gpu_jobs.py register --name <task> --workdir <dir> \
     --piece tokyo106:0:new1_task_t106g0:/path/to/log \
     --piece tokyo106:1:new1_task_t106g1:/path/to/log2
   ```
3. **同时记一条实验记录**（run_id 用台账同名，两边能对上）：
   ```bash
   python ops/record.py start --name <task> --track <所属方向> \
     --model <模型> --seed <种子> --host <host> --gpu <idx> \
     --param <k=v> --data <原始数据落盘路径> --cmd "<实际执行的命令>" \
     --note "这次想验证什么"
   ```
   `--track` 要和 `TIMELINE.md` 里的方向对得上；`--data` 写 NFS 上的真实路径，
   原始数据不进 git，全靠这个字段和 run_id 目录名追溯。
4. 验证存活：tail 每个日志确认真实进度出现，才算发射成功。
5. **必须把这两条命令原样交给用户**（这是用户亲自监控的入口）：
   ```bash
   python /home/y-guo/reproduce/new1/ops/gpu_jobs.py           # 看一眼
   python /home/y-guo/reproduce/new1/ops/gpu_jobs.py watch     # 30s 自动刷新
   ```
   表里直接有每个分片的进度、实测速率、tqdm ETA、tmux 存活状态。

## Phase 5 — 巡检（Claude 侧）

用户能自助看，但 Claude 不当甩手掌柜：长任务定时巡检**派只读的
`job-monitor` agent**（`gpu_jobs.py json` 给它读；起服务期 10 分钟粒度，
跑批期 15-30 分钟），ETA 要靠两个时间点的 Δitems/Δt
交叉核对 tqdm 自报值（方法论见 `references/monitor-methodology.md`）。
发现 EXIT 且进度不满 → 读日志定位，能修则修后重发该分片。

## Phase 6a — 正常收尾（强制五连）

1. **汇报**：结果文件在哪、条数对不对（分片合并后 count == total）、
   关键数字一句话。
2. **记数字**：
   ```bash
   python ops/record.py finish <run_id> --metric <k=v> [--metric ...] \
     --data <最终数据路径> --conclusion "一句话结论"
   ```
   数字自动进 `RESULTS.md`。**如果这个结论动了 `WORKPLAN.md` 里任何一条判断，
   同时往 `TIMELINE.md` 最上面追加一条方向决策**（写清决定了什么、被哪个 run_id
   触发、作废了什么）。纯进度推进不用记 TIMELINE，那是 `plans/` worklog 的活。
3. **释放**：杀掉所有残留 tmux session / vLLM 服务，
   `nvidia-smi` 确认显存归零。批量任务结束不许占卡过夜。
4. **销号**：`python ops/gpu_jobs.py finish <task>`。
5. **提交**：`git add` 本次改的代码 + `ops/runs.jsonl` + `RESULTS.md`
   (+ `TIMELINE.md` 如有)，commit message 里带上 run_id。

## Phase 6b — 中途中断（用户喊停或巡检判死）

1. 逐分片 `ssh <host> tmux kill-session -t <session>`。
2. `nvidia-smi` 确认显存已释放。
3. 汇报已完成到哪、日志和半成品输出在哪、可否断点续跑。
4. `finish <task>` 销号，台账 history 里留档。

## 铁律

- 台账只通过 `gpu_jobs.py register/finish` 读写，不手改 jobs.json。
- 占用状态永远 Phase 1 现场实探，档案文件只记慢变量。
- 一个任务一个 name，重名先 finish 旧的。
- 统计数字只通过 `record.py start/finish` 写；`RESULTS.md` 是渲染产物，
  手改会在下次 render 时被覆盖。`runs.jsonl` 只增不改。
- run_id 是贯穿主键：原始数据目录名 / tmux session / 台账 name / commit
  message 四处一致，缺一处就断一条追溯路径。
