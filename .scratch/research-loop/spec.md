# research-loop plugin — 设计 spec（v2 内核版）

**Status:** needs-triage
**日期：** 2026-08-13
**沿革：** brainstorming 定稿后经十六轮修订收敛（五轮初审 → 用户批注 19 处 +
四裁决 → 九轮对抗复验（硬伤 28→3）→ 保真审计三件 → 用户裁决第二批八条 +
快车道 + 重构令）。全程记录、每轮发现与全部自决点见 `audit-merge.md`。
v2 按用户重构令把 v1（git 历史 `643cb94`）拆成**散文内核 + 结构化表**，
并执行"减防御性设计"指令（裁掉的条目见 audit-merge 第十七轮自决点）。
第十八轮：两份外部评审（`review/`）经多 agent 逐条裁断后落地——
111 条裁断、15 项采纳、34 项驳回，全程与再裁剪见 audit-merge 第十八轮。
**形态：** 机器级 plugin（跟机器走），工程铁轨通过仓库根配置文件挂接。

## 0 一句话

把研究循环（谈 idea → 定原则 → 定工程目标 → 施工 → 跑实验 → 故事裁决 → 写作）
做成一套分层的 plugin：三层干活、四信道通信、判据闸门把关、
结构化账本沉淀、一个独立监察面供用户亲验一切细节。
**上下文是一等设计对象**：任何会话只见与其层、其阶段相关的内容
（隔层=§1，隔时间=R10，读法=§2.1），不给 agent 无关上下文。

## 0.5 本文档的结构（元规则，spec 自身的立法法）

十五轮复审的头号缺陷类是"同一份封闭清单在两处成文，改一处漏一处"。
v2 用结构堵死它：

1. **封闭清单只成文一次**，全部住在 `tables/` 五个数据文件里；散文引用不复述。
   （表自 2026-08-13 实施起随 plugin 本体住仓库根 `research-loop/tables/`，
   spec 与实现共用这一份，spec_lint 指向同处——自决点 #139。）
   - `tables/ledgers.json` —— 账本清单：路径、格式、归属、读法类、轮转上限、活跃行判定式
   - `tables/rows.json` —— 行结构与枚举：各账字段、发射单、RUNMETA、报告头、结构化输出契约
   - `tables/writes.json` —— 写权规则：owner 值域、写入两式白名单、跃迁规则、撤销规则、维护动作豁免
   - `tables/config.json` —— research-loop.json 键表：值域、null 锁什么、兜底件
   - `tables/routes.json` —— 路由表
2. **一个字段/枚举只有一个归属表**；例外必须登记在被豁免规则所在的表条目里。
3. **一物一名**：专名全文只指一物（"注册表"只指 registry_cmd）。
4. **spec 改动交付前 `python3 spec_lint.py` 必须全绿**：lint 机械校验散文与表
   一致（旧枚举、路由表复述、生造字段）。一致性检查是确定重复的活，
   从此不再派 LLM 复审轮去人肉扫（吃 spec 自己的 R7/I12 药）。
5. 这些表不是脚手架：实施时 plugin 的 `schemas/*.schema.json` 与 owners 默认表
   由 `ledger.py gen-schemas` 从表**单向生成**（表 → 生成物），路由薄壳直接引用表，
   spec 与实现共用一个真源。生成物禁手改——改表再生成；生成器键序固定，
   重复生成逐字节相同；生成物与表不一致以表为准，由 `gen-schemas --check` 拦下
   （检查面只含 plugin 携带的默认版，工程覆盖件不入比对）。

## 1 三层 + 监察面

层按**指挥权**切，每层只管自己的，跨层只认信道上的落盘文件。
每层的写权账本、每本账的归属见 `tables/ledgers.json` 的 owner 列
（owner 值域与例外规则见 `tables/writes.json`）。

| 层 | 干什么 |
|---|---|
| idea 层 | 对用户的主对话层：谈想法、定原则、裁决什么进故事、批准计算 |
| 部署层 | 代码主场：原则 → spec → 工单 → 代码（review/测试在此）→ 发实验 → 收数字 |
| 运行层 | 机械执行：跑命令、落日志、钉版本；长期运行，上下文必须短 |

**层纪律**（各层 SKILL.md 骨架写死）：

- **idea 层**是与用户交流的唯一主层，对上行到用户的一切内容的准确可信负责；
  读实验结果（经批次报告与查询视图）与用户讨论。它的下行产出是**原则**；
  "这轮做什么"由部署层拆进 spec、用户在 spec 文件头批准（§8 步 3；
  用户 2026-08-13 确认此口径）——工单由部署层照 spec 开，idea 层不直接开工单。
- **部署层**是代码主场：向下交"怎么跑"（发射单），向上交"怎么读"
  （批次报告头部 `how_to_read`）；运行层升级上来的 bug 回此层修。
- **运行层**零代码写权——发现代码问题只能开待决账条目上报部署层；
  交给它的任务必须一张发射单说清，只跑不解释。
- **会话身份**（用户裁决 2026-08-13）：层身份不由会话自己判断，只在两个
  入口定死——用户触发某层 skill（含经路由句转入，`tables/routes.json`），
  或派发 subagent 时由派发方在派发契约里钉死。身份定下后整个会话不变，
  只加载本层 SKILL.md 骨架（`--layer` 取值见 `tables/writes.json`
  layer_param）；干到一半需要别层的活，走跨层传输（下一条），不许就地换层。
- **跨层传输**：载体可以是 subagent 派发或新开会话，但消息本体必须是落盘
  账本条目（或其引用）——subagent 只是送信的腿，信在账里。
- **代笔分野**：写权说的是账本内容的归属层，不是脚本入口。jsonl 账一律由
  确定性脚本代笔（R7）；md 定稿件由归属层会话直接编辑，机验事后把关
  （principles-lint/trace_check/evidence_lint 按件对号）；
  小 json 单件逐件归口——发射单走 ledger.py，error_classes/schemas/ 归属层
  会话直编（机验交 error_classify 自测与 schema 校验），jobs/RUNMETA 归铁轨
  与发射器代码，research-loop.json 归用户/主会话。
