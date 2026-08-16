# reviewer 角色

> 这份覆盖 reviewer 这个角色的 SKILL.md 要写的一切：谁开它、上线做什么、读什么、按什么基准审、审哪三样、审哪一版代码、清单写成什么样、不许做什么、角色 json 的四栏和模型。
> 不覆盖的：reviewer 的清单怎么回到 idea 手上写在 `25-pair-reviewer-idea.md`；钩子和分权三层写在 `06-hooks-and-permissions.md`；九本账的行格式写在 `03-ledgers.md`；`rl` 每条子命令的参数和 `rl status` 的十段写在 `05-rl-cli.md`；会话登记与销号写在 `04-handoffs-and-sessions.md`；公共母版和反馈账写在 `09-common-and-feedback.md`；别的四个角色各在 `10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`。
> 源：设计文档的「五个角色」总段、「reviewer」一节、「gyb 自己做的事」、「账本」一节的 decisions 与 sessions、「分权与钩子」的第三层、「审读意见里没采纳的」第 5 和第 9 条；施工计划第一节裁决 3 和裁决 7、第二节词表、第五节 reviewer 的 use case 与角色 json、第八节阈值、第十三节公共规矩第 6 条。

## reviewer 是干什么的，谁把它开起来

reviewer 审查整条链有没有照定好的执行。它审的是「gyb 和 idea 层谈定的东西有没有被好好执行」。

reviewer 由 gyb 手动开。没有任何角色能派活给 reviewer：五份角色 json 的 `dispatches_to` 里没有一份指向 reviewer。审读意见里有一条「reviewer 挂在验收上自动跑」，gyb 没采纳，理由写的是「reviewer 只由 gyb 手动开」。

reviewer 审完之后动不动由 gyb 看完之后定。reviewer 自己不改任何东西。

## 上线第一个动作与 session focus

reviewer 和其余四个角色一样，上线第一个动作是 `rl inbox`。inbox 列四类东西：本角色名下 open 的 issue、owner 是本角色而 holder 为空的单子、本会话手上单子引的过版决定、发给本角色的通知（读过即关），再加本角色提的 feedback 的裁决。

reviewer 开工时 `rl session focus --decision ID` 记一下在审什么。这一行落在 sessions 账的 `focus` 字段上，`rl status` 的活着会话那一段把它带出来，gyb 因此在 reviewer 还没落盘清单的时候就看得见有人在审哪条决定。

`session focus` 这条命令在角色 json 里是 reviewer 独有的写命令，别的角色调不动。

## 审查基准：actor 是 gyb 或 idea 的决定行

reviewer 的审查基准只有决定账里 actor 是 gyb 或 idea 的行，不看这一行落在哪个文件里。

判据在 actor 这一栏，不在文件名上。设计文档的原话是：gyb 直接写的决定落 `decisions.gyb.jsonl`（这个文件只收裸终端写的行），角色会话里替 gyb 记的决定落那个角色自己那本、actor 记 gyb、带 quote；reviewer 的审查基准是「actor 是 gyb 或 idea 的决定行」，不看落在哪个文件里。所以 reviewer 要审的行散在 `decisions.gyb.jsonl` 和 `decisions.idea.jsonl` 两个文件里，还可能出现在别的角色那本里（角色会话里 actor 记 gyb 的那些行）。

不在基准里的：文献不算基准，reviewer 不拿文献当基准；gyb 没说出口的意思不算基准，reviewer 不猜 gyb 的意思。deploy 自决那些行（actor 是 deploy）也不是基准，它们是被审的对象。

审读意见里有一条「reviewer 只审决定里明说的几条免得刷假问题」，gyb 没采纳，理由是审查基准本来就只有 gyb 定下的决定，已经是这个意思，不另加限制。

跟基准配套的两处痕迹，reviewer 事后查的时候用得上：角色会话里 `--as-gyb` 必须带的 `--quote`，设计文档写明这个 quote 就是留给 reviewer 的痕迹；grants 账里的授权行，设计文档写明 grant 是给 reviewer 事后查的凭据。

