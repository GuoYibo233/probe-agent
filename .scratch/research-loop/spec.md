# research-loop plugin — 设计 spec

**Status:** needs-triage
**日期：** 2026-08-13（brainstorming 定稿；同日五轮修订：四份分层隔离审核 → 修订一，
两份验收审核（覆盖核查 + 五场景重放）→ 修订二，复验十硬伤 → 修订三，
终验八硬伤 → 修订四，复验五硬伤 → 修订五。过程见 `audit-merge.md`。
同日用户批注 19 处 + 四项裁决（工单归部署层开 / 账本上限进配置 /
部署收官派 opus inspector 通读 / 读走脚本为主归档为辅）→ 修订六；
修订六过三份 opus 对抗审核（批注覆盖/机制一致性/隔离重放，38 条发现 28 硬）→ 修订七；
修订七过两份 opus 复验（逐条复核 3 残留 + 白手 14 新伤）→ 修订八；
修订八过两份 opus 复验（17 项 16 净 + 白手 11 新伤）→ 修订九；
修订九过两份 opus 复验（12 项 10 净 + 白手 12 新伤，4 硬 8 软）→ 修订十；
修订十过两份 opus 复验（12 项 11 净 + 白手 6 新伤，3 硬 3 软，含实读 new1
现状核实）→ 修订十一；
修订十一过两份 opus 复验（7 项 5 净 + 白手 11 新伤，5 硬 6 软）→ 修订十二。
用户 2026-08-13 定迭代上限：此后最多三轮。
第 13 轮（上限第 1 轮）：复验 13 项 10 净 + 白手 9 新伤（5 硬 4 软）+
三件保真审计（73 处设计级改动归因、意图 I1–I16 逐条核对、整体推演）→
修订十三；
第 14 轮（上限第 2 轮）：复验 12 项 9 净 + 白手 2 硬 2 软 → 修订十四；
第 15 轮（上限第 3 轮，最后一轮）：复验 6 项 4 净 + 白手 3 硬 3 软 →
修订十五按报告修复，**未再复验**（迭代上限已到），残留风险见 audit-merge）。
保真审计的裁决清单经用户 2026-08-13 逐条裁决（八条 + 快车道，原话记
audit-merge.md"用户裁决第二批"）→ **修订十六**：六处漂移全部转为用户确认、
下行体裁解除封闭、上行格式开放列表、R5 改双模式（NFS 写豁免、GPU<1h 常设
授权）、授权内自决加回报义务、新增小实验快车道 §2.6。
**形态：** 机器级 plugin（跟机器走），工程铁轨通过仓库根配置文件挂接。

## 0 一句话

把研究循环（谈 idea → 定原则 → 定工程目标 → 施工 → 跑实验 → 故事裁决 → 写作）
做成一套分层的 plugin：三层干活、四信道通信、判据闸门把关、
结构化账本沉淀、一个独立监察面供用户亲验一切细节。
**上下文是一等设计对象**：任何会话只见与其层、其阶段相关的内容
（隔层=§1，隔时间=R10，读法=§2.1），不给 agent 无关上下文。

## 1 三层 + 监察面

层按**指挥权**切，每层只管自己的，跨层只认信道上的落盘文件
（账本怎么读、怎么回收，见 §2.1）。

| 层 | 干什么 | 本层写权的账本（共享账 decisions/runs 列在其主责层，blocked/feedback 与 reports/ 见下方例外条与监察面条目；分工细则以例外条为准；合计与 §7 owners 键集一一对应） |
|---|---|---|
| idea 层 | 对用户的主对话层：谈想法、定原则、裁决什么进故事、批准计算 | 原则文档、故事账、TIMELINE、文献账（KNOWLEDGE_MAP） |
| 部署层 | 代码主场：原则 → spec → 工单 → 代码（review/测试在此）→ 发实验 → 收数字 | spec、工单、抉择账、发射单、批次报告、错误分类表、schema 目录（含 runs schema）、代码地图、数据集清单（DATA.md） |
| 运行层 | 机械执行：跑命令、落日志、钉版本；长期运行，上下文必须短 | runs.jsonl 普通行（按部署层定义的 schema 写入；判据缩减行归部署层，§5）、任务台账、RUNMETA、原始输出、集群慢变量档案 |

（挂接迁移可产生只读冻结件 `runs.legacy.jsonl`：不归任何层，owners=frozen
任何写入拒，§7/§9。）

**层纪律**（2026-08-13 批注定稿；各层 SKILL.md 骨架写死）：

- **idea 层**是与用户交流的唯一主层，对上行到用户的一切内容的准确可信负责；
  读实验结果（经批次报告与查询视图）与用户讨论。它的下行产出是**原则**；
  "这轮做什么"由部署层拆进 spec、用户在 spec 文件头批准（§8 步 3）——
  **工单由部署层照 spec 开**（用户裁决 2026-08-13），idea 层不直接开工单。
- **部署层**是代码主场：代码 review、测试都在此层完成；向下交"怎么跑"（发射单），
  向上交"怎么读"（批次报告头部 `how_to_read`：读数脚本 + 口径说明）；
  运行层升级上来的 bug 回此层修。
- **运行层**面向长期运行：**零代码写权**——发现代码问题只能开待决账条目上报
  部署层，不许就地改；交给它的任务必须清晰明确（一张发射单说清），只跑不解释；
  上下文保持短，不塞解释性任务。
- **会话身份**：每个会话开工第一动作是声明本层身份（--layer 取值由此而来，§5），
  声明后只加载本层 SKILL.md 骨架，别层细则一概不载。
- **跨层传输**：传输载体可以是 subagent 派发或新开会话，但消息本体必须是
  落盘账本条目（或其引用）——subagent 只是送信的腿，信在账里。这是
  "一切通信落盘，不走会话记忆"（§2 总规矩）的实现细则，不是它的例外。

- 写权说的是**账本内容的归属层**，不是脚本入口：jsonl 账一律由确定性脚本
  （ledger.py 等，R7；"注册表"专指 §7 registry_cmd，别混）代笔；
  md 定稿件由归属层会话直接编辑，机验交 principles-lint/trace_check/
  evidence_lint 事后把关；小 json 单件与工程台账逐件归口——
  发射单走 ledger.py 写入；error_classes.json/schemas/ 由归属层会话直接编辑
  （机验交 error_classify 自测与 schema 校验）；jobs.json/RUNMETA 由
  铁轨与发射器代码写（jobs.json 的读法归 §2.1 大体量类）；
  research-loop.json 写权归用户/主会话（§7）。读法分类另有口径，见 §2.1。
  任何层的会话都可以跑脚本，但脚本按 `--layer` 与各账写权规则收；
  kind=grant 明列收三层（§7 per-kind），授权原话因此可以
  在 idea 层会话里当场落进抉择账（audit D7 的定义澄清）。
- **读权同样走脚本**（R7 扩展到读；只约束三层，监察面豁免见其条目）：
  jsonl 账不许整文件读进上下文，只许 `ledger.py query <账本> [过滤]` 拿最小视图，
  默认视图只出活跃行；哪类账怎么读的完整对照在 §2.1。
  非结构化材料（旧批次报告、原始日志）需要摘要时才派小读手 subagent（sonnet）；
  结构化账本一律脚本直查——确定重复的活不派 LLM。
- **写权单层独占有四个成文例外**：待决账（跃迁级写权，谁能改哪个状态写死在 §5）、
  反馈账（append-only 共笔，条目带 layer 字段）、runs.jsonl（按行型分工：普通行归
  运行层经工程记账脚本，判据缩减行归部署层经 `ledger.py runs-append`，§5）、
  抉择账（按 kind 分工：kind=decision 直接写入只收 deploy——**例外：R6 自决
  留痕条目（decided_by=agent 且 authorized_by 指向有效 grant）收 idea|deploy|run
  三层**，授权自决在哪层发生就在哪层落账；kind=grant 授权原话三层会话当场代笔；
  监察面不在其内——它对抉择账零写权，见监察面条目；
  r5-choice 裁决的同步 decision 条目由 ledger.py 机械拼装自动落账，
  不算会话写入，§5）。除这四本外，一本账一个层。

- **监察面**不是层：不在指挥链里，谁也不指挥、只读一切（所有账本+代码+原始输出），
  对各层账本零写权；落盘只有两类——专用报告区 `reports/`，以及按上一条前两个成文例外
  作为参与方写共享账（往待决账开条提问、往反馈账追加建议）。唯一产出是给用户的证据报告。
  监察必须用独立上下文，做事的会话不许自查顶数。
  **读法豁免**：监察面（inspector 与监察会话）是"只读一切"的成文含义——
  唯一允许把账本任意切片全量读进上下文的场合；query 为此提供
  `--batch/--run/--spec-item/--since/--metric` 与 `--all-rows/--include-archive` 维度。
  R3 报告的全量扫描陈述（零计数附全量清单）由这条豁免支撑。
  **部署收官例行核查**（部署层 SKILL.md 收官段写死的规程步骤，非自动 hook，
  §10 边界不破）三步闭环：
  ① 批次报告落盘后派 inspector（opus），**派发契约**成文——必传 batch_id、
  批次报告路径、research-loop.json 路径、机验三件套命令（trace_check、
  evidence_lint、verify_report）；核查范围由批次报告头部 run_ids/spec_items 定位
  （批次报告是落盘物，派发因此仍符合"信在账里"）；
  ② inspector 跑三件套并**通读**本批账目与报告（用户裁决 2026-08-13：每次都通读，
  不只跑脚本；读法走上条豁免），核查报告落 reports/，头部带
  `verdict: clean | blockers[]`；
  ③ 部署层会话读回核查报告：有 blocker 必须逐条转录成 blocked 条目
  （**from_layer=deploy**——写入者是转录的部署层会话，溯源靠 evidence 指
  核查报告路径；to_layer 按问题归属**向上取到最近的可答复层**——运行层的
  问题填 deploy，渲染上即部署层自开自答的条目）且**本批不算收官**；
  无 blocker 才收官，并把核查报告路径补进批次报告头部 `inspection_report` 字段，
  收官段末跑 `trace_check --closeout <batch_id>` 过非空门禁
  （§4/§5——idea 层顺批次报告即可看到核查结论）。
  转录 blocker 不算自查顶数：判定发生在 inspector 的独立上下文里，
  部署层只做机械转录。
  **监察面自有记忆** = `reports/inspector-notes.md`（在 reports/ 写权内，只有监察面写）：
  跨次核查的线索、悬而未决的疑点记这里；各层不读它、不依赖它。

