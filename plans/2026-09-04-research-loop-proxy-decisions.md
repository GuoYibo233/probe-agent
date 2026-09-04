# 2026-09-04 起 research-loop 施工期间代 gyb 做的决定记录，gyb 回来逐条审查

这份记录的来历：2026-09-04 gyb 看完施工指南（`plans/2026-09-04-research-loop-work-guide.md`）之后说：「全都按照推荐的吧，然后这次我不知道的情况下做出的决定这一块专门开一个记录，遇到要我解决的东西就按照你自己的推荐做掉，我回来在审查。」从这句话起，施工中碰到本来要 gyb 裁定的事，施工会话按自己的推荐做掉，每一件在这里记一条，gyb 回来逐条填「审查」栏。

记录的规矩：一件事一条，编号 D-NN 只增不改；每条写清问题、决定、理由、落在哪个文件或 commit；gyb 审查之后在「审查」栏写「认可」或者写改成什么，改了的由施工会话按新裁决返工并在同一条下面记返工的 commit。这份记录只装代裁的决定，gyb 亲口裁的记在第一节当依据。

## 第一节：gyb 2026-09-04 亲口裁定的，当依据

1. 今天交「骨架版」：所有组件文件都在、已裁定的部分代码写完并且能写成用例的测试全绿、没裁定的地方在代码里标「待裁」指回问题编号、母版和说明书是草稿。代码按 sync-inbox 里的新裁决写，另列对照单记每笔欠账落在代码哪里，最后一期合并现行版的时候逐笔核对。今天不走工单化：表和 schema 主会话自己抄录，实现部分派子会话写、另派子会话评审。（指南第九节第一题，gyb 答「按推荐」）
2. 今天点名测试待验证第 5 条（子会话结束时销号钩子触不触发、会话编号是不是同一个、子会话写账算谁）和第 9 条（后台子会话能不能运行几小时、母会话关了会不会被杀），测完再写身份判定，测试期间别的底座照写。（第二题，gyb 答「按推荐」）
3. 分层真源：机器能查的（角色表、转移表、行格式、钩子拦什么）归代码和表；纪律类（读什么、读的顺序、什么时候开 issue、派活怎么交代）归母版和说明书；设计分册在总验收过了之后退成来历，改动走插件自己的反馈账和版本号。（第三题，gyb 答「按推荐」）
4. 这个对话里允许用 fable 当子会话；评审类的子会话交给 fable。（gyb 2026-09-04 原话「在这个对话里允许你使用fable当subagent」「judge的任务交给fable来进行吧」）
5. 碰到要 gyb 裁的事按施工会话自己的推荐做掉，记在这份记录里，gyb 回来审查。

## 第二节：代裁的决定，一件一条

### D-01 授权账（grants）今天留位不建立

- 问题：那本账原来只装「让想法角色读文献目录」一种许可，申请机制 2026-08-21 整套砍掉，账里没有内容，可是账本清单、写账命令、测试 9 的用例都还按这本账存在写着（sync-inbox 问题 43(c) 要问 gyb 存废）。今天写账本清单要定九本还是八本。
- 决定：`tables/ledgers.json` 里保留 grants 这一行并标 `PENDING(问题 43c)`；不写 grants 的 schema、不写 `rl grant` 子命令、测试 9 里 grant 相关的用例标跳过。
- 理由：留位不建立是改动最小的选择，两个方向（留、砍）到最后一期都还能走；今天建了 schema 和命令，砍的时候要删三处。
- 落点：施工步 3a 的 `tables/ledgers.json`。
- 审查：

### D-02 派活开场话把单子内容全抄一遍，推广到所有派活通道

- 问题：deploy 派 run 的开场话把单子内容全抄一遍（11 第 89 行，2026-08-21 裁）；idea 派 deploy、idea 派 analysis 两条通道要不要照此，sync-inbox 问题 46 等 gyb。挡 idea 说明书的派活段。
- 决定：推广到所有派活通道。idea 的 SKILL.md 和 agents/ 定义按「开场话全抄单子内容」写。
- 理由：这条裁决的目的是下游不用回头翻账、不用再问就能开工（04 对 explanation 的要求），三条通道的下游处境相同；工单解释长就长，开场话长的代价比下游翻账错行的代价小。
- 落点：施工步 6 的 `skills/idea/SKILL.md`、`skills/deploy/SKILL.md`。
- 审查：

### D-03 审查角色（reviewer）「被派出来时用 fable」那一档保留，不另加派法

