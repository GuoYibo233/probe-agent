# run 与 analysis 之间的数据契约

> 这一份写 runs 这本账怎么把 run 跑出来的东西交到 analysis 手上：一次尝试分几版、每一版填哪些字段、config 字典里放什么键、metrics 和 data_path 是什么、查的时候默认过滤掉哪些行、按哪几个维度筛、历史 run 缺分组键怎么办、拿着一个 run_id 怎么顺回决定。不写 run 自己怎么探卡发射收尾（见 12-role-run.md），不写 deploy 开发射单时怎么填这些字段（见 21-pair-deploy-run.md），不写口径账怎么提怎么批（见 22-pair-idea-analysis.md），不写 analysis 交活时交什么（见 13-role-analysis.md），不写九本账的公共骨架和另外八本（见 03-ledgers.md）。源：设计文档的原则 9、原则 10、run 一节、analysis 一节、账本一节第 4 条；施工计划的第二节词表、第三节 runs 与 evaluations、第五节 analysis 的 use case、第六节 `rl run` 与 `rl eval` 与 `rl doctor` 三行、第八节阈值、第十节测试 10。

## 契约的两头是谁

runs 这本账叫数字账，文件是 `loop/runs.jsonl`，一个 schema。写的一头只有 run 角色的脚本，gyb 例外（原则 1）；账行的 `actor` 取 `run` 或 `gyb`。读的一头是 analysis：analysis 的 reads 里有 runs、evaluations、handoffs、issues、feedback、`decisions.idea`、`decisions.gyb`、`analysis/`。读不设门禁，查询命令谁都能调（原则 2 推论），所以 idea 和 reviewer 也读得到 runs，只是这一份只说 analysis 这一头。

公共规矩第 3 条把这件事写死了：runs 账只有 run 的脚本能写（gyb 例外），实验数据一个 schema，禁止用眼睛读日志填数。公共规矩第 4 条接着写：每个数字配可复现的执行路径，统计类证据走 analysis 的 notebook；单个 run 的原始指标可以直接引，跨 run 的对比、聚合、画图一律走分析单。哪些人能直接念 metrics、哪些事必须走口径账，在 22-pair-idea-analysis.md。

## 一次尝试两版

runs 是事件流，只增不改，每一行带 `version` 和 `status`，默认查询每个主键只取最新版（原则 4）。一张发射单的一次尝试落两版：发射成功那一刻落发射版，跑完落收尾版。`status` 取 `launched` 或 `finished`，入账校验按 `status` 查必填字段。

| 版 | status | 必填字段 |
|---|---|---|
| 发射版 | `launched` | `commit`、`command`、`host`、`gpus`、`log_path`、`tmux_session`、`watch_cmd`、`started_at`、`config` |
| 收尾版 | `finished` | `finished_at`、`exit_status`、`actual_seconds`；`exit_status` 是 `ok` 时再加 `metrics` 和 `data_path` |

主键是 `run_id`，形如 `ho-0013-a1`，和产物目录名、tmux session、commit message 一致；快车道用 `ql_tag`。另外两个身份字段是 `handoff_id` 和 `attempt`，指这条 run 属于哪张发射单的第几次尝试。`exit_status` 三选一：`ok`、`failed`、`killed`。`actual_seconds` 由 rl 从 `started_at` 和 `finished_at` 两个时间戳算，退出状态是什么都记。

两处原文不一致：设计文档 run 一节列收尾版字段时写的是「结束时间、退出状态、指标、真实耗时」，没有 data_path；施工计划第三节 runs 那一行写 `exit_status` 是 `ok` 时 `metrics` 和 `data_path` 必填。按施工计划的表为准，收尾版的 ok 行有 data_path。（2026-08-17 按 `03-ledgers.md` 的裁决定稿，设计文档那句由统筹 session 回写补上 data_path。）