- **解读不过层**：上行只有事实，一切解读发生在 idea 层、由用户拍板。
  派生量计算（平均、比例等）是 idea 层活动：提案、批准、算、附命令都在 idea 层（R4）；
  部署层只跑既有机械汇总管道，不发明新算法。
- **悬案攒批上报**：一层在一段工作里撞到多个不确定点（原则缺口、R5 分岔、
  实验设定疑问），必须把手头任务扫完、所有决策点一次性开成一批待决账条目，
  不许问一个等一个。问题的去向是待决账走楼梯——不是报给监察面：
  监察面读一切、自然看得到，但它不在指挥链里，不做路由节点。

## 2 信道

| # | 方向 | 体裁 | 规矩 |
|---|---|---|---|
| 1 | idea → 部署 | 原则文档 + spec | spec 每条指回 principle_id；指不回去 = 原则有缺，先回 idea 层补 |
| 2 | 部署 → idea | 数字账、批次报告、待决账条目 | 报告零解读；原则缺口/代码抉择点停手，写 open 条目进待决账 |
| 3 | 部署 → 运行 | 注册表命令、**发射单** | 不在注册表不许跑；**脏树一律拒发并升级部署层**（豁免清单在配置）；产物钉 RUNMETA。工单是部署层层内物（spec→工单→施工走 rails.build），不跨层下发到运行层 |
| 4 | 运行 → 部署 | 日志、RUNMETA、台账、采样器判定（进台账）、待决账条目（故障升级） | 升级必须带证据：错误原文、日志路径、已试动作表 |

**待决账 `blocked.jsonl`**（贯穿信道 2/4 的双向体裁，schema 与跃迁规则见 §5）。
**会话开工必读两样**（每层的 SKILL.md 骨架里写死）：
① 本层待决队列（open 条目里 to_layer=本层的 + answered 条目里 from_layer=本层的，
都算未决）；② 有效授权视图（抉择账 kind=grant 且未过期未撤销的条目）。
两样必读都是**动态视图**：只出活跃条目，closed/withdrawn/过期/被 superseded 的
永不进视图——"用完即清"靠视图过滤实现，不删账（§2.1）。

总规矩：**可追溯链双向**（正向：工单→spec→原则条目；反向：run→发射单→工单，
靠 RUNMETA.launch_order_ref 与台账回指字段；抉择→run 靠发射单 decision_refs）；
**升级走楼梯不跳层**；**一切通信落盘，不走会话记忆**；
**所有账本对所有层可读，写权单层独占**（§1 的四个成文例外除外）。

### 2.1 账本读写纪律与回收

上下文卫生的主手段是**读法**，不是删账：污染上下文的不是文件大小，
而是把整本账读进会话（用户裁决 2026-08-13：读走脚本为主、归档为辅）。
两条主规矩 + 一条辅助机制：

- **查询口（主）**：jsonl 账只经 `ledger.py query` 读，返回最小视图；
  默认视图只出活跃行（判定式见下）。账本文件本身多大都不进上下文。
  **读法对照（"账本怎么读"的完整外延）**：
  ledger.py 管的四本 jsonl（story/decisions/blocked/feedback）+ runs.jsonl
  → 只经 query，禁整读；md 定稿件（原则文档、spec、工单、批次报告、DATA.md、
  MAP.md、TIMELINE、KNOWLEDGE_MAP、集群慢变量档案，以及 reports/ 下的
  核查/观察/回归报告——`inspector-notes.md` 除外，各层不读）→ 允许整读或
  按条目切片（给人读的定稿件，体量由 doctor 按 `md_size_caps` 盯，§7）；
  小 json 单件（发射单、RUNMETA、error_classes.json、research-loop.json、
  schemas/ 下的 schema 文件）→ 直读；
  大体量（任务台账、原始输出、日志）→ 脚本切片或读手 subagent。
  监察面豁免见 §1 监察面条目。
- **subagent 读手（辅）**：非结构化材料（旧批次报告、原始日志、旧 md）需要摘要时，
  派一个小读手 subagent（sonnet，一次一件），主会话只收摘要 + 原件路径。
- **归档轮转（辅）**：每本 jsonl 账在 research-loop.json 配行数上限（`ledger_caps`，
  plugin 带默认值、工程可覆盖；键必须是 ledgers 键的子集，缺键取默认、
  `null` = 不轮转、ledgers 之外的键判非法，§7）。到上限时 `ledger.py archive`
  把非活跃行**原样搬**进同目录 `<name>.archive.jsonl`（同 schema，逐字节不改），
  主文件只留活跃行；搬运记录写伴生索引 `<name>.archive.idx.json`
  （path/rows/last_id/archived_at；消费者两个——`query --include-archive`
  靠它定位归档文件，doctor 靠它汇报归档量）——**主文件不引入任何新行型**，
  各账 schema 不动。
  - **archive 是全 spec 唯一允许把行搬出 jsonl 主文件的动作**
    （唯一成文豁免：挂接时的一次性 legacy 冻结迁移，机验见 §9 挂接清单②）：不收 `--layer`
    （维护动作，无归属层），合法性由三条搬运机验代替写权检查——①被搬的每一行逐字节出现在
    归档文件；②主文件剩余行是原行序列的子序列（内容与相对顺序不变）；
    ③归档新增行数 = 主文件减少行数。行级写权（含单层独占与
    per-kind/per-row-type）、跃迁与 append 校验一律对 archive 与
    freeze-legacy（§9②）豁免，合法性由各自的搬运/迁移机验代替（§5 通用约定）。
  - **并发协议**：archive 全程持该账文件锁；先写归档文件与新主文件的临时副本，
    原子 rename 替换；无锁 query 读到的必须是完整的旧版本或新版本之一。
  - **活跃行判定式**（逐账写死；query 默认视图与 archive 的"非活跃"共用这一份）：
    blocked = status∈{open, answered}；decisions = kind=grant 且 status=decided
    且未过期未被 superseded（与 §5 有效授权视图同口径），或被任何
    decision_refs/affects/grant_ref/decision_ref/superseded_by 指向的行
    （被引用的永不归档；抉择账没有未决态——悬案归待决账，R5）；story = status=active；
    feedback = 建议条按最新 review 行合并后为 pending（suggestion 与指向它的
    全部 review 行永远同批归档）。**runs 无活跃行概念**（不轮转，ledger_caps.runs 只许 null，§7）：
    `query runs` 必须带过滤（--batch/--run/--since/--metric 至少其一；
    --since 按行内 recorded_at 过滤，§5），
    无过滤拒绝返回全表——读全量走渲染产物（RESULTS），不走查询口。
  - **校验/追溯脚本一律跨档读**：trace_check、verify_report、regression_check、
    spotcheck 与 story/runs 写入时的存在性校验，读账本默认等价于
    `--include-archive`；只有面向会话上下文的 query 默认只出活跃行。
  - 归档由 doctor 建议、用户确认后执行，不自动跑（自动执行后置，§10）。
    任何行永不被删丢、事实字段永不改写——**行内字段的就地更新只有 §5 成文的
    几处**（blocked 状态跃迁、decisions 与 story 的撤销字段与回填字段——
    逐项以 §5 写入两式②为唯一穷举，此处不另列），append-only 的实义
    不因回收而破。
  - md 账（TIMELINE、集群慢变量档案等）不轮转：doctor 按 `md_size_caps`（§7）
    扫体量，超限只出整理建议；整理动作由**该账写权层的会话**做
    （TIMELINE/KNOWLEDGE_MAP → idea 层，集群慢变量档案 → 运行层；用户随时
    可亲自整理），原文另存 `<name>.archive.md`、主文件留一行指针——
    这是 md 账仅有的"重写主文件"场合，罕发的维护动作，原文永远留档。

### 2.5 人的位置（idea 层顶端）

用户本人是 idea 层的顶端，一切判断的终点。

**下行（你 → 系统）不设体裁**（用户裁决 2026-08-13）：你怎么说都行，
不用套任何格式。会话负责把你的话转录落账；下面五类是**转录路径**——
说明"你的哪类话落进哪本账、怎么落"，约束的是转录的会话，不是你：
- **拍板**：原则定稿、spec 批准、故事裁决、**待决条目答复**——落对应账本带日期；
  待决答复由当场会话代笔（answered_by 填 user）；
- **授权**：R4 计算批准、R6 自决授权——原话当场落抉择账（kind=grant，
  含结构化 scope 与有效期）；
- **撤销/更正**：任何已落账的拍板可收回，落法按账分四路，留痕对称
  （jsonl 两路脚本代笔走 §5 撤销代笔特例——当场会话代笔不查归属层，
  必须带用户原话；md 两路由归属层会话改文件、同样转录原话）——
  抉择账/故事账走 status 变更 + `superseded_by`（§5 就地更新白名单内；
  纯撤销 superseded_by 留空，更正才由用户给替代 id，§5 特例句）；
  原则定稿撤销 = 条目标【已撤销】+ 用户原话注日期追进 rationale；
  spec 批准撤销 = 文件头 `approved_by/approved_date` 清空 + `spec_version`
  递增 + `withdrawals[]` 追一条 `{date, by, reason}`（reason=用户原话，
  evidence_lint 比照 rejections 豁免，§5 spec 一节）；
  待决答复撤销 = 写 status=withdrawn，ledger.py 同一动作机械重开新条
  （沿用字段清单以 §5 blocked 一节为唯一穷举，ref 指旧 blocked_id；
  该答复已同步拼出 decision 条的，同一动作一并置 withdrawn）——blocked
  行没有 superseded_by，不加字段；
