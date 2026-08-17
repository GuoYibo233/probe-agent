# 待验证清单、测试清单、施工步骤

> 这份覆盖三张表：待验证十一条（每条的测法、通过标准、失败备案，加上 2026-08-17 已经裁掉的两条）、测试十七条（施工计划第十节原文，逐条附上 2026-08-17 各 part 定稿之后要加或者要改的用例，另加 `05` 定稿点名要有测法的三条）、施工步骤 0 到 8（每步交付物、验收、依赖、执行者与模型，加施工纪律四条和 commit 前缀）。
> 这份不覆盖：每条测试用例背后的规矩本身，规矩的定义处在各自的 part 里（转移表在 `04-handoffs-and-sessions.md`，九本账行格式在 `03-ledgers.md`，命令表和退出码在 `05-rl-cli.md`，钩子在 `06-hooks-and-permissions.md`，快车道在 `07-quick-lane.md`，母版和 feedback 在 `09-common-and-feedback.md`，两棵树和 init 在 `08-trees-init-and-host.md`）；待验证第 5、8、9、10 条不成立会改掉哪些正文，写在 `04` 和 `12` 的接口一节，这份只写测法。
> 源：施工计划第九节（待验证清单）、第十节（测试清单）、第十一节（施工步骤）、第十二节（留给 gyb 的）；设计文档「待验证清单」「施工步骤」两节；`05-rl-cli.md` 定稿（`656c8a9`）留给本份的三条（sync-inbox 第五段第 9 项）；`03`、`04`、`05`、`07`、`08` 各份 2026-08-17 的裁决记录里改动了测试用例的那几条。

## 一、待验证清单十一条

施工第 0 步就测，每条写测法、通过标准、失败备案。设计文档「待验证清单」那一节只列题目，清单本体在施工计划第九节，下表照抄第九节，最后一栏是 2026-08-17 之后的状态。gyb 裁定：讨论全部收口之前一律不测。

| # | 要验证的 | 测法 | 通过标准 | 失败备案 | 2026-08-17 之后的状态 |
|---|---|---|---|---|---|
| 1 | Bash 环境里有没有现成的会话 id 变量 | 在会话里 `env \| grep -i session`，再对比钩子输入的 `session_id` | 同一个值 | SessionStart 钩子写状态文件，rl 按 `cwd` 加最近一次登记找 | 待测 |
| 2 | skill 头部声明的钩子能不能给命令带参数 | 写一个测试 skill，头部钩子命令 `hook.sh --role test`，加载后触发看参数到没到 | 脚本收到 `--role test` | 五个角色各一份钩子脚本，内容相同只差常量 | 待测；`08` 第四节写的是「五个角色共用一个脚本、参数报角色名」，就是主案 |
| 3 | monitor 的 `when: "on-skill-invoke:run"` 写法 | 写一个只打印一行的 monitor，加载 run skill 看起不起 | 加载后进程在、不加载不在 | monitor 常驻，脚本自己读会话状态文件判断当前角色是不是 run | 待测 |
| 4 | skill 头部禁止模型调用的声明能不能锁入口 skill | 加声明后让模型自己调一次 | 调不动 | 入口 skill 的 SKILL.md 第一行写「模型调用即违规」靠纪律，另外 rl init 检查调用者状态文件不是任何角色 | 备案已升正案（2026-08-17 随 `05` 定稿裁）：`rl init` 读到会话状态文件就拒收，退出码 3，只在裸终端跑（`08` 第一节、`05` 命令表）。这一条照测，测的结论只决定 skill 头部要不要再加那句声明，不改正文 |
| 5 | SessionEnd 和 SubagentStop 在 subagent 结束时触发不触发、会话 id 是不是同一个 | 起一个加载角色的 subagent，让它写一行账，结束后查 sessions 账 | 有 `ended_at`、`session_id` 和 `started_at` 那行相同 | 全靠 `rl status` 段 7 加 `rl reclaim`，提醒周期从 7 天缩到 1 天 | 待测；不成立会改 `04` 第六、七节和 `12` 的走法 |
| 6 | 桌面通知机制 | 试 Claude Code 自带推送、`notify-send`、终端铃三种 | gyb 桌面看得到 | 退到 `rl status` 单列那一层，通知不做 | 待测；推送表在 `01` 第五节 |
| 7 | 定时提醒机制 | 试 Claude Code 的 schedule 和系统 cron | 到点 gyb 收得到 | `rl status` 第一行打印距上次 reclaim 几天（已是正案的一部分），提醒不做 | 待测 |
| 8 | subagent 里加载角色 skill，头部钩子装不装得上、写权拦不拦 | 起 subagent 加载 deploy，让它写 `analysis/x.md` | 被 deny | subagent 路线改成 workflow 里的 `agentType` 指向 `agents/<role>.md`，钩子在 agent 定义里声明；再不行 subagent 接单只靠纪律加 reviewer 事后查。测完在设计文档 run 一节写死走哪一案，删掉另一案 | 待测；插件树要不要有 `workflows/` 或 `agents/` 一层挂在这条上（`08` 留给 gyb 第 10 条） |
| 9 | 后台 subagent（原则 11）：父会话活着时后台 subagent 能不能跑几个小时；父会话结束后台 subagent 会不会被杀 | 起 deploy 会话后台起一个 sleep 两小时的 run subagent，两种情况各试一次 | 活着时能跑完并回通知；父会话结束时的行为有结论 | 被杀的话正案不变（GPU 在 tmux、单子在账上、下一个 run 认领），只是待认领的单子多；同步等的老方案不再回来 | 待测 |
| 10 | 钩子输入里有没有模型标识 | 打印 SessionStart 钩子的输入 JSON | 有 model 字段 | sessions.model 记 `unknown`，doctor 列出来，gyb 事后补 | 备案已收成正案的一部分（2026-08-17 随 `05` 定稿裁）：doctor 第 19 项扫 `model` 是 `unknown` 的 sessions 行，修法 `rl session amend ID --model M`（`05`「rl doctor」、`04` 第七节）。这一条照测，测出有 model 字段就少走一次 amend，不改正文 |
| 11 | 改一行母版不重启 claude 再加载一次角色，读到的是不是新文本 | 改 common/ 一行，同一进程再 `/` 加载角色 | 模型看到新文本 | feedback accept 的待办里加一句「改完母版必须重开终端」 | 待测；`09` 第二节引了这一条 |

