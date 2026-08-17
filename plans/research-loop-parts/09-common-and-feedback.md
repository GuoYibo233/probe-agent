# 公共母版与反馈账

> 这一份覆盖六样东西：`common/` 五个文件各写什么（含规格模板的五栏是哪五栏、判断类检查问题清单的文件名）、公共规矩八条（rule-01 到 rule-08）的全文、`rules_version` 是什么样、怎么走、`rule-NN`/`principle-NN` 编号不变、feedback 账的行格式和五条命令加采纳之后的待办、issues 账的行格式与九种 kind 与 reply 和 close 的规矩、grants 账的行格式与写入限制。issues 和 grants 是跨角色的公共件，所以放在这一份里。
> 这一份不覆盖：九本账的公共骨架和其余六本账的行格式（`03-ledgers.md`）、派活单状态转移表与会话生命周期（`04-handoffs-and-sessions.md`）、`bin/rl` 的完整命令表和 doctor 的全部扫描项（`05-rl-cli.md`）、`rl status` 的十段与 gyb 的 use case 表（`01-gyb.md`）、分权三层和角色 json（`06-hooks-and-permissions.md`）、五个角色各自什么时候开哪种 issue（`10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`、`14-role-reviewer.md`，以及 `20-pair-idea-deploy.md` 到 `25-pair-reviewer-idea.md` 六份成对文件）、快车道和杂账（`07-quick-lane.md`）、阈值与配置文件（`08-trees-init-and-host.md`）、施工步骤和测试清单（`30-build-steps-verify-tests.md`）。
> 源：设计文档的「gyb 自己做的事」「五个角色」总段、「账本」一节（行格式骨架与第 2、5、6 三本）、「分权与钩子」的读的纪律段、「两棵树」的插件本体段；施工计划第一节裁决 4、第二节词表、第三节 issues/grants/feedback 三本、第六节命令表的相关行、第八节阈值三条、第十一节的 commit 前缀、第十三节公共规矩八条。

## 一、common/ 是什么，里面五个文件

`common/` 是公共母版，放在插件本体里（插件本体的另外几层是 `skills/`、`tables/`、`schemas/`、`scripts/`、`bin/rl`、`hooks/`、`monitors/`、`tests/`）。母版带一个 `rules_version`。

| 文件 | 写什么 |
|---|---|
| `common/GLOBAL-RULES.md` | 公共规矩八条加十一条设计原则，头部一行带 `rules_version`（整数，这一行是唯一真源，见第四节），条目编号是 `rule-NN` 和 `principle-NN`，编号一经定下不再变（见第三节） |
| `common/GLOSSARY.md` | 词表，就是施工计划第二节那份，再加一栏「它不是什么」 |
| `common/SPEC-TEMPLATE.md` | 角色定义的五栏——角色设定、使用场景、可用工具、限制条件、输出样式，是每份角色 SKILL.md 的骨架；「可用工具」一栏只指到角色 json 的四栏，不抄。这五栏沿用 8 月 15 日 `redesign.md` 里 gyb 定的「五栏规格」，和 reviewer 清单「一条问题五栏」是两份东西（2026-08-18 gyb 裁） |
| `common/READING.md` | 读法栏的原话 |
| `common/REVIEW-CHECKLIST.md`（文件名 2026-08-18 gyb 裁） | 判断类检查的问题清单：脚本判不了、要读了才知道对不对的那些项。不进 doctor（doctor 只留脚本能判的十九项），reviewer 按这份清单派 sonnet subagent 一人一题逐条查，查出来的写进 `review/` 清单，要不要开 issue 由 gyb 看完用自己的权限开（2026-08-17 随 `05` 定稿裁；只写清单不开 issue 是 gyb 裁，sync-inbox 问题 6） |

词表那一栏「它不是什么」，施工计划第二节写的是「留到 `common/GLOSSARY.md` 写的时候逐条给 gyb 过，这里只钉名字」。

`common/READING.md` 收的读法原话，设计文档给的方向是这几句：读文件先想清楚要回答什么问题，再挑最小的读法；读进来的每个字都留在上下文里挤占后面的判断，所以大文件禁止整读，抽查实验输出就是抽几条看文字形态，日志用 grep 和头尾定位；读记忆一律经 rl 的查询命令、只读自己需要的那部分、默认最新版，不直接开 `loop/` 下的文件；`rl inbox` 和 `rl decision stale` 都只列和本会话手上单子有关的，不列全库；对污染上下文大的读操作特别警惕。每个角色的 SKILL.md 有一个读法栏，内容从这份母版来。

`common/` 由施工步 5 交付，依赖施工步 3，验收是 gyb 逐条过；执行者是主会话，底稿给 gyb 过，过了就是正式版。五份角色 SKILL.md 是施工步 6，排在母版后面。

## 二、SKILL.md 只引用母版，不抄条文

角色的 SKILL.md 按 `common/SPEC-TEMPLATE.md` 的五栏写（角色设定、使用场景、可用工具、限制条件、输出样式；「可用工具」一栏只指到角色 json，不抄四栏内容——2026-08-18 gyb 裁），不抄公共母版的条文，只写一句「按 `common/` 执行」。这一条有机器检查兜着：`tests/test_skill_refs.py` 查 SKILL.md 里没有 `common/` 母版条文的副本。抄了条文，改母版就不生效，gyb 只能自己去 grep 五份 SKILL.md。

同一个测试还查另外两件事：SKILL.md 正文出现的每条 rl 写命令都在这个角色 json 的 `ledger_writes` 里，查询命令不查（这是原则 2 的推论，读不设权）；SKILL.md 里出现的每条 rl 子命令、账名、状态名、目录名都在施工计划第二、五、六节里查得到。角色 json 那四栏怎么倒推，在 `06-hooks-and-permissions.md`。

## 三、公共规矩八条（rule-01 到 rule-08）

这八条是从设计文档抽出来的，替代 8 月 15 日 `redesign.md` 的通例九条，母版里的编号是 rule-01 到 rule-08。施工计划第一节裁决 4 的原话：公共规矩不再沿用 8 月 15 日 `redesign.md` 第 97 到 105 行的通例九条本文，改成从设计文档里重新抽一份；九条里第③条「机验人判」gyb 裁定去掉，其余八条 gyb 认可仍然代表本意；第⑦条里「自己域自己修」只留给 deploy 和 idea，run 出问题一律开 issue 给 deploy。

八条全文照抄施工计划第十三节：

1. 岔路缺省：规格没写到的岔路，角色按十一条原则推着往下干并追加一条决定，来源写清依据；替 gyb 说话的写入（`--as-gyb`、evaluations 批准、feedback 裁决）没有 gyb 当场的原话一律硬停，不可逆动作（收回、废除）硬停并带原话或理由。
2. 自决必留痕：角色自己做的每个决定进自己那本 decisions 文件，来源不许空；改变实验结果的选择才算自决，纯写法不算；gyb 在角色会话里当场拍的板算 gyb 的决定，落同一本账、actor 记 gyb、带 quote。
3. 数字只经脚本入账：runs 账只有 run 的脚本能写（gyb 例外），实验数据一个 schema，禁止用眼睛读日志填数。
4. 证据配路径：每个数字配可复现的执行路径，统计类证据走 analysis 的 notebook；单个 run 的原始指标可以直接引，跨 run 的对比、聚合、画图一律走分析单。
5. 口径不发明：analysis 只算 gyb 说要看的数、只画 gyb 说要画的图；写代码不算算数，出数才要 `approved` 的口径。
6. 故障分域：deploy 和 idea 接到问题先判病因在不在自己域，在就地修；run 出问题一律开 issue 给 deploy，不自行重试，重来是发射单上的下一次尝试；analysis 卡住开 issue 给出问题的角色；reviewer 不开 issue，卡住也只写进清单交给 gyb。
7. 改规矩走反馈账：角色不许自改母版和规格，提到 feedback 之后照现行母版继续干，不等裁决；裁决只对下次加载的会话生效。
8. 出圈即留痕：钩子拦下的，原话告诉模型开哪条 issue；钩子不拦但越出自己 writes 的（宿主文件、Bash 写入），列进报告并留决定并守宿主规矩；读账一律经 rl 查询命令，查询命令谁都能调。用 Bash 往四个角色目录和 `loop/` 写（重定向、脚本、`cp`、`mv` 都算）等于绕钩子，不许，要写就用 Write/Edit 让钩子看得见，账本一律走 `rl`；reviewer 事后拿 git 历史对着 sessions 账查（这半句 2026-08-18 gyb 裁，定义处 `06` 第三层）。

