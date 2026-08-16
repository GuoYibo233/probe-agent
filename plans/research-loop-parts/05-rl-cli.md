# bin/rl 命令表

> 这份是命令的唯一总表：actor 怎么定、每条子命令干什么谁能调、退出码、`--json`、锁与写序、`rl inbox`、`rl trace`、`rl status` 的十段、`rl reclaim`、`rl doctor` 的全部扫描项与修法、`rl notify` 的签名（推送表归 01-gyb.md 第五节）。别的 part 引用命令时指到这一份。
> 这份不覆盖：九本账每一行的字段和必填规则（03-ledgers.md）、派活单状态转移表的六栏全文与会话生命周期（04-handoffs-and-sessions.md）、钩子拦什么和角色 json 四栏（06-hooks-and-permissions.md）、gyb 自己怎么用这些命令和 gyb 的 use case 表（01-gyb.md）、快车道进出的规矩（07-quick-lane.md）、`rl init` 建出来的两棵树和宿主对接（08-trees-init-and-host.md）、公共母版和反馈账的用法（09-common-and-feedback.md）、五个角色各自调哪些命令（10 到 14 各份）、测试清单和施工步骤（30-build-steps-verify-tests.md）。
> 源：设计文档的十一条原则第 1、2、5、6、9 条，「账本」一节的查询句与锁那一段，「交接与会话生命周期」一节的收件箱段与回收段，「分权与钩子」一节的第二层，「待验证清单」；施工计划第一节裁决 6 与末尾（b）（c）（d）（i），第二节词表，第五节开头两段与 gyb 的 use case 表，第六节全节，第八节阈值表里被命令用到的几个。

## actor 怎么定

这一组规矩（actor 判定、`--as-gyb` 加 `--quote`、`--force --reason`）的定义处是 `01-gyb.md` 第二节（2026-08-17 gyb 裁），本节是命令行写法，两边同步、一字不差。

`rl` 判定 actor 的办法只有一条：看这条命令从哪个会话发出来。原则 1 的推论把这句话写死了，原话是「rl 只认会话，不认手指」——rl 看不到键盘前面坐的是 gyb 还是模型。

判定分三种情形。

第一种，裸终端。`rl` 从会话状态文件读当前角色，状态文件由角色 skill 头部钩子在加载的时候写，路径是 `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json`。读不到状态文件就是裸终端，actor 是 `gyb`，`session_id` 记 `cli`。裸终端不要 `--as-gyb` 这个参数（2026-08-16 夜 gyb 裁）。

第二种，角色会话里以角色身份写。读得到状态文件，actor 就是状态文件里那个角色，`session_id` 记当前会话。

第三种，角色会话里以 gyb 身份写。命令加 `--as-gyb`，actor 记 `gyb`，`session_id` 照记当前会话；同时必须给 `--quote "<gyb 原话>"`，不论敲键盘的是谁，缺 quote 退出码 2。这个 quote 是留给 reviewer 事后查的痕迹，不是身份判定。gyb 本人敲的时候就引自己刚说的那一句。

actor 是 `gyb` 的时候跳过两样检查：命令表「谁能调」那一栏，和转移表「谁能写」那一栏。完整性前提照查——必填字段、路径存在、引用存在这些对 gyb 同样生效，要硬写就加 `--force --reason`，rl 照写并把 reason 记进账行的 `force_reason` 栏。`--force` 只越过完整性前提，越不过转移表外的转移：表外转移对 gyb 同样退出码 2，要硬改状态走 `withdraw` 再重开（2026-08-17 gyb 裁）。

actor 是角色的命令带 `--force` 一律拒收，退出码 3，附「开 issue 给 gyb」的命令；角色会话里 `--as-gyb --quote --force --reason` 算 gyb 身份写，照写（2026-08-17 gyb 裁，来自 03）。

grants 只有 gyb 能写：裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收（2026-08-17 gyb 裁，问题 27）。`decisions.gyb.jsonl` 只收 `session_id` 是 `cli` 的行，这条不变，角色会话里替 gyb 记的决定落那个角色自己那本、actor 记 `gyb`、带 quote。

以上写法出自施工计划第一节末尾的（b）（c）（d）三条：（b）（c）2026-08-17 gyb 认；（d）改成上一段 grants 那句。

两类不是人也不是角色会话的调用者（2026-08-17 gyb 裁）：独立进程（看门狗这一类）读不到会话状态文件，只许调查询命令，查询不进账所以不留痕，它的判定由 run 会话转写进账；钩子和 reclaim 自动写的账行，`rl session end` 顺带做的 release 的 actor 记那个会话的角色、`session_id` 记那个会话，另加可选栏 `via=session_end`，`rl reclaim --apply` 做的写入 actor 记 `gyb`、`via=reclaim`。`via` 和 `force_reason` 一样是九本账骨架的可选栏。

## 命令表

三栏照施工计划第六节：子命令、干什么、谁能调。按账分成几张表，内容不变。

### 建树与会话

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl init` | 在研究仓库建 `research-loop.json`、`loop/` 九本账、`experiments/`、`analysis/`（含公共统计件模板和 `analysis/scratch/`）、`review/`、`notes/`，往 CLAUDE.md 追加一节（三句），问一次要不要给 idea 发 `read:notes`；读到会话状态文件就拒收，退出码 3，提示换裸终端跑 | gyb，只在裸终端 |
| `rl session start --role R [--model M] [--launched-by manual\|subagent\|workflow]` / `rl session end [--session ID] [--reason]` / `rl session focus --decision ID` / `rl session amend ID --model M` / `rl session show ID` / `rl session list [--alive] [--role R]` | 登记和销号，钩子调；`amend` 只许改 `model`，status 与其他栏照抄最新版、closed 的会话也能 amend，是 doctor 第 19 项的修法；`end` 只扫 `in_progress` 且 holder 是本会话的单子，有就全部 release 交回 `todo`、自动填 `progress_note`、给 owner 开 `orphaned`、experiments/ 脏改动打 `wip/<ho-id>` 分支；`--session ID` 给 gyb 关别的会话；`start` 的 `rules_version` 由 rl 从母版读；细则（`--session ID` 不查活、`end_reason` 记 `manual`、closed 会话再写账拒收）见 04 第七节 | start/end 钩子和 gyb，focus reviewer，amend gyb，查谁都行 |
| `rl inbox` | 角色的收件箱：本角色名下 open 的 issue、owner 是本角色而 holder 为空的单子、本会话手上单子引的过版决定、发给本角色的通知、本角色提的 feedback 的裁决；只读，不顺带关任何 issue | 角色会话，谁需要谁敲，run 不查；查谁都行 |

### 决定账

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl decision add --text --source K:V ... [--quote ...]` | 追加一条新决定，编号自动分配，落 actor 自己那本（角色会话 `--as-gyb` 落角色那本） | 五个角色、gyb |
| `rl decision update ID --text [--source ...] [--quote ...]` / `rl decision confirm ID --source ...` | 追加一版（update 换正文；confirm 正文不变只加来源）；不给 source 就继承上一版；写完当场列出引旧版而没到终态的单子和 holder | 同 actor（跨角色改别人的决定在自己那本 add，来源指原决定） |
| `rl decision retire ID [--source ...]` / `rl decision merge ID1 ID2 ... --text --root ID [--source ...]` | 废除；合并成新决定，被合并编号自动进 sources 和 merged_from，旧的各追加一版 `retired`；retire 同样列受影响的单子 | 同 actor |
| `rl decision show ID [--version V] [--history] [--with-runs]` / `rl decision list [--actor A] [--line L]` | 默认最新版；`--with-runs` 沿 parent_id 链反查各版本派出的单子和 run 与 metrics | 谁都行 |
| `rl decision stale [--handoff ID] [--all]` | 过版检查，默认只列和本会话手上单子有关的，`--all` 全库 | 谁都行 |
| `rl trace <dec-\|ho-\|run_id\|iss-\|eval->` | 打出到决定各版本的整条链 | 谁都行 |

### 问题条

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl issue open --to R --kind K [--stage S] --text [--handoff ID] [--log-tail FILE\|--log-text -]` / `rl issue reassign ID --to R` / `rl issue reply ID --text` / `rl issue close ID` / `rl issue link ID --handoff ID` / `rl issue show ID` / `rl issue list [--open] [--to R] [--kind K]` | 问题条；`--to gyb`（开单或改派）触发通知；`link` 是 doctor 修法 | 按角色 json 的 `ledger_writes`，查谁都行 |

### 派活单

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl handoff open --type T --to R [--parent ID] [--decision ID@V ...] [--explain ...] [--eval ID@V ...] [--command ... --workdir ... --track ... --config k=v ...] [--batch B] [--manual\|--no-dispatch] [--quick-lane --report-method P --ql QL]` | 开单，落 `todo`；`launch_order` 从父单抄 decision_refs 和 batch、分 run_id；`--batch` 是调用者的自由文本，rl 不分配；带 `--quick-lane` 的工单直接落 `done_pending_review`，`QL` 存进单子的 `ql_tag` 栏（04 定），补单前提是关联的 scratch 行状态是 `open` | owner；快车道补单是 deploy 调、owner 记 gyb（04 第 60 行） |
| `rl handoff start ID [--batch B]`（接单时发现最新一次尝试已发射没收尾就认领：这一版 `adopted: true`，rl 顺带给 runs 那条写一版 `adopted`，记新 holder 的 `session_id`、`ts`；不另设 `rl run adopt`） / `amend ID [--command ... --workdir ... --track ... --config ...] [--report-method P --report-detail P --code-path P ...] [--notebook P --figure P ...] [--decision ID@V ...] [--eval ID@V ...]`（`--decision` 换 decision_refs 引用；`done_pending_review` 上也可改 `--code-path`） / `stuck ID --issue ID` / `resume ID` / `done ID [--notebook P --figure P ...]` / `accept ID`（顺带关这张单关联的 `answered` issue） / `reject ID --reason` / `withdraw ID --reason [--quote] [--cascade]` / `release ID [--note ...]`（`in_progress`→`todo` 时 `--note` 必给，`rejected`→`todo` 不要求） / `reissue ID --decision ID@V` | 转移表里的每一行一个子命令 | 按转移表 |
| `rl handoff estimate ID --step NAME --kind gpu\|cpu --smoke-seconds S --scale F` / `rl handoff estimate ID --copy-from ID2 [--scale F]` | 往最新一次尝试追加分步表一行，`estimated_seconds` 加总本次尝试；同 batch 复制 | run |
| `rl handoff show ID` / `rl handoff list [--status S] [--owner R] [--holder SESSION] [--to R] [--batch B] [--decision ID] [--line L]` | 查（`--mine` 删掉，拆成 owner 和 holder） | 谁都行 |

### 数字账

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl run add --handoff ID --attempt N --commit ... --host ... --gpus ... --log ... --tmux ... --watch-cmd ...` / `rl run finish RUN_ID --exit ok\|failed\|killed [--metric k=v ...] [--data-path P]` / `rl run relink RUN_ID --handoff ID` / `rl run show RUN_ID` / `rl run list [--handoff ID] [--decision ID] [--batch B] [--line L] [--all]` | 数字账三版（`launched`、`finished`，另有 `adopted` 由 `rl handoff start` 认领时顺带写），`add` 从发射单抄 command、config、run_id；`finish` 算 actual_seconds、同进程跑反常预警、调宿主收尾命令模板；`list` 默认只出每张单最新尝试且 `exit_status=ok` 的行，`--all` 全出，`--decision` 和 `--line` 经 `handoff_id` 反查 handoffs 的 `decision_refs` 和 line；`started_at`、`finished_at` 由 rl 填；`relink` 是 doctor 修法 | 写 run 和 gyb，查谁都行 |

### 授权、反馈、口径

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl grant add --to R --permission P --text ... [--expires ...] [--issue ID]` / `rl grant revoke ID` / `rl grant list` / `rl grant show ID` | 授权；裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收（问题 27） | 写 gyb，查谁都行 |
| `rl feedback add --target ... --text` / `rl feedback accept ID --applied-to FILE ... --text ...` / `rl feedback reject ID --text` / `rl feedback show ID` / `rl feedback list` | 反馈账；accept 校验路径存在、自动 bump `rules_version`、列出还活着的会话和它们的 rules_version、打印待办（还要改哪几处、要不要收会话、单独 commit 加跑测试） | 提谁都行，裁只有 gyb，查谁都行 |
| `rl eval propose --kind metric\|figure --name ... --definition ... [--metrics-key K \| --code-path P] [--group-by ... --x ... --y ... --uses ID ...] --applies-to ...` / `rl eval update ID ...` / `rl eval approve ID ... --quote` / `rl eval reject ID --reason` / `rl eval retire ID` / `rl eval show ID` / `rl eval list [--status S]` | 口径账；approve 一次多条一句 quote；approved 后 update 回 proposed | 提和改 analysis，批、打回、退役都是 gyb，查谁都行 |

