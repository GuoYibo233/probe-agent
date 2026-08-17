# 分权三层、钩子、角色 json

> 这份覆盖约束分成的三层（钩子、入账校验、纪律）各管什么、钩子拦哪两类事又放行什么、钩子的回话怎么写、钩子怎么跟角色绑定、没加载角色的裸会话靠 CLAUDE.md 那一节的三句话、角色 json 的五栏定义和五份 json 逐栏的内容、`tests/test_skill_refs.py` 查什么、读的纪律。
> 不覆盖的：九本账每一行的字段和 status 取值写在 `03-ledgers.md`；派活单转移表和会话登记销号的流程写在 `04-handoffs-and-sessions.md`；`rl` 每条子命令的参数、退出码、`rl status` 的十段写在 `05-rl-cli.md`；`--as-gyb` 和 `--quote` 这条规矩本身、gyb 的豁免范围从 gyb 那头看是什么样写在 `01-gyb.md`；公共母版八条规矩、`common/READING.md` 的正文、反馈账写在 `09-common-and-feedback.md`；插件树里 hooks/ 和 monitors/ 摆在哪、init 建什么写在 `08-trees-init-and-host.md`；每个角色的 use case 表和干活流程写在 `10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`、`14-role-reviewer.md`；待验证清单的测法和测试清单写在 `30-build-steps-verify-tests.md`。
> 源：设计文档的「分权与钩子」一节、「五个角色」总段、「两棵树」一节里插件本体那一段、「待验证清单」；施工计划第一节裁决 3、5、6、7、8，第五节（角色 json 与 gyb 的 use case 表），第六节 actor 判定那一段，第七节 run 照 gpu-run 写的钩子那一格，第九节待验证清单，第十节测试 8、9、13，第十三节公共规矩第 8 条。

## 三层约束，各管各的

约束分三层（原则 2）：钩子、入账校验、纪律。三层管的东西不重叠，写规矩的时候要先想清楚这一条落在哪一层。

### 第一层是钩子，硬拦，宽宽的

钩子只挂 Write 和 Edit 两个工具，只按研究仓库内的相对路径判，只拦两类离谱事：写别的角色的目录，直接写 loop/。仓库外的路径一律放行。路径怎么折、白名单怎么放，写在下一节「路径怎么判」（2026-08-18 gyb 裁）。

这一层是硬的，模型绕不过去。

### 第二层是入账校验，硬的

九本账只能经 `bin/rl`。每本账内部谁能追加哪种行、哪一版哪些字段必填、转移表允许哪些变化，都由入账脚本按施工计划校验，违反的拒收并说明下一步。

gyb 只豁免「谁能调」和「谁能写」两样。完整性校验对 gyb 同样生效：必填字段、路径存在、引用存在这些数据校验不看是谁在写，gyb 要硬写就加 `--force --reason`，rl 照写并把 reason 记进账行（原则 1 推论）。转移表的「前提」一栏就是完整性校验，对 gyb 生效。

这一层拦下来的退出码有两个：校验拒收是 2，角色无权是 3，两种都把原因写到标准错误第一行（固定的原因种类），3 还附一条「开 issue 给谁」的命令。退出码一共六个（0/1/2/3/4/5），完整表在 `03-ledgers.md`，`05-rl-cli.md` 照抄同一张表。

### 第三层是纪律，写在 SKILL.md 里

第三层管的是：读什么、怎么读、Bash 里能写什么、什么时候该开 issue、什么时候该停下来问 gyb。

Bash 写出来的文件钩子不看，宿主发射器的台账、读什么、怎么读，全归这一层。这一层有一句专门管绕钩子的（2026-08-18 gyb 裁）：用 Bash 往四个角色目录和 `loop/` 写（重定向、脚本、`cp`、`mv` 都算）等于绕钩子，不许；要写就用 Write/Edit 让钩子看得见，账本一律走 `rl`。这句进公共规矩第 8 条和每份角色 SKILL.md，reviewer 事后拿 git 历史对着 sessions 账查。reviewer 事后审的就是这一层。

公共规矩第 8 条把三层的出圈处理写成一句：钩子拦下的，原话告诉模型开哪条 issue；钩子不拦但越出自己 writes 的（宿主文件、Bash 写入），列进报告并留决定并守宿主规矩；读账一律经 rl 查询命令，查询命令谁都能调。八条规矩的正文在 `09-common-and-feedback.md`。

### 读一律不设权

读不上任何一层的硬拦（原则 2 推论）。九本账的查询命令谁都能调，角色 json 的 `reads` 栏是纪律不是门禁。机器检查只做文本对照、不设读的门禁：写命令在不在 `ledger_writes` 里、SKILL.md 里出现的账名和目录在不在 `reads` 里、引用的名字存不存在、有没有抄母版，见「`tests/test_skill_refs.py` 查什么」（2026-08-18 gyb 裁，三样都查）。

## 钩子拦什么、放什么

### 拦两类

一类是写别的角色的目录：

| 目录 | 只有谁能写 |
|---|---|
| `experiments/` | deploy |
| `analysis/` | analysis |
| `review/` | reviewer |
| `notes/` | gyb、idea（2026-08-18 gyb 裁） |

`notes/` 的主人是 gyb，gyb 的裸终端本来就不受钩子管，所以这一行在角色会话里等于「只放 idea 会话」，这是本意，不是漏（2026-08-18 gyb 裁）。

另一类是直接 Write 或 Edit `loop/`。九本账只能经 `bin/rl` 进出，任何角色直接改账本文件一律 deny。

### 路径怎么判（2026-08-18 gyb 裁）

钩子按敲出来的路径判：绝对路径折成相对仓库根的写法，相对路径按会话工作目录折，不追软链接。软链接指到仓库外的东西（new1 的产物目录就是仓库里一个指到 net 盘的软链接）按它在仓库里的位置判：落在四个角色目录或 `loop/` 里照拦，不落就放。这样谁也不能靠在角色目录里放一个指到外面的软链接绕过钩子。

另有一张白名单：列在白名单里的路径不管折成什么一律放行。白名单是插件配置里的一项（和阈值表放一起，见 `08-trees-init-and-host.md`），默认为空，由 gyb 在 `rl init` 之后按需填，用来放那些「路径写在仓库里、东西其实在仓库外」的地方。

仓库外的路径仍一律放行不变。

### 放行什么

仓库外的路径一律放行：git worktree、产物根、`/tmp` 都在仓库外。

仓库内其余路径钩子放行：仓库根的 `run.py`、`MAP.md`、`ops/`、docs 之类。这些路径归纪律管，deploy 改到 `experiments/` 外的宿主文件时的三条纪律（列进部署报告带文件的那一份、在 `decisions.deploy.jsonl` 留一条来源指向那个文件、守宿主仓库自己的规矩）写在 `11-role-deploy.md`。

