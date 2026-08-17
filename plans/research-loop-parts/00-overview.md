# 总览：目标、十一条原则、裁决、文档索引

> 这份覆盖 research-loop 插件的目标与总验收、十一条设计原则的全文（带第二轮补的推论）、施工前的九条裁决、第六轮改的九条（a）到（i）（已全部裁完）、审读意见里没采纳的九条、讨论中改掉的十六条方向、两轮模拟的说明与原始文件路径、这套拆分文档的索引。
> 这份不覆盖任何机制细节：五个角色各自干什么在 `10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`、`14-role-reviewer.md`；九本账的行格式在 `03-ledgers.md`；派活单转移表和会话生命周期在 `04-handoffs-and-sessions.md`；`bin/rl` 命令表在 `05-rl-cli.md`；分权三层和钩子在 `06-hooks-and-permissions.md`；快车道在 `07-quick-lane.md`；两棵树、init、宿主对接在 `08-trees-init-and-host.md`；待验证清单、测试清单、施工步骤在 `30-build-steps-verify-tests.md`。
> 源：设计文档 `plans/2026-08-16-research-loop-next-steps.md` 的开头说明、「目标与总验收」「十一条设计原则」「待验证清单」「施工步骤」「审读意见里没采纳的」「讨论中改掉的方向」「第一轮模拟走查后的修订」「第二轮模拟走查后的修订」八节；施工计划 `plans/2026-08-16-research-loop-build-plan.md` 的开头说明、第一节（施工前的裁决）、第九节（待验证清单，只取题目）、第十一节（施工步骤，只取步骤名）、第十二节（留给 gyb 的）、第十四节（模拟走查：问题到原则到改动）。

## 一、目标与总验收

这套东西服务的是研究：想法要快速、多次迭代，代码风格不要求严密，能出数字就行。设计里每一条手续都要拿这两点去衡量。第二轮模拟数出来的手续量摆在本文件第七节，gyb 看着定哪几条要再砍。

施工顺序是先把共同底座和交流用的 json 落进插件，落完之后才写五个角色的 SKILL.md。

总验收由 gyb 定：每个角色配一个对应的任务，两个 agent 一个加载角色 skill、一个不加载，各做一遍，产出摆在一起由 gyb 自己看，不预先定判分办法。五个任务留到验收前由 gyb 定。怎么算过（2026-08-18 gyb 裁）：gyb 每看完一对产出说一句「过 / 不过」加一句原因，记进本文件文末的裁决记录，五对都过总验收才算过。

系统里有五个角色：idea 和 gyb 交流想法，出工单派给 deploy；deploy 写代码，把探索性概念转成清晰可发布的实现，把怎么运行交给 run；run 看服务器、运行实验、主要负责长时间的任务，出问题回报；analysis 分析实验结果，按 gyb 说的算数、画图；reviewer 审查整条链有没有照定好的执行。每个角色的详细规矩在对应的 part 文件里。

## 二、十一条设计原则

第一轮模拟报了 59 条摩擦，归并之后根子只有八个。第二轮模拟按八条改过的文档再走十七个场景，报了 234 条（未核实），归并之后：八条原则本身没有一条被推翻，但是有五条只写了正面一句、没把推论写出来，模拟者在推论上各猜各的；另外有三个根子八条里没有。下面十一条是根子的正面写法，带着推论；正文里每一处规矩都要能对回其中一条，施工时遇到文档没写到的岔路也按这十一条推。

