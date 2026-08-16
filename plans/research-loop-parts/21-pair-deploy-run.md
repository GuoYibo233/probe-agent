# deploy 与 run 之间的交流

> 这份覆盖发射单 launch_order 这一条通道的全部：单子上的 attempts 结构、父单与继承、batch、从开单到验收的整条路、run 的四种失败 issue 回到 deploy 的 amend 与 resume 回路、认领、后台起 run、runs 账当交付物、转移表里和这条通道有关的行、收回和回收时 run 怎么中断。
> 不覆盖：deploy 这个角色自己怎么写代码、写报告、走快车道（`11-role-deploy.md`、`07-quick-lane.md`）；run 这个角色自己的探卡、挑卡、看门狗判定（`12-role-run.md`）；工单 work_order 这条通道（`20-pair-idea-deploy.md`）；runs 账给 analysis 用的那一面（`23-pair-run-analysis.md`）；九本账的完整行格式（`03-ledgers.md`）；转移表全表和会话生命周期（`04-handoffs-and-sessions.md`）；`bin/rl` 全命令表（`05-rl-cli.md`）；钩子与角色 json（`06-hooks-and-permissions.md`）；宿主发射器对接与配置（`08-trees-init-and-host.md`）。
> 源：设计文档的「五个角色」总段、deploy 一节、run 一节、「账本」一节、「交接与会话生命周期」一节，以及原则 3、4、9、10、11；施工计划第一节（裁决 (a)(g)、另定两条）、第二节词表、第三节 handoffs 与 runs 的字段、第四节转移表、第五节 deploy 与 run 的 use case、第六节命令表、第七节 run 照 gpu-run 写、第八节阈值、第六节 doctor 那一行。

## 一、这条通道是什么

deploy 和 run 之间只有一样东西在走，就是发射单。发射单的 `work_type` 是 `launch_order`，`from_role` 是 `deploy`，`to_role` 是 `run`，owner 就是 deploy。deploy 写代码、定命令、开单、验收；run 探卡、smoke、发射、看门、收尾、落数字。

分工是钉死的两条：deploy 不跑 smoke、不估时长，这两样都是 run 的活；run 不修代码、不重试，出问题一律开 issue 回 deploy，重来是这张发射单上的下一次尝试。

一张发射单是多次尝试的容器（原则 10）。smoke 失败、发射失败、跑挂、修完再来，每一次是单子上的一个 attempt，各带自己的命令、分步表、预计时长和 run 行。同一张单子不因为失败就作废，也不因为失败就开新单。

派活不占终端（原则 11）。deploy 开完发射单后台起一个 run 的 subagent 接走，deploy 会话继续可用；run 回来的时候 deploy 验收。deploy 会话先结束了，单子照常在账上等 owner 下次上线或者 gyb 验收。GPU 任务本体在 tmux 里跑，不跟会话走。

## 二、发射单上的 attempts

`attempts` 是一个列表，只在 `launch_order` 上。每一项的形状是 `{"attempt":序号,"command","args","workdir","track","config":{...},"run_id","estimated_seconds","step_table":[...]}`。

| 字段 | 谁填 | 说明 |
|---|---|---|
| `attempt` | rl | 尝试序号 |
| `command` | deploy | 开单时第一项必填 |
| `args` | deploy | 参数 |
| `workdir` | deploy | 工作目录，开单时第一项必填 |
| `track` | deploy | 宿主发射器要的方向名，从被派的工单继承或者 deploy 填；开单时第一项必填 |
| `config` | deploy | 字典，键是 `model`、`params`、`dataset`、`split`，其余超参自由；开单时第一项必填 |
| `run_id` | rl | 按 `<ho-id>-a<attempt>` 分配 |
| `estimated_seconds` | run | 预计时长，只加总最新一次尝试的 `step_table` 行 |
| `step_table` | run | 分步表，每项 `{"step","kind":"gpu"\|"cpu","smoke_seconds","scale_factor","estimated_seconds"}` |

`config` 是给 analysis 分组用的（见 `23-pair-run-analysis.md`），由 deploy 在开单时填，`rl run add` 默认从发射单抄，run 只补机器和卡。

## 三、父单、决定引用、batch、line

`launch_order` 的 `parent_id` 必填，指它所属的工单。开单时 rl 从父单抄 `decision_refs` 和 `batch`，`line` 由 rl 从 `decision_refs` 第一项的 `root_id` 算出来存着。这条链是原则 9 要的：从任何一个编号打 `rl trace` 都能顺回 run 到发射单到工单到决定。

两处原文不一致：设计文档「五个角色」总段那一句写「run 的 inbox 不查过版，发射单不引决定」，同一份文档的 deploy 一节和施工计划第三节都写发射单开单时从父单继承决定引用。按施工计划的表，发射单上带 `decision_refs`；「run 的 inbox 不查过版」这一句照旧。

`batch` 形如 `b-20260816-01`，rl 在锁里分，只有分片语义，不表示研究线；研究线归组用 `line`。deploy 一次开 N 张同 `batch` 的发射单时，只起一个 run 会话接整个 batch，不再一个 workflow 起 N 个 run 各自探卡抢同一张卡。

## 四、开单

deploy 打 `rl handoff open --type launch_order --to run --parent ho-XXXX --command ... --workdir ... --track ... --config k=v ... [--batch B] [--manual|--no-dispatch]`，单子落 `todo`。

前提是 `parent_id` 加第一次尝试的 `command`、`workdir`、`track`、`config` 四样齐。开单的时候不查交付物（原则 4 推论），交付物是交活那一刻才查的东西。

派发方式三个取值：`auto` 时 deploy 后台起 run 的 subagent；`manual` 时 deploy 只开单，gyb 自己开 session 去接；`none` 时单子停在 `todo` 等 gyb 说开跑。

## 五、run 接单：先看认领，再走 smoke

run 接单的第一件事是看这张单最新一次尝试有没有已经发射还没收尾的 run 行。有就认领：不重新 smoke、不重新发射，只接管看门狗和收尾，账行标 `adopted`。没有才走 smoke。

`rl handoff start ID [--batch B]` 的前提有两条：写入会话的角色等于 `to_role`；`holder` 为空，非空退出码 2 并列出当前 holder。

一个 run 会话用 `rl handoff start --batch B` 一次接下整个 batch：smoke 做一次、分步表填一次、探卡挑卡一次、按宿主发射器自己的分片规矩发射 N 份、落 N 条 run 行。

## 六、smoke、分步表、预计时长

预计时长不许模型自己猜，也不许拿一题时间乘题数。run 先读代码列出每一步都干了什么，smoke 的时候给每一步计时，GPU 步按规模外推（装载一次大模型这类一次性开销也是 GPU 步，只算一次），CPU 步很短可以忽略，加总填进这次尝试的时长字段。

填分步表的命令是 `rl handoff estimate ID --step NAME --kind gpu|cpu --smoke-seconds S --scale F`，往最新一次尝试追加一行，`estimated_seconds` 加总本次尝试。同 batch 的其余单子用 `rl handoff estimate ID --copy-from ID2 [--scale F]` 复制，只实测一张。

