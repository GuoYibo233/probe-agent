# 长程任务监控与发射 — 设计定稿（2026-08-08）

一句话：脚本打心跳，采样器算判定，三个出口读同一份采样历史，出事自动拉
事故 agent 补射，发射收成 run.py 一条子命令。

词汇表在 `CONTEXT.md`（长程任务 / 台账 / 分片 / 窗口 / 判定 / 发射 / 心跳 /
采样器 / 采样历史 / 升级线 / 验尸 / 补射 / 事故记录 / 事故 agent / 进度单位），
本文沿用，不再重复定义。本文记设计决定；实施顺序另出计划，动工前再过一次同意。

要解决的问题（2026-08-08 的现状）：看任务状态要 agent 到处读文件做推理——
判定靠 job-monitor agent 两点测速，发射登记靠人打三条命令，定时巡检费上下文
又费 token，agent 半小时一醒大多数时候看到的是"一切健康"。

## 1 范围

只管 GPU 任务（进台账的那些）。CPU 长活、recipe 步骤不进。

交付物三块：
1. 程序：心跳模块 + 采样器 + `run.py launch` 子命令 + 两个排卡发射器的登记改造。
2. 脚本改造：自己的采集/训练/评测脚本接心跳。
3. 文档回写：§8 清单里的 skill / agent / 根文档。

## 2 心跳（脚本侧）

- 新文件 `ops/heartbeat.py`，只用标准库——哪个 venv 都能 import，不新增依赖。
- 脚本每完成一个进度单位往 stdout 打一行：固定前缀 `@hb ` 加一个 JSON。
  心跳行混在普通日志里落进 tmux 的 tee 日志，监控端 tail 日志尾只认前缀。
- 字段：必填 `done` / `total` / `unit`（"task" 或 "step"，脚本自己报）/
  `ts`（打这行时脚本所在机器自己的钟）；选填 `tok_in` / `tok_out`
  （**累计**值：到这一刻为止所有请求的 prompt / completion token 加总）、
  `loss`、`status`（"done" 表示正常收尾）。
- 进主循环先打一条 done=0——这条是"模型加载完了"的标志，
  加载耗时从此永远落在心跳时间轴之外。
- 改造名单：
  - `envs/collect/run_appworld.py`（unit=task；token 数据现成——
    `envs/collect/common.py` 每个请求都拿到 usage，累计后塞进心跳）
  - `pipeline/train/train_mbert_tool.py` 等训练脚本（unit=step，报 loss）
  - 评测脚本（实施时逐个过一遍名单）
- vLLM 服务是第三方，不打心跳，也没有 done/total 这回事。它按服务类
  分片走另一套判定（见 §4 末尾）；它日志里的吞吐行只拿来出 token 速率
  显示，不参与判定。吞吐行的确切字样仓库里还没有真实样本可核，
  实施前先抓一条真实 vLLM 日志确认（进 §10）。

## 3 采样器（监控侧）

- 新文件 `ops/sampler.py`，登录机 tmux 常驻（session 名 `new1_sampler`），
  60 秒一轮。
- 每轮干四件事：从台账 active 读任务清单 → tail 各分片日志抓心跳
  （日志在 NFS，本地读，不用 ssh）→ ssh 四台机 `tmux ls` 探存活
  （沿用现有 fail-closed 语义：探测失败 ≠ 没有 session）→ 算判定，
  append 进采样历史。
- 采样历史一个任务一个文件，逐轮的行里带分片位（shard-id），多分片
  各算各的。除逐轮记录外，每个分片位存一份累计状态：首条心跳 ts、
  最新 done、事故编号、补射次数。平均速率的原点从这里拿，不依赖
  日志开头还在不在 tail 范围里；采样器重启也从这里恢复。
- 台账外 session 扫描保留（现在 `collect(with_extras=True)` 的行为）：
  固定扫 tokyo105-108，漏登记的 session 上表提醒——只列 host 和
  session 名，不算判定、不触发事故（没登记就没有日志路径和发射命令，
  想管先补 register）。
- 采样线程和网页线程分开：HTTP 端口（可配，默认 8377）出网页，网页
  线程只读最新采样历史，采样那边 ssh 卡住不影响出页，页上时刻会变旧。
  ssh 探测本身带超时。你在 VS Code Remote-SSH 里端口自动转发，本地
  浏览器直接看。页面内容：任务表（判定 / 进度 / 速率 / token 指标 /
  ETA）、最后采样时刻（超过 3 轮没更新就变红）、事故记录块、
  台账外 session。
- 采样器自身的死活有两层兜底：终端表和网页都把"最后采样时刻过期"
  亮出来给人看；登录机 crontab 每 5 分钟查一次 tmux session，不在就
  重启采样器——采样器无状态，重启后从采样历史恢复，接着算。
- 落盘：采样历史和事故记录都是高频增量，不进 git，放 NFS 镜像目录
  `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/`，
  finish 后留档不删（占地小）。

## 4 判定

六个值全由采样器算，agent 只读结论。一个分片一轮恰好一格，按下面的
顺序判，命中即停：