8 月 15 日第③条「机验人判」不收录，理由是 gyb 裁定意义不明。

编号 `rule-01` 到 `rule-08`、`principle-01` 到 `principle-11` 一经定下不再变（2026-08-18 gyb 裁）：废掉一条留空号、不补位；新加一条往后排；改一条只换内容、不换号。反馈的 `target` 和决定的来源都引这些编号，编号不动旧引用才对得上（原则 8、4）。

rule-01 点名的两个不可逆动作各有落点：收回是 `rl handoff withdraw --reason [--quote]`（`04-handoffs-and-sessions.md`）；废除是 `rl decision retire`，2026-08-18 gyb 裁废除也必须带理由，谁废都要（角色废自己的、gyb 在裸终端废都一样），理由记进那一版决定行；角色会话里替 gyb 废除的原话按 `--as-gyb --quote` 的既有身份规矩带，不另加。命令签名归 `05-rl-cli.md`、决定行上记理由的那一栏归 `02-decisions.md`，本份只引。

母版里另有一句纪律，不占编号（2026-08-18 gyb 裁，定义处 `06`「钩子跟角色绑定」）：一个会话只加载一个角色，要换角色另开会话；机器不管，第二次加载的行为不定义、不兜底。这句同时写进每份角色 SKILL.md。

设计文档 reviewer 一节里还留着一句「施工计划公共规矩第 6 条里 reviewer 那半句按这一句改」，施工计划第十三节 rule-06 现在的写法已经是改过的那一版（reviewer 不开 issue，卡住也只写进清单交给 gyb），两处说的是同一件事，不用再裁。

## 四、rules_version 与母版改动的生效时刻

母版文件里带一个 `rules_version`：整数、从 1 起、写在 `common/GLOBAL-RULES.md` 头部一行，这一行是唯一真源（2026-08-18 gyb 裁）。会话账的开始版就从这一行读，记下这个会话加载时的 `rules_version`（sessions 的字段在 `04-handoffs-and-sessions.md`）。feedback 采纳的那一版由 rl 自动填 `rules_version_after`，`rl feedback accept` 顺带把头部那一行加一并写回文件；母版正文的改动仍由人手改，rl 只动这一行，这是 rl 唯一一处往母版文件写字的动作。

角色 json 改一栏算改母版，同一个流程（2026-08-18 gyb 裁，定义处 `06`「五栏是什么」）：feedback 账记一条、采纳后单独 commit（前缀 `research-loop rules:`）、`rules_version` 一起加一，生效时刻同母版。

生效时刻定死一句：母版改动在下次加载角色时生效，正在跑的会话不追、不通知，按现行母版干到底。规矩 7 是同一件事的角色侧写法：提到 feedback 之后照现行母版继续干，不等裁决；裁决只对下次加载的会话生效。

采纳的时候 rl 列出还活着的会话和它们各自的 `rules_version`，让 gyb 挑要不要收。收会话的动作本身走 `rl session end --session ID`，在 `04-handoffs-and-sessions.md`。

有一条待验证挂在这里（施工计划第九节第 11 条）：改一行母版、不重启 claude、同一进程再加载一次角色，模型读到的是不是新文本。通过标准是模型看到新文本；失败备案是在 `rl feedback accept` 打印的待办里加一句「改完母版必须重开终端」。

## 五、feedback 账

feedback 是反馈账，谁都能提、只有 gyb 能裁；谁都能读，提的人在 `rl inbox` 里看得到裁决。文件是 `loop/feedback.jsonl`。

行格式（公共骨架七样另见 `03-ledgers.md`）：`id`；`target`，取值只有两种：文件路径，或者带前缀的编号 `rule-06`、`principle-06`；要改的是某张表的某一行（转移表的一行、命令表的一行）时，`target` 填那张表所在文件的路径，哪一行写进 `text`（2026-08-18 gyb 裁）；`text`；`status` 取 `proposed`、`accepted`、`rejected`，`accepted` 和 `rejected` 都是终态：被打回之后要再提就 `rl feedback add` 开新一条，`text` 里说明接着哪一条，rl 不建链，没有改一版的子命令（2026-08-18 gyb 裁）；`verdict_text`，`accepted` 和 `rejected` 两版都必填：采纳的写采纳成什么样，不采纳的写为什么；`applied_to`，采纳时必填、至少写一个，是路径列表，rl 校验每个路径存在；`rules_version_after`，采纳时 rl 自动填。提的那一版谁都能写，裁的那一版 `actor` 必须是 `gyb`。

采纳的那一版要写清改了哪几个文件，母版和文档都算，至少写一个、不要求两样都有（2026-08-17 gyb 裁，sync-inbox 问题 26；doctor 第 17 项只在 `applied_to` 为空时报）。

命令五条：

