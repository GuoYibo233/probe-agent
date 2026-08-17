# analysis 角色

> 这份覆盖 analysis 这个角色的 SKILL.md 要写进去的一切：写权和读法、模型、收件箱、先问 gyb 再提口径的规矩、口径账（evaluations）的两类与四态、接分析单与交活的前提、卡住时开 issue 的两条路、快车道里先画一张图、图和 notebook 落在哪。
> 不覆盖的：evaluations 和 handoffs 两本账的完整行格式在 `03-ledgers.md`，派活单的状态转移表和会话登记销号在 `04-handoffs-and-sessions.md`，rl 的完整命令表在 `05-rl-cli.md`，钩子和角色 json 的写法在 `06-hooks-and-permissions.md`，快车道的总规矩（进出两行账、ql_tag 怎么分）在 `07-quick-lane.md`，公共母版八条规矩在 `09-common-and-feedback.md`，idea 或 gyb 怎么开分析单在 `22-pair-idea-analysis.md`，analysis 从 runs 账里读什么在 `23-pair-run-analysis.md`，analysis 开 issue 给 deploy 那一头在 `24-pair-analysis-deploy.md`，reviewer 怎么审分析代码在 `14-role-reviewer.md`。
> 源：设计文档的「五个角色」总段、analysis 一节、快车道一节、「gyb 自己做的事」、账本一节的 evaluations 与 scratch 两条、「交接与会话生命周期」的交付物段、「两棵树」一节；施工计划第一节裁决 3 与第六轮改动 (e)(f)、第二节词表、第三节 evaluations 与 handoffs、第四节转移表、第五节 analysis 的 use case 与模型表、第六节 eval 与 ql 两行命令、第十三节规矩 4 和规矩 5。

## 一、写权、读的东西、模型、收件箱

analysis 的写权只有 `analysis/` 一个目录。钩子只挂 Write 和 Edit，拦两类事：写别的角色的目录（`experiments/`、`review/`、`notes/`），和直接写 `loop/`。`analysis/` 之外的其余仓库内路径钩子放行，靠纪律管。仓库外的路径（产物根、`/tmp`）钩子一律不判。

角色 json 四栏（施工计划第五节）：

| 栏 | 取值 |
|---|---|
| reads | runs、evaluations、handoffs、issues、feedback、`decisions.idea`、`decisions.gyb`、`analysis/` |
| writes | `analysis/` |
| ledger_writes | evaluations 的 propose/update、handoffs 的 start/done/stuck、issues 的 open/reply、scratch 全部、decisions.analysis 全部、feedback add |
| dispatches_to | 无 |

（`reads` 一行 2026-08-18 按 `06` 定稿的写法核对：账写账名、目录写相对仓库根的路径，没有句子，不用改。）

SKILL.md 里另写两句纪律（2026-08-18 gyb 裁，定义处 `06-hooks-and-permissions.md`）：用 Bash 往四个角色目录和 `loop/` 写（重定向、脚本、`cp`、`mv` 都算）等于绕钩子，不许，要写就用 Write/Edit 让钩子看得见，账本一律走 `rl`；一个会话只加载一个角色，要换角色另开会话。

两处原文不一致：设计文档 analysis 一节写的 reads 是「runs 账、口径账、派给自己的分析单、`decisions.idea` 和 `decisions.gyb`，加 handoffs」，施工计划第五节的表多了 issues、feedback、`analysis/` 三项。按施工计划的表为准。

模型（施工计划第一节裁决 3、第五节表）：由 agent 调用时 analysis 用 opus；gyb 手动加载角色时跟当前会话的模型一致，角色 json 的 `manual` 栏写 `inherit`，sessions 账落解析后的真实模型名，取不到记 `unknown`。

reads 一栏是纪律不设门禁：九本账的查询命令谁都能调。机器检查（测试 13）三样都查（2026-08-18 gyb 裁，定义处 `06-hooks-and-permissions.md`）：SKILL.md 正文出现的每条 rl 写命令都在这个角色 json 的 `ledger_writes` 里（查询命令不查）；SKILL.md 正文出现的每个账名和目录都在 `reads` 里（按 `reads` 栏定死的两种写法逐个对：账写账名，目录和文件写相对仓库根的路径）；引用的名字都在定义处查得到、母版不抄。

