# research-loop 使用场景清单：第三轮预演的题目（2026-08-17）

这份清单列的是 gyb 真正用起 research-loop 的时候会开口提的要求，一个要求一个场景。每个场景按 `plans/research-loop-parts/` 里现在的写法把路走一遍，把中途会岔出去的情况列出来，最后写清预演要回答哪几个问题。用法和第二轮模拟一样：一个场景交给一个 subagent 预演，subagent 只读 `plans/research-loop-parts/` 这个目录（含每份末尾的「裁决记录」），按现在的规矩一步一步走，报步数、gyb 亲自动手的次数、以及每一处走不通或者要靠猜的地方。

清单里的走法是我按 parts 读出来的，不是裁决；写「计划里没写」的地方，是我在 parts 里没找到对应条目，预演的 subagent 要自己再核一遍。

## 这份清单怎么用

预演的 subagent 每个场景一个，模型用 opus（本机全局规则：subagent 不用 fable，需要判断力的任务用 opus）。给 subagent 的输入是这份清单里的一张场景卡加 `plans/research-loop-parts/` 目录路径。要求 subagent 输出四样东西，格式沿用 `plans/2026-08-16-research-loop-simulation-round2.md`：

1. 逐步的走法表：每一步写谁做、打的什么命令或者做的什么动作、账上落哪一行、依据是 parts 里哪个文件哪一行。
2. 步数和 gyb 亲自动手的次数。
3. 摩擦条目：每条标严重度（`blocks`、`slows`、`cosmetic`）和种类（`missing`、`contradiction`、`ambiguous`、`too_heavy`、`principle_violation`、`blocked`、`guessed`），写第几步、原文、依据、改法。
4. 场景卡「预演要回答的问题」那一段里每个问题的答案，答不出来就写「parts 里没写」。

parts 和两份源文档谁为准这件事还没裁（`00-overview.md` 留给 gyb 第 2 条），所以 subagent 只读 parts；parts 内部两份说法打架的地方按 `contradiction` 报，不自己裁。

## 场景总表

| 编号 | 场景名 | gyb 的一句话 | 主要走到的 part | 和第二轮的关系 |
|---|---|---|---|---|
| 1 | idea-from-notes | 按这份笔记帮我提几个想法 | 01、02、10 | 第二轮 idea-request-notes 只走了申请读权，没走到出想法 |
| 2 | browse-ideas-derive-new | 把现有想法列给我看，从里面推几个新的 | 02、05、10 | 新 |
| 3 | retire-old-idea | 那个方向不好使了，记一笔别再派 | 02、04、10、20 | 第二轮 decision-revised 走的是改版重派，没走废除 |
| 4 | deploy-idea-to-code | 把这条决定做出来 | 10、11、20 | 第二轮 new-idea 走过主路，这次走岔路 |
| 5 | run-code-get-results | 跑起来，出数 | 11、12、21、23 | 第二轮 run-crash-midway、n-launch-orders 走过失败和批量，这次走顺路和查进度 |
| 6 | tweak-two-params-rerun | 两个参数各改一下再跑一次，我要和上一版比 | 06、07、11、20、21、23 | 第二轮 param-tweak 走的是旧写法（45 步），这次按新写法重走 |
| 7 | extend-run-more-samples | 上次跑了 200 题，再加 800 题续上 | 03、21、23 | 新 |
| 8 | audit-code-vs-idea | 核对代码是不是按决定做的：算法流程、数据来源、模型设定 | 14、25 | 第二轮 result-wrong-review 是结果不对才审，这次是跑之前审 |
| 9 | inspect-generated-text | 把这次实验生成的文字给我看几条 | 08、13、23 | 新 |
| 10 | dispatch-subagents-read-cases | 派几个 subagent 分头看十次实验的 case | 01、05、06、14 | 新 |
| 11 | aggregate-runs | 把这几次跑的数字汇总成一张表一张图 | 13、22、23 | 第二轮 plot-new-plan、next-plan-after-results 走过画一张图，这次走多 run 汇总和分组键缺失 |
| 12 | daily-queries | 现在跑到哪了、那台卡上跑的是啥、这个数从哪来 | 01、05 | 第二轮 result-wrong-review 步 1 到 5 促成了 `rl trace`，这次单独走 |
| 13 | stop-running-experiment | 那个跑着的停掉 | 04、12、20、21 | 第二轮 decision-revised 部分覆盖 |
| 14 | setup-model-and-env | 换一个模型再跑（要下权重、要建环境） | 08、11 | 新 |
| 15 | gyb-freehand-run | 我自己在终端随手跑一把看看 | 01、03、05、23 | 新 |