| 命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl feedback add --target ... --text` | 提一条 | 谁都行 |
| `rl feedback accept ID --applied-to FILE ... [--text]` | 采纳 | gyb |
| `rl feedback reject ID --text` | 打回 | gyb |
| `rl feedback show ID` | 查一条 | 谁都行 |
| `rl feedback list` | 列表 | 谁都行 |

`accept` 做四件事：校验 `applied_to` 每个路径存在、自动把 `rules_version` 加一并写回 `common/GLOBAL-RULES.md` 头部那一行、列出还活着的会话和它们的 `rules_version`、打印一张待办。待办上写的是还要改哪几处、要不要收会话、单独 commit 加跑测试。

采纳之后的 commit：母版改动单独一个 commit，前缀是 `research-loop rules:`，改完跑一遍 `tests/run_all.py`。施工那八步用的前缀是 `research-loop v2:`，两个前缀分开用。

feedback 的入口和出口各挂在三处：`rl status` 段 8 列等裁的 feedback；`rl notify` 的推送表里有「feedback 提出」一条；角色的 `rl inbox` 里有一类是本角色提的 feedback 的裁决。定期提醒（`notify.reminder_days` 默认 7）叫 gyb 做四件事，其中一件是把采纳的 feedback 落进母版并单独 commit。doctor 有一项扫描：accepted 的 feedback 的 `applied_to` 为空（2026-08-17 gyb 裁，sync-inbox 问题 26；`05-rl-cli.md` doctor 第 17 项）。

五个角色的 `ledger_writes` 里都有 `feedback add`，`reads` 里也都有 feedback（run 那份原来缺，2026-08-18 gyb 裁补上：能提就能查自己那条的裁决，原则 5、6；定义处 `06-hooks-and-permissions.md`）。

## 六、issues 账

issues 是问题条，文件是 `loop/issues.jsonl`。用途是九类里的这几种：干不了、不归我干、被钩子拦了、跑失败（smoke、发射、跑挂三段）、结果反常、申请、通知（收回、孤儿、fyi）。开一条等 assignee 回。每条带「归谁」字段：run 开给 deploy，deploy 解决不了改派给 gyb。

行格式：`id` 形如 `iss-0031`；`assignee` 是五个角色或 `gyb`；`status` 取 `open`、`answered`、`closed`；`kind` 九选一；`stage` 在 `failed` 时必填；`text`；`reply` 在 `answered` 时必填；`handoff_id` 在 `cannot`、`failed`、`denied`、`withdrawn`、`orphaned` 时必填，其余可选；`log_tail` 可选。

九种 kind：

| kind | 中文 | 备注 |
|---|---|---|
| `cannot` | 干不了 | `handoff_id` 必填 |
| `not_mine` | 不归我干 | |
| `denied` | 被钩子拦了 | `handoff_id` 必填 |
| `failed` | 跑失败 | 附 `stage`，取 `smoke`、`launch`、`crash`；`handoff_id` 必填 |
| `anomaly` | 结果反常 | |
| `request` | 申请 | |
| `withdrawn` | 你手上的单子被收回了 | 通知类；`handoff_id` 必填 |
| `orphaned` | holder 会话死了单子交回了 | 通知类；`handoff_id` 必填 |
| `fyi` | gyb 越过 owner 处理了你的单子 | 通知类 |

改派等于追加一版换 `assignee`。`assignee` 是 `gyb` 的那一版（含首次开单）触发桌面通知，其余进角色的 `rl inbox`。

写权三条：`reply` 只有 `assignee` 或 gyb 能写；`close` 只有开单的 actor 或 gyb 能写，通知类 issue（`withdrawn`、`orphaned`、`fyi`）的 `assignee` 也能关（2026-08-17 gyb 裁，sync-inbox 问题 23：`rl inbox` 只读不关，通知类 issue 由收件人做完了自己 `rl issue close`）；另有一处自动关：`rl handoff accept` 关这张单关联的 `answered` issue。reviewer 不开 issue。

命令：`rl issue open --to R --kind K [--stage S] --text [--handoff ID] [--log-tail FILE|--log-text -]`、`rl issue reassign ID --to R`、`rl issue reply ID --text`、`rl issue close ID`、`rl issue link ID --handoff ID`、`rl issue show ID`、`rl issue list [--open] [--to R] [--kind K]`。`--to gyb`（开单或改派）触发通知；`link` 是 doctor 给的修法。谁能调按角色 json 的 `ledger_writes`，查询谁都行。

跨账写序定死：标卡住要同时开 issue 和改单子，先写 issue 拿到编号，再写单子那一行引它。中间崩了顶多多一条没人引的 issue，doctor 扫得出来。转移表里 `in_progress` 到 `stuck` 那一行的前提是 `issue_id` 指向一条已存在的 issue，并且那条 issue 的 `handoff_id` 指回本单。

两条阈值跟 issues 走：`issues.gyb_stale_hours` 默认 24，`rl status` 段 2 标出超过 24 小时没动的；`issues.answered_stale_days` 默认 3，doctor 报 answered 超过 3 天没 close。doctor 另有两项和 issues 有关：`cannot`/`failed`/`denied` 且 open 且没有单子指回的 issue，以及单子回了 `todo` 而关联 issue 还 open。

## 七、grants 账

grants 是授权，文件是 `loop/grants.jsonl`，只有 gyb 能写。

行格式：`id` 形如 `grant-0003`；`grantee` 是角色；`permission` 是字符串，第一版只有一种 `read:notes`；`status` 取 `active`、`revoked`；`expires_at` 可选；`text`；`issue_id` 可选。`actor` 必须是 `gyb`；裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收，`session_id` 照记那个会话。

命令：`rl grant add --to R --permission P [--expires ...] [--issue ID]`、`rl grant revoke ID`、`rl grant list`、`rl grant show ID`。写只有 gyb，查谁都行。

撤销之后已经加载了这条 grant 的会话怎么办（2026-08-18 gyb 裁）：`rl grant revoke` 时 rl 列出 grantee 还活着的会话和各自的加载时间，让 gyb 挑要不要收（和 `rl feedback accept` 列会话是同一个套路），不自动追、不自动收；收会话走 `rl session end --session ID`。读权不上钩子，所以撤销之后那个会话再读 `notes/` 机器不拦，但撤销时刻之后的读算越权，reviewer 拿 grants 账和决定行的时间戳对着查。

授权只有 gyb 能写：`actor` 必须是 `gyb`。裸终端直接写；角色会话里 `--as-gyb --quote` 替 gyb 写也收，`session_id` 照记那个会话（2026-08-17 gyb 裁，sync-inbox 问题 27，原话「3 不是，可以替我写」；施工计划第一节 (d)「grants 只收裸终端」不认）。

这本账现在只服务一件事：idea 读 `notes/` 的权。`notes/` gyb 和 idea 写（idea 能写是 2026-08-18 gyb 裁，定义处 `06`），谁都能读这条不成立——idea 要经 gyb 允许才有读文献的权限。两条路：`rl init` 的时候问 gyb 一次要不要当场给 idea 发 `read:notes`，发了就不再走申请；没发的话 idea 开一条 issue 给 gyb（kind 是 `request`），gyb 写一条 grant，idea 之后才读 `notes/`。

读权不上钩子。grant 是给 reviewer 事后查的凭据。doctor 有一项扫描接住这条纪律：决定的来源指向 `notes/` 但 grants 里查不到这个 actor 的 `read:notes`。

## 和别的 part 的接口

这一份是定义处的东西：`common/` 五个文件各写什么（含 `SPEC-TEMPLATE.md` 五栏是哪五栏、`REVIEW-CHECKLIST.md` 这个名字）、公共规矩八条全文与「编号不变」、`rules_version` 的样子和生效时刻、feedback 账的行格式与五条命令、issues 账的行格式与九种 kind 与 reply/close 写权、grants 账的行格式与写入限制与撤销之后的处置。别处引用这些的时候指到这一份。下面是本份引别处、或与别处写了两遍的：

- 九本账的公共骨架七样（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`）和两个可选栏 `force_reason`、`via`（`fix_for` 2026-08-17 按 sync-inbox 问题 15 删）：`03-ledgers.md`。issues、grants、feedback 三本的行格式在 `03` 和本份写了两遍（HANDOFF 四点五节判断规矩 2），改一处必改另一处；issues 九种 kind 的定义处是本份，`04`、`06`、`10`、`21` 到 `24` 指到 `03` 的按同一份内容读。
- 「closed 会话再写账拒收」的入账校验：`03-ledgers.md` 账本的总规矩。
- `rl inbox` 五类里的两类归这一份（本角色名下 open 的 issue、本角色提的 feedback 的裁决），命令本身在 `05-rl-cli.md`。
- `rl status` 段 2（assignee 是 gyb 的 open issue）、段 8（等裁的 feedback）、段 10（上次 doctor 没修的）：`01-gyb.md`。
- `rl notify` 的推送表（issue assignee 变 gyb、feedback 提出两条归这一份）：`01-gyb.md` 第五节（2026-08-17 gyb 裁，推送表和 `rl notify` 是一件事归 `01`）。
- gyb 的身份规矩（裸终端就是 gyb、`--as-gyb` 加 `--quote`、`--force --reason`、豁免范围、grants 只有 gyb 能写）：`01-gyb.md`；命令行写法在 `05-rl-cli.md`；钩子那一层在 `06-hooks-and-permissions.md`。
- `bin/rl` 每条子命令的签名和「谁能调」：`05-rl-cli.md`。本份抄了 `rl feedback` 五条、`rl issue` 七条、`rl grant` 四条的签名（写了两遍，改一处必改另一处）。2026-08-18 本份裁的三处要 `05` 跟着改：`rl decision retire` 带理由；`rl feedback accept` 把 `rules_version` 写回母版头部那一行；`rl grant revoke` 列出 grantee 还活着的会话。
- `rl decision retire` 带理由之后决定行上记理由的那一栏：`02-decisions.md`（决定账的定义处；栏名归 `02` 定，是新加一栏还是复用 `force_reason` 归 `02`）。
- doctor 的全部扫描项，其中和这一份有关的五项（answered 超期未 close、没人指回的 open issue、单子回 todo 而 issue 还 open、feedback 的 `applied_to` 为空、决定来源指 `notes/` 但没有 `read:notes`）：`05-rl-cli.md`。doctor 只留脚本能判的项，判断类的进 `common/REVIEW-CHECKLIST.md`。
- sessions 账的 `rules_version`（开始版从 `common/GLOBAL-RULES.md` 头部那一行读）、`last_activity`、`status` 与「还活着的会话」怎么判定、`rl session end`：`04-handoffs-and-sessions.md`。
- `rl handoff accept` 自动关 `answered` issue、转移表 `in_progress` 到 `stuck` 那一行要求 issue 与单子互相引用、`rl handoff withdraw --reason [--quote]`：`04-handoffs-and-sessions.md`。
- 角色 json 的 `reads`、`writes`、`ledger_writes`、`dispatches_to`、`model` 五栏（run 的 `reads` 2026-08-18 补 feedback）、钩子的三层分权、`tests/test_skill_refs.py` 查三样、角色 json 改动同母版流程：`06-hooks-and-permissions.md`。
- 五份角色 SKILL.md 按 `common/SPEC-TEMPLATE.md` 五栏写、各自的 use case 表和模型：`10-role-idea.md` 到 `14-role-reviewer.md`；json 副本也在那五份，要跟 `06` 一字不差。
- 三条阈值 `issues.gyb_stale_hours`、`issues.answered_stale_days`、`notify.reminder_days` 写在 `research-loop.json` 里、插件树 `common/` 那一行：`08-trees-init-and-host.md`。
- `rl init` 问一次要不要给 idea 发 `read:notes`：`08-trees-init-and-host.md`。
- idea 申请读 `notes/` 的那条 `request` issue 怎么走：`10-role-idea.md`；gyb 那一头怎么批：`01-gyb.md`。
- run 的四种失败各配哪个 kind 和 stage、smoke 日志落哪：`12-role-run.md` 与 `21-pair-deploy-run.md`。
- reviewer 不开 issue、只写 `review/` 清单、按 `common/REVIEW-CHECKLIST.md` 派 sonnet subagent 一人一题（不算派活，sync-inbox 问题 33）、清单一条问题五栏：`14-role-reviewer.md` 与 `25-pair-reviewer-idea.md`。
- 快车道的杂账 scratch 与 `ql open/close`：`07-quick-lane.md`。
- 施工步 5（母版五个文件）、步 6（五份 SKILL.md）、测试 13（引用检查三样）、测试 17（feedback）、待验证第 11 条（改母版要不要重启）：`30-build-steps-verify-tests.md`。

