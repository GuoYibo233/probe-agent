# idea 与 deploy 之间的交流

> 这份覆盖工单 work_order 这一条通道的全部：字段、从开单到验收的状态走法、验收怎么做、打回、收回与 cascade、reissue、issue 往返、过版检查对工单的影响。
> 这份不覆盖：deploy 怎么开发射单派给 run（21-pair-deploy-run.md）、idea 怎么开分析单（22-pair-idea-analysis.md）、决定账本身和决定的来源与改版规矩（02-decisions.md）、九本账的完整行格式（03-ledgers.md）、派活单转移表全表与会话生命周期（04-handoffs-and-sessions.md）、`bin/rl` 完整命令表（05-rl-cli.md）、钩子和角色 json（06-hooks-and-permissions.md）、快车道（07-quick-lane.md）、idea 和 deploy 两个角色各自的活（10-role-idea.md、11-role-deploy.md）、gyb 的收件箱（01-gyb.md）。
> 源：设计文档的「五个角色」「idea」「deploy」「账本」「交接与会话生命周期」四节加决定树那一段；施工计划的第二节词表、第三节 handoffs 行格式、第四节转移表、第五节 idea 与 deploy 的 use case、第六节命令表里 handoff 和 issue 两行。

## 这条通道上的单子是什么

idea 把决定拆成工单派给 deploy，工单就是 `work_type` 取 `work_order` 的那一种派活单。三种派活单同住 handoffs 一本账，用 `work_type` 区分，另外两种是分析单 `analysis_order` 和发射单 `launch_order`。

工单上的人有三个。`from_role` 是 idea，它同时就是 owner，单子从开到关归它，验收、打回、收回、重新拉起下游都是它的活。`to_role` 是 deploy。`holder` 是当前正在干这张单子的那个会话的 session_id，只在 `in_progress` 这一个状态上非空，离开 `in_progress` 一律清空并把上一个 holder 记进 `last_holder`。owner 是角色不是会话，idea 角色当下没有活着的会话时，这张单子由 gyb 拉起，`rl status` 单列这一类。

## 工单上的字段

下面六个字段是这条通道自己的，取值和必填规则照抄施工计划第三节。

| 字段 | 是什么 | 必填规则 |
|---|---|---|
| `decision_refs` | 列表，每项 `{"id":...,"version":...}`，指这张单子照哪几条决定的哪一版干 | `work_order` 必填至少一项 |
| `explanation` | idea 自己写的一段解释，把决定里的东西讲明白 | `work_order` 必填 |
| `report_paths` | 形如 `{"method":...,"detail":...}`，两份部署报告的路径 | 进 `done_pending_review` 时 `method` 必填且存在，`detail` 非快车道时必填且存在 |
| `code_paths` | 代码路径清单，列表 | 进 `done_pending_review` 时必填 |
| `dispatch` | 派发方式，取 `auto`（owner 后台起 subagent）、`manual`（gyb 亲自接）、`none`（暂不派） | 三选一 |
| `supersedes` | 接替哪张单 | 可选，`rl handoff reissue` 开新单时指旧单 |

工单还带这些公用字段：`id` 形如 `ho-0012`；`status` 七选一；`parent_id`、`batch`、`quick_lane` 布尔；`line` 由 rl 从 `decision_refs` 第一项的 `root_id` 算出来存着；`progress_note`（进 `todo` 且不是新建时必填）；`reason`（`rejected`、`withdrawn` 时必填，角色会话发起的 `withdrawn` 还要 `quote`）；`issue_id`（`stuck` 时必填）。九本账的公共骨架七样在 03-ledgers.md。

工单里不能只甩决定编号。`explanation` 的解释权在 idea：idea 要把那条决定里的东西讲明白。怎么测试、什么算成功也要 idea 自己想明白，只是不预写成单子上的字段。

## 开单

idea 打 `rl handoff open --type work_order --to deploy --decision ID@V ... --explain ...`，单子落 `todo`。开单那一刻只查「单子说得清自己是什么」，也就是 `decision_refs` 和 `explanation` 在不在；交付物齐不齐是交活那一刻才查的事。

开单带的旗子决定谁去接：不带旗子是 `dispatch=auto`，owner 后台起一个 deploy subagent 接走，上游会话继续可用；带 `--manual` 是 `dispatch=manual`，idea 只开单，gyb 自己开 session 去接；带 `--no-dispatch` 是 `dispatch=none`，单子停在 `todo` 等 gyb 说开跑。

派活不占终端。subagent 回来的时候上游验收；上游会话先结束了，单子照常在账上等 owner 下次上线或者 gyb 验收。下游 subagent 没走到交活或者卡住就返回的（报错、上下文满），上游当场 `rl handoff release` 交回待干，再决定是重起一个还是开 issue 给 gyb。

## 从开单到验收的状态走法

七个状态是待干 `todo`、开干 `in_progress`、卡住 `stuck`、干完等待验收 `done_pending_review`、验收完成 `accepted`、打回 `rejected`、收回 `withdrawn`。`accepted` 和 `withdrawn` 是终态。入账脚本只认转移表，表外的转移一律拒收，退出码 2。

下面这张表是施工计划第四节转移表里和 `work_order` 有关的行，另外两种 `work_type` 的前提删掉了，字句没改。全表在 04-handoffs-and-sessions.md。gyb 对「谁能写」一栏一律豁免，「前提」一栏是完整性校验，对 gyb 生效，gyb 用 `--force --reason` 越过并留痕。

