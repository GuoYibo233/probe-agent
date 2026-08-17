# run 角色

> 这份覆盖 run 角色的 SKILL.md 要写的一切：接单与认领、接整个 batch、读档案探卡挑卡、smoke 与分步计时、发射前 commit 与发射、runs 账三版、看门狗、四种失败的 issue、6a 正常收尾与 6b 中断、宿主收尾命令、被收回被回收的中断、run 的 inbox、模型。不覆盖 deploy 怎么开发射单和怎么验收发射单（见 `11-role-deploy.md` 和 `21-pair-deploy-run.md`）、runs 账给 analysis 用的数据契约（见 `23-pair-run-analysis.md`）、派活单状态转移表全表和会话生命周期（见 `04-handoffs-and-sessions.md`）、`bin/rl` 命令表全表（见 `05-rl-cli.md`）、九本账的行格式（见 `03-ledgers.md`）、钩子机制与角色 json 的写法（见 `06-hooks-and-permissions.md`）、快车道（见 `07-quick-lane.md`）、`research-loop.json` 和宿主对接（见 `08-trees-init-and-host.md`）、公共母版八条规矩（见 `09-common-and-feedback.md`）。
>
> 源：设计文档的「五个角色」总段、run 一节、账本一节里 runs 和 issues 与 handoffs 三条、交接与会话生命周期一节、两棵树一节、原则 9 与 10 与 11；施工计划第一节裁决 3 和末尾（a）（g）（h）（i）、第二节词表、第三节 handoffs 与 runs 两本账的字段、第四节转移表里和发射单有关的几行、第五节 run 的 use case 与角色 json、第六节命令表里 run 能调的几行、第七节整节、第八节阈值默认值、第十三节规矩 3 与规矩 6。

## 这个角色干什么

run 看服务器、运行实验、主要负责长时间的任务，出问题回报。它接的单子只有一种，就是 deploy 开的发射单 `launch_order`。run 不写代码、不修代码、不重试，出问题一律开 issue 给 deploy（规矩 6）；重来是发射单上的下一次尝试（原则 10）。

run 要小要快。模型：由 agent 调用的时候是 opus（2026-08-16 晚 gyb 把 run 从 sonnet 改裁为 opus，设计文档里原来那句 sonnet 作废）；gyb 手动加载的时候跟当前会话的模型一致，角色 json 的 `model.manual` 写 `inherit`，sessions 账落解析后的真实模型名，取不到记 `unknown`。

一张卡一个 run，多卡跑一个任务是例外。

run 会话装的钩子只拦写：Write 和 Edit 进 `experiments/`、`analysis/`、`review/`、`notes/`、`loop/` 一律 deny 并提示开 issue，其余路径放行。run 的写权目录只有 `artifact_root`（产物根，在仓库外，钩子不判）。产物根只有 run 的任务能写；数字账只有 run 的脚本能写，gyb 例外（规矩 3、原则 1）。

## 收件箱：run 不查

run 不查 inbox：run 只关注自己那张发射单，一般不会有没带单子的 run 会话。上位规矩是角色被拉起不自动查收件箱，`rl inbox` 谁需要谁敲。

## 接单：认领、单张、整个 batch

接单命令是 `rl handoff start ID [--batch B]`，把单子从 `todo` 推到 `in_progress`，holder 写成本会话的 session_id。前提两条：写入会话的角色等于 `to_role`；holder 为空，非空就退出码 2 并列出当前 holder。

接单之后第一件事是看这张单最新一次尝试有没有已经 `launched` 还没 `finished` 的 run 行。有就是认领：`rl handoff start` 那一版写 `adopted: true`，rl 同时给这条 run 写一版 `adopted`（记新 holder 的 `session_id`、`ts`），不另设 `rl run adopt`；认领不重新 smoke、不重新发射，只接管看门狗和收尾，直接跳到 Phase 5。没有才走 smoke。这条是原则 11 的落点：GPU 任务本体在 tmux 里跑、不跟会话走，run 会话死了单子交回待干，下一个 run 会话接单时认领它。

deploy 一次开 N 张同 batch 的发射单时，一个 run 会话用 `rl handoff start --batch` 一次接下整个 batch：smoke 做一次、分步表填一次（其余单子按规模系数复制）、探卡挑卡一次、按宿主发射器自己的分片规矩发射 N 份、落 N 条 run 行。不再一个 workflow 起 N 个 run 各自探卡抢同一张卡。

## 照 gpu-run 八阶段的对照