- **读权同样走脚本**（R7；只约束三层，监察面豁免见下）：哪类账怎么读，
  完整对照是 `tables/ledgers.json` 的 read 列（四类读法的定义在同文件
  `_read_classes`）。jsonl 账不许整文件读进上下文，只许
  `ledger.py query` 拿最小视图，默认只出活跃行。

**监察面**不是层：不在指挥链里，谁也不指挥、只读一切（所有账本+代码+原始输出），
对各层账本零写权；落盘只有 `reports/`，外加作为参与方往待决账开条提问、
往反馈账追加建议（这两个口子归**监察会话**，不给 inspector agent）。
唯一产出是给用户的证据报告。监察必须用独立上下文，
做事的会话不许自查顶数。

- **读法豁免**：监察面（inspector 与监察会话）是"只读一切"的成文含义——唯一允许把账本任意切片
  全量读进上下文的场合；query 为此提供 --batch/--run/--spec-item/--since/
  --metric 与 --all-rows/--include-archive 维度。R3 报告的全量扫描陈述由此支撑。
- **部署收官例行核查**（部署层 SKILL.md 收官段写死的规程步骤）三步闭环：
  ① 批次报告落盘后派 inspector（模型取 roles.inspector_model），派发契约成文——必传 batch_id、
  批次报告路径、research-loop.json 路径、机验三件套命令
  （trace_check、evidence_lint、verify_report）；核查范围由批次报告头部
  run_ids/spec_items 定位——批次报告是落盘物，派发因此仍符合"信在账里"；
  ② inspector 跑三件套并**通读**本批账目与报告（用户裁决：每次都通读——
  本工程策略值，落 research-loop.json inspection_policy=always），
  核查报告落 reports/，头部带 verdict 字段（取值见 `tables/rows.json`
  inspection_report_header）；blocker 只写流程缺陷与证据缺陷（断链、缺命令、
  口径对不上），不写科学结论（R2）；
  ③ 部署层会话读回：有 blocker 逐条转录成 blocked 条目（from_layer=deploy，
  溯源靠 evidence 指核查报告；to_layer 向上取到最近可答复层）且本批不算收官；
  无 blocker 才收官，核查报告路径回填批次报告 `inspection_report`，
  收官段末跑 `trace_check --closeout <batch_id>` 过非空门禁。
  转录 blocker 不算自查顶数：判定发生在 inspector 的独立上下文里。
  快车道批（§2.6）不触发本核查。
- **监察面自有记忆** = `reports/inspector-notes.md`：跨次核查的线索记这里；
  各层不读它、不依赖它。

**解读不过层**：上行只有事实，一切解读发生在 idea 层、由用户拍板。
派生量计算是 idea 层活动（R4，口径预授权的成文在 R4）；部署层只跑既有机械汇总管道。
**悬案攒批上报**：一层撞到多个不确定点，把手头任务扫完、一次性开一批
待决账条目，不许问一个等一个。问题走待决账楼梯，不报给监察面——
监察面看得到一切，但不做路由节点。

## 2 信道

| # | 方向 | 体裁 | 规矩 |
|---|---|---|---|
| 1 | idea → 部署 | 原则文档 + spec | spec 每条指回 principle_id；指不回去 = 原则有缺，先回 idea 层补 |
| 2 | 部署 → idea | 数字账、批次报告、待决账条目 | 报告零解读；原则缺口/代码抉择点停手，写 open 条目进待决账 |
| 3 | 部署 → 运行 | 注册表命令、**发射单** | 不在注册表不许跑；**脏树一律拒发并升级部署层**（豁免清单在配置）；产物钉 RUNMETA。工单是部署层层内物，不跨层下发 |
| 4 | 运行 → 部署 | 日志、RUNMETA、台账、采样器判定（进台账，`tables/rows.json` jobs_min_additions）、待决账条目（故障升级） | 升级必须带证据：错误原文、日志路径、已试动作表 |

**会话开工必读**（每层 SKILL.md 骨架写死）：开工跑一条
`ledger.py status --layer <本层>`，输出三块——① 本层工作面（在办事项：
发射单已写未发、run 跑完未入账、批次待报告/待核查等，字段与逐项派生源见
`tables/rows.json` status_view）；② 本层待决队列（open 且 to_layer=本层 +
answered 且 from_layer=本层，都算未决）；③ 有效授权视图（定义见
`tables/rows.json` decisions_row）。三块全是跨账本派生的动态视图，
不落盘、不建状态文件，只出活跃条目——"用完即清"靠视图过滤实现，不删账。

总规矩：**可追溯链双向**（正向：工单→spec→原则条目；反向：run→发射单→工单，
靠 RUNMETA.launch_order_ref 与台账回指；抉择→run 靠发射单 decision_refs）；
**升级走楼梯不跳层**；**一切通信落盘，不走会话记忆**；
**所有账本对所有层可读，写权按 `tables/ledgers.json` owner 列独占**
（例外规则在 `tables/writes.json`）。

### 2.1 账本读写纪律与回收

上下文卫生的主手段是**读法**，不是删账：污染上下文的不是文件大小，
而是把整本账读进会话（用户裁决 2026-08-13：读走脚本为主、归档为辅）。

- **查询口（主）**：jsonl 账只经 `ledger.py query` 读；默认视图只出活跃行，
  逐账判定式在 `tables/ledgers.json` active 列。`query runs` 必须带过滤，
  无过滤拒绝返回全表——读全量走渲染产物（RESULTS）。
- **工作面视图（status）**：跨账本派生的在办清单，只出计数、id 与路径，
  不出行内容；字段与逐项派生源见 `tables/rows.json` status_view；纯只读，
  不落盘、不建状态文件。跨账对不上只列进 inconsistencies[]，不推断阶段、
  不自行修补——要么按 R8 开待决条，要么跑 trace_check/doctor 深查。
- **读手 subagent（辅）**：非结构化材料需要摘要时派小读手（模型取
  roles.reader_model，一次一件），主会话只收摘要 + 原件路径。