| 从 | 到 | 谁能写 | 前提 | 之后谁拉起 | 子命令 |
|---|---|---|---|---|---|
| （新建） | `todo` | `from_role` | `work_order` 有 `decision_refs` 和 `explanation` | `dispatch=auto` 时 owner 后台起 subagent；`manual` 等 gyb；`none` 不动 | `handoff open` |
| `todo` | `in_progress` | `to_role` | 写入会话的角色等于 `to_role`；`holder` 为空（非空退出码 2 并列出当前 holder） | 无 | `handoff start` |
| `todo` / `stuck` | `todo`（内容追加） | owner、`to_role` | 只改内容：`work_order` 补 `report_paths` 或 `code_paths`；状态不变 | 无 | `handoff amend` |
| `in_progress` | `stuck` | holder | `issue_id` 指向一条已存在的 issue，并且那条 issue 的 `handoff_id` 指回本单 | 无 | `handoff stuck` |
| `stuck` | `todo` | 回了 issue 的那个角色、owner | 关联 issue 状态是 `answered` | owner | `handoff resume` |
| `in_progress` | `done_pending_review` | holder | `work_order` 的 `report_paths` 和 `code_paths` 齐 | 无 | `handoff done` |
| `done_pending_review` | `todo`（内容追加） | owner、`to_role` | 只补 `report_paths` 里丢了的路径，状态不变（doctor 修法用） | 无 | `handoff amend` |
| `done_pending_review` | `accepted` | owner | 无；gyb 越过 owner 时 rl 给 owner 发 `fyi` | 无 | `handoff accept` |
| `done_pending_review` | `rejected` | owner | `reason` 非空 | owner | `handoff reject` |
| `rejected` | `todo` | owner、`reclaim` | 无 | owner | `handoff release` |
| `rejected` | `in_progress` | `to_role` | 写入会话的角色等于 `to_role`（原会话还活着直接接着干） | 无 | `handoff start` |
| `todo` / `in_progress` / `stuck` / `done_pending_review` / `rejected` | `withdrawn` | owner | `reason` 非空（角色会话发起还要 `quote`）；有 holder 时 rl 顺带开 `withdrawn` 通知给 holder 的角色和 owner；`--cascade` 时 rl 代 owner 连 `parent_id` 指向本单的下游单一起收，下游账行 actor 记发起人 | 无 | `handoff withdraw` |
| `in_progress` | `todo` | 销号钩子、`reclaim`、owner、gyb | `progress_note` 非空（钩子和 reclaim 自动填）；rl 给 owner 开 `orphaned` 通知 | owner，owner 无活会话时进 `rl status` 的「等 gyb 拉起」 | `handoff release` |
| 任一非终态 | 同状态（接替） | owner | `--decision ID@V` 给新版本；rl 收旧单（`withdrawn`，级联）、开新单（继承 `explanation`、`parent_id`、`batch`，`supersedes` 指旧单）、通知全部 holder | 同新建 | `handoff reissue` |

工单被打回、被回收、下游销号之后回到待干，都由 idea 重新拉起下游。

## 验收：先 method 后 detail

验收不预写标准，验收产物是部署报告。理由是要验的是「代码和想法是不是一回事」，这个判断在代码写出来之前写不成条目；写得成条目的（跑得通、快不快）不是要验的东西。

deploy 干完写两份部署报告，都放 experiments/ 下这张工单自己的目录里。第一份叫 `method`，像论文里那样只讲做法、用了什么技术、数据怎么被处理，不带任何文件；它必须原样抄一遍这张工单引的决定编号加版本，reviewer 拿它当锚审「代码和决定是不是一回事」。第二份叫 `detail`，带上文件和处理细节、这次改了哪些文件的清单（含 experiments/ 外的宿主文件）、这张单子上关联的 issue 编号和结论。

deploy 提「干完等待验收」的时候，派活单记两份报告路径和代码路径清单，路径为空入账脚本不收这个状态。deploy 在这条工单下面开的发射单验收完之后，deploy 先把 run_id 和关键指标补进 `detail` 那一份，再提工单的「干完等待验收」。

验收人是 owner，也就是 idea；gyb 随时可以自己验。读的顺序是先读不带文件的 `method` 那一份看做法对不对，再读带文件的 `detail` 那一份看写出来的东西和说的是不是一回事。gyb 越过 owner 验收或者打回的时候，rl 给 owner 发一条 `fyi` 通知。验收一张单子时，它关联的已回复 issue 自动关。

## 打回

打回是 `rl handoff reject ID --reason`，只有 owner 能写，`reason` 必须非空，写明为什么不收。打回之后单子进 `rejected`，往下有两条路：owner 或者 `reclaim` 打 `rl handoff release` 把它交回 `todo`，由 owner 重新拉起下游；或者原来那个 deploy 会话还活着，直接 `rl handoff start` 从 `rejected` 接着干。

两处原文不一致：设计文档「交接」一节写「打回（owner 或 gyb 写，必须附原因，之后单子回待干、owner 重新拉起）」，施工计划第四节把 `rejected` 记成一个独立状态，回 `todo` 要另打一条 `handoff release`，还多给了一条 `rejected` 直接回 `in_progress` 的路。按施工计划的表。

## 收回与 cascade