| gpu-run 阶段 | run 的 use case | 改动 |
|---|---|---|
| Phase 0 读档案 `ops/gpu_state.md` | 接到 `launch_order` 后第一件事读慢变量档案；接单前先看最新尝试有没有 `launched` 未 `finished` 的 run 行，有就认领，跳到 Phase 5 | 档案路径进 `research-loop.json` 的 `gpu_state_path`；认领是新增 |
| Phase 1 实探空卡 `run.py gpu-jobs free` | 同 | 命令进配置的 `launcher.free_cmd` |
| Phase 2 挑卡分片 | 同，规则引用 gpu-run 的 `references/launch-methodology.md`；一个 run 会话接整个 batch，按宿主发射器自己的分片规矩发 N 份 | 不再一个 workflow 起 N 个 run |
| Phase 3 smoke | 同，并且多做一件事：先读代码列出每一步干什么，smoke 时逐步计时，`rl handoff estimate` 填分步表（同 batch 只实测一张，其余 `--copy-from`）；smoke 标准输出落 `artifact_root/smoke/<run_id>.log`；smoke 失败直接 `issue open --kind failed --stage smoke` 加 stuck，分步表不是前提 | 分步计时和 smoke 日志是新增 |
| Phase 4 发射前 commit、`run.py launch`、交监控命令 | 同，命令模板进配置的 `launcher.launch_cmd`，`--run-id` 和 `--track` 从发射单尝试上抄；发射成功后 `rl run add` 落发射版（含 tmux session 名和监控命令） | 三处登记之外多一处 runs 账；宿主发射器写 ops/ 的三个文件是 Bash 写入，钩子不看；loop/ 进宿主脏树白名单 |
| Phase 5 采样器接管 | 看门狗 monitor 只在 run 上线时起，只判、只写自己的状态文件，卡死和超时分开判，每轮顺带查本单是不是 `withdrawn` 或被 reclaim；run 会话每轮读状态文件，杀进程和写账都由 run 会话做 | 卡死阈值沿用 new1 `ops/verdicts.py` 的自适应判定线，超时用最新尝试的 `estimated_seconds` 乘宽松系数；monitor 不写九本账 |
| Phase 6a 正常收尾五连 | 汇报、`rl run finish --exit ok` 记数字（算 actual_seconds、同进程跑反常预警、调 `launcher.finish_cmd` 落宿主账）、释放显存、销号、commit；然后 `rl handoff done` | 数字进 `loop/runs.jsonl`，宿主 `ops/runs.jsonl` 由 finish_cmd 一起落，两本并存，doctor 对账 |
| Phase 6b 中断 | 跑挂：`rl run finish --exit failed`（同样调 finish_cmd），`issue open --kind failed --stage crash`，`handoff stuck`。被收回或被 reclaim `--kill`：`rl run finish --exit killed` 加收尾，不改单子状态 | 中断一律留痕；两种中断分开写 |

下面几节把这张表里属于 run 自己的活写开。

## 读档案、探卡、挑卡

慢变量档案的路径在 `research-loop.json` 的 `gpu_state_path`，在 new1 指的是 `ops/gpu_state.md`，run 的 reads 栏里有它。探空卡的命令模板在配置的 `launcher.free_cmd`，new1 是 `run.py gpu-jobs free`。挑卡分片的规则引用 gpu-run 的 `references/launch-methodology.md`，不在插件里重写一份。

## smoke 与分步计时

预计时长不许模型自己猜，也不许拿一题时间乘题数。做法是：run 先读代码列出每一步都干了什么，smoke 的时候给每一步计时，GPU 步按规模外推（装载一次大模型这类一次性开销也是 GPU 步，只算一次），CPU 步很短可以忽略，加总填进这次尝试的时长字段，分步表附在这次尝试上。

填分步表的命令是 `rl handoff estimate ID --step NAME --kind gpu|cpu --smoke-seconds S --scale F`，往最新一次尝试追加一行；同 batch 的其余单子用 `rl handoff estimate ID --copy-from ID2 [--scale F]` 复制。分步表每项是 `{"step","kind":"gpu"|"cpu","smoke_seconds","scale_factor","estimated_seconds"}`，`estimated_seconds` 只加总最新一次尝试的行（原则 10）。

smoke 的标准输出一律重定向落到 `artifact_root/smoke/<run_id>.log`，开 issue 时 `--log-tail` 指它。

smoke 就失败的时候分步表和预计时长还没有，单子直接标卡住，这两样不是标卡住的前提。

## 发射前 commit 与发射

发射前先 commit，因为记录里存的 HEAD 只有工作树干净时才追得回真实代码。`loop/*.jsonl` 和 `loop/.lock` 不算脏树，要进宿主发射门禁的白名单，new1 这一行由 gyb 亲手改。

发射走宿主发射器，命令模板在配置的 `launcher.launch_cmd`，new1 是 `run.py launch`。`--run-id` 和 `--track` 从发射单这次尝试上抄，run 只抄不猜（原则 9）：run_id 由 rl 按 `<ho-id>-a<attempt>` 分配（形如 `ho-0013-a1`），track 是宿主发射器要的方向名，由 deploy 开单时填。run_id 四处一致：产物目录名、tmux session、台账 name、commit message；产物目录是 `<artifact_root>/<run_id>/`，账上不另记。

