---
name: gpu-run
description: new1 工程内运行任何 GPU 程序的唯一入口——全生命周期一条龙：读慢变量档案 → 实探空卡 → 挑卡分片 → smoke → `launch` 一条命令发射（自动三处登记）→ 告诉用户自助监控命令 → 采样器接管判定与升级 → 结束收尾（汇报+释放显存+销号）或中途中断。Invoke whenever Dungeon♂Master says "跑程序"、"run"、"跑实验"、"跑一下"、"发射"、"用显卡跑"、"起个任务"、"train"、"inference"、or any GPU work needs starting in new1.
version: 1.0.0
---

# gpu-run — new1 GPU 任务全生命周期

一个任务从生到死的强制流水线。每一步都有产物，跳步 = 违规。

固定路径（NFS，处处一致）：
- 慢变量档案：`/home/y-guo/reproduce/new1/ops/gpu_state.md`
- 台账 CLI：`python3 run.py gpu-jobs`（注册任务，底层是 `ops/gpu_jobs.py`；
  记数字同理走 `python3 run.py record`。本机没有 `python`，只有 `python3`）
- 发射方法论（挑卡规则/分片/launch 替你做了什么）：`.claude/skills/gpu-run/references/launch-methodology.md`
- 测速与 ETA 方法论（`ops/verdicts.py` 判定口径/decision tree）：`.claude/skills/gpu-run/references/monitor-methodology.md`
- 探卡脚本：`.claude/skills/gpu-run/scripts/gpu_status.sh`

## Phase 0 — 读档案

Read `ops/gpu_state.md`。重点：别名去重（shiga=105, saitama=108）、
tokyo106/107 只有 CUDA 12.2、tokyo108 的 H100/H200 idx 分布。

## Phase 1 — 实探空卡（永不信缓存）