- **触发**：路由表（§6）里的任何一句话；
- **打回**（批次验收阶段的体裁）：验收不过，退回对应层重做，理由落批次报告
  头部 `rejections: [{date, by, reason}]`——reason 是你原话的转录，
  evidence_lint 对此字段豁免（其余正文照管）。spec/原则阶段的不批准
  不叫打回：不落 approved_by（草稿态即未生效）+ 悬案开待决账 open 条。

**落账定格**（2026-08-13 批注）：聊天里产生的任何决定，生效前必须由会话
转录落账（裁决进对应账、授权进抉择账）——没落账的决定不存在。硬边界单列一条：
**凡涉及实验设定（模型、温度、采样、数据版本等）的悬案，没有你的明说或
有效授权覆盖，不许自行解决**——这是 R5 的明确适用范围。
**授权覆盖下自决了实验设定的，事后必须回报你**（用户裁决 2026-08-13）：
回报走 R6 自决清单——decisions 账里 decided_by=agent 的近期条目渲染成清单，
随下一次对你的汇报明列，不许静默；GPU<1h 常设授权（R5）下干的活同此回报。

**上行（系统 → 你）常用六类**（用户裁决 2026-08-13：**清单不闭**——
常见的按下面六类格式化，需要时可以报额外类别；任何类别都守两条不变量，
见本节末）：
- **提案**：计算提案（R4）、方案抉择（R5）——凡要你拍板的，必须以"提案+证据"形态
  到你面前，不许以既成事实形态出现；
- **证据报告**：R3 体裁（监察报告、观察报告、判据验收报告都是它的子类）；
- **抽查清单**：固定种子抽样直达路径 + 总体指纹；
- **待决队列**：blocked.jsonl 渲染视图，你回来先看这个；
- **回归警报**：新批次数字与故事账 active claim 冲突时的清单（只报事实不判）；
- **数字账**：批次报告 + RESULTS 渲染。

六类管的是**入账物**的格式，不管汇报风格。汇报可以自由发挥、
可以有创造性，可以提框架外的建议（技术方向、框架选型、格式之外的观察），
也可以整类地报清单外的新形态。
不变量只有两条：凡数字有据（R3），凡决定入账（R5/R6）。

**你不在场时**：只有有效授权（kind=grant，scope 覆盖、未过期）内的自决
与 R5 常设授权（GPU<1h）内的发射可以继续（都照 R6 留痕、事后回报），
其余一律停在待决账 open，不许"先做了再说"。

### 2.6 小实验快车道（用户裁决 2026-08-13）

探索性小实验专用通道：**一口气完事，平直快，复用已有基建**。
触发句"快试一下"（§6 路由表）。

- **免的手续**：不开 spec 条目、不开工单、不出批次报告、不派收官通读。
  发射单允许缩减——spec_ref/issue_ref/decision_refs 可空、标 `quick: true`，
  run_id 归入 `quick-<YYYYMMDD>-<序>` 批。
- **不免的底线**（这两条是数字纪律，不是防御手续）：数字仍只经
  metrics_cmd/criterion_cmd 脚本入账（R7，禁止人眼读日志填数）；
  种子仍固定进发射单。发射仍走 rails.gpu——工程唯一发射入口不破。
- **与 R5 常设授权衔接**：预计低于一小时的快实验，部署层默认模式下也可
  直接发射，事后按 §2.5 回报条款向你明列。
- **结果的去向**：`quick: true` 的 run 行不得被故事账引用（story 写入校验拒）；
  要进故事，按正轨补 spec 条目重跑（种子固定，重跑即复现）。
  快车道是试想法的入口，不是论文证据的入口。

## 3 十条硬规矩（全 plugin 通用）

- **R1 原则条目契约**：每条原则 = `principle_id` + `scope` +
  `applies_when`（什么条件下用这条原则）+ 原则一句话 +
  `rationale`（为什么有这条：用户的原因原话或讨论出处）+
  判据（`criterion_cmd`，必须是注册表命令）+ 最近实测。
  **rationale 不许空**：用户口述原则没给原因的，idea 层必须当场追问，
  问不出不落档（`ledger.py principles-lint` 查空，2026-08-13 批注）。
  **未接线态**：工程 registry 未接线时（§7），原则条目允许 criterion_cmd 暂空落档，
  但必须标【想法待定】；补上判据才可转【现状】/【已定要改】
  （principles-lint 按条目 status 列的四色取值放行，§5）。
  **最近实测不手填**：判据每跑一次就是一次 run，进 runs.jsonl 带 principle_id，
  原则文档里的"最近实测+日期"由渲染脚本自动回填。原则文档带修订号。
  **判据必须轻量只读**（不占 GPU、部署层会话当场可跑）；要重算力才能产生的证据，
  先按普通 run 跑出产物，criterion_cmd 吃产物路径做检查。
  写不出轻量判据的原则退回 idea 层重谈。
- **R2 机验人判**：判据机器跑，判断人来下。AI 在验收里只做两件事：把检查跑起来、
  把原始证据摆到用户面前。
- **R3 证据体裁**：判据/监察/观察输出只许——计数、差异定位（分叉点原文并排，
  **两侧各带路径+行号**）、可点开的文件路径（带行号/记录号）。
  **每个数字必须配一条可直接粘贴执行的复现命令**，命令输出必须等于报告数字。
  计数为 0 的否定性陈述必须附扫描范围全量清单与总行数。
  报告头带溯源块：生成时间、git HEAD、所读账本行数/哈希。
  "通过/没问题/符合预期"等结论词违禁。lint + 机械校验器双重把关（§4）。
- **R4 计算授权**：对数据只许忠实呈现原始值。任何派生量先提案
  ——公式、分母、过滤条件、作用文件——用户批了才算，算完连同命令附在结果旁
  （进故事账的记 derivation_command）。
- **R5 抉择点分模式处理**（用户裁决 2026-08-13：不写成铁的，看用户的决定）。
  先识别：施工撞到方案分岔，机械三问判定它算不算抉择点——会改变某条判据的
  输出吗？会引入原则文档没有对应条目的新约束吗？不可逆吗（耗大量 GPU 时长/
  产物已被下游引用；**写 NFS 本身不算不可逆**，用户裁决 2026-08-13）？
  三问全否即施工自由度，直接干。**账本 schema 变更永远算第二问为是**。
  是抉择点的，按当下模式走两条路之一：
  **默认（无覆盖授权）**：停手，写待决账，上桌等裁决；
  **授权自决**：你一句"这类事你自己定"当场落成 grant（§6 路由句），
  scope 覆盖眼前分岔且未过期的，会话自决——照 R6 留痕，且必须按 §2.5
  回报条款事后向你明列干了什么。
  **常设授权一条**（用户裁决 2026-08-13，plugin 携带、无须另发 grant）：
  抉择点若只关系到发射 GPU 任务且预计总时长低于一小时
  （以发射单 expected_runtime_s 合计），默认模式下也可以直接干——
  照 R6 留痕（authorized_by 填 `spec-standing-gpu-1h`），事后必须通知你
  干了什么（§2.5 回报条款）。
  裁决后：ledger.py 把 answered 的 R5 条目**同步生成一条抉择账 decision 条目**
  （chosen 填可 grep 的具体值）——这是抉择账的强制入账口，不许只留自由文本 answer。
- **R6 授权自决留痕**：只有有效授权（grant 的 scope 覆盖眼前分岔且未过期）才许自决；
  每个自决点写抉择账（decided_by=agent，authorized_by 指回 grant 条目）。
- **R7 确定性脚本化（写与读）**：账本写入、schema 校验、溯源检查、抽样、lint、
  渲染，一律脚本干；**账本的读同样走脚本**——结构化账本只经查询口拿最小视图
  （§2.1），不许整文件读进上下文。LLM 只做需要判断的活。渲染产物不手改。
  **runs.jsonl 的数字只有两条脚本路径**（工程记账脚本与 ledger.py runs-append
  入账，§4）：普通实验经发射单 `metrics_cmd`，
  判据 run 经 `criterion_cmd` 的结构化输出——**任何层禁止用眼睛读日志填数**。
  （派生量不进 runs.jsonl，走 R4 归故事账。）
- **R8 故障先自愈后升级**：失败先在本层职责与写权内按**错误分类表**处理
  （特征三类：退出码、output_check 判定、日志正则；命中即得自愈动作或升级指令，
  脚本判不经 LLM）；**没命中的（error_classify 输出 unknown）分层处理**
  （2026-08-13 批注：程序先、LLM 兜底）：**运行层不判**——只做机械动作，
  把错误原文、日志路径、已试动作表收齐开 blocked 条目（kind=failure）升级部署层，
  与"只跑不解释"两立；归类判断由**部署层（及以上）agent** 做——读日志给归类与
  建议动作，动作在本层写权内就执行（顺手往错误分类表加行：表是部署层写权，
  在答复 blocked 时注明），超出写权或拿不准照楼梯再升。解决了留痕；
  解决不了写待决账升一层（运行→部署→idea→你），带证据。
  禁止跳层、静默吞错、越权修别层的东西。"重跑一次输出仍空"必升级。
- **R9 skill 进化落账**：每轮循环收官，各层把"skill 哪里不顺、建议怎么改"写进
  反馈账。建议不自动生效：用户定期审（路由句"审一下反馈"），
  批准的才改 skill 本体（进 git），驳回的记理由——审查以追加 review 行落账
  （§5，账本纯追加），只能由用户审查会话经脚本写。
