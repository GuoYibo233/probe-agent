# idea 角色

> 这份覆盖 idea 角色的 SKILL.md 要写的全部内容：它干什么、use case 表、读什么写什么、能调哪些 rl 写命令、决定怎么落账（来源三类、新版还是新条、confirm、跨角色改别人的决定）、工单和分析单怎么开（explanation、`--manual`、`--no-dispatch`）、怎么验收和打回、收回和 reissue、申请读 notes/、`rl inbox` 谁需要谁敲、模型用 fable 的例外。
> 不覆盖的：派活单的七个状态和状态转移表、会话生命周期与销号，在 `04-handoffs-and-sessions.md`；九本账的行格式和字段必填规则，在 `03-ledgers.md`；`bin/rl` 每条子命令的完整参数和退出码，在 `05-rl-cli.md`；钩子、角色 json 的四栏机制和机器检查，在 `06-hooks-and-permissions.md`；快车道，在 `07-quick-lane.md`；gyb 自己做的事和 `rl status`，在 `01-gyb.md`；公共母版和 feedback 账，在 `09-common-and-feedback.md`。idea 和别的角色来回的细节分别在 `20-pair-idea-deploy.md`、`22-pair-idea-analysis.md`、`25-pair-reviewer-idea.md`。
> 源：设计文档的「gyb 自己做的事」「五个角色」总段、「idea」一节、「账本」一节的决定账部分、「交接与会话生命周期」；施工计划第一节裁决 3、第二节词表、第三节 decisions 与 handoffs、第四节转移表、第五节 idea 的 use case 与角色 json、第六节命令表。

## idea 干什么

idea 和 gyb 谈想法，谈定的东西写进 idea 的决定账。gyb 会参与到影响实验结果的工程细节里，这些细节同样写进决定账，reviewer 的审查基准只有这些 gyb 定下的决定。gyb 在场定的那一版和 idea 自决的那一版，账上要分得出来。

idea 把决定拆成工单派给 deploy，也可以给 analysis 开分析单。idea 是这两种单子的 owner：单子从开到关归它，它负责拉起下游、验收、收回。

有三件事 idea 不做。文献变成想法由 gyb 亲自做，idea 没有 gyb 的允许连 notes/ 都不读。分析什么、画什么图由 gyb 亲自说，idea 不替 gyb 主张要看什么数。写代码不归 idea，idea 的角色 json 里 writes 一栏是空的，一个目录都不能 Write 或 Edit。

## use case 表

施工计划第五节给的 idea use case 和它点名的动作，一条一行：

| use case | 源文档点名的动作 |
|---|---|
| 和 gyb 谈定决定并落账 | `decision add`/`update`/`confirm`/`retire`/`merge`，替 gyb 记时带 quote |
| 开工单和分析单 | `handoff open`，可带 `--manual`、`--no-dispatch` |
| 后台起 deploy 或 analysis subagent，并在它回来时验收或打回 | `handoff accept`/`reject` |
| 决定改版后重派 | `handoff reissue` |
| 收回 | `handoff withdraw` |
| 重新拉起下游 | 源文档没给命令 |
| 申请读 notes/ | `issue open --kind request --to gyb` |
| 回下游的 issue 并把单子交回待干 | `issue reply`、`handoff resume` |
| 读 reviewer 清单 | 只用查询命令 |

角色 json 的四栏是这张表的并集，model 另记。写 SKILL.md 的时候，每个 use case 底下还要写清读哪些账和目录、写哪个目录、调哪些 rl 写命令（原则 5），源文档只给了并集，没有逐条拆开。

## 读什么、写什么、能调哪些命令

| 栏 | 内容 |
|---|---|
| reads | 九本账全部、`notes/`（要 grant）、`analysis/`、`experiments/` 下的部署报告目录、`review/` |
| writes | 无目录 |
| ledger_writes | decisions.idea 全部；handoffs 的 open、accept、reject、withdraw、release、reissue、resume、amend；issues 的 open、reply、reassign、close；feedback add |
| dispatches_to | deploy、analysis |
| model | 由 agent 调用时 fable，gyb 手动加载时跟当前会话的模型一致 |

读一律不设权：九本账的查询命令谁都能调，reads 这一栏是纪律不是门禁。查询命令（show、list、trace、status、inbox、stale、doctor）不进 ledger_writes；`rl doctor --ack`、`--unack` 是写命令、只有 gyb 能敲（2026-08-17 gyb 裁，sync-inbox 问题 23）。机器检查只查 SKILL.md 正文出现的每条 rl 写命令在不在 ledger_writes 里，查询命令不查。SKILL.md 不抄公共母版的条文，只写一句「按 common/ 执行」，测试同样查抄没抄。

## 收件箱

`rl inbox` 谁需要谁敲，不是上线动作：角色被拉起不自动查收件箱，先干拉它起来的那张单。inbox 列本角色名下 open 的 issue、owner 是本角色而 holder 为空的单子、本会话手上单子引的过版决定、发给本角色的通知、本角色提的 feedback 的裁决。

两处原文不一致：过版那一项，设计文档写的是「本角色持有或拥有的单子里过版的决定引用」，施工计划第六节写的是「本会话手上单子引的过版决定」；feedback 裁决那一项，设计文档把它算进通知里，施工计划单列成一项。这份按施工计划的表走。

`rl decision stale` 默认也只列和本会话手上单子有关的，要全库才加 `--all`。

## 决定怎么落账

### 来源三类

每条决定必须带来源。来源是一个列表，每一项是三类之一：

