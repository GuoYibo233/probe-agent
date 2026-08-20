# research-loop 计划拆分：索引与进度（2026-08-16 夜）

两份源文档（`plans/2026-08-16-research-loop-next-steps.md` 设计文档、`plans/2026-08-16-research-loop-build-plan.md` 施工计划）按「一个角色一份、有交流的角色对一份、其余按要出的文件分」拆成 22 份，落在这个目录。写法铁律是只搬运不发明：源文档怎么写就怎么写，两处不一致的标出来不裁，题目里缺的东西写进每份末尾「源文档没写清的」留给 gyb，第二轮模拟里归到这一份的摩擦原样抄在最后一节。

## 进度

22 份里 21 份写完了，每份都有固定的五段（覆盖说明、正文、和别的 part 的接口、源文档没写清的、第二轮摩擦）。workflow 报了 13 个 agent 失败，失败的原因全是月度用量上限，但其中 12 个是把文件写完之后在最后一步返回摘要时才撞上的，文件本身完整（我逐个查了五段都在、末尾以最后一条摩擦收尾）。真正没写成的只有一份：`30-build-steps-verify-tests.md`（待验证十一条、测试十七条、施工步骤 0 到 8），2026-08-17 由主会话补写完。覆盖检查那个 agent 也没跑成，所以「两份源文档每一段都落进了某个 part」这件事没有机器核过；下面每份的「源文档没写清的」是各个 agent 自己写的。

## 每份一行