## 审三样

reviewer 具体审三样：

1. 代码写得对不对。
2. 实验运行得对不对。
3. analysis 写的分析代码和 notebook 是不是 gyb 要的。

第三样有一条边界：reviewer 审分析代码，不碰数据统计本身，统计是 analysis 的活。

## 什么都能读，但读的顺序是死的

reviewer 什么都能读（2026-08-16 晚 gyb 裁，原来的「默认不读 deploy 的想法和部署报告」作废；同一条也是施工计划第一节裁决 7）。角色 json 的 `reads` 栏写的是「一切（九本账、全部目录）」。

对抗性只体现在读的顺序：

1. 先读 gyb 和 idea 的决定，以及最终的代码，形成自己的判断。
2. 再读运行记录和分析代码。
3. 最后才读 deploy 的决定账和部署报告，拿来核对。

这个顺序写进 SKILL.md，靠纪律，没有机器拦它。读一律不设权，九本账的查询命令谁都能调，角色 json 的 `reads` 栏是纪律不是门禁。

读的办法还要照公共母版的读法栏走：读文件先想清楚要回答什么问题，再挑最小的读法；大文件禁止整读；读记忆一律经 rl 的查询命令，不直接开 loop/ 下的文件。母版的原话在 `common/READING.md`，SKILL.md 只写一句「按 common/ 执行」，不抄条文，见 `09-common-and-feedback.md`。

## 审哪一版代码：code_paths 和 runs 账里的 commit

要审的代码清单从工单交活时记的代码路径栏来，就是 handoffs 上 `work_order` 的 `code_paths`。这一栏在工单进 `done_pending_review` 那一版必填，由 deploy 填。

审哪一版：按 runs 账里那个 commit 审，不审当前工作树。runs 账的发射版上有 `commit` 字段。

deploy 改到 experiments/ 外的宿主文件（仓库根 run.py 的注册表、MAP.md、ops/ 里的东西）不进钩子的拦截范围，纪律要求 deploy 把这些改动列进部署报告带文件的那一份（`detail`），并在 `decisions.deploy.jsonl` 留一条来源指向那个文件。

不带文件的那一份报告（`method`）必须原样抄一遍这张工单引的决定编号加版本，reviewer 拿它当锚审「代码和决定是不是一回事」。

## 清单：一个文件、一个头部、五栏

reviewer 的产出只有一样：review/ 里的问题清单。清单不进 notebook。

清单一次审查一个文件，文件名 `review/<日期>-<审的决定编号>.md`。

头部写两样：审的是哪个 run_id、哪个 commit。

一条问题五栏：

| 栏 | 内容 |
|---|---|
| 1 | 决定编号加版本 |
| 2 | 代码或记录的位置 |
| 3 | 对不上在哪 |
| 4 | 建议动作 |
| 5 | 决定账里没写但代码里做了的选择 |

第五栏是让 reviewer 把账的空白也报出来的地方。

清单落盘之后，`rl status` 列出最近的清单（阈值 `status.review_recent_days` 默认 7 天，写在 `research-loop.json` 里）。idea 读 review/，reviewer 的清单是 idea 下一轮的输入。

## 不开 issue、不派活

reviewer 不开 issue、不派活。角色 json 的 `ledger_writes` 里没有 issues 的任何一条，`dispatches_to` 是无。

公共规矩第 6 条（故障分域）里 reviewer 那半句写的是：reviewer 不开 issue，卡住也只写进清单交给 gyb。设计文档同一句加了注：施工计划公共规矩第 6 条里 reviewer 那半句按这一句改。

reviewer 能写的账只有三样：自己那本决定账、`session focus`、feedback。写文件的地方只有 review/ 一处。

## 角色 json 五栏

角色 json 的四栏从上面的 use case 表倒推，`model` 另记。reviewer 的 use case 表（施工计划第五节原文）：按 gyb 点名审一条或一批决定（session focus）；读顺序先决定和代码、再运行记录、最后部署报告；按工单的 code_paths 和 runs 账里的 commit 审；写清单到 review/；自决留痕。