收回是 `rl handoff withdraw ID --reason [--quote] [--cascade]`，只有 owner 能写，单子关闭，`withdrawn` 是终态。从 `todo`、`in_progress`、`stuck`、`done_pending_review`、`rejected` 五个状态都能收回。角色会话发起收回还要带 gyb 的原话。收回一张有 holder 的单子时，rl 顺带开一条 `withdrawn` 通知给 holder 的角色和 owner。

带 `--cascade` 的时候，rl 代 owner 把 `parent_id` 指向本单的下游单子一起收，下游那几行账的 actor 记发起人。工单下面挂着的发射单就是这么被一起收掉的：发射单的 `parent_id` 填的是工单。发射单被收回之后 run 那一头只做 `rl run finish --exit killed` 加收尾，不再改单子状态，见 21-pair-deploy-run.md。

## reissue：决定改版之后重派

决定改了一版，不影响已经派出去的单子。单子按派出时引的那一版继续做，rl 只标过时，不自动打回、不自动标待复核、不自动停。停不停由 gyb 点名，停就用收回。改版之后要重派的用 `rl handoff reissue ID --decision ID@V`：一条命令收旧单、开新单、记接替关系。新单继承 `explanation`、`parent_id`、`batch`，`supersedes` 指旧单，旧单按 `withdrawn` 收掉并级联，全部 holder 收到通知。

## issue 往返

deploy 干不下去的时候先开一条 issue，再把单子标卡住。写序定死：先写 issue 拿到编号，再写单子那一行引它，中间崩了顶多多一条没人引的 issue，doctor 扫得出来。`handoff stuck` 的前提是 `issue_id` 指向一条已存在的 issue，并且那条 issue 的 `handoff_id` 指回本单。issue 的九种 `kind` 里，`cannot`（干不了）、`not_mine`（不归我干）、`denied`（被钩子拦了）三种都必填 `handoff_id`。

issue 的三个状态是 `open`、`answered`、`closed`。回复只有 assignee 或者 gyb 能写；关闭由开单的 actor 或者 gyb 做；`rl handoff accept` 关这张单关联的 `answered` issue；通知类 issue 被 `rl inbox` 读过即关。assignee 是 gyb 的那一版（含首次开单）触发桌面通知，其余进角色的 `rl inbox`。

deploy 解决不了的问题改派给 gyb，用 `rl issue reassign ID --to gyb`。改派之后这条 issue 落进 gyb 的收件箱，见 01-gyb.md。

issue 被回复之后，由回 issue 的那个角色打 `rl handoff resume` 把单子交回待干，`to_role` 的任何一个会话都能接，默认还是 owner 再起一个下游。

## 过版检查对工单的影响

引用记的版本比账里最新版小就是过时。`rl decision update` 和 `rl decision retire` 写完那一刻，rl 当场列出引旧版而没到终态的单子和它们的 holder。过版的单子进 `rl status`，也进相关角色的 `rl inbox`——idea 和 deploy 上线第一个动作是 `rl inbox`，里面有一段就是本角色持有或拥有的单子里过版的决定引用。`rl decision stale [--mine] [--handoff ID]` 默认只列和本会话手上单子有关的，`--all` 才是全库。retired 决定名下还有活单的进 `rl status` 和 doctor。

工单的 `line` 是根决定编号，rl 从 `decision_refs` 第一项的 `root_id` 算出来存在单子上，`rl status --group-by line` 按它切开两条并行的研究线。

## 快车道补单

快车道合回的时候 deploy 补一张标了 `quick_lane` 的工单，`from_role` 和 `to_role` 都是 deploy，验收人固定是 gyb，允许新建直接进 `done_pending_review`，只要一份 `method` 简报，`explanation` 由 deploy 写并抄 gyb 点名的原话。这一整条路（`rl ql open`、杂账、`rl ql close`、免掉哪些手续）在 07-quick-lane.md。

两处原文不一致：设计文档写快车道补单「from_role 和 to_role 都是 deploy」，施工计划第二节词表把 owner 定义成「开单角色，就是 from_role」又补一句「快车道补单和 gyb 开的单 owner 记 gyb」，第四节那一行也写「owner 记 gyb」。按施工计划的表，这一行的 owner 记 gyb。

## 和别的 part 的接口

- `decision_refs` 里的 `{"id","version"}`、`root_id`、决定改版与废除的规矩：02-decisions.md。
- handoffs 一本账的完整行格式和九本账的公共骨架七样：03-ledgers.md。
- 转移表全表（含 `analysis_order` 和 `launch_order` 的行）、holder 不变量、销号与 `reclaim` 怎么把工单交回待干：04-handoffs-and-sessions.md。
- `rl handoff open/start/amend/stuck/resume/done/accept/reject/withdraw/release/reissue` 和 `rl issue open/reassign/reply/close/link` 的完整参数、退出码、`--json`：05-rl-cli.md。
- 「谁能写」一栏之外的分权（钩子只挂 Write 和 Edit）、idea 与 deploy 两份角色 json 的 `ledger_writes`：06-hooks-and-permissions.md。
- 快车道补单的进出登记、杂账、免掉的手续：07-quick-lane.md。
- 发射单的 `parent_id` 指工单、决定引用和 `batch` 从工单继承、`attempts`：21-pair-deploy-run.md。
- 分析单的 `evaluation_refs` 和交付物：22-pair-idea-analysis.md。
- `rl status` 里「等验收的单子」「等 gyb 拉起」「过版的单子」几段、桌面通知推送表：01-gyb.md。
- reviewer 按工单交活时记的 `code_paths` 和 `runs` 账里的 commit 审代码：25-pair-reviewer-idea.md。