smoke 的标准输出一律落到 `artifact_root/smoke/<run_id>.log`，开 issue 的时候 `--log-tail` 指它。

smoke 就失败的时候，分步表和预计时长还没有，单子直接标卡住，这两样不是标卡住的前提。

## 七、发射与 runs 两版

发射前 commit，然后按配置里的 `launcher.launch_cmd` 发射，`--run-id` 和 `--track` 从发射单的这次尝试上抄。

数字账一张单子一次尝试两版：

| 版 | `status` | 必填 |
|---|---|---|
| 发射版 | `launched` | `commit`、`command`、`host`、`gpus`、`log_path`、`tmux_session`、`watch_cmd`、`started_at`、`config`（从发射单抄） |
| 收尾版 | `finished` | `finished_at`、`exit_status`（`ok`、`failed`、`killed`）、`actual_seconds`；`exit_status` 是 `ok` 时还要 `metrics` 和 `data_path` |

`run_id` 是 runs 账的主键，形如 `ho-0013-a1`，和产物目录名、tmux session、commit message 一致；产物目录按约定是 `<artifact_root>/<run_id>/`，账上不另记。runs 账只有 run 角色的脚本能写，gyb 例外。

`rl run finish` 干四件事：算 `actual_seconds`（从两个时间戳算，退出状态是什么都记）、同一个进程里跑反常预警、调宿主的收尾命令模板（new1 是 `run.py record finish`，ok 和失败都调）、落收尾版。

反常预警的阈值：`anomaly.metric_extremes` 默认 `[0, 1]`，指标落在这两个值上触发；`anomaly.duration_factor` 默认 3，实际耗时超过预计 3 倍触发。触发就当场开一条 issue，kind 是 `anomaly`，actor 记 run，归 gyb。

看门狗的超时线用最新一次尝试的 `estimated_seconds` 乘 `watchdog.timeout_factor`（默认 3）；卡死另判，和预计时长无关。看门狗本身是 run 的活，写在 `12-role-run.md`。

## 八、交付物：退出状态 ok 才算干完

发射单的交付物就一样：数字账里退出状态为 `ok` 的那一版。`rl handoff done` 的前提是最新一次尝试的 run 行有 `exit_status=ok` 的 `finished` 版，没有就不收。

`rl run list` 默认只出每张单最新一次尝试且 `exit_status=ok` 的行，`--all` 才把废跑和旧尝试一起出。

## 九、四种失败：run 开 issue，deploy 改完 amend 加 resume

run 出问题一律开 issue 回给 deploy，四种：smoke 失败、发射失败、跑挂、结果反常。前三种的 kind 是 `failed`，`stage` 分别取 `smoke`、`launch`、`crash`，assignee 是 deploy；结果反常的 kind 是 `anomaly`，归 gyb。issue 里带 `handoff_id`，附日志末 40 行和 traceback。run 不修代码、不重试。

失败或者被杀之后，发射单标 `stuck`：`rl handoff stuck ID --issue ID`，前提是那条 issue 已经存在并且它的 `handoff_id` 指回本单。写序定死先写 issue 拿到编号，再写单子那一行引它。

回路在 deploy 手上，四步：

1. deploy 改代码。
2. `rl handoff amend ID --command ... --workdir ...` 给发射单追加一次新的尝试，新命令、新工作目录都在这一版里；状态不变。
3. `rl issue reply ID --text`。
4. `rl handoff resume ID` 把单子交回 `todo`，前提是关联的 issue 状态已经是 `answered`；之后由 owner 也就是 deploy 再起一个 run。

`to_role` 的任何一个会话都能接回来的这张单，默认还是 owner 再起一个下游。

issue 的关闭：`rl handoff accept` 的时候自动关掉这张单关联的 `answered` issue；通知类的 issue 被 `rl inbox` 读过即关。doctor 有一项扫 `answered` 超过 `issues.answered_stale_days`（默认 3 天）没关的 issue。

## 十、deploy 验收发射单

`rl handoff accept ID` 由 owner 也就是 deploy 打。发射单被打回（`rl handoff reject ID --reason`）或者 run 会话销号把单子交回 `todo`，都由 deploy 重新起 run。

验收完之后 deploy 把 `run_id` 和关键指标补进带文件的那一份部署报告（`detail`），再提工单的 `done_pending_review`。工单那一头的交付物写在 `20-pair-idea-deploy.md`。

## 十一、转移表里和这条通道有关的行

下面几行照抄施工计划第四节，只留和 `launch_order` 有关的。`holder` 只在 `in_progress` 非空，进写、出清、`last_holder` 留下，表里不逐行写。

| 从 | 到 | 谁能写 | 前提 | 之后谁拉起 | 子命令 |
|---|---|---|---|---|---|
| （新建） | `todo` | `from_role` | `launch_order` 有 `parent_id` 和第一次尝试的 `command`、`workdir`、`track`、`config` | `dispatch=auto` 时 owner 后台起 subagent；`manual` 等 gyb；`none` 不动 | `handoff open` |
| `todo` | `in_progress` | `to_role` | 写入会话的角色等于 `to_role`；`holder` 为空（非空退出码 2 并列出当前 holder）；`launch_order` 最新尝试已有 `launched` 未 `finished` 的 run 行时是认领，账行标 `adopted` | 无 | `handoff start [--batch B]` |
| `todo` / `stuck` | `todo`（内容追加） | owner、`to_role` | 只改内容：`launch_order` 追加一次尝试；状态不变 | 无 | `handoff amend` |
| `in_progress` | `stuck` | holder | `issue_id` 指向一条已存在的 issue，并且那条 issue 的 `handoff_id` 指回本单 | 无 | `handoff stuck` |
| `stuck` | `todo` | 回了 issue 的那个角色、owner | 关联 issue 状态是 `answered` | owner | `handoff resume` |
| `in_progress` | `done_pending_review` | holder | `launch_order` 最新尝试的 run 行有 `exit_status=ok` 的 `finished` 版 | 无 | `handoff done` |
| `done_pending_review` | `accepted` | owner | 无；gyb 越过 owner 时 rl 给 owner 发 `fyi` | 无 | `handoff accept` |
| `done_pending_review` | `rejected` | owner | `reason` 非空；gyb 越过 owner 时 rl 给 owner 发 `fyi` | owner | `handoff reject` |
| `rejected` | `todo` | owner、`reclaim` | 无 | owner | `handoff release` |
| `rejected` | `in_progress` | `to_role` | 写入会话的角色等于 `to_role`（原会话还活着直接接着干） | 无 | `handoff start` |
| `todo` / `in_progress` / `stuck` / `done_pending_review` / `rejected` | `withdrawn` | owner | `reason` 非空（角色会话发起还要 `quote`）；有 holder 时 rl 顺带开 `withdrawn` 通知给 holder 的角色和 owner；`--cascade` 时 rl 代 owner 连 `parent_id` 指向本单的下游单一起收，下游账行 actor 记发起人 | 无 | `handoff withdraw` |
| `in_progress` | `todo` | 销号钩子、`reclaim`、owner | `progress_note` 非空（钩子和 reclaim 自动填）；`launch_order` 且最新尝试有 `launched` 未 `finished` 的 run 行时不杀进程（等下一个 run 认领），reclaim 带 `--kill` 才先走中断收尾；rl 给 owner 开 `orphaned` 通知；销号钩子写的这一版 `actor` 记会话的角色、`via=session_end`，reclaim 写的 `actor` 记 gyb、`via=reclaim` | owner 照单子原来的 `dispatch` 拉起（`auto` 再起一个 subagent），owner 无活会话时进 `rl status` 的「等 gyb 拉起」 | `handoff release` |