宿主发射器用 Bash 往 `ops/jobs.json`、`ops/runs.jsonl`、`RUNMETA.json` 写字，钩子不看 Bash 写出来的文件，这不算越权（原则 2）。

## runs 账三版

一张单子的一次尝试在数字账上落两版（原则 4、原则 10），被下一个会话认领的时候多一版。

发射成功那一刻落发射版，命令是 `rl run add --handoff ID --attempt N --commit ... --host ... --gpus ... --log ... --tmux ... --watch-cmd ...`。这一版 `status` 是 `launched`，必填 `commit`、`command`、`host`、`gpus`、`log_path`、`tmux_session`、`watch_cmd`、`started_at`、`config`；`command`、`config`、`run_id` 三样从发射单抄，run 只补机器和卡。`watch_cmd` 是交给 gyb 的自助监控命令，`rl status` 靠它和 `log_path` 把在跑的实验摆到 gyb 眼前。

跑完落收尾版，命令是 `rl run finish RUN_ID --exit ok|failed|killed [--metric k=v ...] [--data-path P]`。这一版 `status` 是 `finished`，必填 `finished_at`、`exit_status`、`actual_seconds`；`exit_status` 是 `ok` 的时候 `metrics` 和 `data_path` 也必填。真实耗时由 `rl run finish` 从两个时间戳算出来，不管退出状态是什么都记，几次之后就知道外推偏多少。发射单最新一次尝试上的 `actual_seconds` 由 rl 在 `run finish` 时从这里抄、人不填，`rl handoff done` 不带 `--actual-seconds`，预计和实际在同一张单上对着看。

认领那一刻落 `adopted` 版：`rl handoff start` 顺带给这条 run 写一版，记新 holder 的 `session_id` 和 `ts`，`status` 取 `adopted`。

runs 账的 `actor` 是 `run` 或 `gyb`。

## 看门狗

看门狗是独立进程，只在 run 上线时起，只判、只写自己的状态文件，不写九本账。它只许调 rl 的查询命令、不留痕（独立进程读不到会话状态文件，按 actor 判定就是裸终端，所以一条写命令都不许打），判定由 run 会话转写进账（2026-08-17 随 `05` 定稿裁）。run 会话每轮读它，杀进程和写账一律由 run 会话做。

它判两件事，分开判：卡死看进展停没停（日志多久没新行、产物目录 `<artifact_root>/<run_id>/`（约定定义在 `08-trees-init-and-host.md` 第一节）多久没新文件、显卡利用率是不是掉到零），和预计时长无关；超时才用最新尝试的 `estimated_seconds` 乘一个宽松系数。默认阈值写在 `research-loop.json`，gyb 可改：

| 键 | 默认值 | 用在哪 |
|---|---|---|
| `watchdog.stall_mult` | 5 | 卡死判定线 = 5 倍典型心跳间隔，沿用 `ops/verdicts.py` |
| `watchdog.stall_floor_samples` | 3 | 判定线下限三轮采样 |
| `watchdog.warmup_seconds` | 1800 | 开局 30 分钟不判卡死 |
| `watchdog.gpu_util_zero_seconds` | 900 | 显卡利用率连续 15 分钟为零算一路证据 |
| `watchdog.timeout_factor` | 3 | 超时 = 最新尝试 `estimated_seconds` 乘 3 |

看门狗每轮采样顺带查一次本单状态，见到被收回（`withdrawn`）或被 reclaim 就走中断流程。

反常结果预警不做常驻进程，就在落收尾版的时候由 `rl run finish` 在同一个进程里查阈值：指标落在 `anomaly.metric_extremes`（默认 `[0, 1]`）触发，实际耗时超过预计的 `anomaly.duration_factor` 倍（默认 3）触发。超阈值当场开一条 issue。

## 四种失败的 issue

run 出问题一律开 issue，不修代码、不重试。四种情形对应的 kind 和收件人：

| 情形 | 命令 | 收件人 |
|---|---|---|
| smoke 失败 | `rl issue open --kind failed --stage smoke` | deploy |
| 发射失败 | `rl issue open --kind failed --stage launch` | deploy |
| 跑挂 | `rl issue open --kind failed --stage crash` | deploy |
| 结果反常 | `rl issue open --kind anomaly` | gyb |

三种 `failed` 的 issue 附日志末 40 行和 traceback（`--log-tail FILE` 或 `--log-text -`），issue 里带 `handoff_id`。`anomaly` 那条的 actor 记 run。