## 源文档没写清的（留给 gyb）

（原来的十条：第 5、8 条 2026-08-17 随 sync-inbox 问题 26、23 裁，其余八条加第一节表里问题清单文件名一处 2026-08-18 全部裁完，逐条见文末「裁决记录（日期）」，正文已按裁决改。）

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

下面的条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，保留场景名、序号、严重度、kind、原文、依据、改法，不做判断、不改字。那份文件开头写明：17 个核实者和 critic 全部因为月度用量上限没跑成，所以这些摩擦是未经核实的模拟者原话，可能有误报。

### param-tweak（45 步，gyb 动手 8 次）

17. [cosmetic/contradiction] 第 4 步：设计文档说 SKILL.md 正文出现的每条 rl 子命令都要在角色 json 的 ledger_writes 里，施工计划的测试 13 只查写命令；deploy 上线要跑的 rl decision stale、rl handoff show 都是查询命令，不在 deploy 的 ledger_writes 里，按设计文档那句机器检查就红
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:215; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：把设计文档那一句改成「每条 rl 写命令」，或角色 json 加一栏 queries 单列查询命令

### new-idea（39 步，gyb 动手 7 次）

11. [slows/missing] 第 15 步：new1 的探针代码没搬进 experiments/，deploy 改的是仓库根的宿主代码，插件只写了钩子放行加「列进报告并留决定」；宿主仓库 CLAUDE.md 要求扩展流水线必须从 probe-pipeline skill 进、代码与 run.py 注册表同一个 commit，两套规矩没有对接句，deploy 会绕过宿主的注册表
   - 依据：plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:132; plans/2026-08-16-research-loop-build-plan.md:10
   - 改法：deploy 的 SKILL.md 加一句「改 experiments/ 外的宿主文件时按宿主仓库 CLAUDE.md 的规矩走，new1 是 probe-pipeline 加 run.py 注册表」

12. [slows/ambiguous] 第 37 步：「拿到数字给 gyb 看」两种读法都成立：idea 读九本账全部，可以直接 rl run show 把 metrics 念给 gyb；可另一处写着任何角色不许自己写新的要分析的东西、要看什么 gyb 一条条说由 analysis 记账批准，照抄一个原始指标算不算分析没有界
   - 依据：plans/2026-08-16-research-loop-next-steps.md:52; plans/2026-08-16-research-loop-next-steps.md:30; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：明写「照抄 runs 账 metrics 里的原始数不算分析，任何对比、聚合、画图都要走口径账」

### result-wrong-review（25 步，gyb 动手 11 次）

3. [blocks/contradiction] 第 16 步：设计文档说 reviewer「不开 issue、不派活」，施工计划第十三节公共规矩第 6 条说「analysis 和 reviewer 不在楼梯上，卡住直接开 issue 给出问题的角色」，两句直接打架；而且 reviewer 的角色 json 里 ledger_writes 只有 decisions.reviewer 和 feedback add，没有 issues，真按规矩 6 开 issue 会被入账校验退出码 3，reviewer 中途读不到产物时按文档无路可走。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-build-plan.md:250; plans/2026-08-16-research-loop-build-plan.md:109
   - 改法：规矩 6 里把 reviewer 摘出来，明写 reviewer 只写 review/ 清单、卡住也只写进清单交给 gyb。

4. [slows/contradiction] 第 9 步、第 10 步、第 13 步（reviewer 全程只调查询命令）：设计文档说机器检查是「SKILL.md 正文出现的每条 rl 子命令都要在这个角色 json 的 ledger_writes 里」，施工计划的 test_skill_refs 只要求写命令在 ledger_writes 里；reviewer 的 SKILL.md 必然写到 rl decision stale、rl decision show、rl run show、rl handoff show 这些读命令，按设计文档那句检查必挂。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：把设计文档第 40 行改成「写命令进 ledger_writes、读命令进 reads」，和测试 13 对齐。

### next-plan-after-results（36 步，gyb 动手 16 次）

12. [cosmetic/ambiguous] 第 12 步：派生量口径 approve 时 code_path 必须已存在，可公共规矩 5 又说派生量只用 approved 的口径；analysis 到底能不能为一条还没批的口径先写代码，两种读法都说得通
   - 依据：2026-08-16-research-loop-build-plan.md:69; 2026-08-16-research-loop-build-plan.md:249
   - 改法：规矩 5 补一句「写代码不算算数，出数才要 approved 口径」

