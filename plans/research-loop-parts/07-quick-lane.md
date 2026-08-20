# 快车道

> 这份覆盖快车道（quick_lane）从头到尾：怎么进（gyb 点名、`rl ql open`、ql_tag 谁分、worktree 和分支、`--from`）、中间能做什么（deploy 那一头、analysis 那一头、GPU 走宿主发射器、track 怎么填、宿主台账登不登记、数字进杂账）、怎么出（`rl ql close --merged` 和 `--dropped`、合回时 gyb 亲自 merge、deploy 补一张标了 quick_lane 的工单、只要一份 method 简报、补一条 decisions.deploy、正式重跑挂在补单上），加杂账（scratch）的行格式、快车道在 `rl status` 和 `rl reclaim` 和 `rl doctor` 里的位置、两个阈值。
> 不覆盖的：deploy 这个角色本身的写权、自决、部署报告两份的分工在 `11-role-deploy.md`，analysis 的口径账和分析单在 `13-role-analysis.md`，九本账的完整行格式（含 handoffs 和 scratch 的每个字段）在 `03-ledgers.md`，派活单七个状态与完整转移表在 `04-handoffs-and-sessions.md`，rl 的完整命令表和退出码在 `05-rl-cli.md`，钩子拦什么与角色 json 四栏在 `06-hooks-and-permissions.md`，`research-loop.json` 的配置项和宿主发射器怎么对接在 `08-trees-init-and-host.md`，`rl status` 十段与 `rl reclaim` 的全部行为在 `01-gyb.md`，正常路的发射单怎么开怎么跑在 `12-role-run.md` 和 `21-pair-deploy-run.md`。
> 源：设计文档的原则 7、「快车道」一节、deploy 一节、analysis 一节、账本一节的 scratch 与锁那两段、「入口 skill 与代码迁移」的领路一句；施工计划第一节第六轮改动 (f)、第二节词表、第三节 handoffs 与 scratch、第四节转移表的快车道两行、第五节 deploy 与 analysis 的 use case、第六节 `rl ql`／`rl scratch`／`rl handoff open` 三行与 status、reclaim、doctor 三行、第八节阈值表、第十节测试 16 与测试 4。

## 一、快车道是什么，什么时候进

快车道有明确的进和出，进出都是账上的一行（原则 7）。进是 gyb 点名之后 `rl ql open`，出是 `rl ql close`，中间的一切都在 worktree 和杂账里。

总纲（2026-08-21 gyb 定，原则 7 的推论）：快车道期间的一切对主程序不存在——正账、主分支、正常流程都看不见它；验证好之后，出口那一刻一口气合并落账。中间不落正账，落账只发生在进出两行。

快车道不是 deploy 专属。analysis 想先画一张图给 gyb 看，走的是同一条。

进快车道由 gyb 点名，口头就行，不设别的判据。典型情形三种：决定不动只微调代码；一个想法还没成型先跑一把看看；gyb 想先看一眼图再定要不要正式算。

入口 skill 的领路卡片里对应的那一条原话是：「只想先跑一把看数、不打算留决定和报告的，gyb 直接点快车道；其余走正常路」。

快车道的东西一旦要进正账拿来复用，它就不是快车道了，得按正常路重跑。

## 二、进：`rl ql open`

命令是 `rl ql open [--role deploy|analysis] [--from ho-ID]`，谁能调写的是 deploy、analysis。

这一条命令做三件事：

1. 在锁里分配快车道标签 `ql_tag`，形如 `ql-20260816-01`。锁是 `loop/.lock` 一把全局文件锁，扫号、分配编号、追加三步在同一把锁里；锁里分配的编号包括 `ql_tag`、`run_id`（`batch` 是调用者自由文本，rl 不分配，2026-08-17 问题 9），不许扫完号再排队写。
2. 建目录。deploy 的快车道在配置里的 `quick_lane.worktree_root` 下建 worktree，路径是 `quick_lane.worktree_root/<ql_tag>`，分支同名。analysis 的快车道不建 worktree，产物放 `analysis/scratch/<ql_tag>/`。
3. 往杂账（scratch）写开张的一行，status 是 `open`。

`--from ho-ID` 是另一条进法：把一张待干的工单转进快车道。rl 把那张工单追加一版标 `quick_lane`，单子从此离开待干队列——正常流程不再派人接它、不占 holder；这张单就是出口的补单，不另开新单，出口怎么走见第七节（2026-08-21 gyb 裁，问题 6）。

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