第二轮已经走过、这次不重开的场景：feedback-round（改一条规矩）、two-idea-lines-parallel（两条线并行）、periodic-reclaim（定期回收）、hook-missed-session-end（钩子漏销号）、smoke-fails（smoke 失败）、doctor-findings-fix（doctor 修账）、gyb-manual-takeover（gyb 手动接单）。这七个场景的摩擦已经抄进各 part 末尾，第三轮要不要重走由 gyb 定；重走的话重点数手续量，看新写法砍掉了多少步。

## 场景 1：gyb 拿一份笔记要 idea 提想法

gyb 的原话：「我在 `notes/2026-08-17-survey.md` 里写了一份调查，你按这份笔记帮我提三四个能做的想法，我们谈定了就落成决定。」

开始的时候账上有什么：九本账是空的或者只有别的线的决定；gyb 在 `rl init` 的时候要么给了 idea `read:notes`，要么没给。两种起点各走一遍。

计划里的走法：gyb 在终端用 `/` 加角色 skill 名加载 idea，钩子把会话登记进 sessions 账（`04` 第六节）。idea 先 `rl inbox`（`10`「上线第一个动作」）。idea 读 `notes/` 之前先看有没有 `read:notes` 的 grant：有就直接读；没有就 `rl issue open --to gyb --kind request`，gyb 到裸终端 `rl grant add --to idea --permission read:notes`（`01` 第一节第 1 条，`10`「申请读 notes/」）。谈定之后每条想法落一条决定：gyb 在场定的那一版由 idea 替 gyb 记，`rl decision add --text ... --source file:notes/2026-08-17-survey.md#<小节> --as-gyb --quote "<gyb 原话>"`，落 `decisions.idea.jsonl`、actor 记 gyb（`02`「六个决定文件」）；idea 自己推出来的那一版 actor 记 idea、不带 quote。一条决定链的第一条决定来源必须指现有代码文件或者 `notes/` 里的一行（`02`「来源三类与锚点」）。

会岔出去的地方：gyb 的材料不在仓库里（NFS 上的 pdf、home 下别的目录），`file` 类来源只收仓库内路径，gyb 得先把要引的那一段搬进 `notes/`；gyb 没开 idea 会话、直接在裸终端自己 `rl decision add`，落 `decisions.gyb.jsonl`；一次谈出四条想法互相有先后依赖，每条新开的决定 `root_id` 都是自己（`02`「root_id 与 line」），四条就成了四条研究线，`rl status --group-by line` 会分成四组；idea 谈到一半要读 `analysis/` 里以前的图，reads 栏里有 `analysis/`，直接读。

预演要回答的问题：grant 没给的时候，那条 `request` issue 谁 close（`10` 留给 gyb 第 8 条）；idea 开完 issue 等 gyb 回话的这段时间会话怎么办、销不销号、销了谁再叫起 idea（`10` 留给 gyb 第 9 条）；一次谈出的多条想法要不要有一个共同的根，还是各成一线；仓库外的材料怎么进来才能被决定引用。

## 场景 2：gyb 要看现有的全部想法，再从里面推新的

gyb 的原话：「把现在所有想法列出来，标一下哪些做过了、哪些还没派、哪些废了，然后我们从里面推几个新的。」

开始的时候账上有什么：决定账里有二十来条决定，分两条线，一部分派过工单跑过 run，一部分只有决定没派单，两条已经 retired。

计划里的走法：在 idea 会话里，idea 用查询命令拼这张图：`rl decision list [--actor A] [--line L]` 列决定，`rl decision show ID --history` 看各版本，`rl decision show ID --with-runs` 沿 `parent_id` 链反查每条决定派出的单子和 run 与 metrics，`rl trace` 从任何编号打整条链（`02`「`rl decision` 的全部子命令」，`05`「rl trace」）。新想法落新决定，来源用 `decision` 类指旧决定的编号加版本；两条旧决定并成一条新决定用 `rl decision merge ID1 ID2 --text --root ID`（`02`「update、confirm、retire、merge」）。idea 要念数字给 gyb 听的时候，单个 run 的原始指标可以直接从 runs 账念，跨 run 的对比一律走 analysis 的分析单（`22` 第七节）。

会岔出去的地方：gyb 问「哪些做过了」，回答要跨决定、派活单、runs 三本账，`--with-runs` 打出来的东西够不够一眼看出「派过没派过、跑过没跑过、验收了没有」；gyb 问「这两条方向哪个数好」，idea 不能自己算跨 run 的比较，只能提议开分析单；gyb 顺口说「那 dec-idea-0004 就按 dec-idea-0009 的做法改」，属于同一件事换做法，追加一版而不是新开一条。

预演要回答的问题：`rl decision list` 默认列不列 retired 的决定、有没有按 status 过滤的开关（`02` 只写了 `--actor` 和 `--line`）；「做过没做过」这个问题按现在的查询命令要敲几条才拼得出来；idea 从旧决定推出新决定的时候，来源里除了 `decision` 类要不要同时带 `run` 类，parts 有没有说。