两处原文不一致：设计文档 run 一节先写「反常结果预警……当场开一条 issue（kind 是 anomaly，actor 记 run，归 gyb）」，同一段又写「出问题一律开 issue 回给 deploy：smoke 失败、发射失败、跑挂、结果反常四种」；施工计划第七节写的是三种失败开给 deploy、结果反常 `--kind anomaly --to gyb`。按施工计划，反常那条开给 gyb。

开完 issue 把单子标卡住：`rl handoff stuck ID --issue ID`，从 `in_progress` 到 `stuck`，谁能写是 holder，前提是那条 issue 已经存在并且它的 `handoff_id` 指回本单。跨两本账的写序定死：先写 issue 拿到编号，再写单子那一行引它。

标了卡住之后 run 这一轮就结束了。改代码、给发射单追加一次新的尝试、回 issue、把单子交回待干、再起 run，都是 deploy 的活（见 `11-role-deploy.md`、`21-pair-deploy-run.md`）。

## Phase 6a：正常收尾

顺序是：汇报、`rl run finish --exit ok` 记数字、释放显存、销号、commit；然后 `rl handoff done ID` 把发射单提到 `done_pending_review`。

`rl run finish` 一条命令做三件事：从两个时间戳算 `actual_seconds`、同进程跑反常预警、调宿主收尾命令模板 `launcher.finish_cmd`（new1 是 `run.py record finish`）把宿主那本账一起落。两本账并存不合并，doctor 有一项对账。

`rl handoff done` 的前提是这张单最新尝试的 run 行有 `exit_status=ok` 的 `finished` 版。退出状态不是 ok 就提不了验收，只能走 6b。

## Phase 6b：中断

跑挂：`rl run finish --exit failed`（同样调 `finish_cmd`），`rl issue open --to deploy --kind failed --stage crash`，`rl handoff stuck`。

被收回或者被 `rl reclaim --kill`：只做 `rl run finish --exit killed` 加收尾（杀进程、释放显存、宿主销号），不再改单子状态，状态由收回或回收那一步改。

ok 和失败都调宿主收尾命令，两本账一次落，宿主那本不会停在只有开始没有结束。

## 被收回、被回收、会话死了

三种外部动作会打断一个正在干的 run 会话，处理办法各不相同：

- 单子被 owner 或 gyb 收回（`withdrawn`）：看门狗每轮查到，run 走中断收尾。rl 顺带开一条 `withdrawn` 通知给 holder 的角色和 owner，通知类 issue 由收件人做完了自己 close。
- 被 `rl reclaim` 回收：开干的发射单默认不杀进程（留给下一个 run 认领），`--kill` 才先走中断收尾再把单子交回 `todo`。看门狗把 reclaim 和 withdrawn 一起当中断信号。
- 会话销号：钩子挂在 SessionEnd 和 SubagentStop 上，`rl session end` 只扫 holder 是本会话且状态是 `in_progress` 的单子，有就 release 交回 `todo`、自动填 `progress_note`、给 owner 开 `orphaned` 通知。`launch_order` 且最新尝试有 `launched` 未 `finished` 的 run 行时不杀进程，等下一个 run 会话认领。等几个小时的事只发生在 tmux 里，不发生在任何会话里（原则 11）。

## run 的角色 json 四栏

| 栏 | 内容 |
|---|---|
| reads | handoffs、issues、runs、`experiments/`、`ops/gpu_state.md` |
| writes | `artifact_root`（仓库外，钩子不判） |
| ledger_writes | runs 全部、handoffs 的 start/estimate/done/stuck、issues 的 open、decisions.run add（自决极少，比如挑卡的理由）、feedback add |
| dispatches_to | 无 |
| model | `as_subagent` 是 opus，`manual` 是 `inherit` |

备注（不进 json，2026-08-18 `reads` 写法裁决：备注移到表下）：handoffs 只读自己那张 `launch_order`，issues 只读归自己的。

SKILL.md 里另写两句纪律（2026-08-18 gyb 裁，定义处 `06-hooks-and-permissions.md`）：用 Bash 往四个角色目录和 `loop/` 写（重定向、脚本、`cp`、`mv` 都算）等于绕钩子，不许，要写就用 Write/Edit 让钩子看得见，账本一律走 `rl`；一个会话只加载一个角色，要换角色另开会话。

查询命令（show、list、trace、status、inbox、stale、doctor）谁都能调，不进 `ledger_writes`；`rl doctor --ack`、`--unack` 是写命令、只有 gyb 能敲（2026-08-17 gyb 裁，sync-inbox 问题 23）；读一律不设权（原则 2）。机器检查（测试 13）三样都查（2026-08-18 gyb 裁，定义处 `06-hooks-and-permissions.md`）：SKILL.md 正文出现的每条 rl 写命令都在这个角色 json 的 `ledger_writes` 里（查询命令不查）；SKILL.md 正文出现的每个账名和目录都在 `reads` 里（按 `reads` 栏定死的两种写法逐个对：账写账名，目录和文件写相对仓库根的路径）；引用的名字都在定义处查得到、母版不抄。SKILL.md 不抄公共母版的条文，只写一句「按 common/ 执行」。