- 问题：角色 json 给 reviewer 的 as_subagent 是 fable，可是五份角色 json 的 dispatches_to 没有一份指向 reviewer，gyb 的 use case 表里也没有「启动一个 reviewer」（14 第 141 行第 1 条没裁）。今天写 `tables/roles/reviewer.json` 和 `agents/reviewer.md` 要定这一档留不留。
- 决定：`tables/roles/reviewer.json` 照 06 抄，fable 档保留；`agents/reviewer.md` 照写；不给任何角色加「派 reviewer」的权。
- 理由：只搬运不发明：改模型表是改裁决 3（00 第 41 行），不是施工会话能定的；留着不碍事，将来要加派法走 feedback 账。
- 落点：施工步 3a、步 6。
- 审查：

### D-04 读不设运行时门禁，维持已裁

- 问题：gyb 原话里的「能找什么」如果读成运行时拦读，和三条已裁（00 第 22 行、06 第 35 行、00 第 45 行裁决 7）冲突。
- 决定：维持已裁，reads 栏只进角色 json 和测试 13 的文本对照，代码里不写任何读的拒收逻辑。
- 理由：指南第三节写了：读的口子太多，机器拦不全会变成半拦，让人以为拦住了。
- 落点：`scripts/rl_lib.py` 没有读权检查；`tests/test_skill_refs.py`。
- 审查：

### D-05 30 分册的三处过时句由施工会话直接修改并补裁决记录行

- 问题：30 没走定稿流程（HANDOFF 第 13 行），第 199 行「头部带钩子声明」与 08 第 89 行打架，第 136、227 行 amend 分不分新 run_id「还没裁」与 21 第 179 行「已裁」打架，第 196 行步 3 交付物没写每栏抄自哪份。
- 决定：施工会话直接改这三处，30 的裁决记录加一行记今天的改动和来源。
- 理由：三处都是把已有裁决传播进 30，不是新裁决；30 不在冻结三份里。
- 落点：`plans/research-loop-parts/30-build-steps-verify-tests.md`。
- 审查：

### D-06 gyb 直接 fork 了四个助手，统筹把这个动作当成「开始」

- 问题：2026-09-05 统筹会话给出多会话分工建议，末尾写的开工顺序是 gyb 先改名、再说「开始」、统筹做步 1、gyb 再 fork。gyb 没改名也没说「开始」，直接 `/fork` 了底座、文本、验证、评审四个助手，四个助手都在等步 1 的 commit。
- 决定：把四次 fork 当成对分工建议的同意，统筹立刻做步 1 并提交、写协议文件、通知四个助手开工。统筹会话的名字照旧是 `research-loop directory structure [37c253]`，改名只有 gyb 能做。
- 理由：四个助手是按建议里的名字和分工开的，等一句「开始」会让四个会话空转；步 1 是设计早裁定的动作（00 分册裁决 1），不是新裁决。
- 落点：步 1 的 commit；`plans/2026-09-05-research-loop-fork-protocol.md`。
- 审查：

### D-07 空目录用 .gitkeep 占位，MAP.md 的旧插件行改成 v2

- 问题：30 分册步 1 的验收是「目录里只有 plugin.json 和空目录」，git 不记录空目录；MAP.md 3.5 节那一行还写着旧插件 0.1.0 的入口和脚本，步 1 删掉旧目录之后这一行指向不存在的文件。
- 决定：十个空目录各放一个 `.gitkeep`；MAP.md 3.5 节的那一行改成 v2 的入口、自测命令和设计真源，随步 1 同一个 commit。
- 理由：`.gitkeep` 是 git 的惯用占位，不算发明；MAP.md 是工程规矩要求「加新程序要更新对应行」的代码地图，指向已删文件就是错的。
- 落点：步 1 的 commit。
- 审查：

### D-08 测试 13 对两句纪律设豁免清单（文本助手提，统筹按推荐裁）

- 问题：每份角色 SKILL.md 都要带两句纪律，一句「钩子拦不到的写法一律不许往四个角色目录和 loop/ 写，要写就用 Write/Edit 或者钩子看得见的 Bash 写法，账本一律走 rl」（06 第 29 行「这句进公共规矩第 8 条和每份角色 SKILL.md」），一句「一个会话只加载一个角色，要换角色另开会话」（09 第 53 行「这句同时写进每份角色 SKILL.md」）。测试 13 第 3 样要求说明书里没有母版条文的副本（09 第 27 行），第 2 样要求正文出现的每个目录都在角色 json 的 reads 里（06 第 259 行）。第一句是 rule-08 的一半，抄进说明书就是母版条文的副本；第一句点名的四个角色目录和 loop/ 对 run、deploy 不在 reads 里。两条检查和两句纪律硬碰。
- 决定：测试 13 里放一张两句纪律的豁免清单，写明来源 06 第 29 行、09 第 53 行；检查第 2 样和第 3 样之前先把这两句从说明书正文里剔掉，其余正文照查。
- 理由：设计的两处已裁（两句必带）和两条检查同时保住，例外在代码里明写一处、带来源；不抄这两句直接违反两处已裁；把第 2 样缩成只查「使用场景」栏会漏检限制条件栏里别的目录。代价是母版改这两句话时要同步改测试的豁免清单。
- 落点：施工步 6 的 `research-loop/tests/test_skill_refs.py`（文本助手写）。
- 审查：

