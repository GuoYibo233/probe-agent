# 两棵树、init、入口 skill、宿主对接

> 这份覆盖四件事：`rl init` 在研究仓库里建什么（含 `research-loop.json` 的全部键和阈值默认值表）、插件本体那棵树长什么样、入口 skill 干哪三件事和领路路线图怎么写、迁移老代码的规矩，以及 research-loop 和 new1 这个宿主仓库的每一条对接。
> 这份不覆盖：九本账每一行的字段格式（在 `03-ledgers.md`）、`bin/rl` 每条子命令的参数（在 `05-rl-cli.md`）、钩子拦什么和角色 json（在 `06-hooks-and-permissions.md`）、快车道的进出动作（在 `07-quick-lane.md`）、run 角色照 gpu-run 写的八个阶段（在 `12-role-run.md`）、deploy 改宿主文件的三条纪律本身（在 `11-role-deploy.md`）、待验证清单和施工步骤（在 `30-build-steps-verify-tests.md`）。
> 源：设计文档的「两棵树」「入口 skill 与代码迁移」「分权与钩子」「gyb 自己做的事」四节；施工计划的第一节裁决 2、第二节词表、第六节 `rl init` 那一行、第七节、第八节阈值表、第十一节步 7、第十二节。

## 一、研究仓库这棵树：init 建什么

`rl init` 在研究仓库里建六样东西，再往仓库的 CLAUDE.md 追加一节。`rl init` 只在裸终端跑：读到会话状态文件（`loop/.sessions/<session_id>.json`，2026-08-18 gyb 裁，定义处 `06`）就拒收，退出码 3（2026-08-17 随 `05` 定稿裁，待验证第 4 条的失败备案升正案）。

`rl init` 重跑没有副作用（2026-08-18 gyb 裁）：已经有的东西一样不动（配置文件里 gyb 改过的值不覆盖，`loop/` 不动），缺的补上，CLAUDE.md 那一节已经在就不再追加，跑完打印一张清单分两栏「已存在，跳过」和「这次新建」，退出码 0。插件新版本多了要建的东西，重跑一次就补齐。

`rl init` 只动研究仓库自己的东西：不改宿主的代码（new1 的 `run.py` 门禁那处改动归施工，见 7.2、7.9），不往仓库的 `.claude/agents/` 播文件，不动仓库的 `.claude/settings.json`（角色 agent 定义和钩子都在插件本体里，见第四节；2026-08-18 gyb 裁）。

| 建什么 | 是什么 |
|---|---|
| `research-loop.json` | 配置文件，键见第二节和第三节。init 自带一份默认模板：阈值全按第三节的默认值直接落；跟仓库绑定的那几项（`artifact_root`、`analysis_artifact_root`、`launcher.*` 四条、`repo_run`、`host_ledgers`）init 逐项问 gyb，答完写进去；gyb 跳过的留空，跑完把留空的项列出来，留空的命令模板对应的动作就跳过（2026-08-18 gyb 裁，见第二节） |
| `loop/` | 九本账，一行一条 json，只经 `bin/rl` 进出。九本账的位置和文件名钉死：永远是 `loop/` 下 `03-ledgers.md` 词表里那九个名字，配置里没有「各账路径」这一项（2026-08-18 gyb 裁，原话「定死吧」）。`loop/` 进 git，每次 commit 顺手带上，不另设 commit 动作；`.gitignore` 不排除 `loop/`，但 `rl init` 往 `.gitignore` 加一行 `loop/.sessions/`：会话状态文件 `loop/.sessions/<session_id>.json` 是普通文件、不算九本账、不进 git、不算脏树（2026-08-18 gyb 裁，定义处 `06`「会话状态文件」；`rl init` 建 `loop/.sessions/` 这个空目录）。`loop/.doctor-acks.jsonl` 是普通文件、不算九本账之一，`03-ledgers.md` 的账本总规矩（只增不改、锁、进 git、脏树白名单）不管它，它由 doctor 首次 `--ack` 时建、`rl init` 不建（2026-08-17 随 `05` 定稿裁；不归总规矩管是 gyb 裁，sync-inbox 问题 24） |
| `experiments/` | 运行实验的代码，写权只有 deploy |
| `analysis/` | 统计代码和 notebook，写权只有 analysis |
| `review/` | reviewer 的问题清单 |
| `notes/` | gyb 自己写的文档，gyb 和 idea 写（idea 能写 `notes/` 是 2026-08-18 gyb 裁，定义处 `06`），谁都能读 |

`analysis/` 下面的公共统计件由 init 播模板，播三样（2026-08-18 gyb 裁）：`analysis/common/metrics.py`（指标函数文件，只有骨架和一个示例函数；`13` 里派生指标的 `code_path` 形如 `analysis/common/metrics.py:accuracy`，指的就是它）、`analysis/common/ledger.py`（从 runs 账取数的辅助函数，只经 `bin/rl` 的查询命令读）、`analysis/scratch/` 空目录（留给快车道）。notebook 不播，由 analysis 干活时新建；画图风格、notebook 模板都不播。

原始数据不新建目录，走配置里的产物根 `artifact_root`，在 new1 指到 net 盘。每次 run 的产物目录按约定是 `<artifact_root>/<run_id>/`，账上不另记，看门狗和 analysis 都按这条约定找（这条约定的定义处是本份，2026-08-17 gyb 裁；runs 账去掉 `artifact_dir` 见 `03`）。

往 CLAUDE.md 追加的那一节有三句话，追加不覆盖，new1 原有的规矩照旧：