施工计划第九节末尾的一句照抄：原第 9 条「rl 读不到状态文件按 gyb 处理」gyb 2026-08-16 夜已裁：就是 gyb，不加参数。原第 9 条「上游同步等几个小时」按原则 11 改题成现在的第 9 条。

第 0 步的交付物是把十一条的实测结果写进 `plans/2026-08-1x-research-loop-verify.md`，每条写实测结果和选了主案还是备案；备案影响正文的当场改设计文档，删掉另一案。第 4 条和第 10 条的备案已经升成正案，第 0 步测完这两条只记结果，不用再改正文。

## 二、测试清单十七条，加 `05` 定稿点名的三条

测试放 `research-loop/tests/`，每一步施工结束 `tests/run_all.py` 全绿才 commit。下面每条先抄施工计划第十节的原文，再列 2026-08-17 各 part 定稿之后要加或者要改的用例，改动的每一条都写出来自哪份 part 的哪条裁决。原文没动的条目就只有原文。

### 测试 1：锁与撞号

原文：两个进程同时追加同一本账各 100 行，编号无重复、行数正确；ql_tag 和 run_id 同样不撞。

要改的：`batch` 不在锁里分，是调用者的自由文本（`05`「锁与写序」，2026-08-17 问题 9），撞号用例只测 ql_tag 和 run_id，不测 batch。

### 测试 2：转移表

原文：对每一行合法转移各一个用例，加三个非法转移用例（跨状态、错角色、缺前提），非法一律退出码 2 并且账里没有新行；`holder` 只在 `in_progress` 非空，进写、出清、`last_holder` 留下；start 时 holder 非空拒收；认领用例（最新尝试有 launched 未 finished 的 run 行时 start 标 adopted）。

要加的：

- holder 不变量按 `04` 第二节的写法测：离开 `in_progress` 的每一种转移（交活、卡住、打回、收回、交回、回收）都清空 holder 并记 `last_holder`，`done_pending_review` 上 holder 为空。第二轮 param-tweak 第 1 条、hook-missed-session-end 第 2 条报的就是原来测试 2 漏了 `done_pending_review` 这一处。
- `handoff estimate` 是转移表里 `in_progress` 到 `in_progress` 的一行，只改最新一次尝试的 `step_table` 和 `estimated_seconds`，谁能写是 holder 且角色是 run（`04` 第三节）。
- 表外转移对 gyb 同样退出码 2，带 `--force --reason` 也越不过（`05`「actor 怎么定」，2026-08-17 裁）。
- 认领那一版写 `adopted: true`，rl 同时给 runs 那条写一版 `adopted`，记新 holder 的 `session_id` 和 `ts`（`04` 第三节、`05` 命令表）。
- 快车道补单从（新建）直达 `done_pending_review`，前提是 `quick_lane` 为 true、`report_paths.method` 存在、`explanation` 非空、`ql_tag` 指的 scratch 行状态是 `open`（`04` 第三节，HANDOFF 问题 8 改的）。
- `reissue` 那一行：旧单 `withdrawn` 级联、新单 `todo`、`supersedes` 指旧单（`04` 第三节最后一行）。

### 测试 3：决定来源

原文：空列表拒收；三类来源各一个用例；`file` 类路径不存在拒收、带锚点通过；`run` 类 run_id 不在 runs 账拒收；update 不给 source 继承上一版；confirm 正文不变版本加一；merge 自动并入被合并编号并按 `--root` 记根；`decisions.gyb.jsonl` 拒收非 cli 行；update 时打印引旧版的活单。

要加的：`file` 类是仓库内任意路径，`review/` 里的清单和 `experiments/` 里的部署报告都算（`02`「来源三类与锚点」），用例里各放一个；`retire` 同样打印受影响的单子（`02` 子命令表）。

### 测试 4：交付物

原文：`work_order` 缺任一报告路径或 code_paths 拒收；快车道补单只要 method；`analysis_order` 缺 notebook 拒收、引 proposed 口径开单通过、交活时有 proposed 拒收；`launch_order` 没有最新尝试 `exit_status=ok` 的收尾版拒收；`quick_lane` 工单新建直达 `done_pending_review` 且只有 gyb 能 accept。

要改的：快车道补单的前提里 scratch 行状态是 `open` 不是 `merged`，顺序是先开补单拿编号、再 `rl ql close --merged --handoff ID` 关杂账（`04` 第三节、`07` 第七节，HANDOFF 问题 8）；补单必填 `ql_tag`，其余单子这一栏空（`04` handoffs 字段表）。要加的：`rl handoff done` 不带 `--actual-seconds`，`actual_seconds` 只从 runs 的 `finish` 版来（`03` 裁决记录 2026-08-17）。

### 测试 5：过版

原文：派活单引 v1、决定更新到 v2 之后 `rl decision stale` 列出来，`rl status` 也列，`rl inbox` 对相关角色列；口径引用同样查过版。

要改的：`rl inbox` 第 3 项只列 holder 是本会话的单子引的过版决定，owner 名下但不在本会话手上的过版单子归 `rl status` 段 6（`05`「rl inbox」，2026-08-17 裁）；`rl decision stale` 的签名是 `[--handoff ID] [--all]`，`--mine` 去掉了（`02`、`05`）。「口径引用同样查过版」由哪条命令出，`22` 留给 gyb 第 3 条还没裁，这一句先按原文留着，测法等裁了再定。

### 测试 6：跨账写序

原文：模拟 issue 写成功、handoff 写失败，`rl doctor` 报对应项并给 `issue link` 修法。

要加的：doctor 那一项现在是第 3 项「`stuck` 单子没有 issue」，修法是 `rl issue link ID --handoff ID`，「修完归谁推」是把单子转成 `stuck` 的角色（`05`「rl doctor」）。

### 测试 7：销号