`rl inbox` 谁需要谁敲，不是上线动作：角色被拉起不自动查收件箱，先干拉它起来的那张单。inbox 列五样：本角色名下 open 的 issue、owner 是本角色而 holder 为空的单子、本会话手上单子引的过版决定、发给本角色的通知、本角色提的 feedback 的裁决。

## 二、先问 gyb 再提口径

分析什么、画什么图由 gyb 亲自说。口径账每一行都是 gyb 说、analysis 记、gyb 批，任何角色都不许自己写新的要分析的东西。analysis 不许自作主张画图，只把 gyb 说要看的数算出来。

顺序是先问后提：analysis 先问 gyb 要统计什么，问完再出推荐口径给 gyb 批。画什么图 gyb 自己定、自己说，analysis 只按 gyb 说的画，不许擅自替 gyb 主张画什么图。

批可以一句话批一组：`rl eval approve` 收多个编号加一个 quote。说还是按行说——gyb 一条条说要看什么，只是批的动作可以合成一次。

analysis 的上游是 idea；gyb 直接开 analysis session 的时候上游填 gyb。

跨 run 和单个 run 的界（公共规矩 4）：单个 run 的原始指标可以直接引，任何跨 run 的对比、聚合、画图一律走分析单和口径账。照抄 runs 账 metrics 里的原始数不算分析。

写代码和出数的界（公共规矩 5）：analysis 只算 gyb 说要看的数、只画 gyb 说要画的图；写代码不算算数，出数才要 `approved` 的口径。

## 三、口径账：两类与四态

口径账（evaluations）一行一条口径。分两类，用 `kind` 区分：指标 `metric`、图 `figure`。

指标行写清这个数从哪来，`metrics_key` 和 `code_path` 二选一：`metrics_key` 是直接取 runs 账 metrics 里的那个键，不重算；`code_path` 是由 analysis 现算的派生量，形如 `analysis/common/metrics.py:accuracy`。

图行必填 `group_by`、`x`、`y`、`uses`。`group_by`、`x`、`y` 三栏的取值只能是三样之一：runs 行的顶层字段名、`config.<键>`、已经 `approved` 的指标口径编号。`uses` 写这张图用哪几条指标口径。

四个状态：`proposed`、`approved`、`rejected`、`retired`。转法：

| 这一版 | 谁写 | 要满足什么 |
|---|---|---|
| `proposed` | analysis（`rl eval propose`） | `code_path` 可以还不存在 |
| `proposed`（改一版） | analysis（`rl eval update`） | 被打回之后改，或者 `approved` 之后再改 |
| `approved` | gyb | `code_path` 必须存在；那一版必填 `quote`，一句 quote 可以批多条 |
| `rejected` | gyb | 必填 `reason` |
| `retired` | gyb | —— |

两条要点：`approved` 的口径再 update 一版自动回到 `proposed`，要 gyb 重新批；`code_path` 提的时候可以还不存在、代码可以先写，批的时候必须存在。

口径的引用带版本，每项是 `{"id":...,"version":...}`。

其余字段：`id` 形如 `eval-0004`、`name`、`definition`、`applies_to`。

## 四、接分析单与交活

analysis 接的单子是 `analysis_order`，owner 是 idea 或 gyb。

接单：`rl handoff start ID`，前提是写入会话的角色等于 `to_role`、`holder` 为空；接单那一版把 holder 写成本会话。holder 非空当且仅当单子在 `in_progress`，离开 `in_progress` 的任何一次转移都清空 holder 并记 `last_holder`。

开单时口径可以还是 `proposed`（施工计划第一节第六轮改动 (e)），交活时必须全部 `approved`。

交活：`rl handoff done`，两条前提一起查：

- `output_paths` 填了并且路径存在，形如 `{"notebook":...,"figures":[...]}`。
- `evaluation_refs` 每一项都是 `approved`。

缺一条入账脚本不收 `done_pending_review`，退出码 2。开单的那一刻不查这两条，前提查在交付那一刻。