- **R10 skill 正文按需加载**：SKILL.md 只放骨架（职责、信道、账本写权、开工必读、
  阶段索引），各阶段操作细则拆进 `references/<阶段>.md`，进到那个阶段才读。
  收官才用的反馈方法只在收官段加载。上下文隔离不只隔层，也隔时间。
  账本读写的上下文开销由 §2.1 的查询口管住，本条管 skill 正文本身。

## 4 组件结构（每层一件专责）

```
research-loop/                      # plugin 根
├── .claude-plugin/plugin.json
├── skills/
│   ├── research-loop/SKILL.md      # 路由薄壳：认阶段 → 转层，含路由表（§6）；
│   │                               #   直接转交铁轨前跑 config-check，
│   │                               #   被锁则拒并说明 null 键（§7）
│   ├── idea-layer/SKILL.md         # 谈idea规程、原则模板、故事裁决、R4、撤销体裁
│   ├── deploy-layer/SKILL.md       # spec 体裁、工单化、R5/R6、判据验收、发射单
│   ├── run-layer/SKILL.md          # 运行层契约：发射单执行、错误分类、产物校验
│   └── oversight/SKILL.md          # 监察面：报告体裁、独立性纪律、抽查流程
│   （每个 skill 目录配 references/<阶段>.md，按 R10 分阶段按需加载）
├── agents/
│   └── inspector.md                # 只读监察员：写权限定 reports/、R3 体裁
│                                   #   （监察面参与共享账的两条口子归监察会话，
│                                   #     不给这个 agent）；
│                                   # frontmatter 钉 model: opus（派发必须显式指定模型）
├── schemas/                        # 五本账 + 发射单的 JSON Schema（plugin 携带默认版，
│                                   # 工程可覆盖；变更走 R5 上桌 + schema_version 递增）
└── scripts/                        # 全部确定性，按层归属
    ├── ledger.py                   # 账本总入口：story/decisions(含 grant)/blocked/feedback
    │                               #   写入+schema校验+状态机+跃迁级写权检查+渲染
    │                               #   （渲染含：待决队列视图、有效授权视图、
    │                               #     原则文档"最近实测"回填、账本→md）；
    │                               #   查询口 query（§2.1：各账最小视图，默认只出活跃行；
    │                               #     维度 --batch/--run/--spec-item/--since/--metric/
    │                               #     --all-rows/--include-archive）；
    │                               #   config-check（配置校验：键集/值域/null 对照，
    │                               #     每次写入与 query 自动做，§7）；
    │                               #   归档轮转 archive（§2.1，三条搬运机验、不收 --layer）；
    │                               #   principles-lint（原则文档机验：principle_id 唯一、
    │                               #     applies_when/rationale 非空、【现状】/【已定要改】
    │                               #     条目 criterion_cmd 非空且在注册表）；
    │                               #   另管三件：发射单写入（同一动作回填 affects，§5）、
    │                               #   判据 run 缩减行入账（runs-append：代拉起
    │                               #     criterion_cmd、计时、解析尾行、入账，§5）、
    │                               #   init（挂接问卷生成 research-loop.json 骨架，§7）、
    │                               #   freeze-legacy（一次性接线迁移，§9②）
    ├── trace_check.py              # (deploy) 溯源检查：spec→principle_id、工单→spec、
    │                               #   反向 run→发射单→工单（quick=true 发射单
    │                               #     豁免 spec/工单回指，§2.6）、decision→run（扫发射单
    │                               #   decision_refs + 抉择账 affects）；
    │                               #   批次报告 inspection_report 存在性（平时
    │                               #     非空才查；--closeout <batch_id> 模式
    │                               #     空串即报错=收官非空门禁，§5）；
    │                               #   判据缩减行反向链豁免改查（principle_id 在
    │                               #     原则文档、criterion_cmd 在注册表，§5）
    ├── output_check.py             # (run) 产物校验：expected_outputs 逐条比
    ├── error_classify.py           # (run) 错误分类：按分类表判自愈/升级，输入三类特征
    ├── spotcheck.py                # (oversight) 固定种子抽样：直达路径清单+总体指纹
    ├── evidence_lint.py            # (oversight) 违禁结论词 + "有数字无复现命令"检查
    ├── verify_report.py            # (oversight) 机械校验器：路径 stat、摘录逐字回比、
    │                               #   复现命令数值回比
    ├── regression_check.py         # (oversight) 回归对照：新批次 vs 故事账 active claim
    │                               #   同口径重比，冲突清单落 reports/（idea 层消费）；
    │                               #   --dry-run 只出 stdout 不落盘（doctor 专用，
    │                               #     避免越权写 oversight 独占的 reports/）
    ├── doctor.py                   # (用户) 一键体检：拼装 配置校验 + trace_check +
                                    #   evidence_lint + principles-lint +
                                    #   regression_check --dry-run + 账本行数/md 体量
                                    #   上限扫描 + 遗留 worktree 扫描 + 归档建议（§2.1/§6）。
                                    #   报告只出 stdout（可选 --out 用户指定路径），
                                    #   不写 reports/、不写任何账本目录。
                                    #   代码/bug 检查不在 doctor 范围——归
                                    #   rails.build 会话收尾时自跑工程 selfcheck，
                                    #   doctor 不调用（skill 不是脚本调得动的）；
                                    #   worktree 清理动作归部署层（rails.build 收尾），
                                    #   doctor 只列清单。只查不动：压缩/清理/归档
                                    #   列成建议清单，用户确认后单独执行
    └── fallback/                   # 默认铁轨兜底件（§7）：registry.py（极简注册表，
        ├── registry.py             #   带只读免门禁子命令 --list 供 registry_query）、
        ├── launch.py               #   launch.py（顺序发射：脏树检查 + 写 RUNMETA +
        └── record.py               #   登记极简台账，仅此三件最低必做项）、
                                    #   record.py（append 记账，加载 runs schema、
                                    #   持同一把锁）。裸项目四键分别指
                                    #   registry.py / registry.py --list /
                                    #   record.py / launch.py（§7①）；
                                    #   其余 rails 无兜底件。不复刻任何高级功能
```
runs.jsonl 有且只有两个写入口，按行型分工：**普通实验行**走工程侧记账脚本
（new1: record.py 加载 runs.schema.json 校验；plugin 不接管这个入口——
裸项目可用 `fallback/record.py` 顶上，它同样加载 runs schema 并持同一把锁）；
**判据 run 缩减行**走 `ledger.py runs-append`（§5）。
两个入口加载同一份 schema、共用同一把文件锁。

plugin 本体一律用**英文**交付（SKILL.md、schema 字段说明、脚本报错信息；
用户 2026-08-13 指示，中文 spec 是设计底稿）。
plugin 本体是**通用层**：只要是"idea→实验"形态的项目都装得上；
项目特化全部收进仓库根配置 + 可覆盖 schema，分界与兜底机制见 §7。

## 5 账本 schema（单写多读，主键贯通）

通用约定：**jsonl 账的实体行必带 `schema_version`**（下面示例从略），校验器按行内
版本号选定版本校验，渲染器兼容读；**md 体裁的账（原则文档/spec/工单/批次报告）版本号
在文件头**（原则文档=修订号），不在行内。schema 文件随 plugin 携带默认版、工程可覆盖
（§7 `ledgers.schemas`）；**schema 变更 = R5 必上桌** + 版本递增。
各账 id（S/D/B/F 前缀）由 ledger.py 自增分配。**写入两式**（都过 schema 与
写权检查、都持文件锁）：①原子追加新行；②**成文的字段级就地更新**——仅限
blocked 的跃迁字段（status/answer/answered_*/grant_ref/decision_ref）、
decisions 的 affects 回填与 status/superseded_by/withdrawn_by/withdrawn_reason、
story 的 status/retired_*/superseded_by；除这些成文字段外，行内容不可变。
**撤销代笔特例**（§2.5 撤销是用户下行动作，发起会话不必是归属层）：
撤销体裁的成文就地更新（decisions 的 status=withdrawn+superseded_by、
blocked 的 status=withdrawn、story 的撤销字段）由当场会话代笔、不查
--layer 归属，但字段级强制留发起人与依据，落点按账点名——decisions 写
`withdrawn_by=user` + `withdrawn_reason`（用户原话）；story 写
`retired_by=user` + retired_reason（用户原话）；blocked 的原话进 answer
附注；无原话拒。撤销字段已列入上式②的白名单
（story 的 retired_by 归 retired_* 一族）。**superseded_by 的来源**：
纯撤销留空；"更正"时由用户在撤销命令里给出替代条目 id
（--superseded-by S00x/D00x），脚本校验该 id 存在后才回填。
**行级写权/跃迁/append 校验对三个维护动作豁免**：archive（§2.1，合法性由
三条搬运机验代替——被搬行逐字节在归档、主文件剩余为子序列、行数守恒）、
init（不收 --layer，只在 research-loop.json 不存在或用户确认覆盖时写；
init 也不过 config-check——它的产物就是配置文件本身）与
freeze-legacy（§9②，不收 --layer、只在用户确认下跑，合法性由两条迁移机验
代替——legacy 与原文件逐字节一致、新主文件零行；重复执行拒）。
**渲染/回填类脚本动作同样不过 --layer 检查**（原则文档"最近实测"回填、
账本→md 渲染）：它们不产生新内容，只物化已入账的数据。
**ledger.py 一切写入必带 `--layer` 自报参数**（各层 SKILL.md 骨架写死本层取值；
唯一的第五值 `user` 只有 feedback review 子命令收，见反馈账一节）；
写权与跃迁检查是**防呆不是防伪**——挡误用（会话忘了自己是谁），不设防恶意冒报，
冒报不在威胁模型内。