还有一处原文不一致：设计文档快车道一节写「数字追加进杂账，不进 runs 账」，施工计划第三节 runs 主键那一行写「快车道用 `ql_tag`」，等于承认 runs 里会有快车道的行。按施工计划的表为准，`run_id` 这一栏留了 `ql_tag` 这个取值。快车道本身在 07-quick-lane.md。

写这两版的命令是 `rl run add` 和 `rl run finish`：`add` 从发射单抄 `command`、`config`、`run_id`；`finish` 算 `actual_seconds`、在同一个进程里跑反常预警、调宿主的收尾命令模板。反常预警看两个阈值，`anomaly.metric_extremes` 默认 `[0, 1]`（指标落在 0 或 1 就开一条 `anomaly` issue 给 gyb），`anomaly.duration_factor` 默认 3（实际耗时超过预计 3 倍）。什么时候打这两条命令归 run，见 12-role-run.md。

## config 字典：deploy 填、run 抄、analysis 分组

config 是给 analysis 分组用的字典，deploy 开发射单的时候填在那次尝试上，`rl run add` 默认从发射单抄进 runs 行，run 只补机器和卡。约定的键有四个：`model`、`params`、`dataset`、`split`，其余超参自由。

config 进 runs 行是这条契约里最要紧的一格：analysis 画图时的分组维度和横纵轴取值只能是三样东西之一，runs 行的顶层字段名、`config.<键>`、或者已经 `approved` 的指标口径编号。config 里没有的键，图口径就写不出来。

## metrics 与 data_path

`metrics` 是一个字典，键是指标名，值是数。口径账里的指标行（`kind` 是 `metric`）二选一：要么写 `metrics_key`，直接取 runs 账 metrics 里的那个键，不重算；要么写 `code_path`，由 analysis 按代码现算的派生量。所以 metrics 的键名就是口径账 `metrics_key` 引的那个字符串，两头得是同一个名字。doctor 有一项扫这件事：approved 口径引的 metrics 键在 runs 账里不存在。

`data_path` 只在收尾版且 `exit_status` 是 `ok` 时必填，是产物目录里给 analysis 算数用的那一个文件或子目录。产物目录本身账上不记，按约定是 `<artifact_root>/<run_id>/`（发射版原来的 `artifact_dir` 一栏 2026-08-17 去掉了）；`log_path` 是日志路径，在发射版上。

## 查：一条 show，一条 list

`rl run show RUN_ID` 出一条。`rl run list [--handoff ID] [--decision ID] [--batch B] [--line L] [--all]` 出一批，谁都能调。

默认过滤是这条契约里的第二个要紧处（原则 10）：`list` 默认只出每张单最新尝试且 `exit_status=ok` 的行，`--all` 才全出。所以 analysis 按默认走的时候，跑挂的、被杀的、修完重来之前那几次尝试，都不会混进来。测试 10 里有一条对应的用例：`run list` 默认不出 killed 和旧尝试，`--all` 出。

四个过滤开关对应四种问法：`--handoff` 是「这张发射单跑出来的」，`--decision` 是「这条决定名下的」，`--batch` 是「这一次分片的」，`--line` 是「这条研究线的」。`batch` 只有分片语义，形如 `b-20260816-01`，指 deploy 一次开 N 张同 batch 的发射单；研究线是另一个字段 `line`，就是根决定编号，由 rl 从发射单 `decision_refs` 第一项的 `root_id` 算出来存在发射单上。这两个不是一回事，别拿 batch 当研究线用。

## 分组键缺了怎么办

历史 run 的 config 里缺这次要用的分组键时，analysis 不自己补也不自己猜：开一条 issue 给 gyb，kind 是 `cannot`。由 gyb 定三条路里的哪一条，补跑、换口径、还是走 `code_path` 从产物目录现算。runs 账只增不改而且只有 run 的脚本能写，所以 analysis 补不了历史行，这是这条出路存在的理由。

## 从 run_id 回决定

