# gyb 自己做的事与 gyb 的收件箱

> 这份覆盖三样：gyb 亲自做而任何角色都不代劳的事（文献、口径、grants、feedback、手动结束会话、手动开 reviewer、reclaim）；gyb 的身份规矩（cli、`--as-gyb` 加 `--quote`、`--force --reason`、`decisions.gyb.jsonl` 只收裸终端、豁免范围）；gyb 这一头的出口（gyb 的 use case 表、`rl status` 十段与 `--json` 行结构、桌面通知推送表、定期提醒）。不覆盖：五个角色各自干什么在 `10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`、`14-role-reviewer.md`；九本账的行格式在 `03-ledgers.md`；派活单状态转移表和会话生命周期在 `04-handoffs-and-sessions.md`；`bin/rl` 完整命令表在 `05-rl-cli.md`；钩子与角色 json 在 `06-hooks-and-permissions.md`；快车道在 `07-quick-lane.md`；`rl init` 建的树和宿主对接在 `08-trees-init-and-host.md`；反馈账本身的行格式与母版在 `09-common-and-feedback.md`；决定账在 `02-decisions.md`。源：设计文档的「十一条设计原则」第 1、5、6 条、「gyb 自己做的事」、「交接与会话生命周期」的收件箱段与回收段、「分权与钩子」的豁免段、「入口 skill 与代码迁移」的领路；施工计划第一节裁决 6 与（b）（c）（d）、第二节词表、第五节 gyb 的 use case 表、第六节 actor 判定与各命令行、第八节阈值、第九节待验证第 6、7 条。

## 一、gyb 亲自做的七件事

这套系统里有七件事只有 gyb 亲自做，任何角色都不代劳。

### 1. 文献变成想法

gyb 自己做文献调查，把调查报告写成 md 放进 `notes/`，`notes/` 只有 gyb 写，谁都能读。这一版不加文献线，也没有角色去查「这个想法别人做过没有」，要加文献账是另一件事；`notes/` 就是文献进入这套系统的唯一入口。

idea 要经 gyb 允许才有读文献的权限。`rl init` 的时候问 gyb 一次要不要当场给 idea 发 `read:notes`，发了就不再走申请；没发的话 idea 开一条 issue 给 gyb（kind 是 `request`），gyb 写一条 grant，idea 之后才读 `notes/`。读权不上钩子，grant 是给 reviewer 事后查的凭据，`rl doctor` 有一项扫描「决定的来源指向 `notes/` 但 grants 里查不到这个 actor 的 `read:notes`」。

### 2. 说要分析什么、画什么图

evaluations 每一行都是 gyb 说、analysis 记、gyb 批。任何角色都不许自己写新的要分析的东西，analysis 不许自作主张画图，只把 gyb 说要看的数算出来。gyb 可以打回一条口径（附原因），analysis 改了再提一版；已经 `approved` 的口径再改一版就回到 `proposed`，要 gyb 重新批。批可以一句话批一组：`rl eval approve` 收多个编号一个 `--quote`。口径行的字段和四个状态在 `03-ledgers.md`，analysis 那一头怎么提在 `13-role-analysis.md`。

### 3. 写 grants

授权只有 gyb 能写：grants 的 `actor` 必须是 `gyb`。裸终端直接写；角色会话里 `--as-gyb --quote` 替 gyb 写也收，`session_id` 照记那个会话（2026-08-17 gyb 裁，sync-inbox 问题 27，原话「3 不是，可以替我写」；施工计划第一节（d）「grants 只收裸终端」不认）。`grant list` 和 `grant show` 是查询命令，谁都能调（原则 2 推论：读一律不设权）。

### 4. 裁 feedback

feedback 谁都能提、只有 gyb 能裁，谁都能读。裁成采纳的那一版写清改了哪几个文件（`applied_to` 是路径列表，母版和文档都算，至少写一个、不要求两样都有），rl 校验每个路径存在、自动把 `rules_version` 加一、列出还活着的会话和它们的 `rules_version` 让 gyb 挑要不要收，并打印一张待办（还要改哪几处、要不要收会话、单独 commit 加跑测试）。母版改动在下次加载角色时生效，正在跑的会话不追、不通知，按现行母版干到底；母版改动单独一个 commit。

### 5. 手动结束会话

销号平时由钩子自动做，挂在 SessionEnd 和 SubagentStop 上。gyb 也可以手动结束会话，而且可以指定别的会话：`rl session end --session ID`。销号时程序当场检查这个会话作为 holder 有没有还挂在 `in_progress` 的单子，有就交回 `todo` 并写进度说明、给 owner 发 `orphaned` 通知。会话生命周期的完整规矩在 `04-handoffs-and-sessions.md`。

### 6. 手动开 reviewer

reviewer 只由 gyb 手动开，审整条链，产出只写 `review/` 里的问题清单，不开 issue、不派活，动不动由 gyb 看完之后定。reviewer 开工时 `rl session focus --decision ID` 记一下在审什么，`rl status` 的活着会话那一段带出来；`rl status` 还列出最近 `status.review_recent_days`（默认 7）天的清单。reviewer 的审查基准是「actor 是 gyb 或 idea 的决定行」，不看落在哪个文件里。reviewer 自己怎么读、清单五栏长什么样在 `14-role-reviewer.md`。

### 7. 定期跑回收

`rl reclaim` 收拾很久没动的会话和单子，只有 gyb 能跑，`--apply` 才动手。参数是 `--session-older-than H`、`--handoff-older-than H`、`--only ID ...`、`--skip ID ...`、`--kill`、`--apply`，可以逐条挑或跳过。它做的事：

- 会话标 `reclaim` 销号，并 release 名下 `in_progress` 的单子；
- `in_progress` 的 `launch_order` 默认不杀进程（留给下一个 run 认领），带 `--kill` 才先走中断收尾（杀进程、释放显存、宿主销号、runs 落 `killed`）；
- `stuck` 的单子只把 issue 改派给 owner，状态保持 `stuck`；
- `rejected` 的单子超过 `reclaim.handoff_idle_hours` 没动的推回 `todo`（`actor` 记 gyb、`via=reclaim`），owner 重新拉起；
- `done_pending_review` 和 `todo` 的只列出来附现成命令，不动手；
- 结束时按 owner 分组打印待拉起的单子和加载命令，并自动跑一遍 `rl doctor`。

两处原文不一致：设计文档「交接与会话生命周期」写「回收对开干的发射单先走中断收尾（杀进程、释放显存、宿主销号、runs 落 killed）再交回待干」，施工计划第六节的 reclaim 行和第四节转移表写「默认不杀进程（等下一个 run 认领），`--kill` 才走中断收尾」。2026-08-17 gyb 裁（在 `04-handoffs-and-sessions.md`）：默认不杀，`--kill` 才杀。

阈值默认值（施工计划第八节，写进 `research-loop.json`，gyb 可改）：

| 键 | 默认值 | 用在哪 |
|---|---|---|
| `reclaim.session_idle_hours` | 48 | 会话超过 48 小时没写任何账算很久没动 |
| `reclaim.handoff_idle_hours` | 72 | 单子超过 72 小时没转移算很久没动 |
| `reclaim.ql_idle_days` | 7 | 快车道超过 7 天没关列进 reclaim |
| `status.stale_holder_minutes` | 30 | `rl status` 段 7：holder 会话超过 30 分钟没写账的开干单 |
| `issues.gyb_stale_hours` | 24 | `rl status` 段 2 标出超过 24 小时没动的 |
| `status.review_recent_days` | 7 | `rl status` 列最近 7 天的 review 清单 |
| `notify.reminder_days` | 7 | 每 7 天提醒 gyb 跑 `rl reclaim`、看 feedback、跑 doctor、落母版 |

