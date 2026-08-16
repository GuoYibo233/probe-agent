# 分权三层、钩子、角色 json

> 这份覆盖约束分成的三层（钩子、入账校验、纪律）各管什么、钩子拦哪两类事又放行什么、钩子的回话怎么写、钩子怎么跟角色绑定、没加载角色的裸会话靠 CLAUDE.md 那一节的三句话、角色 json 的五栏定义和五份 json 逐栏的内容、`tests/test_skill_refs.py` 查什么、读的纪律。
> 不覆盖的：九本账每一行的字段和 status 取值写在 `03-ledgers.md`；派活单转移表和会话登记销号的流程写在 `04-handoffs-and-sessions.md`；`rl` 每条子命令的参数、退出码、`rl status` 的十段写在 `05-rl-cli.md`；`--as-gyb` 和 `--quote` 这条规矩本身、gyb 的豁免范围从 gyb 那头看是什么样写在 `01-gyb.md`；公共母版八条规矩、`common/READING.md` 的正文、反馈账写在 `09-common-and-feedback.md`；插件树里 hooks/ 和 monitors/ 摆在哪、init 建什么写在 `08-trees-init-and-host.md`；每个角色的 use case 表和干活流程写在 `10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`、`14-role-reviewer.md`；待验证清单的测法和测试清单写在 `30-build-steps-verify-tests.md`。
> 源：设计文档的「分权与钩子」一节、「五个角色」总段、「两棵树」一节里插件本体那一段、「待验证清单」；施工计划第一节裁决 3、5、6、7、8，第五节（角色 json 与 gyb 的 use case 表），第六节 actor 判定那一段，第七节 run 照 gpu-run 写的钩子那一格，第九节待验证清单，第十节测试 8、9、13，第十三节公共规矩第 8 条。

## 三层约束，各管各的

约束分三层（原则 2）：钩子、入账校验、纪律。三层管的东西不重叠，写规矩的时候要先想清楚这一条落在哪一层。

### 第一层是钩子，硬拦，宽宽的

钩子只挂 Write 和 Edit 两个工具，只按研究仓库内的相对路径判，只拦两类离谱事：写别的角色的目录，直接写 loop/。仓库外的路径一律放行。

这一层是硬的，模型绕不过去。

### 第二层是入账校验，硬的

九本账只能经 `bin/rl`。每本账内部谁能追加哪种行、哪一版哪些字段必填、转移表允许哪些变化，都由入账脚本按施工计划校验，违反的拒收并说明下一步。

gyb 只豁免「谁能调」和「谁能写」两样。完整性校验对 gyb 同样生效：必填字段、路径存在、引用存在这些数据校验不看是谁在写，gyb 要硬写就加 `--force --reason`，rl 照写并把 reason 记进账行（原则 1 推论）。转移表的「前提」一栏就是完整性校验，对 gyb 生效。

退出码分两个：校验拒收是 2，角色无权是 3，两种都把原因写到标准错误，3 还附一条「开 issue 给谁」的命令。退出码的完整表在 `05-rl-cli.md`。

### 第三层是纪律，写在 SKILL.md 里

第三层管的是：读什么、怎么读、Bash 里能写什么、什么时候该开 issue、什么时候该停下来问 gyb。

Bash 写出来的文件钩子不看，宿主发射器的台账、读什么、怎么读，全归这一层。reviewer 事后审的就是这一层。

公共规矩第 8 条把三层的出圈处理写成一句：钩子拦下的，原话告诉模型开哪条 issue；钩子不拦但越出自己 writes 的（宿主文件、Bash 写入），列进报告并留决定并守宿主规矩；读账一律经 rl 查询命令，查询命令谁都能调。八条规矩的正文在 `09-common-and-feedback.md`。

### 读一律不设权

读不上任何一层的硬拦（原则 2 推论）。九本账的查询命令谁都能调，角色 json 的 `reads` 栏是纪律不是门禁。机器检查只查 SKILL.md 里的写命令在不在 `ledger_writes` 里。

## 钩子拦什么、放什么

### 拦两类

一类是写别的角色的目录：

| 目录 | 只有谁能写 |
|---|---|
| `experiments/` | deploy |
| `analysis/` | analysis |
| `review/` | reviewer |
| `notes/` | gyb |

另一类是直接 Write 或 Edit `loop/`。九本账只能经 `bin/rl` 进出，任何角色直接改账本文件一律 deny。

### 放行什么

仓库外的路径一律放行：git worktree、产物根、`/tmp` 都在仓库外。