钩子对哪个角色都不加特例。idea 的 `writes` 只有 `notes/`，可是 idea 会话写仓库根的文档、docs 之类同样放行：`writes` 栏是「该写哪」的纪律口径，钩子只拦「不该写哪」的两类离谱事，两者不是一回事；idea 越出去写了，按公共规矩第 8 条列进报告（2026-08-18 gyb 裁，对回原则 2）。

Bash 写出来的文件钩子不看。所以宿主发射器 `run.py launch` 写 `ops/jobs.json`、`ops/runs.jsonl`、`RUNMETA.json` 这些照旧，不算越权。但用 Bash 往四个角色目录和 `loop/` 写等于绕钩子，纪律明令不许，句子在第三层那一节。

硬拦只管加载了角色的会话。gyb 的裸终端和 `--as-gyb` 不受钩子约束。

run 会话身上装的是同一套写权钩子，按第七节写死的话是：Write/Edit 进 `experiments/`、`analysis/`、`review/`、`notes/`、`loop/` 一律 deny 并提示开 issue，其余放行。run 自己的 `writes` 是 `artifact_root`，在仓库外，钩子不判。

### 钩子的验收用例

测试 8 定了五个用例，钩子按这五条验收：

| 场景 | 预期 |
|---|---|
| deploy 会话 Write `analysis/x` | deny，且标准错误含「开 issue」命令 |
| 任何角色 Write `loop/x.jsonl` | 一律 deny |
| run 会话 Write `experiments/x` | deny |
| deploy 会话 Write 仓库根 `run.py` | 放行 |
| deploy 会话 Write 仓库外 worktree 路径 | 放行 |

施工步 4 的验收里还有一条：在真会话里手动触发一次 deny 和一次销号。

## 钩子的回话要指路

拦下越权用 deny，同时告诉模型三样：你是谁、为什么拦、去开 issue 的命令是什么。

读失败之类的场合同样要返回合理的下一步建议（换个办法、还是发给哪个角色），学 Claude Code 工具调用失败时的回话方式。

被钩子拦下之后开的 issue，kind 是 `denied`，这一种 kind 的 `handoff_id` 必填。issue 的九种 kind 在 `03-ledgers.md`。

这条 issue 的收件人是被写的那个目录的主人，也就是上面钩子表「只有谁能写」栏里的主人（`experiments/` 归 deploy、`analysis/` 归 analysis、`review/` 归 reviewer、`notes/` 归 gyb），钩子回话里那条开 issue 的命令 `--to` 就填这个（2026-08-18 gyb 裁，对回原则 3：拦的理由是「这是别人的地盘」，那就把要改的事说给地盘的主人）。直接写 `loop/` 被拦的场合没有「主人」可指，回话直接指出该用哪条 `rl` 写命令，不给开 issue 的命令——这半句是定稿时补的推论，不是 gyb 原话。

## 钩子跟角色绑定

先有角色才有钩子。钩子写在角色 SKILL.md 的头部，加载角色的那一刻装上，不存在「用钩子去认角色」这回事。

这个机制 2026-08-16 已实测：加载前不拦、加载后拦、拦的时候模型收到钩子写进标准错误的原话。

一个会话只加载一个角色。这是纪律，机器不管：第二次加载会发生什么（钩子叠不叠、状态文件覆不覆盖、sessions 账落几行）不定义、不兜底，公共规矩和每份角色 SKILL.md 写一句「一个会话只加载一个角色，要换角色另开会话」（2026-08-18 gyb 裁，问题六选 c）。

### 钩子还干登记和销号

hooks/ 里除了写权钩子，还有登记和销号两个钩子。

登记：加载 skill 把角色分配给会话的那一刻算会话开始，钩子看得见这次加载，自动登记进 sessions 账。开始版由钩子代角色写，`actor` 填角色。`model` 由钩子从钩子输入的 JSON 里取，取不到记 `unknown`。

销号：挂在 SessionEnd 和 SubagentStop 上，不指望模型自觉调结束命令。销号那一刻要做的检查和 release 动作写在 `04-handoffs-and-sessions.md`。

### 会话状态文件

`rl` 判 actor 靠会话状态文件：状态文件由角色 skill 头部钩子在加载时写，路径 `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json`；`rl` 从它读当前角色，读不到状态文件就是裸终端，actor 是 `gyb`，session_id 记 `cli`。

状态文件谁删（2026-08-18 gyb 裁）：销号钩子在会话结束时顺手删；会话被强杀删不掉的留着，由 `rl doctor` 扫，sessions 账里对应会话已销号、或文件超过一天没动的当垃圾清。活死以 sessions 账为准，状态文件只是缓存（原则 8）。`${CLAUDE_PLUGIN_DATA}` 在这台机器上解析到哪还没测，并进待验证清单第 1 条一起测；宿主不给这个变量的备案是插件在用户目录下自定一个数据目录。

### 钩子脚本本身

hooks/ 是钩子脚本本体：五个角色共用一个脚本、参数报角色名。这一条 2026-08-18 已实测（gyb 点名先测这一条）：skill 头部钩子命令写成「脚本 加 `--role test`」，加载后触发，脚本收到的参数原样是 `--role test`，标准错误里回的角色名模型也原话收到；备案「五个角色各一份、只差常量」作废。测试留在 `~/.claude/jobs/8a102def/tmp/hookargs/`。monitors/ 里只有一个看门狗，只在 run 上线时起，只写自己的状态文件，不写九本账。

和钩子有关的待验证条目有五条，测法和失败备案在 `30-build-steps-verify-tests.md`：Bash 环境里有没有现成的会话 id 变量；skill 头部声明的钩子能不能给命令带参数；monitor 的 `when: "on-skill-invoke:run"` 写法；SessionEnd 和 SubagentStop 在 subagent 结束时触发不触发、会话 id 是不是同一个；subagent 里加载角色 skill 头部钩子装不装得上、写权拦不拦；钩子输入里有没有模型标识。第 2 条已测通过（见上）；其余仍按 gyb 裁定：讨论全部收口之前一律不测。顺带看到的一个事实，不算正式测：2026-08-18 那次测试里 PreToolUse 的钩子输入有会话 id、工作目录、权限模式、工具入参，没有模型标识。

## 裸会话靠研究仓库的 CLAUDE.md

没加载角色的裸会话身上没有钩子，什么都能写。这一点不用兜底钩子去堵：`rl init` 往研究仓库的 CLAUDE.md 里追加一节，追加不覆盖，仓库原有的规矩照旧。

这一节的内容是三句：