交完活由 owner 验收（`rl handoff accept`）或打回（`rl handoff reject --reason`）；gyb 随时可以自己验，gyb 越过 owner 验收或打回时 rl 给 owner 发一条 `fyi` 通知。被打回的单子回到 `todo`，由 owner 重新拉起。

补东西也有路：单子在 `todo` 或 `stuck` 上可以 `rl handoff amend` 补 `evaluation_refs`、换 `decision_refs` 或 `evaluation_refs` 里的引用，状态不变；单子在 `done_pending_review` 上 amend 只允许补或改 `report_paths`、`output_paths`、`code_paths` 里的路径，换 `decision_refs` 或 `evaluation_refs` 里的引用（doctor 的修法用）。

交回待干（`rl handoff release`）那一版必填 `progress_note`：干到哪、产物在哪。

## 五、卡住的两条路

analysis 卡住的时候不自己硬扛，开 issue（公共规矩 6：analysis 卡住开 issue 给出问题的角色），单子标 `stuck` 并且 `issue_id` 要指向那条 issue、那条 issue 的 `handoff_id` 要指回本单。写序定死：先写 issue 拿到编号，再写单子那一行引它。

第一条路，分组键缺失开 issue 给 gyb。历史 run 的 config 里缺这次要用的分组键时，analysis 开 issue 给 gyb，kind 是 `cannot`，由 gyb 定三选一：补跑、换口径、还是走 `code_path` 从产物目录现算。analysis 补不了 runs 账——数字账只有 run 的脚本能写（gyb 例外）。

第二条路，发现代码问题开 issue 给 deploy。写权按角色不开例外，不给下游改一个 typo 的小口子；analysis 发现 `experiments/` 里的代码有问题，开 issue 给 deploy，自己不动那边的文件。

issue 被回复之后，由回 issue 的那个角色 `rl handoff resume` 把单子交回 `todo`，前提是关联 issue 状态已经是 `answered`。

## 六、快车道：先画一张图

快车道不是 deploy 专属。gyb 只想先看一眼图的时候走同一条：进快车道由 gyb 点名，口头就行，不设别的判据。

进：`rl ql open --role analysis`。rl 在锁里分配标签（形如 `ql-20260816-01`）、往杂账（scratch）写开张的一行。analysis 的快车道不建 worktree，产物放 `analysis/scratch/<标签>/`。

中间：不开口径、不开分析单，图落 `analysis/scratch/`，数字追加进杂账、不进 runs 账。杂账中间版格式松，只校验骨架和 `ql_tag`；`open`、`merged`、`dropped` 三版按表查必填。

出：`rl ql close QL --dropped --reason`，杂账上的一行。analysis 的快车道没有补单，只有丢掉这一条出路；`--merged --handoff ID` 只有 deploy 能打。要引用或者复用这张图的时候，按正常路重做一遍，补口径和分析单。快车道的东西一旦要进正账拿来复用，它就不是快车道了，得按正常路重来。

没关掉的快车道出现在 `rl status` 里；超过 `reclaim.ql_idle_days`（默认 7 天）没关的，`rl reclaim` 也列进来。

## 七、图和 notebook 落在哪

小图和 notebook 进仓库的 `analysis/`。大文件进配置里的分析产物根（`research-loop.json` 的 `analysis_artifact_root`），并且在口径行里记路径。

`analysis/` 这棵树由 `rl init` 建：公共统计件由 init 播模板，notebook 由 analysis 干活时新建，`analysis/scratch/` 留给快车道。

宿主自己的四层记录（new1 的 TIMELINE.md、DATA.md、RESULTS.md、`ops/runs.jsonl`）analysis 一律不碰。

## 和别的 part 的接口