`rl trace <dec-|ho-|run_id|iss-|eval->` 一条命令从任何一个编号打出到决定各版本的整条链（原则 9）。链上的字段是这几样：runs 行的 `handoff_id` 指发射单，发射单的 `parent_id` 指工单（`launch_order` 必填），发射单的 `decision_refs` 开单时从父单抄，工单的 `decision_refs` 必填至少一项，每项是 `{"id":..., "version":...}`。所以从一个数字回到决定不需要人工比对命令行里的路径。

反过来走也有：`rl decision show ID [--with-runs]` 沿 `parent_id` 链反查各版本派出的单子和 run 与 metrics。

一条决定的来源可以是一个 run_id（三类来源里的 `run` 类），跑完实验才知道的结论就是这么进决定账的。决定账那一头在 02-decisions.md。

## 账面对不上的时候谁扫

`rl doctor` 里和这条契约有关的扫描项有五条，每项附修法命令：

| 扫描项 | 修法 |
|---|---|
| runs 行 `handoff_id` 为空、悬空或不是 `launch_order` | `run relink` 或 `--ack` |
| runs 有 `launched` 版长期没 `finished` 版 | doctor 那一行没写死修法命令 |
| runs 挂在 `withdrawn` 的单子上 | 同上 |
| approved 口径引的 metrics 键在 runs 账里不存在 | 同上 |
| `loop/runs.jsonl` 与宿主 `ops/runs.jsonl` 对不上的 run_id | 同上 |

`rl run relink RUN_ID --handoff ID` 是专门给 doctor 修法用的第三种写法，只补 `handoff_id`。两本 runs 账并存不合并这件事在 08-trees-init-and-host.md。

## 和别的 part 的接口

- `run_id` 由 rl 按 `<ho-id>-a<attempt>` 分配、`attempt` 是发射单上尝试列表的序号：见 21-pair-deploy-run.md。
- config 字典由 deploy 开发射单时填在那次尝试上：见 21-pair-deploy-run.md。
- `rl run add` 和 `rl run finish` 在 run 的哪一步打、`finish` 调的宿主收尾命令模板是哪一条：见 12-role-run.md。
- 反常预警的两个阈值 `anomaly.metric_extremes` 和 `anomaly.duration_factor` 在施工计划第八节，预警动作归 run：见 12-role-run.md。
- 口径账的行格式、`metrics_key` 与 `code_path` 二选一、图行的 `group_by`/`x`/`y`/`uses`、四个状态：见 03-ledgers.md，提和批的规矩见 22-pair-idea-analysis.md。
- 分析单交活时 `evaluation_refs` 每项必须 `approved`、`output_paths` 必须存在：见 04-handoffs-and-sessions.md。
- 发射单的 `parent_id`、`decision_refs`、`batch`、`line` 四个字段的定义：见 03-ledgers.md；`line` 就是根决定编号，根决定的定义见 02-decisions.md。
- issue 的 `kind` 取值（这一份用到 `cannot` 和 `anomaly`）、assignee 是 gyb 那一版触发桌面通知：见 03-ledgers.md，推送表见 05-rl-cli.md。
- `rl trace`、`rl run list`、`rl doctor` 三条命令的完整参数和退出码：见 05-rl-cli.md。
- 九本账的公共骨架七样字段、`--force --reason` 硬写留痕：见 03-ledgers.md 和 01-gyb.md。
- 快车道的数字进杂账、`ql_tag` 怎么分：见 07-quick-lane.md。
- 单个 run 的原始指标谁能直接念、跨 run 的聚合归谁：见 22-pair-idea-analysis.md。

## 源文档没写清的（留给 gyb）