| 类 | 内容 |
|---|---|
| `decision` | 旧决定的编号加版本 |
| `file` | 仓库里的文件路径，可以是任何仓库内路径，可选一个锚点指到小节或行号区间 |
| `run` | runs 账里的一个 run_id |

三类可以混着放，至少一项，空列表入账脚本拒收。file 类举得出来的例子是 notes/ 里 gyb 的调查报告、analysis/ 里的图和 notebook、experiments/ 里的部署报告、review/ 里的清单、experiments/ 里的代码文件。

不设「口头」这一类来源，每条决定都要能追到一个文件或一个数字。一条决定链的第一条决定，来源指现有代码文件或 notes/ 里的一行，两样都没有就先让 gyb 在 notes/ 写一行。

跑完实验才知道的结论就是这么进账的：来源指那次跑的 run_id 和 analysis 的图，成为原决定的新一版或者一条新决定。

### 新一版还是新一条

改的是同一个问题的答案——同一件事换个做法、换个参数、停掉——就追加一版。换了要回答的问题就开新条。跨角色改别人的决定一律在自己那本开新条，来源指原决定的编号加版本。

追加一版的时候来源默认继承上一版，`update`、`confirm`、`retire`、`merge` 不给 `--source` 就继承。

看过一批结果之后确认「继续、设定不变」也要留痕：`rl decision confirm` 追加一版正文不变、只加来源。

废除等于追加一版标 retired，来源默认继承上一版，停一条方向的时候鼓励再加上那次 run 和那张图。两个旧决定可以合成一个新决定：新决定拿新编号，来源列表自动含全部被合并的旧决定，旧的各追加一版标 retired，合并时用 `--root` 指定保留哪个根。

每条决定记根决定：新开的决定根是自己，追加一版继承。`rl status --group-by line` 按根决定切开看，两条研究线并行时用它。

### 谁定的那一版

账行上的 actor 记的是身份，不是会话。gyb 在场定的那一版 actor 是 gyb 并且带 quote，idea 自决的那一版 actor 是 idea、不带 quote。

rl 只认会话不认手指。裸终端发出的命令 actor 就是 gyb，session_id 记 `cli`，gyb 直接写的决定落 `decisions.gyb.jsonl`，这个文件只收裸终端写的行。idea 会话里替 gyb 记的决定落 `decisions.idea.jsonl`，actor 记 gyb，带 `--quote`，不论键盘前面坐的是谁都要带，缺了 rl 拒收。这个 quote 是留给 reviewer 的痕迹。

reviewer 的审查基准是「actor 是 gyb 或 idea 的决定行」，不看落在哪个文件里。

### 改版之后

决定改版或废除的那一刻，rl 当场列出引着旧版而没到终态的单子和它们的 holder。

决定改了一版不影响已经派出去的单子：单子按派出时引的那一版继续做，rl 只标过时，不自动打回、不自动标待复核、不自动停。停不停由 gyb 点名，停就用收回；改版之后要重派的用 `rl handoff reissue`。

引用记的版本比账里最新一个非 `confirm` 版小才算过时（`confirm` 版不算改版，2026-08-18 gyb 裁，定义处 `02-decisions.md`），查询命令当场标出「上层依据已从第 2 版更新到第 3 版，复核这条还成不成立」。过版的单子进 `rl status` 和相关角色的 `rl inbox`。retired 决定名下还有活单的进 `rl status` 和 doctor。

## 工单怎么开

工单是 `work_order`，idea 开给 deploy，owner 就是 idea。开单时落 `todo`。

单子上必填 `decision_refs`（每项是编号加版本，至少一项）和 `explanation`。工单里不能只甩决定编号，还要附一段 idea 自己写的解释，把那条决定里的东西讲明白，解释权在 idea。怎么测试、什么算成功，也要 idea 自己想明白，只是不预写成单子上的字段。

派发方式三档：

| dispatch | 意思 | 开单时怎么写 |
|---|---|---|
| `auto` | owner 后台起 subagent | 默认 |
| `manual` | gyb 亲自接，owner 不起 subagent | `--manual` |
| `none` | 暂不派，停在 `todo` 等 gyb 说开跑 | `--no-dispatch` |

`auto` 是后台起 subagent 接走，上游会话继续可用，subagent 回来时上游验收；上游会话先结束了，单子照常在账上等 owner 下次上线或 gyb 验收。下游 subagent 没走到交活或卡住就返回的（报错、上下文满），idea 当场 `rl handoff release` 交回待干，并决定重起还是开 issue 给 gyb。

开单的时候不查交付物，只查「单子说得清自己是什么」。

## 分析单怎么开

分析单是 `analysis_order`，idea 或 gyb 开给 analysis。单子上带 `evaluation_refs`，每项是口径编号加版本。开单时引的口径可以还是 `proposed`，交活的时候必须全部 `approved`。`parent_id` 对分析单是可选的。

单个 run 的原始指标 idea 可以直接从 runs 账念给 gyb 听。任何跨 run 的对比、聚合、画图一律走 analysis 的分析单和口径账。

口径本身不是 idea 写的：口径账每一行都是 gyb 说、analysis 记、gyb 批，idea 不许自己写新的要分析的东西。

## 怎么验收和打回

验收不预写标准，验收产物是部署报告。要验的是「代码和想法是不是一回事」，这个判断在代码写出来之前写不成条目。

deploy 提「干完等待验收」必须附报告路径，路径为空入账脚本不收这个状态。工单的交付物是两份部署报告的路径加代码路径清单，分析单的交付物是 notebook 和图的路径加口径全部 approved，三样都是「路径存在或行存在」这种机器可查的前提。

