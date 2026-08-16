# analysis 与 deploy 之间的交流

> 这份只覆盖一条通道：analysis 干活的时候发现实验代码有问题，开一条 issue 给 deploy，deploy 回，然后有人把它关掉。这份写清这条 issue 上填什么 kind、怎么和派活单关联、deploy 怎么回、谁 close。
> 这份不覆盖：analysis 角色本身干什么（13-role-analysis.md）、deploy 角色本身干什么（11-role-deploy.md）、analysis 开给 gyb 的 issue（22-pair-idea-analysis.md）、run 开给 deploy 的 issue（21-pair-deploy-run.md）、issues 账的完整行格式（03-ledgers.md）、issue 命令的完整参数（05-rl-cli.md）、派活单状态转移表全表（04-handoffs-and-sessions.md）、钩子拦哪些路径（06-hooks-and-permissions.md）。
> 源：设计文档的「五个角色」总段、「analysis」一节、「账本」一节的 issues 那一条、「审读意见里没采纳的」第 3 条；施工计划第二节词表、第三节 issues 的行格式、第四节转移表的 `in_progress`→`stuck` 和 `stuck`→`todo` 两行、第五节 analysis 与 deploy 的 use case 表、第六节 issue 那一行命令、第八节两个阈值、第十三节公共规矩第 6 条。

## 为什么只有这一条通道

analysis 的写权只有 `analysis/` 一个目录，实验代码在 `experiments/` 里，钩子只放 deploy 写那里。所以 analysis 看出代码有问题也动不了手，唯一的出路是开一条 issue 给 deploy。

设计文档在「审读意见里没采纳的」第 3 条把这件事写死了，原话是：「下游发现 typo 的小修口子：写权按角色不开例外，run 或 analysis 发现代码问题开 issue 给 deploy。」施工计划第五节 analysis 的 use case 表里对应的一条写作「发现代码问题开 issue 给 deploy」。

公共规矩第 6 条（施工计划第十三节，rule-06）叫故障分域，原话是：「deploy 和 idea 接到问题先判病因在不在自己域，在就地修；run 出问题一律开 issue 给 deploy，不自行重试，重来是发射单上的下一次尝试；analysis 卡住开 issue 给出问题的角色；reviewer 不开 issue，卡住也只写进清单交给 gyb。」analysis 这条通道就是这句话里「开 issue 给出问题的角色」的一个实例，出问题的角色是 deploy。

反方向没有对称的通道。施工计划第五节 deploy 的 use case 表里没有「开 issue 给 analysis」这一条，deploy 的 `dispatches_to` 只有 run 和快车道里的 gpu-runner。机器上不禁止，因为 issues 的 `assignee` 取值是五个角色或 `gyb`，而 deploy 的 `ledger_writes` 含 issues 全部命令；但是两份源文档都没写这件事该怎么走，留在文末。

两份源文档在这条通道上没有互相打架的地方。设计文档的 analysis 一节根本没提这条通道，只在「审读意见里没采纳的」里带了一句；施工计划第五节把它列进了 use case 表。两处说法方向一致，只是设计文档写得少。

## analysis 这一头：开单填什么

命令是 `rl issue open --to deploy --kind K --text [--handoff ID] [--log-tail FILE|--log-text -]`（施工计划第六节）。analysis 的 `ledger_writes` 里有 issues 的 open 和 reply 两个（施工计划第五节），所以这条命令 analysis 调得动。

kind 从九种里挑：`cannot`（干不了）、`not_mine`（不归我干）、`denied`（被钩子拦了）、`failed`（跑失败，附 `stage`）、`anomaly`（结果反常）、`request`（申请）、`withdrawn`、`orphaned`、`fyi`（后三种是通知类）。两份源文档都没有给「analysis 发现代码有问题」这一条指定用哪个 kind，这件事留在文末。

`handoff_id` 这一栏，issues 的行格式规定 `cannot`、`failed`、`denied`、`withdrawn`、`orphaned` 五种 kind 必填，其余可选（施工计划第三节）。analysis 发现代码问题的时候手上一般正拿着一张 `analysis_order`，填的就是这张单子的编号。

开给 deploy 的 issue 不发桌面通知。桌面通知只在 `assignee` 是 `gyb` 的那一版触发，含首次开单（施工计划第三节 issues、第六节 `rl notify` 的推送表）。这条 issue 露头的地方是 deploy 的 `rl inbox`，那里列「本角色名下 open 的 issue」。deploy 上线的第一个动作就是 `rl inbox`。