1. （2026-08-17 按 `03-ledgers.md` 的裁决销掉：`data_path` 是产物目录里给 analysis 算数用的那一个文件或子目录，`artifact_dir` 一栏去掉、产物目录走 `<artifact_root>/<run_id>/` 约定。）
2. `exit_status` 是 `failed` 或 `killed` 的收尾版要不要 `data_path`。施工计划只写了 ok 时必填，测试 10 只写了「`failed` 不要求 metrics 但要有 actual_seconds」，没提 data_path。
3. `rl run list --line L` 和 `--decision ID` 怎么解析。runs 行上既没有 `line` 也没有 `decision_refs`，这两个字段在发射单上，源文档没写这两个开关是先查发射单再回来筛，还是别的走法。
4. 默认过滤那句「每张单最新尝试且 `exit_status=ok`」，两个条件是并列还是有先后。一张发射单跑了三次、第二次 ok 第三次 failed 的时候，默认出不出第二次那一行，两种读法都说得通。
5. config 里除了 `model`、`params`、`dataset`、`split` 四个约定键，其余超参自由，源文档没写自由键的命名规矩；两张发射单把同一个概念填成两个不同的键名时，analysis 按哪个分组也没写。
6. metrics 的键名谁定、由谁保证不同 run 的同名指标是同一个东西。施工计划只写「键是指标名、值是数」，而口径账的 `metrics_key` 引的就是这个键。
7. 快车道的数字到底进不进 runs（正文里标出的第二处原文不一致）。按施工计划的表读，`run_id` 那一栏收 `ql_tag`；按设计文档快车道一节读，数字只进杂账。
8. doctor 五项里只有第一项写死了修法命令（`run relink` 或 `--ack`），另外四项在施工计划第六节 doctor 那一行里只有扫描项名字，没有修法命令模板。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

### result-wrong-review（25 步，gyb 动手 11 次）

1. [blocks/missing] 第 3 步和第 4 步：handoffs 没有指向上游单子的字段，发射单的 decision_refs 又不是必填（只有 work_order 必填），所以从一个不对的 run_id 顺不回工单、更顺不回决定：runs.handoff_id 指的是发射单，发射单上既没有 parent 也可以没有 decision_refs，`rl handoff list --decision` 只出工单，`rl decision show --with-runs` 声称「顺着 handoffs 反查跑出的 run」这条链在工单到发射单这一跳断掉。同一个缺口让 `withdraw --cascade` 的「派生的下游单」和 doctor 的「快车道工单已 accepted 但没有关联发射单」都没有判断依据。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个必填的 parent_id（发射单指它所属的工单、快车道正式重跑的发射单指那张快车道工单），--cascade、doctor 和反查全按它走。

2. [slows/too_heavy] 第 1 步到第 5 步：gyb 只是想知道「这个数字是按哪条决定跑出来的」，按文档要在裸终端敲 rl status、rl run list、rl handoff show、rl decision list、rl decision show 五条命令，中间还要靠 launch.command 里的路径人工比对，和「想法要快速、多次迭代」的目标不相称。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-build-plan.md:137
   - 改法：第六节命令表加一条 `rl trace <run_id>`，一条命令打出 run 到发射单到工单到决定各版本的整条链。

### new-idea（39 步，gyb 动手 7 次）

12. [slows/ambiguous] 第 37 步：「拿到数字给 gyb 看」两种读法都成立：idea 读九本账全部，可以直接 rl run show 把 metrics 念给 gyb；可另一处写着任何角色不许自己写新的要分析的东西、要看什么 gyb 一条条说由 analysis 记账批准，照抄一个原始指标算不算分析没有界
   - 依据：plans/2026-08-16-research-loop-next-steps.md:52; plans/2026-08-16-research-loop-next-steps.md:30; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：明写「照抄 runs 账 metrics 里的原始数不算分析，任何对比、聚合、画图都要走口径账」

### plot-new-plan（17 步，gyb 动手 8 次）

7. [slows/missing] 第 6 步与第 8 步（写图口径的 group_by 和 x 轴）：图行必填 group_by、x、y，但文档没写这三栏的取值域是 runs 行的顶层字段、config 字典里的键、还是 analysis 现算的派生量；「按模型规模分组」要落成 config.params 全靠模型自己猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：在第三节 evaluations 字段里写死 group_by 和 x、y 的取值只能是 runs 的顶层字段名、config.<键>、或已 approved 的 metric 编号。