**原则文档条目**（idea 层写；md 表）：
`principle_id | status（四色）| scope | applies_when（适用条件）| 原则一句话 |
rationale（原因：用户原话或讨论出处，必填不许空）|
criterion_cmd（注册表命令）| 最近实测（ledger.py 回填，不手填）`
文档头带修订号；`status` 列取四色之一：【现状】/【已定要改】/【想法待定】/
【已撤销】——principles-lint 按这一列放行（R1 未接线态）、撤销体裁（§2.5）
也落这一列。用户没说原因，idea 层当场追问；rationale 为空的条目
principles-lint 不过（R1）。
**机器可解析格式约定**：一条原则一行 md 表、列名固定——principles-lint 按列名
解析机验，渲染脚本按列名定位"最近实测"列回填。

**spec**（部署层写）：文件头 `{spec_version, approved_by, approved_date,
approved_against_principles_version, withdrawals[]}`
——批准状态落盘，新会话不许拿草稿当已批。**批准撤销** =
`approved_by/approved_date` 清空（回未批态，新会话按未批处理）+
`spec_version` 递增 + `withdrawals[]` 追 `{date, by, reason}`
（reason=用户原话，evidence_lint 豁免，§2.5 第三路）。
每条目 `{item_id, principle_id, 内容, acceptance, depends_on[], priority, droppable}`。

**工单**（部署层写；最小字段契约，new1 挂接现有 issue-tracker 约定）：
`issue_id、spec_item(回指 item_id)、Status 行、acceptance(抄或引 spec 条目)、Blocked by`。

**批次报告**（部署层写；md）：头部 `{batch_id, spec_items[], run_ids[], date,
how_to_read, inspection_report, rejections[]}`——`how_to_read` 是"怎么读这批
结果"（读数脚本 + 口径说明，部署层向 idea 层交底的落点，§1 层纪律）；
`inspection_report` 是本批例行核查报告路径（收官闭环第③步回填；
**允许空串 = 未收官**，trace_check 平时只在非空时校验路径存在，
收官时由部署层 SKILL.md 收官段跑 `trace_check --closeout <batch_id>`——
该模式下空串即报错，这就是收官非空门禁的执行者，§4）；
`rejections` 是打回记录 `[{date, by, reason}]`（reason=用户原话转录，
evidence_lint 对此字段豁免，§2.5）；batch_id 规则
`<spec条目>-<YYYYMMDD>-<序号>`；正文零解读（发生了什么、数字多少、
证据路径），evidence_lint 同样管它。

**故事账 `story.jsonl`**（idea 层写）：
```json
{"claim_id": "S001", "claim": "一句话主张",
 "evidence_runs": ["run_id"], "baseline_runs": ["run_id"],
 "candidate_runs": ["run_id"], "selection_rule": "怎么从候选里挑的",
 "derivation_command": "派生量的复算命令", "principle_id": "P003",
 "role": "主结果|消融|反例|动机", "decided_by": "user", "date": "YYYY-MM-DD",
 "status": "active|retired", "retired_reason": "", "retired_date": "",
 "retired_by": "",
 "superseded_by": "", "note": ""}
```
写入校验：所有被引 run_id 必须存在于 runs.jsonl **且 status=ok
且非 quick 行**（§2.6：快车道结果要进故事先按正轨重跑）。

**抉择账 `decisions.jsonl`**（§1 第四例外，按 kind 分工——kind=decision 直接
写入只收 `--layer deploy`，例外：decided_by=agent 且 authorized_by=grant:D00x
的 R6 自决留痕条目收 idea|deploy|run 三层；kind=grant 三层会话当场代笔
（均不含 oversight，§1）；r5-choice 同步条目
由 ledger.py 机械拼装自动落账，不算会话写入、不查 --layer）：
```json
{"decision_id": "D001", "kind": "decision|grant",
 "where": "文件路径|spec条目|工单号（kind=grant 时可空）",
 "question": "抉择点或授权的事项类别",
 "options": ["...（grant 可空）"], "chosen": "可 grep 的具体值（grant 可空）",
 "reason": "...", "authorized_by": "用户原话 | discussed | grant:D00x",
 "scope": {"desc": "管哪一类", "path_globs": ["..."], "expires_at": "ISO|null"},
 "principle_ref": "P00x|null", "affects": ["spec条目/工单/run_id"],
 "decided_by": "user|agent", "raised_at": "ISO秒级", "decided_at": "ISO秒级",
 "status": "decided|withdrawn", "superseded_by": "",
 "withdrawn_by": "", "withdrawn_reason": "（撤销时必填用户原话，§5 撤销代笔特例）"}
```
- `kind=grant` 是预授权体裁：where/options/chosen 可空，**scope 必须结构化填全**。
  有效授权视图 = kind=grant、status=decided、未过期、无 superseded_by。
- **decision_refs 是权威，affects 是它的物化索引**：写发射单的同一个 ledger.py 动作
  自动把 run_id 回填进 decision_refs 指向的每条抉择的 affects（触发者=写发射单的
  部署层会话，不是另一个步骤）；两者不一致以发射单为准，trace_check 校验一致性。
- R5 裁决强制入账（§3 R5），杜绝"裁决只活在 blocked.answer 自由文本里"。

**待决账 `blocked.jsonl`**（跃迁级写权）：
```json
{"blocked_id": "B001", "from_layer": "idea|deploy|run|oversight",
 "to_layer": "user|idea|deploy",
 "kind": "principle-gap|r5-choice|failure|other",
 "ref": "spec条目/工单/run_id/blocked_id（撤销重开时指旧条，§2.5）",
 "question": "卡在哪、缺什么",
 "where": "（kind=r5-choice 必填）", "options": ["（kind=r5-choice 必填）"],
 "evidence": ["日志路径", "已试动作"], "raised_at": "ISO秒级",
 "status": "open|answered|closed|withdrawn",
 "answer": "", "answered_at": "", "answered_by": "",
 "grant_ref": "D00x|null（answered_by≠user 的 r5-choice 必填）",
 "decision_ref": "D00x|null"}
```
- 跃迁级写权（ledger.py 按 --layer 强制）：open 只能 from_layer 写；
  answered 只能 to_layer 写——**to_layer=user 的特例**：任何层的当场会话都可代笔，
  但字段级检查强制 answered_by=user 且 answer 含用户原话；
  closed 只能 from_layer 写；**withdrawn 走 §5 撤销代笔特例**——当场会话
  代笔、不查 --layer，字段级强制留用户原话；撤销 answered 条时由 ledger.py
  在**同一动作内机械重开**新条（不查 --layer）：from_layer/to_layer/kind/
  question/where/options/evidence 逐字沿用旧条、ref 指旧 blocked_id、
  status=open——新条回到 to_layer 的待办队列，问题不因撤销而消失。
  被撤销答复若已同步拼出
  decision 条（decision_ref 回指），同一动作把该条置 status=withdrawn +
  withdrawn_by/withdrawn_reason（同一份撤销原话）——被收回的裁决
  不得在抉择账里保持生效。
- 渲染口径：open 归 to_layer 的待办，answered 归 from_layer 的待确认，**两者都算未决**；
  closed/withdrawn 不显示。
- **kind=r5-choice 的条目**：open 时必填 where/options；answer 跃迁必传 `--chosen`
  （可 grep 的具体值）——ledger.py 用 where/options/chosen/answer 四样**机械拼出**
  decision 条目（不猜自由文本），`decision_ref` 回指。拼装的字段映射规则成文：
  reason = answer 原文；decided_by = answered_by 为 user 时填 user、否则填 agent；
  authorized_by = answered_by 为 user 时填 answer（用户原话）、否则填
  `grant:<grant_ref>`——**answered_by≠user 的 r5-choice 答复必传 `--grant`**
  （落 grant_ref 字段，指向覆盖此分岔的有效授权），没有就拒，这正是 R6 的机验落点。

**反馈账 `feedback.jsonl`**（append-only 共笔，条目带 layer；两种行型）：
```json
{"fb_id": "F001", "kind": "suggestion", "date": "YYYY-MM-DD",
 "layer": "idea|deploy|run|oversight",
 "context": "哪个阶段/哪轮运行", "problem": "哪里不顺", "suggestion": "建议怎么改"}
{"fb_id": "F002", "kind": "review", "ref": "F001", "layer": "user",
 "verdict": "accepted|rejected", "note": "", "date": "YYYY-MM-DD"}
```
审查不改写旧行：用户审查会话经 ledger.py **追加 kind=review 行**（路由句"审一下反馈"）；
review 行 layer 恒为 `user`——`--layer` 的合法值因此有第五个 `user`，
只有 feedback 的 review 子命令收它（其余一切写入仍只收四个层/面值）；
建议条的有效状态 = 指向它的最新 review 行的 verdict，没有 review 行 = pending
（渲染器合并显示）。账本本体纯追加，shared-append 的机验（校验器只放行 append；
唯一例外是 §2.1 archive 的搬运，按三条搬运机验判定，且 suggestion 与其全部
review 行同批归档）因此成立。

**发射单 `launch_orders/<run_id>.json`**（部署层写、运行层只读）：
```json
{"run_id": "部署层按工程命名规则给定，运行层不得自造", "spec_ref": "item_id",
 "issue_ref": "工单", "decision_refs": ["D00x"], "batch_id": "...",
 "registry_task": "注册表任务名", "argv": [...], "env_name": "...", "workdir": "...",
 "expected_commit": "...", "seed": 0, "dataset_version": "...",
 "arm": "实验组|对照组", "filter": "口径过滤条件字符串（可空）",
 "quick": false,
 "resources": {"gpus": 1, "min_vram_gb": 0, "exclusive": false},
 "expected_runtime_s": 0, "depends_on": ["run_id"],
 "expected_outputs": [{"path_glob": "...", "min_bytes": 0, "min_lines": 0, "required_keys": []}],
 "metrics_cmd": "结构化抽数命令", "smoke_cmd": "...",
 "retry": {"max_attempts": 2, "retriable_errors": [], "allow_card_swap": true},
 "mutable_params": ["只管 argv 内参数白名单；seed 永不在内；资源分配归 retry 管"],
 "artifact_dir": "...", "created_by": "...", "created_at": "ISO秒级"}
```
- **结构化抽数契约（metrics_cmd 与 criterion_cmd 通用）**：stdout 最后一行必须是
  单个 JSON 对象——criterion_cmd 至少含 `{"value":…, "evidence_path":…}`
  （evidence_path 落缩减行 output_dir）；metrics_cmd 至少含
  `{"metric_name":…, "value":…, "n":…}`。入账脚本只解析这最后一行；
  解析失败 = 入账拒绝并按 R8 升级，禁止人眼读日志补数。