- `analysis_order` 的全部字段、`output_paths` 的形状、`evaluation_refs` 带版本：`03-ledgers.md`。
- evaluations 每个字段的必填规则和 `id` 格式：`03-ledgers.md`。
- 派活单七个状态、转移表每一行的谁能写和前提、holder 的不变量：`04-handoffs-and-sessions.md`。
- 会话登记与销号（钩子代 analysis 写 sessions 账、销号时把 `in_progress` 的单子交回 `todo`）：`04-handoffs-and-sessions.md`。
- `rl eval propose/update/approve/reject/retire/show/list`、`rl handoff start/done/stuck/amend`、`rl ql open/close`、`rl scratch add`、`rl inbox` 的参数：`05-rl-cli.md`。
- 钩子拦哪两类路径、角色 json 四栏的格式、机器检查三样都查（2026-08-18 裁）：`06-hooks-and-permissions.md`。
- 快车道的总规矩：ql_tag 谁分、进出两行账、`rl status` 和 `reclaim` 怎么列：`07-quick-lane.md`。
- `analysis_artifact_root` 和 `analysis/` 目录由 init 建出来的样子：`08-trees-init-and-host.md`。
- 公共规矩 4（证据配路径）、规矩 5（口径不发明）、规矩 6（故障分域）、读法栏：`09-common-and-feedback.md`。
- idea 开分析单、gyb 直接开分析单、口径谁批：`22-pair-idea-analysis.md`。
- runs 账的 `metrics`、`config` 字典、`run list` 默认过滤：`23-pair-run-analysis.md`。
- analysis 开给 deploy 的 issue 那一头怎么接：`24-pair-analysis-deploy.md`。
- reviewer 审分析代码和 notebook 的顺序与基准：`14-role-reviewer.md`。
- `rl status` 里等批的口径、等验收的单子在哪一段：`01-gyb.md`。
- 十一条设计原则的原文：`00-overview.md`。
- 测试 14（口径）、测试 13（SKILL.md 引用检查）：`30-build-steps-verify-tests.md`。

## 源文档没写清的（留给 gyb）

1. analysis 发现代码问题开给 deploy 的那条 issue 填哪个 kind：九种 kind（`cannot`、`not_mine`、`denied`、`failed`、`anomaly`、`request`、`withdrawn`、`orphaned`、`fyi`）里没有一种是「别人的代码有问题」，施工计划第五节只写「发现代码问题开 issue 给 deploy」，kind 没定。分组键缺失那条明写了 `cannot`，这条没有。
2. analysis 快车道的 scratch 开张版填什么：第三节写 scratch 的 `open` 版必填 `worktree`（deploy）或 `dir`（analysis）、`base_commit`、`branch`，可 analysis 的快车道不建 worktree 也不建分支，`base_commit` 和 `branch` 两栏对 analysis 填什么没写。
4. analysis 的自决是什么：角色 json 的 ledger_writes 里有 `decisions.analysis` 全部，可公共规矩 2 把自决定义成「改变实验结果的选择」，analysis 不跑实验，哪些选择算 analysis 的自决没有例子。
5. `rl eval retire` 归谁调：第三节写 `retired` 那一版 actor 必须是 gyb，第六节命令表那一行的「谁能调」写的是「提和改 analysis，批和打回 gyb」，retire 没点名。
6. 口径的 add 还是 update 没有判据：决定账有「同一个问题换做法就追加一版、换了要回答的问题就开新条」这条判据，口径账只写了 `approved` 之后 update 回 `proposed`，什么时候该开一条新口径没写。
7. 没有分析单的 analysis 会话怎么交付：设计文档写「gyb 直接开 analysis session 的时候上游填 gyb」，也写「gyb 只想先看一眼图的时候走快车道」，可 gyb 直接开会话又不走快车道的那一种，notebook 和图落在哪、要不要补一张单，没写。
8. analysis 的 ledger_writes 里有 `issues` 的 reply，可九本账的规矩里没有任何角色开 issue 给 analysis，analysis 回的是谁的 issue 没写。
9. `output_paths` 的 `notebook` 是单值、`figures` 是列表：一张分析单产出两个 notebook 的时候怎么填没写。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

以下条目从 `plans/2026-08-16-research-loop-simulation-round2.md` 原样抄来，不做判断、不改字。那份文件开头写明：模拟者原话，未经核实者和 critic 核实，可能有误报。

### plot-new-plan（17 步，gyb 动手 8 次）