## 源文档没写清的（留给 gyb）

1. 工单卡住时 deploy 开的那条 issue 归谁。源文档只写了 run 出问题一律开 issue 给 deploy、deploy 解决不了改派 gyb，没写 deploy 卡在工单上的时候 assignee 填 idea 还是 gyb。
2. 普通工单的 `parent_id` 填不填。施工计划第三节只规定了 `launch_order` 必填指工单、`analysis_order` 可选、快车道补单空，`rl handoff open` 又有 `--parent ID` 这个参数。
3. 转移表两行 `handoff amend` 的「到」栏写的是 `todo`（内容追加），前提栏又写「状态不变」，两栏对不上。`done_pending_review` 上 amend 完停在 `done_pending_review` 还是回 `todo`，照字面读不出来。
4. `rl handoff reissue` 开的新单继承 `explanation`、`parent_id`、`batch`，`report_paths` 和 `code_paths` 继不继承没写。
5. idea「怎么测试、什么算成功也要自己想明白，只是不预写成单子上的字段」，那这段想法落在 `explanation` 里还是只在会话里说给 deploy 听，没写。
6. 打回之后 deploy 重新交活的时候，旧的 `report_paths` 和 `code_paths` 留着还是换新路径，没写。
7. 工单被收回之后，deploy 已经写在 experiments/ 里的代码和产物怎么处置，两份文档都没写（第二轮模拟 decision-revised-while-in-flight 第 18 条报的就是这条）。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

以下条目从 `plans/2026-08-16-research-loop-simulation-round2.md` 原样抄来，保留场景名、序号、严重度、kind、原文、依据、改法，没做判断也没改字。那份文件开头写明这 234 条全部未经核实。

### param-tweak（45 步，gyb 动手 8 次）

3. [slows/blocked] 第 25、26 步：部署报告要放「experiments/ 下这张工单自己的目录」，而快车道补单是新建直达 done_pending_review、开单时才分配单号，开单又硬要求两份报告路径已经存在，目录名在拿到单号之前取不出来
   - 依据：plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-build-plan.md:82; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：明写快车道补单的报告目录用 ql_tag 命名（experiments/ql-20260816-01/），单号事后不改目录

4. [slows/contradiction] 第 25 步：同一段里先说快车道「不写两层部署报告」，又说合回时补的那张工单要附两份部署报告路径且路径必须存在，等于把免掉的手续原样搬到出口
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:82; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：快车道补单只要一份 method 简报，detail 允许用杂账里那几行 ql_tag 记录顶替

6. [slows/contradiction] 第 26、27 步：词表和 idea 一节定死 work_order 是 idea 开给 deploy、owner 就是 from_role、验收人是 owner，但快车道补单写在 deploy 的 ledger_writes 里由 deploy 自己开，成了 deploy 开给 deploy、deploy 验收自己的报告
   - 依据：plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-next-steps.md:122; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：明写快车道补单 from_role=deploy、to_role=deploy 且验收人固定为 gyb，入账脚本对这一种单子拒收 deploy 自己 accept

18. [cosmetic/missing] 第 26 步：work_order 的 explanation 定义成「idea 自己写的解释」且是必填，快车道全程没有 idea 会话，这段解释谁写、写什么没写
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:48
   - 改法：补一句：快车道补单的 explanation 由 deploy 写，注明来自 gyb 口头点名并抄一句原话

### new-idea（39 步，gyb 动手 7 次）

4. [blocks/too_heavy] 第 10 步和第 19 步：接单默认是同步的，deploy 等 run 几个小时、idea 又等 deploy，于是 gyb 手动加载的 idea 会话从派单那一刻起被整场实验占住，gyb 想看进度只能另开终端；待验证第 9 条的失败备案只写了 deploy→run 这一层改成开单即销号，idea→deploy 这一层没有备案
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：明写 gyb 手动加载的角色会话一律不同步等下游，开完单即返回，验收由下一次会话或 gyb 在 rl status 里做

10. [slows/ambiguous] 第 33 步：设计文档说 deploy 验收完发射单「再拿数字接着干工单」，但没写这一步具体产出什么：工单的交付物只有两份部署报告，而报告在开发射单之前就写完了，数字进不进报告没写，于是既可以读成「什么都不用做直接 done」，也可以读成「要把 run_id 和指标补回报告」
   - 依据：plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:118; plans/2026-08-16-research-loop-build-plan.md:87
   - 改法：明写「发射单验收后 deploy 把 run_id 和关键指标补进 detail 报告，再提 done_pending_review」

### result-wrong-review（25 步，gyb 动手 11 次）

7. [slows/missing] 第 11 步：reviewer 读顺序第一段要「先读最终的代码」，但没写要审的代码清单从哪来；工单上只有 report_paths 没有代码路径，而 deploy 改到 experiments/ 外的宿主文件（run.py 注册表、MAP.md、ops/）只列在 detail 报告里，读顺序又把 detail 排在最后，先读代码那一遍必然漏掉宿主文件的改动。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：工单加一个 code_paths 字段由 deploy 提验收时填，或明写 reviewer 第一段可以先读 detail 报告里的文件清单那一节、不读它的结论。

### next-plan-after-results（36 步，gyb 动手 16 次）