### 快车道与杂账

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl ql open [--role deploy\|analysis] [--from ho-ID]` / `rl ql close QL --merged --handoff ID \| --dropped --reason` / `rl scratch add QL [--note ...] [--metric k=v]` / `rl scratch list [--status S]` / `rl scratch show QL` | 快车道进出和杂账；open 在锁里分 ql_tag、建 worktree（`quick_lane.worktree_root/<ql_tag>`，分支同名）或 `analysis/scratch/<ql_tag>/`；`--from` 把待干工单标 quick_lane；`close --merged --handoff ID` 的前提是 ID 是 quick_lane 补单且它的 `ql_tag` 等于 QL | `ql open`、`scratch add` deploy、analysis；`ql close --merged` 只有 deploy，`--dropped` deploy、analysis 都行（analysis 快车道没有补单）；`scratch list/show` 查谁都行 |

### 收件箱、回收、体检、通知

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl status [--line L] [--group-by line\|batch] [--json]` | gyb 的收件箱十段，见下一节；第一行打印距上次 reclaim 几天 | 谁都行 |
| `rl reclaim [--session-older-than H] [--handoff-older-than H] [--only ID ...] [--skip ID ...] [--kill] [--apply]` | 列出超过阈值没动的会话、单子、快车道，`--apply` 才动手，见下面「rl reclaim」一节 | gyb |
| `rl doctor [--ack ITEM ID] [--unack ITEM ID] [--list-acks]` | 扫九本账，每项附修法命令和「修完归谁推」，扫描项见下面「rl doctor」一节 | 查谁都行，角色跑只看不修，修法报给 owner 或 gyb；`--ack` / `--unack` 只有 gyb |
| `rl notify --text` | 发桌面通知，不进任何账；推送表和机制见 `01-gyb.md` 第五节 | rl 自己；gyb 也可以手动调 |

## 查询命令和写命令的分界

查询命令是 show、list、trace、status、inbox（只读，不顺带关任何 issue）、stale、doctor 七类，谁都能调，不进角色 json 的 `ledger_writes`；doctor 里 `doctor`（查）与 `doctor --list-acks` 是查询，`doctor --ack` / `--unack` 是写命令、只有 gyb 能敲。这是原则 2 的推论：读一律不设权，角色 json 的 `reads` 栏是纪律不是门禁。机器检查只查 SKILL.md 里出现的写命令在不在这个角色的 `ledger_writes` 里。

`rl inbox` 谁需要谁敲：角色被拉起不自动查收件箱，run 不查 inbox（run 只关注自己那张发射单，一般不会有没带单子的 run 会话）（2026-08-17 问题 28）。

## 退出码与 --json

退出码六个（定义处 03，本份照抄、两边一字不差）：

| 码 | 含义 | 附带什么 |
|---|---|---|
| 0 | 成功 | 无 |
| 1 | rl 内部错误 | 标准错误第一行固定原因种类 |
| 2 | 校验拒收 | 原因写到标准错误，包含下一步该做什么 |
| 3 | 角色无权（含角色带 `--force`、被销号会话再写账，`--as-gyb --force` 也越不过） | 同上，附「开 issue 给谁」的命令 |
| 4 | 文件锁等待超时（等 `lock.timeout_seconds`，默认 10 秒，进 `research-loop.json` 阈值表（08 第三节）） | 无 |
| 5 | 用法错（参数写错、编号不存在） | 原因写到标准错误，附正确用法或查不到的编号 |

所有非零退出，标准错误第一行是固定格式的原因种类（2 `validation`、3 `forbidden`、4 `lock_timeout`、5 `usage`、1 `internal`），`--json` 时同一个值放 `error.kind`（2026-08-17 问题 25）。

转移表外的转移一律拒收，退出码 2，带 `--force` 的 gyb 也一样。`rl handoff start` 遇到 holder 非空也是退出码 2，并把当前 holder 列出来。角色会话里 `--as-gyb` 缺 `--quote` 是退出码 2。`rl init` 在角色会话里跑是退出码 3。

所有子命令支持 `--json`。`rl status --json` 每行至少含这十二个键：`id`、`work_type`、`owner`、`holder`、`holder_alive`、`status`、`age_hours`、`line`、`decision_refs`、`batch`、`log_path`、`watch_cmd`。

另外三条的 `--json` 最小结构（2026-08-17 gyb 裁）：`rl inbox --json` 是一个对象，五个键对应下面「rl inbox」的五项，每个键一个数组，数组元素就是那本账的原始行；`rl doctor --json` 是一个数组，每个元素含 `item`（项号）、`ids`（涉及的编号）、`fix_cmd`、`push_to`；`rl reclaim --json` 是一个数组，每个元素含 `kind`（session、handoff、ql 三种）、`id`、`idle_hours`、`action`。以后加字段只加不删。

## 锁与写序

定义处 03，本份照抄、两边一字不差。`loop/.lock` 一把全局文件锁。扫号、分配编号、追加这三步放在同一把锁里，不许扫完号再排队写，否则同角色两个会话会撞号。锁里分配的编号包括 `ql_tag`、`run_id`（`batch` 是调用者自由文本，rl 不分配，2026-08-17 问题 9）。

跨两本账的写入定死写序：先写 issue 拿到编号，再写单子那一行引它。中间崩了顶多多一条没人引的 issue，`rl doctor` 扫得出来。

## rl inbox

角色的收件箱，五项：

1. 本角色名下 open 的 issue。
2. owner 是本角色而 holder 为空的单子。
3. 本会话手上单子引的过版决定。
4. 发给本角色的通知。通知类 issue 是 `withdrawn`、`orphaned`、`fyi` 三种 kind；inbox 只读不关，通知类 issue 由收件人做完了 `rl issue close`（03 写权补 assignee 也能关）。
5. 本角色提的 feedback 的裁决。

run 不查 inbox：run 只关注自己那张发射单，一般不会有没带单子的 run 会话（2026-08-17 gyb 裁，问题 28；施工计划第五节「run 的 `rl inbox` 不查过版」那句例外扩大成这一句）。上位规矩：角色被拉起不自动查 inbox，`rl inbox` 谁需要谁敲。

两处原文不一致：第 3 项的范围。设计文档写的是「本角色持有或拥有的单子里过版的决定引用」，施工计划第六节写的是「本会话手上单子引的过版决定」。2026-08-17 gyb 裁：取施工计划，只列 holder 是本会话的单子引的过版决定；owner 名下但不在本会话手上的过版单子归 `rl status` 段 6，由 gyb 看。

## rl trace

`rl trace <编号>` 收五种编号：`dec-`、`ho-`、`run_id`、`iss-`、`eval-`。一条命令打出 run 到发射单到工单到决定各版本的整条链。这条命令是原则 9 的落点：每张单、每条 run 都有一条回到决定的显式链，链靠 handoffs 的 `parent_id` 和 `decision_refs` 两个字段走。

## rl status 的十段

`rl status` 是 gyb 的收件箱，段落从 gyb 的 use case 表倒推。十段照施工计划第六节：

| 段 | 列什么 |
|---|---|
| 1 | 没到终态的单子（owner、holder 及活没活着、状态、挂了多久、线、发射单带 `log_path` 和 `watch_cmd`） |
| 2 | assignee 是 gyb 的 open issue，超过阈值的标出 |
| 3 | 等批的口径 |
| 4 | 等验收的单子 |
| 5 | 等 gyb 拉起的：owner 无活会话的 todo、`dispatch=manual` 的 |
| 6 | 过版的单子和 retired 决定名下的活单 |
| 7 | holder 会话超过 `status.stale_holder_minutes` 没写账的开干单 |
| 8 | 等裁的 feedback |
| 9 | review/ 最近的清单、活着的会话（含 focus）、没关的快车道 |
| 10 | 上次 doctor 没修的 |

第一行打印距上次 reclaim 几天。整份可以按 `--line` 过滤、按 `--group-by line|batch` 归组；`line` 就是根决定编号。

段 7 和 reclaim 用的 `last_activity` 不落账，取九本账里该 `session_id` 的最大 `ts`（含 sessions 账自己的行）。`rl status --json` 里 `holder_alive` 是 holder 那个 `session_id` 在 sessions 账的最新版是不是 `open`；`age_hours` 从这张单当前状态那一版的 `ts` 起算到现在（2026-08-17 gyb 认，问题 29）。

段落用到的阈值默认值定义在 `08-trees-init-and-host.md` 第三节阈值表：段 2 的 `issues.gyb_stale_hours` 是 24 小时，段 7 的 `status.stale_holder_minutes` 是 30 分钟，段 9 的 `status.review_recent_days` 是 7 天。

## rl reclaim

参数六个：`--session-older-than H`、`--handoff-older-than H`、`--only ID ...`、`--skip ID ...`、`--kill`、`--apply`。不带 `--apply` 只列出，带了才动手。

动手的规矩，一类一条（处置规矩定义处 04，本份照抄）：

- 会话：标 `reclaim` 销号，并 release 名下开干的单。
- 开干的发射单：默认不杀进程，留给下一个 run 认领；带 `--kill` 才走中断收尾，也就是杀进程、释放显存、宿主销号、runs 落 `killed`。
- `stuck` 的单子：只把 issue 改派 owner，状态不动。
- `done_pending_review` 和 `todo` 的单子：只列出附现成命令，不动手。
- 被打回的单子：超过 `reclaim.handoff_idle_hours` 没动的推回 `todo`（走 `rejected`→`todo` 那一行，`actor` 记 gyb、`via=reclaim`），owner 重新拉起。
- 结束时按 owner 分组打印待拉起的单子和加载命令，并自动跑一遍 doctor。

两处原文不一致：开干的发射单杀不杀进程。设计文档「交接与会话生命周期」一节写的是「回收对开干的发射单先走中断收尾（杀进程、释放显存、宿主销号、runs 落 killed）再交回待干」，没有条件；施工计划第六节和第四节转移表写的是默认不杀、`--kill` 才杀。2026-08-17 gyb 裁（在 `04-handoffs-and-sessions.md`）：默认不杀，`--kill` 才杀。

阈值默认值（定义在 `08-trees-init-and-host.md` 第三节阈值表）：`reclaim.session_idle_hours` 48 小时，`reclaim.handoff_idle_hours` 72 小时，`reclaim.ql_idle_days` 7 天。

## rl doctor

`rl doctor [--ack ITEM ID] [--unack ITEM ID] [--list-acks]` 扫九本账。十九项：前十八项照施工计划第六节，第 19 项是 2026-08-17 从待验证第 10 条的失败备案升上来的。修法和「修完之后归谁推」两栏 2026-08-17 gyb 裁（第 3、5、6 项的修法出自源文档，其余是这次补的）。「只报不修」的项 doctor 只列出涉及的行，不给修法命令，人看了决定。