验收人是 owner，也就是 idea。先读不带文件的那一份看做法对不对，再读带文件的那一份看写出来的东西和说的是不是一回事。打回要写明原因，`reason` 为空入账脚本不收。打回之后单子回待干，由 idea 重新拉起下游。

gyb 随时可以自己验。gyb 越过 owner 验收或打回时，rl 给 owner 发一条 `fyi` 通知，idea 下次 `rl inbox` 看得到。

验收一张单子时，它关联的已回复 issue 自动关。

## 收回、重派、拉起

收回是对派出去还没干完的单子追加一版标 `withdrawn`，单子关闭，这是终态。收回要带原因，角色会话里发起还要带 gyb 原话。从 `in_progress` 收回时，rl 顺带开一条 `withdrawn` 通知给 holder 的角色和 owner，其他状态不通知。带 `--cascade` 时，rl 代 owner 连它派生的下游单子一起收，下游单的账行 actor 记发起人。

改版之后要重派的用 `rl handoff reissue ID --decision ID@V`：一条命令收旧单（`withdrawn`，级联）、开新单（继承 `explanation`、`parent_id`、`batch`，`supersedes` 指旧单）、通知全部 holder。

工单被打回、被回收、下游销号之后回到待干，都由 idea 重新拉起下游。owner 是角色不是会话，idea 当下没有活着的会话时，单子由 gyb 拉起，`rl status` 单列这一类。

下游卡住的时候，idea 回 issue，再用 `rl handoff resume` 把单子交回待干；`resume` 的前提是关联 issue 状态已经是 `answered`。交回待干之后 `to_role` 的任何一个会话都能接，默认还是 idea 再起一个下游。

## 申请读 notes/

notes/ 只有 gyb 写，谁都能读，但 idea 要经 gyb 允许才有读文献的权限。

`rl init` 的时候问 gyb 一次要不要当场给 idea 发 `read:notes`。发了就不再走申请。没发的话 idea 开一条 issue 给 gyb，kind 是 `request`；gyb 在裸终端写一条 grant，idea 之后才读 notes/。授权只有 gyb 能写：裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收。

读权不上钩子，grant 是给 reviewer 事后查的凭据。doctor 有一项扫描：决定的来源指向 notes/ 但 grants 里查不到这个 actor 的 `read:notes`。

## 模型

idea 由 agent（subagent 或 workflow）调用的时候用 fable，gyb 手动加载的时候跟当前会话的模型一致。角色 json 的 `model` 两个取值分开写，`manual` 写 `inherit` 是声明跟当前会话走，sessions 账落解析后的真实模型名或 `unknown`。

idea 用 fable 与本机 `~/.claude/CLAUDE.md` 的「subagent 默认不用 Fable」不一致，按原则 8 工程内为准：这条裁决就是 gyb 点名的那一次例外。插件的 README 和角色 json 里都要明写「fable 是 gyb 2026-08-16 点名的例外」。

## 和别的 part 的接口

- 派活单的七个状态、状态转移表的六栏、holder 只在 `in_progress` 非空这条不变量：`04-handoffs-and-sessions.md`。
- handoffs 的字段（`work_type`、`from_role`、`to_role`、`parent_id`、`supersedes`、`batch`、`line`、`dispatch`、`decision_refs`、`evaluation_refs`、`explanation`、`report_paths`、`code_paths`、`output_paths`、`progress_note`、`reason`）：`03-ledgers.md`。
- decisions 的字段（`id` 前缀、`root_id`、`status`、`sources` 三类的写法、`quote`、`merged_from`）和 `decisions.gyb.jsonl` 只收 `cli` 这条：`03-ledgers.md`。
- issues 的九种 kind、三个状态、reply 和 close 谁能写、通知类 issue 由收件人做完了自己 close：`03-ledgers.md`。
- `rl decision add/update/confirm/retire/merge/show/list/stale`、`rl handoff open/accept/reject/withdraw/release/reissue/resume/amend`、`rl issue open/reply/reassign/close`、`rl inbox`、`rl trace` 的完整参数与退出码：`05-rl-cli.md`。
- actor 判定、`--as-gyb`、`--quote`、`--force --reason`、裸终端 session_id 记 `cli`：`01-gyb.md` 和 `05-rl-cli.md`。
- `rl status` 的十段、哪几段推送桌面通知、`fyi` 通知：`01-gyb.md`。
- 角色 json 的五样、`tests/test_skill_refs.py` 的机器检查范围、钩子只挂 Write 和 Edit：`06-hooks-and-permissions.md`。
- 两份部署报告的分工和 `code_paths` 由谁填：`11-role-deploy.md` 和 `20-pair-idea-deploy.md`。
- 口径账的两种 kind、四个状态、谁提谁批：`13-role-analysis.md` 和 `22-pair-idea-analysis.md`。
- reviewer 清单的文件名和五栏：`14-role-reviewer.md` 和 `25-pair-reviewer-idea.md`。
- feedback 账、公共母版 `rules_version`：`09-common-and-feedback.md`。
- 快车道补单的 explanation 由 deploy 写、验收人固定 gyb：`07-quick-lane.md`。
- `rl init` 时问 gyb 要不要给 idea 发 `read:notes`、grants 账的字段：`08-trees-init-and-host.md` 和 `01-gyb.md`。

## 源文档没写清的（留给 gyb）