```bash
python3 run.py gpu-jobs free   # ≈6 秒（仓库根执行）
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

**smoke 阶段树常是脏的**（代码刚改完还没定稿），所以这一段用
`python3 run.py show <task> --allow-dirty` / `python3 run.py launch-probe smoke … --allow-dirty`
出命令：smoke 产物不留档、不进 `runs.jsonl`，不受"HEAD 要追得回代码"这条追溯约束。
`launch-probe smoke` 重跑同一个 smoke 目录还要带 `--force`（smoke 目录名是从
批次/模型/格确定性推出来的，第二次会被"同 out 已有 train_log.jsonl"守卫拦住）。
smoke 也可以先用 `python3 run.py launch <task> ... --dry-run` 看每个分片实际
会跑的命令——只打印，不发射、不登记。
**正式发射（Phase 4）之前必须 commit**，那一步的脏树门禁不许用 `--allow-dirty` 糊过去。

## Phase 4 — 发射前 commit + launch + 交监控入口

**执行方式**：发射环节整段派 `gpu-runner` agent 干（探卡/smoke/launch/验活
打包给它，opus 够用），不在主对话手搓——主对话负责规划与写脚本。

1. **commit 代码**。实验记录里存的 git HEAD，只有工作树干净时才追得回
   真实跑的那版代码。脏工作树 `record.py` 会打 ⚠️ 但不拦你——追溯断链是你自己的损失。
   仓库根 `run.py` 从这里往前顶了一步：注册表里的 GPU/发射类任务出命令前查
   `git status`，脏树直接拒绝（`--allow-dirty` 逃生）——2026-08-02 起的硬门禁。
2. **`python3 run.py launch`**：
   ```bash
   python3 run.py launch <task> [任务参数...] --run-id <run_id> --track <方向> \
     --piece <host>:<gpus> [--piece <host2>:<gpus2> ...] [--note "..."] \
     [--outdir <产物目录>] [--stall-line 秒] [--escalate-line 秒] \
     [--warmup-line 秒] [--service]
   ```
   一条命令做完发射流水线钉死的十步（顺序见 `ops/launch_cmd.py` 头注释）：
   解析参数 → 脏树门禁 → pieces 解析（多分片要任务在注册表里标了
   `shardable: True` 才许多个 `--piece`，会自动往每个分片注入
   `--shard-id i --num-shards N`）+ session/log 命名（session 名
   `new1_<run_id>_t<host去掉tokyo前缀>g<gpu>`，日志
   `<workdir>/logs/<session>.log`）→ 逐 piece 实探非 FREE 就整次拒绝（一张
   占用都不发射）→ tmux 发射 → 30 秒验活窗口（全部 piece 见到日志字节数增长
   即提前通过；窗口到时 session 没了或 tail 出现 Traceback 才算失败——已发射
   的不回滚也不登记，失败会把每个失败分片的日志末 40 行打出来）→ 台账
   `ops/jobs.json`、实验记录 `ops/runs.jsonl`（经 `record.py start` 子进程）、
   产物目录 `RUNMETA.json` 三处登记一次做完（`ops/launch_common.py`
   `register_all`，顺序固定 RUNMETA→台账→记录：RUNMETA 排最前，发射已经
   真实发生，产物钉代码先落盘，后面台账/记录拒绝（重复 run_id）也不会把它
   连带丢掉；RUNMETA 写失败只 WARN，台账/记录任何一步失败原样往外抛，
   不吞）。`register_all` 是 RUNMETA 的唯一写手：两个排卡发射器
   `launch-probe` / `launch-eval` 把产物目录、kind（`train` / `eval_tool` /
   `eval_call`）和 session/gpu/log/排卡表交给它写，回执里有 `RUNMETA: <路径>`
   一行；只有 `run.py launch` 没给 `--outdir` 时才会看到
   `WARN 没给 --outdir，RUNMETA 没写`，那才是真没写。2026-08-26 之前两个排卡
   发射器各自先写一条再调 `register_all`，回执里那句 WARN 是误报，按它手补
   `runmeta` 会在同一份 RUNMETA 里留两条重复记录（np821 批实录）。
   手打三条登记命令的流程不存在了。
   `--run-id`/`--track` 必填（`record start` 硬要求，`--track` 要和
   `TIMELINE.md` 里的方向对得上）；给了 `--outdir` 才写 RUNMETA，没给只打一行
   `WARN`（产物目录事后才能确定的任务，回头自己补
   `python3 run.py runmeta <产物目录> --cmd '<完整命令>' --kind <kind>`；
   kind 是自由字符串，launch 自动登记写 `launch`，两个排卡发射器写
   `train` / `eval_<阶段>`，手搓补录照这批值挑一个贴切的）。
   注册表外的一次性命令走 `--cmd '<完整命令>' --workdir <dir>` 逃生口，不查
   TASKS，命令原样进 tmux，登记照做。
   分片死了要重发同一 session（补射）：
   `python3 run.py launch --refire <run_id> --idx <N> [--piece host:gpus]`——
   不新开 record、不重复 register，只改台账该 piece 的 host/gpus/log/
   launched_at 四元组。
3. **交监控入口**：`launch` 发射成功会自己打印这两条，确认它们出现在给
   用户的回复里（这是用户亲自监控的入口）：
   ```bash
   cd /home/y-guo/reproduce/new1 && python3 run.py gpu-jobs           # 看一眼
   cd /home/y-guo/reproduce/new1 && python3 run.py gpu-jobs watch     # 30s 自动刷新
   ```
   表里有每个分片的进度、实测速率、ETA、tmux 存活状态。
   **两条命令末尾都会列"台账外 tmux session"**（裸 `gpu-jobs` 与 `watch` 走的是
   同一个 `collect(with_extras=True)`），扫的是固定四台机器
   `tokyo105/106/107/108`——不是只扫台账里已有的 host，所以台账为空时也照样能
   看见漏 register 的 session 或别的对话在跑的东西。
   外加浏览器 `http://localhost:8377`（ssh 端口转发）：后台采样器（下一节）
   自己起的网页，展示的是 `ops/verdicts.py` 算出来的六格判定
   （健康/变慢/warm-up 中/疑似卡死/已挂/已完成），`/json` 路径出机器可读的
   同一份数据——终端 `gpu-jobs`/`watch`/`json` 三个出口已经接读这份采样历史
   （工单 07，口径见 `references/monitor-methodology.md`）：`latest.json`
   在 5 分钟新鲜度门槛内就直接渲染判定，过期退回现场实探老路（tail 日志/
   ssh 探 session），不必再单独去开网页看。

## Phase 5 — 采样器接管（Claude 不再常设巡检）

判定、升级由后台采样器负责（`ops/sampler.py` 每 `sample_interval_s`
（默认 60 秒）读一轮全部心跳，按 `ops/verdicts.py` 算出每个分片的判定/速率/
ETA，写进它自己的状态文件（`latest.json`，网页出口直接读这份；口径见
`references/monitor-methodology.md`）——不用再靠 Claude 定时排程巡检。