## 二、gyb 的身份规矩

### rl 只认会话，不认手指

每次写账都有一个 actor：要么是五个角色之一，要么是 `gyb`。gyb 是超级用户，钩子、入账校验里的「谁能调」和转移表的「谁能写」对 gyb 一律不生效，gyb 在任何终端、任何角色会话里都能行使自己的权。

rl 能看到的只有「这条命令从哪个会话发出来」，看不到键盘前面坐的是 gyb 还是模型，所以一切身份规矩只按会话定：

- 裸终端（`session_id` 是 `cli`）发出的命令 actor 就是 `gyb`，不用旗子也不用原话。rl 从会话状态文件读当前角色，读不到状态文件就是裸终端。
- 角色会话里发出的命令默认 actor 是那个角色。加 `--as-gyb` 才以 gyb 身份写，`session_id` 照记当前会话，而且不论是谁敲的都要带 `--quote "<gyb 原话>"`（gyb 本人敲就引自己刚说的那句），缺 quote 退出码 2。这个 quote 是留给 reviewer 的痕迹，不是身份判定。

账行如实记 actor 和会话两样。sessions 账另有一栏 `launched_by`，取 `manual`、`subagent`、`workflow`，分得出这个会话是 gyb 手动加载的还是派出来的。

### 决定落哪本账

决定行按编号前缀落文件，一条决定的所有版本永远同一个文件，谁写的另记 `actor`（2026-08-18 gyb 裁，定义处 `02-decisions.md`）。gyb 在裸终端新开的决定用 `gyb` 前缀、落 `decisions.gyb.jsonl`（第六个决定文件），这个文件只装 gyb 在裸终端新开的决定和它们的后续版本，所以里面只有 `session_id` 是 `cli` 的行；gyb 在裸终端给角色的决定（比如 `dec-idea-0007`）追加的一版落那个角色那本，actor 记 `gyb`、`session_id` 记 `cli`。角色会话里替 gyb 记的决定落那个角色自己那本，actor 记 `gyb`，带 quote。gyb 坐在 deploy 会话里当场拍板一个影响实验结果的参数，按这条落 `decisions.deploy.jsonl`、actor 记 `gyb`、带 quote，不算 deploy 自决。决定编号的前缀只说这条决定开在哪本账，谁写的看 actor。

### 豁免范围

gyb 只豁免权限，不豁免账行的完整性：

| 检查 | 对 gyb 生效吗 |
|---|---|
| 钩子（Write/Edit 的目录限制） | 不生效 |
| 入账校验的「谁能调」 | 不生效 |
| 转移表的「谁能写」 | 不生效 |
| 转移表的「前提」栏 | 生效 |
| 必填字段、路径存在、引用存在 | 生效 |

gyb 要硬写就加 `--force --reason`，rl 照写并把 reason 记进账行的 `force_reason` 字段。actor 是角色的命令带 `--force` 一律拒收，退出码 3，附「开 issue 给 gyb」的命令；角色会话里 `--as-gyb --quote --force --reason` 算 gyb 身份写，照写（2026-08-17 gyb 裁，来自 `03-ledgers.md`）。`--force` 只越过完整性前提，越不过转移表外的转移：表外转移对 gyb 同样退出码 2，硬改状态走 `withdraw` 再重开（2026-08-17 gyb 裁，来自 `05-rl-cli.md`）。runs 账的 actor 允许 `run` 或 `gyb`，gyb 例外这一条明写在字段表里。还有一条 `--force` 越不过：写命令的 `session_id` 在 sessions 账里最新版是 `closed` 的，rl 拒收并提示重新加载角色登记，退出码 3，`--force`、`--as-gyb --force` 都越不过，唯一出路是重新加载角色（2026-08-17 gyb 裁，sync-inbox 问题 14，定义处 `03-ledgers.md`）。

### 只收裸终端的

- `decisions.gyb.jsonl`：只收 `session_id` 是 `cli` 的行。
- grants 不在这一类里（2026-08-17 gyb 裁，sync-inbox 问题 27）：只有 gyb 能写，裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收。
- 其余一切写命令角色会话里都能用 `--as-gyb` 打。

## 三、gyb 的 use case 表

五个角色的读写权从各自的 use case 表倒推（原则 5）。gyb 也有一张，`rl status` 的段落和各 list 命令的过滤维度从这张表倒推，不是从五个角色的表推。表在施工计划第五节，落成 `tables/gyb-usecases.json`：

| use case | 要看什么 | 倒推出的命令或段落 |
|---|---|---|
| 开工第一眼 | 两条线各到哪一步、谁在干、哪些等我 | `rl status [--line L] [--group-by line\|batch]`，每行带线名和决定编号，`--json` 行结构写死 |
| 批 | 等批的口径、等裁的 feedback | status 段 3、段 8；`eval approve ID... --quote`、`feedback accept` |
| 验收 | 等验收的单子（含快车道补单）、报告路径 | status 段 4；`handoff accept/reject` |
| 拉起 | owner 没有活会话的待干单、gyb 手动接的单 | status 段 5，每行附「加载哪个角色」的命令 |
| 看进度 | 在跑的实验到哪了、日志和监控命令 | status 段 1 的发射单行带 `log_path`、`watch_cmd`、按 batch 汇一段 |
| 查一个数从哪来 | run 到发射单到工单到决定 | `rl trace <任何编号>` |
| 收回、改版重派 | 引旧版的活单和它们的 holder | `decision update/retire` 当场打印；`handoff withdraw/reissue` |
| 收拾 | 很久没动的会话和单子、卡住的、没关的快车道 | status 段 6、7、9；`rl reclaim --only/--skip`，输出按 owner 分组附现成命令 |
| 修账 | doctor 扫出没修的 | status 段 10；`rl doctor` 每项附修法和「修完之后归谁推」 |
| 会话 | holder 那个 session 是谁、活没活着 | `rl session show/list [--alive] [--role R]` |

## 四、rl status：gyb 的收件箱

收件箱有两个（原则 6）：gyb 的叫 `rl status`，角色的叫 `rl inbox`（见 `05-rl-cli.md`）。`rl inbox` 是查询命令，谁需要谁敲：角色被拉起不自动查收件箱，先干拉它起来的那张单；run 不查 inbox，只关注自己那张发射单（2026-08-17 gyb 裁，sync-inbox 问题 28）。任何一版把某一行送进「等 gyb」的状态，那一行必须出现在 `rl status` 里。`rl status` 谁都能调。

参数是 `[--line L] [--group-by line|batch] [--json]`。第一行打印距上次 `reclaim` 几天。十段：

| 段 | 列什么 |
|---|---|
| 1 | 没到终态的单子（owner、holder 及活没活着、状态、挂了多久、线、发射单带 `log_path` 和 `watch_cmd`） |
| 2 | assignee 是 gyb 的 open issue（超过 `issues.gyb_stale_hours` 的标出） |
| 3 | 等批的口径 |
| 4 | 等验收的单子 |
| 5 | 等 gyb 拉起的（owner 无活会话的 `todo`、`dispatch=manual` 的） |
| 6 | 过版的单子和 retired 决定名下的活单 |
| 7 | holder 会话超过 `status.stale_holder_minutes` 没写账的开干单 |
| 8 | 等裁的 feedback |
| 9 | `review/` 最近的清单、活着的会话（含 focus）、没关的快车道 |
| 10 | 上次 doctor 没修的 |

