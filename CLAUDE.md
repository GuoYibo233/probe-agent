# new1 工程规则

## GPU 任务：唯一入口是 gpu-run skill

任何要用显卡跑的程序（训练/推理/探针/vLLM，不分大小）一律走
`.claude/skills/gpu-run/SKILL.md` 的全生命周期流水线：
探卡 → 挑卡 → smoke → 发射前 commit → `launch` 发射（tmux + 三处登记）→
交监控命令 → 采样器接管判定与升级 → 收尾（汇报/记数字/释放/销号/提交）或中断。
禁止绕过它手搓 ssh/nohup 启动。

- 发射与登记收成 `python3 run.py launch` 一条命令（探卡/tmux/验活/三处登记一口气做完）。
- 集群慢变量（驱动/CUDA/坑）：`ops/gpu_state.md`
- 任务台账：`ops/jobs.json`，`launch` 发射时自动登记，收尾 `python3 run.py gpu-jobs finish` 销号，
  手搓发射才用 `gpu-jobs register` 补录；不许手改文件本体
- 用户自助监控：`python3 run.py gpu-jobs watch`；网页 `http://localhost:8377`（ssh 端口转发）
  由常驻采样器 `python3 run.py sampler` 提供，采样器没跑网页就没有
- 实时空卡：`python3 run.py gpu-jobs free`（永不信缓存的占用状态）
- 产物钉代码：发射器自动往产物目录写 `RUNMETA.json`（commit+argv+脏清单）；
  手搓发射必须补 `python3 run.py runmeta <产物目录> --cmd '<完整命令>'`

## 探针流水线：整条链走 probe-pipeline skill

要把 collect/annotate/train/eval 串起来跑一批（换数据集 / 换模型 / 出矩阵），
走 `.claude/skills/probe-pipeline/SKILL.md`：定批次 → 采集 → 写码 → 双验收线 →
造数据 → smoke → 训练 → 依赖顺序评测 → 矩阵 → 收官 → **回写 skill**。
单个 GPU 任务仍只用 gpu-run；这个 skill 管的是整条链，GPU 环节转交 gpu-run。

**扩展流水线也从这里进**：加新模型 / 新环境 / 新训练方法(新格) / 新 split 方法，
改动清单在 `references/extending.md`（§5 静默失败点总表必看）。
**扩展完必须按 Phase E 回写 skill**——不回写，下一个人拿的就是旧地图。

## 跑任务：统一从 run.py 进