## 要不要把手上的分析单标 stuck

标 stuck 是另一个动作，命令是 `rl handoff stuck ID --issue ID`。analysis 的 `ledger_writes` 里有 handoffs 的 start、done、stuck 三个，所以标得动。

转移表里 `in_progress`→`stuck` 这一行：谁能写是 holder，前提是「`issue_id` 指向一条已存在的 issue，并且那条 issue 的 `handoff_id` 指回本单」，之后没有人拉起下游（施工计划第四节）。所以顺序定死了，先开 issue 拿到编号，再标 stuck，这也是账本一节写死的跨账写序。

标了 stuck 就清空 holder，上一个 holder 记进 `last_holder`（原则 3 的推论，施工计划第四节表头）。清空之后这张分析单不再挡 analysis 会话销号。

回到待干走 `stuck`→`todo` 那一行：谁能写是「回了 issue 的那个角色、owner」，前提是关联 issue 的状态已经是 `answered`，之后由 owner 拉起下游，子命令是 `rl handoff resume`。分析单的 owner 是 idea 或者 gyb（施工计划第二节词表）。deploy 的 `ledger_writes` 里有 handoffs 的 resume，analysis 的没有，所以按字面读，把这张单子交回待干的是回了 issue 的 deploy 或者 owner，不是 analysis 自己。

两份源文档都没写 analysis 发现代码问题时必不必标 stuck。施工计划第五节把「发现代码问题开 issue 给 deploy」和 handoffs 的 stuck 分成两条 use case 列，没说这两件事绑不绑在一起。这件事留在文末。

## deploy 这一头：怎么回

deploy 在 `rl inbox` 里看到这条 issue，先按公共规矩第 6 条判病因在不在自己域。在自己域就地修，写权是 `experiments/`；改动如果改变实验结果（取第几层、用哪个划分、超参取值），按公共规矩第 2 条要在 `decisions.deploy.jsonl` 里留一条决定，来源默认填改动的文件路径；纯写法的改动不算自决。

回复的命令是 `rl issue reply ID --text`，写完这条 issue 到 `answered` 状态，`reply` 这一栏在 `answered` 那一版必填。写权限定在 assignee 或 gyb 手里（施工计划第三节 issues），这里 assignee 是 deploy。

deploy 解决不了就改派 gyb，命令是 `rl issue reassign ID --to gyb`。改派等于追加一版换 `assignee`，`assignee` 变成 `gyb` 的这一版触发桌面通知。

## 谁 close

close 的写权是「开单的 actor 或 gyb」（施工计划第三节 issues）。这条通道上开单的是 analysis，所以手动关的人是 analysis 或者 gyb，deploy 关不了。

另外有两处自动关。一处是 `rl handoff accept`，验收一张单子的时候，它关联的 `answered` issue 自动关掉；分析单由 idea 或 gyb 验收，验收那一刻这条 issue 就跟着关了。另一处是 `rl inbox` 读到通知类 issue 即关，但是这条通道开的不是通知类 issue，用不上。

没人关的时候有两道网。`rl doctor` 有一项扫「`answered` 超过 N 天没 close 的 issue」，N 是 `issues.answered_stale_days`，默认 3 天（施工计划第八节）。`rl doctor` 还有一项扫「`cannot`/`failed`/`denied` 且 open 且没有单子指回的 issue」。

`rl status` 的段 2 只列 assignee 是 `gyb` 的 open issue，超过 `issues.gyb_stale_hours`（默认 24 小时）的标出来。所以这条开给 deploy 的 issue 在 gyb 的收件箱里不露头，除非 deploy 把它改派给了 gyb。

## 一条通道从头到尾

| 步 | 谁做 | 命令 | 账上落什么 |
|---|---|---|---|
| 1 | analysis | `rl issue open --to deploy --kind K --text [--handoff ID]` | issues 一版，status `open`，assignee `deploy` |
| 2（可选） | analysis | `rl handoff stuck ID --issue ID` | handoffs 一版，status `stuck`，holder 清空并记进 `last_holder` |
| 3 | deploy | `rl issue reply ID --text` | issues 一版，status `answered`，`reply` 必填 |
| 3 的岔路 | deploy | `rl issue reassign ID --to gyb` | issues 一版换 `assignee`，触发桌面通知 |
| 4 | deploy | 改 `experiments/` 里的代码 | 改变实验结果时 `decisions.deploy.jsonl` 一版，来源填改动的文件路径 |
| 5 | deploy 或 owner | `rl handoff resume ID` | handoffs 一版，status 回 `todo`，之后 owner 拉起 |
| 6 | analysis 或 gyb | `rl issue close ID` | issues 一版，status `closed` |
| 6 的替代 | idea 或 gyb | `rl handoff accept ID` | 这张单子关联的 `answered` issue 自动落 `closed` |