| 栏 | reviewer 的值 |
|---|---|
| `reads` | 一切（九本账、全部目录） |
| `writes` | `review/` |
| `ledger_writes` | decisions.reviewer 全部、session focus、feedback add |
| `dispatches_to` | 无 |
| `model` | `as_subagent` 是 fable，`manual` 是 inherit |

模型这一栏按施工计划第一节裁决 3：由 agent（subagent 或 workflow）调用的时候 idea、reviewer 用 fable；gyb 手动加载角色的时候跟当前会话的模型一致。这条与本机 `~/.claude/CLAUDE.md` 的「subagent 默认不用 Fable」不一致，按原则 8 工程内为准，插件的 README 和角色 json 里都要明写「fable 是 gyb 2026-08-16 点名的例外」。

两处原文不一致：设计文档写 reviewer 由 gyb 手动开、审读意见第 9 条也写「reviewer 只由 gyb 手动开」，施工计划第一节裁决 3 又给 reviewer 定了 `as_subagent` 的模型 fable，说的是「由 agent（subagent 或 workflow）调用的时候」。按裁决优先，角色 json 照裁决 3 写两个取值；谁去起这张 subagent，源文档没写，留在下一节。

有一条机器检查（测试 13）：SKILL.md 正文出现的每条 rl 写命令都要在这个角色 json 的 `ledger_writes` 里，查询命令不查；每个读的目录都要在 `reads` 里；SKILL.md 里不许有 common/ 母版条文的副本。

## 和别的 part 的接口

- 决定账行的 `actor` 字段（取值是五个角色或 `gyb`）、`quote` 字段、`root_id`、六个决定文件的拆法：定义在 `03-ledgers.md`。
- handoffs 上 `work_order` 的 `code_paths` 栏、`report_paths` 的 `method` 与 `detail`、`done_pending_review` 时 code_paths 必填这条前提：定义在 `03-ledgers.md` 和 `04-handoffs-and-sessions.md`。
- runs 账发射版上的 `commit` 字段：定义在 `03-ledgers.md`。
- sessions 账的 `focus` 字段、`rl session focus --decision ID` 这条命令：定义在 `03-ledgers.md` 和 `05-rl-cli.md`。
- `rl inbox` 列哪四类、`rl status` 哪一段列 review 清单、哪一段列活着的会话带 focus：定义在 `05-rl-cli.md`。
- 阈值 `status.review_recent_days`（默认 7）：定义在 `08-trees-init-and-host.md` 第三节阈值表（2026-08-17 gyb 裁）。
- 钩子对 reviewer 的拦法（Write/Edit 出了 review/ 一律 deny、直接写 loop/ 一律 deny）、读不设权这条推论：定义在 `06-hooks-and-permissions.md`。
- 公共母版的读法栏、公共规矩第 6 条、feedback 怎么提：定义在 `09-common-and-feedback.md`。
- grants 账里 `read:notes` 那条授权、doctor 那一项「决定的来源指向 notes/ 但 grants 里查不到这个 actor 的 read:notes」的扫描：定义在 `03-ledgers.md` 和 `05-rl-cli.md`。
- reviewer 的清单怎么成为 idea 下一轮的输入、idea 读 review/ 之后干什么：写在 `25-pair-reviewer-idea.md`。
- `--as-gyb` 必须带 `--quote` 这条规矩本身：定义在 `01-gyb.md` 第二节（2026-08-17 gyb 裁）；钩子对 `--as-gyb` 不生效那一句在 `06-hooks-and-permissions.md`。

## 源文档没写清的（留给 gyb）