1. idea 的 ledger_writes 里有 `handoffs 的 release` 和 `handoffs 的 amend`，但 use case 表里没有哪一条点名用它们。按原则 5 权限从动作倒推，这两条要么补进 use case 表，要么从 json 里去掉。
2. use case 表里「重新拉起下游」没有对应命令。拉起下游到底是 rl 的一个动作还是 SKILL.md 里的一句纪律（直接起 subagent），源文档没写。
3. 「怎么测试、什么算成功，也要 idea 自己想明白，只是不预写成单子上的字段」——那它落在哪里没写：写进 `explanation` 里，还是只在起 subagent 的提示里说，还是不落盘。
4. `explanation` 要写多长、写哪几样，只有「把那条决定里的东西讲明白」这一句。
5. 一张工单可以引多条决定，`line` 由 rl 从 `decision_refs` 第一项的 `root_id` 算出来。引的多条决定分属两个不同根决定时，`line` 怎么算、允不允许这么开单，源文档没写。
6. idea 验收工单时要不要读 `code_paths` 里的代码本身、读到什么程度，源文档只说读两份报告。
7. idea 读 review/ 的清单之后该做什么动作没写：是开一条新决定、给旧决定追加一版、还是打回某张单子。
8. idea 开给 gyb 的 `request` issue 谁来 close 没写死。「验收一张单子时它关联的已回复 issue 自动关」这条对 request issue 不适用，它不挂在任何单子上。
9. idea 开完 `--to gyb` 的 issue 之后、等 gyb 回话的这段时间，会话该干什么、该不该销号、销号之后谁把 idea 重新叫起来，源文档没写。idea 是最上游，手上没有派活单，转移表里的 stuck 只有 holder 能写，对 idea 不适用。
10. `dispatch=auto` 的「后台起 subagent」具体怎么起没写：插件树里没有 workflows/ 或 agents/ 这一层，subagent 里加载角色 skill 钩子装不装得上、后台 subagent 能不能跑几个小时都还挂在待验证清单第 8、9 条上。
11. `--manual` 的单子由 gyb 接，owner 仍是 idea。gyb 接完之后由谁验收，转移表写的是 owner，设计文档写的是 gyb 随时可以自己验，这一种单子上两句话叠在一起没有裁过。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

以下条目从 `plans/2026-08-16-research-loop-simulation-round2.md` 原样抄来，保留场景名、序号、严重度、kind、原文、依据、改法，没有核实，也没有做判断。

### param-tweak（45 步，gyb 动手 8 次）

8. [slows/contradiction] 第 27 步：设计文档说替 gyb 打 --as-gyb 带 --quote「靠纪律，钩子不拦」，施工计划和测试 9 说缺 quote 退出码 2 硬拒收；更麻烦的是 gyb 本人和模型在同一个角色会话里打命令，rl 读的是同一个会话状态文件，分不出是谁打的，硬拒收就连 gyb 自己验收都要造一句原话
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：定成硬拒收并只留一个值：gyb 本人在角色会话里用 --as-gyb --by-hand 免 quote，模型用一律要 quote
10. [slows/contradiction] 第 10 步：决定的 add 还是 update 判据说「同一件事换个参数就追加一版」，但 rl decision update 只有同一个 actor 能调；原来的学习率写在 decisions.idea 或 decisions.gyb 里，deploy 追不了那一版，只能在自己那本开新条，判据就落空了
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:128
   - 改法：判据补一句「跨角色改参数一律在自己那本开新条，来源指原决定的编号加版本」
17. [cosmetic/contradiction] 第 4 步：设计文档说 SKILL.md 正文出现的每条 rl 子命令都要在角色 json 的 ledger_writes 里，施工计划的测试 13 只查写命令；deploy 上线要跑的 rl decision stale、rl handoff show 都是查询命令，不在 deploy 的 ledger_writes 里，按设计文档那句机器检查就红
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:215; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：把设计文档那一句改成「每条 rl 写命令」，或角色 json 加一栏 queries 单列查询命令
18. [cosmetic/missing] 第 26 步：work_order 的 explanation 定义成「idea 自己写的解释」且是必填，快车道全程没有 idea 会话，这段解释谁写、写什么没写
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:48
   - 改法：补一句：快车道补单的 explanation 由 deploy 写，注明来自 gyb 口头点名并抄一句原话

### new-idea（39 步，gyb 动手 7 次）

1. [blocks/blocked] 第 8 步：新想法是 gyb 在聊天里当场说出来的，没有旧决定、没有 run_id、没有 analysis 产物，可来源必须至少一项且只有 decision/file/run 三类、明文写着「不设口头这一类」，file 类路径不存在还会被拒收；这条决定链的第一条决定入不了账，后面工单、发射单、runs 全部挂不上
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:205
   - 改法：明写「一条决定链的首条决定可以拿现有代码文件路径或 notes/ 里 gyb 的报告当来源，两者都没有时硬停并要求 gyb 先写一行 notes/」
4. [blocks/too_heavy] 第 10 步和第 19 步：接单默认是同步的，deploy 等 run 几个小时、idea 又等 deploy，于是 gyb 手动加载的 idea 会话从派单那一刻起被整场实验占住，gyb 想看进度只能另开终端；待验证第 9 条的失败备案只写了 deploy→run 这一层改成开单即销号，idea→deploy 这一层没有备案
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：明写 gyb 手动加载的角色会话一律不同步等下游，开完单即返回，验收由下一次会话或 gyb 在 rl status 里做
5. [slows/contradiction] 第 8 步：设计文档说 gyb 亲自打 --as-gyb 的落 decisions.gyb.jsonl、idea 替 gyb 记的落 decisions.idea.jsonl 并带 quote，可角色会话里的命令全是模型打的，而施工计划规定模型打 --as-gyb 必须带 quote、账行 actor 记 gyb，决定文件又按 actor 拆名，同一条命令按两份文档会落进两个不同文件
   - 依据：plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:29; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：明写「decisions.gyb.jsonl 只收裸终端写的行，角色会话里模型打的 --as-gyb 一律落 decisions.<角色>.jsonl 并记 quote」