`--json` 每行至少含 `id`、`work_type`、`owner`、`holder`、`holder_alive`、`status`、`age_hours`、`line`、`decision_refs`、`batch`、`log_path`、`watch_cmd`。可以按 batch 或根决定（`line`）归组。

## 五、桌面通知推送表

桌面通知只是 gyb 收件箱里几段的推送，不是第三个通道。`rl notify --text` 是内部命令，由 rl 在推送表的时机自己调；gyb 也可以手动调来给自己发一条提醒，两种调法都不进任何账（2026-08-17 gyb 裁）。推送表和 `rl notify` 的机制都定义在本节，`05-rl-cli.md` 只留命令签名（2026-08-17 gyb 裁）。推送时机五档：

| # | 触发 |
|---|---|
| 1 | issue 的 assignee 变 gyb（含首次开单） |
| 2 | 单子进 `done_pending_review` 且 owner 是 gyb 或 `dispatch=manual` |
| 3 | feedback 提出 |
| 4 | owner 无活会话的 `todo` 出现——在单子落 `todo` 那刻（open / release / reject / reissue）和 `session end` 销号时查 owner 有无活会话并推（2026-08-17 gyb 裁） |
| 5 | doctor 有没修的 |

通知机制本身还没定，是待验证第 6 条：试 Claude Code 自带推送、`notify-send`、终端铃三种，通过标准是 gyb 桌面看得到；失败备案是退到 `rl status` 单列那一层，通知不做。

gyb 越过 owner 处理别人的单子时，rl 给 owner 开一条 kind 是 `fyi` 的 issue，进那个角色的 `rl inbox`，不进桌面通知；这条 issue 不是读过即关，owner 做完了自己 `rl issue close`（2026-08-17 gyb 裁，sync-inbox 问题 23）。两处原文不一致：设计文档「交接」一节写「gyb 越过 owner 验收或打回时 rl 给 owner 发一条 fyi 通知」，施工计划第四节转移表只在 `done_pending_review → accepted` 那一行写了 fyi，`rejected` 那一行没写。2026-08-17 gyb 裁（在 `04-handoffs-and-sessions.md`）：验收和打回都发 fyi。

## 六、定期提醒

每 `notify.reminder_days`（默认 7）天提醒 gyb 四件事：跑 `rl reclaim`、看 feedback 账、跑 `rl doctor`、把采纳的 feedback 落进母版并单独 commit。

提醒机制也没定，是待验证第 7 条：试 Claude Code 的 schedule 和系统 cron，通过标准是到点 gyb 收得到；失败备案是 `rl status` 第一行打印距上次 reclaim 几天（这一条已经是正案的一部分），提醒不做。

入口 skill 的领路里有一条对应路线：「收到定期提醒：`rl status`、`rl reclaim` 看列表、`--apply`、按 owner 逐个拉起、`rl doctor`」。入口 skill 只许 gyb 手动调用，见 `08-trees-init-and-host.md`。

## 和别的 part 的接口