- 超时判定用 expected_runtime_s（×配置系数）；"卡死"判定用配置 stall_thresholds，两者分工。
- **与工程台账的顺序**：部署层写发射单 → 运行层铁轨读发射单发射并登记任务台账 →
  RUNMETA/台账回指 launch_order_ref。发射单不取代台账：发射单=要跑什么（前瞻），
  台账=跑成什么样（后验）。

**runs.jsonl**（定义权部署层：`runs.schema.json`；写权按行型分工——普通行归运行层、
判据缩减行归部署层，§1 第三例外；写入前脚本校验）：
行至少含 `run_id, status(ok|failed|oom|timeout|empty-output|killed|partial), output_dir,
runmeta_path, metric_name, value, n(分母), filter, seed, dataset_version, batch_id,
arm(实验组|对照组), quick(布尔，记账脚本从发射单透传，§2.6 快车道行为 true),
principle_id(判据缩减行专用，普通行一律为 null),
commit(判据缩减行用，普通行为 null——普通行的 commit 在 RUNMETA), elapsed_s, gpu_count,
recorded_at(ISO秒级，两个入账脚本自动打，不许手填——`query --since` 按它过滤),
schema_version`。**status≠ok 的行 metric_name/value/n 允许为 null**。
普通行的 arm/filter 由记账脚本从发射单透传（部署层填、可空，
运行层不判语义——"只跑不解释"）。
**判据 run 是缩减行**（principle_id 非空即缩减行，一一对应）：
必填只有 run_id、status、principle_id、value（判据输出的计数/判定值）、
output_dir（证据文件路径）、commit（runs-append 自动抓 git HEAD，脏树加 `-dirty` 后缀）、
elapsed_s、recorded_at（脚本自动打）、schema_version，其余允许 null；
run_id 由 ledger.py 按
`chk-<principle_id>-<YYYYMMDD>-<序>` 分配，其中日期段就是渲染脚本回填
"最近实测+日期"的日期来源（判据 run 不开发射单，这是 run_id"由部署层给定"的
唯一成文例外）。**执行契约**：部署层会话只负责发起——执行与入账是同一个动作
`ledger.py runs-append --layer deploy --principle <principle_id>`（§1 第三例外）：
脚本按 principle_id 从原则文档 criterion_cmd 列取命令（缩减行不存命令本体，
trace_check 的"在注册表"豁免检查沿同一条链取值），**代为拉起**并计时，
退出码、elapsed_s 由脚本自取，尾行结构化输出由脚本解析
（契约见发射单一节），会话不经手任何数字（R7）；注册表命令自带解释器与环境，
不需要发射单的 env_name/workdir。判据一律
轻量只读（R1 硬约束）——不占 GPU、不过脏树发射门禁、不登任务台账、不写 RUNMETA，
要重算力的证据先按普通 run 跑出产物、criterion_cmd 吃产物路径做检查
（output_dir 可指向该产物内的证据文件），溯源就是缩减行本身
（principle_id→原则文档 + commit + output_dir 证据文件）。
入账同样过 schema 校验；
**只有退出码 0 且尾行 JSON 解析成功才落行（status=ok）**——退出非 0 或解析失败
一律不落行，按 R8 升级：判据没跑成不算实测，原则文档"最近实测"不更新。
**trace_check 反向链豁免**：principle_id 非空的行不查 run→发射单→工单回指，
改查 principle_id 存在于原则文档、criterion_cmd 在注册表。

**RUNMETA**（运行层写；**落点约定：artifact_dir 根下 `RUNMETA.json`**，
runs.jsonl.runmeta_path 回指）：commit + argv + 脏树清单 + `launch_order_ref` +
`attempt_no` + `env_name` + `outputs: [{file, format, fields:{字段名: 含义}}]`
（产物字段字典，由写文件的代码自动生成——监察面读格式的唯一权威来源；
兜底态允许空，监察面回落直接读产物，§7）。

**任务台账**：补 `status 枚举（同 runs）、exit_code、attempt_no、gpu_ids、host、
tmux_session、started_at、ended_at、log_path、artifact_dir、launch_order_ref、
escalation_ref(blocked_id)、采样器判定(stall|dead|ok + 判定时间)`。

**错误分类表**（部署层写，error_classify.py 判）：
`{特征: {exit_code | output_check 判定 | log_regex} → 动作: 重试|换卡|升级}`。
unknown 的新规则提议路径见 R8：运行层升级的 blocked（kind=failure）带齐三类特征，
部署层答复时判断是否往表里加行（表在其写权内，答复中注明）。
**集群慢变量档案**：写权运行层（new1 挂接：ops/gpu_state.md）；
md 账，回收走 §2.1 的 doctor 扫描 + 写权层人工整理路径。

## 6 路由表（research-loop 薄壳的全部内容）

| 用户说 | 阶段 | 转给 |
|---|---|---|
| 我有个想法 / 讨论方向 | ① | idea-layer（谈；文献核实走 rails.literature 铁轨） |
| 定一下原则 / 这条进原则 | ② | idea-layer（原则模板 + R1） |
| 这轮做什么 / 出 spec | ③ | deploy-layer（spec + trace_check） |
| 施工 / 执行工单 | ④ | deploy-layer → rails.build（new1: ticket-run） |
| 跑实验 | ⑤ | deploy-layer 出发射单 → rails.gpu / rails.pipeline |
| 快试一下 / 快实验 | ⑤ | deploy-layer 快车道（§2.6：缩减发射单 → rails.gpu；预计 <1h 免上桌、事后回报） |
| 这个结果进故事吗 | ⑥ | idea-layer（用户拍板 → ledger.py story） |
| 写论文 | ⑦ | rails.paper（new1: paper-write），溯源对故事账取材 |
| 查 X / 让我亲眼看看 | 任意 | oversight → inspector |
| 看看输出里有什么 | 任意 | oversight → inspector（观察报告 = R3 子类） |
| 有什么在等我 | 任意 | ledger.py blocked 渲染（待决队列视图） |
| 这类事你自己定（授权） | 任意 | ledger.py grant 落账（结构化 scope，当场） |
| 我收回那条决定 | 任意 | 撤销体裁 → 按账分四路落账（§2.5 撤销/更正） |
| 这个不行，重做（打回） | 批次验收后 | 退回对应层，理由落批次报告头部 rejections[]（spec/原则阶段的不批准另走 §2.5：不落 approved_by + 开待决条） |
| 审一下反馈 | 收官后 | ledger.py feedback review（R9） |
| 体检一下 / doctor | 任意 | doctor.py 一键检查（§4）：五件常驻检查（配置校验/trace_check/evidence_lint/principles-lint/regression_check --dry-run）+ 账本体量 + 遗留 worktree；归档/清理只出建议清单，确认后执行 |
| 深查这批 / 核查部署 | ⑤⑥后 | inspector（opus）通读核查——部署收官例行核查（§1）的手动触发口 |

表里一切动作都可由你随时手动触发，不限"阶段"列所示时点；
路由句只是常用入口，不是白名单。

## 7 工程挂接（plugin 通用 ↔ 项目铁轨）

仓库根 `research-loop.json`（写权归用户/主会话，变更过 git）：
```json
{"ledgers": {
   "principles": "METHOD.md", "story": "ops/story.jsonl", "timeline": "TIMELINE.md",
   "literature": "KNOWLEDGE_MAP.md",
   "specs": ".scratch/", "issues": ".scratch/*/issues/",
   "decisions": "ops/decisions.jsonl", "blocked": "ops/blocked.jsonl",
   "feedback": "ops/feedback.jsonl", "launch_orders": "ops/launch_orders/",
   "batch_reports": "plans/", "codemap": "MAP.md",
   "runs": "ops/runs.jsonl", "jobs": "ops/jobs.json",
   "schemas": "ops/schemas/", "runs_schema": "ops/schemas/runs.schema.json",
   "error_classes": "ops/error_classes.json", "cluster_state": "ops/gpu_state.md",
   "datasets": "DATA.md", "reports": "reports/",
   "runmeta": "<artifact_dir>/RUNMETA.json", "raw_data": "<raw_data_roots>/**"},
 "owners": {"principles": "idea", "story": "idea", "timeline": "idea", "literature": "idea",
   "specs": "deploy", "issues": "deploy", "decisions": "per-kind",
   "feedback": "shared-append", "blocked": "per-transition",
   "launch_orders": "deploy", "batch_reports": "deploy", "codemap": "deploy",
   "schemas": "deploy", "runs_schema": "deploy", "error_classes": "deploy",
   "datasets": "deploy",
   "runs": "per-row-type", "jobs": "run", "cluster_state": "run", "runmeta": "run",
   "raw_data": "run", "reports": "oversight"},
 "ledger_caps": {"blocked": 500, "decisions": 1000, "feedback": 500,
                 "story": 1000, "runs": null},
 "md_size_caps": {"cluster_state": 65536, "timeline": null, "literature": null},
 "registry_cmd": "python3 run.py",
 "registry_query": "python3 run.py show --list",
 "record_cmd": "python3 run.py record",
 "dirty_exempt_globs": ["ops/jobs.json*", "ops/runs.jsonl", "RESULTS.md", "*.lock"],
 "stall_thresholds": {"no_log_growth_s": 0, "gpu_idle_s": 0, "startup_grace_s": 0},
 "runtime_factor": 3,
 "rails": {"build": "ticket-run", "gpu": "gpu-run", "pipeline": "probe-pipeline",
           "paper": "paper-write", "literature": "update-knowledge-map"},
 "raw_data_roots": ["/net/.../reproduce/new1/"]}
```
- `rails.*` 值域**按键分收**（config-check 查）：`rails.gpu` 两型——skill 名
  （路由转交给该 skill 会话）或可执行命令/脚本路径（由运行层直接执行，
  入参为发射单路径；兜底件 `scripts/fallback/launch.py` 属此型；区分机械：
  值命中已装 skill 名按前者，否则按命令执行）；
  `rails.build/pipeline/paper/literature` 只许 skill 名——这四轨是会话形态的
  流程（施工不跨层下发到运行层，§2 信道 3），填命令判配置非法。