1. 谁去起 reviewer 的 subagent。角色 json 给了 `as_subagent` 是 fable，可是五份角色 json 的 `dispatches_to` 没有一份指向 reviewer，gyb 的 use case 表里也没有「起一个 reviewer」这一条。
2. 审一批决定的时候清单文件名怎么起。use case 表写的是「按 gyb 点名审一条或一批决定」，文件名格式 `review/<日期>-<审的决定编号>.md` 只放得下一个决定编号。
3. `rl session focus --decision ID` 一次只收一个决定编号，审一批的时候记哪一个，源文档没写；审完之后 focus 清不清、怎么清，也没写。
4. 文件名里的「审的决定编号」带不带版本号。清单正文第一栏明写是「决定编号加版本」，文件名那一处只写「审的决定编号」。
5. reviewer 中途卡住（读不到产物、代码对不上任何一条决定）怎么落。规矩 6 说「卡住也只写进清单交给 gyb」，清单的五栏里没有一栏是装这类东西的。
6. reviewer 自决留痕具体记什么。`ledger_writes` 里有 decisions.reviewer 全部，源文档没举一个例子说 reviewer 会做什么自决。
7. 审运行记录和分析代码的时候按哪一版。代码这一样明写按 runs 账里那个 commit 审，analysis 的 notebook 和图没有对应的锚。
8. 清单头部只写 run_id 和 commit，要审的 code_paths 是从工单来的，头部记不记那张工单的编号，源文档没写。
9. reviewer 自己拿什么核对读的纪律（比如 idea 有没有在没有 grant 的时候读了 notes/）。系统里没有读日志，现有的只有 doctor 的那一项扫描，那是 doctor 跑的不是 reviewer 跑的。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

下面的条目从 `plans/2026-08-16-research-loop-simulation-round2.md` 原样抄来，保留场景名、序号、严重度、kind、原文、依据、改法，没有核实，也没有判断。

### result-wrong-review（25 步，gyb 动手 11 次）

3. [blocks/contradiction] 第 16 步：设计文档说 reviewer「不开 issue、不派活」，施工计划第十三节公共规矩第 6 条说「analysis 和 reviewer 不在楼梯上，卡住直接开 issue 给出问题的角色」，两句直接打架；而且 reviewer 的角色 json 里 ledger_writes 只有 decisions.reviewer 和 feedback add，没有 issues，真按规矩 6 开 issue 会被入账校验退出码 3，reviewer 中途读不到产物时按文档无路可走。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-build-plan.md:250; plans/2026-08-16-research-loop-build-plan.md:109
   - 改法：规矩 6 里把 reviewer 摘出来，明写 reviewer 只写 review/ 清单、卡住也只写进清单交给 gyb。
4. [slows/contradiction] 第 9 步、第 10 步、第 13 步（reviewer 全程只调查询命令）：设计文档说机器检查是「SKILL.md 正文出现的每条 rl 子命令都要在这个角色 json 的 ledger_writes 里」，施工计划的 test_skill_refs 只要求写命令在 ledger_writes 里；reviewer 的 SKILL.md 必然写到 rl decision stale、rl decision show、rl run show、rl handoff show 这些读命令，按设计文档那句检查必挂。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：把设计文档第 40 行改成「写命令进 ledger_writes、读命令进 reads」，和测试 13 对齐。
5. [blocks/missing] 第 19 步（gyb 若当场废掉或改 dec-idea-0007 而不是让 idea 改）：gyb 给别人的决定追加一版落哪个文件没写：设计文档说 gyb 写的决定落 decisions.gyb.jsonl，又说决定账按 actor 拆六个文件、编号带角色前缀，那 dec-idea-0007 的第 3 版由 gyb 写就会和第 1、2 版分居两个文件，「默认查询只取最新版」和锁里的扫号都要跨文件才对，入账脚本没有依据。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-next-steps.md:96; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:128
   - 改法：明写「决定行按 id 前缀落文件，谁写的记在 actor 字段」，dec-gyb 前缀只给 gyb 新开的决定。