仓库内其余路径钩子放行：仓库根的 `run.py`、`MAP.md`、`ops/`、docs 之类。这些路径归纪律管，deploy 改到 `experiments/` 外的宿主文件时的三条纪律（列进部署报告带文件的那一份、在 `decisions.deploy.jsonl` 留一条来源指向那个文件、守宿主仓库自己的规矩）写在 `11-role-deploy.md`。

Bash 写出来的文件钩子不看。所以宿主发射器 `run.py launch` 写 `ops/jobs.json`、`ops/runs.jsonl`、`RUNMETA.json` 这些照旧，不算越权。

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

## 钩子跟角色绑定

先有角色才有钩子。钩子写在角色 SKILL.md 的头部，加载角色的那一刻装上，不存在「用钩子去认角色」这回事。

这个机制 2026-08-16 已实测：加载前不拦、加载后拦、拦的时候模型收到钩子写进标准错误的原话。

一个会话只加载一个角色。

### 钩子还干登记和销号

hooks/ 里除了写权钩子，还有登记和销号两个钩子。

登记：加载 skill 把角色分配给会话的那一刻算会话开始，钩子看得见这次加载，自动登记进 sessions 账。开始版由钩子代角色写，`actor` 填角色。`model` 由钩子从钩子输入的 JSON 里取，取不到记 `unknown`。

销号：挂在 SessionEnd 和 SubagentStop 上，不指望模型自觉调结束命令。销号那一刻要做的检查和 release 动作写在 `04-handoffs-and-sessions.md`。

### 会话状态文件

`rl` 判 actor 靠会话状态文件：状态文件由角色 skill 头部钩子在加载时写，路径 `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json`；`rl` 从它读当前角色，读不到状态文件就是裸终端，actor 是 `gyb`，session_id 记 `cli`。

### 钩子脚本本身

hooks/ 是钩子脚本本体：五个角色共用一个脚本、参数报角色名，落不落得下见待验证清单。monitors/ 里只有一个看门狗，只在 run 上线时起，只写自己的状态文件，不写九本账。

和钩子有关的待验证条目有五条，测法和失败备案在 `30-build-steps-verify-tests.md`：Bash 环境里有没有现成的会话 id 变量；skill 头部声明的钩子能不能给命令带参数；monitor 的 `when: "on-skill-invoke:run"` 写法；SessionEnd 和 SubagentStop 在 subagent 结束时触发不触发、会话 id 是不是同一个；subagent 里加载角色 skill 头部钩子装不装得上、写权拦不拦；钩子输入里有没有模型标识。gyb 裁定：讨论全部收口之前一律不测。

## 裸会话靠研究仓库的 CLAUDE.md

没加载角色的裸会话身上没有钩子，什么都能写。这一点不用兜底钩子去堵：`rl init` 往研究仓库的 CLAUDE.md 里追加一节，追加不覆盖，仓库原有的规矩照旧。

这一节的内容是三句：