| 文件 | 标题 | 覆盖什么 | 行数 | 留给 gyb 的点 | 附的第二轮摩擦 | 状态 |
|---|---|---|---|---|---|---|
| `00-overview.md` | 总览 | 目标、十一条原则全文、九条裁决、（a）到（i）待裁改动、没采纳的九条、改掉的十六条、两轮模拟说明、这套文档的索引 | 316 | 7 | 18 | 已定稿 `6ea0edc`（2026-08-18，rl-part-00；六条同步事项 rl-hub-v4 已传） |
| `01-gyb.md` | gyb 自己做的事与收件箱 | gyb 亲自做的七件事、身份规矩、gyb 的 use case 表、rl status 十段、推送表、定期提醒 | 485 | 8 | 约 80 | 已定稿 `cd569ab`（2026-08-21，rl-part-01；同步事项 rl-hub-v5 已传，桌面通知与定期提醒都裁掉不做，动到冻结三份的记「冻结后待议」问题 40） |
| `02-decisions.md` | 决定账 | 六个文件、行格式、来源三类与锚点、编号版本、root_id 与 line、update/confirm/retire/merge、过版与 reissue、reviewer 基准按 actor、rl decision 子命令 | 383 | 8 | 29 | 已定稿 `7549704`（2026-08-18，rl-part-02；六条同步事项 rl-hub-v4 已传，动到冻结三份的三处记「冻结后待议」） |
| `03-ledgers.md` | 九本账行格式 | 总规矩、公共骨架七样、七本账的字段级行格式（decisions 指 02、handoffs 指 04）、退出码 | 462 | 9 | 约 60 | **冻结 `884ac0b`**（2026-08-17 gyb 定；定稿 `a5d05d4`，收问题 6–31 `81377ac`/`884ac0b`） |
| `04-handoffs-and-sessions.md` | 派活单与会话 | handoffs 行格式、七个状态与 holder 不变量、六栏转移表全文、三种 dispatch、交付物与验收人、销号钩子、sessions 账与 rl session、reclaim 全部规矩、三种通知 | 511 | 8 | 约 90 | **冻结 `9b78d7c`**（2026-08-17 gyb 定；定稿 `130ec90`，收问题 7–30 `a7d1ec9`/`cec2cc9`/`9b78d7c`） |
| `05-rl-cli.md` | rl 命令总表 | actor 判定、命令表全文、退出码与 --json、锁、inbox、trace、status 十段、reclaim、doctor 十九项、notify | 635 | 13 | 约 100 | **冻结 `77213e5`**（2026-08-17 gyb 定；定稿 `656c8a9`，收问题 6–31 `1b37593`/`2c965d9`/`2dcdd23`/`ddafd84`/`77213e5`） |
| `06-hooks-and-permissions.md` | 分权、钩子、角色 json | 三层约束、钩子拦放、回话指路、钩子绑角色、CLAUDE.md 三句、角色 json 五栏与五份内容、test_skill_refs、读的纪律 | 398 | 11 | 约 40 | 已定稿 `d430192`（2026-08-18，rl-part-06；十条同步事项 rl-hub-v4 已传，动到冻结 04/05 的两处记「冻结后待议」问题 35） |
| `07-quick-lane.md` | 快车道 | 进（ql open）、中间（deploy、analysis、GPU 走宿主）、杂账行格式、出（ql close 两条路、补单规矩）、在 status/reclaim/doctor 里的位置、阈值 | 270 | 10 | 约 30 | 已定稿 `7a01842`（2026-08-21，rl-part-07；同步事项 rl-hub-v5 已传，动到冻结三份的记「冻结后待议」问题 41，新公共规矩 rule-09 落 `09`） |
| `08-trees-init-and-host.md` | 两棵树、init、宿主对接 | init 建什么、research-loop.json 的键、阈值表全文、插件树、入口 skill、迁移、new1 宿主对接逐条 | 278 | 10 | 约 26 | 已定稿 `eb02403`（2026-08-18，rl-part-08；十二条同步事项 rl-hub-v5 已传，动到冻结三份的三条记「冻结后待议」问题 39，纪律句改法与 agent 定义母版流程立问题 38 等 gyb） |
| `09-common-and-feedback.md` | 公共母版、反馈账、issues、grants | common/ 四个文件、只引用不抄、公共规矩九条、rules_version、feedback 账、issues 账九种 kind 与 reply/close、grants 账 | 349 | 10 | 约 50 | 已定稿 `aaca3c9`（2026-08-18，rl-part-09；十条同步事项 rl-hub-v5 已传，动到冻结三份的五处记「冻结后待议」问题 37，retire 理由栏立问题 36 等 gyb） |
| `10-role-idea.md` | idea 角色 | 职责、use case 表、四栏、收件箱、决定落账、开工单、开分析单、验收打回、收回重派拉起、notes/ 与问 gyb 的条子、模型 | 398 | 11 | 约 55 | 已定稿 `96459b4`（2026-08-21 rl-part-10；获准机制砍掉等十一条全裁，传播 rl-hub-v6 已做） |
| `11-role-deploy.md` | deploy 角色 | 写权、报告与 code_paths、自决、宿主文件三条纪律、开发射单、后台起 run 与验收、卡住之后、补报告提验收、快车道里的 deploy、四栏 | 381 | 7 | 约 56 | 已定稿 `5e8dffa`（2026-08-21 rl-part-11；七条没写清全裁，传播 rl-hub-v6 已做） |
| `12-role-run.md` | run 角色 | 认领与整 batch、gpu-run 八阶段对照、探卡、smoke 与分步计时、发射、runs 三版、看门狗、四种失败、6a/6b、中断、四栏、和宿主的关系 | 384 | 11 | 59 | 在 `rl-part-12` 手上 |
| `13-role-analysis.md` | analysis 角色 | 写权与读、先问再提口径、口径两类四态、接单交活、卡住两条路、快车道、产物落哪 | 230 | 10 | 18 | 在 `rl-part-13` 手上 |
| `14-role-reviewer.md` | reviewer 角色 | 谁开、focus、审查基准、审三样、读的顺序、审哪一版、清单五栏、不开 issue、五栏 json | 211 | 10 | 16 | 在 `rl-part-14` 手上 |
| `20-pair-idea-deploy.md` | idea 与 deploy | 工单字段、开单、状态走法、验收、打回、收回与 cascade、reissue、issue 往返、过版、快车道补单指到 07 | 330 | 8 | 41 | 未开 |
| `21-pair-deploy-run.md` | deploy 与 run | attempts、父单与继承、开单、认领、smoke、发射与 runs、交付物、四种失败到 amend/resume、验收、相关转移行、中断、对账 | 361 | 10 | 约 59 | 未开 |
| `22-pair-idea-analysis.md` | idea 与 analysis | 谁开单谁接、单子上带什么、交活、验收打回卡住收回、相关转移行、原始指标与跨 run 聚合 | 194 | 8 | 18 | 未开 |
| `23-pair-run-analysis.md` | run 与 analysis | runs 账契约：config、metrics、data_path、run list 过滤、分组键缺失、trace | 184 | 8 | 16 | 未开 |
| `24-pair-analysis-deploy.md` | analysis 与 deploy | 只有一条 issue 通道 | 144 | 8 | 9 | 未开 |
| `25-pair-reviewer-idea.md` | reviewer 与 idea | review/ 文件格式、status 列清单、idea 怎么读、来源指清单、只经文件不经 issue | 131 | 7 | 8 | 未开 |
| `30-build-steps-verify-tests.md` | 待验证、测试、施工步骤 | 待验证十一条（含第 4、10 条已裁的状态）、测试十七条逐条附 2026-08-17 定稿后要加要改的用例、`05` 点名新加的测试 18 到 20、施工步骤 0 到 8、施工纪律四条 | 344 | 10 | 17 | 2026-08-17 补写（主会话亲写，收了 05 定稿留给它的三条；测试 9 里 grant 那句按问题 27 改，`01` 两处相反的句子标了不一致） |