- 派活单的七个状态（`todo`、`in_progress`、`stuck`、`done_pending_review`、`accepted`、`rejected`、`withdrawn`）、`owner`、`holder`、`last_holder`、`dispatch`（`auto`/`manual`/`none`）的定义在 `04-handoffs-and-sessions.md`；`rl status` 段 1、4、5、6、7 全按这些字段过滤。
- 转移表里「前提」栏和「谁能写」栏的分工在 `04-handoffs-and-sessions.md`；本文第二节的豁免表只说这两栏对 gyb 生不生效。
- 九本账的公共骨架（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`、`force_reason`、`via`）和每本的字段在 `03-ledgers.md`。
- grants、feedback、evaluations、sessions 四本账的行格式和状态取值在 `03-ledgers.md`；本文只写 gyb 这一头的动作。
- `rl status`、`rl reclaim`、`rl doctor`、`rl notify`、`rl grant`、`rl feedback`、`rl eval`、`rl session`、`rl inbox`、`rl trace` 的完整参数和退出码在 `05-rl-cli.md`。
- actor 判定的实现（会话状态文件路径 `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json`、钩子在加载角色时写）在 `06-hooks-and-permissions.md`。
- 钩子对 gyb 裸终端和 `--as-gyb` 不生效这一条的另一半（钩子挂在哪两个工具、拦哪两类路径）在 `06-hooks-and-permissions.md`。
- `ql_tag`、快车道补单验收人固定是 gyb、没关的快车道进 status 段 9 与 reclaim，在 `07-quick-lane.md`。
- `rl init` 问 gyb 要不要给 idea 发 `read:notes`、`notes/` 目录、`research-loop.json` 里的阈值，在 `08-trees-init-and-host.md`。
- feedback 采纳之后母版的 `rules_version` 怎么走、`common/` 母版本身，在 `09-common-and-feedback.md`。
- `decisions.gyb.jsonl` 的编号、版本、来源三类、根决定，在 `02-decisions.md`。
- gyb 直接开分析单（owner 记 gyb）在 `22-pair-idea-analysis.md`；gyb 越过 owner 验收后给 owner 的 `fyi` 通知走 `rl inbox`，见对应角色的 part。
- 待验证第 6 条（桌面通知机制）、第 7 条（定时提醒机制）的测法、通过标准、失败备案在 `30-build-steps-verify-tests.md`。

## 源文档没写清的（留给 gyb）

1. gyb 的 use case 表里「收拾」这一行指向 `rl status` 段 6、7、9，可段 6 列的是「过版的单子和 retired 决定名下的活单」，和这一行「很久没动的会话和单子、卡住的、没关的快车道」对不上；哪一段归哪个 use case 没有一一对上。
2. `rl status` 段 2（assignee 是 gyb 的 open issue）在 gyb 的 use case 表里没有对应行，这一段是从哪个 use case 倒推出来的没写。
3. 推送表五档没写通知里带什么字段、gyb 点开之后该打哪条命令；`rl notify --text` 只有一个文本参数。
4. 定时提醒机制不成立时备案是「`rl status` 第一行打印距上次 reclaim 几天」，可谁提醒 gyb 去打 `rl status` 没有第二条路。
5. 只写死了 `rl status --json` 的行结构，`rl reclaim` 和 `rl doctor` 的 `--json` 结构没写。——2026-08-17 已定（`05-rl-cli.md` 定稿「退出码与 --json」一节写了 `rl inbox --json`、`rl doctor --json`、`rl reclaim --json` 三条的最小结构，gyb 裁）。
6. gyb 手动开 reviewer 之后：gyb 怎么点名审哪条决定（除了 reviewer 自己打 `rl session focus`）、gyb 看完 `review/` 清单之后决定的动作落在哪本账，都没写。
7. `--force --reason` 只写了「rl 照写并把 reason 记进账行」，没写哪些完整性前提允许被 force 越过、有没有一条也不许越过的（比如转移表里表外的转移）。——2026-08-17 随 `05` 定稿裁：只越过完整性前提、越不过表外转移，已写进第二节「豁免范围」（rl-hub）。
8. gyb 手动加载角色时 sessions 账的 `model` 记「解析后的真实模型名或 `unknown`」，`unknown` 由 doctor 列出来让 gyb 事后补，可补的命令是哪一条没写。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

以下条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，未做判断、未改字。那份文件开头写明：17 个场景各派一个 opus 模拟者、一个 opus 核实者，最后一个 critic；模拟者跑完 16 个，17 个核实者和 critic 全部因为月度用量上限没跑成，所以下面的摩擦全部是未经核实的模拟者原话，可能有误报。

### param-tweak（45 步，gyb 动手 8 次）

8. [slows/contradiction] 第 27 步：设计文档说替 gyb 打 --as-gyb 带 --quote「靠纪律，钩子不拦」，施工计划和测试 9 说缺 quote 退出码 2 硬拒收；更麻烦的是 gyb 本人和模型在同一个角色会话里打命令，rl 读的是同一个会话状态文件，分不出是谁打的，硬拒收就连 gyb 自己验收都要造一句原话
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：定成硬拒收并只留一个值：gyb 本人在角色会话里用 --as-gyb --by-hand 免 quote，模型用一律要 quote

19. [cosmetic/ambiguous] 第 24 步：「gyb 看着行就合回主分支」这句的主语是 gyb，但 deploy 用 Bash 做 merge 钩子也不拦，谁执行 merge 两种读法都成立
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:132
   - 改法：明写 merge 由 gyb 亲自打，deploy 只把命令交出来

### new-idea（39 步，gyb 动手 7 次）

5. [slows/contradiction] 第 8 步：设计文档说 gyb 亲自打 --as-gyb 的落 decisions.gyb.jsonl、idea 替 gyb 记的落 decisions.idea.jsonl 并带 quote，可角色会话里的命令全是模型打的，而施工计划规定模型打 --as-gyb 必须带 quote、账行 actor 记 gyb，决定文件又按 actor 拆名，同一条命令按两份文档会落进两个不同文件
   - 依据：plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:29; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：明写「decisions.gyb.jsonl 只收裸终端写的行，角色会话里模型打的 --as-gyb 一律落 decisions.<角色>.jsonl 并记 quote」

### result-wrong-review（25 步，gyb 动手 11 次）

5. [blocks/missing] 第 19 步（gyb 若当场废掉或改 dec-idea-0007 而不是让 idea 改）：gyb 给别人的决定追加一版落哪个文件没写：设计文档说 gyb 写的决定落 decisions.gyb.jsonl，又说决定账按 actor 拆六个文件、编号带角色前缀，那 dec-idea-0007 的第 3 版由 gyb 写就会和第 1、2 版分居两个文件，「默认查询只取最新版」和锁里的扫号都要跨文件才对，入账脚本没有依据。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-next-steps.md:96; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:128
   - 改法：明写「决定行按 id 前缀落文件，谁写的记在 actor 字段」，dec-gyb 前缀只给 gyb 新开的决定。

6. [slows/contradiction] 第 19 步和第 23 步：`--as-gyb` 缺 `--quote` 到底硬不硬拦：设计文档说「这条靠纪律，钩子不拦，reviewer 事后可查」，施工计划第六节说「缺 quote 时 rl 拒收（退出码 2）」；再者 rl 只看会话状态文件，分不出角色会话里这条命令是 gyb 本人敲的还是模型敲的，硬拦会把 gyb 本人一起拦住，和原则 1「任何权限检查对 gyb 不生效」相冲。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：统一成硬拦，并明写 gyb 本人在角色会话里也要带 --quote（自引一句即可），设计文档第 34 行的「靠纪律」删掉。

### plot-new-plan（17 步，gyb 动手 8 次）

3. [slows/principle_violation] 第 10 步（gyb 开分析单）：违反原则 1。原则 1 写 gyb 在任何终端、任何角色会话里都能行使自己的权，任何权限检查不生效；但施工计划只让 gyb 豁免转移表「谁能写」一栏和「谁能调」检查，「前提」一栏照旧生效，于是 gyb 自己开分析单时被 evaluation_refs 必须 approved 这条前提挡住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:77; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：在施工计划第四节表头明写「前提」一栏对 gyb 生不生效，若生效就把它改称数据完整性校验、和权限检查分开命名。

9. [slows/ambiguous] 第 9 步与第 15 步（会话里以 gyb 身份写账）：施工计划写「角色会话里的模型用 --as-gyb 必须同时给 --quote」，但 rl 看到的只是同一个 session_id 下的一条命令，分不出键盘前面是 gyb 本人还是模型；gyb 亲手在角色会话里打 --as-gyb 要不要带 quote 两种读法都说得通。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：改成「角色会话里的 --as-gyb 不论谁敲一律要 --quote」，把它定性成痕迹而不是身份判定。

10. [slows/ambiguous] 第 10 步（分析单的 from_role）：owner 被定义成开单角色也就是 from_role，而角色只有五个、gyb 不在角色表里；设计文档和词表都说 gyb 可以开分析单，但 handoffs 的 from_role 能不能填 gyb、gyb 算不算合法 owner 没有明写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:41; plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：在第三节 handoffs 的 from_role 字段写清取值是五个角色或 gyb，并说明 owner 是 gyb 时验收和拉起下游都由 gyb 做。

12. [cosmetic/missing] 第 13 步到第 14 步（图画完之后叫 gyb）：单子进 done_pending_review 只出现在 rl status 里，桌面通知只在 issue 改派给 gyb 的时候发；gyb 不坐在这个会话里的时候，得靠自己轮询才知道图画好了。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：把「等 gyb 验收的单子」也接进 rl notify，或者在设计文档里明写这一类只进 rl status、不通知。

### next-plan-after-results（36 步，gyb 动手 16 次）

3. [slows/principle_violation] 第 14 步：违反原则 1。原则 1 和施工计划裁决 6 说 gyb 不受任何权限检查影响，转移表却只给 gyb 豁免「谁能写」一栏、不豁免「前提」一栏，于是 gyb 自己也开不出引未批口径的分析单、也收不了缺交付物的单子。两句话对「权限检查」的范围理解不一样
   - 依据：2026-08-16-research-loop-build-plan.md:77; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15
   - 改法：把原则 1 改写成「权限检查对 gyb 不生效，数据完整性前提对谁都生效」，并给 gyb 一个 `--force` 带原因写进账行

4. [slows/too_heavy] 第 1 到 36 步整条路：只是「看完一批结果定下一步」，gyb 亲自动作 16 次，其中光批口径就要按行逐条批、图口径还得先有指标口径两级批。设计文档开头写的目标是想法要快速多次迭代，每一条手续都要拿这两点衡量，这条路和那句话拉扯
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-next-steps.md:183; 2026-08-16-research-loop-build-plan.md:69
   - 改法：给「一批结果的例行复盘」开一条批量口令：gyb 一句话批一组口径（rl 记下这句原话展开成多行），图口径自动带上它 uses 的指标

5. [slows/ambiguous] 第 13、19 步：gyb 本人坐在角色会话里敲 `--as-gyb`，rl 分不出是 gyb 敲的还是模型敲的，测试 9 又硬性要求缺 quote 退出码 2，等于逼 gyb 引用自己刚说的话；文档只写了「角色会话里的模型」必须带 quote，没写 gyb 本人要不要
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:211; 2026-08-16-research-loop-next-steps.md:34
   - 改法：明写 `--as-gyb` 一律要 quote、gyb 本人把自己那句话填进去即可，SKILL.md 里给一条示例

6. [slows/ambiguous] 第 26 步：讨论里定下的结论落 decisions.gyb 还是落 decisions.idea 带 quote，判据是「gyb 亲自打的」还是「idea 替 gyb 记的」。可是在手动加载角色的会话里 rl 命令都是模型敲的，「gyb 亲自打」这条路实际只存在于另开裸终端，同一条结论两处都说得通，reviewer 的基准会散在两本账里
   - 依据：2026-08-16-research-loop-next-steps.md:34; 2026-08-16-research-loop-next-steps.md:44; 2026-08-16-research-loop-build-plan.md:121
   - 改法：定死「角色会话里一律落角色那本账带 quote，decisions.gyb 只收裸终端写的」，把判据从「谁亲手敲」换成「哪个会话」

8. [slows/missing] 第 27、36 步：决定 retire 之后，引用它的在办单子没人扫。doctor 的八项扫描和 rl status 的七段都没有「retired 决定名下还有没到终态的单子」这一项，设计文档又把停不停全交给 gyb 点名，忘了收回就一直挂着
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:112
   - 改法：doctor 和 status 各加一项「retired 决定名下还有活单」，附上 `rl handoff withdraw --cascade` 的修法

### n-launch-orders（58 步，gyb 动手 10 次）

11. [slows/principle_violation] 第 41 步：违反原则 1（gyb 是超级用户，钩子、入账校验、转移表的谁能写对 gyb 一律不生效）。施工计划规定角色会话里用 --as-gyb 缺 --quote 一律退出码 2，而 rl 分不出键盘前面坐的是 gyb 本人还是模型，结果 gyb 在自己手动加载的角色会话里反而行使不了 gyb 权，只能退出会话回裸终端。这和裁决 6「gyb 在任何终端、任何角色会话里都能插入」直接打架。
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15; 2026-08-16-research-loop-next-steps.md:34
   - 改法：缺 quote 时不拒收，改成照写并在账行打一个 quote_missing 标记留给 reviewer 事后查。

12. [slows/missing] 第 18、20 步：5 个 run subagent 的监控入口到不了 gyb 眼前。gpu-run 要求发射后把 gpu-jobs watch 和网页交给用户，但 subagent 的输出只回到 deploy 会话；rl status 列的是单子状态和挂了多久，不含进度、速率、ETA。gyb 在这几个小时里看不到这一批五张卡跑到哪了。
   - 依据：.claude/skills/gpu-run/SKILL.md:97; 2026-08-16-research-loop-build-plan.md:161; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:124
   - 改法：rl run add 时把宿主的 tmux session 名和监控命令写进 runs 行，rl status 按 batch 汇一段进度出来。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

7. [slows/contradiction] 第 9、20 步：原则 6（next-steps.md:20）写「所有等 gyb 处理的事由 rl status 一处列出，桌面通知只是它的推送」，issues 一节（next-steps.md:97）写「只有改派到 gyb 名下的时候 bin/rl 才给 gyb 发通知，其余不发」。过版、等批口径、等验收这几段按后一句就永远不推送，gyb 只能靠自己想起来跑 rl status。本场景要不是 gyb 自己就是改决定的人，过版没人叫他。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：把「哪几段触发推送」列成一张表写进第八节阈值旁边，过版且有 holder 的单子归进推送那一档。

8. [slows/principle_violation] 第 11 步：违反第 1 条原则（next-steps.md:15「任何权限检查对 gyb 一律不生效」）。build-plan.md:121 规定角色会话里用 `--as-gyb` 缺 `--quote` 就退出码 2 拒收，而 rl 分不出这条命令是 gyb 本人敲的还是会话里的模型代打的，于是 gyb 本人在角色会话里行使 gyb 权也会被拒收。本场景 gyb 因此被逼退出去另开一个裸终端才收得掉 ho-0013。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：缺 quote 时不拒收，改成落账时把这一行标 `quote_missing` 交给 reviewer 事后查，硬拦只留给模型自己发起的不可逆动作。

10. [slows/missing] 第 10 步：公共规矩第 1 条（build-plan.md:245）要求不可逆动作要有 gyb 当场的原话，收回是终态、不可逆，可是 `rl handoff withdraw ID [--cascade]`（build-plan.md:134）没有 `--quote` 参数，handoffs 行格式（build-plan.md:61）也没有 quote 字段，gyb 那句「停」没有落点。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:245; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：withdraw 和 reject 都加 `--quote`，handoffs 行加 quote 字段，角色会话发起时缺 quote 就报错。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

2. [blocks/missing] 第 1 步：没有任何办法表达「这张单 gyb 手动接，别起 subagent」：rl handoff open 没有这个旗子，handoffs 行里没有这个字段，idea 的默认动作是开完单直接起 deploy subagent 并同步等。gyb 的口头交代不进账，idea 会话一旦重开或被 reclaim，idea 还会按 owner 职责再拉起一个下游，两个会话抢着打 rl handoff start，晚的那个撞上「表外转移一律拒收」拿退出码 2。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:83; plans/2026-08-16-research-loop-build-plan.md:95
   - 改法：给 handoffs 加一个 dispatch 字段（auto / manual），rl handoff open 带 --manual 时 owner 不起 subagent、rl status 单列这类单子。

6. [slows/ambiguous] 第 10 步：gyb 坐在 deploy 会话里当场拍板一个影响实验结果的参数，这条落 decisions.deploy 还是 decisions.gyb 两种读法都说得通：deploy 一节说「取第几层、超参取值算自决，进 decisions.deploy」，idea 一节说「gyb 会参与到影响实验结果的工程细节里，这些细节同样写进决定账」并要求 gyb 定的那一版和角色自决的分得出来。落错了直接影响 reviewer——reviewer 的审查基准只有 gyb 和 idea 层谈定的决定，落进 decisions.deploy 就不在基准里。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:60; plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:34
   - 改法：在 deploy 一节补一句：gyb 当场拍板的算 gyb 的决定，落 decisions.gyb（--as-gyb 加 --quote），deploy 自决只指 gyb 不在场时自己拿的主意。

7. [slows/ambiguous] 第 10 步、第 26 步：--as-gyb 的 --quote 是给「模型替 gyb 打」设的，可 rl 拿不到「这条命令是 gyb 的手指打的还是模型打的」这个信息，同一个角色会话里两种情况长得一模一样。要么一律强制 quote（gyb 本人被迫引用自己一句话），要么一律不强制（模型代打的痕迹就没了）。本次模拟只能绕道：gyb 另开裸终端验收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：定死一律强制 --quote，gyb 本人打的时候 quote 里填自己那句话；文档里把这条写成「无条件」而不是「模型用的时候」。

8. [slows/too_heavy] 第 11、16、22 步：gyb 亲手接一张已经开出来的正式工单，手续和 subagent 走一模一样：必须开发射单、必须分步计时填 step_table、必须写两份部署报告（method 那份还要原样抄决定编号加版本）。想减手续只有快车道，可快车道的入口是「gyb 点名」加另开一棵 worktree 加 rl scratch add，转移表里也没有「已开出的工单转快车道」这一行，而且审读意见第 1、2 条已经明确否掉了按改动大小分档。gyb 亲自上手的场合反而最重，和「想法要快速、多次迭代」相反。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:178; plans/2026-08-16-research-loop-build-plan.md:82
   - 改法：转移表补一行「todo 的 work_order 由 gyb 改标 quick_lane」，改标之后免发射单和两份报告，只留 scratch 记录。

9. [slows/too_heavy] 第 12 步到第 21 步：gyb 手动的 deploy 会话按默认要同步等 run subagent 跑完才能接着干，实验跑几个小时 gyb 的交互终端就被占几个小时；而「上游 subagent 同步等下游几个小时会不会被超时收掉」还挂在待验证第 9 条上没有结论，备案是「长任务改成 deploy 开单即销号」，两种走法对 gyb 手动会话的体验差别很大。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：对 gyb 手动加载的角色会话默认走异步：开完发射单就把工单 release 回 todo，等 run 完了 rl status 提醒 gyb 再接。

10. [slows/principle_violation] 第 3 步：违反原则 1（谁在打命令和会话装了什么角色是两回事，账行如实记 actor 和会话两样）。这条链上第 5 到第 23 步全部由 gyb 本人驱动，可 sessions 账只有 role 和 model 两栏、handoffs 只有 holder 一栏、每条账行的 actor 只能填角色名，事后没有任何字段能分出「这张单是 gyb 亲手干的」还是「subagent 干的」；reviewer 要查也查不到。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-next-steps.md:120
   - 改法：sessions 账加一栏 launched_by（manual / subagent / workflow），钩子登记时按有没有父会话填。

11. [slows/missing] 第 26 步：gyb 越过 owner 直接验收之后，没有任何通道把这件事告诉 owner idea。转移表 done_pending_review→accepted 那一行第五栏是「无」，issues 账只在改派给 gyb 时发通知，rl status 是给 gyb 的收件箱不是给角色的。idea 会话下次上线只会看到单子已经是终态，不知道是谁验的、为什么验过。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:88; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:20
   - 改法：gyb 代 owner 写终态转移时，rl 自动给 owner 角色开一条 kind=not_mine 之外的新 kind（比如 fyi）的 issue，或者在角色上线时和 decision stale 一起报一句「你名下的单子被 gyb 处理过」。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

5. [slows/contradiction] 第 2 步：rl status 列几段两处不一样：设计文档列七段（单子、issue、口径、等验收、过版、review 清单、快车道 worktree），施工计划列八段（多一段「活着的会话」）。按原则 8，施工计划只有第一节的裁决优先，第六节是草案，所以设计文档赢、「活着的会话」被砍——而本场景里 gyb 恰恰要靠这一段看两条线各有谁在干活。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-next-steps.md:22
   - 改法：把「活着的会话」补进设计文档第 124 行那句，两处对齐成八段。

6. [slows/too_heavy] 第 9、10、20、25 步：收件箱里每一条都要两跳才知道属于哪条线：issue 行只有可选的 handoff_id，要 issue show 再 handoff show；口径行只有自由文本 applies_to；scratch 行只有 ql_tag、worktree、base_commit。一条线一天挂三五条，早上第一眼就变成十几条命令。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：rl status 每行直接把这一行溯到的决定编号和线名打出来，别让 gyb 自己跳。

8. [blocks/missing] 第 13 步：owner 是角色不是会话，owner 角色没有活着的会话时谁把它叫醒没写。原则 3 和交接一节四处都写「回到待干、由 owner 重新拉起下游」，本场景蒸馏线的 deploy 会话已销号，账上只剩一张 todo 单子和一个不存在的 owner。按原则 1 只能推出 gyb 有权自己干，推不出系统怎么提醒他该开哪个角色的会话。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:93
   - 改法：rl status 单列一段「等 gyb 拉起」：owner 角色没有活会话的 todo 单子，每行附上该开哪个角色会话的那条命令。

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

12. [slows/too_heavy] 整条路（gyb 亲手做九件事）：改一条规矩要 gyb 亲自做九个动作（status、feedback list、改母版、改施工计划、grep 五份 skill、accept、判断要不要收会话、告诉 deploy、commit），系统只帮他记一行账，剩下八件全靠他自己记得住；这跟「想法要快速、多次迭代」的目标不匹配
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-build-plan.md:67
   - 改法：rl feedback accept 收多个 applied_to 并当场打印一张待办（还要改哪几处、活着的会话要不要收、要不要 commit 和跑测试）

13. [slows/principle_violation] 第 11 步的另一条走法（gyb 就坐在 deploy 会话里裁）：违反第 1 条「gyb 是超级用户，任何权限检查对 gyb 不生效」：角色会话里用 --as-gyb 缺 --quote 一律退出码 2（测试 9 钉死了这条），可 rl 分不出打字的是 gyb 本人还是模型，gyb 亲自在 deploy 会话里裁 feedback 会被自己的校验拦下来，得先换个裸终端
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:211; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-next-steps.md:34
   - 改法：给一个 gyb 本人当场打字的旗子（比如 --i-am-gyb）免 quote，或者把缺 quote 从拒收降成账行打一个「无原话」的标记

### idea-request-notes（15 步，gyb 动手 4 次）

1. [slows/contradiction] 第 7 步：两句打架：设计文档写「只有改派到 gyb 名下的时候 bin/rl 才给 gyb 发通知，其余不发」，施工计划写「assignee 变成 gyb 的那一版（含首次开单就写给 gyb）触发桌面通知」。idea 的 request issue 是首次开单就给 gyb、不是改派，按前一句收不到推送；rl status 那一段的措辞又是「改派给 gyb 超过 N 小时没动的 issue」，也可能不列。按原则 8，施工计划只有第一节的裁决优先，L59 是第三节草案，所以严格读应当以设计文档为准、不发通知——那 gyb 一离开终端这条申请就既没人推也不在收件箱里，idea 干等
   - 依据：plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：两处统一改成「assignee 是 gyb 的那一版一律通知（含首次开单）」，rl status 那一段同步改成「assignee 是 gyb、状态 open 且超过 issues.gyb_stale_hours 的 issue」

2. [slows/contradiction] 第 5 步：命令表里 `rl grant add / rl grant list` 整行的「谁能调」只写 gyb，idea 调 grant list 应拿退出码 3；但 idea 的 reads 写的是「九本账全部」，公共规矩第 8 条又要求「读账一律经 rl 查询命令」。结果是 idea 查不到自己名下有没有 read:notes，每开一个新会话都只能重新走一遍申请，或者凭猜
   - 依据：plans/2026-08-16-research-loop-build-plan.md:138; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:252; plans/2026-08-16-research-loop-next-steps.md:52
   - 改法：第六节把 grants 拆成两行：`grant add` 谁能调写 gyb，`grant list/show` 谁能调写「谁都行」

3. [slows/contradiction] 第 9 步：设计文档一处写「idea 开一条 issue 给 gyb，gyb 写一条 grant」，另一处允许角色会话里的模型带 --quote 替 gyb 打 --as-gyb。本场景两句合起来的结果是：申请方和批准方是同一个会话里的同一个模型，quote 只是模型自己敲进去的字符串、rl 不校验，而 grant 的全部价值就是「给 reviewer 事后查的凭据」，自提自批之后这份凭据证明不了任何事
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:245
   - 改法：第六节 grants 那一行加一句「grants 不接受 --as-gyb，只收 session_id 为 cli 的裸终端写入」，gyb 批授权必须自己在裸终端打一次

4. [slows/ambiguous] 第 14 步：决定落哪本账的判据是「由 gyb 亲自打 --as-gyb 写的落 decisions.gyb.jsonl，idea 替 gyb 记的落 decisions.idea.jsonl 并带 quote」。但在角色会话里 gyb 从不打命令、只说话，命令全是模型打的，「亲自打 --as-gyb」这件事在角色会话里不存在。模型代打的 --as-gyb 算不算亲自，两种读法都说得通，同一条 gyb 定的决定可能落进两本不同的账
   - 依据：plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:57
   - 改法：第三节写死一条：decisions.gyb.jsonl 只收 session_id 为 cli 的行，角色会话里替 gyb 记的一律落角色自己那本并带 quote

6. [slows/too_heavy] 第 6 步到第 11 步整段：gyb 就坐在这个会话里说了句「你去读吧」，为了读一份 md 却要走 issue open、通知、grant add、issue reply、issue close 五个动作四行账。permission 第一版只有 read:notes 一种、grantee 是角色不是会话，所以批一次就永久覆盖整个 notes/，这套手续一辈子只有第一次有信息量，和「想法要快速、多次迭代」这条总目标对不上
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-build-plan.md:65
   - 改法：`rl init` 时问一次 gyb 要不要当场给 idea 发 read:notes，发了以后就不用走申请，没发才走 issue 那条路

8. [slows/missing] 第 12 步：读权不上钩子、靠纪律加 reviewer 事后查，但文档没写 reviewer 拿什么查「idea 有没有在没 grant 的时候就读了 notes/」。系统里没有读日志，doctor 的八项扫描里也没有这一类，这条纪律实际上无从核对
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:136; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl doctor` 加一项扫描「decisions 里 source 指向 notes/ 但 grants 里查不到该 actor 的 read:notes」，把这条纪律接回入账校验那一层

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