## 和宿主的关系

`rl init` 往研究仓库的 CLAUDE.md 里追加的那一节有一句是给 run 的：「加载了 run 角色的会话以 run 的 SKILL.md 为准，它是 gpu-run 的超集，宿主 GPU 铁律里的『唯一入口』对 run 会话读作 run skill」。宿主自己的四层记录（new1 的 TIMELINE.md、DATA.md、RESULTS.md、`ops/runs.jsonl`）角色一律不碰，只有 `rl run finish` 经宿主收尾命令模板往 `ops/runs.jsonl` 落数字，TIMELINE 和 DATA 由 gyb 手动补。

## 和别的 part 的接口

- 发射单 `launch_order` 的字段（`attempts` 里每项的 `command`、`args`、`workdir`、`track`、`config`、`run_id`、`estimated_seconds`、`step_table`，以及 `parent_id`、`batch`、`decision_refs`）：定义在 `03-ledgers.md`，由 deploy 开单时填，见 `11-role-deploy.md`。
- runs 账的完整行格式（`launched`、`finished`、`adopted` 三版的必填栏、`metrics`、`data_path`、`config`）：定义在 `03-ledgers.md`；给 analysis 用的分组契约在 `23-pair-run-analysis.md`。
- 派活单七个状态、转移表每一行的谁能写和前提、holder 只在 `in_progress` 非空这条不变量、会话登记与销号：定义在 `04-handoffs-and-sessions.md`。
- `rl handoff start/estimate/done/stuck`、`rl run add/finish`、`rl issue open`、`rl inbox` 的完整参数：定义在 `05-rl-cli.md`；退出码 0/1/2/3/4/5 同。
- 写权钩子拦哪些路径、角色 json 的四栏怎么被机器检查、`--as-gyb` 与 `--quote`：定义在 `06-hooks-and-permissions.md`。
- 快车道里 GPU 怎么跑（run_id 用 ql_tag、track 沿用被微调那个实验的方向、数字进杂账不进 runs 账、deploy 可以派 gpu-runner）：定义在 `07-quick-lane.md`，那条路上没有 run 会话、不开发射单、不做分步计时。
- `research-loop.json` 里的 `artifact_root`、`gpu_state_path`、`launcher.free_cmd`、`launcher.launch_cmd`、`launcher.finish_cmd`、中断命令模板、宿主台账清单、脏树白名单和 CLAUDE.md 那一节：定义在 `08-trees-init-and-host.md`。
- 公共母版的规矩 3（数字只经脚本入账）和规矩 6（故障分域，run 出问题一律开 issue 给 deploy、不自行重试）：定义在 `09-common-and-feedback.md`。
- 收回、reclaim、doctor 的扫描项（含 runs 有 `launched` 版长期没 `finished` 版、runs 挂在 `withdrawn` 的单子上、两本 runs 账对账）：定义在 `01-gyb.md` 与 `05-rl-cli.md`。
- 待验证第 5、8、9 条（SubagentStop 触不触发、subagent 里钩子装不装得上、后台 subagent 能不能跑几小时）会改掉 run 这一段的走法，结论落在 `30-build-steps-verify-tests.md`。

## 源文档没写清的（留给 gyb）

1. run 的 reads 栏里没有 decisions，`ledger_writes` 里却有 `decisions.run add`。run 自决要写来源，来源的 `decision` 一类怎么查、run 能不能读自己那本 `decisions.run`，两份源文档都没写。
2. 认领一次已发射未收尾的尝试时，新的 run 会话怎么找到还在跑的进程和 tmux session（照 runs 行的 `tmux_session` 走还是重探），原来那条会话起的看门狗进程还在不在、要不要重起一个，都没写。
3. 一个 run 会话接整个 batch 时，N 份分片各自用哪台机器、哪张卡，谁来分、分完写在哪（runs 行有 `host` 和 `gpus`，发射单的尝试对象里没有这两栏），源文档只写「按宿主发射器自己的分片规矩发射 N 份」。
4. 分步表里 `scale_factor` 按什么量取（数据量、步数、还是别的），smoke 规模和正式规模的比值谁定，没写。
5. smoke 用哪张卡、smoke 是不是占用正式发射那张卡、`artifact_root/smoke/` 下的日志谁清理，没写。
6. 看门狗状态文件放哪、格式是什么、run 会话每轮读的间隔多长，没写；run 会话死了之后那个看门狗进程谁停也没写。
7. 「一张卡一个 run，多卡跑一个任务的例外」在账上怎么表达：runs 行的 `gpus` 是列表，但多卡那种例外要不要在发射单上标、由谁批，没写。
8. 认领之后要不要重跑 estimate 或者更新 `estimated_seconds`（认领的那次尝试的分步表是上一个会话填的），没写。
9. `anomaly` 那条 issue 的 `handoff_id`：第三节 issues 的必填规则里 `anomaly` 不在必填之列，第七节又说 run 开的 issue 里带 `handoff_id`，到底必不必填没有一处钉死。
10. 认领和 `--batch` 两件事撞一起怎么办（一个 batch 里有的单子已经发射、有的还没 smoke），没写。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