原文：holder 名下有 `in_progress` 单子时 `rl session end` 自动 release、progress_note 非空、owner 收到 `orphaned`；`done_pending_review` 和 `stuck` 的单子不挡销号；`--session ID` 能关别的会话。

要加的：

- 名下有几张开干的就交回几张，一张不留，run 会话 `--batch` 接下的整批一起交回，交回的编号全部记进 sessions 账 `released_handoffs`（`04` 第六节，2026-08-17 裁）。
- `experiments/` 里的脏改动打 `wip/<ho-id>` 分支，分支名记进 `progress_note`（`04` 第六节）。
- `--session ID` 关别的会话时 rl 不查那个会话活没活着，`end_reason` 记 `manual`；被关的会话再来写账，rl 看到 sessions 最新版是 `closed` 就拒收，退出码 3，`--force`、`--as-gyb --force` 都越不过（`04` 第七节、`03`「账本的总规矩」）。
- 销号钩子写的 release 那一版 `actor` 记会话的角色、`via=session_end`；reclaim 写的 `actor` 记 gyb、`via=reclaim`（`04` 第三节、`05`「actor 怎么定」）。
- `launch_order` 且最新尝试有 `launched` 未 `finished` 的 run 行时不杀进程（`04` 第三节）。

### 测试 8：钩子

原文：deploy 会话 Write `analysis/x` 被 deny 且标准错误含「开 issue」命令；任何角色 Write `loop/x.jsonl` 一律 deny；run 会话 Write `experiments/x` deny；deploy 会话 Write 仓库根 `run.py` 放行；deploy 会话 Write 仓库外 worktree 路径放行。

原文没动。`06` 第 66 行按这五条验收钩子。

### 测试 9：actor 与权限

原文：analysis 调 `rl grant add` 退出码 3；analysis 会话里 `rl eval approve --as-gyb` 缺 `--quote` 退出码 2、带 quote 通过且账行 actor 是 gyb、session_id 是当前会话；裸终端 `rl eval approve` 直接通过、session_id 是 `cli`；裸终端 `rl grant add` 通过、角色会话 `--as-gyb` 的 `grant add` 拒收；非 run 调 `rl run add` 退出码 3、gyb 调通过；gyb 缺必填字段拒收、带 `--force --reason` 通过且账行有 force_reason。

要改的：「角色会话 `--as-gyb` 的 `grant add` 拒收」这一句改成「角色会话里 `--as-gyb --quote` 替 gyb 写 grant 也收」（`05`「actor 怎么定」和命令表，2026-08-17 gyb 裁，sync-inbox 问题 27，gyb 原话「3 不是，可以替我写」；`03` 裁决记录同）。两处原文不一致：`01-gyb.md` 第一节第 3 条和第二节「三条只收裸终端的」还写着「角色会话里 `--as-gyb` 写 grant 一律拒收」，`01` 在 README 里状态是「未开」，没跟上这条裁决。本份按后裁的 `05` 和 `03` 走，`01` 那两句等 `01` 开的时候改。

要加的：

- 角色带 `--force` 一律退出码 3，附「开 issue 给 gyb」的命令；角色会话里 `--as-gyb --quote --force --reason` 算 gyb 身份写，照写（`03` 裁决记录、`05`「actor 怎么定」）。
- `rl init` 在角色会话里跑退出码 3（`05` 命令表、`08` 第一节）。
- `--force` 越不过表外转移，退出码 2（`05`「actor 怎么定」）。
- 退出码 5 用法错（参数写错、编号不存在）；所有非零退出标准错误第一行是固定的原因种类（`validation`、`forbidden`、`lock_timeout`、`usage`、`internal`），`--json` 时同一个值放 `error.kind`（`05`「退出码与 --json」，2026-08-17 问题 25）。
- `decisions.gyb.jsonl` 只收 `session_id` 是 `cli` 的行这一条不变，角色会话里 `--as-gyb` 的决定落角色那本、actor 记 gyb（`02`、`05`），测试 3 已有一条，这里不重复。

### 测试 10：runs 账 schema

原文：发射版缺 `commit` 或 `config` 拒收、不要求 metrics；收尾版 `exit_status=ok` 缺 `metrics` 拒收；`failed` 不要求 metrics 但要有 actual_seconds；`finish` 时指标落在 0 或 1 自动开 `anomaly` issue 给 gyb；`run list` 默认不出 killed 和旧尝试，`--all` 出。

要加的：

- 收尾版 `exit_status=ok` 时 `data_path` 也必填；发射版没有 `artifact_dir` 这一栏（`03` 裁决记录 2026-08-17，`23`）。
- `finish` 时实际耗时超过预计的 `anomaly.duration_factor` 倍（默认 3）同样开 `anomaly` issue（`12`「看门狗」末段、`21` 第七节）。
- `rl run relink RUN_ID --handoff ID` 追加一版只换 `handoff_id`，其他栏照抄最新版（`03` 裁决记录，sync-inbox 问题 31）。
- `started_at`、`finished_at` 由 rl 填，命令行不收（`05` 命令表）。
- `run list --decision` 和 `--line` 经 `handoff_id` 反查 handoffs 的 `decision_refs` 和 `line`（`05` 命令表）。

### 测试 11：`rl status`、`rl inbox` 与 `rl reclaim`

原文：造三张不同时长的单子，阈值内外各列对；收件箱十段各造一条都出现；inbox 四类各造一条；reclaim `--only`/`--skip` 生效、开干的发射单默认不杀、`--kill` 才杀；`--line` 过滤对。

要改的：inbox 是五项不是四类，第五项是本角色提的 feedback 的裁决；inbox 只读，不顺带关任何 issue，通知类 issue 由收件人自己 close（`05`「rl inbox」，2026-08-17 问题 23、28）。要加的：

