# idea 与 analysis 之间的交流（含 gyb 直接开分析单）

> 这份覆盖分析单 `analysis_order` 这一条通道的全部：谁开单、owner 记谁、开单时带的 `evaluation_refs` 怎么带版本、开单可以引 `proposed` 而交活必须全部 `approved`、交活的 `output_paths`、验收和打回、派活单状态转移表里和分析单有关的那几行、以及「单个 run 的原始指标可以直接引、跨 run 的聚合一律走分析单」这条界。
> 这份不覆盖：口径账 `evaluations` 本身的行格式和四个状态的取值（在 `03-ledgers.md`）、analysis 怎么问 gyb 要统计什么和怎么提口径（在 `13-role-analysis.md`）、gyb 批口径和打回口径（在 `01-gyb.md`）、idea 角色的全部动作（在 `10-role-idea.md`）、analysis 走快车道先画一张图（在 `07-quick-lane.md`）、analysis 发现代码问题开 issue 给 deploy（在 `24-pair-analysis-deploy.md`）、派活单转移表整张和会话销号（在 `04-handoffs-and-sessions.md`）、`rl` 命令表整张（在 `05-rl-cli.md`）、九本账的公共骨架（在 `03-ledgers.md`）。
> 源：设计文档的「十一条设计原则」（原则 3、4、9、11）、「gyb 自己做的事」、「五个角色」里 idea 一节和 analysis 一节、「账本」里 handoffs 和 evaluations 两条、「交接与会话生命周期」；施工计划的第一节裁决、第二节词表、第三节 handoffs 字段、第四节转移表、第五节 idea 与 analysis 的 use case、第六节命令表、第十节测试 4 和 5、第十三节公共规矩第 4 条。

## 一、这条通道是什么

分析单的英文名是 `analysis_order`，它和工单 `work_order`、发射单 `launch_order` 同住一本 handoffs 账，用 `work_type` 区分。分析单由 idea 或 gyb 开给 analysis，做的事是把 gyb 说要看的数算出来、把 gyb 说要画的图画出来。

一张分析单从开到关的路是：idea 或 gyb 开单落 `todo`，analysis 会话接单进 `in_progress`，算完写完交活进 `done_pending_review`，owner 验收进 `accepted`。中间可以打回、可以卡住、可以收回，每一步都是 handoffs 账上追加的一版。

派活不占终端（原则 11）：idea 开完分析单之后后台起一个 analysis subagent 接走，idea 会话继续可用，subagent 回来的时候 idea 验收。idea 会话先结束了，单子照常在账上等 idea 下次上线或者 gyb 验收。

## 二、谁开单，owner 记谁，谁去接

开单的角色就是 owner，owner 记在 `from_role` 栏里。分析单的 `from_role` 是 `idea` 或者 `gyb`：idea 开的单 owner 是 idea，gyb 自己开 analysis 会话的时候上游填 gyb。`to_role` 固定是 `analysis`。

owner 负责这张单子从开到关：拉起下游、验收、收回（原则 3）。owner 是角色不是会话，owner 角色当下没有活着的会话时单子由 gyb 拉起，`rl status` 单列这一类。

`holder` 是当前正在干这张单子的那个会话的 `session_id`，只在 `in_progress` 非空。任何离开 `in_progress` 的转移一律清空 `holder` 并把它记进 `last_holder`（原则 3 推论）。

派发方式记在 `dispatch` 栏，三个取值：`auto` 是 owner 后台起 subagent，`manual` 是 gyb 亲自接，`none` 是暂不派。idea 开分析单的命令可以带 `--manual` 或 `--no-dispatch`（施工计划第五节 idea 的 use case）。

`rl inbox` 是查询命令，谁需要谁敲，不是上线动作：被派单拉起的 analysis 会话先干拉它起来的那张单。`rl inbox` 里有本角色名下 open 的 issue、owner 是本角色而 `holder` 为空的单子、本会话手上单子引的过版决定、发给本角色的通知、本角色提的 feedback 的裁决。

## 三、开单时单子上带什么

分析单开单落 `todo` 的前提只有一条：有 `evaluation_refs`（施工计划第四节转移表新建那一行）。