## 场景 3：gyb 要把一条旧想法标成不好使了

gyb 的原话：「dec-idea-0007 那个方向已经不好使了，在上面记一笔为什么，别再往下派了。」

开始的时候账上有什么：dec-idea-0007 第 2 版下面挂着一张 accepted 的工单、一张 in_progress 的工单（deploy subagent 正在写代码）、一张 in_progress 的发射单（GPU 正在跑）。

计划里的走法：在 idea 会话里，idea 替 gyb 打 `rl decision retire dec-idea-0007 --source run:<run_id> --source file:analysis/<那张图> --as-gyb --quote "<原话>"`，追加一版标 retired、来源默认继承上一版再加上这次给的（`02`「update、confirm、retire、merge」）。写完那一刻 rl 当场列出引着旧版而没到终态的单子和那些单子的 holder（`02`「过版、改版那一刻的打印」）。停不停由 gyb 点名：停就 `rl handoff withdraw ho-XXXX --reason ... --quote ... --cascade`，级联把发射单一起收；正在跑的 run 的看门狗每轮查到 withdrawn 就走中断，run 打 `rl run finish --exit killed` 加收尾（`21` 第十二节）。不停的话单子按派出时那一版继续做，retired 决定名下的活单进 `rl status` 段 6 和 doctor 第 15 项。

会岔出去的地方：gyb 说的是「记一笔但先别废」，那是 `rl decision update`（换正文）或者 `rl decision confirm`（正文不变只加来源），不是 retire；gyb 不开 idea 会话、在裸终端直接 retire 这条 idea 的决定，「谁能调」是同 actor 但 gyb 豁免，这一版落哪个文件；收回之后 deploy 写了一半的 `experiments/` 代码和产物根里半截产物目录怎么处置；有 holder 的单子被收回时 rl 开的 `withdrawn` 通知类 issue，收件人是 holder 的角色和 owner，收件人做完了自己 close（`04` 第九节），可 holder 那个 subagent 已经返回了。

预演要回答的问题：gyb 在裸终端给别人的决定追加一版落 `decisions.gyb.jsonl` 还是 `decisions.idea.jsonl`（`02` 「六个决定文件」标了三处口径不一致，`02` 这一份在 README 里状态是「未开」）；收回之后代码和产物的处置（`20` 留给 gyb 第 7 条，`11` 留给 gyb 第 7 条）；holder 已经返回的 `withdrawn` 通知谁 close。

## 场景 4：gyb 要把一条决定做成代码

gyb 的原话：「把 dec-idea-0012 做出来。」

开始的时候账上有什么：dec-idea-0012 第 1 版 active，来源指 `notes/` 里一节；`experiments/` 里还没有对应代码；new1 的老代码里有一段能复用。

计划里的走法：idea 打 `rl handoff open --type work_order --to deploy --decision dec-idea-0012@1 --explain "<idea 自己写的解释>"`，单子落 todo，`dispatch=auto`，idea 后台起一个 deploy subagent 接走，idea 会话继续可用（`20`「开单」，原则 11）。deploy subagent 加载 skill 登记进 sessions，`rl inbox`，`rl handoff start ho-XXXX`。deploy 在 `experiments/` 下这张工单自己的目录里写代码，写两份部署报告（`method` 不带文件、必须原样抄决定编号加版本；`detail` 带文件清单和 issue 结论），填 `code_paths`，`rl handoff done`（`11` 第三节）。改变实验结果的选择记进 `decisions.deploy.jsonl`（`11` 第四节）。idea 验收先读 `method` 再读 `detail`，`rl handoff accept` 或者 `rl handoff reject --reason`（`20`「验收」）。

会岔出去的地方：gyb 说「先别派，我先看看单子」，开单带 `--no-dispatch`；gyb 说「这个我自己写」，开单带 `--manual`，gyb 自己开 deploy 会话接；deploy 要用 new1 老代码，老代码由 gyb 手动搬进 `experiments/`，deploy 只提醒（`08` 第六节）；deploy 要往仓库根 `run.py` 注册表挂一条，钩子放行，走三条纪律（`11` 第五节）；deploy 中途卡住，先 `rl issue open` 再 `rl handoff stuck`；gyb 坐在 deploy 会话里当场说「这里用第 12 层」，落 `decisions.deploy.jsonl`、actor 记 gyb、带 quote，不算 deploy 自决（`11` 第四节）。