- **归档轮转（辅）**：jsonl 账到行数上限（`tables/ledgers.json` cap 列，
  工程经 ledger_caps 覆盖）时 `ledger.py archive` 把非活跃行原样搬进
  `<name>.archive.jsonl`（同 schema、逐字节不改），伴生索引
  `<name>.archive.idx.json`；主文件不引入任何新行型。archive 的豁免地位、
  三条搬运机验与并发规则见 `tables/writes.json` maintenance_exempt。
  归档由 doctor 建议、用户确认后执行，不自动跑。
- **校验/追溯脚本一律跨档读**：trace_check、verify_report、regression_check、
  spotcheck 与 story/runs 写入时的存在性校验默认等价于 `--include-archive`；
  只有面向会话上下文的 query 默认只出活跃行。撤销与更正的就地更新同样跨档
  （写入侧唯一跨档口，规则见 `tables/writes.json` form2）。
- **append-only 的实义**：任何行永不删丢、事实字段永不改写——就地更新只有
  `tables/writes.json` form2 白名单那几个字段。
- md 账不轮转、不设体量机制（v2 裁员）：整理由写权层会话或用户看着办，
  整理时原文另存 `<name>.archive.md`、主文件留指针，原文永远留档。

### 2.5 人的位置（idea 层顶端）

用户本人是 idea 层的顶端，一切判断的终点。

**下行（你 → 系统）不设体裁**（用户裁决 2026-08-13）：你怎么说都行，
不用套任何格式。会话负责把你的话转录落账；五类**转录路径**——约束的是
转录的会话，不是你：

- **拍板**：原则定稿、spec 批准、故事裁决、待决条目答复——落对应账本带日期；
  spec 批准的转录是机械动作：你拍板当场跑 `ledger.py approve-spec`，一次落
  approved_by/approved_date/approved_digest 三字段，会话不手填 digest；
  待决答复由当场会话代笔（answered_by 填 user）；
- **授权**：R4 计算批准、R6 自决授权——原话当场落抉择账
  （kind=grant，含结构化 scope 与有效期）；
- **撤销/更正**：任何已落账的拍板可收回。jsonl 两路（抉择账/故事账/待决账）
  走撤销代笔特例，md 两路（原则/spec 批准）由归属层会话改文件——
  全部规则（字段、原话强制、blocked 撤销后机械重开、superseded_by 来源）
  唯一成文在 `tables/writes.json` withdrawal_proxy 与 withdrawal_routes_md；
- **触发**：路由表（`tables/routes.json`）里的任何一句话；
- **打回**（批次验收阶段专用）：验收不过退回对应层重做，理由落批次报告头部
  rejections[]（用户原话转录，evidence_lint 豁免此字段）。spec/原则阶段的
  不批准不叫打回：不落 approved_by（草稿态即未生效）+ 悬案开待决账 open 条。

**落账定格**：聊天里产生的任何决定，生效前必须由会话转录落账——没落账的
决定不存在。硬边界单列一条：**凡涉及实验设定（模型、温度、采样、数据版本等）
的悬案，没有你的明说或有效授权覆盖，不许自行解决**——这是 R5 的明确适用范围。
**授权覆盖下自决了实验设定的，事后必须回报你**（用户裁决 2026-08-13）：
回报走 R6 自决清单——decisions 账里 decided_by=agent 的近期条目渲染成清单，
随下一次对你的汇报明列，不许静默；GPU<1h 常设授权（R5）下干的活同此回报。

**上行（系统 → 你）常用六类**（用户裁决 2026-08-13：**清单不闭**——常见的
按下面六类格式化，需要时可以报额外类别）：

- **提案**：计算提案（R4）、方案抉择（R5）——凡要你拍板的，必须以"提案+证据"
  形态到你面前，不许以既成事实形态出现；
- **证据报告**：R3 体裁（监察/观察/判据验收报告都是它的子类）；
- **抽查清单**：固定种子抽样直达路径 + 总体指纹；
- **待决队列**：blocked 渲染视图，你回来先看这个；
- **回归警报**：新批次数字与故事账 active claim 冲突时的清单（只报事实不判）；
- **数字账**：批次报告 + RESULTS 渲染。

六类管的是**入账物**的格式，不管汇报风格。汇报可以自由发挥、提框架外建议、
整类地报清单外的新形态。不变量只有两条：凡数字有据（R3），凡决定入账（R5/R6）。

**你不在场时**：只有有效授权内的自决与 R5 常设授权（GPU<1h）内的发射可以继续
（都照 R6 留痕、事后回报），其余一律停在待决账 open，不许"先做了再说"。

### 2.6 小实验快车道（用户裁决 2026-08-13）

探索性小实验专用通道：**一口气完事，平直快，复用已有基建**。
触发句"快试一下"（`tables/routes.json`）。

- **免的手续**：不开 spec 条目、不开工单、不出批次报告、不派收官通读。
  发射单允许缩减——spec_ref/issue_ref/decision_refs 可空、标 `quick: true`，
  run_id 归入 quick 批（命名规则见 `tables/rows.json` batch_report_header）。
- **不免的底线**（数字纪律，不是防御手续）：数字仍只经脚本入账（R7，
  禁止人眼读日志填数）；种子仍固定进发射单。发射仍走 rails.gpu——
  工程唯一发射入口不破。
- **与 R5 常设授权衔接**：预计低于一小时的快实验，部署层默认模式下也可
  直接发射，事后按 §2.5 回报条款向你明列。
- **结果的去向**：quick 行不得被故事账引用（story 写入校验拒）；要进故事，
  按正轨补 spec 条目重跑——以原 quick 发射单为模板生成正轨发射单：
  seed/dataset_version/argv/env_name/filter 逐字沿用，允许变的只有
  run_id/batch_id/spec_ref/issue_ref/decision_refs/expected_commit 与
  quick=false（`promoted_from` 指回原 quick run）。种子固定只是其中一项，
  沿用整张发射单才算重跑。快车道是试想法的入口，不是论文证据的入口。