## 和别的 part 的接口

- issues 的行格式、九种 kind 的取值、`assignee` 和 `handoff_id` 两栏的必填规则、reply 与 close 的写权：03-ledgers.md。
- `rl issue open/reply/reassign/close/link/show/list` 的完整参数，`rl inbox` 列哪四类，`rl status` 的十段，`rl doctor` 的扫描项，`rl notify` 的推送表：05-rl-cli.md。
- 转移表 `in_progress`→`stuck` 和 `stuck`→`todo` 两行的完整六栏，以及 holder 只在 `in_progress` 非空这条不变量：04-handoffs-and-sessions.md。
- analysis 的 `reads`、`writes`、`ledger_writes` 四栏和它的 use case 表：13-role-analysis.md。
- deploy 的 `ledger_writes`、自决留痕的粒度、改 `experiments/` 外文件的纪律：11-role-deploy.md。
- 钩子只拦「写别的角色的目录」和「直接写 loop/」两类事，`experiments/` 只有 deploy 能写：06-hooks-and-permissions.md。
- 公共规矩第 6 条故障分域的全文、公共规矩第 2 条自决必留痕：09-common-and-feedback.md。
- 分析单的 owner 是 idea 或 gyb、验收由 owner 做：22-pair-idea-analysis.md。
- analysis 遇到分组键缺失时开给 gyb 的那条 issue（kind 是 `cannot`）：22-pair-idea-analysis.md。
- 阈值 `issues.answered_stale_days`（默认 3）和 `issues.gyb_stale_hours`（默认 24）出自施工计划第八节；这张阈值表归哪一份 part 收，见 00-overview.md 的文档索引。

## 源文档没写清的（留给 gyb）

1. 这条 issue 填哪个 kind 没定。九种 kind 里没有一种是「代码有问题」，`cannot`（干不了）和 `not_mine`（不归我干）两种读法都说得通。kind 还决定 doctor 扫不扫得到它：doctor 那一项只扫 `cannot`、`failed`、`denied` 三种。
2. analysis 发现代码问题的时候，必不必把手上的分析单标 `stuck` 没写。如果不标，这张单子停在 `in_progress`，holder 一直挂着 analysis 会话；如果标，analysis 自己回不到 `todo`（见下一条）。
3. deploy 修完之后谁把分析单交回待干没写全。转移表允许「回了 issue 的那个角色、owner」写这一行，deploy 的 `ledger_writes` 有 handoffs 的 resume，analysis 的没有。所以按字面读 analysis 自己 resume 不了。这是不是有意的，源文档没说。
4. 反方向的通道没写。deploy 看出 analysis 的统计代码有问题该怎么办，两份源文档都没有条目：deploy 的 use case 表里没有开 issue 给 analysis 这一条，而 reviewer 一节说分析代码由 reviewer 审、reviewer 不开 issue。
5. 「代码问题」的范围没划。`analysis/` 里 init 播下的公共统计件出问题算不算这条通道，源文档没写；那个目录的写权在 analysis 自己手上。
6. analysis 怎么看到实验代码没写。施工计划第五节 analysis 的 `reads` 是 runs、evaluations、handoffs、issues、feedback、`decisions.idea`、`decisions.gyb`、`analysis/`，里面没有 `experiments/`。按原则 2 的推论读一律不设权，`reads` 是纪律不是门禁，所以读得到，但是这条通道要求 analysis 读代码，`reads` 栏里却没有它。
7. issue 里要不要附证据没写。`--log-tail` 和「附日志末 40 行和 traceback」这两条只写给了 run 的四种失败，analysis 这条通道没写要附什么。
8. deploy 改完代码之后，已经跑出来的那些 run 的数字算不算数、要不要重跑，两份源文档在这条通道上都没写。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

以下条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，保留场景名、序号、严重度、kind、原文、依据、改法，不做判断、不改字。这些条目大多是在 run 和 deploy 那条通道上报的，机制和这一份重合，抄进来备查。