### D-09 插件本体一律英文，来源标注写成 `06 L178`，待裁标记写成 `PENDING(issue 43c)`（评审助手提，统筹裁）

- 问题：统筹写的 `research-loop/README.md` 全文中文，评审对照 00 第 321 行 gyb 2026-08-18 原话「所有的东西都默认用英语，插件本体里面用英语写，然后不要出现语言相关的约束」指出应改英文。连带三样没定：插件本体里代码注释、来源标注（分册号加行号）、待裁标记的写法。施工指南第七节原来定的标记是 `PENDING(问题 NN)` 和 `PENDING(22 第 113 行)`，带中文。
- 决定：插件本体（`research-loop/` 下一切：README、代码、注释、测试、母版、说明书、agent 定义）一律英文；来源标注写 `06 L178`（分册号加 L 加行号）；待裁标记改成 `PENDING(issue 43c)`（指 sync-inbox 的问题号）和 `PENDING(part 22 L113)`（指分册条目），施工指南第七节同步改。插件本体里不写任何关于语言的规矩。README 改英文并把「旧文件留在 b63519b 之前的历史里」改成「3ae0bc9 之前」（删除发生在 3ae0bc9）。
- 理由：00 第 321 行是已裁，README 在 08 第四节的插件本体目录表里；待裁标记的用处是最后一期按 `PENDING(` 这个字面扫描，英文形式一样扫得到，并且不让插件本体里夹中文。评审推荐标记保留中文形式，统筹改成英文形式，差别只在标记内部的写法，扫描字面不变。
- 落点：`research-loop/README.md`；`plans/2026-09-05-research-loop-fork-protocol.md`；`plans/2026-09-04-research-loop-work-guide.md` 第七节；四个助手各收一条消息。
- 审查：
- 补记 2026-09-05（评审助手提议加第三种形式 `PENDING(proxy D-NN)`，统筹不加）：等统筹代裁的那几分钟里，标记用指回分册条目或者问题号的原有两种形式（拿不准的事总能指回一处分册或者 sync-inbox 段），裁了之后换成来源标注 `proxy decision D-NN`、不再 PENDING。理由是编号在裁的时候才发，助手裁前猜号会撞（efa5b5f 的 `PENDING(D-14)` 指的是后来记成 D-18 的事）；两种形式保证最后一期扫到的每个 `PENDING(` 都指向一处设计文字。

### D-10 工单（work_order）开单时 `track` 必填（底座助手提，统筹裁）

- 问题：sync-inbox 问题 45(a)(f) 只写「`work_order` 加顶层 `track`（idea 开单填）」，没写必填还是可选。底座写 handoffs 的 schema 要定。
- 决定：`work_order` 开单时 `track` 必填。
- 理由：04 第 43 行写发射单开单时第一次尝试的 `track` 必填，11 第 76 行写发射单的 `track`「从父单抄」，所以没有 `track` 的工单下面永远开不出发射单；在工单开单这一步就要，缺口在源头拦住。每张工单都属于一条研究方向，方向名对工单没有例外。
- 落点：`research-loop/schemas/handoffs.schema.json`、`research-loop/tables/transitions.json` 新建行的前提；sync-inbox 问题 48(b) 记最后一期要落进 04 字段表。
- 审查：

### D-11 feedback 账的编号形状定为 `fb-NNNN`（底座助手提，统筹裁）

- 问题：03 第 145 行只写「反馈编号」，没有形状；别的账都有（`iss-0031`、`grant-0003`、`eval-0004`、`ho-0013`）。schema 和编号分配要一个形状。
- 决定：`fb-NNNN`，序号从 1 起、四位起步、按数值排序，和 03 第 21 行的编号总规矩一致。代码里的来源标注写 `proxy D-11`，不标 PENDING。
- 理由：照别的账的形状类推是唯一不发明的做法；03 的空白由最后一期补进正文。
- 落点：`research-loop/schemas/feedback.schema.json`、`research-loop/scripts/rl_lib.py` 编号分配；sync-inbox 问题 48(a)。
- 审查：

### D-12 `tables/` 允许多三份表：命令表、退出码表、配置默认值表