- `rl status` 第一行打印距上次 reclaim 几天；`--json` 每行至少含十二个键，`holder_alive` 按 sessions 最新版是不是 `open` 算，`age_hours` 从当前状态那一版的 `ts` 起算（`05`「rl status 的十段」，2026-08-17 问题 29）。
- 段 7 和 reclaim 用的 `last_activity` 不落账、查询时现算（`03`、`04` 第七节）。
- reclaim 对被打回超过 `reclaim.handoff_idle_hours` 没动的单子推回 `todo`，走 `rejected` 到 `todo` 那一行，`actor` 记 gyb、`via=reclaim`；对 `stuck` 的单子只改派 issue 给 owner，状态不动（`04` 第八节）。
- `rl inbox --json`、`rl doctor --json`、`rl reclaim --json` 的最小结构（`05`「退出码与 --json」）。
- run 不查 inbox（`05`「rl inbox」，问题 28），用例里不给 run 造 inbox 项。

### 测试 12：端到端

原文：沙盒仓库 `rl init` 建树，模拟 idea 开单、deploy 接单写代码写报告提验收、idea 打回、单子回 `todo`、deploy 再接、idea 验收，全程只经 rl，最后 `rl doctor` 零报告；第二条：deploy 开发射单、run 接单 smoke 失败 stuck、deploy amend 一次尝试 resume、run 再接 ok、`rl trace` 从 run_id 打回决定。

要加的：`rl init` 在裸终端跑（`08` 第一节）；第一条里打回之后走 `rejected` 到 `todo` 的 `handoff release`，再 `handoff start`（`04` 第三节）；第二条里 amend 追加的那次尝试分不分新 run_id 还没裁（`21` 留给 gyb 第 4 条），用例先按「新尝试新 run_id」写，标出等裁。

### 测试 13：`tests/test_skill_refs.py`

原文：五份 SKILL.md 里出现的每条 rl 子命令、账名、状态名、目录名都在第二、五、六节里查得到，写命令在该角色的 `ledger_writes` 里，查询命令不查；SKILL.md 里没有 common/ 母版条文的副本。

原文没动。查询命令是 show、list、trace、status、inbox、stale、doctor 七类，`doctor --ack` 和 `--unack` 算写命令（`05`「查询命令和写命令的分界」）；`reads` 栏五份 json 写法不统一、按哪种形式查还没裁（`06` 留给 gyb 第 8 条）。

### 测试 14：口径

原文：propose 时 code_path 不存在通过，approve 时不存在拒收；reject 后 update 一版再 approve 通过；approved 后 update 回 proposed；figure 行缺 `uses` 或 group_by 取值不在允许域拒收；一次 approve 多条一句 quote。

要加的：`rl eval retire` 只有 gyb 能调（`05` 命令表，2026-08-17 定稿）；`applies_to` 是自由文本、rl 不解析、但必填（`03` 裁决记录）。

### 测试 15：收回与接替

原文：对有 holder 的单子 withdraw，自动出现 `withdrawn` 通知给 holder 的角色和 owner；`--cascade` 沿 parent_id 收掉派生的发射单；`reissue` 收旧开新、supersedes 指旧单。

要改的：`withdrawn` 通知只在从 `in_progress` 收回时开，其他状态收回不通知（`04` 第九节）。要加的：通知类 issue（`withdrawn`、`orphaned`、`fyi`）不是读过即关，收件人自己 close，`withdrawn` 和 `orphaned` 的 `handoff_id` 必填（`04` 第九节）；gyb 越过 owner 验收和打回都给 owner 发 `fyi`（`04` 第五节，2026-08-17 裁）。

### 测试 16：快车道

原文：`ql open` 分标签建 worktree、scratch 开张行；`ql close --merged` 要求 handoff 存在、`--dropped` 要 reason；status 只列没关的。

要改的（HANDOFF 问题 8、16，`07` 第七节，`05` 命令表）：

- 合回顺序是先 `rl handoff open --quick-lane --report-method P --ql QL` 拿到补单编号，再 `rl ql close QL --merged --handoff ID`；`ql close --merged` 的前提是 ID 是 quick_lane 补单且它的 `ql_tag` 等于 QL。
- `ql close --merged` 只有 deploy 能调；analysis 的快车道没有补单，只有 `--dropped`。
- analysis 的 `ql open --role analysis` 不建 worktree，建 `analysis/scratch/<ql_tag>/`，scratch 开张版填 `dir`。
- scratch 中间追加数字的每一版 `status` 仍是 `open`，`open`、`merged`、`dropped` 三版按表查必填，中间版只查骨架和 `ql_tag`（`03` 裁决记录）。

### 测试 17：feedback

原文：accept 校验 applied_to 每个路径存在、rules_version 加一、sessions 开始版记 rules_version、inbox 对提的人列裁决。

要加的：`verdict_text` 在 `accepted` 和 `rejected` 两版都必填（`03` 裁决记录）；accept 列出还活着的会话和它们的 `rules_version`、打印待办（`09` 第四节、`05` 命令表）；`feedback accept --text` 必带（sync-inbox 第五段）。

### 测试 18：`rl session amend`（`05` 定稿点名新加）

用例：对一个 `open` 的会话 `rl session amend ID --model M`，sessions 追加一版只换 `model`、`status` 与其他栏照抄最新版；对一个 `closed` 的会话同样能 amend，不触「被销号会话再写账拒收」那条；amend 试图改 `model` 之外的栏拒收；谁能调是 gyb 裸终端或该角色的活会话，别的角色调退出码 3；doctor 第 19 项在 amend 之后不再报（`04` 第七节、`05` 命令表和「rl doctor」）。

### 测试 19：`rl doctor --ack / --unack / --list-acks`（`05` 定稿点名新加）

用例：doctor 报第 6 项某条 run，gyb `rl doctor --ack 6 RUN_ID` 之后同一项同一编号永久不再报，`loop/.doctor-acks.jsonl` 多一行记 `item`、`id`、`ts`、`actor`、`session_id`；`--list-acks` 列出全部 ack；`--unack 6 RUN_ID` 追加一行 `unack` 之后 doctor 重新报；角色调 `--ack` 退出码 3；`.doctor-acks.jsonl` 不算九本账，`rl init` 不建它、首次 `--ack` 时建（`05`「rl doctor」、`08` 第一节）。

### 测试 20：`lock.timeout_seconds`（`05` 定稿点名新加）