`evaluation_refs` 是一个列表，每一项写成 `{"id":..., "version":...}`，和工单的 `decision_refs` 同一个写法，引用带版本（施工计划第三节 handoffs）。

开单的时候 `evaluation_refs` 里的口径可以还是 `proposed`，交活的时候每一项必须是 `approved`（设计文档 idea 一节；施工计划第三节 handoffs、第四节转移表）。这条对应原则 4 的推论：前提查在交付那一刻，不查在开单那一刻，开单只查「单子说得清自己是什么」。测试 4 里有对应的两条：引 `proposed` 口径开单通过、交活时有 `proposed` 拒收。

这条是施工计划第一节末尾第（e）条列出的、第六轮改的设计变动，写着「gyb 不认就改回」，原来的写法是「单子里只能引已经批准的口径行」。设计文档 idea 一节已经按新写法改过。

`parent_id` 对分析单可选（施工计划第三节 handoffs）。两处原文不一致：设计文档原则 9 写「发射单和分析单都记父单，开单时从父单继承决定引用和 batch」，施工计划第三节写「`parent_id`（`launch_order` 必填指工单，`analysis_order` 可选）」；按施工计划的表为准，分析单的 `parent_id` 可选。

## 四、交活：output_paths 与口径全部 approved

analysis 交活写 `output_paths`，格式是 `{"notebook":..., "figures":[...]}`（施工计划第三节 handoffs）。命令是 `rl handoff done ID [--notebook P --figure P ...]`（2026-08-17 随 `05` 定稿裁：不带 `--actual-seconds`，耗时只由 `rl run finish` 算）。

进 `done_pending_review` 的前提两条，都是机器可查的：`output_paths` 存在，`evaluation_refs` 每一项是 `approved`。缺一条入账脚本不收这个状态（设计文档「交接与会话生命周期」的交付物段；施工计划第四节转移表 `handoff done` 那一行）。测试 4 里对应的一条是「`analysis_order` 缺 notebook 拒收」。

产物落在哪：小图和 notebook 进仓库的 `analysis/`，大文件进配置里的分析产物根 `analysis_artifact_root` 并在口径行里记路径（设计文档 analysis 一节）。

## 五、验收、打回、卡住、收回

验收人是 owner，也就是开单的 idea 或 gyb。gyb 随时可以自己验（原则 1）；gyb 越过 owner 验收或者打回的时候，`rl` 给 owner 发一条 `fyi` 通知（设计文档「交接与会话生命周期」；施工计划第四节 `handoff accept` 那一行）。

打回要附 `reason`，`reason` 为空入账脚本不收。打回之后单子进 `rejected`，由 owner 重新拉起下游；原会话还活着的话 analysis 可以从 `rejected` 直接 `handoff start` 接着干。

分析单卡住走 `handoff stuck`，必须连带一条 issue 互相引用：单子的 `issue_id` 指向那条 issue，那条 issue 的 `handoff_id` 指回本单。analysis 遇到历史 run 的 `config` 里缺这次要用的分组键的时候开 issue 给 gyb，`kind` 是 `cannot`（设计文档 analysis 一节；施工计划第五节 analysis 的 use case）。issue 被回到 `answered` 之后，回了 issue 的那个角色或者 owner 用 `handoff resume` 把单子交回 `todo`。

收回走 `handoff withdraw`，`reason` 非空，角色会话发起还要 `--quote`；从 `in_progress` 收回时 `rl` 顺带开一条 `withdrawn` 通知给 holder 的角色和 owner，从其他状态收回不通知。

analysis 会话销号的时候，如果它是某张 `in_progress` 分析单的 holder，销号钩子把单子 release 回 `todo`、自动填 `progress_note`、给 owner 开一条 `orphaned` 通知。

桌面通知按推送表走（施工计划第六节 `rl notify` 那一行）：单子进 `done_pending_review` 且 owner 是 `gyb` 或者 `dispatch=manual` 的时候推送。owner 是 idea 的分析单交活之后不推送桌面通知，进 idea 的 `rl inbox` 和 `rl status` 的等验收那一段。

## 六、转移表里和分析单有关的行