| # | 扫描项 | 修法 | 修完之后归谁推 |
|---|---|---|---|
| 1 | 编号重复 | 只报不修：列出撞号的行各自的 `ts`、`actor`、`session_id` | gyb |
| 2 | 引用悬空（handoffs 的 `parent_id`、`decision_refs`、`evaluation_refs`、`issue_id`，issues 的 `handoff_id`，evaluations 的 `uses`，decisions 的 `sources`、`merged_from`；runs 的 `handoff_id` 归第 6 项，这里不重报） | handoffs 行 `rl handoff amend ID --decision ID@V` 或 `--eval ID@V` 换引用；其他账只报不修，列出那一行、字段名、指向的编号 | 那一行的 owner：handoffs 是单子 owner，issues 是开 issue 的角色，decisions 和 evaluations 是写那条的 actor；查不出的 gyb |
| 3 | `stuck` 单子没有 issue | `rl issue link ID --handoff ID`；没有可挂的 issue 先 `rl issue open --handoff ID` 再 link | 把单子转成 `stuck` 的角色（`stuck` 那一版的 actor）；无活会话则单子 owner |
| 4 | `cannot`/`failed`/`denied` 且 open 且没有单子指回的 issue | 单子确实卡住：`rl handoff stuck ID --issue ID` 补转移；单子已经过去：`rl issue close ID` | 开 issue 的角色 |
| 5 | `done_pending_review` 的交付物路径不存在 | `rl handoff amend ID --report-method P`、`--code-path P`、`--notebook P`、`--figure P` 改成正确路径 | 交活的角色（`done` 那一版的 actor） |
| 6 | runs 行 `handoff_id` 为空、悬空或不是 launch_order | `rl run relink RUN_ID --handoff ID`；这条 run 本来就不挂单（比如 gyb 手动跑的）用 `rl doctor --ack 6 RUN_ID` | run；无活会话则 gyb |
| 7 | runs 有 `launched` 版、超过 `reclaim.handoff_idle_hours` 没 `finished` 版 | 进程还活着：`rl handoff show ID` 取 `watch_cmd` 去接管（原则 11，下一个 run 会话接单时自动认领）；进程已经死了：`rl run finish RUN_ID --exit failed` 或 `--exit killed` | run；无活会话则 gyb |
| 8 | runs 挂在 `withdrawn` 的单子上且没有 `finished` 版 | 先按 `watch_cmd` 杀进程，再 `rl run finish RUN_ID --exit killed` | 收回单子的角色（`withdrawn` 那一版的 actor） |
| 9 | 快车道工单已 accepted 但没有关联发射单 | `rl handoff open --type launch_order --parent ID ...` 补正式发射单；确实不需要正式重跑（比如只画图的分析快车道）用 `rl doctor --ack 9 ID` | 工单 owner |
| 10 | approved 口径引的 metrics 键在 runs 账里不存在 | 只报不修：列口径编号、`metrics_key`、最接近的已有键名 | analysis |
| 11 | `answered` 超过 N 天没 close 的 issue | `rl issue close ID`；回答不管用就 `rl issue close ID` 再另开一条新 issue、正文引旧编号 | 开 issue 的角色 |
| 12 | 单子回了 `todo` 而关联 issue 还 open | `rl issue close ID` | 开 issue 的角色 |
| 13 | `in_progress` 的 holder 不在活着的会话里 | `rl handoff release ID --note ...` 或 `rl reclaim --only ID --apply` | 单子 owner；无活会话则 gyb |
| 14 | sessions 没有结束版且超阈值没写账 | `rl session end --session ID --reason ...` | gyb |
| 15 | retired 决定名下有活单 | `rl handoff withdraw ID --reason ... --cascade` | 单子 owner |
| 16 | 决定来源指 notes/ 但 grants 里没有该 actor 的 read:notes | 只报不修：附 `rl grant add --to R --permission read:notes`（事后补授权）或 `rl decision update ID` 换来源两条命令 | gyb |
| 17 | accepted 的 feedback 的 applied_to 为空 | `rl feedback accept ID --applied-to FILE ...` 追加一版补齐 | gyb |
| 18 | loop/runs.jsonl 与宿主 ops/runs.jsonl 对不上的 run_id | 只报不修：列出两边各有没有 | run |
| 19 | sessions 行 `model` 是 `unknown` | `rl session amend ID --model M` | gyb |

第 11 项的 N 是 `issues.answered_stale_days`，默认 3 天（定义在 `08-trees-init-and-host.md` 第三节阈值表）。第 7 项的阈值直接用 `reclaim.handoff_idle_hours`（默认 72 小时），不另开一项。

`--ack ITEM ID` 的规矩（2026-08-17 gyb 裁）：`--ack` 和 `--unack` 是写命令、只有 gyb 能敲；ack 写进 `loop/.doctor-acks.jsonl`，这个文件是普通文件、不算九本账之一，03 账本总规矩（只增不改、锁、进 git、脏树白名单）不管它，一行记 `item`、`id`、`ts`、`actor`、`session_id`；ack 过的那一项那个编号永久不再报，`rl doctor --list-acks` 列出全部 ack，`rl doctor --unack ITEM ID` 撤销一条（追加一行 `unack`）。

角色跑 doctor 只看不修，修法报给表里「归谁推」那一栏的人。doctor 扫出还没修的东西进 `rl status` 段 10。`rl reclaim --apply` 结束时自动跑一遍 doctor。

doctor 只做脚本能判的检查，也就是上面十九项。判断类的检查（比如「这张单的报告有没有回答它引的决定」「这条 run 的 config 和发射单写的一不一样」）不在 doctor 里：问题清单写成一份文件放 `common/`，由 reviewer 角色派 sonnet subagent 一人领一题逐条查，查出来的写进 review/ 清单，要不要开 issue 由 gyb 看完用自己的权限开（2026-08-17 gyb 裁，问题 6 后改：只写清单不开 issue；见 09-common-and-feedback.md 和 14-role-reviewer.md）。

## rl notify

`rl notify --text` 的推送表和机制定义在 `01-gyb.md` 第五节（2026-08-17 gyb 裁，一件事归 01）；定期提醒（待验证第 7 条、`notify.reminder_days`）同在 01 第五节。本份只留命令表里的签名行。

## 和别的 part 的接口