9. [slows/too_heavy] 整条路：「探针输入从最后一层换成中间层」这一句话的改动，正常路要走 2 张派活单、3 个嵌套会话、2 份部署报告、至少 9 次 rl 写账，和「想法要快速、多次迭代」这条总目标对不上；唯一的减负出口快车道每次都要 gyb 当场点名
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给 work_order 加一个 --light 档只要一份 detail 报告，或者明写「同一条决定的第二次及以后的参数微调默认走快车道」
12. [slows/ambiguous] 第 37 步：「拿到数字给 gyb 看」两种读法都成立：idea 读九本账全部，可以直接 rl run show 把 metrics 念给 gyb；可另一处写着任何角色不许自己写新的要分析的东西、要看什么 gyb 一条条说由 analysis 记账批准，照抄一个原始指标算不算分析没有界
   - 依据：plans/2026-08-16-research-loop-next-steps.md:52; plans/2026-08-16-research-loop-next-steps.md:30; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：明写「照抄 runs 账 metrics 里的原始数不算分析，任何对比、聚合、画图都要走口径账」

### result-wrong-review（25 步，gyb 动手 11 次）

5. [blocks/missing] 第 19 步（gyb 若当场废掉或改 dec-idea-0007 而不是让 idea 改）：gyb 给别人的决定追加一版落哪个文件没写：设计文档说 gyb 写的决定落 decisions.gyb.jsonl，又说决定账按 actor 拆六个文件、编号带角色前缀，那 dec-idea-0007 的第 3 版由 gyb 写就会和第 1、2 版分居两个文件，「默认查询只取最新版」和锁里的扫号都要跨文件才对，入账脚本没有依据。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-next-steps.md:96; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:128
   - 改法：明写「决定行按 id 前缀落文件，谁写的记在 actor 字段」，dec-gyb 前缀只给 gyb 新开的决定。
10. [slows/ambiguous] 第 23 步：决定来源 file 类允不允许指 review/ 里的清单两种读法都通：设计文档举例只有 notes/ 里 gyb 的调查报告和 analysis/ 里的图与 notebook，测试 3 却只检查路径存不存在。审出问题之后更新决定，最自然的来源就是那份清单，入账脚本按哪种写会决定它收不收。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:205; plans/2026-08-16-research-loop-build-plan.md:57
   - 改法：设计文档第 46 行明写 file 类是仓库内任意路径，举例补上 review/ 的清单和 experiments/ 的部署报告。
11. [slows/missing] 第 8 步到第 15 步：reviewer 的审查基准只有决定账、不猜 gyb 的意思，可 gyb 起疑的正是「当初谈定的东西和代码不是一回事」，谈定却没被 idea 记进决定账的那部分 reviewer 审不出来，也没有任何一栏让它报告「代码里做了选择但决定账里没有对应行」。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:84
   - 改法：清单四栏加第五栏「决定账里没写但代码里做了的选择」，让 reviewer 把账的空白也报出来。

### plot-new-plan（17 步，gyb 动手 8 次）

1. [blocks/contradiction] 第 7 到第 10 步（提口径与开分析单的先后）：转移表规定 analysis_order 新建落 todo 的前提是 evaluation_refs 每项已 approved，但 analysis 的 use case 表把「接分析单」排在「问 gyb 要统计什么并提口径」前面，设计文档也写 analysis 先接单再问 gyb；一个全新的画图计划手上没有任何 approved 口径，照 use case 的顺序开单会被入账校验拒收，照转移表的顺序又要在没有单子的情况下先干活。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-build-plan.md:107; plans/2026-08-16-research-loop-next-steps.md:76; plans/2026-08-16-research-loop-next-steps.md:50
   - 改法：在设计文档 analysis 一节明写新计划的顺序是先开 analysis 会话过口径、口径 approved 之后再开分析单，或者改成分析单可以引 proposed 口径、到 handoff done 时才校验已 approved。
10. [slows/ambiguous] 第 10 步（分析单的 from_role）：owner 被定义成开单角色也就是 from_role，而角色只有五个、gyb 不在角色表里；设计文档和词表都说 gyb 可以开分析单，但 handoffs 的 from_role 能不能填 gyb、gyb 算不算合法 owner 没有明写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:41; plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：在第三节 handoffs 的 from_role 字段写清取值是五个角色或 gyb，并说明 owner 是 gyb 时验收和拉起下游都由 gyb 做。

### next-plan-after-results（36 步，gyb 动手 16 次）

2. [blocks/blocked] 第 11 到 15 步：analysis_order 新建的前提是 evaluation_refs 每项已 approved，但口径是 analysis 接单之后才提的（角色 json 的 use case 顺序是「接分析单 → 提口径」）。一批新结果第一次要新指标时，单子和口径互为前提；只能靠「gyb 直接开一个没有单子的 analysis 会话先提口径」绕过，而文档从没描述过没有单子的 analysis 会话该怎么交付 notebook 和图
   - 依据：2026-08-16-research-loop-build-plan.md:81; 2026-08-16-research-loop-build-plan.md:107; 2026-08-16-research-loop-next-steps.md:76; 2026-08-16-research-loop-next-steps.md:80
   - 改法：允许 analysis_order 引 proposed 口径开单、批准落在 done 之前，或明写「先谈口径后开单」并给无单分析会话一个交付落点