预演要回答的问题：部署报告目录名怎么拼（`11` 留给 gyb 第 1 条）；deploy 卡在工单上开的 issue 归 idea 还是 gyb（`20` 留给 gyb 第 1 条）；idea 验收要不要读 `code_paths` 里的代码本身（`10` 留给 gyb 第 6 条）；`--manual` 的单子 gyb 接完谁验收（`10` 留给 gyb 第 11 条）；后台起 subagent 的机制、subagent 里钩子装不装得上，还挂在待验证第 8、9 条上，预演只能按「能起、能装」假设走，要把假设标出来。

## 场景 5：gyb 要把代码跑起来出数

gyb 的原话：「跑起来，出数。」

开始的时候账上有什么：场景 4 的工单已经 accepted 或者还在 in_progress（deploy 手上）；GPU 集群按 `ops/gpu_state.md` 的现状。

计划里的走法：deploy 打 `rl handoff open --type launch_order --to run --parent ho-XXXX --command ... --workdir ... --track ... --config model=... dataset=... split=... lr=...`，rl 从父单抄 `decision_refs`、分 `run_id`（`<ho-id>-a1`）、算 `line`（`21` 第三、四节）。deploy 后台起 run subagent。run 接单先看最新尝试有没有 launched 未 finished 的 run 行（没有），然后读 `gpu_state_path`、跑 `launcher.free_cmd` 探卡、smoke 并逐步计时 `rl handoff estimate`、发射前 commit、`launcher.launch_cmd` 发射、`rl run add` 落发射版（`12`「照 gpu-run 八阶段的对照」）。看门狗起来，只判只写自己的状态文件。跑完 `rl run finish RUN_ID --exit ok --metric acc=0.83 --data-path <产物目录里的那个文件>`，`finish` 顺带算 `actual_seconds`、跑反常预警、调 `launcher.finish_cmd` 落宿主 `ops/runs.jsonl`（`12`「Phase 6a」）。`rl handoff done`，deploy `rl handoff accept`，deploy 把 run_id 和关键指标补进 `detail` 报告（`rl handoff amend`），再提工单验收（`11` 第九节）。

会岔出去的地方：gyb 中途问「跑到哪了」，`rl status` 段 1 的发射单行带 `log_path` 和 `watch_cmd`；跑出来的指标正好是 1.0，`rl run finish` 当场开 `anomaly` issue 给 gyb；run 会话死了，下一个 run 会话接单时认领（第二轮 run-crash-midway 走过）；deploy 一次开五张同 batch 的发射单，一个 run 会话 `--batch` 接（第二轮 n-launch-orders 走过）。

预演要回答的问题：deploy 验收发射单的时候看什么、什么情况下会 reject 一张 `exit_status=ok` 的发射单（`21` 留给 gyb 第 9 条）；`track` 从哪来，工单上没有 track 栏（`11` 留给 gyb 第 2 条）；这条顺路上 gyb 亲自动手几次、写了几行账；两本 runs 账（`loop/runs.jsonl` 和宿主 `ops/runs.jsonl`）在这条路上各落几行。

## 场景 6：gyb 要把两个参数改了再跑一次，还要和上一版比

gyb 的原话：「把学习率和 batch size 各改一下再跑一次，我要和上一版比。」

开始的时候账上有什么：场景 5 跑完，工单 accepted，runs 账里有一行 ok 的 run，`config` 里有 `lr` 和 `batch_size`。

计划里的走法有两条，各走一遍。第一条是快车道（`07`）：gyb 点名，deploy `rl ql open --role deploy`，在 worktree 上改两个参数、派 gpu-runner 跑，数字 `rl scratch add` 进杂账不进 runs 账，`rl ql close --merged --handoff ID`，gyb 亲自 merge，deploy 补一张 quick_lane 工单加一条 `decisions.deploy`；要正式数字得按正常路再开发射单跑一遍（`07` 第七节）。第二条是正常路：参数属于哪一层的决定先分清，是 idea 层的决定就 `rl decision update` 追加一版，是 deploy 自决就 `decisions.deploy` 新条；然后要么在原工单下面再开一张发射单（config 里 `lr`、`batch_size` 换新值），要么新开一张工单；两次 run 都在 runs 账里之后，「和上一版比」是跨 run 对比，走 analysis 的分析单和口径账，图口径 `group_by` 取 `config.lr`（`22` 第七节，`23`「config 字典」）。

会岔出去的地方：快车道跑出来的数字不在 runs 账里，analysis 的分组维度只能取 runs 行的字段、`config.<键>`、approved 指标口径三样（`23`），快车道那次跑的数就汇不进对比；原工单已经 accepted 是终态，`rl handoff reissue` 只对非终态，能不能在一张终态工单下面再开发射单 parts 没写；两次 run 的 `config` 里同一个超参一次叫 `lr` 一次叫 `learning_rate`，analysis 按哪个分组（`23` 留给 gyb 第 5 条）。