凡是注册表里有的任务（采集/标注/训练/评测/回放注入/执行/活跑，不分 CPU、GPU），
一律从仓库根 `run.py` 进，禁止直接调底层脚本：
- CPU 任务：`python3 run.py <task> [参数...]` 直跑，解释器由注册表定。
- GPU/发射类任务：`python3 run.py show <task>` 出命令，发射本身仍走 gpu-run skill。
  show 对发射类同样过脏树门禁（`--allow-dirty` 放行）；三个台账文件与锁
  （jobs.json/runs.jsonl/RESULTS.md/*.lock）不算脏。
- 多步流程用 `python3 run.py recipe <name>`，进度看 `run.py status`。
- 注册表里没有的任务：先挂进 TASKS/RECIPES 再跑
  （一次性发射器按 2026-08-02 裁决不进注册表，属唯一例外）。
- 扩展代码与注册表更新同一个 commit，交付前过 `python3 run.py selfcheck`。

## 记录：四本账加原始数据，主键 run_id

每次实验都要留下痕迹，分五层（四本账 + 原始数据），别混用：

| 层 | 文件 | 谁写 | 回答什么问题 |
|---|---|---|---|
| 方向 | `TIMELINE.md` | 人写，只增不改 | 当初为什么这么定 |
| 数字 | `ops/runs.jsonl` → `RESULTS.md` | `ops/record.py` | 数据长什么样 |
| 数据设定 | `DATA.md` | 人写，随数据版本更新 | 这批数据是怎么造出来的 |
| 计划 | `WORKPLAN.md` | 人写，会被覆盖 | 接下来打算做什么 |
| 原始数据 | NFS，不进 git | 实验脚本 | 数据本体在哪 |

- **开新实验之前先过 `DATA.md` 的检查清单**。里面每一条都对应一个已经踩过的坑。
- `DATA.md` 只写设定与口径，**不写结论**——结论归 `RESULTS.md`，否则会长成第二本账。
- 代码地图在 `MAP.md`：每个程序是干什么的、怎么用。加新程序要更新对应行。
- `run.py launch` 发射时自动调 `record start`（抓 git HEAD），收尾时手动
  `run.py record finish` 补数字，两步写在 gpu-run skill 的 Phase 4 / 6a 里，跟着流水线走就不会漏。
- `RESULTS.md` 是渲染产物，**不要手改**；`runs.jsonl` append-only，只增不改。
- `WORKPLAN.md` 是会被覆盖的当前计划，`TIMELINE.md` 是永不覆盖的决策历史，
  两者分工不能颠倒。实验结论动了 WORKPLAN 任何一条判断 → 必须补一条 TIMELINE。
- run_id 四处一致：原始数据目录名 / tmux session / 台账 name / commit message。

## 版本控制

- 本目录是 git 仓库（2026-07-29 建，无 remote）。
- 入库边界：代码 / 笔记 / 统计数字进库；虚拟环境、第三方 clone、
  原始轨迹、模型权重、日志不进库（见 `.gitignore`）。
- **发射实验前先 commit**：记录里存的 HEAD 只有工作树干净时才追得回真实代码。

## 铁律：不许猜数据结果

没有用户明确允许，以下三件事一律不做：

1. **没亲眼读过实际的输出文件或代码，不许对数据结果做任何猜测、判断、解读。**
   包括归因、下结论、推测机制。反面案例：w2 比 w0 差，没看任何日志就说是 GPU 原因。
   要解释一个数字，先把产出它的文件（日志 / jsonl / eval 输出）和跑它的代码读了；
   读不到就直说读不到，然后停在那里。
2. **不许给"什么数据有说服力""论文该怎么叙事"这类建议。**
3. **不许夸**用户的结论、问题或数据结果。

汇报实验结果只摆事实、不带评语。这条与 `DATA.md` 只写设定不写结论、
以及"事实和解读分开且事实在前"是同一条纪律。

## 其他铁律

- 与 `/home/y-guo/ACL2026` 完全隔离：不读写其数据/代码/结果（硬件共用没问题）。
- **大产物一律直接写 net 盘**（2026-08-01 起，home quota 打满后的铁律）：训练产物 /
  原始轨迹 / 数据集 / checkpoint 都放
  `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/`（镜像本目录结构），
  home 里只留代码、笔记和软链接。
- 环境一律 uv 管理。
- 模型权重下载到 `/net/tokyo100-10g/data/str01_01/y-guo/models`，不放 /home。
- 动手前先取得同意；一个请求只做那一件事。

## Agent skills

### Issue tracker

spec 和工单以本地 markdown 文件存放：一个功能一个目录 `.scratch/<功能名>/`，
spec 是 `spec.md`，工单是 `issues/NN-<名字>.md`。约定见 `docs/agents/issue-tracker.md`。

### Triage labels

工单状态用五个默认标签字符串（needs-triage / needs-info / ready-for-agent /
ready-for-human / wontfix），写在工单文件的 Status 行。对照表见 `docs/agents/triage-labels.md`。

### Ticket 执行

成批执行 `.scratch/<功能名>/issues/` 里的工单，唯一入口是
`.claude/skills/ticket-run/SKILL.md`：主会话按 Blocked by 分波 → 预检+发射前 commit →
每波发射一个 workflow（`wave.js`，波内工单并行、每张一棵独立工作树一条独立分支，
实现-评审-修复循环上限 5 轮定死在脚本里）→ 分支合并与收账裁决 → 整分支终审。
subagent 模型写死 sonnet/opus，实现者禁发 GPU 进程（回 BLOCKED 走 gpu-run）。

### Domain docs

单库布局：词汇表是仓库根的 `CONTEXT.md`，架构决策记录放 `docs/adr/`。
读取规则见 `docs/agents/domain.md`。