用例：一个进程占着 `loop/.lock` 超过 `lock.timeout_seconds`（默认 10 秒），另一个进程写账退出码 4，标准错误第一行是 `lock_timeout`，`--json` 时 `error.kind` 是 `lock_timeout`，账里没有新行；把 `research-loop.json` 里这个值改成 1 秒再跑一遍，等待时间跟着变（`05`「退出码与 --json」、`08` 第三节阈值表）。

## 三、施工步骤 0 到 8

施工纪律四条从 8 月 15 日的记录搬过来：每步封闭验收（这一步的测试全绿才算完）、检查器先于被检查物（先写 schema 校验和测试，再写入账代码）、一步一个动件（一个 commit 只做一件事）、修三轮修不动就废掉重做。

施工之前 gyb 先自己打磨设计文档。下表照抄施工计划第十一节，测试编号那一栏按第二节补进新加的三条（18、20 归步 3，19 归步 4，这个归属是本份补的，gyb 可改）。

| 步 | 交付 | 验收 | 依赖 | 执行者 |
|---|---|---|---|---|
| 0 验证 | 第一节 11 条的结果写进 `plans/2026-08-1x-research-loop-verify.md`，每条写实测结果和选了主案还是备案；备案影响正文的当场改设计文档，删掉另一案 | 11 条都有结论 | 无 | 主会话亲自做，要真会话 |
| 1 清空 | `git rm -r research-loop/`，只留空目录和 `.claude-plugin/plugin.json` 新写一份 | 目录里只有 plugin.json | 无 | 主会话 |
| 2 架构文档 | `research-loop/ARCHITECTURE.md`，两棵树每个文件一行：干什么、谁读、谁写、改它连带改哪些；十一条原则抄一份在开头 | gyb 读一遍点头 | 步 0（备案影响树） | 主会话写 |
| 3 共同底座 | `tables/ledgers.json`、`tables/transitions.json`、`tables/roles/*.json`、`tables/gyb-usecases.json`、`schemas/*.schema.json`、`scripts/rl_lib.py`（锁、编号、追加、校验、actor 判定）、`bin/rl` 骨架，测试 1 到 7、9、10、14、17、18、20 | `tests/run_all.py` 全绿 | 步 2 | 工单化，走 ticket-run，实现者 sonnet、评审 opus |
| 4 交流机制 | `hooks/`（写权钩子、登记销号钩子）、`rl status`、`rl inbox`、`rl trace`、`rl reclaim`、`rl doctor`、`rl notify`、`monitors/`（看门狗）、快车道命令，测试 8、11、15、16、19 | 全绿；在真会话里手动触发一次 deny 和一次销号 | 步 3 | 工单化同上；真会话验证主会话做 |
| 5 公共母版 | `common/GLOBAL-RULES.md`（公共规矩八条加十一条原则，带 rules_version 和 rule-NN/principle-NN 编号）、`common/GLOSSARY.md`（词表加「它不是什么」）、`common/SPEC-TEMPLATE.md`（五栏）、`common/READING.md`（读法栏原话）、判断类检查的问题清单（文件名待定，reviewer 派 sonnet subagent 按它逐题查，2026-08-17 裁；和 `14` 第一节「不开 issue、不派活」的冲突等 sync-inbox 问题 6） | gyb 逐条过 | 步 3 | 主会话写，中文底稿给 gyb 过，正式版英文 |
| 6 五个 SKILL.md | `skills/idea/`、`skills/deploy/`、`skills/run/`、`skills/analysis/`、`skills/reviewer/` 各一份 SKILL.md（英文，头部带钩子声明，正文有 use case 表，只引用母版不抄），run 的照 `12`，入口 `skills/research-loop/SKILL.md` 只干 init、迁移提醒、领路（路线图在 `08` 第五节） | 测试 13 全绿 | 步 4、5 | gyb 开三个终端并行，每个终端加载 `claude --plugin-dir ./research-loop`，一个终端一到两个角色 |
| 7 最小一条路 | 在临时沙盒仓库 `rl init`（裸终端）→ 加载 idea 写一条决定开一张工单 → 加载 deploy 接单写代码写报告提验收 → 回 idea 打回 → deploy 再接 → idea 验收 → `rl doctor` 零报告；再走一遍测试 12 的第二条（发射单 smoke 失败到 trace）；然后在 new1 跑 `rl init`，gyb 改 new1 CLAUDE.md 的 GPU 那一行和脏树白名单（`08` 第七节 7.9） | 沙盒全程只经 rl；new1 的 `loop/` 长出来、CLAUDE.md 只多一节 | 步 6 | 主会话，真会话 |
| 8 总验收 | gyb 定五个任务，每个角色两个 agent 一个加载 skill 一个不加载各做一遍，产出摆一起 | gyb 自己看 | 步 7 | gyb 定任务，主会话派 agent（模型按 `00` 第三节裁决 3 的表：idea、reviewer 用 fable，deploy、run、analysis 用 opus） |

每步一个或多个 commit，commit message 前缀 `research-loop v2:`；用起来之后改母版的 commit 前缀 `research-loop rules:`，改完跑一遍 `tests/run_all.py`。

施工计划第十二节留给 gyb 的四件事，和本份有关的抄在这里：总验收的五个任务在步 8 前定；第三轮模拟要不要跑、跑之前先把 new1 第一次 `rl init` 那个没跑成的场景补上（第三轮的题目另有一份，`plans/2026-08-17-research-loop-usage-scenarios.md`）；new1 CLAUDE.md 的两处宿主改动在步 7 时由 gyb 亲手改。

## 和别的 part 的接口

