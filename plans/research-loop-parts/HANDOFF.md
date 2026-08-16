# research-loop 设计定稿：交接文档（2026-08-16 夜写，给「统筹 session」和「part session」用）

这份文档写给两种会话读：一种是 gyb 开的「统筹 session」，只开一个，常驻，读了这份就接管全局：管哪份 part 在谁手上、把各份定稿的改动传播到别的 part 和两份源文档、收 part session 报上来的同步事项、攒问题等 gyb 裁；另一种是 gyb 开的「part session」，可以同时开很多个，一个只定稿一份 part，遇到牵连别处的事不自己动手，回报给统筹 session。写这份文档的会话到此结束，gyb 不再回来，之后的一切以这份和目录里的文件为准。

## 一、现在的状态

research-loop 是 new1 工程里的一个 Claude Code 插件，设计已经收口但代码一行没写（旧代码按裁决整体退役，见 `00-overview.md` 第三节裁决 1）。设计写在两份源文档里，然后被拆成这个目录下的 22 份 part，其中 21 份写成了：

- 设计文档 `plans/2026-08-16-research-loop-next-steps.md`：做成什么样、为什么，十一条设计原则在它第二节。
- 施工计划 `plans/2026-08-16-research-loop-build-plan.md`：字段、转移表、命令表、阈值、待验证、测试、施工步骤。可枚举的东西只在它里面写一遍。
- 两轮模拟的原始摩擦：`plans/2026-08-16-research-loop-simulation-round1.md`（59 条，核实过）、`plans/2026-08-16-research-loop-simulation-round2.md`（234 条，没核实过）。
- 这个目录 `plans/research-loop-parts/`：`README.md` 是索引和每份留给 gyb 的点，`00` 到 `25` 是 21 份 part，`30-build-steps-verify-tests.md` 没写成。

全部已 commit：`601f835`。工作树干净。

拆分的写法铁律是只搬运不发明：源文档怎么写就怎么写；两处不一致的在 part 里标「两处原文不一致」不裁；题目里缺的写进每份末尾「源文档没写清的」；每份最后一节把第二轮摩擦原样抄了一遍。所以现在 21 份 part 加起来的内容等于两份源文档，外加每份 agent 自己发现的没写清的点。

## 二、每份 part 的固定结构（part session 改的时候要保持）

```
# 标题
> 覆盖什么、不覆盖什么；源：设计文档哪几节、施工计划哪几节
## 正文（若干小节）
## 和别的 part 的接口
## 源文档没写清的（留给 gyb）
## 第二轮模拟里归到这一份的摩擦（原样，未核实）
```

part session 定稿之后会多两节：

```
## 裁决记录（日期）
## 要同步到别处的
```

「裁决记录」一行一条带日期，是 gyb 说的原话或原意；「要同步到别处的」一行一条，写清目标文件名和要改成什么。摩擦那一节永远原样保留。

## 三、统筹 session 和 part session 怎么通话

统筹 session 开起来之后第一件事 `/rename rl-hub`，part session 开起来第一件事 `/rename rl-part-<编号>`（比如 `rl-part-03`），名字定了两边才找得到对方。同一台机器上的 Claude Code 会话互相能看见：用 `ListAgents` 列出来，用 `SendMessage` 按名字发消息（收件人名字照 `ListAgents` 那一行原样抄）。part session 有事回报就 `SendMessage` 给 `rl-hub`；统筹 session 有话交代就 `SendMessage` 给 `rl-part-<编号>`。

消息发不出去（对方还没开、`ListAgents` 里没有）就走文件邮箱：往 `plans/research-loop-parts/sync-inbox.md` 末尾追加一段，格式固定：

```
## <日期 时间> 来自 <会话名> 关于 <part 文件名>
- 事项：<一句话>
- 裁决原文：<gyb 说的>
- 要改的地方：<目标文件名>：<哪一句改成什么>
- 状态：待处理
```

统筹 session 每次开工先读 `sync-inbox.md`，处理完把那段的状态改成「已处理 <日期>」。消息和邮箱两条路的内容一样，邮箱是兜底，不是可选的第二份：发了消息也要往邮箱补一段，这样会话崩了记录还在。

part session 要回报的三种事：（1）一条裁决动到了别的 part 或两份源文档里的东西（字段、状态、命令、接口一节列的），把裁决原文和要改的目标句子报上去，自己不去改；（2）自己这份里的一句和别的 part 打架，两边原文报上去等裁，不自己定；（3）这份过完了，报一句「`<文件名>` 定稿，commit `<hash>`」。回报之后不等回音接着往下过；统筹 session 有回话（比如「这条别处已经裁成另一个值」）再照回话改。

统筹 session 要交代给 part session 的两种事：（1）它手上那份 part 里的某一句，因为别的 part 先裁了，现在要改成什么，附来源 part 的裁决原文；（2）它报上来的打架 gyb 裁了，结果是什么。

## 三点五、part session 怎么开（gyb 贴给每个 part session 的话）