下面这几行是施工计划第四节转移表里分析单会走到的行，六栏照抄，「前提」一栏只留和 `analysis_order` 有关的部分。整张表在 `04-handoffs-and-sessions.md`。

| 从 | 到 | 谁能写 | 前提（分析单部分） | 之后谁拉起 | 子命令 |
|---|---|---|---|---|---|
| （新建） | `todo` | `from_role` | `analysis_order` 有 `evaluation_refs`（可以是 proposed） | `dispatch=auto` 时 owner 后台起 subagent；`manual` 等 gyb；`none` 不动 | `handoff open` |
| `todo` | `in_progress` | `to_role` | 写入会话的角色等于 `to_role`；`holder` 为空（非空退出码 2 并列出当前 holder） | 无 | `handoff start` |
| `todo` / `stuck` | `todo`（内容追加） | owner、`to_role` | 只改内容：`analysis_order` 补 `evaluation_refs`；换 `evaluation_refs` 里的引用（doctor 悬空引用的修法）；状态不变 | 无 | `handoff amend` |
| `in_progress` | `stuck` | holder | `issue_id` 指向一条已存在的 issue，并且那条 issue 的 `handoff_id` 指回本单 | 无 | `handoff stuck` |
| `stuck` | `todo` | 回了 issue 的那个角色、owner | 关联 issue 状态是 `answered` | owner | `handoff resume` |
| `in_progress` | `done_pending_review` | holder | `analysis_order` 的 `output_paths` 存在且 `evaluation_refs` 每项 `approved` | 无 | `handoff done` |
| `done_pending_review` | `todo`（内容追加） | owner、`to_role` | 补或改 `output_paths` 里的路径，换 `evaluation_refs` 里的引用；状态不变（doctor 修法用） | 无 | `handoff amend` |
| `done_pending_review` | `accepted` | owner | 无；gyb 越过 owner 时 rl 给 owner 发 `fyi`；rl 顺带关这张单关联的 `answered` issue | 无 | `handoff accept` |
| `done_pending_review` | `rejected` | owner | `reason` 非空；gyb 越过 owner 时 rl 给 owner 发 `fyi` | owner | `handoff reject` |
| `rejected` | `todo` | owner、`reclaim` | 无 | owner | `handoff release` |
| `rejected` | `in_progress` | `to_role` | 写入会话的角色等于 `to_role`（原会话还活着直接接着干） | 无 | `handoff start` |
| `todo` / `in_progress` / `stuck` / `done_pending_review` / `rejected` | `withdrawn` | owner | `reason` 非空（角色会话发起还要 `quote`）；从 `in_progress` 收回时 rl 顺带开 `withdrawn` 通知给 holder 的角色和 owner，其他状态不通知 | 无 | `handoff withdraw` |
| `in_progress` | `todo` | 销号钩子、`reclaim`、owner | `progress_note` 非空（钩子和 reclaim 自动填）；rl 给 owner 开 `orphaned` 通知；销号钩子写的这一版 `actor` 记会话的角色、`via=session_end`，reclaim 写的 `actor` 记 gyb、`via=reclaim` | owner 照单子原来的 `dispatch` 拉起（`auto` 再起一个 subagent），owner 无活会话时进 `rl status` 的「等 gyb 拉起」 | `handoff release` |
| 任一非终态 | 旧单 `withdrawn`，新单 `todo`（`supersedes` 指旧单） | owner | `--decision ID@V` 给新版本；rl 收旧单（`withdrawn`，级联）、开新单（继承 `explanation`、`parent_id`、`batch`，`supersedes` 指旧单）、通知全部 holder | 同新建 | `handoff reissue` |

`accepted` 和 `withdrawn` 是终态。入账脚本只认这张表，表外的转移一律拒收，退出码 2。

两处原文不一致：施工计划第四节转移表的 `handoff amend` 那一行写「谁能写：owner、`to_role`」，第五节 analysis 的 `ledger_writes` 里没有 `handoff amend`（只有 handoffs 的 start/done/stuck）。按施工计划的表为准，analysis 作为 `to_role` 能用 `handoff amend` 补 `evaluation_refs`，第五节那一栏漏了。

## 七、单个 run 的原始指标和跨 run 的聚合