1. 「没有 gyb 允许，experiments/、analysis/、review/、loop/ 只能在加载了对应角色的会话里改」
2. 「加载了 run 角色的会话以 run 的 SKILL.md 为准，它是 gpu-run 的超集，宿主 GPU 铁律里的『唯一入口』对 run 会话读作 run skill」
3. 「loop/*.jsonl 和 loop/.lock 不算脏树」

第三句连带一处宿主改动：new1 的发射门禁白名单要加这两样，宿主 CLAUDE.md 那一行由 gyb 改。这处改动排在施工步 7，由 gyb 亲手改，见 `08-trees-init-and-host.md`。

裸会话和读权一样靠纪律。「裸会话装兜底钩子」这个提议 gyb 顶回过，换成 init 往 CLAUDE.md 写一句纪律。

## 角色 json：五栏和五份内容

每个角色由两份文件定义：一份 SKILL.md，一份 json。json 里的东西从 SKILL.md 的 use case 表倒推（原则 5）：每个 use case 写清读哪些账和目录、写哪个目录、调哪些 rl 写命令，前四栏是这张表的并集，`model` 另记。五份 json 合起来就是分权表本体，钩子按角色读自己那份。

各角色的 use case 表在各自那一份：`10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`、`14-role-reviewer.md`。

### 五栏是什么

| 栏 | 装什么 | 谁用它 |
|---|---|---|
| `reads` | 读哪些账和目录 | 纪律，不设门禁 |
| `writes` | 能 Write/Edit 的目录 | 钩子用 |
| `ledger_writes` | 能调哪些 rl 写命令 | 入账校验用 |
| `dispatches_to` | 能派活给谁 | — |
| `model` | `as_subagent` 和 `manual` 两个取值 | 登记会话时用 |

`model` 这一栏的 `manual` 写 `inherit` 是声明跟当前会话走，sessions 账落解析后的真实模型名或 `unknown`。

所有角色上线第一个动作都是 `rl inbox`。查询命令（show、list、trace、status、inbox、stale、doctor）谁都能调，不进 `ledger_writes`。

### 五份 json

idea：

| 栏 | 值 |
|---|---|
| `reads` | 九本账全部、`notes/`（要 grant）、`analysis/`、`experiments/` 下的部署报告目录、`review/` |
| `writes` | 无目录 |
| `ledger_writes` | decisions.idea 全部、handoffs 的 open/accept/reject/withdraw/release/reissue/resume/amend、issues 的 open/reply/reassign/close、feedback add |
| `dispatches_to` | deploy、analysis |
| `model` | `as_subagent` 是 fable，`manual` 是 inherit |

deploy：

| 栏 | 值 |
|---|---|
| `reads` | `decisions.idea`、`decisions.gyb`、`decisions.deploy`、handoffs、issues、runs、feedback、`experiments/`、`ops/gpu_state.md`（快车道自己跑 GPU 时） |
| `writes` | `experiments/`（worktree 在仓库外，钩子不判） |
| `ledger_writes` | decisions.deploy 全部、handoffs 的 start/done/stuck/open/accept/reject/withdraw/release/resume/amend、issues 全部、scratch 全部（含 ql open/close）、feedback add |
| `dispatches_to` | run；gpu-runner（只在快车道） |
| `model` | `as_subagent` 是 opus，`manual` 是 inherit |

run：

| 栏 | 值 |
|---|---|
| `reads` | handoffs 里的 `launch_order`、issues（归自己的）、`experiments/`、`ops/gpu_state.md`、runs |
| `writes` | `artifact_root`（仓库外，钩子不判） |
| `ledger_writes` | runs 全部、handoffs 的 start/estimate/done/stuck、issues 的 open、decisions.run add（自决极少，比如挑卡的理由）、feedback add |
| `dispatches_to` | 无 |
| `model` | `as_subagent` 是 opus，`manual` 是 inherit |

run 的 `rl inbox` 不查过版。

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
| `reads` | 一切（九本账、全部目录） |
| `writes` | `review/` |
| `ledger_writes` | decisions.reviewer 全部、session focus、feedback add |
| `dispatches_to` | 无 |
| `model` | `as_subagent` 是 fable，`manual` 是 inherit |

reviewer 不开 issue。

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

按施工计划第五节：SKILL.md 正文出现的每条 rl 写命令都在这个角色 json 的 `ledger_writes` 里、每个读的目录都在 `reads` 里，查询命令不查。

按测试 13：五份 SKILL.md 里出现的每条 rl 子命令、账名、状态名、目录名都在施工计划第二、五、六节里查得到，写命令在该角色的 `ledger_writes` 里，查询命令不查；SKILL.md 里没有 common/ 母版条文的副本。

第三件事对应的规矩是：SKILL.md 不抄公共母版的条文，只写一句「按 common/ 执行」。母版本体见 `09-common-and-feedback.md`。

两处原文不一致：设计文档「五个角色」总段只写了「每条 rl 写命令都要在 `ledger_writes` 里，查询命令不查」这一条，施工计划第五节多写了「每个读的目录都在 `reads` 里」，测试 13 又多写了账名、状态名、目录名和母版副本三样。按施工计划的表为准，三样都查。

## 读的纪律

读的纪律写进每个角色 SKILL.md 的读法栏，公共母版里的原话方向是这几句：

读文件先想清楚要回答什么问题，再挑最小的读法。读进来的每个字都留在上下文里挤占后面的判断，所以大文件禁止整读，抽查实验输出就是抽几条看文字形态，日志用 grep 和头尾定位。读记忆一律经 rl 的查询命令、只读自己需要的那部分、默认最新版，不直接开 loop/ 下的文件；`rl inbox` 和 `rl decision stale` 都只列和本会话手上单子有关的，不列全库。对污染上下文大的读操作特别警惕。

这几句的正式文本落在 `common/READING.md` 里，见 `09-common-and-feedback.md`。

读权一律不硬拦，所以这一栏全靠纪律加 reviewer 事后查。唯一接回机器的一处是授权：idea 读 `notes/` 要 gyb 发 `read:notes`，grant 是给 reviewer 事后查的凭据，doctor 有一项扫描「决定的来源指向 notes/ 但 grants 里查不到这个 actor 的 read:notes」。授权账的行格式在 `03-ledgers.md`，这项扫描在 `05-rl-cli.md`。

## 和别的 part 的接口

- 九本账的公共骨架（`actor`、`session_id`、`force_reason`、`fix_for`）和每本账的必填规则：定义在 `03-ledgers.md`。
- issue 的 kind `denied`、`request`，以及 `handoff_id` 什么时候必填：定义在 `03-ledgers.md`。
- sessions 账的 `role`、`model`、`launched_by`、`rules_version`、`status`、`focus` 各栏：定义在 `03-ledgers.md`。
- grants 账的 `grantee`、`permission`（第一版只有 `read:notes`）、只收 `cli` 这条规矩：定义在 `03-ledgers.md` 和 `01-gyb.md`。
- 转移表的「谁能写」和「前提」两栏、gyb 对哪一栏豁免：定义在 `04-handoffs-and-sessions.md`。
- 会话登记和销号那两个钩子调的命令 `rl session start` 和 `rl session end`、销号时扫哪些状态：定义在 `04-handoffs-and-sessions.md` 和 `05-rl-cli.md`。
- `rl` 的 actor 判定、`--as-gyb`、`--quote`、`--force --reason` 这一组规矩：定义在 `01-gyb.md` 第二节（2026-08-17 gyb 裁）；参数写法和退出码在 `05-rl-cli.md`。
- gyb 的豁免范围从 gyb 那头怎么用、裸终端就是 gyb 这条推论：写在 `01-gyb.md`。
- 快车道里 deploy 派 gpu-runner 这条 `dispatches_to` 的例外：写在 `07-quick-lane.md`。
- 插件树里 hooks/、monitors/、tables/roles/ 摆在哪，`rl init` 往 CLAUDE.md 追加那一节的时机，宿主脏树白名单那处改动：写在 `08-trees-init-and-host.md`。
- 公共母版八条规矩（尤其第 8 条出圈即留痕）、`common/READING.md`、`rules_version`：写在 `09-common-and-feedback.md`。
- 待验证清单每条的测法、通过标准、失败备案，测试 8 和测试 13 在施工步骤里的位置：写在 `30-build-steps-verify-tests.md`。
- deploy 改宿主文件的三条纪律、reviewer 的读顺序：写在 `11-role-deploy.md` 和 `14-role-reviewer.md`。

## 源文档没写清的（留给 gyb）

1. 钩子怎么判「研究仓库内的相对路径」。绝对路径怎么折回相对路径、软链接指到仓库外算不算仓库内，源文档没写。new1 的产物目录是软链接到 net 盘的，这一条落地时会撞上。
2. 五个角色共用一个钩子脚本还是各一份，现在是主案加备案两个值。主案是「五个角色共用一个脚本、参数报角色名」，备案是「五个角色各一份钩子脚本，内容相同只差常量」，选哪个挂在待验证第 2 条上。
3. idea 的 `writes` 是「无目录」，可是钩子只拦四个角色目录和 `loop/`。idea 会话 Write 仓库根或 `docs/` 会被放行，这跟 `writes` 栏写的「无目录」对不上，源文档没写这里要不要拦。
4. `notes/` 那一条写权规矩对谁生效。四个目录里只有 `notes/` 的主人是 gyb，而 gyb 的裸终端不受钩子约束，所以这一条在角色会话里等于永远 deny，源文档没写这是不是本意。
5. 会话状态文件 `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json` 谁清理、会话结束之后删不删、`${CLAUDE_PLUGIN_DATA}` 这个变量在这台机器上解析到哪，源文档都没写。
6. 一个会话只加载一个角色，但加载第二个角色 skill 会发生什么没写：钩子叠不叠、sessions 账落一行还是两行、状态文件覆不覆盖。
7. `dispatches_to` 这一栏谁来查。`writes` 有钩子、`ledger_writes` 有入账校验加测试 13，`dispatches_to` 只有 deploy 的 gpu-runner 注了「只在快车道」，源文档没写机器上有没有对应的检查。
8. `reads` 栏里的写法没有统一。五份 json 里有的写账的英文名（runs、evaluations），有的写文件路径（`decisions.idea`、`ops/gpu_state.md`），有的写一句话（「九本账全部」「一切」），而测试 13 要按这一栏查「每个读的目录都在 `reads` 里」，源文档没写按哪种形式查。
9. 角色 json 改了一栏算不算母版改动。母版带 `rules_version`、改动要走 feedback 账并单独 commit，角色 json 是不是同一套流程，源文档没写。
10. 钩子拦下之后开的那条 `denied` issue 的 assignee 填谁。九种 kind 的必填字段里 `denied` 要 `handoff_id`，没写这条 issue 归 gyb 还是归 owner。
11. 加载角色的会话在 Bash 里直接写四个角色目录（比如 `echo > analysis/x.md`）钩子看不见，第三层纪律里也没有一句专门管这个，源文档只写了「Bash 写出来的文件钩子不看」。

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
