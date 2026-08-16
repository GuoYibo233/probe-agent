# 快车道

> 这份覆盖快车道（quick_lane）从头到尾：怎么进（gyb 点名、`rl ql open`、ql_tag 谁分、worktree 和分支、`--from`）、中间能做什么（deploy 那一头、analysis 那一头、GPU 走宿主发射器、track 怎么填、宿主台账登不登记、数字进杂账）、怎么出（`rl ql close --merged` 和 `--dropped`、合回时 gyb 亲自 merge、deploy 补一张标了 quick_lane 的工单、只要一份 method 简报、补一条 decisions.deploy、正式重跑挂在补单上），加杂账（scratch）的行格式、快车道在 `rl status` 和 `rl reclaim` 和 `rl doctor` 里的位置、两个阈值。
> 不覆盖的：deploy 这个角色本身的写权、自决、部署报告两份的分工在 `11-role-deploy.md`，analysis 的口径账和分析单在 `13-role-analysis.md`，九本账的完整行格式（含 handoffs 和 scratch 的每个字段）在 `03-ledgers.md`，派活单七个状态与完整转移表在 `04-handoffs-and-sessions.md`，rl 的完整命令表和退出码在 `05-rl-cli.md`，钩子拦什么与角色 json 四栏在 `06-hooks-and-permissions.md`，`research-loop.json` 的配置项和宿主发射器怎么对接在 `08-trees-init-and-host.md`，`rl status` 十段与 `rl reclaim` 的全部行为在 `01-gyb.md`，正常路的发射单怎么开怎么跑在 `12-role-run.md` 和 `21-pair-deploy-run.md`。
> 源：设计文档的原则 7、「快车道」一节、deploy 一节、analysis 一节、账本一节的 scratch 与锁那两段、「入口 skill 与代码迁移」的领路一句；施工计划第一节第六轮改动 (f)、第二节词表、第三节 handoffs 与 scratch、第四节转移表的快车道两行、第五节 deploy 与 analysis 的 use case、第六节 `rl ql`／`rl scratch`／`rl handoff open` 三行与 status、reclaim、doctor 三行、第八节阈值表、第十节测试 16 与测试 4。

## 一、快车道是什么，什么时候进

快车道有明确的进和出，进出都是账上的一行（原则 7）。进是 gyb 点名之后 `rl ql open`，出是 `rl ql close`，中间的一切都在 worktree 和杂账里。

快车道不是 deploy 专属。analysis 想先画一张图给 gyb 看，走的是同一条。

进快车道由 gyb 点名，口头就行，不设别的判据。典型情形三种：决定不动只微调代码；一个想法还没成型先跑一把看看；gyb 想先看一眼图再定要不要正式算。

入口 skill 的领路卡片里对应的那一条原话是：「只想先跑一把看数、不打算留决定和报告的，gyb 直接点快车道；其余走正常路」。

快车道的东西一旦要进正账拿来复用，它就不是快车道了，得按正常路重跑。

## 二、进：`rl ql open`

命令是 `rl ql open [--role deploy|analysis] [--from ho-ID]`，谁能调写的是 deploy、analysis。

这一条命令做三件事：

1. 在锁里分配快车道标签 `ql_tag`，形如 `ql-20260816-01`。锁是 `loop/.lock` 一把全局文件锁，扫号、分配编号、追加三步在同一把锁里；ql_tag 和 run_id、batch 一样在锁里分，不许扫完号再排队写。
2. 建目录。deploy 的快车道在配置里的 `quick_lane.worktree_root` 下建 worktree，路径是 `quick_lane.worktree_root/<ql_tag>`，分支同名。analysis 的快车道不建 worktree，产物放 `analysis/scratch/<ql_tag>/`。
3. 往杂账（scratch）写开张的一行，status 是 `open`。

`--from ho-ID` 是另一条进法：把一张待干的工单转进快车道，rl 把那张工单标 `quick_lane`。

## 三、中间：deploy 能做什么