gpu-runner 是宿主的东西，不进插件的账：不登记 sessions 账、不写杂账（2026-08-21 gyb 裁，问题 7）。deploy 把完整命令备好——`--run-id` 填 ql_tag、`--track` 填被微调实验的方向——交给 gpu-runner，gpu-runner 只管探卡和发射；跑完的数字由 deploy 自己追加进杂账。

快车道的数字追加进杂账，不进 runs 账（2026-08-17 gyb 裁，sync-inbox 问题 22；`03-ledgers.md` runs 表 `run_id` 那格原来写的「快车道用 `ql_tag`」已删）。ql_tag 当宿主发射器要的 run_id 用，这一点不变。

## 六、杂账（scratch）的行格式

杂账只有快车道写，只写三样事：开张、数字、关张。中间版格式松，只校验骨架和 `ql_tag`；`open`、`merged`、`dropped` 三版按表查必填。中间追加数字的每一版 `status` 仍是 `open`，不设第四态。analysis 和 reviewer 默认不读这本账。

主键是 `ql_tag`，同一条快车道的每一次写入是一个新版本。`status` 三取一：`open`、`merged`、`dropped`。`actor` 是 `deploy` 或 `analysis`。

| 这一版 | 必填 |
|---|---|
| `open` | `role`（`deploy` 或 `analysis`）；deploy 填 `worktree`、`base_commit`、`branch`，analysis 只填 `dir`——`base_commit`、`branch` 两栏对 analysis 不设（2026-08-21 gyb 裁，问题 1） |
| 中间版（`status` 仍是 `open`） | 自由，建议 `note`、`metrics` |
| `merged` | `handoff_id`：写序是先开补单拿到编号再 `rl ql close --merged --handoff ID`，补单那头的 `ql_tag` 栏反过来指这条 scratch 行，两边互指；`merged` 只对 deploy 的快车道开，analysis 的快车道只有 `dropped` |
| `dropped` | `reason` |