1. 谁在打命令和会话装了什么角色是两回事。每次写账都有一个 actor：要么是五个角色之一，要么是 gyb。gyb 是超级用户，钩子、入账校验里的「谁能调」和转移表的「谁能写」对 gyb 一律不生效，gyb 在任何终端、任何角色会话里都能行使自己的权。账行如实记 actor 和会话两样。第二轮补的推论：rl 只认会话，不认手指。rl 能看到的只有「这条命令从哪个会话发出来」，看不到键盘前面坐的是 gyb 还是模型，所以一切身份规矩只按会话定：裸终端（session_id 是 `cli`）发出的命令 actor 就是 gyb，不用旗子也不用原话；角色会话里发出的命令默认 actor 是那个角色，加 `--as-gyb` 才以 gyb 身份写，而且不论是谁敲的都要带 `--quote`（gyb 本人敲就引自己刚说的那句），这个 quote 是留给 reviewer 的痕迹，缺了 rl 拒收。gyb 的豁免只豁免权限（谁能调、谁能写），不豁免账行的完整性：必填字段、路径存在、引用存在这些数据校验对 gyb 同样生效，gyb 要硬写就加 `--force --reason`，rl 照写并把 reason 记进账行。授权（grants）只有 gyb 能写：裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收。
2. 约束分三层，各管各的。钩子管 Write、Edit、Bash 三个工具（Bash 2026-08-18 gyb 裁进来：钩子解析命令里的重定向、`tee`、`sed -i`、`mv`/`cp` 目标路径，解析不出的归纪律）、只按研究仓库内的相对路径判、只拦两类离谱事：写别的角色的目录，直接写 loop/。入账校验管九本账的每一行，是硬的。其余一切（钩子解析不出的 Bash 写法、宿主发射器的台账、读什么、怎么读）靠 SKILL.md 的纪律加 reviewer 事后查。第二轮补的推论：读一律不设权。九本账的查询命令谁都能调，角色 json 的 reads 栏是纪律不是门禁；机器检查只查 SKILL.md 里的写命令在不在 ledger_writes 里。
3. 每张派活单有 owner 和 holder。owner 是开单的角色，负责单子从开到关：拉起下游、验收、收回。holder 是当前正在干这张单子的会话。第二轮补的推论：holder 非空当且仅当单子在开干。任何离开开干的转移（交活、卡住、打回、收回、交回、回收）都清空 holder，上一个 holder 另记一栏；开干只能从空 holder 进；销号只查开干的单子。owner 是角色不是会话，owner 角色当下没有活着的会话时单子由 gyb 拉起，`rl status` 单列这一类。开单时可以标「gyb 手动接」，标了 owner 就不起 subagent。
4. 九本账全是事件流。全部只增不改、全部带版本号，「改」永远等于追加一版；一个字段必不必填看这一版的状态，不看全局。第二轮补的推论：九本账每本都有 status 字段，校验按 status 查，runs 和 sessions 也不例外；改单子内容（换命令、补报告路径、补引用）也是追加一版，允许改的状态写在转移表里；前提查在交付那一刻，不查在开单那一刻，开单只查「单子说得清自己是什么」，交付才查「东西齐不齐」。
5. 权限从动作倒推。每个角色的读、写、能调的命令，从它的 use case 表逐条倒推出来，写进角色 json；不是先写 json 再找活对。第二轮补的推论：gyb 也有一张 use case 表（开工第一眼、批、验收、拉起、回收、修账），`rl status` 的段落和各 list 命令的过滤维度从这张表倒推，不是从五个角色的表推。
6. 进出对称，等人的事有收件箱。每本账能写进去就能查出来。第二轮补的推论：收件箱有两个，gyb 的叫 `rl status`，角色的叫 `rl inbox`。任何一版把某一行送进「等某人」的状态（等 gyb 批、等 owner 验收、等 assignee 回、等 owner 拉起、等谁读通知），那一行必须出现在那个人的收件箱里；桌面通知只是 gyb 收件箱里几段的推送，哪几段推送写成一张表。`rl inbox` 是查询命令，不是上线动作：角色被拉起不自动查收件箱，先干拉它起来的那张单，`rl inbox` 谁需要谁敲。
7. 快车道有明确的进和出，进出都是账上的一行。进是 gyb 点名后 `rl ql open`（分配标签、建 worktree、记杂账），出是 `rl ql close`（合回或放弃，各一行）；中间的一切都在 worktree 和杂账里。快车道不是 deploy 专属：analysis 想先画一张图给 gyb 看也走同一条，只是合回（`--merged`）只对 deploy 开，analysis 的快车道只有 `--dropped`，要留就走正常路重做（2026-08-17 gyb 裁，sync-inbox 问题 16）。
8. 文档只有一处为准，后裁的赢。施工计划第一节的裁决优先于设计文档正文；每条推翻正文某一行的裁决，要回来把那一行改掉并标日期，不留两个值。工程内的规矩优先于机器全局规矩，例外要明写。第二轮补的推论：可枚举的东西只在施工计划写一遍，设计文档指过去不抄；两份文档里同一件事说了两遍的地方，第二轮找出来的全部并成一处。2026-08-18 gyb 裁：这套拆分文档逐份定稿之后就是为准的那一处，两份源文档从此不再回写，开头各加一句「已被拆分文档取代，只留作历史」；拆分文档和源文档打架按拆分文档。
9. 每张单、每条 run 都有一条回到决定的显式链（第二轮新增，出处见第七节说的第二轮归堆，第一轮没有对应条目）。发射单和分析单都记父单，开单时从父单继承决定引用和 batch；发射单上就带 run_id、track、config，run 只抄不猜；`rl trace` 一条命令从任何一个编号打出 run 到发射单到工单到决定各版本的整条链。决定树上每条决定记根决定，两条研究线并行时按根决定切开看。
10. 发射单是多次尝试的容器（第二轮新增，出处见第七节说的第二轮归堆，第一轮没有对应条目）。一张发射单可以跑几次：smoke 失败、发射失败、跑挂、修完再来，每一次是单子上的一个 attempt，各带自己的命令、分步表、预计时长和 run 行；预计时长只算最新一次尝试；数字账默认只列每张单最新一次尝试的行、且退出状态是 ok，最新一次不是 ok 的这张单不出；真实耗时由 `rl run finish` 从时间戳算出来，不管退出状态是什么都记。
11. 派活不占终端（第二轮新增，出处见第七节说的第二轮归堆，第一轮没有对应条目；取代原则 3 里「subagent 接单默认同步」那一句）。上游开完单后台起 subagent 接走，上游会话继续可用，subagent 回来时上游验收；上游会话先结束了，单子照常在账上等 owner 下次上线或 gyb 验收。GPU 任务本体在 tmux 里跑、不跟会话走：run 会话死了单子交回待干，下一个 run 会话接单时发现最新一次尝试已经发射还没收尾就认领它（不重新 smoke、不重新发射，只接管看门狗和收尾）。等几个小时的事只发生在 tmux 里，不发生在任何会话里。

十一条原则进公共母版，母版里的编号是 principle-01 到 principle-11。母版本身见 `09-common-and-feedback.md`。原先要求再抄一份在 `research-loop/ARCHITECTURE.md` 开头，2026-08-18 gyb 把那份架构总说明裁掉了（见第八节），不抄。

## 三、施工前的九条裁决（2026-08-16 晚，gyb 裁）

这九条优先于设计文档正文。

1. 旧代码不要。`research-loop/` 目录下现有的 93 个文件（旧的入账脚本、schema、319 个测试、`idea-layer` 等四个旧角色 skill）整体退役，新插件从空目录开始写。旧代码留在 git 历史里，需要抄一段的时候去历史里翻，不在工作树里留任何旧文件。
2. 插件本体留在 `new1/research-loop/` 子目录里，不另开仓库。new1 是第一个用户，迁移 new1 的老代码进 `experiments/` 由 gyb 自己手动搬，插件的入口 skill 不做全量搬迁的 workflow，只保留「按需搬」的提醒。
3. 五个角色的模型：由 agent（subagent 或 workflow）调用的时候，run、deploy、analysis 用 opus，idea、reviewer 用 fable；gyb 手动加载角色的时候跟当前会话的模型一致。写进五份角色 json 的 `model` 字段，两个取值分开写。idea 和 reviewer 用 fable 与本机 `~/.claude/CLAUDE.md` 的「subagent 默认不用 Fable」不一致，按原则 8 工程内为准：这条裁决就是 gyb 点名的那一次例外，插件的 `README` 和角色 json 里都要明写「fable 是 gyb 2026-08-16 点名的例外」。
4. 公共规矩不再沿用 8 月 15 日 `redesign.md` 第 97 到 105 行的通例九条本文，改成从设计文档里重新抽一份，见施工计划第十三节。九条里第③条「机验人判」gyb 裁定去掉，其余八条 gyb 认可仍然代表本意；第⑦条里「自己域自己修」只留给 deploy 和 idea，run 出问题一律开 issue 给 deploy。
5. 钩子宽宽的：只挂 Write 和 Edit，只拦写别的角色的目录和直接写 loop/ 两类离谱事，其余放行；约束主要写在 SKILL.md 里。（2026-08-16 夜，看完第一轮模拟结果裁的。2026-08-18 后改：Bash 也挂，见原则 2。）
6. gyb 什么都能干：gyb 是超级用户，在任何终端、任何角色会话里都能插入，不受任何权限检查影响。
7. reviewer 什么都能读，隔离只体现在读的顺序。
8. 打架的地方以工程内为准，不以机器全局规矩为准。
9. 改文档不许打补丁：先把问题抽成原则，按原则改正文，再拿原则回头审一遍全部条目。