### run-crash-midway（40 步，gyb 动手 4 次）

9. [slows/missing] 第 38、39 步：issue 从 answered 到 closed 谁打、什么时候打没写。run 的 ledger_writes 只有 issue open（build-plan.md:105），deploy 和 idea 都有 close（:101、:103）但没规定何时用；`rl status` 七段（:142）只列改派给 gyb 超时的 issue，`rl doctor` 八项（:144）也不扫 answered 未 close 的 issue。结果是每次崩溃都留一条挂着的 issue，只有 gyb 偶然翻到才收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl handoff accept` 时自动 close 掉这张单子关联的 answered issue，doctor 补一项「answered 超过 N 天没 close」。

13. [slows/guessed] 第 9 步：跑挂该开哪种 kind 的 issue，只能猜。build-plan.md:45 的六种 kind 是 cannot / not_mine / denied / anomaly / request / withdrawn，没有一种对应「跑挂」；build-plan.md:166 给的命令模板直接写成 `rl issue open --to deploy --kind ...` 把 kind 留空；next-steps.md:72 列了四种要开 issue 的情形（smoke 失败、发射失败、跑挂、结果反常）但只给结果反常指定了 anomaly。本 trace 取 cannot 是猜的，四种情形挤进一个 kind 之后 `rl issue list` 没法按失败类型筛。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：给 run 的四种失败各定一个 kind（smoke_failed / launch_failed / crashed / anomaly），写进第二节词表。

### n-launch-orders（58 步，gyb 动手 10 次）

9. [cosmetic/missing] 第 24 步：run 出问题的四种情况里，只有「结果反常」在 issue 的六种 kind 里有对应值（anomaly），smoke 失败、发射失败、跑挂三种该填哪个 kind 没写，施工计划第七节那一句直接写成 `--kind ...`。这里只能挑了 cannot。
   - 依据：2026-08-16-research-loop-build-plan.md:45; 2026-08-16-research-loop-build-plan.md:166; 2026-08-16-research-loop-next-steps.md:72
   - 改法：issue 的 kind 加一个 failed（或把三种失败明写成一律用 cannot），并在 run 的 SKILL.md 里一种失败对一个 kind 列成表。

15. [slows/ambiguous] 第 48 步：跨 run 的聚合数算谁的活，两种读法都说得通。一种读法：idea 读九本账全部，runs 账的 metrics 就在里面，自己把 5 个数平均一下没人拦。另一种读法：规矩 5 说派生量只用 approved 的口径、由 analysis 算，均值方差正是派生量，idea 自己算就是自作主张。
   - 依据：2026-08-16-research-loop-next-steps.md:52; 2026-08-16-research-loop-next-steps.md:30; 2026-08-16-research-loop-build-plan.md:249
   - 改法：明写一句：单个 run 的 metrics idea 可以直接引，任何跨 run 的聚合一律走 analysis 分析单。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

10. [slows/missing] 第 10 步：公共规矩第 1 条（build-plan.md:245）要求不可逆动作要有 gyb 当场的原话，收回是终态、不可逆，可是 `rl handoff withdraw ID [--cascade]`（build-plan.md:134）没有 `--quote` 参数，handoffs 行格式（build-plan.md:61）也没有 quote 字段，gyb 那句「停」没有落点。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:245; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：withdraw 和 reject 都加 `--quote`，handoffs 行加 quote 字段，角色会话发起时缺 quote 就报错。

13. [slows/missing] 第 20 步：rl 自动开的 `kind=withdrawn` issue 的 assignee 是角色不是会话（build-plan.md:59），run 的 subagent 收到信号后就结束了，这条 issue 没人回也没人关。doctor 的扫描项里只有「没人引用的 issue」（build-plan.md:144），这条带着 handoff_id 所以扫不出来，会一直挂在 `rl status` 的 open 列表里。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：withdraw 自动开的 issue 直接落成 `closed`（它是通知不是问题），或者 doctor 加一条「holder 已销号但 withdrawn issue 仍 open」的扫描并附 close 命令。

### feedback-round（15 步，gyb 动手 9 次）

1. [blocks/principle_violation] 第 3、6 步（feedback 落账之后没人叫 gyb）：违反八条原则第 6 条「所有等 gyb 处理的事一处汇总」：feedback 的 proposed 版既不进 rl status 的七段，也不触发通知（通知只给 issue 改派到 gyb 那一版），gyb 唯一的兜底是七天一次的定时提醒 notify.reminder_days，一条规矩改动最坏挂七天
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:183
   - 改法：rl status 加第八段「等 gyb 裁的 feedback」，并让 rl feedback add 走 issue 那条通知通道发一次桌面通知

2. [blocks/principle_violation] 第 7 步（gyb 查 feedback）与第 13 步（deploy 想知道裁决结果）：违反第 6 条「进出对称」和第 5 条「权限从动作倒推」：deploy、run、analysis 三份角色 json 的 ledger_writes 都有 feedback add，reads 里都没有 feedback；命令表也只有 feedback list 没有 feedback show。提反馈的角色写得进去、查不出来，自己提的那条被采纳还是被否只能靠 gyb 口头说
   - 依据：plans/2026-08-16-research-loop-build-plan.md:103; plans/2026-08-16-research-loop-build-plan.md:105; plans/2026-08-16-research-loop-build-plan.md:107; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-next-steps.md:94
   - 改法：五份角色 json 的 reads 一律加 feedback，命令表补 `rl feedback show ID`

3. [slows/contradiction] 第 4 步（deploy 提完 feedback 之后接着干还是停）：公共规矩第 7 条写「提到 feedback 等 gyb 裁」，设计文档 feedback 那一条写「母版改动在下次加载角色时生效，正在跑的会话不追」；前一句读成停下来等裁决，后一句读成照旧按现行母版干到底，两种读法都说得通
   - 依据：plans/2026-08-16-research-loop-build-plan.md:251; plans/2026-08-16-research-loop-next-steps.md:101
   - 改法：规矩第 7 条改成「提完继续按现行母版干，不等裁决；裁决只对下次加载的会话生效」

4. [slows/contradiction] 第 11 步（rl feedback accept 填 applied_to）：applied_to 的口径是「改了母版哪个文件」，单值；但按原则 8「后裁的赢、要回来把正文那一行改掉、不留两个值」，一条采纳的规矩至少要同时改母版 common/GLOBAL-RULES.md 和施工计划第十三节那一行，单值记不下第二处，doctor 也没有一条扫描去查第二处漏没漏
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-next-steps.md:22; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：applied_to 改成路径列表，rl doctor 加一条「accepted 的 feedback 的 applied_to 没同时含母版和设计或施工文档」

5. [slows/missing] 第 12 步（正在跑的 analysis 会话和 idea 会话怎么办）：母版改了以后，正在跑的会话按旧规矩产出的东西算不算数（要不要打回、收回、重做）没写；账上也没有任何地方记得住某个会话是在哪一版母版下跑的：sessions 账只有 session_id、role、model、started_at、ended_at、end_reason、open_handoffs_at_end 七样，母版文件本身也没有版本号
   - 依据：plans/2026-08-16-research-loop-next-steps.md:101; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：母版文件加一个 rules_version，sessions 开始版记下它，accept 时 rl 顺带列出还活着的会话和它们的 rules_version 让 gyb 挑要不要收

6. [slows/missing] 第 12、13 步（想主动通知正在跑的会话）：文档给的答案是不通知、下次加载才生效，但 gyb 万一想立刻让人知道，系统里没有通道：issue 的 assignee 是角色不是会话、六种 kind 里没有「规矩变了」这一类，feedback 账根本没有 assignee，桌面通知只发给 gyb
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:101
   - 改法：要么在 feedback 那一条明写「采纳只对下次加载生效，不给正在跑的会话补通知」，要么给 issue 加 kind=rule_change 并允许 assignee 填 session_id

7. [slows/missing] 第 14 步（下次加载角色时生效）：「母版改动在下次加载角色时生效」是这个场景的最终答案，可是第九节九条待验证清单里没有它：改一行 common/ 之后，同一个 claude 进程里再加载一次角色 skill 读到的是新文本还是缓存的旧文本，没人测过
   - 依据：plans/2026-08-16-research-loop-next-steps.md:101; plans/2026-08-16-research-loop-build-plan.md:187; plans/2026-08-16-research-loop-build-plan.md:196
   - 改法：待验证清单加第 10 条：改一行母版，不重启 claude 再加载一次角色，看模型读到的是不是新文本，失败备案是改完母版必须重开终端

8. [slows/missing] 第 10 步（gyb 自己 grep 五份 SKILL.md）：母版 common/ 和五份角色 SKILL.md 是引用关系还是抄一份，文档没写；施工步 5 和步 6 是两步分别写的两组文件。抄了的话改母版根本不生效，gyb 只能自己去 grep 五份 SKILL.md 有没有重复条文
   - 依据：plans/2026-08-16-research-loop-next-steps.md:150; plans/2026-08-16-research-loop-build-plan.md:232; plans/2026-08-16-research-loop-build-plan.md:233; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：定死 SKILL.md 只写一句「按 common/GLOBAL-RULES.md 执行」、不许抄条文，测试 13 加一条查 SKILL.md 里有没有母版条文的副本

9. [cosmetic/ambiguous] 第 2 步（feedback 的 target 填什么）：target 的口径是「文件路径或规矩编号」，可母版里公共规矩八条编号 1 到 8、八条设计原则也编号 1 到 8，两套都在同一个文件里，`--target 6` 指的是规矩 6 还是原则 6 分不出来
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:245; plans/2026-08-16-research-loop-build-plan.md:252; plans/2026-08-16-research-loop-next-steps.md:13
   - 改法：规矩和原则各给一套带前缀的稳定编号（rule-06、principle-06），target 只收文件路径或这两种编号

10. [cosmetic/ambiguous] 第 8、11 步（先改文件还是先 accept）：accept 那一版要求 applied_to 必填「改了母版哪个文件」，但没写是先把母版改完再 accept 还是先 accept 再去改，入账校验也没说要不要检查这个路径存在、检查改没改
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:139
   - 改法：命令表写死「accept 之前先把母版改完，rl 校验 applied_to 的每个路径存在」

11. [slows/missing] 第 5、13 步（deploy 和 gyb 之间的口头传话）：这条路能走通全靠 deploy 是 gyb 手动加载的终端会话、两头能说话。deploy 要是 subagent（上游同步等着它回来），它提了 feedback 没人告诉 gyb，gyb 裁完也没法把话递回去，整条路断在这儿
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:139
   - 改法：rl feedback add 在 actor 是 subagent 会话时顺带开一条 kind=request 的 issue 给 gyb，借已有的通知和 status 通道

12. [slows/too_heavy] 整条路（gyb 亲手做九件事）：改一条规矩要 gyb 亲自做九个动作（status、feedback list、改母版、改施工计划、grep 五份 skill、accept、判断要不要收会话、告诉 deploy、commit），系统只帮他记一行账，剩下八件全靠他自己记得住；这跟「想法要快速、多次迭代」的目标不匹配
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-build-plan.md:67
   - 改法：rl feedback accept 收多个 applied_to 并当场打印一张待办（还要改哪几处、活着的会话要不要收、要不要 commit 和跑测试）

13. [slows/principle_violation] 第 11 步的另一条走法（gyb 就坐在 deploy 会话里裁）：违反第 1 条「gyb 是超级用户，任何权限检查对 gyb 不生效」：角色会话里用 --as-gyb 缺 --quote 一律退出码 2（测试 9 钉死了这条），可 rl 分不出打字的是 gyb 本人还是模型，gyb 亲自在 deploy 会话里裁 feedback 会被自己的校验拦下来，得先换个裸终端
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:211; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-next-steps.md:34
   - 改法：给一个 gyb 本人当场打字的旗子（比如 --i-am-gyb）免 quote，或者把缺 quote 从拒收降成账行打一个「无原话」的标记

14. [cosmetic/missing] 第 15 步（改完母版要不要 commit、要不要跑测试）：第十一节的「每一步施工结束 tests/run_all.py 全绿才 commit」和 commit 前缀 research-loop v2: 只管施工那八步，用起来之后运行期改母版要不要单独 commit、要不要重跑测试 13，没写
   - 依据：plans/2026-08-16-research-loop-build-plan.md:219; plans/2026-08-16-research-loop-build-plan.md:237; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：feedback 那一节补一句：accept 之后母版改动单独一个 commit，前缀 research-loop rules:，并跑一遍 tests/run_all.py

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

6. [slows/too_heavy] 第 6 步到第 11 步整段：gyb 就坐在这个会话里说了句「你去读吧」，为了读一份 md 却要走 issue open、通知、grant add、issue reply、issue close 五个动作四行账。permission 第一版只有 read:notes 一种、grantee 是角色不是会话，所以批一次就永久覆盖整个 notes/，这套手续一辈子只有第一次有信息量，和「想法要快速、多次迭代」这条总目标对不上
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-build-plan.md:65
   - 改法：`rl init` 时问一次 gyb 要不要当场给 idea 发 read:notes，发了以后就不用走申请，没发才走 issue 那条路

8. [slows/missing] 第 12 步：读权不上钩子、靠纪律加 reviewer 事后查，但文档没写 reviewer 拿什么查「idea 有没有在没 grant 的时候就读了 notes/」。系统里没有读日志，doctor 的八项扫描里也没有这一类，这条纪律实际上无从核对
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:136; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl doctor` 加一项扫描「decisions 里 source 指向 notes/ 但 grants 里查不到该 actor 的 read:notes」，把这条纪律接回入账校验那一层