1. [blocks/contradiction] 第 7 到第 10 步（提口径与开分析单的先后）：转移表规定 analysis_order 新建落 todo 的前提是 evaluation_refs 每项已 approved，但 analysis 的 use case 表把「接分析单」排在「问 gyb 要统计什么并提口径」前面，设计文档也写 analysis 先接单再问 gyb；一个全新的画图计划手上没有任何 approved 口径，照 use case 的顺序开单会被入账校验拒收，照转移表的顺序又要在没有单子的情况下先干活。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-build-plan.md:107; plans/2026-08-16-research-loop-next-steps.md:76; plans/2026-08-16-research-loop-next-steps.md:50
   - 改法：在设计文档 analysis 一节明写新计划的顺序是先开 analysis 会话过口径、口径 approved 之后再开分析单，或者改成分析单可以引 proposed 口径、到 handoff done 时才校验已 approved。

2. [slows/too_heavy] 整条路（第 1 步到第 17 步）：gyb 只想看一眼图，按文档要走 2 次 eval propose、2 次 approve、1 次 handoff open、start、done、accept 共 8 次写账，gyb 本人要介入 8 次；快车道只给 deploy，analysis 没有对应的轻路，和目标里「想法要快速、多次迭代」对不上。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：给 analysis 加一条 gyb 点名的快车道：图先落杂账不开口径不开单，图要被引用或复用的时候再补口径和分析单。

3. [slows/principle_violation] 第 10 步（gyb 开分析单）：违反原则 1。原则 1 写 gyb 在任何终端、任何角色会话里都能行使自己的权，任何权限检查不生效；但施工计划只让 gyb 豁免转移表「谁能写」一栏和「谁能调」检查，「前提」一栏照旧生效，于是 gyb 自己开分析单时被 evaluation_refs 必须 approved 这条前提挡住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:77; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：在施工计划第四节表头明写「前提」一栏对 gyb 生不生效，若生效就把它改称数据完整性校验、和权限检查分开命名。

5. [slows/missing] 第 10 步与第 16 步之后的下一轮迭代：handoffs 的 decision_refs 每项带 {id, version}，evaluation_refs 只写编号不带版本；口径 approved 之后再追加一版，已经派出去的分析单引的是哪一版查不出来，过版检查命令 rl decision stale 也只覆盖决定账。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-next-steps.md:111
   - 改法：evaluation_refs 改成和 decision_refs 一样的 {id, version}，并让 stale 检查同时扫口径引用。

6. [slows/missing] 第 16 步之后（gyb 看完图想换个画法）：口径账只写了被打回之后 analysis 改了再提一版这条路，没写已经 approved 的口径能不能 update、update 之后 status 回不回 proposed、要不要重新批；也没有决定账那种「同一个问题换做法追加一版、换问题开新条」的判据。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:78; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:216; plans/2026-08-16-research-loop-next-steps.md:46
   - 改法：给 evaluations 抄一条决定账同款判据，并明写 approved 之后 update 一版就回 proposed、必须由 gyb 重新 approve。

7. [slows/missing] 第 6 步与第 8 步（写图口径的 group_by 和 x 轴）：图行必填 group_by、x、y，但文档没写这三栏的取值域是 runs 行的顶层字段、config 字典里的键、还是 analysis 现算的派生量；「按模型规模分组」要落成 config.params 全靠模型自己猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：在第三节 evaluations 字段里写死 group_by 和 x、y 的取值只能是 runs 的顶层字段名、config.<键>、或已 approved 的 metric 编号。

8. [slows/missing] 第 6 步（analysis 读 runs 账找分组键）：历史 run 的 config 里没有这次要用的分组键时没有出路：runs 账只有 run 角色的脚本能写、只增不改，analysis 补不了，文档也没写这时该开 issue 给谁、口径要不要改成从产物目录现算。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:99; plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：加一句「分组键在 runs.config 里缺失时 analysis 开 issue 给 gyb（kind 是 cannot），由 gyb 定是补跑、是换口径、还是走 code_path 从产物目录现算」。

10. [slows/ambiguous] 第 10 步（分析单的 from_role）：owner 被定义成开单角色也就是 from_role，而角色只有五个、gyb 不在角色表里；设计文档和词表都说 gyb 可以开分析单，但 handoffs 的 from_role 能不能填 gyb、gyb 算不算合法 owner 没有明写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:41; plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：在第三节 handoffs 的 from_role 字段写清取值是五个角色或 gyb，并说明 owner 是 gyb 时验收和拉起下游都由 gyb 做。