### result-wrong-review（25 步，gyb 动手 11 次）

3. [blocks/contradiction] 第 16 步：设计文档说 reviewer「不开 issue、不派活」，施工计划第十三节公共规矩第 6 条说「analysis 和 reviewer 不在楼梯上，卡住直接开 issue 给出问题的角色」，两句直接打架；而且 reviewer 的角色 json 里 ledger_writes 只有 decisions.reviewer 和 feedback add，没有 issues，真按规矩 6 开 issue 会被入账校验退出码 3，reviewer 中途读不到产物时按文档无路可走。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-build-plan.md:250; plans/2026-08-16-research-loop-build-plan.md:109
   - 改法：规矩 6 里把 reviewer 摘出来，明写 reviewer 只写 review/ 清单、卡住也只写进清单交给 gyb。

### run-crash-midway（40 步，gyb 动手 4 次）

9. [slows/missing] 第 38、39 步：issue 从 answered 到 closed 谁打、什么时候打没写。run 的 ledger_writes 只有 issue open（build-plan.md:105），deploy 和 idea 都有 close（:101、:103）但没规定何时用；`rl status` 七段（:142）只列改派给 gyb 超时的 issue，`rl doctor` 八项（:144）也不扫 answered 未 close 的 issue。结果是每次崩溃都留一条挂着的 issue，只有 gyb 偶然翻到才收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl handoff accept` 时自动 close 掉这张单子关联的 answered issue，doctor 补一项「answered 超过 N 天没 close」。

12. [slows/missing] 第 9、14 步：归角色（不是 gyb）的 issue 没有任何推送，角色上线也没规定要查。build-plan.md:59 只有 assignee 变成 gyb 那一版触发通知，build-plan.md:131 规定的「角色上线第一个动作」只有 `rl decision stale`。本 trace 里 deploy 会话正同步等着才立刻收到；一旦按待验证第 9 条的备案（build-plan.md:197）改成 deploy 开单即销号，iss-0031 就静静躺在账里没人知道，只能等 gyb 打 `rl status`。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：角色上线第一个动作改成两条：`rl decision stale` 加 `rl issue list --open --to <本角色>`。

13. [slows/guessed] 第 9 步：跑挂该开哪种 kind 的 issue，只能猜。build-plan.md:45 的六种 kind 是 cannot / not_mine / denied / anomaly / request / withdrawn，没有一种对应「跑挂」；build-plan.md:166 给的命令模板直接写成 `rl issue open --to deploy --kind ...` 把 kind 留空；next-steps.md:72 列了四种要开 issue 的情形（smoke 失败、发射失败、跑挂、结果反常）但只给结果反常指定了 anomaly。本 trace 取 cannot 是猜的，四种情形挤进一个 kind 之后 `rl issue list` 没法按失败类型筛。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：给 run 的四种失败各定一个 kind（smoke_failed / launch_failed / crashed / anomaly），写进第二节词表。

### idea-request-notes（15 步，gyb 动手 4 次）

10. [cosmetic/missing] 第 10 步和第 11 步：issues 三个状态的写权只有一句「按第五节 ledger_writes」，谁写 reply、谁写 close 没规定；idea 的 ledger_writes 含 issues 的 open/reply/reassign/close 四个，所以 idea 自己开、自己答、自己关全过校验，和派活单那张写得很死的转移表不对称
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:79
   - 改法：第六节 issue 那一行加前提栏：reply 只有 assignee 或 gyb 能写，close 只有开单的 actor 或 gyb 能写

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

5. [slows/blocked] 第 6 步（补 stuck 那一版）：`rl handoff stuck` 的前提是「那条 issue 的 handoff_id 指回本单」，但 `rl issue open` 的 `--handoff` 是可选参数；崩在写序中途的那条 issue 如果当初没带 --handoff，这条前提永远满足不了，而 issues 的命令只有 reassign/reply/close，没有补 handoff_id 的路，第一类同样修不了。
   - 依据：2026-08-16-research-loop-build-plan.md:84; 2026-08-16-research-loop-build-plan.md:132; 2026-08-16-research-loop-build-plan.md:59
   - 改法：要么把 `--handoff` 在 kind 是 cannot/denied/withdrawn 时改成必填，要么加一条 `rl issue link ID --handoff ID`（追加一版只补这个字段）。