- actor 判定、`--as-gyb` 加 `--quote`、`--force --reason`（含 `--force` 只越完整性前提、不越表外转移）、grants 不限裸终端（角色会话 `--as-gyb --quote` 也收）：定义处是 `01-gyb.md` 第二节，本份「actor 怎么定」一节是命令行写法，两边一字不差。gyb 的 use case 表（`rl status` 十段和各 list 的过滤维度从它倒推）、推送表归哪几段：`01-gyb.md`。
- 决定账的来源三类、新版本还是新条的判据、`rl decision add/update/confirm/retire/merge/stale` 背后的规矩：`02-decisions.md`（`02` 抄了这几条的签名，`stale` 签名已改成 `[--handoff ID] [--all]`，两边同步）。
- 九本账公共骨架七样（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`）和两个可选栏（`force_reason`、`via`；`fix_for` 2026-08-17 问题 15 删），七本账的字段与必填规则，退出码 2 查的就是这些：`03-ledgers.md`。本份裁了 `via` 栏、sessions 的 `amend` 版（只改 `model`）、handoffs 的 `actual_seconds` 只从 runs 来，已收（03 第 43/118/176 行）。
- 派活单七个状态、转移表六栏全文、holder 只在 `in_progress` 非空这条不变量、会话登记与销号的钩子、reclaim 动手的规矩：`04-handoffs-and-sessions.md`。命令表里 `rl handoff open/start/amend/stuck/resume/done/accept/reject/withdraw/release/reissue/estimate` 十二条各自的前提在那张表里（`estimate` 现在在表里有行，`in_progress` 上，holder 写）；`done` 已去掉 `--actual-seconds`、`session end` 顺带 release 的 actor 和 `via` 写法，已收（04 第 41/72 行）。
- 角色 json 的 `reads`、`writes`、`ledger_writes`、`dispatches_to`、`model` 五栏，钩子只挂 Write 和 Edit、只拦两类事，`test_skill_refs` 只查写命令，会话状态文件的路径：`06-hooks-and-permissions.md`。
- `rl ql open/close` 的进出规矩、`ql_tag` 的形状、快车道补正式发射单（doctor 第 9 项的依据）：`07-quick-lane.md`。
- `rl init` 建的六样加一节、`research-loop.json` 阈值表（本份用到 `issues.gyb_stale_hours`、`issues.answered_stale_days`、`status.stale_holder_minutes`、`status.review_recent_days`、`reclaim.*`、`notify.reminder_days`、`quick_lane.worktree_root`，新加 `lock.timeout_seconds` 默认 10 秒）、宿主发射器的命令模板（`launcher.free_cmd`、`launcher.launch_cmd`、`launcher.finish_cmd`）、`rl run finish` 调哪条宿主命令：`08-trees-init-and-host.md`。`rl init` 在角色会话里拒收退出码 3，已收（08 第一节）。
- `rl feedback accept` 的 `rules_version` 和母版改动的规矩、公共规矩八条、issues 九种 kind、判断类检查的问题清单文件（本份裁：放 `common/`）：`09-common-and-feedback.md`。
- `read:notes` 的申请走法（`rl init` 问的那一次和 doctor 第 16 项）：`10-role-idea.md`。
- `rl handoff estimate` 的分步表怎么填、看门狗（独立进程，只许调查询命令，判定由 run 会话转写进账）、`rl run add/finish` 与认领顺带写的 `adopted`，三版：`12-role-run.md`。
- `rl eval propose/update/approve/reject/retire` 的口径两类与四态：`13-role-analysis.md`。
- `rl session focus` 谁用、`review/` 清单的五栏、判断类检查怎么派 sonnet subagent 一人一题：`14-role-reviewer.md`。
- 待验证清单十一条（含第 6 条桌面通知、第 7 条定时提醒、第 1 条会话 id 变量）的测法、通过标准、失败备案：`30-build-steps-verify-tests.md`。本份把待验证第 4 条备案「`rl init` 检查调用者不是任何角色」升成正案、把第 10 条备案里的「doctor 列 `model=unknown`」收成 doctor 第 19 项，要 `30` 收。

## 源文档没写清的（留给 gyb）

（2026-08-17 十三条全部裁完，每条的裁决见文末「裁决记录（日期）」，正文对应处已改。）

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

以下条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，保留场景名、序号、严重度、kind、原文、依据、改法，不做判断、不改字。

### param-tweak（45 步，gyb 动手 8 次）

5. [slows/principle_violation] 第 44 步：违反原则 7（快车道有明确的进和出）和原则 6（进出对称）：进有 rl scratch add 登记，出没有任何登记通道——scratch 只有 add 和 list、行里没有状态字段，handoffs 又没有 ql_tag 字段，rl status 的「没合回的快车道 worktree」这一段永远消不掉
   - 依据：plans/2026-08-16-research-loop-build-plan.md:141; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-next-steps.md:21
   - 改法：加 `rl scratch close --tag QL --handoff ID`，status 按有没有 close 行判断合没合回

8. [slows/contradiction] 第 27 步：设计文档说替 gyb 打 --as-gyb 带 --quote「靠纪律，钩子不拦」，施工计划和测试 9 说缺 quote 退出码 2 硬拒收；更麻烦的是 gyb 本人和模型在同一个角色会话里打命令，rl 读的是同一个会话状态文件，分不出是谁打的，硬拒收就连 gyb 自己验收都要造一句原话
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：定成硬拒收并只留一个值：gyb 本人在角色会话里用 --as-gyb --by-hand 免 quote，模型用一律要 quote

16. [cosmetic/missing] 第 8 步：ql_tag 由调用者用 --tag 手填，谁分配这个 01 序号、撞了怎么办没写；锁那一段只保证自动编号的账不撞号
   - 依据：plans/2026-08-16-research-loop-build-plan.md:141; plans/2026-08-16-research-loop-next-steps.md:92
   - 改法：加 `rl scratch new` 由 rl 在锁里分配 ql_tag 并打印出来

17. [cosmetic/contradiction] 第 4 步：设计文档说 SKILL.md 正文出现的每条 rl 子命令都要在角色 json 的 ledger_writes 里，施工计划的测试 13 只查写命令；deploy 上线要跑的 rl decision stale、rl handoff show 都是查询命令，不在 deploy 的 ledger_writes 里，按设计文档那句机器检查就红
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:215; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：把设计文档那一句改成「每条 rl 写命令」，或角色 json 加一栏 queries 单列查询命令

### new-idea（39 步，gyb 动手 7 次）

5. [slows/contradiction] 第 8 步：设计文档说 gyb 亲自打 --as-gyb 的落 decisions.gyb.jsonl、idea 替 gyb 记的落 decisions.idea.jsonl 并带 quote，可角色会话里的命令全是模型打的，而施工计划规定模型打 --as-gyb 必须带 quote、账行 actor 记 gyb，决定文件又按 actor 拆名，同一条命令按两份文档会落进两个不同文件
   - 依据：plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:29; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：明写「decisions.gyb.jsonl 只收裸终端写的行，角色会话里模型打的 --as-gyb 一律落 decisions.<角色>.jsonl 并记 quote」

14. [cosmetic/missing] 第 27 步和第 28 步：gpu-run 的 Phase 4 要求把自助监控命令交到用户手上，可这条链上 run 的上游是 deploy subagent、gyb 不在链上；rl status 列的是单子、会话和快车道 worktree，没有一栏给正在跑的实验的日志路径或宿主 watch 命令，gyb 中途只能自己去猜命令
   - 依据：plans/2026-08-16-research-loop-build-plan.md:161; plans/2026-08-16-research-loop-build-plan.md:142; .claude/skills/gpu-run/SKILL.md:97
   - 改法：rl status 的在办单子一栏顺带打印 runs 账里的 log_path、artifact_dir 和宿主的 watch 命令

### result-wrong-review（25 步，gyb 动手 11 次）

2. [slows/too_heavy] 第 1 步到第 5 步：gyb 只是想知道「这个数字是按哪条决定跑出来的」，按文档要在裸终端敲 rl status、rl run list、rl handoff show、rl decision list、rl decision show 五条命令，中间还要靠 launch.command 里的路径人工比对，和「想法要快速、多次迭代」的目标不相称。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-build-plan.md:137
   - 改法：第六节命令表加一条 `rl trace <run_id>`，一条命令打出 run 到发射单到工单到决定各版本的整条链。

4. [slows/contradiction] 第 9 步、第 10 步、第 13 步（reviewer 全程只调查询命令）：设计文档说机器检查是「SKILL.md 正文出现的每条 rl 子命令都要在这个角色 json 的 ledger_writes 里」，施工计划的 test_skill_refs 只要求写命令在 ledger_writes 里；reviewer 的 SKILL.md 必然写到 rl decision stale、rl decision show、rl run show、rl handoff show 这些读命令，按设计文档那句检查必挂。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：把设计文档第 40 行改成「写命令进 ledger_writes、读命令进 reads」，和测试 13 对齐。

6. [slows/contradiction] 第 19 步和第 23 步：`--as-gyb` 缺 `--quote` 到底硬不硬拦：设计文档说「这条靠纪律，钩子不拦，reviewer 事后可查」，施工计划第六节说「缺 quote 时 rl 拒收（退出码 2）」；再者 rl 只看会话状态文件，分不出角色会话里这条命令是 gyb 本人敲的还是模型敲的，硬拦会把 gyb 本人一起拦住，和原则 1「任何权限检查对 gyb 不生效」相冲。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：统一成硬拦，并明写 gyb 本人在角色会话里也要带 --quote（自引一句即可），设计文档第 34 行的「靠纪律」删掉。

12. [cosmetic/missing] 第 6 步到第 17 步：reviewer 干活期间没有任何派活单，owner 和 holder 都不存在，rl status 只有等清单落盘之后才在「最近 7 天的 review 清单」那一段看得到；审到一半会话崩掉或 gyb 忘了这件事，收件箱里没有任何痕迹。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:182
   - 改法：rl status 的活着会话那一段带上 reviewer 会话正在审哪条决定（gyb 点名时用 rl 记一行），或给 reviewer 开一张 owner 是 gyb 的 review_order。

### plot-new-plan（17 步，gyb 动手 8 次）

3. [slows/principle_violation] 第 10 步（gyb 开分析单）：违反原则 1。原则 1 写 gyb 在任何终端、任何角色会话里都能行使自己的权，任何权限检查不生效；但施工计划只让 gyb 豁免转移表「谁能写」一栏和「谁能调」检查，「前提」一栏照旧生效，于是 gyb 自己开分析单时被 evaluation_refs 必须 approved 这条前提挡住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:77; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：在施工计划第四节表头明写「前提」一栏对 gyb 生不生效，若生效就把它改称数据完整性校验、和权限检查分开命名。

9. [slows/ambiguous] 第 9 步与第 15 步（会话里以 gyb 身份写账）：施工计划写「角色会话里的模型用 --as-gyb 必须同时给 --quote」，但 rl 看到的只是同一个 session_id 下的一条命令，分不出键盘前面是 gyb 本人还是模型；gyb 亲手在角色会话里打 --as-gyb 要不要带 quote 两种读法都说得通。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：改成「角色会话里的 --as-gyb 不论谁敲一律要 --quote」，把它定性成痕迹而不是身份判定。

12. [cosmetic/missing] 第 13 步到第 14 步（图画完之后叫 gyb）：单子进 done_pending_review 只出现在 rl status 里，桌面通知只在 issue 改派给 gyb 的时候发；gyb 不坐在这个会话里的时候，得靠自己轮询才知道图画好了。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：把「等 gyb 验收的单子」也接进 rl notify，或者在设计文档里明写这一类只进 rl status、不通知。

### next-plan-after-results（36 步，gyb 动手 16 次）

3. [slows/principle_violation] 第 14 步：违反原则 1。原则 1 和施工计划裁决 6 说 gyb 不受任何权限检查影响，转移表却只给 gyb 豁免「谁能写」一栏、不豁免「前提」一栏，于是 gyb 自己也开不出引未批口径的分析单、也收不了缺交付物的单子。两句话对「权限检查」的范围理解不一样
   - 依据：2026-08-16-research-loop-build-plan.md:77; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15
   - 改法：把原则 1 改写成「权限检查对 gyb 不生效，数据完整性前提对谁都生效」，并给 gyb 一个 `--force` 带原因写进账行

5. [slows/ambiguous] 第 13、19 步：gyb 本人坐在角色会话里敲 `--as-gyb`，rl 分不出是 gyb 敲的还是模型敲的，测试 9 又硬性要求缺 quote 退出码 2，等于逼 gyb 引用自己刚说的话；文档只写了「角色会话里的模型」必须带 quote，没写 gyb 本人要不要
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:211; 2026-08-16-research-loop-next-steps.md:34
   - 改法：明写 `--as-gyb` 一律要 quote、gyb 本人把自己那句话填进去即可，SKILL.md 里给一条示例

6. [slows/ambiguous] 第 26 步：讨论里定下的结论落 decisions.gyb 还是落 decisions.idea 带 quote，判据是「gyb 亲自打的」还是「idea 替 gyb 记的」。可是在手动加载角色的会话里 rl 命令都是模型敲的，「gyb 亲自打」这条路实际只存在于另开裸终端，同一条结论两处都说得通，reviewer 的基准会散在两本账里
   - 依据：2026-08-16-research-loop-next-steps.md:34; 2026-08-16-research-loop-next-steps.md:44; 2026-08-16-research-loop-build-plan.md:121
   - 改法：定死「角色会话里一律落角色那本账带 quote，decisions.gyb 只收裸终端写的」，把判据从「谁亲手敲」换成「哪个会话」

7. [slows/missing] 第 33 步：「这条方向看完结果继续做、设定不变」这一支没有落点。决定不换做法就不追加版、不换问题就不开新条，账上留不下 gyb 看过这批数字并确认继续的痕迹，下一轮 reviewer 和 `rl decision stale` 都看不到这次复核
   - 依据：2026-08-16-research-loop-next-steps.md:46; 2026-08-16-research-loop-next-steps.md:109
   - 改法：加一条 `rl decision confirm ID --source run:... --source file:...`，追加一版正文不变、只增来源

8. [slows/missing] 第 27、36 步：决定 retire 之后，引用它的在办单子没人扫。doctor 的八项扫描和 rl status 的七段都没有「retired 决定名下还有没到终态的单子」这一项，设计文档又把停不停全交给 gyb 点名，忘了收回就一直挂着
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:112
   - 改法：doctor 和 status 各加一项「retired 决定名下还有活单」，附上 `rl handoff withdraw --cascade` 的修法

### run-crash-midway（40 步，gyb 动手 4 次）

2. [slows/ambiguous] 第 3、9 步：看门狗写账时 actor 判成谁，两种读法都说得通。build-plan.md:166 说「看门狗的判定进 issues 账」，读成 monitor 自己打 `rl issue open`；但 monitor 是独立进程，按 build-plan.md:121 读不到会话状态文件就判 actor 是 gyb、session_id 是 cli，这条 issue 会记成 gyb 开的。读成 run 会话来打则 build-plan.md:166 那句落空。两种读法分别导致账行 actor 记错，或者 monitor 和会话各开一条重复 issue。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：把 monitor 明确排除在写账者之外，改写成「看门狗的判定由 run 会话转写进 issues 账」。

4. [slows/missing] 第 19 步：转移表 build-plan.md:85 的 stuck→todo（谁能写=回了 issue 的那个角色，前提=关联 issue 已 answered）在 bin/rl 命令表 build-plan.md:134 里没有对应子命令，只能借 `release`；而 release 在转移表 build-plan.md:93 那一行的谁能写是「销号钩子、reclaim、owner」、前提只有「holder 清空」，借它就绕开了「issue 必须已回」这个前提。本场景 deploy 恰好既是 owner 又是回 issue 的人才糊得过去，工单场景（owner 是 idea、holder 是 deploy、回 issue 的是 idea）同样糊得过去但语义已经错位。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：给这一行加一个专门的子命令 `rl handoff resume ID`，前提校验关联 issue 是 answered。

5. [blocks/blocked] 第 24 步：deploy 修完代码之后，发射单 ho-0013 的 launch.command 和 args 还是崩之前那一版，命令表 build-plan.md:134 里没有任何改 launch 子对象的子命令，账又是只增不改（next-steps.md:92）。三条路都不通：带着旧命令跑（跑的和账上写的不一样）、开一张新发射单（旧单子只能 withdraw，转移表里 stuck 走不到重开）、手改账（钩子和入账校验都禁止）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-next-steps.md:92
   - 改法：加 `rl handoff relaunch ID --command ... --workdir ...`：给发射单追加一版新的 launch 子对象并把状态带回 todo。

8. [slows/missing] 第 31、40 步：数字账里 killed 的 r1 和 ok 的 r2 挂同一个 handoff_id，没有任何字段标「r1 这条不算数」。build-plan.md:137 的 `rl run list --handoff/--decision` 会同时吐两条，analysis 按决定或 batch 分组时（next-steps.md:80 说 analysis 要顺决定到发射单到 run_id 这条链）会把废跑混进来；build-plan.md:144 的 doctor 也不扫这种情况（r1 有对应发射单，不报）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：`rl run list` 默认只出 exit_status=ok 的行，要废跑加 `--all`。

9. [slows/missing] 第 38、39 步：issue 从 answered 到 closed 谁打、什么时候打没写。run 的 ledger_writes 只有 issue open（build-plan.md:105），deploy 和 idea 都有 close（:101、:103）但没规定何时用；`rl status` 七段（:142）只列改派给 gyb 超时的 issue，`rl doctor` 八项（:144）也不扫 answered 未 close 的 issue。结果是每次崩溃都留一条挂着的 issue，只有 gyb 偶然翻到才收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl handoff accept` 时自动 close 掉这张单子关联的 answered issue，doctor 补一项「answered 超过 N 天没 close」。

### n-launch-orders（58 步，gyb 动手 10 次）

11. [slows/principle_violation] 第 41 步：违反原则 1（gyb 是超级用户，钩子、入账校验、转移表的谁能写对 gyb 一律不生效）。施工计划规定角色会话里用 --as-gyb 缺 --quote 一律退出码 2，而 rl 分不出键盘前面坐的是 gyb 本人还是模型，结果 gyb 在自己手动加载的角色会话里反而行使不了 gyb 权，只能退出会话回裸终端。这和裁决 6「gyb 在任何终端、任何角色会话里都能插入」直接打架。
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15; 2026-08-16-research-loop-next-steps.md:34
   - 改法：缺 quote 时不拒收，改成照写并在账行打一个 quote_missing 标记留给 reviewer 事后查。