deploy 在 worktree 上改代码，自己小规模跑。

免掉的四样：不开发射单、不叫 run、不做分步计时、不写决定账。决定账那一条不是永远免掉——合回的时候要在补单里一并补一条 `decisions.deploy`，见第七节。

数字追加进杂账，不进 runs 账。追加用 `rl scratch add QL [--note ...] [--metric k=v]`。

worktree 在仓库外，钩子按研究仓库内的相对路径判，仓库外的路径一律放行，所以 deploy 在 worktree 里写什么钩子都不判。

## 四、中间：analysis 能做什么

gyb 只想先看一眼图的时候走这条：图落 `analysis/scratch/<ql_tag>/`，不开口径、不开分析单。

数字和图的记录同样追加进杂账。要引用或者复用这张图的时候，再补口径和分析单。

## 五、中间：GPU 走宿主发射器

快车道里的 GPU 照旧走宿主发射器。四件事写死：

- 快车道里 deploy 可以派 gpu-runner。这是 deploy 唯一能派 run 之外的对象，写进 deploy 角色 json 的 `dispatches_to`（run；gpu-runner，只在快车道）。deploy 的 reads 里 `ops/gpu_state.md` 那一项也是为这一步开的（快车道自己跑 GPU 时）。
- run_id 用快车道标签，也就是 ql_tag 本身。
- track 沿用被微调的那个实验的方向，不填别的值。
- 宿主的台账照登记，`record finish` 的结论栏写 quick_lane 加标签。

两处原文不一致：设计文档快车道一节写「数字追加进杂账，不进 runs 账」，施工计划第三节 runs 的 `run_id` 那一栏写「快车道用 `ql_tag`」，读起来快车道会往 runs 账落行。ql_tag 当 run_id 用这一点两份文档一致，不一致的是快车道要不要往 runs 账落一行，见文末第 2 条。

## 六、杂账（scratch）的行格式

杂账只有快车道写，只写三样事：开张、数字、关张。中间版格式松，只校验骨架和 `ql_tag`；`open`、`merged`、`dropped` 三版按表查必填。中间追加数字的每一版 `status` 仍是 `open`，不设第四态。analysis 和 reviewer 默认不读这本账。

主键是 `ql_tag`，同一条快车道的每一次写入是一个新版本。`status` 三取一：`open`、`merged`、`dropped`。`actor` 是 `deploy` 或 `analysis`。

| 这一版 | 必填 |
|---|---|
| `open` | `role`（`deploy` 或 `analysis`）、`worktree`（deploy）或 `dir`（analysis）、`base_commit`、`branch`（deploy） |
| 中间版（`status` 仍是 `open`） | 自由，建议 `note`、`metrics` |
| `merged` | `handoff_id` |
| `dropped` | `reason` |