下面的条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，只有模拟没有核实，不做判断、不改字。

### new-idea（39 步，gyb 动手 7 次）

14. [cosmetic/missing] 第 27 步和第 28 步：gpu-run 的 Phase 4 要求把自助监控命令交到用户手上，可这条链上 run 的上游是 deploy subagent、gyb 不在链上；rl status 列的是单子、会话和快车道 worktree，没有一栏给正在跑的实验的日志路径或宿主 watch 命令，gyb 中途只能自己去猜命令
   - 依据：plans/2026-08-16-research-loop-build-plan.md:161; plans/2026-08-16-research-loop-build-plan.md:142; .claude/skills/gpu-run/SKILL.md:97
   - 改法：rl status 的在办单子一栏顺带打印 runs 账里的 log_path、artifact_dir 和宿主的 watch 命令

### run-crash-midway（40 步，gyb 动手 4 次）

1. [blocks/missing] 第 3 步：看门狗判死之后的动作链没人写：谁去杀训练进程、判定怎么送到 run 会话手里，两份文档都没有。next-steps.md:70 只写看门狗判卡死和超时两件事、每轮顺带查「被收回」并走中断流程，唯独没写「判死之后怎么办」；build-plan.md:162 只说卡死和超时分开判，:166 只说判定进 issues 账。场景标题里的「看门狗判死把它杀了」在文档里找不到执行者。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:70; plans/2026-08-16-research-loop-build-plan.md:162; plans/2026-08-16-research-loop-build-plan.md:166
   - 改法：在 run 的 SKILL.md Phase 5 写死：monitor 只判、只写自己的状态文件，run 会话每轮读它，杀进程和写九本账一律由 run 会话做。
2. [slows/ambiguous] 第 3、9 步：看门狗写账时 actor 判成谁，两种读法都说得通。build-plan.md:166 说「看门狗的判定进 issues 账」，读成 monitor 自己打 `rl issue open`；但 monitor 是独立进程，按 build-plan.md:121 读不到会话状态文件就判 actor 是 gyb、session_id 是 cli，这条 issue 会记成 gyb 开的。读成 run 会话来打则 build-plan.md:166 那句落空。两种读法分别导致账行 actor 记错，或者 monitor 和会话各开一条重复 issue。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：把 monitor 明确排除在写账者之外，改写成「看门狗的判定由 run 会话转写进 issues 账」。
3. [blocks/contradiction] 第 13 步：销号时扫什么单子，两份文档打架。next-steps.md:126 写「检查这个会话作为 holder 有没有还挂在开干的单子」（只管 in_progress），build-plan.md:126 写「扫 holder 是本会话的单子，有就拒绝并列出」（不限状态）。ho-0013 标 stuck 之后 holder 仍是 sess-run-01（转移表 build-plan.md:84 那一行不清 holder），按施工计划这版销号会被拒绝，而调 `rl session end` 的是钩子不是模型，钩子不会自己去选 `--release` 还是 `--stuck`，链条停在这里。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:84
   - 改法：build-plan.md:126 改成「扫 holder 是本会话且状态为 in_progress 的单子」，并在转移表 in_progress→stuck 那一行注明 holder 保留还是清空。
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
14. [slows/ambiguous] 第 13 步：sessions 账的 open_handoffs_at_end 字段说明是「结束时 holder 还是这个会话的单子列表，正常应为空」（build-plan.md:71），但发射单标 stuck 之后 holder 不清空，run 会话销号时这个字段必然非空。到底是「非空就是异常要拦」还是「非空只是记一笔」，文档没说，两种读法分别对应销号被拒和销号放行。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:84
   - 改法：把这个字段的说明改成「结束时状态还是 in_progress 的单子列表，非空即拒绝销号」，stuck 的单子不算。
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
7. [blocks/contradiction] 第 25、42 步：销号时查 holder 的范围两份文档写得不一样：设计文档说「检查这个会话作为 holder 有没有还挂在开干的单子」，施工计划说「扫 holder 是本会话的单子，有就拒绝并列出」。转移表里 done_pending_review 和 stuck 两个状态都不清 holder，所以按施工计划的读法，4 个跑完的 run subagent 和写完报告的 deploy 会话全都退不出去；按设计文档的读法才能销号。测试清单第 7 条只覆盖了 in_progress 这一种。
   - 依据：2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-build-plan.md:126; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:84; 2026-08-16-research-loop-build-plan.md:209
   - 改法：施工计划第六节改成「只拦 status 为 in_progress 且 holder 是本会话的单子」，done_pending_review 和 stuck 一律放行销号。
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

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