12. [cosmetic/missing] 第 13 步到第 14 步（图画完之后叫 gyb）：单子进 done_pending_review 只出现在 rl status 里，桌面通知只在 issue 改派给 gyb 的时候发；gyb 不坐在这个会话里的时候，得靠自己轮询才知道图画好了。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：把「等 gyb 验收的单子」也接进 rl notify，或者在设计文档里明写这一类只进 rl status、不通知。

13. [cosmetic/missing] 第 12 步（图和 notebook 落盘位置）：决定的来源里把 analysis/ 里的图当仓库内文件路径，init 又说原始数据走配置里的产物根；图和 notebook 进不进 git、多大算大产物要挪到产物根，两份文档都没划线。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：在 research-loop.json 里加一个 analysis 产物根，明写小图和 notebook 进仓库 analysis/、大文件进产物根并在口径行里记路径。

### next-plan-after-results（36 步，gyb 动手 16 次）

2. [blocks/blocked] 第 11 到 15 步：analysis_order 新建的前提是 evaluation_refs 每项已 approved，但口径是 analysis 接单之后才提的（角色 json 的 use case 顺序是「接分析单 → 提口径」）。一批新结果第一次要新指标时，单子和口径互为前提；只能靠「gyb 直接开一个没有单子的 analysis 会话先提口径」绕过，而文档从没描述过没有单子的 analysis 会话该怎么交付 notebook 和图
   - 依据：2026-08-16-research-loop-build-plan.md:81; 2026-08-16-research-loop-build-plan.md:107; 2026-08-16-research-loop-next-steps.md:76; 2026-08-16-research-loop-next-steps.md:80
   - 改法：允许 analysis_order 引 proposed 口径开单、批准落在 done 之前，或明写「先谈口径后开单」并给无单分析会话一个交付落点

3. [slows/principle_violation] 第 14 步：违反原则 1。原则 1 和施工计划裁决 6 说 gyb 不受任何权限检查影响，转移表却只给 gyb 豁免「谁能写」一栏、不豁免「前提」一栏，于是 gyb 自己也开不出引未批口径的分析单、也收不了缺交付物的单子。两句话对「权限检查」的范围理解不一样
   - 依据：2026-08-16-research-loop-build-plan.md:77; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15
   - 改法：把原则 1 改写成「权限检查对 gyb 不生效，数据完整性前提对谁都生效」，并给 gyb 一个 `--force` 带原因写进账行

4. [slows/too_heavy] 第 1 到 36 步整条路：只是「看完一批结果定下一步」，gyb 亲自动作 16 次，其中光批口径就要按行逐条批、图口径还得先有指标口径两级批。设计文档开头写的目标是想法要快速多次迭代，每一条手续都要拿这两点衡量，这条路和那句话拉扯
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-next-steps.md:183; 2026-08-16-research-loop-build-plan.md:69
   - 改法：给「一批结果的例行复盘」开一条批量口令：gyb 一句话批一组口径（rl 记下这句原话展开成多行），图口径自动带上它 uses 的指标

12. [cosmetic/ambiguous] 第 12 步：派生量口径 approve 时 code_path 必须已存在，可公共规矩 5 又说派生量只用 approved 的口径；analysis 到底能不能为一条还没批的口径先写代码，两种读法都说得通
   - 依据：2026-08-16-research-loop-build-plan.md:69; 2026-08-16-research-loop-build-plan.md:249
   - 改法：规矩 5 补一句「写代码不算算数，出数才要 approved 口径」

### n-launch-orders（58 步，gyb 动手 10 次）

14. [slows/missing] 第 46 步：同一张发射单重跑之后名下挂了两条 run（一条 killed 一条 ok），`rl run list --batch` 会把 6 条一起吐出来，去重和筛掉失败的规则没写，analysis 按 batch 拉数分组的时候同样吃到这 6 条。这一步只能自己挑。
   - 依据：2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-next-steps.md:80
   - 改法：rl run list 默认只出 exit_status=ok 且每张发射单取最新一条，加 --all 才出全部。