预演要回答的问题：这一件事按新写法（`rl ql open/close`、一份简报、后台派活）走下来还剩多少步、gyb 动手几次，和第二轮 param-tweak 的 45 步、8 次对比；快车道的数字到底进不进 runs 账（`07` 留给 gyb 第 2 条、`23` 留给 gyb 第 7 条，两处都还没裁），不进的话「和上一版比」是不是必然要正式重跑一遍；两个参数的改动记在哪一层的决定账；一张 accepted 的工单下面还能不能挂新的发射单。

## 场景 7：gyb 要把上一次的任务量加大，接着上次的产物续

gyb 的原话：「上次那个只跑了 200 题，再加 800 题，接着上次的产物续，别从头来。」

开始的时候账上有什么：runs 账里 `ho-0013-a1` 是 ok 的，`data_path` 指到 `<artifact_root>/ho-0013-a1/outputs.jsonl`，里面 200 条。

计划里的走法：parts 里没有「续跑」或者「增量」这个概念。按现有规矩能拼出来的路是：deploy 在同一张工单下再开一张发射单，`config` 里题数写 800、命令里带上一次的 `data_path` 当输入，run 分到新的 `run_id`（`<新 ho-id>-a1`），产物落 `<artifact_root>/<新 run_id>/`（`08` 第一节的约定），两次的产物由 analysis 用 `code_path` 类口径合起来算（`13` 第三节）。`rl handoff amend` 追加一次尝试只允许在 `todo` 和 `stuck` 上做（`21` 第十一节），已经 accepted 的发射单加不了 attempt；runs 账只增不改，旧 run 的 `metrics` 改不了。

会岔出去的地方：deploy 想让新 run 直接往旧 run 的产物目录里追加，违反「产物目录是 `<artifact_root>/<run_id>/`」的约定，看门狗和 analysis 都按这条约定找；两次 run 之间「后一条依赖前一条的产物」这层关系，runs 行上没有字段表达，`rl trace` 从新 run 只能回到发射单和工单，回不到旧 run；gyb 想直接在快车道加 800 题，数字进杂账。

预演要回答的问题：增量这件事是要在计划里加一条路（比如发射单上的一种「续跑尝试」，或者 runs 行加一个「依赖的 run」字段），还是明写「一律新 run 加 analysis 合并」；按后一种走，从 gyb 一句话到合并后的数字要几步；两次产物合并算不算「跨 run 聚合」，是不是必须过口径批准。

## 场景 8：gyb 要核对代码是不是按决定做的

gyb 的原话：「帮我核对现在这份代码是不是按 dec-idea-0012 做的：算法流程对不对、数据从哪来、用的什么模型、什么设定。」

开始的时候账上有什么两种起点：一种是场景 4 刚交活、还没跑过 run；另一种是场景 5 跑完了、runs 账里有 commit。

计划里的走法：gyb 手动加载 reviewer，reviewer `rl inbox`，`rl session focus --decision dec-idea-0012`（`14`「上线第一个动作与 session focus」）。读的顺序是死的：先读 gyb 和 idea 的决定和最终代码，再读运行记录和分析代码，最后读 deploy 的决定账和部署报告（`14`「什么都能读，但读的顺序是死的」）。要审的代码清单从工单的 `code_paths` 来，审哪一版按 runs 账里的 commit，不审当前工作树（`14`「审哪一版代码」）。数据来源和模型设定在发射单 `config` 的 `dataset`、`split`、`model` 和 `method` 报告里，reviewer 拿 `method` 报告当锚。产出是 `review/<日期>-dec-idea-0012.md`，一条问题五栏，第五栏报「决定账里没写但代码里做了的选择」（`14`「清单」）。gyb 看完定动不动，动的话 idea 按清单 `rl decision update` 或 `add`，来源指清单路径加锚点（`25`「审出问题之后」）。

会岔出去的地方：还没跑过 run 的时候没有 commit 可审；gyb 只想让 idea 在验收工单的时候顺手核，不想另开 reviewer；reviewer 想把「逐条对照 method 报告和代码」这件事拆给几个 sonnet subagent，`05`「rl doctor」末段写了 reviewer 按 `common/` 里的清单派 sonnet subagent 逐条查，`14` 第一节又写这条和「不开 issue、不派活」冲突、等 sync-inbox 问题 6 裁。

预演要回答的问题：没有 run 的时候 reviewer 审哪一版代码；idea 验收要不要读代码（`10` 留给 gyb 第 6 条）；reviewer 派不派 subagent（sync-inbox 问题 6）；清单落盘之后 idea 怎么知道有新清单（`25` 留给 gyb 第 3 条）；清单没有状态、没有关掉的办法，gyb 看完之后「不动」这一支往哪写（`25` 留给 gyb 第 5、6 条）。