- 待验证第 4 条备案升正案（`rl init` 只在裸终端跑）：定义在 `08-trees-init-and-host.md` 第一节和 `05-rl-cli.md` 命令表，本份只记状态。
- 待验证第 10 条备案收成 doctor 第 19 项、修法 `rl session amend`：定义在 `05-rl-cli.md`「rl doctor」和 `04-handoffs-and-sessions.md` 第七节。
- 待验证第 5、8、9、10 条不成立会改掉的正文：`04-handoffs-and-sessions.md` 第四、六、七节，`12-role-run.md` 接单与销号那几节；两份的接口一节各有一句指回本份。
- 待验证第 6、7 条（桌面通知、定时提醒）的推送表和提醒周期：`01-gyb.md` 第五、六节。
- 待验证第 11 条（改母版要不要重启）和测试 13、17：`09-common-and-feedback.md`。
- 测试 2、4、7、11、15 背后的转移表、holder 不变量、销号、reclaim：`04-handoffs-and-sessions.md`。
- 测试 1、3、10、14、17、18 背后的账行格式、退出码、锁：`03-ledgers.md`；`02-decisions.md` 抄了测试 3 的用例名。
- 测试 8、13 背后的钩子和角色 json：`06-hooks-and-permissions.md`。
- 测试 9、11、19、20 背后的 actor 判定、退出码六个、`--json`、doctor 十九项、`--ack`：`05-rl-cli.md`。
- 测试 4 快车道那两句和测试 16：`07-quick-lane.md`。
- 施工步 1、2、7 的交付与验收里两棵树和宿主改动：`08-trees-init-and-host.md`。
- 施工步 6 里 run 的 SKILL.md 照哪份写：`12-role-run.md`。
- 施工步 8 的模型表：`00-overview.md` 第三节裁决 3。

## 源文档没写清的（留给 gyb）

1. doctor 十九项只有第 3 项（经测试 6）和第 19 项（经测试 18）有对应的测试用例，其余十七项各造一条脏账、跑修法命令、再扫零报告，第十节没有这一条测试。
2. 测试 5 里「口径引用同样查过版」由哪条命令出（`22` 留给 gyb 第 3 条），没裁之前这一句写不成用例。
3. 测试 12 第二条里 amend 追加的那次尝试分不分新 run_id（`21` 留给 gyb 第 4 条），用例只能先按一种写。
4. 测试 13 按 `reads` 栏查「每个读的目录都在 reads 里」，五份 json 里 reads 的写法不统一（`06` 留给 gyb 第 8 条），按哪种形式查没裁。
5. 待验证第 8 条的备案「workflow 里的 `agentType` 指向 `agents/<role>.md`」要求插件树多一层 `workflows/` 或 `agents/`，`08` 第四节的目录清单里没有（`08` 留给 gyb 第 10 条），第 0 步测出走备案的时候步 1 建的空目录要不要多这一层没写。
6. 待验证第 9 条只测 deploy 起 run 这一层，idea 起 deploy、deploy 再起 run 的两层嵌套没测（第二轮 run-crash-midway 第 10 条、new-idea 第 4 条报过）；原则 11 之后是后台派活、不再同步嵌套等，这一条要不要补测两层各自的后台行为没写。
7. 步 3 和步 4 用 ticket-run 工单化，工单怎么切、每张工单对应第二节的哪几条测试，第十一节没写。
8. 步 8 总验收「每个角色两个 agent 一个加载 skill 一个不加载」，不加载 skill 的那个 agent 用什么模型、按裁决 3 的 as_subagent 那一栏还是别的，没写。
9. 运行期改母版的 commit 前缀 `research-loop rules:` 之后要不要重跑整套 `tests/run_all.py` 还是只跑测试 13，第十一节末尾那句只写「改完跑一遍 `tests/run_all.py`」，第二轮 feedback-round 第 14 条报过这一处。
10. 新加的三条测试（18、19、20）归步 3 还是步 4 是本份补的归属，源文档没写。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

以下条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，未做判断、未改字。那份文件开头写明：17 个场景各派一个 opus 模拟者、一个 opus 核实者，最后一个 critic；模拟者跑完 16 个，17 个核实者和 critic 全部因为月度用量上限没跑成，所以下面的摩擦全部是未经核实的模拟者原话，可能有误报。选进来的标准是这一条直接点到待验证清单、某条测试、或者施工步骤；同一条摩擦可能同时出现在别的 part 里。

### param-tweak（45 步，gyb 动手 8 次）

1. [blocks/contradiction] 第 42 步：设计文档说销号只查「还挂在开干的单子」，施工计划说 end 时扫 holder 是本会话的单子、有就拒绝，没有状态过滤；而转移表里 in_progress→done_pending_review 那一行不清 holder（测试 2 只要求 start 写、stuck→todo/rejected/release/reclaim 清），于是 run 交完活就销不了号，用 --release 又会把已交活的单子打回 todo
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:87; plans/2026-08-16-research-loop-build-plan.md:204
   - 改法：转移表 in_progress→done_pending_review 那一行加「holder 清空」，并把 build-plan:126 的扫描限定成 in_progress 和 stuck 两种状态

17. [cosmetic/contradiction] 第 4 步：设计文档说 SKILL.md 正文出现的每条 rl 子命令都要在角色 json 的 ledger_writes 里，施工计划的测试 13 只查写命令；deploy 上线要跑的 rl decision stale、rl handoff show 都是查询命令，不在 deploy 的 ledger_writes 里，按设计文档那句机器检查就红
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:215; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：把设计文档那一句改成「每条 rl 写命令」，或角色 json 加一栏 queries 单列查询命令

20. [cosmetic/missing] 第 3 步：sessions 账要求手动加载也记真实模型名、不记 inherit，而角色 json 的 manual 一律是 inherit；钩子从哪里拿到当前会话的真实模型标识没写，待验证清单里也没有这一条
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:189
   - 改法：待验证清单加一条「SessionStart 钩子输入里有没有模型标识」，拿不到就退到 rl session start --model unknown

### new-idea（39 步，gyb 动手 7 次）

4. [blocks/too_heavy] 第 10 步和第 19 步：接单默认是同步的，deploy 等 run 几个小时、idea 又等 deploy，于是 gyb 手动加载的 idea 会话从派单那一刻起被整场实验占住，gyb 想看进度只能另开终端；待验证第 9 条的失败备案只写了 deploy→run 这一层改成开单即销号，idea→deploy 这一层没有备案
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：明写 gyb 手动加载的角色会话一律不同步等下游，开完单即返回，验收由下一次会话或 gyb 在 rl status 里做

### result-wrong-review（25 步，gyb 动手 11 次）