## 3 十条硬规矩（全 plugin 通用）

- **R1 原则条目契约**：每条原则一行 md 表，列名固定（`tables/rows.json`
  principles_columns；机器可解析，lint 与渲染按列名定位）。
  **rationale 不许空**：用户口述原则没给原因的，idea 层当场追问，问不出不落档
  （principles-lint 查空）。**未接线态**：注册表未接线时允许 criterion_cmd
  暂空落档，但必须标【想法待定】；补上判据才可转【现状】/【已定要改】。
  **最近实测不手填**：判据每跑一次就是一次 run，进 runs.jsonl 带 principle_id，
  原则文档的"最近实测+日期"由渲染脚本自动回填。
  **判据必须轻量只读**（不占算力资源——不走 rails.gpu，部署层会话当场可跑）；
  要重算力的证据先按普通 run 跑出产物，criterion_cmd 吃产物路径做检查。
  写不出轻量判据的原则退回 idea 层重谈。
  **原则的批准是逐行事件**——用户拍板即落 status（§8 步 2），
  原则文档不设文件级批准戳。
- **R2 机验人判**：判据机器跑，最终判断人来下。机械检查一律脚本执行；
  agent 可以做三件事——判结构缺陷、按错误分类表归类故障（R8）、
  提带证据的 blocker（§1 收官核查）并把原始证据摆到用户面前。
  科学结论归用户：结果算不算数、进不进故事，agent 不得代下。
- **R3 证据体裁**：判据/监察/观察输出只许——计数、差异定位（分叉点原文并排，
  两侧各带路径+行号）、可点开的文件路径（带行号/记录号）。
  **支撑经验主张的数值**（计数、指标值、差异量）**必须配一条可直接粘贴执行的
  复现命令**，命令输出必须等于报告数字；溯源元数据（生成时间、git HEAD、
  账本行数与哈希、行号、记录号、路径）不逐项配命令，但必须能从所引文件
  机械读出——豁免面成文在 `tables/rows.json` evidence_lint_exempt。
  计数为 0 的否定性陈述必须附扫描范围全量清单与总行数。
  报告头带溯源块：生成时间、git HEAD、所读账本行数/哈希。
  "通过/没问题/符合预期"等散文结论词违禁；结构化枚举字段（核查报告头
  verdict，取值见 `tables/rows.json`）不算结论词，evidence_lint 按字段豁免。
  lint + 机械校验器双重把关（§4）。
- **R4 计算授权**：对数据只许忠实呈现原始值。派生量先提案——公式、分母、
  过滤条件、作用文件——用户批了才算。**批过的口径即预授权**：公式、分母、
  过滤条件、聚合层级已写进 spec 条目并经用户批准的，每批照算不再上桌；
  口径没写全的不算预授权，仍要提案；新增或改动公式、分母、过滤条件、
  聚合层级、缺失值处理，一律重新提案（§2.5 实验设定硬边界照旧）。
  算完连同命令附在结果旁（进故事账的记 derivation_command）。
- **R5 抉择点分模式处理**（用户裁决 2026-08-13：不写成铁的，看用户的决定）。
  先识别：施工撞到方案分岔，机械三问判定它算不算抉择点——会改变某条判据的
  输出吗？会引入原则文档没有对应条目的新约束吗？不可逆吗（耗大量算力时长/
  产物已被下游引用；**写产物盘（raw_data_roots 下的路径）本身不算不可逆**）？
  三问全否即施工自由度，
  直接干。**账本 schema 变更永远算第二问为是**。是抉择点的，按当下模式走：
  **默认（无覆盖授权）**——停手，写待决账，上桌等裁决；
  **授权自决**——你一句"这类事你自己定"当场落成 grant，scope 覆盖眼前分岔
  且未过期的，会话自决，照 R6 留痕 + §2.5 回报条款事后明列。
  **常设授权一条**（plugin 携带，无须另发 grant）：抉择点若只关系到发射
  算力任务且预计总时长低于 standing_authorization.max_expected_runtime_s
  （plugin 默认 3600 秒；以发射单 expected_runtime_s 合计），
  默认模式下也可直接干——照 R6 留痕（authorized_by 填 `spec-standing-gpu-1h`）、
  事后必须通知你干了什么。
  裁决后：ledger.py 把 answered 的 R5 条目同步生成一条抉择账 decision 条目
  （机械拼装规则见 `tables/writes.json` r5_choice_assembly）——这是抉择账的
  强制入账口，不许只留自由文本 answer。
- **R6 授权自决留痕**：只有有效授权（grant 的 scope 覆盖眼前分岔且未过期，
  或 R5 常设授权）才许自决；每个自决点写抉择账（decided_by=agent，
  authorized_by 指回依据）。
- **R7 确定性脚本化（写与读）**：账本写入、schema 校验、溯源检查、抽样、lint、
  渲染，一律脚本干；账本的读同样走脚本（§2.1）。LLM 只做需要判断的活。
  渲染产物不手改。**runs.jsonl 的数字只有两条脚本路径**（工程记账脚本与
  ledger.py runs-append）：普通实验经发射单 `metrics_cmd`，判据 run 经
  `criterion_cmd` 的结构化输出——**任何层禁止用眼睛读日志填数**。
  （派生量不进 runs.jsonl，走 R4 归故事账。）
- **R8 故障先自愈后升级**：失败先在本层职责与写权内按错误分类表处理
  （形状见 `tables/rows.json` error_classes；命中即得自愈动作或升级指令，
  脚本判不经 LLM）。没命中的（error_classify 输出 unknown）分层处理：
  **运行层不判**——只做机械动作，把错误原文、日志路径、已试动作表收齐开
  blocked 条目（kind=failure）升级部署层；归类判断由部署层（及以上）agent 做，
  动作在本层写权内就执行（顺手往分类表加行，答复 blocked 时注明），
  超出写权或拿不准照楼梯再升。解决了留痕；解决不了写待决账升一层
  （运行→部署→idea→你），带证据。禁止跳层、静默吞错、越权修别层的东西。
  "重跑一次输出仍空"必升级。