`accepted` 和 `withdrawn` 是终态，表外的转移一律拒收，退出码 2。

## 十二、收回和回收时 run 怎么中断

被收回、被回收这两种中断，run 只做 `rl run finish --exit killed` 加收尾，不再改单子状态；状态由收回那一步或者回收那一步改。看门狗每轮采样顺带查一次本单状态，见到被收回或被回收就走中断流程。

`rl handoff withdraw` 走的是收回：owner 写，`reason` 非空，角色会话发起还要 `quote`；有 holder 的时候 rl 顺带开一条 `withdrawn` 通知给 holder 的角色和 owner；`--cascade` 沿 `parent_id` 把派生的下游单一起收，所以 idea 收工单的时候能连着收掉正在烧卡的那张发射单。

`rl reclaim` 走的是回收：开干的发射单默认不杀进程，留给下一个 run 认领；带 `--kill` 才先走中断收尾，杀进程、释放显存、宿主销号、runs 落 `killed`，然后交回 `todo`。

两处原文不一致：设计文档「交接与会话生命周期」一节写「回收对开干的发射单先走中断收尾（杀进程、释放显存、宿主销号、runs 落 killed）再交回待干」，施工计划第四节转移表和第六节 `rl reclaim` 那一行写「默认不杀进程（留给认领），`--kill` 才走中断收尾」。按施工计划的表，默认不杀，`--kill` 才杀。

run 会话销号也走 `handoff release`：单子交回 `todo`，填 `progress_note`，给 owner 开 `orphaned` 通知，GPU 进程不动，下一个 run 会话接单时认领。

## 十三、这条通道上的对账

doctor 里和发射单相关的扫描项：runs 行 `handoff_id` 为空、悬空或者不是 `launch_order`（修法 `run relink` 或 `--ack`）；runs 有 `launched` 版长期没 `finished` 版；runs 挂在 `withdrawn` 的单子上；`stuck` 单子没有 issue（修法 `issue link`）；`loop/runs.jsonl` 与宿主 `ops/runs.jsonl` 对不上的 run_id。

## 和别的 part 的接口