- 问题：08 第四节和 30 步 3 给 `tables/` 列的是四样（账本清单、转移表、角色 json、gyb use case 表）。底座在 5c56edf 里另加了 `tables/commands.json`（05 的命令表）、`tables/exit_codes.json`（03 的退出码六个）、`tables/config_defaults.json`（08 第三节阈值默认值表），每行带来源。
- 决定：允许。三份都是设计里已有的表搬成机器读的形式，代码从表读、不在代码里复写一份：`bin/rl` 的子命令分发读命令表（测试 13 查「子命令在定义处存在」也对这份表查），`rl_lib` 的退出码读退出码表，`rl init` 的默认配置读配置默认值表。
- 理由：gyb 2026-09-04 裁的分层真源是「机器能查的归代码和表」；三份表的内容是搬运，容器是新的。评审对 5c56edf 查「只搬运不发明」，查出发明的内容由底座改。
- 落点：`research-loop/tables/`。
- 审查：

### D-13 入口 skill 关掉模型自动调用，五份角色 skill 不关、靠 description 只写一个触发条件（文本助手提，统筹按推荐裁）

- 问题：五份角色 skill 要同时满足两件事：gyb 手敲 `/research-loop:idea` 加载，和 `agents/idea.md` 用 `skills:` 预载。文本助手让查文档的子会话核实过官方文档：带 `disable-model-invocation: true` 的 skill 不能被 agent 的 `skills:` 预载（预载和模型可调用是同一个集合），没有字段能做到「只预载、不让主会话的模型自动触发」。08 第 108 行待验证第 4 条的候选机制（skill 头部声明禁止模型调用）对角色 skill 走不通；入口 skill 只要 gyb 手敲、不被预载。
- 决定：入口 skill 加 `disable-model-invocation: true`；五份角色 skill 不加，description 只写「Use when gyb has assigned this session the <role> role」这一个触发条件，正文第一段写清 gyb 没点名就停。
- 理由：官方文档的限制绕不过；「一会话一角色」本来就是纪律不是门禁（06 第 106 行），description 收窄是把误触发压到最低的办法；入口 skill 关得掉就关。待验证第 4 条的正案已经是 `rl init` 查调用者状态文件（2026-08-17 裁），这条决定不动它。
- 落点：`research-loop/skills/research-loop/SKILL.md` 头部；`research-loop/skills/<role>/SKILL.md` 头部与正文第一段。验证助手补测两条文档事实：agent 的 `skills:` 引同插件 skill 用裸名还是 `research-loop:idea`；带 `disable-model-invocation` 的 skill 确实预载不了。
- 审查：
- 补记 2026-09-05：验证助手沙盒实测，`skills:` 写裸名和带插件前缀都预载得上；带 `disable-model-invocation: true` 的 skill 两种写法都预载不上（debug 日志报 Warning: Skill 'gate' specified in frontmatter was not found）。D-13 的依据成立。

### D-14 问题 45(b) 里 run 回 withdrawn issue 那一支标待裁，不改 run 的角色 json

- 问题：对照单核手指出三处对不上：sync-inbox 问题 45(b) 要求收回时 holder（含接发射单的 run）把代码位置和半截产物路径回进那条 `withdrawn` issue；03 第 92 行写通知类 issue 的 assignee 能回能关；06 第 204 行给 run 的 issues 写权只有 open，钩子和入账校验会拦 run 的 reply。deploy 和 analysis 的写权没有这个缺口。
- 决定：run 的角色 json 照 06 逐字抄不改；45(b) 的 run 那一支在 `research-loop/skills/run/SKILL.md` 和 rl 的 withdraw 提示里标 `PENDING(issue 50)`；deploy、analysis 两支照 settled 落。sync-inbox 立问题 50 等 gyb 裁 run 的 issues 写权要不要加 reply、close。
- 理由：改角色 json 的一栏是改 06 的定稿裁决（角色 json 内容 2026-08-18 gyb 裁），不在代裁范围；缺口只影响 run 一支，标待裁不挡别的。
- 落点：`plans/2026-09-05-research-loop-debt-map.md` 第四节；sync-inbox 问题 50。
- 审查：

### D-15 子会话写账的身份判定与登记（待验证第 5 条测完；验证助手、底座助手各提推荐，统筹按推荐裁）