4. [slows/ambiguous] 第 5、8、11 步：会话阈值 48 小时比单子阈值 72 小时短，两个方向都出问题：会话被销号而它名下的单子还没超 72 小时（销号要不要连带 release 这张单，两种读法都说得通）；单子超 72 小时被拉回 todo 而 holder 会话还活着在干（没有任何东西通知它停）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:178; plans/2026-08-16-research-loop-build-plan.md:179; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:93
   - 改法：销号一律连带 release 名下全部单子（不看单子阈值），回收还活着的 holder 的单子时照 withdraw 的办法开一条 issue 给 holder 的角色。

5. [slows/contradiction] 第 10 步：转移表里 stuck → todo 有两行：一行前提是关联 issue 状态为 answered，另一行（reclaim 走的这行）前提只要 holder 清空。reclaim 按后一行把还在等回答的单子放回待干，下一个接单的人接到一张实际还卡着的单，那条 open issue 也没人再管。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:84
   - 改法：reclaim 对 stuck 单子只清 holder、状态保持 stuck，同时把关联 issue 改派给 owner。

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

16. [cosmetic/missing] 第 2、4 步：入口 skill 的领路清单里四条路线图都是做实验的路线，没有这条定期收拾的路线，gyb 收到提醒之后要凭记忆敲 status 和 reclaim 的顺序。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:154; plans/2026-08-16-research-loop-build-plan.md:143
   - 改法：领路加一条「收到 7 天提醒 → rl status → rl reclaim 看列表 → --apply → 按 owner 逐个拉起 → rl doctor」。