3. [blocks/contradiction] 第 15 步：build-plan.md:164（Phase 6b）写「`rl run finish --exit failed|killed`，发射单标 `stuck` 并开 issue 给 deploy；被收回时也走这里」，而转移表 build-plan.md:92 只允许各状态转到 `withdrawn`，build-plan.md:95 又写「`accepted` 和 `withdrawn` 是终态，表外的转移一律拒收，退出码 2」。run 按 SKILL.md 走到这一步必然吃退出码 2。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:164; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:95
   - 改法：第七节 6b 拆成两句：跑挂走 stuck，被收回只做 `rl run finish --exit killed` 加收尾，不再动单子状态。

11. [slows/missing] 第 17 步：接单默认是同步的，上游会话等下游 subagent 回来（next-steps.md:120、next-steps.md:17）。等待期间上游会话没有任何中断通道，rl 给它开的 `kind=withdrawn` issue 要等下游返回才看得见。本场景 deploy 从工单被收回到 run 返回的那几个小时里对收回完全无反应，还在等一张已经作废的发射单。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：收回一张有 holder 的单子时，同时给它的下游单子发同一条收回信号，让下游的看门狗把上游一起唤醒；或者明写等待期间的收回一律由 gyb 直接收到最底层那张单。

13. [slows/missing] 第 20 步：rl 自动开的 `kind=withdrawn` issue 的 assignee 是角色不是会话（build-plan.md:59），run 的 subagent 收到信号后就结束了，这条 issue 没人回也没人关。doctor 的扫描项里只有「没人引用的 issue」（build-plan.md:144），这条带着 handoff_id 所以扫不出来，会一直挂在 `rl status` 的 open 列表里。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：withdraw 自动开的 issue 直接落成 `closed`（它是通知不是问题），或者 doctor 加一条「holder 已销号但 withdrawn issue 仍 open」的扫描并附 close 命令。
14. [slows/missing] 第 14、23 步：被收回的发射单跑出来的那条 run（exit killed、config 记的是旧评测集）留在 loop/runs.jsonl 正账里，没有任何作废标记。决定来源的第三类就是 run_id（next-steps.md:46），后面谁都能拿它当来源；doctor 的扫描项（build-plan.md:144）也不查「run 挂在已收回的单子上」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：doctor 加一条扫描「runs 行的 handoff 已 withdrawn」，并且 `rl decision add --source run:ID` 引到这种 run 时当场警告。

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
13. [slows/missing] 第 26 步：doctor 的八个扫描项里没有 reclaim 会造出来的两种脏账：单子已经回到 todo 而关联 issue 还是 open，以及 runs 有发射版长期没有收尾版。这两种正是回收留下的残渣，扫不出来就没人修。文档也没写 reclaim 之后要不要跑 doctor。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:20
   - 改法：doctor 加这两项扫描，reclaim --apply 结束时自动跑一遍 doctor 并打印结果。

### smoke-fails（44 步，gyb 动手 4 次）

1. [blocks/contradiction] 步 22 与步 39（run subagent 两次销号）：销号时要检查的单子范围两份文档不一样：设计文档写「检查这个会话作为 holder 有没有还挂在**开干**的单子」，施工计划写「end 时扫 **holder 是本会话的单子**，有就拒绝并列出」。smoke 失败后这张发射单在 stuck，正常收尾后在 done_pending_review，两次 holder 都还是本会话（转移表 in_progress→stuck、in_progress→done_pending_review 两行都没写清空 holder）。按施工计划的读法，SubagentStop 钩子调的 rl session end 每次都被拒收（退出码 2），而钩子是自动触发的、没法回头补 --release 或 --stuck，结果 sessions 账永远缺结束版、holder 死钉在一个已经不存在的会话上，只能等 48 小时 reclaim。这同时是原则 8 的漏网：两份文档留了两个值，没有回来改掉其中一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:84; plans/2026-08-16-research-loop-build-plan.md:87
   - 改法：把销号检查钉死成「只对 in_progress 拒绝」，stuck 和 done_pending_review 放行并在 end 里顺手清空 holder，两份文档同步改成同一句。
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
15. [slows/guessed] 步 9 与步 22（run subagent 的钩子与销号）：待验证清单第 5 条（SubagentStop 在 subagent 结束时触不触发、会话 id 是不是同一个）和第 8 条（subagent 里加载角色 skill 钩子装不装得上）都还没测，两条各有备案，选主案还是备案会改掉本场景一半的走法：备案里 subagent 路线改成 workflow 的 agentType，或者「接单只靠纪律加 reviewer 事后查」，那样 run 的写权拦不住、销号全靠 reclaim、sessions 账没有结束版。我这次按主案走，属于猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:193; plans/2026-08-16-research-loop-build-plan.md:196; plans/2026-08-16-research-loop-next-steps.md:164; plans/2026-08-16-research-loop-next-steps.md:167
   - 改法：施工步 0 出结论之后，按选中的那一案把 run 的 SKILL.md 和第七节改死，删掉另一案，不留两条路。