- 问题：06 第 118 行留的缺口：子会话的 `session_id` 与母会话相同、不写状态文件，rl 按状态文件读到的是母会话的角色，账上会记成母会话的角色接了单。验证助手 2026-09-05 沙盒实测：SubagentStart、SubagentStop 都触发并带 `agent_id`、`agent_type`，`session_id` 与母会话相同；子会话结束时 SessionEnd 不触发；子会话的 Bash 环境与母会话逐字相同，环境文件那条路不通；PreToolUse(Bash) 钩子能用 updatedInput 往命令前注入环境变量，两个并发子会话各拿到自己的类型和编号；母会话结束时被杀掉的子会话没有 SubagentStop、只有母会话的 SessionEnd。
- 决定：（1）rl 判 actor 的顺序：先看写权钩子注入的 `RL_AGENT_TYPE` 和 `RL_AGENT_ID`（钩子在 `agent_type` 非空时用 updatedInput 注入），类型名按钩子同一张映射表对应角色（06 第 96 行：认识的按角色，不认识的按最严），不认识的类型 rl 拒写、退出码 3 并提示；没有注入变量才按状态文件；都没有是裸终端 gyb（01 第 69 行的判据）。（2）九本账公共骨架加可选栏 `agent_id`，子会话写的行填、顶层会话写的行不填；`session_id` 照记母会话的。（3）子会话在 sessions 账另落一行开始版：`session_id` 记母会话的，`agent_id` 存钩子输入的编号，`role` 按 `agent_type`，`launched_by` 记 subagent；同一个 `session_id` 下 `agent_id` 不同的行是不同的版本链，rl 查「这个会话最新版是不是 closed」按（`session_id`，`agent_id` 或空）配对查，母会话的链不被子会话的 closed 版盖住。（4）销号：SubagentStop 钩子按 `agent_id` 关子会话那一行，并把该子会话开干的单交回（release 行 actor 记子会话的角色，`via` 记 subagent_stop）；母会话 SessionEnd 钩子把本 `session_id` 名下所有开干的单一起交回（含被杀的子会话的，因为它们没有 SubagentStop），再关还开着的子会话行，最后落母会话的 closed 版（03 第 15 行的写序）。（5）待验证第 9 条母会话结束那一半：三种结束方式子会话都被杀，30 的失败备案照旧成立，落法按 verify.md 记录。
- 理由：钩子那一层已经裁定按 `agent_type` 判角色（06 第 96 行），把同一个判定经注入变量交给 rl，两层看到同一个身份，又不违反「子会话不写状态文件」（06 第 118 行）；可选栏不动既有必填；另落一行让「谁真写的、谁起了谁」在账上查得出（06 第 157 行的事后追查靠这个）；版本链按（`session_id`，`agent_id`）配对是为了不让子会话的 closed 版把母会话锁死（03 的「closed 会话再写拒收」那条）。底座的备选（不加栏、只靠 `launched_by`）分不开同一母会话下的两个子会话。
- 落点：`research-loop/hooks/`（写权钩子注入、SubagentStop 钩子、SessionEnd 钩子）；`research-loop/scripts/rl_lib.py` actor 判定与版本链查法；`research-loop/schemas/_skeleton.schema.json`（`agent_id`）、`sessions.schema.json`；测试 9 的用例；sync-inbox 问题 49 记冻结正文的落点（03 骨架与 sessions 字段表、04 第四六七节、05 actor 判定句）；对照单 39(a2) 的标记改 `proxy D-15`。
- 审查：
- 补记 2026-09-05（评审助手指出的技术风险，写死注入写法）：钩子往 Bash 命令前注入不能写成 `RL_AGENT_TYPE=deploy RL_AGENT_ID=x <原命令>`，shell 的前置赋值只作用到紧跟的第一个命令，原命令是 `cd repo && rl handoff start ...` 或者 `python3 x.py; rl ...` 这种链式写法时 rl 拿不到变量、会判成母会话的角色。写法定为 `export RL_AGENT_TYPE='<type>'; export RL_AGENT_ID='<id>'; <原命令>`，值经 shell 转义；验证助手的沙盒用例补一条链式命令（cd 加 && 加 rl）才算测过。D-15 的事实依据是 `plans/2026-09-05-research-loop-verify.md`，验证助手要先把已测完的部分提交，最后一种情况跑完再补。
- 补记 2026-09-05（评审助手指出 holder 分不开两个子会话）：handoffs 的 `holder` 仍记 `session_id`（04 第 21 行），不加字段、不改语义；单子 start 那一版的骨架可选栏 `agent_id` 填子会话的编号；转移表「谁能写」里查 holder、SubagentStop 找该子会话开干的单、SessionEnd 找本会话名下的单，都按（`session_id`，`agent_id` 或空）配对。sync-inbox 问题 49(b) 的 04 落点加这半句。

### D-16 gyb 在裸终端或 `--as-gyb` 写杂账（scratch）照收（评审助手提，统筹按推荐裁）

- 问题：03 第 196 行 scratch 段只写 actor 是 deploy 或 analysis，runs 那本明写 gyb 例外而杂账没写；底座的 scratch schema 把 gyb 加进了 actor 枚举，评审问收不收。
- 决定：收。`scratch.schema.json` 的 actor 枚举含 gyb，加来源注（01 第 65 行、03 第 27 行）；sync-inbox 问题 48 加 (c) 给 03 第 196 行补一句。
- 理由：01 第 65 行 gyb 在任何终端都能行使自己的权，03 第 27 行 gyb 豁免「谁能调」；03 第 196 行那句描述常态、不是排他清单。底座助手同一时间提了同一题（场景是 gyb 替死掉的 deploy 会话关张），同此裁。
- 落点：`research-loop/schemas/scratch.schema.json`；sync-inbox 问题 48(c)。
- 审查：