10. [cosmetic/missing] 第 10 步和第 11 步：issues 三个状态的写权只有一句「按第五节 ledger_writes」，谁写 reply、谁写 close 没规定；idea 的 ledger_writes 含 issues 的 open/reply/reassign/close 四个，所以 idea 自己开、自己答、自己关全过校验，和派活单那张写得很死的转移表不对称
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:79
   - 改法：第六节 issue 那一行加前提栏：reply 只有 assignee 或 gyb 能写，close 只有开单的 actor 或 gyb 能写

### periodic-reclaim（27 步，gyb 动手 11 次）

17. [cosmetic/missing] 第 25 步：提醒里的第三件事「迭代框架本身」没写具体做什么、产出落到哪本账、改完的母版要不要 commit。feedback 账那条线写清楚了，这一条只有名字。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:183; plans/2026-08-16-research-loop-build-plan.md:139
   - 改法：把这一条改写成「跑 rl feedback list，把 accepted 的改动落到 common/ 母版并单独 commit」，不留抽象说法。

### hook-missed-session-end（23 步，gyb 动手 11 次）

9. [slows/missing] 步 6、步 22：整个恢复过程在九本账上不留痕，违反原则 4 的事件流本意（设计 L18）。release 那一版只记 status 和 holder 清空；issue 的六种 kind（施工 L45）没有一种对得上「你的 holder 会话死了、单子被交回」；reclaim 关掉死会话时 open_handoffs_at_end（施工 L71）已经是空的，因为单子先被 release 了。事后谁都看不出钩子漏过一次。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:18; plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：issue 的 kind 加一种 orphaned，release 和 reclaim 交回单子时自动开一条给 owner，把当时的 holder 会话 id 写进去。