公共骨架七样每一行都有（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`），格式在 `03-ledgers.md`。

查的两条命令：`rl scratch list [--status S]`、`rl scratch show QL`。

## 七、出：`rl ql close` 两条路

出快车道两条路，各是杂账上的一行：

- `rl ql close QL --merged --handoff ID`
- `rl ql close QL --dropped --reason`

合回这条路上，动作按这个顺序走。

gyb 亲自 merge 主分支。deploy 只把命令交出来。

deploy 补一张标了 quick_lane 的工单，六条规矩：

1. `from_role` 和 `to_role` 都是 deploy。
2. 验收人固定是 gyb。
3. 允许新建直接进「干完等待验收」（`done_pending_review`），不经 `todo` 和 `in_progress`。
4. 只要一份不带文件的简报（`report_paths.method`），带文件的那一份（`detail`）用杂账里的记录顶替。
5. 解释栏（`explanation`）由 deploy 写，并且抄一句 gyb 点名的原话。
6. 同时补一条 `decisions.deploy` 记这次改动。

对应的两行转移表（施工计划第四节）：

| 从 | 到 | 谁能写 | 前提 | 之后谁拉起 | 子命令 |
|---|---|---|---|---|---|
| （新建） | `done_pending_review` | `deploy`（快车道补单，owner 记 gyb） | `quick_lane` 为 true，`report_paths.method` 存在，`explanation` 非空，关联的 scratch 行状态是 `merged` | 无（等 gyb 验收，只有 gyb 能 accept） | `handoff open --quick-lane` |
| `done_pending_review` | `accepted` | owner；快车道补单只有 gyb | 无；gyb 越过 owner 时 rl 给 owner 发 `fyi` | 无 | `handoff accept` |

开单命令带的三个旗子是 `--quick-lane --report-method P --ql QL`。

两处原文不一致：设计文档快车道一节写补单的 `from_role` 和 `to_role` 都是 deploy，施工计划第二节词表写「owner（开单角色，就是 `from_role`）……快车道补单和 gyb 开的单 owner 记 `gyb`」，转移表那一行也写「谁能写 deploy（快车道补单，owner 记 gyb）」。按施工计划的表为准：写这一行的是 deploy，owner 记 gyb。

主分支上永远只有走过工单的代码。

合回之后要正式数字，按正常路再开发射单跑一遍。那张发射单的父单（`parent_id`）就是这张快车道工单。`rl doctor` 有一项扫描是「快车道工单已 accepted 但没有关联发射单」。

快车道补单自己的 `parent_id` 是空的。

## 八、快车道在 status、reclaim、doctor 里的位置

没关掉的快车道出现在 `rl status` 里，在段 9（review/ 最近的清单、活着的会话含 focus、没关的快车道）。

`rl reclaim` 把超期的快车道也列进来：列出超过阈值没动的会话、单子和快车道，`--apply` 才动手。

`rl doctor` 那一项是「快车道工单已 accepted 但没有关联发射单」。

## 九、阈值

| 键 | 默认值 | 用在哪 |
|---|---|---|
| `quick_lane.worktree_root` | `<仓库>/../<仓库名>-ql/` | 快车道 worktree 建在哪 |
| `reclaim.ql_idle_days` | 7 | 快车道超过 7 天没关列进 reclaim |

两个键都写进 `research-loop.json`，gyb 可改。

## 和别的 part 的接口

- handoffs 的 `quick_lane` 布尔、`report_paths` 的 `{"method":...,"detail":...}` 形状、`explanation`、`parent_id`、`code_paths` 各自的必填规则：`03-ledgers.md`。
- scratch 每个字段的类型和公共骨架七样：`03-ledgers.md`。
- 派活单七个状态的全名与完整转移表（本份只抄了快车道相关的两行）：`04-handoffs-and-sessions.md`。
- `rl ql open/close`、`rl scratch add/list/show`、`rl handoff open --quick-lane`、`rl handoff accept` 的完整参数与退出码：`05-rl-cli.md`。
- 锁 `loop/.lock` 的三步合一规矩、跨账写序：`03-ledgers.md`。
- 钩子只按仓库内相对路径判、仓库外路径一律放行：`06-hooks-and-permissions.md`。
- deploy 角色 json 的四栏（含 `dispatches_to` 里的 gpu-runner、reads 里的 `ops/gpu_state.md`）：`06-hooks-and-permissions.md` 和 `11-role-deploy.md`。
- `quick_lane.worktree_root`、`reclaim.ql_idle_days` 两个键在配置文件里的位置，宿主发射器的命令模板（探卡、发射、收尾、中断）与宿主台账清单：`08-trees-init-and-host.md`。
- `rl status` 十段每段列什么、桌面通知推送表、`rl reclaim` 的全部参数与行为、`rl doctor` 的全部扫描项：`01-gyb.md`。
- 正式重跑那张发射单怎么开、attempt 怎么记、run 怎么接：`11-role-deploy.md`、`12-role-run.md`、`21-pair-deploy-run.md`。
- `decisions.deploy` 的来源三类与自决的粒度：`02-decisions.md`、`11-role-deploy.md`。
- analysis 的口径账、分析单、`analysis/scratch/` 目录：`13-role-analysis.md`。
- 入口 skill 的领路卡片全文：`08-trees-init-and-host.md`。
- 十一条设计原则原文（原则 7 是这一份的根）：`00-overview.md`。
- 测试 16（快车道）、测试 4 里快车道补单那两句：`30-build-steps-verify-tests.md`。

## 源文档没写清的（留给 gyb）

1. analysis 的快车道 scratch 开张版怎么填：第三节写 `open` 版必填 `worktree`（deploy）或 `dir`（analysis）、`base_commit`、`branch`，可 analysis 的快车道既不建 worktree 也不建分支，`base_commit` 和 `branch` 两栏对 analysis 填什么没写。（2026-08-17 按 `03-ledgers.md` 的裁决，`branch` 已改成只对 deploy 的 `open` 版必填；analysis 的 `base_commit` 填什么、要不要 `branch`，03 交这一份裁。）
2. 快车道要不要往 runs 账落一行：设计文档写「数字追加进杂账，不进 runs 账」，施工计划第三节 runs 的 `run_id` 那一栏写「快车道用 `ql_tag`」。两句同时成立推不出结论。
3. 快车道补单的报告目录取什么名：设计文档写部署报告放「experiments/ 下这张工单自己的目录」，而快车道补单是新建直达 `done_pending_review`、开单那一刻才分配单号，前提又要求 `report_paths.method` 已经存在。目录名在拿到单号之前取不出来。
4. 快车道补单要不要 `code_paths`：第三节写 `work_order` 进 `done_pending_review` 时 `code_paths` 必填，第四节快车道那一行的前提只列了 `quick_lane`、`method`、`explanation`、scratch `merged` 四条，没列 `code_paths`。两处对补单要不要这一栏没说到一起。
5. analysis 走 `--merged` 时补哪张单：`rl ql close --merged --handoff ID` 对 analysis 也开着，可补单的六条规矩整段写的是 deploy 的 `work_order`（deploy 开给 deploy、只要 method 简报、补一条 `decisions.deploy`）。analysis 合回要补哪一种单、谁开、交付物是什么，两份源文档都没写。
6. `--from ho-ID` 转进快车道之后那张工单怎么走：第六节命令表写 `--from` 把待干工单标 `quick_lane`，第四节转移表里没有「`todo` 的工单转 `quick_lane`」这一行；标完之后单子还在 `todo`、谁接、出快车道时是复用这张单还是另补一张，都没写。
7. gpu-runner 那一段的规矩：写了 deploy 在快车道里可以派 gpu-runner，可 gpu-runner 起来之后要不要登记 sessions 账、写不写杂账、宿主发射器要的 `--run-id` 和 `--track` 由谁往命令里填，没写。
8. merge 之后 worktree 和分支怎么处置：合回由 gyb 亲自 merge，merge 完那棵 worktree 和那条同名分支删不删、谁删，没写；`--dropped` 那条路上同样没写。
9. 补单一并补的那条 `decisions.deploy` 来源填什么：决定来源的 `file` 类要求仓库里的文件路径且路径不存在拒收，快车道改的文件在 worktree 里，主树同路径的内容是旧的，填哪棵树的路径没写。
10. 快车道的 scratch 行归哪条研究线：handoffs 有 `line`（由 rl 从 `decision_refs` 第一项的 `root_id` 算），scratch 行没有这一栏，`rl status --group-by line` 怎么把没关的快车道归进某条线没写。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

以下条目从 `plans/2026-08-16-research-loop-simulation-round2.md` 原样抄来，不做判断、不改字。那份文件开头写明：模拟者原话，未经核实者和 critic 核实，可能有误报。

### param-tweak（45 步，gyb 动手 8 次）

3. [slows/blocked] 第 25、26 步：部署报告要放「experiments/ 下这张工单自己的目录」，而快车道补单是新建直达 done_pending_review、开单时才分配单号，开单又硬要求两份报告路径已经存在，目录名在拿到单号之前取不出来
   - 依据：plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-build-plan.md:82; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：明写快车道补单的报告目录用 ql_tag 命名（experiments/ql-20260816-01/），单号事后不改目录

4. [slows/contradiction] 第 25 步：同一段里先说快车道「不写两层部署报告」，又说合回时补的那张工单要附两份部署报告路径且路径必须存在，等于把免掉的手续原样搬到出口
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:82; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：快车道补单只要一份 method 简报，detail 允许用杂账里那几行 ql_tag 记录顶替

5. [slows/principle_violation] 第 44 步：违反原则 7（快车道有明确的进和出）和原则 6（进出对称）：进有 rl scratch add 登记，出没有任何登记通道——scratch 只有 add 和 list、行里没有状态字段，handoffs 又没有 ql_tag 字段，rl status 的「没合回的快车道 worktree」这一段永远消不掉
   - 依据：plans/2026-08-16-research-loop-build-plan.md:141; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-next-steps.md:21
   - 改法：加 `rl scratch close --tag QL --handoff ID`，status 按有没有 close 行判断合没合回

6. [slows/contradiction] 第 26、27 步：词表和 idea 一节定死 work_order 是 idea 开给 deploy、owner 就是 from_role、验收人是 owner，但快车道补单写在 deploy 的 ledger_writes 里由 deploy 自己开，成了 deploy 开给 deploy、deploy 验收自己的报告
   - 依据：plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-next-steps.md:122; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：明写快车道补单 from_role=deploy、to_role=deploy 且验收人固定为 gyb，入账脚本对这一种单子拒收 deploy 自己 accept

7. [slows/too_heavy] 第 23 到 43 步：改一个学习率的出口是全套正常路：补工单加两份报告、开发射单、起 run subagent、分步计时、runs 账两版、两次验收，整条路 45 步、gyb 亲自动 8 次，和「想法要快速、多次迭代」的目标打架
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：允许快车道合回后把那次杂账里的数字补成 runs 账一行（标 quick_lane 来源），只有 gyb 点名要正式数字时才重跑

9. [slows/contradiction] 第 10 步：快车道说「中间的一切都在 worktree 和杂账里」，免掉的四样里没有决定账；但 deploy 一节说超参取值算自决必须进 decisions.deploy，规矩 2 又是硬的，两种读法都说得通，deploy 不知道该不该写这条决定
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:60; plans/2026-08-16-research-loop-build-plan.md:246
   - 改法：快车道那一段补一句「不写决定账，合回时在补单里一并补一条 decisions.deploy」

11. [slows/contradiction] 第 16、20 步：快车道说数字进杂账不进 runs 账，但 GPU「照旧走 gpu-run」，run.py launch 一条命令自动往宿主 ops/runs.jsonl 登记、Phase 6a 五连还要 record finish 把数字渲进 RESULTS.md；文档没说快车道要不要跑这一步
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:161; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:140
   - 改法：快车道那一段明写「宿主台账照登记，record finish 的 conclusion 写 quick_lane 加 ql_tag」

12. [slows/contradiction] 第 16 步：设计文档要求快车道发射时 track 一律填 quick_lane，gpu-run 要求 --track 和 TIMELINE.md 里的方向对得上，quick_lane 不是 TIMELINE 里的任何一条方向
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:91
   - 改法：在 TIMELINE.md 里固定登记一条 quick_lane 方向，或者改成沿用被微调那个实验的 track

13. [slows/ambiguous] 第 12 到 16 步：快车道里 GPU「照旧走 gpu-run」，gpu-run Phase 4 明写发射环节整段派 gpu-runner agent、不在主对话手搓，但 deploy 的 dispatches_to 只有 run，派 gpu-runner 算不算越权没写
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:58; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：deploy 的 dispatches_to 加 gpu-runner 并注明只在快车道用，或明写快车道 deploy 自己发射

14. [slows/ambiguous] 第 10 步：决定来源的 file 类要求「仓库里的文件路径」且路径不存在拒收，快车道改的文件在 worktree 里，主树同路径存在但内容是旧的，填哪个路径、校验查哪棵树两种读法都成立
   - 依据：plans/2026-08-16-research-loop-build-plan.md:43; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:205
   - 改法：file 类来源允许带 worktree 或 commit 前缀，校验按给出的那棵树查存在

15. [slows/guessed] 第 7 步：快车道的 worktree 建在哪、分支叫什么名字文档一个字没写，deploy 只能自己编一个路径；同一天开第二条快车道时路径撞不撞也没人管
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:141
   - 改法：research-loop.json 加 quick_lane.worktree_root，路径和分支名都用 ql_tag 拼出来

16. [cosmetic/missing] 第 8 步：ql_tag 由调用者用 --tag 手填，谁分配这个 01 序号、撞了怎么办没写；锁那一段只保证自动编号的账不撞号
   - 依据：plans/2026-08-16-research-loop-build-plan.md:141; plans/2026-08-16-research-loop-next-steps.md:92
   - 改法：加 `rl scratch new` 由 rl 在锁里分配 ql_tag 并打印出来

18. [cosmetic/missing] 第 26 步：work_order 的 explanation 定义成「idea 自己写的解释」且是必填，快车道全程没有 idea 会话，这段解释谁写、写什么没写
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:48
   - 改法：补一句：快车道补单的 explanation 由 deploy 写，注明来自 gyb 口头点名并抄一句原话

19. [cosmetic/ambiguous] 第 24 步：「gyb 看着行就合回主分支」这句的主语是 gyb，但 deploy 用 Bash 做 merge 钩子也不拦，谁执行 merge 两种读法都成立
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:132
   - 改法：明写 merge 由 gyb 亲自打，deploy 只把命令交出来

21. [cosmetic/ambiguous] 第 21 步：杂账「跑出来的数字继续追加」，但 scratch 的主键是什么没写：是同一个 ql_tag 追加一版，还是每跑一次开一行新 id，两种读法都成立
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:55
   - 改法：scratch 的主键定为 ql_tag，每跑一次追加一版

### new-idea（39 步，gyb 动手 7 次）

8. [slows/ambiguous] 第 2 步和第 3 步：这个场景走正常路还是快车道两种读法都成立：领路卡片写着「新想法先开 idea 落决定再派工单」，快车道的典型情形又写着「一个想法还没成型先跑一把看看」，而进快车道只看 gyb 点不点名、明说不设别的判据，gyb 不点名的时候模型没有依据选
   - 依据：plans/2026-08-16-research-loop-next-steps.md:154; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：领路卡片加一句「只想先跑一把看数、不打算留决定和报告的，gyb 直接点快车道；其余走正常路」

9. [slows/too_heavy] 整条路：「探针输入从最后一层换成中间层」这一句话的改动，正常路要走 2 张派活单、3 个嵌套会话、2 份部署报告、至少 9 次 rl 写账，和「想法要快速、多次迭代」这条总目标对不上；唯一的减负出口快车道每次都要 gyb 当场点名
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给 work_order 加一个 --light 档只要一份 detail 报告，或者明写「同一条决定的第二次及以后的参数微调默认走快车道」

### plot-new-plan（17 步，gyb 动手 8 次）

2. [slows/too_heavy] 整条路（第 1 步到第 17 步）：gyb 只想看一眼图，按文档要走 2 次 eval propose、2 次 approve、1 次 handoff open、start、done、accept 共 8 次写账，gyb 本人要介入 8 次；快车道只给 deploy，analysis 没有对应的轻路，和目标里「想法要快速、多次迭代」对不上。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：给 analysis 加一条 gyb 点名的快车道：图先落杂账不开口径不开单，图要被引用或复用的时候再补口径和分析单。

### run-crash-midway（40 步，gyb 动手 4 次）

11. [slows/too_heavy] 第 16 到 20 步：deploy 改完一行超参之后，没有任何办法自己确认修对了：next-steps.md:58 明写 deploy 不跑 smoke，快车道要 gyb 点名才能进（next-steps.md:64），所以每一次修复都得走「起 run 会话 → 读档案 → 探卡 → 挑卡 → smoke → 填分步表 → 发射前 commit → 发射」全套；smoke 再挂就又是一条 issue 一轮循环。改一个 batch size 的代价和跑一个新实验一样。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：允许 deploy 在修 stuck 的发射单时不经 gyb 点名跑一次 smoke 规模的自测，结果写进杂账。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

8. [slows/too_heavy] 第 11、16、22 步：gyb 亲手接一张已经开出来的正式工单，手续和 subagent 走一模一样：必须开发射单、必须分步计时填 step_table、必须写两份部署报告（method 那份还要原样抄决定编号加版本）。想减手续只有快车道，可快车道的入口是「gyb 点名」加另开一棵 worktree 加 rl scratch add，转移表里也没有「已开出的工单转快车道」这一行，而且审读意见第 1、2 条已经明确否掉了按改动大小分档。gyb 亲自上手的场合反而最重，和「想法要快速、多次迭代」相反。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:178; plans/2026-08-16-research-loop-build-plan.md:82
   - 改法：转移表补一行「todo 的 work_order 由 gyb 改标 quick_lane」，改标之后免发射单和两份报告，只留 scratch 记录。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

6. [slows/too_heavy] 第 9、10、20、25 步：收件箱里每一条都要两跳才知道属于哪条线：issue 行只有可选的 handoff_id，要 issue show 再 handoff show；口径行只有自由文本 applies_to；scratch 行只有 ql_tag、worktree、base_commit。一条线一天挂三五条，早上第一眼就变成十几条命令。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：rl status 每行直接把这一行溯到的决定编号和线名打出来，别让 gyb 自己跳。

### periodic-reclaim（27 步，gyb 动手 11 次）

11. [slows/missing] 第 3、24 步：一条一周没动的快车道 worktree 没有出路。reclaim 只管会话和单子，scratch 账只有 add 和 list，设计文档写死出快车道只有合回主分支补工单这一条路，放弃一条快车道没有命令，rl status 里那一行永远挂着，越攒越多。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:141
   - 改法：加 rl scratch retire --tag QL --reason，rl status 只列没 retire 的快车道，reclaim 把超期的快车道也列进来。

### smoke-fails（44 步，gyb 动手 4 次）

10. [slows/too_heavy] 步 19 到步 30（整个修复回路）：一个 import 报错要走完：落一条 issue、把单子标 stuck、run 会话销号、deploy 读 issue、改代码、回 issue、把单子拉回 todo、重起一个 run subagent、重读慢变量档案、重探空卡、重挑卡、重跑 smoke。至少八次账写入加两次会话生死。文档还把两条捷径都堵死了：run 不许自行重试，下游不许小修，快车道只能由 gyb 事先点名进、单子已经在正常路上时没有中途改走快车道的路。这和「想法要快速、多次迭代」的目标拧着。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:185; plans/2026-08-16-research-loop-next-steps.md:180; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给发射单加一条 smoke 失败专用短路：run 返回 traceback，deploy 在同一会话里就地修完打 rl handoff release 再起 run，issue 照开但不必等回复，并明写这不算 run 自行重试。

## 裁决记录（日期）

- 2026-08-17：来自 `03-ledgers.md` 的裁决（gyb：「可以」「可以 那就头尾查 中间不查」），scratch 中间版 `status` 仍是 `open`、不设第四态；校验头尾查中间不查（`open`、`merged`、`dropped` 三版按表查必填，中间版只查骨架和 `ql_tag`）；`branch` 改成 deploy 的 `open` 版必填。第六节两处照改。analysis 的 `base_commit`、`branch` 填什么留给本份「没写清」第 1 条。统筹 session 同步。