1. 「没有 gyb 允许，experiments/、analysis/、review/、loop/ 只能在加载了对应角色的会话里改」。
2. 「加载了 run 角色的会话以 run 的 SKILL.md 为准，它是 gpu-run 的超集，宿主 GPU 铁律里的『唯一入口』对 run 会话读作 run skill」。
3. 「loop/*.jsonl 和 loop/.lock 不算脏树」。

这三句是给没加载角色的裸会话看的纪律。裸会话身上没有钩子，什么都能写，这一点不用兜底钩子去堵，靠这一节加 reviewer 事后查。

init 要问 gyb 的东西都在同一次交互里问完：配置文件里跟仓库绑定的那几项（第二节表里标「init 问」的）。原来外加的一问「要不要当场给 idea 发 `read:notes` 授权」随获准机制 2026-08-21 砍掉，不问了（定义处 `10-role-idea.md`）。重跑 init 时已经填过的项不再问。

## 二、`research-loop.json` 的键

配置文件里放两类东西：路径、宿主命令模板和两项带格式的说明是一类，阈值是另一类（阈值全表在第三节）。设计文档「两棵树」一节列的是：各账路径、产物根、分析产物根、快车道 worktree 根、本仓库跑法、宿主发射器的命令模板（探卡、发射、收尾、中断）、宿主台账清单。其中「各账路径」2026-08-18 gyb 裁掉：账的位置钉死在 `loop/`，配置里没有这一项（见第一节）。其余各项的键如下，「init 问」一栏标 ✓ 的由 `rl init` 逐项问 gyb 填，其余是阈值表或有默认值：

| 键 | 装什么 | init 问 | 出处 |
|---|---|---|---|
| `artifact_root` | 产物根，实验产物和原始数据落这里；new1 指到 net 盘 | ✓ | 词表、设计文档「两棵树」 |
| `analysis_artifact_root` | 分析产物根，大文件落这里，小图和 notebook 进仓库 `analysis/` | ✓ | 词表、设计文档 analysis 一节 |
| `quick_lane.worktree_root` | 快车道 worktree 建在哪，分支名和目录名都用 `ql_tag`；有默认值 | | 第八节阈值表 |
| `gpu_state_path` | 宿主的慢变量档案路径，new1 是 `ops/gpu_state.md` | ✓ | 第七节 Phase 0 |
| `launcher.free_cmd` | 探卡命令模板，new1 是 `run.py gpu-jobs free` | ✓ | 第七节 Phase 1 |
| `launcher.launch_cmd` | 发射命令模板，new1 是 `run.py launch` | ✓ | 第七节 Phase 4 |
| `launcher.finish_cmd` | 宿主收尾命令模板，new1 是 `run.py record finish` | ✓ | 第七节 Phase 6a |
| `launcher.abort_cmd` | 宿主中断收尾命令模板，中断收尾四步（杀进程、释放显存、宿主销号、runs 落 killed，见 `12`）里「宿主销号」那一步调它，new1 是 `run.py gpu-jobs finish`；宿主没有这条命令的仓库留空，留空就跳过这一步（2026-08-18 gyb 裁，四条模板各一个键） | ✓ | 设计文档「两棵树」四条模板 |
| `repo_run` | 「本仓库跑法」，固定三栏、每栏装自然语言或命令，机器不解析、角色上线读配置时原样看到：`env`（环境怎么起，new1 是「一律 uv 环境」）、`entry`（任务从哪进，new1 是 `python3 run.py <task>`）、`notes`（其它要知道的自由文字，new1 是「注册表里没有的任务先挂进注册表再跑」）（2026-08-18 gyb 裁，形状是「有格式又能装自然语言」） | ✓ | 设计文档「两棵树」 |
| `host_ledgers` | 「宿主台账清单」，一张列表、每项三栏：`path`（宿主文件路径）、`note`（一句自然语言说它是什么、谁写它）、`kind`（只有宿主 runs 账那一项填 `runs`，doctor 对账时按这个标记找宿主 runs 账；其余项留空）。角色一律不碰清单里的文件（7.5），机器只解析 `kind`，其余供 reviewer 事后查。new1 的五项：`TIMELINE.md`（方向，gyb 手写）、`DATA.md`（数据设定，gyb 手写）、`RESULTS.md`（渲染产物，宿主脚本写）、`ops/runs.jsonl`（宿主数字账，宿主发射器写，`kind: runs`）、`ops/jobs.json`（宿主任务台账，宿主发射器写）；产物目录里的 `RUNMETA.json` 不在仓库里，不列（2026-08-18 gyb 裁） | ✓ | 设计文档「两棵树」 |

`launcher.*` 四条模板留空的含义都一样：这个宿主没有这一步，rl 调到这里就跳过、不报错，`rl init` 跑完的清单里列出哪几条留空。

## 三、阈值默认值表（全文）

这张表写进 `research-loop.json`，gyb 可以改。

| 键 | 默认值 | 用在哪 |
|---|---|---|
| `watchdog.stall_mult` | 5 | 卡死判定线 = 5 倍典型心跳间隔，沿用 `ops/verdicts.py` |
| `watchdog.stall_floor_samples` | 3 | 判定线下限三轮采样 |
| `watchdog.warmup_seconds` | 1800 | 开局 30 分钟不判卡死 |
| `watchdog.gpu_util_zero_seconds` | 900 | 显卡利用率连续 15 分钟为零算一路证据 |
| `watchdog.timeout_factor` | 3 | 超时 = 最新尝试 `estimated_seconds` 乘 3 |
| `issues.gyb_stale_hours` | 24 | `rl status` 段 2 标出超过 24 小时没动的 |
| `issues.answered_stale_days` | 3 | doctor 报 answered 超过 3 天没 close |
| `status.stale_holder_minutes` | 30 | `rl status` 段 7：holder 会话超过 30 分钟没写账的开干单 |
| `reclaim.session_idle_hours` | 48 | 会话超过 48 小时没写任何账算很久没动 |
| `reclaim.handoff_idle_hours` | 72 | 单子超过 72 小时没转移算很久没动 |
| `reclaim.ql_idle_days` | 7 | 快车道超过 7 天没关列进 reclaim |
| `anomaly.metric_extremes` | `[0, 1]` | 指标落在 0 或 1 触发反常预警，`rl run finish` 里查 |
| `anomaly.duration_factor` | 3 | 实际耗时超过预计 3 倍触发反常预警，同上 |
| `status.review_recent_days` | 7 | `rl status` 列最近 7 天的 review 清单 |
| `lock.timeout_seconds` | 10 | 文件锁等多久算超时，超时退出码 4（2026-08-17 随 `05` 定稿加） |
| `quick_lane.worktree_root` | `<仓库>/../<仓库名>-ql/` | 快车道 worktree 建在哪 |
| `hooks.path_allowlist` | `[]`（空） | 写权钩子的路径白名单：列在里面的路径不管折成什么一律放行，用来放「路径写在仓库里、东西其实在仓库外」的地方；默认为空，gyb 在 `rl init` 之后按需填（2026-08-18 gyb 裁，定义处 `06`「路径怎么判」；键名是本份定的，`06` 只说「插件配置里的一项、和阈值表放一起」） |

## 四、插件本体这棵树

插件本体留在 `new1/research-loop/` 子目录里，不另开仓库。`research-loop/` 目录下现有的 93 个文件整体退役，新插件从空目录开始写，旧代码留在 git 历史里。

| 目录或文件 | 装什么 |
|---|---|
| `.claude-plugin/plugin.json` | 插件清单，施工步 1 新写（施工计划第十一节步 1） |
| `README` | 插件说明，要明写「fable 是 gyb 2026-08-16 点名的例外」（施工计划第一节裁决 3） |
| `skills/` | 六个 skill：入口一个，五个角色各一个。角色 skill 的头部**不再声明钩子**（2026-08-18 gyb 裁，待验证第 8 条测出 skill 头部钩子只管顶层会话、subagent 的调用不经过它，见下面 `hooks/` 一行） |
| `agents/` | 五份角色 agent 定义，派活起 subagent 时一律用这五个类型（`06`、`04` 定具体名字和用法）。每份只做「塑形」：角色提示词、预加载那个角色的 skill、收窄工具面（比如 reviewer 直接禁 Write 和 Edit）；**不写钩子**——插件里的 agent 定义头部的钩子字段被 Claude Code 忽略（官方文档明写，2026-08-18 实测三个变体都不触发）。init 不把这五份播进研究仓库（2026-08-18 gyb 裁） |
| `common/` | 公共母版：公共规矩、词表、五栏规格、读法、判断类检查问题清单 `REVIEW-CHECKLIST.md`，带 `rules_version`（整数，`GLOBAL-RULES.md` 头部一行） |
| `tables/` | 九本账的表结构、派活单的状态转移表、角色 json、gyb 的 use case 表 |
| `schemas/` | 九本账的行格式 |
| `scripts/` | 入账与查询的实现 |
| `bin/rl` | 命令入口，含 status、inbox、trace、回收、doctor |
| `hooks/` | 插件级钩子文件（`hooks/hooks.json`）加钩子脚本本体，一份总钩子，装插件即对这个仓库里所有会话的工具调用生效——顶层会话、subagent、嵌套 subagent 都过闸（2026-08-18 实测：仓库 settings 级和插件级钩子对 subagent 生效，输入里带 `agent_type` 和 `agent_id`，`session_id` 与父会话相同）。脚本判角色两路：先看 `agent_type`，认识的类型名对应角色、不认识的一律按最严策略拦；没有 `agent_type` 才是顶层会话，按会话状态文件查角色。会话状态文件的写入也由这份钩子文件里的一条钩子做（检测到加载角色 skill 时按 `session_id` 落文件，`agent_type` 非空不写，防 subagent 污染父会话状态）；销号钩子也在这里。匹配范围含 Write、Edit 和 Bash（Bash 分支解析命令里的重定向、`tee`、`sed -i`、`mv`/`cp` 目标路径，自己 realpath；2026-08-18 gyb 裁，归 `06`/`00` 改）。第 2 条测通的「参数报角色名」写法作废：角色由脚本自己判，不从参数来（2026-08-18 gyb 裁，钩子怎么挂的定义处仍是 `06`） |
| `monitors/` | 一个，发射看门狗，只在 run 上线时起，只写自己的状态文件 |
| `tests/` | 测试 |

反常结果预警不做常驻进程，并进 `rl run finish`。

上表比设计文档「两棵树」列的插件目录多三样，来历各是：`.claude-plugin/plugin.json` 和 `README` 按施工计划补（第一节裁决 3、第十一节步 1，原文不一致按后裁的施工计划）；`agents/` 是 2026-08-18 待验证第 8 条测完 gyb 裁加的。施工计划步 2 的 `research-loop/ARCHITECTURE.md` 2026-08-18 gyb 裁掉不写（`00` 定稿：定稿的拆分文档本身就是架构说明），插件目录里没有它。不加 `workflows/`：派活是每张单各起一个 subagent（`04`），不需要扇出脚本，加了就是第二套派活机制。

## 五、入口 skill 干哪三件事

入口 skill 只干三件事：init、迁移提醒、领路。SKILL.md 里明写「本 skill 不干别的」。

入口 skill 只许 gyb 手动调用，永远不许模型或其他东西调用。候选机制是 skill 头部声明禁止模型调用，这条还没测，测法和失败备案在 `30-build-steps-verify-tests.md`（待验证第 4 条）。2026-08-17 随 `05` 定稿裁：第 4 条的失败备案「`rl init` 检查调用者状态文件不是任何角色」升正案，`rl init` 只在裸终端跑，见第一节。

领路是几条常见路线图，头几条是：

1. 一批结果出来之后先开 analysis 出数再开 idea 落决定。
2. 新想法先开 idea 落决定再派工单。
3. 结果不对先开 reviewer。
4. 只想先跑一把看数、不打算留决定和报告的，gyb 直接点快车道；其余走正常路。
5. 定期收拾（gyb 自己定期开工，没有提醒机制——桌面通知与定期提醒 2026-08-21 裁掉不做，定义处 `01`）：`rl status`、`rl reclaim` 看列表、`--apply`、按 owner 逐个拉起、`rl doctor`。

加载角色的动作是 gyb 在终端里 `/` 加角色 skill 名。

## 六、迁移的规矩

迁移是搬文件，不是登记指向。理由是写权钩子按路径拦，文件不搬，这条拦截就只覆盖新写的代码，老代码全在钩子外面。

new1 的老代码由 gyb 手动按需搬（2026-08-16 晚裁，全量搬的 workflow 作废）。入口 skill 不做全量搬迁的 workflow，只在 deploy 的报告里列出「这次改了哪些 experiments/ 外的文件」时提醒 gyb 搬。研究仓库代码量小，搬得动。

老代码要不要搬进 `experiments/` 由 gyb 手动定，deploy 只提醒。

## 七、new1 宿主对接

### 7.1 GPU 铁律对 run 会话怎么读

new1 的 CLAUDE.md 现在写的是「任何要用显卡跑的程序一律走 gpu-run skill，禁止绕过」。run 角色照 `.claude/skills/gpu-run/SKILL.md` 写，能力至少覆盖 gpu-run 的全生命周期，所以加载了 run 角色的会话以 run 的 SKILL.md 为准，它是 gpu-run 的超集，宿主 GPU 铁律里的「唯一入口」对 run 会话读作 run skill。这句话两处都要有：init 追加的那一节里有一句，new1 原来那一行由 gyb 亲手改。

### 7.2 loop/ 进脏树白名单

`loop/*.jsonl` 和 `loop/.lock` 不算脏树。这条落在 new1 的两个地方：宿主 CLAUDE.md 那一行由 gyb 亲手改（7.9）；`run.py` 门禁代码里那张白名单加上这两样，归施工步 7 的交付——施工者改，是 new1 自己的代码改动，按 new1 自己的规矩走（改代码和注册表同一个 commit、`selfcheck` 过），gyb 验收；`rl init` 不碰宿主代码（2026-08-18 gyb 裁）。白名单按 `loop/*.jsonl` 字面照旧，`loop/.doctor-acks.jsonl` 顺带不算脏、ack 之后可以直接发射；`03` 说账本总规矩不管 ack 文件，只是说它不受账本约束，不是说门禁要拦它（2026-08-18 gyb 裁，sync-inbox 问题 32，原话「a」）。

### 7.3 两本 runs 账并存

插件的 `loop/runs.jsonl` 和宿主的 `ops/runs.jsonl` 在 new1 里并存：前者是插件的正账，后者是宿主发射器自己的登记。两本不合并，doctor 有一项对账，扫「`loop/runs.jsonl` 与宿主 `ops/runs.jsonl` 对不上的 run_id」。

宿主发射器 `run.py launch` 写 `ops/jobs.json`、`ops/runs.jsonl`、`RUNMETA.json` 这三个文件是 Bash 写入，钩子不看，不算越权。

### 7.4 record finish 由 rl run finish 调

`rl run finish` 同时调宿主发射器的收尾命令，new1 是 `run.py record finish`，命令模板在配置的 `launcher.finish_cmd` 里。退出状态是 ok 还是失败都调，两本账一次落。Phase 6b 的两种中断（跑挂、被收回或被 reclaim `--kill`）也照样调；中断收尾里「宿主销号」那一步另调 `launcher.abort_cmd`，new1 是 `run.py gpu-jobs finish`（第二节；杀进程和释放显存由 run 自己做，见 `12`）。

### 7.5 TIMELINE、DATA、RESULTS 角色不碰

宿主自己的四层记录是 `TIMELINE.md`、`DATA.md`、`RESULTS.md`、`ops/runs.jsonl`。角色一律不碰这四样，只有 `rl run finish` 经宿主收尾命令模板往 `ops/runs.jsonl` 落数字。TIMELINE 和 DATA 由 gyb 手动补。这四样加 `ops/jobs.json` 就是 new1 在配置 `host_ledgers` 里列的五项（第二节），`ops/runs.jsonl` 那项 `kind: runs`，doctor 对账（7.3）按它找宿主 runs 账。

### 7.6 probe-pipeline 与 run.py 注册表

deploy 改到 `experiments/` 外的宿主文件（仓库根 `run.py` 的注册表、`MAP.md`、`ops/` 里的东西）钩子不拦，纪律是三条：改动列进部署报告带文件的那一份；在 `decisions.deploy.jsonl` 留一条来源指向那个文件；宿主仓库自己对这些文件的规矩照守。new1 的规矩就是 CLAUDE.md 里的 probe-pipeline skill 和 run.py 注册表三件套。三条纪律的完整写法在 `11-role-deploy.md`。

### 7.7 产物根指到 net 盘

原始数据不新建目录，走配置里的 `artifact_root`，在 new1 指到 net 盘。

### 7.8 快车道在 new1 的宿主动作

快车道里 GPU 照旧走宿主发射器：宿主的台账照登记，`record finish` 的结论栏写 `quick_lane` 加标签，track 沿用被微调的那个实验的方向。这几条属于快车道，详见 `07-quick-lane.md`。

### 7.9 gyb 要亲手改的两处、施工要改的一处

new1 CLAUDE.md 的两处宿主改动由 gyb 亲手改，时机是施工步 7 跑完 `rl init` 之后：

1. GPU 铁律那一行，改成对 run 会话的读法（见 7.1）。
2. 脏树白名单那一行，加 `loop/`（见 7.2）。

`run.py` 门禁代码里的白名单加 `loop/*.jsonl` 和 `loop/.lock`，由施工者在步 7 改、gyb 验收（见 7.2；2026-08-18 gyb 裁）。

步 7 的验收标准是：new1 的 `loop/` 长出来、CLAUDE.md 只多一节、`run.py` 门禁白名单多两样且 `selfcheck` 过（最后一项 2026-08-18 加，`30` 的步 7 交付清单要同步）。

## 和别的 part 的接口

本份是定义处的东西：`rl init` 建什么、init 问什么、init 重跑无副作用、init 不动宿主代码和仓库 `.claude/`；`research-loop.json` 的全部键（含 `launcher.abort_cmd`、`repo_run`、`host_ledgers`，2026-08-18 加）和阈值默认值表；九本账位置钉死在 `loop/`、配置里没有账路径；产物目录约定 `<artifact_root>/<run_id>/`；插件本体那棵树（含 `agents/` 层、插件级钩子文件放 `hooks/`）；入口 skill 的三件事和领路；迁移规矩；new1 宿主对接每一条（含 `run.py` 门禁白名单归施工步 7、gyb 亲手改的两处）。别的 part 提到这些只指过来。

- 九本账的文件名（`loop/decisions.<actor>.jsonl` 等九个）和每一行的字段、`loop/.doctor-acks.jsonl` 不归总规矩管：`03-ledgers.md`。本份第一节「钉死在 `loop/`」指的就是 `03` 词表那九个名字。
- `rl init` 这一行子命令的完整签名（只在裸终端跑、退出码 3）、`rl run finish` 的参数、doctor 的全部扫描项（含「两本 runs 账对账」那一项按 `host_ledgers` 里 `kind: runs` 找宿主账）：`05-rl-cli.md`。
- 钩子怎么挂（一份插件级钩子文件、判角色先 `agent_type` 后会话状态文件、会话状态文件由钩子写、匹配范围 Write/Edit/Bash、Bash 分支怎么解析路径、`hooks.path_allowlist` 怎么用）、角色 json 四栏、五份角色 agent 定义的名字和「只塑形不设闸」的写法：`06-hooks-and-permissions.md`。本份第四节 `hooks/`、`agents/` 两行只是目录清单，规矩本体在 `06`（2026-08-18 待验证第 8 条的结论要落到 `06`，见「要同步到别处的」）。
- 派活时用哪个 agent 类型起 subagent、`launched_by` 的取值：`04-handoffs-and-sessions.md`。
- `ql_tag` 的形状、快车道 worktree 怎么建、`rl ql open/close`、快车道在宿主的台账动作：`07-quick-lane.md`。
- run 角色照 gpu-run 写的八个阶段、看门狗、smoke 日志落 `artifact_root/smoke/`、中断收尾四步（`launcher.abort_cmd` 只管其中「宿主销号」一步）、`launcher.*` 留空时 run 怎么办：`12-role-run.md`。
- deploy 改宿主文件的三条纪律、部署报告两份的分工：`11-role-deploy.md`。
- analysis 的派生指标 `code_path` 指向 `analysis/common/metrics.py:<函数>`、`analysis_artifact_root` 怎么用：`13-role-analysis.md`。init 播的三样在本份第一节。
- grants 谁能写（只有 gyb；裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收）：`01-gyb.md` 第二节，`03-ledgers.md` grants 一段照它写。idea 申请 `read:notes` 的那条 issue 随获准机制 2026-08-21 砍掉（定义处 `10-role-idea.md`）；grants 账存废等最后一期（sync-inbox 问题 43）。
- 母版的 `rules_version` 和 feedback 采纳后改哪几个文件（角色 agent 定义是不是母版的一部分，归 `09`/`06` 定）：`09-common-and-feedback.md`。
- 待验证清单第 4 条（入口 skill 能不能锁成只许手动）、第 8 条（2026-08-18 已测，结论见「要同步到别处的」）、施工步 1、2、7 的交付与验收（步 7 交付加 `run.py` 门禁白名单）：`30-build-steps-verify-tests.md`。
- 十一条设计原则和文档索引：`00-overview.md`。本份 2026-08-18 的裁决对回的原则：init 幂等与钉死账路径对回原则 8（一处为准）；钩子挂法对回原则 2（第一层约束是硬的，subagent 也要过闸）；`agents/` 层不带钩子、init 不播文件对回原则 8；`launcher.abort_cmd` 对回原则 10/11（中断是尝试的一种结束，宿主销号要留痕）；`repo_run`、`host_ledgers` 对回原则 2（宿主的东西靠纪律，纪律要有具体落点）。

## 源文档没写清的（留给 gyb）

（2026-08-18 全部裁完：原第 1 至 4、6 至 10 条的裁决见文末「裁决记录」，第 5 条 2026-08-17 已销。）

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

以下条目照抄 `plans/2026-08-16-research-loop-simulation-round2.md`，不做判断、不改字。那份文件开头写明：16 个场景的摩擦全部是未经核实的模拟者原话，可能有误报。

### param-tweak（45 步，gyb 动手 8 次）

11. [slows/contradiction] 第 16、20 步：快车道说数字进杂账不进 runs 账，但 GPU「照旧走 gpu-run」，run.py launch 一条命令自动往宿主 ops/runs.jsonl 登记、Phase 6a 五连还要 record finish 把数字渲进 RESULTS.md；文档没说快车道要不要跑这一步
    - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:161; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:140
    - 改法：快车道那一段明写「宿主台账照登记，record finish 的 conclusion 写 quick_lane 加 ql_tag」

12. [slows/contradiction] 第 16 步：设计文档要求快车道发射时 track 一律填 quick_lane，gpu-run 要求 --track 和 TIMELINE.md 里的方向对得上，quick_lane 不是 TIMELINE 里的任何一条方向
    - 依据：plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:91
    - 改法：在 TIMELINE.md 里固定登记一条 quick_lane 方向，或者改成沿用被微调那个实验的 track

15. [slows/guessed] 第 7 步：快车道的 worktree 建在哪、分支叫什么名字文档一个字没写，deploy 只能自己编一个路径；同一天开第二条快车道时路径撞不撞也没人管
    - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:141
    - 改法：research-loop.json 加 quick_lane.worktree_root，路径和分支名都用 ql_tag 拼出来

### new-idea（39 步，gyb 动手 7 次）

8. [slows/ambiguous] 第 2 步和第 3 步：这个场景走正常路还是快车道两种读法都成立：领路卡片写着「新想法先开 idea 落决定再派工单」，快车道的典型情形又写着「一个想法还没成型先跑一把看看」，而进快车道只看 gyb 点不点名、明说不设别的判据，gyb 不点名的时候模型没有依据选
   - 依据：plans/2026-08-16-research-loop-next-steps.md:154; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：领路卡片加一句「只想先跑一把看数、不打算留决定和报告的，gyb 直接点快车道；其余走正常路」

11. [slows/missing] 第 15 步：new1 的探针代码没搬进 experiments/，deploy 改的是仓库根的宿主代码，插件只写了钩子放行加「列进报告并留决定」；宿主仓库 CLAUDE.md 要求扩展流水线必须从 probe-pipeline skill 进、代码与 run.py 注册表同一个 commit，两套规矩没有对接句，deploy 会绕过宿主的注册表
    - 依据：plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:132; plans/2026-08-16-research-loop-build-plan.md:10
    - 改法：deploy 的 SKILL.md 加一句「改 experiments/ 外的宿主文件时按宿主仓库 CLAUDE.md 的规矩走，new1 是 probe-pipeline 加 run.py 注册表」

13. [slows/missing] 第 39 步：插件的 loop/ 九本账和 new1 自己的四层记录（TIMELINE.md、DATA.md、RESULTS.md、ops/runs.jsonl）谁写谁不写只交代了 runs 一本两账并存，这次跑出来的数字要不要同时进 RESULTS.md、结论要不要补 TIMELINE 没人负责
    - 依据：plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:163
    - 改法：在 research-loop.json 里列一张宿主台账清单，明写角色一律不碰 TIMELINE/DATA/RESULTS，由 gyb 收尾时手动补

### plot-new-plan（17 步，gyb 动手 8 次）

13. [cosmetic/missing] 第 12 步（图和 notebook 落盘位置）：决定的来源里把 analysis/ 里的图当仓库内文件路径，init 又说原始数据走配置里的产物根；图和 notebook 进不进 git、多大算大产物要挪到产物根，两份文档都没划线。
    - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:107
    - 改法：在 research-loop.json 里加一个 analysis 产物根，明写小图和 notebook 进仓库 analysis/、大文件进产物根并在口径行里记路径。

### run-crash-midway（40 步，gyb 动手 4 次）

15. [cosmetic/missing] 第 6、27、30 步：崩溃分支下宿主那本账怎么收没写。build-plan.md:163 只在 Phase 6a 说明「数字进 loop/runs.jsonl，new1 的 ops/runs.jsonl 照旧由 run.py launch 写，两本并存」，:164 的 Phase 6b 完全没提宿主账，所以 r1 在 ops/runs.jsonl 里那条永远停在 `record start` 没有 finish，宿主的 RESULTS.md 缺一行。
    - 依据：plans/2026-08-16-research-loop-build-plan.md:163; plans/2026-08-16-research-loop-build-plan.md:164; plans/2026-08-16-research-loop-next-steps.md:148
    - 改法：Phase 6b 那一行补一句：`rl run finish --exit failed|killed` 的同时打宿主的 `python3 run.py record finish <run_id>`。

### n-launch-orders（58 步，gyb 动手 10 次）

2. [blocks/missing] 第 11 步：deploy 用什么起那个 workflow、workflow 定义文件放在插件树的哪里、5 张单号怎么分派给 5 个 subagent，三样都没写。插件本体的目录清单里只有 skills/common/tables/schemas/scripts/bin/hooks/monitors/tests，没有 workflows/ 或 agents/；待验证第 8 条的备案里出现过「workflow 里的 agentType 指向 agents/<role>.md」，但那只是备案，正文没定。这个场景的核心机制整个是猜的。
   - 依据：2026-08-16-research-loop-next-steps.md:68; 2026-08-16-research-loop-next-steps.md:150; 2026-08-16-research-loop-build-plan.md:196
   - 改法：在插件树里加一层 workflows/fanout.js（或 agents/<role>.md），明写 deploy 起 N 个 run 时把单号、batch、分到的卡逐个写进 subagent 提示。

18. [slows/too_heavy] 第 21 步：同一批数字要在两处各填一遍：先按宿主流水线 run.py record finish 写 ops/runs.jsonl，再 rl run finish 写 loop/runs.jsonl，两本并存不合并，谁对账没写。5 张单就是 10 次填数。
    - 依据：2026-08-16-research-loop-build-plan.md:163; 2026-08-16-research-loop-next-steps.md:148; .claude/skills/gpu-run/SKILL.md:143
    - 改法：让 rl run finish 顺带调宿主的 record finish（或反过来），一次输入两本账都落，doctor 加一条两本对账的扫描。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

3. [slows/missing] 第 17 步：正常路的 run_id 谁生成、按什么规则没写。快车道有 ql_tag 的形状规定（ql-20260816-01，兼作宿主要的 run_id，track 一律填 quick_lane），正常路只说 run_id「和产物目录名、tmux session、commit message 一致」，没说谁造、什么格式；发射单的 launch 子对象也只有 command / args / workdir，没有 run_id 和 track 两栏，而宿主 run.py launch 的 --run-id 和 --track 是必填。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:85
   - 改法：在 launch 子对象里加 run_id 和 track 两个必填字段，run_id 由 rl handoff open 时按 ho 号加日期自动生成。

4. [blocks/missing] 第 17 步：没写 loop/ 九本账进不进 git、要不要加进宿主的脏树白名单。new1 的门禁把 ops/jobs.json、ops/runs.jsonl、RESULTS.md、*.lock 排除在脏之外，loop/*.jsonl 不在里面；而每一条 rl 命令都在追加行，run 走到「发射前 commit」那一刻工作树必脏，要么把账本一起 commit 进去（发射前 commit 那一步禁止 --allow-dirty），要么被门禁拦住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:161; /home/y-guo/reproduce/new1/CLAUDE.md:36; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:54
   - 改法：rl init 时把 loop/*.jsonl 和 loop/.lock 一起加进宿主 run.py 的脏树白名单，并在 research-loop.json 里记一句账本入不入 git。

5. [slows/contradiction] 第 13 到 19 步：run 角色 skill 照 gpu-run 写、能力至少覆盖它的全生命周期，等于 GPU 活从 run skill 走；但 new1 的 CLAUDE.md 是「任何要用显卡跑的程序一律走 gpu-run skill，禁止绕过」，而 rl init 明写「往 CLAUDE.md 追加一节，追加不覆盖，new1 原有的规矩照旧」。两条都是工程内的规矩，原则 8 的「工程内为准」裁不动这一对。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:19; plans/2026-08-16-research-loop-build-plan.md:153; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-next-steps.md:22; /home/y-guo/reproduce/new1/CLAUDE.md:3
   - 改法：rl init 追加的那一节里明写一句「加载了 run 角色的会话以 run SKILL.md 为准，gpu-run 铁律对它不适用」，并同步改 new1 CLAUDE.md 第 3 行。

### idea-request-notes（15 步，gyb 动手 4 次）

6. [slows/too_heavy] 第 6 步到第 11 步整段：gyb 就坐在这个会话里说了句「你去读吧」，为了读一份 md 却要走 issue open、通知、grant add、issue reply、issue close 五个动作四行账。permission 第一版只有 read:notes 一种、grantee 是角色不是会话，所以批一次就永久覆盖整个 notes/，这套手续一辈子只有第一次有信息量，和「想法要快速、多次迭代」这条总目标对不上
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-build-plan.md:65
   - 改法：`rl init` 时问一次 gyb 要不要当场给 idea 发 read:notes，发了以后就不用走申请，没发才走 issue 那条路

### periodic-reclaim（27 步，gyb 动手 11 次）

15. [slows/missing] 第 1 步：定时提醒的失败备案是「入口 skill 加载时打印一行距上次 reclaim 几天」，可入口 skill 只许 gyb 手动调用，gyb 不主动加载就永远看不到这一行。备案落空的时候没有第二条路。
    - 依据：plans/2026-08-16-research-loop-build-plan.md:195; plans/2026-08-16-research-loop-next-steps.md:163; plans/2026-08-16-research-loop-next-steps.md:154
    - 改法：备案改成 rl status 的第一行打印距上次 reclaim 的天数，rl status 谁都能调、gyb 天天用。

16. [cosmetic/missing] 第 2、4 步：入口 skill 的领路清单里四条路线图都是做实验的路线，没有这条定期收拾的路线，gyb 收到提醒之后要凭记忆敲 status 和 reclaim 的顺序。
    - 依据：plans/2026-08-16-research-loop-next-steps.md:154; plans/2026-08-16-research-loop-build-plan.md:143
    - 改法：领路加一条「收到 7 天提醒 → rl status → rl reclaim 看列表 → --apply → 按 owner 逐个拉起 → rl doctor」。

### smoke-fails（44 步，gyb 动手 4 次）

6. [slows/missing] 步 33（第二次 smoke 通过后发射）：正常路的 run_id 谁定、怎么命名，文档没写。只有快车道写了 ql_tag 兼作宿主发射器要的 run_id、track 一律填 quick_lane。宿主 run.py launch 的 --run-id 和 --track 都是必填，new1 的规矩还要求 run_id 在产物目录名、tmux session、台账 name、commit message 四处一致，run 在这一步只能自己编一个，且 --track 要和 TIMELINE.md 的方向对得上，谁给这个值也没写。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:161; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：rl handoff open --type launch_order 时自动分配 run_id 写进 launch 子对象（形如 ho-0013-01），track 由 deploy 开单时必填。

## 裁决记录（日期）

- 2026-08-17：来自 `03-ledgers.md` 的裁决（gyb：「A」，路 A 是进 git、每次 commit 顺手带上），`loop/` 九本账进 git，不另设 commit 动作，`.gitignore` 不排除 `loop/`；第一节表里 `loop/` 那行补上，「没写清」第 5 条销掉（后面条目编号没重排）。统筹 session 同步。
- 2026-08-17 来自 `05-rl-cli.md` 定稿（`656c8a9`）的裁决（rl-hub 转来；gyb 原话「全推荐」「只要他不动目前的代码什么的就全推荐就行」「全都推荐，只要不影响正在跑的进程」「A」）：阈值表加 `lock.timeout_seconds` 默认 10 秒；`rl init` 读到会话状态文件拒收退出码 3、只在裸终端跑（待验证第 4 条备案升正案）；`loop/.doctor-acks.jsonl` 不算九本账、doctor 首次 `--ack` 时建、init 不建。对回原则 1、4、8。第一节、第三节、第五节照改。
- 2026-08-17 gyb 裁（sync-inbox 问题 4，原话「问题4 给8」，rl-hub 转来）：「产物目录是 `<artifact_root>/<run_id>/`」这条约定的定义处归本份第一节，`03`、`12`、`21`、`23` 只引。对回原则 8。
- 2026-08-17 来自 sync-inbox 问题 24 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「B」）：`loop/.doctor-acks.jsonl` 是普通文件，`03` 的账本总规矩（只增不改、锁、进 git、脏树白名单）不管它。第一节表里 `loop/` 那行照 `03` 补这一句。
- 2026-08-17 来自 sync-inbox 问题 27 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「3 不是，可以替我写」）：grants 在角色会话里 `--as-gyb --quote` 替 gyb 写也收。接口一节「grants 只收裸终端」那条改成「grants 谁能写（只有 gyb；裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收）」。
- 2026-08-18 来自 `00-overview.md` 定稿（`6ea0edc`，rl-hub-v4 传；gyb 原话「那些分的就是说明，总的没用」）：第五节「两处原文不一致」段插件目录要补的三样去掉 `ARCHITECTURE.md`，剩 `.claude-plugin/plugin.json`、`README` 两样。
- 2026-08-18 来自 sync-inbox 问题 32 的裁决（定义处 `06` 第三节 CLAUDE.md 三句与本份第六节，rl-hub-v4 落；gyb 原话「a」）：宿主白名单照旧 `loop/*.jsonl` 字面，`.doctor-acks.jsonl` 顺带不算脏；第六节那句后补说明，三句本身不改。对回原则 4。
- 2026-08-18 来自 `06-hooks-and-permissions.md` 定稿（`d430192`，rl-hub-v4 传；gyb 原话「有的时候会用到仓库外的东西，建议弄一个白名单，白名单下的文件都允许修改」「问题2现在就测一下」「让idea能写gyb」）：第三节阈值表加 `hooks.path_allowlist`（默认空）；第四节 hooks/ 行注已实测；第一节 `notes/` 行改「gyb 和 idea 写」。对回原则 2、8、3。
- 2026-08-18 来自 `06-hooks-and-permissions.md` 追裁（`f820504`，rl-hub-v4 传；gyb 原话「这个放到记忆那个文件夹下面可以吗。如果是tmp的话就弄个tmp的子文件夹」「a」）：会话状态文件放 `loop/.sessions/<session_id>.json`；第一节 `loop/` 行补 `rl init` 建 `loop/.sessions/` 并往 `.gitignore` 加一行；「读到会话状态文件就拒收」那句写上路径。对回原则 8。
- 2026-08-18 来自 `09-common-and-feedback.md` 定稿（`aaca3c9`，rl-hub-v5 传；gyb 原话「a」）：第四节插件树 `common/` 那行加「判断类检查问题清单 `REVIEW-CHECKLIST.md`」，`rules_version` 注「整数，`GLOBAL-RULES.md` 头部一行」。对回原则 8。
- 2026-08-18 gyb 裁（rl-part-08 会话，第 1 问，原话「第一个选 A」）：宿主中断的命令模板单独一个键 `launcher.abort_cmd`，跟另外三条同一组写法；宿主没有这条命令的仓库留空，留空就跳过；四条模板留空的语义一样。new1 值 `run.py gpu-jobs finish`。对回原则 10、11。第二节表加一行，7.4 补一句。
- 2026-08-18 gyb 裁（第 2 问，原话「第二个选 A 这个要 init 的时候问的」，形状按 gyb 前一句「我希望的是传递信息又能传递自然语言又有格式」）：「本仓库跑法」键 `repo_run`，固定三栏 `env`/`entry`/`notes`，每栏装自然语言或命令，机器不解析，init 时问 gyb 填。对回原则 2。第二节表加一行。
- 2026-08-18 gyb 裁（第 3 问，按同一句「有格式又能装自然语言」记，gyb 没另说）：「宿主台账清单」键 `host_ledgers`，列表、每项 `path`/`note`/`kind` 三栏，`kind: runs` 标宿主 runs 账给 doctor 对账；init 时问 gyb 填；new1 五项 `TIMELINE.md`、`DATA.md`、`RESULTS.md`、`ops/runs.jsonl`、`ops/jobs.json`，`RUNMETA.json` 不列。对回原则 2。第二节表加一行，7.5 补一句。
- 2026-08-18 gyb 裁（原第 4 条，原话「定死吧」）：九本账位置和文件名钉死在 `loop/` 下 `03` 词表那九个名字，配置里没有「各账路径」这一项。对回原则 8。第一节 `loop/` 行、第二节开头照改。
- 2026-08-18 gyb 裁（原第 6 条，原话「A A A」第一个 A）：`run.py` 门禁代码里的脏树白名单加 `loop/*.jsonl` 和 `loop/.lock` 归施工步 7 的交付，施工者改、按 new1 自己的规矩走、gyb 验收；`rl init` 不碰宿主代码；步 7 验收标准加一项。对回原则 2。7.2、7.9 照改，第一节加一段。
- 2026-08-18 gyb 裁（原第 7 条，「A A A」第二个 A）：init 往 `analysis/` 播三样：`analysis/common/metrics.py`（骨架加一个示例函数）、`analysis/common/ledger.py`（从 runs 账取数的辅助）、`analysis/scratch/` 空目录；notebook、画图风格、notebook 模板都不播。对回原则 8（`13` 的 `code_path` 形状有唯一落点）。第一节照改。
- 2026-08-18 gyb 裁（原第 8 条，「A A A」第三个 A）：`rl init` 重跑无副作用——已有的不动、缺的补、CLAUDE.md 那节不重复追加、打印「已存在跳过 / 这次新建」清单、退出码 0。对回原则 8。第一节加一段。
- 2026-08-18 gyb 裁（原第 9 条，按 A 记，gyb 未另说）：init 自带默认模板，阈值直接落默认值；跟仓库绑定的项逐项问 gyb，跳过的留空并列出，留空的命令模板对应动作跳过；重跑不再问已填的项。对回原则 8。第一节 `research-loop.json` 行、第二节表「init 问」栏。
- 2026-08-18 gyb 裁（原第 10 条，第一次答「A 然后现在就测 8」= 先不建、挂第 8 条；测完改裁）：待验证第 8 条当场测（八个变体，记录在 `~/.claude/jobs/caef83fb/tmp/verify8/RESULT.md`）。结论：skill 头部钩子只管顶层会话、subagent 不经过它，主案不成立；插件 `agents/` 里 agent 定义头部的钩子被 Claude Code 忽略（官方文档明写「plugin subagents don't support the hooks, mcpServers, or permissionMode frontmatter fields」），仓库 `.claude/agents/` 里的要仓库受信任才跑，备案一不成立；仓库 settings 级和插件级钩子对 subagent 生效，输入带 `agent_type`。gyb 采纳外部咨询意见裁（原话「剩下的建议我确认」）：钩子一份放插件级 hooks 文件；脚本先看 `agent_type`（认识的按角色、不认识的最严），没有才按会话状态文件查顶层会话角色；会话状态文件由同一份钩子文件里的一条钩子在加载角色 skill 时写（`agent_type` 非空不写）；skill 头部不再声明钩子、第 2 条的「参数报角色名」写法作废；插件 `agents/` 层要建，五份角色 agent 定义只塑形（提示词、预加载角色 skill、收窄工具面）不带钩子；派活一律用这五个类型起 subagent；init 不往仓库播 agent 文件、不动仓库 settings；不加 `workflows/`。对回原则 2、8。第四节表加 `agents/` 行、改 `skills/`、`hooks/` 两行、不一致段改写。
- 2026-08-18 gyb 裁（同一轮，原话「你就说我也定了，让统筹给06 00也改了」）：钩子匹配范围加 Bash（Bash 分支解析命令里的重定向、`tee`、`sed -i`、`mv`/`cp` 目标路径，自己 realpath），原则 2「钩子只管 Write 和 Edit」那句和 `06` 定稿的「Bash 绕钩子不许」纪律句要跟着改。定义处 `00`（原则）和 `06`（钩子），本份只在 `hooks/` 行记一句。
- 2026-08-21 来自 `01-gyb.md` 定稿（`cd569ab`，rl-hub-v5 传；gyb 原话「收件箱这个算了 先不做，就维护一个我要看的东西就行，我自己记得定期手动看」「那这个砍了吧」）：桌面通知与定期提醒这一版都不做——阈值表删 `notify.reminder_days` 一行；入口 skill 领路第 5 条触发词改成 gyb 自己定期开工，路线不变。对回原则 6。
- 2026-08-21 来自 `10-role-idea.md` 定稿（`96459b4`，rl-hub-v6 传；gyb 原话「砍掉，默认能读」「不用申请」）：`rl init` 的「要不要当场给 idea 发 `read:notes`」那一问随获准机制砍掉，第一节 init 问话段与接口一节照改。对回原则 2。

## 要同步到别处的

按 HANDOFF 四点五节，本份 2026-08-18 的裁决动到别的 part 的，一条一条列在这里；`03`/`04`/`05` 冻结三份只报不催。

1. `06-hooks-and-permissions.md`（定义处：钩子怎么挂、角色 json、会话状态文件、SKILL.md 纪律）：待验证第 8 条结论落地——(a) 角色 skill 头部不再声明钩子，「钩子脚本本身」一节「五个角色共用一个脚本、参数报角色名」改成「一份插件级钩子文件 `hooks/hooks.json`，脚本自己判角色：先 `agent_type`（认识的按角色、不认识的最严），没有才按 `loop/.sessions/<session_id>.json`」；(b) 会话状态文件由钩子文件里的一条钩子在加载角色 skill 时写、`agent_type` 非空不写；(c) 加一段「五份角色 agent 定义（`agents/<role>.md`）只塑形不设闸：提示词、预加载角色 skill、收窄工具面（reviewer 禁 Write/Edit 等按 use case 表倒推），不写钩子（插件 agent 忽略钩子字段）」；(d) 钩子匹配范围加 Bash，Bash 分支解析重定向、`tee`、`sed -i`、`mv`/`cp` 目标路径并 realpath；「Bash 绕钩子不许」那句 SKILL.md 纪律相应改（Bash 现在过闸，纪律句改成「钩子拦不到的写法一律不许」或删，`06` 定）；(e) 「读的纪律」不变。角色 agent 定义改动走不走母版流程归 `06`/`09` 定。（已同步 2026-08-18 rl-hub-v5：(a)(b)(c)(d)(e) 已改进 06；纪律句改法与 agent 定义走不走母版流程立 sync-inbox 问题 38 等 gyb）
2. `00-overview.md`（定义处：十一条原则）：原则 2「钩子只管 Write 和 Edit 两个工具」改成「钩子管 Write、Edit、Bash 三个工具」，「其余一切（Bash 写出来的文件……）靠 SKILL.md 的纪律」里去掉 Bash；2026-08-18 gyb 裁，原话「你就说我也定了，让统筹给06 00也改了」。第八节施工步骤一览、第九节索引里 `08` 的覆盖栏加「`agents/` 层」。（已同步 2026-08-18 rl-hub-v5）
3. `04-handoffs-and-sessions.md`（冻结，等最后一期）：`dispatch=auto` 起 subagent 时用插件的角色 agent 类型（名字 `06` 定），不用 general-purpose；第四节「登记」那句「subagent 加载角色 skill 那一刻和普通 session 一样登记进 sessions 账」要按 (b) 改——subagent 的 `session_id` 与父会话相同、钩子输入多 `agent_id`/`agent_type`，subagent 算不算一次 sessions 行、`session_id` 记什么，等待验证第 5 条测完再定（`04` 自己的事，本份只报事实）。（记 sync-inbox 问题 39，等最后一期，2026-08-18 rl-hub-v5）
4. `30-build-steps-verify-tests.md`：待验证第 8 条状态改「已测 2026-08-18：主案不成立、备案一不成立、走插件级钩子文件按 `agent_type` 判角色，见 `06`」；测试记录路径 `~/.claude/jobs/caef83fb/tmp/verify8/RESULT.md`；第 2 条的结论备注「参数报角色名写法已被第 8 条结论取代，脚本自己判角色」；「没写清」第 5 条（`workflows/` 或 `agents/` 层步 1 建不建）改「建 `agents/`，步 1 建空目录；不建 `workflows/`」；施工步 7 交付加「`run.py` 门禁白名单加 `loop/*.jsonl`、`loop/.lock`，`selfcheck` 过」、验收标准加同一项；步 1 交付加 `agents/` 五份。（已同步 2026-08-18 rl-hub-v5）
5. `05-rl-cli.md`（冻结，等最后一期）：`rl init` 一行补「重跑无副作用；逐项问配置；不动宿主代码和仓库 `.claude/`」；`rl run finish` 一节补「中断收尾里宿主销号调 `launcher.abort_cmd`，留空跳过」；doctor「两本 runs 账对账」那项按 `host_ledgers` 里 `kind: runs` 找宿主账；接口一节 `08` 那条的键清单加 `launcher.abort_cmd`、`repo_run`、`host_ledgers`。（记 sync-inbox 问题 39，等最后一期，2026-08-18 rl-hub-v5）
6. `12-role-run.md`：Phase 6b 中断收尾四步里「宿主销号」调配置的 `launcher.abort_cmd`（new1 `run.py gpu-jobs finish`），留空跳过；接口一节「中断命令模板」补键名；`launcher.*` 留空时 run 怎么办由 `12` 写一句。（已同步 2026-08-18 rl-hub-v5）
7. `13-role-analysis.md`：第 119 行「公共统计件由 init 播模板」补「三样：`analysis/common/metrics.py`、`analysis/common/ledger.py`、`analysis/scratch/`，见 `08` 第一节」。（已同步 2026-08-18 rl-hub-v5）
8. `03-ledgers.md`（冻结，等最后一期）：词表九个文件名旁注一句「位置钉死，配置里没有账路径（2026-08-18 gyb 裁，`08` 第一节）」。（记 sync-inbox 问题 39，等最后一期，2026-08-18 rl-hub-v5）
9. `07-quick-lane.md` 接口一节：「宿主发射器的命令模板（探卡、发射、收尾、中断）与宿主台账清单」补键名 `launcher.abort_cmd`、`host_ledgers`。（已同步 2026-08-18 rl-hub-v5）
10. `09-common-and-feedback.md`：角色 agent 定义（`agents/<role>.md`）算不算母版的一部分、`rules_version` 覆不覆盖它，`09` 与 `06` 定；本份只报有这一层。（立 sync-inbox 问题 38 等 gyb，2026-08-18 rl-hub-v5）
11. `10`–`14` 五份角色 part：各自「加载方式」处加一句「被派活时以插件角色 agent 类型起 subagent，agent 定义预加载本角色 skill」（写法等 `06` 定稿后统一传）。（已同步 2026-08-18 rl-hub-v5：五份各加一句，agent 类型名照 `agents/<role>.md` 的文件名）
12. `01-gyb.md`：入口 skill 领路和 `rl init` 问答无变化；`rl status` 无变化。无需改，列此备查。（无需改，2026-08-18 rl-hub-v5 核）