「附的第二轮摩擦」一栏，标「约」的是 agent 没返回摘要、我按行式数的，可能多算几条。「状态」一栏由统筹 session 维护，取值三种：未开、在 `rl-part-NN` 手上、已定稿 `<commit>`（`30` 那份没写之前记「未写」）。

## 各份留给 gyb 的点（agent 写的原话，逐份抄在这里，方便一眼扫）

00 总览（2026-08-18 定稿时全部裁完，见 00 裁决记录）：parts 和施工步 2 的 ARCHITECTURE.md 什么关系；parts 和源文档谁为准；（a）到（i）被否掉时的回退清单；十一条原则彼此打架按谁；总验收怎么算通过；第三轮模拟跑不跑、手续量没再数；原则 9、10、11 没有第一轮语境下的对应条目。

01 gyb：use case 表和 status 段落没一一对上（收拾那行指段 6、7、9 但段 6 是过版）；status 段 2 没有对应 use case；推送表没写通知带什么字段；定时提醒备案没有第二条路；reclaim 和 doctor 的 --json 没写；gyb 点名 reviewer 审什么、看完清单的动作落哪；--force 能越过哪些前提；sessions.model 是 unknown 时用哪条命令补。

02 决定账（2026-08-18 定稿时全部裁完，见 02 裁决记录）：决定行落哪个文件三处口径（按 actor、按 id 前缀、落 actor 自己那本）；序号六个文件各排还是共用；stale 的 --all 不在签名里；confirm 算不算改版要不要打印；merge 后旧决定的 root_id 变不变；--with-runs 第一跳按哪个字段；有新证据的改版和口头改主意长得一样；锚点不校验是有意还是漏。另标两处原文不一致：文件落盘口径；发射单引不引决定。

03 九本账：schema_version 从几起怎么加；last_activity 落账还是内存；编号位数与序号起点、decisions 六文件序号；log_tail 存路径还是文本；verdict_text 哪版必填；applies_to 取值域；scratch 中间版 status；角色能不能用 --force；loop/ 进不进 git。

04 派活单与会话：rejected→todo 要不要 progress_note（字段表和转移表对不上）；销号时多张开干单是不是全交回；交回 todo 之后 dispatch 怎么算；last_holder 清不清；--session ID 关一个还活着的会话怎么办；last_activity 施工时定；in_progress→todo 那行为什么单列 gyb；gyb 越过 owner 打回发不发 fyi 两处不一致。

05 rl 命令（2026-08-17 定稿时全部裁完，见 05 裁决记录）：doctor 十八项只有三项写了修法、「修完归谁推」一条没写；sessions.model unknown 那项算不算第十九项；stale 的 --all；handoff done 的 --actual-seconds 和「rl 算」打架；session end 顺带的 release 账行 actor 填谁；notify 能不能手动调；推送表第 4 条在哪条命令里发现；看门狗读 rl 时 actor 算谁；--force 能不能越表外转移；锁超时多久；inbox/doctor/reclaim 的 --json；--ack 之后还报不报；在角色会话里跑 init 会怎样。

06 分权与钩子（2026-08-18 定稿时全部裁完，见 06 裁决记录）：相对路径怎么判、软链接算不算仓库内；共用一个钩子脚本还是各一份挂在待验证 2；idea writes 是无目录但仓库根放行；notes/ 那条在角色会话里等于永远 deny；会话状态文件谁清理、`${CLAUDE_PLUGIN_DATA}` 解析到哪；加载第二个角色 skill 会怎样；dispatches_to 谁查；reads 栏写法不统一测试 13 按哪种查；角色 json 改动算不算母版改动；denied issue 归谁；Bash 直写角色目录钩子看不见、纪律里没专句。