12. [slows/missing] 第 18、20 步：5 个 run subagent 的监控入口到不了 gyb 眼前。gpu-run 要求发射后把 gpu-jobs watch 和网页交给用户，但 subagent 的输出只回到 deploy 会话；rl status 列的是单子状态和挂了多久，不含进度、速率、ETA。gyb 在这几个小时里看不到这一批五张卡跑到哪了。
   - 依据：.claude/skills/gpu-run/SKILL.md:97; 2026-08-16-research-loop-build-plan.md:161; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:124
   - 改法：rl run add 时把宿主的 tmux session 名和监控命令写进 runs 行，rl status 按 batch 汇一段进度出来。

14. [slows/missing] 第 46 步：同一张发射单重跑之后名下挂了两条 run（一条 killed 一条 ok），`rl run list --batch` 会把 6 条一起吐出来，去重和筛掉失败的规则没写，analysis 按 batch 拉数分组的时候同样吃到这 6 条。这一步只能自己挑。
   - 依据：2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-next-steps.md:80
   - 改法：rl run list 默认只出 exit_status=ok 且每张发射单取最新一条，加 --all 才出全部。

17. [cosmetic/missing] 第 13 步：run 上线第一个动作是跑 rl decision stale，但 run 的角色 json 里 reads 不含 decisions 账，发射单上也没有 decision_refs，这条检查对 run 是空转。
   - 依据：2026-08-16-research-loop-build-plan.md:131; 2026-08-16-research-loop-build-plan.md:105; 2026-08-16-research-loop-build-plan.md:81
   - 改法：把「上线跑过版检查」限定给 idea、deploy、analysis 三个角色，或者让 launch_order 继承父工单的 decision_refs 之后 run 再查。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

6. [slows/missing] 第 7 步：文档只在两个时机查过版：「角色上线第一个动作跑过版检查」（next-steps.md:111）和 `rl status`（next-steps.md:124）。决定改版的那一刻，`rl decision update`（build-plan.md:128）不输出任何「有 N 张在办单子引着旧版」的提示。本场景是我按原则 6 让 idea 主动再跑一次 `rl decision stale`，文档没有这条规矩；idea 不跑就没人发现。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-build-plan.md:128; plans/2026-08-16-research-loop-build-plan.md:131
   - 改法：`rl decision update` 和 `retire` 写完那一刻当场列出引旧版且未到终态的单子，并把它们的 holder 会话一起打印出来。

7. [slows/contradiction] 第 9、20 步：原则 6（next-steps.md:20）写「所有等 gyb 处理的事由 rl status 一处列出，桌面通知只是它的推送」，issues 一节（next-steps.md:97）写「只有改派到 gyb 名下的时候 bin/rl 才给 gyb 发通知，其余不发」。过版、等批口径、等验收这几段按后一句就永远不推送，gyb 只能靠自己想起来跑 rl status。本场景要不是 gyb 自己就是改决定的人，过版没人叫他。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：把「哪几段触发推送」列成一张表写进第八节阈值旁边，过版且有 holder 的单子归进推送那一档。

8. [slows/principle_violation] 第 11 步：违反第 1 条原则（next-steps.md:15「任何权限检查对 gyb 一律不生效」）。build-plan.md:121 规定角色会话里用 `--as-gyb` 缺 `--quote` 就退出码 2 拒收，而 rl 分不出这条命令是 gyb 本人敲的还是会话里的模型代打的，于是 gyb 本人在角色会话里行使 gyb 权也会被拒收。本场景 gyb 因此被逼退出去另开一个裸终端才收得掉 ho-0013。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：缺 quote 时不拒收，改成落账时把这一行标 `quote_missing` 交给 reviewer 事后查，硬拦只留给模型自己发起的不可逆动作。

13. [slows/missing] 第 20 步：rl 自动开的 `kind=withdrawn` issue 的 assignee 是角色不是会话（build-plan.md:59），run 的 subagent 收到信号后就结束了，这条 issue 没人回也没人关。doctor 的扫描项里只有「没人引用的 issue」（build-plan.md:144），这条带着 handoff_id 所以扫不出来，会一直挂在 `rl status` 的 open 列表里。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：withdraw 自动开的 issue 直接落成 `closed`（它是通知不是问题），或者 doctor 加一条「holder 已销号但 withdrawn issue 仍 open」的扫描并附 close 命令。

14. [slows/missing] 第 14、23 步：被收回的发射单跑出来的那条 run（exit killed、config 记的是旧评测集）留在 loop/runs.jsonl 正账里，没有任何作废标记。决定来源的第三类就是 run_id（next-steps.md:46），后面谁都能拿它当来源；doctor 的扫描项（build-plan.md:144）也不查「run 挂在已收回的单子上」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：doctor 加一条扫描「runs 行的 handoff 已 withdrawn」，并且 `rl decision add --source run:ID` 引到这种 run 时当场警告。

16. [slows/too_heavy] 第 6 到 22 步整段：「换个评测集」这一件事走了 23 步、gyb 亲自动手 8 次、牵动 4 个会话，其中 5 步是纯手续（分两次收单、两个会话销不掉号、手动关两条通知 issue、按新版本重开一张内容几乎相同的工单）。目标那一节写的是「想法要快速、多次迭代」（next-steps.md:7），这条路上没有任何一条把「决定改版后重派」压成一步的捷径。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：加一条 `rl handoff reissue ho-XXXX --decision ID@V`：一条命令连锁收旧单、清 holder、继承 explanation 开新单，并通知全部 holder。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

7. [slows/ambiguous] 第 10 步、第 26 步：--as-gyb 的 --quote 是给「模型替 gyb 打」设的，可 rl 拿不到「这条命令是 gyb 的手指打的还是模型打的」这个信息，同一个角色会话里两种情况长得一模一样。要么一律强制 quote（gyb 本人被迫引用自己一句话），要么一律不强制（模型代打的痕迹就没了）。本次模拟只能绕道：gyb 另开裸终端验收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：定死一律强制 --quote，gyb 本人打的时候 quote 里填自己那句话；文档里把这条写成「无条件」而不是「模型用的时候」。

12. [slows/missing] 第 6 步：取一条决定的指定版本没有命令。rl decision show 只有默认最新版和 --history 全量两档，可单子按派出时引的那一版继续做，deploy 要的就是 dec-idea-0007 第 2 版；只能把全部历史拉进上下文再自己挑，和读法纪律「挑最小的读法、大文件禁止整读」直接顶上。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-next-steps.md:144
   - 改法：rl decision show 加一个 --version V 参数，handoff show 里显示 decision_refs 时顺带把那一版正文带出来。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

5. [slows/contradiction] 第 2 步：rl status 列几段两处不一样：设计文档列七段（单子、issue、口径、等验收、过版、review 清单、快车道 worktree），施工计划列八段（多一段「活着的会话」）。按原则 8，施工计划只有第一节的裁决优先，第六节是草案，所以设计文档赢、「活着的会话」被砍——而本场景里 gyb 恰恰要靠这一段看两条线各有谁在干活。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-next-steps.md:22
   - 改法：把「活着的会话」补进设计文档第 124 行那句，两处对齐成八段。

6. [slows/too_heavy] 第 9、10、20、25 步：收件箱里每一条都要两跳才知道属于哪条线：issue 行只有可选的 handoff_id，要 issue show 再 handoff show；口径行只有自由文本 applies_to；scratch 行只有 ql_tag、worktree、base_commit。一条线一天挂三五条，早上第一眼就变成十几条命令。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：rl status 每行直接把这一行溯到的决定编号和线名打出来，别让 gyb 自己跳。

11. [slows/too_heavy] 第 15、18 步：角色上线第一个动作 rl decision stale 没有范围参数，列的是全库过版的单子和决定。两条线并行时，蒸馏线的 deploy 一上线就把探针线的过版项读进上下文，和读法纪律「读进来的每个字都留在上下文里挤占后面的判断、只读自己需要的那部分」直接顶。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-next-steps.md:144
   - 改法：rl decision stale 加 --mine 和 --handoff 两个过滤，角色上线默认只查本会话要接的那张单子相关的决定。

12. [slows/missing] 第 26 步：rl status --json 每行带哪些字段没写。命令表只有一句「所有子命令支持 --json 输出机器可读结果」，没写 status 的 json 行结构。gyb 想自己写脚本按线切，不知道 json 里有没有 decision_refs、batch、workdir 这些能认线的字段。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:147; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：在命令表第六节写死 status --json 的行结构，至少含 id、work_type、owner、holder、status、挂了多久、decision_refs、batch。

13. [slows/principle_violation] 第 2 到 10 步整段：违反原则 6（进出对称、等 gyb 的事一处汇总）。一处汇总做到了，进出对称没做到：账里能写进 batch，却没有任何一个查询能按线一次拿全这条线的三类单子加 issue 加口径加快车道；status 把两条线混排成一段，gyb 每条还要两跳才认线，「一处列出」在两条线并行时退化成「一处混排」。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：原则 6 补一句「一处列出的同时必须能按线切开」，并给 status 和各 list 命令加 --line。

14. [slows/principle_violation] 第 1 到 26 步整条路：违反原则 5（权限从动作倒推）的做法本身。五份角色 json 都从 use case 表倒推，而 gyb 明写「不在表里」，所以 gyb 自己的日常动作（早上分清两条线、逐条认线、批口径、把没人接的单子拉起来）从来没被倒推过一遍，status 和 list 的过滤维度是从五个角色的需求推出来的，不是从 gyb 的需求推出来的。这条路上 gyb 亲自动手二十次，其中十次是纯查询拼图。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:19; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：给 gyb 也写一张 use case 表（开工第一眼、批、验收、拉起、回收），从这张表倒推 status 和各 list 命令要哪些过滤维度和哪些输出栏。

### feedback-round（15 步，gyb 动手 9 次）

1. [blocks/principle_violation] 第 3、6 步（feedback 落账之后没人叫 gyb）：违反八条原则第 6 条「所有等 gyb 处理的事一处汇总」：feedback 的 proposed 版既不进 rl status 的七段，也不触发通知（通知只给 issue 改派到 gyb 那一版），gyb 唯一的兜底是七天一次的定时提醒 notify.reminder_days，一条规矩改动最坏挂七天
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:183
   - 改法：rl status 加第八段「等 gyb 裁的 feedback」，并让 rl feedback add 走 issue 那条通知通道发一次桌面通知

2. [blocks/principle_violation] 第 7 步（gyb 查 feedback）与第 13 步（deploy 想知道裁决结果）：违反第 6 条「进出对称」和第 5 条「权限从动作倒推」：deploy、run、analysis 三份角色 json 的 ledger_writes 都有 feedback add，reads 里都没有 feedback；命令表也只有 feedback list 没有 feedback show。提反馈的角色写得进去、查不出来，自己提的那条被采纳还是被否只能靠 gyb 口头说
   - 依据：plans/2026-08-16-research-loop-build-plan.md:103; plans/2026-08-16-research-loop-build-plan.md:105; plans/2026-08-16-research-loop-build-plan.md:107; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-next-steps.md:94
   - 改法：五份角色 json 的 reads 一律加 feedback，命令表补 `rl feedback show ID`

10. [cosmetic/ambiguous] 第 8、11 步（先改文件还是先 accept）：accept 那一版要求 applied_to 必填「改了母版哪个文件」，但没写是先把母版改完再 accept 还是先 accept 再去改，入账校验也没说要不要检查这个路径存在、检查改没改
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:139
   - 改法：命令表写死「accept 之前先把母版改完，rl 校验 applied_to 的每个路径存在」

12. [slows/too_heavy] 整条路（gyb 亲手做九件事）：改一条规矩要 gyb 亲自做九个动作（status、feedback list、改母版、改施工计划、grep 五份 skill、accept、判断要不要收会话、告诉 deploy、commit），系统只帮他记一行账，剩下八件全靠他自己记得住；这跟「想法要快速、多次迭代」的目标不匹配
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-build-plan.md:67
   - 改法：rl feedback accept 收多个 applied_to 并当场打印一张待办（还要改哪几处、活着的会话要不要收、要不要 commit 和跑测试）