- `ledgers` 是**完整账本清单**（监察面追溯起点），§1 写权表里的每一本都有路径；
  值允许路径模板（`<artifact_dir>`、`<raw_data_roots>` 占位）。
- `owners` 的**键集合与 ledgers 严格相等**（配置校验器查这个），值与 §1 的写权约定
  （三层写权表 + 监察面条目）一一对应。**来源**：plugin 携带 owners 全键默认表
  （值由 §1 写权约定固定），init 按最终 ledgers 键集自动生成、不询问；
  默认表外的工程新增键（如挂接迁移产生的 `runs_legacy`→frozen）由接线会话
  与 ledgers 同批补齐 owners 值，init 对默认表外的键提示补填而非静默生成；
  工程改值 = 改写权约定，先回本 spec 走 R5。**值域成文**：层名 `idea|deploy|run`、
  面名 `oversight`、冻结名 `frozen`（只读冻结件，任何 --layer 写入一律拒；
  挂接迁移产生的 `runs_legacy` 用它）、规则名 `per-transition`
  （按 §5 跃迁规则机验，含撤销代笔特例）| `shared-append`
  （只许追加，条目 layer 自证）| `per-row-type`（runs.jsonl 专用，§1 第三例外：
  普通行归 run 层经工程记账脚本、判据缩减行归 deploy 层经 runs-append，
  机验 = runs-append 只收 `--layer deploy`）| `per-kind`（decisions 专用，
  §1 第四例外：kind=decision 只收 `--layer deploy`——R6 自决留痕条目
  （decided_by=agent 且带有效 grant 指回）收 idea|deploy|run 三层；
  kind=grant 收三层（均不含 oversight，§1）；
  r5-choice 同步拼装不查）——校验器按这九个值收，别的都非法。
- `ledger_caps` 是 §2.1 归档轮转的行数上限（用户裁决 2026-08-13：上限进配置）；
  plugin 带默认值、工程可覆盖；`null` = 该账不轮转。**键约束（配置校验器查）**：
  键必须是 ledgers 键的子集且只许 jsonl 账，缺键取 plugin 默认，
  ledgers 之外的键判非法；**`runs` 与 `runs_legacy` 只许取 null**——runs 无
  活跃行判定式（§2.1）、legacy 是冻结件，归档在两者身上无定义，
  非 null 判配置非法。**runs.jsonl 不轮转**：
  new1 渲染链（RESULTS.md）依赖全量行，且会话读数走渲染产物与查询口、
  不直读原文件，主文件体量不构成上下文问题。归档文件与索引是主账的伴生物
  （`<name>.archive.jsonl` / `<name>.archive.idx.json`），不进本清单（§2.1）。
- `md_size_caps` 是 md 账的体量上限（字节）：键为 ledgers 中 md 账的子集，
  `null` = 不扫，**缺键 = 不扫**（体量告警只对显式配置的账）；
  doctor 读它出整理建议（§2.1），只建议不动作。
- `registry_query` 必须是**只读且不受脏树门禁**的动作；样例值待 new1 核实
  （§9 挂接清单第 5 项），不满足就加只读入口。
- `record_cmd` 是工程记账脚本入口（runs.jsonl 普通行的写入者，§4）；
  为 null 时 runs 普通行入账被锁（下方对照）。
- **未接线拒绝的执行者与时点**：配置校验是 `ledger.py config-check` 子命令——
  ledger.py 每次写入/query 加载配置时自动做（涉及被锁功能的子命令直接拒），
  铁轨类动作（发射/施工/写作取材/文献核实）在触发前跑 config-check 按对照
  拒——经层转交的由该层 SKILL.md 跑，由薄壳直接转交的（写论文）由
  research-loop 薄壳在转交前跑（§4）；
  doctor 拼装的"配置校验"就是这一件。
- **通用层/特化层分界**（2026-08-13 批注）：plugin 本体不含任何工程专名，
  特化只发生在这份配置里。两点补强：
  ① **默认铁轨兜底**——项目没有注册表/记账/发射这类设施时，四个键可指向
  plugin 自带的 `scripts/fallback/`：`registry_cmd`→registry.py、
  `registry_query`→`registry.py --list`（只读、不过脏树门禁的列表子命令）、
  `record_cmd`→record.py、`rails.gpu`→launch.py（§4），裸项目装上即可用，
  项目长出自己的设施后换指；
  **其余铁轨（build/pipeline/paper/literature）无兜底件**——
  未接的留 null 按被锁功能处理。
  **兜底脚本的最低必做项**（溯源链在兜底态不打折）：写 RUNMETA（commit + argv +
  launch_order_ref + 脏树清单；**attempt_no/env_name/outputs 允许空**——兜底态
  不重试、不管环境、没有工程代码生成字段字典，监察面回落到直接读产物文件）、
  脏树检查、登记极简台账；record.py 同样加载 runs schema 并持同一把锁（§4）；
  除此之外不复刻铁轨的任何高级功能（顺序执行 + 文件锁 + append 而已）；
  ② **init 挂接问卷**——`ledger.py init` 逐项问（注册表命令？注册表只读列表
  命令（registry_query）？记账脚本？产物根？
  各铁轨 skill 名（rails.gpu 还可填可执行命令，值域按键分收见上；
  兜底件 `scripts/fallback/launch.py`）？账本落点逐项确认或改——plugin 携带
  `ledgers` 全键的默认相对路径表）；答案落 research-loop.json；没答的留 null，
  配置校验时列成**"null 键 → 被锁功能"对照**（未接线的功能拒绝，不静默降级：
  registry_cmd=null 锁判据实跑/发射/施工，rails.gpu=null 锁批量发射，
  record_cmd=null 锁 runs 普通行入账，registry_query=null 锁 principles-lint
  与 trace_check 的"在注册表"存在性校验（报未接线，不放行）；
  四轨 null 按**动作**锁不按路由行锁：rails.literature=null 只锁文献核实
  入 KNOWLEDGE_MAP（陪谈与落原则照常），rails.pipeline=null 只锁走
  pipeline 的发射路径（rails.gpu 已接线时"跑实验"照常），
  rails.build=null 锁施工动作，rails.paper=null 锁写作取材动作；
  原则落档不被锁——走 R1 未接线态标【想法待定】）。
- 没有配置文件 = 工程未接线：铁轨动作与一切记账都拒绝——账本路径全部来自
  `ledgers`，没有配置就没有落点；只有谈可用。接线第一步就是上面的 init 问卷。
- **编号名字空间**：本 spec 的 R1–R10 只指 §3；工程侧自有编号（如 new1
  METHOD.md 的 R1–R4 判据）是另一套。挂接后引用工程原则一律用 principle_id，
  不用工程侧自编号。
- 数据集清单挂 DATA.md（new1 侧加结构化表头：dataset_id/路径/生成 commit/行数/
  校验和/当前版本）。

## 8 端到端剧本（验收时走一遍）

1. "我有个想法" → idea-layer 陪谈，文献入 KNOWLEDGE_MAP（rails.literature）。产出候选假设。
2. 谈熟 → 写/改原则，每条过 R1。用户拍板。
3. 出 spec（含 acceptance/depends_on，文件头记批准）→ trace_check 全绿。用户拍板。
4. spec → 工单（§5 工单契约）→ rails.build 施工。抉择点走 R5：三问识别、
   分模式处理——自决先查有效授权视图（开工必读②）与 R5 常设授权（GPU<1h），
   命中才自决并留痕（R6）、事后回报（§2.5）。
5. 部署层出发射单（含 seed/dataset_version/decision_refs；同一动作把 run_id 回填进
   被引抉择的 affects）→ 冒烟 →
   判据实跑（criterion_cmd 结构化输出进 runs.jsonl 带 principle_id）→
   证据报告（R3）→ evidence_lint + verify_report 过 → 用户亲验 →
   批量发射走 rails.gpu（铁轨读发射单、登记台账、RUNMETA 回指）；
   output_check 防空产物；数字只经 metrics_cmd/criterion_cmd 入账。
6. 跑完 → inspector 观察报告（RUNMETA.outputs 读格式）+ spotcheck 抽查清单 →
   用户读原件。regression_check 对照故事账，冲突清单落 reports/。
7. 用户拍板进故事 → ledger.py story 记账（run 存在性+status=ok 校验）。
8. 回 1，或走 rails.paper，数字溯源对故事账。
9. 任意时刻"查 X" → inspector 顺账本清单（ledgers）挖到原始文件（runmeta_path→RUNMETA→
   outputs 字典）；"有什么在等我" → 待决队列渲染。
10. 收官：各层反馈进反馈账；用户说"审一下反馈"时走 R9 审查；
    部署收官例行核查走 §1 三步闭环（派发契约 → inspector 通读 + 三件套 →
    verdict 读回：有 blocker 转录 blocked 并阻断收官，无 blocker 才收官
    并回填批次报告 inspection_report）。
    全程失败按 R8 走楼梯：error_classify.py 先判（脚本、不经 LLM）；
    unknown 在运行层只机械升级（证据齐全的 blocked），
    归类与往分类表加行由部署层做。