### D-17 测试 13 的施工约定：说明书里的名字写在反引号里、按反引号提取；词表第一栏当第五类定义处（评审助手提，统筹按推荐裁）

- 问题：06 第 258 到 260 行只说测试 13 查三样，没说机器怎么从说明书正文里把 rl 命令、账名、状态、目录、词表词提取出来，也只列了四类定义处。文本助手在 `common/SPEC-TEMPLATE.md` 第 30 到 31 行和 `tests/test_skill_refs.py` 里定了：一律写在反引号里，测试按反引号提取；`common/GLOSSARY.md` 第一栏当第五类定义处。7d9bcc6 和 4974a8a 建立在这上面，没有出处。
- 决定：认。两处加来源标注 `proxy D-17`。
- 理由：机器检查要有一个可提取的边界，反引号是 markdown 现成的；词表当定义处让「名字定义在哪」有唯一落点。gyb 2026-09-04 裁的分层真源是机器能查的归代码和表，这条约定属于那一层。
- 落点：`research-loop/common/SPEC-TEMPLATE.md` 第 30 到 31 行；`research-loop/tests/test_skill_refs.py` 头注。
- 审查：

### D-18 `agents/reviewer.md` 保留 Write 和 Edit，改禁 NotebookEdit 和 Skill（文本助手提，统筹按推荐裁）

- 问题：08 第 90 行举的收窄工具面的例子是「reviewer 直接禁 Write 和 Edit」，可是 reviewer 的唯一产出是 `review/` 下的清单文件（14 第 73 到 75 行），06 给 reviewer 的 writes 也是 `review/`。照例子禁掉，reviewer 当子会话时写不出清单，只剩钩子解析不出的 Bash 写法，那正是 rule-08 禁的。
- 决定：`agents/reviewer.md` 保留 Write 和 Edit（写权的闸在钩子，钩子把它们限在 `review/`），改禁 NotebookEdit 和 Skill。注释标 `proxy D-18`，不用 PENDING。
- 理由：08 第 90 行那句是「比如」举的例子，reviewer 能写什么的定义处是 06 的角色 json；工具面只是收窄，写权的闸本来就在钩子（06 第 13 行）。禁 Skill 是防子会话里再加载别的角色 skill（一会话一角色，09 第 53 行）。
- 落点：`research-loop/agents/reviewer.md`。
- 审查：
- 附：agents/ 里 `skills:` 预载写带插件前缀的 `research-loop:<role>`，验证助手实测裸名和带前缀都预载得上（D-13 补记），注释不标 PENDING，写「verified 2026-09-05, see plans/2026-09-05-research-loop-verify.md」。

### D-19 压力场景的文件放 `research-loop/tests/scenarios/<role>/`，运行结果的汇总放 plans/（文本助手提，统筹裁）

- 问题：施工指南第五节步 6 要求每份角色 SKILL.md 配两三个压力场景（先不带 skill 运行一遍当对照，再带 skill 运行），08 第四节的插件树没有这一层，文本助手问场景文件放 `tests/scenarios/` 还是 plans/。
- 决定：场景提示词放 `research-loop/tests/scenarios/<role>/<name>.md`（英文，插件本体的一部分，08 的 `tests/` 行装得下，不加新的顶层目录）；每轮运行的对照结果（子会话在哪里违规、用什么理由开脱、带 skill 之后照不照做）汇总写 `plans/2026-09-05-research-loop-pressure-scenarios.md`（中文），原始对话记录留在会话的临时目录不进仓库。
- 理由：场景是说明书的测试，归 `tests/`；运行记录大、带模型输出，按工程规矩大产物不进 git，只留汇总。
- 落点：`research-loop/tests/scenarios/`；`plans/2026-09-05-research-loop-pressure-scenarios.md`。
- 审查：

### D-20 交互会话 `/exit` 选「挪到后台」等于旧会话销号、新会话是裸会话，只写纪律不做机制（评审助手提，统筹按推荐裁）