15. [slows/ambiguous] 第 48 步：跨 run 的聚合数算谁的活，两种读法都说得通。一种读法：idea 读九本账全部，runs 账的 metrics 就在里面，自己把 5 个数平均一下没人拦。另一种读法：规矩 5 说派生量只用 approved 的口径、由 analysis 算，均值方差正是派生量，idea 自己算就是自作主张。
   - 依据：2026-08-16-research-loop-next-steps.md:52; 2026-08-16-research-loop-next-steps.md:30; 2026-08-16-research-loop-build-plan.md:249
   - 改法：明写一句：单个 run 的 metrics idea 可以直接引，任何跨 run 的聚合一律走 analysis 分析单。

16. [slows/too_heavy] 第 50 到 54 步：口径要 approved 之后才能开分析单，而 approve 又要求 code_path 已经存在，于是同一件事要开两个 analysis 会话：先由 gyb 直接开一个没有单子的 analysis 会话把代码写出来，gyb 批完之后 idea 再开正式分析单让第二个 analysis subagent 重做一遍。5 个种子求个均值走完这一圈要 gyb 亲自动手三次。
   - 依据：2026-08-16-research-loop-next-steps.md:78; 2026-08-16-research-loop-next-steps.md:76; 2026-08-16-research-loop-build-plan.md:69; 2026-08-16-research-loop-build-plan.md:81
   - 改法：允许 analysis_order 引 proposed 的口径，把「已 approved」和「code_path 存在」两条前提一起挪到 handoff done 那一步校验。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

10. [blocks/blocked] 第 22 步：分析单和口径互为前提。新建 analysis_order 的前提是 evaluation_refs 每项已 approved，设计文档也写「单子里只能引已经批准的口径行」；而 analysis 的 use case 第一条是接分析单，接完才问 gyb 要统计什么、才提口径给 gyb 批。一批新数出来之后的第一张分析单永远开不出来。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-next-steps.md:50; plans/2026-08-16-research-loop-next-steps.md:76; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：把 evaluation_refs 每项 approved 这个前提从新建那一行挪到 in_progress→done_pending_review 那一行，新建时允许空。

## 裁决记录（日期）

- 2026-08-17 来自 sync-inbox 问题 10 的裁决（定义处 `04`，rl-hub-v3 传；gyb 原话「A」）：第四节 amend 那段照 `04` 转移表两行 amend 改：`todo`/`stuck` 上还能换 `decision_refs` 或 `evaluation_refs` 里的引用，`done_pending_review` 上能补或改 `report_paths`、`output_paths`、`code_paths` 并换引用。
- 2026-08-17 来自 sync-inbox 问题 16 的裁决（定义处 `07`，rl-hub-v3 传；gyb 原话「A」）：第六节「出」那句改成 analysis 的快车道只有 `rl ql close QL --dropped --reason`，没有补单，`--merged --handoff ID` 只有 deploy 能打；「源文档没写清的」第 3 条末尾标已裁。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `03`、`05`，rl-hub-v3 传；gyb 原话「只有做完了的时候才关，巡检要我本人确认」）：第一节 inbox 五样里通知那一项后面的「（读过即关）」删掉。
- 2026-08-17 来自 sync-inbox 问题 28 的裁决（定义处 `01`，rl-hub-v3 传；gyb 原话「每个角色创建时候，不要自动查收件箱」「C」）：第一节标题里的「上线第一个动作」改成「收件箱」，那句改成「`rl inbox` 谁需要谁敲，不是上线动作：角色被拉起不自动查收件箱，先干拉它起来的那张单」；开头摘要那一行跟着改。
- 2026-08-17 rl-hub-v3 按 HANDOFF 第八节问题 16 那行「`13:140`（销）」：「源文档没写清的」第 3 条（analysis 走 `--merged` 补哪张单）已被问题 16 答掉，整条销掉，编号不重排；第六节「中间」那句按 `07-quick-lane.md` 第五节改成「中间版格式松，只校验骨架和 `ql_tag`；三版按表查必填」（`03` 事项 2 的裁决，05 定稿那一轮漏传）。
- 2026-08-18 来自 `06-hooks-and-permissions.md` 定稿（`d430192`，rl-hub-v4 传；gyb 原话「a」（问题八、十一、十二）「6 c」）：json 副本 `reads` 核对无句子；机器检查改三样都查（第二节与接口一节）；加两句 SKILL.md 纪律。对回原则 8、2。