## 9 验收标准

- 五个 skill + inspector agent + 九个脚本 + fallback/ 兜底三件 + schemas/ 齐备，
  plugin 可安装、路由表可触发。
- 每个脚本有可跑自测。重点用例：
  - trace_check：spec 条目指不回 principle_id → 报错；run→工单断链 → 报错；
    判据缩减行（principle_id 非空）→ 不按断链报错，
    改验 principle_id 在原则文档、criterion_cmd 在注册表；
    decision→run 反查（经 decision_refs 与 affects）返回正确集合。
  - ledger.py story：run_id 不存在或 status≠ok 或 quick=true → 拒收（§2.6）；
    撤销 → status+superseded_by。
  - 快车道：缩减发射单（quick=true、spec_ref 空）→ trace_check 不按断链报错；
    quick 行进 runs.jsonl 正常，被 story 引用 → 拒。
  - ledger.py blocked：状态机与跃迁级写权（--layer 传错 → 拒），非法跃迁 → 拒绝；
    kind=r5-choice 缺 where/options 开条 → 拒，answer 未传 --chosen → 拒；
    answered 后自动同步 decision 条目并回填 decision_ref（机械拼装，不解析自由文本）；
    answered_by≠user 的 r5-choice 答复未传 --grant → 拒；
    to_layer=user 特例：answered_by≠user → 拒。
  - ledger.py grant：无结构化 scope → 拒收；过期/被 superseded 的 grant
    不进有效授权视图。
  - 撤销代笔特例（§5）：idea 层会话撤销 deploy 落的 kind=decision →
    放行且落 withdrawn_by/withdrawn_reason（用户原话）；不带原话 → 拒；
    撤销 answered 的 blocked 条 → 同一动作机械重开同 from/to 新 open 条，
    新条出现在 to_layer 待办视图、旧条不再显示；被撤销的是 r5-choice →
    新条 where/options 非空且与旧条一致，其同步 decision 条同批置 withdrawn。
  - ledger.py freeze-legacy：legacy 与原文件逐字节一致、新主文件零行、
    重复执行 → 拒；不收 --layer。
  - ledger.py feedback：review 行只能经审查子命令追加（--layer user），
    layer≠user 的 review 行或改写旧行 → 拒。
  - ledger.py runs-append：--layer≠deploy → 拒；criterion_cmd 退出非 0
    或尾行非 JSON → 不落行、升级。
  - ledger.py query：默认视图严格按 §2.1 逐账活跃行判定式（blocked 只出
    open/answered；decisions 只出有效 grant（kind=grant 且 status=decided 且
    未过期未被 superseded）与被引用行；story 只出 active；
    feedback 按最新 review 合并后只出 pending）；`--all-rows` 出全行、
    `--include-archive` 跨档返回全集（主文件 + 归档逐行并集）、
    `--batch` 按批次切片；`query runs` 无过滤 → 拒绝返回全表（§2.1）。
  - ledger.py archive：到 `ledger_caps` 上限轮转后——三条搬运机验全过
    （被搬行逐字节在归档文件、主文件剩余为原行子序列、行数守恒）、
    idx 索引一致、shared-append/跃迁校验器不误报、suggestion 与其 review 行
    同批归档、被引用的抉择行不被搬走；未经确认不执行；收到 --layer → 拒。
  - ledger.py principles-lint：rationale/applies_when 为空 → 报错；
    【现状】/【已定要改】条目 criterion_cmd 空或不在注册表 → 报错；
    未接线态【想法待定】条目 criterion_cmd 空 → 放行（R1 未接线态）。
  - doctor.py：单项检查件挂掉能正确汇总报告；md 账超 `md_size_caps` → 出整理建议；
    只出建议清单，不执行任何变更动作、不写 reports/。
  - trace_check 跨档：被引条目在归档文件中 → 不报断链（§2.1 跨档读）。
  - 部署收官闭环：部署层 SKILL.md 收官段含派发契约（batch_id + 批次报告路径 +
    配置路径 + 三件套命令）；核查报告 verdict 含 blocker → 收官被阻断且逐条
    转录 blocked；无 blocker → 批次报告 inspection_report 回指存在
    （trace_check 查）；未收官批次 inspection_report 为空串 →
    trace_check 平时不报断链、`--closeout` 模式报错（§5）；
    路由句"深查这批"能手动复现整步。
  - fallback 兜底三件：launch.py（rails.gpu 指入，§7）按发射单 argv 顺序执行，
    另做三件最低必做项——脏树检查 + 写 RUNMETA +
    登记极简台账（四项各有自测）；registry.py 极简可跑，`--list` 只读免门禁
    可跑（兜底态 principles-lint 的"在注册表"校验能过）；record.py 入账过
    runs schema 校验并持同一把锁；兜底态下反向溯源链
    （run→RUNMETA→launch_order_ref）不断。
  - ledger.py config-check：registry_cmd=null → runs-append（判据实跑入账）拒；
    record_cmd=null → runs 普通行入账拒；registry_query=null → principles-lint
    与 trace_check 的"在注册表"校验报未接线（不放行）；owners 键集与 ledgers
    不等 → 报错；ledger_caps 出现 ledgers 外的键或 `runs`/`runs_legacy`
    非 null → 报错；owners 值域按九值收（frozen 键任何写入拒）；
    init 问卷产出的骨架（owners 自动生成）直接过 config-check。
  - output_check：退出码 0 + 空产物 → 判 empty-output，不得记 ok。
  - error_classify：三类特征（exit_code / output_check 判定 / log_regex）各一条规则
    命中正确动作；无命中 → 输出 unknown，脚本不猜——运行层只机械升级
    （证据齐全的 blocked，kind=failure），归类与提议加分类行由部署层 agent 做（R8）。
  - evidence_lint：含"通过"；或有数字无复现命令 → 报违禁。
  - verify_report：伪造计数/不存在路径/被改动的摘录 → 逐条揪出。
  - spotcheck：总体指纹变化后同种子重抽 → 报"总体已变"，不得静默给出不同样本。
  - regression_check：新数字与 active claim 冲突 → 出清单落 reports/。
- 在 new1 挂接后，端到端剧本 §8 的 1-3 步（不动 GPU）真实走通一遍。
- **铁轨兼容承诺（修订版）**：不改变 ticket-run/gpu-run/probe-pipeline/paper-write
  的对外流程与现有行为；new1 挂接所需的**增量改动单列挂接清单**进实施计划，
  已知七项：① 发射器补写 launch_order_ref 等回指字段；② record.py 改造成
  §5 普通行入口——**三件全是新增不是核实**（现状已核实 2026-08-13：
  record.py 写的是 ev=start/finish 两行事件流、runs.jsonl 写入路径上无任何锁）：
  (a) runs.jsonl 文件锁从零新增，与 ledger.py runs-append 约定同一把锁文件
  与协议（fallback/record.py 同协议）；(b) 行型改造——新行按 §5 单指标行入账，
  旧事件流账冻结为 `runs.legacy.jsonl`。**冻结是一次性接线迁移**，不是账本
  写入：执行者 = 用户确认下的接线会话；机验 = legacy 文件与原 runs.jsonl
  逐字节一致、新主文件从零行开始；执行件是 `ledger.py freeze-legacy`
  （不收 --layer、只在用户确认下跑、跑完打印两条机验结果，重复执行拒）；
  对 §2.1"archive 唯一搬行"条款是显式成文豁免（该条款已注明）。
  legacy 挂 `ledgers.runs_legacy`（owners=**frozen**——只读冻结件，
  任何写入拒（§7 值域第九值），监察面追溯起点因此不缺块；接线会话按
  §7 owners 来源句同批补齐两处键）；
  (c) recorded_at/metric_name/n/batch_id/arm/filter/schema_version 等
  §5 字段由 record.py 自动补齐（arm/filter 从发射单透传，§5）；③ RUNMETA 增 outputs 字典；
  ④ 发射器接受部署层给定的 run_id（new1 发射器现以任务
  name 为入参，大概率零改动，需核实）；⑤ registry_query 的只读免门禁入口核实/新增；
  ⑥ METHOD.md 改造成 R1 条目表：定列名与顺序、给现有条目补
  principle_id/applies_when/rationale（rationale 缺的回 idea 层追问用户）、
  criterion_cmd 逐条挂注册表命令（挂不上的按 R1 未接线态标【想法待定】）；
  ⑦ RESULTS.md 渲染器跟随②的行型改造（兼容读 legacy 或一次重渲，实施定——
  §7"渲染链依赖全量行"的依赖对象随之切到新行型）。
  每项逐项过工程自检；①—⑦任一项若涉及流程改动，先回本 spec 走 R5。

## 10 不做什么（YAGNI）

- 不重写任何现有铁轨 skill 的内容，只路由挂接（增量字段见 §9 挂接清单）。
- 不做多研究线并行目录树（schema 已带主键，将来平移不返工）。
- 不做 web 界面；监察面产出是文本报告。
- 不做自动触发（hooks）；路由由对话触发。
- **后置（audit P2 + 二轮验收判定的非阻塞项）**：reports/ 与待决账的通知/时限提醒
  （先用"开工必读"和会话出口回报顶）、下行"临时指令/补证请求"专用体裁
  （先用 spec 的 exploratory 标记和路由句顶）、台账成本字段的可行性查询视图
  （elapsed_s/gpu_count 已入账，视图后置）、监察会话只读性的钩子验证、
  归档的自动执行（定期 --auto；首期一律 doctor 建议 + 用户确认，
  用户批注"可自动"的诉求后置不弃）。
- md 系统最终定形（哪些渲染到根目录、叫什么名）随实施定，不在 spec 锁死。