| 顺序 | 判定 | 条件 |
|---|---|---|
| 1 | 已完成 | done == total，或收到 status=done 的心跳 |
| 2 | 已挂 | session 没了，又不满足已完成（包括一条心跳都没打就死的） |
| 3 | 疑似卡死 | session 活着，停摆时长 > 判定线 |
| 4 | warm-up 中 | session 活着，一条心跳都没有（还在加载） |
| 5 | 变慢 | 近期速率有值，且 < 全程平均速率 × 0.5 |
| 6 | 健康 | 以上都不是 |

- **时钟纪律**：跨机不比钟。停摆时长 = 采样器自己的钟下，"最近一次
  看到新心跳的采样时刻"到现在；心跳 `ts` 只用于同一台机自己的心跳
  之间做差（平均速率的分母）。
- **warm-up 有上限**：从发射时刻计，默认 30 分钟，超了转疑似卡死——
  卡死在加载阶段的任务不再永远沉默。`--warmup-line` 覆盖。
- **判定线** = 5 × 典型心跳间隔，下限 3 轮采样间隔（60 秒一轮即
  3 分钟）。下限的来历是采样粒度：停摆时间低于几轮采样，采样器分不清
  "停了"还是"还没轮到我看"，所以它跟采样间隔走，不是任务侧写死的数。
  典型心跳间隔 = 最近至多 20 个心跳间隔的中位数；攒不够 3 个间隔时
  判定线暂用 warm-up 上限顶着（长 task / 长 step 开局不误报）。
- **升级线** = 判定线 × 3，量的是同一个停摆时长：停摆超判定线转
  疑似卡死，停摆超升级线拉事故 agent。
- **速率**：平均速率 =（最新 done − 0）÷（最新心跳 ts − done=0 那条的
  ts）；近期速率 = 最近至多 10 条心跳的 Δdone ÷ Δts，不足 2 条就没值
  （表里显示 —）。token 速率同理用累计 tok 做差。加载时间碰不到任何
  分母。ETA = 剩余单位数 ÷ 近期速率，近期没值退回用平均速率。
- **探测失败**：那一轮存活沿用上一轮结论，表上标"探测失败"；连续
  10 轮探测失败只亮红、不触发事故 agent——分不清死活就不动手，
  fail-closed 一以贯之。
- **服务类分片（vLLM）**只用四格：warm-up 中（session 活着，端口还没
  应答过，同样吃 warm-up 上限）、健康（session 活着，端口应答）、
  疑似卡死（session 活着，端口连续 3 轮不应答）、已挂（session 没了）。
  已完成、变慢对常驻服务不适用；空闲不打吞吐行不算停摆。

## 5 出事之后

- 触发：判定变 **已挂** 当场触发；**疑似卡死** 停摆超过升级线触发。
- 动作：采样器起一个事故 agent（无头 `claude -p`，模型钉 opus），
  提示词带上这个任务的 json（判定、分片、日志路径、原始发射命令）。
  它和会话里只读的 job-monitor 是两个角色：job-monitor 是你派的检查员，
  只读不动手；事故 agent 是半夜的处置员。
- 事故 agent 只干"把实验办好"一件事，权限线：
  - 已挂 → 验尸（读日志尾定位死因）后补射一次。补射也走 launch：
    先 `gpu-jobs free` 实探挑卡（原卡优先，被占就换实探到的空卡），
    launch 出手前再验一次，被抢就换卡重试。session 已经没了，
    补射弄不坏任何在跑的东西。
  - 疑似卡死 → 只验尸，**不许杀**。心跳久停有假阳性（存 checkpoint、
    长评测段），杀错一个活任务比晚几小时补射贵。
  - 不写人读的报告。事故记录由采样器写；agent 的对话记录自动落在
    claude session 文件里，早上开新会话现场查。
- 补射后的账怎么接：任务名和 shard-id 不变，台账里该分片位的四元组
  （host / gpus / session / log）更新成新的；事故编号和补射限额跟着
  分片位（任务名 + shard-id）走，不跟 session 名走。该分片的心跳
  时间轴重开：判定线、平均速率、近期速率全部从补射后的 done=0
  重新积累，不跟旧轨迹混算。
- 限额与防抖：同一分片位整个任务生命周期**自动补射只许一次**，
  不清零；补射后再挂就停手，只记事故等人。同一次事故只拉一次
  事故 agent（事故记录里每条事故有编号，采样器认编号防重复触发）。

## 6 发射

```
python3 run.py launch <task> [任务参数] --piece <host>:<gpus> [--piece ...] \
  [--track <方向>] [--note <想验证什么>] \
  [--stall-line 秒] [--escalate-line 秒] [--warmup-line 秒] [--allow-dirty]
```

- 解释器 / 脚本 / cwd 从注册表拿；脏树门禁沿用（LEDGER_PATHS 豁免不变，
  smoke 场景 `--allow-dirty` 照旧）。
- `--piece <host>:<gpus>`，gpus 是逗号列表（一张卡就一个数，如
  `tokyo108:0,1`）。出手前对每个 piece 的卡做 FREE 实探，任何一张非
  FREE 整次拒绝——程序只守"不往有人的卡上发射"这条线，挑哪张卡仍是
  agent/人的判断。