> 先 `/rename rl-part-<编号>`。读 `plans/research-loop-parts/HANDOFF.md` 第二、三、四点五节，再全文读 `plans/research-loop-parts/<文件名>`。这份是 research-loop 插件设计的一个部分，我要把它逐条定稿。规矩：只在这一个文件里改，别的 part 和两份源文档不动；文件末尾「第二轮模拟里归到这一份的摩擦」那一节原样保留不改；十一条设计原则在 `00-overview.md` 第二节，改任何一条规矩都要能对回其中一条。先从「源文档没写清的」那一节开始，一条一条问我要裁决，一次只问一个问题，问完等我答，答了就把正文对应的那一处改掉、把那条从「没写清」里删掉；正文里标了「两处原文不一致」的地方同样一处一处问我。我说的每一条裁决都追加到文件末尾新开的「裁决记录（日期）」一节里，一行一条带日期。改动牵连别的 part 的（字段名、命令、状态、接口一节里列的东西），不去改那边：在文末新开的「要同步到别处的」一节里列一条，同时按 HANDOFF 第三节 `SendMessage` 报给 `rl-hub` 并往 `sync-inbox.md` 追加一段。收到 `rl-hub` 的消息照它说的改。全部过完之后把「和别的 part 的接口」一节按定稿重写一遍，commit（前缀 `research-loop parts:`），再报 `rl-hub` 一句定稿。

建议顺序：先 `03-ledgers.md`、`04-handoffs-and-sessions.md`、`05-rl-cli.md`（底座，角色和角色对那十一份的字段、状态、命令全指向它们），再 `02-decisions.md`、`06-hooks-and-permissions.md`，再角色五份 `10` 到 `14`，最后角色对六份 `20` 到 `25` 和 `07`、`08`、`09`。同时开的几份尽量别互为定义处和引用处（第四点五节的表），底座三份最好先过完再开别的。`30` 那份等底座定稿之后再写，源在施工计划第九、十、十一节。

## 四、统筹 session 干什么

统筹 session 常驻，干四件事：

1. 记谁在干什么。维护 `README.md` 进度表里每份的状态（未开、在 `rl-part-NN` 手上、已定稿 commit 几号），part session 报定稿就更新。
2. 收回报、传播。收到 part session 的消息或 `sync-inbox.md` 里的待处理段，先按第四点五节的表判定义处：定义处在别的 part，就把裁决搬回定义处那一份（改它的正文并补进它的「裁决记录」，注明来自哪份），再从定义处往所有引用处传，包括两份源文档（源文档改正文那一句，并在设计文档最后一节或施工计划第十四节补一行「哪天、按哪份 part 的裁决、改了哪句」）。目标 part 正在某个 `rl-part-NN` 手上的，不直接改它的文件，`SendMessage` 交代给那个 session 去改（避免两个会话同时写一个文件），它不在了才自己改。传播完把来源 part 里那条标「已同步 <日期>」，把邮箱那段标「已处理」，commit 前缀 `research-loop sync:`。
3. 攒问题等 gyb。传播时发现目标 part 已经有相反的裁决，或者 part session 报上来的打架，不自己裁：把两边裁决原文并排记进 `sync-inbox.md` 一段（状态「等 gyb」），gyb 来了一次问一个，裁了再改并回话给相关的 part session、补进两份 part 的「裁决记录」。
4. 补漏。第一次开工先按第四点五节末尾那步核关联表；空下来的时候做覆盖检查（第五节）。

统筹 session 开工时先做四件事：`/rename rl-hub`；读这份文档全文；`git log --oneline -20` 加 `git status`；读 `sync-inbox.md` 有没有待处理的。铁律和 part session 一样：只搬运不发明；改任何规矩都要能对回十一条原则；两处不一致不自己裁；摩擦那一节永远不动；每份的固定结构不动；gyb 不在场时不猜他的意思，把问题攒着等他。

## 四点五、总体关联：谁是什么的唯一定义处，谁引用谁

传播的时候先按这张表判「这条改动该落在哪一份」：一样东西只有一份 part 是定义处，其余都是引用；改动从定义处出发往引用处传，引用处的 part session 裁了定义处的东西，同步 session 先把裁决搬回定义处，再从定义处往所有引用处传。