16. [cosmetic/missing] 步 2 与步 9（钩子登记会话）：sessions 账要求 model 记真实模型标识、手动加载也记真实的、不记 inherit，rl session start --role R --model M 由钩子调；但钩子从哪拿到这个真实模型名，文档没写，待验证清单第 1 条只查了会话 id 有没有现成变量，没查模型标识。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:189; plans/2026-08-16-research-loop-next-steps.md:103
   - 改法：待验证清单加一条「钩子输入里有没有模型标识」，拿不到就退成记 unknown 并把启动命令一起写进账行。

## 裁决记录（日期）

- 2026-08-17：来自 `03-ledgers.md` 的裁决（gyb：「我感觉很轻松能从data_path 找出artifact_path啊，而且artifact path定义有点暧昧 能不能不要了」「选A吧那就」），runs 发射版去掉 `artifact_dir`，产物目录按约定是 `<artifact_root>/<run_id>/`、账上不记；收尾版留 `data_path`（`exit_status` 是 `ok` 时必填，是产物目录里给 analysis 算数用的那一个文件或子目录）。统筹 session 同步。
- 2026-08-17 来自 `05-rl-cli.md` 定稿（`656c8a9`）的裁决（rl-hub 转来；gyb 原话「全推荐」「只要他不动目前的代码什么的就全推荐就行」「全都推荐，只要不影响正在跑的进程」「A」）：看门狗只许调 rl 查询命令、不留痕，判定由 run 会话转写进账。对回原则 1、11。「看门狗」一节开头照改。
- 2026-08-17 gyb 裁（sync-inbox 问题 4，原话「问题4 给8」，rl-hub 转来）：「`<artifact_root>/<run_id>/`」约定定义处归 `08-trees-init-and-host.md` 第一节，本份那句只引。
- 2026-08-17 来自 sync-inbox 问题 13 的裁决（定义处 `03`、`04`，rl-hub-v3 传；gyb 原话「B」）：「runs 账三版」一节补一句「发射单最新一次尝试上的 `actual_seconds` 由 rl 在 `run finish` 时从这里抄、人不填，`rl handoff done` 不带 `--actual-seconds`」。
- 2026-08-17 来自 sync-inbox 问题 17 的裁决（定义处 `03`、`04`，rl-hub-v3 传；gyb 原话「C」）：「接单」一节认领那句改成 `rl handoff start` 那一版写 `adopted: true`、rl 同时给这条 run 写一版 `adopted`；「runs 账两版」一节改名「runs 账三版」并补 `adopted` 版一段；接口一节 runs 行格式写成三版。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `03`、`05`，rl-hub-v3 传；gyb 原话「只有做完了的时候才关，巡检要我本人确认」）：「被收回、被回收、会话死了」一节「通知类 issue 被 `rl inbox` 读过即关」改成「通知类 issue 由收件人做完了自己 close」。
- 2026-08-17 来自 sync-inbox 问题 25 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「我想让agent有办法识别发生了什么就行」）：接口一节「退出码 0/2/3/4 同」改成「退出码 0/1/2/3/4/5 同」。
- 2026-08-17 来自 sync-inbox 问题 28 的裁决（定义处 `01`、`05`，rl-hub-v3 传；gyb 原话「顺便run只需要关注自己的工单，一般不会空run，不需要查，这个改了」「C」）：「上线第一个动作」这一节改名「收件箱：run 不查」，整段改成「run 不查 inbox：run 只关注自己那张发射单，一般不会有没带单子的 run 会话。上位规矩是角色被拉起不自动查收件箱，`rl inbox` 谁需要谁敲」。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `05`，rl-hub-v3 传；gyb 原话见 inbox）：查询命令那句后补「`rl doctor --ack`、`--unack` 是写命令、只有 gyb 能敲」，与 `06-hooks-and-permissions.md` 同句一字不差。
- 2026-08-18 来自 `06-hooks-and-permissions.md` 定稿（`d430192`，rl-hub-v4 传；gyb 原话「a」（问题八、十一、十二）「6 c」）：json 副本 `reads` 改成账名加路径、两条备注移到表下；机器检查改三样都查；加两句 SKILL.md 纪律。对回原则 8、2。
