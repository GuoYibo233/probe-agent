# reviewer 与 idea 之间的交流

> 这份覆盖 reviewer 和 idea 之间那一条通道：reviewer 的清单写成什么样、清单落在哪、`rl status` 怎么把清单列给 gyb、idea 怎么读到清单、idea 审出问题之后怎么把清单变成决定账上的新一版或者新一条、以及这条通道为什么只经文件（reviewer 不开 issue、不派活）。
> 这份不覆盖：reviewer 自己怎么审（读的顺序、reads、model、session focus 之外的动作）见 `14-role-reviewer.md`；idea 的完整职责、开工单、验收见 `10-role-idea.md`；决定账的编号、版本、根决定、来源三类的完整规则见 `02-decisions.md`；九本账的行格式见 `03-ledgers.md`；命令签名见 `05-rl-cli.md`；`rl status` 十段怎么分见 `01-gyb.md`；钩子和写权见 `06-hooks-and-permissions.md`。
> 源：设计文档「五个角色」总段、「idea」、「reviewer」、「账本」里决定树那几条、「gyb 自己做的事」末段；施工计划第一节裁决 7、第五节 idea 与 reviewer 的角色 json、第六节命令表（`rl session focus`、`rl decision add/update/confirm`、`rl status`）、第八节 `status.review_recent_days`、第十节测试 3、第十三节规矩 6。

## 这条通道只经文件

reviewer 由 gyb 手动开，审整条链，产出只写 `review/` 里的问题清单，不开 issue、不派活（按 `common/` 问题清单起 sonnet subagent 逐题查不算派活，2026-08-18 gyb 裁，sync-inbox 问题 33），动不动由 gyb 看完之后定。reviewer 的角色 json 里 `ledger_writes` 只有 decisions.reviewer 全部、`session focus`、`feedback add` 三样，issues 不在里面；`writes` 只有 `review/`；`dispatches_to` 是无。所以 reviewer 到 idea 没有派活单、没有问题条，只有 `review/` 里的一个 markdown 文件。reviewer 中途卡住也一样：施工计划第十三节规矩 6 写的是「reviewer 不开 issue，卡住也只写进清单交给 gyb」，设计文档 reviewer 一节写的是同一句，两处一致。

idea 那一头是读：idea 的 `reads` 里列着 `review/`，设计文档在那一栏后面加了一句「reviewer 的清单是 idea 下一轮的输入」，施工计划 idea 的 use case 表最后一条也是「读 reviewer 清单」。

## 清单长什么样

清单一次审查一个文件，不进 notebook。

文件名是 `review/<日期>-<审的决定编号>.md`。

头部写两样：审的是哪个 run_id、哪个 commit。commit 按 runs 账里那个 commit 取，reviewer 审那一版代码，不审当前工作树。

一条问题五栏：

| 栏 | 内容 |
|---|---|
| 1 | 决定编号加版本 |
| 2 | 代码或记录的位置 |
| 3 | 对不上在哪 |
| 4 | 建议动作 |
| 5 | 决定账里没写但代码里做了的选择 |

第五栏是给账上的空白留的：谈定却没被 idea 记进决定账的那部分，reviewer 用这一栏报出来。

reviewer 的审查基准只有决定账里 actor 是 gyb 或 idea 的行，不看这些行落在六个决定文件里的哪一个，不拿文献当基准，不猜 gyb 的意思。所以 idea 写决定账的时候写进去多少，reviewer 能审的就是多少。

## reviewer 干活期间账上的痕迹

reviewer 开工时调 `rl session focus --decision ID` 记一下在审什么。这一条落在 sessions 账的 `focus` 字段上，`rl status` 的活着会话那一段带出来。`rl session focus` 只有 reviewer 能调。

清单落盘之后进 `rl status` 的段 9：review/ 最近的清单、活着的会话（含 focus）、没关的快车道。「最近」的口径是 `status.review_recent_days`，默认 7 天（施工计划第八节）。