- **R9 skill 进化落账**：每轮循环收官，各层把"skill 哪里不顺、建议怎么改"
  写进反馈账。建议不自动生效：用户定期审（路由句"审一下反馈"），批准的才改
  skill 本体（进 git），驳回的记理由——审查以追加 review 行落账，
  只能由用户审查会话经脚本写。
- **R10 skill 正文按需加载**：SKILL.md 只放骨架（职责、信道、账本写权、
  开工必读、阶段索引），各阶段操作细则拆进 `references/<阶段>.md`，
  进到那个阶段才读。上下文隔离不只隔层，也隔时间。

## 4 组件结构（每层一件专责）

```
research-loop/                      # plugin 根
├── .claude-plugin/plugin.json
├── skills/
│   ├── research-loop/SKILL.md      # 路由薄壳：认阶段 → 转层（tables/routes.json）；
│   │                               #   直接转交铁轨前跑 config-check
│   ├── idea-layer/SKILL.md         # 谈idea规程、原则模板、故事裁决、R4、撤销转录
│   ├── deploy-layer/SKILL.md       # spec 体裁、工单化、R5/R6、判据验收、发射单、快车道
│   ├── run-layer/SKILL.md          # 运行层契约：发射单执行、错误分类、产物校验
│   └── oversight/SKILL.md          # 监察面：报告体裁、独立性纪律、抽查流程
│   （每个 skill 目录配 references/<阶段>.md，按 R10 按需加载）
├── agents/
│   └── inspector.md                # 只读监察员：写权限定 reports/、R3 体裁
│                                   #   （监察面参与共享账的两条口子归监察会话，
│                                   #     不给这个 agent，§1）；
│                                   #   frontmatter 钉 model: 取 research-loop.json
│                                   #     roles.inspector_model（plugin 默认 opus）
├── schemas/                        # 各账 + 发射单 JSON Schema（从 tables/ 生成，
│                                   #   plugin 携带默认版、工程可覆盖；
│                                   #   变更走 R5 + schema_version 递增）
└── scripts/                        # 全部确定性
    ├── ledger.py                   # 账本总入口：写入+校验+状态机+写权检查+渲染+查询
    │                               #   （子命令：query / status / config-check /
    │                               #    archive / principles-lint / runs-append /
    │                               #    init / freeze-legacy / feedback review /
    │                               #    发射单写入 / approve-spec / gen-schemas——
    │                               #    gen-schemas 从 tables/ 生成 schemas/ 与
    │                               #    owners 默认表，--check 只重生成到内存
    │                               #    逐字节比对不写盘，§0.5 第 5 条的机验落点）
    ├── trace_check.py              # (deploy) 溯源检查：正反链 + decision→run
    │                               #   （扫发射单 decision_refs + 抉择账 affects，
    │                               #    校验两者一致性）+ 批次收官门禁
    │                               #   （--closeout；quick 发射单豁免回指，§2.6；
    │                               #    判据缩减行改查 principle_id 在原则文档 +
    │                               #    criterion_cmd 在注册表）；
    │                               #   重算 approved_digest 不等报 approval_stale；
    │                               #   promoted_from 非空时比对与来源 quick 发射单
    │                               #   的沿用字段（seed/dataset_version/argv/
    │                               #   env_name/filter），不一致报错
    ├── output_check.py             # (run) 产物校验：expected_outputs 逐条比
    ├── error_classify.py           # (run) 错误分类：按分类表判自愈/升级
    ├── spotcheck.py                # (oversight) 固定种子抽样：直达路径清单+总体指纹
    ├── evidence_lint.py            # (oversight) 违禁结论词 + "有数字无复现命令"
    ├── verify_report.py            # (oversight) 机械校验器：路径 stat、摘录回比、
    │                               #   复现命令数值回比
    ├── regression_check.py         # (oversight) 新批次 vs 故事账 active claim 同口径
    │                               #   重比（--dry-run 只出 stdout 不落盘——避免
    │                               #    doctor 越权写 oversight 独占的 reports/）
    ├── doctor.py                   # (用户) 一键体检：拼装 config-check + trace_check +
    │                               #   evidence_lint + principles-lint +
    │                               #   regression_check --dry-run + 账本行数上限扫描 +
    │                               #   归档量汇报与归档建议 + 遗留 worktree 清单 +
    │                               #   半状态扫描（孤儿 decision：blocked_ref 指向的
    │                               #   blocked 无 decision_ref 回指；撤销中断：
    │                               #   blocked=withdrawn 但同步 decision 仍 decided
    │                               #   或缺重开条；affects 与发射单 decision_refs
    │                               #   不一致）——修复动作一律是重跑原命令；
    │                               #   工作面段直接调 status，不重复实现跨账本派生。
    │                               #   只查不动，报告只出 stdout（可选 --out 用户
    │                               #   指定路径），不写 reports/、不写任何账本目录；
    │                               #   代码检查不在范围（归 rails.build 会话收尾）
    └── fallback/                   # 默认铁轨兜底件三件（tables/config.json
        ├── registry.py             #   fallback 列与 _fallback_rule）；
        ├── launch.py               #   兜底三件同时充当 §9 plugin 自测的假铁轨
        ├── record.py
        ├── fake_experiment.py      # 只在自测用（--seed / --mode / --out），
        └── fake_metrics.py         #   经 registry.py 注册；不计入"九个脚本"计数
```

runs.jsonl 有且只有两个写入口，按行型分工：普通实验行走工程侧记账脚本
（record_cmd），判据缩减行走 `ledger.py runs-append`。两个入口加载同一份
runs schema、共用同一把文件锁。

plugin 本体一律用**英文**交付（SKILL.md、schema 字段说明、脚本报错信息；
中文 spec 是设计底稿）。plugin 本体是**通用层**：只要是"idea→实验"形态的
项目都装得上；项目特化全部收进仓库根配置 + 可覆盖 schema（§7）。

## 5 账本机制（结构在表里，这里只写机制）