07 快车道：analysis 的 scratch 开张版填什么；快车道数字进不进 runs 两句打架（2026-08-17 已裁：不进 runs，问题 22）；补单报告目录名在拿到单号之前取不出来；补单要不要 code_paths 两处没说到一起；analysis 合回补哪张单；--from 转进快车道之后那张工单怎么走；gpu-runner 起来之后登不登记、run-id 和 track 谁填；merge 之后 worktree 和分支谁删；补的 decisions.deploy 来源填哪棵树的路径；scratch 行归哪条线。

08 两棵树与宿主：中断命令模板的键名；「本仓库跑法」的键与形状；「宿主台账清单」的键与 new1 要列哪几个文件；账路径可配置和词表写死的文件名谁说了算；loop/ 进不进 git；脏树白名单在 run.py 里谁改、init 动不动；analysis/ 播哪几个模板文件；init 跑第二次；new1 之外的仓库 research-loop.json 怎么来；插件树要不要 workflows/ 或 agents/。

09 母版与反馈：SPEC-TEMPLATE 的五栏是哪五栏、和 reviewer 清单五栏是不是同一份；英文版措辞和 rule-NN 编号保持；retire 没有 --reason/--quote 而 rule-01 要求废除硬停带原话；target 指到施工计划某张表的某一行时填什么；doctor 那项的「文档」指哪份；feedback 被 reject 之后能不能改一版再提；run 的 reads 要不要补 feedback；通知类 issue 谁关（2026-08-17 已裁：`rl inbox` 只读不关，收件人做完了自己 close，问题 23）；rules_version 格式与同步；grant revoke 之后已加载的会话怎么办。

10 idea：ledger_writes 里的 release 和 amend 没有 use case 点名用；「重新拉起下游」是 rl 动作还是纪律；「怎么测试什么算成功」落在哪；explanation 写多长；一张工单引两个根决定时 line 怎么算；验收要不要读 code_paths 的代码；读完 review/ 之后做什么动作；request issue 谁 close；等 gyb 回话期间会话干什么、销号后谁叫起 idea；后台起 subagent 具体怎么起（待验证 8、9）；--manual 的单子 gyb 接完谁验收。

11 deploy：报告目录名怎么拼（快车道补单更取不出）；track 从工单继承但工单没有 track 栏；code_paths 含不含宿主文件；后台起 run 用什么机制、N 张单怎么把单号和 batch 交给 subagent；自决来源在 worktree 里填哪棵树；deploy 跑 doctor 看到自己名下报告路径没了开 issue 给谁；收回之后 experiments/ 里的代码和半截产物怎么处置。

12 run：reads 没有 decisions 但 ledger_writes 有 decisions.run add；认领怎么接管 tmux 和看门狗；整 batch 时 N 份分片的 host 和 gpus 谁分、写哪；scale_factor 按什么取；smoke 用哪张卡、smoke 日志谁清理；看门狗状态文件路径格式与读的间隔、run 会话死后看门狗谁停；「一张卡一个 run 的例外」账上怎么表达；认领之后要不要重跑 estimate；anomaly issue 的 handoff_id 必不必填；认领和 --batch 撞一起。另标一处不一致：四种失败一律给 deploy 与 anomaly 归 gyb，按施工计划第七节取后者。

13 analysis：开给 deploy 的 issue 填哪个 kind；analysis 快车道 scratch 开张版填什么；analysis 合回补哪张单谁验收；analysis 的自决是什么；eval retire 谁能调；口径 add 还是 update 没判据；没有分析单的会话怎么交付；ledger_writes 有 issue reply 但没人开 issue 给 analysis；两个 notebook 怎么填。另标一处不一致：analysis 的 reads 两份少三项，按施工计划表。

14 reviewer：谁去起 reviewer 的 subagent（没有 dispatches_to 指向它）；审一批时文件名怎么起；focus 一次只收一个、审完清不清；文件名里编号带不带版本；中途卡住怎么落；自决留痕记什么；analysis 的 notebook 和图按哪一版审；头部记不记工单编号；reviewer 拿什么核对读的纪律。另标一处不一致：只由 gyb 手动开与 as_subagent 是 fable。