8. [slows/missing] 第 6 步（analysis 读 runs 账找分组键）：历史 run 的 config 里没有这次要用的分组键时没有出路：runs 账只有 run 角色的脚本能写、只增不改，analysis 补不了，文档也没写这时该开 issue 给谁、口径要不要改成从产物目录现算。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:99; plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：加一句「分组键在 runs.config 里缺失时 analysis 开 issue 给 gyb（kind 是 cannot），由 gyb 定是补跑、是换口径、还是走 code_path 从产物目录现算」。

### run-crash-midway（40 步，gyb 动手 4 次）

8. [slows/missing] 第 31、40 步：数字账里 killed 的 r1 和 ok 的 r2 挂同一个 handoff_id，没有任何字段标「r1 这条不算数」。build-plan.md:137 的 `rl run list --handoff/--decision` 会同时吐两条，analysis 按决定或 batch 分组时（next-steps.md:80 说 analysis 要顺决定到发射单到 run_id 这条链）会把废跑混进来；build-plan.md:144 的 doctor 也不扫这种情况（r1 有对应发射单，不报）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：`rl run list` 默认只出 exit_status=ok 的行，要废跑加 `--all`。

### n-launch-orders（58 步，gyb 动手 10 次）

14. [slows/missing] 第 46 步：同一张发射单重跑之后名下挂了两条 run（一条 killed 一条 ok），`rl run list --batch` 会把 6 条一起吐出来，去重和筛掉失败的规则没写，analysis 按 batch 拉数分组的时候同样吃到这 6 条。这一步只能自己挑。
   - 依据：2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-next-steps.md:80
   - 改法：rl run list 默认只出 exit_status=ok 且每张发射单取最新一条，加 --all 才出全部。

15. [slows/ambiguous] 第 48 步：跨 run 的聚合数算谁的活，两种读法都说得通。一种读法：idea 读九本账全部，runs 账的 metrics 就在里面，自己把 5 个数平均一下没人拦。另一种读法：规矩 5 说派生量只用 approved 的口径、由 analysis 算，均值方差正是派生量，idea 自己算就是自作主张。
   - 依据：2026-08-16-research-loop-next-steps.md:52; 2026-08-16-research-loop-next-steps.md:30; 2026-08-16-research-loop-build-plan.md:249
   - 改法：明写一句：单个 run 的 metrics idea 可以直接引，任何跨 run 的聚合一律走 analysis 分析单。

18. [slows/too_heavy] 第 21 步：同一批数字要在两处各填一遍：先按宿主流水线 run.py record finish 写 ops/runs.jsonl，再 rl run finish 写 loop/runs.jsonl，两本并存不合并，谁对账没写。5 张单就是 10 次填数。
   - 依据：2026-08-16-research-loop-build-plan.md:163; 2026-08-16-research-loop-next-steps.md:148; .claude/skills/gpu-run/SKILL.md:143
   - 改法：让 rl run finish 顺带调宿主的 record finish（或反过来），一次输入两本账都落，doctor 加一条两本对账的扫描。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

14. [slows/missing] 第 14、23 步：被收回的发射单跑出来的那条 run（exit killed、config 记的是旧评测集）留在 loop/runs.jsonl 正账里，没有任何作废标记。决定来源的第三类就是 run_id（next-steps.md:46），后面谁都能拿它当来源；doctor 的扫描项（build-plan.md:144）也不查「run 挂在已收回的单子上」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：doctor 加一条扫描「runs 行的 handoff 已 withdrawn」，并且 `rl decision add --source run:ID` 引到这种 run 时当场警告。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

4. [slows/ambiguous] 第 5 步：batch 一个字段被当成两种粒度用。设计文档定义 batch 是 deploy 一次开 N 张发射单的共用标签（分片级），修订记录却把「两条 idea 线归不了组」列成靠 batch 标签解决的问题（研究线级）。gyb 打 --group-by batch 看到的到底是两条线还是两次分片，两种读法都说得通。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:68; plans/2026-08-16-research-loop-next-steps.md:214; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：batch 只保留分片语义，线级归组交给新加的 line 字段，把修订记录里「两条 idea 线归不了组」那一项的解决办法改成 line。