10. [slows/ambiguous] 第 23 步：决定来源 file 类允不允许指 review/ 里的清单两种读法都通：设计文档举例只有 notes/ 里 gyb 的调查报告和 analysis/ 里的图与 notebook，测试 3 却只检查路径存不存在。审出问题之后更新决定，最自然的来源就是那份清单，入账脚本按哪种写会决定它收不收。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:205; plans/2026-08-16-research-loop-build-plan.md:57
   - 改法：设计文档第 46 行明写 file 类是仓库内任意路径，举例补上 review/ 的清单和 experiments/ 的部署报告。

### next-plan-after-results（36 步，gyb 动手 16 次）

5. [slows/ambiguous] 第 13、19 步：gyb 本人坐在角色会话里敲 `--as-gyb`，rl 分不出是 gyb 敲的还是模型敲的，测试 9 又硬性要求缺 quote 退出码 2，等于逼 gyb 引用自己刚说的话；文档只写了「角色会话里的模型」必须带 quote，没写 gyb 本人要不要
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:211; 2026-08-16-research-loop-next-steps.md:34
   - 改法：明写 `--as-gyb` 一律要 quote、gyb 本人把自己那句话填进去即可，SKILL.md 里给一条示例

### run-crash-midway（40 步，gyb 动手 4 次）

10. [slows/too_heavy] 第 12 到 20 步：三层会话同步嵌套等待：idea 等 deploy 等 run（next-steps.md:120、:58）。一个训练跑几小时，崩了之后 deploy 修完还要再等一整轮重跑，sess-idea-01 从派单到验收全程挂着不能做别的，与 next-steps.md:7「想法要快速、多次迭代」直接冲突。待验证第 9 条（build-plan.md:197）只测了一层（deploy 等 run），没测两层嵌套，备案也只写了 deploy 那一层。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：发射单一旦标 stuck 就让上游 subagent 立刻返回并销号，重跑由 gyb 在 `rl status` 里另起一个 deploy 会话接。

### n-launch-orders（58 步，gyb 动手 10 次）

2. [blocks/missing] 第 11 步：deploy 用什么起那个 workflow、workflow 定义文件放在插件树的哪里、5 张单号怎么分派给 5 个 subagent，三样都没写。插件本体的目录清单里只有 skills/common/tables/schemas/scripts/bin/hooks/monitors/tests，没有 workflows/ 或 agents/；待验证第 8 条的备案里出现过「workflow 里的 agentType 指向 agents/<role>.md」，但那只是备案，正文没定。这个场景的核心机制整个是猜的。
   - 依据：2026-08-16-research-loop-next-steps.md:68; 2026-08-16-research-loop-next-steps.md:150; 2026-08-16-research-loop-build-plan.md:196
   - 改法：在插件树里加一层 workflows/fanout.js（或 agents/<role>.md），明写 deploy 起 N 个 run 时把单号、batch、分到的卡逐个写进 subagent 提示。

7. [blocks/contradiction] 第 25、42 步：销号时查 holder 的范围两份文档写得不一样：设计文档说「检查这个会话作为 holder 有没有还挂在开干的单子」，施工计划说「扫 holder 是本会话的单子，有就拒绝并列出」。转移表里 done_pending_review 和 stuck 两个状态都不清 holder，所以按施工计划的读法，4 个跑完的 run subagent 和写完报告的 deploy 会话全都退不出去；按设计文档的读法才能销号。测试清单第 7 条只覆盖了 in_progress 这一种。
   - 依据：2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-build-plan.md:126; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:84; 2026-08-16-research-loop-build-plan.md:209
   - 改法：施工计划第六节改成「只拦 status 为 in_progress 且 holder 是本会话的单子」，done_pending_review 和 stuck 一律放行销号。

13. [slows/missing] 第 26 步：待验证第 9 条（上游 subagent 同步等几小时会不会被超时收掉）的备案正好落在这个场景上，但备案没给续跑规矩：一旦 deploy 开完单就销号，ho-0012 会被销号钩子交回 todo、报告还没写、5 张发射单已经派出去，下一个 deploy 会话重新 start 之后怎么知道进度到哪、去哪找那个 batch，文档没写。
   - 依据：2026-08-16-research-loop-build-plan.md:197; 2026-08-16-research-loop-build-plan.md:93; 2026-08-16-research-loop-next-steps.md:120
   - 改法：备案里补一句：work_order 也记 batch，重新 start 时第一件事是 rl handoff list --batch 复原五张单的状态。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

13. [slows/guessed] 第 13 步：整段「deploy 会话起 run subagent、subagent 里加载角色 skill、头部钩子装得上、写权拦得住」建立在待验证第 8 条上，那一条还没测，备案是改走 workflow 的 agentType 或者干脆只靠纪律。我按主案（钩子装得上）走完了这一段，主案不成立的话第 13 到 20 步的登记、销号、写权全部要换写法。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:167; plans/2026-08-16-research-loop-build-plan.md:196; plans/2026-08-16-research-loop-build-plan.md:227
   - 改法：施工步 0 先把第 8 条测掉，测完在设计文档 run 一节写死走主案还是备案，不留两种走法。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

3. [blocks/contradiction] 第 4、7 步：handoffs 字段表里没有指向父单的字段，但至少四处规矩依赖这条派生链：转移表的 --cascade 要收「派生的下游单」、测试 15 要 cascade 收掉派生的发射单、快车道正式重跑的发射单要「挂在这张工单上」、doctor 要扫「快车道工单已 accepted 但没有关联发射单」；设计文档还直接断言存在「从决定顺到发射单再顺到 run_id 的那条链」，rl decision show --with-runs 和 rl run list --decision 都靠它。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:217; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-next-steps.md:80; plans/2026-08-16-research-loop-build-plan.md:130
   - 改法：handoffs 加一个 parent_handoff 字段，launch_order 和 analysis_order 新建时必填（快车道补单可空），转移表新建那一行的前提栏写进去。

### feedback-round（15 步，gyb 动手 9 次）