8. [slows/missing] 第 27、36 步：决定 retire 之后，引用它的在办单子没人扫。doctor 的八项扫描和 rl status 的七段都没有「retired 决定名下还有没到终态的单子」这一项，设计文档又把停不停全交给 gyb 点名，忘了收回就一直挂着
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:112
   - 改法：doctor 和 status 各加一项「retired 决定名下还有活单」，附上 `rl handoff withdraw --cascade` 的修法

9. [slows/missing] 第 27 步：`--cascade` 收回下游单子的写入人是上游单的 owner（idea），可发射单的 owner 是 deploy，转移表 withdrawn 那一行「谁能写」只写了 owner，没给级联收回开口子
   - 依据：2026-08-16-research-loop-build-plan.md:92; 2026-08-16-research-loop-next-steps.md:124
   - 改法：转移表 withdrawn 那一行加一句「级联收回时上游单的 owner 可写下游单」，账行记清是级联触发的

10. [slows/ambiguous] 第 31 步：开完工单要不要立刻起 deploy subagent。设计文档说默认上游开完单直接起 subagent 同步等它回来，本场景 gyb 只想定计划不想现在开跑，文档没有「开单但暂不派」的默认，gyb 不当场喊停就会被带进几小时的实施
   - 依据：2026-08-16-research-loop-next-steps.md:120; 2026-08-16-research-loop-next-steps.md:48
   - 改法：`rl handoff open` 加 `--no-dispatch`，SKILL.md 写明 gyb 没说开跑就停在 todo

### run-crash-midway（40 步，gyb 动手 4 次）

4. [slows/missing] 第 19 步：转移表 build-plan.md:85 的 stuck→todo（谁能写=回了 issue 的那个角色，前提=关联 issue 已 answered）在 bin/rl 命令表 build-plan.md:134 里没有对应子命令，只能借 `release`；而 release 在转移表 build-plan.md:93 那一行的谁能写是「销号钩子、reclaim、owner」、前提只有「holder 清空」，借它就绕开了「issue 必须已回」这个前提。本场景 deploy 恰好既是 owner 又是回 issue 的人才糊得过去，工单场景（owner 是 idea、holder 是 deploy、回 issue 的是 idea）同样糊得过去但语义已经错位。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：给这一行加一个专门的子命令 `rl handoff resume ID`，前提校验关联 issue 是 answered。