- `parent_id` 指的工单、工单的交付物与验收：`20-pair-idea-deploy.md`。
- `decision_refs`、`root_id`、`line`、决定的版本与过版：`03-ledgers.md`、`25-pair-reviewer-idea.md` 里的决定账那一头由 `03-ledgers.md` 定。
- handoffs 与 runs 的完整行格式、公共骨架七样（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`）：`03-ledgers.md`。
- 转移表全表、`holder` 与 `last_holder` 的不变量、会话销号与 `orphaned`：`04-handoffs-and-sessions.md`。
- issue 的九种 `kind`、`stage`、`reply` 与 `close` 的权限：`03-ledgers.md`。
- `rl handoff open/start/amend/stuck/resume/done/accept/reject/withdraw/release/reissue/estimate`、`rl run add/finish/list/relink`、`rl issue open/reply`、`rl trace`、`rl reclaim`、`rl doctor` 的完整签名和退出码：`05-rl-cli.md`。
- deploy 和 run 的 `reads`、`writes`、`ledger_writes`、`dispatches_to`、`model`：`06-hooks-and-permissions.md`。
- 看门狗判定、探卡挑卡、gpu-run 八个阶段的对照：`12-role-run.md`。
- 快车道里的 GPU 怎么跑、`ql_tag` 当 run_id：`07-quick-lane.md`。
- `artifact_root`、`launcher.launch_cmd`、`launcher.finish_cmd`、`gpu_state_path` 这些配置项和宿主台账对接：`08-trees-init-and-host.md`。
- `runs` 账的 `config` 给 analysis 分组用的那一面：`23-pair-run-analysis.md`。
- 阈值 `watchdog.timeout_factor`、`anomaly.metric_extremes`、`anomaly.duration_factor`、`issues.answered_stale_days` 的默认值表：`08-trees-init-and-host.md` 第三节阈值表（2026-08-17 gyb 裁）。

## 源文档没写清的（留给 gyb）

1. 发射单到底带不带 `decision_refs`：设计文档一处说不引决定，另一处和施工计划说从父单继承，见上文第三节的不一致标注。这条要 gyb 定一个值。
2. `actual_seconds` 谁算：施工计划第三节和设计文档都说 `rl run finish` 从两个时间戳算，第六节命令表的 `handoff done` 又留着一个 `--actual-seconds N` 参数。两处原文不一致，按表是 rl 算，那个参数留着干什么没写。
3. 认领时账行标 `adopted`，但第三节 handoffs 的字段表里没有 `adopted` 这个字段，标在哪一栏没写。
4. `rl handoff amend` 追加一次尝试的时候，新的 `run_id` 是不是按新的 `attempt` 序号重新分配，命令表和转移表都没写。
5. `attempts` 里的 `args` 不在开单必填之列，它和 `command` 的分工（是不是命令行拆开写）没写。
6. 一个 run 会话接整个 batch 的时候，N 张单的 `host` 和 `gpus` 怎么分、分完写回哪里没写；`rl handoff start --batch B` 是不是一次把 N 张单都置 `in_progress` 且 `holder` 都记同一个会话，表里只有单张单的那一行。
7. deploy 后台起 run subagent 用什么机制、workflow 或 agent 定义文件放插件树的哪里没写，挂在待验证第 8、9 条上。
8. 发射单被 `reject` 之后要不要 `amend` 一次新尝试再跑，还是直接拿最新尝试重发，没写。
9. deploy 验收发射单的时候看什么、什么情况下该 `reject` 一张 `exit_status=ok` 的发射单，没写。
10. 认领的那个 run 会话怎么接管看门狗（原来的看门狗进程还在不在、状态文件在哪），没写。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

下面的条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，只有模拟没有核实，不做判断、不改字。

### run-crash-midway（40 步，gyb 动手 4 次）

4. [slows/missing] 第 19 步：转移表 build-plan.md:85 的 stuck→todo（谁能写=回了 issue 的那个角色，前提=关联 issue 已 answered）在 bin/rl 命令表 build-plan.md:134 里没有对应子命令，只能借 `release`；而 release 在转移表 build-plan.md:93 那一行的谁能写是「销号钩子、reclaim、owner」、前提只有「holder 清空」，借它就绕开了「issue 必须已回」这个前提。本场景 deploy 恰好既是 owner 又是回 issue 的人才糊得过去，工单场景（owner 是 idea、holder 是 deploy、回 issue 的是 idea）同样糊得过去但语义已经错位。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：给这一行加一个专门的子命令 `rl handoff resume ID`，前提校验关联 issue 是 answered。
5. [blocks/blocked] 第 24 步：deploy 修完代码之后，发射单 ho-0013 的 launch.command 和 args 还是崩之前那一版，命令表 build-plan.md:134 里没有任何改 launch 子对象的子命令，账又是只增不改（next-steps.md:92）。三条路都不通：带着旧命令跑（跑的和账上写的不一样）、开一张新发射单（旧单子只能 withdraw，转移表里 stuck 走不到重开）、手改账（钩子和入账校验都禁止）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-next-steps.md:92
   - 改法：加 `rl handoff relaunch ID --command ... --workdir ...`：给发射单追加一版新的 launch 子对象并把状态带回 todo。
6. [slows/missing] 第 26 步：重跑时分步表没法重置。build-plan.md:135 写明 `rl handoff estimate` 是「往发射单追加分步表一行，estimated_seconds 自动加总」，崩之前那一轮的行还在单子上，第二轮 smoke 的行加上去，estimated_seconds 变成两轮之和，超时判定线（build-plan.md:176 timeout_factor=3 乘 estimated_seconds）跟着虚高三倍，等于关掉了超时看门狗。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:135; plans/2026-08-16-research-loop-build-plan.md:176
   - 改法：`rl handoff estimate` 加 `--reset` 或按重跑轮次分组，estimated_seconds 只加总最新一轮的行。
7. [slows/missing] 第 11 步：崩掉的这一跑没有地方回填真实耗时。`--actual-seconds` 只挂在 `rl handoff done`（build-plan.md:134、:61），而 stuck 这条路永远走不到 done，所以 next-steps.md:70 说的「跑完之后 run 把真实耗时回填，几次之后就知道外推偏多少」在崩溃场景下拿不到样本，偏偏崩之前跑到一半的那段耗时正是校准外推最有用的数据。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:70
   - 改法：把 actual_seconds 挪到 `rl run finish` 上，从 started_at 和 finished_at 自动算，不管退出状态是什么都记。
8. [slows/missing] 第 31、40 步：数字账里 killed 的 r1 和 ok 的 r2 挂同一个 handoff_id，没有任何字段标「r1 这条不算数」。build-plan.md:137 的 `rl run list --handoff/--decision` 会同时吐两条，analysis 按决定或 batch 分组时（next-steps.md:80 说 analysis 要顺决定到发射单到 run_id 这条链）会把废跑混进来；build-plan.md:144 的 doctor 也不扫这种情况（r1 有对应发射单，不报）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：`rl run list` 默认只出 exit_status=ok 的行，要废跑加 `--all`。
9. [slows/missing] 第 38、39 步：issue 从 answered 到 closed 谁打、什么时候打没写。run 的 ledger_writes 只有 issue open（build-plan.md:105），deploy 和 idea 都有 close（:101、:103）但没规定何时用；`rl status` 七段（:142）只列改派给 gyb 超时的 issue，`rl doctor` 八项（:144）也不扫 answered 未 close 的 issue。结果是每次崩溃都留一条挂着的 issue，只有 gyb 偶然翻到才收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl handoff accept` 时自动 close 掉这张单子关联的 answered issue，doctor 补一项「answered 超过 N 天没 close」。
10. [slows/too_heavy] 第 12 到 20 步：三层会话同步嵌套等待：idea 等 deploy 等 run（next-steps.md:120、:58）。一个训练跑几小时，崩了之后 deploy 修完还要再等一整轮重跑，sess-idea-01 从派单到验收全程挂着不能做别的，与 next-steps.md:7「想法要快速、多次迭代」直接冲突。待验证第 9 条（build-plan.md:197）只测了一层（deploy 等 run），没测两层嵌套，备案也只写了 deploy 那一层。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：发射单一旦标 stuck 就让上游 subagent 立刻返回并销号，重跑由 gyb 在 `rl status` 里另起一个 deploy 会话接。
11. [slows/too_heavy] 第 16 到 20 步：deploy 改完一行超参之后，没有任何办法自己确认修对了：next-steps.md:58 明写 deploy 不跑 smoke，快车道要 gyb 点名才能进（next-steps.md:64），所以每一次修复都得走「起 run 会话 → 读档案 → 探卡 → 挑卡 → smoke → 填分步表 → 发射前 commit → 发射」全套；smoke 再挂就又是一条 issue 一轮循环。改一个 batch size 的代价和跑一个新实验一样。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：允许 deploy 在修 stuck 的发射单时不经 gyb 点名跑一次 smoke 规模的自测，结果写进杂账。
12. [slows/missing] 第 9、14 步：归角色（不是 gyb）的 issue 没有任何推送，角色上线也没规定要查。build-plan.md:59 只有 assignee 变成 gyb 那一版触发通知，build-plan.md:131 规定的「角色上线第一个动作」只有 `rl decision stale`。本 trace 里 deploy 会话正同步等着才立刻收到；一旦按待验证第 9 条的备案（build-plan.md:197）改成 deploy 开单即销号，iss-0031 就静静躺在账里没人知道，只能等 gyb 打 `rl status`。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：角色上线第一个动作改成两条：`rl decision stale` 加 `rl issue list --open --to <本角色>`。
13. [slows/guessed] 第 9 步：跑挂该开哪种 kind 的 issue，只能猜。build-plan.md:45 的六种 kind 是 cannot / not_mine / denied / anomaly / request / withdrawn，没有一种对应「跑挂」；build-plan.md:166 给的命令模板直接写成 `rl issue open --to deploy --kind ...` 把 kind 留空；next-steps.md:72 列了四种要开 issue 的情形（smoke 失败、发射失败、跑挂、结果反常）但只给结果反常指定了 anomaly。本 trace 取 cannot 是猜的，四种情形挤进一个 kind 之后 `rl issue list` 没法按失败类型筛。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：给 run 的四种失败各定一个 kind（smoke_failed / launch_failed / crashed / anomaly），写进第二节词表。
15. [cosmetic/missing] 第 6、27、30 步：崩溃分支下宿主那本账怎么收没写。build-plan.md:163 只在 Phase 6a 说明「数字进 loop/runs.jsonl，new1 的 ops/runs.jsonl 照旧由 run.py launch 写，两本并存」，:164 的 Phase 6b 完全没提宿主账，所以 r1 在 ops/runs.jsonl 里那条永远停在 `record start` 没有 finish，宿主的 RESULTS.md 缺一行。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:163; plans/2026-08-16-research-loop-build-plan.md:164; plans/2026-08-16-research-loop-next-steps.md:148
   - 改法：Phase 6b 那一行补一句：`rl run finish --exit failed|killed` 的同时打宿主的 `python3 run.py record finish <run_id>`。
16. [cosmetic/contradiction] 第 23 步：卡住的单子被回复之后谁能接，两处说法不一样。next-steps.md:116 写「卡住的 issue 被回复之后单子回待干，谁接都行」，转移表 build-plan.md:83 的 todo→in_progress 那一行前提写死「写入会话的角色等于 to_role」。按正文任何角色都能接，按表只有 run 能接。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:116; plans/2026-08-16-research-loop-build-plan.md:83
   - 改法：把 next-steps.md:116 的「谁接都行」改成「to_role 的任何一个会话都能接」，与转移表对齐。