6. [slows/contradiction] 第 19 步和第 23 步：`--as-gyb` 缺 `--quote` 到底硬不硬拦：设计文档说「这条靠纪律，钩子不拦，reviewer 事后可查」，施工计划第六节说「缺 quote 时 rl 拒收（退出码 2）」；再者 rl 只看会话状态文件，分不出角色会话里这条命令是 gyb 本人敲的还是模型敲的，硬拦会把 gyb 本人一起拦住，和原则 1「任何权限检查对 gyb 不生效」相冲。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：统一成硬拦，并明写 gyb 本人在角色会话里也要带 --quote（自引一句即可），设计文档第 34 行的「靠纪律」删掉。
7. [slows/missing] 第 11 步：reviewer 读顺序第一段要「先读最终的代码」，但没写要审的代码清单从哪来；工单上只有 report_paths 没有代码路径，而 deploy 改到 experiments/ 外的宿主文件（run.py 注册表、MAP.md、ops/）只列在 detail 报告里，读顺序又把 detail 排在最后，先读代码那一遍必然漏掉宿主文件的改动。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：工单加一个 code_paths 字段由 deploy 提验收时填，或明写 reviewer 第一段可以先读 detail 报告里的文件清单那一节、不读它的结论。
8. [slows/missing] 第 11 步和第 15 步：reviewer 审的是哪一版代码没有锚：清单四栏是决定编号加版本、代码或记录的位置、对不上在哪、建议动作，没有 commit；本场景要审的是跑出那个数字的那一版代码，runs 账里存着 commit，文档没写 reviewer 要按那个 commit 审还是审当前工作树，两种结论可能不一样。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：清单头部必填 run_id 和 commit，reviewer 明确按 runs 账里那个 commit 审。
10. [slows/ambiguous] 第 23 步：决定来源 file 类允不允许指 review/ 里的清单两种读法都通：设计文档举例只有 notes/ 里 gyb 的调查报告和 analysis/ 里的图与 notebook，测试 3 却只检查路径存不存在。审出问题之后更新决定，最自然的来源就是那份清单，入账脚本按哪种写会决定它收不收。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:205; plans/2026-08-16-research-loop-build-plan.md:57
   - 改法：设计文档第 46 行明写 file 类是仓库内任意路径，举例补上 review/ 的清单和 experiments/ 的部署报告。
11. [slows/missing] 第 8 步到第 15 步：reviewer 的审查基准只有决定账、不猜 gyb 的意思，可 gyb 起疑的正是「当初谈定的东西和代码不是一回事」，谈定却没被 idea 记进决定账的那部分 reviewer 审不出来，也没有任何一栏让它报告「代码里做了选择但决定账里没有对应行」。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:84
   - 改法：清单四栏加第五栏「决定账里没写但代码里做了的选择」，让 reviewer 把账的空白也报出来。
12. [cosmetic/missing] 第 6 步到第 17 步：reviewer 干活期间没有任何派活单，owner 和 holder 都不存在，rl status 只有等清单落盘之后才在「最近 7 天的 review 清单」那一段看得到；审到一半会话崩掉或 gyb 忘了这件事，收件箱里没有任何痕迹。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:182
   - 改法：rl status 的活着会话那一段带上 reviewer 会话正在审哪条决定（gyb 点名时用 rl 记一行），或给 reviewer 开一张 owner 是 gyb 的 review_order。

### next-plan-after-results（36 步，gyb 动手 16 次）

6. [slows/ambiguous] 第 26 步：讨论里定下的结论落 decisions.gyb 还是落 decisions.idea 带 quote，判据是「gyb 亲自打的」还是「idea 替 gyb 记的」。可是在手动加载角色的会话里 rl 命令都是模型敲的，「gyb 亲自打」这条路实际只存在于另开裸终端，同一条结论两处都说得通，reviewer 的基准会散在两本账里
   - 依据：2026-08-16-research-loop-next-steps.md:34; 2026-08-16-research-loop-next-steps.md:44; 2026-08-16-research-loop-build-plan.md:121
   - 改法：定死「角色会话里一律落角色那本账带 quote，decisions.gyb 只收裸终端写的」，把判据从「谁亲手敲」换成「哪个会话」

### run-crash-midway（40 步，gyb 动手 4 次）