## 场景 9：gyb 要看这次实验生成的文字

gyb 的原话：「把这次实验生成的文字给我看几条，我想看看模型到底写了什么。」

开始的时候账上有什么：runs 账里 `ho-0013-a1` 是 ok 的，`data_path` 指到产物目录里的输出文件。

计划里的走法：产物在 `<artifact_root>/<run_id>/`，`data_path` 在 runs 收尾版上（`23`「metrics 与 data_path」）。gyb 自己 `rl run show ho-0013-a1` 取路径去读，什么都不用写账。让角色去看的话，parts 里没有哪个角色的活是「读几条样例给 gyb 看」：analysis 的活是「只算 gyb 说要看的数、只画 gyb 说要画的图」（`13` 第二节），idea 的活是谈决定和派单，读原始产物在 idea 的 reads 栏里没有（读不设权，读得到，但不是 idea 的活）。

会岔出去的地方：gyb 说「挑错得最离谱的五条给我」，挑选就是一个派生统计，按 `13` 第三节要走口径账的 `code_path`；gyb 想把这几条样例写进决定的来源，来源只有 `decision`、`file`、`run` 三类，`run` 类只指到 run_id，指不到具体某一条样例，要指就得先把样例落成仓库内文件（落哪个目录、谁写）；gyb 想「先随手看一眼」，analysis 的快车道只写了「先画一张图」，没写「先贴几条文字」。

预演要回答的问题：定性看样例归哪个角色、留不留痕；「挑几条」算不算分析、要不要过口径；样例要被引用的时候落哪个目录；analysis 快车道能不能用来贴文字。

## 场景 10：gyb 要派几个 subagent 分头看很多实验的 case

gyb 的原话：「派几个 subagent，一人看一次实验的 case，各自总结问题回来给我。」

开始的时候账上有什么：runs 账里十次 ok 的 run，分属两条线。

计划里的走法：parts 里派活的关系只有角色 json 的 `dispatches_to`：idea 派 deploy 和 analysis，deploy 派 run（快车道里派 gpu-runner），run、analysis、reviewer 不派任何人（`10`、`11`、`12`、`13`、`14` 各自的四栏）。reviewer 派 sonnet subagent 逐题查这条待裁（场景 8 提过）。所以按现在的写法，「派一群 subagent 各看一次实验」只有 gyb 自己在裸终端用 Agent 工具派，subagent 不加载角色 skill、不登记 sessions、读不设权所以读得到产物；subagent 的总结落成文件的时候，`notes/` 只有 gyb 写，`analysis/` 只有 analysis 写，`review/` 只有 reviewer 写，gyb 豁免钩子哪里都写得进去，但 init 追加到 CLAUDE.md 的那一句纪律写的是「没有 gyb 允许，experiments/、analysis/、review/、loop/ 只能在加载了对应角色的会话里改」（`08` 第一节）。

会岔出去的地方：gyb 在 analysis 会话里说「你派几个 subagent 去看」，钩子只挂 Write 和 Edit，Agent 工具不拦，analysis 派得出去；派出去的 subagent 没有角色、读不到会话状态文件，按 `05`「actor 怎么定」的判法这个 subagent 敲任何 rl 写命令都会被当成裸终端、actor 记 gyb；subagent 往 `analysis/` 写总结文件，钩子绑在哪个会话上、subagent 继不继承，挂在待验证第 8 条上。

预演要回答的问题：批量定性审阅这件事归哪个角色，还是明写只有 gyb 自己派；无角色的 subagent 敲 rl 写命令时 actor 被判成 gyb 这个口子要不要堵；这类 subagent 的产出要进决定来源的话落哪；十个 subagent 的模型按本机全局规则该用 sonnet 还是 opus，parts 里对「角色之外的 subagent」有没有说法。

## 场景 11：gyb 要把几次跑的数字汇总成一张表和一张图

gyb 的原话：「把这几次跑的数字汇总成一张表和一张图，横轴学习率，按模型分组。」

开始的时候账上有什么：runs 账里六次 ok 的 run，四次的 `config` 里有 `model` 和 `lr`，两次早期的 run 的 `config` 里没有 `lr`；另有一次快车道跑的数字在杂账里。

计划里的走法：idea 或 gyb 开分析单 `rl handoff open --type analysis_order --to analysis --eval ...`，开单时口径可以还是 proposed（`22` 第三节）。analysis 先问 gyb 要统计什么，再 `rl eval propose --kind metric ...`（`metrics_key` 直接取 runs 的键，或者 `code_path` 现算）和 `rl eval propose --kind figure --group-by config.model --x config.lr --y eval-XXXX --uses eval-XXXX`（`13` 第三节）。gyb 一句 quote 批一组 `rl eval approve eval-0004 eval-0005 --quote`。analysis 算完，notebook 和小图进 `analysis/`，大文件进 `analysis_artifact_root`，`rl handoff done --notebook P --figure P`，前提是 `output_paths` 存在且 `evaluation_refs` 全部 approved（`22` 第四节）。owner 验收。