17. [cosmetic/missing] 第 34 步：崩过一次这件事在两份部署报告里没有落点。next-steps.md:56 规定 method 那份只讲做法、用了什么技术、数据怎么被处理，detail 那份带文件和处理细节，两份都不装失败史；reviewer 拿 method 那份当锚审「代码和决定是不是一回事」时，看不到「原来的 batch size 跑不动」这条，只能自己去 issues 账翻。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:88
   - 改法：detail 那份加一栏「这张单子上关联的 issue 编号和结论」，由 `rl handoff show` 自动列。

### n-launch-orders（58 步，gyb 动手 10 次）

1. [blocks/missing] 第 10、46 步：发射单挂不到工单和决定上：handoffs 的字段表里没有父单字段，转移表对 launch_order 新建也不要求 decision_refs，所以「决定 → 工单 → 5 张发射单 → run_id」这条链在账上是断的。idea 只能从 detail 报告的正文里抄 batch 标签和 run_id 才拿得到这批数字，`rl decision show --with-runs`、`rl run list --decision`、doctor 的「快车道工单已 accepted 但没有关联发射单」三处都没有可走的字段。
   - 依据：2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:81; 2026-08-16-research-loop-build-plan.md:130; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-next-steps.md:64; 2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个 parent_handoff 字段，launch_order 和 analysis_order 新建时必填，并自动从父单继承 decision_refs 和 batch。
2. [blocks/missing] 第 11 步：deploy 用什么起那个 workflow、workflow 定义文件放在插件树的哪里、5 张单号怎么分派给 5 个 subagent，三样都没写。插件本体的目录清单里只有 skills/common/tables/schemas/scripts/bin/hooks/monitors/tests，没有 workflows/ 或 agents/；待验证第 8 条的备案里出现过「workflow 里的 agentType 指向 agents/<role>.md」，但那只是备案，正文没定。这个场景的核心机制整个是猜的。
   - 依据：2026-08-16-research-loop-next-steps.md:68; 2026-08-16-research-loop-next-steps.md:150; 2026-08-16-research-loop-build-plan.md:196
   - 改法：在插件树里加一层 workflows/fanout.js（或 agents/<role>.md），明写 deploy 起 N 个 run 时把单号、batch、分到的卡逐个写进 subagent 提示。
3. [blocks/principle_violation] 第 14 步：违反原则 3（每张派活单有 owner 和 holder，holder 是当前正在干这张单子的那一个会话）。转移表 todo→in_progress 那一行的前提只有「写入会话的角色等于 to_role」，没有「holder 为空」这一条，所以两个 run subagent 先后 start 同一张单是合法转移，后一个直接覆盖前一个的 holder，另一张单没人接却在账上看不出来。
   - 依据：2026-08-16-research-loop-build-plan.md:83; 2026-08-16-research-loop-next-steps.md:17
   - 改法：转移表 todo→in_progress 的前提加一句「holder 为空」，已有 holder 时退出码 2 并把当前 holder 列出来。
4. [slows/missing] 第 16 步：5 个 run subagent 各自实探空卡各自挑卡，中间没有任何互斥，发射单的 launch 子对象里也没有卡位字段，谁给哪张单分哪张卡文档没写。设计文档只说「一张卡一个 run」和「分片对应一次开 N 张同 batch 的发射单」。并发挑到同一张卡时宿主发射器逐 piece 实探非 FREE 就整次拒绝，这正是这个场景里「一张挂了」最容易发生的原因。
   - 依据：2026-08-16-research-loop-next-steps.md:68; 2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:159; .claude/skills/gpu-run/SKILL.md:30
   - 改法：launch 子对象加 host 和 gpus 两个字段，由 deploy 开 N 张单时一次分完；rl 对同一 batch 的挑卡加一把锁。
5. [slows/too_heavy] 第 17 步：同一个 batch 的 5 张单只差一个 seed，每个 run subagent 都要各自读一遍代码、列一遍步骤、跑一遍 smoke、逐步计时、逐步打 estimate。设计文档明说不给「分步计时只对长任务做」的口子，正常路的发射单一律做，于是同一份分步表被重复造 5 次，撞在「想法要快速多次迭代」这个总目标上。
   - 依据：2026-08-16-research-loop-next-steps.md:70; 2026-08-16-research-loop-next-steps.md:179; 2026-08-16-research-loop-build-plan.md:135; 2026-08-16-research-loop-build-plan.md:160
   - 改法：加一条 `rl handoff estimate ID --copy-from <同 batch 的另一张单>`，同 batch 只让第一张单实测分步表，其余按规模系数复制。
6. [slows/missing] 第 34 步：发射单被重跑时分步表没有清空或分版：estimate 是「往发射单追加分步表一行，estimated_seconds 自动加总」，第二次 smoke 的行加在第一次的行后面，预计时长变成两次之和。后果是看门狗的超时线（estimated_seconds 乘 3）和反常预警的 duration_factor 两处一起失真。
   - 依据：2026-08-16-research-loop-build-plan.md:135; 2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:176; 2026-08-16-research-loop-build-plan.md:181
   - 改法：分步表按尝试分组（每次 handoff start 起一个 attempt 号），estimated_seconds 只加总最新一个 attempt 的行。
8. [slows/contradiction] 第 25 步：转移表里 stuck→todo 有两行且前提打架：一行要求「关联 issue 状态是 answered」，另一行允许销号钩子和 reclaim 只清 holder 就把 stuck 降回 todo。run5 一销号，ho-0017 就在 issue 还没被 deploy 回复的情况下变回 todo，owner 按规矩可以立刻再起一个 run，代码没改照样再挂一次。
   - 依据：2026-08-16-research-loop-build-plan.md:85; 2026-08-16-research-loop-build-plan.md:93; 2026-08-16-research-loop-next-steps.md:117
   - 改法：销号钩子和 reclaim 对 stuck 单只清 holder、状态留在 stuck，只有 issue 转 answered 之后才允许回 todo。
9. [cosmetic/missing] 第 24 步：run 出问题的四种情况里，只有「结果反常」在 issue 的六种 kind 里有对应值（anomaly），smoke 失败、发射失败、跑挂三种该填哪个 kind 没写，施工计划第七节那一句直接写成 `--kind ...`。这里只能挑了 cannot。
   - 依据：2026-08-16-research-loop-build-plan.md:45; 2026-08-16-research-loop-build-plan.md:166; 2026-08-16-research-loop-next-steps.md:72
   - 改法：issue 的 kind 加一个 failed（或把三种失败明写成一律用 cannot），并在 run 的 SKILL.md 里一种失败对一个 kind 列成表。
10. [slows/missing] 第 18 步：run_id 谁定、什么格式没写，只写了它要和产物目录名、tmux session、commit message 一致；宿主发射器还硬要求一个 --track 且要和 TIMELINE.md 的方向对得上，插件九本账里根本没有 track 这个字段，也没写谁给。batch 标签同样没有格式（对比 ql_tag 是给了格式的）。这三样在这一步全靠猜。
   - 依据：2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:161; 2026-08-16-research-loop-build-plan.md:49; 2026-08-16-research-loop-next-steps.md:68; .claude/skills/gpu-run/SKILL.md:86
   - 改法：launch 子对象加 run_id 和 track 两个字段由 deploy 开单时填，batch 照 ql_tag 的样子定成 b-<日期>-<序号>。