17. [cosmetic/missing] 第 25 步：提醒里的第三件事「迭代框架本身」没写具体做什么、产出落到哪本账、改完的母版要不要 commit。feedback 账那条线写清楚了，这一条只有名字。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:183; plans/2026-08-16-research-loop-build-plan.md:139
   - 改法：把这一条改写成「跑 rl feedback list，把 accepted 的改动落到 common/ 母版并单独 commit」，不留抽象说法。

### hook-missed-session-end（23 步，gyb 动手 11 次）

1. [slows/too_heavy] 步 2、步 5：文档指名「钩子漏掉的」走 rl reclaim（设计 L126），但 reclaim 的默认阈值是会话 48 小时、单子 72 小时（施工 L178、L179），提醒周期 7 天（施工 L183）。会话死掉 6 小时的时候，文档给的唯一恢复路一条都不触发，这张工单最坏要躺 7 天才有人碰，和设计 L7「想法要快速、多次迭代」打架。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:178; plans/2026-08-16-research-loop-build-plan.md:183
   - 改法：rl status 加一段「holder 会话超过 N 分钟没写任何账的 in_progress 单」，N 默认 30 分钟，和 reclaim 的 48/72 小时分开。

4. [slows/principle_violation] 步 3：违反原则 6（设计 L20、L94「能 add 就有 show 和 list」）。命令表（施工 L126）里 sessions 只有 start 和 end，九本账里唯独它没有 show 和 list。gyb 从 rl status 拿到 holder 的 session_id，查不出它是哪个角色、什么时候开的、最后一次写账是什么时候。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:94; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：命令表补 rl session show ID 和 rl session list [--alive] [--role R]，谁都能调。