13. [slows/principle_violation] 第 11 步的另一条走法（gyb 就坐在 deploy 会话里裁）：违反第 1 条「gyb 是超级用户，任何权限检查对 gyb 不生效」：角色会话里用 --as-gyb 缺 --quote 一律退出码 2（测试 9 钉死了这条），可 rl 分不出打字的是 gyb 本人还是模型，gyb 亲自在 deploy 会话里裁 feedback 会被自己的校验拦下来，得先换个裸终端
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:211; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-next-steps.md:34
   - 改法：给一个 gyb 本人当场打字的旗子（比如 --i-am-gyb）免 quote，或者把缺 quote 从拒收降成账行打一个「无原话」的标记

### idea-request-notes（15 步，gyb 动手 4 次）

2. [slows/contradiction] 第 5 步：命令表里 `rl grant add / rl grant list` 整行的「谁能调」只写 gyb，idea 调 grant list 应拿退出码 3；但 idea 的 reads 写的是「九本账全部」，公共规矩第 8 条又要求「读账一律经 rl 查询命令」。结果是 idea 查不到自己名下有没有 read:notes，每开一个新会话都只能重新走一遍申请，或者凭猜
   - 依据：plans/2026-08-16-research-loop-build-plan.md:138; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:252; plans/2026-08-16-research-loop-next-steps.md:52
   - 改法：第六节把 grants 拆成两行：`grant add` 谁能调写 gyb，`grant list/show` 谁能调写「谁都行」

3. [slows/contradiction] 第 9 步：设计文档一处写「idea 开一条 issue 给 gyb，gyb 写一条 grant」，另一处允许角色会话里的模型带 --quote 替 gyb 打 --as-gyb。本场景两句合起来的结果是：申请方和批准方是同一个会话里的同一个模型，quote 只是模型自己敲进去的字符串、rl 不校验，而 grant 的全部价值就是「给 reviewer 事后查的凭据」，自提自批之后这份凭据证明不了任何事
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:245
   - 改法：第六节 grants 那一行加一句「grants 不接受 --as-gyb，只收 session_id 为 cli 的裸终端写入」，gyb 批授权必须自己在裸终端打一次

4. [slows/ambiguous] 第 14 步：决定落哪本账的判据是「由 gyb 亲自打 --as-gyb 写的落 decisions.gyb.jsonl，idea 替 gyb 记的落 decisions.idea.jsonl 并带 quote」。但在角色会话里 gyb 从不打命令、只说话，命令全是模型打的，「亲自打 --as-gyb」这件事在角色会话里不存在。模型代打的 --as-gyb 算不算亲自，两种读法都说得通，同一条 gyb 定的决定可能落进两本不同的账
   - 依据：plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:57
   - 改法：第三节写死一条：decisions.gyb.jsonl 只收 session_id 为 cli 的行，角色会话里替 gyb 记的一律落角色自己那本并带 quote