9. [slows/missing] 第 38、39 步：issue 从 answered 到 closed 谁打、什么时候打没写。run 的 ledger_writes 只有 issue open（build-plan.md:105），deploy 和 idea 都有 close（:101、:103）但没规定何时用；`rl status` 七段（:142）只列改派给 gyb 超时的 issue，`rl doctor` 八项（:144）也不扫 answered 未 close 的 issue。结果是每次崩溃都留一条挂着的 issue，只有 gyb 偶然翻到才收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl handoff accept` 时自动 close 掉这张单子关联的 answered issue，doctor 补一项「answered 超过 N 天没 close」。

10. [slows/too_heavy] 第 12 到 20 步：三层会话同步嵌套等待：idea 等 deploy 等 run（next-steps.md:120、:58）。一个训练跑几小时，崩了之后 deploy 修完还要再等一整轮重跑，sess-idea-01 从派单到验收全程挂着不能做别的，与 next-steps.md:7「想法要快速、多次迭代」直接冲突。待验证第 9 条（build-plan.md:197）只测了一层（deploy 等 run），没测两层嵌套，备案也只写了 deploy 那一层。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：发射单一旦标 stuck 就让上游 subagent 立刻返回并销号，重跑由 gyb 在 `rl status` 里另起一个 deploy 会话接。

16. [cosmetic/contradiction] 第 23 步：卡住的单子被回复之后谁能接，两处说法不一样。next-steps.md:116 写「卡住的 issue 被回复之后单子回待干，谁接都行」，转移表 build-plan.md:83 的 todo→in_progress 那一行前提写死「写入会话的角色等于 to_role」。按正文任何角色都能接，按表只有 run 能接。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:116; plans/2026-08-16-research-loop-build-plan.md:83
   - 改法：把 next-steps.md:116 的「谁接都行」改成「to_role 的任何一个会话都能接」，与转移表对齐。

17. [cosmetic/missing] 第 34 步：崩过一次这件事在两份部署报告里没有落点。next-steps.md:56 规定 method 那份只讲做法、用了什么技术、数据怎么被处理，detail 那份带文件和处理细节，两份都不装失败史；reviewer 拿 method 那份当锚审「代码和决定是不是一回事」时，看不到「原来的 batch size 跑不动」这条，只能自己去 issues 账翻。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:88
   - 改法：detail 那份加一栏「这张单子上关联的 issue 编号和结论」，由 `rl handoff show` 自动列。

### n-launch-orders（58 步，gyb 动手 10 次）

3. [blocks/principle_violation] 第 14 步：违反原则 3（每张派活单有 owner 和 holder，holder 是当前正在干这张单子的那一个会话）。转移表 todo→in_progress 那一行的前提只有「写入会话的角色等于 to_role」，没有「holder 为空」这一条，所以两个 run subagent 先后 start 同一张单是合法转移，后一个直接覆盖前一个的 holder，另一张单没人接却在账上看不出来。
   - 依据：2026-08-16-research-loop-build-plan.md:83; 2026-08-16-research-loop-next-steps.md:17
   - 改法：转移表 todo→in_progress 的前提加一句「holder 为空」，已有 holder 时退出码 2 并把当前 holder 列出来。

13. [slows/missing] 第 26 步：待验证第 9 条（上游 subagent 同步等几小时会不会被超时收掉）的备案正好落在这个场景上，但备案没给续跑规矩：一旦 deploy 开完单就销号，ho-0012 会被销号钩子交回 todo、报告还没写、5 张发射单已经派出去，下一个 deploy 会话重新 start 之后怎么知道进度到哪、去哪找那个 batch，文档没写。
   - 依据：2026-08-16-research-loop-build-plan.md:197; 2026-08-16-research-loop-build-plan.md:93; 2026-08-16-research-loop-next-steps.md:120
   - 改法：备案里补一句：work_order 也记 batch，重新 start 时第一件事是 rl handoff list --batch 复原五张单的状态。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

1. [blocks/missing] 第 7、10 步：handoffs 行格式（build-plan.md:61）里没有任何父子字段：launch_order 不记它挂在哪张 work_order 上，重开的单子也不记它接的是哪张旧单。可是 next-steps.md:124 的 `--cascade` 要「连它派生的下游单子一起收」、next-steps.md:80 说 analysis 能「从决定顺到发射单再顺到 run_id」、build-plan.md:144 的 doctor 要扫「快车道工单已 accepted 但没有关联发射单」——三处都要这条链，账里没有这个字段。本场景 idea 打了 --cascade，rl 走不到 ho-0013，正在烧卡的那张发射单收不掉。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个 `parent_handoff` 字段，开发射单和分析单时必填，cascade、doctor、链式查询都走它。

2. [blocks/missing] 第 7 步：decision_refs 只对 work_order 必填（build-plan.md:61），文档没有一句要求 deploy 把工单的决定编号抄进发射单，所以 `rl decision stale`（build-plan.md:131）和 `rl handoff list --decision`（build-plan.md:136）都列不出正在跑的 ho-0013。过版检查只看得见工单，看不见真正在花机时的那张单。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-next-steps.md:111
   - 改法：开 launch_order 时自动从父工单继承 decision_refs 并写进单子，stale 检查按继承后的引用算。

4. [blocks/blocked] 第 16、18 步：转移表转到 `withdrawn` 那一行（build-plan.md:92）的前提栏写「无」，没有像 rejected 和 release 两行那样写「holder 清空」。销号时 `rl session end` 要扫 holder 是本会话的单子，有就拒绝（build-plan.md:126、next-steps.md:126），逃生口 `--release` 是把单子交回 `todo`，可是 `withdrawn` 到 `todo` 在表里不存在。结果 run 会话和 deploy 会话都销不了号，只能等 `rl reclaim`。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-next-steps.md:126
   - 改法：转到 `withdrawn` 的那一行前提栏补「holder 清空」，并明写 session end 只检查未到终态的单子。

5. [slows/contradiction] 第 10、11 步：转移表「谁能写」栏（build-plan.md:92）规定收回只有 owner 能写，而 next-steps.md:124 的 `--cascade` 要求 owner 一条命令连下游单一起收，下游单的 owner 是另一个角色（本场景 idea 收 deploy 的发射单）。两句同时成立就等于 owner 能越过另一个 owner 写单子。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：明写 cascade 是 rl 代 owner 连锁收回、被收的下游单 actor 记发起人并自动给下游 owner 开一条 issue，或者干脆只允许 gyb 用 --cascade。

6. [slows/missing] 第 7 步：文档只在两个时机查过版：「角色上线第一个动作跑过版检查」（next-steps.md:111）和 `rl status`（next-steps.md:124）。决定改版的那一刻，`rl decision update`（build-plan.md:128）不输出任何「有 N 张在办单子引着旧版」的提示。本场景是我按原则 6 让 idea 主动再跑一次 `rl decision stale`，文档没有这条规矩；idea 不跑就没人发现。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-build-plan.md:128; plans/2026-08-16-research-loop-build-plan.md:131
   - 改法：`rl decision update` 和 `retire` 写完那一刻当场列出引旧版且未到终态的单子，并把它们的 holder 会话一起打印出来。

10. [slows/missing] 第 10 步：公共规矩第 1 条（build-plan.md:245）要求不可逆动作要有 gyb 当场的原话，收回是终态、不可逆，可是 `rl handoff withdraw ID [--cascade]`（build-plan.md:134）没有 `--quote` 参数，handoffs 行格式（build-plan.md:61）也没有 quote 字段，gyb 那句「停」没有落点。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:245; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：withdraw 和 reject 都加 `--quote`，handoffs 行加 quote 字段，角色会话发起时缺 quote 就报错。

11. [slows/missing] 第 17 步：接单默认是同步的，上游会话等下游 subagent 回来（next-steps.md:120、next-steps.md:17）。等待期间上游会话没有任何中断通道，rl 给它开的 `kind=withdrawn` issue 要等下游返回才看得见。本场景 deploy 从工单被收回到 run 返回的那几个小时里对收回完全无反应，还在等一张已经作废的发射单。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：收回一张有 holder 的单子时，同时给它的下游单子发同一条收回信号，让下游的看门狗把上游一起唤醒；或者明写等待期间的收回一律由 gyb 直接收到最底层那张单。

12. [slows/missing] 第 19 步：转到 `withdrawn` 那一行的「之后谁拉起」栏写「无」（build-plan.md:92），收回只给 holder 的角色开 issue，不给 owner 任何东西。S-idea1 从同步等待里醒来，发现自己开的 ho-0012 已经被收回，下一步该干什么文档没写，它是接着开新单还是销号只能自己猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：收回时给 owner 角色也开一条 issue（kind 复用 withdrawn），转移表第五栏写明 owner 醒来后要么重开单要么销号。

13. [slows/missing] 第 20 步：rl 自动开的 `kind=withdrawn` issue 的 assignee 是角色不是会话（build-plan.md:59），run 的 subagent 收到信号后就结束了，这条 issue 没人回也没人关。doctor 的扫描项里只有「没人引用的 issue」（build-plan.md:144），这条带着 handoff_id 所以扫不出来，会一直挂在 `rl status` 的 open 列表里。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：withdraw 自动开的 issue 直接落成 `closed`（它是通知不是问题），或者 doctor 加一条「holder 已销号但 withdrawn issue 仍 open」的扫描并附 close 命令。

16. [slows/too_heavy] 第 6 到 22 步整段：「换个评测集」这一件事走了 23 步、gyb 亲自动手 8 次、牵动 4 个会话，其中 5 步是纯手续（分两次收单、两个会话销不掉号、手动关两条通知 issue、按新版本重开一张内容几乎相同的工单）。目标那一节写的是「想法要快速、多次迭代」（next-steps.md:7），这条路上没有任何一条把「决定改版后重派」压成一步的捷径。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：加一条 `rl handoff reissue ho-XXXX --decision ID@V`：一条命令连锁收旧单、清 holder、继承 explanation 开新单，并通知全部 holder。

17. [cosmetic/missing] 第 21 步：重开的 ho-0014 和被收回的 ho-0012 之间没有任何字段能看出是同一件事的第二次派发（handoffs 行格式 build-plan.md:61 里没有 supersedes 之类的栏），`rl status` 和 `rl handoff list --decision` 都只会把它们并排列成两张单。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：handoff open 加 `--supersedes ho-XXXX`，写进单子并在 status 里归成一组。

18. [cosmetic/missing] 第 13、18 步：单子被收回之后，experiments/ 里 deploy 已经写下的代码和产物根里那半截产物目录怎么处置，两份文档都没写。快车道有明确的进出规矩（next-steps.md:64 的 worktree 和合回），正常路收回之后没有对应的一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：转移表转到 `withdrawn` 那一行的前提栏补一句：holder 在返回前把半截产物路径写进那条 withdrawn issue，处置由 gyb 定。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

2. [blocks/missing] 第 1 步：没有任何办法表达「这张单 gyb 手动接，别起 subagent」：rl handoff open 没有这个旗子，handoffs 行里没有这个字段，idea 的默认动作是开完单直接起 deploy subagent 并同步等。gyb 的口头交代不进账，idea 会话一旦重开或被 reclaim，idea 还会按 owner 职责再拉起一个下游，两个会话抢着打 rl handoff start，晚的那个撞上「表外转移一律拒收」拿退出码 2。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:83; plans/2026-08-16-research-loop-build-plan.md:95
   - 改法：给 handoffs 加一个 dispatch 字段（auto / manual），rl handoff open 带 --manual 时 owner 不起 subagent、rl status 单列这类单子。

8. [slows/too_heavy] 第 11、16、22 步：gyb 亲手接一张已经开出来的正式工单，手续和 subagent 走一模一样：必须开发射单、必须分步计时填 step_table、必须写两份部署报告（method 那份还要原样抄决定编号加版本）。想减手续只有快车道，可快车道的入口是「gyb 点名」加另开一棵 worktree 加 rl scratch add，转移表里也没有「已开出的工单转快车道」这一行，而且审读意见第 1、2 条已经明确否掉了按改动大小分档。gyb 亲自上手的场合反而最重，和「想法要快速、多次迭代」相反。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:178; plans/2026-08-16-research-loop-build-plan.md:82
   - 改法：转移表补一行「todo 的 work_order 由 gyb 改标 quick_lane」，改标之后免发射单和两份报告，只留 scratch 记录。

9. [slows/too_heavy] 第 12 步到第 21 步：gyb 手动的 deploy 会话按默认要同步等 run subagent 跑完才能接着干，实验跑几个小时 gyb 的交互终端就被占几个小时；而「上游 subagent 同步等下游几个小时会不会被超时收掉」还挂在待验证第 9 条上没有结论，备案是「长任务改成 deploy 开单即销号」，两种走法对 gyb 手动会话的体验差别很大。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：对 gyb 手动加载的角色会话默认走异步：开完发射单就把工单 release 回 todo，等 run 完了 rl status 提醒 gyb 再接。

11. [slows/missing] 第 26 步：gyb 越过 owner 直接验收之后，没有任何通道把这件事告诉 owner idea。转移表 done_pending_review→accepted 那一行第五栏是「无」，issues 账只在改派给 gyb 时发通知，rl status 是给 gyb 的收件箱不是给角色的。idea 会话下次上线只会看到单子已经是终态，不知道是谁验的、为什么验过。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:88; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:20
   - 改法：gyb 代 owner 写终态转移时，rl 自动给 owner 角色开一条 kind=not_mine 之外的新 kind（比如 fyi）的 issue，或者在角色上线时和 decision stale 一起报一句「你名下的单子被 gyb 处理过」。

12. [slows/missing] 第 6 步：取一条决定的指定版本没有命令。rl decision show 只有默认最新版和 --history 全量两档，可单子按派出时引的那一版继续做，deploy 要的就是 dec-idea-0007 第 2 版；只能把全部历史拉进上下文再自己挑，和读法纪律「挑最小的读法、大文件禁止整读」直接顶上。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-next-steps.md:144
   - 改法：rl decision show 加一个 --version V 参数，handoff show 里显示 decision_refs 时顺带把那一版正文带出来。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

8. [blocks/missing] 第 13 步：owner 是角色不是会话，owner 角色没有活着的会话时谁把它叫醒没写。原则 3 和交接一节四处都写「回到待干、由 owner 重新拉起下游」，本场景蒸馏线的 deploy 会话已销号，账上只剩一张 todo 单子和一个不存在的 owner。按原则 1 只能推出 gyb 有权自己干，推不出系统怎么提醒他该开哪个角色的会话。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:93
   - 改法：rl status 单列一段「等 gyb 拉起」：owner 角色没有活会话的 todo 单子，每行附上该开哪个角色会话的那条命令。

### idea-request-notes（15 步，gyb 动手 4 次）

10. [cosmetic/missing] 第 10 步和第 11 步：issues 三个状态的写权只有一句「按第五节 ledger_writes」，谁写 reply、谁写 close 没规定；idea 的 ledger_writes 含 issues 的 open/reply/reassign/close 四个，所以 idea 自己开、自己答、自己关全过校验，和派活单那张写得很死的转移表不对称
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:79
   - 改法：第六节 issue 那一行加前提栏：reply 只有 assignee 或 gyb 能写，close 只有开单的 actor 或 gyb 能写

### periodic-reclaim（27 步，gyb 动手 11 次）

9. [blocks/missing] 第 18、19 步：半成品代码没有落点。handoffs 的字段表里 report_paths 只有提 done_pending_review 时才填，in_progress → todo 那一版里没有任何字段记着上一个会话写到哪、动了哪些文件、下一个人该接着改还是推倒重来。接手的 deploy 只能自己去 experiments/ 里翻代码猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-next-steps.md:56
   - 改法：给 in_progress → todo 这一行加一个必填的 progress_note，reclaim 自动填「reclaim 于 X，工作目录 experiments/<handoff_id>」，接手方先读它。

### hook-missed-session-end（23 步，gyb 动手 11 次）

6. [slows/guessed] 步 13、步 14：设计 L120 只写「上游开完单直接起一个 subagent 接走并同步等它回来」，没写下游 subagent 没走到 done 或 stuck 就返回的时候上游拿到什么、该做什么。待验证第 9 条（设计 L168、施工 L197）只问「等几个小时会不会被超时收掉」，不问「等的对象死了怎么办」。最快能发现这件事的就是被阻塞的上游会话，文档没给它任何职责，我只能按原则 3 推它该 release 加重起。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：设计 L120 补一句「下游 subagent 没走到 done 或 stuck 就返回的，上游当场 rl handoff release 并决定重起还是开 issue 给 gyb」，并写进 idea 和 deploy 的 SKILL.md。

8. [slows/missing] 步 12、步 16：单子交回 todo 之后重派，死掉的 deploy 在 experiments/ 里留下的半成品代码没人负责交代或清理。handoffs 的字段（施工 L61）没有工作记录一栏，交付物只有两份部署报告（设计 L118），单子上看不出这张单干过两遍，新 deploy 是接着干还是推倒重来没有依据。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:118; plans/2026-08-16-research-loop-build-plan.md:93
   - 改法：转移表 in_progress→todo 那一行加一个必填的 note 字段，写清上一手干到哪、产物在哪。

12. [slows/missing] 步 8、步 10：单子回到 todo 之后由 owner 重新拉起（设计 L17、施工 L93 第五栏），但 owner 是角色不是常驻进程。没有活着的 idea 会话的时候，这张 todo 单子只能等 gyb 下次看 rl status 才有人碰；谁在什么时候把 owner 叫起来，文档没写。本场景里重派全靠 gyb 口头说一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：rl status 的单子那段单列一行「todo 且 owner 角色当前没有活着的会话」的单子，并进桌面通知。

### doctor-findings-fix（24 步，gyb 动手 15 次）

6. [slows/too_heavy] 第 9 到 19 步（修第二类）：第二类的真实病因只是一份报告文件没了，修它却要走「打回 → 加载 deploy 会话 → decision stale → start → 重写报告 → done → accept」七步，中间还要新登记一个会话、还要把单子在四个状态之间转一圈。对着「想法要快速、多次迭代」这条目标偏重。
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:91; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:88
   - 改法：给 done_pending_review 的单子加一条 `rl handoff amend ID --report-detail P`：追加一版只换路径、不改状态、校验路径存在。

13. [cosmetic/missing] 第 1 步（谁跑 doctor、跑完能不能自己修）：doctor 写的是「谁都行」，但角色会话跑出问题之后能不能自己修没写。deploy 看到自己名下那张 done_pending_review 的报告路径没了，它是 to_role 不是 owner，按转移表打回只有 owner 能写，它只能开 issue，文档没说这一步该开给谁、kind 填哪个。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:45
   - 改法：在 doctor 那一行写一句「角色跑 doctor 只看不修，修法一律 `rl issue open --to <owner> --kind cannot` 报给 owner 或 gyb」。