20 idea 与 deploy：deploy 卡在工单上时 issue 归 idea 还是 gyb；普通工单 parent_id 填不填；转移表 amend 两行的「到」栏和「状态不变」对不上；reissue 继不继承 report_paths 和 code_paths；「怎么测试」落哪；打回后重新交活旧路径留不留；收回之后代码和产物怎么处置；正文里快车道那句指的是 07 不是题目里写的 22。

21 deploy 与 run：发射单带不带 decision_refs 两处不一致（2026-08-18 已裁：从父单抄 decision_refs，02 定稿）；actual_seconds 谁算（2026-08-17 已裁：`rl run finish` 算、rl 抄进发射单，`handoff done` 不带参数，问题 13）；adopted 标在哪一栏（2026-08-17 已裁：handoffs 的 start 版和 runs 的 adopted 版两边都标，问题 17）；amend 新尝试的 run_id 重不重新分；args 和 command 的分工；整 batch 时 host 和 gpus 怎么分、start --batch 是不是一次全置 in_progress；后台起 run 的机制；reject 之后要不要 amend；deploy 验收发射单看什么、什么时候 reject 一张 ok 的；认领怎么接管看门狗。

22 idea 与 analysis：分析单要不要 decision_refs（没有就算不出 line）；要不要 explanation；口径引用的过版检查由哪条命令出；gyb 在裸终端开的分析单谁去后台起 analysis；output_paths 记仓库内还是产物根、大文件怎么查存在、两个 notebook；分析单的人工验收办法；analysis 的 ledger_writes 缺 amend；（e）待裁（2026-08-18 已认，00 定稿：分析单开单时口径可以是 proposed，交活才要全 approved）。

23 run 与 analysis：data_path 指什么、和 artifact_dir 差在哪；failed/killed 要不要 data_path；run list 的 --line 和 --decision 怎么解析（runs 行没这两栏）；默认过滤两个条件的先后；config 其余键没有命名规矩；metrics 键名谁定谁保证同名同义；快车道数字进不进 runs 两处不一致（2026-08-17 已裁：不进 runs，问题 22）；doctor 五项只有一项写了修法。

24 analysis 与 deploy：issue 填哪个 kind；要不要把分析单标 stuck；deploy 修完谁把分析单交回待干（analysis 没有 resume）；反方向没有通道；「代码问题」的范围含不含公共统计件；analysis 怎么看到实验代码（reads 没列 experiments/）；要不要附证据；deploy 改完之后已跑出来的数字算不算。

25 reviewer 与 idea：审一批时文件名；清单里的问题条没编号锚点指什么；idea 怎么知道有新清单（inbox 没这一项）；status 段 9 扫目录还是另有登记；清单没有状态没有关掉的办法；建议动作被否掉往哪写；idea 按清单改决定要不要先等 gyb 点头。

30 待验证、测试、施工步骤：doctor 十九项只有第 3、19 项有测试用例；测试 5 口径过版由哪条命令出；测试 12 第二条 amend 分不分新 run_id；测试 13 按 reads 哪种写法查；待验证 8 备案要的 workflows/ 或 agents/ 层步 1 建不建；待验证 9 两层嵌套没测；步 3、4 工单怎么切对应哪些测试；步 8 不加载 skill 的 agent 用什么模型；运行期改母版跑全套测试还是只跑测试 13；新加测试 18 到 20 归步 3 还是步 4。另标一处不一致：测试 9 的 grant 那句按问题 27 改了，`01` 两处当时仍写角色会话 `--as-gyb` 写 grant 拒收——2026-08-17 rl-hub-v3 传问题 27 时已把 `01` 那两处改成「角色会话里 `--as-gyb --quote` 替 gyb 写也收」，不一致已消。

## 还没做的

- `30-build-steps-verify-tests.md`：2026-08-17 已补写，留给 gyb 十条在那份末尾。
- 覆盖检查：两份源文档每一段是不是都落进了某个 part、part 之间有没有互相打架、有没有发明源文档没有的规矩，没有机器核过。
- 三份源文件（设计文档、施工计划、这个目录）已 commit：`601f835`（2026-08-16 夜）。