17. [cosmetic/missing] 第 34 步：崩过一次这件事在两份部署报告里没有落点。next-steps.md:56 规定 method 那份只讲做法、用了什么技术、数据怎么被处理，detail 那份带文件和处理细节，两份都不装失败史；reviewer 拿 method 那份当锚审「代码和决定是不是一回事」时，看不到「原来的 batch size 跑不动」这条，只能自己去 issues 账翻。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:88
   - 改法：detail 那份加一栏「这张单子上关联的 issue 编号和结论」，由 `rl handoff show` 自动列。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

6. [slows/ambiguous] 第 10 步：gyb 坐在 deploy 会话里当场拍板一个影响实验结果的参数，这条落 decisions.deploy 还是 decisions.gyb 两种读法都说得通：deploy 一节说「取第几层、超参取值算自决，进 decisions.deploy」，idea 一节说「gyb 会参与到影响实验结果的工程细节里，这些细节同样写进决定账」并要求 gyb 定的那一版和角色自决的分得出来。落错了直接影响 reviewer——reviewer 的审查基准只有 gyb 和 idea 层谈定的决定，落进 decisions.deploy 就不在基准里。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:60; plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:34
   - 改法：在 deploy 一节补一句：gyb 当场拍板的算 gyb 的决定，落 decisions.gyb（--as-gyb 加 --quote），deploy 自决只指 gyb 不在场时自己拿的主意。
10. [slows/principle_violation] 第 3 步：违反原则 1（谁在打命令和会话装了什么角色是两回事，账行如实记 actor 和会话两样）。这条链上第 5 到第 23 步全部由 gyb 本人驱动，可 sessions 账只有 role 和 model 两栏、handoffs 只有 holder 一栏、每条账行的 actor 只能填角色名，事后没有任何字段能分出「这张单是 gyb 亲手干的」还是「subagent 干的」；reviewer 要查也查不到。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-next-steps.md:120
   - 改法：sessions 账加一栏 launched_by（manual / subagent / workflow），钩子登记时按有没有父会话填。

### idea-request-notes（15 步，gyb 动手 4 次）

7. [slows/missing] 第 12 步和第 14 步：file 类来源只有 path 一个字段。一份几十页的文献调查整份当来源，reviewer 拿决定账当唯一审查基准的时候，定位不到是报告里哪一句支撑这条决定，核不动「代码和决定是不是一回事」上游的那一半
   - 依据：plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:88
   - 改法：file 类来源加一个可选的 anchor 字段（小节标题或行号区间），命令写成 `--source file:notes/x.md#<小节>`
8. [slows/missing] 第 12 步：读权不上钩子、靠纪律加 reviewer 事后查，但文档没写 reviewer 拿什么查「idea 有没有在没 grant 的时候就读了 notes/」。系统里没有读日志，doctor 的八项扫描里也没有这一类，这条纪律实际上无从核对
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:136; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl doctor` 加一项扫描「decisions 里 source 指向 notes/ 但 grants 里查不到该 actor 的 read:notes」，把这条纪律接回入账校验那一层

### doctor-findings-fix（24 步，gyb 动手 15 次）

12. [cosmetic/missing] 第 5、9 步（修账那两版留不留痕）：gyb 在裸终端补的 stuck 和 reject 这两版，账上只留 status 和 reason，没有任何字段标明这是 doctor 修账修出来的。reviewer 事后翻 handoffs，分不出这张单子是真卡住过、还是只是把断掉的引用补回去。
   - 依据：2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:55; 2026-08-16-research-loop-next-steps.md:88
   - 改法：公共骨架加一个可选的 `fix_for` 字段，doctor 给的修法命令一律带上扫描项名字。

## 裁决记录（日期）

- 2026-08-17 gyb 裁（sync-inbox 问题 1，原话「这个归01吧」，rl-hub 转来）：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 定义处归 `01-gyb.md`。接口一节的指向照改。
- 2026-08-17 gyb 裁（sync-inbox 问题 3，原话「按照08吧」，rl-hub 转来）：阈值表定义处是 `08-trees-init-and-host.md` 第三节，接口一节的指向照改。