### smoke-fails（44 步，gyb 动手 4 次）

8. [slows/ambiguous] 步 19（run 开 issue）：smoke 失败该填哪个 kind 没定。六种 kind 里 cannot（干不了）和 not_mine（不归我干）两种读法都说得通：ImportError 是代码问题、明显不归 run 干，但 run 的确也是干不了。施工计划第七节只写「一律 rl issue open --to deploy --kind ...」，省略号没填。kind 影响 doctor 和 status 的归类，也影响 gyb 读账时的判断。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：在第七节把四种失败各钉一个 kind：smoke 失败、发射失败、跑挂都是 cannot，结果反常是 anomaly。

11. [slows/principle_violation] 步 43（gyb 跑 rl status 收尾看一眼）：违反原则 6 的「进出对称」那一半。run 开给 deploy 的 issue 不触发通知（只有改派到 gyb 名下才通知），rl status 的七段里只有「改派给 gyb 超过阈值的 issue」，没有「open 的 issue 按 assignee 分组」这一段。这条 iss-0031 从 open 到 answered 之后没人 close，账上也没有任何出口能把它列出来；单子本身能在「没到终态的单子」里露头，issue 露不了头。deploy 会话要是先走了，这条 issue 就悬着，只能靠 reclaim 捞单子，issue 永远 open。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:143
   - 改法：rl status 加一段「open 与 answered 的 issue 按 assignee 分组」，reclaim 一并列出超过阈值没动的 issue。

12. [cosmetic/missing] 步 26 与步 43（iss-0031 的收场）：issue 有 open、answered、closed 三个状态，命令表也有 rl issue close，但谁来 close、什么时候 close 全文没写。这次 deploy 回复之后 issue 停在 answered 就再没人碰过，doctor 只扫「没人引用的 issue」，扫不出这种长期 answered 不 closed 的。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：rl handoff accept 时自动 close 这张单关联的所有 answered issue，剩下的由开单角色手动 close。

### doctor-findings-fix（24 步，gyb 动手 15 次）

4. [slows/ambiguous] 第 3、4 步（判定第一类是什么）：「没人引用的 issue」没有定义什么叫被引用。按现有字段只有 handoff.issue_id 和 grant.issue_id 会指回 issue，而 handoff 的 issue_id 只在 stuck 那一版必填，于是 withdraw 自动开的 kind=withdrawn issue、run finish 开的 kind=anomaly issue、idea 的 kind=request issue 天生就没人引用，doctor 会把这些正常的行当问题报。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:59; 2026-08-16-research-loop-build-plan.md:92
   - 改法：把这一项收窄成「kind 是 cannot 或 denied、status 是 open、且没有任何 handoff 的 issue_id 指回来的 issue」，其余 kind 一律不扫。

5. [slows/blocked] 第 6 步（补 stuck 那一版）：`rl handoff stuck` 的前提是「那条 issue 的 handoff_id 指回本单」，但 `rl issue open` 的 `--handoff` 是可选参数；崩在写序中途的那条 issue 如果当初没带 --handoff，这条前提永远满足不了，而 issues 的命令只有 reassign/reply/close，没有补 handoff_id 的路，第一类同样修不了。
   - 依据：2026-08-16-research-loop-build-plan.md:84; 2026-08-16-research-loop-build-plan.md:132; 2026-08-16-research-loop-build-plan.md:59
   - 改法：要么把 `--handoff` 在 kind 是 cannot/denied/withdrawn 时改成必填，要么加一条 `rl issue link ID --handoff ID`（追加一版只补这个字段）。

13. [cosmetic/missing] 第 1 步（谁跑 doctor、跑完能不能自己修）：doctor 写的是「谁都行」，但角色会话跑出问题之后能不能自己修没写。deploy 看到自己名下那张 done_pending_review 的报告路径没了，它是 to_role 不是 owner，按转移表打回只有 owner 能写，它只能开 issue，文档没说这一步该开给谁、kind 填哪个。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:45
   - 改法：在 doctor 那一行写一句「角色跑 doctor 只看不修，修法一律 `rl issue open --to <owner> --kind cannot` 报给 owner 或 gyb」。

## 裁决记录（日期）