另外两条 gyb 同时定的：run 角色照 `.claude/skills/gpu-run/SKILL.md` 写，能力至少覆盖 gpu-run 的全生命周期，再按设计文档的原则改错误处理、钩子、通信三处（对照表在施工计划第七节，正文在 `12-role-run.md`）；总验收的五个任务留到验收前由 gyb 定。

模型那一栏可枚举，抄在这里：

| 角色 | as_subagent |
|---|---|
| idea | fable（gyb 2026-08-16 点名例外） |
| deploy | opus |
| run | opus |
| analysis | opus |
| reviewer | fable（同上） |

`manual` 那一栏五个角色都写 `inherit`，意思是跟当前会话的模型走，sessions 账落解析后的真实模型名或 `unknown`。角色 json 的其余四栏见 `06-hooks-and-permissions.md`。

## 四、第六轮改的九条（a）到（i），gyb 已裁

第二轮模拟之后写施工计划的人改的设计变动，一行一条。九条 gyb 已全部裁完（三条 2026-08-17、六条 2026-08-18），表里的说法为准，没有回退清单。

| 编号 | 改了什么 |
|---|---|
| （a） | 派活从同步等改成后台派加认领（原则 11）——2026-08-18 gyb 认 |
| （b） | gyb 的豁免收窄成只豁免权限、不豁免完整性，硬写用 `--force --reason`——2026-08-17 gyb 认 |
| （c） | `--as-gyb` 在角色会话里一律要 `--quote`，gyb 本人敲也要——2026-08-17 gyb 认 |
| （d） | grants 只收裸终端——2026-08-17 gyb 不认：授权只有 gyb 能写，裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收 |
| （e） | 分析单开单时口径可以是 proposed，交活才要全 approved（改了设计文档「idea 也可以给 analysis 开单，但是单子里只能引已经批准的口径行」那一句）——2026-08-18 gyb 认 |
| （f） | 快车道加 `rl ql open/close`、补单只要一份简报、验收人固定 gyb、analysis 也能走——2026-08-18 gyb 认 |
| （g） | N 张发射单由一个 run 会话接整个 batch——2026-08-18 gyb 认 |
| （h） | issue 加 `failed`、`orphaned`、`fyi` 三种 kind——2026-08-18 gyb 认 |
| （i） | `rl inbox`、`rl trace`、`rl handoff amend/resume/reissue`、`rl decision confirm`、`rl session show/list/focus` 几条新命令——2026-08-18 gyb 认 |

这九条已经按新写法写进两份源文档和对应 part 的正文。（b）（c）（d）三条 2026-08-17 裁（（d）不认，改成表里的新说法），其余六条 2026-08-18 一并裁认。

## 五、审读意见里没采纳的九条

三个 subagent 的三十条意见（原文在 `plans/2026-08-16-research-loop-plan-critiques.md`）里，八个题目已经裁进正文。剩下九条只出现一次、这一版不采纳，一行一条写为什么。

1. 部署报告按改动大小分档：小改动走快车道，快车道只写一份简报，分档没必要。
2. 分步计时只对长任务做：同上，小任务走快车道，正常路的发射单一律做（同 batch 只实测一次，其余复制）。
3. 下游发现 typo 的小修口子：写权按角色不开例外，run 或 analysis 发现代码问题开 issue 给 deploy。
4. 第一版只给按需搬不给全量搬：全量搬作废，new1 老代码由 gyb 手动按需搬（裁决 2；2026-08-16 晚 gyb 改裁，原先「全量搬保留走 workflow」的说法作废，2026-08-18 定稿时并成这一句）。
5. reviewer 只审决定里明说的几条免得刷假问题：reviewer 的审查基准本来就只有 gyb 定下的决定，已经是这个意思，不另加限制。
6. 口径按组批不按行批：analysis 不许自作主张，要看什么 gyb 一条条说；批的时候可以一句话批一组，说还是按行说。
7. 验收那一步 gyb 在不在场：默认 owner 验收，gyb 随时可以自己验，已经写在「交接」一节。
8. 环境类失败 run 就地重试一次不开 issue：run 出问题一律开 issue 给 deploy，不给自行重试的口子；重来是发射单上的下一次尝试（原则 10）。
9. reviewer 挂在验收上自动跑：reviewer 只由 gyb 手动开。

## 六、讨论中改掉的方向十六条

1. 补齐资产盘点这一步撤掉了。gyb 裁的：先把目标画明白，再拿着图去现有代码里点名挑件，点不到的不花时间判。8 月 15 日 74 件判定被推翻 20 件，就是因为拿着没画完的图判库存。
2. 「读 transcript 认角色」这条验证路线废弃，被 skill 头部钩子取代。
3. 「一个决定更新就换新编号加 superseded_by」废弃，被「编号不变加版本号」取代，理由是下层引用不会挂在旧版上。
4. 「决定账一个字段不拆文件」的旧倾向被 gyb 推翻，拆成五个文件（2026-08-16 晚加 gyb 一个文件，成六个）。
5. reviewer 不管文献这条上午锁过，下午 gyb 把整条文献线说全了：文献变 idea 只有 gyb 亲自做，idea 读文献要经允许。
6. 「派活单预写验收标准」撤掉，换成部署报告当验收产物。
7. 「reviewer 读 deploy 报告要走 grants」撤掉，改成 gyb 口头点名。（2026-08-16 晚再改：reviewer 什么都能读，隔离只体现在读的顺序。）
8. 「init 只登记代码路径不搬文件」撤掉，改成搬文件。
9. 「决定的来源加一类口头」这个提议没立住，改成来源可以指 run_id 和 analysis/ 里的图。
10. 「analysis 可以自己画探索图、不进口径账」这个提议被 gyb 顶回：analysis 不许自作主张画图。（2026-08-16 夜补：gyb 点名要先看一眼图的走快车道，图落 analysis/scratch/，还是 gyb 说了才画。）
11. 「写权表按角色开 run.py、MAP.md、ops/ 的白名单」这个提议被 gyb 顶回：撞到就提醒搬进 experiments/。（2026-08-16 晚改：钩子对这些路径放行不拦，纪律要求 deploy 报告里列出并留决定；「拦下提醒搬」作废。）
12. 「决定改版之后在办单子自动标待复核、加弃单命令」这个提议被 gyb 顶回：在办单子按派出时那一版继续，停不停 gyb 点名。
13. 「裸会话装兜底钩子」这个提议被 gyb 顶回：init 往 CLAUDE.md 写一句纪律。
14. 「通知走 loop/inbox 加 SessionStart 播报」这个提议被 gyb 改成桌面弹窗加 rl status。（2026-08-16 夜补：角色那一头加 `rl inbox`，是查询命令不是播报。）
15. 「subagent 接单默认同步、上游等几个小时」（第五轮原则 3 里的一句）2026-08-16 夜按第二轮模拟改成后台派活加认领（原则 11）。
16. 「一个 workflow 起 N 个 run 各接一张发射单」改成一个 run 会话接整个 batch。