Claude 只在两种时机派只读的 `job-monitor` agent 读采样结果
（`python3 run.py gpu-jobs json`——5 分钟新鲜度门槛内直接吐采样器的判定，
过期自动退回现场实探；网页 `http://localhost:8377/json` 是同一份数据的
另一个出口，两边选一个读就够）：
1. 用户问起进度/ETA/是不是卡住了；
2. 事故记录（`incidents.jsonl`）里有新内容（说明采样器至少判过一次升级）。

**事故 agent 自动验尸补射：已接线、未经真实演练。** `ops/sampler.py` 的
`should_trigger`（触发规则纯函数）与 `maybe_trigger_incidents`（命中后拉
agent）在 2026-08-08 经用户授权由主会话实装：升级发生时先把事故记录写进
`incidents.jsonl`，再拉起一个无头 `claude` 子进程（模型钉 opus，detach 不
等待，输出写进 `monitor/incidents/<事故编号>.out`），同时标记
`incident_open` 防止同一事故每轮重复拉起。手动演练经用户裁决取消——全链
只有单测背书，没有真实拉过一次 agent，第一次真实事故发生时这条链是首跑。
发现升级仍可以靠人或 Claude 主动巡检去看，读日志定位死因，能修则用
`python3 run.py launch --refire <run_id> --idx <N>` 补射。

## Phase 6a — 正常收尾（强制五连）

1. **汇报**：结果文件在哪、条数对不对（分片合并后 count == total）、
   关键数字一句话。
2. **记数字**：
   ```bash
   python3 run.py record finish <run_id> --metric <k=v> [--metric ...] \
     --data <最终数据路径> --conclusion "一句话结论"
   ```
   数字自动进 `RESULTS.md`。**如果这个结论动了 `WORKPLAN.md` 里任何一条判断，
   同时往 `TIMELINE.md` 最上面追加一条方向决策**（写清决定了什么、被哪个 run_id
   触发、作废了什么）。纯进度推进不用记 TIMELINE，那是 `plans/` worklog 的活。
3. **释放**：杀掉所有残留 tmux session / vLLM 服务，
   `nvidia-smi` 确认显存归零。批量任务结束不许占卡过夜。
4. **销号**：`python3 run.py gpu-jobs finish <task>`。
   session 还活着它会**拒绝销号**并把活着的 session 名列出来——先确认是不是真跑完了
   （踩过的坑：16:52 销号，任务实际跑到 18:17）。
   **探测失败也一样拒绝**（fail-closed）：ssh 连不上那台机时它分不清 session 是死是活，
   会列出探测失败的 host 并退出，不会当成"没有 session"放行。
   两种拒绝的逃生口是同一个：`finish <task> --force`（会在 history 里打 `force_finished` 标记）。
5. **提交**：`git add` 本次改的代码 + 三个台账文件 `ops/runs.jsonl` + `RESULTS.md` +
   `ops/jobs.json`(+ `TIMELINE.md` 如有)，commit message 里带上 run_id。
   **提交台账是为了历史保全**——把这次跑的数字与台账变动钉进 git 历史，
   以后 `git log` 能查到哪一版账对应哪一次实验。
   它已经**不是**"下一次发射靠它"了：2026-08-02 起这三个文件加 `ops/*.lock`
   在脏树门禁里走白名单豁免（`run.py` 的 `LEDGER_PATHS`，`ops/record.py` 与
   `ops/runmeta.py` 各有一份同名单），台账没提交也不会拦住下一枪。

## Phase 6b — 中途中断（用户喊停或巡检判死）

1. 逐分片 `ssh <host> tmux kill-session -t <session>`。
2. `nvidia-smi` 确认显存已释放。
3. 汇报已完成到哪、日志和半成品输出在哪、可否断点续跑。
4. `finish <task>` 销号，台账 history 里留档。

## 铁律

- 台账只通过 `run.py gpu-jobs register/finish` 读写，不手改 jobs.json。
- 占用状态永远 Phase 1 现场实探，档案文件只记慢变量。
- 一个任务一个 name，重名先 finish 旧的。
- 统计数字只通过 `run.py record start/finish` 写；`RESULTS.md` 是渲染产物，
  手改会在下次 render 时被覆盖。`runs.jsonl` 只增不改。
- run_id 是贯穿主键：原始数据目录名 / tmux session / 台账 name / commit
  message 四处一致，缺一处就断一条追溯路径。