12. [slows/missing] 第 18、20 步：5 个 run subagent 的监控入口到不了 gyb 眼前。gpu-run 要求发射后把 gpu-jobs watch 和网页交给用户，但 subagent 的输出只回到 deploy 会话；rl status 列的是单子状态和挂了多久，不含进度、速率、ETA。gyb 在这几个小时里看不到这一批五张卡跑到哪了。
   - 依据：.claude/skills/gpu-run/SKILL.md:97; 2026-08-16-research-loop-build-plan.md:161; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:124
   - 改法：rl run add 时把宿主的 tmux session 名和监控命令写进 runs 行，rl status 按 batch 汇一段进度出来。
13. [slows/missing] 第 26 步：待验证第 9 条（上游 subagent 同步等几小时会不会被超时收掉）的备案正好落在这个场景上，但备案没给续跑规矩：一旦 deploy 开完单就销号，ho-0012 会被销号钩子交回 todo、报告还没写、5 张发射单已经派出去，下一个 deploy 会话重新 start 之后怎么知道进度到哪、去哪找那个 batch，文档没写。
   - 依据：2026-08-16-research-loop-build-plan.md:197; 2026-08-16-research-loop-build-plan.md:93; 2026-08-16-research-loop-next-steps.md:120
   - 改法：备案里补一句：work_order 也记 batch，重新 start 时第一件事是 rl handoff list --batch 复原五张单的状态。
14. [slows/missing] 第 46 步：同一张发射单重跑之后名下挂了两条 run（一条 killed 一条 ok），`rl run list --batch` 会把 6 条一起吐出来，去重和筛掉失败的规则没写，analysis 按 batch 拉数分组的时候同样吃到这 6 条。这一步只能自己挑。
   - 依据：2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-next-steps.md:80
   - 改法：rl run list 默认只出 exit_status=ok 且每张发射单取最新一条，加 --all 才出全部。
17. [cosmetic/missing] 第 13 步：run 上线第一个动作是跑 rl decision stale，但 run 的角色 json 里 reads 不含 decisions 账，发射单上也没有 decision_refs，这条检查对 run 是空转。
   - 依据：2026-08-16-research-loop-build-plan.md:131; 2026-08-16-research-loop-build-plan.md:105; 2026-08-16-research-loop-build-plan.md:81
   - 改法：把「上线跑过版检查」限定给 idea、deploy、analysis 三个角色，或者让 launch_order 继承父工单的 decision_refs 之后 run 再查。
18. [slows/too_heavy] 第 21 步：同一批数字要在两处各填一遍：先按宿主流水线 run.py record finish 写 ops/runs.jsonl，再 rl run finish 写 loop/runs.jsonl，两本并存不合并，谁对账没写。5 张单就是 10 次填数。
   - 依据：2026-08-16-research-loop-build-plan.md:163; 2026-08-16-research-loop-next-steps.md:148; .claude/skills/gpu-run/SKILL.md:143
   - 改法：让 rl run finish 顺带调宿主的 record finish（或反过来），一次输入两本账都落，doctor 加一条两本对账的扫描。

### smoke-fails（44 步，gyb 动手 4 次）

2. [slows/contradiction] 步 20 到步 22（run 标卡住之后怎么收场）：转移表有一行 stuck→in_progress，谁能写是 holder，前提是「关联 issue 状态是 answered，holder 会话还活着」。可是接单默认是同步 subagent：deploy 起 run 之后一直等 run 返回。run 要想等到 issue 被回复，就得挂在那儿不返回，而回复它的 deploy 正卡在等 run 返回上，两边互等；run 要是返回，会话就结束，holder 会话不再活着。所以这一行在默认接单模式下永远走不到，smoke 失败只能走「销号—回 issue—回 todo—重起 subagent」的重路。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:86; plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：明写 stuck→in_progress 只给 gyb 手动接的会话用，subagent 接的单子一律以返回上游结束；或者给发射单开一条「同一个 deploy 会话就地修完直接再起 run」的短路并写进转移表。
3. [slows/missing] 步 27（deploy 回完 issue 把发射单拉回 todo）：转移表 stuck→todo 那一行的「谁能写」是「回了 issue 的那个角色」，可是 bin/rl 命令表里 handoff 的子命令只有 start/stuck/done/accept/reject/withdraw/release，没有一条对应这次转移；release 在转移表另一行里写的是 owner 专用。这次 deploy 恰好既是回 issue 的人又是 owner，用 release 蒙混过去了，换成 gyb 之外的非 owner 角色回 issue 就没有命令可打。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：加一条 rl handoff resume ID（前提是关联 issue 已 answered），并在转移表每一行后面补上对应的子命令名。
4. [slows/contradiction] 步 22（销号钩子的逃生口）与步 26 到 27：设计文档说「卡住的 issue 被回复之后单子回待干」，转移表 stuck→todo 的前提也是「关联 issue 状态是 answered」；但转移表最后一行允许销号钩子和 reclaim 把 stuck 直接推回 todo，前提只有「holder 清空」，施工计划的 session end 逃生口 --release 走的正是这条。走这条的话，ImportError 的 issue 还没被回复，单子就回了 todo，owner 一拉起下一个 run subagent 就再撞同一个 ImportError，白烧一轮探卡加 smoke。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:116; plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：销号和 reclaim 对 stuck 单一律保持 stuck 只清 holder，不推回 todo；只有关联 issue 变 answered 才允许进 todo。
5. [slows/missing] 步 7（deploy 开发射单）：handoffs 的行格式没有「这张发射单挂在哪张工单上」的字段，只有 work_order 有 decision_refs，launch_order 既不引决定也不引父单。可是设计文档要求 analysis 顺着 handoffs 从决定走到发射单再走到 run_id，doctor 还要扫「快车道工单已 accepted 但没有关联发射单」，两处都需要这条父子边，账上没有地方记。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-next-steps.md:80; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：handoffs 加一个 parent 字段，rl handoff open 在角色会话里默认填当前会话正持有的那张单，withdraw --cascade 也照它走。
6. [slows/missing] 步 33（第二次 smoke 通过后发射）：正常路的 run_id 谁定、怎么命名，文档没写。只有快车道写了 ql_tag 兼作宿主发射器要的 run_id、track 一律填 quick_lane。宿主 run.py launch 的 --run-id 和 --track 都是必填，new1 的规矩还要求 run_id 在产物目录名、tmux session、台账 name、commit message 四处一致，run 在这一步只能自己编一个，且 --track 要和 TIMELINE.md 的方向对得上，谁给这个值也没写。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:161; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：rl handoff open --type launch_order 时自动分配 run_id 写进 launch 子对象（形如 ho-0013-01），track 由 deploy 开单时必填。
7. [slows/missing] 步 34（rl run add 落发射版）：runs 发射版必填 config 字典，里面要有 model、params、dataset、split，是给 analysis 分组用的；但发射单的 launch 子对象只有 command、args、workdir、estimated_seconds、step_table、actual_seconds，没有 config。run 要么去解析命令行参数，要么去读 experiments/ 的代码猜这四个值，而这四个值本来是 deploy 定的。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：把 config 挪到发射单上由 deploy 开单时填，rl run add 默认从发射单抄，run 只补机器和卡。
8. [slows/ambiguous] 步 19（run 开 issue）：smoke 失败该填哪个 kind 没定。六种 kind 里 cannot（干不了）和 not_mine（不归我干）两种读法都说得通：ImportError 是代码问题、明显不归 run 干，但 run 的确也是干不了。施工计划第七节只写「一律 rl issue open --to deploy --kind ...」，省略号没填。kind 影响 doctor 和 status 的归类，也影响 gyb 读账时的判断。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：在第七节把四种失败各钉一个 kind：smoke 失败、发射失败、跑挂都是 cannot，结果反常是 anomaly。
9. [slows/missing] 步 18（run 准备 --log-tail）：开 issue 要附日志末 40 行和 traceback，命令给的是 --log-tail FILE，要一个文件路径。可是 smoke 阶段按 gpu-run 的规矩产物不留档，ImportError 是前台跑出来的、traceback 只在标准输出里，压根没有日志文件。run 得自己想办法把 stdout 落成文件，落到哪、叫什么名，文档没写（run 的写权只有仓库外的 artifact_root）。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:72; plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:160; .claude/skills/gpu-run/SKILL.md:49
   - 改法：run 的 SKILL.md 规定 smoke 一律重定向到 artifact_root/smoke/<发射单号>.log，或者给 rl issue open 加 --log-text 从标准输入收。