会岔出去的地方：两次早期 run 缺 `lr` 这个分组键，analysis 开 `cannot` issue 给 gyb，gyb 三选一：补跑、换口径、走 `code_path` 从产物目录现算（`23`「分组键缺了怎么办」）；快车道那次的数字不在 runs 账里，汇不进去；gyb 说的「一张表」，口径只有 `metric` 和 `figure` 两类，表格归哪一类；gyb 只想先看一眼图，走 analysis 快车道 `rl ql open --role analysis`，图落 `analysis/scratch/`。

预演要回答的问题：表格口径归哪一类；gyb 在裸终端开的分析单 `dispatch=auto` 时谁去后台起 analysis subagent（`22` 留给 gyb 第 4 条）；owner 拿到 notebook 和图按什么标准点头或者打回（`22` 留给 gyb 第 6 条）；这条路上 gyb 亲自动手几次，和第二轮 next-plan-after-results 的 16 次对比。

## 场景 12：gyb 每天要问的三个问题

gyb 的原话有三句：「现在都跑到哪了」「那台卡上跑的是啥」「这个 0.83 是按哪条决定跑出来的」。

开始的时候账上有什么：两条线并行，三张发射单在跑，一张工单等验收，一条口径等批，一条 issue 归 gyb。

计划里的走法：第一句是 `rl status`，十段（`01` 第四节），第一行打印距上次 reclaim 几天。第二句是 `rl status` 段 1 里发射单那一行的 `watch_cmd` 和 `log_path`，gyb 拿 `watch_cmd` 去看；反过来「tokyo106 的 3 号卡上是谁」要从 runs 账的 `host`、`gpus` 反查，`rl run list` 的过滤开关只有 `--handoff`、`--decision`、`--batch`、`--line`、`--all`（`23`「查」）。第三句是 `rl trace ho-0013-a1`，一条命令打出 run 到发射单到工单到决定各版本（`05`「rl trace」）。

会岔出去的地方：gyb 想按机器或者按卡看，没有这个过滤维度；gyb 想看「这条线这周跑了几次、几次 ok」，`rl run list --line L` 默认只出每张单最新尝试且 ok 的行，`--all` 才全出（`23`）；gyb 想在手机上收到通知，桌面通知机制还是待验证第 6 条。

预演要回答的问题：按机器或者按卡反查现在要敲几条命令；`rl status` 十段一屏能不能看完，段 1 三张发射单加段 3、4、2 的东西一共多少行；`rl run list --line L` 怎么解析，runs 行上没有 `line`（`23` 留给 gyb 第 3 条）。

## 场景 13：gyb 要把一个正在跑的实验停掉

gyb 的原话：「那个跑着的停掉，方向不对。」

开始的时候账上有什么：一张发射单 in_progress，holder 是一个 run subagent，GPU 在跑；父工单 in_progress，holder 是 deploy subagent。

计划里的走法：owner 收回。发射单的 owner 是 deploy，工单的 owner 是 idea；gyb 说「停掉」，要么 gyb 在裸终端直接 `rl handoff withdraw ho-XXXX --reason ...`（gyb 豁免「谁能写」），要么在 idea 会话里 `rl handoff withdraw <工单> --reason ... --quote ... --cascade` 连发射单一起收（`20`「收回与 cascade」）。有 holder 的时候 rl 开 `withdrawn` 通知给 holder 的角色和 owner。看门狗每轮查到 withdrawn，run 走中断：`rl run finish --exit killed` 加收尾（杀进程、释放显存、宿主销号），不改单子状态（`21` 第十二节）。

会岔出去的地方：gyb 只想停发射单不停工单（deploy 继续改代码），只收发射单；gyb 只想「暂停一下过会儿再跑」，parts 里没有暂停，只有收回和重开；收回之后 deploy 那半截代码和产物怎么办；gyb 在裸终端收别人的单子越过了 owner，rl 给 owner 发 `fyi`。

预演要回答的问题：收回一张正在烧卡的发射单，从 gyb 一句话到 GPU 真的释放，中间隔几轮看门狗采样、几行账；「暂停再续」要不要有；收回之后的代码和产物处置（`20` 留给 gyb 第 7 条）。

## 场景 14：gyb 要换一个模型再跑，权重和环境都还没有

gyb 的原话：「换 Qwen3-8B 再跑一遍，权重还没下，环境可能也要动。」

开始的时候账上有什么：场景 5 的工单 accepted，`experiments/` 里的代码写死了模型路径。