## idea 怎么拿到清单

两条路，都在文件这一头，没有推送：

1. gyb 在 `rl status` 段 9 看到最近的清单，看完定动不动，动的话找 idea。
2. idea 自己读 `review/`。idea 的 `reads` 覆盖 `review/`，读权一律不设门禁，查询命令谁都能调。

`rl inbox` 是角色的收件箱，列的是本角色名下 open 的 issue、owner 是本角色而 holder 为空的单子、本会话手上单子引的过版决定、发给本角色的通知、本角色提的 feedback 的裁决。reviewer 不开 issue，所以清单不会经 `rl inbox` 到 idea 手上。

## 审出问题之后 idea 怎么更新决定

idea 把清单变成决定账上的一行，动作是 `rl decision update`（换正文，追加一版）、`rl decision confirm`（正文不变、只加来源）、`rl decision add`（新开一条）、`rl decision retire`（废除）之一。判据是设计文档 idea 一节那一条：改的是同一个问题的答案，也就是同一件事换个做法、换个参数、停掉，就追加一版；换了要回答的问题，就开新条。

来源那一栏是这条通道的落点。每条决定必须带来源，来源是一个列表，每一项是三类之一：

| kind | 内容 |
|---|---|
| `decision` | 旧决定的编号加版本 |
| `file` | 仓库里的文件路径，可带一个锚点指到小节或行号区间 |
| `run` | runs 账里的一个 run_id |

三类可以混着放，至少一项，空列表入账脚本拒收。`file` 类可以是任何仓库内路径，设计文档 idea 一节举的例子里就有「review/ 里的清单」。所以 idea 按清单改决定的时候，来源直接指那份清单的路径，要精确到某一条问题就加锚点。测试 3 那一条管着这件事：`file` 类路径不存在拒收、带锚点通过——清单文件得先落盘，来源才写得进去。

追加一版的时候来源默认继承上一版，`update`、`confirm`、`retire`、`merge` 不给 `--source` 就继承。

reviewer 自己那本 decisions.reviewer 里的行不是 idea 改的对象：跨角色改别人的决定一律在自己那本开新条，来源指原决定的编号加版本。

决定改了一版或者被废除的那一刻，rl 当场列出引着旧版而没到终态的单子和它们的 holder。改版不影响已经派出去的单子：单子按派出时引的那一版继续做，rl 只标过时，不自动打回、不自动标待复核、不自动停。停不停由 gyb 点名，停就用收回；要重派用 `rl handoff reissue`。

## 和别的 part 的接口

- `review/` 的写权只有 reviewer，别的角色 Write 或 Edit 这个目录被钩子 deny：见 `06-hooks-and-permissions.md`。
- decisions 行的字段（`id`、`version`、`status`、`sources`、`root_id`、`quote`、`actor`）和 `decisions.gyb.jsonl` 只收裸终端的规矩：见 `03-ledgers.md`。
- 决定的编号前缀、根决定、追加一版与新开一条的完整规则：见 `02-decisions.md`。
- `rl decision add/update/confirm/retire/merge`、`rl session focus`、`rl status`、`rl inbox`、`rl trace` 的完整签名和「谁能调」：见 `05-rl-cli.md`。
- `rl status` 十段各列什么（桌面通知 2026-08-21 裁掉不做）：见 `01-gyb.md`。
- sessions 账的 `focus` 字段和 reviewer 会话的销号：见 `04-handoffs-and-sessions.md`。
- 清单第二栏「代码或记录的位置」用的 `code_paths` 和两份部署报告，由 deploy 在工单上填：见 `20-pair-idea-deploy.md`。
- 清单头部的 run_id 和 commit 从 runs 账取，runs 行格式见 `03-ledgers.md`。
- reviewer 什么都能读、隔离只体现在读的顺序（施工计划第一节裁决 7）：见 `14-role-reviewer.md`。
- idea 读 `notes/` 要 grant、idea 的其余 reads：见 `10-role-idea.md`。