10. [slows/too_heavy] 步 19 到步 30（整个修复回路）：一个 import 报错要走完：落一条 issue、把单子标 stuck、run 会话销号、deploy 读 issue、改代码、回 issue、把单子拉回 todo、重起一个 run subagent、重读慢变量档案、重探空卡、重挑卡、重跑 smoke。至少八次账写入加两次会话生死。文档还把两条捷径都堵死了：run 不许自行重试，下游不许小修，快车道只能由 gyb 事先点名进、单子已经在正常路上时没有中途改走快车道的路。这和「想法要快速、多次迭代」的目标拧着。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:185; plans/2026-08-16-research-loop-next-steps.md:180; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给发射单加一条 smoke 失败专用短路：run 返回 traceback，deploy 在同一会话里就地修完打 rl handoff release 再起 run，issue 照开但不必等回复，并明写这不算 run 自行重试。
11. [slows/principle_violation] 步 43（gyb 跑 rl status 收尾看一眼）：违反原则 6 的「进出对称」那一半。run 开给 deploy 的 issue 不触发通知（只有改派到 gyb 名下才通知），rl status 的七段里只有「改派给 gyb 超过阈值的 issue」，没有「open 的 issue 按 assignee 分组」这一段。这条 iss-0031 从 open 到 answered 之后没人 close，账上也没有任何出口能把它列出来；单子本身能在「没到终态的单子」里露头，issue 露不了头。deploy 会话要是先走了，这条 issue 就悬着，只能靠 reclaim 捞单子，issue 永远 open。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:143
   - 改法：rl status 加一段「open 与 answered 的 issue 按 assignee 分组」，reclaim 一并列出超过阈值没动的 issue。
12. [cosmetic/missing] 步 26 与步 43（iss-0031 的收场）：issue 有 open、answered、closed 三个状态，命令表也有 rl issue close，但谁来 close、什么时候 close 全文没写。这次 deploy 回复之后 issue 停在 answered 就再没人碰过，doctor 只扫「没人引用的 issue」，扫不出这种长期 answered 不 closed 的。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：rl handoff accept 时自动 close 这张单关联的所有 answered issue，剩下的由开单角色手动 close。
13. [slows/missing] 步 26 到 27（deploy 修完代码）：修 import 有时候要换入口（比如从 python -m pkg.train 换成 python scripts/train.py）或者加环境变量，发射单上写死的 launch.command 就得跟着改。九本账全是事件流、改等于追加一版，可是转移表里没有「改单内容」这一行，命令表里也没有对应的子命令，deploy 只能收回旧单重开一张新单，把 stuck 的 issue 关联关系一起丢掉。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-next-steps.md:18
   - 改法：加 rl handoff amend ID --command ... --workdir ...，只许在 todo 或 stuck 上追加一版，并在转移表里补一行原地追加。
14. [cosmetic/contradiction] 步 10（run 上线跑过版检查）：设计文档说角色上线第一个动作跑过版检查，这是对所有角色说的；施工计划第五节给 run 的 reads 只有 handoffs 里的 launch_order、experiments/、ops/gpu_state.md、runs，不含 decisions。rl decision stale 要读 decisions 账，run 跑它就越出自己的 reads 栏，不跑又违反上线第一个动作那句。发射单本来也不引决定，run 跑了也查不出跟自己有关的东西。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-build-plan.md:105; plans/2026-08-16-research-loop-build-plan.md:131
   - 改法：明写过版检查只对 idea、deploy、analysis、reviewer 强制，run 免跑；或者把 decisions 的只读加进 run 的 reads。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

1. [blocks/missing] 第 7、10 步：handoffs 行格式（build-plan.md:61）里没有任何父子字段：launch_order 不记它挂在哪张 work_order 上，重开的单子也不记它接的是哪张旧单。可是 next-steps.md:124 的 `--cascade` 要「连它派生的下游单子一起收」、next-steps.md:80 说 analysis 能「从决定顺到发射单再顺到 run_id」、build-plan.md:144 的 doctor 要扫「快车道工单已 accepted 但没有关联发射单」——三处都要这条链，账里没有这个字段。本场景 idea 打了 --cascade，rl 走不到 ho-0013，正在烧卡的那张发射单收不掉。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个 `parent_handoff` 字段，开发射单和分析单时必填，cascade、doctor、链式查询都走它。
2. [blocks/missing] 第 7 步：decision_refs 只对 work_order 必填（build-plan.md:61），文档没有一句要求 deploy 把工单的决定编号抄进发射单，所以 `rl decision stale`（build-plan.md:131）和 `rl handoff list --decision`（build-plan.md:136）都列不出正在跑的 ho-0013。过版检查只看得见工单，看不见真正在花机时的那张单。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-next-steps.md:111
   - 改法：开 launch_order 时自动从父工单继承 decision_refs 并写进单子，stale 检查按继承后的引用算。
3. [blocks/contradiction] 第 15 步：build-plan.md:164（Phase 6b）写「`rl run finish --exit failed|killed`，发射单标 `stuck` 并开 issue 给 deploy；被收回时也走这里」，而转移表 build-plan.md:92 只允许各状态转到 `withdrawn`，build-plan.md:95 又写「`accepted` 和 `withdrawn` 是终态，表外的转移一律拒收，退出码 2」。run 按 SKILL.md 走到这一步必然吃退出码 2。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:164; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:95
   - 改法：第七节 6b 拆成两句：跑挂走 stuck，被收回只做 `rl run finish --exit killed` 加收尾，不再动单子状态。