行结构、字段、枚举的唯一真源是 `tables/rows.json`；写权、跃迁、撤销、
维护动作的唯一真源是 `tables/writes.json`。散文只写五段机制语义：

- **写入两式**：原子追加 + 白名单字段就地更新（都过 schema 与写权检查、
  都持文件锁）。防呆不是防伪——挡误用，不设防恶意冒报。
- **复合动作的中断一致性**：① 每个跨文件复合动作定死写序——先 append
  派生行，最后落那笔翻状态的就地更新（各动作的写序成文在
  `tables/writes.json` 的 _write_order），崩溃只会停在"旧状态"或
  "旧状态 + 一条孤儿派生行"，永不停在"新状态 + 缺派生行"；
  ② 每条机械拼出的派生行必带回指触发行的引用，重跑同一命令先按回指查重，
  命中就复用不再新建——**重跑即修复**；③ 半状态由 doctor 扫出（只查不动），
  修复动作就是重跑原命令。明写：不引入事务日志与 staging manifest，
  不提供自动重放与自动补齐。
- **待决账是贯穿信道 2/4 的双向体裁**。kind=r5-choice 承载 R5 抉择：
  开条必填 where/options，答复必传 --chosen，ledger.py 机械拼出 decision
  条目回填 decision_ref——answered_by≠user 的答复必传 --grant，这是 R6 的
  机验落点。撤销 answered 条自动机械重开新条进 to_layer 待办——
  问题不因撤销而消失，被收回的裁决不得保持生效。
- **判据 run 执行契约**：部署层会话只负责发起——执行与入账是同一个动作
  `ledger.py runs-append --layer deploy --principle <id>`：脚本按 principle_id
  从原则文档 criterion_cmd 列取命令（缩减行不存命令本体），代为拉起
  （shlex.split 后直接起进程、不经 shell）并计时，
  退出码/elapsed_s 由脚本自取，尾行结构化输出由脚本解析（契约见
  `tables/rows.json` structured_output_contract），会话不经手任何数字（R7）。
  判据一律轻量只读（R1）：不占算力资源、不过脏树发射门禁、不登台账、
  不写 RUNMETA。
  **只有退出码 0 且尾行解析成功才落行（status=ok）**——判据没跑成不算实测，
  "最近实测"不更新，按 R8 升级。
- **发射单与台账的顺序**：部署层写发射单（同一动作把 run_id 回填进
  decision_refs 所指抉择的 affects；decision_refs 是权威，affects 是物化索引，
  不一致以发射单为准，trace_check 校验一致性——发射单先落盘、affects 回填
  后写：affects 缺失只是索引缺失，trace_check 报出后由部署层重跑同一写发射单
  动作补齐，发射单按 run_id 命名、重写同路径幂等，不产生第二张）
  → 运行层铁轨读发射单发射并登记台账 → RUNMETA/台账
  回指 launch_order_ref。发射单=要跑什么（前瞻），台账=跑成什么样（后验）。
  同理 argv 是权威执行体、registry_task 是归属声明，两者不一致时写入直接拒
  （机验规则见 `tables/rows.json` launch_order）。
  **发射前批准门禁**：写发射单时 spec_ref 非空则校验该 spec approved_by 非空
  且 approved_digest 重算匹配，stale 拒发并升级；spec_ref 空的 quick 发射单
  豁免（§2.6），照 trace_check 既有豁免写法。
  超时判定用 expected_runtime_s × runtime_factor；"卡死"判定用 stall_thresholds，
  两者分工。seed 永不可变。

## 6 路由

路由表唯一真源：`tables/routes.json`（research-loop 薄壳的全部内容）。
表里一切动作都可随时手动触发，不限阶段列；路由句只是常用入口，不是白名单。
脚本名只在 routes.json 出现一次，上层 skill 与用户一律经路由句进，
不直接依赖脚本路径。

## 7 工程挂接（plugin 通用 ↔ 项目铁轨）

仓库根 `research-loop.json` 的键集、值域、null 锁什么、兜底件——唯一真源
`tables/config.json`。散文只写机制语义：

- **通用/特化分界**：plugin 本体不含任何工程专名，特化只发生在这份配置里。
  三分界：plugin 本体（层、账本、跃迁、溯源、批准、报告）｜rails.* 五键指向的
  工程铁轨与发射单契约（怎么探资源、怎么发射、怎么记账——这就是适配接口）｜
  research-loop.json 的策略值（常设授权阈值、角色模型、核查策略、豁免清单）。
  不新建目录层。
- **兜底**：裸项目四键指向 `scripts/fallback/` 即装上可用，项目长出自己的
  设施后换指；兜底最低必做项与"其余铁轨无兜底"见 `tables/config.json`
  _fallback_rule。兜底态溯源链不打折（run→RUNMETA→launch_order_ref 不断）。
- **init 挂接问卷**：`ledger.py init` 逐项问（注册表命令、只读列表命令、
  记账脚本、产物根、各铁轨、账本落点逐项确认），答案落 research-loop.json；
  没答的留 null，config-check 列成"null 键 → 被锁功能"对照——未接线的功能
  拒绝，不静默降级（执行者与时点见 `tables/config.json` _null_lock_rule）。
- 没有配置文件 = 工程未接线：铁轨动作与一切记账都拒绝，只有谈可用。
  接线第一步就是 init 问卷。
- **编号名字空间**：本 spec 的 R1–R10 只指 §3；工程侧自有编号是另一套。
  挂接后引用工程原则一律用 principle_id。
- 数据集清单挂 DATA.md（new1 侧加结构化表头：dataset_id/路径/生成 commit/
  行数/校验和/当前版本）。

## 8 端到端剧本（验收时走一遍）

1. "我有个想法" → idea-layer 陪谈，文献入 KNOWLEDGE_MAP（rails.literature）。
   产出候选假设。