6. [slows/ambiguous] 第 26 步：讨论里定下的结论落 decisions.gyb 还是落 decisions.idea 带 quote，判据是「gyb 亲自打的」还是「idea 替 gyb 记的」。可是在手动加载角色的会话里 rl 命令都是模型敲的，「gyb 亲自打」这条路实际只存在于另开裸终端，同一条结论两处都说得通，reviewer 的基准会散在两本账里
   - 依据：2026-08-16-research-loop-next-steps.md:34; 2026-08-16-research-loop-next-steps.md:44; 2026-08-16-research-loop-build-plan.md:121
   - 改法：定死「角色会话里一律落角色那本账带 quote，decisions.gyb 只收裸终端写的」，把判据从「谁亲手敲」换成「哪个会话」
7. [slows/missing] 第 33 步：「这条方向看完结果继续做、设定不变」这一支没有落点。决定不换做法就不追加版、不换问题就不开新条，账上留不下 gyb 看过这批数字并确认继续的痕迹，下一轮 reviewer 和 `rl decision stale` 都看不到这次复核
   - 依据：2026-08-16-research-loop-next-steps.md:46; 2026-08-16-research-loop-next-steps.md:109
   - 改法：加一条 `rl decision confirm ID --source run:... --source file:...`，追加一版正文不变、只增来源
8. [slows/missing] 第 27、36 步：决定 retire 之后，引用它的在办单子没人扫。doctor 的八项扫描和 rl status 的七段都没有「retired 决定名下还有没到终态的单子」这一项，设计文档又把停不停全交给 gyb 点名，忘了收回就一直挂着
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:112
   - 改法：doctor 和 status 各加一项「retired 决定名下还有活单」，附上 `rl handoff withdraw --cascade` 的修法
9. [slows/missing] 第 27 步：`--cascade` 收回下游单子的写入人是上游单的 owner（idea），可发射单的 owner 是 deploy，转移表 withdrawn 那一行「谁能写」只写了 owner，没给级联收回开口子
   - 依据：2026-08-16-research-loop-build-plan.md:92; 2026-08-16-research-loop-next-steps.md:124
   - 改法：转移表 withdrawn 那一行加一句「级联收回时上游单的 owner 可写下游单」，账行记清是级联触发的
10. [slows/ambiguous] 第 31 步：开完工单要不要立刻起 deploy subagent。设计文档说默认上游开完单直接起 subagent 同步等它回来，本场景 gyb 只想定计划不想现在开跑，文档没有「开单但暂不派」的默认，gyb 不当场喊停就会被带进几小时的实施
   - 依据：2026-08-16-research-loop-next-steps.md:120; 2026-08-16-research-loop-next-steps.md:48
   - 改法：`rl handoff open` 加 `--no-dispatch`，SKILL.md 写明 gyb 没说开跑就停在 todo

### n-launch-orders（58 步，gyb 动手 10 次）

15. [slows/ambiguous] 第 48 步：跨 run 的聚合数算谁的活，两种读法都说得通。一种读法：idea 读九本账全部，runs 账的 metrics 就在里面，自己把 5 个数平均一下没人拦。另一种读法：规矩 5 说派生量只用 approved 的口径、由 analysis 算，均值方差正是派生量，idea 自己算就是自作主张。
   - 依据：2026-08-16-research-loop-next-steps.md:52; 2026-08-16-research-loop-next-steps.md:30; 2026-08-16-research-loop-build-plan.md:249
   - 改法：明写一句：单个 run 的 metrics idea 可以直接引，任何跨 run 的聚合一律走 analysis 分析单。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

5. [slows/contradiction] 第 10、11 步：转移表「谁能写」栏（build-plan.md:92）规定收回只有 owner 能写，而 next-steps.md:124 的 `--cascade` 要求 owner 一条命令连下游单一起收，下游单的 owner 是另一个角色（本场景 idea 收 deploy 的发射单）。两句同时成立就等于 owner 能越过另一个 owner 写单子。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：明写 cascade 是 rl 代 owner 连锁收回、被收的下游单 actor 记发起人并自动给下游 owner 开一条 issue，或者干脆只允许 gyb 用 --cascade。
6. [slows/missing] 第 7 步：文档只在两个时机查过版：「角色上线第一个动作跑过版检查」（next-steps.md:111）和 `rl status`（next-steps.md:124）。决定改版的那一刻，`rl decision update`（build-plan.md:128）不输出任何「有 N 张在办单子引着旧版」的提示。本场景是我按原则 6 让 idea 主动再跑一次 `rl decision stale`，文档没有这条规矩；idea 不跑就没人发现。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-build-plan.md:128; plans/2026-08-16-research-loop-build-plan.md:131
   - 改法：`rl decision update` 和 `retire` 写完那一刻当场列出引旧版且未到终态的单子，并把它们的 holder 会话一起打印出来。
9. [slows/ambiguous] 第 6 步：来源三类不含口头（next-steps.md:46），可是「换个评测集」这种 gyb 当场改主意既没有新文件也没有新 run_id，只能靠 update 默认继承上一版的来源（build-plan.md:57）。于是账上「有新证据的改版」和「临时改主意」长得一模一样，两种读法都说得通：一种是继承就算合规，一种是必须先去 notes/ 落一行再改。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:57
   - 改法：决定行加一个 `change_reason` 枚举（新证据 / gyb 口头改），口头那档必须同时带 quote，来源仍继承。