5. [slows/missing] 步 7：设计 L32 和 L126 两处写「gyb 也可以手动结束会话」，但命令表里 rl session end [--reason]（施工 L126）没有指定会话的参数，只能结束当前会话。gyb 结不掉那个已经死掉的 sess-deploy-3，只能等 reclaim 到 48 小时。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:32; plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：rl session end 加 --session ID，「谁能调」那一栏保持钩子和 gyb。

11. [slows/missing] 步 4：rl handoff list 的过滤器（施工 L136）只有 --status、--mine、--batch、--decision，没有按 holder 会话过滤的口子。死掉的 deploy 名下除了这张工单，还可能有它当 owner 开出去的发射单，gyb 只能全量列 in_progress 肉眼比对。--mine 在 actor 是 gyb 的时候指什么也没定义。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-build-plan.md:41
   - 改法：handoff list 加 --holder SESSION 和 --owner ROLE，并写明 actor 是 gyb 时 --mine 等于全部。

12. [slows/missing] 步 8、步 10：单子回到 todo 之后由 owner 重新拉起（设计 L17、施工 L93 第五栏），但 owner 是角色不是常驻进程。没有活着的 idea 会话的时候，这张 todo 单子只能等 gyb 下次看 rl status 才有人碰；谁在什么时候把 owner 叫起来，文档没写。本场景里重派全靠 gyb 口头说一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：rl status 的单子那段单列一行「todo 且 owner 角色当前没有活着的会话」的单子，并进桌面通知。

### smoke-fails（44 步，gyb 动手 4 次）

11. [slows/principle_violation] 步 43（gyb 跑 rl status 收尾看一眼）：违反原则 6 的「进出对称」那一半。run 开给 deploy 的 issue 不触发通知（只有改派到 gyb 名下才通知），rl status 的七段里只有「改派给 gyb 超过阈值的 issue」，没有「open 的 issue 按 assignee 分组」这一段。这条 iss-0031 从 open 到 answered 之后没人 close，账上也没有任何出口能把它列出来；单子本身能在「没到终态的单子」里露头，issue 露不了头。deploy 会话要是先走了，这条 issue 就悬着，只能靠 reclaim 捞单子，issue 永远 open。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:143
   - 改法：rl status 加一段「open 与 answered 的 issue 按 assignee 分组」，reclaim 一并列出超过阈值没动的 issue。

### doctor-findings-fix（24 步，gyb 动手 15 次）

1. [slows/missing] 第 2 步（doctor 输出修法）：doctor 那一行承诺「每类结果附一条修法（都是追加一版的 rl 命令）」，但八个扫描项没有任何一项写出具体的修法命令是什么；本场景三类问题的修法全靠我按转移表和命令表倒推，三类里有两类倒推出来的路子不止一条。
   - 依据：2026-08-16-research-loop-build-plan.md:144
   - 改法：在第六节 doctor 那一行下面补一张八行表，每个扫描项写死修法命令模板、谁能打、修完之后单子归谁推。

3. [blocks/contradiction] 第 23 步（gyb 能不能手写 runs 行）：设计文档说「第二层是入账校验，硬的……gyb 例外」，读起来 gyb 连必填字段和 actor 限制都免；施工计划说「actor 是 gyb 时跳过全部『谁能调』和转移表『谁能写』的检查」，读起来只免这两类。runs 那一行写着 actor 必须是 run，gyb 到底能不能补写一行 runs 直接取决于这两句谁算数。
   - 依据：2026-08-16-research-loop-next-steps.md:134; 2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:63
   - 改法：在施工计划第六节写死一句「gyb 只豁免谁能调与转移表谁能写，schema 必填与 actor 限制对 gyb 同样生效」，并把设计文档那句「gyb 例外」改成同一句话。