2. 谈熟 → 写/改原则，每条过 R1。用户拍板。
3. 出 spec（含 acceptance/depends_on，文件头记批准）→ trace_check 全绿。用户拍板。
4. spec → 工单 → rails.build 施工。抉择点走 R5：三问识别、分模式处理——
   自决先查有效授权视图（status 的有效授权块）与常设授权（算力<1h），
   命中才自决并留痕（R6）、事后回报（§2.5）。
5. 部署层出发射单 → 冒烟 → 判据实跑（runs-append）→ 证据报告（R3）→
   evidence_lint + verify_report 过 → 用户亲验 → 批量发射走 rails.gpu
   （铁轨读发射单、登记台账、RUNMETA 回指）；output_check 防空产物；
   数字只经 metrics_cmd/criterion_cmd 入账。
   （小试新想法不走这套：说"快试一下"进 §2.6 快车道。）
6. 跑完 → inspector 观察报告（RUNMETA.outputs 读格式）+ spotcheck 抽查清单 →
   用户读原件。regression_check 对照故事账，冲突清单落 reports/。
7. 用户拍板进故事 → ledger.py story 记账（run 存在性 + status=ok + 非 quick）。
8. 回 1，或走 rails.paper，数字溯源对故事账。
9. 任意时刻"查 X" → inspector 顺账本清单挖到原始文件（runmeta_path→RUNMETA→
   outputs 字典）；"有什么在等我" → 待决队列渲染。新会话接手同此：
   开工跑 status 取工作面，不靠用户复述进度。
10. 收官：各层反馈进反馈账；"审一下反馈"走 R9 审查；部署收官例行核查走
    §1 三步闭环。全程失败按 R8 走楼梯。

## 9 验收标准

- 五个 skill + inspector agent + 九个脚本 + fallback 三件 + schemas/ 齐备
  （schemas 与 owners 默认表从 tables/ 生成），plugin 可安装、路由表可触发。
- **spec 自身**：`python3 spec_lint.py` 全绿是 spec 交付门禁（§0.5）。
- 每个脚本有可跑自测。重点用例（正例从略，只列拒绝面与豁免面）：
  - trace_check：断链报错；判据缩减行与 quick 发射单各按成文豁免不误报；
    --closeout 模式空 inspection_report 报错、平时不报；跨档读不报断链。
  - ledger.py story：run 不存在 / status≠ok / quick=true → 拒；
    撤销 → status+superseded_by。
  - ledger.py blocked：跃迁级写权（--layer 传错拒）、非法跃迁拒；r5-choice
    缺 where/options 拒、答复缺 --chosen 拒、answered_by≠user 缺 --grant 拒；
    同步 decision 机械拼装并回填 decision_ref；to_layer=user 特例强制
    answered_by=user。
  - 撤销：无用户原话拒；跨层代笔放行且留痕字段齐；撤销 answered 条同一动作
    机械重开新条（字段沿用、ref 指旧条、进 to_layer 待办）、其同步 decision
    同批置 withdrawn。
  - ledger.py grant：无结构化 scope 拒；过期/被 superseded 不进有效授权视图。
  - ledger.py feedback：review 行只收 --layer user；改写旧行拒。
  - ledger.py runs-append：--layer≠deploy 拒；退出非 0 或尾行非 JSON →
    不落行、升级。
  - ledger.py query：默认视图严格按 `tables/ledgers.json` active 列；
    query runs 无过滤拒。
  - ledger.py principles-lint：principle_id 重复 / applies_when 或 rationale 空 /
    【现状】【已定要改】条目 criterion_cmd 空或不在注册表 → 报错；
    【想法待定】criterion_cmd 暂空 → 放行（R1 未接线态）。
  - ledger.py archive：三条搬运机验全过、idx 一致、被引用行不搬、
    suggestion 与 review 同批、未确认不执行、收到 --layer 拒。
  - ledger.py freeze-legacy：两条迁移机验、重复执行拒、不收 --layer。
  - ledger.py config-check：null 键按 `tables/config.json` null_effect 列锁；
    owners 键集与 ledgers 不等报错；ledger_caps 违反 _cap_rules 报错；
    owners 值域按 `tables/writes.json` 九值收；init 产物直接过。
  - 快车道：缩减发射单入账正常、trace_check 不误报、story 引用 quick 行拒。
  - output_check：退出码 0 + 空产物 → empty-output，不得记 ok。
  - error_classify：三类特征各一条规则命中正确动作；无命中输出 unknown
    不猜，运行层只机械升级。
  - evidence_lint / verify_report / spotcheck / regression_check：
    违禁词、伪造计数、总体指纹变化、claim 冲突各能揪出。
  - doctor：单项检查件挂掉能正确汇总；只出建议清单不执行变更；
    三类半状态 fixture（孤儿 decision、撤销中断、affects 缺失）各能报出
    且不写任何账本。
  - **schema 与入账面**：schema 校验单入口——删任一 required 字段 / 塞不在
    rows.enums 的枚举值 / 违反 conditional 三种注入各被拒，且由同一入口拒
    （两个 runs 写入口、发射单写入、四本 jsonl 账写入共用）；失败信息格式
    固定 `<账名>.<字段路径>: <说明>`，必须带实际非法值。记账脚本：metrics
    尾行两项落两行、run 级字段逐字相同；metrics 空数组或非数组拒并按 R8
    升级；同主键 (run_id, metric_name, filter) 重复入账拒、判据行同 run_id
    重复拒、同 run_id 两行的 run 级字段不一致拒。regression_check：
    metric_names 为空的 claim 列入跳过清单，不报冲突也不静默漏掉；
    metric_names 指向不存在的指标则 story 写入拒。
  - **交付门禁与批准面**：ledger.py gen-schemas --check 全绿——生成器键序
    固定、重复生成逐字节相同、plugin 默认 schemas/ 与表一致（工程覆盖件
    不在检查面内）。trace_check 批准面：spec 正文改一个标点报 approval_stale
    且写发射单拒；只追 withdrawals[] 或只递增 spec_version 不报 stale；
    quick 发射单不受批准门禁影响。
  - **复合动作与恢复面**：answer-r5-choice / 撤销重开 / 记账三条命令各重复
    执行两次，实体数量与引用关系不变；三类半状态 fixture 重跑原命令后收敛
    到完整新状态；崩溃后只可能停在旧状态一侧或旧状态加孤儿派生行。
    不做进程 kill 注入，不提供自动重放与自动补齐。
    ledger.py status：同一份落盘账本连查两次输出一致（generated_at 除外）；
    四个断点 fixture（发射单已写未发/跑完未入账/报告未核查/批次未收官）
    各落进对应字段；批次报告引用不存在的 run_id 只进 inconsistencies[]，
    其余字段照常出、不推断阶段；全程不写任何文件。
  - **注册表与判据面**：写发射单——argv 前缀与 registry_cmd 不符 / 前缀后
    首个 token 不等于 registry_task / task 不在 registry_query 清单，三者
    各拒；registry_query 未接线时按 null_effect 报未接线、不放行。
    principles-lint 追加：criterion_cmd 含管道符或换行报错；首 token 前缀
    不等于 registry_cmd 或任务不在清单报错（与发射单共用一份"在注册表"
    判定）。evidence_lint 追加：元数据数字（生成时间、git HEAD、行号、哈希）
    不报"无复现命令"，经验数字缺命令必报；指标值与分母必须能由同一条
    metrics_cmd 或 criterion_cmd 复算。快车道转正面：promoted_from 指向的
    quick 发射单不存在则拒，沿用字段被改则 trace_check 报错，转正后的
    正轨 run 进故事放行。