1. 「没有 gyb 允许，experiments/、analysis/、review/、loop/ 只能在加载了对应角色的会话里改」
2. 「加载了 run 角色的会话以 run 的 SKILL.md 为准，它是 gpu-run 的超集，宿主 GPU 铁律里的『唯一入口』对 run 会话读作 run skill」
3. 「loop/*.jsonl 和 loop/.lock 不算脏树」

第三句连带一处宿主改动：new1 的发射门禁白名单要加这两样，宿主 CLAUDE.md 那一行由 gyb 改。这处改动排在施工步 7，由 gyb 亲手改，见 `08-trees-init-and-host.md`。白名单按 `loop/*.jsonl` 字面照旧，`loop/.doctor-acks.jsonl` 顺带不算脏、ack 之后可以直接发射；`03` 说账本总规矩不管 ack 文件，只是说它不受账本约束，不是说门禁要拦它（2026-08-18 gyb 裁，sync-inbox 问题 32，原话「a」）。

裸会话和读权一样靠纪律。「裸会话装兜底钩子」这个提议 gyb 顶回过，换成 init 往 CLAUDE.md 写一句纪律。

## 角色 json：五栏和五份内容

每个角色由两份文件定义：一份 SKILL.md，一份 json。json 里的东西从 SKILL.md 的 use case 表倒推（原则 5）：每个 use case 写清读哪些账和目录、写哪个目录、调哪些 rl 写命令，前四栏是这张表的并集，`model` 另记。五份 json 合起来就是分权表本体，钩子按角色读自己那份。

各角色的 use case 表在各自那一份：`10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`、`14-role-reviewer.md`。

### 五栏是什么

| 栏 | 装什么 | 谁用它 |
|---|---|---|
| `reads` | 读哪些账和目录 | 纪律，不设门禁；测试 13 拿它做文本对照 |
| `writes` | 能 Write/Edit 的目录 | 钩子用 |
| `ledger_writes` | 能调哪些 rl 写命令 | 入账校验用 |
| `dispatches_to` | 能派活给谁 | 纪律，机器不查（2026-08-18 gyb 裁）；谁派了不该派的人，事后从 sessions 账看谁起了谁 |
| `model` | `as_subagent` 和 `manual` 两个取值 | 登记会话时用 |

`model` 这一栏的 `manual` 写 `inherit` 是声明跟当前会话走，sessions 账落解析后的真实模型名或 `unknown`。

`reads` 栏的写法定死两种（2026-08-18 gyb 裁）：账写账名（九本账的英文名，decisions 细到 `decisions.<角色>`），目录和文件写相对仓库根的路径（目录带尾斜杠）；「全部」「一切」一律展开成清单，不写句子。备注（要 grant、只在快车道、只读部署报告目录）不进 json，写在表下面。测试 13 按这两种形式逐个对。

`dispatches_to` 栏机器不查、纯纪律（2026-08-18 gyb 裁，对回原则 2 钩子只管写、原则 5 权限从用例来）：这一栏是写给角色 SKILL.md 和 reviewer 看的清单，子会话登记时带角色和 `launched_by`，谁起了谁的下线从 sessions 账一目了然，越权派活当场不拦、事后能查。reviewer 起 sonnet subagent 逐题查不算这一栏的「派活」，reviewer 的 `dispatches_to` 仍是无（2026-08-18 已裁：不算派活，`dispatches_to` 不动；sync-inbox 问题 33，原话「选a」）。

角色 json 改一栏算改母版（2026-08-18 gyb 裁，对回原则 9）：走 feedback 账记一条、采纳后单独 commit（前缀 `research-loop rules:`）、`rules_version` 一起加一，生效时刻同母版（下次加载角色时生效）。流程本体在 `09-common-and-feedback.md`。

`rl inbox` 是查询命令，不是上线动作：角色被拉起不自动查收件箱，先干拉它起来的那张单，谁需要谁敲（2026-08-17 gyb 裁，sync-inbox 问题 28）。查询命令（show、list、trace、status、inbox、stale、doctor）谁都能调，不进 `ledger_writes`；`rl doctor --ack`、`--unack` 是写命令、只有 gyb 能敲（2026-08-17 gyb 裁，sync-inbox 问题 23）。

### 五份 json

idea：

| 栏 | 值 |
|---|---|
| `reads` | `decisions.idea`、`decisions.deploy`、`decisions.run`、`decisions.analysis`、`decisions.reviewer`、`decisions.gyb`、issues、handoffs、runs、grants、feedback、evaluations、sessions、scratch、`notes/`、`analysis/`、`experiments/`、`review/` |
| `writes` | `notes/`（2026-08-18 gyb 裁，原来是「无目录」） |
| `ledger_writes` | decisions.idea 全部、handoffs 的 open/accept/reject/withdraw/release/reissue/resume/amend、issues 的 open/reply/reassign/close、feedback add |
| `dispatches_to` | deploy、analysis |
| `model` | `as_subagent` 是 fable，`manual` 是 inherit |

备注：`notes/` 要 gyb 发 `read:notes` 才读；`experiments/` 只读部署报告目录。

deploy：

| 栏 | 值 |
|---|---|
| `reads` | `decisions.idea`、`decisions.gyb`、`decisions.deploy`、handoffs、issues、runs、feedback、`experiments/`、`ops/gpu_state.md` |
| `writes` | `experiments/`（worktree 在仓库外，钩子不判） |
| `ledger_writes` | decisions.deploy 全部、handoffs 的 start/done/stuck/open/accept/reject/withdraw/release/resume/amend、issues 全部、scratch 全部（含 ql open/close）、feedback add |
| `dispatches_to` | run、gpu-runner |
| `model` | `as_subagent` 是 opus，`manual` 是 inherit |

备注：`ops/gpu_state.md` 只在快车道自己跑 GPU 时读；gpu-runner 只在快车道派。

run：

| 栏 | 值 |
|---|---|
| `reads` | handoffs、issues、runs、`experiments/`、`ops/gpu_state.md` |
| `writes` | `artifact_root`（仓库外，钩子不判） |
| `ledger_writes` | runs 全部、handoffs 的 start/estimate/done/stuck、issues 的 open、decisions.run add（自决极少，比如挑卡的理由）、feedback add |
| `dispatches_to` | 无 |
| `model` | `as_subagent` 是 opus，`manual` 是 inherit |

备注：handoffs 只读自己那张 `launch_order`，issues 只读归自己的。

run 不查 inbox：run 只关注自己那张发射单，一般不会有没带单子的 run 会话（2026-08-17 gyb 裁，sync-inbox 问题 28）。

analysis：

| 栏 | 值 |
|---|---|
| `reads` | runs、evaluations、handoffs、issues、feedback、`decisions.idea`、`decisions.gyb`、`analysis/` |
| `writes` | `analysis/` |
| `ledger_writes` | evaluations 的 propose/update、handoffs 的 start/done/stuck、issues 的 open/reply、scratch 全部、decisions.analysis 全部、feedback add |
| `dispatches_to` | 无 |
| `model` | `as_subagent` 是 opus，`manual` 是 inherit |

reviewer：

| 栏 | 值 |
|---|---|
| `reads` | `decisions.idea`、`decisions.deploy`、`decisions.run`、`decisions.analysis`、`decisions.reviewer`、`decisions.gyb`、issues、handoffs、runs、grants、feedback、evaluations、sessions、scratch、`experiments/`、`analysis/`、`review/`、`notes/` |
| `writes` | `review/` |
| `ledger_writes` | decisions.reviewer 全部、session focus、feedback add |
| `dispatches_to` | 无 |
| `model` | `as_subagent` 是 fable，`manual` 是 inherit |

reviewer 不开 issue。reviewer 的 `reads` 原来写「一切（九本账、全部目录）」，按 2026-08-18 的写法裁决展开成上面的清单，意思不变。

### 模型这一栏

施工计划第一节裁决 3：由 agent（subagent 或 workflow）调用的时候，run、deploy、analysis 用 opus，idea、reviewer 用 fable；gyb 手动加载角色的时候跟当前会话的模型一致。两个取值分开写进 json 的 `model` 字段。

| 角色 | `as_subagent` |
|---|---|
| idea | fable（gyb 2026-08-16 点名例外） |
| deploy | opus |
| run | opus |
| analysis | opus |
| reviewer | fable（同上） |

idea 和 reviewer 用 fable 与本机 `~/.claude/CLAUDE.md` 的「subagent 默认不用 Fable」不一致，按原则 8 工程内为准：这条裁决就是 gyb 点名的那一次例外，插件的 README 和角色 json 里都要明写「fable 是 gyb 2026-08-16 点名的例外」。

run 的模型 2026-08-16 晚 gyb 改裁为 opus，原来写的 sonnet 那一句作废。

## `tests/test_skill_refs.py` 查什么

这条机器检查有三件事要查。

三样都查（2026-08-18 gyb 裁，对回原则 8 后裁为准：三份原文里最全的那份就是最后写的）：

1. 写命令：SKILL.md 正文出现的每条 rl 写命令都在这个角色 json 的 `ledger_writes` 里；查询命令不查。
2. 读权：SKILL.md 正文出现的每个账名和每个目录（按 `reads` 栏定死的两种写法逐个对）都在这个角色 json 的 `reads` 里。
3. 名字存在、不抄母版：五份 SKILL.md 里出现的每条 rl 子命令、账名、状态名、目录名都在对应定义处查得到（施工时是 `tables/`、`schemas/`、`bin/rl` 的子命令表）；SKILL.md 里没有 common/ 母版条文的副本。

第三件事对应的规矩是：SKILL.md 不抄公共母版的条文，只写一句「按 common/ 执行」。母版本体见 `09-common-and-feedback.md`。

三份原文原来不一致：设计文档「五个角色」总段只写了第 1 样，施工计划第五节多了第 2 样，测试 13 又多了第 3 样。2026-08-18 gyb 裁三样都查，第 2 样能查是因为同一天把 `reads` 栏的写法统一了。

## 读的纪律

读的纪律写进每个角色 SKILL.md 的读法栏，公共母版里的原话方向是这几句：

读文件先想清楚要回答什么问题，再挑最小的读法。读进来的每个字都留在上下文里挤占后面的判断，所以大文件禁止整读，抽查实验输出就是抽几条看文字形态，日志用 grep 和头尾定位。读记忆一律经 rl 的查询命令、只读自己需要的那部分、默认最新版，不直接开 loop/ 下的文件；`rl inbox` 和 `rl decision stale` 都只列和本会话手上单子有关的，不列全库。对污染上下文大的读操作特别警惕。

这几句的正式文本落在 `common/READING.md` 里，见 `09-common-and-feedback.md`。

读权一律不硬拦，所以这一栏全靠纪律加 reviewer 事后查。唯一接回机器的一处是授权：idea 读 `notes/` 要 gyb 发 `read:notes`，grant 是给 reviewer 事后查的凭据，doctor 有一项扫描「决定的来源指向 notes/ 但 grants 里查不到这个 actor 的 read:notes」。授权账的行格式在 `03-ledgers.md`，这项扫描在 `05-rl-cli.md`。

## 和别的 part 的接口

这一份是定义处的东西：三层约束、钩子拦放（含路径判法和白名单的规矩）、钩子回话（含 `denied` issue 收件人是目录主人）、钩子跟角色绑定、会话状态文件的写和删、CLAUDE.md 那三句、角色 json 五栏定义和五份 json 内容（含 `reads` 栏的两种写法、`dispatches_to` 机器不查、json 改动算母版改动）、`tests/test_skill_refs.py` 查三样、读的纪律的方向。别处引用这些的时候指到这一份。

- 九本账的公共骨架（`actor`、`session_id`、`force_reason`、`via`）和每本账的必填规则：定义在 `03-ledgers.md`。
- issue 的 kind `denied`、`request`，`handoff_id` 什么时候必填，`assignee` 的取值：定义在 `03-ledgers.md`；`denied` issue 的收件人填目录主人这条规矩定义在本份「钩子的回话要指路」。
- sessions 账的 `role`、`model`、`launched_by`、`rules_version`、`status`、`focus` 各栏：定义在 `03-ledgers.md`。
- grants 账的 `grantee`、`permission`（第一版只有 `read:notes`）、谁能写（只有 gyb；裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收）：定义在 `03-ledgers.md` 和 `01-gyb.md`。
- 转移表的「谁能写」和「前提」两栏、gyb 对哪一栏豁免：定义在 `04-handoffs-and-sessions.md`。
- 会话登记和销号那两个钩子调的命令 `rl session start` 和 `rl session end`、销号时扫哪些状态：定义在 `04-handoffs-and-sessions.md` 和 `05-rl-cli.md`。销号钩子顺手删会话状态文件这一步是本份 2026-08-18 加的，`04` 已冻结，列在「要同步到别处的」等统筹。
- `rl doctor` 的扫描项：定义在 `05-rl-cli.md`。本份 2026-08-18 加的「陈旧会话状态文件」清理项，`05` 已冻结，列在「要同步到别处的」等统筹。
- `rl` 的 actor 判定、`--as-gyb`、`--quote`、`--force --reason` 这一组规矩：定义在 `01-gyb.md` 第二节（2026-08-17 gyb 裁）；参数写法和退出码在 `05-rl-cli.md`。
- gyb 的豁免范围从 gyb 那头怎么用、裸终端就是 gyb 这条推论：写在 `01-gyb.md`。
- 快车道里 deploy 派 gpu-runner 这条 `dispatches_to` 的例外：写在 `07-quick-lane.md`。
- 插件树里 hooks/、monitors/、tables/roles/ 摆在哪，`rl init` 往 CLAUDE.md 追加那一节的时机，宿主脏树白名单那处改动，阈值表：写在 `08-trees-init-and-host.md`。钩子路径白名单是配置里的一项，落在 `08` 的阈值表（本份 2026-08-18 加，列在「要同步到别处的」）。
- 公共母版八条规矩（尤其第 8 条出圈即留痕）、`common/READING.md`、`rules_version` 与母版改动流程：写在 `09-common-and-feedback.md`。本份 2026-08-18 加的三句要进那边：第 8 条补「Bash 往角色目录和 `loop/` 写等于绕钩子，不许」；母版加「一个会话只加载一个角色，要换角色另开会话」；`rules_version` 一节补「角色 json 改动同流程」。
- 待验证清单每条的测法、通过标准、失败备案，测试 8 和测试 13 在施工步骤里的位置：写在 `30-build-steps-verify-tests.md`。第 2 条（头部钩子带参数）2026-08-18 已测通过、备案作废；`${CLAUDE_PLUGIN_DATA}` 解析到哪并进第 1 条一起测。
- 五份角色 json 的副本、每个角色的 use case 表和干活流程：写在 `10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`、`14-role-reviewer.md`。副本要跟本份一字不差：2026-08-18 改了 idea 的 `writes`（`notes/`）、五份的 `reads` 写法、deploy 的 `dispatches_to` 写法（备注移到表下）；每份 SKILL.md 要加两句纪律（Bash 绕钩子、一会话一角色）。
- deploy 改宿主文件的三条纪律、reviewer 的读顺序：写在 `11-role-deploy.md` 和 `14-role-reviewer.md`。

## 源文档没写清的（留给 gyb）

（原来的十一条 2026-08-18 全部裁完，逐条见文末「裁决记录（日期）」，正文已按裁决改。）

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

下面的条目从 `plans/2026-08-16-research-loop-simulation-round2.md` 原样抄来，保留场景名、序号、严重度、kind、原文、依据、改法，没有核实，也没有判断。

### param-tweak（45 步，gyb 动手 8 次）

13. [slows/ambiguous] 第 12 到 16 步：快车道里 GPU「照旧走 gpu-run」，gpu-run Phase 4 明写发射环节整段派 gpu-runner agent、不在主对话手搓，但 deploy 的 dispatches_to 只有 run，派 gpu-runner 算不算越权没写
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:58; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：deploy 的 dispatches_to 加 gpu-runner 并注明只在快车道用，或明写快车道 deploy 自己发射
17. [cosmetic/contradiction] 第 4 步：设计文档说 SKILL.md 正文出现的每条 rl 子命令都要在角色 json 的 ledger_writes 里，施工计划的测试 13 只查写命令；deploy 上线要跑的 rl decision stale、rl handoff show 都是查询命令，不在 deploy 的 ledger_writes 里，按设计文档那句机器检查就红
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:215; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：把设计文档那一句改成「每条 rl 写命令」，或角色 json 加一栏 queries 单列查询命令
19. [cosmetic/ambiguous] 第 24 步：「gyb 看着行就合回主分支」这句的主语是 gyb，但 deploy 用 Bash 做 merge 钩子也不拦，谁执行 merge 两种读法都成立
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:132
   - 改法：明写 merge 由 gyb 亲自打，deploy 只把命令交出来
20. [cosmetic/missing] 第 3 步：sessions 账要求手动加载也记真实模型名、不记 inherit，而角色 json 的 manual 一律是 inherit；钩子从哪里拿到当前会话的真实模型标识没写，待验证清单里也没有这一条
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:189
   - 改法：待验证清单加一条「SessionStart 钩子输入里有没有模型标识」，拿不到就退到 rl session start --model unknown

### new-idea（39 步，gyb 动手 7 次）

7. [slows/missing] 第 4 步：sessions 账要求手动加载也记真实模型标识、不记 inherit，可角色 json 的 manual 一栏写死 inherit，登记钩子调 rl session start --model M 时这个 M 从哪来没写；gyb 手动加载 idea 时钩子拿不到真实模型名
   - 依据：plans/2026-08-16-research-loop-next-steps.md:103; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：明写钩子从钩子输入的 JSON 里取 model 字段传给 rl，取不到就记 unknown 并由 rl doctor 列出来
11. [slows/missing] 第 15 步：new1 的探针代码没搬进 experiments/，deploy 改的是仓库根的宿主代码，插件只写了钩子放行加「列进报告并留决定」；宿主仓库 CLAUDE.md 要求扩展流水线必须从 probe-pipeline skill 进、代码与 run.py 注册表同一个 commit，两套规矩没有对接句，deploy 会绕过宿主的注册表
   - 依据：plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:132; plans/2026-08-16-research-loop-build-plan.md:10
   - 改法：deploy 的 SKILL.md 加一句「改 experiments/ 外的宿主文件时按宿主仓库 CLAUDE.md 的规矩走，new1 是 probe-pipeline 加 run.py 注册表」

### result-wrong-review（25 步，gyb 动手 11 次）

4. [slows/contradiction] 第 9 步、第 10 步、第 13 步（reviewer 全程只调查询命令）：设计文档说机器检查是「SKILL.md 正文出现的每条 rl 子命令都要在这个角色 json 的 ledger_writes 里」，施工计划的 test_skill_refs 只要求写命令在 ledger_writes 里；reviewer 的 SKILL.md 必然写到 rl decision stale、rl decision show、rl run show、rl handoff show 这些读命令，按设计文档那句检查必挂。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：把设计文档第 40 行改成「写命令进 ledger_writes、读命令进 reads」，和测试 13 对齐。

### plot-new-plan（17 步，gyb 动手 8 次）

3. [slows/principle_violation] 第 10 步（gyb 开分析单）：违反原则 1。原则 1 写 gyb 在任何终端、任何角色会话里都能行使自己的权，任何权限检查不生效；但施工计划只让 gyb 豁免转移表「谁能写」一栏和「谁能调」检查，「前提」一栏照旧生效，于是 gyb 自己开分析单时被 evaluation_refs 必须 approved 这条前提挡住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:77; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：在施工计划第四节表头明写「前提」一栏对 gyb 生不生效，若生效就把它改称数据完整性校验、和权限检查分开命名。
11. [slows/missing] 第 3 步（钩子登记会话）：sessions 账要求记真实模型标识、不记 inherit，角色 json 里手动加载那一栏又一律写 inherit；钩子调 rl session start 的时候从哪里拿到真实模型名没写。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:103; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99
   - 改法：明写 model 由 rl session start 从会话环境或钩子输入里读，读不到就记 unknown 并让 doctor 列出来。

### next-plan-after-results（36 步，gyb 动手 16 次）

3. [slows/principle_violation] 第 14 步：违反原则 1。原则 1 和施工计划裁决 6 说 gyb 不受任何权限检查影响，转移表却只给 gyb 豁免「谁能写」一栏、不豁免「前提」一栏，于是 gyb 自己也开不出引未批口径的分析单、也收不了缺交付物的单子。两句话对「权限检查」的范围理解不一样
   - 依据：2026-08-16-research-loop-build-plan.md:77; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15
   - 改法：把原则 1 改写成「权限检查对 gyb 不生效，数据完整性前提对谁都生效」，并给 gyb 一个 `--force` 带原因写进账行

### n-launch-orders（58 步，gyb 动手 10 次）

11. [slows/principle_violation] 第 41 步：违反原则 1（gyb 是超级用户，钩子、入账校验、转移表的谁能写对 gyb 一律不生效）。施工计划规定角色会话里用 --as-gyb 缺 --quote 一律退出码 2，而 rl 分不出键盘前面坐的是 gyb 本人还是模型，结果 gyb 在自己手动加载的角色会话里反而行使不了 gyb 权，只能退出会话回裸终端。这和裁决 6「gyb 在任何终端、任何角色会话里都能插入」直接打架。
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15; 2026-08-16-research-loop-next-steps.md:34
   - 改法：缺 quote 时不拒收，改成照写并在账行打一个 quote_missing 标记留给 reviewer 事后查。
17. [cosmetic/missing] 第 13 步：run 上线第一个动作是跑 rl decision stale，但 run 的角色 json 里 reads 不含 decisions 账，发射单上也没有 decision_refs，这条检查对 run 是空转。
   - 依据：2026-08-16-research-loop-build-plan.md:131; 2026-08-16-research-loop-build-plan.md:105; 2026-08-16-research-loop-build-plan.md:81
   - 改法：把「上线跑过版检查」限定给 idea、deploy、analysis 三个角色，或者让 launch_order 继承父工单的 decision_refs 之后 run 再查。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

15. [slows/contradiction] 第 3 步：sessions 账要求「手动加载记真实模型名，不记 inherit」（next-steps.md:103、build-plan.md:71），角色 json 的 model 栏又写「`manual` 一律 `inherit`」（build-plan.md:99）。钩子调 `rl session start --role R --model M`（build-plan.md:126）时那个 M 从哪里取，两份文档都没写，第九节待验证清单也没有这一条。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:103; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：把「钩子输入里有没有模型标识」加进第九节待验证清单，拿不到就允许 sessions.model 记 `unknown`，两处口径统一。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

4. [blocks/missing] 第 17 步：没写 loop/ 九本账进不进 git、要不要加进宿主的脏树白名单。new1 的门禁把 ops/jobs.json、ops/runs.jsonl、RESULTS.md、*.lock 排除在脏之外，loop/*.jsonl 不在里面；而每一条 rl 命令都在追加行，run 走到「发射前 commit」那一刻工作树必脏，要么把账本一起 commit 进去（发射前 commit 那一步禁止 --allow-dirty），要么被门禁拦住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:161; /home/y-guo/reproduce/new1/CLAUDE.md:36; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:54
   - 改法：rl init 时把 loop/*.jsonl 和 loop/.lock 一起加进宿主 run.py 的脏树白名单，并在 research-loop.json 里记一句账本入不入 git。
5. [slows/contradiction] 第 13 到 19 步：run 角色 skill 照 gpu-run 写、能力至少覆盖它的全生命周期，等于 GPU 活从 run skill 走；但 new1 的 CLAUDE.md 是「任何要用显卡跑的程序一律走 gpu-run skill，禁止绕过」，而 rl init 明写「往 CLAUDE.md 追加一节，追加不覆盖，new1 原有的规矩照旧」。两条都是工程内的规矩，原则 8 的「工程内为准」裁不动这一对。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:19; plans/2026-08-16-research-loop-build-plan.md:153; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-next-steps.md:22; /home/y-guo/reproduce/new1/CLAUDE.md:3
   - 改法：rl init 追加的那一节里明写一句「加载了 run 角色的会话以 run SKILL.md 为准，gpu-run 铁律对它不适用」，并同步改 new1 CLAUDE.md 第 3 行。
13. [slows/guessed] 第 13 步：整段「deploy 会话起 run subagent、subagent 里加载角色 skill、头部钩子装得上、写权拦得住」建立在待验证第 8 条上，那一条还没测，备案是改走 workflow 的 agentType 或者干脆只靠纪律。我按主案（钩子装得上）走完了这一段，主案不成立的话第 13 到 20 步的登记、销号、写权全部要换写法。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:167; plans/2026-08-16-research-loop-build-plan.md:196; plans/2026-08-16-research-loop-build-plan.md:227
   - 改法：施工步 0 先把第 8 条测掉，测完在设计文档 run 一节写死走主案还是备案，不留两种走法。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

9. [cosmetic/contradiction] 第 14 步：手动加载的会话在 sessions 账里 model 记什么，两处打架：sessions 行格式写「真实模型标识，手动加载也记真实的，不记 inherit」，角色 json 那一栏写「model 分 as_subagent 和 manual，manual 一律 inherit」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-next-steps.md:103
   - 改法：角色 json 那一栏加半句「manual 写 inherit 是声明跟当前会话走，sessions 账落解析后的真实模型名」，两句各自限定清楚。
11. [slows/too_heavy] 第 15、18 步：角色上线第一个动作 rl decision stale 没有范围参数，列的是全库过版的单子和决定。两条线并行时，蒸馏线的 deploy 一上线就把探针线的过版项读进上下文，和读法纪律「读进来的每个字都留在上下文里挤占后面的判断、只读自己需要的那部分」直接顶。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-next-steps.md:144
   - 改法：rl decision stale 加 --mine 和 --handoff 两个过滤，角色上线默认只查本会话要接的那张单子相关的决定。

### feedback-round（15 步，gyb 动手 9 次）

2. [blocks/principle_violation] 第 7 步（gyb 查 feedback）与第 13 步（deploy 想知道裁决结果）：违反第 6 条「进出对称」和第 5 条「权限从动作倒推」：deploy、run、analysis 三份角色 json 的 ledger_writes 都有 feedback add，reads 里都没有 feedback；命令表也只有 feedback list 没有 feedback show。提反馈的角色写得进去、查不出来，自己提的那条被采纳还是被否只能靠 gyb 口头说
   - 依据：plans/2026-08-16-research-loop-build-plan.md:103; plans/2026-08-16-research-loop-build-plan.md:105; plans/2026-08-16-research-loop-build-plan.md:107; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-next-steps.md:94
   - 改法：五份角色 json 的 reads 一律加 feedback，命令表补 `rl feedback show ID`
8. [slows/missing] 第 10 步（gyb 自己 grep 五份 SKILL.md）：母版 common/ 和五份角色 SKILL.md 是引用关系还是抄一份，文档没写；施工步 5 和步 6 是两步分别写的两组文件。抄了的话改母版根本不生效，gyb 只能自己去 grep 五份 SKILL.md 有没有重复条文
   - 依据：plans/2026-08-16-research-loop-next-steps.md:150; plans/2026-08-16-research-loop-build-plan.md:232; plans/2026-08-16-research-loop-build-plan.md:233; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：定死 SKILL.md 只写一句「按 common/GLOBAL-RULES.md 执行」、不许抄条文，测试 13 加一条查 SKILL.md 里有没有母版条文的副本

### idea-request-notes（15 步，gyb 动手 4 次）

2. [slows/contradiction] 第 5 步：命令表里 `rl grant add / rl grant list` 整行的「谁能调」只写 gyb，idea 调 grant list 应拿退出码 3；但 idea 的 reads 写的是「九本账全部」，公共规矩第 8 条又要求「读账一律经 rl 查询命令」。结果是 idea 查不到自己名下有没有 read:notes，每开一个新会话都只能重新走一遍申请，或者凭猜
   - 依据：plans/2026-08-16-research-loop-build-plan.md:138; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:252; plans/2026-08-16-research-loop-next-steps.md:52
   - 改法：第六节把 grants 拆成两行：`grant add` 谁能调写 gyb，`grant list/show` 谁能调写「谁都行」
8. [slows/missing] 第 12 步：读权不上钩子、靠纪律加 reviewer 事后查，但文档没写 reviewer 拿什么查「idea 有没有在没 grant 的时候就读了 notes/」。系统里没有读日志，doctor 的八项扫描里也没有这一类，这条纪律实际上无从核对
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:136; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl doctor` 加一项扫描「decisions 里 source 指向 notes/ 但 grants 里查不到该 actor 的 read:notes」，把这条纪律接回入账校验那一层

### periodic-reclaim（27 步，gyb 动手 11 次）

12. [slows/principle_violation] 第 23 步：违反原则 1。runs 账的行格式写死「actor 必须是 run」，而原则 1 说任何权限检查对 gyb 一律不生效。gyb 要给回收下来的孤儿发射版补一条 exit=killed 的收尾版，按前一句写不进去，按原则 1 写进去就破了 schema，入账脚本按哪一条实现没有定论。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：runs 账的 actor 改成允许 run 或 gyb，字段表那一句后面补「gyb 例外，同原则 1」。
14. [slows/missing] 第 13 步：钩子调 rl session start 时那一行的 actor 填什么没写。公共骨架规定 actor 取值是五个角色或 gyb，钩子两样都不是。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：明写钩子代角色写账，sessions 开始版的 actor 填 --role 那个角色，session_id 填新会话。

### smoke-fails（44 步，gyb 动手 4 次）

14. [cosmetic/contradiction] 步 10（run 上线跑过版检查）：设计文档说角色上线第一个动作跑过版检查，这是对所有角色说的；施工计划第五节给 run 的 reads 只有 handoffs 里的 launch_order、experiments/、ops/gpu_state.md、runs，不含 decisions。rl decision stale 要读 decisions 账，run 跑它就越出自己的 reads 栏，不跑又违反上线第一个动作那句。发射单本来也不引决定，run 跑了也查不出跟自己有关的东西。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-build-plan.md:105; plans/2026-08-16-research-loop-build-plan.md:131
   - 改法：明写过版检查只对 idea、deploy、analysis、reviewer 强制，run 免跑；或者把 decisions 的只读加进 run 的 reads。
15. [slows/guessed] 步 9 与步 22（run subagent 的钩子与销号）：待验证清单第 5 条（SubagentStop 在 subagent 结束时触不触发、会话 id 是不是同一个）和第 8 条（subagent 里加载角色 skill 钩子装不装得上）都还没测，两条各有备案，选主案还是备案会改掉本场景一半的走法：备案里 subagent 路线改成 workflow 的 agentType，或者「接单只靠纪律加 reviewer 事后查」，那样 run 的写权拦不住、销号全靠 reclaim、sessions 账没有结束版。我这次按主案走，属于猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:193; plans/2026-08-16-research-loop-build-plan.md:196; plans/2026-08-16-research-loop-next-steps.md:164; plans/2026-08-16-research-loop-next-steps.md:167
   - 改法：施工步 0 出结论之后，按选中的那一案把 run 的 SKILL.md 和第七节改死，删掉另一案，不留两条路。
16. [cosmetic/missing] 步 2 与步 9（钩子登记会话）：sessions 账要求 model 记真实模型标识、手动加载也记真实的、不记 inherit，rl session start --role R --model M 由钩子调；但钩子从哪拿到这个真实模型名，文档没写，待验证清单第 1 条只查了会话 id 有没有现成变量，没查模型标识。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:189; plans/2026-08-16-research-loop-next-steps.md:103
   - 改法：待验证清单加一条「钩子输入里有没有模型标识」，拿不到就退成记 unknown 并把启动命令一起写进账行。

### doctor-findings-fix（24 步，gyb 动手 15 次）

3. [blocks/contradiction] 第 23 步（gyb 能不能手写 runs 行）：设计文档说「第二层是入账校验，硬的……gyb 例外」，读起来 gyb 连必填字段和 actor 限制都免；施工计划说「actor 是 gyb 时跳过全部『谁能调』和转移表『谁能写』的检查」，读起来只免这两类。runs 那一行写着 actor 必须是 run，gyb 到底能不能补写一行 runs 直接取决于这两句谁算数。
   - 依据：2026-08-16-research-loop-next-steps.md:134; 2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:63
   - 改法：在施工计划第六节写死一句「gyb 只豁免谁能调与转移表谁能写，schema 必填与 actor 限制对 gyb 同样生效」，并把设计文档那句「gyb 例外」改成同一句话。

## 裁决记录（日期）

- 2026-08-17 gyb 裁（sync-inbox 问题 1，原话「这个归01吧」，rl-hub 转来）：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 定义处归 `01-gyb.md`。接口一节的指向照改。
- 2026-08-17 来自 sync-inbox 问题 15 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「B」）：`fix_for` 栏删掉，公共骨架的可选栏是 `force_reason`、`via` 两个。「和别的 part 的接口」一节第一条里的 `fix_for` 换成 `via`。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `05`，rl-hub-v3 传；gyb 原话「只有做完了的时候才关，巡检要我本人确认」）：`rl doctor --ack`、`--unack` 是写命令、只有 gyb 能敲。「角色 json：五栏和五份内容」一节里「查询命令谁都能调，不进 `ledger_writes`」那句后面补上这一条。
- 2026-08-17 来自 sync-inbox 问题 27 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「3 不是，可以替我写」）：grants 在角色会话里 `--as-gyb --quote` 替 gyb 写也收。接口一节 grants 那条的「只收 `cli` 这条规矩」改成「谁能写（只有 gyb；裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收）」。
- 2026-08-17 来自 sync-inbox 问题 28 的裁决（定义处 `01`，命令行写法在 `05`，rl-hub-v3 传；gyb 原话「每个角色创建时候，不要自动查收件箱」「C」「顺便run只需要关注自己的工单，一般不会空run，不需要查，这个改了」）：「角色 json：五栏和五份内容」一节的「所有角色上线第一个动作都是 `rl inbox`」改成「`rl inbox` 是查询命令，不是上线动作：角色被拉起不自动查收件箱，先干拉它起来的那张单，谁需要谁敲」；run 那份 json 后面的「run 的 `rl inbox` 不查过版」改成「run 不查 inbox：run 只关注自己那张发射单，一般不会有没带单子的 run 会话」。
- 2026-08-18 gyb 裁（问题一，原话「有的时候会用到仓库外的东西，建议弄一个白名单，白名单下的文件都允许修改」）：钩子按敲出来的路径判、折成相对仓库根、不追软链接；另加一张白名单，白名单里的路径一律放行；仓库外仍一律放行。对回原则 2。「钩子拦什么、放什么」加「路径怎么判」小节。
- 2026-08-18 gyb 裁（问题二，原话「问题2现在就测一下」）：待验证第 2 条当场测，结果 skill 头部钩子命令带的参数原样到达脚本；一份共用脚本、参数报角色名成正案，备案「五份各一份」作废。对回原则 8。「钩子脚本本身」照改。
- 2026-08-18 gyb 裁（问题三，原话「选a」）：idea 会话写仓库内不属于任何角色的地方钩子放行是本意，钩子不给 idea 加特例；`writes` 是纪律口径不是钩子口径。对回原则 2。「放行什么」补一段。
- 2026-08-18 gyb 裁（问题四，原话「让idea能写gyb」）：idea 可以写 `notes/`。钩子表 `notes/` 那行改成「gyb、idea」，idea 的 `writes` 从「无目录」改成 `notes/`；这一行在角色会话里等于只放 idea，是本意。对回原则 3、5。
- 2026-08-18 gyb 裁（问题五，原话「5a」）：会话状态文件由销号钩子顺手删；删不掉的由 `rl doctor` 扫，sessions 账已销号或超过一天没动的清掉；活死以 sessions 账为准。对回原则 8。「会话状态文件」补一段。
- 2026-08-18 gyb 裁（问题六，原话「6 c」）：一个会话只加载一个角色只写纪律，机器不管，第二次加载的行为不定义不兜底。对回原则 2。「钩子跟角色绑定」补一句。
- 2026-08-18 gyb 裁（问题七，原话「a」）：`dispatches_to` 机器不查，纯纪律，事后从 sessions 账看谁起了谁。对回原则 2、5。五栏表和五栏说明照改。
- 2026-08-18 gyb 裁（问题八，原话「a」）：`reads` 栏定死两种写法——账写账名（decisions 细到 `decisions.<角色>`），目录和文件写相对仓库根的路径；「全部」「一切」展开成清单；备注移到表下；测试 13 按此逐个对。对回原则 8。五份 json 的 `reads` 行照改。
- 2026-08-18 gyb 裁（问题九，原话「a」）：角色 json 改一栏算改母版，走 feedback 账、单独 commit、`rules_version` 一起加一。对回原则 9。五栏说明补一段。
- 2026-08-18 gyb 裁（问题十，原话「a」）：钩子拦下之后开的 `denied` issue 归被写目录的主人（`notes/` 归 gyb）。对回原则 3。「钩子的回话要指路」补一段；`loop/` 被拦不给开 issue 命令那半句是定稿时补的推论。
- 2026-08-18 gyb 裁（问题十一，原话「a」）：补一句纪律进公共规矩第 8 条和每份角色 SKILL.md——用 Bash 往四个角色目录和 `loop/` 写等于绕钩子，不许，要写就用 Write/Edit，账本一律走 `rl`；reviewer 事后拿 git 历史对着 sessions 账查。对回原则 2。第三层那一节照改。
- 2026-08-18 来自 sync-inbox 问题 32 的裁决（rl-hub-v4 转来，gyb 原话「a」）：CLAUDE.md 第三句不改字；「第三句连带一处宿主改动」那段末尾补上和 `08` 第六节一字不差的一句（白名单按 `loop/*.jsonl` 字面照旧，`loop/.doctor-acks.jsonl` 顺带不算脏、ack 之后可以直接发射）。
- 2026-08-18 来自 sync-inbox 问题 33 的裁决（rl-hub-v4 转来，gyb 原话「选a」）：reviewer 起 sonnet subagent 逐题查不算派活，reviewer json 的 `dispatches_to` 仍是无，本份「等问题 33」的标注结掉。
- 2026-08-18 gyb 裁（问题十二，正文那处「两处原文不一致」，原话「a」）：`tests/test_skill_refs.py` 三样都查——写命令 ∈ `ledger_writes`；SKILL.md 里出现的账名和目录 ∈ `reads`；引用的名字都存在、母版不抄。对回原则 8。那一节重写。

## 要同步到别处的

下面这些是 2026-08-18 定稿时牵连别的 part 的，这边只列不改，已经 SendMessage 报给 rl-hub-v4 并追加到 `sync-inbox.md`。

- `08-trees-init-and-host.md`：阈值表加一项钩子路径白名单（配置项，默认为空，gyb 在 `rl init` 之后按需填；列在里面的路径钩子一律放行）。hooks/ 那行「五个角色共用一个脚本、参数报角色名」维持，可注「2026-08-18 已实测」。
- `30-build-steps-verify-tests.md`：待验证第 2 条状态改「已测通过（2026-08-18，参数原样到达），主案定，备案删」；第 1 条并入「`${CLAUDE_PLUGIN_DATA}` 在本机解析到哪，宿主不给就插件在用户目录下自定数据目录」；第 6 条（钩子输入里有没有模型标识）可注「2026-08-18 一次 PreToolUse 观察里没有，正式结论仍等测」。
- `09-common-and-feedback.md`：rule-08 补半句「用 Bash 往四个角色目录和 `loop/` 写等于绕钩子，不许，要写就用 Write/Edit，账本一律走 `rl`」；母版加一句「一个会话只加载一个角色，要换角色另开会话」；第四节 `rules_version` 补「角色 json 改动同流程：feedback 记一条、单独 commit、`rules_version` 加一」；第七节「`notes/` 只有 gyb 写」改成「`notes/` gyb 和 idea 写」。
- `10-role-idea.md`：json 副本 `writes` 「无目录」改 `notes/`；第 13 行「idea 的角色 json 里 writes 一栏是空的，一个目录都不能 Write 或 Edit」照改；`reads` 行按新写法展开（清单见本份 idea 那张表）；SKILL.md 加两句纪律（Bash 绕钩子、一会话一角色）。
- `11-role-deploy.md`：json 副本 `reads` 去掉括号备注、`dispatches_to` 改「run、gpu-runner」并把「只在快车道」「快车道自己跑 GPU 时」两条备注移到表下；第 19 行「写别的角色的目录（`analysis/`、`review/`、`notes/`）」仍对，可加「`notes/` idea 也能写」；SKILL.md 加两句纪律。
- `12-role-run.md`：json 副本 `reads` 改「handoffs、issues、runs、`experiments/`、`ops/gpu_state.md`」，「只读自己那张 `launch_order`」「只读归自己的 issue」移到表下；SKILL.md 加两句纪律。
- `13-role-analysis.md`：json 副本 `reads` 写法核对（现在已经是账名加路径，只要确认没有句子）；SKILL.md 加两句纪律。
- `14-role-reviewer.md`：json 副本 `reads` 从「一切（九本账、全部目录）」展开成清单（见本份 reviewer 那张表）；第 117 行测试 13 的描述对齐本份「三样都查」；SKILL.md 加两句纪律。
- `05-rl-cli.md`（已冻结，冻结后待议）：doctor 加一项「陈旧会话状态文件」——sessions 账已销号或超过一天没动的状态文件，修法是删文件、归 gyb 推；第 100 行「机器检查只查 SKILL.md 里出现的写命令在不在 `ledger_writes` 里」与本份「三样都查」不一致。
- `04-handoffs-and-sessions.md`（已冻结，冻结后待议）：销号钩子的动作清单加「删本会话的状态文件」。