8. [slows/ambiguous] 第 19 步（谁来 accept）：gyb 本人坐在 deploy 会话里想验收，按文档要打 `--as-gyb` 并且必须带 `--quote gyb 原话`，缺 quote 退出码 2；可是 rl 只看会话状态文件，分不出这条命令是 gyb 本人敲的还是模型敲的，于是 gyb 本人也得引用自己刚说的一句话。我只能让 gyb 退回裸终端打，多切一次终端。
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-next-steps.md:34
   - 改法：`--as-gyb` 缺 quote 时改成交互式追问一次再放行，或者加一个 `--quote-self` 表示 gyb 本人当场敲的。

9. [slows/principle_violation] 第 1、24 步（doctor 的结果没有落点）：违反原则 6「所有等 gyb 处理的事由 rl status 一处列出」：doctor 扫出来的问题不在 rl status 的七段里，也不在 7 天定时提醒的三件事（reclaim、看 feedback、迭代框架）里，没人叫 gyb 跑 doctor，修不了的那条（第三类）也没有任何地方替他记着。
   - 依据：2026-08-16-research-loop-next-steps.md:20; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-build-plan.md:183; 2026-08-16-research-loop-build-plan.md:144
   - 改法：rl status 加第八段「上次 doctor 扫出还没修的问题」，并把跑 doctor 并进 7 天提醒那三件事里。

10. [slows/missing] 第 7 步（第一类修到哪算完）：文档没写 doctor 修到哪算完。补上 stuck 那一版之后账面一致了，但那张发射单实际还卡着、那条 issue 还等 deploy 回、真正的实验失败没人处理；doctor 的输出也不区分「账面对不上」和「活还没干完」。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:85
   - 改法：doctor 每条修法后面固定加一句「修完之后这张单子归谁推」，取值和转移表第五栏一致。

13. [cosmetic/missing] 第 1 步（谁跑 doctor、跑完能不能自己修）：doctor 写的是「谁都行」，但角色会话跑出问题之后能不能自己修没写。deploy 看到自己名下那张 done_pending_review 的报告路径没了，它是 to_role 不是 owner，按转移表打回只有 owner 能写，它只能开 issue，文档没说这一步该开给谁、kind 填哪个。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:45
   - 改法：在 doctor 那一行写一句「角色跑 doctor 只看不修，修法一律 `rl issue open --to <owner> --kind cannot` 报给 owner 或 gyb」。

## 裁决记录（日期）

- 2026-08-17：来自 `04-handoffs-and-sessions.md` 的裁决（rl-hub 转来；gyb 原话「可以 发」）：gyb 越过 owner 验收和打回都给 owner 发 fyi。对回原则 6。第 148 行的不一致标注照改。
- 2026-08-17：来自 `04-handoffs-and-sessions.md` 的裁决（rl-hub 转来；gyb 原话「不杀」）：reclaim 回收开干的发射单默认不杀进程，`--kill` 才杀。对回原则 11。第 45 行的不一致标注照改。
- 2026-08-17 gyb 裁（sync-inbox 问题 1，原话「这个归01吧」）：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 这一组规矩的定义处归本份第二节；`05-rl-cli.md`「actor 怎么定」是命令行写法，算写了两遍、每次同步对齐；`06` 只留钩子对 `--as-gyb` 不生效那一句。对回原则 8。
- 2026-08-17：来自 `03-ledgers.md` 的裁决（rl-hub 转来；gyb 原话「你说得对」）：actor 是角色的命令带 `--force` 一律拒收，退出码 3，附开 issue 给 gyb 的命令；`--as-gyb --quote --force --reason` 算 gyb 身份照写。对回原则 1、原则 2。第二节「豁免范围」补了这一句。
- 2026-08-17 gyb 裁（sync-inbox 问题 2，原话「算一件事」「给rl notify指到01吧」）：推送表和 `rl notify` 是一件事，定义处归本份第五节；`05-rl-cli.md` 只留 `rl notify --text` 的签名行，其「rl notify」一节缩成一句指本份。对回原则 8。第五节开头补了一句。
- 2026-08-17 来自 `05-rl-cli.md` 定稿（`656c8a9`）的裁决（rl-hub 转来；gyb 原话「全推荐」「只要他不动目前的代码什么的就全推荐就行」「全都推荐，只要不影响正在跑的进程」「A」）：第二节补「`--force` 只越完整性前提、越不过表外转移，gyb 同样退出码 2，硬改走 `withdraw` 再重开」；第五节推送表第 4 条补查的时机（落 `todo` 那刻和 `session end` 销号时）；`rl notify` 补「gyb 也可手动调、不进账」。对回原则 1、4、6、8。「没写清」第 7 条据此销掉。
- 2026-08-17 来自 sync-inbox 问题 14 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「A」）：第二节「豁免范围」补一句——`session_id` 在 sessions 账里最新版是 `closed` 的会话再写任何账，rl 拒收，退出码 3，`--force`、`--as-gyb --force` 都越不过，唯一出路是重新加载角色。对回原则 1、原则 4。
- 2026-08-17 来自 sync-inbox 问题 19 的裁决（定义处 `04`，rl-hub-v3 传；gyb 原话「B」）：第一节第 7 件事 reclaim 的处置从四类加成五类，补「`rejected` 的单子超过 `reclaim.handoff_idle_hours` 没动的推回 `todo`（`actor` 记 gyb、`via=reclaim`），owner 重新拉起」。对回原则 3。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `05`、`03`，rl-hub-v3 传；gyb 原话「只有做完了的时候才关，巡检要我本人确认」）：第五节 `fyi` 那句补「这条 issue 不是读过即关，owner 做完了自己 `rl issue close`」。对回原则 6。
- 2026-08-17 来自 sync-inbox 问题 26 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「我觉得。有一些改的方法，不一定会改公共规矩，如果是这样的话就选b。」）：第一节第 4 件事 `applied_to` 那句补「至少写一个、不要求两样都有」。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 27 的裁决（定义处本份第二节，rl-hub-v3 传；gyb 原话「3 不是，可以替我写」）：第一节第 3 件事「写 grants」改成「授权只有 gyb 能写：`actor` 必须是 `gyb`；裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收，`session_id` 照记那个会话」；第二节小节名由「三条只收裸终端的」改成「只收裸终端的」，grants 那一条改写成不在这一类里。对回原则 1。
- 2026-08-17 来自 sync-inbox 问题 28 的裁决（定义处本份第四节，rl-hub-v3 传；gyb 原话「每个角色创建时候，不要自动查收件箱……这个角色就应该先执行刚才idea给他的工作」「C」「顺便run只需要关注自己的工单，一般不会空run，不需要查，这个改了」）：第四节开头补一句——`rl inbox` 是查询命令，谁需要谁敲，角色被拉起不自动查收件箱、先干拉它起来的那张单，run 不查 inbox。对回原则 6。
- 2026-08-17 来自 sync-inbox 问题 15 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「B」）：接口一节公共骨架那行的两个可选栏由「`fix_for`、`force_reason`」改成「`force_reason`、`via`」。对回原则 4。
- 2026-08-18 来自 `02-decisions.md` 定稿（`7549704`，rl-hub-v4 传；gyb 原话「甲」）：第二节「决定落哪本账」按编号前缀落文件改写：gyb 裸终端新开的用 `gyb` 前缀落 `decisions.gyb.jsonl`，gyb 裸终端给角色决定追加的一版落角色那本、`session_id` 记 `cli`。对回原则 4。