- 问题：验证记录（`plans/2026-09-05-research-loop-verify.md` 3.4 节）实测：交互会话 `/exit` 选「挪到后台」之后会话换了 id（ab2b2c94 变 dd30af6c），新会话没有状态文件，按 06 第 102 行的判据是裸会话，rl 会把这个角色会话之后写的账记成 gyb；旧 id 的 SessionEnd 已经把名下的单子交回。验证在第五节建议 04 记一句。
- 决定：不另做机制。sync-inbox 问题 49 加 (d) 给 04 生命周期一节：「挪到后台等于旧会话销号、新会话是裸会话，要继续干活得重新加载角色」；五份角色 SKILL.md 的限制条件栏各加一句「退出对话框里选留下，不选挪到后台；挪了就重新加载角色再接着干」，来源标注 verify.md 3.4 加 proxy D-20。
- 理由：机制上旧会话的销号已经把单子交回了，账是对的；新会话没有角色是「一会话一角色」纪律的正常情形，重新加载就好。做机制（把状态文件跟着新 id 走）要钩子认出新旧 id 的关系，官方没有这个信号。
- 落点：sync-inbox 问题 49(d)；`research-loop/skills/<role>/SKILL.md` 限制条件栏。
- 审查：
- 补记 2026-09-05（文本助手提）：verify.md 3.2 节实测退出对话框选「退出并停掉」和「挪到后台」都会杀掉正在跑的子会话，只有「留下」保得住。D-20 那句加半句「the other two choices kill any dispatched subagent (verify.md 3.2)」，五份一字相同。

### D-21 `rl` 进 PATH 的办法：SessionStart 钩子往 CLAUDE_ENV_FILE 写一行 PATH，没装钩子走插件根全路径（底座助手的步 4 设计，评审助手要求记号，统筹裁）

- 问题：05 的命令表全部写成裸名 `rl ...`，08 第四节只说命令入口是 `bin/rl`，分册没写 `rl` 怎么进 PATH。底座在步 4 设计成：插件级 SessionStart 钩子往 Claude Code 提供的 CLAUDE_ENV_FILE 写一行 `export PATH="<插件根>/bin:$PATH"`，此后这个会话的每次 Bash 都有 `rl`；钩子没装（裸终端、旧版本）时入口 skill 提示走 `<插件根>/bin/rl` 全路径。文本的入口 skill f2e2a61 已经按这个写，评审指出没有出处。
- 决定：认这个办法。三处落点：`tables/README.md` 惯例加一条写清机制和依据（Claude Code 钩子文档里 SessionStart 钩子写 CLAUDE_ENV_FILE 的那一节，底座补链接）；入口 skill 那句的标记从 `PENDING(part 08 L104)` 改成来源标注 `proxy decision D-21`；验证助手在沙盒补测一条「插件级 SessionStart 钩子写 CLAUDE_ENV_FILE 之后同一会话的 Bash 能直接敲 `rl`、子会话里也能」，测不通就回到全路径写法并改 D-21。
- 理由：五份说明书里 `rl` 命令的写法（裸名）和 `rl init` 之后的第一步都取决于这一条，属于机器能查的那一层，要有一处成文；官方机制比让每个角色自己改 PATH 稳。
- 落点：`research-loop/tables/README.md`；`research-loop/skills/research-loop/SKILL.md`；`research-loop/hooks/hooks.json` 的 SessionStart 条目；verify.md 补一条。
- 审查：
- 补记 2026-09-05：验证助手沙盒实测通（-p 和交互两种模式，母会话和后台子会话都能裸敲 `rl`；环境文件在 `~/.claude/session-env/<session_id>/`），记录随 verify.md 第二个 commit。

### D-22 `rl handoff start ID --batch B` 一次接下同 batch 全部待干的发射单（底座助手提，统筹按推荐裁）

- 问题：04 第 98 行写一个 run 会话「用 `rl handoff start --batch` 一次接下整个 batch」，05 第 65 行的签名是 `rl handoff start ID [--batch B]` 只收一个 ID；21 分册「留给 gyb」第 6 条明写「是不是一次把 N 张单都置 in_progress 且 holder 都记同一个会话，表里只有单张单的那一行」没裁。
- 决定：后者。带 `--batch B` 时，ID 用来定位 batch（ID 必须属于 B，不属于退出码 5），rl 把 batch 为 B、状态 todo 的全部 `launch_order` 一起置 in_progress，每张各追加一版 start、holder 都记本会话；销号时整批交回（04 第 122 行已这么写）。不带 `--batch` 只接 ID 那一张。同一 batch 里 N 张单的 host 和 gpus 怎么分仍没裁，代码标 `PENDING(part 21 L181)`。
- 理由：和 04 第 98 行「一次接下整个 batch」字面一致；备选（只接一张、逐张 start）让那句落空。签名里 ID 显得多余是 05 冻结正文的事，最后一期改 05 时可以把 ID 改成可省。
- 落点：`research-loop/scripts/rl_lib.py`、`research-loop/bin/rl`（handoff start）；`research-loop/tables/commands.json` 那一行的 notes；测试 7 补一条整批 start 的用例；sync-inbox 问题 48(d) 给 05 第 65 行。
- 审查：

### D-23 派活的会话要活到子会话回来，打印模式的派活会话要带 `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`（待验证第 9 条测完，统筹裁）