11. [slows/missing] 第 17 步：接单默认是同步的，上游会话等下游 subagent 回来（next-steps.md:120、next-steps.md:17）。等待期间上游会话没有任何中断通道，rl 给它开的 `kind=withdrawn` issue 要等下游返回才看得见。本场景 deploy 从工单被收回到 run 返回的那几个小时里对收回完全无反应，还在等一张已经作废的发射单。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：收回一张有 holder 的单子时，同时给它的下游单子发同一条收回信号，让下游的看门狗把上游一起唤醒；或者明写等待期间的收回一律由 gyb 直接收到最底层那张单。
14. [slows/missing] 第 14、23 步：被收回的发射单跑出来的那条 run（exit killed、config 记的是旧评测集）留在 loop/runs.jsonl 正账里，没有任何作废标记。决定来源的第三类就是 run_id（next-steps.md:46），后面谁都能拿它当来源；doctor 的扫描项（build-plan.md:144）也不查「run 挂在已收回的单子上」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：doctor 加一条扫描「runs 行的 handoff 已 withdrawn」，并且 `rl decision add --source run:ID` 引到这种 run 时当场警告。
18. [cosmetic/missing] 第 13、18 步：单子被收回之后，experiments/ 里 deploy 已经写下的代码和产物根里那半截产物目录怎么处置，两份文档都没写。快车道有明确的进出规矩（next-steps.md:64 的 worktree 和合回），正常路收回之后没有对应的一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：转移表转到 `withdrawn` 那一行的前提栏补一句：holder 在返回前把半截产物路径写进那条 withdrawn issue，处置由 gyb 定。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

3. [slows/missing] 第 17 步：正常路的 run_id 谁生成、按什么规则没写。快车道有 ql_tag 的形状规定（ql-20260816-01，兼作宿主要的 run_id，track 一律填 quick_lane），正常路只说 run_id「和产物目录名、tmux session、commit message 一致」，没说谁造、什么格式；发射单的 launch 子对象也只有 command / args / workdir，没有 run_id 和 track 两栏，而宿主 run.py launch 的 --run-id 和 --track 是必填。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:85
   - 改法：在 launch 子对象里加 run_id 和 track 两个必填字段，run_id 由 rl handoff open 时按 ho 号加日期自动生成。
9. [slows/too_heavy] 第 12 步到第 21 步：gyb 手动的 deploy 会话按默认要同步等 run subagent 跑完才能接着干，实验跑几个小时 gyb 的交互终端就被占几个小时；而「上游 subagent 同步等下游几个小时会不会被超时收掉」还挂在待验证第 9 条上没有结论，备案是「长任务改成 deploy 开单即销号」，两种走法对 gyb 手动会话的体验差别很大。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：对 gyb 手动加载的角色会话默认走异步：开完发射单就把工单 release 回 todo，等 run 完了 rl status 提醒 gyb 再接。

### periodic-reclaim（27 步，gyb 动手 11 次）

1. [blocks/missing] 第 6、7 步：reclaim 只有 --older-than 和 --apply 两个开关，没有逐条挑选或排除的办法。一个跑三天的 run 会话中间不写账，48 小时的会话阈值必然把它算成很久没动，gyb 想留下它只能整体调大 --older-than，代价是其他该收的也收不了。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:178
   - 改法：reclaim 加 --only ID... 和 --skip ID...，并且默认跳过 launch_order 对应进程还活着的会话。
2. [blocks/missing] 第 8、11、22 步：reclaim 把 launch_order 从 in_progress 改成 todo 之后，GPU 进程照跑、显存不释放、宿主 ops/jobs.json 的号不销。看门狗每轮采样只查本单是不是 withdrawn，改成 todo 它不认，不会走中断流程；owner 这时再起一个 run 接同一张单，同一份实验会被发射两次。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:70; plans/2026-08-16-research-loop-build-plan.md:162; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:143
   - 改法：reclaim 对 launch_order 先走 gpu-run 的中断收尾（rl run finish --exit killed、释放显存、销号）再交回 todo，看门狗把 reclaim 和 withdrawn 一起当中断信号。
12. [slows/principle_violation] 第 23 步：违反原则 1。runs 账的行格式写死「actor 必须是 run」，而原则 1 说任何权限检查对 gyb 一律不生效。gyb 要给回收下来的孤儿发射版补一条 exit=killed 的收尾版，按前一句写不进去，按原则 1 写进去就破了 schema，入账脚本按哪一条实现没有定论。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：runs 账的 actor 改成允许 run 或 gyb，字段表那一句后面补「gyb 例外，同原则 1」。

### hook-missed-session-end（23 步，gyb 动手 11 次）

6. [slows/guessed] 步 13、步 14：设计 L120 只写「上游开完单直接起一个 subagent 接走并同步等它回来」，没写下游 subagent 没走到 done 或 stuck 就返回的时候上游拿到什么、该做什么。待验证第 9 条（设计 L168、施工 L197）只问「等几个小时会不会被超时收掉」，不问「等的对象死了怎么办」。最快能发现这件事的就是被阻塞的上游会话，文档没给它任何职责，我只能按原则 3 推它该 release 加重起。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：设计 L120 补一句「下游 subagent 没走到 done 或 stuck 就返回的，上游当场 rl handoff release 并决定重起还是开 issue 给 gyb」，并写进 idea 和 deploy 的 SKILL.md。

## 裁决记录（日期）

- 2026-08-17：来自 `03-ledgers.md` 的裁决（gyb：「我感觉很轻松能从data_path 找出artifact_path啊，而且artifact path定义有点暧昧 能不能不要了」「选A吧那就」），runs 发射版去掉 `artifact_dir`，产物目录按约定是 `<artifact_root>/<run_id>/`、账上不记；收尾版留 `data_path`（`exit_status` 是 `ok` 时必填，是产物目录里给 analysis 算数用的那一个文件或子目录）。统筹 session 同步。
- 2026-08-17：来自 `04-handoffs-and-sessions.md` 的裁决（rl-hub 转来；gyb 原话「删了吧」「我想这个问题应该取决于再干能不能成功吧，如果是啥外部元素，重试能成功那可以再来，但是如果代码有问题得给代码先修了啊」）：抄的转移表 `in_progress` → `todo` 行「谁能写」删单列的 gyb，「之后谁拉起」改成 owner 照单子原来的 `dispatch` 拉起（`auto` 再起一个 subagent）。对回原则 8、原则 11、原则 3。
- 2026-08-17：来自 `04-handoffs-and-sessions.md` 的裁决（rl-hub 转来；gyb 原话「可以 发」）：gyb 越过 owner 打回也发 fyi，抄的转移表 `done_pending_review` → `rejected` 行前提栏补上。对回原则 6。
- 2026-08-17 gyb 裁（sync-inbox 问题 3，原话「按照08吧」，rl-hub 转来）：阈值表定义处是 `08-trees-init-and-host.md` 第三节，接口一节的指向照改。
- 2026-08-17 来自 `05-rl-cli.md` 定稿（`656c8a9`）的裁决（rl-hub 转来；gyb 原话「全推荐」「只要他不动目前的代码什么的就全推荐就行」「全都推荐，只要不影响正在跑的进程」「A」）：抄的转移表 `in_progress` → `todo` 行补「销号钩子写的 `actor` 记会话角色、`via=session_end`；reclaim 写的 `actor` 记 gyb、`via=reclaim`」，与 `04` 一字不差。对回原则 4。