## 七、两轮模拟怎么来的

设计现状是六轮讨论的产物：上午一轮逐步确认锁了六个裁决和五块架构，下午一轮语音打磨，晚上一轮按 gyb 的真实用法从 init 走到 reviewer 做了纸上走查，第四轮拿三个 subagent 的审读意见逐条裁了八个题目，第五轮拿第一轮模拟结果抽出八条设计原则并按原则改了正文，第六轮拿第二轮模拟结果把八条原则补成十一条、再按十一条把正文审了一遍。

原始文件在这四处：

| 文件 | 里面是什么 |
|---|---|
| `plans/2026-08-16-research-loop-plan-critiques.md` | 三个 subagent 的三十条审读意见原文 |
| `plans/2026-08-16-research-loop-simulation-round1.md` | 第一轮模拟的原始结果 |
| `plans/2026-08-16-research-loop-simulation-round2.md` | 第二轮模拟的原始结果 |
| `.scratch/research-loop/redesign.md` | 8 月 15 日的旧设计，和现在的文档冲突的地方以现在的为准 |

第一轮：十一个 opus subagent 按五个使用场景（改一个参数、新想法要实施、结果不对审代码、新计划画图、出结果定下一步）读上一版文档逐步走了一遍，核实后成立的摩擦 59 条，critic 归并成 13 条跨场景缺口。gyb 看完裁了四条：钩子只挂读写、宽宽的约束、太离谱的才拦，主要在 skill 里约束；gyb 什么都能干、任何地方都能插入、不受权限影响；reviewer 什么都能读；打架的地方以工程内为准不以全局为准。另外要求不打补丁，先把问题抽成原则再按原则改。

第二轮：十六个 opus subagent 各走一个场景（十七个里 new1 第一次 rl init 那个没跑成），报了 234 条摩擦；十七个核实者和 critic 因为月度用量上限没跑成，所以这 234 条没有经过对抗核实，写设计文档的人自己对着两份文档核了每一堆里引用最多的那几条，核过的都成立。234 条里 107 条是 missing、44 条 contradiction、30 条 ambiguous、22 条 too_heavy、17 条 principle_violation、8 条 blocked、6 条 guessed；40 条标 blocks。归堆之后是十一堆，前八堆对应第五轮的八条原则各缺一段推论、后三堆是新根子。每一堆归了哪些问题、改了两份文档的哪里，写在设计文档最后一节和施工计划第十四节，这份不抄。

第二轮数出来的手续量（模拟者数的，未核实；这一版砍手续之后没有重数）：

| 场景 | 步数 | gyb 亲自动手次数 |
|---|---|---|
| 改一个学习率走快车道 | 45 | 8 |
| 新想法正常路 | 39 | 7 |
| 结果不对审代码 | 25 | 11 |
| 画一张新图 | 17 | 8 |
| 一批结果定下一步 | 36 | 16 |
| 跑挂重来 | 40 | 4 |
| N 张发射单 | 58 | 10 |
| 决定改版重派 | 23 | 8 |
| gyb 手动接单 | 27 | 9 |
| 两条线并行 | 26 | 20 |
| 改一条规矩 | 15 | 9 |
| 申请读 notes | 15 | 4 |
| 定期回收 | 27 | 11 |
| 钩子漏销号 | 23 | 11 |
| smoke 失败 | 44 | 4 |
| doctor 修账 | 24 | 15 |

这一版按十一条原则砍掉的手续：快车道出口一份简报、同 batch 一次 smoke、后台派活不占终端、认领代替重跑、amend 代替收旧单开新单、reissue 一条命令、一句话批一组口径、init 时给 read:notes、accept 自动关 issue、reclaim 自带修法命令。剩下多少步没有再数。第三轮模拟先不跑，等整套拆分文档定稿、施工完成之后再说（2026-08-18 gyb 裁）；到时跑的话走同样十七个场景，重点数手续量，跑之前先把 new1 第一次 rl init 那个没跑成的场景补上。

## 八、施工步骤一览

施工之前 gyb 先把这套拆分文档逐份定稿（原文写的是「打磨设计文档」，按原则 8 的 2026-08-18 裁决，定稿的对象是拆分文档）。之后的八步，每步的交付物、验收、依赖、执行者与模型展开在 `30-build-steps-verify-tests.md`，这里只列步骤名：步 0 验证（第九节 11 条待验证）、步 1 清空旧代码（建空目录，含 `agents/` 层，不建 `workflows/`，2026-08-18 `08` 定稿裁）、步 2 架构文档（2026-08-18 gyb 裁掉：定稿的拆分文档本身就是架构说明，不另写 `research-loop/ARCHITECTURE.md`，这一步不做，编号保留不重排）、步 3 共同底座、步 4 交流机制、步 5 公共母版、步 6 五个 SKILL.md、步 7 最小一条路、步 8 总验收。

施工纪律四条从 8 月 15 日的记录搬过来：每步封闭验收（这一步的测试全绿才算完）、检查器先于被检查物（先写 schema 校验和测试，再写入账代码）、一步一个动件（一个 commit 只做一件事）、修三轮修不动就废掉重做。每步一个或多个 commit，commit message 前缀 `research-loop v2:`；用起来之后改母版的 commit 前缀 `research-loop rules:`，改完跑一遍 `tests/run_all.py`。

## 九、这套拆分文档的索引