7. [slows/missing] 第 14 步（下次加载角色时生效）：「母版改动在下次加载角色时生效」是这个场景的最终答案，可是第九节九条待验证清单里没有它：改一行 common/ 之后，同一个 claude 进程里再加载一次角色 skill 读到的是新文本还是缓存的旧文本，没人测过
   - 依据：plans/2026-08-16-research-loop-next-steps.md:101; plans/2026-08-16-research-loop-build-plan.md:187; plans/2026-08-16-research-loop-build-plan.md:196
   - 改法：待验证清单加第 10 条：改一行母版，不重启 claude 再加载一次角色，看模型读到的是不是新文本，失败备案是改完母版必须重开终端

8. [slows/missing] 第 10 步（gyb 自己 grep 五份 SKILL.md）：母版 common/ 和五份角色 SKILL.md 是引用关系还是抄一份，文档没写；施工步 5 和步 6 是两步分别写的两组文件。抄了的话改母版根本不生效，gyb 只能自己去 grep 五份 SKILL.md 有没有重复条文
   - 依据：plans/2026-08-16-research-loop-next-steps.md:150; plans/2026-08-16-research-loop-build-plan.md:232; plans/2026-08-16-research-loop-build-plan.md:233; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：定死 SKILL.md 只写一句「按 common/GLOBAL-RULES.md 执行」、不许抄条文，测试 13 加一条查 SKILL.md 里有没有母版条文的副本

14. [cosmetic/missing] 第 15 步（改完母版要不要 commit、要不要跑测试）：第十一节的「每一步施工结束 tests/run_all.py 全绿才 commit」和 commit 前缀 research-loop v2: 只管施工那八步，用起来之后运行期改母版要不要单独 commit、要不要重跑测试 13，没写
   - 依据：plans/2026-08-16-research-loop-build-plan.md:219; plans/2026-08-16-research-loop-build-plan.md:237; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：feedback 那一节补一句：accept 之后母版改动单独一个 commit，前缀 research-loop rules:，并跑一遍 tests/run_all.py

### hook-missed-session-end（23 步，gyb 动手 11 次）

2. [blocks/contradiction] 步 20：施工 L126 写 rl session end「扫 holder 是本会话的单子，有就拒绝并列出」，测试 7（施工 L209）写的是「holder 名下有 in_progress 单子时拒绝」。转移表 in_progress→done_pending_review 那一行（施工 L87）不清空 holder，测试 2（施工 L204）列的清空时机也不含 done_pending_review。按 L126 字面，正常交完活的 deploy subagent 销号会被拒收，钩子拿不到合法的下一步（--release 会把已交活的单子打回 todo），会话照样结束，sessions 账再留一行没有结束版的死会话，本场景的 bug 自我复制一遍。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:209; plans/2026-08-16-research-loop-build-plan.md:87; plans/2026-08-16-research-loop-build-plan.md:204
   - 改法：L126 改成「扫 holder 是本会话且状态是 in_progress 或 stuck 的单子」，并在转移表那一行写明 holder 保留到 accepted 或 rejected。

6. [slows/guessed] 步 13、步 14：设计 L120 只写「上游开完单直接起一个 subagent 接走并同步等它回来」，没写下游 subagent 没走到 done 或 stuck 就返回的时候上游拿到什么、该做什么。待验证第 9 条（设计 L168、施工 L197）只问「等几个小时会不会被超时收掉」，不问「等的对象死了怎么办」。最快能发现这件事的就是被阻塞的上游会话，文档没给它任何职责，我只能按原则 3 推它该 release 加重起。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：设计 L120 补一句「下游 subagent 没走到 done 或 stuck 就返回的，上游当场 rl handoff release 并决定重起还是开 issue 给 gyb」，并写进 idea 和 deploy 的 SKILL.md。

### smoke-fails（44 步，gyb 动手 4 次）

15. [slows/guessed] 步 9 与步 22（run subagent 的钩子与销号）：待验证清单第 5 条（SubagentStop 在 subagent 结束时触不触发、会话 id 是不是同一个）和第 8 条（subagent 里加载角色 skill 钩子装不装得上）都还没测，两条各有备案，选主案还是备案会改掉本场景一半的走法：备案里 subagent 路线改成 workflow 的 agentType，或者「接单只靠纪律加 reviewer 事后查」，那样 run 的写权拦不住、销号全靠 reclaim、sessions 账没有结束版。我这次按主案走，属于猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:193; plans/2026-08-16-research-loop-build-plan.md:196; plans/2026-08-16-research-loop-next-steps.md:164; plans/2026-08-16-research-loop-next-steps.md:167
   - 改法：施工步 0 出结论之后，按选中的那一案把 run 的 SKILL.md 和第七节改死，删掉另一案，不留两条路。

### doctor-findings-fix（24 步，gyb 动手 15 次）

7. [slows/missing] 第 8、18 步（holder 指向死会话）：转移表和测试 2 列的 holder 清空时机是 start 写、stuck→todo / rejected / release / reclaim 清，唯独 in_progress→done_pending_review 不清；销号钩子又只检查 holder 名下还在 in_progress 的单子。于是等验收的单子上 holder 长期写着一个已经销号的会话，rl status 那一栏显示有人在干，实际没有。
   - 依据：2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:204; 2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-next-steps.md:124
   - 改法：在转移表 in_progress→done_pending_review 那一行补一句 holder 清空，或者 rl status 显示 holder 时标出这个会话还活着没有。

## 裁决记录（日期）

- 2026-08-17：本份补写（前一天的 workflow 没写成这一份）。正文只搬运施工计划第九、十、十一节和各 part 2026-08-17 的裁决，测试 18、19、20 是 `05` 定稿点名要有测法的三条，本份给了用例；三条归步 3 还是步 4 是本份补的归属，记在留给 gyb 第 10 条。
- 2026-08-17：待验证第 4 条备案升正案、第 10 条备案收成 doctor 第 19 项，两条都来自 `05` 定稿（`656c8a9`）的裁决，本份第一节状态栏照记；两条照测不改正文。
- 2026-08-17：测试 9 里「角色会话 `--as-gyb` 的 `grant add` 拒收」按 sync-inbox 问题 27 的裁决改成「`--as-gyb --quote` 替 gyb 写也收」，`01-gyb.md` 两处相反的句子标为不一致、等 `01` 开的时候改。