- 2026-08-17：来自 `03-ledgers.md` 的裁决（gyb：「都必填」），feedback 的 `verdict_text` 在 `accepted` 和 `rejected` 两版都必填；第五节行格式那句照 03 字段表补齐。统筹 session 同步。
- 2026-08-17 gyb 裁（sync-inbox 问题 2，原话「算一件事」「给rl notify指到01吧」，rl-hub 转来）：推送表和 `rl notify` 是一件事，定义处归 `01-gyb.md` 第五节；`05-rl-cli.md` 命令表只留 `rl notify --text` 的签名行，「rl notify」一节缩成一句指 `01`。接口一节的指向照改。
- 2026-08-17 来自 `05-rl-cli.md` 定稿（`656c8a9`）的裁决（rl-hub 转来；gyb 原话「全推荐」「只要他不动目前的代码什么的就全推荐就行」「全都推荐，只要不影响正在跑的进程」「A」）：`common/` 加一份判断类检查的问题清单文件（名字归本份定），reviewer 按它派 sonnet subagent 逐题查。对回原则 2、5。第一节的表加一行，四个文件改成五个。（2026-08-17 问题 6 后改：查出的只写 `review/` 清单，不开 issue，gyb 看完用自己的权限开。）
- 2026-08-17 来自 sync-inbox 问题 6 的裁决（定义处 `14`，rl-hub-v3 传；gyb 原话「全给我审查，然后我用我的权限放到issue里面」）：reviewer 查出的只写 `review/` 清单，不开 issue，gyb 看完用自己的权限开。第一节表里问题清单那行照 `05` doctor 一节末段补「查出来的写进 `review/` 清单，要不要开 issue 由 gyb 看完用自己的权限开」；上一条裁决记录标「后改」。
- 2026-08-17 来自 sync-inbox 问题 15 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「B」）：`fix_for` 栏删掉，可选栏是 `force_reason`、`via` 两个。接口一节第一条照改。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「只有做完了的时候才关，巡检要我本人确认」）：`rl inbox` 只读不关，通知类 issue 由收件人做完了自己 `rl issue close`。第六节写权三条里的「`rl inbox` 关读到的通知类 issue」删掉，`close` 那条照 `03` 补「通知类 issue（`withdrawn`、`orphaned`、`fyi`）的 `assignee` 也能关」；「没写清」第 8 条标已裁。
- 2026-08-17 来自 sync-inbox 问题 26 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「我觉得。有一些改的方法，不一定会改公共规矩，如果是这样的话就选b。」）：`applied_to` 至少写一个即可。第五节行格式那句补「至少写一个」，下一句照 `03` 一字不差改写，doctor 那一项改成「`applied_to` 为空」；接口一节 doctor 五项那条同改；「没写清」第 5 条标已裁。
- 2026-08-17 来自 sync-inbox 问题 27 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「3 不是，可以替我写」）：grants 在角色会话里 `--as-gyb --quote` 替 gyb 写也收。第七节开头「只有 gyb 在裸终端能写」改成「只有 gyb 能写」，行格式末句的「`session_id` 必须是 `cli`」改成「裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收，`session_id` 照记那个会话」，「grants 只收裸终端写的行……不接受 `--as-gyb`」那段照 `03` grants 段一字不差换掉。
- 2026-08-18 来自 `00-overview.md` 定稿（`6ea0edc`，rl-hub-v4 传；gyb 原话「所有的东西都默认用英语，插件本体里面用英语写，然后不要出现语言相关的约束，就默认只有英语就可以了，不需要强调任何语言」）：第二节施工步 5 那句「中文底稿给 gyb 过，正式版是英文」去掉语言字样；「没写清」第 2 条英文措辞那一半销掉，只留 `rule-NN` 编号保持不变一句。
- 2026-08-18 来自 `06-hooks-and-permissions.md` 定稿（`d430192`，rl-hub-v4 传；gyb 原话「a」（问题十一、九）「6 c」「让idea能写gyb」）：rule-08 补 Bash 绕钩子那半句；八条之后加一句不占编号的纪律「一个会话只加载一个角色」；第四节补「角色 json 改动同母版流程」；第七节「`notes/` 只有 gyb 写」改「gyb 和 idea 写」。对回原则 2、9、3。
- 2026-08-18 gyb 裁（问题 1，原话「a」）：`common/SPEC-TEMPLATE.md` 的五栏就是 8 月 15 日 `redesign.md` 里定的角色定义五栏——角色设定、使用场景、可用工具、限制条件、输出样式，是每份角色 SKILL.md 的骨架；「可用工具」一栏只指到角色 json、不抄；和 reviewer 清单「一条问题五栏」是两份东西。对回原则 5、8。第一节表和第二节照改。
- 2026-08-18 gyb 裁（问题 2，原话「a」）：`rule-NN`、`principle-NN` 编号一经定下不再变——废掉留空号不补位、新加往后排、改内容不换号。对回原则 8、4。第三节加一段。
- 2026-08-18 gyb 裁（问题 3，原话「a」）：`rl decision retire` 必须带理由，谁废都要，理由记进那一版决定行；角色会话里替 gyb 废除的原话按 `--as-gyb --quote` 既有规矩带，不另加。对回原则 1、8。第三节 rule-01 之后加一段；命令签名归 `05`、行上那一栏归 `02`，列进「要同步到别处的」。
- 2026-08-18 gyb 裁（问题 4，原话「a」）：feedback 的 `target` 只认两种——文件路径、带前缀编号；表的某一行填那张表所在文件的路径，哪一行写进 `text`。对回原则 4、6。第五节行格式照改。
- 2026-08-18 gyb 裁（问题 5，原话「a」）：`rejected` 是终态，要再提就开新一条、`text` 说明接着哪条，rl 不建链，不加改一版的子命令。对回原则 4。第五节行格式照改。
- 2026-08-18 gyb 裁（问题 6，原话「a」）：run 的角色 json `reads` 补 feedback，和另外四个角色一样。对回原则 5、6。第五节末句照改；定义处 `06`、副本 `12`，列进「要同步到别处的」。
- 2026-08-18 gyb 裁（问题 7，原话「a」）：`rules_version` 是整数、从 1 起、写在 `common/GLOBAL-RULES.md` 头部一行，这一行是唯一真源；`rl feedback accept` 自动加一并写回那一行，母版正文仍人手改，rl 只动这一行；会话开始版从这一行读。对回原则 8。第一节表、第四节、第五节 accept 四件事照改；`05` 的 accept 描述、`04` 的开始版来源列进「要同步到别处的」。
- 2026-08-18 gyb 裁（问题 8，原话「a」）：`rl grant revoke` 时列出 grantee 还活着的会话和加载时间，gyb 挑要不要收，不自动追不自动收；撤销时刻之后再读算越权，reviewer 按时间戳查。对回原则 1、2、6。第七节加一段；`05` revoke 一节、`03` grants 段列进「要同步到别处的」。
- 2026-08-18 gyb 裁（问题 9，原话「a」）：判断类检查问题清单的文件名定为 `common/REVIEW-CHECKLIST.md`。第一节表照改；`05` doctor 末段、`08` 插件树、`14`、`30` 步 5 列进「要同步到别处的」。
- 2026-08-18 定稿时的编辑性改动（不是新裁决）：开头覆盖句「`common/` 四个文件」改「五个文件」，与第一节标题和 2026-08-17 加的第五行对齐；「源文档没写清的」一节收成一句。

## 要同步到别处的

下面这些是 2026-08-18 定稿时牵连别的 part 的，这边只列不改，SendMessage 报给 rl-hub-v5 并追加到 `sync-inbox.md`；动到 `03`/`04`/`05` 冻结三份的只报不催，等最后一期。

- `02-decisions.md`：`rl decision retire` 必须带理由（谁废都要），理由记进那一版决定行——行格式上要有记理由的地方，是新加一栏还是复用 `force_reason` 归 `02` 定；角色会话里替 gyb 废除的原话按 `--as-gyb --quote` 既有规矩。
- `05-rl-cli.md`（已冻结，冻结后待议）：三处——`rl decision retire ID [--source ...]` 签名加理由项（必填）；`rl feedback accept` 那句「自动把 `rules_version` 加一」补「并写回 `common/GLOBAL-RULES.md` 头部那一行」；`rl grant revoke` 一节补「列出 grantee 还活着的会话和各自加载时间，让 gyb 挑要不要收，不自动收」。另：doctor 一节末段「判断类检查的问题清单」可带上文件名 `common/REVIEW-CHECKLIST.md`。
- `03-ledgers.md`（已冻结，冻结后待议）：grants 段（与本份写了两遍）加「撤销时刻之后再读算越权，reviewer 按时间戳查；撤销时 rl 列出还活着的会话让 gyb 挑」；feedback 段 `target` 那句加「表的某一行填那张表所在文件的路径，哪一行写进 `text`」、`status` 那句加「`rejected` 是终态，再提开新一条」；`rules_version` 相关字段说明可注「整数」。
- `04-handoffs-and-sessions.md`（已冻结，冻结后待议）：sessions 账开始版 `rules_version` 补「从 `common/GLOBAL-RULES.md` 头部那一行读」；`rl grant revoke` 列会话之后收会话走 `rl session end`（只是引用，那边若有「谁会调 session end」的清单可加一条）。
- `06-hooks-and-permissions.md`：run 那张 json 表 `reads` 加 feedback（改成「handoffs、issues、runs、feedback、`experiments/`、`ops/gpu_state.md`」）；「五栏是什么」或 `test_skill_refs` 一节可注 SKILL.md 骨架是 `common/SPEC-TEMPLATE.md` 五栏。
- `12-role-run.md`：json 副本 `reads` 同 `06` 加 feedback。
- `10-role-idea.md` 到 `14-role-reviewer.md`：SKILL.md 按 `common/SPEC-TEMPLATE.md` 五栏（角色设定、使用场景、可用工具、限制条件、输出样式）写，「可用工具」栏只指到角色 json；`14` 另把「判断类检查问题清单」带上文件名 `common/REVIEW-CHECKLIST.md`。
- `08-trees-init-and-host.md`：插件树 `common/` 那行「公共规矩、词表、五栏规格、读法，带 `rules_version`」加「判断类检查问题清单 `REVIEW-CHECKLIST.md`」，`rules_version` 可注「整数，头部一行」。
- `30-build-steps-verify-tests.md`：步 5 那行「判断类检查的问题清单（文件名待定……）」改成 `common/REVIEW-CHECKLIST.md`；测试 17（feedback）若列了 `accept` 的动作，加「写回母版头部 `rules_version` 那一行」。
- `00-overview.md`：索引里 `09` 那行「公共母版（公共规矩八条、词表、五栏规格、读法）」可加「判断类检查清单」；不改也不打架。