计划里的走法：换模型是改变实验结果的选择，要么 idea 层决定 update，要么 deploy 自决进 `decisions.deploy`（`11` 第四节）。下权重和建环境这两件事在 parts 里没有对应的角色动作：deploy 的 `dispatches_to` 只有 run 和快车道里的 gpu-runner（`11` 第十一节），本机的 env-runner 这类 agent parts 里没提；钩子只管 Write 和 Edit，deploy 自己用 Bash 下权重到 NFS、用 uv 建环境都不会被拦。权重落 `/net/.../models`、环境落 home，都在仓库外，deploy 的报告要不要列这两样、决定账要不要留痕，`11` 第五节的三条纪律只写了仓库根 `run.py`、`MAP.md`、`ops/` 这些宿主文件。然后开发射单，`config.model` 换新值，走场景 5。

会岔出去的地方：新模型要新的 transformers 版本，撞上 new1 的双环境铁律（`probe-env-rules`），deploy 要不要开 issue 给 gyb 还是自己判；下权重要一个小时，deploy 会话等还是派出去；run 探卡发现新模型显存不够，属于四种失败里的哪一种。

预演要回答的问题：环境和权重这类既不是写代码也不是 GPU 的杂活归谁做、派不派 subagent、留痕在哪；仓库外的改动（环境、权重）要不要进部署报告和决定账。

## 场景 15：gyb 要自己在终端随手跑一把

gyb 的原话：「我自己在终端随手跑一把看看，不走你们那一套。」

开始的时候账上有什么：任意。

计划里的走法：gyb 是超级用户，裸终端什么都能干，钩子对裸会话不生效（`08` 第一节说裸会话身上没有钩子，靠 CLAUDE.md 那三句加 reviewer 事后查）。gyb 手搓 `run.py launch` 跑，宿主 `ops/jobs.json`、`ops/runs.jsonl` 照登记，`loop/runs.jsonl` 里没有这条。之后 doctor 第 18 项扫「`loop/runs.jsonl` 与宿主 `ops/runs.jsonl` 对不上的 run_id」，只报不修，归 run 推（`05`「rl doctor」）。gyb 想让这次的数进 runs 账，runs 的 actor 允许 gyb，`rl run add` 要 `--handoff ID`，没有发射单就挂不上，doctor 第 6 项报 `handoff_id` 为空，修法是 `rl doctor --ack 6 RUN_ID`。

会岔出去的地方：gyb 跑完觉得有意思、想让 analysis 把这次的数和正账里的对比，那这条 run 得先进 runs 账、`config` 得有分组键；gyb 在 `experiments/` 外随手改了代码，reviewer 审的是 runs 账里的 commit，随手改的不在任何工单的 `code_paths` 里；gyb 手搓的 run 占了卡，run 角色探卡的时候看得见（`free_cmd` 实探）但账上没有。

预演要回答的问题：gyb 随手跑的东西怎么不污染正账、又能在需要的时候补进去；doctor 第 6、18 项对这类 run 各报一次，`--ack` 之后是不是就干净了；随手跑的代码要不要有一条路补成工单。

## 我读 parts 的时候已经看到、这批场景一定会撞上的没裁的点

下面这些点各 part 末尾「源文档没写清的」里都有，我按场景归一下，方便 gyb 决定预演之前先裁哪几条：

1. 快车道的数字进不进 runs 账（`07` 第 2 条、`23` 第 7 条）：场景 6、7、11 都撞。不进的话「改参数再比」「加样本再合」「汇总」三件事都必须正式重跑。
2. gyb 在裸终端给别的角色的决定追加一版落哪个文件（`02`「六个决定文件」三处口径不一致，`02` 未开）：场景 3、6 撞。
3. 定性看样例、批量看 case 归谁（parts 里没有条目）：场景 9、10 撞。连带无角色 subagent 敲 rl 写命令时 actor 被判成 gyb 这个口子。
4. 续跑或者增量（parts 里没有条目）：场景 7 撞。
5. reviewer 派不派 subagent（sync-inbox 问题 6）、没有 run 的时候审哪一版：场景 8、10 撞。
6. 环境、权重这类仓库外杂活归谁、留不留痕（parts 里没有条目）：场景 14 撞。
7. 后台起 subagent 的机制、subagent 里钩子装不装得上、能不能跑几小时（待验证第 8、9 条）：场景 4、5、6、11 全部建立在「能」的假设上，预演的 subagent 要把这个假设标在第一步。
8. 收回之后代码和产物的处置（`20` 第 7 条、`11` 第 7 条）：场景 3、13 撞。
9. 一张 accepted 的工单下面能不能再挂新发射单（parts 没写）：场景 6、7 撞。
10. 表格算不算口径、归 metric 还是 figure（parts 没写）：场景 11 撞。