单个 run 的原始指标 idea 可以直接从 runs 账念给 gyb 听，任何跨 run 的对比、聚合、画图一律走 analysis 的分析单和口径账（设计文档 idea 一节）。

公共规矩第 4 条写的是同一件事：每个数字配可复现的执行路径，统计类证据走 analysis 的 notebook；单个 run 的原始指标可以直接引，跨 run 的对比、聚合、画图一律走分析单（施工计划第十三节）。

配套的两条：analysis 只算 gyb 说要看的数、只画 gyb 说要画的图；写代码不算算数，出数才要 `approved` 的口径（施工计划第十三节公共规矩第 5 条）。

gyb 只想先看一眼图的时候不开分析单，走快车道，图落 `analysis/scratch/`，要引用或者复用的时候按正常路重做：补口径、开分析单重跑。analysis 的快车道没有合回补单这条路，只有 `rl ql close --dropped`（2026-08-17 gyb 裁，sync-inbox 问题 16），见 `07-quick-lane.md`。

## 和别的 part 的接口

- handoffs 账的公共骨架七样字段（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`）和 handoffs 的全部字段：`03-ledgers.md`。
- 口径账 `evaluations` 的行格式、四个状态 `proposed`/`approved`/`rejected`/`retired`、指标行和图行各自的必填栏：`03-ledgers.md`。
- 口径怎么提（`rl eval propose`、`rl eval update`）、analysis 先问 gyb 要统计什么：`13-role-analysis.md`。
- 口径怎么批和怎么打回（`rl eval approve ID... --quote`、`rl eval reject`），一句话批一组：`01-gyb.md`。
- 派活单七个状态的完整转移表、`holder` 的不变量、会话销号和 `rl reclaim`：`04-handoffs-and-sessions.md`。
- `rl handoff open/start/amend/stuck/resume/done/accept/reject/withdraw/release/reissue` 的完整参数、`rl inbox`、`rl status` 十段：`05-rl-cli.md`；`rl notify` 推送表：`01-gyb.md` 第五节（2026-08-17 gyb 裁）。
- issue 的九种 `kind`（这份用到 `cannot`、`withdrawn`、`orphaned`、`fyi`）、issue 的开与回与关：`03-ledgers.md`。
- gyb 是超级用户、`--as-gyb` 与 `--quote`、`--force --reason`：定义在 `01-gyb.md` 第二节（2026-08-17 gyb 裁）；钩子那一层在 `06-hooks-and-permissions.md`。
- idea 的全部 use case、`reads`、`ledger_writes`、`dispatches_to`：`10-role-idea.md`。
- analysis 的全部 use case、写权只有 `analysis/`、`reads`：`13-role-analysis.md`。
- 快车道 `rl ql open/close` 和 analysis 的轻路：`07-quick-lane.md`。
- 分析产物根 `analysis_artifact_root` 这个配置键：`08-trees-init-and-host.md`。

## 源文档没写清的（留给 gyb）

1. 分析单要不要 `decision_refs`。施工计划第三节只写了 `work_order` 必填至少一项、`launch_order` 开单时从父单抄，没写 `analysis_order`。连带的问题是 `line` 栏：`line` 由 rl 从 `decision_refs` 第一项的 `root_id` 算出来，分析单没有 `decision_refs` 的时候 `line` 算不出来，两条研究线并行时 `rl status --line L` 过滤不到分析单。
2. 分析单要不要 `explanation`。施工计划第三节写的是「`explanation`（`work_order` 必填；快车道补单由 deploy 写并含 gyb 点名原话）」，`analysis_order` 那一栏没写。
3. 口径引用的过版检查由哪条命令出。测试 5 写「口径引用同样查过版」，但是命令表里 `rl decision stale` 只写决定账，`rl inbox` 那一条只写「本会话手上单子引的过版决定」，`rl status` 段 6 也只写「过版的单子和 retired 决定名下的活单」。口径追加一版之后，引旧版的分析单由谁列出来、进不进 `rl inbox`，三处都没写。
4. gyb 在裸终端开的分析单，`dispatch=auto` 由谁去后台起 analysis subagent。转移表新建那一行写「`dispatch=auto` 时 owner 后台起 subagent」，这张单的 owner 是 `gyb`，裸终端里没有会话去起 subagent。
5. `output_paths` 记的是仓库内路径还是分析产物根下的路径。设计文档写「大文件进配置里的分析产物根并在口径行里记路径」，转移表又要求 `output_paths` 存在；大文件的时候 `output_paths` 填哪一个、rl 怎么查它存在，没写。另外 `output_paths` 的 `notebook` 是单值，一张分析单要交两个 notebook 的时候怎么填，没写。
6. 分析单的人工验收办法。工单的验收产物是两份部署报告，设计文档专门写了怎么读、按什么打回；分析单只写了「`output_paths` 存在、`evaluation_refs` 全部 `approved`」这两条机器前提，owner 拿到 notebook 和图之后按什么标准点头或者打回，没写。
7. 施工计划第五节 analysis 的 `ledger_writes` 里缺 `handoff amend`（见第六节末尾那条不一致），要不要补进去。

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

来源：`plans/2026-08-16-research-loop-simulation-round2.md`。那份文件开头写着：17 个核实者和 critic 全部因为月度用量上限没跑成，下面的摩擦全部是未经核实的模拟者原话，可能有误报。下面照抄，不做判断、不改字。

### plot-new-plan（17 步，gyb 动手 8 次）

1. [blocks/contradiction] 第 7 到第 10 步（提口径与开分析单的先后）：转移表规定 analysis_order 新建落 todo 的前提是 evaluation_refs 每项已 approved，但 analysis 的 use case 表把「接分析单」排在「问 gyb 要统计什么并提口径」前面，设计文档也写 analysis 先接单再问 gyb；一个全新的画图计划手上没有任何 approved 口径，照 use case 的顺序开单会被入账校验拒收，照转移表的顺序又要在没有单子的情况下先干活。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-build-plan.md:107; plans/2026-08-16-research-loop-next-steps.md:76; plans/2026-08-16-research-loop-next-steps.md:50
   - 改法：在设计文档 analysis 一节明写新计划的顺序是先开 analysis 会话过口径、口径 approved 之后再开分析单，或者改成分析单可以引 proposed 口径、到 handoff done 时才校验已 approved。
2. [slows/too_heavy] 整条路（第 1 步到第 17 步）：gyb 只想看一眼图，按文档要走 2 次 eval propose、2 次 approve、1 次 handoff open、start、done、accept 共 8 次写账，gyb 本人要介入 8 次；快车道只给 deploy，analysis 没有对应的轻路，和目标里「想法要快速、多次迭代」对不上。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：给 analysis 加一条 gyb 点名的快车道：图先落杂账不开口径不开单，图要被引用或复用的时候再补口径和分析单。
3. [slows/principle_violation] 第 10 步（gyb 开分析单）：违反原则 1。原则 1 写 gyb 在任何终端、任何角色会话里都能行使自己的权，任何权限检查不生效；但施工计划只让 gyb 豁免转移表「谁能写」一栏和「谁能调」检查，「前提」一栏照旧生效，于是 gyb 自己开分析单时被 evaluation_refs 必须 approved 这条前提挡住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:77; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：在施工计划第四节表头明写「前提」一栏对 gyb 生不生效，若生效就把它改称数据完整性校验、和权限检查分开命名。
4. [slows/contradiction] 第 17 步（结束会话）：设计文档说销号时检查这个会话作为 holder 有没有还挂在「开干」的单子，施工计划说 end 时扫 holder 是本会话的单子、有就拒绝，没限状态；转移表里 in_progress 到 done_pending_review 那一行又没写清空 holder，于是单子停在等验收时 gyb 想先关掉会话去看图会被拒绝下线。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:87
   - 改法：在转移表 in_progress→done_pending_review 那一行加「holder 清空」，并把销号检查明确限定在 in_progress 和 stuck 两个状态。
5. [slows/missing] 第 10 步与第 16 步之后的下一轮迭代：handoffs 的 decision_refs 每项带 {id, version}，evaluation_refs 只写编号不带版本；口径 approved 之后再追加一版，已经派出去的分析单引的是哪一版查不出来，过版检查命令 rl decision stale 也只覆盖决定账。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-next-steps.md:111
   - 改法：evaluation_refs 改成和 decision_refs 一样的 {id, version}，并让 stale 检查同时扫口径引用。
6. [slows/missing] 第 16 步之后（gyb 看完图想换个画法）：口径账只写了被打回之后 analysis 改了再提一版这条路，没写已经 approved 的口径能不能 update、update 之后 status 回不回 proposed、要不要重新批；也没有决定账那种「同一个问题换做法追加一版、换问题开新条」的判据。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:78; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:216; plans/2026-08-16-research-loop-next-steps.md:46
   - 改法：给 evaluations 抄一条决定账同款判据，并明写 approved 之后 update 一版就回 proposed、必须由 gyb 重新 approve。
10. [slows/ambiguous] 第 10 步（分析单的 from_role）：owner 被定义成开单角色也就是 from_role，而角色只有五个、gyb 不在角色表里；设计文档和词表都说 gyb 可以开分析单，但 handoffs 的 from_role 能不能填 gyb、gyb 算不算合法 owner 没有明写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:41; plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：在第三节 handoffs 的 from_role 字段写清取值是五个角色或 gyb，并说明 owner 是 gyb 时验收和拉起下游都由 gyb 做。
12. [cosmetic/missing] 第 13 步到第 14 步（图画完之后叫 gyb）：单子进 done_pending_review 只出现在 rl status 里，桌面通知只在 issue 改派给 gyb 的时候发；gyb 不坐在这个会话里的时候，得靠自己轮询才知道图画好了。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：把「等 gyb 验收的单子」也接进 rl notify，或者在设计文档里明写这一类只进 rl status、不通知。
13. [cosmetic/missing] 第 12 步（图和 notebook 落盘位置）：决定的来源里把 analysis/ 里的图当仓库内文件路径，init 又说原始数据走配置里的产物根；图和 notebook 进不进 git、多大算大产物要挪到产物根，两份文档都没划线。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：在 research-loop.json 里加一个 analysis 产物根，明写小图和 notebook 进仓库 analysis/、大文件进产物根并在口径行里记路径。

### next-plan-after-results（36 步，gyb 动手 16 次）

1. [blocks/contradiction] 第 20 步：销号时 holder 扫描的范围两处打架：设计文档说只查「还挂在开干的单子」，施工计划说「扫 holder 是本会话的单子」不限状态；同时转移表的 done_pending_review 和 accepted 两行都没写清空 holder，所以一张已验收的分析单会永远把 holder 挂在这个会话上，而逃生口 `--release` 只允许从 in_progress/stuck 走，analysis 会话按字面走关不掉
   - 依据：2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-build-plan.md:126; 2026-08-16-research-loop-build-plan.md:88; 2026-08-16-research-loop-build-plan.md:93
   - 改法：转移表在 done_pending_review、accepted、withdrawn 三行明写 holder 清空，`rl session end` 只扫 in_progress 和 stuck
2. [blocks/blocked] 第 11 到 15 步：analysis_order 新建的前提是 evaluation_refs 每项已 approved，但口径是 analysis 接单之后才提的（角色 json 的 use case 顺序是「接分析单 → 提口径」）。一批新结果第一次要新指标时，单子和口径互为前提；只能靠「gyb 直接开一个没有单子的 analysis 会话先提口径」绕过，而文档从没描述过没有单子的 analysis 会话该怎么交付 notebook 和图
   - 依据：2026-08-16-research-loop-build-plan.md:81; 2026-08-16-research-loop-build-plan.md:107; 2026-08-16-research-loop-next-steps.md:76; 2026-08-16-research-loop-next-steps.md:80
   - 改法：允许 analysis_order 引 proposed 口径开单、批准落在 done 之前，或明写「先谈口径后开单」并给无单分析会话一个交付落点
3. [slows/principle_violation] 第 14 步：违反原则 1。原则 1 和施工计划裁决 6 说 gyb 不受任何权限检查影响，转移表却只给 gyb 豁免「谁能写」一栏、不豁免「前提」一栏，于是 gyb 自己也开不出引未批口径的分析单、也收不了缺交付物的单子。两句话对「权限检查」的范围理解不一样
   - 依据：2026-08-16-research-loop-build-plan.md:77; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15
   - 改法：把原则 1 改写成「权限检查对 gyb 不生效，数据完整性前提对谁都生效」，并给 gyb 一个 `--force` 带原因写进账行
4. [slows/too_heavy] 第 1 到 36 步整条路：只是「看完一批结果定下一步」，gyb 亲自动作 16 次，其中光批口径就要按行逐条批、图口径还得先有指标口径两级批。设计文档开头写的目标是想法要快速多次迭代，每一条手续都要拿这两点衡量，这条路和那句话拉扯
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-next-steps.md:183; 2026-08-16-research-loop-build-plan.md:69
   - 改法：给「一批结果的例行复盘」开一条批量口令：gyb 一句话批一组口径（rl 记下这句原话展开成多行），图口径自动带上它 uses 的指标
12. [cosmetic/ambiguous] 第 12 步：派生量口径 approve 时 code_path 必须已存在，可公共规矩 5 又说派生量只用 approved 的口径；analysis 到底能不能为一条还没批的口径先写代码，两种读法都说得通
   - 依据：2026-08-16-research-loop-build-plan.md:69; 2026-08-16-research-loop-build-plan.md:249
   - 改法：规矩 5 补一句「写代码不算算数，出数才要 approved 口径」

### n-launch-orders（58 步，gyb 动手 10 次）

15. [slows/ambiguous] 第 48 步：跨 run 的聚合数算谁的活，两种读法都说得通。一种读法：idea 读九本账全部，runs 账的 metrics 就在里面，自己把 5 个数平均一下没人拦。另一种读法：规矩 5 说派生量只用 approved 的口径、由 analysis 算，均值方差正是派生量，idea 自己算就是自作主张。
   - 依据：2026-08-16-research-loop-next-steps.md:52; 2026-08-16-research-loop-next-steps.md:30; 2026-08-16-research-loop-build-plan.md:249
   - 改法：明写一句：单个 run 的 metrics idea 可以直接引，任何跨 run 的聚合一律走 analysis 分析单。
16. [slows/too_heavy] 第 50 到 54 步：口径要 approved 之后才能开分析单，而 approve 又要求 code_path 已经存在，于是同一件事要开两个 analysis 会话：先由 gyb 直接开一个没有单子的 analysis 会话把代码写出来，gyb 批完之后 idea 再开正式分析单让第二个 analysis subagent 重做一遍。5 个种子求个均值走完这一圈要 gyb 亲自动手三次。
   - 依据：2026-08-16-research-loop-next-steps.md:78; 2026-08-16-research-loop-next-steps.md:76; 2026-08-16-research-loop-build-plan.md:69; 2026-08-16-research-loop-build-plan.md:81
   - 改法：允许 analysis_order 引 proposed 的口径，把「已 approved」和「code_path 存在」两条前提一起挪到 handoff done 那一步校验。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

10. [blocks/blocked] 第 22 步：分析单和口径互为前提。新建 analysis_order 的前提是 evaluation_refs 每项已 approved，设计文档也写「单子里只能引已经批准的口径行」；而 analysis 的 use case 第一条是接分析单，接完才问 gyb 要统计什么、才提口径给 gyb 批。一批新数出来之后的第一张分析单永远开不出来。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-next-steps.md:50; plans/2026-08-16-research-loop-next-steps.md:76; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：把 evaluation_refs 每项 approved 这个前提从新建那一行挪到 in_progress→done_pending_review 那一行，新建时允许空。

### new-idea（39 步，gyb 动手 7 次）

12. [slows/ambiguous] 第 37 步：「拿到数字给 gyb 看」两种读法都成立：idea 读九本账全部，可以直接 rl run show 把 metrics 念给 gyb；可另一处写着任何角色不许自己写新的要分析的东西、要看什么 gyb 一条条说由 analysis 记账批准，照抄一个原始指标算不算分析没有界
   - 依据：plans/2026-08-16-research-loop-next-steps.md:52; plans/2026-08-16-research-loop-next-steps.md:30; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：明写「照抄 runs 账 metrics 里的原始数不算分析，任何对比、聚合、画图都要走口径账」
</content>
</invoke>

## 裁决记录（日期）

- 2026-08-17：来自 `04-handoffs-and-sessions.md` 的裁决（rl-hub 转来；gyb 原话「删了吧」「我想这个问题应该取决于再干能不能成功吧，如果是啥外部元素，重试能成功那可以再来，但是如果代码有问题得给代码先修了啊」）：抄的转移表 `in_progress` → `todo` 行「谁能写」删单列的 gyb，「之后谁拉起」改成 owner 照单子原来的 `dispatch` 拉起（`auto` 再起一个 subagent）。对回原则 8、原则 11、原则 3。
- 2026-08-17：来自 `04-handoffs-and-sessions.md` 的裁决（rl-hub 转来；gyb 原话「可以 发」）：gyb 越过 owner 打回也发 fyi，抄的转移表 `done_pending_review` → `rejected` 行前提栏补上。对回原则 6。
- 2026-08-17 gyb 裁（sync-inbox 问题 1，原话「这个归01吧」，rl-hub 转来）：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 定义处归 `01-gyb.md`。接口一节的指向照改。
- 2026-08-17 gyb 裁（sync-inbox 问题 2，原话「算一件事」「给rl notify指到01吧」，rl-hub 转来）：推送表和 `rl notify` 是一件事，定义处归 `01-gyb.md` 第五节；`05-rl-cli.md` 命令表只留 `rl notify --text` 的签名行，「rl notify」一节缩成一句指 `01`。接口一节的指向照改。
- 2026-08-17 来自 `05-rl-cli.md` 定稿（`656c8a9`）的裁决（rl-hub 转来；gyb 原话「全推荐」「只要他不动目前的代码什么的就全推荐就行」「全都推荐，只要不影响正在跑的进程」「A」）：抄的转移表 `in_progress` → `todo` 行补「销号钩子写的 `actor` 记会话角色、`via=session_end`；reclaim 写的 `actor` 记 gyb、`via=reclaim`」，与 `04` 一字不差。对回原则 4。
- 2026-08-17 来自 `05-rl-cli.md` 定稿（`656c8a9`）的裁决（rl-hub 转来；gyb 原话「全推荐」「只要他不动目前的代码什么的就全推荐就行」「全都推荐，只要不影响正在跑的进程」「A」）：`rl handoff done` 签名去掉 `--actual-seconds`。对回原则 8。第 41 行照改。
- 2026-08-17 来自 sync-inbox 问题 10 的裁决（定义处 `04`，rl-hub-v3 传；gyb 原话「A」）：第六节抄的转移表两条 `handoff amend` 行加「换 `evaluation_refs` 里的引用（doctor 悬空引用的修法）」，`done_pending_review` 那行改成「补或改 `output_paths` 里的路径」。
- 2026-08-17 来自 sync-inbox 问题 16 的裁决（定义处 `03`、`07`，rl-hub-v3 传；gyb 原话「A」）：第七节末句补「analysis 的快车道没有合回补单这条路，只有 `rl ql close --dropped`，要留就按正常路重做」。
- 2026-08-17 来自 sync-inbox 问题 20 的裁决（定义处 `04`，rl-hub-v3 传；gyb 原话「B」）：第五节和第六节抄的转移表 withdraw 行「有 holder 时通知」改成「从 `in_progress` 收回时通知，其他状态不通知」。
- 2026-08-17 来自 sync-inbox 问题 21 的裁决（定义处 `04`，rl-hub-v3 传；gyb 原话「A」）：第六节抄的转移表 reissue 行「到」栏由「同状态（接替）」改成「旧单 `withdrawn`，新单 `todo`（`supersedes` 指旧单）」。
- 2026-08-17 来自 sync-inbox 问题 28 的裁决（定义处 `01`、`05`，rl-hub-v3 传；gyb 原话「C」）：第二节「analysis 上线第一个动作是 `rl inbox`」改成「`rl inbox` 是查询命令，谁需要谁敲，不是上线动作：被派单拉起的 analysis 会话先干拉它起来的那张单」。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `03`、`05`，rl-hub-v3 传；gyb 原话「只有做完了的时候才关，巡检要我本人确认」）：第六节抄的转移表 accept 行按 `04` 第三节补「rl 顺带关这张单关联的 `answered` issue」。