| 东西 | 定义处 | 引用处 |
|---|---|---|
| 十一条原则、九条裁决、（a）到（i） | `00-overview.md` | 全部 |
| gyb 的身份规矩、gyb use case 表、`rl status` 十段、推送表 | `01-gyb.md` | `05`（status 命令行）、`04`（销号与 reclaim）、`14`、`25` |
| 决定账：行格式、来源、版本、root_id、stale、reissue、`rl decision` | `02-decisions.md` | `03`（只指过去）、`10`、`11`、`13`、`14`、`20`、`21`、`22`、`25` |
| 九本账公共骨架、七本账行格式（issues、runs、grants、feedback、evaluations、sessions、scratch）、退出码 | `03-ledgers.md` | 全部角色和角色对；`09` 抄了 issues/grants/feedback 三本的规则、`07` 抄了 scratch、`04` 抄了 sessions——这四处是同一件事写了两遍，改一处必改另一处 |
| handoffs 行格式、七个状态、holder 不变量、转移表、dispatch、交付物、销号、reclaim、三种通知 | `04-handoffs-and-sessions.md` | `10`、`11`、`12`、`13`、`20`、`21`、`22`、`24`、`05`（命令行那一栏） |
| `bin/rl` 每条子命令的签名和「谁能调」、inbox、trace、doctor 十八项、notify、锁 | `05-rl-cli.md` | 全部；`04` 里 reclaim/session、`02` 里 decision、`07` 里 ql/scratch、`09` 里 feedback/issue/grant 各抄了自己那几条的签名 |
| 三层约束、钩子拦放、CLAUDE.md 三句、五份角色 json 四栏、test_skill_refs、读的纪律 | `06-hooks-and-permissions.md` | 五份角色 part 各抄了自己那份 json；`08` 抄了 CLAUDE.md 三句 |
| 快车道进出、scratch 三态、ql 命令、补单规矩 | `07-quick-lane.md` | `11`、`13`、`20`、`21`、`23` |
| init 建什么、research-loop.json 的键、阈值表、插件树、入口 skill、宿主对接 | `08-trees-init-and-host.md` | `12`（宿主命令模板、阈值）、`06`（CLAUDE.md）、`01`（提醒阈值） |
| common/ 四文件、公共规矩八条、rules_version、feedback 流程、issues 九种 kind 与 reply/close、grants | `09-common-and-feedback.md` | 全部角色 part 抄了规矩；issues 的 kind 在 `03`、`04`、`12`、`24` 各出现 |
| 角色的职责、use case 表、模型 | `10` 到 `14` 各自 | 对应的角色对 part 和 `06`（json 四栏是从 use case 表倒推的，use case 改了 json 必改） |
| 一条通道上的字段、状态走法、issue 往返 | `20` 到 `25` 各自 | 通道两头的角色 part |

三条判断规矩：
1. 角色对 part（`20` 到 `25`）里定的东西，只要是字段、状态、命令，定义处永远在 `03`、`04`、`05` 之一，角色对 part 只是「这条通道用了哪些」；同理角色 part 里的 json 四栏定义处在 `06`。
2. 上表里标了「写了两遍」的四处（`03` 对 `09`/`07`/`04`、`05` 对 `04`/`02`/`07`/`09`、`06` 对五份角色、`06` 对 `08`），每次同步结束都要各对一遍，两边一字不差。
3. 一条改动找不到定义处（比如新加一个字段、新加一条子命令），先问 gyb 归哪一份，不自己定。

这张表是拆分时按给每份定的范围列的，不是从 21 份文件里机器扫出来的。同步 session 第一次开工先把 21 份的「和别的 part 的接口」一节全读一遍，对着这张表核：表里漏的引用关系补进表里，表里写错的改掉，改完 commit。以后每次同步遇到表外的引用也照此补。

## 五、还悬着的、统筹 session 要记着的

- 施工计划第一节末尾（a）到（i）九条是我改的设计、gyb 还没裁；哪一份 part 的裁决碰到它们，就等于 gyb 裁了那一条，同步的时候把结果回写到施工计划第一节那一条后面标日期。
- 五处两份源文档互相不一致，各 part 已标出、等 part session 裁：决定行落哪个文件三处口径（`02`）；发射单引不引决定（`21`、`02`）；快车道数字进不进 runs（`07`、`23`）；actual_seconds 谁算（`21`、`05`）；reviewer 只由 gyb 手动开还是也能当 subagent（`14`）。哪份先裁到，统筹 session 负责把另一份改成一样。
- 覆盖检查没跑成：两份源文档每一段是不是都落进了某个 part 没有机器核过。统筹 session 手头空的时候可以做：把两份源文档从头过一遍，每段在某个 part 里找到落点，找不到的补进最合适的 part 并在 README 里记一笔。
- `30-build-steps-verify-tests.md` 没写。
- 第三轮模拟跑不跑、跑几个场景，gyb 定；跑的话 workflow 脚本在会话目录里（`rl-scenario-simulation-r2-wf_0b204aaa-355.js`），场景清单和 schema 可以直接复用，模型一律显式写 opus。
- 用量：subagent 一次派 22 个会撞月度上限，上一轮 22 个里 13 个报错（文件都写完了只是最后一步没返回）；再派一律六个以内。

## 六、跟这件事有关的工程规矩（从 new1 的 CLAUDE.md 和记忆里抄的，统筹 session 也要守）

- 动手前取得同意，一个请求只做一件事；一轮只问一个问题。
- 派 subagent 一律显式写模型，默认 sonnet 或 opus，不用 fable；插件里 idea 和 reviewer 用 fable 是 gyb 2026-08-16 点名的例外，只对插件运行时生效，不对派去写文档的 subagent 生效。
- 写作按 humanizer-gyb：白话、断言、一物一名（术语用施工计划第二节词表的英文名）、事实和解读分开、不用 emoji、不堆粗体。
- 不读 `research-loop/` 目录下的旧代码（已退役会误导），不碰 `/home/y-guo/ACL2026`。
- 提交前 `git status` 看清楚，只 add 这次改的文件；commit message 前缀按上面两种。