10. [slows/missing] 第 10 步：公共规矩第 1 条（build-plan.md:245）要求不可逆动作要有 gyb 当场的原话，收回是终态、不可逆，可是 `rl handoff withdraw ID [--cascade]`（build-plan.md:134）没有 `--quote` 参数，handoffs 行格式（build-plan.md:61）也没有 quote 字段，gyb 那句「停」没有落点。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:245; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：withdraw 和 reject 都加 `--quote`，handoffs 行加 quote 字段，角色会话发起时缺 quote 就报错。
12. [slows/missing] 第 19 步：转到 `withdrawn` 那一行的「之后谁拉起」栏写「无」（build-plan.md:92），收回只给 holder 的角色开 issue，不给 owner 任何东西。S-idea1 从同步等待里醒来，发现自己开的 ho-0012 已经被收回，下一步该干什么文档没写，它是接着开新单还是销号只能自己猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：收回时给 owner 角色也开一条 issue（kind 复用 withdrawn），转移表第五栏写明 owner 醒来后要么重开单要么销号。
16. [slows/too_heavy] 第 6 到 22 步整段：「换个评测集」这一件事走了 23 步、gyb 亲自动手 8 次、牵动 4 个会话，其中 5 步是纯手续（分两次收单、两个会话销不掉号、手动关两条通知 issue、按新版本重开一张内容几乎相同的工单）。目标那一节写的是「想法要快速、多次迭代」（next-steps.md:7），这条路上没有任何一条把「决定改版后重派」压成一步的捷径。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：加一条 `rl handoff reissue ho-XXXX --decision ID@V`：一条命令连锁收旧单、清 holder、继承 explanation 开新单，并通知全部 holder。
17. [cosmetic/missing] 第 21 步：重开的 ho-0014 和被收回的 ho-0012 之间没有任何字段能看出是同一件事的第二次派发（handoffs 行格式 build-plan.md:61 里没有 supersedes 之类的栏），`rl status` 和 `rl handoff list --decision` 都只会把它们并排列成两张单。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：handoff open 加 `--supersedes ho-XXXX`，写进单子并在 status 里归成一组。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

2. [blocks/missing] 第 1 步：没有任何办法表达「这张单 gyb 手动接，别起 subagent」：rl handoff open 没有这个旗子，handoffs 行里没有这个字段，idea 的默认动作是开完单直接起 deploy subagent 并同步等。gyb 的口头交代不进账，idea 会话一旦重开或被 reclaim，idea 还会按 owner 职责再拉起一个下游，两个会话抢着打 rl handoff start，晚的那个撞上「表外转移一律拒收」拿退出码 2。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:83; plans/2026-08-16-research-loop-build-plan.md:95
   - 改法：给 handoffs 加一个 dispatch 字段（auto / manual），rl handoff open 带 --manual 时 owner 不起 subagent、rl status 单列这类单子。
11. [slows/missing] 第 26 步：gyb 越过 owner 直接验收之后，没有任何通道把这件事告诉 owner idea。转移表 done_pending_review→accepted 那一行第五栏是「无」，issues 账只在改派给 gyb 时发通知，rl status 是给 gyb 的收件箱不是给角色的。idea 会话下次上线只会看到单子已经是终态，不知道是谁验的、为什么验过。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:88; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:20
   - 改法：gyb 代 owner 写终态转移时，rl 自动给 owner 角色开一条 kind=not_mine 之外的新 kind（比如 fyi）的 issue，或者在角色上线时和 decision stale 一起报一句「你名下的单子被 gyb 处理过」。
12. [slows/missing] 第 6 步：取一条决定的指定版本没有命令。rl decision show 只有默认最新版和 --history 全量两档，可单子按派出时引的那一版继续做，deploy 要的就是 dec-idea-0007 第 2 版；只能把全部历史拉进上下文再自己挑，和读法纪律「挑最小的读法、大文件禁止整读」直接顶上。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-next-steps.md:144
   - 改法：rl decision show 加一个 --version V 参数，handoff show 里显示 decision_refs 时顺带把那一版正文带出来。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

2. [blocks/missing] 第 3、4 步：「根决定」这个归组键没有定义。设计文档说 status 可按根决定归组、施工计划写 --group-by decision，但 decisions 行上只有 sources 没有 parent 或 root 字段；两个旧决定合并成新决定之后一条决定有多个被合并的旧编号，往上走根不唯一。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-next-steps.md:110
   - 改法：要么给 decisions 加一个显式 root_id（merge 时指定保留哪个根），要么把 --group-by decision 定义成「按单子上直接引的决定编号分组」并在文档里写死这一句。
8. [blocks/missing] 第 13 步：owner 是角色不是会话，owner 角色没有活着的会话时谁把它叫醒没写。原则 3 和交接一节四处都写「回到待干、由 owner 重新拉起下游」，本场景蒸馏线的 deploy 会话已销号，账上只剩一张 todo 单子和一个不存在的 owner。按原则 1 只能推出 gyb 有权自己干，推不出系统怎么提醒他该开哪个角色的会话。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:93
   - 改法：rl status 单列一段「等 gyb 拉起」：owner 角色没有活会话的 todo 单子，每行附上该开哪个角色会话的那条命令。
11. [slows/too_heavy] 第 15、18 步：角色上线第一个动作 rl decision stale 没有范围参数，列的是全库过版的单子和决定。两条线并行时，蒸馏线的 deploy 一上线就把探针线的过版项读进上下文，和读法纪律「读进来的每个字都留在上下文里挤占后面的判断、只读自己需要的那部分」直接顶。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-next-steps.md:144
   - 改法：rl decision stale 加 --mine 和 --handoff 两个过滤，角色上线默认只查本会话要接的那张单子相关的决定。

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
5. [slows/missing] 第 6 步之后到第 8 步之间：idea 开完 --to gyb 的 request issue 之后，等回话期间会话该干什么没写。idea 手上没有派活单，转移表里的 stuck 只有 holder 能写、对 idea 不适用；gyb 要是走开了，idea 会话要么空转要么销号，而销号之后没有任何机制重新拉起 idea——原则 3 只管有 owner 的单子，idea 是最上游、只由 gyb 在终端手动 / 加载
   - 依据：plans/2026-08-16-research-loop-build-plan.md:84; plans/2026-08-16-research-loop-next-steps.md:117; plans/2026-08-16-research-loop-next-steps.md:154
   - 改法：idea 的 SKILL.md 纪律栏写死：开完 --to gyb 的 issue 立即把待办交回 gyb 并结束本轮，gyb 下次开 idea 会话时用 `rl issue list --to gyb` 捡起来接着走