- 分片：注册表 TASKS 新加一个键 `shardable`（现在没有这个键；现存的
  `shards=N` 是 RECIPES 步骤上的另一套，别混）。标了 shardable 的任务
  给多个 `--piece` 时，按 piece 顺序自动注入 `--shard-id i
  --num-shards N`，i 从 0 起——分片编号从此不过人手。没标的任务给
  多个 `--piece` 直接拒绝（防止两张卡各跑一份全量互写输出）。
- 然后一口气：起 tmux（session 名沿用 `new1_<task>_<host>g<gpus>`，
  多卡把逗号写成连字符；日志 `<workdir>/logs/<session>.log`）→
  三处登记（gpu-jobs register、record start、RUNMETA.json）→ 验活 →
  打印监控入口。验活标准：session 在、30 秒内日志有输出且无
  traceback，即发射成功；加载完不完交给采样器的 warm-up 判定，
  launch 不在原地等。
- run_id 一致性照 CLAUDE.md 原律（原始数据目录名 / tmux session /
  台账 name / commit message 四处一致）：session 名、台账 name、
  record run-id、日志名全部由程序从同一个 run_id 生成，不靠人对。
- 注册表外的一次性发射（2026-08-02 裁决的唯一例外）不给 `<task>`，
  用 `run.py launch --name <run_id> --workdir <dir> --cmd '<完整命令>'
  --piece ...`：命令原样进 tmux，解释器写在命令里，登记照做。
- `launch-probe` / `launch-eval` 两个排卡发射器不合并，各自的守卫
  保留（launch-probe 的排卡表与 smoke 模式；launch-eval 的依赖顺序
  硬检查与训练产物 `best/` 存在检查——它没有 smoke），内部改调
  同一套登记函数 + 同一个 FREE 实探。改完，"程序保证登记"在所有
  发射路径上成立，没有例外注脚。

## 7 三个出口

- **终端表**：`gpu-jobs` / `watch` 改读采样历史，瞬间出结果，表头带
  最后采样时刻，过期亮出来。`free` 和发射验卡**永远现场实探**——
  "永不信缓存"这条铁律管占卡决策，不管看进度。
- **json**：给 agent 的出口，判定、速率、ETA 都是现成结论。job-monitor
  从此不再自己两点测速——那套动作变成采样器的固有能力。
- **网页**：同一份采样历史的出口，你远程看。
- 收尾流程不动：已完成只是判定，销号仍走 `gpu-jobs finish` 的
  fail-closed 检查，gpu-run skill 的 Phase 6a 五连照旧。

## 8 文档回写清单

grep 数出来的引用点（2026-08-08），实施时逐个改：

**大改**：`gpu-run/SKILL.md`（Phase 4 发射段收成一条 launch、Phase 5 巡检
制度改成采样器条款、交给用户的监控命令换新）；`gpu-run/references/
launch-methodology.md`（tmux 模板段归 launch）；`gpu-run/references/
monitor-methodology.md`（两点测速从 agent 手册变程序职责说明）；
`agents/job-monitor.md`（瘦成"读 json 判定 + 按需验尸"，只读不变，
与事故 agent 的分工写清）；`agents/gpu-runner.md`（发射段改用 launch，
双登记段删）；`probe-pipeline/SKILL.md`（74-75 收尾链、134 G16、
172-173 释放销号、221-222 agent 分工表）；`probe-pipeline/references/
gates.md`（G2/G16/G17 措辞）；`references/stage-commands.md`（19、352 行）；
`references/invariants.md`（记账双写：从"人保证"变"launch 保证"）；
`references/extending.md`（新脚本清单加"接心跳"，130 行 job-monitor
认日志事件）；`MAP.md`（gpu_jobs.py、launch_probe.py、launch_eval.py
三行更新，heartbeat.py / sampler.py / launch 各加一行）；`CLAUDE.md`
（GPU 段监控命令与台账入口）；`ops/gpu_state.md`（页首指引）。

**小改**：`handoff/SKILL.md` 42 行"在跑的任务"表指向采样历史。

**不动**：`agents/env-runner.md`（CPU 侧，范围外）、exp-status /
paper-write / 两个 knowledge-map skill（无引用）。

## 9 明确不做（v1）

- CPU 任务不进窗口。
- 手机推送不做；事故记录里每条事故自带定位一条事故所需的字段，
  以后接推送是加法。
- 对活着的任务自动杀，不做。
- 常设定时巡检制度撤销，不是改良——采样器顶替。
- 采样历史不进 git。

## 10 留到实施时定的小事

- vLLM 吞吐行的确切字样：先起一次真实 vLLM 服务抓日志核对，再写解析。
- 事故记录与 json 出口的字段表。
- 评测脚本接心跳的具体文件名单（逐个过）。
- 分片输出文件名怎么从模板生成。
- 网页具体布局。
- 所有常数做成配置，跑出误报再调：判定线的 5 倍与 3 轮采样下限、
  升级线的 ×3、warm-up 上限 30 分钟、近期速率窗口 10 条心跳、
  探测失败亮红的 10 轮、验活等待 30 秒。