## 源文档没写清的（留给 gyb）

1. 一份清单审一批决定的时候文件名怎么取。施工计划第五节 reviewer 的 use case 写的是「按 gyb 点名审一条或一批决定」，设计文档写的文件名模板 `review/<日期>-<审的决定编号>.md` 只装得下一个决定编号，一批是拆成几个文件还是一个文件挂多个编号，两份都没写。
2. 清单里的问题条没有编号。idea 拿 `file` 类来源加锚点指回某一条问题时，锚点指的是小节还是行号区间，清单本身要不要给每条问题一个可引用的编号，两份都没写。
3. idea 怎么知道有新清单落盘。清单不进任何一本账，`rl inbox` 的四类里没有「新的 review 清单」这一项，只有 gyb 的 `rl status` 段 9 列最近 7 天的清单。idea 是靠 gyb 转达还是每次上线自己扫 `review/`，两份都没写。
4. `rl status` 段 9 怎么找到这些清单。清单是 `review/` 下的文件、不是账行，rl 是扫目录按文件名日期排还是另有登记，两份都没写。
5. 清单没有状态，也没有关掉的办法。idea 读完、按不按清单改决定，账上不留痕；doctor 的扫描项里没有「清单里的问题有没有被处理」这一类。
6. 清单第四栏「建议动作」被 idea 或 gyb 否掉的时候往哪写。设计文档只写「动不动由 gyb 看完之后定」，没写不动的那一支要不要留一条决定或者一行记录。
7. idea 按清单改决定要不要先等 gyb 点头。设计文档一边写「动不动由 gyb 看完之后定」，一边把 `review/` 列进 idea 的 reads 并说清单是 idea 下一轮的输入，idea 能不能不等 gyb 直接 `rl decision update`，没写。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

来源：`plans/2026-08-16-research-loop-simulation-round2.md`。那份文件开头写明：17 个场景各派一个 opus 模拟者、一个 opus 核实者，最后一个 critic；模拟者跑完 16 个，17 个核实者和 critic 全部因为月度用量上限没跑成，所以下面的摩擦全部是未经核实的模拟者原话，可能有误报。

### result-wrong-review（25 步，gyb 动手 11 次）

3. [blocks/contradiction] 第 16 步：设计文档说 reviewer「不开 issue、不派活」，施工计划第十三节公共规矩第 6 条说「analysis 和 reviewer 不在楼梯上，卡住直接开 issue 给出问题的角色」，两句直接打架；而且 reviewer 的角色 json 里 ledger_writes 只有 decisions.reviewer 和 feedback add，没有 issues，真按规矩 6 开 issue 会被入账校验退出码 3，reviewer 中途读不到产物时按文档无路可走。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-build-plan.md:250; plans/2026-08-16-research-loop-build-plan.md:109
   - 改法：规矩 6 里把 reviewer 摘出来，明写 reviewer 只写 review/ 清单、卡住也只写进清单交给 gyb。

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

7. [slows/missing] 第 33 步：「这条方向看完结果继续做、设定不变」这一支没有落点。决定不换做法就不追加版、不换问题就不开新条，账上留不下 gyb 看过这批数字并确认继续的痕迹，下一轮 reviewer 和 `rl decision stale` 都看不到这次复核
   - 依据：2026-08-16-research-loop-next-steps.md:46; 2026-08-16-research-loop-next-steps.md:109
   - 改法：加一条 `rl decision confirm ID --source run:... --source file:...`，追加一版正文不变、只增来源
- 2026-08-18 来自 sync-inbox 问题 33 的裁决（定义处 `14`，rl-hub-v4 传；gyb 原话「选a」）：第一节「不派活」后补半句「起 sonnet subagent 逐题查不算派活」。对回原则 5。
- 2026-08-21 来自 `01-gyb.md` 定稿（`cd569ab`，rl-hub-v5 传）：接口一节「哪几段推桌面通知」按「桌面通知这一版不做」改。对回原则 6。