| 文件 | 一句话 |
|---|---|
| `00-overview.md` | 本文件：目标与总验收、十一条原则、九条裁决、（a）到（i）九条改动（已裁）、审读没采纳九条、改掉的方向十六条、两轮模拟说明、文档索引 |
| `01-gyb.md` | 只有 gyb 亲自做的那几件事，和 gyb 的收件箱 `rl status` |
| `02-decisions.md` | 决定账：编号、版本、来源三类、根决定、追加一版还是开新条、废除与合并、过版 |
| `03-ledgers.md` | 九本账的行格式、每本的 status 取值、必填规则、公共骨架、锁与写序 |
| `04-handoffs-and-sessions.md` | 派活单的七个状态与转移表、交付物、接单与验收、会话生命周期与回收 |
| `05-rl-cli.md` | `bin/rl` 的子命令表、退出码、`--json` 结构 |
| `06-hooks-and-permissions.md` | 分权三层、钩子挂什么拦什么、五份角色 json 的四栏 |
| `07-quick-lane.md` | 快车道的进出、worktree、杂账、合回补单 |
| `08-trees-init-and-host.md` | 研究仓库和插件本体两棵树（含 `agents/` 层）、`rl init` 建什么、入口 skill、宿主台账对接 |
| `09-common-and-feedback.md` | 公共母版（公共规矩八条、词表、五栏规格、读法、判断类检查清单）和 feedback 账 |
| `10-role-idea.md` | idea 角色：和 gyb 谈决定、拆工单、验收 |
| `11-role-deploy.md` | deploy 角色：写代码、两份部署报告、开发射单、自决留痕 |
| `12-role-run.md` | run 角色：接发射单、smoke 与分步计时、发射、看门狗、收尾与中断 |
| `13-role-analysis.md` | analysis 角色：口径账、算数画图、交活 |
| `14-role-reviewer.md` | reviewer 角色：审查基准、读的顺序、review/ 清单五栏 |
| `20-pair-idea-deploy.md` | idea 与 deploy 之间的交流 |
| `21-pair-deploy-run.md` | deploy 与 run 之间的交流 |
| `22-pair-idea-analysis.md` | idea 与 analysis 之间的交流，含 gyb 直接开分析单 |
| `23-pair-run-analysis.md` | run 与 analysis 之间的数据契约 |
| `24-pair-analysis-deploy.md` | analysis 与 deploy 之间的交流 |
| `25-pair-reviewer-idea.md` | reviewer 与 idea 之间的交流 |
| `30-build-steps-verify-tests.md` | 待验证十一条、测试清单十七条、施工步骤八步 |

## 和别的 part 的接口