- **plugin 自测（假铁轨）**：用 scripts/fallback/ 三件加 fake 任务
  （fake_experiment.py：--seed / --mode ok|fail|timeout|empty|bad-metrics /
  --out DIR，输出遵 `tables/rows.json` structured_output_contract），
  不碰 GPU、不碰外部服务，走通 §8 步 3→10 的机械链。九个场景：
  ① 正轨闭环：spec 条目→工单→发射单→fake run(ok)→RUNMETA/jobs/runs→
  批次报告→核查 clean→story 入账→trace_check --closeout 过；
  ② 快车道链：缩减发射单→fake run→runs 行 quick=true，story 引用被拒，
  且 trace_check 不因缺 spec_ref/issue_ref 报断链；
  ③ 同一 fake 任务按正轨重跑（新 spec 条目 + 完整发射单、promoted_from
  指原 quick run）→ 新 run 可进故事，两条 runs 行 value 逐字相同；
  ④ --mode empty → output_check 判 empty-output，runs 行 status=empty-output
  且 metric 三字段为 null；
  ⑤ --mode bad-metrics → runs 无新行、blocked 新增一条 kind=failure 且
  evidence 带日志路径；
  ⑥ 第一次 --mode fail、重试后 ok → runs 单行 status=ok，RUNMETA attempts
  两条俱在、第一条 argv 与日志路径未被覆盖；
  ⑦ spec 批准后改一字 → 写发射单被 approval_stale 拒；
  ⑧ 三类半状态 fixture 重跑原命令后收敛；
  ⑨ 新会话只跑 ledger.py status 即可接着干。
- 在 new1 挂接后，端到端剧本 §8 的 1-3 步（不动 GPU）真实走通一遍。
- **铁轨兼容承诺**：不改变 ticket-run/gpu-run/probe-pipeline/paper-write 的
  对外流程；new1 挂接的增量改动单列挂接清单进实施计划，已知七项：
  ① 发射器补写 launch_order_ref 等回指字段；
  ② record.py 改造成 §5 普通行入口——三件全是新增不是核实（现状已核实
  2026-08-13：record.py 写的是 ev=start/finish 两行事件流、写入路径无锁）：
  (a) runs.jsonl 文件锁从零新增（与 runs-append 同协议）；(b) 行型改造，
  旧事件流冻结为 runs.legacy.jsonl（`ledger.py freeze-legacy`，机验与豁免
  地位见 `tables/writes.json`；legacy 挂 ledgers.runs_legacy，owners=frozen，
  接线会话同批补齐两处键）；(c) recorded_at 等 §5 字段由 record.py 自动补齐
  （arm/filter/quick 从发射单透传，recorded_at 由脚本自动打不许手填）；
  ③ RUNMETA 增 outputs 字典与 attempts 数组；④ 发射器接受部署层给定的 run_id（需核实，
  大概率零改动）；⑤ registry_query 只读免门禁入口核实/新增；
  ⑥ METHOD.md 改造成 R1 条目表（列按 `tables/rows.json` principles_columns；
  rationale 缺的回 idea 层追问用户；挂不上判据的标【想法待定】）；
  ⑦ RESULTS.md 渲染器跟随②行型改造，并处理同 run_id 多行（一行一指标）
  的合并展示。
  每项过工程自检；任一项涉及流程改动，先回本 spec 走 R5。

## 10 不做什么（YAGNI）

- 不重写任何现有铁轨 skill 的内容，只路由挂接（增量字段见 §9 挂接清单）。
- 不做多研究线并行目录树（schema 已带主键，将来平移不返工）。
- 不做 web 界面；监察面产出是文本报告。
- 不做自动触发（hooks）；路由由对话触发。
- **后置不弃**（实施后按需拾起）：reports/ 与待决账的通知/时限提醒；
  下行"临时指令/补证请求"专用体裁；台账成本字段的可行性查询视图；
  监察会话只读性的钩子验证；归档的自动执行（用户批注"可自动"的诉求）；
  多资源适配器（local-process/scheduler/remote-service）、risk-based 与
  manual 核查策略、兜底件的高级功能——这三项有第二个使用者时再做。
- **archive 执行件整体排 v1.1**（用户裁决 2026-08-13：删过度防御、要快）：
  v1 只做行数到 cap 上限的告警（doctor 已有账本行数上限扫描）；
  archive 命令、归档索引、跨档就地更新随 v1.1 一并落地——设计已在
  `tables/writes.json` maintenance_exempt 与 §2.1 成文，届时不重谈。
- md 系统最终定形（哪些渲染到根目录、叫什么名）随实施定，不在 spec 锁死。