### smoke-fails（44 步，gyb 动手 4 次）

7. [slows/missing] 步 34（rl run add 落发射版）：runs 发射版必填 config 字典，里面要有 model、params、dataset、split，是给 analysis 分组用的；但发射单的 launch 子对象只有 command、args、workdir、estimated_seconds、step_table、actual_seconds，没有 config。run 要么去解析命令行参数，要么去读 experiments/ 的代码猜这四个值，而这四个值本来是 deploy 定的。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：把 config 挪到发射单上由 deploy 开单时填，rl run add 默认从发射单抄，run 只补机器和卡。

### periodic-reclaim（27 步，gyb 动手 11 次）

12. [slows/principle_violation] 第 23 步：违反原则 1。runs 账的行格式写死「actor 必须是 run」，而原则 1 说任何权限检查对 gyb 一律不生效。gyb 要给回收下来的孤儿发射版补一条 exit=killed 的收尾版，按前一句写不进去，按原则 1 写进去就破了 schema，入账脚本按哪一条实现没有定论。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：runs 账的 actor 改成允许 run 或 gyb，字段表那一句后面补「gyb 例外，同原则 1」。

### doctor-findings-fix（24 步，gyb 动手 15 次）

2. [blocks/blocked] 第 21、22、23 步（修第三类）：「runs 行没有对应发射单」这一类没有可用的修法：runs 的写命令只有 add 和 finish，第三节只定义了 version 1 发射版和 version 2 收尾版，没有第三版；handoff 编号自动分配，补开一张 launch_order 也补不进已有 runs 行的 handoff_id（账只增不改）。gyb 按文档走到这里做不下去，doctor 每次都会继续报这一条。
   - 依据：2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:133; 2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-next-steps.md:92
   - 改法：加一条 `rl run relink RUN_ID --handoff ID`，作为 runs 的第三版（只允许补 handoff_id），或者给 doctor 加一条 acknowledge 命令把确认过的孤儿行消音。

3. [blocks/contradiction] 第 23 步（gyb 能不能手写 runs 行）：设计文档说「第二层是入账校验，硬的……gyb 例外」，读起来 gyb 连必填字段和 actor 限制都免；施工计划说「actor 是 gyb 时跳过全部『谁能调』和转移表『谁能写』的检查」，读起来只免这两类。runs 那一行写着 actor 必须是 run，gyb 到底能不能补写一行 runs 直接取决于这两句谁算数。
   - 依据：2026-08-16-research-loop-next-steps.md:134; 2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:63
   - 改法：在施工计划第六节写死一句「gyb 只豁免谁能调与转移表谁能写，schema 必填与 actor 限制对 gyb 同样生效」，并把设计文档那句「gyb 例外」改成同一句话。

11. [slows/guessed] 第 21 步（第三类到底指什么）：「runs 行没有对应发射单」有两种读法：handoff_id 为空，还是 handoff_id 指向的单子不存在或者 work_type 不是 launch_order。命令表里 `rl run add --handoff ID` 看着是必给的，第一种读法在文档里产生不出来，我只能猜是第二种，而文档也没写这条脏数据是怎么进来的。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-build-plan.md:63
   - 改法：把这一项改写成「runs.handoff_id 为空、悬空、或者指向的单子 work_type 不是 launch_order」，并在旁边注一句它怎么产生。

## 裁决记录（日期）

- 2026-08-17：来自 `03-ledgers.md` 的裁决（gyb：「我感觉很轻松能从data_path 找出artifact_path啊，而且artifact path定义有点暧昧 能不能不要了」「选A吧那就」），runs 发射版去掉 `artifact_dir`，产物目录按约定是 `<artifact_root>/<run_id>/`、账上不记；收尾版留 `data_path`（`exit_status` 是 `ok` 时必填，是产物目录里给 analysis 算数用的那一个文件或子目录）。统筹 session 同步。