- actor 的取值（五个角色或 `gyb`）、`--as-gyb` 与 `--quote` 的规矩、`--force --reason` 的豁免范围：定义在 `01-gyb.md` 和 `05-rl-cli.md`，原则 1 用它。
- `owner`、`holder`、`last_holder` 三个栏和七个状态名（`todo`、`in_progress`、`stuck`、`done_pending_review`、`accepted`、`rejected`、`withdrawn`）：定义在 `04-handoffs-and-sessions.md`，原则 3 和原则 11 用它。
- 九本账的公共骨架（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`、`force_reason`、`via`）：定义在 `03-ledgers.md`，原则 4 用它。
- 角色 json 的四栏（`reads`、`writes`、`ledger_writes`、`dispatches_to`）加 `model`：定义在 `06-hooks-and-permissions.md`，裁决 3 的模型表落在那份的 `model` 栏里。
- `rl status`、`rl inbox` 两个收件箱：分别定义在 `01-gyb.md` 和 `05-rl-cli.md`，原则 6 用它。
- `rl ql open`、`rl ql close`、`ql_tag`、`--merged` 只对 deploy 开：定义在 `07-quick-lane.md`，原则 7 和第四节（f）用它。
- `parent_id`、`root_id`、`batch`、`attempt`、`rl trace`：定义在 `02-decisions.md`、`03-ledgers.md`、`05-rl-cli.md`，原则 9 和原则 10 用它。
- 第四节（a）到（i）九条改动的正文落点：（a）在 `04`（后台派活加认领）；（e）在 `22`（分析单开单时口径可以是 proposed）；（f）在 `07`；（g）在 `12` 和 `21`；（h）在 `03`（issue 的 kind）；（i）在 `05`。这一份只记裁没裁，机制在各自的定义处。
- 公共母版里的 principle-01 到 principle-11 编号和 rules_version：定义在 `09-common-and-feedback.md`，第二节那十一条抄进去；不再另抄进 `research-loop/ARCHITECTURE.md`（该文件 2026-08-18 裁掉）。
- 施工八步的细节和待验证十一条的题目：在 `30-build-steps-verify-tests.md`，第八节只列步骤名；步 2 架构文档不做、步 8 总验收的过法（每对产出「过 / 不过」加一句原因、五对都过才算过）由第一节和第八节定，`30` 照抄。
- gyb 手动搬老代码、入口 skill 的迁移提醒（裁决 2）：在 `08-trees-init-and-host.md`；`08` 里插件目录清单不再含 `ARCHITECTURE.md`。
- 文档谁为准（原则 8 的 2026-08-18 推论：拆分文档定稿为准，源文档停回写、加取代注）：影响统筹的传播规矩（`HANDOFF.md`）和两份源文档的开头，不影响任何机制。
- 语言：一切默认英语，任何 part 里不写语言相关的约束（2026-08-18 gyb 裁，见裁决记录）；这一份没有语言字样，别处有的由统筹去掉。

## 源文档没写清的（留给 gyb）

（2026-08-18 七条全部裁完，逐条见文末「裁决记录」；第 4 条 2026-08-17 已由 sync-inbox 问题 27 裁掉。）

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

下面的条目从 `plans/2026-08-16-research-loop-simulation-round2.md` 原样抄来，保留场景名、序号、严重度、kind、原文、依据、改法，没有核实，也没有做判断。选进来的标准是这一条直接拿「目标与总验收」那一句去衡量手续量，或者直接说某条原则和某条裁决对不上。同一条摩擦可能同时出现在别的 part 里。

### param-tweak（45 步，gyb 动手 8 次）

7. [slows/too_heavy] 第 23 到 43 步：改一个学习率的出口是全套正常路：补工单加两份报告、开发射单、起 run subagent、分步计时、runs 账两版、两次验收，整条路 45 步、gyb 亲自动 8 次，和「想法要快速、多次迭代」的目标打架
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：允许快车道合回后把那次杂账里的数字补成 runs 账一行（标 quick_lane 来源），只有 gyb 点名要正式数字时才重跑

### new-idea（39 步，gyb 动手 7 次）

9. [slows/too_heavy] 整条路：「探针输入从最后一层换成中间层」这一句话的改动，正常路要走 2 张派活单、3 个嵌套会话、2 份部署报告、至少 9 次 rl 写账，和「想法要快速、多次迭代」这条总目标对不上；唯一的减负出口快车道每次都要 gyb 当场点名
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给 work_order 加一个 --light 档只要一份 detail 报告，或者明写「同一条决定的第二次及以后的参数微调默认走快车道」

### result-wrong-review（25 步，gyb 动手 11 次）

2. [slows/too_heavy] 第 1 步到第 5 步：gyb 只是想知道「这个数字是按哪条决定跑出来的」，按文档要在裸终端敲 rl status、rl run list、rl handoff show、rl decision list、rl decision show 五条命令，中间还要靠 launch.command 里的路径人工比对，和「想法要快速、多次迭代」的目标不相称。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-build-plan.md:137
   - 改法：第六节命令表加一条 `rl trace <run_id>`，一条命令打出 run 到发射单到工单到决定各版本的整条链。

### plot-new-plan（17 步，gyb 动手 8 次）

2. [slows/too_heavy] 整条路（第 1 步到第 17 步）：gyb 只想看一眼图，按文档要走 2 次 eval propose、2 次 approve、1 次 handoff open、start、done、accept 共 8 次写账，gyb 本人要介入 8 次；快车道只给 deploy，analysis 没有对应的轻路，和目标里「想法要快速、多次迭代」对不上。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：给 analysis 加一条 gyb 点名的快车道：图先落杂账不开口径不开单，图要被引用或复用的时候再补口径和分析单。

3. [slows/principle_violation] 第 10 步（gyb 开分析单）：违反原则 1。原则 1 写 gyb 在任何终端、任何角色会话里都能行使自己的权，任何权限检查不生效；但施工计划只让 gyb 豁免转移表「谁能写」一栏和「谁能调」检查，「前提」一栏照旧生效，于是 gyb 自己开分析单时被 evaluation_refs 必须 approved 这条前提挡住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:77; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：在施工计划第四节表头明写「前提」一栏对 gyb 生不生效，若生效就把它改称数据完整性校验、和权限检查分开命名。

### next-plan-after-results（36 步，gyb 动手 16 次）

3. [slows/principle_violation] 第 14 步：违反原则 1。原则 1 和施工计划裁决 6 说 gyb 不受任何权限检查影响，转移表却只给 gyb 豁免「谁能写」一栏、不豁免「前提」一栏，于是 gyb 自己也开不出引未批口径的分析单、也收不了缺交付物的单子。两句话对「权限检查」的范围理解不一样
   - 依据：2026-08-16-research-loop-build-plan.md:77; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15
   - 改法：把原则 1 改写成「权限检查对 gyb 不生效，数据完整性前提对谁都生效」，并给 gyb 一个 `--force` 带原因写进账行

4. [slows/too_heavy] 第 1 到 36 步整条路：只是「看完一批结果定下一步」，gyb 亲自动作 16 次，其中光批口径就要按行逐条批、图口径还得先有指标口径两级批。设计文档开头写的目标是想法要快速多次迭代，每一条手续都要拿这两点衡量，这条路和那句话拉扯
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-next-steps.md:183; 2026-08-16-research-loop-build-plan.md:69
   - 改法：给「一批结果的例行复盘」开一条批量口令：gyb 一句话批一组口径（rl 记下这句原话展开成多行），图口径自动带上它 uses 的指标

### run-crash-midway（40 步，gyb 动手 4 次）

10. [slows/too_heavy] 第 12 到 20 步：三层会话同步嵌套等待：idea 等 deploy 等 run（next-steps.md:120、:58）。一个训练跑几小时，崩了之后 deploy 修完还要再等一整轮重跑，sess-idea-01 从派单到验收全程挂着不能做别的，与 next-steps.md:7「想法要快速、多次迭代」直接冲突。待验证第 9 条（build-plan.md:197）只测了一层（deploy 等 run），没测两层嵌套，备案也只写了 deploy 那一层。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：发射单一旦标 stuck 就让上游 subagent 立刻返回并销号，重跑由 gyb 在 `rl status` 里另起一个 deploy 会话接。

11. [slows/too_heavy] 第 16 到 20 步：deploy 改完一行超参之后，没有任何办法自己确认修对了：next-steps.md:58 明写 deploy 不跑 smoke，快车道要 gyb 点名才能进（next-steps.md:64），所以每一次修复都得走「起 run 会话 → 读档案 → 探卡 → 挑卡 → smoke → 填分步表 → 发射前 commit → 发射」全套；smoke 再挂就又是一条 issue 一轮循环。改一个 batch size 的代价和跑一个新实验一样。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：允许 deploy 在修 stuck 的发射单时不经 gyb 点名跑一次 smoke 规模的自测，结果写进杂账。

### n-launch-orders（58 步，gyb 动手 10 次）

5. [slows/too_heavy] 第 17 步：同一个 batch 的 5 张单只差一个 seed，每个 run subagent 都要各自读一遍代码、列一遍步骤、跑一遍 smoke、逐步计时、逐步打 estimate。设计文档明说不给「分步计时只对长任务做」的口子，正常路的发射单一律做，于是同一份分步表被重复造 5 次，撞在「想法要快速多次迭代」这个总目标上。
   - 依据：2026-08-16-research-loop-next-steps.md:70; 2026-08-16-research-loop-next-steps.md:179; 2026-08-16-research-loop-build-plan.md:135; 2026-08-16-research-loop-build-plan.md:160
   - 改法：加一条 `rl handoff estimate ID --copy-from <同 batch 的另一张单>`，同 batch 只让第一张单实测分步表，其余按规模系数复制。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

16. [slows/too_heavy] 第 6 到 22 步整段：「换个评测集」这一件事走了 23 步、gyb 亲自动手 8 次、牵动 4 个会话，其中 5 步是纯手续（分两次收单、两个会话销不掉号、手动关两条通知 issue、按新版本重开一张内容几乎相同的工单）。目标那一节写的是「想法要快速、多次迭代」（next-steps.md:7），这条路上没有任何一条把「决定改版后重派」压成一步的捷径。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：加一条 `rl handoff reissue ho-XXXX --decision ID@V`：一条命令连锁收旧单、清 holder、继承 explanation 开新单，并通知全部 holder。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

8. [slows/too_heavy] 第 11、16、22 步：gyb 亲手接一张已经开出来的正式工单，手续和 subagent 走一模一样：必须开发射单、必须分步计时填 step_table、必须写两份部署报告（method 那份还要原样抄决定编号加版本）。想减手续只有快车道，可快车道的入口是「gyb 点名」加另开一棵 worktree 加 rl scratch add，转移表里也没有「已开出的工单转快车道」这一行，而且审读意见第 1、2 条已经明确否掉了按改动大小分档。gyb 亲自上手的场合反而最重，和「想法要快速、多次迭代」相反。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:178; plans/2026-08-16-research-loop-build-plan.md:82
   - 改法：转移表补一行「todo 的 work_order 由 gyb 改标 quick_lane」，改标之后免发射单和两份报告，只留 scratch 记录。

### feedback-round（15 步，gyb 动手 9 次）

12. [slows/too_heavy] 整条路（gyb 亲手做九件事）：改一条规矩要 gyb 亲自做九个动作（status、feedback list、改母版、改施工计划、grep 五份 skill、accept、判断要不要收会话、告诉 deploy、commit），系统只帮他记一行账，剩下八件全靠他自己记得住；这跟「想法要快速、多次迭代」的目标不匹配
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-build-plan.md:67
   - 改法：rl feedback accept 收多个 applied_to 并当场打印一张待办（还要改哪几处、活着的会话要不要收、要不要 commit 和跑测试）

### idea-request-notes（15 步，gyb 动手 4 次）

6. [slows/too_heavy] 第 6 步到第 11 步整段：gyb 就坐在这个会话里说了句「你去读吧」，为了读一份 md 却要走 issue open、通知、grant add、issue reply、issue close 五个动作四行账。permission 第一版只有 read:notes 一种、grantee 是角色不是会话，所以批一次就永久覆盖整个 notes/，这套手续一辈子只有第一次有信息量，和「想法要快速、多次迭代」这条总目标对不上
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-build-plan.md:65
   - 改法：`rl init` 时问一次 gyb 要不要当场给 idea 发 read:notes，发了以后就不用走申请，没发才走 issue 那条路

### periodic-reclaim（27 步，gyb 动手 11 次）

7. [slows/too_heavy] 第 12、15 步：回收之后没有任何东西通知 owner，也没有 owner 的收件箱（rl status 是 gyb 的）。owner 是角色不是会话，原来的会话已经被销号，gyb 得亲手为每个 owner 角色开一个终端加载 skill，单子分属几个 owner 就开几个。文档开头写这套东西服务的是想法要快速多次迭代，这一步和它拧着。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:154; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：reclaim --apply 结束时按 owner 分组打印每张单子和一条现成的加载命令，rl status 里加「按角色分的待接单」一段。

### hook-missed-session-end（23 步，gyb 动手 11 次）

1. [slows/too_heavy] 步 2、步 5：文档指名「钩子漏掉的」走 rl reclaim（设计 L126），但 reclaim 的默认阈值是会话 48 小时、单子 72 小时（施工 L178、L179），提醒周期 7 天（施工 L183）。会话死掉 6 小时的时候，文档给的唯一恢复路一条都不触发，这张工单最坏要躺 7 天才有人碰，和设计 L7「想法要快速、多次迭代」打架。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:178; plans/2026-08-16-research-loop-build-plan.md:183
   - 改法：rl status 加一段「holder 会话超过 N 分钟没写任何账的 in_progress 单」，N 默认 30 分钟，和 reclaim 的 48/72 小时分开。

### smoke-fails（44 步，gyb 动手 4 次）

10. [slows/too_heavy] 步 19 到步 30（整个修复回路）：一个 import 报错要走完：落一条 issue、把单子标 stuck、run 会话销号、deploy 读 issue、改代码、回 issue、把单子拉回 todo、重起一个 run subagent、重读慢变量档案、重探空卡、重挑卡、重跑 smoke。至少八次账写入加两次会话生死。文档还把两条捷径都堵死了：run 不许自行重试，下游不许小修，快车道只能由 gyb 事先点名进、单子已经在正常路上时没有中途改走快车道的路。这和「想法要快速、多次迭代」的目标拧着。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:185; plans/2026-08-16-research-loop-next-steps.md:180; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给发射单加一条 smoke 失败专用短路：run 返回 traceback，deploy 在同一会话里就地修完打 rl handoff release 再起 run，issue 照开但不必等回复，并明写这不算 run 自行重试。

### doctor-findings-fix（24 步，gyb 动手 15 次）

6. [slows/too_heavy] 第 9 到 19 步（修第二类）：第二类的真实病因只是一份报告文件没了，修它却要走「打回 → 加载 deploy 会话 → decision stale → start → 重写报告 → done → accept」七步，中间还要新登记一个会话、还要把单子在四个状态之间转一圈。对着「想法要快速、多次迭代」这条目标偏重。
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:91; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:88
   - 改法：给 done_pending_review 的单子加一条 `rl handoff amend ID --report-detail P`：追加一版只换路径、不改状态、校验路径存在。

## 裁决记录（日期）

- 2026-08-17 来自 sync-inbox 问题 12 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「B」）：第二节原则 10 的「数字账默认只列每张单最新一次退出状态为 ok 的行」改成「数字账默认只列每张单最新一次尝试的行、且退出状态是 ok，最新一次不是 ok 的这张单不出」。对回原则 10。
- 2026-08-17 来自 sync-inbox 问题 15 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「B」）：接口一节公共骨架那行的两个可选栏由「`fix_for`、`force_reason`」改成「`force_reason`、`via`」。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 27 的裁决（定义处 `01`，rl-hub-v3 传；gyb 原话「3 不是，可以替我写」）：第二节原则 1 末句「授权（grants）只收裸终端写的行，角色会话里替 gyb 批授权没有意义」改成「授权（grants）只有 gyb 能写：裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收」；第四节（d）行标不认并写上新说法，（b）（c）两行标 gyb 认，那一节末句补一句三条已裁；「没写清」第 4 条末尾记（b）已认。对回原则 1。
- 2026-08-17 来自 sync-inbox 问题 28 的裁决（定义处 `01`，rl-hub-v3 传；gyb 原话「每个角色创建时候，不要自动查收件箱……这个角色就应该先执行刚才idea给他的工作」「C」）：第二节原则 6 末句「角色上线第一个动作是 `rl inbox`」改成「`rl inbox` 是查询命令，不是上线动作：角色被拉起不自动查收件箱，先干拉它起来的那张单，`rl inbox` 谁需要谁敲」。对回原则 6。
- 2026-08-17 来自 sync-inbox 问题 16 的裁决（定义处 `07`，rl-hub-v3 传；gyb 原话「A」）：第二节原则 7 末句「analysis 想先画一张图给 gyb 看也走同一条」后面补「只是合回（`--merged`）只对 deploy 开，analysis 的快车道只有 `--dropped`，要留就走正常路重做」。
- 2026-08-18 问题 1（本份「没写清」第 1 条，parts 与架构总说明的关系；gyb 原话「那个旧的说明已经可以不要了 毕竟都变成新的了」「是的 那些分的就是说明，总的没用」）：施工步 2 的 `research-loop/ARCHITECTURE.md` 不写，定稿的拆分文档本身就是架构说明；第二节末段、第八节步 2 照改，编号保留不重排。对回原则 8。
- 2026-08-18 语言（问题 1 顺带；gyb 原话「所有的东西都默认用英语，插件本体里面用英语写，然后不要出现语言相关的约束，就默认只有英语就可以了，不需要强调任何语言」）：一切默认英语，任何 part 里不写语言相关的约束。本份没有语言字样，别处的列进「要同步到别处的」。对回原则 8（一处为准、不写多余规矩）。
- 2026-08-18 问题 2（「没写清」第 2 条，parts 与源文档谁为准；gyb 原话「b」）：拆分文档定稿为准，两份源文档从此不再回写、开头各加一句「已被拆分文档取代，只留作历史」，打架按拆分文档。写进第二节原则 8 末尾。对回原则 8。
- 2026-08-18 问题 3（「没写清」第 3 条，（a）到（i）回退清单；gyb 原话「a」）：（a）（e）（f）（g）（h）（i）六条一并裁认，九条全裁完，不写回退清单；第四节标题、导语、六行、末句照改。对回原则 8（后裁的赢，不留两个值）。
- 2026-08-18 问题 4（「没写清」第 5 条，总验收怎么算过；gyb 原话「总验收是b」）：不预定判分办法；gyb 每看完一对产出说一句「过 / 不过」加一句原因，记进本份裁决记录，五对都过才算过。写进第一节。对回原则 8。
- 2026-08-18 问题 5（「没写清」第 6 条，第三轮模拟；gyb 原话「第三轮先不跑，等整个plan完事，施工完成后再说」）：第三轮先不跑，等整套拆分文档定稿、施工完成之后再说；第七节手续量表标「改后未重数」。对回原则 8。
- 2026-08-18 问题 7（「没写清」第 7 条，原则 9、10、11 缺第一轮对应；gyb 原话「b」）：三条原则括号里各加「出处见第七节说的第二轮归堆，第一轮没有对应条目」。对回原则 8。
- 2026-08-18 问题 8（第五节第 4 条「两处原文不一致」；gyb 原话「a」）：那一条并成一句「全量搬作废，new1 老代码由 gyb 手动按需搬（裁决 2）」，「两处原文不一致」段删掉。对回原则 8。
- 2026-08-18 「没写清」第 4 条（原则打架按谁）2026-08-17 已由 sync-inbox 问题 27 裁掉，本次只销号不再问。
- 2026-08-18 来自 `09-common-and-feedback.md` 定稿（`aaca3c9`，rl-hub-v5 传；gyb 原话「a」）：索引里 `09` 那行加「判断类检查清单」。
- 2026-08-18 来自 `08-trees-init-and-host.md` 定稿（`eb02403`，rl-hub-v5 传；gyb 原话「你就说我也定了，让统筹给06 00也改了」）：原则 2「钩子只管 Write 和 Edit 两个工具」改成管 Write、Edit、Bash 三个（Bash 分支解析重定向、`tee`、`sed -i`、`mv`/`cp` 目标路径），「其余一切」里 Bash 改成「钩子解析不出的 Bash 写法」；第三节裁决 5 注后改；第八节步 1 注建 `agents/` 层不建 `workflows/`；第九节索引 `08` 覆盖栏加 `agents/` 层。对回原则 2。

## 要同步到别处的

- `30-build-steps-verify-tests.md`：施工步骤表步 2 「架构文档 `research-loop/ARCHITECTURE.md`」改成「不做（2026-08-18 gyb 裁：定稿的拆分文档就是架构说明），编号保留」；步 8 总验收的验收栏「gyb 自己看」后面补「每对产出说一句过 / 不过加一句原因，记进 `00` 裁决记录，五对都过才算过」；「第三轮模拟要不要跑」那句改成「先不跑，等施工完成后再说」；步 6 那行「（英文，……）」去掉「英文」二字。（已同步 2026-08-18 rl-hub-v4）
- `08-trees-init-and-host.md`：「两处原文不一致」段里插件目录要补的三样去掉 `ARCHITECTURE.md`，只补 `.claude-plugin/plugin.json` 和 `README`。（已同步 2026-08-18 rl-hub-v4）
- `09-common-and-feedback.md`：「中文底稿给 gyb 过，正式版是英文」和「没写清」里英文措辞那条，按「一切默认英语、不写语言约束」改：去掉语言字样，`rule-NN` 编号不变这一句保留。（已同步 2026-08-18 rl-hub-v4）
- `22-pair-idea-analysis.md`：「没写清」里「（e）待裁」那条改成「（e）2026-08-18 gyb 认：分析单开单时口径可以是 proposed，交活才要全 approved」。（已同步 2026-08-18 rl-hub-v4）
- `HANDOFF.md`（统筹的传播规矩）：两份源文档从此不再回写；统筹在两份源文档开头各加一句「已被拆分文档取代，只留作历史（2026-08-18）」；「（a）到（i）gyb 还没裁」改成已全裁；第三轮那句改成「施工完成后再说」。（已同步 2026-08-18 rl-hub-v4）
- 两份源文档：只加取代注，不再回写任何裁决（含本份的这几条）。（已同步 2026-08-18 rl-hub-v4）