6. [slows/too_heavy] 第 6 步到第 11 步整段：gyb 就坐在这个会话里说了句「你去读吧」，为了读一份 md 却要走 issue open、通知、grant add、issue reply、issue close 五个动作四行账。permission 第一版只有 read:notes 一种、grantee 是角色不是会话，所以批一次就永久覆盖整个 notes/，这套手续一辈子只有第一次有信息量，和「想法要快速、多次迭代」这条总目标对不上
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-build-plan.md:65
   - 改法：`rl init` 时问一次 gyb 要不要当场给 idea 发 read:notes，发了以后就不用走申请，没发才走 issue 那条路
7. [slows/missing] 第 12 步和第 14 步：file 类来源只有 path 一个字段。一份几十页的文献调查整份当来源，reviewer 拿决定账当唯一审查基准的时候，定位不到是报告里哪一句支撑这条决定，核不动「代码和决定是不是一回事」上游的那一半
   - 依据：plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:88
   - 改法：file 类来源加一个可选的 anchor 字段（小节标题或行号区间），命令写成 `--source file:notes/x.md#<小节>`
8. [slows/missing] 第 12 步：读权不上钩子、靠纪律加 reviewer 事后查，但文档没写 reviewer 拿什么查「idea 有没有在没 grant 的时候就读了 notes/」。系统里没有读日志，doctor 的八项扫描里也没有这一类，这条纪律实际上无从核对
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:136; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl doctor` 加一项扫描「decisions 里 source 指向 notes/ 但 grants 里查不到该 actor 的 read:notes」，把这条纪律接回入账校验那一层
10. [cosmetic/missing] 第 10 步和第 11 步：issues 三个状态的写权只有一句「按第五节 ledger_writes」，谁写 reply、谁写 close 没规定；idea 的 ledger_writes 含 issues 的 open/reply/reassign/close 四个，所以 idea 自己开、自己答、自己关全过校验，和派活单那张写得很死的转移表不对称
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:79
   - 改法：第六节 issue 那一行加前提栏：reply 只有 assignee 或 gyb 能写，close 只有开单的 actor 或 gyb 能写

### hook-missed-session-end（23 步，gyb 动手 11 次）

6. [slows/guessed] 步 13、步 14：设计 L120 只写「上游开完单直接起一个 subagent 接走并同步等它回来」，没写下游 subagent 没走到 done 或 stuck 就返回的时候上游拿到什么、该做什么。待验证第 9 条（设计 L168、施工 L197）只问「等几个小时会不会被超时收掉」，不问「等的对象死了怎么办」。最快能发现这件事的就是被阻塞的上游会话，文档没给它任何职责，我只能按原则 3 推它该 release 加重起。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：设计 L120 补一句「下游 subagent 没走到 done 或 stuck 就返回的，上游当场 rl handoff release 并决定重起还是开 issue 给 gyb」，并写进 idea 和 deploy 的 SKILL.md。

## 裁决记录（日期）

- 2026-08-17 来自 sync-inbox 问题 20 的裁决（定义处 `04`，rl-hub-v3 传；gyb 原话「B」）：「收回、重派、拉起」一节「收回一张有 holder 的单子时」改成「从 `in_progress` 收回时……其他状态不通知」，跟 `04` 转移表 withdraw 那一行一致。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `03`、`05`，rl-hub-v3 传；gyb 原话「只有做完了的时候才关，巡检要我本人确认」）：「收件箱」一节通知那一项后面的「（读过即关）」删掉；接口一节「通知类 issue 被 `rl inbox` 读过即关」改成「通知类 issue 由收件人做完了自己 close」。
- 2026-08-17 来自 sync-inbox 问题 27 的裁决（定义处 `01`，`03` grants 段照它写，rl-hub-v3 传；gyb 原话「3 不是，可以替我写」）：「申请读 notes/」一节「grants 只收裸终端写的行，角色会话里替 gyb 批授权没有意义」改成「授权只有 gyb 能写：裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收」。
- 2026-08-17 来自 sync-inbox 问题 28 的裁决（定义处 `01`，rl-hub-v3 传；gyb 原话「每个角色创建时候，不要自动查收件箱」「C」）：「上线第一个动作」这一节改名叫「收件箱」，头一句改成「`rl inbox` 谁需要谁敲，不是上线动作：角色被拉起不自动查收件箱，先干拉它起来的那张单」；开头摘要那一行的「上线第一个动作 `rl inbox`」跟着改。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `05`，rl-hub-v3 传；gyb 原话见 inbox）：查询命令那句后补「`rl doctor --ack`、`--unack` 是写命令、只有 gyb 能敲」，与 `06-hooks-and-permissions.md` 同句一字不差。
- 2026-08-18 来自 `02-decisions.md` 定稿（`7549704`，rl-hub-v4 传；gyb 原话「乙」）：第五节过版判定改成「比账里最新一个非 `confirm` 版小才算过时」。对回原则 9。