- 问题：验证记录第三节：母会话活着时后台子会话跑满 1200 秒并回通知；母会话三种结束方式子会话都被杀；打印模式（`-p`）的母会话默认只等后台子会话 600 秒，到点终止，被终止的子会话和母会话都没有触发销号钩子（标准错误原文在 3.7 节）；带 `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` 时等了 728 秒、子会话跑完、通知到、SessionEnd 触发。
- 决定：不做机制，写纪律两句：派活的会话（idea 派 deploy、idea 派 analysis、deploy 派 run）在子会话回来之前不退出，`/exit` 选留下（与 D-20 同一句）；用打印模式或者 workflow 起的派活会话要带 `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`，否则 600 秒到点连销号钩子都不触发、单子要靠 reclaim 收。落点是三份派活角色 SKILL.md 的派活段和入口 skill 的领路，来源标注 verify.md 3.5、3.7 加 proxy decision D-23。30 待验证第 9 条状态栏同步。
- 理由：600 秒上限是宿主行为，插件改不了；失败备案（被杀就等下一个 run 认领）照旧成立，但是没有销号钩子的那种死法要 reclaim 兜，说明书里写明比让人撞上强。
- 落点：`research-loop/skills/idea/SKILL.md`、`skills/deploy/SKILL.md`（派活段）、`skills/reviewer/SKILL.md`（按清单起 sonnet 子会话那段，14 第 95 行）；`skills/research-loop/SKILL.md`；30 第 21 行状态栏。
- 审查：
### D-24 快车道补单的行：actor 记 deploy、`from_role` 记 gyb、`to_role` 记 deploy（评审助手提，统筹按推荐裁）

- 问题：04 第 19 行「`from_role` 就是 owner，可以是 `gyb`」，07 第 96 行「`from_role` 和 `to_role` 都是 deploy」，07 第 116 行定稿「开单动作由 deploy 做，owner 记 gyb」；handoffs 没有单独的 owner 字段，owner 从 `from_role` 推。三句同时成立只有一种写法。底座测试 test_02 第 83 到 86 行那处标了 UNDECIDED。
- 决定：补单行 actor 记 deploy（谁写的），`from_role` 记 gyb（owner），`to_role` 记 deploy（谁干活）。`transitions.json` 的 owner_definition 和 open_quick_lane 行注明，来源标注 proxy decision D-24；test_02 那处按此写。
- 理由：07 第 116 行是 07 定稿时对第 96 行那句的裁定（「设计文档『`from_role` 和 `to_role` 都是 deploy』」那句在 116 行里被点名改），04 第 19 行 owner 从 `from_role` 推是定义处；三句里后裁的赢。
- 落点：`research-loop/tables/transitions.json`；`research-loop/tests/test_02_transitions.py`；sync-inbox 问题 41 段加统筹补扫 (k)。
- 审查：

### D-25 写权钩子内部出错时放行、往标准错误留痕、不注入身份；注入身份的钩子不许替用户批准工具调用（评审助手提，统筹按推荐裁）

- 问题：底座 0dc07a8 的钩子 main() 捕获一切异常返回 0 不输出，等于出错放行，06 没写这种情况；同一份钩子里注入子会话身份那一支返回 permissionDecision "allow"，按官方文档这是替用户批准这次工具调用，子会话在研究仓库里的每条 Bash 都会被插件自动放行，权限模式失效。06 只授权钩子拦两类事（06 第 13 行），没授权替人批准。
- 决定：（1）钩子内部出错放行，但往标准错误打一行 `research-loop hook error: <原因>`，并且不注入身份；理由是拒收会把 gyb 的裸会话和所有非角色目录的写一起拦死，钩子判不出角色时本来就该放行（06 第 102 行），放行加留痕让 reviewer 事后查得到。（2）注入身份不许带 permissionDecision "allow"；改输入但不替人批准的写法由评审派子会话查官方文档，结果到了按结果改；官方没有这种写法就回到 D-15 的备选（子会话不注入、rl 按状态文件读母会话角色并把 `agent_id` 留空、账上记不出子会话身份），并改 D-15、sync-inbox 问题 49。
- 理由：写权钩子是唯一硬拦的一层，出错的处置要成文；替用户批准工具调用超出 06 给钩子的授权，是权限层的事，不能顺手做。
- 落点：`research-loop/hooks/rl_hook.py` 头注与实现；`research-loop/tables/README.md` 惯例；测试 8 补出错放行的用例。
- 审查：

- 更正 2026-09-05（文本助手指出）：统筹原来把 analysis 写进落点是错的，analysis 的 `dispatches_to` 为空（06 第 218 行）、说明书里没有派活段；reviewer 按清单起 sonnet 子会话，打印模式起的 reviewer 会话同样受 600 秒上限，所以落点是 idea、deploy、reviewer 三份。「留下」保得住子会话是推断不是实测（verify.md 第一节「没测的」），说明书里写成纪律、不写成已验证。