公共骨架七样每一行都有（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`），格式在 `03-ledgers.md`。

查的两条命令：`rl scratch list [--status S]`、`rl scratch show QL`。

## 七、出：`rl ql close` 两条路

出快车道两条路，各是杂账上的一行：

- `rl ql close QL --merged --handoff ID`
- `rl ql close QL --dropped --reason`

合回（`--merged`）只对 deploy 开；analysis 的快车道只有 `--dropped`，要把成果留下就走正常路重做（2026-08-17 gyb 裁，sync-inbox 问题 16）。

合回这条路上，动作按这个顺序走：gyb 亲自 merge，deploy 开补单拿到编号，再 `rl ql close --merged --handoff ID` 关杂账（2026-08-17 gyb 裁，sync-inbox 问题 8：先开补单，补单的前提是关联的 scratch 行状态还是 `open`，补单与 scratch 行两边互指）。

gyb 亲自 merge 主分支。deploy 只把命令交出来。

`rl ql close` 关张时把工作树和同名分支一并删掉，`--merged` 和 `--dropped` 两条路都删（2026-08-21 gyb 裁，问题 8）：合回的代码已经在主分支上，放弃的改动随分支一起没了，gyb 想留就在关张前自己处理；改动留下的记录只剩杂账那几行。关张即清干净，对应第一节总纲。

deploy 补一张标了 quick_lane 的工单，八条规矩：

1. `from_role` 和 `to_role` 都是 deploy。
2. 验收人固定是 gyb。
3. 允许新建直接进「干完等待验收」（`done_pending_review`），不经 `todo` 和 `in_progress`。
4. 只要一份不带文件的简报（`report_paths.method`），放在用快车道标签命名的目录里（`experiments/<ql_tag>/`），拿到单号之后目录名不改（2026-08-21 gyb 裁，问题 3）；带文件的那一份（`detail`）用杂账里的记录顶替。
5. 解释栏（`explanation`）由 deploy 写，并且抄一句 gyb 点名的原话。
6. `code_paths` 必填，列出这次改了哪些代码路径，要求和正常工单进 `done_pending_review` 时一样（2026-08-21 gyb 裁，问题 4）。
7. 同时补一条 `decisions.deploy` 记这次改动。file 类来源按普通规矩填主仓库路径：补决定发生在 gyb 合并之后，那时主树已经是新内容，路径存在、内容也对，不需要指定哪棵树的特殊写法（2026-08-21 gyb 裁，问题 9）。
8. 这条快车道修的东西是某个角色报上来的 issue 时（发射员报的运行报错是典型），合回时 deploy 回复并关掉那条 issue：发现者一方从收件箱看到修好了，卡住的单子照正常路回到待干，新拉起的发射员接着发。这不是快车道特例，是公共规矩「凡修的东西是账上报过的 issue，修完必须回复并关掉、不许静默修」（2026-08-21 gyb 立，定义处 `09-common-and-feedback.md`）落在快车道上的时点：回复发生在合回那一刻，因为合回之前快车道对主程序不存在、不算修好。

对应的两行转移表（施工计划第四节）：

| 从 | 到 | 谁能写 | 前提 | 之后谁拉起 | 子命令 |
|---|---|---|---|---|---|
| （新建） | `done_pending_review` | `deploy`（快车道补单，owner 记 gyb） | `quick_lane` 为 true，`report_paths.method` 存在，`explanation` 非空，`code_paths` 非空（2026-08-21 加，问题 4，`04` 冻结表未跟、在要同步的清单里），`ql_tag` 指的 scratch 行状态是 `open`（补单开完拿到编号再 `rl ql close --merged --handoff ID` 关杂账，两边互指） | 无（等 gyb 验收，只有 gyb 能 accept） | `handoff open --quick-lane` |
| `done_pending_review` | `accepted` | owner；快车道补单只有 gyb | 无；gyb 越过 owner 时 rl 给 owner 发 `fyi`；rl 顺带关这张单关联的 `answered` issue（`03` 定） | 无 | `handoff accept` |

开单命令带的三个旗子是 `--quick-lane --report-method P --ql QL`；`QL` 存进单子的 `ql_tag` 栏，和那条 scratch 行互指（字段在 `04-handoffs-and-sessions.md`）。

从待干转进来的单子（`--from`）不走上表「（新建）」那一行：出口合回时把原单追加一版直达 `done_pending_review`，前提同上表那一栏（简报、`code_paths`、`explanation`、和 scratch 行互指），验收人同样是 gyb，不另开新单，原有的决定引用照留；放弃时追加一版退回 `todo`、去掉 `quick_lane` 标（或 gyb 收回）。这两行 `04` 的转移表要补、子命令名归 `05` 定，都在要同步的清单里（2026-08-21 gyb 裁，问题 6）。

开单动作由 deploy 做，owner 记 gyb（2026-08-21 gyb 裁定稿：验收本来就是 owner 的职责，「已合并」的信息回到点名进快车道的 gyb 手里，也堵死 deploy 自己开自己收；「owner 就是开单角色」的通则要加这一句例外，通则在 `04-handoffs-and-sessions.md`，在要同步的清单里）。设计文档「`from_role` 和 `to_role` 都是 deploy」那句照旧成立，说的是谁干的活。

主分支上永远只有走过工单的代码。

合回之后要正式数字，按正常路再开发射单跑一遍。那张发射单的父单（`parent_id`）就是这张快车道工单。`rl doctor` 有一项扫描是「快车道工单已 accepted 但没有关联发射单」。

快车道补单自己的 `parent_id` 是空的；从待干转进来的单子保留它原有的引用。

## 八、快车道在 status、reclaim、doctor 里的位置

没关掉的快车道出现在 `rl status` 里，在段 9（review/ 最近的清单、活着的会话含 focus、没关的快车道）。按线分组看（`--group-by line`）的时候，没关的快车道不归任何一条研究线，单独列成一堆：杂账行不引决定、算不出线，也不加可选栏（2026-08-21 gyb 裁，问题 10）。

`rl reclaim` 把超期的快车道也列进来：列出超过阈值没动的会话、单子和快车道，`--apply` 才动手。

`rl doctor` 那一项是「快车道工单已 accepted 但没有关联发射单」。

## 九、阈值

| 键 | 默认值 | 用在哪 |
|---|---|---|
| `quick_lane.worktree_root` | `<仓库>/../<仓库名>-ql/` | 快车道 worktree 建在哪 |
| `reclaim.ql_idle_days` | 7 | 快车道超过 7 天没关列进 reclaim |

两个键都写进 `research-loop.json`，gyb 可改。

## 和别的 part 的接口

（2026-08-21 按定稿重写。标了「在要同步的清单里」的条目是本份裁的、定义处还没跟，落地前以本份为准。）

- handoffs 的 `quick_lane` 布尔、`report_paths` 的 `{"method":...,"detail":...}` 形状、`explanation`、`parent_id`、`code_paths`、`ql_tag` 各自的必填规则：`04-handoffs-and-sessions.md`（`03-ledgers.md` 的 handoffs 一段只指过去）。
- scratch 每个字段的类型和公共骨架七样：`03-ledgers.md`（`open` 版必填 2026-08-21 按问题 1 改成 deploy 三样、analysis 只 `dir`，在要同步的清单里）。
- 派活单七个状态的全名与完整转移表：`04-handoffs-and-sessions.md`（本份抄了快车道相关的两行；前提加 `code_paths`、`--from` 单的转进与出口两行是 2026-08-21 裁的，在要同步的清单里）。
- 「owner 就是开单角色」的通则与快车道补单「开单动作 deploy、owner 记 gyb」这条例外：`04-handoffs-and-sessions.md`（例外 2026-08-21 定稿，在要同步的清单里）。
- sessions 账本体：`04-handoffs-and-sessions.md`（宿主 gpu-runner 不登记 sessions 账是 2026-08-21 裁的，在要同步的清单里）。
- `rl ql open/close`、`rl scratch add/list/show`、`rl handoff open --quick-lane`、`rl handoff accept` 的完整参数与退出码：`05-rl-cli.md`（`rl ql close` 两条路都删工作树与分支、`--from` 标完单子离开待干、转进单出口那一步的子命令名，都是 2026-08-21 裁的，在要同步的清单里）。
- 锁 `loop/.lock` 的三步合一规矩、跨账写序：`03-ledgers.md`。
- 钩子只按仓库内相对路径判、仓库外路径一律放行：`06-hooks-and-permissions.md`。
- deploy 角色 json 的四栏（含 `dispatches_to` 里的 gpu-runner、reads 里的 `ops/gpu_state.md`）：`06-hooks-and-permissions.md` 和 `11-role-deploy.md`。
- `quick_lane.worktree_root`、`reclaim.ql_idle_days` 两个键在配置文件里的位置，宿主发射器的命令模板（探卡、发射、收尾、中断：`launcher.free_cmd`、`launcher.launch_cmd`、`launcher.finish_cmd`、`launcher.abort_cmd`）与宿主台账清单 `host_ledgers`：`08-trees-init-and-host.md`。
- `rl status` 十段每段列什么（桌面通知与推送表 2026-08-21 裁掉不做）、`rl reclaim` 的全部参数与行为、`rl doctor` 的全部扫描项：`01-gyb.md`（段 9 里没关的快车道不归线、按线分组时单独列一堆是 2026-08-21 裁的，在要同步的清单里）。
- 正式重跑那张发射单怎么开、attempt 怎么记、run 怎么接：`11-role-deploy.md`、`12-role-run.md`、`21-pair-deploy-run.md`。
- 快车道补单的报告目录用 `experiments/<ql_tag>/`、单号事后不改（2026-08-21 裁，在要同步的清单里）；部署报告目录约定本体：`11-role-deploy.md`。
- `decisions.deploy` 的来源三类与自决的粒度：`02-decisions.md`、`11-role-deploy.md`。
- 公共规矩「凡修的东西是账上报过的 issue，修完必须回复并关掉、不许静默修」（2026-08-21 gyb 立，在要同步的清单里）与 issues 的 reply/close 机制：`09-common-and-feedback.md`。
- analysis 的口径账、分析单、`analysis/scratch/` 目录：`13-role-analysis.md`。
- 入口 skill 的领路卡片全文：`08-trees-init-and-host.md`。
- 十一条设计原则原文（原则 7 是这一份的根，第一节总纲是它的推论）：`00-overview.md`。
- 测试 16（快车道）、测试 4 里快车道补单那两句：`30-build-steps-verify-tests.md`。

## 源文档没写清的（留给 gyb）

（2026-08-21 全部裁完：第 1、3、4、6、7、8、9、10 条的裁决见当日裁决记录，正文已改；第 2、5 条 2026-08-17 已销。此节清空。）

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
- 2026-08-17 来自 sync-inbox 问题 8 的裁决（定义处 `04`，rl-hub-v3 传；gyb 原话「A」）：快车道合回先开补单再关杂账。第七节「动作按这个顺序走」那句写实成「gyb 亲自 merge，deploy 开补单拿到编号，再 `rl ql close --merged --handoff ID` 关杂账」；第七节转移表补单那一行的前提照 `04` 改成「`ql_tag` 指的 scratch 行状态是 `open`」；开单旗子那句补「`QL` 存进单子的 `ql_tag` 栏，和那条 scratch 行互指」；第六节 scratch 表 `merged` 行照 `03` 补写序与互指。
- 2026-08-17 来自 sync-inbox 问题 9 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「A」）：`batch` 是调用者自由文本、rl 不分配。第二节锁那句照 `03` 改成「锁里分配的编号包括 `ql_tag`、`run_id`（`batch` 是调用者自由文本，rl 不分配）」。
- 2026-08-17 来自 sync-inbox 问题 16 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「A」）：analysis 的快车道没有补单。第七节两条路后面补一句「合回（`--merged`）只对 deploy 开；analysis 的快车道只有 `--dropped`，要把成果留下就走正常路重做」；第六节 scratch 表 `merged` 行同写；「没写清」第 5 条标已裁。
- 2026-08-17 来自 sync-inbox 问题 22 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「A」）：快车道数字不进 runs。第五节那段「两处原文不一致」改成「快车道的数字追加进杂账，不进 runs 账（`03` runs 表 `run_id` 那格的『快车道用 `ql_tag`』已删）」；「没写清」第 2 条标已裁。
- 2026-08-17 对齐定义处（不是新裁决，rl-hub-v3 传）：第七节转移表 `done_pending_review` → `accepted` 那一行照 `04` HEAD 补「rl 顺带关这张单关联的 `answered` issue（`03` 定）」；接口一节 handoffs 字段那条加 `ql_tag`、定义处改指 `04`（`03` 的 handoffs 一段只指过去）。
- 2026-08-17 rl-hub-v3 按 HANDOFF 第八节问题 16、22 两行的「销」：「源文档没写清的」第 2 条（快车道要不要往 runs 落一行）和第 5 条（analysis 走 `--merged` 补哪张单）已被裁决答掉，整条销掉，编号不重排（照 `08` 销第 5 条的先例）。
- 2026-08-18 来自 `08-trees-init-and-host.md` 定稿（`eb02403`，rl-hub-v5 传）：接口一节命令模板与宿主台账清单补键名 `launcher.abort_cmd`、`host_ledgers`。
- 2026-08-21（gyb，rl-part-07 定稿）总纲：快车道期间的一切对主程序不存在，验证好之后出口一口气合并落账（原话「对于主程序，快车道的东西在验证完之前是不存在的，验证好之后一口气合并到主要的地方」）。第一节补段。
- 2026-08-21 问题 1 裁 A（原话「A」）：analysis 的 scratch 开张行只填 `dir`，`base_commit`、`branch` 两栏不设、只对 deploy 必填。第六节表改；`03` 冻结，列同步。
- 2026-08-21 问题 3 裁 A（原话「A」）：快车道补单的报告目录用 ql_tag 命名（`experiments/<ql_tag>/`），拿到单号之后不改名。第七节规矩 4 改；目录约定本体在 `11`，列同步。
- 2026-08-21 问题 4 裁 A（原话「A」）：补单 `code_paths` 必填，和正常工单一样。第七节规矩 6 加、转移表前提加；`04` 冻结，列同步。
- 2026-08-21 问题 6 裁 A（gyb 确认「可以」，按总纲）：`--from` 转进的单子离开待干、就是出口的补单，不另开新单；合回追加一版直达 `done_pending_review`，放弃退回 `todo` 去标记。第二节、第七节改；转移表两行归 `04`、子命令名归 `05`，列同步。
- 2026-08-21 问题 7 裁 A（gyb 确认「可以」）：宿主 gpu-runner 不进插件的账（不登记 sessions、不写杂账）；deploy 备好完整命令交给它，数字由 deploy 记杂账。第五节改；sessions 账定义处 `04`，列同步。
- 2026-08-21 问题 8 裁 A（gyb 确认「可以」，按总纲关张即清干净）：`rl ql close` 两条路都自动删工作树、删同名分支，记录只剩杂账；gyb 想留在关张前自己处理。第七节改；`rl ql close` 行为归 `05`，列同步。
- 2026-08-21 问题 9 裁 A（原话「A」）：`decisions.deploy` 的 file 来源按普通规矩填主仓库路径——补决定发生在合并之后，主树已是新内容。第七节规矩 7 补句；`02` 不用改。
- 2026-08-21 问题 10 裁 A（原话「A」）：快车道不归研究线，`rl status` 按线分组时单独列一堆，不加可选栏。第八节补句；段 9 行为归 `01`，列同步。
- 2026-08-21 不一致处裁定稿：开单动作 deploy 做，owner 记 gyb；gyb 的本意「修好的信息回报发现者」由下一条公共规矩承担，owner 这栏按原推荐收。「owner 就是开单角色」通则加例外，归 `04`，列同步。
- 2026-08-21 gyb 立公共规矩（原话「我希望这个是个规则，而不是什么补丁特例」）：凡修的东西是账上报过的 issue，修完必须回复并关掉，发现者从收件箱看到，不许静默修。定义处归 `09`，列同步；本份第七节规矩 8 只写快车道的时点（回复发生在合回那一刻）。
- 2026-08-21 错误处理机制裁 A（原话「那就选A吧」）：发射员发现报错、落 issue、单子标卡住后销号；修好后单子回待干、拉起新的发射员接单，信息由单子承载——维持 `04`/`12`/`21` 现状，本份正文无改动。
- 2026-08-21 来自 `01-gyb.md` 定稿（`cd569ab`，rl-hub-v5 传）：接口一节推送表字样按「桌面通知这一版不做」改。对回原则 6。

## 要同步到别处的

- `03-ledgers.md`（冻结，等最后一期）：scratch 表 `open` 版必填改成「deploy 填 `worktree`、`base_commit`、`branch`；analysis 只填 `dir`」（问题 1）。（记 sync-inbox 问题 41，等最后一期，2026-08-21 rl-hub-v5）
- `04-handoffs-and-sessions.md`（冻结，等最后一期）：转移表快车道「（新建）→ done_pending_review」行前提加「`code_paths` 非空」（问题 4）。（记 sync-inbox 问题 41，等最后一期，2026-08-21 rl-hub-v5）
- `04-handoffs-and-sessions.md`（冻结，等最后一期）：转移表补两行——「`todo` 的单 `rl ql open --from` 标 `quick_lane`、离开待干不占 holder」「`quick_lane` 标记的单出口追加一版直达 `done_pending_review`（前提同快车道新建行）／放弃退回 `todo` 去标记」（问题 6）。（记 sync-inbox 问题 41，等最后一期，2026-08-21 rl-hub-v5）
- `04-handoffs-and-sessions.md`（冻结，等最后一期）：「owner 就是开单角色」通则加例外「快车道补单开单动作 deploy、owner 记 gyb」（不一致处定稿）。（记 sync-inbox 问题 41，等最后一期，2026-08-21 rl-hub-v5）
- `04-handoffs-and-sessions.md`（冻结，等最后一期）：sessions 账补一句「宿主 gpu-runner 不登记 sessions 账」（问题 7）。（记 sync-inbox 问题 41，等最后一期，2026-08-21 rl-hub-v5）
- `05-rl-cli.md`（冻结，等最后一期）：`rl ql close` 行为补「`--merged` 和 `--dropped` 都删工作树与同名分支」（问题 8）；`rl ql open --from` 行为补「单子标 `quick_lane` 并离开待干」；转进单出口追加一版直达 `done_pending_review` 的子命令名归 `05` 定（问题 6）。（记 sync-inbox 问题 41，等最后一期，2026-08-21 rl-hub-v5）
- `01-gyb.md`：`rl status` 段 9／`--group-by line` 补「没关的快车道不归线，单独列一堆」（问题 10）。（已同步 2026-08-21 rl-hub-v5）
- `09-common-and-feedback.md`：公共规矩加一条「凡修的东西是账上报过的 issue，修完必须回复并关掉那条 issue，不许静默修」（gyb 2026-08-21 立，非快车道特例）。（已同步 2026-08-21 rl-hub-v5：立为 rule-09，标题与各处「八条」改九条）
- `11-role-deploy.md`：部署报告目录约定补「快车道补单的报告目录用 `experiments/<ql_tag>/`，拿到单号之后不改名」（问题 3）。（已同步 2026-08-21 rl-hub-v5）