8. [slows/missing] 第 12 步：读权不上钩子、靠纪律加 reviewer 事后查，但文档没写 reviewer 拿什么查「idea 有没有在没 grant 的时候就读了 notes/」。系统里没有读日志，doctor 的八项扫描里也没有这一类，这条纪律实际上无从核对
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:136; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl doctor` 加一项扫描「decisions 里 source 指向 notes/ 但 grants 里查不到该 actor 的 read:notes」，把这条纪律接回入账校验那一层

10. [cosmetic/missing] 第 10 步和第 11 步：issues 三个状态的写权只有一句「按第五节 ledger_writes」，谁写 reply、谁写 close 没规定；idea 的 ledger_writes 含 issues 的 open/reply/reassign/close 四个，所以 idea 自己开、自己答、自己关全过校验，和派活单那张写得很死的转移表不对称
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:79
   - 改法：第六节 issue 那一行加前提栏：reply 只有 assignee 或 gyb 能写，close 只有开单的 actor 或 gyb 能写

### periodic-reclaim（27 步，gyb 动手 11 次）

1. [blocks/missing] 第 6、7 步：reclaim 只有 --older-than 和 --apply 两个开关，没有逐条挑选或排除的办法。一个跑三天的 run 会话中间不写账，48 小时的会话阈值必然把它算成很久没动，gyb 想留下它只能整体调大 --older-than，代价是其他该收的也收不了。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:178
   - 改法：reclaim 加 --only ID... 和 --skip ID...，并且默认跳过 launch_order 对应进程还活着的会话。

2. [blocks/missing] 第 8、11、22 步：reclaim 把 launch_order 从 in_progress 改成 todo 之后，GPU 进程照跑、显存不释放、宿主 ops/jobs.json 的号不销。看门狗每轮采样只查本单是不是 withdrawn，改成 todo 它不认，不会走中断流程；owner 这时再起一个 run 接同一张单，同一份实验会被发射两次。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:70; plans/2026-08-16-research-loop-build-plan.md:162; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:143
   - 改法：reclaim 对 launch_order 先走 gpu-run 的中断收尾（rl run finish --exit killed、释放显存、销号）再交回 todo，看门狗把 reclaim 和 withdrawn 一起当中断信号。

3. [slows/contradiction] 第 8、9 步：施工计划第六节写 reclaim 是「会话标 reclaim 销号，单子交回 todo、holder 清空」，同一节又写 session end 时扫到 holder 是本会话的单子就拒绝。按前一句的顺序做，reclaim 的第一步就被自己的入账校验拒收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：把 reclaim 那一格改写成「先把名下单子交回 todo、holder 清空，再销号」，两步放同一把锁里。

6. [slows/missing] 第 11、27 步：reclaim 列出的单子里，done_pending_review 和 todo 这两类在转移表里没有 reclaim 能写的行，--apply 之后原样不动，文档也没说这两类被列出来之后 gyb 该干什么。挂了 100 小时没人验收的单子就这么继续挂着。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:88
   - 改法：reclaim 的输出把这两类单独分一段，明写不自动动，每条附一条现成的 accept / reject / withdraw 命令。

7. [slows/too_heavy] 第 12、15 步：回收之后没有任何东西通知 owner，也没有 owner 的收件箱（rl status 是 gyb 的）。owner 是角色不是会话，原来的会话已经被销号，gyb 得亲手为每个 owner 角色开一个终端加载 skill，单子分属几个 owner 就开几个。文档开头写这套东西服务的是想法要快速多次迭代，这一步和它拧着。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:154; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：reclaim --apply 结束时按 owner 分组打印每张单子和一条现成的加载命令，rl status 里加「按角色分的待接单」一段。

8. [slows/ambiguous] 第 15 步：rl handoff list 的 --mine 没定义是按 owner 过滤还是按 holder 过滤。owner 找回被回收的单子正是要按 owner 过滤，按 holder 过滤会一条都查不到。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-build-plan.md:41
   - 改法：拆成 --owner 和 --holder 两个开关，--mine 删掉。

11. [slows/missing] 第 3、24 步：一条一周没动的快车道 worktree 没有出路。reclaim 只管会话和单子，scratch 账只有 add 和 list，设计文档写死出快车道只有合回主分支补工单这一条路，放弃一条快车道没有命令，rl status 里那一行永远挂着，越攒越多。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:141
   - 改法：加 rl scratch retire --tag QL --reason，rl status 只列没 retire 的快车道，reclaim 把超期的快车道也列进来。

12. [slows/principle_violation] 第 23 步：违反原则 1。runs 账的行格式写死「actor 必须是 run」，而原则 1 说任何权限检查对 gyb 一律不生效。gyb 要给回收下来的孤儿发射版补一条 exit=killed 的收尾版，按前一句写不进去，按原则 1 写进去就破了 schema，入账脚本按哪一条实现没有定论。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：runs 账的 actor 改成允许 run 或 gyb，字段表那一句后面补「gyb 例外，同原则 1」。

13. [slows/missing] 第 26 步：doctor 的八个扫描项里没有 reclaim 会造出来的两种脏账：单子已经回到 todo 而关联 issue 还是 open，以及 runs 有发射版长期没有收尾版。这两种正是回收留下的残渣，扫不出来就没人修。文档也没写 reclaim 之后要不要跑 doctor。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:20
   - 改法：doctor 加这两项扫描，reclaim --apply 结束时自动跑一遍 doctor 并打印结果。

15. [slows/missing] 第 1 步：定时提醒的失败备案是「入口 skill 加载时打印一行距上次 reclaim 几天」，可入口 skill 只许 gyb 手动调用，gyb 不主动加载就永远看不到这一行。备案落空的时候没有第二条路。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:195; plans/2026-08-16-research-loop-next-steps.md:163; plans/2026-08-16-research-loop-next-steps.md:154
   - 改法：备案改成 rl status 的第一行打印距上次 reclaim 的天数，rl status 谁都能调、gyb 天天用。

### hook-missed-session-end（23 步，gyb 动手 11 次）

1. [slows/too_heavy] 步 2、步 5：文档指名「钩子漏掉的」走 rl reclaim（设计 L126），但 reclaim 的默认阈值是会话 48 小时、单子 72 小时（施工 L178、L179），提醒周期 7 天（施工 L183）。会话死掉 6 小时的时候，文档给的唯一恢复路一条都不触发，这张工单最坏要躺 7 天才有人碰，和设计 L7「想法要快速、多次迭代」打架。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:178; plans/2026-08-16-research-loop-build-plan.md:183
   - 改法：rl status 加一段「holder 会话超过 N 分钟没写任何账的 in_progress 单」，N 默认 30 分钟，和 reclaim 的 48/72 小时分开。

3. [slows/missing] 步 2：rl status 的「活着的会话」（施工 L142）只能按 sessions 账有没有结束版判定，钩子漏销号的死会话被列成活着。sessions 行（施工 L71）没有 last_activity 之类的字段，reclaim 的口径「会话超过 48 小时没写任何账」（施工 L178）要跨九本账扫 session_id，怎么算没写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:178
   - 改法：sessions 账加 last_activity 字段，rl 每次写任何账顺带刷新，status 和 reclaim 都读它。

4. [slows/principle_violation] 步 3：违反原则 6（设计 L20、L94「能 add 就有 show 和 list」）。命令表（施工 L126）里 sessions 只有 start 和 end，九本账里唯独它没有 show 和 list。gyb 从 rl status 拿到 holder 的 session_id，查不出它是哪个角色、什么时候开的、最后一次写账是什么时候。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:94; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：命令表补 rl session show ID 和 rl session list [--alive] [--role R]，谁都能调。

5. [slows/missing] 步 7：设计 L32 和 L126 两处写「gyb 也可以手动结束会话」，但命令表里 rl session end [--reason]（施工 L126）没有指定会话的参数，只能结束当前会话。gyb 结不掉那个已经死掉的 sess-deploy-3，只能等 reclaim 到 48 小时。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:32; plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：rl session end 加 --session ID，「谁能调」那一栏保持钩子和 gyb。

7. [slows/ambiguous] 步 5、步 6：把单子从 in_progress 拉回 todo 有三个写入者（施工 L93：销号钩子、reclaim、owner 的 release），设计 L126 又单独指名钩子漏掉的走 reclaim，文档没说这一情形该走哪条，两种读法都说得通。rl reclaim [--older-than H]（施工 L143）只有一个 H，第八节却有会话和单子两个阈值（施工 L178、L179），H 盖哪个也没写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-next-steps.md:126
   - 改法：设计 L126 改成「钩子漏掉的：owner 或 gyb 当场 release，超阈值没人管的由 reclaim 兜底」，--older-than 拆成 --session-older-than 和 --handoff-older-than。

10. [slows/missing] 步 23：rl doctor 的八项扫描（施工 L144）没有一项覆盖本场景：既没有「sessions 账里没有结束版但超过阈值没写账的会话」，也没有「in_progress 单子的 holder 不在活着的会话里」。恢复完 doctor 报零，钩子漏销号永远不进 doctor 的视野。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：doctor 加这两项扫描，修法分别给 rl handoff release 和 rl session end --session ID。

11. [slows/missing] 步 4：rl handoff list 的过滤器（施工 L136）只有 --status、--mine、--batch、--decision，没有按 holder 会话过滤的口子。死掉的 deploy 名下除了这张工单，还可能有它当 owner 开出去的发射单，gyb 只能全量列 in_progress 肉眼比对。--mine 在 actor 是 gyb 的时候指什么也没定义。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-build-plan.md:41
   - 改法：handoff list 加 --holder SESSION 和 --owner ROLE，并写明 actor 是 gyb 时 --mine 等于全部。

12. [slows/missing] 步 8、步 10：单子回到 todo 之后由 owner 重新拉起（设计 L17、施工 L93 第五栏），但 owner 是角色不是常驻进程。没有活着的 idea 会话的时候，这张 todo 单子只能等 gyb 下次看 rl status 才有人碰；谁在什么时候把 owner 叫起来，文档没写。本场景里重派全靠 gyb 口头说一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：rl status 的单子那段单列一行「todo 且 owner 角色当前没有活着的会话」的单子，并进桌面通知。

### smoke-fails（44 步，gyb 动手 4 次）

3. [slows/missing] 步 27（deploy 回完 issue 把发射单拉回 todo）：转移表 stuck→todo 那一行的「谁能写」是「回了 issue 的那个角色」，可是 bin/rl 命令表里 handoff 的子命令只有 start/stuck/done/accept/reject/withdraw/release，没有一条对应这次转移；release 在转移表另一行里写的是 owner 专用。这次 deploy 恰好既是回 issue 的人又是 owner，用 release 蒙混过去了，换成 gyb 之外的非 owner 角色回 issue 就没有命令可打。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：加一条 rl handoff resume ID（前提是关联 issue 已 answered），并在转移表每一行后面补上对应的子命令名。

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

### doctor-findings-fix（24 步，gyb 动手 15 次）

1. [slows/missing] 第 2 步（doctor 输出修法）：doctor 那一行承诺「每类结果附一条修法（都是追加一版的 rl 命令）」，但八个扫描项没有任何一项写出具体的修法命令是什么；本场景三类问题的修法全靠我按转移表和命令表倒推，三类里有两类倒推出来的路子不止一条。
   - 依据：2026-08-16-research-loop-build-plan.md:144
   - 改法：在第六节 doctor 那一行下面补一张八行表，每个扫描项写死修法命令模板、谁能打、修完之后单子归谁推。

2. [blocks/blocked] 第 21、22、23 步（修第三类）：「runs 行没有对应发射单」这一类没有可用的修法：runs 的写命令只有 add 和 finish，第三节只定义了 version 1 发射版和 version 2 收尾版，没有第三版；handoff 编号自动分配，补开一张 launch_order 也补不进已有 runs 行的 handoff_id（账只增不改）。gyb 按文档走到这里做不下去，doctor 每次都会继续报这一条。
   - 依据：2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:133; 2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-next-steps.md:92
   - 改法：加一条 `rl run relink RUN_ID --handoff ID`，作为 runs 的第三版（只允许补 handoff_id），或者给 doctor 加一条 acknowledge 命令把确认过的孤儿行消音。

3. [blocks/contradiction] 第 23 步（gyb 能不能手写 runs 行）：设计文档说「第二层是入账校验，硬的……gyb 例外」，读起来 gyb 连必填字段和 actor 限制都免；施工计划说「actor 是 gyb 时跳过全部『谁能调』和转移表『谁能写』的检查」，读起来只免这两类。runs 那一行写着 actor 必须是 run，gyb 到底能不能补写一行 runs 直接取决于这两句谁算数。
   - 依据：2026-08-16-research-loop-next-steps.md:134; 2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:63
   - 改法：在施工计划第六节写死一句「gyb 只豁免谁能调与转移表谁能写，schema 必填与 actor 限制对 gyb 同样生效」，并把设计文档那句「gyb 例外」改成同一句话。

4. [slows/ambiguous] 第 3、4 步（判定第一类是什么）：「没人引用的 issue」没有定义什么叫被引用。按现有字段只有 handoff.issue_id 和 grant.issue_id 会指回 issue，而 handoff 的 issue_id 只在 stuck 那一版必填，于是 withdraw 自动开的 kind=withdrawn issue、run finish 开的 kind=anomaly issue、idea 的 kind=request issue 天生就没人引用，doctor 会把这些正常的行当问题报。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:59; 2026-08-16-research-loop-build-plan.md:92
   - 改法：把这一项收窄成「kind 是 cannot 或 denied、status 是 open、且没有任何 handoff 的 issue_id 指回来的 issue」，其余 kind 一律不扫。

5. [slows/blocked] 第 6 步（补 stuck 那一版）：`rl handoff stuck` 的前提是「那条 issue 的 handoff_id 指回本单」，但 `rl issue open` 的 `--handoff` 是可选参数；崩在写序中途的那条 issue 如果当初没带 --handoff，这条前提永远满足不了，而 issues 的命令只有 reassign/reply/close，没有补 handoff_id 的路，第一类同样修不了。
   - 依据：2026-08-16-research-loop-build-plan.md:84; 2026-08-16-research-loop-build-plan.md:132; 2026-08-16-research-loop-build-plan.md:59
   - 改法：要么把 `--handoff` 在 kind 是 cannot/denied/withdrawn 时改成必填，要么加一条 `rl issue link ID --handoff ID`（追加一版只补这个字段）。

6. [slows/too_heavy] 第 9 到 19 步（修第二类）：第二类的真实病因只是一份报告文件没了，修它却要走「打回 → 加载 deploy 会话 → decision stale → start → 重写报告 → done → accept」七步，中间还要新登记一个会话、还要把单子在四个状态之间转一圈。对着「想法要快速、多次迭代」这条目标偏重。
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:91; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:88
   - 改法：给 done_pending_review 的单子加一条 `rl handoff amend ID --report-detail P`：追加一版只换路径、不改状态、校验路径存在。

7. [slows/missing] 第 8、18 步（holder 指向死会话）：转移表和测试 2 列的 holder 清空时机是 start 写、stuck→todo / rejected / release / reclaim 清，唯独 in_progress→done_pending_review 不清；销号钩子又只检查 holder 名下还在 in_progress 的单子。于是等验收的单子上 holder 长期写着一个已经销号的会话，rl status 那一栏显示有人在干，实际没有。
   - 依据：2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:204; 2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-next-steps.md:124
   - 改法：在转移表 in_progress→done_pending_review 那一行补一句 holder 清空，或者 rl status 显示 holder 时标出这个会话还活着没有。

8. [slows/ambiguous] 第 19 步（谁来 accept）：gyb 本人坐在 deploy 会话里想验收，按文档要打 `--as-gyb` 并且必须带 `--quote gyb 原话`，缺 quote 退出码 2；可是 rl 只看会话状态文件，分不出这条命令是 gyb 本人敲的还是模型敲的，于是 gyb 本人也得引用自己刚说的一句话。我只能让 gyb 退回裸终端打，多切一次终端。
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-next-steps.md:34
   - 改法：`--as-gyb` 缺 quote 时改成交互式追问一次再放行，或者加一个 `--quote-self` 表示 gyb 本人当场敲的。

9. [slows/principle_violation] 第 1、24 步（doctor 的结果没有落点）：违反原则 6「所有等 gyb 处理的事由 rl status 一处列出」：doctor 扫出来的问题不在 rl status 的七段里，也不在 7 天定时提醒的三件事（reclaim、看 feedback、迭代框架）里，没人叫 gyb 跑 doctor，修不了的那条（第三类）也没有任何地方替他记着。
   - 依据：2026-08-16-research-loop-next-steps.md:20; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-build-plan.md:183; 2026-08-16-research-loop-build-plan.md:144
   - 改法：rl status 加第八段「上次 doctor 扫出还没修的问题」，并把跑 doctor 并进 7 天提醒那三件事里。

10. [slows/missing] 第 7 步（第一类修到哪算完）：文档没写 doctor 修到哪算完。补上 stuck 那一版之后账面一致了，但那张发射单实际还卡着、那条 issue 还等 deploy 回、真正的实验失败没人处理；doctor 的输出也不区分「账面对不上」和「活还没干完」。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:85
   - 改法：doctor 每条修法后面固定加一句「修完之后这张单子归谁推」，取值和转移表第五栏一致。

11. [slows/guessed] 第 21 步（第三类到底指什么）：「runs 行没有对应发射单」有两种读法：handoff_id 为空，还是 handoff_id 指向的单子不存在或者 work_type 不是 launch_order。命令表里 `rl run add --handoff ID` 看着是必给的，第一种读法在文档里产生不出来，我只能猜是第二种，而文档也没写这条脏数据是怎么进来的。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-build-plan.md:63
   - 改法：把这一项改写成「runs.handoff_id 为空、悬空、或者指向的单子 work_type 不是 launch_order」，并在旁边注一句它怎么产生。

12. [cosmetic/missing] 第 5、9 步（修账那两版留不留痕）：gyb 在裸终端补的 stuck 和 reject 这两版，账上只留 status 和 reason，没有任何字段标明这是 doctor 修账修出来的。reviewer 事后翻 handoffs，分不出这张单子是真卡住过、还是只是把断掉的引用补回去。
   - 依据：2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:55; 2026-08-16-research-loop-next-steps.md:88
   - 改法：公共骨架加一个可选的 `fix_for` 字段，doctor 给的修法命令一律带上扫描项名字。

13. [cosmetic/missing] 第 1 步（谁跑 doctor、跑完能不能自己修）：doctor 写的是「谁都行」，但角色会话跑出问题之后能不能自己修没写。deploy 看到自己名下那张 done_pending_review 的报告路径没了，它是 to_role 不是 owner，按转移表打回只有 owner 能写，它只能开 issue，文档没说这一步该开给谁、kind 填哪个。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:45
   - 改法：在 doctor 那一行写一句「角色跑 doctor 只看不修，修法一律 `rl issue open --to <owner> --kind cannot` 报给 owner 或 gyb」。

## 裁决记录（日期）

- 2026-08-17 来自 03（rl-hub 转，gyb 原话「我感觉很轻松能从data_path 找出artifact_path啊，而且artifact path定义有点暧昧 能不能不要了」「选A吧那就」）：`rl run add` 签名去掉 `--artifact-dir`，产物目录按约定 `<artifact_root>/<run_id>/`、账上不记；`rl run finish --data-path P` 不动。对回原则 8、9。
- 2026-08-17 来自 03（rl-hub 转，gyb 原话「你说得对」）：actor 是角色的命令带 `--force` 一律拒收，退出码 3，附「开 issue 给 gyb」的命令；角色会话里 `--as-gyb --quote --force --reason` 算 gyb 身份写，照写。退出码表第 3 行加「含角色带 `--force`」。对回原则 1、2。
- 2026-08-17：来自 `04-handoffs-and-sessions.md` 的裁决（rl-hub 转来；gyb 原话「不杀」）：reclaim 回收开干的发射单默认不杀进程，`--kill` 才杀。对回原则 11。第 170 行不一致标注照改。
- 2026-08-17：来自 sync-inbox 问题 1（rl-hub 转来；gyb 原话「这个归01吧」）：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 这一组规矩定义处归 `01-gyb.md` 第二节，05「actor 怎么定」是命令行写法、两边同步；照抄了 01 新补的「角色带 `--force` 拒收退出码 3、`--as-gyb --quote --force --reason` 算 gyb 身份」那句。对回原则 1、8。

- 2026-08-17（gyb 原话「可以」，doctor 第 1 项）：编号重复只报不修，列撞号行的 `ts`、`actor`、`session_id`，归 gyb。对回原则 4。
- 2026-08-17（gyb 原话「都同意」，doctor 第 2 到 6 项）：第 2 项 handoffs 行 `amend` 换引用、其他账只报，归那一行的 owner；第 3 项 `issue link`（没 issue 先 open），归转 stuck 的角色；第 4 项 `handoff stuck` 或 `issue close`，归开 issue 的角色；第 5 项 `handoff amend` 改路径，归交活的角色；第 6 项 `run relink` 或 `--ack`，归 run。对回原则 6。
- 2026-08-17（gyb 原话「doctor不太关键，先全都按照你推荐的来吧，很费劲的就不用了，我想的是脚本检查和subagent检查结合，比如说写好问题，然后让很多sonnetsubagent去逐个检查」，doctor 第 7 到 18 项）：修法与归谁推按本份表里写的；doctor 只留脚本能判的项。对回原则 2、6。
- 2026-08-17（gyb 原话「A」）：判断类检查不进 doctor，问题清单放 `common/`，reviewer 派 sonnet subagent 一人一题逐条查，查出的 `rl issue open --to <owner>` 落账。对回原则 2、5。（2026-08-17 问题 6 后改：只写清单不开 issue）
- 2026-08-17（gyb 原话「全推荐」，没写清第 2 到 6 条）：加 doctor 第 19 项 `sessions.model=unknown`，修法新子命令 `rl session amend ID --model M`；`rl decision stale` 签名改 `[--handoff ID] [--all]`；`rl handoff done` 去掉 `--actual-seconds`，耗时只由 `rl run finish` 算；`session end` 顺带 release 的 actor 记会话角色、加可选栏 `via=session_end`，reclaim 做的 `via=reclaim` actor gyb；`rl notify` gyb 也可手动调、不进账。对回原则 1、4、6、8、10。
- 2026-08-17（gyb 原话「只要他不动目前的代码什么的就全推荐就行」，没写清第 7 到 11 条）：推送表第 4 条在单子落 todo 那刻和 session end 销号时查并推；独立进程只许查询、不留痕；`--force` 越不过表外转移；锁超时 `lock.timeout_seconds` 默认 10 秒；`inbox`/`doctor`/`reclaim` 三条 `--json` 最小结构按正文。对回原则 1、4、6、8、11。
- 2026-08-17（gyb 原话「全都推荐，只要不影响正在跑的进程」，没写清第 12、13 条与 inbox 不一致）：`--ack` 写 `loop/.doctor-acks.jsonl` 永久消音、`--list-acks`、`--unack`；`rl init` 读到会话状态文件拒收退出码 3；`rl inbox` 第 3 项取施工计划，只列 holder 是本会话的单子。对回原则 1、4、6、8。
- 2026-08-17：来自 sync-inbox 问题 2（rl-hub 转来；gyb 原话「算一件事」「给rl notify指到01吧」）：推送表和 `rl notify` 是一件事，定义处归 `01-gyb.md` 第五节；05「rl notify」一节缩成一句指过去，推送表和机制那段删掉（05 独有的两句已列在同步第 1 条给 01）。对回原则 8。
- 2026-08-17：来自 sync-inbox 问题 3（rl-hub 转来；gyb 原话「按照08吧」）：阈值表定义处是 `08-trees-init-and-host.md` 第三节，05 里三处「施工计划第八节」和退出码 4 那句改成指 08 第三节。对回原则 8。
- 2026-08-17 三份互查，rl-hub 转来（对齐 03/04 定义处，不是新裁决）：`release` 的 `--note` 只在 `in_progress`→`todo` 必给；`amend` 加 `--notebook --figure`；`open` 谁能调补快车道补单 deploy 调 owner 记 gyb；`session end` 全部 release、细则指 04 第七节、`rules_version` rl 从母版读；`grant add` 加 `--text`；`feedback accept --text` 必给；`eval` 退役也是 gyb；`scratch list/show` 和 `inbox` 查谁都行；`last_activity` 现算写法与 03 第 186 行一字不差；`accept` 顺带关 `answered` issue；`run list --decision/--line` 反查、`started_at/finished_at` rl 填；锁与写序、退出码表标定义处 03，reclaim 处置标定义处 04；接口一节三处「要收」改「已收」、十条改十二条。
- 2026-08-17（rl-part-05 定，待 gyb 过目；已过目）：`holder_alive` 是 holder 会话在 sessions 账最新版是不是 `open`；`age_hours` 从当前状态那一版 `ts` 起算；「run 的 inbox 不查过版」例外删掉，run 的 inbox 第 3 项照查。（前两句问题 29 gyb 认；第三句被问题 28 推翻，run 不查 inbox）

- 2026-08-17 来自 sync-inbox 问题 6（rl-hub-v2 转来；gyb 原话「全给我审查，然后我用我的权限放到issue里面」）：reviewer 查出的只写 review/ 清单，不开 issue，gyb 看完用自己的权限开。对回原则 2。
- 2026-08-17 来自 sync-inbox 问题 7（rl-hub-v2 转来；gyb 原话「冒烟也是正式动作」）：`estimate` 在 04 转移表有行（`in_progress`→`in_progress`，holder 写），接口一节注明。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 8（rl-hub-v2 转来；gyb 原话「A」）：快车道合回先开补单再关杂账，`--ql QL` 存进单子 `ql_tag` 栏，补单前提关联 scratch 行 open；`ql close --merged --handoff ID` 前提 ID 是 quick_lane 补单且 `ql_tag` 等于 QL。对回原则 7。
- 2026-08-17 来自 sync-inbox 问题 9（rl-hub-v2 转来；gyb 原话「A」）：`--batch` 是调用者自由文本、可选，rl 不分配；锁那句里的 `batch` 去掉。对回原则 9。
- 2026-08-17 来自 sync-inbox 问题 10（rl-hub-v2 转来；gyb 原话「A」）：`amend` 加 `[--decision ID@V ...]`，`done_pending_review` 上也可改 `--code-path`。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 11（rl-hub-v2 转来；gyb 原话「B」）：issue 不加追问；doctor 第 11 项修法改成 close 再另开新 issue、正文引旧编号。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 12（rl-hub-v2 转来；gyb 原话「B」）：runs 默认列表是最新一次尝试且 ok，05 已是，不改。对回原则 10。
- 2026-08-17 来自 sync-inbox 问题 14（rl-hub-v2 转来；gyb 原话「A」）：被销号会话再写账退出码 3，`--as-gyb --force` 也越不过。对回原则 1。
- 2026-08-17 来自 sync-inbox 问题 15（rl-hub-v2 转来；gyb 原话「B」）：`fix_for` 栏删掉，可选栏剩 `force_reason`、`via`。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 16（rl-hub-v2 转来；gyb 原话「A」）：analysis 快车道没有补单，`ql close --merged` 只有 deploy，`--dropped` deploy、analysis 都行。对回原则 7。
- 2026-08-17 来自 sync-inbox 问题 17（rl-hub-v2 转来；gyb 原话「C」）：认领两边都标，handoffs `start` 版 `adopted: true`，runs 加一版 `adopted`（记新 holder 的 `session_id`、`ts`），由 `rl handoff start` 顺带写、不另设 `rl run adopt`（rl-part-05 定）。对回原则 11。
- 2026-08-17 来自 sync-inbox 问题 19（rl-hub-v2 转来；gyb 原话「B」）：reclaim 处置加第五类，被打回的单子超过 `reclaim.handoff_idle_hours` 没动的推回 `todo`，`actor` gyb、`via=reclaim`，owner 重新拉起，与 04 第八节一字不差。对回原则 3。
- 2026-08-17 来自 sync-inbox 问题 18（rl-hub-v2 转来；gyb 原话「A」）：`rl session amend` 只换 model，status 与其他栏照抄最新版，closed 也能 amend。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 23（rl-hub-v2 转来；gyb 原话「只有做完了的时候才关，巡检要我本人确认」）：`rl inbox` 只读不关；通知类 issue 收件人做完了自己 close；`doctor --ack/--unack` 是写命令、只有 gyb。对回原则 2、6。
- 2026-08-17 来自 sync-inbox 问题 24（rl-hub-v2 转来；gyb 原话「B」）：`loop/.doctor-acks.jsonl` 是普通文件，03 账本总规矩不管它。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 25（rl-hub-v2 转来；gyb 原话「我想让agent有办法识别发生了什么就行」）：退出码加 1 内部错、5 用法错，共六个；非零退出标准错误第一行固定原因种类（`validation`、`forbidden`、`lock_timeout`、`usage`、`internal`），`--json` 放 `error.kind`。种类词是统筹拟的措辞。对回原则 6。
- 2026-08-17 来自 sync-inbox 问题 26（rl-hub-v2 转来；gyb 原话「我觉得。有一些改的方法，不一定会改公共规矩，如果是这样的话就选b。」）：doctor 第 17 项改成「applied_to 为空」。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 27（rl-hub-v2 转来；gyb 原话「3 不是，可以替我写」）：（b）（c）认；（d）不认，grants 角色会话里 `--as-gyb --quote` 替 gyb 写也收，`decisions.gyb.jsonl` 只收裸终端不变。对回原则 1。
- 2026-08-17 来自 sync-inbox 问题 28（rl-hub-v2 转来；gyb 原话「顺便run只需要关注自己的工单，一般不会空run，不需要查，这个改了」「每个角色创建时候，不要自动查收件箱」「C」）：run 不查 inbox；角色被拉起不自动查 inbox，谁需要谁敲；「上线第一个动作是 rl inbox」删。对回原则 6。
- 2026-08-17 来自 sync-inbox 问题 29（rl-hub-v2 转来；gyb 原话「A」）：`holder_alive`、`age_hours` 算法认，去掉「待 gyb 过目」。对回原则 6。

## 要同步到别处的

（九条已同步 2026-08-17：rl-hub 改的见 commit cb5e1e2；04 由 rl-part-04 改，见 42b6594；30 未写成，记在 README 30 那行。第 8 条 reviewer 派 subagent 并 `rl issue open` 落账，rl-hub 指出和 14 第八节「不开 issue、不派活」、公共规矩第 6 条冲突，立为 sync-inbox 问题 6 等 gyb 裁，裁下来若动 05 再改。）

- `01-gyb.md` 第二节（定义处）：补「`--force` 只越过完整性前提，越不过转移表外的转移，表外转移对 gyb 同样退出码 2，硬改状态走 `withdraw` 再重开」；推送表第 4 条补「在单子落 todo 那刻和 `session end` 销号时查并推」；`rl notify` 补「gyb 也可手动调，不进账」。
- `02-decisions.md`：`rl decision stale` 签名改成 `[--handoff ID] [--all]`，去掉 `--mine`。
- `03-ledgers.md`：公共骨架可选栏加 `via`（值 `session_end`、`reclaim`）；sessions 账加 `amend` 版，只许改 `model`；handoffs 的 `actual_seconds` 只从 runs 的 `finish` 版来，`done` 不填。
- `04-handoffs-and-sessions.md`：`rl handoff done` 签名去掉 `--actual-seconds`；转移表 `in_progress`→`todo` 由销号钩子写的那一行 actor 记会话角色、`via=session_end`，由 reclaim 写的 actor 记 gyb、`via=reclaim`；`--force` 越不过表外转移。
- `08-trees-init-and-host.md`：阈值表加 `lock.timeout_seconds` 默认 10 秒；`rl init` 读到会话状态文件拒收退出码 3、只在裸终端跑；`loop/.doctor-acks.jsonl` 由 doctor 首次 ack 时建，`rl init` 不建。
- `09-common-and-feedback.md`：`common/` 加一份判断类检查的问题清单文件（名字归 09 定）。
- `12-role-run.md`：看门狗只许调查询命令、不留痕，判定由 run 会话转写进账；发射单不再记 `--artifact-dir`（来自 03，核一遍）。
- `14-role-reviewer.md`：reviewer 加一项职责，按 `common/` 的问题清单派 sonnet subagent 一人一题逐条查，查出的 `rl issue open --to <owner>` 落账。（2026-08-17 问题 6 后改：只写清单不开 issue）
- `30-build-steps-verify-tests.md`：待验证第 4 条备案「`rl init` 检查调用者不是任何角色」升正案；第 10 条备案里「doctor 列 `model=unknown`」已收成 doctor 第 19 项；测试里 `rl session amend`、`rl doctor --ack/--unack/--list-acks`、`lock.timeout_seconds` 要有测法。
